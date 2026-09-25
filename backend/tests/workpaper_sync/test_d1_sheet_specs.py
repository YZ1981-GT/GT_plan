# -*- coding: utf-8 -*-
"""D1 sheet 层声明判据（Tasks 15 / 25 / 26）。

spec: d1-sync-row-table-engine-and-d1-coverage
Requirements 2.1 / 2.2 / 5.1 / 5.4 / 5.7 / 5.8 / 11.1 / 11.2 / 11.3 / 11.7

═══ 判据面 ═══

1. **声明 ≡ 模板实测几何**（禁推演铁律）：逐 sheet 用 openpyxl 直读权威模板，断言声明的
   header_row / first_data_row / last_data_row / footer_row / footer_marker / formula_columns /
   formula_templates 与模板逐字一致。声明漂移即红。
2. **D1-3 声明 ≡ provider 现状**（Task 15 零回归）。
3. **D1-2 是稳定 key 固定行**（实测推翻 spec 首版的「固定 2 + 动态行」假设）。
4. **D1-4 三区 UUID 列互不相同**（D4-1 主营 W / 其他 X 的实测教训：同列会让行身份串区）。
5. **D1-4 第三区走 static_region**（footer 之下 ⇒ 绕开位移链）且满足 BindingKind 分派铁律
   （table_name/uuid_col 必空、defined_name 必填）。
6. **第三写入方与下游消费方已显式登记**（需求 5.7 / 5.8 的可执行落点）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d1_02_category as D102
from app.services.workpaper_sync import phase5_d1_03_customer as D103
from app.services.workpaper_sync import phase5_d1_04_bad_debt as D104
from app.services.workpaper_sync import phase5_d1_notes_receivable as ENTRY
from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

_TEMPLATE = _BACKEND / "wp_templates" / "D" / "D1 应收票据.xlsx"


@pytest.fixture(scope="module")
def workbook():
    import openpyxl

    return openpyxl.load_workbook(_TEMPLATE, data_only=False)


def _formula_templates_from_template(ws, spec) -> dict[str, list[str]]:
    """从模板读出数据区各列的公式模板（行号归一为 {r}）。"""
    import re

    from openpyxl.utils import get_column_letter

    out: dict[str, list[str]] = {}
    for c in range(1, ws.max_column + 1):
        col = get_column_letter(c)
        tpls: set[str] = set()
        for r in range(spec.first_data_row, spec.last_data_row + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and v.startswith("="):
                tpls.add(re.sub(rf"(?<=[A-Z]){r}\b", "{r}", v))
        if tpls:
            out[col] = sorted(tpls)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 1. 声明 ≡ 模板实测几何（禁推演）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "spec",
    [D103.SPEC_D103, D102.SPEC_D102, D104.SPEC_D104_INDIVIDUAL,
     D104.SPEC_D104_PORTFOLIO, D104.SPEC_D104_NOTETYPE],
    ids=["d1-3", "d1-2", "d1-4-individual", "d1-4-portfolio", "d1-4-notetype"],
)
def test_declared_sheet_exists_in_template(workbook, spec) -> None:
    assert spec.managed_sheet in workbook.sheetnames, (
        f"声明的 sheet 名 {spec.managed_sheet!r} 不在模板 21 张里 —— sheet 名必须逐字实测"
    )


@pytest.mark.parametrize(
    "spec",
    [D103.SPEC_D103, D102.SPEC_D102],
    ids=["d1-3", "d1-2"],
)
def test_footer_marker_matches_template(workbook, spec) -> None:
    """footer marker 必须与模板 A 列该行逐字相等（D1-4 带两全角空格是反面教材）。"""
    ws = workbook[spec.managed_sheet]
    actual = ws.cell(row=spec.footer_row, column=1).value
    assert isinstance(actual, str)
    assert actual.strip() == spec.footer_marker.strip(), (
        f"{spec.managed_sheet} footer R{spec.footer_row} 实测 {actual!r}，声明 {spec.footer_marker!r}"
    )


def test_d104_footer_marker_is_byte_exact(workbook) -> None:
    """🔴 D1-4 footer marker 必须 **codepoint 级**逐字相等（不是 strip 后相等）。

    实测为「合计」+ 一个**半角**空格（0x5408 0x8ba1 0x20），与 D1-2 的纯「合计」、
    D3 的「合计」、D7 的「合   计」都不同。

    🔴 本判据打红过一次真实的推演错误：声明首版据终端输出目测写成「两个全角空格」
    （\\u3000\\u3000），被本判据按 codepoint 打红后改为实测值 —— 目测终端输出不算实测。
    """
    ws = workbook[D104.MANAGED_SHEET_D104]
    actual = ws.cell(row=D104.FOOTER_ROW_D104, column=1).value
    assert actual == D104.FOOTER_MARKER_D104, (
        f"实测 {actual!r}（codepoints {[hex(ord(c)) for c in str(actual)]}）"
        f" vs 声明 {D104.FOOTER_MARKER_D104!r}"
        f"（codepoints {[hex(ord(c)) for c in D104.FOOTER_MARKER_D104]}）"
    )
    # 钉住「不是纯两字」这个易被 strip 掉的事实
    assert actual != "合计", "D1-4 的 marker 带尾部空格，不可与 D1-2 的纯「合计」混用"
    assert [hex(ord(c)) for c in actual] == ["0x5408", "0x8ba1", "0x20"]


@pytest.mark.parametrize(
    "spec",
    [D103.SPEC_D103, D102.SPEC_D102, D104.SPEC_D104_INDIVIDUAL, D104.SPEC_D104_PORTFOLIO],
    ids=["d1-3", "d1-2", "d1-4-individual", "d1-4-portfolio"],
)
def test_formula_columns_match_template(workbook, spec) -> None:
    """声明的 formula_columns 必须 ⊆ 模板数据区实测有公式的列，且公式模板逐字相等。"""
    ws = workbook[spec.managed_sheet]
    actual = _formula_templates_from_template(ws, spec)
    for col in spec.formula_columns:
        assert col in actual, (
            f"{spec.managed_sheet} 声明 {col} 列为 formula，但模板数据区 "
            f"R{spec.first_data_row}-{spec.last_data_row} 该列无公式；实测有公式的列={sorted(actual)}"
        )
        declared = spec.formula_templates.get(col)
        if declared:
            assert declared in actual[col], (
                f"{spec.managed_sheet} {col} 列公式模板不符：声明 {declared!r}，实测 {actual[col]}"
            )


@pytest.mark.parametrize(
    "spec",
    [D103.SPEC_D103, D102.SPEC_D102],
    ids=["d1-3", "d1-2"],
)
def test_header_texts_match_template(workbook, spec) -> None:
    """字段 7 元组的 header_text 必须与模板表头行逐字相等（单级表头的两张）。"""
    ws = workbook[spec.managed_sheet]
    assert spec.header_row is not None
    for column_key, column, _mode, _vt, _json, header_text, _group in spec.field_specs:
        from openpyxl.utils import column_index_from_string

        actual = ws.cell(row=spec.header_row, column=column_index_from_string(column)).value
        assert isinstance(actual, str) and actual.strip() == header_text, (
            f"{spec.managed_sheet} {column}{spec.header_row} 实测 {actual!r}，"
            f"声明 {header_text!r}（字段 {column_key}）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. D1-3 声明 ≡ provider 现状（Task 15 零回归）
# ═══════════════════════════════════════════════════════════════════════════


def test_d103_spec_equals_provider_constants() -> None:
    spec = D103.SPEC_D103
    assert spec.managed_sheet == ENTRY.MANAGED_SHEET
    assert spec.sheet_key == ENTRY.SHEET_KEY
    assert spec.table_key == ENTRY.ROWS_TABLE_KEY
    assert spec.first_data_row == ENTRY.FIRST_DATA_ROW
    assert spec.last_data_row == ENTRY.LAST_DATA_ROW
    assert spec.footer_row == ENTRY.FOOTER_ROW
    assert spec.uuid_col == ENTRY.UUID_COL
    assert spec.store_item_id == ENTRY.STORE_ITEM_ID
    assert spec.row_identity_key == ENTRY.ROW_IDENTITY_STORE_KEY
    # 引擎现算 mask ≡ provider 手写 mask
    assert spec.formula_mask == tuple(ENTRY.FORMULA_MASK)
    # 字段投影掉第 7 位 ≡ provider 的 6 元组
    assert tuple(r[:6] for r in managed_field_specs(spec)) == tuple(ENTRY.MANAGED_FIELD_SPECS)


# ═══════════════════════════════════════════════════════════════════════════
# 3. D1-2 是稳定 key 固定行（实测推翻 spec 首版假设）
# ═══════════════════════════════════════════════════════════════════════════


def test_d102_is_stable_key_fixed_rows_not_dynamic(workbook) -> None:
    """🔴 实测：D1-2 只有 3 个固定票据种类行、零动态行 ⇒ row_identity_key='key'（D4-6 范式）。"""
    spec = D102.SPEC_D102
    assert spec.row_identity_key == "key", (
        "D1-2 是稳定 key 固定行（3 个写死的票据种类），不是 UUID 动态行 —— "
        "spec 首版的「固定 2 + 动态行」假设已被 openpyxl 实测推翻"
    )
    # 仍是 excel_table binding 且仍注入 UUID 列（判据是「有没有行维度」而非「行会不会变」）
    assert spec.binding_kind is BindingKind.excel_table
    assert spec.uuid_col == "L"
    # 数据区恰好 3 行，与三个固定 key 一一对应
    assert spec.last_data_row - spec.first_data_row + 1 == 3
    assert len(D102.FIXED_ROW_KEYS_D102) == 3
    ws = workbook[spec.managed_sheet]
    for key, row, label in D102.FIXED_ROW_KEYS_D102:
        actual = ws.cell(row=row, column=1).value
        assert actual == label, f"{key} 声明行 R{row} 标签 {label!r}，实测 {actual!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 4~5. D1-4 三区：UUID 列互不相同 + 第三区 static_region
# ═══════════════════════════════════════════════════════════════════════════


def test_d104_three_regions_have_distinct_uuid_columns() -> None:
    """🔴 同 sheet 多区必须各用不同 UUID 列（同列 ⇒ 行身份串区，回写落错区块）。"""
    cols = [s.uuid_col for s in D104.SPECS_D104 if s.uuid_col]
    assert len(cols) == len(set(cols)), f"三区 UUID 列重复：{cols}"
    assert D104.SPEC_D104_INDIVIDUAL.uuid_col == "O"
    assert D104.SPEC_D104_PORTFOLIO.uuid_col == "P"
    # 第三区走 static_region ⇒ 无 UUID 列
    assert D104.SPEC_D104_NOTETYPE.uuid_col == ""


def test_d104_three_regions_have_distinct_table_keys_and_store_items() -> None:
    keys = [s.table_key for s in D104.SPECS_D104]
    items = [s.store_item_id for s in D104.SPECS_D104]
    assert len(keys) == len(set(keys)), f"table_key 重复：{keys}"
    assert len(items) == len(set(items)), f"store_item_id 重复：{items}"
    assert set(items) == {
        "D1-bd-individual-rows", "D1-bd-portfolio-rows", "D1-notetype-rows"
    }


def test_d104_regions_row_ranges_match_template_sum_intervals(workbook) -> None:
    """三区行范围必须与模板父行 SUM 区间/行标签逐字吻合（禁推演）。"""
    ws = workbook[D104.MANAGED_SHEET_D104]
    # 区一父行 R12 = SUM(B13:B16)
    assert ws.cell(row=12, column=1).value == "按单项计提"
    assert ws.cell(row=12, column=2).value == "=SUM(B13:B16)"
    assert (D104.SPEC_D104_INDIVIDUAL.first_data_row,
            D104.SPEC_D104_INDIVIDUAL.last_data_row) == (13, 16)
    # 区二父行 R17 = SUM(B18:B21)
    assert ws.cell(row=17, column=1).value == "按组合计提"
    assert ws.cell(row=17, column=2).value == "=SUM(B18:B21)"
    assert (D104.SPEC_D104_PORTFOLIO.first_data_row,
            D104.SPEC_D104_PORTFOLIO.last_data_row) == (18, 21)
    # 区三 R23/24 两个票据种类小计，且在 footer R22 **之下**
    assert ws.cell(row=23, column=1).value == "银行承兑汇票小计"
    assert ws.cell(row=24, column=1).value == "商业承兑汇票小计"
    assert (D104.SPEC_D104_NOTETYPE.first_data_row,
            D104.SPEC_D104_NOTETYPE.last_data_row) == (23, 24)
    assert D104.SPEC_D104_NOTETYPE.first_data_row > D104.FOOTER_ROW_D104, (
        "第三区应在 footer 之下 —— 这是它必须走 static_region 的依据"
    )


def test_d104_notetype_region_is_static_region_with_binding_kind_rules() -> None:
    """第三区 static_region 必须满足 BindingKind 分派铁律：table_name/uuid_col 必空、defined_name 必填。"""
    spec = D104.SPEC_D104_NOTETYPE
    assert spec.binding_kind is BindingKind.static_region
    assert spec.table_name == "", "static_region 的 table_name 必空"
    assert spec.uuid_col == "", "static_region 的 uuid_col 必空"
    assert spec.defined_name, "static_region 的 defined_name 必填"
    assert spec.row_identity_key == "", "static_region 无行维度"


def test_d104_notetype_rejects_row_projection() -> None:
    """static_region 无行身份 ⇒ 走行表投影必 fail closed（不会被误当动态行接入）。"""
    from app.services.workpaper_sync import phase5_row_table_sheet as ENGINE

    with pytest.raises(ENGINE.RowTableStorePayloadError, match="static_region"):
        list(ENGINE.iter_store_rows(D104.SPEC_D104_NOTETYPE, [{"rowId": "x"}]))


# ═══════════════════════════════════════════════════════════════════════════
# 6. 第三写入方与下游消费方已显式登记
# ═══════════════════════════════════════════════════════════════════════════


def test_third_writer_store_key_is_declared() -> None:
    """需求 5.7 / P17：有第三个写入方的 store 键必须显式登记（供宿主定序与判据引用）。"""
    assert "D1-bd-portfolio-rows" in D104.THIRD_WRITER_STORE_KEYS
    reason = D104.THIRD_WRITER_STORE_KEYS["D1-bd-portfolio-rows"]
    assert "syncReversalToD14" in reason, "登记须指名具体写入方，否则无法定序"


def test_downstream_consumers_are_declared() -> None:
    """需求 5.8 / P18：三键的下游 computed 消费方必须登记（零回归不得只验自身读回等值）。"""
    consumers = D104.DOWNSTREAM_CONSUMERS_D104
    assert len(consumers) >= 4
    joined = " ".join(consumers)
    for expected in ("useD1EclCalc", "parseD1_4Rows", "useD1Adjudication", "progressKeys"):
        assert expected in joined, f"下游消费方清单缺 {expected}"
