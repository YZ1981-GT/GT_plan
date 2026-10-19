"""LLM 单一运行时解析与 OpenAI-compatible transport。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_model_secret_service import decrypt_api_key
from app.services.llm_endpoint_policy import (
    describe_network_failure,
    resolve_endpoint,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import ProviderProfile, provider_profile


class LLMRuntimeError(RuntimeError):
    """可安全返回稳定 code 的运行时错误；message 不含上游正文或密钥。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedLLMConfig:
    model_name: str
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str
    api_key: str | None
    profile: ProviderProfile
    source: str
    model_id: UUID | None = None
    reasoning_effort: str | None = None

    def safe_dict(self) -> dict[str, object]:
        return {
            "model_id": str(self.model_id) if self.model_id else None,
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "provider": self.provider.value,
            "endpoint_url": self.endpoint_url,
            "source": self.source,
            "has_api_key": bool(self.api_key),
            "reasoning_effort": self.reasoning_effort,
        }


def resolve_config_from_model(
    model: AIModelConfig, *, requested_model: str | None = None
) -> ResolvedLLMConfig:
    """把一条 ORM 配置解析为短生命周期运行时配置。"""
    profile = provider_profile(model.provider)
    if model.model_type not in profile.supported_types:
        raise LLMRuntimeError("unsupported_model_type", "提供商不支持该模型类型")
    try:
        endpoint = validate_endpoint_structure(model.endpoint_url or "", profile)
        api_key = decrypt_api_key(model.api_key_ciphertext)
    except ValueError as exc:
        raise LLMRuntimeError("invalid_model_config", str(exc)) from exc
    if profile.requires_api_key and not api_key:
        raise LLMRuntimeError("api_key_required", "该提供商尚未配置 API Key")
    return ResolvedLLMConfig(
        model_name=(requested_model or model.model_name).strip(),
        model_type=model.model_type,
        provider=model.provider,
        endpoint_url=endpoint,
        api_key=api_key,
        profile=profile,
        source="database",
        model_id=model.id,
        reasoning_effort=model.reasoning_effort,
    )


async def resolve_runtime_config(
    db: AsyncSession,
    model_type: AIModelType,
    *,
    requested_model: str | None = None,
) -> ResolvedLLMConfig:
    """解析 active row；仅无 active row 时回落 `.env`。"""
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_type == model_type,
            AIModelConfig.is_active.is_(True),
            AIModelConfig.is_deleted.is_(False),
        )
    )
    rows = list(result.scalars().all())
    if len(rows) > 1:
        raise LLMRuntimeError("multiple_active_models", "同一模型类型存在多个激活配置")
    if rows:
        return resolve_config_from_model(rows[0], requested_model=requested_model)

    profile = provider_profile(AIProvider.openai_compatible)
    endpoint = (
        settings.LLM_EMBEDDING_BASE_URL
        if model_type == AIModelType.embedding
        else settings.LLM_BASE_URL
    )
    default_model = (
        settings.DEFAULT_EMBEDDING_MODEL
        if model_type == AIModelType.embedding
        else settings.DEFAULT_CHAT_MODEL
    )
    try:
        endpoint = validate_endpoint_structure(endpoint, profile)
    except ValueError as exc:
        raise LLMRuntimeError("invalid_fallback_config", str(exc)) from exc
    api_key = settings.LLM_API_KEY
    if not api_key or api_key == "not-needed":
        api_key = None
    return ResolvedLLMConfig(
        model_name=(requested_model or default_model).strip(),
        model_type=model_type,
        provider=AIProvider.openai_compatible,
        endpoint_url=endpoint,
        api_key=api_key,
        profile=profile,
        source="environment",
    )


