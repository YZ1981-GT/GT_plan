"""B1 子公司本体汇总 — 纯函数单元测试（consol-phase0-core-pipeline 任务 2）

只验证 `_aggregate_from_company_amounts` 与 `_collect_leaves` 的纯逻辑，
不依赖真实 PG / DB（完整 PBT P3/P2/P7 见任务 10）。

Validates: Requirements 1.2, 1.4, 1.7
"""

from decimal import Decimal
from uuid import uuid4

from app.services.consol_individual_sum_service import (
    ZERO,
    _aggregate_from_company_amounts,
    _collect_leaves,
)
from app.services.consol_tree_service import TreeNode


def _meta(code: str, name: str) -> dict:
    return {"company_code": code, "company_name": name}


def test_aggregate_sums_across_companies():
    """2 子公司 × 3 科目：acc 跨子公司按科目加总正确。"""
    company_amounts = [
        (_meta("SUB001", "子公司A"), {
            "1001": Decimal("100.00"),
            "1002": Decimal("200.00"),
            "1601": Decimal("-50.00"),  # 负数科目（如累计折旧）
        }),
        (_meta("SUB002", "子公司B"), {
            "1001": Decimal("10.00"),
            "1002": Decimal("20.00"),
            "1601": Decimal("-5.00"),
        }),
    ]

    acc, prov = _aggregate_from_company_amounts(company_amounts)

    assert acc["1001"] == Decimal("110.00")
    assert acc["1002"] == Decimal("220.00")
    assert acc["1601"] == Decimal("-55.00")
    # 每个科目两家子公司都有贡献
    assert len(prov["1001"]) == 2
    assert len(prov["1601"]) == 2


def test_provenance_excludes_zero_contributions():
    """amount == 0 的子公司不写入 provenance（属性 P2 / 后置条件）。"""
    company_amounts = [
        (_meta("SUB001", "子公司A"), {"1001": Decimal("100.00")}),
        (_meta("SUB002", "子公司B"), {"1001": ZERO}),  # 0 贡献
        (_meta("SUB003", "子公司C"), {"1001": Decimal("0.00")}),  # 0 贡献（不同字面量）
    ]

    acc, prov = _aggregate_from_company_amounts(company_amounts)

    assert acc["1001"] == Decimal("100.00")
    # 只有 SUB001 进入溯源
    assert len(prov["1001"]) == 1
    assert prov["1001"][0]["company_code"] == "SUB001"
    # 金额以 str(Decimal) 序列化，无 float 中转（属性 P7）
    assert prov["1001"][0]["amount"] == "100.00"
    assert isinstance(prov["1001"][0]["amount"], str)


def test_individual_sum_self_consistency():
    """breakdown.individual_sum == Σ by_company[*].amount（provenance 自洽，属性 P2）。"""
    company_amounts = [
        (_meta("SUB001", "子公司A"), {"1001": Decimal("123456.78")}),
        (_meta("SUB002", "子公司B"), {"1001": Decimal("234567.00")}),
        (_meta("SUB003", "子公司C"), {"1001": Decimal("0.11")}),
    ]

    acc, prov = _aggregate_from_company_amounts(company_amounts)

    # acc 与 provenance 逐项相加自洽（用 Decimal 重算，不经 float）
    recomputed = sum((Decimal(row["amount"]) for row in prov["1001"]), ZERO)
    assert recomputed == acc["1001"]
    assert acc["1001"] == Decimal("358023.89")


def test_account_only_in_one_company():
    """某科目仅出现在一个子公司：不丢科目，acc 正确。"""
    company_amounts = [
        (_meta("SUB001", "子公司A"), {"1001": Decimal("100.00"), "6601": Decimal("33.33")}),
        (_meta("SUB002", "子公司B"), {"1001": Decimal("50.00")}),
    ]

    acc, prov = _aggregate_from_company_amounts(company_amounts)

    assert acc["6601"] == Decimal("33.33")
    assert len(prov["6601"]) == 1
    assert acc["1001"] == Decimal("150.00")


def test_subsidiary_without_tb_contributes_nothing():
    """某子公司无 TB 数据（空字典）→ 视为 0 贡献，不抛错（属性 P3 边界）。"""
    company_amounts = [
        (_meta("SUB001", "子公司A"), {"1001": Decimal("100.00")}),
        (_meta("SUB002", "子公司B"), {}),  # 无 TB 数据
    ]

    acc, prov = _aggregate_from_company_amounts(company_amounts)

    assert acc["1001"] == Decimal("100.00")
    assert len(prov["1001"]) == 1


def test_collect_leaves_single_layer():
    """单层合并树：母节点 + 2 直接子公司 → 叶子恰为 2 个子公司。"""
    root = TreeNode(
        project_id=uuid4(), company_code="P", company_name="母公司",
        parent_company_code=None, ultimate_company_code="P", consol_level=2,
        children=[
            TreeNode(
                project_id=uuid4(), company_code="SUB001", company_name="子公司A",
                parent_company_code="P", ultimate_company_code="P", consol_level=1,
            ),
            TreeNode(
                project_id=uuid4(), company_code="SUB002", company_name="子公司B",
                parent_company_code="P", ultimate_company_code="P", consol_level=1,
            ),
        ],
    )

    leaves = _collect_leaves(root)

    leaf_codes = {n.company_code for n in leaves}
    assert leaf_codes == {"SUB001", "SUB002"}
    assert len(leaves) == 2
