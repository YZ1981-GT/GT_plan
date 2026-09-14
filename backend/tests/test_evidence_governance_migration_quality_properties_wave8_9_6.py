"""Wave 8 — migration-quality 属性组 PBT（Task 9.6）：逐项覆盖 P28 / P29 / P30。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.6 (Wave 8)
Requirements: R14, R15, R16
Design: §8.2 M0–M4/backfill、§5.3 FormalOutputGate 降级、§9 质量快照、§P28/P29/P30

逐项：
  - **P28 迁移幂等守恒**：迁移中断/重跑不增加逻辑对象、不改变历史字节与业务内容。
      纯 PBT：``build_backfill_aggregates`` 对同一固定行集合的守恒/幂等/顺序无关；
      真实 PG16 crash-point：backfill 批中崩溃 → 已提交批保留、崩溃批回滚 → 续跑补齐 →
      对象基数与一次完整回填一致，再跑零新增，legacy 字节/列不变。
  - **P29 降级安全**：storage/OCR/retrieval/AI 失败、超时、stub、不可验证 → FormalOutputGate
      preflight/finalize 恒 FAIL 且 degraded，绝不产生 confirmed/written_back/archived 终态。
  - **P30 固定快照质量指标可复算**：固定不可变快照重复计算得到完全相同的 metrics/账龄桶/
      问题清单/业务结论；输出与记录顺序无关。P30 独立于 UAT-15（固定快照，非在线容量数据）。

常规 PBT 用 ``backend/tests/conftest.py`` 全局 fast profile（默认 max_examples=5，可由
``HYPOTHESIS_MAX_EXAMPLES`` env 覆盖）；不在测试正文固定样本数。真实 PG16 约束/并发/事务
回滚只在 PostgreSQL 16 验证，无 PG 时 skip；不以 SQLite 代替。保留失败 counterexample。
"""

from __future__ import annotations

