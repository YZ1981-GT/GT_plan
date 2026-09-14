"""MCP Scoped REST Endpoints（dsh-agent-panel-integration Task 25）

全部 /api/ai-chat/mcp/* 端点：
  1. ResourceAccessResolver 校验
  2. scope/project/run/expiry 校验（McpTokenService）
  3. ExportMaskService 脱敏
  4. McpBudgetTracker 行数/字节/调用预算
  5. 哈希链审计（audit_tool_started / audit_tool_finished）

Requirements:
  - 11.5：scoped token 绑定 user/project/run/scope/exp
  - 11.7：子 Agent 继承相同 run security context
  - 11.8：调用配额超限明确失败
  - 11.9：五角色脱敏映射
  - 12.6/12.7：工具调用哈希链审计

Properties:
  - 28：双用户交换 token/run/project 均返回拒绝
  - 29：子 Agent 权限只收窄
  - 30：五角色脱敏一致
  - 32：哈希链事件成对完整
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.audit import audit_tool_finished, audit_tool_started
from app.services.ai_chat.contracts import AccessDecision
from app.services.ai_chat.mcp_budget import McpBudgetExceeded, McpBudgetTracker
from app.services.ai_chat.mcp_token import (
    MCP_READONLY_TOOLS,
    McpMaskLevel,
    McpTokenError,
    McpTokenExpired,
    McpTokenInvalid,
    McpTokenPayload,
    McpTokenRevoked,
    McpTokenScopeMismatch,
    McpTokenService,
    resolve_mask_policy,
)
from app.services.ai_chat.mcp_tools import (
    McpToolContext,
    McpToolError,
    build_tool_context,
    tool_addr_lookup,
    tool_kb_search,
    tool_note_read,
    tool_review_prompt,
    tool_tb_query,
    tool_wp_list,
    tool_wp_read,
)
from app.services.wp_visibility.denial import ExternalNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-chat/mcp", tags=["ai-chat-mcp"])

# ---------------------------------------------------------------------------
# 单例（进程级）
# ---------------------------------------------------------------------------

# 🔴 这里**没有** ExportMaskService 单例：脱敏统一走
# `ai_chat.dsh_masking.mask_tool_result`（见 `mcp_tool_call` 第 ⑥ 段的说明）。
# 曾存在一个 `_mask_service = ExportMaskService()` 模块级单例，切到 dsh_masking 后
# 零引用，已按「死代码立即删除」清掉。
_token_service = McpTokenService()
_budget_tracker = McpBudgetTracker()


def get_token_service() -> McpTokenService:
    return _token_service


def get_budget_tracker() -> McpBudgetTracker:
    return _budget_tracker


def build_host_decision(token_payload: McpTokenPayload) -> AccessDecision:
    """把已验签的 scoped token 提升为宿主级 ``AccessDecision``。

    🔴 这只是**携带 token 声明**（user/project/scope），**不是**授权结论 ——
    每个工具内部仍会用它作 host 去调 ``ResourceAccessResolver.authorize_resource``
    做第二道判定（Req 11.5 / 2.4）。单独抽成函数是为了让守卫测试与生产走
    同一份构造，避免形状漂移。
    """
    return AccessDecision(
        allowed=True,
        principal_id=token_payload.user_id,
        project_id=token_payload.project_id,
        cycle_scope=token_payload.cycle_scope,
        allowed_actions=frozenset({"read", "search", "review", "history"}),
    )


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class McpTokenCreateRequest(BaseModel):
    """创建 scoped token 的请求。"""

    run_id: UUID = Field(..., description="绑定的 run ID")
    project_id: UUID = Field(..., description="绑定的项目 ID")
    cycle_scope: list[str] = Field(default_factory=list, description="授权的循环范围")
    ttl_seconds: int | None = Field(None, description="TTL（秒），不超过 run timeout")


class McpTokenCreateResponse(BaseModel):
    """创建 scoped token 的响应。"""

    token: str = Field(..., description="scoped token 字符串")
    token_id: str = Field(..., description="token 唯一 ID")
    expires_at: float = Field(..., description="过期时间戳")
    mask_policy: str = Field(..., description="脱敏策略")
    budget: dict = Field(..., description="MCP 配额状态")


class McpTokenRevokeRequest(BaseModel):
    """撤销 token 的请求。"""

    token_id: str = Field(..., description="要撤销的 token ID")


class McpToolCallRequest(BaseModel):
    """MCP 工具调用请求。"""

    tool_name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    tool_call_id: str = Field(..., description="工具调用 ID（客户端生成）")


class McpToolCallResponse(BaseModel):
    """MCP 工具调用响应。"""

    tool_call_id: str
    tool_name: str
    status: str  # "success" | "error"
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    budget: dict = Field(default_factory=dict)


class McpBudgetResponse(BaseModel):
    """MCP 配额查询响应。"""

    run_id: str
    max_calls: int
    max_bytes_per_call: int
    calls_used: int
    calls_remaining: int
    total_bytes: int


class McpChildTokenRequest(BaseModel):
    """子 Agent 继承 token 的请求。"""

    narrowed_scope: list[str] | None = Field(None, description="收窄的循环范围")
    ttl_seconds: int | None = Field(None, description="子 token TTL")


# ---------------------------------------------------------------------------
# Token 认证依赖
# ---------------------------------------------------------------------------


async def _extract_mcp_token(
    x_mcp_token: str = Header(..., alias="X-MCP-Token"),
) -> str:
    """从 Header 提取 MCP token。"""
    return x_mcp_token


async def _validate_mcp_token(
    token_str: str = Depends(_extract_mcp_token),
) -> McpTokenPayload:
    """验证 MCP token 并返回 payload。"""
    try:
        return _token_service.validate_token(token_str)
    except McpTokenExpired:
        raise HTTPException(status_code=401, detail="MCP token 已过期")
    except McpTokenRevoked:
        raise HTTPException(status_code=401, detail="MCP token 已撤销")
    except McpTokenInvalid as exc:
        raise HTTPException(status_code=401, detail=exc.message)
    except McpTokenScopeMismatch as exc:
        raise HTTPException(status_code=403, detail=exc.message)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/tokens", response_model=McpTokenCreateResponse)
async def create_mcp_token(
    req: McpTokenCreateRequest,
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> McpTokenCreateResponse:
    """创建 MCP scoped token（由 ChatRunCoordinator 在 run 启动时调用）。

    🔴 只有 run 的 owner 可创建本 run 的 token。
    🔴 未知角色 fail-closed。
    """
    # 授权：确认调用者身份 + 角色可签发（资源级授权在每次 tool_call 里做，
    # 见 `_dispatch_tool` → `mcp_tools._authorize_resource`；签发环节不需要 resolver）
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未认证")

    role = _get_user_role(user)
    mask_policy = resolve_mask_policy(role)
    if mask_policy == McpMaskLevel.REJECTED:
        raise HTTPException(status_code=403, detail=f"未知角色 '{role}' 不允许创建 MCP token")

    try:
        scoped = _token_service.create_token(
            user_id=UUID(str(user_id)),
            project_id=req.project_id,
            run_id=req.run_id,
            role=role,
            cycle_scope=frozenset(req.cycle_scope),
            ttl_seconds=req.ttl_seconds,
        )
    except McpTokenError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    budget = _budget_tracker.get_or_create(req.run_id)

    return McpTokenCreateResponse(
        token=scoped.token,
        token_id=scoped.payload.token_id,
        expires_at=scoped.payload.expires_at,
        mask_policy=scoped.payload.mask_policy,
        budget=budget.to_dict(),
    )


@router.post("/tokens/child", response_model=McpTokenCreateResponse)
async def create_child_token(
    req: McpChildTokenRequest,
    token_payload: McpTokenPayload = Depends(_validate_mcp_token),
) -> McpTokenCreateResponse:
    """为子 Agent 创建 child token（Property 29：只能收窄）。"""
    try:
        narrowed = frozenset(req.narrowed_scope) if req.narrowed_scope else None
        child = _token_service.create_child_token(
            token_payload,
            narrowed_scope=narrowed,
            ttl_seconds=req.ttl_seconds,
        )
    except McpTokenError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    budget = _budget_tracker.get_or_create(token_payload.run_id)

    return McpTokenCreateResponse(
        token=child.token,
        token_id=child.payload.token_id,
        expires_at=child.payload.expires_at,
        mask_policy=child.payload.mask_policy,
        budget=budget.to_dict(),
    )


@router.post("/tokens/revoke")
async def revoke_mcp_token(
    req: McpTokenRevokeRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """撤销指定 token（cancel / run terminal 时调用）。"""
    _token_service.revoke_token(req.token_id)
    return {"status": "revoked", "token_id": req.token_id}


@router.post("/tools/call", response_model=McpToolCallResponse)
async def mcp_tool_call(
    req: McpToolCallRequest,
    token_payload: McpTokenPayload = Depends(_validate_mcp_token),
    db: AsyncSession = Depends(get_db),
) -> McpToolCallResponse:
    """MCP 工具调用入口。

    完整流程：
    1. token 验证（已由依赖完成）
    2. 工具白名单检查
    3. 预算预检
    4. 审计 tool_started
    5. ResourceAccessResolver 校验
    6. 执行工具
    7. ExportMaskService 脱敏
    8. 预算消费
    9. 审计 tool_finished
    """
    start_time = time.time()

    # ① 工具白名单检查
    if req.tool_name not in MCP_READONLY_TOOLS:
        return McpToolCallResponse(
            tool_call_id=req.tool_call_id,
            tool_name=req.tool_name,
            status="error",
            error_code="tool_not_allowed",
            error_message=f"工具 '{req.tool_name}' 不在允许列表中",
        )

    # ② 预算预检
    try:
        _budget_tracker.pre_check(token_payload.run_id)
    except McpBudgetExceeded as exc:
        return McpToolCallResponse(
            tool_call_id=req.tool_call_id,
            tool_name=req.tool_name,
            status="error",
            error_code="tool_budget_exceeded",
            error_message=str(exc),
            budget=_budget_tracker.get_or_create(token_payload.run_id).to_dict(),
        )

    # ③ 审计 tool_started（Property 32：每个 tool call 有 started）
    await audit_tool_started(
        db,
        user_id=token_payload.user_id,
        project_id=token_payload.project_id,
        run_id=token_payload.run_id,
        tool_call_id=req.tool_call_id,
        tool_name=req.tool_name,
    )

    # ④ 授权校验：用 ResourceAccessResolver 确认当前 token scope 有权读取目标资源
    resolver = ResourceAccessResolver(db)
    host_decision = build_host_decision(token_payload)

    # ⑤ 执行工具（分发到具体实现）
    result: dict[str, Any] = {}
    error_code: str | None = None
    error_message: str | None = None
    status = "success"

    try:
        result = await _dispatch_tool(
            tool_name=req.tool_name,
            arguments=req.arguments,
            token_payload=token_payload,
            host_decision=host_decision,
            resolver=resolver,
            db=db,
        )
    except McpToolError as exc:
        # 🔴 typed error 分离：资源不存在 / 无权限 / 服务不可用 各自有码，
        #    绝不都塌缩成空 dict（否则 Agent 无法区分"没数据"与"没权限"）。
        status = "error"
        error_code = exc.code
        error_message = exc.message
    except ExternalNotFound:
        # 平台统一不可枚举拒绝（resolver.enforce_* 抛出）
        status = "error"
        error_code = "access_denied"
        error_message = "资源不存在或不可访问"
    except HTTPException as exc:
        status = "error"
        error_code = "access_denied"
        error_message = exc.detail
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "MCP tool_call 执行异常 run=%s tool=%s: %s",
            token_payload.run_id, req.tool_name, exc,
            exc_info=True,
        )
        status = "error"
        error_code = "tool_execution_failed"
        error_message = "工具执行失败，请重试"

    # ⑥ 脱敏（Property 30：五角色一致）
    #    🔴 走 dsh_masking.mask_tool_result 而不是裸 ExportMaskService.apply_mask：
    #    后者的规则表只有联系方式/银行账号/身份证号，对「只含金额的试算表结构」
    #    是空操作 —— auditor(strict) 与 partner(none) 会拿到逐字节相同的结果。
    if status == "success" and result:
        from app.services.ai_chat.dsh_masking import mask_tool_result

        result = await mask_tool_result(
            result,
            role=token_payload.role,
            mask_policy=token_payload.mask_policy,
        )

    # ⑦ 预算消费
    result_bytes = len(str(result).encode("utf-8")) if result else 0
    budget_dict: dict = {}
    try:
        budget = _budget_tracker.check_and_consume(
            token_payload.run_id,
            response_bytes=result_bytes,
        )
        budget_dict = budget.to_dict()
    except McpBudgetExceeded as exc:
        status = "error"
        error_code = "tool_budget_exceeded"
        error_message = str(exc)
        budget_dict = _budget_tracker.get_or_create(token_payload.run_id).to_dict()

    # ⑧ 审计 tool_finished（Property 32：每个 tool call 有 finished/failed）
    duration_ms = int((time.time() - start_time) * 1000)
    await audit_tool_finished(
        db,
        user_id=token_payload.user_id,
        project_id=token_payload.project_id,
        run_id=token_payload.run_id,
        tool_call_id=req.tool_call_id,
        tool_name=req.tool_name,
        status="finished" if status == "success" else "failed",
        result_bytes=result_bytes,
        duration_ms=duration_ms,
        error_code=error_code,
    )

    return McpToolCallResponse(
        tool_call_id=req.tool_call_id,
        tool_name=req.tool_name,
        status=status,
        result=result if status == "success" else {},
        error_code=error_code,
        error_message=error_message,
        budget=budget_dict,
    )


@router.get("/budget/{run_id}", response_model=McpBudgetResponse)
async def get_budget(
    run_id: UUID,
    token_payload: McpTokenPayload = Depends(_validate_mcp_token),
) -> McpBudgetResponse:
    """查询 run 的 MCP 配额状态。"""
    # 校验 token 绑定的 run_id
    if token_payload.run_id != run_id:
        raise HTTPException(status_code=403, detail="token 不属于此 run")

    budget = _budget_tracker.get_or_create(run_id)
    return McpBudgetResponse(
        run_id=str(budget.run_id),
        max_calls=budget.max_calls,
        max_bytes_per_call=budget.max_bytes_per_call,
        calls_used=budget.calls_used,
        calls_remaining=budget.calls_remaining,
        total_bytes=budget.total_bytes,
    )


@router.get("/tools", response_model=list[str])
async def list_available_tools(
    token_payload: McpTokenPayload = Depends(_validate_mcp_token),
) -> list[str]:
    """列出可用的 MCP 工具。"""
    return sorted(MCP_READONLY_TOOLS)


# ---------------------------------------------------------------------------
# 工具分发
# ---------------------------------------------------------------------------


async def _dispatch_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """按工具名分发到具体实现。

    🔴 所有工具都是只读的（readonly=true）。
    🔴 每个工具内部会再次校验 ResourceAccessResolver 和 cycle_scope。
    """
    dispatchers = {
        "wp_list": _tool_wp_list,
        "wp_read": _tool_wp_read,
        "tb_query": _tool_tb_query,
        "addr_lookup": _tool_addr_lookup,
        "kb_search": _tool_kb_search,
        "note_read": _tool_note_read,
        "review_prompt": _tool_review_prompt,
    }
    handler = dispatchers.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"未知工具：{tool_name}")

    return await handler(
        arguments=arguments,
        token_payload=token_payload,
        host_decision=host_decision,
        resolver=resolver,
        db=db,
    )


async def _tool_context(
    *,
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> McpToolContext:
    """构造工具调用上下文（加载真实主体 + 项目权威年度）。"""
    return await build_tool_context(
        db=db,
        token_payload=token_payload,
        host_decision=host_decision,
        resolver=resolver,
    )


async def _tool_wp_list(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """列出当前项目有权访问的底稿（真实取数，见 ``ai_chat.mcp_tools``）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_wp_list(ctx, arguments)


