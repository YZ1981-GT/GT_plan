"""Wave 8 — OCR 属性组 PBT（Task 9.2）：逐项覆盖 P9–P14。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.2 (Wave 8)
Requirements: R5, R6
Design: §4.5 OCR 模型, §5.2 OCR 决策与写回, §11 属性 P9–P14, §10 真实 PG 铁律

逐项属性:
  * P9  OCR 状态机封闭 —— 纯/模型 PBT：仅 contracts.OCR_TRANSITIONS 定义的迁移合法，
        非法事件不改变当前状态或历史。
  * P10 OCR 重试授权 —— 纯/模型 PBT：仅具备项目访问权 + `ocr.retry` 的主体可重试；
        幂等重放至多一次排队效果；越权零副作用。
  * P11 OCR 原始结果不可变 —— 真实 PG16：immutable 触发器拒绝 UPDATE；确认/修正/拒绝/写回
        全流程后 OCRResult 原值/来源版本/hash/page/region 不变。
  * P12 未确认不可写回 —— 纯/模型 mapping predicate + 真实 PG16：任一 required 未决定或拟写回
        含非 accepted/corrected（含 rejected）→ 目标变化量=0；rejected 永不进 mapping。
  * P13 写回原子性 —— 真实 PG16：transactional-local 全部成功或全部保持旧值（事务回滚）；
        staged-external 以 staging + 回执实现业务原子边界。
  * P14 写回幂等性 —— 真实 PG16：同一写回幂等键重放 → 一次业务效果 + 一个成功记录
        （服务层复用 + DB uq_ocr_writeback_idempotency 唯一约束）。

真实 PG 铁律（design §10.1/§10.2）：immutable 触发器 / unique 约束 / 事务回滚 /
staged-external 回执必须在真实 PostgreSQL 16 验证；SQLite 不得替代这些证据 → 无 PG 环境 skip。

常规 PBT 使用全局 fast profile（conftest 注册，默认 max_examples=5，可由
HYPOTHESIS_MAX_EXAMPLES 覆盖）；不在测试正文固定样本数。失败 counterexample 由 Hypothesis 保留。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.core.migration_runner import MigrationRunner
from app.services.evidence_governance.contracts import (
    OCR_FIELD_DECISIONS,
    OCR_STATES,
    OCR_TRANSITIONS,
    OCR_WRITEBACK_ELIGIBLE_DECISIONS,
    OcrState,
    is_legal_ocr_transition,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
)
from app.services.evidence_governance.role_capability_contract import can_retry_ocr

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
V106 = MIGRATIONS_DIR / "V106__evidence_governance_attachment_versions.sql"
V107 = MIGRATIONS_DIR / "V107__evidence_governance_legacy_alias_evidence_ref.sql"
V108 = MIGRATIONS_DIR / "V108__evidence_governance_ocr_citation_review_archive_hold.sql"


# ===========================================================================
# P9 — OCR 状态机封闭（纯/模型 PBT）
# ===========================================================================
#
# 模型：以 contracts.OCR_TRANSITIONS 为唯一真源，逐事件推进一个状态机。
#   * 事件 = (from_state, to_state)。
#   * 仅当 `当前状态 == from_state` 且 (from,to) ∈ OCR_TRANSITIONS 时状态改变、历史追加一条边。
#   * 其它一切事件（非法迁移、或 from 与当前状态不符）→ 状态与历史完全不变。


def _apply_ocr_event(
    state: str, ev_from: str, ev_to: str, history: list[tuple[str, str]]
) -> tuple[str, list[tuple[str, str]]]:
    """封闭状态机单步：仅定义迁移可改变状态/历史，否则原样返回。"""
    if state == ev_from and is_legal_ocr_transition(ev_from, ev_to):
        return ev_to, history + [(ev_from, ev_to)]
    return state, list(history)


_STATE_STRATEGY = st.sampled_from(sorted(OCR_STATES))
# 事件流：from/to 取自封闭状态集，允许非法组合以证明它们零效果。
_EVENT_STRATEGY = st.tuples(_STATE_STRATEGY, _STATE_STRATEGY)


@given(events=st.lists(_EVENT_STRATEGY, max_size=25))
def test_property_p9_ocr_state_machine_closed(events):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 9.

    OCR 状态机封闭：仅 OCR_TRANSITIONS 定义的迁移合法；非法事件（含 from 与当前状态
    不符）不改变当前状态或历史；所有历史边 ⊆ OCR_TRANSITIONS。

    **Validates: Requirements 5.2**
    """
    state = OcrState.queued.value
    history: list[tuple[str, str]] = []

    for ev_from, ev_to in events:
        prev_state = state
        prev_history = list(history)
        new_state, new_history = _apply_ocr_event(state, ev_from, ev_to, history)

        legal_now = (prev_state == ev_from) and is_legal_ocr_transition(ev_from, ev_to)
        if legal_now:
            # 合法：状态推进到 ev_to，历史恰好追加这一条合法边。
            assert new_state == ev_to
            assert new_history == prev_history + [(ev_from, ev_to)]
        else:
            # 非法事件：状态与历史零变化（P9 封闭性）。
            assert new_state == prev_state
            assert new_history == prev_history

        state, history = new_state, new_history

    # 全部历史边都是定义迁移（永不出现未定义边）。
    for edge in history:
        assert edge in OCR_TRANSITIONS


