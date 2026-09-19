"""G-HANDOFF-CONSUMER 行为测试（Task 16 / spec Requirement 13）。

覆盖：
    * candidate handoff → review_pending，绝不 ACCEPTED、不写 ledger（13.1）
    * finalized handoff → 有序 pipeline → ACCEPTED（13.2/13.3）
    * 缺段 / 生命周期 locator kind / 缺 digest / phase 错 → REJECTED（13.3）
    * ACK ledger durable + 幂等（重复提交命中同一行）（13.4）
    * visibility saga：全 ACCEPTED→ACTIVE；REJECTED/缺 ACK→0（13.5/13.6）
    * handoff 变化 → 旧 visibility stale（13.7）

🔴 用 sync SQLAlchemy + SQLite in-memory，不依赖真实 PG；V157 迁移 schema 与
ORM 双向对齐（见 guidance_handoff_ack_models）。真实 fixtures 直接读 C0 bundle，
不手写第二份，防契约漂移。
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_REJECTED,
    GuidanceConsumerAck,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
)
from app.services.guidance_gc0_contract import fixtures_dir
from app.services.guidance_handoff_consumer_service import (
    CANONICAL_HANDOFF_SECTION_KEYS,
    GUIDANCE_CONSUMER_VERSION,
    compute_handoff_digest,
    mark_stale_on_change,
    record_ack,
    resolve_visibility,
    verify_candidate_handoff,
    verify_finalized_handoff,
    build_ghandoff_consumer_evidence_payload,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load(name: str) -> dict:
    return json.loads((fixtures_dir() / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def finalized() -> dict:
    return _load("handoff_finalized")


@pytest.fixture
def candidate() -> dict:
    return _load("handoff_candidate")


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    # 只建 ACK 相关两张表（其余模型不参与本测试，避免跨表 FK 干扰）。
    Base.metadata.create_all(
        engine,
        tables=[
            GuidanceConsumerAck.__table__,
            __import__(
                "app.models.guidance_handoff_ack_models",
                fromlist=["GuidanceHandoffVisibility"],
            ).GuidanceHandoffVisibility.__table__,
        ],
    )
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# candidate 永不 exact
# ---------------------------------------------------------------------------


def test_candidate_handoff_is_review_pending_never_accepted(candidate):
    result = verify_candidate_handoff(candidate)
    assert result.verdict == "review_pending"
    assert result.verdict != ACK_ACCEPTED


def test_candidate_ack_must_not_enter_ledger(session, candidate):
    result = verify_candidate_handoff(candidate)
    with pytest.raises(ValueError, match="review_pending"):
        record_ack(session, handoff_id=candidate["handoffId"], result=result)
    assert session.query(GuidanceConsumerAck).count() == 0


def test_candidate_carrying_finalization_is_rejected(candidate):
    tainted = deepcopy(candidate)
    tainted["finalizationId"] = "fin-sneaky"
    result = verify_candidate_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert "candidate-carries-finalization" in result.reason_codes


# ---------------------------------------------------------------------------
# finalized pipeline
# ---------------------------------------------------------------------------


def test_finalized_handoff_accepted(finalized):
    result = verify_finalized_handoff(finalized)
    assert result.verdict == ACK_ACCEPTED, result.reason_codes
    assert result.reason_codes == ()
    # 校验过的 digests 至少含四类
    for k in ("artifact", "mapping", "formulaBoundary", "guidance"):
        assert k in result.validated_digests


def test_finalized_missing_section_rejected(finalized):
    tainted = deepcopy(finalized)
    tainted["sections"] = [s for s in tainted["sections"] if s["key"] != "formulas"]
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert "missing-section:formulas" in result.reason_codes


def test_finalized_lifecycle_locator_kind_rejected(finalized):
    tainted = deepcopy(finalized)
    tainted["sections"][0]["sourceRefs"][0]["locator"]["kind"] = "custom_confirmed"
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert any(r.startswith("lifecycle-locator-kind") for r in result.reason_codes)


def test_finalized_missing_digest_rejected(finalized):
    tainted = deepcopy(finalized)
    tainted["mappingVersion"] = ""
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert "digest-missing:mapping" in result.reason_codes


def test_finalized_phase_candidate_rejected(finalized):
    tainted = deepcopy(finalized)
    tainted["phase"] = "candidate"
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert any(r.startswith("phase-mismatch") for r in result.reason_codes)


def test_finalized_unknown_major_blocked(finalized):
    tainted = deepcopy(finalized)
    tainted["contractVersion"] = "9.0"
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    assert any("unknown-major" in r for r in result.reason_codes)


# ---------------------------------------------------------------------------
# digest 稳定性
# ---------------------------------------------------------------------------


def test_handoff_digest_changes_with_content(finalized):
    d1 = compute_handoff_digest(finalized)
    tainted = deepcopy(finalized)
    tainted["guidanceRevision"] = "guid-v99"
    d2 = compute_handoff_digest(tainted)
    assert d1 != d2
    assert len(d1) == 64
    # 不得是常量
    assert d1 != "0" * 64


# ---------------------------------------------------------------------------
# ACK ledger durable + 幂等
# ---------------------------------------------------------------------------


def test_ack_ledger_is_durable_and_idempotent(session, finalized):
    result = verify_finalized_handoff(finalized)
    row1 = record_ack(session, handoff_id=finalized["handoffId"], result=result)
    row2 = record_ack(session, handoff_id=finalized["handoffId"], result=result)
    assert row1.id == row2.id  # 同一行
    assert session.query(GuidanceConsumerAck).count() == 1
    assert row1.verdict == ACK_ACCEPTED
    assert row1.consumer_version == GUIDANCE_CONSUMER_VERSION


def test_ack_new_row_for_new_digest(session, finalized):
    r1 = verify_finalized_handoff(finalized)
    record_ack(session, handoff_id=finalized["handoffId"], result=r1)
    changed = deepcopy(finalized)
    changed["guidanceRevision"] = "guid-v2-changed"
    r2 = verify_finalized_handoff(changed)
    record_ack(session, handoff_id=changed["handoffId"], result=r2)
    assert session.query(GuidanceConsumerAck).count() == 2  # 新 digest → 新行


# ---------------------------------------------------------------------------
# visibility saga
# ---------------------------------------------------------------------------


def test_visibility_active_only_when_all_required_accepted(session, finalized):
    result = verify_finalized_handoff(finalized)
    record_ack(session, handoff_id=finalized["handoffId"], result=result)
    vis = resolve_visibility(session, handoff=finalized, handoff_digest=result.handoff_digest)
    assert vis.state == VISIBILITY_ACTIVE
    assert vis.is_visible is True


def test_visibility_zero_when_ack_missing(session, finalized):
    result = verify_finalized_handoff(finalized)
    # 不写 ACK
    vis = resolve_visibility(session, handoff=finalized, handoff_digest=result.handoff_digest)
    assert vis.state == VISIBILITY_PENDING
    assert vis.is_visible is False
    assert any(r.startswith("ack-missing") for r in vis.reason_codes_json)


def test_visibility_rejected_keeps_zero(session, finalized):
    tainted = deepcopy(finalized)
    tainted["sections"] = [s for s in tainted["sections"] if s["key"] != "steps"]
    result = verify_finalized_handoff(tainted)
    assert result.verdict == ACK_REJECTED
    record_ack(session, handoff_id=tainted["handoffId"], result=result)
    vis = resolve_visibility(session, handoff=tainted, handoff_digest=result.handoff_digest)
    assert vis.state == VISIBILITY_REJECTED
    assert vis.is_visible is False


def test_visibility_zero_when_required_consumer_missing(session, finalized):
    """guidance ACCEPTED 但 renderer 未 ACK → 仍不可见。"""
    result = verify_finalized_handoff(finalized)
    record_ack(session, handoff_id=finalized["handoffId"], result=result)
    vis = resolve_visibility(
        session,
        handoff=finalized,
        handoff_digest=result.handoff_digest,
        required_consumers=("guidance", "renderer"),
    )
    assert vis.state == VISIBILITY_PENDING
    assert vis.is_visible is False


def test_handoff_change_marks_old_visibility_stale(session, finalized):
    result = verify_finalized_handoff(finalized)
    record_ack(session, handoff_id=finalized["handoffId"], result=result)
    vis = resolve_visibility(session, handoff=finalized, handoff_digest=result.handoff_digest)
    assert vis.is_visible is True

    # handoff 变化 → 新 digest；旧行应 stale
    changed = deepcopy(finalized)
    changed["guidanceRevision"] = "guid-v3"
    new_digest = compute_handoff_digest(changed)
    n = mark_stale_on_change(session, handoff_id=finalized["handoffId"], new_handoff_digest=new_digest)
    assert n == 1
    session.refresh(vis)
    assert vis.stale is True
    assert vis.is_visible is False


# ---------------------------------------------------------------------------
# evidence payload
# ---------------------------------------------------------------------------


def test_evidence_payload_shape():
    payload = build_ghandoff_consumer_evidence_payload()
    assert payload["subject"] == {"kind": "contract", "contractId": "G-HANDOFF-CONSUMER"}
    assert payload["contractVersions"]["G-C0"] == "1.0"
    assert payload["sagaContract"]["ackFailVisibility"] == 0
    assert payload["sagaContract"]["candidateVerdict"] == "review_pending"
    assert payload["sagaContract"]["crossSystemAcid"] is False
    assert payload["idempotencyKey"] == [
        "handoff_id",
        "handoff_digest",
        "consumer",
        "consumer_version",
    ]
    assert len(CANONICAL_HANDOFF_SECTION_KEYS) == 9


def test_on_disk_evidence_matches_live_module_digest():
    """落盘 evidence 的 module sha256 必须 == 当前实现的 sha256。

    防「evidence 过时假绿」：改了 service 却没重跑 emit 脚本 → digest 不符 → 红。
    """
    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "data" / "guidance" / "contracts" / "ghandoff" / "evidence"
        / "ghandoff_consumer_evidence.json"
    )
    assert evidence_path.exists(), "G-HANDOFF-CONSUMER evidence 未落盘（跑 emit 脚本）"
    on_disk = json.loads(evidence_path.read_text(encoding="utf-8"))
    live = build_ghandoff_consumer_evidence_payload()
    assert on_disk["sourceDigests"]["module"] == live["sourceDigests"]["module"], (
        "evidence module digest 与实现不符——改了 service 后需重跑 "
        "emit_ghandoff_consumer_evidence.py"
    )
    assert on_disk["subject"] == live["subject"]
