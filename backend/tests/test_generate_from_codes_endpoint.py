"""按编码生成底稿端点守卫（spec formula-governance-coverage-closure R5 走查撞上的缺陷，2026-10-22）。

原端点在函数体内 import 全仓从未实现的 ``populate_parsed_data`` ⇒ 对**任何**调用都在入口 ImportError 500；
前端「生成底稿」在模板集生成 5xx 时回退到本端点，回退同样失败。既有 property 测试只在内存里模拟端点逻辑、
从未真发请求，所以一直全绿。本守卫按真实路由发请求（SQLite 真 ORM，存储目录指到临时目录）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401  全量注册（外键引用的表要在 metadata 里）
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.routers import wp_template  # noqa: E402
from app.services.wp_parsed_data_service import ensure_parsed_data_placeholder  # noqa: E402

pytestmark = pytest.mark.asyncio

_TABLES = [User.__table__, Project.__table__, TrialBalance.__table__, WpIndex.__table__, WorkingPaper.__table__]
_URL = "/api/projects/{pid}/working-papers/generate-from-codes"


@pytest.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 端点按相对路径 storage/projects/... 落文件
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        user = User(id=uuid.uuid4(), username="gen_user", email="gen_user@example.com", hashed_password="x",
                    role=UserRole.auditor, is_active=True)
        with_tb, without_tb = uuid.uuid4(), uuid.uuid4()
        db.add(user)
        for pid, name in ((with_tb, "【测试】按编码生成_有试算表"), (without_tb, "【测试】按编码生成_无试算表")):
            db.add(Project(id=pid, name=name, client_name=name, status=ProjectStatus.execution,
                           template_type="soe", report_scope="standalone", audit_year=2025))
        await db.flush()
        db.add(TrialBalance(project_id=with_tb, year=2025, company_code="001", standard_account_code="1001",
                            account_name="库存现金", account_category=AccountCategory.asset,
                            unadjusted_amount=Decimal("100"), audited_amount=Decimal("100")))
        await db.commit()

        api = FastAPI()
        api.include_router(wp_template.router)

        async def _db():
            yield db

        async def _user() -> User:
            return user

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://gen") as http:
            yield {"http": http, "db": db, "with_tb": with_tb, "without_tb": without_tb, "root": tmp_path}
    await engine.dispose()


async def _papers(db: AsyncSession, pid: uuid.UUID) -> list[tuple[str, dict | None]]:
    rows = (await db.execute(
        sa.select(WpIndex.wp_code, WorkingPaper.parsed_data)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WpIndex.project_id == pid)
    )).all()
    return [(r[0], r[1]) for r in rows]


async def test_generate_creates_workpaper_with_placeholder_parsed_data(world):
    r = await world["http"].post(_URL.format(pid=world["with_tb"]), json={"wp_codes": ["E1"], "year": 2025})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1 and body["failures"] == [] and body["created_codes"] == ["E1"]
    papers = await _papers(world["db"], world["with_tb"])
    assert [code for code, _ in papers] == ["E1"]
    parsed = papers[0][1]
    assert parsed["_created_by"] == "generate_from_codes" and parsed["wp_code"] == "E1"
    assert parsed["html_data"] == {}
    assert (world["root"] / "storage" / "projects" / str(world["with_tb"]) / "workpapers" / "E" / "E1.xlsx").exists()


async def test_generate_twice_skips_existing(world):
    url = _URL.format(pid=world["with_tb"])
    assert (await world["http"].post(url, json={"wp_codes": ["E1"], "year": 2025})).status_code == 200
    again = (await world["http"].post(url, json={"wp_codes": ["E1"], "year": 2025})).json()
    assert again["created"] == 0 and again["skipped"] == 1 and again["skipped_codes"] == ["E1"]
    assert len(await _papers(world["db"], world["with_tb"])) == 1


async def test_generate_without_trial_balance_is_rejected(world):
    r = await world["http"].post(_URL.format(pid=world["without_tb"]), json={"wp_codes": ["E1"], "year": 2025})
    assert r.status_code == 422
    assert "试算表" in str(r.json())
    assert await _papers(world["db"], world["without_tb"]) == []


async def test_placeholder_keeps_existing_parsed_data():
    wp = WorkingPaper(project_id=uuid.uuid4(), wp_index_id=uuid.uuid4(), file_path="x.xlsx")
    wp.parsed_data = {"html_data": {"Sheet1": {"cells": {"A1": 1}}}}
    assert ensure_parsed_data_placeholder(wp, wp_code="E1", created_by="generate_from_codes") is False
    assert wp.parsed_data == {"html_data": {"Sheet1": {"cells": {"A1": 1}}}}
    blank = WorkingPaper(project_id=uuid.uuid4(), wp_index_id=uuid.uuid4(), file_path="y.xlsx")
    assert ensure_parsed_data_placeholder(blank, wp_code="D2", created_by="standard_conversion") is True
    assert blank.parsed_data["_created_by"] == "standard_conversion" and blank.parsed_data["html_data"] == {}
