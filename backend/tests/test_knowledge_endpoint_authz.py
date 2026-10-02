"""知识库端点资源级授权（真发请求；spec knowledge-base-retrieval-and-authz-closure Req 6，P11 / P12）。

回归背景（2026-09-29 现读）：删除文件夹 / 删除文档 / 重命名文件夹 / 移动文档 / 预览 / 下载 / 搜索
七个端点**只校验登录** —— 任何登录用户可以删除、改名、移动他人的私有资料，预览下载任意
文档，并用搜索枚举他人私有文档名。前端改名调用的 ``PUT /documents/{id}`` 后端不存在（405）。

判定矩阵：
  * 不可读（含不存在 / 已删除）→ 404 同构 ``资源不存在或不可访问``
  * 可读但非创建者且非管理员，或系统角色 readonly → 403（中文原因）
  * 改名 / 移动作用于整条版本链；同名冲突 → 409

只 mock ``get_current_user``（随请求切换身份）与 ``get_db``（SQLite 内存库）；路由、service、
判定面全部真实执行。
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
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.knowledge_models import KnowledgeAccessLevel as L, KnowledgeDocument, KnowledgeFolder  # noqa: E402
from app.routers.knowledge_folders import router as kb_router  # noqa: E402

OWNER = uuid.UUID("00000000-0000-0000-0000-00000000f001")
OTHER = uuid.UUID("00000000-0000-0000-0000-00000000f002")
ADMIN = uuid.UUID("00000000-0000-0000-0000-00000000f003")
READER = uuid.UUID("00000000-0000-0000-0000-00000000f004")
P = uuid.UUID("00000000-0000-0000-0000-00000000f101")
NOT_FOUND = {"detail": "资源不存在或不可访问"}


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole) -> None:
        self.id = uid
        self.role = role
        self.username = f"u-{uid.hex[-4:]}"
        self.email = f"{self.username}@example.com"
        self.is_active = True


ACTORS = {
    "owner": _Actor(OWNER, UserRole.auditor),
    "other": _Actor(OTHER, UserRole.auditor),
    "admin": _Actor(ADMIN, UserRole.admin),
    "reader": _Actor(READER, UserRole.readonly),
}

_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, KnowledgeFolder.__table__, KnowledgeDocument.__table__]


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {}

    def fid(key):
        ids[key] = uuid.uuid4()
        return ids[key]

    stored = tmp_path / "stored.txt"
    stored.write_text("原始文件字节", encoding="utf-8")
    async with factory() as s:
        s.add(Project(id=P, name="项目P", client_name="客户P", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=OWNER))
        await s.flush()
        for uid in (OWNER, OTHER, READER):
            s.add(ProjectUser(project_id=P, user_id=uid, role=ProjectUserRole.auditor))
        s.add_all([
            KnowledgeFolder(id=fid("pub"), name="公开", access_level=L.public, created_by=OWNER),
            KnowledgeFolder(id=fid("pub2"), name="公开二", access_level=L.public, created_by=OTHER),
            KnowledgeFolder(id=fid("priv"), name="我的私有", access_level=L.private, created_by=OWNER),
            KnowledgeFolder(id=fid("sys"), name="系统", access_level=L.public, created_by=None,
                            system_key=f"project:{P}"),
        ])
        await s.flush()
        s.add_all([
            KnowledgeDocument(id=fid("doc_owner"), folder_id=ids["pub"], name="制度.md", content_text="制度正文 关键词丙",
                              created_by=OWNER, storage_path=str(stored), version=1),
            # 与生产 create_document 一致：同名重传的新版本 previous_version_id 指向上一版
            KnowledgeDocument(id=fid("doc_owner_v2"), folder_id=ids["pub"], name="制度.md", content_text="制度正文第二版 关键词丙",
                              created_by=OWNER, version=2, previous_version_id=ids["doc_owner"]),
            KnowledgeDocument(id=fid("doc_other"), folder_id=ids["pub"], name="他人.md", content_text="他人正文 关键词丙",
                              created_by=OTHER),
            KnowledgeDocument(id=fid("doc_mixed_v1"), folder_id=ids["pub"], name="混合链.md", content_text="v1",
                              created_by=OWNER, version=1),
            KnowledgeDocument(id=fid("doc_mixed_v2"), folder_id=ids["pub"], name="混合链.md", content_text="v2",
                              created_by=OTHER, version=2, previous_version_id=ids["doc_mixed_v1"]),
            KnowledgeDocument(id=fid("doc_priv"), folder_id=ids["priv"], name="私密笔记.md",
                              content_text="私密正文 关键词丙", created_by=OWNER),
            KnowledgeDocument(id=fid("doc_clash"), folder_id=ids["pub2"], name="制度.md", content_text="同名",
                              created_by=OTHER),
        ])
        await s.commit()

    current = {"actor": ACTORS["owner"]}
    app = FastAPI()
    app.include_router(kb_router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    with patch("app.routers.knowledge_folders._trigger_index_delete", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "ids": ids, "factory": factory, "as": lambda k: current.update(actor=ACTORS[k])}
    await engine.dispose()


async def _doc(env, key):
    async with env["factory"]() as s:
        return (await s.execute(sa.select(KnowledgeDocument).where(KnowledgeDocument.id == env["ids"][key]))).scalar_one()


async def _folder(env, key):
    async with env["factory"]() as s:
        return (await s.execute(sa.select(KnowledgeFolder).where(KnowledgeFolder.id == env["ids"][key]))).scalar_one()


# ── 读：预览 / 下载 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_and_download_require_read_permission(env):
    c, ids = env["client"], env["ids"]
    env["as"]("other")
    for path in (f"/api/knowledge-library/documents/{ids['doc_priv']}/preview",
                 f"/api/knowledge-library/documents/{ids['doc_priv']}/download",
                 f"/api/knowledge-library/documents/{uuid.uuid4()}/preview"):
        resp = await c.get(path)
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, path
    # 管理员也不绕过可见性（可见性角色无关）
    env["as"]("admin")
    assert (await c.get(f"/api/knowledge-library/documents/{ids['doc_priv']}/preview")).status_code == 404

    env["as"]("owner")
    resp = await c.get(f"/api/knowledge-library/documents/{ids['doc_priv']}/preview")
    assert resp.status_code == 200 and resp.json()["content"].startswith("私密正文")
    assert resp.json()["folder_id"] == str(ids["priv"])
    dl = await c.get(f"/api/knowledge-library/documents/{ids['doc_owner']}/download")
    assert dl.status_code == 200 and dl.content.decode("utf-8") == "原始文件字节"


# ── 删除 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,expected", [("other", 403), ("reader", 403), ("owner", 200), ("admin", 200)])
async def test_delete_document_matrix(env, actor, expected):
    env["as"](actor)
    resp = await env["client"].delete(f"/api/knowledge-library/documents/{env['ids']['doc_owner']}")
    assert resp.status_code == expected, resp.text
    assert (await _doc(env, "doc_owner")).is_deleted is (expected == 200)


@pytest.mark.asyncio
async def test_delete_invisible_document_is_404_not_403(env):
    env["as"]("other")
    resp = await env["client"].delete(f"/api/knowledge-library/documents/{env['ids']['doc_priv']}")
    assert resp.status_code == 404 and resp.json() == NOT_FOUND
    assert (await _doc(env, "doc_priv")).is_deleted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,expected", [("other", 403), ("reader", 403), ("owner", 200)])
async def test_delete_folder_matrix(env, actor, expected):
    env["as"](actor)
    resp = await env["client"].delete(f"/api/knowledge-library/folders/{env['ids']['pub']}")
    assert resp.status_code == expected, resp.text
    assert (await _folder(env, "pub")).is_deleted is (expected == 200)


@pytest.mark.asyncio
async def test_system_folder_only_admin_can_manage(env):
    c, sys_id = env["client"], env["ids"]["sys"]
    env["as"]("owner")
    assert (await c.put(f"/api/knowledge-library/folders/{sys_id}/rename", json={"name": "改"})).status_code == 403
    assert (await c.delete(f"/api/knowledge-library/folders/{sys_id}")).status_code == 403
    env["as"]("admin")
    assert (await c.put(f"/api/knowledge-library/folders/{sys_id}/rename", json={"name": "改"})).status_code == 200


# ── 重命名（整条版本链）──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_document_renames_whole_version_chain(env):
    env["as"]("owner")
    resp = await env["client"].put(
        f"/api/knowledge-library/documents/{env['ids']['doc_owner']}", json={"name": "  内控制度.md "}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["renamed"] == 2
    assert (await _doc(env, "doc_owner")).name == "内控制度.md"
    assert (await _doc(env, "doc_owner_v2")).name == "内控制度.md"


@pytest.mark.asyncio
async def test_rename_document_conflicts_and_permissions(env):
    c, ids = env["client"], env["ids"]
    env["as"]("owner")
    clash = await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}", json={"name": "他人.md"})
    assert clash.status_code == 409
    assert (await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}", json={"name": "  "})).status_code == 422
    # 链内含他人版本 → 创建者本人也不能只改自己那部分
    mixed = await c.put(f"/api/knowledge-library/documents/{ids['doc_mixed_v1']}", json={"name": "新名.md"})
    assert mixed.status_code == 403
    assert (await _doc(env, "doc_mixed_v1")).name == "混合链.md"
    env["as"]("other")
    assert (await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}", json={"name": "x.md"})).status_code == 403
    assert (await c.put(f"/api/knowledge-library/documents/{ids['doc_priv']}", json={"name": "x.md"})).status_code == 404


@pytest.mark.asyncio
async def test_rename_folder_requires_ownership(env):
    c, ids = env["client"], env["ids"]
    env["as"]("other")
    assert (await c.put(f"/api/knowledge-library/folders/{ids['pub']}/rename", json={"name": "改名"})).status_code == 403
    assert (await c.put(f"/api/knowledge-library/folders/{ids['priv']}/rename", json={"name": "改名"})).status_code == 404
    env["as"]("owner")
    resp = await c.put(f"/api/knowledge-library/folders/{ids['pub']}/rename", json={"name": " 改名 "})
    assert resp.status_code == 200 and (await _folder(env, "pub")).name == "改名"


# ── 移动（整条版本链 + 目标创建权）────────────────────────────────────────────


@pytest.mark.asyncio
async def test_move_document_moves_chain_and_checks_target(env):
    c, ids = env["client"], env["ids"]
    env["as"]("owner")
    clash = await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}/move",
                        json={"target_folder_id": str(ids["pub2"])})
    assert clash.status_code == 409, "目标已有同名文档仍被移入"
    missing = await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}/move",
                          json={"target_folder_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    moved = await c.put(f"/api/knowledge-library/documents/{ids['doc_owner']}/move",
                        json={"target_folder_id": str(ids["priv"])})
    assert moved.status_code == 200 and moved.json()["moved"] == 2
    assert (await _doc(env, "doc_owner")).folder_id == ids["priv"]
    assert (await _doc(env, "doc_owner_v2")).folder_id == ids["priv"]


@pytest.mark.asyncio
async def test_move_into_invisible_folder_is_404(env):
    env["as"]("admin")  # 管理员对他人私有文件夹同样不可见
    resp = await env["client"].put(f"/api/knowledge-library/documents/{env['ids']['doc_other']}/move",
                                   json={"target_folder_id": str(env["ids"]["priv"])})
    assert resp.status_code == 404


# ── 写角色上界 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_readonly_role_cannot_create_or_upload(env):
    c, ids = env["client"], env["ids"]
    env["as"]("reader")
    assert (await c.post("/api/knowledge-library/folders", json={"name": "新"})).status_code == 403
    assert (await c.post(f"/api/knowledge-library/folders/{ids['pub']}/documents",
                         json={"name": "a.md", "content_text": "x"})).status_code == 403
    assert (await c.post(f"/api/knowledge-library/folders/{ids['pub']}/upload",
                         files=[("files", ("a.txt", b"x", "text/plain"))])).status_code == 403
    assert (await c.post("/api/knowledge-library/init-presets")).status_code == 403


# ── 搜索（browse 模式）──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_hides_other_users_private_documents(env):
    c, ids = env["client"], env["ids"]
    env["as"]("other")
    names = {r["name"] for r in (await c.get("/api/knowledge-library/search", params={"q": "关键词丙"})).json()}
    assert "私密笔记.md" not in names, "搜索泄露了他人私有文档名"
    assert {"他人.md", "制度.md"} <= names
    env["as"]("owner")
    rows = (await c.get("/api/knowledge-library/search", params={"q": "关键词丙"})).json()
    by_name = {r["name"]: r for r in rows}
    assert "私密笔记.md" in by_name and by_name["私密笔记.md"]["folder_path"] == "/我的私有"
    # 同名重传只返回最新版本；片段来自最新版正文
    assert [r["id"] for r in rows if r["name"] == "制度.md" and r["folder_id"] == str(ids["pub"])] == [str(ids["doc_owner_v2"])]
    assert by_name["他人.md"]["can_manage"] is False and by_name["私密笔记.md"]["can_manage"] is True
    assert (await c.get("/api/knowledge-library/search", params={"q": " "})).json() == []


# ── 目录树 / 列表的能力标记与计数 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tree_flags_and_doc_count_only_counts_readable(env):
    c, ids = env["client"], env["ids"]
    # 在公开文件夹放一篇「他人私有」文档：计数不得把它算进来
    async with env["factory"]() as s:
        s.add(KnowledgeDocument(folder_id=ids["pub"], name="他人私有.md", content_text="x",
                                access_level=L.private, created_by=OTHER))
        await s.commit()
    env["as"]("owner")
    tree = {n["id"]: n for n in (await c.get("/api/knowledge-library/tree")).json()}
    pub = tree[str(ids["pub"])]
    assert pub["doc_count"] == 5, pub  # 制度×2 + 他人 + 混合链×2；不含他人私有
    assert pub["can_manage"] is True and pub["can_create"] is True
    assert tree[str(ids["pub2"])]["can_manage"] is False and tree[str(ids["pub2"])]["can_create"] is True
    assert tree[str(ids["sys"])]["can_manage"] is False and tree[str(ids["sys"])]["is_system"] is True

    env["as"]("reader")
    tree = {n["id"]: n for n in (await c.get("/api/knowledge-library/tree")).json()}
    assert tree[str(ids["pub"])]["can_create"] is False and tree[str(ids["pub"])]["can_manage"] is False

    env["as"]("owner")
    docs = {d["name"] + str(d["version"]): d for d in (await c.get(f"/api/knowledge-library/folders/{ids['pub']}/documents")).json()}
    assert docs["制度.md1"]["can_manage"] is True and docs["他人.md1"]["can_manage"] is False
