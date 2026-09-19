"""四 lifecycle repositories 守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.custom_template_ingestion.lifecycles import (
    FakeClock,
    InMemoryLifecycleRepository,
    InvalidLifecycleTransition,
    LifecycleError,
    ProjectOperationState,
    ProjectOperationType,
    PublicationState,
    TemplateCandidate,
    UploadArtifactState,
    freeze_candidate,
)


def _clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc))


def test_upload_cannot_jump_to_active_publication_state() -> None:
    """Requirement 6.1：UploadArtifact 枚举不含 ACTIVE/publication。"""
    assert not hasattr(UploadArtifactState, "ACTIVE")
    assert "PENDING_VISIBILITY" not in UploadArtifactState.__members__


def test_upload_transition_matrix_enforced() -> None:
    repo = InMemoryLifecycleRepository(clock=_clock())
    up = repo.create_upload(
        organization_id="org1", project_id="p1", artifact_sha256="abc",
    )
    assert up.state is UploadArtifactState.QUARANTINED
    up.transition(
        UploadArtifactState.PREFLIGHT_RUNNING, clock=repo.clock, reason="start",
    )
    up.transition(
        UploadArtifactState.PREFLIGHT_READY, clock=repo.clock, reason="ok",
        output_digest="out1",
    )
    with pytest.raises(InvalidLifecycleTransition):
        up.transition(
            UploadArtifactState.PREFLIGHT_RUNNING, clock=repo.clock, reason="back",
        )


def test_draft_optimistic_version_and_freeze_immutable() -> None:
    clock = _clock()
    repo = InMemoryLifecycleRepository(clock=clock)
    draft = repo.create_draft(
        organization_id="org1", artifact_id="up1", mapping={"a": 1},
    )
    draft.update_mapping({"a": 2}, clock=clock, expected_revision=1)
    assert draft.revision == 2
    with pytest.raises(LifecycleError):
        draft.update_mapping({"a": 3}, clock=clock, expected_revision=1)

    cand = repo.freeze_draft(
        draft.draft_id,
        artifact_sha256="sha",
        policy_digest="pol",
        scanner_digest="scn",
        guidance_digest="g",
    )
    assert isinstance(cand, TemplateCandidate)
    assert draft.frozen is True
    with pytest.raises(LifecycleError):
        draft.update_mapping({"a": 9}, clock=clock, expected_revision=2)
    # candidate frozen dataclass — replace would be new object; digest stable
    d1 = cand.digest
    d2 = cand.digest
    assert d1 == d2
    assert len(d1) == 64


def test_freeze_creates_new_candidate_revision_when_mapping_changes() -> None:
    clock = _clock()
    repo = InMemoryLifecycleRepository(clock=clock)
    d1 = repo.create_draft(organization_id="o", artifact_id="a", mapping={"x": 1})
    c1 = repo.freeze_draft(
        d1.draft_id,
        artifact_sha256="sha",
        policy_digest="p",
        scanner_digest="s",
        guidance_digest="g",
    )
    d2 = repo.create_draft(organization_id="o", artifact_id="a", mapping={"x": 2})
    c2 = repo.freeze_draft(
        d2.draft_id,
        artifact_sha256="sha",
        policy_digest="p",
        scanner_digest="s",
        guidance_digest="g",
        supersedes=c1.candidate_id,
    )
    assert c1.candidate_revision != c2.candidate_revision
    assert c1.mapping_digest != c2.mapping_digest
    assert c2.supersedes == c1.candidate_id


def test_publication_pending_then_active_withdraw() -> None:
    clock = _clock()
    repo = InMemoryLifecycleRepository(clock=clock)
    pub = repo.create_publication(
        organization_id="o",
        candidate_id="c1",
        candidate_digest="d1",
        authority_ref="auth:finalized:1",
    )
    assert pub.state is PublicationState.PENDING_VISIBILITY
    pub.transition(PublicationState.ACTIVE, clock=clock, reason="acks_ok")
    pub.transition(PublicationState.WITHDRAWN, clock=clock, reason="retire")
    with pytest.raises(InvalidLifecycleTransition):
        pub.transition(PublicationState.ACTIVE, clock=clock, reason="revive")


def test_operation_idempotency_returns_same_record() -> None:
    clock = _clock()
    repo = InMemoryLifecycleRepository(clock=clock)
    kwargs = dict(
        organization_id="o",
        project_id="p",
        operation_type=ProjectOperationType.GRID_MUTATION,
        idempotency_key="idem-1",
        base_revision="r1",
        authorization_epoch=1,
        write_fence="fence-1",
        input_digest="in1",
        lease_owner="user-1",
    )
    op1 = repo.begin_operation(**kwargs)
    op2 = repo.begin_operation(**kwargs)
    assert op1.operation_id == op2.operation_id
    assert op1 is op2


def test_lease_expiry_blocks_commit_and_watchdog_recovers() -> None:
    clock = _clock()
    repo = InMemoryLifecycleRepository(clock=clock)
    op = repo.begin_operation(
        organization_id="o",
        project_id="p",
        operation_type=ProjectOperationType.INSTANTIATE,
        idempotency_key="idem-lease",
        base_revision="r0",
        authorization_epoch=1,
        write_fence="f",
        input_digest="in",
        lease_owner="u",
        lease_ttl_seconds=30,
    )
    op.transition(ProjectOperationState.APPLYING, clock=clock, reason="start")
    clock.advance(31)
    with pytest.raises(LifecycleError):
        op.transition(
            ProjectOperationState.COMMITTED, clock=clock, reason="too_late",
        )
    recovered = repo.recover_expired_leases()
    assert op.operation_id in recovered
    assert op.state is ProjectOperationState.FAILED
    op.transition(
        ProjectOperationState.COMPENSATED, clock=clock, reason="rollback",
    )


def test_fake_clock_does_not_use_wall_time() -> None:
    clock = _clock()
    start = clock.now()
    clock.advance(3600)
    assert (clock.now() - start).total_seconds() == 3600


def test_publication_enum_disjoint_from_upload() -> None:
    upload_values = {s.value for s in UploadArtifactState}
    pub_values = {s.value for s in PublicationState}
    # PREFLIGHT_* 不得出现在 publication；ACTIVE 不得出现在 upload
    assert "ACTIVE" not in upload_values
    assert not any(v.startswith("PREFLIGHT") for v in pub_values)
