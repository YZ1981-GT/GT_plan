"""总体完整性独立数据源测试（voucher-sampling-hardening Task 4.3）

Property 5：不以序时账总体自身比对——无独立账面时 reconcile_available=false 且
book_amount=null，绝不等于抽样总体金额（population_amount）。

Validates: Requirements 2.1, 2.2, 2.5
Properties: Property 5
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers.voucher_sampling import (
    _resolve_independent_book_amount,
    router,
)

from tests.test_voucher_sampling_integration import (
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


@pytest.fixture(autouse=True)
def _bridge_exclusions_to_legacy(monkeypatch):
    """P3：新 `_get_voucher_sampling_exclusions`（ledger_line 行级排除入口）委托到各测试
    已 mock 的 legacy 收集器，使端点级 reconcile 测试的 voucher-extract 调用不触达未 mock
    的 db。行级拆分本身由 test_voucher_sampling_row_exclusion.py 独立覆盖。"""
    import app.routers.voucher_sampling as _vs

    async def _delegate(db, wp, preliminary_only=False):
        if preliminary_only:
            nos = await _vs._get_preliminary_voucher_nos(db, wp)
        else:
            nos = await _vs._get_voucher_sampling_extracted_nos(db, wp)
        return list(nos), []

    monkeypatch.setattr(_vs, "_get_voucher_sampling_exclusions", _delegate)


class TestResolveIndependentBookAmount:
    @pytest.mark.asyncio
    async def test_empty_account_codes_returns_none(self):
        # 无科目 → 无法解析独立账面 → (None, None)，不自身比对
        got = await _resolve_independent_book_amount(AsyncMock(), _PID, 2025, [])
        assert got == (None, None)

    @pytest.mark.asyncio
    async def test_db_failure_degrades_gracefully(self):
        # 独立源取数异常 → (None, None) 不抛（Req2.5）
        # 用损益类 6601（通过口径守卫到达 DB 路径）验证 DB 失败降级
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        got = await _resolve_independent_book_amount(db, _PID, 2025, ["6601"])
        assert got == (None, None)


class TestReconcileScopeGuard:
    """P1 口径守卫：发生额总体只对损益/成本类(5/6)核对，资产/负债/权益类不核对。"""

    @pytest.mark.asyncio
    async def test_asset_account_no_reconcile(self):
        # 资产类 1122：审定=期末余额，与发生额总体口径不符 → (None,None)，且不查 DB
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=AssertionError("不应查询 DB"))
        got = await _resolve_independent_book_amount(db, _PID, 2025, ["1122"])
        assert got == (None, None)

    @pytest.mark.asyncio
    async def test_liability_account_no_reconcile(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=AssertionError("不应查询 DB"))
        got = await _resolve_independent_book_amount(db, _PID, 2025, ["2202"])
        assert got == (None, None)

    @pytest.mark.asyncio
    async def test_mixed_scope_no_reconcile(self):
        # 含资产类 → 整体口径不符 → (None,None)
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=AssertionError("不应查询 DB"))
        got = await _resolve_independent_book_amount(db, _PID, 2025, ["6601", "1122"])
        assert got == (None, None)

    @pytest.mark.asyncio
    async def test_pl_account_reconciles_occurrence(self):
        # 损益类 6601：审定=发生额，可核对 → 返回汇总值 + occurrence basis
        from decimal import Decimal

        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: (Decimal("123456.00"), 3)[i]
        result = MagicMock()
        result.one = MagicMock(return_value=row)
        db.execute = AsyncMock(return_value=result)
        amount, basis = await _resolve_independent_book_amount(db, _PID, 2025, ["6601"])
        assert amount == Decimal("123456.00")
        assert basis == "trial_balance_audited_occurrence"

    @pytest.mark.asyncio
    async def test_cost_account_5_reconciles(self):
        # 成本类 5001（发生额口径）同样可核对
        from decimal import Decimal

        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: (Decimal("999.00"), 1)[i]
        result = MagicMock()
        result.one = MagicMock(return_value=row)
        db.execute = AsyncMock(return_value=result)
        _, basis = await _resolve_independent_book_amount(db, _PID, 2025, ["5001"])
        assert basis == "trial_balance_audited_occurrence"


class TestReconcileResponseContract:
    @pytest.mark.asyncio
    async def test_no_independent_source_not_self_compare(self):
        """无独立账面时 reconcile_available=false 且 book_amount!=population_amount。"""
        app = FastAPI()
        app.include_router(router)
        mock_db = AsyncMock()

        async def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        population = _make_ledger_rows(30)
        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._resolve_independent_book_amount",
            new=AsyncMock(return_value=(None, None)),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, _make_stats(population))
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PID}/sampling/voucher-extract",
                    json=_make_extract_request(method="random"),
                )
        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["reconcile_available"] is False
        assert stats["book_amount"] is None
        # 关键：book_amount 不等于 population_amount（消除自身比对）
        assert stats["book_amount"] != stats["population_amount"]

    @pytest.mark.asyncio
    async def test_independent_source_present(self):
        """有独立账面时 reconcile_available=true + book_amount 为独立来源值。"""
        app = FastAPI()
        app.include_router(router)
        mock_db = AsyncMock()

        async def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        population = _make_ledger_rows(30)
        from decimal import Decimal

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._resolve_independent_book_amount",
            new=AsyncMock(return_value=(Decimal("888888.00"), "trial_balance_audited")),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, _make_stats(population))
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PID}/sampling/voucher-extract",
                    json=_make_extract_request(method="random"),
                )
        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["reconcile_available"] is True
        assert stats["book_amount"] == "888888.00"
        assert stats["reconcile_basis"] == "trial_balance_audited"
