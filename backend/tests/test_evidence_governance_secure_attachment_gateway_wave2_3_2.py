"""Task 3.2 (Wave 2) — SecureAttachmentGateway 上传审计优先接收：单元 + 真实 PG16 集成。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 3.2 (Wave 2)
Requirements: R1, R12
Design: §4.0 (UploadAttempt/失败审计/隔离区), §5.1 (流式上传与异步 finalize), §3.2 (Facade)
Properties: P1 (项目隔离), P3 (创建主体完备), P25 (command-root 唯一 + 同事务)

被测 API（``secure_attachment_gateway``）：
  * ``sanitize_upload_filename`` —— 文件名清洗（纯函数）。
  * ``SecureAttachmentGateway.begin_upload_attempt`` —— 内容验证 **之前** 持久最小
    ``UploadAttempt(pending)``（attempt-first）。
  * ``SecureAttachmentGateway.converge_upload_attempt`` —— 验证推进后 **更新同一 attempt**
    到 accepted|rejected|quarantined|failed（不另建匿名 attempt）。

覆盖：
  * 单元（纯函数，无 DB）：清洗 basename/穿越/控制字符/保留字符/空/超长。
  * 真实 PG16（throwaway 库，用完即 DROP）：
    - attempt 在验证前已持久（pending，detected/bytes/hash 为 NULL）；
    - converge 更新同一 attempt（不新建行）：单行 + outcome + failure_category + 回填元数据；
    - 清洗后的文件名入库（绝不写原始/绝对路径）；
    - actor XOR（user / service 两侧 FK 正确落列）；
    - outcome 生命周期 pending→{accepted,rejected,quarantined,failed} 全覆盖；
    - 非终态 converge → INVALID_STATE_TRANSITION；已收敛再 converge 幂等无副作用。

真实 PG 铁律（design §10.1/§10.2）：约束/并发/事务在真实 PG16 验证，无 PG 环境 skip。
全局 Hypothesis fast profile（conftest 注册）；本文件不固定 max_examples。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.secure_attachment_gateway import (
    SecureAttachmentGateway,
    UploadAttemptRecord,
    sanitize_upload_filename,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


# ===========================================================================
# 1) 单元（纯函数；无 DB）—— sanitize_upload_filename
# ===========================================================================


class TestSanitizeUploadFilename:
    def test_basename_strips_directory(self):
        assert sanitize_upload_filename("a/b/c/report.pdf") == "report.pdf"

    def test_windows_backslash_and_drive(self):
        assert sanitize_upload_filename(r"C:\Users\x\secret.xlsx") == "secret.xlsx"

    def test_path_traversal_reduced_to_basename(self):
        name = sanitize_upload_filename("../../../../etc/passwd/report.pdf")
        assert name == "report.pdf"
        assert "/" not in name and "\\" not in name

    def test_dotdot_and_empty_fall_back(self):
        for raw in ("", "   ", "..", ".", None):
            assert sanitize_upload_filename(raw) == "unnamed"

    def test_control_chars_stripped(self):
        name = sanitize_upload_filename("re\x00po\x1frt\x7f.pdf")
        assert "\x00" not in name and "\x1f" not in name and "\x7f" not in name

    def test_reserved_chars_replaced(self):
        name = sanitize_upload_filename('in:va*lid?.pdf')
        assert ":" not in name and "*" not in name and "?" not in name

    def test_never_absolute_path(self):
        for raw in ("/var/data/x.pdf", r"\\server\share\y.pdf"):
            name = sanitize_upload_filename(raw)
            assert not name.startswith("/") and "\\" not in name

    def test_truncated_keeps_extension(self):
        raw = "x" * 400 + ".pdf"
        name = sanitize_upload_filename(raw, max_length=64)
        assert len(name) <= 64
        assert name.endswith(".pdf")


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
    tmp_db = f"evgov_gw_{uuid.uuid4().hex[:12]}"

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


async def _seed(eng, *, member: bool = True):
    """seed user + project(+成员) + service_identity；返回 ids。"""
    from sqlalchemy import text as T

    ids = {"user": uuid.uuid4(), "project": uuid.uuid4(), "service": uuid.uuid4()}
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
        await conn.execute(
            T(
                "INSERT INTO service_identities (id, identity_key, display_name) "
                "VALUES (:i, :k, 'migration-worker')"
            ),
            {"i": ids["service"], "k": f"svc-{uuid.uuid4().hex[:8]}"},
        )
    return ids


def _sessionmaker(eng):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(eng, expire_on_commit=False)


async def _count(session, table, **filters) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters) or "true"
    row = await session.execute(
        sa.text(f"SELECT count(*) FROM {table} WHERE {where}"), filters
    )
    return row.scalar()


async def _fetch_attempt(session, attempt_id):
    row = await session.execute(
        sa.text(
            "SELECT project_id, audit_year, sanitized_file_name, declared_media_type, "
            "detected_media_type, received_byte_size, content_hash, "
            "validation_outcome, failure_category, actor_type, actor_user_id, "
            "actor_service_identity_id, command_root_id "
            "FROM evidence_upload_attempts WHERE id = :i"
        ),
        {"i": attempt_id},
    )
    return row.mappings().first()


async def _begin(gw, ids, *, actor=None, actor_role="auditor", raw_file_name="report.pdf",
                 declared="application/pdf", idem=None) -> UploadAttemptRecord:
    return await gw.begin_upload_attempt(
        project_id=ids["project"],
        audit_year=2025,
        raw_file_name=raw_file_name,
        declared_media_type=declared,
        actor=actor or ActorContext.for_user(ids["user"]),
        actor_role=actor_role,
        idempotency_key=idem or f"up-{uuid.uuid4().hex[:8]}",
    )


# --- attempt-first：验证前已持久 pending（R1.1）-------------------------------


@pytest.mark.asyncio
async def test_begin_persists_pending_attempt_before_validation():
    """begin 在任何内容验证前持久最小 pending attempt；detected/bytes/hash 为 NULL。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec = await _begin(gw, ids, idem="up-pending")
            assert rec.outcome == "pending"
            assert rec.replayed is False
        async with SM() as s2:
            assert await _count(s2, "evidence_upload_attempts") == 1
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "pending"
            assert att["sanitized_file_name"] == "report.pdf"
            assert att["declared_media_type"] == "application/pdf"
            # 验证尚未进行 → 内容派生字段仍为 NULL（design §4.0）
            assert att["detected_media_type"] is None
            assert att["received_byte_size"] is None
            assert att["content_hash"] is None
            assert att["command_root_id"] == rec.command_root_id
            # attempt-first command-root 存在（P25）
            assert await _count(s2, "evidence_audit_command_roots") == 1
            # 不创建可用 Attachment（本 slice 从不触碰 attachments）
            assert await _count(s2, "attachments") == 0


