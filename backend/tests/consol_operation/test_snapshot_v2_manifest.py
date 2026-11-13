"""批 7 任务 7.1：签字快照 v2 manifest 测试。

覆盖 ADR-CRW-007 / R9.3：
1. v2 build/round-trip —— 11 类分片全部捕获，解压还原分片原始数据。
2. 每类分片独立 hash + manifest 根 hash；恢复须逐分片 + 根 hash 全部校验通过。
3. operation/version refs —— manifest 挂最近成功 operation 与其版本向量摘要。
4. v1（gzip+base64）向后兼容读取仍通过；旧空壳快照记 legacy。
5. 篡改任一分片 / 根 hash ⇒ hash_valid=False（完整性检测，归档 fail-closed）。

纯函数层（root/shard hash、v1 兼容）无需 DB；DB 层用 SQLite 内存库跨分片落数据后
真实走 create_consol_snapshot(format_version=2) → restore_consol_snapshot。

注：本文件只验 manifest/hash 结构，reason 一律用 "manual"（结构与 reason 无关）；
sign/lock fail-closed 政策门（任务 7.2）单独在 test_snapshot_sign_lock_gate.py 验证。
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.models.base import Base, ProjectStatus
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.consol_operation_models import ConsolOperation
from app.models.consol_push_models import ConsolNoteFormula
from app.models.consol_scope_confirmation_models import ConsolScopeConfirmation
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.consolidation_models import (
    ConsolTrial,
    ConsolWorksheet,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.core import Project, User
from app.models.phase10_models import ConsolSnapshot
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.models.report_models import FinancialReport, ReportConfig
from app.services import consol_snapshot_service as svc
from app.services.consol_snapshot_service import (
    _SHARD_ORDER,
    _root_hash,
    _shard_hash,
    create_consol_snapshot,
    restore_consol_snapshot,
)

YEAR = 2025

_TABLES = [
    User.__table__, Project.__table__, ConsolOperation.__table__,
    ConsolScopeConfirmation.__table__, ConsolWorksheetData.__table__,
    EliminationEntry.__table__, ConsolNoteData.__table__,
    ConsolSnapshot.__table__,
    ConsolWorksheet.__table__, ConsolTrial.__table__,
    FinancialReport.__table__, ReportConfig.__table__,
    ConsolNoteTemplateBinding.__table__, ConsolNoteMappingRule.__table__,
    ConsolNoteMappingBinding.__table__, ConsolNoteFormula.__table__,
    ReportGenerationRun.__table__, ConsolArtifact.__table__,
    AuditLogEntry.__table__, AuditChainHead.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】快照v2_2025", client_name="【测试】快照v2",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        template_type="soe", status=ProjectStatus.execution,
    )


async def _seed_shards(db: AsyncSession, project_id: uuid.UUID) -> ConsolOperation:
    """跨多个分片表落最小真实数据，并建一条成功 operation 供 version/operation refs。"""
    operation = ConsolOperation(
        id=uuid.uuid4(), project_id=project_id, year=YEAR,
        operation_type="refresh_all", idempotency_key="idem-v2-" + uuid.uuid4().hex,
        request_hash="a" * 64, status="succeeded", revision=3, attempt=1,
        version_vector={
            "digest": "v" * 64, "tree_fingerprint": "f" * 64, "tree_revision": 7,
            "tb_digest": "t" * 64, "elimination_digest": "e" * 64,
            "formula_digest": "o" * 64, "note_mapping_digest": "m" * 64,
            "template_digest": "p" * 64,
        },
        trigger_source="manual", finished_at=datetime.now(timezone.utc),
    )
    db.add(operation)

    db.add(ConsolScopeConfirmation(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, report_scope="consolidated",
        revision=7, fingerprint="f" * 64, canonical_payload={"nodes": []}, status="active",
    ))
    db.add(ConsolWorksheetData(
        id=uuid.uuid4(), project_id=project_id, year=YEAR,
        sheet_key="审定表L1-1", data={"rows": [{"a": "1"}]}, version=5,
    ))
    db.add(EliminationEntry(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, entry_no="DR-1",
        entry_type=EliminationEntryType.equity, account_code="1601",
        debit_amount=Decimal("100.00"), credit_amount=Decimal("0.00"),
        entry_group_id=uuid.uuid4(), review_status=ReviewStatusEnum.approved,
    ))
    db.add(ConsolNoteData(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, section_id="五、8",
        node_key="root", data={"table": [["x"]]}, cell_state="auto",
    ))
    await db.commit()
    return operation


@pytest.mark.asyncio
async def test_v2_manifest_has_all_eleven_shards(db: AsyncSession):
    """create_consol_snapshot(format_version=2) 捕获全部 11 类分片且 manifest 结构完整。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())
    manifest = result["manifest"]

    assert manifest["manifest_version"] == 2
    assert tuple(manifest["shard_order"]) == _SHARD_ORDER
    assert set(manifest["shard_hashes"]) == set(_SHARD_ORDER)
    assert len(_SHARD_ORDER) == 11
    # 每个分片 hash 都是 64 位十六进制
    assert all(len(h) == 64 for h in manifest["shard_hashes"].values())
    assert len(manifest["root_hash"]) == 64
    assert result["hash"] == manifest["root_hash"]
    assert manifest["partial"] is False
    assert manifest["failed_sources"] == []
    assert set(manifest["captured_sources"]) == set(_SHARD_ORDER)


