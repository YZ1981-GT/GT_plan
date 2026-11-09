"""批 7 任务 7.2：签字/锁定快照 fail-closed 政策门测试（ADR-CRW-007 / R9.1~R9.2）。

政策拆分：
- manual 诊断快照：允许 partial，单分片采集失败不阻断，回执列明 failed_sources / partial=True。
- sign/signed/lock 快照：fail-closed —— required source（分片采集）/ readiness（七域）/
  artifact（正式报表运行 + 不可变 artifact）任一失败即抛 ConsolSnapshotRejected，不落库。

门本身复用既有真源（consol_readiness_service、consol_archive_provider），不重建 readiness /
artifact 逻辑。本测试通过 monkeypatch 这两处 seam 精确隔离"政策拆分"行为，不重复 5.x/6.x 的
readiness/artifact fixture；required-source 分支用真实分片采集失败注入验证。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.phase10_models import ConsolSnapshot
from app.services import consol_snapshot_service as svc
from app.services.consol_snapshot_service import (
    ConsolSnapshotRejected,
    _is_lock_reason,
    create_consol_snapshot,
    evaluate_sign_lock_gate,
)

YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    # 建全部 ORM 表：create_consol_snapshot 的 v2 分片采集会读多张 consol 表（空表无妨，
    # 门的 readiness/artifact 通过 monkeypatch 控制），缺表会在采集外的 operation 查询处抛错。
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】签字门_2025", client_name="【测试】签字门",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        template_type="soe", status=ProjectStatus.execution,
    )


# ── readiness / artifact 事实构造（供 monkeypatch 两处 seam）──────────────────

def _ready_facts() -> dict:
    """七域 readiness 全就绪（lifecycle 仅剩"未创建签字快照"自引用阻断，门内豁免）。"""
    return {
        "tree": {"has_tree": True, "node_count": 2},
        "worksheet": {"has_worksheet_data": True, "evidence_status": "ready"},
        "elimination": {"approved_count": 1, "draft_count": 0, "pending_count": 0},
        "calc": {"has_trial": True, "stale_trial_count": 0},
        "report": {"has_published_run": True},
        "note": {"total_sections": 0},
        "lifecycle": {"has_snapshot": False},  # 自引用阻断（门内豁免）
        "evidence": {"status": "ready"},
        "review": {"review_status": None},
    }


def _ready_artifact_items() -> list[dict]:
    """归档 provider 的 artifact 相关项全部 ready（operation/report_run/两 artifact）。"""
    return [
        {"kind": "consol_operation", "status": "ready"},
        {"kind": "report_run", "status": "ready"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "ready"},
    ]


def _patch_gate_deps(monkeypatch, *, facts: dict, items: list[dict]) -> None:
    """把门复用的两处真源替换为受控事实（readiness facts + archive items）。"""
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


# ── _is_lock_reason 政策映射 ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "reason,lock,expected",
    [
        ("sign", None, True),
        ("signed", None, True),
        ("lock", None, True),
        ("locked", None, True),
        ("signature", None, True),
        ("manual", None, False),
        ("diagnostic", None, False),
        ("manual", True, True),      # 显式 lock=True 覆盖 manual
        ("sign", False, False),      # 显式 lock=False 覆盖 sign
        ("SIGN", None, True),        # 大小写不敏感
    ],
)
def test_is_lock_reason_policy(reason, lock, expected):
    assert _is_lock_reason(reason, lock) is expected


# ── 门直接评估（evaluate_sign_lock_gate）────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_allows_when_all_pass(db: AsyncSession, monkeypatch):
    p = _project(); db.add(p); await db.commit()
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=[])
    assert gate["allowed"] is True
    assert gate["failures"] == []


@pytest.mark.asyncio
async def test_gate_rejects_on_required_source_missing(db: AsyncSession, monkeypatch):
    """某 required 分片采集失败 ⇒ required_source_missing（其余两类全过以隔离）。"""
    p = _project(); db.add(p); await db.commit()
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=["report", "trial"])
    assert gate["allowed"] is False
    codes = {f["code"] for f in gate["failures"]}
    assert codes == {"required_source_missing"}
    detail = next(f for f in gate["failures"])["detail"]
    assert set(detail["failed_required_shards"]) == {"report", "trial"}


@pytest.mark.asyncio
async def test_gate_ignores_non_required_failed_shard(db: AsyncSession, monkeypatch):
    """失败分片不在 required 集合内（构造一个不存在的键）⇒ 不触发 required_source 失败。"""
    p = _project(); db.add(p); await db.commit()
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=["not_a_required_shard"])
    assert gate["allowed"] is True


@pytest.mark.asyncio
async def test_gate_rejects_on_readiness_not_ready(db: AsyncSession, monkeypatch):
    """readiness 某域未就绪 ⇒ readiness_not_ready（其余两类全过以隔离）。"""
    p = _project(); db.add(p); await db.commit()
    facts = _ready_facts()
    facts["elimination"] = {"approved_count": 0, "draft_count": 0, "pending_count": 3}  # 3 笔待审批
    _patch_gate_deps(monkeypatch, facts=facts, items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=[])
    assert gate["allowed"] is False
    codes = {f["code"] for f in gate["failures"]}
    assert codes == {"readiness_not_ready"}
    blockers = next(f for f in gate["failures"])["detail"]["blockers"]
    assert any("待审批" in b for b in blockers)


@pytest.mark.asyncio
async def test_gate_readiness_exempts_snapshot_self_blocker(db: AsyncSession, monkeypatch):
    """lifecycle 仅剩"未创建签字快照"自引用阻断时，门必须放行（鸡生蛋豁免）。"""
    p = _project(); db.add(p); await db.commit()
    facts = _ready_facts()
    # lifecycle 未锁定、未归档、无快照 ⇒ _lifecycle 产出唯一阻断"未创建签字快照"
    facts["lifecycle"] = {"has_snapshot": False, "is_locked": False, "is_archived": False}
    _patch_gate_deps(monkeypatch, facts=facts, items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=[])
    assert gate["allowed"] is True, gate["failures"]


@pytest.mark.asyncio
async def test_gate_still_blocks_other_lifecycle_blockers(db: AsyncSession, monkeypatch):
    """lifecycle 复核退回仍是真实阻断（不被自引用豁免误放）。"""
    p = _project(); db.add(p); await db.commit()
    facts = _ready_facts()
    facts["lifecycle"] = {
        "has_snapshot": False, "is_locked": False, "is_archived": False,
        "review_status": "level1_rejected",
    }
    _patch_gate_deps(monkeypatch, facts=facts, items=_ready_artifact_items())

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=[])
    assert gate["allowed"] is False
    blockers = next(f for f in gate["failures"] if f["code"] == "readiness_not_ready")["detail"]["blockers"]
    assert any("退回" in b for b in blockers)
    assert all("未创建签字快照" not in b for b in blockers)


@pytest.mark.asyncio
async def test_gate_rejects_on_artifact_missing(db: AsyncSession, monkeypatch):
    """正式报表运行或 artifact 缺失 ⇒ artifact_missing（其余两类全过以隔离）。"""
    p = _project(); db.add(p); await db.commit()
    items = [
        {"kind": "consol_operation", "status": "ready"},
        {"kind": "report_run", "status": "ready"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "missing", "label": "合并工作底稿包",
         "reason": "没有已生成的合并工作底稿包"},
    ]
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=items)

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=[])
    assert gate["allowed"] is False
    codes = {f["code"] for f in gate["failures"]}
    assert codes == {"artifact_missing"}
    missing = next(f for f in gate["failures"])["detail"]["missing"]
    assert [m["kind"] for m in missing] == ["consol_workpaper"]


@pytest.mark.asyncio
async def test_gate_accumulates_all_three_categories(db: AsyncSession, monkeypatch):
    """三类同时失败 ⇒ 门列明全部失败（不提前短路）。"""
    p = _project(); db.add(p); await db.commit()
    facts = _ready_facts()
    facts["report"] = {"has_published_run": False}
    items = [
        {"kind": "consol_operation", "status": "missing", "label": "合并运行", "reason": "无"},
        {"kind": "report_run", "status": "ready"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "ready"},
    ]
    _patch_gate_deps(monkeypatch, facts=facts, items=items)

    gate = await evaluate_sign_lock_gate(db, p.id, YEAR, failed_shards=["entries"])
    assert gate["allowed"] is False
    codes = {f["code"] for f in gate["failures"]}
    assert codes == {"required_source_missing", "readiness_not_ready", "artifact_missing"}


# ── create_consol_snapshot：manual 允许 partial，sign/lock fail-closed ─────────

@pytest.mark.asyncio
async def test_manual_partial_allowed_lists_failures(db: AsyncSession, monkeypatch):
    """manual：某分片采集失败 ⇒ 仍创建快照，回执 partial=True + 列明 failed_sources。"""
    p = _project(); db.add(p); await db.commit()

    async def _boom(*_a, **_k):
        raise RuntimeError("采集失败注入")

    # 真实让多个分片采集失败（SQLite 无其余 consol 表 ⇒ 多数分片本就会抛错）；
    # 显式再注入一个确保 failed_sources 非空。
    monkeypatch.setitem(svc._SHARD_CAPTURERS, "artifact", _boom)

    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())

    assert result["meta"]["partial"] is True
    assert "artifact" in result["meta"]["failed_sources"]
    # 快照确实落库（manual 不拒绝）
    assert result["id"]
    row = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    assert row is not None
    assert row.snapshot_data["_manifest"]["partial"] is True


@pytest.mark.asyncio
async def test_manual_never_invokes_gate(db: AsyncSession, monkeypatch):
    """manual 口径即使门会拒绝也不评估门：gate 被替换成"必抛"仍能创建快照。"""
    p = _project(); db.add(p); await db.commit()

    async def _never(*_a, **_k):
        raise AssertionError("manual 不应评估 sign/lock 门")

    monkeypatch.setattr(svc, "evaluate_sign_lock_gate", _never)
    result = await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())
    assert result["id"]
    assert result["locked"] is False


@pytest.mark.asyncio
async def test_sign_rejects_and_persists_nothing_required_source(db: AsyncSession, monkeypatch):
    """sign + required 分片采集失败 ⇒ 抛 ConsolSnapshotRejected 且零落库。"""
    p = _project(); db.add(p); await db.commit()
    # readiness / artifact 全过，隔离 required_source 分支
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=_ready_artifact_items())

    async def _boom(*_a, **_k):
        raise RuntimeError("采集失败注入")

    monkeypatch.setitem(svc._SHARD_CAPTURERS, "report", _boom)

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert ei.value.code == "required_source_missing"
    assert ei.value.failures
    # 零落库
    count = (await db.execute(sa.select(sa.func.count()).select_from(ConsolSnapshot))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_sign_rejects_on_readiness(db: AsyncSession, monkeypatch):
    """sign + readiness 未就绪 ⇒ 拒绝且零落库（分片采集全过）。"""
    p = _project(); db.add(p); await db.commit()
    facts = _ready_facts()
    facts["tree"] = {"has_tree": False}
    _patch_gate_deps(monkeypatch, facts=facts, items=_ready_artifact_items())
    # 让全部分片采集成功，隔离 readiness 分支
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason="lock", user_id=uuid.uuid4())
    assert ei.value.code == "readiness_not_ready"
    count = (await db.execute(sa.select(sa.func.count()).select_from(ConsolSnapshot))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_sign_rejects_on_artifact(db: AsyncSession, monkeypatch):
    """sign + artifact 缺失 ⇒ 拒绝且零落库（分片采集 + readiness 全过）。"""
    p = _project(); db.add(p); await db.commit()
    items = [
        {"kind": "consol_operation", "status": "ready"},
        {"kind": "report_run", "status": "missing", "label": "正式报表运行", "reason": "无"},
        {"kind": "report_excel", "status": "ready"},
        {"kind": "consol_workpaper", "status": "ready"},
    ]
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=items)
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)

    with pytest.raises(ConsolSnapshotRejected) as ei:
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert ei.value.code == "artifact_missing"
    count = (await db.execute(sa.select(sa.func.count()).select_from(ConsolSnapshot))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_sign_succeeds_when_all_pass(db: AsyncSession, monkeypatch):
    """sign + required/readiness/artifact 全过 ⇒ 创建锁定快照并落库。"""
    p = _project(); db.add(p); await db.commit()
    _patch_gate_deps(monkeypatch, facts=_ready_facts(), items=_ready_artifact_items())
    # 全部分片采集成功（避免 required_source 失败）
    for key in svc._SHARD_ORDER:
        async def _ok(*_a, _k2=key, **_k):
            return [] if _k2 not in ("tree", "mappings", "formulas", "lifecycle", "artifact") else {}
        monkeypatch.setitem(svc._SHARD_CAPTURERS, key, _ok)

    result = await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4())
    assert result["id"]
    assert result["locked"] is True
    assert result["meta"]["partial"] is False
    row = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
    assert row is not None
    assert row.snapshot_data["_locked"] is True


@pytest.mark.asyncio
async def test_enforce_gate_false_bypasses_gate(db: AsyncSession, monkeypatch):
    """enforce_gate=False（fixture 构造口径）绕过门：即使门会拒绝也创建锁定快照。"""
    p = _project(); db.add(p); await db.commit()

    async def _never(*_a, **_k):
        raise AssertionError("enforce_gate=False 不应评估门")

    monkeypatch.setattr(svc, "evaluate_sign_lock_gate", _never)
    # 多数分片在 SQLite 下采集失败也无妨（门被绕过）
    result = await create_consol_snapshot(
        db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False,
    )
    assert result["id"]
    assert result["locked"] is True
