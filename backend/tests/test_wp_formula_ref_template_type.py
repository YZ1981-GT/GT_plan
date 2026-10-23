"""底稿公式保存：引用校验口径取底稿所属项目（spec formula-fetch-and-wp-generation-defect-closure R6）。

缺陷：``FormulaSaveRequest.template_type`` 缺省 ``"soe"``，自定义底稿编辑器又写死 ``'soe'``、公式状态面板不传
⇒ 这两处保存的上市项目底稿公式按国企附注 / 报表口径校验引用（NOTE 等引用被误判悬空或误放行）。公式管理中心
传的是页面口径（来自项目），不受影响。现：不传则取 ``projects.template_type``（与附注渲染、底稿用户公式同一
权威），显式传仍可覆盖。

真实路由 + SQLite 真 ORM（项目 / 底稿 / 公式表），管理员身份过真实鉴权门；``wp_formula_service.save`` 换成记录
入参并返回悬空引用（端点据此 422），只观测「端点交给校验的口径」这一项。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex, WpSourceType  # noqa: E402
from app.routers import wp_formula as router_mod  # noqa: E402
from tests._test_auth_helper import FakeAuthUser  # noqa: E402

pytestmark = pytest.mark.asyncio

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__, WpFormula.__table__]
_FRONTEND = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src"
_BODY = {"sheet_name": "Sheet1", "target_cell": "B5", "expression": "NOTE('五、1','合计','期末')", "year": 2025}


@pytest.fixture
async def world(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        wps: dict[str | None, uuid.UUID] = {}
        for template_type in ("listed", "soe", "custom", None):
            pid, idx, wid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            db.add(Project(id=pid, name=f"【测试】口径{template_type}", client_name="【测试】",
                           status=ProjectStatus.execution, template_type=template_type, audit_year=2025))
            await db.flush()
            db.add(WpIndex(id=idx, project_id=pid, wp_code="ZZ1", wp_name="自定义"))
            db.add(WorkingPaper(id=wid, project_id=pid, wp_index_id=idx, file_path="",
                                source_type=WpSourceType.template))
            wps[template_type] = wid
        await db.commit()

        seen: list[str] = []

        async def _fake_save(_db, **kw):
            seen.append(kw["template_type"])
            return None, [{"ref": kw["expression"], "status": "not_found", "message": "引用不存在"}]

        monkeypatch.setattr(router_mod.wp_formula_service, "save", _fake_save)

        api = FastAPI()
        api.include_router(router_mod.router)

        async def _db():
            yield db

        async def _user():
            return FakeAuthUser()

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://wpf") as http:
            yield {"http": http, "wps": wps, "seen": seen}
    await engine.dispose()


async def _save(world, template_type, body: dict) -> str:
    r = await world["http"].put(f"/api/workpapers/{world['wps'][template_type]}/formulas", json=body)
    assert r.status_code == 422, r.text  # 替身返回悬空引用 ⇒ 端点 422（证明走到了校验）
    return world["seen"][-1]


@pytest.mark.parametrize("project_type, expected", [("listed", "listed"), ("soe", "soe"),
                                                    ("custom", "soe"), (None, "soe")])
async def test_save_without_template_type_uses_project_type(world, project_type, expected):
    assert await _save(world, project_type, _BODY) == expected


async def test_explicit_template_type_still_overrides(world):
    assert await _save(world, "soe", {**_BODY, "template_type": "listed"}) == "listed"
    assert await _save(world, "listed", {**_BODY, "template_type": "private"}) == "soe", "非 soe/listed 归一为 soe"


async def test_batch_items_without_template_type_use_project_type(world):
    url = f"/api/workpapers/{world['wps']['listed']}/formulas/batch"
    item = {k: v for k, v in _BODY.items() if k != "year"}
    r = await world["http"].put(url, json={"year": 2025, "items": [item]})
    assert r.status_code == 422, r.text
    assert world["seen"][-1] == "listed"
    r = await world["http"].put(url, json={"year": 2025, "items": [{**item, "template_type": "soe"}]})
    assert r.status_code == 422, r.text
    assert world["seen"][-1] == "soe"


def test_frontend_wp_formula_saves_do_not_hardcode_template_type():
    """前端保存底稿公式的调用点不得写死口径（原 GtCustomWpEditor 写死 'soe'）。"""
    save_call = re.compile(r"api\.put\(\s*(?:wpFormula\.upsert|apiPaths\.workpapers\.formulas)\(")
    callers = []
    for p in _FRONTEND.rglob("*"):
        if p.suffix not in {".ts", ".vue"} or "__tests__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in save_call.finditer(text):
            callers.append(p.name)
            window = text[m.end():m.end() + 1500]
            assert not re.search(r"template_type\s*:\s*['\"]", window), f"{p.name} 保存底稿公式时写死了口径"
    assert {"GtCustomWpEditor.vue", "FormulaStatusPanel.vue", "FormulaManagerDialog.vue"} <= set(callers), callers
