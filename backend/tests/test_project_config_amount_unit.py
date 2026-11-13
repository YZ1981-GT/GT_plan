"""项目默认金额单位的端点、服务和接线契约。

全部用内存 SQLite；不连接共享 PostgreSQL 或修改任何业务数据。

Validates: Requirements R4, AC-05, AC-06
"""
from __future__ import annotations

import ast
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import ProjectCreateResponse
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project
from app.routers.project_config import router
from app.routers.project_wizard import _to_project_response
from app.schemas.project_config import ProjectConfigUpdate
from app.services.project_config_service import ProjectConfigService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
ROOT = Path(__file__).resolve().parents[1]
_BACKEND_WIRING = (
    "app/models/core.py",
    "app/models/audit_platform_schemas.py",
    "app/routers/project_wizard.py",
    "app/services/project_config_service.py",
    "app/routers/project_config.py",
)


class _Actor:
    def __init__(self, role: UserRole) -> None:
        self.id = uuid.uuid4()
        self.username = "project-unit-tester"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def actor_state() -> SimpleNamespace:
    return SimpleNamespace(actor=_Actor(UserRole.admin))


@pytest_asyncio.fixture
async def client(db: AsyncSession, actor_state: SimpleNamespace) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    async def _actor():
        return actor_state.actor

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as result:
        yield result


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    item = Project(
        id=uuid.uuid4(),
        name="【测试】项目金额单位",
        client_name="测试客户",
        status=ProjectStatus.created,
        template_type="soe",
        report_scope="standalone",
        amount_unit="yuan",
    )
    db.add(item)
    await db.commit()
    return item


@pytest.mark.asyncio
@pytest.mark.parametrize("amount_unit", ["yuan", "qian", "wan"])
async def test_config_round_trip_accepts_only_the_three_amount_units(client, db, project, amount_unit):
    response = await client.put(
        f"/api/projects/{project.id}/config", json={"amount_unit": amount_unit}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == str(project.id)
    assert payload["amount_unit"] == amount_unit
    assert payload["changed_fields"] == ([] if amount_unit == "yuan" else ["amount_unit"])

    row = (await db.execute(select(Project).where(Project.id == project.id))).scalar_one()
    assert row.amount_unit == amount_unit
    reread = await client.get(f"/api/projects/{project.id}/config")
    assert reread.status_code == 200
    assert reread.json()["amount_unit"] == amount_unit


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "hundred", "亿元", 10000])
async def test_config_rejects_invalid_amount_unit_without_writing(client, db, project, value):
    response = await client.put(
        f"/api/projects/{project.id}/config", json={"amount_unit": value}
    )

    assert response.status_code == 422
    await db.refresh(project)
    assert project.amount_unit == "yuan"


@pytest.mark.asyncio
async def test_config_readonly_and_project_edit_gates(client, actor_state, project):
    actor_state.actor = _Actor(UserRole.auditor)
    get_response = await client.get(f"/api/projects/{project.id}/config")
    put_response = await client.put(
        f"/api/projects/{project.id}/config", json={"amount_unit": "wan"}
    )

    assert get_response.status_code == 403
    assert put_response.status_code == 403


@pytest.mark.asyncio
async def test_config_write_to_archived_project_is_423(client, db, project):
    project.status = ProjectStatus.archived
    await db.commit()

    response = await client.put(
        f"/api/projects/{project.id}/config", json={"amount_unit": "wan"}
    )
    assert response.status_code == 423


@pytest.mark.asyncio
async def test_config_unknown_project_is_404(client):
    response = await client.get(f"/api/projects/{uuid.uuid4()}/config")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_service_flushes_but_never_commits(db, project, monkeypatch):
    commit = AsyncMock()
    monkeypatch.setattr(db, "commit", commit)

    response = await ProjectConfigService(db).update_config(
        project.id, ProjectConfigUpdate(amount_unit="qian")
    )

    assert response.amount_unit == "qian"
    assert project.amount_unit == "qian"
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_detail_mapper_carries_actual_amount_unit(project):
    project.amount_unit = "wan"
    response = _to_project_response(project)

    assert isinstance(response, ProjectCreateResponse)
    assert response.amount_unit == "wan"


def test_amount_unit_schema_rejects_null_and_unknown_values():
    assert ProjectConfigUpdate.model_validate({"amount_unit": "qian"}).amount_unit == "qian"
    with pytest.raises(ValidationError):
        ProjectConfigUpdate.model_validate({"amount_unit": None})
    with pytest.raises(ValidationError):
        ProjectConfigUpdate.model_validate({"amount_unit": "hundred"})


def _tree(root: Path, relative: str) -> ast.Module:
    return ast.parse((root / relative).read_text(encoding="utf-8"))


def _class(tree: ast.AST, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"缺少类 {name}")