# --- converge 更新同一 attempt（不另建）-------------------------------------


@pytest.mark.asyncio
async def test_converge_updates_same_attempt_not_new_row():
    """验证推进后 converge 更新 **同一** attempt（单行）：outcome + failure_category + 回填元数据。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec = await _begin(gw, ids, idem="up-conv")
            done = await gw.converge_upload_attempt(
                attempt_id=rec.attempt_id,
                outcome="rejected",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                idempotency_key="up-conv",
                project_id=ids["project"],
                audit_year=2025,
                failure_category="media_type_mismatch",
                detected_media_type="image/png",
                received_byte_size=2048,
                content_hash="b" * 64,
            )
            assert done.outcome == "rejected"
        async with SM() as s2:
            # 仍是同一行（converge 更新，而非新建第二行）
            assert await _count(s2, "evidence_upload_attempts") == 1
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert att["failure_category"] == "media_type_mismatch"
            assert att["detected_media_type"] == "image/png"
            assert att["received_byte_size"] == 2048
            assert att["content_hash"] == "b" * 64


# --- 清洗后的文件名入库（绝不写原始/绝对路径）--------------------------------


@pytest.mark.asyncio
async def test_sanitized_file_name_never_stores_raw_path():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec = await _begin(
                gw, ids, raw_file_name="../../../../etc/passwd/report.pdf", idem="up-san"
            )
        async with SM() as s2:
            stored = (await _fetch_attempt(s2, rec.attempt_id))["sanitized_file_name"]
            assert stored == "report.pdf"
            assert "/" not in stored and "\\" not in stored and not stored.startswith("/")


# --- actor XOR（user / service）--------------------------------------------


@pytest.mark.asyncio
async def test_actor_xor_user_and_service():
    """actor XOR：user 落 actor_user_id、service 落 actor_service_identity_id（P3）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec_u = await _begin(gw, ids, idem="up-user")
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec_s = await _begin(
                gw,
                ids,
                actor=ActorContext.for_service(ids["service"]),
                actor_role="service",
                idem="up-svc",
            )
        async with SM() as s2:
            au = await _fetch_attempt(s2, rec_u.attempt_id)
            assert au["actor_type"] == "user"
            assert au["actor_user_id"] == ids["user"]
            assert au["actor_service_identity_id"] is None
            asr = await _fetch_attempt(s2, rec_s.attempt_id)
            assert asr["actor_type"] == "service"
            assert asr["actor_service_identity_id"] == ids["service"]
            assert asr["actor_user_id"] is None


