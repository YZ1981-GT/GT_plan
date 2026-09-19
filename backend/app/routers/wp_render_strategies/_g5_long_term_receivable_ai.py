"""G5 长期应收款 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g5/ai/{section}
G5-9/10 相关 section 待 G4-9/G4-10 完成后启用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g5-ai"])
_AI_TIMEOUT = 30.0


class G5AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G5《长期应收款》审计底稿。
科目1531长期应收款（借方/资产类）。
关注：融资租赁内含利率法、分期销售实际利率法、保理终止确认、ECL减值、凭证核对。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G5-1 审定表审计说明，评价长期应收款各项目变动及主要原因。",
    "adjudication-note": "请生成 G5-1 审定表审计说明，覆盖期初/期末审定、净值与报表列示勾稽及重大变动原因。",
    "adjudication-conclusion": "请生成 G5-1 审定表审计结论，按 A/B/C 口径评价长期应收款审定结果。",
    "detail-note": "请生成 G5-2 余额明细表审计说明，评价债务人明细、账龄勾稽及关联方/长账龄风险。",
    "detail-conclusion": "请生成 G5-2 余额明细表审计结论，按 A/B/C 口径表述程序结果。",
    "baddebt-note": "请生成 G5-3 坏账准备明细表审计说明，评价计提方式、损失率与审定坏账勾稽。",
    "baddebt-conclusion": "请生成 G5-3 坏账准备明细表审计结论，按 A/B/C 口径表述。",
    "adjustment-note": "请生成 G5-4 调整分录汇总审计说明，说明调整依据、事由及回写审定表情况。",
    "adjustment-conclusion": "请生成 G5-4 调整分录汇总审计结论，评价借贷平衡与依据充分性。",
    "lease-amortization-conclusion": "请生成 G5-5 融资租赁测算审计结论，评价内含利率法测算与企业账面差异。",
    "sales-amortization-conclusion": "请生成 G5-6 分期销售测算审计结论，评价实际利率法测算合理性。",
    "factoring-conclusion": "请生成 G5-7 保理核查综合结论，评价终止确认判断适当性。",
    "ecl-policy-eval-1": (
        "请根据 CAS22 生成 G5-8（一）具体减值政策说明的审计评价。"
        "覆盖长期应收款信用风险组合划分依据、单项/组合计提、简化法或一般法选用、损失率确定方法，"
        "并提示与会计政策披露及附注组合名称一致性。"
    ),
    "ecl-policy-eval-2": (
        "请生成 G5-8（二）被审计单位历史坏账损失情况的审计评价。"
        "说明历史损失率数据来源、核实程序、货币时间价值、与当前敞口相关性及需关注风险点。"
    ),
    "ecl-policy-eval-3": (
        "请生成 G5-8（三）前瞻性信息的来源及其影响的审计评价。"
        "覆盖内部模型/第三方/外部专家来源、宏观指标选取、情景权重、对损失率调整及可靠性核查程序。"
    ),
    "ecl-policy-eval-4": (
        "请生成 G5-8（四）同行业公司会计政策对比的审计评价。"
        "基于已有同业披露摘要，评价被审计单位政策合理性、与同业差异及是否一贯执行。"
    ),
    "ecl-policy-conclusion": (
        "请生成 G5-8 信用减值损失会计政策检查综合结论。"
        "明确判断政策是否符合准则、与同业是否重大差异、是否一贯执行；按 A/B/C 口径表述。"
    ),
    "stage-classification-conclusion": "请生成 G5-9 三阶段划分审计结论，评价信用风险显著增加与已减值判断的合理性。",
    "impairment-calc-conclusion": "请生成 G5-10 坏账准备测算审计结论，评价 ECL 计提金额与明细勾稽。",
    "reversal-writeoff-conclusion": "请生成 G5-11 转回核销检查审计结论。",
    "voucher-conclusion": "请生成 G5-12 凭证检查表审计结论。",
    "disclosure-conclusion": "请生成长期应收款附注披露说明文字。",
    "disclosure-listed-note": "请按上市公司附注格式生成长期应收款披露说明文字。",
    "disclosure-soe-note": "请按国企附注格式生成长期应收款披露说明文字。",
}


@router.post("/workpapers/{wp_id}/g5/ai/{section}", response_model=G5AiGenerateResponse)
async def generate_g5_ai(
    wp_id: str,
    section: str,
    body: G5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G5AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G5%' LIMIT 50"
            ),
            {"wp_id": wp_id},
        )
        rows = result.fetchall()
        if rows:
            context_snippet = "\n".join(
                f"{r.item_id}: {(r.remark or '')[:200]}" for r in rows[:10]
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 AI context load failed: %s", e)

    user_prompt = (
        f"{_PROMPTS[section]}\n\n"
        f"已有内容：\n{body.existingContent or '（无）'}\n\n"
        f"相关上下文：\n{context_snippet or str(body.relatedContext)}"
    )

    try:
        content = await asyncio.wait_for(
            chat_completion(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI generation timeout") from None
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 AI failed: %s", e)
        content = f"【AI草稿】{_PROMPTS[section]}"

    return G5AiGenerateResponse(content=content or "", sources=[])