@given(pair=_EVENT_STRATEGY)
def test_property_p9_only_frozen_transitions_legal(pair):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 9.

    合法迁移判定 = 恰在冻结集合内，其它一律非法。

    **Validates: Requirements 5.2**
    """
    ev_from, ev_to = pair
    assert is_legal_ocr_transition(ev_from, ev_to) == ((ev_from, ev_to) in OCR_TRANSITIONS)


def test_property_p9_terminal_and_retry_shape():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 9.

    written_back 无出边（终态）；failed→queued 是唯一的重试边。

    **Validates: Requirements 5.2**
    """
    out_edges = {t for t in OCR_TRANSITIONS if t[0] == OcrState.written_back.value}
    assert out_edges == set()
    assert (OcrState.failed.value, OcrState.queued.value) in OCR_TRANSITIONS
    # failed 只有一条出边（回到 queued）。
    failed_out = {t[1] for t in OCR_TRANSITIONS if t[0] == OcrState.failed.value}
    assert failed_out == {OcrState.queued.value}


# ===========================================================================
# P10 — OCR 重试授权（纯/模型 PBT）
# ===========================================================================
#
# 授权真源 = role_capability_contract.can_retry_ocr。
# 幂等重放模型：复刻 OCRRetryService.retry_failed_job 的守卫顺序
#   1) 未授权 → 零副作用（state 不变、无 enqueue）。
#   2) 非 failed / 超限 / 已有活动重复(queued|running) → 不入队。
#   3) 满足条件 → failed→queued，enqueue 一次；此后 job 变为活动态，后续重放被抑制。

_AUTHORIZED_ROLES = ("manager", "partner", "admin")
_UNAUTHORIZED_ROLES = ("auditor", "qc", "eqcr", "readonly")


def _retry_replay_model(
    *,
    authorized: bool,
    initial_state: str,
    attempts: int,
    max_attempts: int,
    n_replays: int,
) -> tuple[int, str]:
    """返回 (enqueue 次数, 终态)。复刻重试服务的封闭守卫（P9 约束下的 P10 幂等）。"""
    state = initial_state
    active = state in (OcrState.queued.value, OcrState.running.value)
    enqueues = 0
    for _ in range(n_replays):
        if not authorized:
            continue  # P10：越权零副作用
        if state != OcrState.failed.value:
            continue  # 仅 failed 可重试（P9）
        if attempts >= max_attempts:
            continue  # 有界重试（R15.4）
        if active:
            continue  # 重复调度抑制（R5.4）
        # 通过全部守卫：failed → queued，恰一次入队效果。
        state = OcrState.queued.value
        active = True
        enqueues += 1
    return enqueues, state


