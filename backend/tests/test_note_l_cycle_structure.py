# -*- coding: utf-8 -*-
"""L 循环附注章节结构守卫（L7 其他非流动负债 / L8 财务费用）。

锁死 `fix_note_l_cycle_structure.py` 的修订结果，防后续 md 重建 / 并发会话回退：

- 表名正名（五、52 原为表头首格泄漏名 `项  目`）
- 四张表 columns 齐备且**显式 flat**（单级表头，抑制后端前缀推断）
- 财务费用两版行集 = 源 xlsx r7~r18 共 12 行，且两版**完全相同**
- 八、57 `……` 占位行已删
- guidance 齐备
- **反向自检**：断言脚本能被 import 且 `--check` 语义可用（防守卫空转）

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 4.5 / 4.6
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIX_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix" / "fix_note_l_cycle_structure.py"

# 源 xlsx `L8 财务费用.xlsx` 两个披露 sheet 的 r7~r18 逐字行清单
FINANCE_COST_LABELS = [
    "利息费用总额",
    "减：利息资本化",
    "利息费用",
    "减：利息收入",
    "利息净支出",
    "承兑汇票贴息",
    "汇兑损失",
    "减：汇兑收益",
    "减：汇兑损益资本化",
    "汇兑净损失",
    "手续费及其他",
    "合计",
]

TARGETS = {
    "l5-listed": ("note_template_listed.json", "五、48", "长期应付款"),
    "l5-soe": ("note_template_soe.json", "八、53", "长期应付款"),
    "l5-soe-within1y": ("note_template_soe.json", "八、47", "（3）一年内到期的长期应付款"),
    "l7-listed": ("note_template_listed.json", "五、52", "其他非流动负债"),
    "l7-soe": ("note_template_soe.json", "八、57", "其他非流动负债"),
    "l8-listed": ("note_template_listed.json", "五、67", "财务费用（按费用性质列示）"),
    "l8-soe": ("note_template_soe.json", "八、68", "财务费用"),
}

# 五、48 / 八、53 各含 3 张表（主表 + 明细/前5 项 + 专项应付款）
L5_LISTED_TABLES = ["长期应付款", "长期应付款（按款项性质列示）", "专项应付款"]
L5_SOE_TABLES = ["长期应付款", "①长期应付款项期末余额最大的前5 项", "①专项应付款期末余额最大的前5 项"]


def _load_section(file_name: str, section_number: str) -> dict:
    doc = json.loads((DATA_DIR / file_name).read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number")) == section_number:
            return sec
    pytest.fail(f"未找到章节 {section_number}（{file_name}）")


def _table(section: dict, name: str) -> dict:
    for tbl in section.get("tables") or []:
        if str(tbl.get("name")) == name:
            return tbl
    names = [t.get("name") for t in section.get("tables") or []]
    pytest.fail(f"未找到表「{name}」，现有：{names}")


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_table_exists_with_expected_name(key: str) -> None:
    file_name, section_number, table_name = TARGETS[key]
    section = _load_section(file_name, section_number)
    tbl = _table(section, table_name)
    assert tbl.get("name") == table_name


def test_l7_listed_table_renamed_from_header_leak() -> None:
    """五、52 表名原是表头首格泄漏 `项  目`，必须已正名。"""
    section = _load_section("note_template_listed.json", "五、52")
    names = [str(t.get("name")) for t in section.get("tables") or []]
    assert "项  目" not in names, "表头首格泄漏名未清理"
    assert "其他非流动负债" in names


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_columns_present_and_flat(key: str) -> None:
    """主表都是源模板单行表头 → columns 齐备 + 显式 flat + 无 group。"""
    file_name, section_number, table_name = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    cols = tbl.get("columns") or []
    assert len(cols) >= 3, f"{table_name} columns={len(cols)}，至少 3 列"
    assert cols[0].get("is_label") is True, "首列未标 is_label"
    assert any(c.get("flat") for c in cols), "未表态 flat（后端会凭空推断父表头）"
    assert not any(c.get("group") for c in cols), "单级表头不应有 group"
    assert tbl.get("_column_groups") is None, "单级表头残留 _column_groups"
    # headers 与 columns 对齐且纯文本
    headers = tbl.get("headers") or []
    assert len(headers) == len(cols)
    assert headers[0] == cols[0].get("label")
    assert not any("<" in str(h) for h in headers), "headers 含 HTML"


def test_l5_sections_have_three_tables() -> None:
    """五、48 / 八、53 各须含 3 张表（主表 + 明细/前5 项 + 专项应付款）。"""
    listed = _load_section("note_template_listed.json", "五、48")
    soe = _load_section("note_template_soe.json", "八、53")
    assert [t["name"] for t in listed["tables"]] == L5_LISTED_TABLES
    assert [t["name"] for t in soe["tables"]] == L5_SOE_TABLES


@pytest.mark.parametrize(
    "file_name,section_number,table_name",
    [
        ("note_template_listed.json", "五、48", "长期应付款（按款项性质列示）"),
        ("note_template_listed.json", "五、48", "专项应付款"),
        ("note_template_soe.json", "八、53", "①长期应付款项期末余额最大的前5 项"),
        ("note_template_soe.json", "八、53", "①专项应付款期末余额最大的前5 项"),
    ],
)
def test_l5_extra_tables_have_columns_and_guidance(file_name, section_number, table_name) -> None:
    """L5 三张表全部补齐 columns(flat) + guidance。"""
    tbl = _table(_load_section(file_name, section_number), table_name)
    cols = tbl.get("columns") or []
    assert len(cols) >= 3
    assert any(c.get("flat") for c in cols), f"{table_name} 未表态 flat"
    assert str(tbl.get("guidance") or "").strip(), f"{table_name} 缺 guidance"


def test_l5_soe_top5_placeholder_rows_are_blank() -> None:
    """八、53「前5 项」的序号占位 `1．`~`5．` 必须已改空白骨架（否则推占位披露行）。"""
    tbl = _table(_load_section("note_template_soe.json", "八、53"), "①长期应付款项期末余额最大的前5 项")
    labels = [str(r.get("label", "")) for r in tbl.get("rows") or []]
    for placeholder in ("1．", "2．", "3．", "4．", "5．"):
        assert placeholder not in labels, f"序号占位行 {placeholder} 未清理"
    # 应有「其他」「小计」「合计」结构行
    assert "其他" in labels
    assert any(str(r.get("label")).replace(" ", "") == "小计" for r in tbl.get("rows"))


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_guidance_present(key: str) -> None:
    file_name, section_number, table_name = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    assert str(tbl.get("guidance") or "").strip(), f"{table_name} 缺 guidance"


@pytest.mark.parametrize("key", ["l8-listed", "l8-soe"])
def test_finance_cost_rows_match_source_template(key: str) -> None:
    """财务费用行集 = 源 xlsx 12 行，逐字逐序。"""
    file_name, section_number, table_name = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    labels = [str(r.get("label")) for r in tbl.get("rows") or []]
    assert labels == FINANCE_COST_LABELS


def test_finance_cost_rows_identical_across_variants() -> None:
    """两版行集必须完全相同（源 xlsx 实证；组件原先各自造 7 / 10 行）。"""
    listed = _table(_load_section("note_template_listed.json", "五、67"), "财务费用（按费用性质列示）")
    soe = _table(_load_section("note_template_soe.json", "八、68"), "财务费用")
    assert [r.get("label") for r in listed["rows"]] == [r.get("label") for r in soe["rows"]]


def test_finance_cost_guidance_states_derivations() -> None:
    """guidance 必须写明源模板 4 条派生关系（前端派生列的口径来源）。"""
    for file_name, section_number, table_name in (
        TARGETS["l8-listed"],
        TARGETS["l8-soe"],
    ):
        tbl = _table(_load_section(file_name, section_number), table_name)
        g = str(tbl.get("guidance") or "")
        for frag in ("利息费用 = 利息费用总额", "利息净支出 = 利息费用", "汇兑净损失 = 汇兑损失", "合计 = 利息净支出"):
            assert frag in g, f"{table_name} guidance 缺派生关系「{frag}」"


def test_l7_soe_placeholder_row_removed() -> None:
    """八、57 的 `……` 占位行（md 重建把省略号当数据行）必须已删。"""
    tbl = _table(_load_section("note_template_soe.json", "八、57"), "其他非流动负债")
    labels = [str(r.get("label")) for r in tbl.get("rows") or []]
    assert "……" not in labels
    assert labels[-1] == "合计"


def test_l7_variant_column_labels_differ() -> None:
    """两版列名按源模板分取（上市 期末数/上年年末数；国企 期末余额/期初余额）。"""
    listed = _table(_load_section("note_template_listed.json", "五、52"), "其他非流动负债")
    soe = _table(_load_section("note_template_soe.json", "八、57"), "其他非流动负债")
    assert [c["label"] for c in listed["columns"]] == ["项目", "期末数", "上年年末数"]
    assert [c["label"] for c in soe["columns"]] == ["项目", "期末余额", "期初余额"]


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_no_header_label_rows(key: str) -> None:
    """压扁的第二行表头残留（row_type=header_label）= 假数据行，必须为 0。"""
    file_name, section_number, table_name = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    bad = [r for r in tbl.get("rows") or [] if str(r.get("row_type")) == "header_label"]
    assert not bad, f"{table_name} 残留 header_label 假数据行"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_aligned_by_stamped(key: str) -> None:
    """章节须带 `_aligned_by` 戳，便于识别是否被 md 重建回退。"""
    file_name, section_number, _ = TARGETS[key]
    section = _load_section(file_name, section_number)
    assert section.get("_aligned_by") == "fix_note_l_cycle_structure"


def test_fix_script_check_mode_is_wired() -> None:
    """反向自检：脚本可加载且导出 `main` / `SECTIONS`（防守卫对着空脚本空转）。"""
    assert FIX_SCRIPT.exists(), "幂等脚本不存在"
    spec = importlib.util.spec_from_file_location("_fix_note_l_cycle_structure", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_fix_note_l_cycle_structure"] = mod
    spec.loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))
    assert set(mod.SECTIONS) == set(TARGETS)
    # 行清单单一真源：脚本常量与本守卫期望一致（防两处漂移）
    assert list(mod.FINANCE_COST_ROWS) == FINANCE_COST_LABELS[:-1]
