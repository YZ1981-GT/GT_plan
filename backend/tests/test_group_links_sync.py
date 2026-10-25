"""派生链接 ``sync_group_links`` 与各写路径接线（spec consol-tree-three-code-autobuild 任务 6.5 / 需求 7.1~7.6）。

真 SQLite + 真 ORM 行；端点类用例真发请求（ASGITransport）：
- 幂等 + 只写变化行 + 受影响合并项目的合并试算标陈旧 + 提交后才广播（回滚不广播）；
- 建项顺序无关（先子后母 = 先母后子）；批量导入子行在前也挂得上；
- 保存基本信息改上级 ⇒ 重算；PATCH 上级代码两口径同写；纳入下级改写三码；
- 删除 / 回收站恢复 / 配置改报表类型 ⇒ 重算；连续审计只算新年度、不串用上年链接。
"""

from __future__ import annotations

import uuid
from io import BytesIO

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import BasicInfoSchema, WizardStep
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consolidation_models import ConsolTrial
from app.models.core import Project
from app.services import group_links
from app.services import project_wizard_service as svc

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

G = "91110000100000000R"   # 集团
P = "911100002000000005"   # 母公司/中间层
A = "91110000300000000G"   # 子公司
B = "91110000400000000U"   # 分公司
X = "911100005000000007"   # 未建项企业
Y = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def broadcasts(monkeypatch):
    calls: list[tuple[uuid.UUID, int | None]] = []
    import app.services.consol_scope_service as scope_svc

    monkeypatch.setattr(scope_svc, "_emit_scope_changed", lambda pid, year: calls.append((pid, year)))
    return calls


def _info(code: str, name: str, scope: str = "standalone", **kw) -> BasicInfoSchema:
    return BasicInfoSchema(
        client_name=name, audit_year=kw.pop("audit_year", Y), project_type="annual",
        accounting_standard="enterprise", company_code=code, short_name=name[:20],
        report_scope=scope, **kw,
    )


async def _fresh(db: AsyncSession, pid: uuid.UUID) -> Project:
    """丢弃会话缓存后按 id 重读（id 须在 expire 之前取出：过期对象连主键访问都会触发同步 IO）。"""
    db.expire_all()
    return await db.get(Project, pid)


async def _links(db: AsyncSession) -> dict[tuple[str, str], tuple[str, str] | None]:
    """(企业代码, 口径) → 链接目标的 (企业代码, 口径)；与 uuid 无关，便于跨库比较。"""
    db.expire_all()
    rows = (await db.execute(select(Project).where(Project.is_deleted == False))).scalars().all()  # noqa: E712
    by_id = {p.id: p for p in rows}
    out = {}
    for p in rows:
        target = by_id.get(p.parent_project_id) if p.parent_project_id else None
        out[(p.company_code, p.report_scope)] = (target.company_code, target.report_scope) if target else None
    return out


async def _seed_raw(db: AsyncSession) -> dict[str, Project]:
    """直接落 ORM 行（链接全空），模拟存量数据。"""
    rows = {
        "g_c": Project(name="集团_2025", client_name="某集团", status=ProjectStatus.created, company_code=G,
                       report_scope="consolidated", audit_year=Y),
        "g_s": Project(name="集团_2025", client_name="某集团", status=ProjectStatus.created, company_code=G,
                       report_scope="standalone", audit_year=Y),
        "a": Project(name="甲_2025", client_name="甲公司", status=ProjectStatus.created, company_code=A,
                     report_scope="standalone", audit_year=Y, parent_company_code=G, relation_to_parent="subsidiary"),
    }
    db.add_all(rows.values())
    await db.commit()
    return rows


# ─────────────────────────────── sync_group_links 本身 ───────────────────────────────


