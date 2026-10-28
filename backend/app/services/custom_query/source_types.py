"""业务视图 SQL 源的声明类型（advanced-query-linkage-closure design §3.1）。

从 ``source_registry`` 拆出（B5 起该模块登记的源已逾十个，类型与源定义同处一个文件会超出 800 行门）：这里只有
「一个源怎么声明」——列、旧筛选键、取数上下文、源定义，以及「本次请求是否已按某列收窄」的判断；具体登记哪些源、
各源的口径谓词与源键解析仍在 ``source_registry``（并从那里再导出这些名字，既有导入不变）。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import Cast, ColumnElement, Label

Dtype = Literal["number", "text", "date", "bool"]
#: 旧筛选键的谓词形态；``code_family`` = 编码精确或其子编码（``E1`` 带出 ``E1-1``），即底稿树叶子的口径
FilterOp = Literal["eq", "like", "prefix", "gte", "lte", "nonempty", "code_family"]


def _base_column(expr: Any) -> Any:
    """剥掉 ``Label`` / ``Cast`` 取到底层列，用于读取列定义的可空性。"""
    while True:
        if isinstance(expr, Label):
            expr = expr.element
        elif isinstance(expr, Cast):
            expr = expr.clause
        else:
            return expr


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


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
    """一次取数的上下文。

    ``cycle``：请求级 ``cycle_scope.CycleScopeCache``（任务 23，R3.8）—— 业务视图入口按当前用户带上，试算表 / 调整分录
    的口径谓词据此按循环过滤；内部调用不带用户时为 None（不限）。
    """

    db: AsyncSession
    user: Any
    project_id: uuid.UUID
    year: int
    filters: dict[str, Any]
    company_code: str | None = None
    cycle: Any = None
    #: 同一请求内的记忆（如生效数据集 id），避免谓词与 warnings 重复查库
    memo: dict[str, Any] = field(default_factory=dict)
    #: 本次的结构化条件（``paged_fetch.build_statement`` 写入）：只供「是否已按某列收窄」的判断（必填筛选、提示），
    #: 谓词仍由 paged_fetch 生成
    conditions: tuple[Mapping[str, Any], ...] = ()
    condition_logic: str = "and"


#: 视为「已按该列收窄」的条件算子（任务 21：辅助明细必填筛选与辅助余额跨维提示）
NARROWING_CONDITION_OPS = frozenset({"eq", "in", "between"})


def filtered_by(ctx: FetchContext, key: str, *, single_value: bool = False) -> bool:
    """本次请求是否已按 ``key`` 收窄：旧筛选键有值，或有该字段的 eq / in / between 条件（OR 逻辑且多于一条时不算）。

    ``single_value=True``：只认收窄到一个值（eq、或只有一个值的 in）——辅助余额判断「是否只看一个辅助维度」用。
    """
    if not _blank(ctx.filters.get(key)):
        return True
    if ctx.condition_logic == "or" and len(ctx.conditions) > 1:
        return False
    for cond in ctx.conditions:
        op = str(cond.get("op") or "")
        if str(cond.get("field") or "") != key or op not in NARROWING_CONDITION_OPS:
            continue
        value = cond.get("value")
        if isinstance(value, (list, tuple)):
            if not value or any(_blank(v) for v in value):
                continue
            if single_value and not (op == "in" and len(value) == 1):
                continue
            return True
        if not _blank(value):
            return True
    return False


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
