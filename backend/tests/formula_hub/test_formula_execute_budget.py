"""执行预算（spec formula-hub-integrity-closure 任务 13；需求 12.3，ADR-FHIC-19 的 ``formula_budget.run_with_deadline``）。

端点装配同 ``_central_world.py``（五个执行端点 = 四类：中央 execute、中央 batch、debug、报表配置单条 / 批量）。
一、慢取数（SQLite）：取数函数（中央与 debug 走的 ``formula_preloader._load_tb``、报表配置走的
   ``TrialBalanceResolver._get_tb_rows_prefix``）先睡 30 秒，时限调到 0.3 秒 ⇒ 504 ``FORMULA_TIMEOUT``（整体超时），用时远小于
   30 秒、响应里没有任何结果；之后同一会话 ``SELECT 1`` 成功且夹具行仍在（只回滚到保存点，连接没被作废）。
   整批一个时限：三条各睡 0.2 秒、单条时限 10 秒、整批 0.5 秒 ⇒ 504；整批放宽到 5 秒 ⇒ 200 且三条都有值。
二、真 PG 语句超时：``FORMULA_EXECUTE_TIMEOUT=1``（单条语句 500 毫秒），取数前先 ``pg_sleep(2)`` ⇒ 数据库以 query_canceled
   结束语句 ⇒ 504（cause = 数据库语句超时：先于 1 秒的 Python 时限）；之后同一会话可查询、仍是同一连接、
   ``statement_timeout`` 回到请求前的值。五个端点各一例，另一例的取消被预载层 fail-soft 吞掉（``ROW`` 读报表行时
   ``pg_sleep``，预载层把异常记成取数缺口后继续求值）⇒ 仍 504。
   被吞掉的是其他数据库错误（取数时查不存在的表；debug 的上下文构造、报表配置 batch 的逐条求值都吞异常）⇒ 照常 200、
   原因如实回显，之后同一会话可查询、GUC 已撤销（PG 事务停在失败态时预算回到保存点，而不是 500）。
三、真 PG 取消落在语句执行中（Python 侧时限先到、语句时限 29.5 秒）：SQLAlchemy 作废该连接 ⇒ 预算作废会话后 504；同一会话
   再查询换了新连接（``pg_backend_pid`` 不同）且成功。
四、超大表达式：深度 60 / 节点 2002 ⇒ 200、``ok=false``、原因「表达式超出求值预算」（求值前报错，不超时）。
五、超条数：``batch-execute`` 201 条、``execute-formulas-batch`` 1001 条 ⇒ 422 ``FORMULA_BATCH_TOO_LARGE``；200 / 1000 条放行。
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_platform_models import TrialBalance
from app.services import formula_preloader
from app.services.amount_resolver import TrialBalanceResolver
from app.services.formula_budget import (
    BATCH_TOO_LARGE_ERROR_CODE,
    CAUSE_DEADLINE,
    CAUSE_STATEMENT,
    TIMEOUT_ERROR_CODE,
    FormulaTimeout,
    run_with_deadline,
)
from tests.formula_hub._central_world import (
    BATCH_PATH,
    DEBUG_PATH,
    EXECUTE_PATH,
    REPORT_BATCH_PATH,
    REPORT_EXECUTE_PATH,
    YEAR,
    Row,
    authenticate,
    pg_endpoint,
    seed,
    sqlite_endpoint,
)
from tests.formula_hub._pg_harness import assert_snapshot_database, make_engine

D = Decimal
ROWS = (Row("1001", D(1500), D(1400)), Row("1002", D(500), D(450)), Row("1012", D(70), D(60)))
#: 端点 → 一条带试算表取数的公式（报表配置用「期末余额」，中央 / debug 用「审定数」）
ENDPOINTS = (EXECUTE_PATH, BATCH_PATH, DEBUG_PATH, REPORT_EXECUTE_PATH, REPORT_BATCH_PATH)
_IDS = ("execute", "batch-execute", "debug", "report-execute", "report-batch")


def _formula(path: str, code: str = "1001") -> str:
    return f"TB('{code}','期末余额')" if path.startswith("/api/report-config") else f"TB('{code}','审定数')"


def _payload(path: str, pid, formulas: list[str]) -> Any:
    if path in (EXECUTE_PATH, BATCH_PATH):
        items = [{"project_id": str(pid), "year": YEAR, "formula_type": "TB", "params": {"formula": f}}
                 for f in formulas]
        return items if path == BATCH_PATH else items[0]
    if path == DEBUG_PATH:
        return {"project_id": str(pid), "year": YEAR, "formula": formulas[0], "scope": "report"}
    if path == REPORT_EXECUTE_PATH:
        return {"project_id": str(pid), "year": YEAR, "formula": formulas[0]}
    return {"project_id": str(pid), "year": YEAR,
            "formulas": [{"row_code": f"R{i:04d}", "formula": f} for i, f in enumerate(formulas)]}


def _post(client, path: str, pid, formulas: list[str]):
    started = time.monotonic()
    response = client.post(path, json=_payload(path, pid, formulas))
    return response, time.monotonic() - started


def _patch_fetch(monkeypatch, before: Callable[[Any], Any]) -> None:
    """两条取数路径在真正取数前先 ``await before(db)``（中央 / debug：预载试算表；报表配置：试算表宽集合）。"""
    load_tb = formula_preloader._load_tb
    prefix = TrialBalanceResolver._get_tb_rows_prefix

    async def slow_load_tb(db, *args, **kwargs):
        await before(db)
        return await load_tb(db, *args, **kwargs)

    async def slow_prefix(self, account_code):
        await before(self.db)
        return await prefix(self, account_code)

    monkeypatch.setattr(formula_preloader, "_load_tb", slow_load_tb)
    monkeypatch.setattr(TrialBalanceResolver, "_get_tb_rows_prefix", slow_prefix)


def _sleeper(seconds: float):
    async def before(_db):
        await asyncio.sleep(seconds)
    return before


def _pg_sleeper(seconds: float):
    async def before(db):
        await db.execute(sa.text(f"SELECT pg_sleep({float(seconds)})"))
    return before


def _assert_timeout(response, cause: str) -> None:
    assert response.status_code == 504, response.text
    body = response.json()
    assert set(body) == {"detail"}, body  # 不返回部分结果
    assert (body["detail"]["error_code"], body["detail"]["cause"]) == (TIMEOUT_ERROR_CODE, cause), body


async def _session_state(session: AsyncSession, pid) -> tuple[int, int]:
    """同一会话：``SELECT 1`` 与夹具行数（ORM 条件，SQLite 存的 UUID 无连字符，不能按 str 绑定）。"""
    one = (await session.execute(sa.text("SELECT 1"))).scalar_one()
    count = (await session.execute(sa.select(sa.func.count()).select_from(TrialBalance)
                                   .where(TrialBalance.project_id == pid))).scalar_one()
    return one, count


# ─── 一、慢取数（SQLite） ─────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ENDPOINTS, ids=_IDS)
def test_slow_fetch_times_out_and_session_reusable(path, monkeypatch):
    monkeypatch.setattr(settings, "FORMULA_EXECUTE_TIMEOUT", 0.3)
    monkeypatch.setattr(settings, "FORMULA_BATCH_TIMEOUT", 0.3)
    _patch_fetch(monkeypatch, _sleeper(30))
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_slow") as (client, world):
        pid = world.projects["p"]
        response, elapsed = _post(client, path, pid, [_formula(path)])
        _assert_timeout(response, CAUSE_DEADLINE)
        assert elapsed < 10, elapsed
        assert client.portal.call(_session_state, world.session, pid) == (1, len(ROWS))


@pytest.mark.parametrize("path", (BATCH_PATH, REPORT_BATCH_PATH), ids=("batch-execute", "report-batch"))
def test_batch_deadline_is_whole_batch(path, monkeypatch):
    monkeypatch.setattr(settings, "FORMULA_EXECUTE_TIMEOUT", 10)
    _patch_fetch(monkeypatch, _sleeper(0.2))
    formulas = [_formula(path, r.code) for r in ROWS]
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_whole") as (client, world):
        pid = world.projects["p"]
        monkeypatch.setattr(settings, "FORMULA_BATCH_TIMEOUT", 0.5)
        response, _ = _post(client, path, pid, formulas)
        _assert_timeout(response, CAUSE_DEADLINE)
        monkeypatch.setattr(settings, "FORMULA_BATCH_TIMEOUT", 5)
        response, _ = _post(client, path, pid, formulas)
        assert response.status_code == 200, response.text
        body = response.json()
        values = [r["value"] for r in (body if path == BATCH_PATH else body["results"])]
        assert values == [float(r.audited) for r in ROWS], body


# ─── 二、真 PG 语句超时 ───────────────────────────────────────────────────────


async def _pg_state(session: AsyncSession) -> tuple[int, int, str]:
    row = (await session.execute(sa.text(
        "SELECT 1, pg_backend_pid(), current_setting('statement_timeout')"))).one()
    return tuple(row)


@pytest.mark.pg_only
@pytest.mark.parametrize("path", ENDPOINTS, ids=_IDS)
def test_pg_statement_timeout_maps_to_504(path, monkeypatch):
    monkeypatch.setattr(settings, "FORMULA_EXECUTE_TIMEOUT", 1)
    _patch_fetch(monkeypatch, _pg_sleeper(2))
    with pg_endpoint() as (client, session, api):
        world = client.portal.call(lambda s: seed(s, {"p": ROWS}, tag="fh_task13_pg"), session)
        authenticate(api, session, world.user)
        before = client.portal.call(_pg_state, session)
        response, elapsed = _post(client, path, world.projects["p"], [_formula(path)])
        _assert_timeout(response, CAUSE_STATEMENT)
        assert elapsed < 2, elapsed
        assert client.portal.call(_pg_state, session) == before  # 同一连接、可查询、GUC 已撤销


@pytest.mark.pg_only
def test_pg_statement_timeout_swallowed_by_preload(monkeypatch):
    """``ROW`` 读报表行时语句被取消：预载层 ``_load_report_rows`` 吞掉异常记成缺口，预算仍按超时处理。"""
    monkeypatch.setattr(settings, "FORMULA_EXECUTE_TIMEOUT", 1)
    load_rows = formula_preloader.load_report_rows

    async def slow_rows(db, *args, **kwargs):
        await db.execute(sa.text("SELECT pg_sleep(2.0)"))
        return await load_rows(db, *args, **kwargs)

    monkeypatch.setattr(formula_preloader, "load_report_rows", slow_rows)
    with pg_endpoint() as (client, session, api):
        world = client.portal.call(lambda s: seed(s, {"p": ROWS}, tag="fh_task13_pg_swallow"), session)
        authenticate(api, session, world.user)
        before = client.portal.call(_pg_state, session)
        response, elapsed = _post(client, EXECUTE_PATH, world.projects["p"], ["ROW('BS-002')"])
        _assert_timeout(response, CAUSE_STATEMENT)
        assert elapsed < 2, elapsed
        assert client.portal.call(_pg_state, session) == before


_MISSING_TABLE = "fh_task13_no_such_table"


async def _broken_fetch(db) -> None:
    await db.execute(sa.text(f"SELECT 1 FROM {_MISSING_TABLE}"))


@pytest.mark.pg_only
@pytest.mark.parametrize("path", (DEBUG_PATH, REPORT_BATCH_PATH), ids=("debug", "report-batch"))
def test_pg_swallowed_db_error_keeps_result_and_session(path, monkeypatch):
    _patch_fetch(monkeypatch, _broken_fetch)
    with pg_endpoint() as (client, session, api):
        world = client.portal.call(lambda s: seed(s, {"p": ROWS}, tag="fh_task13_pg_broken"), session)
        authenticate(api, session, world.user)
        before = client.portal.call(_pg_state, session)
        response, _ = _post(client, path, world.projects["p"], [_formula(path, r.code) for r in ROWS])
        assert response.status_code == 200, response.text
        body = response.json()
        items = body["results"] if path == REPORT_BATCH_PATH else [body]
        assert all(item["ok"] is False and item["errors"] for item in items), body
        assert _MISSING_TABLE in " ".join(items[0]["errors"]), body
        assert client.portal.call(_pg_state, session) == before


# ─── 三、真 PG 取消落在语句执行中 ─────────────────────────────────────────────


@pytest.mark.pg_only
async def test_pg_inflight_cancel_invalidates_session(monkeypatch):
    """Python 侧时限先到、语句还在跑：连接被作废 ⇒ 预算作废会话；同一会话换新连接后照常可查询。"""
    assert_snapshot_database()  # 本例的会话直连引擎（只读、无外层回滚事务），只许快照库
    monkeypatch.setattr(settings, "FORMULA_EXECUTE_TIMEOUT", 30)
    engine = make_engine()
    try:
        async with AsyncSession(engine) as db:
            before = (await db.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
            started = time.monotonic()
            with pytest.raises(FormulaTimeout) as caught:
                await run_with_deadline(db, lambda: db.execute(sa.text("SELECT pg_sleep(5)")), seconds=1)
            assert time.monotonic() - started < 4.5
            assert caught.value.status_code == 504
            assert caught.value.detail["cause"] == CAUSE_DEADLINE
            after = (await db.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
            assert after != before
            assert (await db.execute(sa.text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


# ─── 四、超大表达式 ───────────────────────────────────────────────────────────


DEEP = "+".join(["1"] * 60)  # 左结合链，深度 60 > 50
WIDE = "MAX(" + ",".join(["1"] * 2001) + ")"  # 节点 2002 > 2000，深度 2


@pytest.mark.parametrize("path", ENDPOINTS, ids=_IDS)
def test_oversized_expression_reported_not_evaluated(path):
    cases = [(DEEP, "AST 深度超过 50 层")] + ([] if path == DEBUG_PATH else [(WIDE, "AST 节点超过 2000 个")])
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_ast") as (client, world):
        for formula, reason in cases:
            response, elapsed = _post(client, path, world.projects["p"], [formula])
            assert response.status_code == 200, response.text
            body = response.json()
            item = body[0] if path == BATCH_PATH else (body["results"][0] if path == REPORT_BATCH_PATH else body)
            assert item["ok"] is False, item
            if path != DEBUG_PATH:  # debug 照 L1 回显 value（失败时 "0"），以 ok / errors 判
                assert item["value"] is None, item
            assert any(f"表达式超出求值预算：{reason}" in e for e in item["errors"]), item
            assert elapsed < 10, elapsed


# ─── 五、超条数 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("path", "limit"), ((BATCH_PATH, 200), (REPORT_BATCH_PATH, 1000)),
                         ids=("batch-execute", "report-batch"))
def test_batch_size_limit(path, limit):
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_size") as (client, world):
        pid = world.projects["p"]
        response, _ = _post(client, path, pid, ["1"] * (limit + 1))
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert (detail["error_code"], detail["max_items"], detail["received"]) == (
            BATCH_TOO_LARGE_ERROR_CODE, limit, limit + 1)
        response, _ = _post(client, path, pid, ["1"] * limit)
        assert response.status_code == 200, response.text
        body = response.json()
        values = [r["value"] for r in (body if path == BATCH_PATH else body["results"])]
        assert values == [1.0] * limit
