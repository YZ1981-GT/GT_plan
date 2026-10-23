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

# 2026-10-23 R7.6 国企章节号按 Word 重对齐：同一张 Word 表的重复条目并成一条、规则随之合并（53 条一条不少），
# 带规则的章节 48 → 43（规则逐条核对见 R7.5）。
# 2026-10-23 R7.5 规则逐条核对（design §16.9 批 8c）：主动删的不是回退 ——
#   跨期 CT 24 条全删（同一年度内比续表期初与前表期末，不成立；只有比上年同表才成立，几条「续表」还不是续表）；
#   跨表 国企删 7 / 上市删 7（说明的关系不成立：大额 / 重要明细 ≠ 全表合计、减值准备 ≠ 原值、抵销后 ≠ 未抵销、
#   错挂的规则、上市没有坏账分类表；上市 F9-4 随合同资产净额简表删）、其余按标题行库语义改对两侧单元格；
#   列平衡 删 5 张标题行库认不出变动表的（两期余额表 / 数量 + 账面价值两套期初期末）、合并位置带来的重复 4 条。
#   语义另由 test_consol_note_check_rules_semantics.py 逐条钉住。
_BASELINE = {
    "soe": {"sections_with_rules": 32, "total_rules": 34, "mode_a": 11, "mode_b": 23, "cross_period": 0},
    "listed": {"sections_with_rules": 31, "total_rules": 36, "mode_a": 13, "mode_b": 23, "cross_period": 0},
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
    def test_mode_b_columns_come_from_header_library(self, std: str):
        """模式 B 不在种子里写列号（R7.5：原手写列号 16 条与表头不符），期初 / 期末 / 增减列由标题行库按表头认。"""
        from app.services.note_check_rules import rollforward_for

        data = json.loads((DATA / f"consol_note_sections_{std}.json").read_text("utf-8"))
        for t in data:
            for r in t.get("check_rules") or []:
                if r.get("mode") != "column_balance":
                    continue
                written = sorted(k for k in ("opening_col", "increase_col", "decrease_col", "closing_col") if k in r)
                assert not written, f"{std} {t['section_id']} {r['check_id']}: 种子里写了列号 {written}"
                assert rollforward_for(std, t["section_id"]) is not None, f"{std} {t['section_id']}: 标题行库认不出变动表"

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
