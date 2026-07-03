"""后端集成测试 — 底稿版本链

覆盖场景：
1. 完整流程：创建手动快照 → 列表 → 详情 → 修改数据 → 再创建快照 → diff → 回滚 → 验证恢复
2. 安全隔离：项目A快照不可被项目B访问
3. 生命周期：创建51个auto快照验证purge
4. 回滚权限：审计助理调用返回403
5. 自动快照失败不阻塞：mock DB异常
6. 空底稿快照：checklist_responses=0条时正常创建
7. 2MB降级：构造大数据验证降级存储格式

Requirements: 1.1, 2.5, 5.2, 5.6, 9.2, 9.5, 10.3, 10.5
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.version_trail_service import (
    SnapshotDetail,
    SnapshotMeta,
    VersionTrailService,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mapping_row(data: dict):
    """Create a mock mapping row that supports dict-like access."""
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.get = lambda key, default=None: data.get(key, default)
    return m


def _make_user(role: str = "manager"):
    """Create a mock User object with a given role."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = MagicMock()
    user.role.value = role
    return user


def _sample_responses(count: int = 3) -> list[dict]:
    """Generate sample checklist_responses rows."""
    return [
        {
            "item_id": f"D2-item-{i}",
            "conclusion": "Y" if i % 2 == 0 else None,
            "remark": f"备注{i}" if i % 3 == 0 else None,
            "wp_ref": f"D2-{i}" if i % 2 == 0 else None,
        }
        for i in range(count)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 场景1: 完整流程集成测试
# 创建手动快照 → 列表 → 详情 → 修改数据 → 再创建快照 → diff → 回滚 → 验证恢复
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullFlowIntegration:
    """完整流程：create → list → detail → create again → diff → rollback → verify."""

    @pytest.mark.asyncio
    async def test_full_flow(self):
        """Validates: Requirements 1.1, 5.2"""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        user_id = uuid.uuid4()
        snapshot1_id = uuid.uuid4()
        snapshot2_id = uuid.uuid4()

        responses_v1 = _sample_responses(3)
        responses_v2 = [
            {"item_id": "D2-item-0", "conclusion": "N", "remark": "已更新", "wp_ref": "D2-0"},
            {"item_id": "D2-item-1", "conclusion": "Y", "remark": None, "wp_ref": None},
            {"item_id": "D2-item-2", "conclusion": "Y", "remark": None, "wp_ref": "D2-2"},
            {"item_id": "D2-item-3", "conclusion": "N/A", "remark": "新增项", "wp_ref": None},
        ]

        # ─── Step 1: Create first snapshot ────────────────────────────────
        db = AsyncMock()
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            _make_mapping_row(r) for r in responses_v1
        ]
        prev_result = MagicMock()
        prev_result.mappings.return_value.first.return_value = None
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 0}
        db.execute.side_effect = [rows_result, prev_result, count_result]
        db.flush = AsyncMock()

        created_at_1 = datetime(2024, 6, 1, 10, 0, 0)
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap:
            mock_inst = MagicMock()
            mock_inst.id = snapshot1_id
            mock_inst.snapshot_type = "manual"
            mock_inst.description = "初始版本"
            mock_inst.change_summary = None
            mock_inst.item_count = 3
            mock_inst.data_size_bytes = len(json.dumps(responses_v1).encode())
            mock_inst.user_id = user_id
            mock_inst.created_at = created_at_1
            MockSnap.return_value = mock_inst

            result1 = await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="manual",
                description="初始版本",
            )

        assert result1.id == snapshot1_id
        assert result1.snapshot_type == "manual"
        assert result1.item_count == 3

        # ─── Step 2: List snapshots ───────────────────────────────────────
        db2 = AsyncMock()
        count_list_result = MagicMock()
        count_list_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.mappings.return_value.all.return_value = [
            _make_mapping_row({
                "id": snapshot1_id,
                "snapshot_type": "manual",
                "description": "初始版本",
                "change_summary": None,
                "item_count": 3,
                "data_size_bytes": 200,
                "user_id": user_id,
                "created_at": created_at_1,
            })
        ]
        db2.execute.side_effect = [count_list_result, list_result]

        items, total = await VersionTrailService.list_snapshots(
            db=db2, workpaper_id=workpaper_id, project_id=project_id
        )
        assert total == 1
        assert len(items) == 1
        assert items[0].id == snapshot1_id

        # ─── Step 3: Get detail ───────────────────────────────────────────
        db3 = AsyncMock()
        detail_result = MagicMock()
        detail_result.mappings.return_value.first.return_value = _make_mapping_row({
            "id": snapshot1_id,
            "snapshot_type": "manual",
            "description": "初始版本",
            "change_summary": None,
            "item_count": 3,
            "data_size_bytes": 200,
            "data_json": responses_v1,
            "user_id": user_id,
            "created_at": created_at_1,
        })
        db3.execute.return_value = detail_result

        detail = await VersionTrailService.get_snapshot_detail(
            db=db3, snapshot_id=snapshot1_id, project_id=project_id
        )
        assert detail.id == snapshot1_id
        assert detail.data_json == responses_v1
        assert detail.item_count == 3

        # ─── Step 4: Create second snapshot (after data modification) ─────
        db4 = AsyncMock()
        rows_result2 = MagicMock()
        rows_result2.mappings.return_value.all.return_value = [
            _make_mapping_row(r) for r in responses_v2
        ]
        prev_result2 = MagicMock()
        prev_result2.mappings.return_value.first.return_value = _make_mapping_row({
            "data_json": responses_v1,
        })
        count_result2 = MagicMock()
        count_result2.mappings.return_value.first.return_value = {"cnt": 1}
        db4.execute.side_effect = [rows_result2, prev_result2, count_result2]
        db4.flush = AsyncMock()

        created_at_2 = datetime(2024, 6, 1, 11, 0, 0)
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap2:
            mock_inst2 = MagicMock()
            mock_inst2.id = snapshot2_id
            mock_inst2.snapshot_type = "manual"
            mock_inst2.description = "修改后版本"
            mock_inst2.change_summary = "修改2个字段，新增1项"
            mock_inst2.item_count = 4
            mock_inst2.data_size_bytes = len(json.dumps(responses_v2).encode())
            mock_inst2.user_id = user_id
            mock_inst2.created_at = created_at_2
            MockSnap2.return_value = mock_inst2

            result2 = await VersionTrailService.create_snapshot(
                db=db4,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="manual",
                description="修改后版本",
            )

        assert result2.id == snapshot2_id
        assert result2.item_count == 4

        # ─── Step 5: Diff between v1 and v2 ──────────────────────────────
        diff_result = VersionTrailService.compute_diff_pure(responses_v1, responses_v2)
        assert len(diff_result.added) == 1  # D2-item-3
        assert diff_result.added[0].item_id == "D2-item-3"
        assert len(diff_result.modified) > 0  # D2-item-0 conclusion Y→N, remark changed
        assert diff_result.unchanged_count >= 0

        # ─── Step 6: Rollback to v1 ──────────────────────────────────────
        db5 = AsyncMock()
        snap_row = _make_mapping_row({
            "id": snapshot1_id,
            "project_id": project_id,
            "workpaper_id": workpaper_id,
            "data_json": responses_v1,
            "created_at": created_at_1,
        })
        snap_select_result = MagicMock()
        snap_select_result.mappings.return_value.first.return_value = snap_row
        db5.execute.return_value = snap_select_result
        db5.flush = AsyncMock()

        rollback_id = uuid.uuid4()
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap3:
            mock_rb = MagicMock()
            mock_rb.id = rollback_id
            mock_rb.snapshot_type = "rollback"
            mock_rb.description = f"回滚到{created_at_1}的版本"
            mock_rb.change_summary = None
            mock_rb.item_count = 3
            mock_rb.data_size_bytes = len(json.dumps(responses_v1).encode())
            mock_rb.user_id = user_id
            mock_rb.created_at = datetime.now()
            MockSnap3.return_value = mock_rb

            rollback_result = await VersionTrailService.rollback_to_snapshot(
                db=db5,
                project_id=project_id,
                workpaper_id=workpaper_id,
                snapshot_id=snapshot1_id,
                user_id=user_id,
            )

        assert rollback_result.snapshot_type == "rollback"
        assert rollback_result.item_count == 3
        # Verify rollback snapshot stores same data as v1
        rollback_call_kwargs = MockSnap3.call_args[1]
        assert rollback_call_kwargs["data_json"] == responses_v1


