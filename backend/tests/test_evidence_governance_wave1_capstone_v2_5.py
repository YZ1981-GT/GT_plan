"""Task 2.5 (Wave 1 capstone) — 全 Wave 1 治理模型 ORM/Pydantic/enum 同步 +
真实 PG16 空库/历史库/中断重跑/schema drift/actor·人工 FK/复合约束/trigger 契约测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.5 (Wave 1)
Requirements: R1, R2, R3, R5, R6, R11, R13, R14
Design: §Data Models, §4.0–§4.6, §8.1, §10.1, §10.2
Properties: P3(actor 完备), P4(版本不可变), P5(哈希绑定), P6(EvidenceRef 完整性),
            P7(intent 幂等), P9(OCR 状态机封闭), P11(OCR 结果不可变), P24(manifest 防覆盖),
            P25(command-root 唯一), P26(hold 保护), P28(迁移幂等守恒)

本套件是 Wave 1 的验证 capstone，覆盖：
  1. ORM ↔ 迁移(V106/V107/V108) ↔ 冻结契约(contracts) parity（跨全部 Wave 1 表 + Pydantic 枚举）。
  2. 真实 PG16（throwaway 数据库，用完即 DROP）契约：
     - 空库 apply（V106→V107→V108 全新落库，验证 27 表 + 命名约束 + 触发器齐全）；
     - 历史库 apply（在既有 legacy attachment 上 additive 加列/表 + audit_year 回填）；
     - 中断重跑幂等（重复 apply 不新增对象/行，P28）；
     - actor XOR + 人工专属 NOT NULL FK 强制（P3）；
     - 复合 scope FK + 活动 intent partial unique + deferrable 约束触发器行为；
     - immutable/append-only 触发器（AttachmentVersion / OCRResult / sealed Manifest / quality snapshot / OCRConfirmation）。
  3. schema drift 检测：SchemaDriftDetector 对治理表零漂移 + MigrationRunner checksum-drift 守卫
     （Task 2.3 finding：已应用迁移被事后编辑会静默不重跑）。

真实 PG 铁律（design §10.1/§10.2）：约束/并发/trigger/rollback 必须在真实 PostgreSQL 16 验证，
不以 SQLite 代替。无 PG 环境时相关用例 skip。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance import contracts as C

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"
# V110 additively 补齐 Wave 1 ocr_jobs 表的 next_retry_at 列（R15.4 有界指数退避；
# V108 建表时漏列）。按本仓「已应用迁移不可事后编辑、缺列靠 additive repair 迁移补跑」
# 铁律（正是 MigrationRunner.detect_checksum_drift 守卫的对象），该列由 V110 补齐而非改 V108，
# 故 Wave 1 DDL parity 语料库须纳入这条 additive 完成迁移。
V110 = MIGRATIONS_DIR / "V110__repair_procedure_row_tasks_missed_by_v105_conflict.sql"

# 全部 27 张 Wave 1 治理表（+ attachments 是既有表的 additive 扩展，另测）。
GOVERNANCE_TABLES: tuple[str, ...] = (
    # V106
    "service_identities",
    "evidence_upload_attempts",
    "evidence_quarantine_handles",
    "attachment_versions",
    # V107
    "legacy_attachment_alias",
    "evidence_refs",
    "evidence_dependencies",
    # V108
    "evidence_audit_command_roots",
    "evidence_audit_transitions",
    "ocr_jobs",
    "ocr_job_transitions",
    "ocr_results",
    "ocr_confirmations",
    "ocr_writebacks",
    "ocr_writeback_staging",
    "citation_snapshots",
    "review_evidence_snapshots",
    "review_closes",
    "archive_manifests",
    "archive_manifest_entries",
    "archive_manifest_edges",
    "legal_holds",
    "legal_hold_scopes",
    "evidence_outbox",
    "evidence_inbox",
    "evidence_migration_checkpoints",
    "evidence_quality_snapshots",
)

# 全部约束触发器 + immutable/append-only 触发器（V106/V107 3 个 + V108 9 个 = 12）。
ALL_TRIGGERS: tuple[str, ...] = (
    "trg_av_previous_link",
    "trg_attachment_current_link",
    "trg_av_immutable",
    "trg_ocr_result_immutable",
    "trg_ocr_job_transition_append_only",
    "trg_citation_snapshot_immutable",
    "trg_audit_transition_append_only",
    "trg_archive_entry_append_only",
    "trg_archive_edge_append_only",
    "trg_quality_snapshot_immutable",
    "trg_ocr_confirmation_append_only",
    "trg_archive_manifest_sealed_immutable",
)

# 关键命名约束（复合 FK / 复合 unique / 幂等 unique / command-root unique / manifest 版本 unique）。
KEY_CONSTRAINTS: tuple[str, ...] = (
    "uq_attachments_scope",
    "uq_av_scope_identity",
    "uq_av_attachment_version",
    "fk_av_parent_scope",
    "fk_av_previous_scope",
    "fk_attachments_current_version",
    "fk_legacy_alias_attachment_scope",
    "fk_legacy_alias_version_scope",
    "uq_ocr_job_idempotency",
    "uq_ocr_writeback_idempotency",
    "uq_ocr_wb_staging_idempotency",
    "uq_audit_command_root",
    "uq_archive_manifest_version",
    "uq_migration_checkpoint_batch",
    "uq_quality_snapshot_key",
)

# 人工专属 NOT NULL FK（design §Data Models；Service Identity 不得填充）。
HUMAN_ONLY_NOT_NULL_FKS: tuple[tuple[str, str], ...] = (
    ("ocr_confirmations", "confirmed_by_user_id"),
    ("ocr_writebacks", "written_by_user_id"),
    ("review_closes", "closed_by_user_id"),
)


def _all_wave1_sql() -> str:
    # V106/V107/V108 建表 + V110 additive 补齐（ocr_jobs.next_retry_at）——
    # 见 V110 常量注释：缺列靠 additive repair 迁移补齐（不改已应用迁移），
    # 故 Wave 1 表的完整 DDL 语料库须含 V110。
    return "\n".join(p.read_text(encoding="utf-8") for p in (V106, V107, V108, V110))


def _governance_orm_models() -> dict[str, type]:
    """全部 Wave 1 治理 ORM 模型（tablename -> class）。"""
    import app.models  # noqa: F401  触发注册
    from app.models import evidence_governance_models as M

    models: dict[str, type] = {}
    from app.models.base import Base

    for cls in Base.registry.mappers:
        pass  # ensure mappers configured
    for name in dir(M):
        obj = getattr(M, name)
        if isinstance(obj, type) and hasattr(obj, "__tablename__") and getattr(obj, "__table__", None) is not None:
            if obj.__module__ == M.__name__:
                models[obj.__tablename__] = obj
    return models


# ===========================================================================
# 1) 纯 parity：ORM ↔ 迁移 ↔ 冻结契约（跨全部 Wave 1 表 + Pydantic 枚举）
# ===========================================================================

class TestWave1Parity:
    def test_all_27_governance_tables_have_orm_model(self):
        models = _governance_orm_models()
        missing = [t for t in GOVERNANCE_TABLES if t not in models]
        assert missing == [], f"以下治理表无 ORM 模型：{missing}"
        assert len(GOVERNANCE_TABLES) == 27

    def test_every_orm_column_present_in_wave1_migrations(self):
        sql = _all_wave1_sql()
        models = _governance_orm_models()
        for tname in GOVERNANCE_TABLES:
            model = models[tname]
            for col in model.__table__.columns:
                assert col.name in sql, f"ORM 列 {tname}.{col.name} 未出现在 Wave 1 迁移 SQL"

    def test_attachments_governance_extension_columns_in_v106(self):
        """attachments 是既有表的 additive 扩展；治理列须在 V106（或 V107 §R0 补齐）出现。"""
        sql = V106.read_text(encoding="utf-8") + V107.read_text(encoding="utf-8")
        from app.models.attachment_models import Attachment

        gov_cols = {
            "audit_year", "original_file_name", "source_type", "obtained_at", "provider",
            "is_key_evidence", "metadata_status", "metadata_missing", "state",
            "current_version_id", "actor_type", "actor_user_id", "actor_service_identity_id",
            "original_creator_unknown",
        }
        orm_cols = {c.name for c in Attachment.__table__.columns}
        for c in gov_cols:
            assert c in orm_cols, f"Attachment ORM 缺治理列 {c}"
            assert c in sql, f"attachments 治理列 {c} 未在 V106/V107 迁移出现"

    def test_actor_xor_is_all_or_nothing_no_polymorphic_id(self):
        """真不变量（design §Data Models）：凡出现 actor_type 的治理表，必须同时具备
        物理 XOR 三列（actor_type / actor_user_id / actor_service_identity_id），
        禁止部分 actor 列或单个多态 actor_id。用 human-only FK 或无 actor 的表不检查。"""
        models = _governance_orm_models()
        actor_tables: list[str] = []
        for tname in GOVERNANCE_TABLES:
            cols = {c.name for c in models[tname].__table__.columns}
            if "actor_type" in cols:
                actor_tables.append(tname)
                assert set(C.ACTOR_COLUMNS) <= cols, f"{tname} actor 列不完整：{C.ACTOR_COLUMNS}"
            # 禁止单个多态 actor_id（无 actor_type 却有裸 actor_id）
            assert "actor_id" not in cols, f"{tname} 出现多态 actor_id（禁止；须物理 XOR）"
        # 至少大多数治理表带 actor XOR（防止空集误判通过）
        assert len(actor_tables) >= 18, f"actor XOR 表数异常偏少：{len(actor_tables)}"

    def test_human_only_fks_are_not_null(self):
        models = _governance_orm_models()
        for tname, colname in HUMAN_ONLY_NOT_NULL_FKS:
            col = models[tname].__table__.columns[colname]
            assert col.nullable is False, f"{tname}.{colname} 必须 NOT NULL（人工专属）"
        # released_by_user_id 列级可空（active hold 未解除），但 released 时由 CHECK 强制非空
        lh = models["legal_holds"].__table__.columns["released_by_user_id"]
        assert lh.nullable is True

    def test_ocr_state_check_matches_frozen_contract(self):
        sql = V108.read_text(encoding="utf-8")
        # 迁移 CHECK 的状态字面量必须与 contracts.OCR_STATES 一一对应
        for st in C.OCR_STATES:
            assert f"'{st}'" in sql, f"OCR state {st} 未出现在 V108 CHECK"
        # 契约本身封闭 6 态
        assert C.OCR_STATES == frozenset(
            {"queued", "running", "awaiting_confirmation", "confirmed", "written_back", "failed"}
        )

    def test_ocr_transition_set_frozen_and_closed(self):
        # 合法迁移封闭集（P9）：7 条边，written_back 终态无出边
        assert len(C.OCR_TRANSITIONS) == 7
        assert C.is_legal_ocr_transition("queued", "running")
        assert C.is_legal_ocr_transition("failed", "queued")
        assert not C.is_legal_ocr_transition("written_back", "queued")
        assert not C.is_legal_ocr_transition("confirmed", "queued")

    def test_evidence_ref_status_and_resolution_kind_frozen(self):
        assert C.EVIDENCE_REF_STATUSES == frozenset({"active", "inactive"})
        assert C.LEGACY_RESOLUTION_KINDS == frozenset(
            {"root", "current_version", "historical_version"}
        )

    def test_writeback_eligible_excludes_rejected(self):
        # P12：rejected 已决定但永不进 mapping
        assert "rejected" in C.OCR_FIELD_DECISIONS
        assert "rejected" not in C.OCR_WRITEBACK_ELIGIBLE_DECISIONS
        assert C.OCR_WRITEBACK_ELIGIBLE_DECISIONS < C.OCR_FIELD_DECISIONS

    def test_pydantic_enums_sourced_from_frozen_contracts(self):
        from app.schemas.evidence_governance import (
            ActorType,
            EvidenceRefStatus,
            LegacyResolutionKind,
            OcrFieldDecision,
            OcrState,
            assert_enum_matches_frozen_contracts,
        )

        # import 期已断言；此处再显式跑一次（漂移即 raise）。
        assert_enum_matches_frozen_contracts()
        assert {m.value for m in OcrState} == set(C.OCR_STATES)
        assert {m.value for m in ActorType} == set(C.ACTOR_TYPES)
        assert {m.value for m in OcrFieldDecision} == set(C.OCR_FIELD_DECISIONS)
        assert {m.value for m in EvidenceRefStatus} == set(C.EVIDENCE_REF_STATUSES)
        assert {m.value for m in LegacyResolutionKind} == set(C.LEGACY_RESOLUTION_KINDS)


# ===========================================================================
# 2) 真实 PG16 契约（throwaway 数据库，用完即 DROP；非 PG 环境 skip）
# ===========================================================================

_STUB_PARENTS_SQL = """
CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE projects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_year int, audit_period_end date, audit_period_start date);
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


