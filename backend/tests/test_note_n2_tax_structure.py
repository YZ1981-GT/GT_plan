"""附注 N2 应交税费章节行集守卫（§五、41 / §八、41）。

验证：
- 两版 rows 各 13 + 合计 = 14 行
- label 逐字比对 N2_FIXED_TAX_LABELS
- --check exit 0

spec: n2-disclosure-and-extraction-alignment Task 2.3
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ─── 加载幂等脚本 ─────────────────────────────────────────────────────────────

_FIX_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "fix" / "fix_note_n2_tax_structure.py"
)


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_n2_tax", _FIX_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()

# ─── 权威 13 行 label（逐字取自源模板 R8~R20）────────────────────────────────

N2_FIXED_TAX_LABELS = [
    "企业所得税",
    "增值税",
    "消费税",
    "资源税",
    "土地增值税",
    "城市维护建设税",
    "车船牌照税",
    "房产税",
    "土地使用税",
    "教育费附加",
    "矿产资源补偿费",
    "代扣代缴外国企业所得税",
    "代扣代缴个人所得税",
]


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _load_section(variant: str) -> dict:
    if variant == "listed":
        path = FIX.LISTED_PATH
        section_number = FIX.SECTION_LISTED
    else:
        path = FIX.SOE_PATH
        section_number = FIX.SECTION_SOE
    data = json.loads(path.read_text(encoding="utf-8"))
    hits = [s for s in data["sections"] if s.get("section_number") == section_number]
    assert len(hits) == 1, f"{variant}: 未找到 {section_number}"
    return hits[0]


# ─── 测试 ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_row_count_is_14(variant: str):
    """两版 rows 各 13 种 + 合计 = 14 行。"""
    section = _load_section(variant)
    tables = section.get("tables") or []
    assert tables, f"{variant}: tables 为空"
    rows = tables[0].get("rows") or []
    assert len(rows) == 14, f"{variant}: 期望 14 行，实际 {len(rows)} 行"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_labels_match_n2_fixed(variant: str):
    """label 逐字比对 N2_FIXED_TAX_LABELS。"""
    section = _load_section(variant)
    rows = section["tables"][0]["rows"]
    data_rows = [r for r in rows if r.get("row_type") == "data"]
    assert len(data_rows) == 13, f"{variant}: data 行数 {len(data_rows)} ≠ 13"
    labels = [r["label"] for r in data_rows]
    assert labels == N2_FIXED_TAX_LABELS, f"{variant}: label 不匹配\n  实际: {labels}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_total_row(variant: str):
    """末行是合计行。"""
    section = _load_section(variant)
    rows = section["tables"][0]["rows"]
    last = rows[-1]
    assert last.get("label") == "合计", f"{variant}: 末行 label = {last.get('label')}"
    assert last.get("is_total") is True, f"{variant}: 末行缺 is_total"
    assert last.get("row_type") == "total", f"{variant}: 末行 row_type = {last.get('row_type')}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_aligned_by(variant: str):
    """_aligned_by 标记正确。"""
    section = _load_section(variant)
    assert section.get("_aligned_by") == FIX.ALIGNED_BY


def test_check_exit_zero():
    """--check exit 0（CI 可用）。"""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.fix.fix_note_n2_tax_structure", "--check"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--check 失败:\n{result.stdout}\n{result.stderr}"