# ═══════════════════════════════════════════════════════════════════════════════
# 场景2: 安全隔离 — 项目A快照不可被项目B访问
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityIsolation:
    """项目A的快照不可通过项目B的project_id访问。

    Validates: Requirements 10.5
    """

    @pytest.mark.asyncio
    async def test_project_isolation_get_detail(self):
        """get_snapshot_detail with wrong project_id returns 404."""
        project_a = uuid.uuid4()
        project_b = uuid.uuid4()
        snapshot_id = uuid.uuid4()

        # Mock DB: the query with project_b returns None (snapshot belongs to project_a)
        db = AsyncMock()
        empty_result = MagicMock()
        empty_result.mappings.return_value.first.return_value = None
        db.execute.return_value = empty_result

        with pytest.raises(HTTPException) as exc_info:
            await VersionTrailService.get_snapshot_detail(
                db=db, snapshot_id=snapshot_id, project_id=project_b
            )
        assert exc_info.value.status_code == 404
        assert "版本快照不存在" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_project_isolation_list(self):
        """list_snapshots for project_a only returns project_a's data."""
        project_a = uuid.uuid4()
        workpaper_id = uuid.uuid4()

        # DB returns 0 snapshots for project_a (all belong to project_b)
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.mappings.return_value.all.return_value = []
        db.execute.side_effect = [count_result, list_result]

        items, total = await VersionTrailService.list_snapshots(
            db=db, workpaper_id=workpaper_id, project_id=project_a
        )
        assert total == 0
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_rollback_wrong_project_returns_403(self):
        """Rollback with snapshot belonging to another project returns 403."""
        project_a = uuid.uuid4()
        project_b = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        user_id = uuid.uuid4()

        db = AsyncMock()
        # Snapshot exists but belongs to project_b
        snap_row = _make_mapping_row({
            "id": snapshot_id,
            "project_id": project_b,
            "workpaper_id": workpaper_id,
            "data_json": [{"item_id": "x", "conclusion": "Y", "remark": None, "wp_ref": None}],
            "created_at": datetime(2024, 1, 1),
        })
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = snap_row
        db.execute.return_value = select_result

        with pytest.raises(HTTPException) as exc_info:
            await VersionTrailService.rollback_to_snapshot(
                db=db,
                project_id=project_a,
                workpaper_id=workpaper_id,
                snapshot_id=snapshot_id,
                user_id=user_id,
            )
        assert exc_info.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 场景3: 生命周期 — 创建51个auto快照验证purge
