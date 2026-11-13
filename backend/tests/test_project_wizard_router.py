"""项目初始化向导 API 路由单元测试

Validates: Requirements 1.1-1.8
"""

import inspect
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.routers.project_wizard import confirm_project, router, update_step as update_step_route

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    """轻量级用户替身，避免 SQLAlchemy 映射属性问题。"""

    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_manager"
        self.email = "manager@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """构造带依赖覆盖的测试 HTTP 客户端。"""
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def authorized_wizard_client(db_session: AsyncSession):
    """用真实项目成员门禁测试向导保存 / 确认，不覆盖 require_project_access 工厂。"""
    app = FastAPI()
    app.include_router(router)
    state = {"user": "admin"}
    identities = {
        "admin": User(
            id=uuid.uuid4(), username="wizard_admin", email="wizard_admin@test.com",
            hashed_password="x", role=UserRole.admin,
        ),
        "member": User(
            id=uuid.uuid4(), username="wizard_member", email="wizard_member@test.com",
            hashed_password="x", role=UserRole.auditor,
        ),
        "outsider": User(
            id=uuid.uuid4(), username="wizard_outsider", email="wizard_outsider@test.com",
            hashed_password="x", role=UserRole.auditor,
        ),
    }
    db_session.add_all(identities.values())
    await db_session.commit()

    async def _override_db():
        yield db_session

    async def _override_user():
        return identities[state["user"]]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda name: state.update(user=name)  # type: ignore[attr-defined]
        c.identities = identities  # type: ignore[attr-defined]
        yield c


async def _create_member_project(
    client: AsyncClient,
    db_session: AsyncSession,
) -> str:
    response = await client.post("/api/projects", json=BASIC_INFO)
    assert response.status_code == 200, response.text
    project_id = response.json()["id"]
    member = client.identities["member"]  # type: ignore[attr-defined]
    db_session.add(
        ProjectUser(
            project_id=uuid.UUID(project_id),
            user_id=member.id,
            role=ProjectUserRole.auditor,
            permission_level=PermissionLevel.edit,
        )
    )
    await db_session.commit()
    return project_id


# company_code / short_name 自 project-creation-enhancement（2026-06-05）起为必填；原常量
# 未提供 ⇒ 本文件 10 条用例在 HEAD 上全部 422（预存失败，consol-tree-three-code-autobuild
# 任务 3.7 补齐；代码为合法 18 位 USCC）。
BASIC_INFO = {
    "client_name": "测试客户",
    "audit_year": 2024,
    "project_type": "annual",
    "accounting_standard": "enterprise",
    "company_code": "91110000710931130E",
    "short_name": "测试客户",
}


async def _complete_confirmation_steps(client: AsyncClient, project_id: str) -> None:
    await client.put(
        f"/api/projects/{project_id}/wizard/account_import",
        json={"file_name": "chart.xlsx", "count": 50},
    )
    await client.put(
        f"/api/projects/{project_id}/wizard/account_mapping",
        json={"mapped_count": 10, "total_count": 10, "completion_rate": 100},
    )
    await client.put(
        f"/api/projects/{project_id}/wizard/materiality",
        json={"benchmark_type": "revenue"},
    )
    await client.put(
        f"/api/projects/{project_id}/wizard/team_assignment",
        json={"members": []},
    )


# ===================================================================
# POST /api/projects — 创建项目
# ===================================================================


class TestCreateProject:
    """Validates: Requirements 1.2, 1.3"""

    @pytest.mark.asyncio
    async def test_create_project_success(self, client: AsyncClient):
        resp = await client.post("/api/projects", json=BASIC_INFO)
        assert resp.status_code == 200
        body = resp.json()
        assert body["client_name"] == "测试客户"
        assert body["audit_year"] == 2024
        assert body["status"] == "created"
        assert "id" in body

    @pytest.mark.asyncio
    async def test_create_project_missing_field(self, client: AsyncClient):
        resp = await client.post(
            "/api/projects",
            json={"client_name": "测试", "audit_year": 2024},
        )
        assert resp.status_code == 422


# ===================================================================
# 集团架构字段（consol-tree-three-code-autobuild 需求 1 / 2）— 真发请求
# ===================================================================

_PARENT_USCC = "911100002000000005"
_GROUP_USCC = "91110000100000000R"


class TestGroupFieldsEndpoints:
    @pytest.mark.asyncio
    async def test_create_returns_group_fields_and_default_relation(self, client: AsyncClient):
        """单户项目也能带三码；关系缺省按名称补默认，响应回显字段与 notices。"""
        resp = await client.post(
            "/api/projects",
            json={**BASIC_INFO, "client_name": "某某有限公司临港店",
                  "parent_company_code": _PARENT_USCC, "parent_company_name": "某某有限公司",
                  "ultimate_company_code": _GROUP_USCC, "report_scope": "standalone"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["parent_company_code"] == _PARENT_USCC
        assert body["parent_company_name"] == "某某有限公司"
        assert body["ultimate_company_code"] == _GROUP_USCC
        assert body["relation_to_parent"] == "branch"
        assert any("已按企业名称默认为「分公司」" in n for n in body["notices"])

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_parent_uscc(self, client: AsyncClient):
        resp = await client.post(
            "/api/projects",
            json={**BASIC_INFO, "parent_company_code": "91110000710931130F"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "上级企业代码：统一社会信用代码校验码错误"

    @pytest.mark.asyncio
    async def test_create_accepts_parent_equal_to_self_as_top(self, client: AsyncClient):
        """需求 1.5：上级=本企业不再 422 —— 本企业就是上级企业；关系置空，响应说明处理方式。"""
        own = BASIC_INFO["company_code"]
        resp = await client.post(
            "/api/projects",
            json={**BASIC_INFO, "parent_company_code": own, "relation_to_parent": "分公司"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["parent_company_code"] == own
        assert body["relation_to_parent"] is None
        assert body["notices"] == [
            "上级企业代码与本企业相同，已按「本企业就是上级企业」处理：本企业为集团顶层企业，不另建上级节点"
        ]

    @pytest.mark.asyncio
    async def test_create_three_codes_equal_is_ultimate(self, client: AsyncClient):
        own = BASIC_INFO["company_code"]
        resp = await client.post(
            "/api/projects",
            json={**BASIC_INFO, "parent_company_code": own, "ultimate_company_code": own},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["notices"] == [
            "三个代码相同，已按「本企业即为最终控制方（集团总部或母公司）」处理"
        ]

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_relation(self, client: AsyncClient):
        resp = await client.post(
            "/api/projects",
            json={**BASIC_INFO, "parent_company_code": _PARENT_USCC,
                  "relation_to_parent": "joint_venture"},
        )
        assert resp.status_code == 422
        assert "与上级关系只能是" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_save_basic_info_returns_notices_and_detail_roundtrip(self, client: AsyncClient):
        """保存外推到同企业合并项目 ⇒ 响应 notices 说明；详情接口回显三码与关系。"""
        standalone = (await client.post("/api/projects", json=BASIC_INFO)).json()
        consol = (await client.post(
            "/api/projects", json={**BASIC_INFO, "report_scope": "consolidated"}
        )).json()

        resp = await client.put(
            f"/api/projects/{standalone['id']}/wizard/basic_info",
            json={**BASIC_INFO, "report_scope": "standalone",
                  "parent_company_code": _PARENT_USCC, "relation_to_parent": "子公司"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert any("已同步集团关系到同企业的合并项目" in n for n in body["notices"])
        assert body["steps"]["basic_info"]["data"]["relation_to_parent"] == "subsidiary"

        detail = (await client.get(f"/api/projects/{consol['id']}")).json()
        assert detail["parent_company_code"] == _PARENT_USCC
        assert detail["relation_to_parent"] == "subsidiary"

    @pytest.mark.asyncio
    async def test_save_basic_info_malformed_payload_uses_chinese_field_labels(
        self, client: AsyncClient
    ):
        project_id = (await client.post("/api/projects", json=BASIC_INFO)).json()["id"]
        resp = await client.put(
            f"/api/projects/{project_id}/wizard/basic_info",
            json={"client_name": "只有名称"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail == (
            "基本信息字段缺失或格式错误：会计准则、审计年度、企业代码、项目类型、项目简称"
        )
        assert "audit_year" not in detail
        assert "company_code" not in detail

    @pytest.mark.asyncio
    async def test_save_basic_info_invalid_company_code_uses_chinese_label(
        self, client: AsyncClient
    ):
        project_id = (await client.post("/api/projects", json=BASIC_INFO)).json()["id"]
        resp = await client.put(
            f"/api/projects/{project_id}/wizard/basic_info",
            json={**BASIC_INFO, "company_code": "too-short"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "基本信息字段缺失或格式错误：企业代码"


# ===================================================================
# GET /api/projects/{id}/wizard — 获取向导状态
# ===================================================================


class TestGetWizardState:
    """Validates: Requirements 1.4, 1.5"""

    @pytest.mark.asyncio
    async def test_get_wizard_state(self, client: AsyncClient):
        # 先创建项目
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.get(f"/api/projects/{project_id}/wizard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["current_step"] == "basic_info"
        assert body["completed"] is False
        assert "basic_info" in body["steps"]

    @pytest.mark.asyncio
    async def test_get_wizard_state_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/projects/{fake_id}/wizard")
        assert resp.status_code == 404


# ===================================================================
# PUT /api/projects/{id}/wizard/{step} — 更新步骤
# ===================================================================


class TestUpdateStep:
    """Validates: Requirements 1.3, 1.4, 1.5"""

    @pytest.mark.asyncio
    async def test_update_step_success(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/projects/{project_id}/wizard/account_import",
            json={"file_name": "chart.xlsx", "count": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "account_import" in body["steps"]
        assert body["steps"]["account_import"]["completed"] is True

    @pytest.mark.asyncio
    async def test_update_step_dependency_fail(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        # account_mapping 依赖 account_import
        resp = await client.put(
            f"/api/projects/{project_id}/wizard/account_mapping",
            json={"mappings": []},
        )
        assert resp.status_code == 400


# ===================================================================
# POST /api/projects/{id}/wizard/validate/{step} — 校验步骤
# ===================================================================


class TestValidateStep:
    """Validates: Requirements 1.8"""

    @pytest.mark.asyncio
    async def test_validate_basic_info_valid(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/wizard/validate/basic_info"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_confirmation_incomplete(self, client: AsyncClient):
        """确认只需 basic_info（其他步骤可后续补充，不阻塞创建）。

        commit ea6fe261d（2026-06-05）起 ``STEP_DEPENDENCIES[confirmation] = []``，
        服务层同名用例已随之改为「直接通过」；本路由用例当时未同步，因 BASIC_INFO
        缺必填字段先 422 而被掩盖（consol-tree-three-code-autobuild 任务 3.7 对齐）。
        """
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/wizard/validate/confirmation"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert {item["field"] for item in body["messages"]}.isdisjoint({
            "account_import",
            "account_mapping",
            "materiality",
            "team_assignment",
        })

    @pytest.mark.asyncio
    async def test_validate_confirmation_ready(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]
        await _complete_confirmation_steps(client, project_id)

        resp = await client.post(
            f"/api/projects/{project_id}/wizard/validate/confirmation"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert len(body["messages"]) == 0


# ===================================================================
# POST /api/projects/{id}/wizard/confirm — 确认项目
# ===================================================================


class TestConfirmProject:
    """Validates: Requirements 1.7"""

    @pytest.mark.asyncio
    async def test_confirm_project_success(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]
        await _complete_confirmation_steps(client, project_id)

        resp = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "planning"
        assert body["audit_year"] == 2024

    @pytest.mark.asyncio
    async def test_confirm_project_missing_required_steps(self, client: AsyncClient):
        """basic_info 已有时确认应成功（其他步骤不再阻塞，与服务层同名用例同口径）。"""
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "planning"

    @pytest.mark.asyncio
    async def test_confirm_project_missing_basic_info(self, client: AsyncClient, db_session: AsyncSession):
        """即使 wizard_state.steps 为空，确认也应成功（向导已简化，无前置依赖）。"""
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        result = await db_session.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one()
        project.wizard_state = {**project.wizard_state, "steps": {}}
        await db_session.commit()

        resp = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "planning"

    @pytest.mark.asyncio
    async def test_confirm_project_twice_rejected(self, client: AsyncClient):
        """确认后再确认 ⇒ 400（仅 created 可确认），守住状态机不被「无前置依赖」放宽。"""
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        first = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert first.status_code == 200
        second = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert second.status_code == 400
        assert "planning" in second.text


# ===================================================================
# 向导保存 / 确认的真实项目级鉴权（consol-group-code-entry-consistency 任务 3.1）
# ===================================================================


@pytest.mark.parametrize("operation", ["update", "confirm"])
@pytest.mark.asyncio
async def test_wizard_write_routes_reject_non_member(
    authorized_wizard_client: AsyncClient,
    db_session: AsyncSession,
    operation: str,
):
    """非成员不能通过登录依赖访问任意项目的向导写端点。"""
    project_id = await _create_member_project(authorized_wizard_client, db_session)
    authorized_wizard_client.as_user("outsider")  # type: ignore[attr-defined]

    if operation == "update":
        response = await authorized_wizard_client.put(
            f"/api/projects/{project_id}/wizard/account_import",
            json={"file_name": "chart.xlsx", "count": 50},
        )
    else:
        response = await authorized_wizard_client.post(
            f"/api/projects/{project_id}/wizard/confirm"
        )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "权限不足"
    result = await db_session.execute(
        select(Project).where(Project.id == uuid.UUID(project_id))
    )
    persisted = result.scalar_one()
    assert persisted.status == ProjectStatus.created
    if operation == "update":
        assert "account_import" not in (persisted.wizard_state or {}).get("steps", {})


@pytest.mark.parametrize("operation", ["update", "confirm"])
@pytest.mark.asyncio
async def test_wizard_write_routes_allow_edit_member(
    authorized_wizard_client: AsyncClient,
    db_session: AsyncSession,
    operation: str,
):
    """真实 edit 成员可保存向导步骤并确认项目，且写入确实落库。"""
    project_id = await _create_member_project(authorized_wizard_client, db_session)
    authorized_wizard_client.as_user("member")  # type: ignore[attr-defined]

    if operation == "update":
        response = await authorized_wizard_client.put(
            f"/api/projects/{project_id}/wizard/account_import",
            json={"file_name": "chart.xlsx", "count": 50},
        )
    else:
        response = await authorized_wizard_client.post(
            f"/api/projects/{project_id}/wizard/confirm"
        )

    assert response.status_code == 200, response.text
    result = await db_session.execute(
        select(Project).where(Project.id == uuid.UUID(project_id))
    )
    persisted = result.scalar_one()
    if operation == "update":
        assert persisted.status == ProjectStatus.created
        saved_step = (persisted.wizard_state or {}).get("steps", {}).get("account_import")
        assert saved_step is not None
        assert saved_step["completed"] is True
        assert saved_step["data"] == {"file_name": "chart.xlsx", "count": 50}
    else:
        assert persisted.status == ProjectStatus.planning


@pytest.mark.asyncio
async def test_update_step_passes_authenticated_actor(
    authorized_wizard_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """向导路由把真实鉴权返回的用户传入服务 actor，而不是只校验登录。"""
    from app.services import project_wizard_service

    project_id = await _create_member_project(authorized_wizard_client, db_session)
    authorized_wizard_client.as_user("member")  # type: ignore[attr-defined]
    captured: dict[str, object] = {}

    async def _fake_update_step(project_id, step, data, db, *, actor=None):
        captured["actor"] = actor
        return {
            "project_id": project_id,
            "current_step": step,
            "steps": {},
            "completed": False,
            "notices": [],
        }

    monkeypatch.setattr(project_wizard_service, "update_step", _fake_update_step)
    response = await authorized_wizard_client.put(
        f"/api/projects/{project_id}/wizard/account_import",
        json={"file_name": "chart.xlsx", "count": 50},
    )

    assert response.status_code == 200, response.text
    assert captured["actor"] is authorized_wizard_client.identities["member"]  # type: ignore[attr-defined]


@pytest.mark.parametrize("route", [update_step_route, confirm_project])
def test_wizard_write_routes_use_edit_project_access(route):
    """运行时依赖闭包必须捕获 edit，而非仅登录或 readonly。"""
    dependency = inspect.signature(route).parameters["current_user"].default.dependency
    freevars = dependency.__code__.co_freevars
    assert "min_permission" in freevars
    assert dependency.__closure__[freevars.index("min_permission")].cell_contents == "edit"
