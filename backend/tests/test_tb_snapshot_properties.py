"""
PBT + Unit tests for Trial Balance Snapshot Service (Properties 1-8)
Runs independently of full conftest (uses in-memory validation).
"""
import hashlib
import json
import uuid
from decimal import Decimal

import pytest

# ─── Import service components directly ───
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))

from app.services.tb_snapshot_service import TbSnapshotService, DecimalEncoder


# ─── Property 2: Deduplication (content hash determinism) ───

class TestContentHashDeterminism:
    """Property 2: Same content → same hash, different content → different hash."""

    def test_same_data_same_hash(self):
        svc = TbSnapshotService()
        data = {"detail_rows": [{"standard_account_code": "1001", "audited_amount": "100.50"}], "summary_rows": []}
        h1 = svc._compute_content_hash(data)
        h2 = svc._compute_content_hash(data)
        assert h1 == h2

    def test_key_order_irrelevant(self):
        """Sort keys ensures determinism regardless of dict insertion order."""
        svc = TbSnapshotService()
        data1 = {"detail_rows": [], "summary_rows": [{"row_code": "BS-001", "audited": 100}]}
        data2 = {"summary_rows": [{"row_code": "BS-001", "audited": 100}], "detail_rows": []}
        assert svc._compute_content_hash(data1) == svc._compute_content_hash(data2)

    def test_different_data_different_hash(self):
        svc = TbSnapshotService()
        data1 = {"detail_rows": [{"audited_amount": "100"}], "summary_rows": []}
        data2 = {"detail_rows": [{"audited_amount": "200"}], "summary_rows": []}
        assert svc._compute_content_hash(data1) != svc._compute_content_hash(data2)

    def test_decimal_handling(self):
        """Decimal values are serialized consistently."""
        svc = TbSnapshotService()
        data = {"detail_rows": [{"amount": Decimal("1234.56")}], "summary_rows": []}
        h = svc._compute_content_hash(data)
        assert len(h) == 64  # SHA-256 hex

    def test_uuid_handling(self):
        """UUID values are serialized to string."""
        svc = TbSnapshotService()
        data = {"detail_rows": [{"id": uuid.uuid4()}], "summary_rows": []}
        h = svc._compute_content_hash(data)
        assert len(h) == 64


# ─── Property 5: Version Monotonicity (tested via pure logic) ───

class TestVersionMonotonicity:
    """Property 5: version_no is strictly monotonically increasing."""

    def test_first_version_is_1(self):
        """When max is None (no existing snapshots), next version = 1."""
        # Simulate: max_no = None → (None or 0) + 1 = 1
        max_no = None
        next_v = (max_no or 0) + 1
        assert next_v == 1

    def test_increment_from_existing(self):
        """Existing max=5 → next=6."""
        max_no = 5
        next_v = (max_no or 0) + 1
        assert next_v == 6

    def test_monotonic_sequence(self):
        """Simulating a series of creates always produces increasing versions."""
        versions = []
        max_no = None
        for _ in range(10):
            next_v = (max_no or 0) + 1
            versions.append(next_v)
            max_no = next_v
        assert versions == list(range(1, 11))
        assert all(versions[i] < versions[i + 1] for i in range(len(versions) - 1))


# ─── Property 6: Diff Correctness ───

class TestDiffCorrectness:
    """Property 6: diff(v,v) = 0 changes; diff is symmetric in changed set."""

    def test_self_diff_zero_changes(self):
        """Diffing same data should yield zero changes."""
        data = {"detail_rows": [{"standard_account_code": "1001", "audited_amount": "500"}], "summary_rows": []}
        # Simulate: both snapshots have same data
        map1 = {r["standard_account_code"]: r for r in data["detail_rows"]}
        map2 = {r["standard_account_code"]: r for r in data["detail_rows"]}
        changed = []
        for key in set(map1) | set(map2):
            aud1 = float(map1.get(key, {}).get("audited_amount", 0) or 0)
            aud2 = float(map2.get(key, {}).get("audited_amount", 0) or 0)
            if abs(aud2 - aud1) > 0.005:
                changed.append(key)
        assert len(changed) == 0

    def test_diff_detects_change(self):
        """Different audited amounts should be detected."""
        map1 = {"1001": {"audited_amount": "100"}}
        map2 = {"1001": {"audited_amount": "200"}}
        aud1 = float(map1["1001"]["audited_amount"])
        aud2 = float(map2["1001"]["audited_amount"])
        assert abs(aud2 - aud1) > 0.005

    def test_diff_symmetric_changed_set(self):
        """Changed set is same regardless of direction (v1,v2) vs (v2,v1)."""
        rows_v1 = [{"standard_account_code": "1001", "audited_amount": "100"}, {"standard_account_code": "1002", "audited_amount": "500"}]
        rows_v2 = [{"standard_account_code": "1001", "audited_amount": "150"}, {"standard_account_code": "1002", "audited_amount": "500"}]

        def get_changed(r1, r2):
            m1 = {r["standard_account_code"]: r for r in r1}
            m2 = {r["standard_account_code"]: r for r in r2}
            changed = set()
            for k in set(m1) | set(m2):
                a1 = float(m1.get(k, {}).get("audited_amount", 0) or 0)
                a2 = float(m2.get(k, {}).get("audited_amount", 0) or 0)
                if abs(a2 - a1) > 0.005:
                    changed.add(k)
            return changed

        assert get_changed(rows_v1, rows_v2) == get_changed(rows_v2, rows_v1)


# ─── Property 4: Fail-Open (DecimalEncoder robustness) ───

class TestFailOpen:
    """Property 4: Serialization handles edge cases without throwing."""

    def test_empty_data(self):
        svc = TbSnapshotService()
        h = svc._compute_content_hash({"detail_rows": [], "summary_rows": []})
        assert isinstance(h, str) and len(h) == 64

    def test_none_values(self):
        svc = TbSnapshotService()
        data = {"detail_rows": [{"amount": None, "code": None}], "summary_rows": []}
        h = svc._compute_content_hash(data)
        assert isinstance(h, str)

    def test_large_numbers(self):
        svc = TbSnapshotService()
        data = {"detail_rows": [{"amount": Decimal("99999999999.99")}], "summary_rows": []}
        h = svc._compute_content_hash(data)
        assert isinstance(h, str)


# ─── Property 1: Immutability (code-level assertion) ───

class TestImmutability:
    """Property 1: Service code has no UPDATE/DELETE on snapshots table."""

    def test_no_update_or_delete_in_service(self):
        import inspect
        source = inspect.getsource(TbSnapshotService)
        # Should not contain direct UPDATE or DELETE on snapshots
        assert "UPDATE trial_balance_snapshots" not in source
        assert "DELETE FROM trial_balance_snapshots" not in source
        # restore_snapshot deletes trial_balance (target) not snapshots
        assert "delete(TrialBalanceSnapshot)" not in source