import asyncio
import random
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.backfill_runner import (
    EvidenceBackfillRunner,
    build_backfill_aggregates,
    compute_input_hash,
)
from app.services.evidence_governance.formal_output_gate import (
    BlockReasonCode,
    ExternalDependencyChecker,
    ExternalDependencyStatus,
    FormalOutputGate,
    GatePhase,
    GateVerdict,
    PolicyProvider,
    UnifiedGraphProvider,
)
from app.services.evidence_governance.quality_snapshot import (
    AGING_BUCKET_KEYS,
    build_snapshot_input_hash,
    compute_quality_snapshot,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


def _run(coro):
    """在同步 @given 测试体内运行 async 协程（FormalOutputGate 无 DB，纯内存）。"""
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# P28 迁移幂等守恒 — 纯 PBT（build_backfill_aggregates 守恒 / 幂等 / 顺序无关）
# ═══════════════════════════════════════════════════════════════════════════


def _row(rid, prev=None, version=1, project="P", year=2025):
    return {
        "id": rid,
        "project_id": project,
        "audit_year": year,
        "version": version,
        "previous_version_id": prev,
    }


def _gen_rows(n: int, seed: int) -> list[dict]:
    """随机生成 legacy 行集合：prev = None / 指向前一行 / 悬空。"""
    rng = random.Random(seed)
    ids = [uuid.uuid4() for _ in range(n)]
    rows = []
    for i, rid in enumerate(ids):
        choice = rng.randint(0, 2)
        if choice == 0 or i == 0:
            prev = None
        elif choice == 1:
            prev = ids[rng.randint(0, i - 1)]
        else:
            prev = uuid.uuid4()  # 悬空
        rows.append(_row(rid, prev=prev, version=rng.randint(1, 5)))
    return rows


def _version_id_multiset(aggs) -> list[str]:
    return sorted(str(v["id"]) for a in aggs for v in a.versions)


@settings(deadline=None)
@given(n=st.integers(min_value=1, max_value=10), seed=st.integers(min_value=0, max_value=10_000))
def test_property_p28_aggregation_conserves_logical_objects(n, seed):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 28.

    迁移幂等守恒（纯）：对同一固定行集合聚合 → 每个输入逻辑对象恰好出现一次
    （不增不减不重）；这是"重跑不增加逻辑对象"的纯不变式基础。
    """
    rows = _gen_rows(n, seed)
    input_ids = sorted(str(r["id"]) for r in rows)
    aggs = build_backfill_aggregates(rows)
    assert _version_id_multiset(aggs) == input_ids


@settings(deadline=None)
@given(n=st.integers(min_value=1, max_value=10), seed=st.integers(min_value=0, max_value=10_000))
def test_property_p28_aggregation_idempotent_and_order_independent(n, seed):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 28.

    重跑/乱序守恒：重复聚合结果一致；打乱输入顺序，聚合的逻辑对象集合与分组不变
    （确定性 → 重跑不产生新逻辑对象）。
    """
    rows = _gen_rows(n, seed)
    a1 = build_backfill_aggregates(list(rows))
    a2 = build_backfill_aggregates(list(rows))
    # 幂等：两次结果完全一致
    assert [[str(v["id"]) for v in a.versions] for a in a1] == [
        [str(v["id"]) for v in a.versions] for a in a2
    ]
    # 顺序无关：打乱输入后逻辑对象集合守恒
    shuffled = list(rows)
    random.Random(seed + 1).shuffle(shuffled)
    a3 = build_backfill_aggregates(shuffled)
    assert _version_id_multiset(a1) == _version_id_multiset(a3)
    # input_hash 顺序无关
    ids = [r["id"] for r in rows]
    assert compute_input_hash(ids) == compute_input_hash(list(reversed(ids)))


# ═══════════════════════════════════════════════════════════════════════════
# P28 迁移幂等守恒 — 真实 PG16 crash-point 集成
# ═══════════════════════════════════════════════════════════════════════════


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
    tmp_db = f"evgov_p28_{uuid.uuid4().hex[:12]}"

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


async def _seed_singletons(eng, n: int):
    """seed n 个独立单件 legacy attachment（同 project/year），返回 (project_id, [ids])。"""
    from sqlalchemy import text as T

    user = uuid.uuid4()
    proj = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(n)]
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": user})
        await conn.execute(
            T("INSERT INTO projects (id, audit_period_end) VALUES (:i, DATE '2025-12-31')"),
            {"i": proj},
        )
        for k, aid in enumerate(ids):
            await conn.execute(
                T(
                    "INSERT INTO attachments (id, project_id, file_name, file_path, file_type,"
                    " file_size, storage_type, ocr_status, version, created_by) "
                    "VALUES (:a,:p,:fn,:fp,'pdf',:sz,'local','pending',1,:cb)"
                ),
                {
                    "a": aid, "p": proj, "fn": f"f{k}.pdf",
                    "fp": f"/abs/secret/{aid}.pdf", "sz": 100 + k, "cb": user,
                },
            )
    await _apply_all(eng)
    return proj, ids


class _CrashingRunner(EvidenceBackfillRunner):
    """在处理到第 ``crash_after`` 个聚合时抛异常，模拟迁移中断。"""

    def __init__(self, *a, crash_after: int, **kw):
        super().__init__(*a, **kw)
        self._crash_after = crash_after
        self._done = 0

    async def _backfill_aggregate(self, agg, report):  # type: ignore[override]
        if self._done >= self._crash_after:
            raise RuntimeError("simulated migration crash mid-batch")
        self._done += 1
        return await super()._backfill_aggregate(agg, report)


async def _counts(eng):
    from sqlalchemy import text as T

    async with eng.connect() as conn:
        av = (await conn.execute(T("SELECT count(*) FROM attachment_versions"))).scalar()
        al = (await conn.execute(T("SELECT count(*) FROM legacy_attachment_alias"))).scalar()
        cp = (await conn.execute(T("SELECT count(*) FROM evidence_migration_checkpoints WHERE status='done'"))).scalar()
        sizes = (await conn.execute(T("SELECT id, file_size FROM attachments ORDER BY id"))).all()
    return av, al, cp, {str(r[0]): r[1] for r in sizes}


