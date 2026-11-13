"""附注目录树的「口径解析失败」必须只降级、不能把事务弄废（真 PG）。

## 被测的是什么

`DisclosureEngine._project_scope_columns` 读项目口径（template_type / report_scope）失败时
**有意** fail-open：记一条 warning、返回 `(None, None)`（不过滤），因为这是读侧过滤，
退回「全量返回」不丢数据。

问题出在 PG 的事务语义上：一条语句失败后事务立刻进入 aborted，**之后每条语句都会
`InFailedSQLTransactionError`**。于是"降级"实际变成了"整条请求 500"。
2026-11-01 实测到的现场：共享库缺 `projects.amount_unit`（远端迁移 V250 未落库）⇒
该函数的全列 ORM 读失败 ⇒ 被吞掉 ⇒ 高级查询的附注指标树与目录取数**整条 500**
（`INTERNAL_ERROR`，日志里只有一行 warning）。

修法两条：读取改最小列投影（不再依赖领先于库的列）+ **把读取放进 `begin_nested()` 保存点**，
失败回滚到保存点再降级。本文件钉的是后者 —— 前者会随迁移落库而"自愈"，后者是永久不变式。

## 判据怎么立

用**真实语句失败**注入（`SELECT 1/0`），不 mock 异常：mock 出来的异常不会让 PG 事务 aborted，
判据会在"保存点被删掉"时照样绿。注入点是本函数的下一层 `_get_project_basic_info`。

两条断言合起来才算数：
1. `get_notes_tree` 仍返回行（降级生效，没有变成 500）；
2. **同一会话随后的查询照常执行**（事务没有停在 aborted）—— 这一条才是保存点的证据。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.services.disclosure_engine import DisclosureEngine
from tests.advanced_query_linkage.writable_projects import insert_test_project

pytestmark = pytest.mark.pg_only


async def _seed_one_note(session, pid, year: int) -> None:
    """造一条附注行（显式列裸 SQL：避免 ORM 列领先于库时整体失败）。"""
    await session.execute(
        sa.text(
            "INSERT INTO disclosure_notes (id, project_id, year, note_section, section_title, sort_order) "
            "VALUES (gen_random_uuid(), :pid, :year, '五、1', '【测试】保存点用例章节', 0)"
        ),
        {"pid": pid, "year": year},
    )


async def test_scope_resolution_failure_degrades_without_aborting_the_transaction(
    pg_rollback_session, monkeypatch
) -> None:
    session = pg_rollback_session
    year = 2025
    pid, _name = await insert_test_project(session, name_suffix="附注目录树保存点", audit_year=year)
    await _seed_one_note(session, pid, year)

    fired: list[str] = []

    async def _boom(self, _project_id):  # noqa: ANN001 - 替换实例方法
        # 真实制造一次 PG 语句失败：事务由此进入 aborted（mock 异常做不到这一点）
        fired.append("executed")
        await self.db.execute(sa.text("SELECT 1/0"))
        raise AssertionError("上一行必然抛错，不应到达这里")

    monkeypatch.setattr(DisclosureEngine, "_get_project_basic_info", _boom, raising=True)

    engine = DisclosureEngine(session)
    tree = await engine.get_notes_tree(pid, year)

    assert fired, "故障没有注入到口径解析的下一层（判据空转）"
    assert [node["note_section"] for node in tree] == ["五、1"], (
        f"口径解析失败应降级为「不过滤、全量返回」，实得 {tree!r}"
    )

    # 🔴 关键：事务必须仍可用。没有保存点时这一行会 InFailedSQLTransactionError。
    still_usable = (
        await session.execute(
            sa.text("SELECT count(*) FROM disclosure_notes WHERE project_id = :pid"), {"pid": pid}
        )
    ).scalar_one()
    assert still_usable == 1, "降级之后同一会话应能继续查询（事务没有停在 aborted）"


async def test_scope_resolution_success_keeps_filtering(pg_rollback_session) -> None:
    """阴性对照：不注入故障时，口径解析正常走通、目录树照常返回（判据不是对任何情况都绿）。

    自建项目的 `wizard_state` 为空 ⇒ 解析得到 `(None, None)` ⇒ 同样不过滤；
    这里要证明的是「没有故障时不会误报失败」，以及 `begin_nested` 的 commit 分支不抛。
    """
    session = pg_rollback_session
    year = 2025
    pid, _name = await insert_test_project(session, name_suffix="附注目录树正常路径", audit_year=year)
    await _seed_one_note(session, pid, year)

    tree = await DisclosureEngine(session).get_notes_tree(pid, year)
    assert [node["note_section"] for node in tree] == ["五、1"], tree
    assert (
        await session.execute(
            sa.text("SELECT count(*) FROM disclosure_notes WHERE project_id = :pid"), {"pid": pid}
        )
    ).scalar_one() == 1
