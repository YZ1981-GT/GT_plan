# Feature: procedure-chain-hardening-and-java-contracts — R2 编辑锁鉴权
"""编辑锁端点鉴权（真实 FastAPI app + 真实 PostgreSQL，每例事务回滚）。

原先五个端点只要求登录：打不开某底稿（底稿门 404）的审计员照样能取锁、续期，负责人打开时被锁成只读。
表驱动：未委派成员 / 负责人（lead）/ 被委派执行人（assignee）/ 只做复核（reviewer）/ admin × 取锁 / 续期 / 强制接管 / 列表。
断言状态码 + 锁行（拒绝时不建锁行；续期被拒时本人的锁被放掉）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.models.core import PermissionLevel
from app.models.editing_lock_models import EditingLock
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

from ._factories import IS_PG, mk_project, mk_project_user, mk_row_task, mk_staff, mk_user, mk_working_paper, mk_wp_index
from .test_task15_full_entry_integration import _Ctx, _wire_detail

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real app + gate integration)"),
]


def _lock_url(wp_id) -> str:
    return f"/api/editing-locks/workpaper/{wp_id}"


async def _member(s, proj, user, *, scope="D", level=PermissionLevel.edit):
    pu = await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    pu.permission_level = level
    await s.flush()
    return pu


async def _scenario(s):
    """一张 D2-1 底稿：lead（负责人）、assignee（被委派执行人）、reviewer（只做复核）、outsider（成员但未委派）。"""
    proj = await mk_project(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    lead = await mk_user(s)
    wp.assigned_to = lead.id
    await _member(s, proj, lead)
    assignee = await mk_user(s)
    a_staff = await mk_staff(s, user_id=assignee.id)
    await _member(s, proj, assignee)
    reviewer = await mk_user(s)
    r_staff = await mk_staff(s, user_id=reviewer.id)
    await _member(s, proj, reviewer)
    await mk_row_task(s, proj.id, wi.id, sheet_key="D2A", sheet_name="甲",
                      assignee_staff_id=a_staff.id, reviewer_staff_id=r_staff.id)
    outsider = await mk_user(s)
    await _member(s, proj, outsider, scope="")
    admin = await mk_user(s, role="admin")
    await s.flush()
    return {"proj": proj, "wp": wp, "lead": lead, "assignee": assignee, "reviewer": reviewer,
            "outsider": outsider, "admin": admin}


async def _active_locks(s, wp_id) -> list[EditingLock]:
    rows = (await s.execute(sa.select(EditingLock).where(
        EditingLock.resource_type == "workpaper",
        EditingLock.resource_id == str(wp_id),
        EditingLock.released_at.is_(None),
    ))).scalars().all()
    return list(rows)


async def _hold(s, user, wp_id, client_instance=None) -> EditingLock:
    now = datetime.now(timezone.utc)
    lock = EditingLock(id=uuid4(), resource_type="workpaper", resource_id=str(wp_id), holder_id=user.id,
                       holder_name=user.username, acquired_at=now, heartbeat_at=now, client_instance=client_instance)
    s.add(lock)
    await s.flush()
    return lock


@pytest.mark.parametrize("who, expected", [
    ("outsider", 404), ("reviewer", 404), ("lead", 200), ("assignee", 200), ("admin", 200),
])
async def test_acquire_by_identity(who, expected):
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        async with ctx.bind_app(w[who]) as c:
            r = await c.post(_lock_url(w["wp"].id))
        assert r.status_code == expected, r.text
        locks = await _active_locks(s, w["wp"].id)
        if expected == 404:
            assert _wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL
            assert locks == []  # 拒绝时不建锁行
        else:
            assert [lk.holder_id for lk in locks] == [w[who].id]
    finally:
        await ctx.__aexit__()


async def test_acquire_denied_does_not_expire_others_stale_lock():
    """被拒的请求不得先清理他人的锁（判定在动锁行之前）。"""
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        held = await _hold(s, w["lead"], w["wp"].id)
        held.heartbeat_at = datetime(2020, 1, 1, tzinfo=timezone.utc)  # 早已过期
        await s.flush()
        async with ctx.bind_app(w["outsider"]) as c:
            r = await c.post(_lock_url(w["wp"].id))
        assert r.status_code == 404
        await s.refresh(held)
        assert held.released_at is None
    finally:
        await ctx.__aexit__()


async def test_heartbeat_denied_releases_own_lock():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        held = await _hold(s, w["outsider"], w["wp"].id)  # 撤权前取到的锁
        async with ctx.bind_app(w["outsider"]) as c:
            r = await c.patch(f"{_lock_url(w['wp'].id)}/heartbeat")
        assert r.status_code == 404
        await s.refresh(held)
        assert held.released_at is not None
    finally:
        await ctx.__aexit__()


async def test_heartbeat_allowed_for_holder():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        await _hold(s, w["assignee"], w["wp"].id)
        async with ctx.bind_app(w["assignee"]) as c:
            r = await c.patch(f"{_lock_url(w['wp'].id)}/heartbeat")
        assert r.status_code == 200, r.text
    finally:
        await ctx.__aexit__()


@pytest.mark.parametrize("who, expected", [("outsider", 404), ("assignee", 403), ("lead", 200), ("admin", 200)])
async def test_force_by_identity(who, expected):
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        other = w["reviewer"] if who != "reviewer" else w["lead"]
        await _hold(s, other, w["wp"].id)
        async with ctx.bind_app(w[who]) as c:
            r = await c.post(f"{_lock_url(w['wp'].id)}/force", headers={"X-Client-Instance": "win-7"})
        assert r.status_code == expected, r.text
        locks = await _active_locks(s, w["wp"].id)
        if expected == 200:
            assert [(lk.holder_id, lk.client_instance) for lk in locks] == [(w[who].id, "win-7")]
        else:
            assert [lk.holder_id for lk in locks] == [other.id]  # 被拒不动原锁
    finally:
        await ctx.__aexit__()


async def test_active_list_admin_only():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        async with ctx.bind_app(w["lead"]) as c:
            assert (await c.get("/api/editing-locks/active")).status_code == 403
        async with ctx.bind_app(w["admin"]) as c:
            assert (await c.get("/api/editing-locks/active")).status_code == 200
    finally:
        await ctx.__aexit__()


async def test_unknown_type_and_bad_id_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        w = await _scenario(s)
        async with ctx.bind_app(w["admin"]) as c:
            assert (await c.post("/api/editing-locks/other/abc")).status_code == 404
            assert (await c.post("/api/editing-locks/workpaper/not-a-uuid")).status_code == 404
            assert (await c.post(f"/api/editing-locks/audit_report/{w['proj'].id}")).status_code == 404  # 缺后缀
    finally:
        await ctx.__aexit__()


@pytest.mark.parametrize("level, expected", [(None, 403), (PermissionLevel.readonly, 403), (PermissionLevel.edit, 200)])
async def test_audit_report_lock_by_member_level(level, expected):
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        proj = await mk_project(s)
        user = await mk_user(s)
        if level is not None:
            await _member(s, proj, user, level=level)
        async with ctx.bind_app(user) as c:
            r = await c.post(f"/api/editing-locks/audit_report/{proj.id}_report")
        assert r.status_code == expected, r.text
    finally:
        await ctx.__aexit__()


async def test_disclosure_note_lock_requires_note_edit_access():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False  # 与生产会话一致（database.async_session）
    try:
        proj = await mk_project(s)
        stranger = await mk_user(s)
        async with ctx.bind_app(stranger) as c:
            r = await c.post(f"/api/editing-locks/disclosure_note/{proj.id}_note")
        assert r.status_code == 403
        admin = await mk_user(s, role="admin")
        async with ctx.bind_app(admin) as c:
            r = await c.post(f"/api/editing-locks/disclosure_note/{proj.id}_note")
        assert r.status_code == 200, r.text
    finally:
        await ctx.__aexit__()
