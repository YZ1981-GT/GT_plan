"""I1 上市披露主表的列集 / 类别真源 / 文案 HTML 守卫（Property 18 / 19 + 表名文案）。

从 `test_note_i_cycle_structure.py` 拆出（该文件 1671 行超 pre-commit 的 800 行门禁）。
共享基线常量与 helper 仍在核心文件，本文件只引用不复制 —— 复制一份就等于把当时的值
当基线锁死（本 spec 反复踩过的假绿第③源）。
"""
from __future__ import annotations

import re

import openpyxl
import pytest

from tests.test_note_i_cycle_structure import (  # noqa: F401
    _DYNAMIC_MARK_RE,
    _SRC_DISCLOSURE_SHEETS,
    _SRC_DYNAMIC_MARK_COUNT,
    _SRC_FILES,
    _norm,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 18 / 19：I1 上市列集与类别真源 ↔ 源模板交叉锁死
#
# 🔴 **基线一律以 openpyxl 逐格实测为准，不照抄 spec 文本**（2026-08-12 实测）：
#   design.md 的 Property 19 写「`底稿目录!A9:A19`（12 类）」——
#   而 A9:A19 只有 **11** 个单元格、逐格读出的也是 11 个类别名，
#   `i1_asset_categories.I1_ASSET_CATEGORIES` 同样是 11 条。按「12 类」写断言
#   会把错值当基线锁死（平台已记的第三类假绿）。
#
# 源模板实证（`I1 无形资产、累计摊销及减值准备.xlsx`）：
#   `底稿目录!A8`  = 「无形资产类别设置（以下内容请根据实际情况修改）：」
#   `底稿目录!A9:A19` = 土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 /
#                       著作权 / 特许经营权 / 软件 / 矿产权 / 数据资源 / 其他（11 个）
#   `底稿目录!A20` = 「……」（动态扩位）
#   `附注披露信息（上市公司）!A10:M10` = 「项目」+ 上述 11 类 + 「合计」= **13 列**
#   row10/row11 **无合并单元格** ⇒ 单级表头（不是两级）
# ═══════════════════════════════════════════════════════════════════════════════


#: 类别真源单元格区间（`底稿目录`）—— 起止行由源模板实证冻结
_I1_CATEGORY_SHEET = "底稿目录"
_I1_CATEGORY_FIRST_ROW = 9
_I1_CATEGORY_LAST_ROW = 19
#: 类别区上方的标题格（锚点有效性自检用）
_I1_CATEGORY_TITLE_CELL = "A8"
_I1_CATEGORY_TITLE_TEXT = "无形资产类别设置"
#: 类别区下方的动态扩位格
_I1_CATEGORY_EXPAND_CELL = "A20"

#: 上市披露主表表头行与列区间
_I1_LISTED_HEADER_ROW = 10
_I1_LISTED_LABEL_COL = 1   # A：「项目」
_I1_LISTED_TOTAL_COL = 13  # M：「合计」


def _i1_workbook():
    return openpyxl.load_workbook(_SRC_FILES["I1"], data_only=True)


def _i1_category_labels_from_source() -> list[str]:
    """openpyxl 直读 `底稿目录!A9:A19` 的类别名（去空白 + 去「其中：」前缀）。"""
    ws = _i1_workbook()[_I1_CATEGORY_SHEET]
    out: list[str] = []
    for row in range(_I1_CATEGORY_FIRST_ROW, _I1_CATEGORY_LAST_ROW + 1):
        raw = _norm(ws.cell(row=row, column=1).value)
        out.append(re.sub(r"^其中[:：]", "", raw))
    return out


def _load_i1_categories():
    """导入类别声明模块（延迟导入：避免拉起 DB 依赖）。"""
    from app.services.four_table import i1_asset_categories as mod

    return mod


# ─── Property 19：类别真源派生自源模板，且 source_ref 可回溯 ───────────────────


def test_i1_category_source_anchor_still_valid():
    """反向自检：类别区的标题格与扩位格必须仍在原处 —— 否则行区间已漂移。

    没有这条，`A9:A19` 换了位置时下面几条会静静地读到别的内容（读到空串也算「一致」）。
    """
    ws = _i1_workbook()[_I1_CATEGORY_SHEET]
    title = _norm(ws[_I1_CATEGORY_TITLE_CELL].value)
    assert _I1_CATEGORY_TITLE_TEXT in title, (
        f"{_I1_CATEGORY_SHEET}!{_I1_CATEGORY_TITLE_CELL} 已不含 "
        f"{_I1_CATEGORY_TITLE_TEXT!r}（实为 {title!r}）⇒ 类别区行号漂移，"
        f"_I1_CATEGORY_FIRST_ROW/_LAST_ROW 需重新实测"
    )
    expand = _norm(ws[_I1_CATEGORY_EXPAND_CELL].value)
    assert _DYNAMIC_MARK_RE.fullmatch(expand), (
        f"{_I1_CATEGORY_SHEET}!{_I1_CATEGORY_EXPAND_CELL} 应是动态扩位标记，"
        f"实为 {expand!r} ⇒ 类别区末行漂移"
    )
    labels = _i1_category_labels_from_source()
    assert all(labels), f"类别区有空格：{labels}"
    assert len(labels) == 11, (
        f"源模板 `底稿目录!A9:A19` 实测 {len(labels)} 个类别（冻结基线 11）。"
        f"🔴 spec design.md 写的「12 类」与源模板不符，以本条实测为准：{labels}"
    )


def test_i1_category_labels_match_source_template():
    """`I1_ASSET_CATEGORIES` 按 `seq` 排序后的 label 必须逐字等于源模板行序。

    🔴 用 `seq` 而不是声明顺序：声明顺序是**归类优先级**（`非专利技术` 必须先于
    `专利权`，后者是前者子串），`seq` 才是展示/行序。两者混用会让本条恒红或恒绿。
    """
    mod = _load_i1_categories()
    declared = [c.label for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)]
    assert declared == _i1_category_labels_from_source(), (
        f"类别声明（按 seq）与源模板 `底稿目录!A9:A19` 不一致：\n"
        f"  声明 = {declared}\n  源表 = {_i1_category_labels_from_source()}"
    )