@pytest.mark.asyncio
async def test_sync_writes_changes_marks_stale_and_is_idempotent(db, broadcasts):
    rows = await _seed_raw(db)
    db.add(ConsolTrial(project_id=rows["g_c"].id, year=Y, standard_account_code="1001",
                       account_name="库存现金", account_category="asset"))
    await db.commit()

    affected = await group_links.sync_group_links(db, Y)
    await db.commit()
    assert affected == {rows["g_c"].id}
    assert await _links(db) == {
        (G, "consolidated"): None, (G, "standalone"): (G, "consolidated"), (A, "standalone"): (G, "consolidated"),
    }
    trial = (await db.execute(select(ConsolTrial))).scalar_one()
    assert trial.is_stale is True, "结构变化 ⇒ 受影响合并项目的合并试算标陈旧"
    assert broadcasts == [(rows["g_c"].id, Y)], "提交后广播一次"

    broadcasts.clear()
    assert await group_links.sync_group_links(db, Y) == set(), "幂等：第二次没有变化"
    await db.commit()
    assert broadcasts == []


@pytest.mark.asyncio
async def test_broadcast_dropped_on_rollback(db, broadcasts):
    await _seed_raw(db)
    assert await group_links.sync_group_links(db, Y)
    await db.rollback()
    assert broadcasts == [], "回滚不广播"
    assert await _links(db) == {(G, "consolidated"): None, (G, "standalone"): None, (A, "standalone"): None}


@pytest.mark.asyncio
async def test_sync_is_year_scoped(db):
    db.add_all([
        Project(name="集团_2024", client_name="某集团", status=ProjectStatus.created, company_code=G,
                report_scope="consolidated", audit_year=2024),
        Project(name="甲_2025", client_name="甲公司", status=ProjectStatus.created, company_code=A,
                report_scope="standalone", audit_year=Y, parent_company_code=G, relation_to_parent="subsidiary"),
    ])
    await db.commit()
    await group_links.sync_group_links(db, Y)
    await db.commit()
    assert (await _links(db))[(A, "standalone")] is None, "不跨年挂到上年的合并项目"


# ─────────────────────────────── 建项 / 保存 / 批量 / 连续审计 ───────────────────────────────


async def _create_in_order(db: AsyncSession, order: list[str]) -> dict:
    specs = {
        "g_c": _info(G, "某集团", "consolidated"),
        "g_s": _info(G, "某集团"),
        "a": _info(A, "甲公司", parent_company_code=G, relation_to_parent="subsidiary"),
        "b": _info(B, "某集团上海分公司", parent_company_code=G),
    }
    for key in order:
        await svc.create_project(specs[key], db)
    return await _links(db)


@pytest.mark.asyncio
async def test_create_order_independent(db):
    child_first = await _create_in_order(db, ["a", "b", "g_s", "g_c"])
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    parent_first = await _create_in_order(db, ["g_c", "g_s", "b", "a"])
    assert child_first == parent_first == {
        (G, "consolidated"): None,
        (G, "standalone"): (G, "consolidated"),
        (A, "standalone"): (G, "consolidated"),
        (B, "standalone"): (G, "consolidated"),
    }


@pytest.mark.asyncio
async def test_update_step_parent_change_relinks(db):
    await svc.create_project(_info(G, "某集团", "consolidated"), db)
    await svc.create_project(_info(P, "乙控股", "consolidated"), db)
    a = await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)
    assert (await _links(db))[(A, "standalone")] == (G, "consolidated")

    payload = dict(a.wizard_state["steps"]["basic_info"]["data"])
    payload["parent_company_code"] = P
    await svc.update_step(a.id, WizardStep.basic_info, payload, db)
    assert (await _links(db))[(A, "standalone")] == (P, "consolidated")


@pytest.mark.asyncio
async def test_batch_import_child_rows_before_parent(db):
    from app.services.batch_project_service import _TEMPLATE_COLUMNS, parse_and_import

    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(_TEMPLATE_COLUMNS)
    ws.append(["甲公司", A, "甲", Y, "年报审计", "企业会计准则", "单户", P, G, "子公司"])
    ws.append(["乙控股", P, "乙", Y, "年报审计", "企业会计准则", "合并", G, G, "子公司"])
    ws.append(["某集团", G, "集团", Y, "年报审计", "企业会计准则", "合并", "", G, ""])
    buf = BytesIO()
    wb.save(buf)
    result = await parse_and_import(buf.getvalue(), db)
    assert result.fail_count == 0, result.failures
    links = await _links(db)
    assert links[(A, "standalone")] == (P, "consolidated")
    assert links[(P, "consolidated")] == (G, "consolidated")
    assert links[(G, "consolidated")] is None


