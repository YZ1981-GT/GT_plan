"""C1：**完整** FormulaPushEngine run 的 statement 计数守卫。

spec: `platform-heavy-jobs-and-capacity-closure` C1。

既有守卫 `tests/formula_runtime/test_workpaper_adapter.py::
test_apply_many_statement_count_is_constant_for_existing_rows` 只覆盖 adapter 一层
（10/1000/10000 条 CAS 均固定 3 次 SQL）。C1 登记勘误指出的缺口是「完整
``FormulaPushEngine.run`` 的 statement count 仍缺」——本文件补这一层。

判据：同一项目、同一底稿、同一规则命中 N 个目标条目时，一次完整 run 发出的
**SQL 条数必须与 N 无关**（R4.1「SQL 数不得随单元格数线性增长」），且不超过棘轮上限。

口径：在真 engine 上挂 `before_cursor_execute` 统计**真发出的 SQL**，不是 mock 调用数。

🔴 为什么必须测引擎层：引擎每个底稿还会走 `_load_states` / savepoint / 附注 follow-up /
`FormulaPushState` upsert。任何一处写成「逐条目一条 SQL」都会让目标条目数放大成往返数，
而 adapter 守卫照样全绿（它只看 adapter 自己那三次）。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.formula_push import engine as push
from app.services.formula_push.bindings.e1 import WorkpaperTarget
from app.services.formula_push.rules import PushRule, PushSource, PushTarget
from tests._formula_push_env import Env, make_env

pytestmark = pytest.mark.asyncio

#: 一次完整 run 的 SQL 条数上限（棘轮，只降不升）。
#:
#: 现算值（2026-11-16 实测，单底稿单规则）：**14 条**，与目标单元数 1/10/50 无关。
#: 给 20 的余量吸收无关的辅助查询（如状态预载），但逐条目 SQL 的回退会让 50 单元
#: 直接跳到 60+ 条而打红。
_MAX_STATEMENTS_PER_RUN = 20

_UNIT_COUNTS = (1, 10, 50)


def _build_rule() -> PushRule:
    """规则指向夹具已有的 E1 底稿（`make_env` 会建 wp_index=wp_code 'E1'）。"""
    return PushRule(
        rule_id="E1.metric",
        page_key="workpaper:E1",
        stage="source",
        policy="system",
        target=PushTarget(
            domain="workpaper", wp_code="E1", sheet_code="E1",
            item_id="E1-metric-0", fields=("value",),
        ),
        source=PushSource(kind="derivation", name="fake"),
        triggers=("manual",),
        description="C1 statement count",
    )


def _install_single_rule_binding(monkeypatch, rule: PushRule, item_ids: list[str]) -> None:
    """把引擎的候选集收敛到「一条规则 + 一个假 binding」。"""

    class _Binding:
        wp_code = "E1"
        account_prefixes = ("999",)
        derivations = frozenset()

        async def load_sources(self, db, project_id, year, wp_id):
            return SimpleNamespace(warnings=[], template_type=None)

        def workpaper_targets(self, rules, entries, sources):
            return [
                WorkpaperTarget(
                    rule_id=rules.rule_id,
                    policy=rules.policy,
                    addr_id=f"E1/E1/{item_id}",
                    item_id=item_id,
                    formula_value="new",
                    current_value=entries.get(item_id),
                )
                for item_id in item_ids
            ], []

        def apply(self, entries, target, value):
            value = str(value)
            changed = entries.get(target.item_id) != value
            entries[target.item_id] = value
            return changed

        def entry_warnings(self, entries):
            return []

    binding = _Binding()
    monkeypatch.setattr(push, "supported_wp_codes", lambda: ("E1",))
    monkeypatch.setattr(push, "get_binding", lambda code: binding)
    monkeypatch.setattr(
        push, "rules_for",
        lambda rules, *, wp_code, trigger: (rule,) if wp_code == "E1" else (),
    )

    async def _fake_effective(db, project_id):
        return [rule], []

    monkeypatch.setattr(
        "app.services.formula_settings.push_settings.effective_push_rules",
        _fake_effective,
    )


async def _seed_items(env: Env, item_ids: list[str]) -> None:
    from datetime import datetime, timezone

    async with env.factory() as db:
        # PG 上 updated_at 是 timestamptz（asyncpg 严格类型），必须传 datetime；
        # SQLite 列是 TEXT，传 str。按引擎绑定列类型。
        is_pg = db.get_bind().dialect.name == "postgresql"
        stale_ts = (
            datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
            if is_pg
            else "2026-09-01 08:00:00.000000+00:00"
        )
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses "
                "(id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ),
            [
                {
                    "id": str(uuid.uuid4()),
                    "p": str(env.pid),
                    "w": str(env.wp_id),
                    "i": item_id,
                    "r": "old",
                    "t": stale_ts,
                }
                for item_id in item_ids
            ],
        )
        await db.commit()


async def _run_once(monkeypatch, unit_count: int) -> tuple[int, int]:
    """在全新环境里跑一次完整 run，返回 (SQL 条数, 推送成功条目数)。"""
    item_ids = [f"E1-metric-{index}" for index in range(unit_count)]
    rule = _build_rule()

    async with make_env(monkeypatch) as env:
        _install_single_rule_binding(monkeypatch, rule, item_ids)
        await _seed_items(env, item_ids)

        statements: list[str] = []

        def _count(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        # make_env 建的 engine 挂在 session factory 上；从 factory 取 sync_engine
        sync_engine = env.factory.kw["bind"].sync_engine
        sa.event.listen(sync_engine, "before_cursor_execute", _count)
        try:
            result = await env.push("manual", codes=["E1"])
        finally:
            sa.event.remove(sync_engine, "before_cursor_execute", _count)

        pushed = len(result.changed_items)
        if pushed == 0:
            raise AssertionError(
                "夹具没接上（changed_items=0）—— 诊断信息：\n"
                f"  status={result.status!r}\n"
                f"  warnings={result.warnings}\n"
                f"  workpapers={result.workpapers}\n"
                f"  items={[(i.rule_id, i.action, i.state, i.reason) for i in result.items]}\n"
                f"  statements={len(statements)}"
            )
        return len(statements), pushed


@pytest_asyncio.fixture
async def _noop_fixture():
    """占位：确保 pytest_asyncio 已加载（本文件的 run 都在 _run_once 内自建环境）。"""
    yield None


async def test_statement_count_is_constant_across_unit_counts(monkeypatch):
    """1 / 10 / 50 个目标单元 ⇒ SQL 条数相同，且推送条目数等于单元数。"""
    observed: dict[int, int] = {}
    for unit_count in _UNIT_COUNTS:
        statements, pushed = await _run_once(monkeypatch, unit_count)
        observed[unit_count] = statements
        print(f"[C1] units={unit_count} statements={statements} changed_items={pushed}")
        assert pushed == unit_count, (
            f"{unit_count} 个目标单元应全部推送成功，实际 {pushed}；"
            "（若为 0 说明夹具没接上，不是引擎问题）"
        )

    assert observed[1] == observed[10] == observed[50], (
        "SQL 条数随目标单元数变化 ⇒ 引擎里存在逐条目写入："
        f"{observed}"
    )
    assert observed[50] <= _MAX_STATEMENTS_PER_RUN, (
        f"单次 run 发出 {observed[50]} 条 SQL，超过棘轮上限 {_MAX_STATEMENTS_PER_RUN}"
    )


async def test_statement_count_does_not_grow_with_unit_count(monkeypatch):
    """独立的反向判据：50 单元的 SQL 条数不得显著多于 1 单元（防「常数但很大」）。"""
    one, _ = await _run_once(monkeypatch, 1)
    fifty, _ = await _run_once(monkeypatch, 50)
    assert fifty == one, (
        f"50 单元发出 {fifty} 条 SQL、1 单元 {one} 条 —— 目标单元数不得影响 SQL 条数"
    )
