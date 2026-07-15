"""Task 2.2 — ServiceIdentity / UploadAttempt / Attachment 聚合 / 不可变 AttachmentVersion
迁移与 ORM 形状测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.2 (Wave 1)
Requirements: R1, R2, R12, R13
Design: §Data Models(actor XOR), §4.0, §4.2, §4.3
Properties: P3(actor 完备), P4(版本不可变), P5(哈希绑定), P26(RESTRICT)

覆盖（本任务范围）：
  * V106 迁移约定 lint（additive / repeatable / FK RESTRICT）。
  * V106 已按动态分配落在下一可用 V（无重复号）。
  * ORM ↔ 迁移列名/表名 parity（4 新表 + attachments 治理扩展列）。
  * actor XOR 契约与迁移/ORM 对齐（contracts.validate_actor）。
  * 真实 PG16 集成 smoke（rolled-back 事务，不落库）：DDL 有效、4 表 + 6 命名约束 +
    3 触发器存在、UploadAttempt 严格 actor XOR、AttachmentVersion immutable 触发器、
    quarantine 不可公开读取 CHECK。

注：完整的空库/历史库/中断重跑/drift/deferrable 链穷举契约套件属 Task 2.5。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.evidence_governance.contracts import (
    ACTOR_COLUMNS,
    is_valid_actor,
    validate_actor,
)
from app.services.evidence_governance.migration_allocation import (
    lint_migration_sql,
    normalize_version,
    parse_dir_versions,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106_PATH = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"

NEW_TABLES = (
    "service_identities",
    "evidence_upload_attempts",
    "evidence_quarantine_handles",
    "attachment_versions",
)
NAMED_CONSTRAINTS = (
    "uq_attachments_scope",
    "uq_av_scope_identity",
    "uq_av_attachment_version",
    "fk_av_parent_scope",
    "fk_av_previous_scope",
    "fk_attachments_current_version",
)
TRIGGERS = ("trg_av_previous_link", "trg_attachment_current_link", "trg_av_immutable")


# ---------------------------------------------------------------------------
# 迁移文件存在 + 约定 lint + 动态分配落点
# ---------------------------------------------------------------------------

class TestMigrationFileConventions:
    def test_v106_exists(self):
        assert V106_PATH.is_file(), "V106 迁移文件缺失"

    def test_v106_lint_clean(self):
        sql = V106_PATH.read_text(encoding="utf-8")
        violations = lint_migration_sql(sql)
        assert violations == [], f"V106 违反迁移约定：{violations}"

    def test_v106_present_and_no_duplicate(self):
        # V106 落在动态分配的号位且无重复；不再断言"当前最高号"——
        # 后续任务的迁移（如 Task 2.3 的 V107）会合法地叠加在其之上。
        filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
        by = parse_dir_versions(filenames)
        dupes = {v: names for v, names in by.items() if len(names) > 1}
        assert dupes == {}, f"重复版本号：{dupes}"
        assert 106 in by, "V106 未在目录中"

    def test_v106_is_additive_no_destructive(self):
        # 剥离行注释后再检查破坏性语句（注释里记录"不含 DROP TABLE 等"是合法说明）
        import re
        sql = re.sub(r"--[^\n]*", "", V106_PATH.read_text(encoding="utf-8")).upper()
        assert "DROP TABLE" not in sql
        assert "DROP COLUMN" not in sql
        assert "TRUNCATE" not in sql

    def test_v106_creates_expected_tables_and_objects(self):
        import re
        raw = V106_PATH.read_text(encoding="utf-8")
        sql = re.sub(r"--[^\n]*", "", raw)  # 剥离行注释
        for t in NEW_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {t}" in sql, f"缺 CREATE TABLE {t}"
        for c in NAMED_CONSTRAINTS:
            assert c in sql, f"缺命名约束 {c}"
        for trg in TRIGGERS:
            assert trg in sql, f"缺触发器 {trg}"
        # 循环 FK 分阶段：current_version 复合 FK 与 previous 复合 FK 均 DEFERRABLE
        assert "DEFERRABLE INITIALLY DEFERRED" in sql
        # 冗余 hash unique 有意不创建
        assert "content_hash,version_no" not in sql.replace(" ", "")


# ---------------------------------------------------------------------------
# actor XOR 契约（contracts 单一真源）
# ---------------------------------------------------------------------------

class TestActorContract:
    def test_actor_columns_frozen(self):
        assert ACTOR_COLUMNS == ("actor_type", "actor_user_id", "actor_service_identity_id")

    def test_anonymous_rejected(self):
        # actor_type NULL / 未知 → 拒绝（P3 no-anonymous）
        assert not is_valid_actor(None, None, None)
        assert not is_valid_actor(None, str(uuid.uuid4()), None)
        assert validate_actor("bogus", str(uuid.uuid4()), None) is not None

    def test_user_and_service_xor(self):
        u = str(uuid.uuid4())
        s = str(uuid.uuid4())
        assert is_valid_actor("user", u, None)
        assert is_valid_actor("service", None, s)
        # 双设 / 错配 → 拒绝
        assert not is_valid_actor("user", u, s)
        assert not is_valid_actor("service", u, s)
        assert not is_valid_actor("user", None, None)
        assert not is_valid_actor("service", None, None)

    def test_strict_actor_xor_check_in_new_tables(self):
        """新表（无 legacy 行）使用严格 XOR（actor_type NOT NULL），迁移含对应 CHECK。"""
        sql = V106_PATH.read_text(encoding="utf-8")
        for name in ("chk_upload_attempt_actor_xor", "chk_quarantine_actor_xor", "chk_av_actor_xor"):
            assert name in sql, f"缺严格 actor XOR CHECK {name}"
        # attachments 走宽松版（允许 legacy actor_type IS NULL 祖父化）
        assert "chk_attachments_actor_xor" in sql
        assert "actor_type IS NULL" in sql


# ---------------------------------------------------------------------------
# ORM ↔ 迁移 parity
# ---------------------------------------------------------------------------

class TestOrmMigrationParity:
    def _orm_tables(self):
        # 触发模型注册
        import app.models  # noqa: F401
        from app.models.attachment_models import Attachment
        from app.models.evidence_governance_models import (
            AttachmentVersion,
            QuarantineHandle,
            ServiceIdentity,
            UploadAttempt,
        )
        return {
            "service_identities": ServiceIdentity,
            "evidence_upload_attempts": UploadAttempt,
            "evidence_quarantine_handles": QuarantineHandle,
            "attachment_versions": AttachmentVersion,
            "attachments": Attachment,
        }

    def test_orm_columns_present_in_migration(self):
        sql = V106_PATH.read_text(encoding="utf-8")
        tables = self._orm_tables()
        # attachments 的 legacy 列不在 V106（早期迁移建），只校验治理扩展列。
        legacy_attachment_cols = {
            "id", "project_id", "file_name", "file_path", "file_type", "file_size",
            "attachment_type", "reference_id", "reference_type", "storage_type",
            "paperless_document_id", "ocr_status", "ocr_text", "ocr_fields_cache",
            "is_deleted", "created_by", "created_at", "updated_at", "version",
            "previous_version_id",
        }
        for tname, model in tables.items():
            for col in model.__table__.columns:
                if tname == "attachments" and col.name in legacy_attachment_cols:
                    continue
                assert col.name in sql, f"ORM 列 {tname}.{col.name} 未出现在 V106 迁移"

    def test_new_tables_carry_actor_columns(self):
        tables = self._orm_tables()
        for tname in ("evidence_upload_attempts", "evidence_quarantine_handles", "attachment_versions"):
            cols = {c.name for c in tables[tname].__table__.columns}
            assert set(ACTOR_COLUMNS) <= cols, f"{tname} 缺 actor XOR 列"

    def test_attachment_version_has_composite_unique(self):
        from app.models.evidence_governance_models import AttachmentVersion
        uniques = {
            tuple(c.name for c in con.columns)
            for con in AttachmentVersion.__table__.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        }
        assert ("id", "attachment_id", "project_id", "audit_year") in uniques
        assert ("attachment_id", "version_no") in uniques

    def test_attachment_aggregate_has_scope_unique(self):
        from app.models.attachment_models import Attachment
        uniques = {
            tuple(c.name for c in con.columns)
            for con in Attachment.__table__.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        }
        assert ("id", "project_id", "audit_year") in uniques


# ---------------------------------------------------------------------------
# 真实 PG16 集成 smoke（rolled-back 事务，不落库；非 PG 环境 skip）
# ---------------------------------------------------------------------------

def _split(sql: str) -> list[str]:
    from app.core.migration_runner import MigrationRunner
    return MigrationRunner._split_sql_statements(sql)


@pytest.mark.asyncio
async def test_v106_applies_on_real_pg_and_enforces_invariants():
    """在 rolled-back 事务中应用 V106，验证 DDL 有效 + 关键约束/触发器行为。

    完整 empty/historical/rerun/drift/deferrable-链穷举 → Task 2.5。
    """
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql"):
        pytest.skip("V106 集成 smoke 需真实 PostgreSQL 16")

    # 自建引擎（NullPool）绑定当前事件循环，避免复用全局 engine 跨 function-scoped loop 的连接。
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(db_url, poolclass=NullPool, connect_args=connect_args)

    sql = V106_PATH.read_text(encoding="utf-8")
    stmts = _split(sql)

    conn = await engine.connect()
    trans = await conn.begin()
    try:
        for s in stmts:
            await conn.exec_driver_sql(s)

        # 1) 4 表存在
        for t in NEW_TABLES:
            r = await conn.exec_driver_sql(f"SELECT to_regclass('public.{t}')")
            assert r.scalar() is not None, f"表 {t} 未创建"

        # 2) 6 命名约束 + 3 触发器存在
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_constraint WHERE conname = ANY(:names)"),
            {"names": list(NAMED_CONSTRAINTS)},
        )
        assert r.scalar() == len(NAMED_CONSTRAINTS)
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_trigger WHERE tgname = ANY(:names)"),
            {"names": list(TRIGGERS)},
        )
        assert r.scalar() == len(TRIGGERS)

        # 迁移专用 Service Identity 已 seed
        r = await conn.exec_driver_sql(
            "SELECT id FROM service_identities WHERE identity_key = 'migration'"
        )
        svc_id = r.scalar()
        assert svc_id is not None

        # 取一个真实 project 做 FK 目标；无则跳过行为断言
        r = await conn.exec_driver_sql("SELECT id FROM projects LIMIT 1")
        project_id = r.scalar()
        if project_id is None:
            pytest.skip("无可用 project，跳过行为断言（DDL 已验证）")

        # 3) UploadAttempt 严格 actor XOR：匿名（actor_type NULL）被拒
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO evidence_upload_attempts "
                        "(id, project_id, sanitized_file_name, actor_type) "
                        "VALUES (gen_random_uuid(), :pid, 'x.pdf', NULL)"
                    ),
                    {"pid": project_id},
                )
            await sp.rollback()

        # service actor 合法
        r = await conn.execute(
            _text(
                "INSERT INTO evidence_upload_attempts "
                "(id, project_id, sanitized_file_name, actor_type, actor_service_identity_id) "
                "VALUES (gen_random_uuid(), :pid, 'x.pdf', 'service', :svc) RETURNING id"
            ),
            {"pid": project_id, "svc": svc_id},
        )
        assert r.scalar() is not None

        # 4) quarantine 不可公开读取 CHECK：is_publicly_readable=true 被拒
        r = await conn.execute(
            _text(
                "INSERT INTO evidence_upload_attempts "
                "(id, project_id, sanitized_file_name, actor_type, actor_service_identity_id) "
                "VALUES (gen_random_uuid(), :pid, 'q.pdf', 'service', :svc) RETURNING id"
            ),
            {"pid": project_id, "svc": svc_id},
        )
        attempt_id = r.scalar()
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO evidence_quarantine_handles "
                        "(id, upload_attempt_id, project_id, storage_key, is_publicly_readable, "
                        " actor_type, actor_service_identity_id) "
                        "VALUES (gen_random_uuid(), :aid, :pid, 'k', true, 'service', :svc)"
                    ),
                    {"aid": attempt_id, "pid": project_id, "svc": svc_id},
                )
            await sp.rollback()

        # 5) AttachmentVersion immutable 触发器：建父附件 + v1，再改 content_hash 被拒
        att_id = uuid.uuid4()
        await conn.execute(
            _text(
                "INSERT INTO attachments "
                "(id, project_id, file_name, file_path, file_type, file_size, audit_year, "
                " state, actor_type, actor_service_identity_id) "
                "VALUES (:aid, :pid, 'f.pdf', 'opaque', 'pdf', 10, 2025, 'available', 'service', :svc)"
            ),
            {"aid": att_id, "pid": project_id, "svc": svc_id},
        )
        ver_id = uuid.uuid4()
        await conn.execute(
            _text(
                "INSERT INTO attachment_versions "
                "(id, attachment_id, project_id, audit_year, version_no, availability, "
                " content_hash, actor_type, actor_service_identity_id) "
                "VALUES (:vid, :aid, :pid, 2025, 1, 'available', :h, 'service', :svc)"
            ),
            {"vid": ver_id, "aid": att_id, "pid": project_id,
             "h": "a" * 64, "svc": svc_id},
        )
        # 改可变列 availability → 允许
        await conn.execute(
            _text("UPDATE attachment_versions SET availability='inactive' WHERE id=:vid"),
            {"vid": ver_id},
        )
        # 改不可变 content_hash → 被 immutable 触发器拒绝
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text("UPDATE attachment_versions SET content_hash=:h WHERE id=:vid"),
                    {"vid": ver_id, "h": "b" * 64},
                )
            await sp.rollback()

        # 6) version_no 唯一：同 attachment 再插 version_no=1 被拒
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO attachment_versions "
                        "(id, attachment_id, project_id, audit_year, version_no, availability, "
                        " actor_type, actor_service_identity_id) "
                        "VALUES (gen_random_uuid(), :aid, :pid, 2025, 1, 'available', 'service', :svc)"
                    ),
                    {"aid": att_id, "pid": project_id, "svc": svc_id},
                )
            await sp.rollback()
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()
