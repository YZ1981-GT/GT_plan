"""Task 7.3 (Wave 6) — Legal Hold 统一图闭包 + 新增边监听 + 零效果 + purge 四条件 + 墓碑。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 7.3 (Wave 6)
Requirements: R2, R12, R13
Design: §4.6 (LegalHold/LegalHoldScope/EvidenceTombstone), §5.5 (Archive/Retention/Hold)
Properties:
  P26 — Legal Hold 单调保护：active hold 闭包内 delete/purge/overwrite 对任意授权级别恒零效果，
        无紧急绕过；替换只能新增版本。
  P27 — 保留期边界：仅 hold 已解除 ∧ retention 届满 ∧ 主体具 retention.purge ∧ 无悬空活动 ref 时可清理。

覆盖：
  * 纯单元（无 DB）：freeze_hold_closure / compute_new_edge_additions / evaluate_purge_conditions /
    subject_has_purge_capability / split_node_key —— P26/P27 决策面的确定性逻辑。
  * 真实 PG16（throwaway 库，用完即 DROP）：
    - activate_hold 固化 direct+transitive legal_hold_scopes + graph_watermark；
    - is_node_under_active_hold / authorize_destructive 对 admin/partner/auditor/service 恒零效果；
    - register_new_edge 单调扩展 transitive 保护；
    - release_hold 需独立人工 FK（service 拒绝）+ 范围历史保留；
    - evaluate_purge/purge 四条件（任一不满足 delta=0）+ 不可变墓碑（UPDATE/DELETE 被触发器拒绝）。

真实 PG 铁律（design §10.1/§10.2）：约束/触发器/事务在真实 PG16 验证，无 PG 环境 skip。
全局 Hypothesis fast profile（conftest）；本文件不固定 max_examples。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.retention_legal_hold_service import (
    PURGE_UNMET_CAPABILITY,
    PURGE_UNMET_DANGLING_REF,
    PURGE_UNMET_HOLD_ACTIVE,
    PURGE_UNMET_RETENTION,
    PurgeConditions,
    RetentionLegalHoldService,
    compute_new_edge_additions,
    evaluate_purge_conditions,
    freeze_hold_closure,
    split_node_key,
    subject_has_purge_capability,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    compute_canonical_edge_hash,
    normalize_node_key,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"
V111 = MIGRATIONS_DIR / "V111__evidence_governance_tombstones.sql"


# ===========================================================================
# helpers — build an in-memory UnifiedGraph
# ===========================================================================


def _edge(src: str, tgt: str) -> NormalizedEdge:
    return NormalizedEdge(
        source_key=src,
        target_key=tgt,
        provenance=EdgeProvenance.EVIDENCE_DEPENDENCY,
        edge_hash=compute_canonical_edge_hash(
            src.split(":", 1)[0], src.split(":", 1)[1],
            tgt.split(":", 1)[0], tgt.split(":", 1)[1],
            EdgeProvenance.EVIDENCE_DEPENDENCY,
        ),
    )


def _chain_graph() -> tuple[UnifiedGraph, str, str, str]:
    """attachment_version:A → wp_cell:X → report_row:R (linear chain)."""
    g = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
    a = normalize_node_key("attachment_version", "A")
    x = normalize_node_key("wp_cell", "X")
    r = normalize_node_key("report_row", "R")
    g.add_edge(_edge(a, x))
    g.add_edge(_edge(x, r))
    return g, a, x, r


# ===========================================================================
# 1) 纯单元 —— split_node_key
# ===========================================================================


class TestSplitNodeKey:
    def test_simple(self):
        assert split_node_key("attachment_version:A") == ("attachment_version", "A")

    def test_id_contains_colon(self):
        # ACNR-style URI id keeps its inner colons.
        assert split_node_key("acnr:WP:D2:D2-2:A1") == ("acnr", "WP:D2:D2-2:A1")

    def test_invalid(self):
        with pytest.raises(ValueError):
            split_node_key("no-separator")


# ===========================================================================
# 2) 纯单元 —— freeze_hold_closure (P26 闭包固化)
# ===========================================================================


class TestFreezeClosure:
    def test_direct_and_transitive(self):
        g, a, x, r = _chain_graph()
        closure = freeze_hold_closure(g, [a])
        assert closure.direct == frozenset({a})
        assert closure.transitive == frozenset({x, r})
        assert closure.all_keys == frozenset({a, x, r})

    def test_seed_downstream_only(self):
        # Seed at the middle → only its downstream is protected, not upstream.
        g, a, x, r = _chain_graph()
        closure = freeze_hold_closure(g, [x])
        assert closure.direct == frozenset({x})
        assert closure.transitive == frozenset({r})
        assert a not in closure.all_keys

    def test_cycle_safe(self):
        g = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
        n1, n2 = normalize_node_key("n", "1"), normalize_node_key("n", "2")
        g.add_edge(_edge(n1, n2))
        g.add_edge(_edge(n2, n1))
        closure = freeze_hold_closure(g, [n1])
        # BFS terminates; n2 reachable, n1 stays direct.
        assert closure.direct == frozenset({n1})
        assert closure.transitive == frozenset({n2})


# ===========================================================================
# 3) 纯单元 —— compute_new_edge_additions (P26 单调新增边)
# ===========================================================================


class TestNewEdgeAdditions:
    def test_source_protected_adds_target_closure(self):
        g, a, x, r = _chain_graph()
        # New edge from a protected node r → new node s → t.
        s = normalize_node_key("deliverable", "S")
        t = normalize_node_key("archive", "T")
        e1 = _edge(r, s)
        e2 = _edge(s, t)
        g.add_edge(e1)
        g.add_edge(e2)
        protected = frozenset({a, x, r})
        additions = compute_new_edge_additions(protected, g, e1)
        assert additions == frozenset({s, t})

    def test_source_not_protected_no_additions(self):
        g, a, x, r = _chain_graph()
        # An edge whose source is outside the protected set adds nothing.
        u = normalize_node_key("other", "U")
        v = normalize_node_key("other", "V")
        e = _edge(u, v)
        g.add_edge(e)
        protected = frozenset({a, x, r})
        assert compute_new_edge_additions(protected, g, e) == frozenset()

    def test_already_protected_target_no_dup(self):
        g, a, x, r = _chain_graph()
        # Edge a→r where both already protected → no new additions.
        e = _edge(a, r)
        g.add_edge(e)
        protected = frozenset({a, x, r})
        assert compute_new_edge_additions(protected, g, e) == frozenset()


# ===========================================================================
# 4) 纯单元 —— purge 四条件 (P27)
# ===========================================================================


class TestPurgeConditions:
    def test_all_met_allows(self):
        d = evaluate_purge_conditions(
            PurgeConditions(True, True, True, True)
        )
        assert d.allowed is True
        assert d.delta == 1
        assert d.unmet == ()

    @pytest.mark.parametrize(
        "conds,expected_code",
        [
            (PurgeConditions(False, True, True, True), PURGE_UNMET_HOLD_ACTIVE),
            (PurgeConditions(True, False, True, True), PURGE_UNMET_RETENTION),
            (PurgeConditions(True, True, False, True), PURGE_UNMET_CAPABILITY),
            (PurgeConditions(True, True, True, False), PURGE_UNMET_DANGLING_REF),
        ],
    )
    def test_any_unmet_zero_effect(self, conds, expected_code):
        d = evaluate_purge_conditions(conds)
        assert d.allowed is False
        assert d.delta == 0
        assert expected_code in d.unmet

    def test_multiple_unmet(self):
        d = evaluate_purge_conditions(PurgeConditions(False, False, False, False))
        assert d.allowed is False
        assert d.delta == 0
        assert set(d.unmet) == {
            PURGE_UNMET_HOLD_ACTIVE,
            PURGE_UNMET_RETENTION,
            PURGE_UNMET_CAPABILITY,
            PURGE_UNMET_DANGLING_REF,
        }


class TestPurgeCapability:
    def test_partner_admin_have_capability(self):
        assert subject_has_purge_capability("partner") is True
        assert subject_has_purge_capability("admin") is True

    def test_auditor_manager_qc_eqcr_readonly_denied(self):
        for role in ("auditor", "manager", "qc", "eqcr", "readonly"):
            assert subject_has_purge_capability(role) is False

    def test_service_identity_never(self):
        svc = ActorContext.for_service(uuid.uuid4())
        # Even if a caller passes a privileged role string, a service actor maps
        # to the service row and can never purge.
        assert subject_has_purge_capability("partner", actor=svc) is False
        assert subject_has_purge_capability("service") is False


# ===========================================================================
# 5) 真实 PG16 集成
# ===========================================================================


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


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_hold73_{uuid.uuid4().hex[:12]}"

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
        for f in (V106, V107, V108, V111):
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


def _sessionmaker(eng):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(eng, expire_on_commit=False)


async def _seed(eng):
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "user2": uuid.uuid4(),
        "project": uuid.uuid4(),
        "service": uuid.uuid4(),
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user2"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            T("INSERT INTO project_users (project_id, user_id) VALUES (:p, :u)"),
            {"p": ids["project"], "u": ids["user"]},
        )
        await conn.execute(
            T(
                "INSERT INTO service_identities (id, identity_key, display_name, is_active) "
                "VALUES (:i, :k, :n, true)"
            ),
            {"i": ids["service"], "k": f"svc-{uuid.uuid4().hex[:8]}", "n": "test-svc"},
        )
    return ids


def _scope(ids) -> GraphScope:
    return GraphScope(project_id=ids["project"], audit_year=2025)


def _svc(session, ids) -> RetentionLegalHoldService:
    return RetentionLegalHoldService(session)


async def _activate_chain_hold(session, ids):
    """Activate a hold seeded at attachment_version:A over an in-memory chain graph."""
    g, a, x, r = _chain_graph()
    svc = _svc(session, ids)
    res = await svc.activate_hold(
        scope=_scope(ids),
        reason="litigation preservation",
        actor=ActorContext.for_user(ids["user"]),
        seed_nodes=[("attachment_version", "A")],
        graph=g,
    )
    await session.commit()
    return svc, res, (a, x, r)


@pytest.mark.asyncio
async def test_activate_freezes_direct_and_transitive_scope():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, _ = await _activate_chain_hold(session, ids)
            assert res.direct_count == 1
            assert res.transitive_count == 2
            assert len(res.graph_watermark) == 64
        async with SM() as s2:
            rows = (await s2.execute(sa.text(
                "SELECT node_type, node_id, scope_kind, is_active FROM legal_hold_scopes "
                "WHERE legal_hold_id = :h ORDER BY scope_kind, node_id"
            ), {"h": res.legal_hold_id})).mappings().all()
            kinds = {(r["node_type"], r["node_id"]): r["scope_kind"] for r in rows}
            assert kinds[("attachment_version", "A")] == "direct"
            assert kinds[("wp_cell", "X")] == "transitive"
            assert kinds[("report_row", "R")] == "transitive"
            assert all(r["is_active"] for r in rows)


@pytest.mark.asyncio
async def test_destructive_zero_effect_all_actors():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, _ = await _activate_chain_hold(session, ids)
            # P26: any role / admin / service / emergency → zero-effect on protected ops.
            for role in ("auditor", "manager", "partner", "admin", "readonly"):
                for op in ("delete", "purge", "overwrite"):
                    with pytest.raises(EvidenceGovernanceError) as ei:
                        await svc.authorize_destructive(
                            actor_role=role,
                            operation=op,
                            project_id=ids["project"],
                            node_type="attachment_version",
                            node_id="A",
                        )
                    assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE
            # Service actor also blocked.
            with pytest.raises(EvidenceGovernanceError) as ei:
                await svc.authorize_destructive(
                    actor_role="service",
                    operation="delete",
                    project_id=ids["project"],
                    node_type="wp_cell",
                    node_id="X",
                    actor=ActorContext.for_service(ids["service"]),
                )
            assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE


@pytest.mark.asyncio
async def test_non_held_node_and_non_protected_op_pass():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, _ = await _activate_chain_hold(session, ids)
            # A node outside the closure → no block.
            await svc.authorize_destructive(
                actor_role="admin",
                operation="delete",
                project_id=ids["project"],
                node_type="attachment_version",
                node_id="ZZZ",
            )
            # Non-protected operation (e.g. read) on a held node → no block.
            await svc.authorize_destructive(
                actor_role="admin",
                operation="read",
                project_id=ids["project"],
                node_type="attachment_version",
                node_id="A",
            )


@pytest.mark.asyncio
async def test_register_new_edge_monotonic_extension():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, keys = await _activate_chain_hold(session, ids)
            a, x, r = keys
            # New edge from protected r → new node s → t.
            g, _, _, _ = _chain_graph()
            s = normalize_node_key("deliverable", "S")
            t = normalize_node_key("archive", "T")
            g.add_edge(_edge(r, s))
            g.add_edge(_edge(s, t))
            new_edge = _edge(r, s)
            out = await svc.register_new_edge(scope=_scope(ids), new_edge=new_edge, graph=g)
            await session.commit()
            assert set(out.added_keys) == {s, t}
            # The newly reached nodes are now under active hold.
            assert await svc.is_node_under_active_hold(
                project_id=ids["project"], node_type="deliverable", node_id="S"
            )
            assert await svc.is_node_under_active_hold(
                project_id=ids["project"], node_type="archive", node_id="T"
            )


@pytest.mark.asyncio
async def test_release_requires_human_fk_and_retains_scope():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, _ = await _activate_chain_hold(session, ids)
            # Service Identity cannot release.
            with pytest.raises(EvidenceGovernanceError) as ei:
                await svc.release_hold(
                    legal_hold_id=res.legal_hold_id,
                    released_by_user_id=ids["user"],
                    release_reason="x",
                    actor=ActorContext.for_service(ids["service"]),
                )
            assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
            # Empty reason rejected.
            with pytest.raises(EvidenceGovernanceError):
                await svc.release_hold(
                    legal_hold_id=res.legal_hold_id,
                    released_by_user_id=ids["user"],
                    release_reason="  ",
                    actor=ActorContext.for_user(ids["user"]),
                )
            # Valid release by human.
            await svc.release_hold(
                legal_hold_id=res.legal_hold_id,
                released_by_user_id=ids["user2"],
                release_reason="matter closed",
                actor=ActorContext.for_user(ids["user"]),
            )
            await session.commit()
        async with SM() as s2:
            hold = (await s2.execute(sa.text(
                "SELECT state, released_by_user_id, released_at, release_reason "
                "FROM legal_holds WHERE id = :i"
            ), {"i": res.legal_hold_id})).mappings().first()
            assert hold["state"] == "released"
            assert str(hold["released_by_user_id"]) == str(ids["user2"])
            assert hold["released_at"] is not None
            assert hold["release_reason"] == "matter closed"
            # Scope history retained (not deleted).
            n = (await s2.execute(sa.text(
                "SELECT count(*) FROM legal_hold_scopes WHERE legal_hold_id = :i"
            ), {"i": res.legal_hold_id})).scalar()
            assert n == 3
            # No longer under active hold.
            svc2 = RetentionLegalHoldService(s2)
            assert not await svc2.is_node_under_active_hold(
                project_id=ids["project"], node_type="attachment_version", node_id="A"
            )


async def _insert_active_ref(session, ids, evidence_type, evidence_id):
    from app.services.evidence_governance.frozen_contracts import content_hash_of

    await session.execute(
        sa.text(
            "INSERT INTO evidence_refs "
            "(id, project_id, audit_year, source_type, source_id, evidence_type, "
            " evidence_id, intent_hash, status, actor_type, actor_user_id) "
            "VALUES (:id, :pid, 2025, 'wp_cell', 'src-1', :et, :eid, :ih, 'active', "
            " 'user', :uid)"
        ),
        {
            "id": uuid.uuid4(),
            "pid": str(ids["project"]),
            "et": evidence_type,
            "eid": evidence_id,
            "ih": content_hash_of({"e": evidence_id}),
            "uid": str(ids["user"]),
        },
    )


@pytest.mark.asyncio
async def test_purge_four_conditions_and_immutable_tombstone():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc, res, _ = await _activate_chain_hold(session, ids)

            # (1) active hold → purge blocked (delta 0).
            d = await svc.evaluate_purge(
                project_id=ids["project"], node_type="attachment_version", node_id="A",
                actor_role="partner", retention_expired=True,
            )
            assert d.allowed is False and d.delta == 0
            assert PURGE_UNMET_HOLD_ACTIVE in d.unmet

            # release hold
            await svc.release_hold(
                legal_hold_id=res.legal_hold_id,
                released_by_user_id=ids["user"],
                release_reason="done",
                actor=ActorContext.for_user(ids["user"]),
            )
            await session.commit()

            # (2) released but retention not expired → blocked.
            d = await svc.evaluate_purge(
                project_id=ids["project"], node_type="attachment_version", node_id="A",
                actor_role="partner", retention_expired=False,
            )
            assert d.delta == 0 and PURGE_UNMET_RETENTION in d.unmet

            # (3) released + retention expired but no capability (auditor) → blocked.
            d = await svc.evaluate_purge(
                project_id=ids["project"], node_type="attachment_version", node_id="A",
                actor_role="auditor", retention_expired=True,
            )
            assert d.delta == 0 and PURGE_UNMET_CAPABILITY in d.unmet

            # (4) dangling active EvidenceRef → blocked even with all else met.
            await _insert_active_ref(session, ids, "attachment_version", "A")
            await session.commit()
            d = await svc.evaluate_purge(
                project_id=ids["project"], node_type="attachment_version", node_id="A",
                actor_role="partner", retention_expired=True,
            )
            assert d.delta == 0 and PURGE_UNMET_DANGLING_REF in d.unmet
            # No tombstone should have been created by any blocked evaluation.
            n0 = (await session.execute(sa.text(
                "SELECT count(*) FROM evidence_tombstones"
            ))).scalar()
            assert n0 == 0

            # Deactivate the dangling ref so all four conditions hold.
            await session.execute(sa.text(
                "UPDATE evidence_refs SET status = 'inactive', deactivation_reason = 'x' "
                "WHERE evidence_type = 'attachment_version' AND evidence_id = 'A'"
            ))
            await session.commit()

            # All four met → purge effected (delta 1) + immutable tombstone.
            result = await svc.purge(
                project_id=ids["project"], audit_year=2025,
                node_type="attachment_version", node_id="A",
                actor_role="partner", actor=ActorContext.for_user(ids["user"]),
                retention_expired=True, purged_by_user_id=ids["user"],
                content_hash="a" * 64, retention_policy_version="rp-1",
                metadata_redacted={"note": "purged"},
            )
            await session.commit()
            assert result.decision.allowed is True
            assert result.decision.delta == 1
            assert result.tombstone_id is not None

        async with SM() as s2:
            tomb = (await s2.execute(sa.text(
                "SELECT purge_reason, purged_by_user_id, content_hash, retention_policy_version "
                "FROM evidence_tombstones WHERE id = :i"
            ), {"i": result.tombstone_id})).mappings().first()
            assert tomb["purge_reason"] == "retention_expired"
            assert str(tomb["purged_by_user_id"]) == str(ids["user"])
            assert tomb["content_hash"] == "a" * 64
            # Immutable: UPDATE and DELETE both rejected by trigger.
            with pytest.raises(Exception):
                await s2.execute(sa.text(
                    "UPDATE evidence_tombstones SET purge_reason = 'manual_purge' WHERE id = :i"
                ), {"i": result.tombstone_id})
                await s2.commit()
        async with SM() as s3:
            with pytest.raises(Exception):
                await s3.execute(sa.text(
                    "DELETE FROM evidence_tombstones WHERE id = :i"
                ), {"i": result.tombstone_id})
                await s3.commit()
