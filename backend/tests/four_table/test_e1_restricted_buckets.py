"""E1 受限制货币资金分类真源守卫。

**Validates: Requirements 11.2, 11.3, 11.4, 11.11**

Properties: 10（宁缺勿造）、15（顺序即优先级）

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ (Task 3.5)
"""
from __future__ import annotations

import dataclasses

import pytest

from app.services.four_table.e1_restricted_buckets import (
    E1_RESTRICTED_BUCKET_BY_KEY,
    E1_RESTRICTED_BUCKETS,
    UNRESTRICTED,
    E1RestrictedBucket,
    bucket_defs_payload,
    classify_e1_restricted_leaf,
)

# ── 源 xlsx「附注披露信息(国企)」R17~R21 的五个类别（逐字）──────────────────
#: 与 backend/wp_templates/E/E1-1至E1-11 …xlsx 的披露 sheet 逐字一致；
#: openpyxl 交叉比对由 test_note_e1_structure.py 负责，此处锁标签字面。
SOURCE_TEMPLATE_LABELS = {
    "bank_acceptance": "银行承兑汇票保证金",
    "letter_of_credit": "信用证保证金",
    "performance": "履约保证金",
    "pledged_deposit": "用于担保的定期存款或通知存款",
    "overseas": "放在境外且资金汇回受到限制的款项",
}

#: 活体实证叶子名（项目 df5b8403 的货币资金叶子）—— 必须**全部**不归类。
#: 叶子名是银行户名/支付渠道名，不含受限关键字，这是设计如此而非缺陷。
LIVE_LEAF_NAMES = (
    "金华招行基本户801",
    "金华结构性存款账户",
    "金华支付宝",
    "金华微信小程序",
    "聚合收款",
    "AFO",
    "小桔有车",
    "北京基本户202",
    "北京资本金户401",
    "北京三井住友801",
    "金华招行资本金户403",
    "西安聚合收款",
)


class TestBucketDefinitions:
    def test_labels_match_source_template(self):
        """五个命名桶的 label 必须与源模板逐字一致（反向自检：桶清单非空）。"""
        assert len(E1_RESTRICTED_BUCKETS) >= 6
        for key, label in SOURCE_TEMPLATE_LABELS.items():
            assert key in E1_RESTRICTED_BUCKET_BY_KEY, f"缺桶 {key}"
            assert E1_RESTRICTED_BUCKET_BY_KEY[key].label == label

    def test_five_named_buckets_carry_source_ref(self):
        """源模板行必须带 source_ref（供 openpyxl 守卫反查）；兜底桶为 None。"""
        for key in SOURCE_TEMPLATE_LABELS:
            assert E1_RESTRICTED_BUCKET_BY_KEY[key].source_ref, f"{key} 缺 source_ref"
        assert E1_RESTRICTED_BUCKET_BY_KEY["other"].source_ref is None

    def test_keys_unique_and_stable(self):
        keys = [b.key for b in E1_RESTRICTED_BUCKETS]
        assert len(keys) == len(set(keys))
        # UNRESTRICTED 是哨兵值，不能与任何桶 key 相同
        assert UNRESTRICTED not in keys

    def test_bucket_defs_payload_is_single_source_of_labels(self):
        """下发前端的 payload 即中文标签唯一来源。"""
        payload = bucket_defs_payload()
        assert [p["key"] for p in payload] == [b.key for b in E1_RESTRICTED_BUCKETS]
        assert [p["label"] for p in payload] == [b.label for b in E1_RESTRICTED_BUCKETS]
        assert payload[-1]["isPlatformExtra"] is True


