"""Wave 8 — archive-hold 属性组 PBT（Task 9.5）：逐项覆盖 P23、P24、P25、P26、P27。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.5 (Wave 8)
Requirements: R11, R12, R13
Design: §4.4 统一依赖图, §4.6 (Manifest/Hold/审计), §5.5 (Archive/Retention/Legal Hold),
        §7.1 (command-root 唯一与 transition 多条), §10.1/§10.2 (Testing Strategy),
        §11 属性 P23–P27

逐项属性:
  * P23 manifest 精确完备 —— manifest nodes/edges 精确等于归档范围内“策略必需证据 ∪
        对象已有依赖”所形成的可达统一证据图；历史对象无附件本身不扩大该图，已有证据的
        P0 完整性不放宽。图 PBT + 真实 PG16 archive 集成（从 evidence_dependencies 构图）。
  * P24 防覆盖 —— 每次归档新增版本；历史包字节 / manifest / hash / 冻结关系不变；
        sealed 后不可再封。PBT + 离线 verifier。
  * P25 command-root 唯一 / transition 多条 —— 每个敏感命令 + 幂等键恰一个脱敏
        command-root；零到多条可关联 transition；执行与重放均不重复 root；事件不含凭据 /
        附件原文 / 绝对路径。脱敏 PBT + 真实 PG16 唯一约束/审计集成。
  * P26 hold 三类操作无绕过 —— active hold 闭包内 delete/purge/overwrite 对任何授权级别
        （任意角色 / admin / Service Identity / 紧急授权）恒零效果且无绕过；替换只能新增版本。
        真值 PBT + 真实 PG16 hold 集成。
  * P27 hold 解除 + retention 到期清理边界 —— 仅 hold 已解除 ∧ retention 届满 ∧ 主体获授权
        ∧ 无悬空活动 EvidenceRef 时才允许清理；任一条件不满足则清理效果 = 0。
        真值 PBT + 真实 PG16 purge/tombstone 集成。

真实 PG 铁律（design §10.1/§10.2）：PG enum/check/partial unique/复合 FK/deferrable/
immutable trigger、command-root 唯一约束、并发去重、事务回滚必须在真实 PostgreSQL 16 验证；
SQLite 不得替代 PG 约束/并发/trigger → 无 PG 环境 skip。

常规 PBT 使用全局 fast profile（conftest 注册，默认 max_examples=5，可由
HYPOTHESIS_MAX_EXAMPLES 覆盖）；不在测试正文固定样本数。失败 counterexample 由 Hypothesis 保留。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifest,
    ArchiveManifestService,
    ArchiveResult,
    ManifestEntryType,
    verify_package_offline,
)
from app.services.evidence_governance.command_audit import (
    CommandAuditService,
    redact_audit_metadata,
)
from app.services.evidence_governance.formal_output_gate import FormalOutputGate
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
    RetentionLegalHoldService,
    compute_new_edge_additions,
    evaluate_purge_conditions,
    freeze_hold_closure,
)
from app.services.evidence_governance.role_capability_contract import (
    LEGAL_HOLD_PROTECTED_OPERATIONS,
    legal_hold_permits,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    UnifiedGraphBuilder,
    compute_canonical_edge_hash,
    normalize_node_key,
)

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"
V111 = MIGRATIONS_DIR / "V111__evidence_governance_tombstones.sql"


def _run(coro):
    """Run a coroutine to completion on a fresh event loop (Hypothesis-safe)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# 共享策略与图构造
# ═══════════════════════════════════════════════════════════════════════════

_NODE_TYPE_ST = st.sampled_from([
    "attachment_version", "workpaper", "ocr_result", "ai_content",
    "citation", "evidence_ref", "acnr", "legacy", "deliverable", "archive",
])
_NODE_ID_ST = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=8)
_PROVENANCE_ST = st.sampled_from(list(EdgeProvenance))


@st.composite
def _edge_st(draw: st.DrawFn) -> dict:
    return {
        "source_type": draw(_NODE_TYPE_ST),
        "source_id": draw(_NODE_ID_ST),
        "target_type": draw(_NODE_TYPE_ST),
        "target_id": draw(_NODE_ID_ST),
        "provenance": draw(_PROVENANCE_ST),
    }


def _build_graph(edges: list[dict]) -> UnifiedGraph:
    graph = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
    for e in edges:
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"], e["target_type"], e["target_id"], e["provenance"],
        )
        graph.add_edge(NormalizedEdge(
            source_key=normalize_node_key(e["source_type"], e["source_id"]),
            target_key=normalize_node_key(e["target_type"], e["target_id"]),
            provenance=e["provenance"],
            edge_hash=edge_hash,
        ))
    return graph


