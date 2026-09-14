"""F1 源模板事实守卫（openpyxl 直读 `backend/wp_templates/F/F1 预付账款.xlsx`）。

本文件把 spec `f1-extraction-chain-and-disclosure-source-fidelity` 所依赖的**源模板事实**
钉死，防后续 md 重建 / 并发改动把口径悄悄改回去。

三条被钉死的事实：

1. **F1-5「账龄1年以上的大额预付账款检查表」的列语义**（R5 表头）——
   `J 审定余额` 是 `B 期末余额 − I 计提坏账准备`，国企披露②表的「期末余额」取的是
   **J 列**而不是 B 列。若把 J 当成 B，附注②表会披露未扣坏账的毛额。

2. **国企披露②表四列的数据源**（`附注披露信息(国企)` R18）——
   `A18=RIGHT($A$3,…)`（被审计单位名）/ `B18='长期挂款检查表F1-5'!A6` /
   `C18=…!J6` / `D18=…!C6` / `E18=…!E6`。这是「②表以 F1-5 为权威数据源」
   与「债权单位缺省取被审计单位名」两项需求的全部依据。

3. **上市披露①③两表的数据源** —— ①按账龄表取 `审定表F1-1` 的 I/E 列，
   ③前五名取 `实质性分析F1-4` 的 A/B 列。

每组断言都配**反向自检**（把列字母/sheet 名换一个必须失败），
防「正则/坐标写错导致断言恒真」的空转守卫。

spec: .kiro/specs/f1-extraction-chain-and-disclosure-source-fidelity/ (Task 1.1)
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC_XLSX = _ROOT / "wp_templates" / "F" / "F1 预付账款.xlsx"

SHEET_LT = "长期挂款检查表F1-5"
SHEET_SOE = "附注披露信息(国企)"
SHEET_LISTED = "附注披露信息(上市公司)"
SHEET_ADJ = "审定表F1-1"
SHEET_ANALYSIS = "实质性分析F1-4"

#: F1-5 R5 表头（列字母 → 字面）。J 列是「审定余额」是本 spec 的核心依据。
_LT_HEADER_R5 = {
    "A": "债务人名称",
    "B": "期末余额",
    "C": "账龄",
    "D": "经济业务说明",
    "E": "未偿还或未结转的原因",
    "I": "计提坏账准备金额",
    "J": "审定余额",
}

#: 国企②表首个数据行（R18）各列引用的 F1-5 列字母。
#: 键 = 披露②表列字母，值 = F1-5 列字母。
_SOE_OVER1_R18_REFS = {
    "B": "A",  # 债务单位   ← F1-5 债务人名称
    "C": "J",  # 期末余额   ← F1-5 审定余额（已扣坏账）
    "D": "C",  # 账龄       ← F1-5 账龄
    "E": "E",  # 未结算的原因 ← F1-5 未偿还或未结转的原因
}


def _wb():
    assert _SRC_XLSX.exists(), f"源模板缺失: {_SRC_XLSX}"
    # data_only=False：本守卫要读**公式串**本身，不是缓存值
    return openpyxl.load_workbook(_SRC_XLSX, data_only=False)


def _norm(v) -> str:
    """去空白归一（源模板列头普遍带全/半角空格）。"""
    return re.sub(r"\s+", "", str(v or ""))


def _cell(ws, col: str, row: int):
    return ws[f"{col}{row}"].value


# ─────────────────────────── 事实 1：F1-5 列语义 ───────────────────────────


def test_f1_5_sheet_exists():
    wb = _wb()
    assert SHEET_LT in wb.sheetnames, wb.sheetnames


@pytest.mark.parametrize("col,expected", sorted(_LT_HEADER_R5.items()))
def test_f1_5_header_row5(col: str, expected: str):
    ws = _wb()[SHEET_LT]
    assert _norm(_cell(ws, col, 5)) == _norm(expected), (
        f"F1-5 R5 表头 {col}5 应为 {expected!r}，实为 {_cell(ws, col, 5)!r}"
    )


def test_f1_5_audited_balance_is_column_j_not_b():
    """反向自检：J 与 B 的字面必须不同 —— 否则「取 J 列」这条断言毫无意义。"""
    ws = _wb()[SHEET_LT]
    assert _norm(_cell(ws, "J", 5)) != _norm(_cell(ws, "B", 5))
    assert _norm(_cell(ws, "J", 5)) == "审定余额"
    assert _norm(_cell(ws, "B", 5)) == "期末余额"


def test_f1_5_total_row_sums_audited_column():
    """R15 合计行对 J 列求和 → 证明 J 是可加金额列（不是文本列）。"""
    ws = _wb()[SHEET_LT]
    assert str(_cell(ws, "J", 15) or "").startswith("=SUM(J6:J14")


# ─────────────────────── 事实 2：国企②表以 F1-5 为源 ───────────────────────


def test_soe_sheet_exists():
    wb = _wb()
    assert SHEET_SOE in wb.sheetnames, wb.sheetnames


def test_soe_over1_section_title():
    ws = _wb()[SHEET_SOE]
    assert _norm(_cell(ws, "A", 16)) == _norm("（2）账龄超过1年的大额预付款项")


def test_soe_over1_header_row17():
    ws = _wb()[SHEET_SOE]
    got = [_norm(_cell(ws, c, 17)) for c in ("A", "B", "C", "D", "E")]
    assert got == ["债权单位", "债务单位", "期末余额", "账龄", "未结算的原因"], got


@pytest.mark.parametrize("disc_col,lt_col", sorted(_SOE_OVER1_R18_REFS.items()))
def test_soe_over1_r18_references_f1_5(disc_col: str, lt_col: str):
    """②表 R18 各列必须引用 F1-5 的指定列（行号 6 = F1-5 首个数据行）。"""
    ws = _wb()[SHEET_SOE]
    formula = str(_cell(ws, disc_col, 18) or "")
    assert SHEET_LT in formula, f"{disc_col}18 未引用 {SHEET_LT}：{formula!r}"
    assert re.search(rf"!\${{0,1}}{lt_col}\${{0,1}}6\b", formula), (
        f"{disc_col}18 应引用 F1-5 的 {lt_col}6，实为 {formula!r}"
    )


def test_soe_over1_creditor_unit_is_audited_entity_name():
    """A18~A20「债权单位」= 从底稿目录 A2「被审计单位：XXX」截出的主体名。"""
    ws = _wb()[SHEET_SOE]
    for row in (18, 19, 20):
        formula = str(_cell(ws, "A", row) or "")
        assert "RIGHT(" in formula and "$A$3" in formula, (
            f"A{row} 应为 RIGHT($A$3,…) 形态，实为 {formula!r}"
        )


def test_soe_over1_reverse_selfcheck_wrong_column_fails():
    """反向自检：若把「期末余额」的来源列由 J 改成 I，断言必须失败。"""
    ws = _wb()[SHEET_SOE]
    formula = str(_cell(ws, "C", 18) or "")
    assert not re.search(r"!\${0,1}I\${0,1}6\b", formula), (
        "C18 竟引用了 F1-5 的 I 列（计提坏账准备）—— 守卫参数写错了"
    )


def test_soe_over1_total_row_dashes():
    """R21 合计行：账龄/未结算原因列为「——」（载荷须原样推，不推空串）。"""
    ws = _wb()[SHEET_SOE]
    assert _norm(_cell(ws, "A", 21)) == "合计"
    assert _norm(_cell(ws, "D", 21)) == "——"
    assert _norm(_cell(ws, "E", 21)) == "——"


def test_soe_aging_table_is_three_level_seven_columns():
    """国企①表是**三级表头 7 列**（坏账准备作列）—— 这是底稿收集形态。

    附注侧保持 5 列 + 小计/减值准备/合计 7 行（校验预设 F7-6/7/8 裁决），
    本断言只固化「底稿源模板确实是 7 列」，防有人据此误改附注。
    """
    ws = _wb()[SHEET_SOE]
    assert _norm(_cell(ws, "A", 8)) == "账龄"
    assert _norm(_cell(ws, "B", 8)) == "期末数"
    assert _norm(_cell(ws, "E", 8)) == "期初数"
    assert _norm(_cell(ws, "B", 9)) == "账面余额"
    assert _norm(_cell(ws, "D", 9)) == "坏账准备"
    assert _norm(_cell(ws, "E", 9)) == "账面余额"
    assert _norm(_cell(ws, "G", 9)) == "坏账准备"
    assert _norm(_cell(ws, "B", 10)) == "金额"
    assert _norm(_cell(ws, "C", 10)) == "比例（%）"


# ──────────────────── 事实 3：上市①③两表的数据源 ────────────────────


def test_listed_sheet_exists():
    wb = _wb()
    assert SHEET_LISTED in wb.sheetnames, wb.sheetnames


@pytest.mark.parametrize("row,adj_row", [(10, 17), (11, 18), (12, 19), (13, 20)])
def test_listed_aging_rows_reference_adjudication(row: int, adj_row: int):
    """①按账龄表：期末取 F1-1 的 I 列、上年年末取 E 列。"""
    ws = _wb()[SHEET_LISTED]
    end_f = str(_cell(ws, "B", row) or "")
    prior_f = str(_cell(ws, "D", row) or "")
    assert SHEET_ADJ in end_f and f"I{adj_row}" in end_f, end_f
    assert SHEET_ADJ in prior_f and f"E{adj_row}" in prior_f, prior_f


@pytest.mark.parametrize("row,src_row", [(28, 41), (29, 42), (30, 43), (31, 44), (32, 45)])
def test_listed_top5_rows_reference_analysis(row: int, src_row: int):
    """③前五名：单位名称取 F1-4 的 A 列、金额取 B 列。"""
    ws = _wb()[SHEET_LISTED]
    name_f = str(_cell(ws, "A", row) or "")
    amt_f = str(_cell(ws, "B", row) or "")
    assert SHEET_ANALYSIS in name_f and f"A{src_row}" in name_f, name_f
    assert SHEET_ANALYSIS in amt_f and f"B{src_row}" in amt_f, amt_f


def test_listed_over1_rows_are_manual():
    """上市②表 R17~R19 的「债务人名称/账面余额/减值准备」无公式（手工录入）。

    这条钉住「上市②表保持手工、只有国企②表由 F1-5 驱动」的差异，
    防有人照国企做法把上市②表也接成 F1-5 派生。
    """
    ws = _wb()[SHEET_LISTED]
    for row in (17, 18, 19):
        for col in ("A", "B", "D"):
            v = _cell(ws, col, row)
            assert v in (None, ""), f"上市②表 {col}{row} 竟有值 {v!r}（应为手工空白）"
        # C 列是占比公式（自动派生），必须有
        assert str(_cell(ws, "C", row) or "").startswith("="), row


def test_listed_top5_has_two_disclosure_formats():
    """③前五名「汇总或分别披露」二选一（A24 / A26 两个格式标签）。"""
    ws = _wb()[SHEET_LISTED]
    assert _norm(_cell(ws, "A", 24)) == "汇总披露格式："
    assert _norm(_cell(ws, "A", 26)) == "分别披露格式："
