"""Wave 8 — stale-review 属性组 PBT（Task 9.4）：逐项覆盖 P20–P22。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.4 (Wave 8)
Requirements: R9, R10
Design: §4.4 UnifiedGraphBuilder, §5.4 stale/Review/统一依赖图, §10.1 真实 PG 铁律,
        §11 属性 P20–P22

逐项属性（每个属性一个 `Feature: ..., Property N` 注解的属性测试）:
  * P20 统一图精确闭包 —— 纯/模型 PBT：actual stale 集合精确等于变化源在同一
        project/year "统一依赖图"（活动 EvidenceDependency ∪ 规范化 ACNR/legacy 边并集）
        中的可达下游闭包；不得以任一单表闭包替代。
  * P21 Blocking Review 关闭门禁 —— 纯/模型 PBT：Blocking_Review 仅在
        (非 Service Identity) ∧ 权限 ∧ 充分说明 ∧ 至少一个非 stale EvidenceRef ∧ 可关闭态
        五者同时满足时才允许关闭，否则拒绝并保留完整历史。
  * P22 复核自动重开 —— 纯/模型 PBT：已关闭意见依据（被替换/停用/标记 stale）失效后
        进入 re_review_required，并阻断 QC/EQCR/partner 完成。

复用 Wave 5 已构建服务，不分叉、不影子实现：
  - `unified_graph_builder`（P20 的 UnifiedGraph / normalize_node_key /
    compute_canonical_edge_hash / downstream_closure），
  - `review_evidence_service.ReviewEvidenceService`（P21/P22 的关闭门禁与自动重开）。

P20 说明：本文件是 Wave 8 合并属性组对 P20 的合并级重述，走 UnifiedGraph 公开 API
（downstream_closure）对齐参考 BFS 闭包，并显式验证三 provenance 并集不被任一单表替代。
P20 的详尽 DAG 生成器 / 去重 / 全入边清除等原始覆盖在
`tests/evidence_governance/test_unified_graph_stale_closure_pbt.py`（Task 6.4）已实现且通过，
本文件引用之而非复制其生成器。

常规 PBT 使用全局 fast profile（conftest 注册，默认 max_examples=5，可由
HYPOTHESIS_MAX_EXAMPLES 覆盖）；不在测试正文固定样本数。失败 counterexample 由
Hypothesis 保留。R9/R10 的纯谓词与内存参考模型无需真实 PG（design §10.1：仅 PG 相关
不变量才要求 PostgreSQL 16）。
"""

from __future__ import annotations

import uuid
from collections import deque

from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance.frozen_contracts import ActorContext, ActorType
from app.services.evidence_governance.review_evidence_service import (
    ReviewEvidenceService,
    ReviewSeverity,
    ReviewStatus,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    compute_canonical_edge_hash,
    normalize_node_key,
)

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"


# ===========================================================================
# P20 — 统一图精确闭包（纯/模型 PBT）
# ===========================================================================
#
# 模型：随机生成混合 provenance（EvidenceDependency / ACNR / legacy）的有向边，
#   经 normalize_node_key + compute_canonical_edge_hash 归一化后并入单一 UnifiedGraph；
#   downstream_closure(source) 必须精确等于参考 BFS 可达下游闭包（无过纳、无漏纳），
#   且闭包穿越三种 provenance 边界（union，而非任一单表闭包）。

_NODE_TYPE = st.sampled_from([
    "attachment_version", "workpaper", "ocr_result", "ai_content",
    "citation", "evidence_ref", "acnr", "legacy",
])
_NODE_ID = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=6)
_PROVENANCE = st.sampled_from(list(EdgeProvenance))


@st.composite
def _edge(draw: st.DrawFn) -> dict:
    return {
        "source_type": draw(_NODE_TYPE),
        "source_id": draw(_NODE_ID),
        "target_type": draw(_NODE_TYPE),
        "target_id": draw(_NODE_ID),
        "provenance": draw(_PROVENANCE),
    }


@st.composite
def _graph_and_source(draw: st.DrawFn) -> tuple[list[dict], str]:
    edges = draw(st.lists(_edge(), min_size=1, max_size=18))
    source_key = draw(
        st.sampled_from([
            normalize_node_key(e["source_type"], e["source_id"]) for e in edges
        ])
    )
    return edges, source_key


