"""统一 LLM 调用服务 — stub 引擎的结构化响应封装

设计目标：
- 走平台本机优先路由（V197，本机不可用时服务器兜底），不再自建 httpx 直连 `.env` 端点
- 超时 30s + 失败降级（返回 is_stub=True）
- 调用日志记录（耗时/token 数/成功率）
- 结构化响应（LLMResponse dataclass）

Requirements: F2.1, F2.4
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

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
    """统一 LLM 调用封装：stub 引擎经此调用平台对话路由（本机优先、服务器兜底）。

    ``model`` 只作优先提示（等于某条已启用模型的模型名时排到最前），不会把模型名
    套到另一条模型的端点上（ADR-ROUTE-005）。
    """

    def __init__(self, model: str | None = None):
        self.model = model

    async def _route(self):
        """对话路由候选（测试替换点）。"""
        from app.core.database import async_session
        from app.models.ai_models import AIModelType
        from app.services.llm_runtime import resolve_route

        async with async_session() as db:
            return await resolve_route(db, AIModelType.chat, requested_model=self.model)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """经平台路由调用对话模型

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 生成温度（默认 0.3，审计场景偏保守）
            max_tokens: 最大生成 token 数
            timeout: 超时秒数（默认 30s）

        Returns:
            LLMResponse: 结构化响应，失败时 is_stub=True + error 描述（不含上游正文）
        """
        from app.services.llm_route import route_chat_sync, served_model_label
        from app.services.llm_runtime import LLMRuntimeError, last_total_tokens

        start_time = time.perf_counter()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            route = await self._route()
            content = await route_chat_sync(
                route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )
        except LLMRuntimeError as exc:
            error_msg = f"{exc.code}: {exc}"
        except Exception as exc:  # noqa: BLE001 — stub 引擎约定失败降级而不是抛出
            error_msg = f"LLM call failed: {type(exc).__name__}"
        else:
            duration_ms = (time.perf_counter() - start_time) * 1000
            tokens_used = last_total_tokens()
            model = served_model_label(self.model)
            logger.info(
                "LLM call success: model=%s duration_ms=%.1f tokens_used=%d",
                model, duration_ms, tokens_used,
            )
            llm_metrics.record_call(
                duration_ms=duration_ms, tokens_used=tokens_used, success=True, model=model,
            )
            return LLMResponse(
                content=content, tokens_used=tokens_used, is_stub=False, duration_ms=duration_ms,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        model = self.model or "route"
        logger.warning(
            "LLM call failed: model=%s duration_ms=%.1f error=%s", model, duration_ms, error_msg,
        )
        llm_metrics.record_call(
            duration_ms=duration_ms, tokens_used=0, success=False, model=model, error=error_msg,
        )
        return LLMResponse(
            content=None, tokens_used=0, is_stub=True, error=error_msg, duration_ms=duration_ms,
        )
