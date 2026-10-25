"""合并报表行级计算内核（spec consol-elimination-single-source-push 任务 2，design §四 / §十二）。

- P2（hypothesis）：逐节点逐科目 ``个别数 + 调整 + 权益抵销 + 往来交易抵销 = 合并数``，且合并数 = 差额表合并数；
  各度量在汇总节点 = Σ 直接子节点。
- P3（hypothesis + 真库公式快照）：线性行 ``Σ 子节点行值 = 汇总节点行值``（到分四舍五入，容差 0.01）；
  四个分解度量的行值之和 = 合并数行值。
- P5：``TB('1122')`` 含 ``112201``，与单体 ``TrialBalanceResolver`` 同值（真 SQLite 对照）；``SUM_TB`` 含
  区间终点科目的子级（与 L1 内核 ``_handle_sum_tb`` 同口径，单体 ``resolve_sum`` 是字符串区间、不含，已知差异）。
- P9：年初列、非损益类科目的本期发生额、不取数函数、非线性分解、引用留空行 ⇒ 留空并给原因，不静默 0。
- 公式形态：规范化（宽松空格、负号接负值）、线性判定、行引用收集、口径解析。
"""

from __future__ import annotations

import asyncio
import json
import uuid
import zlib
from decimal import Decimal
from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from app.services.consol_calc_basis import (
    MEASURE_ADJUSTMENT,
    MEASURE_CONSOLIDATED,
    MEASURE_ELIM_EQUITY,
    MEASURE_ELIM_TRADE,
    MEASURE_INDIVIDUAL,
    MEASURES,
    build_calc_basis,
    node_measures,
    node_values,
)
from app.models.audit_platform_models import AccountCategory
from app.services.consol_report_values import (
    BasisResolver,
    ReportRow,
    analyze_formula,
    canonical_formula,
    consol_standard,
    is_period_account,
    node_report,
    report_values,
    validate_linear,
)
from app.services.consol_tree_service import iter_nodes
from app.services.report_engine import evaluate_formula
from tests.test_consol_calc_basis import NAME, Y, _targeted, _world, entry, rec

D = Decimal
SNAPSHOT = Path(__file__).parent / "fixtures" / "consol_report_config_snapshot.json"


def run(coro):
    return asyncio.run(coro)


def rows_of(*specs) -> list[ReportRow]:
    """(报表类型, 行次, 行号, 公式) → ReportRow。"""
    return [ReportRow(t, code, code, n, f) for t, code, n, f in specs]


def amounts(values: dict) -> dict:
    return {k: v.amount for k, v in values.items()}


# ─────────────────────────────── 公式形态 ───────────────────────────────


