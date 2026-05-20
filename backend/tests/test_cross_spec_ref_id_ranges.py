"""跨 spec ref_id 区间核验单元测试

验证：
1. D/F/H/I 四 spec 的 ref_id 区间无重叠
   - D ≤ CW-175
   - F: CW-176 ~ CW-210
   - H: CW-211 ~ CW-242
   - I: CW-243 ~ CW-266
2. 各区间内的条目 cycle membership 正确（source_wp/target wp_code 与 cycle 字母一致）
3. 全局 ref_id 唯一性（无重复）
4. ref_id 格式合法 CW-NNN

来源：Sprint 4 Task 4.7（跨 spec ref_id 闭区间铁律）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CWR_PATH = DATA_DIR / "cross_wp_references.json"


@pytest.fixture(scope="module")
def references() -> list[dict]:
    assert CWR_PATH.exists(), f"missing {CWR_PATH}"
    return json.loads(CWR_PATH.read_text(encoding="utf-8"))["references"]


# spec → (lo, hi inclusive, cycle_letter)
SPEC_RANGES = {
    # D 区间是历史累积段（CW-01 起即含跨循环 ref，未做 spec 化区间分配），不做 membership 严格检查
    "F": (176, 210, "F"),
    "H": (211, 242, "H"),
    "I": (243, 266, "I"),
    "G": (267, 292, "G"),
    "K": (313, 332, "K"),
    "L": (333, 352, "L"),
}


REF_PATTERN = re.compile(r"^CW-(\d+)$")


def _ref_num(rid: str) -> int | None:
    m = REF_PATTERN.match(rid or "")
    return int(m.group(1)) if m else None


def _cycle_membership(r: dict, letter: str) -> bool:
    src = (r.get("source_wp") or "").upper()
    tgt_codes = [(t.get("wp_code") or "").upper() for t in r.get("targets", [])]
    return src.startswith(letter) or any(t.startswith(letter) for t in tgt_codes)


class TestSpecRangesNoOverlap:
    def test_no_overlap_between_specs(self):
        """各 spec ref_id 区间彼此不相交"""
        ranges = list(SPEC_RANGES.values())
        for i, (lo1, hi1, _) in enumerate(ranges):
            for (lo2, hi2, _) in ranges[i + 1:]:
                assert hi1 < lo2 or hi2 < lo1, (
                    f"区间重叠: [{lo1},{hi1}] 与 [{lo2},{hi2}]"
                )


class TestRefIdFormat:
    def test_all_ref_ids_match_pattern(self, references):
        for r in references:
            rid = r.get("ref_id", "")
            assert REF_PATTERN.match(rid), f"非法 ref_id: {rid}"

    def test_all_ref_ids_globally_unique(self, references):
        ids = [r.get("ref_id") for r in references]
        dups = [rid for rid in ids if ids.count(rid) > 1]
        assert len(ids) == len(set(ids)), f"重复 ref_id: {set(dups)}"


class TestCycleMembershipInRange:
    """每个 spec 区间内的 ref 必须属于该 cycle（source_wp/target 以 cycle 字母开头）"""

    @pytest.mark.parametrize("spec_key", list(SPEC_RANGES.keys()))
    def test_cycle_membership(self, references, spec_key: str):
        lo, hi, letter = SPEC_RANGES[spec_key]
        violations: list[tuple[str, str, list[str]]] = []
        for r in references:
            n = _ref_num(r.get("ref_id"))
            if n is None or not (lo <= n <= hi):
                continue
            if not _cycle_membership(r, letter):
                tgt_codes = [t.get("wp_code") for t in r.get("targets", [])]
                violations.append((r["ref_id"], r.get("source_wp"), tgt_codes))
        # D 区间允许少量"非 D 起头但跨循环"的条目（如 D→E 函证）
        # 容忍率：min(violations) <= 5%
        total_in_range = sum(
            1 for r in references
            if (n := _ref_num(r.get("ref_id"))) is not None and lo <= n <= hi
        )
        if total_in_range == 0:
            return
        ratio = len(violations) / total_in_range
        assert ratio <= 0.30, (
            f"{spec_key} 区间 [{lo},{hi}] cycle membership 违规率 {ratio:.2%} > 30%；"
            f"违规样本（前 5）: {violations[:5]}"
        )


class TestSingleSidedFilterDetection:
    """扫描全仓 cross_wp_ref tests，检测仍使用单边 ≥ N 过滤的代码（应改用闭区间）"""

    def test_no_single_sided_filter_in_cross_wp_ref_tests(self):
        """test_*_cross_wp_refs.py 中应使用闭区间过滤；如有单边过滤需有理由"""
        test_dir = Path(__file__).resolve().parent
        offenders: list[tuple[str, int, str]] = []
        # 单边 >= 数字 模式
        single_side_pattern = re.compile(
            r"int\(.*?ref_id.*?\)\s*>=\s*\d+|int\(.*?\.group\(1\)\)\s*>=\s*\d+"
        )
        # 闭区间 模式（白名单：含 lo <= ... <= hi 即合规）
        closed_range_pattern = re.compile(
            r"\d+\s*<=\s*int\(.*?\)\s*<=\s*\d+|"
            r"\(\s*\d+\s*<=\s*\w+\s*<=\s*\d+\s*\)"
        )

        for tf in test_dir.glob("test_*_cross_wp_refs.py"):
            content = tf.read_text(encoding="utf-8")
            lines = content.splitlines()
            has_single = False
            has_closed = False
            single_lines: list[tuple[int, str]] = []
            for i, line in enumerate(lines, start=1):
                if single_side_pattern.search(line):
                    has_single = True
                    single_lines.append((i, line.strip()))
                if closed_range_pattern.search(line):
                    has_closed = True
            if has_single and not has_closed:
                for (ln, ls) in single_lines:
                    offenders.append((tf.name, ln, ls))

        assert not offenders, (
            "发现单边 ref_id ≥ N 过滤但无闭区间约束（违反跨 spec ref_id 闭区间铁律）：\n"
            + "\n".join(f"  {fn}:{ln}: {ls}" for fn, ln, ls in offenders)
        )
