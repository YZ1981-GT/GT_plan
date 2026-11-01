"""证据就绪度四态、消费方一致性和正式门 fail-closed。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.models.attachment_models import AttachmentWorkingPaper
from app.models.wp_optimization_models import WorkpaperProcedure
from app.services import evidence_readiness as readiness_module
from app.services.attachment_service import AttachmentService
from app.services.evidence_readiness import (
    EvidenceReadinessService,
    ProjectEvidenceReadiness,
    WorkpaperEvidenceReadiness,
)
from app.services.gate_rules_evidence import EvidenceReadinessRule
from app.services.qc_engine import AttachmentSufficiencyRule, QCContext
from app.services.wp_evidence_service import WpEvidenceService
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_wp,
    sqlite_attachment_world,
)


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as value:
        await value.db.run_sync(
            lambda session: WorkpaperProcedure.__table__.create(session.connection(), checkfirst=True)
        )
        yield value


@pytest.mark.asyncio
async def test_four_state_baseline_and_compatibility_consumers_agree(world):
    undeclared = await add_wp(world, world.target, wp_code="B1-1")
    declared = await add_wp(world, world.target, wp_code="F3-5")
    ready_wp = await add_wp(world, world.target, wp_code="F3-6")
    evidence = await add_attachment(
        world, world.target, file_name="票据.pdf", attachment_type="note",
    )
    await world._add(AttachmentWorkingPaper(
        attachment_id=evidence.id, wp_id=ready_wp.id, association_type="note",
    ))

    service = EvidenceReadinessService(world.db)
    assert (await service.evaluate_workpaper(undeclared.id)).status == "not_declared"
    missing = await service.evaluate_workpaper(declared.id)
    assert missing.status == "not_ready" and missing.missing_types == ("note",)
    ready = await service.evaluate_workpaper(ready_wp.id)
    assert ready.status == "ready" and ready.missing_types == ()

    view = await AttachmentService(world.db).get_wp_attachments(ready_wp.id)
    compat = await WpEvidenceService(world.db).check_sufficiency(ready_wp.id)
    qc = await AttachmentSufficiencyRule().check(QCContext(world.db, ready_wp))
    assert view["evidence_readiness"]["status"] == compat["status"] == "ready"
    assert view["evidence_requirements"] == compat["requirements"]
    assert compat["sufficient"] is True and qc == []


@pytest.mark.asyncio
async def test_dependency_failure_becomes_unknown_and_all_formal_consumers_block(world, monkeypatch):
    wp = await add_wp(world, world.target, wp_code="F3-5")

    async def fail(self, wp_id, wp_meta, *, preloaded_items):
        raise RuntimeError("forced dependency failure")

    monkeypatch.setattr(EvidenceReadinessService, "_evaluate_strict", fail)
    result = await EvidenceReadinessService(world.db).evaluate_workpaper(wp.id)
    compat = await WpEvidenceService(world.db).check_sufficiency(wp.id)
    qc = await AttachmentSufficiencyRule().check(QCContext(world.db, wp))
    assert result.status == "unknown"
    assert compat["status"] == "unknown" and compat["sufficient"] is False
    assert len(qc) == 1 and qc[0].severity == "blocking"


@pytest.mark.asyncio
async def test_key_evidence_unconfirmed_ocr_is_blocking_but_ordinary_is_warning(world):
    wp = await add_wp(world, world.target, wp_code="F3-5")
    ordinary = await add_attachment(
        world, world.target, file_name="普通票据.pdf", attachment_type="note",
        ocr_status="completed", ocr_text="未确认文本",
    )
    await world._add(AttachmentWorkingPaper(
        attachment_id=ordinary.id, wp_id=wp.id, association_type="note",
    ))
    ordinary_result = await EvidenceReadinessService(world.db).evaluate_workpaper(wp.id)
    assert ordinary_result.status == "ready"
    assert ordinary_result.warnings and ordinary_result.warnings[0]["blocking"] is False

    ordinary.is_key_evidence = True
    await world.db.flush()
    key_result = await EvidenceReadinessService(world.db).evaluate_workpaper(wp.id)
    assert key_result.status == "not_ready"
    assert "key_evidence_ocr_confirmation" in key_result.missing_types


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expect_hit", [
    ("ready", False), ("not_declared", False), ("not_ready", True), ("unknown", True),
])
async def test_gate_rule_uses_same_four_state(monkeypatch, status, expect_hit):
    project_id = uuid.uuid4()
    blocker = WorkpaperEvidenceReadiness(
        wp_id=uuid.uuid4(), project_id=project_id, wp_code="F3-5", status=status,
    )
    project = ProjectEvidenceReadiness(
        project_id=project_id,
        status=status,
        workpapers=(blocker,) if status in {"not_ready", "unknown"} else (),
        counts={status: 1},
    )

    async def result(self, pid):
        assert pid == project_id
        return project

    monkeypatch.setattr(EvidenceReadinessService, "evaluate_project", result)
    hit = await EvidenceReadinessRule().check(object(), {"project_id": project_id})
    assert (hit is not None) is expect_hit
    if hit is not None:
        assert str(getattr(hit.severity, "value", hit.severity)) == "blocking"
