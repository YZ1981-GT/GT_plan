"""程序链跨角色端到端（spec procedure-chain-hardening-and-java-contracts R21）。

真实 PostgreSQL + 真实 FastAPI 应用（全部中间件、注册表、底稿门）。一个外层事务（``create_savepoint``：路由里的
commit / rollback 只动保存点），结束整体回滚、不落库；底稿文件生成到临时目录。

三种角色：系统管理员；项目经理（唯一人员档案 + 团队分配 manager + 项目成员 edit：可裁剪、委派、生成）；
审计员（团队分配勾选 D 循环 + 项目成员 edit）。按界面上的真实顺序走一遍：

1. 经理按编码生成 D1 / D2 / H3；
2. 经理粗裁 H3：已生成的 H3 移入回收站（生命周期事件记移入人；回收站「删除人」= 经理）；
3. 再生成 H3 / H3-1：两个都按「已裁」跳过，不建；
4. 审计员不能裁剪、不能委派（403）；
5. 经理把 D2 委派给审计员；
6. 可见：审计员列表只有 D2，打开 D1 / H3 都是 404（不暴露存在性）；经理、管理员看到 D1 / D2；
7. 编辑锁：审计员取 D2 → 经理取同一把 409（带持有人）、放不掉别人的锁 → 审计员释放 → 经理取到；审计员取 D1 404；
8. 经理恢复执行 H3：H3 从回收站恢复（事件记恢复），审计员仍打不开（不在其循环）；
9. 再生成 H3 / H3-1：H3 已存在、H3-1 新建。
"""
from __future__ import annotations

import types
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.migration_runner import MigrationRunner
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import PermissionLevel
from app.models.procedure_models import ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services import wp_template_init_service
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL
from app.services.wp_visibility.epoch_cache import reset_epoch_cache
from tests.procedure_delegation_visibility._factories import (
    mk_assignment,
    mk_procedure_instance,
    mk_project,
    mk_project_user,
    mk_staff,
    mk_user,
)

pytestmark = [pytest.mark.pg_only, pytest.mark.asyncio]

YEAR = 2025
V207 = Path(__file__).resolve().parents[2] / "migrations" / "V207__workpaper_lifecycle_events.sql"


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    monkeypatch.chdir(tmp_path)
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    reset_epoch_cache()
    try:
        yield s
    finally:
        try:
            from app.main import app

            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
        finally:  # 回滚不依赖任何导入成功
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()
            reset_epoch_cache()


@pytest.fixture(autouse=True)
def side_writes(monkeypatch):
    """操作日志 / 拒绝记录 / 哈希链审计走独立连接，会在真库留下引用回滚数据的行 ⇒ 换成内存记录。"""
    from app.middleware import audit_log
    from app.services import audit_logger_enhanced
    from app.services.wp_visibility.denial import DenialResponder

    seen: dict[str, list] = {"logs": [], "denials": [], "audit": []}

    async def _log(**kw):
        seen["logs"].append(kw)

    async def _denial(self, **kw):
        seen["denials"].append(kw)

    async def _audit(self, *args, **kw):
        seen["audit"].append(kw)

    monkeypatch.setattr(audit_log, "_write_log", _log)
    monkeypatch.setattr(DenialResponder, "_write_outbox", _denial)
    monkeypatch.setattr(type(audit_logger_enhanced.audit_logger), "log_action", _audit)
    return seen


def _principal(user):
    """路由里有 rollback（只回滚保存点）⇒ 不把 ORM 用户对象交给依赖，免得过期属性触发懒加载。"""
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 full_name=None, is_active=True, is_deleted=False)


def _client(s: AsyncSession, user) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    principal = _principal(user)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: principal
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _data(resp):
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def _wire_detail(resp):
    """真实应用：响应包装把错误详情放进 message。"""
    body = resp.json()
    return (body.get("detail") or body.get("message")) if isinstance(body, dict) else None