@pytest.mark.asyncio
async def test_v2_root_hash_is_over_ordered_shard_hashes(db: AsyncSession):
    """根 hash = 按 _SHARD_ORDER 有序的 (key, shard_hash) 列表的 SHA-256。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")
    manifest = result["manifest"]
    assert _root_hash(manifest["shard_hashes"]) == manifest["root_hash"]


@pytest.mark.asyncio
async def test_v2_round_trip_restores_shards_and_validates_all_hashes(db: AsyncSession):
    """还原 v2 快照：分片数据回得来，逐分片 + 根 hash 全部校验通过。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")

    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    restored = restore_consol_snapshot(snap)

    assert restored["hash_valid"] is True
    assert restored["root_valid"] is True
    assert restored["shard_mismatches"] == []
    # 分片原始数据可还原（shards 子树 + 顶层展平两种口径）
    assert set(restored["data"]["shards"]) == set(_SHARD_ORDER)
    assert restored["data"]["trial"] == restored["data"]["shards"]["trial"]
    # 工作表分片带出 version
    ws = restored["data"]["shards"]["worksheet_data"]
    assert ws and ws[0]["version"] == 5
    # 分录分片带出审批状态
    entries = restored["data"]["shards"]["entries"]
    assert entries and entries[0]["review_status"] == "approved"


@pytest.mark.asyncio
async def test_v2_manifest_carries_operation_and_version_refs(db: AsyncSession):
    """manifest 挂最近成功 operation 引用与其版本向量摘要（operation/version refs）。"""
    p = _project(); db.add(p); await db.commit()
    operation = await _seed_shards(db, p.id)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")
    manifest = result["manifest"]

    op_ref = manifest["operation_ref"]
    assert op_ref["operation_id"] == str(operation.id)
    assert op_ref["revision"] == 3
    assert op_ref["status"] == "succeeded"

    ver_ref = manifest["version_ref"]
    assert ver_ref["digest"] == "v" * 64
    assert ver_ref["tree_fingerprint"] == "f" * 64
    assert ver_ref["tree_revision"] == 7
    assert ver_ref["elimination_digest"] == "e" * 64


