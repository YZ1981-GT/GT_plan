"""platform-release-blocker-closure Tasks 10-13: security regression guards."""
from __future__ import annotations

import inspect
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient


ROOT = Path(__file__).resolve().parents[1]


class _Db:
    def __init__(self):
        self.commit = AsyncMock()


@pytest.mark.asyncio
async def test_metabase_embed_requires_admin_or_project_permission(monkeypatch):
    from app.models.base import UserRole
    from app.routers import metabase

    fake_service = SimpleNamespace(get_embed_url=lambda *args: "signed")
    monkeypatch.setattr(metabase, "_svc", lambda *_args, **_kwargs: fake_service)
    permission = AsyncMock()
    monkeypatch.setattr(metabase, "assert_project_permission", permission)
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.auditor)

    with pytest.raises(HTTPException) as denied:
        await metabase.get_embed_url(db=_Db(), current_user=user)
    assert denied.value.status_code == 403

    project_id = uuid.uuid4()
    result = await metabase.get_embed_url(
        project_id=project_id, db=_Db(), current_user=user,
    )
    assert result == {"embed_url": "signed"}
    permission.assert_awaited_once_with(ANY, user, project_id, "readonly")


def test_release_config_rejects_default_metabase_secret():
    from pydantic import ValidationError
    from app.core.config import DEFAULT_METABASE_EMBEDDING_SECRET, Settings

    with pytest.raises(ValidationError, match="METABASE_EMBEDDING_SECRET"):
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="x" * 32,
            METABASE_EMBEDDING_SECRET=DEFAULT_METABASE_EMBEDDING_SECRET,
            _env_file=None,
        )


def test_debug_routes_removed_from_main_source():
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "/api/_debug/" not in source
    assert "debug_a51" not in source


@pytest.mark.asyncio
async def test_review_reply_uses_authenticated_actor_and_path_scope(monkeypatch):
    from app.routers import wp_review

    actor = SimpleNamespace(id=uuid.uuid4())
    wp_id, review_id = uuid.uuid4(), uuid.uuid4()
    reply = AsyncMock(return_value={"id": str(review_id)})
    monkeypatch.setattr(wp_review.WpReviewService, "reply", reply)
    db = _Db()
    body = wp_review.ReplyRequest.model_validate({
        "reply_text": "已补充", "replier_id": str(uuid.uuid4()),
    })
    await wp_review.reply_review(wp_id, review_id, body, db, actor)
    kwargs = reply.await_args.kwargs
    assert kwargs["working_paper_id"] == wp_id
    assert kwargs["review_id"] == review_id
    assert kwargs["replier_id"] == actor.id
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_lookup_binds_review_to_live_workpaper():
    from app.services.wp_review_service import WpReviewService

    statement = None
    class Result:
        def scalar_one_or_none(self): return None
    class Db:
        async def execute(self, value):
            nonlocal statement
            statement = value
            return Result()
    with pytest.raises(ValueError, match="复核意见不存在"):
        await WpReviewService._get_live_review(
            Db(), working_paper_id=uuid.uuid4(), review_id=uuid.uuid4(),
        )
    sql = str(statement)
    assert "review_records.id" in sql
    assert "review_records.working_paper_id" in sql
    assert "review_records.is_deleted" in sql

@pytest.mark.asyncio
async def test_user_formula_v2_endpoints_are_authenticated_stable_410():
    from app.deps import get_current_user
    from app.routers.wp_user_formulas_v2 import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in (
            ("GET", "/api/workpapers/wp1/user-formulas/v2"),
            ("POST", "/api/workpapers/wp1/user-formulas/v2:batchMutate"),
            ("GET", "/api/workpapers/wp1/user-formulas/v2/f1/history"),
        ):
            response = await client.request(method, path, json={"capabilitySnapshot": {"allowed": True}})
            assert response.status_code == 410
            assert response.json()["detail"]["code"] == "USER_FORMULA_V2_RETIRED"


@pytest.mark.asyncio
async def test_ledger_sse_query_is_project_bound(monkeypatch):
    from app.routers import ledger_import_v2

    seen = []
    class Result:
        def scalar_one_or_none(self): return None
    class Session:
        async def execute(self, statement):
            seen.append(statement)
            return Result()
    @asynccontextmanager
    async def session_factory():
        yield Session()
    monkeypatch.setattr(ledger_import_v2, "async_session", session_factory)

    project_id, job_id = uuid.uuid4(), uuid.uuid4()
    chunk = await anext(ledger_import_v2._sse_generator(project_id, job_id))
    assert "job_not_found" in chunk
    sql = str(seen[0])
    assert "import_jobs.id" in sql and "import_jobs.project_id" in sql


def test_review_config_dependencies_are_project_scoped():
    from app.routers import review_config

    get_route = next(
        route for route in review_config.router.routes
        if route.path == "/api/projects/{project_id}/review-config" and "GET" in route.methods
    )
    put_route = next(
        route for route in review_config.router.routes
        if route.path == get_route.path and "PUT" in route.methods
    )

    def project_permission(route):
        for dependency in route.dependant.dependencies:
            closure = inspect.getclosurevars(dependency.call).nonlocals
            if "min_permission" in closure:
                return closure["min_permission"]
        return None

    assert project_permission(get_route) == "readonly"
    assert project_permission(put_route) == "edit"
    assert review_config.DEFAULT_REVIEW_CONFIG["level_roles"] == {"L1": "manager", "L2": "partner"}


def test_review_level_roles_match_wp_gate_supervisors():
    """复核层级只能配给底稿门按主管放行的角色。

    复核状态 PUT 经 dedicated_wp_gate 映射为 dedicated_write：主管全权放行，审计员只有作为编制人（lead）才有写权
    （= 自复核），作为行复核人（reviewer grant）写动作不在白名单 ⇒ 404。原校验放行 auditor，按此配置审计员复核必定失败。
    """
    import pytest
    from pydantic import ValidationError

    from app.routers.review_config import REVIEW_LEVEL_ROLES, ReviewConfigUpdate
    from app.services.assignment_service import ROLE_MAP
    from app.services.wp_visibility.effective_scope import SUPERVISOR_ROLES

    assert REVIEW_LEVEL_ROLES == {"manager", "partner", "qc", "eqcr"}
    # 每个可配角色作为委派角色时都被底稿门判为主管（eqcr 经 ROLE_MAP 映射为 partner）
    for role in REVIEW_LEVEL_ROLES:
        assert role in ROLE_MAP and role.lower() in SUPERVISOR_ROLES, role

    ReviewConfigUpdate(levels=4, level_roles={"L1": "manager", "L2": "partner", "L3": "eqcr", "L4": "qc"})
    for bad in ("auditor", "readonly"):
        with pytest.raises(ValidationError, match="非法角色"):
            ReviewConfigUpdate(levels=2, level_roles={"L1": bad, "L2": "partner"})
