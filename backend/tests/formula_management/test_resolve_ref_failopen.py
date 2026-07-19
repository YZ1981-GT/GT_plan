"""resolve_ref fail-open 行为直接测试（#3 公式管理加固）。

验证：
1. ACNR full_resolve 正常返回 found → resolve_ref 返回 found=True + canonical addr_id
2. ACNR full_resolve 返回 miss → resolve_ref 返回 found=False + 回显入参
3. ACNR full_resolve 抛异常 → resolve_ref 返回 found=False + fail_open=True（绝不阻断）
4. formula_ref 和 addr_id 两种输入形式均正常
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from dataclasses import dataclass


@dataclass
class FakeResolveResult:
    found: bool
    addr_id: str | None = None
    formula_ref: str | None = None
    semantic_label: str | None = None
    error: str | None = None


@pytest.mark.asyncio
async def test_resolve_ref_found():
    """ACNR 命中 → found=True, canonical addr_id 返回。"""
    from app.services.formula_management.engine import resolve_ref

    fake = FakeResolveResult(found=True, addr_id="D2/D2-1/B5", semantic_label="应收账款期末")
    with patch("app.services.acnr.resolver.full_resolve", new=AsyncMock(return_value=fake)):
        r = await resolve_ref(formula_ref="WP(D2-1, B5)", project_id="proj-1")

    assert r.found is True
    assert r.addr_id == "D2/D2-1/B5"
    assert r.semantic_label == "应收账款期末"
    assert r.fail_open is False
    assert r.error is None


@pytest.mark.asyncio
async def test_resolve_ref_miss():
    """ACNR 未命中 → found=False, 回显入参 addr_id。"""
    from app.services.formula_management.engine import resolve_ref

    fake = FakeResolveResult(found=False, addr_id=None, error="not_found")
    with patch("app.services.acnr.resolver.full_resolve", new=AsyncMock(return_value=fake)):
        r = await resolve_ref(addr_id="nonexistent/addr", project_id="proj-1")

    assert r.found is False
    assert r.addr_id == "nonexistent/addr"  # 回显入参
    assert r.fail_open is False
    assert r.error == "not_found"


@pytest.mark.asyncio
async def test_resolve_ref_exception_failopen():
    """ACNR 抛异常 → fail-open 降级：found=False + fail_open=True，绝不抛出。"""
    from app.services.formula_management.engine import resolve_ref

    with patch(
        "app.services.acnr.resolver.full_resolve",
        new=AsyncMock(side_effect=RuntimeError("ACNR 连接超时")),
    ):
        r = await resolve_ref(formula_ref="TB(1122, 期末余额)", project_id="proj-1")

    assert r.found is False
    assert r.fail_open is True
    assert r.error == "acnr_unavailable_fallback"
    # 回显入参
    assert r.formula_ref == "TB(1122, 期末余额)"


@pytest.mark.asyncio
async def test_resolve_ref_addr_id_input():
    """addr_id 形式输入正常工作。"""
    from app.services.formula_management.engine import resolve_ref

    fake = FakeResolveResult(found=True, addr_id="report/BS-001", formula_ref=None)
    with patch("app.services.acnr.resolver.full_resolve", new=AsyncMock(return_value=fake)):
        r = await resolve_ref(addr_id="report/BS-001", project_id="proj-1")

    assert r.found is True
    assert r.addr_id == "report/BS-001"


@pytest.mark.asyncio
async def test_resolve_ref_both_none():
    """formula_ref 和 addr_id 都为 None → 仍然调 ACNR（不崩溃）。"""
    from app.services.formula_management.engine import resolve_ref

    fake = FakeResolveResult(found=False, error="empty_input")
    with patch("app.services.acnr.resolver.full_resolve", new=AsyncMock(return_value=fake)):
        r = await resolve_ref(formula_ref=None, addr_id=None, project_id=None)

    assert r.found is False
    assert r.fail_open is False
