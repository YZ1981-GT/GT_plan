"""G10 交易性金融负债 — AI 辅助端点.

POST /api/workpapers/{wp_id}/g10/ai/{section}
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

router = APIRouter(tags=["g10-ai"])
_AI_TIMEOUT = 30.0


class G10AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    variant: str = ""


class G10AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM = """你是一位资深注册会计师，协助编制 G10《交易性金融负债》审计底稿。
科目2101交易性金融负债（贷方/负债类），关注公允价值计量、分类适当性、衍生工具核查与凭证测试结论。
输出：中文、审计专业用语、简洁适合底稿。"""

_PROMPTS = {
    "adjudication-analysis": "请生成 G10-1 审定表审计说明，分析各负债项目期初期末变动及主要原因。",
    "adjudication-note": "请生成 G10-1 审定表审计说明，概述程序执行情况、重大变动原因及与试算表/明细表勾稽结果。",
    "adjudication-conclusion": "请生成 G10-1 审定表审计结论，按 A/B/C 口径评价科目2101审定数准确性与列报正确性。",
    "detail-note": "请生成 G10-2 明细表审计说明，概述各负债项目核实、公允价值变动计入损益验证及与审定表勾稽情况。",
    "detail-conclusion": "请生成 G10-2 明细表审计结论，评价明细完整性、准确性及与 G10-1 勾稽一致性。",
    "adjustment-note": "请生成 G10-3 调整分录审计说明，概述 AJE/RJE 依据、借贷平衡核对及回写审定表影响。",
    "adjustment-conclusion": "请生成 G10-3 调整分录审计结论，评价分录恰当性、借贷平衡及回写审定表情况。",
    "classification-note": "请生成 G10-4 分类适当性检查审计说明，概述 CAS22/37 分类条件矩阵核查、与 G10-2 勾稽及未勾选依据项目的核查情况。",
    "classification-conclusion": "请根据 G10-4 分类适当性检查表（各负债项目交易性/初始指定依据勾选），生成综合审计结论（A/B/C 口径）。",
    "fair-value-note": "请生成 G10-5 公允价值测试审计说明，概述层次划分依据、估值来源及 Level3 输入值核实情况。",
    "fair-value-conclusion": "请根据 G10-5 公允价值测试表，生成公允价值计量审计结论。",
    "l3-note": "请生成 G10-6 第三层次调节表审计说明，概述期初至期末调节核实、层次转入转出原因及差异核查结果。",
    "l3-conclusion": "请生成 G10-6 第三层次调节表审计结论，评价调节完整性、准确性及与 G10-5 勾稽一致性。",
    "derivative-note": "请生成 G10-8 衍生金融工具核查审计说明，概述五要素核查、嵌入衍生拆分、公允价值及套期关系测试情况。",
    "derivative-conclusion": "请根据 G10-8 衍生金融工具核查问卷，生成衍生工具审计结论。",
    "voucher-note": "请生成 G10-7 凭证检查审计说明，概述抽样方法、样本量及逐笔核对发现的异常事项。",
    "voucher-conclusion": "请根据 G10-7 凭证检查表异常样本，生成凭证测试结论。",
    "disclosure-listed-note": "请生成 G10 附注披露（上市公司格式）审计说明，概述披露项目、金额与公允价值层次核对及与审定表勾稽结果。",
    "disclosure-soe-note": "请生成 G10 附注披露（国有企业格式）审计说明，概述披露项目、金额与相关风险管理披露核对及与审定表勾稽结果。",
    "disclosure-conclusion": "请生成 G10 附注披露审计结论，评价披露完整性、准确性及是否符合企业会计准则与监管要求。",
}


@router.post("/api/workpapers/{wp_id}/g10/ai/{section}", response_model=G10AiGenerateResponse)
async def generate_g10_ai(
    wp_id: str,
    section: str,
    body: G10AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> G10AiGenerateResponse:
    if section not in _PROMPTS:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")

    context_snippet = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, remark, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'G10%' LIMIT 60"
            ),
            {"wp_id": wp_id},
        )
        rows = result.fetchall()
        if rows:
            parts = []
            for r in rows[:12]:
                text = (r.remark or r.conclusion or "")[:200]
                parts.append(f"{r.item_id}: {text}")
            context_snippet = "\n".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.warning("G10 AI context load failed: %s", e)

    rows_hint = ""
    if body.rows:
        rows_hint = "\n".join(str(r)[:120] for r in body.rows[:8])

    user_prompt = (
        f"{_PROMPTS[section]}\n\n"
        f"已有内容：\n{body.existingContent or '（无）'}\n\n"
        f"行数据摘要：\n{rows_hint or '（无）'}\n\n"
        f"底稿上下文：\n{context_snippet or str(body.relatedContext)}"
    )

    try:
        content = await asyncio.wait_for(
            chat_completion(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            ),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 生成超时") from None
    except Exception as e:  # noqa: BLE001
        logger.exception("G10 AI failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return G10AiGenerateResponse(content=content or "", sources=["G10 checklist_responses"])