class TestFormulaShape:
    def test_canonical_brackets_and_strips_spaces(self):
        assert canonical_formula("TB( '1122' , '期末余额' )") == "(TB('1122','期末余额'))"
        assert canonical_formula("TB ('1122','期末余额')") == "(TB('1122','期末余额'))"
        assert canonical_formula("SUM_TB('6001 ~ 6099', '本期发生额')") == "(SUM_TB('6001~6099','本期发生额'))"
        # 不改 ROW / 其他函数；不误伤函数名后缀为 TB 的调用
        assert canonical_formula("ROW('BS-002') - XTB('1','2')") == "ROW('BS-002') - XTB('1','2')"

    @pytest.mark.parametrize("formula, reason", [
        ("TB('1001','期末余额') + TB('1002','期末余额')", None),
        ("TB('1601','期末余额') - TB('1602','期末余额')", None),
        ("-TB('1602','期末余额')", None),
        ("TB('1001','期末余额') * 2 - TB('1002','期末余额') / 4", None),
        ("ROW('BS-002') + SUM_ROW('BS-003','BS-005')", None),
        ("TB('1001','期末余额') * '2'", None),                       # 文本数字与内核同口径按数字
        ("ABS(TB('1001','期末余额'))", "含 ABS()"),
        ("TB('1001','期末余额') * TB('1002','期末余额')", "两个取数项相乘"),
        ("100 / TB('1001','期末余额')", "除以取数项"),
        ("TB('1001','期末余额') + 1", "含常数项 1"),
    ])
    def test_linearity(self, formula, reason):
        shape = analyze_formula(formula)
        assert shape.error is None
        assert shape.nonlinear == reason
        assert validate_linear(formula) == reason

    @pytest.mark.parametrize("formula, fragment", [
        ("PREV('1001','期末余额')", "PREV() 在合并报表中不取数"),
        ("ADJ('1001','aje_net')", "ADJ() 在合并报表中不取数"),
        ("FOO(1)", "FOO() 未注册"),
        ("IF(1)", "IF() 参数个数不对"),
        ("TB('1001','期末余额') > 0", "勾稽校验式"),
        ("TB('1001','期末余额') / 0", "除数为 0"),
        ("TB('1001~1002','期末余额')", "含「~」"),
        ("SUM_TB('1001','期末余额')", "应写成「起始~结束」"),
        ("REPORT('BS-002','上期')", "只有本期值"),
        ("TB('1001','期末余额') 加 TB('1002','期末余额')", "无法识别的内容「加」"),
        # 全角减号被内核词法跳过 ⇒ 单体编排静默算成 A + B（实测 130 而非 70）
        ("TB('1001','期末余额') +－ TB('1002','期末余额')", "无法识别的内容「－」"),
        ("TB('1001','期末余额'", "无法解析"),
    ])
    def test_errors(self, formula, fragment):
        shape = analyze_formula(formula)
        assert shape.error and fragment in shape.error, shape

    def test_collects_references(self):
        shape = analyze_formula("ROW('A') - REPORT('B','本期') + SUM_ROW('C','E') + TB('1122','期末余额')"
                                " + SUM_TB('6001~6099','本期发生额')")
        assert shape.row_refs == ("A", "B")
        assert shape.row_ranges == (("C", "E"),)
        assert shape.tb_codes == ("1122",) and shape.tb_ranges == (("6001", "6099"),)

    @pytest.mark.parametrize("template_type, standard", [
        ("listed", "listed_consolidated"), (" LISTED ", "listed_consolidated"),
        ("soe", "soe_consolidated"), (None, "soe_consolidated"), ("", "soe_consolidated"),
        ("enterprise", "soe_consolidated"),
    ])
    def test_consol_standard(self, template_type, standard):
        assert consol_standard(template_type) == standard


# ─────────────────────────────── 取数与行求值 ───────────────────────────────


