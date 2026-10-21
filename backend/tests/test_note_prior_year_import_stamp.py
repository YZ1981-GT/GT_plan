"""上年 Word 导入 / 上年继承（spec disclosure-note-template-word-realignment Task 15，design §5）。

路由前缀带 ``{project_id}``，原来五个端点一个鉴权依赖都没挂（未登录可读写任意项目附注，鉴权基线扫描器只看
装饰器路径所以没看见）；导入服务读不存在的 ``note.title``、调不存在的 ``_extract_to_opening_balance``、年度恒为
2025。真 SQLite + 真 ORM + 真路由与真项目鉴权。
"""
from __future__ import annotations

import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import note_advanced
from tests.test_note_text_batch_endpoints import _Actor

YEAR = 2025
OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)
HEADERS = ["项目", "期末余额", "期初余额"]


def _table(values: list[list]) -> dict:
    rows = [{"label": label, "values": list(v)} for label, v in zip(("库存现金", "银行存款"), values)]
    return {"name": "货币资金", "headers": HEADERS, "rows": rows}


def _docx(sections: list[tuple[str, str, list[list[str]] | None]]) -> bytes:
    import docx

    doc = docx.Document()
    for title, para, rows in sections:
        doc.add_heading(title, level=2)
        if para:
            doc.add_paragraph(para)
        if rows:
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            for i, row in enumerate(rows):
                for j, value in enumerate(row):
                    t.cell(i, j).text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


PRIOR_DOCX = _docx([
    ("货币资金", "上年货币资金说明正文。", [HEADERS, ["库存现金", "1,234.50", "800"], ["银行存款", "(66)", "9"]]),
    ("会计期间", "上年会计期间说明。", None),
])


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, ProjectUser.__table__, DisclosureNote.__table__,
                         StaffMember.__table__, ProjectAssignment.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "viewer", "p", "cash", "period", "prior_cash", "prior_gone")}
    first = _table([[None, None], [5, 7]])
    async with factory() as s:
        s.add(Project(id=ids["p"], name="甲_2025", client_name="甲公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        s.add_all([
            ProjectUser(project_id=ids["p"], user_id=ids["me"], role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            ProjectUser(project_id=ids["p"], user_id=ids["viewer"], role=ProjectUserRole.auditor),
            DisclosureNote(id=ids["cash"], project_id=ids["p"], year=YEAR, note_section="八、1", section_title="货币资金",
                           table_data={"_tables": [first], **_table([[None, None], [5, 7]])},
                           updated_at=OLD, updated_by=None),
            DisclosureNote(id=ids["period"], project_id=ids["p"], year=YEAR, note_section="四、会计期间",
                           section_title="会计期间", text_content="<p>内容模板写的</p>", is_local_override=True,
                           updated_at=OLD, updated_by=None),
            DisclosureNote(id=ids["prior_cash"], project_id=ids["p"], year=YEAR - 1, note_section="八、1",
                           section_title="货币资金", text_content="上年库里的货币资金说明"),
            DisclosureNote(id=ids["prior_gone"], project_id=ids["p"], year=YEAR - 1, note_section="四、会计期间",
                           section_title="会计期间", text_content="回收站里的不该被继承", is_deleted=True),
        ])
        await s.commit()

    app = FastAPI()
    app.include_router(note_advanced.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    actor = {"user": _Actor(ids["me"])}
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "ids": ids, "factory": factory, "actor": actor, "app": app}
    await engine.dispose()


async def _note(env: dict, key: str) -> DisclosureNote:
    async with env["factory"]() as db:
        return await db.get(DisclosureNote, env["ids"][key])


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _import(env: dict, year: int | None = YEAR):
    url = f"/api/projects/{env['ids']['p']}/notes/import-prior-year" + (f"?year={year}" if year else "")
    files = {"file": ("上年附注.docx", PRIOR_DOCX,
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    return await env["client"].post(url, files=files)


@pytest.mark.asyncio
async def test_every_endpoint_requires_login(env):
    """不带身份 ⇒ 401/403（原来五个端点全部 200）。"""
    env["app"].dependency_overrides.pop(get_current_user)
    base = f"/api/projects/{env['ids']['p']}/notes"
    responses = [
        await _import(env),
        await env["client"].post(f"{base}/inherit-prior-year?year={YEAR}"),
        await env["client"].get(f"{base}/cross-references?year={YEAR}"),
        await env["client"].post(f"{base}/cross-references/update?year={YEAR}"),
        await env["client"].post(f"{base}/generate-variation-analysis?year={YEAR}"),
    ]
    assert [r.status_code in (401, 403) for r in responses] == [True] * 5, [r.status_code for r in responses]


@pytest.mark.asyncio
async def test_readonly_member_cannot_write(env):
    env["actor"]["user"] = _Actor(env["ids"]["viewer"])
    assert (await _import(env)).status_code == 403
    assert (await env["client"].post(
        f"/api/projects/{env['ids']['p']}/notes/inherit-prior-year?year={YEAR}")).status_code == 403
    assert (await _note(env, "cash")).updated_by is None


@pytest.mark.asyncio
async def test_year_is_required(env):
    assert (await _import(env, year=None)).status_code == 422


@pytest.mark.asyncio
async def test_import_fills_text_and_opening_column_and_stamps(env):
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    resp = await _import(env)
    assert resp.status_code == 200, resp.text
    assert resp.json()["matched"] == 2
    cash, period = await _note(env, "cash"), await _note(env, "period")
    assert cash.text_content == "上年货币资金说明正文。"
    # 期初列（下标 1）：空格填上年期末（千分位 / 括号负数照解析）；已有值的不覆盖
    assert [r["values"] for r in cash.table_data["_tables"][0]["rows"]] == [[None, 1234.5], [5, 7]]
    assert [r["values"] for r in cash.table_data["rows"]] == [[None, 1234.5], [5, 7]]  # 顶层镜像一并填
    assert cash.template_lineage["prior_year_status"] == "pending_update"
    assert cash.updated_by == env["ids"]["me"] and _utc(cash.updated_at) >= since
    # 内容模板写过的正文不覆盖，也不算编辑
    assert (period.text_content, period.updated_by, _utc(period.updated_at)) == ("<p>内容模板写的</p>", None, OLD)


@pytest.mark.asyncio
async def test_reimport_with_nothing_new_does_not_stamp(env):
    assert (await _import(env)).status_code == 200
    async with env["factory"]() as db:
        note = await db.get(DisclosureNote, env["ids"]["cash"])
        note.updated_at, note.updated_by = OLD, None
        await db.commit()
    assert (await _import(env)).status_code == 200
    cash = await _note(env, "cash")
    assert (_utc(cash.updated_at), cash.updated_by) == (OLD, None)


@pytest.mark.asyncio
async def test_inherit_copies_prior_text_stamps_and_ignores_recycle_bin(env):
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    resp = await env["client"].post(f"/api/projects/{env['ids']['p']}/notes/inherit-prior-year?year={YEAR}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["inherited"] == 1
    cash, period = await _note(env, "cash"), await _note(env, "period")
    assert cash.text_content == "上年库里的货币资金说明"
    assert cash.updated_by == env["ids"]["me"] and _utc(cash.updated_at) >= since
    assert cash.template_lineage["prior_year_source"] == YEAR - 1
    assert period.text_content == "<p>内容模板写的</p>" and period.updated_by is None
