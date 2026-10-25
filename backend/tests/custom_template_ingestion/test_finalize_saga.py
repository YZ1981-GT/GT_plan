"""Task 11 守卫：finalize visibility saga + G-HANDOFF-CONSUMER 消费。"""
from __future__ import annotations

import copy

import pytest

from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_CONSUMER_ENTRY_NAMESPACE,
    ACK_CONSUMER_GUIDANCE,
    ACK_CONSUMER_PUBLIC_SHELL,
    ACK_CONSUMER_RENDERER,
    ACK_REJECTED,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
)
from app.services.custom_template_ingestion.finalize_saga import (
    FinalizeLock,
    FinalizeSagaError,
    InMemoryAckLedger,
    assert_instantiate_allowed,
    run_finalize_saga,
)
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.guidance_handoff_consumer_service import compute_handoff_digest


def _lock(**overrides) -> FinalizeLock:
    base = dict(
        candidate_id="cand-1",
        candidate_digest="cdig-1",
        approval_intent_id="ai-1",
        approval_intent_digest="adig-1",
        policy_fingerprint="pol-1",
        scanner_fingerprint="scn-1",
        authority_ref="auth-1",
        mapping_digest="map-1",
        guidance_digest="guid-1",
        idempotency_key="idem-1",
        organization_id="org-1",
    )
    base.update(overrides)
    return FinalizeLock(**base)


def _handoff(**overrides) -> dict:
    base = {
        "handoffId": "ho-1",
        "phase": "finalized",
        "organizationId": "org-1",
        "projectId": "proj-1",
        "wpCode": "CX-1",
        "entryId": "pwi-wid:s1",
        "sheetUid": "s1",
        "sections": {"purpose": "x"},
    }
    base.update(overrides)
    return base


def _all_accepted() -> dict:
    return {
        ACK_CONSUMER_GUIDANCE: ACK_ACCEPTED,
        ACK_CONSUMER_RENDERER: ACK_ACCEPTED,
        ACK_CONSUMER_PUBLIC_SHELL: ACK_ACCEPTED,
        ACK_CONSUMER_ENTRY_NAMESPACE: ACK_ACCEPTED,
    }


def test_pending_not_runtime_discoverable_until_all_acks():
    ledger = InMemoryAckLedger()
    # 缺 entry_namespace ACK → PENDING
    partial = {
        ACK_CONSUMER_GUIDANCE: ACK_ACCEPTED,
        ACK_CONSUMER_RENDERER: ACK_ACCEPTED,
        ACK_CONSUMER_PUBLIC_SHELL: ACK_ACCEPTED,
    }
    result = run_finalize_saga(
        lock=_lock(),
        finalized_handoff=_handoff(),
        consumer_results=partial,
        ledger=ledger,
    )
    assert result.publication.state == PublicationState.PENDING_VISIBILITY
    assert result.visibility_state == VISIBILITY_PENDING
    assert result.runtime_discoverable is False
    with pytest.raises(FinalizeSagaError):
        assert_instantiate_allowed(result.publication)


def test_all_accepted_becomes_active_and_instantiate_ok():
    result = run_finalize_saga(
        lock=_lock(),
        finalized_handoff=_handoff(),
        consumer_results=_all_accepted(),
    )
    assert result.publication.state == PublicationState.ACTIVE
    assert result.visibility_state == VISIBILITY_ACTIVE
    assert result.runtime_discoverable is True
    assert_instantiate_allowed(result.publication)


def test_rejected_ack_keeps_visibility_zero():
    results = _all_accepted()
    results[ACK_CONSUMER_RENDERER] = ACK_REJECTED
    result = run_finalize_saga(
        lock=_lock(idempotency_key="idem-rej"),
        finalized_handoff=_handoff(handoffId="ho-rej"),
        consumer_results=results,
    )
    assert result.publication.state == PublicationState.FAILED
    assert result.visibility_state == VISIBILITY_REJECTED
    assert result.runtime_discoverable is False


def test_idempotent_replay_returns_same_result():
    ledger = InMemoryAckLedger()
    lock = _lock(idempotency_key="idem-replay")
    first = run_finalize_saga(
        lock=lock,
        finalized_handoff=_handoff(handoffId="ho-replay"),
        consumer_results=_all_accepted(),
        ledger=ledger,
    )
    second = run_finalize_saga(
        lock=lock,
        finalized_handoff=_handoff(handoffId="ho-replay"),
        consumer_results=_all_accepted(),
        ledger=ledger,
        prior_result=first,
    )
    assert second is first
    assert second.publication.publication_id == first.publication.publication_id


def test_idempotency_digest_conflict_on_lock_change():
    first = run_finalize_saga(
        lock=_lock(idempotency_key="idem-c"),
        finalized_handoff=_handoff(handoffId="ho-c"),
        consumer_results=_all_accepted(),
    )
    with pytest.raises(FinalizeSagaError, match="digest conflict"):
        run_finalize_saga(
            lock=_lock(idempotency_key="idem-c", candidate_digest="CHANGED"),
            finalized_handoff=_handoff(handoffId="ho-c"),
            consumer_results=_all_accepted(),
            prior_result=first,
        )


def test_candidate_phase_rejected():
    with pytest.raises(FinalizeSagaError, match="finalized"):
        run_finalize_saga(
            lock=_lock(idempotency_key="idem-cand"),
            finalized_handoff=_handoff(phase="candidate"),
            consumer_results=_all_accepted(),
        )


def test_ack_ledger_idempotent_upsert():
    ledger = InMemoryAckLedger()
    ho = _handoff(handoffId="ho-idem")
    digest = compute_handoff_digest(ho)
    a1 = ledger.upsert(
        handoff_id="ho-idem",
        handoff_digest=digest,
        consumer=ACK_CONSUMER_GUIDANCE,
        consumer_version="v1",
        verdict=ACK_ACCEPTED,
    )
    a2 = ledger.upsert(
        handoff_id="ho-idem",
        handoff_digest=digest,
        consumer=ACK_CONSUMER_GUIDANCE,
        consumer_version="v1",
        verdict=ACK_ACCEPTED,
    )
    assert a1.ack_id == a2.ack_id
    with pytest.raises(FinalizeSagaError, match="conflict"):
        ledger.upsert(
            handoff_id="ho-idem",
            handoff_digest=digest,
            consumer=ACK_CONSUMER_GUIDANCE,
            consumer_version="v1",
            verdict=ACK_REJECTED,
        )
