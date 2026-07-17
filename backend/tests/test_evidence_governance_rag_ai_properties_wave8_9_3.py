"""Wave 8 — RAG/AI 属性组 PBT（Task 9.3）：逐项覆盖 P15–P19。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.3 (Wave 8)
Requirements: R7, R8, R9
Design: §3.2 CitationSnapshotService / AIEvidenceGate / FormalOutputGate,
        §4.6 Citation/AI, §5.3 RAG/AI, §11 属性 P15–P19

逐项属性（复用已实现服务，不重造引擎）:
  * P15 RAG 引用可定位 —— 纯/模型 PBT：confirmed citation 的 page(>=1)/region(非空)/
        version/hash/ref/excerpt-hash 均有效且可复算。复用真实
        CitationSnapshotService._is_locatable（纯谓词）+ frozen_contracts.sha256_hex/
        is_sha256_hex 做「可复算」判定。
  * P16 RAG 权限不扩张 —— 纯/模型 PBT：返回引用集合恒为 actor 可访问来源集合的子集。
        以过滤链模型复刻 CitationSnapshotService.create_citation_from_retrieval 语义
        （candidates ∩ readable ∩ same_scope ∩ active_ref ∩ version_valid ∩ locatable），
        证明输出 ⊆ readable，且永不引入不可读来源。
  * P17 AI 状态门禁 —— 真值 PBT + gate 集成：复用真实 FormalOutputGate（可注入 provider，
        纯逻辑无 DB）。只有人工确认 + hash 一致 + 有效证据的 AI 内容能进入 FormalOutput；
        「策略必需证据 ∪ 已有依赖」为空的历史对象不因无附件而自动违规。
  * P18 AI 入口覆盖 —— scanner PBT/契约：复用真实 compute_coverage_gap + AI_ENTRY_REGISTRY。
        discovered AI entrypoints − declared gated entrypoints 恒等于精确集合差；
        discovered ⊆ declared ⟹ 差集为空。
  * P19 已确认内容变更失效 —— 真值 PBT + gate 集成：confirmed 内容或任一已有依据变化
        （ref stale / hash 变更 / 依赖失效）后，原确认不再授权输出（FormalOutputGate FAIL）。

分工（design §10 铁律 / 任务说明）：
  * P15/P16/P18 及 P17/P19 的门禁判定为纯谓词/纯逻辑 → 纯/模型 PBT + 真实服务函数。
  * 真实 PG16 约束（citation_snapshots immutable 触发器 = P15「快照不可篡改/可复算」的
    物理保证）→ throwaway PG16 库验证；无 PG 环境 skip（SQLite 不得替代）。

常规 PBT 使用全局 fast profile（conftest 注册，默认 max_examples=5，可由
HYPOTHESIS_MAX_EXAMPLES 覆盖）；不在测试正文固定样本数。失败 counterexample 由
Hypothesis 保留。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.ai_evidence_gate import (
    AI_ENTRY_REGISTRY,
    compute_coverage_gap,
)
from app.services.evidence_governance.citation_snapshot_service import (
    CitationSnapshotService,
    RetrievalCandidate,
)
from app.services.evidence_governance.formal_output_gate import (
    BlockReasonCode,
    EvidenceItem,
    FormalOutputGate,
    GateVerdict,
    PolicyProvider,
    UnifiedGraphProvider,
)
from app.services.evidence_governance.frozen_contracts import (
    is_sha256_hex,
    sha256_hex,
)

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"


def _run(coro):
    """在同步 Hypothesis 测试体里跑协程（每次新建 loop 独立隔离）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================================================
# P15 — RAG 引用可定位（纯/模型 PBT）
# ===========================================================================
#
# 复用真实 CitationSnapshotService._is_locatable（纯谓词，不触碰 self._db）：
#   locatable ⇔ page 非空 且 page >= 1 且 region 非空。
# 并对「confirmed citation 完整可定位且可复算」建模：page/region/version/hash/
# excerpt-hash 全部有效，且 excerpt_hash == sha256(excerpt)（可复算）。


