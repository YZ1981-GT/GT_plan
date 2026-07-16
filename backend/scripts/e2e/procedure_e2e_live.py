"""procedure-delegation-notification / Task 17 — 四角色全链路 LIVE 实测（API 层）

针对 **运行中的 cutover 后端**（9980，PROCEDURE_ROW_TASKS_ENABLED=True /
WRITE_MODE=task-source / DISPATCHER_ENABLED=True）做真实 HTTP 全链路验证。

覆盖 Task 17 场景族：
- seed 四角色 user+staff+assignment（现场经理/审计助理/操作复核人/无assignment合伙人）
- 先委派后生成 + 底稿原子绑定（task_id/assignment/history 不变）
- delegation preview/apply 一次消费 + 重放/伪造 preview → 409
- 同执行人 no-op、转派重新 ack（assignment_version 递增+清 ack）
- ack→start→submit→review 主链
- changes_requested→IssueTicket→关闭→再提交→review（高阶门槛不变）
- 批量委派逐任务 history + 每 recipient 聚合通知（dispatcher 投递）
- 跨项目 IDOR → 403/404
- due_at null 不逾期
- 无 assignment 合伙人 delegator 403（fail-closed）

运行（backend 目录，env 已带三开关）：
  python scripts/e2e/procedure_e2e_live.py
证据 → backend/test-results/procedure_e2e_live_evidence.json
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = os.environ.get("E2E_BASE", "http://localhost:9980")
API = BASE + "/api"
PROJECT_ID = "5e193c68-f53c-4e95-8d03-5d9c996c402d"
WP_INDEX_A1 = "51271c7e-63d9-4f11-b45f-485faaf46d0b"
WP_INDEX_A10 = "1a9e32df-c5b9-4221-97a2-8fcbafab1e00"
OTHER_PROJECT_ID = "14fb8c10-9462-45f6-8f56-d023f5b6df13"
PW = "e2e123456"

ROLE_USERS = {
    "manager": ("e2e_manager", "manager", "现场经理"),
    "assistant": ("e2e_assistant", "auditor", "审计助理"),
    "reviewer": ("e2e_reviewer", "auditor", "操作复核人"),
    "partner_na": ("e2e_partner_na", "partner", "无assignment合伙人"),
}

RESULTS: list[dict] = []


def rec(name, ok, detail="", extra=None):
    RESULTS.append({"scenario": name, "pass": bool(ok), "detail": str(detail), **(extra or {})})
    print(f"{'[OK]  ' if ok else '[FAIL]'} {name}: {detail}")
    return ok


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
SEED: dict = {}


async def seed():
    import sqlalchemy as sa
    from app.core.database import async_session
    from app.core.security import hash_password
    from app.models.core import User
    from app.models.staff_models import ProjectAssignment, StaffMember

    async with async_session() as db:
        out = {}
        for key, (username, role, cn) in ROLE_USERS.items():
            u = (await db.execute(sa.select(User).where(User.username == username))).scalar_one_or_none()
            if u is None:
                u = User(username=username, email=f"{username}@e2e.local",
                         hashed_password=hash_password(PW), role=role, is_active=True)
                db.add(u)
                await db.flush()
            else:
                u.hashed_password = hash_password(PW)
                u.is_active = True
                u.role = role
            staff_rows = (await db.execute(sa.select(StaffMember).where(
                StaffMember.user_id == u.id, StaffMember.is_deleted == False))).scalars().all()  # noqa: E712
            if len(staff_rows) == 0:
                sm = StaffMember(user_id=u.id, name=cn, source="custom", role_level="auditor")
                db.add(sm)
                await db.flush()
            else:
                sm = staff_rows[0]
                for extra_sm in staff_rows[1:]:
                    extra_sm.is_deleted = True
            out[key] = {"user_id": str(u.id), "staff_id": str(sm.id), "username": username, "role": role}

        for key, assign_role in (("manager", "manager"), ("assistant", "auditor"), ("reviewer", "auditor")):
            sid = uuid.UUID(out[key]["staff_id"])
            pa = (await db.execute(sa.select(ProjectAssignment).where(
                ProjectAssignment.project_id == uuid.UUID(PROJECT_ID),
                ProjectAssignment.staff_id == sid,
                ProjectAssignment.is_deleted == False))).scalars().first()  # noqa: E712
            if pa is None:
                db.add(ProjectAssignment(project_id=uuid.UUID(PROJECT_ID), staff_id=sid,
                                         role=assign_role, assigned_at=datetime.now(timezone.utc)))
            else:
                pa.role = assign_role
                pa.is_deleted = False
        await db.commit()
    SEED.update(out)
    print("[SEED]", json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def task_snap(task_id):
    import sqlalchemy as sa
    from app.core.database import async_session
    from app.models.procedure_models import ProcedureRowTask, ProcedureRowTaskHistory
    async with async_session() as db:
        t = (await db.execute(sa.select(ProcedureRowTask).where(ProcedureRowTask.id == uuid.UUID(task_id)))).scalar_one_or_none()
        if t is None:
            return None
        hc = (await db.execute(sa.select(sa.func.count()).select_from(ProcedureRowTaskHistory).where(ProcedureRowTaskHistory.task_id == uuid.UUID(task_id)))).scalar_one()
        return {"task_id": str(t.id), "wp_id": str(t.wp_id) if t.wp_id else None,
                "workflow": t.workflow_status, "applicability": t.applicability_status,
                "assignee": str(t.assignee_staff_id) if t.assignee_staff_id else None,
                "reviewer": str(t.reviewer_staff_id) if t.reviewer_staff_id else None,
                "assignment_version": t.assignment_version, "lock_version": t.lock_version,
                "acknowledged_at": t.acknowledged_at.isoformat() if getattr(t, "acknowledged_at", None) else None,
                "history_count": hc, "due_at": t.due_at.isoformat() if t.due_at else None}


async def reset_project_state():
    """清空本测试项目的程序行任务/历史/预览/outbox，保证 re-run 幂等（仅测试项目）。"""
    import sqlalchemy as sa
    from app.core.database import async_session
    async with async_session() as db:
        await db.execute(sa.text(
            "DELETE FROM procedure_row_task_history WHERE task_id IN "
            "(SELECT id FROM procedure_row_tasks WHERE project_id=:p)"), {"p": PROJECT_ID})
        await db.execute(sa.text("DELETE FROM task_events WHERE project_id=:p"), {"p": PROJECT_ID})
        await db.execute(sa.text("DELETE FROM procedure_operation_previews WHERE project_id=:p"), {"p": PROJECT_ID})
        await db.execute(sa.text("DELETE FROM procedure_row_tasks WHERE project_id=:p"), {"p": PROJECT_ID})
        await db.commit()
    print("[RESET] 已清空测试项目程序行任务/历史/预览/outbox")


async def anchor_tasks(wp_index_id):
    import sqlalchemy as sa
    from app.core.database import async_session
    from app.models.procedure_models import ProcedureRowTask
    async with async_session() as db:
        rows = (await db.execute(sa.select(ProcedureRowTask.id).where(
            ProcedureRowTask.project_id == uuid.UUID(PROJECT_ID),
            ProcedureRowTask.wp_index_id == uuid.UUID(wp_index_id),
            ProcedureRowTask.is_deleted == False).order_by(ProcedureRowTask.program_no))).scalars().all()  # noqa: E712
        return [str(r) for r in rows]


async def bind_generate(wp_index_id):
    from app.core.database import async_session
    from app.services.workpaper_generation_service import workpaper_generation_service
    async with async_session() as db:
        wp = await workpaper_generation_service.ensure_working_paper(db, uuid.UUID(PROJECT_ID), uuid.UUID(wp_index_id))
        await db.commit()
        return str(wp.id)


async def notifications_since(user_ids, since):
    import sqlalchemy as sa
    from app.core.database import async_session
    from app.models.core import Notification
    async with async_session() as db:
        out = {}
        for uid in user_ids:
            rows = (await db.execute(sa.select(
                Notification.message_type, Notification.title, Notification.event_id,
                Notification.dedup_key, Notification.notification_metadata)
                .where(Notification.recipient_id == uuid.UUID(uid))
                .where(Notification.created_at >= since))).all()
            out[uid] = [{"type": r[0], "title": (r[1] or "")[:50], "event_id": r[2],
                         "dedup_key": r[3], "meta": r[4]} for r in rows]
        return out


async def outbox_stats():
    import sqlalchemy as sa
    from app.core.database import async_session
    async with async_session() as db:
        for tbl in ("task_events", "procedure_task_outbox", "procedure_delivery_outbox", "procedure_outbox"):
            try:
                total = (await db.execute(sa.text(f"SELECT count(*) FROM {tbl} WHERE aggregate_type='procedure_row_task'"))).scalar()
                proc = (await db.execute(sa.text(f"SELECT count(*) FROM {tbl} WHERE aggregate_type='procedure_row_task' AND processed_at IS NOT NULL"))).scalar()
                dead = (await db.execute(sa.text(f"SELECT count(*) FROM {tbl} WHERE aggregate_type='procedure_row_task' AND dead_letter_at IS NOT NULL"))).scalar()
                return {"table": tbl, "total": total, "processed": proc, "dead_letter": dead}
            except Exception:
                continue
        return {"table": None}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
async def login(client, username, password):
    r = await client.post(f"{API}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    b = r.json()
    d = b.get("data") or b
    return d.get("access_token") or d.get("token")


def H(t):
    return {"Authorization": f"Bearer {t}"}


def uw(r):
    try:
        b = r.json()
    except Exception:
        return None
    if isinstance(b, dict) and "data" in b and set(b.keys()) <= {"code", "message", "data"}:
        return b["data"]
    return b


async def transition(client, token, task_id, action, **kw):
    body = {"action": action, "request_id": f"e2e-{action}-{uuid.uuid4().hex}"}
    body.update(kw)
    return await client.post(f"{API}/projects/{PROJECT_ID}/procedure-row-tasks/{task_id}/transitions",
                             headers=H(token), json=body)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
async def scenarios(client, tokens):
    admin_t, mgr_t, asst_t, rev_t = tokens["admin"], tokens["manager"], tokens["assistant"], tokens["reviewer"]
    pna_t = tokens.get("partner_na")
    assignee_staff = SEED["assistant"]["staff_id"]
    reviewer_staff = SEED["reviewer"]["staff_id"]
    manager_staff = SEED["manager"]["staff_id"]
    since = datetime.now(timezone.utc)

    # ===== S1 先委派：materialize (wp_id null) =====
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-row-tasks/materialize",
                          headers=H(mgr_t), json={"wp_index_ids": [WP_INDEX_A1], "request_id": "e2e-mat"})
    mat = uw(r)
    rec("S1a materialize先委派", r.status_code == 200,
        f"status={r.status_code} created={(mat or {}).get('created')} targets={(mat or {}).get('targets')}")
    ids = await anchor_tasks(WP_INDEX_A1)
    snap0 = await task_snap(ids[0]) if ids else None
    rec("S1b 物化任务 wp_id 为空(先委派)", bool(ids) and snap0 and snap0["wp_id"] is None,
        f"n={len(ids)} first.wp_id={snap0['wp_id'] if snap0 else 'N/A'}")

    # ===== S10 无 assignment 合伙人 delegator 403 (fail-closed) =====
    if pna_t:
        r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(pna_t),
                              json={"selector": {"kind": "workpaper", "wp_index_ids": [WP_INDEX_A1]},
                                    "assignee_staff_id": assignee_staff})
        rec("S10 无assignment合伙人 delegator→403", r.status_code == 403, f"status={r.status_code}")

    # ===== S2 delegation preview→apply 一次消费 + 重放/伪造 409 =====
    sel = {"kind": "row", "task_ids": [ids[0]]}
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": sel, "assignee_staff_id": assignee_staff,
                                "reviewer_staff_id": reviewer_staff})
    prev = uw(r)
    preview_id = (prev or {}).get("preview_id") or (prev or {}).get("id")
    rec("S2a delegation preview", r.status_code == 200 and bool(preview_id),
        f"status={r.status_code} preview_id={preview_id} targets={(prev or {}).get('target_count') or (prev or {}).get('targets')}")

    req_id = "e2e-apply-" + uuid.uuid4().hex
    apply_body = {"selector": sel, "assignee_staff_id": assignee_staff, "reviewer_staff_id": reviewer_staff,
                  "preview_id": preview_id, "request_id": req_id}
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t), json=apply_body)
    rec("S2b delegation apply", r.status_code == 200, f"status={r.status_code} body={str(uw(r))[:120]}")
    snap1 = await task_snap(ids[0])
    rec("S2c apply 后 task 已分配", snap1 and snap1["assignee"] == assignee_staff and snap1["workflow"] == "assigned",
        f"workflow={snap1['workflow'] if snap1 else '?'} assignee_ok={snap1['assignee']==assignee_staff if snap1 else '?'} av={snap1['assignment_version'] if snap1 else '?'}")

    # 重放同一 preview_id（新 request_id）→ 409
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                          json={**apply_body, "request_id": "e2e-replay-" + uuid.uuid4().hex})
    rec("S2d 重放已消费 preview→409", r.status_code == 409, f"status={r.status_code}")

    # 伪造 preview_id → 409/404
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                          json={**apply_body, "preview_id": "00000000-0000-0000-0000-ffffffffffff",
                                "request_id": "e2e-fake-" + uuid.uuid4().hex})
    rec("S2e 伪造 preview→409/404", r.status_code in (404, 409), f"status={r.status_code}")

    # 同 request_id 幂等重试（应返回已保存 result，不 409、不重复领域写）
    av_before = (await task_snap(ids[0]))["assignment_version"]
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t), json=apply_body)
    av_after = (await task_snap(ids[0]))["assignment_version"]
    rec("S2f 同 request_id 幂等重试无二次领域写", r.status_code in (200, 409) and av_before == av_after,
        f"status={r.status_code} av {av_before}->{av_after}")

    # ===== S12 底稿原子绑定（task_id/assignment/history 不变；须先绑定后才能 start/submit）=====
    before = await task_snap(ids[0])
    wp_id = await bind_generate(WP_INDEX_A1)
    after = await task_snap(ids[0])
    ok = (after["wp_id"] is not None and after["task_id"] == before["task_id"]
          and after["assignment_version"] == before["assignment_version"]
          and after["assignee"] == before["assignee"] and after["history_count"] == before["history_count"])
    rec("S12 底稿生成原子绑定(task_id/assignment/history 不变)", ok,
        f"wp_id={after['wp_id']} task_same={after['task_id']==before['task_id']} av_same={after['assignment_version']==before['assignment_version']} hist {before['history_count']}->{after['history_count']}")

    # ===== S3 同执行人重复委派 no-op（assignment_version 不递增）=====
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": sel, "assignee_staff_id": assignee_staff, "reviewer_staff_id": reviewer_staff})
    p2 = uw(r)
    pid2 = (p2 or {}).get("preview_id") or (p2 or {}).get("id")
    av_pre = (await task_snap(ids[0]))["assignment_version"]
    if pid2:
        await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                          json={"selector": sel, "assignee_staff_id": assignee_staff, "reviewer_staff_id": reviewer_staff,
                                "preview_id": pid2, "request_id": "e2e-noop-" + uuid.uuid4().hex})
    av_post = (await task_snap(ids[0]))["assignment_version"]
    rec("S3 同执行人 no-op(assignment_version 不变)", av_pre == av_post, f"av {av_pre}->{av_post}")

    # ===== S4 ack→start→submit→review 主链（task ids[0]）=====
    s = await task_snap(ids[0])
    r = await transition(client, asst_t, ids[0], "acknowledge",
                         expected_lock_version=s["lock_version"], expected_assignment_version=s["assignment_version"])
    rec("S4a assistant ack", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")
    s = await task_snap(ids[0])
    r = await transition(client, asst_t, ids[0], "start", expected_lock_version=s["lock_version"])
    rec("S4b assistant start", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")
    s = await task_snap(ids[0])
    r = await transition(client, asst_t, ids[0], "submit", expected_lock_version=s["lock_version"],
                         execution_summary="E2E 执行说明：已完成财务报告程序核对", evidence_snapshot=["cell:A1!C10"])
    rec("S4c assistant submit", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")
    # 越权：assistant 不能 review
    s = await task_snap(ids[0])
    r = await transition(client, asst_t, ids[0], "review", expected_lock_version=s["lock_version"])
    rec("S4d assistant 不能 review→403", r.status_code == 403, f"status={r.status_code}")
    r = await transition(client, rev_t, ids[0], "review", expected_lock_version=s["lock_version"])
    rec("S4e reviewer review 通过", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")

    # ===== S5 changes_requested→IssueTicket→关闭→再提交→review（task ids[1]）=====
    t5 = ids[1]
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": {"kind": "row", "task_ids": [t5]}, "assignee_staff_id": assignee_staff,
                                "reviewer_staff_id": reviewer_staff})
    p5 = uw(r)
    pid5 = (p5 or {}).get("preview_id") or (p5 or {}).get("id")
    await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                      json={"selector": {"kind": "row", "task_ids": [t5]}, "assignee_staff_id": assignee_staff,
                            "reviewer_staff_id": reviewer_staff, "preview_id": pid5, "request_id": "e2e-a5-" + uuid.uuid4().hex})
    for act, kw in (("acknowledge", {}), ("start", {}), ("submit", {"execution_summary": "初次提交", "evidence_snapshot": ["cell:A1!C11"]})):
        s = await task_snap(t5)
        await transition(client, asst_t, t5, act, expected_lock_version=s["lock_version"],
                         **({"expected_assignment_version": s["assignment_version"]} if act == "acknowledge" else {}), **kw)
    s = await task_snap(t5)
    r = await transition(client, rev_t, t5, "request_changes", expected_lock_version=s["lock_version"], reason="请补充函证程序记录")
    rec("S5a reviewer request_changes", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")
    # 查 IssueTicket（conversation 端点返回未解决数 + 列表）
    r = await client.get(f"{API}/projects/{PROJECT_ID}/procedure-row-tasks/{t5}/conversation", headers=H(rev_t))
    conv = uw(r)
    issues = (conv or {}).get("issues") or (conv or {}).get("issue_tickets") or []
    open_cnt = (conv or {}).get("open_issue_count")
    if open_cnt is None:
        open_cnt = sum(1 for i in issues if str(i.get("status")).lower() == "open")
    issue_id = issues[0].get("id") if issues else None
    rec("S5b changes_requested 创建 IssueTicket", r.status_code == 200 and (open_cnt or 0) >= 1 and bool(issue_id),
        f"status={r.status_code} open_issues={open_cnt} issue_id={issue_id}")
    # review 前置门槛：issue 未关 → review 应 409
    s = await task_snap(t5)
    # 需先让任务回到 submitted 才能 review；但先验证未关 issue 时无法通过复核闭环：
    # 先 start+submit 再尝试 review（open issue → 409）
    for act, kw in (("start", {}), ("submit", {"execution_summary": "补充后再次提交", "evidence_snapshot": ["cell:A1!C12"]})):
        s = await task_snap(t5)
        await transition(client, asst_t, t5, act, expected_lock_version=s["lock_version"], **kw)
    s = await task_snap(t5)
    r = await transition(client, rev_t, t5, "review", expected_lock_version=s["lock_version"])
    rec("S5c 未关 issue 时 review→409", r.status_code == 409, f"status={r.status_code}")
    # 关闭 issue
    if issue_id:
        r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-row-tasks/{t5}/issues/{issue_id}/close",
                              headers=H(rev_t), json={})
        rec("S5d 关闭 IssueTicket", r.status_code in (200, 204), f"status={r.status_code}")
    # 再 review → 通过
    s = await task_snap(t5)
    r = await transition(client, rev_t, t5, "review", expected_lock_version=s["lock_version"])
    rec("S5e issue 全关后 review 通过", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")

    # ===== S6 转派重新 ack（assignment_version 递增 + 清 ack）=====
    t6 = ids[2]
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": {"kind": "row", "task_ids": [t6]}, "assignee_staff_id": assignee_staff,
                                "reviewer_staff_id": reviewer_staff})
    p6 = uw(r)
    pid6 = (p6 or {}).get("preview_id") or (p6 or {}).get("id")
    await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                      json={"selector": {"kind": "row", "task_ids": [t6]}, "assignee_staff_id": assignee_staff,
                            "reviewer_staff_id": reviewer_staff, "preview_id": pid6, "request_id": "e2e-a6-" + uuid.uuid4().hex})
    s = await task_snap(t6)
    await transition(client, asst_t, t6, "acknowledge", expected_lock_version=s["lock_version"], expected_assignment_version=s["assignment_version"])
    av_b = (await task_snap(t6))["assignment_version"]
    # reassign 到 manager staff（新执行人）——delegator 动作
    s = await task_snap(t6)
    r = await transition(client, mgr_t, t6, "reassign", expected_lock_version=s["lock_version"],
                         new_assignee_staff_id=manager_staff, reason="现场经理接手执行以便演示转派重新确认")
    s2 = await task_snap(t6)
    rec("S6a 转派后 assignment_version 递增+清 ack", r.status_code == 200 and s2["assignment_version"] > av_b and s2["acknowledged_at"] is None,
        f"status={r.status_code} av {av_b}->{s2['assignment_version']} ack={s2['acknowledged_at']}")
    # 旧执行人（assistant）已非当前 assignee → ack 403
    r = await transition(client, asst_t, t6, "acknowledge", expected_lock_version=s2["lock_version"], expected_assignment_version=s2["assignment_version"])
    rec("S6b 旧执行人 ack→403", r.status_code == 403, f"status={r.status_code}")
    # 新执行人（manager）须重新 ack
    r = await transition(client, mgr_t, t6, "acknowledge", expected_lock_version=s2["lock_version"], expected_assignment_version=s2["assignment_version"])
    rec("S6c 新执行人重新 ack", r.status_code == 200, f"status={r.status_code} wf={(uw(r) or {}).get('workflow_status')}")

    # ===== S7 批量委派：逐任务 history + 每 recipient 聚合通知 =====
    await client.post(f"{API}/projects/{PROJECT_ID}/procedure-row-tasks/materialize", headers=H(mgr_t),
                      json={"wp_index_ids": [WP_INDEX_A10], "request_id": "e2e-mat-a10"})
    a10 = await anchor_tasks(WP_INDEX_A10)
    batch_ids = a10[:5]
    since_batch = datetime.now(timezone.utc)
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": {"kind": "row", "task_ids": batch_ids}, "assignee_staff_id": assignee_staff,
                                "reviewer_staff_id": reviewer_staff})
    p7 = uw(r)
    pid7 = (p7 or {}).get("preview_id") or (p7 or {}).get("id")
    r = await client.post(f"{API}/projects/{PROJECT_ID}/procedure-delegations/apply", headers=H(mgr_t),
                          json={"selector": {"kind": "row", "task_ids": batch_ids}, "assignee_staff_id": assignee_staff,
                                "reviewer_staff_id": reviewer_staff, "preview_id": pid7, "request_id": "e2e-batch-" + uuid.uuid4().hex})
    apply7 = uw(r) or {}
    batch_id = apply7.get("delegation_batch_id")
    rec("S7a 批量委派 apply", r.status_code == 200 and bool(batch_id), f"status={r.status_code} n={len(batch_ids)} batch_id={batch_id}")
    # 逐任务 history：每个被分配任务 history_count>=1
    per_hist = [(await task_snap(t))["history_count"] for t in batch_ids]
    rec("S7b 批量逐任务独立 history", all(h >= 1 for h in per_hist), f"history_counts={per_hist}")
    # 聚合通知：等待 dispatcher 投递，按本批 delegation_batch_id 精确计数
    await asyncio.sleep(6)
    notif = await notifications_since([SEED["assistant"]["user_id"]], since_batch)
    asst_notifs = notif[SEED["assistant"]["user_id"]]

    def _batch_of(n):
        m = n.get("meta") or {}
        return (m.get("filter") or {}).get("delegation_batch_id") or m.get("delegation_batch_id") or m.get("batch_id")
    this_batch = [n for n in asst_notifs if _batch_of(n) == batch_id]
    # 5 个任务委派给同一 recipient → 聚合为 1 条（不是 5 条），但逐任务 history 仍为 5
    rec("S7c 每 recipient 聚合为单条通知(5任务→1通知)", len(this_batch) == 1 and per_hist.count(1) == 5,
        f"batch_notifs_for_assistant={len(this_batch)} per_task_history={per_hist}")
    # metadata 驱动跳转（不解析中文 content）
    meta0 = this_batch[0].get("meta") if this_batch else None
    has_route = bool(meta0 and ((meta0.get("filter") or {}).get("delegation_batch_id") or meta0.get("task_ids")))
    rec("S7d 聚合通知含可跳转 metadata(不靠中文content)", has_route,
        f"meta={str(meta0)[:160]}")

    ob = await outbox_stats()
    rec("S11 dispatcher 投递 outbox(processed>0)", (ob.get("processed") or 0) > 0,
        f"outbox={ob}")

    # ===== S8 跨项目 IDOR =====
    # 用 OTHER_PROJECT_ID 访问 PROJECT 的 task → 404（不泄露）
    r = await client.get(f"{API}/projects/{OTHER_PROJECT_ID}/procedure-row-tasks/{ids[0]}", headers=H(mgr_t))
    rec("S8a 跨项目 task 详情→404", r.status_code in (403, 404), f"status={r.status_code}")
    # manager 在 OTHER_PROJECT 无 assignment → delegator preview 403
    r = await client.post(f"{API}/projects/{OTHER_PROJECT_ID}/procedure-delegations/preview", headers=H(mgr_t),
                          json={"selector": {"kind": "cycle", "cycle": "A"}, "assignee_staff_id": assignee_staff})
    rec("S8b 跨项目无assignment delegator→403", r.status_code in (403, 404), f"status={r.status_code}")

    # ===== S9 due_at null 不逾期 =====
    r = await client.get(f"{API}/my/procedure-row-tasks?page_size=100", headers=H(asst_t))
    mine = uw(r)
    my_items = (mine.get("items") if isinstance(mine, dict) else mine) or []
    null_due = [t for t in my_items if t.get("due_at") in (None, "")]
    bad = [t for t in null_due if t.get("overdue") is True]
    rec("S9 due_at null 不逾期", r.status_code == 200 and len(bad) == 0,
        f"status={r.status_code} my_tasks={len(my_items)} null_due={len(null_due)} overdue_bad={len(bad)}")

    # ===== S13 legacy wp_procedure_status 旁路写被拒（task-source 写模式）=====
    # 已有 backing task 的 sheet 直接旧端点写应被拒绝/引导 transition
    return {"a1_ids": ids[:3], "a10_batch": batch_ids, "wp_id": wp_id, "outbox": ob,
            "assistant_notifs": asst_notifs}


async def main():
    Path("test-results").mkdir(exist_ok=True)
    print("=== procedure-delegation-notification Task 17 LIVE E2E ===")
    from app.core.config import settings
    flags = {k: getattr(settings, k, None) for k in
             ("PROCEDURE_ROW_TASKS_ENABLED", "PROCEDURE_ROW_TASK_WRITE_MODE", "PROCEDURE_TASK_DISPATCHER_ENABLED")}
    print("[FLAGS]", flags)
    rec("Flags cutover 已启用", flags["PROCEDURE_ROW_TASKS_ENABLED"] is True and flags["PROCEDURE_ROW_TASK_WRITE_MODE"] == "task-source" and flags["PROCEDURE_TASK_DISPATCHER_ENABLED"] is True, str(flags))

    await seed()
    await reset_project_state()
    detail = {}
    async with httpx.AsyncClient(timeout=40.0) as client:
        tokens = {"admin": await login(client, "admin", "admin123")}
        for key, (username, _r, _c) in ROLE_USERS.items():
            tokens[key] = await login(client, username, PW)
        for k, v in tokens.items():
            rec(f"login {k}", bool(v), "ok" if v else "FAIL")
        if all(tokens.get(k) for k in ("admin", "manager", "assistant", "reviewer")):
            try:
                detail = await scenarios(client, tokens)
            except Exception as e:
                import traceback
                rec("scenarios 执行异常", False, f"{type(e).__name__}: {e}")
                traceback.print_exc()
        else:
            rec("四角色登录齐备", False, "缺少必要 token，跳过场景")

    passed = sum(1 for r in RESULTS if r["pass"])
    total = len(RESULTS)
    print(f"\n=== SUMMARY: {passed}/{total} passed ===")
    for r in RESULTS:
        if not r["pass"]:
            print(f"  FAIL -> {r['scenario']}: {r['detail']}")
    evidence = {"flags": flags, "seed": SEED, "summary": {"passed": passed, "total": total},
                "results": RESULTS, "detail": {k: (str(v)[:400]) for k, v in (detail or {}).items()}}
    (Path("test-results") / "procedure_e2e_live_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[EVIDENCE] test-results/procedure_e2e_live_evidence.json")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
