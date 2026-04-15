"""Tests for architecture optimization: Problems 2, 3, 7

- UnifiedAIService: delegates to AIService and AIPluginService correctly
- UnifiedOCRService: auto-select engine, fallback logic, health check
- CacheManager: namespace operations, TTL, invalidation, stats
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import fakeredis.aioredis
import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Mock AsyncSession — UnifiedAIService tests mock all delegates anyway."""
    return MagicMock()


@pytest_asyncio.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ===========================================================================
# Problem 7: CacheManager
# ===========================================================================

class TestCacheManager:

    @pytest.mark.asyncio
    async def test_set_and_get(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("formula", "key1", {"value": 42})
        result = await cm.get("formula", "key1")
        assert result == {"value": 42}

    @pytest.mark.asyncio
    async def test_get_miss_returns_none(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        result = await cm.get("formula", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("auth", "token1", "abc")
        deleted = await cm.delete("auth", "token1")
        assert deleted is True
        assert await cm.get("auth", "token1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        deleted = await cm.delete("auth", "nope")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_namespace_prefix(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("ledger", "abc", "data")
        # Verify the raw key has the namespace prefix
        raw = await fake_redis.get("ledger:abc")
        assert raw is not None

    @pytest.mark.asyncio
    async def test_default_ttl_from_namespace(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("auth", "sess1", "val")
        ttl = await fake_redis.ttl("auth:sess1")
        # auth default TTL is 7200
        assert 7100 < ttl <= 7200

    @pytest.mark.asyncio
    async def test_custom_ttl(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("formula", "k", "v", ttl=60)
        ttl = await fake_redis.ttl("formula:k")
        assert 50 < ttl <= 60

    @pytest.mark.asyncio
    async def test_invalidate_namespace(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("notification", "a", 1)
        await cm.set("notification", "b", 2)
        await cm.set("formula", "c", 3)  # different namespace
        deleted = await cm.invalidate_namespace("notification")
        assert deleted == 2
        assert await cm.get("notification", "a") is None
        assert await cm.get("formula", "c") == 3  # untouched

    @pytest.mark.asyncio
    async def test_get_stats(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        await cm.set("formula", "x", 1)
        await cm.set("formula", "y", 2)
        await cm.set("auth", "z", 3)
        stats = await cm.get_stats()
        assert stats["formula"]["key_count"] == 2
        assert stats["auth"]["key_count"] == 1
        assert stats["_total"] >= 3

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        stats = await cm.get_stats()
        assert stats["_total"] == 0

    @pytest.mark.asyncio
    async def test_set_complex_value(self, fake_redis):
        from app.services.cache_manager import CacheManager
        cm = CacheManager(fake_redis)
        data = {"items": [1, 2, 3], "nested": {"a": True}}
        await cm.set("metabase", "complex", data)
        result = await cm.get("metabase", "complex")
        assert result == data

    @pytest.mark.asyncio
    async def test_namespaces_defined(self, fake_redis):
        from app.services.cache_manager import CacheManager
        assert "formula" in CacheManager.NAMESPACES
        assert "metabase" in CacheManager.NAMESPACES
        assert "ledger" in CacheManager.NAMESPACES
        assert "auth" in CacheManager.NAMESPACES
        assert "notification" in CacheManager.NAMESPACES


# ===========================================================================
# Problem 3: UnifiedOCRService
# ===========================================================================

class TestUnifiedOCRService:

    @pytest.mark.asyncio
    async def test_health_check_no_engines(self):
        from app.services.unified_ocr_service import UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = False
        svc._tesseract_available = False
        result = await svc.health_check()
        assert result["status"] == "unhealthy"
        assert result["default_engine"] is None

    @pytest.mark.asyncio
    async def test_health_check_paddle_only(self):
        from app.services.unified_ocr_service import UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = False
        result = await svc.health_check()
        assert result["status"] == "healthy"
        assert result["default_engine"] == "paddle"

    @pytest.mark.asyncio
    async def test_health_check_tesseract_only(self):
        from app.services.unified_ocr_service import UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = False
        svc._tesseract_available = True
        result = await svc.health_check()
        assert result["status"] == "healthy"
        assert result["default_engine"] == "tesseract"

    @pytest.mark.asyncio
    async def test_select_engine_invoice_paddle(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/tmp/发票_001.png", OCREngine.AUTO)
        assert engine == OCREngine.PADDLE

    @pytest.mark.asyncio
    async def test_select_engine_contract_paddle(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/docs/contract_v2.jpg", OCREngine.AUTO)
        assert engine == OCREngine.PADDLE

    @pytest.mark.asyncio
    async def test_select_engine_confirmation_paddle(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/docs/回函_ABC.png", OCREngine.AUTO)
        assert engine == OCREngine.PADDLE

    @pytest.mark.asyncio
    async def test_select_engine_general_tesseract(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/docs/report.png", OCREngine.AUTO)
        assert engine == OCREngine.TESSERACT

    @pytest.mark.asyncio
    async def test_select_engine_fallback_when_paddle_unavailable(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = False
        svc._tesseract_available = True
        # Invoice pattern but paddle unavailable → tesseract
        engine = await svc._select_engine("/tmp/发票.png", OCREngine.AUTO)
        assert engine == OCREngine.TESSERACT

    @pytest.mark.asyncio
    async def test_select_engine_no_engines_raises(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = False
        svc._tesseract_available = False
        with pytest.raises(RuntimeError, match="没有可用的OCR引擎"):
            await svc._select_engine("/tmp/test.png", OCREngine.AUTO)

    @pytest.mark.asyncio
    async def test_select_engine_forced_mode(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/docs/report.png", OCREngine.PADDLE)
        assert engine == OCREngine.PADDLE

    @pytest.mark.asyncio
    async def test_recognize_fallback(self):
        """If primary engine fails, fallback to the other"""
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = False
        svc._tesseract_available = True

        mock_result = {"text": "hello", "engine": "tesseract", "regions": []}
        svc._tesseract_recognize = AsyncMock(return_value=mock_result)

        result = await svc.recognize("/tmp/report.png", OCREngine.AUTO)
        assert result["engine"] == "tesseract"

    @pytest.mark.asyncio
    async def test_bank_statement_selects_paddle(self):
        from app.services.unified_ocr_service import OCREngine, UnifiedOCRService
        svc = UnifiedOCRService()
        svc._paddle_available = True
        svc._tesseract_available = True
        engine = await svc._select_engine("/docs/银行对账单_202501.png", OCREngine.AUTO)
        assert engine == OCREngine.PADDLE


# ===========================================================================
# Problem 2: UnifiedAIService
# ===========================================================================

class TestUnifiedAIService:

    @pytest.mark.asyncio
    async def test_init(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        assert svc._ai_service is not None
        assert svc._plugin_service is not None
        assert svc._ocr_service is not None

    @pytest.mark.asyncio
    async def test_chat_completion_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._ai_service.chat_completion = AsyncMock(return_value="hello")
        result = await svc.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
        )
        assert result == "hello"
        svc._ai_service.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedding_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._ai_service.embedding = AsyncMock(return_value=[0.1, 0.2])
        result = await svc.embedding("test text")
        assert result == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_ocr_recognize_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        mock_result = {"text": "OCR text", "engine": "tesseract", "regions": []}
        svc._ocr_service.recognize = AsyncMock(return_value=mock_result)
        result = await svc.ocr_recognize("/tmp/test.png", mode="auto")
        assert result["text"] == "OCR text"

    @pytest.mark.asyncio
    async def test_ocr_recognize_with_paddle_mode(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        from app.services.unified_ocr_service import OCREngine
        svc = UnifiedAIService(mock_db)
        svc._ocr_service.recognize = AsyncMock(
            return_value={"text": "paddle", "engine": "paddle", "regions": []}
        )
        await svc.ocr_recognize("/tmp/test.png", mode="paddle")
        call_args = svc._ocr_service.recognize.call_args
        assert call_args[0][1] == OCREngine.PADDLE

    @pytest.mark.asyncio
    async def test_list_plugins_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._plugin_service.list_plugins = AsyncMock(return_value=[{"id": "test"}])
        result = await svc.list_plugins()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_execute_plugin_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._plugin_service.execute_plugin = AsyncMock(
            return_value={"status": "ok"}
        )
        result = await svc.execute_plugin("test_plugin", {"param": 1})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_enable_plugin_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._plugin_service.enable_plugin = AsyncMock(
            return_value={"is_enabled": True}
        )
        result = await svc.enable_plugin("test_plugin")
        assert result["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_plugin_delegates(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._plugin_service.disable_plugin = AsyncMock(
            return_value={"is_enabled": False}
        )
        result = await svc.disable_plugin("test_plugin")
        assert result["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_health_check(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._ai_service.health_check = AsyncMock(return_value={
            "ollama_status": "unavailable",
            "paddleocr_status": "unavailable",
            "chromadb_status": "unavailable",
            "timestamp": "2026-01-01",
        })
        svc._ocr_service.health_check = AsyncMock(return_value={
            "status": "healthy",
            "engines": {"paddle": {"available": False}, "tesseract": {"available": True}},
            "default_engine": "tesseract",
        })
        result = await svc.health_check()
        assert "ai" in result
        assert "ocr" in result
        assert "timestamp" in result
        assert result["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, mock_db):
        from app.services.unified_ai_service import UnifiedAIService
        svc = UnifiedAIService(mock_db)
        svc._ai_service.health_check = AsyncMock(return_value={
            "ollama_status": "unavailable",
        })
        svc._ocr_service.health_check = AsyncMock(return_value={
            "status": "unhealthy",
        })
        result = await svc.health_check()
        assert result["status"] == "degraded"
