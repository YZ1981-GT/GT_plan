"""workpaper_summaries_service — 底稿摘要 API 骨架

GET /api/projects/{pid}/workpaper-summaries/{key}

提供跨底稿摘要数据供 A17/A18 等完成阶段底稿消费。
当前 P1 阶段所有 key 返回 ready=False（数据源未就绪）。

key 列表见 linkage.md §摘要 API 契约。
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


# ── 摘要注册表：key → {source_wp, description} ──

SUMMARY_REGISTRY: dict[str, dict] = {
    "misstatement": {
        "source_wp": ["A13-1", "A13-4"],
        "description": "错报计数、未更正列表",
    },
    "control_deficiency": {
        "source_wp": ["A14-1"],
        "description": "缺陷数、重大/重要分级",
    },
    "going_concern": {
        "source_wp": ["A15-1"],
        "description": "调查结论、疑虑项摘要",
    },
    "governance_communication": {
        "source_wp": ["A10-2"],
        "description": "沟通事项条数（stub）",
    },
    "related_party": {
        "source_wp": ["A7-1"],
        "description": "交易/往来计数",
    },
}


async def get_workpaper_summary(
    db: AsyncSession, project_id: UUID, key: str
) -> dict | None:
    """获取指定 key 的底稿摘要。

    返回:
        dict — 摘要响应（ready=True/False）
        None — key 不在注册表中（调用方应返回 404）
    """
    entry = SUMMARY_REGISTRY.get(key)
    if entry is None:
        return None

    # P1: 所有 key 均返回 ready=False（数据源未实现）
    return {
        "ready": False,
        "key": key,
        "source_wp": entry["source_wp"],
        "reason": "数据源未就绪",
    }
