"""附注内容模板端点安全矩阵（Task 45 / R-03 / R-04）：TestClient 真发请求，鉴权依赖链真实执行。

只覆盖 ``get_db`` / ``get_current_user``；权限缓存打桩为未命中。SQLite 内存库 + 真 ORM。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User, UserRole
from app.models.note_content_template_models import NoteContentTemplate, NoteContentTemplateVersion
from app.models.report_models import DisclosureNote
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import note_content_templates

YEAR = 2025
_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, DisclosureNote.__table__,
           NoteContentTemplate.__table__, NoteContentTemplateVersion.__table__, StaffMember.__table__,
           ProjectAssignment.__table__]


class _Actor:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id, self.role, self.is_active = uid, UserRole.auditor, True
        self.username = f"u-{uid.hex[-4:]}"
        self.email = f"{self.username}@example.com"


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "peer", "boss", "viewer", "outsider", "P", "A")}
    async with factory() as s:
        s.add(Project(id=ids["P"], name="集团", client_name="集团公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        s.add(Project(id=ids["A"], name="子甲", client_name="子甲公司", template_type="soe", report_scope="standalone",
                      status=ProjectStatus.execution, parent_project_id=ids["P"]))
        staff = StaffMember(name="经理甲", user_id=ids["boss"])
        s.add(staff)
        await s.flush()
        s.add_all([
            *[ProjectUser(project_id=ids["A"], user_id=ids[k], role=ProjectUserRole.auditor,
                          permission_level=PermissionLevel.edit) for k in ("me", "peer", "boss")],
            ProjectUser(project_id=ids["A"], user_id=ids["viewer"], role=ProjectUserRole.auditor),
            ProjectAssignment(project_id=ids["P"], staff_id=staff.id, role="manager"),
            DisclosureNote(project_id=ids["A"], year=YEAR, note_section="一、1", section_title="公司基本情况",
                           text_content="<p>子甲公司成立于2001年。</p>", sort_index=1),
        ])
        await s.commit()

    current = {"actor": _Actor(ids["me"])}
    app = FastAPI()
    app.include_router(note_content_templates.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    with patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)), \
            patch("app.deps._set_cached_permission", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "ids": ids, "factory": factory,
                   "act_as": lambda key: current.update(actor=_Actor(ids[key]))}
    await engine.dispose()


def _url(env: dict, tail: str = "") -> str:
    return f"/api/projects/{env['ids']['A']}/note-content-templates{tail}"


def _assert_error(resp, status: int, code: str) -> None:
    assert resp.status_code == status, resp.text
    assert resp.json()["detail"]["error_code"] == code, resp.text


async def _preview(env: dict, scope: str = "personal", name: str = "全套模板"):
    return await env["client"].post(_url(env, "/snapshot-preview"),
                                    json={"year": YEAR, "name": name, "owner_scope": scope})


async def _save(env: dict, scope: str = "personal", name: str = "全套模板", digest: str | None = None):
    if digest is None:
        resp = await _preview(env, scope, name)
        assert resp.status_code == 200, resp.text
        digest = resp.json()["snapshot_digest"]
    return await env["client"].post(_url(env), json={"year": YEAR, "name": name, "owner_scope": scope,
                                                     "snapshot_digest": digest})


class TestSchema:
    """R-03：首版 ``body: dict``，任意 owner_scope 落到 service、year 缺省成 0。"""

    @pytest.mark.parametrize("patch_body", [
        {"owner_scope": "public"},                          # 普通用户不能声明 public/system
        {"allowed_project_ids": ["x"]},                     # 不能自带可见范围
        {"year": None},                                     # 年度必填
        {"owner_group_project_id": "00000000-0000-0000-0000-000000000000"},  # 集团根只能服务端解析
    ])
    @pytest.mark.asyncio
    async def test_save_rejects_forged_or_missing_fields(self, env, patch_body):
        body = {"year": YEAR, "name": "全套模板", "owner_scope": "personal", "snapshot_digest": "a" * 64, **patch_body}
        body = {k: v for k, v in body.items() if v is not None}
        resp = await env["client"].post(_url(env), json=body)
        assert resp.status_code == 422, resp.text
        # 必须是 schema 层拦下（detail 为校验错误列表），而不是放进 service 后靠业务校验兜底
        assert isinstance(resp.json()["detail"], list), resp.text
        async with env["factory"]() as db:
            assert await db.scalar(sa.select(sa.func.count()).select_from(NoteContentTemplate)) == 0

    @pytest.mark.asyncio
    async def test_blank_name_rejected(self, env):
        _assert_error(await _save(env, name="   "), 422, "TEMPLATE_NAME_INVALID")


class TestFlow:
    @pytest.mark.asyncio
    async def test_preview_save_list_detail_versions(self, env):
        preview = (await _preview(env)).json()
        assert preview["quality_summary"]["total"] == 1 and preview["section_count"] == 1
        saved = await _save(env, digest=preview["snapshot_digest"])
        assert saved.status_code == 200, saved.text
        tid = saved.json()["template_id"]
        listed = (await env["client"].get(_url(env))).json()
        assert listed["total"] == 1 and listed["items"][0]["current_version"]["version_no"] == 1
        assert (await env["client"].get(_url(env, f"/{tid}"))).status_code == 200
        assert (await env["client"].get(_url(env, f"/{tid}/versions"))).json()["total"] == 1

    @pytest.mark.asyncio
    async def test_stale_digest_is_409(self, env):
        digest = (await _preview(env)).json()["snapshot_digest"]
        async with env["factory"]() as db:
            note = (await db.execute(DisclosureNote.__table__.select())).first()
            (await db.get(DisclosureNote, note.id)).text_content = "<p>预检后被改</p>"
            await db.commit()
        _assert_error(await _save(env, digest=digest), 409, "STALE_SNAPSHOT")


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_group_publish_needs_manager_on_root(self, env):
        _assert_error(await _preview(env, "group"), 403, "GROUP_PUBLISH_FORBIDDEN")
        _assert_error(await _save(env, "group", digest="a" * 64), 403, "GROUP_PUBLISH_FORBIDDEN")
        env["act_as"]("boss")
        preview = (await _preview(env, "group")).json()
        assert preview["group_root_project_name"] == "集团"
        assert (await _save(env, "group", digest=preview["snapshot_digest"])).status_code == 200

    @pytest.mark.asyncio
    async def test_other_users_personal_template_is_404_everywhere(self, env):
        tid = (await _save(env)).json()["template_id"]
        env["act_as"]("peer")
        for method, tail in (("get", f"/{tid}"), ("get", f"/{tid}/versions"), ("delete", f"/{tid}")):
            _assert_error(await getattr(env["client"], method)(_url(env, tail)), 404, "TEMPLATE_NOT_VISIBLE")
        assert (await env["client"].get(_url(env))).json()["total"] == 0

    @pytest.mark.asyncio
    async def test_visible_group_template_delete_forbidden_for_non_manager(self, env):
        env["act_as"]("boss")
        tid = (await _save(env, "group")).json()["template_id"]
        env["act_as"]("peer")
        assert (await env["client"].get(_url(env, f"/{tid}"))).status_code == 200
        _assert_error(await env["client"].delete(_url(env, f"/{tid}")), 403, "TEMPLATE_DELETE_FORBIDDEN")
        env["act_as"]("boss")
        assert (await env["client"].delete(_url(env, f"/{tid}"))).status_code == 200
        assert (await env["client"].get(_url(env, f"/{tid}"))).status_code == 404

    @pytest.mark.asyncio
    async def test_readonly_member_reads_but_cannot_write(self, env):
        tid = (await _save(env)).json()["template_id"]
        env["act_as"]("viewer")
        assert (await env["client"].get(_url(env))).status_code == 200
        assert (await _preview(env)).status_code == 403
        assert (await _save(env, digest="a" * 64)).status_code == 403
        assert (await env["client"].delete(_url(env, f"/{tid}"))).status_code == 403

    @pytest.mark.asyncio
    async def test_outsider_forbidden(self, env):
        env["act_as"]("outsider")
        assert (await env["client"].get(_url(env))).status_code == 403
