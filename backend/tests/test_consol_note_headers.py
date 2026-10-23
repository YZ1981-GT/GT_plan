"""合并附注表头契约：种子只存 ``multi_header``，展示表头由 ``normalize_consol_note_section`` 投影（R7.8 按类重写）。

CP-04 曾计划在种子里显式写 ``header_rows`` / ``_header_row_indexes``，未落地；契约在 ``d59512f33`` + ``70e718922`` 改为种子只存
多级表头、读取时投影。本文件按现行契约断言（design §16.8）：
- A 投影后表头行都在 ``header_rows``，表体行一行不少（``_header_row_indexes == []``）、金额留在存储坐标；
- B 章节接口与公式服务两条读取路径投影一致；C 章节详情接口带 ``template_type``（前端身份校验）；
- D 上市第五章每张表的列数 / 逐列表头路径 / 行名与上市合并 Word 一致（测试时解析 Word；有意保留的差异逐条登记，失效即报；
  表头占位列按单体模板实例化的 6 张逐列比单体模板，R7.7）；
- E 上市 五-9-4~7 保留 8 个网格列（R6.3）；F 种子不带 ``header_rows`` / ``_header_row_indexes``。
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.services.consol_note_headers import header_cells, normalize_consol_note_section
from app.services.note_table_header_catalog import standalone_sections
from app.services.note_table_header_library import column_paths, norm
from app.services.note_word_table import _row_keys, _table_grid, parse_word_table
from scripts.seed import sync_note_templates_from_word as S

DATA = Path(__file__).resolve().parents[1] / "data"
DOCX = DATA / "audit_report_templates" / "disclosure_notes"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def section(standard, section_id="五-5-2"):
    return next(s for s in json.loads((DATA / f"consol_note_sections_{standard}.json").read_text(encoding="utf-8")) if s["section_id"] == section_id)


# ─── A：投影坐标 ─────────────────────────────────────────────────────────


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
    # 表头全在 header_rows（由 multi_header 投影），种子 rows 里没有表头行
    assert normalized["_header_row_indexes"] == []
    assert normalized["_body_row_indexes"] == list(range(len(raw["rows"])))


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
    path = DOCX / f"{standard}_{variant}.docx"
    candidates = docx_header(path, width, period)
    assert actual in candidates, f"Contract not found in {path.name}: {actual}"


# ─── B：两条读取路径投影一致 ─────────────────────────────────────────────


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
        # 章节接口（补了 _column_groups / columns / _row_types）与公式服务读到的同一张表，投影出的表头逐格相同
        api, formula = normalize_consol_note_section(api_sections[sid]), normalize_consol_note_section(formula_sections[sid])
        assert api["header_rows"] == formula["header_rows"] == normalize_consol_note_section(item)["header_rows"], sid


# ─── C：章节详情接口 ─────────────────────────────────────────────────────


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
    assert payload["template_type"] == standard and payload["section_id"] == "五-5-2"
    assert len(payload["headers"]) == width and payload["rows"] == section(standard)["rows"]
    # 接口带的多级表头足够前后端投影出同一份表头（3 层），表体行不被当表头
    projected = normalize_consol_note_section(payload)
    assert len(projected["header_rows"]) == 3 and projected["_header_row_indexes"] == []
    assert projected["header_rows"] == normalize_consol_note_section(section(standard))["header_rows"]


# ─── 投影器本身（不读种子） ──────────────────────────────────────────────


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


# ─── D：上市第五章逐表与 Word 一致 ───────────────────────────────────────

#: 与上市合并 Word 结构不同、有意保留的表 → (差异, 理由)。差异变了或没了都报（登记可伪证）。
LISTED_WORD_EXEMPT: dict[str, tuple[list[str], str]] = {
    "五-5-1": (["列数 3≠4"], "Word 小计 / 减：坏账准备两行末格横跨两个网格列（其余行 3 格），逻辑上就是账龄 / 期末余额 / 上年年末余额 3 列"),
    **{sid: (["列数 8≠7"], "R6.3：保留 8 个网格列（Word 账面余额/金额拆成两格、数据行再并回一格），不折成 7 列；E 类钉住")
       for sid in ("五-9-4", "五-9-5", "五-9-6", "五-9-7")},
    "五-10-1": (["列数 9≠7", "行名"], "网格 9 列（Word 账面价值、减值准备各拆两格，同 R6.3 口径）；Word 表下半截的净额简表"
                "（合同资产 / 减：减值准备 / 小计…）与上半截同口径重复，单体也不收，种子不收（R7.8）"),
    "五-11-1": (["列数 9≠7", "行名"], "网格 9 列（同上）；Word 表下半截另起表头的持有待售负债表与单体一致拆成 五-11-2"),
    "五-23-3": (["表头路径 列[1, 2, 3, 4, 8]"], "Word 第 2 行是勾稽字母注记（A / B / C / D / E=A+B-C-D），平台按数据行判，"
                "种子按第二层表头存（R6.3：字母注记列不做变动表勾稽）"),
    "五-28-3": (["列数 2≠1"], "列跨度表示差异：Word 表头一格横跨两个网格列，种子按两列存（design §16.8）"),
}
#: 没有 Word 标记、从上一张 Word 表下半截拆出来的种子条目（同步工具 ``EMBEDDED_SPLITS``）
LISTED_EMBEDDED = {"五-11-2"}
#: 表头占位列按单体模板实例化的条目（同步工具 ``STANDALONE_INSTANTIATED``，R7.7）：列与单体模板逐列相同、Word 那一格
#: 确实是按需增加的占位、表体行（含「可无限量添加行」动态行）仍照 Word
LISTED_INSTANTIATED = {sid for std, sid in S.STANDALONE_INSTANTIATED if std == "listed"}
_PLACEHOLDER = re.compile(r"^(?:…+|可无限量添加[行列])$")


@lru_cache(maxsize=None)
def _listed_positions() -> dict[str, dict]:
    """上市合并 Word 五、1~69 节每张表 → 种子条目号：有标记的按同步工具 ``entry_sid``，节内没有标记的接在上一张之后。
    五、70 以后 Word 缺节标记（``KNOWN_SECTION_GAPS``），由 ``test_consol_note_seed_word_identity`` 按表名逐张钉住。"""
    out: dict[str, dict] = {}
    last: dict[int, int] = {}
    for wt in S.extract_all_word_tables(DOCX / "listed_consolidated.docx"):
        head, _, num = (wt.get("section") or "").partition("、")
        if head != "五" or not num.isdigit() or int(num) >= 70:
            continue
        n, tag = int(num), S.parse_tag(wt["tag"])
        sid = S.entry_sid("listed", tag) if tag else f"五-{n}-{last.get(n, 0) + 1}"
        last[n] = int(sid.rsplit("-", 1)[1])
        assert sid not in out, f"两张 Word 表对到 {sid}"
        out[sid] = wt
    return out


def _structure_diffs(entry: dict, wt: dict) -> list[str]:
    word = parse_word_table(wt["el"], "")
    if len(entry["headers"]) != word.columns:
        out = [f"列数 {len(entry['headers'])}≠{word.columns}"]
    else:
        mine, theirs = column_paths(entry), [tuple(norm(x) for x in p) for p in word.header_paths]
        bad = [i for i in range(len(mine)) if mine[i] != theirs[i] and (i or theirs[0])]  # Word 标签列表头留白不比
        out = [f"表头路径 列{bad}"] if bad else []
    if _row_keys([r[0] if isinstance(r, list) and r else "" for r in entry.get("rows") or []]) != _row_keys(word.row_labels):
        out.append("行名")
    return out


def _sid_order(sid: str) -> tuple[int, ...]:
    return tuple(int(x) for x in sid.split("-")[1:])


_LISTED_FIVE = sorted(
    (s["section_id"] for s in json.loads((DATA / "consol_note_sections_listed.json").read_text(encoding="utf-8"))
     if s["section_id"].count("-") == 2 and s["section_id"].startswith("五-") and _sid_order(s["section_id"])[0] < 70),
    key=_sid_order,
)


@pytest.mark.parametrize("sid", _LISTED_FIVE)
def test_listed_chapter_five_tables_follow_word(sid):
    entry = section("listed", sid)
    wt = _listed_positions().get(sid)
    if wt is None:
        assert sid in LISTED_EMBEDDED, f"{sid} 没有对应的 Word 表"
        return
    if sid in LISTED_INSTANTIATED:
        code, name = S.STANDALONE_INSTANTIATED[("listed", sid)]
        single = next(t for t in dict(standalone_sections("listed"))[code] if t.get("name") == name)
        word = parse_word_table(wt["el"], "")
        assert column_paths(entry)[1:] == column_paths(single)[1:], f"{sid} 列与单体模板《{name}》不一致"
        assert any(p and _PLACEHOLDER.match(norm(p[-1])) for p in word.header_paths[1:]), f"{sid} Word 表头已无占位列"
        assert [d for d in _structure_diffs(entry, wt) if d == "行名"] == [], f"{sid} 行与 Word 不一致"
        return
    diffs = _structure_diffs(entry, wt)
    expected = LISTED_WORD_EXEMPT.get(sid, ([], ""))[0]
    assert diffs == expected, f"{sid}《{entry.get('title')}》与 Word 不一致：{diffs}（登记：{expected}）"


def test_every_listed_word_table_has_a_seed_entry_and_exemptions_are_live():
    seed = set(_LISTED_FIVE)
    assert set(_listed_positions()) <= seed
    assert set(LISTED_WORD_EXEMPT) <= set(_listed_positions()) and LISTED_EMBEDDED <= seed - set(_listed_positions())
    assert all(reason for _diffs, reason in LISTED_WORD_EXEMPT.values())
    assert LISTED_INSTANTIATED <= set(_listed_positions()) and not LISTED_INSTANTIATED & set(LISTED_WORD_EXEMPT)


# ─── E：上市 五-9-4~7 保留 8 个网格列（R6.3） ────────────────────────────

INVENTORY = ("五-9-4", "五-9-5", "五-9-6", "五-9-7")


@pytest.mark.parametrize("section_id", INVENTORY)
def test_inventory_keeps_eight_grid_columns_and_header_ranges(section_id):
    raw = section("listed", section_id)
    nrows, ncols, grid, _texts, _spans = _table_grid(_listed_positions()[section_id]["el"])
    # Word：8 个网格列，表头「金额」横跨第 1、2 网格列，数据行把这两格并回一格（死重复列）
    assert ncols == 8 and len(raw["headers"]) == 8 and raw["headers"][1] == raw["headers"][2]
    first_body = len(raw["multi_header"])
    assert grid[(first_body, 1)] == grid[(first_body, 2)], "Word 数据行第 1、2 网格列应是同一格"
    normalized = normalize_consol_note_section(raw)
    cells = header_cells(normalized["header_rows"], 8)
    assert normalized["_header_row_indexes"] == [] and len(normalized["header_rows"]) == 3
    assert [(r, c, v["colspan"]) for r, c, v in cells if v["text"] == "账面余额"] == [(1, 1, 3)]
    assert [(r, c, v["colspan"]) for r, c, v in cells if v["text"] == "存货跌价准备"] == [(1, 4, 3)]
    assert [(r, c, v["rowspan"]) for r, c, v in cells if v["text"] == "账面价值"] == [(1, 7, 2)]
    assert [(r, c, v["colspan"]) for r, c, v in cells if v["text"] == "金额"] == [(2, 1, 2), (2, 4, 1)]
    raw["rows"][0] = ["业务", "101", "", "303", "404", "505", "606", "707"]
    assert normalize_consol_note_section(raw)["rows"][0] == raw["rows"][0]


# ─── F：种子只存多级表头 ─────────────────────────────────────────────────

SINGLE_LEVEL = {"五-4-11", "五-5-11", "五-16-10", "五-6-2", "五-13-2", "五-31-2", "五-27-1", "五-28-3"}


@pytest.mark.parametrize("standard", ["soe", "listed"])
def test_seeds_store_multi_header_only_and_single_level_rows_are_not_removed(standard):
    all_sections = json.loads((DATA / f"consol_note_sections_{standard}.json").read_text(encoding="utf-8"))
    assert [s["section_id"] for s in all_sections if "header_rows" in s or "_header_row_indexes" in s] == []
    if standard != "listed":
        return
    for section_id in SINGLE_LEVEL:
        raw = section("listed", section_id)
        result = normalize_consol_note_section(raw)
        assert len(result["header_rows"]) == 1 and not raw.get("multi_header")
        assert result["_header_row_indexes"] == []
        assert result["_body_row_indexes"] == list(range(len(raw["rows"])))
        assert result["rows"] == raw["rows"]