def _split(sql: str) -> list[str]:
    return MigrationRunner._split_sql_statements(sql)


def _base_url():
    from app.core.config import settings
    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args():
    from app.core.config import settings
    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


@asynccontextmanager
async def _throwaway_db(*, apply_migrations: bool = True, seed: bool = False):
    """创建一次性 PG 数据库，建 stub 父表（+可选 apply V106→V107→V108 + seed 基础行），
    yield 绑定该库的 NullPool 引擎；退出时强制断连并 DROP DATABASE。

    空库场景：public 全新 → 迁移的 DO 守卫（pg_constraint/pg_trigger 全局名）不会被现网
    public 对象误命中，所有约束/触发器如实创建（这是「空库 apply」的真值前提）。
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_cap_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca)
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            for s in _STUB_PARENTS_SQL.strip().split(";"):
                if s.strip():
                    await conn.exec_driver_sql(s)
        if apply_migrations:
            await _apply_all(eng)
        if seed:
            await _seed_base(eng)
        yield eng
    finally:
        await eng.dispose()
        admin = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca)
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')
        await admin.dispose()


async def _apply_all(eng) -> None:
    for f in (V106, V107, V108):
        stmts = _split(f.read_text(encoding="utf-8"))
        async with eng.begin() as conn:
            for s in stmts:
                await conn.exec_driver_sql(s)


async def _count_objects(conn) -> dict[str, int]:
    from sqlalchemy import text as T
    tables = (await conn.execute(T(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
    ))).scalar()
    triggers = (await conn.execute(T(
        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"
    ))).scalar()
    constraints = (await conn.execute(T(
        "SELECT count(*) FROM pg_constraint"
    ))).scalar()
    indexes = (await conn.execute(T(
        "SELECT count(*) FROM pg_indexes WHERE schemaname='public'"
    ))).scalar()
    return {"tables": tables, "triggers": triggers, "constraints": constraints, "indexes": indexes}


async def _seed_base(eng):
    """seed 一个 user / project / available attachment+version(v1)；返回 id 字典。"""
    from sqlalchemy import text as T
    ids = {
        "user": uuid.uuid4(), "svc": None, "project": uuid.uuid4(),
        "att": uuid.uuid4(), "ver": uuid.uuid4(),
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year, audit_period_end) VALUES (:i, 2025, DATE '2025-12-31')"),
            {"i": ids["project"]},
        )
        ids["svc"] = (await conn.execute(
            T("SELECT id FROM service_identities WHERE identity_key='migration'")
        )).scalar()
        await conn.execute(
            T("INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size,"
              " audit_year, state, actor_type, actor_user_id) "
              "VALUES (:a, :p, 'f.pdf', 'opaque', 'pdf', 10, 2025, 'available', 'user', :u)"),
            {"a": ids["att"], "p": ids["project"], "u": ids["user"]},
        )
        await conn.execute(
            T("INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, version_no,"
              " availability, content_hash, actor_type, actor_user_id) "
              "VALUES (:v, :a, :p, 2025, 1, 'available', :h, 'user', :u)"),
            {"v": ids["ver"], "a": ids["att"], "p": ids["project"], "u": ids["user"], "h": "a" * 64},
        )
        # 把 attachment 的 current_version 指向 v1（deferrable 约束触发器在提交时校验）
        await conn.execute(
            T("UPDATE attachments SET current_version_id=:v WHERE id=:a"),
            {"v": ids["ver"], "a": ids["att"]},
        )
    return ids


# --- 空库 apply -------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_db_apply_creates_full_object_set():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=True) as eng:
        async with eng.connect() as conn:
            # 27 治理表全部存在
            for t in GOVERNANCE_TABLES:
                r = await conn.execute(T(f"SELECT to_regclass('public.{t}')"))
                assert r.scalar() is not None, f"空库 apply 后缺表 {t}"
            # 12 触发器齐全
            r = await conn.execute(
                T("SELECT count(*) FROM pg_trigger WHERE tgname = ANY(:n)"),
                {"n": list(ALL_TRIGGERS)},
            )
            assert r.scalar() == len(ALL_TRIGGERS), "触发器未全部创建"
            # 关键命名约束齐全
            r = await conn.execute(
                T("SELECT count(*) FROM pg_constraint WHERE conname = ANY(:n)"),
                {"n": list(KEY_CONSTRAINTS)},
            )
            assert r.scalar() == len(KEY_CONSTRAINTS), "关键命名约束未全部创建"
            # 迁移专用 Service Identity 已 seed
            r = await conn.execute(T("SELECT count(*) FROM service_identities WHERE identity_key='migration'"))
            assert r.scalar() == 1
            # 活动 intent partial unique 索引存在
            r = await conn.execute(T(
                "SELECT count(*) FROM pg_indexes WHERE indexname='uq_evidence_ref_active_intent'"
            ))
            assert r.scalar() == 1


# --- 历史库 apply -----------------------------------------------------------

@pytest.mark.asyncio
async def test_historical_db_apply_preserves_legacy_and_backfills():
    """在既有 legacy attachment 上 additive 加列 + audit_year 回填（R14/P28），旧字节/创建者不改。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=False) as eng:
        legacy_att = uuid.uuid4()
        proj = uuid.uuid4()
        legacy_user = uuid.uuid4()
        async with eng.begin() as conn:
            await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": legacy_user})
            await conn.execute(
                T("INSERT INTO projects (id, audit_period_end) VALUES (:i, DATE '2023-12-31')"),
                {"i": proj},
            )
            # legacy attachment：无治理列（apply 前建）
            await conn.execute(
                T("INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size, created_by) "
                  "VALUES (:a, :p, 'legacy.pdf', '/abs/legacy.pdf', 'pdf', 999, :u)"),
                {"a": legacy_att, "p": proj, "u": legacy_user},
            )
        # apply 全部迁移（历史库场景）
        await _apply_all(eng)
        async with eng.connect() as conn:
            row = (await conn.execute(
                T("SELECT audit_year, state, metadata_status, is_key_evidence, file_name, file_size, created_by "
                  "FROM attachments WHERE id=:a"),
                {"a": legacy_att},
            )).one()
            audit_year, state, metadata_status, is_key, file_name, file_size, created_by = row
            # audit_year 由 V107 §R0 从 project.audit_period_end 回填
            assert audit_year == 2023, "历史 attachment.audit_year 未从 project 回填"
            # 治理列默认值 additive 落位
            assert state == "available"
            assert metadata_status == "incomplete"
            assert is_key is False
            # 旧字节/创建者/文件名不变（P28：不改历史业务内容）
            assert file_name == "legacy.pdf"
            assert file_size == 999
            assert created_by == legacy_user


