"""单元测试：DeliverableSectionStateService.detect_stale_sections_layered

验证分层 stale 检测逻辑（D9）：
- tb_hash 未变 → 返回空列表（跳过逐章计算）
- tb_hash 变了 → 逐章节计算 hash，返回变更的 section_code 列表
- 无绑定快照 → 返回空列表
- 任务不存在 → 返回空列表
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.deliverable_section_state_service import (
    DeliverableSectionStateService,
)


@dataclass
class FakeSnapshotRef:
    """Minimal SnapshotRef stand-in for testing."""
    tb_hash: str


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def task_id():
    return uuid.uuid4()


@pytest.fixture
def year():
    return 2025


# Patch target: the source module where DeliverableSnapshotService is defined
_SNAP_SVC_PATCH = "app.services.deliverable_snapshot_service.DeliverableSnapshotService"


# ─── Test: tb_hash 未变时跳过逐章计算 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tb_hash_unchanged_returns_empty(project_id, task_id, year):
    """tb_hash 未变 → 整份未变，返回空列表，跳过逐章计算。"""
    mock_db = AsyncMock()

    # Mock: WordExportTask with bound tb_hash
    mock_task = MagicMock()
    mock_task.source_snapshot_refs = {"tb_hash": "abc123", "year": year}
    mock_task.doc_type = "disclosure_notes"
    mock_task.project_id = project_id

    # First execute: SELECT WordExportTask
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = mock_task

    mock_db.execute = AsyncMock(return_value=mock_task_result)

    svc = DeliverableSectionStateService(mock_db)

    # Mock DeliverableSnapshotService to return same tb_hash
    with patch(_SNAP_SVC_PATCH) as MockSnapSvc:
        mock_snap_instance = AsyncMock()
        mock_snap_instance.capture_snapshot_ref = AsyncMock(
            return_value=FakeSnapshotRef(tb_hash="abc123")
        )
        MockSnapSvc.return_value = mock_snap_instance

        result = await svc.detect_stale_sections_layered(
            word_export_task_id=task_id,
            project_id=project_id,
            year=year,
        )

    assert result == []
    # Should NOT query section states (only 1 DB call for the task)
    assert mock_db.execute.call_count == 1


# ─── Test: tb_hash 变了 → 返回变更章节 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tb_hash_changed_returns_stale_sections(project_id, task_id, year):
    """tb_hash 变了 → 逐章节比对，返回变更的 section_code。"""
    mock_db = AsyncMock()

    # Mock: WordExportTask with bound tb_hash
    mock_task = MagicMock()
    mock_task.source_snapshot_refs = {"tb_hash": "old_hash", "year": year}
    mock_task.doc_type = "disclosure_notes"
    mock_task.project_id = project_id

    # Mock section states in DB
    section_1 = MagicMock()
    section_1.section_code = "八、1"
    section_1.source_snapshot_hash = "hash_section_1_old"

    section_2 = MagicMock()
    section_2.section_code = "八、2"
    section_2.source_snapshot_hash = "hash_section_2_unchanged"

    section_3 = MagicMock()
    section_3.section_code = "八、3"
    section_3.source_snapshot_hash = "hash_section_3_old"

    # First call: SELECT WordExportTask
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = mock_task

    # Second call: SELECT DeliverableSectionState
    mock_sections_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [section_1, section_2, section_3]
    mock_sections_result.scalars.return_value = mock_scalars

    call_count = [0]
    results = [mock_task_result, mock_sections_result]

    async def side_effect_execute(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(results):
            return results[idx]
        # For compute_source_snapshot_hash internal queries
        # Return empty note result
        mock_empty = MagicMock()
        mock_empty.first.return_value = None
        mock_empty.all.return_value = []
        return mock_empty

    mock_db.execute = AsyncMock(side_effect=side_effect_execute)

    svc = DeliverableSectionStateService(mock_db)

    # Mock DeliverableSnapshotService to return new tb_hash
    with patch(_SNAP_SVC_PATCH) as MockSnapSvc:
        mock_snap_instance = AsyncMock()
        mock_snap_instance.capture_snapshot_ref = AsyncMock(
            return_value=FakeSnapshotRef(tb_hash="new_hash")
        )
        MockSnapSvc.return_value = mock_snap_instance

        # Mock compute_source_snapshot_hash to return specific hashes
        # section_1 changed, section_2 unchanged, section_3 changed
        hash_map = {
            "八、1": "hash_section_1_new",  # changed
            "八、2": "hash_section_2_unchanged",  # unchanged
            "八、3": "hash_section_3_new",  # changed
        }

        async def mock_compute(pid, yr, sc):
            return hash_map[sc]

        svc.compute_source_snapshot_hash = mock_compute  # type: ignore[method-assign]

        result = await svc.detect_stale_sections_layered(
            word_export_task_id=task_id,
            project_id=project_id,
            year=year,
        )

    assert sorted(result) == ["八、1", "八、3"]


# ─── Test: 任务不存在 → 返回空 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_not_found_returns_empty(project_id, task_id, year):
    """任务不存在 → 返回空列表。"""
    mock_db = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    svc = DeliverableSectionStateService(mock_db)

    result = await svc.detect_stale_sections_layered(
        word_export_task_id=task_id,
        project_id=project_id,
        year=year,
    )

    assert result == []


# ─── Test: 无绑定快照 → 返回空 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_bound_snapshot_returns_empty(project_id, task_id, year):
    """source_snapshot_refs 为空或无 tb_hash → 返回空列表。"""
    mock_db = AsyncMock()

    mock_task = MagicMock()
    mock_task.source_snapshot_refs = None  # No snapshot refs
    mock_task.doc_type = "disclosure_notes"
    mock_task.project_id = project_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db.execute = AsyncMock(return_value=mock_result)

    svc = DeliverableSectionStateService(mock_db)

    result = await svc.detect_stale_sections_layered(
        word_export_task_id=task_id,
        project_id=project_id,
        year=year,
    )

    assert result == []


@pytest.mark.asyncio
async def test_empty_dict_snapshot_returns_empty(project_id, task_id, year):
    """source_snapshot_refs 为 dict 但无 tb_hash → 返回空列表。"""
    mock_db = AsyncMock()

    mock_task = MagicMock()
    mock_task.source_snapshot_refs = {"year": 2025}  # no tb_hash key
    mock_task.doc_type = "disclosure_notes"
    mock_task.project_id = project_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db.execute = AsyncMock(return_value=mock_result)

    svc = DeliverableSectionStateService(mock_db)

    result = await svc.detect_stale_sections_layered(
        word_export_task_id=task_id,
        project_id=project_id,
        year=year,
    )

    assert result == []


# ─── Test: tb_hash 变了但无 section 记录 → 返回空 ─────────────────────────────


@pytest.mark.asyncio
async def test_tb_hash_changed_no_sections_returns_empty(project_id, task_id, year):
    """tb_hash 变了但 deliverable_section_state 无记录 → 返回空。"""
    mock_db = AsyncMock()

    mock_task = MagicMock()
    mock_task.source_snapshot_refs = {"tb_hash": "old_hash", "year": year}
    mock_task.doc_type = "disclosure_notes"
    mock_task.project_id = project_id

    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = mock_task

    # Second call: empty section states
    mock_sections_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_sections_result.scalars.return_value = mock_scalars

    call_count = [0]
    results = [mock_task_result, mock_sections_result]

    async def side_effect_execute(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return results[idx] if idx < len(results) else MagicMock()

    mock_db.execute = AsyncMock(side_effect=side_effect_execute)

    svc = DeliverableSectionStateService(mock_db)

    with patch(_SNAP_SVC_PATCH) as MockSnapSvc:
        mock_snap_instance = AsyncMock()
        mock_snap_instance.capture_snapshot_ref = AsyncMock(
            return_value=FakeSnapshotRef(tb_hash="new_hash")
        )
        MockSnapSvc.return_value = mock_snap_instance

        result = await svc.detect_stale_sections_layered(
            word_export_task_id=task_id,
            project_id=project_id,
            year=year,
        )

    assert result == []