def _svc() -> CitationSnapshotService:
    # _is_locatable 不使用 db，仅需一个实例。
    return CitationSnapshotService(db=None)  # type: ignore[arg-type]


@given(
    page=st.one_of(st.none(), st.integers(min_value=-5, max_value=50)),
    region=st.one_of(
        st.none(),
        st.just({}),
        st.fixed_dictionaries({"x": st.integers(0, 10), "y": st.integers(0, 10)}),  # type: ignore[arg-type]
    ),
)
def test_property_p15_is_locatable_predicate(page, region):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15.

    可定位谓词精确等价：candidate 可定位 ⇔ page 非空且 >= 1 且 region 非空（页级 +
    区域边界保留，绝不以缺失位置的切片作为正式引用）。

    **Validates: Requirements 7.1, 7.4**
    """
    candidate = RetrievalCandidate(
        source_type="attachment_version",
        source_id="s1",
        page=page,
        region=region,
    )
    expected = page is not None and page >= 1 and bool(region)
    assert _svc()._is_locatable(candidate) is expected


def _confirmed_citation_valid(c: dict) -> bool:
    """confirmed citation 完整可定位且可复算的模型谓词（R7.1/R7.3）。

    要求：page>=1、region 非空、version 非空、content_hash 为合法 sha256、
    active ref、excerpt 非空且 excerpt_hash 可由 excerpt 复算一致。
    """
    if not (isinstance(c.get("page"), int) and c["page"] >= 1):
        return False
    if not c.get("region"):
        return False
    if not c.get("version"):
        return False
    if not is_sha256_hex(c.get("content_hash")):
        return False
    if not c.get("ref_active"):
        return False
    excerpt = c.get("excerpt")
    if not excerpt:
        return False
    # 可复算：存储的 excerpt_hash 必须 == 当前 excerpt 的 sha256。
    return c.get("excerpt_hash") == sha256_hex(excerpt)


@given(
    page=st.integers(min_value=1, max_value=40),
    version=st.text(min_size=1, max_size=8),
    excerpt=st.text(min_size=1, max_size=40),
    ref_active=st.booleans(),
    tamper=st.booleans(),
)
def test_property_p15_confirmed_citation_recomputable(
    page, version, excerpt, ref_active, tamper
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15.

    confirmed citation 的 page/region/version/hash/ref/excerpt-hash 均有效且可复算：
    正确构造时谓词为真；任一维度失效（ref 停用 / excerpt_hash 被篡改）→ 谓词为假。

    **Validates: Requirements 7.1, 7.3**
    """
    good_excerpt_hash = sha256_hex(excerpt)
    citation = {
        "page": page,
        "region": {"x": 1, "y": 2, "w": 3, "h": 4},
        "version": version,
        "content_hash": sha256_hex(version + excerpt),  # 合法 sha256
        "ref_active": ref_active,
        "excerpt": excerpt,
        "excerpt_hash": (good_excerpt_hash[::-1] if tamper else good_excerpt_hash),
    }

    valid = _confirmed_citation_valid(citation)
    # 当且仅当 ref active 且 excerpt_hash 未被篡改（可复算）时有效。
    hash_recomputable = citation["excerpt_hash"] == good_excerpt_hash
    assert valid == (ref_active and hash_recomputable)

    # 可复算铁律：从 excerpt 复算 hash 恒等于 good_excerpt_hash。
    assert sha256_hex(excerpt) == good_excerpt_hash


# ===========================================================================
# P16 — RAG 权限不扩张（纯/模型 PBT）
# ===========================================================================
#
# 过滤链模型复刻 create_citation_from_retrieval：输出恒为
#   candidates ∩ locatable ∩ same_scope ∩ readable ∩ active_ref ∩ version_valid。
# P16 断言：输出 ⊆ readable（actor 可访问集合），永不通过 RAG 扩张权限。


def _filter_citations(candidates: list[dict]) -> list[dict]:
    """复刻 CitationSnapshotService 过滤链（顺序无关的合取过滤）。"""
    out: list[dict] = []
    for c in candidates:
        if not c["locatable"]:
            continue
        if not c["same_scope"]:
            continue
        if not c["readable"]:  # P16：不可读来源绝不进入结果
            continue
        if not c["active_ref"]:
            continue
        if not c["version_valid"]:
            continue
        out.append(c)
    return out


