"""Task 8.1 (Wave 7) — M0–M4 阶段状态机 + M1 checkpoint backfill 契约测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 8.1
Requirements: R14（迁移兼容与可恢复回填）, R16（历史覆盖）
Design: §8.2 M0–M4、§8.3 Health Gate、§8.4 Rollback、§4.1/§4.3 Attachment 聚合
Properties: P3（创建主体完备）, P4（版本递增/不可变）, P28（迁移幂等守恒）, P29（降级安全）

分层（design §10.1/§10.2 铁律）：
  1. **纯 PBT（fast profile）**：阶段状态机单调推进 + 行为矩阵不变量；backfill 聚合链分析
     的覆盖/确定性/可证明性。
  2. **真实 PG16 集成**：在既有 legacy attachments 上跑 M1 backfill —— 可证明字段回填、
     未知 creator→migration identity、legacy_unverified_chain 标记、audit_year 未知跳过、
     legacy 列保留、content_hash 不臆造、checkpoint 幂等、重跑零新增（P28）。

真实约束/触发器/幂等只在 PostgreSQL 16 验证，不以 SQLite 代替。无 PG 时 skip。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance import migration_phases as MP
from app.services.evidence_governance.backfill_runner import (
    BACKFILL_MIGRATION_VERSION,
    EvidenceBackfillRunner,
    build_backfill_aggregates,
    build_batch_key,
    compute_input_hash,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


# ===========================================================================
# 1) 纯 PBT — 阶段状态机（design §8.2/§8.3/§8.4）
# ===========================================================================


class TestMigrationPhaseMatrix:
    def test_five_phases_ordered(self):
        assert MP.PHASES == ("M0", "M1", "M2", "M3", "M4")

    def test_m0_dark_read_writes_nothing(self):
        b = MP.phase_behavior(MP.PHASE_M0_DARK_READ)
        assert b.write_compat_mirror is False
        assert b.new_source_of_truth is False
        assert b.p0_hard_block is False
        assert b.all_gates_enabled is False

    def test_m1_backfill_active_no_cutover(self):
        b = MP.phase_behavior(MP.PHASE_M1_BACKFILL)
        assert b.backfill_active is True
        assert b.new_source_of_truth is False

    def test_m2_dual_write_p0_hard_block(self):
        b = MP.phase_behavior(MP.PHASE_M2_DUAL_WRITE)
        assert b.write_compat_mirror is True
        assert b.new_source_of_truth is False  # legacy 仍权威
        assert b.p0_hard_block is True

    def test_m3_cutover_source_of_truth_and_gates(self):
        b = MP.phase_behavior(MP.PHASE_M3_CUTOVER)
        assert b.new_source_of_truth is True
        assert b.all_gates_enabled is True
        assert b.write_compat_mirror is True  # 仍写镜像供兼容读

    def test_m4_retirement_stops_mirror_keeps_source(self):
        b = MP.phase_behavior(MP.PHASE_M4_RETIREMENT)
        assert b.write_compat_mirror is False  # 停非必要 mirror
        assert b.new_source_of_truth is True
        assert b.all_gates_enabled is True

    def test_unknown_phase_raises(self):
        with pytest.raises(ValueError):
            MP.phase_behavior("MX")


class TestPhaseAdvanceMonotonic:
    @settings(deadline=None)
    @given(
        ci=st.integers(min_value=0, max_value=4),
        ti=st.integers(min_value=0, max_value=4),
        checks=st.booleans(),
    )
    def test_advance_only_single_forward_step_with_checks(self, ci, ti, checks):
        cur, tgt = MP.PHASES[ci], MP.PHASES[ti]
        ok, _ = MP.can_advance(cur, tgt, checks_passed=checks)
        if ti == ci:
            assert ok  # no-op 允许
        elif ti < ci:
            assert not ok  # 回退不允许
        elif ti - ci > 1:
            assert not ok  # 跳阶段不允许
        else:  # 恰好下一步
            assert ok is checks

    def test_p0_hard_block_monotonic_from_m2(self):
        """P0 hard-block 一旦在 M2 启用，M3/M4 不回退（单调）。"""
        blocks = [MP.phase_behavior(p).p0_hard_block for p in MP.PHASES]
        assert blocks == [False, False, True, True, True]

    def test_new_source_of_truth_monotonic_from_m3(self):
        sot = [MP.phase_behavior(p).new_source_of_truth for p in MP.PHASES]
        assert sot == [False, False, False, True, True]


class TestCutoverAndRetirementAndRollback:
    def test_cutover_blocked_when_backfill_incomplete(self):
        pre = MP.evaluate_cutover_preconditions(
            migrations_applied=True,
            pending_migration_count=0,
            failed_migration_count=0,
            schema_contract_ok=True,
            backfill_coverage_ratio=0.9,  # < 1.0
            failed_checkpoint_count=0,
            backup_verified=True,
            queue_quota_ready=True,
        )
        assert not pre.passed
        assert "backfill_coverage" in pre.failures()

    def test_cutover_blocked_on_failed_checkpoint_or_pending_migration(self):
        pre = MP.evaluate_cutover_preconditions(
            migrations_applied=True,
            pending_migration_count=1,
            failed_migration_count=0,
            schema_contract_ok=True,
            backfill_coverage_ratio=1.0,
            failed_checkpoint_count=2,
            backup_verified=True,
            queue_quota_ready=True,
        )
        assert not pre.passed
        assert "pending_or_failed_migration" in pre.failures()
        assert "failed_checkpoint" in pre.failures()

    def test_cutover_passes_when_all_green(self):
        pre = MP.evaluate_cutover_preconditions(
            migrations_applied=True,
            pending_migration_count=0,
            failed_migration_count=0,
            schema_contract_ok=True,
            backfill_coverage_ratio=1.0,
            failed_checkpoint_count=0,
            backup_verified=True,
            queue_quota_ready=True,
        )
        assert pre.passed and pre.failures() == []

    def test_retirement_requires_zero_legacy_write_telemetry(self):
        assert not MP.evaluate_retirement_preconditions(
            legacy_write_events_in_window=3, cutover_stable=True
        ).passed
        assert MP.evaluate_retirement_preconditions(
            legacy_write_events_in_window=0, cutover_stable=True
        ).passed

    def test_rollback_is_non_destructive_and_retains_legacy(self):
        plan = MP.production_rollback_plan(from_phase=MP.PHASE_M3_CUTOVER)
        assert plan.destructive is False
        assert plan.retain_legacy_columns is True
        assert plan.target_phase == MP.PHASE_M2_DUAL_WRITE
        # 保留全部治理对象类别（不删 AttachmentVersion/EvidenceRef/OCR/审计/Manifest/Hold/checkpoint）
        assert "attachment_versions" in plan.retained_object_kinds
        assert "evidence_migration_checkpoints" in plan.retained_object_kinds
        assert "legacy_attachment_alias" in plan.retained_object_kinds


# ===========================================================================
# 2) 纯 PBT — backfill 聚合链分析（覆盖 / 确定性 / 可证明性）
# ===========================================================================


def _row(rid, prev=None, version=1, project="P", year=2025):
    return {
        "id": rid,
        "project_id": project,
        "audit_year": year,
        "version": version,
        "previous_version_id": prev,
    }


class TestBuildAggregatesUnit:
    def test_singleton_no_prev_is_provable_root(self):
        a = uuid.uuid4()
        aggs = build_backfill_aggregates([_row(a)])
        assert len(aggs) == 1
        assert aggs[0].unverified_chain is False
        assert [v["id"] for v in aggs[0].versions] == [a]

    def test_singleton_dangling_prev_is_unverified(self):
        a = uuid.uuid4()
        aggs = build_backfill_aggregates([_row(a, prev=uuid.uuid4())])
        assert len(aggs) == 1
        assert aggs[0].unverified_chain is True

    def test_provable_two_version_chain(self):
        v1, v2 = uuid.uuid4(), uuid.uuid4()
        rows = [_row(v1, version=1), _row(v2, prev=v1, version=2)]
        aggs = build_backfill_aggregates(rows)
        assert len(aggs) == 1
        assert aggs[0].unverified_chain is False
        assert [v["id"] for v in aggs[0].versions] == [v1, v2]  # root 在前，current 在后

    def test_branching_chain_is_unverified_split(self):
        """分叉（同一 prev 两个后继）不可证明 → 拆为独立单版本聚合，全部标 unverified。"""
        root = uuid.uuid4()
        c1, c2 = uuid.uuid4(), uuid.uuid4()
        rows = [_row(root, version=1), _row(c1, prev=root, version=2), _row(c2, prev=root, version=2)]
        aggs = build_backfill_aggregates(rows)
        assert len(aggs) == 3
        assert all(a.unverified_chain for a in aggs)

    def test_decreasing_version_chain_is_unverified(self):
        v1, v2 = uuid.uuid4(), uuid.uuid4()
        rows = [_row(v1, version=5), _row(v2, prev=v1, version=2)]  # 递减
        aggs = build_backfill_aggregates(rows)
        assert all(a.unverified_chain for a in aggs)

    def test_cross_scope_chain_is_unverified(self):
        v1, v2 = uuid.uuid4(), uuid.uuid4()
        rows = [_row(v1, version=1, year=2025), _row(v2, prev=v1, version=2, year=2024)]
        aggs = build_backfill_aggregates(rows)
        assert all(a.unverified_chain for a in aggs)


class TestBuildAggregatesProperties:
    @settings(deadline=None)
    @given(
        n=st.integers(min_value=1, max_value=8),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_coverage_every_row_appears_exactly_once(self, n, seed):
        """P28 基础：每个输入行在聚合的 versions 中恰好出现一次（不丢不重）。"""
        import random

        rng = random.Random(seed)
        ids = [uuid.uuid4() for _ in range(n)]
        rows = []
        for i, rid in enumerate(ids):
            # 随机 prev：None / 指向前一个 / 悬空
            choice = rng.randint(0, 2)
            if choice == 0 or i == 0:
                prev = None
            elif choice == 1:
                prev = ids[rng.randint(0, i - 1)]
            else:
                prev = uuid.uuid4()  # 悬空
            rows.append(_row(rid, prev=prev, version=rng.randint(1, 5)))
        aggs = build_backfill_aggregates(rows)
        seen = [v["id"] for a in aggs for v in a.versions]
        assert sorted(map(str, seen)) == sorted(map(str, ids))
        assert len(seen) == len(ids)

    @settings(deadline=None)
    @given(n=st.integers(min_value=1, max_value=6), seed=st.integers(min_value=0, max_value=10_000))
    def test_deterministic(self, n, seed):
        import random

        rng = random.Random(seed)
        ids = [uuid.uuid4() for _ in range(n)]
        rows = []
        for i, rid in enumerate(ids):
            prev = None if i == 0 or rng.random() < 0.5 else ids[i - 1]
            rows.append(_row(rid, prev=prev, version=i + 1))
        a1 = build_backfill_aggregates(list(rows))
        a2 = build_backfill_aggregates(list(rows))
        assert [[str(v["id"]) for v in a.versions] for a in a1] == [
            [str(v["id"]) for v in a.versions] for a in a2
        ]

    @settings(deadline=None)
    @given(n=st.integers(min_value=2, max_value=6))
    def test_provable_linear_chain_stays_single_aggregate(self, n):
        """严格线性递增链（v1→v2→...→vn，同 scope）→ 单一可证明聚合，顺序 root..current。"""
        ids = [uuid.uuid4() for _ in range(n)]
        rows = [_row(ids[0], version=1)]
        for i in range(1, n):
            rows.append(_row(ids[i], prev=ids[i - 1], version=i + 1))
        aggs = build_backfill_aggregates(rows)
        assert len(aggs) == 1
        assert aggs[0].unverified_chain is False
        assert [v["id"] for v in aggs[0].versions] == ids


class TestBatchKey:
    def test_batch_key_contains_version_project_partition_hash(self):
        p = uuid.uuid4()
        ih = compute_input_hash([uuid.uuid4(), uuid.uuid4()])
        key = build_batch_key(p, 2025, "p0000", ih)
        assert key.startswith(BACKFILL_MIGRATION_VERSION + ":")
        assert str(p) in key
        assert "2025" in key
        assert "p0000" in key
        assert ih in key

    def test_input_hash_order_independent_and_stable(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        assert compute_input_hash([a, b]) == compute_input_hash([b, a])
        assert compute_input_hash([a, b]) == compute_input_hash([a, b])


# ===========================================================================
# 3) 真实 PG16 集成 — M1 checkpoint backfill
# ===========================================================================


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
    storage_type varchar(20) DEFAULT 'paperless',
    paperless_document_id int,
    ocr_status varchar(20), version int DEFAULT 1, previous_version_id uuid,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false
);
"""


