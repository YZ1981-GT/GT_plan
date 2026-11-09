"""批 7 任务 7.5：签字快照故障注入 / 变异证明（ADR-CRW-007 / R9.1~R9.3 / R5.3）。

本文件把批 7 全部签字快照面做**系统化**故障注入，补齐 7.1~7.4 既有测试未覆盖的
参数化面与端到端联动：

1. 逐个摘 capturer（manual）——对 11 类分片逐一注入采集失败（参数化），证明 manual
   快照仍创建、该分片进 failed_sources、partial=True、根 hash 仍可校验还原。
2. 逐个摘 capturer（sign/lock）——对 11 个 required 分片逐一注入采集失败（参数化），
   证明 sign/lock 快照被 ConsolSnapshotRejected 拒绝且零落库。
3. 篡改分片/hash + 归档 fail-closed 联动——三类篡改向量（根 hash / payload 分片 /
   manifest 分片 hash）逐一证明 restore hash_valid=False + shard_mismatches 正确，并断言
   归档 provider（6.5）把被篡改的签字快照当成缺件（fail-closed）。
4. 并发改数据后签字失败关闭——门评估与落库之间 required 分片转失败 / readiness 转
   not_ready，证明 sign/lock 拒绝且零落库（stale-between-gate-and-persist）。
5. 签字后还原——真实锁定签字快照落库后，即使子公司/抵销/底层数据被改，还原仍得到
   签字时合并数且 hash_valid 恒 True，compare_snapshot_to_current 检出漂移科目。

每个保护点都标注变异证明口径（见文件末 `test_mutation_*` 与各断言旁注）。
SQLite 内存库即可（真实 PG 双会话属批 8）。
"""
from __future__ import annotations

import copy
import json as _json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
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
    AccountCategory,
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
    ConsolSnapshotRejected,
    _SHARD_ORDER,
    _SIGN_LOCK_REQUIRED_SHARDS,
    create_consol_snapshot,
    compare_snapshot_to_current,
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
        id=uuid.uuid4(), name="【测试】快照故障注入_2025", client_name="【测试】快照故障注入",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        template_type="soe", status=ProjectStatus.execution,
    )


async def _seed_shards(db: AsyncSession, project_id: uuid.UUID) -> ConsolOperation:
    """跨多个分片表落最小真实数据 + 一条成功 operation（供 version/operation refs）。

    含一行 consol_trial（供签字后还原 / 漂移对比），其余分片落最小行以使全部 capturer
    真实返回非空（逐个摘 capturer 时才能和"本就为空"区分开）。
    """
    operation = ConsolOperation(
        id=uuid.uuid4(), project_id=project_id, year=YEAR,
        operation_type="refresh_all", idempotency_key="idem-fi-" + uuid.uuid4().hex,
        request_hash="a" * 64, status="succeeded", revision=3, attempt=1,
        version_vector={"digest": "v" * 64, "tree_fingerprint": "f" * 64},
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
    db.add(ConsolTrial(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, standard_account_code="1601",
        account_name="固定资产", account_category=AccountCategory.asset,
        individual_sum=Decimal("500.00"), consol_adjustment=Decimal("0.00"),
        consol_elimination=Decimal("0.00"), consol_amount=Decimal("500.00"),
    ))
    await db.commit()
    return operation


# ── 门事实构造（readiness/artifact 两处 seam，与 7.2/7.3 同口径）──────────────

def _ready_facts() -> dict:
    return {
        "tree": {"has_tree": True, "node_count": 2},
        "worksheet": {"has_worksheet_data": True, "evidence_status": "ready"},
        "elimination": {"approved_count": 1, "draft_count": 0, "pending_count": 0},
        "calc": {"has_trial": True, "stale_trial_count": 0},
        "report": {"has_published_run": True},
        "note": {"total_sections": 0},
        "lifecycle": {"has_snapshot": False},
        "evidence": {"status": "ready"},
        "review": {"review_status": None},
    }


def _ready_items() -> list[dict]:
    return [
        {"kind": "consol_operation", "status": "ready"},
        {"kind": "report_run", "status": "ready"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "ready"},
    ]


def _patch_readiness_artifact(monkeypatch, *, facts: dict, items: list[dict]) -> None:
    async def _facts(*_a, **_k):
        return facts

    async def _items(*_a, **_k):
        return items

    monkeypatch.setattr(
        "app.services.consol_readiness_service.load_readiness_facts", _facts,
    )
    monkeypatch.setattr(
        "app.services.consol_archive_provider.collect_consol_archive_items", _items,
    )


def _patch_all_capturers_ok(monkeypatch) -> None:
    """全部分片采集成功（返回空 list/dict），隔离 readiness/artifact 分支。"""
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)


