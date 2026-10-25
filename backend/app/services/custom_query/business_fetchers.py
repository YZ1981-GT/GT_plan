"""业务视图取数分派（QueryOrchestrator 的 ``business_fetcher`` 实现）。

设计对应 `.kiro/specs/advanced-query-hardening-wiring-closure/design.md` §Components 4。

**存在理由**：改造前 ``custom_query.execute_query`` 用 14 条内联 ``if/elif`` 直接分发
取数器，`ExecuteCompatibilityAdapter` 与 `QueryOrchestrator` 因此被完整绕过 ——
两者连同 `pagination` / `grouping_engine` / `pivot_engine` 全部成为死代码。本模块把
分派逻辑抽为编排器可注入的单一 fetcher，使 router 只保留 HTTP 层职责
（响应头、审计、错误映射），取数、分组、透视、分页统一由编排器驱动。

取数器函数体仍留在 ``app.routers.custom_query``（14 个 ``_query_*``，共约 900 行 SQL），
本模块经**惰性 import** 引用，避免 router ↔ service 循环导入。这是有意的分层取舍：
分派与生命周期归服务层，具体 SQL 归原处，不做一次性大搬迁。

_Requirements: 3.7, 4.8, 5.3_
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.services.custom_query.pagination import FETCH_HARD_CAP
from app.services.custom_query.query_orchestrator import ColumnMeta, QueryRequest

logger = logging.getLogger(__name__)

#: 精确匹配的数据源 → 取数器函数名（函数定义在 app.routers.custom_query）。
EXACT_SOURCE_FETCHERS: dict[str, str] = {
    "report": "_query_report",
    "trial_balance": "_query_trial_balance",
    "tb_detail": "_query_trial_balance",
    "tb_summary": "_query_tb_summary",
    "disclosure": "_query_disclosure",
    "disclosure_note": "_query_disclosure",
    "adjustment": "_query_adjustments",
    "worksheet": "_query_worksheet",
    "workpaper": "_query_workpaper",
    "account_balance": "_query_account_balance",
    "ledger_entries": "_query_ledger_entries",
    "report_lines": "_query_report_lines",
    "workhours": "_query_workhours",
}

#: 前缀匹配的数据源 → 取数器函数名（``report_xxx`` / ``adj_xxx`` / ``ws_xxx``）。
PREFIX_SOURCE_FETCHERS: tuple[tuple[str, str], ...] = (
    ("report_", "_query_report"),
    ("adj_", "_query_adjustments"),
    ("ws_", "_query_worksheet"),
)

#: 合并单位子类型 → 取数器函数名（``consol_unit:{company_code}:{kind}``）。
CONSOL_UNIT_KINDS: dict[str, str] = {
    "account_balance": "_query_account_balance",
    "ledger_entries": "_query_ledger_entries",
    "tb_detail": "_query_trial_balance",
    "adjustment": "_query_adjustments",
}


def _router_module() -> Any:
    """惰性取 router 模块（取数器宿主），避免 service ↔ router 循环导入。"""
    from app.routers import custom_query as router_module

    return router_module


def _resolve_fetcher(name: str) -> Callable[..., Awaitable[dict]]:
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


def _reject_unknown_source(source: str) -> None:
    """未知数据源 → 400。

    改造前返回 ``200 {"rows": [], "error": "未知数据源: x"}``，前端表现为「查不到
    数据」而非「参数错了」（R5.3 禁止 2xx 携带 error）。
    """
    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "UNKNOWN_SOURCE",
            "message": f"未知数据源: {source}",
            "source": source,
        },
    )


def _columns_from_result(result: dict, rows: list[dict]) -> list[ColumnMeta]:
    """取数结果的 ``columns``（``list[str]``）→ ``list[ColumnMeta]``。

    取数器未声明 columns 时回退为首行键序，避免结果有行却无列元数据（前端据
    columns 决定表头，缺列会渲染成空表）。
    """
    raw = result.get("columns")
    keys: list[str]
    if isinstance(raw, (list, tuple)) and raw:
        keys = [str(c) for c in raw]
    elif rows:
        keys = [str(k) for k in rows[0].keys()]
    else:
        keys = []
    return [ColumnMeta(key=k, title=k) for k in keys]


async def _dispatch(
    req: QueryRequest, db: Any, fetch_limit: int | None
) -> dict:
    """按 ``req.source`` 分派到具体取数器，返回其原始 dict 结果。"""
    source = (req.source or "").strip()
    if not source:
        _reject_unknown_source(source)

    pid = req.project_id
    year = req.year
    filters = dict(req.filters or {})
    router_module = _router_module()

    # ── 跨模块 cell 级查询（report:type|range / note:section|range / …）──
    from app.services.custom_query.module_cell_resolver import (
        is_module_cell_source,
        module_cell_resolver,
    )

    if is_module_cell_source(source):
        return await module_cell_resolver.resolve(db, source, pid, year)

    # ── disclosure_note:{section_id}（附注树叶子）──
    if source.startswith("disclosure_note:"):
        section_id = source.split(":", 1)[1]
        return await _resolve_fetcher("_query_disclosure")(
            db, pid, year, {**filters, "section_id": section_id}, fetch_limit
        )

    # ── consol_unit:{company_code}:{kind}（合并单位树叶子）──
    if source.startswith("consol_unit:"):
        parts = source.split(":", 2)
        if len(parts) != 3:
            _reject_unknown_source(source)
        _, company_code, kind = parts
        fetcher_name = CONSOL_UNIT_KINDS.get(kind)
        if fetcher_name is None:
            _reject_unknown_source(source)
        scoped = {**filters, "company_code": company_code}
        if kind == "adjustment":
            scoped["adjustment_type"] = "AJE"
        return await _resolve_fetcher(fetcher_name)(db, pid, year, scoped, fetch_limit)

    # ── workpaper:{wp_code}[|{sheet_name}]（底稿树叶子）──
    if source.startswith("workpaper:"):
        tail = source.split(":", 1)[1]
        scoped = dict(filters)
        if "|" in tail:
            wp_code, sheet_name = tail.split("|", 1)
            scoped.update({"wp_code": wp_code, "sheet_name": sheet_name})
        else:
            scoped["wp_code"] = tail
        return await _resolve_fetcher("_query_workpaper")(
            db, pid, year, scoped, fetch_limit
        )

    # ── 精确匹配 ──
    fetcher_name = EXACT_SOURCE_FETCHERS.get(source)
    if fetcher_name is None:
        # ── 前缀匹配 ──
        for prefix, name in PREFIX_SOURCE_FETCHERS:
            if source.startswith(prefix):
                fetcher_name = name
                break
    if fetcher_name is None:
        _reject_unknown_source(source)

    assert fetcher_name is not None  # 上一行必抛，此处仅供类型收窄
    _ = router_module  # 引用以明示宿主已解析（_resolve_fetcher 内再次取用）
    return await _resolve_fetcher(fetcher_name)(db, pid, year, filters, fetch_limit)


async def business_fetcher(
    req: QueryRequest, resolved: list[Any], db: Any
) -> tuple[list[dict], list[ColumnMeta]]:
    """编排器 step4 的业务视图取数钩子。

    与改造前的差异在于**不再预截断为展示 limit**：取数层按
    :func:`resolve_fetch_limit` 取整页所需（受 :data:`FETCH_HARD_CAP` 约束），
    分页切片交由编排器 step7，故 ``total`` 在上限内是真实行数（R4.8）。
    """
    # limit=None：取数层不施加展示截断（R4.8）。硬上限由取数器内部的
    # `custom_query._effective_limit` 归一为 FETCH_HARD_CAP，故既不会拉全表，
    # 也不会让 total 退化为「当前页行数」。
    result = await _dispatch(req, db, None)

    if not isinstance(result, dict):  # pragma: no cover — 取数器契约违约应立刻暴露
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "FETCHER_CONTRACT_VIOLATION",
                "message": f"取数器返回类型非 dict：{type(result).__name__}",
            },
        )

    # 取数器内部的 error 字段不得以 2xx 形态外泄（R5.3）
    error = result.get("error")
    if error:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "QUERY_FAILED",
                "message": str(error),
                "source": req.source,
            },
        )

    rows = list(result.get("rows") or [])
    columns = _columns_from_result(result, rows)
    return rows, columns


def fetch_cap_warning(row_count: int) -> str | None:
    """触达取数硬上限时的 warning 文案（供编排器/router 追加到 warnings）。"""
    if row_count >= FETCH_HARD_CAP:
        return (
            f"结果已达取数上限 {FETCH_HARD_CAP} 行，total 与后续分页可能不完整；"
            "请补充筛选条件后重查"
        )
    return None
