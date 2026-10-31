"""试算表取数统一叶子口径（spec formula-hub-integrity-closure 需求 4.1、4.2、4.3 取数部分；ADR-FHIC-03）。

* 纯函数 ``select_leaves`` 的 PBT（max_examples=5）：随机科目树叶子和恒等、父行不计入、告警阈值；
* ``formula_warnings`` 收集器嵌套 / 跨 await / gather；
* 父子并存夹具（SQLite 真 ORM）表驱动 F8 的全部取数函数：值 = 测试内独立算出的叶子和，且父子不符告警被 emit。

金标准（``_gold``）在测试内独立按「同一取数集合内存在以本码为前缀且更长的码 ⇒ 父行」计算，不调用 ``tb_leaf_codes``。
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401  全量注册（ledger_datasets 外键引用的表要在 metadata 里）
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project
from app.models.dataset_models import LedgerDataset
from app.services import formula_preloader, formula_warnings, wp_formula_eval_service
from app.services.amount_resolver import TrialBalanceResolver
from app.services.formula_push.sources import load_tb_audited
from app.services.report_engine import ReportFormulaParser, evaluate_formula_result
from app.services.tb_leaf_codes import LEAF_DIFF_TOLERANCE, leaf_code_set, select_leaves

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

D = Decimal
YEAR = 2025
_TOL = D("0.005")  # 测试内独立写死（与生产常量另行比对）


def _code(r):
    return r[0]


def _amt(r):
    return r[1]


def _gold(rows, amount=_amt):
    """独立金标准：(叶子合计, {(父码, 差额)})；rows 为同一取数集合。"""
    codes = {r[0] for r in rows}

    def is_parent(c):
        return any(o != c and o.startswith(c) for o in codes)

    leaves = [r for r in rows if not is_parent(r[0])]
    warns = set()
    for p in sorted(c for c in codes if is_parent(c)):
        diff = sum((amount(r) for r in rows if r[0] == p), D(0)) - sum(
            (amount(r) for r in leaves if r[0].startswith(p)), D(0))
        if abs(diff) > _TOL:
            warns.add((p, diff))
    return sum((amount(r) for r in leaves), D(0)), warns


# ── 纯函数：PBT ───────────────────────────────────────────────────────────────

_ROOTS = ("1001", "1122", "1231", "1405", "2221")
_CENTS = st.integers(-10**8, 10**8).map(lambda n: D(n).scaleb(-2))
_DELTAS = st.sampled_from([D(0), D("0.004"), D("0.005"), D("-0.005"), D("0.0051"), D("-0.006"), D("0.01"), D(10)])


@st.composite
def _forests(draw, *, consistent: bool):
    """随机科目树 → [(码, 金额)]；码按「根 4 位 + 若干段（'-dd' 或 'dd'）」生成 ⇒ 字符串前缀关系 = 树上祖先关系。
    consistent=True：父行 = 其下叶子合计；否则父行 = 叶子合计 + 随机偏差（含阈值两侧）。"""
    rows: list[tuple[str, Decimal]] = []

    def node(code: str, depth: int) -> Decimal:
        width = draw(st.integers(0, 3)) if depth < 3 else 0
        leaf_sum = sum((node(f"{code}{draw(st.sampled_from(['-', '']))}{i:02d}", depth + 1) for i in range(1, width + 1)),
                       D(0))
        if not width:
            amount = draw(_CENTS)
            rows.append((code, amount))
            return amount
        rows.append((code, leaf_sum if consistent else leaf_sum + draw(_DELTAS)))
        return leaf_sum

    for root in draw(st.lists(st.sampled_from(_ROOTS), min_size=1, max_size=4, unique=True)):
        node(root, 0)
    return draw(st.permutations(rows))


@settings(max_examples=5, deadline=None)
@given(_forests(consistent=True))
def test_pbt_leaf_sum_identity(rows):
    """父行 = 下级合计的一致科目树：叶子合计 = 各根行金额之和，且无告警（层级多深都一样）。"""
    sel = select_leaves(rows, _code, _amt)
    roots = [r for r in rows if r[0] in _ROOTS]
    assert sel.total == sum((r[1] for r in roots), D(0))
    assert sel.warnings == []


@settings(max_examples=5, deadline=None)
@given(_forests(consistent=False))
def test_pbt_parent_never_counted_and_warning_threshold(rows):
    """选中行恰为叶子（父行不计入）、合计 = 叶子和；告警恰为 |父 − 其下叶子和| > 0.005 的父码，差额与金标准一致。"""
    sel = select_leaves(rows, _code, _amt, column="期末余额", scope="2025 年度试算表")
    codes = {r[0] for r in rows}
    assert all(not any(o != r[0] and o.startswith(r[0]) for o in codes) for r in sel.rows)
    total, warns = _gold(rows)
    assert sel.total == total
    assert {(w["code"], w["diff"]) for w in sel.warnings} == warns
    for w in sel.warnings:
        assert w["diff"] == w["parent"] - w["leaf_sum"]
        assert w["code"] in w["message"] and "（期末余额）" in w["message"]


# ── 纯函数：示例与边界 ─────────────────────────────────────────────────────────

def test_requirement_fixture_parent_100_children_40_50():
    """需求 4.2 / 4.3 夹具：父 1231 = 100、子 40 + 50 ⇒ 90，告警含「1231」与「10.00」。"""
    sel = select_leaves([("1231", D(100)), ("1231-01", D(40)), ("1231-02", D(50))], _code, _amt)
    assert sel.total == D(90) and [r[0] for r in sel.rows] == ["1231-01", "1231-02"]
    (w,) = sel.warnings
    assert (w["code"], w["parent"], w["leaf_sum"], w["diff"]) == ("1231", D(100), D(90), D(10))
    assert "1231" in w["message"] and "10.00" in w["message"]


def test_only_children_and_same_code_rows():
    """只有子科目 ⇒ 子科目和；同码多行（多公司编码）互不为父子、全部计入。"""
    assert select_leaves([("1122-01", D(3)), ("1122-02", D(4))], _code, _amt).total == D(7)
    sel = select_leaves([("1002", D(5)), ("1002", D(6))], _code, _amt)
    assert sel.total == D(11) and len(sel.rows) == 2 and sel.warnings == []


@pytest.mark.parametrize(("delta", "warned"), [
    (D("0.005"), False), (D("-0.005"), False), (D("0.0051"), True), (D("-0.006"), True), (D("0.01"), True)])
def test_warning_threshold_boundary(delta, warned):
    sel = select_leaves([("1231", D(90) + delta), ("1231-01", D(40)), ("1231-02", D(50))], _code, _amt)
    assert bool(sel.warnings) is warned
    assert LEAF_DIFF_TOLERANCE == _TOL


def test_nested_parents_warn_each_level():
    rows = [("1231", D(100)), ("1231-01", D(40)), ("1231-01-01", D(30)), ("1231-02", D(50))]
    sel = select_leaves(rows, _code, _amt)
    assert sel.total == D(80)
    assert {(w["code"], w["diff"]) for w in sel.warnings} == {("1231", D(20)), ("1231-01", D(10))}
    assert leaf_code_set(r[0] for r in rows) == {"1231-01-01", "1231-02"}


# ── formula_warnings：收集嵌套 ────────────────────────────────────────────────

def _w(code):
    return {"code": code, "message": f"告警 {code}"}


def test_emit_without_collector_only_logs(caplog):
    with caplog.at_level("INFO", logger="app.services.formula_warnings"):
        formula_warnings.emit(_w("A"))
    assert "告警 A" in caplog.text


def test_collect_nesting_and_dedupe():
    with formula_warnings.collect() as outer:
        formula_warnings.emit(_w("O1"))
        with formula_warnings.collect() as inner:
            formula_warnings.emit([_w("I1"), _w("I1")])
        formula_warnings.emit(_w("O2"))
    formula_warnings.emit(_w("after"))
    assert [w["code"] for w in inner] == ["I1"]
    assert [w["code"] for w in outer] == ["O1", "I1", "O2"]
    target = ["告警 O1"]
    assert formula_warnings.merge_into(target, outer) == ["告警 O1", "告警 I1", "告警 O2"]


@pytest.mark.asyncio
async def test_collect_spans_awaits_and_gather():
    async def fetch(code):
        await asyncio.sleep(0)
        formula_warnings.emit(_w(code))

    with formula_warnings.collect() as got:
        await fetch("A")
        await asyncio.gather(fetch("B"), fetch("C"))
    assert sorted(w["code"] for w in got) == ["A", "B", "C"]


# ── 父子并存夹具：表驱动 F8 全部取数函数 ─────────────────────────────────────

#: (码, 审定, 年初, 未审, AJE)；1231 父 ≠ 子和（期末差 10、年初差 5、未审差 10）；1122 只有子科目；
#: 1403 父 ≠ 子和（差 3）；1499（区间止码）有下级 1499-01（差 1）；1501 在区间外
_ROWS = (
    ("1231", 100, 30, 95, 5), ("1231-01", 40, 10, 38, 2), ("1231-02", 50, 15, 47, 3),
    ("1122-01", 3, 1, 3, 0), ("1122-02", 4, 2, 4, 0),
    ("1403", 20, 6, 20, 0), ("1403-01", 8, 2, 8, 0), ("1403-02", 9, 3, 9, 0),
    ("1405", 7, 1, 7, 0), ("1499", 6, 0, 6, 0), ("1499-01", 5, 0, 5, 0), ("1501", 1000, 0, 1000, 0),
)
_COL = {"期末余额": 1, "年初余额": 2, "未审数": 3, "AJE调整": 4}


def _amount_of(col):
    if col == "本期发生额":
        return lambda r: D(r[1]) - D(r[2])
    return lambda r: D(r[_COL[col]])


def _wide(target):
    if "~" in target:
        start, end = target.split("~")
        return [r for r in _ROWS if start <= r[0] and (r[0] <= end or r[0].startswith(end))]
    return [r for r in _ROWS if r[0].startswith(target)]


def _expect(target, col):
    total, warns = _gold(_wide(target), _amount_of(col))
    return total, {(c, col, d) for c, d in warns}


_MSG = re.compile(r"科目 (\S+)（(.+?)）本级金额")


def _seen(bucket):
    return {(w["code"], _MSG.search(w["message"]).group(2), w["diff"]) for w in bucket}


@pytest_asyncio.fixture
async def tb_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[Project.__table__, TrialBalance.__table__, LedgerDataset.__table__]))
    pid, other = uuid.uuid4(), uuid.uuid4()
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        for p in (pid, other):
            db.add(Project(id=p, name=f"叶子口径_{p.hex[:6]}", client_name="叶子口径"))
        await db.flush()

        def tb(project, year, code, audited, opening, unadjusted, aje, *, deleted=False):
            db.add(TrialBalance(
                project_id=project, year=year, company_code="001", standard_account_code=code, account_name=code,
                account_category=AccountCategory.asset, audited_amount=D(audited), opening_balance=D(opening),
                unadjusted_amount=D(unadjusted), aje_adjustment=D(aje), rje_adjustment=D(0), is_deleted=deleted))

        for row in _ROWS:
            tb(pid, YEAR, *row)
        tb(pid, YEAR - 1, "1231-01", 999, 0, 999, 0)          # 上年
        tb(other, YEAR, "1231-01", 777, 0, 777, 0)            # 他项目
        tb(pid, YEAR, "1231-03", 555, 0, 555, 0, deleted=True)  # 已删除
        await db.commit()
        yield db, pid
    await engine.dispose()


def _report(db, pid, *, opening=False, unadjusted=False):
    parser = ReportFormulaParser(db, pid, YEAR)
    parser._use_opening, parser._use_unadjusted = opening, unadjusted
    return parser


async def _preloaded(db, pid, targets, col):
    return (await formula_preloader._load_tb(db, pid, YEAR, set(targets)))[targets[0]][col]


async def _push_loaded(db, pid, target, col):
    return (await load_tb_audited(db, pid, YEAR, [target])).tb_data[target][col]


#: (取数函数, 调用, 取数码, 列, 告警按哪一列比)
_CASES = [
    ("report.TB", lambda db, pid, t, c: _report(db, pid).resolve_tb(t, c), "1231", "期末余额", None),
    ("report.TB", lambda db, pid, t, c: _report(db, pid).resolve_tb(t, c), "1231", "本期发生额", None),
    ("report.TB", lambda db, pid, t, c: _report(db, pid).resolve_tb(t, c), "1122", "期末余额", None),
    ("report.TB.opening", lambda db, pid, t, c: _report(db, pid, opening=True).resolve_tb(t, "期末余额"),
     "1231", "年初余额", None),
    ("report.TB.unadjusted", lambda db, pid, t, c: _report(db, pid, unadjusted=True).resolve_tb(t, "期末余额"),
     "1231", "未审数", None),
    ("report.SUM_TB", lambda db, pid, t, c: _report(db, pid).resolve_sum(t, c), "1400~1499", "期末余额", None),
    ("TrialBalanceResolver.TB", lambda db, pid, t, c: TrialBalanceResolver(db, pid, YEAR).resolve_tb(t, c),
     "1231", "期末余额", None),
    ("TrialBalanceResolver.TB.unadjusted",
     lambda db, pid, t, c: TrialBalanceResolver(db, pid, YEAR, use_unadjusted=True).resolve_tb(t, "审定数"),
     "1231", "未审数", None),
    ("TrialBalanceResolver.SUM_TB", lambda db, pid, t, c: TrialBalanceResolver(db, pid, YEAR).resolve_sum(t, c),
     "1400~1499", "年初余额", None),
    ("preloader._load_tb", lambda db, pid, t, c: _preloaded(db, pid, [t], c), "1231", "期末余额", "*"),
    ("preloader._load_tb", lambda db, pid, t, c: _preloaded(db, pid, [t], c), "1231", "本期发生额", "*"),
    ("preloader._load_tb", lambda db, pid, t, c: _preloaded(db, pid, [t], c), "1231", "未审数", "*"),  # ADR-FHIC-18
    ("preloader._load_tb.range", lambda db, pid, t, c: _preloaded(db, pid, [t], c), "1400~1499", "期末余额", "*"),
    ("push.load_tb_audited", lambda db, pid, t, c: _push_loaded(db, pid, t, c), "1231", "期末余额", "*"),
    ("push.load_tb_audited", lambda db, pid, t, c: _push_loaded(db, pid, t, c), "1122", "年初余额", "*"),
    ("strict._resolve_tb", lambda db, pid, t, c: wp_formula_eval_service._resolve_tb(db, pid, YEAR, t, c),
     "1231", "期末余额", None),
    ("strict._resolve_tb", lambda db, pid, t, c: wp_formula_eval_service._resolve_tb(db, pid, YEAR, t, c),
     "1231", "未审数", None),
    ("strict._resolve_sum_tb", lambda db, pid, t, c: wp_formula_eval_service._resolve_sum_tb(db, pid, YEAR, t, c),
     "1400~1499", "期末余额", None),
]
#: 一次取多列的取数点（预载 / 推送）告警覆盖各自存储的余额列，「本期发生额」由两列相减、不单独告警
_MULTI_COLUMNS = {"preloader": ("期末余额", "年初余额", "未审数", "AJE调整"), "push": ("期末余额", "年初余额")}


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "call", "target", "col", "warn_cols"), _CASES,
                         ids=[f"{c[0]}[{c[2]}|{c[3]}]" for c in _CASES])
async def test_every_fetch_function_sums_leaves(tb_db, name, call, target, col, warn_cols):
    """F8 全部取数函数：父子并存 ⇒ 值 = 叶子和（父行不计入），父子不符告警被 emit（码、列、差额与金标准一致）。"""
    db, pid = tb_db
    with formula_warnings.collect() as bucket:
        value = await call(db, pid, target, col)
    expected, _ = _expect(target, col)
    assert value == expected, f"{name}: {value} != 叶子和 {expected}"
    cols = _MULTI_COLUMNS[name.split(".")[0]] if warn_cols else (col,)
    assert _seen(bucket) == set().union(*(_expect(target, c)[1] for c in cols))


def test_fixture_is_not_vacuous():
    """夹具确有父子不符：前缀全加 ≠ 叶子和（守卫非空转）。"""
    assert sum((D(r[1]) for r in _wide("1231")), D(0)) == D(190) != _expect("1231", "期末余额")[0] == D(90)
    assert _expect("1400~1499", "期末余额") == (D(29), {("1403", "期末余额", D(3)), ("1499", "期末余额", D(1))})


@pytest.mark.asyncio
async def test_evaluate_formula_result_merges_leaf_warnings(tb_db):
    """结果合并点：L2 ``evaluate_formula_result`` 的 ``FormulaResult.warnings`` 含科目码与差额，值按叶子。"""
    db, pid = tb_db
    result = await evaluate_formula_result(
        "TB('1231','期末余额') - TB('1231-01','期末余额')", resolver=ReportFormulaParser(db, pid, YEAR))
    assert result.ok and result.value == D(50)
    assert any("1231" in w and "10.00" in w and "（期末余额）" in w for w in result.warnings), result.warnings
    clean = await evaluate_formula_result("TB('1122','期末余额')", resolver=TrialBalanceResolver(db, pid, YEAR))
    assert clean.value == D(7) and clean.warnings == []
