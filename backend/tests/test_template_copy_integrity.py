"""模板复制：外键顺序 / 复制产物落本底稿文件 / 看不见与不存在同一句（spec procedure-chain-hardening-and-java-contracts R3）。

SQLite **开外键检查**（``PRAGMA foreign_keys=ON``）：原先 wp_index 与 working_paper 同一次 flush，SQLAlchemy 按类名排序先插
working_paper ⇒ PG 上 ``working_paper_wp_index_id_fkey`` 违例 500；SQLite 默认不查外键，所以既有用例一直是绿的。

来源可见性的口径（主管全循环 / 受限成员只看委派给自己的）用的是 PG 语法的可见性查询，真库用例见
``tests/procedure_delegation_visibility/test_template_copy_visibility_pg.py``；本文件把可见集当作输入（``_visible_index_ids``）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.routers import wp_template_copy_router  # noqa: E402
from app.services import wp_template_init_service  # noqa: E402

pytestmark = pytest.mark.asyncio

_URL = "/api/projects/{pid}/workpapers/template-copy"


def _user(name: str) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com", hashed_password="x",
                role=UserRole.auditor, is_active=True)


def _project(name: str) -> Project:
    return Project(id=uuid.uuid4(), name=name, client_name=name, status=ProjectStatus.execution,
                   template_type="soe", report_scope="standalone", audit_year=2025)


@pytest.fixture
async def cw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "wp_storage"
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", storage)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @sa.event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):  # 与 PG 一样检查外键（删掉中间那次 flush 即红）
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        editor = _user("tc_editor")
        target, source = _project("【测试】复制目标"), _project("【测试】复制来源")
        db.add_all([editor, target, source])
        await db.flush()
        db.add_all([
            ProjectUser(project_id=target.id, user_id=editor.id, role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            ProjectUser(project_id=source.id, user_id=editor.id, role=ProjectUserRole.manager,
                        permission_level=PermissionLevel.readonly),
        ])
        papers = {}
        for code in ("G1", "G2"):
            idx = WpIndex(project_id=source.id, wp_code=code, wp_name=f"{code} 投资", audit_cycle="G",
                          status=WpStatus.not_started)
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(project_id=source.id, wp_index_id=idx.id, file_path="", file_version=1,
                              source_type=WpSourceType.template, parsed_data={"html_data": {"k": "v"}})
            db.add(wp)
            await db.flush()
            papers[code] = (wp, idx)
        await db.commit()

        visible: set = {idx.id for _wp, idx in papers.values()}

        async def _visible(db_, user, project_id):
            return frozenset(visible)

        monkeypatch.setattr(wp_template_copy_router, "_visible_index_ids", _visible)

        api = FastAPI()
        api.include_router(wp_template_copy_router.router)

        async def _db():
            yield db

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = lambda: editor
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://tc") as http:
            yield {"http": http, "db": db, "editor": editor, "target": target.id, "source": source.id,
                   "papers": papers, "storage": storage, "visible": visible}
    await engine.dispose()


async def _target_papers(cw) -> list[tuple[str, str]]:
    rows = (await cw["db"].execute(
        sa.select(WpIndex.wp_code, WorkingPaper.file_path)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.project_id == cw["target"], WorkingPaper.is_deleted == sa.false())
        .order_by(WpIndex.wp_code)
    )).all()
    return [(c, p) for c, p in rows]


def _own_file(cw, path: str) -> bool:
    return bool(path) and Path(path).exists() and Path(path).resolve().is_relative_to(cw["storage"].resolve())


async def test_single_copy_respects_fk_and_writes_own_file(cw):
    wp, _idx = cw["papers"]["G1"]
    r = await cw["http"].post(_URL.format(pid=cw["target"]), json={"source_wp_id": str(wp.id)})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "copied"
    [(code, path)] = await _target_papers(cw)
    assert code == "G1"
    assert _own_file(cw, path), f"复制产物须落本底稿自己的文件（原先 file_path=''）：{path!r}"


async def test_single_copy_existing_code_skips_with_chinese_reason(cw):
    """目标已有同编码：跳过、不落行，说明是给用户看的中文（原先界面显示「目标项目已存在 wp_code=G1，overwrite=False 跳过」）。"""
    wp, _idx = cw["papers"]["G1"]
    first = await cw["http"].post(_URL.format(pid=cw["target"]), json={"source_wp_id": str(wp.id)})
    assert first.json()["status"] == "copied"
    again = await cw["http"].post(_URL.format(pid=cw["target"]), json={"source_wp_id": str(wp.id)})
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["status"] == "skipped" and body["target_wp_id"] is None
    assert body["message"] == "目标项目已有该编码的底稿（暂不支持覆盖），未复制"
    assert [c for c, _p in await _target_papers(cw)] == ["G1"]


async def test_single_copy_invisible_and_missing_source_answer_the_same(cw):
    """看不见（不在可见集）与不存在：同一句 404，不泄露存在性；目标项目不落任何行。"""
    wp, idx = cw["papers"]["G1"]
    cw["visible"].discard(idx.id)
    for source_id in (wp.id, uuid.uuid4()):
        r = await cw["http"].post(_URL.format(pid=cw["target"]), json={"source_wp_id": str(source_id)})
        assert r.status_code == 404
        assert r.json()["detail"] == "源底稿不存在"
    assert await _target_papers(cw) == []


async def test_cycle_copy_requires_source_membership(cw):
    await cw["db"].execute(sa.update(ProjectUser).where(ProjectUser.project_id == cw["source"]).values(is_deleted=True))
    await cw["db"].commit()
    r = await cw["http"].post(_URL.format(pid=cw["target"]),
                              json={"source_project_id": str(cw["source"]), "audit_cycle": "G"})
    assert r.status_code == 404
    assert "无可复制底稿" in r.json()["detail"]
    assert await _target_papers(cw) == []


async def test_cycle_copy_skips_invisible_papers_with_reason(cw):
    _wp, idx = cw["papers"]["G2"]
    cw["visible"].discard(idx.id)
    r = await cw["http"].post(_URL.format(pid=cw["target"]),
                              json={"source_project_id": str(cw["source"]), "audit_cycle": "G"})
    assert r.status_code == 200, r.text
    by_code = {it["source_wp_code"]: it for it in r.json()}
    assert by_code["G1"]["status"] == "copied"
    assert by_code["G2"]["status"] == "skipped" and "无权查看" in by_code["G2"]["message"]
    rows = await _target_papers(cw)
    assert [c for c, _p in rows] == ["G1"]
    assert _own_file(cw, rows[0][1])


async def test_cycle_copy_all_visible_copies_all_with_files(cw):
    r = await cw["http"].post(_URL.format(pid=cw["target"]),
                              json={"source_project_id": str(cw["source"]), "audit_cycle": "G"})
    assert r.status_code == 200, r.text
    assert sorted(it["status"] for it in r.json()) == ["copied", "copied"]
    rows = await _target_papers(cw)
    assert [c for c, _p in rows] == ["G1", "G2"]
    assert all(_own_file(cw, p) for _c, p in rows)