def _function(
    tree: ast.AST,
    name: str,
    class_name: str | None = None,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    scope: ast.AST = _class(tree, class_name) if class_name else tree
    for node in ast.iter_child_nodes(scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"缺少函数 {name}")


def _has_annotated_field(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and child.target.id == name
        for child in ast.walk(node)
    )


def _has_project_amount_assignment(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "project"
            and target.attr == "amount_unit"
            for target in child.targets
        )
        for child in ast.walk(node)
    )


def _has_mapper_keyword(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not isinstance(child.func, ast.Name) or child.func.id != "ProjectCreateResponse":
            continue
        for keyword in child.keywords:
            if (
                keyword.arg == "amount_unit"
                and isinstance(keyword.value, ast.Attribute)
                and isinstance(keyword.value.value, ast.Name)
                and keyword.value.value.id == "project"
                and keyword.value.attr == "amount_unit"
            ):
                return True
    return False


def _has_dependency(node: ast.AST, factory: str, argument: str) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Name) or child.func.id != "Depends":
            continue
        if not child.args or not isinstance(child.args[0], ast.Call):
            continue
        dependency = child.args[0]
        if (
            isinstance(dependency.func, ast.Name)
            and dependency.func.id == factory
            and dependency.args
            and isinstance(dependency.args[0], ast.Constant)
            and dependency.args[0].value == argument
        ):
            return True
    return False


def _assert_backend_wiring(root: Path) -> None:
    core = _tree(root, "app/models/core.py")
    response_schema = _tree(root, "app/models/audit_platform_schemas.py")
    wizard = _tree(root, "app/routers/project_wizard.py")
    service = _tree(root, "app/services/project_config_service.py")
    route = _tree(root, "app/routers/project_config.py")

    assert _has_annotated_field(_class(core, "Project"), "amount_unit"), "ORM 未声明 amount_unit"
    assert _has_annotated_field(_class(response_schema, "ProjectCreateResponse"), "amount_unit"), "详情 schema 未声明 amount_unit"
    assert _has_mapper_keyword(_function(wizard, "_to_project_response")), "详情 mapper 未传递 project.amount_unit"
    assert _has_project_amount_assignment(
        _function(service, "update_config", "ProjectConfigService")
    ), "service 未写入 project.amount_unit"
    assert _has_dependency(
        _function(route, "get_project_config"), "require_project_access", "readonly"
    ), "config GET 未使用 readonly 项目权限"
    assert _has_dependency(
        _function(route, "update_project_config"), "require_project_permission", "project:edit"
    ), "config PUT 未使用 project:edit 权限"


def _copy_backend_sources(tmp_path: Path) -> Path:
    root = tmp_path / "backend-copy"
    for relative in _BACKEND_WIRING:
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return root


def _remove_node(path: Path, select_node) -> None:
    source = path.read_text(encoding="utf-8")
    node = select_node(ast.parse(source))
    assert node is not None, f"变异锚点未命中：{path.name}"
    lines = source.splitlines(keepends=True)
    del lines[node.lineno - 1:node.end_lineno]
    path.write_text("".join(lines), encoding="utf-8")


def test_backend_wiring_guard_and_each_layer_deletion_mutation(tmp_path):
    """ORM、mapper、service、router 的删除变异均在复制源树中红，不触碰工作树。"""
    _assert_backend_wiring(ROOT)

    def remove_orm(path: Path) -> None:
        _remove_node(
            path,
            lambda tree: next(
                node for node in ast.walk(_class(tree, "Project"))
                if isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "amount_unit"
            ),
        )

    def remove_mapper(path: Path) -> None:
        _remove_node(
            path,
            lambda tree: next(
                node for node in ast.walk(_function(tree, "_to_project_response"))
                if isinstance(node, ast.keyword) and node.arg == "amount_unit"
            ),
        )

    def remove_service_write(path: Path) -> None:
        _remove_node(
            path,
            lambda tree: next(
                node for node in ast.walk(_function(tree, "update_config", "ProjectConfigService"))
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "amount_unit" for target in node.targets)
            ),
        )

    def remove_router_gate(path: Path) -> None:
        source = path.read_text(encoding="utf-8")
        needle = 'require_project_permission("project:edit")'
        assert source.count(needle) == 1, "router 变异锚点不唯一"
        path.write_text(source.replace(needle, "get_current_user"), encoding="utf-8")

    mutations = {
        "orm": ("app/models/core.py", remove_orm),
        "mapper": ("app/routers/project_wizard.py", remove_mapper),
        "service": ("app/services/project_config_service.py", remove_service_write),
        "router": ("app/routers/project_config.py", remove_router_gate),
    }
    for name, (relative, mutate) in mutations.items():
        copied = _copy_backend_sources(tmp_path / name)
        mutate(copied / relative)
        with pytest.raises(AssertionError):
            _assert_backend_wiring(copied)
