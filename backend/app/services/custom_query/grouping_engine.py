"""GroupingEngine — 多维度分组聚合引擎（高级查询模块）

Task 9.1（advanced-query-module）：实现 0–10 维度分组聚合，供 QueryOrchestrator
在「DB 取回后的 Python 层」对业务视图查询结果（cell 级、非单表）做分组聚合。

设计要点（design.md §Components 4 GroupingEngine）：
- 支持 **0–10** 个分组维度，每个维度须为有效 addr_id 或结果集中存在的有效列
  （R5.1）；超 10 或无效维度 → ``INVALID_GROUP_DIM``（含 ``invalid`` 清单）、
  **保留原始查询条件不变、不执行**（R5.5）。
- 按维度值的唯一组合分组聚合（R5.2），结果按分组维度组合**升序**排序（R5.3）。
- 对数值型值字段支持 **sum/count/avg/max/min** 五种聚合（R5.4）；``count`` 适用
  于任意类型，``sum/avg/min/max`` 要求数值列——对非数值列施加这四类聚合 →
  ``AGG_TYPE_MISMATCH``（含 ``field``, ``agg``）、**保留条件、不执行**（R5.6）。
- 未指定任何分组维度 → 返回未分组的**明细结果集**（R5.7）。

两个入口的分工（design.md Architecture）：
- **白名单构建器入口**：``GROUP BY`` 直接走 SQL 层（``query_builder`` 的
  ``AGGREGATE_WHITELIST`` + ``_resolve_field_ref``，DB 内聚合）。
- **业务视图入口**：cell 级数据非单表，DB 取回后由本引擎在 Python 层分组聚合。

本引擎为**纯函数**（无 IO、无 async），便于属性测试（P6/P7/P8/P9，见 Task 9.2–9.5）。

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import decimal as _dec
from dataclasses import dataclass, field
from typing import Any, Iterable

from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# 常量：维度上限 + 聚合白名单（与 query_builder.AGGREGATE_WHITELIST 对齐）
# ─────────────────────────────────────────────────────────────────────────────
#: 分组维度数量上限（R5.1 / R5.5）
MAX_GROUP_DIMS: int = 10

#: 聚合函数白名单（R5.4）——与 query_builder.AGGREGATE_WHITELIST 保持一致
AGGREGATE_WHITELIST: set[str] = {"count", "sum", "avg", "min", "max"}

#: 需要数值列的聚合函数（``count`` 适用任意类型，故不在此集合中）（R5.6）
NUMERIC_AGG_FUNCS: set[str] = {"sum", "avg", "min", "max"}


def _is_number(value: Any) -> bool:
    """判断值是否为数值型（int / float / Decimal，排除 bool）。

    ``bool`` 是 ``int`` 子类，但语义上不是数值列，故显式排除。``None`` 视为缺失
    值（不参与数值判定，交由调用方按「非 None 值须为数值」的规则处理）。
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, _dec.Decimal))


def _sort_key(value: Any) -> tuple[int, Any]:
    """构造对异构维度值稳定升序的排序键（避免 Python3 混合类型比较 TypeError）。

    排序分层：None < 数值 < 其它（按字符串）。同层内按自然序。
    """
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, float(int(value)))
    if isinstance(value, (int, float, _dec.Decimal)):
        return (1, float(value))
    return (2, str(value))


@dataclass
class Agg:
    """聚合定义：``{field, func, alias}``（design.md §Components 4）。

    - ``field``：被聚合的值字段名（结果行的键）；``count`` 允许 ``"*"`` / 空串表示计数全部行。
    - ``func``：聚合函数，∈ ``AGGREGATE_WHITELIST``。
    - ``alias``：输出列名；缺省为 ``{func}_{field}``。
    """

    field: str
    func: str
    alias: str | None = None

    @property
    def out_key(self) -> str:
        if self.alias:
            return self.alias
        raw = (self.field or "").strip()
        if raw in ("", "*"):
            safe_field = "all"
        else:
            safe_field = raw.replace(".", "_")
        return f"{self.func}_{safe_field}"

    @classmethod
    def coerce(cls, obj: "Agg | dict[str, Any]") -> "Agg":
        if isinstance(obj, Agg):
            return obj
        if isinstance(obj, dict):
            return cls(
                field=str(obj.get("field", "") or ""),
                func=str(obj.get("func", "") or "").lower(),
                alias=obj.get("alias") or None,
            )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_AGG_SPEC",
                "message": f"聚合定义须为 Agg 或 dict，收到 {type(obj).__name__}",
            },
        )


