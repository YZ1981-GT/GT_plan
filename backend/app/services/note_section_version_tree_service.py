"""Sprint C.2 — 章节版本图服务 (D11).

主要 API:
- fork(project_id, section_id, branch_name, user_id) → node_id
- merge(project_id, section_id, source_branch, target_branch, strategy) → merged_node
- diff(project_id, section_id, node_a_id, node_b_id) → list[CellDiff]
- get_tree(project_id, section_id) → VersionTree
- highlight_consol_changes(project_id, year) → list[dict]

纯 async service，依赖 DB session。
CI-14: 版本树无环（DAG 校验）。
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

__all__ = ["NoteSectionVersionTreeService", "VersionNode", "VersionTree"]


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class VersionNode:
    """A node in the version tree (DAG)."""

    __slots__ = ("id", "project_id", "section_id", "branch", "parent_node_id",
                 "snapshot_data", "created_by", "created_at", "label")

    def __init__(
        self,
        *,
        id: str | None = None,
        project_id: str = "",
        section_id: str = "",
        branch: str = "main",
        parent_node_id: str | None = None,
        snapshot_data: dict[str, Any] | None = None,
        created_by: str = "",
        created_at: str | None = None,
        label: str = "",
    ):
        self.id = id or str(uuid.uuid4())
        self.project_id = project_id
        self.section_id = section_id
        self.branch = branch
        self.parent_node_id = parent_node_id
        self.snapshot_data = snapshot_data or {}
        self.created_by = created_by
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.label = label

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "section_id": self.section_id,
            "branch": self.branch,
            "parent_node_id": self.parent_node_id,
            "snapshot_data": self.snapshot_data,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "label": self.label,
        }


class VersionTree:
    """In-memory version tree for a section."""

    def __init__(self, nodes: list[VersionNode] | None = None):
        self.nodes: list[VersionNode] = nodes or []
        self._index: dict[str, VersionNode] = {n.id: n for n in self.nodes}

    def add_node(self, node: VersionNode) -> None:
        self.nodes.append(node)
        self._index[node.id] = node

    def get_node(self, node_id: str) -> VersionNode | None:
        return self._index.get(node_id)

    def get_branches(self) -> list[str]:
        return list(set(n.branch for n in self.nodes))

    def get_branch_head(self, branch: str) -> VersionNode | None:
        """Get the latest node on a branch (last added)."""
        branch_nodes = [n for n in self.nodes if n.branch == branch]
        if not branch_nodes:
            return None
        # Return last added node on this branch (insertion order)
        return branch_nodes[-1]

    def validate_dag(self) -> bool:
        """CI-14: Validate tree is a DAG (no cycles)."""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            if node_id in in_stack:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            in_stack.add(node_id)
            node = self._index.get(node_id)
            if node and node.parent_node_id:
                if has_cycle(node.parent_node_id):
                    return True
            in_stack.discard(node_id)
            return False

        for node_id in self._index:
            if has_cycle(node_id):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "branches": self.get_branches(),
            "is_valid_dag": self.validate_dag(),
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NoteSectionVersionTreeService:
    """章节版本图服务 (Sprint C.2, D11).

    支持 git-like 操作：fork / merge / diff。
    CI-14: 版本树无环（DAG 校验）。
    """

    def __init__(self, db: Any = None):
        self.db = db
        # In-memory store for testing (production uses DB)
        self._trees: dict[str, VersionTree] = {}

    def _get_tree_key(self, project_id: str, section_id: str) -> str:
        return f"{project_id}:{section_id}"

    def _get_or_create_tree(self, project_id: str, section_id: str) -> VersionTree:
        key = self._get_tree_key(project_id, section_id)
        if key not in self._trees:
            self._trees[key] = VersionTree()
        return self._trees[key]

    async def fork(
        self,
        project_id: str,
        section_id: str,
        branch_name: str,
        user_id: str,
        source_branch: str = "main",
        label: str = "",
    ) -> VersionNode:
        """Create a new branch from source branch head (C.2.3).

        Returns the new fork node.
        """
        tree = self._get_or_create_tree(project_id, section_id)

        # Find source branch head
        source_head = tree.get_branch_head(source_branch)
        parent_id = source_head.id if source_head else None
        snapshot = deepcopy(source_head.snapshot_data) if source_head else {}

        # Create fork node
        node = VersionNode(
            project_id=project_id,
            section_id=section_id,
            branch=branch_name,
            parent_node_id=parent_id,
            snapshot_data=snapshot,
            created_by=user_id,
            label=label or f"Fork from {source_branch}",
        )

        tree.add_node(node)

        # CI-14: Validate DAG
        if not tree.validate_dag():
            raise ValueError("版本树出现环路（CI-14 校验失败）")

        return node

    async def merge(
        self,
        project_id: str,
        section_id: str,
        source_branch: str,
        target_branch: str,
        strategy: str = "ours",
        user_id: str = "",
    ) -> VersionNode:
        """Merge source branch into target branch (C.2.4).

        Strategies:
        - 'ours': keep target data, ignore source conflicts
        - 'theirs': use source data for conflicts
        - 'manual': raise for manual resolution (not implemented here)

        Returns the merge commit node.
        """
        tree = self._get_or_create_tree(project_id, section_id)

        source_head = tree.get_branch_head(source_branch)
        target_head = tree.get_branch_head(target_branch)

        if not source_head:
            raise ValueError(f"源分支 '{source_branch}' 不存在")

        # Compute merged snapshot
        source_data = source_head.snapshot_data or {}
        target_data = (target_head.snapshot_data if target_head else {}) or {}

        if strategy == "theirs":
            merged_data = deepcopy(source_data)
            # Overlay target-only keys
            for k, v in target_data.items():
                if k not in merged_data:
                    merged_data[k] = v
        else:  # 'ours' default
            merged_data = deepcopy(target_data)
            # Overlay source-only keys
            for k, v in source_data.items():
                if k not in merged_data:
                    merged_data[k] = v

        # Create merge node on target branch
        node = VersionNode(
            project_id=project_id,
            section_id=section_id,
            branch=target_branch,
            parent_node_id=target_head.id if target_head else None,
            snapshot_data=merged_data,
            created_by=user_id,
            label=f"Merge {source_branch} → {target_branch} ({strategy})",
        )

        tree.add_node(node)

        # CI-14
        if not tree.validate_dag():
            raise ValueError("合并后版本树出现环路（CI-14 校验失败）")

        return node

    async def diff(
        self,
        project_id: str,
        section_id: str,
        node_a_id: str,
        node_b_id: str,
    ) -> list[dict[str, Any]]:
        """Compare two version nodes (C.2.1).

        Returns list of diffs: [{key, value_a, value_b, type}]
        """
        tree = self._get_or_create_tree(project_id, section_id)

        node_a = tree.get_node(node_a_id)
        node_b = tree.get_node(node_b_id)

        if not node_a or not node_b:
            raise ValueError("节点不存在")

        data_a = node_a.snapshot_data or {}
        data_b = node_b.snapshot_data or {}

        diffs: list[dict[str, Any]] = []
        all_keys = set(data_a.keys()) | set(data_b.keys())

        for key in sorted(all_keys):
            val_a = data_a.get(key)
            val_b = data_b.get(key)
            if val_a != val_b:
                if val_a is None:
                    diff_type = "add"
                elif val_b is None:
                    diff_type = "remove"
                else:
                    diff_type = "modify"
                diffs.append({
                    "key": key,
                    "value_a": val_a,
                    "value_b": val_b,
                    "type": diff_type,
                })

        return diffs

    async def get_tree(
        self,
        project_id: str,
        section_id: str,
    ) -> VersionTree:
        """Get the full version tree for a section."""
        return self._get_or_create_tree(project_id, section_id)

    async def add_version(
        self,
        project_id: str,
        section_id: str,
        snapshot_data: dict[str, Any],
        user_id: str,
        branch: str = "main",
        label: str = "",
    ) -> VersionNode:
        """Add a new version node to the tree."""
        tree = self._get_or_create_tree(project_id, section_id)
        head = tree.get_branch_head(branch)

        node = VersionNode(
            project_id=project_id,
            section_id=section_id,
            branch=branch,
            parent_node_id=head.id if head else None,
            snapshot_data=snapshot_data,
            created_by=user_id,
            label=label or f"Version {len(tree.nodes) + 1}",
        )

        tree.add_node(node)
        return node

    async def highlight_consol_changes(
        self,
        project_id: str,
        year: int,
    ) -> list[dict[str, Any]]:
        """Highlight cross-year consolidation scope changes (C.2.2).

        Returns list of changes: [{section_id, change_type, description}]
        """
        # This would compare current year vs prior year consolidation scope
        # Stub implementation — real version queries DB
        return []
