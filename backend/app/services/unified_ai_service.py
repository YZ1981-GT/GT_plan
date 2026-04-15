"""统一AI服务入口 — 整合核心能力与插件管理

Wraps AIService (core capabilities) and AIPluginService (plugin management)
into a single facade. Existing services remain untouched — this is additive.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIService
from app.services.ai_plugin_service import AIPluginService
from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

logger = logging.getLogger(__name__)


class UnifiedAIService:
    """统一AI服务入口 — 整合核心能力与插件管理"""

    def __init__(self, db: AsyncSession):
        self._ai_service = AIService(db)
        self._plugin_service = AIPluginService()
        self._ocr_service = UnifiedOCRService()
        self._db = db

    # ------------------------------------------------------------------
    # Core capabilities (delegate to AIService)
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> Any:
        """LLM对话（同步/流式）"""
        return await self._ai_service.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            stream=stream,
        )

    async def embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """文本向量化"""
        return await self._ai_service.embedding(text=text, model=model)

    async def ocr_recognize(
        self,
        image_path: str,
        mode: str = "auto",
    ) -> dict:
        """OCR识别 — 代理到统一OCR服务层"""
        engine = OCREngine(mode) if mode in [e.value for e in OCREngine] else OCREngine.AUTO
        return await self._ocr_service.recognize(image_path, engine)

    # ------------------------------------------------------------------
    # Plugin management (delegate to AIPluginService)
    # ------------------------------------------------------------------

    async def list_plugins(self) -> list[dict]:
        """列出所有插件"""
        return await self._plugin_service.list_plugins(self._db)

    async def execute_plugin(self, plugin_id: str, params: dict) -> dict:
        """执行插件"""
        return await self._plugin_service.execute_plugin(self._db, plugin_id, params)

    async def enable_plugin(self, plugin_id: str) -> dict:
        """启用插件"""
        return await self._plugin_service.enable_plugin(self._db, plugin_id)

    async def disable_plugin(self, plugin_id: str) -> dict:
        """禁用插件"""
        return await self._plugin_service.disable_plugin(self._db, plugin_id)

    # ------------------------------------------------------------------
    # Unified health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """统一AI+OCR健康检查"""
        ai_health = await self._ai_service.health_check()
        ocr_health = await self._ocr_service.health_check()

        overall = "healthy"
        if ai_health.get("ollama_status") != "healthy" and ocr_health["status"] != "healthy":
            overall = "degraded"

        return {
            "status": overall,
            "ai": ai_health,
            "ocr": ocr_health,
            "timestamp": datetime.now().isoformat(),
        }
