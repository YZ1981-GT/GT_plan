"""G7 公式管理预设守卫（Wave 3）。

断言：
1. G7 预设中无具体客户/供应商编码（正则 AUX([^)]*'\\d{6}' 不得命中）
2. G7-2 明细表块不含 WP(
3. 每个 G7 block 的 cells 中 cell_ref 在同一 page_key 内唯一
4. sheet 字段与源 xlsx sheetnames 逐字一致
5. G7-1 块包含 TB('1512','期初余额') 和 TB('1512','期末余额')
6. G7-1 块包含至少一条 WP( 公式（审定表可用 WP）

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ Task 3.3
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
DATA = BACKEND / "data" / "prefill_formula_mapping.json"
SOURCE_XLSX = BACKEND / "wp_templates" / "G" / "G7 长期股权投资.xlsx"


def _all_blocks() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw


@pytest.fixture(scope="module")
def g7_blocks() -> list[dict]:
    blocks = [b for b in _all_blocks() if b.get("wp_code") == "G7"]
    assert blocks, "prefill_formula_mapping 中无 wp_code=='G7' 的块"
    return blocks


@pytest.fixture(scope="module")
def g7_1_block(g7_blocks: list[dict]) -> dict:
    hit = [b for b in g7_blocks if b.get("sheet") == "长期股权投资审定表G7-1"]
    assert hit, "G7 缺 sheet='长期股权投资审定表G7-1' 块"
    assert len(hit) == 1
    return hit[0]


@pytest.fixture(scope="module")
def g7_2_block(g7_blocks: list[dict]) -> dict:
    hit = [b for b in g7_blocks if b.get("sheet") == "明细表G7-2"]
    assert hit, "G7 缺 sheet='明细表G7-2' 块"
    assert len(hit) == 1
    return hit[0]


def _formulas(block: dict) -> list[str]:
    return [str(c.get("formula") or "") for c in block.get("cells") or []]


# ── 1. 无具体客户/供应商编码 ─────────────────────────────────────────────────


_CLIENT_CODE_RE = re.compile(r"AUX\([^)]*'\d{6}'")


def test_no_hardcoded_client_codes(g7_blocks: list[dict]) -> None:
    """G7 预设中不得残留具体客户/供应商编码（某项目实测污染）。"""
    for block in g7_blocks:
        block_json = json.dumps(block, ensure_ascii=False)
        match = _CLIENT_CODE_RE.search(block_json)
        assert match is None, (
            f"sheet='{block.get('sheet')}' 残留硬编码客户编码: {match.group()}"
        )


# ── 2. G7-2 明细表块不含 WP( ────────────────────────────────────────────────


def test_g7_2_has_no_wp_formula(g7_2_block: dict) -> None:
    """明细表禁 WP 防循环引用。"""
    block_json = json.dumps(g7_2_block, ensure_ascii=False)
    assert "WP(" not in block_json, (
        f"明细表G7-2 含 WP() 公式，会导致 G7-1 ← G7-2 ← G7-1 循环"
    )


# ── 3. cell_ref 唯一性 ───────────────────────────────────────────────────────


def test_cell_ref_unique_within_each_block(g7_blocks: list[dict]) -> None:
    """每个 G7 block 内 cell_ref 必须唯一（跨 block 同名属平台级已知问题 page_key 不含 sheet）。"""
    for block in g7_blocks:
        refs: list[str] = []
        for cell in block.get("cells") or []:
            refs.append(cell.get("cell_ref", ""))
        seen: set[str] = set()
        dupes: list[str] = []
        for ref in refs:
            if ref in seen:
                dupes.append(ref)
            seen.add(ref)
        assert not dupes, (
            f"sheet='{block.get('sheet')}' cell_ref 重复: {dupes}"
        )


# ── 4. sheet 字段与源 xlsx sheetnames 逐字一致 ──────────────────────────────


def test_sheet_names_match_source_xlsx(g7_blocks: list[dict]) -> None:
    """sheet 字段必须与源 xlsx tab 名逐字一致（唯一裁决者）。"""
    if not SOURCE_XLSX.exists():
        pytest.skip("backend/wp_templates/G/G7 长期股权投资.xlsx 不存在")
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(SOURCE_XLSX, read_only=True)
    try:
        tabs = list(wb.sheetnames)
    finally:
        wb.close()

    for block in g7_blocks:
        sheet = block.get("sheet")
        assert sheet in tabs, (
            f"预设 sheet='{sheet}' 不在源 xlsx tab 名中。"
            f"\n可用 tabs: {tabs}"
        )


# ── 5. G7-1 包含 TB('1512','期初余额') 和 TB('1512','期末余额') ────────────


def test_g7_1_has_impairment_tb_formulas(g7_1_block: dict) -> None:
    """审定表有减值段，必须取 1512 期初/期末。"""
    formulas = _formulas(g7_1_block)
    joined = "\n".join(formulas)
    assert "TB('1512','期初余额')" in joined, "G7-1 缺 TB('1512','期初余额')"
    assert "TB('1512','期末余额')" in joined, "G7-1 缺 TB('1512','期末余额')"


# ── 6. G7-1 块包含至少一条 WP( 公式（审定表可用 WP） ────────────────────────


def test_g7_1_has_wp_formula(g7_1_block: dict) -> None:
    """审定表可引用其他底稿数据（明细表合计勾稽等）。"""
    formulas = _formulas(g7_1_block)
    assert any("WP(" in f for f in formulas), (
        "G7-1 审定表块应至少有一条 WP() 公式用于勾稽"
    )
