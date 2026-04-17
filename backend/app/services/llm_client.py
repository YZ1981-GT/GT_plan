"""LLM 客户端 — 统一的 vLLM/OpenAI 兼容 API 调用

Phase 9: 从 stub 升级为实际 vLLM 调用
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = settings.LLM_BASE_URL
_API_KEY = settings.LLM_API_KEY
_MODEL = settings.DEFAULT_CHAT_MODEL


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
    """同步调用（非流式）"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        logger.warning("LLM 服务不可用（连接失败），返回占位回复")
        return "[LLM 服务暂不可用，请检查 vLLM 是否启动]"
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return f"[LLM 调用失败: {e}]"


async def _stream_completion(payload: dict) -> AsyncGenerator[str, None]:
    """流式调用"""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_API_KEY}"},
            ) as resp:
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
        yield "[LLM 服务暂不可用]"
    except Exception as e:
        yield f"[LLM 错误: {e}]"