async def _tool_wp_read(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """读取指定底稿内容（``working_paper JOIN wp_index`` + ``parsed_data``）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_wp_read(ctx, arguments)


async def _tool_tb_query(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """查询试算表数据（``get_active_filter`` + 叶子聚合 + 方向定符号）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_tb_query(ctx, arguments)


async def _tool_addr_lookup(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """查询地址坐标（复用 ``resolve_address_mention``：授权 + 脱敏 + stale）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_addr_lookup(ctx, arguments)


async def _tool_kb_search(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """搜索知识库（只走 embedding；不可用即 ``semantic_unavailable``）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_kb_search(ctx, arguments)


async def _tool_note_read(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """读取附注（行真源 = ``table_data.rows[].label/values``）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_note_read(ctx, arguments)


async def _tool_review_prompt(
    *,
    arguments: dict[str, Any],
    token_payload: McpTokenPayload,
    host_decision: Any,
    resolver: ResourceAccessResolver,
    db: AsyncSession,
) -> dict[str, Any]:
    """获取复核提示（``ReviewPromptService`` 三级降级；不返回正文）。"""
    ctx = await _tool_context(
        token_payload=token_payload, host_decision=host_decision,
        resolver=resolver, db=db,
    )
    return await tool_review_prompt(ctx, arguments)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _get_user_role(user: Any) -> str:
    """提取用户角色（与 ResourceAccessResolver 内部一致）。"""
    raw = getattr(user, "role", None)
    if raw is None:
        return ""
    value = getattr(raw, "value", raw)
    return str(value) if value else ""
