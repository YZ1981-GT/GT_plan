"""R4：已授权只读成员经真实依赖链查询过滤；不连接外部 HTTP。"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.dataset_models import EventOutboxDLQ, ImportEventOutbox
from app.routers import formula_settings as fs_router

from ._env import add_member, add_project, add_user, make_db
from ._r4_test_data import outbox_row


@pytest.fixture
async def filtered_api():
    async with make_db(extra_models=(ImportEventOutbox, EventOutboxDLQ)) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】R4 过滤接口")
            reader = await add_user(db, "r4-reader", "auditor")
            await add_member(db, pid, reader, "readonly")
            target = outbox_row(pid, domain="note", token="batch-1")
            sibling = outbox_row(pid, domain="note", token="batch-1", minutes=1)
            db.add_all([target, sibling, outbox_row(pid, year=2024, domain="note"),
                        outbox_row(pid, domain="report"), outbox_row(pid, domain="note", token="batch-10")])
            await db.commit()
        app = FastAPI()
        app.include_router(fs_router.project_router)

        async def isolated_db():
            async with factory() as db:
                yield db

        async def authenticated_reader():
            return reader

        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[get_current_user] = authenticated_reader
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://synthetic.invalid") as client:
            yield client, pid, target.id, sibling.id

async def test_authorized_readonly_member_receives_combined_exact_filters(filtered_api):
    client, pid, target_id, sibling_id = filtered_api
    path = f"/api/projects/{pid}/formula-settings/propagation"
    params = {"year": 2025, "domain": "note", "publish_token": "batch-1"}
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text
    result = response.json()
    assert {r["outbox_id"] for r in result["receipts"]} == {str(target_id), str(sibling_id)}
    assert result["counts"] == {"pending": 0, "failed": 0, "published": 2}
    response = await client.get(path, params={**params, "outbox_id": str(target_id)})
    assert response.status_code == 200, response.text
    assert [r["outbox_id"] for r in response.json()["receipts"]] == [str(target_id)]


async def test_authorized_reader_unknown_outbox_filter_returns_empty_not_recent(filtered_api):
    client, pid, _target_id, _sibling_id = filtered_api
    response = await client.get(
        f"/api/projects/{pid}/formula-settings/propagation", params={"outbox_id": str(uuid.uuid4())})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["receipts"] == []
    assert result["counts"] == {"pending": 0, "failed": 0, "published": 0}


@pytest.mark.parametrize("params, status", [
    ({"year": 1899}, 422), ({"year": 10000}, 422),
    ({"outbox_id": "not-a-uuid"}, 422), ({"publish_token": ""}, 422),
    ({"domain": "missing-domain"}, 404),
])
async def test_authorized_reader_filter_validation(filtered_api, params, status):
    client, pid, _target_id, _sibling_id = filtered_api
    response = await client.get(f"/api/projects/{pid}/formula-settings/propagation", params=params)
    assert response.status_code == status, response.text
