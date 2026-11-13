"""底稿公式写入口登记到公式设置同步内核（spec formula-management-repair-closure R2）。

真发请求（生产路由 + 生产鉴权判定，只替换 ``get_db`` / ``get_current_user``）；SQLite 全量建表。
``record_changes`` 真实运行（同事务标过期 + 入队），只把提交后的 ``publish_pending`` 换成记录调用（不起后台投递）。

判据：执行字段（表达式 / 公式类型）变了才登记；公式位 = ``{wp_index.wp_code}|{sheet}|{cell}``（与 ``/effective`` 同口径）；
同编码的全部底稿标 ``prefill_stale``；只改说明不登记；``PUT /user-formulas`` 响应形状不变。
修复前五个写端点都不登记（outbox 0 行、prefill_stale 不动）。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
# 全量建表要有 asset_blobs：附件版本表的外键指向它，而它的模型模块没被 app.models / 生产路由导入
# （HEAD 上 conftest 的显式模型清单也漏了它，全量 create_all 报 NoReferencedTableError）
import app.models.asset_blob_models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectUserRole  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User, UserRole  # noqa: E402
from app.models.dataset_models import ImportEventOutbox  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper, WpFileStatus, WpFormula, WpIndex, WpReviewStatus, WpSourceType, WpStatus,
)
from app.routers import wp_formula, wp_user_formulas  # noqa: E402
from app.services.formula_settings import outbox  # noqa: E402

YEAR = 2025
SHEET, CELL = "Z1-1", "B2"


@pytest_asyncio.fixture
async def world(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(id=uuid.uuid4(), username="wp_editor", email="wp_editor@example.com", hashed_password="x",
                    role=UserRole.manager)
        project = Project(id=uuid.uuid4(), name="【测试】底稿登记_2025", client_name="【测试】",
                          project_type=ProjectType.annual, status=ProjectStatus.execution, audit_year=YEAR)
        db.add_all([user, project])
        await db.flush()
        db.add(ProjectUser(id=uuid.uuid4(), project_id=project.id, user_id=user.id, role=ProjectUserRole.manager,
                           permission_level=PermissionLevel.edit))
        idx = WpIndex(id=uuid.uuid4(), project_id=project.id, wp_code="Z1", wp_name="Z1 中性底稿",
                      status=WpStatus.not_started, is_deleted=False)
        other_idx = WpIndex(id=uuid.uuid4(), project_id=project.id, wp_code="Z2", wp_name="Z2 别的底稿",
                            status=WpStatus.not_started, is_deleted=False)
        db.add_all([idx, other_idx])
        await db.flush()
        papers = [WorkingPaper(id=uuid.uuid4(), project_id=project.id, wp_index_id=i.id, file_path="",
                               source_type=WpSourceType.template, status=WpFileStatus.draft,
                               review_status=WpReviewStatus.not_submitted, is_deleted=False, prefill_stale=False)
                  for i in (idx, other_idx)]  # 本底稿 + 别的编码一张（每项目每编码只有一张底稿：唯一索引）
        db.add_all(papers)
        await db.flush()
        existing = WpFormula(id=uuid.uuid4(), project_id=project.id, wp_id=papers[0].id, sheet_name=SHEET,
                             target_cell=CELL, expression="1 + 1", category="auto_calc", description="既有",
                             formula_type="auto_calc", formula_source="custom", definition_version=1,
                             created_by=user.id)
        db.add(existing)
        await db.commit()
    published: list[int] = []

    async def fake_publish(db):
        published.append(len(outbox._take_pending(db)))
        return {"queued": published[-1]}

    monkeypatch.setattr(outbox, "publish_pending", fake_publish)
    app = FastAPI()
    app.include_router(wp_formula.router)
    app.include_router(wp_user_formulas.router)

    async def _db():
        async with factory() as s:
            yield s

    async def _user():
        async with factory() as s:
            return await s.get(User, user.id)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    no_refs = AsyncMock(return_value=[])
    with patch("app.services.wp_formula_service.validate_refs_via_acnr", new=no_refs), \
            patch("app.services.acnr.formula_validation.validate_refs_via_acnr", new=no_refs):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "f": factory, "wp": papers[0].id, "papers": [p.id for p in papers],
                   "formula": existing.id, "project": project.id, "published": published}
    await engine.dispose()


async def _events(world) -> list[dict]:
    async with world["f"]() as db:
        rows = (await db.execute(sa.select(ImportEventOutbox).order_by(ImportEventOutbox.created_at))).scalars().all()
    return [r.payload for r in rows]


async def _stale(world) -> list[bool]:
    async with world["f"]() as db:
        got = {wid: flag for wid, flag in (await db.execute(sa.select(WorkingPaper.id, WorkingPaper.prefill_stale)))}
    return [bool(got[w]) for w in world["papers"]]


def _body(expression: str, **extra) -> dict:
    return {"sheet_name": SHEET, "target_cell": CELL, "expression": expression, "year": YEAR, **extra}


async def test_save_with_changed_expression_registers_slot_and_marks_same_code(world):
    r = await world["c"].put(f"/api/workpapers/{world['wp']}/formulas", json=_body("2 + 2", expected_version=1))
    assert r.status_code == 200, r.text
    assert r.json()["changed_slot_keys"] == [f"Z1|{SHEET}|{CELL}"], "R4：回执带公式位，公式管理据此问应用范围"
    [payload] = await _events(world)
    assert (payload["domain"], payload["slot_keys"], payload["source"]) == ("wp", [f"Z1|{SHEET}|{CELL}"], "project_edit")
    assert await _stale(world) == [True, False], "本编码底稿过期，别的编码不动"
    assert world["published"] == [1]


async def test_description_only_change_registers_nothing(world):
    r = await world["c"].put(f"/api/workpapers/{world['wp']}/formulas",
                             json=_body("1 + 1", expected_version=1, description="只改说明"))
    assert r.status_code == 200, r.text
    assert "changed_slot_keys" not in r.json(), "定义没变：回执不带公式位（不弹应用范围）"
    assert await _events(world) == [] and await _stale(world) == [False, False]
    assert world["published"] == [0]


async def test_batch_registers_only_cells_whose_definition_changed(world):
    r = await world["c"].put(f"/api/workpapers/{world['wp']}/formulas/batch", json={"year": YEAR, "items": [
        {"sheet_name": SHEET, "target_cell": CELL, "expression": "1 + 1", "expected_version": 1, "description": "x"},
        {"sheet_name": SHEET, "target_cell": "C3", "expression": "3 * 3"},
    ]})
    assert r.status_code == 200, r.text
    [payload] = await _events(world)
    assert payload["slot_keys"] == [f"Z1|{SHEET}|C3"]


async def test_delete_registers_slot(world):
    r = await world["c"].delete(f"/api/workpapers/{world['wp']}/formulas/{world['formula']}",
                                params={"expected_version": 1})
    assert r.status_code == 200, r.text
    [payload] = await _events(world)
    assert payload["slot_keys"] == [f"Z1|{SHEET}|{CELL}"]
    assert world["published"] == [1]


async def test_user_formulas_put_registers_saved_and_deleted_cells_and_keeps_shape(world):
    r = await world["c"].put(f"/api/workpapers/{world['wp']}/user-formulas", json={"formulas": {
        f"{SHEET}!{CELL}": "", f"{SHEET}!D4": "=TB('1001','期末余额')"}})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"wp_id", "updated", "deleted", "total"}
    [payload] = await _events(world)
    assert payload["slot_keys"] == sorted([f"Z1|{SHEET}|{CELL}", f"Z1|{SHEET}|D4"])


async def test_restore_preset_registers_slot(world):
    r = await world["c"].delete(f"/api/workpapers/{world['wp']}/user-formulas/{SHEET}!{CELL}")
    assert r.status_code == 200, r.text
    [payload] = await _events(world)
    assert payload["slot_keys"] == [f"Z1|{SHEET}|{CELL}"]


async def test_rejected_save_registers_nothing(world):
    """CAS 冲突（409）：整笔回滚，不留入队行、不标过期。"""
    r = await world["c"].put(f"/api/workpapers/{world['wp']}/formulas", json=_body("5 + 5", expected_version=7))
    assert r.status_code == 409, r.text
    assert await _events(world) == [] and await _stale(world) == [False, False]
