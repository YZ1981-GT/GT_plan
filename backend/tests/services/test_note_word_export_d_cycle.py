"""D 类剩余循环（D6 合同资产）附注两级表头的 Word 导出结构验证。

D3/D5/D7 全为单级表头（`flat`），不走两级路径；D6 有 4 张两级表头表
（上市主表 / 减值计提情况 ×2 / 组合明细，国企主表 + 减值准备变动），
必须验证 `note_word_exporter._build_two_level_header_rows` 对**混合分组**的处理：

- row 0 的 colspan 之和 == 总列数
- 🔴 row 1 只放分组内子列名，**不得**为 rowspan=2 的独立列补空占位
  （多补占位会让子列名整体右移、末列被丢弃 —— 存货章节曾实测中招）
- 独立列（标签列 / 减值表「账面价值」/ 国企「期初数」「期末数」「原因」）rowspan=2

spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 7.2
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_word_exporter import _build_two_level_header_rows

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

SECTION = {"listed": "五、10", "soe": "八、11"}
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


def _two_level() -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = []
    for variant in ("listed", "soe"):
        for t in _tables(variant):
            if t.get("_column_groups"):
                out.append((variant, str(t.get("name", "")), t))
    return out


TWO_LEVEL = _two_level()
IDS = [f"{v}:{n}" for v, n, _ in TWO_LEVEL]


def test_two_level_table_count() -> None:
    """上市 5 张（主表 + 减值 ×2 + 组合骨架 ×2）+ 国企 2 张（主表 + 减值准备）。"""
    assert len(TWO_LEVEL) >= 7, f"两级表头表过少（{len(TWO_LEVEL)}），_column_groups 可能被清空"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_row0_covers_all_columns(variant: str, name: str, tbl: dict) -> None:
    headers = tbl["headers"]
    row0, _ = _build_two_level_header_rows(headers, tbl["_column_groups"])
    assert sum(c["colspan"] for c in row0) == len(headers), f"{name} row0 覆盖列数错：{row0}"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_row1_has_only_grouped_subcolumns(variant: str, name: str, tbl: dict) -> None:
    headers = tbl["headers"]
    groups = tbl["_column_groups"]
    _, row1 = _build_two_level_header_rows(headers, groups)
    grouped_cols = sum(int(g["span"]) for g in groups)
    assert len(row1) == grouped_cols, f"{name} row1 长度应为 {grouped_cols}，实际 {len(row1)}"
    assert all(c["colspan"] == 1 and c["rowspan"] == 1 for c in row1), f"{name} row1 不应合并"
    assert all(str(c["text"]).strip() for c in row1), f"{name} row1 含空子列名：{row1}"


@pytest.mark.parametrize(("variant", "name", "tbl"), TWO_LEVEL, ids=IDS)
def test_ungrouped_columns_span_two_rows(variant: str, name: str, tbl: dict) -> None:
    headers = tbl["headers"]
    groups = tbl["_column_groups"]
    covered = {i for g in groups for i in range(int(g["start"]), int(g["start"]) + int(g["span"]))}
    ungrouped = [h for i, h in enumerate(headers) if i not in covered]
    row0, _ = _build_two_level_header_rows(headers, groups)
    assert [c["text"] for c in row0 if c["rowspan"] == 2] == ungrouped, f"{name} 独立列 rowspan 错"


def _table(variant: str, name: str) -> dict:
    for t in _tables(variant):
        if str(t.get("name", "")) == name:
            return t
    pytest.fail(f"{variant} 缺表「{name}」")


def _rows(variant: str, name: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    tbl = _table(variant, name)
    row0, row1 = _build_two_level_header_rows(tbl["headers"], tbl["_column_groups"])
    return (
        [(c["text"], c["colspan"], c["rowspan"]) for c in row0],
        [c["text"] for c in row1],
    )


def test_listed_main_header() -> None:
    row0, row1 = _rows("listed", "合同资产")
    assert row0 == [("项  目", 1, 2), ("期末余额", 3, 1), ("上年年末余额", 3, 1)]
    assert row1 == ["账面余额", "减值准备", "账面价值"] * 2


def test_soe_main_header() -> None:
    row0, row1 = _rows("soe", "合同资产情况")
    assert row0 == [("项  目", 1, 2), ("期末数", 3, 1), ("期初数", 3, 1)]
    assert row1 == ["账面余额", "减值准备", "账面价值"] * 2


@pytest.mark.parametrize(
    "name",
    ["合同资产减值准备计提情况（期末余额）", "合同资产减值准备计提情况（续：上年年末余额）"],
)
def test_listed_impairment_mixed_grouping(name: str) -> None:
    """混合分组：账面余额/减值准备各跨 2 列，账面价值独立跨 2 行。"""
    row0, row1 = _rows("listed", name)
    assert row0 == [
        ("类别", 1, 2),
        ("账面余额", 2, 1),
        ("减值准备", 2, 1),
        ("账面价值", 1, 2),
    ]
    assert row1 == ["金额", "比例(%)", "金额", "预期信用损失率(%)"]


def test_soe_impairment_movement_mixed_grouping() -> None:
    row0, row1 = _rows("soe", "合同资产减值准备")
    assert row0 == [
        ("项  目", 1, 2),
        ("期初数", 1, 2),
        ("本期变动金额", 3, 1),
        ("期末数", 1, 2),
        ("原因", 1, 2),
    ]
    assert row1 == ["计提", "转回", "转销/核销"]


def test_listed_group_table_header() -> None:
    row0, row1 = _rows("listed", "组合计提项目：工程施工")
    assert row0 == [("账  龄", 1, 2), ("期末余额", 3, 1), ("上年年末余额", 3, 1)]
    assert row1 == ["合同资产", "坏账准备", "预期信用损失率(%)"] * 2


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_flat_tables_have_no_column_groups(variant: str) -> None:
    offenders = [
        t.get("name")
        for t in _tables(variant)
        if any(c.get("flat") for c in (t.get("columns") or []))
        and t.get("_column_groups") is not None
    ]
    assert offenders == [], offenders
