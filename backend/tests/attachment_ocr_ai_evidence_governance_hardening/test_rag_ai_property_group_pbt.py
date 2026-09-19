"""Feature: attachment-ocr-ai-evidence-governance-hardening

Wave 8 / Task 9.3 — RAG-AI **合并属性组** PBT（逐项覆盖 P15–P19）。

本文件是 Wave 8 的 **RAG / AI 专属属性组测试层**：把已在 Wave 5 落地的真实治理服务
（``citation_snapshot_service`` / ``ai_evidence_gate`` / ``formal_output_gate`` /
``check_ai_entry_coverage`` 扫描器）的不可协商不变量，以生成式输入逐项作为属性重新
证明。**不重新实现任何业务逻辑**——所有断言都调用真实服务的纯方法 / 过滤链 / 门禁
/ 扫描器；DB 交互用 test-double（与既有 ``test_citation_snapshot_service.py`` 同款
``patch(get_adapter)`` + 假会话）驱动真实过滤链，不伪造判定结果。

设计基线（design §10.1/§10.2）：
- 常规 PBT 用 ``backend/tests/conftest.py`` 全局 ``fast`` profile（默认 5 例，可用
  ``HYPOTHESIS_MAX_EXAMPLES`` 覆盖）；**测试正文不固定 max_examples**。
- 纯函数 / 门禁 / 状态谓词用内存 reference model；失败保留 Hypothesis 原始
  counterexample。

## 复用而非重复（引用既有等价测试）

- **P15 locatability 单例 / P16 can_read 单点**：已由
  ``tests/evidence_governance/test_citation_snapshot_service.py`` 以固定样例覆盖
  （``TestP15Locatability`` / ``TestP16PermissionNonExpansion``）。本文件用生成式输入
  驱动同一真实 ``CitationSnapshotService`` 过滤链，补齐属性层证明（P15 可复算摘录哈希 /
  P16 输出集 ⊆ 可访问集 的全链路子集不变量）。
- **P17/P19 门禁单例**：已由 ``tests/test_ai_evidence_gate.py``（mock DB）与
  ``formal_output_gate`` 单测覆盖固定样例；本文件以生成式证据集驱动真实
  ``FormalOutputGate.preflight`` 的 P0 校验与 RequiredEvidence 并集语义。
- **P18 compute_coverage_gap 单点**：已在 gate 单测出现；本文件补生成式代数律 + 用真实
  ``check_ai_entry_coverage`` 扫描器对**真实仓库**求 ``discovered − declared``（P18 的
  实际 CI 不变量）。

## 平台现状说明（诚实报告，非 fake-green）

设计 §4.6 的 ``ai_content_governance`` / ``ai_content_logs`` 物理表在当前库中**尚未迁移**
（information_schema 实测缺失；Wave 5 的 ``AIEvidenceGate`` 单测全部用 mock DB）。因此
P17/P19 的「AI 内容日志 PG 持久化」无法在真实 PG16 上运行——本文件不伪造该表的 PG 测试，
而是通过**设计核心门禁** ``FormalOutputGate``（纯内存，无 DB）逐项证明 P17/P19 的不变量：
仅人工确认 + hash 一致 + 证据非 stale 才可进入 FormalOutput；确认内容或任一依据变化即失效
阻断。``citation_snapshots`` / ``evidence_refs`` / ``service_identities`` 表存在，但
``create_citation_from_retrieval`` 依赖真实 adapter 解析真实目标行，PG 全链路 seeding 成本
过高且不属于本属性组核心；本文件用 test-double 会话驱动真实过滤链代码路径。

Requirements: R7, R8, R9
Properties: P15, P16, P17, P18, P19
"""

from __future__ import annotations