async def _ensure_lifecycle_table(s: AsyncSession) -> None:
    """真库在下次全量重启前可能还没有 V207 的表（热重载不跑迁移）⇒ 事务里执行 V207 本身，回滚即撤销。"""
    if (await s.execute(sa.text("SELECT to_regclass('public.workpaper_lifecycle_events')"))).scalar_one() is None:
        for stmt in MigrationRunner._split_sql_statements(V207.read_text(encoding="utf-8")):
            await s.execute(sa.text(stmt))


async def _member(s, project, *, role: str, cycles: tuple[str, ...] = ()):
    user = await mk_user(s, role=role)
    staff = await mk_staff(s, user_id=user.id)
    assignment = await mk_assignment(s, project.id, staff.id, role=role)
    assignment.assigned_cycles = list(cycles) or None
    pu = await mk_project_user(s, project.id, user.id, role=role, scope_cycles=",".join(cycles) or None)
    pu.permission_level = PermissionLevel.edit
    await s.flush()
    return user, staff


async def _world(s):
    project = await mk_project(s)
    project.name = f"【测试】程序链跨角色_{uuid.uuid4().hex[:6]}"
    project.audit_year = YEAR
    project.audit_period_end = date(YEAR, 12, 31)
    admin = await mk_user(s, role="admin")
    manager, _ = await _member(s, project, role="manager")
    auditor, a_staff = await _member(s, project, role="auditor", cycles=("D",))
    s.add(TrialBalance(project_id=project.id, year=YEAR, company_code="001", standard_account_code="1001",
                       account_name="库存现金", account_category=AccountCategory.asset,
                       unadjusted_amount=Decimal("1"), audited_amount=Decimal("1")))
    await mk_procedure_instance(s, project.id, audit_cycle="H", wp_code="H3")  # 粗裁的对象：H 循环的 H3 程序
    await s.flush()
    return types.SimpleNamespace(pid=project.id, admin=admin, manager=manager, auditor=auditor, a_staff=a_staff)


async def _index(s, pid) -> dict:
    rows = (await s.execute(sa.select(WpIndex.wp_code, WpIndex.id, WpIndex.is_deleted)
                            .where(WpIndex.project_id == pid))).all()
    return {r.wp_code: r for r in rows}


async def _papers(s, pid) -> dict:
    rows = (await s.execute(sa.select(WpIndex.wp_code, WorkingPaper.id, WorkingPaper.file_path)
                            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                            .where(WpIndex.project_id == pid))).all()
    return {r.wp_code: r for r in rows}


async def _events(s, pid) -> list[tuple]:
    rows = (await s.execute(sa.text(
        "SELECT wp_code, event_type, kind, actor_user_id::text, request_id FROM workpaper_lifecycle_events "
        "WHERE project_id = :p ORDER BY created_at, wp_code"), {"p": pid})).all()
    return [tuple(r) for r in rows]


async def _generate(c: AsyncClient, pid, codes: list[str]) -> dict:
    r = await c.post(f"/api/projects/{pid}/working-papers/generate-from-codes", json={"wp_codes": codes, "year": YEAR})
    assert r.status_code == 200, r.text
    return _data(r)


def _h3_entry(status: str, reason: str | None = None) -> dict:
    entry = {"kind": "scope", "cycle": "H", "wp_index_code": "H3", "target_status": status}
    if reason:
        entry["skip_reason"] = reason
    return entry


async def _trim(c: AsyncClient, pid, entry: dict) -> tuple[dict, dict, str]:
    pv = await c.post(f"/api/projects/{pid}/procedure-trim/preview", json={"entries": [entry]})
    assert pv.status_code == 200, pv.text
    preview = _data(pv)
    request_id = f"r21-{entry['target_status']}-{uuid.uuid4().hex[:8]}"
    res = await c.post(f"/api/projects/{pid}/procedure-trim/apply",
                       json={"entries": [entry], "preview_id": preview["preview_id"], "request_id": request_id})
    assert res.status_code == 200, res.text
    return preview, _data(res), request_id


