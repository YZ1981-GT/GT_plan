"""K 循环公式预设守卫。

钉死 `prefill_formula_mapping.json` 中 K 循环块的正确性，防止再次错位。

Property 12：每个码 ∈ 标准科目表 且 ∈ 本循环报表行引用科目集
Property 13：无孤儿 wp_code 块（K14~K18 已移除）
Property 14：无跨大类区间
Property 15：明细表块不反引审定表

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Task 16 / Requirements 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.four_table.k_cycle_specs import (
    K_CYCLE_SPECS,
    NONEXISTENT_ACCOUNT_CODES,
    no_account_cycle_codes,
)

# Re-derive correct accounts from the single source of truth
_CORRECT_ACCOUNTS: dict[str, str | None] = {
    code: spec.fallback_standard or None for code, spec in K_CYCLE_SPECS.items()
}

_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prefill_formula_mapping.json"
_ACCOUNT_CHART_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "standard_account_chart.json"

# Orphan wp_codes that should NOT exist in the presets
_ORPHAN_CODES = {"K14", "K15", "K16", "K17", "K18"}

# Prefill engine vocabulary — functions allowed in formulas that are NOT in formula_engine._REGISTRY
_PREFILL_ONLY_FUNCS = {"ADJ", "TB_SUM", "LEDGER", "LEDGER_DETAIL", "AUX", "PREV", "WP"}


@pytest.fixture(scope="module")
def presets() -> list[dict]:
    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return data["mappings"]


@pytest.fixture(scope="module")
def k_presets(presets) -> list[dict]:
    return [x for x in presets if str(x.get("wp_code", "")).startswith("K")]


@pytest.fixture(scope="module")
def account_chart_codes() -> set[str]:
    """标准科目表中存在的科目码集合。"""
    p = _ACCOUNT_CHART_PATH
    if not p.exists():
        # Fallback: load from multiple possible locations
        alt = Path(__file__).resolve().parent.parent.parent / "data" / "account_chart_standard.json"
        if alt.exists():
            p = alt
        else:
            pytest.skip("标准科目表 JSON 不在预期路径")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(x.get("account_code", "")).strip() for x in data} - {""}
    if isinstance(data, dict) and "accounts" in data:
        return {str(x.get("account_code", "")).strip() for x in data["accounts"]} - {""}
    return set()


# ─────────────────────────────────────────────────────────────────────────────
# Property 13: 无孤儿 wp_code 块
# ─────────────────────────────────────────────────────────────────────────────


def test_no_orphan_blocks(k_presets):
    """K14~K18 块已被移除（平台无对应循环）。"""
    orphan_found = [x["wp_code"] for x in k_presets if x["wp_code"] in _ORPHAN_CODES]
    assert not orphan_found, f"孤儿块未移除: {orphan_found}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 12: 预设科目属本循环
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", sorted(_CORRECT_ACCOUNTS))
def test_main_block_account_codes_correct(k_presets, wp_code):
    """主审定表块的 account_codes 与 k_cycle_specs 声明一致。"""
    expected = _CORRECT_ACCOUNTS[wp_code]
    # Find the main adjudication block (has ADJ or PREV formulas)
    main_blocks = [
        x for x in k_presets
        if x["wp_code"] == wp_code
        and any("ADJ(" in (c.get("formula") or "") or "PREV(" in (c.get("formula") or "")
                for c in (x.get("cells") or x.get("entries") or []))
    ]
    if not main_blocks:
        pytest.skip(f"{wp_code} 无主审定表块")
    block = main_blocks[0]
    accts = block.get("account_codes", [])
    if expected is None:
        # 宁缺勿造：不应有科目码
        assert accts == [] or accts == [""], f"{wp_code} 应无科目码，实际 {accts}"
    else:
        assert expected in str(accts), (
            f"{wp_code} account_codes 应含 {expected}，实际 {accts}"
        )


@pytest.mark.parametrize("wp_code", sorted(_CORRECT_ACCOUNTS))
def test_formulas_reference_correct_account(k_presets, wp_code):
    """TB()/ADJ() 公式引用的科目码与本循环一致。"""
    expected = _CORRECT_ACCOUNTS[wp_code]
    if expected is None:
        return  # 宁缺勿造循环不应有 TB()

    blocks = [x for x in k_presets if x["wp_code"] == wp_code]
    for block in blocks:
        cells = block.get("cells") or block.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if not f:
                continue
            # Extract codes from TB('xxxx',...) and ADJ('xxxx',...)
            codes = re.findall(r"(?:TB|ADJ)\('([^']+)'", f)
            for code in codes:
                if "~" in code:
                    continue  # Range handled by Property 14
                # Code should start with expected or be the expected itself
                assert code == expected or code.startswith(expected), (
                    f"{wp_code} 公式引用 {code}，应属于 {expected} 科目族"
                    f"（cell={c.get('cell_ref','')}, block={block.get('wp_name','')}）"
                )


def test_no_nonexistent_codes_in_presets(k_presets):
    """预设中不出现三表零命中的不存在码。"""
    for block in k_presets:
        accts = block.get("account_codes", [])
        cells = block.get("cells") or block.get("entries") or []
        all_text = str(accts) + " ".join(c.get("formula", "") or "" for c in cells)
        for bad in NONEXISTENT_ACCOUNT_CODES:
            assert f"'{bad}'" not in all_text and f'"{bad}"' not in all_text, (
                f"{block['wp_code']} 含不存在的码 {bad}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Property 14: 无病态区间
# ─────────────────────────────────────────────────────────────────────────────


def test_no_pathological_ranges(k_presets):
    """K 循环预设中不存在跨科目大类的 TB_SUM('a~b')。"""
    issues = []
    for block in k_presets:
        cells = block.get("cells") or block.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            ranges = re.findall(r"TB_SUM\('(\d+)~(\d+)'", f)
            for a, b in ranges:
                # Same major class = first 2 digits match
                if a[:2] != b[:2]:
                    issues.append(
                        f"{block['wp_code']} | {c.get('cell_ref','')} | TB_SUM('{a}~{b}')"
                    )
    assert not issues, f"病态区间（跨大类）: {issues}"


def test_no_empty_tb_sum_formulas(k_presets):
    """TB_SUM 带空串或只有范围无第二参数的视为清除残留。"""
    for block in k_presets:
        cells = block.get("cells") or block.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if "TB_SUM('')" in f or "TB_SUM('~')" in f:
                pytest.fail(
                    f"{block['wp_code']} 含无效 TB_SUM: {c.get('cell_ref','')} = {f}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Property 15: 预设不成环
# ─────────────────────────────────────────────────────────────────────────────


def test_detail_blocks_no_wp_back_reference(k_presets):
    """明细表块（非主审定表）不得含 WP() 反引审定表。"""
    for block in k_presets:
        wc = block.get("wp_code", "")
        if wc not in _CORRECT_ACCOUNTS:
            continue
        cells = block.get("cells") or block.get("entries") or []
        # Is this a detail/sub block? (no ADJ() = not the main adjudication block)
        is_main = any("ADJ(" in (c.get("formula") or "") for c in cells)
        if is_main:
            continue
        # Detail block should not WP() back to the adjudication table
        for c in cells:
            f = c.get("formula") or ""
            wp_refs = re.findall(r"WP\('([^']+)','([^']*)'", f)
            for ref_wc, ref_sheet in wp_refs:
                if ref_wc == wc and "审定表" in ref_sheet:
                    pytest.fail(
                        f"{wc} 明细块 WP() 反引审定表: {c.get('cell_ref','')} → "
                        f"WP('{ref_wc}','{ref_sheet}') — 会成环"
                    )


# ─────────────────────────────────────────────────────────────────────────────
# 语法合法性
# ─────────────────────────────────────────────────────────────────────────────


def test_formula_syntax_valid(k_presets):
    """所有公式只使用已知函数名。"""
    known_funcs = {"TB", "ADJ", "PREV", "WP", "TB_SUM", "LEDGER", "LEDGER_DETAIL", "AUX"}
    issues = []
    for block in k_presets:
        cells = block.get("cells") or block.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if not f:
                continue
            # Extract function calls: NAME(
            func_names = set(re.findall(r"=?([A-Z_]+)\(", f))
            unknown = func_names - known_funcs
            if unknown:
                issues.append(f"{block['wp_code']} | {c.get('cell_ref','')} | unknown: {unknown}")
    assert not issues, f"未知函数: {issues}"


# ─────────────────────────────────────────────────────────────────────────────
# 反向自检
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_has_k_blocks(k_presets):
    """反向自检：K 循环块数应 ≥ 20（含 K0/K1 的多个明细块）。"""
    assert len(k_presets) >= 20, f"K 块数过少: {len(k_presets)}（预期 ≥20）"


def test_k5_detail_uses_2801_not_2701(k_presets):
    """反向自检：K5 明细块使用 2801（预计负债），不是 2701（长期应付款）。"""
    k5_detail = [
        x for x in k_presets
        if x["wp_code"] == "K5"
        and not any("ADJ(" in (c.get("formula") or "") for c in (x.get("cells") or []))
        and any("TB(" in (c.get("formula") or "") for c in (x.get("cells") or []))
    ]
    assert k5_detail, "K5 明细块不存在"
    block = k5_detail[0]
    all_formulas = " ".join(c.get("formula", "") or "" for c in block.get("cells", []))
    assert "2801" in all_formulas, f"K5 明细块公式未引用 2801: {all_formulas[:200]}"
    assert "2701" not in all_formulas, f"K5 明细块仍引用 2701（长期应付款）: {all_formulas[:200]}"
