"""本目录共用夹具的自测（advanced-query-linkage-closure 任务 1；design §10）。

- ``require_pg_only``：没带 ``pg_only`` 的用例要用真库夹具即失败。
- ``pg_rollback_session``：被测代码 ``commit`` 只释放保存点——写入对其他连接不可见，结束整体回滚。
- ``active_sql``：与平台 ``dataset_query.get_active_filter(strict=True)`` 逐项目同口径，且在"有 active
  数据集且还存在非生效数据集行"的项目上**确实比「只按未删」更窄**（这正是 AQ-02 的口径差）。

🔴 **2026-11-01 阶段 0 改造**：原先用 `gold.py` 写死的 `YB`（宜宾临港店）/ `WL`（和平物流）两个 UUID，
两者现算在 `projects` 表里都已查不到行。两个角色改法不同，原因写明：
- "口径更窄"是**数据分布事实**，必须在真实项目上验 ⇒ 按能力 `balance_with_narrowing_active_dataset` 动态解析；
- "该年度没有 active 数据集"是**结构分支**，而现算共享库里**没有任何活项目**的审计年度满足它
  （8 个有余额表行的项目全都有 active 数据集）⇒ 改在回滚事务里自建（夹具 `no_active_dataset_project`）。
  退而求其次挑一个"生效口径恰好等于只按未删"的真实项目也能让断言变绿，但走的是"所有行都属于生效数据集"
  那条路，**分支覆盖会静默丢失**。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.models.audit_platform_models import TbBalance
from app.models.core import Project
from app.services.dataset_query import get_active_filter
from tests.advanced_query_linkage.gold import active_sql, require_pg_only
from tests.advanced_query_linkage.writable_projects import insert_test_project


def test_require_pg_only_fails_unmarked_node_and_passes_marked_one() -> None:
    unmarked = SimpleNamespace(nodeid="x::unmarked", get_closest_marker=lambda name: None)
    with pytest.raises(pytest.fail.Exception, match="必须带 pytest.mark.pg_only"):
        require_pg_only(unmarked)
    marked = SimpleNamespace(nodeid="x::marked", get_closest_marker=lambda name: object() if name == "pg_only" else None)
    require_pg_only(marked)


@pytest.mark.pg_only
async def test_rollback_session_commit_only_releases_a_savepoint(pg_rollback_session, gold) -> None:
    # 插入走显式列裸 SQL：ORM 声明的列可以领先于共享库（2026-11-01 缺 `projects.amount_unit` 时
    # `session.add(Project(...))` 当场 UndefinedColumnError），见 `writable_projects` 模块说明。
    pid, _name = await insert_test_project(pg_rollback_session, name_suffix="夹具自检")
    await pg_rollback_session.commit()
    seen_inside = (await pg_rollback_session.execute(select(func.count()).where(Project.id == pid))).scalar_one()
    seen_outside = await gold.scalar("SELECT count(*) FROM projects WHERE id = :pid", pid=pid)
    assert (seen_inside, seen_outside) == (1, 0), "commit 之后其他连接仍看不到：外层事务没有提交，结束时整体回滚"


async def _counts(session, reader, pick) -> tuple[int, int, int]:
    """返回 (平台口径, 金标准口径, 只按未删) 三个计数。

    ``reader(sql, **params) -> int`` 由调用方给：
    - 真实（已提交）数据用 `gold`（独立连接、独立只读事务，与被测会话无关）；
    - 回滚事务里**自建**的数据只能用同一个会话 —— 它还没提交，别的连接根本看不到
      （`test_rollback_session_commit_only_releases_a_savepoint` 正是在验这一点）。
      换连接读会得到 0 而不是报错，**断言会以"两边都空"的方式假绿**，所以这里显式区分。
    """
    table = TbBalance.__table__
    where = await get_active_filter(session, table, pick.id, pick.audit_year, strict=True)
    platform = (await session.execute(select(func.count()).select_from(table).where(where))).scalar_one()
    golden = await reader(
        f"SELECT count(*) FROM tb_balance t WHERE {active_sql('t')}", pid=pick.id, year=pick.audit_year)
    undeleted = await reader(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=pick.id, year=pick.audit_year)
    return platform, golden, undeleted


def _session_reader(session):
    async def read(sql: str, **params):
        return (await session.execute(text(sql), params)).scalar_one()

    return read


@pytest.mark.pg_only
async def test_active_sql_is_narrower_when_non_active_datasets_exist(pg_rollback_session, gold, picks) -> None:
    """真实项目：有 active 数据集且该年度还有非生效数据集的行 ⇒ 生效口径严格窄于只按未删。"""
    pick = await picks.resolve("balance_with_narrowing_active_dataset")
    platform, golden, undeleted = await _counts(pg_rollback_session, gold.scalar, pick)
    assert golden == platform > 0, (pick, platform, golden)
    assert golden < undeleted, (
        f"{pick}：生效口径 {golden} 应严格窄于只按未删 {undeleted} —— 相等的话这条用例证明不了口径差"
    )


@pytest.mark.pg_only
async def test_active_sql_falls_back_to_undeleted_without_any_dataset(
    pg_rollback_session, gold, no_active_dataset_project
) -> None:
    """自建项目：该年度没有任何数据集行 ⇒ 生效口径 = 只按未删（且软删行确实被排除）。"""
    pick = no_active_dataset_project
    read = _session_reader(pg_rollback_session)
    platform, golden, undeleted = await _counts(pg_rollback_session, read, pick)
    assert golden == platform == undeleted > 0, (pick, platform, golden, undeleted)
    total_rows = await read(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year",
        pid=pick.id, year=pick.audit_year)
    assert undeleted < total_rows, (
        f"自建项目里应有软删行（现 {undeleted}/{total_rows}）—— 否则「只按未删」这一半没被走到"
    )
    # 反向断言：这些行确实只存在于本事务里（换连接读不到），否则就是真写进了共享库
    assert await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid", pid=pick.id
    ) == 0, "自建行对其他连接可见 ⇒ 写出了回滚事务，共享库会留残留"