@given(role=st.sampled_from(_AUTHORIZED_ROLES + _UNAUTHORIZED_ROLES + ("nonsense", "")))
def test_property_p10_retry_authorization_matrix(role):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 10.

    只有基线授权主体（manager/partner/admin）可重试；auditor/qc/eqcr/readonly/垃圾
    token 一律拒绝。

    **Validates: Requirements 5.3**
    """
    if role in _AUTHORIZED_ROLES:
        assert can_retry_ocr(role) is True
    else:
        assert can_retry_ocr(role) is False


@given(
    role=st.sampled_from(_AUTHORIZED_ROLES + _UNAUTHORIZED_ROLES),
    initial_state=_STATE_STRATEGY,
    attempts=st.integers(min_value=0, max_value=8),
    max_attempts=st.integers(min_value=1, max_value=6),
    n_replays=st.integers(min_value=1, max_value=6),
)
def test_property_p10_idempotent_replay_at_most_one_enqueue(
    role, initial_state, attempts, max_attempts, n_replays
):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 10.

    重复提交（幂等重放）至多产生一次排队效果；越权主体产生零副作用（终态不变）。

    **Validates: Requirements 5.3, 5.4**
    """
    authorized = can_retry_ocr(role)
    enqueues, final_state = _retry_replay_model(
        authorized=authorized,
        initial_state=initial_state,
        attempts=attempts,
        max_attempts=max_attempts,
        n_replays=n_replays,
    )

    # 至多一次排队效果（幂等重放）。
    assert enqueues <= 1

    if not authorized:
        # 越权：零副作用（enqueue=0 且终态 == 初态）。
        assert enqueues == 0
        assert final_state == initial_state

    # 仅当 授权 + 初态 failed + 未超限 时才会入队一次。
    eligible = (
        authorized
        and initial_state == OcrState.failed.value
        and attempts < max_attempts
    )
    assert enqueues == (1 if eligible else 0)
    if enqueues == 1:
        assert final_state == OcrState.queued.value


# ===========================================================================
# 真实 PG16 引导（throwaway 库；无 PG 环境 skip）
# ===========================================================================


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
    tmp_db = f"evgov_ocr_p9_14_{uuid.uuid4().hex[:12]}"

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
        # ocr_jobs.next_retry_at 由后续 V110 补齐（ORM 已有、V108 漏列）；此处仅追加该 additive 列，
        # 不引入 V110 的 procedure-delegation 依赖。
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                "ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ"
            )
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


async def _seed_scope(eng):
    """seed user + project + 成员 + command root；返回 ids。"""
    from sqlalchemy import text as T

    ids = {
        "user": uuid.uuid4(),
        "project": uuid.uuid4(),
        "root": uuid.uuid4(),
        "attachment": uuid.uuid4(),
        "attachment_version": uuid.uuid4(),
        "content_hash": "a" * 64,
    }
    async with eng.begin() as conn:
        await conn.execute(T("INSERT INTO users (id) VALUES (:i)"), {"i": ids["user"]})
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
                "INSERT INTO attachments (id, project_id, audit_year, file_name, file_type, file_size, created_by) "
                "VALUES (:a, :p, 2025, 'f.pdf', 'pdf', 10, :u)"
            ),
            {"a": ids["attachment"], "p": ids["project"], "u": ids["user"]},
        )
        await conn.execute(
            T(
                "INSERT INTO attachment_versions "
                "(id, attachment_id, project_id, audit_year, version_no, storage_type, "
                " content_hash, availability, actor_type, actor_user_id) "
                "VALUES (:i, :a, :p, 2025, 1, 'paperless', :h, 'available', 'user', :u)"
            ),
            {
                "i": ids["attachment_version"],
                "a": ids["attachment"],
                "p": ids["project"],
                "h": ids["content_hash"],
                "u": ids["user"],
            },
        )
        await conn.execute(
            T(
                "INSERT INTO evidence_audit_command_roots "
                "(id, command_type, idempotency_key, project_id, audit_year, actor_type, actor_user_id) "
                "VALUES (:i, 'ocr_writeback', :k, :p, 2025, 'user', :u)"
            ),
            {"i": ids["root"], "k": "root-" + uuid.uuid4().hex, "p": ids["project"], "u": ids["user"]},
        )
    return ids