def _reference_bfs_closure(edges: list[dict], start_key: str) -> set[str]:
    """参考实现：以 canonical edge hash 去重后，从 start_key 做精确 BFS 下游闭包。"""
    adjacency: dict[str, set[str]] = {}
    seen: set[str] = set()
    for e in edges:
        h = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"], e["provenance"],
        )
        if h in seen:
            continue
        seen.add(h)
        sk = normalize_node_key(e["source_type"], e["source_id"])
        tk = normalize_node_key(e["target_type"], e["target_id"])
        adjacency.setdefault(sk, set()).add(tk)

    visited = {start_key}
    q: deque[str] = deque([start_key])
    closure: set[str] = set()
    while q:
        cur = q.popleft()
        for nb in adjacency.get(cur, set()):
            if nb not in visited:
                visited.add(nb)
                closure.add(nb)
                q.append(nb)
    return closure


def _build_unified_graph(edges: list[dict]) -> UnifiedGraph:
    graph = UnifiedGraph(scope=GraphScope(project_id=uuid.uuid4(), audit_year=2025))
    for e in edges:
        graph.add_edge(NormalizedEdge(
            source_key=normalize_node_key(e["source_type"], e["source_id"]),
            target_key=normalize_node_key(e["target_type"], e["target_id"]),
            provenance=e["provenance"],
            edge_hash=compute_canonical_edge_hash(
                e["source_type"], e["source_id"],
                e["target_type"], e["target_id"], e["provenance"],
            ),
        ))
    return graph


@given(data=_graph_and_source())
def test_property_p20_unified_closure_exact(data: tuple[list[dict], str]) -> None:
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    统一图精确闭包：UnifiedGraph.downstream_closure(source) 精确等于统一依赖图
    （活动 EvidenceDependency ∪ 规范化 ACNR/legacy 边并集）中的可达下游闭包，
    无过纳、无漏纳。（详尽生成器覆盖见 Task 6.4 test_unified_graph_stale_closure_pbt.py）

    **Validates: Requirements 9**
    """
    edges, start_key = data
    graph = _build_unified_graph(edges)

    actual = graph.downstream_closure(start_key)
    expected = _reference_bfs_closure(edges, start_key)

    assert actual == expected, (
        f"P20 违背：actual={actual} expected={expected} start={start_key} "
        f"edges={len(edges)}"
    )


@given(data=_graph_and_source())
def test_property_p20_union_not_single_table(data: tuple[list[dict], str]) -> None:
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    统一图为三 provenance（EvidenceDependency/ACNR/legacy）边的并集，闭包穿越
    provenance 边界；任一单一 provenance 的子图闭包都是统一闭包的子集（不得以单表替代）。

    **Validates: Requirements 9**
    """
    edges, start_key = data
    unified = _build_unified_graph(edges)
    unified_closure = unified.downstream_closure(start_key)

    # 逐 provenance 构建单表子图，其闭包必须 ⊆ 统一闭包（单表不得超出统一并集）。
    for prov in EdgeProvenance:
        sub_edges = [e for e in edges if e["provenance"] == prov]
        if not sub_edges:
            continue
        source_keys = {normalize_node_key(e["source_type"], e["source_id"]) for e in sub_edges}
        if start_key not in source_keys and start_key not in {
            normalize_node_key(e["target_type"], e["target_id"]) for e in sub_edges
        }:
            # start_key 不在该单表子图中，其单表闭包为空，天然 ⊆。
            continue
        sub_closure = _reference_bfs_closure(sub_edges, start_key)
        assert sub_closure <= unified_closure, (
            f"P20 违背：单表({prov}) 闭包 {sub_closure} 不是统一闭包 "
            f"{unified_closure} 的子集"
        )


# ===========================================================================
# P21 — Blocking Review 关闭门禁（纯/模型 PBT）
# ===========================================================================
#
# 关闭当且仅当：(非 Service Identity) ∧ 有 review.close 权限 ∧ 充分关闭说明
#   ∧ 至少一个非 stale EvidenceRef ∧ 意见处于可关闭态（open / re_review_required）。