async def _apply_all(eng) -> None:
    for f in (V106, V107, V108):
        stmts = _split(f.read_text(encoding="utf-8"))
        async with eng.begin() as conn:
            for s in stmts:
                await conn.exec_driver_sql(s)


@asynccontextmanager
async def _throwaway_db():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_m1_{uuid.uuid4().hex[:12]}"

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


@asynccontextmanager
async def _session(eng):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    maker = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s


async def _seed_legacy(eng):
    """在 migration 前建 legacy 数据 → apply 全迁移（历史库路径）。返回 id 字典。"""
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "proj": uuid.uuid4(),
        "proj_no_year": uuid.uuid4(),
        "known": uuid.uuid4(),          # 已知 creator 单件
        "unknown": uuid.uuid4(),        # 未知 creator 单件
        "chain_v1": uuid.uuid4(),       # 可证明链 v1
        "chain_v2": uuid.uuid4(),       # 可证明链 v2
        "dangling": uuid.uuid4(),       # 悬空 prev（不可证明）
        "no_year": uuid.uuid4(),        # audit_year 无法证明
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_period_end) VALUES (:i, DATE '2025-12-31')"),
            {"i": ids["proj"]},
        )
        # 无任何年度线索的项目 → 其附件 audit_year 回填仍为 NULL
        await conn.execute(
            T("INSERT INTO projects (id) VALUES (:i)"), {"i": ids["proj_no_year"]}
        )

        def _ins(aid, proj, *, created_by, version=1, prev=None, size=100, ftype="pdf", storage="paperless", pdoc=None):
            return conn.execute(
                T(
                    "INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size,"
                    " storage_type, paperless_document_id, ocr_status, version, previous_version_id, created_by) "
                    "VALUES (:a,:p,:fn,:fp,:ft,:sz,:stg,:pd,'pending',:v,:prev,:cb)"
                ),
                {
                    "a": aid, "p": proj, "fn": f"{ftype}-{str(aid)[:6]}.{ftype}",
                    "fp": f"/abs/secret/{aid}.{ftype}", "ft": ftype, "sz": size,
                    "stg": storage, "pd": pdoc, "v": version, "prev": prev, "cb": created_by,
                },
            )

        await _ins(ids["known"], ids["proj"], created_by=ids["user"], size=111, storage="paperless", pdoc=42)
        await _ins(ids["unknown"], ids["proj"], created_by=None, size=222, storage="local")
        await _ins(ids["chain_v1"], ids["proj"], created_by=ids["user"], version=1, size=333)
        await _ins(ids["chain_v2"], ids["proj"], created_by=ids["user"], version=2, prev=ids["chain_v1"], size=334)
        await _ins(ids["dangling"], ids["proj"], created_by=ids["user"], version=2, prev=uuid.uuid4(), size=444)
        await _ins(ids["no_year"], ids["proj_no_year"], created_by=ids["user"], size=555)
    await _apply_all(eng)
    return ids