# --- ORM helpers (real PG) ---


async def _create_confirmed_job(session, ids):
    from app.models.evidence_governance_models import OcrJob

    job = OcrJob(
        id=uuid.uuid4(),
        project_id=ids["project"],
        audit_year=2025,
        attachment_id=ids["attachment"],
        attachment_version_id=ids["attachment_version"],
        content_hash=ids["content_hash"],
        idempotency_key="job-" + uuid.uuid4().hex,
        state=OcrState.confirmed.value,
        progress=100,
        attempt_count=1,
        max_attempts=5,
        actor_type="user",
        actor_user_id=ids["user"],
        actor_service_identity_id=None,
    )
    session.add(job)
    await session.flush()
    return job


async def _create_result(session, job, user_id, *, fields):
    """创建 OCRResult（原始识别值）。fields: dict[name -> original_value]。返回 result。"""
    from app.models.evidence_governance_models import OcrResult

    result = OcrResult(
        id=uuid.uuid4(),
        ocr_job_id=job.id,
        project_id=job.project_id,
        audit_year=job.audit_year,
        attachment_version_id=job.attachment_version_id,
        source_content_hash=job.content_hash,
        raw_text="raw-original-text",
        pages={"count": 1},
        fields=dict(fields),
        confidence=0.91,
        page=3,
        region={"x": 1, "y": 2, "w": 30, "h": 40},
        engine="tesseract",
        model_version="5.0.0",
        config_version="v1",
        result_hash=content_hash_of({"fields": dict(fields), "raw": "raw-original-text"}),
        actor_type="user",
        actor_user_id=user_id,
        actor_service_identity_id=None,
    )
    session.add(result)
    await session.flush()
    return result


async def _add_confirmation(session, job, result, user_id, *, field_key, decision, confirmed_value, original_value):
    from app.models.evidence_governance_models import OcrConfirmation

    conf = OcrConfirmation(
        id=uuid.uuid4(),
        ocr_job_id=job.id,
        ocr_result_id=result.id,
        project_id=job.project_id,
        audit_year=job.audit_year,
        field_key=field_key,
        is_required=True,
        original_value=original_value,
        confirmed_value=confirmed_value,
        decision=decision,
        is_current=True,
        revision_no=1,
        confirmed_by_user_id=user_id,
    )
    session.add(conf)
    await session.flush()
    return conf


def _mock_adapter(target_version=1):
    mock_adapter = MagicMock()
    mock_adapter.can_edit = AsyncMock(return_value=True)
    mock_adapter.lock_for_update = AsyncMock(return_value=True)
    mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=target_version))
    return mock_adapter


# ===========================================================================
# P11 — OCR 原始结果不可变（真实 PG16 immutable 触发器）
# ===========================================================================


@pytest.mark.asyncio
async def test_property_p11_ocr_result_immutable_trigger():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 11.

    真实 PG16：ocr_results 的 immutable 触发器拒绝任何 UPDATE（原识别值/来源版本/
    hash/page/region 不可改）。

    **Validates: Requirements 6.1**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16（immutable 触发器不可用 SQLite 替代）")

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(
                session, job, ids["user"], fields={"amount": "1234", "date": "2025-01-01"}
            )
            await session.commit()
            result_id = result.id

        # 任何 UPDATE 都必须被 immutable 触发器拒绝。
        async with SM() as session:
            with pytest.raises(Exception) as exc_info:
                await session.execute(
                    sa.text("UPDATE ocr_results SET raw_text = 'tampered' WHERE id = :i"),
                    {"i": result_id},
                )
                await session.commit()
            # 触发器抛出的异常信息包含 "不可变/append-only"。
            assert "不可变" in str(exc_info.value) or "append-only" in str(exc_info.value)

        # 原始值确实未变。
        async with SM() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT raw_text, page, region, result_hash, source_content_hash, "
                        "attachment_version_id FROM ocr_results WHERE id = :i"
                    ),
                    {"i": result_id},
                )
            ).one()
            assert row[0] == "raw-original-text"
            assert row[1] == 3


