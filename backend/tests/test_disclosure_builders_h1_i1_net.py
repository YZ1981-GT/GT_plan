"""H1 / I1 附注 builder：审定净值读不到不写 0、期初不编造。spec formula-fetch-followup-defect-closure R6.3。

两个 builder 读公式推送写的 ``{H1,I1}-1-audited-net``。原先推送恒写 ``'0'``（读错键），builder 再把 0 写进附注主表；
推送改按审定表行清单算净值后，行清单没存时写空 —— builder 必须把空当「没有」而不是 0。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

PID = UUID("aaaaaaaa-0000-0000-0000-000000000002")
YEAR = 2025


async def _build(module: str, cls: str, entries: dict):
    mod = __import__(f"app.services.disclosure_builders.{module}", fromlist=[cls])
    base = f"app.services.disclosure_builders.{module}"
    with patch(f"{base}.load_disclosure_entries", new=AsyncMock(return_value=entries)), \
         patch(f"{base}.load_project_template_type", new=AsyncMock(return_value="soe")), \
         patch(f"{base}.load_project_standard", new=AsyncMock(return_value="soe_standalone")):
        return await getattr(mod, cls)().build(AsyncMock(), PID, YEAR)


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "cls", "key"), [
    ("h1_builder", "H1Builder", "H1-1-audited-net"),
    ("i1_builder", "I1Builder", "I1-1-audited-net"),
])
@pytest.mark.parametrize("raw", ["", "   ", None, "abc"])
async def test_blank_or_bad_net_builds_nothing(module, cls, key, raw):
    entries = {"其他键": "1"} if raw is None else {key: raw, "其他键": "1"}
    assert await _build(module, cls, entries) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "cls", "key", "table", "label"), [
    ("h1_builder", "H1Builder", "H1-1-audited-net", "固定资产", "固定资产"),
    ("i1_builder", "I1Builder", "I1-1-audited-net", "无形资产", "无形资产"),
])
async def test_net_present_writes_end_and_leaves_opening_blank(module, cls, key, table, label):
    result = await _build(module, cls, {key: "18823146.01"})
    rows = result.sub_table_data[table]
    assert rows[0] == {"label": label, "end_amount": 18823146.01, "prior_amount": None}
    assert rows[1]["is_total"] is True and rows[1]["end_amount"] == 18823146.01 and rows[1]["prior_amount"] is None
    # 真为 0 的净值照常写 0
    zero = await _build(module, cls, {key: "0"})
    assert zero.sub_table_data[table][0]["end_amount"] == 0.0
