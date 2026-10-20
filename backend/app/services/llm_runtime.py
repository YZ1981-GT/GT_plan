"""LLM 运行时：配置解析、路由候选与 OpenAI-compatible transport。

路由（本机优先、服务器兜底）的候选在这里解析与排序；故障转移、冷却与实际服务模型记录
在 ``llm_route``。单个候选的 HTTP 调用（chat / stream / embedding / probe）只有这一份实现。
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_model_options import AIDeployment, classify_deployment
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_model_secret_service import decrypt_api_key
from app.services.llm_endpoint_policy import (
    LLMEndpointPolicyError,
    describe_network_failure,
    resolve_endpoint,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import ProviderProfile, provider_profile

# 可改用下一个候选的错误类别（ADR-ROUTE-003）。
_FAILOVER_KINDS = frozenset({"unavailable", "config"})

# 最近一次非流式调用上报的 total_tokens（同一请求上下文内可读，供用量统计）。
_LAST_TOTAL_TOKENS: ContextVar[int | None] = ContextVar("llm_last_total_tokens", default=None)


def last_total_tokens() -> int:
    return _LAST_TOTAL_TOKENS.get() or 0


class LLMRuntimeError(RuntimeError):
    """可安全返回稳定 code 的运行时错误；message 不含上游正文或密钥。

    ``kind`` 决定路由能否改用下一个候选：
    ``unavailable``（连不上 / 5xx / 端点被拦）与 ``config``（鉴权 / 模型不存在 / 非兼容响应）
    可转移；``request`` / ``timeout`` / ``output`` 不转移 —— 请求已被接收或会在另一端同样失败，
    重发会让同一请求在两端重复执行。
    """

    def __init__(self, code: str, message: str, *, kind: str = "request"):
        self.code = code
        self.kind = kind
        super().__init__(message)

    @property
    def failover(self) -> bool:
        return self.kind in _FAILOVER_KINDS


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
    deployment: str = AIDeployment.server.value

    @property
    def identity(self) -> str:
        """候选身份：熔断、冷却与状态缓存按它区分（不含密钥）。

        含模型类型：同一端点同一模型名可能同时登记为对话与向量（本机 8100 现状如此），
        向量 /embeddings 失败不得让对话路由跳过本机，也不得共用探测结果。
        """
        return f"{self.model_type.value}|{self.provider.value}|{self.endpoint_url}|{self.model_name}"

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
            "deployment": self.deployment,
        }


def classify_model_deployment(model: AIModelConfig) -> str:
    """按行当前的端点 / OCR 协议推导部署位置（创建、改端点、种子时写库用）。"""
    endpoint = model.endpoint_url
    if not endpoint:
        try:
            endpoint = provider_profile(model.provider).default_endpoint
        except ValueError:
            endpoint = ""
    return classify_deployment(
        endpoint_url=endpoint, ocr_protocol=getattr(model, "ocr_protocol", None)
    )


def deployment_of(model: AIModelConfig) -> str:
    """行的部署位置：以库内 V197 列为准；缺失或非法时按端点推导。"""
    stored = getattr(model, "deployment", None)
    if stored in (AIDeployment.local.value, AIDeployment.server.value):
        return stored
    return classify_model_deployment(model)


def resolve_config_from_model(
    model: AIModelConfig, *, requested_model: str | None = None
) -> ResolvedLLMConfig:
    """把一条 ORM 配置解析为短生命周期运行时配置。"""
    profile = provider_profile(model.provider)
    if model.model_type not in profile.supported_types:
        raise LLMRuntimeError("unsupported_model_type", "提供商不支持该模型类型", kind="config")
    try:
        endpoint = validate_endpoint_structure(model.endpoint_url or "", profile)
        api_key = decrypt_api_key(model.api_key_ciphertext)
    except ValueError as exc:
        raise LLMRuntimeError("invalid_model_config", str(exc), kind="config") from exc
    if profile.requires_api_key and not api_key:
        raise LLMRuntimeError("api_key_required", "该提供商尚未配置 API Key", kind="config")
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
        deployment=deployment_of(model),
    )


def _environment_config(
    model_type: AIModelType, requested_model: str | None
) -> ResolvedLLMConfig:
    """无启用行时的 `.env` 兜底（单候选，模型名仍可由调用方指定）。"""
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
        raise LLMRuntimeError("invalid_fallback_config", str(exc), kind="config") from exc
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
        deployment=classify_deployment(endpoint_url=endpoint),
    )


@dataclass(frozen=True)
class RouteCandidate:
    """路由候选。配置无法解析（如缺 Key）时 ``config`` 为空、``error`` 记录原因，执行时按失败处理。"""

    model_name: str
    deployment: str
    model_id: UUID | None = None
    config: ResolvedLLMConfig | None = None
    error: LLMRuntimeError | None = None
    implicit: bool = False  # 无启用行时的 `.env` 兜底

    @property
    def identity(self) -> str:
        if self.config is not None:
            return self.config.identity
        return f"invalid|{self.model_id}|{self.model_name}"

    @property
    def label(self) -> str:
        where = "本机" if self.deployment == AIDeployment.local.value else "服务器"
        return f"{where}模型「{self.model_name}」"


def order_candidates(
    candidates: list[RouteCandidate], requested_model: str | None = None
) -> list[RouteCandidate]:
    """本机在前、服务器在后（稳定排序）；调用方点名的模型只作优先提示（ADR-ROUTE-005）。"""
    ordered = sorted(
        candidates, key=lambda c: 0 if c.deployment == AIDeployment.local.value else 1
    )
    wanted = (requested_model or "").strip()
    if wanted:
        hit = [c for c in ordered if c.model_name == wanted]
        if hit:
            ordered = hit + [c for c in ordered if c.model_name != wanted]
    return ordered


async def enabled_model_rows(
    db: AsyncSession, model_type: AIModelType, *, ocr_capability: str | None = None
) -> list[AIModelConfig]:
    """已启用（参与路由）的行；OCR 可按能力槽过滤。"""
    conditions = [
        AIModelConfig.model_type == model_type,
        AIModelConfig.is_active.is_(True),
        AIModelConfig.is_deleted.is_(False),
    ]
    if model_type == AIModelType.ocr and ocr_capability:
        conditions.append(AIModelConfig.ocr_capability == ocr_capability)
    result = await db.execute(select(AIModelConfig).where(*conditions))
    return list(result.scalars().all())


def _assert_route_uniqueness(rows: list[AIModelConfig], model_type: AIModelType) -> None:
    """与 V197 唯一索引同一约束；索引缺失（如未迁移的库）时在应用层兜住。"""
    if model_type == AIModelType.embedding:
        if len(rows) > 1:
            raise LLMRuntimeError(
                "multiple_active_models", "向量模型只能启用一条（不跨模型兜底）", kind="config"
            )
        return
    seen: set[str] = set()
    for row in rows:
        key = deployment_of(row)
        if key in seen:
            raise LLMRuntimeError(
                "multiple_active_models", "同一类型的同一部署位置存在多个启用配置", kind="config"
            )
        seen.add(key)


async def resolve_route(
    db: AsyncSession,
    model_type: AIModelType,
    *,
    requested_model: str | None = None,
) -> list[RouteCandidate]:
    """按「本机 → 服务器」排序的已启用候选；没有启用行时回落 `.env` 单候选。"""
    rows = await enabled_model_rows(db, model_type)
    _assert_route_uniqueness(rows, model_type)
    if not rows:
        config = _environment_config(model_type, requested_model)
        return [RouteCandidate(config.model_name, config.deployment, None, config, implicit=True)]
    candidates: list[RouteCandidate] = []
    for row in rows:
        try:
            config = resolve_config_from_model(row)
        except LLMRuntimeError as exc:
            candidates.append(
                RouteCandidate(row.model_name, deployment_of(row), row.id, None, exc)
            )
        else:
            candidates.append(RouteCandidate(config.model_name, config.deployment, row.id, config))
    return order_candidates(candidates, requested_model)


async def resolve_runtime_config(
    db: AsyncSession,
    model_type: AIModelType,
    *,
    requested_model: str | None = None,
) -> ResolvedLLMConfig:
    """路由首个可解析的候选（不做连通性判断）；全部不可解析时抛首个原因。"""
    route = await resolve_route(db, model_type, requested_model=requested_model)
    for candidate in route:
        if candidate.config is not None:
            return candidate.config
    raise route[0].error or LLMRuntimeError("no_model", "没有可用的模型配置", kind="config")


async def build_runtime_client(
    config: ResolvedLLMConfig,
    *,
    timeout: float,
    connect_timeout: float = 10.0,
) -> httpx.AsyncClient:
    """出站前复核 endpoint，构造不跟随重定向且不继承代理的客户端。

    本机代理把 allowlist 端点解析成 fake-IP 时，transport 会把 TCP 改投到已复核的真实地址。
    本机候选连接超时收紧：本机服务没起时尽快转去服务器（Windows 上连关闭端口约 1.5 秒才报错）。
    """
    if config.deployment == AIDeployment.local.value:
        connect_timeout = min(connect_timeout, float(settings.LLM_LOCAL_CONNECT_TIMEOUT_SECONDS))
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
    payload.update(reasoning_fields(config, enable_thinking))
    return payload


def reasoning_fields(
    config: ResolvedLLMConfig, enable_thinking: bool | None = None
) -> dict[str, object]:
    """按候选生成思考参数（平台直调与 DSH 转发共用这一份规则）。

    - 配置了思考强度 ⇒ ``reasoning_effort``（企业网关只认 low / medium / xhigh）。
    - 本机 OpenAI-compatible 的 Qwen ⇒ ``chat_template_kwargs.enable_thinking``。
    """
    fields: dict[str, object] = {}
    if config.reasoning_effort:
        fields["reasoning_effort"] = config.reasoning_effort
    host = (urlsplit(config.endpoint_url).hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if local and "qwen" in config.model_name.lower() and config.provider == AIProvider.openai_compatible:
        thinking = settings.LLM_ENABLE_THINKING if enable_thinking is None else enable_thinking
        fields["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
    return fields


def _raise_for_status(
    response: httpx.Response, config: ResolvedLLMConfig | None = None
) -> None:
    if response.status_code < 400:
        return
    if response.status_code in {401, 403}:
        raise LLMRuntimeError(
            "provider_auth_failed", "模型提供商认证失败，请检查 API Key", kind="config"
        )
    if response.status_code == 404:
        raise LLMRuntimeError(
            "model_not_found", "模型或 API 路径不存在，请检查端点与模型名", kind="config"
        )
    if response.status_code == 429:
        raise LLMRuntimeError("provider_rate_limited", "模型提供商限流，请稍后重试")
    message = f"模型提供商返回 HTTP {response.status_code}"
    if response.status_code >= 500:
        raise LLMRuntimeError("provider_error", message, kind="unavailable")
    if response.status_code in {400, 422} and config is not None and config.reasoning_effort:
        message += "（请求参数被拒绝；若该模型不支持思考强度，请改为「未指定」）"
    raise LLMRuntimeError("provider_error", message)


async def _transport_error(
    config: ResolvedLLMConfig, exc: BaseException, *, subject: str = "模型"
) -> LLMRuntimeError:
    """传输层失败 → 稳定 code + 类别 + 可展示的具体原因（TLS / 拒连 / DNS / fake-IP）。

    连接阶段失败（连不上、连接超时、端点被策略拦截）可转移；连接建立后的超时 / 读写错误不转移。
    """
    if isinstance(exc, LLMEndpointPolicyError):
        return LLMRuntimeError("endpoint_blocked", f"{subject}端点不可用：{exc}", kind="unavailable")
    detail = await describe_network_failure(config.endpoint_url, exc)
    if isinstance(exc, httpx.ConnectTimeout):
        return LLMRuntimeError("provider_timeout", f"{subject}调用超时：{detail}", kind="unavailable")
    if isinstance(exc, httpx.TimeoutException):
        return LLMRuntimeError("provider_timeout", f"{subject}调用超时：{detail}", kind="timeout")
    if isinstance(exc, httpx.ConnectError):
        return LLMRuntimeError("provider_unreachable", f"{subject}端点不可达：{detail}", kind="unavailable")
    return LLMRuntimeError("provider_unreachable", f"{subject}端点不可达：{detail}")


def _json_body(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise LLMRuntimeError(
            "invalid_response", "模型端点返回的不是 JSON（可能不是 OpenAI 兼容服务）", kind="config"
        ) from exc


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
    _LAST_TOTAL_TOKENS.set(None)
    try:
        async with await build_runtime_client(config, timeout=timeout) as client:
            response = await client.post("chat/completions", json=payload)
            _raise_for_status(response, config)
            body = _json_body(response)
            usage = body.get("usage") if isinstance(body, dict) else None
            if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                _LAST_TOTAL_TOKENS.set(usage["total_tokens"])
            choices = body.get("choices") if isinstance(body, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices else {}
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            # reasoning_content 是模型内部思考，不得当成最终答复返回。
            content = message.get("content") if isinstance(message, dict) else None
            if content is None and isinstance(choice, dict) and choice.get("finish_reason") == "length":
                raise LLMRuntimeError("output_limit", "模型输出超过 token 限制", kind="output")
            if not isinstance(content, str) or not content:
                raise LLMRuntimeError("empty_response", "模型未返回有效内容", kind="output")
            return content
    except LLMRuntimeError:
        raise
    except (httpx.HTTPError, LLMEndpointPolicyError) as exc:
        raise await _transport_error(config, exc) from exc


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
                    except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
                        continue
                    content = delta.get("content", "") if isinstance(delta, dict) else ""
                    if content:
                        yield content
    except LLMRuntimeError:
        raise
    except (httpx.HTTPError, LLMEndpointPolicyError) as exc:
        raise await _transport_error(config, exc) from exc


async def embedding(config: ResolvedLLMConfig, text: str, *, timeout: float = 30.0) -> list[float]:
    try:
        async with await build_runtime_client(config, timeout=timeout, connect_timeout=5.0) as client:
            response = await client.post("embeddings", json={"model": config.model_name, "input": text})
            _raise_for_status(response, config)
            body = _json_body(response)
            rows = body.get("data", []) if isinstance(body, dict) else []
            vector = rows[0].get("embedding", []) if rows and isinstance(rows[0], dict) else []
            if not isinstance(vector, list) or not vector:
                raise LLMRuntimeError("empty_response", "Embedding 未返回有效向量", kind="output")
            return vector
    except LLMRuntimeError:
        raise
    except (httpx.HTTPError, LLMEndpointPolicyError) as exc:
        raise await _transport_error(config, exc, subject="Embedding ") from exc


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
            data = _json_body(response)
    except LLMRuntimeError:
        raise
    except (httpx.HTTPError, LLMEndpointPolicyError) as exc:
        raise await _transport_error(config, exc) from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMRuntimeError(
            "invalid_response", "模型响应缺少 choices，不是 OpenAI 兼容格式", kind="config"
        )


async def test_runtime_config(config: ResolvedLLMConfig) -> None:
    """用生产同路径验证配置，不改变启用状态。"""
    if config.model_type == AIModelType.chat:
        await _probe_chat_completion(config)
    elif config.model_type == AIModelType.embedding:
        await embedding(config, "test", timeout=15.0)
    else:
        raise LLMRuntimeError(
            "unsupported_model_type", "该模型类型不走 LLM HTTP 测试", kind="config"
        )


async def probe_runtime_config(config: ResolvedLLMConfig) -> bool:
    """低成本健康探针；不返回上游正文。"""
    try:
        async with await build_runtime_client(config, timeout=5.0, connect_timeout=3.0) as client:
            response = await client.get("models")
            return response.status_code == 200
    except Exception:
        return False
