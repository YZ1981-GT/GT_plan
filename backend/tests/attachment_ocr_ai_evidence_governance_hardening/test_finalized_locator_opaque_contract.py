"""契约：FINALIZED 附件版本的对外 file_path 恒为 opaque 定位符，绝不回退裸绝对路径。

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R14 · Design: §6.1 C3(opaque-locator), §4.3(AttachmentVersion 不可变),
        §5.1(finalize：finalized_storage 写 config_snapshot + attachment.file_path)

C3 冻结契约（file_path_boundary_freeze / 见 secure_attachment_gateway §Task3.4 注释）：
    对外 locator 只能是 opaque/脱敏定位符（``/api/attachments/{id}/download`` 或 ``paperless://``），
    **绝不返回绝对路径 / 原始 storage key / token**。

本测试是聚焦的回归守卫：一次内容 finalize 后，真实永久存储写在
``AttachmentVersion.config_snapshot['finalized_storage']`` 与 ``Attachment.file_path``
（可能是本地 **绝对路径**）。内部字节读取按 ``_effective_storage`` 以该真实位置为准是**允许**的
（read path 内部）；但任何 **对外/序列化** 投影（``SecureAttachmentGateway.project_read_locator``
与 legacy ``AttachmentService._to_dict``）都必须是 opaque。若未来回归把 finalized 版本的
``attachment.file_path`` 直接对外暴露，本测试立即失败。

覆盖：
  (a) 纯函数（无 PG）——直接构造 finalized version+attachment，走 ``_effective_storage`` 拿到
      内部真实（绝对）路径，断言两条对外投影恒 opaque 且绝不含该绝对路径。
  (b) 真实 PG16 端到端 finalize（``receive_upload`` synchronous_finalize，finalizer 返回真实绝对
      路径）——从 DB 读回 finalized 版本，断言 ``_effective_storage`` 内部为绝对路径、而
      ``project_read_locator`` 与 ``_to_dict['file_path']`` 均 opaque。无 PG 环境 graceful skip。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion
from app.services.attachment_locator import project_attachment_locator
from app.services.attachment_service import AttachmentService
from app.services.evidence_governance.frozen_contracts import ActorContext
from app.services.evidence_governance.secure_attachment_gateway import (
    SecureAttachmentGateway,
    StorageBoundaryResolver,
    _effective_storage,
    sanitize_upload_filename,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"

_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\nfinalized-evidence-bytes\n"

# 明确的"裸绝对路径" sentinel —— 绝不应出现在任何对外投影里。
_ABS_PATH_SENTINEL = "/srv/audit/storage/attachments/RAW-ABS-LEAK/evidence/report.pdf"
_PAPERLESS_LOC = "paperless://documents/7"


def _chunks(data: bytes, block: int = 16):
    for i in range(0, len(data), block):
        yield data[i : i + block]


def _is_opaque_locator(value: str) -> bool:
    """opaque = 受控下载 URL 或 paperless:// scheme（C3 唯二允许形态）。"""
    return (
        value.startswith("/api/attachments/") and value.endswith("/download")
    ) or value.startswith("paperless://")


# ===========================================================================
# (a) 纯函数：finalized version 内部真实(绝对)路径 vs 对外 opaque 投影
# ===========================================================================


