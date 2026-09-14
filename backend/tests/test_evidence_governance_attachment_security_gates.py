"""附件安全门接线 — 单元 + 真实 PG16 集成（生产接线缺口修复）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1.2, R1.3, R2, R15
Design: §5.1 流式上传与内容验证门, §9.3 可观测性

覆盖：
  1. 门工厂单元（纯函数，无 DB）：媒体类型允许清单解析 / 签名式恶意内容检查 /
     可读性检查 / 三道门装配 + fully_wired 判定。
  2. 启动 fail-closed 守卫（纯逻辑，无 DB）：
     - 三道门接线 → pass；
     - production + REQUIRED 缺门 → 抛 AttachmentSecurityGatesNotWiredError；
     - production 缺门（未强制）→ loud WARNING + 治理 alert；
     - 非 production 缺门 → 不阻断。
  3. 真实 PG16（throwaway 库）：用「从配置装配的真实门」构造 gateway，验证
     - (a) 声明媒体类型不在允许清单 → rejected（MEDIA_TYPE_MISMATCH / declared_type_not_allowed）；
     - (b) 恶意内容（PE MZ 可执行）→ quarantined + 加密擦除 + 无 available Attachment/Version。

真实 PG 铁律（design §10.1/§10.2）：无 PG 环境 skip。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.attachment_security_gates import (
    AttachmentSecurityGatesNotWiredError,
    build_allowed_media_types,
    build_malware_scanner,
    build_readability_checker,
    check_attachment_security_gates_startup,
    readability_is_ok,
    resolve_attachment_security_gates,
    signature_scan_is_clean,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
)
from app.services.evidence_governance.secure_attachment_gateway import (
    FAILURE_MALWARE,
    FAILURE_TYPE_NOT_ALLOWED,
    InMemoryQuarantineStore,
    SecureAttachmentGateway,
)

# 常见 magic 内容前缀。
_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_PE = b"MZ\x90\x00\x03\x00\x00\x00"  # Windows PE 可执行
_ELF = b"\x7fELF\x02\x01\x01\x00"
_EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _cfg(**overrides):
    """构造一个配置替身（默认全门开启、dev 环境）。"""
    base = dict(
        ATTACHMENT_ALLOWED_MEDIA_TYPES="application/pdf,image/png,text/csv",
        ATTACHMENT_SIGNATURE_SCAN_ENABLED=True,
        ATTACHMENT_READABILITY_CHECK_ENABLED=True,
        ATTACHMENT_SECURITY_GATES_REQUIRED=False,
        CLAMAV_ENABLED=False,
        APP_ENV="dev",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ===========================================================================
# 1) 门工厂单元（纯函数）
# ===========================================================================


class TestAllowedMediaTypes:
    def test_parse_comma_list_lowercased(self):
        allow = build_allowed_media_types(_cfg(ATTACHMENT_ALLOWED_MEDIA_TYPES="Application/PDF, image/PNG"))
        assert allow == frozenset({"application/pdf", "image/png"})

    def test_empty_disables_allow_list(self):
        assert build_allowed_media_types(_cfg(ATTACHMENT_ALLOWED_MEDIA_TYPES="")) is None
        assert build_allowed_media_types(_cfg(ATTACHMENT_ALLOWED_MEDIA_TYPES="  , ,")) is None


class TestSignatureScanner:
    def test_rejects_executable_and_script_magic(self):
        assert signature_scan_is_clean(_PE) is False
        assert signature_scan_is_clean(_ELF) is False
        assert signature_scan_is_clean(b"#!/bin/sh\nrm -rf /") is False

    def test_rejects_eicar_signature(self):
        assert signature_scan_is_clean(b"prefix " + _EICAR + b" suffix") is False

    def test_allows_benign_content(self):
        assert signature_scan_is_clean(_PDF + b"benign body") is True
        assert signature_scan_is_clean(b"") is True  # 空由流式 empty 门拦截，此处从宽

    @pytest.mark.asyncio
    async def test_build_malware_scanner_is_real_not_stub(self):
        scanner = build_malware_scanner(_cfg())
        assert scanner is not None
        # 真实拒绝可执行内容（非 lambda:True 桩）。
        assert await scanner(_PE) is False
        assert await scanner(_PDF + b"ok") is True

    def test_disabling_both_returns_none(self):
        assert build_malware_scanner(_cfg(ATTACHMENT_SIGNATURE_SCAN_ENABLED=False, CLAMAV_ENABLED=False)) is None


class TestReadabilityChecker:
    def test_empty_and_zero_bytes_unreadable(self):
        assert readability_is_ok(b"", "application/pdf") is False
        assert readability_is_ok(b"\x00" * 100, "application/pdf") is False

    def test_pdf_requires_header(self):
        assert readability_is_ok(_PDF + b"body", "application/pdf") is True
        assert readability_is_ok(b"not a pdf", "application/pdf") is False

    def test_text_must_decode(self):
        assert readability_is_ok("列,金额\n工资,100".encode("utf-8"), "text/csv") is True
        assert readability_is_ok(b"\xff\xfe\xfa\xfb", "text/csv") is False

    def test_unregistered_type_lenient(self):
        assert readability_is_ok(b"anything", "application/octet-stream") is True

    def test_build_returns_none_when_disabled(self):
        assert build_readability_checker(_cfg(ATTACHMENT_READABILITY_CHECK_ENABLED=False)) is None


class TestResolveGates:
    def test_fully_wired(self):
        gates = resolve_attachment_security_gates(_cfg())
        assert gates.fully_wired is True
        assert gates.missing_gates() == []

    def test_missing_reported(self):
        gates = resolve_attachment_security_gates(
            _cfg(
                ATTACHMENT_ALLOWED_MEDIA_TYPES="",
                ATTACHMENT_SIGNATURE_SCAN_ENABLED=False,
                CLAMAV_ENABLED=False,
                ATTACHMENT_READABILITY_CHECK_ENABLED=False,
            )
        )
        assert gates.fully_wired is False
        assert set(gates.missing_gates()) == {
            "allowed_media_types",
            "malware_scanner",
            "readability_checker",
        }


# ===========================================================================
# 2) 启动 fail-closed 守卫
# ===========================================================================


class _FakeMetrics:
    def __init__(self):
        self.alerts = []

    def record_alert(self, **kw):
        self.alerts.append(kw)


class TestStartupGuard:
    def test_passes_when_fully_wired(self):
        res = check_attachment_security_gates_startup(_cfg(APP_ENV="production"))
        assert res["ok"] is True
        assert res["fully_wired"] is True

    def test_raises_when_required_and_missing(self):
        cfg = _cfg(
            APP_ENV="production",
            ATTACHMENT_SECURITY_GATES_REQUIRED=True,
            ATTACHMENT_SIGNATURE_SCAN_ENABLED=False,
            CLAMAV_ENABLED=False,
        )
        with pytest.raises(AttachmentSecurityGatesNotWiredError):
            check_attachment_security_gates_startup(cfg)

    def test_production_missing_warns_and_records_alert(self):
        cfg = _cfg(
            APP_ENV="production",
            ATTACHMENT_SECURITY_GATES_REQUIRED=False,
            ATTACHMENT_ALLOWED_MEDIA_TYPES="",
        )
        metrics = _FakeMetrics()
        res = check_attachment_security_gates_startup(cfg, metrics=metrics)
        assert res["ok"] is False
        assert "allowed_media_types" in res["missing"]
        assert len(metrics.alerts) == 1
        assert metrics.alerts[0]["alert_type"] == "gate_bypass"

    def test_non_production_missing_does_not_block(self):
        cfg = _cfg(
            APP_ENV="dev",
            ATTACHMENT_SIGNATURE_SCAN_ENABLED=False,
            CLAMAV_ENABLED=False,
        )
        metrics = _FakeMetrics()
        res = check_attachment_security_gates_startup(cfg, metrics=metrics)
        assert res["ok"] is False
        # 非生产不记录治理告警（合法注入 fake / 关门运行）。
        assert metrics.alerts == []

    def test_explicit_raise_on_missing_overrides_flag(self):
        cfg = _cfg(APP_ENV="dev", ATTACHMENT_READABILITY_CHECK_ENABLED=False)
        with pytest.raises(AttachmentSecurityGatesNotWiredError):
            check_attachment_security_gates_startup(cfg, raise_on_missing=True)


# ===========================================================================
# 3) 真实 PG16 集成 — gateway 用「从配置装配的真实门」
# ===========================================================================

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


def _chunks(data: bytes, block: int = 16):
    for i in range(0, len(data), block):
        yield data[i : i + block]


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_gates_{uuid.uuid4().hex[:12]}"

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
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"), {"i": ids["project"]}
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
            "SELECT validation_outcome, failure_category FROM evidence_upload_attempts "
            "WHERE id = :i"
        ),
        {"i": attempt_id},
    )
    return row.mappings().first()


async def _fake_finalizer(*, project_id, file_name, content, media_type):
    loc = f"evidence://{uuid.uuid4()}"
    return {"storage_type": "local", "storage_key": loc, "file_path": loc}


def _wired_gateway(session, store=None):
    """从真实配置装配三道门构造 gateway（与生产 _build_gateway 同路径）。"""
    gates = resolve_attachment_security_gates(_cfg())
    return SecureAttachmentGateway(
        session,
        storage_finalizer=_fake_finalizer,
        quarantine_store=store or InMemoryQuarantineStore(),
        allowed_media_types=gates.allowed_media_types,
        malware_scanner=gates.malware_scanner,
        readability_checker=gates.readability_checker,
        chunk_size=32,
    )


async def _receive(gw, ids, *, content, declared, raw_file_name, idem=None):
    return await gw.receive_upload(
        project_id=ids["project"],
        audit_year=2025,
        raw_file_name=raw_file_name,
        declared_media_type=declared,
        chunks=_chunks(content),
        actor=ActorContext.for_user(ids["user"]),
        actor_role="auditor",
        idempotency_key=idem or f"gate-{uuid.uuid4().hex[:8]}",
        synchronous_finalize=True,
    )


# --- (a) 声明媒体类型不在允许清单 → rejected --------------------------------


@pytest.mark.asyncio
async def test_disallowed_declared_media_type_rejected():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = _wired_gateway(session)
            # 声明 application/x-msdownload（不在允许清单 pdf/png/csv）。
            rec = await _receive(
                gw, ids,
                content=_PDF + b"body",
                declared="application/x-msdownload",
                raw_file_name="tool.exe",
                idem="notallowed",
            )
            assert rec.outcome == "rejected"
            assert rec.error_code == EvidenceErrorCode.MEDIA_TYPE_MISMATCH
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "rejected"
            assert att["failure_category"] == FAILURE_TYPE_NOT_ALLOWED
            # 无可用 Attachment/Version。
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0


# --- (b) 恶意内容（PE 可执行）→ quarantined + 加密擦除 + 无 available ---------


@pytest.mark.asyncio
async def test_malware_content_quarantined_and_crypto_erased():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        store = InMemoryQuarantineStore()
        async with SM() as session:
            gw = _wired_gateway(session, store=store)
            # 声明 application/pdf（在允许清单），但内容是 PE 可执行 → 真实签名门判定恶意。
            rec = await _receive(
                gw, ids,
                content=_PE + b"\x00malicious payload" * 20,
                declared="application/pdf",
                raw_file_name="invoice.pdf",
                idem="malware",
            )
            assert rec.outcome == "quarantined"
            assert rec.failure_category == FAILURE_MALWARE
        async with SM() as s2:
            att = await _fetch_attempt(s2, rec.attempt_id)
            assert att["validation_outcome"] == "quarantined"
            # 无可用 Attachment/Version。
            assert await _count(s2, "attachments") == 0
            assert await _count(s2, "attachment_versions") == 0
            # quarantine handle = quarantined + purged_at 已设 + 不可公开读取。
            qrow = (
                await s2.execute(
                    sa.text(
                        "SELECT handle_state, purged_at, is_publicly_readable "
                        "FROM evidence_quarantine_handles WHERE id = :i"
                    ),
                    {"i": rec.quarantine_handle_id},
                )
            ).mappings().first()
            assert qrow["handle_state"] == "quarantined"
            assert qrow["purged_at"] is not None
            assert qrow["is_publicly_readable"] is False
        # 加密擦除后隔离缓冲不可读。
        assert not store.exists(f"quarantine://{rec.quarantine_handle_id}")


# --- 对照：合法 PDF（声明允许 + 通过签名/可读性门）→ accepted ------------------


@pytest.mark.asyncio
async def test_allowed_clean_pdf_accepted():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            gw = _wired_gateway(session)
            rec = await _receive(
                gw, ids,
                content=_PDF + b"clean audit evidence body" * 20,
                declared="application/pdf",
                raw_file_name="evidence.pdf",
                idem="clean",
            )
            assert rec.outcome == "accepted"
            assert rec.availability == "available"
        async with SM() as s2:
            assert await _count(s2, "attachments") == 1
            assert await _count(s2, "attachment_versions") == 1
