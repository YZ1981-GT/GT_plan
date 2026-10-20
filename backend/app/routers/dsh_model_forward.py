"""DSH 子进程模型请求的环回转发（spec dsh-kb-ocr-local-first-routing ADR-DKR-001）。

DSH 子进程的模型服务 ``baseURL`` 指向这里，``Authorization: Bearer <run 令牌>``。本端点：

1. 只接受本机直连：来源必须是环回地址，且不带反向代理头（经 nginx 转发的公网请求同样显示为
   127.0.0.1，靠 ``X-Forwarded-For`` 等头区分）。令牌才是真正的鉴权：HMAC 签名、短时效、绑定 run。
2. 按令牌绑定的候选重新解析路由（配置被停用 / 修改 ⇒ 409，不悄悄换模型）。
3. 用平台出站客户端转发（端点策略、DNS 复核、fake-IP 兼容），思考参数按候选重写，SSE 原样回传。
4. 上游连接失败 / 5xx / 401 / 403 / 404 ⇒ 该候选记入冷却；400 / 422 / 429 是请求本身的问题，不冷却。

响应体按 OpenAI 兼容格式（``{"error": {"message", "type"}}``）给 vendor 适配器解析，不走平台信封
（2xx 是 SSE，ResponseWrapperMiddleware 本就跳过；错误码非 2xx 不包装）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.config import settings
from app.services.ai_chat.dsh_model_bridge import (
    FORWARD_PATH,
    DshTokenError,
    candidate_for,
    rewrite_request,
    verify_token,
)
from app.services.llm_endpoint_policy import LLMEndpointPolicyError, describe_network_failure
from app.services.llm_route import mark_available, mark_unavailable
from app.services.llm_runtime import ResolvedLLMConfig, build_runtime_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix=FORWARD_PATH, tags=["DSH 模型转发"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded")
#: 这些上游状态说明候选本身不可用（服务挂了 / Key 失效 / 路径不对），记冷却让下一次 run 换候选
_UNAVAILABLE_STATUS = frozenset({401, 403, 404})


def _error(status: int, message: str, kind: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": kind}})


def _from_local_process(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in _LOOPBACK_HOSTS and not any(h in request.headers for h in _PROXY_HEADERS)


def _bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value[:7].lower() == "bearer " else ""


@router.post("/chat/completions", include_in_schema=False)
async def forward_chat_completions(request: Request) -> Response:
    if not _from_local_process(request):
        return _error(403, "仅接受本机 DSH 子进程直连", "forbidden")
    try:
        claims = verify_token(_bearer(request))
    except DshTokenError as exc:
        return _error(401, f"DSH 转发令牌无效：{exc}", "unauthorized")
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "请求体不是 JSON", "invalid_request_error")
    if not isinstance(body, dict):
        return _error(400, "请求体必须是 JSON 对象", "invalid_request_error")
    config = await candidate_for(claims.identity)
    if config is None:
        return _error(409, "本次运行选定的模型已被停用或修改，请重新发起", "route_changed")
    return await relay_chat_completion(config, rewrite_request(body, config))


async def relay_chat_completion(config: ResolvedLLMConfig, payload: dict) -> Response:
    """把改写后的请求发给上游并原样回传（流式按字节转发）。"""
    identity = config.identity
    timeout = float(getattr(settings, "AI_CHAT_RUN_TIMEOUT_SECONDS", 180))
    try:
        client = await build_runtime_client(config, timeout=timeout)
    except LLMEndpointPolicyError as exc:
        reason = f"模型端点不可用：{exc}"
        mark_unavailable(identity, reason)
        return _error(502, reason, "upstream_unavailable")
    try:
        upstream = await client.send(
            client.build_request("POST", "chat/completions", json=payload), stream=True
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        reason = await describe_network_failure(config.endpoint_url, exc)
        if not isinstance(exc, httpx.ReadTimeout):
            mark_unavailable(identity, reason)
        logger.warning("DSH 模型转发失败（%s）：%s", config.model_name, reason)
        return _error(504 if isinstance(exc, httpx.ReadTimeout) else 502, reason, "upstream_unavailable")

    if upstream.status_code >= 400:
        content = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        if upstream.status_code >= 500 or upstream.status_code in _UNAVAILABLE_STATUS:
            mark_unavailable(identity, f"模型服务返回 HTTP {upstream.status_code}")
        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )

    mark_available(identity)

    async def relay() -> AsyncIterator[bytes]:
        try:
            # aiter_bytes 解掉上游 content-encoding：回传时只带 content-type，不能转发压缩字节
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
    )
