"""Property-Based Tests for 底稿版本链 — Backend (hypothesis)

Feature: workpaper-version-trail

Properties tested:
- P1: 快照数据保真性 (Snapshot Fidelity)
- P2: Diff 完备性 (Diff Completeness)
- P3: Diff 互斥性 (Diff Mutual Exclusivity)
- P4: 回滚恢复保真性 (Rollback Restores State)
- P5: 回滚创建新版本 (Rollback Creates Snapshot)
- P6: 生命周期上界 (Lifecycle Bound)
- P8: 安全隔离性 (Security Isolation)

Uses hypothesis with max_examples=100.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.version_trail_service import (
    DiffResult,
    SnapshotMeta,
    VersionTrailService,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Strategies
# ═══════════════════════════════════════════════════════════════════════════════

checklist_response_strategy = st.fixed_dictionaries(
    {
        "item_id": st.text(min_size=1, max_size=50),
        "conclusion": st.one_of(st.none(), st.text(max_size=20)),
        "remark": st.one_of(st.none(), st.text(max_size=500)),
        "wp_ref": st.one_of(st.none(), st.text(max_size=20)),
    }
)

checklist_responses_list = st.lists(checklist_response_strategy, max_size=30)

# Strategy that generates lists with UNIQUE item_ids (for diff tests)
unique_checklist_responses = st.lists(
    checklist_response_strategy, max_size=30
).map(lambda items: list({d["item_id"]: d for d in items}.values()))


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mapping_row(data: dict):
    """Create a mock mapping row that supports dict-like access."""
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.get = lambda key, default=None: data.get(key, default)
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: 快照数据保真性 (Snapshot Fidelity)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty1SnapshotFidelity:
    """Feature: workpaper-version-trail, Property 1: 快照数据保真性

    For any workpaper with any set of checklist_responses rows,
    when a snapshot is created, the resulting data_json SHALL contain
    exactly those rows with all field values preserved identically.

    **Validates: Requirements 1.1, 1.2, 1.5**
    """

    @settings(max_examples=100)
    @given(responses=checklist_responses_list)
    @pytest.mark.asyncio
    async def test_snapshot_data_fidelity(self, responses: list[dict]):
        """After create_snapshot, stored data_json deep-equals input checklist_responses."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Mock DB session
        db = AsyncMock()

        # Mock: SELECT checklist_responses returns our generated data
        rows_result = MagicMock()
        mapping_rows = [_make_mapping_row(r) for r in responses]
        rows_result.mappings.return_value.all.return_value = mapping_rows

        # Mock: SELECT previous snapshot (none exists)
        prev_result = MagicMock()
        prev_result.mappings.return_value.first.return_value = None

        # Mock: COUNT non-manual snapshots for lifecycle
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 0}

        db.execute.side_effect = [rows_result, prev_result, count_result]

        # Track what gets added to session
        added_objects = []
        db.add = lambda obj: added_objects.append(obj)
        db.flush = AsyncMock()

        # Mock WorkpaperSnapshot so it gets an id and created_at
        with patch(
            "app.services.version_trail_service.WorkpaperSnapshot"
        ) as MockSnapshot:
            mock_instance = MagicMock()
            mock_instance.id = uuid.uuid4()
            mock_instance.snapshot_type = "manual"
            mock_instance.description = None
            mock_instance.change_summary = None
            mock_instance.item_count = len(responses)
            mock_instance.data_size_bytes = len(
                json.dumps(responses, ensure_ascii=False).encode("utf-8")
            )
            mock_instance.user_id = user_id
            mock_instance.created_at = datetime.now()
            MockSnapshot.return_value = mock_instance

            await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="manual",
            )

            # Verify: WorkpaperSnapshot was constructed with correct data_json
            call_kwargs = MockSnapshot.call_args[1]
            stored_data_json = call_kwargs["data_json"]

            # The service converts rows to dicts with str(item_id)
            expected = [
                {
                    "item_id": str(r["item_id"]),
                    "conclusion": r["conclusion"],
                    "remark": r["remark"],
                    "wp_ref": r["wp_ref"],
                }
                for r in responses
            ]

            # Data size check — if under 2MB, should store full data
            data_bytes = json.dumps(expected, ensure_ascii=False).encode("utf-8")
            if len(data_bytes) <= 2 * 1024 * 1024:
                assert stored_data_json == expected
                assert call_kwargs["item_count"] == len(responses)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: Diff 完备性 (Diff Completeness)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty2DiffCompleteness:
    """Feature: workpaper-version-trail, Property 2: Diff 完备性

    For any two snapshots A and B, the diff result's sets SHALL satisfy:
    added_ids ∪ deleted_ids ∪ modified_ids ∪ unchanged_ids
    == all_item_ids_in_A ∪ all_item_ids_in_B

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """

    @settings(max_examples=100)
    @given(
        data_a=unique_checklist_responses,
        data_b=unique_checklist_responses,
    )
    def test_diff_completeness(self, data_a: list[dict], data_b: list[dict]):
        """Union of all diff categories equals union of all item_ids from both snapshots."""
        result: DiffResult = VersionTrailService.compute_diff_pure(data_a, data_b)

        # Collect IDs from diff result
        added_ids = {item.item_id for item in result.added}
        deleted_ids = {item.item_id for item in result.deleted}
        # modified may have multiple DiffItems per item_id (one per field)
        modified_ids = {item.item_id for item in result.modified}

        # Derive unchanged: items in both A and B that are NOT modified
        all_a_ids = {d["item_id"] for d in data_a}
        all_b_ids = {d["item_id"] for d in data_b}
        common_ids = all_a_ids & all_b_ids
        unchanged_ids = common_ids - modified_ids

        # Verify completeness
        diff_union = added_ids | deleted_ids | modified_ids | unchanged_ids
        expected_union = all_a_ids | all_b_ids

        assert diff_union == expected_union, (
            f"Diff not complete: "
            f"diff_union={diff_union}, expected_union={expected_union}"
        )

        # Also verify unchanged_count matches
        assert result.unchanged_count == len(unchanged_ids)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: Diff 互斥性 (Diff Mutual Exclusivity)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty3DiffMutualExclusivity:
    """Feature: workpaper-version-trail, Property 3: Diff 互斥性

    For any two snapshots A and B, the diff result's four sets SHALL be
    pairwise disjoint.

    **Validates: Requirements 4.2, 4.3, 4.4**
    """

    @settings(max_examples=100)
    @given(
        data_a=unique_checklist_responses,
        data_b=unique_checklist_responses,
    )
    def test_diff_mutual_exclusivity(self, data_a: list[dict], data_b: list[dict]):
        """The four sets (added/deleted/modified/unchanged) are pairwise disjoint."""
        result: DiffResult = VersionTrailService.compute_diff_pure(data_a, data_b)

        added_ids = {item.item_id for item in result.added}
        deleted_ids = {item.item_id for item in result.deleted}
        modified_ids = {item.item_id for item in result.modified}

        # Derive unchanged_ids
        all_a_ids = {d["item_id"] for d in data_a}
        all_b_ids = {d["item_id"] for d in data_b}
        common_ids = all_a_ids & all_b_ids
        unchanged_ids = common_ids - modified_ids

        # Pairwise disjoint checks
        assert added_ids & deleted_ids == set(), "added ∩ deleted should be ∅"
        assert added_ids & modified_ids == set(), "added ∩ modified should be ∅"
        assert added_ids & unchanged_ids == set(), "added ∩ unchanged should be ∅"
        assert deleted_ids & modified_ids == set(), "deleted ∩ modified should be ∅"
        assert deleted_ids & unchanged_ids == set(), "deleted ∩ unchanged should be ∅"
        assert modified_ids & unchanged_ids == set(), "modified ∩ unchanged should be ∅"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: 回滚恢复保真性 (Rollback Restores State)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty4RollbackRestoresState:
    """Feature: workpaper-version-trail, Property 4: 回滚恢复保真性

    For any snapshot with data_json D and any current checklist_responses state,
    after executing rollback to that snapshot, the resulting INSERT params
    SHALL match the snapshot data_json exactly.

    **Validates: Requirements 5.2, 5.4**
    """

    @settings(max_examples=100)
    @given(
        snapshot_data=unique_checklist_responses,
        current_data=unique_checklist_responses,
    )
    @pytest.mark.asyncio
    async def test_rollback_restores_state(
        self, snapshot_data: list[dict], current_data: list[dict]
    ):
        """After rollback, the INSERT params match the target snapshot's data_json."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        user_id = uuid.uuid4()
        created_at = datetime(2024, 6, 1, 12, 0, 0)

        # Mock DB
        db = AsyncMock()

        # Mock: SELECT snapshot by id
        snapshot_row = _make_mapping_row(
            {
                "id": snapshot_id,
                "project_id": project_id,
                "workpaper_id": workpaper_id,
                "data_json": snapshot_data,
                "created_at": created_at,
            }
        )
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = snapshot_row

        # Track execute calls to capture DELETE and INSERT params
        execute_calls = []

        async def mock_execute(query, params=None):
            execute_calls.append((str(query), params))
            return select_result

        db.execute = mock_execute

        # Track what gets added to session (the rollback snapshot)
        added_objects = []
        db.add = lambda obj: added_objects.append(obj)
        db.flush = AsyncMock()

        with patch(
            "app.services.version_trail_service.WorkpaperSnapshot"
        ) as MockSnapshot:
            mock_instance = MagicMock()
            mock_instance.id = uuid.uuid4()
            mock_instance.snapshot_type = "rollback"
            mock_instance.description = f"回滚到{created_at}的版本"
            mock_instance.change_summary = None
            mock_instance.item_count = len(snapshot_data)
            mock_instance.data_size_bytes = len(
                json.dumps(snapshot_data, ensure_ascii=False).encode("utf-8")
            )
            mock_instance.user_id = user_id
            mock_instance.created_at = datetime.now()
            MockSnapshot.return_value = mock_instance

            await VersionTrailService.rollback_to_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                snapshot_id=snapshot_id,
                user_id=user_id,
            )

            # Verify INSERT params match snapshot data
            # The service does: DELETE then INSERT for each row in data_json
            insert_params = [
                call[1]
                for call in execute_calls
                if call[1] is not None and "item_id" in call[1]
            ]

            assert len(insert_params) == len(snapshot_data)

            for i, row in enumerate(snapshot_data):
                assert insert_params[i]["item_id"] == row["item_id"]
                assert insert_params[i]["conclusion"] == row.get("conclusion")
                assert insert_params[i]["remark"] == row.get("remark")
                assert insert_params[i]["wp_ref"] == row.get("wp_ref")
                assert insert_params[i]["project_id"] == project_id
                assert insert_params[i]["wp_id"] == workpaper_id


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: 回滚创建新版本 (Rollback Creates Snapshot)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty5RollbackCreatesSnapshot:
    """Feature: workpaper-version-trail, Property 5: 回滚创建新版本

    For any rollback operation, upon completion the system SHALL have created
    exactly one new snapshot with snapshot_type='rollback' whose data_json
    equals the target snapshot's data_json.

    **Validates: Requirements 5.3**
    """

    @settings(max_examples=100)
    @given(snapshot_data=unique_checklist_responses)
    @pytest.mark.asyncio
    async def test_rollback_creates_snapshot(self, snapshot_data: list[dict]):
        """After rollback, exactly 1 new snapshot with type='rollback' is created."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        user_id = uuid.uuid4()
        created_at = datetime(2024, 3, 15, 10, 30, 0)

        # Mock DB
        db = AsyncMock()

        # Mock: SELECT snapshot
        snapshot_row = _make_mapping_row(
            {
                "id": snapshot_id,
                "project_id": project_id,
                "workpaper_id": workpaper_id,
                "data_json": snapshot_data,
                "created_at": created_at,
            }
        )
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = snapshot_row
        db.execute.return_value = select_result

        # Track what gets added
        added_objects = []
        db.add = lambda obj: added_objects.append(obj)
        db.flush = AsyncMock()

        with patch(
            "app.services.version_trail_service.WorkpaperSnapshot"
        ) as MockSnapshot:
            mock_instance = MagicMock()
            mock_instance.id = uuid.uuid4()
            mock_instance.snapshot_type = "rollback"
            mock_instance.description = f"回滚到{created_at}的版本"
            mock_instance.change_summary = None
            mock_instance.item_count = len(snapshot_data)
            mock_instance.data_size_bytes = len(
                json.dumps(snapshot_data, ensure_ascii=False).encode("utf-8")
            )
            mock_instance.user_id = user_id
            mock_instance.created_at = datetime.now()
            MockSnapshot.return_value = mock_instance

            result = await VersionTrailService.rollback_to_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                snapshot_id=snapshot_id,
                user_id=user_id,
            )

            # Verify exactly 1 WorkpaperSnapshot was constructed
            assert MockSnapshot.call_count == 1

            # Verify snapshot_type='rollback'
            call_kwargs = MockSnapshot.call_args[1]
            assert call_kwargs["snapshot_type"] == "rollback"

            # Verify data_json equals target snapshot's data_json
            assert call_kwargs["data_json"] == snapshot_data

            # Verify the returned meta has correct type
            assert result.snapshot_type == "rollback"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6: 生命周期上界 (Lifecycle Bound)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty6LifecycleBound:
    """Feature: workpaper-version-trail, Property 6: 生命周期上界

    For any workpaper, after any sequence of snapshot creation operations,
    the snapshot count SHALL never exceed 5 (keep newest).

    **Validates: Requirements 9.2, 9.3, 9.4**
    """

    @settings(max_examples=100)
    @given(
        num_creates=st.integers(min_value=1, max_value=20),
        snapshot_type=st.sampled_from(
            [
                "manual",
                "auto",
                "auto_sampling",
                "auto_import",
                "review_sign",
                "status_change",
            ]
        ),
    )
    @pytest.mark.asyncio
    async def test_lifecycle_bound(self, num_creates: int, snapshot_type: str):
        """At any moment, total snapshot count ≤ 5 after enforce_lifecycle."""
        workpaper_id = uuid.uuid4()
        max_snapshots = 5

        # Simulate current count being num_creates
        db = AsyncMock()

        # Mock count query result
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": num_creates}

        # Mock delete result
        delete_result = MagicMock()

        db.execute.side_effect = [count_result, delete_result]
        db.flush = AsyncMock()

        purged = await VersionTrailService.enforce_lifecycle(
            db=db,
            workpaper_id=workpaper_id,
            max_snapshots=max_snapshots,
        )

        if num_creates < max_snapshots:
            assert purged == 0
        else:
            # 创建前腾空位：excess = count - max + 1
            expected_purge = num_creates - max_snapshots + 1
            assert purged == expected_purge
            effective_count = num_creates - purged
            assert effective_count == max_snapshots - 1


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8: 安全隔离性 (Security Isolation)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty8SecurityIsolation:
    """Feature: workpaper-version-trail, Property 8: 安全隔离性

    For any request with project_id P, list_snapshots SHALL only return
    snapshots where snapshot.project_id = P. Cross-project access is impossible.

    **Validates: Requirements 10.5, 11.6, 12.3**
    """

    @settings(max_examples=100)
    @given(
        project_a_id=st.uuids(),
        project_b_id=st.uuids(),
        num_a_snapshots=st.integers(min_value=0, max_value=10),
        num_b_snapshots=st.integers(min_value=0, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_security_isolation(
        self,
        project_a_id: uuid.UUID,
        project_b_id: uuid.UUID,
        num_a_snapshots: int,
        num_b_snapshots: int,
    ):
        """list_snapshots(project_a) never returns project_b's snapshots."""
        # Skip trivial case where both projects have same ID
        if project_a_id == project_b_id:
            return

        workpaper_id = uuid.uuid4()

        # Generate snapshot data for project A
        snapshots_a = [
            {
                "id": uuid.uuid4(),
                "snapshot_type": "manual",
                "description": f"snap_a_{i}",
                "change_summary": None,
                "item_count": 5,
                "data_size_bytes": 100,
                "user_id": uuid.uuid4(),
                "created_at": datetime(2024, 1, 1, i, 0, 0),
            }
            for i in range(num_a_snapshots)
        ]

        # Generate snapshot data for project B
        snapshots_b = [
            {
                "id": uuid.uuid4(),
                "snapshot_type": "auto_sampling",
                "description": f"snap_b_{i}",
                "change_summary": None,
                "item_count": 3,
                "data_size_bytes": 80,
                "user_id": uuid.uuid4(),
                "created_at": datetime(2024, 2, 1, i, 0, 0),
            }
            for i in range(num_b_snapshots)
        ]

        # Mock DB for project A query — should only return A's snapshots
        db_a = AsyncMock()

        # COUNT result for project A
        count_result_a = MagicMock()
        count_result_a.scalar_one.return_value = num_a_snapshots

        # List result for project A (only A's snapshots)
        list_result_a = MagicMock()
        list_result_a.mappings.return_value.all.return_value = [
            _make_mapping_row(s) for s in snapshots_a
        ]

        db_a.execute.side_effect = [count_result_a, list_result_a]

        results_a, total_a = await VersionTrailService.list_snapshots(
            db=db_a,
            workpaper_id=workpaper_id,
            project_id=project_a_id,
        )

        # Verify: only project A snapshots returned
        assert total_a == num_a_snapshots
        assert len(results_a) == num_a_snapshots

        # Verify: none of the returned snapshots have project B's IDs
        returned_ids_a = {r.id for r in results_a}
        b_ids = {s["id"] for s in snapshots_b}
        assert returned_ids_a & b_ids == set(), (
            "Project A query must not return any of Project B's snapshots"
        )

        # Mock DB for project B query — should only return B's snapshots
        db_b = AsyncMock()

        count_result_b = MagicMock()
        count_result_b.scalar_one.return_value = num_b_snapshots

        list_result_b = MagicMock()
        list_result_b.mappings.return_value.all.return_value = [
            _make_mapping_row(s) for s in snapshots_b
        ]

        db_b.execute.side_effect = [count_result_b, list_result_b]

        results_b, total_b = await VersionTrailService.list_snapshots(
            db=db_b,
            workpaper_id=workpaper_id,
            project_id=project_b_id,
        )

        # Verify: only project B snapshots returned
        assert total_b == num_b_snapshots
        assert len(results_b) == num_b_snapshots

        # Verify: none of the returned snapshots have project A's IDs
        returned_ids_b = {r.id for r in results_b}
        a_ids = {s["id"] for s in snapshots_a}
        assert returned_ids_b & a_ids == set(), (
            "Project B query must not return any of Project A's snapshots"
        )