@pytest.mark.asyncio
async def test_property_p11_confirm_correct_reject_writeback_preserve_original():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 11.

    真实 PG16：accepted/corrected/rejected 确认 + 写回后，OCRResult 原识别值/来源
    版本/hash/page/region 完全不变（确认写入独立 append-only 表，不触碰原结果）。

    **Validates: Requirements 6.1, 6.2**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(
                session,
                job,
                ids["user"],
                fields={"amount": "1234", "vendor": "ACME", "note": "junk"},
            )
            # 记录原始快照
            orig = {
                "raw_text": result.raw_text,
                "fields": dict(result.fields),
                "page": result.page,
                "region": dict(result.region),
                "result_hash": result.result_hash,
                "source_content_hash": result.source_content_hash,
            }
            # accepted / corrected / rejected 三态确认
            await _add_confirmation(session, job, result, ids["user"], field_key="amount", decision="accepted", confirmed_value="1234", original_value="1234")
            await _add_confirmation(session, job, result, ids["user"], field_key="vendor", decision="corrected", confirmed_value="ACME Corp", original_value="ACME")
            await _add_confirmation(session, job, result, ids["user"], field_key="note", decision="rejected", confirmed_value=None, original_value="junk")
            await session.commit()
            job_id, result_id = job.id, result.id

        # 执行写回（accepted+corrected 进 mapping；rejected 排除）
        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        async with SM() as session:
            service = OCRWritebackService(session)
            with patch(
                "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                return_value=_mock_adapter(target_version=1),
            ):
                wb = await service.execute_writeback(
                    job_id=job_id,
                    result_id=result_id,
                    target_type="workpaper_cell",
                    target_id="cell-1",
                    actor=actor,
                    project_id=ids["project"],
                    audit_year=2025,
                    target_version_at_start="1",
                    command_root_id=ids["root"],
                )
            assert wb.status == "written_back"
            # rejected 字段不进 mapping
            assert "note" not in (wb.fields_written or {})
            assert wb.fields_written == {"amount": "1234", "vendor": "ACME Corp"}
            await session.commit()

        # OCRResult 原值不变
        async with SM() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT raw_text, fields, page, region, result_hash, source_content_hash "
                        "FROM ocr_results WHERE id = :i"
                    ),
                    {"i": result_id},
                )
            ).one()
            assert row[0] == orig["raw_text"]
            assert row[1] == orig["fields"]
            assert row[2] == orig["page"]
            assert row[3] == orig["region"]
            assert row[4] == orig["result_hash"]
            assert row[5] == orig["source_content_hash"]


# ===========================================================================
# P12 — 未确认不可写回（mapping predicate 纯模型 + 真实 PG16 强制）
# ===========================================================================
#
# mapping predicate 模型：复刻 OCRConfirmationService.build_mapping
#   * 任一 required 字段未决定（decision None）→ mapping = None（目标零变化）。
#   * 否则 mapping 仅含 accepted/corrected；rejected 与 undecided 永不进 mapping。

_DECISION_STRATEGY = st.sampled_from(sorted(OCR_FIELD_DECISIONS) + [None])


def _build_mapping_model(fields):
    """fields: list[(name, required: bool, decision: str|None, value)]。返回 mapping|None。"""
    if any(required and decision is None for (_n, required, decision, _v) in fields):
        return None
    mapping = {}
    for name, _required, decision, value in fields:
        if decision in OCR_WRITEBACK_ELIGIBLE_DECISIONS:
            mapping[name] = value
    return mapping


