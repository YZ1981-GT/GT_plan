"""visibility-isolation-go-live-hardening / Task 6 — Playwright 8 角色 fresh-context 验收 seed.

为 R5 的 Fresh_Context_Acceptance 播种一个**committed**的 8 角色隔离夹具（Acceptance_Role：
Admin/Supervisor/Workpaper_Lead/Row_Assignee/Operation_Reviewer/History_Lead/History_Row/
plain Restricted），并输出 Playwright harness 读取的 fixture JSON。

这套夹具与父 spec Task 17 的 ``TestRoleMatrixApiLevel._seed`` 同构（同样的 in-scope=D 主编 /
scope-internal-not-delegated / row 委派 / out-of-scope=K 被委派 / 跨项目 / 历史快照），但**COMMIT**
到 dev 库供真实浏览器（3030 前端 → 9980 后端 gate）走 fresh navigation 深链验收。

真实 PostgreSQL ``audit_platform``；不 mock。幂等：先清理上轮 T6 夹具（按 username 前缀 + 项目名
前缀）再重建。提供 ``--revoke-lead``（撤销 lead 主编 + 递增 policy epoch，供 ≤1s 撤权刷新验收）与
``--cleanup``（FK 安全顺序删除全部 T6 夹具）。

用法（backend 目录）：
  python scripts/e2e/task6_role_acceptance_seed.py            # 播种 + 写 fixture
  python scripts/e2e/task6_role_acceptance_seed.py --revoke-lead  # 撤权（供撤权收敛验收）
  python scripts/e2e/task6_role_acceptance_seed.py --cleanup   # 清理
fixture → audit-platform/frontend/e2e/fixtures/task6_role_acceptance.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# 确保 backend 根目录在 sys.path（脚本方式运行时 sys.path[0] 是脚本目录，不含 backend）
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = (
    _REPO_ROOT / "audit-platform" / "frontend" / "e2e" / "fixtures" / "task6_role_acceptance.json"
)

# 稳定标识（幂等清理用）
USER_PREFIX = "t6_"
PROJECT_NAME = "T6-VIS-GOLIVE-ACCEPTANCE"
OTHER_PROJECT_NAME = "T6-VIS-GOLIVE-OTHER"
PW = "t6pass123"

# 唯一可辨识底稿名（供浏览器断言 no-flash：拒绝时这些名字绝不出现在 DOM）
WP_NAMES = {
    "lead": "T6应收账款主编底稿ZZZUNIQUE",
    "undelegated": "T6预付账款未委派底稿ZZZUNIQUE",
    "row": "T6其他应收款行任务底稿ZZZUNIQUE",
    "external": "T6其他应付款域外底稿ZZZUNIQUE",
    "other": "T6跨项目底稿ZZZUNIQUE",
}

# 非 admin 角色（admin 复用系统内置 admin/admin123）
ROLE_USERS = {
    "supervisor": (f"{USER_PREFIX}supervisor", "auditor"),
    "lead": (f"{USER_PREFIX}lead", "auditor"),
    "assignee": (f"{USER_PREFIX}assignee", "auditor"),
    "reviewer": (f"{USER_PREFIX}reviewer", "auditor"),
    "history_lead": (f"{USER_PREFIX}history_lead", "auditor"),
    "history_row": (f"{USER_PREFIX}history_row", "auditor"),
    "restricted": (f"{USER_PREFIX}restricted", "auditor"),
}


def _load_all_models() -> None:
    """填充完整 ORM registry（解析跨表 FK，如 projects.accounting_standard_id）。"""
    from app.core.schema_drift_detector import SchemaDriftDetector
    SchemaDriftDetector._import_all_models()


async def _cleanup(db) -> None:
    """FK 安全顺序删除全部 T6 夹具（项目 + 用户 + 依赖）。"""
    # 项目 id（本 + other）
    pids = (await db.execute(
        sa.text("SELECT id FROM projects WHERE name IN (:a, :b)"),
        {"a": PROJECT_NAME, "b": OTHER_PROJECT_NAME},
    )).scalars().all()
    uids = (await db.execute(
        sa.text("SELECT id FROM users WHERE username LIKE :p"),
        {"p": f"{USER_PREFIX}%"},
    )).scalars().all()
    if pids:
        pset = [str(x) for x in pids]
        # workpaper_delegation_history / wp_access_security_outbox /
        # wp_visibility_invalidation_outbox 是 append-only（BEFORE DELETE 触发器禁止删除）。
        # 测试夹具清理需临时旁路触发器：session_replication_role=replica 关闭本会话全部触发器，
        # 删完立即恢复 DEFAULT（仅限本清理会话，不影响他人）。
        await db.execute(sa.text("SET session_replication_role = replica"))
        try:
            for stmt in (
                "DELETE FROM workpaper_delegation_history WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM wp_access_security_outbox WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM wp_visibility_invalidation_outbox WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM wp_visibility_policy_epoch WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM procedure_row_task_history WHERE task_id IN "
                "(SELECT id FROM procedure_row_tasks WHERE project_id = ANY(CAST(:p AS uuid[])))",
                "DELETE FROM procedure_row_tasks WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM procedure_instances WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM working_paper WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM project_assignments WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM project_users WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM wp_index WHERE project_id = ANY(CAST(:p AS uuid[]))",
                "DELETE FROM projects WHERE id = ANY(CAST(:p AS uuid[]))",
            ):
                await db.execute(sa.text(stmt), {"p": pset})
        finally:
            await db.execute(sa.text("SET session_replication_role = DEFAULT"))
    if uids:
        uset = [str(x) for x in uids]
        # 浏览器打开底稿编辑器会为 holder 建 editing_locks（FK → users）；清理。
        await db.execute(
            sa.text("DELETE FROM editing_locks WHERE holder_id = ANY(CAST(:u AS uuid[]))"),
            {"u": uset},
        )
        # 删 staff（project_assignments/procedure_row_tasks 已随项目清理）。
        await db.execute(
            sa.text("DELETE FROM staff_members WHERE user_id = ANY(CAST(:u AS uuid[]))"),
            {"u": uset},
        )
        # 注意：**不删除 T6 users** —— users 被 logs/notifications 等多表 append-only 引用，
        # 逐一 FK 清理不可行且无必要。改为 seed 时 upsert 复用用户（user_id 跨运行稳定）。
    await db.commit()


async def cleanup():
    _load_all_models()
    from app.core.database import async_session
    async with async_session() as db:
        await _cleanup(db)
    print("[T6-SEED] cleanup 完成（已删除全部 T6 夹具）")


async def revoke_lead():
    """撤销 lead 对主编底稿的委派 + 同事务递增 policy epoch（供 ≤1s 撤权收敛浏览器验收）。"""
    _load_all_models()
    from app.core.database import async_session
    from app.services.wp_visibility.delegation_transaction import DelegationTransactionService

    if not _FIXTURE.exists():
        raise SystemExit("[T6-SEED] fixture 不存在，先运行播种")
    fx = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    pid = uuid.UUID(fx["project_id"])
    lead_wp_id = uuid.UUID(fx["wp"]["lead"]["wp_id"])
    admin_uid = uuid.UUID(fx["roles"]["admin"]["user_id"])
    async with async_session() as db:
        await db.execute(
            sa.text("UPDATE working_paper SET assigned_to = NULL WHERE id = :w"),
            {"w": str(lead_wp_id)},
        )
        svc = DelegationTransactionService(db)
        await svc.bump_policy_epoch(pid, "delegation", actor_user_id=admin_uid)
        await db.commit()
    print("[T6-SEED] revoke-lead 完成（lead 主编已清空 + policy epoch 递增）")


async def seed():
    _load_all_models()
    from app.core.database import async_session
    from app.core.security import hash_password
    from app.models.base import ProjectUserRole, UserRole
    from app.models.core import Project, ProjectUser, User
    from app.models.staff_models import ProjectAssignment, StaffMember
    from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
    from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask
    from app.models.wp_visibility_models import WorkpaperDelegationHistory

    _HASH64 = "0" * 64

    async with async_session() as db:
        # 幂等：先清理
        await _cleanup(db)

        # admin（复用系统内置）
        admin = (await db.execute(sa.select(User).where(User.username == "admin"))).scalar_one_or_none()
        if admin is None:
            raise SystemExit("[T6-SEED] 系统内置 admin 用户不存在，无法播种")

        # 项目
        proj = Project(name=PROJECT_NAME, client_name="T6测试客户")
        other = Project(name=OTHER_PROJECT_NAME, client_name="T6其它客户")
        db.add_all([proj, other])
        await db.flush()

        # 角色用户（upsert by username —— 不删除用户，跨运行稳定 user_id）
        users: dict[str, User] = {}
        staff: dict[str, StaffMember] = {}
        for key, (username, role) in ROLE_USERS.items():
            u = (await db.execute(sa.select(User).where(User.username == username))).scalar_one_or_none()
            if u is None:
                u = User(
                    username=username, email=f"{username}@t6.local",
                    hashed_password=hash_password(PW), role=UserRole(role), is_active=True,
                )
                db.add(u)
                await db.flush()
            else:
                u.hashed_password = hash_password(PW)
                u.role = UserRole(role)
                u.is_active = True
                await db.flush()
            users[key] = u
        # staff for supervisor/assignee/reviewer
        for key in ("supervisor", "assignee", "reviewer"):
            sm = StaffMember(name=f"T6-{key}", user_id=users[key].id, source="custom", role_level="auditor")
            db.add(sm)
            await db.flush()
            staff[key] = sm

        # project_users（scope D）
        for key in ("supervisor", "lead", "assignee", "reviewer", "history_lead", "history_row", "restricted"):
            db.add(ProjectUser(
                project_id=proj.id, user_id=users[key].id,
                role=ProjectUserRole("auditor"), scope_cycles="D",
            ))
        # supervisor assignment(manager) → supervisor_scope grant
        db.add(ProjectAssignment(project_id=proj.id, staff_id=staff["supervisor"].id, role="manager"))
        await db.flush()

        # wp_index + working_paper
        def _mk_wi(project, code, name, cycle):
            wi = WpIndex(project_id=project.id, wp_code=code, wp_name=name, audit_cycle=cycle)
            db.add(wi)
            return wi

        wiD_lead = _mk_wi(proj, "D2-1", WP_NAMES["lead"], "D")
        wiD_und = _mk_wi(proj, "D3-1", WP_NAMES["undelegated"], "D")
        wiD_row = _mk_wi(proj, "D4-1", WP_NAMES["row"], "D")
        wiK = _mk_wi(proj, "K1-1", WP_NAMES["external"], "K")
        wiOther = _mk_wi(other, "D2-1", WP_NAMES["other"], "D")
        await db.flush()

        def _mk_wp(project, wi):
            wp = WorkingPaper(
                project_id=project.id, wp_index_id=wi.id,
                file_path=f"/tmp/t6_{uuid.uuid4().hex[:8]}.xlsx",
                source_type=WpSourceType.template, file_version=1,
            )
            db.add(wp)
            return wp

        wpD_lead = _mk_wp(proj, wiD_lead)
        wpD_und = _mk_wp(proj, wiD_und)
        wpD_row = _mk_wp(proj, wiD_row)
        wpK = _mk_wp(proj, wiK)
        wpOther = _mk_wp(other, wiOther)
        await db.flush()

        # lead 主编：scope 内 wpD_lead + scope 外 wpK（scope-external-delegated）
        wpD_lead.assigned_to = users["lead"].id
        wpK.assigned_to = users["lead"].id

        # assignee row 任务：scope 内 wpD_row sheet D4A + scope 外 wpK sheet K1A
        defD = ProcedureRowDefinition(
            definition_key=f"t6-def-d4a-{uuid.uuid4().hex[:8]}", template_code="D4",
            template_revision_hash=_HASH64, sheet_key="D4A", procedure_text="执行审计程序",
        )
        defK = ProcedureRowDefinition(
            definition_key=f"t6-def-k1a-{uuid.uuid4().hex[:8]}", template_code="K1",
            template_revision_hash=_HASH64, sheet_key="K1A", procedure_text="执行审计程序",
        )
        defRev = ProcedureRowDefinition(
            definition_key=f"t6-def-d4a-rev-{uuid.uuid4().hex[:8]}", template_code="D4",
            template_revision_hash=_HASH64, sheet_key="D4A", procedure_text="复核审计程序",
        )
        db.add_all([defD, defK, defRev])
        await db.flush()

        db.add(ProcedureRowTask(
            project_id=proj.id, wp_index_id=wiD_row.id, wp_id=wpD_row.id,
            definition_key=defD.definition_key, sheet_key="D4A",
            definition_revision_hash=_HASH64, audit_cycle_snapshot="D",
            assignee_staff_id=staff["assignee"].id,
        ))
        db.add(ProcedureRowTask(
            project_id=proj.id, wp_index_id=wiK.id, wp_id=wpK.id,
            definition_key=defK.definition_key, sheet_key="K1A",
            definition_revision_hash=_HASH64, audit_cycle_snapshot="K",
            assignee_staff_id=staff["assignee"].id,
        ))
        db.add(ProcedureRowTask(
            project_id=proj.id, wp_index_id=wiD_row.id, wp_id=wpD_row.id,
            definition_key=defRev.definition_key, sheet_key="D4A",
            definition_revision_hash=_HASH64, audit_cycle_snapshot="D",
            reviewer_staff_id=staff["reviewer"].id,
        ))

        # history lead：wiD_lead lead 历史快照（scope 内）+ wiK lead 历史（scope 外）
        db.add(WorkpaperDelegationHistory(
            project_id=proj.id, wp_index_id=wiD_lead.id, layer="lead", target_role="lead",
            action="clear", new_user_id=users["history_lead"].id, actor_user_id=admin.id,
        ))
        db.add(WorkpaperDelegationHistory(
            project_id=proj.id, wp_index_id=wiK.id, layer="lead", target_role="lead",
            action="clear", new_user_id=users["history_lead"].id, actor_user_id=admin.id,
        ))
        # history row：wiD_row assignee 历史快照 sheet D4A
        db.add(WorkpaperDelegationHistory(
            project_id=proj.id, wp_index_id=wiD_row.id, layer="row", target_role="assignee",
            action="clear", sheet_key="D4A", new_user_id=users["history_row"].id, actor_user_id=admin.id,
        ))

        await db.commit()

        # ── fixture ──
        def wp_rec(wi, wp):
            return {"wp_id": str(wp.id), "wp_index_id": str(wi.id), "wp_code": wi.wp_code, "wp_name": wi.wp_name}

        roles_out = {"admin": {"username": "admin", "password": "admin123", "user_id": str(admin.id)}}
        for key, u in users.items():
            roles_out[key] = {"username": u.username, "password": PW, "user_id": str(u.id)}

        # 每角色浏览器深链探针（wp_key → allow/deny）——覆盖 scope-internal-not-delegated
        # 与 scope-external-delegated 双拒绝不变量。
        probes = {
            # admin 是全局 admin：经 /render-config（路径无 project）反查资源真实 project 后放行，
            # 故 lead/undelegated/external 均 allow；跨项目拒绝仅在显式传入不匹配 project_id 时触发，
            # 由 gate 级测试覆盖（浏览器 render-config 不传 project，不在此断言）。
            "admin": [["lead", "allow"], ["undelegated", "allow"], ["external", "allow"]],
            "supervisor": [["undelegated", "allow"], ["external", "deny"]],
            "lead": [["lead", "allow"], ["undelegated", "deny"], ["external", "deny"]],
            "assignee": [["row", "allow"], ["undelegated", "deny"], ["external", "deny"]],
            "reviewer": [["row", "allow"], ["undelegated", "deny"], ["external", "deny"]],
            "history_lead": [["lead", "allow"], ["undelegated", "deny"], ["external", "deny"]],
            "history_row": [["row", "allow"], ["undelegated", "deny"], ["external", "deny"]],
            "restricted": [["lead", "deny"], ["undelegated", "deny"], ["external", "deny"]],
        }

        fixture = {
            "project_id": str(proj.id),
            "other_project_id": str(other.id),
            "wp": {
                "lead": wp_rec(wiD_lead, wpD_lead),
                "undelegated": wp_rec(wiD_und, wpD_und),
                "row": wp_rec(wiD_row, wpD_row),
                "external": wp_rec(wiK, wpK),
                "other": wp_rec(wiOther, wpOther),
            },
            "roles": roles_out,
            "probes": probes,
            "editor_url_template": "/projects/{project_id}/workpapers/{wp_id}/edit",
            "render_config_path_template": "/api/workpapers/{wp_id}/render-config",
            "external_not_found_message": "资源不存在或不可访问",
        }
        _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        _FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[T6-SEED] 播种完成 → {_FIXTURE}")
        print(f"[T6-SEED] project={proj.id} roles={list(roles_out.keys())}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--revoke-lead", action="store_true")
    args = ap.parse_args()
    if args.cleanup:
        asyncio.run(cleanup())
    elif args.revoke_lead:
        asyncio.run(revoke_lead())
    else:
        asyncio.run(seed())


if __name__ == "__main__":
    main()