# ═══════════════════════════════════════════════════════════════════════════════


class TestLifecyclePurge:
    """当auto快照超过50个时，enforce_lifecycle应删除最老的auto快照。

    Validates: Requirements 9.2
    """

    @pytest.mark.asyncio
    async def test_purge_when_exceeding_50(self):
        """51 non-manual snapshots → purge 1 oldest."""
        workpaper_id = uuid.uuid4()
        db = AsyncMock()

        # count returns 51
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 51}
        delete_result = MagicMock()
        db.execute.side_effect = [count_result, delete_result]
        db.flush = AsyncMock()

        purged = await VersionTrailService.enforce_lifecycle(
            db=db, workpaper_id=workpaper_id, max_snapshots=50
        )
        assert purged == 1

    @pytest.mark.asyncio
    async def test_no_purge_when_under_limit(self):
        """49 non-manual snapshots → no purge."""
        workpaper_id = uuid.uuid4()
        db = AsyncMock()

        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 49}
        db.execute.side_effect = [count_result]

        purged = await VersionTrailService.enforce_lifecycle(
            db=db, workpaper_id=workpaper_id, max_snapshots=50
        )
        assert purged == 0

    @pytest.mark.asyncio
    async def test_purge_preserves_manual_snapshots(self):
        """enforce_lifecycle counts only non-manual snapshots for purge."""
        workpaper_id = uuid.uuid4()
        db = AsyncMock()

        # The count query only counts WHERE snapshot_type != 'manual'
        # So 60 non-manual → purge 10
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 60}
        delete_result = MagicMock()
        db.execute.side_effect = [count_result, delete_result]
        db.flush = AsyncMock()

        purged = await VersionTrailService.enforce_lifecycle(
            db=db, workpaper_id=workpaper_id, max_snapshots=50
        )
        assert purged == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 场景4: 回滚权限 — 审计助理调用返回403
# ═══════════════════════════════════════════════════════════════════════════════


