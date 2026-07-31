"""K1 其他应收款附注章节结构契约（spec: k1-other-receivable-disclosure-alignment）.

锁定三件事：
1. §五、8 / §八、9 的表清单、两级表头（``_column_groups``）、``guidance`` 齐备；
2. 新增的 4 张国企表存在且列头逐字对齐 K1 国企披露 sheet；
3. 生成期 seed 元数据透传：``_carry_seed_column_meta`` 带 ``_column_groups``，
   ``_carry_seed_table_guidance`` 让 seed 显式 guidance 覆盖段落推断结果。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.disclosure_engine import (
    _carry_seed_column_meta,
    _carry_seed_table_guidance,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED_SECTION = "五、8"
SOE_SECTION = "八、9"

SOE_NEW_TABLES = {
    "其他应收款项账面余额变动": ["账面余额", "第一阶段", "第二阶段", "第三阶段", "合计"],
    "由金融资产转移而终止确认的其他应收款项": [
        "债务人名称", "终止确认金额", "与终止确认相关的利得或损失",
    ],
    "其他应收款项转移继续涉入形成的资产、负债的金额": ["项  目", "期末金额"],
    "涉及政府补助的应收款项": [
        "单位名称", "政府补助项目名称", "期末余额", "期末账龄", "预计收取的时间、金额及依据",
    ],
}

# 两级表头表 → 期望的 group 名（顺序即 _column_groups 顺序）
GROUPED_TABLES = {
    "listed": {
        "按款项性质披露": ["期末金额", "上年年末金额"],
        # 源 xlsx 上市 A91:E92 两行表头（A91:A92 / E91:E92 rowspan=2，B/C/D 各带 ECL 释义）
        # → 混合分组：三个阶段各 span=1，标签列与「合计」列不带 group
        "本期计提、收回或转回的坏账准备情况": ["第一阶段", "第二阶段", "第三阶段"],
    },
    "soe": {
        # 🔴 「按账龄披露其他应收款项」已按源 xlsx A6:C15 还原为**单级 3 列** →
        # 不再是两级表头，故从本清单移出（下方 SOE_FLAT_TABLES 反向锁死）

        "按坏账准备计提方法分类披露其他应收款项": ["账面余额", "坏账准备"],
        # 🔴 原为**裸续表名** `续：`（源 xlsx A27 就是这两个字）。裸续表名跨章节撞键，
        # 且附注 TAB 只显示「续：」看不出续的是哪张表 → `fix_note_k_complex_structure`
        # 已正名；前端同源常量 `K1_SOE_SUBTABLE.methodPrior`。
        "按坏账准备计提方法分类披露其他应收款项（续：期初余额）": ["账面余额", "坏账准备"],
        "单项计提坏账准备的其他应收款项": ["期末余额"],
        "账龄组合": ["期末数", "期初数"],
        "采用余额百分比法或其他组合方法计提坏账准备的其他应收款项": ["期末数", "期初数"],
    },
}

#: 显式单级（`flat`）的表 —— 反向锁死「不得被误加两级表头」
SOE_FLAT_TABLES = ["按账龄披露其他应收款项", "其他应收款项坏账准备计提情况", "其他应收款项账面余额变动"]

#: 上市侧 2026-07-31 补入的 3 张表（源模板 ⑧⑨⑩，国企侧一直有、上市侧整张缺失）
LISTED_ADDED_TABLES = {
    "应收政府补助情况": [
        "单位名称（注：政府补助的发文单位）", "政府补助项目名称", "期末余额", "账龄",
        "预计收取的时间、金额及依据",
    ],
    "因金融资产转移而终止确认的其他应收款情况": [
        "项  目", "转移方式", "终止确认金额", "与终止确认相关的利得或损失",
    ],
    "转移其他应收款且继续涉入形成的资产、负债的金额": ["项  目", "期末数"],
}

#: 账龄行骨架（源 xlsx = 5 年段 6 档；模板原先是 3 年段，缺 3至4年/4至5年/5年以上）
LISTED_AGING_ROWS = [
    "1年以内", "其中：0-X个月", "X-Y个月", "1年以内小计：",
    "1至2年", "2至3年", "3至4年", "4至5年", "5年以上",
    "小计", "减：坏账准备", "合计",
]
SOE_AGING_ROWS = [
    "1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上",
    "小  计", "减：坏账准备", "合  计",
]
SOE_PORTFOLIO_AGING_ROWS = [
    "1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上", "合  计",
]


def _section(std: str) -> dict:
    path = DATA_DIR / f"note_template_{std}.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    target = LISTED_SECTION if std == "listed" else SOE_SECTION
    hit = [s for s in raw["sections"] if str(s.get("section_number", "")).strip() == target]
    assert hit, f"{path.name} 缺少章节 {target}"
    return hit[0]


@pytest.fixture(scope="module")
def listed() -> dict:
    return _section("listed")


@pytest.fixture(scope="module")
def soe() -> dict:
    return _section("soe")


# ─── 表清单与列头 ────────────────────────────────────────────────────────────

def test_soe_has_four_new_tables(soe: dict) -> None:
    names = {t["name"] for t in soe["tables"]}
    missing = set(SOE_NEW_TABLES) - names
    assert not missing, f"§八、9 缺表：{sorted(missing)}"


@pytest.mark.parametrize("name,headers", sorted(SOE_NEW_TABLES.items()))
def test_soe_new_table_headers(soe: dict, name: str, headers: list[str]) -> None:
    tbl = next(t for t in soe["tables"] if t["name"] == name)
    assert tbl["headers"] == headers


@pytest.mark.parametrize("std", ["listed", "soe"])
def test_every_table_has_guidance(std: str, listed: dict, soe: dict) -> None:
    sec = listed if std == "listed" else soe
    missing = [t["name"] for t in sec["tables"] if not str(t.get("guidance") or "").strip()]
    assert not missing, f"{std} 缺 guidance：{missing}"


@pytest.mark.parametrize("std", ["listed", "soe"])
def test_two_level_headers_declared(std: str, listed: dict, soe: dict) -> None:
    sec = listed if std == "listed" else soe
    by_name = {t["name"]: t for t in sec["tables"]}
    for name, groups in GROUPED_TABLES[std].items():
        tbl = by_name.get(name)
        assert tbl is not None, f"{std} 缺表 {name}"
        declared = tbl.get("_column_groups")
        assert isinstance(declared, list) and declared, f"{name} 缺 _column_groups"
        assert [g["group"] for g in declared] == groups
        # group 覆盖范围不得越界，且不得与标签列（index 0）重叠
        for g in declared:
            assert g["start"] >= 1
            assert g["start"] + g["span"] <= len(tbl["headers"])


def test_headers_have_no_blank(listed: dict, soe: dict) -> None:
    """两级表头用全限定列名 + _column_groups 表达，禁止空串占位。"""
    for sec in (listed, soe):
        for t in sec["tables"]:
            for h in t.get("headers") or []:
                assert str(h).strip(), f'{t["name"]} 存在空列名'


def test_listed_stage_tables_have_unit_rows(listed: dict) -> None:
    """6 张三阶段表都应在「按单项计提坏账准备」下挂示例单位行（源模板 R34/R35）。"""
    stage_names = [t["name"] for t in listed["tables"] if "阶段的坏账准备" in t["name"]]
    assert len(stage_names) == 6
    for name in stage_names:
        labels = [r.get("label") for r in next(t for t in listed["tables"] if t["name"] == name)["rows"]]
        assert "其他应收款单位1" in labels and "其他应收款单位2" in labels, name


def test_soe_text_sections_cover_new_blocks(soe: dict) -> None:
    joined = "\n".join(soe.get("text_sections") or [])
    for keyword in (
        "其他应收款项账面余额变动",
        "由金融资产转移而终止确认的其他应收款项",
        "其他应收款项转移继续涉入形成的资产、负债的金额",
        "涉及政府补助的应收款项",
        "本期坏账准备计提金额以及评估金融工具的信用风险是否显著增加的采用依据",
    ):
        assert keyword in joined, f"text_sections 缺 {keyword}"


# ─── 生成期透传 ──────────────────────────────────────────────────────────────

def test_carry_seed_column_meta_passes_column_groups() -> None:
    seed = {"_column_groups": [{"group": "期末数", "start": 1, "span": 2}]}
    built: dict = {"headers": ["账  龄", "a", "b"], "rows": []}
    _carry_seed_column_meta(seed, built)
    assert built["_column_groups"] == seed["_column_groups"]


def test_carry_seed_column_meta_does_not_override_existing() -> None:
    seed = {"_column_groups": [{"group": "seed", "start": 1, "span": 1}]}
    built = {"_column_groups": [{"group": "existing", "start": 1, "span": 1}]}
    _carry_seed_column_meta(seed, built)
    assert built["_column_groups"][0]["group"] == "existing"


def test_seed_guidance_overrides_inferred() -> None:
    seed_tables = [{"name": "A", "guidance": "源模板红字"}, {"name": "B"}]
    built_tables = [{"name": "A", "guidance": "段落推断"}, {"name": "B", "guidance": "段落推断"}]
    _carry_seed_table_guidance(seed_tables, built_tables)
    assert built_tables[0]["guidance"] == "源模板红字"
    # seed 未声明 guidance 的表保持推断结果（其余 300+ 章节零影响）
    assert built_tables[1]["guidance"] == "段落推断"


def test_seed_guidance_tolerates_length_mismatch() -> None:
    built_tables = [{"name": "A"}]
    _carry_seed_table_guidance([{"guidance": "x"}, {"guidance": "y"}], built_tables)
    assert built_tables[0]["guidance"] == "x"
    _carry_seed_table_guidance([], built_tables)
    assert built_tables[0]["guidance"] == "x"


# ─── 2026-07-31 结构对齐（spec: k1-four-table-extraction-and-disclosure-alignment）───
#
# 本段是**三向比对**：源 xlsx 单元格文本 ↔ 模板 headers ↔ 期望常量。
# 源 xlsx 是唯一裁决者（`附注模版/*.md` 在本仓库不存在），故直读 openpyxl。

K1_XLSX = (
    Path(__file__).resolve().parents[2] / "wp_templates" / "K" / "K1 其他应收款.xlsx"
)
SHEET_LISTED = "附注披露信息(上市公司）"
SHEET_SOE = "附注披露信息（国企）"


def _rows(std: str) -> dict[str, list[str]]:
    """表名 → rows 的 label 列表。"""
    sec = _section(std)
    return {
        t["name"]: [str(r.get("label", "")) for r in (t.get("rows") or [])]
        for t in sec["tables"]
    }


@pytest.fixture(scope="module")
def xlsx_cells() -> dict[str, dict[str, str]]:
    """源 xlsx 两个披露 sheet 的 `{sheet: {coord: text}}`（只读，非空格）。"""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(K1_XLSX, data_only=True)
    out: dict[str, dict[str, str]] = {}
    for name in (SHEET_LISTED, SHEET_SOE):
        assert name in wb.sheetnames, f"源 xlsx 缺 sheet「{name}」（tab 名漂移？）"
        ws = wb[name]
        cells: dict[str, str] = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and str(c.value).strip():
                    cells[c.coordinate] = str(c.value).strip()
        out[name] = cells
    wb.close()
    return out


def test_source_xlsx_sheet_names_are_authoritative(xlsx_cells: dict) -> None:
    """反向自检：源 xlsx tab 名确实是「前半角后全角」/「国企」，本文件常量没写错。"""
    assert set(xlsx_cells) == {SHEET_LISTED, SHEET_SOE}


# ── 上市：三阶段变动表两级表头（源 A91:E92） ─────────────────────────────────

def test_listed_movement_two_level_matches_xlsx(listed: dict, xlsx_cells: dict) -> None:
    cells = xlsx_cells[SHEET_LISTED]
    # 源 xlsx 第一行 = 阶段名 / 第二行 = ECL 释义（反向自检：单元格确实存在）
    assert cells["A91"] == "坏账准备"
    assert cells["B91"] == "第一阶段"
    assert cells["E91"] == "合计"
    parents = [cells["B91"], cells["C91"], cells["D91"]]
    leaves = [cells["B92"], cells["C92"], cells["D92"]]

    tbl = next(
        t for t in listed["tables"] if t["name"] == "本期计提、收回或转回的坏账准备情况"
    )
    # headers = 叶子列名（父表头由 _column_groups 承载）
    assert tbl["headers"] == [cells["A91"], *leaves, cells["E91"]]
    assert [g["group"] for g in tbl["_column_groups"]] == parents
    # 混合分组：标签列（0）与合计列（4）不在任何组里
    covered = {i for g in tbl["_column_groups"] for i in range(g["start"], g["start"] + g["span"])}
    assert covered == {1, 2, 3}
    # 标签列不得打 flat（打了 _extract_column_groups 会判为显式单级 → 分组失效）
    assert not tbl["columns"][0].get("flat")
    # key 保持既有中文数据键（同步载荷行对象就是这些键）
    assert [c["key"] for c in tbl["columns"]] == [
        "label", "第一阶段", "第二阶段", "第三阶段", "合计",
    ]


def test_soe_movement_stays_flat(soe: dict, xlsx_cells: dict) -> None:
    """国企侧源 xlsx 是一行表头（阶段名+释义同格）→ 必须保持单级，不得被误加分组。"""
    cells = xlsx_cells[SHEET_SOE]
    assert cells["B63"] == "第一阶段未来12个月预期信用损失"
    assert "B64" not in cells or cells.get("B64") != "未来12个月预期信用损失"
    for name in SOE_FLAT_TABLES:
        tbl = next(t for t in soe["tables"] if t["name"] == name)
        assert tbl["columns"][0].get("flat") is True, f"{name} 标签列须打 flat"
        assert "_column_groups" not in tbl, f"{name} 不该有 _column_groups"


# ── 账龄行骨架（源 xlsx 是 5 年段 6 档） ────────────────────────────────────

def test_listed_aging_rows_are_five_year_bands(xlsx_cells: dict) -> None:
    cells = xlsx_cells[SHEET_LISTED]
    # 反向自检：源 xlsx 确实有 3至4年 / 4至5年 / 5年以上
    assert [cells["A15"], cells["A16"], cells["A17"]] == ["3至4年", "4至5年", "5年以上"]
    assert _rows("listed")["按账龄披露"] == LISTED_AGING_ROWS


def test_soe_aging_table_is_three_columns(soe: dict, xlsx_cells: dict) -> None:
    """源 xlsx 国企 A6:C15 = 单级 3 列 + 小计/减坏账准备/合计（模板原为 5 列无小计）。"""
    cells = xlsx_cells[SHEET_SOE]
    assert [cells["A6"], cells["B6"], cells["C6"]] == ["账  龄", "期末数", "期初数"]
    assert cells["A13"] == "小  计"
    assert cells["A14"] == "减：坏账准备"
    assert cells["A15"] == "合  计"

    tbl = next(t for t in soe["tables"] if t["name"] == "按账龄披露其他应收款项")
    assert tbl["headers"] == ["账  龄", "期末数", "期初数"]
    assert [c["key"] for c in tbl["columns"]] == ["label", "期末数", "期初数"]
    assert _rows("soe")["按账龄披露其他应收款项"] == SOE_AGING_ROWS


def test_soe_portfolio_aging_rows_are_six_bands(xlsx_cells: dict) -> None:
    cells = xlsx_cells[SHEET_SOE]
    assert [cells[f"A{r}"] for r in range(49, 55)] == [
        "1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上",
    ]
    assert _rows("soe")["账龄组合"] == SOE_PORTFOLIO_AGING_ROWS


# ── 上市补入的 3 张表（源模板 ⑧⑨⑩） ───────────────────────────────────────

def test_listed_has_three_added_tables(listed: dict) -> None:
    names = {t["name"] for t in listed["tables"]}
    missing = set(LISTED_ADDED_TABLES) - names
    assert not missing, f"§五、8 缺表：{sorted(missing)}"


@pytest.mark.parametrize("name,headers", sorted(LISTED_ADDED_TABLES.items()))
def test_listed_added_table_headers(listed: dict, name: str, headers: list[str]) -> None:
    tbl = next(t for t in listed["tables"] if t["name"] == name)
    assert tbl["headers"] == headers


def test_listed_added_tables_backed_by_xlsx(xlsx_cells: dict) -> None:
    """三张表的列头逐字来自源 xlsx（⑧ A137:E137 / ⑨ A146:D146 / ⑩ A153:B153）。"""
    cells = xlsx_cells[SHEET_LISTED]
    assert cells["A137"] == "单位名称（注：政府补助的发文单位）"
    assert cells["B137"] == "政府补助项目名称"
    assert [cells["A146"], cells["B146"], cells["C146"], cells["D146"]] == [
        "项  目", "转移方式", "终止确认金额", "与终止确认相关的利得或损失",
    ]
    assert [cells["A153"], cells["B153"]] == ["项  目", "期末数"]


def test_listed_text_sections_cover_added_blocks(listed: dict) -> None:
    joined = "\n".join(listed.get("text_sections") or [])
    for keyword in (
        "应收政府补助情况",
        "因金融资产转移而终止确认的其他应收款情况",
        "转移其他应收款且继续涉入形成的资产、负债的金额",
    ):
        assert keyword in joined, f"text_sections 缺 {keyword}"


def test_added_text_sections_are_not_all_titles(listed: dict) -> None:
    """正文段不得带 `#` —— 否则被 `_is_table_title_paragraph` 当标题静默丢弃。"""
    paras = [str(p) for p in (listed.get("text_sections") or [])]
    body = [p for p in paras if "信息披露解释性公告2号" in p]
    assert body, "补入的政府补助说明正文段缺失"
    for p in body:
        assert not p.strip().startswith("#"), f"正文段误加标题前缀：{p[:30]}"


def test_fixer_check_reports_no_debt() -> None:
    """幂等脚本 `--check` 必须零欠账（含 text_sections 缺段检查）。"""
    import importlib.util

    fixer_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "fix"
        / "fix_note_k_complex_structure.py"
    )
    spec = importlib.util.spec_from_file_location("_k1_fixer", fixer_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for std, section_number, expected, required in (
        ("listed", LISTED_SECTION, mod.K1_LISTED_EXPECTED, mod.K1_LISTED_REQUIRE_TEXTS),
        ("soe", SOE_SECTION, mod.K1_SOE_EXPECTED, None),
    ):
        sec = _section(std)
        assert str(sec.get("section_number")) == section_number
        errs = mod.validate_section(sec, expected)
        assert not errs, f"{std} 结构欠账：{errs}"
        if required:
            miss = mod.missing_text_sections(sec, required)
            assert not miss, f"{std} text_sections 缺段：{[m[:20] for m in miss]}"
