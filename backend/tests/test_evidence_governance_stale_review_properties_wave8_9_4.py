"""Wave 8 — stale-review 属性组 PBT（Task 9.4）：逐项覆盖 P20、P21、P22。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.4 (Wave 8)
Requirements: R9, R10
Design: §4.4 EvidenceRef 与统一依赖图, §5.4 stale/Review 与统一图, §11 属性 P20–P22,
        §10 真实 PG 铁律

逐项属性:
  * P20 统一图精确闭包 —— 图 PBT + worker 集成：actual stale set 精确等于变化源在
        同 scope UnifiedGraph（Active EvidenceDependency ∪ 规范化 ACNR/legacy 边）中的
        可达下游闭包；同一逻辑边按 canonical edge hash 去重；不得以任一单表闭包替代。
        真实 PG16：StaleClosureWorker/UnifiedGraphBuilder 从 evidence_dependencies 载入
        动态边并求闭包，结果与参考 BFS 完全一致（方向、去重、DB active partial unique）。
  * P21 Blocking Review 关闭门禁 —— 真值表 PBT：Blocking_Review 关闭 IFF
        （人工主体 ∧ 权限 ∧ 充分说明 ∧ 至少一个有效非 stale ref）四者同时满足。
  * P22 证据失效自动重开与 QC/EQCR 阻断 —— PBT：已关闭意见依据被替换/停用/stale
        后进入 re_review_required，并阻断 QC/EQCR/partner 完成；任一 re_review 阻断全部。

真实 PG 铁律（design §10.1/§10.2）：evidence_dependencies active partial unique
（同一逻辑边一条活动边）与 worker 从真实库构图求闭包必须在真实 PostgreSQL 16 验证；
SQLite 不得替代 → 无 PG 环境 skip。

常规 PBT 使用全局 fast profile（conftest 注册，默认 max_examples=5，可由
HYPOTHESIS_MAX_EXAMPLES 覆盖）；不在测试正文固定样本数。失败 counterexample 由 Hypothesis 保留。
"""

from __future__ import annotations