_CANDIDATE = st.builds(
    lambda i, lo, sc, rd, ar, vv: {
        "id": i,
        "locatable": lo,
        "same_scope": sc,
        "readable": rd,
        "active_ref": ar,
        "version_valid": vv,
    },
    i=st.uuids(),
    lo=st.booleans(),
    sc=st.booleans(),
    rd=st.booleans(),
    ar=st.booleans(),
    vv=st.booleans(),
)


@given(candidates=st.lists(_CANDIDATE, max_size=12, unique_by=lambda c: c["id"]))
def test_property_p16_citation_subset_of_accessible(candidates):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 16.

    返回引用集合恒为 actor 可访问（readable）来源集合的子集，且永不引入不可读来源
    （不通过 RAG 扩张权限）。

    **Validates: Requirements 7.2**
    """
    result = _filter_citations(candidates)
    result_ids = {c["id"] for c in result}
    accessible_ids = {c["id"] for c in candidates if c["readable"]}

    # P16：输出 ⊆ 可访问集合。
    assert result_ids <= accessible_ids
    # 结果里每一条都可读、同 scope、active ref、版本有效、可定位。
    for c in result:
        assert c["readable"] and c["same_scope"] and c["active_ref"]
        assert c["version_valid"] and c["locatable"]
    # 不可读来源恒被排除。
    for c in candidates:
        if not c["readable"]:
            assert c["id"] not in result_ids


@given(candidates=st.lists(_CANDIDATE, max_size=12, unique_by=lambda c: c["id"]))
def test_property_p16_no_amplification_monotone(candidates):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 16.

    把任一来源标记为不可读只会缩小结果，绝不扩大（权限不扩张的单调性）。

    **Validates: Requirements 7.2**
    """
    base = {c["id"] for c in _filter_citations(candidates)}
    for idx in range(len(candidates)):
        mutated = [dict(c) for c in candidates]
        mutated[idx]["readable"] = False
        after = {c["id"] for c in _filter_citations(mutated)}
        assert after <= base


# ===========================================================================
# P17 — AI 状态门禁（真值 PBT + 真实 FormalOutputGate 集成）
# ===========================================================================


class _FakePolicy(PolicyProvider):
    def __init__(self, items: list[EvidenceItem], version: str | None = "v1") -> None:
        self._items = items
        self._version = version

    async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
        return list(self._items)

    async def get_policy_version(self, target_id, target_type):
        return self._version


class _FakeGraph(UnifiedGraphProvider):
    def __init__(self, items: list[EvidenceItem]) -> None:
        self._items = items

    async def get_existing_dependencies(self, target_id, target_type):
        return list(self._items)


def _gate(policy_items=None, dep_items=None) -> FormalOutputGate:
    return FormalOutputGate(
        policy_provider=_FakePolicy(policy_items or []),
        graph_provider=_FakeGraph(dep_items or []),
    )


@given(confirmed=st.booleans(), hash_consistent=st.booleans(), stale=st.booleans())
def test_property_p17_ai_content_gate(confirmed, hash_consistent, stale):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17.

    只有人工确认 + hash 一致且非 stale 的 AI 内容才可进入 FormalOutput；未确认 /
    hash 变化 / stale 任一成立即阻断（真实 FormalOutputGate 判定）。

    **Validates: Requirements 8.3**
    """
    ai_item = EvidenceItem(
        evidence_id="ai-1",
        evidence_type="ai_content",
        source="policy",
        ai_human_confirmed=confirmed,
        ai_hash_consistent=hash_consistent,
        is_stale=stale,
    )
    result = _run(_gate(policy_items=[ai_item]).preflight("t1", "workpaper_conclusion"))

    expected_pass = confirmed and hash_consistent and not stale
    assert result.passed is expected_pass

    codes = {r.code for r in result.blocking_reasons}
    if not confirmed:
        assert BlockReasonCode.AI_NOT_CONFIRMED in codes
    if not hash_consistent:
        assert BlockReasonCode.AI_HASH_CHANGED in codes
    if stale:
        assert BlockReasonCode.STALE_EVIDENCE in codes


def test_property_p17_historical_no_attachment_not_violation():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17.

    「策略必需证据 ∪ 已有依赖」为空的历史对象不因缺附件自动违规：RequiredEvidence
    为空 → gate PASS，无 MISSING_REQUIRED_EVIDENCE。

    **Validates: Requirements 8.3**
    """
    result = _run(_gate(policy_items=[], dep_items=[]).preflight("hist", "report"))
    assert result.passed is True
    assert result.evidence_count == 0
    codes = {r.code for r in result.blocking_reasons}
    assert BlockReasonCode.MISSING_REQUIRED_EVIDENCE not in codes


