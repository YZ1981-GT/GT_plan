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

登记的 SQL 源：试算表、科目余额、序时账、底稿清单、工时、合并单位前缀（实施计划 B2），报表、报表行次、调整分录
（B5 任务 17 / 18；router 内的旧取数器随之删除）；JSON 内存源在 ``fetchers/``。

- 报表源（AQ-01）：结构 = 项目适用准则的行 ∪ 本项目独有的 ``project:{项目}`` 行（准则取报表生成用的
  ``ReportConfigService.resolve_applicable_standard``，覆盖行的结构仍取准则行，与 ``load_effective_report_configs``
  同口径），金额 LEFT JOIN 项目已生成的 ``financial_report``；改造前金额取自全库 0 行的 ``report_snapshot``。
- 报表行次（AQ-08）：只含准则行与本项目副本行，按行号排序；改造前按不存在的 ``sort_order`` 排序，恒 500。
- 调整分录（AQ-07）：按 PG 枚举小写值查询；改造前绑大写 ``'AJE'`` / ``'RCL'``（枚举里没有），恒 500。
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

from app.models.audit_platform_models import Adjustment, TbBalance, TbLedger, TrialBalance
from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig
from app.models.staff_models import WorkHour
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.dataset_query import get_active_dataset_id_or_none, get_active_filter
from app.services.report_config_service import ReportConfigService

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
    #: 来自 LEFT JOIN 的被连接一侧：没有匹配行时为空，排序按可空列处理（NULLS LAST）
    outer: bool = False
    #: 排序用的表达式（缺省 = ``expr``）：如报表类型显示与条件按文本、排序仍按枚举声明顺序
    sort_expr: Any = None

    @property
    def nullable(self) -> bool:
        return self.outer or bool(getattr(_base_column(self.expr), "nullable", True))

    @property
    def order_expr(self) -> Any:
        return self.expr if self.sort_expr is None else self.sort_expr


@dataclass(frozen=True)
class FilterKey:
    """旧 ``filters`` 字典允许的一个键（未登记即 400 ``UNKNOWN_FILTER_KEY``）。"""

    key: str
    column: str  # 对应 SourceColumn.key（显示列或隐藏列）
    op: FilterOp
    #: 取值归一（如调整类型 AJE / RCL → 枚举小写值）；取值非法时抛 400
    normalize: Callable[[Any], Any] | None = None


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
    #: 由本源口径谓词 / 提示自己消费的键（如报表类型、准则）：不生成通用谓词，取值在 ``base_where`` 里校验
    context_filters: tuple[str, ...] = ()
    #: 源键自带、覆盖请求同名键的筛选（如 adj_aje ⇒ 调整类型 aje）
    fixed_filters: tuple[tuple[str, Any], ...] = ()

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


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _invalid_filter(key: str, message: str, allowed: list[str]) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error_code": "INVALID_FILTER_VALUE", "message": message, "filter_key": key, "allowed": allowed,
    })


# ── 报表 / 报表行次（任务 17）──

#: 报表类型（financial_report_type 枚举的取值，顺序同枚举声明）
REPORT_TYPES: tuple[str, ...] = tuple(t.value for t in FinancialReportType)
#: 通用报表源（``report``）不带报表类型时按资产负债表（与旧取数器相同）
DEFAULT_REPORT_TYPE = "balance_sheet"
#: 报表配置的项目副本行写法（``applicable_standard = 'project:{项目 id}'``）
PROJECT_STANDARD_PREFIX = "project:"
REPORT_NOT_GENERATED_WARNING = "该项目尚未生成此报表，金额为空"
REPORT_STALE_WARNING = "报表数据已过期，请在报表页重新生成"

_RC = ReportConfig.__table__
_RC_STANDARD = _RC.alias("rc_standard")
_FR = FinancialReport.__table__


def _report_type(ctx: FetchContext) -> str:
    raw = ctx.filters.get("report_type")
    value = DEFAULT_REPORT_TYPE if _blank(raw) else str(raw).strip()
    if value not in REPORT_TYPES:
        raise _invalid_filter("report_type", f"报表类型「{value}」不存在，可用：{'、'.join(REPORT_TYPES)}",
                              list(REPORT_TYPES))
    return value


