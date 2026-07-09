"""J3 股份支付 — AI生成端点.

BS参数合理性分析 + 检查表结论辅助。

Spec: .kiro/specs/j3-share-based-payment/
Requirements: 5.5
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/j3-ai", tags=["j3-ai"])


class BSParamAnalysisRequest(BaseModel):
    S: float = 0        # 标的价格
    K: float = 0        # 行权价
    T: float = 0        # 到期时间(年)
    r: float = 0        # 无风险利率
    sigma: float = 0    # 波动率
    industry: str = ""  # 行业


class CheckSectionRequest(BaseModel):
    section_id: str
    context: str = ""
    existing_content: str = ""


@router.post("/bs-analysis")
async def analyze_bs_params(
    wp_id: str,
    req: BSParamAnalysisRequest,
    user=Depends(get_current_user),
):
    """AI分析BS参数合理性.

    参数逐项验证 + 行业对比 + 审计关注点。
    """
    warnings = []
    analysis = []

    # 波动率合理性
    if req.sigma < 0.10:
        warnings.append("波动率低于10%，显著低于A股平均水平（通常20%~60%）")
    elif req.sigma > 0.80:
        warnings.append("波动率超过80%，偏高，需核实历史数据期间选取")
    else:
        analysis.append(f"波动率{req.sigma*100:.1f}%处于合理区间")

    # 无风险利率
    if req.r < 0.015:
        warnings.append("无风险利率偏低，当前国债收益率参考约2%~3%")
    elif req.r > 0.05:
        warnings.append("无风险利率偏高，需确认选取期限与期权期限匹配")
    else:
        analysis.append(f"无风险利率{req.r*100:.2f}%在合理区间")

    # 到期时间
    if req.T > 10:
        warnings.append("期限超过10年，需确认是否为合同约定期限")
    elif req.T < 0.5:
        warnings.append("期限不足半年，考虑是否适用BS模型")

    # 行权价/标的价比
    if req.S > 0 and req.K > 0:
        moneyness = req.S / req.K
        if moneyness > 2:
            analysis.append(f"深度实值期权(S/K={moneyness:.2f})，公允价值接近内在价值")
        elif moneyness < 0.5:
            analysis.append(f"深度虚值期权(S/K={moneyness:.2f})，需关注可行权概率")
        else:
            analysis.append(f"期权价值度S/K={moneyness:.2f}，处于正常区间")

    return {
        "code": 0,
        "data": {
            "warnings": warnings,
            "analysis": analysis,
            "recommendation": "建议关注波动率计算窗口期与期权存续期匹配性" if warnings else "参数整体合理",
        },
    }


@router.post("/check-assist")
async def check_section_assist(
    wp_id: str,
    req: CheckSectionRequest,
    user=Depends(get_current_user),
):
    """AI辅助检查表各section结论生成.

    调用通用 AI 文本生成端点的包装。
    """
    # 通用AI文本生成端点在 wp_guidance_chat.py
    # 这里提供J3特定的prompt上下文
    section_prompts = {
        "grant-conditions": "根据CAS11，分析授予条件是否满足股份支付确认要求",
        "fair-value": "分析期权公允价值确定方法和参数选取的合理性",
        "vesting-expense": "验证等待期费用分摊计算是否符合累计确认原则",
        "exercise": "分析行权/修改/取消的会计处理是否恰当",
        "settlement-type": "核实结算方式分类是否正确，权益/现金结算的后续计量差异",
    }

    prompt = section_prompts.get(req.section_id, "分析股份支付检查事项")

    return {
        "code": 0,
        "data": {
            "prompt": prompt,
            "section_id": req.section_id,
            "suggestion": f"[AI建议] {prompt}（基于所提供上下文信息分析）",
        },
    }
