"""NativeEngine 的模型调用接缝（从 ``native_engine.py`` 原样抽出：该文件 812 行超行数门禁）。

唯一生产实现 :class:`AIServiceModelClient` 走既有 ``AIService``（本机优先路由，V197），
本模块没有任何网络代码；test_task6 的「engine 模块无第二套 HTTP client / 不写消息与 run 状态」
两条守卫同样扫描本文件。``native_engine`` 原样 re-export 两个名字，旧 import 路径不变。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ModelClient", "AIServiceModelClient"]


class ModelClient(Protocol):
    """模型调用接缝。生产实现只有 :class:`AIServiceModelClient` 一个。

    存在的理由是**可测**：守卫要注入"只产出占位串""中途抛异常""永远不结束"三种
    模型行为，而这些行为无法从真实 vLLM 稳定复现。接缝**不是**第二套 HTTP client ——
    它没有任何网络代码，网络只发生在 ``AIService`` 里。
    """

    async def resolve_model(self) -> str: ...

    def stream_chat(
        self, messages: list[dict[str, str]], *, model: str
    ) -> AsyncIterator[str]: ...


class AIServiceModelClient:
    """把既有 ``AIService.chat_completion(stream=True)`` 包成 :class:`ModelClient`。

    ``AIService._chat_stream`` 内部已经做 ``_merge_system_messages``（vLLM + Qwen3.5
    只允许开头一条 system），并按本机优先路由选择模型（本机不可用时服务器兜底）。
    本类只做参数传递，**没有** httpx 调用。

    ``served_model``：流结束后记录实际回答的模型（路由可能已改用服务器），供对话消息
    的 ``model_used`` 留痕；与 ``resolve_model()`` 的「首选模型」不一定相同。
    """

    def __init__(self, db: AsyncSession, *, temperature: float = 0.3) -> None:
        self._db = db
        self._temperature = temperature
        self.served_model: str | None = None

    async def resolve_model(self) -> str:
        """路由中排在最前的已启用对话模型（本机优先；无启用记录则回落服务端默认值）。"""
        from app.core.config import settings
        from app.models import AIModelType
        from app.services.ai_service import AIService

        active = await AIService(self._db).get_active_model(AIModelType.chat)
        return active.model_name if active else settings.DEFAULT_CHAT_MODEL

    async def stream_chat(
        self, messages: list[dict[str, str]], *, model: str
    ) -> AsyncIterator[str]:
        from app.services.ai_service import AIService
        from app.services.llm_route import last_route_outcome

        self.served_model = None
        generator = await AIService(self._db).chat_completion(
            messages=messages,
            model=model,
            stream=True,
            temperature=self._temperature,
        )
        async for chunk in generator:  # type: ignore[union-attr]
            yield chunk
        outcome = last_route_outcome()
        if outcome is not None:
            self.served_model = outcome.model_name
