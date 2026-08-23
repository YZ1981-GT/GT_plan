"""白名单构建器的 DSL 契约与 DSL → SQL 构建（服务层）。

从 ``routers/query_builder.py`` 抽出：router 只保留 HTTP 层职责（依赖注入、
响应头、审计、错误映射），DSL 校验与 ``select()`` 构建属服务层。

安全铁律（与抽出前完全一致，仅位置变化）：
- 表 / 字段 / 算子 / 聚合 / JOIN 一律经 ``table_whitelist`` 白名单，无字符串拼接；
- 项目作用域约束由 ``builder_scope.apply_scope_to_select`` 在 WHERE 组装的
  **最后一步**追加，用户 DSL 无法放宽；
- 默认列集取 ``default_fields``（业务列），技术列与 PII 列需显式请求且经角色校验。

``routers/query_builder`` 对本模块的符号做 re-export，既有
``from app.routers.query_builder import QueryDSL, _build_select`` 的调用方与测试
不受影响。

_Requirements: 2.1, 2.6, 6.1, 6.2, 6.3, 7.1, 7.3, 7.4, 4.3_
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Select, and_, asc, desc, false, func, select, true
from sqlalchemy.sql.elements import ColumnElement

from app.services.custom_query.builder_scope import apply_scope_to_select
from app.services.custom_query.param_sql_builder import (
    ParamSQLBuilder as _ParamSQLBuilder,
    build_filter as _psb_build_filter,
    coerce_value as _psb_coerce_value,
)

_psb_build_where = _ParamSQLBuilder.build_where
from app.services.custom_query.table_whitelist import (
    AGGREGATE_WHITELIST,
    JOIN_WHITELIST,
    OPERATOR_WHITELIST,
    TABLE_WHITELIST,
    enforce_complexity_budget,
    enforce_join_business_key,
    enforce_pii_field_access,
    enforce_query_plan,
)

if TYPE_CHECKING:  # 仅类型标注需要，避免运行时循环导入
    from app.services.custom_query.builder_scope import BuilderScope

logger = logging.getLogger(__name__)

class FilterCond(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    op: str = Field(..., min_length=1, max_length=20)
    # value 类型由后端按 op 解释（in/not_in 接受 list；is_null/is_not_null 忽略；between 接受 [lo, hi]）
    value: Any | None = None


class OrderBy(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    direction: Literal["asc", "desc"] = "asc"


class QueryDSL(BaseModel):
    table: str = Field(..., min_length=1, max_length=64)
    fields: list[str] = Field(default_factory=list)
    filters: list[FilterCond] = Field(default_factory=list)
    filter_logic: Literal["and", "or"] = "and"
    group_by: list[str] = Field(default_factory=list)
    aggregates: list[dict[str, str]] = Field(default_factory=list)
    # aggregates 元素：{"func": "sum", "field": "audited_amount", "alias": "total"}
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    # S-3 v2 新增：JOIN 关联（声明式白名单，不接受用户传 ON）
    # joins 元素：{"table": "wp_index", "type": "inner"|"left"}
    joins: list[dict[str, str]] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 核心：DSL → SQLAlchemy core `select()`（白名单+绑定参数；无字符串拼接）
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_table(table_name: str) -> dict[str, Any]:
    if table_name not in TABLE_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "TABLE_NOT_ALLOWED",
                    "message": f"表 '{table_name}' 不在白名单中",
                    "allowed_tables": sorted(TABLE_WHITELIST.keys())},
        )
    return TABLE_WHITELIST[table_name]


def _resolve_column(table_meta: dict[str, Any], field: str) -> Column:
    if field not in table_meta["fields"]:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "FIELD_NOT_ALLOWED",
                    "message": f"字段 '{field}' 不在表 '{table_meta['label']}' 白名单中",
                    "allowed_fields": list(table_meta["fields"])},
        )
    model = table_meta["model"]
    col = getattr(model, field, None)
    if col is None:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "FIELD_NOT_FOUND",
                    "message": f"模型 {model.__name__} 不存在字段 '{field}'"},
        )
    return col


def _resolve_field_ref(
    base_table: str,
    field: str,
    join_tables: set[str],
) -> Column:
    """S-3 v2：解析字段引用，支持 ``table.field`` 双段语法

    - ``audited_amount`` → 默认从 base_table 解析
    - ``trial_balance.audited_amount`` → 从指定表解析
    - 引用的表必须 ∈ (base_table ∪ join_tables)
    """
    if "." in field:
        table_name, field_name = field.split(".", 1)
        if table_name != base_table and table_name not in join_tables:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "FIELD_TABLE_NOT_JOINED",
                    "message": f"字段引用 '{field}' 中的表 '{table_name}' 未在 joins 中声明",
                    "joined_tables": sorted(join_tables | {base_table}),
                },
            )
        meta = _resolve_table(table_name)
        return _resolve_column(meta, field_name)
    # 单段语法：从 base_table 解析
    return _resolve_column(_resolve_table(base_table), field)


def _coerce_value(col: Column, value: Any) -> Any:
    """按列的 SQLAlchemy 类型把用户值转为正确 Python 类型（薄委托）。

    实现在 ``param_sql_builder.coerce_value`` —— 该模块是「值 → 参数化谓词」的
    单一真源。此前两处各有一份几乎相同的实现（本文件与 param_sql_builder），
    而 param_sql_builder 那份从未被生产调用（router 引用数 0）。保留本函数名是因为
    ``_build_select`` 与既有测试都引用它。
    """
    return _psb_coerce_value(col, value)


def _build_filter(col: Column, op: str, value: Any) -> ColumnElement:
    """把 (列, 操作符, 用户值) 构造为参数化谓词。

    值 coerce 与除 ``in`` / ``not_in`` 外的算子全部委托
    ``param_sql_builder``（值 → 谓词的单一真源），消除此前两份几乎相同的实现。

    ``in`` / ``not_in`` **不**委托，原因是方言：``param_sql_builder`` 用
    ``col == any_(list)``（PG 专用，其契约测试固定以 postgresql 方言**编译**、不
    执行），而构建器的端点测试在 SQLite 上**真实执行** —— SQLite 无 ``ANY``
    函数，会直接 ``OperationalError: no such function: ANY``。故此处用方言中立的
    ``in_`` / ``notin_``（SQLAlchemy 2.x 以 expanding bindparam 展开，asyncpg 下
    同样是参数化的，不存在旧式「IN 传 tuple」的问题）。

    但 R10.3 的**实质**照样落地：原实现对空数组抛 400「要求非空数组」，现在
    ``in`` 空集合 → 恒假谓词（0 行）、``not_in`` 空集合 → 恒真谓词（全部行），
    均不报错。空候选集在真实使用中很常见（上游过滤后为空），报错会让用户以为
    查询坏了。
    """
    if op in ("in", "not_in"):
        if not isinstance(value, (list, tuple)):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_IN_VALUE",
                    "message": f"{op} 操作符要求 value 为数组",
                },
            )
        coerced = [_coerce_value(col, v) for v in value]
        if not coerced:
            # R10.3：空集合返回空结果集 / 全部行，不报错
            return false() if op == "in" else true()
        return col.in_(coerced) if op == "in" else col.notin_(coerced)
    return _psb_build_filter(col, op, value)


def _build_select(
    dsl: QueryDSL,
    *,
    scope: "BuilderScope | None" = None,
    role: str | None = None,
    warnings: list[str] | None = None,
) -> tuple[Select, list[str]]:
    """根据 DSL 构造 `select()` 与列名列表。

    ``scope`` 非空时在 WHERE 组装的最后一步追加项目作用域约束（R2.1）；
    ``role`` 用于 PII 字段准入（R7.4）；``warnings`` 收集非致命提示。
    """
    table_meta = _resolve_table(dsl.table)
    model = table_meta["model"]
    notes = warnings if warnings is not None else []

    # ── 复杂度预算（R6.2 / R6.3）──
    enforce_complexity_budget(
        joins=len(dsl.joins),
        group_dims=len(dsl.group_by),
        aggregates=len(dsl.aggregates),
    )

    # ── PII 字段准入（R7.4）──
    requested = [
        *dsl.fields,
        *dsl.group_by,
        *(str(a.get("field", "")) for a in dsl.aggregates if a.get("field")),
        *(c.field for c in dsl.filters),
    ]
    if requested:
        enforce_pii_field_access(dsl.table, requested, role)

    # ── S-3 v2：解析 joins ──
    join_specs: list[tuple[str, str, list[tuple[str, str]]]] = []  # (target_table, join_type, on_pairs)
    join_tables: set[str] = set()
    for j in dsl.joins:
        target = j.get("table", "")
        jtype = (j.get("type") or "inner").lower()
        if jtype not in ("inner", "left"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "JOIN_TYPE_NOT_ALLOWED",
                    "message": f"join type '{jtype}' 必须 ∈ {{inner, left}}",
                },
            )
        # 校验 target 表存在 + 在 base_table 的 JOIN_WHITELIST 中
        if target not in TABLE_WHITELIST:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "JOIN_TABLE_NOT_ALLOWED",
                    "message": f"join 目标表 '{target}' 不在 TABLE_WHITELIST 中",
                },
            )
        allowed_joins = JOIN_WHITELIST.get(dsl.table, {})
        if target not in allowed_joins:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "JOIN_NOT_REGISTERED",
                    "message": (
                        f"表 '{dsl.table}' 与 '{target}' 之间没有预登记的 JOIN 关系"
                    ),
                    "available_joins_for_base": sorted(allowed_joins.keys()),
                },
            )
        on_pairs = allowed_joins[target]["on"]
        # 运行期复核 ON 含业务键（登记期不变式已拦一层，这里防绕过白名单直调）
        enforce_join_business_key(dsl.table, target, on_pairs)
        join_specs.append((target, jtype, on_pairs))
        join_tables.add(target)

    # ── 单一门禁（R2.6）：表 / JOIN 统一经服务层校验 ──
    # 改造前构建器走自己的 `_resolve_table` 私有路径，`enforce_query_plan` 声明为
    # 「执行前单一门禁」却零调用。放在 join 解析**之后**：JOIN 类型 / 目标表 /
    # 登记关系有各自更具体的 error_code（JOIN_TYPE_NOT_ALLOWED 等），前置会把它们
    # 统一盖成 NOT_WHITELISTED，反而降低可诊断性。
    # 算子与聚合不在此复核 —— 它们由下方 `_build_filter` 与聚合分支按同一真源
    # （OPERATOR_WHITELIST / AGGREGATE_WHITELIST）校验，error_code 更具体。
    enforce_query_plan(
        tables=[dsl.table, *sorted(join_tables)],
        joins=[(dsl.table, t) for t in sorted(join_tables)],
    )

    # ── 选择列 ──
    select_cols: list[ColumnElement] = []
    column_names: list[str] = []

    if dsl.fields:
        for f in dsl.fields:
            col = _resolve_field_ref(dsl.table, f, join_tables)
            select_cols.append(col)
            column_names.append(f)
    elif dsl.aggregates:
        # 纯聚合查询：不要求 fields，但若有 group_by 则前端应同时把它放入 fields
        pass
    else:
        # 无 fields 默认**业务列集**（R7.1）：改造前是全字段，而前端 dsl.fields=[]
        # 是默认值 ⇒ 用户不选字段时结果首列是 UUID 主键，技术列与 PII 混在业务列
        # 之间。技术列仍可显式选择（保留排查能力），只是不再默认带出。
        default_fields = table_meta.get("default_fields") or table_meta["fields"]
        for f in default_fields:
            col = getattr(model, f, None)
            if col is not None:
                select_cols.append(col)
                column_names.append(f)

    # ── 聚合列 ──
    aggregate_funcs = {
        "count": func.count,
        "sum": func.sum,
        "avg": func.avg,
        "min": func.min,
        "max": func.max,
    }
    for agg in dsl.aggregates:
        agg_func = agg.get("func", "").lower()
        agg_field = agg.get("field", "")
        agg_alias = agg.get("alias") or f"{agg_func}_{agg_field.replace('.', '_')}"
        if agg_func not in AGGREGATE_WHITELIST:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "AGG_NOT_ALLOWED",
                        "message": f"聚合函数 '{agg_func}' 不在白名单中",
                        "allowed_aggs": sorted(AGGREGATE_WHITELIST)},
            )
        # count(*) 特例：field='*' 或为空时使用常量
        if agg_func == "count" and (not agg_field or agg_field == "*"):
            agg_col = func.count().label(agg_alias)
        else:
            target = _resolve_field_ref(dsl.table, agg_field, join_tables)
            agg_col = aggregate_funcs[agg_func](target).label(agg_alias)
        select_cols.append(agg_col)
        column_names.append(agg_alias)

    if not select_cols:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "EMPTY_SELECT",
                    "message": "fields 与 aggregates 不能同时为空"},
        )

    stmt: Select = select(*select_cols)

    # ── S-3 v2：应用 JOIN ──
    for target_table, jtype, on_pairs in join_specs:
        target_meta = _resolve_table(target_table)
        target_model = target_meta["model"]
        on_clauses = []
        for left_col, right_col in on_pairs:
            left = _resolve_column(table_meta, left_col)
            right = _resolve_column(target_meta, right_col)
            on_clauses.append(left == right)
        on_expr = and_(*on_clauses) if len(on_clauses) > 1 else on_clauses[0]
        if jtype == "left":
            stmt = stmt.outerjoin(target_model, on_expr)
        else:
            stmt = stmt.join(target_model, on_expr)

    # ── WHERE ──
    # 组合逻辑（and / or / 单条直返 / 空集合不追加 WHERE）委托
    # ``ParamSQLBuilder.build_where``，单条谓词构造传本模块的方言中立版本。
    conditions = [
        (_resolve_field_ref(dsl.table, cond.field, join_tables), cond.op, cond.value)
        for cond in dsl.filters
    ]
    where_clause = _psb_build_where(
        conditions, logic=dsl.filter_logic, filter_builder=_build_filter
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)

    # ── 项目作用域（R2.1）：必须是 WHERE 组装的最后一步 ──
    # 追加语义（AND），用户 DSL 里自写的 project_id 过滤只能与之取交集、无法放宽。
    if scope is not None:
        stmt = apply_scope_to_select(stmt, scope=scope, table_name=dsl.table)
        notes.extend(scope.warnings)

    # ── GROUP BY ──
    for f in dsl.group_by:
        col = _resolve_field_ref(dsl.table, f, join_tables)
        stmt = stmt.group_by(col)

    # ── ORDER BY ──
    # 稳定排序（R4.3）：order_by 为空时 PG 对结果集不保证顺序，而下面紧接 offset
    # ⇒ 翻页会重复/漏行。故无用户排序时补一个确定性键。
    order_cols: list[Any] = []
    for ob in dsl.order_by:
        col = _resolve_field_ref(dsl.table, ob.field, join_tables)
        order_cols.append(asc(col) if ob.direction == "asc" else desc(col))
    if not order_cols and not dsl.group_by and not dsl.aggregates:
        tie_col = getattr(model, "id", None)
        if tie_col is not None:
            order_cols.append(asc(tie_col))
    for col in order_cols:
        stmt = stmt.order_by(col)

    # ── LIMIT / OFFSET ──
    stmt = stmt.limit(min(dsl.limit, 1000)).offset(dsl.offset)

    return stmt, column_names


def _stmt_to_sql(stmt: Select) -> str:
    """生成可读的 SQL 预览（保留绑定参数为命名占位）。"""
    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        return str(compiled)
    except Exception as exc:  # 兼容部分类型无法 inline 的情况
        logger.debug("compile preview fallback: %s", exc)
        return str(stmt)



# ─────────────────────────────────────────────────────────────────────────────
def _serialize_cell(v: Any) -> Any:
    """将 SQL 行单元格序列化为 JSON 友好类型。"""
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value  # SQLAlchemy enum
    return v


def _excel_cell_value(v: Any) -> Any:
    """Excel cell 接受 str/number/datetime；UUID/Decimal/枚举要转换。

    openpyxl 不支持 timezone-aware datetime（会抛 TypeError），
    PG ``timestamptz`` 字段会带 tzinfo，必须显式 strip。
    """
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        # strip tzinfo（保持壁钟时间，符合用户本地化预期）
        return v.replace(tzinfo=None) if v.tzinfo is not None else v
    if isinstance(v, date):
        return v
    if isinstance(v, UUID):
        return str(v)
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value
    return v

