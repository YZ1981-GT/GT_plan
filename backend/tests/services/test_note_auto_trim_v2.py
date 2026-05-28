"""单测 — NoteTrimService.auto_trim_v2 三级裁剪（Sprint A.3.3）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.3.3
Design:  D5 三级 trim — 章节 + 段落 + 表格（CI-8 互斥）
Reqs:    auto_trim_v2 三级裁剪
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import note_template_bindings_loader as loader
from app.services.note_trim_service import NoteTrimService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _binding_for(account_codes: list[str]) -> dict[str, Any]:
    return {
        "tables": [{
            "table_index": 0,
            "rows": {
                "data_row": {
                    "row_type": "data",
                    "binding": {
                        "closing_balance": {
                            "source": "trial_balance",
                            "field": "audited_amount",
                            "account_codes": list(account_codes),
                            "mode": "auto",
                        },
                    },
                },
            },
        }],
    }


def _make_note(*, snum: str, text: str = "", table: dict | None = None):
    return SimpleNamespace(
        id=uuid4(),
        note_section=snum,
        section_title=snum,
        text_content=text,
        table_data=table if table is not None else {"rows": []},
        is_deleted=False,
        template_lineage=None,
    )


def _empty_table() -> dict:
    return {"headers": ["项目", "期末", "期初"], "rows": [
        {"row_type": "data", "label": "p1", "values": [None, 0, 0]},
        {"row_type": "data", "label": "p2", "values": [None, None, None]},
    ]}


def _nonempty_table() -> dict:
    return {"headers": ["项目", "期末", "期初"], "rows": [
        {"row_type": "data", "label": "p1", "values": [None, 100.0, 80.0]},
    ]}


def _section(snum: str = "S1") -> dict:
    return {"id": str(uuid4()), "section_number": snum, "section_title": snum,
            "status": "retain", "skip_reason": None, "sort_order": 0}


def _make_service(
    *, sections: list[dict],
    notes: list | None = None,
    tb_zero: set[str] | None = None,
):
    db = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    notes = notes or []

    async def _exec(_q):
        res = MagicMock()
        sc = MagicMock()
        sc.all = MagicMock(return_value=notes)
        res.scalars = MagicMock(return_value=sc)
        res.all = MagicMock(return_value=[])
        return res
    db.execute = AsyncMock(side_effect=_exec)

    svc = NoteTrimService(db)

    async def _resolve(_p, _t):
        return "soe"
    svc.resolve_template_type = _resolve  # type: ignore[assignment]

    async def _get_sections(_p, _t):
        return sections
    svc.get_sections = _get_sections  # type: ignore[assignment]

    async def _save_trim(_p, _t, _items):
        return len(_items)
    svc.save_trim = _save_trim  # type: ignore[assignment]

    tb_zero = tb_zero or set()

    async def _is_all_zero(_p, _y, codes):
        return all(c in tb_zero for c in codes)
    svc._is_all_zero_for_codes = _is_all_zero  # type: ignore[assignment]

    return svc


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    loader.reload()
    yield
    loader.reload()


def _patch_loader(monkeypatch, mapping):
    def _fake(snum):
        return mapping.get(snum)
    monkeypatch.setattr(
        "app.services.note_trim_service.get_binding_for_section", _fake, raising=False,
    )


# ===========================================================================
# Level 1: 章节级
# ===========================================================================


@pytest.mark.asyncio
async def test_level1_section_skip_when_tb_all_zero(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1604"])})
    svc = _make_service(sections=sections, tb_zero={"1604"})
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_skipped"] == 1
    assert r["section_deleted"] == 0
    assert r["table_replaced"] == 0
    assert r["retained"] == 0


@pytest.mark.asyncio
async def test_level1_section_retained_when_tb_nonzero(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1122"])})
    note = _make_note(snum="S1", text="x", table=_nonempty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r == {"section_skipped": 0, "section_deleted": 0,
                 "table_replaced": 0, "retained": 1, "errors": []}
    assert note.is_deleted is False


# ===========================================================================
# Level 2: 段落级
# ===========================================================================


@pytest.mark.asyncio
async def test_level2_section_deleted_when_note_empty(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})  # 无 level 1
    note = _make_note(snum="S1", text="", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_deleted"] == 1
    assert r["table_replaced"] == 0
    assert note.is_deleted is True
    assert note.template_lineage["deletion_reason"] == "auto_trim_v2_empty"
    assert "deletion_at" in note.template_lineage


@pytest.mark.asyncio
async def test_level2_skipped_when_text_nonempty(monkeypatch):
    """text 非空 → 不走段落级；表空走表格级."""
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="本年无相关业务发生", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_deleted"] == 0
    assert r["table_replaced"] == 1
    assert note.is_deleted is False
    assert note.table_data["_render_as"] == "no_business_paragraph"


# ===========================================================================
# Level 3: 表格级
# ===========================================================================


@pytest.mark.asyncio
async def test_level3_table_marked_no_business(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="说明", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["table_replaced"] == 1
    assert note.table_data["_render_as"] == "no_business_paragraph"


@pytest.mark.asyncio
async def test_level3_skips_when_table_nonempty(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="说明", table=_nonempty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["table_replaced"] == 0
    assert "_render_as" not in note.table_data


@pytest.mark.asyncio
async def test_level3_multi_tables_partial(monkeypatch):
    """多表场景：仅空表被标，非空表保留."""
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    multi = {"_tables": [_empty_table(), _nonempty_table()]}
    note = _make_note(snum="S1", text="说明", table=multi)
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["table_replaced"] == 1
    assert note.table_data["_tables"][0].get("_render_as") == "no_business_paragraph"
    assert "_render_as" not in note.table_data["_tables"][1]


# ===========================================================================
# CI-8 互斥
# ===========================================================================


@pytest.mark.asyncio
async def test_mutex_section_over_paragraph_and_table(monkeypatch):
    """章节级触发后，段落 + 表格级不再扫该章节."""
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1604"])})
    note = _make_note(snum="S1", text="", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note], tb_zero={"1604"})
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_skipped"] == 1
    assert r["section_deleted"] == 0
    assert r["table_replaced"] == 0
    assert note.is_deleted is False
    assert "_render_as" not in note.table_data


@pytest.mark.asyncio
async def test_mutex_paragraph_over_table(monkeypatch):
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_deleted"] == 1
    assert r["table_replaced"] == 0
    assert "_render_as" not in note.table_data


# ===========================================================================
# 混合 / 空 / 幂等
# ===========================================================================


@pytest.mark.asyncio
async def test_mixed_three_sections(monkeypatch):
    """3 章节：S1 章节级 / S2 段落级 / S3 表格级."""
    sections = [_section("S1"), _section("S2"), _section("S3")]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1604"])})
    n1 = _make_note(snum="S1", text="x", table=_nonempty_table())
    n2 = _make_note(snum="S2", text="", table=_empty_table())
    n3 = _make_note(snum="S3", text="说明", table=_empty_table())
    svc = _make_service(
        sections=sections, tb_zero={"1604"}, notes=[n1, n2, n3],
    )
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r["section_skipped"] == 1
    assert r["section_deleted"] == 1
    assert r["table_replaced"] == 1
    assert r["retained"] == 1
    assert n1.is_deleted is False
    assert n2.is_deleted is True
    assert n3.table_data["_render_as"] == "no_business_paragraph"


@pytest.mark.asyncio
async def test_no_sections_returns_empty_counts(monkeypatch):
    _patch_loader(monkeypatch, {})
    svc = _make_service(sections=[])
    r = await svc.auto_trim_v2(uuid4(), 2025)
    assert r == {"section_skipped": 0, "section_deleted": 0,
                 "table_replaced": 0, "retained": 0, "errors": []}


@pytest.mark.asyncio
async def test_idempotent_second_run(monkeypatch):
    """重跑：数字稳定（同一个 note 重复标 _render_as 也只计 1 次/run）."""
    sections = [_section("S1")]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="说明", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])
    r1 = await svc.auto_trim_v2(uuid4(), 2025)
    r2 = await svc.auto_trim_v2(uuid4(), 2025)
    assert r1["table_replaced"] == r2["table_replaced"] == 1
    assert note.table_data["_render_as"] == "no_business_paragraph"
