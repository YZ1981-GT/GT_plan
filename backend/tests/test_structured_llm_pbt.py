"""PBT: structured_llm_service round-trip 验证。

Validates: Requirements 6.2

用 hypothesis 生成简单 Pydantic 模型实例 → mock instructor client 返回该实例
→ `extract_structured` round-trip 解析回等值实例。
验证：Pydantic schema → instructor → Pydantic model 解析链路完整性。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel


# --- 测试用 Pydantic 模型 ---


class RoundTripModel(BaseModel):
    name: str
    value: int


# --- PBT round-trip ---


@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ),
    value=st.integers(min_value=-1000, max_value=1000),
)
async def test_extract_structured_round_trip(name, value):
    """**Validates: Requirements 6.2**

    任意合法 RoundTripModel 实例经 mock instructor → extract_structured
    round-trip 后应返回等值实例。
    """
    from app.services.structured_llm_service import extract_structured

    expected = RoundTripModel(name=name, value=value)

    # Mock instructor client: chat.completions.create 直接返回 expected 实例
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=expected)

    # Mock breaker
    mock_breaker = MagicMock()
    mock_breaker.is_open = False

    with patch(
        "app.services.structured_llm_service._get_instructor_client",
        return_value=mock_client,
    ), patch("app.services.structured_llm_service.settings") as mock_settings, patch(
        "app.services.structured_llm_service._breaker", mock_breaker
    ), patch(
        "app.services.structured_llm_service._guided_unsupported_logged", False
    ):
        mock_settings.LLM_GUIDED_DECODING_ENABLED = True
        mock_settings.LLM_STRUCTURED_MAX_RETRIES = 2
        mock_settings.DEFAULT_CHAT_MODEL = "test-model"

        result = await extract_structured(
            [{"role": "user", "content": "extract structured data"}],
            RoundTripModel,
        )

    # Round-trip 等值断言
    assert result == expected
    assert result.name == name
    assert result.value == value
    assert isinstance(result, RoundTripModel)
