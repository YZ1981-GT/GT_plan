"""总体完整性核对 — 端点契约测试（voucher-sampling-reconcile-balance-source Task 3）

Property 5 改写：接入科目余额表后，资产类科目（如 1122）也应返回 reconcile_available=true
（不再因科目类别恒返 false）。新增逐方向字段必须存在且类型正确。

Validates: Requirements R1.1, R1.5, R2.1, R5.1
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers.voucher_sampling import router
from app.services.sampling_population_reconcile import PopulationReconcileFacts

from tests.test_voucher_sampling_integration import (
    _legacy_exclusions,
    _make_extract_request,
    _make_ledger_rows,
    _make_stats,
)

_PID = uuid.uuid4()
_WP = uuid.uuid4()


class _FakeUser:
    id = uuid.uuid4()
    username = "审计助理"
    role = UserRole.auditor


@pytest.fixture(autouse=True)
def _bypass_extract_auth():
    with patch(
        "app.routers.voucher_sampling._authorize_and_validate_extract",
        new=AsyncMock(return_value=None),
    ):
        yield



def _make_app():
    app = FastAPI()
    app.include_router(router)
    mock_db = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return app, mock_db


def _mock_reconcile_facts(available=True, **kwargs):
    """构造 mock 的 PopulationReconcileFacts 用于端点 patch。"""
    defaults = dict(
        available=available,
        basis="tb_balance_movement" if available else None,
        ledger_debit=Decimal("1000000") if available else None,
        ledger_credit=Decimal("900000") if available else None,
        book_debit=Decimal("1000000") if available else None,
        book_credit=Decimal("900000") if available else None,
        unavailable_reason=None if available else "测试不可用原因",
    )
    defaults.update(kwargs)
    return PopulationReconcileFacts(**defaults)


async def _extract(app, account_codes=None):
    """发一次 voucher-extract 请求。"""
    population = _make_ledger_rows(30)
    with patch(
        "app.routers.voucher_sampling.LedgerSamplingService"
    ) as MockService, patch(
        "app.routers.voucher_sampling.collect_exclusions",
        new=_legacy_exclusions(extracted=[], preliminary=[]),
    ) as mock_excl:
        MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
        MockService.execute_with_stats = AsyncMock(
            return_value=(population, _make_stats(population))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PID}/sampling/voucher-extract",
                json=_make_extract_request(
                    method="random",
                    account_codes=account_codes or ["1122"],
                ),
            )
    return resp


class TestReconcileResponseContract:
    """端点契约：新核对字段存在且类型正确。"""

    @pytest.mark.asyncio
    async def test_asset_account_now_available(self):
        """资产类科目（1122）不再恒返 false —— 有余额表行即 available=true。"""
        app, _ = _make_app()
        facts = _mock_reconcile_facts(available=True)

        with patch(
            "app.routers.voucher_sampling.resolve_population_reconcile",
            new=AsyncMock(return_value=facts),
        ):
            resp = await _extract(app, account_codes=["1122"])

        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["reconcile_available"] is True
        assert stats["reconcile_basis"] == "tb_balance_movement"
        assert stats["book_amount"] is not None

    @pytest.mark.asyncio
    async def test_new_direction_fields_present(self):
        """新逐方向字段在 stats 中存在且为字符串或 null。"""
        app, _ = _make_app()
        facts = _mock_reconcile_facts(available=True)

        with patch(
            "app.routers.voucher_sampling.resolve_population_reconcile",
            new=AsyncMock(return_value=facts),
        ):
            resp = await _extract(app)

        stats = resp.json()["stats"]
        for key in (
            "reconcile_ledger_debit",
            "reconcile_ledger_credit",
            "reconcile_book_debit",
            "reconcile_book_credit",
            "reconcile_unavailable_reason",
        ):
            assert key in stats, f"缺失字段 {key}"

        # 数值字段为字符串（JSON 序列化口径）
        assert isinstance(stats["reconcile_ledger_debit"], str)
        assert isinstance(stats["reconcile_book_credit"], str)

    @pytest.mark.asyncio
    async def test_unavailable_returns_reason(self):
        """不可用时 unavailable_reason 非空、book_amount 为 null。"""
        app, _ = _make_app()
        facts = _mock_reconcile_facts(available=False, unavailable_reason="余额表无行")

        with patch(
            "app.routers.voucher_sampling.resolve_population_reconcile",
            new=AsyncMock(return_value=facts),
        ):
            resp = await _extract(app)

        stats = resp.json()["stats"]
        assert stats["reconcile_available"] is False
        assert stats["book_amount"] is None
        assert stats["reconcile_unavailable_reason"] == "余额表无行"

    @pytest.mark.asyncio
    async def test_book_amount_backward_compatible(self):
        """book_amount = |借| + |贷|（向后兼容旧前端单值核对）。"""
        app, _ = _make_app()
        facts = _mock_reconcile_facts(
            available=True,
            book_debit=Decimal("600"),
            book_credit=Decimal("400"),
        )

        with patch(
            "app.routers.voucher_sampling.resolve_population_reconcile",
            new=AsyncMock(return_value=facts),
        ):
            resp = await _extract(app)

        stats = resp.json()["stats"]
        assert stats["book_amount"] == "1000"  # |600| + |400|

    @pytest.mark.asyncio
    async def test_not_self_compare(self):
        """book_amount 不等于 population_amount（不以序时账总体自身比对）。"""
        app, _ = _make_app()
        facts = _mock_reconcile_facts(
            available=True,
            book_debit=Decimal("888888"),
            book_credit=Decimal("0"),
        )

        with patch(
            "app.routers.voucher_sampling.resolve_population_reconcile",
            new=AsyncMock(return_value=facts),
        ):
            resp = await _extract(app)

        stats = resp.json()["stats"]
        assert stats["book_amount"] != stats["population_amount"]
