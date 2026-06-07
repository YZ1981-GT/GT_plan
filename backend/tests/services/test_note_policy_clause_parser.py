"""Tests for backend/app/services/note_policy_clause_parser.py

验证：
1. 从会计政策长文本解析标题层级
2. clause_id 生成规则：显式 ID → semantic_section_id + heading_path_hash → 重复追加序号
3. 标题改名但路径不变时保留 clause_id 并标记 title_changed
4. 三栏对比 diff_status 生成
5. 批量确认 unchanged 条款
6. PBT: 解析结果 clause_id 唯一且非空

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_policy_clause_parser import (
    batch_confirm_unchanged,
    compare_clauses,
    generate_clause_id,
    parse_policy_text_to_clauses,
    reconcile_clause_ids_on_rename,
    _detect_heading_level,
    _extract_title,
    _detect_variables,
)


# ===========================================================================
# 5.1 标题层级解析测试
# ===========================================================================


class TestDetectHeadingLevel:
    """标题层级检测测试"""

    def test_level1_full_width_number(self) -> None:
        """一、二、三、等全角编号 → level 1"""
        assert _detect_heading_level("一、存货") == 1
        assert _detect_heading_level("二、固定资产") == 1
        assert _detect_heading_level("十二、长期股权投资") == 1

    def test_level1_parenthesis(self) -> None:
        """（一）（二）等括号编号 → level 1"""
        assert _detect_heading_level("（一）收入确认") == 1
        assert _detect_heading_level("（二）金融工具") == 1

    def test_level2_dot(self) -> None:
        """1. 2. 3. 等数字点号 → level 2"""
        assert _detect_heading_level("1. 一般规定") == 2
        assert _detect_heading_level("2. 特殊规定") == 2
        assert _detect_heading_level("12. 其他") == 2

    def test_level2_parenthesis(self) -> None:
        """(1) (2) 等半角括号 → level 2"""
        assert _detect_heading_level("(1) 定义") == 2
        assert _detect_heading_level("(2) 分类") == 2

    def test_level2_chinese_comma(self) -> None:
        """1、2、3、等数字顿号 → level 2"""
        assert _detect_heading_level("1、存货跌价准备") == 2
        assert _detect_heading_level("2、计提方法") == 2

    def test_level3_circle_number(self) -> None:
        """① ② ③ 等圆圈编号 → level 3"""
        assert _detect_heading_level("①按账龄分析法计提") == 3
        assert _detect_heading_level("②个别认定法") == 3

    def test_level3_alpha_parenthesis(self) -> None:
        """(a) (b) 等字母括号 → level 3"""
        assert _detect_heading_level("(a) 第一类") == 3

    def test_level3_alpha_dot(self) -> None:
        """a. b. 等字母点号 → level 3"""
        assert _detect_heading_level("a. 第一种情况") == 3

    def test_non_heading_line(self) -> None:
        """普通内容行 → None"""
        assert _detect_heading_level("本公司采用成本法核算存货。") is None
        assert _detect_heading_level("") is None
        assert _detect_heading_level("   ") is None


class TestExtractTitle:
    """标题文本提取测试"""

    def test_strips_level1_prefix(self) -> None:
        assert _extract_title("一、存货") == "存货"
        assert _extract_title("（一）收入确认") == "收入确认"

    def test_strips_level2_prefix(self) -> None:
        assert _extract_title("1. 一般规定") == "一般规定"
        assert _extract_title("(1) 定义") == "定义"
        assert _extract_title("1、存货跌价准备") == "存货跌价准备"

    def test_strips_level3_prefix(self) -> None:
        assert _extract_title("①按账龄分析法计提") == "按账龄分析法计提"
        assert _extract_title("(a) 第一类") == "第一类"


# ===========================================================================
# 5.1 完整解析测试
# ===========================================================================


class TestParsePolicyTextToClauses:
    """政策文本解析主函数测试"""

    def test_parses_simple_policy_text(self) -> None:
        """简单两级结构解析"""
        text = """一、存货
