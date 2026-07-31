# -*- coding: utf-8 -*-
"""M 循环权益类「变动表」附注章节结构守卫。

锁死 `fix_note_m_equity_structure.py` 的修订结果，防后续 md 重建 / 并发会话回退：

覆盖结构同构的标准变动表（项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额）：

| 章节   | 科目       | 备注                       |
|--------|------------|----------------------------|
| 五、55 | 资本公积   | 上市                       |
| 八、60 | 资本公积   | 国企                       |
| 五、59 | 盈余公积   | 上市                       |
| 八、62 | 盈余公积   | 国企                       |
| 五、58 | 专项储备   | 上市                       |
| 八、61 | 专项储备   | 国企（含「备注」列，共 6 列）|

断言：
- 六张表 columns 齐备且**显式 flat**（单级表头，抑制后端前缀推断凭空造「本期」父表头）
- 标签列头与 headers[0] 一致（同步后表头不错位）
- 国企八、61 专项储备含「备注」列（源模板），其余五张为标准 5 列
- guidance 齐备且写明勾稽关系
- 无 header_label 假数据行
- 章节带 `_aligned_by` 戳
- **反向自检**：脚本可 import 且导出 `main` / `SECTIONS`（防守卫空转）

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 5（M 循环批 4）
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIX_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix" / "fix_note_m_equity_structure.py"

STANDARD_COLS = ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]

# key → (file, section_number, table_name, with_remark)
TARGETS = {
    "m4-listed": ("note_template_listed.json", "五、55", "资本公积", False),
    "m4-soe": ("note_template_soe.json", "八、60", "资本公积", False),
    "m5-listed": ("note_template_listed.json", "五、59", "盈余公积", False),
    "m5-soe": ("note_template_soe.json", "八、62", "盈余公积", False),
    "m7-listed": ("note_template_listed.json", "五、58", "专项储备", False),
    "m7-soe": ("note_template_soe.json", "八、61", "专项储备", True),
}


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
    file_name, section_number, table_name, _ = TARGETS[key]
    section = _load_section(file_name, section_number)
    tbl = _table(section, table_name)
    assert tbl.get("name") == table_name


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_columns_present_and_flat(key: str) -> None:
    """单行表头 → columns 齐备 + 显式 flat + 无 group + 无残留 _column_groups。"""
    file_name, section_number, table_name, with_remark = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    cols = tbl.get("columns") or []
    expected_len = 6 if with_remark else 5
    assert len(cols) == expected_len, f"{table_name} columns={len(cols)}，应为 {expected_len}"
    assert cols[0].get("is_label") is True, "首列未标 is_label"
    assert any(c.get("flat") for c in cols), "未表态 flat（后端会凭空推断父表头）"
    assert not any(c.get("group") for c in cols), "单级表头不应有 group"
    assert tbl.get("_column_groups") is None, "单级表头残留 _column_groups"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_label_header_aligned(key: str) -> None:
    """标签列头必须与 headers[0] 一致（否则同步后表头错位）。"""
    file_name, section_number, table_name, _ = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    headers = tbl.get("headers") or []
    cols = tbl.get("columns") or []
    assert headers, f"{table_name} 缺 headers"
    assert headers[0] == cols[0].get("label"), f"{table_name} 标签列头 {cols[0].get('label')} ≠ headers[0] {headers[0]}"
    assert not any("<" in str(h) for h in headers), "headers 含 HTML"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_standard_five_columns(key: str) -> None:
    """前 5 列为标准变动表列；国企八、61 额外含第 6 列「备注」。"""
    file_name, section_number, table_name, with_remark = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    labels = [c.get("label") for c in tbl.get("columns") or []]
    assert labels[:5] == STANDARD_COLS, f"{table_name} 前 5 列 {labels[:5]} ≠ {STANDARD_COLS}"
    if with_remark:
        assert labels[5] == "备注", f"{table_name} 第 6 列应为「备注」，实为 {labels[5:]}"
    else:
        assert "备注" not in labels, f"{table_name} 不应有「备注」列"


def test_only_soe_special_reserve_has_remark() -> None:
    """仅国企八、61 专项储备有「备注」列（源模板实证），其余五张标准 5 列。"""
    remarked = []
    for key, (file_name, section_number, table_name, _) in TARGETS.items():
        tbl = _table(_load_section(file_name, section_number), table_name)
        labels = [c.get("label") for c in tbl.get("columns") or []]
        if "备注" in labels:
            remarked.append(key)
    assert remarked == ["m7-soe"], f"含备注列的表应仅 m7-soe，实为 {remarked}"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_guidance_present_with_reconciliation(key: str) -> None:
    """guidance 齐备且写明勾稽关系（期末 = 期初 + 本期增加 − 本期减少）。"""
    file_name, section_number, table_name, _ = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    g = str(tbl.get("guidance") or "")
    assert g.strip(), f"{table_name} 缺 guidance"
    assert "期末余额 = 期初余额 + 本期增加 − 本期减少" in g, f"{table_name} guidance 缺勾稽关系"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_no_header_label_rows(key: str) -> None:
    """压扁的第二行表头残留（row_type=header_label）= 假数据行，必须为 0。"""
    file_name, section_number, table_name, _ = TARGETS[key]
    tbl = _table(_load_section(file_name, section_number), table_name)
    bad = [r for r in tbl.get("rows") or [] if str(r.get("row_type")) == "header_label"]
    assert not bad, f"{table_name} 残留 header_label 假数据行"


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_aligned_by_stamped(key: str) -> None:
    """章节须带 `_aligned_by` 戳，便于识别是否被 md 重建回退。"""
    file_name, section_number, _, _ = TARGETS[key]
    section = _load_section(file_name, section_number)
    assert section.get("_aligned_by") == "fix_note_m_equity_structure"


def test_fix_script_check_mode_is_wired() -> None:
    """反向自检：脚本可加载且导出 `main` / `SECTIONS`（防守卫对着空脚本空转）。"""
    assert FIX_SCRIPT.exists(), "幂等脚本不存在"
    spec = importlib.util.spec_from_file_location("_fix_note_m_equity_structure", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_fix_note_m_equity_structure"] = mod
    spec.loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))
    assert set(mod.SECTIONS) == set(TARGETS)