@pytest.mark.asyncio
async def test_v2_compare_snapshot_to_current_reads_trial_shard(db: AsyncSession):
    """compare_snapshot_to_current 在 v2 快照上仍按 trial 分片比对（向后兼容读取）。"""
    from app.models.consolidation_models import AccountCategory
    from app.services.consol_snapshot_service import compare_snapshot_to_current

    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    # trial 分片落一行，签字时合并数 = 500.00
    db.add(ConsolTrial(
        id=uuid.uuid4(), project_id=p.id, year=YEAR, standard_account_code="1601",
        account_name="固定资产", account_category=AccountCategory.asset,
        individual_sum=Decimal("500.00"), consol_adjustment=Decimal("0.00"),
        consol_elimination=Decimal("0.00"), consol_amount=Decimal("500.00"),
    ))
    await db.commit()

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")
    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))

    # 未改数据：无差异且 hash 校验通过
    cmp_same = await compare_snapshot_to_current(db, snap)
    assert cmp_same["hash_valid"] is True
    assert cmp_same["changed_count"] == 0

    # 改当前合并数 → 逐科目检出差异
    trial = (await db.execute(
        ConsolTrial.__table__.select().where(ConsolTrial.project_id == p.id)
    )).first()
    await db.execute(
        ConsolTrial.__table__.update()
        .where(ConsolTrial.id == trial.id)
        .values(consol_amount=Decimal("999.00"))
    )
    await db.commit()
    cmp_changed = await compare_snapshot_to_current(db, snap)
    assert cmp_changed["changed_count"] == 1
    row = next(r for r in cmp_changed["by_account"] if r["account_code"] == "1601")
    assert row["snapshot_amount"] == "500.00"
    assert row["current_amount"] == "999.00"
    assert row["changed"] is True


@pytest.mark.asyncio
async def test_v2_tampered_root_hash_fails_validation(db: AsyncSession):
    """篡改存储根 hash（_hash）⇒ hash_valid=False（归档 provider 据此 fail-closed）。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")

    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    tampered = copy.deepcopy(snap.snapshot_data)
    tampered["_hash"] = "0" * 64
    snap.snapshot_data = tampered
    await db.commit()

    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is False


@pytest.mark.asyncio
async def test_v2_tampered_shard_payload_fails_validation(db: AsyncSession):
    """篡改分片原始数据（payload 内某分片）而 manifest 分片 hash 不符 ⇒ hash_valid=False。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")

    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    data = snap.snapshot_data
    # 解压 payload → 改一个分片的值 → 重新压缩（但不更新 manifest 分片 hash）
    raw_json = svc._decompress_payload(data["_payload"])
    import json as _json

    raw = _json.loads(raw_json)
    raw["shards"]["entries"].append({"id": "injected", "review_status": "approved"})
    tampered = copy.deepcopy(data)
    tampered["_payload"] = svc._compress_payload(svc._canonical_json(raw))
    snap.snapshot_data = tampered
    await db.commit()

    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is False
    assert "entries" in restored["shard_mismatches"]
    assert restored["root_valid"] is False


@pytest.mark.asyncio
async def test_v2_tampered_manifest_shard_hash_fails_validation(db: AsyncSession):
    """篡改 manifest 内某分片 hash（payload 不动）⇒ manifest 自相矛盾 ⇒ hash_valid=False。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")

    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    tampered = copy.deepcopy(snap.snapshot_data)
    tampered["_manifest"]["shard_hashes"]["trial"] = "0" * 64
    snap.snapshot_data = tampered
    await db.commit()

    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is False
    assert "trial" in restored["shard_mismatches"]


@pytest.mark.asyncio
async def test_v2_partial_when_a_shard_capturer_fails(db: AsyncSession, monkeypatch):
    """某分片采集抛错 ⇒ 该分片记 failed + partial=True，其余分片仍捕获，根 hash 仍可校验。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    async def _boom(*_a, **_k):
        raise RuntimeError("采集失败注入")

    monkeypatch.setitem(svc._SHARD_CAPTURERS, "artifact", _boom)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")
    manifest = result["manifest"]

    assert manifest["partial"] is True
    assert "artifact" in manifest["failed_sources"]
    assert "artifact" not in manifest["captured_sources"]
    # 失败分片以 None 入 payload，其 hash 仍记录，根 hash 校验仍一致
    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is True
    assert restored["data"]["shards"]["artifact"] is None


