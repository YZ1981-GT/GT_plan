"""坏账准备明细表 D2-3 嵌套子表服务（NestedTableService）

管理父行/子行 CRUD、排序、层级完整性校验。对应 design.md
「Components and Interfaces #1 NestedTableService」。

铁律：
- service 只 flush 不 commit（跨 service 编排由 router 统一 commit 保原子）。
- asyncpg 事务污染：可能触发唯一约束的 flush 用 SAVEPOINT（begin_nested）包裹，
  捕获 IntegrityError 后 rollback savepoint 再抛 ValueError，避免污染整个外层事务。
- 乐观锁/层级冲突用自定义异常类便于 router 映射 409/400/422。

父行金额口径：
- 父行有子行 → 金额列 = sum_children(子行)，并持久化到父行 13 列（供公式引擎直接读列）。
- 父行无子行 → 使用父行自身存储值，is_editable=True。
- 合计行（Summary_Row）= sum_parents(全部父行有效金额)，运行时计算不落库。

Requirements: 1.2, 1.3, 2.1, 2.4, 2.5, 2.6, 3.1, 6.7, 8.2, 8.3, 8.4, 8.5, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.bad_debt_models import (
    PROVISION_METHOD_LABELS,
    BadDebtDetailRow,
    ProvisionMethod,
)
from app.schemas.bad_debt_schemas import (
    BadDebtTreeResponse,
    ChildRowResponse,
    CreateChildRowDTO,
    CreateParentRowDTO,
    ParentRowResponse,
    RowAmounts,
    SummaryRowResponse,
    UpdateRowDTO,
)
from app.services.bad_debt_account_codes import bad_debt_provision_account
from app.services.bad_debt_auto_sum import AutoSumEngine

# 13 金额列名 amount_b ~ amount_n
_AMOUNT_COLUMNS = AutoSumEngine.AMOUNT_COLUMNS


# ─── 自定义异常（供 router 映射 HTTP 状态码）────────────────────────────────


class BadDebtServiceError(Exception):
    """坏账准备嵌套服务基础异常。"""


class RowNotFoundError(BadDebtServiceError):
    """行不存在（→ 404）。"""


class OptimisticLockError(BadDebtServiceError):
    """乐观锁 version 不匹配，并发冲突（→ 409）。"""


class HierarchyError(BadDebtServiceError):
    """层级约束违反：删最后一个父行 / 父行有子行时编辑金额（→ 400）。"""


class DuplicateProvisionMethodError(BadDebtServiceError, ValueError):
    """同一 sheet 内 provision_method 重复（→ 409）。继承 ValueError 满足"捕获 IntegrityError→ValueError"。"""


# ─── 完整性校验错误结构 ──────────────────────────────────────────────────────


class BadDebtValidationError(BaseModel):
    """validate_integrity 返回的单条校验错误。"""

    row_id: uuid.UUID | None = None
    code: str          # ORPHAN_CHILD | PRECISION_OVERFLOW | PARENT_SUM_MISMATCH
    message: str
    action: str | None = None  # 如 "RESUM"（重新汇总）


# ─── 内部工具 ────────────────────────────────────────────────────────────────


def _row_to_amounts(row: BadDebtDetailRow) -> RowAmounts:
    """从 ORM 行抽取 13 金额列为 RowAmounts。"""
    return RowAmounts(**{col: getattr(row, col) for col in _AMOUNT_COLUMNS})


def _apply_amounts(row: BadDebtDetailRow, amounts: RowAmounts) -> None:
    """将 RowAmounts 13 列写回 ORM 行（全量替换）。"""
    for col in _AMOUNT_COLUMNS:
        setattr(row, col, getattr(amounts, col))


def _within_numeric_18_2(value: Decimal) -> bool:
    """校验金额落在 NUMERIC(18,2) 精度内：整数位 ≤ 16，小数位 ≤ 2。"""
    sign, digits, exponent = Decimal(str(value)).normalize().as_tuple()
    if not isinstance(exponent, int):
        return False  # NaN / Infinity
    # 小数位数（exponent 为负时即小数位）
    frac_digits = -exponent if exponent < 0 else 0
    if frac_digits > 2:
        return False
    # 整数位数 = 总位数 - 小数位数（含 exponent 为正的放大）
    total_digits = len(digits) + (exponent if exponent > 0 else 0)
    int_digits = total_digits - min(frac_digits, len(digits))
    return int_digits <= 16


def _normalize(value: Decimal | None) -> Decimal:
    """None 视作 0，量化到两位小数用于比较。"""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


# ─── 序列化 / 反序列化辅助 ───────────────────────────────────────────────────

# 序列化 JSON 格式版本号（便于未来结构演进时兼容）
_SERIALIZE_FORMAT_VERSION = 1


def _amounts_to_jsonable(row: BadDebtDetailRow) -> dict[str, str | None]:
    """将 ORM 行 13 金额列导出为 JSON 友好字典（Decimal → str 保精度，None → null）。"""
    out: dict[str, str | None] = {}
    for col in _AMOUNT_COLUMNS:
        val = getattr(row, col)
        out[col] = None if val is None else str(val)
    return out


def _parse_amount(
    value: object, label: str, errors: list[str]
) -> Decimal | None:
    """解析单个金额值：None → None；可解析为 Decimal 且落在 NUMERIC(18,2) 内 → Decimal；
    否则向 errors 追加详细错误并返回 None。
    """
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        errors.append(f"{label}: 金额无法解析为数值 ({value!r})")
        return None
    if dec.is_nan() or dec.is_infinite():
        errors.append(f"{label}: 金额非法 ({value!r})")
        return None
    if not _within_numeric_18_2(dec):
        errors.append(f"{label}: 金额 {dec} 超出 NUMERIC(18,2) 精度范围")
        return None
    return dec


def _parse_amounts_block(
    block: object, label: str, errors: list[str]
) -> dict[str, Decimal | None]:
    """解析 amounts 块（13 金额列），返回列名→Decimal|None 字典。

    block 缺失（None）视作全空；类型非 dict 记录错误。未知键忽略，缺失列视作 None。
    """
    parsed: dict[str, Decimal | None] = {col: None for col in _AMOUNT_COLUMNS}
    if block is None:
        return parsed
    if not isinstance(block, dict):
        errors.append(f"{label}: amounts 必须是对象，实际为 {type(block).__name__}")
        return parsed
    for col in _AMOUNT_COLUMNS:
        if col in block:
            parsed[col] = _parse_amount(block[col], f"{label}.{col}", errors)
    return parsed


class _NormalizedChild(BaseModel):
    """反序列化校验通过后的规范化子行。"""

    row_label: str
    sort_order: int
    amounts: dict[str, Decimal | None]

    model_config = {"arbitrary_types_allowed": True}


class _NormalizedParent(BaseModel):
    """反序列化校验通过后的规范化父行。"""

    provision_method: str
    row_label: str
    sort_order: int
    amounts: dict[str, Decimal | None]
    children: list[_NormalizedChild]

    model_config = {"arbitrary_types_allowed": True}


def _validate_and_normalize_payload(
    payload: object,
) -> tuple[list[str], list[_NormalizedParent]]:
    """校验并规范化 deserialize 入参。

    返回 (errors, normalized_parents)：errors 非空时 normalized 不可用（不应写库）。
    校验项：
    - payload 是对象且含 parents 列表
    - 每个父行：provision_method 必填且为合法枚举、不重复；row_label 必填非空
    - 每个子行：row_label 必填非空
    - 所有金额列可解析且落在 NUMERIC(18,2) 精度内
    """
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ([f"payload 必须是 JSON 对象，实际为 {type(payload).__name__}"], [])

    raw_parents = payload.get("parents")
    if raw_parents is None:
        errors.append("缺少必要字段: parents")
        return (errors, [])
    if not isinstance(raw_parents, list):
        errors.append(f"parents 必须是数组，实际为 {type(raw_parents).__name__}")
        return (errors, [])

    valid_methods = {m.value for m in ProvisionMethod}
    seen_methods: set[str] = set()
    normalized: list[_NormalizedParent] = []

    for p_idx, raw_parent in enumerate(raw_parents):
        plabel = f"parents[{p_idx}]"
        if not isinstance(raw_parent, dict):
            errors.append(f"{plabel}: 父行必须是对象")
            continue

        # provision_method 必填 + 合法 + 不重复
        method = raw_parent.get("provision_method")
        if method is None:
            errors.append(f"{plabel}: 缺少必要字段 provision_method")
        elif not isinstance(method, str) or method not in valid_methods:
            errors.append(
                f"{plabel}: provision_method 非法值 {method!r}，"
                f"合法值={sorted(valid_methods)}"
            )
        elif method in seen_methods:
            errors.append(f"{plabel}: provision_method 重复 {method!r}（同一底稿不允许重复计提方法）")
        else:
            seen_methods.add(method)

        # row_label 必填非空
        row_label = raw_parent.get("row_label")
        if not isinstance(row_label, str) or not row_label.strip():
            errors.append(f"{plabel}: 缺少必要字段 row_label 或为空")

        sort_order = raw_parent.get("sort_order")
        if sort_order is None:
            sort_order = (p_idx + 1) * 10
        elif not isinstance(sort_order, int):
            errors.append(f"{plabel}: sort_order 必须是整数，实际为 {type(sort_order).__name__}")
            sort_order = (p_idx + 1) * 10

        p_amounts = _parse_amounts_block(raw_parent.get("amounts"), plabel, errors)

        # 子行
        raw_children = raw_parent.get("children", [])
        norm_children: list[_NormalizedChild] = []
        if raw_children is None:
            raw_children = []
        if not isinstance(raw_children, list):
            errors.append(f"{plabel}.children: 必须是数组，实际为 {type(raw_children).__name__}")
            raw_children = []

        for c_idx, raw_child in enumerate(raw_children):
            clabel = f"{plabel}.children[{c_idx}]"
            if not isinstance(raw_child, dict):
                errors.append(f"{clabel}: 子行必须是对象")
                continue
            c_label = raw_child.get("row_label")
            if not isinstance(c_label, str) or not c_label.strip():
                errors.append(f"{clabel}: 缺少必要字段 row_label 或为空")
            c_sort = raw_child.get("sort_order")
            if c_sort is None:
                c_sort = (c_idx + 1) * 10
            elif not isinstance(c_sort, int):
                errors.append(f"{clabel}: sort_order 必须是整数，实际为 {type(c_sort).__name__}")
                c_sort = (c_idx + 1) * 10
            c_amounts = _parse_amounts_block(raw_child.get("amounts"), clabel, errors)
            norm_children.append(
                _NormalizedChild(
                    row_label=c_label if isinstance(c_label, str) else "",
                    sort_order=c_sort,
                    amounts=c_amounts,
                )
            )

        # 仅当本父行结构基本完整时收入 normalized（即便如此，只要 errors 非空就不会写库）
        normalized.append(
            _NormalizedParent(
                provision_method=method if isinstance(method, str) else "",
                row_label=row_label if isinstance(row_label, str) else "",
                sort_order=sort_order,
                amounts=p_amounts,
                children=norm_children,
            )
        )

    return (errors, normalized)


# ─── wp_id 归一解析（working_paper.id ↔ wp_index_id 兼容）─────────────────────


async def resolve_wp_index_id(db: AsyncSession, wp_id: uuid.UUID) -> uuid.UUID:
    """将路由路径参数 wp_id 归一为 wp_index_id。

    背景：GtWpRenderer 经 render-config 链路向所有子组件传 `working_paper.id`
    （铁律：route wpId 是 working_paper.id 非 wp_index 节点 id），但坏账准备明细表
    整条链路按 wp_index_id 寻址。为同时兼容两种入参：
      1. 先按 working_paper.id 查 WorkingPaper.wp_index_id，命中则返回解析出的
         wp_index_id（前端经渲染链传来的场景）；
      2. 查不到（说明传入的本身就是 wp_index_id，如直接调 API / 现有测试）→
         原值返回。

    该函数为只读查询，不产生写操作。
    """
    from app.models.workpaper_models import WorkingPaper

    row = (
        await db.execute(
            select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id)
        )
    ).first()
    if row is not None:
        return row[0]
    # 查不到 working_paper → 入参本身即 wp_index_id，回退原值
    return wp_id


# ─── NestedTableService ──────────────────────────────────────────────────────


class NestedTableService:
    """坏账准备明细表 D2-3 嵌套子表服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 内部查询 ────────────────────────────────────────────────────────────

    async def _get_row(self, row_id: uuid.UUID) -> BadDebtDetailRow:
        """按 id 取单行，不存在抛 RowNotFoundError。"""
        row = await self.db.get(BadDebtDetailRow, row_id)
        if row is None:
            raise RowNotFoundError(f"行不存在: {row_id}")
        return row

    async def _list_all_rows(self, wp_index_id: uuid.UUID) -> list[BadDebtDetailRow]:
        """取某底稿下全部行（父行+子行），按 sort_order 排序。"""
        stmt = (
            select(BadDebtDetailRow)
            .where(BadDebtDetailRow.wp_index_id == wp_index_id)
            .order_by(BadDebtDetailRow.sort_order, BadDebtDetailRow.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _list_children(self, parent_row_id: uuid.UUID) -> list[BadDebtDetailRow]:
        """取某父行下全部子行，按 sort_order 排序。"""
        stmt = (
            select(BadDebtDetailRow)
            .where(BadDebtDetailRow.parent_row_id == parent_row_id)
            .order_by(BadDebtDetailRow.sort_order, BadDebtDetailRow.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _effective_parent_amounts(
        self, parent: BadDebtDetailRow, children: list[BadDebtDetailRow]
    ) -> RowAmounts:
        """父行有效金额：有子行 → 子行合计；无子行 → 父行自身存储值。"""
        if children:
            return AutoSumEngine.sum_children([_row_to_amounts(c) for c in children])
        return _row_to_amounts(parent)

    # ─── 3.1 get_tree ─────────────────────────────────────────────────────────

    async def get_tree(self, wp_index_id: uuid.UUID) -> BadDebtTreeResponse:
        """返回完整嵌套树：父行嵌套 children + Summary 合计 + 每行 balance_check。

        - 父行金额：有子行则等于 sum_children，无子行则用自身存储值；is_editable=无子行。
        - Summary：sum_parents(全部父行有效金额) + 平衡公式校验。

        Requirements: 2.1, 8.2, 8.3
        """
        rows = await self._list_all_rows(wp_index_id)

        # 分离父行与按父分组的子行
        parents = [r for r in rows if r.parent_row_id is None]
        children_by_parent: dict[uuid.UUID, list[BadDebtDetailRow]] = {}
        for r in rows:
            if r.parent_row_id is not None:
                children_by_parent.setdefault(r.parent_row_id, []).append(r)

        parent_responses: list[ParentRowResponse] = []
        parent_effective_amounts: list[RowAmounts] = []

        for parent in parents:
            children = children_by_parent.get(parent.id, [])
            children.sort(key=lambda c: (c.sort_order, c.created_at))
            effective = self._effective_parent_amounts(parent, children)
            parent_effective_amounts.append(effective)

            child_responses = [
                ChildRowResponse(
                    id=c.id,
                    parent_row_id=c.parent_row_id,
                    sort_order=c.sort_order,
                    row_label=c.row_label,
                    amounts=_row_to_amounts(c),
                    version=c.version,
                )
                for c in children
            ]

            method = ProvisionMethod(parent.provision_method) if parent.provision_method else None
            parent_responses.append(
                ParentRowResponse(
                    id=parent.id,
                    provision_method=method,
                    provision_method_label=(
                        PROVISION_METHOD_LABELS.get(method, "") if method else ""
                    ),
                    sort_order=parent.sort_order,
                    row_label=parent.row_label,
                    amounts=effective,
                    children=child_responses,
                    version=parent.version,
                    is_editable=len(children) == 0,
                )
            )

        summary_amounts = AutoSumEngine.sum_parents(parent_effective_amounts)
        summary = SummaryRowResponse(
            amounts=summary_amounts,
            balance_check=AutoSumEngine.validate_balance_formula(summary_amounts),
        )

        return BadDebtTreeResponse(
            wp_index_id=wp_index_id,
            summary=summary,
            parents=parent_responses,
            prefill_source=None,
        )


    # ─── 7.1 serialize ────────────────────────────────────────────────────────

    async def serialize(self, wp_index_id: uuid.UUID) -> dict:
        """将某底稿完整嵌套结构导出为 JSON 友好的 dict。

        结构::

            {
              "format_version": 1,
              "wp_index_id": "<uuid>",
              "parents": [
                {
                  "provision_method": "INDIVIDUAL",
                  "provision_method_label": "按单项评估计提",
                  "row_label": "按单项评估计提",
                  "sort_order": 10,
                  "amounts": {"amount_b": "100.00", ..., "amount_n": null},
                  "children": [
                    {"row_label": "其中：甲公司", "sort_order": 10,
                     "amounts": {"amount_e": "10.00", ...}}
                  ]
                }
              ]
            }

        - 金额 Decimal → str 保精度，None → null。
        - 父行/子行均按 sort_order, created_at 稳定排序。
        - 父行金额导出其当前存储值（有子行时已被 _resum_parent 落库为子行合计）。

        Requirements: 11.1, 11.2
        """
        rows = await self._list_all_rows(wp_index_id)

        parents = [r for r in rows if r.parent_row_id is None]
        children_by_parent: dict[uuid.UUID, list[BadDebtDetailRow]] = {}
        for r in rows:
            if r.parent_row_id is not None:
                children_by_parent.setdefault(r.parent_row_id, []).append(r)

        parents.sort(key=lambda p: p.sort_order)

        parents_json: list[dict] = []
        for parent in parents:
            children = children_by_parent.get(parent.id, [])
            children.sort(key=lambda c: c.sort_order)

            method = (
                ProvisionMethod(parent.provision_method)
                if parent.provision_method
                else None
            )
            parents_json.append(
                {
                    "provision_method": parent.provision_method,
                    "provision_method_label": (
                        PROVISION_METHOD_LABELS.get(method, "") if method else ""
                    ),
                    "row_label": parent.row_label,
                    "sort_order": parent.sort_order,
                    "amounts": _amounts_to_jsonable(parent),
                    "children": [
                        {
                            "row_label": c.row_label,
                            "sort_order": c.sort_order,
                            "amounts": _amounts_to_jsonable(c),
                        }
                        for c in children
                    ],
                }
            )

        return {
            "format_version": _SERIALIZE_FORMAT_VERSION,
            "wp_index_id": str(wp_index_id),
            "parents": parents_json,
        }

    # ─── 7.1 deserialize ──────────────────────────────────────────────────────

    async def deserialize(self, wp_index_id: uuid.UUID, payload: dict) -> list[str]:
        """从 JSON dict 恢复完整嵌套结构到数据库（先清空该底稿现有行再重建）。

        - 校验失败（缺必要字段/枚举非法/重复/金额越界/层级无效）时**不写库**，
          返回详细 ValidationError 信息列表（不静默忽略）。
        - 校验通过：删除该 wp_index_id 下全部现有行（先删子行再删父行避免外键孤儿），
          按 payload 重建父行+子行，sort_order 与 provision_method 原样恢复。
        - service 只 flush 不 commit（由 router 统一 commit）。

        Requirements: 11.1, 11.2, 11.4
        """
        errors, normalized = _validate_and_normalize_payload(payload)
        if errors:
            return errors

        # 清空现有行：先删子行（parent_row_id 非空）再删父行，避免自引用外键孤儿
        await self.db.execute(
            delete(BadDebtDetailRow).where(
                BadDebtDetailRow.wp_index_id == wp_index_id,
                BadDebtDetailRow.parent_row_id.is_not(None),
            )
        )
        await self.db.execute(
            delete(BadDebtDetailRow).where(
                BadDebtDetailRow.wp_index_id == wp_index_id,
                BadDebtDetailRow.parent_row_id.is_(None),
            )
        )
        await self.db.flush()

        # 重建
        for np in normalized:
            parent = BadDebtDetailRow(
                id=uuid.uuid4(),
                wp_index_id=wp_index_id,
                parent_row_id=None,
                provision_method=np.provision_method,
                sort_order=np.sort_order,
                row_label=np.row_label,
                version=1,
            )
            for col, val in np.amounts.items():
                setattr(parent, col, val)
            self.db.add(parent)
            await self.db.flush()

            for nc in np.children:
                child = BadDebtDetailRow(
                    id=uuid.uuid4(),
                    wp_index_id=wp_index_id,
                    parent_row_id=parent.id,
                    provision_method=None,
                    sort_order=nc.sort_order,
                    row_label=nc.row_label,
                    version=1,
                )
                for col, val in nc.amounts.items():
                    setattr(child, col, val)
                self.db.add(child)
            await self.db.flush()

        return []

    # ─── 父行汇总重算（持久化）─────────────────────────────────────────────────

    async def _resum_parent(self, parent: BadDebtDetailRow) -> None:
        """重算父行 13 列 = sum_children(子行) 并写回父行（flush 不 commit）。

        仅在父行有子行时覆盖父行金额；无子行时保留父行自身值（允许直接编辑）。
        """
        children = await self._list_children(parent.id)
        if not children:
            return
        summed = AutoSumEngine.sum_children([_row_to_amounts(c) for c in children])
        _apply_amounts(parent, summed)
        await self.db.flush()

    # ─── 3.2 create_parent_row ────────────────────────────────────────────────

    async def create_parent_row(
        self, wp_index_id: uuid.UUID, data: CreateParentRowDTO
    ) -> ParentRowResponse:
        """新增父行：必须指定 provision_method，唯一偏索引拦截同 sheet 重复。

        用 SAVEPOINT 包裹 flush，捕获 IntegrityError 后 rollback savepoint 再抛
        DuplicateProvisionMethodError（继承 ValueError），避免污染外层事务。

        Requirements: 1.2, 1.3, 2.6
        """
        # 新父行 sort_order = 现有父行最大值 + 10（留间隔便于插入）
        max_stmt = select(func.max(BadDebtDetailRow.sort_order)).where(
            BadDebtDetailRow.wp_index_id == wp_index_id,
            BadDebtDetailRow.parent_row_id.is_(None),
        )
        max_order = (await self.db.execute(max_stmt)).scalar()
        next_order = (max_order or 0) + 10

        row = BadDebtDetailRow(
            id=uuid.uuid4(),
            wp_index_id=wp_index_id,
            parent_row_id=None,
            provision_method=data.provision_method.value,
            sort_order=next_order,
            row_label=data.row_label,
            version=1,
        )

        nested = await self.db.begin_nested()
        try:
            self.db.add(row)
            await self.db.flush()
            await nested.commit()
        except IntegrityError as exc:
            await nested.rollback()
            raise DuplicateProvisionMethodError(
                f"同一底稿下计提方法已存在: {data.provision_method.value}"
            ) from exc

        method = data.provision_method
        return ParentRowResponse(
            id=row.id,
            provision_method=method,
            provision_method_label=PROVISION_METHOD_LABELS.get(method, ""),
            sort_order=row.sort_order,
            row_label=row.row_label,
            amounts=_row_to_amounts(row),
            children=[],
            version=row.version,
            is_editable=True,
        )

    # ─── 3.2 create_child_row ─────────────────────────────────────────────────

    async def _compute_child_sort_order(
        self,
        parent_row_id: uuid.UUID,
        *,
        insert_before_id: uuid.UUID | None = None,
        insert_after_id: uuid.UUID | None = None,
    ) -> int:
        """计算子行 sort_order：默认末尾；支持在某子行之前/之后插入。"""
        if insert_before_id and insert_after_id:
            raise HierarchyError("insert_before_id 与 insert_after_id 不能同时指定")

        children = await self._list_children(parent_row_id)
        if not children:
            return 10

        if not insert_before_id and not insert_after_id:
            return children[-1].sort_order + 10

        ref_id = insert_before_id or insert_after_id
        ref_idx = next((i for i, c in enumerate(children) if c.id == ref_id), -1)
        if ref_idx < 0:
            raise RowNotFoundError(f"参考子行不存在: {ref_id}")

        ref = children[ref_idx]
        if insert_before_id:
            prev = children[ref_idx - 1] if ref_idx > 0 else None
            if prev is None:
                return max(ref.sort_order - 5, 1)
            gap = ref.sort_order - prev.sort_order
            if gap > 1:
                return prev.sort_order + gap // 2
            return await self._renumber_children_and_slot(parent_row_id, ref_idx)
        # insert_after_id
        nxt = children[ref_idx + 1] if ref_idx + 1 < len(children) else None
        if nxt is None:
            return ref.sort_order + 10
        gap = nxt.sort_order - ref.sort_order
        if gap > 1:
            return ref.sort_order + gap // 2
        return await self._renumber_children_and_slot(parent_row_id, ref_idx + 1)

    async def _renumber_children_and_slot(
        self, parent_row_id: uuid.UUID, slot_index: int
    ) -> int:
        """子行 sort_order 间隙耗尽时按 10 步长重编号，返回 slot_index 位置的新 order。"""
        children = await self._list_children(parent_row_id)
        for i, child in enumerate(children):
            child.sort_order = (i + 1) * 10
        await self.db.flush()
        if slot_index <= 0:
            return 5
        if slot_index >= len(children):
            return children[-1].sort_order + 10
        prev_order = children[slot_index - 1].sort_order
        next_order = children[slot_index].sort_order
        return prev_order + max((next_order - prev_order) // 2, 1)

    async def create_child_row(
        self, parent_row_id: uuid.UUID, data: CreateChildRowDTO
    ) -> ChildRowResponse:
        """新增子行：默认末尾；可指定在某子行之前/之后插入。触发父行汇总重算。

        Requirements: 1.2, 2.4, 2.6, 3.1
        """
        parent = await self._get_row(parent_row_id)
        if parent.parent_row_id is not None:
            raise HierarchyError("不能在子行下再创建子行（仅支持两层嵌套）")

        next_order = await self._compute_child_sort_order(
            parent_row_id,
            insert_before_id=data.insert_before_id,
            insert_after_id=data.insert_after_id,
        )

        child = BadDebtDetailRow(
            id=uuid.uuid4(),
            wp_index_id=parent.wp_index_id,
            parent_row_id=parent_row_id,
            provision_method=None,
            sort_order=next_order,
            row_label=data.row_label,
            amount_e=data.amount_e,
            amount_k=data.amount_k,
            amount_n=data.amount_n,
            version=1,
        )
        self.db.add(child)
        await self.db.flush()

        # 触发父行汇总重算
        await self._resum_parent(parent)

        return ChildRowResponse(
            id=child.id,
            parent_row_id=parent_row_id,
            sort_order=child.sort_order,
            row_label=child.row_label,
            amounts=_row_to_amounts(child),
            version=child.version,
        )


    # ─── 3.3 update_row（乐观锁）──────────────────────────────────────────────

    async def update_row(self, row_id: uuid.UUID, data: UpdateRowDTO) -> RowAmounts:
        """更新单行金额/标签，乐观锁校验。

        - 传入 version 与当前不一致 → OptimisticLockError（409）。
        - 父行有子行时拒绝直接编辑金额列 → HierarchyError（400）。
        - 成功更新后重算父→合计，version += 1。

        Requirements: 2.5, 6.7, 8.5, 10.5
        """
        row = await self._get_row(row_id)

        # 乐观锁：version 不匹配即冲突
        if row.version != data.version:
            raise OptimisticLockError(
                f"并发冲突：期望 version={data.version}，当前 version={row.version}"
            )

        is_parent = row.parent_row_id is None

        # 父行有子行时拒绝直接编辑金额列（金额由子行汇总决定）
        if is_parent and data.amounts is not None:
            children = await self._list_children(row.id)
            if children:
                raise HierarchyError("父行存在子行，金额由子行汇总决定，不可直接编辑")

        if data.row_label is not None:
            row.row_label = data.row_label
        if data.amounts is not None:
            _apply_amounts(row, data.amounts)

        row.version += 1
        await self.db.flush()

        # 子行变更 → 重算其父行；父行（无子行）变更 → 合计由 get_tree 运行时算
        if row.parent_row_id is not None:
            parent = await self._get_row(row.parent_row_id)
            await self._resum_parent(parent)

        return _row_to_amounts(row)

    # ─── 3.3 delete_row（级联）────────────────────────────────────────────────

    async def delete_row(self, row_id: uuid.UUID) -> None:
        """删除行：

        - 删子行后重算父行汇总。
        - 删父行：ORM cascade 级联删子行；但拒绝删除最后一个父行（→ 400）。

        Requirements: 2.5, 8.4, 10.5
        """
        row = await self._get_row(row_id)

        if row.parent_row_id is None:
            # 父行：至少保留一个计提类别
            count_stmt = select(func.count()).where(
                BadDebtDetailRow.wp_index_id == row.wp_index_id,
                BadDebtDetailRow.parent_row_id.is_(None),
            )
            parent_count = (await self.db.execute(count_stmt)).scalar() or 0
            if parent_count <= 1:
                raise HierarchyError("至少保留一个计提类别，不能删除最后一个父行")

            # 级联删子行（不依赖 ORM relationship 缓存，直接 DELETE 子行再删父行，
            # 兼容 SQLite 无 ON DELETE CASCADE 的测试场景）
            await self.db.execute(
                delete(BadDebtDetailRow).where(
                    BadDebtDetailRow.parent_row_id == row.id
                )
            )
            await self.db.delete(row)
            await self.db.flush()
        else:
            # 子行：删除后重算父行汇总
            parent_id = row.parent_row_id
            await self.db.delete(row)
            await self.db.flush()
            parent = await self._get_row(parent_id)
            await self._resum_parent(parent)

    # ─── 3.4 validate_integrity ───────────────────────────────────────────────

    async def validate_integrity(
        self,
        wp_index_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        year: int | None = None,
    ) -> list[BadDebtValidationError]:
        """完整性校验：

        - 孤儿子行：parent_row_id 指向的父行不存在或不在同一 wp_index_id 下。
        - 金额精度：13 金额列不超 NUMERIC(18,2)（整数位 ≤16、小数位 ≤2）。
        - 父行显示值与子行合计不一致：标记 PARENT_SUM_MISMATCH + "重新汇总"动作。
        - Summary_Row 期末审定数(N) 与 TB 科目 1231 audited_amount 比对（仅当
          同时提供 project_id 与 year 时执行；不提供则跳过，保持向后兼容）：
          不等标记 SUMMARY_TB_MISMATCH；TB 无 1231 数据则跳过（无可比基准）。

        Requirements: 10.1, 10.2, 10.3, 10.4
        """
        errors: list[BadDebtValidationError] = []
        rows = await self._list_all_rows(wp_index_id)

        # 同 wp_index 下有效父行 id 集合
        parent_ids = {
            r.id for r in rows if r.parent_row_id is None
        }
        children_by_parent: dict[uuid.UUID, list[BadDebtDetailRow]] = {}
        for r in rows:
            if r.parent_row_id is not None:
                children_by_parent.setdefault(r.parent_row_id, []).append(r)

        # 1) 孤儿子行
        for r in rows:
            if r.parent_row_id is not None and r.parent_row_id not in parent_ids:
                errors.append(
                    BadDebtValidationError(
                        row_id=r.id,
                        code="ORPHAN_CHILD",
                        message=(
                            f"子行 {r.id} 的 parent_row_id={r.parent_row_id} "
                            f"未指向同一底稿下的有效父行"
                        ),
                    )
                )

        # 2) 金额精度
        for r in rows:
            for col in _AMOUNT_COLUMNS:
                val = getattr(r, col)
                if val is None:
                    continue
                if not _within_numeric_18_2(val):
                    errors.append(
                        BadDebtValidationError(
                            row_id=r.id,
                            code="PRECISION_OVERFLOW",
                            message=f"行 {r.id} 列 {col} 金额 {val} 超出 NUMERIC(18,2) 精度",
                        )
                    )

        # 3) 父行显示值与子行合计不一致
        for parent in (r for r in rows if r.parent_row_id is None):
            children = children_by_parent.get(parent.id, [])
            if not children:
                continue
            expected = AutoSumEngine.sum_children(
                [_row_to_amounts(c) for c in children]
            )
            actual = _row_to_amounts(parent)
            for col in _AMOUNT_COLUMNS:
                exp_v = getattr(expected, col)
                act_v = getattr(actual, col)
                if _normalize(exp_v) != _normalize(act_v):
                    errors.append(
                        BadDebtValidationError(
                            row_id=parent.id,
                            code="PARENT_SUM_MISMATCH",
                            message=(
                                f"父行 {parent.id} 列 {col} 显示值 {act_v} "
                                f"与子行合计 {exp_v} 不一致"
                            ),
                            action="RESUM",
                        )
                    )
                    break  # 同一父行只报一次

        # 4) Summary_Row 期末审定数(N) vs TB 科目 1231 audited_amount（Req 10.1）
        #    仅当同时提供 project_id 与 year 时执行（向后兼容旧单参调用）。
        if project_id is not None and year is not None:
            await self._check_summary_against_tb(
                wp_index_id, project_id, year, rows, errors
            )

        return errors

    async def _check_summary_against_tb(
        self,
        wp_index_id: uuid.UUID,
        project_id: uuid.UUID,
        year: int,
        rows: list[BadDebtDetailRow],
        errors: list[BadDebtValidationError],
    ) -> None:
        """比对 Summary_Row 期末审定数(N) 与 TB 科目 1231 audited_amount。

        - Summary_Row 期末审定数 = sum_parents(全部父行有效金额).amount_n。
        - TB 1231 audited_amount 按 project_id+year 跨 company_code 聚合（软删排除）。
        - TB 无 1231 数据（行数为 0 或 audited 合计为 None）→ 跳过（无可比基准）。
        - 不等（容差 0.01）→ 追加 SUMMARY_TB_MISMATCH 校验提示。

        Requirements: 10.1
        """
        # Summary 期末审定数：复用 get_tree 同口径的父行有效金额汇总
        parents = [r for r in rows if r.parent_row_id is None]
        children_by_parent: dict[uuid.UUID, list[BadDebtDetailRow]] = {}
        for r in rows:
            if r.parent_row_id is not None:
                children_by_parent.setdefault(r.parent_row_id, []).append(r)

        parent_effective: list[RowAmounts] = [
            self._effective_parent_amounts(
                parent, children_by_parent.get(parent.id, [])
            )
            for parent in parents
        ]
        summary = AutoSumEngine.sum_parents(parent_effective)
        summary_n = summary.amount_n

        provision_code, provision_name = bad_debt_provision_account()

        # TB 坏账准备 audited_amount 聚合
        stmt = select(
            func.count(TrialBalance.id),
            func.sum(TrialBalance.audited_amount),
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == provision_code,
            TrialBalance.is_deleted.is_(False),
        )
        row_count, audited_sum = (await self.db.execute(stmt)).one()

        # 无可比基准 → 跳过（Req 10.1：不等时才提示，无数据不报）
        if not row_count or audited_sum is None:
            return

        tb_audited = _normalize(audited_sum)
        summary_norm = _normalize(summary_n)
        if summary_norm != tb_audited:
            errors.append(
                BadDebtValidationError(
                    row_id=None,
                    code="SUMMARY_TB_MISMATCH",
                    message=(
                        f"合计行期末审定数 {summary_norm} 与试算表科目 "
                        f"{provision_code} {provision_name} 审定数 {tb_audited} 不一致"
                    ),
                )
            )
