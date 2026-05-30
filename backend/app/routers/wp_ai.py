"""AI 辅助底稿 API

Phase 9 Task 9.8 + workpaper-editor-slimdown Task 7.2
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_ai_service import WpAIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers", tags=["wp-ai"])


# ─── US-5: LLM 辅助填写 suggest 端点 ─────────────────────────────────────────


class SuggestRequest(BaseModel):
    """AI 建议请求体"""
    sheet_name: str = Field(..., max_length=200)
    field_name: str = Field(..., max_length=200)
    existing_content: str = Field(default="", max_length=5000)


class SuggestResponse(BaseModel):
    """AI 建议响应体"""
    suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)


@router.post("/{wp_id}/ai/suggest", response_model=SuggestResponse)
async def suggest_fill(
    wp_id: UUID,
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """US-5: LLM 辅助填写 — 返回 AI 建议文本（≤2000 字符）

    当 WP_AI_SERVICE_ENABLED=false 时返回 403。
    采纳后前端在保存 payload 中标记 ai_assisted_fields，后端写入审计轨迹。
    """
    if not settings.WP_AI_SERVICE_ENABLED:
        raise HTTPException(status_code=403, detail="AI service disabled")

    # 验证底稿存在
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper
    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 调用 AI service（stub 模式下返回模板建议）
    svc = WpAIService(db)
    result = await svc.suggest_field_content(
        wp_id=wp_id,
        sheet_name=body.sheet_name,
        field_name=body.field_name,
        existing_content=body.existing_content,
    )

    # 截断到 2000 字符
    suggestion_text = (result.get("text") or "")[:2000]
    confidence = float(result.get("confidence", 0.6))

    # 写入审计轨迹
    try:
        from app.services.audit_logger_enhanced import audit_logger
        await audit_logger.log_action(
            user_id=user.id,
            action="workpaper.ai_suggest_requested",
            object_type="workpaper",
            object_id=wp_id,
            project_id=wp.project_id,
            details={
                "sheet_name": body.sheet_name,
                "field_name": body.field_name,
                "suggestion_length": len(suggestion_text),
                "confidence": confidence,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to write audit trail for AI suggest: {e}")

    return SuggestResponse(suggestion=suggestion_text, confidence=confidence)


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


# ─── TSJ 提示词驱动 LLM 复核（wp-tsj-llm-review spec Task 1.1） ───


class TsjReviewItem(BaseModel):
    """单条复核发现"""
    id: str
    content_type: str
    content_text: str
    confidence_level: str | None = None
    confirmation_status: str
    issue_type: str = ""
    severity: str = "medium"
    sheet: str = ""
    cell_range: str = ""
    description: str = ""
    remediation: str = ""


class TsjReviewResponse(BaseModel):
    """TSJ 复核响应"""
    findings: list[TsjReviewItem]
    workpaper_id: str
    audit_cycle: str | None = None


@router.post("/{wp_id}/ai/tsj-review", response_model=TsjReviewResponse)
async def tsj_review(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """TSJ 提示词驱动 LLM 复核 — 调用 review_workpaper_with_prompt

    当 WP_AI_SERVICE_ENABLED=False 时返回 403。
    """
    if not settings.WP_AI_SERVICE_ENABLED:
        raise HTTPException(status_code=403, detail="AI 服务未启用")

    # 验证底稿存在
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 实例化服务并调用复核
    from app.services.workpaper_fill_service import WorkpaperFillService
    from app.services.ai_service import AIService

    svc = WorkpaperFillService(db)
    ai_service = AIService(db)
    results = await svc.review_workpaper_with_prompt(
        project_id=wp.project_id,
        workpaper_id=wp_id,
        ai_service=ai_service,
    )

    # 写入审计轨迹
    try:
        from app.services.audit_logger_enhanced import audit_logger
        await audit_logger.log_action(
            user_id=user.id,
            action="workpaper.tsj_review_requested",
            object_type="workpaper",
            object_id=wp_id,
            project_id=wp.project_id,
            details={
                "findings_count": len(results) if results else 0,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to write audit trail for TSJ review: {e}")

    # 构建响应
    findings = []
    for item in (results or []):
        ds = getattr(item, "data_sources", None) or {}
        description = ds.get("description", "") or getattr(item, "content_text", "")
        remediation = ds.get("remediation", "")
        # content_text 格式: "{description}\n整改建议：{remediation}"
        ct = getattr(item, "content_text", "")
        if not remediation and "\n整改建议：" in ct:
            parts = ct.split("\n整改建议：", 1)
            description = parts[0]
            remediation = parts[1] if len(parts) > 1 else ""
        elif not description:
            description = ct

        findings.append(TsjReviewItem(
            id=str(getattr(item, "id", "")),
            content_type=str(getattr(item, "content_type", "risk_alert")),
            content_text=ct,
            confidence_level=str(getattr(item, "confidence_level", None) or ""),
            confirmation_status=str(
                getattr(item, "confirmation_status", "pending") or "pending"
            ),
            issue_type=ds.get("issue_type", ""),
            severity=ds.get("severity", "medium"),
            sheet=ds.get("sheet", ""),
            cell_range=ds.get("cell_range", ""),
            description=description,
            remediation=remediation,
        ))

    # 获取 audit_cycle 信息
    audit_cycle = None
    if results and hasattr(results[0], "data_sources"):
        ds = getattr(results[0], "data_sources", None)
        if isinstance(ds, dict):
            audit_cycle = ds.get("audit_cycle")

    return TsjReviewResponse(
        findings=findings,
        workpaper_id=str(wp_id),
        audit_cycle=audit_cycle,
    )
