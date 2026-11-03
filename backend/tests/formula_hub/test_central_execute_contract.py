"""中央执行合同（spec formula-hub-integrity-closure 需求 2.1、2.2、2.4、2.8，ADR-FHIC-18 / 19）。

夹具与端点装配在 ``tests/formula_hub/_central_world.py``：应用按生产注册只挂 ``formula.router`` + ``formula_debug.router``，
TestClient 真发请求，只替换 ``get_current_user`` / ``get_db``（身份 = 本项目 readonly 成员，门禁真实运行）；SQLite 引擎、
会话与夹具建在 TestClient 的事件循环线程里（``client.portal``），真 PG 用 ``pg_tx_session``（快照库，外层事务回滚）。
金标准一律在测试内独立计算：前缀宽集合里存在以本码为前缀且更长的码 ⇒ 父行，不计入（不 import ``tb_leaf_codes``）。

任务 11 ——「未审数」规范列：``TB(code,'未审数')`` = 叶子 ``unadjusted_amount`` 之和（原别名指向「期末余额」，而预载层的
「期末余额」存的是 ``audited_amount`` ⇒ 取到的是审定数）。
一、debug 未审 = 金标准（SQLite）：夹具「审定 ≠ 未审」，含父子并存行（``1122`` 父 95、子 38 + 47）与「未审 = 0」行
   （``1601`` 审定 1,200,000）。
二、XR-07（审定数 = 未审数 + ADJ + ADJ），规则文本取生产规则库 ``wp_cross_check_service.load_rules()``：
   1. ``test_xr07_unadjusted_semantics``（SQLite）：按科目展开后经 L1 生产路径（debug 端点，``scope=wp``）求值 ——
      「审定 ≠ 未审、无调整」的科目 ⇒ 0（判出差异）；「审定 = 未审 + 已审批 AJE + RJE」（审定 ≠ 未审）⇒ 1（通过）。
   2. ``test_xr07_production_cross_check_entry``（真 PG）：生产表间审核入口 ``CrossCheckService.execute``（按
      ``trial_balance`` 的列逐行比、不经 ``COLUMN_ALIASES``；裸 SQL 按 ``str(uuid)`` 绑定，只能真 PG）：差异项目 ``fail``
      且点名的科目 = 金标准算出的不平科目，一致项目 ``pass``。

任务 12 —— 中央执行合同（``/api/formula/execute`` / ``/batch-execute`` 经 ``FormulaEngine`` 薄转发到
``formula_central_execute.execute_central``；``/api/formula/debug`` 共用同一预检）：
三、``test_central_execute_gold_huashi_uat``（真 PG 只读）：华氏 / 【UAT】子公司A 的 ``TB(code,'审定数')`` = 叶子
   ``audited_amount`` 和、``TB(code,'未审数')`` = 叶子 ``unadjusted_amount`` 和（金标准 = 测试内独立 SQL + 叶子判定），三个端点
   一致；现值（2026-10-27 快照）华氏 1001 审定 100 / 未审 0、子公司A 1001 审定 1,200,000 / 未审 0，只作记录、不写进断言。
四、``test_central_execute_failures``（SQLite，9 例）：除零、ROW 缺行、未注册列名、``IF`` 两参、``MAX`` / ``MIN`` 一参、
   ``ROUND()``、``AUX`` 一参 ⇒ 200、``ok=false``、``value=null``、``errors`` 含该例原因、``error`` 非空、``state ∈ {blocked,
   error}``；试算表无此科目 ⇒ ``state=missing``「试算表无科目 9999」。另：两参 ``PREV(code,'未审数')`` 取不到上年 ⇒
   ``missing``（任务 11 交接①）。
五、``test_precheck_classification``（SQLite，正反各 4 例 × execute / batch / debug）：``formula_type=TB``，表达式含未注册
   函数 ⇒ 422 ``FORMULA_FUNCTION_UNSUPPORTED`` 且点名该函数；``ROUND`` / ``IF`` / ``MAX`` / 已注册自定义函数 ⇒ 200 且
   ``ok=true``、值 = 金标准。
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.services.formula_engine import FormulaEngine
from app.services.formula_management.function_support_matrix import called_function_names
from app.services.wp_cross_check_service import CrossCheckService, load_rules
from tests.formula_hub._central_world import (
    YEAR,
    Row,
    authenticate,
    membership,
    new_user,
    pg_endpoint,
    post_batch,
    post_debug,
    post_execute,
    seed,
    send_batch,
    send_debug,
    send_execute,
    sqlite_endpoint,
)

D = Decimal
_CENT = D("0.01")


# ─── 夹具数据（SQLite / PG 同一份） ───────────────────────────────────────────


#: 差异项目：审定 ≠ 未审、无调整；1122 父子并存（父 95 ≠ 子 38 + 47）；1601 未审 = 0
MISMATCH = (
    Row("1122", D(100), D(95)), Row("1122-01", D(40), D(38)), Row("1122-02", D(50), D(47)),
    Row("1601", D(1200000), D(0)), Row("1001", D(150), D(100)),
)
#: 一致项目：审定 180 = 未审 100 + 已审批 AJE 50 + RJE 30（审定 ≠ 未审）
BALANCED = (Row("1002", D(180), D(100), aje=D(50), rje=D(30)),)
FIXTURES = {"mismatch": MISMATCH, "balanced": BALANCED}
#: 经 L1 求值 XR-07 的科目（差异项目含父码 1122 与「未审 = 0」的 1601）
XR07_CODES = {"mismatch": ("1122", "1601", "1001"), "balanced": ("1002",)}


def _leaf_sum(rows, target: str, attr: str) -> Decimal:
    """独立金标准：前缀宽集合里存在「以本码为前缀且更长的码」的行是父行，不计入（行只需有 ``code`` 与 ``attr``）。"""
    wide = [r for r in rows if r.code.startswith(target)]
    codes = {r.code for r in wide}
    leaves = [r for r in wide if not any(c != r.code and c.startswith(r.code) for c in codes)]
    return sum((getattr(r, attr) for r in leaves), D(0))


def _xr07_l1_gold(rows: tuple[Row, ...], code: str) -> Decimal:
    """XR-07 经 L1 求值：审定（叶子和）== 未审（叶子和）+ 本码已审批 AJE + RJE ⇒ 1，否则 0。"""
    adj = sum((r.aje + r.rje for r in rows if r.code == code), D(0))
    return D(1) if _leaf_sum(rows, code, "audited") == _leaf_sum(rows, code, "unadjusted") + adj else D(0)


def _xr07_row_failures(rows: tuple[Row, ...]) -> set[str]:
    """生产表间审核入口的 XR-07：逐行「审定 ≠ 未审 + 试算表 AJE + RJE」的科目。"""
    return {r.code for r in rows if r.audited != r.unadjusted + r.aje + r.rje}


def _xr07_rule() -> dict:
    (rule,) = [r for r in load_rules(force=True) if r["rule_id"] == "XR-07"]
    assert "{account}" in rule["formula"] and "'未审数'" in rule["formula"], rule["formula"]
    return rule


@contextmanager
def _endpoint():
    with sqlite_endpoint(FIXTURES, tag="fh_task11") as pair:
        yield pair


def _debug(client, pid: uuid.UUID, formula: str, scope: str = "report") -> tuple[Decimal | None, bool, list]:
    body = post_debug(client, pid, formula, scope)
    return (D(body["value"]) if body["value"] is not None else None), body["ok"], body["errors"]


def _cents(value) -> Decimal | None:
    return None if value is None else D(str(value)).quantize(_CENT)


# ─── 一、debug 未审 = 金标准 ───────────────────────────────────────────────────


def test_fixture_is_not_vacuous():
    """夹具：被测科目审定 ≠ 未审；1122 叶子和 85 ≠ 父行 95 ≠ 前缀全加 180；1601 未审 = 0；XR-07 两组一假一真。"""
    for code in XR07_CODES["mismatch"]:
        assert _leaf_sum(MISMATCH, code, "unadjusted") != _leaf_sum(MISMATCH, code, "audited"), code
    wide_1122 = sum((r.unadjusted for r in MISMATCH if r.code.startswith("1122")), D(0))
    assert (_leaf_sum(MISMATCH, "1122", "unadjusted"), MISMATCH[0].unadjusted, wide_1122) == (D(85), D(95), D(180))
    assert _leaf_sum(MISMATCH, "1601", "unadjusted") == 0 != _leaf_sum(MISMATCH, "1601", "audited")
    assert BALANCED[0].audited != BALANCED[0].unadjusted
    assert {c: _xr07_l1_gold(MISMATCH, c) for c in XR07_CODES["mismatch"]} == dict.fromkeys(XR07_CODES["mismatch"], 0)
    assert _xr07_l1_gold(BALANCED, "1002") == 1
    assert _xr07_row_failures(MISMATCH) == {r.code for r in MISMATCH} and _xr07_row_failures(BALANCED) == set()


def test_debug_unadjusted_equals_leaf_gold():
    """``TB(code,'未审数')`` = 叶子 ``unadjusted_amount`` 和（父子并存按叶子、未审 = 0 取 0）；同一端点 ``审定数`` 取审定叶子和。"""
    with _endpoint() as (client, world):
        pid = world.projects["mismatch"]
        got = {(code, column): _debug(client, pid, f"TB('{code}','{column}')")
               for code in XR07_CODES["mismatch"] for column in ("未审数", "审定数")}
    expected = {(code, column): (_leaf_sum(MISMATCH, code, attr), True, [])
                for code in XR07_CODES["mismatch"] for column, attr in (("未审数", "unadjusted"), ("审定数", "audited"))}
    assert got == expected


# ─── 二、XR-07 ────────────────────────────────────────────────────────────────


def test_xr07_unadjusted_semantics():
    """XR-07 规则文本经 L1 生产路径求值：差异项目各科目 0（判出差异），一致项目 1（通过）。"""
    formula = _xr07_rule()["formula"]
    with _endpoint() as (client, world):
        got = {(label, code): _debug(client, world.projects[label], formula.replace("{account}", code), scope="wp")
               for label, codes in XR07_CODES.items() for code in codes}
    expected = {(label, code): (_xr07_l1_gold(FIXTURES[label], code), True, [])
                for label, codes in XR07_CODES.items() for code in codes}
    assert got == expected
    assert {key: value for key, (value, _ok, _errors) in got.items()} == {
        ("mismatch", "1122"): 0, ("mismatch", "1601"): 0, ("mismatch", "1001"): 0, ("balanced", "1002"): 1}


@pytest.mark.pg_only
async def test_xr07_production_cross_check_entry(pg_tx):
    """生产表间审核入口（``CrossCheckService.execute``）：差异项目 fail 且点名的科目 = 金标准；一致项目 pass。"""
    rule = _xr07_rule()
    world = await seed(pg_tx, FIXTURES, tag="fh_task11")
    service = CrossCheckService(pg_tx)
    got = {}
    for label in FIXTURES:
        (result,) = await service.execute(world.projects[label], YEAR, rule_ids=[rule["rule_id"]])
        details = result.get("details") or {}
        got[label] = (result["status"], {f["account_code"] for f in details.get("failures", [])},
                      details.get("total_failures"))
    expected = {label: ("fail" if bad else "pass", bad, len(bad))
                for label, bad in ((label, _xr07_row_failures(rows)) for label, rows in FIXTURES.items())}
    assert got == expected
    assert (expected["mismatch"][0], expected["balanced"][0]) == ("fail", "pass")


# ─── 三、华氏 / UAT 金标准（真 PG 只读） ─────────────────────────────────────────


#: (项目名, 取数码)：两个项目都有「审定 ≠ 未审」的 1001（快照里未审为 0 / NULL），另各取一个科目
GOLD_PROJECTS = (("陕西华氏医药有限公司_2025", ("1001", "1002")), ("【UAT】子公司A", ("1001", "1601")))
GOLD_COLUMNS = (("审定数", "audited"), ("未审数", "unadjusted"))
_GOLD_SQL = sa.text(
    "SELECT standard_account_code AS code, COALESCE(audited_amount, 0) AS audited, "
    "COALESCE(unadjusted_amount, 0) AS unadjusted FROM trial_balance "
    "WHERE project_id = CAST(:pid AS uuid) AND year = :year AND is_deleted = false "
    "AND standard_account_code LIKE :prefix")


async def _gold_world(session) -> tuple[object, dict[str, uuid.UUID], dict[tuple[str, str, str], Decimal]]:
    """只读定位两个真实项目、按独立 SQL 算金标准；再在外层事务里建一个 readonly 成员身份（用例结束回滚）。"""
    projects: dict[str, uuid.UUID] = {}
    for name, _codes in GOLD_PROJECTS:
        ids = (await session.execute(sa.text("SELECT id FROM projects WHERE name = :name AND is_deleted = false"),
                                     {"name": name})).scalars().all()
        assert len(ids) == 1, f"快照库里未删的「{name}」应恰有 1 个，实际 {ids}"
        projects[name] = ids[0]
    gold: dict[tuple[str, str, str], Decimal] = {}
    for name, codes in GOLD_PROJECTS:
        for code in codes:
            rows = (await session.execute(_GOLD_SQL, {"pid": str(projects[name]), "year": YEAR,
                                                      "prefix": f"{code}%"})).all()
            assert rows, f"夹具空转：{name} {YEAR} 年度试算表没有 {code}"
            for _column, attr in GOLD_COLUMNS:
                gold[(name, code, attr)] = _leaf_sum(rows, code, attr)
    user = new_user("fh_task12")
    session.add(user)
    await session.flush()
    session.add_all([membership(pid, user) for pid in projects.values()])
    await session.commit()  # pg_tx_session：只释放保存点
    return user, projects, gold


@pytest.mark.pg_only
def test_central_execute_gold_huashi_uat():
    """华氏 / UAT：三个端点的 ``审定数`` = 叶子审定和、``未审数`` = 叶子未审和（金标准独立 SQL），均 ok。"""
    with pg_endpoint() as (client, session, api):
        user, projects, gold = client.portal.call(_gold_world, session)
        authenticate(api, session, user)
        got, expected = {}, {}
        for name, codes in GOLD_PROJECTS:
            pid = projects[name]
            # 夹具不空转：1001 审定 ≠ 未审（审定口径改回未审数、或未审改回审定，都会被看出来）
            assert gold[(name, "1001", "audited")] != gold[(name, "1001", "unadjusted")], name
            cases = {f"TB('{code}','{column}')": gold[(name, code, attr)]
                     for code in codes for column, attr in GOLD_COLUMNS}
            batch = dict(zip(cases, post_batch(client, pid, list(cases))))
            for formula, value in cases.items():
                for kind, body in (("execute", post_execute(client, pid, formula)), ("batch", batch[formula])):
                    got[(name, formula, kind)] = (_cents(body["value"]), body["ok"], body["state"], body["errors"],
                                                  body["error"])
                    expected[(name, formula, kind)] = (_cents(value), True, "ok", [], None)
                debug = post_debug(client, pid, formula)
                got[(name, formula, "debug")] = (_cents(debug["value"]), debug["ok"], debug["errors"])
                expected[(name, formula, "debug")] = (_cents(value), True, [])
    assert got == expected


# ─── 四、失败 9 例（SQLite） ──────────────────────────────────────────────────


FAILURES = (
    ("div_zero", "TB('1001','审定数')/0", "除数为 0"),
    ("row_missing", "ROW('BS-999')", "ROW('BS-999')"),
    ("column_unregistered", "TB('1001','不存在的列')", "列名「不存在的列」未注册"),
    ("if_two_args", "IF(1>0,1)", "IF() 参数个数不符"),
    ("max_one_arg", "MAX(1)", "MAX() 参数个数不符"),
    ("min_one_arg", "MIN(1)", "MIN() 参数个数不符"),
    ("round_no_args", "ROUND()", "ROUND() 参数个数不符"),
    ("aux_one_arg", "AUX('1122')", "AUX() 参数个数不符"),
    ("account_missing", "TB('9999','审定数')", "试算表无科目 9999"),
)


@pytest.mark.parametrize(("formula", "reason"), [case[1:] for case in FAILURES], ids=[case[0] for case in FAILURES])
def test_central_execute_failures(formula, reason):
    """200、``ok=false``、``value=null``、``errors`` 与 ``error`` 含该例原因；科目零命中 ``missing``，其余 ``blocked`` / ``error``。"""
    with sqlite_endpoint(FIXTURES, tag="fh_task12") as (client, world):
        pid = world.projects["mismatch"]
        single = post_execute(client, pid, formula)
        (batched,) = post_batch(client, pid, [formula])
    states = {"missing"} if "无科目" in reason else {"blocked", "error"}
    for kind, body in (("execute", single), ("batch", batched)):
        assert (body["ok"], body["value"]) == (False, None), (kind, body)
        assert body["state"] in states, (kind, body)
        assert [e for e in body["errors"] if reason in e], (kind, body)
        assert body["error"] and reason in body["error"], (kind, body)


def test_prev_unadjusted_without_prior_year_is_reported():
    """任务 11 交接①：两参 ``PREV(code,'未审数')`` 经预载层取上年项目试算表（叶子 ``unadjusted_amount``）；本项目没有上年
    项目 ⇒ 取数缺口 ⇒ ``ok=false``、``value=null``、``state=missing``（原 ``from_simple_map`` 路径没有上年数据，静默得 0）。"""
    with sqlite_endpoint(FIXTURES, tag="fh_task12") as (client, world):
        body = post_execute(client, world.projects["mismatch"], "PREV('1001','未审数')")
    assert (body["ok"], body["value"], body["state"]) == (False, None, "missing"), body
    assert [e for e in body["errors"] if e.startswith("PREV 上年试算表：")], body


# ─── 五、预检分类（SQLite） ───────────────────────────────────────────────────


CUSTOM_NAME = "FHIC_T12_CUSTOM"
CUSTOM_EXPRESSION, CUSTOM_VALUE = "40+2", D(42)
_GOLD_1001 = _leaf_sum(MISMATCH, "1001", "audited")
#: 正例（表达式 → 金标准值）与反例（表达式 → 422 点名的函数）
PRECHECK_ACCEPT = (
    ("round", "ROUND(TB('1001','审定数'),2)", _GOLD_1001),
    ("if", "IF(1>0,TB('1001','审定数'),0)", _GOLD_1001),
    ("max", "MAX(1,2)", D(2)),
    ("custom", f"{CUSTOM_NAME}()", CUSTOM_VALUE),
)
PRECHECK_REJECT = (
    ("unknown", "EVIL()", {"EVIL"}),
    ("unknown_beside_tb", "TB('1001','审定数')+EVIL(1)", {"EVIL"}),
    ("unknown_lowercase_in_round", "ROUND(evil(1),2)", {"EVIL"}),
    ("dunder_in_if", "IF(1>0,__import__('os'),0)", {"__IMPORT__"}),
)


@contextmanager
def _custom_function() -> Iterator[None]:
    engine = FormulaEngine()
    engine.register_custom_function(CUSTOM_NAME, description="任务 12 预检正例", expression=CUSTOM_EXPRESSION)
    try:
        yield
    finally:
        engine.unregister_custom_function(CUSTOM_NAME)


def test_called_function_names_strips_quotes():
    """预检的取名：剔除引号段（引号里的 ``EVIL(`` 不算）、大写、去重、按出现顺序。"""
    assert called_function_names("TB('EVIL(1)','审定数') + round(TB(\"X(\",'审定数'),2) + tb('1001')") == ["TB", "ROUND"]
    assert called_function_names("SUM_TB('1001~1999','审定数') - ROUND(MAX(1,2))") == ["SUM_TB", "ROUND", "MAX"]


@pytest.mark.parametrize(("formula", "outcome"), [case[1:] for case in (*PRECHECK_ACCEPT, *PRECHECK_REJECT)],
                         ids=[case[0] for case in (*PRECHECK_ACCEPT, *PRECHECK_REJECT)])
def test_precheck_classification(formula, outcome):
    """``formula_type=TB``：未注册函数 ⇒ 三个端点 422 点名；内置纯函数 / 已注册自定义函数 ⇒ 200、ok、值 = 金标准。"""
    with _custom_function(), sqlite_endpoint(FIXTURES, tag="fh_task12") as (client, world):
        pid = world.projects["mismatch"]
        responses = {"execute": send_execute(client, pid, formula), "batch": send_batch(client, pid, [formula]),
                     "debug": send_debug(client, pid, formula)}
    if isinstance(outcome, set):
        for kind, response in responses.items():
            assert response.status_code == 422, (kind, response.text)
            detail = response.json()["detail"]
            assert detail["error_code"] == "FORMULA_FUNCTION_UNSUPPORTED" and detail["message"], (kind, detail)
            if kind == "batch":
                assert [item["index"] for item in detail["items"]] == [0], detail
                issues = detail["items"][0]["issues"]
            else:
                issues = detail["issues"]
            assert {issue["function"] for issue in issues} == outcome, (kind, detail)
        return
    for kind, response in responses.items():
        assert response.status_code == 200, (kind, response.text)
    single, (batched,), debug = (responses[k].json() for k in ("execute", "batch", "debug"))
    for kind, body in (("execute", single), ("batch", batched)):
        assert (_cents(body["value"]), body["ok"], body["state"], body["errors"]) == (_cents(outcome), True, "ok", []), \
            (kind, body)
    assert (_cents(debug["value"]), debug["ok"], debug["errors"]) == (_cents(outcome), True, []), debug