@given(
    fields=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=8),
            st.booleans(),
            _DECISION_STRATEGY,
            st.text(max_size=8),
        ),
        min_size=1,
        max_size=8,
        unique_by=lambda t: t[0],
    )
)
def test_property_p12_mapping_predicate(fields):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 12.

    未确认不可写回：任一 required 字段未决定 → mapping=None（目标变化量=0）；
    mapping 内每个字段的 decision 必为 accepted/corrected；rejected 与 undecided 永不进 mapping。

    **Validates: Requirements 6.2, 6.3**
    """
    mapping = _build_mapping_model(fields)

    any_required_undecided = any(
        required and decision is None for (_n, required, decision, _v) in fields
    )
    if any_required_undecided:
        # 目标零变化：mapping 不可用。
        assert mapping is None
        return

    assert mapping is not None
    decided_by_name = {n: d for (n, _r, d, _v) in fields}
    for key in mapping:
        # mapping 里每个字段必是 accepted/corrected。
        assert decided_by_name[key] in OCR_WRITEBACK_ELIGIBLE_DECISIONS
    # rejected 永不进 mapping。
    rejected = {n for (n, _r, d, _v) in fields if d == "rejected"}
    assert rejected.isdisjoint(mapping.keys())


@pytest.mark.asyncio
async def test_property_p12_undecided_blocks_writeback_zero_change():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 12.

    真实 PG16：required 字段未决定 → 写回被拒（REQUIRED_FIELD_UNDECIDED），
    无 OCRWriteback 记录（目标变化量=0）。

    **Validates: Requirements 6.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            # 有 required 字段但无任何确认 → undecided
            result = await _create_result(session, job, ids["user"], fields={"amount": "1234"})
            await session.commit()
            job_id, result_id = job.id, result.id

        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        async with SM() as session:
            service = OCRWritebackService(session)
            with patch(
                "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                return_value=_mock_adapter(),
            ):
                with pytest.raises(EvidenceGovernanceError) as exc:
                    await service.execute_writeback(
                        job_id=job_id,
                        result_id=result_id,
                        target_type="workpaper_cell",
                        target_id="cell-1",
                        actor=actor,
                        project_id=ids["project"],
                        audit_year=2025,
                    )
            assert exc.value.error_code == EvidenceErrorCode.REQUIRED_FIELD_UNDECIDED
            await session.rollback()

        # 目标变化量=0：无 OCRWriteback 记录。
        async with SM() as session:
            n = (await session.execute(sa.text("SELECT count(*) FROM ocr_writebacks"))).scalar()
            assert n == 0


@pytest.mark.asyncio
async def test_property_p12_all_rejected_blocks_writeback():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 12.

    真实 PG16：全部字段 rejected → mapping 空 → 写回被拒（INVALID_MAPPING），
    rejected 永不进 mapping，目标零变化。

    **Validates: Requirements 6.2, 6.3**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(session, job, ids["user"], fields={"amount": "1234"})
            await _add_confirmation(
                session, job, result, ids["user"],
                field_key="amount", decision="rejected", confirmed_value=None, original_value="1234",
            )
            await session.commit()
            job_id, result_id = job.id, result.id

        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        async with SM() as session:
            service = OCRWritebackService(session)
            with patch(
                "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                return_value=_mock_adapter(),
            ):
                with pytest.raises(EvidenceGovernanceError) as exc:
                    await service.execute_writeback(
                        job_id=job_id,
                        result_id=result_id,
                        target_type="workpaper_cell",
                        target_id="cell-1",
                        actor=actor,
                        project_id=ids["project"],
                        audit_year=2025,
                    )
            assert exc.value.error_code == EvidenceErrorCode.INVALID_MAPPING
            await session.rollback()

        async with SM() as session:
            n = (await session.execute(sa.text("SELECT count(*) FROM ocr_writebacks"))).scalar()
            assert n == 0


# ===========================================================================
# P13 — 写回原子性（真实 PG16 事务回滚 + staged-external 回执）
# ===========================================================================


@pytest.mark.asyncio
async def test_property_p13_transactional_local_rollback_all_or_nothing():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 13.

    真实 PG16：transactional-local 写回过程中任一步骤失败 → 整事务回滚，
    无 OCRWriteback 记录、Job 状态保持旧值（全部保持旧值）。

    **Validates: Requirements 6.4**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(session, job, ids["user"], fields={"amount": "1234"})
            await _add_confirmation(
                session, job, result, ids["user"],
                field_key="amount", decision="accepted", confirmed_value="1234", original_value="1234",
            )
            await session.commit()
            job_id, result_id = job.id, result.id

        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        async with SM() as session:
            service = OCRWritebackService(session)
            # 注入故障：审计 transition 记录抛错（发生在 OCRWriteback 已 add + Job 状态改后）。
            service._audit_svc.record_transition = AsyncMock(  # type: ignore[method-assign]
                side_effect=RuntimeError("injected failure mid-writeback")
            )
            with patch(
                "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                return_value=_mock_adapter(target_version=1),
            ):
                with pytest.raises(RuntimeError):
                    await service.execute_writeback(
                        job_id=job_id,
                        result_id=result_id,
                        target_type="workpaper_cell",
                        target_id="cell-1",
                        actor=actor,
                        project_id=ids["project"],
                        audit_year=2025,
                        target_version_at_start="1",
                        command_root_id=ids["root"],
                    )
            # 调用者回滚（facade/worker 事务边界）。
            await session.rollback()

        # 全部保持旧值：无 OCRWriteback、Job 仍为 confirmed。
        async with SM() as session:
            n = (await session.execute(sa.text("SELECT count(*) FROM ocr_writebacks"))).scalar()
            assert n == 0
            state = (
                await session.execute(
                    sa.text("SELECT state FROM ocr_jobs WHERE id = :i"), {"i": job_id}
                )
            ).scalar()
            assert state == OcrState.confirmed.value


@pytest.mark.asyncio
async def test_property_p13_staged_external_staging_and_receipt():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 13.

    真实 PG16：staged-external 写回先落 staging（持久），回执成功后才推进
    Job→written_back、staging→consumed、writeback→success（业务原子边界）。

    **Validates: Requirements 6.4**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import (
        OCRWritebackService,
        WRITE_MODE_STAGED_EXTERNAL,
    )

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(session, job, ids["user"], fields={"amount": "1234"})
            await _add_confirmation(
                session, job, result, ids["user"],
                field_key="amount", decision="accepted", confirmed_value="1234", original_value="1234",
            )
            await session.commit()
            job_id, result_id = job.id, result.id

        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        # 1) 落 staging（Job 尚未 written_back）
        async with SM() as session:
            service = OCRWritebackService(session)
            with patch(
                "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                return_value=_mock_adapter(target_version=1),
            ), patch(
                "app.services.evidence_governance.ocr_writeback_service._get_write_mode",
                return_value=WRITE_MODE_STAGED_EXTERNAL,
            ):
                wb = await service.execute_writeback(
                    job_id=job_id,
                    result_id=result_id,
                    target_type="workpaper_cell",
                    target_id="cell-1",
                    actor=actor,
                    project_id=ids["project"],
                    audit_year=2025,
                    command_root_id=ids["root"],
                )
            assert wb.status == "staged"
            await session.commit()
            writeback_id = wb.writeback_id

        # staging 落库 pending；Job 仍 confirmed；writeback pending
        async with SM() as session:
            staging_id, cstate = (
                await session.execute(
                    sa.text(
                        "SELECT id, consume_state FROM ocr_writeback_staging "
                        "WHERE ocr_writeback_id = :w"
                    ),
                    {"w": writeback_id},
                )
            ).one()
            assert cstate == "pending"
            jstate = (
                await session.execute(
                    sa.text("SELECT state FROM ocr_jobs WHERE id = :i"), {"i": job_id}
                )
            ).scalar()
            assert jstate == OcrState.confirmed.value

        # 2) 回执成功 → 推进
        async with SM() as session:
            service = OCRWritebackService(session)
            await service.receive_external_receipt(
                staging_id=staging_id, success=True, actor=actor, receipt_data={"ext": "OK"}
            )
            await session.commit()

        async with SM() as session:
            cstate = (
                await session.execute(
                    sa.text("SELECT consume_state FROM ocr_writeback_staging WHERE id = :i"),
                    {"i": staging_id},
                )
            ).scalar()
            assert cstate == "consumed"
            wbresult = (
                await session.execute(
                    sa.text("SELECT result FROM ocr_writebacks WHERE id = :i"),
                    {"i": writeback_id},
                )
            ).scalar()
            assert wbresult == "success"
            jstate = (
                await session.execute(
                    sa.text("SELECT state FROM ocr_jobs WHERE id = :i"), {"i": job_id}
                )
            ).scalar()
            assert jstate == OcrState.written_back.value


# ===========================================================================
# P14 — 写回幂等性（真实 PG16 唯一约束 + 服务复用）
# ===========================================================================


@pytest.mark.asyncio
async def test_property_p14_service_replay_single_effect():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 14.

    真实 PG16：同一写回参数重放 → 服务复用既有记录，只一次业务效果、一个成功记录。

    **Validates: Requirements 6.4**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            result = await _create_result(session, job, ids["user"], fields={"amount": "1234"})
            await _add_confirmation(
                session, job, result, ids["user"],
                field_key="amount", decision="accepted", confirmed_value="1234", original_value="1234",
            )
            await session.commit()
            job_id, result_id = job.id, result.id

        actor = ActorContext(actor_type=ActorType.USER, actor_user_id=ids["user"])
        wb_ids = []
        for _ in range(3):
            async with SM() as session:
                service = OCRWritebackService(session)
                with patch(
                    "app.services.evidence_governance.ocr_writeback_service.get_adapter",
                    return_value=_mock_adapter(target_version=1),
                ):
                    wb = await service.execute_writeback(
                        job_id=job_id,
                        result_id=result_id,
                        target_type="workpaper_cell",
                        target_id="cell-1",
                        actor=actor,
                        project_id=ids["project"],
                        audit_year=2025,
                        target_version_at_start="1",
                        command_root_id=ids["root"],
                    )
                await session.commit()
                wb_ids.append(wb.writeback_id)

        # 所有重放返回同一 writeback；只一条记录 + 一个 success。
        assert len(set(wb_ids)) == 1
        async with SM() as session:
            n = (await session.execute(sa.text("SELECT count(*) FROM ocr_writebacks"))).scalar()
            assert n == 1
            n_success = (
                await session.execute(
                    sa.text("SELECT count(*) FROM ocr_writebacks WHERE result = 'success'")
                )
            ).scalar()
            assert n_success == 1


@pytest.mark.asyncio
async def test_property_p14_db_unique_constraint_enforces_single_record():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 14.

    真实 PG16：uq_ocr_writeback_idempotency 唯一约束在 DB 层强制同 scope + 同幂等键
    只能有一条记录（第二次直插违反约束）。

    **Validates: Requirements 6.4**
    """
    if not _pg_available():
        pytest.skip("需真实 PostgreSQL 16")

    from app.models.evidence_governance_models import OcrWriteback

    async with _throwaway_engine() as eng:
        ids = await _seed_scope(eng)
        SM = _sessionmaker(eng)
        async with SM() as session:
            job = await _create_confirmed_job(session, ids)
            await session.commit()
            job_id = job.id

        idem = "wb-idem-" + uuid.uuid4().hex

        def _row():
            return OcrWriteback(
                id=uuid.uuid4(),
                ocr_job_id=job_id,
                project_id=ids["project"],
                audit_year=2025,
                target_type="workpaper_cell",
                target_id="cell-1",
                target_version="1",
                write_mode="transactional-local",
                field_mapping={"amount": "1234"},
                confirmation_ids=[],
                idempotency_key=idem,
                payload_hash="p" * 64,
                result="success",
                written_by_user_id=ids["user"],
            )

        async with SM() as session:
            session.add(_row())
            await session.commit()

        # 第二条同 (project, year, idempotency_key) → 违反唯一约束。
        async with SM() as session:
            session.add(_row())
            with pytest.raises(Exception) as exc:
                await session.commit()
            assert "uq_ocr_writeback_idempotency" in str(exc.value) or "unique" in str(
                exc.value
            ).lower()

        async with SM() as session:
            n = (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM ocr_writebacks WHERE idempotency_key = :k"
                    ),
                    {"k": idem},
                )
            ).scalar()
            assert n == 1
