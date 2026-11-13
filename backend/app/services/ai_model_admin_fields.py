"""AI 模型配置页的请求体与字段规范化（从 ``routers/ai_models.py`` 原样移出，行为不变）。

只做「表单 → 合法字段值」：provider / 端点校验、信任域与客户数据政策、OCR 专用字段、凭证更新。
路由按原名导入（测试与审计守卫按路由模块引用这些名字）。spec enterprise-embedding-rerank-closure R11.5。
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_model_options import (
    AIAuthScheme,
    AIDeployment,
    AIMaskPolicy,
    AITrustZone,
    OCRCapability,
    OCRProtocol,
    ReasoningEffort,
    default_trust_zone,
)
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_model_secret_service import (
    CredentialEncryptionUnavailable,
    apply_api_key_update,
)
from app.services.llm_endpoint_policy import (
    LLMEndpointPolicyError,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import provider_profile


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=100)
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=2000, repr=False)
    reasoning_effort: ReasoningEffort | None = None
    ocr_capability: OCRCapability | None = None
    ocr_protocol: OCRProtocol | None = None
    api_path: str | None = Field(default=None, max_length=128)
    auth_scheme: AIAuthScheme | None = None
    auth_header_name: str | None = Field(default=None, max_length=128)
    request_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    context_window: int | None = Field(default=None, ge=1)
    performance_notes: str | None = Field(default=None, max_length=4000)
    trust_zone: AITrustZone | None = None
    client_data_allowed: bool | None = None
    mask_policy: AIMaskPolicy | None = None


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: AIProvider | None = None
    endpoint_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=2000, repr=False)
    clear_api_key: bool = False
    reasoning_effort: ReasoningEffort | None = None
    ocr_capability: OCRCapability | None = None
    ocr_protocol: OCRProtocol | None = None
    api_path: str | None = Field(default=None, max_length=128)
    auth_scheme: AIAuthScheme | None = None
    auth_header_name: str | None = Field(default=None, max_length=128)
    request_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    context_window: int | None = Field(default=None, ge=1)
    performance_notes: str | None = Field(default=None, max_length=4000)
    trust_zone: AITrustZone | None = None
    client_data_allowed: bool | None = None
    mask_policy: AIMaskPolicy | None = None


def _validated_endpoint(
    provider: AIProvider,
    model_type: AIModelType,
    endpoint_url: str | None,
    *,
    ocr_protocol: str | None = None,
) -> str | None:
    profile = provider_profile(provider)
    if model_type not in profile.supported_types:
        raise HTTPException(422, "所选提供商不支持该模型类型")
    if model_type == AIModelType.ocr and ocr_protocol == OCRProtocol.local.value:
        return None
    try:
        return validate_endpoint_structure(endpoint_url or profile.default_endpoint, profile)
    except LLMEndpointPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc


def _trust_values(
    *,
    deployment: str,
    preset_key: str | None,
    trust_zone: AITrustZone | None,
    client_data_allowed: bool | None,
    mask_policy: AIMaskPolicy | None,
) -> dict[str, object]:
    """规范化信任域。位置不能由表单伪造，信任域必须与客户数据政策一致。"""
    zone = trust_zone.value if trust_zone else default_trust_zone(
        deployment=deployment, preset_key=preset_key
    )
    if deployment == AIDeployment.local.value and zone != AITrustZone.local_device.value:
        raise HTTPException(422, "本机端点的信任域必须是‘本机设备’")
    if deployment != AIDeployment.local.value and zone == AITrustZone.local_device.value:
        raise HTTPException(422, "服务器端点不能标记为‘本机设备’")

    allowed = client_data_allowed
    if allowed is None:
        allowed = zone in {
            AITrustZone.local_device.value,
            AITrustZone.firm_private.value,
        }
    policy = mask_policy.value if mask_policy else (
        AIMaskPolicy.role_based.value
        if zone == AITrustZone.local_device.value
        else AIMaskPolicy.strict.value
    )
    if zone == AITrustZone.restricted.value and allowed:
        raise HTTPException(422, "受限端点禁止处理客户数据")
    if zone == AITrustZone.approved_provider.value and allowed and policy != AIMaskPolicy.strict.value:
        raise HTTPException(422, "经批准外部服务处理客户数据时必须使用严格脱敏")
    return {
        "trust_zone": zone,
        "client_data_allowed": bool(allowed),
        "mask_policy": policy,
    }


def _ocr_values_for_create(body: ModelCreate) -> dict[str, object | None]:
    if body.model_type != AIModelType.ocr:
        return {
            "ocr_capability": None, "ocr_protocol": None, "api_path": None,
            "auth_scheme": None, "auth_header_name": None,
            "request_timeout_seconds": body.request_timeout_seconds,
        }
    if body.provider != AIProvider.paddleocr:
        raise HTTPException(422, "OCR 模型当前仅支持 PaddleOCR provider")
    capability = body.ocr_capability or OCRCapability.ocr
    protocol = body.ocr_protocol or OCRProtocol.local
    auth = body.auth_scheme or (
        AIAuthScheme.bearer if protocol == OCRProtocol.paddlex_json else AIAuthScheme.none
    )
    expected_path = "/layout-parsing" if capability == OCRCapability.layout_parsing else "/ocr"
    api_path = body.api_path or expected_path
    if api_path != expected_path:
        raise HTTPException(422, f"{capability.value} 的接口路径必须是 {expected_path}")
    if auth == AIAuthScheme.custom_header and not body.auth_header_name:
        raise HTTPException(422, "自定义认证方式必须填写 Header 名称")
    if protocol == OCRProtocol.paddlex_json and auth != AIAuthScheme.none and not str(body.api_key or "").strip():
        raise HTTPException(422, "远程 OCR 认证方式要求配置 API Key")
    return {
        "ocr_capability": capability.value,
        "ocr_protocol": protocol.value,
        "api_path": api_path if protocol == OCRProtocol.paddlex_json else None,
        "auth_scheme": auth.value,
        "auth_header_name": body.auth_header_name,
        "request_timeout_seconds": body.request_timeout_seconds,
    }


def _apply_ocr_update(
    model: AIModelConfig,
    body: ModelUpdate,
    changed: dict[str, object],
) -> None:
    ocr_fields = {
        "ocr_capability", "ocr_protocol", "api_path", "auth_scheme",
        "auth_header_name", "request_timeout_seconds",
    }
    if model.model_type != AIModelType.ocr:
        if ocr_fields & set(changed):
            raise HTTPException(422, "非 OCR 模型不能配置 OCR 专用字段")
        return
    if model.provider != AIProvider.paddleocr:
        raise HTTPException(422, "OCR 模型当前仅支持 PaddleOCR provider")
    if body.ocr_capability is not None:
        model.ocr_capability = body.ocr_capability.value
    if body.ocr_protocol is not None:
        model.ocr_protocol = body.ocr_protocol.value
    if body.auth_scheme is not None:
        model.auth_scheme = body.auth_scheme.value
    if "auth_header_name" in changed:
        model.auth_header_name = body.auth_header_name
    if "request_timeout_seconds" in changed:
        model.request_timeout_seconds = body.request_timeout_seconds
    capability = model.ocr_capability or OCRCapability.ocr.value
    protocol = model.ocr_protocol or OCRProtocol.local.value
    expected_path = "/layout-parsing" if capability == OCRCapability.layout_parsing.value else "/ocr"
    if "api_path" in changed:
        model.api_path = body.api_path
    if protocol == OCRProtocol.local.value:
        model.api_path = None
        model.auth_scheme = AIAuthScheme.none.value
        model.auth_header_name = None
    else:
        model.api_path = model.api_path or expected_path
        if model.api_path != expected_path:
            raise HTTPException(422, f"{capability} 的接口路径必须是 {expected_path}")
        model.auth_scheme = model.auth_scheme or AIAuthScheme.bearer.value
        if model.auth_scheme == AIAuthScheme.custom_header.value and not model.auth_header_name:
            raise HTTPException(422, "自定义认证方式必须填写 Header 名称")


def _apply_secret_or_raise(
    model: AIModelConfig,
    *,
    api_key: str | None,
    clear_api_key: bool,
) -> bool:
    try:
        return apply_api_key_update(
            model, api_key=api_key, clear_api_key=clear_api_key
        )
    except CredentialEncryptionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
