"""check_rules 全科目覆盖率守卫。

钉住当前基线值（只许增加不许减少），并验证三种模式的结构完整性。
spec: note-sub-table-formula-and-cross-check Phase 4
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_check_rules import load_all_check_rules

DATA = Path(__file__).resolve().parents[1] / "data"

# ── 基线（只许 >= 不许 <）──────────────────────────────────────────────────────

_BASELINE = {
    "soe": {"sections_with_rules": 48, "total_rules": 53, "mode_a": 24, "mode_b": 29, "cross_period": 6},
    "listed": {"sections_with_rules": 56, "total_rules": 64, "mode_a": 38, "mode_b": 26, "cross_period": 18},
}


class TestCheckRulesCoverageBaseline:
    """check_rules 覆盖率棘轮：只许增长不许衰减。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_sections_with_rules_not_regressed(self, std: str):
        all_rules = load_all_check_rules(std)
        actual = len(all_rules)
        baseline = _BASELINE[std]["sections_with_rules"]
        assert actual >= baseline, (
            f"{std}: 有 check_rules 的章节 {actual} < 基线 {baseline}，不允许回退"
        )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_total_rules_not_regressed(self, std: str):
        all_rules = load_all_check_rules(std)
        total = sum(len(r) for r in all_rules.values())
        baseline = _BASELINE[std]["total_rules"]
        assert total >= baseline, (
            f"{std}: 总规则数 {total} < 基线 {baseline}，不允许回退"
        )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mode_a_not_regressed(self, std: str):
        all_rules = load_all_check_rules(std)
        count = sum(1 for rules in all_rules.values() for r in rules if r.mode == "cross_table")
        baseline = _BASELINE[std]["mode_a"]
        assert count >= baseline, f"{std}: 模式 A {count} < 基线 {baseline}"

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mode_b_not_regressed(self, std: str):
        all_rules = load_all_check_rules(std)
        count = sum(1 for rules in all_rules.values() for r in rules if r.mode == "column_balance")
        baseline = _BASELINE[std]["mode_b"]
        assert count >= baseline, f"{std}: 模式 B {count} < 基线 {baseline}"

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_cross_period_not_regressed(self, std: str):
        all_rules = load_all_check_rules(std)
        count = sum(1 for rules in all_rules.values() for r in rules if r.check_id.startswith("CT-"))
        baseline = _BASELINE[std]["cross_period"]
        assert count >= baseline, f"{std}: 跨期 CT {count} < 基线 {baseline}"


class TestCheckRulesStructuralIntegrity:
    """check_rules 结构完整性——确保规则不会因 JSON 编辑而损坏。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_duplicate_check_ids(self, std: str):
        """同一 std 内 check_id 全局唯一（模式 A/CT 的 check_id 不含行标签）。"""
        all_rules = load_all_check_rules(std)
        ids = [r.check_id for rules in all_rules.values() for r in rules if r.mode != "column_balance"]
        dupes = [cid for cid in ids if ids.count(cid) > 1]
        assert not dupes, f"{std}: 重复 check_id: {set(dupes)}"

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_mode_b_has_valid_columns(self, std: str):
        """模式 B 的四个列索引必须 >= 0 且互不相同。"""
        all_rules = load_all_check_rules(std)
        for sid, rules in all_rules.items():
            for r in rules:
                if r.mode != "column_balance":
                    continue
                cols = (r.opening_col, r.increase_col, r.decrease_col, r.closing_col)
                assert all(c >= 0 for c in cols), f"{std} {sid} {r.check_id}: 列索引有负值 {cols}"
                assert len(set(cols)) == 4, f"{std} {sid} {r.check_id}: 四列索引不互相独立 {cols}"

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_cross_table_peer_exists(self, std: str):
        """模式 A 的 peer_section_id 必须在同 std 的 JSON 中存在。"""
        data = json.loads((DATA / f"consol_note_sections_{std}.json").read_text("utf-8"))
        all_sids = {t["section_id"] for t in data if t.get("section_id")}
        all_rules = load_all_check_rules(std)
        for sid, rules in all_rules.items():
            for r in rules:
                if r.mode != "cross_table":
                    continue
                assert r.peer_section_id in all_sids, (
                    f"{std} {sid} {r.check_id}: peer_section_id '{r.peer_section_id}' 不存在"
                )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_continuation_of_targets_exist(self, std: str):
        """所有 continuation_of 指向的 section_id 必须存在。"""
        data = json.loads((DATA / f"consol_note_sections_{std}.json").read_text("utf-8"))
        all_sids = {t["section_id"] for t in data if t.get("section_id")}
        for t in data:
            cont = t.get("continuation_of")
            if cont:
                assert cont in all_sids, (
                    f"{std} {t['section_id']}: continuation_of '{cont}' 不存在"
                )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_baseline_not_inflated(self, std: str):
        """基线不得虚高超过实际值 20（防止基线被提前拉高掩盖衰减）。"""
        all_rules = load_all_check_rules(std)
        actual_sections = len(all_rules)
        actual_total = sum(len(r) for r in all_rules.values())
        bl = _BASELINE[std]
        assert bl["sections_with_rules"] <= actual_sections + 20, (
            f"{std}: 基线 sections {bl['sections_with_rules']} 远超实际 {actual_sections}"
        )
        assert bl["total_rules"] <= actual_total + 20, (
            f"{std}: 基线 total_rules {bl['total_rules']} 远超实际 {actual_total}"
        )
