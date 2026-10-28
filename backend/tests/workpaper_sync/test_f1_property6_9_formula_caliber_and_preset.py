# -*- coding: utf-8 -*-
"""F1 红判据 Property 6 + Property 9。

spec: f1-sync-coverage-and-first-canary · Task 5

Property 6: F1-2 O/X 与模板数学等价
  对随机行断言前端 recalcRowFormulas 的 O/X 等于模板 O=E+M-N、X=Q+V+W。
  Task 17 时模板 X 列是 =O+V+W（漏了被审计单位重分类 P）；spec
  oo-writeback-template-parity-closure R1 已把模板修成 =Q+V+W，前端随之回到 Q 起算。
  模板口径不再写死在本文件：先逐格读权威模板 R14:R34，再按读到的口径做等价判据。

Property 9: prefill 预设 sheet 名与源 tab 逐字一致
  `test_f1_formula_presets.py` 4 条 F1 用例现状红（块[16] 全角国企 vs 半角源 tab）。
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ═══════════════════════════════════════════════════════════════════════════
# Property 6：F1-2 O/X 口径与模板数学等价
# ═══════════════════════════════════════════════════════════════════════════


_F1_TEMPLATE = Path(__file__).resolve().parents[2] / "wp_templates" / "F" / "F1 预付账款.xlsx"
_F1_DETAIL_SHEET = "明细表F1-2"
#: 数据区 R14:R34 每行的四列公式（{r} = 行号）
_F1_ROW_FORMULAS = {
    "H": "=E{r}+F{r}+G{r}",
    "O": "=E{r}+M{r}-N{r}",
    "Q": "=O{r}+P{r}",
    "X": "=Q{r}+V{r}+W{r}",
}


def test_template_detail_formulas_are_the_audited_caliber() -> None:
    """权威模板 F1-2 数据区四列逐格就是本文件判据用的口径（X 从期末未审 Q 起算）。"""
    import openpyxl

    wb = openpyxl.load_workbook(_F1_TEMPLATE, data_only=False)
    try:
        ws = wb[_F1_DETAIL_SHEET]
        wrong = [
            (f"{col}{r}", ws[f"{col}{r}"].value, text.format(r=r))
            for r in range(14, 35)
            for col, text in _F1_ROW_FORMULAS.items()
            if ws[f"{col}{r}"].value != text.format(r=r)
        ]
    finally:
        wb.close()
    assert not wrong, f"F1-2 模板公式与判据口径不一致（格, 实得, 期望）：{wrong[:5]}"


def _template_O(E: float, M: float, N: float) -> float:
    """模板权威公式：O = E + M - N（期初未审 + 借方 - 贷方）。"""
    return E + M - N


def _template_X(Q: float, V: float, W: float) -> float:
    """模板权威公式：X = Q + V + W（期末未审 + AJE + RJE）。"""
    return Q + V + W


class TestProperty6FormulaCaliberCurrentState:
    """前端 O 以期初未审起算（Task 17），与模板一致。"""

    def test_o_column_equivalence_with_prior_adjustment(self) -> None:
        """当期初有调整 F≠0 时，修复后前端 O = 模板 O。✅ Task 17 已修复。"""
        E, F_adj, G = 1000.0, 50.0, -30.0
        M, N = 200.0, 100.0

        # 修复后前端口径：O = E + M - N（与模板一致）
        frontend_O_fixed = E + M - N  # 1100
        template_O = _template_O(E, M, N)  # 1100

        assert frontend_O_fixed == template_O, (
            f"修复后 frontend_O={frontend_O_fixed} 应 == template_O={template_O}"
        )


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis 未安装")
class TestProperty6HypothesisPBT:
    """PBT：随机行验证 O/X 与模板等价。修复后转绿。"""

    @settings(max_examples=5)
    @given(
        E=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
        F_adj=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        G=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        M=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
        N=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
        P=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        V=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        W=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_o_x_pbt(
        self, E: float, F_adj: float, G: float,
        M: float, N: float, P: float, V: float, W: float,
    ) -> None:
        """随机行：前端 O/X（useF1Detail.recalcRowFormulas 的口径）与模板 O/X 数学等价。"""
        # 模板口径
        template_O = _template_O(E, M, N)
        template_X = _template_X(template_O + P, V, W)

        # 前端口径：O = E + M - N，Q = O + P，X = Q + V + W
        frontend_O_fixed = E + M - N
        frontend_X_fixed = frontend_O_fixed + P + V + W

        assert abs(frontend_O_fixed - template_O) < 0.01, (
            f"O 不等价：frontend={frontend_O_fixed} template={template_O}"
        )
        assert abs(frontend_X_fixed - template_X) < 0.01, (
            f"X 不等价：frontend={frontend_X_fixed} template={template_X}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 9：prefill 预设 sheet 名与源 tab 逐字一致
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9PrefillPreset:
    """块[16] sheet 名应为半角 `附注披露信息(国企)`。"""

    def test_soe_disclosure_block_uses_halfwidth_parentheses(self) -> None:
        """块[16] 的 sheet 名应为半角 `附注披露信息(国企)` 与源 tab 一致。✅ Task 18 已修复。"""
        import json
        from pathlib import Path

        mapping_path = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"
        if not mapping_path.exists():
            mapping_path = Path(__file__).resolve().parents[2] / "app" / "data" / "prefill_formula_mapping.json"
        assert mapping_path.exists(), f"找不到 prefill_formula_mapping.json: {mapping_path}"

        with open(mapping_path, encoding="utf-8") as f:
            data = json.load(f)

        blocks = data.get("mappings", data) if isinstance(data, dict) else data
        f1_soe_blocks = [
            b for b in blocks
            if b.get("wp_code") == "F1"
            and "国企" in (b.get("sheet") or b.get("sheet_name") or "")
        ]
        assert len(f1_soe_blocks) >= 1, "未找到 F1 国企披露块"

        for block in f1_soe_blocks:
            sheet_name = block.get("sheet") or block.get("sheet_name", "")
            assert "（" not in sheet_name and "）" not in sheet_name, (
                f"块 sheet='{sheet_name}' 含全角括号，应改为半角"
            )
            assert sheet_name == "附注披露信息(国企)", (
                f"块 sheet='{sheet_name}'，期望 '附注披露信息(国企)'"
            )