@pytest.mark.asyncio
async def test_continuous_audit_links_new_year_only(db):
    from app.services.continuous_audit_service import ContinuousAuditService

    await svc.create_project(_info(G, "某集团", "consolidated"), db)
    a = await svc.create_project(_info(A, "甲公司", parent_company_code=G, relation_to_parent="subsidiary"), db)
    assert (await _links(db))[(A, "standalone")] == (G, "consolidated")

    b_id = (await svc.create_project(_info(B, "乙公司", parent_company_code=G, relation_to_parent="subsidiary"), db)).id
    a_id = a.id

    result = await ContinuousAuditService().create_next_year(db, a_id)
    await db.commit()
    new_id = uuid.UUID(result["new_project_id"])
    new = await _fresh(db, new_id)
    assert new.audit_year == Y + 1
    assert new.parent_project_id is None, "新年度集团还没建合并项目 ⇒ 链接为空，不指向上年合并项目"

    g_next = await svc.create_project(_info(G, "某集团", "consolidated", audit_year=Y + 1), db)
    g_next_id = g_next.id
    assert (await _fresh(db, new_id)).parent_project_id == g_next_id, "新年度合并项目建好后自动挂上"

    # 新年度合并项目已存在时再结转下级：结转本身就要把链接算好（不等下一次别的写路径）
    result_b = await ContinuousAuditService().create_next_year(db, b_id)
    await db.commit()
    assert (await _fresh(db, uuid.UUID(result_b["new_project_id"]))).parent_project_id == g_next_id


# ─────────────────────────────── 端点（真发请求） ───────────────────────────────


class _User:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "tester"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    from app.routers.project_config import router as config_router
    from app.routers.project_wizard import router as wizard_router
    from app.routers.recycle_bin import router as recycle_router

    app = FastAPI()
    for r in (wizard_router, config_router, recycle_router):
        app.include_router(r)

    async def _db():
        yield db

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_patch_parent_code_writes_both_scopes_and_relinks(db, client):
    await svc.create_project(_info(G, "某集团", "consolidated"), db)
    await svc.create_project(_info(P, "乙控股", "consolidated"), db)
    await svc.create_project(_info(P, "乙控股"), db)
    a_c_id = (await svc.create_project(_info(A, "甲公司", "consolidated", parent_company_code=G), db)).id
    a_s_id = (await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)).id

    resp = await client.patch(f"/api/projects/{a_s_id}/parent-code", json={"parent_company_code": P})
    assert resp.status_code == 200, resp.text
    for pid in (a_s_id, a_c_id):
        row = await _fresh(db, pid)
        assert row.parent_company_code == P, "两口径同写"
        assert row.wizard_state["steps"]["basic_info"]["data"]["parent_company_code"] == P
    links = await _links(db)
    assert links[(A, "consolidated")] == (P, "consolidated")
    assert links[(A, "standalone")] == (A, "consolidated")
    assert resp.json()["parent_project_id"] == str(a_c_id)


@pytest.mark.asyncio
async def test_patch_parent_code_validation(db, client):
    await svc.create_project(_info(G, "某集团", "consolidated"), db)
    a_id = (await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)).id
    bad = await client.patch(f"/api/projects/{a_id}/parent-code", json={"parent_company_code": "91110000100000000Z"})
    assert bad.status_code == 422 and bad.json()["detail"].startswith("上级企业代码：")
    # 上级 = 本企业（需求 1.5）⇒ 接受，按顶层处理，关系清空
    ok = await client.patch(f"/api/projects/{a_id}/parent-code", json={"parent_company_code": A})
    assert ok.status_code == 200, ok.text
    row = await _fresh(db, a_id)
    assert row.parent_company_code == A and row.relation_to_parent is None


