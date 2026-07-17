"""Real-PG16 contract test — CitationSnapshotService column/UUID hardening (Task 6.1).

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R7 (R7.3 re-auth on open), R9, R15
Design: §3.2 CitationSnapshotService, §4.6 Citation (immutable snapshot), §10 (无 PG 环境 skip)
Properties: P15 (RAG 引用可定位), P16 (RAG 权限不扩张)

Regression guard for the CONFIRMED live bug (HTTP 500 on citation locate):

    asyncpg.UndefinedColumnError: column "status" does not exist

The ``citation_snapshots`` table (migration V108 / ORM ``CitationSnapshot``) is an
IMMUTABLE snapshot with NO ``status`` column — locatability/validity is DERIVED at read
time from the immutable fields (version/hash/page/region) + the linked EvidenceRef being
active. The service SELECT must reference only real columns, and locate/list/validate must
tolerate a nonexistent AND a non-UUID citation id by returning a clean coded result
(None / INVALID / desensitized 404) WITHOUT raising ProgrammingError/DataError.

Runs against a throwaway PG16 database seeded from the real V106–V108 migrations. Skips
gracefully when no PostgreSQL is available (design §10 — SQLite must NOT substitute).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.citation_snapshot_service import (
    CitationSnapshotService,
    CitationStatus,
)
from app.services.evidence_governance.frozen_contracts import ActorContext, sha256_hex

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


# ─────────────────────────────────────────────────────────────────────────────
# PG16 throwaway-engine helpers (mirrors test_evidence_governance_rag_ai_*_9_3)
# ─────────────────────────────────────────────────────────────────────────────


def _pg_available() -> bool:
    from app.core.config import settings

    return settings.DATABASE_URL.startswith("postgresql")


def _base_url() -> str:
    from app.core.config import settings

    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args() -> dict:
    from app.core.config import settings

    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


def _split(sql: str) -> list[str]:
    return MigrationRunner._split_sql_statements(sql)


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
    audit_year int,
    current_version_id uuid,
    file_name varchar(500), file_path varchar(1000),
    file_type varchar(100), file_size bigint,
    ocr_status varchar(20), version int, previous_version_id uuid,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false,
    CONSTRAINT uq_attach_scope UNIQUE (id, project_id, audit_year)
);
"""


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_cite_contract_{uuid.uuid4().hex[:12]}"

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


async def _seed_citation(eng) -> dict:
    """Seed user + project + ai_content_log + active evidence_ref + citation_snapshot."""
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "project": uuid.uuid4(),
        "ai_log": uuid.uuid4(),
        "ref": uuid.uuid4(),
        "citation": uuid.uuid4(),
        "content_hash": "a" * 64,
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            T("INSERT INTO ai_content_log (id, project_id) VALUES (:i, :p)"),
            {"i": ids["ai_log"], "p": ids["project"]},
        )
        await conn.execute(
            T(
                "INSERT INTO evidence_refs "
                "(id, project_id, audit_year, source_type, source_id, evidence_type, "
                " evidence_id, intent_hash, status, actor_type, actor_user_id) "
                "VALUES (:i, :p, 2025, 'workpaper_cell', 's1', 'attachment_version', "
                " 'e1', :h, 'active', 'user', :u)"
            ),
            {"i": ids["ref"], "p": ids["project"], "h": ids["content_hash"], "u": ids["user"]},
        )
        await conn.execute(
            T(
                "INSERT INTO citation_snapshots "
                "(id, ai_content_log_id, evidence_ref_id, project_id, audit_year, "
                " target_version, target_hash, page, region, excerpt_hash, "
                " index_version, locator_version, actor_type, actor_user_id) "
                "VALUES (:i, :ai, :ref, :p, 2025, "
                " '1', :h, 3, CAST(:region AS jsonb), :eh, "
                " 'idx-v1', 'loc-v1', 'user', :u)"
            ),
            {
                "i": ids["citation"],
                "ai": ids["ai_log"],
                "ref": ids["ref"],
                "p": ids["project"],
                "h": ids["content_hash"],
                "region": '{"x":1,"y":2,"w":3,"h":4}',
                "eh": sha256_hex("excerpt-text"),
                "u": ids["user"],
            },
        )
    return ids


def _fake_readable_adapter():
    """A typed adapter double that reports the source readable + resolvable.

    Isolates this contract to column/UUID drift (not adapter internals): the real
    ``attachment_version`` adapter would run its own attachment_versions SQL, which is
    orthogonal to the ``status`` column bug under test.
    """
    adapter = MagicMock()
    adapter.can_read = AsyncMock(return_value=True)
    adapter.resolve = AsyncMock(return_value={"ok": True})
    return adapter


