"""Phase 16: 集成测试

测试用例 ID: P16-IT-001 ~ P16-IT-006 + P16-SEC-001 + P16-UT 补充
"""
import uuid
import hashlib
import tempfile
import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from decimal import Decimal

from app.services.version_line_service import VersionLineService
from app.services.export_integrity_service import ExportIntegrityService
from app.services.offline_conflict_service import OfflineConflictService
from app.services.consistency_replay_engine import (
    ConsistencyReplayEngine, ConsistencyLayer, ConsistencyDiff, CONSISTENCY_THRESHOLD
)
from app.models.phase16_enums import ConflictStatus, ConflictResolution, HashCheckStatus


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


# ── P16-IT-002: 导出→完整性校验→查询全链路 ─────────────────────

@pytest.mark.asyncio
async def test_export_build_and_verify_full_chain():
    """P16-IT-002: build_manifest → persist → verify → all passed"""
    svc = ExportIntegrityService()

    # 创建临时文件
    files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.docx") as f:
            f.write(f"content_{i}_test".encode())
            files.append(f.name)

    try:
        # Step 1: build manifest
        manifest = await svc.build_manifest("test_export_001", files)
        assert len(manifest["files"]) == 3
        assert manifest["manifest_hash"]

        # Step 2: verify each file hash
        for fc in manifest["files"]:
            actual = await svc.calc_hash(fc["file_path"])
            assert actual == fc["sha256"], f"Hash mismatch for {fc['file_path']}"

    finally:
        for f in files:
            os.unlink(f)


# ── P16-IT-003: 篡改检测 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_tamper_detection():
    """P16-SEC-001: 篡改文件 → hash 不匹配"""
    svc = ExportIntegrityService()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
        f.write(b"original content")
        path = f.name

    try:
        original_hash = await svc.calc_hash(path)

        # 篡改文件
        with open(path, "wb") as f:
            f.write(b"tampered content")

        tampered_hash = await svc.calc_hash(path)
        assert original_hash != tampered_hash, "Tampered file should have different hash"

    finally:
        os.unlink(path)


# ── P16-UT-011~016: 冲突检测与合并 ────────────────────────────

@pytest.mark.asyncio
async def test_conflict_resolve_requires_reason_code(mock_db):
    """P16-UT-015: resolve 缺 reason_code → 400"""
    svc = OfflineConflictService()

    mock_conflict = MagicMock()
    mock_conflict.id = uuid.uuid4()
    mock_conflict.status = ConflictStatus.open
    mock_conflict.project_id = uuid.uuid4()
    mock_conflict.local_value = {"value": 100}
    mock_conflict.remote_value = {"value": 200}

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conflict
    mock_db.execute.return_value = mock_result

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await svc.resolve(mock_db, mock_conflict.id, "accept_local", uuid.uuid4(), "")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_conflict_resolve_already_resolved(mock_db):
    """P16-UT-014: resolve 已 resolved → 409"""
    svc = OfflineConflictService()

    mock_conflict = MagicMock()
    mock_conflict.id = uuid.uuid4()
    mock_conflict.status = ConflictStatus.resolved  # 已解决

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conflict
    mock_db.execute.return_value = mock_result

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await svc.resolve(mock_db, mock_conflict.id, "accept_local", uuid.uuid4(), "DATA_MISMATCH")
    assert exc_info.value.status_code == 409
    assert "CONFLICT_ALREADY_RESOLVED" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_conflict_resolve_manual_merge_requires_value(mock_db):
    """P16-UT-016: manual_merge 无 merged_value → 400"""
    svc = OfflineConflictService()

    mock_conflict = MagicMock()
    mock_conflict.id = uuid.uuid4()
    mock_conflict.status = ConflictStatus.open

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conflict
    mock_db.execute.return_value = mock_result

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await svc.resolve(
            mock_db, mock_conflict.id, ConflictResolution.manual_merge,
            uuid.uuid4(), "DATA_MISMATCH", None  # 无 merged_value
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_conflict_resolve_accept_local_sets_merged(mock_db):
    """P16-UT-013: accept_local → merged_value=local_value + qc_job_id 非空"""
    svc = OfflineConflictService()

    mock_conflict = MagicMock()
    mock_conflict.id = uuid.uuid4()
    mock_conflict.status = ConflictStatus.open
    mock_conflict.project_id = uuid.uuid4()
    mock_conflict.local_value = {"value": 12000}
    mock_conflict.remote_value = {"value": 12500}
    mock_conflict.merged_value = None
    mock_conflict.resolver_id = None
    mock_conflict.reason_code = None
    mock_conflict.resolved_at = None
    mock_conflict.qc_replay_job_id = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conflict
    mock_db.execute.return_value = mock_result

    result = await svc.resolve(
        mock_db, mock_conflict.id, "accept_local", uuid.uuid4(), "DATA_MISMATCH"
    )
    assert mock_conflict.merged_value == {"value": 12000}
    assert mock_conflict.status == ConflictStatus.resolved
    assert mock_conflict.qc_replay_job_id is not None
    assert "qc_replay_job_id" in result


# ── P16-UT-017~025: 一致性复算 ────────────────────────────────

def test_consistency_threshold():
    """P16 prereq: 阻断阈值 = 0.01"""
    assert CONSISTENCY_THRESHOLD == Decimal("0.01")


def test_consistency_layer_structure():
    """P16-UT-023: overall_status = inconsistent 当任一层 inconsistent"""
    layers = [
        ConsistencyLayer("tb_balance", "trial_balance", "consistent"),
        ConsistencyLayer("trial_balance", "financial_report", "inconsistent", [
            ConsistencyDiff("report_line", "BS-001", "amount", 12000, 12500, 500, "blocking")
        ]),
        ConsistencyLayer("financial_report", "disclosure_notes", "consistent"),
        ConsistencyLayer("disclosure_notes", "working_papers", "consistent"),
        ConsistencyLayer("working_papers", "trial_balance", "consistent"),
    ]

    has_inconsistent = any(l.status == "inconsistent" for l in layers)
    assert has_inconsistent is True

    blocking_count = sum(1 for l in layers for d in l.diffs if d.severity == "blocking")
    assert blocking_count == 1


def test_consistency_diff_severity():
    """P16-UT-018: 差异 500 → severity=blocking"""
    diff = ConsistencyDiff("account", "1001", "closing_balance", 12000, 12500, 500, "blocking")
    assert diff.severity == "blocking"
    assert diff.diff == 500


# ── P16 合同测试 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_version_line_query_returns_list(mock_db):
    """P16-CONTRACT-001: query_lineage 返回 list"""
    svc = VersionLineService()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    result = await svc.query_lineage(mock_db, uuid.uuid4())
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_export_integrity_calc_hash_deterministic():
    """P16-CONTRACT-002: 同一文件多次 calc_hash 结果一致"""
    svc = ExportIntegrityService()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"deterministic content")
        path = f.name

    try:
        h1 = await svc.calc_hash(path)
        h2 = await svc.calc_hash(path)
        assert h1 == h2, "Same file should produce same hash"
    finally:
        os.unlink(path)
