"""Feature: attachment-ocr-ai-evidence-governance-hardening

Wave 8 / Task 9.5 — archive-hold **合并属性组** PBT（逐项覆盖 P23–P27）。

本文件是 Wave 8 的 **专属属性组测试层**：把已在 Wave 6（tasks 7.1–7.4）落地的真实治理服务
（``ArchiveManifestService`` / ``FormalOutputGate`` / ``UnifiedGraphBuilder`` /
``RetentionLegalHoldService`` / ``CommandAuditService`` / ``OfflineManifestVerifier`` /
``role_capability_contract``）的不可协商不变量，以生成式输入逐项作为属性重新证明。
**不重新实现任何业务逻辑**——所有断言都调用真实服务的纯函数 / 决策面 / DB 约束 / 触发器。

设计基线（design §10.1/§10.2）：闭包 / 谓词 / manifest 完备性用全局 ``fast`` profile 的
graph/pure reference model；**immutable trigger、unique 约束、purge 四条件（真实落库）** 必须
跑真实 PostgreSQL 16（读 ``settings.DATABASE_URL``，非 PG 环境自动 skip）。属性测试不在正文
固定 ``max_examples``；样本数由 ``backend/tests/conftest.py`` 的全局 fast profile（默认 5，可用
``HYPOTHESIS_MAX_EXAMPLES`` 覆盖）统一收敛。失败时保留 Hypothesis 原始 counterexample。

## 复用而非重复（引用既有等价用例）

- **P24 sealed 防覆盖 / P26 hold 无绕过 / P27 purge 四条件（in-memory + 单点 PG）**：
  已由 ``tests/evidence_governance/test_archive_hold_capstone_wave6_7_5.py`` 以单例/矩阵覆盖。
  本文件不复制其单例，而是补充「生成式输入」层：任意归档序列的字节不变式（P24）、任意
  role×operation 的零效果（P26）、四条件全部 2^4 组合（P27），以及真实 PG16 的 **command-root
  唯一 + transition 多条（P25）** 生成式证明——这是 capstone 未以生成式覆盖的核心缺口。

Requirements: R11, R12, R13
Properties: P23, P24, P25, P26, P27
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifestService,
    verify_package_offline,
)
from app.services.evidence_governance.command_audit import (
    CommandAuditService,
    redact_audit_metadata,
)
from app.services.evidence_governance.formal_output_gate import (
    EvidenceItem,
    FormalOutputGate,
    PolicyProvider,
    UnifiedGraphProvider,
)
from app.services.evidence_governance.frozen_contracts import ActorContext
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
    PurgeDecision,
    compute_new_edge_additions,
    evaluate_purge_conditions,
    freeze_hold_closure,
    subject_has_purge_capability,
)
from app.services.evidence_governance.role_capability_contract import (
    LEGAL_HOLD_PROTECTED_OPERATIONS,
    SERVICE_IDENTITY,
    SYSTEM_ROLES,
    legal_hold_permits,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    compute_canonical_edge_hash,
    normalize_node_key,
)


# ═════════════════════════════════════════════════════════════════════════════
# 共享构造器（graph / evidence 生成）
# ═════════════════════════════════════════════════════════════════════════════


def _edge(src_type: str, src_id: str, tgt_type: str, tgt_id: str) -> NormalizedEdge:
    return NormalizedEdge(
        source_key=normalize_node_key(src_type, src_id),
        target_key=normalize_node_key(tgt_type, tgt_id),
        provenance=EdgeProvenance.EVIDENCE_DEPENDENCY,
        edge_hash=compute_canonical_edge_hash(
            src_type, src_id, tgt_type, tgt_id, EdgeProvenance.EVIDENCE_DEPENDENCY
        ),
    )


class _ListPolicy(PolicyProvider):
    """Policy provider returning a fixed list of policy-required evidence items."""

    def __init__(self, items: list[EvidenceItem]) -> None:
        self._items = items

    async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
        return list(self._items)

    async def get_policy_version(self, target_id, target_type):
        return "policy-v1"


class _ListGraphProvider(UnifiedGraphProvider):
    """Graph provider returning a fixed list of existing-dependency evidence items."""

    def __init__(self, items: list[EvidenceItem]) -> None:
        self._items = items

    async def get_existing_dependencies(self, target_id, target_type):
        return list(self._items)


def _ev(evidence_id: str, source: str, *, metadata_complete=True, has_actor=True) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        evidence_type="attachment_version",
        source=source,
        metadata_complete=metadata_complete,
        has_actor=has_actor,
    )


# ═════════════════════════════════════════════════════════════════════════════
# P23 manifest 精确完备 — manifest nodes/edges 恰等于
#   (policy-required 证据 ∪ 已有依赖) 在归档范围内形成的可达证据图；
#   历史无附件不扩大图；已有证据的 P0 完整性不放宽。
# ═════════════════════════════════════════════════════════════════════════════


@given(
    policy_ids=st.lists(st.integers(min_value=0, max_value=8), min_size=0, max_size=6, unique=True),
    dep_ids=st.lists(st.integers(min_value=0, max_value=8), min_size=0, max_size=6, unique=True),
    # historical-no-attachment 对象：既非 policy 必需，也非已有依赖 → 不得进入 manifest。
    historical_ids=st.lists(st.integers(min_value=20, max_value=28), min_size=0, max_size=5, unique=True),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_p23_manifest_entries_equal_required_evidence_union(policy_ids, dep_ids, historical_ids):
    """P23：manifest entry 集合恰等于 (policy 必需 ∪ 已有依赖) 去重集；
    历史无附件对象（既非 policy 必需也非已有依赖）绝不扩大该集合。

    exercises 真实 ``FormalOutputGate._build_required_evidence`` (union+dedup)
    + 真实 ``ArchiveManifestService.build_manifest`` (entries from evidence set)。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23
    """
    policy_items = [_ev(f"e{i}", "policy") for i in policy_ids]
    dep_items = [_ev(f"e{i}", "dependency") for i in dep_ids]
    gate = FormalOutputGate(
        policy_provider=_ListPolicy(policy_items),
        graph_provider=_ListGraphProvider(dep_items),
    )

    # 真实 gate 构造 RequiredEvidence（policy ∪ deps，按 evidence_id 去重，policy 优先）。
    required = await gate._build_required_evidence("archive:p:2025", "archive", "policy-v1")
    required_ids = {it.evidence_id for it in required}

    # 期望：并集恰为 policy_ids ∪ dep_ids（用同一 e{i} 命名）；historical 绝不出现。
    expected_ids = {f"e{i}" for i in set(policy_ids) | set(dep_ids)}
    assert required_ids == expected_ids
    for hid in historical_ids:
        assert f"e{hid}" not in required_ids, "P23 违反：历史无附件对象扩大了证据图"

    # manifest entries 恰由 RequiredEvidence 驱动（object_id == evidence_id）。
    service = ArchiveManifestService(gate=gate)
    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    actor = ActorContext.for_user(uuid.uuid4())
    manifest = await service.preflight(scope, actor)
    evidence_items = [
        {"id": it.evidence_id, "type": it.evidence_type, "object_id": it.evidence_id,
         "version": "1", "content_hash": "a" * 64, "state": "available"}
        for it in required
    ]
    await service.build_manifest(manifest, evidence_items=evidence_items)
    manifest_ids = {e.object_id for e in manifest.entries}
    assert manifest_ids == expected_ids, "P23 违反：manifest 节点集合 ≠ 可达证据图"


@st.composite
def _reachable_graph(draw):
    """生成一个小依赖图 + 一组 root 节点；返回 (edges, root_keys, expected_edge_hashes)。"""
    n = draw(st.integers(min_value=1, max_value=5))
    node_ids = [f"o{i}" for i in range(n)]
    edge_pairs = draw(
        st.lists(
            st.tuples(st.sampled_from(node_ids), st.sampled_from(node_ids)),
            min_size=0, max_size=6,
        )
    )
    edges = [_edge("attachment_version", a, "attachment_version", b)
             for (a, b) in edge_pairs if a != b]
    return edges


@given(edges=_reachable_graph())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_p23_manifest_edges_equal_graph_edges_deduped(edges):
    """P23：manifest edges 恰等于 UnifiedGraph 去重后的边集（按 canonical edge_hash）。

    exercises 真实 ``UnifiedGraph.add_edge`` 去重 + ``build_manifest`` 边填充逻辑
    （manifest.edges 逐边来自 graph.edges）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23
    """
    graph = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
    for e in edges:
        graph.add_edge(e)
    # graph 去重后的 canonical edge_hash 集合。
    graph_hashes = set(graph.edges.keys())

    # build_manifest 从 graph.edges.values() 逐边写入 → manifest 边 hash 集合恒等。
    service = ArchiveManifestService()
    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    actor = ActorContext.for_user(uuid.uuid4())
    manifest = await service.preflight(scope, actor)
    await service.build_manifest(manifest, graph=graph)
    manifest_hashes = {e.edge_hash for e in manifest.edges}
    assert manifest_hashes == graph_hashes, "P23 违反：manifest 边集 ≠ 去重后的可达图边集"


@given(
    bad_meta=st.booleans(),
    bad_actor=st.booleans(),
)
def test_p23_existing_evidence_p0_integrity_not_relaxed(bad_meta, bad_actor):
    """P23：manifest 完备 ≠ P0 放宽——已有/被引用证据若 metadata/actor 缺失，
    真实 gate ``_validate_evidence_set`` 仍产生 blocking reason（不因归档而豁免）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23
    """
    gate = FormalOutputGate()
    item = _ev("e0", "dependency",
               metadata_complete=not bad_meta, has_actor=not bad_actor)
    reasons = gate._validate_evidence_set([item])
    codes = {r.code.value for r in reasons}
    if bad_meta:
        assert "METADATA_INCOMPLETE" in codes
    if bad_actor:
        assert "ACTOR_MISSING" in codes
    if not bad_meta and not bad_actor:
        assert reasons == []


# ═════════════════════════════════════════════════════════════════════════════
# P24 防覆盖 — 重复归档始终创建新版本；历史包字节 / manifest / hash 不变。
# ═════════════════════════════════════════════════════════════════════════════


@given(
    archive_count=st.integers(min_value=2, max_value=5),
    seed=st.integers(min_value=0, max_value=9999),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_p24_repeated_archive_new_version_history_byte_immutable(archive_count, seed):
    """P24：对同一 scope 连续归档 N 次，版本严格递增 1..N；每次归档后，此前所有已封包
    的 manifest_hash / package_hash / 离线序列化字节保持不变，且仍离线验签通过。

    exercises 真实 ``ArchiveManifestService.finalize`` (versioned seal) +
    ``serialize_sealed_package`` + ``verify_package_offline`` + ``OfflineManifestVerifier``。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 24
    """
    service = ArchiveManifestService(gate=FormalOutputGate())  # default gate → passes
    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    actor = ActorContext.for_user(uuid.uuid4())
    verifier = OfflineManifestVerifier()

    snapshots: dict[int, tuple[str, str, dict]] = {}
    for k in range(1, archive_count + 1):
        manifest = await service.preflight(scope, actor)
        await service.build_manifest(
            manifest,
            evidence_items=[
                {"id": f"e{seed}-{k}", "type": "attachment_version",
                 "object_id": f"o{seed}-{k}", "version": str(k),
                 "content_hash": f"{k:064d}", "state": "available"},
            ],
        )
        result = await service.finalize(manifest, actor)
        assert result.success and result.sealed_package is not None
        assert result.sealed_package.version == k  # strictly increments 1..N

        # 所有历史包字节级不变（且离线验签仍通过）。
        for pkg in service.get_sealed_packages(scope):
            if pkg.version in snapshots:
                mh, ph, ser = snapshots[pkg.version]
                assert pkg.manifest.manifest_hash == mh, "P24 违反：历史 manifest_hash 改变"
                assert pkg.package_hash == ph, "P24 违反：历史 package_hash 改变"
                assert serialize_sealed_package(pkg) == ser, "P24 违反：历史包字节改变"
            else:
                snapshots[pkg.version] = (
                    pkg.manifest.manifest_hash,
                    pkg.package_hash,
                    serialize_sealed_package(pkg),
                )
            assert verify_package_offline(pkg) is True
            res = verifier.verify_package(serialize_sealed_package(pkg))
            assert res.status == VerificationStatus.PASSED and res.difference_count == 0

    # 最终恰有 N 个不可覆盖的历史版本。
    versions = sorted(p.version for p in service.get_sealed_packages(scope))
    assert versions == list(range(1, archive_count + 1))


# ═════════════════════════════════════════════════════════════════════════════
# P26 hold 三类操作无绕过（纯谓词 / 闭包层）
# ═════════════════════════════════════════════════════════════════════════════

# 任意 actor token（含七个系统角色 + service + 编造的“紧急/管理”角色）。
_ANY_ACTOR = st.sampled_from(
    list(SYSTEM_ROLES) + [SERVICE_IDENTITY, "emergency", "superadmin", "break_glass", ""]
)
_PROTECTED_OPS = st.sampled_from(sorted(LEGAL_HOLD_PROTECTED_OPERATIONS))


@given(actor=_ANY_ACTOR, op=_PROTECTED_OPS)
def test_p26_no_actor_can_bypass_hold_for_protected_ops(actor, op):
    """P26：hold 生效时 delete/purge/overwrite 对 **任何** actor（角色/admin/service/
    紧急授权）恒零效果——真实 ``legal_hold_permits`` 对受保护操作恒 False。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26
    """
    assert legal_hold_permits(actor, op) is False, "P26 违反：存在绕过 hold 的授权级别"


@given(actor=_ANY_ACTOR, op=st.sampled_from(["replace", "add_version", "read", "annotate"]))
def test_p26_non_destructive_ops_out_of_hold_zero_effect_scope(actor, op):
    """P26：内容替换（新增版本）等非破坏性操作不在 hold 零效果保护范围内（恒放行）——
    这与“替换只能新增版本、不覆盖历史”一致（覆盖 = overwrite 属受保护，已在上条证明）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26
    """
    assert legal_hold_permits(actor, op) is True


@st.composite
def _closure_case(draw):
    """生成 seed 节点 + 一条链式图，返回 (graph, seed_keys)。"""
    n = draw(st.integers(min_value=1, max_value=5))
    ids = [f"n{i}" for i in range(n)]
    graph = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
    # 生成链 n0->n1->...->n(k) 的随机前缀边，构造可达闭包。
    for i in range(n - 1):
        if draw(st.booleans()):
            graph.add_edge(_edge("node", ids[i], "node", ids[i + 1]))
    seed = [normalize_node_key("node", ids[0])]
    return graph, seed, ids


@given(case=_closure_case())
def test_p26_hold_closure_covers_transitive_downstream(case):
    """P26：hold 冻结闭包 = seed direct + 全部传递下游（真实 ``freeze_hold_closure``
    复用 UnifiedGraph BFS，无深度截断）；direct 与 transitive 不相交。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26
    """
    graph, seed, _ids = case
    closure = freeze_hold_closure(graph, seed)
    # direct 恰为 seed；transitive 恰为 seed 的下游闭包（不含 seed 自身）。
    assert closure.direct == frozenset(seed)
    expected_transitive = set()
    for s in seed:
        expected_transitive |= graph.downstream_closure(s)
    expected_transitive -= set(seed)
    assert closure.transitive == frozenset(expected_transitive)
    assert closure.direct.isdisjoint(closure.transitive)


@given(case=_closure_case(), new_tgt=st.integers(min_value=90, max_value=95))
def test_p26_new_edge_protection_is_monotonic(case, new_tgt):
    """P26：hold 内新增边——若 source 已在保护集则 target+下游被单调纳入；否则零新增。
    保护范围只增不减、不虚增（真实 ``compute_new_edge_additions``）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26
    """
    graph, seed, _ids = case
    protected = freeze_hold_closure(graph, seed).all_keys
    tgt_key = normalize_node_key("node", f"n{new_tgt}")
    src_in = next(iter(protected))
    src_out = normalize_node_key("node", "OUTSIDE")

    # source 在保护集 → 至少纳入新 target（若其尚未被保护）。
    e_in = _edge("node", src_in.split(":", 1)[1], "node", f"n{new_tgt}")
    add_in = compute_new_edge_additions(protected, graph, e_in)
    if tgt_key not in protected:
        assert tgt_key in add_in
    assert add_in.isdisjoint(protected)  # 只返回“新增”，不含已保护

    # source 不在保护集 → 零新增（不虚增保护范围）。
    e_out = _edge("node", "OUTSIDE", "node", f"n{new_tgt}")
    assert compute_new_edge_additions(protected, graph, e_out) == frozenset()
    assert src_out not in protected


# ═════════════════════════════════════════════════════════════════════════════
# P27 保留期边界（纯真值 PBT）— purge 仅在四条件全满足时 delta=1；任一不满足 delta=0。
# ═════════════════════════════════════════════════════════════════════════════


@given(
    hold_released=st.booleans(),
    retention_expired=st.booleans(),
    has_purge_capability=st.booleans(),
    no_dangling_active_ref=st.booleans(),
)
def test_p27_purge_allowed_iff_all_four_conditions(
    hold_released, retention_expired, has_purge_capability, no_dangling_active_ref
):
    """P27：purge 授权 ⇔ 四条件全满足；任一不满足 ⇒ allowed=False, delta=0，且 unmet
    携带对应稳定原因码（真实 ``evaluate_purge_conditions``）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 27
    """
    conds = PurgeConditions(
        hold_released=hold_released,
        retention_expired=retention_expired,
        has_purge_capability=has_purge_capability,
        no_dangling_active_ref=no_dangling_active_ref,
    )
    decision = evaluate_purge_conditions(conds)
    assert isinstance(decision, PurgeDecision)
    all_met = hold_released and retention_expired and has_purge_capability and no_dangling_active_ref
    assert decision.allowed is all_met
    assert decision.delta == (1 if all_met else 0)

    expected_unmet = set()
    if not hold_released:
        expected_unmet.add(PURGE_UNMET_HOLD_ACTIVE)
    if not retention_expired:
        expected_unmet.add(PURGE_UNMET_RETENTION)
    if not has_purge_capability:
        expected_unmet.add(PURGE_UNMET_CAPABILITY)
    if not no_dangling_active_ref:
        expected_unmet.add(PURGE_UNMET_DANGLING_REF)
    assert set(decision.unmet) == expected_unmet


@given(role=st.sampled_from(list(SYSTEM_ROLES)))
def test_p27_service_identity_never_has_purge_capability(role):
    """P27：Service Identity 永不具 ``retention.purge``；service actor 强制走 service 行。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 27
    """
    # service actor 覆盖任何传入 role → 恒无 purge 能力。
    svc_actor = ActorContext.for_service(uuid.uuid4())
    assert subject_has_purge_capability(role, actor=svc_actor) is False
    # SERVICE_IDENTITY token 亦然。
    assert subject_has_purge_capability(SERVICE_IDENTITY) is False


# ═════════════════════════════════════════════════════════════════════════════
# P25 command-root 唯一 / transition 多条（纯脱敏 + 真实 PG16）
# ═════════════════════════════════════════════════════════════════════════════


@given(
    secret=st.text(min_size=1, max_size=20),
    abspath=st.sampled_from(["/srv/secret/a.pdf", "C:/evidence/x.xlsx", r"\\host\share\y"]),
    raw=st.text(min_size=1, max_size=40),
    safe_val=st.text(min_size=0, max_size=20),
)
def test_p25_redaction_strips_credentials_paths_and_raw_text(secret, abspath, raw, safe_val):
    """P25：审计事件脱敏后不含凭据 / 附件原文 / 绝对路径（真实 ``redact_audit_metadata``）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25
    """
    meta = {
        "password": secret,
        "api_key": secret,
        "authorization": secret,
        "file_path": abspath,
        "raw_text": raw,
        "prompt": raw,
        "nested": {"secret": secret, "abs_path": abspath},
        "trace_id": safe_val,  # 非敏感键保留
    }
    out = redact_audit_metadata(meta)
    for k in ("password", "api_key", "authorization", "file_path", "raw_text", "prompt"):
        assert out[k] == "[redacted]", f"P25 违反：敏感键 {k} 未脱敏"
    assert out["nested"]["secret"] == "[redacted]"
    assert out["nested"]["abs_path"] == "[redacted]"
    # 非敏感键（trace_id）保留（仅超长截断）。
    assert out["trace_id"] == (safe_val if len(safe_val) <= 200 else safe_val[:200] + "…")


# ─── 真实 PostgreSQL 16（throwaway 库；非 PG 环境 skip）─────────────────────────

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
_V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
_V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
_V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"
_V111 = MIGRATIONS_DIR / "V111__evidence_governance_tombstones.sql"


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
    tmp_db = f"evgov_p95_{uuid.uuid4().hex[:12]}"

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
        for f in (_V106, _V107, _V108, _V111):
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


async def _seed(eng) -> dict:
    from sqlalchemy import text as T

    ids = {"user": uuid.uuid4(), "project": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"), {"i": ids["project"]}
        )
    return ids


@pytest.mark.asyncio
@given(
    command_type=st.sampled_from(["archive.finalize", "attachment.replace", "ocr.confirm",
                                  "legal_hold.activate", "retention.purge"]),
    idem_key=st.uuids(),
    transition_count=st.integers(min_value=0, max_value=4),
    replay_count=st.integers(min_value=1, max_value=3),
)
@settings(
    max_examples=2,  # 真实 throwaway PG16 建库/迁移较重：显式收敛（env 可下探至 1）
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_p25_command_root_unique_and_transitions_zero_to_many(
    command_type, idem_key, transition_count, replay_count
):
    """P25（真实 PG16）：对同一 (command_type, idempotency_key, scope)，执行 + 任意次重放
    恰只建 **一个** command-root（``uq_audit_command_root`` + upsert 幂等）；可关联零到多条
    transition，均 FK 到同一 root，且脱敏元数据无凭据 / 原文。

    exercises 真实 ``CommandAuditService.upsert_command_root`` / ``record_transition``
    + 真实 ``evidence_audit_command_roots`` UNIQUE 约束。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    import sqlalchemy as sa

    async with _throwaway_engine() as eng:
        ids = await _seed(eng)
        SM = _sessionmaker(eng)
        actor = ActorContext.for_user(ids["user"])
        idem = str(idem_key)

        async with SM() as session:
            svc = CommandAuditService(session)

            # 首次执行：created=True，且恰建一个 root。
            root, created = await svc.upsert_command_root(
                command_type=command_type, idempotency_key=idem,
                project_id=ids["project"], audit_year=2025, actor=actor,
            )
            await session.commit()
            assert created is True
            root_id = root.id

            # 任意次重放：created=False，且不多建 root（返回同一 root）。
            for _ in range(replay_count):
                r2, created2 = await svc.upsert_command_root(
                    command_type=command_type, idempotency_key=idem,
                    project_id=ids["project"], audit_year=2025, actor=actor,
                )
                await session.commit()
                assert created2 is False
                assert r2.id == root_id, "P25 违反：重放创建了重复 command-root"

            # 零到多条 transition，全部 FK 到同一 root + 脱敏。
            for i in range(transition_count):
                await svc.record_transition(
                    command_root_id=root_id,
                    transition_type=f"step-{i}",
                    actor=actor,
                    from_state="queued", to_state="running",
                    metadata={"password": "s3cr3t", "file_path": "/srv/x", "note": "ok"},
                )
            await session.commit()

        async with SM() as s2:
            # 恰有一个 root。
            n_root = (await s2.execute(sa.text(
                "SELECT count(*) FROM evidence_audit_command_roots "
                "WHERE command_type=:ct AND idempotency_key=:ik "
                "AND project_id=:pid AND audit_year=2025"
            ), {"ct": command_type, "ik": idem, "pid": str(ids["project"])})).scalar()
            assert n_root == 1, f"P25 违反：command-root 数 = {n_root}（应为 1）"

            # transition 数恰为生成值（零到多），且全部关联该 root。
            n_tr = (await s2.execute(sa.text(
                "SELECT count(*) FROM evidence_audit_transitions WHERE command_root_id=:rid"
            ), {"rid": str(root_id)})).scalar()
            assert n_tr == transition_count

            # 脱敏落库：无凭据 / 绝对路径原文。
            if transition_count > 0:
                metas = (await s2.execute(sa.text(
                    "SELECT metadata_redacted FROM evidence_audit_transitions "
                    "WHERE command_root_id=:rid"
                ), {"rid": str(root_id)})).scalars().all()
                for m in metas:
                    assert m["password"] == "[redacted]"
                    assert m["file_path"] == "[redacted]"