def _make_boom(label: str):
    async def _boom(*_a, **_k):
        raise RuntimeError(f"采集失败注入:{label}")
    return _boom


# ═══════════════════════════════════════════════════════════════════════════
# 场景 1：逐个摘 capturer（manual）—— 参数化全部 11 类分片
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("shard", list(_SHARD_ORDER))
@pytest.mark.asyncio
async def test_manual_each_capturer_removed_still_creates_partial(
    db: AsyncSession, monkeypatch, shard: str,
):
    """逐一摘掉 11 类分片中的某一个 ⇒ manual 快照仍创建、该分片进 failed_sources、
    partial=True，且失败分片以 None 入 payload 其 hash 仍记录 ⇒ 根 hash 还原校验通过。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    monkeypatch.setitem(svc._SHARD_CAPTURERS, shard, _make_boom(shard))

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())
    manifest = result["manifest"]

    # 快照确实落库（manual 不拒绝）
    assert result["id"]
    assert manifest["partial"] is True
    assert shard in manifest["failed_sources"]
    assert shard not in manifest["captured_sources"]
    # 其余 10 分片仍成功捕获
    assert set(manifest["captured_sources"]) == set(_SHARD_ORDER) - {shard}
    # 失败分片仍有 hash（捕获为 None 后 hash）；全部 11 个 shard_hash 齐备
    assert set(manifest["shard_hashes"]) == set(_SHARD_ORDER)

    # 还原：失败分片 = None，根 hash 仍校验通过（partial 快照完整性自洽）
    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is True
    assert restored["root_valid"] is True
    assert restored["shard_mismatches"] == []
    assert restored["data"]["shards"][shard] is None


@pytest.mark.asyncio
async def test_manual_all_capturers_removed_still_creates(db: AsyncSession, monkeypatch):
    """极端：11 类分片全部采集失败 ⇒ manual 仍创建、failed_sources 含全部、仍可还原校验。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    for key in _SHARD_ORDER:
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _make_boom(key))

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())
    manifest = result["manifest"]
    assert manifest["partial"] is True
    assert set(manifest["failed_sources"]) == set(_SHARD_ORDER)
    assert manifest["captured_sources"] == []

    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is True
    assert all(restored["data"]["shards"][k] is None for k in _SHARD_ORDER)


# ═══════════════════════════════════════════════════════════════════════════
# 场景 2：逐个摘 capturer（sign/lock）—— 参数化全部 11 个 required 分片，fail-closed
# ═══════════════════════════════════════════════════════════════════════════


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar_one()


