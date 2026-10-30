"""只读 UAT 专用账号工具（spec trim-generation-plan-followup-optimizations R5.1 / R5.2）。

默认只报告、不写库。写入必须同时给 ``--apply`` 与 ``--confirm-project-id``（与 ``--project-id`` 逐字一致）。

单事务，只写两张表：

- ``users``：创建 / 复用 ``role=readonly`` 的专用账号（复用时校验密码、停用的重新启用；不改角色，不碰别人的账号）；
- ``project_users``：为该账号在目标项目建 ``role=readonly``、``permission_level=readonly`` 的成员行；
  ``--scope-cycles`` 写该行的 ``scope_cycles``（只读成员按它看底稿；不给则不改，新建行为空 = 看不到底稿）。

拒绝（整份不写）：项目不存在 / 已删除 / 已归档；同名账号不是 readonly、已删除或密码不符；该账号在本项目已有
非 readonly 的成员行（权限高于只读）；确认项目号不一致；需要密码却没有。

``--revoke``：软删这条只读成员行并停用该专用账号（账号若还在别的项目有成员行，回执里列出）。

不建人员档案（staff_members）、团队分配（project_assignments），不碰业务表。密码只从环境变量
``GT_READONLY_UAT_PASSWORD`` 或交互输入读取，不收命令行参数、不打印。共享库上执行须用户放行。

用法（backend 目录）::

  python scripts/e2e/provision_readonly_uat_user.py --project-id <uuid> --username <name>
  python scripts/e2e/provision_readonly_uat_user.py --project-id <uuid> --username <name> --scope-cycles D,E \
      --apply --confirm-project-id <uuid>
  python scripts/e2e/provision_readonly_uat_user.py --project-id <uuid> --username <name> --revoke \
      --apply --confirm-project-id <uuid>

退出码：0 已执行 / 只报告且可执行；2 拒绝；3 参数错误。
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys
import uuid

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402

PASSWORD_ENV = "GT_READONLY_UAT_PASSWORD"
MIN_PASSWORD_LENGTH = 12
EMAIL_DOMAIN = "readonly-uat.invalid"  # RFC 2606 保留域名，不会真的发信
READONLY = "readonly"
#: 团队分配可勾选的循环（与 wp_visibility.effective_scope.STANDARD_CYCLES 同一组，测试对拍）
STANDARD_CYCLES = frozenset("ABCDEFGHIJKLMN") | {"S"}
#: 本工具只写这两张表（测试按语句捕获逐条核对）
WRITABLE_TABLES = frozenset({"users", "project_users"})

EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 2, 3


@dataclass(frozen=True)
class ProjectFacts:
    id: uuid.UUID
    name: str
    status: str
    is_deleted: bool


@dataclass(frozen=True)
class UserFacts:
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    is_deleted: bool
    hashed_password: str


@dataclass(frozen=True)
class MemberFacts:
    id: uuid.UUID
    role: str
    permission_level: str
    scope_cycles: frozenset[str]


@dataclass(frozen=True)
class Snapshot:
    project: ProjectFacts | None
    user: UserFacts | None
    members: tuple[MemberFacts, ...]  # 本账号在本项目的未删除成员行
    other_projects: tuple[str, ...]  # 本账号在其他项目的未删除成员行（项目名）


@dataclass(frozen=True)
class Plan:
    mode: str  # provision / revoke
    refusals: tuple[str, ...]
    actions: tuple[str, ...]  # create_user / reactivate_user / create_member / update_scope / revoke_member / deactivate_user
    scope: frozenset[str] | None  # None = 不改

    @property
    def allowed(self) -> bool:
        return not self.refusals


def parse_scope(raw: str | None) -> frozenset[str] | None:
    """``--scope-cycles``：None ⇒ 不改；``ALL`` ⇒ 全部标准循环；否则逗号分隔的循环代号（未登记即 ValueError）。"""
    if raw is None:
        return None
    text = raw.strip().upper()
    if text == "ALL":
        return STANDARD_CYCLES
    items = frozenset(part.strip() for part in text.split(",") if part.strip())
    unknown = sorted(items - STANDARD_CYCLES)
    if unknown:
        raise ValueError(f"未登记的循环代号：{', '.join(unknown)}（只认 A~N、S 或 ALL）")
    return items


def format_scope(scope: frozenset[str] | None) -> str | None:
    return ",".join(sorted(scope)) if scope else None


def _parse_cycles(raw: str | None) -> frozenset[str]:
    return frozenset(part.strip().upper() for part in (raw or "").split(",") if part.strip())


def decide(snapshot: Snapshot, *, mode: str, scope: frozenset[str] | None, password_ok: bool | None) -> Plan:
    """纯函数：按快照决定动作或拒绝。``password_ok``：None = 没有可校验的密码（只报告时）。"""
    refusals: list[str] = []
    actions: list[str] = []
    project, user = snapshot.project, snapshot.user
    if project is None:
        refusals.append("项目不存在")
    if mode == "revoke":
        if user is None:
            refusals.append("账号不存在")
        elif user.role != READONLY:
            refusals.append(f"账号角色是 {user.role}，不是只读专用账号（工具不停用）")
        foreign = [m for m in snapshot.members if (m.role, m.permission_level) != (READONLY, READONLY)]
        if foreign:
            refusals.append("本项目成员行不是工具建的只读行（{}），不处理".format(
                "、".join(f"{m.role}/{m.permission_level}" for m in foreign)))
        if not refusals:
            if snapshot.members:
                actions.append("revoke_member")
            if user is not None and user.is_active:
                actions.append("deactivate_user")
        return Plan(mode, tuple(refusals), tuple(actions), None)

    if project is not None:
        if project.is_deleted:
            refusals.append("项目已删除")
        if project.status == "archived":
            refusals.append("项目已归档")
    if user is None:
        actions.append("create_user")
    else:
        if user.is_deleted:
            refusals.append("同名账号已删除，需管理员处理")
        if user.role != READONLY:
            refusals.append(f"同名账号角色是 {user.role}，不是只读专用账号（工具不改角色）")
        if password_ok is False:
            refusals.append("同名只读账号密码不符（工具不重置密码）")
        if not user.is_active:
            actions.append("reactivate_user")
    if len(snapshot.members) > 1:
        refusals.append(f"本项目有 {len(snapshot.members)} 条未删除成员行（数据异常，需人工处理）")
    elif snapshot.members:
        member = snapshot.members[0]
        if (member.role, member.permission_level) != (READONLY, READONLY):
            refusals.append(f"本项目已有 {member.role}/{member.permission_level} 成员行，高于只读（工具不降级、不升级）")
        elif scope is not None and scope != member.scope_cycles:
            actions.append("update_scope")
    else:
        actions.append("create_member")
    return Plan(mode, tuple(refusals), tuple(actions) if not refusals else (), scope)


async def load_snapshot(db, project_id: uuid.UUID, username: str, *, lock: bool) -> Snapshot:
    """读快照；``lock`` 时锁住账号行与成员行（同一事务内决定后再写，期间不被并发修改）。"""
    for_update = " FOR UPDATE" if lock else ""
    prow = (await db.execute(sa.text(
        "SELECT id, name, status::text AS status, is_deleted FROM projects WHERE id = :pid"), {"pid": project_id})).first()
    project = ProjectFacts(prow.id, prow.name, prow.status, bool(prow.is_deleted)) if prow else None
    urow = (await db.execute(sa.text(
        "SELECT id, username, role::text AS role, is_active, is_deleted, hashed_password FROM users "
        f"WHERE username = :username{for_update}"), {"username": username})).first()
    user = UserFacts(urow.id, urow.username, urow.role, bool(urow.is_active), bool(urow.is_deleted),
                     urow.hashed_password) if urow else None
    members: tuple[MemberFacts, ...] = ()
    others: tuple[str, ...] = ()
    if user is not None:
        rows = (await db.execute(sa.text(
            "SELECT id, role::text AS role, permission_level::text AS permission_level, scope_cycles FROM project_users "
            f"WHERE project_id = :pid AND user_id = :uid AND is_deleted = false ORDER BY id{for_update}"),
            {"pid": project_id, "uid": user.id})).all()
        members = tuple(MemberFacts(r.id, r.role, r.permission_level, _parse_cycles(r.scope_cycles)) for r in rows)
        others = tuple(r.name for r in (await db.execute(sa.text(
            "SELECT p.name FROM project_users pu JOIN projects p ON p.id = pu.project_id "
            "WHERE pu.user_id = :uid AND pu.is_deleted = false AND pu.project_id <> :pid ORDER BY p.name"),
            {"pid": project_id, "uid": user.id})).all())
    return Snapshot(project, user, members, others)


async def apply_plan(db, snapshot: Snapshot, plan: Plan, *, username: str, password: str | None,
                     project_id: uuid.UUID) -> dict:
    """在调用方的事务里执行 ``plan``（调用方负责提交 / 回滚）。返回回执（不含密码 / 哈希）。"""
    from app.core.security import hash_password

    if not plan.allowed:
        raise RuntimeError("拒绝的计划不能执行")
    now = datetime.now(timezone.utc)
    user_id = snapshot.user.id if snapshot.user else None
    receipt: dict = {"mode": plan.mode, "project_id": str(project_id), "username": username, "done": []}
    for action in plan.actions:
        if action == "create_user":
            if not password:
                raise RuntimeError("创建账号需要密码")
            user_id = uuid.uuid4()
            await db.execute(sa.text(
                "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted, created_at, updated_at) "
                "VALUES (:id, :username, :email, :hashed, 'readonly', true, false, :now, :now)"),
                {"id": user_id, "username": username, "email": f"{username}@{EMAIL_DOMAIN}",
                 "hashed": hash_password(password), "now": now})
        elif action == "reactivate_user":
            await db.execute(sa.text(
                "UPDATE users SET is_active = true, updated_at = :now WHERE id = :id AND role = 'readonly'"),
                {"id": user_id, "now": now})
        elif action == "create_member":
            await db.execute(sa.text(
                "INSERT INTO project_users (id, project_id, user_id, role, permission_level, scope_cycles, is_deleted, "
                "created_at, updated_at) VALUES (:id, :pid, :uid, 'readonly', 'readonly', :scope, false, :now, :now)"),
                {"id": uuid.uuid4(), "pid": project_id, "uid": user_id, "scope": format_scope(plan.scope), "now": now})
        elif action == "update_scope":
            await db.execute(sa.text(
                "UPDATE project_users SET scope_cycles = :scope, updated_at = :now WHERE id = :id "
                "AND role = 'readonly' AND permission_level = 'readonly' AND is_deleted = false"),
                {"id": snapshot.members[0].id, "scope": format_scope(plan.scope), "now": now})
        elif action == "revoke_member":
            for member in snapshot.members:
                await db.execute(sa.text(
                    "UPDATE project_users SET is_deleted = true, deleted_at = :now, updated_at = :now WHERE id = :id "
                    "AND role = 'readonly' AND permission_level = 'readonly' AND is_deleted = false"),
                    {"id": member.id, "now": now})
        elif action == "deactivate_user":
            await db.execute(sa.text(
                "UPDATE users SET is_active = false, updated_at = :now WHERE id = :id AND role = 'readonly'"),
                {"id": user_id, "now": now})
        else:  # pragma: no cover - decide 只产出上面几种
            raise RuntimeError(f"未知动作 {action}")
        receipt["done"].append(action)
    receipt["user_id"] = str(user_id) if user_id else None
    receipt["scope_cycles"] = format_scope(plan.scope) if plan.scope is not None else None
    receipt["other_projects_still_member"] = list(snapshot.other_projects)
    return receipt


def check_password(snapshot: Snapshot, password: str | None) -> bool | None:
    """只对同名只读账号校验（别的角色本来就拒绝，不去碰它的哈希）；哈希损坏按不符处理，工具不崩。"""
    from app.core.security import verify_password

    if snapshot.user is None or not password or snapshot.user.role != READONLY:
        return None
    try:
        return bool(verify_password(password, snapshot.user.hashed_password))
    except ValueError:
        return False


def read_password(*, interactive: bool) -> str | None:
    password = os.environ.get(PASSWORD_ENV)
    if not password and interactive and sys.stdin.isatty():
        password = getpass.getpass("只读 UAT 账号密码（不回显）：")
    return password or None


async def run(project_id: uuid.UUID, username: str, *, mode: str, scope: frozenset[str] | None, apply: bool,
              password: str | None, engine=None) -> tuple[int, dict]:
    """执行一次（只报告或写入）。``engine`` 供测试注入；默认用平台配置的数据库。"""
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    owns_engine = engine is None
    if owns_engine:
        connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=connect_args)
    try:
        async with engine.connect() as conn:
            async with conn.begin() as transaction:
                if not apply:
                    await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                snapshot = await load_snapshot(conn, project_id, username, lock=apply)
                if mode == "provision" and apply and password is None:
                    report = _report(snapshot, Plan(mode, ("需要密码：设置环境变量 GT_READONLY_UAT_PASSWORD 或交互输入",), (),
                                                    scope), apply)
                    await transaction.rollback()
                    return EXIT_REFUSED, report
                password_ok = check_password(snapshot, password) if mode == "provision" else None
                plan = decide(snapshot, mode=mode, scope=scope, password_ok=password_ok)
                report = _report(snapshot, plan, apply)
                if not plan.allowed:
                    await transaction.rollback()
                    return EXIT_REFUSED, report
                if not apply:
                    await transaction.rollback()
                    return EXIT_OK, report
                try:
                    report["receipt"] = await apply_plan(conn, snapshot, plan, username=username, password=password,
                                                         project_id=project_id)
                except sa.exc.IntegrityError as exc:
                    await transaction.rollback()
                    report["planned_actions"] = []
                    report["refusals"] = [
                        "写入冲突（并发创建同名账号 / 邮箱或成员行），已整体回滚，请重跑：" + type(exc.orig).__name__]
                    return EXIT_REFUSED, report
                await transaction.commit()
                return EXIT_OK, report
    finally:
        if owns_engine:
            await engine.dispose()


def _report(snapshot: Snapshot, plan: Plan, apply: bool) -> dict:
    project = snapshot.project
    user = snapshot.user
    return {
        "apply": apply,
        "mode": plan.mode,
        "project": None if project is None else {
            "id": str(project.id), "name": project.name, "status": project.status, "is_deleted": project.is_deleted},
        "user": None if user is None else {
            "id": str(user.id), "username": user.username, "role": user.role, "is_active": user.is_active,
            "is_deleted": user.is_deleted},
        "members": [{"role": m.role, "permission_level": m.permission_level,
                     "scope_cycles": format_scope(m.scope_cycles)} for m in snapshot.members],
        "other_projects": list(snapshot.other_projects),
        "planned_actions": list(plan.actions),
        "refusals": list(plan.refusals),
        "scope_cycles": format_scope(plan.scope) if plan.scope is not None else "（不改）",
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读 UAT 专用账号（默认只报告）")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--scope-cycles", default=None, help="只读成员可见的循环，逗号分隔或 ALL；不给则不改")
    parser.add_argument("--revoke", action="store_true", help="软删本项目只读成员行并停用该专用账号")
    parser.add_argument("--apply", action="store_true", help="真的写库（须同时给 --confirm-project-id）")
    parser.add_argument("--confirm-project-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    username = args.username
    try:
        project_id = uuid.UUID(args.project_id.strip())
        if not username or username != username.strip() or len(username) > 150 or any(c.isspace() for c in username):
            raise ValueError("用户名不能为空、不能含空白，长度不超过 150")
        scope = parse_scope(args.scope_cycles)
        if args.revoke and scope is not None:
            raise ValueError("--revoke 不接受 --scope-cycles")
        if args.apply and (args.confirm_project_id or "").strip() != args.project_id.strip():
            raise ValueError("--apply 需要 --confirm-project-id，且与 --project-id 逐字一致")
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    mode = "revoke" if args.revoke else "provision"
    password = None
    if mode == "provision":
        password = read_password(interactive=args.apply)
        if password is not None and len(password) < MIN_PASSWORD_LENGTH:
            print(f"参数错误：密码至少 {MIN_PASSWORD_LENGTH} 位", file=sys.stderr)
            return EXIT_USAGE
    code, report = asyncio.run(run(project_id, username, mode=mode, scope=scope, apply=args.apply, password=password))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
