"""export-word + check-incomplete 端点骨架测试（PRE-2-E2E）.

验证：
- export-word 对未注册 wp_code 返回 501
- check-incomplete 返回正确 schema（complete=false, reason, wp_code）
- 不存在的 wp_id 返回 404
- 分发注册表结构正确
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.wp_export_word_service import (
    CHECK_DISPATCH,
    EXPORT_DISPATCH,
    _match_dispatch_key,
    _resolve_wp_code,
    check_incomplete,
    export_word,
)


# ─── 单元测试：dispatch key 匹配 ─────────────────────────────────────────────


class TestMatchDispatchKey:
    """分发注册表键匹配逻辑。"""

    def test_exact_match(self):
        registry = {"A17-1": ..., "A18": ...}
        assert _match_dispatch_key("A17-1", registry) == "A17-1"

    def test_prefix_match(self):
        registry = {"A17": ..., "A18": ...}
        assert _match_dispatch_key("A17-3", registry) == "A17"

    def test_longest_prefix_wins(self):
        registry = {"A": ..., "A17": ..., "A17-1": ...}
        assert _match_dispatch_key("A17-1-sub", registry) == "A17-1"

    def test_no_match(self):
        registry = {"A17": ..., "A18": ...}
        assert _match_dispatch_key("B10-1", registry) is None

    def test_empty_registry(self):
        assert _match_dispatch_key("A17-1", {}) is None


# ─── 单元测试：dispatch 注册表当前为空 ───────────────────────────────────────


class TestDispatchRegistryEmpty:
    """当前无 spec 编排服务注册。"""

    def test_export_dispatch_empty(self):
        assert len(EXPORT_DISPATCH) == 0

    def test_check_dispatch_empty(self):
        assert len(CHECK_DISPATCH) == 0


# ─── 集成测试：通过 ASGI transport 测试端点 ──────────────────────────────────


@pytest.fixture
def fake_project_id():
    return uuid.uuid4()


@pytest.fixture
def fake_wp_id():
    return uuid.uuid4()


@pytest.fixture
def fake_wp_code():
    return "A17-3"


@pytest.mark.asyncio
async def test_export_word_returns_501_for_unregistered(
    fake_project_id, fake_wp_id, fake_wp_code
):
    """export-word 端点：未注册的 wp_code 应返回 501。"""
    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=fake_wp_code,
    ):
        result_bytes, wp_code, status = await export_word(
            db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
        )
        assert status == 501
        assert result_bytes is None
        assert wp_code == fake_wp_code


@pytest.mark.asyncio
async def test_export_word_returns_404_for_missing_wp(fake_project_id, fake_wp_id):
    """export-word 端点：不存在的 wp_id 应返回 404。"""
    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result_bytes, wp_code, status = await export_word(
            db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
        )
        assert status == 404
        assert wp_code is None
        assert result_bytes is None


@pytest.mark.asyncio
async def test_check_incomplete_returns_501_schema(
    fake_project_id, fake_wp_id, fake_wp_code
):
    """check-incomplete 端点：未注册时返回 complete=false + reason + wp_code。"""
    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=fake_wp_code,
    ):
        result, status = await check_incomplete(
            db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
        )
        assert status == 501
        assert result["complete"] is False
        assert result["wp_code"] == fake_wp_code
        assert result["reason"] == "检查服务未就绪"
        assert "missing_fields" in result
        assert isinstance(result["missing_fields"], list)


@pytest.mark.asyncio
async def test_check_incomplete_returns_404_for_missing_wp(
    fake_project_id, fake_wp_id
):
    """check-incomplete 端点：不存在的 wp_id 应返回 404。"""
    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result, status = await check_incomplete(
            db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
        )
        assert status == 404


@pytest.mark.asyncio
async def test_export_word_dispatches_when_registered(
    fake_project_id, fake_wp_id, fake_wp_code
):
    """export-word 端点：注册了 handler 后应正确分发。"""
    fake_bytes = b"fake-docx-content"
    mock_handler = AsyncMock(return_value=fake_bytes)

    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=fake_wp_code,
    ):
        # 临时注册 handler
        EXPORT_DISPATCH["A17"] = mock_handler
        try:
            result_bytes, wp_code, status = await export_word(
                db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
            )
            assert status == 200
            assert result_bytes == fake_bytes
            assert wp_code == fake_wp_code
            mock_handler.assert_awaited_once()
        finally:
            del EXPORT_DISPATCH["A17"]


@pytest.mark.asyncio
async def test_check_incomplete_dispatches_when_registered(
    fake_project_id, fake_wp_id, fake_wp_code
):
    """check-incomplete 端点：注册了 handler 后应正确分发。"""
    fake_result = {
        "complete": True,
        "missing_fields": [],
        "wp_code": fake_wp_code,
    }
    mock_handler = AsyncMock(return_value=fake_result)

    with patch(
        "app.services.wp_export_word_service._resolve_wp_code",
        new_callable=AsyncMock,
        return_value=fake_wp_code,
    ):
        CHECK_DISPATCH["A17"] = mock_handler
        try:
            result, status = await check_incomplete(
                db=AsyncMock(), project_id=fake_project_id, wp_id=fake_wp_id
            )
            assert status == 200
            assert result["complete"] is True
            mock_handler.assert_awaited_once()
        finally:
            del CHECK_DISPATCH["A17"]