import asyncio
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    is_sha256_hex,
    sha256_hex,
)
from app.services.evidence_governance.citation_snapshot_service import (
    CitationSnapshotService,
    RetrievalCandidate,
)
from app.services.evidence_governance.ai_evidence_gate import (
    AI_ENTRY_REGISTRY,
    AIEvidenceGate,
    compute_coverage_gap,
)
from app.services.evidence_governance.formal_output_gate import (
    BlockReasonCode,
    EvidenceItem,
    FormalOutputGate,
    GateVerdict,
    PolicyProvider,
    UnifiedGraphProvider,
)


# ═════════════════════════════════════════════════════════════════════════════
# 共享 test-double：驱动真实 CitationSnapshotService 过滤链（不伪造判定）
# ═════════════════════════════════════════════════════════════════════════════


class _FakeResult:
    """最小 SQLAlchemy Result 替身：``.first()`` 与 ``.mappings().first()`` 均返回同一行。"""

    def __init__(self, row: dict | None) -> None:
        self._row = row

    def first(self):  # noqa: D401
        return self._row

    def mappings(self):  # noqa: D401
        return self

    def scalar(self):  # noqa: D401
        if self._row is None:
            return None
        return next(iter(self._row.values()))


class _FakeCitationSession:
    """test-double AsyncSession：只服务 CitationSnapshotService 需要的两类查询。

    - ``evidence_refs`` 搜索 → 返回一条 active ref 行（保证 filter 3 通过，把属性隔离到
      P15 可定位性 / P16 权限维度）。
    - ``citation_snapshots`` INSERT ... RETURNING → 返回 created_at。

    不返回任何伪造的 can_read / 可定位判定——那些由真实 ``_is_locatable`` 与被 patch 的
    真实 adapter 协议决定。
    """

    async def execute(self, stmt, params=None):  # noqa: D401
        sql = str(stmt)
        if "INSERT INTO citation_snapshots" in sql:
            from datetime import datetime, timezone

            return _FakeResult({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)})
        if "evidence_refs" in sql:
            return _FakeResult({"id": str(uuid.uuid4())})
        return _FakeResult(None)


class _FakeAdapter:
    """test-double typed adapter：resolve 恒同 scope（非 None）；can_read 由可访问集决定。

    can_read 只是查一个由测试构造的「actor 可访问 source_id 集合」——这正是真实 adapter
    在 DB 层做的权限判定的语义等价 double，用来隔离 P16 的权限维度。
    """

    def __init__(self, accessible_source_ids: set[str]) -> None:
        self._accessible = accessible_source_ids

    async def resolve(self, target_id, *, project_id, audit_year, db):  # noqa: D401
        # 同 scope：返回一个非 None 占位（真实类型为 ResolvedTarget，此处仅需真值语义）
        return object()

    async def can_read(self, target_id, *, actor, project_id, db):  # noqa: D401
        return str(target_id) in self._accessible


@st.composite
def _retrieval_candidates(draw):
    """生成一批检索候选：source_id 唯一；page/region 有效性与可访问性各自随机。"""
    n = draw(st.integers(min_value=0, max_value=6))
    cands: list[RetrievalCandidate] = []
    accessible: set[str] = set()
    for _ in range(n):
        sid = str(uuid.uuid4())
        page = draw(st.one_of(st.none(), st.integers(min_value=-2, max_value=5)))
        region = draw(
            st.one_of(
                st.none(),
                st.just({}),
                st.fixed_dictionaries({"x": st.integers(), "y": st.integers()}),
            )
        )
        is_accessible = draw(st.booleans())
        if is_accessible:
            accessible.add(sid)
        cands.append(
            RetrievalCandidate(
                source_type="attachment_version",
                source_id=sid,
                source_version="1",
                content_hash=sha256_hex(sid),  # 真实有效 sha256 hex
                page=page,
                region=region,
                excerpt_text=f"excerpt-{sid[:8]}",
                index_version="v1",
                locator_version="v1",
                locator=f"/doc/{sid[:6]}",
                evidence_ref_id=None,  # 走 filter3 搜索分支（假会话返回 active ref）
            )
        )
    return cands, accessible


