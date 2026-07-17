"""Task 8.3 (Wave 7) — Evidence outbox worker crash / dead-letter gap coverage.

Spec: attachment-ocr-ai-evidence-governance-hardening
Task: 8.3 (汇总后端测试 — 覆盖 worker crash/dead-letter 维度)
Requirements: R12, R15
Design: §3.1 (事务性 outbox + worker), §5.4 (pending/dead-letter → governance_degraded)
Properties: P25 (审计事件覆盖 / 幂等 dispatch), P29 (降级安全)

Gap rationale (Task 8.3 aggregation):
  The Wave-2 facade suite (``test_evidence_governance_facade_wave2_3_1.py``)
  covers outbox ``enqueue`` idempotency and inbox idempotent consume, but the
  outbox **worker** paths — ``claim_pending`` (``FOR UPDATE SKIP LOCKED``) and
  ``mark_failed`` → bounded retry → ``dead_letter`` — had no direct test. This
  file fills exactly that gap; it does not duplicate existing coverage.

真实 PG16 铁律（design §10.1/§10.2）：SKIP LOCKED、并发 claim、退避/dead-letter 状态
迁移必须在真实 PostgreSQL 16 验证；无 PG 环境 skip。使用 throwaway 库，用完即 DROP。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.frozen_contracts import ActorContext
from app.services.evidence_governance.outbox import OutboxService

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"

_STUB_PARENTS_SQL = """
CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE projects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_year int, audit_period_end date, audit_period_start date,
    is_deleted boolean DEFAULT false);
CREATE TABLE project_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL, user_id uuid NOT NULL,
    is_deleted boolean DEFAULT false
);
CREATE TABLE ai_content_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid);
CREATE TABLE attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    file_name varchar(500), file_path varchar(1000),
    file_type varchar(100), file_size bigint,
    ocr_status varchar(20), version int, previous_version_id uuid,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false
);
"""


def _pg_available() -> bool:
    from app.core.config import settings

    return settings.DATABASE_URL.startswith("postgresql")


def _base_url():
    from app.core.config import settings

    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args():
    from app.core.config import settings

    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


def _split(sql: str) -> list[str]:
    return MigrationRunner._split_sql_statements(sql)


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_outbox83_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            for s in _STUB_PARENTS_SQL.strip().split(";"):
                if s.strip():
                    await conn.exec_driver_sql(s)
        for f in (V106, V107, V108):
            for s in _split(f.read_text(encoding="utf-8")):
                async with eng.begin() as conn:
                    await conn.exec_driver_sql(s)
        yield eng
    finally:
        await eng.dispose()
        admin = create_async_engine(
            admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
        )
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')
        await admin.dispose()


def _sessionmaker(eng):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(eng, expire_on_commit=False)


async def _seed(eng):
    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            sa.text("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            sa.text("INSERT INTO project_users (project_id, user_id) VALUES (:p, :u)"),
            {"p": ids["project"], "u": ids["user"]},
        )
    return ids


async def _enqueue(session, ids, actor, *, event_id: str, event_type: str = "attachment.created"):
    svc = OutboxService(session)
    return await svc.enqueue(
        project_id=ids["project"],
        audit_year=2025,
        event_id=event_id,
        event_type=event_type,
        payload={"note": "x"},
        actor=actor,
    )


# ───────────────────────────────────────────────────────────────────────────
# 1) claim_pending — FOR UPDATE SKIP LOCKED: concurrent workers never double-claim
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_pending_skip_locked_no_double_claim():
    """两个并发 worker 同时 claim：被 A 锁住的行被 B SKIP，不发生双认领。

    模拟 worker 崩溃/并发场景：A 在事务内 claim 并持锁（未提交），B 的 claim 必须
    跳过被锁行（SKIP LOCKED），只取到剩余行。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        actor = ActorContext.for_user(ids["user"])
        SM = _sessionmaker(eng)

        # 入队两行 pending
        async with SM() as s:
            await _enqueue(s, ids, actor, event_id="evt-a")
            await _enqueue(s, ids, actor, event_id="evt-b")
            await s.commit()

        # A：claim 1 行并保持事务打开（持锁）
        sA = SM()
        try:
            a_rows = await OutboxService(sA).claim_pending(limit=1)
            assert len(a_rows) == 1
            a_id = a_rows[0].id

            # B：另一事务 claim，SKIP LOCKED → 只能拿到未被锁的另一行
            async with SM() as sB:
                b_rows = await OutboxService(sB).claim_pending(limit=10)
                b_ids = {r.id for r in b_rows}
                assert a_id not in b_ids, "被 A 锁住的行不得被 B 认领（SKIP LOCKED 违约）"
                assert len(b_rows) == 1
                await sB.rollback()
        finally:
            await sA.rollback()
            await sA.close()