class TestProperty10NeverInvent:
    """Property 10：未命中一律返 None（宁缺勿造）。"""

    @pytest.mark.parametrize("name", LIVE_LEAF_NAMES)
    def test_live_leaf_names_are_never_classified(self, name):
        assert classify_e1_restricted_leaf(name) is None, (
            f"{name!r} 被归类了 —— 活体叶子名是银行户名/支付渠道名，"
            "臆造归属会把正常资金说成受限资金"
        )

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_returns_none(self, name):
        assert classify_e1_restricted_leaf(name) is None

    def test_plain_overseas_account_is_not_restricted(self):
        """🔴 光是境外 ≠ 受限：香港子公司基本户不得被判成「汇回受限」。"""
        assert classify_e1_restricted_leaf("香港基本户") is None
        assert classify_e1_restricted_leaf("境外基本户") is None
        assert classify_e1_restricted_leaf("海外一般户") is None

    def test_structured_deposit_excluded_from_pledged(self):
        """结构性存款不等于质押受限（exclude_keywords 生效）。"""
        assert classify_e1_restricted_leaf("结构性存款") is None
        assert classify_e1_restricted_leaf("金华结构性存款账户") is None


class TestProperty15OrderIsPriority:
    """Property 15：声明顺序即优先级。"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # 三者名称都含「保证金」→ 必须命中各自专属桶而非兜底桶
            ("信用证保证金", "letter_of_credit"),
            ("银行承兑汇票保证金", "bank_acceptance"),
            ("履约保证金", "performance"),
            # 「境外」优先于「冻结」（上市规则要求境外汇回受限单独披露）
            ("境外冻结存款", "overseas"),
            ("境外资金汇回受限账户", "overseas"),
            # 无境外时才落质押桶
            ("冻结存款", "pledged_deposit"),
            ("质押定期存款", "pledged_deposit"),
            ("用于担保的通知存款", "pledged_deposit"),
            # 兜底桶：确属受限但非五个命名类别
            ("投标保证金", "other"),
            ("专项监管专户", "other"),
        ],
    )
    def test_classification(self, name, expected):
        assert classify_e1_restricted_leaf(name) == expected

    def test_reverse_selfcheck_shuffled_order_breaks_letter_of_credit(self, monkeypatch):
        """反向自检：把兜底桶提到最前，「信用证保证金」会被它的『保证金』吃掉。

        证明「顺序即优先级」不是空话，也证明上面的断言不是恒真。
        """
        import app.services.four_table.e1_restricted_buckets as mod

        shuffled = (
            E1_RESTRICTED_BUCKET_BY_KEY["other"],
            *[b for b in E1_RESTRICTED_BUCKETS if b.key != "other"],
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", shuffled)
        assert mod.classify_e1_restricted_leaf("信用证保证金") == "other"

    def test_reverse_selfcheck_overseas_after_pledged_breaks(self, monkeypatch):
        """反向自检：境外桶排到质押桶之后，`境外冻结存款` 会被质押桶抢走。"""
        import app.services.four_table.e1_restricted_buckets as mod

        reordered = tuple(
            sorted(
                E1_RESTRICTED_BUCKETS,
                key=lambda b: 0 if b.key == "pledged_deposit" else 1,
            )
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", reordered)
        assert mod.classify_e1_restricted_leaf("境外冻结存款") == "pledged_deposit"

    def test_require_any_of_is_actually_used(self):
        """反向自检：确有桶声明了 require_any_of（否则该分支是死代码）。"""
        with_req = [b for b in E1_RESTRICTED_BUCKETS if b.require_any_of]
        assert with_req, "没有任何桶使用 require_any_of，共现分支成了死代码"
        assert {b.key for b in with_req} == {"overseas"}


class TestBucketDataclassContract:
    def test_frozen_dataclass(self):
        b = E1_RESTRICTED_BUCKETS[0]
        assert dataclasses.is_dataclass(b)
        with pytest.raises(dataclasses.FrozenInstanceError):
            b.label = "改不了"  # type: ignore[misc]

    def test_custom_bucket_can_be_constructed_without_optional_fields(self):
        """自定义类别（审计师新建）只需 key/label/keywords。"""
        b = E1RestrictedBucket(key="custom_x", label="某自定义类别", keywords=("某某",))
        assert b.exclude_keywords == ()
        assert b.require_any_of == ()
        assert b.source_ref is None
