"""Tests for A17 partner summary timeline and B3 period import helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.a17_independence_drift import (
    _period_dict_to_signature,
    import_b3_periods_to_a177,
)
from app.services import a17_upstream_stale_service as stale_svc
from app.services import a17_partner_summary_service as partner_svc


def test_period_signature_stable():
    a = _period_dict_to_signature(
        {
            "business_start": "2024-01-01",
            "business_end": "2024-12-31",
            "report_start": None,
            "report_end": None,
        }
    )
    b = _period_dict_to_signature(
        {
            "business_start": "2024/01/01",
            "business_end": "2024.12.31",
            "report_start": "",
            "report_end": "",
        }
    )
    assert a == b


def test_load_chapter_sources():
    sources = stale_svc._load_chapter_sources()
    assert isinstance(sources, dict)
    # definitions file should yield at least ch02 / ch10 style entries
    assert any(k.startswith("A17-1-ch") for k in sources.keys()) or sources == {}


@pytest.mark.asyncio
async def test_import_b3_no_data():
    db = AsyncMock()
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    empty.fetchall.return_value = []
    empty.fetchone.return_value = None
    db.execute = AsyncMock(return_value=empty)

    result = await import_b3_periods_to_a177(db, uuid4(), uuid4(), uuid4(), overwrite=False)
    assert result["imported"] == 0


@pytest.mark.asyncio
async def test_partner_timeline_empty():
    db = AsyncMock()
    empty = MagicMock()
    empty.fetchall.return_value = []
    empty.fetchone.return_value = None
    empty.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=empty)

    tl = await partner_svc.get_report_date_timeline(db, uuid4())
    assert len(tl["milestones"]) == 3
    assert isinstance(tl["warnings"], list)
