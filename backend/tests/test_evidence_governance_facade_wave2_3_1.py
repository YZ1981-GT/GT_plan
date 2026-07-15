"""Task 3.1 (Wave 2) — EvidenceGovernanceFacade / ProjectYearScopeGuard /
CapabilityGuard / command-root·outbox·inbox 单元 + 真实 PG16 集成测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 3.1 (Wave 2)
Requirements: R1, R3, R4, R5, R8, R12
Design: §3.1 信任边界, §3.2 统一 Facade 与服务职责, §7.1 command-root, §7.2 稳定失败类别
Properties: P1 (项目隔离), P25 (command-root 唯一 + 同事务)

覆盖：
  * 单元（纯函数，无 DB）：CapabilityGuard 矩阵/service 禁令/admin 不绕过/ocr.retry/legal hold；
    脱敏 redact_audit_metadata；有界抖动 compute_backoff；derive_event_id 确定性。
  * 真实 PG16（throwaway 库，用完即 DROP）：
    - P25 command-root 唯一（重复/重放不重复 root，success/reject 各恰一 root）；
    - 事务原子性（成功：业务+审计+outbox 同提交；拒绝：业务回滚、root+reject 保留、目标零变化）；
    - 脱敏错误（跨项目对象访问 → SCOPE_NOT_FOUND_OR_FORBIDDEN，guard 先于业务、无 root）；
    - capability/scope 拒绝零副作用。

真实 PG 铁律（design §10.1/§10.2）：约束/并发/事务在真实 PG16 验证，无 PG 环境 skip。
全局 Hypothesis fast profile（conftest 注册）。
"""

from __future__ import annotations

