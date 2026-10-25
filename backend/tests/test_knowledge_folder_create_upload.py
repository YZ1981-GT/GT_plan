"""知识库「新建文件夹 → 上传文档」闭环（端点级：真发请求 + 真 ORM 落库）

回归背景（2026-09-29 Playwright 实测）：
  ① 前端原生 XHR 上传读 localStorage 的 token（已迁 sessionStorage）→ 401。前端修复由
     ``authTokenSingleSource.spec.ts`` 守卫；本文件守后端这一半。
  ② 「项目组」权限不指定项目也能建成功，但 ``KnowledgeAccessPolicy`` 对任何人（含创建者）
     判不可见 → 文件夹一建就从目录树消失、上传被写权限门 404。
  ③ 同名重传建 v2 版本链，但 v2 物理文件**覆盖** v1（落盘名 = 展示名）→ v1 内容静默丢失。

只 mock ``get_current_user``（鉴权身份）与 ``get_db``（SQLite 内存库），其余走真实路由 +
真实 service + 真实权限策略。上传后的索引钩子/后台流水线打桩（依赖 embedding 服务），
本文件只验上传主链路。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import sqlalchemy as sa  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import (  # noqa: E402
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    ProjectUserRole,
    User,
    UserRole,
)
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder  # noqa: E402
from app.routers.knowledge_folders import router as kb_router  # noqa: E402
from app.services.knowledge_folder_service import normalize_folder_create_input  # noqa: E402

USER_ID = uuid.uuid4()
MY_PROJECT_ID = uuid.uuid4()
OTHER_PROJECT_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self) -> None:
        self.id = USER_ID
        self.role = UserRole.auditor
        self.username = "kb-tester"
        self.email = "kb@example.com"
        self.is_active = True


_TABLES = [
    User.__table__,
    Project.__table__,
    ProjectUser.__table__,
    KnowledgeFolder.__table__,
    KnowledgeDocument.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for pid in (MY_PROJECT_ID, OTHER_PROJECT_ID):
            session.add(Project(
                id=pid, name=f"P-{pid.hex[:6]}", client_name="KB 测试",
                project_type=ProjectType.annual, status=ProjectStatus.execution,
                created_by=USER_ID,
            ))
        await session.flush()
        # 当前用户只是 MY_PROJECT 的成员
        session.add(ProjectUser(project_id=MY_PROJECT_ID, user_id=USER_ID, role=ProjectUserRole.auditor))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()
    app.include_router(kb_router)

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    from app.core.config import settings

    with patch.object(settings, "STORAGE_ROOT", str(tmp_path)), patch(
        "app.routers.knowledge_folders._trigger_index_update", new=AsyncMock()
    ), patch("app.services.indexing_pipeline.run_indexing_pipeline", new=AsyncMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _tree_ids(client: AsyncClient) -> set[str]:
    resp = await client.get("/api/knowledge-library/tree")
    assert resp.status_code == 200, resp.text
    ids: set[str] = set()

    def walk(nodes):
        for n in nodes:
            ids.add(n["id"])
            walk(n.get("children") or [])

    walk(resp.json())
    return ids


# ---------------------------------------------------------------------------
# 1. 用户报告的主链路：新建文件夹 → 上传 → 列表可见 → 预览/下载取回原内容
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_public_folder_then_upload_then_list_and_preview(client: AsyncClient) -> None:
    resp = await client.post("/api/knowledge-library/folders", json={"name": "  函证资料  "})
    assert resp.status_code == 200, resp.text
    folder_id = resp.json()["id"]
    assert resp.json()["name"] == "函证资料"  # 名称去首尾空白
    assert folder_id in await _tree_ids(client)

    content = "应收账款函证程序要点：发函、跟函、回函核对。".encode("utf-8")
    resp = await client.post(
        f"/api/knowledge-library/folders/{folder_id}/upload",
        files=[("files", ("函证要点.txt", content, "text/plain"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["uploaded"] == 1
    assert body["files"][0]["text_extracted"] is True
    doc_id = body["files"][0]["id"]

    resp = await client.get(f"/api/knowledge-library/folders/{folder_id}/documents")
    assert resp.status_code == 200
    assert [d["name"] for d in resp.json()] == ["函证要点.txt"]

    resp = await client.get(f"/api/knowledge-library/documents/{doc_id}/preview")
    assert resp.status_code == 200
    assert resp.json()["preview_type"] == "text"
    assert "跟函" in resp.json()["content"]

    resp = await client.get(f"/api/knowledge-library/documents/{doc_id}/download")
    assert resp.status_code == 200
    assert resp.content == content


# ---------------------------------------------------------------------------
# 2. 项目组权限：不指定项目 / 只指定非本人项目 → 422；指定本人项目 → 可见可传
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_group_without_projects_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    resp = await client.post(
        "/api/knowledge-library/folders",
        json={"name": "项目组资料", "access_level": "project_group"},
    )
    assert resp.status_code == 422
    assert "至少指定一个项目" in resp.json()["detail"]
    count = (await db_session.execute(sa.select(sa.func.count()).select_from(KnowledgeFolder))).scalar()
    assert count == 0, "被拒绝的请求不得落库"


@pytest.mark.asyncio
async def test_project_group_with_only_foreign_projects_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/knowledge-library/folders",
        json={"name": "别人的项目", "access_level": "project_group", "project_ids": [str(OTHER_PROJECT_ID)]},
    )
    assert resp.status_code == 422
    assert "你参与的项目" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_project_group_with_own_project_is_visible_and_uploadable(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/knowledge-library/folders",
        json={
            "name": "本项目资料",
            "access_level": "project_group",
            "project_ids": [str(MY_PROJECT_ID), str(MY_PROJECT_ID)],  # 重复项去重
        },
    )
    assert resp.status_code == 200, resp.text
    folder_id = resp.json()["id"]
    assert folder_id in await _tree_ids(client), "创建者必须能在目录树里看到自己建的项目组文件夹"

    resp = await client.post(
        f"/api/knowledge-library/folders/{folder_id}/upload",
        files=[("files", ("说明.md", "# 项目组说明".encode("utf-8"), "text/markdown"))],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["uploaded"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, fragment",
    [
        ({"name": "   "}, "名称不能为空"),
        ({"name": "x" * 201}, "不能超过"),
        ({"name": "A", "access_level": "everyone"}, "不支持的权限级别"),
        ({"name": "A", "access_level": "public", "project_ids": ["not-a-uuid"]}, "格式不合法"),
    ],
)
async def test_invalid_folder_input_returns_422(client: AsyncClient, payload: dict, fragment: str) -> None:
    resp = await client.post("/api/knowledge-library/folders", json=payload)
    assert resp.status_code == 422
    assert fragment in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. 同名重传：v2 不得覆盖 v1 的物理文件
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reupload_same_name_keeps_previous_version_bytes(client: AsyncClient) -> None:
    folder_id = (await client.post("/api/knowledge-library/folders", json={"name": "版本"})).json()["id"]

    first = await client.post(
        f"/api/knowledge-library/folders/{folder_id}/upload",
        files=[("files", ("制度.txt", "第一版".encode("utf-8"), "text/plain"))],
    )
    second = await client.post(
        f"/api/knowledge-library/folders/{folder_id}/upload",
        files=[("files", ("制度.txt", "第二版".encode("utf-8"), "text/plain"))],
    )
    v1, v2 = first.json()["files"][0], second.json()["files"][0]
    assert v2["version"] == 2 and v2["previous_version_id"] == v1["id"]

    v1_bytes = (await client.get(f"/api/knowledge-library/documents/{v1['id']}/download")).content
    v2_bytes = (await client.get(f"/api/knowledge-library/documents/{v2['id']}/download")).content
    assert v1_bytes.decode("utf-8") == "第一版", "v1 物理文件被 v2 覆盖 ⇒ 历史版本内容丢失"
    assert v2_bytes.decode("utf-8") == "第二版"


# ---------------------------------------------------------------------------
# 4. 纯函数：规范化结果（router 与 service 共用同一校验）
# ---------------------------------------------------------------------------


def test_normalize_folder_create_input_contract() -> None:
    name, level, ids = normalize_folder_create_input(" A ", "public", None)
    assert (name, level.value, ids) == ("A", "public", None)

    pid = str(uuid.uuid4())
    _, level, ids = normalize_folder_create_input("A", "project_group", [pid, pid.upper()])
    assert level.value == "project_group" and ids == [pid]

    with pytest.raises(ValueError, match="至少指定一个项目"):
        normalize_folder_create_input("A", "project_group", [])


# ---------------------------------------------------------------------------
# 5. 项目知识文件夹上传（A17-3 相关文件；spec knowledge-base-retrieval-and-authz-closure 5.7）
# ---------------------------------------------------------------------------


async def _set_permission(db_session: AsyncSession, level: str) -> None:
    from app.models.base import PermissionLevel

    await db_session.execute(
        sa.update(ProjectUser)
        .where(ProjectUser.project_id == MY_PROJECT_ID, ProjectUser.user_id == USER_ID)
        .values(permission_level=PermissionLevel(level))
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_project_upload_creates_project_folder_and_document(client: AsyncClient, db_session: AsyncSession) -> None:
    await _set_permission(db_session, "edit")
    content = "咨询事项：收入确认时点的专业判断。".encode("utf-8")
    resp = await client.post(
        f"/api/knowledge-library/projects/{MY_PROJECT_ID}/upload",
        files=[("files", ("咨询附件.txt", content, "text/plain"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["uploaded"] == 1 and body["files"][0]["text_extracted"] is True
    doc_id = uuid.UUID(body["files"][0]["id"])

    doc = (await db_session.execute(sa.select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))).scalar_one()
    slot = (await db_session.execute(sa.select(KnowledgeFolder).where(KnowledgeFolder.id == doc.folder_id))).scalar_one()
    root = (await db_session.execute(sa.select(KnowledgeFolder).where(KnowledgeFolder.id == slot.parent_id))).scalar_one()
    assert slot.system_key == f"project:{MY_PROJECT_ID}:consultation" and slot.name == "A17-3 咨询附件"
    assert root.system_key == f"project:{MY_PROJECT_ID}" and root.name.endswith("（项目资料）")
    assert slot.access_level.value == "project_group" and slot.project_ids == [str(MY_PROJECT_ID)]
    assert doc.created_by == USER_ID and doc.content_text.startswith("咨询事项")

    # 第二次上传复用同一文件夹（系统文件夹幂等定位）
    again = await client.post(
        f"/api/knowledge-library/projects/{MY_PROJECT_ID}/upload",
        files=[("files", ("第二份.txt", "补充".encode("utf-8"), "text/plain"))],
    )
    assert again.status_code == 200 and again.json()["folder_id"] == str(slot.id)

    # 上传者本人（项目成员）在目录树里看得到它
    assert str(slot.id) in await _tree_ids(client)


@pytest.mark.asyncio
async def test_project_upload_requires_edit_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    # 夹具默认 readonly 权限的项目成员
    resp = await client.post(
        f"/api/knowledge-library/projects/{MY_PROJECT_ID}/upload",
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert resp.status_code == 403
    # 非项目成员
    resp = await client.post(
        f"/api/knowledge-library/projects/{OTHER_PROJECT_ID}/upload",
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert resp.status_code == 403
    count = (await db_session.execute(sa.select(sa.func.count()).select_from(KnowledgeFolder))).scalar_one()
    assert count == 0, "无权上传时不得先建出项目文件夹"


@pytest.mark.asyncio
async def test_project_upload_rejects_unknown_slot(client: AsyncClient, db_session: AsyncSession) -> None:
    await _set_permission(db_session, "edit")
    resp = await client.post(
        f"/api/knowledge-library/projects/{MY_PROJECT_ID}/upload?slot=hack",
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert resp.status_code == 422