class TestResolverAndRows:
    def test_prefix_sum_and_range_with_end_children(self):
        values = {"1122": D("10"), "112201": D("2.5"), "11221": D("1"), "1123": D("99"),
                  "6001": D("5"), "6099": D("7"), "609901": D("1"), "6101": D("100")}

        async def go():
            r = BasisResolver(values)
            r.begin_row()
            return (await r.resolve_tb("1122", "期末余额"), await r.resolve_sum("6001~6099", "本期发生额"),
                    await r.resolve_tb("6001~6099", "本期发生额"), r.reasons)

        tb, rng, inner, reasons = run(go())
        assert tb == D("13.50")                  # 1122 + 112201 + 11221，不含 1123
        assert rng == D("13.00")                 # 6001 + 6099 + 609901（区间终点子级），不含 6101
        assert inner == D(0) and reasons == []   # 编排层 TB 正则命中 SUM_TB 内部 ⇒ 0 且不记原因

    def test_sum_tb_bad_column_reported_once(self):
        """SUM_TB 内部被 TB 正则重复命中的那一次不另记原因：一个错误只报一条。"""
        rows = rows_of(("balance_sheet", "BS-1", 1, "SUM_TB('6001~6099','乱写')"))
        got = run(report_values(rows, {"6001": D(1)}))["BS-1"]
        assert got.amount is None and got.reason == "SUM_TB('6001~6099')：列名「乱写」未注册"

    @pytest.mark.parametrize("code, category, expect", [
        ("6001", "revenue", True), ("6401", AccountCategory.expense, True), ("5001", None, True),
        ("4001", "expense", False),          # 旧表成本类 / 新表权益类：都有年初数
        ("3102", None, False), ("1122", "asset", False), ("6001", "equity", False),
    ])
    def test_period_account(self, code, category, expect):
        assert is_period_account(code, category) is expect

    def test_values_quantized_to_cents(self):
        """取数值先到分：① 极小值 ``str()`` 成 ``1E-7``，内核词法不认 ⇒ 整条公式解析失败 = 静默 0；
        ② 每个科目值先到分再相加（与计算口径逐分落库一致），否则 0.005 + 0.005 到分后是 0.01 而非 0.02。"""
        rows = rows_of(("balance_sheet", "BS-1", 1, "TB('1001','期末余额') + TB('1002','期末余额')"))
        assert amounts(run(report_values(rows, {"1001": D("1E-7"), "1002": D("5")}))) == {"BS-1": D("5.00")}
        assert amounts(run(report_values(rows, {"1001": D("0.005"), "1002": D("0.005")}))) == {"BS-1": D("0.02")}

    def test_negative_values_behind_unary_minus(self):
        """``-TB`` 取到负值：未加括号时拼成 ``--7.00`` 解析失败 = 静默 0（变异证明见 canonical 用例）。"""
        rows = rows_of(
            ("balance_sheet", "BS-1", 1, "-TB('1602','期末余额')"),
            ("balance_sheet", "BS-2", 2, "TB('1601','期末余额') - TB('1602','期末余额')"),
        )
        got = amounts(run(report_values(rows, {"1601": D("50"), "1602": D("-7")})))
        assert got == {"BS-1": D("7.00"), "BS-2": D("57.00")}

    def test_cross_report_row_cache_and_order(self):
        rows = rows_of(
            ("cash_flow_supplement", "CFSS-1", 1, "ROW('IS-9') + ROW('BS-3')"),
            ("income_statement", "IS-9", 9, "ROW('IS-1') - ROW('IS-2')"),
            ("income_statement", "IS-1", 1, "SUM_TB('6001~6099','本期发生额')"),
            ("income_statement", "IS-2", 2, "TB('6401','本期发生额')"),
            ("balance_sheet", "BS-3", 3, "SUM_ROW('BS-1','BS-2')"),
            ("balance_sheet", "BS-1", 1, "TB('1001','期末余额')"),
            ("balance_sheet", "BS-2", 2, "TB('1122','期末余额')"),
            ("balance_sheet", "BS-0", 0, None),
        )
        got = run(report_values(rows, {"1001": D(100), "1122": D(20), "6001": D(300), "6401": D(120)}))
        assert amounts(got) == {
            "BS-0": D(0), "BS-1": D("100.00"), "BS-2": D("20.00"), "BS-3": D("120.00"),
            "IS-1": D("300.00"), "IS-2": D("120.00"), "IS-9": D("180.00"), "CFSS-1": D("300.00"),
        }
        assert got["BS-0"].has_formula is False and all(v.has_formula for k, v in got.items() if k != "BS-0")

    def test_p9_blank_rows_have_reasons(self):
        """P9：取不到数的行留空（None）并说明原因，引用它的行也留空；不静默给 0。"""
        rows = rows_of(
            ("balance_sheet", "BS-1", 1, "TB('1702','期末余额') - TB('1702','年初余额')"),
            ("balance_sheet", "BS-2", 2, "TB('1703','年初余额')"),             # 全树无 1703 ⇒ 真 0
            ("balance_sheet", "BS-3", 3, "TB('1001','未审数')"),               # 已注册但不在口径内
            ("balance_sheet", "BS-4", 4, "TB('1001','乱写的列')"),             # 未注册列
            ("balance_sheet", "BS-5", 5, "ROW('BS-1') + ROW('BS-2')"),
            ("balance_sheet", "BS-6", 6, "ROW('BS-9')"),                       # 排在后面
            ("balance_sheet", "BS-7", 7, "ROW('NOPE')"),                        # 不存在
            ("balance_sheet", "BS-8", 8, "SUM_ROW('BS-1','BS-2')"),             # 区间含留空行
            ("balance_sheet", "BS-9", 9, "TB('1001','期末余额')"),
            ("income_statement", "IS-1", 1, "TB('3102','本期发生额')"),         # 权益类没有本期发生额口径
            ("income_statement", "IS-2", 2, "PREV('1001','期末余额')"),
            ("income_statement", "IS-3", 3, "ROW('IS-3')"),                     # 自引用
        )
        got = run(report_values(rows, {"1702": D(4), "1001": D(1), "3102": D(3)}))
        assert got["BS-2"].amount == D("0.00") and got["BS-9"].amount == D("1.00")
        expect = {
            "BS-1": "年初余额", "BS-3": "未审数", "BS-4": "未注册", "BS-5": "BS-1 留空", "BS-6": "尚未计算",
            "BS-7": "NOPE 不存在", "BS-8": "BS-1 留空", "IS-1": "3102 不是损益类", "IS-2": "PREV",
            "IS-3": "循环引用",
        }
        for code, fragment in expect.items():
            assert got[code].amount is None and fragment in (got[code].reason or ""), (code, got[code])

    def test_period_column_judged_on_whole_tree_accounts(self):
        """「本期发生额」能否取按全树科目判定：某度量里恰好没有非损益科目也要一致留空（五度量判定一致）。"""
        rows = rows_of(("income_statement", "IS-1", 1, "TB('3102','本期发生额')"))
        assert run(report_values(rows, {}))["IS-1"].amount == D("0.00")          # 全树无 3102 ⇒ 真 0
        cats = {"3102": "equity"}
        got = run(report_values(rows, {}, categories=cats))["IS-1"]
        assert got.amount is None and "3102" in got.reason

    def test_require_linear_blanks_only_decomposition(self):
        rows = rows_of(("balance_sheet", "BS-1", 1, "ABS(TB('1001','期末余额'))"))
        values = {"1001": D(-5)}
        full = run(report_values(rows, values))["BS-1"]
        part = run(report_values(rows, values, require_linear=True))["BS-1"]
        assert (full.amount, full.linear) == (D("5.00"), False)
        assert part.amount is None and "不能按列分解" in part.reason


