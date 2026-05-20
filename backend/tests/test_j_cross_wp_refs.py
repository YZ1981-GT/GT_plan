"""
test_j_cross_wp_refs.py — J-F4 cross_wp_references 新增 ≥ 20 条验证

验证内容：
1. 新增条目格式正确（schema 完整性）
2. ref_id 闭区间 CW-293~CW-312
3. cycle membership 双重过滤（source_wp 或 target wp_code 以 J 开头）
4. severity 比例：blocking ≥ 6 / warning ≥ 8 / info ≤ 5（info < 25%）
5. 5 分组覆盖完整
"""
import json
from pathlib import Path

import pytest

DATA_FILE = Path(__file__).parent.parent / "data" / "cross_wp_references.json"

# J 循环新增闭区间
J_CWR_START = 293
J_CWR_END = 312


@pytest.fixture
def cross_wp_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def j_cycle_new_refs(cross_wp_data):
    """双重过滤：闭区间 CW-293~CW-312 AND cycle membership（source_wp 或 target wp_code 以 J 开头）"""
    refs = []
    for ref in cross_wp_data["references"]:
        ref_id = ref.get("ref_id", "")
        if not ref_id.startswith("CW-"):
            continue
        num = int(ref_id.split("-")[1])
        if not (J_CWR_START <= num <= J_CWR_END):
            continue
        # cycle membership: source_wp starts with J OR any target wp_code starts with J
        source_is_j = ref.get("source_wp", "").startswith("J")
        target_is_j = any(
            t.get("wp_code", "").startswith("J")
            for t in ref.get("targets", [])
        )
        if source_is_j or target_is_j:
            refs.append(ref)
    return refs


class TestJCrossWpRefsCount:
    """验证新增条目数量 ≥ 20"""

    def test_new_refs_count_at_least_20(self, j_cycle_new_refs):
        assert len(j_cycle_new_refs) >= 20, (
            f"Expected ≥ 20 new J-cycle cross_wp_references, got {len(j_cycle_new_refs)}"
        )


class TestJCrossWpRefsSchema:
    """验证新增条目格式正确"""

    REQUIRED_FIELDS = {"ref_id", "description", "source_wp", "source_sheet", "source_cell", "targets", "category", "severity"}
    VALID_SEVERITIES = {"blocking", "warning", "info"}

    def test_all_required_fields_present(self, j_cycle_new_refs):
        for ref in j_cycle_new_refs:
            missing = self.REQUIRED_FIELDS - set(ref.keys())
            assert not missing, (
                f"{ref['ref_id']} missing fields: {missing}"
            )

    def test_severity_values_valid(self, j_cycle_new_refs):
        for ref in j_cycle_new_refs:
            assert ref["severity"] in self.VALID_SEVERITIES, (
                f"{ref['ref_id']} has invalid severity: {ref['severity']}"
            )

    def test_targets_non_empty(self, j_cycle_new_refs):
        for ref in j_cycle_new_refs:
            assert len(ref["targets"]) > 0, (
                f"{ref['ref_id']} has empty targets"
            )

    def test_targets_have_wp_code(self, j_cycle_new_refs):
        for ref in j_cycle_new_refs:
            for target in ref["targets"]:
                assert "wp_code" in target, (
                    f"{ref['ref_id']} target missing wp_code"
                )


class TestJCrossWpRefsRefId:
    """验证 ref_id 闭区间 CW-293~CW-312"""

    def test_ref_ids_in_closed_interval(self, j_cycle_new_refs):
        for ref in j_cycle_new_refs:
            num = int(ref["ref_id"].split("-")[1])
            assert J_CWR_START <= num <= J_CWR_END, (
                f"{ref['ref_id']} outside closed interval CW-{J_CWR_START}~CW-{J_CWR_END}"
            )

    def test_ref_ids_unique(self, j_cycle_new_refs):
        ids = [ref["ref_id"] for ref in j_cycle_new_refs]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_ref_ids_sequential(self, j_cycle_new_refs):
        nums = sorted(int(ref["ref_id"].split("-")[1]) for ref in j_cycle_new_refs)
        expected = list(range(J_CWR_START, J_CWR_START + len(nums)))
        assert nums == expected, (
            f"ref_ids not sequential: got {nums}, expected {expected}"
        )