async def _report_standard(ctx: FetchContext) -> str:
    """本次报表结构用的准则：显式 ``filters.standard``（限平台准则）优先，否则同报表生成（项目模板类型 + 报表范围）。"""
    if "report_standard" not in ctx.memo:
        raw = ctx.filters.get("standard")
        if _blank(raw):
            standard = await ReportConfigService.resolve_applicable_standard(ctx.db, ctx.project_id)
        else:
            standard = str(raw).strip()
            allowed = sorted(ReportConfigService.VALID_STANDARDS)
            if standard not in allowed:
                raise _invalid_filter("standard", f"报表准则「{standard}」不存在，可用：{'、'.join(allowed)}", allowed)
        ctx.memo["report_standard"] = standard
    return ctx.memo["report_standard"]


def _report_from(ctx: FetchContext) -> Any:
    # 金额 = 项目已生成的报表结果（同项目年度、同类型行次、未删）；financial_report 在这组键上唯一，不会放大行数
    return _RC.outerjoin(_FR, sa.and_(
        _FR.c.project_id == ctx.project_id,
        _FR.c.year == ctx.year,
        _FR.c.report_type == _RC.c.report_type,
        _FR.c.row_code == _RC.c.row_code,
        _FR.c.is_deleted == sa.false(),
    ))


async def _report_where(ctx: FetchContext) -> list[ColumnElement]:
    report_type = _report_type(ctx)
    standard = await _report_standard(ctx)
    # 本项目独有行 = 项目副本行中准则下没有同（报表类型, 行次码）的行；覆盖行的结构仍取准则行（行名 / 缩进 / 合计），
    # 与报表生成用的 load_effective_report_configs 同口径
    shadowed = sa.exists().where(
        _RC_STANDARD.c.applicable_standard == standard,
        _RC_STANDARD.c.report_type == _RC.c.report_type,
        _RC_STANDARD.c.row_code == _RC.c.row_code,
        _RC_STANDARD.c.is_deleted == sa.false(),
    )
    own_rows = sa.and_(_RC.c.applicable_standard == f"{PROJECT_STANDARD_PREFIX}{ctx.project_id}", ~shadowed)
    return [
        _RC.c.is_deleted == sa.false(),
        _RC.c.report_type == report_type,
        sa.or_(_RC.c.applicable_standard == standard, own_rows),
    ]


async def _report_warn(ctx: FetchContext) -> list[str]:
    total, stale = (await ctx.db.execute(
        sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(sa.case((_FR.c.is_stale == sa.true(), 1), else_=0)), 0))
        .where(_FR.c.project_id == ctx.project_id, _FR.c.year == ctx.year,
               _FR.c.report_type == _report_type(ctx), _FR.c.is_deleted == sa.false())
    )).one()
    if not total:
        return [REPORT_NOT_GENERATED_WARNING]
    return [REPORT_STALE_WARNING] if stale else []


async def _report_lines_where(ctx: FetchContext) -> list[ColumnElement]:
    # 准则行 + 本项目副本行（他项目副本行不可见）
    return [
        _RC.c.is_deleted == sa.false(),
        sa.or_(_RC.c.applicable_standard.notlike(f"{PROJECT_STANDARD_PREFIX}%"),
               _RC.c.applicable_standard == f"{PROJECT_STANDARD_PREFIX}{ctx.project_id}"),
    ]


# ── 调整分录（任务 18）──

#: 调整类型取值（大小写不敏感）→ PG 枚举 ``adjustment_type`` 的值；RCL 是旧叶子的写法，即重分类调整（rje）
_ADJUSTMENT_TYPE_VALUES = {"aje": "aje", "rje": "rje", "rcl": "rje"}


def normalize_adjustment_type(value: Any) -> str:
    """调整类型归一：AJE → aje、RJE / RCL → rje；其余（含 cf）400。"""
    key = str(value).strip().lower()
    if key not in _ADJUSTMENT_TYPE_VALUES:
        raise _invalid_filter("adjustment_type", f"调整类型「{value}」不存在，可用：AJE（审计调整）、RJE（重分类调整）",
                              ["AJE", "RJE"])
    return _ADJUSTMENT_TYPE_VALUES[key]


async def _adjustment_where(ctx: FetchContext) -> list[ColumnElement]:
    a = Adjustment.__table__
    clauses: list[ColumnElement] = [a.c.project_id == ctx.project_id, a.c.year == ctx.year, a.c.is_deleted == sa.false()]
    if ctx.company_code:
        clauses.append(a.c.company_code == ctx.company_code)
    return clauses


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

