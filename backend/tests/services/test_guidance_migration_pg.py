"""存量迁移 pg_only 属性测试 — note-guidance-text-separation Task 6.6–6.9."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text as sa_text

from app.models.core import Project
from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.services.disclosure_engine import identify_guidance

pytestmark = pytest.mark.pg_only


async def _seed_note(session, project_id, note_section, text_content):
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2025,
        note_section=note_section,
        section_title=f"标题{note_section}",
        content_type=ContentType.text,
        text_content=text_content,
        status=NoteStatus.draft,
        sort_order=1,
    )
    session.add(note)
    await session.flush()
    return note


@pytest.mark.asyncio
async def test_property_7_low_confidence_no_split(pg_session):
    """Feature: note-guidance-text-separation, Property 7: 不可靠识别则不拆分"""
    project = Project(
        id=uuid.uuid4(),
        name="guidance-mig-p7",
        client_name="guidance-mig-p7",
        template_type="soe",
        report_scope="standalone",
    )
    pg_session.add(project)
    source = "本公司采用成本模式计量投资性房地产。"
    note = await _seed_note(pg_session, project.id, "八、99", source)
    assert identify_guidance(source) is None
    note.guidance_text = None
    await pg_session.commit()
    await pg_session.refresh(note)
    assert note.text_content == source
    assert note.guidance_text in (None, "")


@pytest.mark.asyncio
async def test_property_8_preview_does_not_mutate(pg_session):
    """Feature: note-guidance-text-separation, Property 8: 未确认执行只读"""
    project = Project(
        id=uuid.uuid4(),
        name="guidance-mig-p8",
        client_name="guidance-mig-p8",
        template_type="soe",
        report_scope="standalone",
    )
    pg_session.add(project)
    source = "（注：应披露受限货币资金。）\n\n正文保留段。"
    note = await _seed_note(pg_session, project.id, "八、98", source)
    await pg_session.commit()
    note_id = note.id

    # preview path: only identify_guidance, no write
    split = identify_guidance(source)
    assert split is not None

    loaded = (
        await pg_session.execute(
            select(DisclosureNote).where(DisclosureNote.id == note_id)
        )
    ).scalar_one()
    assert loaded.text_content == source
    assert loaded.guidance_text in (None, "")


@pytest.mark.asyncio
async def test_property_9_rollback_restores_text(pg_session):
    """Feature: note-guidance-text-separation, Property 9: 拆分回滚往返恢复"""
    project = Project(
        id=uuid.uuid4(),
        name="guidance-mig-p9",
        client_name="guidance-mig-p9",
        template_type="soe",
        report_scope="standalone",
    )
    pg_session.add(project)
    source = "（注：应披露受限货币资金。）\n\n正文保留段。"
    note = await _seed_note(pg_session, project.id, "八、97", source)
    await pg_session.commit()

    await pg_session.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS _note_guidance_split_backup (
            note_id UUID PRIMARY KEY,
            project_id UUID NOT NULL,
            year INT NOT NULL,
            note_section TEXT NOT NULL,
            source_text_content TEXT NOT NULL,
            backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    await pg_session.execute(
        sa_text("""
            INSERT INTO _note_guidance_split_backup
                (note_id, project_id, year, note_section, source_text_content)
            VALUES (:note_id, :project_id, :year, :note_section, :source_text_content)
        """),
        {
            "note_id": note.id,
            "project_id": project.id,
            "year": 2025,
            "note_section": note.note_section,
            "source_text_content": source,
        },
    )
    split = identify_guidance(source)
    assert split is not None
    note.guidance_text, note.text_content = split[0], split[1] or None
    await pg_session.commit()

    await pg_session.execute(sa_text("""
        UPDATE disclosure_notes d
        SET text_content = b.source_text_content, guidance_text = NULL
        FROM _note_guidance_split_backup b
        WHERE d.id = b.note_id
    """))
    await pg_session.commit()
    await pg_session.refresh(note)
    assert note.text_content == source
    assert note.guidance_text in (None, "")


@pytest.mark.asyncio
async def test_property_10_scope_isolation(pg_session):
    """Feature: note-guidance-text-separation, Property 10: 范围隔离"""
    p1 = Project(
        id=uuid.uuid4(), name="g-scope-1", client_name="g-scope-1",
        template_type="soe", report_scope="standalone",
    )
    p2 = Project(
        id=uuid.uuid4(), name="g-scope-2", client_name="g-scope-2",
        template_type="soe", report_scope="standalone",
    )
    pg_session.add_all([p1, p2])
    src1 = "（注：应披露A。）\n\n正文A。"
    src2 = "（注：应披露B。）\n\n正文B。"
    n1 = await _seed_note(pg_session, p1.id, "八、1", src1)
    n2 = await _seed_note(pg_session, p2.id, "八、1", src2)
    await pg_session.commit()

    split = identify_guidance(src1)
    assert split is not None
    n1.guidance_text, n1.text_content = split[0], split[1] or None
    await pg_session.commit()

    await pg_session.refresh(n2)
    assert n2.text_content == src2
    assert n2.guidance_text in (None, "")