def _run(coro):
    """每个 hypothesis example 用全新事件循环运行 async 服务，避免 loop 复用问题。"""
    return asyncio.run(coro)


# ═════════════════════════════════════════════════════════════════════════════
# P15 RAG 引用可定位 — confirmed citation 必须 page/region 有效、摘录哈希可复算
# ═════════════════════════════════════════════════════════════════════════════


@given(page=st.one_of(st.none(), st.integers(min_value=-3, max_value=7)),
       region=st.one_of(st.none(), st.just({}), st.dictionaries(st.text(max_size=4), st.integers(), max_size=4)))
def test_p15_is_locatable_predicate(page, region):
    """P15：真实 ``CitationSnapshotService._is_locatable`` 判定 = page 为 int≥1 且 region 非空。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15
    """
    svc = CitationSnapshotService(MagicMock())
    cand = RetrievalCandidate(source_type="attachment_version", source_id="s", page=page, region=region)
    expected = (page is not None) and (page >= 1) and bool(region)
    assert svc._is_locatable(cand) is expected


@given(data=_retrieval_candidates())
def test_p15_created_citations_are_locatable_and_recomputable(data):
    """P15：真实过滤链创建的每条 citation 必满足 page≥1、region 非空、
    excerpt_hash == sha256_hex(excerpt_text) 且为合法 64 位十六进制（可离线复算）。

    exercises 真实 ``create_citation_from_retrieval`` + ``_create_snapshot``。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15
    """
    candidates, accessible = data

    async def _go():
        svc = CitationSnapshotService(_FakeCitationSession())
        with patch(
            "app.services.evidence_governance.citation_snapshot_service.get_adapter",
            return_value=_FakeAdapter(accessible),
        ):
            return await svc.create_citation_from_retrieval(
                retrieval_results=candidates,
                actor=ActorContext.for_user(uuid.uuid4()),
                project_id=uuid.uuid4(),
                audit_year=2025,
                ai_content_log_id=uuid.uuid4(),
            )

    created = _run(_go())
    by_id = {c.source_id: c for c in candidates}
    for cite in created:
        # page 有效 + region 非空（P15 可定位）
        assert cite.page is not None and cite.page >= 1
        assert cite.region
        # 摘录哈希可复算且为合法 sha256（page/region/hash/ref/excerpt-hash 均可复算）
        src = by_id[cite.source_id]
        assert cite.excerpt_hash == sha256_hex(src.excerpt_text)
        assert is_sha256_hex(cite.excerpt_hash)
        # 内容哈希绑定：与候选一致且合法
        assert cite.content_hash == src.content_hash and is_sha256_hex(cite.content_hash)


# ═════════════════════════════════════════════════════════════════════════════
# P16 RAG 权限不扩张 — 返回引用集合恒是 actor 可访问来源集合的子集
# ═════════════════════════════════════════════════════════════════════════════


@given(data=_retrieval_candidates())
def test_p16_citation_set_is_subset_of_accessible(data):
    """P16：真实过滤链输出的 citation 来源集合始终 ⊆ actor 可访问来源集合，
    绝不因 RAG 而扩张权限（不可访问的候选永不进入结果）。

    exercises 真实 ``create_citation_from_retrieval``（含真实 ``_actor_can_read_source``
    调用被 patch 的 adapter.can_read）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 16
    """
    candidates, accessible = data

    async def _go():
        svc = CitationSnapshotService(_FakeCitationSession())
        with patch(
            "app.services.evidence_governance.citation_snapshot_service.get_adapter",
            return_value=_FakeAdapter(accessible),
        ):
            return await svc.create_citation_from_retrieval(
                retrieval_results=candidates,
                actor=ActorContext.for_user(uuid.uuid4()),
                project_id=uuid.uuid4(),
                audit_year=2025,
                ai_content_log_id=uuid.uuid4(),
            )

    created = _run(_go())
    out_sources = {c.source_id for c in created}
    # 子集不变量：输出 ⊆ 可访问集
    assert out_sources <= accessible, (
        f"P16 违反：输出来源 {out_sources - accessible} 不在 actor 可访问集内"
    )


