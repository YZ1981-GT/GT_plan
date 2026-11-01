"""合并附注根节点到 Word 章节的严格只读适配测试。"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.consol_note_export_adapter import (
    ConsolNoteExportError,
    adapt_root_consol_records,
    load_root_consol_export_notes,
)


def _index(code: str = "八、1", *, alias: str | None = "五、1") -> list[dict]:
    return [
        {
            "section_code": code,
            "section_title": "货币资金",
            "content_type": "mixed",
            "legacy_aliases": [alias] if alias else [],
        }
    ]


def _table(section_id: str, title: str = "货币资金") -> dict:
    return {
        "section_id": section_id,
        "parent_section": "货币资金",
        "parent_seq": 1,
        "title": title,
        "seq": 1,
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [["模板行", "", ""]],
        "_row_types": ["total"],
    }


def _record(section_id: str, rows=None, *, stale: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        section_id=section_id,
        data={
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": rows if rows is not None else [["银行存款", "100", "80"]],
        },
        is_stale=stale,
    )


def test_soe_tables_aggregate_to_word_section_without_mutating_templates(monkeypatch):
    templates = [_table("五-1-1", "货币资金"), _table("五-1-2", "受限制货币资金")]
    before = copy.deepcopy(templates)
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: {"standalone_note_section": "八、1"},
    )

    notes = adapt_root_consol_records(
        [_record("五-1-1"), _record("五-1-2", [["保证金", "20", "10"]])],
        project_id=uuid4(),
        year=2025,
        template_type="soe",
        index_sections=_index(),
        table_templates=templates,
    )

    assert templates == before
    assert [note.note_section for note in notes] == ["八、1"]
    tables = notes[0].table_data["_tables"]
    assert [table["name"] for table in tables] == ["货币资金", "受限制货币资金"]
    assert tables[0]["rows"] == [
        {"label": "银行存款", "values": ["100", "80"], "row_type": "total"}
    ]


def test_listed_structural_mapping_keeps_five_chapter(monkeypatch):
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: None,
    )
    [note] = adapt_root_consol_records(
        [_record("五-1-1")],
        project_id=uuid4(),
        year=2025,
        template_type="listed",
        index_sections=_index("五、1", alias=None),
        table_templates=[_table("五-1-1")],
    )
    assert note.note_section == "五、1"


@pytest.mark.parametrize(
    ("records", "templates", "expected_code"),
    [
        ([], [_table("五-1-1")], "CONSOL_NOTE_SECTION_DATA_MISSING"),
        ([_record("五-1-1", stale=True)], [_table("五-1-1")], "CONSOL_NOTE_DATA_STALE"),
        (
            [_record("五-1-1", [["列数错误", "1"]])],
            [_table("五-1-1")],
            "CONSOL_NOTE_ROW_INVALID",
        ),
        (
            [_record("未知-1-1")],
            [_table("五-1-1")],
            "CONSOL_NOTE_DATA_UNKNOWN_SECTION",
        ),
    ],
)
def test_invalid_or_incomplete_root_data_fails_closed(
    monkeypatch, records, templates, expected_code
):
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: {"standalone_note_section": "八、1"},
    )
    with pytest.raises(ConsolNoteExportError) as caught:
        adapt_root_consol_records(
            records,
            project_id=uuid4(),
            year=2025,
            template_type="soe",
            index_sections=_index(),
            table_templates=templates,
        )
    assert caught.value.code == expected_code


def test_explicit_selection_requires_mapped_table_data(monkeypatch):
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: {"standalone_note_section": "八、1"},
    )
    index = _index() + [
        {
            "section_code": "八、2",
            "section_title": "交易性金融资产",
            "content_type": "mixed",
            "legacy_aliases": ["五、2"],
        }
    ]
    with pytest.raises(ConsolNoteExportError) as caught:
        adapt_root_consol_records(
            [_record("五-1-1")],
            project_id=uuid4(),
            year=2025,
            template_type="soe",
            index_sections=index,
            table_templates=[_table("五-1-1")],
            selected_sections=["八、2"],
        )
    assert caught.value.code == "CONSOL_NOTE_SECTION_DATA_MISSING"


def test_full_export_rejects_template_table_without_word_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: None,
    )
    bad_table = _table("五-99-1", "不存在的表")
    bad_table["parent_section"] = "不存在的章节"
    with pytest.raises(ConsolNoteExportError) as caught:
        adapt_root_consol_records(
            [_record("五-99-1")],
            project_id=uuid4(),
            year=2025,
            template_type="soe",
            index_sections=_index(),
            table_templates=[bad_table],
        )
    assert caught.value.code == "CONSOL_NOTE_TEMPLATE_UNMAPPED"


@pytest.mark.asyncio
async def test_loader_uses_verified_root_scope_and_root_legacy_fallback(monkeypatch):
    project_id = uuid4()
    root = SimpleNamespace(node_key="ROOT:consol", role="consol")
    scope = SimpleNamespace(
        node_key="ROOT:consol",
        is_root_consol=True,
    )
    records = [_record("五-1-1")]

    resolve_template = AsyncMock(return_value="soe")
    build_tree = AsyncMock(return_value=root)
    resolve_scope = AsyncMock(return_value=scope)
    load_records = AsyncMock(return_value=records)
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        resolve_template,
    )
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.consol_note_tables",
        lambda _tt: [_table("五-1-1")],
    )
    monkeypatch.setattr("app.services.consol_tree_service.build_tree", build_tree)
    monkeypatch.setattr("app.services.consol_node_scope.resolve_node_scope", resolve_scope)
    monkeypatch.setattr(
        "app.services.consol_node_scope.load_scoped_note_records", load_records
    )
    monkeypatch.setattr(
        "app.services.consol_note_section_mapping.resolve_mapping_entry",
        lambda _tt, _sid: {"standalone_note_section": "八、1"},
    )

    result = await load_root_consol_export_notes(
        MagicMock(),
        project_id,
        2025,
        template_type="soe",
        index_sections=_index(),
    )

    assert [note.note_section for note in result] == ["八、1"]
    resolve_template.assert_awaited_once()
    build_tree.assert_awaited_once()
    resolve_scope.assert_awaited_once_with(
        resolve_template.await_args.args[0], project_id, 2025, "ROOT:consol"
    )
    load_records.assert_awaited_once_with(
        resolve_template.await_args.args[0],
        scope,
        allow_root_legacy_fallback=True,
    )


@pytest.mark.asyncio
async def test_loader_rejects_missing_or_non_consol_root(monkeypatch):
    monkeypatch.setattr(
        "app.services.consol_note_formula_service.resolve_note_template_type",
        AsyncMock(return_value="soe"),
    )
    monkeypatch.setattr(
        "app.services.consol_tree_service.build_tree",
        AsyncMock(return_value=SimpleNamespace(node_key="ROOT:parent", role="parent")),
    )
    resolve_scope = AsyncMock()
    monkeypatch.setattr("app.services.consol_node_scope.resolve_node_scope", resolve_scope)

    with pytest.raises(ConsolNoteExportError) as caught:
        await load_root_consol_export_notes(
            MagicMock(),
            uuid4(),
            2025,
            template_type="soe",
            index_sections=_index(),
        )
    assert caught.value.code == "CONSOL_NOTE_ROOT_MISSING"
    resolve_scope.assert_not_awaited()
