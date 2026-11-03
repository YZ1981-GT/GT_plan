"""只读 UAT 账号工具的真实 PostgreSQL 写库路径（spec trim-generation-plan-followup-optimizations R5.1 / R5.2）。

在随机临时 schema 里跑：``users`` / ``project_users`` / ``staff_members`` / ``project_assignments`` 用
``LIKE public.<表> INCLUDING ALL`` 照搬共享库的列、默认值、唯一索引（含成员行的部分唯一索引）与枚举类型；
``projects`` 从共享库只读复制一行再改成【测试】项目。所有执行的 SQL 经引擎事件逐条捕获：

- 只报告：零写入语句（且事务只读）；
- 写入只落 ``users`` / ``project_users`` 两张表，不碰人员档案 / 团队分配；重跑幂等；
- 建出来的账号对本项目 readonly 校验通过、review / edit 403；撤销后 readonly 也 403、账号停用；撤销后可重建；
- 拒绝（同名非只读账号 / 密码不符 / 成员行高于只读 / 项目归档）零写入；写到一半失败整体回滚；
- 两个会话并发创建同名账号：一个成功，另一个回滚并拒绝，最终只有一个账号一条成员行。
所有建表 / 写入都在临时 schema 内，finally 删除；共享 public 只读。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from tests.pg_temp_schema import temporary_schema  # noqa: E402
from tests.test_provision_readonly_uat_user import load_tool  # noqa: E402

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]

tool = load_tool()
PASSWORD = "Uat-Readonly-2026!"
USERNAME = "uat_readonly_probe"
_WRITE = ("INSERT", "UPDATE", "DELETE")


class _Capture:
    """引擎级语句捕获（被测函数下一层）；``fail_on`` 命中即抛错，模拟写到一半失败。"""

    def __init__(self, engine):
        self.statements: list[str] = []
        self.fail_on: str | None = None
        self._engine = engine.sync_engine
        event.listen(self._engine, "before_cursor_execute", self._hook)

    def _hook(self, _conn, _cursor, statement, _params, _context, _executemany):
        text = " ".join(statement.split())
        self.statements.append(text)
        if self.fail_on and text.upper().startswith(self.fail_on):
            raise RuntimeError("注入故障：" + self.fail_on)

    def writes(self) -> list[str]:
        return [s for s in self.statements if s.upper().startswith(_WRITE)]

    def written_tables(self) -> set[str]:
        tables = set()
        for s in self.writes():
            words = s.split()
            tables.add((words[2] if words[0].upper() in ("INSERT", "DELETE") else words[1]).lower())
        return tables

    def reset(self) -> None:
        self.statements.clear()

    def close(self) -> None:
        event.remove(self._engine, "before_cursor_execute", self._hook)


async def _world(engine, schema: str) -> uuid.UUID:
    pid = uuid.uuid4()
    async with engine.begin() as conn:
        for table in ("users", "project_users", "staff_members", "project_assignments", "projects"):
            await conn.exec_driver_sql(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING ALL)')
        copied = await conn.execute(sa.text(
            f'INSERT INTO "{schema}".projects SELECT * FROM public.projects ORDER BY created_at LIMIT 1'))
        assert copied.rowcount == 1, "共享库没有项目可复制"
        await conn.execute(sa.text(
            "UPDATE projects SET id = :pid, name = '【测试】只读 UAT 工具', client_name = '【测试】只读 UAT 工具', "
            "status = 'execution', is_deleted = false"), {"pid": pid})
    return pid


async def _state(engine, pid: uuid.UUID) -> dict:
    async with engine.connect() as conn:
        users = (await conn.execute(sa.text(
            "SELECT id, username, role::text AS role, is_active, is_deleted, hashed_password, email FROM users "
            "WHERE username = :u"), {"u": USERNAME})).all()
        members = (await conn.execute(sa.text(
            "SELECT role::text AS role, permission_level::text AS level, scope_cycles, is_deleted, deleted_at "
            "FROM project_users WHERE project_id = :pid ORDER BY created_at, id"), {"pid": pid})).all()
        staff = await conn.scalar(sa.text("SELECT count(*) FROM staff_members"))
        assignments = await conn.scalar(sa.text("SELECT count(*) FROM project_assignments"))
    return {"users": users, "members": members, "staff": staff, "assignments": assignments}


async def _authorize(engine, pid: uuid.UUID, level: str) -> int:
    """用平台真实门禁 ``assert_project_permission`` 判这个账号；返回 200 / 403。"""
    from app.deps import assert_project_permission
    from app.models.core import User

    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = (await session.execute(sa.select(User).where(User.username == USERNAME))).scalar_one()
        try:
            await assert_project_permission(session, user, pid, level)
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            await session.rollback()


async def _run(engine, pid, *, mode="provision", scope=None, apply=True, password=PASSWORD):
    return await tool.run(pid, USERNAME, mode=mode, scope=scope, apply=apply, password=password, engine=engine)


async def test_dry_run_apply_idempotent_permissions_revoke_and_recreate():
    async with temporary_schema("tgfo_uat") as (engine, schema):
        pid = await _world(engine, schema)
        capture = _Capture(engine)
        try:
            code, report = await _run(engine, pid, scope=frozenset({"D", "E"}), apply=False, password=None)
            assert code == tool.EXIT_OK
            assert report["planned_actions"] == ["create_user", "create_member"]
            assert capture.writes() == [], "只报告不得有任何写入语句"
            assert any("READ ONLY" in s.upper() for s in capture.statements)
            assert (await _state(engine, pid))["users"] == []

            capture.reset()
            code, report = await _run(engine, pid, scope=frozenset({"D", "E"}))
            assert code == tool.EXIT_OK, report
            assert report["receipt"]["done"] == ["create_user", "create_member"]
            assert capture.written_tables() == tool.WRITABLE_TABLES == {"users", "project_users"}
            text = str(report)
            assert PASSWORD not in text and "$2b$" not in text, "回执不得含密码或哈希"
            state = await _state(engine, pid)
            (user,) = state["users"]
            assert (user.role, user.is_active, user.is_deleted) == ("readonly", True, False)
            assert user.email == f"{USERNAME}@{tool.EMAIL_DOMAIN}"
            from app.core.security import verify_password
            assert verify_password(PASSWORD, user.hashed_password)
            assert [(m.role, m.level, m.scope_cycles, m.is_deleted) for m in state["members"]] == [
                ("readonly", "readonly", "D,E", False)]
            assert (state["staff"], state["assignments"]) == (0, 0)

            assert [await _authorize(engine, pid, level) for level in ("readonly", "review", "edit")] == [200, 403, 403]

            capture.reset()
            code, report = await _run(engine, pid, scope=frozenset({"D", "E"}))
            assert (code, report["receipt"]["done"]) == (tool.EXIT_OK, []), "重跑幂等"
            assert capture.writes() == []

            capture.reset()
            code, report = await _run(engine, pid, mode="revoke", password=None)
            assert code == tool.EXIT_OK, report
            assert report["receipt"]["done"] == ["revoke_member", "deactivate_user"]
            assert capture.written_tables() <= tool.WRITABLE_TABLES
            state = await _state(engine, pid)
            assert state["users"][0].is_active is False
            assert [(m.is_deleted, m.deleted_at is not None) for m in state["members"]] == [(True, True)]
            assert await _authorize(engine, pid, "readonly") == 403

            code, report = await _run(engine, pid)  # 撤销后重建：重新启用 + 新成员行（旧行保留为已删除）
            assert code == tool.EXIT_OK, report
            assert report["receipt"]["done"] == ["reactivate_user", "create_member"]
            state = await _state(engine, pid)
            assert [(m.is_deleted, m.scope_cycles) for m in state["members"]] == [(True, "D,E"), (False, None)]
            assert await _authorize(engine, pid, "readonly") == 200
        finally:
            capture.close()


@pytest.mark.parametrize("case", ["auditor_user", "bad_password", "higher_member", "archived"])
async def test_refusals_write_nothing(case):
    async with temporary_schema("tgfo_uatr") as (engine, schema):
        pid = await _world(engine, schema)
        if case == "auditor_user":
            async with engine.begin() as conn:
                await conn.execute(sa.text(
                    "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted, created_at, "
                    "updated_at) VALUES (:id, :u, 'x@example.invalid', 'h', 'auditor', true, false, now(), now())"),
                    {"id": uuid.uuid4(), "u": USERNAME})
        elif case in ("bad_password", "higher_member"):
            assert (await _run(engine, pid))[0] == tool.EXIT_OK
            if case == "higher_member":
                async with engine.begin() as conn:
                    await conn.execute(sa.text(
                        "UPDATE project_users SET permission_level = 'edit', role = 'auditor' WHERE project_id = :pid"),
                        {"pid": pid})
        else:
            async with engine.begin() as conn:
                await conn.execute(sa.text("UPDATE projects SET status = 'archived' WHERE id = :pid"), {"pid": pid})
        before = await _state(engine, pid)
        capture = _Capture(engine)
        try:
            password = "Wrong-Password-2026" if case == "bad_password" else PASSWORD
            code, report = await _run(engine, pid, scope=frozenset({"D"}), password=password)
        finally:
            capture.close()
        assert code == tool.EXIT_REFUSED, report
        assert report["refusals"]
        assert capture.writes() == []
        assert await _state(engine, pid) == before


async def test_failure_midway_rolls_back_the_new_account():
    async with temporary_schema("tgfo_uatf") as (engine, schema):
        pid = await _world(engine, schema)
        capture = _Capture(engine)
        capture.fail_on = "INSERT INTO PROJECT_USERS"
        try:
            with pytest.raises(RuntimeError, match="注入故障"):
                await _run(engine, pid)
            assert any(s.upper().startswith("INSERT INTO USERS") for s in capture.statements), "故障前账号已写入"
        finally:
            capture.close()
        state = await _state(engine, pid)
        assert (state["users"], state["members"]) == ([], []), "写到一半失败不得留下账号"


async def test_concurrent_provision_leaves_exactly_one_account():
    async with temporary_schema("tgfo_uatc") as (engine, schema):
        pid = await _world(engine, schema)
        results = await asyncio.gather(_run(engine, pid), _run(engine, pid))
        codes = sorted(code for code, _ in results)
        assert codes in ([tool.EXIT_OK, tool.EXIT_OK], [tool.EXIT_OK, tool.EXIT_REFUSED]), results
        refused = [report for code, report in results if code == tool.EXIT_REFUSED]
        assert all("写入冲突" in report["refusals"][0] for report in refused)
        state = await _state(engine, pid)
        assert len(state["users"]) == 1
        assert [(m.role, m.is_deleted) for m in state["members"]] == [("readonly", False)]
