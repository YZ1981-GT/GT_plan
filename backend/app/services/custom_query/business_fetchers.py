"""业务视图取数分派（QueryOrchestrator 的 ``business_fetcher`` 实现）。

设计对应 `.kiro/specs/advanced-query-hardening-wiring-closure/design.md` §Components 4 与
`.kiro/specs/advanced-query-linkage-closure/design.md` §3.1~§3.3（ADR-AQL-06）。

分派只有一处：``source_registry.resolve_source`` 把源键解析为两种实现之一——

- **注册表 SQL 源**（试算表、科目余额、序时账、底稿清单、工时、报表、报表行次、调整分录、合并单位前缀）：交
  ``paged_fetch``，COUNT、排序、分页与条件都在数据库内，返回 ``FetchPage(paged=True)``；带分组 / 透视时取全量
  （> 5,000 行即 400）交编排器内存处理。
- **JSON 内存源**（附注、合并工作底稿、底稿单元格区域，``fetchers/``）：行带隐藏列 ``_row_index``（取数顺序），
  行数 > ``FETCH_HARD_CAP`` 即 400 ``RESULT_TOO_LARGE``，不支持结构化条件。

改造前取数层一律 ``LIMIT 5000``、编排器在样本上内存排序计数，``fetch_cap_warning`` 拿本页行数比 5,000 永不触发
（AQ-03），已删除；router 内暂留的报表 / 报表行次 / 调整分录取数器随 B5 任务 17 / 18 切到注册表删除。

_Requirements: 3.7, 4.8, 5.3（hardening）；R1、R2、R6（linkage-closure）_
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.services.custom_query import paged_fetch
from app.services.custom_query.cycle_scope import CycleScopeCache
from app.services.custom_query.pagination import FETCH_HARD_CAP
from app.services.custom_query.query_orchestrator import ColumnMeta, FetchPage, QueryRequest
from app.services.custom_query.source_registry import FetchContext, ResolvedSource, resolve_source

logger = logging.getLogger(__name__)


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


def _cycle_cache(user: Any, db: Any) -> CycleScopeCache | None:
    """请求级循环范围缓存（R3.8）：业务视图的 execute / export / 模板执行都按当前用户带上；无用户（内部调用）时不限。"""
    return CycleScopeCache(user, db) if user is not None else None


def _sql_context(req: QueryRequest, target: ResolvedSource, db: Any, cycle: CycleScopeCache | None = None) -> FetchContext:
    return FetchContext(
        db=db,
        user=None if cycle is None else cycle.user,
        project_id=paged_fetch.project_uuid(req.project_id),
        year=int(req.year),
        filters={**dict(req.filters or {}), **dict(target.fixed_filters)},
        company_code=target.company_code,
        cycle=cycle,
    )


async def _fetch_sql(req: QueryRequest, target: ResolvedSource, db: Any, cycle: CycleScopeCache | None) -> FetchPage:
    assert target.spec is not None
    ctx = _sql_context(req, target, db, cycle)
    common = {"conditions": list(req.conditions), "logic": req.condition_logic, "columns": list(req.columns)}
    if req.group_by or req.pivot is not None:
        # 分组 / 透视要全量参与计算：> FETCH_HARD_CAP 行即 400，不在截断样本上聚合（ADR-AQL-07）
        return await paged_fetch.all_rows(target.spec, ctx, **common)
    return await paged_fetch.page(
        target.spec, ctx, **common, sort=list(req.sort), count_token=req.count_token,
        limit=int(req.limit), offset=int(req.offset)
    )


async def _fetch_json(req: QueryRequest, target: ResolvedSource, db: Any, cycle: CycleScopeCache | None) -> FetchPage:
    assert target.json_fetcher is not None
    _reject_conditions(req)
    filters = {**dict(req.filters or {}), **dict(target.fixed_filters)}
    fetcher = _json_fetcher(target.json_fetcher)
    if target.json_fetcher[1] == "_query_workpaper_cell_range":
        result = await fetcher(db, req.project_id, filters)
    elif target.json_fetcher[0] == "disclosure":
        # 附注目录 / 章节按本人循环的章节集合严格过滤（与附注页同，R3.8）；None = 不限
        sections = None if cycle is None else (await cycle.scope(paged_fetch.project_uuid(req.project_id))).sections
        result = await fetcher(db, req.project_id, req.year, filters, None, sections=sections)
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


async def business_fetcher(req: QueryRequest, resolved: list[Any], db: Any, *, user: Any = None) -> FetchPage:
    """编排器 step4 的业务视图取数钩子（分派见模块文档）。

    ``user``：当前用户（router 以 ``functools.partial`` 绑定）—— 试算表、调整分录、附注按其循环范围过滤（R3.8）。
    跨模块单元格源键（``report:类型|区域`` 等）随任务 34 删除（AQ-25），由 ``resolve_source`` 按未知数据源 400。
    """
    source = (req.source or "").strip()
    filters = dict(req.filters or {})
    target = resolve_source(source, filters)
    cycle = _cycle_cache(user, db)
    if target.spec is not None:
        return await _fetch_sql(req, target, db, cycle)
    return await _fetch_json(req, target, db, cycle)


async def prepare_export(req: QueryRequest, db: Any, *, user: Any = None) -> "paged_fetch.StreamPlan | None":
    """服务端完整导出的取数准备（R8，design §3.5），与 :func:`business_fetcher` 同一分派与校验。

    注册表 SQL 源 → ``paged_fetch.StreamPlan``（与 ``page`` 同一语句、同一排序，不带 LIMIT；400 / 422 在这一步）；JSON 内存源
    → None：调用方取导出名额后经 :func:`business_fetcher` 取全部行（≤ 5,000，同 execute 的内存路径）。带结构化条件的
    非 SQL 源在这里就 400 ``CONDITIONS_UNSUPPORTED``；未知源（含已删除的跨模块单元格源键）400 ``UNKNOWN_SOURCE``。
    """
    source = (req.source or "").strip()
    target = resolve_source(source, dict(req.filters or {}))
    if target.spec is None:
        _reject_conditions(req)
        return None
    return await paged_fetch.prepare_stream(
        target.spec, _sql_context(req, target, db, _cycle_cache(user, db)), conditions=list(req.conditions),
        logic=req.condition_logic, columns=list(req.columns), sort=list(req.sort),
    )