def test_i1_category_seq_is_dense_and_one_based():
    """`seq` 必须是 1..N 连续无空洞 —— 否则列序/行序会出现跳号或重叠。"""
    mod = _load_i1_categories()
    seqs = sorted(c.seq for c in mod.I1_ASSET_CATEGORIES)
    assert seqs == list(range(1, len(seqs) + 1)), f"seq 非 1..N 连续：{seqs}"


def test_i1_category_source_ref_not_stale():
    """stale 检测：每个类别的 `source_ref` 指向的单元格必须仍含该 label。

    源模板一改动即打红（对齐平台已有的 `test_note_expandable_rows` 范式）。
    """
    mod = _load_i1_categories()
    wb = _i1_workbook()
    offenders: list[str] = []
    checked = 0
    for cat in mod.I1_ASSET_CATEGORIES:
        assert cat.source_ref, f"类别 {cat.key} 缺 source_ref 证据"
        hit = False
        for ref in cat.source_ref:
            sheet, _, cell = str(ref).partition("!")
            if sheet not in wb.sheetnames:
                offenders.append(f"{cat.key}: sheet {sheet!r} 不存在")
                continue
            checked += 1
            val = re.sub(r"^其中[:：]", "", _norm(wb[sheet][cell].value))
            if _norm(cat.label) in val:
                hit = True
        if not hit:
            refs = [f"{r}={_norm(wb[r.split('!')[0]][r.split('!')[1]].value)!r}"
                    for r in cat.source_ref if r.split("!")[0] in wb.sheetnames]
            offenders.append(f"{cat.key}({cat.label}): 无一命中 —— {refs}")
    assert checked >= len(mod.I1_ASSET_CATEGORIES), (
        f"只校验了 {checked} 个 source_ref 单元格 / {len(mod.I1_ASSET_CATEGORIES)} 个类别 "
        f"⇒ 判据在空转"
    )
    assert not offenders, f"source_ref stale：{offenders}"


def test_i1_category_defs_payload_matches_declaration():
    """下发给前端的 `category_defs_payload()` 必须与声明同序同值（无第二份真源）。"""
    mod = _load_i1_categories()
    payload = mod.category_defs_payload()
    expected = [
        {"key": c.key, "label": c.label, "seq": c.seq}
        for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)
    ]
    assert [
        {"key": p["key"], "label": p["label"], "seq": p["seq"]} for p in payload
    ] == expected, f"payload 与声明漂移：\n  payload={payload}\n  expected={expected}"


def test_i1_category_other_is_last_wide_fallback():
    """`其他` 必须是 seq 最大（列尾/行尾）且归类优先级最低（宽兜底放最后）。"""
    mod = _load_i1_categories()
    other = next(c for c in mod.I1_ASSET_CATEGORIES if c.key == mod.CATEGORY_OTHER)
    assert other.seq == max(c.seq for c in mod.I1_ASSET_CATEGORIES), "「其他」不在末位"
    assert other.priority == max(c.priority for c in mod.I1_ASSET_CATEGORIES), (
        "「其他」的 priority 不是最大 ⇒ 会抢在具体类别之前命中"
    )


