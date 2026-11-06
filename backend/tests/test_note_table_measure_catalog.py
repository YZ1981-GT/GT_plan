"""附注稳定 table/column ID 与七类度量目录（platform-global-display-settings-closure 6A）。"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.contracts.display_measure import DisplayMeasureKind
from app.services.note_table_enrichment import enrich_note_table_data
from app.services.note_table_header_library import column_keys
from app.services.note_table_measure_catalog import (
    apply_measure_metadata,
    attach_consolidated_measure_metadata,
    catalog_entries,
)

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data"


def test_generator_check_is_clean_and_catalog_ids_are_unique():
    proc = subprocess.run(
        [sys.executable, "scripts/gen/gen_note_table_measure_catalog.py", "--check"],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    entries = catalog_entries()
    assert len(entries) > 1000
    table_ids = [row["table_id"] for row in entries]
    column_ids = [column["column_id"] for row in entries for column in row["columns"]]
    assert len(table_ids) == len(set(table_ids))
    assert len(column_ids) == len(set(column_ids))
    assert {column["kind"] for row in entries for column in row["columns"]} <= {item.value for item in DisplayMeasureKind}
    assert all(
        column["kind"] != "ratio" or (
            column["ratio_scale"] in ("fraction", "percent_points")
            or column["source"] == "unresolved-ratio-scale"
        )
        for row in entries for column in row["columns"]
    )


def _first_standalone_table(variant: str = "soe", *, without_ratio: bool = False):
    raw = json.loads((DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))
    for section in raw["sections"]:
        for table in section.get("tables") or []:
            if without_ratio and any(key.kind == "ratio" for key in column_keys(table)):
                continue
            return str(section["section_number"]), copy.deepcopy(table)
    raise AssertionError("template has no matching tables")


def test_standalone_enrichment_attaches_equal_length_metadata():
    section, table = _first_standalone_table(without_ratio=True)
    payload = {"_tables": [table]}
    enrich_note_table_data(payload, "soe", section)
    enriched = payload["_tables"][0]
    assert enriched["measure_status"] == "matched"
    width = len(enriched["headers"])
    assert width > 1
    assert len(enriched["column_ids"]) == len(enriched["column_kinds"]) == len(enriched["column_ratio_scales"]) == width
    assert enriched["column_kinds"][0] == "text"


def test_consolidated_uses_template_uuid_not_persisted_data_row_id():
    sections = json.loads((DATA / "consol_note_sections_soe.json").read_text(encoding="utf-8"))
    section = copy.deepcopy(next(
        row for row in sections if row.get("headers") and not any(key.kind == "ratio" for key in column_keys(row))
    ))
    expected = str(section["id"])
    section.pop("table_id", None)
    assert attach_consolidated_measure_metadata(section, "soe") == "matched"
    assert section["table_id"] == expected
    assert len(section["column_ids"]) == len(section["headers"])


def test_unmatched_table_keeps_explicit_unknown_columns_instead_of_guessing_amount():
    table = {"headers": ["项目", "数值"], "rows": []}
    assert apply_measure_metadata(table, variant="soe", section_id="不存在", table_index=0) == "unmatched"
    assert table["measure_status"] == "unmatched"
    assert table["column_kinds"] == [None, None]
    assert table["column_ratio_scales"] == [None, None]


@pytest.mark.asyncio
async def test_consolidated_detail_route_preserves_template_id_and_measure_arrays():
    from app.routers.consol_note_sections import get_section_detail

    section_id = next(
        row["section_id"] for row in json.loads((DATA / "consol_note_sections_soe.json").read_text(encoding="utf-8"))
        if row.get("headers") and not any(key.kind == "ratio" for key in column_keys(row))
    )
    response = await get_section_detail("soe", section_id)
    assert response["measure_status"] == "matched"
    assert response["table_id"] == response["id"]
    assert len(response["headers"]) == len(response["column_ids"]) == len(response["column_kinds"])


def test_standalone_catalog_corrects_unambiguous_project_template_mismatch():
    raw = json.loads((DATA / "note_template_listed.json").read_text(encoding="utf-8"))
    section = next(row for row in raw["sections"] if row.get("tables") and str(row.get("section_number", "")).startswith("五、"))
    payload = {"_tables": [copy.deepcopy(section["tables"][0])]}
    # 真实历史形态：项目 source_template=soe，上市章节号却只在 listed 目录出现。
    enrich_note_table_data(payload, "soe", str(section["section_number"]))
    assert payload["_tables"][0]["measure_status"] == "matched"


def test_ratio_without_explicit_scale_is_invalid_not_assumed_percent_points():
    entry = next(
        row for row in catalog_entries()
        if any(column["kind"] == "ratio" and column["ratio_scale"] is None for column in row["columns"])
    )
    table = {"table_id": entry["table_id"], "headers": ["列" for _ in entry["columns"]]}
    assert apply_measure_metadata(
        table, variant=entry["variant"], section_id=entry["section_id"], table_index=entry["table_index"],
    ) == "invalid"
    assert table["column_kinds"] == [None] * len(table["headers"])