class TestFinalizedLocatorPureProjection:
    def test_effective_storage_returns_raw_but_projection_is_opaque(self):
        """finalize 后 _effective_storage 以 finalized_storage 绝对路径为准（内部读取 OK），
        但 project_read_locator / _to_dict 对外投影恒 opaque，绝不含绝对路径。"""
        aid = uuid.uuid4()
        version = AttachmentVersion(
            id=uuid.uuid4(),
            attachment_id=aid,
            project_id=uuid.uuid4(),
            version_no=1,
            storage_type="local",
            # 不可变 staged locator（finalize 后保持不变）
            storage_key=f"staged://{uuid.uuid4()}",
            availability="available",
            # 真实永久存储写在 config_snapshot['finalized_storage']（绝对路径）
            config_snapshot={
                "finalized_storage": {
                    "storage_type": "local",
                    "storage_key": _ABS_PATH_SENTINEL,
                    "file_path": _ABS_PATH_SENTINEL,
                }
            },
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )
        attachment = Attachment(
            id=aid,
            project_id=version.project_id,
            file_name="report.pdf",
            file_path=_ABS_PATH_SENTINEL,  # legacy 列也可能是绝对路径
            file_type="pdf",
            file_size=len(_PDF),
            storage_type="local",
            state="available",
            current_version_id=version.id,
        )

        # 内部读取解析：以 finalized_storage 绝对路径为准（这是 read path 内部，允许）。
        s_type, s_key = _effective_storage(version, attachment)
        assert s_key == _ABS_PATH_SENTINEL, "内部读取应回退 finalized_storage 真实路径"
        assert s_type == "local"

        # 对外投影 1：治理网关 project_read_locator。
        resolver = StorageBoundaryResolver([])
        gw_locator = resolver.project_read_locator(aid, storage_key=s_key)
        assert _is_opaque_locator(gw_locator), f"网关投影非 opaque: {gw_locator!r}"
        assert _ABS_PATH_SENTINEL not in gw_locator
        assert gw_locator == f"/api/attachments/{aid}/download"

        # 对外投影 2：legacy AttachmentService._to_dict（不需 DB —— 纯序列化）。
        svc = AttachmentService(db=None)  # _to_dict 不触库
        projected = svc._to_dict(attachment)
        assert _is_opaque_locator(projected["file_path"]), (
            f"_to_dict.file_path 非 opaque: {projected['file_path']!r}"
        )
        assert _ABS_PATH_SENTINEL not in projected["file_path"]
        # 共享单一真源投影一致
        assert projected["file_path"] == project_attachment_locator(
            aid, storage_type="local", storage_key=_ABS_PATH_SENTINEL
        )

    def test_paperless_finalized_projects_to_paperless_scheme(self):
        """finalized_storage 为 paperless 时，投影为 paperless:// opaque scheme（非绝对路径）。"""
        aid = uuid.uuid4()
        version = AttachmentVersion(
            id=uuid.uuid4(),
            attachment_id=aid,
            project_id=uuid.uuid4(),
            version_no=1,
            storage_type="paperless",
            storage_key=f"staged://{uuid.uuid4()}",
            availability="available",
            config_snapshot={
                "finalized_storage": {
                    "storage_type": "paperless",
                    "storage_key": _PAPERLESS_LOC,
                    "file_path": _PAPERLESS_LOC,
                }
            },
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )
        attachment = Attachment(
            id=aid,
            project_id=version.project_id,
            file_name="reply.pdf",
            file_path=_PAPERLESS_LOC,
            file_type="pdf",
            file_size=1,
            storage_type="paperless",
            state="available",
            current_version_id=version.id,
        )
        s_type, s_key = _effective_storage(version, attachment)
        assert s_key == _PAPERLESS_LOC

        resolver = StorageBoundaryResolver([])
        assert resolver.project_read_locator(aid, storage_key=s_key) == _PAPERLESS_LOC

        svc = AttachmentService(db=None)
        assert svc._to_dict(attachment)["file_path"] == _PAPERLESS_LOC

    def test_config_snapshot_missing_falls_back_to_attachment_but_still_opaque(self):
        """即便 finalized_storage 缺失、回退 attachment.file_path(绝对路径)，投影仍 opaque。"""
        aid = uuid.uuid4()
        version = AttachmentVersion(
            id=uuid.uuid4(),
            attachment_id=aid,
            project_id=uuid.uuid4(),
            version_no=1,
            storage_type="local",
            storage_key=f"staged://{uuid.uuid4()}",
            availability="available",
            config_snapshot=None,  # 无 finalized_storage → 回退 attachment
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )
        attachment = Attachment(
            id=aid,
            project_id=version.project_id,
            file_name="report.pdf",
            file_path=_ABS_PATH_SENTINEL,
            file_type="pdf",
            file_size=1,
            storage_type="local",
            state="available",
            current_version_id=version.id,
        )
        _s_type, s_key = _effective_storage(version, attachment)
        assert s_key == _ABS_PATH_SENTINEL  # 内部回退真实路径

        resolver = StorageBoundaryResolver([])
        locator = resolver.project_read_locator(aid, storage_key=s_key)
        assert _is_opaque_locator(locator)
        assert _ABS_PATH_SENTINEL not in locator


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
    tmp_db = f"evgov_loc_{uuid.uuid4().hex[:12]}"

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


