"""Task 7.5 (Wave 6) capstone — archive/hold backend unit/integration/contract.

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 7.5 (Wave 6)
Requirements: R11, R12, R13
Design: §5.5 (Archive/Retention/Legal Hold), §10.1/§10.2 (testing strategy),
        §11/§12 (P23–P27, UAT-12/UAT-13 matrix)
Properties:
  P24 — manifest 防覆盖：重复归档始终创建新包，历史包字节/清单/hash 保持不变。
  P26 — Legal Hold 单调保护：hold 闭包内 delete/purge/overwrite 对任意授权级别恒零效果。
  P27 — 保留期边界：hold 已解除 ∧ retention 届满 ∧ 具 retention.purge ∧ 无悬空活动 ref
        四条件全满足才可清理；任一不满足 delta=0。

本文件是 Wave 6 archive + legal hold 域的验证 capstone（tasks 7.1–7.4）。它 **不重复**
已由 7.1/7.2/7.3 覆盖的用例，而是补齐以下真实缺口并做跨域集成：

  1. **失败才有阻断报告、成功无阻断报告**（R11.2）—— 用 passing/failing gate 做归档全流程契约断言。
  2. **sealed 防覆盖字节级不变（P24）** —— 二次归档后，第一个已封包的 manifest_hash /
     package_hash / entries 逐字节不变（in-memory service 未覆盖此字节级不变式）。
  3. **hold 无绕过（P26）+ purge 四条件（P27）** —— 纯谓词 capstone 矩阵 + 真实 PG16。
  4. **离线 verifier** —— 不连接业务库重算 member/manifest/package hash；二次归档后历史包仍验签通过。
  5. **真实 PG16（throwaway 库）** —— archive_manifests sealed 不可变触发器
     （building→sealed 允许，sealed 后 UPDATE 拒绝）、版本唯一约束（重复归档不覆盖历史）、
     以及 hold 覆盖 sealed 归档包节点的 delete/overwrite/purge 三类操作零效果 + 墓碑不可变。

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
from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifestService,
    ArchiveResult,
    SealedPackage,
    verify_package_offline,
)
from app.services.evidence_governance.formal_output_gate import (
    EvidenceItem,
    FormalOutputGate,
    PolicyProvider,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.offline_manifest_verifier import (
    OfflineManifestVerifier,
    VerificationStatus,
    serialize_sealed_package,
)
from app.services.evidence_governance.retention_legal_hold_service import (
    PURGE_UNMET_CAPABILITY,
    PURGE_UNMET_DANGLING_REF,
    PURGE_UNMET_HOLD_ACTIVE,
    PURGE_UNMET_RETENTION,
    PurgeConditions,
    RetentionLegalHoldService,
    evaluate_purge_conditions,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    compute_canonical_edge_hash,
    normalize_node_key,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"
V111 = MIGRATIONS_DIR / "V111__evidence_governance_tombstones.sql"


# ===========================================================================
# gate fixtures
# ===========================================================================


class _FailPolicy(PolicyProvider):
    """Policy that always yields an incomplete-metadata evidence item → gate fails."""

    async def get_policy_required_evidence(
        self, target_id, target_type, policy_version=None
    ):
        return [
            EvidenceItem(
                evidence_id="capstone-fail-ev",
                evidence_type="attachment_version",
                source="policy",
                metadata_complete=False,
                has_actor=True,
            )
        ]


def _passing_service() -> ArchiveManifestService:
    return ArchiveManifestService(gate=FormalOutputGate())


def _failing_service() -> ArchiveManifestService:
    return ArchiveManifestService(gate=FormalOutputGate(policy_provider=_FailPolicy()))


def _scope() -> GraphScope:
    return GraphScope(project_id=uuid.uuid4(), audit_year=2025)


def _actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


async def _archive_once(
    service: ArchiveManifestService,
    scope: GraphScope,
    actor: ActorContext,
    *,
    evidence_items: list[dict] | None = None,
) -> ArchiveResult:
    manifest = await service.preflight(scope, actor)
    if evidence_items is not None:
        await service.build_manifest(manifest, evidence_items=evidence_items)
    return await service.finalize(manifest, actor)


# ===========================================================================
# 1) 契约：失败才有阻断报告，成功无阻断报告（R11.2）
# ===========================================================================


class TestBlockingReportContract:
    """R11.2 — blocking difference report ONLY when validation fails AND blocks."""

    @pytest.mark.asyncio
    async def test_success_produces_no_blocking_report(self):
        scope, actor = _scope(), _actor()
        result = await _archive_once(
            _passing_service(),
            scope,
            actor,
            evidence_items=[
                {"id": "e1", "type": "attachment_version", "object_id": "o1",
                 "version": "1", "content_hash": "a" * 64, "state": "available"},
            ],
        )
        assert result.success is True
        assert result.sealed_package is not None
        # KEY invariant: no blocking difference report on success.
        assert result.blocking_report is None
        assert result.has_blocking_report is False

    @pytest.mark.asyncio
    async def test_failure_produces_full_machine_readable_blocking_report(self):
        scope, actor = _scope(), _actor()
        result = await _archive_once(_failing_service(), scope, actor)
        assert result.success is False
        assert result.sealed_package is None
        assert result.has_blocking_report is True
        report = result.blocking_report
        assert report is not None
        assert len(report.blocking_reasons) > 0
        mr = report.to_machine_readable()
        assert mr["is_blocking"] is True
        assert mr["blocking_reason_count"] == len(report.blocking_reasons)
        assert mr["evidence_gaps"] == report.evidence_gaps
        # Each machine-readable gap carries a stable code + description.
        assert all("code" in g and "description" in g for g in mr["blocking_reasons"])

    @pytest.mark.asyncio
    async def test_failed_archive_creates_no_sealed_package_version(self):
        """A blocked archive must not consume a version / create a package."""
        scope, actor = _scope(), _actor()
        service = _failing_service()
        r1 = await _archive_once(service, scope, actor)
        r2 = await _archive_once(service, scope, actor)
        assert r1.success is False and r2.success is False
        # No sealed package persisted for either attempt.
        assert service.get_sealed_packages(scope) == []


# ===========================================================================
# 2) P24 —— sealed 防覆盖字节级不变（二次归档不改历史包）
# ===========================================================================


class TestSealedAntiOverwriteByteLevel:
    """P24 — repeated archive creates a NEW version; the historical sealed
    package (manifest_hash / package_hash / entries / edges) is byte-immutable."""

    @pytest.mark.asyncio
    async def test_rearchive_leaves_first_package_bytes_unchanged(self):
        scope, actor = _scope(), _actor()
        service = _passing_service()

        r1 = await _archive_once(
            service, scope, actor,
            evidence_items=[
                {"id": "e1", "type": "attachment_version", "object_id": "o1",
                 "version": "1", "content_hash": "a" * 64, "state": "available"},
            ],
        )
        assert r1.success and r1.sealed_package is not None
        pkg1 = r1.sealed_package

        # Snapshot the first package's frozen bytes.
        v1 = pkg1.version
        manifest_hash_1 = pkg1.manifest.manifest_hash
        package_hash_1 = pkg1.package_hash
        entry_snapshot_1 = [
            (e.entry_id, e.entry_type.value, e.object_id, e.content_hash)
            for e in pkg1.manifest.entries
        ]
        offline_before = serialize_sealed_package(pkg1)

        # Second archive with a DIFFERENT evidence set → new version.
        r2 = await _archive_once(
            service, scope, actor,
            evidence_items=[
                {"id": "e2", "type": "ocr_result", "object_id": "o2",
                 "version": "2", "content_hash": "b" * 64, "state": "confirmed"},
                {"id": "e3", "type": "ai_content", "object_id": "o3",
                 "version": "1", "content_hash": "c" * 64, "state": "confirmed"},
            ],
        )
        assert r2.success and r2.sealed_package is not None
        assert r2.sealed_package.version == v1 + 1  # strictly increments

        # The FIRST package is byte-identical after the second archive.
        packages = service.get_sealed_packages(scope)
        assert len(packages) == 2
        first = next(p for p in packages if p.version == v1)
        assert first.manifest.manifest_hash == manifest_hash_1
        assert first.package_hash == package_hash_1
        assert [
            (e.entry_id, e.entry_type.value, e.object_id, e.content_hash)
            for e in first.manifest.entries
        ] == entry_snapshot_1
        # Offline serialization is byte-stable too.
        assert serialize_sealed_package(first) == offline_before

    @pytest.mark.asyncio
    async def test_reseal_rejected(self):
        """A sealed manifest cannot be re-sealed (immutability guard)."""
        scope, actor = _scope(), _actor()
        r = await _archive_once(_passing_service(), scope, actor)
        assert r.sealed_package is not None
        with pytest.raises(EvidenceGovernanceError):
            r.sealed_package.manifest.seal()


# ===========================================================================
# 3) 离线 verifier —— 不连接业务库；二次归档后历史包仍验签
# ===========================================================================


class TestOfflineVerifierCapstone:
    """Offline verifier recomputes member/manifest/package hash without DB."""

    @pytest.mark.asyncio
    async def test_both_versions_verify_offline_after_rearchive(self):
        scope, actor = _scope(), _actor()
        service = _passing_service()
        r1 = await _archive_once(
            service, scope, actor,
            evidence_items=[{"id": "e1", "type": "attachment_version",
                             "object_id": "o1", "version": "1",
                             "content_hash": "a" * 64, "state": "available"}],
        )
        r2 = await _archive_once(
            service, scope, actor,
            evidence_items=[{"id": "e2", "type": "ocr_result", "object_id": "o2",
                             "version": "1", "content_hash": "b" * 64,
                             "state": "confirmed"}],
        )
        assert r1.sealed_package and r2.sealed_package

        verifier = OfflineManifestVerifier()
        for pkg in service.get_sealed_packages(scope):
            # in-process helper
            assert verify_package_offline(pkg) is True
            # standalone offline verifier (dict form, no DB)
            res = verifier.verify_package(serialize_sealed_package(pkg))
            assert res.status == VerificationStatus.PASSED
            assert res.is_valid and res.difference_count == 0

    def test_offline_verifier_module_has_no_db_imports(self):
        """The offline verifier must not import DB session/connection modules."""
        import inspect

        import app.services.evidence_governance.offline_manifest_verifier as mod

        src = inspect.getsource(mod)
        for forbidden in ("sqlalchemy", "asyncpg", "AsyncSession",
                          "create_async_engine", "get_db", "async_session"):
            assert f"import {forbidden}" not in src
            assert f"from {forbidden}" not in src


# ===========================================================================
# 4) 纯谓词 capstone —— hold 无绕过意图 / purge 四条件
# ===========================================================================


class TestPurgeFourConditionMatrix:
    """P27 — purge allowed IFF all four conditions hold; any unmet ⇒ delta=0."""

    def test_all_four_met_allows(self):
        d = evaluate_purge_conditions(PurgeConditions(True, True, True, True))
        assert d.allowed is True and d.delta == 1 and d.unmet == ()

    @pytest.mark.parametrize(
        "conds,code",
        [
            (PurgeConditions(False, True, True, True), PURGE_UNMET_HOLD_ACTIVE),
            (PurgeConditions(True, False, True, True), PURGE_UNMET_RETENTION),
            (PurgeConditions(True, True, False, True), PURGE_UNMET_CAPABILITY),
            (PurgeConditions(True, True, True, False), PURGE_UNMET_DANGLING_REF),
        ],
    )
    def test_single_unmet_zero_effect(self, conds, code):
        d = evaluate_purge_conditions(conds)
        assert d.allowed is False and d.delta == 0 and code in d.unmet


# ===========================================================================
# 5) 真实 PG16 集成
# ===========================================================================


def _edge(src: str, tgt: str) -> NormalizedEdge:
    st, si = src.split(":", 1)
    tt, ti = tgt.split(":", 1)
    return NormalizedEdge(
        source_key=src,
        target_key=tgt,
        provenance=EdgeProvenance.EVIDENCE_DEPENDENCY,
        edge_hash=compute_canonical_edge_hash(
            st, si, tt, ti, EdgeProvenance.EVIDENCE_DEPENDENCY
        ),
    )


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
    tmp_db = f"evgov_cap75_{uuid.uuid4().hex[:12]}"

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

    ids = {"user": uuid.uuid4(), "user2": uuid.uuid4(),
           "project": uuid.uuid4(), "service": uuid.uuid4()}
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
            {"i": ids["service"], "k": f"svc-{uuid.uuid4().hex[:8]}", "n": "cap75-svc"},
        )
    return ids


async def _insert_manifest(conn, *, pid, uid, version_no, state="building", package_hash=None):
    from sqlalchemy import text as T

    mid = uuid.uuid4()
    await conn.execute(
        T(
            "INSERT INTO archive_manifests "
            "(id, project_id, audit_year, version_no, watermark, package_hash, state, "
            " actor_type, actor_user_id) "
            "VALUES (:id, :pid, 2025, :vn, :wm, :ph, :st, 'user', :uid)"
        ),
        {
            "id": mid, "pid": str(pid), "vn": version_no,
            "wm": "w" * 64, "ph": package_hash, "st": state, "uid": str(uid),
        },
    )
    return mid


# ─── 5a. archive_manifests sealed 不可变触发器（P24）────────────────────────


@pytest.mark.asyncio
async def test_pg_archive_manifest_building_to_sealed_then_immutable():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        # building → sealed is allowed.
        async with eng.begin() as conn:
            mid = await _insert_manifest(conn, pid=ids["project"], uid=ids["user"],
                                         version_no=1, state="building")
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                f"UPDATE archive_manifests SET state='sealed', "
                f"package_hash='{'a' * 64}', sealed_at=now() WHERE id='{mid}'"
            )
        # sealed → any UPDATE is rejected by the immutability trigger.
        with pytest.raises(Exception):
            async with eng.begin() as conn:
                await conn.exec_driver_sql(
                    f"UPDATE archive_manifests SET package_hash='{'b' * 64}' "
                    f"WHERE id='{mid}'"
                )
        # Row still carries the sealed bytes (no partial mutation).
        async with eng.connect() as conn:
            row = (await conn.execute(sa.text(
                "SELECT state, package_hash FROM archive_manifests WHERE id=:i"
            ), {"i": mid})).mappings().first()
        assert row["state"] == "sealed"
        assert row["package_hash"] == "a" * 64


# ─── 5b. archive_manifests 版本唯一约束（重复归档不覆盖历史）────────────────


@pytest.mark.asyncio
async def test_pg_archive_manifest_version_unique_no_overwrite():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        async with eng.begin() as conn:
            await _insert_manifest(conn, pid=ids["project"], uid=ids["user"], version_no=1)
        # Re-using the same (project, year, version_no) is rejected → cannot overwrite.
        with pytest.raises(Exception):
            async with eng.begin() as conn:
                await _insert_manifest(conn, pid=ids["project"], uid=ids["user"], version_no=1)
        # A new archive must increment the version; history is preserved.
        async with eng.begin() as conn:
            await _insert_manifest(conn, pid=ids["project"], uid=ids["user"], version_no=2)
        async with eng.connect() as conn:
            versions = (await conn.execute(sa.text(
                "SELECT version_no FROM archive_manifests "
                "WHERE project_id=:p ORDER BY version_no"
            ), {"p": str(ids["project"])})).scalars().all()
        assert versions == [1, 2]


# ─── 5c. 跨域：hold 覆盖 sealed 归档包节点 → delete/overwrite/purge 零效果 ──


@pytest.mark.asyncio
async def test_pg_hold_over_archive_package_blocks_destructive_and_purge():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        # Build an in-memory unified graph: archive package → deliverable.
        g = UnifiedGraph(scope=GraphScope(project_id=ids["project"], audit_year=2025))
        pkg_node = normalize_node_key("archive", "PKG-1")
        deliverable = normalize_node_key("deliverable", "DLV-1")
        g.add_edge(_edge(pkg_node, deliverable))

        async with SM() as session:
            svc = RetentionLegalHoldService(session)
            res = await svc.activate_hold(
                scope=GraphScope(project_id=ids["project"], audit_year=2025),
                reason="litigation preserves sealed archive package",
                actor=ActorContext.for_user(ids["user"]),
                seed_nodes=[("archive", "PKG-1")],
                graph=g,
            )
            await session.commit()
            assert res.direct_count == 1
            assert res.transitive_count == 1  # deliverable pulled in

            # P26: every authorization level blocked on the sealed package node.
            for role in ("auditor", "manager", "partner", "admin", "readonly"):
                for op in ("delete", "overwrite", "purge"):
                    with pytest.raises(EvidenceGovernanceError) as ei:
                        await svc.authorize_destructive(
                            actor_role=role, operation=op,
                            project_id=ids["project"],
                            node_type="archive", node_id="PKG-1",
                        )
                    assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE
            # Service identity + emergency-style role also blocked on the downstream node.
            with pytest.raises(EvidenceGovernanceError) as ei:
                await svc.authorize_destructive(
                    actor_role="service", operation="overwrite",
                    project_id=ids["project"], node_type="deliverable", node_id="DLV-1",
                    actor=ActorContext.for_service(ids["service"]),
                )
            assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE

            # P27: purge of the held package is blocked (hold active), delta=0, no tombstone.
            decision = await svc.evaluate_purge(
                project_id=ids["project"], node_type="archive", node_id="PKG-1",
                actor_role="partner", retention_expired=True,
            )
            assert decision.allowed is False and decision.delta == 0
            assert PURGE_UNMET_HOLD_ACTIVE in decision.unmet

        async with SM() as s2:
            n = (await s2.execute(sa.text(
                "SELECT count(*) FROM evidence_tombstones"
            ))).scalar()
            assert n == 0


# ─── 5d. purge 四条件全满足 → delta=1 + 不可变墓碑（UPDATE/DELETE 拒绝）─────


@pytest.mark.asyncio
async def test_pg_purge_all_conditions_met_then_immutable_tombstone():
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")
    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            svc = RetentionLegalHoldService(session)
            # No active hold, retention expired, partner has purge capability,
            # no dangling active ref → all four conditions met.
            result = await svc.purge(
                project_id=ids["project"], audit_year=2025,
                node_type="archive", node_id="PKG-9",
                actor_role="partner", actor=ActorContext.for_user(ids["user"]),
                retention_expired=True, purged_by_user_id=ids["user"],
                content_hash="d" * 64, retention_policy_version="rp-cap-75",
                metadata_redacted={"note": "capstone purge"},
            )
            await session.commit()
            assert result.decision.allowed is True and result.decision.delta == 1
            assert result.tombstone_id is not None

        # Tombstone is immutable: both UPDATE and DELETE are rejected by triggers.
        async with SM() as s2:
            with pytest.raises(Exception):
                await s2.execute(sa.text(
                    "UPDATE evidence_tombstones SET purge_reason='manual_purge' WHERE id=:i"
                ), {"i": result.tombstone_id})
                await s2.commit()
        async with SM() as s3:
            with pytest.raises(Exception):
                await s3.execute(sa.text(
                    "DELETE FROM evidence_tombstones WHERE id=:i"
                ), {"i": result.tombstone_id})
                await s3.commit()
        async with SM() as s4:
            tomb = (await s4.execute(sa.text(
                "SELECT purge_reason, content_hash, retention_policy_version "
                "FROM evidence_tombstones WHERE id=:i"
            ), {"i": result.tombstone_id})).mappings().first()
        assert tomb["purge_reason"] == "retention_expired"
        assert tomb["content_hash"] == "d" * 64
        assert tomb["retention_policy_version"] == "rp-cap-75"
