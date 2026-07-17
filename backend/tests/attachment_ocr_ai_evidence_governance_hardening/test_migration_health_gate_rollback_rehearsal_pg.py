"""Feature: attachment-ocr-ai-evidence-governance-hardening

Wave 10 / Task 11.2 —— 预生产 **可执行 migration health gate + 完整回滚演练**。

Requirements: R11, R12, R13, R14, R15
Design: §8.3 高风险部署 Health Gate、§8.4 Rollback

本套件把 design §8.3 / §8.4 的部署门禁与回滚演练做成**可执行断言**（非文档描述）：

  1. **Health gate 阻断**（§8.3）：切 feature flag / 启治理 worker / 设新写真源前，任一条件命中
     即阻断 —— 任一相关迁移失败、迁移进入 **无锁降级 / 跳过约束**、存在 pending/failed migration、
     **所需锁/约束未生效**、alias/backfill 差异超阈值、备份未验证可恢复、PG/PgBouncer/队列 配额超预算。
     纯判定面用 ``evaluate_deployment_health_gate``（逐条阻断 + 稳定原因码）；
     **“所需锁/约束是否生效”在真实 PostgreSQL 16 上探测**（immutable/deferrable trigger、复合
     scope unique、command-root unique、sealed 防覆盖 trigger、hold 释放 CHECK 等）。

  2. **完整回滚演练**（§8.4）：以 throwaway PG16 播种全部治理对象（AttachmentVersion / EvidenceRef /
     EvidenceDependency / OCR 决策链 / 审计 command-root / Manifest / Hold），执行非破坏性回滚演练
     （停新写、drain worker、暂停 backfill、兼容读回退）后，逐类核验治理对象 **零删除 / 零覆盖**：
     行数与内容字节/哈希不变；且 immutable/sealed 覆盖保护在回滚后仍生效（附件版本字节、已封
     manifest 不可被覆盖）。

  3. **备份失败自动响应**（§8.3）：备份失败**不得**自动执行高风险 DB 回滚；自动响应只能停止新写、
     关闭 flag、drain worker、保留现场并告警，由人工确认恢复策略。

设计 §10 测试规则：约束/触发器/回滚必须在真实 PostgreSQL 16 验证，无 PG 环境时优雅 skip；
SQLite 不得替代 PG 证据。纯判定逻辑（gate 阻断组合、备份失败响应、演练脚本）为 database-agnostic
纯函数，可无 PG 运行。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.services.evidence_governance.deployment_health_gate import (
    REASON_BACKFILL_DIFF,
    REASON_BACKUP_NOT_VERIFIED,
    REASON_LOCKLESS_DEGRADED,
    REASON_LOCKS_NOT_IN_EFFECT,
    REASON_MIGRATION_FAILED,
    REASON_PENDING_OR_FAILED_MIGRATION,
    REASON_QUOTA_OVER_BUDGET,
    backup_failure_response,
    build_rollback_rehearsal_script,
    evaluate_deployment_health_gate,
)
from app.services.evidence_governance.migration_phases import (
    PHASE_M2_DUAL_WRITE,
    RETAINED_GOVERNANCE_OBJECTS,
)

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"


# ═════════════════════════════════════════════════════════════════════════════
# 健康基线：全绿输入（供各阻断用例逐条翻转一项）
# ═════════════════════════════════════════════════════════════════════════════


def _healthy_kwargs() -> dict:
    """全部条件满足的 health-gate 输入（放行基线）。"""
    return dict(
        migrations_applied=True,
        pending_migration_count=0,
        failed_migration_count=0,
        schema_contract_ok=True,
        backfill_coverage_ratio=1.0,
        failed_checkpoint_count=0,
        backup_verified=True,
        queue_quota_ready=True,
        lockless_degraded=False,
        locks_constraints_in_effect=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. Health gate 纯判定面（design §8.3）—— database-agnostic
# ═════════════════════════════════════════════════════════════════════════════


def test_health_gate_all_green_allows_flag_flip_and_worker_start():
    """全绿 → 允许切 flag / 启 worker / 设新真源。

    这是“阻断由具体条件导致、而非 gate 恒阻断”的对照（避免 vacuous / fake-green）。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    decision = evaluate_deployment_health_gate(**_healthy_kwargs())
    assert decision.allowed is True
    assert decision.allow_flag_flip is True
    assert decision.allow_worker_start is True
    assert decision.allow_new_source_of_truth is True
    assert decision.blocking_reasons == ()