@given(
    n_policy=st.integers(min_value=0, max_value=4),
    n_dep=st.integers(min_value=0, max_value=4),
    n_overlap=st.integers(min_value=0, max_value=3),
)
def test_property_p17_required_evidence_union(n_policy, n_dep, n_overlap):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 17.

    RequiredEvidence = 策略必需证据 ∪ 已有依赖（按 evidence_id 去重）：评估证据数 =
    两集合并集大小。全部有效证据 → gate PASS。

    **Validates: Requirements 8.3**
    """
    n_overlap = min(n_overlap, n_policy, n_dep)

    def _ok_item(eid: str, source: str) -> EvidenceItem:
        # attachment 版本类证据，全部合规（不触发任何 P0 阻断）。
        return EvidenceItem(
            evidence_id=eid,
            evidence_type="attachment_version",
            source=source,
            metadata_complete=True,
            has_actor=True,
            is_active_ref=True,
            is_stale=False,
        )

    policy_ids = [f"e{i}" for i in range(n_policy)]
    # 让前 n_overlap 个 dep 与 policy 重叠。
    dep_ids = policy_ids[:n_overlap] + [f"d{i}" for i in range(n_dep - n_overlap)]

    policy_items = [_ok_item(e, "policy") for e in policy_ids]
    dep_items = [_ok_item(e, "dependency") for e in dep_ids]

    expected_unique = len(set(policy_ids) | set(dep_ids))

    result = _run(
        _gate(policy_items=policy_items, dep_items=dep_items).preflight(
            "t2", "disclosure_note"
        )
    )
    assert result.evidence_count == expected_unique
    assert result.passed is True


# ===========================================================================
# P18 — AI 入口覆盖（scanner PBT / 契约，复用真实 compute_coverage_gap）
# ===========================================================================


@given(
    subset=st.sets(st.sampled_from(sorted(AI_ENTRY_REGISTRY))),
    extras=st.sets(st.text(min_size=1, max_size=12).filter(lambda s: s not in AI_ENTRY_REGISTRY)),
)
def test_property_p18_coverage_gap_exact_difference(subset, extras):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 18.

    coverage gap 恒等于精确集合差 discovered − declared：
      * discovered ⊆ declared ⟹ gap = ∅（P18 恒为空）。
      * discovered 含未登记入口 ⟹ gap 精确等于这些未登记入口。

    **Validates: Requirements 8.2**
    """
    # 仅声明集内的入口 → 差集必为空。
    assert compute_coverage_gap(set(subset), AI_ENTRY_REGISTRY) == set()

    # 加入未登记入口 → 差集精确等于这些未登记项。
    discovered = set(subset) | set(extras)
    gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)
    assert gap == set(extras)
    assert gap == discovered - set(AI_ENTRY_REGISTRY)


