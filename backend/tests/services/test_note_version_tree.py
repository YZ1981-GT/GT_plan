"""Tests for Sprint C.2 — 章节版本图服务 (D11).

Covers:
- C.2.1: fork/merge/diff
- C.2.2: 跨年合并范围变化高亮
- C.2.3: 章节 fork
- C.2.4: 多版本 merge
- CI-14: 版本树无环（DAG）
"""
from __future__ import annotations

import pytest

from app.services.note_section_version_tree_service import (
    NoteSectionVersionTreeService,
    VersionNode,
    VersionTree,
)


@pytest.fixture
def service():
    return NoteSectionVersionTreeService(db=None)


# ---------------------------------------------------------------------------
# VersionTree DAG validation (CI-14)
# ---------------------------------------------------------------------------


class TestVersionTreeDAG:
    """CI-14 — 版本树无环."""

    def test_empty_tree_is_valid(self):
        tree = VersionTree()
        assert tree.validate_dag() is True

    def test_linear_chain_is_valid(self):
        n1 = VersionNode(id="n1", section_id="s1", branch="main")
        n2 = VersionNode(id="n2", section_id="s1", branch="main", parent_node_id="n1")
        n3 = VersionNode(id="n3", section_id="s1", branch="main", parent_node_id="n2")
        tree = VersionTree([n1, n2, n3])
        assert tree.validate_dag() is True

    def test_cycle_detected(self):
        n1 = VersionNode(id="n1", section_id="s1", branch="main", parent_node_id="n2")
        n2 = VersionNode(id="n2", section_id="s1", branch="main", parent_node_id="n1")
        tree = VersionTree([n1, n2])
        assert tree.validate_dag() is False

    def test_branching_is_valid(self):
        n1 = VersionNode(id="n1", section_id="s1", branch="main")
        n2 = VersionNode(id="n2", section_id="s1", branch="main", parent_node_id="n1")
        n3 = VersionNode(id="n3", section_id="s1", branch="dev", parent_node_id="n1")
        tree = VersionTree([n1, n2, n3])
        assert tree.validate_dag() is True

    def test_get_branches(self):
        n1 = VersionNode(id="n1", branch="main")
        n2 = VersionNode(id="n2", branch="dev")
        tree = VersionTree([n1, n2])
        branches = tree.get_branches()
        assert "main" in branches
        assert "dev" in branches


# ---------------------------------------------------------------------------
# C.2.3: Fork
# ---------------------------------------------------------------------------


class TestFork:
    """C.2.3 — 章节 fork."""

    @pytest.mark.asyncio
    async def test_fork_from_empty(self, service):
        node = await service.fork("p1", "s1", "dev", "user1")
        assert node.branch == "dev"
        assert node.parent_node_id is None

    @pytest.mark.asyncio
    async def test_fork_from_main(self, service):
        # Add a main node first
        await service.add_version("p1", "s1", {"key": "value"}, "user1", "main", "v1")
        # Fork
        node = await service.fork("p1", "s1", "feature", "user1", source_branch="main")
        assert node.branch == "feature"
        assert node.parent_node_id is not None
        assert node.snapshot_data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_fork_preserves_dag(self, service):
        await service.add_version("p1", "s1", {}, "user1")
        await service.fork("p1", "s1", "b1", "user1")
        await service.fork("p1", "s1", "b2", "user1")
        tree = await service.get_tree("p1", "s1")
        assert tree.validate_dag() is True


# ---------------------------------------------------------------------------
# C.2.4: Merge
# ---------------------------------------------------------------------------


