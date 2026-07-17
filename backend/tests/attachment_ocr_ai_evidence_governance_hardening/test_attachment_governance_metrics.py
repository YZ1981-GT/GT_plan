"""附件治理低基数积压指标 —— 命名点 gauge + 计算 callable 契约。

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R12, R15 · Design: §9.3 可观测性(低基数指标)

覆盖：
  (a) 纯函数（无 PG）——``set_named_gauge`` 只接受冻结允许集内名称（未登记名被丢弃，防高基数）；
      ``get_aggregated_metrics()`` 经 ``named_gauges`` 段暴露；``buffered_bytes()`` 复用。
  (b) 真实 PG16 —— seed staged/quarantined handle（含过 TTL）+ 双模型漂移附件，运行
      ``record_attachment_governance_metrics`` callable，断言四项 gauge 与 DB 事实一致，且
      orphaned 口径与 reaper 扫描一致。无 PG 环境 graceful skip。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.attachment_governance_metrics import (
    GAUGE_BUFFER_BYTES,
    GAUGE_HANDLE_COUNT,
    GAUGE_ORPHANED_STAGED,
    GAUGE_VERSION_DRIFT,
    record_attachment_governance_metrics,
)
from app.services.evidence_governance.observability import (
    ATTACHMENT_GOVERNANCE_GAUGES,
    EvidenceGovernanceMetrics,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


class _FakeStore:
    def __init__(self, buffered: int) -> None:
        self._b = buffered

    def buffered_bytes(self) -> int:
        return self._b


# ===========================================================================
# (a) 纯函数：命名点 gauge 低基数守卫 + 聚合输出结构
# ===========================================================================


class TestNamedGaugeLowCardinality:
    def test_only_frozen_names_accepted(self):
        m = EvidenceGovernanceMetrics()
        m.set_named_gauge(GAUGE_HANDLE_COUNT, 3)
        m.set_named_gauge(GAUGE_BUFFER_BYTES, 2048)
        # 未登记名称被丢弃（防 per-attachment 高基数）
        m.set_named_gauge("attachment_" + uuid.uuid4().hex, 99)
        assert m.get_named_gauge(GAUGE_HANDLE_COUNT) == 3
        assert m.get_named_gauge(GAUGE_BUFFER_BYTES) == 2048
        agg = m.get_aggregated_metrics()
        assert "named_gauges" in agg
        assert agg["named_gauges"][GAUGE_HANDLE_COUNT] == 3
        # 只有 4 个冻结名 —— series 有界
        assert set(agg["named_gauges"]).issubset(ATTACHMENT_GOVERNANCE_GAUGES)
        assert len(agg["named_gauges"]) <= len(ATTACHMENT_GOVERNANCE_GAUGES)

    def test_reset_clears_named_gauges(self):
        m = EvidenceGovernanceMetrics()
        m.set_named_gauge(GAUGE_ORPHANED_STAGED, 5)
        m.reset()
        assert m.get_named_gauge(GAUGE_ORPHANED_STAGED) is None
        assert m.get_aggregated_metrics()["named_gauges"] == {}

    def test_four_gauge_names_are_the_frozen_set(self):
        assert ATTACHMENT_GOVERNANCE_GAUGES == {
            GAUGE_BUFFER_BYTES,
            GAUGE_HANDLE_COUNT,
            GAUGE_ORPHANED_STAGED,
            GAUGE_VERSION_DRIFT,
        }


# ===========================================================================
# PG16 集成脚手架（复用 durable-reaper wave2 约定）
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
    tmp_db = f"evgov_metrics_{uuid.uuid4().hex[:12]}"

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


async def _seed_base(eng):
    from sqlalchemy import text as T

    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"), {"i": ids["project"]}
        )
    return ids


async def _insert_handle(conn, *, project_id, user_id, state, created_at):
    from sqlalchemy import text as T

    hid = uuid.uuid4()
    attempt_id = uuid.uuid4()
    await conn.execute(
        T(
            "INSERT INTO evidence_upload_attempts "
            "(id, project_id, audit_year, sanitized_file_name, validation_outcome, "
            " actor_type, actor_user_id) "
            "VALUES (:i, :p, 2025, 'f.pdf', 'pending', 'user', :u)"
        ),
        {"i": attempt_id, "p": project_id, "u": user_id},
    )
    await conn.execute(
        T(
            "INSERT INTO evidence_quarantine_handles "
            "(id, upload_attempt_id, project_id, audit_year, storage_key, handle_state, "
            " is_publicly_readable, actor_type, actor_user_id, created_at) "
            "VALUES (:i, :a, :p, 2025, :k, :st, false, 'user', :u, :ts)"
        ),
        {
            "i": hid,
            "a": attempt_id,
            "p": project_id,
            "k": f"quarantine://{hid}",
            "st": state,
            "u": user_id,
            "ts": created_at,
        },
    )
    return hid


async def _insert_attachment_with_versions(conn, *, project_id, user_id, legacy_version, gov_max_vn):
    """插入一个既有 legacy version 又有治理 AttachmentVersion 链的附件。"""
    from sqlalchemy import text as T

    aid = uuid.uuid4()
    await conn.execute(
        T(
            "INSERT INTO attachments (id, project_id, audit_year, file_name, file_path, "
            " file_type, file_size, storage_type, version, state, is_deleted) "
            "VALUES (:i, :p, 2025, 'a.pdf', '/x/a.pdf', 'pdf', 1, 'local', :v, 'available', false)"
        ),
        {"i": aid, "p": project_id, "v": legacy_version},
    )
    for vn in range(1, gov_max_vn + 1):
        await conn.execute(
            T(
                "INSERT INTO attachment_versions "
                "(id, attachment_id, project_id, audit_year, version_no, storage_type, "
                " availability, actor_type, actor_user_id) "
                "VALUES (:i, :a, :p, 2025, :vn, 'local', 'available', 'user', :u)"
            ),
            {"i": uuid.uuid4(), "a": aid, "p": project_id, "vn": vn, "u": user_id},
        )
    return aid


# ===========================================================================
# (b) 真实 PG16：callable 计算四项 gauge 与 DB 事实一致
# ===========================================================================


@pytest.mark.asyncio
async def test_pg_record_metrics_matches_db_facts():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(timezone.utc)
    async with _throwaway_engine() as eng:
        ids = await _seed_base(eng)
        pid, uid = ids["project"], ids["user"]

        async with eng.begin() as conn:
            # 2 个"新鲜" staged（未过 TTL）+ 1 个过 TTL 的 staged + 1 个过 TTL 的 quarantined
            await _insert_handle(conn, project_id=pid, user_id=uid, state="staged", created_at=now)
            await _insert_handle(conn, project_id=pid, user_id=uid, state="staged", created_at=now)
            await _insert_handle(
                conn, project_id=pid, user_id=uid, state="staged",
                created_at=now - timedelta(seconds=7200),
            )
            await _insert_handle(
                conn, project_id=pid, user_id=uid, state="quarantined",
                created_at=now - timedelta(seconds=7200),
            )
            # 1 个已 purged（既不计 active 也不计 orphaned）
            await _insert_handle(
                conn, project_id=pid, user_id=uid, state="purged",
                created_at=now - timedelta(seconds=7200),
            )
            # 双模型漂移：legacy version=3 但治理 MAX(version_no)=1 → drift；一致的不计
            await _insert_attachment_with_versions(
                conn, project_id=pid, user_id=uid, legacy_version=3, gov_max_vn=1
            )
            await _insert_attachment_with_versions(
                conn, project_id=pid, user_id=uid, legacy_version=2, gov_max_vn=2
            )

        SM = async_sessionmaker(eng, expire_on_commit=False)
        metrics = EvidenceGovernanceMetrics()
        async with SM() as s:
            snapshot = await record_attachment_governance_metrics(
                s,
                quarantine_store=_FakeStore(4096),
                ttl_seconds=3600,
                now=now,
                metrics=metrics,
            )

        # active handle count = staged+quarantined not purged = 2 + 1 + 1 = 4
        assert snapshot[GAUGE_HANDLE_COUNT] == 4
        # orphaned = staged/quarantined past TTL (3600s) = 1 staged + 1 quarantined = 2
        assert snapshot[GAUGE_ORPHANED_STAGED] == 2
        # version drift = 1 (legacy 3 vs gov 1); the consistent one not counted
        assert snapshot[GAUGE_VERSION_DRIFT] == 1
        # buffer bytes from store
        assert snapshot[GAUGE_BUFFER_BYTES] == 4096

        # 也记录到收集器 + 经聚合输出暴露
        agg = metrics.get_aggregated_metrics()
        assert agg["named_gauges"][GAUGE_HANDLE_COUNT] == 4
        assert agg["named_gauges"][GAUGE_ORPHANED_STAGED] == 2
        assert agg["named_gauges"][GAUGE_VERSION_DRIFT] == 1
        assert agg["named_gauges"][GAUGE_BUFFER_BYTES] == 4096


@pytest.mark.asyncio
async def test_pg_orphaned_count_agrees_with_reaper_scan():
    """orphaned gauge 与 reaper 实际扫描到的 stale handle 数一致（同一 cutoff 口径）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.evidence_governance.attachment_governance_metrics import (
        count_orphaned_staged_handles,
    )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=3600)
    async with _throwaway_engine() as eng:
        ids = await _seed_base(eng)
        pid, uid = ids["project"], ids["user"]
        async with eng.begin() as conn:
            await _insert_handle(
                conn, project_id=pid, user_id=uid, state="staged",
                created_at=now - timedelta(seconds=7200),
            )
            await _insert_handle(conn, project_id=pid, user_id=uid, state="staged", created_at=now)

        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as s:
            metric_count = await count_orphaned_staged_handles(s, cutoff=cutoff)
            # 直接跑 reaper 扫描 SQL（口径应一致）
            reaper_scan = (
                await s.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM evidence_quarantine_handles "
                        "WHERE handle_state IN ('staged','quarantined') AND created_at < :c"
                    ),
                    {"c": cutoff},
                )
            ).scalar()
        assert metric_count == reaper_scan == 1
