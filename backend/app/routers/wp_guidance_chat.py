"""底稿编制指导面板端点

GET  /api/workpapers/{wp_id}/guidance — 获取底稿编制说明（静态）
POST /api/workpapers/{wp_id}/ai-chat — 底稿级 AI 对话（SSE streaming）
GET  /api/workpapers/{wp_id}/ai-chat/history — 对话历史
DELETE /api/workpapers/{wp_id}/ai-chat/history — 清除对话历史
PUT  /api/workpapers/{wp_id}/guidance/custom — 保存项目级自定义编制说明（P4 预留）

需求: 2.7, 2.8, 4.2, 4.3, 4.6, 4.7, 5.1, 9.1, 9.2, 9.3, 9.5, 9.6
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers", tags=["底稿编制指导"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class WpAiChatRequest(BaseModel):
    """底稿 AI 对话请求"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户提问")
    project_id: str = Field(..., description="项目 ID")
    year: int | None = Field(None, description="审计年度")
    wp_code: str | None = Field(None, description="底稿编码")
    wp_name: str | None = Field(None, description="底稿名称")


class CustomGuidanceRequest(BaseModel):
    """保存项目级自定义编制说明请求（P4 预留）"""

    content: str = Field(..., max_length=5000, description="自定义编制说明内容")
    project_id: str = Field(..., description="项目 ID")