class TestJCrossWpRefsSeverity:
    """验证 severity 比例"""

    def test_blocking_at_least_6(self, j_cycle_new_refs):
        blocking = [r for r in j_cycle_new_refs if r["severity"] == "blocking"]
        assert len(blocking) >= 6, (
            f"Expected ≥ 6 blocking, got {len(blocking)}"
        )

    def test_warning_at_least_8(self, j_cycle_new_refs):
        warning = [r for r in j_cycle_new_refs if r["severity"] == "warning"]
        assert len(warning) >= 8, (
            f"Expected ≥ 8 warning, got {len(warning)}"
        )

    def test_info_at_most_5(self, j_cycle_new_refs):
        info = [r for r in j_cycle_new_refs if r["severity"] == "info"]
        assert len(info) <= 5, (
            f"Expected ≤ 5 info, got {len(info)}"
        )

    def test_info_less_than_25_percent(self, j_cycle_new_refs):
        info = [r for r in j_cycle_new_refs if r["severity"] == "info"]
        pct = len(info) / len(j_cycle_new_refs) * 100
        assert pct < 25, (
            f"info percentage {pct:.1f}% exceeds 25% limit"
        )


class TestJCrossWpRefsGroups:
    """验证 5 分组覆盖"""

    def test_j_internal_group(self, j_cycle_new_refs):
        """J 内部联动：source_wp 以 J 开头 AND target wp_code 以 J 开头"""
        internal = [
            r for r in j_cycle_new_refs
            if r["source_wp"].startswith("J")
            and any(t["wp_code"].startswith("J") for t in r["targets"])
        ]
        assert len(internal) >= 4, (
            f"Expected ≥ 4 J internal refs, got {len(internal)}"
        )

    def test_j_to_expense_group(self, j_cycle_new_refs):
        """J→费用循环：target wp_code in (D5, K8, K9, F2, H1)"""
        expense_targets = {"D5", "K8", "K9", "F2", "H1"}
        expense = [
            r for r in j_cycle_new_refs
            if any(t["wp_code"] in expense_targets for t in r["targets"])
        ]
        assert len(expense) >= 5, (
            f"Expected ≥ 5 J→expense refs, got {len(expense)}"
        )

    def test_j_to_report_group(self, j_cycle_new_refs):
        """J→报表：target wp_code == REPORT"""
        report = [
            r for r in j_cycle_new_refs
            if any(t["wp_code"] == "REPORT" for t in r["targets"])
        ]
        assert len(report) >= 4, (
            f"Expected ≥ 4 J→report refs, got {len(report)}"
        )

    def test_j_to_note_group(self, j_cycle_new_refs):
        """J→附注：target wp_code == NOTE"""
        note = [
            r for r in j_cycle_new_refs
            if any(t["wp_code"] == "NOTE" for t in r["targets"])
        ]
        assert len(note) >= 4, (
            f"Expected ≥ 4 J→note refs, got {len(note)}"
        )

    def test_j_to_tax_group(self, j_cycle_new_refs):
        """J→N 税费：target wp_code starts with N"""
        tax = [
            r for r in j_cycle_new_refs
            if any(t["wp_code"].startswith("N") for t in r["targets"])
        ]
        assert len(tax) >= 3, (
            f"Expected ≥ 3 J→N tax refs, got {len(tax)}"
        )


class TestJCrossWpRefsCycleMembership:
    """验证 cycle membership 双重过滤正确性"""

    def test_all_refs_have_j_involvement(self, j_cycle_new_refs):
        """每条 ref 必须 source_wp 以 J 开头 OR target wp_code 以 J 开头"""
        for ref in j_cycle_new_refs:
            source_j = ref["source_wp"].startswith("J")
            target_j = any(
                t.get("wp_code", "").startswith("J")
                for t in ref["targets"]
            )
            assert source_j or target_j, (
                f"{ref['ref_id']} has no J involvement: "
                f"source_wp={ref['source_wp']}, targets={[t['wp_code'] for t in ref['targets']]}"
            )

    def test_no_non_j_refs_in_interval(self, cross_wp_data):
        """闭区间内不应有非 J 循环的条目"""
        for ref in cross_wp_data["references"]:
            ref_id = ref.get("ref_id", "")
            if not ref_id.startswith("CW-"):
                continue
            num = int(ref_id.split("-")[1])
            if not (J_CWR_START <= num <= J_CWR_END):
                continue
            source_j = ref.get("source_wp", "").startswith("J")
            target_j = any(
                t.get("wp_code", "").startswith("J")
                for t in ref.get("targets", [])
            )
            assert source_j or target_j, (
                f"{ref_id} in J interval but has no J involvement"
            )
