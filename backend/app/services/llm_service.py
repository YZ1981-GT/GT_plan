"""统一 LLM 调用服务 — 所有 stub 引擎通过此服务调用 vLLM

设计目标：
- OpenAI 兼容 API 调用（httpx async）
- 超时 30s + 失败降级（返回 is_stub=True）
- 调用日志记录（耗时/token 数/成功率）
- 结构化响应（LLMResponse dataclass）

Requirements: F2.1, F2.4
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.services.llm_metrics import llm_metrics

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 调用结构化响应"""

    content: str | None = None
    tokens_used: int = 0
    is_stub: bool = False
    error: str | None = None
    duration_ms: float = 0.0
    # K-4 解释链字段（task 4.2）— 各引擎填充供前端展示推理依据
    reasoning: str | None = None
    references: list[dict] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    confidence: float = 0.0


def build_reasoning_chain(
    reasoning: str | None = None,
    references: list[dict] | None = None,
    data_sources: list[str] | None = None,
    is_llm_stub: bool = True,
    base_confidence: float = 0.0,
) -> tuple[str | None, list[dict], list[str], float]:
    """K-4 解释链统一构造器（task 4.2 / ADR-6）

    所有 stub 引擎共用：
    - is_llm_stub=True  → confidence 强制 0.0
    - is_llm_stub=False → confidence = clamp(base_confidence, 0.0, 1.0)
    - references / data_sources 为 None 时归一化为 []

    Returns: (reasoning, references, data_sources, confidence)
    """
    refs = list(references) if references else []
    sources = list(data_sources) if data_sources else []
    if is_llm_stub:
        confidence = 0.0
    else:
        if base_confidence > 1.0:
            confidence = 1.0
        elif base_confidence < 0.0:
            confidence = 0.0
        else:
            confidence = float(base_confidence)
    return reasoning, refs, sources, confidence


class LLMService:
    """统一 LLM 调用封装，所有 stub 引擎通过此服务调用 vLLM"""

    BASE_URL: str = settings.LLM_BASE_URL
    MODEL: str = settings.DEFAULT_CHAT_MODEL

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        if base_url is not None:
            self.BASE_URL = base_url
        if model is not None:
            self.MODEL = model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """调用 vLLM OpenAI 兼容 API

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 生成温度（默认 0.3，审计场景偏保守）
            max_tokens: 最大生成 token 数
            timeout: 超时秒数（默认 30s）

        Returns:
            LLMResponse: 结构化响应，失败时 is_stub=True + error 描述
        """
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    json={
                        "model": self.MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                )
                resp.raise_for_status()
                data = resp.json()

                content = data["choices"][0]["message"]["content"]
                tokens_used = data.get("usage", {}).get("total_tokens", 0)
                duration_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "LLM call success: model=%s duration_ms=%.1f tokens_used=%d",
                    self.MODEL,
                    duration_ms,
                    tokens_used,
                )

                llm_metrics.record_call(
                    duration_ms=duration_ms,
                    tokens_used=tokens_used,
                    success=True,
                    model=self.MODEL,
                )

                return LLMResponse(
                    content=content,
                    tokens_used=tokens_used,
                    is_stub=False,
                    duration_ms=duration_ms,
                )

        except httpx.TimeoutException as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"LLM call timeout after {timeout}s"
            logger.warning(
                "LLM call timeout: model=%s duration_ms=%.1f error=%s",
                self.MODEL,
                duration_ms,
                str(e),
            )
            llm_metrics.record_call(
                duration_ms=duration_ms,
                tokens_used=0,
                success=False,
                model=self.MODEL,
                error=error_msg,
            )
            return LLMResponse(
                content=None,
                tokens_used=0,
                is_stub=True,
                error=error_msg,
                duration_ms=duration_ms,
            )

        except httpx.HTTPStatusError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"LLM HTTP error {e.response.status_code}: {e.response.text[:200]}"
            logger.warning(
                "LLM call HTTP error: model=%s duration_ms=%.1f status=%d",
                self.MODEL,
                duration_ms,
                e.response.status_code,
            )
            llm_metrics.record_call(
                duration_ms=duration_ms,
                tokens_used=0,
                success=False,
                model=self.MODEL,
                error=error_msg,
            )
            return LLMResponse(
                content=None,
                tokens_used=0,
                is_stub=True,
                error=error_msg,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"LLM call failed: {type(e).__name__}: {e}"
            logger.warning(
                "LLM call failed: model=%s duration_ms=%.1f error=%s",
                self.MODEL,
                duration_ms,
                error_msg,
            )
            llm_metrics.record_call(
                duration_ms=duration_ms,
                tokens_used=0,
                success=False,
                model=self.MODEL,
                error=error_msg,
            )
            return LLMResponse(
                content=None,
                tokens_used=0,
                is_stub=True,
                error=error_msg,
                duration_ms=duration_ms,
            )