async def test_trim_generate_delegate_visibility_lock_restore_chain(db, tmp_path):
    s = db
    await _ensure_lifecycle_table(s)
    w = await _world(s)
    pid = w.pid

    # 1. 经理按编码生成：文件落在临时存储目录（不写真实存储）
    async with _client(s, w.manager) as c:
        first = await _generate(c, pid, ["D1", "D2", "H3"])
    assert first["created_codes"] == ["D1", "D2", "H3"], first
    assert (first["failures"], first["skipped_trimmed_codes"], first["in_recycle_codes"]) == ([], [], [])
    papers = await _papers(s, pid)
    storage = (tmp_path / "wp_storage").resolve()
    for code in ("D1", "D2", "H3"):
        path = Path(papers[code].file_path).resolve()
        assert path.is_file() and storage in path.parents, (code, path)
    wp = {code: papers[code].id for code in papers}

    # 2. 经理粗裁 H3：已生成的 H3 移入回收站
    async with _client(s, w.manager) as c:
        preview, trimmed, trim_request = await _trim(c, pid, _h3_entry("not_applicable", "本期无投资性房地产"))
        assert preview["recycle_preview"]["to_recycle"] == ["H3"], preview["recycle_preview"]
        assert preview["recycle_preview"]["substantive"] == [], "刚生成、没编制过的底稿不需要二次确认"
        assert (trimmed["recycled_codes"], trimmed["restored_codes"]) == (["H3"], [])
        rb = await c.get("/api/recycle-bin", params={"item_type": "working_paper"})
    assert rb.status_code == 200, rb.text
    index = await _index(s, pid)
    assert index["H3"].is_deleted is True and index["D2"].is_deleted is False
    assert await _events(s, pid) == [("H3", "recycled", "trim", str(w.manager.id), trim_request)]
    [h3_item] = [i for i in _data(rb)["items"] if i["id"] == str(index["H3"].id)]
    assert h3_item["deleted_by"] == str(w.manager.id) and h3_item["deleted_by_name"], h3_item

    # 3. 再生成 H3 / H3-1：已裁优先于「在回收站」，两个都跳过、不建
    async with _client(s, w.manager) as c:
        again = await _generate(c, pid, ["H3", "H3-1"])
    assert (again["created_codes"], again["skipped_trimmed_codes"]) == ([], ["H3", "H3-1"]), again
    assert (again["in_recycle_codes"], again["existing_codes"]) == ([], [])
    assert "H3-1" not in await _index(s, pid)

    # 4. 审计员不能裁剪、不能委派
    delegation = {"selector": {"kind": "workpaper", "wp_index_ids": [str(index["D2"].id)]},
                  "assignee_staff_id": str(w.a_staff.id)}
    async with _client(s, w.auditor) as c:
        r = await c.post(f"/api/projects/{pid}/procedure-trim/preview", json={"entries": [_h3_entry("execute")]})
        assert r.status_code == 403, r.text
        r = await c.post(f"/api/projects/{pid}/procedure-delegations/preview", json=delegation)
        assert r.status_code == 403, r.text

    # 5. 经理把 D2 委派给审计员
    async with _client(s, w.manager) as c:
        pv = await c.post(f"/api/projects/{pid}/procedure-delegations/preview", json=delegation)
        assert pv.status_code == 200, pv.text
        dpv = _data(pv)
        assert dpv["preparation_ready"] is True and dpv["summary"]["would_assign"] > 0, dpv["summary"]
        ap = await c.post(f"/api/projects/{pid}/procedure-delegations/apply", json={
            **delegation, "preview_id": dpv["preview_id"], "request_id": f"r21-del-{uuid.uuid4().hex[:8]}"})
        assert ap.status_code == 200, ap.text
    applied = _data(ap)["applied"]
    assert applied == dpv["summary"]["would_assign"]
    assigned = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask).where(
        ProcedureRowTask.project_id == pid, ProcedureRowTask.wp_index_id == index["D2"].id,
        ProcedureRowTask.assignee_staff_id == w.a_staff.id, ProcedureRowTask.is_deleted == sa.false(),
    ))).scalar_one()
    assert assigned == applied


    # 6. 可见：审计员只看到被委派的 D2；打开别的底稿 404 且不暴露存在性
    reset_epoch_cache()
    detail = f"/api/projects/{pid}/working-papers/{{}}"
    listing = f"/api/projects/{pid}/working-papers"
    async with _client(s, w.auditor) as c:
        r = await c.get(listing, params={"page_size": 100})
        assert r.status_code == 200, r.text
        assert [i["wp_code"] for i in _data(r)["items"]] == ["D2"]
        assert (await c.get(detail.format(wp["D2"]))).status_code == 200
        for code in ("D1", "H3"):
            r = await c.get(detail.format(wp[code]))
            assert r.status_code == 404 and _wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, (code, r.text)
        rc = await c.get(f"/api/workpapers/{wp['D2']}/render-config")
        assert not (rc.status_code == 404 and _wire_detail(rc) == EXTERNAL_NOT_FOUND_DETAIL), rc.text
    for who in ("manager", "admin"):
        async with _client(s, getattr(w, who)) as c:
            r = await c.get(listing, params={"page_size": 100})
            assert r.status_code == 200, (who, r.text)
            assert [i["wp_code"] for i in _data(r)["items"]] == ["D1", "D2"], who
            assert (await c.get(detail.format(wp["D1"]))).status_code == 200, who
            assert (await c.get(detail.format(wp["H3"]))).status_code == 404, f"{who}：回收站里的底稿打不开"

    # 7. 编辑锁
    lock = "/api/editing-locks/workpaper/{}"
    async with _client(s, w.auditor) as c:
        assert (await c.post(lock.format(wp["D2"]))).status_code == 200
        r = await c.post(lock.format(wp["D1"]))
        assert r.status_code == 404 and _wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, r.text
    async with _client(s, w.manager) as c:
        r = await c.post(lock.format(wp["D2"]))
        assert r.status_code == 409, r.text
        held = _wire_detail(r)
        assert held["error_code"] == "LOCK_HELD" and held["locked_by"] == str(w.auditor.id), held
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 404, "只有持有人能释放"
    async with _client(s, w.auditor) as c:
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 200
    async with _client(s, w.manager) as c:
        assert (await c.post(lock.format(wp["D2"]))).status_code == 200
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 200
    async with _client(s, w.admin) as c:
        assert (await c.post(lock.format(wp["D1"]))).status_code == 200
        assert (await c.delete(lock.format(wp["D1"]))).status_code == 200

    # 8. 经理恢复执行 H3：从回收站恢复
    async with _client(s, w.manager) as c:
        preview, restored, restore_request = await _trim(c, pid, _h3_entry("execute"))
    assert preview["recycle_preview"]["to_restore"] == ["H3"], preview["recycle_preview"]
    assert (restored["restored_codes"], restored["recycled_codes"]) == (["H3"], [])
    assert (await _index(s, pid))["H3"].is_deleted is False
    assert await _events(s, pid) == [("H3", "recycled", "trim", str(w.manager.id), trim_request),
                                     ("H3", "restored", "trim", str(w.manager.id), restore_request)]
    reset_epoch_cache()
    async with _client(s, w.manager) as c:
        assert (await c.get(detail.format(wp["H3"]))).status_code == 200
    async with _client(s, w.auditor) as c:
        r = await c.get(detail.format(wp["H3"]))
        assert r.status_code == 404 and _wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, "H3 不在审计员的循环范围"

    # 9. 再生成 H3 / H3-1：H3 已存在、H3-1 新建
    async with _client(s, w.manager) as c:
        final = await _generate(c, pid, ["H3", "H3-1"])
    assert (final["existing_codes"], final["created_codes"]) == (["H3"], ["H3-1"]), final
    assert (final["skipped_trimmed_codes"], final["in_recycle_codes"], final["failures"]) == ([], [], [])
