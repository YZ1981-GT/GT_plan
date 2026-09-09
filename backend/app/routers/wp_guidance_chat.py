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
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.routers.wp_guidance_chat_stream import _MAX_HISTORY_ROUNDS, _stream_wp_chat
from app.routers.wp_guidance_section_prompts import _SECTION_PROMPTS

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


async def _load_runtime_custom_guidance_entries(
    *,
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    wp_code: str,
):
    """只读已确认 custom guidance；普通补充文本不进入 exact 清册。"""
    from app.services.field_override_service import FieldOverrideService
    from app.services.guidance_inventory import normalize_runtime_custom_guidance
    from app.services.project_audit_year import fetch_project_audit_year

    year = await fetch_project_audit_year(db, project_id)
    if year is None:
        return ()
    scope = f"wp_guidance_custom:{wp_code}:{project_id}"
    batch = await FieldOverrideService(db).get_batch(project_id, year, scope)
    return normalize_runtime_custom_guidance(batch, wp_id=str(wp_id))


@router.get("/{wp_id}/guidance")
async def get_workpaper_guidance(
    wp_id: str,
    sheet_code: str | None = None,
    sheet_name: str | None = None,
    whole_workbook: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """获取版本化、render-membership 约束的编制说明。

    Task 8 AC#1: GuidanceMembershipError → 403。
    Task 9 AC#1: 响应携带 service 计算的 ETag / responseVersion；
    命中 If-None-Match 时返回 304 短路（route 无 request 时跳过协商）。
    """
    if_none_match = request.headers.get("if-none-match") if request is not None else None
    try:
        wp_uuid = UUID(wp_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="无效的底稿 ID")

    # 先复用九维门完成用户/项目/候选 sheet 授权，再读取 render 内容。最终
    # membership 仍以 render-config sheets 为准，static/template 不得反向授权。
    from app.services import guidance_inventory as inventory
    from app.services import guidance_source_refs
    from app.services.wp_visibility.entry_integration import gate_wp

    gate_sheet_code = sheet_code or inventory.extract_sheet_code(sheet_name)
    await gate_wp(
        db,
        current_user,
        entrypoint="workpaper.dedicated_subroute",
        action="dedicated_read",
        method="GET",
        wp_id=wp_uuid,
        route_name="get_workpaper_guidance",
        entry_family="workpaper",
        requested_sheet_key=gate_sheet_code,
    )

    from app.models.workpaper_models import WorkingPaper, WpIndex

    stmt = (
        select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_uuid,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WpIndex.is_deleted == False,  # noqa: E712
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    working_paper, wp_index = row
    wp_code = wp_index.wp_code
    wp_name = wp_index.wp_name or ""

    from pathlib import Path
    from pathlib import Path
    from app.routers import wp_render_config, wp_render_config_helpers

    raw_template_path = wp_render_config_helpers._resolve_template_path(working_paper, wp_code)
    template_path = Path(raw_template_path) if raw_template_path else None
    # inventory 分母必须基于 parent 的完整最终 render manifest；请求 sheet 只在
    # resolve_render_sheet_context 阶段选择，不能先过滤成单页再冒充全量清册。
    render_response = await wp_render_config._get_render_config_impl(
        wp_uuid,
        None,
        db,
        current_user,
    )
    render_sheets = render_response.get("sheets", []) if isinstance(render_response, dict) else []

    try:
        resolved_sheet_code, sheet_identity_reason, _matched_fact = (
            inventory.resolve_render_sheet_context(
                parent_wp_code=wp_code,
                render_sheets=render_sheets,
                requested_sheet_code=sheet_code,
                requested_sheet_name=sheet_name,
                whole_workbook=whole_workbook,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 若 canonical identity 只能由 render manifest 裁决，再以该 key 做第二次 sheet gate。
    if resolved_sheet_code and resolved_sheet_code != gate_sheet_code:
        await gate_wp(
            db,
            current_user,
            entrypoint="workpaper.dedicated_subroute",
            action="dedicated_read",
            method="GET",
            wp_id=wp_uuid,
            route_name="get_workpaper_guidance",
            entry_family="workpaper",
            requested_sheet_key=resolved_sheet_code,
        )

    import asyncio

    try:
        authority_snapshot = await asyncio.to_thread(
            guidance_source_refs.build_template_authority_snapshot,
            parent_wp_code=wp_code,
            render_sheets=render_sheets,
            active_template_path=template_path,
            template_version=str(render_response.get("template_version") or "") or None,
            template_origin=str(getattr(working_paper, "source_type", "") or "") or None,
        )
        source_ref_contexts = guidance_source_refs.build_source_ref_contexts(
            authority_snapshot,
            render_sheets,
        )
        static_entries, template_facts, exemptions = await asyncio.gather(
            asyncio.to_thread(
                inventory.build_static_guidance_inventory,
                source_ref_contexts=source_ref_contexts,
            ),
            asyncio.to_thread(
                inventory.load_template_source_facts,
                wp_code,
                template_path=template_path,
                template_version=str(render_response.get("template_version") or "") or None,
                template_origin=str(getattr(working_paper, "source_type", "") or "") or None,
            ),
            asyncio.to_thread(inventory.load_runtime_exemptions, wp_code),
        )
        custom_entries = await _load_runtime_custom_guidance_entries(
            db=db,
            project_id=working_paper.project_id,
            wp_id=wp_uuid,
            wp_code=wp_code,
        )
        runtime_inventory = await asyncio.to_thread(
            inventory.build_runtime_guidance_inventory,
            parent_wp_code=wp_code,
            render_sheets=render_sheets,
            template_facts=template_facts,
            static_entries=static_entries,
            custom_entries=custom_entries,
            exemptions=exemptions,
            include_whole_workbook_context=whole_workbook,
        )
        runtime_entry = inventory.find_runtime_inventory_entry(
            runtime_inventory,
            sheet_code=resolved_sheet_code,
            sheet_name=sheet_name,
            whole_workbook=whole_workbook,
        )
    except (OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("guidance runtime inventory 无效 wp_id=%s wp_code=%s: %s", wp_id, wp_code, exc)
        raise HTTPException(status_code=503, detail=f"编制说明清册无效：{exc}") from exc

    from app.services.wp_guidance_service import GuidanceService

    guidance_response = await GuidanceService().resolve_guidance(
        parent_wp_code=wp_code,
        requested_sheet_code=resolved_sheet_code,
        wp_name=wp_name,
        parent_template_path=template_path,
        whole_workbook=whole_workbook,
        runtime_entry=runtime_entry,
        inventory_facts_digest=runtime_inventory.facts_digest,
        inventory_run_id=runtime_inventory.run_id,
    )
    guidance_response.update(
        {
            "requested_sheet_name": sheet_name,
            "sheet_identity_reason": sheet_identity_reason,
            "whole_workbook": whole_workbook,
            "inventory_run_id": runtime_inventory.run_id,
            "inventory_facts_digest": runtime_inventory.facts_digest,
            "inventory_entry_id": runtime_entry.entry_id if runtime_entry else None,
            "inventory_entry_digest": runtime_entry.entry_digest if runtime_entry else None,
            "runtime_guidance_status": runtime_entry.exact_status if runtime_entry else None,
            "stale_reasons": list(runtime_entry.stale_reasons) if runtime_entry else [],
            "guidance_required": runtime_entry.required if runtime_entry else None,
            "guidance_context_kind": runtime_entry.context_kind if runtime_entry else None,
            "template_authority_digest": authority_snapshot.facts_digest,
            "template_authority_blockers": list(authority_snapshot.blockers),
        }
    )

    from app.core.config import settings

    guidance_response["ai_enabled"] = settings.WP_AI_SERVICE_ENABLED

    # Task 9 AC#1：命中 If-None-Match 时以 304 短路，避免重复传输不变内容。
    etag = guidance_response.get("etag")
    if if_none_match and etag and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return guidance_response


def _resolve_template_path(wp_code: str):
    """AI chat 兼容入口；guidance GET 已复用实例优先的 render resolver。"""
    from app.services.wp_template_finder import find_template_file_any

    return find_template_file_any(wp_code)


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
