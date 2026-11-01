"""函证附件原子上传、补偿、能力回执与回填归属。"""
from __future__ import annotations

import io
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.attachment_models import Attachment
from app.models.confirmation_models import ConfirmationActionLog, ConfirmationAttachmentLink
from app.routers.confirmations import router
from app.services import confirmation_evidence_service
from app.services.confirmation_scope_gate import confirmation_project_gate
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_confirmation,
    sqlite_attachment_world,
)

PDF = b"%PDF-1.4\n%confirmation\n"


def app() -> FastAPI:
    value = FastAPI()
    value.include_router(router, prefix="/api")

    async def allow_gate():
        return None

    value.dependency_overrides[confirmation_project_gate] = allow_gate
    return value


@asynccontextmanager
async def client_for(world, user):
    api = app()

    async def db_override():
        yield world.db

    async def user_override():
        return user

    api.dependency_overrides[get_db] = db_override
    api.dependency_overrides[get_current_user] = user_override
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    monkeypatch.setattr(settings, "ATTACHMENT_PRIMARY_STORAGE", "local")
    monkeypatch.setattr(settings, "PAPERLESS_URL", "")
    monkeypatch.setattr(settings, "PAPERLESS_TOKEN", "")
    async with sqlite_attachment_world(monkeypatch) as value:
        yield value, root


def upload_url(world, confirmation_id):
    return f"/api/projects/{world.target.id}/confirmations/{confirmation_id}/attachments/upload"


@pytest.mark.asyncio
async def test_atomic_upload_creates_file_attachment_link_reference_and_log(world):
    value, root = world
    identity = await value.edit_member()
    confirmation = await add_confirmation(value, value.target)
    async with client_for(value, identity.user) as client:
        response = await client.post(
            upload_url(value, confirmation.id),
            files={"file": ("发函.pdf", io.BytesIO(PDF), "application/pdf")},
            data={"role": "outbound"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    attachment_id = uuid.UUID(body["attachment_id"])
    attachment = await value.db.get(Attachment, attachment_id)
    assert attachment is not None
    assert attachment.reference_type == "confirmation_list"
    assert attachment.reference_id == confirmation.id
    link = (await value.db.execute(sa.select(ConfirmationAttachmentLink).where(
        ConfirmationAttachmentLink.attachment_id == attachment_id,
    ))).scalar_one()
    assert link.confirmation_id == confirmation.id and link.role == "outbound"
    logs = (await value.db.execute(sa.select(ConfirmationActionLog).where(
        ConfirmationActionLog.attachment_id == attachment_id,
    ))).scalars().all()
    assert len(logs) == 1 and logs[0].action == "attachment_link"
    assert list((root / str(value.target.id)).rglob("发函.pdf"))


@pytest.mark.asyncio
async def test_inbound_pairing_is_validated_before_any_file_is_written(world):
    value, root = world
    identity = await value.edit_member()
    confirmation = await add_confirmation(value, value.target)
    async with client_for(value, identity.user) as client:
        response = await client.post(
            upload_url(value, confirmation.id),
            files={"file": ("回函.pdf", io.BytesIO(PDF), "application/pdf")},
            data={"role": "inbound"},
        )
    assert response.status_code == 400
    assert (await value.db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0
    assert not root.exists() or not list(root.rglob("*.*"))


@pytest.mark.asyncio
async def test_link_failure_rolls_back_database_and_compensates_local_file(world, monkeypatch):
    value, root = world
    identity = await value.edit_member()
    confirmation = await add_confirmation(value, value.target)

    async def fail_link(*args, **kwargs):
        raise RuntimeError("forced link failure")

    monkeypatch.setattr(confirmation_evidence_service, "link_attachment", fail_link)
    async with client_for(value, identity.user) as client:
        response = await client.post(
            upload_url(value, confirmation.id),
            files={"file": ("待补偿.pdf", io.BytesIO(PDF), "application/pdf")},
            data={"role": "outbound"},
        )
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["storage_cleanup"] == {"deleted": 1, "remote_deleted": 0, "failed": 0}
    assert (await value.db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0
    assert not list(root.rglob("待补偿.pdf"))


@pytest.mark.asyncio
async def test_list_capability_and_refreshable_comparison_follow_actor_role(world):
    value, _root = world
    manager = await value.member("edit", "manager", global_role="manager")
    confirmation = await add_confirmation(value, value.target)
    outbound = await add_attachment(value, value.target, attachment_type="confirmation")
    inbound = await add_attachment(
        value, value.target, attachment_type="confirmation",
        ocr_status="completed",
    )
    inbound.ocr_fields_cache = {
        "reply_amount": 99.0,
        "reply_date": "2025-12-31",
        "match_verdict": "matched",
        "requires_human_confirmation": True,
    }
    await confirmation_evidence_service.link_attachment(
        value.db, confirmation_id=confirmation.id, attachment_id=outbound.id,
        role="outbound", actor_user_id=manager.user.id,
    )
    await confirmation_evidence_service.link_attachment(
        value.db, confirmation_id=confirmation.id, attachment_id=inbound.id,
        role="inbound", actor_user_id=manager.user.id,
    )
    await value.db.commit()

    url = f"/api/projects/{value.target.id}/confirmations/{confirmation.id}/attachments"
    async with client_for(value, manager.user) as client:
        response = await client.get(url)
    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    reply = next(row for row in rows if row["role"] == "inbound")
    assert reply["can_apply_reply"] is True
    assert reply["ocr_compare"]["reply_amount"] == 99.0
    assert reply["backfill_defaults"] == {
        "confirmed_amount": 99.0, "reply_date": "2025-12-31", "target_status": "matched",
    }

    auditor = await value.member("edit", "auditor", global_role="auditor")
    async with client_for(value, auditor.user) as client:
        response = await client.get(url)
    reply = next(row for row in response.json()["items"] if row["role"] == "inbound")
    assert reply["can_apply_reply"] is False
    assert "经理及以上" in reply["apply_reply_block_reason"]


@pytest.mark.asyncio
async def test_apply_reply_rejects_same_project_attachment_not_linked_as_inbound(world):
    value, _root = world
    identity = await value.member("edit", "manager", global_role="manager")
    confirmation = await add_confirmation(value, value.target)
    foreign = await add_attachment(value, value.target, attachment_type="confirmation")
    foreign.ocr_fields_cache = {"requires_human_confirmation": True, "reply_amount": 1}
    with pytest.raises(ValueError, match="不是本函证的回函件"):
        await confirmation_evidence_service.apply_reply(
            value.db,
            confirmation_id=confirmation.id,
            attachment_id=foreign.id,
            confirmed_amount=1,
            reply_date=None,
            target_status="matched",
            actor_user_id=identity.user.id,
        )
