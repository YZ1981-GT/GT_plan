"""中央执行每请求的数据库往返（spec formula-hub-integrity-closure requirements §3 性能 ABBA 的热点修复）。

阶段 C 基准实测：中央 execute 每请求比基线多 6 条语句（预算的读原值 / 设新值分两条、缺科目另发一次 ``EXISTS``），
路由函数层中位数倍率 2.107 > 1.5。修复后的判据：

一、缺科目判定复用预载读到的试算表行（``preload(tb_presence=…)``）：预载读过的码不再另发 ``EXISTS``（SQLite 端点真发请求，
   按 ``before_cursor_execute`` 数语句）；缺科目（单码、区间）照旧 ``missing`` 并点名，有下级行的父码、区间内有行 ⇒ 不缺。
二、``missing_account_codes(known=…)``：已知码不查库；预载没读的码（``known`` 里没有）只对这些码发一条语句。
三、真 PG：执行预算一条语句读原值并设新值 —— 求值期间 ``statement_timeout`` = 预算值，成功后回到请求前的值；
   预算自身只发两条含 ``statement_timeout`` 的语句（设 + 恢复）。
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.services.formula_budget import run_with_deadline, statement_timeout_ms
from app.services.formula_central_execute import missing_account_codes
from tests.formula_hub._central_world import Row, post_execute, sqlite_endpoint

D = Decimal
FIXTURES = {"p": (Row("1122", D(100), D(95)), Row("1122-01", D(40), D(38)), Row("1601", D(5), D(5)))}

#: (公式, 期望 ok, 期望值 / 缺科目点名的码)
CASES = (
    ("TB('1122','审定数')", True, D(40)),
    ("TB('112','审定数')", True, D(40)),
    ("SUM_TB('1100~1199','审定数')", True, D(40)),
    ("TB('9999','审定数')", False, "9999"),
    ("SUM_TB('8000~8999','审定数')", False, "8000~8999"),
    ("TB('1601','审定数')+TB('9998','审定数')", False, "9998"),
)


@pytest.mark.parametrize(("formula", "ok", "expect"), CASES, ids=[c[0] for c in CASES])
def test_missing_codes_from_preload_without_exists(formula, ok, expect):
    statements: list[str] = []

    def _record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    with sqlite_endpoint(FIXTURES, tag="fh_stagec_roundtrips") as (client, world):
        bind = world.session.get_bind()
        sa.event.listen(bind, "before_cursor_execute", _record)
        try:
            body = post_execute(client, world.projects["p"], formula)
        finally:
            sa.event.remove(bind, "before_cursor_execute", _record)
    assert body["ok"] is ok, body
    if ok:
        assert D(str(body["value"])) == expect, body
    else:
        assert (body["state"], body["value"]) == ("missing", None), body
        assert any(f"无科目 {expect}" in e for e in body["errors"]), body
    exists = [s for s in statements if "EXISTS" in s.upper()]
    assert not exists, f"预载已读过的码不应再发 EXISTS：{exists}"
    assert any("trial_balance" in s for s in statements), "非空转：本次求值确实读了试算表"


class _RecordingDb:
    def __init__(self, hits: tuple[bool, ...]):
        self.statements: list = []
        self._hits = hits

    async def execute(self, statement):
        self.statements.append(statement)
        hits = self._hits

        class _Result:
            def one(self):
                return hits

        return _Result()


async def test_known_codes_skip_query():
    db = _RecordingDb(())
    formula = "TB('1001','审定数')+SUM_TB('6001~6999','审定数')"
    missing = await missing_account_codes(db, None, 2025, formula, known={"1001": True, "6001~6999": False})
    assert missing == ["6001~6999"]
    assert db.statements == []


async def test_unknown_codes_probe_only_those():
    db = _RecordingDb((False,))
    formula = "TB('1001','审定数')+TB('2001','审定数')"
    missing = await missing_account_codes(db, None, 2025, formula, known={"1001": True})
    assert missing == ["2001"]
    (statement,) = db.statements
    assert len(statement.selected_columns) == 1, "只对预载没读的码发 EXISTS"


async def test_without_known_probes_every_code():
    db = _RecordingDb((True, False))
    missing = await missing_account_codes(db, None, 2025, "TB('1001','审定数')+TB('2001','审定数')")
    assert missing == ["2001"]
    (statement,) = db.statements
    assert len(statement.selected_columns) == 2


@pytest.mark.pg_only
async def test_pg_budget_sets_and_restores_in_two_statements(pg_tx):
    await pg_tx.execute(sa.text("SELECT set_config('statement_timeout', '7s', true)"))
    bind = pg_tx.get_bind()
    engine = getattr(bind, "engine", bind)
    statements: list[str] = []

    def _record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    async def _inside():
        return (await pg_tx.execute(sa.text("SELECT current_setting('statement_timeout') AS inner_value"))).scalar_one()

    sa.event.listen(engine, "before_cursor_execute", _record)
    try:
        inside = await run_with_deadline(pg_tx, _inside, seconds=5)
    finally:
        sa.event.remove(engine, "before_cursor_execute", _record)
    after = (await pg_tx.execute(sa.text("SELECT current_setting('statement_timeout')"))).scalar_one()
    assert inside == f"{statement_timeout_ms()}ms"
    assert after == "7s"
    budget = [s for s in statements if "statement_timeout" in s and "inner_value" not in s]
    assert len(budget) == 2, budget
