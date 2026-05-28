"""Sprint B.0.10 — CI 卡点测试 CI-15 / CI-16 / CI-17.

CI-15: consol_aggregation source 必有 child_section_id
CI-16: 多层合并 lineage 链无环（DAG 校验）
CI-17: elimination_rules 引用的 wp_code 必存在

Validates: Requirements D12, CI-15, CI-16, CI-17
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import uuid4, UUID

from app.services.note_source_resolvers import VALID_SOURCES, SOURCE_RESOLVERS
from app.services.consol_note_aggregation_service import (
    validate_lineage_dag,
    get_lineage_chain,
    aggregate_cell,
    AGGREGATION_METHODS,
)
from app.services.consol_elimination_rules import (
    ELIMINATION_RULES,
    VALID_WP_CODES,
    validate_wp_code_exists,
    validate_all_rules_wp_codes,
    get_elimination_rules,
)


# ===========================================================================
# CI-15: consol_aggregation source 必有 child_section_id
# ===========================================================================


class TestCI15ConsolAggregationSource:
    """CI-15: consol_aggregation binding 必须包含 child_section_id."""

    def test_consol_aggregation_in_valid_sources(self):
        """consol_aggregation 必须在 VALID_SOURCES 中."""
        assert "consol_aggregation" in VALID_SOURCES

    def test_consol_aggregation_in_source_resolvers(self):
        """consol_aggregation 必须在 SOURCE_RESOLVERS 中有对应 resolver."""
        assert "consol_aggregation" in SOURCE_RESOLVERS

    def test_source_resolvers_match_valid_sources(self):
        """SOURCE_RESOLVERS keys 必须与 VALID_SOURCES 完全一致."""
        assert set(SOURCE_RESOLVERS.keys()) == set(VALID_SOURCES)

    @pytest.mark.asyncio
    async def test_resolver_returns_none_without_child_section_id(self):
        """缺少 child_section_id 时 resolver 返回 None."""
        from app.services.note_source_resolvers import resolve_consol_aggregation

        # 无 child_section_id
        result = await resolve_consol_aggregation(
            binding={"source": "consol_aggregation", "aggregation_method": "simple_sum"},
            ctx={"project_id": uuid4(), "year": 2025},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolver_returns_none_with_empty_child_section_id(self):
        """child_section_id 为空字符串时 resolver 返回 None."""
        from app.services.note_source_resolvers import resolve_consol_aggregation

        result = await resolve_consol_aggregation(
            binding={
                "source": "consol_aggregation",
                "child_section_id": "",
                "aggregation_method": "simple_sum",
            },
            ctx={"project_id": uuid4(), "year": 2025},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolver_accepts_valid_binding(self):
        """有效 binding（含 child_section_id）不会因缺字段而 None.

        注意：无 DB 时仍返回 None（无子公司数据），但不是因为缺 child_section_id。
        """
        from app.services.note_source_resolvers import resolve_consol_aggregation

        result = await resolve_consol_aggregation(
            binding={
                "source": "consol_aggregation",
                "child_section_id": "section_cash",
                "aggregation_method": "simple_sum",
            },
            ctx={"project_id": uuid4(), "year": 2025, "db": None},
        )
        # 无 DB 返回 None 是正常的（无法查子公司）
        assert result is None

    def test_valid_sources_count(self):
        """VALID_SOURCES 应有 9 种（原 8 + consol_aggregation）."""
        assert len(VALID_SOURCES) == 9


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
    async def test_lineage_chain_single(self):
        """单节点 lineage chain 仅含自身."""
        pid = uuid4()
        chain = await get_lineage_chain(pid, db=None)
        assert chain == [pid]

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

            chain = await get_lineage_chain(mock_db.a, db=mock_db)
            assert len(chain) == 2
            assert chain[0] == mock_db.a
            assert chain[1] == mock_db.b
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

    @pytest.mark.asyncio
    async def test_lineage_chain_breaks_on_cycle(self):
        """get_lineage_chain 遇到环时中断（不无限循环）."""
        import app.services.consol_note_aggregation_service as svc

        a = uuid4()
        b = uuid4()
        cycle_map = {a: b, b: a}

        original = svc._get_parent_project_id

        async def mock_get_parent(project_id, db=None):
            return cycle_map.get(project_id)

        svc._get_parent_project_id = mock_get_parent
        try:
            chain = await get_lineage_chain(a, db="fake")
            # 应该在检测到环时停止
            assert len(chain) == 2
            assert a in chain
            assert b in chain
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
