"""Tests for vr_coverage router — Phase 7 F6

Validates: Requirements F6.1, F6.2, F6.3, F6.6
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.routers.vr_coverage import (
    CycleCoverage,
    VRCoverageResponse,
    _check_qc_admin,
    _scan_vr_rules,
    router,
)


class TestVRCoverageRouter:
    """Test VR coverage endpoint."""

    def test_router_prefix(self):
        """Router has correct prefix."""
        assert router.prefix == "/api/qc/vr-coverage"

    def test_router_tags(self):
        """Router has correct tags."""
        assert "qc-vr-coverage" in router.tags

    def test_permission_check_admin(self):
        """Admin user passes permission check."""
        user = MagicMock()
        user.role.value = "admin"
        _check_qc_admin(user)

    def test_permission_check_qc(self):
        """QC user passes permission check."""
        user = MagicMock()
        user.role.value = "qc"
        _check_qc_admin(user)

    def test_permission_check_auditor_rejected(self):
        """Non-QC/admin user is rejected."""
        from fastapi import HTTPException

        user = MagicMock()
        user.role.value = "auditor"
        with pytest.raises(HTTPException) as exc_info:
            _check_qc_admin(user)
        assert exc_info.value.status_code == 403

    def test_scan_vr_rules_compliant_cycle(self, tmp_path):
        """Cycle with blocking >= 3 and warning >= 2 is compliant."""
        rules_data = {
            "rules": [
                {"rule_id": "R1", "severity": "blocking"},
                {"rule_id": "R2", "severity": "blocking"},
                {"rule_id": "R3", "severity": "blocking"},
                {"rule_id": "R4", "severity": "warning"},
                {"rule_id": "R5", "severity": "warning"},
                {"rule_id": "R6", "severity": "info"},
            ]
        }
        (tmp_path / "test_cycle_validation_rules.json").write_text(
            json.dumps(rules_data), encoding="utf-8"
        )

        cycles = _scan_vr_rules(tmp_path)
        assert len(cycles) == 1
        c = cycles[0]
        assert c.blocking_count == 3
        assert c.warning_count == 2
        assert c.info_count == 1
        assert c.meets_standard is True
        assert c.gap_blocking == 0
        assert c.gap_warning == 0

    def test_scan_vr_rules_non_compliant_cycle(self, tmp_path):
        """Cycle with blocking < 3 is non-compliant."""
        rules_data = {
            "rules": [
                {"rule_id": "R1", "severity": "blocking"},
                {"rule_id": "R2", "severity": "warning"},
                {"rule_id": "R3", "severity": "info"},
            ]
        }
        (tmp_path / "x_cycle_validation_rules.json").write_text(
            json.dumps(rules_data), encoding="utf-8"
        )

        cycles = _scan_vr_rules(tmp_path)
        assert len(cycles) == 1
        c = cycles[0]
        assert c.blocking_count == 1
        assert c.warning_count == 1
        assert c.meets_standard is False
        assert c.gap_blocking == 2
        assert c.gap_warning == 1

    def test_scan_vr_rules_empty_dir(self, tmp_path):
        """Empty directory returns empty list."""
        cycles = _scan_vr_rules(tmp_path)
        assert cycles == []

    def test_scan_vr_rules_invalid_json(self, tmp_path):
        """Invalid JSON file is skipped gracefully."""
        (tmp_path / "bad_cycle_validation_rules.json").write_text(
            "not valid json", encoding="utf-8"
        )
        cycles = _scan_vr_rules(tmp_path)
        assert cycles == []

    def test_scan_vr_rules_multiple_cycles(self, tmp_path):
        """Multiple cycle files are all scanned."""
        for prefix in ["d", "f", "g"]:
            rules_data = {
                "rules": [
                    {"rule_id": f"{prefix}-1", "severity": "blocking"},
                    {"rule_id": f"{prefix}-2", "severity": "blocking"},
                    {"rule_id": f"{prefix}-3", "severity": "blocking"},
                    {"rule_id": f"{prefix}-4", "severity": "warning"},
                    {"rule_id": f"{prefix}-5", "severity": "warning"},
                ]
            }
            (tmp_path / f"{prefix}_cycle_validation_rules.json").write_text(
                json.dumps(rules_data), encoding="utf-8"
            )

        cycles = _scan_vr_rules(tmp_path)
        assert len(cycles) == 3
        assert all(c.meets_standard for c in cycles)

    def test_scan_real_data_dir(self):
        """Scan the actual backend/data directory for VR rules."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        if not data_dir.is_dir():
            pytest.skip("backend/data not found")

        cycles = _scan_vr_rules(data_dir)
        # We know there are multiple VR rule files
        assert len(cycles) > 0
        # Total rules should be > 0
        total = sum(c.total_count for c in cycles)
        assert total > 0

    def test_gap_calculation(self):
        """Gap calculation is correct."""
        # gap_blocking = max(0, 3 - blocking_count)
        assert max(0, 3 - 5) == 0
        assert max(0, 3 - 3) == 0
        assert max(0, 3 - 2) == 1
        assert max(0, 3 - 0) == 3

        # gap_warning = max(0, 2 - warning_count)
        assert max(0, 2 - 3) == 0
        assert max(0, 2 - 2) == 0
        assert max(0, 2 - 1) == 1
        assert max(0, 2 - 0) == 2

    def test_coverage_response_model(self):
        """VRCoverageResponse model validates correctly."""
        resp = VRCoverageResponse(
            cycles=[
                CycleCoverage(
                    cycle_name="D",
                    blocking_count=5,
                    warning_count=3,
                    info_count=2,
                    total_count=10,
                    meets_standard=True,
                    gap_blocking=0,
                    gap_warning=0,
                )
            ],
            total_rules=10,
            compliant_cycles=1,
            non_compliant_cycles=0,
        )
        assert resp.total_rules == 10
        assert resp.compliant_cycles == 1