@pytest.mark.asyncio
async def test_m1_backfill_provable_fields_and_migration_identity():
    """M1 回填：可证明字段、未知 creator→migration identity、unverified 标记、
    audit_year 未知跳过、content_hash 不臆造、legacy 列保留（R14/P3/P4）。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T

    async with _throwaway_db() as eng:
        ids = await _seed_legacy(eng)
        async with _session(eng) as db:
            runner = EvidenceBackfillRunner(db, batch_size=2)
            report = await runner.run(ids["proj"])

        # 扫描到 proj 下 5 条 legacy（known/unknown/chain_v1/chain_v2/dangling）
        assert report.scanned == 5
        # 聚合：known / unknown / dangling(unverified) / chain(v1+v2) = 4 个聚合
        assert report.aggregates == 4
        # 版本：4 单件等价（known+unknown+dangling=3）+ 链 2 = 5 个 AttachmentVersion
        assert report.versions_created == 5
        assert report.aliases_created == 5
        assert report.unknown_creator == 1
        assert report.unverified_chains == 1  # dangling

        async with eng.connect() as conn:
            # --- 未知 creator → migration Service Identity + original_creator_unknown ---
            svc_id = (
                await conn.execute(T("SELECT id FROM service_identities WHERE identity_key='migration'"))
            ).scalar()
            row = (
                await conn.execute(
                    T(
                        "SELECT av.actor_type, av.actor_service_identity_id, av.actor_user_id,"
                        " av.original_creator_unknown, av.content_hash, av.byte_size, av.media_type,"
                        " av.storage_type, av.storage_key, av.version_no "
                        "FROM legacy_attachment_alias al JOIN attachment_versions av "
                        "ON av.id = al.attachment_version_id WHERE al.old_attachment_id=:o"
                    ),
                    {"o": ids["unknown"]},
                )
            ).one()
            (atype, asvc, auser, unk, chash, bsize, mtype, stype, skey, vno) = row
            assert atype == "service"
            assert asvc == svc_id
            assert auser is None
            assert unk is True
            assert chash is None                 # content_hash 不臆造
            assert bsize == 222                   # 可证明 byte_size
            assert stype == "local"
            assert vno == 1

            # --- 已知 creator → user actor，paperless storage_key opaque ---
            krow = (
                await conn.execute(
                    T(
                        "SELECT av.actor_type, av.actor_user_id, av.original_creator_unknown,"
                        " av.storage_key, av.byte_size "
                        "FROM legacy_attachment_alias al JOIN attachment_versions av "
                        "ON av.id = al.attachment_version_id WHERE al.old_attachment_id=:o"
                    ),
                    {"o": ids["known"]},
                )
            ).one()
            assert krow[0] == "user"
            assert krow[1] == ids["user"]
            assert krow[2] is False
            assert krow[3] == "paperless:42"     # opaque，不含绝对路径
            assert "/abs/secret" not in (krow[3] or "")
            assert krow[4] == 111

            # --- 可证明链：单聚合，2 版本，version_no 1→2 严格递增，previous 链正确 ---
            chain_alias = (
                await conn.execute(
                    T(
                        "SELECT al.old_attachment_id, al.attachment_id, al.resolution_kind,"
                        " av.version_no, av.previous_version_id, av.config_snapshot "
                        "FROM legacy_attachment_alias al JOIN attachment_versions av "
                        "ON av.id = al.attachment_version_id "
                        "WHERE al.old_attachment_id IN (:v1,:v2) ORDER BY av.version_no"
                    ),
                    {"v1": ids["chain_v1"], "v2": ids["chain_v2"]},
                )
            ).all()
            assert len(chain_alias) == 2
            # 两个旧 id 折叠到同一聚合根 = chain_v1
            assert chain_alias[0][1] == ids["chain_v1"]
            assert chain_alias[1][1] == ids["chain_v1"]
            assert [r[3] for r in chain_alias] == [1, 2]              # 严格递增
            assert chain_alias[0][2] == "root"
            assert chain_alias[1][2] == "current_version"
            assert chain_alias[1][4] is not None                     # v2.previous 指向 v1 的新 AV
            # 链聚合不标 unverified
            assert chain_alias[0][5]["backfill"]["legacy_unverified_chain"] is False

            # --- 悬空 prev → unverified 单件 ---
            drow = (
                await conn.execute(
                    T(
                        "SELECT av.version_no, av.config_snapshot, al.resolution_kind "
                        "FROM legacy_attachment_alias al JOIN attachment_versions av "
                        "ON av.id = al.attachment_version_id WHERE al.old_attachment_id=:o"
                    ),
                    {"o": ids["dangling"]},
                )
            ).one()
            assert drow[0] == 1                                       # 独立根 version_no=1
            assert drow[1]["backfill"]["legacy_unverified_chain"] is True
            assert drow[2] == "root"

            # --- root attachment 设置 current_version + actor（legacy 列不动）---
            arow = (
                await conn.execute(
                    T(
                        "SELECT current_version_id, actor_type, actor_user_id, file_name, file_size, created_by "
                        "FROM attachments WHERE id=:a"
                    ),
                    {"a": ids["known"]},
                )
            ).one()
            assert arow[0] is not None                               # current_version 已设
            assert arow[1] == "user"
            assert arow[2] == ids["user"]
            assert arow[4] == 111                                    # legacy file_size 保留
            assert arow[5] == ids["user"]                            # legacy created_by 保留

            # --- checkpoint：batch_key 含 V106，status done ---
            cps = (
                await conn.execute(
                    T(
                        "SELECT migration_version, batch_key, status, actor_type "
                        "FROM evidence_migration_checkpoints ORDER BY partition_key"
                    )
                )
            ).all()
            assert len(cps) >= 1
            assert all(c[0] == BACKFILL_MIGRATION_VERSION for c in cps)
            assert all(c[1].startswith("V106:") for c in cps)
            assert all(c[2] == "done" for c in cps)
            assert all(c[3] == "service" for c in cps)


@pytest.mark.asyncio
async def test_m1_backfill_rerun_idempotent_p28():
    """P28：重跑不新增 AttachmentVersion / alias / checkpoint 副作用；对象基数稳定。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T

    async with _throwaway_db() as eng:
        ids = await _seed_legacy(eng)
        async with _session(eng) as db:
            r1 = await EvidenceBackfillRunner(db, batch_size=2).run(ids["proj"])
        async with eng.connect() as conn:
            av1 = (await conn.execute(T("SELECT count(*) FROM attachment_versions"))).scalar()
            al1 = (await conn.execute(T("SELECT count(*) FROM legacy_attachment_alias"))).scalar()
            cp1 = (await conn.execute(T("SELECT count(*) FROM evidence_migration_checkpoints"))).scalar()

        # 重跑
        async with _session(eng) as db:
            r2 = await EvidenceBackfillRunner(db, batch_size=2).run(ids["proj"])
        async with eng.connect() as conn:
            av2 = (await conn.execute(T("SELECT count(*) FROM attachment_versions"))).scalar()
            al2 = (await conn.execute(T("SELECT count(*) FROM legacy_attachment_alias"))).scalar()
            cp2 = (await conn.execute(T("SELECT count(*) FROM evidence_migration_checkpoints"))).scalar()

        assert r1.versions_created == 5
        assert r2.scanned == 0                    # 全部已回填（alias 存在）→ 无待处理
        assert r2.versions_created == 0
        assert r2.aliases_created == 0
        assert (av1, al1, cp1) == (av2, al2, cp2), "重跑改变对象基数（P28 违反）"
        assert av2 == 5 and al2 == 5


@pytest.mark.asyncio
async def test_m1_backfill_skips_unknown_audit_year():
    """audit_year 无法证明的项目附件不臆造 alias（NOT NULL scope）→ 计入 skipped_no_audit_year。"""
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    from sqlalchemy import text as T

    async with _throwaway_db() as eng:
        ids = await _seed_legacy(eng)
        async with _session(eng) as db:
            report = await EvidenceBackfillRunner(db).run(ids["proj_no_year"])
        assert report.scanned == 1
        assert report.skipped_no_audit_year == 1
        assert report.versions_created == 0
        async with eng.connect() as conn:
            n_alias = (
                await conn.execute(
                    T("SELECT count(*) FROM legacy_attachment_alias WHERE old_attachment_id=:o"),
                    {"o": ids["no_year"]},
                )
            ).scalar()
            assert n_alias == 0
            # legacy 行本身保留
            keep = (
                await conn.execute(T("SELECT file_size FROM attachments WHERE id=:a"), {"a": ids["no_year"]})
            ).scalar()
            assert keep == 555
