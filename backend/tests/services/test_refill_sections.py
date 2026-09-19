"""单测 — DisclosureEngine.refill_sections 窄接口

Feature: disclosure-note-linkage-and-slimdown
Validates: Requirements 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 1.3

覆盖：
- 含表格的章节被重算，auto 单元格新值写回
- 纯文本章节计入 text_only_sections
- manual 单元格被跳过
- cells_updated 仅计变化单元格
- 取数失败章节记入 errors，不抛异常
- 只 flush 不 commit
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.services.disclosure_engine import (
    CellRefillRecord,
    DisclosureEngine,
    RefillReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()
YEAR = 2025


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _make_note(
    section: str,
    content_type: ContentType = ContentType.table,
    table_data: dict | None = None,
) -> MagicMock:
    """Create a mock DisclosureNote."""
    note = MagicMock(spec=DisclosureNote)
    note.note_section = section
    note.content_type = content_type
    note.table_data = table_data
    note.is_stale = True
    return note


@pytest.fixture(autouse=True)
def _patch_flag_modified():
    """flag_modified needs a real ORM instance; mock it for unit tests."""
    with patch("sqlalchemy.orm.attributes.flag_modified"):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refill_text_only_section():
    """纯文本章节（content_type=text）计入 text_only_sections，不尝试重算。"""
    eng = _make_engine()
    note = _make_note("五、1", content_type=ContentType.text, table_data=None)

    # Mock DB query returns this note
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    with patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、1"])

    assert "五、1" in report.text_only_sections
    assert report.cells_updated == 0
    assert report.sections_recomputed == []


@pytest.mark.asyncio
async def test_refill_no_rows_section():
    """table_data 无 rows 的章节视为纯文本。"""
    eng = _make_engine()
    note = _make_note("五、2", content_type=ContentType.table, table_data={"headers": ["项目"]})

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    with patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、2"])

    assert "五、2" in report.text_only_sections
    assert report.cells_updated == 0


@pytest.mark.asyncio
async def test_refill_auto_cell_updated():
    """auto 单元格值变化时被更新，cells_updated 计数正确。"""
    eng = _make_engine()
    table_data = {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {
                "label": "银行存款",
                "values": [100.0, 200.0],
                "_cell_modes": {"0": "auto", "1": "auto"},
                "_cell_meta": {
                    "0": {"semantic": "closing_balance", "binding_id": "五、3.银行存款.closing_balance"},
                    "1": {"semantic": "opening_balance", "binding_id": "五、3.银行存款.opening_balance"},
                },
            },
        ],
    }
    note = _make_note("五、3", content_type=ContentType.table, table_data=table_data)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    # Mock binding loader to return the binding
    binding = {
        "tables": [{
            "header_normalize": [
                {"semantic": "row_label"},
                {"semantic": "closing_balance"},
                {"semantic": "opening_balance"},
            ],
            "rows": {
                "银行存款": {
                    "binding": {
                        "closing_balance": {"source": "trial_balance", "account_codes": ["1001"], "field": "audited"},
                        "opening_balance": {"source": "trial_balance", "account_codes": ["1001"], "field": "opening"},
                    }
                }
            },
        }]
    }

    async def mock_dispatch(cell_binding, ctx):
        if cell_binding.get("field") == "audited":
            return 999.0  # new value different from old 100.0
        if cell_binding.get("field") == "opening":
            return 200.0  # same as old, no change
        return None

    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ),
    ):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、3"])

    assert report.cells_updated == 1
    assert report.sections_recomputed == ["五、3"]
    assert len(report.records) == 1
    assert report.records[0].old_value == 100.0
    assert report.records[0].new_value == 999.0
    # Verify value was actually written back
    assert table_data["rows"][0]["values"][0] == 999.0
    assert table_data["rows"][0]["values"][1] == 200.0  # unchanged


@pytest.mark.asyncio
async def test_refill_manual_cell_skipped():
    """skip_manual=True 时 manual 单元格不被修改。"""
    eng = _make_engine()
    table_data = {
        "headers": ["项目", "期末余额"],
        "rows": [
            {
                "label": "现金",
                "values": [50.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            },
        ],
    }
    note = _make_note("五、4", content_type=ContentType.mixed, table_data=table_data)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    with patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、4"])

    assert report.cells_updated == 0
    assert table_data["rows"][0]["values"][0] == 50.0  # preserved


@pytest.mark.asyncio
async def test_refill_error_section_recorded():
    """取数失败的章节记入 errors，不抛异常。"""
    eng = _make_engine()
    table_data = {
        "headers": ["项目", "期末余额"],
        "rows": [
            {
                "label": "坏账",
                "values": [10.0],
                "_cell_modes": {"0": "auto"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            },
        ],
    }
    note = _make_note("五、5", content_type=ContentType.table, table_data=table_data)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    binding = {
        "tables": [{
            "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}],
            "rows": {
                "坏账": {
                    "binding": {
                        "closing_balance": {"source": "trial_balance", "account_codes": ["1231"]},
                    }
                }
            },
        }]
    }

    async def mock_dispatch_raise(cell_binding, ctx):
        raise RuntimeError("DB connection lost")

    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch_raise,
        ),
    ):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、5"])

    # Should not raise
    assert len(report.errors) == 1
    assert "五、5" in report.errors[0]
    assert "五、5" not in report.sections_recomputed


@pytest.mark.asyncio
async def test_refill_only_flush_not_commit():
    """验证 refill_sections 只调用 flush，从不调用 commit。"""
    eng = _make_engine()
    table_data = {
        "headers": ["项目", "金额"],
        "rows": [
            {
                "label": "A",
                "values": [1.0],
                "_cell_modes": {"0": "auto"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            },
        ],
    }
    note = _make_note("五、6", content_type=ContentType.table, table_data=table_data)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    binding = {
        "tables": [{
            "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}],
            "rows": {"A": {"binding": {"closing_balance": {"source": "trial_balance"}}}},
        }]
    }

    async def mock_dispatch(cell_binding, ctx):
        return 2.0

    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ),
    ):
        await eng.refill_sections(PROJECT_ID, YEAR, ["五、6"])

    eng.db.flush.assert_called_once()
    eng.db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_refill_no_change_no_update():
    """当新值等于旧值时，cells_updated 不增加。"""
    eng = _make_engine()
    table_data = {
        "headers": ["项目", "金额"],
        "rows": [
            {
                "label": "B",
                "values": [100.0],
                "_cell_modes": {"0": "auto"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            },
        ],
    }
    note = _make_note("五、7", content_type=ContentType.table, table_data=table_data)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    binding = {
        "tables": [{
            "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}],
            "rows": {"B": {"binding": {"closing_balance": {"source": "trial_balance"}}}},
        }]
    }

    async def mock_dispatch(cell_binding, ctx):
        return 100.0  # same as old

    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ),
    ):
        report = await eng.refill_sections(PROJECT_ID, YEAR, ["五、7"])

    assert report.cells_updated == 0
    assert report.sections_recomputed == []


@pytest.mark.asyncio
async def test_refill_mixed_sections():
    """多个章节混合：text → text_only, table → recomputed, error → errors。"""
    eng = _make_engine()

    text_note = _make_note("一、1", content_type=ContentType.text)
    table_note = _make_note("五、1", content_type=ContentType.table, table_data={
        "headers": ["项目", "金额"],
        "rows": [
            {
                "label": "X",
                "values": [0.0],
                "_cell_modes": {"0": "auto"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            },
        ],
    })

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [text_note, table_note]
    eng.db.execute = AsyncMock(return_value=mock_result)

    binding = {
        "tables": [{
            "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}],
            "rows": {"X": {"binding": {"closing_balance": {"source": "trial_balance"}}}},
        }]
    }

    async def mock_dispatch(cell_binding, ctx):
        return 42.0

    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ),
    ):
        report = await eng.refill_sections(PROJECT_ID, YEAR)

    assert "一、1" in report.text_only_sections
    assert "五、1" in report.sections_recomputed
    assert report.cells_updated == 1
