"""附注 AI 续写 / 改写接入知识库（端点级：TestClient 真发请求）

spec: knowledge-upload-robustness-and-consumer-wiring（Requirement 6.2–6.5）

═══ 回归背景（2026-09-30 现跑 + Playwright）═══

  * ``POST /{project_id}/ai/complete`` 注册了两次，先注册的 query 版（``section_number`` 必填
    查询参数）遮蔽了 body 版 ⇒ 前端按 JSON 调用恒 422，续写从未可用。
  * 前端把「📚 知识库」选中的文档拼成 ``knowledge_context`` 发来，后端请求模型没有这个字段，
    被静默丢弃 ⇒ 用户以为 AI 参考了资料，实际没有。

本文件只 mock ``chat_completion``（LLM）与上年附注加载器；路由、``require_project_access``、
``KnowledgeIndexService.load_documents`` 的单一判定面全部真实执行（SQLite 内存库）。
权限缓存打桩为「未命中 / 不写」：既不写共享 Redis，也避免用例间缓存串味。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

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
from app.models.knowledge_models import KnowledgeAccessLevel as L, KnowledgeDocument, KnowledgeFolder  # noqa: E402
from app.routers import note_ai  # noqa: E402

PRIOR_NOTE = "【上年附注 五、4 应收账款】上年正文"
_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, KnowledgeFolder.__table__, KnowledgeDocument.__table__]
ENDPOINTS = {
    "complete": ("/ai/complete", {"text": "本公司应收账款", "section_number": "五、4", "year": 2025}),
    "rewrite": ("/ai/rewrite", {"text": "本公司应收账款", "instruction": "更专业", "section_number": "五、4", "year": 2025}),
}


class _Actor:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.role = UserRole.auditor
        self.username = f"u-{uid.hex[-4:]}"
        self.email = f"{self.username}@example.com"
        self.is_active = True


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    me, other, p, q = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ids: dict[str, uuid.UUID] = {}

    def nid(key: str) -> uuid.UUID:
        ids[key] = uuid.uuid4()
        return ids[key]

    async with factory() as s:
        for pid, tag in ((p, "P"), (q, "Q")):
            s.add(Project(id=pid, name=f"项目{tag}", client_name=f"客户{tag}",
                          project_type=ProjectType.annual, status=ProjectStatus.execution, created_by=me))
        await s.flush()
        s.add(ProjectUser(project_id=p, user_id=me, role=ProjectUserRole.auditor))  # 默认 readonly 权限
        s.add_all([
            KnowledgeFolder(id=nid("pub"), name="公开", access_level=L.public, created_by=other),
            KnowledgeFolder(id=nid("priv_other"), name="他人私有", access_level=L.private, created_by=other),
            KnowledgeFolder(id=nid("grp_q"), name="Q 项目组", access_level=L.project_group, project_ids=[str(q)]),
            KnowledgeFolder(id=nid("grp_p"), name="P 项目组", access_level=L.project_group, project_ids=[str(p)]),
        ])
        await s.flush()
        s.add_all([
            KnowledgeDocument(id=nid("A"), folder_id=ids["pub"], name="准则A.md", content_text="甲 公开知识正文"),
            KnowledgeDocument(id=nid("B"), folder_id=ids["priv_other"], name="私密B.md", content_text="乙 他人私密"),
            KnowledgeDocument(id=nid("C"), folder_id=ids["grp_q"], name="他项目C.md", content_text="丙 他项目资料"),
            KnowledgeDocument(id=nid("D"), folder_id=ids["pub"], name="已删D.md", content_text="丁 已删除", is_deleted=True),
            KnowledgeDocument(id=nid("E"), folder_id=ids["pub"], name="扫描件E.pdf", content_text=""),
            KnowledgeDocument(id=nid("F"), folder_id=ids["grp_p"], name="本项目F.md", content_text="戊 本项目组资料"),
        ])
        for i in range(3):
            s.add(KnowledgeDocument(id=nid(f"long{i}"), folder_id=ids["pub"], name=f"长文{i}.md",
                                    content_text=chr(ord("甲") + i) * 5000))
        await s.commit()

    current = {"actor": _Actor(me)}
    app = FastAPI()
    app.include_router(note_ai.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    llm = AsyncMock(return_value="生成片段")
    with patch("app.services.llm_client.chat_completion", new=llm), patch(
        "app.services.reference_doc_service.ReferenceDocService.load_context",
        new=AsyncMock(return_value=[PRIOR_NOTE]),
    ), patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)), patch(
        "app.deps._set_cached_permission", new=AsyncMock()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {
                "client": client, "ids": ids, "llm": llm, "p": p,
                "as_other": lambda: current.update(actor=_Actor(other)),
            }
    await engine.dispose()


async def _post(env, kind: str, doc_keys: list[str] | None = None, **extra):
    path, body = ENDPOINTS[kind]
    payload = dict(body, **extra)
    if doc_keys is not None:
        payload["knowledge_doc_ids"] = [str(env["ids"][k]) if k in env["ids"] else k for k in doc_keys]
    return await env["client"].post(f"/api/disclosure-notes/{env['p']}{path}", json=payload)


def _context_docs(env) -> list[str]:
    assert env["llm"].await_count == 1, "LLM 应被调用恰好一次"
    return env["llm"].await_args.kwargs.get("context_documents") or []


@pytest.mark.asyncio
async def test_continue_write_json_body_is_reachable(env):
    """R6.3：body 版是唯一实现 —— 前端 JSON 调用不再 422。"""
    resp = await _post(env, "complete")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["appended"] == "生成片段" and body["result"] == "本公司应收账款生成片段"
    assert body["knowledge_count"] == 0
    assert _context_docs(env) == [PRIOR_NOTE]


def test_ai_complete_route_is_registered_once():
    routes = [
        r for r in note_ai.router.routes
        if getattr(r, "path", "") == "/api/disclosure-notes/{project_id}/ai/complete"
        and "POST" in getattr(r, "methods", set())
    ]
    assert len(routes) == 1, "同一路径注册两次时先注册者遮蔽后者（旧 query 版遮蔽了 body 版）"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", sorted(ENDPOINTS))
async def test_only_retrievable_documents_are_injected_before_prior_notes(env, kind):
    """R6.2：客户端 ID 逐篇过判定面 —— 他人私有 / 他项目组 / 已删除静默跳过，保序，知识在前。"""
    resp = await _post(env, kind, ["B", "A", "C", "D", "F"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["knowledge_count"] == 2
    docs = _context_docs(env)
    assert docs[-1] == PRIOR_NOTE and len(docs) == 3
    assert docs[0].startswith("【知识库 - 准则A.md】") and "甲 公开知识正文" in docs[0]
    assert docs[1].startswith("【知识库 - 本项目F.md】") and "戊 本项目组资料" in docs[1]
    leaked = "".join(docs)
    for secret in ("乙 他人私密", "丙 他项目资料", "丁 已删除"):
        assert secret not in leaked, f"不可见文档被注入了 LLM：{secret}"


@pytest.mark.asyncio
async def test_documents_without_text_are_not_counted(env):
    """R6.5：扫描件等无正文的文档不算「已参考」。"""
    resp = await _post(env, "complete", ["E", "A"])
    assert resp.status_code == 200 and resp.json()["knowledge_count"] == 1
    assert [d.split("】", 1)[0] for d in _context_docs(env)[:-1]] == ["【知识库 - 准则A.md"]


@pytest.mark.asyncio
async def test_budget_is_split_so_every_selected_document_survives(env):
    """三篇长文各 5000 字：均分预算后每篇都进上下文（逐篇 4000 字会让第 3 篇被总长截断整篇丢掉）。"""
    resp = await _post(env, "complete", ["long0", "long1", "long2"])
    assert resp.status_code == 200 and resp.json()["knowledge_count"] == 3
    knowledge = _context_docs(env)[:3]
    assert [d.split("】", 1)[0] for d in knowledge] == [f"【知识库 - 长文{i}.md" for i in range(3)]
    assert sum(len(d) for d in knowledge) <= note_ai._KNOWLEDGE_BUDGET_CHARS + 3 * 40


@pytest.mark.asyncio
async def test_all_invisible_selection_reports_zero(env):
    resp = await _post(env, "rewrite", ["B", "C", str(uuid.uuid4())])
    assert resp.status_code == 200 and resp.json()["knowledge_count"] == 0
    assert _context_docs(env) == [PRIOR_NOTE]


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_keys", [["not-a-uuid"], [str(uuid.uuid4()) for _ in range(6)]])
async def test_malformed_or_too_many_ids_are_rejected(env, doc_keys):
    resp = await _post(env, "complete", doc_keys)
    assert resp.status_code == 422
    assert env["llm"].await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", sorted(ENDPOINTS))
async def test_non_member_is_forbidden(env, kind):
    """R6.4：项目非成员 403，且不触达 LLM 与知识库（此前任意登录用户可调）。"""
    env["as_other"]()
    resp = await _post(env, kind, ["A"])
    assert resp.status_code == 403
    assert env["llm"].await_count == 0


@pytest.mark.asyncio
async def test_legacy_query_style_call_is_not_accepted(env):
    """被删除的 query 版调用形态：缺 JSON body → 422（契约有意变化，前端与 e2e 均用 body）。"""
    resp = await env["client"].post(
        f"/api/disclosure-notes/{env['p']}/ai/complete", params={"section_number": "五、4", "current_text": "x"}
    )
    assert resp.status_code == 422