@pytest.mark.asyncio
async def test_property_p28_crash_point_resume_conserves_objects():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 28.

    真实 PG16 crash-point：backfill 批处理中崩溃 → 已提交批保留、崩溃批整体回滚；
    续跑补齐后对象基数 == 一次完整回填的基数（不多不少），再次重跑零新增，
    legacy 字节/列不变（迁移中断/重跑不增加逻辑对象、不改历史字节）。
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    n = 7  # 7 个单件 → batch_size=2 → 4 批（2,2,2,1）
    async with _throwaway_db() as eng:
        proj, ids = await _seed_singletons(eng, n)
        legacy_sizes = {str(i): 100 + k for k, i in enumerate(ids)}

        # 崩溃点：处理 3 个聚合后崩（第 2 批中途）→ 前 1 批（2 个）已提交，崩溃批回滚。
        with pytest.raises(RuntimeError):
            async with _session(eng) as db:
                await _CrashingRunner(db, batch_size=2, crash_after=3).run(proj)

        av_c, al_c, cp_c, sizes_c = await _counts(eng)
        # 崩溃后：已提交的批保留（>0），但未达全量；legacy 字节不变。
        assert 0 < av_c < n
        assert av_c == al_c
        assert sizes_c == legacy_sizes, "崩溃不得改变历史字节（P28）"

        # 续跑（新 runner / 新 session）→ 补齐剩余。
        async with _session(eng) as db:
            r_resume = await EvidenceBackfillRunner(db, batch_size=2).run(proj)
        av_r, al_r, cp_r, sizes_r = await _counts(eng)
        assert av_r == n and al_r == n
        assert r_resume.versions_created == (n - av_c)  # 只补差额
        assert sizes_r == legacy_sizes

        # 再次重跑 → 零新增（幂等守恒）。
        async with _session(eng) as db:
            r_again = await EvidenceBackfillRunner(db, batch_size=2).run(proj)
        av_2, al_2, cp_2, sizes_2 = await _counts(eng)
        assert r_again.versions_created == 0 and r_again.aliases_created == 0
        assert (av_2, al_2) == (n, n)
        assert sizes_2 == legacy_sizes


@pytest.mark.asyncio
async def test_property_p28_full_run_matches_object_count_baseline():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 28.

    真实 PG16 基线：一次完整（无崩溃）回填 n 个单件 → 恰 n 个 AttachmentVersion + n 个 alias。
    与 crash-resume 路径的最终基数一致（守恒的对照基线）。
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    n = 7
    async with _throwaway_db() as eng:
        proj, ids = await _seed_singletons(eng, n)
        async with _session(eng) as db:
            report = await EvidenceBackfillRunner(db, batch_size=2).run(proj)
        av, al, cp, sizes = await _counts(eng)
        assert report.versions_created == n
        assert (av, al) == (n, n)


# ═══════════════════════════════════════════════════════════════════════════
# P29 降级安全 — FormalOutputGate 故障 PBT（外部依赖失败 → 无终态）
# ═══════════════════════════════════════════════════════════════════════════

_DEP_NAMES = ("storage", "ocr", "retrieval", "ai")
#: stub/超时/不可验证均建模为 available=False + 描述性 error。
_DEGRADE_ERRORS = ("failure", "timeout", "stub", "unverifiable")


class _DegradedDepChecker(ExternalDependencyChecker):
    """指定子集的外部依赖不可用（其余可用）。"""

    def __init__(self, unavailable: dict[str, str]):
        # unavailable: name -> error(failure/timeout/stub/unverifiable)
        self._unavailable = unavailable

    async def check_dependencies(self):
        return [
            ExternalDependencyStatus(
                name=name,
                available=name not in self._unavailable,
                error=self._unavailable.get(name),
            )
            for name in _DEP_NAMES
        ]


class _AllHealthyChecker(ExternalDependencyChecker):
    async def check_dependencies(self):
        return [ExternalDependencyStatus(name=n, available=True) for n in _DEP_NAMES]


def _degraded_subsets():
    """非空的降级子集 + 每个降级依赖一种失败模式。"""
    return st.dictionaries(
        keys=st.sampled_from(_DEP_NAMES),
        values=st.sampled_from(_DEGRADE_ERRORS),
        min_size=1,
        max_size=len(_DEP_NAMES),
    )


