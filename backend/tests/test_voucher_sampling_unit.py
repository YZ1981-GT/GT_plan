"""抽样单位（ledger_line / voucher）测试（voucher-sampling-hardening Task 5.4）

Property 6/7：voucher 单位下按凭证号聚合抽样，抽中一张凭证带出其全部分录行；
样本行的凭证号均属于被选中的凭证集合（不跨凭证部分带出）。

Validates: Requirements 3.1, 3.2, 3.5
Properties: Property 6, Property 7
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
from app.services.ledger_sampling_service import StatsResult

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


def _multiline_population(n_vouchers: int, lines_per: int) -> list[dict]:
    """构造每张凭证多行的总体（借贷两行/凭证）。"""
    rows: list[dict] = []
    for v in range(n_vouchers):
        vno = f"记-2025-{v:04d}"
        for ln in range(lines_per):
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "voucher_date": f"2025-01-{(v % 28) + 1:02d}",
                    "voucher_no": vno,
                    "account_code": "1122" if ln == 0 else "6001",
                    "account_name": "行" + str(ln),
                    "voucher_type": "记",
                    "debit_amount": str(Decimal(1000 * (v + 1))) if ln == 0 else None,
                    "credit_amount": None if ln == 0 else str(Decimal(1000 * (v + 1))),
                    "counterpart_account": None,
                    "summary": f"凭证{v}行{ln}",
                    "entry_seq": ln + 1,
                    "accounting_period": 1,
                    "preparer": "张三",
                    "company_code": "001",
                    "currency_code": "CNY",
                }
            )
    return rows


def _stats(rows: list[dict]) -> StatsResult:
    def _n(v):
        return Decimal(str(v)) if v is not None else Decimal("0")

    return StatsResult(
        total_count=len(rows),
        debit_total=sum((_n(r["debit_amount"]) for r in rows), Decimal("0")),
        credit_total=sum((_n(r["credit_amount"]) for r in rows), Decimal("0")),
        amount_total=sum(
            (max(abs(_n(r["debit_amount"])), abs(_n(r["credit_amount"]))) for r in rows),
            Decimal("0"),
        ),
        by_voucher_type={},
        truncated=False,
    )


def _req(unit: str) -> dict:
    return {
        "sampling_method": "random",
        "sampling_params": {"sample_size": 3},
        "random_seed": 42,
        "phase": "preliminary",
        "filters": {
            "account_codes": ["1122"],
            "period_range": list(range(1, 13)),
            "sampling_unit": unit,
            "exclude_extracted": False,
        },
        "workpaper_id": str(_WP),
        "year": 2025,
    }


async def _call(unit: str, population: list[dict]) -> dict:
    app = FastAPI()
    app.include_router(router)
    mock_db = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()

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
            return_value=(population, _stats(population))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PID}/sampling/voucher-extract", json=_req(unit)
            )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSamplingUnit:
    @pytest.mark.asyncio
    async def test_voucher_unit_brings_full_entries(self):
        # 10 张凭证 × 2 行；voucher 单位抽 3 张 → 样本行数 = 3×2 = 6，且成对同凭证
        pop = _multiline_population(10, 2)
        data = await _call("voucher", pop)
        items = data["items"]
        vnos = {it["voucher_no"] for it in items}
        # 抽中的凭证数 = 3（sample_size），每张带出 2 行
        assert len(vnos) == 3
        assert len(items) == 6
        # 每张被选中的凭证其两行都在样本中（完整带出）
        from collections import Counter

        c = Counter(it["voucher_no"] for it in items)
        assert all(cnt == 2 for cnt in c.values())

    @pytest.mark.asyncio
    async def test_ledger_line_unit_samples_lines(self):
        # ledger_line 单位：按行抽样，sample_size=3 → 3 行（可能跨不同凭证的单行）
        pop = _multiline_population(10, 2)
        data = await _call("ledger_line", pop)
        assert data["stats"]["sample_count"] == 3
        assert data["stats"]["sampling_unit"] == "ledger_line"

    @pytest.mark.asyncio
    async def test_voucher_unit_stats_label(self):
        pop = _multiline_population(8, 2)
        data = await _call("voucher", pop)
        assert data["stats"]["sampling_unit"] == "voucher"