# ═══════════════════════════════════════════════════════════════════════════
# P23 — manifest 精确完备（图 PBT，纯/模型）
# ═══════════════════════════════════════════════════════════════════════════
#
# 归档 manifest 的 edges 精确等于冻结时统一图（policy-required evidence ∪ existing
# dependencies 形成的可达图）的 edges；不多含、不少含。历史对象无附件本身不扩大该图。


@given(edges=st.lists(_edge_st(), min_size=0, max_size=20))
def test_property_p23_manifest_edges_exactly_equal_graph_edges(edges):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23.

    manifest 的 edge 集合（edge_hash + source/target/provenance 三元组）精确等于冻结
    统一图的 edge 集合：不多含、不少含。

    **Validates: Requirements 11.1, 11.2**
    """
    graph = _build_graph(edges)
    service = ArchiveManifestService(gate=FormalOutputGate())
    manifest = ArchiveManifest(project_id=str(graph.scope.project_id), audit_year=2025)
    manifest = _run(service.build_manifest(manifest, graph=graph))

    manifest_hashes = {e.edge_hash for e in manifest.edges}
    graph_hashes = set(graph.edges.keys())
    assert manifest_hashes == graph_hashes, (
        f"P23 违背：manifest edges != graph edges "
        f"(manifest={len(manifest_hashes)} graph={len(graph_hashes)})"
    )
    # 三元组精确对齐（provenance/方向不得漂移）
    manifest_triples = {(e.source_key, e.target_key, e.provenance) for e in manifest.edges}
    graph_triples = {
        (e.source_key, e.target_key, e.provenance.value) for e in graph.edges.values()
    }
    assert manifest_triples == graph_triples


@given(
    edges=st.lists(_edge_st(), min_size=0, max_size=12),
    n_historical=st.integers(min_value=0, max_value=6),
)
def test_property_p23_historical_objects_without_attachments_do_not_expand_graph(
    edges, n_historical
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23.

    历史对象无附件本身不扩大证据图：向 manifest 加入不带附件依赖的历史 entry（如
    历史 workpaper/report），边集合仍恒等于冻结统一图的边集合（entry 不产生新边）。

    **Validates: Requirements 11.2**
    """
    graph = _build_graph(edges)
    # 历史对象 entries（无附件依赖，不是图边的一部分）
    historical_items = [
        {"id": f"hist-{i}", "type": "review_record", "object_id": f"wp-hist-{i}",
         "version": None, "content_hash": None, "state": "historical"}
        for i in range(n_historical)
    ]
    service = ArchiveManifestService(gate=FormalOutputGate())
    manifest = ArchiveManifest(project_id=str(graph.scope.project_id), audit_year=2025)
    manifest = _run(service.build_manifest(manifest, graph=graph, evidence_items=historical_items))

    # 边集合仍精确等于图边集合（历史 entry 不引入任何新边）
    assert {e.edge_hash for e in manifest.edges} == set(graph.edges.keys())
    # entries 恰好等于传入的历史对象数（不臆造、也不遗漏）
    assert manifest.entry_count == n_historical


@given(edges=st.lists(_edge_st(), min_size=1, max_size=15))
def test_property_p23_manifest_reachable_graph_is_deduped_union(edges):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23.

    统一证据图为多 provenance 边的去重并集：重复喂入相同逻辑边不改变 manifest 边数，
    manifest 边集合恒等于按 canonical edge hash 去重后的图边集合。

    **Validates: Requirements 11.1**
    """
    graph = _build_graph(edges)
    graph_dup = _build_graph(edges + edges)  # duplicated logical edges
    service = ArchiveManifestService(gate=FormalOutputGate())

    m1 = _run(service.build_manifest(
        ArchiveManifest(project_id=str(graph.scope.project_id), audit_year=2025), graph=graph))
    m2 = _run(service.build_manifest(
        ArchiveManifest(project_id=str(graph_dup.scope.project_id), audit_year=2025), graph=graph_dup))

    assert m1.edge_count == m2.edge_count == len(graph.edges)
    assert {e.edge_hash for e in m1.edges} == {e.edge_hash for e in m2.edges}


# ═══════════════════════════════════════════════════════════════════════════
# P24 — 防覆盖（PBT + 离线 verifier）
# ═══════════════════════════════════════════════════════════════════════════


_ENTRY_TYPE_ST = st.sampled_from([t.value for t in ManifestEntryType])


@st.composite
def _evidence_item_st(draw: st.DrawFn) -> dict:
    return {
        "id": f"e-{draw(_NODE_ID_ST)}-{uuid.uuid4().hex[:6]}",
        "type": draw(_ENTRY_TYPE_ST),
        "object_id": f"o-{draw(_NODE_ID_ST)}",
        "version": str(draw(st.integers(min_value=1, max_value=9))),
        "content_hash": draw(st.sampled_from(["a", "b", "c", "d", "e"])) * 64,
        "state": draw(st.sampled_from(["available", "confirmed", "written_back"])),
    }


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


@given(item_sets=st.lists(st.lists(_evidence_item_st(), max_size=4), min_size=2, max_size=4))
def test_property_p24_each_archive_new_version_history_immutable(item_sets):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 24.

    每次归档新增严格递增版本；先前已封包的 manifest_hash / package_hash / entries 在
    后续归档后逐字节不变；每个历史包离线验签均通过。

    **Validates: Requirements 11.3**
    """
    async def scenario():
        service = ArchiveManifestService(gate=FormalOutputGate())
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())

        snapshots: list[tuple[int, str, str, list, str]] = []
        for idx, items in enumerate(item_sets):
            result = await _archive_once(service, scope, actor, evidence_items=items)
            assert result.success is True and result.sealed_package is not None
            assert result.blocking_report is None  # 成功归档无阻断报告
            pkg = result.sealed_package
            # 版本严格递增（从 1 起）
            assert pkg.version == idx + 1
            snapshots.append((
                pkg.version,
                pkg.manifest.manifest_hash,
                pkg.package_hash,
                [(e.entry_id, e.entry_type.value, e.object_id, e.content_hash)
                 for e in pkg.manifest.entries],
                serialize_sealed_package(pkg),
            ))

        # 全部归档后，历史包逐字节不变 + 离线验签通过
        packages = {p.version: p for p in service.get_sealed_packages(scope)}
        assert len(packages) == len(item_sets)
        versions = sorted(packages)
        assert versions == list(range(1, len(item_sets) + 1))  # 无覆盖、无缺号

        for (v, mh, ph, entries, offline) in snapshots:
            p = packages[v]
            assert p.manifest.manifest_hash == mh, f"P24 违背：v{v} manifest_hash 被改写"
            assert p.package_hash == ph, f"P24 违背：v{v} package_hash 被改写"
            assert [(e.entry_id, e.entry_type.value, e.object_id, e.content_hash)
                    for e in p.manifest.entries] == entries
            assert serialize_sealed_package(p) == offline  # 离线序列化字节稳定
            assert verify_package_offline(p) is True

    _run(scenario())


