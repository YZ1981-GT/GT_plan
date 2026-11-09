"""批 7 任务 7.3：签字快照一致事务边界（flush-only 服务 + 原子签字写入）。

验证 ADR-CRW-007（design §49-51「snapshot 创建只 flush，签字路由统一提交并设置
projects.consol_lock」）：

1. 服务 flush-not-commit —— `create_consol_snapshot` 只 flush，不 commit：
   调用后在同一会话可见快照；但调用方 `rollback()` 后快照不落库（证明服务没自行 commit）。
2. 原子签字写入 —— 签字路由（reason=sign/lock）在一个事务边界内写齐四项：
   快照 + 签字记录（SignatureRecord）+ operation terminal（result_refs.sealed）+
   consol_lock（projects 三字段），commit 后四项全部落库且互相引用。
3. 任一步失败整体回滚 —— 第四项（锁定）注入失败 ⇒ 前三项（快照/签字/terminal）零落库。
4. 门拒绝零落库 —— sign/lock 门（7.2）拒绝 ⇒ 快照/签字/terminal/锁定全部零落库。

纯 SQLite 内存库 + 直接调用路由函数（不起 HTTP 栈）：路由函数对 db 的 commit/rollback
是本任务的被测对象，用真实会话跑完整事务边界。门复用的 readiness/artifact 两处真源用
monkeypatch 控制（与 test_snapshot_sign_lock_gate 同口径，不重复 5.x/6.x fixture）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

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
    ConsolTrial,
    ConsolWorksheet,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.core import Project, User
from app.models.extension_models import SignatureRecord
from app.models.phase10_models import ConsolSnapshot
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.models.report_models import FinancialReport, ReportConfig
from app.services import consol_snapshot_service as svc

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
    SignatureRecord.__table__,
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
        id=uuid.uuid4(), name="【测试】签字事务_2025", client_name="【测试】签字事务",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        template_type="soe", status=ProjectStatus.execution,
    )


async def _seed_shards(db: AsyncSession, project_id: uuid.UUID) -> ConsolOperation:
    """落最小真实分片数据 + 一条成功 operation（供 version/operation refs 与封存目标）。"""
    operation = ConsolOperation(
        id=uuid.uuid4(), project_id=project_id, year=YEAR,
        operation_type="refresh_all", idempotency_key="idem-signoff-" + uuid.uuid4().hex,
        request_hash="a" * 64, status="succeeded", revision=3, attempt=1,
        version_vector={"digest": "v" * 64},
        trigger_source="manual", finished_at=datetime.now(timezone.utc),
        result_refs={"report_run_id": str(uuid.uuid4())},
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


# ── 门事实构造（与 test_snapshot_sign_lock_gate 同口径）─────────────────────────

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


def _patch_gate_pass(monkeypatch) -> None:
    """门全过：readiness/artifact 两处真源替换为就绪事实，并让全部分片采集成功。"""
    async def _facts(*_a, **_k):
        return _ready_facts()

    async def _items(*_a, **_k):
        return _ready_items()

    monkeypatch.setattr(
        "app.services.consol_readiness_service.load_readiness_facts", _facts,
    )
    monkeypatch.setattr(
        "app.services.consol_archive_provider.collect_consol_archive_items", _items,
    )
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)


def _user(uid: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uid)


async def _call_create_snapshot(db, project_id, *, reason, user_id):
    """直接调用路由函数（require_project_audit_year monkeypatch 到固定年度）。"""
    from app.routers import report_trace

    return await report_trace.create_snapshot(
        project_id=project_id, year=YEAR, reason=reason,
        db=db, current_user=_user(user_id),
    )


@pytest.fixture(autouse=True)
def _stub_audit_year(monkeypatch):
    async def _year(_db, _pid, year=None):
        return year or YEAR
    monkeypatch.setattr(
        "app.routers.report_trace.require_project_audit_year", _year,
    )


# ── 1. 服务只 flush 不 commit ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_flushes_not_commits(db: AsyncSession):
    """create_consol_snapshot 只 flush：调用后同会话可见；rollback 后不落库。"""
    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    await _seed_shards(db, pid)

    result = await svc.create_consol_snapshot(
        db, pid, YEAR, reason="manual", user_id=uuid.uuid4(),
    )
    # flush 后同会话可见（拿到 id）
    assert result["id"]
    row = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    assert row is not None

    # 服务没有 commit ⇒ 调用方回滚后快照消失（证明事务由调用方拥有）
    await db.rollback()
    count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolSnapshot)
    )).scalar_one()
    assert count == 0


# ── 2. 签字路由在一致事务边界写齐四项 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_signoff_writes_all_four_atomically(db: AsyncSession, monkeypatch):
    """reason=sign：commit 后 快照 + 签字记录 + operation sealed + consol_lock 四项齐落库。"""
    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    operation = await _seed_shards(db, pid)
    op_id = operation.id  # 捕获主键，避免 expire_all 后惰性加载触发 MissingGreenlet
    _patch_gate_pass(monkeypatch)
    actor = uuid.uuid4()

    result = await _call_create_snapshot(db, pid, reason="sign", user_id=actor)
    assert result["locked"] is True
    snap_id = uuid.UUID(result["id"])

    # commit 后 expire_all 强制重读（路由已 db.commit()，证明四项真正落库）。
    db.expire_all()

    # ① 快照
    snap = await db.get(ConsolSnapshot, snap_id)
    assert snap is not None
    assert snap.snapshot_data["_locked"] is True

    # ② 签字记录（object_type=consol_snapshot，指向本快照）
    sigs = (await db.execute(
        sa.select(SignatureRecord).where(
            SignatureRecord.object_type == "consol_snapshot",
            SignatureRecord.object_id == snap_id,
        )
    )).scalars().all()
    assert len(sigs) == 1
    assert sigs[0].signer_id == actor
    assert sigs[0].signature_data["snapshot_hash"] == result["hash"]

    # ③ operation terminal / sealed（result_refs.sealed 指回本快照）
    op = await db.get(ConsolOperation, op_id)
    sealed = (op.result_refs or {}).get("sealed")
    assert sealed is not None
    assert sealed["snapshot_id"] == result["id"]
    assert sealed["snapshot_hash"] == result["hash"]
    assert sealed["signed_by"] == str(actor)

    # ④ consol_lock（projects 三字段原子设置）
    proj = await db.get(Project, pid)
    assert proj.consol_lock is True
    assert proj.consol_lock_by == actor
    assert proj.consol_lock_at is not None


# ── 3. 任一步失败整体回滚（all-or-nothing）────────────────────────────────────

@pytest.mark.asyncio
async def test_signoff_rolls_back_all_when_lock_fails(db: AsyncSession, monkeypatch):
    """第四项（锁定）注入失败 ⇒ 快照/签字/operation sealed 全部零落库。"""
    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    operation = await _seed_shards(db, pid)
    op_id = operation.id
    _patch_gate_pass(monkeypatch)

    # 让 ConsolLockService.lock_project 抛错（模拟第四步失败）
    async def _boom(self, *_a, **_k):
        raise RuntimeError("锁定注入失败")

    monkeypatch.setattr(
        "app.services.consol_enhanced_service.ConsolLockService.lock_project", _boom,
    )

    with pytest.raises(RuntimeError, match="锁定注入失败"):
        await _call_create_snapshot(db, pid, reason="sign", user_id=uuid.uuid4())

    # 路由 except 已 db.rollback()；expire_all 后重读证明四项全部零落库 / 未改。
    db.expire_all()
    snap_count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolSnapshot)
    )).scalar_one()
    assert snap_count == 0  # ① 快照零落库
    sig_count = (await db.execute(
        sa.select(sa.func.count()).select_from(SignatureRecord)
    )).scalar_one()
    assert sig_count == 0  # ② 签字记录零落库
    op = await db.get(ConsolOperation, op_id)
    assert (op.result_refs or {}).get("sealed") is None  # ③ operation 未封存
    proj = await db.get(Project, pid)
    assert proj.consol_lock is False  # ④ 项目未锁定


@pytest.mark.asyncio
async def test_signoff_rolls_back_all_when_signature_fails(db: AsyncSession, monkeypatch):
    """第二项（签字记录）注入失败 ⇒ 快照 + 后续步骤全部零落库（更早步失败同样整体回滚）。"""
    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    operation = await _seed_shards(db, pid)
    op_id = operation.id
    _patch_gate_pass(monkeypatch)

    async def _boom(self, *_a, **_k):
        raise RuntimeError("签字注入失败")

    monkeypatch.setattr(
        "app.services.sign_service.SignService.sign_document", _boom,
    )

    with pytest.raises(RuntimeError, match="签字注入失败"):
        await _call_create_snapshot(db, pid, reason="lock", user_id=uuid.uuid4())

    db.expire_all()
    snap_count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolSnapshot)
    )).scalar_one()
    assert snap_count == 0
    op = await db.get(ConsolOperation, op_id)
    assert (op.result_refs or {}).get("sealed") is None
    proj = await db.get(Project, pid)
    assert proj.consol_lock is False


# ── 4. 门拒绝（7.2）零落库，且不触发后三步 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_rejection_leaves_zero_rows(db: AsyncSession, monkeypatch):
    """sign 门拒绝（artifact 缺失）⇒ 409，快照/签字/operation sealed/锁定全部零落库。"""
    from fastapi import HTTPException

    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    operation = await _seed_shards(db, pid)
    op_id = operation.id

    # readiness 全过、全部分片采集成功，但 artifact 缺件 ⇒ 门拒绝
    async def _facts(*_a, **_k):
        return _ready_facts()

    async def _items(*_a, **_k):
        return [
            {"kind": "consol_operation", "status": "ready"},
            {"kind": "report_run", "status": "missing", "label": "正式报表运行", "reason": "无"},
            {"kind": "report_excel", "status": "ready"},
            {"kind": "consol_workpaper", "status": "ready"},
        ]

    monkeypatch.setattr(
        "app.services.consol_readiness_service.load_readiness_facts", _facts,
    )
    monkeypatch.setattr(
        "app.services.consol_archive_provider.collect_consol_archive_items", _items,
    )
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)

    # 签字步若被触发应当红；门在它们之前，故永远不会被调用。
    async def _should_not_run(self, *_a, **_k):
        raise AssertionError("门拒绝后不应写签字记录")

    monkeypatch.setattr(
        "app.services.sign_service.SignService.sign_document", _should_not_run,
    )

    with pytest.raises(HTTPException) as ei:
        await _call_create_snapshot(db, pid, reason="sign", user_id=uuid.uuid4())
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "artifact_missing"

    db.expire_all()
    snap_count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolSnapshot)
    )).scalar_one()
    assert snap_count == 0
    sig_count = (await db.execute(
        sa.select(sa.func.count()).select_from(SignatureRecord)
    )).scalar_one()
    assert sig_count == 0
    op = await db.get(ConsolOperation, op_id)
    assert (op.result_refs or {}).get("sealed") is None
    proj = await db.get(Project, pid)
    assert proj.consol_lock is False


# ── 5. manual 不触发签字四步（只提交快照一项）─────────────────────────────────

@pytest.mark.asyncio
async def test_manual_does_not_sign_or_lock(db: AsyncSession, monkeypatch):
    """reason=manual：只落快照，不写签字记录、不封存 operation、不锁定项目。"""
    p = _project()
    pid = p.id
    db.add(p)
    await db.commit()
    operation = await _seed_shards(db, pid)
    op_id = operation.id

    async def _should_not_run(self, *_a, **_k):
        raise AssertionError("manual 不应写签字记录")

    monkeypatch.setattr(
        "app.services.sign_service.SignService.sign_document", _should_not_run,
    )

    result = await _call_create_snapshot(db, pid, reason="manual", user_id=uuid.uuid4())
    assert result["locked"] is False
    assert "locked_project" not in result

    db.expire_all()
    snap = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    assert snap is not None  # 快照确实提交
    sig_count = (await db.execute(
        sa.select(sa.func.count()).select_from(SignatureRecord)
    )).scalar_one()
    assert sig_count == 0
    op = await db.get(ConsolOperation, op_id)
    assert (op.result_refs or {}).get("sealed") is None
    proj = await db.get(Project, pid)
    assert proj.consol_lock is False
