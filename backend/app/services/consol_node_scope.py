"""合并节点作用域与附注行访问。

该模块是附注、custom query 和节点级读写共用的身份边界：
- node_key 只能由当前项目、当前审计年度的企业树精确确认；
- ``node_key is None`` 是旧调用专用的 legacy NULL 作用域；
- 根节点读取可以兼容 legacy 行，但写入永远落到节点专属行。
"""

from __future__ import annotations

import copy
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
    """解析节点键：query 与兼容 body 必须一致，query 作为唯一有效来源。

    旧客户端可能把 ``node_key`` 放在 JSON body；新客户端放在 query。两者
    同时存在时，显式冲突直接拒绝，避免“query 优先”掩盖调用方把两个节点
    混在一起的错误。空字符串同样是无效输入，不降级为 legacy NULL 作用域。
    """
    body_value = body.get("node_key") if isinstance(body, dict) else None
    query_present = query_node_key is not None
    # Pydantic 的可选字段在 model_dump() 中会带 None；None 表示旧请求省略，
    # 只有非 None 值才构成 body 侧的显式 node_key。
    body_present = isinstance(body, dict) and body.get("node_key") is not None

    if query_present and (not isinstance(query_node_key, str) or not query_node_key):
        raise NodeScopeError(
            "node_key 不能为空字符串；省略参数表示 legacy 模式，传入则必须是当前企业树中的完整节点键"
        )
    if body_present and (not isinstance(body_value, str) or not body_value):
        raise NodeScopeError(
            "node_key 不能为空字符串；省略参数表示 legacy 模式，传入则必须是当前企业树中的完整节点键"
        )
    if query_present and body_present and query_node_key != body_value:
        raise NodeScopeError(
            "query 参数 node_key 与请求体 node_key 冲突，请只提交同一个企业树节点",
            status=400,
        )
    if query_present:
        return query_node_key
    if body_present:
        return body_value
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
    if year != effective_year:
        raise NodeScopeError(
            f"请求年度 {year} 与项目有效审计年度 {effective_year} 不一致",
            status=400,
        )

    # 无 node_key — legacy 作用域
    if not node_key or not isinstance(node_key, str):
        return NodeScope(
            project_id=project_id,
            year=effective_year,
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
        year=effective_year,
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


async def _load_exact_note_record(
    db: AsyncSession,
    scope: NodeScope,
    *,
    for_update: bool = False,
    populate_existing: bool = False,
) -> ConsolNoteData | None:
    """只按当前四元组读取一行，不执行根节点 legacy 回退。"""
    if not scope.section_id:
        raise NodeScopeError("读取附注行必须提供 section_id")

    stmt = sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == scope.project_id,
        ConsolNoteData.year == scope.year,
        ConsolNoteData.section_id == scope.section_id,
        _note_scope_filter(scope),
    )
    if for_update:
        stmt = stmt.with_for_update()
    if populate_existing:
        stmt = stmt.execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


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

    record = await _load_exact_note_record(db, scope, for_update=for_update)
    if record is not None or not scope.is_root_consol or not allow_root_legacy_fallback:
        return record

    # 根合并节点回退读 legacy NULL 行；写入复制时也必须锁住该基线。
    return await _load_exact_note_record(
        db,
        NodeScope(
            project_id=scope.project_id,
            year=scope.year,
            section_id=scope.section_id,
        ),
        for_update=for_update,
    )


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
    """按作用域保存附注行，节点写入不更新 NULL legacy 行。

    PUT 的 ``data`` 是完整快照，因此保存时替换目标行的数据；无论是已有行还是
    从 legacy 首次复制，都会深拷贝请求对象，避免嵌套 rows/单元格对象共享引用。
    显式根节点首次保存会读取并锁定 legacy 行，仅继承其 ``is_stale`` 状态；
    legacy 的数据、时间和身份始终不被修改。创建竞争由 V177 唯一约束裁决，
    SAVEPOINT 回滚后重读赢家并应用本次快照，保持外层事务可继续。
    """
    if not scope.section_id:
        raise NodeScopeError("保存附注行必须提供 section_id")
    if not isinstance(data, dict):
        raise NodeScopeError("附注数据必须是对象")

    if now is None:
        now = datetime.now(timezone.utc)

    # 先锁定精确目标。显式节点绝不把根 legacy fallback 当成写入目标。
    record = await _load_exact_note_record(db, scope, for_update=True)
    if record is not None:
        record.data = copy.deepcopy(data)
        record.updated_at = now
        return record

    inherited_stale = bool(scope.node_key)
    if scope.node_key is not None and scope.is_root_consol:
        # 根节点首次写入：legacy 只作为基线读取，最终仍创建 node_key 专属行。
        legacy_scope = NodeScope(
            project_id=scope.project_id,
            year=scope.year,
            section_id=scope.section_id,
        )
        legacy = await _load_exact_note_record(db, legacy_scope, for_update=True)
        if legacy is not None:
            inherited_stale = bool(legacy.is_stale)

    candidate = ConsolNoteData(
        project_id=scope.project_id,
        year=scope.year,
        section_id=scope.section_id,
        node_key=scope.node_key,
        data=copy.deepcopy(data),
        # stale 表示数据是否等待上游刷新，不是“是否已经完成节点复制”。
        # 新显式节点没有 legacy 基线时沿用历史约定标 stale；从 legacy 复制时
        # 保留源状态；旧 NULL 行保持 fresh。
        is_stale=inherited_stale if scope.node_key is not None else False,
        updated_at=now,
    )

    try:
        # 必须在 SAVEPOINT 建立后 add，避免失败候选污染外层事务。
        async with db.begin_nested():
            db.add(candidate)
            await db.flush()
    except IntegrityError as exc:
        # SAVEPOINT 已经退出并回滚；此时才能查询，不会触发 PendingRollbackError。
        winner = await _load_exact_note_record(
            db, scope, populate_existing=True,
        )
        if winner is None:
            original = getattr(exc, "orig", exc)
            text = str(original).lower()
            pgcode = getattr(original, "pgcode", None)
            is_unique = pgcode == "23505" or "unique constraint" in text or "duplicate key" in text
            if is_unique:
                raise NodeScopeError("附注行并发冲突，请重试", status=409) from exc
            raise
        winner.data = copy.deepcopy(data)
        winner.updated_at = now
        await db.flush()
        return winner

    return candidate


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
