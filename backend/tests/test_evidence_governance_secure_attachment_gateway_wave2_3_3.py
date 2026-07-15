"""Task 3.3 (Wave 2) — 固定块流式接收 / 背压 / staged→finalize：单元 + 真实 PG16 集成。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 3.3 (Wave 2)
Requirements: R1, R2, R15
Design: §4.0 (quarantine/staging), §5.1 (流式上传与异步 finalize), §9.1/§9.2 (SLO/背压)
Properties: P2 (存储边界), P4 (版本不可变), P5 (哈希绑定), P29 (降级安全)

被测 API（``secure_attachment_gateway``）：
  * ``sniff_media_type`` / ``media_types_compatible`` —— magic 嗅探与声明一致性（纯函数）。
  * ``SecureAttachmentGateway._stream_to_quarantine`` —— 固定块流式：增量 SHA-256 /
    magic 嗅探 / 累加字节 / 大小 / 背压（内存字节流，无 DB）。
  * ``SecureAttachmentGateway.receive_upload`` —— begin → 流式 → staged → finalize/202 → converge。
  * ``SecureAttachmentGateway.finalize_staged_upload`` —— 异步 finalize worker 路径。

覆盖：
  * 单元（纯函数/流式，无 DB）：嗅探、一致性、流式 hash 正确性、大小/空/背压/mismatch 拒绝。
  * 真实 PG16（throwaway 库，用完即 DROP）：
    - staged→available happy path（201）：Attachment.state/version.availability/current + attempt=accepted；
    - 大小/MIME/空拒绝：收敛同一 attempt=rejected，且无 available Attachment/Version；
    - 恶意内容：quarantine handle=quarantined+purged_at，加密擦除不可读，无 available Attachment/Version；
    - 背压 429：CAPACITY_BACKPRESSURE，无 Attachment/Version；
    - 异步 202 staged + finalize_staged_upload → available；staged 内容不可被引用（非 available）。

真实 PG 铁律（design §10.1/§10.2）：约束/触发器/事务在真实 PG16 验证，无 PG 环境 skip。
全局 Hypothesis fast profile（conftest）；本文件不固定 max_examples。
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
)
from app.services.evidence_governance.secure_attachment_gateway import (
    FAILURE_BACKPRESSURE,
    FAILURE_EMPTY,
    FAILURE_MALWARE,
    FAILURE_TOO_LARGE,
    FAILURE_TYPE_MISMATCH,
    InMemoryQuarantineStore,
    SecureAttachmentGateway,
    media_types_compatible,
    sniff_media_type,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"

# 常见 magic 内容前缀。
_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
_ZIP = b"PK\x03\x04\x14\x00"


def _chunks(data: bytes, block: int = 7):
    """把字节切成小块的同步生成器（触发固定块重切逻辑）。"""
    for i in range(0, len(data), block):
        yield data[i : i + block]


# ===========================================================================
# 1) 单元（纯函数；无 DB）—— 嗅探 / 一致性
# ===========================================================================


class TestSniffAndCompat:
    def test_sniff_known_types(self):
        assert sniff_media_type(_PDF) == "application/pdf"
        assert sniff_media_type(_PNG) == "image/png"
        assert sniff_media_type(_JPEG) == "image/jpeg"
        assert sniff_media_type(_ZIP) == "application/zip"

    def test_sniff_unknown_and_empty(self):
        assert sniff_media_type(b"not-a-known-magic-header") is None
        assert sniff_media_type(b"") is None
        assert sniff_media_type(None) is None

    def test_compat_matching_and_mismatch(self):
        assert media_types_compatible("application/pdf", "application/pdf") is True
        # 声明 pdf 却识别为 png → 不一致
        assert media_types_compatible("application/pdf", "image/png") is False
        # docx 声明 → zip 家族一致
        assert (
            media_types_compatible(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/zip",
            )
            is True
        )

    def test_compat_unknown_detected_is_lenient(self):
        # 无法识别实际类型 → 不据此判定不一致
        assert media_types_compatible("application/pdf", None) is True

    def test_compat_unregistered_declared_is_lenient(self):
        # 未登记映射的声明类型（纯文本）→ 从宽
        assert media_types_compatible("text/plain", "application/pdf") is True


# ===========================================================================
# 2) 单元（流式；无 DB）—— _stream_to_quarantine
# ===========================================================================


class TestStreamingNoDB:
    def _gw(self, **kw):
        # db=None：_stream_to_quarantine 不触碰 DB。
        return SecureAttachmentGateway(None, **kw)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_stream_hash_correctness(self):
        content = _PDF + b"x" * 5000
        gw = self._gw(chunk_size=13)
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(content, 7),
            declared_media_type="application/pdf",
        )
        assert res.ok
        assert res.received_byte_size == len(content)
        assert res.content_hash == hashlib.sha256(content).hexdigest()
        assert res.detected_media_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_stream_empty_rejected(self):
        gw = self._gw()
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(b"", 7), declared_media_type=None
        )
        assert not res.ok
        assert res.error_code == EvidenceErrorCode.METADATA_INCOMPLETE
        assert res.failure_category == FAILURE_EMPTY

    @pytest.mark.asyncio
    async def test_stream_too_large_rejected(self):
        gw = self._gw(max_upload_bytes=100, chunk_size=16)
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(_PDF + b"y" * 500, 16),
            declared_media_type="application/pdf",
        )
        assert not res.ok
        assert res.error_code == EvidenceErrorCode.ATTACHMENT_TOO_LARGE
        assert res.failure_category == FAILURE_TOO_LARGE

    @pytest.mark.asyncio
    async def test_stream_mime_mismatch_rejected(self):
        # 声明 pdf，实际 png 内容 → MEDIA_TYPE_MISMATCH
        gw = self._gw(chunk_size=16)
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(_PNG + b"z" * 100, 16),
            declared_media_type="application/pdf",
        )
        assert not res.ok
        assert res.error_code == EvidenceErrorCode.MEDIA_TYPE_MISMATCH
        assert res.failure_category == FAILURE_TYPE_MISMATCH

    @pytest.mark.asyncio
    async def test_stream_backpressure_high_water(self):
        # 高水位很低 + 大流 → CAPACITY_BACKPRESSURE（不无限缓存）
        gw = self._gw(quarantine_high_water_bytes=64, chunk_size=16, max_upload_bytes=10_000)
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(_PDF + b"a" * 2000, 16),
            declared_media_type="application/pdf",
        )
        assert not res.ok
        assert res.error_code == EvidenceErrorCode.CAPACITY_BACKPRESSURE
        assert res.failure_category == FAILURE_BACKPRESSURE

    @pytest.mark.asyncio
    async def test_stream_purge_crypto_erases(self):
        store = InMemoryQuarantineStore()
        gw = self._gw(quarantine_store=store, chunk_size=16)
        res = await gw._stream_to_quarantine(
            attempt_id=uuid.uuid4(), chunks=_chunks(_PDF + b"secret" * 50, 16),
            declared_media_type="application/pdf",
        )
        assert store.exists(res.quarantine_key)
        store.purge(res.quarantine_key, crypto_erase=True)
        assert not store.exists(res.quarantine_key)


# ===========================================================================
# 3) 真实 PG16 集成
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
    attachment_type varchar(50) DEFAULT 'general',
    reference_id uuid, reference_type varchar(50),
    storage_type varchar(20), paperless_document_id int,
    ocr_status varchar(20), ocr_text text, ocr_fields_cache json,
    version int DEFAULT 1, previous_version_id uuid,
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
    tmp_db = f"evgov_gw33_{uuid.uuid4().hex[:12]}"

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


async def _seed(eng):
    from sqlalchemy import text as T

    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            T("INSERT INTO project_users (project_id, user_id) VALUES (:p, :u)"),
            {"p": ids["project"], "u": ids["user"]},
        )
    return ids


def _sessionmaker(eng):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(eng, expire_on_commit=False)


async def _count(session, table, **filters) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters) or "true"
    row = await session.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {where}"), filters)
    return row.scalar()


async def _fetch_attempt(session, attempt_id):
    row = await session.execute(
        sa.text(
            "SELECT validation_outcome, failure_category, detected_media_type, "
            "received_byte_size, content_hash FROM evidence_upload_attempts WHERE id = :i"
        ),
        {"i": attempt_id},
    )
    return row.mappings().first()


async def _fake_finalizer(*, project_id, file_name, content, media_type):
    """finalize 存储委托的注入 fake（不触碰真实 FS/Paperless）。"""
    loc = f"evidence://{uuid.uuid4()}"
    return {"storage_type": "local", "storage_key": loc, "file_path": loc}


def _actor(ids):
    return ActorContext.for_user(ids["user"])


async def _receive(gw, ids, *, content, declared="application/pdf", idem=None,
                   synchronous_finalize=True, raw_file_name="report.pdf"):
    return await gw.receive_upload(
        project_id=ids["project"],
        audit_year=2025,
        raw_file_name=raw_file_name,
        declared_media_type=declared,
        chunks=_chunks(content, 16),
        actor=_actor(ids),
        actor_role="auditor",
        idempotency_key=idem or f"up-{uuid.uuid4().hex[:8]}",
        synchronous_finalize=synchronous_finalize,
    )


# --- staged→available happy path（201）--------------------------------------


@pytest.mark.asyncio
async def test_staged_to_available_happy_path():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    content = _PDF + b"h" * 3000
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session, storage_finalizer=_fake_finalizer, chunk_size=64)
            rec = await _receive(gw, ids, content=content, idem="happy")
            assert rec.outcome == "accepted"
            assert rec.response_mode == 201
            assert rec.availability == "available"
            assert rec.content_hash == hashlib.sha256(content).hexdigest()
        async with SM() as s2:
            # attempt=accepted 且回填元数据
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "accepted"
            assert att["content_hash"] == hashlib.sha256(content).hexdigest()
            assert att["received_byte_size"] == len(content)
            assert att["detected_media_type"] == "application/pdf"
            # Attachment available + current_version 指向 available 版本
            arow = (await s2.execute(sa.text(
                "SELECT state, current_version_id FROM attachments WHERE id = :i"
            ), {"i": rec.attachment_id})).mappings().first()
            assert arow["state"] == "available"
            assert arow["current_version_id"] == rec.attachment_version_id
            vrow = (await s2.execute(sa.text(
                "SELECT availability, version_no, content_hash, byte_size FROM attachment_versions WHERE id = :i"
            ), {"i": rec.attachment_version_id})).mappings().first()
            assert vrow["availability"] == "available"
            assert vrow["version_no"] == 1
            assert vrow["content_hash"] == hashlib.sha256(content).hexdigest()
            assert vrow["byte_size"] == len(content)
            # quarantine handle promoted
            qrow = (await s2.execute(sa.text(
                "SELECT handle_state, is_publicly_readable FROM evidence_quarantine_handles "
                "WHERE id = :i"
            ), {"i": rec.quarantine_handle_id})).mappings().first()
            assert qrow["handle_state"] == "promoted"
            assert qrow["is_publicly_readable"] is False


# --- 大小拒绝：同一 attempt=rejected，无 available Attachment/Version ------------


@pytest.mark.asyncio
async def test_oversize_rejected_no_available_records():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(
                session, storage_finalizer=_fake_finalizer, max_upload_bytes=200, chunk_size=32
            )
            rec = await _receive(gw, ids, content=_PDF + b"z" * 2000, idem="oversize")
            assert rec.outcome == "rejected"
            assert rec.error_code == EvidenceErrorCode.ATTACHMENT_TOO_LARGE
            assert rec.response_mode == 413
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert att["failure_category"] == FAILURE_TOO_LARGE
            # 无可用 Attachment/Version
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0


# --- MIME mismatch 拒绝 -------------------------------------------------------


@pytest.mark.asyncio
async def test_media_type_mismatch_rejected():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session, storage_finalizer=_fake_finalizer, chunk_size=32)
            # 声明 pdf 实际 png
            rec = await _receive(gw, ids, content=_PNG + b"z" * 200, declared="application/pdf",
                                 idem="mism", raw_file_name="fake.pdf")
            assert rec.outcome == "rejected"
            assert rec.error_code == EvidenceErrorCode.MEDIA_TYPE_MISMATCH
            assert rec.response_mode == 415
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert att["failure_category"] == FAILURE_TYPE_MISMATCH
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0


# --- 空文件拒绝 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_rejected():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(session, storage_finalizer=_fake_finalizer)
            rec = await _receive(gw, ids, content=b"", idem="empty")
            assert rec.outcome == "rejected"
            assert rec.failure_category == FAILURE_EMPTY
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0


# --- 恶意内容：quarantined + purged + 不可访问，无 available -------------------


@pytest.mark.asyncio
async def test_malicious_content_quarantined_and_purged():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        store = InMemoryQuarantineStore()
        async with SM() as session:
            gw = SecureAttachmentGateway(
                session,
                storage_finalizer=_fake_finalizer,
                quarantine_store=store,
                malware_scanner=lambda content: False,  # 判定为恶意
                chunk_size=32,
            )
            rec = await _receive(gw, ids, content=_PDF + b"evil" * 100, idem="mal")
            assert rec.outcome == "quarantined"
            assert rec.failure_category == FAILURE_MALWARE
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "quarantined"
            # 无可用 Attachment/Version
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0
            # quarantine handle = quarantined + purged_at 已设 + 不可公开读取
            qrow = (await s2.execute(sa.text(
                "SELECT handle_state, purged_at, is_publicly_readable "
                "FROM evidence_quarantine_handles WHERE id = :i"
            ), {"i": rec.quarantine_handle_id})).mappings().first()
            assert qrow["handle_state"] == "quarantined"
            assert qrow["purged_at"] is not None
            assert qrow["is_publicly_readable"] is False
        # 加密擦除后隔离缓冲不可读
        assert not store.exists(f"quarantine://{rec.quarantine_handle_id}")


# --- 背压 429 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_backpressure_429_no_records():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = SecureAttachmentGateway(
                session, storage_finalizer=_fake_finalizer,
                quarantine_high_water_bytes=64, chunk_size=16, max_upload_bytes=100_000,
            )
            rec = await _receive(gw, ids, content=_PDF + b"a" * 4000, idem="bp")
            assert rec.outcome == "rejected"
            assert rec.error_code == EvidenceErrorCode.CAPACITY_BACKPRESSURE
            assert rec.response_mode == 429
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert att["failure_category"] == FAILURE_BACKPRESSURE
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0


# --- 异步 202 staged + finalize_staged_upload → available；staged 不可引用 -------


@pytest.mark.asyncio
async def test_async_staged_then_finalize_and_not_referenceable_while_staged():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    content = _PDF + b"async" * 200
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        store = InMemoryQuarantineStore()
        async with SM() as session:
            gw = SecureAttachmentGateway(
                session, storage_finalizer=_fake_finalizer, quarantine_store=store, chunk_size=64
            )
            rec = await _receive(gw, ids, content=content, idem="async", synchronous_finalize=False)
            assert rec.outcome == "pending"
            assert rec.response_mode == 202
            assert rec.availability == "staged"
        # staged 期间：attachment.state != available、version.availability='staged'（不可被正式路径引用）
        async with SM() as s2:
            arow = (await s2.execute(sa.text(
                "SELECT state, current_version_id FROM attachments WHERE id = :i"
            ), {"i": rec.attachment_id})).mappings().first()
            assert arow["state"] == "pending"
            assert arow["current_version_id"] is None
            vrow = (await s2.execute(sa.text(
                "SELECT availability FROM attachment_versions WHERE id = :i"
            ), {"i": rec.attachment_version_id})).mappings().first()
            assert vrow["availability"] == "staged"
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "pending"
        # worker finalize
        async with SM() as session:
            gw = SecureAttachmentGateway(
                session, storage_finalizer=_fake_finalizer, quarantine_store=store, chunk_size=64
            )
            done = await gw.finalize_staged_upload(
                attempt_id=rec.attempt_id,
                attachment_id=rec.attachment_id,
                attachment_version_id=rec.attachment_version_id,
                quarantine_handle_id=rec.quarantine_handle_id,
                quarantine_key=f"quarantine://{rec.quarantine_handle_id}",
                sanitized_file_name="report.pdf",
                content_hash=rec.content_hash,
                detected_media_type=rec.detected_media_type,
                received_byte_size=rec.received_byte_size,
                actor=_actor(ids),
                actor_role="auditor",
                idempotency_key="async",
                project_id=ids["project"],
                audit_year=2025,
            )
            assert done.outcome == "accepted"
            assert done.availability == "available"
        async with SM() as s2:
            arow = (await s2.execute(sa.text(
                "SELECT state, current_version_id FROM attachments WHERE id = :i"
            ), {"i": rec.attachment_id})).mappings().first()
            assert arow["state"] == "available"
            assert arow["current_version_id"] == rec.attachment_version_id
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "accepted"