def _make_actor(is_service: bool) -> ActorContext:
    if is_service:
        return ActorContext(
            actor_type=ActorType.SERVICE,
            actor_service_identity_id=uuid.uuid4(),
        )
    return ActorContext(actor_type=ActorType.USER, actor_user_id=uuid.uuid4())


def _make_refs(*, n_valid: int, n_stale: int) -> list[dict]:
    refs: list[dict] = []
    for i in range(n_valid):
        refs.append({
            "evidence_ref_id": f"ref-valid-{i}",
            "evidence_type": "attachment_version",
            "target_version": 1,
            "target_hash": "h" * 64,
            "locator": "opaque://x",
            "stale": False,
        })
    for i in range(n_stale):
        refs.append({
            "evidence_ref_id": f"ref-stale-{i}",
            "evidence_type": "attachment_version",
            "target_version": 1,
            "target_hash": "h" * 64,
            "locator": "opaque://x",
            "stale": True,
        })
    return refs


@given(
    is_service=st.booleans(),
    has_perm=st.booleans(),
    explanation=st.sampled_from(["", "   ", "关闭说明：证据充分且已核对。"]),
    n_valid=st.integers(min_value=0, max_value=3),
    n_stale=st.integers(min_value=0, max_value=3),
    severity=st.sampled_from([s.value for s in ReviewSeverity]),
)
def test_property_p21_close_gate(
    is_service, has_perm, explanation, n_valid, n_stale, severity
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 21.

    Blocking Review 关闭门禁：允许关闭 IFF (非 Service Identity) ∧ 权限 ∧ 充分说明
    ∧ 至少一个非 stale EvidenceRef ∧ 可关闭态；任一不满足则拒绝且不改变状态、保留历史。

    **Validates: Requirements 10.2**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id=str(uuid.uuid4()),
        audit_year=2025,
        target_type="workpaper_cell",
        target_id="cell-1",
        severity=severity,
        content="需复核",
        created_by_user_id=str(uuid.uuid4()),
    )
    assert opinion.status == ReviewStatus.open.value  # 初始可关闭态
    prev_history_len = len(opinion.history)

    refs = _make_refs(n_valid=n_valid, n_stale=n_stale)
    actor = _make_actor(is_service)

    result = service.close_review(
        opinion,
        closing_explanation=explanation,
        closer_user_id=str(uuid.uuid4()),
        actor=actor,
        has_close_permission=has_perm,
        current_evidence_refs=refs,
    )

    has_explanation = bool(explanation and explanation.strip())
    has_valid_ref = n_valid > 0
    should_allow = (
        (not is_service) and has_perm and has_explanation and has_valid_ref
    )

    assert result.allowed == should_allow, (
        f"P21 违背：allowed={result.allowed} 期望={should_allow} "
        f"service={is_service} perm={has_perm} expl={has_explanation} "
        f"valid_ref={has_valid_ref}"
    )

    if should_allow:
        assert opinion.status == ReviewStatus.closed.value
        assert opinion.closed_by_user_id is not None
    else:
        # 拒绝：状态保持 open，且历史记录追加（保留完整历史，不丢失）。
        assert opinion.status == ReviewStatus.open.value
        assert len(opinion.history) > prev_history_len
        assert result.reject_reasons  # 至少一个结构化拒绝原因


@given(
    n_stale=st.integers(min_value=1, max_value=4),
)
def test_property_p21_only_stale_refs_reject(n_stale):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 21.

    仅有 stale EvidenceRef（无一个非 stale）时，即便权限/说明齐备也必须拒绝关闭。

    **Validates: Requirements 10.2**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id=str(uuid.uuid4()), audit_year=2025,
        target_type="workpaper_cell", target_id="c1",
        severity=ReviewSeverity.critical.value, content="x",
        created_by_user_id=str(uuid.uuid4()),
    )
    result = service.close_review(
        opinion,
        closing_explanation="完整关闭说明。",
        closer_user_id=str(uuid.uuid4()),
        actor=_make_actor(is_service=False),
        has_close_permission=True,
        current_evidence_refs=_make_refs(n_valid=0, n_stale=n_stale),
    )
    assert result.allowed is False
    assert opinion.status == ReviewStatus.open.value
    from app.services.evidence_governance.review_evidence_service import CloseRejectReason

    assert CloseRejectReason.no_valid_evidence_ref in result.reject_reasons