# ═════════════════════════════════════════════════════════════════════════════
# P17 AI 状态门禁 — 仅人工确认 + hash 一致 + (策略必需证据 ∪ 已有依赖) 有效可进 FormalOutput
#   历史对象无附件本身不构成违规
# ═════════════════════════════════════════════════════════════════════════════


class _ListPolicyProvider(PolicyProvider):
    def __init__(self, items: list[EvidenceItem], version: str | None = "pol-v1") -> None:
        self._items = items
        self._version = version

    async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
        return list(self._items)

    async def get_policy_version(self, target_id, target_type):
        return self._version


class _ListGraphProvider(UnifiedGraphProvider):
    def __init__(self, items: list[EvidenceItem]) -> None:
        self._items = items

    async def get_existing_dependencies(self, target_id, target_type):
        return list(self._items)


def _clean_item(evidence_type: str, eid: str | None = None) -> EvidenceItem:
    """构造一个满足全部 P0 约束的干净证据项（gate 不应对它产生任何阻断原因）。"""
    return EvidenceItem(
        evidence_id=eid or str(uuid.uuid4()),
        evidence_type=evidence_type,
        source="policy",
        metadata_complete=True,
        has_actor=True,
        version="1",
        content_hash="a" * 64,
        is_active_ref=True,
        ocr_confirmed=True,
        ocr_written_back=True,
        ai_human_confirmed=True,
        ai_hash_consistent=True,
        citation_locatable=True,
        is_stale=False,
        has_pending_propagation=False,
        has_blocking_review=False,
        hold_retention_consistent=True,
    )


_EVIDENCE_TYPES = ["attachment_version", "ocr_result", "ai_content", "citation", "ref"]


def test_p17_historical_object_without_attachment_is_not_a_violation():
    """P17：策略未要求且无已有依赖的历史对象 → RequiredEvidence 为空 → preflight PASS，
    绝不产生 MISSING_REQUIRED_EVIDENCE / MISSING_ATTACHMENT。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17
    """
    gate = FormalOutputGate(
        policy_provider=_ListPolicyProvider([], version=None),
        graph_provider=_ListGraphProvider([]),
    )
    result = _run(gate.preflight("hist-target", "workpaper_conclusion"))
    assert result.verdict is GateVerdict.PASS
    assert result.evidence_count == 0
    codes = {r.code for r in result.blocking_reasons}
    assert BlockReasonCode.MISSING_REQUIRED_EVIDENCE not in codes


@given(types=st.lists(st.sampled_from(_EVIDENCE_TYPES), min_size=1, max_size=5))
def test_p17_all_clean_evidence_passes(types):
    """P17：当「策略必需证据 ∪ 已有依赖」全部满足 P0 约束（人工确认 / hash 一致 / 非 stale …）
    时，preflight 判 PASS 且无阻断原因。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17
    """
    policy_items = [_clean_item(t) for t in types]
    gate = FormalOutputGate(
        policy_provider=_ListPolicyProvider(policy_items),
        graph_provider=_ListGraphProvider([]),
    )
    result = _run(gate.preflight("t1", "workpaper_conclusion"))
    assert result.verdict is GateVerdict.PASS, [r.code for r in result.blocking_reasons]
    assert result.blocking_reasons == []


