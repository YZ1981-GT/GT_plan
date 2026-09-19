"""G7 长期股权投资(权益法组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g7-equity-method/ai/{section}

sections:
  - accounting-policy-conclusion    (G7-6 会计政策一致性结论)
  - cost-test-conclusion            (G7-13 投资成本测试结论)
  - equity-method-conclusion        (G7-14 权益法测算结论)
  - internal-transaction-conclusion (G7-15 内部交易抵销结论)
  - unrecognized-loss-conclusion    (G7-16 未确认投资损失结论)
  - impairment-conclusion           (G7-17 减值测试结论)
  - impairment-note                 (G7-17 审计说明)
"""

from __future__ import annotations

import asyncio
import json
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

router = APIRouter(tags=["g7-equity-method-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G7EquityMethodAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G7EquityMethodAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G7《长期股权投资》权益法组工作底稿。
科目1401长期股权投资（借方/资产类，权益法核算部分），G循环中权益法核算全流程。

本组底稿核心关注权益法核算（CAS2）：
- G7-4 被投资单位基本信息：工商信息+股权结构+管理层+持股比例
- G7-5 被投资单位财务信息：损益表/资产负债表关键数据
- G7-6 被投资公司会计政策：与投资方政策一致性检查
- G7-13 投资成本测试：初始投资成本vs享有可辨认净资产公允价值份额
- G7-14 权益法测算表（★最核心）：净利润调整→享有份额→投资收益确认→期末余额
- G7-15 内部交易抵销：顺流/逆流交易未实现利润抵销
- G7-16 未确认投资损失：超额亏损时长期权益的抵减顺序
- G7-17 减值测试：可收回金额(CAS8)vs账面价值

权益法核算核心公式链：
1. 调整后净利润 = 报告净利润 - 内部交易 - FV折旧 ± 政策 ± 其他
2. 应享有份额 = 调整后净利润 × 持股比例
3. 期末余额 = 期初 + 投资收益 + OCI份额 + 其他权益份额 - 股利

投资成本测试判断（CAS2）：
- 初始投资成本 > 享有可辨认净资产FV份额 → 差额确认为商誉（不调整初始成本）
- 初始投资成本 < 享有可辨认净资产FV份额 → 差额计入营业外收入（调增初始成本）

内部交易抵销规则：
- 顺流交易(投资方→被投资方)：应抵销 = 未实现利润 × 100%
- 逆流交易(被投资方→投资方)：应抵销 = 未实现利润 × 持股比例

减值判断（CAS8）：
- 可收回金额 = MAX(公允价值-处置费用, 使用价值)
- 减值金额 = MAX(0, 账面价值 - 可收回金额)

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "accounting-policy-conclusion": (
        "请基于G7-6被投资公司会计政策一致性检查数据，生成审计结论。需包含：\n"
        "1. 核对范围（被投资方家数、事项覆盖）\n"
        "2. 一致/不一致/不适用概况；不一致事项摘要及调整金额\n"
        "3. 调整是否应同步至G7-14「会计政策调整」列\n"
        "4. 明确公允价值/可辨认净资产调整属G7-13，勿与本表混淆\n"
        "5. 总体结论：是否符合CAS2按投资方政策调整后再计算应享份额的要求"
    ),
    "cost-test-conclusion": (
        "请基于G7-13投资成本测试数据，生成审计结论。需包含以下方面：\n"
        "1. 各被投资单位初始投资成本的确定依据（对价+直接费用）\n"
        "2. 被投资方可辨认净资产公允价值的确定方法和合理性\n"
        "3. 享有份额的计算（净资产FV×持股比例）是否准确\n"
        "4. 差额性质判断：正差额（商誉）不调整初始成本、负差额（营业外收入）需调增初始成本\n"
        "5. 公允价值调整明细是否充分（如有调整）\n"
        "6. 投资成本测试的总体结论：初始计量是否符合CAS2规定"
    ),
    "equity-method-conclusion": (
        "请基于G7-14权益法测算数据，生成审计结论。需包含以下方面：\n"
        "1. 净利润调整是否完整（内部交易/FV折旧摊销/会计政策/其他调整）\n"
        "2. 调整后净利润×持股比例=应享有份额的计算准确性\n"
        "3. 投资收益差异（应享有-企业确认）分析及合理性判断\n"
        "4. 差异是否超过重要性水平，超过时的原因分析\n"
        "5. OCI份额和其他权益变动份额的确认准确性\n"
        "6. 期末余额递推（期初+收益+OCI+其他-股利）与企业账面的一致性\n"
        "7. 权益法核算总体结论：投资收益确认和期末计量是否符合CAS2"
    ),
    "internal-transaction-conclusion": (
        "请基于G7-15内部交易数据，生成审计结论。需包含以下方面：\n"
        "1. 内部交易的识别是否完整（顺流/逆流分类准确性）\n"
        "2. 未实现利润的计算方法和金额合理性\n"
        "3. 顺流交易抵销（全额=未实现利润×100%）的准确性\n"
        "4. 逆流交易抵销（按份额=未实现利润×持股比例）的准确性\n"
        "5. 本年变动（应抵销-上年抵销）的连续性分析\n"
        "6. 抵销分录是否正确影响投资收益/长期股权投资\n"
        "7. 内部交易抵销总体结论：抵销金额是否合理、完整"
    ),
    "unrecognized-loss-conclusion": (
        "请基于G7-16未确认投资损失测试数据，生成审计结论。需包含以下方面：\n"
        "1. 被投资单位累计亏损与合计长期权益（投资账面+长应收+其他实质权益+预计负债）的比较\n"
        "2. 超额亏损 = MAX(0, 累计亏损−合计长期权益) 的计算是否准确\n"
        "3. 抵减顺序是否符合CAS2第44条：①冲减投资账面→②冲减长应收→③确认预计负债\n"
        "4. 未确认投资损失（超额−各项冲减，且≥0）是否在备查簿恰当登记\n"
        "5. 本期变动与上期累计的勾稽关系\n"
        "6. 未确认投资损失总体结论：超额亏损分配及未确认部分是否合理、完整"
    ),
    "impairment-conclusion": (
        "请基于G7-17减值测试数据，生成审计结论。需包含以下方面：\n"
        "1. 减值迹象判断：是否存在被投资方持续亏损/净资产大幅下降/市场恶化等情形\n"
        "2. 可收回金额的确定方法（公允价值-处置费用 vs 使用价值取高）\n"
        "3. 公允价值-处置费用的确定依据（市场法/收益法/成本法）\n"
        "4. 使用价值的折现假设合理性（折现率/预测期/现金流量预测）\n"
        "5. 减值金额 = MAX(0, 账面价值-可收回金额)的计算准确性\n"
        "6. 减值计提的充分性评价（是否存在应提未提情形）\n"
        "7. 减值测试总体结论：减值准备是否充分、合理，符合CAS8"
    ),
    "impairment-note": (
        "请基于G7-17减值测试数据，生成审计说明（程序与证据说明，非最终结论）。需包含：\n"
        "1. 已执行的减值迹象识别程序（访谈/财报分析/行业对比等）\n"
        "2. 可收回金额估计的证据来源（估值报告/可比交易/折现模型）\n"
        "3. 对存在减值迹象但未计提、或全额减值等特殊情形的复核说明\n"
        "4. 拟调整/未调整事项及其对报表的影响（如有）\n"
        "语气为工作底稿说明，勿写成笼统的「总体结论」口号"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g7-equity-method/ai/{section}")
async def g7_equity_method_ai_generate(
    wp_id: str,
    section: str,
    body: G7EquityMethodAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G7EquityMethodAiGenerateResponse:
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
        return G7EquityMethodAiGenerateResponse(content="", sources=[])
    return G7EquityMethodAiGenerateResponse(content=result, sources=[])


def _format_related_context_value(value: Any) -> str:
    """序列化 relatedContext 值；保留 0/False，嵌套结构用 JSON。"""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)[:6000]
        except (TypeError, ValueError):
            return str(value)[:6000]
    return str(value)


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
        ctx_str = "\n".join(
            f"- {k}: {_format_related_context_value(v)}"
            for k, v in related_context.items()
            if v is not None and v != ""
        )
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
        logger.warning("G7 EquityMethod AI: project context 加载失败: %s", e)
    return ctx