class TestRollbackPermission:
    """审计助理(auditor)调用回滚端点应返回403。

    Validates: Requirements 5.6, 10.3
    """

    @pytest.mark.asyncio
    async def test_auditor_cannot_rollback(self):
        """Router-level permission check: auditor role → 403."""
        from app.routers.version_trail import _ROLLBACK_ALLOWED_ROLES, rollback_version

        user = _make_user(role="auditor")
        pid = uuid.uuid4()
        wp_id = uuid.uuid4()
        vid = uuid.uuid4()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await rollback_version(
                pid=pid,
                wp_id=wp_id,
                vid=vid,
                db=db,
                current_user=user,
            )
        assert exc_info.value.status_code == 403
        assert "仅现场经理及以上" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_can_rollback(self):
        """Manager role passes permission check (reaches service call)."""
        from app.routers.version_trail import rollback_version

        user = _make_user(role="manager")
        pid = uuid.uuid4()
        wp_id = uuid.uuid4()
        vid = uuid.uuid4()
        db = AsyncMock()

        # Mock the _validate call
        validate_row = MagicMock()
        validate_row.fetchone.return_value = MagicMock()  # workpaper exists

        # Mock the rollback service call
        snap_row = _make_mapping_row({
            "id": vid,
            "project_id": pid,
            "workpaper_id": wp_id,
            "data_json": [{"item_id": "x1", "conclusion": "Y", "remark": None, "wp_ref": None}],
            "created_at": datetime(2024, 3, 1),
        })
        snap_select = MagicMock()
        snap_select.mappings.return_value.first.return_value = snap_row
        snap_select.fetchone.return_value = MagicMock()

        db.execute.return_value = snap_select
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        rollback_id = uuid.uuid4()
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap:
            mock_rb = MagicMock()
            mock_rb.id = rollback_id
            mock_rb.snapshot_type = "rollback"
            mock_rb.description = "回滚到2024-03-01 00:00:00的版本"
            mock_rb.change_summary = None
            mock_rb.item_count = 1
            mock_rb.data_size_bytes = 80
            mock_rb.user_id = user.id
            mock_rb.created_at = datetime.now()
            MockSnap.return_value = mock_rb

            result = await rollback_version(
                pid=pid,
                wp_id=wp_id,
                vid=vid,
                db=db,
                current_user=user,
            )

        assert result.snapshot_type == "rollback"

    @pytest.mark.asyncio
    async def test_readonly_cannot_rollback(self):
        """Readonly role → 403."""
        from app.routers.version_trail import rollback_version

        user = _make_user(role="readonly")
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await rollback_version(
                pid=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                vid=uuid.uuid4(),
                db=db,
                current_user=user,
            )
        assert exc_info.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 场景5: 自动快照失败不阻塞 — mock DB异常
# ═══════════════════════════════════════════════════════════════════════════════