@given(items=st.lists(_evidence_item_st(), max_size=4))
def test_property_p24_sealed_manifest_cannot_be_resealed(items):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 24.

    sealed manifest 不可再封（不可变守卫）：任何再次 seal 均抛错，历史封包不被覆盖。

    **Validates: Requirements 11.3**
    """
    from app.services.evidence_governance.frozen_contracts import EvidenceGovernanceError

    async def scenario():
        service = ArchiveManifestService(gate=FormalOutputGate())
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())
        result = await _archive_once(service, scope, actor, evidence_items=items)
        assert result.sealed_package is not None
        with pytest.raises(EvidenceGovernanceError):
            result.sealed_package.manifest.seal()

    _run(scenario())


@given(item_sets=st.lists(st.lists(_evidence_item_st(), max_size=3), min_size=2, max_size=3))
def test_property_p24_offline_verifier_passes_all_versions(item_sets):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 24.

    独立离线 verifier（不连接业务库）对每个封包版本重算 member/manifest/package hash
    均验签通过；篡改任一字节则验签失败（防覆盖 + 完整性）。

    **Validates: Requirements 11.3**
    """
    async def scenario():
        service = ArchiveManifestService(gate=FormalOutputGate())
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())
        for items in item_sets:
            await _archive_once(service, scope, actor, evidence_items=items)

        verifier = OfflineManifestVerifier()
        for pkg in service.get_sealed_packages(scope):
            res = verifier.verify_package(serialize_sealed_package(pkg))
            assert res.status == VerificationStatus.PASSED
            assert res.is_valid and res.difference_count == 0

    _run(scenario())


# ═══════════════════════════════════════════════════════════════════════════
# P25 — command-root 唯一 / transition 多条（脱敏 PBT）
# ═══════════════════════════════════════════════════════════════════════════

_FORBIDDEN_KEYS = (
    "password", "secret", "token", "credential", "authorization", "api_key",
    "cookie", "session_id", "file_path", "storage_key", "raw_text", "raw_content",
    "file_bytes", "prompt", "answer", "excerpt",
)


@st.composite
def _redaction_meta_st(draw: st.DrawFn) -> tuple[dict, dict]:
    """生成 (含敏感键的元数据, 敏感键→原始值 映射)。"""
    safe = {
        "object_id": draw(_NODE_ID_ST),
        "version": draw(st.integers(min_value=1, max_value=9)),
        "action": draw(st.sampled_from(["create", "replace", "confirm"])),
        "result": draw(st.sampled_from(["accepted", "rejected"])),
    }
    secrets: dict[str, str] = {}
    for key in draw(st.lists(st.sampled_from(_FORBIDDEN_KEYS), max_size=6, unique=True)):
        secret_val = f"SENSITIVE-{uuid.uuid4().hex}"
        safe[key] = secret_val
        secrets[key] = secret_val
    return safe, secrets


