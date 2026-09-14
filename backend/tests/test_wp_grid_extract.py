"""univer 表格类底稿网格提取服务单测

守护 render-config univer sheet（审定表/明细表/测算表）从模板自动提取网格数据，
修复混合底稿里 univer sheet 只显示死占位「数据尚未导入」的问题。
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.services.wp_grid_extract import extract_grid, extract_grid_from_sheet


def _build_grid_sheet(tmp_path, sheet_name="审定表D1-1"):
    """构建一个贴合致同审定表布局的最小 xlsx（含合并单元格 + 样式）。"""
    from openpyxl.styles import PatternFill, Font, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws["A1"] = "致同会计师事务所"
    ws["A2"] = "应收票据审定表"
    ws["A5"] = "项目"
    ws["B5"] = "期初数"
    ws["F5"] = "期末数"
    ws["B6"] = "未审数"
    ws["E6"] = "审定数"
    ws["A7"] = "一、应收票据原值"
    ws["A8"] = "银行承兑汇票"
    ws["A10"] = "小计"

    # 样式：表头加粗+居中+紫色填充；分节行紫填充加粗；数据列会计格式
    purple = PatternFill(fill_type="solid", fgColor="FFE4DFEC")
    for coord in ("A5", "B5", "F5", "B6", "E6"):
        ws[coord].font = Font(bold=True, size=10)
        ws[coord].alignment = Alignment(horizontal="center")
        ws[coord].fill = purple
    ws["A7"].font = Font(bold=True, size=10)
    ws["A7"].fill = purple
    ws["A7"].alignment = Alignment(horizontal="left")
    ws["A10"].font = Font(bold=True, size=10)
    # 数据单元格会计格式 + 填充（确保被提取）
    ws["B8"].number_format = '_ * #,##0.00_ ;_ * \\-#,##0.00_ ;_ * "-"??_ ;_ @_ '
    ws["B8"].alignment = Alignment(horizontal="right")
    ws["B8"].fill = purple

    # 合并：标题横跨 A1:F1，项目列 A5:A6 纵向合并
    ws.merge_cells("A1:F1")
    ws.merge_cells("A5:A6")
    ws.merge_cells("B5:E5")
    # 列宽
    ws.column_dimensions["A"].width = 20

    fp = tmp_path / "grid.xlsx"
    wb.save(str(fp))
    wb.close()
    return fp, sheet_name


def test_extract_styles(tmp_path):
    """提取真实样式：加粗/对齐/会计格式标记（无 fill）。"""
    fp, sn = _build_grid_sheet(tmp_path)
    g = extract_grid(fp, sn)
    # 项目 (偏移后 A1) → bold + center
    a1 = g["cells"]["A1"]["style"]
    assert a1.get("bold") is True
    assert a1.get("align") == "center"
    assert a1.get("fill") is None  # 不输出 fill
    # 一、应收票据原值 (偏移后 A3) → bold + left
    a3 = g["cells"]["A3"]["style"]
    assert a3.get("bold") is True
    assert a3.get("align") == "left"
    assert a3.get("fill") is None


def test_extract_basic_grid(tmp_path):
    fp, sn = _build_grid_sheet(tmp_path)
    g = extract_grid(fp, sn)
    # 数据表从"项目"行开始（标题行被跳过）
    # 第一行应该是"项目"（偏移后 r=1）
    assert g["max_row"] >= 6
    assert g["max_col"] >= 6
    # 第一行 A1 = "项目"
    assert g["cells"]["A1"]["v"] == "项目"
    assert g["cells"]["A1"]["r"] == 1
    assert g["cells"]["A1"]["c"] == 1
    # "一、应收票据原值" 偏移到 row 3（原 row7 - offset4 = row3）
    a3 = g["cells"].get("A3")
    assert a3 is not None
    assert a3["v"] == "一、应收票据原值"
    # 标题行（致同/审定表）不应出现
    has_title = any("致同" in str(c.get("v", "")) for c in g["cells"].values())
    assert not has_title
    # 无 fill 样式
    fills = [c["style"].get("fill") for c in g["cells"].values() if c.get("style", {}).get("fill")]
    assert len(fills) == 0


def test_merged_ranges_extracted(tmp_path):
    fp, sn = _build_grid_sheet(tmp_path)
    g = extract_grid(fp, sn)
    merged = g["merged_cells"]
    # 标题区合并 (A1:F1) 被跳过，只保留数据区合并
    # A5:A6 (原 row5-6) → 偏移后 row1-2：项目列纵向合并
    a_merge = next((m for m in merged if m["s"]["c"] == 1 and m["s"]["r"] == 1), None)
    assert a_merge is not None
    assert a_merge["e"]["r"] == 2  # 2 行合并
    # B5:E5 (原 row5) → 偏移后 row1: 期初数横向合并
    b_merge = next((m for m in merged if m["s"]["c"] == 2 and m["s"]["r"] == 1), None)
    assert b_merge is not None
    assert b_merge["e"]["c"] == 5  # B~E


def test_col_widths_extracted(tmp_path):
    fp, sn = _build_grid_sheet(tmp_path)
    g = extract_grid(fp, sn)
    assert g["col_widths"].get("A") == 20.0


def test_missing_file_returns_empty(tmp_path):
    g = extract_grid(tmp_path / "nope.xlsx", "X")
    assert g["cells"] == {}
    assert g["merged_cells"] == []
    assert g["max_row"] == 0


def test_missing_sheet_returns_empty(tmp_path):
    fp, _ = _build_grid_sheet(tmp_path)
    g = extract_grid(fp, "不存在的Sheet")
    assert g["cells"] == {}
    assert g["max_row"] == 0


def test_empty_sheet_returns_empty_grid(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "空表"
    fp = tmp_path / "empty.xlsx"
    wb.save(str(fp))
    wb.close()
    g = extract_grid(fp, "空表")
    assert g["cells"] == {}


# ─────────────────────────────────────────────────────────────────────────
# 真实模板：C-附注披露（上市公司 / 国企）只读网格兜底
# （render-config 对无 schema 的 c-note-table 用本提取做兜底，避免「尚未配置」空态）
# ─────────────────────────────────────────────────────────────────────────

_REAL_TEMPLATE = Path(__file__).resolve().parents[1] / "wp_templates" / "D" / "D1 应收票据.xlsx"


@pytest.mark.skipif(
    not _REAL_TEMPLATE.exists(),
    reason=f"真实模板缺失：{_REAL_TEMPLATE}",
)
@pytest.mark.parametrize(
    "sheet_name",
    ["附注披露信息（上市公司）", "附注披露信息（国企）"],
)
def test_real_disclosure_sheets_extract_grid(sheet_name):
    """D1 应收票据两个附注披露 sheet 提取出非空只读网格（含合并单元格）。"""
    g = extract_grid(str(_REAL_TEMPLATE), sheet_name)
    # 多级披露表格 → 大量单元格
    assert len(g["cells"]) > 100, f"{sheet_name} 提取单元格过少：{len(g['cells'])}"
    assert g["max_row"] > 20
    # 含合并区域（披露表头跨列/跨行合并）
    assert len(g["merged_cells"]) > 0
    # 关键披露行存在（票据种类 / 银行承兑汇票 / 合计 等任一）
    texts = {str(c.get("v", "")).strip() for c in g["cells"].values()}
    assert any("承兑汇票" in t for t in texts)


# ─────────────────────────────────────────────────────────────────────────
# strip_standard_header：编制信息行判定（2026-08-02 修「列头行被误删」）
#
# 旧实现按「整行文本包含 致同/被审计单位/编制人/编制日/截止日/复核人」子串命中，
# 且取 rows1..7 里最后一个命中行作为裁剪终点 → E0-3~E0-6 四张发函记录表的
# 列头行含「报表截止日」（内含「截止日」）→ 列头行连同上方一起被删，
# 前端只剩一张无表头空网格（实测 E0-4 只剩源模板残留的两个 0）。
# ─────────────────────────────────────────────────────────────────────────

from app.services.wp_grid_extract import (  # noqa: E402
    _is_prep_info_row,
    _looks_like_prep_label,
    strip_standard_header,
)

_E0_TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "wp_templates" / "E" / "E0 货币资金 - 函证（Leap应对措施-函证）.xlsx"
)

#: 四张发函前清单的源模板列头（openpyxl 直读 row 5，逐字）
_E0_SEND_LIST_HEADERS = {
    "货币资金发函记录表E0-3": [
        "所属科目", "索引号", "报表截止日", "开户银行", "是否函证", "账户名称",
        "银行账号", "币种", "利率(%)", "账户类型", "账户余额（原币）",
        "是否属于资金归集（资金池或其他资金管理）账户", "起始日期", "终止日期",
        "是否存在冻结、担保或其他使用限制（如是，请注明）", "备注",
    ],
    "借款发函记录表E0-4": [
        "所属科目", "索引号", "报表截止日", "开户银行", "是否函证", "借款人名称",
        "借款账号", "币种", "余额", "借款日期", "到期日期", "利率(%)",
        "抵(质)押品/担保人", "备注", "借款类型", "期末应付利息",
    ],
    "应付银行承兑汇票发函记录表E0-5": [
        "索引号", "报表截止日", "开户银行", "银行承兑汇票号码", "结算账户账号",
        "币种", "票面金额", "出票日", "到期日", "抵（质）押品",
    ],
    "理财产品发函记录表E0-6": [
        "索引号", "报表截止日", "开户行名称及收件人", "产品名称",
        "产品类型（封闭式/开放式）", "币种", "持有份额", "产品净值",
        "购买日", "到期日", "是否被用于担保或存在其他使用限制",
    ],
}


def _legacy_skip(grid: dict) -> int:
    """改造前的裁剪判据（整行子串命中），仅供反向自检与单调性对照。"""
    cells = grid.get("cells", {})
    if not cells:
        return 0
    max_col = grid.get("max_col", 0)
    max_row = grid.get("max_row", 0)
    skip = 0
    for r in range(1, min(8, max_row + 1)):
        row_text = " ".join(
            str(cells.get(f"{chr(64 + c)}{r}", {}).get("v", ""))
            for c in range(1, min(15, max_col + 1))
        ).lower()
        if any(kw in row_text for kw in ("致同", "被审计单位", "编制人", "编制日", "截止日", "复核人")):
            skip = r
    return skip


def _actual_skip(grid: dict) -> int:
    return grid.get("max_row", 0) - strip_standard_header(grid).get("max_row", 0)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("截止日：202X年12月31日", True),
        ("被审计单位：", True),
        ("编制人：李四", True),
        ("致同会计师事务所", True),
        # ↓ 关键词表刻意不含「页次/索引号/会计期间/复核日」：扩充会让新判据
        #   不再是旧判据的子集，实测 83 张 sheet 反而多删行（详见服务层注释）
        ("页  次  1", False),
        ("索引号：E0-4", False),
        # ↓ 关键负例：列头，不是编制信息标签
        ("报表截止日", False),   # 关键词不在开头
        ("索引号", False),       # 关键词后无取值
        ("所属科目", False),
        ("期末应付利息", False),
        ("", False),
    ],
)
def test_looks_like_prep_label(text, expected):
    assert _looks_like_prep_label(text) is expected


def test_is_prep_info_row_requires_majority():
    """过半规则：列头行/数据行里偶有一格像标签也不算编制信息行。"""
    e0_2_header = [
        "函证索引",
        "被审计单位提供的被函证单位信息及核对（核实被函证单位信息）（备注1）",
        "回函信息情况（回函核对记录）",
        "第一次发函结果？\n（送抵/退回）（备注2）",
        "经核实的原因",
        "该原因是否合理（是/否）\n（备注3）",
    ]
    assert _is_prep_info_row(e0_2_header) is False
    # B50-2 数据行：首格以「被审计单位」开头，但整行是内容
    assert _is_prep_info_row([
        "被审计单位的风险评估流程未识别出预期应当识别出的潜在风险",
        "B22C", "是", "….", "在期末而非期中实施更多的审计程序；", "B60",
    ]) is False
    # A1-11「文号规则」数据行：含事务所名 + 带换行的长内容格
    assert _is_prep_info_row([
        "1、以总部名义出具的鉴证业务报告\n（以上海办公室为例）",
        "致同会计师事务所（特殊普通合伙）", "是", "中国•北京", "是",
        "审计报告：致同审字（2021）第310A0001号；\n专项报告：致同专字（2021）第310A0001号；",
        "审、专、验：业务属性；\n310：上海办公室代码；",
    ]) is False
    assert _is_prep_info_row([]) is False


@pytest.mark.parametrize(
    "row",
    [
        # 关键词只覆盖一格，其余是「会计期间 / 复核日期 / 索引 / 页次」等变体标签
        ["会计期间：202X年度", "复核人：李四", "复核日期：2025.X.X"],
        ["客户名称：", "编制人：", "日期：", "索引：A1-13-1"],
        ["截止日：202X年12月31日", "回复人：张XX", "回复日期：2025.XX.XX"],
        ["截止日/会计期间：202X年X月X日/202X年度", "复核人：李四", "复核日期：2025.X.X", "页 次  1"],
        ["致同会计师事务所"],
    ],
)
def test_prep_info_row_variant_labels_still_detected(row):
    """编制信息行用变体标签（会计期间/复核日期/索引/页次）时仍须判为编制信息行。

    只用关键词过半会漏掉它们（``复核日期`` 不以 ``复核人`` 开头）→ 这些行会被
    「复活」到 grid 里，用户在表格顶部看到重复的编制信息。
    """
    assert _is_prep_info_row(row) is True


def _synth_grid(rows: list[list[str]]) -> dict:
    cells = {}
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row, start=1):
            if v:
                cells[f"{chr(64 + c)}{r}"] = {"v": v, "r": r, "c": c, "style": {}}
    return {"cells": cells, "merged_cells": [], "col_widths": {},
            "max_row": len(rows), "max_col": max(len(r) for r in rows), "header_rows": 1}


def test_prep_rows_still_stripped_but_header_row_survives():
    """合成 fixture：编制信息行照删，含「报表截止日」的列头行必须留下。"""
    grid = _synth_grid([
        ["致同会计师事务所"],
        ["借款发函记录表"],
        ["被审计单位：", "", "", "", "", "编制人：", "", "", "", "", "编制日期："],
        ["截止日：202X年12月31日", "", "", "", "", "复核人：", "", "", "", "", "复核日期："],
        ["所属科目", "索引号", "报表截止日", "开户银行", "是否函证", "借款人名称"],
        ["短期借款", "E0-1-1", "2025-12-31", "XX银行", "是", "XX公司"],
    ])
    out = strip_standard_header(grid)
    assert out["cells"]["A1"]["v"] == "所属科目"
    assert out["cells"]["C1"]["v"] == "报表截止日"
    assert out["cells"]["A2"]["v"] == "短期借款"
    assert out["max_row"] == 2
    # 反向自检：旧判据会把列头行也删掉（证明本守卫不是空转）
    assert _legacy_skip(grid) == 5
    assert _actual_skip(grid) == 4


@pytest.mark.skipif(not _E0_TEMPLATE.exists(), reason=f"真实模板缺失：{_E0_TEMPLATE}")
@pytest.mark.parametrize("sheet_name", sorted(_E0_SEND_LIST_HEADERS))
def test_e0_send_list_header_row_survives_strip(sheet_name):
    """E0 四张发函前清单：strip 后首行 = 源模板列头逐字（不再是无表头空网格）。"""
    expected = _E0_SEND_LIST_HEADERS[sheet_name]
    grid = extract_grid(str(_E0_TEMPLATE), sheet_name)
    assert grid["cells"], f"{sheet_name} 原始提取为空"
    out = strip_standard_header(grid)
    row1 = [
        str(out["cells"][f"{chr(64 + c)}1"]["v"]).strip()
        for c in range(1, len(expected) + 1)
    ]
    assert row1 == expected, f"{sheet_name} 列头行与源模板不一致"
    # 反向自检：旧判据把列头行删了（skip 恰好落在列头行 5）
    assert _legacy_skip(grid) > _actual_skip(grid)


@pytest.mark.skipif(not _E0_TEMPLATE.exists(), reason=f"真实模板缺失：{_E0_TEMPLATE}")
@pytest.mark.parametrize(
    "sheet_name",
    sorted(_E0_SEND_LIST_HEADERS) + ["银行函证其他信息核对表E0-5", "回函情况汇编"],
)
def test_strip_never_removes_more_rows_than_before(sheet_name):
    """单调性：新判据只可能少删行，绝不多删（零回归护栏）。"""
    grid = extract_grid(str(_E0_TEMPLATE), sheet_name)
    if not grid["cells"]:
        pytest.skip(f"{sheet_name} 提取为空")
    assert _actual_skip(grid) <= _legacy_skip(grid)


def test_prep_keywords_are_identical_to_legacy_set():
    """结构性单调护栏：关键词表必须与旧子串判据逐字相同。

    只要关键词相同，「某格以关键词开头」⇒「整行含该关键词」，新判据即旧判据的
    真子集 → 裁剪行数只可能变少。一旦有人扩充关键词，这条立刻红，提醒必须重跑
    全量 characterization（``tmp_strip_charac`` 范式）确认没有 sheet 多删行。
    """
    from app.services.wp_grid_extract import _PREP_LABEL_KEYWORDS

    assert _PREP_LABEL_KEYWORDS == ("致同", "被审计单位", "编制人", "编制日", "截止日", "复核人")


@pytest.mark.parametrize(
    "row",
    [
        ["致同会计师事务所"],
        ["被审计单位：", "编制人：", "编制日期："],
        ["截止日：202X年12月31日", "复核人：李四", "复核日期：2025.X.X", "页 次  1"],
        ["所属科目", "索引号", "报表截止日", "开户银行"],
        ["短期借款", "E0-1-1", "2025-12-31", "XX银行"],
        ["被审计单位的风险评估流程未识别出预期应当识别出的潜在风险", "B22C", "是", "…"],
        [],
    ],
)
def test_new_predicate_is_subset_of_legacy(row):
    """新判据命中 ⇒ 旧子串判据也命中（子集不变式，逐行校验）。"""
    legacy_hit = any(
        kw in " ".join(row).lower()
        for kw in ("致同", "被审计单位", "编制人", "编制日", "截止日", "复核人")
    )
    if _is_prep_info_row(row):
        assert legacy_hit, f"新判据命中但旧判据未命中 → 会多删行：{row}"