@settings(deadline=None)
@given(unavailable=_degraded_subsets(), target_type=st.sampled_from(sorted(
    {"workpaper_conclusion", "disclosure_note", "report", "signoff", "qc_conclusion",
     "eqcr_conclusion", "deliverable", "archive"}
)))
def test_property_p29_degraded_dependency_never_reaches_terminal(unavailable, target_type):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 29.

    降级安全：任一 storage/OCR/retrieval/AI 失败/超时/stub/不可验证时，
    FormalOutputGate preflight 与 finalize 恒 FAIL 且 degraded=True，
    绝不产生 confirmed/written_back/archived 终态（fail-closed）。
    """
    gate = FormalOutputGate(dependency_checker=_DegradedDepChecker(unavailable))
    target_id = "t-" + uuid.uuid4().hex[:8]

    pre = _run(gate.preflight(target_id, target_type))
    assert pre.verdict == GateVerdict.FAIL
    assert pre.degraded is True
    assert not pre.passed
    assert any(r.code == BlockReasonCode.DEPENDENCY_DEGRADED for r in pre.blocking_reasons)

    # finalize（即便给任意 watermark）仍 fail-closed，不放行终态。
    fin = _run(gate.finalize(target_id, target_type, preflight_watermark="whatever"))
    assert fin.verdict == GateVerdict.FAIL
    assert fin.degraded is True
    assert not fin.passed
    assert fin.phase == GatePhase.FINALIZE


@settings(deadline=None)
@given(target_type=st.sampled_from(["archive", "report", "signoff", "deliverable"]))
def test_property_p29_healthy_empty_evidence_passes_control(target_type):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 29 (control).

    对照：全部依赖健康且无策略必需证据/依赖时，gate PASS —— 证明 P29 的 FAIL 由降级导致，
    而非 gate 恒 FAIL（避免 vacuous / fake-green）。历史无附件本身不违规。
    """
    gate = FormalOutputGate(
        policy_provider=PolicyProvider(),          # 默认返回空策略证据
        graph_provider=UnifiedGraphProvider(),      # 默认返回空已有依赖
        dependency_checker=_AllHealthyChecker(),
    )
    target_id = "t-" + uuid.uuid4().hex[:8]
    pre = _run(gate.preflight(target_id, target_type))
    assert pre.verdict == GateVerdict.PASS
    assert pre.degraded is False
    fin = _run(gate.finalize(target_id, target_type, preflight_watermark=pre.watermark))
    assert fin.verdict == GateVerdict.PASS
    assert fin.degraded is False


# ═══════════════════════════════════════════════════════════════════════════
# P30 固定快照质量指标可复算 — 独立固定快照 PBT
# ═══════════════════════════════════════════════════════════════════════════

_EVIDENCE_TYPES = ("attachment_version", "ocr_result", "ai_content", "citation", "ref")


@st.composite
def _quality_record(draw):
    etype = draw(st.sampled_from(_EVIDENCE_TYPES))
    has_version = draw(st.booleans())
    return {
        "id": "e-" + uuid.uuid4().hex[:10],
        "evidence_type": etype,
        "has_actor": draw(st.booleans()),
        "content_hash": draw(st.one_of(st.none(), st.just("a" * 64))),
        "version": (draw(st.integers(min_value=1, max_value=9)) if has_version else None),
        "is_active_ref": draw(st.booleans()),
        "unverified_chain": draw(st.booleans()),
        "is_stale": draw(st.booleans()),
        "ocr_confirmed": draw(st.one_of(st.none(), st.booleans())),
        "ai_human_confirmed": draw(st.one_of(st.none(), st.booleans())),
        "citation_locatable": draw(st.one_of(st.none(), st.booleans())),
        "age_days": draw(st.integers(min_value=0, max_value=800)),
    }


def _fixed_payload(records):
    return {
        "scope": {"project_id": str(uuid.uuid4()), "audit_year": 2025},
        "as_of_day": 20250,
        "records": records,
    }


@settings(deadline=None)
@given(records=st.lists(_quality_record(), max_size=15))
def test_property_p30_recompute_is_identical(records):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 30.

    固定快照重复计算 → 完全相同的 metrics/账龄桶/问题清单/业务结论/input_hash。
    """
    payload = _fixed_payload(records)
    r1 = compute_quality_snapshot(payload)
    r2 = compute_quality_snapshot(payload)
    assert r1.metrics == r2.metrics
    assert r1.aging_buckets == r2.aging_buckets
    assert r1.issue_list == r2.issue_list
    assert r1.business_conclusion == r2.business_conclusion
    assert r1.input_hash == r2.input_hash
    assert r1.snapshot_key == r2.snapshot_key


@settings(deadline=None)
@given(records=st.lists(_quality_record(), min_size=1, max_size=15), seed=st.integers(0, 10_000))
def test_property_p30_order_independent(records, seed):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 30.

    输出与记录输入顺序无关（快照可复算不依赖采集顺序）：打乱 records → 指标/桶/问题清单/
    结论/input_hash 全部一致。
    """
    payload = _fixed_payload(records)
    base = compute_quality_snapshot(payload)

    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    perm = compute_quality_snapshot(_fixed_payload_same_scope(payload, shuffled))

    assert base.metrics == perm.metrics
    assert base.aging_buckets == perm.aging_buckets
    assert base.issue_list == perm.issue_list
    assert base.business_conclusion == perm.business_conclusion
    assert base.input_hash == perm.input_hash


