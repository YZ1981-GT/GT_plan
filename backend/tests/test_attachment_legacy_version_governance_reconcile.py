"""Legacy AttachmentService 版本模型收敛 — 真实 PG16 集成测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Baseline: R2 / R9 / §4.1 / §4.3 / §5.1
Properties: P4（版本不可变/递增）, P20（stale 传播）

背景：平台在 strangler 期并存两套版本模型 —— legacy ``AttachmentService``
（``attachments`` 表行式版本 ``version`` / ``previous_version_id``）与治理
``AttachmentVersion``（独立不可变表 + FOR UPDATE 父锁 + trigger）。本测试锁定对
legacy 服务的两处收敛改造，使其不再违反治理契约：

(a) 并发 legacy 版本创建不产生重复版本号（父作用域锁串行化）。
(b) 回滚绝不改写任何历史行的 file_path/字节/created_by（旧行回滚后逐字节不变）。
(c) 回滚/替换发出与治理 replace 相同的失效信号（``attachment.version_replaced``
    outbox 事件），令下游可标记 stale。
(d) 若存在治理 ``AttachmentVersion`` 链，legacy 路径被守卫：不创建分叉的治理版本行，
    仅镜像失效信号使两条链保持一致。

真实 PG 铁律（design §10.1/§10.2）：锁/并发/不可变性在真实 PG16 验证；无 PG 环境 skip。
无 ``&&``；``python`` 而非 ``python3``。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
import sqlalchemy as sa

# 确保 Attachment 的 FK 目标表（users / service_identities）与治理 ORM 表都注册进
# Base.metadata —— 否则单独运行本文件时 ORM flush 排表阶段无法解析 FK。
import app.models  # noqa: F401
import app.models.evidence_governance_models  # noqa: F401
from app.services.attachment_service import AttachmentService

# ---------------------------------------------------------------------------
# PG16 一次性库 harness（用完即 DROP）
# ---------------------------------------------------------------------------

# 仅建本测试需要的最小 schema：legacy attachments + 治理 attachment_versions +
# 治理 outbox（+ service_identities 供 attachments/attachment_versions 的 actor FK）。
_SCHEMA_SQL = """
CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE service_identities (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_year int, is_deleted boolean DEFAULT false
);
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
    audit_year int,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false,
    -- V106 evidence-governance additive 扩展（ORM Attachment 映射的治理列）
    original_file_name varchar(500), source_type varchar(50),
    obtained_at timestamptz, provider varchar(200),
    is_key_evidence boolean DEFAULT false,
    metadata_status varchar(20) DEFAULT 'incomplete',
    metadata_missing jsonb,
    state varchar(20) DEFAULT 'available',
    current_version_id uuid,
    actor_type varchar(20), actor_user_id uuid, actor_service_identity_id uuid,
    original_creator_unknown boolean DEFAULT false
);
CREATE TABLE attachment_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attachment_id uuid NOT NULL,
    project_id uuid NOT NULL,
    audit_year int,
    version_no int NOT NULL,
    storage_type varchar(20) DEFAULT 'local',
    storage_key varchar(500),
    media_type varchar(100),
    byte_size bigint,
    content_hash varchar(64),
    availability varchar(20) DEFAULT 'available',
    previous_version_id uuid,
    actor_type varchar(20) NOT NULL,
    actor_user_id uuid,
    actor_service_identity_id uuid,
    original_creator_unknown boolean DEFAULT false,
    created_at timestamptz DEFAULT now(),
    CONSTRAINT uq_av_attachment_version UNIQUE (attachment_id, version_no)
);
CREATE TABLE evidence_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    audit_year int,
    event_id varchar(120) NOT NULL,
    event_type varchar(100) NOT NULL,
    payload jsonb,
    status varchar(20) NOT NULL DEFAULT 'pending',
    attempt_count int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    command_root_id uuid,
    actor_type varchar(20),
    actor_user_id uuid,
    actor_service_identity_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_evidence_outbox_event UNIQUE (event_id)
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


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"legacy_ver_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            for stmt in _SCHEMA_SQL.strip().split(";"):
                if stmt.strip():
                    await conn.exec_driver_sql(stmt)
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