@given(
    n_clean=st.integers(min_value=0, max_value=3),
    defect=st.sampled_from(
        [
            ("metadata_complete", False, BlockReasonCode.METADATA_INCOMPLETE, "attachment_version"),
            ("has_actor", False, BlockReasonCode.ACTOR_MISSING, "attachment_version"),
            ("is_active_ref", False, BlockReasonCode.REF_INACTIVE, "attachment_version"),
            ("ocr_confirmed", False, BlockReasonCode.OCR_NOT_CONFIRMED, "ocr_result"),
            ("ai_human_confirmed", False, BlockReasonCode.AI_NOT_CONFIRMED, "ai_content"),
            ("citation_locatable", False, BlockReasonCode.CITATION_NOT_LOCATABLE, "citation"),
            ("is_stale", True, BlockReasonCode.STALE_EVIDENCE, "attachment_version"),
            ("hold_retention_consistent", False, BlockReasonCode.HOLD_RETENTION_INCONSISTENT, "attachment_version"),
        ]
    ),
)
def test_p17_any_p0_violation_blocks_formal_output(n_clean, defect):
    """P17：只要「必需证据」集合内存在任一违反 P0 完整性的项（元数据缺 / 无 actor / ref 失效 /
    OCR 未确认 / AI 未人工确认 / citation 不可定位 / stale / hold 不一致），preflight 必 FAIL
    且带出对应阻断码——非人工确认 / hash 不一致的 AI 内容不得进入 FormalOutput。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17
    """
    field, bad_value, expected_code, etype = defect
    items = [_clean_item("attachment_version") for _ in range(n_clean)]
    bad = _clean_item(etype)
    # 用 dataclasses.replace 保持其它字段干净，只翻转被测违规字段
    import dataclasses

    bad = dataclasses.replace(bad, **{field: bad_value})
    items.append(bad)

    gate = FormalOutputGate(
        policy_provider=_ListPolicyProvider(items),
        graph_provider=_ListGraphProvider([]),
    )
    result = _run(gate.preflight("t1", "workpaper_conclusion"))
    assert result.verdict is GateVerdict.FAIL
    codes = {r.code for r in result.blocking_reasons}
    assert expected_code in codes, f"期望阻断码 {expected_code} 未出现，实得 {codes}"


def test_p17_undeclared_ai_entry_is_rejected_before_persistence():
    """P17（运行时门禁）：真实 ``AIEvidenceGate.register_generation`` 对未登记入口在任何
    持久化之前即抛 ``EVIDENCE_GATE_BLOCKED``（未登记内容无法生成 draft，遑论进入 FormalOutput）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17
    """
    gate = AIEvidenceGate(MagicMock())  # DB 永不会被触达（校验在最前）

    async def _go():
        return await gate.register_generation(
            entry_point="totally_undeclared_entry",
            prompt_hash=sha256_hex("x"),
            model_name="m",
            output="o",
            actor=ActorContext.for_user(uuid.uuid4()),
            project_id=uuid.uuid4(),
        )

    with pytest.raises(EvidenceGovernanceError) as exc:
        _run(_go())
    assert exc.value.error_code is EvidenceErrorCode.EVIDENCE_GATE_BLOCKED


# ═════════════════════════════════════════════════════════════════════════════
# P18 AI 入口覆盖 — discovered − declared 恒为空集
# ═════════════════════════════════════════════════════════════════════════════


@given(
    declared=st.sets(st.text(min_size=1, max_size=8), max_size=8),
    extra=st.sets(st.text(min_size=1, max_size=8), max_size=6),
)
def test_p18_coverage_gap_is_set_difference(declared, extra):
    """P18：真实 ``compute_coverage_gap`` = discovered − declared；gap 为空 ⇔ discovered ⊆ declared。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 18
    """
    discovered = set(declared) | set(extra)
    gap = compute_coverage_gap(discovered, declared)
    assert gap == discovered - set(declared)
    assert (gap == set()) == (discovered <= set(declared))
    # 已登记入口全在覆盖内：discovered=declared 时 gap 必空
    assert compute_coverage_gap(set(declared), declared) == set()


