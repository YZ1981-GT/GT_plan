"""H1 四表取数 — 零回归基线（characterization）.

锁定灰度 `H1_FOUR_TABLE_EXTRACTION_ENABLED` 关闭时 render() 的输出契约：
键集合不含 `h1_four_table_prefill`，且既有 `adjudication_category_prefill` /
`tb_values` / `responses_snapshot` / `sheets` 结构不变。
"""
from __future__ import annotations

import types

import pytest

from app.core.config import settings
from app.routers.wp_render_strategies import _h1_fixed_assets as h1

_BASELINE_KEYS = {
    "component_type",
    "account_codes",
    "responses_snapshot",
    "tb_values",
    "adjudication_category_prefill",
    "project_context",
    "tb_source_codes",
    "prefix",
    "sheets",
}


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeDb:
    """所有查询返回空结果（render 各段 fail-open 后仍应产出完整键集合）。"""

    async def execute(self, *_args, **_kwargs):
        return _FakeResult()


def _ctx():
    return types.SimpleNamespace(
        db=_FakeDb(), project_id="p1", year=2025, wp_id="wp1", classification=None,
    )


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False)


@pytest.mark.asyncio
async def test_render_keys_unchanged_when_flag_off(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(h1, "get_active_filter", _fake_filter)
    out = await h1.render(_ctx())
    assert out is not None
    assert set(out.keys()) == _BASELINE_KEYS
    assert "h1_four_table_prefill" not in out


@pytest.mark.asyncio
async def test_existing_category_prefill_structure_unchanged(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(h1, "get_active_filter", _fake_filter)
    out = await h1.render(_ctx())
    prefill = out["adjudication_category_prefill"]
    assert set(prefill.keys()) == {"categories", "totals"}
    assert [c["category"] for c in prefill["categories"]] == list(h1._H1_FA_CATEGORIES)
    for c in prefill["categories"]:
        assert set(c.keys()) == {"category", "cost", "dep", "impair", "needs_review"}
        assert set(c["cost"].keys()) == {"begin", "debit", "credit", "end", "unadjusted"}
    assert set(prefill["totals"].keys()) == {"cost1601", "dep1602", "impair1603"}


@pytest.mark.asyncio
async def test_sheets_and_prefix_stable(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(h1, "get_active_filter", _fake_filter)
    out = await h1.render(_ctx())
    assert out["component_type"] == "h1-fixed-assets"
    assert out["prefix"] == "H1"
    assert out["account_codes"] == ["1601", "1602", "1603"]
    assert out["sheets"] == h1.H1_SHEETS
    assert len(h1.H1_SHEETS) == 24


def test_flag_defaults_to_false():
    from app.core.config import Settings

    assert Settings().H1_FOUR_TABLE_EXTRACTION_ENABLED is False
