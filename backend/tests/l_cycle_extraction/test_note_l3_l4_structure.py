"""附注长期借款(L3) / 应付债券(L4) / 一年内到期非流动负债 章节结构守卫。

锁定 `fix_note_l3_l4_structure.py` 的对齐结果，防 md 重建 / 并发会话回退：

覆盖 6 个章节 16 张表：
- L3 listed 五、45 长期借款（1 表，5 列，**有 group** 两级表头）
- L3 soe 八、49 长期借款（1 表，5 列，有 group）
- L4 listed 五、46 应付债券（5 表，列数 3/6/8/10/5）
- L4 soe 八、50 应付债券（2 表，列数 3/10）
- 五、43 一年内到期的非流动负债 listed（5 表，列数 3/3/5/7/3）
- 八、44 一年内到期的非流动负债 soe（1 表，3 列）

守卫内容：
- 表数正确；
- 每张表列数正确 + flat/group 表态正确；
- L3 两表有 group（两级表头），其余为 flat（单级表头）；
- 所有表 guidance 齐备且非空；
- 旧名「参考披露格式：」（L4 表4）不得复活；
- 旧名「项  目」（五、43 表5）不得复活；
- 幂等性：脚本 `--check` 应返回 exit 0；
- 反向自检：源码含 `_aligned_by` 或 `SCRIPT_NAME`。

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
SCRIPT = SCRIPTS / "fix_note_l3_l4_structure.py"


@pytest.fixture(scope="module")
def listed():
    return json.loads((DATA / "note_template_listed.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def soe():
    return json.loads((DATA / "note_template_soe.json").read_text("utf-8"))


def _find_section(data: dict, section_number: str) -> dict:
    """递归查找 section_number 对应的章节 dict（检查 sections/children/subsections）。"""
    for key in ("sections", "children", "subsections"):
        items = data.get(key)
        if not items:
            continue
        for sec in items:
            if str(sec.get("section_number")) == section_number:
                return sec
            # 递归
            found = _find_section(sec, section_number)
            if found:
                return found
    return {}


def _get_table(section: dict, table_name: str) -> dict:
    tables = section.get("tables") or []
    for t in tables:
        if str(t.get("name")) == table_name:
            return t
    raise AssertionError(
        f"表 '{table_name}' 不存在，实际表名: {[t.get('name') for t in tables]}"
    )


# ═══════════════════════════════════════════════════════════════════
# 参数化定义
# (section_number, table_name, expected_col_count, has_group, variant)
# ═══════════════════════════════════════════════════════════════════

CASES = [
    # L3 - 两级表头
    ("五、45", "长期借款", 5, True, "listed"),
    ("八、49", "长期借款", 5, True, "soe"),
    # L4 listed 五、46 - 5 张表
    ("五、46", "应付债券", 3, False, "listed"),
    ("五、46", "应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）", 6, False, "listed"),
    ("五、46", "应付债券（续）", 8, False, "listed"),
    ("五、46", "（3）划分为金融负债的其他金融工具", 10, False, "listed"),
    ("五、46", "期末发行在外的优先股、永续债等其他金融工具变动情况", 9, True, "listed"),
    # L4 soe 八、50 - 2 张表
    ("八、50", "应付债券", 3, False, "soe"),
    ("八、50", "应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）", 10, False, "soe"),
    # 五、43 一年内到期非流动负债 listed - 5 张表
    ("五、43", "一年内到期的非流动负债", 3, False, "listed"),
    ("五、43", "一年内到期的长期借款", 3, False, "listed"),
    ("五、43", "一年内到期的应付债券", 5, False, "listed"),
    ("五、43", "一年内到期的应付债券（续）", 7, False, "listed"),
    ("五、43", "一年内到期的长期应付款", 3, False, "listed"),
    # 八、44 一年内到期非流动负债 soe - 1 张表
    ("八、44", "一年内到期的非流动负债", 3, False, "soe"),
]


@pytest.fixture(scope="module")
def all_sections(listed, soe):
    """预加载所有需要的章节。"""
    results = {}
    for section_number in ("五、45", "五、46", "五、43"):
        results[("listed", section_number)] = _find_section(listed, section_number)
    for section_number in ("八、49", "八、50", "八、44"):
        results[("soe", section_number)] = _find_section(soe, section_number)
    return results


@pytest.mark.parametrize(
    "section_number,table_name,expected_col_count,has_group,variant",
    CASES,
    ids=[f"{c[4]}-{c[0]}-{c[1][:12]}" for c in CASES],
)
def test_columns_count_and_structure(
    section_number, table_name, expected_col_count, has_group, variant,
    all_sections,
):
    """每张表列数正确，且 flat/group 表态正确。"""
    sec = all_sections[(variant, section_number)]
    assert sec, f"章节 {section_number} ({variant}) 未找到"
    tbl = _get_table(sec, table_name)
    cols = tbl.get("columns") or []
    assert len(cols) == expected_col_count, (
        f"{variant}/{section_number}/{table_name} "
        f"列数应为 {expected_col_count}，实为 {len(cols)}"
    )

    if has_group:
        # L3 两级表头：至少一列有 group
        groups = [c.get("group") for c in cols if c.get("group")]
        assert len(groups) >= 2, (
            f"{variant}/{section_number}/{table_name} 应有 group 两级表头"
        )
    else:
        # flat 单级：首列 is_label + flat，无 group
        assert cols[0].get("is_label"), (
            f"{variant}/{section_number}/{table_name} 首列缺 is_label"
        )
        assert cols[0].get("flat"), (
            f"{variant}/{section_number}/{table_name} 首列缺 flat"
        )
        assert all(not c.get("group") for c in cols), (
            f"{variant}/{section_number}/{table_name} 混入 group（应为单级 flat）"
        )


@pytest.mark.parametrize(
    "section_number,table_name,expected_col_count,has_group,variant",
    CASES,
    ids=[f"{c[4]}-{c[0]}-{c[1][:12]}-guidance" for c in CASES],
)
def test_guidance_present(
    section_number, table_name, expected_col_count, has_group, variant,
    all_sections,
):
    """所有表都有 guidance 且非空。"""
    sec = all_sections[(variant, section_number)]
    assert sec, f"章节 {section_number} ({variant}) 未找到"
    tbl = _get_table(sec, table_name)
    guidance = str(tbl.get("guidance") or "").strip()
    assert guidance, f"{variant}/{section_number}/{table_name} 缺 guidance"


def test_l4_listed_old_name_not_resurrected(listed):
    """旧名「参考披露格式：」不得复活为 L4 listed 表名。"""
    sec = _find_section(listed, "五、46")
    table_names = [str(t.get("name")) for t in sec.get("tables") or []]
    assert "参考披露格式：" not in table_names, (
        f"旧名「参考披露格式：」复活！当前表名: {table_names}"
    )


def test_nc_listed_old_name_not_resurrected(listed):
    """旧名「项  目」不得复活为五、43 表名（应为「一年内到期的长期应付款」）。"""
    sec = _find_section(listed, "五、43")
    table_names = [str(t.get("name")) for t in sec.get("tables") or []]
    assert "项  目" not in table_names, (
        f"旧名「项  目」复活！当前表名: {table_names}"
    )


def test_idempotent_check():
    """幂等性：运行脚本 --check 应返回 exit 0。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS.parent.parent),
    )
    assert result.returncode == 0, (
        f"脚本 --check 返回 {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_reverse_self_check():
    """反向自检：源码含 SCRIPT_NAME 标记（脚本自身标识）。"""
    source = SCRIPT.read_text("utf-8")
    assert "SCRIPT_NAME" in source, "脚本源码缺少 SCRIPT_NAME 标记"
