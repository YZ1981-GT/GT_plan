"""F 采购存货循环 — 存货监盘 LLM 差异分析 API

POST /api/projects/{project_id}/workpapers/{wp_id}/ai/stocktake-summary

复用 wp_ai_service._execute_llm_with_mask + mask_context 脱敏。
当前为 stub 实现（真实 LLM 集成已在 wp_ai_service 中就绪，
此端点仅做 prompt 组装 + 调用 + 解析）。

对应 spec：workpaper-f-purchase-inventory F-F5（监盘弹窗 LLM 差异分析）
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/ai",
    tags=["wp-ai-stocktake"],
)


class StocktakeDiffItem(BaseModel):
    """监盘差异行项目"""

    itemName: str = Field("", description="存货品名")
    bookQty: float = Field(0.0, description="账面数量")
    actualQty: float = Field(0.0, description="实盘数量")
    reason: str = Field("", description="差异原因/说明")


class StocktakeSummaryRequest(BaseModel):
    """监盘差异分析请求体"""

    differences: list[StocktakeDiffItem] = Field(
        default_factory=list, description="盘点差异记录列表"
    )
    conclusion: str = Field("", description="当前已填写的监盘结论（可空）")


class StocktakeSummaryResponse(BaseModel):
    """监盘差异分析响应"""

    summary: str
    risk_alerts: list[str]


def _format_differences(diffs: list[StocktakeDiffItem]) -> str:
    """将差异行格式化为 LLM prompt 可读文本"""
    if not diffs:
        return "（无差异行）"
    lines: list[str] = []
    for i, d in enumerate(diffs, 1):
        diff_qty = (d.actualQty or 0) - (d.bookQty or 0)
        lines.append(
            f"{i}. 品名={d.itemName or '-'}, 账面={d.bookQty}, 实盘={d.actualQty}, "
            f"差异={diff_qty:+.2f}, 原因={d.reason or '-'}"
        )
    return "\n".join(lines)


def _parse_stocktake_summary(
    ai_text: str, original_diffs: list[StocktakeDiffItem]
) -> tuple[str, list[str]]:
    """解析 LLM 输出为结构化摘要

    尝试从 LLM 输出中提取摘要 + 风险提示两部分。
    解析失败时返回原始文本作为摘要。
    """
    if not ai_text or ai_text.startswith("["):
        # fallback 或空输出
        n = len(original_diffs)
        return (
            f"[监盘差异摘要待人工填写] 差异行数: {n}",
            [],
        )

    lines = ai_text.strip().split("\n")
    summary_lines: list[str] = []
    alerts: list[str] = []

    section = "summary"
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "风险提示" in stripped or "风险" in stripped and "：" in stripped:
            section = "alerts"
            continue
        if "摘要" in stripped and stripped.endswith(("：", ":")):
            section = "summary"
            continue

        clean = stripped.lstrip("0123456789.-、）) ·•")

        if section == "summary":
            summary_lines.append(stripped)
        elif section == "alerts":
            if clean:
                alerts.append(clean)

    summary = "\n".join(summary_lines) if summary_lines else ai_text[:500]
    return summary, alerts


@router.post("/stocktake-summary", response_model=StocktakeSummaryResponse)
async def stocktake_summary(
    project_id: UUID,
    wp_id: UUID,
    body: StocktakeSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """LLM 生成存货监盘差异分析摘要

    基于盘点差异记录表生成结构化分析，包含：
    - summary：监盘差异分析摘要（200~400 字，覆盖差异成因/合理性/调整建议）
    - risk_alerts：基于差异分布给出的审计风险提示列表

    对应 requirements.md F-F5.4：
    > WHEN 盘点差异记录填写完成后，系统 SHALL 提供 LLM 辅助生成监盘差异分析摘要
    """
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa

    # 验证底稿存在
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not wp:
        raise HTTPException(404, "底稿不存在")

    if not body.differences and not body.conclusion.strip():
        raise HTTPException(400, "差异记录和当前结论不能同时为空")

    # 调用 LLM 生成摘要（复用 wp_ai_service 的脱敏 + LLM 调用机制）
    from app.services.wp_ai_service import WpAIService

    svc = WpAIService(db)
    diff_text = _format_differences(body.differences)

    try:
        result = await svc._execute_llm_with_mask(
            system_prompt=(
                "你是审计专家，请根据存货监盘差异记录生成结构化监盘分析。"
                "输出格式（必须分两段，每段以小标题开头）：\n"
                "1. 摘要：（300字以内，概括差异规模/分布/合理性/调整建议）\n"
                "2. 风险提示：（逐条列出基于差异给出的审计风险提示，每条独占一行）"
            ),
            user_prompt=(
                f"盘点差异明细：\n{diff_text}\n\n"
                f"当前已填结论（如有）：\n{body.conclusion or '（空）'}"
            ),
            scenario="stocktake_summary",
        )
        ai_text = result.get("content", "") or result.get("value", "")
        summary, alerts = _parse_stocktake_summary(ai_text, body.differences)
    except Exception:
        # LLM 调用失败时返回 placeholder
        summary = f"[监盘差异摘要待人工填写] 差异行数: {len(body.differences)}"
        alerts = []

    return StocktakeSummaryResponse(
        summary=summary,
        risk_alerts=alerts,
    )