class TestMerge:
    """C.2.4 — 多版本 merge."""

    @pytest.mark.asyncio
    async def test_merge_ours(self, service):
        await service.add_version("p1", "s1", {"a": 1, "b": 2}, "user1", "main")
        await service.fork("p1", "s1", "dev", "user1")
        await service.add_version("p1", "s1", {"a": 1, "b": 2, "c": 3}, "user1", "dev")

        merged = await service.merge("p1", "s1", "dev", "main", strategy="ours", user_id="user1")
        assert merged.branch == "main"
        # 'ours' keeps main data, adds source-only keys
        assert "c" in merged.snapshot_data

    @pytest.mark.asyncio
    async def test_merge_theirs(self, service):
        await service.add_version("p1", "s1", {"a": 1}, "user1", "main")
        await service.fork("p1", "s1", "dev", "user1")
        await service.add_version("p1", "s1", {"a": 99, "new": "val"}, "user1", "dev")

        merged = await service.merge("p1", "s1", "dev", "main", strategy="theirs", user_id="user1")
        assert merged.snapshot_data["a"] == 99
        assert merged.snapshot_data["new"] == "val"

    @pytest.mark.asyncio
    async def test_merge_nonexistent_source_raises(self, service):
        await service.add_version("p1", "s1", {}, "user1", "main")
        with pytest.raises(ValueError, match="不存在"):
            await service.merge("p1", "s1", "nonexistent", "main", user_id="user1")


# ---------------------------------------------------------------------------
# C.2.1: Diff
# ---------------------------------------------------------------------------


class TestDiff:
    """C.2.1 — diff between nodes."""

    @pytest.mark.asyncio
    async def test_diff_identical(self, service):
        n1 = await service.add_version("p1", "s1", {"a": 1}, "user1")
        n2 = await service.add_version("p1", "s1", {"a": 1}, "user1")
        diffs = await service.diff("p1", "s1", n1.id, n2.id)
        assert len(diffs) == 0

    @pytest.mark.asyncio
    async def test_diff_modify(self, service):
        n1 = await service.add_version("p1", "s1", {"a": 1}, "user1")
        n2 = await service.add_version("p1", "s1", {"a": 2}, "user1")
        diffs = await service.diff("p1", "s1", n1.id, n2.id)
        assert len(diffs) == 1
        assert diffs[0]["type"] == "modify"
        assert diffs[0]["value_a"] == 1
        assert diffs[0]["value_b"] == 2

    @pytest.mark.asyncio
    async def test_diff_add_remove(self, service):
        n1 = await service.add_version("p1", "s1", {"a": 1, "b": 2}, "user1")
        n2 = await service.add_version("p1", "s1", {"a": 1, "c": 3}, "user1")
        diffs = await service.diff("p1", "s1", n1.id, n2.id)
        types = {d["key"]: d["type"] for d in diffs}
        assert types["b"] == "remove"
        assert types["c"] == "add"

    @pytest.mark.asyncio
    async def test_diff_nonexistent_node_raises(self, service):
        await service.add_version("p1", "s1", {}, "user1")
        with pytest.raises(ValueError, match="不存在"):
            await service.diff("p1", "s1", "fake_id", "another_fake")


# ---------------------------------------------------------------------------
# C.2.2: Consol Changes Highlight
# ---------------------------------------------------------------------------


class TestConsolChanges:
    """C.2.2 — 跨年合并范围变化高亮."""

    @pytest.mark.asyncio
    async def test_highlight_returns_list(self, service):
        result = await service.highlight_consol_changes("p1", 2025)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    """Full workflow tests."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, service):
        """Add versions → fork → modify → merge → diff."""
        # Initial versions on main
        v1 = await service.add_version("p1", "s1", {"title": "货币资金", "amount": 100}, "user1", label="初始")
        v2 = await service.add_version("p1", "s1", {"title": "货币资金", "amount": 200}, "user1", label="更新金额")

        # Fork to dev
        fork_node = await service.fork("p1", "s1", "dev", "user2")
        assert fork_node.snapshot_data["amount"] == 200

        # Add version on dev
        v3 = await service.add_version("p1", "s1", {"title": "货币资金", "amount": 300, "note": "新增"}, "user2", "dev")

        # Diff main head vs dev head
        tree = await service.get_tree("p1", "s1")
        main_head = tree.get_branch_head("main")
        dev_head = tree.get_branch_head("dev")
        diffs = await service.diff("p1", "s1", main_head.id, dev_head.id)
        assert len(diffs) == 2  # amount changed + note added

        # Merge dev → main
        merged = await service.merge("p1", "s1", "dev", "main", strategy="theirs", user_id="user1")
        assert merged.snapshot_data["amount"] == 300
        assert merged.snapshot_data["note"] == "新增"

        # Validate DAG
        assert tree.validate_dag() is True
