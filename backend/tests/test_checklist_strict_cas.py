from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.routers.checklist_responses import ChecklistResponseItem, _do_batch_save
from app.services.checklist_response_cas import lock_and_check_versions


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Db:
    def __init__(self, versions: dict[str, datetime]):
        self.versions = versions
        self.locked: list[str] = []

    async def execute(self, _statement, params):
        item_id = str(params["item_id"])
        self.locked.append(item_id)
        value = self.versions.get(item_id)
        return _Result(None if value is None else SimpleNamespace(updated_at=value))


@pytest.mark.asyncio
async def test_strict_client_requires_version_for_existing_row_but_not_new_row():
    stamp = datetime(2026, 11, 1, 1, 2, 3, tzinfo=timezone.utc)
    db = _Db({"existing": stamp})
    items = [
        ChecklistResponseItem(item_id="new", remark="new"),
        ChecklistResponseItem(item_id="existing", remark="changed"),
    ]

    with pytest.raises(HTTPException) as raised:
        await lock_and_check_versions(
            db, uuid.uuid4(), items, require_if_match=True,
        )

    assert raised.value.status_code == 428
    assert raised.value.detail == {
        "code": "version_required",
        "item_id": "existing",
        "server_version": stamp.isoformat(),
        "message": "底稿条目已有更新版本，请刷新后再保存",
        "atomic": True,
    }
    assert db.locked == ["existing", "new"]

    assert await lock_and_check_versions(
        _Db({}),
        uuid.uuid4(),
        [ChecklistResponseItem(item_id="brand-new", remark="new")],
        require_if_match=True,
    ) == {}


@pytest.mark.asyncio
async def test_legacy_client_keeps_lww_during_migration():
    stamp = datetime(2026, 11, 1, 1, 2, 3, tzinfo=timezone.utc)
    existing = await lock_and_check_versions(
        _Db({"existing": stamp}),
        uuid.uuid4(),
        [ChecklistResponseItem(item_id="existing", remark="legacy")],
    )
    assert existing == {"existing": stamp.isoformat()}


@pytest.mark.asyncio
async def test_strict_client_accepts_matching_version_and_rejects_stale_version():
    stamp = datetime(2026, 11, 1, 1, 2, 3, tzinfo=timezone.utc)
    matching = ChecklistResponseItem(
        item_id="existing", remark="ok", if_match=stamp.isoformat(),
    )
    assert await lock_and_check_versions(
        _Db({"existing": stamp}), uuid.uuid4(), [matching], require_if_match=True,
    ) == {"existing": stamp.isoformat()}

    stale = ChecklistResponseItem(item_id="existing", remark="bad", if_match="old")
    with pytest.raises(HTTPException) as raised:
        await lock_and_check_versions(
            _Db({"existing": stamp}), uuid.uuid4(), [stale], require_if_match=True,
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "version_conflict"
    assert raised.value.detail["atomic"] is True


def test_endpoint_returns_428_before_any_write_for_strict_request(monkeypatch):
    """TestClient 真发 PUT，守住 body 开关、依赖接线和 HTTP 状态。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.routers import checklist_responses as router_module

    stamp = datetime(2026, 11, 1, 1, 2, 3, tzinfo=timezone.utc)
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    class EndpointDb(_Db):
        rollback_calls = 0

        async def execute(self, _statement, params):
            if "item_id" not in params:
                return _Result(SimpleNamespace(
                    project_id=project_id, wp_code=None, audit_year=2026,
                ))
            return await super().execute(_statement, params)

        async def rollback(self):
            self.rollback_calls += 1

    db = EndpointDb({"existing": stamp})

    async def allow_gate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(router_module, "enforce_wp_gate", allow_gate)
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_db] = lambda: db
    route = next(route for route in app.routes if route.path.endswith("checklist-responses") and "PUT" in route.methods)
    current_user_dep = next(dep.call for dep in route.dependant.dependencies if dep.name == "current_user")
    app.dependency_overrides[current_user_dep] = lambda: SimpleNamespace(id=uuid.uuid4())

    response = TestClient(app).put(
        f"/api/workpapers/{wp_id}/checklist-responses",
        json={
            "project_id": str(project_id),
            "require_if_match": True,
            "items": [{"item_id": "existing", "remark": "changed"}],
        },
    )

    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "version_required"
    assert db.locked == ["existing"]
    assert db.rollback_calls == 1


@pytest.mark.asyncio
async def test_omitted_wp_ref_preserves_existing_reference_and_explicit_null_clears_it(monkeypatch):
    """隔离 SQLite 执行真实 UPSERT，守住省略与显式 null 的持久化差异。"""
    from app.routers import checklist_responses as router_module

    stamp = "2026-11-05T01:02:03+00:00"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(router_module, "_version_of", lambda _value: "test-version")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE checklist_responses (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    wp_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    conclusion TEXT,
                    remark TEXT,
                    wp_ref TEXT,
                    updated_by TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE (wp_id, item_id)
                )
            """))

        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        async with AsyncSession(engine) as db:
            await db.execute(
                text("""
                    INSERT INTO checklist_responses (
                        id, project_id, wp_id, item_id, conclusion, remark, wp_ref,
                        updated_by, created_at, updated_at
                    ) VALUES (
                        :id, :project_id, :wp_id, :item_id, :conclusion, :remark, :wp_ref,
                        :updated_by, :created_at, :updated_at
                    )
                """),
                {
                    "id": str(uuid.uuid4()),
                    "project_id": str(project_id),
                    "wp_id": str(wp_id),
                    "item_id": "G1-local",
                    "conclusion": "Y",
                    "remark": "原备注",
                    "wp_ref": "existing-reference",
                    "updated_by": str(user.id),
                    "created_at": stamp,
                    "updated_at": stamp,
                },
            )
            await _do_batch_save(
                db,
                wp_id,
                SimpleNamespace(items=[ChecklistResponseItem(item_id="G1-local", remark="只改备注")]),
                user,
                stamp,
                project_id,
                {},
            )
            preserved = await db.execute(
                text("SELECT wp_ref FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id"),
                {"wp_id": str(wp_id), "item_id": "G1-local"},
            )
            assert preserved.scalar_one() == "existing-reference"

            await _do_batch_save(
                db,
                wp_id,
                SimpleNamespace(items=[ChecklistResponseItem(
                    item_id="G1-local", remark="明确清除", wp_ref=None,
                )]),
                user,
                stamp,
                project_id,
                {},
            )
            cleared = await db.execute(
                text("SELECT wp_ref FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id"),
                {"wp_id": str(wp_id), "item_id": "G1-local"},
            )
            assert cleared.scalar_one() is None
    finally:
        await engine.dispose()
