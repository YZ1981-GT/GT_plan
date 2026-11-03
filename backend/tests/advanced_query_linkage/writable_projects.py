"""在回滚事务里自建【测试】项目（**不经 ORM**）。

## 为什么不能用 `session.add(Project(...))`

ORM 模型声明的列可以**领先于**共享库的实际结构。现算：`Project` 已声明 `amount_unit`
（远端迁移 V250 尚未落共享库）⇒ ORM 的 INSERT 把它写进列清单，PG 直接
`UndefinedColumnError: column projects.amount_unit does not exist`。
这与前十五节那 5 处 500（`db.get(Project, ...)` 全列 **读** 投影）是同一个机理的**写**侧形态：
只要 ORM 比库新一列，所有经 ORM 读写 `projects` 的测试夹具就全部报废。

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
