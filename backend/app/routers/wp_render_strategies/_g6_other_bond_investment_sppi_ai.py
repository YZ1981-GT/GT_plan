"""G6 其他债权投资(SPPI组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g6-sppi/ai/{section}

sections:
  - fair-value-conclusion       (公允价值测试审计结论)
  - interest-note               (利息测算审计说明)
  - interest-conclusion         (利息测算审计结论)
  - business-model-conclusion   (业务模式分析综合判断)
  - sppi-conclusion             (SPPI测试综合结论)
  - inventory-conclusion        (有价证券盘点表结论)
  - reconciliation-conclusion   (盘点倒轧表结论)
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

router = APIRouter(tags=["g6-sppi-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G6SppiAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G6SppiAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G6《其他债权投资》的SPPI组工作底稿。
科目1503其他债权投资（借方/资产类），以公允价值计量且其变动计入其他综合收益的金融资产（IFRS9/CAS22分类为FVOCI-Debt类）。

本组底稿核心关注IFRS9/CAS22金融工具分类标准的三要素验证：

1. SPPI测试要素（合同现金流量特征分析）：
   - 本金定义：初始确认时的公允价值，可因还款而变化
   - 利息定义：货币时间价值+信用风险+流动性风险+管理成本+利润率的对价
   - 修改时间价值：利率重置与计息期不匹配时的差异评估
   - 提前还款条款：提前偿付金额是否基本代表未偿付本金及利息（含合理补偿）
   - 合同关联工具：优先/次级结构中标的池每项资产是否满足SPPI

2. 业务模式三分类（CAS22第17-19条）：
   - 持有以收取合同现金流量（Hold-to-Collect）
   - 既以收取合同现金流量为目标又以出售为目标（Hold-and-Sell）
   - 其他业务模式（Trading/Other）

3. 其他债权投资(FVOCI-Debt)的计量特点：
   - 摊余成本计量利息收入（实际利率法）
   - 公允价值变动计入其他综合收益（OCI）
   - 减值损失在利润表确认但不减少账面金额
   - 处置时OCI累计公允价值变动转入当期损益

4. 实际利率法利息计算：
   - 利息收入 = 摊余成本 × 实际利率 × 计息天数/365
   - 现金流入 = 面值 × 票面利率 × 计息天数/365
   - 期末摊余成本 = 期初 + 实际利息 - 现金流入

5. 公允价值层次（Level1/2/3）：
   - Level1：活跃市场报价（相同资产/负债的未经调整报价）
   - Level2：可观察输入值（类似资产报价、收益率曲线等）
   - Level3：不可观察输入值（需披露估值技术和关键假设）

审计逻辑链：业务模式(FVOCI) + SPPI通过 → 确认分类为其他债权投资 → 实际利率法利息 → 公允价值计量 → 盘点存在性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "fair-value-conclusion": (
        "请生成G6-5公允价值测试表的审计结论，评价以下方面：\n"
        "1. 各投资项目公允价值层次（Level1/2/3）划分的合理性\n"
        "2. 估值方法的适当性及与上期的一致性\n"
        "3. 期末审定公允价值与未审数的差异分析（差异原因及合理性）\n"
        "4. Level3项目不可观察输入值的合理性及敏感性分析\n"
        "5. 估值来源机构的独立性和权威性\n"
        "6. 公允价值变动对其他综合收益的影响金额是否正确"
    ),
    "interest-note": (
        "请生成G6-6利息测算表的审计说明，概述以下方面：\n"
        "1. 实际利率法测算的执行范围与抽样/全覆盖情况\n"
        "2. 实际利率、票面利率与计息天数的确定依据\n"
        "3. 摊余成本链条（期初→实际利息→票息→期末）的复核结果\n"
        "4. 与G6-1利息调整本期变动或账面利息收入的交叉验证差异及原因\n"
        "5. 拟调整事项、未调整事项及其对报表的影响"
    ),
    "interest-conclusion": (
        "请生成G6-6利息测算表的审计结论，评价以下方面：\n"
        "1. 实际利率法计算利息收入的正确性（摊余成本×实际利率×天数/365）\n"
        "2. 实际利率与票面利率的差异合理性（折溢价摊销）\n"
        "3. 各期摊余成本链条的连续性和正确性（期末=期初+利息-现金流入）\n"
        "4. 利息测算合计数与G6-1审定表利息调整科目的交叉验证结论\n"
        "5. 计息天数确定的合理性（实际天数/30天/360天制）\n"
        "6. 是否存在减值迹象需将利息收入改按净额（摊余成本-减值准备）计算"
    ),
    "business-model-conclusion": (
        "请生成G6-7业务模式分析的综合判断结论，评价以下方面：\n"
        "1. 被审计单位管理其他债权投资的业务模式判定\n"
        "   - 是否既以收取合同现金流量为目标又以出售为目标（FVOCI分类依据）\n"
        "   - 管理层日常管理和业绩评价方式是否支持该分类\n"
        "2. 出售情况分析：\n"
        "   - 期内出售频率和金额是否与'兼有'模式一致\n"
        "   - 出售原因是否合理（信用恶化/集中度/久期管理等）\n"
        "   - 出售行为是否改变了业务模式的整体判定\n"
        "3. 综合分类结论：\n"
        "   - 最终分类为'兼有'（FVOCI-Debt）是否有充分的审计证据支持\n"
        "   - 与上年分类是否一致，变更是否有合理理由\n"
        "   - 对于非'兼有'模式的投资项目是否需要重分类"
    ),
    "sppi-conclusion": (
        "请生成G6-8合同现金流量特征分析（SPPI测试）的综合结论，评价以下方面：\n"
        "1. 本金定义：各投资项目本金金额是否明确，是否存在非标本金结构\n"
        "2. 利息定义：合同利率是否仅反映货币时间价值、信用风险等基本借贷对价\n"
        "3. 修改时间价值：是否存在利率重置频率与计息期不匹配的情况\n"
        "   - 如存在，基准测试/定性评估结论是否合理\n"
        "4. 提前还款条款分析：\n"
        "   - 是否包含提前还款/延期选择权\n"
        "   - 提前偿付金额是否基本代表未偿付本金及相应利息（含合理补偿）\n"
        "5. 合同关联工具（如适用）：\n"
        "   - 是否存在优先/次级分层结构\n"
        "   - 标的资产池中每项资产是否满足SPPI条件\n"
        "6. SPPI综合结论：\n"
        "   - 各投资项目是否均满足SPPI条件\n"
        "   - 不满足SPPI的项目是否已重分类为FVTPL\n"
        "   - 整体SPPI测试是否支持其他债权投资分类的合理性"
    ),
    "inventory-conclusion": (
        "请生成G6-9有价证券盘点表的审计结论，评价以下方面：\n"
        "1. 盘点程序执行的充分性（盘点范围、参与人员、盘点日期选择）\n"
        "2. 盘点数量与账面数量的一致性及差异追查情况\n"
        "3. 有价证券的存在性与权属确认（含第三方托管对账单核对）\n"
        "4. 限售/质押/冻结等受限情况的披露完整性\n"
        "5. 盘点过程中发现的异常情况及处理结论"
    ),
    "reconciliation-conclusion": (
        "请生成G6-10盘点倒轧表的审计结论，评价以下方面：\n"
        "1. 盘点日至资产负债表日（基准日）增减变动的完整性与合理性\n"
        "2. 基准日数量（盘点日±增减）与账面数量的差异分析\n"
        "3. 差异原因是否充分、是否需要调整入账\n"
        "4. 增减明细与凭证、对账单的交叉核对结论\n"
        "5. 通过倒轧程序确认的其他债权投资对应有价证券存在性与完整性结论"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g6-sppi/ai/{section}")
async def g6_sppi_ai_generate(
    wp_id: str,
    section: str,
    body: G6SppiAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G6SppiAiGenerateResponse:
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
        return G6SppiAiGenerateResponse(content="", sources=[])
    return G6SppiAiGenerateResponse(content=result, sources=[])


def _format_context_value(value: Any, *, depth: int = 0) -> str:
    """将 relatedContext 中的嵌套 list/dict 格式化为可读文本，避免直接 str()。"""
    import json

    if value is None or value == "":
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if depth >= 3:
        try:
            return json.dumps(value, ensure_ascii=False)[:800]
        except Exception:  # noqa: BLE001
            return str(value)[:800]
    if isinstance(value, list):
        if not value:
            return "（空）"
        lines: list[str] = []
        for i, item in enumerate(value[:20]):
            if isinstance(item, dict):
                compact = "; ".join(
                    f"{k}={_format_context_value(v, depth=depth + 1)}"
                    for k, v in list(item.items())[:12]
                    if v not in (None, "")
                )
                lines.append(f"  {i + 1}. {compact}")
            else:
                lines.append(f"  {i + 1}. {_format_context_value(item, depth=depth + 1)}")
        if len(value) > 20:
            lines.append(f"  …共 {len(value)} 条，已截断")
        return "\n" + "\n".join(lines)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)[:1200]
        except Exception:  # noqa: BLE001
            return str(value)[:1200]
    return str(value)[:800]


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
        formatted: list[str] = []
        for k, v in related_context.items():
            if v in (None, "", [], {}):
                continue
            rendered = _format_context_value(v)
            if rendered:
                formatted.append(f"- {k}: {rendered}")
        if formatted:
            parts.append("## 底稿数据\n" + "\n".join(formatted) + "\n")
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
        logger.warning("G6 SPPI AI: project context 加载失败: %s", e)
    return ctx
