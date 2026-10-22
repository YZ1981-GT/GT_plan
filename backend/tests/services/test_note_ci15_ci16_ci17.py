"""Sprint B.0.10 — CI 卡点测试 CI-15 / CI-16 / CI-17.

CI-15: 合并附注不走单元格取数源 —— ``consol_aggregation`` 已随 V2 汇总器下线（2026-10-22，
       spec consol-note-header-library-and-node-reaggregate R6.1），个别数按已确认映射从单体附注拉取
CI-16: 多层合并 lineage 链无环（DAG 校验）
CI-17: elimination_rules 引用的 wp_code 必存在

Validates: Requirements D12, CI-15, CI-16, CI-17
"""

from __future__ import annotations

import pytest
from uuid import uuid4, UUID

from app.services.note_source_resolvers import VALID_SOURCES, SOURCE_RESOLVERS, dispatch_resolver
from app.services.consol_note_aggregation_service import validate_lineage_dag
from app.services.consol_elimination_rules import (
    ELIMINATION_RULES,
    VALID_WP_CODES,
    validate_wp_code_exists,
    validate_all_rules_wp_codes,
)


# ===========================================================================
# CI-15: consol_aggregation 取数源已下线
# ===========================================================================


class TestCI15ConsolAggregationRetired:
    """CI-15：合并附注的个别数只从单体附注按映射拉取，单元格取数源里没有「合并汇总」。"""

    def test_consol_aggregation_not_a_source(self):
        assert "consol_aggregation" not in VALID_SOURCES
        assert "consol_aggregation" not in SOURCE_RESOLVERS

    def test_source_resolvers_match_valid_sources(self):
        """SOURCE_RESOLVERS keys 必须与 VALID_SOURCES 完全一致."""
        assert set(SOURCE_RESOLVERS.keys()) == set(VALID_SOURCES)
        assert len(VALID_SOURCES) == 8

    @pytest.mark.asyncio
    async def test_legacy_binding_resolves_to_none(self):
        """残留的旧绑定按「未识别取数源」处理：返回 None，不报错。"""
        result = await dispatch_resolver(
            {"source": "consol_aggregation", "child_section_id": "section_cash"},
            {"project_id": uuid4(), "year": 2025},
        )
        assert result is None


# ===========================================================================
# CI-16: 多层合并 lineage 链无环（DAG 校验）
# ===========================================================================


class TestCI16LineageDAG:
    """CI-16: 多层合并 lineage 链必须是 DAG（无环）."""

    @pytest.mark.asyncio
    async def test_single_node_is_valid(self):
        """单节点（无 parent）是有效 DAG."""
        result = await validate_lineage_dag(uuid4(), db=None)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_with_mock_db_no_cycle(self):
        """模拟无环链路."""

        class MockDB:
            """模拟 DB：A → B → None（无环）."""
            def __init__(self):
                self.a = uuid4()
                self.b = uuid4()
                self._map = {self.a: self.b, self.b: None}

            async def execute(self, query, params):
                pid = UUID(params["pid"])
                parent = self._map.get(pid)

                class Row:
                    def first(self_inner):
                        return (parent,) if parent else None
                return Row()

        # Monkey-patch _get_parent_project_id for this test
        import app.services.consol_note_aggregation_service as svc

        mock_db = MockDB()
        original = svc._get_parent_project_id

        async def mock_get_parent(project_id, db=None):
            if db is mock_db:
                parent = mock_db._map.get(project_id)
                return parent
            return None

        svc._get_parent_project_id = mock_get_parent
        try:
            result = await validate_lineage_dag(mock_db.a, db=mock_db)
            assert result is True
        finally:
            svc._get_parent_project_id = original

    @pytest.mark.asyncio
    async def test_validate_with_mock_db_cycle(self):
        """模拟有环链路 → 返回 False."""
        import app.services.consol_note_aggregation_service as svc

        a = uuid4()
        b = uuid4()
        cycle_map = {a: b, b: a}  # A → B → A（环！）

        original = svc._get_parent_project_id

        async def mock_get_parent(project_id, db=None):
            return cycle_map.get(project_id)

        svc._get_parent_project_id = mock_get_parent
        try:
            result = await validate_lineage_dag(a, db="fake")
            assert result is False
        finally:
            svc._get_parent_project_id = original


# ===========================================================================
# CI-17: elimination_rules 引用的 wp_code 必存在
# ===========================================================================


class TestCI17EliminationWpCode:
    """CI-17: 所有 elimination_rules 引用的 wp_code 必须存在于注册表."""

    def test_all_rules_have_wp_code(self):
        """每个规则必须有非空 wp_code."""
        for rule_type, rule_config in ELIMINATION_RULES.items():
            assert "wp_code" in rule_config, f"{rule_type} missing wp_code"
            assert rule_config["wp_code"], f"{rule_type} has empty wp_code"

    def test_all_wp_codes_in_valid_set(self):
        """所有 wp_code 必须在 VALID_WP_CODES 集合中."""
        for rule_type, rule_config in ELIMINATION_RULES.items():
            wp_code = rule_config["wp_code"]
            assert wp_code in VALID_WP_CODES, (
                f"{rule_type} wp_code '{wp_code}' not in VALID_WP_CODES"
            )

    def test_validate_wp_code_exists_all_pass(self):
        """validate_wp_code_exists 对所有预设规则返回 True."""
        for rule_type in ELIMINATION_RULES:
            assert validate_wp_code_exists(rule_type) is True

    def test_validate_all_rules_no_invalid(self):
        """validate_all_rules_wp_codes 返回空列表（全部合法）."""
        invalid = validate_all_rules_wp_codes()
        assert invalid == []

    def test_rules_have_required_fields(self):
        """每个规则必须有 name / wp_code / match_logic / affects_columns / category."""
        required_fields = {"name", "wp_code", "match_logic", "affects_columns", "category"}
        for rule_type, rule_config in ELIMINATION_RULES.items():
            for field in required_fields:
                assert field in rule_config, (
                    f"{rule_type} missing required field '{field}'"
                )

    def test_four_rules_registered(self):
        """必须有 4 种预设规则."""
        assert len(ELIMINATION_RULES) == 4

    def test_wp_codes_unique(self):
        """所有 wp_code 必须唯一."""
        wp_codes = [r["wp_code"] for r in ELIMINATION_RULES.values()]
        assert len(wp_codes) == len(set(wp_codes))
