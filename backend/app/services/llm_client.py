"""LLM 客户端 — 统一的 vLLM/OpenAI 兼容 API 调用 + 熔断器

Phase 9: 从 stub 升级为实际 vLLM 调用
熔断器：连续 N 次失败后自动熔断，冷却期内直接返回降级响应，避免拖垮后端。
"""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = settings.LLM_BASE_URL
_API_KEY = settings.LLM_API_KEY
_MODEL = settings.DEFAULT_CHAT_MODEL

# --- 熔断器配置 ---
_CIRCUIT_FAILURE_THRESHOLD = 3   # 连续失败 N 次后熔断
_CIRCUIT_COOLDOWN_SECONDS = 60   # 熔断冷却期（秒）
_LLM_TIMEOUT_SYNC = 30.0        # 非流式超时（秒）
_LLM_TIMEOUT_STREAM = 90.0      # 流式超时（秒）


class _CircuitBreaker:
    """简单熔断器：closed → open → half-open"""

    def __init__(self):
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"  # closed | open | half-open

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            # 检查冷却期是否已过
            if time.time() - self._last_failure_time > _CIRCUIT_COOLDOWN_SECONDS:
                self._state = "half-open"
                return False
            return True
        return False

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= _CIRCUIT_FAILURE_THRESHOLD:
            self._state = "open"
            logger.warning(
                "LLM 熔断器打开：连续 %d 次失败，冷却 %ds",
                self._failure_count, _CIRCUIT_COOLDOWN_SECONDS
            )


_breaker = _CircuitBreaker()


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    stream: bool = False,
) -> str | AsyncGenerator[str, None]:
    """调用 LLM chat completion API

    Args:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: 模型名称，默认使用 DEFAULT_CHAT_MODEL
        stream: 是否流式返回

    Returns:
        非流式：完整回复文本
        流式：AsyncGenerator[str, None]
    """
    payload = {
        "model": model or _MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }

    if stream:
        return _stream_completion(payload)
    else:
        return await _sync_completion(payload)


async def _sync_completion(payload: dict) -> str:
    """同步调用（非流式），含熔断检查"""
    if _breaker.is_open:
        return "[LLM 服务熔断中，请稍后重试]"

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_SYNC) as client:
            resp = await client.post(
                f"{_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            _breaker.record_success()
            return data["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        _breaker.record_failure()
        logger.warning("LLM 服务不可用（连接失败），返回占位回复")
        return "[LLM 服务暂不可用，请检查 vLLM 是否启动]"
    except httpx.TimeoutException:
        _breaker.record_failure()
        logger.warning("LLM 调用超时（%ds）", _LLM_TIMEOUT_SYNC)
        return "[LLM 调用超时，请稍后重试]"
    except Exception as e:
        _breaker.record_failure()
        logger.error(f"LLM 调用失败: {e}")
        return f"[LLM 调用失败: {e}]"


async def _stream_completion(payload: dict) -> AsyncGenerator[str, None]:
    """流式调用，含熔断检查"""
    if _breaker.is_open:
        yield "[LLM 服务熔断中，请稍后重试]"
        return

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_STREAM) as client:
            async with client.stream(
                "POST",
                f"{_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_API_KEY}"},
            ) as resp:
                _breaker.record_success()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            import json
                            data = json.loads(chunk)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
    except httpx.ConnectError:
        _breaker.record_failure()
        yield "[LLM 服务暂不可用]"
    except httpx.TimeoutException:
        _breaker.record_failure()
        yield "[LLM 调用超时，请稍后重试]"
    except Exception as e:
        _breaker.record_failure()
        yield f"[LLM 错误: {e}]"
