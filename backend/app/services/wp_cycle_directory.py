"""审计循环底稿目录 — B-Index 跨底稿导航数据源。

动机（2026-06-06 修复）：B-Index「底稿目录」此前只列当前 xlsx 内的 sheets
（`_generate_b_index_data` 遍历当前 working_paper 的 classifications），
但致同体系下「底稿目录」应展示**整个审计循环的所有底稿**——如 D 循环目录应含
D0（函证）/ D1（应收票据）/ D2（应收账款）… D7，让用户从目录直接跨底稿跳转，
而不仅是当前底稿内部的 sheet 切换。

本模块查同一 `audit_cycle` 下的全部 wp_index + 对应 working_paper，
按 wp_code 自然排序（D2-1 在 D2-10 之前），供前端渲染跨底稿目录区。
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# wp_code 自然排序：把数字段按数值比较（D2-1 < D2-10 < D3），
# 字母段按字符串比较（D1 < D1A）。拆成 (str|int) 元组做混合排序键。
_NUM_RE = re.compile(r"(\d+)")


def _natural_key(code: str) -> list:
    """生成 wp_code 自然排序键。

    'D2-10' → ['D', 2, '-', 10, '']；'D2-1' → ['D', 2, '-', 1, '']
    → D2-1 排在 D2-10 之前（数值比较，非字典序）。
    """
    parts = _NUM_RE.split(code or "")
    key: list = []
    for i, p in enumerate(parts):
        # _NUM_RE.split 的奇数索引是捕获的数字段
        if i % 2 == 1:
            key.append(int(p))
        else:
            key.append(p)
    return key


async def build_cycle_workpapers(
    db: AsyncSession,
    project_id: UUID,
    audit_cycle: str | None,
    current_wp_id: UUID,
) -> list[dict]:
    """查同一审计循环的所有底稿，供 B-Index 跨底稿目录渲染。

    Args:
        db: 异步会话
        project_id: 项目 ID
        audit_cycle: 当前底稿所属审计循环（如 'D'）；为空则返回 []
        current_wp_id: 当前 working_paper.id（用于标注 is_current）

    Returns:
        [{ wp_code, wp_name, wp_id, status, is_current }]，按 wp_code 自然排序。
        wp_id 为 None 表示该底稿尚未生成文件（前端置灰不可跳转）。
        任意异常 → 记 warning 返回 []（降级不阻塞 B-Index 渲染）。
    """
    if not audit_cycle:
        return []

    try:
        # wp_index 左连 working_paper（同 project + 未删），取每个 wp_code 的实体底稿 id
        query = (
            sa.select(
                WpIndex.wp_code,
                WpIndex.wp_name,
                WpIndex.status,
                WorkingPaper.id.label("wp_id"),
            )
            .select_from(WpIndex)
            .outerjoin(
                WorkingPaper,
                sa.and_(
                    WorkingPaper.wp_index_id == WpIndex.id,
                    WorkingPaper.is_deleted == sa.false(),
                ),
            )
            .where(
                WpIndex.project_id == project_id,
                WpIndex.audit_cycle == audit_cycle,
                WpIndex.is_deleted == sa.false(),
            )
        )
        result = await db.execute(query)
        rows = result.all()
    except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
        logger.warning(
            "build_cycle_workpapers 查询失败 project=%s cycle=%s: %s",
            project_id, audit_cycle, e,
        )
        return []

    items: list[dict] = []
    for row in rows:
        wp_id = row.wp_id
        items.append({
            "wp_code": row.wp_code,
            "wp_name": row.wp_name,
            "wp_id": str(wp_id) if wp_id else None,
            "status": getattr(row.status, "value", row.status) if row.status else "",
            "is_current": wp_id is not None and wp_id == current_wp_id,
        })

    # ─── 多文件聚合：已被父码工作包聚合的子码从循环目录隐藏 ─────────────
    # 如 D2 已聚合 D2-2/D2-3/D2-4 等为内部 sheet，
    # 这些子码不应再作为独立底稿出现在跨底稿目录中（避免重复混淆）。
    # 仅隐藏属于该 package primary_wp_code 的子码（D2-N for D2），
    # 不隐藏其他 primary 的底稿（如 D0 函证仍保留为独立条目）。
    aggregated_child_codes: set[str] = set()
    try:
        from app.services.account_package_registry_service import AccountPackageRegistryService
        registry = AccountPackageRegistryService()
        for pkg in registry.get_packages():
            if pkg.get("cycle") != audit_cycle:
                continue
            primary = pkg.get("primary_wp_code", "")
            if not primary:
                continue
            # 从 sheet_name 中提取子码，仅保留属于本 primary 的子码
            # 如 D2 package: "审定表D2-1" → D2-1 (属于 D2), "函证结果汇总表D0-1" → D0-1 (属于 D0, 不隐藏)
            for sheet in pkg.get("sheets", []):
                name = sheet.get("sheet_name", "")
                m = re.search(r"([A-Z]\d+(?:-\d+)+)", name)
                if m:
                    child_code = m.group(1)
                    # 仅当子码以 primary 开头时才隐藏（D2-1 属于 D2，D0-1 不属于 D2）
                    if child_code != primary and child_code.startswith(primary):
                        aggregated_child_codes.add(child_code)
            # source_wp_codes 中属于 primary 的子码也隐藏（如 D2-5/D2-6）
            for src in pkg.get("source_wp_codes", []):
                if src != primary and src.startswith(primary):
                    aggregated_child_codes.add(src)
    except Exception as e:  # noqa: BLE001 — registry 读取失败不影响目录显示
        logger.debug("build_cycle_workpapers: 聚合子码收集失败: %s", e)

    if aggregated_child_codes:
        items = [it for it in items if it["wp_code"] not in aggregated_child_codes]

    items.sort(key=lambda x: _natural_key(x["wp_code"]))
    return items
