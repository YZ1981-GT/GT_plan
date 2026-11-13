"""审计链多死端确认（spec enterprise-embedding-rerank-closure R8，SQLite 内存库）。

覆盖 ``forks.append_fork_acks`` / ``append_fork_ack`` / ``build_fork_plan`` / ``blocked_chains`` /
``scan_forks(chain_key=…)``：一次确认多个死端、侧枝根一并确认、v2 哈希可被链校验重算、写后恰好一个链尾、
前置校验不符整体拒绝。真 PG（链锁 + JSONB 过滤）见 ``test_audit_chain_forks_pg.py``。
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.audit_log_models  # noqa: E402,F401
import app.models.core  # noqa: E402,F401
from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.services.audit_chain.canonical import GENESIS_HASH  # noqa: E402
from app.services.audit_chain.forks import (  # noqa: E402
    FORK_ACK_ACTION,
    _unconfirmed_tails,
    append_fork_ack,
    append_fork_acks,
    blocked_chains,
    build_fork_plan,
    plan_chain_forks,
    scan_forks,
)
from app.services.audit_chain.head import append_entry, read_head  # noqa: E402
from app.services.audit_chain.verify import verify_chain  # noqa: E402

engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
T0 = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
OPERATOR = uuid.uuid4()


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables = [Base.metadata.tables["audit_log_entries"], Base.metadata.tables["audit_chain_head"]]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _legacy(prev_hash: str, label: str, seconds: int, *, project_id: str | None = None) -> AuditLogEntry:
    """旧写法条目（无 _hash_v）：只用于搭链接关系，哈希取随机值。"""
    payload = {"label": label}
    if project_id:
        payload["project_id"] = project_id
    return AuditLogEntry(
        id=uuid.uuid4(), ts=T0 + timedelta(seconds=seconds), action_type=f"old.{label}",
        object_type="test", payload=payload, prev_hash=prev_hash,
        entry_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
    )


async def _add(db: AsyncSession, *entries: AuditLogEntry) -> None:
    db.add_all(entries)
    await db.flush()


async def _forked_chain(db: AsyncSession, project_id: str | None = None) -> dict[str, AuditLogEntry]:
    """主链 a1→a2→a3→main；a1 旁出单条 x；a2 旁出三条侧枝 y1→y2→y3 与单条 z（同一分叉点两个死端）。"""
    e: dict[str, AuditLogEntry] = {}
    e["a1"] = _legacy(GENESIS_HASH, "a1", 1, project_id=project_id)
    await _add(db, e["a1"])
    e["a2"] = _legacy(e["a1"].entry_hash, "a2", 2, project_id=project_id)
    e["x"] = _legacy(e["a1"].entry_hash, "x", 3, project_id=project_id)
    await _add(db, e["a2"], e["x"])
    e["y1"] = _legacy(e["a2"].entry_hash, "y1", 4, project_id=project_id)
    e["z"] = _legacy(e["a2"].entry_hash, "z", 5, project_id=project_id)
    e["a3"] = _legacy(e["a2"].entry_hash, "a3", 6, project_id=project_id)
    await _add(db, e["y1"], e["z"], e["a3"])
    e["y2"] = _legacy(e["y1"].entry_hash, "y2", 7, project_id=project_id)
    e["main"] = _legacy(e["a3"].entry_hash, "main", 9, project_id=project_id)
    await _add(db, e["y2"], e["main"])
    e["y3"] = _legacy(e["y2"].entry_hash, "y3", 8, project_id=project_id)
    await _add(db, e["y3"])
    return e


async def _ack_count(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count()).select_from(AuditLogEntry).where(AuditLogEntry.action_type == FORK_ACK_ACTION)
    )).scalar_one())


@pytest.mark.asyncio
async def test_multi_dead_tails_confirmed_in_one_chain(db: AsyncSession) -> None:
    e = await _forked_chain(db)
    assert await _unconfirmed_tails(db, "__global__") == {e["main"].id, e["x"].id, e["y3"].id, e["z"].id}

    written = await append_fork_acks(
        db, chain_key="__global__", survivor_entry_id=e["main"].id,
        dead_entry_ids=[e["x"].id, e["y3"].id, e["z"].id], operator_id=OPERATOR, reason="并发侧枝",
    )

    roles = {w.payload["dead_entry_id"]: w.payload["dead_role"] for w in written}
    assert roles == {
        str(e["x"].id): "tail_and_root", str(e["y1"].id): "branch_root",
        str(e["y3"].id): "tail", str(e["z"].id): "tail_and_root",
    }
    # 从主链尾起首尾相接，v2 载荷
    assert written[0].prev_hash == e["main"].entry_hash
    for prev, cur in zip(written, written[1:]):
        assert cur.prev_hash == prev.entry_hash
    assert all(w.payload["_hash_v"] == 2 and w.payload["batch_size"] == 4 for w in written)
    assert len({w.payload["batch_id"] for w in written}) == 1

    head = await read_head(db, "__global__")
    assert head is not None and head.tail_entry_id == written[-1].id
    assert await _unconfirmed_tails(db, "__global__") == {written[-1].id}
    assert [f for f in await scan_forks(db) if len(f["survivors"]) > 1] == []

    result = await verify_chain(db, chain_key="__global__")
    bad = [p for p in result.problems if p["type"] in {"fork", "content_mismatch", "orphan"}]
    assert bad == [], bad

    nxt = await append_entry(db, "__global__", action_type="test.after_ack", object_type="test")
    assert nxt.prev_hash == written[-1].entry_hash


@pytest.mark.asyncio
async def test_precondition_mismatch_rejects_and_writes_nothing(db: AsyncSession) -> None:
    e = await _forked_chain(db)
    with pytest.raises(ValueError, match="未确认链尾不匹配") as info:
        await append_fork_acks(
            db, chain_key="__global__", survivor_entry_id=e["main"].id,
            dead_entry_ids=[e["x"].id, e["y3"].id], operator_id=OPERATOR, reason="漏了 z",
        )
    assert str(e["z"].id) in str(info.value), "报错要列出实际链尾，便于核对"
    assert await _ack_count(db) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["empty", "survivor_in_deads", "blank_reason"])
async def test_argument_validation(db: AsyncSession, case: str) -> None:
    e = await _forked_chain(db)
    kwargs = {
        "empty": {"dead_entry_ids": [], "reason": "r"},
        "survivor_in_deads": {"dead_entry_ids": [e["main"].id, e["x"].id], "reason": "r"},
        "blank_reason": {"dead_entry_ids": [e["x"].id, e["y3"].id, e["z"].id], "reason": "  "},
    }[case]
    with pytest.raises(ValueError):
        await append_fork_acks(
            db, chain_key="__global__", survivor_entry_id=e["main"].id, operator_id=OPERATOR, **kwargs
        )
    assert await _ack_count(db) == 0


@pytest.mark.asyncio
async def test_single_wrapper_also_confirms_branch_root(db: AsyncSession) -> None:
    """单死端但侧枝有两条：旧实现只点名链尾，扫描 / 健康端点仍报这处分叉。"""
    a1 = _legacy(GENESIS_HASH, "a1", 1)
    await _add(db, a1)
    b = _legacy(a1.entry_hash, "b", 5)
    c1 = _legacy(a1.entry_hash, "c1", 2)
    await _add(db, b, c1)
    c2 = _legacy(c1.entry_hash, "c2", 3)
    await _add(db, c2)

    last = await append_fork_ack(
        db, chain_key="__global__", survivor_entry_id=b.id, dead_entry_id=c2.id,
        operator_id=OPERATOR, reason="下载侧枝",
    )
    assert last.payload["dead_entry_id"] == str(c2.id)
    assert await _ack_count(db) == 2
    forks = await scan_forks(db)
    assert forks and all(len(f["survivors"]) <= 1 for f in forks)
    assert {f["chain_key"] for f in forks} == {"__global__"}


@pytest.mark.asyncio
async def test_project_chain_ack_carries_project_and_verifies(db: AsyncSession) -> None:
    pid = str(uuid.uuid4())
    e = await _forked_chain(db, project_id=pid)
    key = f"project:{pid}"
    written = await append_fork_acks(
        db, chain_key=key, survivor_entry_id=e["main"].id,
        dead_entry_ids=[e["x"].id, e["y3"].id, e["z"].id], operator_id=OPERATOR, reason="项目链",
    )
    assert all(w.payload["project_id"] == pid for w in written)
    head = await read_head(db, key)
    assert head is not None and head.tail_entry_id == written[-1].id
    # 表里只有本例这条链；按项目过滤的分支按 settings 判方言，SQLite 下不走它
    result = await verify_chain(db)
    assert [p for p in result.problems if p["type"] in {"fork", "content_mismatch"}] == []


@pytest.mark.asyncio
async def test_scan_forks_chain_key_filters_by_derived_chain(db: AsyncSession) -> None:
    pid_a, pid_b = str(uuid.uuid4()), str(uuid.uuid4())
    for pid in (pid_a, pid_b):
        root = _legacy(GENESIS_HASH, "root", 1, project_id=pid)
        await _add(db, root)
        await _add(db, _legacy(root.entry_hash, "l", 2, project_id=pid), _legacy(root.entry_hash, "r", 3, project_id=pid))
    only_a = await scan_forks(db, chain_key=f"project:{pid_a}")
    assert len(only_a) == 1 and only_a[0]["chain_key"] == f"project:{pid_a}"
    assert {f["chain_key"] for f in await scan_forks(db)} == {f"project:{pid_a}", f"project:{pid_b}"}


@pytest.mark.asyncio
async def test_blocked_chains_and_plan(db: AsyncSession) -> None:
    pid = str(uuid.uuid4())
    e = await _forked_chain(db)
    root = _legacy(GENESIS_HASH, "root", 1, project_id=pid)
    await _add(db, root)
    await _add(db, _legacy(root.entry_hash, "ok", 2, project_id=pid))

    assert await blocked_chains(db) == [("__global__", 9, 4)]
    plan = await plan_chain_forks(db, "__global__")
    assert plan.survivor_id == e["main"].id, "建议主链尾 = 时间最新的链尾"
    assert {b.tail_id for b in plan.branches} == {e["x"].id, e["y3"].id, e["z"].id}
    branch_y = next(b for b in plan.branches if b.tail_id == e["y3"].id)
    assert branch_y.root_id == e["y1"].id and len(branch_y.entry_ids) == 3

    await append_fork_acks(
        db, chain_key="__global__", survivor_entry_id=plan.survivor_id,
        dead_entry_ids=[b.tail_id for b in plan.branches], operator_id=OPERATOR, reason="按计划",
    )
    assert await blocked_chains(db) == []


def test_plan_does_not_guess_survivor_on_tie() -> None:
    from app.services.audit_chain.forks import ChainRow

    root = ChainRow(uuid.uuid4(), "h0", GENESIS_HASH, T0, "a")
    left = ChainRow(uuid.uuid4(), "h1", "h0", T0 + timedelta(seconds=1), "b")
    right = ChainRow(uuid.uuid4(), "h2", "h0", T0 + timedelta(seconds=1), "c")
    plan = build_fork_plan("__global__", [root, left, right], set())
    assert plan.survivor_id is None and plan.ack_ids == ()


@pytest.mark.asyncio
async def test_verify_chain_can_target_global_without_mixing_a_project_chain(db: AsyncSession) -> None:
    """``project_id=None`` 原本代表全表，运维确认全局链时会混入项目链；新增 chain_key 精确取全局。"""
    global_row = _legacy(GENESIS_HASH, "global", 1)
    project_id = str(uuid.uuid4())
    project_root = _legacy(GENESIS_HASH, "project-root", 1, project_id=project_id)
    project_left = _legacy(project_root.entry_hash, "project-left", 2, project_id=project_id)
    project_right = _legacy(project_root.entry_hash, "project-right", 3, project_id=project_id)
    await _add(db, global_row, project_root, project_left, project_right)

    global_only = await verify_chain(db, chain_key="__global__")
    all_rows = await verify_chain(db)
    assert global_only.entries_checked == 1 and not any(p["type"] == "fork" for p in global_only.problems)
    assert any(p["type"] == "fork" for p in all_rows.problems)
    with pytest.raises(ValueError, match="不能同时"):
        await verify_chain(db, project_id=project_id, chain_key="__global__")
