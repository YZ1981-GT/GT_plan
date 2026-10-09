"""CP04: real JSON and four DOCX facts, pure projection and HTTP boundary."""
from copy import deepcopy
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.services.consol_note_headers import header_cells, normalize_consol_note_section

DATA = Path(__file__).resolve().parents[1] / "data"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def section(standard, section_id="五-5-2"):
    return next(s for s in json.loads((DATA / f"consol_note_sections_{standard}.json").read_text(encoding="utf-8")) if s["section_id"] == section_id)


@pytest.mark.parametrize("standard,section_id,width", [("soe", "五-5-2", 11), ("listed", "五-5-2", 6), ("listed", "五-5-3", 6)])
def test_header_spans_rows_and_unique_amounts_stay_in_storage_coordinates(standard, section_id, width):
    raw = section(standard, section_id)
    raw["rows"][-1] = ["合  计"] + [str(101 * c) for c in range(1, width)]
    before = deepcopy(raw)
    normalized = normalize_consol_note_section(raw)
    assert raw == before and normalized["rows"] == raw["rows"]
    cells = header_cells(normalized["header_rows"], width)
    assert cells[0] == (0, 0, {"text": "类  别", "colspan": 1, "rowspan": 3})
    assert [(r, c, v["colspan"], v["rowspan"]) for r, c, v in cells if v["text"] == "账面价值"] == [(1, 5, 1, 2)] + ([(1, 10, 1, 2)] if width == 11 else [])
    assert [(r, c) for r, c, v in cells if v["text"] == "金额"] == [(2, 1), (2, 3)] + ([(2, 6), (2, 8)] if width == 11 else [])
    assert normalized["rows"][-1][1:] == [str(101 * c) for c in range(1, width)]
    assert normalized["_header_row_indexes"] == ([0, 1] if standard == "listed" else [])


def docx_header(path, width, period):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    matches = []
    for table in root.findall(".//w:tbl", NS):
        if len(table.findall("w:tblGrid/w:gridCol", NS)) != width:
            continue
        trs = table.findall("w:tr", NS)[:3]
        text = "".join(t.text or "" for tr in trs for t in tr.findall(".//w:t", NS))
        if "类" not in text or "账面余额" not in text or "坏账准备" not in text or period not in text:
            continue
        placed = []
        pending = {}
        for r, tr in enumerate(trs):
            c = 0
            for tc in tr.findall("w:tc", NS):
                span = tc.find("w:tcPr/w:gridSpan", NS)
                cs = int(span.get(W + "val", "1")) if span is not None else 1
                merge = tc.find("w:tcPr/w:vMerge", NS)
                value = "".join(t.text or "" for t in tc.findall(".//w:t", NS))
                if merge is not None and merge.get(W + "val") != "restart":
                    if c in pending:
                        pending[c][2]["rowspan"] += 1
                else:
                    entry = (r, c, {"text": value, "colspan": cs, "rowspan": 1})
                    placed.append(entry)
                    if merge is not None:
                        pending[c] = entry
                c += cs
        matches.append(placed)
    assert matches, f"Missing real DOCX header: {path.name}"
    return matches


@pytest.mark.parametrize("standard,variant,width,period", [
    ("soe", "standalone", 11, "期初数"), ("soe", "consolidated", 11, "期初数"),
    ("listed", "standalone", 6, "期末余额"), ("listed", "consolidated", 6, "期末余额"),
])
def test_header_contract_matches_raw_xml_of_four_authority_templates(standard, variant, width, period):
    config = normalize_consol_note_section(section(standard))
    actual = header_cells(config["header_rows"], width)
    path = DATA / "audit_report_templates/disclosure_notes" / f"{standard}_{variant}.docx"
    candidates = docx_header(path, width, period)
    assert actual in candidates, f"Contract not found in {path.name}: {actual}"


@pytest.mark.parametrize("standard", ["soe", "listed"])
def test_all_real_sections_normalize_without_mutation_and_loader_paths_agree(standard):
    from app.routers.consol_note_sections import _load_sections
    from app.services.consol_note_formula_service import consol_note_tables
    raw = json.loads((DATA / f"consol_note_sections_{standard}.json").read_text(encoding="utf-8"))
    for item in raw:
        before = deepcopy(item)
        result = normalize_consol_note_section(item)
        assert item == before
        assert normalize_consol_note_section(result) == result
        assert result["rows"] == item["rows"]
        assert sorted(result["_header_row_indexes"] + result["_body_row_indexes"]) == list(range(len(item["rows"])))
    api_sections = {s["section_id"]: s for s in _load_sections(standard)}
    formula_sections = {s["section_id"]: s for s in consol_note_tables(standard)}
    assert len(api_sections) == len(raw) == len(formula_sections)
    for item in raw:
        sid = item["section_id"]
        assert api_sections[sid]["header_rows"] == formula_sections[sid]["header_rows"]


