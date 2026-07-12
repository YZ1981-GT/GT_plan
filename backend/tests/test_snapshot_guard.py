"""SnapshotGuard 单元测试。

验证：
1. snapshot() 逐个调用 VersionTrailService.create_snapshot 并记录
2. rollback() 逐个调用 VersionTrailService.rollback_to_snapshot
3. rollback_single() 单个回滚
4. 单个快照创建失败不阻断其余（fire-and-forget）
5. 单个回滚失败不阻断其余
6. AtomicityMode 枚举值正确
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.bulk_tab.snapshot_guard import (
    AtomicityMode,
    SnapshotGuard,
    SnapshotRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _make_snapshot_meta(snapshot_id: uuid.UUID | None = None):
    """生成模拟的 SnapshotMeta 返回值。"""
    from datetime import datetime, timezone
    from app.services.version_trail_service import SnapshotMeta

    return SnapshotMeta(
        id=snapshot_id or _make_uuid(),
        snapshot_type="auto_import",
        description="批量导入前自动快照",
        change_summary=None,
        item_count=5,
        data_size_bytes=200,
        user_id=_make_uuid(),
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests — snapshot()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_creates_for_each_wp_id():
    """snapshot() 为每个 wp_id 创建快照并返回 SnapshotRecord 列表。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    wp_ids = [_make_uuid(), _make_uuid(), _make_uuid()]

    # 为每个 wp_id 生成对应的 snapshot_id
    snapshot_ids = [_make_uuid() for _ in wp_ids]
    metas = [_make_snapshot_meta(sid) for sid in snapshot_ids]

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.create_snapshot",
        new_callable=AsyncMock,
        side_effect=metas,
    ) as mock_create:
        records = await SnapshotGuard.snapshot(
            mock_db, wp_ids, project_id=project_id, user_id=user_id
        )

    assert len(records) == 3
    for i, record in enumerate(records):
        assert isinstance(record, SnapshotRecord)
        assert record.wp_id == wp_ids[i]
        assert record.snapshot_id == snapshot_ids[i]

    # 验证 create_snapshot 被调用了 3 次
    assert mock_create.call_count == 3
    # 验证参数正确
    for i, call in enumerate(mock_create.call_args_list):
        assert call.kwargs["workpaper_id"] == wp_ids[i]
        assert call.kwargs["project_id"] == project_id
        assert call.kwargs["user_id"] == user_id
        assert call.kwargs["snapshot_type"] == "auto_import"


@pytest.mark.asyncio
async def test_snapshot_custom_description():
    """snapshot() 使用自定义描述。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    wp_ids = [_make_uuid()]
    meta = _make_snapshot_meta()

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.create_snapshot",
        new_callable=AsyncMock,
        return_value=meta,
    ) as mock_create:
        await SnapshotGuard.snapshot(
            mock_db,
            wp_ids,
            project_id=project_id,
            user_id=user_id,
            description="custom pre-import",
        )

    assert mock_create.call_args.kwargs["description"] == "custom pre-import"


@pytest.mark.asyncio
async def test_snapshot_fire_and_forget_on_failure():
    """snapshot() 单个失败不阻断其余，返回成功列表。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    wp_ids = [_make_uuid(), _make_uuid(), _make_uuid()]

    meta_ok_1 = _make_snapshot_meta()
    meta_ok_2 = _make_snapshot_meta()

    # 第二个快照抛异常
    side_effects = [meta_ok_1, RuntimeError("DB error"), meta_ok_2]

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.create_snapshot",
        new_callable=AsyncMock,
        side_effect=side_effects,
    ):
        records = await SnapshotGuard.snapshot(
            mock_db, wp_ids, project_id=project_id, user_id=user_id
        )

    # 只有 2 个成功
    assert len(records) == 2
    assert records[0].wp_id == wp_ids[0]
    assert records[1].wp_id == wp_ids[2]


@pytest.mark.asyncio
async def test_snapshot_empty_wp_ids():
    """snapshot() 空列表返回空结果。"""
    mock_db = AsyncMock()

    records = await SnapshotGuard.snapshot(
        mock_db, [], project_id=_make_uuid(), user_id=_make_uuid()
    )

    assert records == []


