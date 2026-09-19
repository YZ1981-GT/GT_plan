"""AI 结论保存校验器

Task 3.4, 3.5 (workpaper-ai-conclusion-copilot spec):
- 后端保存 D1-C / D2-C 结论时校验 AI log 状态
- 校验 AI log 的目标绑定与当前结论字段一致
- pending → 拒绝保存
- confirmed/revised → 允许保存
- rejected → 不得将 AI 草稿写入正式结论

Requirements: 2.1, 4.5
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import AiContentLog


class ConclusionSaveBlockedError(Exception):
    """保存正式结论被阻断（存在 pending AI 草稿）"""

    def __init__(self, message: str, pending_log_ids: list[str] | None = None):
        super().__init__(message)
        self.pending_log_ids = pending_log_ids or []


async def validate_conclusion_save(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    field_id: str,
) -> None:
    """校验保存正式结论前 AI log 状态

    规则：
    - 如果存在 pending 状态的 AI log 指向同一 wp_id + field_id，阻断保存
    - confirmed/revised 允许保存
    - rejected 允许手动保存（用户自行写结论）

    Raises:
        ConclusionSaveBlockedError: 存在 pending AI 草稿时抛出
    """
    # 查找指向该 wp_id 且状态为 pending 的 AI log
    # target_cell 格式: "workpaper:<wp_id>:<field_id>"
    target_pattern = f"workpaper:{wp_id}:{field_id}"

    stmt = (
        select(AiContentLog)
        .where(
            AiContentLog.project_id == project_id,
            AiContentLog.confirm_action == "pending",
            AiContentLog.wp_id == wp_id,
        )
    )

    result = await db.execute(stmt)
    pending_logs = result.scalars().all()

    # 过滤匹配当前 field_id 的 pending 记录
    blocking_logs = []
    for log in pending_logs:
        target_cell = log.target_cell or ""
        # target_cell 可能为 "workpaper:<wp_id>:<field_id>" 格式
        if field_id in target_cell:
            blocking_logs.append(log)

    if blocking_logs:
        log_ids = [str(log.id) for log in blocking_logs]
        raise ConclusionSaveBlockedError(
            f"存在 {len(blocking_logs)} 条 pending AI 草稿指向该结论字段，"
            f"请先确认或拒绝后再保存正式结论",
            pending_log_ids=log_ids,
        )


async def validate_rejected_draft_not_used(
    *,
    db: AsyncSession,
    log_id: uuid.UUID,
    conclusion_content: str,
) -> bool:
    """校验被拒绝的草稿不得进入正式结论

    规则：
    - 如果 AI log 状态为 rejected，且 conclusion_content 与 generated_content 完全相同
      → 不允许（返回 False）
    - 其他情况 → 允许（返回 True）

    Returns:
        True: 允许保存
        False: 被拒绝的 AI 草稿内容不得直接进入正式结论
    """
    stmt = select(AiContentLog).where(AiContentLog.id == log_id)
    result = await db.execute(stmt)
    ai_log = result.scalar_one_or_none()

    if ai_log is None:
        return True

    # 被拒绝的草稿内容不得直接复制到正式结论
    if ai_log.confirm_action == "rejected":
        if ai_log.generated_content == conclusion_content:
            return False

    return True
