"""企业代码修改的影响检查（spec consol-group-code-entry-consistency R6）。

改企业代码前按**旧**代码、同一审计年度查引用；有任何引用返回 409 列出影响项，
不做「确认后照改」（平台尚无节点身份迁移能力，照改会让下级脱挂、合并附注与
映射挂在旧身份上，design §2.6）。

判据只看同一审计年度：历年数据按当年身份保留；历史留痕类表（树版本快照、
产物、运行记录）不算引用（design §2.6 / §1.8）。

R6.5 节点身份列登记：ORM 元数据中名为 ``node_key`` / ``entity_node_key`` /
``node_company_code`` 的列，每一列须在影响清单（``_IMPACT_SPECS``）里或登记
为豁免（``_NODE_IDENTITY_EXEMPTIONS``，附理由），新增未登记即打红（守卫测试
``test_wizard_company_code_change.py``）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.models.core import Project
from app.services.uscc_validator import normalize_uscc_input

COMPANY_CODE_IN_USE = "COMPANY_CODE_IN_USE"

# 这些列保存企业树节点身份。守卫只扫描列名，不把相似的业务字段误当成节点身份。
_NODE_IDENTITY_COLUMN_NAMES = frozenset(
    {"node_key", "entity_node_key", "node_company_code"}
)


@dataclass(frozen=True)
class _NodeIdentityExemption:
    """节点身份列的历史留痕豁免，必须有可核验的表列与非空理由。"""

    table: str
    column: str
    reason: str

    @property
    def key(self) -> str:
        return f"{self.table}.{self.column}"


# 这些列记录历史时刻的结构或产物，不是当前关系输入，不能阻止代码更正。
# ``validate_node_identity_exemptions`` 会核对表列真实存在，防止理由字符串变成静态白名单后失效。
_NODE_IDENTITY_EXEMPTIONS: tuple[_NodeIdentityExemption, ...] = (
    _NodeIdentityExemption(
        "consol_scope_confirmation_nodes",
        "node_key",
        "树版本快照，历史留痕（确认时刻的结构记录）",
    ),
    _NodeIdentityExemption(
        "consol_scope_confirmation_nodes",
        "company_code",
        "树版本快照，历史留痕",
    ),
    _NodeIdentityExemption(
        "consol_artifact",
        "node_key",
        "推送产物，历史留痕",
    ),
    _NodeIdentityExemption(
        "report_generation_run",
        "node_key",
        "报表运行记录，历史留痕",
    ),
)


@dataclass(frozen=True)
class _ImpactSpec:
    """一类引用：模型列 + 匹配方式 + 中文标签 + 计数说明。"""

    model: Any
    column: str
    match: str  # "exact" 精确等于旧码 | "node_prefix" 节点键前缀「{旧码}:」
    label: str
    kind: str


def _active_clause(model: Any) -> Any | None:
    """返回软删除表的活动行条件；没有该列的引用表不额外猜测状态。"""
    is_deleted = getattr(model, "is_deleted", None)
    return is_deleted.is_(False) if is_deleted is not None else None


def _add_active_filter(stmt: Any, model: Any) -> Any:
    active = _active_clause(model)
    return stmt.where(active) if active is not None else stmt


async def _count_exact(db: AsyncSession, model: Any, column: str, code: str, year: int | None) -> int:
    col = getattr(model, column)
    stmt = sa.select(sa.func.count()).select_from(model).where(col == code)
    year_col = getattr(model, "year", None)
    if year is not None and year_col is not None:
        stmt = stmt.where(year_col == year)
    stmt = _add_active_filter(stmt, model)
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_node_prefix(db: AsyncSession, model: Any, column: str, code: str, year: int | None) -> int:
    """节点键「{企业代码}:{角色}」按 LIKE 前缀匹配；无 year 列的表按所属合并项目年度过滤。"""
    col = getattr(model, column)
    pattern = f"{code}:%"
    year_col = getattr(model, "year", None)
    stmt = sa.select(sa.func.count()).select_from(model).where(col.like(pattern))
    if year_col is not None and year is not None:
        stmt = stmt.where(year_col == year)
    elif year_col is None:
        # 无年度列（当前只有 consol_note_mapping_binding）：经所属合并项目年度过滤。
        stmt = stmt.where(
            model.project_id.in_(
                sa.select(Project.id).where(
                    Project.audit_year == year,
                    Project.is_deleted.is_(False),
                )
            )
        )
    stmt = _add_active_filter(stmt, model)
    return int((await db.execute(stmt)).scalar() or 0)


# 影响清单（design §1.8「关系输入 / 合并数据」五类；判据见各 spec）
_IMPACT_SPECS: tuple[_ImpactSpec, ...] = (
    # 1. 同企业另一口径项目，以及其他项目的集团关系引用。
    _ImpactSpec(Project, "company_code", "other_scope", "同企业其他口径项目", "project_refs"),
    _ImpactSpec(Project, "parent_company_code", "exact", "以旧代码为上级的其他项目", "parent_refs"),
    _ImpactSpec(Project, "ultimate_company_code", "exact", "以旧代码为最终控制方的其他项目", "ultimate_refs"),
    # 2. 合并附注节点数据（node_key = "{代码}:{角色}"）
    _ImpactSpec("app.models.consol_note_data_models:ConsolNoteData", "node_key", "node_prefix",
                "合并附注节点数据", "consol_note_data"),
    # 3. 附注明细映射绑定（entity_node_key；无年度列，按所属合并项目年度）
    _ImpactSpec("app.models.consol_note_mapping_models:ConsolNoteMappingBinding", "entity_node_key",
                "node_prefix", "附注明细映射绑定", "mapping_binding"),
    # 4. 合并差额表（node_company_code 存节点键）
    _ImpactSpec("app.models.consolidation_models:ConsolWorksheet", "node_company_code", "node_prefix",
                "合并差额表", "worksheet"),
    # 5. 股权变动事件（node_key）
    _ImpactSpec("app.models.share_change_event_models:ShareChangeEvent", "node_key", "node_prefix",
                "股权变动事件", "share_change"),
)

# R6.5 豁免表：ORM 元数据中同名「节点身份列」但属历史留痕、不算引用。
# 保留一个按限定名索引的只读视图，兼容审计/测试代码只需要查登记集合的场景。


def _exemption_by_key() -> dict[str, _NodeIdentityExemption]:
    return {item.key: item for item in _NODE_IDENTITY_EXEMPTIONS}


def _resolve_model(spec: _ImpactSpec) -> Any:
    if isinstance(spec.model, str):
        module_path, _, class_name = spec.model.partition(":")
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    return spec.model


async def code_change_impacts(
    db: AsyncSession, project: Project, old_code: str, year: int | None
) -> list[dict[str, Any]]:
    """按旧代码、同一年度统计各类引用；返回 ``[{kind, label, count}]``。

    查询包在 SAVEPOINT 和 ``no_autoflush`` 中：检查失败时不会把调用方的 PG
    事务留在 aborted 状态，也不会把向导尚未提交的对象提前 flush。查询异常原样
    上抛，调用方不得把无法完成的影响检查误当成「无引用」（fail-closed）。
    """
    normalized_code = normalize_uscc_input(old_code)
    if normalized_code is None:
        return []
    effective_year = year if year is not None else getattr(project, "audit_year", None)
    if effective_year is None:
        raise ValueError("企业代码影响检查缺少审计年度，拒绝按全年度放行")

    impacts: list[dict[str, Any]] = []
    async with db.begin_nested():
        with db.no_autoflush:
            for spec in _IMPACT_SPECS:
                model = _resolve_model(spec)
                if spec.model is Project:
                    col = getattr(model, spec.column)
                    stmt = (
                        sa.select(sa.func.count())
                        .select_from(model)
                        .where(col == normalized_code)
                        .where(model.id != project.id)
                        .where(model.is_deleted.is_(False))
                    )
                    year_col = getattr(model, "audit_year", None)
                    if effective_year is not None and year_col is not None:
                        stmt = stmt.where(year_col == effective_year)
                    if spec.match == "other_scope":
                        # 同企业另一口径属于影响；同口径重复由唯一性检查负责。
                        stmt = stmt.where(model.report_scope != project.report_scope)
                    count = int((await db.execute(stmt)).scalar() or 0)
                elif spec.match == "exact":
                    count = await _count_exact(db, model, spec.column, normalized_code, effective_year)
                else:
                    count = await _count_node_prefix(db, model, spec.column, normalized_code, effective_year)
                if count > 0:
                    impacts.append({"kind": spec.kind, "label": spec.label, "count": count})
    return impacts


def raise_if_code_in_use(impacts: list[dict[str, Any]]) -> None:
    """有引用即 409（R6.2）：detail 带 error_code / message / impacts，不提供「确认后照改」。"""
    if not impacts:
        return
    summary = "、".join(f"{item['label']} {item['count']} 条" for item in impacts)
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": COMPANY_CODE_IN_USE,
            "message": (
                f"企业代码已被以下数据引用，不能直接修改：{summary}。"
                "如需更正代码，请先联系管理员处理关联数据。"
            ),
            "impacts": impacts,
        },
    )


def discover_node_identity_columns(registry: Any | None = None) -> set[str]:
    """从 SQLAlchemy mapper registry 实际枚举节点身份列。"""
    active_registry = registry if registry is not None else Base.registry
    discovered: set[str] = set()
    for mapper in active_registry.mappers:
        table = getattr(mapper, "local_table", None)
        if table is None:
            continue
        for column in table.columns:
            if column.name in _NODE_IDENTITY_COLUMN_NAMES:
                discovered.add(f"{table.name}.{column.name}")
    return discovered


def find_unregistered_node_identity_columns(
    discovered: set[str] | None = None, *, registry: Any | None = None
) -> set[str]:
    """返回实际扫描到但未登记的节点身份列；供守卫和变异测试共用。"""
    actual = discover_node_identity_columns(registry) if discovered is None else set(discovered)
    return actual - all_registered_node_identity_columns()


def validate_node_identity_exemptions(registry: Any | None = None) -> tuple[str, ...]:
    """校验豁免项有理由且对应真实 ORM 表列，避免静态字符串白名单恒绿。"""
    active_registry = registry if registry is not None else Base.registry
    actual_columns = {
        f"{table.name}.{column.name}"
        for mapper in active_registry.mappers
        if (table := getattr(mapper, "local_table", None)) is not None
        for column in table.columns
    }
    errors: list[str] = []
    seen: set[str] = set()
    for exemption in _NODE_IDENTITY_EXEMPTIONS:
        if exemption.key in seen:
            errors.append(f"重复豁免登记：{exemption.key}")
        seen.add(exemption.key)
        if not exemption.reason.strip():
            errors.append(f"豁免缺少可核验理由：{exemption.key}")
        if exemption.key not in actual_columns:
            errors.append(f"豁免对应的 ORM 表列不存在：{exemption.key}")
    return tuple(errors)


def all_registered_node_identity_columns() -> set[str]:
    """返回影响清单与豁免表中的全部登记限定名。"""
    registered: set[str] = set()
    for spec in _IMPACT_SPECS:
        model = _resolve_model(spec)
        registered.add(f"{model.__tablename__}.{spec.column}")
    registered.update(_exemption_by_key())
    return registered


__all__ = [
    "COMPANY_CODE_IN_USE",
    "code_change_impacts",
    "raise_if_code_in_use",
    "discover_node_identity_columns",
    "find_unregistered_node_identity_columns",
    "validate_node_identity_exemptions",
    "all_registered_node_identity_columns",
]