@pytest.mark.asyncio
@given(versions=st.integers(min_value=2, max_value=4))
@settings(
    max_examples=2,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_p24_pg_version_unique_and_sealed_immutable(versions):
    """P24（真实 PG16）：``archive_manifests`` (project, year, version_no) 唯一——重复
    version 被拒（历史不覆盖）；sealed 后 UPDATE 被不可变触发器拒绝（字节冻结）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 24
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    import sqlalchemy as sa

    async with _throwaway_engine() as eng:
        ids = await _seed(eng)

        async def _insert(vn: int, state: str = "building", ph=None):
            mid = uuid.uuid4()
            async with eng.begin() as conn:
                await conn.execute(sa.text(
                    "INSERT INTO archive_manifests "
                    "(id, project_id, audit_year, version_no, watermark, package_hash, state, "
                    " actor_type, actor_user_id) "
                    "VALUES (:id, :pid, 2025, :vn, :wm, :ph, :st, 'user', :uid)"
                ), {"id": mid, "pid": str(ids["project"]), "vn": vn,
                    "wm": "w" * 64, "ph": ph, "st": state, "uid": str(ids["user"])})
            return mid

        # 递增版本插入成功（历史保留）。
        first = await _insert(1)
        for vn in range(2, versions + 1):
            await _insert(vn)

        # 重复版本被唯一约束拒绝（不覆盖历史）。
        with pytest.raises(Exception):
            await _insert(1)

        # building → sealed 允许；sealed 后 UPDATE 被触发器拒绝。
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                f"UPDATE archive_manifests SET state='sealed', package_hash='{'a'*64}', "
                f"sealed_at=now() WHERE id='{first}'"
            )
        with pytest.raises(Exception):
            async with eng.begin() as conn:
                await conn.exec_driver_sql(
                    f"UPDATE archive_manifests SET package_hash='{'b'*64}' WHERE id='{first}'"
                )

        async with eng.connect() as conn:
            all_versions = (await conn.execute(sa.text(
                "SELECT version_no FROM archive_manifests WHERE project_id=:p ORDER BY version_no"
            ), {"p": str(ids["project"])})).scalars().all()
            sealed = (await conn.execute(sa.text(
                "SELECT state, package_hash FROM archive_manifests WHERE id=:i"
            ), {"i": first})).mappings().first()
        assert all_versions == list(range(1, versions + 1))
        assert sealed["state"] == "sealed" and sealed["package_hash"] == "a" * 64