# ─────────────────────────────── P5：与单体前缀口径同值（真 SQLite） ───────────────────────────────


async def _p5_run() -> None:
    import tests.conftest  # noqa: F401  注册全部模型
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.audit_platform_models import TrialBalance
    from app.models.base import Base
    from app.services.amount_resolver import TrialBalanceResolver

    pid = uuid.uuid4()
    data = {"1122": D("100.10"), "112201": D("20.02"), "11220101": D("3.03"), "1123": D("7"),
            "6001": D("50"), "600101": D("5"), "6051": D("9"), "6099": D("1")}
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            from app.services.account_chart_service import _infer_category

            for code, amount in data.items():
                db.add(TrialBalance(id=uuid.uuid4(), project_id=pid, year=Y, company_code="001",
                                    standard_account_code=code, account_category=_infer_category(code, ""),
                                    audited_amount=amount, opening_balance=D(0)))
            await db.commit()
            single = TrialBalanceResolver(db, pid, Y)
            consol = BasisResolver(data)
            for code in ("1122", "112201", "1123", "11", "6001"):
                assert await consol.resolve_tb(code, "期末余额") == await single.resolve_tb(code, "期末余额"), code
            # 损益类无年初数 ⇒ 单体「本期发生额 = 审定 − 年初」与合并「= 审定」同值
            assert await consol.resolve_tb("6001", "本期发生额") == await single.resolve_tb("6001", "本期发生额")
            # 区间不含终点子级时两者同值；终点科目有子级时合并口径与 L1 内核一致（含子级），单体不含（已知差异）
            assert await consol.resolve_sum("6001~6051", "本期发生额") == await single.resolve_sum(
                "6001~6051", "本期发生额") == D("64.00")
            assert await consol.resolve_sum("1122~1122", "期末余额") == D("123.15")
            assert await single.resolve_sum("1122~1122", "期末余额") == D("100.10")
    finally:
        await engine.dispose()


def test_p5_prefix_parity_with_single_entity_resolver():
    run(_p5_run())


