"""合同证据查询、绑定/改绑、幂等和解绑的端点闭环。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.models.wp_optimization_models import EvidenceLink
from app.services.contract_evidence import normalize_contract_key
from tests.attachment_evidence_intake._helpers import evidence_app
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_wp,
    sqlite_attachment_world,
)


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as value:
        yield value


@pytest.mark.asyncio
async def test_bind_updates_existing_position_without_leaving_old_contract_key(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D4-12")
    attachment = await add_attachment(world, world.target, attachment_type="contract")
    link = await world._add(EvidenceLink(
        wp_id=wp.id,
        attachment_id=attachment.id,
        sheet_name="D4-12",
        cell_ref="row:c-1",
        evidence_type="contract",
        contract_key=normalize_contract_key('["OLD","旧对方"]'),
        created_by=who.user.id,
    ))
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        first = await client.put(
            f"/api/projects/{world.target.id}/workpapers/{wp.id}/evidence/contract-link",
            json={
                "attachment_id": str(attachment.id),
                "contract_key": '["NEW-001","新对方"]',
                "sheet_name": "D4-12",
                "cell_ref": "row:c-1",
            },
        )
        again = await client.put(
            f"/api/projects/{world.target.id}/workpapers/{wp.id}/evidence/contract-link",
            json={
                "attachment_id": str(attachment.id),
                "contract_key": '["NEW-001","新对方"]',
                "sheet_name": "D4-12",
                "cell_ref": "row:c-1",
            },
        )
    assert first.status_code == again.status_code == 200, (first.text, again.text)
    rows = list((await world.db.execute(
        sa.select(EvidenceLink).where(
            EvidenceLink.wp_id == wp.id,
            EvidenceLink.attachment_id == attachment.id,
        )
    )).scalars().all())
    assert len(rows) == 1 and rows[0].id == link.id
    assert rows[0].contract_key == normalize_contract_key('["NEW-001","新对方"]')
    assert rows[0].voucher_key is None and rows[0].evidence_type == "contract"


@pytest.mark.asyncio
async def test_contract_query_calls_visible_cross_workpaper_service(world, monkeypatch):
    who = await world.edit_member()
    source = await add_wp(world, world.target, wp_code="D4-11")
    target = await add_wp(world, world.target, wp_code="D4-12")
    attachment = await add_attachment(world, world.target, file_name="合同原件.pdf", attachment_type="contract")
    key = normalize_contract_key('["HT-001","甲方"]')
    await world._add(EvidenceLink(
        wp_id=source.id, attachment_id=attachment.id, evidence_type="contract",
        contract_key=key, created_by=who.user.id,
    ))

    import app.services.contract_evidence as contract_module

    async def all_visible(_db, _user, ids):
        return set(ids)

    monkeypatch.setattr(contract_module, "_visible_wp_ids", all_visible)
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        response = await client.post(
            f"/api/projects/{world.target.id}/workpapers/{target.id}/evidence/contract-query",
            json={"keys": [key]},
        )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence[key][0]["working_paper_id"] == str(source.id)
    assert evidence[key][0]["attachments"][0]["id"] == str(attachment.id)


@pytest.mark.asyncio
async def test_bind_rejects_cross_project_attachment_and_delete_keeps_file_record(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D4-12")
    other = await world.other_project()
    foreign = await add_attachment(world, other, attachment_type="contract")
    local = await add_attachment(world, world.target, attachment_type="contract")
    link = await world._add(EvidenceLink(
        wp_id=wp.id, attachment_id=local.id, evidence_type="contract",
        contract_key=normalize_contract_key("HT-LOCAL"), created_by=who.user.id,
    ))
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        rejected = await client.put(
            f"/api/projects/{world.target.id}/workpapers/{wp.id}/evidence/contract-link",
            json={"attachment_id": str(foreign.id), "contract_key": "HT-X"},
        )
        removed = await client.delete(
            f"/api/projects/{world.target.id}/workpapers/{wp.id}/evidence/{link.id}",
        )
    assert rejected.status_code == 404
    assert removed.status_code == 200
    assert await world.db.get(EvidenceLink, link.id) is None
    assert await world.db.get(Attachment, local.id) is not None


@pytest.mark.asyncio
async def test_contract_query_caps_keys_at_500(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D4-12")
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        response = await client.post(
            f"/api/projects/{world.target.id}/workpapers/{wp.id}/evidence/contract-query",
            json={"keys": [f"HT-{i}" for i in range(501)]},
        )
    assert response.status_code == 422