本公司存货包括原材料、在产品、产成品等。

二、固定资产
本公司固定资产按成本计量。
"""
        result = parse_policy_text_to_clauses(text, "policy")
        assert len(result) == 2
        assert result[0]["title"] == "存货"
        assert result[0]["level"] == 1
        assert "原材料" in (result[0]["current_text"] or "")
        assert result[1]["title"] == "固定资产"
        assert result[1]["level"] == 1

    def test_parses_nested_headings(self) -> None:
        """嵌套标题层级解析"""
        text = """（一）收入确认
1. 一般规定
本公司按照合同约定确认收入。
2. 特殊规定
对于分期收款合同，按权责发生制确认。
"""
        result = parse_policy_text_to_clauses(text, "policy")
        assert len(result) == 3
        assert result[0]["title"] == "收入确认"
        assert result[0]["level"] == 1
        assert result[1]["title"] == "一般规定"
        assert result[1]["level"] == 2
        assert result[2]["title"] == "特殊规定"
        assert result[2]["level"] == 2

    def test_empty_text_returns_empty(self) -> None:
        """空文本返回空列表"""
        assert parse_policy_text_to_clauses("") == []
        assert parse_policy_text_to_clauses("   ") == []

    def test_detects_variables(self) -> None:
        """检测模板变量"""
        text = """一、概述
{{company_name}}（以下简称"本公司"）成立于{{year}}年。
"""
        result = parse_policy_text_to_clauses(text, "policy")
        assert len(result) == 1
        assert "company_name" in result[0]["variables"]
        assert "year" in result[0]["variables"]

    def test_all_clauses_have_clause_id(self) -> None:
        """所有条款都有 clause_id"""
        text = """一、存货
