"""附注公式灰度按项目服务。

统一入口 `is_note_formula_enabled(db, project_id)`：
- 全局 `settings.DISCLOSURE_NOTE_FORMULA_ENABLED=True` → True（向后兼容全开）
- 否则查 `project.wizard_state.disclosure_note_formula_enabled`（项目级 override，默认 False）
- 异常 fail-open 返 False（绝不误开）

Validates: Requirements 5.1, 5.3, 5.4, 6.1
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def is_note_formula_enabled(db: AsyncSession, project_id: UUID) -> bool:
    """判定指定项目是否启用附注表内公式求值。

    优先级：
    1. 全局 settings.DISCLOSURE_NOTE_FORMULA_ENABLED=True → True（向后兼容全开）
    2. 否则查 project.wizard_state.disclosure_note_formula_enabled（项目级 override）
    3. 任何异常 fail-open 返 False（关闭态，绝不误开）
    """
    try:
        from app.core.config import settings

        # 全局开关 True → 直接全开（向后兼容，不查项目级）
        if getattr(settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False) is True:
            return True

        # 全局关 → 查项目级 override
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

        return bool(wizard_state.get("disclosure_note_formula_enabled", False))

    except Exception as exc:
        # fail-open 返 False（关闭态，绝不误开）
        logger.warning(
            "is_note_formula_enabled fail-open: project_id=%s error=%s",
            project_id,
            exc,
        )
        return False