# --- 中断重跑幂等（P28）------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupt_rerun_idempotent_p28():
    """中断后重跑：apply V106（模拟中断）→ 再 apply 全部 → 再 apply 全部（重跑），
    对象/行基数稳定，不新增重复对象、不报错（P28）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=False) as eng:
        # 模拟中断：只 apply V106
        stmts = _split(V106.read_text(encoding="utf-8"))
        async with eng.begin() as conn:
            for s in stmts:
                await conn.exec_driver_sql(s)
        # 恢复：apply 全部（V106 重跑 + V107 + V108）
        await _apply_all(eng)
        async with eng.connect() as conn:
            first = await _count_objects(conn)
            # 行数基准：service_identities 只应有 1 条 migration identity
            svc1 = (await conn.execute(T("SELECT count(*) FROM service_identities"))).scalar()
        # 再 apply 全部一次（纯重跑）
        await _apply_all(eng)
        async with eng.connect() as conn:
            second = await _count_objects(conn)
            svc2 = (await conn.execute(T("SELECT count(*) FROM service_identities"))).scalar()
        assert first == second, f"重跑改变了对象基数：{first} → {second}（P28 违反）"
        assert svc1 == svc2 == 1, "migration Service Identity 被重复插入（ON CONFLICT 失效）"


# --- actor XOR + 人工专属 NOT NULL FK（P3）----------------------------------

@pytest.mark.asyncio
async def test_actor_xor_and_human_only_fk_enforced_p3():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=True, seed=True) as eng:
        proj = (await _first_project(eng))
        svc = (await _migration_svc(eng))
        user = (await _first_user(eng))
        async with eng.connect() as conn:
            trans = await conn.begin()
            try:
                # 1) 匿名（actor_type NULL）被拒
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO evidence_upload_attempts (project_id, sanitized_file_name, actor_type) "
                              "VALUES (:p, 'x.pdf', NULL)"),
                            {"p": proj},
                        )
                    await sp.rollback()
                # 2) user + service 同设 → XOR CHECK 拒
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO evidence_upload_attempts "
                              "(project_id, sanitized_file_name, actor_type, actor_user_id, actor_service_identity_id) "
                              "VALUES (:p, 'x.pdf', 'user', :u, :s)"),
                            {"p": proj, "u": user, "s": svc},
                        )
                    await sp.rollback()
                # 3) service actor 合法
                r = await conn.execute(
                    T("INSERT INTO evidence_upload_attempts "
                      "(project_id, sanitized_file_name, actor_type, actor_service_identity_id) "
                      "VALUES (:p, 'x.pdf', 'service', :s) RETURNING id"),
                    {"p": proj, "s": svc},
                )
                assert r.scalar() is not None
                # 4) 人工专属 FK closed_by_user_id NOT NULL：review_closes 传 NULL 被拒
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO review_closes (review_id, project_id, close_note, closed_by_user_id) "
                              "VALUES (gen_random_uuid(), :p, 'note', NULL)"),
                            {"p": proj},
                        )
                    await sp.rollback()
                # 5) Service Identity 不得作人工确认：review_closes.closed_by_user_id 只 REFERENCES users，
                #    传一个 service identity 的 id（不在 users 表）→ FK 拒
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO review_closes (review_id, project_id, close_note, closed_by_user_id) "
                              "VALUES (gen_random_uuid(), :p, 'note', :s)"),
                            {"p": proj, "s": svc},
                        )
                    await sp.rollback()
                # 人工用户合法关闭
                r = await conn.execute(
                    T("INSERT INTO review_closes (review_id, project_id, close_note, closed_by_user_id) "
                      "VALUES (gen_random_uuid(), :p, 'note', :u) RETURNING id"),
                    {"p": proj, "u": user},
                )
                assert r.scalar() is not None
            finally:
                await trans.rollback()

        # schema 级：人工专属 FK is_nullable
        async with eng.connect() as conn:
            for tname, colname in HUMAN_ONLY_NOT_NULL_FKS:
                r = await conn.execute(T(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name=:t AND column_name=:c"
                ), {"t": tname, "c": colname})
                assert r.scalar() == "NO", f"{tname}.{colname} 应为 NOT NULL"


# --- 复合 scope FK + partial unique + deferrable ----------------------------

@pytest.mark.asyncio
async def test_composite_fk_partial_unique_and_deferrable():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=True, seed=True) as eng:
        proj = await _first_project(eng)
        user = await _first_user(eng)
        att = (await _first_attachment(eng))

        async with eng.connect() as conn:
            trans = await conn.begin()
            try:
                # A) 活动 intent partial unique：两条 active 同 (proj,year,intent) → 第 2 条被拒
                base = dict(p=proj, u=user, ih="c" * 64)
                await conn.execute(
                    T("INSERT INTO evidence_refs (project_id, audit_year, source_type, source_id, "
                      "evidence_type, evidence_id, intent_hash, status, actor_type, actor_user_id) "
                      "VALUES (:p, 2025, 'workpaper_cell', 's1', 'attachment', 'e1', :ih, 'active', 'user', :u)"),
                    base,
                )
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO evidence_refs (project_id, audit_year, source_type, source_id, "
                              "evidence_type, evidence_id, intent_hash, status, actor_type, actor_user_id) "
                              "VALUES (:p, 2025, 'workpaper_cell', 's2', 'attachment', 'e2', :ih, 'active', 'user', :u)"),
                            base,
                        )
                    await sp.rollback()
                # active + inactive 同 intent → 允许（partial unique 仅约束 active）
                await conn.execute(
                    T("INSERT INTO evidence_refs (project_id, audit_year, source_type, source_id, "
                      "evidence_type, evidence_id, intent_hash, status, actor_type, actor_user_id) "
                      "VALUES (:p, 2025, 'workpaper_cell', 's3', 'attachment', 'e3', :ih, 'inactive', 'user', :u)"),
                    base,
                )

                # B) 复合 scope FK：attachment_version.project_id 与父 attachment scope 不一致 → FK 拒
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("INSERT INTO attachment_versions (attachment_id, project_id, audit_year, version_no, "
                              "availability, actor_type, actor_user_id) "
                              "VALUES (:a, gen_random_uuid(), 2025, 2, 'staged', 'user', :u)"),
                            {"a": att, "u": user},
                        )
                    await sp.rollback()
                await trans.rollback()
            except Exception:
                await trans.rollback()
                raise

        # C) deferrable 前序复合 FK：单事务内先插引用尚不存在的 previous 的 v2，再插 v1，提交成功
        async with eng.connect() as conn:
            trans = await conn.begin()
            try:
                att2 = uuid.uuid4()
                v1 = uuid.uuid4()
                v2 = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size, "
                      "audit_year, state, actor_type, actor_user_id) "
                      "VALUES (:a, :p, 'g.pdf', 'opaque', 'pdf', 5, 2025, 'available', 'user', :u)"),
                    {"a": att2, "p": proj, "u": user},
                )
                # 先插 v2（previous=v1，此刻 v1 尚不存在）—— DEFERRABLE INITIALLY DEFERRED 允许
                await conn.execute(
                    T("INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, version_no, "
                      "availability, previous_version_id, actor_type, actor_user_id) "
                      "VALUES (:v2, :a, :p, 2025, 2, 'available', :v1, 'user', :u)"),
                    {"v2": v2, "v1": v1, "a": att2, "p": proj, "u": user},
                )
                await conn.execute(
                    T("INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, version_no, "
                      "availability, actor_type, actor_user_id) "
                      "VALUES (:v1, :a, :p, 2025, 1, 'available', 'user', :u)"),
                    {"v1": v1, "a": att2, "p": proj, "u": user},
                )
                # 提交（deferred FK + 约束触发器在此校验）→ 成功
                await trans.commit()
            except Exception:
                await trans.rollback()
                raise
            # 验证确实提交
            async with eng.connect() as conn2:
                cnt = (await conn2.execute(
                    T("SELECT count(*) FROM attachment_versions WHERE attachment_id=:a"),
                    {"a": att2},
                )).scalar()
                assert cnt == 2

        # D) deferrable 约束触发器：previous 自指 → 提交时被拒
        async with eng.connect() as conn:
            trans = await conn.begin()
            self_ref_failed = False
            try:
                att3 = uuid.uuid4()
                vs = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size, "
                      "audit_year, state, actor_type, actor_user_id) "
                      "VALUES (:a, :p, 'h.pdf', 'opaque', 'pdf', 5, 2025, 'available', 'user', :u)"),
                    {"a": att3, "p": proj, "u": user},
                )
                await conn.execute(
                    T("INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, version_no, "
                      "availability, previous_version_id, actor_type, actor_user_id) "
                      "VALUES (:v, :a, :p, 2025, 1, 'available', :v, 'user', :u)"),
                    {"v": vs, "a": att3, "p": proj, "u": user},
                )
                await trans.commit()
            except Exception:
                self_ref_failed = True
                await trans.rollback()
            assert self_ref_failed, "previous_version_id 自指应在提交时被约束触发器拒绝"


# --- immutable / append-only 触发器 -----------------------------------------

@pytest.mark.asyncio
async def test_immutable_and_append_only_triggers():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=True, seed=True) as eng:
        proj = await _first_project(eng)
        user = await _first_user(eng)
        att = await _first_attachment(eng)
        ver = await _first_version(eng)

        async with eng.connect() as conn:
            trans = await conn.begin()
            try:
                # 1) AttachmentVersion immutable：改 content_hash 被拒；改 availability 允许
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("UPDATE attachment_versions SET content_hash=:h WHERE id=:v"),
                            {"h": "b" * 64, "v": ver},
                        )
                    await sp.rollback()
                await conn.execute(
                    T("UPDATE attachment_versions SET media_type='application/pdf' WHERE id=:v"),
                    {"v": ver},
                )

                # 2) OCRResult immutable：建 job+result，任何 UPDATE 被拒
                job = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO ocr_jobs (id, project_id, audit_year, attachment_id, attachment_version_id, "
                      "content_hash, idempotency_key, state, actor_type, actor_user_id) "
                      "VALUES (:j, :p, 2025, :a, :v, :h, 'k1', 'queued', 'user', :u)"),
                    {"j": job, "p": proj, "a": att, "v": ver, "h": "a" * 64, "u": user},
                )
                res = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO ocr_results (id, ocr_job_id, project_id, audit_year, attachment_version_id, "
                      "source_content_hash, raw_text, result_hash, actor_type, actor_user_id) "
                      "VALUES (:r, :j, :p, 2025, :v, :h, 'raw', :rh, 'user', :u)"),
                    {"r": res, "j": job, "p": proj, "v": ver, "h": "a" * 64, "rh": "d" * 64, "u": user},
                )
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("UPDATE ocr_results SET raw_text='tampered' WHERE id=:r"), {"r": res}
                        )
                    await sp.rollback()

                # 3) OCRConfirmation append-only：改 is_current 允许；改 decision 被拒
                conf = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO ocr_confirmations (id, ocr_job_id, ocr_result_id, project_id, audit_year, "
                      "field_key, decision, confirmed_value, is_current, confirmed_by_user_id) "
                      "VALUES (:c, :j, :r, :p, 2025, 'amount', 'accepted', '100', true, :u)"),
                    {"c": conf, "j": job, "r": res, "p": proj, "u": user},
                )
                await conn.execute(
                    T("UPDATE ocr_confirmations SET is_current=false WHERE id=:c"), {"c": conf}
                )
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("UPDATE ocr_confirmations SET decision='rejected' WHERE id=:c"), {"c": conf}
                        )
                    await sp.rollback()

                # 4) sealed ArchiveManifest 不可变：插 sealed 后任何 UPDATE 被拒
                man = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO archive_manifests (id, project_id, audit_year, version_no, watermark, "
                      "state, actor_type, actor_user_id) "
                      "VALUES (:m, :p, 2025, 1, :w, 'sealed', 'user', :u)"),
                    {"m": man, "p": proj, "w": "e" * 64, "u": user},
                )
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("UPDATE archive_manifests SET watermark=:w WHERE id=:m"),
                            {"w": "f" * 64, "m": man},
                        )
                    await sp.rollback()

                # 5) quality snapshot immutable：任何 UPDATE 被拒
                qs = uuid.uuid4()
                await conn.execute(
                    T("INSERT INTO evidence_quality_snapshots (id, project_id, audit_year, snapshot_key, metrics, "
                      "actor_type, actor_user_id) VALUES (:q, :p, 2025, 'snap1', :m, 'user', :u)"),
                    {"q": qs, "p": proj, "m": '{"metadata_complete_rate": 1.0}', "u": user},
                )
                async with conn.begin_nested() as sp:
                    with pytest.raises(Exception):
                        await conn.execute(
                            T("UPDATE evidence_quality_snapshots SET metrics=:m WHERE id=:q"),
                            {"m": '{"x": 1}', "q": qs},
                        )
                    await sp.rollback()
            finally:
                await trans.rollback()


# --- 小工具：从 seed 库取基础 id -------------------------------------------

async def _scalar(eng, sql):
    from sqlalchemy import text as T
    async with eng.connect() as conn:
        return (await conn.execute(T(sql))).scalar()


async def _first_project(eng):
    return await _scalar(eng, "SELECT id FROM projects LIMIT 1")


async def _first_user(eng):
    return await _scalar(eng, "SELECT id FROM users LIMIT 1")


async def _migration_svc(eng):
    return await _scalar(eng, "SELECT id FROM service_identities WHERE identity_key='migration'")


async def _first_attachment(eng):
    return await _scalar(eng, "SELECT id FROM attachments LIMIT 1")


async def _first_version(eng):
    return await _scalar(eng, "SELECT id FROM attachment_versions LIMIT 1")


# ===========================================================================
# 3) schema drift 检测（真实 DB）+ MigrationRunner checksum-drift 守卫
# ===========================================================================

@pytest.mark.asyncio
async def test_schema_drift_detector_clean_for_governance_tables():
    """SchemaDriftDetector 对 27 治理表零 orm_extra/db_extra/type_mismatch（ORM 已注册 + V106-108 已应用）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from app.core.config import settings
    from app.core.schema_drift_detector import SchemaDriftDetector
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=_connect_args())
    try:
        detector = SchemaDriftDetector(eng)
        items = await detector.scan()
        gov = set(GOVERNANCE_TABLES)
        offenders = [
            it for it in items
            if it.table in gov and it.drift_type in ("orm_extra", "db_extra", "type_mismatch")
        ]
        assert offenders == [], f"治理表存在 schema 漂移：{[(o.table, o.column, o.drift_type, o.detail) for o in offenders]}"
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_checksum_drift_guard_detects_edited_migration():
    """MigrationRunner.detect_checksum_drift 检测「已应用迁移文件被事后编辑」（Task 2.3 finding）。

    用 throwaway 库 apply V106，然后在 schema_version 里把 V106 的存储 checksum 篡改为旧值，
    detect_checksum_drift 必须精确报出 V106 漂移（纯检测，不重跑）。
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T
    async with _throwaway_db(apply_migrations=False) as eng:
        runner = MigrationRunner(engine=eng)
        await runner.ensure_schema_version_table()
        # 记录 V106 为已应用，但存储一个「旧」checksum（模拟文件应用后被编辑）
        async with eng.begin() as conn:
            await conn.execute(
                T("INSERT INTO schema_version (version, filename, checksum) VALUES ('106', :f, :c)"),
                {"f": "V106__evidence_governance_attachment_versions.sql", "c": "0" * 64},
            )
            # 一个 checksum 一致的对照版本（用真实 V107 checksum）
            v107 = [m for m in runner.scan_migrations() if m.version == "107"][0]
            await conn.execute(
                T("INSERT INTO schema_version (version, filename, checksum) VALUES ('107', :f, :c)"),
                {"f": v107.filename, "c": v107.checksum},
            )
        drifts = await runner.detect_checksum_drift()
        versions = {d.version for d in drifts}
        assert "106" in versions, "checksum 漂移未被检测（V106 存储值与当前文件不一致）"
        assert "107" not in versions, "一致的 V107 不应报漂移"
        d106 = next(d for d in drifts if d.version == "106")
        assert d106.stored_checksum == "0" * 64
        assert d106.current_checksum != "0" * 64


def test_checksum_drift_guard_method_exists_and_returns_list():
    """纯接口存在性（非 PG 也可跑）：detect_checksum_drift 已加到 MigrationRunner。"""
    from app.core.migration_runner import ChecksumDrift, MigrationRunner as _R
    assert hasattr(_R, "detect_checksum_drift")
    assert ChecksumDrift.__dataclass_fields__.keys() >= {
        "version", "filename", "stored_checksum", "current_checksum"
    }