@dataclass
class GroupResult:
    """分组聚合结果。

    - ``rows``：分组后（或未分组的明细）结果行。
    - ``dims``：实际使用的分组维度（升序排序键顺序）。
    - ``agg_keys``：聚合输出列名清单。
    - ``grouped``：是否发生了分组（无维度时为 False，即明细结果集，R5.7）。
    """

    rows: list[dict[str, Any]]
    dims: list[str]
    agg_keys: list[str] = field(default_factory=list)
    grouped: bool = False


class GroupingEngine:
    """多维度分组聚合引擎（Python 层，业务视图入口）。"""

    max_dims: int = MAX_GROUP_DIMS
    aggregate_whitelist: set[str] = AGGREGATE_WHITELIST

    def group(
        self,
        rows: list[dict[str, Any]],
        dims: list[str],
        aggs: Iterable["Agg | dict[str, Any]"] | None = None,
        *,
        columns: Iterable[str] | None = None,
        valid_dims: Iterable[str] | None = None,
    ) -> GroupResult:
        """按 ``dims`` 对 ``rows`` 分组并应用 ``aggs`` 聚合。

        参数
        ----
        rows:
            待分组的结果行（``list[dict]``）。
        dims:
            分组维度名清单（0–10 个）；每个须为有效 addr_id 或结果集存在的列。
        aggs:
            聚合定义清单（``Agg`` 或 ``dict``）。无维度时忽略。
        columns:
            结果集的已知列集合（用于空结果集也能校验维度有效性）；缺省时从
            ``rows`` 的键推导。
        valid_dims:
            显式允许的维度集合（列 ∪ 有效 addr_id）；提供时优先于 ``columns``。

        返回
        ----
        ``GroupResult``。无维度 → ``grouped=False``、原样明细（R5.7）。

        错误
        ----
        - 维度无效 / 超 10 → ``HTTPException(400, INVALID_GROUP_DIM)``（R5.5）。
        - 非数值列施加 sum/avg/min/max → ``HTTPException(400, AGG_TYPE_MISMATCH)``（R5.6）。
        - 聚合函数不在白名单 → ``HTTPException(400, AGG_NOT_ALLOWED)``。
        """
        dims = list(dims or [])
        agg_list = [Agg.coerce(a) for a in (aggs or [])]

        # ── R5.7：无维度 → 明细结果集（不聚合，原样返回）──
        if not dims:
            return GroupResult(rows=list(rows), dims=[], agg_keys=[], grouped=False)

        # ── 已知列集合（用于维度有效性校验，空结果集也可校验）──
        if valid_dims is not None:
            known = set(valid_dims)
        elif columns is not None:
            known = set(columns)
        else:
            known = {k for r in rows for k in r}

        # ── R5.1 / R5.5：维度数量上限 + 有效性校验（保留条件、不执行）──
        self._validate_dims(dims, known)

        # ── 聚合函数白名单 + R5.6 数值类型校验（保留条件、不执行）──
        self._validate_aggs(agg_list, rows)

        # ── 分组聚合 ──
        grouped_rows = self._aggregate(rows, dims, agg_list)

        # ── R5.3：按维度组合升序排序 ──
        grouped_rows.sort(key=lambda r: tuple(_sort_key(r.get(d)) for d in dims))

        return GroupResult(
            rows=grouped_rows,
            dims=dims,
            agg_keys=[a.out_key for a in agg_list],
            grouped=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 校验
    # ─────────────────────────────────────────────────────────────────────────
    def _validate_dims(self, dims: list[str], known: set[str]) -> None:
        """R5.1 / R5.5：维度数量 ≤ 10 且每个维度有效，否则 INVALID_GROUP_DIM。"""
        invalid = [d for d in dims if d not in known]
        too_many = len(dims) > self.max_dims
        if too_many or invalid:
            detail: dict[str, Any] = {
                "error_code": "INVALID_GROUP_DIM",
                "invalid": invalid,
            }
            if too_many:
                detail["message"] = (
                    f"分组维度数 {len(dims)} 超过上限 {self.max_dims}"
                )
                detail["count"] = len(dims)
                detail["max_dims"] = self.max_dims
            else:
                detail["message"] = (
                    f"无效分组维度（非有效 addr_id 或结果集列）：{invalid}"
                )
            raise HTTPException(status_code=400, detail=detail)

    def _validate_aggs(self, aggs: list[Agg], rows: list[dict[str, Any]]) -> None:
        """聚合函数白名单 + R5.6 非数值列拒绝 sum/avg/min/max。"""
        for agg in aggs:
            if agg.func not in self.aggregate_whitelist:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "AGG_NOT_ALLOWED",
                        "message": f"聚合函数 '{agg.func}' 不在白名单中",
                        "allowed_aggs": sorted(self.aggregate_whitelist),
                    },
                )
            # count 适用任意类型；sum/avg/min/max 要求数值列
            if agg.func in NUMERIC_AGG_FUNCS:
                self._assert_numeric_field(agg, rows)

    @staticmethod
    def _assert_numeric_field(agg: Agg, rows: list[dict[str, Any]]) -> None:
        """R5.6：字段存在非 None 且非数值的值 → AGG_TYPE_MISMATCH。"""
        for row in rows:
            val = row.get(agg.field)
            if val is None:
                continue
            if not _is_number(val):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "AGG_TYPE_MISMATCH",
                        "message": (
                            f"聚合 '{agg.func}' 不能应用于非数值字段 '{agg.field}'"
                        ),
                        "field": agg.field,
                        "agg": agg.func,
                    },
                )

    # ─────────────────────────────────────────────────────────────────────────
    # 聚合执行
    # ─────────────────────────────────────────────────────────────────────────
    def _aggregate(
        self,
        rows: list[dict[str, Any]],
        dims: list[str],
        aggs: list[Agg],
    ) -> list[dict[str, Any]]:
        """按维度组合分组并对每组应用聚合。"""
        # 保持首次出现顺序的分组（排序在外层统一做）
        buckets: dict[tuple, list[dict[str, Any]]] = {}
        for row in rows:
            key = tuple(row.get(d) for d in dims)
            buckets.setdefault(key, []).append(row)

        out: list[dict[str, Any]] = []
        for key, group_rows in buckets.items():
            record: dict[str, Any] = {d: key[i] for i, d in enumerate(dims)}
            for agg in aggs:
                record[agg.out_key] = self._compute_agg(agg, group_rows)
            out.append(record)
        return out

    @staticmethod
    def _compute_agg(agg: Agg, group_rows: list[dict[str, Any]]) -> Any:
        """计算单个聚合值。"""
        func = agg.func

        # count：field 为空/'*' → 计数全部行；否则计数非 None 值
        if func == "count":
            if not agg.field or agg.field == "*":
                return len(group_rows)
            return sum(1 for r in group_rows if r.get(agg.field) is not None)

        # 数值聚合：仅取非 None 数值（类型校验已在 _validate_aggs 完成）
        raw = [r.get(agg.field) for r in group_rows]
        nums = [v for v in raw if v is not None]
        if not nums:
            # 全为 None → sum=0（与 SQL SUM 空组返 NULL 不同，此处置 0 以便下游数值处理）
            # avg/min/max 无值 → None
            return 0 if func == "sum" else None

        # 混合 float 与 Decimal 会抛 TypeError → 统一提升为 float
        if any(isinstance(v, float) for v in nums):
            nums = [float(v) for v in nums]

        if func == "sum":
            return sum(nums)
        if func == "avg":
            return sum(nums) / len(nums)
        if func == "min":
            return min(nums)
        if func == "max":
            return max(nums)

        # 不会到此（_validate_aggs 已拦截）
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "AGG_NOT_IMPLEMENTED",
                "message": f"聚合 {func} 未实现",
            },
        )
