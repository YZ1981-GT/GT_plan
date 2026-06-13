"""Property 11: 基线回写抑制 stale — note-guidance-text-separation Task 7.3."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.audit_platform_models import DeliverableSectionState
from app.models.core import Project
from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.services.deliverable_section_state_service import DeliverableSectionStateService
from app.services.disclosure_engine import identify_guidance

pytestmark = pytest.mark.pg_only


@pytest.mark.asyncio
async def test_property_11_baseline_rewrite_no_stale_after_guidance_removal(pg_session):
    """Feature: note-guidance-text-separation, Property 11: 基线回写抑制误判 stale"""
    project = Project(
        id=uuid.uuid4(),
        name="guidance-stale-p11",
        client_name="guidance-stale-p11",
        template_type="soe",
        report_scope="standalone",
    )
    pg_session.add(project)
    section_code = "八、96"
    source = "（注：应披露受限货币资金详情。）\n\n本公司货币资金无受限。"
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2025,
        note_section=section_code,
        section_title="货币资金",
        content_type=ContentType.text,
        text_content=source,
        status=NoteStatus.draft,
        sort_order=1,
    )
    pg_session.add(note)
    task_id = uuid.uuid4()
    svc = DeliverableSectionStateService(pg_session)
    old_hash = await svc.compute_source_snapshot_hash(project.id, 2025, section_code)
    state = DeliverableSectionState(
        id=uuid.uuid4(),
        word_export_task_id=task_id,
        project_id=project.id,
        year=2025,
        section_code=section_code,
        source_snapshot_hash=old_hash,
        is_stale=False,
    )
    pg_session.add(state)
    await pg_session.flush()

    split = identify_guidance(source)
    assert split is not None
    guidance, remaining = split
    note.guidance_text = guidance
    note.text_content = remaining or None
    new_hash = await svc.compute_source_snapshot_hash(project.id, 2025, section_code)
    await svc.clear_section_stale(task_id, section_code, new_hash)
    await pg_session.commit()

    drift = await svc.detect_upstream_drift(task_id, project.id, 2025, section_code)
    assert drift is False

    loaded = (
        await pg_session.execute(
            select(DeliverableSectionState).where(
                DeliverableSectionState.word_export_task_id == task_id,
                DeliverableSectionState.section_code == section_code,
            )
        )
    ).scalar_one()
    assert loaded.is_stale is False
    assert loaded.source_snapshot_hash == new_hash