def test_p5_range_parity_with_l1_kernel():
    """合并 ``SUM_TB`` 区间口径 = L1 内核 ``_handle_sum_tb``（同一份科目数据两种入口求值）。"""
    from app.services.formula_engine import FormulaContext, execute

    data = {"1400": D("1"), "1401": D("2"), "140101": D("3"), "1499": D("4"), "149901": D("5"), "1500": D("6")}
    ctx = FormulaContext(tb_data={k: {"期末余额": v} for k, v in data.items()})
    for rng in ("1401~1499", "1400~1499", "14~14"):
        kernel = execute(f"SUM_TB('{rng}','期末余额')", ctx).value
        rows = rows_of(("balance_sheet", "BS-1", 1, f"SUM_TB('{rng}','期末余额')"))
        assert run(report_values(rows, data))["BS-1"].amount == kernel, rng


# ─────────────────────────────── P2 / P3：随机集团 ───────────────────────────────


def _snapshot_rows(standard: str) -> list[ReportRow]:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return [ReportRow(t, code, name, n, f) for t, code, n, f, name in data[standard]]


def _p3_rows() -> list[ReportRow]:
    """覆盖测试科目的线性公式（取数、减、乘除常数、同表 / 跨表 ROW、SUM_ROW）。"""
    return rows_of(
        ("balance_sheet", "BS-1", 1, "TB('1001','期末余额') + TB('1122','期末余额')"),
        ("balance_sheet", "BS-2", 2, "TB('1601','期末余额') - TB('1602','期末余额')"),
        ("balance_sheet", "BS-3", 3, "TB('2202','期末余额') * 3 - TB('4001','期末余额') / 4"),
        ("balance_sheet", "BS-4", 4, "SUM_ROW('BS-1','BS-3') - ROW('BS-2')"),
        ("income_statement", "IS-1", 1, "SUM_TB('6001~6099','本期发生额') - TB('6401','本期发生额')"),
        ("cash_flow_supplement", "CFSS-1", 1, "ROW('IS-1') + ROW('BS-4') - TB('4201','期末余额')"),
    )


def _assert_p2(basis) -> dict:
    measures = node_measures(basis)
    worksheet = node_values(basis)
    for node in iter_nodes(basis.tree):
        m = measures[node.node_key]
        for a in basis.accounts:
            parts = sum((m[k].get(a, D(0)) for k in (
                MEASURE_INDIVIDUAL, MEASURE_ADJUSTMENT, MEASURE_ELIM_EQUITY, MEASURE_ELIM_TRADE)), D(0))
            assert parts == m[MEASURE_CONSOLIDATED].get(a, D(0)), (node.node_key, a)
            assert m[MEASURE_CONSOLIDATED].get(a, D(0)) == worksheet[node.node_key][a].consolidated_amount
        if node.children:
            for k in MEASURES:
                for a in basis.accounts:
                    assert m[k].get(a, D(0)) == sum(
                        (measures[c.node_key][k].get(a, D(0)) for c in node.children), D(0)), (node.node_key, k, a)
        assert all(v != 0 for amounts_ in m.values() for v in amounts_.values()), "只存非零"
    return measures


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(world=_world())
def test_p2_measure_identity(world):
    records, root, tb, entries, tree = _targeted(world)
    _assert_p2(build_calc_basis(tree, Y, tb, entries))


def _p3_check(basis, rows, *, exact: bool) -> None:
    """``exact``：公式系数全为整数（真库公式只有 + −）⇒ 全程到分精确相等；
    含乘除常数时每个行值各自到分四舍五入 ⇒ 容差为「参与相加的行值个数 × 半分」。"""
    measures = _assert_p2(basis)
    cats = basis.categories

    async def go():
        return {n.node_key: await node_report(rows, measures[n.node_key], categories=cats)
                for n in iter_nodes(basis.tree)}

    reports = run(go())
    half_cent = D("0.005")
    for node in iter_nodes(basis.tree):
        rep = reports[node.node_key]
        for row in rows:
            code = row.row_code
            vals = {k: rep[k][code] for k in MEASURES}
            cons = vals[MEASURE_CONSOLIDATED]
            if cons.amount is None:
                # 留空判定按全树科目 ⇒ 五个度量一致留空
                assert all(v.amount is None for v in vals.values()), (node.node_key, code, vals)
                continue
            if not cons.linear:
                assert all(vals[k].amount is None for k in MEASURES if k != MEASURE_CONSOLIDATED)
                continue
            assert all(v.amount is not None for v in vals.values()), (node.node_key, code, vals)
            parts = sum((vals[k].amount for k in MEASURES if k != MEASURE_CONSOLIDATED), D(0))
            assert abs(parts - cons.amount) <= (D(0) if exact else half_cent * 5), (node.node_key, code)
            if node.children:
                for k in MEASURES:
                    kids = sum((reports[c.node_key][k][code].amount for c in node.children), D(0))
                    tol = D(0) if exact else half_cent * (len(node.children) + 1)
                    assert abs(kids - vals[k].amount) <= tol, (node.node_key, k, code, kids, vals[k].amount)


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(world=_world())
def test_p3_linear_rows_decompose_over_children(world):
    records, root, tb, entries, tree = _targeted(world)
    _p3_check(build_calc_basis(tree, Y, tb, entries), _p3_rows(), exact=False)


