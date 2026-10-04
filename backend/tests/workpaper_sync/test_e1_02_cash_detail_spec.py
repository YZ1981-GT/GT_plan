# -*- coding: utf-8 -*-
"""E1-2 canary 声明判据（E1 Tasks 2 / 8；E1-P2 / E1-P3）。

spec: e1-sync-coverage-and-first-canary · Requirements 1.1 / 1.3 / 2.1 / 2.2

═══ 判据面 ═══

* **E1-P2 键名实证**：`store_item_id` 逐字等于前端实测值。含 spec 要求的两条变异：
  ①`E1-cash-detail-rows` → `E1-2-rows` ⇒ 投影恒空必红
  ②`cash-count` → `cashcount`（一个连字符之差，六次事故背书）⇒ 必红
* **E1-P3 binding_kind 三元组**：动态行表（不是 static_region）。含 spec 的**自省变异**：
  把判据改回公式数阈值（`< 10 ⇒ static_region`）⇒ 会把 E1-9/10/11 三张全判 static_region，
  必红 —— 这复现的正是本 spec 首版裁决 H3 的错法。
* **声明 ≡ 模板实测几何**（禁推演）：两级表头 / 数据区 / footer marker / 公式列与模板逐字一致。
* **两处推翻 spec 隐含假设的事实被钉住**：
  ①行身份字段名是 `id` 不是 `rowId`（照抄 D 类会 fail-closed 打挂整个 entry）
  ②`fixed-rmb` 固定行 + 动态行混合身份（同在 `id` 字段，无需拆区）
* **footer 下 static 行不被误纳入受管区**（R23，与 D1-4 第三区同型）。
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_e1_02_cash_detail as E102
from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend" / "src"
_COMPOSABLE = _FRONTEND / "components" / "workpaper" / "composables" / "useE1CashDetail.ts"


@pytest.fixture(scope="module")
def e1_first_volume():
    import openpyxl

    cands = [p for p in glob.glob(str(_BACKEND / "wp_templates" / "E" / "*.xlsx"))
             if "E1-1至E1-11" in p]
    assert cands, "E1 第一册模板未找到"
    return openpyxl.load_workbook(cands[0], data_only=False)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P2：键名实证 + 两条变异
# ═══════════════════════════════════════════════════════════════════════════


def test_e1p2_store_item_id_matches_frontend_verbatim() -> None:
    """store 键必须与前端 composable 里的 STORAGE_KEY 逐字相等（按值 grep，不推演）。"""
    assert _COMPOSABLE.exists(), f"前端 composable 缺失：{_COMPOSABLE}"
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert f"const STORAGE_KEY = '{E102.STORE_ITEM_ID_E102}'" in src, (
        f"声明的 store 键 {E102.STORE_ITEM_ID_E102!r} 与前端 STORAGE_KEY 不符 —— "
        "E1 有四种命名风格，键名必须按值 grep 实证"
    )


def test_e1p2_mutation_sheet_code_style_key_is_not_used() -> None:
    """变异①：若把键写成编号风格 `E1-2-rows`，前端根本不写该键 ⇒ 投影恒空。"""
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert "'E1-2-rows'" not in src, (
        "前端并不使用 E1-2-rows（编号风格）—— 若声明用它，OO 投影会恒空（E1-P2 变异①）"
    )


def test_e1p2_mutation_hyphen_drop_is_a_different_key() -> None:
    """变异②：`cash-detail` → `cashdetail` 是**另一个键**（一个连字符之差，六次事故背书）。

    E1 实测同张 sheet 上并存 `E1-cash-count-fx-rows` 与 `E1-cashcount-audit-note-fx`
    两种风格 ⇒ 连字符差异是真实存在的陷阱，不是假想。
    """
    declared = E102.STORE_ITEM_ID_E102
    mutated = declared.replace("cash-detail", "cashdetail")
    assert mutated != declared
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert f"'{mutated}'" not in src, f"{mutated!r} 不是前端使用的键"


# ═══════════════════════════════════════════════════════════════════════════
# E1-P3：binding_kind 三元组 + 自省变异
# ═══════════════════════════════════════════════════════════════════════════


def test_e1p3_binding_kind_from_frontend_triple() -> None:
    """三元组判据：store 键存在 + addRow/removeRow 信号 + composable 归属 ⇒ excel_table。"""
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert "function addRow(" in src, "缺 addRow 信号"
    assert "function removeRow(" in src, "缺 removeRow 信号"
    assert E102.SPEC_E102.binding_kind is BindingKind.excel_table, (
        "有 addRow/removeRow 双信号 ⇒ 必须是动态行表 excel_table，不得判 static_region"
    )
    assert E102.SPEC_E102.uuid_col, "动态行表必须注入 UUID 列"
    assert E102.SPEC_E102.table_name, "动态行表必须有 Excel Table displayName"


def test_e1p3_introspective_mutation_formula_count_threshold_is_wrong(e1_first_volume) -> None:
    """🔴 **自省变异**（spec Task 4 第 3 条）：把 binding_kind 判据改回「公式数 < 10 ⇒
    static_region」会把 E1-9/E1-10/E1-11 三张**全部**误判成 static_region。

    这复现的正是本 spec 首版裁决 H3 的错法 —— 判据必须能打红自己的历史错误，
    否则下一轮原样复发。实证：三张各 7 公式，而 E1-9/E1-10 实际是动态行表
    （有 `-rows` 键），只有 E1-11 是真 static_region（零 `-rows` 键）。
    """
    wb = e1_first_volume
    seven_formula_sheets = {}
    for name in ("银行存单盘点表E1-9", "已开立银行账户清单核对表E1-10", "银行账户情况承诺E1-11"):
        ws = wb[name]
        cnt = sum(
            1 for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("=")
        )
        seven_formula_sheets[name] = cnt

    # 三张公式数都 < 10 ⇒ 错误阈值会把三张全判静态
    assert all(c < 10 for c in seven_formula_sheets.values()), seven_formula_sheets
    would_be_static = [n for n, c in seven_formula_sheets.items() if c < 10]
    assert len(would_be_static) == 3, (
        "公式数阈值会把三张全判 static_region —— 这正是首版 H3 的错法；"
        "正确判据是前端三元组（E1-9/E1-10 有 -rows 键 ⇒ 动态行表）"
    )

    # 反证：E1-9 / E1-10 的前端确实有 -rows 键（⇒ 它们不是 static_region）
    #
    # 🔴 E1-9 的键是**模板化拼接** `` `E1-cash-count-${variant}-rows` ``（variant ∈ rmb|fx|cert）
    #    —— 按字面量 grep `E1-cash-count-cert-rows` **查不到**，必须按前缀 + 拼接形态查。
    #    这正是 spec 警告的 style ③ 陷阱（首版因此误记「useE1CashCount 无 -rows 键」）。
    comp_dir = _FRONTEND / "components" / "workpaper" / "composables"
    all_src = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in comp_dir.glob("useE1*.ts")
    )
    assert "`E1-cash-count-${variant}-rows`" in all_src, (
        "E1-9/E1-7/E1-8 的键是模板化拼接 `E1-cash-count-${variant}-rows` ⇒ 它们是动态行表"
    )
    assert "E1-account-list-rows" in all_src, "E1-10 应有 -rows 键 ⇒ 动态行表"
    # 🔴 连字符陷阱实证：同一文件里并存带连字符的新键与无连字符的 legacy 兜底键
    assert "E1-cashcount-fx-summary-fx" in all_src, (
        "legacy 兜底键 E1-cashcount-fx-summary-fx（无连字符 + 双 -fx 后缀）实测存在 —— "
        "投影须能读到历史底稿，不得只认新键"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 声明 ≡ 模板实测几何（禁推演）
# ═══════════════════════════════════════════════════════════════════════════


def test_sheet_exists_in_first_volume(e1_first_volume) -> None:
    assert E102.MANAGED_SHEET_E102 in e1_first_volume.sheetnames


def test_footer_marker_and_row_match_template(e1_first_volume) -> None:
    ws = e1_first_volume[E102.MANAGED_SHEET_E102]
    actual = ws.cell(row=E102.FOOTER_ROW_E102, column=1).value
    assert actual == E102.FOOTER_MARKER_E102, (
        f"footer R{E102.FOOTER_ROW_E102} 实测 {actual!r}，声明 {E102.FOOTER_MARKER_E102!r}"
    )


def test_two_level_header_texts_match_template(e1_first_volume) -> None:
    """两级表头：A/H/I/J 取 R13 组标题，B..G 取 R14 叶子（逐格实测）。"""
    from openpyxl.utils import column_index_from_string

    ws = e1_first_volume[E102.MANAGED_SHEET_E102]
    for column_key, column, _mode, _vt, _json, header_text, group_cell in E102.FIELD_SPECS_E102:
        row = E102.HEADER_LEAF_ROW_E102 if group_cell else E102.HEADER_GROUP_ROW_E102
        actual = ws.cell(row=row, column=column_index_from_string(column)).value
        assert isinstance(actual, str) and actual.strip() == header_text, (
            f"{column}{row} 实测 {actual!r}，声明 {header_text!r}（字段 {column_key}）"
        )


def test_formula_columns_and_templates_match_template(e1_first_volume) -> None:
    """E/G/I 三列公式模板逐字相等；G 是乘法、I 是乘加混合（引擎首次遇非纯加减）。"""
    import re

    from openpyxl.utils import column_index_from_string

    ws = e1_first_volume[E102.MANAGED_SHEET_E102]
    for col, tpl in E102.FORMULA_TEMPLATES_E102.items():
        found = False
        for r in range(E102.FIRST_DATA_ROW_E102, E102.LAST_DATA_ROW_E102 + 1):
            v = ws.cell(row=r, column=column_index_from_string(col)).value
            if isinstance(v, str) and v.startswith("="):
                normalised = re.sub(rf"(?<=[A-Z]){r}\b", "{r}", v)
                assert normalised == tpl, (
                    f"{col}{r} 实测 {v!r} → 归一 {normalised!r}，声明 {tpl!r}"
                )
                found = True
        assert found, f"{col} 列在数据区无公式，但声明为 formula"
    # 钉住非纯加减的两条
    assert "*" in E102.FORMULA_TEMPLATES_E102["G"], "G 应为乘法（=E*F）"
    assert "*" in E102.FORMULA_TEMPLATES_E102["I"] and "+" in E102.FORMULA_TEMPLATES_E102["I"], (
        "I 应为乘加混合（=G+H*F）"
    )


def test_prefilled_currency_rows_match_template(e1_first_volume) -> None:
    ws = e1_first_volume[E102.MANAGED_SHEET_E102]
    for row, label in E102.PREFILLED_CURRENCY_ROWS_E102:
        actual = ws.cell(row=row, column=1).value
        assert actual == label, f"R{row} 实测 {actual!r}，声明 {label!r}"


def test_formula_mask_is_engine_computed() -> None:
    """mask 由引擎按 formula_columns 现算（provider 不手写字面量）。"""
    spec = E102.SPEC_E102
    assert spec.formula_mask == ("E15:E21", "G15:G21", "I15:I21")


def test_managed_field_specs_are_column_ordered() -> None:
    specs = managed_field_specs(E102.SPEC_E102)
    cols = [row[1] for row in specs]
    assert cols == sorted(cols, key=lambda c: (len(c), c)), f"字段未按列序：{cols}"
    assert len(specs) == 10


# ═══════════════════════════════════════════════════════════════════════════
# 两处推翻 spec 隐含假设的事实
# ═══════════════════════════════════════════════════════════════════════════


def test_row_identity_key_is_id_not_rowid() -> None:
    """🔴 实测行身份字段名是 `id`；照抄 D 类的 `rowId` 会 fail-closed 打挂整个 entry。"""
    assert E102.ROW_IDENTITY_STORE_KEY_E102 == "id"
    assert E102.SPEC_E102.row_identity_key == "id"
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert "id: generateRowId()" in src, "前端行对象的身份字段应是 id"
    # 反证：行**对象字面量**里没有 rowId 字段（`rowId` 只作函数参数名出现，
    # 如 removeRow(rowId: string) / updateCell(rowId, …)，那不是落库字段）。
    assert "rowId: " not in src.replace("rowId: string", ""), (
        "行对象字面量里不应有 rowId 字段 —— 落库身份是 id"
    )
    # 正向：查行身份的读取处用的是 r.id
    assert "r.id ===" in src or "String(r.id" in src, "读行身份应走 r.id"


def test_fixed_row_and_dynamic_rows_share_identity_field() -> None:
    """🔴 混合身份：固定行 `fixed-rmb` 与动态行 `cash-<uuid>` 同在 `id` 字段，无需拆区。"""
    src = _COMPOSABLE.read_text(encoding="utf-8")
    assert f"rowId === '{E102.FIXED_ROW_KEY_E102}'" in src, (
        f"前端应硬挡删除固定行 {E102.FIXED_ROW_KEY_E102}"
    )
    assert "`cash-${crypto.randomUUID()}`" in src or "cash-" in src, "动态行 id 前缀应为 cash-"
    # 固定行对应模板 R15 人民币
    assert E102.PREFILLED_CURRENCY_ROWS_E102[0] == (15, "人民币")


def test_footer_below_static_row_is_declared_html_only(e1_first_volume) -> None:
    """🔴 R23「其中：存放在境外的款项总额」在 footer 之下 ⇒ 登记 HTML-only，不纳入受管区。"""
    ws = e1_first_volume[E102.MANAGED_SHEET_E102]
    assert ws.cell(row=23, column=1).value == "其中：存放在境外的款项总额"
    assert E102.HTML_ONLY_ROWS_E102, "footer 下的 static 行必须显式登记原因"
    row_no, label, reason = E102.HTML_ONLY_ROWS_E102[0]
    assert row_no == 23
    assert row_no > E102.FOOTER_ROW_E102, "该行应在 footer 之下"
    assert "static_region" in reason, "登记须说明将来受管的正确路径"
    # 受管区不含它
    assert E102.LAST_DATA_ROW_E102 < E102.FOOTER_ROW_E102 < row_no
