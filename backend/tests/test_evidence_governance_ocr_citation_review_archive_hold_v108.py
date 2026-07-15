"""Task 2.4 — OCR Job/Transition/Result/Confirmation/Writeback(+staging), CitationSnapshot,
AiContentLog 扩展, Review snapshot/close, audit command-root/transition, outbox/inbox,
Archive Manifest/Entry/Edge, Legal Hold/Scope, migration checkpoint, quality snapshot
迁移与 ORM 形状 + 真实 PG16 行为 smoke。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.4 (Wave 1)
Requirements: R5, R6, R7, R8, R10, R11, R12, R13, R16
Design: §4.5（OCR 模型）, §4.6（Citation/AI/Review/Manifest/Hold 与审计）, §7.1（command-root）
Properties: P9(状态机封闭), P11(结果不可变), P12(未确认不可写回), P13/P14(写回原子/幂等),
            P15(citation), P17/P18/P19(AI 门禁), P21/P22(复核), P23/P24(manifest),
            P25(command-root 唯一), P26/P27(hold), P30(质量快照)

覆盖（本任务范围）：
  * V108 迁移约定 lint（additive / repeatable / FK RESTRICT）+ 动态分配落点（最高号 / 无重复）。
  * 冻结契约 parity：OCR_STATES / OCR_FIELD_DECISIONS / HUMAN_ONLY_DECISION_FKS ↔ 迁移/ORM。
  * ORM ↔ 迁移列名/表名 parity（20 新表 + AiContentLog 扩展列）。
  * 真实 PG16 集成 smoke（rolled-back，不落库）：DDL 有效、OCR state CHECK 封闭、
    immutable OCRResult 触发器、command-root UNIQUE、human-only FK NOT NULL、legal_hold release CHECK。

注：完整 empty/historical/interrupt/drift/composite/trigger 穷举契约套件属 Task 2.5，
    穷举 P9–P30 属性组属 Wave 8。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from app.services.evidence_governance.contracts import (
    HUMAN_ONLY_DECISION_FKS,
    OCR_FIELD_DECISIONS,
    OCR_STATES,
)
from app.services.evidence_governance.migration_allocation import (
    lint_migration_sql,
    parse_dir_versions,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V108_PATH = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"

NEW_TABLES = (
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

NAMED_CONSTRAINTS = (
    "uq_audit_command_root",
    "chk_audit_root_actor_xor",
    "chk_ocr_job_state",
    "uq_ocr_job_idempotency",
    "chk_ocr_confirmation_decision",
    "chk_ocr_confirmation_value",
    "uq_ocr_writeback_idempotency",
    "chk_ocr_writeback_mode",
    "uq_ocr_wb_staging_idempotency",
    "chk_citation_actor_xor",
    "chk_review_snapshot_phase",
    "uq_archive_manifest_version",
    "chk_archive_manifest_state",
    "chk_legal_hold_state",
    "chk_legal_hold_release",
    "uq_evidence_outbox_event",
    "uq_evidence_inbox_event",
    "uq_migration_checkpoint_batch",
    "uq_quality_snapshot_key",
)

# 人工专属 NOT NULL 决定 FK（Service Identity 不得填充）
HUMAN_ONLY_NOT_NULL = {
    "ocr_confirmations": "confirmed_by_user_id",
    "ocr_writebacks": "written_by_user_id",
    "review_closes": "closed_by_user_id",
}

IMMUTABLE_TRIGGERS = (
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

# AiContentLog 扩展列（design §4.6）
AI_CONTENT_LOG_EXT_COLS = (
    "service_status", "output_hash", "evidence_ref_id", "citation_snapshot_id",
    "is_stale", "stale_reason",
)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


# ---------------------------------------------------------------------------
# 迁移文件存在 + 约定 lint + 动态分配落点
# ---------------------------------------------------------------------------

class TestMigrationFileConventions:
    def test_v108_exists(self):
        assert V108_PATH.is_file(), "V108 迁移文件缺失"

    def test_v108_lint_clean(self):
        violations = lint_migration_sql(V108_PATH.read_text(encoding="utf-8"))
        assert violations == [], f"V108 违反迁移约定：{violations}"

    def test_v108_no_duplicate_and_is_highest(self):
        by = parse_dir_versions([p.name for p in MIGRATIONS_DIR.glob("V*.sql")])
        dupes = {v: names for v, names in by.items() if len(names) > 1}
        assert dupes == {}, f"重复版本号：{dupes}"
        assert 108 in by, "V108 未在目录中"
        assert max(by) == 108, f"V108 应为当前最高号，实际最高={max(by)}"

    def test_v108_additive_no_destructive(self):
        sql = _strip_comments(V108_PATH.read_text(encoding="utf-8")).upper()
        assert "DROP TABLE" not in sql
        assert "DROP COLUMN" not in sql
        assert "TRUNCATE" not in sql

    def test_v108_creates_all_tables(self):
        sql = _strip_comments(V108_PATH.read_text(encoding="utf-8"))
        for t in NEW_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {t}" in sql, f"缺 CREATE TABLE {t}"

    def test_v108_declares_named_constraints_and_triggers(self):
        sql = _strip_comments(V108_PATH.read_text(encoding="utf-8"))
        for c in NAMED_CONSTRAINTS:
            assert c in sql, f"缺命名约束 {c}"
        for trg in IMMUTABLE_TRIGGERS:
            assert trg in sql, f"缺不可变/append-only 触发器 {trg}"

    def test_v108_ai_content_log_extension_additive(self):
        sql = V108_PATH.read_text(encoding="utf-8")
        for col in AI_CONTENT_LOG_EXT_COLS:
            assert f"ADD COLUMN IF NOT EXISTS {col}" in sql, f"AiContentLog 扩展列 {col} 未 additive 添加"


# ---------------------------------------------------------------------------
# 冻结契约 parity（contracts 单一真源）
# ---------------------------------------------------------------------------

class TestFrozenContractParity:
    def test_ocr_states_closed_set_in_check(self):
        sql = V108_PATH.read_text(encoding="utf-8")
        # chk_ocr_job_state 封闭集恰为 contracts.OCR_STATES
        m = re.search(r"chk_ocr_job_state[^(]*\(\s*state IN \(([^)]*)\)", sql)
        assert m, "找不到 chk_ocr_job_state"
        states = {s.strip().strip("'") for s in m.group(1).split(",")}
        assert states == set(OCR_STATES), f"OCR state CHECK 与冻结集不一致：{states} vs {set(OCR_STATES)}"

    def test_ocr_field_decisions_in_check(self):
        sql = V108_PATH.read_text(encoding="utf-8")
        m = re.search(r"chk_ocr_confirmation_decision[^(]*\(decision IN \(([^)]*)\)", sql)
        assert m, "找不到 chk_ocr_confirmation_decision"
        decisions = {d.strip().strip("'") for d in m.group(1).split(",")}
        assert decisions == set(OCR_FIELD_DECISIONS), (
            f"OCR decision CHECK 与冻结集不一致：{decisions} vs {set(OCR_FIELD_DECISIONS)}"
        )

    def test_human_only_decision_fks_present_and_not_null(self):
        sql = V108_PATH.read_text(encoding="utf-8")
        # confirmed_by / written_by / closed_by 均 NOT NULL REFERENCES users
        for col in ("confirmed_by_user_id", "written_by_user_id", "closed_by_user_id"):
            assert col in HUMAN_ONLY_DECISION_FKS, f"{col} 不在冻结 HUMAN_ONLY_DECISION_FKS"
            assert re.search(
                rf"{col} UUID NOT NULL REFERENCES users\(id\) ON DELETE RESTRICT", sql
            ), f"{col} 未声明为 NOT NULL 人工专属 FK"
        # released_by_user_id 在 HUMAN_ONLY_DECISION_FKS，但 released 时经 CHECK 强制非空
        assert "released_by_user_id" in HUMAN_ONLY_DECISION_FKS
        assert "chk_legal_hold_release" in sql


# ---------------------------------------------------------------------------
# ORM ↔ 迁移 parity
# ---------------------------------------------------------------------------

class TestOrmMigrationParity:
    def _orm_models(self):
        import app.models  # noqa: F401
        from app.models.evidence_governance_models import (
            ArchiveManifest,
            ArchiveManifestEdge,
            ArchiveManifestEntry,
            CitationSnapshot,
            EvidenceAuditCommandRoot,
            EvidenceAuditTransition,
            EvidenceInbox,
            EvidenceMigrationCheckpoint,
            EvidenceOutbox,
            EvidenceQualitySnapshot,
            LegalHold,
            LegalHoldScope,
            OcrConfirmation,
            OcrJob,
            OcrJobTransition,
            OcrResult,
            OcrWriteback,
            OcrWritebackStaging,
            ReviewClose,
            ReviewEvidenceSnapshot,
        )
        return {
            "evidence_audit_command_roots": EvidenceAuditCommandRoot,
            "evidence_audit_transitions": EvidenceAuditTransition,
            "ocr_jobs": OcrJob,
            "ocr_job_transitions": OcrJobTransition,
            "ocr_results": OcrResult,
            "ocr_confirmations": OcrConfirmation,
            "ocr_writebacks": OcrWriteback,
            "ocr_writeback_staging": OcrWritebackStaging,
            "citation_snapshots": CitationSnapshot,
            "review_evidence_snapshots": ReviewEvidenceSnapshot,
            "review_closes": ReviewClose,
            "archive_manifests": ArchiveManifest,
            "archive_manifest_entries": ArchiveManifestEntry,
            "archive_manifest_edges": ArchiveManifestEdge,
            "legal_holds": LegalHold,
            "legal_hold_scopes": LegalHoldScope,
            "evidence_outbox": EvidenceOutbox,
            "evidence_inbox": EvidenceInbox,
            "evidence_migration_checkpoints": EvidenceMigrationCheckpoint,
            "evidence_quality_snapshots": EvidenceQualitySnapshot,
        }

    def test_all_orm_tablenames_match_migration(self):
        models = self._orm_models()
        assert set(models) == set(NEW_TABLES), "ORM 表集合与迁移表集合不一致"
        for tname, model in models.items():
            assert model.__tablename__ == tname

    def test_orm_columns_present_in_migration(self):
        sql = V108_PATH.read_text(encoding="utf-8")
        for tname, model in self._orm_models().items():
            for col in model.__table__.columns:
                assert col.name in sql, f"ORM 列 {tname}.{col.name} 未出现在 V108"

    def test_ai_content_log_orm_has_extension_columns(self):
        import app.models  # noqa: F401
        from app.models.v3_refinement_models import AiContentLog
        cols = {c.name for c in AiContentLog.__table__.columns}
        missing = set(AI_CONTENT_LOG_EXT_COLS) - cols
        assert missing == set(), f"AiContentLog ORM 缺扩展列：{missing}"

    def test_ocr_confirmation_human_only_fk_not_null(self):
        for tname, col in HUMAN_ONLY_NOT_NULL.items():
            model = self._orm_models()[tname]
            column = model.__table__.columns[col]
            assert column.nullable is False, f"{tname}.{col} 应为 NOT NULL 人工专属 FK"

    def test_ocr_confirmation_current_partial_unique(self):
        from app.models.evidence_governance_models import OcrConfirmation
        idx = {i.name: i for i in OcrConfirmation.__table__.indexes}.get("uq_ocr_confirmation_current")
        assert idx is not None and idx.unique is True
        assert tuple(c.name for c in idx.columns) == ("ocr_job_id", "field_key")

    def test_command_root_unique_scope(self):
        from app.models.evidence_governance_models import EvidenceAuditCommandRoot
        uniques = {
            tuple(c.name for c in con.columns)
            for con in EvidenceAuditCommandRoot.__table__.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        }
        assert ("command_type", "idempotency_key", "project_id", "audit_year") in uniques


# ---------------------------------------------------------------------------
# 真实 PG16 集成 smoke（rolled-back 事务，不落库；非 PG 环境 skip）
# ---------------------------------------------------------------------------

def _split(sql: str) -> list[str]:
    from app.core.migration_runner import MigrationRunner
    return MigrationRunner._split_sql_statements(sql)


@pytest.mark.asyncio
async def test_v108_applies_on_real_pg_and_enforces_invariants():
    """在 rolled-back 事务中应用 V108，验证 DDL + OCR state CHECK + immutable OCRResult 触发器
    + command-root UNIQUE + human-only NOT NULL + legal_hold release CHECK。

    前置 V106/V107/V017 已在真实 DB 应用（attachment_versions / evidence_refs / ai_content_log 存在）。
    完整穷举（trigger/复合/并发/rollback）→ Task 2.5 / Wave 8。
    """
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql"):
        pytest.skip("V108 集成 smoke 需真实 PostgreSQL 16")

    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(db_url, poolclass=NullPool, connect_args=connect_args)

    v108_stmts = _split(V108_PATH.read_text(encoding="utf-8"))

    conn = await engine.connect()
    trans = await conn.begin()
    try:
        for s in v108_stmts:
            await conn.exec_driver_sql(s)

        # 1) 20 新表存在
        for t in NEW_TABLES:
            r = await conn.exec_driver_sql(f"SELECT to_regclass('public.{t}')")
            assert r.scalar() is not None, f"表 {t} 未创建"

        # 2) 命名约束 + 触发器存在
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_constraint WHERE conname = ANY(:names)"),
            {"names": list(NAMED_CONSTRAINTS)},
        )
        assert r.scalar() == len(NAMED_CONSTRAINTS)
        r = await conn.execute(
            _text("SELECT count(*) FROM pg_trigger WHERE tgname = ANY(:names)"),
            {"names": list(IMMUTABLE_TRIGGERS)},
        )
        assert r.scalar() == len(IMMUTABLE_TRIGGERS)

        # 3) human-only FK NOT NULL（information_schema）
        for tname, col in HUMAN_ONLY_NOT_NULL.items():
            r = await conn.execute(
                _text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": tname, "c": col},
            )
            assert r.scalar() == "NO", f"{tname}.{col} 应为 NOT NULL 人工专属 FK"

        svc_id = (
            await conn.exec_driver_sql(
                "SELECT id FROM service_identities WHERE identity_key = 'migration'"
            )
        ).scalar()
        assert svc_id is not None
        project_id = (await conn.exec_driver_sql("SELECT id FROM projects LIMIT 1")).scalar()
        if project_id is None:
            pytest.skip("无可用 project，跳过行为断言（DDL 已验证）")

        # 4) command-root UNIQUE（P25）：同 (command_type, idempotency_key, scope) 只一条
        async def _insert_root(ikey: str):
            return await conn.execute(
                _text(
                    "INSERT INTO evidence_audit_command_roots "
                    "(id, command_type, idempotency_key, project_id, audit_year, actor_type, "
                    " actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), 'ocr.start', :ik, :pid, 2025, 'service', :svc) "
                    "RETURNING id"
                ),
                {"ik": ikey, "pid": project_id, "svc": svc_id},
            )

        root_id = (await _insert_root("cmd-1")).scalar()
        assert root_id is not None
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_root("cmd-1")  # 同幂等键 → uq_audit_command_root 违反
            await sp.rollback()

        # 5) OCR state CHECK（P9）：非法状态被拒。先建 attachment + version。
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

        async def _insert_job(state: str, ikey: str):
            return await conn.execute(
                _text(
                    "INSERT INTO ocr_jobs "
                    "(id, project_id, audit_year, attachment_id, attachment_version_id, content_hash, "
                    " idempotency_key, state, actor_type, actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), :pid, 2025, :aid, :vid, :h, :ik, :st, 'service', :svc) "
                    "RETURNING id"
                ),
                {"pid": project_id, "aid": att_id, "vid": ver_id, "h": "a" * 64,
                 "ik": ikey, "st": state, "svc": svc_id},
            )

        job_id = (await _insert_job("queued", "ocrjob-1")).scalar()
        assert job_id is not None
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_job("bogus", "ocrjob-2")  # 非法 state → chk_ocr_job_state
            await sp.rollback()
        # OCR job 幂等键唯一
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_job("queued", "ocrjob-1")  # 同幂等键 → uq_ocr_job_idempotency
            await sp.rollback()

        # 6) immutable OCRResult 触发器（P11）：UPDATE 被拒
        result_id = (
            await conn.execute(
                _text(
                    "INSERT INTO ocr_results "
                    "(id, ocr_job_id, project_id, audit_year, attachment_version_id, "
                    " source_content_hash, raw_text, result_hash, actor_type, actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), :jid, :pid, 2025, :vid, :h, 'hello', :rh, 'service', :svc) "
                    "RETURNING id"
                ),
                {"jid": job_id, "pid": project_id, "vid": ver_id, "h": "a" * 64,
                 "rh": "b" * 64, "svc": svc_id},
            )
        ).scalar()
        assert result_id is not None
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await conn.execute(
                    _text("UPDATE ocr_results SET raw_text = 'tampered' WHERE id = :rid"),
                    {"rid": result_id},
                )
            await sp.rollback()

        # 7) legal_hold release CHECK（P26/P27 支撑）：active 不得带 released_by
        async def _insert_hold(state: str, released_by, released_at, release_reason):
            return await conn.execute(
                _text(
                    "INSERT INTO legal_holds "
                    "(id, project_id, audit_year, reason, state, released_by_user_id, released_at, "
                    " release_reason, actor_type, actor_service_identity_id) "
                    "VALUES (gen_random_uuid(), :pid, 2025, 'litigation', :st, :rb, :rat, :rr, "
                    " 'service', :svc) RETURNING id"
                ),
                {"pid": project_id, "st": state, "rb": released_by, "rat": released_at,
                 "rr": release_reason, "svc": svc_id},
            )

        hold_id = (await _insert_hold("active", None, None, None)).scalar()
        assert hold_id is not None
        # released 但缺 released_by_user_id → chk_legal_hold_release 违反
        async with conn.begin_nested() as sp:
            with pytest.raises(Exception):
                await _insert_hold("released", None, None, None)
            await sp.rollback()
        # active 但带 released_by（真实 user）→ chk_legal_hold_release 违反
        user_id = (await conn.exec_driver_sql("SELECT id FROM users LIMIT 1")).scalar()
        if user_id is not None:
            async with conn.begin_nested() as sp:
                with pytest.raises(Exception):
                    await conn.execute(
                        _text(
                            "INSERT INTO legal_holds "
                            "(id, project_id, audit_year, reason, state, released_by_user_id, "
                            " actor_type, actor_service_identity_id) "
                            "VALUES (gen_random_uuid(), :pid, 2025, 'x', 'active', :uid, 'service', :svc)"
                        ),
                        {"pid": project_id, "uid": user_id, "svc": svc_id},
                    )
                await sp.rollback()
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()
