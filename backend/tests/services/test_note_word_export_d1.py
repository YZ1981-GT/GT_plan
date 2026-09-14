"""D1 应收票据附注两级表头的 Word 导出结构验证。

背景：D1 第一阶段给 五、4 / 八、4 的 9 张表补了 `_column_groups`（含**混合分组**——
部分列有 `group`、部分列是 rowspan=2 的独立列，如国企分类表的「账面价值」、
变动表的「期初数」「期末数」）。浏览器侧已实测渲染正确，但 Word 导出走的是
另一条路径（`note_word_exporter._build_two_level_header_rows` → `fill_multi_header`），
此前未验证。

`_build_two_level_header_rows` 有一条容易回归的约定：**row 1 不得为 rowspan=2 的
无分组列补空占位**（`fill_multi_header` 内部会自动跳过被上方 rowspan 占用的列位，
多补占位会让子列名整体右移、末列被丢弃 —— 存货章节曾实测中招）。本测试用 D1 的
真实模板数据把这条约定钉住。

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ P2-3
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_word_exporter import _build_two_level_header_rows

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

SECTION = {"listed": "五、4", "soe": "八、4"}
TEMPLATE = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}


def _tables(variant: str) -> list[dict]:
    doc = json.loads(TEMPLATE[variant].read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == SECTION[variant]:
            return sec.get("tables") or []
    pytest.fail(f"缺章节 {SECTION[variant]}")


def _two_level_tables() -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = []
    for variant in ("listed", "soe"):
        for t in _tables(variant):
            if t.get("_column_groups"):
                out.append((variant, str(t.get("name", "")), t))
    return out


TWO_LEVEL = _two_level_tables()
IDS = [f"{v}:{n}" for v, n, _ in TWO_LEVEL]


def test_two_level_table_count() -> None:
    """五、4 有 4 张（主表 + 分类表 ×2 + 组合表 ×2 = 5）、八、4 有 4 张。

    实际张数以模板为准，此处只锁「必须有」以防 `_column_groups` 被整体清掉。
    """
    assert len(TWO_LEVEL) >= 8, f"两级表头表过少（{len(TWO_LEVEL)}），_column_groups 可能被清空"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_row0_covers_all_columns(variant: str, name: str, tbl: dict) -> None:
    """row 0 的 colspan 之和必须等于总列数（否则 Word 表头缺列或越界）。"""
    headers = tbl["headers"]
    row0, _row1 = _build_two_level_header_rows(headers, tbl["_column_groups"])
    assert sum(c["colspan"] for c in row0) == len(headers), (
        f"{name} row0 覆盖列数 != {len(headers)}：{row0}"
    )


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_row1_has_only_grouped_subcolumns(variant: str, name: str, tbl: dict) -> None:
    """🔴 row 1 只放分组内子列名，**不得**为 rowspan=2 的独立列补空占位。

    补了占位会挤掉一个真实列位 → 子列名整体右移、末列被丢弃
    （存货章节实测：「账面价值」「比例(%)」曾消失）。
    """
    headers = tbl["headers"]
    groups = tbl["_column_groups"]
    row0, row1 = _build_two_level_header_rows(headers, groups)
    grouped_cols = sum(int(g["span"]) for g in groups)
    assert len(row1) == grouped_cols, f"{name} row1 长度应为分组列数 {grouped_cols}，实际 {len(row1)}"
    assert all(c["colspan"] == 1 and c["rowspan"] == 1 for c in row1), f"{name} row1 不应有合并"
    assert all(str(c["text"]).strip() for c in row1), f"{name} row1 含空子列名：{row1}"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_ungrouped_columns_span_two_rows(variant: str, name: str, tbl: dict) -> None:
    """独立列（标签列 / 国企分类表账面价值 / 变动表期初数·期末数）纵向合并 2 行。"""
    headers = tbl["headers"]
    groups = tbl["_column_groups"]
    covered = {i for g in groups for i in range(int(g["start"]), int(g["start"]) + int(g["span"]))}
    ungrouped_headers = [h for i, h in enumerate(headers) if i not in covered]
    row0, _ = _build_two_level_header_rows(headers, groups)
    rowspan2 = [c["text"] for c in row0 if c["rowspan"] == 2]
    assert rowspan2 == ungrouped_headers, f"{name} 独立列应 rowspan=2：期望 {ungrouped_headers}，实际 {rowspan2}"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_group_names_appear_in_row0(variant: str, name: str, tbl: dict) -> None:
    """分组名必须出现在 row 0 且 colspan 与 span 一致。"""
    row0, _ = _build_two_level_header_rows(tbl["headers"], tbl["_column_groups"])
    by_name = {c["text"]: c for c in row0}
    for g in tbl["_column_groups"]:
        cell = by_name.get(g["group"])
        assert cell is not None, f"{name} row0 缺分组名「{g['group']}」"
        assert cell["colspan"] == int(g["span"])
        assert cell["rowspan"] == 1


# ─── 逐表钉死关键结构（防 group 定义被悄悄改动）─────────────────────────────


def _table(variant: str, name: str) -> dict:
    for t in _tables(variant):
        if str(t.get("name", "")) == name:
            return t
    pytest.fail(f"{variant} 缺表「{name}」")


def _row_texts(variant: str, name: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    tbl = _table(variant, name)
    row0, row1 = _build_two_level_header_rows(tbl["headers"], tbl["_column_groups"])
    return (
        [(c["text"], c["colspan"], c["rowspan"]) for c in row0],
        [c["text"] for c in row1],
    )


def test_listed_main_table_header() -> None:
    row0, row1 = _row_texts("listed", "应收票据")
    assert row0 == [
        ("票据种类", 1, 2),
        ("期末余额", 3, 1),
        ("上年年末余额", 3, 1),
    ]
    assert row1 == ["账面余额", "坏账准备", "账面价值"] * 2


def test_soe_main_table_header() -> None:
    row0, row1 = _row_texts("soe", "应收票据分类")
    assert row0 == [
        ("票据种类", 1, 2),
        ("期末数", 3, 1),
        ("期初数", 3, 1),
    ]
    assert row1 == ["账面余额", "坏账准备", "账面价值"] * 2


def test_soe_class_table_mixed_grouping() -> None:
    """国企分类表是**混合分组**：账面余额/坏账准备各跨 2 列，账面价值独立跨 2 行。"""
    row0, row1 = _row_texts("soe", "按坏账准备计提方法分类披露应收票据（期末数）")
    assert row0 == [
        ("类别", 1, 2),
        ("账面余额", 2, 1),
        ("坏账准备", 2, 1),
        ("账面价值", 1, 2),
    ]
    assert row1 == ["金额", "比例(%)", "金额", "预期信用损失率(%)"]


def test_soe_movement_table_mixed_grouping() -> None:
    """国企变动表：期初数 / 期末数 独立跨 2 行，本期变动情况跨 4 列。"""
    row0, row1 = _row_texts("soe", "本期计提、收回或转回的应收票据坏账准备情况")
    assert row0 == [
        ("类别", 1, 2),
        ("期初数", 1, 2),
        ("本期变动情况", 4, 1),
        ("期末数", 1, 2),
    ]
    assert row1 == ["计提", "收回或转回", "核销", "其他变动"]


def test_listed_portfolio_table_header() -> None:
    row0, row1 = _row_texts("listed", "组合计提项目：银行承兑汇票")
    assert row0 == [
        ("名称", 1, 2),
        ("期末余额", 3, 1),
        ("上年年末余额", 3, 1),
    ]
    assert row1 == ["应收票据", "坏账准备", "预期信用损失率(%)"] * 2


def test_listed_class_table_single_group() -> None:
    """上市分类表：期间父表头跨全部 5 个数据列（源模板 B38:F38 合并）。"""
    row0, row1 = _row_texts("listed", "按坏账计提方法分类（期末余额）")
    assert row0 == [("类别", 1, 2), ("期末余额", 5, 1)]
    assert row1 == ["金额", "比例(%)", "坏账准备", "预期信用损失率(%)", "账面价值"]


# ─── 单级表头的表不得进两级路径 ───────────────────────────────────────────────


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_flat_tables_have_no_column_groups(variant: str) -> None:
    """标了 `flat` 的表必须没有 `_column_groups`（否则 Word 会渲出凭空父表头）。"""
    offenders = []
    for t in _tables(variant):
        cols = t.get("columns") or []
        if any(c.get("flat") for c in cols) and t.get("_column_groups") is not None:
            offenders.append(t.get("name"))
    assert offenders == [], offenders