import random
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.capability_guard import CapabilityGuard
from app.services.evidence_governance.command_audit import (
    compute_backoff,
    next_attempt_at,
    redact_audit_metadata,
)
from app.services.evidence_governance.facade import (
    CommandRequest,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.outbox import derive_event_id

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


# ===========================================================================
# 1) 单元（纯函数；无 DB）
# ===========================================================================


class TestCapabilityGuard:
    def setup_method(self):
        self.g = CapabilityGuard()

    def test_matrix_authoritative_auditor_ocr_retry_denied(self):
        # auditor 的 ocr.retry 基线默认禁（design §2.2）。
        assert self.g.is_authorized("auditor", "ocr.retry") is False
        with pytest.raises(EvidenceGovernanceError) as ei:
            self.g.authorize("auditor", "ocr.retry")
        assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

    def test_manager_partner_admin_ocr_retry_allowed(self):
        for role in ("manager", "partner", "admin"):
            assert self.g.is_authorized(role, "ocr.retry") is True

    def test_service_forbidden_human_actions(self):
        svc = ActorContext.for_service(uuid.uuid4())
        for cap in ("ocr.confirm", "ai.confirm", "review.close", "legal_hold.release",
                    "qc.complete", "eqcr.complete", "signoff"):
            assert self.g.is_authorized("service", cap, actor=svc) is False

    def test_admin_cannot_bypass_human_confirm_for_service_actor(self):
        # 即便传入 admin role，service actor 也强制走 service 行（人工确认恒禁）。
        svc = ActorContext.for_service(uuid.uuid4())
        assert self.g.is_authorized("admin", "ocr.confirm", actor=svc) is False

    def test_admin_conditional_confirm_permitted_for_user(self):
        user = ActorContext.for_user(uuid.uuid4())
        # admin ocr.confirm 是 conditional（有目标编辑权时）→ is_permitted True（非 bypass）。
        assert self.g.is_authorized("admin", "ocr.confirm", actor=user) is True

    def test_readonly_denied_everything(self):
        for cap in ("attachment.create", "ocr.start", "ai.generate", "evidence_ref.create"):
            assert self.g.is_authorized("readonly", cap) is False

    def test_legal_hold_destructive_zero_effect_all_actors(self):
        for role in ("admin", "partner", "manager", "service"):
            for op in ("delete", "purge", "overwrite"):
                with pytest.raises(EvidenceGovernanceError) as ei:
                    self.g.authorize_destructive_under_hold(role, op, hold_active=True)
                assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE

    def test_legal_hold_inactive_allows(self):
        # hold 未生效时不拦截（非破坏性/无 hold）。
        self.g.authorize_destructive_under_hold("admin", "delete", hold_active=False)


class TestRedaction:
    def test_strips_credentials_and_paths_and_raw(self):
        meta = {
            "password": "hunter2",
            "authorization": "Bearer xyz",
            "file_path": "/var/data/secret.pdf",
            "storage_key": "paperless://123",
            "raw_text": "机密全文",
            "attachment_version_id": "abc",
            "content_hash": "a" * 64,
            "action": "confirm",
            "nested": {"api_key": "k", "kept": "v", "win_path": "C:\\secret\\a.pdf"},
            "list": [{"token": "t"}, "ok"],
        }
        out = redact_audit_metadata(meta)
        assert out["password"] == "[redacted]"
        assert out["authorization"] == "[redacted]"
        assert out["file_path"] == "[redacted]"
        assert out["storage_key"] == "[redacted]"
        assert out["raw_text"] == "[redacted]"
        # 保留非敏感 id/hash/action
        assert out["attachment_version_id"] == "abc"
        assert out["content_hash"] == "a" * 64
        assert out["action"] == "confirm"
        # 嵌套：键名命中丢弃，绝对路径值脱敏
        assert out["nested"]["api_key"] == "[redacted]"
        assert out["nested"]["kept"] == "v"
        assert out["nested"]["win_path"] == "[redacted]"
        assert out["list"][0]["token"] == "[redacted]"
        assert out["list"][1] == "ok"

    def test_empty(self):
        assert redact_audit_metadata(None) == {}
        assert redact_audit_metadata({}) == {}


class TestBackoff:
    def test_bounded_within_cap(self):
        rng = random.Random(42)
        for attempt in range(1, 20):
            d = compute_backoff(attempt, base_seconds=1.0, cap_seconds=60.0, rng=rng)
            assert 0.0 <= d <= 60.0

    def test_grows_then_caps(self):
        # 无抖动（jitter_ratio=0）时严格单调至 cap。
        d1 = compute_backoff(1, base_seconds=1, cap_seconds=100, jitter_ratio=0.0)
        d3 = compute_backoff(3, base_seconds=1, cap_seconds=100, jitter_ratio=0.0)
        d10 = compute_backoff(10, base_seconds=1, cap_seconds=100, jitter_ratio=0.0)
        assert d1 == 1.0
        assert d3 == 4.0
        assert d10 == 100.0  # capped

    def test_next_attempt_at_future(self):
        from datetime import datetime, timezone
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        nxt = next_attempt_at(2, now=now, jitter_ratio=0.0)
        assert nxt > now


class TestDeriveEventId:
    def test_deterministic(self):
        root = uuid.uuid4()
        a = derive_event_id(command_root_id=root, event_type="attachment.created", seq=0)
        b = derive_event_id(command_root_id=root, event_type="attachment.created", seq=0)
        assert a == b and len(a) <= 120

    def test_distinct_by_seq_and_type(self):
        root = uuid.uuid4()
        assert derive_event_id(command_root_id=root, event_type="x", seq=0) != \
            derive_event_id(command_root_id=root, event_type="x", seq=1)
        assert derive_event_id(command_root_id=root, event_type="x", seq=0) != \
            derive_event_id(command_root_id=root, event_type="y", seq=0)


# ===========================================================================
# 2) 真实 PG16 集成（throwaway 库，用完即 DROP；非 PG 环境 skip）
# ===========================================================================

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
    tmp_db = f"evgov_facade_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca)
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
        admin = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca)
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')
        await admin.dispose()


async def _seed(eng, *, member: bool = True):
    """seed user + project(+成员)；返回 ids。"""
    from sqlalchemy import text as T
    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        if member:
            await conn.execute(
                T("INSERT INTO project_users (project_id, user_id) VALUES (:p, :u)"),
                {"p": ids["project"], "u": ids["user"]},
            )
    return ids


def _sessionmaker(eng):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    return async_sessionmaker(eng, expire_on_commit=False)


async def _count(session, table, **filters) -> int:
    import sqlalchemy as sa
    where = " AND ".join(f"{k} = :{k}" for k in filters) or "true"
    row = await session.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {where}"), filters)
    return row.scalar()


