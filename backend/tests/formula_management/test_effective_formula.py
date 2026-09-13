# -*- coding: utf-8 -*-
"""有效公式解析器 — 预设+自定义单一真源治理守卫。

Spec: d4-adjustment-and-analysis-gap-closure Task 3 / Task 5
Requirements: 2.3

守 6 态状态机 + 「custom 优先、删 custom 回落 preset、预设升级不覆盖 custom」+
schema 白名单（禁 eval/外链）。用可注入的 preset_index 避免依赖真实预设库文件内容，
每条断言对应一个可变异点。
"""

from __future__ import annotations

import pytest

from app.services.formula_management.effective_formula import (
    EffectiveFormula,
    make_formula_key,
    resolve_effective_formula,
    validate_expression,
)
from app.services.formula_management.preset_library import PresetEntry


def _index(page_key: str, target_cell: str, expression: str, formula_type: str = "auto_calc"):
    entry = PresetEntry(
        page_key=page_key,
        target_cell=target_cell,
        expression=expression,
        formula_type=formula_type,
        refs=[],
        source="prefill_formula_mapping",
        description="",
    )
    return {page_key: [entry]}


class TestFormulaKey:
    def test_key_serializes_all_five_parts_stably(self) -> None:
        k = make_formula_key("wp1", "workpaper:D4-4", "row3", "C", "alt")
        s = k.serialize()
        assert "wp1" in s and "workpaper:D4-4" in s and "row3" in s and "C" in s and "alt" in s
        # 稳定：同输入同输出。
        assert make_formula_key("wp1", "workpaper:D4-4", "row3", "C", "alt").serialize() == s

    def test_page_key_is_stable_sheet_key(self) -> None:
        k = make_formula_key("wp1", "workpaper:D4-4", "row3", "C")
        assert k.page_key == "workpaper:D4-4"


class TestSingleSourceOfTruth:
    def test_no_custom_falls_back_to_preset(self) -> None:
        idx = _index("workpaper:D4-4", "C", "=TB(6001)")
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            preset_index=idx,
        )
        assert r.state == "preset"
        assert r.expression == "=TB(6001)"
        assert r.source.startswith("preset:")

    def test_custom_overrides_preset(self) -> None:
        idx = _index("workpaper:D4-4", "C", "=TB(6001)")
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            custom_expression="=TB(6001)+WP('D4-2')",
            preset_index=idx,
        )
        assert r.state == "custom"
        assert r.expression == "=TB(6001)+WP('D4-2')"
        # 预设仍作为可恢复底稿保留。
        assert r.preset_expression == "=TB(6001)"

    def test_deleting_custom_restores_preset(self) -> None:
        """删 custom = 调用方不再传 override → 自动回落 preset，无需显式回填。"""
        idx = _index("workpaper:D4-4", "C", "=TB(6001)")
        key = make_formula_key("wp1", "workpaper:D4-4", "r1", "C")
        with_custom = resolve_effective_formula(key, custom_expression="=SUM(1:3,2)", preset_index=idx)
        assert with_custom.state == "custom"
        after_delete = resolve_effective_formula(key, custom_expression=None, preset_index=idx)
        assert after_delete.state == "preset"
        assert after_delete.expression == "=TB(6001)"

    def test_preset_upgrade_does_not_clobber_custom(self) -> None:
        """预设升级（换了新的预设表达式）不动 custom：有 custom 恒返回 custom。"""
        upgraded = _index("workpaper:D4-4", "C", "=TB(6001)+TB(6051)")  # 新预设
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            custom_expression="=TB(6001)",  # 用户旧自定义
            preset_index=upgraded,
        )
        assert r.state == "custom"
        assert r.expression == "=TB(6001)"
        # 但 preset_expression 反映升级后的新预设（供用户选择是否采纳）。
        assert r.preset_expression == "=TB(6001)+TB(6051)"


class TestStates:
    def test_preset_missing_when_no_preset_and_no_custom(self) -> None:
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:UNKNOWN", "r1", "C"),
            preset_index={},
        )
        assert r.state == "preset_missing"
        assert r.expression is None

    def test_corrupt_when_expression_illegal(self) -> None:
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            custom_expression="=eval('1+1')",
            preset_index={},
        )
        assert r.state == "corrupt"
        assert r.expression is None

    def test_stale_state_preserves_expression(self) -> None:
        idx = _index("workpaper:D4-4", "C", "=TB(6001)")
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            is_stale=True,
            preset_index=idx,
        )
        assert r.state == "stale"
        assert r.expression == "=TB(6001)"

    def test_blocked_state_is_read_only_but_shows_value(self) -> None:
        idx = _index("workpaper:D4-4", "C", "=TB(6001)")
        r = resolve_effective_formula(
            make_formula_key("wp1", "workpaper:D4-4", "r1", "C"),
            is_blocked=True,
            preset_index=idx,
        )
        assert r.state == "blocked"
        assert r.expression == "=TB(6001)"  # 只读展示，不隐藏


class TestSchemaWhitelist:
    @pytest.mark.parametrize(
        "expr",
        [
            "=eval('x')",
            "=__import__('os')",
            "=WP('http://evil.com')",
            "=cell(1,2).__class__",
            "=exec('y')",
            "=file:///etc/passwd",
        ],
    )
    def test_forbidden_forms_rejected(self, expr: str) -> None:
        ok, reason = validate_expression(expr)
        assert ok is False
        assert reason

    @pytest.mark.parametrize(
        "expr",
        [
            "=TB(6001)",
            "=TB(6001)+WP('D4-2')",
            "=SUM(1:5,3)",
            "=cell(3,2)+cell(4,2)",
            "=ROUND(TB(6001),2)",
        ],
    )
    def test_allowed_forms_pass(self, expr: str) -> None:
        ok, reason = validate_expression(expr)
        assert ok is True, reason

    def test_whitelist_rejects_unknown_function(self) -> None:
        ok, reason = validate_expression("=DANGEROUS(1)")
        assert ok is False
        assert "DANGEROUS" in reason
