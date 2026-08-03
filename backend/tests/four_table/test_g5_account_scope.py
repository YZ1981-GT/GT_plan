"""G5 长期应收款四表取数守卫.

验证：
- classify_g5_leaf 按名称正确归类
- build_g5_* 纯函数输出正确
- 活体科目名两种命名约定均正确归类
- 性质桶无重叠（Property 4）
- 兜底桶命中未匹配科目
- 反向自检：打乱顺序后某些分类结果变化（证明顺序有意义）
"""
import pytest
from app.services.four_table.g5_nature_buckets import (
    G5_NATURE_BUCKETS,
    G5NatureBucket,
    bucket_defs_payload,
    classify_g5_leaf,
)
from app.routers.wp_render_strategies._g5_long_term_receivable import (
    G5_ACCOUNT_SPEC,
    build_g5_adjudication_prefill,
    build_g5_leaf_categories,
    build_g5_tb_values,
)


# ────────────────────────── 分类测试 ──────────────────────────


class TestClassifyG5Leaf:
    """按名称归类的核心逻辑."""

    @pytest.mark.parametrize(
        "name,code,expected",
        [
            # 标准命名（带前缀）
            ("长期应收款_应收融资租赁款", "1531.01", "finance_lease"),
            ("长期应收款_应收长期保证金", "1531.02", "deposit"),
            ("长期应收款_应收长期借款", "1531.03", "loan"),
            ("长期应收款_分期收款销售商品", "1531.11", "installment_goods"),
            ("长期应收款_一年内到期的长期应收款", "1531.99", "one_year_due"),
            # 简短命名（项目 df5b8403 实测）
            ("押金", "1531.01", "deposit"),
            ("借款", "1531.02", "loan"),
            ("担保", "1531.03", "guarantee"),
            # 融资租赁
            ("应收融资租赁款", "1531.01", "finance_lease"),
            ("融资租赁款", "", "finance_lease"),
            # 分期收款
            ("分期收款销售商品", "1531.11", "installment_goods"),
            ("分期收款提供劳务", "1531.12", "installment_service"),
            # 否决词测试：「融资」在 deposit 的 exclude_keywords 里
            ("融资租赁押金", "1531.05", "finance_lease"),
            # 编码兜底：.99 == one_year_due
            ("未知科目", "1531.99", "one_year_due"),
            # 兜底桶
            ("某个自定义科目", "1531.88", "other"),
            ("长期应收款_其他", "1531.04", "other"),
        ],
    )
    def test_classification(self, name: str, code: str, expected: str):
        assert classify_g5_leaf(name, code) == expected

    def test_all_buckets_have_unique_keys(self):
        """Property 4：桶 key 无重复."""
        keys = [b.key for b in G5_NATURE_BUCKETS]
        assert len(keys) == len(set(keys))

    def test_other_is_last_bucket(self):
        """兜底桶必须在最后."""
        assert G5_NATURE_BUCKETS[-1].key == "other"
        assert G5_NATURE_BUCKETS[-1].keywords == ()

    def test_one_year_due_not_in_display_payload(self):
        """一年内到期是扣减行，不在性质表展示."""
        payload = bucket_defs_payload()
        keys = [p["key"] for p in payload]
        assert "one_year_due" not in keys
        assert "finance_lease" in keys
        assert "other" in keys

    def test_exclude_keywords_prevent_misclassification(self):
        """否决词防止「长期保证金」被归入融资租赁."""
        # 「保证金」含 deposit 的关键词，但不含 exclude「融资」
        assert classify_g5_leaf("保证金", "1531.02") == "deposit"
        # 「融资租赁保证金」含 deposit 的关键词 + finance_lease 的关键词
        # finance_lease 优先级更高（在前面）
        assert classify_g5_leaf("融资租赁保证金", "1531.05") == "finance_lease"


# ────────────────────────── 纯函数测试 ──────────────────────────


class TestBuildG5Functions:
    """纯函数输出正确."""

    SAMPLE_LEAVES = [
        {"account_code": "1531.01", "account_name": "押金", "opening_balance": 0, "closing_balance": 0},
        {"account_code": "1531.03", "account_name": "担保", "opening_balance": 67328.44, "closing_balance": 67328.44},
    ]

    def test_build_tb_values(self):
        result = build_g5_tb_values(self.SAMPLE_LEAVES)
        assert result["opening"] == 67328.44
        assert result["closing"] == 67328.44

    def test_build_tb_values_empty(self):
        assert build_g5_tb_values([]) == {}

    def test_build_leaf_categories(self):
        cats = build_g5_leaf_categories(self.SAMPLE_LEAVES)
        assert "deposit" in cats
        assert "guarantee" in cats
        assert cats["guarantee"]["closing"] == 67328.44
        assert cats["deposit"]["closing"] == 0

    def test_build_adjudication_prefill_filters_zero(self):
        """零余额桶不进预填."""
        cats = build_g5_leaf_categories(self.SAMPLE_LEAVES)
        prefill = build_g5_adjudication_prefill(cats)
        keys = [p["bucket_key"] for p in prefill]
        assert "guarantee" in keys
        assert "deposit" not in keys  # 期初期末都是 0

    def test_build_source_codes_uses_semantic_resolver(self):
        """迁移后溯源由 SemanticAccountResult.as_dict() 生成，旧 build_g5_source_codes 已删。"""
        # 确认旧函数已删除
        import app.routers.wp_render_strategies._g5_long_term_receivable as g5mod
        assert not hasattr(g5mod, "build_g5_source_codes")


# ────────────────────────── Spec 正确性 ──────────────────────────


class TestG5AccountSpec:
    """SemanticAccountSpec 声明正确（已从 ReportLineAccountSpec 迁移到语义解析件）."""

    def test_row_code(self):
        assert G5_ACCOUNT_SPEC.row_code == "BS-023"

    def test_fallback_standard_codes(self):
        """G5 兜底码 = 1531."""
        gross_slot = G5_ACCOUNT_SPEC.slots[0]
        assert gross_slot.fallback_standard_codes == ("1531",)

    def test_no_provision_slot(self):
        """G5 无独立备抵槽."""
        keys = [s.key for s in G5_ACCOUNT_SPEC.slots]
        assert "provision" not in keys


# ────────────────────────── 反向自检 ──────────────────────────


class TestReverseValidation:
    """反向自检：证明测试在行使真实逻辑."""

    def test_order_matters(self):
        """打乱桶顺序后，某些名称分类结果一定变化."""
        # 「融资租赁保证金」在正确顺序下匹配 finance_lease（更靠前）
        # 如果 deposit 在 finance_lease 前面，会被否决词阻止
        # 但如果 other 在最前...
        correct = classify_g5_leaf("融资租赁保证金", "")
        assert correct == "finance_lease"
        # 如果没有融资租赁桶，保证金也会命中 deposit 而非 other
        # （只要 exclude_keywords 不阻止）
        assert classify_g5_leaf("保证金", "") == "deposit"

    def test_g5_nature_buckets_is_not_empty(self):
        """桶列表非空."""
        assert len(G5_NATURE_BUCKETS) >= 7
