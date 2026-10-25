"""Tests for formula_runtime.source_scope — 公式来源范围解析。

spec: consol-node-key-isolation-and-shared-context 任务 8.5
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.formula_runtime.source_scope import (
    DEFAULT_SCOPE_DOMAINS,
    ResolvedSourceScope,
    parse_source_scope,
    resolve_scope_with_tree,
)

PROJECT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
CHILD_PROJECT = uuid.UUID("20000000-0000-0000-0000-000000000002")


class TestParseSourceScope:
    def test_none_returns_none(self):
        assert parse_source_scope(None) is None

    def test_empty_dict_returns_none(self):
        assert parse_source_scope({}) is None

    def test_missing_project_id_returns_none(self):
        assert parse_source_scope({"year": 2025}) is None

    def test_missing_year_returns_none(self):
        assert parse_source_scope({"project_id": str(PROJECT_ID)}) is None

    def test_valid_minimal(self):
        result = parse_source_scope({
            "project_id": str(PROJECT_ID),
            "year": 2025,
        })
        assert result is not None
        assert result.project_id == PROJECT_ID
        assert result.year == 2025
        assert result.node_key is None
        assert result.include_descendants is True
        assert result.domains == DEFAULT_SCOPE_DOMAINS

    def test_valid_full(self):
        result = parse_source_scope({
            "project_id": str(PROJECT_ID),
            "year": 2025,
            "node_key": "A001:subsidiary",
            "include_descendants": False,
            "domains": ["report", "note"],
        })
        assert result is not None
        assert result.node_key == "A001:subsidiary"
        assert result.include_descendants is False
        assert result.domains == frozenset({"report", "note"})

    def test_invalid_project_id_returns_none(self):
        assert parse_source_scope({"project_id": "not-a-uuid", "year": 2025}) is None


class TestResolveWithTree:

    @pytest.mark.asyncio
    async def test_no_node_key_returns_project_only(self):
        scope = ResolvedSourceScope(
            project_id=PROJECT_ID, year=2025, node_key=None,
        )
        result = await resolve_scope_with_tree(None, scope)
        assert result.resolved_project_ids == (PROJECT_ID,)
        assert result.resolved_node_keys == ()

    @pytest.mark.asyncio
    async def test_node_key_resolves_descendants(self):
        # 构造企业树 mock
        root_node = MagicMock()
        root_node.node_key = "ROOT:consol"
        root_node.host_project_id = PROJECT_ID

        child_node = MagicMock()
        child_node.node_key = "A001:subsidiary"
        child_node.host_project_id = CHILD_PROJECT

        with patch("app.services.consol_tree_service.build_tree", new_callable=AsyncMock) as mock_build, \
             patch("app.services.consol_tree_service.find_node_by_key") as mock_find, \
             patch("app.services.consol_tree_service.get_descendants") as mock_desc:

            mock_build.return_value = root_node
            mock_find.return_value = root_node
            mock_desc.return_value = [child_node]

            scope = ResolvedSourceScope(
                project_id=PROJECT_ID, year=2025, node_key="ROOT:consol",
                include_descendants=True,
            )
            result = await resolve_scope_with_tree(MagicMock(), scope)

            assert "ROOT:consol" in result.resolved_node_keys
            assert "A001:subsidiary" in result.resolved_node_keys
            assert PROJECT_ID in result.resolved_project_ids
            assert CHILD_PROJECT in result.resolved_project_ids

    @pytest.mark.asyncio
    async def test_node_key_not_found_returns_original(self):
        root_node = MagicMock()
        root_node.node_key = "ROOT:consol"

        with patch("app.services.consol_tree_service.build_tree", new_callable=AsyncMock) as mock_build, \
             patch("app.services.consol_tree_service.find_node_by_key") as mock_find:

            mock_build.return_value = root_node
            mock_find.return_value = None  # 节点不存在

            scope = ResolvedSourceScope(
                project_id=PROJECT_ID, year=2025, node_key="NONEXISTENT:consol",
            )
            result = await resolve_scope_with_tree(MagicMock(), scope)

            # 返回原始 scope，不含解析后的子树
            assert result.resolved_node_keys == ()

    @pytest.mark.asyncio
    async def test_no_tree_returns_original(self):
        with patch("app.services.consol_tree_service.build_tree", new_callable=AsyncMock) as mock_build:
            mock_build.return_value = None

            scope = ResolvedSourceScope(
                project_id=PROJECT_ID, year=2025, node_key="ROOT:consol",
            )
            result = await resolve_scope_with_tree(MagicMock(), scope)
            assert result.resolved_node_keys == ()

    @pytest.mark.asyncio
    async def test_include_descendants_false(self):
        root_node = MagicMock()
        root_node.node_key = "ROOT:consol"
        root_node.host_project_id = PROJECT_ID

        child_node = MagicMock()
        child_node.node_key = "A001:subsidiary"
        child_node.host_project_id = CHILD_PROJECT

        with patch("app.services.consol_tree_service.build_tree", new_callable=AsyncMock) as mock_build, \
             patch("app.services.consol_tree_service.find_node_by_key") as mock_find, \
             patch("app.services.consol_tree_service.get_descendants") as mock_desc:

            mock_build.return_value = root_node
            mock_find.return_value = root_node
            mock_desc.return_value = [child_node]

            scope = ResolvedSourceScope(
                project_id=PROJECT_ID, year=2025, node_key="ROOT:consol",
                include_descendants=False,
            )
            result = await resolve_scope_with_tree(MagicMock(), scope)

            # include_descendants=False 时不调用 get_descendants
            assert result.resolved_node_keys == ("ROOT:consol",)
            mock_desc.assert_not_called()
