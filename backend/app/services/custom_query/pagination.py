"""稳定分页（StablePagination）——排序解析、tie-breaker 追加与分页切片。

设计对应 `.kiro/specs/advanced-query-hardening-wiring-closure/design.md` §Components 5。

**存在理由**：改造前业务视图的分页是「声明了但从不存在」——
``custom_query.QueryRequest.offset`` 声明后全文件零使用，14 个取数器签名均为
``(db, pid, year, filters, limit)``、SQL 只拼 ``LIMIT :lim``，而前端两处都在传
``offset: 0`` ⇒ 用户永远只能看第 1 页；``limit = min(body.limit, 2000)`` 又被压进
SQL，使 ``total`` 恒等于截断后行数、无法判断是否还有下一页。构建器侧则是
``order_by`` 为空即无 ``ORDER BY`` 却直接 ``.offset()`` —— PG 对无序结果集的
offset 不保证稳定，翻页会重复/漏行。

本模块把「排序 → total → 切片」收敛成单一顺序，保证：
- ``total`` 反映**分组/透视之后**的行数（R4.1）；
- 用户排序之后**追加** tie-breaker 而非替换（R4.2）；
- 重复执行同一查询恒得到相同行顺序（R4.3）；
- 逐页并集 == 全集且互不重叠（R4.5）。

_Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Literal, Optional, Sequence

from fastapi import HTTPException

# ── 分页边界（与 custom_query.QueryRequest 的 pydantic ge/le 必须一致）──────────
#: 单页最小行数。契约：``limit=0`` → 422。
MIN_LIMIT = 1
#: 单页最大行数。契约：``limit=2001`` → 422（沿用 router 既有的 2000 上限语义）。
MAX_LIMIT = 2000

_DIRECTIONS = ("asc", "desc")

#: 各数据源的领域默认排序（无用户 sort 时使用）。
#: 字段若不存在于实际结果列中会被跳过——数据源的列集随 filters/group 变化，
#: 硬指定不存在的列会让默认排序整体失效，故按实际列集过滤而非报错。
DEFAULT_SORT_BY_SOURCE: dict[str, tuple[tuple[str, str], ...]] = {
    "report": (("row_code", "asc"),),
    "report_lines": (("applicable_standard", "asc"), ("report_type", "asc"), ("sort_order", "asc")),
    "trial_balance": (("standard_account_code", "asc"),),
    "tb_detail": (("account_code", "asc"),),
    "tb_summary": (("row_code", "asc"),),
    "account_balance": (("account_code", "asc"),),
    "ledger_entries": (("voucher_date", "desc"), ("voucher_no", "asc"), ("entry_seq", "asc")),
    "adjustment": (("adjustment_no", "asc"),),
    "adjustments": (("adjustment_no", "asc"),),
    "disclosure": (("section_id", "asc"),),
    "workhours": (("work_date", "desc"),),
    "workpaper": (("sheet_name", "asc"), ("cell_ref", "asc")),
}

#: 优先作为 tie-breaker 的候选列（按此顺序取第一个存在的）。
#: 之所以不只用 ``id``：分组/透视后的结果行不含 ``id``（如 ``{dept, sum_amount}``），
#: 此时退化为「全部列参与排序」以取得全序。
TIE_BREAKER_CANDIDATES = ("id", "addr_id", "account_code", "row_code", "voucher_no")


@dataclass(frozen=True)
class SortKey:
    """单个排序项。``is_tie_breaker`` 仅用于断言「追加而非替换」，不影响比较语义。"""

    field: str
    direction: Literal["asc", "desc"] = "asc"
    is_tie_breaker: bool = False


@dataclass(frozen=True)
class PagedRows:
    """分页结果：当前页行 + 分页前总行数。"""

    rows: list[dict]
    total: int
    limit: int
    offset: int


# ─────────────────────────────────────────────────────────────────────────────
# 校验
# ─────────────────────────────────────────────────────────────────────────────
def validate_pagination(limit: Any, offset: Any) -> tuple[int, int]:
    """校验并归一分页参数；越界 → 422（R4.6）。

    router 的 pydantic 层已有 ``ge/le``，这里是**第二道**：防止绕过 router 直接
    调用编排器（契约测试 ``test_orchestrator_422_for_limit_out_of_range`` /
    ``test_orchestrator_422_for_negative_offset`` 正是直调编排器）。
    """
    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_PAGINATION",
                "message": "limit / offset 必须为整数",
            },
        )

    if limit_i < MIN_LIMIT or limit_i > MAX_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_PAGINATION",
                "message": f"limit 必须在 {MIN_LIMIT}~{MAX_LIMIT} 之间，收到 {limit_i}",
                "limit": limit_i,
                "min": MIN_LIMIT,
                "max": MAX_LIMIT,
            },
        )
    if offset_i < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_PAGINATION",
                "message": f"offset 不能为负，收到 {offset_i}",
                "offset": offset_i,
            },
        )
    return limit_i, offset_i


def _reject_sort_field(field: str, available: Sequence[str]) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "error_code": "INVALID_SORT_FIELD",
            "message": f"排序字段 '{field}' 不在结果列中",
            "field": field,
            "available_fields": sorted(available),
        },
    )


def _reject_sort_direction(field: str, direction: Any) -> None:
    # error_code 必须含 ``INVALID_SORT_FIELD`` 前缀：契约测试
    # ``test_invalid_sort_direction_returns_422`` 断言的是子串包含。
    raise HTTPException(
        status_code=422,
        detail={
            "error_code": "INVALID_SORT_FIELD_DIRECTION",
            "message": f"排序字段 '{field}' 的方向 '{direction}' 非法，须为 asc / desc",
            "field": field,
            "direction": direction,
            "allowed": list(_DIRECTIONS),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 排序解析
# ─────────────────────────────────────────────────────────────────────────────
def collect_available_columns(
    rows: Iterable[dict], column_keys: Iterable[str] = ()
) -> set[str]:
    """结果可排序列集 = 列元数据 key ∪ 实际行键。

    两者取并集而非只用其一：分组/透视会重写列元数据，而某些 fetcher 只填 rows
    不填 columns；只取一侧会把合法排序字段误判为非法。
    """
    available = {str(k) for k in column_keys if k}
    for row in rows:
        if isinstance(row, dict):
            available.update(str(k) for k in row.keys())
    return available


def resolve_sort(
    source: Optional[str],
    user_sort: Sequence[dict] | None,
    available_columns: Iterable[str],
) -> list[SortKey]:
    """解析排序项：用户 sort → 领域默认 → **追加** tie-breaker（R4.2）。

    - 用户 sort 非法字段 / 非法方向 → 422，不静默丢弃（静默丢弃会让「排序没生效」
      表现为「数据顺序怪」，用户无从判断）。
    - 领域默认中不存在于当前列集的字段被跳过（不报错）。
    - tie-breaker 恒追加在末位，保证全序；已被前序排序项覆盖的列不重复追加。
    """
    available = {str(c) for c in available_columns}
    keys: list[SortKey] = []
    used: set[str] = set()

    for item in user_sort or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        if not field:
            continue
        if field not in available:
            _reject_sort_field(field, available)
        direction = item.get("direction", "asc")
        if not isinstance(direction, str) or direction.lower() not in _DIRECTIONS:
            _reject_sort_direction(field, direction)
        if field in used:
            continue
        keys.append(SortKey(field=field, direction=direction.lower()))  # type: ignore[arg-type]
        used.add(field)

    if not keys:
        for field, direction in DEFAULT_SORT_BY_SOURCE.get(source or "", ()):
            if field in available and field not in used:
                keys.append(SortKey(field=field, direction=direction))  # type: ignore[arg-type]
                used.add(field)

    keys.extend(_tie_breaker_keys(available, used))
    return keys


def _tie_breaker_keys(available: set[str], used: set[str]) -> list[SortKey]:
    """构造 tie-breaker：优先唯一键，否则退化为「全部剩余列」以取得全序。"""
    for candidate in TIE_BREAKER_CANDIDATES:
        if candidate in available:
            if candidate in used:
                return []  # 已参与排序，本身即 tie-breaker
            return [SortKey(field=candidate, direction="asc", is_tie_breaker=True)]

    # 无唯一键候选：把剩余列按名称排序后全部纳入，保证确定性全序。
    return [
        SortKey(field=field, direction="asc", is_tie_breaker=True)
        for field in sorted(available - used)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 排序与切片
# ─────────────────────────────────────────────────────────────────────────────
def _comparable(value: Any) -> tuple[int, Any]:
    """把任意单元格值映射为可跨类型比较的键。

    真实结果集里同一列可能混有 None / Decimal / str / date（JSONB 取数尤其如此），
    直接 ``sorted`` 会 ``TypeError``。这里按「类型档位 + 同档可比值」二元组排序：
    None < 数值 < 其他（字符串化）。
    """
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, float(value))
    if isinstance(value, (int, float)):
        return (1, float(value))
    if isinstance(value, Decimal):
        return (1, float(value))
    return (2, str(value))


def sort_rows(rows: list[dict], sort_keys: Sequence[SortKey]) -> list[dict]:
    """按 sort_keys 稳定排序（不修改入参）。

    从最低优先级键向最高优先级键依次排序，利用 Python 排序的稳定性实现多键
    混合升降序；一次性组合 key 无法表达「部分列 desc」。
    """
    ordered = list(rows)
    for key in reversed(list(sort_keys)):
        ordered.sort(
            key=lambda r, f=key.field: _comparable(r.get(f) if isinstance(r, dict) else None),
            reverse=(key.direction == "desc"),
        )
    return ordered


def apply_pagination(
    rows: list[dict],
    *,
    sort: Sequence[SortKey],
    limit: int,
    offset: int,
) -> PagedRows:
    """排序 → 计 total → 切片（R4.1 / R4.4 / R4.5）。

    ``total`` 在切片**之前**计算，故不受 ``offset`` 影响；``offset`` 超出 total 时
    自然得到空页而 ``total`` 保持真实值（契约
    ``test_offset_beyond_total_returns_empty_rows_total_unchanged``）。
    """
    ordered = sort_rows(rows, sort)
    total = len(ordered)
    page = ordered[offset : offset + limit] if offset < total else []
    return PagedRows(rows=page, total=total, limit=limit, offset=offset)


# ── 取数层硬上限（R4.8）────────────────────────────────────────────────────
#: 取数层单次最多拉取的行数。
#:
#: 改造前 router 把**展示用** ``limit`` 直接压进各取数器的 ``LIMIT :lim``
#: （``limit = min(body.limit, 2000)``），于是 ``total = len(rows)`` 恒等于截断后的
#: 行数 —— 前端拿到 ``total == limit`` 时无从判断「刚好这么多」还是「被截断了」。
#: 现在取数层按本上限取数、由 :func:`apply_pagination` 在其后切片，``total`` 因此
#: 在上限内是真实值；触达上限时由调用方追加 warning 明示结果可能不完整。
#:
#: 注意**不能**按 ``offset + limit`` 只取当前页所需：那样 ``total`` 又会退化为
#: 「取到的行数」，与 R4.1「total 反映聚合后真实行数」直接冲突。故取数层统一按本
#: 上限取数，由 :func:`apply_pagination` 在其后切片。
FETCH_HARD_CAP = 5000