# ───────────────────────────────────────────────────────────────────────────
# 2) mark_failed — bounded retry below max → back to pending with backoff
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_reschedules_below_max():
    """未达上限：mark_failed → attempt+1、回 pending、设置未来 next_attempt_at（有界退避）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        actor = ActorContext.for_user(ids["user"])
        SM = _sessionmaker(eng)

        async with SM() as s:
            await _enqueue(s, ids, actor, event_id="evt-fail-1")
            await s.commit()

        async with SM() as s:
            svc = OutboxService(s)
            rows = await svc.claim_pending(limit=1)
            assert len(rows) == 1
            row = rows[0]
            new_state = await svc.mark_failed(row, max_attempts=8)
            await s.commit()
            assert new_state == "pending"
            assert row.attempt_count == 1
            assert row.next_attempt_at is not None
            assert row.next_attempt_at > datetime.now(timezone.utc)


# ───────────────────────────────────────────────────────────────────────────
# 3) mark_failed — reaching max_attempts parks message in dead_letter
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_dead_letter_at_max():
    """达到 max_attempts：mark_failed → 进入 dead_letter（毒消息停靠，不再无限重试）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        actor = ActorContext.for_user(ids["user"])
        SM = _sessionmaker(eng)

        async with SM() as s:
            await _enqueue(s, ids, actor, event_id="evt-dl")
            await s.commit()

        async with SM() as s:
            svc = OutboxService(s)
            rows = await svc.claim_pending(limit=1)
            row = rows[0]
            # max_attempts=3：前两次回 pending，第三次进 dead_letter
            st1 = await svc.mark_failed(row, max_attempts=3)
            assert st1 == "pending" and row.attempt_count == 1
            st2 = await svc.mark_failed(row, max_attempts=3)
            assert st2 == "pending" and row.attempt_count == 2
            st3 = await svc.mark_failed(row, max_attempts=3)
            assert st3 == "dead_letter" and row.attempt_count == 3
            await s.commit()

        # 复核：DB 持久化为 dead_letter
        async with SM() as s:
            state = (
                await s.execute(
                    sa.text("SELECT status FROM evidence_outbox WHERE event_id='evt-dl'")
                )
            ).scalar_one()
            assert state == "dead_letter"


# ───────────────────────────────────────────────────────────────────────────
# 4) claim_pending — honors next_attempt_at backoff (not-yet-due rows skipped)
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_pending_respects_backoff_window():
    """退避窗口内（next_attempt_at 在未来）的 pending 行不被 claim；到期行才被认领。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        actor = ActorContext.for_user(ids["user"])
        SM = _sessionmaker(eng)

        async with SM() as s:
            await _enqueue(s, ids, actor, event_id="evt-due")
            await _enqueue(s, ids, actor, event_id="evt-future")
            # evt-future 设未来退避窗口
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            await s.execute(
                sa.text(
                    "UPDATE evidence_outbox SET next_attempt_at=:t WHERE event_id='evt-future'"
                ),
                {"t": future},
            )
            await s.commit()

        async with SM() as s:
            rows = await OutboxService(s).claim_pending(limit=10)
            claimed = {r.event_id for r in rows}
            assert "evt-due" in claimed
            assert "evt-future" not in claimed, "退避窗口内的行不得被认领"
            await s.rollback()


@pytest.mark.asyncio
async def test_mark_done_terminal():
    """mark_done → status=done（终态，不再被 claim）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        actor = ActorContext.for_user(ids["user"])
        SM = _sessionmaker(eng)

        async with SM() as s:
            await _enqueue(s, ids, actor, event_id="evt-done")
            await s.commit()

        async with SM() as s:
            svc = OutboxService(s)
            rows = await svc.claim_pending(limit=1)
            await svc.mark_done(rows[0])
            await s.commit()

        async with SM() as s:
            rows = await OutboxService(s).claim_pending(limit=10)
            assert rows == []