def _load_scanner():
    """从脚本路径加载真实 AI 入口覆盖扫描器模块。"""
    backend_root = Path(__file__).resolve().parents[2]
    scanner_path = backend_root / "scripts" / "check" / "check_ai_entry_coverage.py"
    spec = importlib.util.spec_from_file_location("_ai_entry_scanner_p18", scanner_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, backend_root


def test_p18_real_repo_has_no_undeclared_ai_entrypoints():
    """P18（真实仓库不变量 / CI 门）：用真实扫描器对 backend 源码求 discovered − declared，
    差集必须为空——存在未登记 AI 入口即 P18 违反（保留反例清单）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 18
    """
    scanner, backend_root = _load_scanner()
    discovered = scanner.scan_directories(backend_root, scanner.SCAN_DIRS)
    gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)
    assert gap == set(), f"P18 违反：发现未登记 AI 入口 {sorted(gap)}"


# ═════════════════════════════════════════════════════════════════════════════
# P19 已确认内容变更失效 — confirmed 内容或任一依据变化 → 回到 draft/stale，原确认不再授权
# ═════════════════════════════════════════════════════════════════════════════


@given(seed=st.integers(min_value=0, max_value=3))
def test_p19_confirmed_ai_content_authorizes_only_while_hash_and_deps_hold(seed):
    """P19：AI 内容在「人工确认 + hash 一致 + 依据非 stale」时授权输出（gate 无 AI 阻断）；
    一旦内容 hash 变化（confirmed 内容改动）或任一依据 stale，gate 立刻阻断
    （AI_HASH_CHANGED / STALE_EVIDENCE），原确认不再授权。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 19
    """
    ai_ok = _clean_item("ai_content")

    # 基线：确认 + hash 一致 + 非 stale → gate 不因该 AI 项阻断
    gate_ok = FormalOutputGate(
        policy_provider=_ListPolicyProvider([ai_ok]),
        graph_provider=_ListGraphProvider([]),
    )
    res_ok = _run(gate_ok.preflight("t", "report"))
    assert res_ok.verdict is GateVerdict.PASS, [r.code for r in res_ok.blocking_reasons]

    import dataclasses

    # 变体 A：已确认内容的 hash 变化 → 失效（P19）
    hash_changed = dataclasses.replace(ai_ok, ai_hash_consistent=False)
    res_a = _run(
        FormalOutputGate(
            policy_provider=_ListPolicyProvider([hash_changed]),
            graph_provider=_ListGraphProvider([]),
        ).preflight("t", "report")
    )
    assert res_a.verdict is GateVerdict.FAIL
    assert BlockReasonCode.AI_HASH_CHANGED in {r.code for r in res_a.blocking_reasons}

    # 变体 B：任一依据 stale → 失效（P19：依据变化传播）。
    # 注意：RequiredEvidence 按 evidence_id 去重且策略项优先，故 stale 依赖必须用**不同** id，
    # 才能真正进入被校验集合（这本身印证了 gate 的并集去重语义）。
    dep_stale = dataclasses.replace(ai_ok, evidence_id=str(uuid.uuid4()), is_stale=True)
    res_b = _run(
        FormalOutputGate(
            policy_provider=_ListPolicyProvider([ai_ok]),
            graph_provider=_ListGraphProvider([dep_stale]),
        ).preflight("t", "report")
    )
    assert res_b.verdict is GateVerdict.FAIL
    assert BlockReasonCode.STALE_EVIDENCE in {r.code for r in res_b.blocking_reasons}

    # 变体 C：未确认（draft，人工确认缺失）→ 不授权
    not_confirmed = dataclasses.replace(ai_ok, ai_human_confirmed=False)
    res_c = _run(
        FormalOutputGate(
            policy_provider=_ListPolicyProvider([not_confirmed]),
            graph_provider=_ListGraphProvider([]),
        ).preflight("t", "report")
    )
    assert res_c.verdict is GateVerdict.FAIL
    assert BlockReasonCode.AI_NOT_CONFIRMED in {r.code for r in res_c.blocking_reasons}
