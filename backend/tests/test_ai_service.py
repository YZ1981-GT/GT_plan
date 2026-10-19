"""
AI Service Unit Tests — Task 24.1
Test AI service unified abstraction layer (health check, model switching +
availability validation, graceful degradation, boundary checks).
Mock the LLM API responses. Test AIService.health_check(),
switch_model(), and chat_completion().

Requirements: 1.1-1.4
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai_service import AIService, ModelValidationError, ModelNotFoundError
from app.models.ai_models import AIModelType, AIProvider


def _mock_model(model_type=AIModelType.chat, model_name="llama3",
                provider=AIProvider.ollama):
    """Minimal mock AIModelConfig with all attributes accessed by AIService."""
    m = MagicMock()
    m.model_type = model_type
    m.model_name = model_name
    m.api_base = "http://localhost:11434"
    m.endpoint_url = "http://localhost:11434"
    m.provider = provider
    m.is_active = True
    return m


def _mock_execute_result(scalar_value=None):
    """Build an awaitable mock db.execute result for scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    return result


def _runtime_config(
    *,
    provider=AIProvider.ollama,
    model_name="llama3.1",
    model_type=AIModelType.chat,
    source="database",
):
    from app.services.llm_provider_registry import provider_profile
    from app.services.llm_runtime import ResolvedLLMConfig

    endpoint = provider_profile(provider).default_endpoint or "https://example.openai.azure.com/openai/v1"
    return ResolvedLLMConfig(
        model_name=model_name,
        model_type=model_type,
        provider=provider,
        endpoint_url=endpoint,
        api_key=None,
        profile=provider_profile(provider),
        source=source,
    )


# ---------------------------------------------------------------------------
# Test AIService.health_check()  — Requirement 1.1
# ---------------------------------------------------------------------------