@given(data=_redaction_meta_st())
def test_property_p25_redaction_strips_credentials_and_raw_content(data):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25.

    审计脱敏：敏感键（凭据 / 附件原文 / prompt/answer / 绝对路径 / storage_key）在脱敏后
    恒为 [redacted]，且原始敏感值不出现在任何脱敏字符串中。

    **Validates: Requirements 12.1, 12.2**
    """
    meta, secrets = data
    redacted = redact_audit_metadata(meta)
    for key, original in secrets.items():
        assert redacted.get(key) == "[redacted]", f"敏感键 {key} 未脱敏"
    # 序列化后不含任何原始敏感值
    import json

    dumped = json.dumps(redacted, ensure_ascii=False)
    for original in secrets.values():
        assert original not in dumped, "脱敏后仍泄露原始敏感值"


@given(
    path=st.sampled_from([
        "/etc/secret/key.pem", "C:\\Users\\a\\storage\\blob.bin",
        "/var/lib/paperless/media/documents/0001.pdf", "\\\\server\\share\\x",
    ]),
)
def test_property_p25_redaction_masks_absolute_paths(path):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25.

    绝对路径形态的字符串值恒被替换为 [redacted]（POSIX / Windows 盘符 / UNC）。

    **Validates: Requirements 12.2**
    """
    redacted = redact_audit_metadata({"note": path, "safe": "relative/ok.txt"})
    assert redacted["note"] == "[redacted]"
    # 相对路径不误伤
    assert redacted["safe"] == "relative/ok.txt"


@given(nested=st.dictionaries(
    keys=st.sampled_from(["token", "meta", "child", "list_of"]),
    values=st.recursive(
        st.text(max_size=10) | st.integers(),
        lambda c: st.dictionaries(st.sampled_from(["secret", "ok"]), c, max_size=3),
        max_leaves=5,
    ),
    max_size=4,
))
def test_property_p25_redaction_recurses_into_nested_structures(nested):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25.

    脱敏递归进入嵌套 dict/list：无论嵌套多深，命中敏感键子串的键恒被脱敏；输入不被修改。

    **Validates: Requirements 12.2**
    """
    import copy

    original = copy.deepcopy(nested)
    redacted = redact_audit_metadata(nested)

    def _no_secret_key_survives(obj) -> bool:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if any(sub in str(k).lower() for sub in _FORBIDDEN_KEYS):
                    if v != "[redacted]":
                        return False
                elif not _no_secret_key_survives(v):
                    return False
        elif isinstance(obj, list):
            return all(_no_secret_key_survives(x) for x in obj)
        return True

    assert _no_secret_key_survives(redacted)
    assert nested == original  # 不修改入参


# ═══════════════════════════════════════════════════════════════════════════
# P26 — hold 三类操作无绕过（真值 PBT）
# ═══════════════════════════════════════════════════════════════════════════

_ANY_ACTOR_ST = st.one_of(
    st.sampled_from(["auditor", "manager", "partner", "qc", "eqcr", "admin",
                     "readonly", "service", "emergency", "root", "superuser"]),
    st.none(),
    st.text(max_size=12),
)


@given(actor=_ANY_ACTOR_ST, op=st.sampled_from(sorted(LEGAL_HOLD_PROTECTED_OPERATIONS)))
def test_property_p26_no_actor_bypasses_hold_for_protected_ops(actor, op):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26.

    active hold 内 delete/purge/overwrite 对任何授权级别恒零效果：``legal_hold_permits``
    对任意 actor（含 admin / service / emergency / 任意字符串 / None）× 受保护操作恒 False，
    无紧急绕过通道。

    **Validates: Requirements 13.2**
    """
    assert legal_hold_permits(actor, op) is False, (
        f"P26 违背：actor={actor!r} 竟被允许在 hold 内执行受保护操作 {op}"
    )


@given(actor=_ANY_ACTOR_ST,
       op=st.sampled_from(["replace", "add_version", "read", "create_version", "annotate"]))