async def _seed(eng) -> dict:
    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            sa.text("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
    return ids


# ===========================================================================
# (a) 并发 legacy 版本创建不产生重复版本号（FOR UPDATE / advisory 父锁串行化）
# ===========================================================================


@pytest.mark.asyncio
async def test_concurrent_legacy_version_creation_no_duplicate_version_no():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        ref_id = uuid.uuid4()
        common = dict(
            file_name="合同.pdf",
            reference_id=ref_id,
            reference_type="contract",
            file_type="pdf",
        )

        # 先建初始版本 v1（链的锚点），使后续并发都是"替换现有链"。
        async with SM() as s0:
            svc0 = AttachmentService(s0)
            await svc0.create_attachment(
                ids["project"],
                {**common, "file_path": "/v1.pdf", "file_size": 1},
                created_by=ids["user"],
            )
            await s0.commit()

        n = 8

        async def _one(i: int) -> int:
            async with SM() as s:
                svc = AttachmentService(s)
                r = await svc.create_attachment(
                    ids["project"],
                    {**common, "file_path": f"/c{i}.pdf", "file_size": 100 + i},
                    created_by=ids["user"],
                )
                await s.commit()
                return r["version"]

        versions = await asyncio.gather(*[_one(i) for i in range(n)])

        # 并发替换均落到严格递增、互不重复的版本号（父锁串行化）。
        async with SM() as s2:
            rows = (
                await s2.execute(
                    sa.text(
                        "SELECT version FROM attachments "
                        "WHERE project_id = :p AND file_name = :f AND reference_id = :r "
                        "ORDER BY version"
                    ),
                    {"p": ids["project"], "f": "合同.pdf", "r": ref_id},
                )
            ).scalars().all()

        # v1 + n 个并发替换 → 版本号恰为 1..n+1，无重复、无缺号。
        assert rows == list(range(1, n + 2)), f"版本号出现重复/缺号: {rows}"
        assert len(set(rows)) == len(rows)


# ===========================================================================
# (b) 回滚绝不改写任何历史行（旧行 file_path/字节/created_by 逐字节不变）
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_never_mutates_prior_rows():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as s:
            svc = AttachmentService(s)
            v1 = await svc.create_attachment(
                ids["project"],
                {"file_name": "d.pdf", "file_path": "/v1.pdf", "file_type": "pdf",
                 "file_size": 100, "ocr_text": "内容一"},
                created_by=ids["user"],
            )
            v2 = await svc.create_attachment(
                ids["project"],
                {"file_name": "d.pdf", "file_path": "/v2.pdf", "file_type": "pdf",
                 "file_size": 200, "ocr_text": "内容二"},
                created_by=ids["user"],
            )
            await s.commit()

        # 快照旧行的真实存储字段（对外投影 opaque，用内部通道取真实值）。
        async def _raw_snapshot(session, att_id):
            row = (
                await session.execute(
                    sa.text(
                        "SELECT file_path, file_size, ocr_text, created_by, version "
                        "FROM attachments WHERE id = :i"
                    ),
                    {"i": att_id},
                )
            ).mappings().first()
            return dict(row)

        async with SM() as s:
            before_v1 = await _raw_snapshot(s, v1["id"])
            before_v2 = await _raw_snapshot(s, v2["id"])

        # 回滚 v2 → 取 v1 重建为 v3。
        async with SM() as s:
            svc = AttachmentService(s)
            v3 = await svc.rollback_to_version(
                attachment_id=uuid.UUID(v2["id"]),
                version_id=uuid.UUID(v1["id"]),
                created_by=ids["user"],
            )
            await s.commit()

        async with SM() as s:
            after_v1 = await _raw_snapshot(s, v1["id"])
            after_v2 = await _raw_snapshot(s, v2["id"])
            v3_raw = await _raw_snapshot(s, v3["id"])

        # 旧行逐字段不变（只 INSERT 新行，绝不 UPDATE 历史行）。
        assert after_v1 == before_v1
        assert after_v2 == before_v2
        # 新行是 v3，复制 v1 的字节，actor 落库。
        assert v3_raw["version"] == 3
        assert v3_raw["file_path"] == "/v1.pdf"
        assert v3_raw["file_size"] == 100
        assert str(v3_raw["created_by"]) == str(ids["user"])


# ===========================================================================
# (c) 回滚 / 替换发出与治理 replace 相同的失效信号（下游可标记 stale）
# ===========================================================================


async def _outbox_events(session, event_type: str = "attachment.version_replaced"):
    rows = (
        await session.execute(
            sa.text(
                "SELECT event_id, event_type, payload FROM evidence_outbox "
                "WHERE event_type = :t ORDER BY created_at"
            ),
            {"t": event_type},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@pytest.mark.asyncio
async def test_replace_and_rollback_emit_stale_signal():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as s:
            svc = AttachmentService(s)
            v1 = await svc.create_attachment(
                ids["project"],
                {"file_name": "e.pdf", "file_path": "/v1.pdf", "file_type": "pdf", "file_size": 1},
                created_by=ids["user"],
            )
            await s.commit()

        # 首版上传不应发失效信号。
        async with SM() as s:
            assert await _outbox_events(s) == []

        # 替换（version=2）→ 发一条 attachment.version_replaced。
        async with SM() as s:
            svc = AttachmentService(s)
            v2 = await svc.create_attachment(
                ids["project"],
                {"file_name": "e.pdf", "file_path": "/v2.pdf", "file_type": "pdf", "file_size": 2},
                created_by=ids["user"],
            )
            await s.commit()

        async with SM() as s:
            evs = await _outbox_events(s)
            assert len(evs) == 1
            p = evs[0]["payload"]
            assert p["new_version_no"] == 2
            assert p["origin"] == "legacy_attachment_service"
            assert p["previous_version_id"] == v1["id"]

        # 回滚 → 再发一条独立失效信号。
        async with SM() as s:
            svc = AttachmentService(s)
            await svc.rollback_to_version(
                attachment_id=uuid.UUID(v2["id"]),
                version_id=uuid.UUID(v1["id"]),
                created_by=ids["user"],
            )
            await s.commit()

        async with SM() as s:
            evs = await _outbox_events(s)
            assert len(evs) == 2  # 每次新版本各一条，event_id 互不相同（幂等键唯一）
            assert len({e["event_id"] for e in evs}) == 2
            assert evs[-1]["payload"]["new_version_no"] == 3


# ===========================================================================
# (d) 存在治理 AttachmentVersion 链时：legacy 路径被守卫（不分叉治理链 + 镜像信号）
# ===========================================================================


@pytest.mark.asyncio
async def test_governed_chain_present_legacy_path_guarded_and_mirrors_signal():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        # 建一条 legacy 链 v1/v2，并为 v1（治理聚合根锚点）种入一条治理 AttachmentVersion 链。
        async with SM() as s:
            svc = AttachmentService(s)
            v1 = await svc.create_attachment(
                ids["project"],
                {"file_name": "g.pdf", "file_path": "/v1.pdf", "file_type": "pdf", "file_size": 1},
                created_by=ids["user"],
            )
            v2 = await svc.create_attachment(
                ids["project"],
                {"file_name": "g.pdf", "file_path": "/v2.pdf", "file_type": "pdf", "file_size": 2},
                created_by=ids["user"],
            )
            # 治理链锚定在 v1（rollback 契约1 的 target=v1）。
            await s.execute(
                sa.text(
                    "INSERT INTO attachment_versions "
                    "(id, attachment_id, project_id, audit_year, version_no, actor_type, "
                    " actor_user_id, availability) "
                    "VALUES (:id, :aid, :p, 2025, 1, 'user', :u, 'available')"
                ),
                {"id": uuid.uuid4(), "aid": v1["id"], "p": ids["project"], "u": ids["user"]},
            )
            await s.commit()

        async with SM() as s:
            gov_before = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM attachment_versions WHERE attachment_id = :a"
                    ),
                    {"a": v1["id"]},
                )
            ).scalar()

        # legacy 回滚（target=v1，已被治理）。
        async with SM() as s:
            svc = AttachmentService(s)
            v3 = await svc.rollback_to_version(
                attachment_id=uuid.UUID(v2["id"]),
                version_id=uuid.UUID(v1["id"]),
                created_by=ids["user"],
            )
            await s.commit()

        async with SM() as s:
            # 守卫：治理 attachment_versions 链未被 legacy 路径分叉/新增。
            gov_after = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM attachment_versions WHERE attachment_id = :a"
                    ),
                    {"a": v1["id"]},
                )
            ).scalar()
            assert gov_after == gov_before

            # legacy 路径也绝不给自己的新行创建治理版本行。
            new_gov = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM attachment_versions WHERE attachment_id = :a"
                    ),
                    {"a": v3["id"]},
                )
            ).scalar()
            assert new_gov == 0

            # 两条失效信号：v2 替换（治理链尚未种入，governed=False）+ 回滚（治理链已存在，
            # governed=True）。镜像信号发出 governed_chain_present=True，令两条链经同一信号一致。
            evs = await _outbox_events(s)
            assert len(evs) == 2
            assert evs[0]["payload"]["governed_chain_present"] is False  # v2 替换时
            assert evs[-1]["payload"]["governed_chain_present"] is True  # 回滚（target=治理v1）