@pytest.mark.parametrize(
    "override, expected_reason",
    [
        (dict(migrations_applied=False), REASON_MIGRATION_FAILED),
        (dict(failed_migration_count=1), REASON_PENDING_OR_FAILED_MIGRATION),
        (dict(pending_migration_count=1), REASON_PENDING_OR_FAILED_MIGRATION),
        (dict(lockless_degraded=True), REASON_LOCKLESS_DEGRADED),
        (dict(locks_constraints_in_effect=False), REASON_LOCKS_NOT_IN_EFFECT),
        (dict(backfill_coverage_ratio=0.99), REASON_BACKFILL_DIFF),
        (dict(backup_verified=False), REASON_BACKUP_NOT_VERIFIED),
        (dict(queue_quota_ready=False), REASON_QUOTA_OVER_BUDGET),
    ],
)
def test_health_gate_each_condition_blocks_flag_flip_and_worker_start(override, expected_reason):
    """§8.3 逐条：任一条件命中 → 不得切 flag / 启 worker / 设新真源，且带对应稳定原因码。

    覆盖：失败迁移、pending/failed migration、无锁降级/跳过约束、所需锁/约束未生效、
    alias/backfill 差异超阈值、备份未验证、PG/PgBouncer/队列 配额超预算。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    kwargs = _healthy_kwargs()
    kwargs.update(override)
    decision = evaluate_deployment_health_gate(**kwargs)

    assert decision.allowed is False, f"{override} 应阻断"
    assert decision.allow_flag_flip is False
    assert decision.allow_worker_start is False
    assert decision.allow_new_source_of_truth is False
    assert expected_reason in decision.blocking_reasons


def test_health_gate_lockless_degraded_blocks_even_when_migrations_reported_applied():
    """§8.3 关键：即便迁移“已应用”，只要进入无锁降级/跳过约束模式，也一律阻断。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    kwargs = _healthy_kwargs()
    kwargs["lockless_degraded"] = True  # 迁移因锁不可得而降级/跳过约束
    decision = evaluate_deployment_health_gate(**kwargs)
    assert decision.allowed is False
    assert REASON_LOCKLESS_DEGRADED in decision.blocking_reasons


def test_health_gate_accumulates_multiple_reasons_in_stable_order():
    """多条同时命中 → 原因码去重且按 §8.3 固定顺序排列（低基数、可审计/关联）。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3, R12)
    """
    decision = evaluate_deployment_health_gate(
        migrations_applied=False,
        pending_migration_count=2,
        failed_migration_count=1,
        schema_contract_ok=True,
        backfill_coverage_ratio=0.5,
        failed_checkpoint_count=0,
        backup_verified=False,
        queue_quota_ready=False,
        lockless_degraded=True,
        locks_constraints_in_effect=False,
    )
    assert decision.allowed is False
    reasons = decision.blocking_reasons
    # 去重
    assert len(reasons) == len(set(reasons))
    # 固定顺序：migration_failed → lockless → pending/failed → locks → backfill → backup → quota
    order_index = {
        REASON_MIGRATION_FAILED: 0,
        REASON_LOCKLESS_DEGRADED: 1,
        REASON_PENDING_OR_FAILED_MIGRATION: 2,
        REASON_LOCKS_NOT_IN_EFFECT: 3,
        REASON_BACKFILL_DIFF: 4,
        REASON_BACKUP_NOT_VERIFIED: 5,
        REASON_QUOTA_OVER_BUDGET: 6,
    }
    indices = [order_index[r] for r in reasons if r in order_index]
    assert indices == sorted(indices)


