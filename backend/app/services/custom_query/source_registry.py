"""业务视图 SQL 源注册表（advanced-query-linkage-closure ADR-AQL-03 / 06，design §3.1）。

**存在理由（AQ-02 / AQ-03 / AQ-13 / AQ-26）**：改造前业务视图由 router 内 14 个文本 SQL 取数器承担，
取数层一律 ``LIMIT 5000``，编排器再在这 ≤5,000 行样本上内存排序、分组、计 total、切片——和平药房序时账
（114 万行）的 total 恒为 5,000、借方降序首行是样本里的最大值而不是全量最大值；四表只按 ``is_deleted``
过滤、不经生效数据集（宜宾临港店科目余额多出一倍）；``filters`` 只认取数器写死的几个键、``columns``
无人消费，其余条件被静默忽略。

本模块把每个 SQL 源声明成一条 :class:`SourceSpec`（显示列 / 隐藏列 / 旧筛选键 / 默认排序 / 唯一键 / 口径谓词），
COUNT、ORDER BY、LIMIT / OFFSET 与条件全部交给 ``paged_fetch`` 在数据库内执行：

- 四表源的口径谓词只经平台唯一入口 ``dataset_query.get_active_filter(strict=True)``——查生效数据集失败原样上抛
  （500 + 追踪号），不退化为「不按数据集过滤」；
- 默认排序只由本注册表定义（``pagination.DEFAULT_SORT_BY_SOURCE`` 不再登记 SQL 源），末项恒追加唯一键；
- 未登记的筛选键 / 条件字段 / 列 → 400（``paged_fetch``）。

本批（实施计划 B2）登记试算表、科目余额、序时账、底稿清单、工时与合并单位前缀；报表、报表行次、调整分录
三个源仍由 router 内取数器承担（任务 17 / 18 切到本注册表后删除），JSON 内存源在 ``fetchers/``。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import Cast, ColumnElement, Label

from app.models.audit_platform_models import TbBalance, TbLedger, TrialBalance
from app.models.core import Project
from app.models.staff_models import WorkHour
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.dataset_query import get_active_dataset_id_or_none, get_active_filter

Dtype = Literal["number", "text", "date", "bool"]
#: 旧筛选键的谓词形态；``code_family`` = 编码精确或其子编码（``E1`` 带出 ``E1-1``），即底稿树叶子的口径
FilterOp = Literal["eq", "like", "prefix", "gte", "lte", "nonempty", "code_family"]

#: 四表无生效数据集时的提示（R1.3）
NO_ACTIVE_DATASET_WARNING = "该项目年度没有生效数据集，按未删除行返回"


def _base_column(expr: Any) -> Any:
    """剥掉 ``Label`` / ``Cast`` 取到底层列，用于读取列定义的可空性。"""
    while True:
        if isinstance(expr, Label):
            expr = expr.element
        elif isinstance(expr, Cast):
            expr = expr.clause
        else:
            return expr


@dataclass(frozen=True)
class SourceColumn:
    """源的一列：响应列键（英文契约）+ 列表达式（取自 ORM ``__table__``）。

    可空性由列定义读出（:attr:`nullable`）：排序时只对可空列加 ``NULLS LAST``——非空列加了语义相同却会让
    索引用不上（ADR-AQL-06 N1 预案②）。
    """

    key: str
    expr: Any
    dtype: Dtype
    conditionable: bool = True
    sortable: bool = True

    @property
    def nullable(self) -> bool:
        return bool(getattr(_base_column(self.expr), "nullable", True))


@dataclass(frozen=True)
class FilterKey:
    """旧 ``filters`` 字典允许的一个键（未登记即 400 ``UNKNOWN_FILTER_KEY``）。"""

    key: str
    column: str  # 对应 SourceColumn.key（显示列或隐藏列）
    op: FilterOp


@dataclass
class FetchContext:
    """一次取数的上下文；``cycle`` 由任务 23（循环范围）接入，本批恒为 None。"""

    db: AsyncSession
    user: Any
    project_id: uuid.UUID
    year: int
    filters: dict[str, Any]
    company_code: str | None = None
    cycle: Any = None
    #: 同一请求内的记忆（如生效数据集 id），避免谓词与 warnings 重复查库
    memo: dict[str, Any] = field(default_factory=dict)


WhereBuilder = Callable[[FetchContext], Awaitable[list[ColumnElement]]]
WarnBuilder = Callable[[FetchContext], Awaitable[list[str]]]


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str  # 指标树叶子中文名，也用于 400 提示
    from_clause: Callable[[FetchContext], Any]
    columns: tuple[SourceColumn, ...]  # 显示列，顺序即默认列序
    hidden: tuple[SourceColumn, ...]  # 下钻 / 排序 / 唯一键：随行返回，不进 columns
    base_where: WhereBuilder
    filter_keys: tuple[FilterKey, ...]
    default_sort: tuple[tuple[str, str], ...]
    unique_key: str  # hidden 中的唯一列
    required_filters: tuple[frozenset[str], ...] = ()
    tree_scope: Literal["any", "standalone", "consolidated"] = "any"
    warn: WarnBuilder | None = None
    #: 只回显、不筛选的键（如底稿叶子 ``workpaper:{code}|{sheet}`` 的 sheet 名），以隐藏列随行返回
    echo_filters: tuple[str, ...] = ()

    def column(self, key: str) -> SourceColumn | None:
        for col in (*self.columns, *self.hidden):
            if col.key == key:
                return col
        return None

    @property
    def display_keys(self) -> list[str]:
        return [c.key for c in self.columns]


# ─── 口径谓词 ────────────────────────────────────────────────────────────────


async def _active_dataset_id(ctx: FetchContext) -> uuid.UUID | None:
    """本请求内只查一次生效数据集 id（warnings 用；谓词仍经 get_active_filter）。"""
    if "active_dataset_id" not in ctx.memo:
        ctx.memo["active_dataset_id"] = await get_active_dataset_id_or_none(ctx.db, ctx.project_id, ctx.year)
    return ctx.memo["active_dataset_id"]


def _four_table_where(table: sa.Table) -> WhereBuilder:
    async def build(ctx: FetchContext) -> list[ColumnElement]:
        # 平台四表读路径唯一入口；strict=True：查生效数据集失败原样上抛，不 rollback、不退化（R1.1）
        clauses: list[ColumnElement] = [
            await get_active_filter(ctx.db, table, ctx.project_id, ctx.year, strict=True)
        ]
        if ctx.company_code:
            clauses.append(table.c.company_code == ctx.company_code)
        return clauses

    return build


async def _warn_no_active_dataset(ctx: FetchContext) -> list[str]:
    return [] if await _active_dataset_id(ctx) is not None else [NO_ACTIVE_DATASET_WARNING]


async def _trial_balance_where(ctx: FetchContext) -> list[ColumnElement]:
    t = TrialBalance.__table__
    clauses: list[ColumnElement] = [t.c.project_id == ctx.project_id, t.c.year == ctx.year, t.c.is_deleted == sa.false()]
    if ctx.company_code:
        clauses.append(t.c.company_code == ctx.company_code)
    return clauses


async def _workpaper_where(ctx: FetchContext) -> list[ColumnElement]:
    w = WorkingPaper.__table__
    return [w.c.project_id == ctx.project_id, w.c.is_deleted == sa.false()]


async def _workhours_where(ctx: FetchContext) -> list[ColumnElement]:
    h = WorkHour.__table__
    return [h.c.project_id == ctx.project_id, sa.extract("year", h.c.work_date) == ctx.year, h.c.is_deleted == sa.false()]


# ─── 源定义 ──────────────────────────────────────────────────────────────────

_TB = TrialBalance.__table__
_BAL = TbBalance.__table__
_LED = TbLedger.__table__
_WP = WorkingPaper.__table__
_WI = WpIndex.__table__
_WH = WorkHour.__table__


def _c(table: sa.Table, name: str, dtype: Dtype, *, key: str | None = None, **kw: Any) -> SourceColumn:
    return SourceColumn(key or name, table.c[name], dtype, **kw)


def _id(table: sa.Table) -> SourceColumn:
    return SourceColumn("id", table.c.id, "text", conditionable=False)


TRIAL_BALANCE = SourceSpec(
    key="trial_balance",
    label="试算平衡表（科目）",
    from_clause=lambda ctx: _TB,
    columns=(
        _c(_TB, "standard_account_code", "text"),
        _c(_TB, "account_name", "text"),
        _c(_TB, "opening_balance", "number"),
        _c(_TB, "unadjusted_amount", "number"),
        _c(_TB, "aje_adjustment", "number"),
        _c(_TB, "audited_amount", "number"),
    ),
    hidden=(_id(_TB), _c(_TB, "company_code", "text", conditionable=False)),
    base_where=_trial_balance_where,
    filter_keys=(FilterKey("account_name", "account_name", "like"), FilterKey("company_code", "company_code", "eq")),
    default_sort=(("standard_account_code", "asc"),),
    unique_key="id",
)

ACCOUNT_BALANCE = SourceSpec(
    key="account_balance",
    label="科目余额表",
    from_clause=lambda ctx: _BAL,
    columns=(
        _c(_BAL, "account_code", "text"),
        _c(_BAL, "account_name", "text"),
        _c(_BAL, "opening_balance", "number"),
        _c(_BAL, "closing_balance", "number"),
        _c(_BAL, "debit_amount", "number"),
        _c(_BAL, "credit_amount", "number"),
        _c(_BAL, "currency_code", "text"),
    ),
    hidden=(_id(_BAL), _c(_BAL, "company_code", "text", conditionable=False)),
    base_where=_four_table_where(_BAL),
    filter_keys=(
        FilterKey("account_code", "account_code", "prefix"),
        FilterKey("account_name", "account_name", "like"),
        FilterKey("company_code", "company_code", "eq"),
    ),
    default_sort=(("account_code", "asc"),),
    unique_key="id",
    warn=_warn_no_active_dataset,
)

LEDGER_ENTRIES = SourceSpec(
    key="ledger_entries",
    label="序时账明细",
    from_clause=lambda ctx: _LED,
    columns=(
        _c(_LED, "voucher_date", "date"),
        _c(_LED, "voucher_no", "text"),
        _c(_LED, "account_code", "text"),
        _c(_LED, "account_name", "text"),
        _c(_LED, "debit_amount", "number"),
        _c(_LED, "credit_amount", "number"),
        _c(_LED, "summary", "text"),
    ),
    hidden=(
        _id(_LED),
        _c(_LED, "entry_seq", "number", conditionable=False),
        _c(_LED, "accounting_period", "number", conditionable=False),
        _c(_LED, "company_code", "text", conditionable=False),
    ),
    base_where=_four_table_where(_LED),
    filter_keys=(
        FilterKey("account_code", "account_code", "prefix"),
        FilterKey("voucher_no", "voucher_no", "like"),
        FilterKey("summary", "summary", "like"),
        FilterKey("date_from", "voucher_date", "gte"),
        FilterKey("date_to", "voucher_date", "lte"),
        FilterKey("company_code", "company_code", "eq"),
    ),
    default_sort=(("voucher_date", "desc"), ("voucher_no", "asc"), ("entry_seq", "asc")),
    unique_key="id",
    warn=_warn_no_active_dataset,
)

WORKPAPER = SourceSpec(
    key="workpaper",
    label="底稿清单",
    from_clause=lambda ctx: _WP.join(_WI, _WI.c.id == _WP.c.wp_index_id),
    columns=(
        _c(_WI, "wp_code", "text"),
        _c(_WI, "wp_name", "text"),
        _c(_WI, "audit_cycle", "text"),
        # 枚举列按文本比较：用户值不合枚举时是「查不到」而不是 PG 报错 500；like 也能用
        SourceColumn("status", sa.cast(_WP.c.status, sa.String), "text"),
        SourceColumn("review_status", sa.cast(_WP.c.review_status, sa.String), "text"),
        _c(_WP, "assigned_to", "text", conditionable=False),
    ),
    hidden=(SourceColumn("id", _WP.c.id, "text", conditionable=False),),
    base_where=_workpaper_where,
    filter_keys=(
        FilterKey("wp_code", "wp_code", "code_family"),
        FilterKey("status", "status", "eq"),
        FilterKey("review_status", "review_status", "eq"),
        FilterKey("cycle", "audit_cycle", "eq"),
    ),
    default_sort=(("wp_code", "asc"),),
    unique_key="id",
    echo_filters=("sheet_name",),
)

WORKHOURS = SourceSpec(
    key="workhours",
    label="工时记录",
    from_clause=lambda ctx: _WH,
    columns=(
        _c(_WH, "work_date", "date"),
        _c(_WH, "hours", "number"),
        _c(_WH, "description", "text"),
        _c(_WH, "status", "text"),
        _c(_WH, "staff_id", "text"),
    ),
    hidden=(_id(_WH),),
    base_where=_workhours_where,
    filter_keys=(
        FilterKey("staff_id", "staff_id", "eq"),
        FilterKey("status", "status", "eq"),
        FilterKey("date_from", "work_date", "gte"),
        FilterKey("date_to", "work_date", "lte"),
    ),
    default_sort=(("work_date", "desc"),),
    unique_key="id",
)

#: 注册表：源键 → 定义（别名见 SOURCE_ALIASES）
SOURCE_REGISTRY: dict[str, SourceSpec] = {
    spec.key: spec for spec in (TRIAL_BALANCE, ACCOUNT_BALANCE, LEDGER_ENTRIES, WORKPAPER, WORKHOURS)
}
#: 别名 → 源键（tb_detail 是指标树叶子键）
SOURCE_ALIASES: dict[str, str] = {"tb_detail": "trial_balance"}
#: ``consol_unit:{company_code}:{kind}`` 中由本注册表承担的 kind
CONSOL_UNIT_KINDS: dict[str, str] = {
    "account_balance": "account_balance",
    "ledger_entries": "ledger_entries",
    "tb_detail": "trial_balance",
}

# ─── 内存源（fetchers/）与暂留 router 的取数器 ────────────────────────────────

#: JSON 内存源：源键 → (fetchers 子模块, 函数名)。行序即取数顺序（_row_index），不支持 conditions。
JSON_SOURCES: dict[str, tuple[str, str]] = {
    "tb_summary": ("worksheet", "_query_tb_summary"),
    "worksheet": ("worksheet", "_query_worksheet"),
    "disclosure": ("disclosure", "_query_disclosure"),
    "disclosure_note": ("disclosure", "_query_disclosure"),
}
JSON_PREFIXES: tuple[tuple[str, tuple[str, str]], ...] = (("ws_", ("worksheet", "_query_worksheet")),)
#: 底稿单元格区域（签名不同：``(db, pid, filters)``）
WORKPAPER_CELLS: tuple[str, str] = ("workpaper_cells", "_query_workpaper_cell_range")

#: 暂留 router 的取数器（任务 17 / 18 切到注册表后删除；在此之前它们不支持 conditions）
LEGACY_SOURCES: dict[str, str] = {
    "report": "_query_report",
    "adjustment": "_query_adjustments",
    "report_lines": "_query_report_lines",
}
LEGACY_PREFIXES: tuple[tuple[str, str], ...] = (("report_", "_query_report"), ("adj_", "_query_adjustments"))


@dataclass(frozen=True)
class ResolvedSource:
    """源键解析结果：三者恰有其一（SQL 定义 / JSON 取数器 / 暂留 router 的取数器）。"""

    source: str
    spec: SourceSpec | None = None
    json_fetcher: tuple[str, str] | None = None
    legacy_fetcher: str | None = None
    fixed_filters: Mapping[str, Any] = field(default_factory=dict)
    company_code: str | None = None


def unknown_source(source: str) -> HTTPException:
    """未知数据源 → 400（既有错误码 UNKNOWN_SOURCE，不再 200 + error）。"""
    return HTTPException(
        status_code=400,
        detail={"error_code": "UNKNOWN_SOURCE", "message": f"未知数据源: {source}", "source": source},
    )


def resolve_source(source: str, filters: Mapping[str, Any] | None = None) -> ResolvedSource:
    """把请求里的源键解析为一个取数实现（别名、前缀、合并单位、底稿叶子、附注叶子）。

    ``filters`` 只用于判定底稿叶子是否带单元格区域（带 ``cell_range`` 走选区取数，否则走底稿清单）。
    """
    key = (source or "").strip()
    if not key:
        raise unknown_source(key)
    merged = dict(filters or {})

    if key.startswith("disclosure_note:"):
        return ResolvedSource(key, json_fetcher=JSON_SOURCES["disclosure_note"],
                              fixed_filters={"section_id": key.split(":", 1)[1]})

    if key.startswith("consol_unit:"):
        parts = key.split(":", 2)
        if len(parts) != 3 or not parts[1]:
            raise unknown_source(key)
        _, company_code, kind = parts
        if kind in CONSOL_UNIT_KINDS:
            return ResolvedSource(key, spec=SOURCE_REGISTRY[CONSOL_UNIT_KINDS[kind]], company_code=company_code)
        if kind == "adjustment":  # 任务 18 切到注册表（并改小写枚举）
            return ResolvedSource(key, legacy_fetcher="_query_adjustments",
                                  fixed_filters={"company_code": company_code, "adjustment_type": "AJE"})
        raise unknown_source(key)

    if key.startswith("workpaper:"):
        tail = key.split(":", 1)[1]
        wp_code, _, sheet_name = tail.partition("|")
        if not wp_code:
            raise unknown_source(key)
        fixed: dict[str, Any] = {"wp_code": wp_code}
        if sheet_name:
            fixed["sheet_name"] = sheet_name
        if merged.get("cell_range"):
            return ResolvedSource(key, json_fetcher=WORKPAPER_CELLS, fixed_filters=fixed)
        return ResolvedSource(key, spec=WORKPAPER, fixed_filters=fixed)

    if key == "workpaper" and merged.get("wp_code") and merged.get("cell_range"):
        return ResolvedSource(key, json_fetcher=WORKPAPER_CELLS)

    canonical = SOURCE_ALIASES.get(key, key)
    if canonical in SOURCE_REGISTRY:
        return ResolvedSource(key, spec=SOURCE_REGISTRY[canonical])
    if key in JSON_SOURCES:
        return ResolvedSource(key, json_fetcher=JSON_SOURCES[key])
    if key in LEGACY_SOURCES:
        return ResolvedSource(key, legacy_fetcher=LEGACY_SOURCES[key])
    for prefix, target in JSON_PREFIXES:
        if key.startswith(prefix):
            return ResolvedSource(key, json_fetcher=target)
    for prefix, name in LEGACY_PREFIXES:
        if key.startswith(prefix):
            return ResolvedSource(key, legacy_fetcher=name)
    raise unknown_source(key)


async def ref_context(ctx: FetchContext) -> dict[str, Any]:
    """注册表源响应的 ``meta.ref_context``：前端按它校验公式引用（ADR-AQL-18）。"""
    memo = ctx.memo.get("template_type")
    if memo is None:
        project = await ctx.db.get(Project, ctx.project_id)
        memo = "listed" if project is not None and project.template_type == "listed" else "soe"
        ctx.memo["template_type"] = memo
    return {"template_type": memo, "year": ctx.year}
