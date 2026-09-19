"""Durable quarantine store + stale-quarantine reaper — 持久隔离区与崩溃安全收尾。

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1.2, R2 · Design: §4.0 (UploadAttempt/隔离区), §5.1 (流式上传与异步 finalize)

覆盖（对齐用户所述四组）：
  (a) DurableQuarantineStore round-trip：begin/write/read/size/buffered_bytes + purge(crypto_erase)
      先覆写字节再删除（断言文件消失 + 不可读）——纯 fs，无 DB。
  (b) durable-store staged 上传跨 **新 gateway 实例**（模拟跨进程/重启 finalize）仍可 finalize→available。
  (c) reaper：过期 orphaned staged handle 被加密擦除 + 标记 purged + 对账 inactive；
      still-fresh / available 的不动。
  (d) 隔离根在所有 Storage_Boundary root 之外：StorageBoundaryResolver 拒绝其下任何路径。

真实 PG 铁律（design §10.1/§10.2）：约束/事务在真实 PG16 验证，无 PG 环境 skip（reaper/跨实例）。
"""

from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.frozen_contracts import ActorContext
from app.services.evidence_governance.quarantine_reaper import reap_stale_quarantine
from app.services.evidence_governance.secure_attachment_gateway import (
    DurableQuarantineStore,
    InMemoryQuarantineStore,
    SecureAttachmentGateway,
    StorageBoundaryResolver,
    sanitize_upload_filename,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"

_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def _chunks(data: bytes, block: int = 16):
    for i in range(0, len(data), block):
        yield data[i : i + block]


# ===========================================================================
# (a) DurableQuarantineStore — 纯 fs round-trip + crypto-erase
# ===========================================================================


class TestDurableQuarantineStore:
    def test_round_trip_begin_write_read_size(self, tmp_path):
        store = DurableQuarantineStore(tmp_path / "q")
        key = f"quarantine://{uuid.uuid4()}"
        store.begin(key)
        assert store.exists(key)
        assert store.size(key) == 0
        payload = _PDF + b"payload-bytes" * 100
        # 分块写入模拟流式接收
        for c in _chunks(payload, 32):
            store.write(key, c)
        assert store.read(key) == payload
        assert store.size(key) == len(payload)

    def test_buffered_bytes_tracks_and_survives_new_instance(self, tmp_path):
        root = tmp_path / "q"
        store = DurableQuarantineStore(root)
        k1 = f"quarantine://{uuid.uuid4()}"
        k2 = f"quarantine://{uuid.uuid4()}"
        store.write(k1, b"a" * 500)
        store.write(k2, b"b" * 300)
        assert store.buffered_bytes() == 800
        # 新实例（重启）指向同一根：按磁盘现存文件大小重建计数
        store2 = DurableQuarantineStore(root)
        assert store2.buffered_bytes() == 800

    def test_purge_crypto_erase_overwrites_then_removes(self, tmp_path):
        store = DurableQuarantineStore(tmp_path / "q")
        key = f"quarantine://{uuid.uuid4()}"
        secret = b"TOP-SECRET-EVIDENCE" * 50
        store.write(key, secret)
        path = store._path(key)
        assert path.exists()
        before = store.buffered_bytes()
        assert before == len(secret)

        store.purge(key, crypto_erase=True)

        # 文件消失 + 不可读（read 抛 KeyError）
        assert not store.exists(key)
        assert not path.exists()
        with pytest.raises(KeyError):
            store.read(key)
        assert store.buffered_bytes() == 0

    def test_purge_missing_key_is_noop(self, tmp_path):
        store = DurableQuarantineStore(tmp_path / "q")
        # 不存在的 key（如 quarantined handle 内容早已擦除）→ 幂等 no-op
        store.purge(f"quarantine://{uuid.uuid4()}", crypto_erase=True)
        assert store.buffered_bytes() == 0

    def test_begin_does_not_clobber_existing(self, tmp_path):
        store = DurableQuarantineStore(tmp_path / "q")
        key = f"quarantine://{uuid.uuid4()}"
        store.write(key, b"keep-me")
        store.begin(key)  # setdefault 语义：不清空
        assert store.read(key) == b"keep-me"

    def test_same_interface_as_in_memory(self):
        # 与 InMemoryQuarantineStore 接口一致（drop-in 可替换）
        for name in ("begin", "write", "size", "read", "buffered_bytes", "purge", "exists"):
            assert hasattr(DurableQuarantineStore, name)
            assert hasattr(InMemoryQuarantineStore, name)


# ===========================================================================
# (d) 隔离根在所有 Storage_Boundary root 之外 —— 纯路径，无 I/O
# ===========================================================================


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class TestQuarantineRootOutsideBoundary:
    def test_quarantine_root_not_within_any_boundary_root(self):
        from app.core.config import settings

        resolver = StorageBoundaryResolver(
            [settings.ATTACHMENT_LOCAL_STORAGE_ROOT, settings.STORAGE_ROOT]
        )
        qroot = Path(os.path.normpath(settings.ATTACHMENT_QUARANTINE_ROOT)).absolute()
        for root in resolver.roots:
            assert not _is_relative_to(qroot, root), (
                f"quarantine root {qroot} 落在 boundary root {root} 内——隔离内容会经边界可读"
            )

    def test_resolver_rejects_paths_under_quarantine_root(self):
        from app.core.config import settings

        resolver = StorageBoundaryResolver(
            [settings.ATTACHMENT_LOCAL_STORAGE_ROOT, settings.STORAGE_ROOT]
        )
        qroot = Path(os.path.normpath(settings.ATTACHMENT_QUARANTINE_ROOT)).absolute()
        # 隔离目录下真实 blob 文件路径 → 越界（None），字节读取器绝不会被调用
        blob_path = str(qroot / hashlib.sha256(b"quarantine://x").hexdigest())
        assert resolver.normalize_within_boundary(blob_path) is None

    def test_resolver_rejects_opaque_quarantine_and_staged_scheme(self):
        from app.core.config import settings

        resolver = StorageBoundaryResolver(
            [settings.ATTACHMENT_LOCAL_STORAGE_ROOT, settings.STORAGE_ROOT]
        )
        assert resolver.resolve_read_plan(None, f"quarantine://{uuid.uuid4()}").rejected
        assert resolver.resolve_read_plan(None, f"staged://{uuid.uuid4()}").rejected


# ===========================================================================
# PG16 集成脚手架（复用 3.3 wave2 约定）
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
    tmp_db = f"evgov_reap_{uuid.uuid4().hex[:12]}"

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


async def _fake_finalizer(*, project_id, file_name, content, media_type):
    loc = f"evidence://{uuid.uuid4()}"
    return {"storage_type": "local", "storage_key": loc, "file_path": loc}


def _actor(ids):
    return ActorContext.for_user(ids["user"])


async def _receive(gw, ids, *, content, idem=None, synchronous_finalize=True,
                   raw_file_name="report.pdf"):
    return await gw.receive_upload(
        project_id=ids["project"],
        audit_year=2025,
        raw_file_name=raw_file_name,
        declared_media_type="application/pdf",
        chunks=_chunks(content, 32),
        actor=_actor(ids),
        actor_role="auditor",
        idempotency_key=idem or f"up-{uuid.uuid4().hex[:8]}",
        synchronous_finalize=synchronous_finalize,
    )


# ===========================================================================
# (b) durable staged 上传跨新 gateway 实例（跨进程/重启）仍可 finalize
# ===========================================================================


@pytest.mark.asyncio
async def test_durable_staged_survives_new_gateway_and_finalizes(tmp_path):
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    content = _PDF + b"cross-process-payload" * 80
    root = tmp_path / "durable_q"
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        # --- 实例 A：durable store + 异步 finalize → 202 staged ---
        store_a = DurableQuarantineStore(root)
        async with SM() as session_a:
            gw_a = SecureAttachmentGateway(
                session_a, quarantine_store=store_a,
                storage_finalizer=_fake_finalizer, chunk_size=64,
            )
            rec = await _receive(
                gw_a, ids, content=content, idem="cross", synchronous_finalize=False
            )
            assert rec.response_mode == 202
            assert rec.availability == "staged"

        q_key = f"quarantine://{rec.quarantine_handle_id}"
        # blob 落盘：即便进程重启也在
        assert store_a.exists(q_key)

        # --- 实例 B：全新 gateway + 全新 durable store（同根）→ finalize → available ---
        store_b = DurableQuarantineStore(root)
        assert store_b.exists(q_key)  # 新实例可读到 A staged 的内容
        assert store_b.read(q_key) == content
        async with SM() as session_b:
            gw_b = SecureAttachmentGateway(
                session_b, quarantine_store=store_b,
                storage_finalizer=_fake_finalizer, chunk_size=64,
            )
            final = await gw_b.finalize_staged_upload(
                attempt_id=rec.attempt_id,
                attachment_id=rec.attachment_id,
                attachment_version_id=rec.attachment_version_id,
                quarantine_handle_id=rec.quarantine_handle_id,
                quarantine_key=q_key,
                sanitized_file_name=sanitize_upload_filename("report.pdf"),
                content_hash=rec.content_hash,
                detected_media_type=rec.detected_media_type,
                received_byte_size=rec.received_byte_size,
                actor=_actor(ids),
                actor_role="auditor",
                idempotency_key="cross",
                project_id=ids["project"],
                audit_year=2025,
            )
            assert final.outcome == "accepted"
            assert final.availability == "available"

        async with SM() as s2:
            arow = (await s2.execute(sa.text(
                "SELECT state, current_version_id FROM attachments WHERE id = :i"
            ), {"i": rec.attachment_id})).mappings().first()
            assert arow["state"] == "available"
            assert arow["current_version_id"] == rec.attachment_version_id
            vrow = (await s2.execute(sa.text(
                "SELECT availability FROM attachment_versions WHERE id = :i"
            ), {"i": rec.attachment_version_id})).mappings().first()
            assert vrow["availability"] == "available"
            att = (await s2.execute(sa.text(
                "SELECT validation_outcome FROM evidence_upload_attempts WHERE id = :i"
            ), {"i": rec.attempt_id})).mappings().first()
            assert att["validation_outcome"] == "accepted"


# ===========================================================================
# (c) reaper：过期 orphaned staged → 加密擦除 + purged + inactive；fresh/available 不动
# ===========================================================================


async def _backdate_handle(SM, handle_id, delta_seconds):
    async with SM() as s:
        await s.execute(
            sa.text("UPDATE evidence_quarantine_handles SET created_at = :t WHERE id = :i"),
            {"t": datetime.now(timezone.utc) - timedelta(seconds=delta_seconds), "i": str(handle_id)},
        )
        await s.commit()


@pytest.mark.asyncio
async def test_reaper_purges_stale_and_spares_fresh_and_available(tmp_path):
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    root = tmp_path / "reap_q"
    store = DurableQuarantineStore(root)
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        # (1) 过期 orphaned staged 上传（202，永不 finalize）
        async with SM() as s:
            gw = SecureAttachmentGateway(
                s, quarantine_store=store, storage_finalizer=_fake_finalizer, chunk_size=64
            )
            stale = await _receive(
                gw, ids, content=_PDF + b"stale" * 100, idem="stale",
                synchronous_finalize=False,
            )
        stale_key = f"quarantine://{stale.quarantine_handle_id}"
        assert store.exists(stale_key)

        # (2) 全新 staged 上传（未过期）
        async with SM() as s:
            gw = SecureAttachmentGateway(
                s, quarantine_store=store, storage_finalizer=_fake_finalizer, chunk_size=64
            )
            fresh = await _receive(
                gw, ids, content=_PDF + b"fresh" * 100, idem="fresh",
                synchronous_finalize=False,
            )
        fresh_key = f"quarantine://{fresh.quarantine_handle_id}"

        # (3) 已 finalize 的 available 上传（handle=promoted）
        async with SM() as s:
            gw = SecureAttachmentGateway(
                s, quarantine_store=store, storage_finalizer=_fake_finalizer, chunk_size=64
            )
            avail = await _receive(
                gw, ids, content=_PDF + b"good" * 100, idem="good",
                synchronous_finalize=True,
            )
            assert avail.availability == "available"

        # 把过期 handle 的 created_at 回拨到 TTL 之外
        await _backdate_handle(SM, stale.quarantine_handle_id, delta_seconds=7200)

        # --- 运行 reaper（TTL=3600s）---
        async with SM() as s:
            report = await reap_stale_quarantine(s, store, ttl_seconds=3600)

        assert report.purged == 1
        assert stale.quarantine_handle_id in report.purged_handle_ids
        assert report.attachments_inactivated == 1
        assert report.versions_inactivated == 1

        # 过期内容被加密擦除
        assert not store.exists(stale_key)
        # 全新内容不动
        assert store.exists(fresh_key)

        async with SM() as s2:
            # 过期 handle → purged + purged_at；is_publicly_readable 仍 false
            h = (await s2.execute(sa.text(
                "SELECT handle_state, purged_at, is_publicly_readable "
                "FROM evidence_quarantine_handles WHERE id = :i"
            ), {"i": stale.quarantine_handle_id})).mappings().first()
            assert h["handle_state"] == "purged"
            assert h["purged_at"] is not None
            assert h["is_publicly_readable"] is False
            # 过期 orphaned Attachment/Version → inactive
            a = (await s2.execute(sa.text(
                "SELECT state FROM attachments WHERE id = :i"
            ), {"i": stale.attachment_id})).mappings().first()
            assert a["state"] == "inactive"
            v = (await s2.execute(sa.text(
                "SELECT availability FROM attachment_versions WHERE id = :i"
            ), {"i": stale.attachment_version_id})).mappings().first()
            assert v["availability"] == "inactive"

            # 全新 staged handle 未动
            hf = (await s2.execute(sa.text(
                "SELECT handle_state FROM evidence_quarantine_handles WHERE id = :i"
            ), {"i": fresh.quarantine_handle_id})).mappings().first()
            assert hf["handle_state"] == "staged"
            af = (await s2.execute(sa.text(
                "SELECT state FROM attachments WHERE id = :i"
            ), {"i": fresh.attachment_id})).mappings().first()
            assert af["state"] == "pending"

            # available 上传未动（handle promoted / attachment available）
            hp = (await s2.execute(sa.text(
                "SELECT handle_state FROM evidence_quarantine_handles WHERE id = :i"
            ), {"i": avail.quarantine_handle_id})).mappings().first()
            assert hp["handle_state"] == "promoted"
            ap = (await s2.execute(sa.text(
                "SELECT state FROM attachments WHERE id = :i"
            ), {"i": avail.attachment_id})).mappings().first()
            assert ap["state"] == "available"


@pytest.mark.asyncio
async def test_reaper_spares_handle_under_legal_hold(tmp_path):
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    root = tmp_path / "reap_hold_q"
    store = DurableQuarantineStore(root)
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        async with SM() as s:
            gw = SecureAttachmentGateway(
                s, quarantine_store=store, storage_finalizer=_fake_finalizer, chunk_size=64
            )
            held = await _receive(
                gw, ids, content=_PDF + b"held" * 100, idem="held",
                synchronous_finalize=False,
            )
        held_key = f"quarantine://{held.quarantine_handle_id}"

        # 激活 Legal Hold 覆盖该 attachment
        hold_id = uuid.uuid4()
        async with SM() as s:
            await s.execute(sa.text(
                "INSERT INTO legal_holds (id, project_id, audit_year, state, reason, "
                "actor_type, actor_user_id) "
                "VALUES (:id, :pid, 2025, 'active', 'litigation', 'user', :uid)"
            ), {"id": str(hold_id), "pid": str(ids["project"]), "uid": str(ids["user"])})
            await s.execute(sa.text(
                "INSERT INTO legal_hold_scopes (id, legal_hold_id, project_id, audit_year, "
                "node_type, node_id, scope_kind, is_active) "
                "VALUES (:id, :hid, :pid, 2025, 'attachment', :nid, 'direct', true)"
            ), {"id": str(uuid.uuid4()), "hid": str(hold_id), "pid": str(ids["project"]),
                "nid": str(held.attachment_id)})
            await s.commit()

        await _backdate_handle(SM, held.quarantine_handle_id, delta_seconds=7200)

        async with SM() as s:
            report = await reap_stale_quarantine(s, store, ttl_seconds=3600)

        assert report.purged == 0
        assert report.skipped_legal_hold == 1
        # hold 下内容/行都不动
        assert store.exists(held_key)
        async with SM() as s2:
            h = (await s2.execute(sa.text(
                "SELECT handle_state FROM evidence_quarantine_handles WHERE id = :i"
            ), {"i": held.quarantine_handle_id})).mappings().first()
            assert h["handle_state"] == "staged"
            a = (await s2.execute(sa.text(
                "SELECT state FROM attachments WHERE id = :i"
            ), {"i": held.attachment_id})).mappings().first()
            assert a["state"] == "pending"