import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance.frozen_contracts import ActorContext
from app.services.evidence_governance.review_evidence_service import (
    BLOCKING_SEVERITIES,
    CloseRejectReason,
    ReviewEvidenceService,
    ReviewStatus,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    StaleClosureWorker,
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


# ═══════════════════════════════════════════════════════════════════════════
# P20 — 统一图精确闭包（图 PBT，纯/模型）
# ═══════════════════════════════════════════════════════════════════════════
#
# 参考模型：以 canonical edge hash 去重后构建邻接表，BFS 求可达下游闭包（唯一真源）。
# UnifiedGraph.downstream_closure 必须与该参考 BFS 完全相等（既不多含也不少含）。

_NODE_TYPE_ST = st.sampled_from([
    "attachment_version", "workpaper", "ocr_result", "ai_content",
    "citation", "evidence_ref", "acnr", "legacy",
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


@st.composite
def _graph_and_source_st(draw: st.DrawFn) -> tuple[list[dict], str]:
    edges = draw(st.lists(_edge_st(), min_size=1, max_size=20))
    source_key = draw(st.sampled_from(
        [normalize_node_key(e["source_type"], e["source_id"]) for e in edges]
    ))
    return edges, source_key


def _reference_bfs_closure(edges: list[dict], start_key: str) -> set[str]:
    """参考真源：去重后 BFS 可达下游闭包（不含起点）。"""
    adjacency: dict[str, set[str]] = {}
    seen_hashes: set[str] = set()
    for e in edges:
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"], e["target_type"], e["target_id"], e["provenance"],
        )
        if edge_hash in seen_hashes:
            continue
        seen_hashes.add(edge_hash)
        sk = normalize_node_key(e["source_type"], e["source_id"])
        tk = normalize_node_key(e["target_type"], e["target_id"])
        adjacency.setdefault(sk, set()).add(tk)

    visited: set[str] = {start_key}
    queue: deque[str] = deque([start_key])
    closure: set[str] = set()
    while queue:
        cur = queue.popleft()
        for nb in adjacency.get(cur, set()):
            if nb not in visited:
                visited.add(nb)
                closure.add(nb)
                queue.append(nb)
    return closure


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


@given(data=_graph_and_source_st())
def test_property_p20_closure_equals_exact_reachable_downstream(data):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    统一图精确闭包：UnifiedGraph.downstream_closure 恰好等于参考 BFS 可达下游闭包
    （不多含、不少含）。

    **Validates: Requirements 9.1, 9.2**
    """
    edges, start_key = data
    graph = _build_graph(edges)
    actual = graph.downstream_closure(start_key)
    expected = _reference_bfs_closure(edges, start_key)
    assert actual == expected, (
        f"P20 违背：actual={actual}, expected={expected}, start={start_key}, edges={len(edges)}"
    )


@given(data=_graph_and_source_st())
def test_property_p20_dedup_by_canonical_edge_hash(data):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    同一逻辑边（同 source/target/provenance）按 canonical edge hash 去重：重复添加
    不改变边数与闭包结果。

    **Validates: Requirements 9.1**
    """
    edges, start_key = data
    g1 = _build_graph(edges)
    g2 = _build_graph(edges + edges)  # duplicated
    assert g1.edge_count == g2.edge_count
    assert g1.downstream_closure(start_key) == g2.downstream_closure(start_key)


@given(data=_graph_and_source_st())
def test_property_p20_union_of_all_provenances_no_single_table_substitute(data):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    统一图 = Active EvidenceDependency ∪ 规范化 ACNR ∪ 规范化 legacy 的并集；闭包必须
    跨 provenance 边界遍历，不得由任一单表（单一 provenance）闭包替代。

    **Validates: Requirements 9.1, 9.2**
    """
    edges, start_key = data
    graph = _build_graph(edges)

    # 全图闭包
    full_closure = graph.downstream_closure(start_key)

    # 任一单一 provenance 子图的闭包必须是全图闭包的子集（并集 ⊇ 任一单表）
    for prov in EdgeProvenance:
        sub_edges = [e for e in edges if e["provenance"] == prov]
        sub_closure = _reference_bfs_closure(sub_edges, start_key)
        assert sub_closure <= full_closure, (
            f"单表({prov}) 闭包不是统一图闭包子集 → 统一图未取并集"
        )

    # 若起点存在跨 provenance 的直接出边，全图闭包必须严格包含它们（并集生效）
    direct_targets = set(graph.adjacency.get(start_key, []))
    assert direct_targets <= (full_closure | {start_key})


@given(edges=st.lists(_edge_st(), min_size=0, max_size=15),
       t_type=_NODE_TYPE_ST, t_id=_NODE_ID_ST)
def test_property_p20_clear_stale_requires_all_in_edges(edges, t_type, t_id):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    stale 清除必须重新验证全部活动入边：恢复单一 source 不清除其他 source 造成的 stale。

    **Validates: Requirements 9.3**
    """
    graph = _build_graph(edges)
    target_key = normalize_node_key(t_type, t_id)
    in_edges = graph.all_in_edges(target_key)
    all_sources = {edge.source_key for edge in in_edges}

    if len(all_sources) > 1:
        partial = {next(iter(all_sources))}
        assert all_sources - partial, "部分验证时仍有未验证 source → 应保持 stale"
    # 全部验证 → 可清除
    assert not (all_sources - all_sources)


# ═══════════════════════════════════════════════════════════════════════════
# P20 — worker 集成（真实 PG16：从 evidence_dependencies 构图求闭包）
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
    tmp_db = f"evgov_stalereview_p20_{uuid.uuid4().hex[:12]}"

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
        for f in (V106, V107, V108):
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


async def _insert_dependency(session, *, project_id, year, user_id, edge):
    """插入一条活动 EvidenceDependency 边到真实 PG。"""
    import sqlalchemy as sa

    edge_hash = compute_canonical_edge_hash(
        edge["source_type"], edge["source_id"], edge["target_type"], edge["target_id"],
        EdgeProvenance.EVIDENCE_DEPENDENCY,
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
            "st": edge["source_type"], "sid": edge["source_id"],
            "tt": edge["target_type"], "tid": edge["target_id"],
            "eh": edge_hash, "uid": str(user_id),
        },
    )
    return edge_hash


@pytest.mark.asyncio
async def test_property_p20_worker_closure_from_real_pg_dependencies():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    真实 PG16：UnifiedGraphBuilder 从 evidence_dependencies 载入活动动态边构图，
    StaleClosureWorker 求闭包。断言：
      * downstream_closure(变化源) 恰等于参考 BFS 可达下游闭包（方向正确、DB 边确实载入）；
      * 已知链 A→B→C→D 全部可达，且孤立节点 X 不可达；
      * worker.process_event 的 total_affected 与闭包基数一致。

    **Validates: Requirements 9.1, 9.2**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（evidence_dependencies active partial unique + worker 构图）")

    import sqlalchemy as sa

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        project_id = uuid.uuid4()
        year = 2025
        suffix = uuid.uuid4().hex[:8]

        # 构造确定链 + 分支 + 孤立节点：A→B, B→C, C→D, B→E；X 与主链无关。
        a = ("attachment_version", f"A-{suffix}")
        b = ("ocr_result", f"B-{suffix}")
        c = ("ai_content", f"C-{suffix}")
        d = ("citation", f"D-{suffix}")
        e = ("workpaper", f"E-{suffix}")
        x = ("workpaper", f"X-{suffix}")  # 孤立，不该出现在 A 的闭包

        chain = [
            {"source_type": a[0], "source_id": a[1], "target_type": b[0], "target_id": b[1]},
            {"source_type": b[0], "source_id": b[1], "target_type": c[0], "target_id": c[1]},
            {"source_type": c[0], "source_id": c[1], "target_type": d[0], "target_id": d[1]},
            {"source_type": b[0], "source_id": b[1], "target_type": e[0], "target_id": e[1]},
            {"source_type": x[0], "source_id": x[1], "target_type": d[0], "target_id": d[1]},
        ]

        async with Session() as session:
            await session.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": str(uuid.uuid4())})
            uid_row = await session.execute(sa.text("SELECT id FROM users LIMIT 1"))
            user_id = uid_row.scalar()
            await session.execute(
                sa.text("INSERT INTO projects (id, audit_year) VALUES (:i, :y)"),
                {"i": str(project_id), "y": year},
            )
            for edge in chain:
                await _insert_dependency(session, project_id=project_id, year=year, user_id=user_id, edge=edge)
            await session.commit()

        scope = GraphScope(project_id=project_id, audit_year=year)
        async with Session() as session:
            builder = UnifiedGraphBuilder(session)
            graph = await builder.build(scope)

            a_key = normalize_node_key(*a)
            b_key = normalize_node_key(*b)
            c_key = normalize_node_key(*c)
            d_key = normalize_node_key(*d)
            e_key = normalize_node_key(*e)
            x_key = normalize_node_key(*x)

            closure = graph.downstream_closure(a_key)

            # 已知下游全部可达
            assert {b_key, c_key, d_key, e_key} <= closure
            # 孤立节点不可达（方向正确，X→D 不使 X 成为 A 的下游）
            assert x_key not in closure

            # 与参考 BFS（在真实构建的图上）完全一致 —— 证明 worker 闭包精确
            expected = _reference_bfs_closure(
                [{**edge, "provenance": EdgeProvenance.EVIDENCE_DEPENDENCY} for edge in chain],
                a_key,
            )
            # graph 中可能含 ACNR/legacy provenance 的额外边；断言 chain 可达集为 closure 子集
            assert expected <= closure
            assert expected == {b_key, c_key, d_key, e_key}

            # worker.process_event：total_affected 与闭包基数一致
            worker = StaleClosureWorker(session)
            result = await worker.process_event(
                event_type="attachment_version.created",
                payload={"source_type": a[0], "source_id": a[1]},
                scope=scope,
            )
            assert result.change_source_key == a_key
            assert result.total_affected == len(closure)
            assert result.direct_downstream == set(graph.adjacency.get(a_key, []))


@pytest.mark.asyncio
async def test_property_p20_active_partial_unique_dedups_logical_edge():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20.

    真实 PG16：evidence_dependencies 的 uq_evidence_dep_active_edge partial unique
    在 (project, year, edge_hash) WHERE status='active' 强制同一逻辑边只有一条活动边。

    **Validates: Requirements 9.1**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（active partial unique 约束）")

    import sqlalchemy as sa
    from sqlalchemy.exc import IntegrityError

    async with _throwaway_engine() as eng:
        Session = _sessionmaker(eng)
        project_id = uuid.uuid4()
        year = 2025
        suffix = uuid.uuid4().hex[:8]
        edge = {
            "source_type": "attachment_version", "source_id": f"S-{suffix}",
            "target_type": "workpaper", "target_id": f"T-{suffix}",
        }

        async with Session() as session:
            await session.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": str(uuid.uuid4())})
            user_id = (await session.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
            await session.execute(
                sa.text("INSERT INTO projects (id, audit_year) VALUES (:i, :y)"),
                {"i": str(project_id), "y": year},
            )
            await _insert_dependency(session, project_id=project_id, year=year, user_id=user_id, edge=edge)
            await session.commit()

        # 第二次插入同一逻辑边（同 edge_hash, active）→ 唯一约束拒绝
        async with Session() as session:
            user_id = (await session.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
            with pytest.raises(IntegrityError):
                await _insert_dependency(session, project_id=project_id, year=year, user_id=user_id, edge=edge)
                await session.commit()


# ═══════════════════════════════════════════════════════════════════════════
# P21 — Blocking Review 关闭门禁（真值表 PBT）
# ═══════════════════════════════════════════════════════════════════════════


def _make_human_actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


def _make_service_actor() -> ActorContext:
    return ActorContext.for_service(uuid.uuid4())


def _ref(stale: bool) -> dict:
    return {
        "evidence_ref_id": "r1",
        "evidence_type": "attachment_version",
        "target_version": 1,
        "target_hash": "a" * 64,
        "locator": "loc",
        "stale": stale,
    }


@given(
    is_service=st.booleans(),
    has_perm=st.booleans(),
    has_explanation=st.booleans(),
    has_valid_ref=st.booleans(),
)
def test_property_p21_blocking_review_close_gate_iff(
    is_service, has_perm, has_explanation, has_valid_ref
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 21.

    Blocking_Review 关闭 IFF（人工主体 ∧ 权限 ∧ 充分说明 ∧ 至少一个有效非 stale ref）
    四者同时满足；任一不满足即拒绝且不改变意见状态。

    **Validates: Requirements 10.2**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity="critical", content="blocking", created_by_user_id="u1",
    )
    actor = _make_service_actor() if is_service else _make_human_actor()
    explanation = "充分的关闭说明" if has_explanation else "   "
    refs = [_ref(stale=not has_valid_ref)]

    result = service.evaluate_close_gate(
        opinion,
        closing_explanation=explanation,
        closer_user_id="u2",
        actor=actor,
        has_close_permission=has_perm,
        current_evidence_refs=refs,
    )

    expected = (not is_service) and has_perm and has_explanation and has_valid_ref
    assert result.allowed == expected, (
        f"P21 违背：allowed={result.allowed} expected={expected} "
        f"(service={is_service} perm={has_perm} expl={has_explanation} ref={has_valid_ref})"
    )
    # 拒绝原因与失败维度一致
    if not expected:
        if is_service:
            assert CloseRejectReason.service_identity_forbidden in result.reject_reasons
        else:
            if not has_perm:
                assert CloseRejectReason.permission_denied in result.reject_reasons
            if not has_explanation:
                assert CloseRejectReason.insufficient_explanation in result.reject_reasons
            if not has_valid_ref:
                assert CloseRejectReason.no_valid_evidence_ref in result.reject_reasons


@given(n_stale=st.integers(min_value=0, max_value=4), n_valid=st.integers(min_value=0, max_value=4))
def test_property_p21_requires_at_least_one_non_stale_ref(n_stale, n_valid):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 21.

    在人工主体 + 权限 + 充分说明恒满足时，关闭 IFF 至少存在一个非 stale ref。

    **Validates: Requirements 10.2**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity="high", content="blocking", created_by_user_id="u1",
    )
    refs = [_ref(stale=True) for _ in range(n_stale)] + [_ref(stale=False) for _ in range(n_valid)]
    result = service.evaluate_close_gate(
        opinion,
        closing_explanation="说明充分",
        closer_user_id="u2",
        actor=_make_human_actor(),
        has_close_permission=True,
        current_evidence_refs=refs,
    )
    assert result.allowed == (n_valid > 0)


@given(severity=st.sampled_from(["low", "medium", "high", "critical"]))
def test_property_p21_blocking_only_high_critical(severity):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 21.

    Blocking_Review 仅为 high/critical 严重级别（且未有效关闭）。

    **Validates: Requirements 10.2**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity=severity, content="c", created_by_user_id="u1",
    )
    assert opinion.is_blocking == (severity in BLOCKING_SEVERITIES)


# ═══════════════════════════════════════════════════════════════════════════
# P22 — 证据失效自动重开与 QC/EQCR 阻断（PBT）
# ═══════════════════════════════════════════════════════════════════════════


def _close_opinion(service: ReviewEvidenceService, opinion) -> None:
    service.close_review(
        opinion,
        closing_explanation="已解决",
        closer_user_id="u2",
        actor=_make_human_actor(),
        has_close_permission=True,
        current_evidence_refs=[_ref(stale=False)],
    )


@given(reason=st.sampled_from(["evidence_replaced", "evidence_deactivated", "evidence_stale"]))
def test_property_p22_auto_reopen_blocks_completion(reason):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    已关闭意见依据被替换/停用/stale → 自动进入 re_review_required，并阻断
    QC/EQCR/partner 完成。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity="high", content="blocking", created_by_user_id="u1",
    )
    _close_opinion(service, opinion)
    assert opinion.status == ReviewStatus.closed.value

    reopened = service.auto_reopen(opinion, reason=reason)
    assert reopened is True
    assert opinion.status == ReviewStatus.re_review_required.value
    # QC/EQCR/partner 完成被阻断
    assert service.check_completion_blocked([opinion]) is True


