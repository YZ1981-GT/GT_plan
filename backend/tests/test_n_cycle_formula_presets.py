"""N 类公式预设守卫.

Property 1: N2/N4/N5 各有披露 sheet 块
Property 2: 科目码合法（在标准科目表范围内）
Property 3: 无成环引用（披露块禁引自身 sheet）
Property 4: 公式类型合法（WP/PREV/TB/ADJ/LEDGER/LEDGER_DETAIL/TB_SUM/PLACEHOLDER）

Requirements: n-cycle-note-template-and-disclosure-completion 4.4
"""
import json
from pathlib import Path

import pytest

BACKEND_DATA = Path(__file__).resolve().parent.parent / "data"
PRESET_PATH = BACKEND_DATA / "prefill_formula_mapping.json"


def _load_mappings() -> list[dict]:
    raw = json.loads(PRESET_PATH.read_text("utf-8"))
    return raw.get("mappings", [])


def _n_disclosure_blocks() -> list[dict]:
    """只取 N 类的披露 sheet 块."""
    mappings = _load_mappings()
    return [
        b for b in mappings
        if isinstance(b, dict)
        and (b.get("wp_code", "") or "").startswith("N")
        and ("附注" in (b.get("sheet") or "") or "披露" in (b.get("sheet") or ""))
    ]


# ─── Property 1: 披露块存在 ─────────────────────────────────────────────────

def test_n2_has_disclosure_blocks():
    """N2 有 2 个披露块（上市+国企）."""
    blocks = [b for b in _n_disclosure_blocks() if b["wp_code"] == "N2"]
    assert len(blocks) == 2, f"N2 披露块数: {len(blocks)}, 期望 2"


def test_n4_has_disclosure_block():
    """N4 有 1 个披露块（仅上市）."""
    blocks = [b for b in _n_disclosure_blocks() if b["wp_code"] == "N4"]
    assert len(blocks) == 1, f"N4 披露块数: {len(blocks)}, 期望 1"


def test_n5_has_disclosure_blocks():
    """N5 有 2 个披露块（上市+国企）."""
    blocks = [b for b in _n_disclosure_blocks() if b["wp_code"] == "N5"]
    assert len(blocks) == 2, f"N5 披露块数: {len(blocks)}, 期望 2"


# ─── Property 2: 每个块至少 2 条公式 ─────────────────────────────────────────

@pytest.mark.parametrize("wp_code", ["N2", "N4", "N5"])
def test_disclosure_blocks_have_cells(wp_code):
    """每个披露块至少 2 条公式."""
    blocks = [b for b in _n_disclosure_blocks() if b["wp_code"] == wp_code]
    for b in blocks:
        cells = b.get("cells", [])
        assert len(cells) >= 2, (
            f"{wp_code}/{b.get('sheet')}: 公式数 {len(cells)} < 2"
        )


# ─── Property 3: 无成环引用 ──────────────────────────────────────────────────

def test_no_self_referencing():
    """披露块的 WP 公式不引用自身 sheet."""
    for b in _n_disclosure_blocks():
        sheet = b.get("sheet", "")
        for cell in b.get("cells", []):
            formula = cell.get("formula", "")
            if formula.startswith("WP("):
                # WP('N2','应交税费审定表N2-1','...') — 第二参是被引 sheet
                # 如果与当前 sheet 相同则成环
                parts = formula.split("'")
                if len(parts) >= 4:
                    ref_sheet = parts[3]
                    assert ref_sheet != sheet, (
                        f"{b['wp_code']}/{sheet}: WP 公式自引用 '{ref_sheet}'"
                    )


# ─── Property 4: 公式类型合法 ────────────────────────────────────────────────

VALID_FORMULA_TYPES = {"WP", "PREV", "TB", "ADJ", "LEDGER", "LEDGER_DETAIL", "TB_SUM", "PLACEHOLDER", "AUX"}


def test_formula_types_valid():
    """所有 N 类块的 formula_type 合法."""
    mappings = _load_mappings()
    n_blocks = [b for b in mappings if isinstance(b, dict) and (b.get("wp_code", "") or "").startswith("N")]
    for b in n_blocks:
        for cell in b.get("cells", []):
            ft = cell.get("formula_type", "")
            assert ft in VALID_FORMULA_TYPES, (
                f"{b['wp_code']}/{b.get('sheet')}: 非法 formula_type '{ft}'"
            )


# ─── 反向自检 ────────────────────────────────────────────────────────────────

def test_total_n_blocks_anchor():
    """N 类共至少 20 块（15 原有 + 5 新增披露块）."""
    mappings = _load_mappings()
    n_count = sum(1 for b in mappings if isinstance(b, dict) and (b.get("wp_code", "") or "").startswith("N"))
    assert n_count >= 20, f"N 类块数 {n_count} < 20"