REPORT = SourceSpec(
    key="report",
    label="报表",
    from_clause=_report_from,
    columns=(
        _c(_RC, "row_code", "text"),
        _c(_RC, "row_name", "text"),
        SourceColumn("current_period_amount", _FR.c.current_period_amount, "number", outer=True),
        SourceColumn("prior_period_amount", _FR.c.prior_period_amount, "number", outer=True),
        # 响应键沿用旧取数器（indent / is_total），前端标签与编码类列判定按它
        SourceColumn("indent", _RC.c.indent_level, "number"),
        SourceColumn("is_total", _RC.c.is_total_row, "bool"),
    ),
    hidden=(
        _id(_RC),
        _c(_RC, "row_number", "number", conditionable=False),
        SourceColumn("is_stale", _FR.c.is_stale, "bool", conditionable=False, outer=True),
        SourceColumn("blank_reason", _FR.c.blank_reason, "text", conditionable=False, outer=True),
    ),
    base_where=_report_where,
    filter_keys=(),
    default_sort=(("row_number", "asc"), ("row_code", "asc")),
    unique_key="id",
    warn=_report_warn,
    context_filters=("report_type", "standard"),
)

REPORT_LINES = SourceSpec(
    key="report_lines",
    label="报表行次配置",
    from_clause=lambda ctx: _RC,
    columns=(
        _c(_RC, "row_code", "text"),
        _c(_RC, "row_name", "text"),
        # 显示与条件按文本（非法值是查不到，不是 PG 报错 500），排序仍按枚举声明顺序（资产负债表、利润表……）
        SourceColumn("report_type", sa.cast(_RC.c.report_type, sa.String), "text", sort_expr=_RC.c.report_type),
        _c(_RC, "applicable_standard", "text"),
        _c(_RC, "indent_level", "number"),
        _c(_RC, "is_total_row", "bool"),
        _c(_RC, "formula", "text"),
        _c(_RC, "row_number", "number"),
    ),
    hidden=(_id(_RC),),
    base_where=_report_lines_where,
    filter_keys=(
        FilterKey("report_type", "report_type", "eq"),
        FilterKey("applicable_standard", "applicable_standard", "eq"),
        FilterKey("has_formula", "formula", "nonempty"),
        FilterKey("row_name", "row_name", "like"),
    ),
    default_sort=(("applicable_standard", "asc"), ("report_type", "asc"), ("row_number", "asc")),
    unique_key="id",
)

_ADJ = Adjustment.__table__
#: 枚举列按文本读写比较：PG 枚举有 cf、ORM 枚举没有，按 ORM 类型读会 LookupError
_ADJ_TYPE = SourceColumn("adjustment_type", sa.cast(_ADJ.c.adjustment_type, sa.String), "text")
_ADJ_COLUMNS = (
    _c(_ADJ, "adjustment_no", "text"),
    _c(_ADJ, "account_code", "text"),
    _c(_ADJ, "account_name", "text"),
    _c(_ADJ, "debit_amount", "number"),
    _c(_ADJ, "credit_amount", "number"),
    _c(_ADJ, "description", "text"),
    SourceColumn("review_status", sa.cast(_ADJ.c.review_status, sa.String), "text"),
)
_ADJ_HIDDEN = (
    _id(_ADJ),
    _c(_ADJ, "entry_group_id", "text", conditionable=False),  # 下钻到调整分录页按分录组
    _c(_ADJ, "company_code", "text", conditionable=False),
)
_ADJ_FILTERS = (
    FilterKey("adjustment_type", "adjustment_type", "eq", normalize=normalize_adjustment_type),
    FilterKey("account_name", "account_name", "like"),
    FilterKey("review_status", "review_status", "eq"),
    FilterKey("company_code", "company_code", "eq"),
)

ADJUSTMENT = SourceSpec(
    key="adjustment",
    label="调整分录（全部类型）",
    from_clause=lambda ctx: _ADJ,
    columns=(_ADJ_COLUMNS[0], _ADJ_TYPE, *_ADJ_COLUMNS[1:]),
    hidden=_ADJ_HIDDEN,
    base_where=_adjustment_where,
    filter_keys=_ADJ_FILTERS,
    default_sort=(("adjustment_no", "asc"),),
    unique_key="id",
)