@pytest.mark.parametrize("standard", ["soe_consolidated", "listed_consolidated"])
def test_p3_real_formula_snapshot(standard):
    """真库公式快照（``fixtures/consol_report_config_snapshot.json``）在固定集团上逐行可分解。

    快照 = 2026-09-30 真库 ``report_config``；全部有公式的行都是线性（本用例同时守住这一点：
    若有人在合并口径写入非线性公式，这里先红，差额表需要显式标注的范围随之变化）。
    """
    rows = _snapshot_rows(standard)
    with_formula = [r for r in rows if (r.formula or "").strip()]
    assert with_formula and all(analyze_formula(r.formula).error is None for r in with_formula)
    assert [r.row_code for r in with_formula if not analyze_formula(r.formula).linear] == []

    g_c, g_s = rec("G", "某集团", "consolidated"), rec("G", "某集团")
    a_s = rec("A", "甲公司", parent="G", relation="subsidiary")
    b_s = rec("B", "乙公司", parent="G", relation="subsidiary")
    gb = rec("GB", "某集团分公司", parent="G", relation="branch")
    from app.services.consol_calc_basis import TbRow
    from app.services.consol_group_tree import derive_group_tree

    tree = derive_group_tree([g_c, g_s, a_s, b_s, gb], g_c, Y).root
    codes = sorted({c for r in with_formula for c in analyze_formula(r.formula).tb_codes})
    codes += sorted({a for r in with_formula for a, _b in analyze_formula(r.formula).tb_ranges})
    # 金额确定性（``hash()`` 对字符串逐进程加盐，不能用）
    tb = [TbRow(p.id, code + sfx, None, None, D(zlib.crc32(f"{p.company_code}/{code}{sfx}".encode()) % 100000) / 100)
          for p in (g_s, a_s, b_s, gb) for code in codes for sfx in ("", "01")]
    lines = [("1122", "300", "0"), ("2202", "0", "300")]
    entries = [entry(g_c.id, "E1", lines, entry_type="internal_ar_ap"),
               entry(g_c.id, "E2", [("6001", "80", "0"), ("6401", "0", "80")], entry_type="internal_trade"),
               entry(g_c.id, "E3", [("4001", "500", "0"), ("1511", "0", "500")], entry_type="equity"),
               entry(g_c.id, "E4", [("6602", "12", "0"), ("2241", "0", "12")], entry_type="other"),
               entry(g_c.id, "E5", [("1601", "9", "0"), ("6115", "0", "9")], branch="G")]
    basis = build_calc_basis(tree, Y, tb, entries)
    _p3_check(basis, rows, exact=True)

    root = run(node_report(rows, node_measures(basis)[tree.node_key], categories=basis.categories))
    consolidated = root[MEASURE_CONSOLIDATED]
    blanks = {code: v.reason for code, v in consolidated.items() if v.amount is None}
    expected_blank = {"IS-030", "IS-031", "CFSS-007", "CFSS-008"} | (
        {"IS-053"} if standard == "soe_consolidated" else set())
    assert set(blanks) == expected_blank, blanks
    assert "年初余额" in blanks["CFSS-007"] and "3102 不是损益类" in blanks["IS-030"]
    assert blanks["IS-031"] == "引用的行 IS-030 留空"
    # 测试数据给每个被取数的科目都造了非零金额 ⇒ 直接取数且没留空的行必须非零（防「全 0 也恒等」的假绿）；
    # 只引用无公式行（如现金流量表小计）的行可以为 0
    fetch_rows = [r.row_code for r in with_formula
                  if (analyze_formula(r.formula).tb_codes or analyze_formula(r.formula).tb_ranges)
                  and r.row_code not in expected_blank]
    zero = [c for c in fetch_rows if consolidated[c].amount == 0]
    assert fetch_rows and zero == [], zero
    # 抵销确实进了报表：往来抵销列在应收账款行 = 借 300 ⇒ +300
    assert root[MEASURE_ELIM_TRADE]["BS-006"].amount == D("300.00")


