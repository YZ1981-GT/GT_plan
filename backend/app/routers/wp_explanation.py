"""审计说明智能生成 API 路由

Phase 12 P1-1:
- POST /generate-explanation  生成草稿
- POST /confirm-explanation   确认写回
- POST /refine-explanation    优化草稿
- POST /review-content        AI预审
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.schemas.phase12_schemas import (
    ConfirmDraftRequest,
    ConfirmDraftResponse,
    GenerateDraftRequest,
    GenerateDraftResponse,
    RefineDraftRequest,
    ReviewContentResponse,
)

router = APIRouter(prefix="/api/projects/{project_id}/wp-ai")


@router.post("/{wp_id}/generate-explanation")
async def generate_explanation(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成审计说明草稿"""
    from app.services.wp_explanation_service import WpExplanationService

    svc = WpExplanationService(db)
    # 从项目获取审计年度
    try:
        from app.models.core import Project
        proj_result = await db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        proj = proj_result.scalar_one_or_none()
        audit_year = 2025  # 默认值
        if proj and proj.wizard_state:
            steps = proj.wizard_state.get("steps", {})
            basic = steps.get("basic_info", {}).get("data", {})
            audit_year = basic.get("audit_year", 2025)
    except Exception:
        audit_year = 2025

    result = await svc.generate_draft(
        project_id=project_id,
        year=audit_year,
        wp_id=wp_id,
        user_id=current_user.id,
    )
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{wp_id}/confirm-explanation")
async def confirm_explanation(
    project_id: UUID,
    wp_id: UUID,
    body: ConfirmDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """确认审计说明并写回工作簿"""
    from app.services.wp_explanation_service import WpExplanationService

    svc = WpExplanationService(db)
    result = await svc.confirm_draft(
        wp_id=wp_id,
        generation_id=body.generation_id,
        final_text=body.final_text,
        user_id=current_user.id,
    )
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{wp_id}/refine-explanation")
async def refine_explanation(
    project_id: UUID,
    wp_id: UUID,
    body: RefineDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于用户修改优化草稿"""
    from app.services.wp_explanation_service import WpExplanationService

    svc = WpExplanationService(db)
    result = await svc.refine_draft(
        wp_id=wp_id,
        generation_id=body.generation_id,
        user_edits=body.user_edits,
        feedback=body.feedback,
    )
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{wp_id}/review-content")
async def review_content(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI预审底稿内容"""
    from app.services.wp_ai_service import WpAIService

    svc = WpAIService(db)
    # 复用已有的 check_wp_report_consistency 并扩展
    issues = []

    # 数据一致性检查
    from app.models.workpaper_models import WorkingPaper
    from app.models.audit_platform_models import TrialBalance
    import sqlalchemy as sa

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()

    if wp and wp.parsed_data:
        pd = wp.parsed_data
        wp_amount = pd.get("audited_amount")
        explanation = pd.get("audit_explanation", "")

        # 检查说明完整性
        if not explanation or len(explanation) < 50:
            issues.append({
                "description": "审计说明不完整（少于50字）",
                "severity": "warning",
                "suggested_action": "补充审计说明，建议使用AI生成功能",
            })

        # 检查结论
        if not pd.get("conclusion"):
            issues.append({
                "description": "审计结论为空",
                "severity": "blocking",
                "suggested_action": "填写审计结论",
            })

    return {"issues": issues}