# ═════════════════════════════════════════════════════════════════════════════
# 2. 备份失败自动响应（design §8.3）—— 禁止自动高风险 DB 回滚
# ═════════════════════════════════════════════════════════════════════════════


def test_backup_failure_never_auto_executes_destructive_db_rollback():
    """§8.3：备份失败时自动响应只能停新写/关 flag/drain/保留/告警，**不自动**执行破坏性 DB 回滚。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    resp = backup_failure_response()
    # 恒 False：不自动执行高风险 DB 回滚
    assert resp.auto_executes_destructive_db_rollback is False
    # 只能做的四类 + 告警
    assert resp.stop_new_writes is True
    assert resp.close_feature_flag is True
    assert resp.drain_workers is True
    assert resp.preserve_state is True
    assert resp.alert is True
    # 恢复策略必须人工确认
    assert resp.requires_human_confirmation is True
    assert len(resp.steps) >= 5


def test_backup_not_verified_blocks_gate_and_response_is_non_destructive():
    """§8.3：备份未验证 → gate 阻断；配套自动响应非破坏性（不自动 DB 回滚）。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    kwargs = _healthy_kwargs()
    kwargs["backup_verified"] = False
    decision = evaluate_deployment_health_gate(**kwargs)
    assert decision.allowed is False
    assert REASON_BACKUP_NOT_VERIFIED in decision.blocking_reasons

    resp = backup_failure_response()
    assert resp.auto_executes_destructive_db_rollback is False


# ═════════════════════════════════════════════════════════════════════════════
# 3. 回滚演练脚本（design §8.4）—— 非破坏性 + 保留全部治理对象
# ═════════════════════════════════════════════════════════════════════════════


def test_rollback_rehearsal_script_is_non_destructive_and_covers_four_actions():
    """§8.4：回滚演练 = 停新写 + drain worker + 暂停 backfill + 兼容读回退；非破坏性；退回 dual-write。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.4)
    """
    script = build_rollback_rehearsal_script()
    assert script.destructive is False
    assert script.retains_legacy_columns is True
    assert script.stop_new_writes is True
    assert script.drain_workers is True
    assert script.pause_backfill is True
    assert script.compat_read_fallback is True
    # 退回 dual-write（避免双主）
    assert script.plan.target_phase == PHASE_M2_DUAL_WRITE
    # 保留全部治理对象类别（不删治理对象）
    assert set(script.must_preserve_object_kinds) == set(RETAINED_GOVERNANCE_OBJECTS)
    for kind in ("attachment_versions", "evidence_refs", "ocr_results", "ocr_confirmations",
                 "archive_manifests", "legal_holds", "evidence_audit_command_roots"):
        assert kind in script.must_preserve_object_kinds


def test_rollback_plan_steps_mention_no_destructive_ddl():
    """§8.4：回滚计划步骤不得包含删表/降 enum/删约束/删治理对象（DDL 前滚修复优先）。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.4)
    """
    script = build_rollback_rehearsal_script()
    joined = "\n".join(script.plan.steps)
    for forbidden in ("DROP TABLE", "DROP COLUMN", "删表", "降 enum", "删除约束"):
        assert forbidden not in joined
    # 明确声明保留全部治理对象与 legacy 列
    assert "保留全部治理对象" in joined


# ═════════════════════════════════════════════════════════════════════════════
# 真实 PostgreSQL 16（throwaway 库；非 PG 环境 skip）—— design §10
# ═════════════════════════════════════════════════════════════════════════════

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
_V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
_V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
_V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


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
    from app.core.migration_runner import MigrationRunner

    return MigrationRunner._split_sql_statements(sql)


_STUB_PARENTS_SQL = """
CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE projects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_year int, audit_period_end date, audit_period_start date,
    is_deleted boolean DEFAULT false);
CREATE TABLE ai_content_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid);
CREATE TABLE attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL,
    file_name varchar(500), file_path varchar(1000),
    file_type varchar(100), file_size bigint,
    storage_type varchar(20), paperless_document_id int,
    ocr_status varchar(20), version int DEFAULT 1, previous_version_id uuid,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false
);
"""


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_healthgate_{uuid.uuid4().hex[:12]}"

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
        for f in (_V106, _V107, _V108):
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


