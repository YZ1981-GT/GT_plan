"""G6 其他债权投资(main组) — API 集成测试（render + 导入导出 + AI + 公式验证）."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g6_other_bond_investment_main_import_export import (
    _SUPPORTED_SHEETS,
)
from app.routers.wp_render_strategies._g6_other_bond_investment_main_service import (
    G6OtherBondInvestmentMainService,
)


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_g6_main_render_dispatch_registered():
    assert "g6-other-bond-investment-main" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g6-other-bond-investment-main"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G6-2", "G6-3", "G6-4"])
async def test_g6_main_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/g6-main/export-template?sheet={sheet}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_g6_main_specs_cover_three_sheets():
    assert _SUPPORTED_SHEETS == {"G6-2", "G6-3", "G6-4"}


def test_g6_validate_formulas_debit_balance_ok():
    errors = G6OtherBondInvestmentMainService.validate_formulas({
        "debit_balance_check": {
            "opening": 100,
            "debit": 50,
            "credit": 20,
            "balance": 130,
        },
    })
    assert errors == []


def test_g6_validate_formulas_debit_balance_fail():
    errors = G6OtherBondInvestmentMainService.validate_formulas({
        "debit_balance_check": {
            "opening": 100,
            "debit": 50,
            "credit": 20,
            "balance": 999,
        },
    })
    assert len(errors) == 1
    assert errors[0]["field"] == "debit_balance"


def test_g6_validate_formulas_ecl_chain_ok():
    errors = G6OtherBondInvestmentMainService.validate_formulas({
        "ecl_check": {
            "provision_3": 50,
            "adjustment_6": 10,
            "result_8": 60,
            "balance_7": 1000,
            "rate_2a": 0.06,
        },
    })
    assert errors == []


@given(
    opening=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    debit=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    credit=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=5)
def test_g6_pbt_debit_balance_consistency(opening: float, debit: float, credit: float):
    expected = opening + debit - credit
    errors = G6OtherBondInvestmentMainService.validate_formulas({
        "debit_balance_check": {
            "opening": opening,
            "debit": debit,
            "credit": credit,
            "balance": expected,
        },
    })
    assert errors == []


@pytest.mark.asyncio
async def test_g6_main_ai_sections(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "ok"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g6_other_bond_investment_main_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in ("adjudication-analysis", "disclosure-text"):
            resp = await client.post(
                f"/api/workpapers/test-wp/g6-main/ai/{section}",
                json={"existingContent": "", "relatedContext": {}},
            )
            assert resp.status_code == 200, section
