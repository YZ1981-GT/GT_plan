"""Task 2.3 — legacy_attachment_alias / 持久 EvidenceRef / EvidenceDependency
迁移与 ORM 形状 + 真实 PG16 行为测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.3 (Wave 1)
Requirements: R3, R4, R9, R14
Design: §4.1（legacy_attachment_alias）, §4.4（持久 EvidenceRef + EvidenceDependency）
Properties: P1(项目隔离), P6(Ref 完整性), P7(活动 intent/边幂等), P8(双向一致),
            P20(canonical edge hash 去重), P28(迁移幂等)

覆盖（本任务范围）：
  * V107 迁移约定 lint（additive / repeatable / FK RESTRICT）+ 动态分配落点（最高号 / 无重复）。
  * 冻结契约 parity：EVIDENCE_REF_PERSISTENT_COLUMNS / EVIDENCE_REF_ACTIVE_INTENT_UNIQUE /
    EVIDENCE_REF_STATUSES / LEGACY_ALIAS_COLUMNS / LegacyResolutionKind ↔ 迁移/ORM。
  * ORM ↔ 迁移列名/表名 parity（3 新表）。
  * 真实 PG16 集成 smoke（rolled-back，不落库）：DDL 有效、3 表 + partial-unique +
    双向索引存在、活动 intent partial unique 幂等、canonical edge_hash 去重、
    actor XOR、resolution_kind CHECK、复合 scope FK。

注：完整 empty/historical/interrupt/drift/composite/trigger 穷举契约套件属 Task 2.5。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from app.services.evidence_governance.contracts import (
    ACTOR_COLUMNS,
    EVIDENCE_REF_ACTIVE_INTENT_UNIQUE,
    EVIDENCE_REF_PERSISTENT_COLUMNS,
    EVIDENCE_REF_STATUSES,
    LEGACY_ALIAS_COLUMNS,
    LEGACY_RESOLUTION_KINDS,
)
from app.services.evidence_governance.migration_allocation import (
    lint_migration_sql,
    parse_dir_versions,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106_PATH = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107_PATH = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"

NEW_TABLES = ("legacy_attachment_alias", "evidence_refs", "evidence_dependencies")
NAMED_CONSTRAINTS = (
    "chk_legacy_alias_resolution_kind",
    "fk_legacy_alias_attachment_scope",
    "fk_legacy_alias_version_scope",
    "chk_evidence_ref_status",
    "chk_evidence_ref_actor_xor",
    "chk_evidence_dep_status",
    "chk_evidence_dep_actor_xor",
)
PARTIAL_UNIQUE_INDEXES = ("uq_evidence_ref_active_intent", "uq_evidence_dep_active_edge")
BIDIRECTIONAL_INDEXES = (
    "idx_evidence_ref_source",
    "idx_evidence_ref_evidence",
    "idx_evidence_dep_source",
    "idx_evidence_dep_target",
    "idx_evidence_dep_edge_hash",
)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


# ---------------------------------------------------------------------------
# 迁移文件存在 + 约定 lint + 动态分配落点
# ---------------------------------------------------------------------------

class TestMigrationFileConventions:
    def test_v107_exists(self):
        assert V107_PATH.is_file(), "V107 迁移文件缺失"

    def test_v107_lint_clean(self):
        sql = V107_PATH.read_text(encoding="utf-8")
        violations = lint_migration_sql(sql)
        assert violations == [], f"V107 违反迁移约定：{violations}"

    def test_v107_no_duplicate_and_is_highest(self):
        filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
        by = parse_dir_versions(filenames)
        dupes = {v: names for v, names in by.items() if len(names) > 1}
        assert dupes == {}, f"重复版本号：{dupes}"
        assert 107 in by, "V107 未在目录中"
        # V107 落地时为最高号；后续 wave（如 Task 2.4 的 V108）会追加更高号，故此处不再断言等于 107。
        assert max(by) >= 107, f"目录最高号应 >= 107，实际={max(by)}"

    def test_v107_additive_no_destructive(self):
        sql = _strip_comments(V107_PATH.read_text(encoding="utf-8")).upper()
        assert "DROP TABLE" not in sql
        assert "DROP COLUMN" not in sql
        assert "TRUNCATE" not in sql

    def test_v107_creates_expected_objects(self):
        sql = _strip_comments(V107_PATH.read_text(encoding="utf-8"))
        for t in NEW_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {t}" in sql, f"缺 CREATE TABLE {t}"
        for c in NAMED_CONSTRAINTS:
            assert c in sql, f"缺命名约束 {c}"
        for idx in PARTIAL_UNIQUE_INDEXES + BIDIRECTIONAL_INDEXES:
            assert idx in sql, f"缺索引 {idx}"
        # partial unique 均带 WHERE status='active'
        assert sql.count("WHERE status = 'active'") >= 2
        # 复合 scope FK RESTRICT
        assert "REFERENCES attachments(id, project_id, audit_year) ON DELETE RESTRICT" in sql
        assert (
            "REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT"
            in sql
        )


# ---------------------------------------------------------------------------
# 冻结契约 parity（contracts 单一真源）
# ---------------------------------------------------------------------------

class TestFrozenContractParity:
    def test_evidence_ref_persistent_columns_present_in_migration(self):
        sql = V107_PATH.read_text(encoding="utf-8")
        for col in EVIDENCE_REF_PERSISTENT_COLUMNS:
            assert col in sql, f"EvidenceRef 冻结列 {col} 未出现在 V107"

    def test_active_intent_unique_matches_frozen(self):
        # 冻结 active-intent 唯一键 = (project_id, audit_year, intent_hash)
        assert EVIDENCE_REF_ACTIVE_INTENT_UNIQUE == ("project_id", "audit_year", "intent_hash")
        sql = _strip_comments(V107_PATH.read_text(encoding="utf-8"))
        assert "uq_evidence_ref_active_intent" in sql
        # 索引列顺序与冻结键一致
        m = re.search(
            r"uq_evidence_ref_active_intent\s+ON\s+evidence_refs\s*\(([^)]*)\)",
            sql,
            re.IGNORECASE,
        )
        assert m, "找不到 uq_evidence_ref_active_intent 索引定义"
        cols = tuple(c.strip() for c in m.group(1).split(","))
        assert cols == EVIDENCE_REF_ACTIVE_INTENT_UNIQUE

    def test_evidence_ref_statuses_frozen(self):
        assert EVIDENCE_REF_STATUSES == frozenset({"active", "inactive"})

    def test_legacy_alias_columns_present_in_migration(self):
        sql = V107_PATH.read_text(encoding="utf-8")
        for col in LEGACY_ALIAS_COLUMNS:
            assert col in sql, f"legacy_attachment_alias 冻结列 {col} 未出现在 V107"

    def test_legacy_resolution_kinds_in_check(self):
        sql = V107_PATH.read_text(encoding="utf-8")
        for kind in LEGACY_RESOLUTION_KINDS:
            assert f"'{kind}'" in sql, f"resolution_kind CHECK 缺 {kind}"


# ---------------------------------------------------------------------------
# ORM ↔ 迁移 parity
# ---------------------------------------------------------------------------

class TestOrmMigrationParity:
    def _orm_tables(self):
        import app.models  # noqa: F401
        from app.models.evidence_governance_models import (
            EvidenceDependency,
            EvidenceRef,
            LegacyAttachmentAlias,
        )
        return {
            "legacy_attachment_alias": LegacyAttachmentAlias,
            "evidence_refs": EvidenceRef,
            "evidence_dependencies": EvidenceDependency,
        }

    def test_orm_columns_present_in_migration(self):
        sql = V107_PATH.read_text(encoding="utf-8")
        for tname, model in self._orm_tables().items():
            for col in model.__table__.columns:
                assert col.name in sql, f"ORM 列 {tname}.{col.name} 未出现在 V107"

    def test_evidence_ref_orm_covers_frozen_persistent_columns(self):
        from app.models.evidence_governance_models import EvidenceRef
        cols = {c.name for c in EvidenceRef.__table__.columns}
        missing = set(EVIDENCE_REF_PERSISTENT_COLUMNS) - cols
        assert missing == set(), f"EvidenceRef ORM 缺冻结持久列：{missing}"

    def test_legacy_alias_orm_covers_frozen_columns(self):
        from app.models.evidence_governance_models import LegacyAttachmentAlias
        cols = {c.name for c in LegacyAttachmentAlias.__table__.columns}
        missing = set(LEGACY_ALIAS_COLUMNS) - cols
        assert missing == set(), f"LegacyAttachmentAlias ORM 缺冻结列：{missing}"

    def test_new_tables_carry_actor_columns(self):
        for tname in ("evidence_refs", "evidence_dependencies"):
            cols = {c.name for c in self._orm_tables()[tname].__table__.columns}
            assert set(ACTOR_COLUMNS) <= cols, f"{tname} 缺 actor XOR 列"

    def test_evidence_ref_active_intent_partial_unique_index(self):
        from app.models.evidence_governance_models import EvidenceRef
        idx = {
            i.name: i for i in EvidenceRef.__table__.indexes
        }.get("uq_evidence_ref_active_intent")
        assert idx is not None, "缺 uq_evidence_ref_active_intent 索引"
        assert idx.unique is True
        assert tuple(c.name for c in idx.columns) == EVIDENCE_REF_ACTIVE_INTENT_UNIQUE

    def test_evidence_dep_active_edge_partial_unique_index(self):
        from app.models.evidence_governance_models import EvidenceDependency
        idx = {
            i.name: i for i in EvidenceDependency.__table__.indexes
        }.get("uq_evidence_dep_active_edge")
        assert idx is not None, "缺 uq_evidence_dep_active_edge 索引"
        assert idx.unique is True
        assert tuple(c.name for c in idx.columns) == ("project_id", "audit_year", "edge_hash")


# ---------------------------------------------------------------------------
# 真实 PG16 集成 smoke（rolled-back 事务，不落库；非 PG 环境 skip）
# ---------------------------------------------------------------------------

def _split(sql: str) -> list[str]:
    from app.core.migration_runner import MigrationRunner
    return MigrationRunner._split_sql_statements(sql)


@pytest.mark.asyncio
async def test_v107_applies_on_real_pg_and_enforces_invariants():
    """在 rolled-back 事务中先应用 V106（前置表）再 V107，验证 DDL + 关键行为。

    完整 empty/historical/rerun/drift/composite/trigger 穷举 → Task 2.5。
    """
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql"):
        pytest.skip("V107 集成 smoke 需真实 PostgreSQL 16")

    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(db_url, poolclass=NullPool, connect_args=connect_args)

    v106_stmts = _split(V106_PATH.read_text(encoding="utf-8"))
    v107_stmts = _split(V107_PATH.read_text(encoding="utf-8"))

    conn = await engine.connect()
    trans = await conn.begin()
    try:
        # V106 前置表（idempotent），再 V107
        for s in v106_stmts + v107_stmts:
            await conn.exec_driver_sql(s)

        # 1) 3 新表存在
        for t in NEW_TABLES:
            r = await conn.exec_driver_sql(f"SELECT to_regclass('public.{t}')")
            assert r.scalar() is not None, f"表 {t} 未创建"

        # 2) 命名约束 + partial-unique + 双向索引存在
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_constraint WHERE conname = ANY(:names)"),
            {"names": list(NAMED_CONSTRAINTS)},
        )
        assert r.scalar() == len(NAMED_CONSTRAINTS)
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_indexes WHERE indexname = ANY(:names)"),
            {"names": list(PARTIAL_UNIQUE_INDEXES + BIDIRECTIONAL_INDEXES)},
        )
        assert r.scalar() == len(PARTIAL_UNIQUE_INDEXES + BIDIRECTIONAL_INDEXES)

        # partial-unique 确实是带 WHERE 的部分索引
        r = await conn.execute(
            _text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_evidence_ref_active_intent'"
            )
        )
        idxdef = r.scalar()
        assert idxdef and "WHERE" in idxdef.upper() and "ACTIVE" in idxdef.upper()

        svc_r = await conn.exec_driver_sql(
            "SELECT id FROM service_identities WHERE identity_key = 'migration'"
        )
        svc_id = svc_r.scalar()
        assert svc_id is not None

        proj_r = await conn.exec_driver_sql("SELECT id FROM projects LIMIT 1")
        project_id = proj_r.scalar()
        if project_id is None:
            pytest.skip("无可用 project，跳过行为断言（DDL 已验证）")

        # 3) 活动 intent partial unique 幂等（P7）：同 (project,year,intent_hash) 只一条 active
        intent = "c" * 64

        async def _insert_ref(status: str, intent_hash: str):
            return await conn.execute(
                _text(
                    "INSERT INTO evidence_refs "
                    "(id, project_id, audit_year, source_type, source_id, evidence_type, "
                    " evidence_id, intent_hash, status, actor_type, actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), :pid, 2025, 'workpaper_cell', 'D2!A1', "
                    " 'attachment', :eid, :ih, :st, 'service', :svc) RETURNING id"
                ),
                {"pid": project_id, "eid": str(uuid.uuid4()), "ih": intent_hash,
                 "st": status, "svc": svc_id},
            )

        r = await _insert_ref("active", intent)
        assert r.scalar() is not None
        # 重复活动同 intent → partial unique 违反
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_ref("active", intent)
            await sp.rollback()
        # 同 intent 的 inactive 允许（partial unique 只约束 active）
        r = await _insert_ref("inactive", intent)
        assert r.scalar() is not None

        # 4) actor XOR 严格：匿名（actor_type NULL）被拒
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO evidence_refs "
                        "(id, project_id, audit_year, source_type, source_id, evidence_type, "
                        " evidence_id, intent_hash, actor_type) "
                        "VALUES (gen_random_uuid(), :pid, 2025, 'wp', 's', 'attachment', 'e', :ih, NULL)"
                    ),
                    {"pid": project_id, "ih": "d" * 64},
                )
            await sp.rollback()

        # 5) canonical edge_hash 去重（P20）：同 (project,year,edge_hash) 只一条 active
        edge = "e" * 64

        async def _insert_dep(status: str, edge_hash: str):
            return await conn.execute(
                _text(
                    "INSERT INTO evidence_dependencies "
                    "(id, project_id, audit_year, source_type, source_id, target_type, "
                    " target_id, relation, edge_hash, status, actor_type, actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), :pid, 2025, 'attachment', :sid, 'workpaper_cell', "
                    " 'D2!A1', 'derived_from', :eh, :st, 'service', :svc) RETURNING id"
                ),
                {"pid": project_id, "sid": str(uuid.uuid4()), "eh": edge_hash,
                 "st": status, "svc": svc_id},
            )

        r = await _insert_dep("active", edge)
        assert r.scalar() is not None
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_dep("active", edge)
            await sp.rollback()
        # inactive 同 edge_hash 允许
        r = await _insert_dep("inactive", edge)
        assert r.scalar() is not None

        # 6) legacy_attachment_alias：resolution_kind CHECK 拒非法值
        att_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        await conn.execute(
            _text(
                "INSERT INTO attachments "
                "(id, project_id, file_name, file_path, file_type, file_size, audit_year, "
                " state, actor_type, actor_service_identity_id) "
                "VALUES (:aid, :pid, 'f.pdf', 'opaque', 'pdf', 10, 2025, 'available', 'service', :svc)"
            ),
            {"aid": att_id, "pid": project_id, "svc": svc_id},
        )
        await conn.execute(
            _text(
                "INSERT INTO attachment_versions "
                "(id, attachment_id, project_id, audit_year, version_no, availability, "
                " content_hash, actor_type, actor_service_identity_id) "
                "VALUES (:vid, :aid, :pid, 2025, 1, 'available', :h, 'service', :svc)"
            ),
            {"vid": ver_id, "aid": att_id, "pid": project_id, "h": "a" * 64, "svc": svc_id},
        )
        # 合法别名（复合 scope FK 满足）
        r = await conn.execute(
            _text(
                "INSERT INTO legacy_attachment_alias "
                "(old_attachment_id, attachment_id, attachment_version_id, project_id, audit_year, "
                " resolution_kind) "
                "VALUES (gen_random_uuid(), :aid, :vid, :pid, 2025, 'current_version') RETURNING old_attachment_id"
            ),
            {"aid": att_id, "vid": ver_id, "pid": project_id},
        )
        assert r.scalar() is not None
        # 非法 resolution_kind → CHECK 违反
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO legacy_attachment_alias "
                        "(old_attachment_id, attachment_id, attachment_version_id, project_id, "
                        " audit_year, resolution_kind) "
                        "VALUES (gen_random_uuid(), :aid, :vid, :pid, 2025, 'bogus')"
                    ),
                    {"aid": att_id, "vid": ver_id, "pid": project_id},
                )
            await sp.rollback()
        # 复合 scope FK：错 scope（audit_year 不匹配版本）→ FK 违反
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text(
                        "INSERT INTO legacy_attachment_alias "
                        "(old_attachment_id, attachment_id, attachment_version_id, project_id, "
                        " audit_year, resolution_kind) "
                        "VALUES (gen_random_uuid(), :aid, :vid, :pid, 2099, 'root')"
                    ),
                    {"aid": att_id, "vid": ver_id, "pid": project_id},
                )
            await sp.rollback()
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()