@pytest.mark.asyncio
async def test_attach_rewrites_three_codes(db, client):
    g_id = (await svc.create_project(_info(G, "某集团", "consolidated", ultimate_company_code=G), db)).id
    a_id = (await svc.create_project(_info(A, "某集团上海分公司"), db)).id
    b_id = (await svc.create_project(_info(B, "乙公司"), db)).id
    old_id = (await svc.create_project(_info(X, "丙公司", audit_year=Y - 1), db)).id

    avail = await client.get(f"/api/projects/{g_id}/available-subsidiaries")
    assert avail.status_code == 200
    by_code = {r["company_code"]: r for r in avail.json()}
    assert set(by_code) == {A, B}, "其他年度不列出"
    assert by_code[A]["relation_to_parent"] == "branch", "未填关系 ⇒ 按名称推断"

    resp = await client.post(
        f"/api/projects/{g_id}/attach-subsidiaries",
        json={"child_project_ids": [str(a_id), str(b_id), str(old_id)]},
    )
    assert resp.status_code == 200, resp.text
    assert {r["company_code"] for r in resp.json()} == {A, B}
    row = await _fresh(db, a_id)
    assert (row.parent_company_code, row.ultimate_company_code, row.relation_to_parent) == (G, G, "branch")
    assert row.parent_project_id == g_id
    after = await client.get(f"/api/projects/{g_id}/available-subsidiaries")
    assert after.json() == [], "已在企业树中的不再列出"


@pytest.mark.asyncio
async def test_delete_and_restore_relink(db, client):
    g_id = (await svc.create_project(_info(G, "某集团", "consolidated"), db)).id
    a_id = (await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)).id
    assert (await _fresh(db, a_id)).parent_project_id == g_id

    assert (await client.delete(f"/api/projects/{g_id}")).status_code == 200
    assert (await _fresh(db, a_id)).parent_project_id is None, "合并项目删除 ⇒ 下级链接清空"

    restored = await client.post(f"/api/recycle-bin/project/{g_id}/restore")
    assert restored.status_code == 200, restored.text
    assert (await _fresh(db, a_id)).parent_project_id == g_id, "恢复 ⇒ 重新挂上"

    batch = await client.post("/api/projects/batch-delete", json={"project_ids": [str(g_id)]})
    assert batch.status_code == 200 and batch.json()["deleted_count"] == 1
    assert (await _fresh(db, a_id)).parent_project_id is None


@pytest.mark.asyncio
async def test_config_report_scope_change_relinks(db, client):
    g_id = (await svc.create_project(_info(G, "某集团"), db)).id
    a_id = (await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)).id
    assert (await _fresh(db, a_id)).parent_project_id is None, "上级只有单户项目 ⇒ 无合并消费方"

    resp = await client.put(f"/api/projects/{g_id}/config", json={"report_scope": "consolidated"})
    assert resp.status_code == 200, resp.text
    assert (await _fresh(db, a_id)).parent_project_id == g_id


@pytest.mark.asyncio
async def test_standard_unification_scope_change_relinks(db, monkeypatch):
    """准则统一写报表类型（合并 ↔ 单户）⇒ 重算派生链接（需求 7.2 写路径之一）。"""
    from app.services import standard_unification_service as sus
    from app.services.standard_unification_service import StandardUnificationService

    async def _no_publish(_payload):
        return None

    monkeypatch.setattr(sus.event_bus, "publish_immediate", _no_publish)
    g_id = (await svc.create_project(_info(G, "某集团"), db)).id
    a_id = (await svc.create_project(_info(A, "甲公司", parent_company_code=G), db)).id
    assert (await _fresh(db, a_id)).parent_project_id is None

    await StandardUnificationService(db).set_standard(
        g_id, {"entity_type": "soe", "scope": "consolidated", "stage": "normal"}, changed_by=uuid.uuid4(),
    )
    await db.commit()
    assert (await _fresh(db, a_id)).parent_project_id == g_id
