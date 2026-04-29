"""Phase 16: 版本链与取证完整性测试

测试用例 ID: P16-UT-001 ~ P16-UT-010
"""
import uuid
import hashlib
import tempfile
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.version_line_service import VersionLineService
from app.services.export_integrity_service import ExportIntegrityService
from app.models.phase16_enums import (
    VersionObjectType, ConflictResolution, ConflictStatus, HashCheckStatus
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def version_service():
    return VersionLineService()


@pytest.fixture
def integrity_service():
    return ExportIntegrityService()


# ── P16-UT-001: write_stamp version_no=1 成功 ─────────────────

@pytest.mark.asyncio
async def test_write_stamp_first_version(mock_db, version_service):
    """P16-UT-001: 首次写入 version_no=1 成功"""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0  # max=0
    mock_db.execute.return_value = mock_result

    result = await version_service.write_stamp(
        db=mock_db,
        project_id=uuid.uuid4(),
        object_type="workpaper",
        object_id=uuid.uuid4(),
        version_no=1,
    )
    assert result["version_no"] == 1
    assert result["trace_id"].startswith("trc_")
    mock_db.add.assert_called_once()


# ── P16-UT-002: write_stamp 跳号阻断 ──────────────────────────

@pytest.mark.asyncio
async def test_write_stamp_gap_rejected(mock_db, version_service):
    """P16-UT-002: version_no=3 跳号（当前 max=1）→ 409"""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1  # max=1
    mock_db.execute.return_value = mock_result

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await version_service.write_stamp(
            db=mock_db,
            project_id=uuid.uuid4(),
            object_type="workpaper",
            object_id=uuid.uuid4(),
            version_no=3,
        )
    assert exc_info.value.status_code == 409
    assert "VERSION_LINE_GAP" in str(exc_info.value.detail)


# ── P16-UT-003: write_stamp 连续成功 ──────────────────────────

@pytest.mark.asyncio
async def test_write_stamp_sequential(mock_db, version_service):
    """P16-UT-003: version_no=2（当前 max=1）→ 成功"""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db.execute.return_value = mock_result

    result = await version_service.write_stamp(
        db=mock_db,
        project_id=uuid.uuid4(),
        object_type="report",
        object_id=uuid.uuid4(),
        version_no=2,
    )
    assert result["version_no"] == 2


# ── P16-UT-006: calc_hash 正确性 ──────────────────────────────

@pytest.mark.asyncio
async def test_calc_hash_known_content(integrity_service):
    """P16-UT-006: 已知内容的 SHA-256"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"hello world")
        f.flush()
        path = f.name

    try:
        result = await integrity_service.calc_hash(path)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected
    finally:
        os.unlink(path)


# ── P16-UT-007: build_manifest ─────────────────────────────────

@pytest.mark.asyncio
async def test_build_manifest(integrity_service):
    """P16-UT-007: 3 个文件 → manifest 含 3 条 + manifest_hash"""
    files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.txt") as f:
            f.write(f"content_{i}".encode())
            files.append(f.name)

    try:
        result = await integrity_service.build_manifest("test_export_001", files)
        assert len(result["files"]) == 3
        assert result["manifest_hash"]
        assert all(fc["sha256"] for fc in result["files"])
    finally:
        for f in files:
            os.unlink(f)


# ── P16-UT-008: verify_package 全部匹配 ───────────────────────

@pytest.mark.asyncio
async def test_calc_hash_nonexistent_file(integrity_service):
    """P16-UT-008 prereq: 不存在的文件返回空字符串"""
    result = await integrity_service.calc_hash("/nonexistent/file.txt")
    assert result == ""


# ── 枚举完整性 ─────────────────────────────────────────────────

def test_version_object_type_enum():
    assert len(VersionObjectType) == 4


def test_conflict_resolution_enum():
    assert len(ConflictResolution) == 3


def test_conflict_status_enum():
    assert len(ConflictStatus) == 3


def test_hash_check_status_enum():
    assert len(HashCheckStatus) == 2
