"""附注油气资产章节结构守卫（§八、25，仅国企）。

锁定 `fix_note_h5_oil_gas_structure.py` 的对齐结果，并固化两个结论：

1. §八、25 行集本就与源模板一致（16 行四层）—— 守卫防后续被 md 重建/并发会话改坏；
2. **上市侧没有油气资产章节**（`variant_matrix` listed=null + listed 模板实测 0 章节）
   —— 源 xlsx 有上市披露 sheet，易被误认为"缺章节"而凭空新建，此处显式固化。

spec: h5-oil-gas-disclosure-alignment (Task 5)
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import openpyxl

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "fix_note_h5_oil_gas_structure.py"
_SRC_XLSX = _ROOT / "wp_templates" / "H" / "H5 油气资产.xlsx"
_LISTED = _ROOT / "data" / "note_template_listed.json"
_MATRIX = _ROOT / "data" / "note_template_variant_matrix.json"
_FE_MAP = (
    _ROOT.parent / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "composables" / "h5NoteSectionMap.ts"
)


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_h5_struct", _FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()

_EXPECTED_KEYS = ["label", "begin", "increase", "decrease", "end"]

# 源模板四层 16 行（openpyxl 行 10~24 交叉验证）
_EXPECTED_ROWS = [
    "一、原价合计",
    "其中：1．探明矿区权益", "2．未探明矿区权益", "3．井及相关设施",
    "二、累计折耗合计",
    "其中：1．探明矿区权益", "2．井及相关设施",
    "三、油气资产减值准备累计金额合计",
    "其中：1．探明矿区权益", "2．未探明矿区权益", "3．井及相关设施",
    "四、油气资产账面价值合计",
    "其中：1．探明矿区权益", "2．未探明矿区权益", "3．井及相关设施",
]
_TOTAL_ROWS = [
    "一、原价合计", "二、累计折耗合计",
    "三、油气资产减值准备累计金额合计", "四、油气资产账面价值合计",
]


def _section() -> dict:
    path, section_number, _ = FIX._TARGETS["soe"]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return next(s for s in doc["sections"] if str(s.get("section_number")) == section_number)


def test_check_passes():
    _changes, warnings, errs = FIX._runner("soe", dry_run=True, check=True)
    assert not errs, f"结构欠账：{errs}"
    assert not warnings, f"告警：{warnings}"


def test_table_and_columns():
    sec = _section()
    tables = sec.get("tables") or []
    assert [t.get("name") for t in tables] == ["油气资产"], tables
    tbl = tables[0]
    cols = tbl.get("columns") or []
    assert [c.get("key") for c in cols] == _EXPECTED_KEYS, cols
    assert [c.get("label") for c in cols] == tbl["headers"], "columns.label 必须逐字等于 headers"
    assert cols[0].get("is_label") and cols[0].get("flat"), "首列须 is_label + flat（单级表头）"
    assert not tbl.get("_column_groups"), "单级表头不得残留 _column_groups"
    assert str(tbl.get("guidance") or "").strip(), "缺 guidance"


def test_row_set_four_layers():
    """16 行四层且合计行标 is_total（模板行集本就正确，此处防被改坏）。"""
    tbl = (_section().get("tables") or [])[0]
    rows = tbl.get("rows") or []
    assert [r.get("label") for r in rows] == _EXPECTED_ROWS, [r.get("label") for r in rows]
    assert [r.get("label") for r in rows if r.get("is_total")] == _TOTAL_ROWS
    assert not any(r.get("row_type") == "header_label" for r in rows)


def test_source_xlsx_cross_check():
    """openpyxl 直读源 xlsx：表头（行 9）与四层行标签（行 10~24）与模板一致。"""
    wb = openpyxl.load_workbook(_SRC_XLSX, data_only=True)
    assert "附注披露信息（国有企业）" in wb.sheetnames
    ws = wb["附注披露信息（国有企业）"]
    headers = [ws.cell(9, c).value for c in range(1, 6)]
    # 源模板首格是「项  目」（含空格），模板 headers[0] 归一为「项目」
    assert [str(h).replace(" ", "") for h in headers] == [
        "项目", "期初余额", "本期增加额", "本期减少额", "期末余额",
    ], headers
    src_rows = [str(ws.cell(r, 1).value or "").strip() for r in range(10, 25)]
    normalized = [x.replace(" ", "") for x in src_rows]
    assert normalized == [x.replace(" ", "") for x in _EXPECTED_ROWS], normalized


def test_listed_has_no_oil_gas_section():
    """🔴 上市侧无油气资产章节 —— 源 xlsx 有上市 sheet，禁据此凭空建章节。"""
    listed = json.loads(_LISTED.read_text(encoding="utf-8"))
    hits = [
        s.get("section_number")
        for s in listed.get("sections", [])
        if "油气" in str(s.get("section_title") or "") or "油气" in str(s.get("account_name") or "")
    ]
    assert hits == [], f"listed 模板出现油气资产章节 {hits} —— 与 variant_matrix listed=null 冲突"

    matrix = json.loads(_MATRIX.read_text(encoding="utf-8"))
    acct = next(a for a in matrix["accounts"] if a["account_key"] == "you_qi_zi_chan")
    assert acct["variants"]["listed_standalone"] is None
    assert acct["variants"]["listed_consolidated"] is None


def test_frontend_map_alignment():
    """前端列 key / 章节号 / `_note_texts` 位置与后端一致。"""
    src = _FE_MAP.read_text(encoding="utf-8")
    assert "soe: '八、25'" in src, "章节号漂移"
    for key in _EXPECTED_KEYS:
        assert f"key: '{key}'" in src, f"前端缺列 key {key}"
    # `_note_texts` 必须挂在 sub_table_data 上，不能是顶层字段
    assert "sub_table_data._note_texts" in src, "_note_texts 必须放 sub_table_data 内"
    assert "flat: true" in src, "单级表头须显式 flat"


def test_reverse_self_check():
    """validate_section 能抓出缺 columns（防守卫空转）。"""
    from _note_structure_kit import validate_section

    broken = {"tables": [{"name": "油气资产", "headers": ["项目"], "rows": [], "guidance": "x"}]}
    errs = validate_section(broken, ["油气资产"])
    assert any("缺 columns" in e for e in errs), errs