@router.get("/{wp_id}/guidance")
async def get_workpaper_guidance(
    wp_id: str,
    sheet_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿编制说明

    按优先级从模板 sheet / header / static JSON / fallback 提取，
    结合 LRU + mtime 缓存。

    Args:
        sheet_code: 可选的 sheet 级编码（如 D0-1/D0-5），多 sheet 底稿切 tab 时传入。
            优先按 sheet_code 查找专属 guidance JSON，找不到回退到父码 wp_code。

    Returns:
        {wp_code, wp_name, source, complexity, guidance: {sections, raw_text}, recommended_questions}
    """
    # 验证 wp_id 格式
    try:
        wp_uuid = UUID(wp_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="无效的底稿 ID")

    # 查询底稿信息：working_papers → wp_index
    from app.models.workpaper_models import WorkingPaper, WpIndex

    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
        )
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_uuid)
    )

    result = await db.execute(stmt)
    row = result.first()

    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp_code = row.wp_code
    wp_name = row.wp_name or ""

    # 多 sheet 底稿：优先使用 sheet_code 获取专属 guidance（如 D0-1.json）
    # 找不到时回退到父码 wp_code（如 D0）
    effective_code = sheet_code if sheet_code else wp_code

    # 尝试定位模板路径（从 wp_templates 按 wp_code 推导）
    template_path = _resolve_template_path(wp_code)

    # 调用 GuidanceService 获取编制说明
    from app.services.wp_guidance_service import GuidanceService

    service = GuidanceService()
    guidance_response = await service.get_guidance(
        wp_code=effective_code,
        wp_name=wp_name,
        template_path=template_path,
    )

    # 如果 sheet_code 级 guidance 提取结果是 fallback（通用提示），再试父码
    if sheet_code and guidance_response.get("source") == "fallback":
        guidance_response = await service.get_guidance(
            wp_code=wp_code,
            wp_name=wp_name,
            template_path=template_path,
        )

    # 注入 ai_enabled 字段供前端 Tab 显隐（读 feature flag）
    from app.core.config import settings
    guidance_response["ai_enabled"] = settings.WP_AI_SERVICE_ENABLED

    return guidance_response


def _resolve_template_path(wp_code: str):
    """尝试从 wp_templates 目录按 wp_code 推导模板路径

    按循环字母（wp_code 首字母）+ 文件名模式查找。
    """
    from pathlib import Path

    templates_root = Path(__file__).resolve().parent.parent.parent / "wp_templates"

    if not templates_root.exists():
        return None

    # 从 wp_code 提取循环字母（首字母）
    if not wp_code:
        return None

    cycle_letter = wp_code[0].upper()
    cycle_dir = templates_root / cycle_letter

    if not cycle_dir.exists():
        return None

    # 在循环目录下查找匹配的模板文件
    # 尝试精确匹配：{wp_code}.xlsx, {wp_code}.docx
    for ext in (".xlsx", ".xls", ".docx"):
        candidate = cycle_dir / f"{wp_code}{ext}"
        if candidate.exists():
            return candidate

    # 尝试模糊匹配：文件名包含 wp_code
    for f in cycle_dir.iterdir():
        if f.is_file() and wp_code in f.stem and f.suffix.lower() in (".xlsx", ".xls", ".docx"):
            return f

    return None


# ---------------------------------------------------------------------------
# PUT /api/workpapers/{wp_id}/guidance/custom — 保存项目级自定义编制说明（P4 预留）
# ---------------------------------------------------------------------------


@router.put("/{wp_id}/guidance/custom")
async def save_custom_guidance(
    wp_id: str,
    request: CustomGuidanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存项目级自定义编制说明（P4 预留端点）

    存储到 field_overrides，scope="wp_guidance_custom:{wp_code}:{project_id}"

    设计意图：
    - 项目经理可为特定底稿添加项目级补充编制说明
    - 补充说明在面板「补充说明」区域展示
    - 不覆盖系统提取的编制说明，仅作补充
    """
    # TODO(P4): Implement save logic using field_overrides
    # 预期实现：
    # 1. 验证 wp_id 存在
    # 2. 验证 project_id 有效
    # 3. 构建 scope = f"wp_guidance_custom:{wp_code}:{project_id}"
    # 4. 写入 field_overrides 表（UPSERT）
    # 5. 返回保存结果
    raise HTTPException(status_code=501, detail="功能即将上线（P4）")


# ---------------------------------------------------------------------------
# POST /api/workpapers/{wp_id}/ai/generate-text — 通用 AI 文本生成（单次，非流式）
# ---------------------------------------------------------------------------


class AiGenerateTextRequest(BaseModel):
    prompt: str = ""
    context: dict[str, str] = {}
    existingContent: str = ""
    section: str = ""


class AiGenerateTextResponse(BaseModel):
    content: str


# section → 默认 system prompt 映射（仅当调用方未显式传 prompt 时作兜底）。
# 该端点对 section 不做拒绝式白名单校验，任意 section 均放行；此处仅为
# voucher-review / cutoff-review 等已知场景提供针对性的默认复核提示词。
_SECTION_PROMPTS: dict[str, str] = {
    # 抽凭回写后复核：识别金额异常/无原始凭证/对方科目异常/重复入账/跨期等
    "voucher-review": (
        "你是资深审计师。请基于提供的抽样回写凭证，识别潜在异常"
        "（金额异常、缺少原始凭证、对方科目异常、重复入账、跨期确认等），"
        "逐条指出可疑凭证及理由，并给出复核意见，作为审计说明草稿供人工确认。"
    ),
    # 截止性测试回写后复核：识别收入/成本/费用的跨期确认问题
    "cutoff-review": (
        "你是资深审计师。请基于提供的截止性测试回写凭证，识别是否存在跨期确认"
        "（收入/成本/费用提前或滞后确认）问题，逐条指出可疑凭证及理由，"
        "并给出截止准确性的复核意见，作为审计说明草稿供人工确认。"
    ),
    # ─── J1 应付职工薪酬 附注披露说明（源模板逐段口径，spec j1-disclosure-template-alignment R5）
    #
    # 🔴 这 6 个 section 原本落到本模块末尾的通用兜底
    # 「请根据提供的上下文信息生成专业的审计文本。」——等于放任模型自造披露内容。
    # 每条 prompt 必须写明源模板 / CAS 9 口径 + 「不得虚构」约束。
    "j1-disclosure-listed-short-term-note": (
        "你是资深审计师，正在编制上市公司附注「应付职工薪酬 — 短期薪酬」的说明文字"
        "（对应源模板说明区两条要求）。请分两点撰写：①本期为职工提供的各项非货币性福利的"
        "形式及其计算依据；②依据短期利润分享计划提供的职工薪酬的计算依据。"
        "口径依 CAS 9《职工薪酬》。**只使用上下文给出的数据，不得虚构福利形式、比例或金额**；"
        "上下文未提供的事实用「（待补充：xxx）」占位，不要编造。"
    ),
    "j1-disclosure-listed-post-employment-note": (
        "你是资深审计师，正在编制上市公司附注「应付职工薪酬 — 设定提存计划」的说明文字。"
        "请说明企业设立或参与的设定提存计划的性质（基本养老保险、失业保险、企业年金等）、"
        "计算缴费金额的公式或依据（计提基数与费率）。口径依 CAS 9；其他长期职工福利仅指"
        "符合设定提存计划条件的部分。**不得虚构费率、缴费基数或计划名称**，"
        "上下文未提供的用「（待补充：xxx）」占位。"
    ),
    "j1-disclosure-listed-severance-note": (
        "你是资深审计师，正在编制上市公司附注「应付职工薪酬 — 辞退福利」的说明文字。"
        "请说明辞退福利的性质、内容及计算依据，并区分预期在报告期末后 12 个月内完全支付的"
        "部分与超过 1 年支付的部分（后者在长期应付职工薪酬列示）。口径依 CAS 9。"
        "**不得虚构裁员方案、人数或补偿标准**，上下文未提供的用「（待补充：xxx）」占位。"
    ),
    "j1-disclosure-soe-soeNonMonetary-note": (
        "你是资深审计师，正在编制国有企业附注「应付职工薪酬」说明第 1 条。"
        "请说明企业本期为职工提供的各项非货币性福利的形式、金额及其计算依据"
        "（国企口径下非货币性福利并入「其他短期薪酬」列示，不单独设行）。口径依 CAS 9。"
        "**只使用上下文给出的数据，不得虚构福利形式或金额**，未提供的用「（待补充：xxx）」占位。"
    ),
    "j1-disclosure-soe-soeDefinedContribution-note": (
        "你是资深审计师，正在编制国有企业附注「应付职工薪酬」说明第 2 条。"
        "请说明企业设立或参与的设定提存计划的性质，以及计算缴费金额的公式或依据"
        "（基本养老保险、失业保险、企业年金缴费的计提基数与费率）。口径依 CAS 9。"
        "**不得虚构费率或缴费基数**，未提供的用「（待补充：xxx）」占位。"
    ),
    "j1-disclosure-soe-soeDefinedBenefit-note": (
        "你是资深审计师，正在编制国有企业附注「应付职工薪酬」说明第 3 条。"
        "若企业存在设定受益计划，请说明该计划的特征及与之相关的风险、在财务报表中确认的"
        "金额及其变动、对未来现金流的影响、重大精算假设及有关敏感性分析等，"
        "并注明「设定受益计划情况详见附注八、54」。口径依 CAS 9。"
        "**不得虚构精算假设（折现率、死亡率、离职率等）或计划资产数据**；"
        "若企业不存在设定受益计划，直接说明「本公司不存在设定受益计划」，不要编造内容。"
    ),
    # ─── D4 营业收入 8 个附注披露文本域（spec d4-four-table-extraction Task 7.2）────
    # 前端 wpAiText 传 section='d4-disc-note-N'，本端点不做白名单拒绝，
    # 但匹配到专属 prompt 后可避免退化到无指令泛化生成。
    "d4-disc-note-1": (
        "撰写（1）营业收入和营业成本主表的附注说明。依据审定表 D4-1 的主营/其他业务收入与成本"
        "数据，说明构成与变动原因。不得虚构未提供的数据或事实，缺失部分用「待补充」占位。"
    ),
    "d4-disc-note-2": (
        "撰写（2）按行业或产品类型划分的营业收入与营业成本说明。依据各行业/产品的本期与上期"
        "收入及成本数据，说明各板块收入贡献与变动趋势。不得虚构未提供的行业或金额数据。"
    ),
    "d4-disc-note-3": (
        "撰写（3）按地区划分的营业收入与营业成本说明。依据各地区本期与上期收入及成本数据，"
        "说明地区分布特征及变动原因。不得虚构未提供的地区名称或金额，缺失用「待补充」占位。"
    ),
    "d4-disc-note-4": (
        "撰写（4）收入分解信息的说明。依据按商品转让时间维度划分的分解表，说明各类别收入"
        "确认时点或时段选择依据与占比情况。不得虚构分解维度或未提供的金额数据。"
    ),
    "d4-disc-note-5": (
        "撰写（5）履约义务相关信息。依据 CAS14 收入准则，说明履约义务的履行时间、重要支付"
        "条款、承诺转让商品的性质、代理人判断、退款义务与质量保证义务。"
        "不得虚构未提供的合同条款或交易安排，缺失部分用「待补充」占位。"
    ),
    "d4-disc-note-6": (
        "撰写（6）与剩余履约义务有关的信息。依据 CAS14 披露要求，说明分摊至尚未履行的"
        "履约义务的交易价格总额及预计确认为收入的时间安排；如采用简化操作方法应提供定性说明。"
        "不得虚构未提供的合同金额或时间安排。"
    ),
    "d4-disc-note-7": (
        "撰写（7）重大合同变更或交易价格调整说明。依据实际变更事项说明内容、会计处理方法"
        "及对收入确认的影响金额。不得虚构未提供的合同变更事项或金额。"
    ),
    "d4-disc-note-8": (
        "撰写（8）试运行销售收入说明。依据准则解释第 15 号，说明固定资产试运行收入与研发"
        "样品销售收入的确认依据、金额构成及成本抵减情况。不得虚构未提供的试运行数据或金额。"
    ),
}


@router.post("/{wp_id}/ai/generate-text")
async def workpaper_ai_generate_text(
    wp_id: str,
    request: AiGenerateTextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """通用底稿级 AI 文本生成 — 单次调用返回生成内容

    用于底稿编制中的各类 AI 辅助文本生成（控制描述、审计说明、例外描述等）。
    接收 prompt（系统指令）+ context（字段上下文）+ existingContent（已有内容），
    拼接为单轮请求发送给 LLM，返回生成文本。
    """
    from app.services.llm_client import chat_completion
    from app.core.config import settings
    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：AI 上下文构造 / LLM 调用之前完成授权判定（Req 8.11 "AI gate 后构造 context"）。
    # wp_id 为字符串 → 转 UUID；非法/不存在 → gate 反查失败 → 统一 404。
    try:
        _wp_uuid = UUID(str(wp_id))
    except (ValueError, TypeError):
        from app.services.wp_visibility.denial import ExternalNotFound
        raise ExternalNotFound()
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.ai_generate", action="ai_generate", method="POST",
        wp_id=_wp_uuid, entry_family="ai",
        route_name="/api/workpapers/{wp_id}/ai/generate-text",
    )

    if not settings.WP_AI_SERVICE_ENABLED:
        raise HTTPException(status_code=503, detail="AI 服务未启用")

    # 构建 LLM 输入：显式 prompt 优先，其次按 section 兜底，最后通用默认
    system_msg = (
        request.prompt
        or _SECTION_PROMPTS.get(request.section)
        or "请根据提供的上下文信息生成专业的审计文本。"
    )
    user_parts = []
    if request.context:
        user_parts.append("【上下文信息】")
        for k, v in request.context.items():
            user_parts.append(f"- {k}：{v}")
    if request.existingContent:
        user_parts.append(f"\n【现有内容（可参考或改进）】\n{request.existingContent}")
    if request.section:
        user_parts.append(f"\n【目标字段】{request.section}")

    user_msg = "\n".join(user_parts) if user_parts else "请生成内容。"

    try:
        generated = await chat_completion(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            model=settings.DEFAULT_CHAT_MODEL,
            max_tokens=512,
        )
        content = generated if isinstance(generated, str) else ""
        return {"code": 200, "message": "success", "data": {"content": content}}
    except Exception as e:
        logger.warning("AI generate-text failed: %s", e)
        raise HTTPException(status_code=503, detail="AI 服务暂不可用")


# ---------------------------------------------------------------------------
# POST /api/workpapers/{wp_id}/ai-chat — 底稿级 AI 对话（SSE streaming）
# ---------------------------------------------------------------------------

_MAX_HISTORY_ROUNDS = 20  # 20 轮 = 40 条消息（user + assistant）


@router.post("/{wp_id}/ai-chat")
async def workpaper_ai_chat(
    wp_id: str,
    request: WpAiChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿级 AI 对话 — SSE streaming 响应

    注入底稿上下文（编制说明 + 项目信息 + 已填数据摘要）作为 system prompt，
    复用 doc_chat_persistence 实现对话历史持久化。

    需求: 4.2, 4.3, 4.6, 5.1, 9.1, 9.2, 9.3, 9.5
    """
    # 1. 验证 wp_id 格式
    try:
        wp_uuid = UUID(wp_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="无效的底稿 ID")

    # 2. 验证 project_id
    try:
        project_uuid = UUID(request.project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="无效的 project_id")

    # 3. 查询底稿信息
    from app.models.workpaper_models import WorkingPaper, WpIndex

    stmt = (
        select(
            WpIndex.wp_code,
            WpIndex.wp_name,
            WorkingPaper.project_id,
        )
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_uuid)
    )
    result = await db.execute(stmt)
    wp_row = result.first()

    if wp_row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp_code = request.wp_code or wp_row.wp_code
    wp_name = request.wp_name or wp_row.wp_name or ""

    # 4. 获取项目信息（client_name, audit_period, business_category）
    from app.models.core import Project

    project_result = await db.execute(
        select(
            Project.client_name,
            Project.audit_period_start,
            Project.audit_period_end,
            Project.business_category,
        ).where(Project.id == project_uuid)
    )
    project_row = project_result.first()

    client_name = ""
    audit_period = ""
    business_category = ""
    if project_row:
        client_name = project_row.client_name or ""
        start = project_row.audit_period_start
        end = project_row.audit_period_end
        if start and end:
            audit_period = f"{start.isoformat()} 至 {end.isoformat()}"
        elif end:
            audit_period = f"至 {end.isoformat()}"
        business_category = project_row.business_category or ""

    # 5. 获取编制说明（guidance_text）
    guidance_text = ""
    try:
        from app.services.wp_guidance_service import GuidanceService

        service = GuidanceService()
        template_path = _resolve_template_path(wp_code)
        guidance_resp = await service.get_guidance(
            wp_code=wp_code,
            wp_name=wp_name,
            template_path=template_path,
        )
        guidance_text = guidance_resp.get("guidance", {}).get("raw_text", "")
    except Exception as e:
        logger.warning(f"获取编制说明失败 wp_code={wp_code}: {e}")

    # 6. 推导 component_type（从 wp_code 模式推断）
    component_type = _infer_component_type(wp_code)

    # 7. 构建上下文
    from app.services.context_injector import ContextInjector, WpChatContext

    ctx = WpChatContext(
        wp_code=wp_code,
        wp_name=wp_name,
        component_type=component_type,
        client_name=client_name,
        audit_period=audit_period,
        business_category=business_category,
        guidance_text=guidance_text,
        filled_data_summary="",  # P1 阶段暂不注入已填数据
    )

    injector = ContextInjector()
    system_prompt = injector.build_system_prompt(ctx)

    # 8. 返回 SSE streaming response
    return StreamingResponse(
        _stream_wp_chat(
            wp_id=wp_id,
            query=request.query,
            system_prompt=system_prompt,
            user=current_user,
            project_id=project_uuid,
            wp_code=wp_code,
        ),
        media_type="text/event-stream",
    )


async def _stream_wp_chat(
    wp_id: str,
    query: str,
    system_prompt: str,
    user: User,
    project_id: UUID,
    wp_code: str = "",
) -> AsyncGenerator[str, None]:
    """SSE streaming 生成器：构建 messages → ai_service streaming → 收集回复 → 持久化

    ⚠️ 自建独立 session：FastAPI 在端点 return StreamingResponse 时即关闭 get_db
    的请求级 session，而本生成器在 response 返回后才被 ASGI 消费执行。

    客户端断开时 try/finally 确保部分响应也被持久化到 DB。
    """
    from app.core.database import async_session
    from app.services import doc_chat_persistence
    from app.services.ai_service import AIService
    from app.services.context_injector import ContextInjector

    async with async_session() as db:
        # ─── 检查 LLM 熔断器状态（提前 503 避免不必要的 RAG/history 查询）──
        try:
            ai_service = AIService(db)
            if hasattr(ai_service, '_breaker') and ai_service._breaker and ai_service._breaker.state.name == 'open':
                yield f"data: {json.dumps({'type': 'error', 'data': 'AI 服务暂不可用（熔断器已开启）'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'data': {}}, ensure_ascii=False)}\n\n"
                return
        except Exception as e:
            logger.debug("检查 LLM 熔断器状态失败，继续正常流程: %s", e)

        # ─── RAG 知识库检索（降级：失败时继续无 RAG） ───────────────────
        citations: list[dict] = []
        rag_context = ""
        try:
            from app.services.knowledge_index_service import KnowledgeIndexService

            ks = KnowledgeIndexService(db)
            search_text = f"{wp_code} {query}"
            hits = await ks.semantic_search(
                project_id, search_text, scope="knowledge_doc", top_k=5
            )
            if hits:
                rag_parts: list[str] = []
                for hit in hits[:5]:
                    text = hit.get("content", "")[:1000]  # 500 tokens ≈ 1000 chars
                    source = hit.get("source_name", "")
                    rag_parts.append(f"[{source}] {text}")
                    citations.append({
                        "source_type": "knowledge_doc",
                        "source_id": hit.get("id", ""),
                        "source_name": source,
                    })
                rag_context = "\n\n相关知识库参考：\n" + "\n---\n".join(rag_parts)
        except Exception as e:
            logger.warning(f"RAG 检索失败 (降级继续): {e}")

        # 将 RAG 上下文追加到 system prompt
        if rag_context:
            system_prompt += rag_context

        # ─── 发送 citations 作为首个 SSE 事件 ─────────────────────────────
        if citations:
            yield f"data: {json.dumps({'type': 'citations', 'data': citations}, ensure_ascii=False)}\n\n"

        # 获取/创建会话（doc_type="workpaper", doc_id=wp_id）
        session = await doc_chat_persistence.get_or_create_session(
            db, "workpaper", wp_id, user.id, project_id
        )

        # 读取历史（限 20 轮 = 40 条消息）
        history = await doc_chat_persistence.get_history(
            db, "workpaper", wp_id, user.id, limit=_MAX_HISTORY_ROUNDS * 2
        )

        # 构建 LLM messages: [system] + history + [user query]
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        # 添加历史消息（最近 20 轮）
        for msg in history[-((_MAX_HISTORY_ROUNDS) * 2):]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        # 当前用户消息
        messages.append({"role": "user", "content": query})

        # 合并 system 消息（vLLM 约束）
        messages = ContextInjector.merge_system_messages(messages)

        # 记录用户消息到 DB + 提交
        await doc_chat_persistence.append_message(db, session, "user", query)
        await db.commit()

        # 流式调用 ai_service — try/finally 确保部分响应持久化
        full_response = ""
        response_saved = False

        try:
            try:
                stream_gen = await ai_service.chat_completion(
                    messages=messages,
                    stream=True,
                    temperature=0.3,
                )
                async for chunk in stream_gen:
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'data': chunk}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.exception("workpaper_ai_chat streaming 失败")
                error_msg = "AI 服务暂不可用"
                if "熔断" in str(e) or "circuit" in str(e).lower():
                    error_msg = "AI 服务暂不可用（熔断器已开启）"
                yield f"data: {json.dumps({'type': 'error', 'data': error_msg}, ensure_ascii=False)}\n\n"

            # 记录助手回复到 DB + 提交（正常完成路径）
            if full_response:
                await doc_chat_persistence.append_message(db, session, "assistant", full_response)
            await db.commit()
            response_saved = True

            # 发送完成事件
            yield f"data: {json.dumps({'type': 'done', 'data': {}}, ensure_ascii=False)}\n\n"
        finally:
            # 确保部分响应也持久化（客户端断开时 generator 被 close）
            if not response_saved and full_response:
                try:
                    await doc_chat_persistence.append_message(db, session, "assistant", full_response)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"部分响应持久化失败: {e}")


# ---------------------------------------------------------------------------
# GET /api/workpapers/{wp_id}/ai-chat/history — 对话历史
# ---------------------------------------------------------------------------


@router.get("/{wp_id}/ai-chat/history")
async def get_wp_chat_history(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿 AI 对话历史

    需求: 4.6, 9.6
    """
    from app.services import doc_chat_persistence

    history = await doc_chat_persistence.get_history(
        db, "workpaper", wp_id, current_user.id, limit=_MAX_HISTORY_ROUNDS * 2
    )
    return {"messages": history, "total": len(history)}


# ---------------------------------------------------------------------------
# DELETE /api/workpapers/{wp_id}/ai-chat/history — 清除对话历史
# ---------------------------------------------------------------------------


@router.delete("/{wp_id}/ai-chat/history")
async def clear_wp_chat_history(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除底稿 AI 对话历史

    需求: 4.7, 9.6
    """
    from app.services import doc_chat_persistence

    cleared = await doc_chat_persistence.clear_history(
        db, "workpaper", wp_id, current_user.id
    )
    await db.commit()
    return {"success": True, "cleared": cleared}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _infer_component_type(wp_code: str) -> str:
    """从 wp_code 推断 component_type（简化版，不依赖完整注册表）"""
    if not wp_code:
        return "unknown"

    # 尝试从注册表获取
    try:
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE

        if wp_code in _WP_CODE_OVERRIDE:
            return _WP_CODE_OVERRIDE[wp_code]
    except ImportError:
        pass

    # 降级：按模式推断
    if wp_code.endswith("A") and len(wp_code) > 1:
        return "a-program-console"
    if wp_code.endswith("-1") and len(wp_code) > 2:
        return "d-form-table"
    return "univer"


# ---------------------------------------------------------------------------
# POST /api/workpapers/{wp_id}/ai-generate-notes — AI 预填充审计说明
# ---------------------------------------------------------------------------


class ConfirmationNotesGenRequest(BaseModel):
    """AI 生成函证审计说明请求"""

    project_id: str = Field(..., description="项目 ID")
    wp_code: str | None = Field(None, description="底稿编码")
    # 从前端传入的函证统计摘要（避免后端再查 parse_data）
    total_count: int = Field(0, description="函证总笔数")
    total_amount: float = Field(0, description="函证总金额")
    replied_count: int = Field(0, description="已回函笔数")
    matched_count: int = Field(0, description="相符笔数")
    unreplied_count: int = Field(0, description="未回函笔数")
    coverage_pct: float = Field(0, description="覆盖率%")
    account_types: list[str] = Field(default_factory=list, description="涉及科目")
    # 用户可选：已有的部分填写内容（AI 补充完善）
    existing_notes: dict | None = Field(None, description="已有审计说明（可选）")


@router.post("/{wp_id}/ai-generate-notes")
async def generate_confirmation_notes(
    wp_id: str,
    req: ConfirmationNotesGenRequest,
    current_user: User = Depends(get_current_user),
):
    """根据函证统计数据，调用 LLM 生成审计说明初稿

    LLM 不可用时降级为规则生成模板文本。
    """
    from app.core.config import settings

    # 构建 prompt 上下文
    stats_text = (
        f"函证统计摘要：\n"
        f"- 发函总数：{req.total_count} 笔\n"
        f"- 发函总额：{req.total_amount:,.2f} 元\n"
        f"- 已回函：{req.replied_count} 笔\n"
        f"- 相符：{req.matched_count} 笔\n"
        f"- 未回函：{req.unreplied_count} 笔\n"
        f"- 覆盖率：{req.coverage_pct:.1f}%\n"
        f"- 涉及科目：{', '.join(req.account_types) if req.account_types else '未分类'}\n"
    )

    system_prompt = (
        "你是一位资深审计经理，正在编制函证程序的审计工作底稿。"
        "请根据以下函证统计数据，生成5个维度的审计说明初稿。"
        "返回 JSON 格式（不要 markdown code block），字段为：\n"
        '{"note_general": "...", "note_exception": "...", "note_unreplied": "...", '
        '"note_alternative": "...", "note_other": "..."}\n\n'
        "要求：\n"
        "1. note_general：函证总体情况概述（发函范围、方式、时间安排）\n"
        '2. note_exception：异常情况说明（差异、退函等，无异常则写"本次函证未发现异常情况"）\n'
        "3. note_unreplied：未回函处理方案\n"
        "4. note_alternative：替代程序说明（检查期后收款/合同/出库单等）\n"
        "5. note_other：其他事项（电子函证可靠性、舞弊考量等，可为空）\n\n"
        "语言简洁专业，符合中国注册会计师审计准则用语习惯。每项 50-150 字。"
    )

    # 尝试 LLM
    llm_enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
    if llm_enabled:
        try:
            from app.services.llm_client import chat_completion

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": stats_text},
            ]
            raw = await chat_completion(messages, temperature=0.4, max_tokens=1000)
            # 解析 JSON
            import re
            # 尝试提取 JSON（LLM 可能返回 markdown code block）
            json_match = re.search(r'\{[^{}]*"note_general"[^{}]*\}', raw, re.DOTALL)
            if json_match:
                notes = json.loads(json_match.group())
                return {
                    "notes": notes,
                    "source": "llm",
                }
            # JSON 解析失败，降级
            logger.warning("LLM 返回内容无法解析为 JSON，降级为规则生成")
        except Exception as e:
            logger.warning(f"LLM 生成审计说明失败: {e}，降级为规则生成")

    # 降级：规则生成模板文本
    reply_rate = (
        f"{req.replied_count}/{req.total_count}"
        if req.total_count > 0
        else "0/0"
    )
    coverage_str = f"{req.coverage_pct:.1f}%" if req.coverage_pct > 0 else "—"
    acct_str = "、".join(req.account_types[:5]) if req.account_types else "相关科目"

    notes = {
        "note_general": (
            f"本次审计共向 {req.total_count} 家单位发出函证，"
            f"涉及{acct_str}等科目，"
            f"函证金额合计 {req.total_amount:,.2f} 元。"
            f"函证方式以积极式为主，发函覆盖率 {coverage_str}。"
        ),
        "note_exception": (
            "本次函证未发现重大异常情况。"
            if req.matched_count == req.replied_count
            else f"函证过程中发现 {req.replied_count - req.matched_count} 笔不符项，"
            f"差异原因待进一步核查（详见 D0-4 差异调节表）。"
        ),
        "note_unreplied": (
            f"截至审计报告日，共有 {req.unreplied_count} 家单位未回函。"
            f"对未回函单位已执行替代审计程序以获取充分适当的审计证据。"
            if req.unreplied_count > 0
            else "所有函证对象均已回函，无需执行替代程序。"
        ),
        "note_alternative": (
            "对未回函单位，已执行以下替代程序：\n"
            "1. 检查期后收款/付款记录\n"
            "2. 核对销售合同/采购订单及出库/入库单\n"
            "3. 检查相关发票及对账单"
            if req.unreplied_count > 0
            else "本次函证全部回函，未执行替代程序。"
        ),
        "note_other": (
            "其他需关注事项：无。"
        ),
    }

    return {
        "notes": notes,
        "source": "rule",
    }
