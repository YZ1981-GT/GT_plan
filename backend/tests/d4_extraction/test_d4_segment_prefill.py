"""Test build_d4_segment_prefill — Task 2.2 验证."""

from app.routers.wp_render_strategies._d4_operating_revenue import (
    build_d4_segment_prefill,
)
from app.services.d4_extraction.account_scope import D4AccountScope
from app.services.four_table import LeafRow


def _leaf(code: str, name: str, credit: float = 0, debit: float = 0) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=0,
        closing=0,
        debit=debit,
        credit=credit,
        direction="",
        opening_direction="",
        dataset_id="",
    )


class TestBuildD4SegmentPrefill:
    """build_d4_segment_prefill 纯函数单测."""

    def test_empty_leaves_returns_empty(self):
        scope = D4AccountScope()
        assert build_d4_segment_prefill([], [], scope) == []

    def test_basic_mirror_pairing(self):
        scope = D4AccountScope()
        rev = [_leaf("6001.11", "营业收入_批发", credit=100.0)]
        cost = [_leaf("6401.11", "营业成本_批发", debit=80.0)]
        result = build_d4_segment_prefill(rev, cost, scope)
        assert len(result) == 1
        row = result[0]
        assert row["label"] == "批发"
        assert row["section"] == "主营业务"
        assert row["current_revenue"] == 100.0
        assert row["current_cost"] == 80.0
        assert row["name_mismatch"] is False
        assert row["cost_missing"] is False
        assert row["revenue_missing"] is False

    def test_name_mismatch_flagged(self):
        """后缀配对成立但名称不等（Property 8）."""
        scope = D4AccountScope()
        rev = [_leaf("6001.16", "营业收入_医疗收入", credit=200.0)]
        cost = [_leaf("6401.16", "营业成本_医疗支出", debit=150.0)]
        result = build_d4_segment_prefill(rev, cost, scope)
        assert len(result) == 1
        assert result[0]["name_mismatch"] is True
        assert result[0]["current_revenue"] == 200.0
        assert result[0]["current_cost"] == 150.0

    def test_cost_missing(self):
        """收入有对应成本无 → cost_missing=True, current_cost=None."""
        scope = D4AccountScope()
        rev = [_leaf("6001.15", "营业收入_物业与租赁", credit=300.0)]
        result = build_d4_segment_prefill(rev, [], scope)
        assert len(result) == 1
        assert result[0]["cost_missing"] is True
        assert result[0]["current_cost"] is None
        assert result[0]["current_revenue"] == 300.0

    def test_revenue_missing(self):
        """成本有对应收入无 → revenue_missing=True."""
        scope = D4AccountScope()
        cost = [_leaf("6401.14", "营业成本_物流", debit=500.0)]
        result = build_d4_segment_prefill([], cost, scope)
        assert len(result) == 1
        assert result[0]["revenue_missing"] is True
        assert result[0]["current_revenue"] is None
        assert result[0]["current_cost"] == 500.0

    def test_asymmetric_rollup(self):
        """层级不对称归并：父收入 + 子成本 → 合并为一行."""
        scope = D4AccountScope()
        rev = [_leaf("6001.12", "营业收入_零售", credit=1000.0)]
        cost = [
            _leaf("6401.12.01", "营业成本_零售_货物成本", debit=600.0),
            _leaf("6401.12.02", "营业成本_零售_成本差异", debit=200.0),
        ]
        result = build_d4_segment_prefill(rev, cost, scope)
        assert len(result) == 1
        assert result[0]["label"] == "零售"
        assert result[0]["current_revenue"] == 1000.0
        assert result[0]["current_cost"] == 800.0

    def test_multiple_sections(self):
        """主营 + 其他 两段分部行."""
        scope = D4AccountScope()
        rev = [
            _leaf("6001.11", "营业收入_批发", credit=100.0),
            _leaf("6051.01", "其他业务收入_租赁", credit=50.0),
        ]
        cost = [
            _leaf("6401.11", "营业成本_批发", debit=80.0),
            _leaf("6402.01", "其他业务成本_租赁", debit=30.0),
        ]
        result = build_d4_segment_prefill(rev, cost, scope)
        assert len(result) == 2
        # 按 section 顺序：主营在前
        assert result[0]["section"] == "主营业务"
        assert result[0]["label"] == "批发"
        assert result[1]["section"] == "其他业务"
        assert result[1]["label"] == "租赁"

    def test_none_leaves_treated_as_empty(self):
        """None 输入不崩溃."""
        scope = D4AccountScope()
        # pair_revenue_cost_leaves 内部对 None 做了兼容
        result = build_d4_segment_prefill(None, None, scope)  # type: ignore[arg-type]
        assert result == []