# ===========================================================================
# P22 — 复核自动重开与 QC/EQCR 阻断（纯/模型 PBT）
# ===========================================================================
#
# 已关闭意见依据失效（替换/停用/stale）→ auto_reopen → re_review_required；
# 任一 re_review_required 意见都阻断 QC/EQCR/partner 完成。


def _close_opinion(service: ReviewEvidenceService) -> "object":
    opinion = service.create_opinion(
        project_id=str(uuid.uuid4()), audit_year=2025,
        target_type="workpaper_cell", target_id="c1",
        severity=ReviewSeverity.high.value, content="需复核",
        created_by_user_id=str(uuid.uuid4()),
    )
    res = service.close_review(
        opinion,
        closing_explanation="证据充分，予以关闭。",
        closer_user_id=str(uuid.uuid4()),
        actor=_make_actor(is_service=False),
        has_close_permission=True,
        current_evidence_refs=_make_refs(n_valid=1, n_stale=0),
    )
    assert res.allowed is True
    assert opinion.status == ReviewStatus.closed.value
    return opinion


@given(
    reason=st.sampled_from(["evidence_replaced", "evidence_deactivated", "marked_stale"]),
)
def test_property_p22_auto_reopen_blocks_completion(reason):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    已关闭意见依据失效后 auto_reopen → re_review_required，且 QC/EQCR/partner 完成被阻断。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()
    opinion = _close_opinion(service)

    reopened = service.auto_reopen(
        opinion, reason=reason, invalidated_ref_ids=["ref-valid-0"]
    )
    assert reopened is True
    assert opinion.status == ReviewStatus.re_review_required.value
    # 历史保留自动重开记录。
    assert opinion.history[-1]["action"] == "auto_reopened"
    assert opinion.history[-1]["reason"] == reason

    # P22 不变量：完成被阻断。
    assert service.check_completion_blocked([opinion]) is True
    # 目标限定同样阻断（同 target）。
    assert service.check_completion_blocked(
        [opinion], target_type="workpaper_cell", target_id="c1"
    ) is True


@given(
    n_total=st.integers(min_value=1, max_value=5),
    n_reopened=st.integers(min_value=0, max_value=5),
)
def test_property_p22_any_reopened_blocks_all(n_total, n_reopened):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    完成被阻断 IFF 至少存在一个 re_review_required 意见；全部为 closed 时才可完成。

    **Validates: Requirements 10.3**
    """
    n_reopened = min(n_reopened, n_total)
    service = ReviewEvidenceService()
    opinions = []
    for i in range(n_total):
        op = _close_opinion(service)
        if i < n_reopened:
            service.auto_reopen(op, reason="marked_stale")
            assert op.status == ReviewStatus.re_review_required.value
        else:
            assert op.status == ReviewStatus.closed.value
        opinions.append(op)

    blocked = service.check_completion_blocked(opinions)
    assert blocked == (n_reopened > 0), (
        f"P22 违背：blocked={blocked} n_reopened={n_reopened} n_total={n_total}"
    )


def test_property_p22_reopen_only_from_closed():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    auto_reopen 仅对 closed 意见生效；open / 已 re_review_required 为幂等 no-op。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()

    # open 意见：auto_reopen no-op。
    open_op = service.create_opinion(
        project_id=str(uuid.uuid4()), audit_year=2025,
        target_type="t", target_id="i",
        severity=ReviewSeverity.high.value, content="x",
        created_by_user_id=str(uuid.uuid4()),
    )
    assert service.auto_reopen(open_op, reason="stale") is False
    assert open_op.status == ReviewStatus.open.value

    # closed → re_review_required；二次 reopen no-op。
    closed_op = _close_opinion(service)
    assert service.auto_reopen(closed_op, reason="stale") is True
    assert closed_op.status == ReviewStatus.re_review_required.value
    assert service.auto_reopen(closed_op, reason="replaced") is False
    assert closed_op.status == ReviewStatus.re_review_required.value
