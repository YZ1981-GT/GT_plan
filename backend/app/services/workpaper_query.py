"""Spec B (R10) Sprint 3.2.1 — 共享 helper：按科目编码反查关联底稿

设计 D5：所有 related-workpapers 端点（reports / disclosure-notes / misstatements / adjustments）
共享此 helper，避免重复 SQL，便于将来精确化映射。

简化实现（与 note_related_workpapers / report_related_workpapers 同样模式）：
- 现阶段返回项目所有底稿（最多 50 个），前端可显示选择器
- 完整实现需 wp_account_mapping JSON 加载到 DB（Spec D 评估）
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def find_workpapers_by_account_codes(
    db: AsyncSession,
    project_id: UUID,
    account_codes: list[str],
    limit: int = 50,
) -> list[dict]:
    """按科目编码列表反查项目下的关联底稿。

    Args:
        db: AsyncSession
        project_id: 项目 ID
        account_codes: 标准科目编码列表（如 ["1001", "1002"]）
        limit: 返回上限（默认 50）

    Returns:
        list of {id, wp_code, wp_name} dicts
    """
    from app.models.workpaper_models import WpIndex

    # 简化实现：忽略 account_codes 精确匹配，按 project_id 列出全部底稿
    # 后续 Spec D 精确化时扩展为 JOIN wp_account_mapping
    if not account_codes:
        return []

    try:
        stmt = (
            select(WpIndex)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
            .order_by(WpIndex.wp_code)
            .limit(limit)
        )
        result = await db.execute(stmt)
        wps = result.scalars().all()
    except Exception as e:
        logger.debug("find_workpapers_by_account_codes failed: %s", e)
        return []

    # 简化匹配：wp_code 首字符循环匹配 account_code 首字符
    # 例如 1001 → D 类（货币资金）；2202 → D 类（应付账款）；6001 → K 类（管理费用）
    cycle_hint = {
        "1": ("D", "E"),  # 流动资产 → D/E
        "2": ("D",),       # 流动负债 → D
        "3": ("M",),       # 权益 → M
        "4": ("M",),       # 权益（资本公积等）→ M
        "5": ("K",),       # 收入 → K
        "6": ("K", "L"),  # 费用 → K/L
    }
    relevant_prefixes: set[str] = set()
    for code in account_codes:
        if not code:
            continue
        first = str(code)[:1]
        for prefix in cycle_hint.get(first, ()):
            relevant_prefixes.add(prefix)

    matched = [
        {
            "id": str(wp.id),
            "wp_code": wp.wp_code,
            "wp_name": wp.wp_name,
        }
        for wp in wps
        if not relevant_prefixes or (wp.wp_code and wp.wp_code[:1] in relevant_prefixes)
    ]

    # 如果按前缀过滤后为空，退化返回全部（避免 0 结果用户困惑）
    if not matched:
        matched = [
            {"id": str(wp.id), "wp_code": wp.wp_code, "wp_name": wp.wp_name}
            for wp in wps[:10]
        ]

    return matched[:limit]
