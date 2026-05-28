"""Sprint A.5.1/A.5.2/A.5.3 — conversion_service v2 单测.

覆盖：
- preview_conversion_v2 返回完整字段
- convert_disclosure_notes_v2 共有章节保留
- convert_disclosure_notes_v2 manual cells 保留
- convert_disclosure_notes_v2 SOE 独有归档
- convert_disclosure_notes_v2 Listed 独有创建空 section
- convert_disclosure_notes_v2 format_diff 调 adapt_table_data
- convert_disclosure_notes_v2 更新 project.template_type
- 同类型切换 → 空操作
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_conversion_service import NoteConversionService


def _make_project(template_type="soe"):
    return SimpleNamespace(
        id=uuid4(),
        template_type=template_type,
        is_deleted=False,
    )


def _make_note(section_id, table_data=None, template_lineage=None):
    return SimpleNamespace(
        id=uuid4(),
        section_id=section_id,
        note_section=section_id,
        section_title=section_id,
        table_data=table_data or {"rows": []},
        template_lineage=template_lineage,
        is_deleted=False,
        is_empty=False,
    )


MOCK_DIFF = {
    "version": "test",
    "is_mock": True,
    "common_sections": [
        {"section_id": "common_1", "soe_section_id": "common_1", "listed_section_id": "common_1"},
        {"section_id": "common_2", "soe_section_id": "common_2", "listed_section_id": "common_2"},
    ],
    "soe_only_sections": [
        {"section_id": "soe_only_1", "title": "国资委特别披露"},
    ],
    "listed_only_sections": [
        {"section_id": "listed_only_1", "title": "库存股"},
    ],
    "format_diff_sections": [
        {
            "section_id": "fmt_diff_1",
            "soe_format": {"layout": "movement"},
            "listed_format": {"layout": "category_sum"},
            "field_mapping": {"col_a": "col_b"},
        },
    ],
}


def _make_db(project, notes=None):
    db = MagicMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    notes = notes or []
    call_count = {"n": 0}

    async def _exec(query):
        call_count["n"] += 1
        res = MagicMock()
        sc = MagicMock()
        if call_count["n"] == 1:
            # _get_project
            sc.one_or_none = MagicMock(return_value=project)
            res.scalar_one_or_none = MagicMock(return_value=project)
        else:
            # disclosure_notes query
            sc.all = MagicMock(return_value=notes)
        res.scalars = MagicMock(return_value=sc)
        return res

    db.execute = AsyncMock(side_effect=_exec)
    return db


# ===========================================================================
# preview_conversion_v2
# ===========================================================================


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_preview_v2_returns_all_fields(mock_sa):
    project = _make_project("soe")
    notes = [_make_note("common_1", {"rows": [{"_cell_modes": {"0": "manual"}}]})]
    db = _make_db(project, notes)
    svc = NoteConversionService(db)

    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        result = await svc.preview_conversion_v2(project.id, 2025, "listed")

    assert result["current_type"] == "soe"
    assert result["target_type"] == "listed"
    assert len(result["common_sections"]) == 2
    assert len(result["to_archive_sections"]) == 1  # soe_only
    assert len(result["to_create_sections"]) == 1   # listed_only
    assert result["user_edits_preserved"] == 1
    assert "mock" in result["warnings"][0]


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_preview_v2_same_type_noop(mock_sa):
    project = _make_project("listed")
    db = _make_db(project)
    svc = NoteConversionService(db)

    result = await svc.preview_conversion_v2(project.id, 2025, "listed")

    assert result["common_sections"] == []
    assert "无需切换" in result["warnings"][0]


# ===========================================================================
# convert_disclosure_notes_v2
# ===========================================================================


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_common_sections_preserved(mock_sa):
    project = _make_project("soe")
    notes = [
        _make_note("common_1", {"rows": [{"label": "A", "values": [100], "_cell_modes": {"0": "manual"}}]}),
        _make_note("common_2", {"rows": [{"label": "B", "values": [200], "_cell_modes": {}}]}),
    ]
    db = _make_db(project, notes)
    svc = NoteConversionService(db)

    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        with patch("app.services.note_template_diff.adapt_table_data", side_effect=lambda td, *a: td):
            result = await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert result["common_count"] == 2
    assert result["user_edits_preserved"] == 1
    # notes 未被 is_deleted
    assert all(not n.is_deleted for n in notes)


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_soe_only_archived(mock_sa):
    project = _make_project("soe")
    soe_note = _make_note("soe_only_1", {"rows": []})
    db = _make_db(project, [soe_note])
    svc = NoteConversionService(db)

    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        with patch("app.services.note_template_diff.adapt_table_data", side_effect=lambda td, *a: td):
            result = await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert result["archived_count"] == 1
    assert soe_note.is_deleted is True
    assert "archived_sections" in (soe_note.template_lineage or {})


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_listed_only_created(mock_sa):
    project = _make_project("soe")
    db = _make_db(project, [])
    svc = NoteConversionService(db)

    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        with patch("app.services.note_template_diff.adapt_table_data", side_effect=lambda td, *a: td):
            result = await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert result["created_count"] == 1
    assert db.add.call_count >= 1


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_format_diff_adapted(mock_sa):
    project = _make_project("soe")
    fmt_note = _make_note("fmt_diff_1", {"rows": [{"label": "X", "values": [1]}]})
    db = _make_db(project, [fmt_note])
    svc = NoteConversionService(db)

    adapted_td = {"rows": [{"label": "X", "values": [1]}], "_adapted": True}
    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        with patch("app.services.note_template_diff.adapt_table_data", return_value=adapted_td):
            result = await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert result["format_adapted_count"] == 1
    assert fmt_note.table_data.get("_adapted") is True


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_updates_template_type(mock_sa):
    project = _make_project("soe")
    db = _make_db(project, [])
    svc = NoteConversionService(db)

    with patch("app.services.note_template_diff.load_diff_data", return_value=MOCK_DIFF):
        with patch("app.services.note_template_diff.adapt_table_data", side_effect=lambda td, *a: td):
            await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert project.template_type == "listed"


@pytest.mark.asyncio
@patch("app.services.note_conversion_service.sa")
async def test_convert_v2_same_type_noop(mock_sa):
    project = _make_project("listed")
    db = _make_db(project, [])
    svc = NoteConversionService(db)

    result = await svc.convert_disclosure_notes_v2(project.id, 2025, "listed")

    assert result == {
        "common_count": 0, "archived_count": 0, "created_count": 0,
        "format_adapted_count": 0, "user_edits_preserved": 0, "errors": [],
    }


@pytest.mark.asyncio
async def test_convert_v2_invalid_target_raises():
    db = MagicMock()
    svc = NoteConversionService(db)
    with pytest.raises(ValueError, match="target_type"):
        await svc.convert_disclosure_notes_v2(uuid4(), 2025, "invalid")


@pytest.mark.asyncio
async def test_preview_v2_invalid_target_raises():
    db = MagicMock()
    svc = NoteConversionService(db)
    with pytest.raises(ValueError, match="target_type"):
        await svc.preview_conversion_v2(uuid4(), 2025, "bad")
