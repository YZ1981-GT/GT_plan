"""auto_data_source 注册式解析器。

将 ProcedureTableService._resolve_auto_values 的 20+ elif 分支
拆解为独立的注册式 resolver 函数，每个 resolver：
- 只负责单一数据源的查询逻辑
- 返回 dict（至少 summary 字段）
- 异常由调度器统一捕获记录

用法：
    from app.services.auto_data_resolvers import resolve_auto_data_source

    result = await resolve_auto_data_source(db, project_id, year, source_name)
    # result = {"summary": "...", ...}  或  None（未注册的 source）

新增 resolver 只需在本模块底部加一个 @auto_resolver("name") 装饰的 async 函数。
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Awaitable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Registry 基础设施
# ═══════════════════════════════════════════════════════════════════════════════

# resolver 签名: async (db, project_id, year, **kwargs) -> dict[str, Any]
ResolverFn = Callable[..., Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, ResolverFn] = {}

# ─── 可观测性：resolver 失败计数 ─────────────────────────────────────────────
_RESOLVER_FAILURE_COUNTS: dict[str, int] = {}


def _inc_resolver_failure(source: str) -> None:
    """记录 resolver 失败次数（内存计数器，供 /health 或 Prometheus 采集）。"""
    _RESOLVER_FAILURE_COUNTS[source] = _RESOLVER_FAILURE_COUNTS.get(source, 0) + 1


def get_resolver_failure_counts() -> dict[str, int]:
    """返回各 resolver 累计失败次数（供监控端点使用）。"""
    return dict(_RESOLVER_FAILURE_COUNTS)


def auto_resolver(name: str):
    """装饰器：注册一个 auto_data_source 解析器。"""
    def decorator(fn: ResolverFn) -> ResolverFn:
        _REGISTRY[name] = fn
        return fn
    return decorator


def get_registered_sources() -> list[str]:
    """返回所有已注册的 source 名列表（供测试/自省用）。"""
    return list(_REGISTRY.keys())


async def resolve_auto_data_source(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    source: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """调度器：按 source 名查找并执行对应 resolver。

    Returns:
        resolver 返回的 dict（至少含 summary），或 None 表示未注册。
        resolver 异常时返回 {"summary": "⚠️ 数据获取失败", "_error": True}，
        前端可据此区分"真的无数据"和"resolver 报错降级"。
    """
    resolver = _REGISTRY.get(source)
    if resolver is None:
        return None
    try:
        return await resolver(db, project_id, year, **kwargs)
    except Exception as e:
        _logger.error(
            "auto_data_source '%s' failed [project=%s year=%s]: %s",
            source, project_id, year, e, exc_info=True,
        )
        _inc_resolver_failure(source)
        return {"summary": "⚠️ 数据获取失败", "_error": True, "_error_detail": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 触发各域子模块的 @auto_resolver 装饰器注册
# 放在 auto_resolver 定义之后（文件末尾），避免循环导入
# ═══════════════════════════════════════════════════════════════════════════════
from . import _adjustments, _consol, _control_b, _cycle, _completion, _misstatement_aggregation, _tax_income, _going_concern, _a17_ch08, _d3_prepaid, _f1_prepaid, _f2_inventory, _d4_revenue, _d5_receivables_financing, _d6_contract_assets, _d7_contract_liabilities, _s_transaction  # noqa: E402,F401