async def build_runtime_client(
    config: ResolvedLLMConfig,
    *,
    timeout: float,
    connect_timeout: float = 10.0,
) -> httpx.AsyncClient:
    """出站前复核 endpoint，构造不跟随重定向且不继承代理的客户端。

    本机代理把 allowlist 端点解析成 fake-IP 时，transport 会把 TCP 改投到已复核的真实地址。
    """
    endpoint = await resolve_endpoint(config.endpoint_url, config.profile)
    headers: dict[str, str] = {}
    if config.api_key and config.profile.api_key_header == "Authorization":
        headers["Authorization"] = f"Bearer {config.api_key}"
    elif config.api_key and config.profile.api_key_header:
        headers[config.profile.api_key_header] = config.api_key
    return httpx.AsyncClient(
        base_url=endpoint.url.rstrip("/") + "/",
        headers=headers,
        timeout=httpx.Timeout(timeout, connect=connect_timeout),
        follow_redirects=False,
        mounts={},
        trust_env=False,
        transport=endpoint.transport(),
    )


def merge_system_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """合并所有 system 消息为首条，保持其他消息原序。"""
    systems = [m.get("content", "") for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]
    return ([{"role": "system", "content": "\n\n".join(filter(None, systems))}] if any(systems) else []) + others


def build_chat_payload(
    config: ResolvedLLMConfig,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    stream: bool,
    enable_thinking: bool | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": config.model_name,
        "messages": merge_system_messages(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if config.reasoning_effort:
        payload["reasoning_effort"] = config.reasoning_effort
    host = (urlsplit(config.endpoint_url).hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if local and "qwen" in config.model_name.lower() and config.provider == AIProvider.openai_compatible:
        thinking = settings.LLM_ENABLE_THINKING if enable_thinking is None else enable_thinking
        payload["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
    return payload


def _raise_for_status(
    response: httpx.Response, config: ResolvedLLMConfig | None = None
) -> None:
    if response.status_code < 400:
        return
    if response.status_code in {401, 403}:
        raise LLMRuntimeError("provider_auth_failed", "模型提供商认证失败，请检查 API Key")
    if response.status_code == 404:
        raise LLMRuntimeError("model_not_found", "模型或 API 路径不存在，请检查端点与模型名")
    if response.status_code == 429:
        raise LLMRuntimeError("provider_rate_limited", "模型提供商限流，请稍后重试")
    message = f"模型提供商返回 HTTP {response.status_code}"
    if response.status_code in {400, 422} and config is not None and config.reasoning_effort:
        message += "（请求参数被拒绝；若该模型不支持思考强度，请改为「未指定」）"
    raise LLMRuntimeError("provider_error", message)


async def _network_error(
    code: str, prefix: str, config: ResolvedLLMConfig, exc: BaseException
) -> LLMRuntimeError:
    """传输层失败 → 稳定 code + 可展示的具体原因（TLS / 拒连 / DNS / fake-IP）。"""
    detail = await describe_network_failure(config.endpoint_url, exc)
    return LLMRuntimeError(code, f"{prefix}：{detail}")


async def chat_sync(
    config: ResolvedLLMConfig,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    enable_thinking: bool | None = None,
    timeout: float = 30.0,
) -> str:
    payload = build_chat_payload(
        config, messages, temperature=temperature, max_tokens=max_tokens,
        stream=False, enable_thinking=enable_thinking,
    )
    try:
        async with await build_runtime_client(config, timeout=timeout) as client:
            response = await client.post("chat/completions", json=payload)
            _raise_for_status(response, config)
            choice = response.json().get("choices", [{}])[0]
            message = choice.get("message", {})
            # reasoning_content 是模型内部思考，不得当成最终答复返回。
            content = message.get("content")
            if content is None and choice.get("finish_reason") == "length":
                raise LLMRuntimeError("output_limit", "模型输出超过 token 限制")
            if not isinstance(content, str) or not content:
                raise LLMRuntimeError("empty_response", "模型未返回有效内容")
            return content
    except LLMRuntimeError:
        raise
    except httpx.TimeoutException as exc:
        error = await _network_error("provider_timeout", "模型调用超时", config, exc)
        raise error from exc
    except httpx.HTTPError as exc:
        error = await _network_error("provider_unreachable", "模型端点不可达", config, exc)
        raise error from exc


async def chat_stream(
    config: ResolvedLLMConfig,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    enable_thinking: bool | None = None,
    timeout: float = 90.0,
):
    payload = build_chat_payload(
        config, messages, temperature=temperature, max_tokens=max_tokens,
        stream=True, enable_thinking=enable_thinking,
    )
    try:
        async with await build_runtime_client(config, timeout=timeout) as client:
            async with client.stream("POST", "chat/completions", json=payload) as response:
                _raise_for_status(response, config)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        delta = json.loads(raw).get("choices", [{}])[0].get("delta", {})
                    except (json.JSONDecodeError, IndexError, TypeError):
                        continue
                    content = delta.get("content", "")
                    if content:
                        yield content
    except LLMRuntimeError:
        raise
    except httpx.TimeoutException as exc:
        error = await _network_error("provider_timeout", "模型调用超时", config, exc)
        raise error from exc
    except httpx.HTTPError as exc:
        error = await _network_error("provider_unreachable", "模型端点不可达", config, exc)
        raise error from exc


async def embedding(config: ResolvedLLMConfig, text: str, *, timeout: float = 30.0) -> list[float]:
    try:
        async with await build_runtime_client(config, timeout=timeout, connect_timeout=5.0) as client:
            response = await client.post("embeddings", json={"model": config.model_name, "input": text})
            _raise_for_status(response, config)
            rows = response.json().get("data", [])
            vector = rows[0].get("embedding", []) if rows else []
            if not isinstance(vector, list):
                raise LLMRuntimeError("empty_response", "Embedding 未返回有效向量")
            return vector
    except LLMRuntimeError:
        raise
    except httpx.TimeoutException as exc:
        error = await _network_error("provider_timeout", "Embedding 调用超时", config, exc)
        raise error from exc
    except httpx.HTTPError as exc:
        error = await _network_error("provider_unreachable", "Embedding 端点不可达", config, exc)
        raise error from exc


# 连接测试的输出预算：只为证明协议可用，不追求完整答复。
_PROBE_MAX_TOKENS = 16


async def _probe_chat_completion(config: ResolvedLLMConfig) -> None:
    """连接测试：与生产同一 transport / 鉴权 / payload（含思考强度），只验证协议可用。

    推理模型在小 max_tokens 下会把预算全部用于思考，返回 content=null +
    finish_reason=length（本机 vLLM Qwen3.5 实测 max_tokens=1 与 16 均如此）。这已证明
    端点、凭证、模型名与参数都被接受；按生产 `chat_sync` 的「必须有正文」判据测试，
    推理模型会永远激活失败。
    """
    payload = build_chat_payload(
        config, [{"role": "user", "content": "hi"}],
        temperature=0.0, max_tokens=_PROBE_MAX_TOKENS, stream=False,
    )
    try:
        async with await build_runtime_client(config, timeout=15.0) as client:
            response = await client.post("chat/completions", json=payload)
            _raise_for_status(response, config)
            try:
                data = response.json()
            except ValueError as exc:
                raise LLMRuntimeError("invalid_response", "模型端点返回的不是 JSON") from exc
    except LLMRuntimeError:
        raise
    except httpx.TimeoutException as exc:
        error = await _network_error("provider_timeout", "模型调用超时", config, exc)
        raise error from exc
    except httpx.HTTPError as exc:
        error = await _network_error("provider_unreachable", "模型端点不可达", config, exc)
        raise error from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMRuntimeError("invalid_response", "模型响应缺少 choices，不是 OpenAI 兼容格式")


async def test_runtime_config(config: ResolvedLLMConfig) -> None:
    """用生产同路径验证配置，不改变 active 状态。"""
    if config.model_type == AIModelType.chat:
        await _probe_chat_completion(config)
    elif config.model_type == AIModelType.embedding:
        await embedding(config, "test", timeout=15.0)
    else:
        raise LLMRuntimeError("unsupported_model_type", "该模型类型不走 LLM HTTP 测试")


async def probe_runtime_config(config: ResolvedLLMConfig) -> bool:
    """低成本健康探针；不返回上游正文。"""
    try:
        async with await build_runtime_client(config, timeout=5.0, connect_timeout=3.0) as client:
            response = await client.get("models")
            return response.status_code == 200
    except Exception:
        return False
