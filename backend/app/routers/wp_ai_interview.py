"""D 循环客户访谈 LLM 摘要 API

POST /api/projects/{project_id}/workpapers/{wp_id}/ai/interview-summary

复用 wp_ai_service._execute_llm_with_mask + mask_context 脱敏。
当前为 stub 实现（真实 LLM 集成已在 wp_ai_service 中就绪，
此端点仅做 prompt 组装 + 调用）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/ai",
    tags=["wp-ai-interview"],
)


class InterviewSummaryRequest(BaseModel):
    """客户访谈摘要请求体"""
    transcript: str
    audio_recording_uuid: str | None = None


class InterviewSummaryResponse(BaseModel):
    """客户访谈摘要响应"""
    summary: str
    issues_found: list[str]
    risk_alerts: list[str]


@router.post("/interview-summary", response_model=InterviewSummaryResponse)
async def interview_summary(
    project_id: UUID,
    wp_id: UUID,
    body: InterviewSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """LLM 生成客户访谈摘要

    基于访谈记录文本（transcript）生成结构化摘要，
    包含：摘要文本 + 发现问题列表 + 风险提示列表。

    复用 wp_ai_service.analytical_review 的 mask_context 脱敏机制。
    """
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa

    # 验证底稿存在
    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(404, "底稿不存在")

    if not body.transcript or not body.transcript.strip():
        raise HTTPException(400, "访谈记录不能为空")

    # 调用 LLM 生成摘要（复用 wp_ai_service 的脱敏 + LLM 调用机制）
    from app.services.wp_ai_service import WpAIService

    svc = WpAIService(db)
    try:
        result = await svc._execute_llm_with_mask(
            system_prompt=(
                "你是审计专家，请根据以下客户访谈记录生成结构化摘要。"
                "输出格式：\n"
                "1. 摘要（200字以内，概括访谈要点）\n"
                "2. 发现问题（逐条列出访谈中发现的异常或风险点）\n"
                "3. 风险提示（基于访谈内容给出审计风险提示）"
            ),
            user_prompt=f"客户访谈记录：\n{body.transcript}",
            scenario="interview_summary",
        )
        # 解析 LLM 输出为结构化响应
        ai_text = result.get("content", "") or result.get("value", "")
        summary, issues, alerts = _parse_interview_summary(ai_text, body.transcript)
    except Exception:
        # LLM 调用失败时返回 placeholder
        summary = f"[访谈摘要待人工填写] 访谈记录长度: {len(body.transcript)} 字"
        issues = []
        alerts = []

    return InterviewSummaryResponse(
        summary=summary,
        issues_found=issues,
        risk_alerts=alerts,
    )


def _parse_interview_summary(
    ai_text: str, original_transcript: str
) -> tuple[str, list[str], list[str]]:
    """解析 LLM 输出为结构化摘要

    尝试从 LLM 输出中提取摘要/问题/风险三部分。
    如果解析失败，返回原始文本作为摘要。
    """
    if not ai_text or ai_text.startswith("["):
        # fallback 或空输出
        return (
            f"[访谈摘要待人工填写] 原始记录: {original_transcript[:200]}...",
            [],
            [],
        )

    lines = ai_text.strip().split("\n")
    summary_lines: list[str] = []
    issues: list[str] = []
    alerts: list[str] = []

    section = "summary"
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if "发现问题" in lower or "问题" in lower and "：" in stripped:
            section = "issues"
            continue
        if "风险提示" in lower or "风险" in lower and "：" in stripped:
            section = "alerts"
            continue

        # Remove bullet markers
        clean = stripped.lstrip("0123456789.-、）) ·•")

        if section == "summary":
            summary_lines.append(stripped)
        elif section == "issues":
            if clean:
                issues.append(clean)
        elif section == "alerts":
            if clean:
                alerts.append(clean)

    summary = "\n".join(summary_lines) if summary_lines else ai_text[:500]
    return summary, issues, alerts