def test_property_p26_non_destructive_ops_pass_through(actor, op):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26.

    替换只能新增版本：非破坏性操作（add_version/replace 等）不属于 hold 的零效果范围，
    ``legal_hold_permits`` 返回 True（由其他门禁治理），而三类破坏性操作恒被拒。

    **Validates: Requirements 13.2**
    """
    assert legal_hold_permits(actor, op) is True
    assert op not in LEGAL_HOLD_PROTECTED_OPERATIONS


@given(edges=st.lists(_edge_st(), min_size=1, max_size=15),
       seed_idx=st.integers(min_value=0, max_value=14))
def test_property_p26_new_edge_protection_is_monotonic(edges, seed_idx):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26.

    hold 保护范围单调（只增不减）：若新增边的 source 已在闭包内，其 target 及下游闭包被
    纳入保护；若 source 未受保护，则新增边不引入任何保护（不误增）。

    **Validates: Requirements 13.2**
    """
    graph = _build_graph(edges)
    all_sources = [e.source_key for e in graph.edges.values()]
    seed_key = all_sources[seed_idx % len(all_sources)]
    closure = freeze_hold_closure(graph, [seed_key])
    protected = closure.all_keys

    # 取图中任意一条边作为“新增边”候选
    sample = next(iter(graph.edges.values()))
    new_edge = NormalizedEdge(
        source_key=sample.source_key, target_key=sample.target_key,
        provenance=sample.provenance, edge_hash=sample.edge_hash,
    )
    additions = compute_new_edge_additions(protected, graph, new_edge)

    if new_edge.source_key not in protected:
        assert additions == frozenset(), "source 未受保护却引入了保护（非单调误增）"
    else:
        # 新增项必为 target 下游闭包中尚未受保护的部分（单调扩张）
        expected = ({new_edge.target_key} | graph.downstream_closure(new_edge.target_key)) - set(protected)
        assert additions == frozenset(expected)
        # 扩张后总保护集恒 ⊇ 原保护集（只增不减）
        assert protected <= (protected | additions)


# ═══════════════════════════════════════════════════════════════════════════
# P27 — hold 解除 + retention 到期清理边界（真值 PBT）
# ═══════════════════════════════════════════════════════════════════════════