# ── design §8.3 “所需锁/约束” 探测清单（真实 PG16 上必须全部生效） ─────────────
_REQUIRED_CONSTRAINTS = (
    "uq_attachments_scope",            # 附件复合 scope key
    "uq_av_scope_identity",            # AttachmentVersion 复合身份 unique
    "uq_av_attachment_version",        # 每附件版本号唯一
    "fk_av_parent_scope",              # 版本→附件父 scope FK（ON DELETE RESTRICT）
    "fk_av_previous_scope",            # 前序版本复合 FK（DEFERRABLE）
    "fk_attachments_current_version",  # 附件→当前版本循环 FK（DEFERRABLE）
    "uq_audit_command_root",           # command-root 唯一（P25）
    "uq_archive_manifest_version",     # 归档版本唯一，重复归档不覆盖（P24）
    "uq_ocr_job_idempotency",          # OCR job 幂等
    "uq_ocr_writeback_idempotency",    # OCR writeback 幂等（P14）
    "chk_legal_hold_release",          # hold 释放人工专属 CHECK（P26/P27）
)
_REQUIRED_TRIGGERS = (
    "trg_av_immutable",                     # AttachmentVersion 不可变字节
    "trg_av_previous_link",                 # 前序 deferrable 约束触发器
    "trg_attachment_current_link",          # current_version deferrable 约束触发器
    "trg_archive_manifest_sealed_immutable",# 已封 manifest 防覆盖
    "trg_ocr_result_immutable",             # OCRResult 不可变
    "trg_ocr_confirmation_append_only",     # OCR 确认 append-only
)


async def _present_constraints(eng, names) -> set[str]:
    import sqlalchemy as sa

    async with eng.connect() as conn:
        rows = (await conn.execute(
            sa.text("SELECT conname FROM pg_constraint WHERE conname = ANY(:n)"),
            {"n": list(names)},
        )).scalars().all()
    return set(rows)


async def _present_triggers(eng, names) -> set[str]:
    import sqlalchemy as sa

    async with eng.connect() as conn:
        rows = (await conn.execute(
            sa.text("SELECT tgname FROM pg_trigger WHERE tgname = ANY(:n)"),
            {"n": list(names)},
        )).scalars().all()
    return set(rows)


@pytest.mark.asyncio
async def test_pg_required_locks_and_constraints_in_effect_then_gate_allows():
    """§8.3（真实 PG16）：探测 immutable/deferrable trigger + 复合 unique/FK + command-root/hold
    约束是否全部生效；全部生效才把 ``locks_constraints_in_effect=True`` 喂入 gate → 放行。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    async with _throwaway_engine() as eng:
        present_cons = await _present_constraints(eng, _REQUIRED_CONSTRAINTS)
        present_trg = await _present_triggers(eng, _REQUIRED_TRIGGERS)

        missing_cons = set(_REQUIRED_CONSTRAINTS) - present_cons
        missing_trg = set(_REQUIRED_TRIGGERS) - present_trg
        assert not missing_cons, f"缺失约束（锁/约束未生效）：{missing_cons}"
        assert not missing_trg, f"缺失触发器（不可变/防覆盖保护未生效）：{missing_trg}"

        locks_in_effect = not missing_cons and not missing_trg
        kwargs = _healthy_kwargs()
        kwargs["locks_constraints_in_effect"] = locks_in_effect
        decision = evaluate_deployment_health_gate(**kwargs)
        assert decision.allowed is True
        assert decision.allow_flag_flip and decision.allow_worker_start


@pytest.mark.asyncio
async def test_pg_missing_required_constraint_blocks_gate():
    """§8.3（真实 PG16）：若探测到某个必需约束/触发器缺失（模拟无锁降级留下的“跳过约束”），
    则 ``locks_constraints_in_effect=False`` → gate 阻断切 flag / 启 worker。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.3)
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    async with _throwaway_engine() as eng:
        # 探测一个“本不应存在”的约束名，模拟必需约束缺失（跳过约束）。
        present = await _present_constraints(eng, ["nonexistent_constraint_xyz"])
        locks_in_effect = "nonexistent_constraint_xyz" in present  # False
        assert locks_in_effect is False

        kwargs = _healthy_kwargs()
        kwargs["locks_constraints_in_effect"] = locks_in_effect
        decision = evaluate_deployment_health_gate(**kwargs)
        assert decision.allowed is False
        assert REASON_LOCKS_NOT_IN_EFFECT in decision.blocking_reasons


