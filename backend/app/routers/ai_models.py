"""AI 模型配置管理 API — admin-only、安全凭证与统一 runtime。"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_role
from app.models.ai_model_options import (
    AIAuthScheme,
    OCRCapability,
    OCRProtocol,
    ReasoningEffort,
)
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.models.core import User
from app.services.ai_model_secret_service import (
    CredentialEncryptionUnavailable,
    apply_api_key_update,
    has_api_key,
)
from app.services.ai_model_presets import (
    PRESET_BY_KEY,
    PRESET_USER_EDITABLE_FIELDS,
    AIModelPreset,
)
from app.services.ai_service import AIService, ModelNotFoundError, ModelValidationFailure
from app.services.model_route_status import collect_route_status
from app.services.llm_endpoint_policy import (
    LLMEndpointPolicyError,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import provider_profile, public_provider_list
from app.services.llm_runtime import (
    LLMRuntimeError,
    classify_model_deployment,
    resolve_config_from_model,
    test_runtime_config,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-models", tags=["ai-models"])
_admin = require_role(["admin"])


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


@router.get("/providers")
async def list_providers(current_user: User = Depends(_admin)):
    """provider registry 的前端投影。"""
    return {
        "providers": public_provider_list(),
        "credential_encryption_ready": bool(settings.ENCRYPTION_KEY),
    }


@router.get("/health")
async def ai_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    return await AIService(db).health_check()


@router.post("/seed")
async def seed_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    await AIService.init_default_models(db)
    await db.commit()
    logger.info("AI 默认模型已初始化 by=%s", current_user.username)
    return {"message": "默认模型已初始化"}


@router.get("")
async def list_models(
    model_type: AIModelType | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    models = await AIService(db).get_all_models()
    if model_type:
        models = [model for model in models if model.model_type == model_type]
    return [_to_dict(model) for model in models]


@router.post("")
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_name == body.model_name.strip(),
            AIModelConfig.model_type == body.model_type,
            AIModelConfig.is_deleted.is_(False),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, "同名同类型模型已存在")

    ocr_values = _ocr_values_for_create(body)
    model = AIModelConfig(
        model_name=body.model_name.strip(),
        model_type=body.model_type,
        provider=body.provider,
        endpoint_url=_validated_endpoint(
            body.provider,
            body.model_type,
            body.endpoint_url,
            ocr_protocol=ocr_values["ocr_protocol"],
        ),
        reasoning_effort=body.reasoning_effort.value if body.reasoning_effort else None,
        is_active=False,
        context_window=body.context_window,
        performance_notes=body.performance_notes,
        **ocr_values,
    )
    model.deployment = classify_model_deployment(model)
    _apply_secret_or_raise(model, api_key=body.api_key, clear_api_key=False)
    db.add(model)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "模型配置与现有记录冲突") from exc
    await db.refresh(model)
    logger.info("AI 模型已创建 id=%s provider=%s by=%s", model.id, model.provider.value, current_user.username)
    return _to_dict(model)


@router.put("/{model_id}")
async def update_model(
    model_id: UUID,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    model = await _get_model(db, model_id)
    changed = body.model_dump(exclude_unset=True)
    if model.preset_key:
        allowed = set(PRESET_USER_EDITABLE_FIELDS)
        if model.model_type != AIModelType.chat:
            allowed.discard("reasoning_effort")
        forbidden = set(changed) - allowed
        if forbidden:
            raise HTTPException(
                422,
                "企业预设参数已锁定，只允许录入或清除 API Key"
                + ("、调整思考强度" if model.model_type == AIModelType.chat else ""),
            )
        options = _reasoning_effort_options(model)
        if options and body.reasoning_effort is not None and body.reasoning_effort.value not in options:
            raise HTTPException(
                422, f"该企业模型支持的思考强度为：{'、'.join(options)}，或「未指定」"
            )
    original_provider = model.provider
    original_endpoint = model.endpoint_url
    if body.model_name is not None:
        model.model_name = body.model_name.strip()
    if body.provider is not None:
        model.provider = body.provider
    if "reasoning_effort" in changed:
        model.reasoning_effort = (
            body.reasoning_effort.value if body.reasoning_effort else None
        )
    _apply_ocr_update(model, body, changed)
    if "endpoint_url" in changed or body.provider is not None:
        model.endpoint_url = _validated_endpoint(
            model.provider,
            model.model_type,
            body.endpoint_url,
            ocr_protocol=model.ocr_protocol,
        )
    else:
        # 旧记录也必须在保存时通过当前 provider 策略。
        model.endpoint_url = _validated_endpoint(
            model.provider,
            model.model_type,
            model.endpoint_url,
            ocr_protocol=model.ocr_protocol,
        )
    if "context_window" in changed:
        model.context_window = body.context_window
    if "performance_notes" in changed:
        model.performance_notes = body.performance_notes

    destination_changed = (
        model.provider != original_provider
        or model.endpoint_url != original_endpoint
        or bool(
            {"ocr_capability", "ocr_protocol", "api_path", "auth_scheme", "auth_header_name"}
            & set(changed)
        )
    )
    new_key = body.api_key if "api_key" in changed else None
    if (
        destination_changed
        and has_api_key(model)
        and not str(new_key or "").strip()
        and not body.clear_api_key
    ):
        await db.rollback()
        raise HTTPException(
            422,
            "修改提供商或端点时必须重新输入 API Key，或显式清除旧凭证",
        )
    secret_changed = _apply_secret_or_raise(
        model,
        api_key=new_key,
        clear_api_key=body.clear_api_key,
    )

    connection_changed = bool(
        {
            "model_name", "provider", "endpoint_url", "api_key", "clear_api_key",
            "reasoning_effort", "ocr_capability", "ocr_protocol", "api_path",
            "auth_scheme", "auth_header_name",
        }
        & set(changed)
    )
    new_deployment = classify_model_deployment(model)
    if model.is_active and new_deployment != model.deployment:
        with db.no_autoflush:  # 冲突检查不得提前把未校验完的改动刷进库
            taken = await AIService.route_slot_taken(
                db, model_type=model.model_type, deployment=new_deployment,
                ocr_capability=model.ocr_capability, exclude_id=model.id,
            )
        if taken:
            await db.rollback()
            raise HTTPException(
                409,
                f"该类型已启用另一条{_DEPLOYMENT_LABEL[new_deployment]}模型，请先停用后再修改端点",
            )
    model.deployment = new_deployment

    warning: str | None = None
    if model.is_active and connection_changed:
        service = AIService(db)
        if not await service._validate_model(model):
            failure = service.last_validation_error
            if not _local_unavailable(model, failure):
                await db.rollback()
                raise HTTPException(
                    400,
                    _validation_failure_detail(failure, "当前已启用模型的新配置验证失败，未保存"),
                )
            warning = await _local_unavailable_warning(db, model, failure)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "模型配置与现有记录冲突") from exc
    await db.refresh(model)
    logger.info(
        "AI 模型已更新 id=%s key_changed=%s by=%s",
        model.id,
        secret_changed,
        current_user.username,
    )
    return {**_to_dict(model), "warning": warning}


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    model = await _get_model(db, model_id)
    if model.preset_key:
        raise HTTPException(409, "企业预设模型不能删除，可编辑后录入 API Key")
    if model.is_active:
        raise HTTPException(409, "已启用的模型不能删除，请先停用")
    model.is_deleted = True
    model.api_key_ciphertext = None
    await db.commit()
    logger.info("AI 模型已软删除 id=%s by=%s", model.id, current_user.username)
    return {"message": "已移入回收状态"}


@router.post("/{model_id}/test")
async def test_model_connection(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    model = await _get_model(db, model_id)
    if model.model_type == AIModelType.ocr:
        service = AIService(db)
        ok = await service._validate_model(model)
        remote = model.ocr_protocol == OCRProtocol.paddlex_json.value
        label = "远程 OCR" if remote else "本机 OCR"
        if ok:
            return {"status": "ok", "error_code": None, "message": f"{label} 引擎可用"}
        failure = service.last_validation_error
        logger.warning(
            "AI 模型连接测试失败 id=%s code=%s by=%s",
            model.id,
            failure.code if failure else "engine_unavailable",
            current_user.username,
        )
        return {
            "status": "error",
            "error_code": failure.code if failure else "engine_unavailable",
            "message": failure.message if failure else f"{label} 引擎不可用",
        }
    try:
        await test_runtime_config(resolve_config_from_model(model))
        return {"status": "ok", "error_code": None, "message": "连接及模型响应正常"}
    except LLMRuntimeError as exc:
        logger.warning(
            "AI 模型连接测试失败 id=%s code=%s by=%s",
            model.id,
            exc.code,
            current_user.username,
        )
        return {"status": "error", "error_code": exc.code, "message": str(exc)}
    except ValueError as exc:
        return {"status": "error", "error_code": "invalid_model_config", "message": str(exc)}


@router.post("/{model_id}/activate")
async def activate_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    """启用模型参与路由：只替换同类型（OCR 同能力槽）同部署位置的那一条（ADR-ROUTE-002）。"""
    model = await _get_model(db, model_id)
    service = AIService(db)
    try:
        ok = await service.switch_model(model.model_name, model.model_type)
    except ModelNotFoundError as exc:
        raise HTTPException(404, "模型不存在") from exc
    if not ok:
        failure = service.last_validation_error
        await db.rollback()
        raise HTTPException(400, _validation_failure_detail(failure, "模型验证失败，未启用"))
    warning = await _local_unavailable_warning(db, model, service.last_validation_warning)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "并发切换冲突，请刷新后重试") from exc
    logger.info("AI 模型已启用 id=%s deployment=%s by=%s", model.id, model.deployment, current_user.username)
    return {
        "message": "已启用",
        "model_name": model.model_name,
        "provider": model.provider.value,
        "deployment": model.deployment,
        "warning": warning,
    }


@router.post("/{model_id}/deactivate")
async def deactivate_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    """停用：退出路由；该类型没有任何启用模型时回落 `.env` / 本机进程内 OCR。"""
    model = await _get_model(db, model_id)
    if model.is_active:
        await AIService(db).disable_model(model)
        await db.commit()
        logger.info("AI 模型已停用 id=%s by=%s", model.id, current_user.username)
    return {"message": "已停用", "model_name": model.model_name}


@router.get("/routes")
async def model_routes(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin),
):
    """各类「本机 → 服务器」路由的候选、状态与当前生效（ADR-ROUTE-010）。"""
    return await collect_route_status(db, refresh=refresh)


_DEPLOYMENT_LABEL = {"local": "本机", "server": "服务器"}


def _local_unavailable(model: AIModelConfig, failure: ModelValidationFailure | None) -> bool:
    """本机模型仅因「当前不可用」验证失败：允许保存 / 启用并给出提示（R4.2）。"""
    return (
        failure is not None
        and failure.kind == "unavailable"
        and model.deployment == "local"
    )


async def _local_unavailable_warning(
    db: AsyncSession, model: AIModelConfig, failure: ModelValidationFailure | None
) -> str | None:
    """本机或企业预设不可用仍启用时的提示：按有没有可兜底的模型如实说明后果。"""
    if failure is None:
        return None
    deployment = deployment_of(model)
    is_local = deployment == AIDeployment.local.value
    is_preset = model.preset_key is not None

    if is_local:
        head = f"本机模型当前不可用（{failure.message}），已启用"
    elif is_preset:
        head = f"企业预设当前不可达（{failure.message}），已启用；连上公司网络后自动生效"
    else:
        head = f"模型当前不可用（{failure.message}），已启用"

    if model.model_type == AIModelType.embedding:
        return f"{head}；向量模型不跨模型兜底，恢复前向量检索不可用"
    with db.no_autoflush:
        has_fallback = await AIService.route_slot_taken(
            db, model_type=model.model_type,
            deployment="local" if not is_local else "server",
            ocr_capability=model.ocr_capability, exclude_id=model.id,
        )
    if has_fallback:
        return f"{head}；调用时会自动使用另一候选兜底"
    if is_preset:
        return f"{head}；该类型尚无其他候选，连上公司网络前 AI 调用会失败"
    return f"{head}；该类型尚未启用服务器模型，本机恢复前调用会失败"


def _chat_preset(model: AIModelConfig) -> AIModelPreset | None:
    if not model.preset_key or model.model_type != AIModelType.chat:
        return None
    return PRESET_BY_KEY.get(model.preset_key)


def _reasoning_effort_options(model: AIModelConfig) -> tuple[str, ...] | None:
    """企业预设登记了服务端实际支持的思考强度时返回该集合；其他模型不限制。"""
    preset = _chat_preset(model)
    return preset.reasoning_effort_options if preset else None


def _validation_failure_detail(
    failure: ModelValidationFailure | None, prefix: str
) -> dict[str, str]:
    """验证失败的稳定 code + 具体原因；前端 handleApiError 读取 detail.message。"""
    if failure is None:
        return {
            "error_code": "validation_failed",
            "message": f"{prefix}：请检查端点、模型名和凭证",
        }
    return {"error_code": failure.code, "message": f"{prefix}：{failure.message}"}


async def _get_model(db: AsyncSession, model_id: UUID) -> AIModelConfig:
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.id == model_id,
            AIModelConfig.is_deleted.is_(False),
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型不存在")
    return model


def _to_dict(model: AIModelConfig) -> dict[str, object]:
    preset = _chat_preset(model)
    effort_options = preset.reasoning_effort_options if preset else None
    return {
        "id": str(model.id),
        "preset_key": model.preset_key,
        "model_name": model.model_name,
        "model_type": model.model_type.value,
        "provider": model.provider.value,
        "endpoint_url": model.endpoint_url,
        "reasoning_effort": model.reasoning_effort,
        "reasoning_effort_options": list(effort_options) if effort_options else None,
        "reasoning_effort_server_default": (
            preset.reasoning_effort_server_default if preset else None
        ),
        "ocr_capability": model.ocr_capability,
        "ocr_protocol": model.ocr_protocol,
        "api_path": model.api_path,
        "auth_scheme": model.auth_scheme,
        "auth_header_name": model.auth_header_name,
        "request_timeout_seconds": model.request_timeout_seconds,
        "has_api_key": has_api_key(model),
        "api_key_updated_at": (
            model.api_key_updated_at.isoformat() if model.api_key_updated_at else None
        ),
        "deployment": model.deployment,
        "is_active": model.is_active,
        "context_window": model.context_window,
        "performance_notes": model.performance_notes,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }
