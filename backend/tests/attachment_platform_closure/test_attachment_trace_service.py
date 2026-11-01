"""统一溯源直接消费底稿权威附件关系，不依赖双写。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from pydantic import ValidationError

from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from app.schemas.attachment_lineage_schema import AttachmentLineageCreate
from app.services.attachment_trace_service import AttachmentTraceService
from app.services.unified_lineage_service import UnifiedLineageService
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as value:
        await value.db.run_sync(
            lambda session: AttachmentLineage.__table__.create(session.connection(), checkfirst=True)
        )
        async def ready(_db):
            return True
        monkeypatch.setattr("app.services.attachment_trace_service.lineage_project_column_ready", ready)
        yield value


@pytest.mark.asyncio
async def test_wp_trace_reads_evidence_whole_and_reference_without_lineage_double_write(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D4-1")
    similar = await add_wp(world, world.target, wp_code="D4-10")
    row_attachment = await add_attachment(world, world.target, file_name="行证据.pdf")
    whole_attachment = await add_attachment(world, world.target, file_name="整稿证据.pdf")
    reference = await add_attachment(world, world.target, file_name="兼容证据.pdf")
    other = await add_attachment(world, world.target, file_name="相似编码证据.pdf")
    reference.reference_type = "working_paper"
    reference.reference_id = wp.id
    await world._add(EvidenceLink(
        wp_id=wp.id, attachment_id=row_attachment.id, sheet_name="D4-1", cell_ref="B5",
        evidence_type="contract", created_by=who.user.id,
    ))
    await world._add(AttachmentWorkingPaper(
        attachment_id=whole_attachment.id, wp_id=wp.id, association_type="evidence",
    ))
    await world._add(EvidenceLink(
        wp_id=similar.id, attachment_id=other.id, sheet_name="D4-10", cell_ref="B5",
        created_by=who.user.id,
    ))

    rows = await AttachmentTraceService(world.db).for_object(world.target.id, "wp_cell", "D4-1!B5")
    names = {row["file_name"] for row in rows}
    assert names == {"行证据.pdf", "整稿证据.pdf", "兼容证据.pdf"}
    assert all(row["source"] != "attachment_lineage" for row in rows)

    unified = await UnifiedLineageService(world.db)._query_attachments(world.target.id, "wp_cell", "D4-1!B5")
    assert {row["attachment_id"] for row in unified} == {str(row_attachment.id), str(whole_attachment.id), str(reference.id)}


@pytest.mark.asyncio
async def test_trace_filters_cross_project_soft_deleted_and_similar_codes(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3")
    other_project = await world.other_project()
    other_wp = await add_wp(world, other_project, wp_code="F3")
    deleted = await add_attachment(world, world.target, file_name="已删.pdf", is_deleted=True)
    foreign = await add_attachment(world, other_project, file_name="他项目.pdf")
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=deleted.id, cell_ref="B5", created_by=who.user.id))
    await world._add(EvidenceLink(wp_id=other_wp.id, attachment_id=foreign.id, cell_ref="B5", created_by=who.user.id))
    assert await AttachmentTraceService(world.db).for_object(world.target.id, "wp_cell", "F3!B5") == []


@pytest.mark.asyncio
async def test_output_lineage_filters_project_and_is_deduplicated(world):
    attachment = await add_attachment(world, world.target, file_name="报表依据.pdf")
    await world._add(AttachmentLineage(
        attachment_id=attachment.id, project_id=world.target.id,
        target_type="report_row", target_ref="BS-001",
    ))
    await world._add(AttachmentLineage(
        attachment_id=attachment.id, project_id=world.target.id,
        target_type="report_row", target_ref="BS-001!detail",
    ))
    rows = await AttachmentTraceService(world.db).for_object(world.target.id, "report_row", "BS-001")
    assert len(rows) == 2  # 两个稳定输出位置保留，不在 service 内伪造同一关系
    assert {row["attachment_id"] for row in rows} == {str(attachment.id)}


def test_lineage_create_requires_stable_nonempty_ref_and_allows_deliverable_section():
    with pytest.raises(ValidationError):
        AttachmentLineageCreate(target_type="report_row", target_ref="   ")
    model = AttachmentLineageCreate(target_type="deliverable_section", target_ref="task-1:五、1")
    assert model.target_ref == "task-1:五、1"


@pytest.mark.asyncio
async def test_attachment_lineage_route_is_idempotent(world, monkeypatch):
    import app.routers.attachment_lineage as route_module

    attachment = await add_attachment(world, world.target, file_name="附注依据.pdf")
    user = (await world.edit_member()).user

    async def ready(_db):
        return None

    async def visible(_db, _user, _attachment_id):
        return world.target.id

    async def allow(*_args, **_kwargs):
        return None

    monkeypatch.setattr(route_module, "ensure_lineage_project_column", ready)
    monkeypatch.setattr(route_module, "_visible_attachment_project", visible)
    monkeypatch.setattr(route_module, "assert_project_permission", allow)
    body = AttachmentLineageCreate(target_type="note_section", target_ref="五、1")
    first = await route_module.link_attachment(attachment.id, body, world.db, user)
    second = await route_module.link_attachment(attachment.id, body, world.db, user)
    count = (await world.db.execute(sa.select(sa.func.count()).select_from(AttachmentLineage))).scalar_one()
    assert first.id == second.id and count == 1