def _insert_attachment_business(project_id, user_id, *, reject=False):
    """返回一个 business_fn：插入 attachment（业务变化）+ enqueue outbox；reject 时抛拒绝。"""
    import sqlalchemy as sa
    att_id = uuid.uuid4()

    async def business(txn):
        await txn.db.execute(
            sa.text(
                "INSERT INTO attachments (id, project_id, file_name, file_type, file_size,"
                " state, actor_type, actor_user_id) "
                "VALUES (:a, :p, 'f.pdf', 'pdf', 10, 'available', 'user', :u)"
            ),
            {"a": att_id, "p": project_id, "u": user_id},
        )
        await txn.db.flush()
        await txn.enqueue_outbox("attachment.created", {"attachment_id": str(att_id)})
        if reject:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE, "missing evidence metadata"
            )
        return {"attachment_id": str(att_id)}

    return business, att_id


@pytest.mark.asyncio
async def test_facade_success_atomic_commit_business_audit_outbox():
    """成功：业务变化 + command-root + success transition + outbox 同事务提交。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)
            business, att_id = _insert_attachment_business(ids["project"], ids["user"])
            req = CommandRequest(
                command_type="attachment.create",
                idempotency_key="idem-success-1",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                project_id=ids["project"],
                audit_year=2025,
                capability="attachment.create",
            )
            res = await facade.execute(req, business)
            assert res.replayed is False
            assert res.result["attachment_id"] == str(att_id)

        # 全部落库：1 attachment + 1 command-root(success) + >=1 transition + 1 outbox
        async with SM() as s2:
            assert await _count(s2, "attachments", id=att_id) == 1
            assert await _count(s2, "evidence_audit_command_roots") == 1
            assert await _count(s2, "evidence_audit_command_roots", result="success") == 1
            assert await _count(s2, "evidence_outbox") == 1
            assert await _count(s2, "evidence_audit_transitions") >= 1


@pytest.mark.asyncio
async def test_facade_reject_rolls_back_business_keeps_root_and_reject_transition():
    """拒绝：业务回滚（目标零变化），保留恰一 command-root(rejected) + reject transition，无 outbox。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)
            business, att_id = _insert_attachment_business(ids["project"], ids["user"], reject=True)
            req = CommandRequest(
                command_type="attachment.create",
                idempotency_key="idem-reject-1",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                project_id=ids["project"],
                audit_year=2025,
                capability="attachment.create",
            )
            with pytest.raises(EvidenceGovernanceError) as ei:
                await facade.execute(req, business)
            assert ei.value.error_code == EvidenceErrorCode.METADATA_INCOMPLETE

        async with SM() as s2:
            # 目标零变化：业务 attachment 未落库；outbox 未产生
            assert await _count(s2, "attachments", id=att_id) == 0
            assert await _count(s2, "evidence_outbox") == 0
            # 恰一个 command-root，result=rejected + reason_code
            assert await _count(s2, "evidence_audit_command_roots") == 1
            import sqlalchemy as sa
            row = (await s2.execute(sa.text(
                "SELECT result, reason_code FROM evidence_audit_command_roots"
            ))).first()
            assert row.result == "rejected"
            assert row.reason_code == EvidenceErrorCode.METADATA_INCOMPLETE.value
            # reject transition 存在
            assert await _count(s2, "evidence_audit_transitions", transition_type="reject") == 1