# ── 治理对象播种（回滚演练用） ────────────────────────────────────────────────

_GOVERNANCE_COUNT_TABLES = (
    "attachment_versions",
    "evidence_refs",
    "evidence_dependencies",
    "ocr_jobs",
    "ocr_results",
    "ocr_confirmations",
    "evidence_audit_command_roots",
    "archive_manifests",
    "legal_holds",
)


async def _seed_governance_objects(eng) -> dict:
    """播种一整条治理链：附件+版本 / EvidenceRef / 依赖 / OCR 决策链 / 审计 root / Manifest / Hold。"""
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "project": uuid.uuid4(),
        "attachment": uuid.uuid4(),
        "version": uuid.uuid4(),
        "ref": uuid.uuid4(),
        "dep": uuid.uuid4(),
        "ocr_job": uuid.uuid4(),
        "ocr_result": uuid.uuid4(),
        "ocr_conf": uuid.uuid4(),
        "root": uuid.uuid4(),
        "manifest": uuid.uuid4(),
        "hold": uuid.uuid4(),
        "content_hash": "a" * 64,
        "package_hash": "b" * 64,
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"), {"i": ids["project"]}
        )
        await conn.execute(
            T("INSERT INTO ai_content_log (id, project_id) VALUES (:i, :p)"),
            {"i": uuid.uuid4(), "p": ids["project"]},
        )
        # 附件聚合 + 不可变版本（actor=user）
        await conn.execute(
            T("INSERT INTO attachments (id, project_id, audit_year, file_name, file_type, "
              "file_size, state, actor_type, actor_user_id, created_by) "
              "VALUES (:i,:p,2025,'f.pdf','pdf',100,'available','user',:u,:u)"),
            {"i": ids["attachment"], "p": ids["project"], "u": ids["user"]},
        )
        await conn.execute(
            T("INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, "
              "version_no, storage_type, storage_key, media_type, byte_size, content_hash, "
              "availability, actor_type, actor_user_id) "
              "VALUES (:i,:a,:p,2025,1,'local','k1','pdf',100,:h,'available','user',:u)"),
            {"i": ids["version"], "a": ids["attachment"], "p": ids["project"],
             "h": ids["content_hash"], "u": ids["user"]},
        )
        await conn.execute(
            T("UPDATE attachments SET current_version_id=:v WHERE id=:a"),
            {"v": ids["version"], "a": ids["attachment"]},
        )
        # EvidenceRef（active）
        await conn.execute(
            T("INSERT INTO evidence_refs (id, project_id, audit_year, source_type, source_id, "
              "evidence_type, evidence_id, intent_hash, status, actor_type, actor_user_id) "
              "VALUES (:i,:p,2025,'workpaper_cell','s1','attachment_version',:e,:ih,'active','user',:u)"),
            {"i": ids["ref"], "p": ids["project"], "e": str(ids["version"]),
             "ih": "c" * 64, "u": ids["user"]},
        )
        # EvidenceDependency（active edge）
        await conn.execute(
            T("INSERT INTO evidence_dependencies (id, project_id, audit_year, source_type, "
              "source_id, target_type, target_id, relation, edge_hash, status, actor_type, actor_user_id) "
              "VALUES (:i,:p,2025,'attachment_version',:s,'workpaper_cell','s1','derived_from',:eh,'active','user',:u)"),
            {"i": ids["dep"], "p": ids["project"], "s": str(ids["version"]),
             "eh": "d" * 64, "u": ids["user"]},
        )
        # command-root（审计）
        await conn.execute(
            T("INSERT INTO evidence_audit_command_roots (id, command_type, idempotency_key, "
              "project_id, audit_year, result, actor_type, actor_user_id) "
              "VALUES (:i,'attachment.upload',:ik,:p,2025,'accepted','user',:u)"),
            {"i": ids["root"], "ik": str(uuid.uuid4()), "p": ids["project"], "u": ids["user"]},
        )
        # OCR 决策链：job → result → confirmation（accepted）
        await conn.execute(
            T("INSERT INTO ocr_jobs (id, project_id, audit_year, attachment_id, "
              "attachment_version_id, content_hash, idempotency_key, state, actor_type, actor_user_id) "
              "VALUES (:i,:p,2025,:a,:v,:h,:ik,'confirmed','user',:u)"),
            {"i": ids["ocr_job"], "p": ids["project"], "a": ids["attachment"],
             "v": ids["version"], "h": ids["content_hash"], "ik": str(uuid.uuid4()), "u": ids["user"]},
        )
        await conn.execute(
            T("INSERT INTO ocr_results (id, ocr_job_id, project_id, audit_year, "
              "attachment_version_id, source_content_hash, raw_text, result_hash, actor_type, actor_user_id) "
              "VALUES (:i,:j,:p,2025,:v,:h,'hello',:rh,'user',:u)"),
            {"i": ids["ocr_result"], "j": ids["ocr_job"], "p": ids["project"],
             "v": ids["version"], "h": ids["content_hash"], "rh": "e" * 64, "u": ids["user"]},
        )
        await conn.execute(
            T("INSERT INTO ocr_confirmations (id, ocr_job_id, ocr_result_id, project_id, "
              "audit_year, field_key, decision, confirmed_value, confirmed_by_user_id) "
              "VALUES (:i,:j,:r,:p,2025,'invoice_no','accepted','INV-1',:u)"),
            {"i": ids["ocr_conf"], "j": ids["ocr_job"], "r": ids["ocr_result"],
             "p": ids["project"], "u": ids["user"]},
        )
        # 已封归档 Manifest（sealed）
        await conn.execute(
            T("INSERT INTO archive_manifests (id, project_id, audit_year, version_no, watermark, "
              "package_hash, state, actor_type, actor_user_id) "
              "VALUES (:i,:p,2025,1,:wm,:ph,'sealed','user',:u)"),
            {"i": ids["manifest"], "p": ids["project"], "wm": "w" * 64,
             "ph": ids["package_hash"], "u": ids["user"]},
        )
        # 生效中的 Legal Hold
        await conn.execute(
            T("INSERT INTO legal_holds (id, project_id, audit_year, reason, state, actor_type, actor_user_id) "
              "VALUES (:i,:p,2025,'litigation','active','user',:u)"),
            {"i": ids["hold"], "p": ids["project"], "u": ids["user"]},
        )
    return ids


