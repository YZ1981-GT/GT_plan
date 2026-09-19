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
- G7-9 非同一控制下企业合并初始计量：按公允价值计量合并成本（对价FV+原持股购买日FV）；直接相关中介费用计入当期损益、不构成合并成本；差额确认商誉或廉价购买利得
- G7-10 子公司后续计量：①股利测算（成本法宣告日确认）；②购买少数股权（合并权益性交易）；③不丧失控制权处置（个别确认损益、合并调权益）
- G7-11 非一揽子处置：单次交易丧失控制权，个别+合并处置损益
- G7-12 一揽子交易处置：多次交易实质构成一项安排，丧失控制权日统一确认+追溯
- G7-18 凭证检查：借贷平衡+异常项识别

核心公式：
1. 同控初始成本 = 被合并方账面净资产 × 持股比例（差额调资本公积/留存收益）
2. 非同控初始成本 = 支付对价公允价值 + 原持股购买日公允价值（直接相关费用费用化，不进成本）；商誉 = 初始成本 - 享有可辨认净资产FV份额；廉价购买须复核后确认利得
3. 成本法投资收益 = 被投资方宣告股利 × 持股比例；差异 = 应享 − 入账
4. 购买少数股权合并调整⑤ = 购买成本② − 持续计算净资产FV③ × 新增比例①（不确认商誉）
5. 不丧失控制权处置：个别⑤=④−①×③/②；合并⑧=④−⑦（调权益不确认损益）
6. 个别处置损益（丧失控制）= 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
7. 一揽子处置：各次交易在丧失控制权日统一确认，之前损益追溯调整

控制判断CAS33（与 G7-7 问卷六段对齐）：
(一) 对被投资方的权力
(二) 因参与被投资方的相关活动而享有可变回报
(三) 有能力运用对被投资方的权力影响其回报金额
(四) 保护性权利（不构成权力的权利评估）
(五) 代理人/委托人判断
(六) 分类与控制权转移时点（三要素综合 + 同控/非同控/重大影响）

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "control-judgment-conclusion": (
        "请基于G7-7控制判断决策树数据，生成综合审计结论。需包含以下方面：\n"
        "1. CAS33 问卷六段回顾：权力/可变回报/联系/保护性权利/代理人委托人/分类与控制权转移时点\n"
        "2. 各被投资单位的关系类型最终判定（控制/共同控制/重大影响/无重大影响）\n"
        "3. 若构成控制：企业合并类型（同控/非同控/非企业合并）及后续底稿路线（G7-8/G7-9/G7-10）\n"
        "4. 边界判断情形（如持股≤50%但有实质性权力、保护性权利与实质性权利界限等）及风险评估\n"
        "5. 较上年关系类型是否变化，变化原因及会计处理合规性\n"
        "6. 控制判断文档化完整性评价及总体审计结论"
    ),
    "initial-measurement-conclusion": (
        "请基于当前传入的初始计量测试数据生成审计结论。"
        "若 relatedContext.sheet 为 G7-8，仅围绕同一控制下初始计量分析，勿臆造G7-9数据；"
        "若为 G7-9，仅围绕非同一控制下初始计量分析。需覆盖：\n"
        "【G7-8同控】\n"
        "1. 合并方式取得：最终控制方、账面价值份额③=①×②、对价组成④及调整⑤=③-④是否准确\n"
        "2. 分步实现同控合并：是否构成一揽子交易；合并日初始成本及⑥=②+③-⑤是否准确\n"
        "3. 反向购买：会计购买方识别、构成业务判断及文档化充分性\n"
        "4. 会计政策统一、资本公积/留存收益恢复及总体结论\n"
        "【G7-9非同控】\n"
        "1. 购买日认定、对价公允价值组成及原持股购买日FV；直接相关中介费用是否已费用化（不进初始成本）\n"
        "2. 初始投资成本⑥=对价FV③+原持股FV④；可辨认净资产FV份额；商誉⑧或廉价购买利得（须复核）\n"
        "3. 分步取得（非一揽子）累计对价与母公司初始成本⑦；反向购买构成业务判断\n"
        "4. 总体结论是否符合CAS20/CAS2"
    ),
    "subsequent-conclusion": (
        "请基于G7-10子公司后续计量三区段测试数据，生成审计结论。需包含以下方面：\n"
        "1. 股利分配测算：\n"
        "   - 宣告时点、决议依据及应享股利=宣告金额×持股比例的计算准确性\n"
        "   - 应享与实际入账差异及追查结果；是否存在清算性股利需冲减投资成本\n"
        "2. 购买少数股东股权：\n"
        "   - 个别报表新增成本确认（CAS2）是否正确\n"
        "   - 合并层面⑤=购买成本②−按新增比例①享有的持续计算净资产份额④\n"
        "   - 差额是否仅调整资本公积/留存收益、未错误确认商誉或损益\n"
        "3. 处置子公司权益但不丧失控制权：\n"
        "   - 个别投资收益⑤=④−①×③/②是否准确；处置后是否仍保持控制\n"
        "   - 合并⑧=④−⑦是否按权益性交易处理、未计入损益\n"
        "4. 与G7-11/G7-12（丧失控制权）的边界是否划分清楚\n"
        "5. 总体结论：后续计量是否符合CAS2/CAS33相关规定"
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
