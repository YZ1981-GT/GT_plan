"""a18_regulatory — A18 监管沟通函辅助路由

GET /api/projects/{project_id}/a18/suggestions
返回 issue_hints + A8 步骤建议，供 GtRegulatoryLetter 前端消费。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.issue_hints_service import get_issue_hints
from app.services.regulatory_letter_service import get_a8_step_suggestion
from app.services.a18_summary_generator import generate_audit_summary

router = APIRouter(prefix="/api/projects", tags=["a18-regulatory"])


@router.get("/{project_id}/a18/suggestions")
async def get_a18_suggestions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取 A18-2 议题填写建议（issue_hints + A8 步骤映射）"""
    hints = await get_issue_hints(db, project_id)
    a8 = await get_a8_step_suggestion(db, project_id)
    return {
        "issue_hints": hints,
        "a8_suggestion": a8,
    }


@router.get("/{project_id}/a18/generate-summary")
async def get_a18_generated_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """从 A17-1 章节生成 A18-1 审计小结框架（P2，依赖 A17-core）"""
    return await generate_audit_summary(db, project_id)
