"""G6 其他债权投资(ECL组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g6-ecl/ai/{section}

sections:
  - stage-conclusion                (G6-11 三阶段划分审计结论)
  - impairment-conclusion           (G6-12 减值准备测算审计结论)
  - ecl-measurement-conclusion      (G6-13 ECL计量测试审计结论)
  - voucher-conclusion              (G6-15 凭证检查审计结论)
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

router = APIRouter(tags=["g6-ecl-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G6EclAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G6EclAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G6《其他债权投资》的ECL组工作底稿。
科目1503其他债权投资（借方/资产类），以公允价值计量且其变动计入其他综合收益的金融资产（CAS22分类为FVOCI-Debt类）。

本组底稿核心关注预期信用损失（ECL）相关审计：
- G6-11 三阶段划分：CAS22/CAS24信用风险三阶段分类判定（Stage1/Stage2/Stage3）
- G6-12 减值准备测算表：22列ECL公式链验证（③=①×②、⑥=⑤×②A+①×(②A-②)、⑧=③+⑥、⑨=⑦-⑧）
- G6-13 预期信用损失计量测试：49行5section问卷，验证PD/LGD/EAD参数合理性
- G6-15 凭证检查表：22列3区段Tab，减值计提/转回/核销凭证正确性

其他债权投资（FVOCI-Debt）ECL减值的特殊性：
1. 减值准备按摊余成本口径计算（非公允价值口径），与AC类(G4)方法一致
2. 减值损失在利润表确认，但不减少账面金额（通过OCI调整）
3. 三阶段判定优先级：已发生信用减值(Stage3) > 信用风险显著增加(Stage2) > 未显著增加(Stage1)
4. ECL公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧

审计逻辑链：Stage判定(G6-11) → ECL测算(G6-12) → 计量方法评价(G6-13) → 转回核销(G6-14) → 凭证检查(G6-15)。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "stage-conclusion": (
        "请生成G6-11三阶段划分检查的审计结论，评价以下方面：\n"
        "1. 被审计单位对各投资项目信用风险三阶段划分的恰当性\n"
        "2. 是否存在信用风险显著增加的判断标准不一致的情况\n"
        "3. 对已发生信用减值事件(Stage3)的识别是否充分\n"
        "4. 企业划分阶段与审计判断阶段的一致性分析\n"
        "5. 对不一致项目的差异原因说明是否合理\n"
        "6. 各阶段分布(S1/S2/S3)数量及金额的合理性\n"
        "7. 综合评价三阶段划分对ECL计提基数的影响"
    ),
    "impairment-conclusion": (
        "请生成G6-12减值准备测算表的审计结论，评价以下方面：\n"
        "1. 各Stage分组的减值准备计算是否正确（③=①×②）\n"
        "2. 审计调整的合理性（⑥=⑤×②A+①×(②A-②)）\n"
        "3. 审定后减值准备余额（⑧=③+⑥）与上年末余额的变动分析\n"
        "4. 审定后账面价值（⑨=⑦-⑧）的准确性\n"
        "5. 信用损失率(②/②A)确定的依据是否充分\n"
        "6. 本年计提/转回金额及OCI调整的合理性\n"
        "7. 减值准备按摊余成本口径计算（非公允价值口径）的一致性\n"
        "8. 整体减值准备充分性的综合结论"
    ),
    "ecl-measurement-conclusion": (
        "请生成G6-13 ECL计量测试的审计结论，评价以下方面：\n"
        "1. PD（违约概率）：数据来源是否可靠、估计方法是否适当、前瞻性调整是否合理\n"
        "2. LGD（违约损失率）：抵押品评估、回收率假设、优先级考量是否充分\n"
        "3. EAD（违约风险暴露）：余额口径确定及表外承诺纳入是否正确\n"
        "4. 折现率：是否使用原始实际利率或合理近似利率\n"
        "5. 前瞻性信息：宏观经济情景设定及权重分配是否合理\n"
        "6. 各参数与上期的变动分析及变更合理性\n"
        "7. ECL计量方法整体适当性的综合结论"
    ),
    "voucher-conclusion": (
        "请生成G6-15凭证检查的审计结论，评价以下方面：\n"
        "1. 抽取的减值计提/转回/核销凭证的借贷方向是否正确\n"
        "2. 各凭证的原始凭证是否完整、有授权批准\n"
        "3. 账务处理是否正确（科目使用、金额）\n"
        "4. 减值金额与G6-12测算表的一致性\n"
        "5. OCI调整分录是否正确（FVOCI减值通过OCI调整）\n"
        "6. 借贷平衡校验结果及异常凭证的说明\n"
        "7. 凭证抽样覆盖率及总体合规性评价"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g6-ecl/ai/{section}")
async def g6_ecl_ai_generate(
    wp_id: str,
    section: str,
    body: G6EclAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G6EclAiGenerateResponse:
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
        return G6EclAiGenerateResponse(content="", sources=[])
    return G6EclAiGenerateResponse(content=result, sources=[])


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
        logger.warning("G6 ECL AI: project context 加载失败: %s", e)
    return ctx
