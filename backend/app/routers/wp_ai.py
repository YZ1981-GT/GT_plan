"""AI 辅助底稿 API

Phase 9 Task 9.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_ai_service import WpAIService

router = APIRouter(prefix="/api/workpapers", tags=["wp-ai"])


@router.post("/{wp_id}/ai/analytical-review")
async def analytical_review(
    wp_id: UUID,
    account_code: str = Query(...),
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    wp = (await db.execute(
        __import__("sqlalchemy").select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.analytical_review(wp.project_id, account_code, year)


@router.post("/{wp_id}/ai/extract-confirmations")
async def extract_confirmations(
    wp_id: UUID,
    account_code: str = Query(...),
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa
    wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_id))).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.extract_confirmations(wp.project_id, account_code, year)


@router.post("/{wp_id}/ai/check-consistency")
async def check_consistency(
    wp_id: UUID,
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa
    wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_id))).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.check_wp_report_consistency(wp.project_id, year)


# ─── E1 Sprint 2: 4 个审计说明 prompt 端点（前端 AiConclusionButton 调用） ───

from pydantic import BaseModel


class AiConclusionRequest(BaseModel):
    sheet_key: str | None = None
    context: dict | None = None


def _wp_or_404(db, wp_id):
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    return db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )


@router.post("/{wp_id}/ai/audit-conclusion")
async def ai_audit_conclusion(
    wp_id: UUID,
    payload: AiConclusionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """E1 spec F6.3 场景 1：审计说明生成"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    ctx = payload.context or {}
    svc = WpAIService(db)
    out = await svc.generate_audit_conclusion(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
        company_name=ctx.get("company_name", ""),
        audited_amount=float(ctx.get("audited_amount") or 0),
        prior_amount=float(ctx.get("prior_amount") or 0),
        period_change=float(ctx.get("period_change") or 0),
        change_rate=float(ctx.get("change_rate") or 0),
        aje_total=float(ctx.get("aje_total") or 0),
        rje_total=float(ctx.get("rje_total") or 0),
        anomalies=str(ctx.get("anomalies") or "无"),
    )
    return out


@router.post("/{wp_id}/ai/variance-analysis")
async def ai_variance_analysis(
    wp_id: UUID,
    payload: AiConclusionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """E1 spec F6.3 场景 2：差异原因分析（同时用于 WorkpaperAuditNav 关键风险提示）"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    ctx = payload.context or {}
    svc = WpAIService(db)
    out = await svc.generate_variance_analysis(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
        company_name=ctx.get("company_name", ""),
        diff_amount=float(ctx.get("diff_amount") or 0),
        diff_direction=str(ctx.get("diff_direction") or ""),
        bank_name=str(ctx.get("bank_name") or ""),
        materiality_level=float(ctx.get("materiality_level") or 0),
    )
    return out


@router.post("/{wp_id}/ai/check-conclusion")
async def ai_check_conclusion(
    wp_id: UUID,
    payload: AiConclusionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """E1 spec F6.3 场景 3：检查清单结论"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    ctx = payload.context or {}
    items = ctx.get("items") or []
    passed = sum(1 for i in items if (i or {}).get("verified"))
    total = len(items)
    svc = WpAIService(db)
    out = await svc.generate_check_conclusion(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
        check_type=str(ctx.get("check_type") or "检查清单"),
        check_scope=str(ctx.get("check_scope") or ""),
        passed_count=int(ctx.get("passed_count") or passed),
        total_count=int(ctx.get("total_count") or total),
        exceptions=str(ctx.get("exceptions") or "无"),
        attachment_count=int(ctx.get("attachment_count") or 0),
    )
    return out


@router.post("/{wp_id}/ai/cutoff-conclusion")
async def ai_cutoff_conclusion(
    wp_id: UUID,
    payload: AiConclusionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """E1 spec F6.3 场景 4：截止测试结论"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    ctx = payload.context or {}
    items = ctx.get("items") or []
    issues = sum(1 for i in items if (i or {}).get("period_correct") is False)
    svc = WpAIService(db)
    out = await svc.generate_cutoff_conclusion(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
        cutoff_date=str(ctx.get("cutoff_date") or ""),
        days_before=int(ctx.get("days_before") or 5),
        days_after=int(ctx.get("days_after") or 5),
        sample_count=int(ctx.get("sample_count") or len(items)),
        amount_range=str(ctx.get("amount_range") or ""),
        issues_count=int(ctx.get("issues_count") or issues),
    )
    return out


# ─── E1 Sprint 2 Task 2.22 + 2.23: 复核问题生成 + 复核回复辅助 ───


class ReviewQuestionsRequest(BaseModel):
    review_layer: str = "L3"
    target_sheet: str | None = None


class ReviewReplyRequest(BaseModel):
    review_record_id: str | None = None
    question: str
    target_sheet: str | None = None


@router.post("/{wp_id}/ai/review-questions")
async def ai_review_questions(
    wp_id: UUID,
    payload: ReviewQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Task 2.22: 合伙人打开复核模板时一键生成"建议关注问题清单"。

    复用 generate_audit_conclusion 但 prompt 维度为"风险关注 + 异常项"。
    输出格式: { questions: [{title, cell?, severity, rationale}], summary }
    """
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    svc = WpAIService(db)
    # 复用 audit_conclusion prompt 的 LLM 调用基础设施
    base = await svc.generate_audit_conclusion(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
        anomalies="基于风险关注点列出建议",
    )
    text = (base or {}).get("content") or ""
    # 简化：将文本切分为问题清单
    lines = [ln.strip(" -·•").strip() for ln in text.split("\n") if ln.strip()]
    questions = [
        {
            "title": ln,
            "cell": None,
            "severity": "medium",
            "rationale": "基于 E1 数据 LLM 自动生成",
            "review_layer": payload.review_layer,
        }
        for ln in lines[:10]
    ]
    return {
        "questions": questions,
        "summary": text,
        "wp_code": wp_index.wp_code,
        "review_layer": payload.review_layer,
    }


@router.post("/{wp_id}/ai/review-reply")
async def ai_review_reply(
    wp_id: UUID,
    payload: ReviewReplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Task 2.23: 审计助理收到问题后 LLM 基于底稿+序时账草拟回复。

    输出: { reply: str, evidence_refs: [{type, ref}] }
    """
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from fastapi import HTTPException

    res = (await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id)
    )).first()
    if not res:
        raise HTTPException(404, "底稿不存在")
    wp, wp_index = res
    svc = WpAIService(db)
    # 复用 variance_analysis prompt 来生成回复
    base = await svc.generate_variance_analysis(
        project_id=wp.project_id,
        wp_code=wp_index.wp_code,
        year=getattr(wp, "year", None) or 2025,
    )
    text = (base or {}).get("content") or ""
    return {
        "reply": f"针对问题「{payload.question[:60]}」的回复草稿：\n\n{text}",
        "evidence_refs": [],
        "wp_code": wp_index.wp_code,
    }
