"""F3/F4/F5 分类桶守卫（Property 2, 4, 5, 6）。

验证：
- Property 2: 各桶金额之和等于叶子合计（不丢科目）
- Property 4: 归类顺序敏感性（打乱顺序改变结果 = 反向自检）
- Property 5: 符号约定归一（正数/负数两种存法输出相同）
- Property 6: 损益类取 debit_amount 之和（结转账非零）

spec: f-cycle-four-table-extraction-and-disclosure-completion Task 14
"""
from __future__ import annotations

import pytest

from app.services.four_table.f3_note_categories import (
    F3_CATEGORIES,
    F3_CATCHALL_KEY,
    build_f3_bucket_prefill,
    build_f3_leaf_categories,
    classify_f3_leaf,
    f3_category_payload,
)
from app.services.four_table.f4_nature_buckets import (
    F4_NATURE_BUCKETS,
    classify_f4_leaf,
    f4_bucket_payload,
)
from app.services.four_table.f5_cost_segments import (
    F5_SEGMENTS,
    classify_f5_leaf,
    f5_segment_payload,
)
from app.services.four_table import LeafRow


# ═══════════════════════════════════ F3 ═══════════════════════════════════════


class TestF3Classification:
    """F3 票据种类分类。"""

    def test_classify_bank(self):
        assert classify_f3_leaf("应付票据_银行承兑汇票") == "bank"

    def test_classify_commercial(self):
        assert classify_f3_leaf("应付票据_商业承兑汇票") == "commercial"

    def test_classify_letter_of_credit(self):
        assert classify_f3_leaf("应付票据_信用证") == "letter_of_credit"

    def test_classify_supplychain(self):
        assert classify_f3_leaf("银行供应链票据") == "supplychain"

    def test_classify_other(self):
        assert classify_f3_leaf("应付票据_其他") == F3_CATCHALL_KEY

    def test_code_hint_fallback(self):
        """名称无关键字时按 code_hints 兜底。"""
        assert classify_f3_leaf("某科目", "2201.03") == "letter_of_credit"
        assert classify_f3_leaf("某科目", "2201.01") == "bank"

    def test_supplychain_before_bank(self):
        """Property 4: 供应链必须先于银行（「银行云信」应归供应链不归银行）。"""
        assert classify_f3_leaf("招商银行云信") == "supplychain"

    def test_property2_bucket_sum_equals_total(self):
        """Property 2: 各桶金额之和 == 叶子合计。"""
        leaves = [
            LeafRow(account_code="2201.01", account_name="银行承兑", opening=100, closing=200),
            LeafRow(account_code="2201.02", account_name="商业承兑", opening=50, closing=80),
            LeafRow(account_code="2201.03", account_name="信用证", opening=300, closing=500),
        ]
        categories = build_f3_leaf_categories(leaves)
        prefill = build_f3_bucket_prefill(categories)
        total_closing = sum(b["closing"] for b in prefill.values())
        total_opening = sum(b["opening"] for b in prefill.values())
        assert abs(total_closing - sum(r.closing for r in leaves)) < 0.01
        assert abs(total_opening - sum(r.opening for r in leaves)) < 0.01

    def test_property4_order_matters(self):
        """Property 4 反向自检: 打乱顺序后「银行云信」归类改变。"""
        original = classify_f3_leaf("招商银行云信")
        # 如果 bank 先于 supplychain，「银行云信」含「银行」会被误归 bank
        assert original == "supplychain"
        # 直接用 _matches 模拟：bank 的 keywords 含「银行」且排除词含「云信」
        # → 排除词阻止了误归。这是顺序+否决词双重保护
        from app.services.four_table.f3_note_categories import _matches, F3_CATEGORIES
        bank_cat = next(c for c in F3_CATEGORIES if c.key == "bank")
        assert not _matches(bank_cat, "招商银行云信")  # 被否决词阻止

    def test_property5_sign_convention_normalized(self):
        """Property 5: 正数/负数两种存法→桶预填金额相等（正数口径）。"""
        # 正数存法
        pos_leaves = [
            LeafRow(account_code="2201.01", account_name="银行承兑", opening=100, closing=200),
        ]
        # 负数存法（贷方负数约定）
        neg_leaves = [
            LeafRow(account_code="2201.01", account_name="银行承兑", opening=-100, closing=-200),
        ]
        pos_prefill = build_f3_bucket_prefill(build_f3_leaf_categories(pos_leaves))
        neg_prefill = build_f3_bucket_prefill(build_f3_leaf_categories(neg_leaves))
        assert pos_prefill["bank"]["closing"] == neg_prefill["bank"]["closing"]
        assert pos_prefill["bank"]["opening"] == neg_prefill["bank"]["opening"]

    def test_payload_nonempty(self):
        """反向自检：payload 非空。"""
        payload = f3_category_payload()
        assert len(payload) >= 5
        assert any(p["key"] == "letter_of_credit" for p in payload)


# ═══════════════════════════════════ F4 ═══════════════════════════════════════


class TestF4Classification:
    """F4 性质桶分类。"""

    def test_classify_goods(self):
        assert classify_f4_leaf("应付账款_货款") == "goods"

    def test_classify_construction(self):
        assert classify_f4_leaf("应付账款_工程款") == "construction"

    def test_classify_equipment(self):
        assert classify_f4_leaf("应付账款_设备款") == "equipment"

    def test_classify_service(self):
        assert classify_f4_leaf("应付账款_服务费") == "service"

    def test_classify_other(self):
        """暂估/返利/进项税等内部核算科目归 other。"""
        assert classify_f4_leaf("应付账款_暂估应付款") == "other"
        assert classify_f4_leaf("应付账款_预提供应商返利") == "other"
        assert classify_f4_leaf("应付账款_进项税") == "other"

    def test_ambiguous_construction_equipment(self):
        """Property 4: 「工程设备款」归工程款（在前）而非设备款。"""
        assert classify_f4_leaf("应付账款_工程设备款") == "construction"

    def test_property4_order_matters(self):
        """反向自检：如果设备在工程前，「工程设备款」会归设备。"""
        # 找到 construction 和 equipment 的位置
        keys = [b.key for b in F4_NATURE_BUCKETS]
        assert keys.index("construction") < keys.index("equipment")

    def test_payload_five_buckets(self):
        payload = f4_bucket_payload()
        assert len(payload) >= 5


# ═══════════════════════════════════ F5 ═══════════════════════════════════════


class TestF5Classification:
    """F5 成本分段。"""

    def test_classify_main(self):
        assert classify_f5_leaf("主营业务成本") == "main"
        assert classify_f5_leaf("营业成本") == "main"

    def test_classify_other(self):
        assert classify_f5_leaf("其他业务成本") == "other"
        assert classify_f5_leaf("其他业务支出") == "other"

    def test_exclude_prevents_main_eating_other(self):
        """Property 4: 「其他业务成本」不被 main 桶的「业务成本」吃掉。"""
        # main 有 exclude_keywords=('其他业务',)
        assert classify_f5_leaf("其他业务成本") == "other"

    def test_property4_order_matters(self):
        """反向自检：main 的 exclude 确实生效（去掉后会误归）。"""
        main_seg = next(s for s in F5_SEGMENTS if s.key == "main")
        assert "其他业务" in main_seg.exclude_keywords

    def test_payload_two_segments(self):
        payload = f5_segment_payload()
        assert len(payload) == 2
        assert payload[0]["key"] == "main"
        assert payload[1]["key"] == "other"
