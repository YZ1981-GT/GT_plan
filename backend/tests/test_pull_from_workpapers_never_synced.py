"""`POST /api/disclosure-notes/{pid}/{year}/pull-from-workpapers` 不得把从未同步的章节标成底稿来源。

🔴 缺陷（spec chain-closure-phase2-formula-push-engine 需求 5 / F8）：
端点对 registry 里每个章节无条件写 `table_data._source='workpaper'`。模板刷新
（`refill_sections` / `update_note_values`）见到该标记就永久跳过表格 ——
而从未同步过的章节，表格本来就是模板按试算表取数生成的，底稿侧没有要保护的内容。
附注生成 / 刷新前前端**每次**都调本端点，且 HEAD 之前它一直 500（漏 import）从未生效，
不修则一上线就批量扩大死区。

测试方式：TestClient 真发请求（只 override `get_current_user` / `get_db`，
让 `require_project_access("edit")` 照常执行）。两向：
1. 表格带同步指纹 `_last_sync_wp_id` 的章节 → 被标记（`_last_sync_at` 刷新）；
2. 从未同步的章节 → `table_data` 逐键不变，计入 `skipped_never_synced`。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, UserRole  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.models.report_models import ContentType, DisclosureNote  # noqa: E402

_NEVER_SYNCED_TD = {
    "rows": [
        {"label": "银行存款", "values": [110.3, 148151.74], "_cell_modes": {"0": "auto", "1": "auto"}},
    ],
    "headers": ["项目", "期末余额", "期初余额"],
}
_SYNCED_TD = {
    "_source": "workpaper",
    "_last_sync_wp_id": str(uuid.uuid4()),
    "sub_table_data": {"应收账款": [{"label": "1年以内", "end_amount": 100.0}]},
}


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pid = uuid.uuid4()
    admin = User(
        id=uuid.uuid4(), username="admin_pull", email="a@t.local",
        hashed_password="x", role=UserRole.admin, is_active=True,
    )
    async with factory() as db:
        db.add(admin)
        db.add(Project(
            id=pid, name="附注死区项目_2025", client_name="测试客户",
            project_type=ProjectType.annual, status=ProjectStatus.created,
            audit_year=2025, template_type="soe",
        ))
        db.add(DisclosureNote(
            project_id=pid, year=2025, note_section="八、1", section_title="货币资金",
            content_type=ContentType.table, table_data=dict(_NEVER_SYNCED_TD),
        ))
        db.add(DisclosureNote(
            project_id=pid, year=2025, note_section="八、5", section_title="应收账款",
            content_type=ContentType.table, table_data=dict(_SYNCED_TD),
        ))
        await db.commit()

    from app.routers.disclosure_notes import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        async with factory() as s:
            yield s

    async def _user():
        return admin

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory, pid
    await engine.dispose()


async def _td(factory, pid, section: str) -> dict:
    async with factory() as db:
        return (await db.execute(
            select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == pid, DisclosureNote.note_section == section,
            )
        )).scalar_one()


@pytest.mark.asyncio
async def test_never_synced_section_is_left_untouched(env):
    client, factory, pid = env
    r = await client.post(f"/api/disclosure-notes/{pid}/2025/pull-from-workpapers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_never_synced"] == 1, body
    td = await _td(factory, pid, "八、1")
    assert "_source" not in td, "从未同步的章节被打上 _source —— 模板刷新从此永久跳过它"
    assert td == _NEVER_SYNCED_TD, "从未同步的章节 table_data 被改动"


@pytest.mark.asyncio
async def test_synced_section_still_gets_marked(env):
    """反向：真正同步过的章节仍刷新标记（修复不能把正常路径一起关掉）。"""
    client, factory, pid = env
    r = await client.post(f"/api/disclosure-notes/{pid}/2025/pull-from-workpapers")
    assert r.status_code == 200, r.text
    assert r.json()["synced"] == 1
    td = await _td(factory, pid, "八、5")
    assert td["_source"] == "workpaper"
    assert td.get("_last_sync_at"), "同步过的章节未刷新 _last_sync_at"
    assert td["sub_table_data"] == _SYNCED_TD["sub_table_data"], "同步过的章节表格被改动"


@pytest.mark.asyncio
async def test_single_section_mode_obeys_same_rule(env):
    client, factory, pid = env
    r = await client.post(
        f"/api/disclosure-notes/{pid}/2025/pull-from-workpapers", params={"note_section": "八、1"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"synced": 0, "skipped": 0, "skipped_never_synced": 1}
    assert "_source" not in await _td(factory, pid, "八、1")
