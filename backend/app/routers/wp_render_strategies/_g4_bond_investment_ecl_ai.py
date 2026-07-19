"""G4 债权投资(ECL组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g4-ecl/ai/{section}

sections:
  - stage-classification-conclusion   (G4-9 三阶段划分审计结论)
  - ecl-measurement-conclusion        (G4-10 减值测算审计结论)
  - ecl-method-evaluation             (G4-11 ECL方法评价)
  - reversal-writeoff-conclusion      (G4-12 转回核销审计结论)
  - voucher-check-conclusion          (G4-13 凭证检查审计结论)
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

router = APIRouter(tags=["g4-ecl-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G4EclAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G4EclAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G4《债权投资》的ECL组工作底稿。
科目1501债权投资（借方/资产类），以摊余成本计量的金融资产（CAS22分类为AC类）。

本组底稿核心关注预期信用损失（ECL）相关审计：
- G4-9 三阶段划分：CAS22/CAS24信用风险三阶段分类判定（Stage1/Stage2/Stage3）
- G4-10 减值准备测算表：ECL公式链验证（Stage1/2：③=①×②、⑥=目标审定减值−③；Stage3：③=max(0,①−PV)；⑨=⑦−⑧）
- G4-11 预期信用损失计量测试：ECL方法评价（逐笔/组合/迁移矩阵/简化）+参数验证(PD/LGD/EAD)
- G4-12 减值准备转回核销检查：转回合理性（转回≤累计计提）、核销程序合规性
- G4-13 凭证检查表：减值计提/转回/核销的会计分录正确性，借贷平衡校验

审计逻辑链：Stage判定(G4-9) → ECL测算(G4-10) → 方法评价(G4-11) → 转回核销(G4-12) → 凭证检查(G4-13)。
三阶段判定优先级：已发生信用减值(Stage3) > 信用风险显著增加(Stage2) > 未显著增加(Stage1)。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "stage-classification-conclusion": (
        "请生成G4-9三阶段划分检查的审计结论，评价以下方面：\n"
        "1. 被审计单位对各投资项目信用风险三阶段划分的恰当性\n"
        "2. 是否存在信用风险显著增加的判断标准不一致的情况\n"
        "3. 对已发生信用减值事件(Stage3)的识别是否充分\n"
        "4. 企业划分阶段与审计判断阶段的一致性分析\n"
        "5. 对不一致项目的差异原因说明是否合理\n"
        "6. 综合评价三阶段划分对ECL计提基数的影响"
    ),
    "ecl-measurement-conclusion": (
        "请生成G4-10减值准备测算表的审计结论，评价以下方面：\n"
        "1. 各Stage分组的减值准备计算是否正确（③=①×②）\n"
        "2. 审计调整的合理性（⑥=⑤×②A+①×(②A-②)）\n"
        "3. 审定后减值准备余额（⑧=③+⑥）与上年末余额的变动分析\n"
        "4. 本年计提/转回/核销金额与G4-12的一致性\n"
        "5. 信用损失率(②/②A)确定的依据是否充分\n"
        "6. 整体减值准备充分性的综合结论"
    ),
    "ecl-method-evaluation": (
        "请生成G4-11 ECL计量方法评价的审计结论，评价以下方面：\n"
        "1. 被审计单位选用的ECL计量方法（逐笔法/组合法/迁移矩阵法/简化法）是否适当\n"
        "2. 组合划分的依据是否合理（风险特征相似性）\n"
        "3. 关键参数（PD/LGD/EAD）的数据来源与计算方法是否可靠\n"
        "4. 前瞻性信息（宏观经济预测）是否合理纳入ECL模型\n"
        "5. 与上期ECL方法的变更（如有）是否披露且合理\n"
        "6. 综合评价ECL计量方法的合理性和一致性"
    ),
    "reversal-writeoff-conclusion": (
        "请生成G4-12减值准备转回（收回）、核销检查的审计结论，评价以下方面：\n"
        "1. 是否支持「债权投资已按适当金额列报、相关计价调整已恰当记录」的审计目标\n"
        "2. 转回原因是否有客观证据（信用风险改善），转回金额是否≤累计已计提\n"
        "3. 核销是否履行适当审批程序，债权投资性质与核销原因是否清晰\n"
        "4. 关联交易核销是否已特别关注并说明合理性\n"
        "5. 与 G4-10/G4-11/G4-13 的勾稽及拟调整事项\n"
        "6. 给出明确结论（可参考 A未见异常 / B个别例外 / C重大例外）"
    ),
    "voucher-check-conclusion": (
        "请生成G4-13凭证检查的审计结论，评价以下方面：\n"
        "1. 是否覆盖存在、完整性、计价分摊三项认定\n"
        "2. 样本选取方法与规模是否合理（特定样本+代表性样本），检查比例是否充分\n"
        "3. 所抽凭证支持性文件、授权批准、六项核对结果及异常说明\n"
        "4. 借贷勾稽/平衡情况；减值相关金额与 G4-10、转回核销与 G4-12 的一致性\n"
        "5. 期后处置/新增（如有）对截止认定的影响\n"
        "6. 给出明确结论（可参考 A未见异常 / B个别例外 / C重大事项）"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g4-ecl/ai/{section}")
async def g4_ecl_ai_generate(
    wp_id: str,
    section: str,
    body: G4EclAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G4EclAiGenerateResponse:
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
        return G4EclAiGenerateResponse(content="", sources=[])
    return G4EclAiGenerateResponse(content=result, sources=[])


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
        logger.warning("G4 ECL AI: project context 加载失败: %s", e)
    return ctx
