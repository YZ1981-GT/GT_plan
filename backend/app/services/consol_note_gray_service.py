"""合并附注 V2 灰度按项目服务（consol-disclosure-note-persistence Req3/Req5）。

统一入口 `is_consol_note_v2_enabled(db, project_id)`：
- 全局 `settings.CONSOL_NOTES_V2_ENABLED=True` → True（向后兼容全开，不查项目级）
- 否则查 `project.wizard_state.consol_notes_v2_enabled`（项目级 opt-in，默认 False）
- 异常 fail-open 返 False（绝不误开）

照抄 `note_formula_gray_service.is_note_formula_enabled` 范式：
既有单测 monkeypatch 全局开关=True 时短路返 True → 零回归兼容。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def is_consol_note_v2_enabled(db: AsyncSession, project_id: UUID) -> bool:
    """判定指定项目是否启用合并附注 V2（生成 + 落库穿透）。

    优先级：
    1. 全局 settings.CONSOL_NOTES_V2_ENABLED=True → True（向后兼容全开，不查项目级）
    2. 否则查 project.wizard_state.consol_notes_v2_enabled（项目级 opt-in）
    3. 任何异常 fail-open 返 False（关闭态，绝不误开）
    """
    try:
        from app.core.config import settings

        # 全局开关 True → 直接全开（向后兼容，不查项目级）
        if getattr(settings, "CONSOL_NOTES_V2_ENABLED", False) is True:
            return True

        # 全局关 → 查项目级 opt-in
        from app.models.core import Project

        result = await db.execute(
            sa.select(Project.wizard_state).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        row = result.first()
        if row is None:
            return False

        wizard_state = row[0]
        if not isinstance(wizard_state, dict):
            return False

        return bool(wizard_state.get("consol_notes_v2_enabled", False))

    except Exception as exc:
        # fail-open 返 False（关闭态，绝不误开）
        logger.warning(
            "is_consol_note_v2_enabled fail-open: project_id=%s error=%s",
            project_id,
            exc,
        )
        return False
