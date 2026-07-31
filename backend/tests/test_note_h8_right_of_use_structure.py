"""附注「使用权资产」章节结构守卫（上市 §五、25 / 国企 §八、26）。

锁定 `fix_note_h8_right_of_use_structure.py` 的对齐结果，并固化本 spec 最易踩错的判断：

**`……` 有两种语义，处理方式相反**：

- 作**列头**（上市源模板 F6 第 5 列）→ 永远收不到数据（载荷 `key: c.label` 推的是
  底稿默认分类第 4 类 `其他`）→ 必须展开为 `其他`；
- 作**行**（上市各层「本期增加/减少金额」下的 `……`）→ 在底稿模型里是**真实可扩行**
  （`cost_inc_ellipsis` 等键参与 `sumOf` 小计）→ **必须保留**，与「可无限量添加行」
  那类纯占位说明不同。

故本守卫既断言 headers/labels 里 `……` 不复活，又**正向断言上市 6 个 `……` 行仍在**。

spec: h8-right-of-use-disclosure-alignment (Task 4)
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import openpyxl

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "fix_note_h8_right_of_use_structure.py"
_SRC_XLSX = _ROOT / "wp_templates" / "H" / "H8 使用权资产.xlsx"
_FE = (
    _ROOT.parent / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "composables"
)
_FE_PAYLOAD = _FE / "h8DisclosureSyncPayload.ts"
_FE_LISTED_MODEL = _FE / "h8ListedDisclosureModel.ts"
_FE_SOE_MODEL = _FE / "h8SoeDisclosureModel.ts"

_SHEET_LISTED = "附注披露信息（上市公司）"
_SHEET_SOE = "附注披露信息（国企）"


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_h8_struct", _FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()

T_MAIN = "使用权资产"

_LISTED_KEYS = ["label", "房屋及建筑物", "机器设备", "运输设备", "其他", "合计"]
_SOE_KEYS = ["label", "begin", "increase", "decrease", "end"]

# 国企五层合计行（源 xlsx A7/A12/A17/A22/A27）
_SOE_LAYER_TOTALS = [
    "一、账面原值合计",
    "二、累计折旧合计",
    "三、使用权资产账面净值合计",
    "四、减值准备合计",
    "五、使用权资产账面价值合计",
]

_ELLIPSIS = "……"


def _norm(v: object) -> str:
    """去掉全部空白（源模板行标签带缩进与「4. 期末余额」式空格）。"""
    return re.sub(r"\s+", "", str(v or ""))


def _section(variant: str) -> dict:
    path, section_number, _ = FIX._TARGETS[variant]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return next(
        s for s in doc["sections"] if str(s.get("section_number")) == section_number
    )


def _main_table(variant: str) -> dict:
    tables = _section(variant).get("tables") or []
    assert [t.get("name") for t in tables] == [T_MAIN], tables
    return tables[0]


def _src_rows(sheet: str, first: int, last: int) -> list[str]:
    wb = openpyxl.load_workbook(_SRC_XLSX, data_only=True)
    assert sheet in wb.sheetnames, wb.sheetnames
    ws = wb[sheet]
    return [_norm(ws.cell(r, 1).value) for r in range(first, last + 1)]


# ───────────────────── Property 7：幂等与零欠账 ─────────────────────


def test_check_passes_both_variants():
    for variant in ("listed", "soe"):
        _changes, warnings, errs = FIX._runner(variant, dry_run=True, check=True)
        assert not errs, f"{variant} 结构欠账：{errs}"
        assert not warnings, f"{variant} 告警：{warnings}"


def test_templates_parse():
    for variant in ("listed", "soe"):
        path, _sec, _fn = FIX._TARGETS[variant]
        json.loads(Path(path).read_text(encoding="utf-8"))


# ───────────────────── Property 1：列定义表态且对齐 headers ─────────────────────


def test_listed_columns():
    tbl = _main_table("listed")
    cols = tbl.get("columns") or []
    assert [c.get("key") for c in cols] == _LISTED_KEYS, cols
    assert [c.get("label") for c in cols] == tbl["headers"], "columns.label 须逐字等于 headers"
    assert cols[0].get("is_label") and cols[0].get("flat"), "首列须 is_label + flat"
    assert all(c.get("format") == "amount" for c in cols[1:]), "类别列与合计列须 format=amount"
    assert not tbl.get("_column_groups"), "单级表头不得残留 _column_groups"
    assert str(tbl.get("guidance") or "").strip(), "上市缺 guidance"


def test_soe_columns():
    tbl = _main_table("soe")
    cols = tbl.get("columns") or []
    assert [c.get("key") for c in cols] == _SOE_KEYS, cols
    assert [c.get("label") for c in cols] == tbl["headers"]
    assert [c.get("label") for c in cols] == [
        "项目", "期初余额", "本期增加", "本期减少", "期末余额",
    ]
    assert cols[0].get("is_label") and cols[0].get("flat")
    assert all(c.get("format") == "amount" for c in cols[1:])
    assert not tbl.get("_column_groups"), (
        "单级表头必须 flat，否则 `本期增加`/`本期减少` 会被反猜出凭空「本期」父表头"
    )
    assert str(tbl.get("guidance") or "").strip(), "国企缺 guidance"


# ───────────────── Property 2：`……` 列头已展开且不复活 ─────────────────


def test_ellipsis_absent_from_headers_and_labels():
    for variant in ("listed", "soe"):
        tbl = _main_table(variant)
        assert _ELLIPSIS not in tbl["headers"], f"{variant} headers 残留 `……` 占位列头"
        labels = [c.get("label") for c in tbl.get("columns") or []]
        assert _ELLIPSIS not in labels, f"{variant} columns.label 残留 `……`"


def test_listed_fifth_column_is_other():
    """源模板 F6 是 `……`，须展开为底稿默认分类第 4 类 `其他`（载荷推的就是它）。"""
    tbl = _main_table("listed")
    assert tbl["headers"][4] == "其他"
    wb = openpyxl.load_workbook(_SRC_XLSX, data_only=True)
    ws = wb[_SHEET_LISTED]
    assert _norm(ws.cell(6, 5).value) == _ELLIPSIS, (
        "源模板第 5 列不再是 `……` —— 展开依据已变，需重新确权"
    )


# ─────────── Property 4：行集与源 xlsx 一致 + `……` 行保留 ───────────


def test_listed_rows_match_source_xlsx():
    """上市 39 行四层（源 xlsx 行 7~45），空白归一后逐行相等。"""
    rows = _main_table("listed").get("rows") or []
    tpl = [_norm(r.get("label")) for r in rows]
    src = _src_rows(_SHEET_LISTED, 7, 45)
    assert len(src) == 39, len(src)
    assert tpl == src, f"上市行集漂移\n模板={tpl}\n源={src}"


def test_listed_keeps_six_ellipsis_rows():
    """🔴 正向断言：`……` 作**行**是真实可扩行（参与 sumOf），不得被当占位删除。"""
    rows = _main_table("listed").get("rows") or []
    hits = [i for i, r in enumerate(rows) if _norm(r.get("label")) == _ELLIPSIS]
    assert len(hits) == 6, f"上市 `……` 可扩行应为 6 行，实测 {len(hits)}：{hits}"
    # 三层（原值/折旧/减值）× 增减两处
    assert hits == [5, 10, 17, 22, 29, 34], hits


def test_soe_rows_match_source_xlsx():
    """国企 25 行五层（源 xlsx 行 7~31），且五个层合计行标 is_total。"""
    rows = _main_table("soe").get("rows") or []
    tpl = [_norm(r.get("label")) for r in rows]
    src = _src_rows(_SHEET_SOE, 7, 31)
    assert len(src) == 25, len(src)
    assert tpl == src, f"国企行集漂移\n模板={tpl}\n源={src}"
    totals = [_norm(r.get("label")) for r in rows if r.get("is_total")]
    assert totals == [_norm(x) for x in _SOE_LAYER_TOTALS], totals


def test_no_header_label_fake_rows():
    for variant in ("listed", "soe"):
        rows = _main_table(variant).get("rows") or []
        assert not any(r.get("row_type") == "header_label" for r in rows), variant
        assert not any(
            "可无限量添加行" in _norm(r.get("label")) for r in rows
        ), f"{variant} 残留占位说明行"


# ───────────────────── 前后端键对齐（seed ↔ 推送同键） ─────────────────────


def test_frontend_payload_keys_align():
    src = _FE_PAYLOAD.read_text(encoding="utf-8")
    assert "H8_NOTE_TEXT_TITLES" in src, "缺 `_note_texts` 中文标题映射"
    assert "buildH8NoteTexts" in src
    for key in _SOE_KEYS:
        assert f"key: '{key}'" in src, f"前端国企缺列 key {key}"
    # 上市列 key = 类别名本身（`key: c.label`）
    assert "key: c.label" in src, "上市列 key 须取类别名本身（与模板 seed 同键）"
    assert "out._note_texts" in src, "_note_texts 必须挂在 sub_table_data 内"


def test_frontend_listed_default_categories_match_template_headers():
    """底稿默认分类 = 模板列（`其他` 即原 `……`），任一侧改动都会打红。"""
    src = _FE_LISTED_MODEL.read_text(encoding="utf-8")
    block = src.split("H8_LISTED_DEFAULT_CATEGORIES", 1)[1].split("] as const", 1)[0]
    labels = re.findall(r"label:\s*'([^']+)'", block)
    assert labels == _LISTED_KEYS[1:-1], labels


def test_frontend_soe_layer_titles_match_template_totals():
    src = _FE_SOE_MODEL.read_text(encoding="utf-8")
    block = src.split("H8_SOE_LAYER_META", 1)[1].split("\n}", 1)[0]
    titles = re.findall(r"title:\s*'([^']+)'", block)
    assert titles == _SOE_LAYER_TOTALS, titles
    # 推导层（净值/账面价值）增减列填「——」→ movementNa
    assert block.count("movementNa: true") == 2, block


def test_section_numbers():
    assert FIX.LISTED_SECTION == "五、25"
    assert FIX.SOE_SECTION == "八、26"
    assert _section("listed").get("section_title") == T_MAIN
    assert _section("soe").get("section_title") == T_MAIN


def test_soe_has_no_text_sections():
    """国企源 xlsx 只有表格无说明段 → `text_sections=[]` 是正确状态，禁凭空补。"""
    assert not (_section("soe").get("text_sections") or [])


# ───────────────────── 反向自检（防守卫空转） ─────────────────────


def test_reverse_self_check_missing_columns():
    from _note_structure_kit import validate_section

    broken = {
        "tables": [
            {"name": T_MAIN, "headers": ["项目"], "rows": [], "guidance": "x"}
        ]
    }
    errs = validate_section(broken, [T_MAIN])
    assert any("缺 columns" in e for e in errs), errs


def test_reverse_self_check_normalizer():
    """`_norm` 必须能把源模板的缩进/内嵌空格归一，否则行集比对恒绿。"""
    assert _norm("    4. 期末余额") == "4.期末余额"
    assert _norm("其中：土地") == "其中：土地"
    assert _norm(None) == ""
