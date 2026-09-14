"""
test_catalog_gap_count_integrity.py — P13: gap_count == 明细计数之和

单元测试验证 catalog_report.json 的 gap_count 与明细计数守恒关系。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

Feature: acnr-runtime-convergence, Task 12
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# 确保可导入 CI 脚本
_SCRIPTS_CHECK_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "check"
sys.path.insert(0, str(_SCRIPTS_CHECK_DIR))

from check_acnr_catalog_drift import (  # noqa: E402
    check_gap_count_conservation,
    check_staleness,
    compute_expected_gap_count,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(
    *,
    alias_conflicts: list | None = None,
    acknowledged_conflicts: list | None = None,
    unregistered_aliases: list | None = None,
    gaps: list | None = None,
    gap_count: int | None = None,
    sheets_with_skip_reason: int = 0,
    generated_at: str | None = None,
) -> dict:
    """构建一个最小化的 catalog_report 结构。"""
    if alias_conflicts is None:
        alias_conflicts = []
    if acknowledged_conflicts is None:
        acknowledged_conflicts = []
    if unregistered_aliases is None:
        unregistered_aliases = []
    if gaps is None:
        gaps = []
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    # 计算期望 gap_count
    acknowledged_aliases_set = {c.get("alias") for c in acknowledged_conflicts}
    effective_conflicts = [
        c for c in alias_conflicts
        if c.get("alias") not in acknowledged_aliases_set
    ]
    expected_gap = (
        len(effective_conflicts) + len(unregistered_aliases) + len(gaps) + sheets_with_skip_reason
    )

    if gap_count is None:
        gap_count = expected_gap

    return {
        "generated_at": generated_at,
        "registry_version": "20260710000000",
        "manifest_blocked": False,
        "alias_conflicts": alias_conflicts,
        "acknowledged_conflicts": acknowledged_conflicts,
        "gaps": gaps,
        "unregistered_aliases": unregistered_aliases,
        "summary": {
            "total_sheets": 100,
            "total_cells": 200,
            "alias_conflict_count": len(alias_conflicts),
            "gap_count": gap_count,
            "unregistered_alias_count": len(unregistered_aliases),
            "sheets_with_skip_reason": sheets_with_skip_reason,
            "acknowledged_conflict_count": len(acknowledged_conflicts),
        },
    }


# ---------------------------------------------------------------------------
# Test: gap_count 守恒 (Req-10.1)
# ---------------------------------------------------------------------------


class TestGapCountConservation:
    """P13: gap_count == 明细计数之和。"""

    def test_all_zero(self):
        """全空时 gap_count == 0。"""
        report = _make_report()
        assert compute_expected_gap_count(report) == 0
        assert check_gap_count_conservation(report) == []

    def test_alias_conflicts_only(self):
        """仅有 alias_conflicts 时 gap_count == alias_conflicts 数量。"""
        conflicts = [
            {"alias": "foo", "sheet_codes": ["A", "B"], "action": "blocked"},
            {"alias": "bar", "sheet_codes": ["C", "D"], "action": "blocked"},
        ]
        report = _make_report(alias_conflicts=conflicts)
        assert compute_expected_gap_count(report) == 2
        assert check_gap_count_conservation(report) == []

    def test_unregistered_aliases_only(self):
        """仅有 unregistered_aliases 时 gap_count == unregistered 数量。"""
        unregistered = [
            {"sheet_code": "X1", "aliases": ["x"], "reason": "not found"},
            {"sheet_code": "X2", "aliases": ["y"], "reason": "not found"},
            {"sheet_code": "X3", "aliases": ["z"], "reason": "not found"},
        ]
        report = _make_report(unregistered_aliases=unregistered)
        assert compute_expected_gap_count(report) == 3
        assert check_gap_count_conservation(report) == []

    def test_combined_counts(self):
        """多种缺口类型组合时 gap_count 等于各项之和。"""
        conflicts = [{"alias": "a", "sheet_codes": ["S1", "S2"], "action": "blocked"}]
        unregistered = [
            {"sheet_code": "U1", "aliases": ["u1"], "reason": "not found"},
            {"sheet_code": "U2", "aliases": ["u2"], "reason": "not found"},
        ]
        gaps = [{"addr_id": "X/Y/Z", "type": "semantic_only_missing_a1"}]
        report = _make_report(
            alias_conflicts=conflicts,
            unregistered_aliases=unregistered,
            gaps=gaps,
            sheets_with_skip_reason=1,
        )
        # 1 conflict + 2 unregistered + 1 gap + 1 skip = 5
        assert compute_expected_gap_count(report) == 5
        assert check_gap_count_conservation(report) == []

    def test_mismatch_detected(self):
        """gap_count 与明细不一致时应报错。"""
        conflicts = [{"alias": "a", "sheet_codes": ["S1", "S2"], "action": "blocked"}]
        unregistered = [{"sheet_code": "U1", "aliases": ["u1"], "reason": "not found"}]
        # 故意设错误 gap_count = 0（应为 2）
        report = _make_report(
            alias_conflicts=conflicts,
            unregistered_aliases=unregistered,
            gap_count=0,
        )
        errors = check_gap_count_conservation(report)
        assert len(errors) >= 1
        assert "mismatch" in errors[0]

    def test_acknowledged_conflicts_deducted(self):
        """已确认例外(acknowledged) 从 gap_count 扣除。

        Validates: Req-10.4
        """
        conflicts = [
            {"alias": "known", "sheet_codes": ["A", "B"], "action": "acknowledged"},
            {"alias": "real", "sheet_codes": ["C", "D"], "action": "blocked"},
        ]
        acknowledged = [
            {"alias": "known", "sheet_codes": ["A", "B"], "reason": "legacy compat"},
        ]
        report = _make_report(
            alias_conflicts=conflicts,
            acknowledged_conflicts=acknowledged,
        )
        # known 被扣除，只算 real = 1
        assert compute_expected_gap_count(report) == 1
        assert check_gap_count_conservation(report) == []


# ---------------------------------------------------------------------------
# Test: generated_at 陈旧度 (Req-10.3)
# ---------------------------------------------------------------------------


class TestStaleness:
    """generated_at 时间戳陈旧度校验。"""

    def test_fresh_report_passes(self):
        """1 天内的报告不报错。"""
        ts = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        report = _make_report(generated_at=ts)
        assert check_staleness(report) == []

    def test_stale_report_fails(self):
        """超过 7 天的报告应报错。"""
        ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        report = _make_report(generated_at=ts)
        errors = check_staleness(report)
        assert len(errors) == 1
        assert "stale" in errors[0]

    def test_exactly_7_days_passes(self):
        """恰好 7 天不报错（边界条件）。"""
        ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        report = _make_report(generated_at=ts)
        # timedelta(days=7) == timedelta(days=7) → not > → pass
        assert check_staleness(report) == []

    def test_missing_generated_at(self):
        """缺失 generated_at 应报错。"""
        report = _make_report()
        del report["generated_at"]
        errors = check_staleness(report)
        assert len(errors) == 1
        assert "missing" in errors[0]

    def test_invalid_timestamp_format(self):
        """无效时间戳格式应报错。"""
        report = _make_report(generated_at="not-a-date")
        errors = check_staleness(report)
        assert len(errors) == 1
        assert "not a valid" in errors[0]


# ---------------------------------------------------------------------------
# Test: 真实 catalog_report.json 守恒 (集成)
# ---------------------------------------------------------------------------


class TestRealCatalogReport:
    """验证仓库中的 catalog_report.json gap_count 守恒。"""

    @pytest.fixture
    def real_report(self) -> dict | None:
        report_path = Path(__file__).resolve().parent.parent.parent / "data" / "acnr" / "catalog_report.json"
        if not report_path.exists():
            pytest.skip("catalog_report.json not found")
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_real_gap_count_conservation(self, real_report):
        """真实 catalog_report.json 的 gap_count 应与明细一致。"""
        errors = check_gap_count_conservation(real_report)
        assert errors == [], f"gap_count 守恒失败: {errors}"
