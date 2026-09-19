"""附注短期借款（L1）章节 columns 结构守卫（§五、33 上市 / §八、33 国企）。

锁定 `fix_note_l1_short_term_loans_structure.py` 的对齐结果，防 md 重建 / 并发会话回退：

- 两版章节各含 2 张表，表名正确（旧名「借款单位」不得复活）；
- 每张表 `columns` 齐备、列数正确（**注意国企表2 只有 3 列，不是 5 列**）；
- 所有列显式 `flat`（单级表头）；
- guidance 齐备且非空；
- 幂等性：脚本 `--check` 应返回 exit 0；
- 反向自检：源码含 `_aligned_by` 标记。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "data"
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "fix"
SCRIPT = SCRIPTS / "fix_note_l1_short_term_loans_structure.py"


@pytest.fixture(scope="module")
def listed():
    return json.loads((DATA / "note_template_listed.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def soe():
    return json.loads((DATA / "note_template_soe.json").read_text("utf-8"))


def _find_section(data: dict, section_number: str) -> dict:
    """递归查找 section_number 对应的章节 dict。"""
    for sec in data.get("sections") or data.get("children") or data.get("subsections") or []:
        if str(sec.get("section_number")) == section_number:
            return sec
        # 递归子键
        for child_key in ("sections", "children", "subsections"):
            if child_key in sec:
                try:
                    found = _find_section(sec, section_number)
                    if found:
                        return found
                except (StopIteration, TypeError):
                    pass
    return {}


# ─── 参数化定义 ───
# (section_number, table_name, expected_col_count, variant_fixture)
CASES = [
    ("五、33", "短期借款分类", 3, "listed"),
    ("五、33", "（2）逾期借款情况", 5, "listed"),
    ("八、33", "短期借款分类", 3, "soe"),
    ("八、33", "已逾期未偿还的短期借款情况", 3, "soe"),
]


@pytest.fixture(scope="module")
def listed_section(listed):
    return _find_section(listed, "五、33")


@pytest.fixture(scope="module")
def soe_section(soe):
    return _find_section(soe, "八、33")


def _get_table(section: dict, table_name: str) -> dict:
    tables = section.get("tables") or []
    for t in tables:
        if str(t.get("name")) == table_name:
            return t
    raise AssertionError(f"表 '{table_name}' 不存在于章节中，实际表名: {[t.get('name') for t in tables]}")


@pytest.mark.parametrize(
    "section_number,table_name,expected_col_count,variant",
    CASES,
    ids=[f"{c[3]}-{c[1]}" for c in CASES],
)
def test_columns_count_and_flat(
    section_number, table_name, expected_col_count, variant,
    listed_section, soe_section,
):
    """每张表列数正确且为单级 flat 表头。"""
    sec = listed_section if variant == "listed" else soe_section
    tbl = _get_table(sec, table_name)
    cols = tbl.get("columns") or []
    assert len(cols) == expected_col_count, (
        f"{variant}/{table_name} 列数应为 {expected_col_count}，实为 {len(cols)}"
    )
    # flat：首列 is_label + flat，无 group
    assert cols[0].get("is_label"), f"{variant}/{table_name} 首列缺 is_label"
    assert cols[0].get("flat"), f"{variant}/{table_name} 首列缺 flat"
    assert all(not c.get("group") for c in cols), f"{variant}/{table_name} 混入 group（应为单级）"


@pytest.mark.parametrize(
    "section_number,table_name,expected_col_count,variant",
    CASES,
    ids=[f"{c[3]}-{c[1]}-guidance" for c in CASES],
)
def test_guidance_present(
    section_number, table_name, expected_col_count, variant,
    listed_section, soe_section,
):
    """所有 4 张表都有 guidance 且非空。"""
    sec = listed_section if variant == "listed" else soe_section
    tbl = _get_table(sec, table_name)
    guidance = str(tbl.get("guidance") or "").strip()
    assert guidance, f"{variant}/{table_name} 缺 guidance"


def test_listed_old_name_not_resurrected(listed_section):
    """旧名「借款单位」不得复活为表名（应为「（2）逾期借款情况」）。"""
    table_names = [str(t.get("name")) for t in listed_section.get("tables") or []]
    assert "借款单位" not in table_names, f"旧名「借款单位」复活！当前表名: {table_names}"


def test_idempotent_check():
    """幂等性：运行脚本 --check 应返回 exit 0。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS.parent.parent),
    )
    assert result.returncode == 0, (
        f"脚本 --check 返回 {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_reverse_self_check_aligned_by():
    """反向自检：源码含 `_aligned_by` 标记。"""
    source = SCRIPT.read_text("utf-8")
    assert "_aligned_by" in source, "脚本源码缺少 `_aligned_by` 标记"