def _make_finalizer(file_path: str, storage_type: str = "local"):
    async def _finalizer(*, project_id, file_name, content, media_type):
        return {"storage_type": storage_type, "storage_key": file_path, "file_path": file_path}

    return _finalizer


# ===========================================================================
# (b) 真实 PG16：端到端 finalize → 读回 finalized 版本 → 断言对外投影 opaque
# ===========================================================================


@pytest.mark.asyncio
async def test_pg_finalized_version_outward_projection_never_raw_path(tmp_path):
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        # 同步 finalize：finalizer 返回真实绝对路径（模拟本地存储 abs path）。
        async with SM() as s:
            gw = SecureAttachmentGateway(
                s,
                storage_finalizer=_make_finalizer(_ABS_PATH_SENTINEL, "local"),
                chunk_size=32,
            )
            receipt = await gw.receive_upload(
                project_id=ids["project"],
                audit_year=2025,
                raw_file_name="report.pdf",
                declared_media_type="application/pdf",
                chunks=_chunks(_PDF, 32),
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                idempotency_key=f"loc-{uuid.uuid4().hex[:8]}",
                synchronous_finalize=True,
            )
            assert receipt.outcome == "accepted"
            assert receipt.availability == "available"
            att_id = receipt.attachment_id
            ver_id = receipt.attachment_version_id

        # 读回 finalized 版本 + 附件。
        async with SM() as s:
            version = await s.get(AttachmentVersion, ver_id)
            attachment = await s.get(Attachment, att_id)
            assert version is not None and attachment is not None
            assert version.availability == "available"

            # 内部读取解析：以 finalized_storage 绝对路径为准（read path 内部，允许）。
            s_type, s_key = _effective_storage(version, attachment)
            assert s_key == _ABS_PATH_SENTINEL, "finalized 版本内部应解析到真实绝对路径"
            # DB 中 attachment.file_path 也被写成绝对路径（legacy 列）。
            assert attachment.file_path == _ABS_PATH_SENTINEL

            # 边界解析器把该绝对路径判为越界（read path C2 会据此拒绝）——顺带验证。
            resolver = StorageBoundaryResolver(
                [str(tmp_path / "attach"), str(tmp_path / "storage")]
            )
            assert resolver.resolve_read_plan(s_type, s_key).rejected

            # ---- 对外投影 1：治理网关 project_read_locator（C3）----
            gw_locator = gw._storage_boundary.project_read_locator(att_id, storage_key=s_key)
            assert _is_opaque_locator(gw_locator)
            assert _ABS_PATH_SENTINEL not in gw_locator
            assert gw_locator == f"/api/attachments/{att_id}/download"

            # ---- 对外投影 2：legacy AttachmentService._to_dict / get_attachment ----
            svc = AttachmentService(s)
            projected = svc._to_dict(attachment)
            assert _is_opaque_locator(projected["file_path"]), (
                f"finalized 版本对外 file_path 泄露非 opaque: {projected['file_path']!r}"
            )
            assert _ABS_PATH_SENTINEL not in projected["file_path"]

            fetched = await svc.get_attachment(att_id)
            assert fetched is not None
            assert _ABS_PATH_SENTINEL not in fetched["file_path"]
            assert _is_opaque_locator(fetched["file_path"])


@pytest.mark.asyncio
async def test_pg_finalized_paperless_version_projects_scheme(tmp_path):
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)

        async with SM() as s:
            gw = SecureAttachmentGateway(
                s,
                storage_finalizer=_make_finalizer(_PAPERLESS_LOC, "paperless"),
                chunk_size=32,
            )
            receipt = await gw.receive_upload(
                project_id=ids["project"],
                audit_year=2025,
                raw_file_name="reply.pdf",
                declared_media_type="application/pdf",
                chunks=_chunks(_PDF, 32),
                actor=ActorContext.for_user(ids["user"]),
                actor_role="auditor",
                idempotency_key=f"loc-pl-{uuid.uuid4().hex[:8]}",
                synchronous_finalize=True,
            )
            assert receipt.outcome == "accepted"
            att_id = receipt.attachment_id

        async with SM() as s:
            attachment = await s.get(Attachment, att_id)
            svc = AttachmentService(s)
            projected = svc._to_dict(attachment)
            # paperless scheme 本身即 opaque，可安全对外。
            assert projected["file_path"] == _PAPERLESS_LOC
            assert _is_opaque_locator(projected["file_path"])
