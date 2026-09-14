"""G0 投资循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/g0/ai-generate

sections:
- securities-diff-conclusion   → G0-3(证券) 证券投资差异核对审计结论
- alternative-audit-conclusion → G0-6 投资循环替代程序审计结论
- g0-summary-control           → G0-1 下区 三、审计说明 第1项（源 S20）
- g0-summary-error-analysis    → G0-1 下区 三、审计说明 第2项（源 X20，提示语 X21+X22）
- g0-summary-reliability       → G0-1 下区 三、审计说明 第3项（源 S24）
- g0-summary-mismatch          → G0-1 下区 三、审计说明 第4项（源 S25，提示语 S26）
- g0-summary-alternative       → G0-1 下区 三、审计说明 第5项（源 S28）
- g0-summary-conclusion        → G0-1 下区 四、审计结论（源 C30，参考结论 B55~B57）

🔴 ``_SUPPORTED_SECTIONS`` 是**硬门**（``raise HTTPException(400)``），而前端
``catch`` 会把 400 吞成「AI 生成失败」→ 按钮看着能点、实际永远失败。故 section
必须两处同时登记（``_SUPPORTED_SECTIONS`` + ``_SECTION_PROMPTS``），守卫见
``backend/tests/test_g0_review_prompts.py``（键集相等 + 与前端 ``G0_AI_SECTIONS``
双向锁死）。
"""

from __future__ import annotations

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

router = APIRouter(tags=["g0-ai"])


class G0AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "securities-diff-conclusion",
    "alternative-audit-conclusion",
    # G0-1 下区（spec g0-confirmation-source-alignment Task 19 / R3.7 / R3.9）。
    # 真源 = 前端 `g0-confirmation/g0SummaryLowerZone.G0_AI_SECTIONS`。
    "g0-summary-control",
    "g0-summary-error-analysis",
    "g0-summary-reliability",
    "g0-summary-mismatch",
    "g0-summary-alternative",
    "g0-summary-conclusion",
}

# 「不得虚构」通用约束（每条 prompt 都拼它；G0-1 下区五段说明与结论在无数据时
# 必须写「[待补充]」而不是编造金额/结论）。
_NO_FABRICATION = (
    "严禁虚构未提供的数据、被函证单位名称、金额或结论；上下文缺失处直接写「[待补充]」，"
    "不得推测，只依据给定数据组织语言。"
)

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G0《投资循环函证》。
科目覆盖：交易性金融资产/债权投资/长期股权投资/其他权益工具投资。
核心关注：证券投资函证回函与账面在持仓数量/公允价值/市值三维度的差异核对；
未回函投资项目的替代程序（持仓证明检查/股利收入证据/投资处置收益证据/公允价值佐证）；
差异原因分类（估值时点差异/交易日与结算日差异/计量方法差异）；公允价值 Level1-3 佐证充分性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "securities-diff-conclusion": (
        "请生成 G0-3(证券) 函证差异核对表的审计结论，评价证券投资回函确认的持仓数量、"
        "单位公允价值、总市值与账面记录的差异，分析差异原因的合理性，并对函证证据的充分适当性作出结论。"
    ),
    "alternative-audit-conclusion": (
        "请生成 G0-6 投资循环替代程序检查表的审计结论，评价对未回函投资项目执行的替代程序"
        "（持仓证明/股利收入/处置收益/公允价值佐证）所获取证据的充分适当性，"
        "对投资的存在性、计价与准确性作出结论。"
    ),
    # ─── G0-1 下区（源模板 `函证结果汇总表G0-1`，openpyxl 逐格核对） ───────────
    #
    # 🔴 源模板笔误原样保留的边界：S24 原文交叉引用写「（G0-6）」，而回函可靠性
    #    验证表实为 **G0-7**（`邮件传真回函可靠性验证G0-7`），G0-6 是替代程序检查表。
    #    prompt 里按**意图**指向 G0-7；源模板文字断言（Task 20 源缺陷登记）不得改。
    "g0-summary-control": (
        "请生成 G0-1「1、对询证函保持的控制的说明」（源模板 S20）。依据 CAS 1312 第十条，"
        "说明注册会计师对询证函全过程保持控制的具体措施：被函证方名称与地址的独立核实（G0-2）、"
        "询证函由项目组亲自编制与寄发、回函直接寄至会计师事务所而非被审计单位、"
        "跟函过程留痕（G0-3）。\n" + _NO_FABRICATION
    ),
    "g0-summary-error-analysis": (
        "请生成 G0-1「2、对误差的分析」（源模板 X20）。按源模板界定误差构成条件"
        "（源 X21+X22：不符事项金额高于或低于账户余额人民币（）万元，"
        "并且被审计单位不能合理解释其差异并提供相应依据），逐项分析回函不符事项，"
        "区分估值时点差异 / 交易日与结算日差异 / 计量方法差异，"
        "判断是否构成误差、是否需推 A13 错报。\n" + _NO_FABRICATION
    ),
    "g0-summary-reliability": (
        "请生成 G0-1「3、对以传真或电子邮件形式收到的回函的可靠性的考虑」（源模板 S24）。"
        "依据回函可靠性验证底稿 G0-7（源模板此处交叉引用写「（G0-6）」属笔误）说明已执行的"
        "可靠性程序：回函方身份确认、邮箱域名与被函证方公示信息的一致性核对、"
        "致电原始联系人复核、必要时索取纸质原件，并评价电子回函作为审计证据的可靠性。"
        "\n" + _NO_FABRICATION
    ),
    "g0-summary-mismatch": (
        "请生成 G0-1「4、针对不符事项的程序」（源模板 S25）。说明对回函不符项执行的追加程序"
        "（调取原始交易凭证 / 对账单 / 持仓证明，重新核对差异构成，"
        "与被审计单位沟通并取得书面解释）。按源模板提示语（S26）："
        "如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序。"
        "\n" + _NO_FABRICATION
    ),
    "g0-summary-alternative": (
        "请生成 G0-1「5、针对未回函的替代程序」（源模板 S28）。依据替代程序检查表 G0-6，"
        "说明对未回函投资项目执行的替代程序及结果：期末持仓证明或托管对账单检查、"
        "股利/利息收入原始凭证检查、投资处置收益的银行流水与结算单核对、"
        "公允价值 Level1-3 佐证检查，并评价证据对存在性与计价认定的充分适当性。"
        "\n" + _NO_FABRICATION
    ),
    "g0-summary-conclusion": (
        "请生成 G0-1「四、审计结论」（源模板 C30）。依据函证覆盖率、回函确认金额、"
        "替代程序确认金额与账面金额的勾稽结果给出结论，并以源模板参考结论三选一为基准"
        "（源 B55 未见异常 / B56 除以下重大不符事项应当作为调整事项予以调整外，其余未见异常 / "
        "B57 由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认）。"
        "\n" + _NO_FABRICATION
    ),
}


@router.post("/api/workpapers/{wp_id}/g0/ai-generate")
async def g0_ai_generate(
    wp_id: str,
    body: G0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G0AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return G0AiGenerateResponse(content="", sources=[])
    return G0AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:
        logger.warning("G0 AI: project context 加载失败: %s", e)
    return ctx