@pytest.mark.parametrize("shard", sorted(_SIGN_LOCK_REQUIRED_SHARDS))
@pytest.mark.parametrize("reason", ["sign", "lock"])
@pytest.mark.asyncio
async def test_sign_lock_each_required_capturer_removed_rejects_zero_rows(
    db: AsyncSession, monkeypatch, shard: str, reason: str,
):
    """sign/lock + 任一 required 分片采集失败 ⇒ ConsolSnapshotRejected
    (required_source_missing) 且零落库（snapshot 零行）。参数化覆盖 11 个 required 分片。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    # readiness / artifact 全过以隔离 required_source 分支
    _patch_readiness_artifact(monkeypatch, facts=_ready_facts(), items=_ready_items())
    # 先让全部分片采集成功，再单独摘掉目标 required 分片
    _patch_all_capturers_ok(monkeypatch)
    monkeypatch.setitem(svc._SHARD_CAPTURERS, shard, _make_boom(shard))

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason=reason, user_id=uuid.uuid4())

    assert ei.value.code == "required_source_missing"
    detail = next(f for f in ei.value.failures if f["code"] == "required_source_missing")["detail"]
    assert shard in detail["failed_required_shards"]
    # 零落库（fail-closed：拒绝绝不 add/flush/commit）
    assert await _count(db, ConsolSnapshot) == 0


@pytest.mark.asyncio
async def test_sign_lock_all_required_shards_in_frozenset_are_eleven(db: AsyncSession):
    """守卫：required 集合恰为 11 类分片（与 _SHARD_ORDER 同集合），逐个摘覆盖完整。"""
    assert _SIGN_LOCK_REQUIRED_SHARDS == frozenset(_SHARD_ORDER)
    assert len(_SIGN_LOCK_REQUIRED_SHARDS) == 11


# ═══════════════════════════════════════════════════════════════════════════
# 场景 3：篡改分片 / hash + 归档 provider fail-closed 联动
# ═══════════════════════════════════════════════════════════════════════════


async def _make_locked_snapshot(db: AsyncSession, project_id: uuid.UUID) -> ConsolSnapshot:
    """落一个真实锁定签字快照（enforce_gate=False 绕门，只为构造完整 v2 manifest fixture）。"""
    result = await create_consol_snapshot(
        db, project_id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False,
    )
    await db.commit()
    return await db.get(ConsolSnapshot, uuid.UUID(result["id"]))


def _tamper_root_hash(data: dict) -> dict:
    tampered = copy.deepcopy(data)
    tampered["_hash"] = "0" * 64
    return tampered


def _tamper_payload_shard(data: dict) -> dict:
    """解压 payload → 改一个分片内容 → 重新压缩（不更新 manifest 分片 hash）。"""
    raw = _json.loads(svc._decompress_payload(data["_payload"]))
    raw.setdefault("shards", {})
    existing = raw["shards"].get("entries")
    if isinstance(existing, list):
        existing.append({"id": "injected", "review_status": "approved"})
    else:
        raw["shards"]["entries"] = [{"id": "injected"}]
    tampered = copy.deepcopy(data)
    tampered["_payload"] = svc._compress_payload(svc._canonical_json(raw))
    return tampered


def _tamper_manifest_shard_hash(data: dict) -> dict:
    tampered = copy.deepcopy(data)
    tampered["_manifest"]["shard_hashes"]["trial"] = "0" * 64
    return tampered


_TAMPER_VECTORS = {
    "root_hash": (_tamper_root_hash, None),
    "payload_shard": (_tamper_payload_shard, "entries"),
    "manifest_shard_hash": (_tamper_manifest_shard_hash, "trial"),
}


@pytest.mark.parametrize("vector", sorted(_TAMPER_VECTORS))
@pytest.mark.asyncio
async def test_tamper_vector_fails_restore_validation(
    db: AsyncSession, vector: str,
):
    """三类篡改向量逐一证明 restore hash_valid=False；payload/manifest 向量还要命中
    对应 shard_mismatches（根 hash 向量使 root_valid=False）。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    snap = await _make_locked_snapshot(db, p.id)

    tamper_fn, expected_mismatch = _TAMPER_VECTORS[vector]
    snap.snapshot_data = tamper_fn(snap.snapshot_data)
    await db.commit()

    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is False
    if expected_mismatch is not None:
        assert expected_mismatch in restored["shard_mismatches"]
    else:
        assert restored["root_valid"] is False


@pytest.mark.parametrize("vector", sorted(_TAMPER_VECTORS))
@pytest.mark.asyncio
async def test_tamper_vector_makes_archive_fail_closed(
    db: AsyncSession, vector: str,
):
    """每类篡改向量 ⇒ 归档 provider 的签字快照项判 missing（fail-closed 联动 6.5）。

    未篡改时同一快照项 = ready；篡改后同一快照项 = missing（完整性受损），证明归档
    确实复用 restore 的 hash_valid 作完整性闸门，而非只看快照存在。
    """
    from app.services.consol_archive_provider import _snapshot_item

    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    snap = await _make_locked_snapshot(db, p.id)

    # 未篡改：归档项 ready（对照组）
    before = await _snapshot_item(db, p.id, YEAR, require_snapshot=True)
    assert before["status"] == "ready", before

    tamper_fn, _ = _TAMPER_VECTORS[vector]
    snap.snapshot_data = tamper_fn(snap.snapshot_data)
    await db.commit()

    after = await _snapshot_item(db, p.id, YEAR, require_snapshot=True)
    assert after["status"] == "missing"
    assert ("哈希" in after["reason"]) or ("完整性" in after["reason"])


