"""各生成入口只建保留范围内的底稿（spec procedure-trim-generation-delegation-chain 需求 2 / 任务 6~7）。

真实路由 / 真实服务 + SQLite 真 ORM：模板集生成、按编码生成（前端 5xx 回退路径）、自定义底稿（单条 / 批量）、
模板列表 ``trimmed`` 标记、全链生成（含第 8 步补建子底稿）、B60 附件、IPO 加载、跨项目模板复制、准则转换。
每个入口都断言三件事：已裁（含子表 / 程序表）不建、在回收站的同码不建且不落 failures、回执如实列出；
读不到裁剪结果（删掉 procedure_instances 表）一律停止生成。
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

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from app.routers import wp_template, wp_template_copy_router, wp_template_list  # noqa: E402
from app.services import wp_template_init_service  # noqa: E402
from app.services.procedure_scope_retention import TrimScopeUnavailable  # noqa: E402
from app.services.template_engine import TemplateEngine  # noqa: E402

pytestmark = pytest.mark.asyncio

_GEN = "/api/projects/{pid}/working-papers/generate"
_CODES = "/api/projects/{pid}/working-papers/generate-from-codes"


def _user(name: str) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com", hashed_password="x",
                role=UserRole.auditor, is_active=True)


def _project(name: str) -> Project:
    return Project(id=uuid.uuid4(), name=name, client_name=name, status=ProjectStatus.execution,
                   template_type="soe", report_scope="standalone", audit_year=2025)


def _proc(pid, code, status="not_applicable") -> ProcedureInstance:
    return ProcedureInstance(project_id=pid, audit_cycle=code[0], procedure_code=code, procedure_name=code,
                             status=status, wp_code=code)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        editor, reader, outsider = _user("ret_editor"), _user("ret_reader"), _user("ret_outsider")
        proj, source = _project("【测试】保留范围生成"), _project("【测试】复制来源")
        db.add_all([editor, reader, outsider, proj, source])
        await db.flush()
        db.add_all([
            ProjectUser(project_id=proj.id, user_id=editor.id, role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            ProjectUser(project_id=proj.id, user_id=reader.id, role=ProjectUserRole.readonly,
                        permission_level=PermissionLevel.readonly),
            TrialBalance(project_id=proj.id, year=2025, company_code="001", standard_account_code="1001",
                         account_name="库存现金", account_category=AccountCategory.asset,
                         unadjusted_amount=Decimal("1"), audited_amount=Decimal("1")),
            _proc(proj.id, "H3"), _proc(proj.id, "M4"), _proc(proj.id, "A1-12"), _proc(proj.id, "E1", "execute"),
        ])
        recycled = WpIndex(project_id=proj.id, wp_code="E2", wp_name="E2", audit_cycle="E",
                           status=WpStatus.not_started, is_deleted=True)
        db.add(recycled)
        await db.flush()
        db.add(WorkingPaper(project_id=proj.id, wp_index_id=recycled.id, file_path="", is_deleted=True,
                            source_type=WpSourceType.template, file_version=1))
        ts = await TemplateEngine().create_template_set(
            db=db, set_name="【测试】保留范围集", template_codes=["E1", "H3", "H3-1", "M4A", "E2", "H1"])
        await db.commit()

        current = {"user": editor}
        api = FastAPI()
        for r in (wp_template.router, wp_template_list.router, wp_template_copy_router.router):
            api.include_router(r)

        async def _db():
            yield db

        async def _current() -> User:
            return current["user"]

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _current
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://ret") as http:
            yield {"http": http, "db": db, "pid": proj.id, "source": source.id, "set_id": str(ts.id),
                   "current": current, "editor": editor, "reader": reader, "outsider": outsider}
    await engine.dispose()


async def _live_codes(world, pid=None) -> list[str]:
    rows = await world["db"].execute(
        sa.select(WpIndex.wp_code).where(WpIndex.project_id == (pid or world["pid"]), WpIndex.is_deleted == sa.false())
    )
    return sorted(rows.scalars().all())


async def _drop_trim_table(world) -> None:
    await world["db"].execute(sa.text("DROP TABLE procedure_instances"))


# ── 模板集生成 / 按编码生成 ──────────────────────────────────────────────


async def test_template_set_generation_skips_trimmed_and_recycled(world):
    r = await world["http"].post(_GEN.format(pid=world["pid"]), json={"template_set_id": world["set_id"], "year": 2025})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_trimmed_codes"] == ["H3", "H3-1", "M4A"], "子表、程序表跟随科目"
    assert body["in_recycle_codes"] == ["E2"]
    assert body["created"] == 2 and await _live_codes(world) == ["E1", "H1"]
    assert "3 个编码已在程序裁剪中标为不执行" in body["message"] and "回收站" in body["message"]


async def test_generate_from_codes_skips_trimmed_and_recycled(world):
    """前端模板集生成 5xx 时回退到本接口：同一判定，在回收站的同码不再撞唯一索引落进 failures。"""
    r = await world["http"].post(_CODES.format(pid=world["pid"]),
                                 json={"wp_codes": ["H3-2", "E2", "ZZ9", "M4A", "ZZ9"], "year": 2025})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_codes"] == ["ZZ9"] and body["failures"] == []
    assert body["skipped_trimmed_codes"] == ["H3-2", "M4A"] and body["in_recycle_codes"] == ["E2"]
    assert "回收站" in body["message"]
    assert await _live_codes(world) == ["ZZ9"]


@pytest.mark.parametrize("url", [_GEN, _CODES])
async def test_generation_requires_edit_membership(world, url):
    body = {"template_set_id": world["set_id"], "year": 2025} if url == _GEN else {"wp_codes": ["H1"], "year": 2025}
    for who in ("outsider", "reader"):
        world["current"]["user"] = world[who]
        r = await world["http"].post(url.format(pid=world["pid"]), json=body)
        assert r.status_code == 403, (who, r.text)
    assert await _live_codes(world) == []


@pytest.mark.parametrize("url", [_GEN, _CODES])
async def test_generation_fails_closed_when_trim_scope_unreadable(world, url):
    await _drop_trim_table(world)
    body = {"template_set_id": world["set_id"], "year": 2025} if url == _GEN else {"wp_codes": ["H1", "H3"], "year": 2025}
    r = await world["http"].post(url.format(pid=world["pid"]), json=body)
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "trim_scope_unavailable"
    assert await _live_codes(world) == []


# ── 自定义底稿 / 模板列表 ──────────────────────────────────────────────


async def test_custom_workpaper_respects_trim_and_recycle(world):
    one = "/api/projects/{pid}/working-papers/create-custom"
    r = await world["http"].post(one.format(pid=world["pid"]), json={"wp_code": "H3-7", "wp_name": "自定义"})
    assert r.status_code == 409 and "程序裁剪" in r.text
    batch = await world["http"].post(
        "/api/projects/{pid}/working-papers/create-custom-batch".format(pid=world["pid"]),
        json={"items": [{"wp_code": "X1", "wp_name": "自定义一"}, {"wp_code": "H3-8", "wp_name": "裁掉的"},
                        {"wp_code": "E2", "wp_name": "回收站里的"}]})
    assert batch.status_code == 200, batch.text
    by_code = {x["wp_code"]: x for x in batch.json()["results"]}
    assert by_code["X1"]["status"] == "created"
    assert by_code["H3-8"]["status"] == "skipped" and "程序裁剪" in by_code["H3-8"]["reason"]
    assert by_code["E2"]["status"] == "skipped" and "回收站" in by_code["E2"]["reason"]
    world["current"]["user"] = world["outsider"]
    r = await world["http"].post(one.format(pid=world["pid"]), json={"wp_code": "X2", "wp_name": "外人"})
    assert r.status_code == 403
    assert await _live_codes(world) == ["X1"]


async def test_template_list_marks_trimmed(world):
    r = await world["http"].get("/api/workpapers/template-list", params={"project_id": str(world["pid"])})
    assert r.status_code == 200, r.text
    items = {t["wp_code"]: t for t in r.json()}
    assert items["H3"]["trimmed"] is True and items["H3"]["trimmed_by"] == "H3"
    assert items["H3-1"]["trimmed"] is True and items["H3-1"]["trimmed_by"] == "H3"
    assert items["E1"]["trimmed"] is False and items["E1"]["trimmed_by"] is None
    assert items["G1"]["trimmed"] is False
    world["current"]["user"] = world["outsider"]
    r = await world["http"].get("/api/workpapers/template-list", params={"project_id": str(world["pid"])})
    assert r.status_code == 403


# ── 全链生成 / B60 / IPO / 模板复制 / 准则转换 ─────────────────────────


async def test_chain_step_filters_primary_and_step8_subs(world, monkeypatch):
    from app.services import chain_orchestrator, wp_code_override_loader

    monkeypatch.setattr(chain_orchestrator, "match_workpapers",
                        lambda mappings, tb, flags: ({"A1", "H3", "E2", "E1"}, {}))
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", lambda **kw: None)
    monkeypatch.setattr(wp_code_override_loader, "load_wp_code_overrides",
                        lambda: {"A1-11": "skip", "A1-12": "skip", "H3-1": "skip"})
    result = await chain_orchestrator.ChainOrchestrator()._step_generate_workpapers(world["db"], world["pid"], 2025)
    assert result["skipped_trimmed_codes"] == ["H3", "A1-12"], "主编码 H3 被裁；第 8 步子表 A1-12 自己被裁"
    assert result["in_recycle_codes"] == ["E2"]
    assert await _live_codes(world) == ["A1", "A1-11", "E1"]

    await _drop_trim_table(world)
    with pytest.raises(TrimScopeUnavailable):
        await chain_orchestrator.ChainOrchestrator()._step_generate_workpapers(world["db"], world["pid"], 2025)


async def test_b60_and_ipo_loaders(world, monkeypatch):
    from app.services.b60_plan_service import ensure_workpapers_for_codes
    from app.services.wp_template_init_service import _ensure_d4_ipo_loaded, _ensure_ipo_loaded

    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", lambda **kw: None)
    db = world["db"]
    db.add_all([_proc(world["pid"], "B60B"), _proc(world["pid"], "D4-22至D4-25")])
    db.add(WpIndex(project_id=world["pid"], wp_code="B60C", wp_name="B60C", audit_cycle="B",
                   status=WpStatus.not_started, is_deleted=True))
    await db.flush()

    ensured = await ensure_workpapers_for_codes(world["pid"], ["B60A", "B60B", "B60C", "B60B-1"], db)
    assert ensured.created == ["B60A"]
    assert ensured.skipped_trimmed_codes == ["B60B", "B60B-1"] and ensured.in_recycle_codes == ["B60C"]

    ipo = await _ensure_ipo_loaded(db, world["pid"], 2025, wp_code_prefix="D4")
    assert ipo["skipped_trimmed_codes"] == ["D4-22", "D4-22A", "D4-23", "D4-24", "D4-25"], "区间行展开，D4-22A 跟随 D4-22"
    assert ipo["errors"] == [] and "D4-26" in ipo["added_codes"] and "D4-22" not in ipo["added_codes"]
    again = await _ensure_d4_ipo_loaded(db, world["pid"], 2025)
    assert set(again) == {"added_codes", "skipped_existing", "errors"}, "D4 包装保持原三键"
    assert again["added_codes"] == [] and "D4-26" in again["skipped_existing"]


async def test_template_copy_skips_trimmed_and_returns_json(world, monkeypatch):
    """复制前按保留范围拦截；响应不再在 commit 后调不存在的 model_dump（原先复制落库、接口却 500）。"""
    db = world["db"]

    async def _all_visible(db_, user, project_id):  # 来源可见性是 PG 口径（真库用例另见 test_template_copy_visibility_pg.py）
        return frozenset((await db_.execute(sa.select(WpIndex.id).where(WpIndex.project_id == project_id))).scalars())

    monkeypatch.setattr(wp_template_copy_router, "_visible_index_ids", _all_visible)
    created = {}
    for code in ("H3-1", "G1"):
        idx = WpIndex(project_id=world["source"], wp_code=code, wp_name=code, audit_cycle=code[0],
                      status=WpStatus.not_started)
        db.add(idx)
        await db.flush()
        wp = WorkingPaper(project_id=world["source"], wp_index_id=idx.id, file_path="",
                          source_type=WpSourceType.template, file_version=1)
        db.add(wp)
        await db.flush()
        created[code] = wp.id
    await db.commit()
    url = "/api/projects/{pid}/workpapers/template-copy".format(pid=world["pid"])
    r = await world["http"].post(url, json={"source_wp_id": str(created["H3-1"])})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped" and "程序裁剪" in r.json()["message"]
    r = await world["http"].post(url, json={"source_wp_id": str(created["G1"])})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "copied" and r.json()["target_wp_id"]
    r = await world["http"].post(url, json={"source_wp_id": str(created["G1"]), "overwrite": True})
    assert r.status_code == 200 and r.json()["status"] == "skipped", "覆盖未实现：不再撞唯一索引"
    assert await _live_codes(world) == ["G1"]


async def test_standard_conversion_skips_trimmed_target_only(world, monkeypatch):
    from app.services.wp_standard_conversion_service import WpStandardConversionService

    svc = WpStandardConversionService(world["db"])
    seen: dict[str, list[str]] = {}

    async def _noop(*args, **kwargs):
        return 0

    async def _create(project_id, codes, new_standard, changed_by=None):
        seen["codes"] = list(codes)
        return len(codes)

    for name in ("check_preconditions", "_retain_shared_workpapers", "_archive_source_only_workpapers"):
        monkeypatch.setattr(svc, name, _noop)
    monkeypatch.setattr(svc, "_create_target_only_workpapers", _create)
    out = await svc.convert_workpapers(
        world["pid"], {"shared": [], "source_only": [], "target_only": ["H3-2", "M4A", "N1"]}, {"entity_type": "listed"})
    assert seen["codes"] == ["N1"] and out["created"] == 1
    assert out["skipped_trimmed_codes"] == ["H3-2", "M4A"]

    await _drop_trim_table(world)
    with pytest.raises(TrimScopeUnavailable):
        await svc.convert_workpapers(world["pid"], {"target_only": ["N1"]}, {"entity_type": "listed"})
