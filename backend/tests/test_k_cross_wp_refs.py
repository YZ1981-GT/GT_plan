"""
test_k_cross_wp_refs.py — K-F4 cross_wp_references 新增 ≥ 20 条验证

Validates: Requirements K-F4

验证内容：
1. 双重过滤（闭区间 CW-313~CW-332 AND cycle membership：source_wp 或 target wp_code 以 K 开头）
2. 新增条目格式正确（schema 完整性）
3. ref_id 闭区间 + 唯一 + 顺序
4. severity 比例：blocking ≥ 4 / warning ≥ 8 / info < 25%
5. 5 分组覆盖：K 内部(≥4) / K→跨循环来源(≥5) / K→报表(≥4) / K→附注(≥4) / K→其他循环(≥3)
"""
import json
from pathlib import Path

import pytest

DATA_FILE = Path(__file__).parent.parent / "data" / "cross_wp_references.json"

# K 循环新增闭区间（J spec 占至 CW-312 → K spec 起编 CW-313）
K_CWR_START = 313
K_CWR_END = 332


@pytest.fixture
def cross_wp_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def k_cycle_new_refs(cross_wp_data):
    """双重过滤：闭区间 CW-313~CW-332 AND cycle membership（source_wp 或 target wp_code 以 K 开头）"""
    refs = []
    for ref in cross_wp_data["references"]:
        ref_id = ref.get("ref_id", "")
        if not ref_id.startswith("CW-"):
            continue
        try:
            num = int(ref_id.split("-")[1])
        except (IndexError, ValueError):
            continue
        if not (K_CWR_START <= num <= K_CWR_END):
            continue
        # cycle membership: source_wp starts with K OR any target wp_code starts with K
        source_is_k = ref.get("source_wp", "").startswith("K")
        target_is_k = any(
            t.get("wp_code", "").startswith("K")
            for t in ref.get("targets", [])
        )
        if source_is_k or target_is_k:
            refs.append(ref)
    return refs


class TestKCrossWpRefsCount:
    """验证新增条目数量 ≥ 20"""

    def test_new_refs_count_at_least_20(self, k_cycle_new_refs):
        assert len(k_cycle_new_refs) >= 20, (
            f"Expected ≥ 20 new K-cycle cross_wp_references, got {len(k_cycle_new_refs)}"
        )