@given(
    discovered=st.sets(st.text(min_size=1, max_size=12), max_size=8),
    declared=st.sets(st.text(min_size=1, max_size=12), max_size=8),
)
def test_property_p18_gap_pure_set_difference(discovered, declared):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 18.

    compute_coverage_gap 对任意集合都是纯集合差；gap 与 declared 不相交，且 gap 空
    当且仅当 discovered ⊆ declared。

    **Validates: Requirements 8.2**
    """
    gap = compute_coverage_gap(discovered, declared)
    assert gap == discovered - declared
    assert gap.isdisjoint(declared)
    assert (gap == set()) == discovered.issubset(declared)


def test_property_p18_default_registry_is_full_declared_set():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 18.

    未显式传 declared 时默认对齐 AI_ENTRY_REGISTRY；已登记入口集自身差集为空。

    **Validates: Requirements 8.2**
    """
    assert compute_coverage_gap(set(AI_ENTRY_REGISTRY)) == set()
    # 显式传 registry 与默认一致。
    assert compute_coverage_gap(set(AI_ENTRY_REGISTRY), AI_ENTRY_REGISTRY) == set()


# ===========================================================================
# P19 — 已确认内容变更失效（真值 PBT + 真实 FormalOutputGate 集成）
# ===========================================================================


def _confirmation_authorizes(confirmed: bool, dependency_changed: bool) -> bool:
    """模型：原确认授权输出 ⇔ 已确认 且 无任一已有依据变化。"""
    return confirmed and not dependency_changed


@given(confirmed=st.booleans(), dependency_changed=st.booleans())
def test_property_p19_confirmation_invalidated_on_change_model(confirmed, dependency_changed):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 19.

    confirmed 内容或任一已有依据变化后，原确认不再授权输出：只要发生依据变化，
    无论此前是否确认，授权谓词恒为假。

    **Validates: Requirements 8.3, 9.1**
    """
    authorizes = _confirmation_authorizes(confirmed, dependency_changed)
    if dependency_changed:
        assert authorizes is False
    else:
        assert authorizes is confirmed


@given(
    change=st.sampled_from(["stale", "hash_changed", "ref_inactive"]),
)
def test_property_p19_gate_blocks_after_dependency_change(change):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 19.

    已进入依赖的 AI 内容，其依据变化（stale / hash 变更 / ref 停用）后 FormalOutputGate
    FAIL —— 原确认不再授权输出（真实 gate 判定）。

    **Validates: Requirements 8.3, 9.1**
    """
    # 基线：曾人工确认 + hash 一致 + active ref + 非 stale（可授权）。
    base = dict(
        evidence_id="ai-19",
        evidence_type="ai_content",
        source="dependency",
        ai_human_confirmed=True,
        ai_hash_consistent=True,
        is_active_ref=True,
        is_stale=False,
    )
    # 基线可通过。
    base_result = _run(_gate(dep_items=[EvidenceItem(**base)]).preflight("t3", "signoff"))
    assert base_result.passed is True

    # 施加一种依据变化。
    changed = dict(base)
    expected_code: BlockReasonCode
    if change == "stale":
        changed["is_stale"] = True
        expected_code = BlockReasonCode.STALE_EVIDENCE
    elif change == "hash_changed":
        changed["ai_hash_consistent"] = False
        expected_code = BlockReasonCode.AI_HASH_CHANGED
    else:  # ref_inactive
        changed["is_active_ref"] = False
        expected_code = BlockReasonCode.REF_INACTIVE

    result = _run(_gate(dep_items=[EvidenceItem(**changed)]).preflight("t3", "signoff"))
    assert result.passed is False
    assert expected_code in {r.code for r in result.blocking_reasons}