def test_elim_measures_split_by_entry_type():
    """权益抵销 / 往来交易抵销 / 调整按分录类型分桶；贷方科目按自然方向归一（贷 100 ⇒ +100）。"""
    g = rec("G", "某集团", "consolidated")
    from app.services.consol_group_tree import derive_group_tree

    tree = derive_group_tree([g], g, Y).root
    basis = build_calc_basis(tree, Y, [], [
        entry(g.id, "E1", [("1122", "0", "30"), ("2202", "30", "0")], entry_type="internal_ar_ap"),
        entry(g.id, "E2", [("6001", "10", "0"), ("6401", "0", "10")], entry_type="unrealized_profit"),
        entry(g.id, "E3", [("4001", "50", "0"), ("1511", "0", "50")], entry_type="equity"),
        entry(g.id, "E4", [("1122", "4", "0"), ("6001", "0", "4")], entry_type="other"),
    ])
    elim = node_measures(basis)["G:consol_elim"]
    assert elim[MEASURE_ELIM_TRADE] == {"1122": D(-30), "2202": D(-30), "6001": D(-10), "6401": D(-10)}
    assert elim[MEASURE_ELIM_EQUITY] == {"4001": D(-50), "1511": D(-50)}
    assert elim[MEASURE_ADJUSTMENT] == {"1122": D(4), "6001": D(4)}
    assert elim[MEASURE_INDIVIDUAL] == {}
    assert elim[MEASURE_CONSOLIDATED] == {"1122": D(-26), "2202": D(-30), "6001": D(-6), "6401": D(-10),
                                          "4001": D(-50), "1511": D(-50)}
    assert NAME["1122"] == "应收账款"


def test_measures_reach_report_rows_through_evaluator():
    """度量值经同一求值函数到报表行：负的抵销净额也能正确进 ``A - B`` 与 ``-TB`` 形态的公式。"""
    g = rec("G", "某集团", "consolidated")
    from app.services.consol_group_tree import derive_group_tree

    tree = derive_group_tree([g], g, Y).root
    basis = build_calc_basis(tree, Y, [], [
        entry(g.id, "E1", [("1602", "8", "0"), ("6115", "0", "8")], entry_type="internal_trade"),
    ])
    rows = rows_of(("balance_sheet", "BS-1", 1, "TB('1601','期末余额') - TB('1602','期末余额')"),
                   ("balance_sheet", "BS-2", 2, "-TB('1602','期末余额')"))
    rep = run(node_report(rows, node_measures(basis)["G:consol"], categories=basis.categories))
    # 累计折旧（贷方性质）借 8 ⇒ 归一 −8 ⇒ 固定资产净额 +8
    assert rep[MEASURE_ELIM_TRADE]["BS-1"].amount == D("8.00")
    assert rep[MEASURE_ELIM_TRADE]["BS-2"].amount == D("8.00")
    assert rep[MEASURE_CONSOLIDATED]["BS-1"].amount == D("8.00")
    assert rep[MEASURE_INDIVIDUAL]["BS-1"].amount == D("0.00")


def test_evaluator_is_report_engine_entry():
    """内核走 ``report_engine.evaluate_formula``（与单体报表同一编排），不是另写一套求值。"""
    import app.services.consol_report_values as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from app.services.report_engine import evaluate_formula" in src
    assert run(evaluate_formula("(TB('1001','期末余额'))*2", resolver=BasisResolver({"1001": D(3)}))) == D("6.00")
