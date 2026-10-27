"""业务视图取数分派（QueryOrchestrator 的 ``business_fetcher`` 实现）。

设计对应 `.kiro/specs/advanced-query-hardening-wiring-closure/design.md` §Components 4 与
`.kiro/specs/advanced-query-linkage-closure/design.md` §3.1~§3.3（ADR-AQL-06）。

分派只有一处：``source_registry.resolve_source`` 把源键解析为三种实现之一——

- **注册表 SQL 源**（试算表、科目余额、序时账、底稿清单、工时、合并单位前缀）：交 ``paged_fetch``，COUNT、
  排序、分页与条件都在数据库内，返回 ``FetchPage(paged=True)``；带分组 / 透视时取全量（> 5,000 行即 400）
  交编排器内存处理。
- **JSON 内存源**（附注、合并工作底稿、底稿单元格区域，``fetchers/``）：行带隐藏列 ``_row_index``（取数顺序），
  行数 > ``FETCH_HARD_CAP`` 即 400 ``RESULT_TOO_LARGE``，不支持结构化条件。
- **暂留 router 的取数器**（报表、报表行次、调整分录）：任务 17 / 18 切到注册表后删除；在此之前同样不支持
  结构化条件，结果触顶（取数层 LIMIT 5,000）即 400，不再返回截断样本。

改造前取数层一律 ``LIMIT 5000``、编排器在样本上内存排序计数，``fetch_cap_warning`` 拿本页行数比 5,000 永不触发
（AQ-03），已删除。

_Requirements: 3.7, 4.8, 5.3（hardening）；R1、R2、R6（linkage-closure）_
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.services.custom_query import paged_fetch
from app.services.custom_query.pagination import FETCH_HARD_CAP
from app.services.custom_query.query_orchestrator import ColumnMeta, FetchPage, QueryRequest
from app.services.custom_query.source_registry import FetchContext, ResolvedSource, resolve_source

logger = logging.getLogger(__name__)


def _router_module() -> Any:
    """惰性取 router 模块（暂留取数器的宿主），避免 service ↔ router 循环导入。"""
    from app.routers import custom_query as router_module

    return router_module


def _legacy_fetcher(name: str) -> Callable[..., Awaitable[dict]]:
    fn = getattr(_router_module(), name, None)
    if fn is None:  # pragma: no cover — 取数器改名即应立刻暴露，不静默降级
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "FETCHER_NOT_FOUND",
                "message": f"取数器 '{name}' 不存在（注册表与实现已漂移）",
            },
        )
    return fn


def _json_fetcher(target: tuple[str, str]) -> Callable[..., Awaitable[dict]]:
    module_name, func_name = target
    module = importlib.import_module(f"app.services.custom_query.fetchers.{module_name}")
    return getattr(module, func_name)


def _columns_from_result(result: dict, rows: list[dict]) -> list[ColumnMeta]:
    """取数结果的 ``columns``（``list[str]``）→ ``list[ColumnMeta]``。

    取数器未声明 columns 时回退为首行键序（隐藏列 ``_row_index`` 除外），避免结果有行却无列元数据。
    """
    raw = result.get("columns")
    keys: list[str]
    if isinstance(raw, (list, tuple)) and raw:
        keys = [str(c) for c in raw]
    elif rows:
        keys = [str(k) for k in rows[0].keys() if k != "_row_index"]
    else:
        keys = []
    return [ColumnMeta(key=k, title=k) for k in keys]


def _reject_conditions(req: QueryRequest) -> None:
    if req.conditions:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "CONDITIONS_UNSUPPORTED",
                "message": f"数据源「{req.source}」不支持结构化条件（附注表格、合并工作底稿、底稿选区等按原表返回）",
                "source": req.source,
            },
        )


def _raise_fetch_error(req: QueryRequest, result: dict) -> None:
    # 取数器内部的 error 字段不得以 2xx 形态外泄（R5.3）
    error = result.get("error")
    if error:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "QUERY_FAILED", "message": str(error), "source": req.source},
        )


def _too_large(req: QueryRequest, row_count: int) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error_code": "RESULT_TOO_LARGE",
            "message": f"结果超过 {FETCH_HARD_CAP:,} 行上限，未返回截断结果；请补充筛选条件后重查",
            "source": req.source,
            "row_count": row_count,
            "limit": FETCH_HARD_CAP,
        },
    )


async def _fetch_sql(req: QueryRequest, target: ResolvedSource, db: Any) -> FetchPage:
    assert target.spec is not None
    ctx = FetchContext(
        db=db,
        user=None,
        project_id=paged_fetch.project_uuid(req.project_id),
        year=int(req.year),
        filters={**dict(req.filters or {}), **dict(target.fixed_filters)},
        company_code=target.company_code,
    )
    common = {"conditions": list(req.conditions), "logic": req.condition_logic, "columns": list(req.columns)}
    if req.group_by or req.pivot is not None:
        # 分组 / 透视要全量参与计算：> FETCH_HARD_CAP 行即 400，不在截断样本上聚合（ADR-AQL-07）
        return await paged_fetch.all_rows(target.spec, ctx, **common)
    return await paged_fetch.page(
        target.spec, ctx, **common, sort=list(req.sort), limit=int(req.limit), offset=int(req.offset)
    )


async def _fetch_json(req: QueryRequest, target: ResolvedSource, db: Any) -> FetchPage:
    assert target.json_fetcher is not None
    _reject_conditions(req)
    filters = {**dict(req.filters or {}), **dict(target.fixed_filters)}
    fetcher = _json_fetcher(target.json_fetcher)
    if target.json_fetcher[1] == "_query_workpaper_cell_range":
        result = await fetcher(db, req.project_id, filters)
    else:
        result = await fetcher(db, req.project_id, req.year, filters, None)
    if not isinstance(result, dict):  # pragma: no cover — 取数器契约违约应立刻暴露
        raise HTTPException(status_code=500, detail={
            "error_code": "FETCHER_CONTRACT_VIOLATION",
            "message": f"取数器返回类型非 dict：{type(result).__name__}",
        })
    _raise_fetch_error(req, result)
    rows = list(result.get("rows") or [])
    if len(rows) > FETCH_HARD_CAP:
        raise _too_large(req, len(rows))
    columns = _columns_from_result(result, rows)
    # 隐藏列 _row_index = 取数顺序（不进 columns、不导出）：内存分页默认保持原表行序（R2.8）
    indexed = [{**row, "_row_index": i} if isinstance(row, dict) else row for i, row in enumerate(rows)]
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    # 取数器给的提示原样带出（如底稿选区「公式未能重算，显示的是文件缓存值」，design §3.7）
    warnings = [str(w) for w in result.get("warnings") or []]
    return FetchPage(rows=indexed, columns=columns, total=len(indexed), paged=False, meta=dict(meta), warnings=warnings)


async def _fetch_legacy(req: QueryRequest, target: ResolvedSource, db: Any) -> tuple[list[dict], list[ColumnMeta]]:
    assert target.legacy_fetcher is not None
    _reject_conditions(req)
    filters = {**dict(req.filters or {}), **dict(target.fixed_filters)}
    result = await _legacy_fetcher(target.legacy_fetcher)(db, req.project_id, req.year, filters, None)
    if not isinstance(result, dict):  # pragma: no cover — 取数器契约违约应立刻暴露
        raise HTTPException(status_code=500, detail={
            "error_code": "FETCHER_CONTRACT_VIOLATION",
            "message": f"取数器返回类型非 dict：{type(result).__name__}",
        })
    _raise_fetch_error(req, result)
    rows = list(result.get("rows") or [])
    # 取数层 LIMIT 5,000（router._effective_limit）：触顶即可能截断，宁可 400 也不返回不完整的 total
    if len(rows) >= FETCH_HARD_CAP:
        raise _too_large(req, len(rows))
    return rows, _columns_from_result(result, rows)


async def business_fetcher(
    req: QueryRequest, resolved: list[Any], db: Any
) -> "tuple[list[dict], list[ColumnMeta]] | FetchPage":
    """编排器 step4 的业务视图取数钩子（分派见模块文档）。"""
    source = (req.source or "").strip()
    filters = dict(req.filters or {})

    # ── 跨模块 cell 级查询（report:type|range / note:section|range / …）——任务 34 随该源族一起删除 ──
    from app.services.custom_query.module_cell_resolver import (
        is_module_cell_source,
        module_cell_resolver,
    )

    if is_module_cell_source(source):
        _reject_conditions(req)
        result = await module_cell_resolver.resolve(db, source, req.project_id, req.year, filters=filters)
        _raise_fetch_error(req, result)
        rows = list(result.get("rows") or [])
        return rows, _columns_from_result(result, rows)

    target = resolve_source(source, filters)
    if target.spec is not None:
        return await _fetch_sql(req, target, db)
    if target.json_fetcher is not None:
        return await _fetch_json(req, target, db)
    return await _fetch_legacy(req, target, db)
