"""合并节点作用域与附注行访问。

该模块是附注、custom query 和节点级读写共用的身份边界：
- node_key 只能由当前项目、当前审计年度的企业树精确确认；
- ``node_key is None`` 是旧调用专用的 legacy NULL 作用域；
- 根节点读取可以兼容 legacy 行，但写入永远落到节点专属行。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeAlias

import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.services.consol_group_tree import ROLE_CONSOL, build_group_tree
from app.services.consol_tree_service import TreeNode, find_node_by_key
from app.services.project_audit_year import resolve_project_audit_year


class NodeScopeError(ValueError):
    """请求无法映射到当前项目的合法节点作用域。"""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class NodeScope:
    """一次附注/节点请求的不可变归属。"""

    project_id: UUID
    year: int
    section_id: str | None = None
    node_key: str | None = None
    tree: TreeNode | None = None
    node: TreeNode | None = None

    @property
    def is_root_consol(self) -> bool:
        """当前节点是合并树根节点。"""
        return (
            self.tree is not None
            and self.node is not None
            and self.node is self.tree
            and self.tree.role == ROLE_CONSOL
        )


LegacyScope: TypeAlias = NodeScope


def resolve_requested_node_key(
    query_node_key: str | None,
    body: dict | None = None,
) -> str | None:
    """query 参数优先，兼容旧 body 中的 node_key。

    空字符串是无效输入（不降级为省略）：调用方传了空 node_key 应立即拒绝，
    而不是静默当作 ``None`` 走 legacy 路径。
    """
    if isinstance(query_node_key, str):
        if not query_node_key:
            raise NodeScopeError(
                "node_key 不能为空字符串；省略参数表示 legacy 模式，传入则必须是当前企业树中的完整节点键"
            )
        return query_node_key
    if isinstance(body, dict):
        val = body.get("node_key")
        if isinstance(val, str):
            if not val:
                raise NodeScopeError(
                    "node_key 不能为空字符串；省略参数表示 legacy 模式，传入则必须是当前企业树中的完整节点键"
                )
            return val
    return None


async def resolve_node_scope(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_key: str | None,
    section_id: str | None = None,
) -> NodeScope:
    """验证项目、年度和显式节点，返回后续查询必须使用的作用域。"""
    if isinstance(section_id, str) and not section_id.strip():
        raise NodeScopeError("section_id 不能为空")

    project = (
        await db.execute(
            sa.select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
        )
    ).scalar_one_or_none()
    if project is None:
        raise NodeScopeError("项目不存在", status=404)

    effective_year = resolve_project_audit_year(project)
    if effective_year is None:
        raise NodeScopeError("项目没有有效审计年度")

    # 无 node_key — legacy 作用域
    if not node_key or not isinstance(node_key, str):
        return NodeScope(
            project_id=project_id,
            year=year,
            section_id=section_id,
            node_key=None,
            tree=None,
            node=None,
        )

    # 构建企业树、定位节点
    result = await build_group_tree(db, project_id)
    if result is None or result.root is None:
        raise NodeScopeError(f"请求年度 {year} 无法构建企业树")

    if result.root.role != ROLE_CONSOL:
        raise NodeScopeError(f"请求年度 {year} 无法构建企业树")

    node = find_node_by_key(result.root, node_key)
    if node is None:
        raise NodeScopeError(f"节点 {node_key} 不在当前企业树中", status=404)

    return NodeScope(
        project_id=project_id,
        year=year,
        section_id=section_id,
        node_key=node_key,
        tree=result.root,
        node=node,
    )


def scope_for_tree_node(
    parent: NodeScope,
    node: TreeNode,
    section_id: str | None = None,
) -> NodeScope:
    """从已验证的企业树派生子节点作用域，避免再次按 company_code 推断身份。"""
    if not node.node_key:
        raise NodeScopeError("企业树节点缺少 node_key")
    return NodeScope(
        project_id=parent.project_id,
        year=parent.year,
        section_id=section_id or parent.section_id,
        node_key=node.node_key,
        tree=parent.tree,
        node=node,
    )


def _note_scope_filter(scope: NodeScope):
    """生成附注行的 node_key 过滤条件。"""
    if scope.node_key:
        return ConsolNoteData.node_key == scope.node_key
    return ConsolNoteData.node_key.is_(None)


async def load_scoped_note_record(
    db: AsyncSession,
    scope: NodeScope,
    *,
    allow_root_legacy_fallback: bool = True,
    for_update: bool = False,
) -> ConsolNoteData | None:
    """按作用域读取附注行；只有已验证根节点允许读 NULL legacy 行。"""
    if not scope.section_id:
        raise NodeScopeError("读取附注行必须提供 section_id")

    stmt = (
        sa.select(ConsolNoteData)
        .where(
            ConsolNoteData.project_id == scope.project_id,
            ConsolNoteData.year == scope.year,
            ConsolNoteData.section_id == scope.section_id,
            _note_scope_filter(scope),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()

    record = (await db.execute(stmt)).scalar_one_or_none()
    if record is not None or not scope.is_root_consol or not allow_root_legacy_fallback:
        return record

    # 根合并节点回退读 legacy NULL 行
    legacy = (
        await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == scope.project_id,
                ConsolNoteData.year == scope.year,
                ConsolNoteData.section_id == scope.section_id,
                ConsolNoteData.node_key.is_(None),
            )
        )
    ).scalar_one_or_none()
    return legacy


async def load_scoped_note_records(
    db: AsyncSession,
    scope: NodeScope,
    *,
    allow_root_legacy_fallback: bool = True,
) -> list[ConsolNoteData]:
    """批量读取作用域内附注行，节点专属行优先覆盖 legacy 同章节行。"""
    stmt = (
        sa.select(ConsolNoteData)
        .where(
            ConsolNoteData.project_id == scope.project_id,
            ConsolNoteData.year == scope.year,
        )
    )
    if scope.section_id:
        stmt = stmt.where(ConsolNoteData.section_id == scope.section_id)

    if scope.node_key:
        if scope.is_root_consol and allow_root_legacy_fallback:
            # 根合并节点：取节点专属行与 legacy 行，节点专属行优先
            stmt = stmt.where(
                sa.or_(
                    ConsolNoteData.node_key == scope.node_key,
                    ConsolNoteData.node_key.is_(None),
                )
            )
        else:
            stmt = stmt.where(ConsolNoteData.node_key == scope.node_key)
    else:
        stmt = stmt.where(ConsolNoteData.node_key.is_(None))

    rows = list((await db.execute(stmt.order_by(ConsolNoteData.id))).scalars().all())

    if not scope.is_root_consol or not allow_root_legacy_fallback:
        return rows

    # 节点专属行优先覆盖 legacy 同章节行
    by_section: dict[str, ConsolNoteData] = {}
    for row in rows:
        existing = by_section.get(row.section_id)
        if existing is None or (row.node_key is not None and existing.node_key is None):
            by_section[row.section_id] = row
    return list(by_section.values())


async def save_scoped_note_record(
    db: AsyncSession,
    scope: NodeScope,
    data: dict,
    *,
    now: datetime | None = None,
) -> ConsolNoteData:
    """按作用域保存附注行，节点写入不更新 NULL legacy 行。"""
    if not scope.section_id:
        raise NodeScopeError("保存附注行必须提供 section_id")
    if not isinstance(data, dict):
        raise NodeScopeError("附注数据必须是对象")

    if now is None:
        now = datetime.now(timezone.utc)

    record = await load_scoped_note_record(
        db, scope, allow_root_legacy_fallback=False,
    )

    if record is not None:
        record.data = data
        record.updated_at = now
        return record

    # 根合并节点写入时不更新 legacy 行——直接创建节点专属行
    if scope.is_root_consol and not scope.node_key:
        # legacy 作用域的根节点写入（兼容旧调用）
        legacy = await load_scoped_note_record(
            db, scope, allow_root_legacy_fallback=True,
        )
        if legacy is not None:
            legacy.data = data
            legacy.updated_at = now
            return legacy

    new_record = ConsolNoteData(
        project_id=scope.project_id,
        year=scope.year,
        section_id=scope.section_id,
        node_key=scope.node_key,
        data=data,
        is_stale=bool(scope.node_key),
        updated_at=now,
    )
    async with db.begin_nested():
        db.add(new_record)
        try:
            await db.flush()
        except IntegrityError:
            raise NodeScopeError("附注行并发冲突，请重试", status=409)
    return new_record


__all__ = [
    "NodeScopeError",
    "NodeScope",
    "LegacyScope",
    "resolve_requested_node_key",
    "resolve_node_scope",
    "scope_for_tree_node",
    "load_scoped_note_record",
    "load_scoped_note_records",
    "save_scoped_note_record",
]
