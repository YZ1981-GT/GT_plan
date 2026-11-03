"""程序链端到端用例的公共世界与请求助手（跨角色链路用例与 PG 契约用例共用）。

世界：一个【测试】项目（审计年度 2025、一行试算表、H 循环的 H3 程序）+ 系统管理员 + 项目经理
（唯一人员档案 + 团队分配 manager + 项目成员 edit：可裁剪、委派、生成）+ 审计员（团队分配勾选 D 循环 + 项目成员 edit）。
世界里的人员都是快照（不是 ORM 对象）：路由出错时会回滚保存点，会话里的 ORM 对象随之过期，之后再读属性就是
异步懒加载（MissingGreenlet）。
"""
from __future__ import annotations

import types
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.migration_runner import MigrationRunner
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import PermissionLevel
from app.models.workpaper_models import WorkingPaper, WpIndex
from tests.procedure_delegation_visibility._factories import (
    mk_assignment,
    mk_procedure_instance,
    mk_project,
    mk_project_user,
    mk_staff,
    mk_user,
)

YEAR = 2025
V207 = Path(__file__).resolve().parents[2] / "migrations" / "V207__workpaper_lifecycle_events.sql"


def principal(user):
    """路由里有 rollback（只回滚保存点）⇒ 不把 ORM 用户对象交给依赖，免得过期属性触发懒加载。"""
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 full_name=None, is_active=True, is_deleted=False)


def client(s: AsyncSession, user) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    who = principal(user)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def data(resp):
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def wire_detail(resp):
    """真实应用：响应包装把错误详情放进 message。"""
    body = resp.json()
    return (body.get("detail") or body.get("message")) if isinstance(body, dict) else None


async def ensure_lifecycle_table(s: AsyncSession) -> None:
    """真库在下次全量重启前可能还没有 V207 的表（热重载不跑迁移）⇒ 事务里执行 V207 本身，回滚即撤销。"""
    if (await s.execute(sa.text("SELECT to_regclass('public.workpaper_lifecycle_events')"))).scalar_one() is None:
        for stmt in MigrationRunner._split_sql_statements(V207.read_text(encoding="utf-8")):
            await s.execute(sa.text(stmt))


async def member(s, project, *, role: str, cycles: tuple[str, ...] = ()):
    user = await mk_user(s, role=role)
    staff = await mk_staff(s, user_id=user.id)
    assignment = await mk_assignment(s, project.id, staff.id, role=role)
    assignment.assigned_cycles = list(cycles) or None
    pu = await mk_project_user(s, project.id, user.id, role=role, scope_cycles=",".join(cycles) or None)
    pu.permission_level = PermissionLevel.edit
    await s.flush()
    return user, staff


async def world(s):
    project = await mk_project(s)
    project.name = f"【测试】程序链跨角色_{uuid.uuid4().hex[:6]}"
    project.audit_year = YEAR
    project.audit_period_end = date(YEAR, 12, 31)
    admin = await mk_user(s, role="admin")
    manager, m_staff = await member(s, project, role="manager")
    auditor, a_staff = await member(s, project, role="auditor", cycles=("D",))
    s.add(TrialBalance(project_id=project.id, year=YEAR, company_code="001", standard_account_code="1001",
                       account_name="库存现金", account_category=AccountCategory.asset,
                       unadjusted_amount=Decimal("1"), audited_amount=Decimal("1")))
    await mk_procedure_instance(s, project.id, audit_cycle="H", wp_code="H3")  # 粗裁的对象：H 循环的 H3 程序
    await s.flush()
    return types.SimpleNamespace(pid=project.id, admin=principal(admin), manager=principal(manager),
                                 m_staff=types.SimpleNamespace(id=m_staff.id), auditor=principal(auditor),
                                 a_staff=types.SimpleNamespace(id=a_staff.id))


async def index_rows(s, pid) -> dict:
    rows = (await s.execute(sa.select(WpIndex.wp_code, WpIndex.id, WpIndex.is_deleted)
                            .where(WpIndex.project_id == pid))).all()
    return {r.wp_code: r for r in rows}


async def papers(s, pid) -> dict:
    rows = (await s.execute(sa.select(WpIndex.wp_code, WorkingPaper.id, WorkingPaper.file_path)
                            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                            .where(WpIndex.project_id == pid))).all()
    return {r.wp_code: r for r in rows}


async def events(s, pid) -> list[tuple]:
    rows = (await s.execute(sa.text(
        "SELECT wp_code, event_type, kind, actor_user_id::text, request_id FROM workpaper_lifecycle_events "
        "WHERE project_id = :p ORDER BY created_at, wp_code"), {"p": pid})).all()
    return [tuple(r) for r in rows]


async def generate(c: AsyncClient, pid, codes: list[str]) -> dict:
    r = await c.post(f"/api/projects/{pid}/working-papers/generate-from-codes", json={"wp_codes": codes, "year": YEAR})
    assert r.status_code == 200, r.text
    return data(r)


def h3_entry(status: str, reason: str | None = None) -> dict:
    entry = {"kind": "scope", "cycle": "H", "wp_index_code": "H3", "target_status": status}
    if reason:
        entry["skip_reason"] = reason
    return entry


async def trim(c: AsyncClient, pid, entry: dict) -> tuple[dict, dict, str]:
    pv = await c.post(f"/api/projects/{pid}/procedure-trim/preview", json={"entries": [entry]})
    assert pv.status_code == 200, pv.text
    preview = data(pv)
    request_id = f"r21-{entry['target_status']}-{uuid.uuid4().hex[:8]}"
    res = await c.post(f"/api/projects/{pid}/procedure-trim/apply",
                       json={"entries": [entry], "preview_id": preview["preview_id"], "request_id": request_id})
    assert res.status_code == 200, res.text
    return preview, data(res), request_id
