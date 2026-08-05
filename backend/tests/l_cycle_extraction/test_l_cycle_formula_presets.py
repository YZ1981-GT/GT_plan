"""L 类公式预设守卫。

验证 Property 13：
- wp_name 与 wp_code 一致（非错位他循环）
- account_codes 属本循环报表行科目集合
- 无环：明细表块不引 WP() 指向本循环审定表
- sheet 名与预期一致

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R5, Property 13
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.l_cycle_extraction.account_scope import L_CYCLE_SPECS

PREFILL_PATH = ROOT / "data" / "prefill_formula_mapping.json"


@pytest.fixture(scope="module")
def l_prefill_blocks() -> list[dict]:
    """加载 L 类全部预设块。"""
    data = json.loads(PREFILL_PATH.read_text(encoding="utf-8"))
    return [b for b in data["mappings"] if b.get("wp_code", "").startswith("L")]


@pytest.fixture(scope="module")
def standard_account_codes() -> set[str]:
    """从 account_chart JSON 加载标准科目码集合。"""
    chart_path = ROOT / "data" / "standard_account_chart.json"
    if chart_path.exists():
        chart = json.loads(chart_path.read_text(encoding="utf-8"))
        if isinstance(chart, list):
            return {item.get("code", "") for item in chart if item.get("code")}
        elif isinstance(chart, dict) and "accounts" in chart:
            return {item.get("code", "") for item in chart["accounts"] if item.get("code")}
    # 兜底：从 L_CYCLE_SPECS 的 fallback_codes 收集已知合法码
    known = set()
    for spec in L_CYCLE_SPECS.values():
        known.update(spec.fallback_codes)
    return known


class TestLCyclePresetWpNameAlignment:
    """wp_name 必须与 wp_code 的真实科目一致。"""

    @pytest.mark.parametrize("wp_code", list(L_CYCLE_SPECS.keys()))
    def test_adjudication_block_wp_name_matches_spec(self, l_prefill_blocks, wp_code):
        """审定表块的 wp_name 包含该循环科目中文名。"""
        spec = L_CYCLE_SPECS[wp_code]
        adj_blocks = [
            b for b in l_prefill_blocks
            if b["wp_code"] == wp_code and "审定表" in b.get("sheet", "")
        ]
        if not adj_blocks:
            pytest.skip(f"{wp_code} 无审定表预设块")
        for block in adj_blocks:
            # wp_name 应包含本循环科目名
            assert spec.account_label in block["wp_name"], (
                f"{wp_code} 审定表块 wp_name={block['wp_name']!r} "
                f"不含本循环科目名 {spec.account_label!r}（疑似错位）"
            )


class TestLCyclePresetAccountCodes:
    """account_codes 必须属本循环。"""

    @pytest.mark.parametrize("wp_code", list(L_CYCLE_SPECS.keys()))
    def test_codes_are_this_cycle_fallback(self, l_prefill_blocks, wp_code):
        """审定表块的 account_codes 必须是本循环兜底码的子集或为空（宁缺勿造）。"""
        spec = L_CYCLE_SPECS[wp_code]
        adj_blocks = [
            b for b in l_prefill_blocks
            if b["wp_code"] == wp_code and "审定表" in b.get("sheet", "")
        ]
        if not adj_blocks:
            pytest.skip(f"{wp_code} 无审定表预设块")
        allowed = set(spec.fallback_codes)
        for block in adj_blocks:
            codes = set(block.get("account_codes", []))
            if not allowed:
                # 宁缺勿造（L7）：codes 应为空
                assert codes == set(), (
                    f"{wp_code} 宁缺勿造但 account_codes={codes}"
                )
            else:
                assert codes <= allowed, (
                    f"{wp_code} account_codes={codes} 不属于本循环 {allowed}"
                )


class TestLCyclePresetNoCycle:
    """明细表块的 cells 中不得有 WP() 引用本循环审定表（防成环）。"""

    def test_no_wp_ref_to_own_adjudication(self, l_prefill_blocks):
        """明细表块禁 WP() 引用本循环审定表。"""
        for block in l_prefill_blocks:
            sheet = block.get("sheet", "")
            wp_code = block.get("wp_code", "")
            if "审定表" in sheet:
                continue  # 审定表块不受此约束
            for cell in block.get("cells", []):
                formula = cell.get("formula", "")
                # WP('L3','审定表L3-1',...) 形态
                if f"WP('{wp_code}'" in formula and "审定表" in formula:
                    pytest.fail(
                        f"{wp_code}/{sheet} cell={cell['cell_ref']} "
                        f"引用本循环审定表 → 成环！formula={formula}"
                    )


class TestLCyclePresetDisplacement:
    """反向自检：确认旧错位口径已纠正。"""

    def test_l2_not_long_term_loan(self, l_prefill_blocks):
        """L2 审定表块不再是长期借款（旧错位值）。"""
        adj = [b for b in l_prefill_blocks if b["wp_code"] == "L2" and "审定表" in b.get("sheet", "")]
        for block in adj:
            assert "长期借款" not in block.get("wp_name", ""), "L2 仍错位为长期借款"
            assert "2501" not in block.get("account_codes", []), "L2 仍引用 2501"

    def test_l4_not_lease_liability(self, l_prefill_blocks):
        """L4 审定表块不再是租赁负债（旧错位值）。"""
        adj = [b for b in l_prefill_blocks if b["wp_code"] == "L4" and "审定表" in b.get("sheet", "")]
        for block in adj:
            assert "租赁负债" not in block.get("wp_name", ""), "L4 仍错位为租赁负债"
            assert "2601" not in block.get("account_codes", []), "L4 仍引用 2601"

    def test_l6_not_long_term_payable(self, l_prefill_blocks):
        """L6 审定表块不再是长期应付款（旧错位值）。"""
        adj = [b for b in l_prefill_blocks if b["wp_code"] == "L6" and "审定表" in b.get("sheet", "")]
        for block in adj:
            assert "长期应付款" not in block.get("wp_name", ""), "L6 仍错位为长期应付款"
            assert "2701" not in block.get("account_codes", []), "L6 仍引用 2701"

    def test_l7_not_provision(self, l_prefill_blocks):
        """L7 审定表块不再是预计负债（旧错位值）。"""
        adj = [b for b in l_prefill_blocks if b["wp_code"] == "L7" and "审定表" in b.get("sheet", "")]
        for block in adj:
            assert "预计负债" not in block.get("wp_name", ""), "L7 仍错位为预计负债"
            assert "2801" not in block.get("account_codes", []), "L7 仍引用 2801"