@pytest.mark.asyncio
async def test_facade_duplicate_and_replay_single_command_root_p25():
    """P25：同一幂等键重复/重放只保留一个 command-root，业务只执行一次。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)
            b1, att1 = _insert_attachment_business(ids["project"], ids["user"])
            req = CommandRequest(
                command_type="attachment.create",
                idempotency_key="idem-dup",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                project_id=ids["project"],
                audit_year=2025,
                capability="attachment.create",
            )
            res1 = await facade.execute(req, b1)
            assert res1.replayed is False

            # 重放：相同幂等键，业务回调重新构造（新 att id），但不应执行
            b2, att2 = _insert_attachment_business(ids["project"], ids["user"])
            res2 = await facade.execute(req, b2)
            assert res2.replayed is True
            assert res2.command_root_id == res1.command_root_id

        async with SM() as s2:
            assert await _count(s2, "evidence_audit_command_roots") == 1  # 唯一 root
            assert await _count(s2, "attachments", id=att1) == 1
            assert await _count(s2, "attachments", id=att2) == 0  # 重放未执行业务
            assert await _count(s2, "evidence_outbox") == 1  # outbox 不重复


@pytest.mark.asyncio
async def test_facade_cross_project_object_redacted_denial_no_root():
    """脱敏项目隔离（P1）：请求 scope 与对象权威归属不一致 → SCOPE_NOT_FOUND_OR_FORBIDDEN，
    guard 先于业务，无 command-root、无业务副作用。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    import sqlalchemy as sa
    async with _throwaway_engine() as eng:
        a = await _seed(eng)                 # project A（用户是成员）
        b = await _seed(eng)                 # project B
        # 在 project B 建一个 attachment
        obj_id = uuid.uuid4()
        async with eng.begin() as conn:
            await conn.execute(sa.text(
                "INSERT INTO attachments (id, project_id, file_name, state, actor_type, actor_user_id) "
                "VALUES (:i, :p, 'b.pdf', 'available', 'user', :u)"
            ), {"i": obj_id, "p": b["project"], "u": b["user"]})

        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)

            async def business(txn):  # 不应被调用
                raise AssertionError("business must not run when scope denied")

            req = CommandRequest(
                command_type="attachment.replace",
                idempotency_key="idem-cross",
                actor=ActorContext.for_user(a["user"]),
                actor_role="auditor",
                project_id=a["project"],        # 声明 A，但对象属于 B
                audit_year=2025,
                capability="attachment.replace",
                object_type="attachment",
                object_id=obj_id,
            )
            with pytest.raises(EvidenceGovernanceError) as ei:
                await facade.execute(req, business)
            assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

        async with SM() as s2:
            assert await _count(s2, "evidence_audit_command_roots") == 0  # guard 先于 root


@pytest.mark.asyncio
async def test_facade_capability_denied_no_side_effect():
    """capability 拒绝：auditor 无 ocr.retry → 拒绝且无 command-root、无业务副作用。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)

            async def business(txn):
                raise AssertionError("business must not run when capability denied")

            req = CommandRequest(
                command_type="ocr.retry",
                idempotency_key="idem-cap",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                project_id=ids["project"],
                audit_year=2025,
                capability="ocr.retry",
            )
            with pytest.raises(EvidenceGovernanceError) as ei:
                await facade.execute(req, business)
            assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

        async with SM() as s2:
            assert await _count(s2, "evidence_audit_command_roots") == 0


@pytest.mark.asyncio
async def test_facade_scope_non_member_denied():
    """scope 拒绝：非项目成员 auditor → SCOPE_NOT_FOUND_OR_FORBIDDEN，无副作用。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng, member=False)   # 用户不是项目成员
        SM = _sessionmaker(eng)
        async with SM() as session:
            facade = EvidenceGovernanceFacade(session)

            async def business(txn):
                raise AssertionError("must not run")

            req = CommandRequest(
                command_type="attachment.create",
                idempotency_key="idem-nonmember",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                project_id=ids["project"],
                audit_year=2025,
                capability="attachment.create",
            )
            with pytest.raises(EvidenceGovernanceError) as ei:
                await facade.execute(req, business)
            assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

        async with SM() as s2:
            assert await _count(s2, "evidence_audit_command_roots") == 0


@pytest.mark.asyncio
async def test_inbox_idempotent_consume():
    """inbox：按 event_id 幂等消费，重复 register 只首次返回 True。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from app.services.evidence_governance.outbox import InboxService
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            inbox = InboxService(session)
            actor = ActorContext.for_user(ids["user"])
            first = await inbox.register(
                project_id=ids["project"], audit_year=2025,
                event_id="evt-1", event_type="stale.propagate", actor=actor,
            )
            second = await inbox.register(
                project_id=ids["project"], audit_year=2025,
                event_id="evt-1", event_type="stale.propagate", actor=actor,
            )
            await session.commit()
            assert first is True
            assert second is False
            assert await inbox.is_processed("evt-1") is False
            await inbox.mark_processed("evt-1")
            await session.commit()
            assert await inbox.is_processed("evt-1") is True