def _fixed_payload_same_scope(payload, records):
    """复用同一 scope/as_of_day，仅替换（打乱后的）records。"""
    return {
        "scope": payload["scope"],
        "as_of_day": payload["as_of_day"],
        "records": records,
    }


@settings(deadline=None)
@given(records=st.lists(_quality_record(), max_size=15))
def test_property_p30_metrics_and_buckets_are_conserved(records):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 30.

    守恒不变式：账龄桶计数之和 == 总记录数；桶键恰为固定集合；
    business_conclusion 由指标确定性派生（archive_ready ⇔ blocking_records==0），不改结论。
    """
    payload = _fixed_payload(records)
    r = compute_quality_snapshot(payload)

    assert set(r.aging_buckets.keys()) == set(AGING_BUCKET_KEYS)
    assert sum(r.aging_buckets.values()) == len(records)
    assert r.metrics["total_records"] == len(records)
    # 业务结论与阻断记录一致（确定性派生）
    assert r.business_conclusion["archive_ready"] == (r.metrics["blocking_records"] == 0)
    if r.metrics["blocking_records"] > 0:
        assert r.business_conclusion["grade"] == "blocked"
    elif r.metrics["unverified_chain"] > 0:
        assert r.business_conclusion["grade"] == "advisory"
    else:
        assert r.business_conclusion["grade"] == "clean"


def test_property_p30_fixed_snapshot_golden_example():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 30.

    固定不可变金样：给定确定输入，指标/桶/问题清单/结论/哈希为已知固定值 —— 证明可复算
    独立于在线容量数据（P30 独立于 UAT-15）。
    """
    payload = {
        "scope": {"project_id": "11111111-1111-1111-1111-111111111111", "audit_year": 2025},
        "as_of_day": 20250,
        "records": [
            {"id": "a1", "evidence_type": "attachment_version", "has_actor": True,
             "content_hash": "b" * 64, "version": 1, "is_active_ref": True,
             "unverified_chain": False, "is_stale": False, "age_days": 10},
            {"id": "a2", "evidence_type": "ocr_result", "has_actor": True,
             "content_hash": "c" * 64, "version": 1, "is_active_ref": True,
             "ocr_confirmed": False, "age_days": 200},
            {"id": "a3", "evidence_type": "attachment_version", "has_actor": False,
             "content_hash": None, "version": None, "is_active_ref": True,
             "unverified_chain": True, "age_days": 400},
        ],
    }
    r1 = compute_quality_snapshot(payload)
    r2 = compute_quality_snapshot(payload)
    assert r1.as_dict() == r2.as_dict()

    assert r1.metrics["total_records"] == 3
    assert r1.metrics["missing_actor"] == 1          # a3
    assert r1.metrics["ocr_unconfirmed"] == 1        # a2
    assert r1.metrics["unverified_chain"] == 1       # a3
    assert r1.aging_buckets == {"0-30": 1, "31-90": 0, "91-180": 0, "181-365": 1, "365+": 1}
    # a2(OCR_UNCONFIRMED) + a3(MISSING_ACTOR) 为阻断记录
    assert r1.metrics["blocking_records"] == 2
    assert r1.business_conclusion["archive_ready"] is False
    assert r1.business_conclusion["grade"] == "blocked"
    # issue_list 按 id 排序
    assert [item["id"] for item in r1.issue_list] == ["a2", "a3"]
    assert r1.issue_list[0]["issues"] == ["OCR_UNCONFIRMED"]
    assert r1.issue_list[1]["issues"] == ["MISSING_ACTOR", "UNVERIFIED_CHAIN"]
    # input_hash 稳定复算
    assert r1.input_hash == build_snapshot_input_hash(payload)
