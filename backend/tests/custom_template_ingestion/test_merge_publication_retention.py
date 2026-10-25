"""Task 15–17 守卫：merge/remap、publication ops、retention。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.guidance_gid import StableSheetIdentity
from app.services.custom_template_ingestion.lifecycles import (
    FakeClock,
    PublicationState,
    ProjectOperationRecord,
    ProjectOperationState,
    ProjectOperationType,
    TemplatePublicationRecord,
)
from app.services.custom_template_ingestion.mapping import ProjectionMode
from app.services.custom_template_ingestion.merge_remap import (
    detect_structural_remap,
    replay_crashed_operation,
    three_way_merge_fields,
)
from app.services.custom_template_ingestion.publication_ops import (
    PublicationRegistry,
    apply_upgrade_via_staging,
    instantiate_from_active,
    offer_upgrade,
    security_revoke,
    withdraw_publication,
)
from app.services.custom_template_ingestion.retention import (
    ArtifactKind,
    ReferenceGraph,
    build_evidence_envelope,
    execute_retention,
    plan_retention,
    register_ref,
)
from app.services.custom_template_ingestion.workbook_instance import SheetSeed


def test_three_way_merge_auto_and_conflict_no_lww():
    out = three_way_merge_fields(
        base={"a": 1, "b": 1},
        ours={"a": 2, "b": 1},
        theirs={"a": 1, "b": 3},
        unmanaged={"note": "keep"},
    )
    assert out.auto_merged["a"] == 2
    assert out.auto_merged["b"] == 3
    assert out.unmanaged_preserved["note"] == "keep"
    assert out.conflicts == ()

    conflicted = three_way_merge_fields(
        base={"a": 1},
        ours={"a": 2},
        theirs={"a": 3},
    )
    assert conflicted.blocked is True
    assert len(conflicted.conflicts) == 1
    assert "a" not in conflicted.auto_merged


def test_structural_remap_blocks_and_no_label_guess():
    remaps = detect_structural_remap(
        before_locators={"row1": "A10"},
        after_locators={"row2": "A11"},
    )
    assert any(r.reason == "carrier_lost" for r in remaps)
    assert any(r.reason == "carrier_new_unmapped" for r in remaps)
    assert all(r.blocks_auto_projection for r in remaps)


def test_replay_crashed_operation():
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    clock = FakeClock(now)
    op = ProjectOperationRecord(
        operation_id="op-1",
        organization_id="o",
        project_id="p",
        operation_type=ProjectOperationType.GRID_MUTATION,
        state=ProjectOperationState.PENDING,
        idempotency_key="idem",
        base_revision="r0",
        current_revision=None,
        incoming_revision=None,
        authorization_epoch=1,
        write_fence="f1",
        input_digest="in",
        output_digest=None,
        created_at=now,
        updated_at=now,
    )
    calls = []
    replay_crashed_operation(op, clock=clock, apply=lambda o: calls.append(o.operation_id))
    assert op.state == ProjectOperationState.COMMITTED
    assert calls == ["op-1"]
    # idempotent
    replay_crashed_operation(op, clock=clock)
    assert op.state == ProjectOperationState.COMMITTED


def _active_pub(pid: str, cand: str = "c1") -> TemplatePublicationRecord:
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    return TemplatePublicationRecord(
        publication_id=pid,
        organization_id="org",
        candidate_id=cand,
        candidate_digest="cd",
        authority_ref="auth",
        state=PublicationState.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _seed() -> SheetSeed:
    return SheetSeed(
        sheet=StableSheetIdentity(
            template_lineage_id="l",
            template_version_id="v",
            wp_code="CX",
            sheet_uid="s1",
            sheet_code="A",
        ),
        sheet_code="A",
        wp_code="CX",
        component_type="custom_grid",
        projection_mode=ProjectionMode.READ_ONLY_HTML,
    )


def test_instantiate_pin_upgrade_withdraw_revoke():
    reg = PublicationRegistry()
    clock = FakeClock(datetime(2026, 9, 9, tzinfo=timezone.utc))
    p1 = _active_pub("pub-1")
    p2 = _active_pub("pub-2", cand="c2")
    reg.register_active(p1, "dig-1")
    reg.register_active(p2, "dig-2")

    inst = instantiate_from_active(
        reg,
        publication_id="pub-1",
        organization_id="org",
        project_id="proj",
        wp_id="wp",
        sheets=[_seed()],
        current_artifact_id="art",
    )
    assert inst.pinned_template_version_id == "pub-1"
    assert reg.pins["proj"] == "pub-1"

    offer = offer_upgrade(reg, project_id="proj", to_publication_id="pub-2")
    with pytest.raises(ValueError, match="ApprovalIntent"):
        apply_upgrade_via_staging(
            reg, project_id="proj", offer=offer, approval_intent_id=None, staging_ok=True
        )
    assert (
        apply_upgrade_via_staging(
            reg, project_id="proj", offer=offer, approval_intent_id="ai", staging_ok=False
        )
        == "pub-1"
    )
    assert (
        apply_upgrade_via_staging(
            reg, project_id="proj", offer=offer, approval_intent_id="ai", staging_ok=True
        )
        == "pub-2"
    )

    withdraw_publication(reg, "pub-2", clock=clock)
    assert reg.publications["pub-2"].state == PublicationState.WITHDRAWN
    # pin 仍指向 withdrawn（继续使用）
    assert reg.pins["proj"] == "pub-2"

    # SECURITY_REVOKED 只能从 ACTIVE 出发：另建 ACTIVE 再 pin 后撤销
    p3 = _active_pub("pub-3", cand="c3")
    reg.register_active(p3, "dig-3")
    reg.pins["proj"] = "pub-3"
    affected = security_revoke(reg, "pub-3", clock=clock)
    assert "proj" in affected
    assert "proj" not in reg.pins
    assert reg.publications["pub-3"].state == PublicationState.SECURITY_REVOKED


def test_retention_ttl_and_protected_refs():
    clock = FakeClock(datetime(2026, 9, 9, tzinfo=timezone.utc))
    g = ReferenceGraph()
    upload = register_ref(
        g, kind=ArtifactKind.UPLOAD, digest="u", clock=clock, ttl_seconds=10
    )
    pub = register_ref(
        g, kind=ArtifactKind.PUBLICATION, digest="p", clock=clock, ttl_seconds=10
    )
    g.add_edge(pub.artifact_id, upload.artifact_id)

    assert plan_retention(g, clock=clock) == []
    clock.advance(11)
    intents = plan_retention(g, clock=clock)
    assert {i.artifact_id for i in intents} == {upload.artifact_id, pub.artifact_id}

    r_pub = execute_retention(g, intents[0] if intents[0].artifact_id == pub.artifact_id else intents[1])
    # find publication intent
    pub_intent = next(i for i in intents if i.artifact_id == pub.artifact_id)
    up_intent = next(i for i in intents if i.artifact_id == upload.artifact_id)
    assert execute_retention(g, pub_intent).deleted is False
    assert execute_retention(g, up_intent).deleted is False  # still referenced
    # drop edge then delete
    g.nodes[upload.artifact_id].referenced_by.clear()
    assert execute_retention(g, up_intent).deleted is True


def test_evidence_envelope_strips_secrets():
    env = build_evidence_envelope(
        scope={"projectId": "p"},
        digests={"artifact": "abc"},
        scanner_fingerprint="scn",
        revisions={"content": "c1"},
        operations=("op-1",),
        verdict="PASS",
    )
    assert "token" not in env.to_dict()
    with pytest.raises(ValueError):
        build_evidence_envelope(
            scope={"projectId": "token-xyz"},
            digests={},
            scanner_fingerprint="s",
            revisions={},
            operations=(),
            verdict="PASS",
        )
