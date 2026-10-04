"""合并附注节点作用域共享解析器（spec consol-node-key-isolation-and-shared-context §三，ADR-CNSC-001/002）。

所有附注端点（GET / PUT / refresh / audit / audit-all / apply-formulas / aggregate / breakdown /
fill-by-formula）共用这里的一套解析与装载规则，不再各自拼 SQL、也不再以字符串后缀判根：

- :func:`requested_node_key`：显式 query 参数优先于兼容 body；空字符串按无效输入拒绝（不降级成省略）。
- :func:`resolve_note_scope`：经**当前企业树**精确校验 node_key，产出 :class:`NodeScope`
  （命中节点，``is_root_consol`` = 树根本身且 role=consol）或 :class:`LegacyScope`（未传键，只认 NULL 行）。
  根身份由企业树判定，**不能**仅凭 ``":consol"`` 后缀（ADR-CNSC-001：同企业多角色会撞车、伪造键会命中）。
- :func:`is_root_consol_node`：给只有树和键、无需重建上下文的调用方（如装载器）复用的根判定。
- :func:`load_scoped_record` / :func:`exact_scoped_record`：节点行 loader（根可回退 legacy）与写入目标 loader
  （从不回退 legacy），委托给 ``consol_note_formula_service`` 已落地的真实实现，保证单一真源。

本模块只读树、不写库；``NoteScopeError`` 由路由转 400 / 404。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_group_tree import ROLE_CONSOL
from app.services.consol_tree_service import TreeNode, find_node_by_key

if TYPE_CHECKING:  # 仅类型标注；运行时按需延迟 import，避免模块级环依赖
    from app.services.consol_report_view_service import ViewContext


class NoteScopeError(ValueError):
    """node_key / 年度与当前企业树不符；``status`` 供路由转 400 / 404。"""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class NodeScope:
    """命中企业树节点的作用域（显式 node_key）。"""

    project_id: UUID
    year: int
    node_key: str
    is_root_consol: bool

    @property
    def allow_legacy_fallback(self) -> bool:
        """只有树根合并节点允许 GET 回退到 NULL legacy 行。"""
        return self.is_root_consol


@dataclass(frozen=True)
class LegacyScope:
    """未传 node_key 的旧调用作用域：读写只匹配 ``node_key IS NULL``。"""

    project_id: UUID
    year: int
    node_key: None = None
    is_root_consol: bool = False

    @property
    def allow_legacy_fallback(self) -> bool:  # legacy 行就是它自己，不存在"回退"
        return False


Scope = NodeScope | LegacyScope


def requested_node_key(query_node_key: str | None, body: dict | None = None) -> str | None:
    """统一入参优先级：显式 query 参数优先于兼容 body ``node_key``。

    - query 为 ``None``（根本没传该参数）才去读 body；
    - query 为**空字符串**是显式的无效输入 ⇒ 原样返回空字符串，由 :func:`resolve_note_scope` 拒绝，
      **不**降级成"等同省略节点键"。
    """
    if query_node_key is not None:
        return query_node_key
    if isinstance(body, dict):
        value = body.get("node_key")
        return value if isinstance(value, str) or value is None else str(value)
    return None


def is_root_consol_node(tree: TreeNode | None, node_key: str | None) -> bool:
    """经**企业树**判定：node_key 命中的是不是树根合并节点（树根本身 + role=consol）。

    ADR-CNSC-001：根身份不能靠 ``node_key.endswith(':consol')`` ——
    ``A:consol`` 这类同企业的子合并节点 role 也是 consol，但它**不是**树根，不得享有 legacy 回退。
    """
    if tree is None or not node_key:
        return False
    return tree.node_key == node_key and tree.role == ROLE_CONSOL


async def resolve_note_scope(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    *,
    node_key: str | None,
) -> Scope:
    """附注端点共用的节点作用域解析（§三.1~§三.5）。

    1. 未传 node_key ⇒ :class:`LegacyScope`（只认 NULL 行，不选任何节点）。
    2. 传了 node_key ⇒ 经当前合并项目企业树校验：
       - 项目不是合并项目 / 没有有效审计年度 ⇒ 404；
       - 空字符串或不在当前树的键 ⇒ 400（禁冒号前缀 / company_code / ``:consol`` 后缀兜底）；
       - 命中 ⇒ :class:`NodeScope`，``is_root_consol`` 经树判定。
    """
    if node_key is None:
        # 旧调用：不建树也能用 NULL 兼容行。年度由调用方按既有口径处理。
        return LegacyScope(project_id=project_id, year=year if year is not None else 0)

    if node_key == "":
        raise NoteScopeError("node_key 不能为空字符串（省略该参数才走旧项目级兼容行）", status=400)

    tree, effective_year = await _load_tree(db, project_id, year)
    node = find_node_by_key(tree, node_key)
    if node is None:
        raise NoteScopeError(f"企业树中没有节点 {node_key}", status=400)
    return NodeScope(
        project_id=project_id,
        year=effective_year,
        node_key=node_key,
        is_root_consol=is_root_consol_node(tree, node_key),
    )


async def resolve_report_node_scope(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    *,
    node_key: str | None,
) -> NodeScope:
    """普通合并报表端点的节点作用域解析（设计 §六.1，需求 4.1，ADR-CNSC-003）。

    与附注的 :func:`resolve_note_scope` 的关键差异：**省略 node_key 时选当前树的根合并节点**，
    以保持旧报表页面默认行为（而非像附注那样走 NULL legacy 作用域）。此默认根语义仅适用于报表
    endpoint，不改变附注旧调用的 NULL 语义。

    - 项目不是合并项目 / 没有有效审计年度 ⇒ ``NoteScopeError`` 404 / 400；
    - 空字符串或不在当前树的 node_key ⇒ 400（禁冒号前缀 / company_code / ``:consol`` 后缀兜底）；
    - 命中（含默认根）⇒ :class:`NodeScope`，``is_root_consol`` 经树判定。

    始终返回 :class:`NodeScope`（报表没有 legacy NULL 作用域）。
    """
    tree, effective_year = await _load_tree(db, project_id, year)

    if node_key == "":
        raise NoteScopeError("node_key 不能为空字符串（省略该参数才默认选根合并节点）", status=400)

    if node_key is None:
        # 省略 ⇒ 默认当前树的根合并节点（_load_tree 已保证 root.role == consol）。
        return NodeScope(
            project_id=project_id,
            year=effective_year,
            node_key=tree.node_key,
            is_root_consol=True,
        )

    node = find_node_by_key(tree, node_key)
    if node is None:
        raise NoteScopeError(f"企业树中没有节点 {node_key}", status=400)
    return NodeScope(
        project_id=project_id,
        year=effective_year,
        node_key=node_key,
        is_root_consol=is_root_consol_node(tree, node_key),
    )


async def _load_tree(db: AsyncSession, project_id: UUID, year: int | None) -> tuple[TreeNode, int]:
    """构建当前合并项目企业树并解析有效年度；非合并项目 / 无年度 ⇒ 404。"""
    from app.services.consol_group_tree import build_group_tree

    result = await build_group_tree(db, project_id)
    if result is None or result.root is None or result.root.role != ROLE_CONSOL:
        raise NoteScopeError(
            "只有合并报表项目有合并附注节点（项目不存在、不是合并项目）", status=404,
        )
    effective_year = year if year is not None else result.year
    if effective_year is None:
        raise NoteScopeError("项目没有有效审计年度，无法按节点读写附注", status=400)
    if result.year is not None and year is not None and year != result.year:
        # 显式年度与项目审计年度不一致：不跨年读写（§三.2）。
        raise NoteScopeError(
            f"请求年度 {year} 与项目审计年度 {result.year} 不一致", status=400,
        )
    return result.root, effective_year


@dataclass
class NoteRequestContext:
    """一次附注请求内共享的视图上下文（§四「一次请求尽量只装载一次上下文」）。

    把节点作用域解析、合并视图上下文（企业树 + 计算口径 + 报表配置）与 ``node_measures`` 都只做一次，
    供 ``/refresh``、``/audit``、``/audit-all``、``/apply-formulas``、``/aggregate``、差额穿透与
    ``fill-by-formula`` 复用，避免每个端点各自重建树 / 重解析 / 重取数（设计 §四，ADR-CNSC-003）。

    - ``scope``：经当前企业树校验的 :class:`NodeScope` / :class:`LegacyScope`。
    - ``view``：:class:`ViewContext`（``load_view_context`` 的产物），本请求只装载一次。
    - ``measures``：``node_measures(view.basis)`` 的缓存；首次 :meth:`node_measures` 调用才计算一次。
    """

    scope: Scope
    view: "ViewContext"
    _measures: dict[str, dict[str, dict[str, Decimal]]] | None = field(default=None, repr=False)

    @property
    def project_id(self) -> UUID:
        return self.scope.project_id

    @property
    def year(self) -> int:
        return self.view.year

    @property
    def node_key(self) -> str | None:
        return self.scope.node_key

    def node_measures(self) -> dict[str, dict[str, dict[str, Decimal]]]:
        """``node_measures(basis)`` 的请求级缓存：纯函数遍历整棵树，一次请求只算一遍。"""
        if self._measures is None:
            from app.services.consol_calc_basis import node_measures as _node_measures

            self._measures = _node_measures(self.view.basis)
        return self._measures

    def find_node(self, node_key: str | None = None) -> TreeNode:
        """在共享上下文的企业树里定位节点；缺省用本请求作用域的 node_key（根作用域 ⇒ 树根）。"""
        from app.services.consol_report_view_service import find_node

        return find_node(self.view.basis.tree, node_key if node_key is not None else self.scope.node_key)


async def load_note_request_context(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    *,
    node_key: str | None,
) -> NoteRequestContext:
    """附注公式类端点的统一入口：解析一次作用域 + 装载一次合并视图上下文（§四）。

    1. :func:`resolve_note_scope` 经当前企业树精确校验 node_key / 年度，产出 scope。
    2. ``consol_report_view_service.load_view_context`` 按同一有效年度装载合并计算口径与报表配置，仅一次。
    3. 返回的 :class:`NoteRequestContext` 内各端点复用 scope / view / node_measures，不再各自建树取数。

    非合并项目 / 无有效年度 / 非法 node_key 以 :class:`NoteScopeError` 抛出（路由转 400 / 404）。
    """
    from app.services.consol_report_view_service import load_view_context

    scope = await resolve_note_scope(db, project_id, year, node_key=node_key)
    # NodeScope 已带经树解析的有效年度；LegacyScope（旧调用）用请求显式年度，None 时由 load_view_context
    # 按项目审计年度解析（LegacyScope.year 的 0 占位只是兜底，不作为取数年度）。
    effective_year = scope.year if isinstance(scope, NodeScope) else year
    view = await load_view_context(db, project_id, effective_year)
    if view is None:
        raise NoteScopeError(
            "只有合并报表项目有合并附注节点（项目不存在、不是合并项目或没有审计年度）", status=404,
        )
    return NoteRequestContext(scope=scope, view=view)


async def load_scoped_record(db: AsyncSession, scope: Scope, section_id: str):
    """按作用域读取附注行（根合并节点允许回退 legacy；非根 / legacy 只认精确行）。

    委托 ``consol_note_formula_service._note_data_record``，但**根判定来自 scope（经树验证）**，
    不再由 loader 自己按字符串后缀兜底。
    """
    from app.services.consol_note_formula_service import _note_data_record

    return await _note_data_record(
        db, scope.project_id, scope.year, section_id,
        node_key=scope.node_key,
        allow_root_legacy_fallback=scope.allow_legacy_fallback,
    )


async def exact_scoped_record(db: AsyncSession, scope: Scope, section_id: str):
    """按作用域读取**写入目标行**：从不回退 legacy（写必须落专属行 / NULL 行本身）。"""
    from app.services.consol_note_formula_service import _note_data_record_exact

    return await _note_data_record_exact(
        db, scope.project_id, scope.year, section_id, node_key=scope.node_key,
    )


__all__ = [
    "LegacyScope",
    "NodeScope",
    "NoteRequestContext",
    "NoteScopeError",
    "Scope",
    "exact_scoped_record",
    "is_root_consol_node",
    "load_note_request_context",
    "load_scoped_record",
    "requested_node_key",
    "resolve_note_scope",
    "resolve_report_node_scope",
]