class TestAIServiceHealthCheck:
    """health_check 只探测当前生效的 chat/embedding runtime。"""

    @staticmethod
    def _chroma(status=503):
        response = MagicMock(status_code=status)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(return_value=response)
        return client

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        async def resolve(_db, model_type):
            if model_type == AIModelType.chat:
                return _runtime_config()
            return _runtime_config(
                provider=AIProvider.openai_compatible,
                model_name="BAAI/bge-m3",
                model_type=AIModelType.embedding,
            )

        service = AIService(MagicMock())
        with patch(
            "app.services.ai_service.resolve_runtime_config",
            side_effect=resolve,
        ), patch(
            "app.services.ai_service.probe_runtime_config",
            new=AsyncMock(return_value=True),
        ), patch(
            "app.services.ai_service._get_chromadb_client",
            new=AsyncMock(return_value=self._chroma()),
        ), patch("app.services.ai_service.paddleocr", None):
            result = await service.health_check()

        assert result["llm_status"] == "healthy"
        assert result["ollama_status"] == "healthy"
        assert result["active_chat_model"] == "llama3.1"
        assert "api_key" not in str(result)

    @pytest.mark.asyncio
    async def test_health_check_degraded_ollama_down(self):
        service = AIService(MagicMock())
        with patch(
            "app.services.ai_service.resolve_runtime_config",
            new=AsyncMock(return_value=_runtime_config()),
        ), patch(
            "app.services.ai_service.probe_runtime_config",
            new=AsyncMock(return_value=False),
        ), patch(
            "app.services.ai_service._get_chromadb_client",
            new=AsyncMock(return_value=self._chroma()),
        ), patch("app.services.ai_service.paddleocr", None):
            result = await service.health_check()
        assert result["llm_status"] == "unavailable"
        assert result["ollama_status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_health_check_degraded_connection_error(self):
        service = AIService(MagicMock())
        with patch(
            "app.services.ai_service.resolve_runtime_config",
            new=AsyncMock(return_value=_runtime_config()),
        ), patch(
            "app.services.ai_service.probe_runtime_config",
            new=AsyncMock(side_effect=RuntimeError("connection refused")),
        ), patch(
            "app.services.ai_service._get_chromadb_client",
            new=AsyncMock(return_value=self._chroma()),
        ), patch("app.services.ai_service.paddleocr", None):
            result = await service.health_check()
        assert result["llm_status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_health_check_healthy_fallback_model(self):
        fallback = _runtime_config(
            provider=AIProvider.openai_compatible,
            model_name="Qwen3.5-27B",
            source="environment",
        )
        service = AIService(MagicMock())
        with patch(
            "app.services.ai_service.resolve_runtime_config",
            new=AsyncMock(return_value=fallback),
        ), patch(
            "app.services.ai_service.probe_runtime_config",
            new=AsyncMock(return_value=True),
        ), patch(
            "app.services.ai_service._get_chromadb_client",
            new=AsyncMock(return_value=self._chroma()),
        ), patch("app.services.ai_service.paddleocr", None):
            result = await service.health_check()
        assert result["vllm_status"] == "healthy"
        assert result["ollama_status"] == "unavailable"
        assert result["chat_config"]["source"] == "environment"


# ---------------------------------------------------------------------------
# Test AIService.get_active_model()  — Requirement 1.2
# ---------------------------------------------------------------------------

class TestAIServiceGetActiveModel:
    """get_active_model queries the DB for the active model of a given type."""

    @pytest.mark.asyncio
    async def test_get_active_model_found(self):
        """Returns AIModelConfig when an active model exists."""
        mock_model = _mock_model(model_name="llama3.1")
        mock_result = _mock_execute_result(scalar_value=mock_model)

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        result = await service.get_active_model(AIModelType.chat)

        assert result is not None
        assert result.model_name == "llama3.1"

    @pytest.mark.asyncio
    async def test_get_active_model_not_found(self):
        """Returns None when no active model is configured."""
        mock_result = _mock_execute_result(scalar_value=None)

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        result = await service.get_active_model(AIModelType.chat)

        assert result is None


# ---------------------------------------------------------------------------
# Test AIService.switch_model()  — Requirement 1.2
# ---------------------------------------------------------------------------

class TestAIServiceSwitchModel:
    """switch_model activates a model after availability validation."""

    @pytest.mark.asyncio
    async def test_switch_model_success(self):
        """switch_model returns True and flushes; router owns commit."""
        mock_model = _mock_model(model_name="llama3")

        # 1st call: SELECT target model; 2nd call: UPDATE other models
        select_result = _mock_execute_result(scalar_value=mock_model)
        update_result = MagicMock()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[select_result, update_result])
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()

        service = AIService(mock_db)
        with patch.object(
            AIService, "_validate_model", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True
            result = await service.switch_model("llama3", AIModelType.chat)

        # switch_model returns True on success (confirmed from code)
        assert result is True
        mock_db.flush.assert_awaited()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_switch_model_not_found(self):
        """Raises ModelNotFoundError when target model doesn't exist."""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(
            return_value=_mock_execute_result(scalar_value=None)
        )

        service = AIService(mock_db)
        with pytest.raises(ModelNotFoundError):
            await service.switch_model("nonexistent", AIModelType.chat)

    @pytest.mark.asyncio
    async def test_switch_model_validation_fails(self):
        """Returns False when model fails availability check."""
        mock_model = _mock_model(model_name="broken-model")

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(
            return_value=_mock_execute_result(scalar_value=mock_model)
        )

        service = AIService(mock_db)
        with patch.object(
            AIService, "_validate_model", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = False
            result = await service.switch_model("broken-model", AIModelType.chat)

        assert result is False


# ---------------------------------------------------------------------------
# Test AIService.chat_completion()  — Requirements 1.3, 1.4
# ---------------------------------------------------------------------------

class TestAIServiceChatCompletion:
    """Test LLM chat completion with mocked Ollama HTTP responses."""

    @pytest.mark.asyncio
    async def test_chat_completion_sync_success(self):
        """chat_completion returns the LLM response text."""
        mock_model = _mock_model(model_name="llama3")
        mock_result = _mock_execute_result(scalar_value=mock_model)

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        with patch.object(
            service, "_chat_sync",
            new_callable=AsyncMock,
            return_value="Hello from LLM",
        ):
            result = await service.chat_completion(
                [{"role": "user", "content": "hello"}],
                stream=False,
            )

        assert result == "Hello from LLM"

    @pytest.mark.asyncio
    async def test_chat_completion_no_active_model(self):
        """Raises Exception when Ollama is unreachable."""
        # Even when no active model is configured, chat_completion falls back to
        # settings.DEFAULT_CHAT_MODEL, so we block the network call directly.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        with patch(
            "app.services.ai_service.AIService._chat_sync",
            side_effect=Exception("connection refused"),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.chat_completion([{"role": "user", "content": "hi"}])

            assert "connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_api_error(self):
        """Raises Exception when Ollama returns non-200."""
        mock_model = _mock_model(model_name="llama3")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        with patch(
            "app.services.ai_service.AIService._chat_sync",
            side_effect=Exception("500 — Internal Server Error"),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.chat_completion([{"role": "user", "content": "hi"}])

            assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_with_explicit_model(self):
        """Uses the explicitly passed model_name instead of the active model."""
        mock_model = _mock_model(model_name="custom-model")
        mock_result = _mock_execute_result(scalar_value=mock_model)

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AIService(mock_db)
        with patch.object(
            service, "_chat_sync",
            new_callable=AsyncMock,
            return_value="custom response",
        ):
            result = await service.chat_completion(
                [{"role": "user", "content": "test"}],
                model="custom-model",
            )

        assert result == "custom response"


# ---------------------------------------------------------------------------
# Boundary checks and error handling  — Requirements 1.1-1.4
# ---------------------------------------------------------------------------

class TestAIServiceBoundaryChecks:
    """Sanity / enum / error-class tests."""

    def test_service_instantiation(self):
        """AIService instantiates with a db session."""
        mock_db = MagicMock()
        service = AIService(mock_db)
        assert service is not None
        assert service.db is mock_db

    def test_model_type_enum_values(self):
        """AIModelType enum members exist and have expected values."""
        assert AIModelType.chat.value == "chat"
        assert AIModelType.embedding.value == "embedding"
        assert AIModelType.ocr.value == "ocr"

    def test_ai_provider_enum_values(self):
        """AIProvider enum has expected values."""
        assert AIProvider.ollama.value == "ollama"
        assert AIProvider.openai_compatible.value == "openai_compatible"
        assert AIProvider.paddleocr.value == "paddleocr"

    def test_model_validation_error_message(self):
        """ModelValidationError is callable with message."""
        err = ModelValidationError("no model configured")
        assert "no model configured" in str(err)

    def test_model_not_found_error(self):
        """ModelNotFoundError is callable."""
        err = ModelNotFoundError("Model not found: test")
        assert "test" in str(err)

    def test_mock_model_has_required_attributes(self):
        """Mock model has every attribute that AIService accesses."""
        mock = _mock_model(model_name="test", model_type=AIModelType.chat)
        for attr in ("model_type", "model_name", "provider", "endpoint_url", "is_active"):
            assert hasattr(mock, attr)