# ---------------------------------------------------------------------------
# Tests — rollback()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_calls_rollback_for_each_snapshot():
    """rollback() 逐个调用 rollback_to_snapshot。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    snapshots = [
        SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid()),
        SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid()),
    ]

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.rollback_to_snapshot",
        new_callable=AsyncMock,
    ) as mock_rollback:
        await SnapshotGuard.rollback(
            mock_db, snapshots, project_id=project_id, user_id=user_id
        )

    assert mock_rollback.call_count == 2
    for i, call in enumerate(mock_rollback.call_args_list):
        assert call.kwargs["workpaper_id"] == snapshots[i].wp_id
        assert call.kwargs["snapshot_id"] == snapshots[i].snapshot_id
        assert call.kwargs["project_id"] == project_id
        assert call.kwargs["user_id"] == user_id


@pytest.mark.asyncio
async def test_rollback_single_failure_does_not_block_others():
    """rollback() 单个回滚失败不阻断其余。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    snapshots = [
        SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid()),
        SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid()),
        SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid()),
    ]

    call_count = {"value": 0}

    async def side_effect(**kwargs):
        call_count["value"] += 1
        if call_count["value"] == 2:
            raise RuntimeError("rollback failed")

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.rollback_to_snapshot",
        new_callable=AsyncMock,
        side_effect=side_effect,
    ) as mock_rollback:
        # 不应该抛异常
        await SnapshotGuard.rollback(
            mock_db, snapshots, project_id=project_id, user_id=user_id
        )

    # 全部 3 个都被调用了（即使第 2 个失败）
    assert mock_rollback.call_count == 3


@pytest.mark.asyncio
async def test_rollback_empty_snapshots():
    """rollback() 空快照列表不做任何操作。"""
    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.rollback_to_snapshot",
        new_callable=AsyncMock,
    ) as mock_rollback:
        await SnapshotGuard.rollback(
            mock_db, [], project_id=_make_uuid(), user_id=_make_uuid()
        )

    mock_rollback.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — rollback_single()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_single_calls_version_trail():
    """rollback_single() 正确调用 VersionTrailService.rollback_to_snapshot。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    snapshot = SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid())

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.rollback_to_snapshot",
        new_callable=AsyncMock,
    ) as mock_rollback:
        await SnapshotGuard.rollback_single(
            mock_db, snapshot, project_id=project_id, user_id=user_id
        )

    mock_rollback.assert_called_once_with(
        db=mock_db,
        project_id=project_id,
        workpaper_id=snapshot.wp_id,
        snapshot_id=snapshot.snapshot_id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_rollback_single_logs_error_on_failure():
    """rollback_single() 失败时 log error 但不抛异常。"""
    project_id = _make_uuid()
    user_id = _make_uuid()
    snapshot = SnapshotRecord(wp_id=_make_uuid(), snapshot_id=_make_uuid())

    mock_db = AsyncMock()

    with patch(
        "app.services.bulk_tab.snapshot_guard.VersionTrailService.rollback_to_snapshot",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB connection lost"),
    ):
        # 不应该抛异常
        await SnapshotGuard.rollback_single(
            mock_db, snapshot, project_id=project_id, user_id=user_id
        )


# ---------------------------------------------------------------------------
# Tests — AtomicityMode enum
# ---------------------------------------------------------------------------


def test_atomicity_mode_values():
    """AtomicityMode 枚举包含 per-sheet 和 all-or-nothing。"""
    assert AtomicityMode.PER_SHEET == "per-sheet"
    assert AtomicityMode.ALL_OR_NOTHING == "all-or-nothing"
    assert AtomicityMode.PER_SHEET.value == "per-sheet"
    assert AtomicityMode.ALL_OR_NOTHING.value == "all-or-nothing"


def test_atomicity_mode_is_string():
    """AtomicityMode 继承 str，可直接做字符串比较。"""
    assert AtomicityMode.PER_SHEET == "per-sheet"
    assert "all-or-nothing" == AtomicityMode.ALL_OR_NOTHING


# ---------------------------------------------------------------------------
# Tests — SnapshotRecord
# ---------------------------------------------------------------------------


def test_snapshot_record_fields():
    """SnapshotRecord 数据类包含 wp_id 和 snapshot_id。"""
    wp_id = _make_uuid()
    snapshot_id = _make_uuid()
    record = SnapshotRecord(wp_id=wp_id, snapshot_id=snapshot_id)

    assert record.wp_id == wp_id
    assert record.snapshot_id == snapshot_id