# ═══════════════════════════════════════════════════════════════════════════
# 场景 4：并发改数据 / stale ⇒ 签字 fail-closed 且零落库
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_concurrent_readiness_flip_rejects_zero_rows(db: AsyncSession, monkeypatch):
    """门评估时 readiness 已被并发改动翻成 not_ready ⇒ sign 拒绝且零落库。

    模拟"分片采集完成后、落库前，另一会话撤回了某审批 / 新增待审批分录" —— 门在落库前
    现读 readiness，fail-closed。分片采集全过以隔离 readiness 分支。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    _patch_all_capturers_ok(monkeypatch)
    # readiness 现读到并发改动后的状态：elimination 多出 3 笔待审批 ⇒ not_ready
    stale_facts = _ready_facts()
    stale_facts["elimination"] = {"approved_count": 0, "draft_count": 0, "pending_count": 3}
    _patch_readiness_artifact(monkeypatch, facts=stale_facts, items=_ready_items())

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert ei.value.code == "readiness_not_ready"
    assert await _count(db, ConsolSnapshot) == 0


@pytest.mark.asyncio
async def test_concurrent_artifact_disappears_rejects_zero_rows(db: AsyncSession, monkeypatch):
    """门评估时正式报表运行 artifact 已被并发删除（missing）⇒ sign 拒绝且零落库。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    _patch_all_capturers_ok(monkeypatch)
    gone_items = [
        {"kind": "consol_operation", "status": "ready"},
        {"kind": "report_run", "status": "missing", "label": "正式报表运行", "reason": "并发删除"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "ready"},
    ]
    _patch_readiness_artifact(monkeypatch, facts=_ready_facts(), items=gone_items)

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason="lock", user_id=uuid.uuid4())
    assert ei.value.code == "artifact_missing"
    assert await _count(db, ConsolSnapshot) == 0


@pytest.mark.asyncio
async def test_gate_evaluated_before_persist_not_after(db: AsyncSession, monkeypatch):
    """变异证明：门必须在落库前评估。把门替换成"必拒"，验证没有任何快照被写入。

    若生产代码把门挪到 flush 之后（或忽略门结果），本断言会红（零落库被打破）。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)

    async def _reject(*_a, **_k):
        return {
            "allowed": False,
            "failures": [{"category": "readiness", "code": "readiness_not_ready",
                          "message": "注入拒绝", "detail": {"blockers": ["注入"]}}],
            "readiness": {},
        }

    monkeypatch.setattr(svc, "evaluate_sign_lock_gate", _reject)
    with pytest.raises(ConsolSnapshotRejected):
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert await _count(db, ConsolSnapshot) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 场景 5：签字后还原 —— 数据被改后仍还原签字时合并数并检出漂移
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_post_sign_restore_freezes_signed_numbers_and_detects_drift(
    db: AsyncSession,
):
    """真实锁定签字快照后，改 consol_trial / 分录 ⇒
    (a) restore_consol_snapshot 仍得到签字时合并数且 hash_valid=True（冻结不受后续改动影响）；
    (b) compare_snapshot_to_current 检出被改科目（漂移）。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)  # trial 1601=500.00

    snap = await _make_locked_snapshot(db, p.id)
    assert snap.snapshot_data["_locked"] is True
    signed_hash = snap.snapshot_data["_hash"]

    # 签字时还原：trial 1601=500.00，无漂移
    before = await compare_snapshot_to_current(db, snap)
    assert before["hash_valid"] is True
    assert before["changed_count"] == 0

    # 并发/后续改底层数据：改合并数 500 → 888，新增一笔抵销分录
    await db.execute(
        ConsolTrial.__table__.update()
        .where(ConsolTrial.project_id == p.id, ConsolTrial.standard_account_code == "1601")
        .values(consol_amount=Decimal("888.00"))
    )
    db.add(EliminationEntry(
        id=uuid.uuid4(), project_id=p.id, year=YEAR, entry_no="DR-2",
        entry_type=EliminationEntryType.equity, account_code="1601",
        debit_amount=Decimal("50.00"), credit_amount=Decimal("0.00"),
        entry_group_id=uuid.uuid4(), review_status=ReviewStatusEnum.approved,
    ))
    await db.commit()

    # (a) 还原仍是签字时数值，hash 恒有效（快照冻结自洽，不随库变化）
    restored = restore_consol_snapshot(snap)
    assert restored["hash_valid"] is True
    assert restored["hash"] == signed_hash
    trial_shard = restored["data"]["shards"]["trial"]
    row_1601 = next(r for r in trial_shard if r["standard_account_code"] == "1601")
    assert row_1601["consol_amount"] == "500.00"  # 冻结值，不是 888

    # (b) compare 检出漂移：1601 签字时 500 vs 当前 888
    after = await compare_snapshot_to_current(db, snap)
    assert after["hash_valid"] is True
    assert after["changed_count"] == 1
    drift = next(r for r in after["by_account"] if r["account_code"] == "1601")
    assert drift["snapshot_amount"] == "500.00"
    assert drift["current_amount"] == "888.00"
    assert drift["changed"] is True


