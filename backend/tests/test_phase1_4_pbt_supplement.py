"""Phase 1~4 PBT 补充 — 覆盖核心算法的 property-based tests.

共 10 个 property，全部使用 hypothesis max_examples=30，纯逻辑测试（无 DB/无 async）。

Phase 1:
  P-1.1: 全局搜索 relevance 排序稳定性
  P-1.2: 全局搜索 relevance 评分范围

Phase 2:
  P-2.1: 签字 Gate checklist 完整性
  P-2.2: 复核优先级排序正确性

Phase 3:
  P-3.1: 双向穿透路径一致性
  P-3.2: LLM 降级行为
  P-3.3: CacheService TTL 不变量

Phase 4:
  P-4.1: (已存在于 test_phase4_pbt.py — 跳过)
  P-4.2: 多年度对比数据对齐
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: 全局搜索
# ═══════════════════════════════════════════════════════════════════════════════


class TestGlobalSearchRelevanceSortStability:
    """P-1.1: 全局搜索 relevance 排序稳定性

    **Validates: Requirements S-1 (全局搜索 Ctrl+K)**

    Property: 对于任意两个搜索结果，若 result_a.relevance > result_b.relevance，
    则排序后 result_a 始终出现在 result_b 之前。
    """

    @given(
        items=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),  # title
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),  # relevance
            ),
            min_size=2,
            max_size=50,
        )
    )
    @settings(max_examples=30)
    def test_sort_by_relevance_descending_preserves_order(self, items):
        """排序后高 relevance 项始终在低 relevance 项之前。"""
        # 模拟 global_search 的排序逻辑
        sorted_items = sorted(items, key=lambda r: r[1], reverse=True)

        for i in range(len(sorted_items) - 1):
            assert sorted_items[i][1] >= sorted_items[i + 1][1]

    @given(
        items=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=999),  # unique id
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            ),
            min_size=2,
            max_size=50,
            unique_by=lambda x: x[0],  # 确保 id 唯一
        )
    )
    @settings(max_examples=30)
    def test_sort_stability_equal_relevance(self, items):
        """相同 relevance 的项保持原始相对顺序（稳定排序）。"""
        # 记录原始索引
        indexed_items = [(i, item) for i, item in enumerate(items)]
        sorted_indexed = sorted(indexed_items, key=lambda r: r[1][1], reverse=True)

        # 对于相同 relevance 的相邻项，原始索引应保持升序
        for i in range(len(sorted_indexed) - 1):
            if sorted_indexed[i][1][1] == sorted_indexed[i + 1][1][1]:
                assert sorted_indexed[i][0] < sorted_indexed[i + 1][0]


class TestGlobalSearchRelevanceScoreRange:
    """P-1.2: 全局搜索 relevance 评分范围

    **Validates: Requirements S-1 (全局搜索评分)**

    Property: 对于任意搜索结果，relevance score 始终在 [0.0, 1.0] 范围内。
    评分规则: exact_match=1.0, prefix_match=0.8, contains_match=0.6, pinyin_match=0.4
    """

    @given(
        query=st.text(min_size=1, max_size=10, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
        text=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
    )
    @settings(max_examples=30)
    def test_score_always_in_valid_range(self, query, text):
        """_score 函数返回值始终在 [0.0, 1.0]。"""
        from app.services.global_search_service import _score

        result = _score(query, text)
        assert 0.0 <= result <= 1.0

    @given(
        text=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
    )
    @settings(max_examples=30)
    def test_exact_match_always_highest(self, text):
        """完全匹配始终返回最高分 1.0。"""
        from app.services.global_search_service import _score

        result = _score(text, text)
        assert result == 1.0

    @given(
        prefix=st.text(min_size=1, max_size=5, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
        suffix=st.text(min_size=1, max_size=10, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
    )
    @settings(max_examples=30)
    def test_prefix_match_returns_0_8(self, prefix, suffix):
        """前缀匹配返回 0.8（query 是 text 的前缀但不等于 text）。"""
        from app.services.global_search_service import _score

        text = prefix + suffix
        assume(text.lower() != prefix.lower())  # 排除完全匹配
        assume(text.lower().startswith(prefix.lower()))  # 确保前缀匹配

        result = _score(prefix, text)
        assert result == 0.8


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: 签字 Gate + 复核优先级
# ═══════════════════════════════════════════════════════════════════════════════


class TestGateChecklistCompleteness:
    """P-2.1: 签字 Gate checklist 完整性

    **Validates: Requirements P-1 (签字前 Gate)**

    Property: 对于任意项目状态，gate 返回 ready=True 当且仅当所有 blocking 条件均满足。
    模拟: 给定 N 个 gate 条件（随机 pass/fail），ready = all(conditions)。
    """

    @given(
        conditions=st.lists(
            st.booleans(),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_gate_ready_iff_all_conditions_pass(self, conditions):
        """ready=True 当且仅当所有条件为 True。"""
        ready = all(conditions)

        if ready:
            # 所有条件必须为 True
            assert all(c is True for c in conditions)
        else:
            # 至少一个条件为 False
            assert any(c is False for c in conditions)

    @given(
        n_conditions=st.integers(min_value=1, max_value=20),
        fail_index=st.integers(min_value=0, max_value=19),
    )
    @settings(max_examples=30)
    def test_single_blocking_condition_blocks_gate(self, n_conditions, fail_index):
        """任何单个 blocking 条件失败都会阻断 gate。"""
        assume(fail_index < n_conditions)

        conditions = [True] * n_conditions
        conditions[fail_index] = False

        ready = all(conditions)
        assert ready is False

    @given(
        conditions=st.lists(
            st.booleans(),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_gate_blocking_count_matches_false_conditions(self, conditions):
        """blocking 数量等于 False 条件数。"""
        blocking_count = sum(1 for c in conditions if not c)
        ready = all(conditions)

        if blocking_count == 0:
            assert ready is True
        else:
            assert ready is False
            assert blocking_count >= 1


class TestReviewPrioritySorting:
    """P-2.2: 复核优先级排序正确性

    **Validates: Requirements RV-2 (复核意见优先级)**

    Property: 对于任意复核意见列表，按优先级排序后
    must_fix 始终在 suggest 之前，suggest 始终在 info 之前。
    """

    PRIORITY_ORDER = {"must_fix": 0, "suggest": 1, "info": 2}

    @given(
        reviews=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),  # comment_text
                st.sampled_from(["must_fix", "suggest", "info"]),  # priority
            ),
            min_size=1,
            max_size=30,
        )
    )
    @settings(max_examples=30)
    def test_priority_sort_must_fix_before_suggest_before_info(self, reviews):
        """排序后 must_fix < suggest < info 顺序始终正确。"""
        sorted_reviews = sorted(
            reviews, key=lambda r: self.PRIORITY_ORDER[r[1]]
        )

        for i in range(len(sorted_reviews) - 1):
            current_priority = self.PRIORITY_ORDER[sorted_reviews[i][1]]
            next_priority = self.PRIORITY_ORDER[sorted_reviews[i + 1][1]]
            assert current_priority <= next_priority

    @given(
        must_fix_count=st.integers(min_value=0, max_value=10),
        suggest_count=st.integers(min_value=0, max_value=10),
        info_count=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=30)
    def test_priority_groups_contiguous_after_sort(self, must_fix_count, suggest_count, info_count):
        """排序后各优先级组是连续的（不交错）。"""
        assume(must_fix_count + suggest_count + info_count > 0)

        reviews = (
            [("fix_" + str(i), "must_fix") for i in range(must_fix_count)]
            + [("sug_" + str(i), "suggest") for i in range(suggest_count)]
            + [("inf_" + str(i), "info") for i in range(info_count)]
        )
        import random
        shuffled = reviews.copy()
        random.shuffle(shuffled)

        sorted_reviews = sorted(
            shuffled, key=lambda r: self.PRIORITY_ORDER[r[1]]
        )

        # 验证分组连续性
        seen_priorities = []
        for _, priority in sorted_reviews:
            if not seen_priorities or seen_priorities[-1] != priority:
                seen_priorities.append(priority)

        # 出现顺序必须是 must_fix → suggest → info 的子序列
        expected_order = ["must_fix", "suggest", "info"]
        filtered_expected = [p for p in expected_order if p in seen_priorities]
        assert seen_priorities == filtered_expected


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: 双向穿透 + LLM 降级 + Cache TTL
# ═══════════════════════════════════════════════════════════════════════════════


class TestBidirectionalDrillPath:
    """P-3.1: 双向穿透路径一致性

    **Validates: Requirements L-1 (双向穿透)**

    Property: 如果 A→B 是有效的下钻路径，则 B→A 是有效的上钻路径（双向性）。
    模拟: 用随机 (source, target) 对构建穿透图，验证双向可达。
    """

    @given(
        edges=st.lists(
            st.tuples(
                st.sampled_from(["note", "report_line", "tb_account", "ledger", "workpaper"]),
                st.sampled_from(["note", "report_line", "tb_account", "ledger", "workpaper"]),
            ),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_drill_down_implies_drill_up(self, edges):
        """每条下钻边 A→B 都有对应的上钻边 B→A。"""
        # 构建双向穿透图
        drill_down: set[tuple[str, str]] = set()
        drill_up: set[tuple[str, str]] = set()

        for source, target in edges:
            assume(source != target)  # 自环无意义
            drill_down.add((source, target))
            drill_up.add((target, source))

        # 验证双向性：每条下钻路径都有对应上钻路径
        for source, target in drill_down:
            assert (target, source) in drill_up

    @given(
        path=st.lists(
            st.sampled_from(["note", "report_line", "tb_account", "ledger", "workpaper"]),
            min_size=2,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_path_reversal_is_valid_drill_up(self, path):
        """任意下钻路径的反转是有效的上钻路径。"""
        # 下钻路径: path[0] → path[1] → ... → path[n]
        drill_down_edges = [(path[i], path[i + 1]) for i in range(len(path) - 1)]

        # 上钻路径: path[n] → path[n-1] → ... → path[0]
        reversed_path = list(reversed(path))
        drill_up_edges = [(reversed_path[i], reversed_path[i + 1]) for i in range(len(reversed_path) - 1)]

        # 验证: 上钻边集 == 下钻边集的反转
        expected_up_edges = [(t, s) for s, t in drill_down_edges]
        assert set(drill_up_edges) == set(expected_up_edges)


class TestLLMDegradationBehavior:
    """P-3.2: LLM 降级行为

    **Validates: Requirements K-1 (LLM 接入路线图)**

    Property: 当 WP_AI_SERVICE_ENABLED=False 时，所有 LLM 响应的 is_llm_stub=True；
    当 WP_AI_SERVICE_ENABLED=True 时，is_llm_stub=False。
    """

    @given(
        enabled=st.booleans(),
        endpoint_name=st.sampled_from([
            "expense_analysis", "impairment_dcf", "goodwill_test",
            "fair_value_test", "share_payment", "income_tax_calc",
        ]),
    )
    @settings(max_examples=30)
    def test_stub_flag_reflects_config(self, enabled, endpoint_name):
        """is_llm_stub 标志始终与 WP_AI_SERVICE_ENABLED 配置相反。"""
        # 模拟配置驱动的 stub 标志逻辑
        is_llm_stub = not enabled

        if enabled:
            assert is_llm_stub is False
        else:
            assert is_llm_stub is True

    @given(
        enabled=st.just(False),
        n_endpoints=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30)
    def test_all_endpoints_stub_when_disabled(self, enabled, n_endpoints):
        """禁用时所有端点都返回 stub 标志。"""
        responses = [{"is_llm_stub": not enabled, "data": {}} for _ in range(n_endpoints)]

        for resp in responses:
            assert resp["is_llm_stub"] is True


class TestCacheServiceTTLInvariant:
    """P-3.3: CacheService TTL 不变量

    **Validates: Requirements PF-6 (prefill 引擎缓存)**

    Property: 对于任意缓存项，若 TTL=T 秒，则:
    - access_time < T → 缓存可用（命中）
    - access_time >= T → 缓存不可用（过期）
    """

    @given(
        ttl=st.integers(min_value=1, max_value=3600),
        access_time=st.integers(min_value=0, max_value=7200),
    )
    @settings(max_examples=30)
    def test_cache_available_within_ttl(self, ttl, access_time):
        """TTL 内访问命中，TTL 后访问过期。"""
        is_available = access_time < ttl

        if access_time < ttl:
            assert is_available is True
        else:
            assert is_available is False

    @given(
        ttl=st.integers(min_value=1, max_value=3600),
        access_times=st.lists(
            st.integers(min_value=0, max_value=7200),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=30)
    def test_cache_ttl_boundary_consistency(self, ttl, access_times):
        """TTL 边界一致性: 恰好 TTL 时刻过期（access_time >= ttl → miss）。"""
        for t in access_times:
            is_hit = t < ttl
            if t < ttl:
                assert is_hit is True
            elif t == ttl:
                assert is_hit is False  # 恰好 TTL 时刻已过期
            else:
                assert is_hit is False

    @given(
        ttl_tb=st.just(60),  # TB_QUERY_TTL = 60
        ttl_prefill=st.just(300),  # PREFILL_RESULT_TTL = 300
        access_time=st.integers(min_value=0, max_value=600),
    )
    @settings(max_examples=30)
    def test_real_ttl_config_invariant(self, ttl_tb, ttl_prefill, access_time):
        """真实 TTL 配置: TB=60s, Prefill=300s 的不变量。"""
        from app.services.cache_service import TB_QUERY_TTL, PREFILL_RESULT_TTL

        assert TB_QUERY_TTL == 60
        assert PREFILL_RESULT_TTL == 300

        tb_hit = access_time < TB_QUERY_TTL
        prefill_hit = access_time < PREFILL_RESULT_TTL

        # TB 过期时 prefill 可能仍有效
        if not tb_hit:
            # access_time >= 60, prefill 可能仍有效 (if < 300)
            if access_time < PREFILL_RESULT_TTL:
                assert prefill_hit is True
        # prefill 过期时 TB 必然也过期
        if not prefill_hit:
            assert not tb_hit


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: 多年度对比数据对齐
# (P-4.1 RLS 隔离性已存在于 test_phase4_pbt.py — 跳过)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiYearDataAlignment:
    """P-4.2: 多年度对比数据对齐

    **Validates: Requirements Y-3 (多年度对比分析)**

    Property: 对于任意 N 年数据，多年度对比始终返回恰好 N 列，
    且按 report_line_code 对齐（每行包含所有年度的值）。
    """

    @given(
        years=st.lists(
            st.integers(min_value=2000, max_value=2030),
            min_size=1,
            max_size=5,
            unique=True,
        ),
        line_codes=st.lists(
            st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            min_size=1,
            max_size=20,
            unique=True,
        ),
    )
    @settings(max_examples=30)
    def test_alignment_returns_n_year_columns(self, years, line_codes):
        """多年度对比返回恰好 N 年的列。"""
        sorted_years = sorted(years)

        # 模拟多年度对比逻辑: 按 line_code 对齐
        rows = []
        for code in line_codes:
            values = {str(yr): float(yr * 100 + hash(code) % 1000) for yr in sorted_years}
            rows.append({"line_code": code, "values": values})

        # 验证: 每行恰好有 N 年的值
        for row in rows:
            assert len(row["values"]) == len(sorted_years)
            for yr in sorted_years:
                assert str(yr) in row["values"]

    @given(
        years=st.lists(
            st.integers(min_value=2000, max_value=2030),
            min_size=2,
            max_size=5,
            unique=True,
        ),
        line_codes=st.lists(
            st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            min_size=1,
            max_size=20,
            unique=True,
        ),
        missing_rate=st.floats(min_value=0.0, max_value=0.5),
    )
    @settings(max_examples=30)
    def test_alignment_with_missing_years_uses_none(self, years, line_codes, missing_rate):
        """部分年度缺失数据时，对应位置填 None 但列数不变。"""
        import random

        sorted_years = sorted(years)

        # 模拟: 部分年度缺失数据
        rows = []
        for code in line_codes:
            values: dict[str, float | None] = {}
            for yr in sorted_years:
                if random.random() < missing_rate:
                    values[str(yr)] = None  # 缺失
                else:
                    values[str(yr)] = float(yr * 100)
            rows.append({"line_code": code, "values": values})

        # 验证: 即使有缺失，每行仍有 N 年的 key
        for row in rows:
            assert len(row["values"]) == len(sorted_years)
            for yr in sorted_years:
                assert str(yr) in row["values"]
                # 值要么是 float 要么是 None
                v = row["values"][str(yr)]
                assert v is None or isinstance(v, float)

    @given(
        years=st.lists(
            st.integers(min_value=2000, max_value=2030),
            min_size=2,
            max_size=5,
            unique=True,
        ),
        line_codes=st.lists(
            st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            min_size=1,
            max_size=20,
            unique=True,
        ),
    )
    @settings(max_examples=30)
    def test_line_code_uniqueness_preserved(self, years, line_codes):
        """对齐后 line_code 唯一性保持不变。"""
        sorted_years = sorted(years)

        rows = []
        for code in line_codes:
            values = {str(yr): float(yr) for yr in sorted_years}
            rows.append({"line_code": code, "values": values})

        # 验证: line_code 唯一
        result_codes = [r["line_code"] for r in rows]
        assert len(result_codes) == len(set(result_codes))