# ---------------------------------------------------------------------------
# 纯函数层：root/shard hash 与向后兼容（无需 DB）
# ---------------------------------------------------------------------------


def test_shard_hash_deterministic_and_order_independent():
    """分片 hash 对 key 顺序无关（canonical sort_keys），同内容稳定。"""
    a = {"x": [1, 2], "y": {"a": 1, "b": 2}}
    b = {"y": {"b": 2, "a": 1}, "x": [1, 2]}
    assert _shard_hash(a) == _shard_hash(b)


def test_root_hash_only_covers_known_shard_order():
    """根 hash 只纳入 _SHARD_ORDER 中出现的分片，额外键不参与。"""
    hashes = {k: _shard_hash({"k": k}) for k in _SHARD_ORDER}
    base = _root_hash(hashes)
    with_extra = dict(hashes)
    with_extra["unknown_shard"] = _shard_hash({"k": "unknown"})
    assert _root_hash(with_extra) == base


def test_root_hash_changes_when_any_shard_hash_changes():
    """任一分片 hash 变化 ⇒ 根 hash 变化。"""
    hashes = {k: _shard_hash({"k": k}) for k in _SHARD_ORDER}
    base = _root_hash(hashes)
    mutated = dict(hashes)
    mutated["trial"] = "0" * 64
    assert _root_hash(mutated) != base


@pytest.mark.asyncio
async def test_v1_backward_compatible_read_still_valid(db: AsyncSession):
    """旧 gzip+base64（v1）快照仍能还原且 hash_valid=True（向后兼容读取）。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", format_version=1)
    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    assert snap.snapshot_data["_format"] == "gzip+base64"

    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is True
    # v1 顶层字段仍是 trial/worksheet/report/notes
    assert "trial" in restored["data"]
    assert "shards" not in restored["data"]


def test_legacy_empty_shell_reads_as_legacy():
    """旧 {created_at} 空壳快照：hash_valid=False + legacy=True，不抛错。"""
    from types import SimpleNamespace

    snap = SimpleNamespace(
        snapshot_data={"created_at": "2026-05-30T00:00:00Z"},
        project_id=uuid.uuid4(), year=YEAR,
    )
    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is False
    assert restored["legacy"] is True


def test_v2_valid_vs_tampered_via_namespace_replica():
    """纯替身层：合法 v2 → hash_valid=True；改 payload 不改 manifest → False（变异证明）。"""
    from types import SimpleNamespace

    shards = {k: {"k": k} for k in _SHARD_ORDER}
    shard_hashes = {k: _shard_hash(v) for k, v in shards.items()}
    root = _root_hash(shard_hashes)
    raw = {"project_id": "pid", "year": YEAR, "shards": shards}
    payload = svc._compress_payload(svc._canonical_json(raw))
    good = {
        "_format": "manifest-v2", "_payload": payload, "_hash": root, "_locked": True,
        "_manifest": {
            "manifest_version": 2, "shard_order": list(_SHARD_ORDER),
            "shard_hashes": shard_hashes, "root_hash": root,
        },
    }
    assert restore_consol_snapshot(SimpleNamespace(snapshot_data=good))["hash_valid"] is True

    # 改一个分片内容但不更新 shard_hashes/root ⇒ 失败
    bad_raw = copy.deepcopy(raw)
    bad_raw["shards"]["trial"] = {"k": "tampered"}
    bad = copy.deepcopy(good)
    bad["_payload"] = svc._compress_payload(svc._canonical_json(bad_raw))
    out = restore_consol_snapshot(SimpleNamespace(snapshot_data=bad))
    assert out["hash_valid"] is False
    assert "trial" in out["shard_mismatches"]