# The router's list SELECT (kept in sync with citation_router.list_citations) — proves
# the list path references only real columns.
_LIST_SQL = (
    "SELECT id, ai_content_log_id, evidence_ref_id, audit_year, "
    "target_version, target_hash, page, region, excerpt_hash, "
    "index_version, locator_version, created_at "
    "FROM citation_snapshots "
    "WHERE project_id = :pid AND (audit_year = :yr OR audit_year IS NULL) "
    "ORDER BY created_at DESC LIMIT :lim"
)


# ─────────────────────────────────────────────────────────────────────────────
# Contract tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_locate_existing_citation_no_column_drift():
    """locate() on a real citation resolves via real columns — no ``status`` UndefinedColumn.

    Regression for the live HTTP 500 (asyncpg.UndefinedColumnError: column "status").

    **Validates: Requirements 7.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        actor = ActorContext.for_user(ids["user"])

        async with SM() as session:
            svc = CitationSnapshotService(session)
            with patch(
                "app.services.evidence_governance.citation_snapshot_service.get_adapter",
                return_value=_fake_readable_adapter(),
            ):
                result = await svc.locate_citation(
                    citation_id=ids["citation"],
                    actor=actor,
                    project_id=ids["project"],
                )

        # No exception raised (the bug would have surfaced as UndefinedColumnError → 500).
        # Citation exists, ref active, version/hash match, actor readable → ACTIVE, and the
        # exact page/region are returned (P15 locatable).
        assert result.status == CitationStatus.ACTIVE
        assert result.readable is True
        assert result.source_available is True
        assert result.version_valid is True
        assert result.page == 3
        assert result.region == {"x": 1, "y": 2, "w": 3, "h": 4}


@pytest.mark.asyncio
async def test_locate_nonexistent_uuid_returns_invalid_no_error():
    """locate() with a valid-format but nonexistent UUID → INVALID, no ProgrammingError.

    **Validates: Requirements 7.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)

        async with SM() as session:
            svc = CitationSnapshotService(session)
            result = await svc.locate_citation(
                citation_id=uuid.uuid4(),  # nonexistent
                actor=ActorContext.for_user(ids["user"]),
                project_id=ids["project"],
            )

        assert result.status == CitationStatus.INVALID
        assert result.readable is False
        assert result.reason == "citation_not_found"


@pytest.mark.asyncio
async def test_locate_non_uuid_id_returns_invalid_no_dataerror():
    """locate() with a NON-UUID citation id → clean INVALID, never asyncpg DataError.

    Mirrors the typed-adapter hardening: the id shape is screened BEFORE any UUID-keyed
    SQL runs, so a malformed id resolves to "not found" rather than a server error.

    **Validates: Requirements 7.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)

        async with SM() as session:
            svc = CitationSnapshotService(session)
            # Intentionally pass a non-UUID string (a client could route here directly).
            result = await svc.locate_citation(
                citation_id="not-a-uuid",  # type: ignore[arg-type]
                actor=ActorContext.for_user(ids["user"]),
                project_id=ids["project"],
            )

        assert result.status == CitationStatus.INVALID
        assert result.reason == "citation_not_found"


@pytest.mark.asyncio
async def test_validate_set_with_nonexistent_and_non_uuid_ids():
    """validate() over [real, nonexistent, non-uuid] ids → coded buckets, no DB error.

    **Validates: Requirements 7.3, 9**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        actor = ActorContext.for_user(ids["user"])

        async with SM() as session:
            svc = CitationSnapshotService(session)
            with patch(
                "app.services.evidence_governance.citation_snapshot_service.get_adapter",
                return_value=_fake_readable_adapter(),
            ):
                result = await svc.validate_citation_set(
                    citation_ids=[
                        ids["citation"],       # real → valid
                        uuid.uuid4(),          # nonexistent uuid → invalid
                        "not-a-uuid",          # type: ignore[list-item]  # non-uuid → invalid
                    ],
                    actor=actor,
                    project_id=ids["project"],
                )

        assert len(result.valid) == 1
        assert result.valid[0].citation_id == ids["citation"]
        assert len(result.invalid) == 2
        assert result.all_valid is False


@pytest.mark.asyncio
async def test_list_select_references_only_real_columns():
    """The router list SELECT runs against PG16 — proves no column drift on the list path.

    A seeded scope returns the row; an empty scope returns [] — both without
    ProgrammingError/UndefinedColumnError.

    **Validates: Requirements 9, 15**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)

        async with SM() as session:
            seeded = (
                await session.execute(
                    sa.text(_LIST_SQL),
                    {"pid": str(ids["project"]), "yr": 2025, "lim": 100},
                )
            ).mappings().all()
            empty = (
                await session.execute(
                    sa.text(_LIST_SQL),
                    {"pid": str(uuid.uuid4()), "yr": 2025, "lim": 100},
                )
            ).mappings().all()

        assert len(seeded) == 1
        assert str(seeded[0]["id"]) == str(ids["citation"])
        assert seeded[0]["page"] == 3
        assert empty == []
