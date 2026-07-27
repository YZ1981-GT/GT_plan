"""Wave 3 / Task 4.1 — G7-1 叶子分类合计（render 注入）单测。

覆盖：Category_Map 最长前缀分类、灰度关闭返回 None（Property 5）；
叶子过滤无双算由 test_g7_characterization 的 _sum_leaf_by_prefix 锁定，此处补分类映射。
"""

from __future__ import annotations

import asyncio
import types

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7


class TestClassifyLeaf:
    def test_exact_and_dotted(self):
        assert g7._classify_leaf("1511.01") == "cost"
        assert g7._classify_leaf("1511.02") == "cost"
        assert g7._classify_leaf("1511.03") == "profit_loss"
        assert g7._classify_leaf("1511.04.01") == "oci"
        assert g7._classify_leaf("1511.04.02") == "other_equity"

    def test_dotted_child_of_key(self):
        # 1511.01.05 → 归 1511.01 = cost
        assert g7._classify_leaf("1511.01.05") == "cost"
        # 1512.01 → 归 1512 = impairment
        assert g7._classify_leaf("1512.01") == "impairment"

    def test_impairment_exact(self):
        assert g7._classify_leaf("1512") == "impairment"

    def test_unmapped_parent(self):
        # 1511 自身（无子级归属）不落任何分类
        assert g7._classify_leaf("1511") is None
        # 1511.99 未在 Category_Map → None（进 unmapped）
        assert g7._classify_leaf("1511.99") is None

    def test_longest_prefix_wins(self):
        # 1511.04.01 应命中 1511.04.01(oci) 而非更短的前缀
        assert g7._classify_leaf("1511.04.01") == "oci"


class TestGrayOff:
    def test_returns_none_when_flag_off(self, monkeypatch):
        # _build_g7_leaf_categories 内 `from app.core.config import settings`，
        # 故直接 patch settings 单例属性（局部 import 会读到）
        from app.core.config import settings

        monkeypatch.setattr(settings, "G7_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False)
        ctx = types.SimpleNamespace(db=None, project_id="p", year=2025)
        result = asyncio.run(g7._build_g7_leaf_categories(ctx))
        assert result is None
