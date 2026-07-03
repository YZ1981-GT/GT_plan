"""Unit tests for VersionTrailService.compute_diff (Task 2.4)

Tests the async compute_diff method which reads snapshots from DB,
validates them, and delegates to compute_diff_pure.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.version_trail_service import DiffResult, VersionTrailService


def _make_mapping(data: dict):
    """Create a mock mapping row."""
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    return m


def _make_result(row):
    """Create a mock DB result with .mappings().first()."""
    result = MagicMock()
    mappings = MagicMock()
    mappings.first.return_value = row
    result.mappings.return_value = mappings
    return result


@pytest.mark.asyncio
async def test_compute_diff_snapshot_a_not_found():
    """If snapshot A is not found, raises 404."""
    db = AsyncMock()
    db.execute.return_value = _make_result(None)

    with pytest.raises(HTTPException) as exc_info:
        await VersionTrailService.compute_diff(
            db=db,
            version_a_id=uuid.uuid4(),
            version_b_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 404
    assert "版本快照不存在" in exc_info.value.detail


@pytest.mark.asyncio
async def test_compute_diff_snapshot_b_not_found():
    """If snapshot B is not found, raises 404."""
    wp_id = uuid.uuid4()
    row_a = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": wp_id,
        "data_json": [{"item_id": "x1", "conclusion": "Y", "remark": None, "wp_ref": None}],
    })

    db = AsyncMock()
    # First call returns row_a, second call returns None
    db.execute.side_effect = [_make_result(row_a), _make_result(None)]

    with pytest.raises(HTTPException) as exc_info:
        await VersionTrailService.compute_diff(
            db=db,
            version_a_id=uuid.uuid4(),
            version_b_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_compute_diff_different_workpapers():
    """If the two snapshots belong to different workpapers, raises 400."""
    row_a = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": uuid.uuid4(),
        "data_json": [],
    })
    row_b = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": uuid.uuid4(),  # different
        "data_json": [],
    })

    db = AsyncMock()
    db.execute.side_effect = [_make_result(row_a), _make_result(row_b)]

    with pytest.raises(HTTPException) as exc_info:
        await VersionTrailService.compute_diff(
            db=db,
            version_a_id=uuid.uuid4(),
            version_b_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 400
    assert "只能对比同一底稿的版本" in exc_info.value.detail


@pytest.mark.asyncio
async def test_compute_diff_degraded_a():
    """If snapshot A is degraded (dict, not list), raises 400."""
    wp_id = uuid.uuid4()
    row_a = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": wp_id,
        "data_json": {"_degraded": True, "item_ids": ["x1"]},
    })
    row_b = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": wp_id,
        "data_json": [{"item_id": "x1", "conclusion": "Y", "remark": None, "wp_ref": None}],
    })

    db = AsyncMock()
    db.execute.side_effect = [_make_result(row_a), _make_result(row_b)]

    with pytest.raises(HTTPException) as exc_info:
        await VersionTrailService.compute_diff(
            db=db,
            version_a_id=uuid.uuid4(),
            version_b_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 400
    assert "版本A" in exc_info.value.detail


@pytest.mark.asyncio
async def test_compute_diff_degraded_b():
    """If snapshot B is degraded (dict, not list), raises 400."""
    wp_id = uuid.uuid4()
    row_a = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": wp_id,
        "data_json": [{"item_id": "x1", "conclusion": "Y", "remark": None, "wp_ref": None}],
    })
    row_b = _make_mapping({
        "id": uuid.uuid4(),
        "workpaper_id": wp_id,
        "data_json": {"_degraded": True, "item_ids": ["x1"]},
    })

    db = AsyncMock()
    db.execute.side_effect = [_make_result(row_a), _make_result(row_b)]

    with pytest.raises(HTTPException) as exc_info:
        await VersionTrailService.compute_diff(
            db=db,
            version_a_id=uuid.uuid4(),
            version_b_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 400
    assert "版本B" in exc_info.value.detail


@pytest.mark.asyncio
async def test_compute_diff_success():
    """Happy path: two valid snapshots from same workpaper → DiffResult."""
    wp_id = uuid.uuid4()
    data_a = [
        {"item_id": "item1", "conclusion": "Y", "remark": "ok", "wp_ref": "D2-3"},
        {"item_id": "item2", "conclusion": "N", "remark": "问题", "wp_ref": None},
        {"item_id": "item3", "conclusion": "Y", "remark": None, "wp_ref": None},
    ]
    data_b = [
        {"item_id": "item1", "conclusion": "Y", "remark": "ok", "wp_ref": "D2-3"},  # unchanged
        {"item_id": "item2", "conclusion": "Y", "remark": "已修正", "wp_ref": "D2-5"},  # modified
        # item3 deleted
        {"item_id": "item4", "conclusion": None, "remark": "新增行", "wp_ref": None},  # added
    ]

    row_a = _make_mapping({"id": uuid.uuid4(), "workpaper_id": wp_id, "data_json": data_a})
    row_b = _make_mapping({"id": uuid.uuid4(), "workpaper_id": wp_id, "data_json": data_b})

    db = AsyncMock()
    db.execute.side_effect = [_make_result(row_a), _make_result(row_b)]

    result = await VersionTrailService.compute_diff(
        db=db,
        version_a_id=uuid.uuid4(),
        version_b_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )

    assert isinstance(result, DiffResult)
    # item4 added
    assert len(result.added) == 1
    assert result.added[0].item_id == "item4"
    # item3 deleted
    assert len(result.deleted) == 1
    assert result.deleted[0].item_id == "item3"
    # item2 modified (conclusion + remark + wp_ref all changed)
    assert len(result.modified) == 3  # 3 fields changed
    modified_item_ids = {m.item_id for m in result.modified}
    assert modified_item_ids == {"item2"}
    # item1 unchanged
    assert result.unchanged_count == 1
    # summary
    assert "新增1项" in result.summary
    assert "删除1项" in result.summary
    assert "修改3个字段" in result.summary
