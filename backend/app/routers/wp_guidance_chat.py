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
