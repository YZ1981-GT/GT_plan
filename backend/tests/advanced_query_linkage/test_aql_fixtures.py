"""本目录共用夹具的自测（advanced-query-linkage-closure 任务 1；design §10）。

- ``require_pg_only``：没带 ``pg_only`` 的用例要用真库夹具即失败。
- ``pg_rollback_session``：被测代码 ``commit`` 只释放保存点——写入对其他连接不可见，结束整体回滚。
- ``active_sql``：与平台 ``dataset_query.get_active_filter(strict=True)`` 逐项目同口径（有 / 无 active 数据集两种项目），
  且确实比「只按未删」更窄（宜宾临港店有多个数据集的行，这正是 AQ-02 的口径差）。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.audit_platform_models import TbBalance
from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.dataset_query import get_active_filter
from tests.advanced_query_linkage.gold import AUDIT_YEAR, WL, YB, active_sql, require_pg_only


def test_require_pg_only_fails_unmarked_node_and_passes_marked_one() -> None:
    unmarked = SimpleNamespace(nodeid="x::unmarked", get_closest_marker=lambda name: None)
    with pytest.raises(pytest.fail.Exception, match="必须带 pytest.mark.pg_only"):
        require_pg_only(unmarked)
    marked = SimpleNamespace(nodeid="x::marked", get_closest_marker=lambda name: object() if name == "pg_only" else None)
    require_pg_only(marked)


@pytest.mark.pg_only
async def test_rollback_session_commit_only_releases_a_savepoint(pg_rollback_session, gold) -> None:
    pid = uuid.uuid4()
    pg_rollback_session.add(Project(
        id=pid, name="【测试】aql 夹具自检", client_name="aql 夹具自检", status=ProjectStatus.created,
    ))
    await pg_rollback_session.commit()
    seen_inside = (await pg_rollback_session.execute(select(func.count()).where(Project.id == pid))).scalar_one()
    seen_outside = await gold.scalar("SELECT count(*) FROM projects WHERE id = :pid", pid=pid)
    assert (seen_inside, seen_outside) == (1, 0), "commit 之后其他连接仍看不到：外层事务没有提交，结束时整体回滚"


@pytest.mark.pg_only
@pytest.mark.parametrize("project_id", [YB, WL], ids=["宜宾临港店（有 active 数据集）", "和平物流（没有 active 数据集）"])
async def test_active_sql_matches_platform_active_filter(pg_rollback_session, gold, project_id) -> None:
    table = TbBalance.__table__
    where = await get_active_filter(pg_rollback_session, table, project_id, AUDIT_YEAR, strict=True)
    platform = (await pg_rollback_session.execute(select(func.count()).select_from(table).where(where))).scalar_one()
    golden = await gold.scalar(
        f"SELECT count(*) FROM tb_balance t WHERE {active_sql('t')}", pid=project_id, year=AUDIT_YEAR)
    undeleted = await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=project_id, year=AUDIT_YEAR)
    assert golden == platform > 0
    has_active = await gold.scalar(
        "SELECT count(*) FROM ledger_datasets WHERE project_id = :pid AND year = :year AND status = 'active'",
        pid=project_id, year=AUDIT_YEAR)
    if has_active:
        assert golden < undeleted, "有 active 数据集的项目：生效口径应比只按未删更窄（否则这条用例证明不了口径）"
    else:
        assert golden == undeleted
