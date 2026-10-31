"""报表配置两个执行端点（spec formula-hub-integrity-closure 任务 13；需求 2.5、2.7，N6）。

端点装配同 ``_central_world.py``（应用挂 formula / formula_debug / report_config 三个 router，TestClient 真发请求，只替换
``get_current_user`` / ``get_db``，门禁真实运行）。金标准一律在测试内独立计算（叶子 = 宽集合里没有以本码为前缀且更长的码）。

一、trace 与 value 同源（需求 2.5）：``POST /api/report-config/execute-formula`` 对 BS-002 返回的 trace 里各 ``TB(...) = x``
   之和 = value，且 value = 金标准、非 0；夹具含父子并存行（1002 父 999、子 300 + 200，叶子 500）。SQLite 一例（公式取 2026-10-27
   快照里 BS-002 的现值）、真 PG 一例（公式现读快照库 ``report_config``）。原实现 value 走报表路径、trace 另跑一次空上下文的
   L1 ⇒ trace 里 TB 全是 0。
二、batch 串行（需求 2.7，真 PG）：10 条互不依赖、各取不同科目的公式全部返回数值 = 金标准（原 ``asyncio.gather`` 在同一
   ``AsyncSession`` 上并发）。
三、batch 依赖序（SQLite）：合计行写在明细行之前（``SUM_ROW`` / ``ROW`` 函数写法，报表配置里行次引用的唯一写法）仍先算明细；
   互相引用 ⇒ 两行都报「循环依赖」。原实现只认裸行次写法 ⇒ 合计行先算、取到 0。
四、``year`` 必填（N6）：两个端点缺 ``year`` ⇒ 422（原 ``body.get("year", 2024)`` 静默按 2024 年取数）。
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

import pytest
import sqlalchemy as sa

from tests.formula_hub._central_world import (
    REPORT_BATCH_PATH,
    REPORT_EXECUTE_PATH,
    YEAR,
    Row,
    authenticate,
    pg_endpoint,
    seed,
    sqlite_endpoint,
)

D = Decimal
_CENT = D("0.01")
#: 2026-10-27 快照 report_config 四个准则 BS-002（货币资金）的公式，SQLite 用例照抄（真 PG 用例现读）
BS002_FORMULA = "TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')"
ROWS = (Row("1001", D(1500), D(1400)), Row("1002", D(999), D(900)), Row("1002-01", D(300), D(280)),
        Row("1002-02", D(200), D(190)), Row("1012", D(70), D(60)))
_TB_TRACE = re.compile(r"^(?:SUM_)?TB\('([^']*)','([^']*)'\) = (-?\d+(?:\.\d+)?)$")


def _leaf_gold(rows: Iterable[Row], code: str) -> Decimal:
    wide = [r for r in rows if r.code.startswith(code)]
    codes = {r.code for r in wide}
    return sum((r.audited for r in wide if not any(c != r.code and c.startswith(r.code) for c in codes)), D(0))


def _tb_codes(formula: str) -> list[str]:
    return re.findall(r"TB\('([^']+)'", formula)


def _cents(value) -> Decimal:
    return D(str(value)).quantize(_CENT)


def _trace_terms(trace: list[str]) -> list[tuple[str, Decimal]]:
    return [(m.group(1), D(m.group(3))) for m in map(_TB_TRACE.match, trace) if m]


def _assert_trace_matches_value(body: dict, formula: str, rows: Iterable[Row]) -> None:
    rows = tuple(rows)
    gold = sum((_leaf_gold(rows, code) for code in _tb_codes(formula)), D(0))
    terms = _trace_terms(body["trace"])
    assert gold != 0, "夹具空转：金标准为 0"
    assert (body["ok"], body["error"], body["errors"]) == (True, None, [])
    assert [code for code, _ in terms] == _tb_codes(formula), body["trace"]
    assert _cents(sum((v for _, v in terms), D(0))) == _cents(body["value"]) == _cents(gold), body["trace"]
    assert any("1002" in w for w in body["warnings"]), body["warnings"]  # 1002 父 999 ≠ 子 500：告警随结果返回


def _execute_body(pid, formula: str, **extra) -> dict:
    return {"project_id": str(pid), "year": YEAR, "formula": formula, **extra}


# ─── 一、trace 与 value 同源 ──────────────────────────────────────────────────


def test_bs002_trace_sum_equals_value():
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_trace") as (client, world):
        response = client.post(REPORT_EXECUTE_PATH, json=_execute_body(world.projects["p"], BS002_FORMULA))
        assert response.status_code == 200, response.text
        _assert_trace_matches_value(response.json(), BS002_FORMULA, ROWS)


_BS002_SQL = sa.text(
    "SELECT formula FROM report_config WHERE applicable_standard = 'soe_standalone' "
    "AND report_type = 'balance_sheet' AND row_code = 'BS-002'")


async def _bs002_world(session):
    (formula,) = (await session.execute(_BS002_SQL)).scalars().all()
    world = await seed(session, {"p": ROWS}, tag="fh_task13_trace_pg")
    return formula, world


@pytest.mark.pg_only
def test_bs002_trace_sum_equals_value_pg():
    with pg_endpoint() as (client, session, api):
        formula, world = client.portal.call(_bs002_world, session)
        authenticate(api, session, world.user)
        assert set(_tb_codes(formula)) <= {r.code for r in ROWS}, f"快照 BS-002 公式引用了夹具没有的科目：{formula}"
        response = client.post(REPORT_EXECUTE_PATH, json=_execute_body(world.projects["p"], formula))
        assert response.status_code == 200, response.text
        _assert_trace_matches_value(response.json(), formula, ROWS)


# ─── 二、batch 串行（真 PG） ───────────────────────────────────────────────────


SERIAL_CODES = ("1001", "1002", "1012", "1122", "1231", "1601", "1602", "2001", "2202", "2241")
SERIAL_ROWS = tuple(Row(code, D(101) * (i + 1), D(0)) for i, code in enumerate(SERIAL_CODES))


@pytest.mark.pg_only
def test_batch_serial():
    with pg_endpoint() as (client, session, api):
        world = client.portal.call(lambda s: seed(s, {"p": SERIAL_ROWS}, tag="fh_task13_serial"), session)
        authenticate(api, session, world.user)
        formulas = [{"row_code": f"R{code}", "formula": f"TB('{code}','期末余额')"} for code in SERIAL_CODES]
        response = client.post(REPORT_BATCH_PATH, json={"project_id": str(world.projects["p"]), "year": YEAR,
                                                        "formulas": formulas})
        assert response.status_code == 200, response.text
        body = response.json()
        got = {r["row_code"]: (r["error"], None if r["value"] is None else _cents(r["value"])) for r in body["results"]}
        assert got == {f"R{r.code}": (None, _cents(r.audited)) for r in SERIAL_ROWS}
        assert {k: _cents(v) for k, v in body["row_values"].items()} == {f"R{r.code}": _cents(r.audited)
                                                                         for r in SERIAL_ROWS}


# ─── 三、batch 依赖序（SQLite） ────────────────────────────────────────────────


DEPENDENT_BATCH = (
    ("BS-011", "ROW('BS-010')+ROW('BS-002')"),
    ("BS-010", "SUM_ROW('BS-002','BS-004')"),
    ("BS-002", "TB('1001','期末余额')"),
    ("BS-003", "TB('1002','期末余额')"),
    ("BS-004", "TB('1012','期末余额')"),
    ("CY-001", "ROW('CY-002')+1"),
    ("CY-002", "ROW('CY-001')+1"),
)


def test_batch_dependency_order():
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_order") as (client, world):
        response = client.post(REPORT_BATCH_PATH, json={
            "project_id": str(world.projects["p"]), "year": YEAR,
            "formulas": [{"row_code": code, "formula": formula} for code, formula in DEPENDENT_BATCH]})
        assert response.status_code == 200, response.text
        results = response.json()["results"]
    order = [r["row_code"] for r in results]
    by_code = {r["row_code"]: r for r in results}
    detail = {code: _leaf_gold(ROWS, tb) for code, tb in (("BS-002", "1001"), ("BS-003", "1002"), ("BS-004", "1012"))}
    total = sum(detail.values(), D(0))
    assert {code: _cents(by_code[code]["value"]) for code in (*detail, "BS-010", "BS-011")} == {
        **{code: _cents(v) for code, v in detail.items()}, "BS-010": _cents(total),
        "BS-011": _cents(total + detail["BS-002"])}
    assert max(order.index(code) for code in detail) < order.index("BS-010") < order.index("BS-011"), order
    for code in ("CY-001", "CY-002"):
        assert by_code[code]["value"] is None and "循环依赖" in by_code[code]["error"], by_code[code]


# ─── 四、year 必填 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("path", "payload"), [
    (REPORT_EXECUTE_PATH, {"formula": "TB('1001','期末余额')"}),
    (REPORT_BATCH_PATH, {"formulas": [{"row_code": "BS-002", "formula": "TB('1001','期末余额')"}]}),
], ids=["execute-formula", "execute-formulas-batch"])
def test_year_required(path, payload):
    with sqlite_endpoint({"p": ROWS}, tag="fh_task13_year") as (client, world):
        response = client.post(path, json={"project_id": str(world.projects["p"]), **payload})
    assert response.status_code == 422, response.text
    assert any(err.get("loc", [])[-1:] == ["year"] for err in response.json()["detail"]), response.text