内容A
二、固定资产
内容B
三、无形资产
内容C
"""
        result = parse_policy_text_to_clauses(text, "section_policy")
        assert all(c["clause_id"] for c in result)
        # clause_id 唯一
        ids = [c["clause_id"] for c in result]
        assert len(ids) == len(set(ids))


# ===========================================================================
# 5.2 clause_id 生成规则
# ===========================================================================


class TestGenerateClauseId:
    """clause_id 生成规则测试"""

    def test_explicit_id_used_directly(self) -> None:
        """显式 ID 直接使用"""
        existing: set[str] = set()
        cid = generate_clause_id("policy", ["收入确认"], existing, explicit_id="policy_revenue")
        assert cid == "policy_revenue"
        assert "policy_revenue" in existing

    def test_semantic_section_id_plus_hash(self) -> None:
        """无显式 ID → semantic_section_id + heading_path_hash"""
        existing: set[str] = set()
        cid = generate_clause_id("policy", ["存货", "跌价准备"], existing)
        assert cid.startswith("policy_")
        assert len(cid) > len("policy_")
        assert cid in existing

    def test_duplicate_heading_path_gets_suffix(self) -> None:
        """重复 heading path 追加序号"""
        existing: set[str] = set()
        cid1 = generate_clause_id("policy", ["存货"], existing)
        cid2 = generate_clause_id("policy", ["存货"], existing)
        assert cid1 != cid2
        assert cid2.endswith("_2")

    def test_empty_semantic_section_id(self) -> None:
        """空 semantic_section_id → 仅用 hash"""
        existing: set[str] = set()
        cid = generate_clause_id("", ["收入确认"], existing)
        assert cid  # 非空
        assert "_" not in cid or len(cid) == 8  # 纯 hash 8 位

    def test_explicit_id_conflict_gets_suffix(self) -> None:
        """显式 ID 冲突时追加序号"""
        existing: set[str] = {"policy_revenue"}
        cid = generate_clause_id("policy", ["收入确认"], existing, explicit_id="policy_revenue")
        assert cid == "policy_revenue_2"


# ===========================================================================
# 5.3 标题改名保留 clause_id
# ===========================================================================


class TestReconcileClauseIdsOnRename:
    """标题改名但路径不变时保留 clause_id"""

    def test_title_rename_preserves_clause_id(self) -> None:
        """标题改名但位置不变 → 保留旧 clause_id + title_changed 标记"""
        old_clauses = [
            {"clause_id": "policy_abc123", "title": "存货", "level": 1},
            {"clause_id": "policy_def456", "title": "固定资产", "level": 1},
        ]
        new_clauses = [
            {"clause_id": "policy_new1", "title": "存货（修订）", "level": 1},
            {"clause_id": "policy_new2", "title": "固定资产", "level": 1},
        ]
        result = reconcile_clause_ids_on_rename(new_clauses, old_clauses)

        # 第一个条款：标题改了 → 保留旧 ID
        assert result[0]["clause_id"] == "policy_abc123"
        assert result[0]["title_changed"] is True
        assert result[0]["previous_title"] == "存货"

        # 第二个条款：标题没变 → 不标记 title_changed
        assert result[1]["clause_id"] == "policy_new2"  # 标题相同不触发
        assert "title_changed" not in result[1]

    def test_level_mismatch_does_not_reconcile(self) -> None:
        """层级不同不做匹配"""
        old_clauses = [
            {"clause_id": "old_id", "title": "存货", "level": 1},
        ]
        new_clauses = [
            {"clause_id": "new_id", "title": "存货详情", "level": 2},
        ]
        result = reconcile_clause_ids_on_rename(new_clauses, old_clauses)
        assert result[0]["clause_id"] == "new_id"
        assert "title_changed" not in result[0]

    def test_empty_old_clauses(self) -> None:
        """无旧条款 → 直接返回新条款"""
        new_clauses = [{"clause_id": "new_id", "title": "存货", "level": 1}]
        result = reconcile_clause_ids_on_rename(new_clauses, [])
        assert result == new_clauses


# ===========================================================================
# 5.5/5.6 三栏对比测试
# ===========================================================================


class TestCompareClauses:
    """三栏对比 diff_status 生成"""

    def test_unchanged_clause(self) -> None:
        """内容完全一致 → unchanged"""
        current = [{"clause_id": "c1", "current_text": "内容A", "title": "T", "level": 1}]
        prior = [{"clause_id": "c1", "current_text": "内容A", "title": "T", "level": 1}]
        template = [{"clause_id": "c1", "current_text": "内容A", "title": "T", "level": 1}]

        result = compare_clauses(current, prior, template)
        assert result[0]["diff_status"] == "unchanged"
        assert result[0]["prior_year_text"] == "内容A"
        assert result[0]["template_text"] == "内容A"

    def test_changed_clause(self) -> None:
        """与上年不同 → changed"""
        current = [{"clause_id": "c1", "current_text": "新内容", "title": "T", "level": 1}]
        prior = [{"clause_id": "c1", "current_text": "旧内容", "title": "T", "level": 1}]
        template = [{"clause_id": "c1", "current_text": "模板内容", "title": "T", "level": 1}]

        result = compare_clauses(current, prior, template)
        assert result[0]["diff_status"] == "changed"

    def test_added_clause(self) -> None:
        """上年和模板都没有 → added"""
        current = [{"clause_id": "c_new", "current_text": "新条款", "title": "新", "level": 1}]
        result = compare_clauses(current, [], [])
        assert result[0]["diff_status"] == "added"

    def test_removed_clause(self) -> None:
        """上年有但本年没有 → removed"""
        current: list[dict] = []
        prior = [{"clause_id": "c_old", "current_text": "旧条款", "title": "旧", "level": 1}]
        result = compare_clauses(current, prior, [])
        assert len(result) == 1
        assert result[0]["diff_status"] == "removed"
        assert result[0]["current_text"] is None


# ===========================================================================
# 5.7 批量确认
# ===========================================================================


class TestBatchConfirmUnchanged:
    """批量确认 unchanged 条款"""

    def test_confirms_unchanged_pending(self) -> None:
        """unchanged + pending → confirmed"""
        clauses = [
            {"clause_id": "c1", "diff_status": "unchanged", "confirm_status": "pending"},
            {"clause_id": "c2", "diff_status": "changed", "confirm_status": "pending"},
            {"clause_id": "c3", "diff_status": "unchanged", "confirm_status": "confirmed"},
        ]
        result = batch_confirm_unchanged(clauses)
        assert result[0]["confirm_status"] == "confirmed"
        assert result[1]["confirm_status"] == "pending"  # changed 不动
        assert result[2]["confirm_status"] == "confirmed"  # 已 confirmed 不变

    def test_does_not_mutate_original(self) -> None:
        """不修改原始列表"""
        clauses = [{"clause_id": "c1", "diff_status": "unchanged", "confirm_status": "pending"}]
        result = batch_confirm_unchanged(clauses)
        assert clauses[0]["confirm_status"] == "pending"
        assert result[0]["confirm_status"] == "confirmed"


# ===========================================================================
# 变量检测
# ===========================================================================


class TestDetectVariables:
    """模板变量检测"""

    def test_detects_standard_variables(self) -> None:
        text = "{{company_name}}成立于{{year}}年"
        assert _detect_variables(text) == ["company_name", "year"]

    def test_no_variables(self) -> None:
        assert _detect_variables("普通文本无变量") == []

    def test_empty_text(self) -> None:
        assert _detect_variables("") == []


# ===========================================================================
# PBT: 解析结果 clause_id 唯一且非空
# ===========================================================================


# 生成策略：模拟会计政策文本
heading_prefixes_l1 = ["一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、"]
heading_prefixes_l2 = ["1. ", "2. ", "3. ", "4. ", "5. "]

policy_text_strategy = st.builds(
    lambda sections: "\n".join(sections),
    sections=st.lists(
        st.builds(
            lambda prefix, title, body: f"{prefix}{title}\n{body}",
            prefix=st.sampled_from(heading_prefixes_l1 + heading_prefixes_l2),
            title=st.text(
                alphabet=st.sampled_from(list("存货固定资产无形资产收入确认金融工具长期股权投资")),
                min_size=2,
                max_size=6,
            ),
            body=st.text(
                alphabet=st.sampled_from(list("本公司采用成本法核算。按照准则规定进行处理。")),
                min_size=5,
                max_size=30,
            ),
        ),
        min_size=1,
        max_size=8,
    ),
)


class TestParsePolicyClausesPBT:
    """Property-based tests for parse_policy_text_to_clauses

    **Validates: Requirements 1.1**
    """

    @settings(max_examples=5)
    @given(text=policy_text_strategy)
    def test_all_clauses_have_non_empty_unique_clause_id(self, text: str) -> None:
        """P1: 所有解析出的条款都有非空且唯一的 clause_id"""
        result = parse_policy_text_to_clauses(text, "test_section")
        if not result:
            return  # 无标题行是合法输入
        ids = [c["clause_id"] for c in result]
        # 非空
        assert all(cid and isinstance(cid, str) and cid.strip() for cid in ids), (
            f"Found empty clause_id in: {ids}"
        )
        # 唯一
        assert len(ids) == len(set(ids)), f"Duplicate clause_ids: {ids}"

    @settings(max_examples=5)
    @given(text=policy_text_strategy)
    def test_all_clauses_have_valid_level(self, text: str) -> None:
        """P2: 所有条款的 level 在 1-3 范围内"""
        result = parse_policy_text_to_clauses(text, "test_section")
        for clause in result:
            assert clause["level"] in (1, 2, 3), (
                f"Invalid level {clause['level']} for clause: {clause['title']}"
            )
