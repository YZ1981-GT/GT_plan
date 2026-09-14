"""G8 其他权益工具投资 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g8/ai/{section}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g8-ai"])

_SYSTEM = """你是一位资深注册会计师，协助编制 G8《其他权益工具投资》审计底稿。
科目1503其他权益工具投资（借方/资产类），关注 FVOCI 指定适当性(CAS22)、公允价值三层次测试与 OCI 核算。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G8-1 审定表审计说明，分析期初期末变动及公允价值计量合理性。",
    "adjudication-note": "请生成 G8-1 审定表审计说明，概述程序执行情况、重大变动原因及与试算表/明细表勾稽结果。",
    "adjudication-conclusion": "请生成 G8-1 审定表审计结论，按 A/B/C 口径评价科目1503审定数准确性与 OCI 分类恰当性。",
    "detail-note": "请生成 G8-2 明细表审计说明，概述各被投资单位成本、公允价值及 OCI 变动核对情况。",
    "detail-conclusion": "请生成 G8-2 明细表审计结论，评价明细完整性、准确性及与 G8-1 勾稽一致性。",
    "adjustment-note": "请生成 G8-3 调整分录审计说明，概述 AJE/RJE 依据及对 OCI/留存收益的影响。",
    "adjustment-conclusion": "请生成 G8-3 调整分录审计结论，评价分录恰当性、借贷平衡及回写审定表情况。",
    "fair-value-note": "请生成 G8-4 公允价值测试审计说明，概述层次划分依据、取数来源及 Level3 估值核实情况。",
    "fair-value-conclusion": "请根据 G8-4 公允价值测试表，生成公允价值计量审计结论（含 Level1-3 层次分析）。",
    "designation-note": "请生成 G8-5 指定适当性检查审计说明，概述按被投资单位矩阵核查 CAS22 非交易性/FVOCI 指定条件的执行情况、与 G8-2/G8-4 勾稽结果及异常事项。",
    "designation-conclusion": "请根据 G8-5 按被投资单位指定适当性矩阵，生成非交易性权益工具指定 FVOCI 是否恰当的审计结论（A/B/C 口径）。",
    "voucher-note": "请生成 G8-6 凭证检查审计说明，概述抽样方法、样本量及逐笔核对发现的异常事项。",
    "voucher-conclusion": "请根据 G8-6 凭证检查表异常样本，生成凭证测试结论。",
    "disclosure-section": "请为 G8 附注披露单行项目生成专业附注文本（科目1503其他权益工具投资）。",
    "disclosure-listed-note": "请生成 G8 附注披露（上市公司格式）审计说明，概述披露项目、金额与公允价值层次核对及与审定表勾稽结果。",
    "disclosure-soe-note": "请生成 G8 附注披露（国有企业格式）审计说明，概述披露项目、金额与 OCI 相关披露核对及与审定表勾稽结果。",
    "disclosure-conclusion": "请生成 G8 附注披露审计结论，评价披露完整性、准确性及是否符合企业会计准则与监管要求。",
}


class G8AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G8AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


def _summarize_voucher_abnormal_rows(rows: list[dict[str, Any]], *, limit: int = 30) -> str:
    """将 G8-6 异常行压缩为 AI 可用的短摘要。"""
    if not rows:
        return ""
    lines: list[str] = []
    for i, row in enumerate(rows[:limit]):
        voucher = str(row.get("voucherNo") or "").strip() or f"行{i + 1}"
        investee = str(row.get("investeeName") or "").strip()
        abn_type = str(row.get("abnormalType") or "").strip() or "unknown"
        desc = str(row.get("abnormalDesc") or row.get("businessContent") or "").strip()
        debit = row.get("debitAmount")
        credit = row.get("creditAmount")
        checks = []
        for label, key in (
            ("原始", "check1OriginalComplete"),
            ("授权", "check2Authorization"),
            ("账务", "check3Accounting"),
            ("公允", "check4FairValueCorrect"),
            ("OCI", "check5OCICorrect"),
        ):
            v = row.get(key)
            if v is False:
                checks.append(f"{label}=不通过")
            elif v is None or v == "":
                checks.append(f"{label}=未测")
        amt = ""
        try:
            d = abs(float(debit or 0))
            c = abs(float(credit or 0))
            if d or c:
                amt = f"借{d:.2f}/贷{c:.2f}"
        except (TypeError, ValueError):
            amt = ""
        parts = [f"{i + 1}. 凭证{voucher}", f"类型={abn_type}"]
        if investee:
            parts.append(investee)
        if amt:
            parts.append(amt)
        if checks:
            parts.append("核对:" + ",".join(checks))
        if desc:
            parts.append(desc[:120])
        lines.append("｜".join(parts))
    if len(rows) > limit:
        lines.append(f"…另有 {len(rows) - limit} 笔未列入摘要")
    return "\n".join(lines)


@router.post("/api/workpapers/{wp_id}/g8/ai/{section}", response_model=G8AiGenerateResponse)
async def generate_g8_ai(
    wp_id: str,
    section: str,
    body: G8AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G8AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown G8 AI section: {section}")
    prompt = _PROMPTS[section]
    if section == "disclosure-section":
        label = body.relatedContext.get("label", "")
        if label:
            prompt += f"\n\n项目：{label}"
        if body.relatedContext.get("currentAmount") is not None:
            prompt += f"\n本期金额：{body.relatedContext.get('currentAmount')}"
        if body.relatedContext.get("priorAmount") is not None:
            prompt += f"\n上期金额：{body.relatedContext.get('priorAmount')}"
    if section in ("voucher-conclusion", "voucher-note") and body.rows:
        summary = _summarize_voucher_abnormal_rows(body.rows)
        if summary:
            prompt += f"\n\n异常/样本摘要（共 {len(body.rows)} 笔）：\n{summary}"
        if body.relatedContext:
            ctx_bits = [f"{k}={v}" for k, v in list(body.relatedContext.items())[:12]]
            if ctx_bits:
                prompt += "\n\n相关上下文：" + "；".join(ctx_bits)
    elif body.rows and section.endswith("-conclusion"):
        # 其他结论类：给少量行上下文，避免 prompt 过长
        preview = body.rows[:8]
        prompt += f"\n\n相关行数：{len(body.rows)}；预览：{preview!s}"[:1500]
    if body.existingContent:
        prompt += f"\n\n已有内容：{body.existingContent[:2000]}"
    try:
        content = await chat_completion(
            system=_SYSTEM,
            user=prompt,
            db=db,
            wp_id=wp_id,
            feature=f"g8-ai-{section}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G8 AI %s failed: %s", section, e)
        content = f"【G8 {section} 审计结论占位】请结合 G8 底稿数据补充专业结论。（AI 暂不可用）"
    return G8AiGenerateResponse(content=content or "", sources=[f"g8/{section}"])
