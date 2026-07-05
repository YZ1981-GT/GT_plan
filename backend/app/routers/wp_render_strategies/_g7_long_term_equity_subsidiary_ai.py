"""G7 长期股权投资(子公司组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g7-sub/ai/{section}

sections:
  - control-judgment-conclusion       (G7-7 控制判断综合结论)
  - initial-measurement-conclusion    (G7-8/G7-9 初始计量审计结论)
  - subsequent-conclusion             (G7-10 后续计量审计结论)
  - disposal-conclusion               (G7-11/G7-12 处置审计结论)
  - voucher-conclusion                (G7-18 凭证检查结论)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g7-subsidiary-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G7SubAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G7SubAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G7《长期股权投资》子公司组工作底稿。
本组聚焦子公司投资全生命周期：控制判断→同控/非同控取得→成本法后续计量→处置→凭证检查。科目1511（借方/资产类）。

本组底稿核心关注子公司投资的完整生命周期测试（CAS33/CAS20/CAS2）：
- G7-7 控制判断决策树：CAS33六要素（权力+可变回报+联系）→控制/共同控制/重大影响/无
- G7-8 同一控制下企业合并初始计量：按被合并方账面价值×持股比例确认初始成本
- G7-9 非同一控制下企业合并初始计量：按公允价值（对价+直接费用），差额确认商誉
- G7-10 成本法后续计量：不调整账面，仅确认股利和减值
- G7-11 非一揽子处置：单次交易丧失控制权，个别+合并处置损益
- G7-12 一揽子交易处置：多次交易实质构成一项安排，丧失控制权日统一确认+追溯
- G7-18 凭证检查：借贷平衡+异常项识别

核心公式：
1. 同控初始成本 = 被合并方账面净资产 × 持股比例（差额调资本公积/留存收益）
2. 非同控初始成本 = 支付对价 + 直接费用；商誉 = 初始成本 - 享有净资产FV份额
3. 成本法期末 = 期初 + 追加投资 - 减值（不含权益法调整）
4. 成本法投资收益 = 被投资方宣告股利 × 持股比例
5. 个别处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
6. 一揽子处置：各次交易在丧失控制权日统一确认，之前损益追溯调整

控制判断CAS33六要素：
(一) 对被投资方的权力
(二) 因参与被投资方的相关活动而享有可变回报
(三) 有能力运用对被投资方的权力影响其回报金额
(四) 是否为代理人（实质性/非实质性权力判断）
(五) 潜在表决权的影响
(六) 综合判断（权力+可变回报+联系三要素全满足→控制）

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "control-judgment-conclusion": (
        "请基于G7-7控制判断决策树数据，生成综合审计结论。需包含以下方面：\n"
        "1. CAS33六要素逐项判断结果回顾：权力/可变回报/联系/代理人/潜在表决权/综合\n"
        "2. 各被投资单位的控制类型最终判定（控制/共同控制/重大影响/无重大影响）\n"
        "3. 控制类型对应的后续计量方法（控制→成本法，共同控制/重大影响→权益法）\n"
        "4. 六要素中是否存在边界判断情形（如持股50%但有一票否决权等）及风险评估\n"
        "5. 较上年控制类型是否变化，变化原因及会计处理合规性\n"
        "6. 控制判断文档化完整性评价及总体审计结论"
    ),
    "initial-measurement-conclusion": (
        "请基于G7-8（同控）和G7-9（非同控）初始计量测试数据，生成审计结论。需包含以下方面：\n"
        "1. 同一控制下企业合并（G7-8）：\n"
        "   - 合并方式（吸收合并/控股合并）的判断依据\n"
        "   - 被合并方账面净资产金额的确认（合并日资产负债表）\n"
        "   - 初始投资成本=享有份额=账面净资产×持股比例的计算准确性\n"
        "   - 支付对价与初始成本的差额处理（先冲资本公积/溢价，再调留存收益）\n"
        "2. 非同一控制下企业合并（G7-9）：\n"
        "   - 购买日的确定依据（取得控制权的时点）\n"
        "   - 支付对价的公允价值确认（现金/资产/股权等）\n"
        "   - 直接费用（审计/评估/法律等中介费用）的归集完整性\n"
        "   - 初始投资成本=对价+直接费用的计算准确性\n"
        "   - 被购买方可辨认净资产公允价值的评估方法和合理性\n"
        "   - 商誉=初始成本-享有可辨认净资产FV份额的计算及合理性评价\n"
        "   - 负商誉（廉价购买利得）情形的复核及计入当期损益的充分性\n"
        "3. 总体结论：初始计量是否符合CAS20/CAS33相关规定"
    ),
    "subsequent-conclusion": (
        "请基于G7-10成本法后续计量测试数据，生成审计结论。需包含以下方面：\n"
        "1. 成本法核算规则确认：子公司投资按成本计量，不因被投资方净资产变动调整账面\n"
        "2. 投资收益确认：\n"
        "   - 被投资方宣告分配现金股利的时点和金额\n"
        "   - 应确认投资收益=宣告股利×持股比例的计算准确性\n"
        "   - 是否存在清算性股利（超额分配超出投资后净利润累计）需冲减投资成本\n"
        "3. 减值测试：\n"
        "   - 是否存在减值迹象（被投资方持续亏损/净资产大幅下降等）\n"
        "   - 减值金额的确定依据（可收回金额vs账面价值）\n"
        "   - 本期减值计提的充分性和合理性\n"
        "4. 期末账面余额递推：期末=期初+追加投资-减值，与企业账面差异分析\n"
        "5. 追加投资（如有）的商业实质和定价公允性\n"
        "6. 总体结论：成本法后续计量是否符合CAS2相关规定"
    ),
    "disposal-conclusion": (
        "请基于G7-11（非一揽子处置）和G7-12（一揽子交易处置）数据，生成审计结论。需包含以下方面：\n"
        "1. 非一揽子处置（G7-11）：\n"
        "   - 处置时点（丧失控制权日）的确定依据\n"
        "   - 处置对价的公允性（关联交易需额外关注定价公允）\n"
        "   - 个别报表处置损益=对价-账面-应收股利+可转损益OCI的计算准确性\n"
        "   - 合并报表层面调整：剩余投资按丧失控制权日FV重新计量\n"
        "   - 合并处置损益与个别处置损益差异的合理性\n"
        "2. 一揽子交易处置（G7-12）：\n"
        "   - 一揽子交易判断依据是否充分（CAS33应用指南条件）\n"
        "   - 各次交易在丧失控制权日统一确认的会计处理正确性\n"
        "   - 追溯调整金额：之前各次处置已确认的损益需追溯调整\n"
        "   - 累计对价和累计持股变动的完整性\n"
        "   - 合并层面处置损益的最终计算准确性\n"
        "3. 总体结论：处置会计处理是否符合CAS33/CAS2相关规定，个别报表和合并报表处置损益"
        "是否准确"
    ),
    "voucher-conclusion": (
        "请基于G7-18凭证检查数据，生成审计结论。需包含以下方面：\n"
        "1. 抽样方法和样本量的充分性评价\n"
        "2. 借贷平衡检查：所有抽查凭证借贷合计是否平衡\n"
        "3. 核对项目完成情况：\n"
        "   - 核对1-原始凭证：投资协议/股权转让协议/工商变更登记等\n"
        "   - 核对2-授权：股东会/董事会决议/投资审批文件\n"
        "   - 核对3-账务：会计分录与业务实质一致性\n"
        "   - 核对4-金额：凭证金额与协议/评估报告/验资报告的一致性\n"
        "   - 核对5-分类：科目分类（成本/收益/OCI）的正确性\n"
        "   - 核对6-投资收益：股利收入与被投资方利润分配决议的匹配\n"
        "4. 异常项识别：是否发现异常凭证（金额异常/对方科目异常/摘要含可疑描述）\n"
        "5. 异常项风险等级评估及后续审计应对措施\n"
        "6. 总体结论：凭证检查是否发现重大错报迹象"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g7-sub/ai/{section}")
async def g7_subsidiary_ai_generate(
    wp_id: str,
    section: str,
    body: G7SubAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G7SubAiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        result = await asyncio.wait_for(
            chat_completion(messages=messages, temperature=0.3, max_tokens=2000),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI 生成超时（30秒），请重试")
    if isinstance(result, str) and result.startswith("["):
        return G7SubAiGenerateResponse(content="", sources=[])
    return G7SubAiGenerateResponse(content=result, sources=[])


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
) -> str:
    parts: list[str] = [f"## 任务\n{_SECTION_PROMPTS.get(section, '请生成审计文本。')}\n"]
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")
    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")
    if existing_content:
        parts.append(f"## 已有内容\n{existing_content[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")
    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    ctx: dict = {"client_name": "", "audit_year": ""}
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        if row:
            ctx["client_name"] = row.client_name or ""
            ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G7 Subsidiary AI: project context 加载失败: %s", e)
    return ctx
