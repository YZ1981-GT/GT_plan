"""GET /api/ai-chat/capabilities 端点逻辑（Task 30）

Feature: dsh-agent-panel-integration
Requirements:
  - 10.1：engine 选择只由服务端 config/flag 决定，客户端不可覆盖。
  - 10.3：每个 engine 发布 capability manifest。
  - 10.4：不支持的能力前端禁用入口并显示中文原因。
  - 10.5：DSH 失败 → engine_unavailable，绝不静默 NativeEngine。
  - 10.6：DSH 为实验 flag + 项目 allowlist 控制。
  - 12.1：model/embedding/OCR endpoint 启动验证为本地。
  - 12.2：cloud/bundled default/unknown → refuse + local_only_violation。
  - 12.4：embedding/OCR/model 各自 typed error，不伪装"无结果"。
Design: "Components and Interfaces → 3. API Surface" + "→ 12. Engine Contract"
Properties:
  - 24：引擎能力与 UI 一致
  - 25：DSH 失败不降级
  - 26：Effective Cordis 与工具目录受控

## 设计

``/capabilities`` 不绑定具体 run/host，而是返回**当前服务端配置**下的引擎能力。
前端据此禁用不支持的入口（tools、subagents）并显示中文原因。

当 project_id 传入时，resolve_engine 可精确判断该项目是否 allowlisted；
不传时按"无项目上下文"处理（DSH 降回 native）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.ai_chat.engine import (
    ENGINE_GATE_REASON_ZH,
    resolve_engine,
)
from app.services.ai_chat.run_contract import (
    ChatEngineName,
    EngineCapabilities,
    capabilities_for,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CapabilityResponse",
    "CapabilityGate",
    "CAPABILITY_DISABLE_REASON_ZH",
    "get_capabilities",
]


# ---------------------------------------------------------------------------
# 中文禁用原因（NFR-5：全中文，前端不复制常量）
# ---------------------------------------------------------------------------

#: 能力字段 → 禁用时中文原因。只对 False 的字段生效；True 的字段不出现在 disabled_reasons。
CAPABILITY_DISABLE_REASON_ZH: dict[str, str] = {
    "tools": "当前引擎不支持工具调用，切换到 DSH 多步 Agent 后可用。",
    "subagents": "当前引擎不支持子 Agent，切换到 DSH 多步 Agent 后可用。",
    "structured_output": "当前引擎不支持结构化输出。",
    "streaming": "当前引擎不支持流式输出。",
    "review_mode": "当前引擎不支持底稿复核模式。",
    "attachments": "当前引擎不支持会话附件。",
}


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class CapabilityGate(BaseModel):
    """单个能力的门控状态。"""

    model_config = ConfigDict(frozen=True)

    field: str = Field(..., description="能力字段名（如 tools, subagents）")
    supported: bool = Field(..., description="当前引擎是否支持")
    reason: str = Field(
        default="", description="不支持时的中文原因（supported=True 时为空）"
    )


class CapabilityResponse(BaseModel):
    """GET /api/ai-chat/capabilities 响应。

    前端从此单一端点获取引擎能力，不手写第二份常量（Req 10.4 / Property 24）。
    """

    model_config = ConfigDict(frozen=True)

    engine: str = Field(..., description="当前生效的 engine 名称")
    capabilities: EngineCapabilities = Field(..., description="完整能力 manifest")
    gate_reason: str | None = Field(
        None,
        description="DSH 被门拦下时的中文原因（None = 本就是配置选择的 engine）",
    )
    disabled_reasons: dict[str, str] = Field(
        default_factory=dict,
        description="不支持的能力字段 → 中文原因（前端据此禁用入口）",
    )
    health: dict[str, "ServiceHealth"] = Field(
        default_factory=dict,
        description="各服务健康状态（model/embedding/ocr/mcp）",
    )


class ServiceHealth(BaseModel):
    """单个服务的健康状态。"""

    model_config = ConfigDict(frozen=True)

    available: bool = Field(..., description="服务是否可用")
    endpoint: str = Field(default="", description="实际 endpoint（脱敏后）")
    error_code: str | None = Field(None, description="不可用时的 typed error code")
    message: str = Field(default="", description="中文说明")


# 前向引用解析
CapabilityResponse.model_rebuild()


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def get_capabilities(
    *, project_id: UUID | None = None
) -> CapabilityResponse:
    """返回当前服务端配置下的引擎能力响应。

    参数:
        project_id: 可选的项目 ID（精确判断 DSH allowlist）。

    返回:
        CapabilityResponse，前端据此禁用不支持的入口。

    🔴 不接受请求体中的 engine 字段（Req 10.1）。
    """
    engine, gate_reason = resolve_engine(project_id=project_id)
    caps = capabilities_for(engine)

    # 构造 disabled_reasons：只对 False 的字段填入原因
    disabled: dict[str, str] = {}
    caps_dict = caps.model_dump()
    for field_name, reason in CAPABILITY_DISABLE_REASON_ZH.items():
        if field_name in caps_dict and caps_dict[field_name] is False:
            disabled[field_name] = reason

    # gate_reason 的中文翻译
    gate_reason_zh: str | None = None
    if gate_reason:
        gate_reason_zh = ENGINE_GATE_REASON_ZH.get(gate_reason, gate_reason)

    # 收集健康状态
    health = _collect_service_health()

    return CapabilityResponse(
        engine=engine.value,
        capabilities=caps,
        gate_reason=gate_reason_zh,
        disabled_reasons=disabled,
        health=health,
    )


def _collect_service_health() -> dict[str, ServiceHealth]:
    """收集 model/embedding/OCR/MCP 的健康状态。

    各服务独立检查，错误码分离（Req 12.4）。
    """
    from app.core.config import settings

    health: dict[str, ServiceHealth] = {}

    # Model health
    health["model"] = _check_model_health(settings)

    # Embedding health
    health["embedding"] = _check_embedding_health(settings)

    # OCR health
    health["ocr"] = _check_ocr_health(settings)

    # MCP health (只在 DSH 启用时有意义)
    if getattr(settings, "AI_DSH_ENABLED", False):
        health["mcp"] = _check_mcp_health(settings)

    return health


def _check_model_health(settings: Any) -> ServiceHealth:
    """检查模型 endpoint 是否为本地（Req 12.1 / 12.2）。"""
    from app.services.ai_chat.dsh_discovery import validate_model_route

    endpoint = getattr(settings, "LLM_BASE_URL", "") or ""
    if not endpoint:
        return ServiceHealth(
            available=False,
            endpoint="(未配置)",
            error_code="engine_unavailable",
            message="模型 API 地址未配置。",
        )

    errors = validate_model_route(endpoint)
    if errors:
        logger.warning(
            "[ai-chat] 模型 endpoint local-only 校验失败: %s (endpoint=%s)",
            "; ".join(errors), _mask_endpoint(endpoint),
        )
        return ServiceHealth(
            available=False,
            endpoint=_mask_endpoint(endpoint),
            error_code="local_only_violation",
            message=f"模型路由不合规: {errors[0]}",
        )

    return ServiceHealth(
        available=True,
        endpoint=_mask_endpoint(endpoint),
        message="本地模型可用。",
    )


def _check_embedding_health(settings: Any) -> ServiceHealth:
    """检查 embedding endpoint 是否为本地（Req 12.1 / 12.4）。"""
    from app.services.ai_chat.dsh_discovery import validate_model_route

    endpoint = getattr(settings, "LLM_EMBEDDING_BASE_URL", "") or ""
    if not endpoint:
        return ServiceHealth(
            available=False,
            endpoint="(未配置)",
            error_code="semantic_unavailable",
            message="Embedding 服务地址未配置。",
        )

    errors = validate_model_route(endpoint)
    if errors:
        logger.warning(
            "[ai-chat] embedding endpoint local-only 校验失败: %s",
            "; ".join(errors),
        )
        return ServiceHealth(
            available=False,
            endpoint=_mask_endpoint(endpoint),
            error_code="local_only_violation",
            message=f"Embedding 路由不合规: {errors[0]}",
        )

    return ServiceHealth(
        available=True,
        endpoint=_mask_endpoint(endpoint),
        message="本地 Embedding 服务可用。",
    )


def _check_ocr_health(settings: Any) -> ServiceHealth:
    """检查 OCR 服务配置状态（Req 12.4）。"""
    # OCR 服务端口（Docker 容器 8200）
    ocr_enabled = (
        getattr(settings, "OCR_PADDLE_ENABLED", False)
        or getattr(settings, "OCR_TESSERACT_ENABLED", False)
    )
    if not ocr_enabled:
        return ServiceHealth(
            available=False,
            endpoint="(未启用)",
            error_code="ocr_unavailable",
            message="OCR 服务未启用（Paddle 和 Tesseract 均已关闭）。",
        )

    return ServiceHealth(
        available=True,
        endpoint="localhost:8200",
        message="OCR 服务已配置。",
    )


def _check_mcp_health(settings: Any) -> ServiceHealth:
    """检查 MCP server 可用性（Phase C only）。"""
    from app.services.ai_chat.dsh_discovery import discover_dsh_sdk

    try:
        discovery = discover_dsh_sdk()
        if not discovery.is_available:
            return ServiceHealth(
                available=False,
                endpoint="(DSH SDK 不可用)",
                error_code="engine_unavailable",
                message=f"DSH SDK: {discovery.status.value}",
            )
        return ServiceHealth(
            available=True,
            endpoint="stdio (per-run)",
            message="MCP stdio server 可用。",
        )
    except Exception as exc:
        return ServiceHealth(
            available=False,
            endpoint="(检查失败)",
            error_code="engine_unavailable",
            message=f"MCP 健康检查异常: {exc}",
        )


def _mask_endpoint(endpoint: str) -> str:
    """脱敏 endpoint URL（只显示 host:port，不暴露完整路径或凭据）。"""
    if not endpoint:
        return "(empty)"
    # 只保留 scheme + host + port
    try:
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        if parsed.hostname:
            port_str = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{parsed.hostname}{port_str}"
    except Exception:
        pass
    # fallback: 截断到第一个 /（scheme://host:port 后）
    parts = endpoint.split("/", 3)
    return "/".join(parts[:3]) if len(parts) >= 3 else endpoint
