"""一致性门禁分支夹具（需求 16.3，ADR-FHIC-14 第 4 点）。

每个 BranchSpec.kind 对应一个夹具键：
- missing：无试算表 / 无底稿数据
- unsaved：（保留占位，门禁当前检查无此路径）
- partial：（保留占位）
- not_applicable：底稿是在线表单 / 已裁剪
- exception：注入 SQL 异常

``pg_tx`` 内建【测试】项目，结束回滚。
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession


async def seed_test_project(db: AsyncSession, *, name: str = "【测试】FH-gate") -> tuple[UUID, int]:
    """在 pg_tx 内建一个极简【测试】项目，返回 (project_id, year)。

    用 ORM 模型插入以满足全部 NOT NULL 约束。
    """
    from app.models.core import Project

    pid = uuid4()
    year = 2025
    proj = Project(id=pid, name=name, client_name=name, audit_year=year)
    db.add(proj)
    await db.flush()
    return pid, year


async def seed_tb_rows(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    rows: list[tuple[str, str, Decimal]],
) -> None:
    """插入试算表行。rows = [(standard_account_code, account_category, audited_amount), ...]"""
    from sqlalchemy import text

    for code, cat, amt in rows:
        await db.execute(text("""
            INSERT INTO trial_balance
                (id, project_id, year, standard_account_code, account_category,
                 audited_amount, unadjusted_amount, is_deleted, company_code,
                 account_name)
            VALUES
                (:id, :pid, :yr, :code, :cat, :amt, :amt, false, 'FH', :code)
        """), {
            "id": uuid4(), "pid": project_id, "yr": year,
            "code": code, "cat": cat, "amt": amt,
        })
    await db.flush()


# ---------------------------------------------------------------------------
# 预定义的分支夹具构造器
# ---------------------------------------------------------------------------

async def fixture_missing_no_data(db: AsyncSession) -> tuple[UUID, int]:
    """missing 类：项目有但无试算表数据"""
    return await seed_test_project(db, name="【测试】FH-gate-missing")


async def fixture_missing_unknown_category(db: AsyncSession) -> tuple[UUID, int]:
    """missing 类：试算表含未知科目类别"""
    pid, year = await seed_test_project(db, name="【测试】FH-gate-unk-cat")
    await seed_tb_rows(db, pid, year, [
        ("9999", "alien_type", Decimal("100")),
        ("1001", "asset", Decimal("100")),
    ])
    return pid, year


async def fixture_missing_sign_unknown(db: AsyncSession) -> tuple[UUID, int]:
    """missing 类：负债与权益都为 0，口径无法识别"""
    pid, year = await seed_test_project(db, name="【测试】FH-gate-sign-unk")
    await seed_tb_rows(db, pid, year, [
        ("1001", "asset", Decimal("100")),
        ("6001", "revenue", Decimal("0")),
    ])
    return pid, year


async def fixture_not_applicable_placeholder(db: AsyncSession) -> tuple[UUID, int]:
    """not_applicable 占位：当前 check_tb_balance 无此路径，留给其他检查方法"""
    return await seed_test_project(db, name="【测试】FH-gate-na")


async def fixture_exception_inject(db: AsyncSession) -> tuple[UUID, int]:
    """exception 类：由测试注入使 check_tb_balance 方法体抛异常"""
    return await seed_test_project(db, name="【测试】FH-gate-exc")


# ---------------------------------------------------------------------------
# 分支 → 夹具映射（与 _branches.BRANCHES 对齐）
# ---------------------------------------------------------------------------

#: key = branch_id，value = (构造器, 预期 status)
BRANCH_FIXTURES: dict[str, tuple] = {
    "tb_balance.1.missing": (fixture_missing_no_data, "not_executed"),
    "tb_balance.sign_unknown": (fixture_missing_sign_unknown, "not_executed"),
    "tb_balance.exception": (fixture_exception_inject, "error"),
}

# tb_balance.unknown_category 在 PG 上无法触发（account_category 是 PG 枚举），
# 由非 PG 单测覆盖。