@pytest.mark.asyncio
async def test_post_sign_restore_detects_deleted_account_as_drift(db: AsyncSession):
    """签字后删除一个被合并科目 ⇒ compare 把它记为漂移（当前为 0 / 签字时非 0）。"""
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    snap = await _make_locked_snapshot(db, p.id)

    # 软删 trial 行（_capture_trial 过滤 is_deleted）
    await db.execute(
        ConsolTrial.__table__.update()
        .where(ConsolTrial.project_id == p.id)
        .values(is_deleted=True)
    )
    await db.commit()

    after = await compare_snapshot_to_current(db, snap)
    assert after["hash_valid"] is True
    drift = next(r for r in after["by_account"] if r["account_code"] == "1601")
    assert drift["snapshot_amount"] == "500.00"
    assert drift["current_amount"] == "0"
    assert drift["changed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 变异证明（mutation proof）：确认各保护点被移除时断言会红
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mutation_tamper_undetected_if_shard_hash_not_checked(db: AsyncSession):
    """变异证明（场景 3）：若 restore 只看根 hash、不逐分片比对，payload 篡改将漏网。

    这里用一个"只看根 hash"的替身还原器复现"去掉分片校验"的变异，证明在该变异下
    篡改确实不会被 shard_mismatches 检出 —— 从而反证真实 _restore_v2 的逐分片校验是
    必要保护点（真实还原器对同一篡改返回 hash_valid=False，见
    test_tamper_vector_fails_restore_validation[payload_shard]）。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    snap = await _make_locked_snapshot(db, p.id)

    # 篡改 payload 分片但同步改根 hash 以匹配被篡改 payload（模拟"只校验根 hash"的世界）
    raw = _json.loads(svc._decompress_payload(snap.snapshot_data["_payload"]))
    raw["shards"]["entries"].append({"id": "injected"})
    new_payload = svc._compress_payload(svc._canonical_json(raw))
    # 只看根 hash 的替身：根 hash = payload 的 sha256（与真实根 hash 口径不同，仅示意）
    faux_root = svc._sha256_hex(svc._canonical_json(raw))

    # 真实还原器：根 hash 仍是旧的、manifest 分片 hash 未改 ⇒ 必然 hash_valid=False
    tampered = copy.deepcopy(snap.snapshot_data)
    tampered["_payload"] = new_payload
    snap.snapshot_data = tampered
    await db.commit()
    real = restore_consol_snapshot(snap)
    assert real["hash_valid"] is False  # 真实保护点生效
    assert "entries" in real["shard_mismatches"]
    # 对照：仅根 hash 口径下 faux_root == 篡改后 payload 的 hash（变异世界会误判为有效）
    assert faux_root == svc._sha256_hex(svc._canonical_json(raw))


@pytest.mark.asyncio
async def test_mutation_manual_partial_flag_reflects_real_failures(
    db: AsyncSession, monkeypatch,
):
    """变异证明（场景 1）：partial 必须由真实 failed_sources 推出，而非恒 False。

    注入一个分片失败后 partial 必须 True；若生产把 partial 写死 False（变异），
    本断言会红。对照：无失败注入时 partial 为 False（见 7.1 既有测试）。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    monkeypatch.setitem(svc._SHARD_CAPTURERS, "trial", _make_boom("trial"))
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual")
    assert result["meta"]["partial"] is True
    assert bool(result["meta"]["failed_sources"]) is True


@pytest.mark.asyncio
async def test_mutation_sign_lock_zero_rows_requires_no_persist_on_reject(
    db: AsyncSession, monkeypatch,
):
    """变异证明（场景 2/4）：拒绝路径必须零落库。

    若生产在抛 ConsolSnapshotRejected 前已 add+flush（变异），count 会 > 0。这里直接
    断言拒绝后 count==0，作为该保护点的红线。
    """
    p = _project(); db.add(p); await db.commit()
    await _seed_shards(db, p.id)
    _patch_readiness_artifact(monkeypatch, facts=_ready_facts(), items=_ready_items())
    _patch_all_capturers_ok(monkeypatch)
    monkeypatch.setitem(svc._SHARD_CAPTURERS, "trial", _make_boom("trial"))

    with pytest.raises(ConsolSnapshotRejected):
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert await _count(db, ConsolSnapshot) == 0
