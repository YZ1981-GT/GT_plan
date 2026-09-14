"""POST /api/acnr/resolve-batch 批量解析端点集成测试 — Task 18 [Req-15.4]

验证:
1. 正常批量解析返回等长结果数组
2. items ≤ 50 限制（超出返回 422）
3. 空 items 返回空数组
4. 携带 project_id 时复用 auth 校验
5. 单项解析失败不影响其他项

Validates: Requirements 15.3, 15.4
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))


# ─── Fake ResolveResult dataclass (mirrors resolver.ResolveResult) ───────────

@dataclass
class FakeResolveResult:
    found: bool = False
    addr_id: Optional[str] = None
    entry_type: Optional[str] = None
    cell_address: Optional[str] = None
    semantic_label: Optional[str] = None
    formula_ref: Optional[str] = None
    uri: Optional[str] = None
    jump_route: Optional[str] = None
    wp_id: Optional[str] = None
    error: Optional[str] = None
    candidates: Optional[list] = None
    source_layer: Optional[str] = None


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_full_resolve():
    """Mock full_resolve to return predictable results."""
    async def _fake_full_resolve(*, uri=None, formula_ref=None, addr_id=None,
                                  index_ref=None, project_id=None, db=None, **kwargs):
        # Return found for known addr_ids, miss for others
        input_key = uri or formula_ref or addr_id or index_ref or ""
        if input_key and "invalid" not in input_key:
            return FakeResolveResult(
                found=True,
                addr_id=addr_id or f"resolved/{input_key}",
                entry_type="cell",
                source_layer="L1_cell",
            )
        return FakeResolveResult(found=False, error="not_found")

    with patch("app.routers.acnr.full_resolve", side_effect=_fake_full_resolve) as m:
        yield m


@pytest.fixture
def mock_auth():
    """Mock auth to always pass."""
    with patch("app.routers.acnr.check_project_access", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_user():
    """Mock get_current_user."""

    class FakeUser:
        id = "test-user-id"
        role = "admin"

    return FakeUser()


# ─── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_batch_returns_equal_length_results(mock_full_resolve, mock_auth, mock_user):
    """正常批量解析返回等长结果数组。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem

    body = AcnrResolveBatchRequest(
        items=[
            AcnrResolveBatchItem(addr_id="D2/D2-2/E100"),
            AcnrResolveBatchItem(addr_id="D2/D2-2/E200"),
            AcnrResolveBatchItem(formula_ref="WP('D2','D2-2','E300')"),
        ],
        project_id=None,
    )

    results = await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    assert len(results) == 3
    assert results[0]["found"] is True
    assert results[1]["found"] is True
    assert results[2]["found"] is True


@pytest.mark.asyncio
async def test_resolve_batch_items_limit_50(mock_full_resolve, mock_auth, mock_user):
    """items > 50 时返回 422。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from fastapi import HTTPException

    body = AcnrResolveBatchRequest(
        items=[AcnrResolveBatchItem(addr_id=f"D2/D2-2/E{i}") for i in range(51)],
        project_id=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_batch_empty_items_returns_empty(mock_full_resolve, mock_auth, mock_user):
    """空 items 返回空数组。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest

    body = AcnrResolveBatchRequest(items=[], project_id=None)

    results = await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())
    assert results == []


@pytest.mark.asyncio
async def test_resolve_batch_with_project_id_checks_auth(mock_full_resolve, mock_auth, mock_user):
    """携带 project_id 时调用 check_project_access 一次。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem

    body = AcnrResolveBatchRequest(
        items=[
            AcnrResolveBatchItem(addr_id="D2/D2-2/E100"),
            AcnrResolveBatchItem(addr_id="D2/D2-2/E200"),
        ],
        project_id="proj-123",
    )

    await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    # Auth checked exactly once (not per-item)
    mock_auth.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_batch_auth_failure_returns_403(mock_full_resolve, mock_user):
    """项目授权失败时返回 403。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem
    from fastapi import HTTPException

    # Mock auth to raise 403
    with patch("app.routers.acnr.check_project_access", side_effect=HTTPException(status_code=403)):
        # Also mock metrics to avoid import issues
        with patch("app.services.acnr.metrics.get_acnr_metrics") as mock_metrics:
            mock_metrics.return_value.record_auth_reject = lambda **kw: None

            body = AcnrResolveBatchRequest(
                items=[AcnrResolveBatchItem(addr_id="D2/D2-2/E100")],
                project_id="unauthorized-project",
            )

            with pytest.raises(HTTPException) as exc_info:
                await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

            assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_resolve_batch_single_item_error_does_not_break_others(mock_auth, mock_user):
    """单项解析异常不影响其他项。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem

    call_count = 0

    async def _mixed_resolve(*, uri=None, formula_ref=None, addr_id=None,
                              index_ref=None, project_id=None, db=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated DB error")
        return FakeResolveResult(found=True, addr_id=addr_id or "test")

    with patch("app.routers.acnr.full_resolve", side_effect=_mixed_resolve):
        body = AcnrResolveBatchRequest(
            items=[
                AcnrResolveBatchItem(addr_id="D2/D2-2/E100"),
                AcnrResolveBatchItem(addr_id="D2/D2-2/E200"),  # This will throw
                AcnrResolveBatchItem(addr_id="D2/D2-2/E300"),
            ],
            project_id=None,
        )

        results = await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    assert len(results) == 3
    assert results[0]["found"] is True
    assert results[1]["found"] is False
    assert results[1]["error"] == "resolve_error"
    assert results[2]["found"] is True


@pytest.mark.asyncio
async def test_resolve_batch_without_project_id_strips_wp_data(mock_full_resolve, mock_auth, mock_user):
    """不携带 project_id 时不返回 wp_id/jump_route。"""
    from app.routers.acnr import acnr_resolve_batch, AcnrResolveBatchRequest, AcnrResolveBatchItem

    # Override mock to include wp_id/jump_route
    async def _resolve_with_wp(**kwargs):
        return FakeResolveResult(
            found=True,
            addr_id="D2/D2-2/E100",
            wp_id="wp-uuid-123",
            jump_route="/workpapers/wp-uuid-123?sheet=D2-2",
        )

    with patch("app.routers.acnr.full_resolve", side_effect=_resolve_with_wp):
        body = AcnrResolveBatchRequest(
            items=[AcnrResolveBatchItem(addr_id="D2/D2-2/E100")],
            project_id=None,  # No project_id
        )

        results = await acnr_resolve_batch(body=body, _user=mock_user, db=AsyncMock())

    assert len(results) == 1
    assert "wp_id" not in results[0]
    assert "jump_route" not in results[0]
