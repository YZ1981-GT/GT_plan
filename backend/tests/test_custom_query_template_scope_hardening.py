"""Template scope/API hardening regression tests.

Feature: advanced-query-disclosure-integration-hardening, Property P7.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from app.routers import custom_query as router_mod
from app.services.custom_query.template_scope_adapter import TemplateScopeAdapter


class FakeDb:
    def __init__(self, template=None) -> None:
        self.template = template
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    async def get(self, _model, _key):
        return self.template

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def refresh(self, _value):
        self.refresh_calls += 1


def make_user(*, user_id=None, role="auditor"):
    return SimpleNamespace(id=user_id or uuid.uuid4(), role=role)


def make_template(*, owner_id=None, scope="private", config=None, shared=None):
    owner = owner_id or uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(), name="中文模板", description=None,
        data_source="workpaper", config=config or {}, scope=scope,
        shared_project_ids=shared or [], creator_id=owner, created_by=owner,
        created_at=datetime(2026, 7, 15), updated_at=datetime(2026, 7, 15),
    )

def test_scope_normalization_and_serialization_are_canonical():
    project_id = uuid.uuid4()
    normalized = router_mod._normalize_template_scope(
        "project", [str(project_id), str(project_id)], {}
    )
    assert normalized.scope == "project"
    assert normalized.shared_project_ids == (project_id,)

    legacy = make_template(scope="global")
    payload = router_mod._serialize_template(legacy, legacy.creator_id)
    assert payload["scope"] == "public"
    assert payload["shared_project_ids"] == []


def test_team_requires_config_project_anchor_and_does_not_reuse_shared_ids():
    with pytest.raises(HTTPException) as exc:
        router_mod._normalize_template_scope("team", [str(uuid.uuid4())], {})
    assert exc.value.status_code == 422
    assert exc.value.detail["error_code"] == "TEMPLATE_SCOPE_INVALID"

    anchor = uuid.uuid4()
    normalized = router_mod._normalize_template_scope(
        "team", [str(uuid.uuid4())], {"project_id": str(anchor)}
    )
    assert normalized.scope == "team"
    assert normalized.shared_project_ids == ()


@pytest.mark.asyncio
async def test_scope_edit_authorizes_each_project(monkeypatch):
    project_ids = tuple(sorted({uuid.uuid4(), uuid.uuid4()}, key=str))
    checked = []

    async def fake_dependency(*, project_id, current_user, db):
        checked.append(project_id)

    monkeypatch.setattr(
        router_mod, "require_project_access", lambda _operation: fake_dependency
    )
    await router_mod._assert_template_scope_edit(
        TemplateScopeAdapter.normalize("project", list(reversed(project_ids))),
        current_user=make_user(), db=FakeDb(),
    )
    assert checked == list(project_ids)


@pytest.mark.asyncio
async def test_create_rolls_back_before_write_when_share_authorization_fails(monkeypatch):
    db = FakeDb()
    user = make_user()
    save = AsyncMock()

    async def deny(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN"})

    monkeypatch.setattr(router_mod, "_assert_template_scope_edit", deny)
    monkeypatch.setattr(router_mod.template_service, "save_template", save)
    body = router_mod.TemplateCreateRequest(
        name="项目共享模板", data_source="workpaper", config={},
        scope="project", shared_project_ids=[str(uuid.uuid4())],
    )
    with pytest.raises(HTTPException) as exc:
        await router_mod.create_template(body=body, db=db, current_user=user)
    assert exc.value.status_code == 403
    assert db.rollback_calls == 1
    save.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_non_owner_including_admin_cannot_update_or_delete(monkeypatch, operation):
    owner = uuid.uuid4()
    template = make_template(owner_id=owner, scope="public")
    db = FakeDb(template)
    admin = make_user(role="admin")
    monkeypatch.setattr(router_mod, "_assert_template_visible", AsyncMock())

    if operation == "update":
        with pytest.raises(HTTPException) as exc:
            await router_mod.update_template(
                template_id=str(template.id),
                body=router_mod.TemplateUpdateRequest(name="越权修改"),
                db=db, current_user=admin,
            )
        assert exc.value.detail["error_code"] == "ONLY_OWNER_CAN_UPDATE"
    else:
        with pytest.raises(HTTPException) as exc:
            await router_mod.delete_template(
                template_id=str(template.id), db=db, current_user=admin
            )
        assert exc.value.detail["error_code"] == "ONLY_OWNER_CAN_DELETE"
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_execute_template_reauthorizes_target_and_reuses_main_execute(monkeypatch):
    owner = uuid.uuid4()
    target_project = uuid.uuid4()
    template = make_template(
        owner_id=owner,
        config={
            "year": 2025,
            "filters": {"科目名称": "应收账款"},
            "selected_columns": ["科目编码", "期末余额"],
            "page_size": 20,
            "offset": 20,
            "sort": [{"field": "期末余额", "direction": "desc"}],
            "group": {"dimensions": ["科目编码"]},
            "pivot": {"rows": ["科目编码"]},
            "acnr_targets": ["D2/D2-2/A1"],
        },
    )
    db = FakeDb(template)
    user = make_user(user_id=owner)
    assert_visible = AsyncMock()
    captured = {}

    async def fake_execute(query_body, response, execute_db, execute_user):
        captured.update(
            query=query_body, response=response, db=execute_db, user=execute_user
        )
        return {"rows": [], "columns": [], "total": 0}

    monkeypatch.setattr(router_mod.template_service, "assert_executable", assert_visible)
    monkeypatch.setattr(router_mod, "execute_query", fake_execute)
    response = Response()
    result = await router_mod.execute_template(
        template_id=str(template.id),
        body=router_mod.TemplateExecuteRequest(project_id=str(target_project)),
        response=response, db=db, current_user=user,
    )

    assert result["total"] == 0
    assert_visible.assert_awaited_once_with(template, user=user, db=db)
    query = captured["query"]
    assert query.project_id == str(target_project)
    assert query.year == 2025
    assert query.filters == {"科目名称": "应收账款"}
    assert query.columns == ["科目编码", "期末余额"]
    assert query.offset == 20 and query.limit == 20
    assert query.sort[0].field == "期末余额"
    assert query.acnr_targets == ["D2/D2-2/A1"]
    assert captured["db"] is db and captured["user"] is user