@pytest.mark.asyncio
@pytest.mark.parametrize("standard,width", [("soe", 11), ("listed", 6)])
async def test_real_http_detail_exposes_shared_contract_without_db(standard, width):
    from app.routers.consol_note_sections import router
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/consol-note-sections/{standard}/五-5-2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["template_type"] == standard
    assert len(payload["headers"]) == width and len(payload["header_rows"]) == 3
    assert payload["rows"] == section(standard)["rows"]
    assert payload["_header_row_indexes"] == ([0, 1] if standard == "listed" else [])


def test_groups_flat_fallback_and_configured_indexes_do_not_guess_business_text():
    flat = {"headers": ["类别", "金额", "比例"], "rows": [["账面余额", "100", "20"], ["金额", "200", "30"]]}
    result = normalize_consol_note_section(flat)
    assert result["_body_row_indexes"] == [0, 1]
    grouped = normalize_consol_note_section({**flat, "_column_groups": [{"group": "期末", "start": 1, "span": 2}]})
    assert header_cells(grouped["header_rows"], 3)[0][2]["rowspan"] == 2
    assert grouped["rows"] == flat["rows"]


@pytest.mark.parametrize("rows", [
    [[{"text": "x", "colspan": 4, "rowspan": 1}]],
    [[{"text": "x", "colspan": 1, "rowspan": 2}]],
    [[{"text": "x", "colspan": 1, "rowspan": 1}]],
    [[{"text": "x", "colspan": True, "rowspan": 1}]],
])
def test_invalid_header_geometry_fails_closed(rows):
    with pytest.raises(ValueError):
        header_cells(rows, 3)


def test_explicit_header_contract_takes_precedence_over_legacy_multi_header():
    result = normalize_consol_note_section({
        "headers": ["amount"], "rows": [["101"]], "multi_header": [["legacy"]],
        "header_rows": [[{"text": "exact", "colspan": 1, "rowspan": 1}]],
    })
    assert result["header_rows"][0][0]["text"] == "exact"


@pytest.mark.parametrize("indexes", [[1], [-1], [0.1], [True], [0, 0]])
def test_invalid_configured_row_indexes_fail_closed(indexes):
    with pytest.raises(ValueError, match="header row index"):
        normalize_consol_note_section({"headers": ["amount"], "rows": [["101"]], "_header_row_indexes": indexes})


EXPLICIT_LISTED = (
    "五-4-1 五-4-5 五-4-6 五-4-7 五-4-8 五-4-9 五-4-10 五-4-11 "
    "五-5-2 五-5-3 五-5-4 五-5-5 五-5-11 五-6-2 五-7-1 五-8-7 "
    "五-9-1 五-9-2 五-9-4 五-9-5 五-9-6 五-9-7 五-10-1 五-10-4 五-10-5 五-10-6 "
    "五-11-1 五-11-3 五-12-2 五-13-2 五-13-3 五-14-1 五-14-3 五-14-4 "
    "五-15-4 五-15-5 五-16-1 五-16-2 五-16-3 五-16-4 五-16-10 五-18-1 "
    "五-23-2 五-24-1 五-24-2 五-27-1 五-28-1 五-28-2 五-28-3 五-28-4 "
    "五-29-1 五-30-1 五-31-1 五-31-2 五-32-1 五-32-2 五-46-5 五-49-6 五-49-8 "
    "五-53-1 五-54-2 五-57-1 五-57-2 五-62-1 五-62-2 五-62-3 五-62-4 五-62-6 五-74-2 五-78-9"
).split()
INVENTORY = {"五-9-4", "五-9-5", "五-9-6", "五-9-7"}
HEADER_ONLY = {"五-10-1", "五-11-1"}
SINGLE_LEVEL = {"五-4-11", "五-5-11", "五-16-10", "五-6-2", "五-13-2", "五-31-2", "五-27-1", "五-28-3"}


@pytest.fixture(scope="module", params=["standalone", "consolidated"])
def listed_authority(request):
    from docx import Document
    path = DATA / "audit_report_templates/disclosure_notes" / f"listed_{request.param}.docx"
    result = []
    for table in Document(path).tables:
        values = []
        for row in table.rows:
            cells, seen = [], set()
            for cell in row.cells:
                if cell._tc not in seen:
                    seen.add(cell._tc)
                    cells.append(cell.text.strip().replace("\n", "<br/>"))
            values.append(cells)
        result.append((table._tbl, len(table.columns), values))
    return result


