"""H 类公式预设守卫 — Property 7/9/10。

- 科目码正确性：预设中每个码 ∈ 本循环兜底集
- 旧错误码不得残留
- H10 损益口径守卫（不出现 期初余额/期末余额）
- 幂等脚本 `--check` 通过

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MAPPING_FILE = _DATA_DIR / "prefill_formula_mapping.json"

_OLD_ERROR_CODES = {"1503", "1504", "1901", "190101", "2205", "1522", "1523", "2802", "2803", "1611"}


@pytest.fixture(scope="module")
def h_blocks() -> list[dict]:
    """加载 H 类预设块。"""
    with open(_MAPPING_FILE, encoding="utf-8") as f:
        data = json.load(f)
    blocks = []
    for block in data.get("mappings", []):
        if not isinstance(block, dict):
            continue
        wp = block.get("wp_code", "") or ""
        if wp.upper().startswith("H") and len(wp) > 1 and wp[1:2].isdigit():
            blocks.append(block)
    return blocks


@pytest.fixture(scope="module")
def h_cycle_allowed_codes() -> dict[str, set[str]]:
    """各循环允许出现在预设中的科目码集合（= 兜底集 ∪ 合法交叉引用）。"""
    sys.path.insert(0, str(_DATA_DIR.parent))
    from app.services.four_table.h_cycle_specs import H_CYCLE_SPECS

    allowed: dict[str, set[str]] = {}
    for cycle, spec in H_CYCLE_SPECS.items():
        codes: set[str] = set()
        for slot in spec.slots:
            codes.update(slot.fallback_standard_codes or ())
        allowed[cycle] = codes

    # H10 明细表合法引用 1606（固定资产清理→损益的来源）
    allowed.setdefault("H10", set()).add("1606")
    # H0 是函证不是 H 类核心循环，跳过
    return allowed


# ──────────────────────────────────────────────────────────────────────────────
# Property 7: 科目码属于本循环
# ──────────────────────────────────────────────────────────────────────────────

def test_no_old_error_codes_in_presets(h_blocks: list[dict]):
    """旧错误码不得出现在任何 H 类预设块的 `account_codes` 中。"""
    violations = []
    for block in h_blocks:
        codes = set(block.get("account_codes", []))
        hit = codes & _OLD_ERROR_CODES
        if hit:
            violations.append(f"{block.get('wp_code')}/{block.get('sheet')}: {hit}")
    assert not violations, f"旧错误码残留：{violations}"


def test_no_old_error_codes_in_formula_expressions(h_blocks: list[dict]):
    """🔴 公式**表达式**里也不得含旧错误码。

    2026-08-03 浏览器实测发现：只改块级 `account_codes` 不够 ——
    `cells[].formula` 里的 `=TB('2802','期末余额')` 照旧生效，
    底稿「四表取数（公式管理）」面板显示的还是错科目、取数还是错的。
    （字段名是 `cells` 不是 `items`，首轮扫描因此报 `formulas=0` 而漏掉。）
    """
    violations = []
    for block in h_blocks:
        wp = block.get("wp_code")
        sheet = block.get("sheet")
        for cell in block.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            f = cell.get("formula") or ""
            for bad in _OLD_ERROR_CODES:
                if f"'{bad}'" in f:
                    violations.append(
                        f"{wp}/{sheet} [{cell.get('cell_ref')}]: 公式含旧码 {bad} → {f}"
                    )
    assert not violations, "公式表达式残留旧错误码：\n" + "\n".join(
        f"  {v}" for v in violations
    )


def test_h10_pl_formula_uses_occurrence(h_blocks: list[dict]):
    """H10 引用 `6115` 的公式必须用发生额口径，不得用期初/期末余额。

    反向边界：同块里引用 `1606 固定资产清理`（资产类过渡科目）的公式
    **允许**用余额口径 —— 它有真实期初/期末余额。
    """
    violations = []
    for block in h_blocks:
        if (block.get("wp_code") or "").upper() != "H10":
            continue
        for cell in block.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            f = cell.get("formula") or ""
            if "'6115'" not in f:
                continue
            for bad in ("期初余额", "期末余额"):
                if f"'{bad}'" in f:
                    violations.append(
                        f"H10/{block.get('sheet')} [{cell.get('cell_ref')}]: {f}"
                    )
    assert not violations, "H10 损益科目仍用余额口径：\n" + "\n".join(
        f"  {v}" for v in violations
    )


def test_h10_asset_account_keeps_balance_semantics(h_blocks: list[dict]):
    """反向自检：H10 里引用 `1606` 的公式**不应**被改成发生额口径。

    首版脚本无科目过滤，把 `TB('1606','期初余额')` 也改成了发生额（dry-run 抓到）。
    """
    for block in h_blocks:
        if (block.get("wp_code") or "").upper() != "H10":
            continue
        for cell in block.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            f = cell.get("formula") or ""
            if "'1606'" in f and "'本期发生额'" in f:
                pytest.fail(
                    f"H10/{block.get('sheet')} [{cell.get('cell_ref')}] "
                    f"把资产类过渡科目 1606 误改为发生额口径：{f}"
                )


def test_preset_codes_belong_to_cycle(h_blocks: list[dict], h_cycle_allowed_codes: dict[str, set[str]]):
    """预设中每个科目码 ∈ 该循环的允许集。"""
    violations = []
    for block in h_blocks:
        wp = (block.get("wp_code") or "").upper()
        if wp == "H0":
            continue  # H0 是函证，不属本 spec 范围
        allowed = h_cycle_allowed_codes.get(wp, set())
        if not allowed:
            continue  # 不在注册表中的跳过（如 H0）
        codes = set(block.get("account_codes", []))
        foreign = codes - allowed
        if foreign:
            violations.append(f"{wp}/{block.get('sheet')}: {foreign} 不属于 {wp} 的允许集")
    assert not violations, f"跨循环科目码：{violations}"


# ──────────────────────────────────────────────────────────────────────────────
# Property 9: H10 损益口径
# ──────────────────────────────────────────────────────────────────────────────

def test_h10_no_balance_formula_pattern(h_blocks: list[dict]):
    """H10 预设中不应出现 '期初余额'/'期末余额' 口径（损益类用发生额）。"""
    bad_patterns = ["期初余额", "期末余额"]
    violations = []
    for block in h_blocks:
        if (block.get("wp_code") or "").upper() != "H10":
            continue
        # 检查 items 中的公式
        for item in block.get("items", []):
            if not isinstance(item, dict):
                continue
            formula = item.get("formula", "") or ""
            for pat in bad_patterns:
                if pat in formula:
                    violations.append(f"H10/{block.get('sheet')}: formula含'{pat}'")
        # 也检查 account_codes 描述文本
        desc = block.get("description", "") or ""
        for pat in bad_patterns:
            if pat in desc:
                violations.append(f"H10/{block.get('sheet')}: description含'{pat}'")
    assert not violations, f"H10 损益口径违规：{violations}"


# ──────────────────────────────────────────────────────────────────────────────
# Property 10: 幂等脚本自洽
# ──────────────────────────────────────────────────────────────────────────────

def test_fix_script_check_passes():
    """幂等脚本 `--check` 应返回 0（零欠账）。"""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.fix.fix_h_cycle_prefill_presets", "--check"],
        cwd=str(_DATA_DIR.parent),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"--check 失败：{result.stdout}\n{result.stderr}"
