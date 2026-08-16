"""行骨架三向守卫（Property 43）：源 xlsx 首列 ↔ 附注模板 `tables[].rows`。

从 `test_note_i_cycle_structure.py` 拆出（该文件 1671 行超 pre-commit 的 800 行门禁）。
本组是 2026-08-15 归档前复盘新增的**第三条边** —— 原三向（Property 16）只比列、
`_SRC_DYNAMIC_MARK_COUNT`（Property 21）只锁源侧扩位数，行维度此前完全裸奔。
"""
from __future__ import annotations

import re

import openpyxl
import pytest

from tests.test_note_i_cycle_structure import (  # noqa: F401
    _SECTION_MAP,
    _SRC_DISCLOSURE_SHEETS,
    _SRC_DYNAMIC_MARK_COUNT,
    _SRC_FILES,
    _VERIFIED_TABLES,
    _norm,
    _section,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 43：**行维度**第三边（源 xlsx 首列 ↔ 附注模板 rows）
#
# 🔴🔴 为什么必须补这一条（2026-08-15 三向实测抓出真错）：本文件此前的三向比对
# （Property 16）只比**列**（源表头 ↔ 模板 headers ↔ 载荷 columns），
# `_SRC_DYNAMIC_MARK_COUNT`（Property 21）只数**源侧**扩位、从不看模板与前端消费侧。
# 于是下面这处 38 行里的 2 行错**同时逃过全部 38 张列契约 + 12 条扩位基线**：
#
#   源模板 `附注披露信息（上市公司）!A43:A44` = 「（2）失效且终止确认的部分」/「（3）其他减少」
#   改造前模板 JSON 第 33/34 行 = 「（2）其他减少」/「……」
#   改造前前端 `I1_LISTED_MOVEMENT_ROWS` 第 33/34 行 = 同上（同批生成的同一处错）
#
# ⇒ 减值准备减少段**丢了一个真实披露项、并凭空多出第 4 个可扩位**。两侧同错，
# 故任何「模板 ↔ 载荷」自洽型判据都放行（memory 已记「自洽性判据只能保证两侧一致，
# 不能保证两侧都对」）—— 只有拿源 xlsx 当第三边才抓得到。
# 国企侧同表更严重：48 行 / 10 个类别（缺「其他」、「矿产权」被拆成「采矿权+探矿权」、
# 「特许经营权」写成「特许权」、首类别是「软件」而源模板是「土地使用权」）。
#
# 判据范围**只覆盖 I1 两版**，理由见 `_ROW_SKELETON_NOT_ASSERTED`（其余 10 对的
# 「源侧扩位数 ↔ 模板 expandable 数」关系实测**不成立**，把它当不变量断言会锁死错值）。
# ═══════════════════════════════════════════════════════════════════════════════

#: 行骨架经源模板逐格实证、可做逐行断言的表。值 = `(表名, 源 sheet 首列行区间[含端点])`
_ROW_SKELETON_ASSERTED: dict[tuple[str, str], tuple[str, int, int]] = {
    ("I1", "listed"): ("无形资产情况", 11, 48),  # 四层变动行 38 行（类别作列）
    ("I1", "soe"): ("无形资产情况", 8, 59),      # 四层 × (层标题 + 11 类别 + 扩位) = 52 行
}

#: 其余 10 个 (循环, 变体) **不做**行骨架断言的实证理由（2026-08-15 逐对实测）。
#: 🔴 这不是偷懒白名单，而是「源 xlsx 披露 sheet 的行 ↔ 附注模板的行」本就不是 1:1 的
#: 实证结论：源侧是底稿录入表（常按列转置、含表头/说明/多张子表混排），
#: 附注侧是披露表（按 docx 要求组织、可有源 xlsx 没有的独立披露表）。
#: 把不成立的关系写成断言 = 锁死错值（memory 已记的假绿第③源）。
_ROW_SKELETON_NOT_ASSERTED: dict[tuple[str, str], str] = {
    ("I2", "listed"): "源侧 2 处扩位（A15 按费用性质 / A27 课题）落在**动态行表**上，"
                      "模板 rows 为空骨架由推送生成 ⇒ 模板 expandable=0 是正确形态",
    ("I2", "soe"): "源 A13「开发支出课题」扩位同样落在动态行表上，"
                   "模板 rows 为空骨架、由底稿推送生成 ⇒ 模板 expandable=0 是正确形态",
    ("I3", "listed"): "源侧 0 处扩位而模板有 2 处（商誉账面原值 / 商誉减值准备按资产组分项）"
                      "—— 附注 docx 要求按资产组逐项披露，底稿 xlsx 未留标记，模板多出是正确的",
    ("I3", "soe"): "源侧 0 处扩位、模板 expandable 也 0 处，扩位维度无信号；"
                   "两张表（商誉/商誉减值准备）的列结构已由 test_i3_soe_tables_are_flat 覆盖",
    ("I4", "listed"): "源侧 0 处扩位、模板 0 处，扩位维度无信号；源披露 sheet 的行是"
                      "「按项目逐行」的动态区（源模板只给示例行），列结构已由"
                      "test_i4_listed_two_level_headers_from_source 三向覆盖",
    ("I4", "soe"): "同上市侧（源侧 0 / 模板 0），源披露 sheet 行为动态项目区，"
                   "列结构由 _VERIFIED_TABLES 的两级表头判据覆盖",
    ("I5", "listed"): "源侧 1 处扩位（A18 其他非流动资产项目）落在动态项目行表，模板 expandable=0",
    ("I5", "soe"): "源 A17「其他非流动资产项目」扩位同样落在动态项目行表上，"
                   "模板 expandable=0；该章节另有段落泄漏表名的专项判据覆盖",
    ("I6", "listed"): "源侧 0 处而模板 1 处（研发费用按费用性质动态行），附注侧需要可扩位",
    ("I6", "soe"): "源侧 0 处扩位、模板 0 处；国企版研发费用表是固定三列"
                   "（项目/本期发生额/上期发生额），行按费用性质动态生成，"
                   "列结构已由 test_i6_columns_are_flat + test_i6_soe_table_name_matches_source 覆盖",
}


def _src_col_a(cycle: str, variant: str, r1: int, r2: int) -> list[str]:
    """openpyxl 直读源披露 sheet 首列 `[r1, r2]` 区间（去空白归一）。"""
    wb = openpyxl.load_workbook(_SRC_FILES[cycle], data_only=True)
    ws = wb[_SRC_DISCLOSURE_SHEETS[(cycle, variant)]]
    return [_norm(ws.cell(row=r, column=1).value) for r in range(r1, r2 + 1)]


def _template_table(cycle: str, variant: str, table_name: str) -> dict:
    sec = _section(cycle, variant)
    hit = [t for t in (sec.get("tables") or []) if str(t.get("name", "")) == table_name]
    assert len(hit) == 1, (
        f"{cycle}/{variant} 期望恰好一张名为 {table_name!r} 的表，实测 {len(hit)} 张"
    )
    return hit[0]


@pytest.mark.parametrize(
    "cycle,variant", sorted(_ROW_SKELETON_ASSERTED.keys())
)
def test_row_skeleton_matches_source_column_a(cycle: str, variant: str):
    """模板 rows 的 label 序列必须逐行等于源 xlsx 首列（Property 43 主判据）。"""
    table_name, r1, r2 = _ROW_SKELETON_ASSERTED[(cycle, variant)]
    src = _src_col_a(cycle, variant, r1, r2)
    tbl = _template_table(cycle, variant, table_name)
    rows = [_norm(r.get("label")) for r in (tbl.get("rows") or []) if isinstance(r, dict)]
    assert len(rows) == len(src), (
        f"{cycle}/{variant} {table_name} 行数 {len(rows)} != 源模板 "
        f"{_SRC_DISCLOSURE_SHEETS[(cycle, variant)]}!A{r1}:A{r2} 的 {len(src)} 行；"
        f"重跑 fix_note_i_cycle_structure.py --apply 可修"
    )
    bad = [
        f"第 {i} 行：模板「{t}」≠ 源模板 A{r1 + i}「{s}」"
        for i, (s, t) in enumerate(zip(src, rows))
        if s != t
    ]
    assert not bad, f"{cycle}/{variant} {table_name} 行标签与源模板不符：{bad}"


@pytest.mark.parametrize(
    "cycle,variant", sorted(_ROW_SKELETON_ASSERTED.keys())
)
def test_row_skeleton_expandable_count_matches_source(cycle: str, variant: str):
    """模板 `expandable` 行数必须等于源模板首列 `……` 标记数（Property 43 扩位判据）。

    这是把 `_SRC_DYNAMIC_MARK_COUNT`（只锁源侧）延伸到**消费侧**的一条边 ——
    改造前 I1 上市源侧 3 处、模板侧 4 处，旧判据结构上看不见这个差。
    """
    table_name, _r1, _r2 = _ROW_SKELETON_ASSERTED[(cycle, variant)]
    tbl = _template_table(cycle, variant, table_name)
    actual = sum(
        1
        for r in (tbl.get("rows") or [])
        if isinstance(r, dict) and str(r.get("row_type") or "") == "expandable"
    )
    expected = _SRC_DYNAMIC_MARK_COUNT[(cycle, variant)]
    assert actual == expected, (
        f"{cycle}/{variant} {table_name} 模板 expandable 行 {actual} 处 != 源模板首列 "
        f"`……` 标记 {expected} 处 ⇒ 要么凭空多了可扩位、要么真实可扩位被抹掉"
    )


def test_row_skeleton_registry_covers_all_twelve():
    """反向自检：12 个 (循环,变体) 必须**恰好**被两张登记表二分，不漏不重。"""
    asserted = set(_ROW_SKELETON_ASSERTED)
    skipped = set(_ROW_SKELETON_NOT_ASSERTED)
    assert not (asserted & skipped), f"同时出现在两张登记表：{sorted(asserted & skipped)}"
    assert asserted | skipped == set(_SECTION_MAP), (
        "行骨架登记表未覆盖全部 12 个 (循环,变体)："
        f"缺 {sorted(set(_SECTION_MAP) - asserted - skipped)}"
    )
    for key, reason in _ROW_SKELETON_NOT_ASSERTED.items():
        assert len(reason) >= 20, f"{key} 的免断言理由过短（≥20 字），疑似空话：{reason!r}"


def test_row_skeleton_source_anchors_still_valid():
    """反向自检：源侧行区间锚点仍有效（防源模板改版后区间漂移、判据比空气）。

    判据 = 区间**内**首末格非空 + 区间**外**紧邻的下一格不是数据行的延续
    （listed A49 = 「说明：」段落 / soe A60 = 「说明：」段落）。
    """
    for (cycle, variant), (_name, r1, r2) in _ROW_SKELETON_ASSERTED.items():
        rows = _src_col_a(cycle, variant, r1, r2)
        assert rows[0] and rows[-1], (
            f"{cycle}/{variant} 行区间 A{r1}:A{r2} 端点为空 ⇒ 锚点已漂移"
        )
        assert rows[0].startswith("一、"), (
            f"{cycle}/{variant} A{r1} 应是第一层标题（以「一、」开头），实测 {rows[0]!r}"
        )
        nxt = _src_col_a(cycle, variant, r2 + 1, r2 + 1)[0]
        assert nxt.startswith("说明"), (
            f"{cycle}/{variant} A{r2 + 1} 应是「说明：」段落（=数据区结束），实测 {nxt!r}"
        )


def test_row_skeleton_impairment_decrease_has_three_details():
    """点名钉死本轮修的那处：I1 两层减少段结构必须**三层一致**。

    源模板账面原值 / 累计摊销 / 减值准备三层的减少段都是
    「（1）处置 / （2）失效且终止确认的部分 / （3）其他减少」，无扩位。
    改造前只有减值准备层缺了「失效且终止确认的部分」并多了 `……`
    ⇒ 一旦有人按旧形态改回去，本条立刻打红并指名道姓。
    """
    tbl = _template_table("I1", "listed", "无形资产情况")
    rows = [_norm(r.get("label")) for r in (tbl.get("rows") or [])]
    dec_starts = [i for i, lb in enumerate(rows) if lb == "3.本期减少金额"]
    assert len(dec_starts) == 3, f"应有三层减少段，实测 {len(dec_starts)} 处：{rows}"
    want = ("（1）处置", "（2）失效且终止确认的部分", "（3）其他减少")
    for at in dec_starts:
        got = tuple(rows[at + 1 : at + 4])
        assert got == want, (
            f"第 {at} 行「3.本期减少金额」之后三个明细应为 {want}，实测 {got}"
        )
        assert rows[at + 4] == "4.期末余额", (
            f"减少段后应直接是「4.期末余额」（无扩位），实测 {rows[at + 4]!r}"
        )