class TestFireAndForgetResilience:
    """create_snapshot_fire_and_forget 中DB异常不应传播。

    Validates: Requirements 2.5, 9.5
    """

    @pytest.mark.asyncio
    async def test_db_exception_returns_none(self):
        """When create_snapshot raises, fire_and_forget returns None."""
        db = AsyncMock()
        db.execute.side_effect = Exception("DB connection lost")

        result = await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            snapshot_type="auto_sampling",
            description="抽凭前自动快照",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_db_exception_does_not_propagate(self):
        """No exception escapes from fire_and_forget."""
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("Connection pool exhausted")

        # Should NOT raise
        result = await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            snapshot_type="auto_import",
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 场景6: 空底稿快照 — checklist_responses=0条时正常创建
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyWorkpaperSnapshot:
    """空底稿（无checklist_responses）时应正常创建快照。

    Validates: Requirements 1.1
    """

    @pytest.mark.asyncio
    async def test_empty_responses_creates_snapshot(self):
        """Zero checklist_responses → snapshot with data_json=[], item_count=0."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        user_id = uuid.uuid4()

        db = AsyncMock()
        # SELECT checklist_responses returns empty
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = []
        # No previous snapshot
        prev_result = MagicMock()
        prev_result.mappings.return_value.first.return_value = None
        # Count: 0 non-manual
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 0}

        db.execute.side_effect = [rows_result, prev_result, count_result]
        db.flush = AsyncMock()

        snap_id = uuid.uuid4()
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap:
            mock_inst = MagicMock()
            mock_inst.id = snap_id
            mock_inst.snapshot_type = "manual"
            mock_inst.description = None
            mock_inst.change_summary = None
            mock_inst.item_count = 0
            mock_inst.data_size_bytes = 2  # len("[]".encode())
            mock_inst.user_id = user_id
            mock_inst.created_at = datetime.now()
            MockSnap.return_value = mock_inst

            result = await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="manual",
            )

            # Verify stored data_json is empty list
            call_kwargs = MockSnap.call_args[1]
            assert call_kwargs["data_json"] == []
            assert call_kwargs["item_count"] == 0

        assert result.item_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 场景7: 2MB降级 — 构造大数据验证降级存储格式
# ═══════════════════════════════════════════════════════════════════════════════


class TestTwoMBDegradation:
    """当data_json超过2MB时，应降级存储（仅item_id列表 + _degraded标记）。

    Validates: Requirements 9.5
    """

    @pytest.mark.asyncio
    async def test_large_data_triggers_degradation(self):
        """Data exceeding 2MB → stored as degraded dict with _degraded=True."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Generate enough rows to exceed 2MB
        # Each row with ~1200 bytes of remark text → ~1800 rows ≈ 2.1MB
        large_responses = [
            {
                "item_id": f"item-{i:05d}",
                "conclusion": "Y",
                "remark": "A" * 1200,  # 1200 chars per remark
                "wp_ref": f"ref-{i}",
            }
            for i in range(1800)
        ]

        db = AsyncMock()
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            _make_mapping_row(r) for r in large_responses
        ]
        # No previous snapshot
        prev_result = MagicMock()
        prev_result.mappings.return_value.first.return_value = None
        # Lifecycle count
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 0}

        db.execute.side_effect = [rows_result, prev_result, count_result]
        db.flush = AsyncMock()

        snap_id = uuid.uuid4()
        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap:
            mock_inst = MagicMock()
            mock_inst.id = snap_id
            mock_inst.snapshot_type = "auto_import"
            mock_inst.description = None
            mock_inst.change_summary = None
            mock_inst.item_count = 1800
            mock_inst.data_size_bytes = 2_200_000
            mock_inst.user_id = user_id
            mock_inst.created_at = datetime.now()
            MockSnap.return_value = mock_inst

            await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="auto_import",
            )

            # Verify the data_json was stored in degraded format
            call_kwargs = MockSnap.call_args[1]
            stored = call_kwargs["data_json"]

            assert isinstance(stored, dict)
            assert stored["_degraded"] is True
            assert stored["reason"] == "data_size_exceeds_2MB"
            assert stored["item_count"] == 1800
            assert len(stored["item_ids"]) == 1800
            # item_ids should be string item_id values
            assert stored["item_ids"][0] == "item-00000"
            assert stored["item_ids"][-1] == "item-01799"

    @pytest.mark.asyncio
    async def test_under_2mb_stores_full_data(self):
        """Data under 2MB → stored as full list."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Small dataset: well under 2MB
        small_responses = _sample_responses(5)

        db = AsyncMock()
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            _make_mapping_row(r) for r in small_responses
        ]
        prev_result = MagicMock()
        prev_result.mappings.return_value.first.return_value = None
        count_result = MagicMock()
        count_result.mappings.return_value.first.return_value = {"cnt": 0}
        db.execute.side_effect = [rows_result, prev_result, count_result]
        db.flush = AsyncMock()

        with patch("app.services.version_trail_service.WorkpaperSnapshot") as MockSnap:
            mock_inst = MagicMock()
            mock_inst.id = uuid.uuid4()
            mock_inst.snapshot_type = "manual"
            mock_inst.description = None
            mock_inst.change_summary = None
            mock_inst.item_count = 5
            mock_inst.data_size_bytes = 300
            mock_inst.user_id = user_id
            mock_inst.created_at = datetime.now()
            MockSnap.return_value = mock_inst

            await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type="manual",
            )

            call_kwargs = MockSnap.call_args[1]
            stored = call_kwargs["data_json"]
            assert isinstance(stored, list)
            assert len(stored) == 5

    @pytest.mark.asyncio
    async def test_degraded_snapshot_cannot_rollback(self):
        """Rollback to a degraded snapshot returns 400."""
        project_id = uuid.uuid4()
        workpaper_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        user_id = uuid.uuid4()

        degraded_data = {
            "_degraded": True,
            "item_ids": ["a", "b", "c"],
            "item_count": 3,
            "reason": "data_size_exceeds_2MB",
        }

        db = AsyncMock()
        snap_row = _make_mapping_row({
            "id": snapshot_id,
            "project_id": project_id,
            "workpaper_id": workpaper_id,
            "data_json": degraded_data,
            "created_at": datetime(2024, 1, 1),
        })
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = snap_row
        db.execute.return_value = select_result

        with pytest.raises(HTTPException) as exc_info:
            await VersionTrailService.rollback_to_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                snapshot_id=snapshot_id,
                user_id=user_id,
            )
        assert exc_info.value.status_code == 400
        assert "降级存储" in exc_info.value.detail