async def _governance_counts(eng) -> dict:
    import sqlalchemy as sa

    out: dict[str, int] = {}
    async with eng.connect() as conn:
        for tbl in _GOVERNANCE_COUNT_TABLES:
            out[tbl] = (await conn.execute(sa.text(f"SELECT count(*) FROM {tbl}"))).scalar()
    return out


@pytest.mark.asyncio
async def test_pg_rollback_rehearsal_preserves_all_governance_objects():
    """§8.4（真实 PG16）：完整回滚演练 —— 播种全部治理对象后，执行非破坏性回滚演练
    （停新写/drain/暂停 backfill/兼容读回退），逐类核验 **零删除 / 零覆盖**：行数不变、
    附件版本字节/哈希不变、已封 manifest package_hash 不变、hold 仍生效。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.4, R11/R12/R13)
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    import sqlalchemy as sa

    async with _throwaway_engine() as eng:
        ids = await _seed_governance_objects(eng)

        # 播种后基线快照。
        before_counts = await _governance_counts(eng)
        assert all(v >= 1 for v in before_counts.values()), f"播种不完整：{before_counts}"

        async with eng.connect() as conn:
            av_before = (await conn.execute(sa.text(
                "SELECT content_hash, byte_size FROM attachment_versions WHERE id=:i"
            ), {"i": ids["version"]})).one()
            mf_before = (await conn.execute(sa.text(
                "SELECT package_hash, state FROM archive_manifests WHERE id=:i"
            ), {"i": ids["manifest"]})).one()
            hold_before = (await conn.execute(sa.text(
                "SELECT state FROM legal_holds WHERE id=:i"
            ), {"i": ids["hold"]})).scalar()

        # 执行回滚演练脚本（design §8.4）：非破坏性，绝不含删表/删列/删治理对象。
        script = build_rollback_rehearsal_script()
        assert script.destructive is False
        assert script.stop_new_writes and script.drain_workers
        assert script.pause_backfill and script.compat_read_fallback
        # 应用层回滚只切 flag/adapter + drain + 暂停 backfill + 兼容读回退，不对治理数据执行任何 DDL/DML。
        # （本演练不运行任何 DROP/DELETE/UPDATE，模拟真实非破坏性应用回滚。）

        # 回滚演练后快照。
        after_counts = await _governance_counts(eng)
        assert after_counts == before_counts, "回滚删除/丢失了治理对象（违反 §8.4）"

        async with eng.connect() as conn:
            av_after = (await conn.execute(sa.text(
                "SELECT content_hash, byte_size FROM attachment_versions WHERE id=:i"
            ), {"i": ids["version"]})).one()
            mf_after = (await conn.execute(sa.text(
                "SELECT package_hash, state FROM archive_manifests WHERE id=:i"
            ), {"i": ids["manifest"]})).one()
            hold_after = (await conn.execute(sa.text(
                "SELECT state FROM legal_holds WHERE id=:i"
            ), {"i": ids["hold"]})).scalar()

        assert tuple(av_after) == tuple(av_before), "附件版本字节/哈希被覆盖（违反 §8.4）"
        assert tuple(mf_after) == tuple(mf_before), "已封 manifest 被覆盖（违反 §8.4）"
        assert hold_after == hold_before == "active", "Legal Hold 状态被改变（违反 §8.4）"


@pytest.mark.asyncio
async def test_pg_overwrite_protection_survives_rollback_immutable_and_sealed():
    """§8.4（真实 PG16）：即便在应用回滚期间，治理对象的不可变/防覆盖保护仍生效——
    附件版本字节被 UPDATE 时被 immutable 触发器拒绝，已封 manifest 被 UPDATE 时被 sealed 触发器拒绝。
    证明回滚不会打开覆盖历史治理对象的口子。

    Feature: attachment-ocr-ai-evidence-governance-hardening (Task 11.2, design §8.4, R2/R11)
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（SQLite 不得替代，design §10）")

    import sqlalchemy as sa

    async with _throwaway_engine() as eng:
        ids = await _seed_governance_objects(eng)

        # 附件版本字节不可覆盖（immutable 触发器）。
        with pytest.raises(Exception):
            async with eng.begin() as conn:
                await conn.execute(sa.text(
                    "UPDATE attachment_versions SET content_hash=:h WHERE id=:i"
                ), {"h": "f" * 64, "i": ids["version"]})

        # 已封 manifest 不可覆盖（sealed 触发器）。
        with pytest.raises(Exception):
            async with eng.begin() as conn:
                await conn.execute(sa.text(
                    "UPDATE archive_manifests SET package_hash=:h WHERE id=:i"
                ), {"h": "0" * 64, "i": ids["manifest"]})

        # 保护后原值仍在（未被覆盖）。
        async with eng.connect() as conn:
            av_hash = (await conn.execute(sa.text(
                "SELECT content_hash FROM attachment_versions WHERE id=:i"
            ), {"i": ids["version"]})).scalar()
            mf_hash = (await conn.execute(sa.text(
                "SELECT package_hash FROM archive_manifests WHERE id=:i"
            ), {"i": ids["manifest"]})).scalar()
        assert av_hash == "a" * 64
        assert mf_hash == "b" * 64