class TestKCrossWpRefsSchema:
    """验证新增条目格式正确"""

    REQUIRED_FIELDS = {
        "ref_id",
        "description",
        "source_wp",
        "source_sheet",
        "source_cell",
        "targets",
        "category",
        "severity",
    }
    VALID_SEVERITIES = {"blocking", "warning", "info"}

    def test_all_required_fields_present(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            missing = self.REQUIRED_FIELDS - set(ref.keys())
            assert not missing, f"{ref['ref_id']} missing fields: {missing}"

    def test_severity_values_valid(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            assert ref["severity"] in self.VALID_SEVERITIES, (
                f"{ref['ref_id']} has invalid severity: {ref['severity']}"
            )

    def test_targets_non_empty(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            assert len(ref["targets"]) > 0, f"{ref['ref_id']} has empty targets"

    def test_targets_have_wp_code_and_sheet_and_formula(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            for target in ref["targets"]:
                assert "wp_code" in target, f"{ref['ref_id']} target missing wp_code"
                assert "sheet" in target, f"{ref['ref_id']} target missing sheet"
                assert "formula" in target, f"{ref['ref_id']} target missing formula"
                assert target["formula"].startswith("=WP("), (
                    f"{ref['ref_id']} target formula must start with =WP(: {target['formula']}"
                )

    def test_descriptions_non_empty(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            assert ref["description"].strip(), f"{ref['ref_id']} has empty description"


class TestKCrossWpRefsRefId:
    """验证 ref_id 闭区间 CW-313~CW-332"""

    def test_ref_ids_in_closed_interval(self, k_cycle_new_refs):
        for ref in k_cycle_new_refs:
            num = int(ref["ref_id"].split("-")[1])
            assert K_CWR_START <= num <= K_CWR_END, (
                f"{ref['ref_id']} outside closed interval CW-{K_CWR_START}~CW-{K_CWR_END}"
            )

    def test_ref_ids_unique(self, k_cycle_new_refs):
        ids = [ref["ref_id"] for ref in k_cycle_new_refs]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate ref_ids found: {set(dupes)}"

    def test_ref_ids_sequential(self, k_cycle_new_refs):
        nums = sorted(int(ref["ref_id"].split("-")[1]) for ref in k_cycle_new_refs)
        expected = list(range(K_CWR_START, K_CWR_START + len(nums)))
        assert nums == expected, f"ref_ids not sequential: got {nums}, expected {expected}"


class TestKCrossWpRefsSeverity:
    """验证 severity 比例：blocking ≥ 4 / warning ≥ 8 / info < 25%"""

    def test_blocking_at_least_4(self, k_cycle_new_refs):
        blocking = [r for r in k_cycle_new_refs if r["severity"] == "blocking"]
        assert len(blocking) >= 4, f"Expected ≥ 4 blocking, got {len(blocking)}"

    def test_warning_at_least_8(self, k_cycle_new_refs):
        warning = [r for r in k_cycle_new_refs if r["severity"] == "warning"]
        assert len(warning) >= 8, f"Expected ≥ 8 warning, got {len(warning)}"

    def test_info_less_than_25_percent(self, k_cycle_new_refs):
        info = [r for r in k_cycle_new_refs if r["severity"] == "info"]
        pct = len(info) / len(k_cycle_new_refs) * 100
        assert pct < 25, f"info percentage {pct:.1f}% exceeds 25% limit"


class TestKCrossWpRefsGroups:
    """验证 5 分组覆盖（K 内部 / K→跨循环来源 / K→报表 / K→附注 / K→其他循环）"""

    def test_k_internal_group_at_least_4(self, k_cycle_new_refs):
        """K 内部联动：source_wp 以 K 开头 AND 任一 target wp_code 以 K 开头"""
        internal = [
            r
            for r in k_cycle_new_refs
            if r["source_wp"].startswith("K")
            and any(t["wp_code"].startswith("K") for t in r["targets"])
        ]
        assert len(internal) >= 4, f"Expected ≥ 4 K internal refs, got {len(internal)}"

    def test_k_from_cross_cycle_source_at_least_5(self, k_cycle_new_refs):
        """K→跨循环来源：source_wp NOT 以 K 开头 AND 任一 target wp_code 以 K 开头
        （即外部循环数据流入 K）"""
        cross_source = [
            r
            for r in k_cycle_new_refs
            if not r["source_wp"].startswith("K")
            and any(t["wp_code"].startswith("K") for t in r["targets"])
        ]
        assert len(cross_source) >= 5, (
            f"Expected ≥ 5 cross-cycle→K refs, got {len(cross_source)}"
        )

    def test_k_to_report_at_least_4(self, k_cycle_new_refs):
        """K→报表：source_wp 以 K 开头 AND 任一 target wp_code == REPORT"""
        to_report = [
            r
            for r in k_cycle_new_refs
            if r["source_wp"].startswith("K")
            and any(t["wp_code"] == "REPORT" for t in r["targets"])
        ]
        assert len(to_report) >= 4, f"Expected ≥ 4 K→REPORT refs, got {len(to_report)}"

    def test_k_to_note_at_least_4(self, k_cycle_new_refs):
        """K→附注：source_wp 以 K 开头 AND 任一 target wp_code == NOTE"""
        to_note = [
            r
            for r in k_cycle_new_refs
            if r["source_wp"].startswith("K")
            and any(t["wp_code"] == "NOTE" for t in r["targets"])
        ]
        assert len(to_note) >= 4, f"Expected ≥ 4 K→NOTE refs, got {len(to_note)}"

    def test_k_to_other_cycle_at_least_3(self, k_cycle_new_refs):
        """K→其他循环：source_wp 以 K 开头 AND 任一 target wp_code 既不以 K 开头也不属于 REPORT/NOTE"""
        to_other = [
            r
            for r in k_cycle_new_refs
            if r["source_wp"].startswith("K")
            and any(
                (
                    not t["wp_code"].startswith("K")
                    and t["wp_code"] not in ("REPORT", "NOTE")
                )
                for t in r["targets"]
            )
        ]
        assert len(to_other) >= 3, f"Expected ≥ 3 K→other-cycle refs, got {len(to_other)}"


class TestKCrossWpRefsCycleMembership:
    """验证 cycle membership 双重过滤正确性"""

    def test_all_refs_have_k_involvement(self, k_cycle_new_refs):
        """每条 ref 必须 source_wp 以 K 开头 OR 任一 target wp_code 以 K 开头"""
        for ref in k_cycle_new_refs:
            source_k = ref["source_wp"].startswith("K")
            target_k = any(
                t.get("wp_code", "").startswith("K") for t in ref["targets"]
            )
            assert source_k or target_k, (
                f"{ref['ref_id']} has no K involvement: "
                f"source_wp={ref['source_wp']}, "
                f"targets={[t['wp_code'] for t in ref['targets']]}"
            )

    def test_no_non_k_refs_in_interval(self, cross_wp_data):
        """闭区间内不应有非 K 循环的条目（双重过滤的反向核验）"""
        for ref in cross_wp_data["references"]:
            ref_id = ref.get("ref_id", "")
            if not ref_id.startswith("CW-"):
                continue
            try:
                num = int(ref_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            if not (K_CWR_START <= num <= K_CWR_END):
                continue
            source_k = ref.get("source_wp", "").startswith("K")
            target_k = any(
                t.get("wp_code", "").startswith("K") for t in ref.get("targets", [])
            )
            assert source_k or target_k, (
                f"{ref_id} in K interval but has no K involvement"
            )


class TestKCrossWpRefsK52SheetNameSpace:
    """验证 K5-2 sheet 名包含必要空格（`明细表 K5-2`）"""

    def test_k5_2_sheet_name_with_space(self, k_cycle_new_refs):
        """K5-2 模板真实 sheet 名为 `明细表 K5-2`（K5 与 -2 之间有空格）"""
        k5_refs = [
            r
            for r in k_cycle_new_refs
            if r["source_sheet"] == "明细表 K5-2"
            or any(t.get("sheet") == "明细表 K5-2" for t in r["targets"])
        ]
        assert len(k5_refs) >= 1, (
            "Expected at least one ref using K5-2 真实 sheet 名 '明细表 K5-2'（含空格）"
        )