@given(
    confirmed=st.booleans(),
    hash_consistent=st.booleans(),
)
def test_property_p19_original_confirmation_not_reused_when_hash_changes(
    confirmed, hash_consistent
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 19.

    即便曾人工确认，只要内容 hash 不再一致（内容/依据变化），原确认不再授权输出。

    **Validates: Requirements 8.3, 9.1**
    """
    item = EvidenceItem(
        evidence_id="ai-h",
        evidence_type="ai_content",
        source="policy",
        ai_human_confirmed=confirmed,
        ai_hash_consistent=hash_consistent,
    )
    result = _run(_gate(policy_items=[item]).preflight("t4", "eqcr_conclusion"))
    # 只有「确认 且 hash 一致」才可授权。
    assert result.passed is (confirmed and hash_consistent)


# ===========================================================================
# 真实 PG16：citation_snapshots immutable 触发器（P15/P16 快照可复算的物理保证）
# ===========================================================================
#
# design §4.6：CitationSnapshot 不可变（immutable 触发器禁止 UPDATE），打开时重新鉴权。
# 这是 P15「引用可定位且可复算」的 DB 层保证：快照一旦创建，其 page/region/version/hash
# 不可被篡改。无真实 PG16 环境 skip（SQLite 不得替代）。

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


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
    tmp_db = f"evgov_rag_p15_19_{uuid.uuid4().hex[:12]}"

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


async def _seed_citation(eng) -> dict:
    """seed user + project + ai_content_log + evidence_ref + citation_snapshot。"""
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "project": uuid.uuid4(),
        "ai_log": uuid.uuid4(),
        "ref": uuid.uuid4(),
        "citation": uuid.uuid4(),
        "content_hash": "a" * 64,
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
        await conn.execute(
            T("INSERT INTO projects (id, audit_year) VALUES (:i, 2025)"),
            {"i": ids["project"]},
        )
        await conn.execute(
            T("INSERT INTO ai_content_log (id, project_id) VALUES (:i, :p)"),
            {"i": ids["ai_log"], "p": ids["project"]},
        )
        await conn.execute(
            T(
                "INSERT INTO evidence_refs "
                "(id, project_id, audit_year, source_type, source_id, evidence_type, "
                " evidence_id, intent_hash, status, actor_type, actor_user_id) "
                "VALUES (:i, :p, 2025, 'workpaper_cell', 's1', 'attachment_version', "
                " 'e1', :h, 'active', 'user', :u)"
            ),
            {"i": ids["ref"], "p": ids["project"], "h": ids["content_hash"], "u": ids["user"]},
        )
        await conn.execute(
            T(
                "INSERT INTO citation_snapshots "
                "(id, ai_content_log_id, evidence_ref_id, project_id, audit_year, "
                " target_version, target_hash, page, region, excerpt_hash, "
                " index_version, locator_version, actor_type, actor_user_id) "
                "VALUES (:i, :ai, :ref, :p, 2025, "
                " '1', :h, 3, CAST(:region AS jsonb), :eh, "
                " 'idx-v1', 'loc-v1', 'user', :u)"
            ),
            {
                "i": ids["citation"],
                "ai": ids["ai_log"],
                "ref": ids["ref"],
                "p": ids["project"],
                "h": ids["content_hash"],
                "region": '{"x":1,"y":2,"w":3,"h":4}',
                "eh": sha256_hex("excerpt-text"),
                "u": ids["user"],
            },
        )
    return ids


@pytest.mark.asyncio
async def test_property_p15_citation_snapshot_immutable_trigger():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15.

    真实 PG16：citation_snapshots 的 immutable 触发器拒绝任何 UPDATE —— confirmed
    citation 的 page/region/version/hash/locator 不可被篡改（可复算/可定位的物理保证）。

    **Validates: Requirements 7.1, 7.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（immutable 触发器不可用 SQLite 替代）")

    async with _throwaway_engine() as eng:
        ids = await _seed_citation(eng)

        # 任何 UPDATE 都必须被 immutable 触发器拒绝。
        from sqlalchemy.ext.asyncio import async_sessionmaker

        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as session:
            with pytest.raises(Exception) as exc_info:
                await session.execute(
                    sa.text("UPDATE citation_snapshots SET page = 99 WHERE id = :i"),
                    {"i": ids["citation"]},
                )
                await session.commit()
            assert "不可变" in str(exc_info.value) or "append-only" in str(exc_info.value)

        # 原始定位信息未变（page/region/hash 可复算不漂移）。
        async with SM() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT page, target_version, target_hash, excerpt_hash "
                        "FROM citation_snapshots WHERE id = :i"
                    ),
                    {"i": ids["citation"]},
                )
            ).one()
            assert row[0] == 3
            assert row[1] == "1"
            assert row[2] == "a" * 64
            assert row[3] == sha256_hex("excerpt-text")
