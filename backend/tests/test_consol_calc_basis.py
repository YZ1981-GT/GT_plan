"""合并计算口径（spec consol-tree-three-code-autobuild 任务 7.6）。

- P7（hypothesis）：每个汇总节点逐科目 = 直接子节点合计；差额节点合并数 = 归一后调整 + 抵销；
  数据节点 = 单户审定数。
- P8（真 SQLite + 随机集团）：差额表根合并数 = 合并试算合并数，逐科目相等（对账 0 差异）；重算幂等。
- P9（hypothesis）：每笔已审批非孤儿分录只计入一个差额节点；孤儿分录两条路径都不计入；
  两条路径的调整 + 抵销合计逐科目相等。
- P10（示例）：借方性质科目借 100 ⇒ 合并数 +100；贷方性质科目贷 100 ⇒ +100；备抵科目按名称识别。
- 归属 ``attribute_entry`` 各分支、明细行解析、到分取整、科目集合与建行。
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

import hypothesis.strategies as st
import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.services.consol_calc_basis import (  # noqa: E402
    EntryDataError,
    EntryLine,
    EntryRecord,
    TbRow,
    account_sign,
    attribute_entry,
    build_calc_basis,
    data_leaves,
    index_tree,
    line_items,
    node_values,
    to_cents,
    trial_amounts,
)
from app.services.consol_group_tree import ProjectRecord, derive_group_tree  # noqa: E402
from app.services.consol_tree_service import iter_nodes  # noqa: E402

Y = 2025
D = Decimal
# 覆盖借方性质、贷方性质、备抵（资产类编码但贷方性质）、权益备抵（库存股，借方性质）
ACCOUNTS = [
    ("1001", "货币资金"), ("1122", "应收账款"), ("1602", "累计折旧"), ("2202", "应付账款"),
    ("4001", "实收资本"), ("4201", "库存股"), ("6001", "营业收入"), ("6401", "营业成本"),
]
NAME = dict(ACCOUNTS)


def _uid(tag: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"ctree-calc/{tag}")


def rec(code, name, scope="standalone", *, parent=None, relation=None) -> ProjectRecord:
    return ProjectRecord(
        id=_uid(f"{code}/{scope}"), company_code=code, client_name=name, report_scope=scope,
        audit_year=Y, parent_company_code=parent, relation_to_parent=relation,
    )


def entry(project_id, no, lines, *, entry_type="internal_ar_ap", branch=None) -> EntryRecord:
    return EntryRecord(
        id=_uid(f"entry/{no}"), project_id=project_id, entry_no=no, entry_type=entry_type,
        branch_entity_code=branch,
        lines=tuple(EntryLine(code, NAME.get(code), D(dr), D(cr)) for code, dr, cr in lines),
    )


# ─────────────────────────────── 示例：符号 / 明细行 / 归属 ───────────────────────────────


class TestSignAndLines:
    def test_p10_sign_by_nature(self):
        """P10：借方性质 +1、贷方性质 −1；备抵按名称（累计折旧贷方、库存股借方），与单体调整同源。"""
        assert [account_sign(c, n) for c, n in ACCOUNTS] == [
            D(1), D(1), D(-1), D(-1), D(-1), D(1), D(-1), D(1),
        ]

    def test_p10_elimination_raises_consolidated_by_100(self):
        """P10：借方性质科目借 100 ⇒ 合并数 +100；贷方性质科目贷 100 ⇒ 合并数 +100。"""
        g = rec("G", "某集团", "consolidated")
        tree = derive_group_tree([g], g, Y).root
        basis = build_calc_basis(tree, Y, [], [
            entry(g.id, "E1", [("1122", "100", "0"), ("2202", "0", "100")]),
        ])
        root = node_values(basis)["G:consol"]
        assert root["1122"].consolidated_amount == D(100)
        assert root["2202"].consolidated_amount == D(100)
        # 反向录入 ⇒ 两个科目都 −100
        basis = build_calc_basis(tree, Y, [], [
            entry(g.id, "E2", [("2202", "100", "0"), ("1122", "0", "100")]),
        ])
        root = node_values(basis)["G:consol"]
        assert (root["1122"].consolidated_amount, root["2202"].consolidated_amount) == (D(-100), D(-100))

    def test_line_items_fallback_and_errors(self):
        class E:
            def __init__(self, **kw):
                self.lines = kw.get("lines")
                self.account_code = kw.get("account_code", "")
                self.account_name = None
                self.debit_amount = kw.get("debit_amount")
                self.credit_amount = kw.get("credit_amount")

        assert line_items(E(lines=None, account_code="1001", debit_amount=D("5.005"))) == (
            EntryLine("1001", None, D("5.01"), D("0")),
        )
        assert line_items(E(lines=[{"account_code": "", "debit_amount": "0"}])) == ()
        # 明细行被写成非列表（空对象 / 空串）⇒ 报错，不静默退回表头（否则金额从表头来、与录入明细不一致）
        for bad_lines in ({}, ""):
            with pytest.raises(EntryDataError, match="不是列表"):
                line_items(E(lines=bad_lines, account_code="1001", debit_amount=D("1")))
        for bad in ({"lines": {"x": 1}}, {"lines": ["x"]}, {"lines": [{"account_code": "", "debit_amount": "1"}]},
                    {"lines": [{"account_code": "1001", "debit_amount": "abc"}]},
                    {"lines": [{"account_code": "1001", "debit_amount": "NaN"}]}):
            with pytest.raises(EntryDataError):
                line_items(E(**bad))

    def test_to_cents(self):
        assert to_cents("1.005") == D("1.01") and to_cents(None) == D(0) and to_cents(D("2")) == D("2.00")


def _nested_group():
    """G（合并+单户）⊃ 分公司 GB、子公司 A（合并+单户，A 有分公司 AB）、子公司 S（单户）。"""
    g_c, g_s = rec("G", "某集团", "consolidated"), rec("G", "某集团")
    gb = rec("GB", "某集团北京分公司", parent="G", relation="branch")
    a_c, a_s = rec("A", "甲公司", "consolidated", parent="G", relation="subsidiary"), rec(
        "A", "甲公司", parent="G", relation="subsidiary")
    ab = rec("AB", "甲公司上海分公司", parent="A", relation="branch")
    s = rec("S", "乙公司", parent="G", relation="subsidiary")
    records = [g_c, g_s, gb, a_c, a_s, ab, s]
    return records, g_c, a_c, derive_group_tree(records, g_c, Y).root


class TestAttribution:
    def test_branches_of_attribute_entry(self):
        records, g_c, a_c, tree = _nested_group()
        index = index_tree(tree)
        other = uuid.uuid4()
        cases = {
            "G 合并差额": (entry(g_c.id, "1", []), "G:consol_elim"),
            "A 合并差额（下级合并项目）": (entry(a_c.id, "2", []), "A:consol_elim"),
            "G 母分差额": (entry(g_c.id, "3", [], branch="G"), "G:branch_elim"),
            # A 的母分差额节点在 G 树里由 A 的合并项目承载（design §3.3），由 G 录入是孤儿
            "A 母分差额由 A 录入": (entry(a_c.id, "4", [], branch="A"), "A:branch_elim"),
        }
        for label, (e, want) in cases.items():
            assert attribute_entry(e, index) == (want, None), label

        key, reason = attribute_entry(entry(g_c.id, "5", [], branch="A"), index)
        assert key is None and "甲公司" in reason and "应到该合并项目录入" in reason
        key, reason = attribute_entry(entry(g_c.id, "6", [], branch="S"), index)
        assert key is None and "没有母分差额节点" in reason
        key, reason = attribute_entry(entry(other, "7", []), index)
        assert key is None and "不是本企业树中的合并项目" in reason

    def test_account_set_and_names(self):
        """科目集合 = 数据叶子试算表 ∪ 已归属分录明细行；孤儿分录的科目不进集合；科目名试算表优先。"""
        records, g_c, a_c, tree = _nested_group()
        tb = [TbRow(_uid("G/standalone"), "1001", "现金及银行", None, D(1))]
        basis = build_calc_basis(tree, Y, tb, [
            entry(g_c.id, "E1", [("1001", "5", "0"), ("6001", "0", "5")]),
            entry(g_c.id, "E2", [("4201", "9", "0"), ("4001", "0", "9")], branch="S"),  # 孤儿
        ])
        assert basis.accounts == ["1001", "6001"]
        assert basis.names["1001"] == "现金及银行" and basis.names["6001"] == "营业收入"
        assert [o.entry_no for o in basis.orphans] == ["E2"]
        assert basis.attributed == {_uid("entry/E1"): "G:consol_elim"}


# ─────────────────────────────── 属性测试：随机集团 + 随机试算 + 随机分录 ───────────────────────────────

_amounts = st.decimals(min_value=D("-99999.99"), max_value=D("99999.99"), places=2, allow_nan=False)


@st.composite
def _world(draw):
    """随机集团（与 test_consol_group_tree 同构的生成规则）+ 各单户项目随机试算 + 随机分录。

    分录的承载项目从全部合并项目 + 一个树外项目里抽，归属企业代码从全部企业 + 空里抽 ⇒
    同时覆盖正常归属、下级合并项目承载、母分差额、各类孤儿。
    """
    n = draw(st.integers(min_value=2, max_value=6))
    records: list[ProjectRecord] = []
    for i in range(n):
        code = f"E{i}"
        has_consol = True if i == 0 else draw(st.booleans())
        has_standalone = draw(st.booleans()) if has_consol else True
        parent_idx = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=n - 1)))
        kw = {
            "parent": f"E{parent_idx}" if parent_idx is not None else None,
            "relation": draw(st.sampled_from([None, "subsidiary", "branch"])),
        }
        if has_consol:
            records.append(rec(code, f"企业{i}", "consolidated", **kw))
        if has_standalone:
            records.append(rec(code, f"企业{i}", **kw))
    codes = [c for c, _n in ACCOUNTS]
    tb = [
        TbRow(r.id, code, NAME[code], None, draw(_amounts))
        for r in records if r.report_scope == "standalone"
        for code in draw(st.lists(st.sampled_from(codes), max_size=4, unique=True))
    ]
    hosts = [r.id for r in records if r.report_scope == "consolidated"] + [_uid("outside")]
    entries = []
    for k in range(draw(st.integers(min_value=0, max_value=6))):
        lines = [
            (draw(st.sampled_from(codes)), str(draw(_amounts).copy_abs()), str(draw(_amounts).copy_abs()))
            for _ in range(draw(st.integers(min_value=1, max_value=3)))
        ]
        entries.append(entry(
            draw(st.sampled_from(hosts)), f"R{k:02d}", lines,
            entry_type=draw(st.sampled_from(["other", "equity", "internal_trade"])),
            branch=draw(st.one_of(st.none(), st.sampled_from([f"E{i}" for i in range(n)]))),
        ))
    root = next(r for r in records if r.company_code == "E0" and r.report_scope == "consolidated")
    return records, root, tb, entries


def _targeted(world):
    """在随机分录之外，给树里每个差额节点补一笔「正确录入」的分录（随机归属很少命中母分差额）。"""
    records, root, tb, entries = world
    tree = derive_group_tree(records, root, Y).root
    extra = []
    for i, node in enumerate(n for n in iter_nodes(tree) if n.kind == "elim"):
        branch = node.company_code if node.role == "branch_elim" else None
        extra.append(entry(node.host_project_id, f"T{i:02d}", [("1122", "100", "0"), ("2202", "0", "100")],
                           branch=branch))
    return records, root, tb, entries + extra, tree


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(world=_world())
def test_p7_node_amounts(world):
    records, root, tb, entries, tree = _targeted(world)
    basis = build_calc_basis(tree, Y, tb, entries)
    values = node_values(basis)
    tb_sum: dict[tuple, Decimal] = {}
    for row in tb:
        tb_sum[(row.project_id, row.account_code)] = tb_sum.get((row.project_id, row.account_code), D(0)) + row.audited_amount
    for node in iter_nodes(tree):
        for a in basis.accounts:
            v = values[node.node_key][a]
            if node.kind == "aggregate":
                assert v.children_amount_sum == v.consolidated_amount == sum(
                    (values[c.node_key][a].consolidated_amount for c in node.children), D(0))
                assert v.net_difference == D(0)
            elif node.kind == "elim":
                sign = account_sign(a, NAME.get(a))
                expect = sign * ((v.adjustment_debit - v.adjustment_credit) + (v.elimination_debit - v.elimination_credit))
                assert v.consolidated_amount == v.net_difference == expect
                assert v.children_amount_sum == D(0)
            else:
                expect = tb_sum.get((node.project_id, a), D(0)) if node.project_id else D(0)
                assert v.consolidated_amount == v.children_amount_sum == expect


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(world=_world(), seed=st.integers(min_value=0, max_value=10_000))
def test_p9_each_entry_counted_once_and_orphans_excluded(world, seed):
    records, root, tb, entries, tree = _targeted(world)
    basis = build_calc_basis(tree, Y, tb, entries)
    index = index_tree(tree)

    elim_keys = {n.node_key for n in iter_nodes(tree) if n.kind == "elim"}
    orphan_ids = {o.entry_id for o in basis.orphans}
    assert set(basis.attributed) | orphan_ids == {e.id for e in entries}
    assert not (set(basis.attributed) & orphan_ids), "一笔分录不能既计入又是孤儿"
    assert set(basis.attributed.values()) == elim_keys, "只能计入差额节点，且每个差额节点都能被正确录入命中"
    for e in entries:
        assert basis.attributed.get(e.id) == attribute_entry(e, index)[0]

    # 只保留非孤儿分录重算 ⇒ 两条路径结果完全相同（孤儿对金额零影响，科目集合也不受其影响）
    counted = [e for e in entries if e.id not in orphan_ids]
    clean = build_calc_basis(tree, Y, tb, counted)
    assert clean.accounts == basis.accounts
    assert node_values(clean) == node_values(basis)
    trial = trial_amounts(basis)
    assert trial_amounts(clean) == trial

    # 与输入顺序无关
    shuffled_tb, shuffled_entries = tb[:], entries[:]
    rnd = random.Random(seed)
    rnd.shuffle(shuffled_tb)
    rnd.shuffle(shuffled_entries)
    again = build_calc_basis(tree, Y, shuffled_tb, shuffled_entries)
    assert node_values(again) == node_values(basis) and trial_amounts(again) == trial

    # 两条路径同源：根合并数 = 个别数 + 调整 + 抵销（P8 的纯函数面）
    root_values = node_values(basis)[tree.node_key]
    for a in basis.accounts:
        t = trial[a]
        assert root_values[a].consolidated_amount == t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination
        assert t.individual_sum == sum((D(r["amount"]) for r in t.by_company), D(0))


# ─────────────────────────────── P8：真 SQLite（随机集团 → 两条路径落库后逐科目相等） ───────────────────────────────


async def _p8_run(world) -> None:
    import app.models.audit_platform_models  # noqa: F401
    import app.models.core  # noqa: F401
    import app.models.report_models  # noqa: F401
    import app.models.workpaper_models  # noqa: F401
    from app.models.audit_platform_models import TrialBalance
    from app.models.base import Base
    from app.models.consolidation_models import (
        ConsolWorksheet, EliminationEntry, EliminationEntryType, ReviewStatusEnum,
    )
    from app.models.core import Project
    from app.services.account_chart_service import _infer_category
    from app.services.consol_reconciliation_service import reconcile_worksheet_vs_trial
    from app.services.consol_trial_service import recalculate_trial
    from app.services.consol_worksheet_engine import recalc_full

    records, root, tb, entries, _tree = _targeted(world)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            for r in records:
                db.add(Project(
                    id=r.id, name=f"{r.client_name}_{Y}", client_name=r.client_name, company_code=r.company_code,
                    report_scope=r.report_scope, audit_year=Y, parent_company_code=r.parent_company_code,
                    relation_to_parent=r.relation_to_parent,
                ))
            for row in tb:
                db.add(TrialBalance(
                    id=uuid.uuid4(), project_id=row.project_id, year=Y, company_code="001",
                    standard_account_code=row.account_code, account_name=row.account_name,
                    account_category=_infer_category(row.account_code, row.account_name),
                    audited_amount=row.audited_amount,
                ))
            for e in entries:
                db.add(EliminationEntry(
                    id=e.id, project_id=e.project_id, year=Y, entry_no=e.entry_no,
                    entry_type=EliminationEntryType(e.entry_type),
                    account_code=e.lines[0].account_code,
                    debit_amount=sum((ln.debit for ln in e.lines), D(0)),
                    credit_amount=sum((ln.credit for ln in e.lines), D(0)),
                    lines=[{"account_code": ln.account_code, "account_name": ln.account_name,
                            "debit_amount": str(ln.debit), "credit_amount": str(ln.credit)} for ln in e.lines],
                    entry_group_id=uuid.uuid4(), branch_entity_code=e.branch_entity_code,
                    review_status=ReviewStatusEnum.approved,
                ))
            await db.commit()

            ws = await recalc_full(db, root.id, Y)
            trials = await recalculate_trial(db, root.id, Y)
            await db.commit()

            root_rows = (await db.execute(
                sa.select(ConsolWorksheet.account_code, ConsolWorksheet.consolidated_amount).where(
                    ConsolWorksheet.project_id == root.id,
                    ConsolWorksheet.node_company_code == "E0:consol",
                    ConsolWorksheet.is_deleted == sa.false(),
                )
            )).all()
            root_ws = {code: D(str(amount)) for code, amount in root_rows}
            trial_map = {t.standard_account_code: D(str(t.consol_amount)) for t in trials}
            assert set(root_ws) == set(trial_map)
            for code in trial_map:
                assert abs(root_ws[code] - trial_map[code]) <= D("0.01"), code

            recon = await reconcile_worksheet_vs_trial(db, root.id, Y)
            assert recon.is_reconciled is True and recon.diffs == []

            again = await recalc_full(db, root.id, Y)
            assert (again["rows_written"], again["rows_removed"]) == (0, 0), "重算幂等"
            assert again["orphan_entries"] == ws["orphan_entries"]
    finally:
        await engine.dispose()


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(world=_world())
def test_p8_worksheet_root_equals_trial_on_sqlite(world):
    import asyncio

    asyncio.run(_p8_run(world))
