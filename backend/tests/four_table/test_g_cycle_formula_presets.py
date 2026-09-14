"""守卫：G 循环公式预设科目码正确性与披露块覆盖。

锁定 `fix_g_cycle_prefill_presets.py`（审定表块纠偏）+
`fix_g_cycle_disclosure_presets.py`（披露块补全）的结果。

Property 8：审定表块的科目码属于本循环报表行
Property 9：损益类审定表块口径 = 本期发生额
Property 10：每个有披露 sheet 的循环都有对应的披露块
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
MAPPING_PATH = BACKEND / "data" / "prefill_formula_mapping.json"
DISCLOSURE_SCRIPT = BACKEND / "scripts" / "fix" / "fix_g_cycle_disclosure_presets.py"

# 科目真源（g_cycle_specs.py 实证）
G_ACCOUNT_CODES = {
    "G1": "1101", "G2": "1132", "G3": "1131", "G4": "1504",
    "G5": "1531", "G6": "1506", "G7": "1511", "G8": "1507",
    "G9": "1519", "G10": "2101", "G11": "6111", "G12": "6103",
    "G13": "6101", "G14": "6702",
}

# 损益类循环（口径 = 本期发生额，不是期末余额）
PL_CYCLES = {"G11", "G12", "G13", "G14"}


@pytest.fixture(scope="module")
def g_mappings():
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return [m for m in data.get("mappings", []) if m.get("wp_code", "").startswith("G")]


# ─── Property 8: 审定表块科目码属于本循环 ─────────────────────────────────────


def test_property_8_adjudication_account_codes(g_mappings):
    """审定表块的 account_codes 应包含本循环科目。"""
    adj_blocks = [m for m in g_mappings if "审定表" in m.get("sheet", "")]
    assert len(adj_blocks) >= 14, f"审定表块不足 14 个（实际 {len(adj_blocks)}）"

    for block in adj_blocks:
        wp_code = block["wp_code"]
        expected_code = G_ACCOUNT_CODES.get(wp_code)
        if not expected_code:
            continue
        codes = block.get("account_codes", [])
        if not codes:
            # 空占位块（4.1 之前的遗留），跳过
            continue
        assert expected_code in codes, (
            f"{wp_code} 审定表块 account_codes {codes} 不含 {expected_code}"
        )


# ─── Property 9: 损益类口径 = 本期发生额 ─────────────────────────────────────


def test_property_9_pl_cycles_use_current_period(g_mappings):
    """损益类循环的公式应使用本期发生额而非期末余额。"""
    for block in g_mappings:
        wp_code = block["wp_code"]
        if wp_code not in PL_CYCLES:
            continue
        cells = block.get("cells", [])
        for cell in cells:
            formula = cell.get("formula", "")
            if not formula or "TB(" not in formula:
                continue
            # 损益类 TB 公式应含「本期发生额」，不应含「期末余额」
            if "期末余额" in formula:
                # 🔴 排除 PREV() 里嵌套的 TB 引用（PREV 取上期的期末是对的）
                if "PREV(" in formula:
                    continue
                pytest.fail(
                    f"{wp_code}|{block.get('sheet', '')} 的 {cell.get('cell_ref', '')}"
                    f" 使用「期末余额」（损益类应用「本期发生额」）: {formula}"
                )


# ─── Property 10: 披露块覆盖完整 ─────────────────────────────────────────


def test_property_10_disclosure_blocks_complete(g_mappings):
    """每个有披露 sheet 的 G 循环都有对应的两变体披露块。"""
    disc_blocks = [
        m for m in g_mappings
        if "附注" in m.get("sheet", "") or "披露" in m.get("sheet", "")
    ]
    # 按 wp_code 分组
    by_code = {}
    for b in disc_blocks:
        by_code.setdefault(b["wp_code"], []).append(b)

    # G0 无披露 sheet，跳过；其余 G1~G14 应各有 2 个变体
    for code in ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
                 "G10", "G11", "G12", "G13", "G14"]:
        blocks = by_code.get(code, [])
        assert len(blocks) >= 2, (
            f"{code} 只有 {len(blocks)} 个披露块（应至少 2 个：上市+国企）"
        )


def test_disclosure_presets_script_check():
    """幂等脚本 --check 应返回 0 项欠账。

    🔴 `encoding="utf-8"` 必须显式声明：Windows 上 ``text=True`` 用 locale 编码
    （GBK）解码子进程输出，而脚本输出含中文 → reader thread 抛
    ``UnicodeDecodeError`` → ``result.stdout`` 变 ``None`` → 断言以
    ``TypeError: argument of type 'NoneType' is not iterable`` 恒失败。
    表现为「守卫恒红且零信号」——既判不出脚本真有欠账，也判不出脚本是好的。
    """
    result = subprocess.run(
        [sys.executable, str(DISCLOSURE_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(BACKEND),
    )
    assert result.stdout is not None, (
        "子进程 stdout 解码失败（应已由 encoding='utf-8' 兜住）"
    )
    assert result.returncode == 0, f"--check failed:\n{result.stdout}\n{result.stderr}"
    assert "0 项欠账" in result.stdout, f"--check 输出未见「0 项欠账」:\n{result.stdout}"


# ─── 反向自检：已纠偏的错码不得复活 ─────────────────────────────────────────


KNOWN_BAD_CODES = {
    "G4": ["1501"],  # 旧值是持有至到期投资
    "G6": ["1505", "1503"],  # 旧值是债权投资减值准备 / 可供出售
    "G8": ["1506", "1503"],  # 旧值是其他债权投资 / 可供出售
    "G9": ["1507", "1510", "1504"],  # 旧值连续偏移
    "G14": ["6701"],  # 旧值是资产减值损失（IS-016↔017 互换）
    "G12": ["6115"],  # 旧值是资产处置损益
}


def test_known_bad_codes_not_present(g_mappings):
    """已实证的错码不得复活。"""
    for block in g_mappings:
        wp_code = block["wp_code"]
        bad_set = KNOWN_BAD_CODES.get(wp_code)
        if not bad_set:
            continue
        codes = block.get("account_codes", [])
        for cell in block.get("cells", []):
            formula = cell.get("formula", "")
            for bad in bad_set:
                if bad in codes:
                    pytest.fail(
                        f"{wp_code} account_codes 含已纠偏的错码 {bad}"
                    )
                if f"TB('{bad}'" in formula or f"TB(\"{bad}\"" in formula:
                    pytest.fail(
                        f"{wp_code}|{block.get('sheet', '')} 公式含已纠偏错码"
                        f" {bad}: {formula[:80]}"
                    )