# --- outcome 生命周期 pending→{accepted,rejected,quarantined,failed}----------


@pytest.mark.asyncio
async def test_outcome_lifecycle_all_four_terminals():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    cases = [
        ("accepted", None),
        ("rejected", "declared_type_not_allowed"),
        ("quarantined", "malware_detected"),
        ("failed", "finalize_failed"),
    ]
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        recs = []
        for outcome, cat in cases:
            async with SM() as session:
                gw = SecureAttachmentGateway(session)
                rec = await _begin(gw, ids, idem=f"life-{outcome}")
                assert rec.outcome == "pending"
                done = await gw.converge_upload_attempt(
                    attempt_id=rec.attempt_id,
                    outcome=outcome,
                    actor=ActorContext.for_user(ids["user"]),
                    actor_role="auditor",
                    idempotency_key=f"life-{outcome}",
                    project_id=ids["project"],
                    audit_year=2025,
                    failure_category=cat,
                )
                assert done.outcome == outcome
                recs.append((rec.attempt_id, outcome, cat))
        async with SM() as s2:
            # 四次尝试 → 四行；无 pending 残留
            assert await _count(s2, "evidence_upload_attempts") == 4
            assert await _count(s2, "evidence_upload_attempts", validation_outcome="pending") == 0
            for attempt_id, outcome, cat in recs:
                att = await _fetch_attempt(s2, attempt_id)
                assert att["validation_outcome"] == outcome
                assert att["failure_category"] == cat


# --- 非终态 converge 拒绝 -----------------------------------------------------


@pytest.mark.asyncio
async def test_converge_non_terminal_rejected():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec = await _begin(gw, ids, idem="up-bad")
            with pytest.raises(EvidenceGovernanceError) as ei:
                await gw.converge_upload_attempt(
                    attempt_id=rec.attempt_id,
                    outcome="pending",  # 非终态
                    actor=ActorContext.for_user(ids["user"]),
                    actor_role="auditor",
                    idempotency_key="up-bad",
                    project_id=ids["project"],
                    audit_year=2025,
                )
            assert ei.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "pending"  # 未被改动


# --- 已收敛再 converge 幂等无副作用 ------------------------------------------


@pytest.mark.asyncio
async def test_converge_replay_idempotent_no_side_effect():
    """同一 converge 幂等键重放：单 converge command-root，outcome 保持不变。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            rec = await _begin(gw, ids, idem="up-idem")
            first = await gw.converge_upload_attempt(
                attempt_id=rec.attempt_id,
                outcome="accepted",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                idempotency_key="up-idem",
                project_id=ids["project"],
                audit_year=2025,
            )
            assert first.replayed is False
        async with SM() as session:
            gw = SecureAttachmentGateway(session)
            second = await gw.converge_upload_attempt(
                attempt_id=rec.attempt_id,
                outcome="accepted",
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                idempotency_key="up-idem",
                project_id=ids["project"],
                audit_year=2025,
            )
            assert second.replayed is True
            assert second.outcome == "accepted"
        async with SM() as s2:
            assert await _count(s2, "evidence_upload_attempts") == 1
            # converge 命令根唯一（begin:attempt + converge:converge = 2 个不同命令根）
            assert await _count(
                s2, "evidence_audit_command_roots", command_type="attachment.upload.converge"
            ) == 1
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "accepted"
