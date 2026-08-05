"""test_e0_send_list_source_facts — 源模板事实固化（openpyxl 直读，三向比对）

Wave 1 Task 1 of spec `e0-send-list-dedicated-components`.
覆盖 Property 1/2/3/10/11/12/17/24/25。

核心目的：把源模板的物理事实用守卫钉死 → 后续实现全以本文件为裁决者。
三向比对 = 源 xlsx ↔ manifest ↔ E0.yaml（dynamic_table）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

# ──────────────────────── 路径常量 ────────────────────────────────────────────

_BACKEND = Path(__file__).resolve().parents[1]
_E0_TEMPLATE = _BACKEND / "wp_templates" / "E" / "E0 货币资金 - 函证（Leap应对措施-函证）.xlsx"
_MANIFEST = _BACKEND / "data" / "e0_send_list_source_manifest.json"
_E0_YAML = _BACKEND / "data" / "ledger_adapters" / "wp_render_schema" / "generated" / "E0.yaml"
_WP_CODE_OVERRIDES = _BACKEND / "app" / "data" / "wp_code_overrides.json"

_SEND_LIST_SHEETS = [
    "货币资金发函记录表E0-3",
    "借款发函记录表E0-4",
    "应付银行承兑汇票发函记录表E0-5",
    "理财产品发函记录表E0-6",
]

# 源模板逐字列标签（openpyxl 实测 2026-08-03 确认）
_EXPECTED_HEADERS: dict[str, list[str]] = {
    "货币资金发函记录表E0-3": [
        "所属科目", "索引号", "报表截止日", "开户银行", "是否函证", "账户名称",
        "银行账号", "币种", "利率(%)", "账户类型", "账户余额（原币）",
        "是否属于资金归集（资金池或其他资金管理）账户", "起始日期", "终止日期",
        "是否存在冻结、担保或其他使用限制（如是，请注明）", "备注",
    ],
    "借款发函记录表E0-4": [
        "所属科目", "索引号", "报表截止日", "开户银行", "是否函证",
        "借款人名称", "借款账号", "币种", "余额", "借款日期", "到期日期",
        "利率(%)", "抵(质)押品/担保人", "备注", "借款类型", "期末应付利息",
    ],
    "应付银行承兑汇票发函记录表E0-5": [
        "索引号", "报表截止日", "开户银行", "银行承兑汇票号码",
        "结算账户账号", "币种", "票面金额", "出票日", "到期日", "抵（质）押品",
    ],
    "理财产品发函记录表E0-6": [
        "索引号", "报表截止日", "开户行名称及收件人", "产品名称",
        "产品类型（封闭式/开放式）", "币种", "持有份额", "产品净值",
        "购买日", "到期日", "是否被用于担保或存在其他使用限制",
    ],
}

# 列数
_EXPECTED_COL_COUNTS = {"E0-3": 16, "E0-4": 16, "E0-5": 10, "E0-6": 11}

# dims / print_area / 数据区行范围
# 注意：openpyxl 的 ws.dimensions 包含有格式化的空列（如列宽/隐藏设置），
# 实测四张表都到 AW 列（因为编制信息区占位列宽延伸）。
# 这里用 max_row 校验行范围即可，列范围以 print_area 为准。
_EXPECTED_MAX_ROW = {
    "货币资金发函记录表E0-3": 26,
    "借款发函记录表E0-4": 20,
    "应付银行承兑汇票发函记录表E0-5": 20,
    "理财产品发函记录表E0-6": 20,
}
_EXPECTED_PRINT_AREA = {
    "货币资金发函记录表E0-3": "$A$1:$P$29",
    "借款发函记录表E0-4": "$A$1:$P$21",
    "应付银行承兑汇票发函记录表E0-5": "$A$1:$J$21",
    "理财产品发函记录表E0-6": "$A$1:$K$20",
}
_DATA_RANGE_START = 6
_DATA_RANGE_END = {
    "货币资金发函记录表E0-3": 26,
    "借款发函记录表E0-4": 20,
    "应付银行承兑汇票发函记录表E0-5": 20,
    "理财产品发函记录表E0-6": 20,
}

# ──────────────────────── fixtures ────────────────────────────────────────────


@pytest.fixture(scope="module")
def e0_workbook():
    # 跳过 ~$ 锁文件
    lock = _E0_TEMPLATE.parent / f"~${_E0_TEMPLATE.name}"
    if lock.exists():
        pytest.skip(f"源模板被锁定（WPS/Excel 打开中）：{lock}")
    if not _E0_TEMPLATE.exists():
        pytest.skip(f"真实模板缺失：{_E0_TEMPLATE}")
    wb = openpyxl.load_workbook(str(_E0_TEMPLATE), data_only=False)
    yield wb
    wb.close()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def e0_yaml() -> dict:
    import yaml
    return yaml.safe_load(_E0_YAML.read_text(encoding="utf-8"))


# ──────────────────────── 1. 四张 sheet 的 tab 名存在且可见 ───────────────────


def test_four_send_list_sheets_exist_and_visible(e0_workbook):
    for sn in _SEND_LIST_SHEETS:
        assert sn in e0_workbook.sheetnames, f"源模板缺少 tab: {sn}"
        assert e0_workbook[sn].sheet_state == "visible", f"{sn} 应为 visible"


# ──────────────────────── 2. 表头行号 = 5，逐字标签一致 ──────────────────────


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_header_row_labels_verbatim(e0_workbook, sheet_name):
    ws = e0_workbook[sheet_name]
    expected = _EXPECTED_HEADERS[sheet_name]
    actual = []
    for col in range(1, len(expected) + 1):
        v = ws.cell(row=5, column=col).value
        actual.append(v)
    assert actual == expected, f"{sheet_name} 表头行 5 标签不匹配"


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_column_count(e0_workbook, sheet_name):
    expected_count = len(_EXPECTED_HEADERS[sheet_name])
    ws = e0_workbook[sheet_name]
    # 只数表头行 5 有值的列
    actual = sum(1 for c in range(1, 50) if ws.cell(row=5, column=c).value is not None)
    assert actual == expected_count, f"{sheet_name} 列数 {actual} != {expected_count}"


# ──────────────────────── 3. 隐藏列事实 ─────────────────────────────────────


def test_e03_and_e04_column_e_hidden(e0_workbook):
    """E0-3 与 E0-4 的 E 列（是否函证）在源模板是 hidden。"""
    for sn in ("货币资金发函记录表E0-3", "借款发函记录表E0-4"):
        ws = e0_workbook[sn]
        assert ws.column_dimensions["E"].hidden is True, f"{sn} 的 E 列应为 hidden"


def test_e05_e06_no_hidden_columns(e0_workbook):
    """E0-5 与 E0-6 无任何隐藏列。"""
    for sn in ("应付银行承兑汇票发函记录表E0-5", "理财产品发函记录表E0-6"):
        ws = e0_workbook[sn]
        hidden = [c for c, cd in ws.column_dimensions.items() if cd.hidden]
        assert hidden == [], f"{sn} 不应有隐藏列，实为 {hidden}"


def test_e05_e06_no_is_confirm_in_header(e0_workbook):
    """E0-5 与 E0-6 表头里确实无「是否函证」。"""
    for sn in ("应付银行承兑汇票发函记录表E0-5", "理财产品发函记录表E0-6"):
        ws = e0_workbook[sn]
        headers = [ws.cell(row=5, column=c).value for c in range(1, 20)]
        assert "是否函证" not in headers, f"{sn} 表头不应含「是否函证」"


# ──────────────────────── 反向自检：给 E0-5 加 is_confirm 必红 ────────────────

def test_reverse_check_e05_has_no_confirm_flag():
    """反向自检：如果有人把 is_confirm 塞进 E0-5 的 manifest，这条必红。"""
    m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    fields = [c["field"] for c in m["sheets"]["应付银行承兑汇票发函记录表E0-5"]["cell_columns"].values()]
    assert "is_confirm" not in fields, "E0-5 manifest 不应有 is_confirm"


# ──────────────────────── 4. 数据验证 (DV) 范围 ──────────────────────────────


def test_e03_data_validations(e0_workbook):
    ws = e0_workbook["货币资金发函记录表E0-3"]
    dvs = list(ws.data_validations.dataValidation)
    assert len(dvs) == 1, "E0-3 应恰好有 1 条 DV 规则"
    dv = dvs[0]
    # openpyxl may include surrounding quotes in formula1
    assert "是,否" in str(dv.formula1)
    sqref = str(dv.sqref)
    assert "L6:L26" in sqref and "O6:O26" in sqref


def test_e04_zero_data_validations(e0_workbook):
    ws = e0_workbook["借款发函记录表E0-4"]
    dvs = list(ws.data_validations.dataValidation)
    assert len(dvs) == 0, "E0-4 应无数据验证"


def test_e05_zero_data_validations(e0_workbook):
    ws = e0_workbook["应付银行承兑汇票发函记录表E0-5"]
    dvs = list(ws.data_validations.dataValidation)
    assert len(dvs) == 0, "E0-5 应无数据验证"


def test_e06_data_validation_range(e0_workbook):
    ws = e0_workbook["理财产品发函记录表E0-6"]
    dvs = list(ws.data_validations.dataValidation)
    assert len(dvs) == 1, "E0-6 应恰好有 1 条 DV 规则"
    dv = dvs[0]
    assert "是,否" in str(dv.formula1)
    # 源模板 DV 范围残缺只到 K10（平台侧应整列启用，但这里钉的是源模板事实）
    assert "K6:K10" in str(dv.sqref)


# ──────────────────────── 5. dims / print_area / 数据区 ──────────────────────


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_max_row_and_print_area(e0_workbook, sheet_name):
    ws = e0_workbook[sheet_name]
    assert ws.max_row == _EXPECTED_MAX_ROW[sheet_name], (
        f"{sheet_name} max_row 不匹配: {ws.max_row} != {_EXPECTED_MAX_ROW[sheet_name]}"
    )
    # print_area 格式可能包含 sheet 名引用
    pa = ws.print_area
    # 有些 openpyxl 版本返回 list
    if isinstance(pa, list):
        pa = pa[0] if pa else ""
    expected_pa = _EXPECTED_PRINT_AREA[sheet_name]
    assert expected_pa in str(pa), f"{sheet_name} print_area 不含 {expected_pa}，实为 {pa}"


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_data_area_rows_are_print_skeleton(e0_workbook, sheet_name):
    """数据区行带边框但无值（打印骨架非数据），验证 R3.2。"""
    ws = e0_workbook[sheet_name]
    end_row = _DATA_RANGE_END[sheet_name]
    # 对 E0-3 跳过有公式的行
    if sheet_name == "货币资金发函记录表E0-3":
        # E0-3 R6:R24 有公式（不是空白），R25:R26 才是空白骨架
        for r in range(25, end_row + 1):
            for c in range(1, len(_EXPECTED_HEADERS[sheet_name]) + 1):
                v = ws.cell(row=r, column=c).value
                assert v is None or v == "", (
                    f"E0-3 R{r} col{c} 应为空白打印骨架，实为 {v!r}"
                )
    elif sheet_name == "借款发函记录表E0-4":
        # E0-4 数据区除 R16 G/H=0 外全空
        for r in range(_DATA_RANGE_START, end_row + 1):
            for c in range(1, 17):
                v = ws.cell(row=r, column=c).value
                if r == 16 and c in (7, 8):
                    continue  # 已知残留
                assert v is None or v == "", (
                    f"E0-4 R{r} col{c} 应为空白，实为 {v!r}"
                )
    else:
        # E0-5, E0-6 数据区全空
        for r in range(_DATA_RANGE_START, end_row + 1):
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                assert v is None or v == "", (
                    f"{sheet_name} R{r} col{c} 应为空白，实为 {v!r}"
                )


# ──────────────────────── 6. E0-4 R16 孤立残留 ──────────────────────────────


def test_e04_r16_residual(e0_workbook):
    """E0-4 R16 有 G=0 H=0 残留值，迁移时必须按空行处理。"""
    ws = e0_workbook["借款发函记录表E0-4"]
    assert ws.cell(row=16, column=7).value == 0, "E0-4 R16.G 应为 0"
    assert ws.cell(row=16, column=8).value == 0, "E0-4 R16.H 应为 0"
    # 其余列空
    for c in [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16]:
        v = ws.cell(row=16, column=c).value
        assert v is None or v == "", f"E0-4 R16 col{c} 应为空"


# ──────────────────────── 7. E0-3 公式目标 ──────────────────────────────────


def test_e03_formula_targets(e0_workbook):
    """E0-3 的 D/G/K 列公式指向 E1-3 的 $A/$C/$K。"""
    ws = e0_workbook["货币资金发函记录表E0-3"]
    expected_target_sheet = "银行存款及其他货币资金明细表(仅人民币)E1-3"
    expected_cols = {"D": "$A", "G": "$C", "K": "$K"}
    for r in range(6, 25):  # R6:R24 有公式
        for col_idx, (col_letter, target_col) in enumerate(expected_cols.items(), start=1):
            col_num = {"D": 4, "G": 7, "K": 11}[col_letter]
            formula = str(ws.cell(row=r, column=col_num).value or "")
            assert expected_target_sheet in formula, (
                f"E0-3 R{r}.{col_letter} 应引用 {expected_target_sheet}"
            )
            assert target_col in formula, (
                f"E0-3 R{r}.{col_letter} 应引用列 {target_col}"
            )


def test_e03_formula_row_mapping_skips_22_and_26(e0_workbook):
    """行映射跳过 E1-3 的 R22 和 R26（段头 SUM 行）。"""
    ws = e0_workbook["货币资金发函记录表E0-3"]
    # 收集所有 D 列公式引用的 E1-3 行号
    referenced_rows: list[int] = []
    for r in range(6, 25):
        formula = str(ws.cell(row=r, column=4).value or "")
        m = re.search(r"\$A(\d+)", formula)
        if m:
            referenced_rows.append(int(m.group(1)))
    # 不应包含 22 和 26
    assert 22 not in referenced_rows, "行映射不应包含 E1-3 R22（段头）"
    assert 26 not in referenced_rows, "行映射不应包含 E1-3 R26（段头）"
    # 也不应包含 12（银行：段头本身）
    assert 12 not in referenced_rows, "行映射不应包含 E1-3 R12（银行：段头）"
    # 确认映射范围
    assert min(referenced_rows) == 13, "映射应从 E1-3 R13 开始"
    assert max(referenced_rows) == 33, "映射应到 E1-3 R33 结束"


# ──────────────────────── 8. 四张表均无合计行 ────────────────────────────────


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_no_total_row(e0_workbook, sheet_name):
    ws = e0_workbook[sheet_name]
    end_row = _DATA_RANGE_END[sheet_name]
    for r in range(1, end_row + 5):
        a_val = str(ws.cell(row=r, column=1).value or "")
        assert "合计" not in a_val and "合 计" not in a_val, (
            f"{sheet_name} R{r} 不应有合计行，实为 {a_val!r}"
        )


# ──────────────────────── 9. 三向比对：源 xlsx ↔ manifest ↔ E0.yaml ─────────


@pytest.mark.parametrize("sheet_name", _SEND_LIST_SHEETS)
def test_three_way_comparison(e0_workbook, manifest, e0_yaml, sheet_name):
    """源 xlsx 表头 ↔ manifest.cell_columns ↔ E0.yaml.dynamic_table.columns。"""
    ws = e0_workbook[sheet_name]
    spec_cols = manifest["sheets"][sheet_name]["cell_columns"]
    yaml_cols = e0_yaml["sheets"][sheet_name]["dynamic_table"]["columns"]

    # 列字母集合与顺序一致
    spec_keys = list(spec_cols.keys())
    yaml_keys = list(yaml_cols.keys())
    assert spec_keys == yaml_keys, f"{sheet_name} manifest 与 E0.yaml 列序不一致"

    # 逐列五元组比对
    for i, cell_letter in enumerate(spec_keys):
        col_num = i + 1
        xlsx_label = ws.cell(row=5, column=col_num).value
        manifest_label = spec_cols[cell_letter]["label"]
        yaml_label = yaml_cols[cell_letter]["label"]
        assert xlsx_label == manifest_label == yaml_label, (
            f"{sheet_name}.{cell_letter} label 三方不一致: "
            f"xlsx={xlsx_label!r}, manifest={manifest_label!r}, yaml={yaml_label!r}"
        )

        manifest_field = spec_cols[cell_letter]["field"]
        yaml_field = yaml_cols[cell_letter]["field"]
        assert manifest_field == yaml_field, (
            f"{sheet_name}.{cell_letter} field 不一致: manifest={manifest_field}, yaml={yaml_field}"
        )

        manifest_type = spec_cols[cell_letter]["type"]
        yaml_type = yaml_cols[cell_letter]["type"]
        assert manifest_type == yaml_type, (
            f"{sheet_name}.{cell_letter} type 不一致: manifest={manifest_type}, yaml={yaml_type}"
        )


# ──────────────────────── 10. 底稿目录归属裁决 ──────────────────────────────


def test_e05_belongs_to_send_list_not_checklist(e0_workbook):
    """底稿目录 F8=E0-5 ↔ E8=应付银行承兑汇票发函记录表；核对表不在目录里。"""
    ws = e0_workbook["底稿目录"]
    # F8 = E0-5（索引号）
    assert ws["F8"].value == "E0-5", "底稿目录 F8 应为 E0-5"
    # E8 = 应付银行承兑汇票发函记录表
    e8 = str(ws["E8"].value or "")
    assert "应付银行承兑汇票" in e8, f"底稿目录 E8 应含「应付银行承兑汇票」，实为 {e8!r}"

    # 核对表不在底稿目录的索引号列里
    index_nos = []
    for r in range(1, 25):
        v = ws.cell(row=r, column=6).value  # F 列
        if v:
            index_nos.append(str(v))
    assert "银行函证其他信息核对表E0-5" not in " ".join(index_nos)


# ──────────────────────── 11. E0-5 一码两表在模板中共存 ─────────────────────


def test_two_e05_sheets_coexist(e0_workbook):
    """源模板确实有两张以 E0-5 结尾的 tab。"""
    e05_tabs = [s for s in e0_workbook.sheetnames if s.endswith("E0-5")]
    assert len(e05_tabs) == 2
    assert "应付银行承兑汇票发函记录表E0-5" in e05_tabs
    assert "银行函证其他信息核对表E0-5" in e05_tabs


def test_checklist_e05_is_hidden(e0_workbook):
    """核对表 E0-5 是 hidden sheet。"""
    ws = e0_workbook["银行函证其他信息核对表E0-5"]
    assert ws.sheet_state == "hidden"


# ──────────────────────── 12. 反向自检：改一字必红 ──────────────────────────


def test_reverse_check_header_mismatch_detected():
    """反向自检：如果 manifest 里某列 label 与 _EXPECTED_HEADERS 不一致，应能检测出。"""
    # 构造一个篡改的 label
    fake_headers = _EXPECTED_HEADERS["货币资金发函记录表E0-3"].copy()
    fake_headers[0] = "所属科目_篡改"
    m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    actual_label = m["sheets"]["货币资金发函记录表E0-3"]["cell_columns"]["A"]["label"]
    # 真实 manifest 应与 expected 一致
    assert actual_label == "所属科目"
    # 篡改版应不一致
    assert actual_label != fake_headers[0]