def raw_xml_header(table, width):
    """Determine depth from first-row vMerge, independently of JSON configuration."""
    trs = table.findall("w:tr", NS)
    depth, active, placed = 1, {}, []
    for r, tr in enumerate(trs):
        cursor, continued = 0, set()
        for tc in tr.findall("w:tc", NS):
            span = tc.find("w:tcPr/w:gridSpan", NS)
            cs = int(span.get(W + "val", "1")) if span is not None else 1
            merge = tc.find("w:tcPr/w:vMerge", NS)
            if merge is not None and merge.get(W + "val") != "restart":
                if cursor in active:
                    active[cursor][2]["rowspan"] += 1
                    continued.add(cursor)
            else:
                value = "<br/>".join("".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in tc.findall("w:p", NS)).strip()
                entry = (r, cursor, {"text": value, "colspan": cs, "rowspan": 1})
                placed.append(entry)
                if merge is not None:
                    active[cursor] = entry
            cursor += cs
        assert cursor == width
        if r == 0:
            roots = set(active)
        elif not roots.intersection(continued):
            break
        else:
            depth = r + 1
    return depth, [cell for cell in placed if cell[0] < depth]


@pytest.mark.parametrize("section_id", sorted(set(EXPLICIT_LISTED) - INVENTORY))
def test_explicit_listed_headers_match_authority_without_runtime_text_guessing(section_id, listed_authority):
    raw = section("listed", section_id)
    width = len(raw["headers"])
    expected_values = [raw["headers"], *raw["rows"]]
    matches = []
    for table, grid_width, rows in listed_authority:
        if grid_width != width:
            continue
        values = [row + [""] * (width - len(row)) for row in rows]
        if (values[:2] == expected_values[:2] if section_id in HEADER_ONLY else values == expected_values):
            matches.append(raw_xml_header(table, width))
    assert matches, f"No independently matched authority header for {section_id}"
    actual = header_cells(raw["header_rows"], width)
    assert all(actual == placed and len(raw["header_rows"]) == depth for depth, placed in matches)
    assert raw["_header_row_indexes"] == list(range(matches[0][0] - 1))
    assert (len(raw["header_rows"]) == 1) == (section_id in SINGLE_LEVEL)


@pytest.mark.parametrize("section_id", sorted(INVENTORY))
def test_inventory_logical_seven_columns_preserve_amounts_and_header_ranges(section_id, listed_authority):
    raw = section("listed", section_id)
    width = len(raw["headers"])
    candidates = []
    for table, grid_width, rows in listed_authority:
        if grid_width != 8 or rows[0][0] != raw["headers"][0]:
            continue
        if rows[0][2] != raw["headers"][2]:
            continue
        # Body cells merge physical columns 1 and 2 into a single amount leaf.
        if [row + [""] * (width - len(row)) for row in rows[3:]] != raw["rows"][2:]:
            continue
        body_cells = table.findall("w:tr", NS)[3].findall("w:tc", NS)
        assert len(body_cells) == 7
        assert body_cells[1].find("w:tcPr/w:gridSpan", NS).get(W + "val") == "2"
        candidates.append(raw_xml_header(table, 8))
    assert candidates and all(depth == 3 for depth, _ in candidates)
    normalized = normalize_consol_note_section(raw)
    cells = header_cells(normalized["header_rows"], width)
    assert width == 7 and normalized["_header_row_indexes"] == [0, 1]
    assert [(r, c, cell["colspan"]) for r, c, cell in cells if cell["text"] == "账面余额"] == [(1, 1, 2)]
    assert [(r, c, cell["colspan"]) for r, c, cell in cells if cell["text"] == "存货跌价准备"] == [(1, 3, 3)]
    assert [(r, c, cell["rowspan"]) for r, c, cell in cells if cell["text"] == "账面价值"] == [(1, 6, 2)]
    assert [(r, c) for r, c, cell in cells if cell["text"] == "金额"] == [(2, 1), (2, 3)]
    raw["rows"][2] = ["业务", "101", "202", "303", "404", "505", "606"]
    assert normalize_consol_note_section(raw)["rows"][2] == raw["rows"][2]


def test_explicit_listed_scope_is_exact_and_single_level_rows_are_not_removed():
    all_sections = json.loads((DATA / "consol_note_sections_listed.json").read_text(encoding="utf-8"))
    assert {s["section_id"] for s in all_sections if s.get("header_rows")} == set(EXPLICIT_LISTED)
    for section_id in SINGLE_LEVEL:
        raw = section("listed", section_id)
        result = normalize_consol_note_section(raw)
        assert result["_header_row_indexes"] == []
        assert result["_body_row_indexes"] == list(range(len(raw["rows"])))
        assert result["rows"] == raw["rows"]
