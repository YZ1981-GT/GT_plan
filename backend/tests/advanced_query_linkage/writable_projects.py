"""在回滚事务里自建【测试】项目（**不经 ORM**）。

## 为什么不能用 `session.add(Project(...))`

ORM 模型声明的列可以**领先于**共享库的实际结构。2026-11-01 实测：`Project` 已声明 `amount_unit`
（远端迁移 V250 当时尚未落共享库）⇒ ORM 的 INSERT 把它写进列清单，PG 直接
`UndefinedColumnError: column projects.amount_unit does not exist`。
这与前十五节那 5 处 500（`db.get(Project, ...)` 全列 **读** 投影）是同一个机理的**写**侧形态：
只要 ORM 比库新一列，所有经 ORM 读写 `projects` 的测试夹具就全部报废。

2026-11-03 21:48（北京时间）共享库已由他人迁到 V251，`amount_unit` 现已存在（V236 / V248 / V249 仍缺，
不在 `projects` 上）。具体缺哪一列会变，「ORM 可领先于共享库」这个机理不会变 ⇒ 夹具继续只写显式列。

所以这里用**显式列**的裸 SQL 插入，只写「NOT NULL 且无默认值」的那几列加调用方指定的几列：
`id` / `name` / `client_name` / `status` / `version`（现算这 5 列是 NOT NULL 且无 DB 默认值），
其余列交给数据库默认值。这样 ORM 再加多少列都与夹具无关。

所有写入都在 `pg_rollback_session` 的回滚事务里，结束整体回滚；名称一律带【测试】前缀。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

#: 自建项目名称前缀（共享库里凡以此开头的行都是测试残留，便于事后对账）
TEST_NAME_PREFIX = "【测试】aql"

_INSERT_PROJECT = sa.text(
    "INSERT INTO projects (id, name, client_name, status, version, audit_year, report_scope, template_type) "
    "VALUES (:id, :name, :client_name, CAST(:status AS projectstatus), 1, :audit_year, :report_scope, :template_type)"
)


async def insert_test_project(
    session: AsyncSession,
    *,
    name_suffix: str,
    audit_year: int | None = 2025,
    report_scope: str | None = "standalone",
    template_type: str | None = None,
    status: str = "created",
) -> tuple[uuid.UUID, str]:
    """插入一个【测试】项目，返回 ``(id, name)``。

    `name_suffix` 只是人读的后缀；名称自带 `TEST_NAME_PREFIX`，并附一段随机值避免并发用例撞唯一约束。
    """
    pid = uuid.uuid4()
    name = f"{TEST_NAME_PREFIX} {name_suffix} {pid.hex[:8]}"
    await session.execute(
        _INSERT_PROJECT,
        {
            "id": pid,
            "name": name,
            "client_name": name,
            "status": status,
            "audit_year": audit_year,
            "report_scope": report_scope,
            "template_type": template_type,
        },
    )
    return pid, name


async def project_columns(session: AsyncSession) -> set[str]:
    """共享库里 `projects` 实际存在的列（用于断言「夹具没有依赖尚未落库的列」）。"""
    rows = await session.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'projects'"
        )
    )
    return {r[0] for r in rows}


async def table_columns(session: AsyncSession, table: str) -> list[str]:
    """共享库里某表的实际列（排除生成列），按物理顺序。复制行时用它而不是 ORM 列清单。"""
    rows = await session.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = :t AND is_generated = 'NEVER' ORDER BY ordinal_position"
        ),
        {"t": table},
    )
    return [r[0] for r in rows]


async def copy_project_rows(
    session: AsyncSession,
    table: str,
    *,
    target: uuid.UUID,
    source: uuid.UUID,
    year: int | None = None,
    where: str = "TRUE",
) -> int:
    """把来源项目（只读）的行复制到自建【测试】项目：新 id、新项目，其余列原值。

    ``table`` / ``where`` 只取用例里的固定字面量（不接收外部输入）。列清单按 information_schema 现读，
    来源表再加列也不会失配；``year`` 给了就只复制该年度，且要求表上确有 ``year`` 列。
    """
    cols = await table_columns(session, table)
    exprs = ["gen_random_uuid()" if c == "id" else ":target" if c == "project_id" else c for c in cols]
    year_clause = ""
    params: dict = {"target": target, "source": source}
    if year is not None:
        if "year" not in cols:
            raise AssertionError(f"{table} 没有 year 列，不能按年度复制")
        year_clause = " AND year = :year"
        params["year"] = year
    deleted_clause = " AND NOT is_deleted" if "is_deleted" in cols else ""
    result = await session.execute(
        sa.text(
            f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(exprs)} FROM {table} "
            f"WHERE project_id = :source{year_clause}{deleted_clause} AND ({where})"
        ),
        params,
    )
    return int(result.rowcount or 0)


async def insert_member(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    system_role: str,
    member_role: str | None,
    permission: str = "edit",
    assignment_role: str | None = None,
    assigned_cycles: list[str] | None = None,
):
    """自建一个成员身份（用户 + 人员记录 + 可选成员行 + 可选委派），返回 ORM ``User``。

    取代 builder 用例里按用户名读的真实账号（e2e_manager、u_011abb97dd2d4101 —— 2026-11-03 现算
    共享库里都已不存在）。四张表的 ORM 列与共享库一致（现算无漂移），这里直接用 ORM。

    - ``member_role`` = None ⇒ 不建成员行（只经委派访问）；
    - ``assignment_role`` = None ⇒ 不建委派；``assigned_cycles`` 只在建委派时生效。
    """
    from datetime import datetime, timezone

    from app.models.base import UserRole
    from app.models.core import PermissionLevel, ProjectUser, ProjectUserRole, User
    from app.models.staff_models import ProjectAssignment, StaffMember

    tag = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"aql-member-{tag}",
        email=f"aql-member-{tag}@test.invalid",
        hashed_password="x",
        role=UserRole(system_role),
        is_active=True,
    )
    session.add(user)
    await session.flush()
    staff = StaffMember(user_id=user.id, name=f"【测试】aql 成员 {tag}")
    session.add(staff)
    await session.flush()
    if member_role is not None:
        session.add(
            ProjectUser(
                project_id=project_id,
                user_id=user.id,
                role=ProjectUserRole(member_role),
                permission_level=PermissionLevel(permission),
            )
        )
    if assignment_role is not None:
        session.add(
            ProjectAssignment(
                project_id=project_id,
                staff_id=staff.id,
                role=assignment_role,
                assigned_cycles=list(assigned_cycles or []),
                assigned_at=datetime.now(timezone.utc),
            )
        )
    await session.flush()
    return user