# ─── Property 18：I1 上市披露主表列集 = 项目 + 11 类 + 合计 = 13 列 ─────────────


def test_i1_listed_header_is_13_columns():
    """`附注披露信息（上市公司）!A10:M10` 必须是 13 个非空列且第 14 列起为空。"""
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    vals = [
        _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=c).value)
        for c in range(1, _I1_LISTED_TOTAL_COL + 1)
    ]
    assert all(vals), f"A10:M10 有空列：{vals}"
    assert len(vals) == 13, f"列数应为 13，实为 {len(vals)}"
    # 反向自检：第 14 列必须为空（否则真实列数 >13，冻结基线过期）
    beyond = _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=_I1_LISTED_TOTAL_COL + 1).value)
    assert not beyond, f"N10 非空（{beyond!r}）⇒ 实际列数 >13，基线需重新实测"


def test_i1_listed_header_middle_equals_category_labels():
    """B10:L10 逐格等于类别真源（按 seq 排序），A10=「项目」、M10=「合计」。

    这是 Property 18 的核心：披露主表列集**由类别真源派生**，不是另抄一份。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    row = [
        _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=c).value)
        for c in range(1, _I1_LISTED_TOTAL_COL + 1)
    ]
    assert row[0] == "项目", f"A10 应为「项目」，实为 {row[0]!r}"
    assert row[-1] == "合计", f"M10 应为「合计」，实为 {row[-1]!r}"
    mod = _load_i1_categories()
    declared = [c.label for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)]
    assert row[1:-1] == declared, (
        f"B10:L10 与类别声明（按 seq）不一致：\n"
        f"  表头 = {row[1:-1]}\n  声明 = {declared}"
    )


def test_i1_listed_header_is_single_level():
    """表头行**无合并单元格** ⇒ 单级（flat），不得按两级 group 渲染。

    实测 row10/row11 相关合并为空。若源模板改成两级表头，本条会打红，
    提醒同步改前端 `buildI1ListedColumns` 的表态与附注模板的 `_column_groups`。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    merged = [
        str(rng)
        for rng in ws.merged_cells.ranges
        if rng.min_row <= _I1_LISTED_HEADER_ROW + 1 and rng.max_row >= _I1_LISTED_HEADER_ROW
    ]
    assert not merged, (
        f"表头行出现合并单元格 {merged} ⇒ 源模板已改为两级表头，"
        f"前端列表态与附注 _column_groups 需同步改造"
    )


def test_i1_listed_layer_titles_and_expand_marks_align():
    """四个层标题 + 三个动态扩位的相对位置必须成立（扩位在层内、不越层）。

    实证：层标题 A11/A24/A35/A46（一、账面原值 / 二、累计摊销 / 三、减值准备 / 四、账面价值），
    扩位 A18/A29/A40 —— 各落在前三层内部，第四层（账面价值，派生层）无扩位。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    layer_rows: list[int] = []
    mark_rows: list[int] = []
    for row in range(_I1_LISTED_HEADER_ROW, ws.max_row + 1):
        text = _norm(ws.cell(row=row, column=1).value)
        if not text:
            continue
        if _DYNAMIC_MARK_RE.fullmatch(text):
            mark_rows.append(row)
        elif re.match(r"^[一二三四五六]、", text):
            layer_rows.append(row)
    assert len(layer_rows) == 4, f"应有 4 个层标题，实测 {layer_rows}"
    assert len(mark_rows) == _SRC_DYNAMIC_MARK_COUNT[("I1", "listed")], (
        f"动态扩位数与冻结基线不一致：实测 {mark_rows}，"
        f"基线 {_SRC_DYNAMIC_MARK_COUNT[('I1', 'listed')]}"
    )
    # 每个扩位都必须落在某层标题之后、下一层标题之前
    for mark in mark_rows:
        enclosing = [r for r in layer_rows if r < mark]
        assert enclosing, f"扩位 A{mark} 出现在第一个层标题之前"
        nxt = [r for r in layer_rows if r > mark]
        assert nxt, f"扩位 A{mark} 落在最后一层之后（第四层是派生层，不该有扩位）"
    # 第四层（账面价值，由前三层推导）不得有扩位
    assert all(m < layer_rows[3] for m in mark_rows), (
        f"第四层（A{layer_rows[3]} 账面价值）内出现扩位 {[m for m in mark_rows if m > layer_rows[3]]}"
        f" —— 该层是派生层，不应可扩"
    )
