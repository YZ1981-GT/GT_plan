"""SQL 源取数内核：COUNT、ORDER BY、LIMIT / OFFSET 与条件都在数据库内（advanced-query-linkage-closure ADR-AQL-06，design §3.1）。

- ``build_statement``：WHERE = 源口径谓词（``SourceSpec.base_where``）+ 旧 ``filters`` + 结构化条件；选择列 =
  所选显示列（空 = 全部，按源定义的列序）+ 全部隐藏列。未登记的筛选键 / 条件字段 / 列 → 400，不再静默忽略。
- ``page``：total 来自 COUNT（同一 WHERE），排序 = 用户 sort → 源默认排序 → 末项唯一键；只对可空列加
  ``NULLS LAST``；offset > :data:`MAX_SQL_OFFSET` → 422 ``OFFSET_TOO_DEEP``（深翻页请改用导出）。
- ``all_rows``：分组 / 透视要全量参与计算，先 COUNT，> ``FETCH_HARD_CAP`` → 400 ``AGGREGATION_TOO_LARGE``，
  不再在截断样本上算出「看起来对」的合计（AQ-03）。

谓词一律经 ``param_sql_builder``（``build_portable_filter`` / ``ParamSQLBuilder.build_where``）生成，用户值只进绑定参数。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.sql import Select

from app.services.custom_query.builder_dsl import _serialize_cell
from app.services.custom_query.execution_guard import QUERY_TIMEOUT_MS, cancellable_query
from app.services.custom_query.pagination import FETCH_HARD_CAP, _reject_sort_direction, _reject_sort_field
from app.services.custom_query.param_sql_builder import ParamSQLBuilder, build_portable_filter
from app.services.custom_query.query_orchestrator import ColumnMeta, FetchPage
from app.services.custom_query.source_registry import (
    FetchContext,
    SourceColumn,
    SourceSpec,
    ref_context,
)
from app.services.custom_query.table_whitelist import OPERATOR_WHITELIST

#: SQL 源可达的最深 offset（R2.3）；更深的翻页请缩小范围或使用导出
MAX_SQL_OFFSET = 100_000
#: in / not_in 条件值数组上限（design §6）
MAX_IN_VALUES = 500
_DIRECTIONS = ("asc", "desc")


def _bad_request(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=400, detail={"error_code": code, "message": message, **extra})


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _filter_predicates(spec: SourceSpec, filters: Mapping[str, Any]) -> list[Any]:
    """旧 ``filters`` 字典 → 谓词。空值（None / 空串）视为未填，与旧取数器 ``if filters.get(k)`` 同口径。"""
    by_key = {fk.key: fk for fk in spec.filter_keys}
    clauses: list[Any] = []
    for key, value in filters.items():
        if key in spec.echo_filters or key in spec.context_filters:  # 回显键；口径键由源的 base_where 消费并校验
            continue
        fk = by_key.get(key)
        if fk is None:
            allowed = sorted([*by_key, *spec.echo_filters, *spec.context_filters])
            raise _bad_request(
                "UNKNOWN_FILTER_KEY",
                f"数据源「{spec.label}」不支持筛选键「{key}」，可用：{'、'.join(allowed) or '无'}",
                filter_key=key, allowed=allowed,
            )
        if _is_blank(value):
            continue
        if isinstance(value, (dict, list, tuple, set)):
            raise _bad_request("INVALID_FILTER_VALUE", f"筛选键「{key}」的值必须是单个值", filter_key=key)
        if fk.normalize is not None:
            value = fk.normalize(value)
        column = spec.column(fk.column)
        assert column is not None, f"{spec.key}.{fk.key} 指向未登记的列 {fk.column}"  # 注册表自洽（单元测试守住）
        if fk.op == "code_family":
            # 编码精确或其子编码：E1 带出 E1-1 / E1-2（底稿树叶子口径），前缀按字面匹配
            clauses.append(sa.or_(
                build_portable_filter(column.expr, "eq", value),
                build_portable_filter(column.expr, "prefix", f"{value}-", allow_internal=True),
            ))
        else:
            clauses.append(build_portable_filter(column.expr, fk.op, value, allow_internal=True))
    return clauses


def _condition_where(spec: SourceSpec, conditions: Sequence[Mapping[str, Any]], logic: str) -> Any:
    """结构化条件（字段、算子、值 + and / or）→ 单个参数化谓词；字段只认可作条件的显示列。"""
    conditionable = {c.key: c for c in spec.columns if c.conditionable}
    triples: list[tuple[Any, str, Any]] = []
    for cond in conditions:
        field = str(cond.get("field") or "")
        op = str(cond.get("op") or "")
        value = cond.get("value")
        column = conditionable.get(field)
        if column is None:
            raise _bad_request(
                "UNKNOWN_CONDITION_FIELD",
                f"数据源「{spec.label}」没有可作条件的字段「{field}」，可用：{'、'.join(conditionable)}",
                field=field, allowed=list(conditionable),
            )
        if op not in OPERATOR_WHITELIST:
            raise _bad_request(
                "OP_NOT_ALLOWED", f"条件「{field}」的算子「{op}」不在白名单中",
                field=field, allowed_ops=sorted(OPERATOR_WHITELIST),
            )
        if op in ("in", "not_in") and isinstance(value, (list, tuple)) and len(value) > MAX_IN_VALUES:
            raise _bad_request("INVALID_IN_VALUE", f"条件「{field}」的取值不能超过 {MAX_IN_VALUES} 个", field=field)
        triples.append((column.expr, op, value))
    return ParamSQLBuilder.build_where(triples, logic=logic, filter_builder=build_portable_filter)


def _select_columns(spec: SourceSpec, requested: Iterable[str]) -> tuple[list[SourceColumn], list[SourceColumn]]:
    """所选显示列（按源定义的列序）与随行返回的隐藏列。"""
    wanted = [str(k) for k in requested if k]
    if wanted:
        known = set(spec.display_keys)
        unknown = [k for k in wanted if k not in known]
        if unknown:
            raise _bad_request(
                "UNKNOWN_COLUMN",
                f"数据源「{spec.label}」没有列「{'、'.join(unknown)}」，可用：{'、'.join(spec.display_keys)}",
                columns=unknown, allowed=spec.display_keys,
            )
        display = [c for c in spec.columns if c.key in set(wanted)]
    else:
        display = list(spec.columns)
    shown = {c.key for c in display}
    return display, [h for h in spec.hidden if h.key not in shown]


async def build_statement(
    spec: SourceSpec,
    ctx: FetchContext,
    *,
    conditions: Sequence[Mapping[str, Any]] = (),
    logic: str = "and",
    columns: Iterable[str] = (),
) -> tuple[Select, list[SourceColumn]]:
    """不带 ORDER BY / LIMIT 的语句 + 显示列。先校验输入（全部 400），再查口径（可能触库）。"""
    filters = dict(ctx.filters)
    # required_filters：至少满足其中一组（组内各键都有值）
    if spec.required_filters and not any(
        all(not _is_blank(filters.get(k)) for k in group) for group in spec.required_filters
    ):
        raise _bad_request("AUX_FILTER_REQUIRED", "辅助明细请先按科目或辅助类型筛选")
    display, hidden = _select_columns(spec, columns)
    filter_clauses = _filter_predicates(spec, filters)
    condition_clause = _condition_where(spec, conditions, logic)
    where = [*await spec.base_where(ctx), *filter_clauses]
    if condition_clause is not None:
        where.append(condition_clause)
    selected = [c.expr.label(c.key) for c in (*display, *hidden)]
    for key in spec.echo_filters:
        if not _is_blank(filters.get(key)):
            selected.append(sa.literal(str(filters[key]), sa.String).label(key))
    stmt = sa.select(*selected).select_from(spec.from_clause(ctx)).where(*where)
    return stmt, display


def _order_by(spec: SourceSpec, sort: Sequence[Mapping[str, Any]]) -> list[Any]:
    """用户 sort → 源默认排序 → 末项唯一键升序；可空列 NULLS LAST（R2.2）。"""
    sortable = {c.key: c for c in (*spec.columns, *spec.hidden) if c.sortable}
    keys: list[tuple[SourceColumn, str]] = []
    used: set[str] = set()
    for item in sort or []:
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        if field not in sortable:
            _reject_sort_field(field, list(sortable))
        direction = item.get("direction", "asc")
        if not isinstance(direction, str) or direction.lower() not in _DIRECTIONS:
            _reject_sort_direction(field, direction)
        if field not in used:
            keys.append((sortable[field], direction.lower()))
            used.add(field)
    if not keys:
        for field, direction in spec.default_sort:
            if field not in used:
                keys.append((sortable[field], direction))
                used.add(field)
    if spec.unique_key not in used:
        keys.append((sortable[spec.unique_key], "asc"))
    clauses = []
    for column, direction in keys:
        expr = column.order_expr
        clause = expr.desc() if direction == "desc" else expr.asc()
        clauses.append(clause.nulls_last() if column.nullable else clause)
    return clauses


def _rows(result: Any) -> list[dict]:
    return [{k: _serialize_cell(v) for k, v in row.items()} for row in result.mappings().all()]


def _column_meta(display: Sequence[SourceColumn]) -> list[ColumnMeta]:
    return [ColumnMeta(key=c.key, title=c.key, dtype=c.dtype) for c in display]


async def _count(ctx: FetchContext, stmt: Select) -> int:
    return int((await ctx.db.execute(sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one())


async def page(
    spec: SourceSpec,
    ctx: FetchContext,
    *,
    conditions: Sequence[Mapping[str, Any]] = (),
    logic: str = "and",
    columns: Iterable[str] = (),
    sort: Sequence[Mapping[str, Any]] = (),
    limit: int,
    offset: int,
) -> FetchPage:
    """一页结果 + 真实 total（编排器跳过内存排序 / 计数 / 切片）。"""
    if offset > MAX_SQL_OFFSET:
        raise HTTPException(status_code=422, detail={
            "error_code": "OFFSET_TOO_DEEP",
            "message": f"翻页过深（offset 超过 {MAX_SQL_OFFSET:,}），请缩小范围或使用导出",
            "max_offset": MAX_SQL_OFFSET,
        })
    order = _order_by(spec, sort)
    async with cancellable_query(ctx.db, QUERY_TIMEOUT_MS):
        stmt, display = await build_statement(spec, ctx, conditions=conditions, logic=logic, columns=columns)
        total = await _count(ctx, stmt)
        rows = _rows(await ctx.db.execute(stmt.order_by(*order).limit(limit).offset(offset)))
        warnings = await spec.warn(ctx) if spec.warn else []
        meta = {"ref_context": await ref_context(ctx)}
    return FetchPage(rows=rows, columns=_column_meta(display), total=total, paged=True, meta=meta, warnings=warnings)


async def all_rows(
    spec: SourceSpec,
    ctx: FetchContext,
    *,
    conditions: Sequence[Mapping[str, Any]] = (),
    logic: str = "and",
    columns: Iterable[str] = (),
    cap: int = FETCH_HARD_CAP,
) -> FetchPage:
    """分组 / 透视用的全量行（交编排器内存处理）；参与行数 > cap → 400，不返回截断样本上的聚合。"""
    async with cancellable_query(ctx.db, QUERY_TIMEOUT_MS):
        stmt, display = await build_statement(spec, ctx, conditions=conditions, logic=logic, columns=columns)
        total = await _count(ctx, stmt)
        if total > cap:
            raise _bad_request(
                "AGGREGATION_TOO_LARGE",
                f"参与分组 / 透视的行数为 {total:,}，超过 {cap:,} 行上限；请补充筛选条件，或改用高级构建器",
                row_count=total, limit=cap,
            )
        rows = _rows(await ctx.db.execute(stmt.order_by(*_order_by(spec, ()))))
        warnings = await spec.warn(ctx) if spec.warn else []
        meta = {"ref_context": await ref_context(ctx)}
    return FetchPage(rows=rows, columns=_column_meta(display), total=len(rows), paged=False, meta=meta, warnings=warnings)


def project_uuid(project_id: Any) -> uuid.UUID:
    """编排器已经过 OwnershipGuard（无效标识即 403），这里只做类型转换。"""
    return project_id if isinstance(project_id, uuid.UUID) else uuid.UUID(str(project_id))