def _typed_adjustment(key: str, label: str, adjustment_type: str) -> SourceSpec:
    """单一类型的调整分录源：类型列不显示（随行返回），类型由源键固定、覆盖请求里的同名键。"""
    return SourceSpec(
        key=key,
        label=label,
        from_clause=lambda ctx: _ADJ,
        columns=_ADJ_COLUMNS,
        hidden=(*_ADJ_HIDDEN, _ADJ_TYPE),
        base_where=_adjustment_where,
        filter_keys=_ADJ_FILTERS,
        default_sort=(("adjustment_no", "asc"),),
        unique_key="id",
        fixed_filters=(("adjustment_type", adjustment_type),),
    )


ADJUSTMENT_AJE = _typed_adjustment("adj_aje", "审计调整分录(AJE)", "aje")
ADJUSTMENT_RJE = _typed_adjustment("adj_rje", "重分类调整分录(RJE)", "rje")

#: 注册表：源键 → 定义（别名见 SOURCE_ALIASES；``report_{类型}`` 前缀见 resolve_source）
SOURCE_REGISTRY: dict[str, SourceSpec] = {
    spec.key: spec for spec in (TRIAL_BALANCE, ACCOUNT_BALANCE, LEDGER_ENTRIES, WORKPAPER, WORKHOURS, REPORT,
                                REPORT_LINES, ADJUSTMENT, ADJUSTMENT_AJE, ADJUSTMENT_RJE)
}
#: 别名 → 源键（tb_detail 是指标树叶子键；adj_rcl 是「重分类调整」旧叶子键）
SOURCE_ALIASES: dict[str, str] = {"tb_detail": "trial_balance", "adj_rcl": "adj_rje"}
#: ``consol_unit:{company_code}:{kind}`` 中由本注册表承担的 kind（单位下的「调整分录」= 该单位全部类型）
CONSOL_UNIT_KINDS: dict[str, str] = {
    "account_balance": "account_balance",
    "ledger_entries": "ledger_entries",
    "tb_detail": "trial_balance",
    "adjustment": "adjustment",
}
#: 报表源的类型前缀：``report_{类型}`` ⇒ 报表源 + 固定报表类型
REPORT_SOURCE_PREFIX = "report_"

# ─── 内存源（fetchers/）────────────────────────────────────────────────────────

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


@dataclass(frozen=True)
class ResolvedSource:
    """源键解析结果：二者恰有其一（SQL 定义 / JSON 取数器）。"""

    source: str
    spec: SourceSpec | None = None
    json_fetcher: tuple[str, str] | None = None
    fixed_filters: Mapping[str, Any] = field(default_factory=dict)
    company_code: str | None = None


def _sql_source(source: str, spec: SourceSpec, *, company_code: str | None = None, **extra: Any) -> ResolvedSource:
    return ResolvedSource(source, spec=spec, fixed_filters={**dict(spec.fixed_filters), **extra},
                          company_code=company_code)


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
            return _sql_source(key, SOURCE_REGISTRY[CONSOL_UNIT_KINDS[kind]], company_code=company_code)
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
        return _sql_source(key, WORKPAPER, **fixed)

    if key == "workpaper" and merged.get("wp_code") and merged.get("cell_range"):
        return ResolvedSource(key, json_fetcher=WORKPAPER_CELLS)

    canonical = SOURCE_ALIASES.get(key, key)
    if canonical in SOURCE_REGISTRY:
        return _sql_source(key, SOURCE_REGISTRY[canonical])
    if key in JSON_SOURCES:
        return ResolvedSource(key, json_fetcher=JSON_SOURCES[key])
    for prefix, target in JSON_PREFIXES:
        if key.startswith(prefix):
            return ResolvedSource(key, json_fetcher=target)
    if key.startswith(REPORT_SOURCE_PREFIX) and key[len(REPORT_SOURCE_PREFIX):] in REPORT_TYPES:
        # 报表叶子：源键决定报表类型（改造前后端只认 filters.report_type，页面版不带时一律当资产负债表）
        return _sql_source(key, REPORT, report_type=key[len(REPORT_SOURCE_PREFIX):])
    raise unknown_source(key)


async def ref_context(ctx: FetchContext) -> dict[str, Any]:
    """注册表源响应的 ``meta.ref_context``：前端按它校验公式引用（ADR-AQL-18）。"""
    memo = ctx.memo.get("template_type")
    if memo is None:
        project = await ctx.db.get(Project, ctx.project_id)
        memo = "listed" if project is not None and project.template_type == "listed" else "soe"
        ctx.memo["template_type"] = memo
    return {"template_type": memo, "year": ctx.year}
