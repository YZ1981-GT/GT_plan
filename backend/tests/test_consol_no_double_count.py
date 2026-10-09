"""合并计算防双计守卫：individual 取审定数，与 adjustment/elimination 正交。

spec: consol-comprehensive-runtime-defect-closure 任务 11 (R5.1)

验证：
1. individual 度量仅来自 leaf_amounts（trial_balance.audited_amount），差额节点 individual 恒零
2. adjustment/elimination 仅来自 elimination_entries，数据叶子 adjustment/elimination 恒零
3. consol_amount = individual + adjustment + elimination（恒等式）
4. 只消费 approved 分录（草稿不进入金额）
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.consol_calc_basis import (
    MEASURE_ADJUSTMENT,
    MEASURE_CONSOLIDATED,
    MEASURE_ELIM_EQUITY,
    MEASURE_ELIM_TRADE,
    MEASURE_INDIVIDUAL,
    CalcBasis,
    ElimTotals,
    EntryLine,
    EntryRecord,
    TbRow,
    build_calc_basis,
    node_measures,
    trial_amounts,
)
from app.services.consol_tree_service import TreeNode

ZERO = Decimal("0")
D = Decimal


def _tree():
    """最小测试树：根合并 → [差额, 甲子, 乙子]。"""
    a_pid = uuid4()
    b_pid = uuid4()
    root_pid = uuid4()
    root = TreeNode(
        project_id=root_pid, company_code="ROOT", company_name="集团",
        parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
        node_key="ROOT:consol", role="consol", kind="aggregate",
    )
    elim = TreeNode(
        project_id=None, company_code="ROOT", company_name="差额",
        parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
        node_key="ROOT:consol_elim", role="consol_elim", kind="elim",
        host_project_id=root_pid,
    )
    a = TreeNode(
        project_id=a_pid, company_code="A", company_name="甲",
        parent_company_code="ROOT", ultimate_company_code="ROOT", consol_level=1,
        node_key="A:entity", role="subsidiary", kind="data",
    )
    b = TreeNode(
        project_id=b_pid, company_code="B", company_name="乙",
        parent_company_code="ROOT", ultimate_company_code="ROOT", consol_level=1,
        node_key="B:entity", role="subsidiary", kind="data",
    )
    root.children = [elim, a, b]
    return root, a_pid, b_pid, root_pid


def _tb_rows(a_pid, b_pid) -> list[TbRow]:
    """两个子公司各有一行审定数（已含单体 AJE）。"""
    return [
        TbRow(project_id=a_pid, account_code="1122", account_name="应收账款",
              account_category="asset", audited_amount=D("1000")),  # 含单体 AJE +200
        TbRow(project_id=b_pid, account_code="1122", account_name="应收账款",
              account_category="asset", audited_amount=D("500")),
    ]


def _entry(entry_type: str = "trade", amount: Decimal = D("50"), project_id=None) -> list[EntryRecord]:
    """一笔已审批的合并抵销分录：借 1122 / 贷 2202。project_id 须匹配合并项目。"""
    return [EntryRecord(
        id=uuid4(), project_id=project_id or uuid4(), entry_no="E-001",
        entry_type=entry_type,
        branch_entity_code="",  # 空→归属到根合并差额节点
        lines=(
            EntryLine(account_code="1122", account_name="应收账款", debit=amount, credit=ZERO),
            EntryLine(account_code="2202", account_name="应付账款", debit=ZERO, credit=amount),
        ),
    )]


def _iter(tree: TreeNode):
    yield tree
    for c in tree.children:
        yield from _iter(c)


class TestNoDoubleCount:
    """确认 individual 与 adjustment/elimination 正交，不双计。"""

    def test_individual_only_from_leaf_amounts(self):
        """数据叶子：individual = audited_amount；差额节点：individual = 0。"""
        tree, a_pid, b_pid, root_pid = _tree()
        basis = build_calc_basis(tree, 2025, _tb_rows(a_pid, b_pid), _entry(project_id=root_pid))
        measures = node_measures(basis)

        a_m = measures["A:entity"]
        assert a_m[MEASURE_INDIVIDUAL].get("1122", ZERO) == D("1000.00")
        assert a_m[MEASURE_ADJUSTMENT].get("1122", ZERO) == ZERO
        assert a_m[MEASURE_ELIM_EQUITY].get("1122", ZERO) == ZERO
        assert a_m[MEASURE_ELIM_TRADE].get("1122", ZERO) == ZERO

        elim_m = measures["ROOT:consol_elim"]
        assert elim_m[MEASURE_INDIVIDUAL].get("1122", ZERO) == ZERO
        assert elim_m[MEASURE_ELIM_TRADE].get("1122", ZERO) == D("50.00")

    def test_consol_equals_sum(self):
        """恒等式：consolidated = individual + adjustment + elim_equity + elim_trade。"""
        tree, a_pid, b_pid, root_pid = _tree()
        entries = _entry("trade", D("50"), root_pid) + _entry("other", D("10"), root_pid)
        basis = build_calc_basis(tree, 2025, _tb_rows(a_pid, b_pid), entries)
        measures = node_measures(basis)

        root_m = measures["ROOT:consol"]
        for account in basis.accounts:
            ind = root_m[MEASURE_INDIVIDUAL].get(account, ZERO)
            adj = root_m[MEASURE_ADJUSTMENT].get(account, ZERO)
            eq = root_m[MEASURE_ELIM_EQUITY].get(account, ZERO)
            tr = root_m[MEASURE_ELIM_TRADE].get(account, ZERO)
            con = root_m[MEASURE_CONSOLIDATED].get(account, ZERO)
            assert ind + adj + eq + tr == con, (
                f"科目 {account}: {ind} + {adj} + {eq} + {tr} != {con}"
            )

    def test_trial_amounts_consistent(self):
        """trial_amounts() 恒等式：consol_amount = individual_sum + consol_adjustment + consol_elimination。"""
        tree, a_pid, b_pid, root_pid = _tree()
        entries = _entry("trade", D("50"), root_pid) + _entry("equity", D("30"), root_pid)
        basis = build_calc_basis(tree, 2025, _tb_rows(a_pid, b_pid), entries)
        ta = trial_amounts(basis)

        for account, amounts in ta.items():
            assert amounts.consol_amount == amounts.individual_sum + amounts.consol_adjustment + amounts.consol_elimination, (
                f"科目 {account}: {amounts.individual_sum} + {amounts.consol_adjustment} + "
                f"{amounts.consol_elimination} != {amounts.consol_amount}"
            )

    def test_draft_entry_excluded(self):
        """未审批（草稿）分录不进入金额计算——传空分录列表模拟。"""
        tree, a_pid, b_pid, root_pid = _tree()
        basis = build_calc_basis(tree, 2025, _tb_rows(a_pid, b_pid), [])
        ta = trial_amounts(basis)

        for account, amounts in ta.items():
            assert amounts.consol_adjustment == ZERO
            assert amounts.consol_elimination == ZERO
            assert amounts.consol_amount == amounts.individual_sum

    def test_adjustment_entry_type_separation(self):
        """entry_type='other' → adjustment 列；'trade' → elim_trade 列。"""
        tree, a_pid, b_pid, root_pid = _tree()
        entries = _entry("other", D("10"), root_pid) + _entry("trade", D("50"), root_pid)
        basis = build_calc_basis(tree, 2025, _tb_rows(a_pid, b_pid), entries)
        measures = node_measures(basis)

        elim_m = measures["ROOT:consol_elim"]
        assert elim_m[MEASURE_ADJUSTMENT].get("1122", ZERO) == D("10.00")
        assert elim_m[MEASURE_ELIM_TRADE].get("1122", ZERO) == D("50.00")
        assert elim_m[MEASURE_ELIM_EQUITY].get("1122", ZERO) == ZERO