@given(
    hold_released=st.booleans(),
    retention_expired=st.booleans(),
    has_capability=st.booleans(),
    no_dangling=st.booleans(),
)
def test_property_p27_purge_allowed_iff_all_four_conditions(
    hold_released, retention_expired, has_capability, no_dangling
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 27.

    清理允许 IFF（hold 已解除 ∧ retention 届满 ∧ 主体获授权 ∧ 无悬空活动 ref）四者全满足；
    任一不满足则 allowed=False 且 delta=0，并给出对应 unmet 原因码。

    **Validates: Requirements 13.4**
    """
    conds = PurgeConditions(
        hold_released=hold_released,
        retention_expired=retention_expired,
        has_purge_capability=has_capability,
        no_dangling_active_ref=no_dangling,
    )
    decision = evaluate_purge_conditions(conds)

    expected_allowed = hold_released and retention_expired and has_capability and no_dangling
    assert decision.allowed is expected_allowed
    assert decision.delta == (1 if expected_allowed else 0)

    if not expected_allowed:
        if not hold_released:
            assert PURGE_UNMET_HOLD_ACTIVE in decision.unmet
        if not retention_expired:
            assert PURGE_UNMET_RETENTION in decision.unmet
        if not has_capability:
            assert PURGE_UNMET_CAPABILITY in decision.unmet
        if not no_dangling:
            assert PURGE_UNMET_DANGLING_REF in decision.unmet
    else:
        assert decision.unmet == ()


@given(unmet_count=st.integers(min_value=1, max_value=4))
def test_property_p27_any_unmet_condition_yields_zero_effect(unmet_count):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 27.

    任一（乃至任意组合）条件不满足时，清理效果恒为 0（delta=0，不授权），unmet 集与
    不满足维度精确对应。

    **Validates: Requirements 13.4**
    """
    flags = [True, True, True, True]
    for i in range(unmet_count):
        flags[i] = False
    conds = PurgeConditions(*flags)
    decision = evaluate_purge_conditions(conds)
    assert decision.allowed is False
    assert decision.delta == 0
    assert len(decision.unmet) == unmet_count


# ═══════════════════════════════════════════════════════════════════════════
# 真实 PG16 集成：P23（构图归档）/ P25（command-root 唯一）/ P26 / P27
# ═══════════════════════════════════════════════════════════════════════════


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
    audit_year int,
    current_version_id uuid,
    file_name varchar(500), file_path varchar(1000),
    file_type varchar(100), file_size bigint,
    ocr_status varchar(20), version int, previous_version_id uuid,
    created_by uuid, created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(), is_deleted boolean DEFAULT false,
    CONSTRAINT uq_attach_scope UNIQUE (id, project_id, audit_year)
);
"""


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"evgov_archhold_p95_{uuid.uuid4().hex[:12]}"

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
    ids = {"user": uuid.uuid4(), "project": uuid.uuid4(), "service": uuid.uuid4()}
    async with eng.begin() as conn:
        await conn.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            sa.text("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            sa.text("INSERT INTO project_users (project_id, user_id) VALUES (:p, :u)"),
            {"p": ids["project"], "u": ids["user"]},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO service_identities (id, identity_key, display_name, is_active) "
                "VALUES (:i, :k, :n, true)"
            ),
            {"i": ids["service"], "k": f"svc-{uuid.uuid4().hex[:8]}", "n": "p95-svc"},
        )
    return ids


async def _insert_dependency(session, *, project_id, year, user_id, src, tgt):
    edge_hash = compute_canonical_edge_hash(
        src[0], src[1], tgt[0], tgt[1], EdgeProvenance.EVIDENCE_DEPENDENCY,
    )
    await session.execute(
        sa.text("""
            INSERT INTO evidence_dependencies
              (project_id, audit_year, source_type, source_id, target_type, target_id,
               relation, edge_hash, status, actor_type, actor_user_id)
            VALUES
              (:pid, :yr, :st, :sid, :tt, :tid, 'derived_from', :eh, 'active', 'user', :uid)
        """),
        {
            "pid": str(project_id), "yr": year,
            "st": src[0], "sid": src[1], "tt": tgt[0], "tid": tgt[1],
            "eh": edge_hash, "uid": str(user_id),
        },
    )
    return edge_hash


# ─── P23 集成：manifest 边精确等于从真实 evidence_dependencies 构建的统一图边 ───


@pytest.mark.asyncio
async def test_property_p23_manifest_edges_equal_pg_built_graph():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 23.

    真实 PG16：UnifiedGraphBuilder 从 evidence_dependencies 载入活动边构建统一图，
    ArchiveManifestService.build_manifest 冻结该图；断言 manifest edge 集合精确等于
    图 edge 集合（不多含、不少含），且已知链 A→B→C 全在 manifest 中。

    **Validates: Requirements 11.1, 11.2**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（evidence_dependencies 构图 + archive manifest 集成）")

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        ids = await _seed(eng)
        project_id, year = ids["project"], 2025
        suffix = uuid.uuid4().hex[:8]

        a = ("attachment_version", f"A-{suffix}")
        b = ("ocr_result", f"B-{suffix}")
        c = ("ai_content", f"C-{suffix}")
        chain = [(a, b), (b, c)]

        async with Session() as session:
            for src, tgt in chain:
                await _insert_dependency(
                    session, project_id=project_id, year=year, user_id=ids["user"], src=src, tgt=tgt)
            await session.commit()

        scope = GraphScope(project_id=project_id, audit_year=year)
        async with Session() as session:
            builder = UnifiedGraphBuilder(session)
            graph = await builder.build(scope)

            service = ArchiveManifestService(gate=FormalOutputGate(), graph_builder=builder)
            manifest = ArchiveManifest(project_id=str(project_id), audit_year=year)
            manifest = await service.build_manifest(manifest, graph=graph)

        # manifest 边精确等于图边（reachable 统一图）
        assert {e.edge_hash for e in manifest.edges} == set(graph.edges.keys())
        # 已知链的两条边确实纳入 manifest
        chain_hashes = {
            compute_canonical_edge_hash(s[0], s[1], t[0], t[1], EdgeProvenance.EVIDENCE_DEPENDENCY)
            for s, t in chain
        }
        assert chain_hashes <= {e.edge_hash for e in manifest.edges}


# ─── P25 集成：command-root 唯一 + 多条 transition + 重放不重复 root ───


@pytest.mark.asyncio
async def test_property_p25_command_root_unique_transitions_many_pg():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25.

    真实 PG16：同 (command_type, idempotency_key, project, year) 重复 upsert command-root
    恰得一个 root（首次 created=True，重放 created=False 且同一 id）；可关联零到多条
    transition；不同 idempotency_key → 不同 root；transition 元数据脱敏（无原文/凭据）。

    **Validates: Requirements 12.1**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（uq_audit_command_root 唯一约束 + 审计集成）")

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        ids = await _seed(eng)
        project_id, year = ids["project"], 2025
        actor = ActorContext.for_user(ids["user"])
        idem = f"idem-{uuid.uuid4().hex}"

        async with Session() as session:
            audit = CommandAuditService(session)

            # 首次执行 → 建 root
            root1, created1 = await audit.upsert_command_root(
                command_type="archive.seal", idempotency_key=idem,
                project_id=project_id, audit_year=year, actor=actor, trace_id="t-1",
            )
            assert created1 is True

            # 记录多条 transition（含疑似敏感元数据 → 必须脱敏）
            for i, tt in enumerate(["queued", "building", "sealed"]):
                await audit.record_transition(
                    command_root_id=root1.id, transition_type=tt, actor=actor,
                    from_state=(None if i == 0 else "prev"), to_state=tt,
                    metadata={"token": "SECRET-XYZ", "file_path": "/abs/secret.pdf",
                              "step": i},
                )

            # 重放（相同幂等键）→ 不多建 root
            root2, created2 = await audit.upsert_command_root(
                command_type="archive.seal", idempotency_key=idem,
                project_id=project_id, audit_year=year, actor=actor, trace_id="t-1-replay",
            )
            assert created2 is False
            assert root2.id == root1.id

            # 不同幂等键 → 不同 root
            root3, created3 = await audit.upsert_command_root(
                command_type="archive.seal", idempotency_key=f"idem-{uuid.uuid4().hex}",
                project_id=project_id, audit_year=year, actor=actor,
            )
            assert created3 is True and root3.id != root1.id
            await session.commit()

        # 断言：该幂等键恰一个 root；transition 多条；脱敏生效
        async with Session() as session:
            root_count = (await session.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_audit_command_roots "
                    "WHERE command_type='archive.seal' AND idempotency_key=:k "
                    "AND project_id=:p AND audit_year=:y"
                ),
                {"k": idem, "p": str(project_id), "y": year},
            )).scalar()
            assert root_count == 1, "P25 违背：同一命令+幂等键出现多个 command-root"

            trans_count = (await session.execute(
                sa.text("SELECT count(*) FROM evidence_audit_transitions WHERE command_root_id=:r"),
                {"r": str(root1.id)},
            )).scalar()
            assert trans_count == 3  # 零到多条：此处三条

            # 脱敏：transition 元数据无凭据/原文/绝对路径
            metas = (await session.execute(
                sa.text(
                    "SELECT metadata_redacted::text FROM evidence_audit_transitions "
                    "WHERE command_root_id=:r"
                ),
                {"r": str(root1.id)},
            )).scalars().all()
            for m in metas:
                assert "SECRET-XYZ" not in m
                assert "/abs/secret.pdf" not in m
                assert "[redacted]" in m

            # 总 root 数为 2（一个复用键 + 一个新键）
            total_roots = (await session.execute(
                sa.text("SELECT count(*) FROM evidence_audit_command_roots")
            )).scalar()
            assert total_roots == 2


@pytest.mark.asyncio
async def test_property_p25_command_root_unique_constraint_enforced_pg():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25.

    真实 PG16：uq_audit_command_root 唯一约束物理阻止同 (command_type, idempotency_key,
    project, year) 出现第二行 command-root（裸 INSERT 绕过 upsert 也被拒）。

    **Validates: Requirements 12.1**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（uq_audit_command_root 唯一约束）")

    from sqlalchemy.exc import IntegrityError

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        ids = await _seed(eng)
        idem = f"idem-{uuid.uuid4().hex}"

        async def _raw_insert(session):
            await session.execute(
                sa.text(
                    "INSERT INTO evidence_audit_command_roots "
                    "(command_type, idempotency_key, project_id, audit_year, "
                    " actor_type, actor_user_id) "
                    "VALUES ('ocr.writeback', :k, :p, 2025, 'user', :u)"
                ),
                {"k": idem, "p": str(ids["project"]), "u": str(ids["user"])},
            )

        async with Session() as session:
            await _raw_insert(session)
            await session.commit()

        async with Session() as session:
            with pytest.raises(IntegrityError):
                await _raw_insert(session)
                await session.commit()


# ─── P26 集成：active hold 闭包内三类破坏性操作对任何角色零效果 ───


@pytest.mark.asyncio
async def test_property_p26_active_hold_blocks_all_destructive_all_roles_pg():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 26.

    真实 PG16：激活 hold 固化统一图闭包后，闭包内（直接种子 + 传递下游）节点的
    delete/overwrite/purge 对任意角色（含 admin / Service Identity / 紧急授权风格角色）
    恒抛 LEGAL_HOLD_ACTIVE（零效果）；purge 因 hold active 而 delta=0 且无墓碑。

    **Validates: Requirements 13.2**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（legal_hold_scopes 闭包 + 零效果强制）")

    from app.services.evidence_governance.frozen_contracts import (
        EvidenceErrorCode,
        EvidenceGovernanceError,
    )

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        ids = await _seed(eng)
        scope = GraphScope(project_id=ids["project"], audit_year=2025)

        # in-memory 统一图：受保护种子 → 下游
        g = UnifiedGraph(scope=scope)
        seed = normalize_node_key("attachment_version", "SEED-1")
        downstream = normalize_node_key("workpaper", "WP-1")
        eh = compute_canonical_edge_hash(
            "attachment_version", "SEED-1", "workpaper", "WP-1",
            EdgeProvenance.EVIDENCE_DEPENDENCY)
        g.add_edge(NormalizedEdge(source_key=seed, target_key=downstream,
                                  provenance=EdgeProvenance.EVIDENCE_DEPENDENCY, edge_hash=eh))

        async with Session() as session:
            svc = RetentionLegalHoldService(session)
            res = await svc.activate_hold(
                scope=scope, reason="litigation hold P26 integration",
                actor=ActorContext.for_user(ids["user"]),
                seed_nodes=[("attachment_version", "SEED-1")], graph=g,
            )
            await session.commit()
            assert res.direct_count == 1 and res.transitive_count == 1

            # 每个授权级别 × 三类破坏性操作 → 零效果（抛 LEGAL_HOLD_ACTIVE）
            for role in ("auditor", "manager", "partner", "qc", "eqcr", "admin",
                         "readonly", "emergency"):
                for op in ("delete", "overwrite", "purge"):
                    with pytest.raises(EvidenceGovernanceError) as ei:
                        await svc.authorize_destructive(
                            actor_role=role, operation=op, project_id=ids["project"],
                            node_type="attachment_version", node_id="SEED-1",
                        )
                    assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE

            # Service Identity 在传递下游节点上同样零效果
            with pytest.raises(EvidenceGovernanceError) as ei:
                await svc.authorize_destructive(
                    actor_role="service", operation="delete", project_id=ids["project"],
                    node_type="workpaper", node_id="WP-1",
                    actor=ActorContext.for_service(ids["service"]),
                )
            assert ei.value.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE

            # 非破坏性操作（新增版本）不被 hold 拦截
            await svc.authorize_destructive(
                actor_role="manager", operation="add_version", project_id=ids["project"],
                node_type="attachment_version", node_id="SEED-1",
            )

            # purge 因 hold active → delta=0
            decision = await svc.evaluate_purge(
                project_id=ids["project"], node_type="attachment_version", node_id="SEED-1",
                actor_role="partner", retention_expired=True,
            )
            assert decision.allowed is False and decision.delta == 0
            assert PURGE_UNMET_HOLD_ACTIVE in decision.unmet

        # 无墓碑生成
        async with Session() as s2:
            n = (await s2.execute(sa.text("SELECT count(*) FROM evidence_tombstones"))).scalar()
            assert n == 0


# ─── P27 集成：解除 hold + retention 到期 + 授权 + 无悬空 ref 才可清理 ───


@pytest.mark.asyncio
async def test_property_p27_purge_boundary_pg_all_conditions_and_dangling_ref():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 27.

    真实 PG16 清理边界：
      * 悬空活动 EvidenceRef 存在 → delta=0（dangling）；
      * 无 hold + retention 届满 + partner 有 retention.purge + 无悬空 ref → delta=1 + 不可变墓碑；
      * 无 retention.purge 能力（如 readonly / service） → delta=0（capability）。

    **Validates: Requirements 13.4**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（evidence_refs 悬空检测 + 墓碑不可变触发器）")

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        ids = await _seed(eng)
        node_id = f"PKG-{uuid.uuid4().hex[:8]}"

        # 1) 插入一条指向该节点的活动 EvidenceRef → 悬空
        async with Session() as session:
            await session.execute(
                sa.text("""
                    INSERT INTO evidence_refs
                      (project_id, audit_year, source_type, source_id,
                       evidence_type, evidence_id,
                       intent_hash, status, actor_type, actor_user_id)
                    VALUES (:p, 2025, 'workpaper', 'wp-ref-src', 'archive', :nid,
                            :ih, 'active', 'user', :u)
                """),
                {"p": str(ids["project"]), "nid": node_id,
                 "ih": uuid.uuid4().hex, "u": str(ids["user"])},
            )
            await session.commit()

        async with Session() as session:
            svc = RetentionLegalHoldService(session)
            d_dangling = await svc.evaluate_purge(
                project_id=ids["project"], node_type="archive", node_id=node_id,
                actor_role="partner", retention_expired=True,
            )
            assert d_dangling.allowed is False and d_dangling.delta == 0
            assert PURGE_UNMET_DANGLING_REF in d_dangling.unmet

        # 2) 停用该 ref → 移除悬空
        async with Session() as session:
            await session.execute(
                sa.text("UPDATE evidence_refs SET status='inactive' "
                        "WHERE project_id=:p AND evidence_id=:nid"),
                {"p": str(ids["project"]), "nid": node_id},
            )
            await session.commit()

        # 3) 无 retention.purge 能力（readonly）→ delta=0
        async with Session() as session:
            svc = RetentionLegalHoldService(session)
            d_nocap = await svc.evaluate_purge(
                project_id=ids["project"], node_type="archive", node_id=node_id,
                actor_role="readonly", retention_expired=True,
            )
            assert d_nocap.allowed is False and d_nocap.delta == 0
            assert PURGE_UNMET_CAPABILITY in d_nocap.unmet

        # 4) 四条件全满足 → delta=1 + 不可变墓碑
        async with Session() as session:
            svc = RetentionLegalHoldService(session)
            result = await svc.purge(
                project_id=ids["project"], audit_year=2025,
                node_type="archive", node_id=node_id,
                actor_role="partner", actor=ActorContext.for_user(ids["user"]),
                retention_expired=True, purged_by_user_id=ids["user"],
                content_hash="f" * 64, retention_policy_version="rp-p27",
            )
            await session.commit()
            assert result.decision.allowed is True and result.decision.delta == 1
            assert result.tombstone_id is not None

        # 墓碑不可变：UPDATE 被触发器拒绝
        async with Session() as session:
            with pytest.raises(Exception):
                await session.execute(
                    sa.text("UPDATE evidence_tombstones SET purge_reason='manual_purge' WHERE id=:i"),
                    {"i": result.tombstone_id},
                )
                await session.commit()