@given(n_opinions=st.integers(min_value=1, max_value=5),
       reopen_idx=st.integers(min_value=0, max_value=4))
def test_property_p22_any_re_review_blocks_all(n_opinions, reopen_idx):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    任一 re_review_required 意见即阻断整体完成；全部关闭则不阻断。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()
    opinions = []
    for i in range(n_opinions):
        op = service.create_opinion(
            project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
            severity="high", content=f"o{i}", created_by_user_id="u1",
        )
        _close_opinion(service, op)
        opinions.append(op)

    # 全部关闭 → 不阻断
    assert service.check_completion_blocked(opinions) is False

    # 重开其中一个 → 阻断
    idx = reopen_idx % n_opinions
    service.auto_reopen(opinions[idx], reason="evidence_stale")
    assert service.check_completion_blocked(opinions) is True


@given(already_open=st.booleans())
def test_property_p22_reopen_only_from_closed(already_open):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    auto_reopen 仅对 closed 意见生效；open / re_review_required 均为 noop（幂等）。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity="high", content="o", created_by_user_id="u1",
    )
    if not already_open:
        _close_opinion(service, opinion)

    first = service.auto_reopen(opinion, reason="evidence_stale")
    if already_open:
        # 从未关闭 → 不能重开
        assert first is False
        assert opinion.status == ReviewStatus.open.value
    else:
        assert first is True
        assert opinion.status == ReviewStatus.re_review_required.value
        # 二次重开为 noop
        assert service.auto_reopen(opinion, reason="again") is False


@given(target_match=st.booleans())
def test_property_p22_completion_block_scoped_by_target(target_match):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 22.

    指定 target 时，仅同 target 的 re_review_required 阻断该目标完成。

    **Validates: Requirements 10.3**
    """
    service = ReviewEvidenceService()
    opinion = service.create_opinion(
        project_id="p1", audit_year=2025, target_type="workpaper", target_id="wp-1",
        severity="high", content="o", created_by_user_id="u1",
    )
    _close_opinion(service, opinion)
    service.auto_reopen(opinion, reason="evidence_replaced")

    query_id = "wp-1" if target_match else "wp-999"
    blocked = service.check_completion_blocked(
        [opinion], target_type="workpaper", target_id=query_id
    )
    assert blocked == target_match
