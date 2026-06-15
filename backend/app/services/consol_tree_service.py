"""合并报表树形服务 — 三码体系构建企业树

build_tree: 从 projects 表构建树（parent_project_id 关系，11 个 consol 服务依赖，签名不变）
build_tree_by_codes: 按三代码（company_code/parent_company_code/ultimate_company_code）构建森林
find_node: 按 company_code 查找节点
get_descendants: 获取所有后代节点
to_dict: 树→JSON（保留旧字段，consol 服务依赖）
to_dict_v2: 树→JSON（含容错/展示标记字段，group-tree-architecture 前端用）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project


@dataclass
class TreeNode:
    """企业树节点

    基础字段（project_id..children）被现有 11 个 consol 服务依赖，顺序/语义不可变更。
    容错/展示标记字段（is_detached..report_scope）为 group-tree-architecture 新增，
    均带默认值，不影响现有以关键字构造 TreeNode 的代码。
    """
    project_id: UUID
    company_code: str
    company_name: str
    parent_company_code: str | None
    ultimate_company_code: str | None
    consol_level: int
    children: list[TreeNode] = field(default_factory=list)
    # --- 容错/展示标记字段（group-tree-architecture 新增）---
    is_detached: bool = False       # parent_company_code 指向不存在的企业
    is_independent: bool = False    # ultimate_company_code 为空
    is_cycle_break: bool = False    # 循环引用被打断
    has_no_company_code: bool = False  # company_code 为空
    status: str | None = None       # 项目状态
    report_scope: str | None = None  # 报表范围（consolidated 等）
    # --- Phase 2 持股/合并方式可视化（group-tree-architecture Task 14.1）---
    # 由 build_tree_by_codes 从 companies 表富集；无数据时保持 None（优雅降级）
    shareholding: float | None = None    # 持股比例（如 100.00）
    consol_method: str | None = None     # 合并方式（ConsolMethod 枚举值：full/equity/proportional）


async def build_tree(db: AsyncSession, root_project_id: UUID) -> TreeNode | None:
    """从 projects 表构建企业树。

    root_project_id 是合并项目（最顶层），其子项目通过 parent_project_id 关联。
    """
    # 加载根项目
    result = await db.execute(
        sa.select(Project).where(
            Project.id == root_project_id,
            Project.is_deleted == sa.false(),
        )
    )
    root = result.scalar_one_or_none()
    if not root:
        return None

    # 加载所有子项目（递归查找所有 parent_project_id 链）
    all_projects = await _load_all_descendants(db, root_project_id)
    all_projects.insert(0, root)

    # 构建节点映射
    node_map: dict[UUID, TreeNode] = {}
    for p in all_projects:
        node_map[p.id] = TreeNode(
            project_id=p.id,
            company_code=p.company_code or str(p.id)[:8],
            company_name=p.client_name,
            parent_company_code=p.parent_company_code,
            ultimate_company_code=p.ultimate_company_code,
            consol_level=p.consol_level or 1,
        )

    # 建立父子关系
    for p in all_projects:
        if p.parent_project_id and p.parent_project_id in node_map:
            parent_node = node_map[p.parent_project_id]
            parent_node.children.append(node_map[p.id])

    return node_map.get(root_project_id)


async def _load_all_descendants(db: AsyncSession, root_id: UUID) -> list[Project]:
    """BFS 加载所有后代项目"""
    descendants: list[Project] = []
    queue = [root_id]
    visited: set[UUID] = {root_id}

    while queue:
        parent_ids = queue[:]
        queue.clear()
        result = await db.execute(
            sa.select(Project).where(
                Project.parent_project_id.in_(parent_ids),
                Project.is_deleted == sa.false(),
            )
        )
        children = result.scalars().all()
        for child in children:
            if child.id not in visited:
                visited.add(child.id)
                descendants.append(child)
                queue.append(child.id)

    return descendants


def find_node(root: TreeNode, company_code: str) -> TreeNode | None:
    """在树中按 company_code 查找节点（DFS）"""
    if root.company_code == company_code:
        return root
    for child in root.children:
        found = find_node(child, company_code)
        if found:
            return found
    return None


def get_descendants(node: TreeNode) -> list[TreeNode]:
    """获取节点的所有后代（不含自身）"""
    result: list[TreeNode] = []
    for child in node.children:
        result.append(child)
        result.extend(get_descendants(child))
    return result


def to_dict(node: TreeNode) -> dict:
    """树节点→JSON 字典（保留旧字段，11 个 consol 服务依赖，不动）"""
    return {
        "project_id": str(node.project_id),
        "company_code": node.company_code,
        "company_name": node.company_name,
        "parent_company_code": node.parent_company_code,
        "ultimate_company_code": node.ultimate_company_code,
        "consol_level": node.consol_level,
        "children": [to_dict(c) for c in node.children],
    }


def to_dict_v2(node: TreeNode) -> dict:
    """树节点→JSON 字典（含容错/展示标记字段，group-tree-architecture 前端用）

    字段名与前端 useGroupTree 的 TreeNode 接口对齐（camelCase）。
    """
    return {
        "id": str(node.project_id),
        "label": node.company_name,
        "companyCode": node.company_code,
        "companyName": node.company_name,
        "parentCompanyCode": node.parent_company_code,
        "ultimateCompanyCode": node.ultimate_company_code,
        "consolLevel": node.consol_level,
        "status": node.status,
        "reportScope": node.report_scope,
        "isDetached": node.is_detached,
        "isIndependent": node.is_independent,
        "isCycleBreak": node.is_cycle_break,
        "hasNoCompanyCode": node.has_no_company_code,
        "shareholding": node.shareholding,
        "consolMethod": node.consol_method,
        "children": [to_dict_v2(c) for c in node.children],
    }


def _make_node(p: Project) -> TreeNode:
    """Project → TreeNode（携带容错/展示标记字段，由调用方设置具体标记）"""
    status_val = None
    raw_status = getattr(p, "status", None)
    if raw_status is not None:
        # status 可能是枚举，取其 value
        status_val = getattr(raw_status, "value", raw_status)
    return TreeNode(
        project_id=p.id,
        company_code=p.company_code or "",
        company_name=p.client_name,
        parent_company_code=p.parent_company_code,
        ultimate_company_code=p.ultimate_company_code,
        consol_level=p.consol_level or 1,
        status=str(status_val) if status_val is not None else None,
        report_scope=p.report_scope,
    )


def build_group_trees_from_projects(
    projects: list[Project],
    year: int | None = None,
) -> dict:
    """纯函数：扁平项目列表 → 分组树形森林（按三代码构建）。

    区别于 build_tree（parent_project_id 模式），本函数按三代码字段构建：
    company_code / parent_company_code / ultimate_company_code。

    步骤：
    1. 按年度过滤（audit_period_end 提取年份）
    2. 排除 company_code 为空的项目 → independent 分组（has_no_company_code=True）
    3. ultimate_company_code 为空 → independent 分组（is_independent=True）
    4. 按 ultimate_company_code 分组（森林，多棵树）
    5. 组内按 parent_company_code → company_code 匹配建立父子关系
    6. parent 指向组内不存在的企业 → is_detached，挂 ultimate 根（虚拟根）直接子节点
    7. 循环引用检测（visited set 遍历）→ 打断 + is_cycle_break 标记

    返回:
        {
            "trees": [ { "ultimateCode", "ultimateName", "rootProjectId", "children": [...] }, ... ],
            "independents": [ <node dict>, ... ],
        }
    其中 children / independents 中的节点均为 to_dict_v2 输出格式。
    """
    # 1. 年度过滤
    if year is not None:
        filtered: list[Project] = []
        for p in projects:
            ape = getattr(p, "audit_period_end", None)
            if ape is not None and ape.year == year:
                filtered.append(p)
        projects = filtered

    independents: list[TreeNode] = []
    # 按 ultimate 分组的有效项目
    grouped: dict[str, list[Project]] = {}

    for p in projects:
        code = (p.company_code or "").strip()
        ultimate = (p.ultimate_company_code or "").strip()
        if not code:
            # 2. company_code 为空 → 独立分组（扁平展示）
            node = _make_node(p)
            node.has_no_company_code = True
            node.is_independent = True
            independents.append(node)
            continue
        if not ultimate:
            # 3. ultimate 为空 → 独立分组
            node = _make_node(p)
            node.is_independent = True
            independents.append(node)
            continue
        grouped.setdefault(ultimate, []).append(p)

    trees: list[dict] = []
    for ultimate_code, members in grouped.items():
        tree = _build_single_group(ultimate_code, members)
        trees.append(tree)

    return {
        "trees": trees,
        "independents": [to_dict_v2(n) for n in independents],
    }


def _build_single_group(ultimate_code: str, members: list[Project]) -> dict:
    """构建单棵集团树（同一 ultimate_company_code 分组）。

    返回 GroupTree 字典：{ultimateCode, ultimateName, rootProjectId, children}
    """
    # 建立 company_code → node 映射（同组内 company_code 应唯一；重复时后者覆盖）
    node_map: dict[str, TreeNode] = {}
    for p in members:
        node = _make_node(p)
        node_map[node.company_code] = node

    # 找出 ultimate 对应的根项目（company_code == ultimate_code）
    root_node = node_map.get(ultimate_code)
    root_project_id = str(root_node.project_id) if root_node else None
    ultimate_name = root_node.company_name if root_node else ultimate_code

    # 5/6. 建立父子关系
    # 顶层节点（挂在 ultimate 根下）：parent 为空、parent == ultimate（指向根本身）、
    # parent 指向组内不存在的企业（detached）、或参与循环引用（cycle break）。
    # 用 company_code 集合跟踪顶层成员（TreeNode 是 unhashable dataclass，且 == 为值比较，
    # 不能用 set/in 直接判等）。
    top_level_codes: list[str] = []
    top_level_set: set[str] = set()

    def _add_top(n: TreeNode) -> None:
        if n.company_code not in top_level_set:
            top_level_set.add(n.company_code)
            top_level_codes.append(n.company_code)

    for code, node in node_map.items():
        if code == ultimate_code:
            # 根节点本身，作为顶层（其子节点挂它下面）
            continue
        parent_code = (node.parent_company_code or "").strip()
        if not parent_code:
            # 无 parent → 直接挂在 ultimate 根下
            _add_top(node)
        elif parent_code == ultimate_code:
            # parent 指向 ultimate 根 → 挂根下（若根节点存在则挂根，否则顶层）
            _add_top(node)
        elif parent_code in node_map:
            # parent 存在于组内 → 由下面的循环检测后挂载
            pass
        else:
            # 6. parent 指向组内不存在的企业 → detached，挂 ultimate 根下
            node.is_detached = True
            _add_top(node)

    # 7. 循环检测 + 建立真实父子链
    # 对每个有有效组内 parent 的节点，沿 parent 链向上走，检测环
    for code, node in node_map.items():
        if code == ultimate_code:
            continue
        if code in top_level_set:
            continue
        parent_code = (node.parent_company_code or "").strip()
        if parent_code not in node_map:
            continue  # 已作为 detached/top 处理
        # 检测从 node 沿 parent 链是否成环
        if _has_cycle(node, node_map, ultimate_code):
            # 环 → 打断，标记并作为顶层挂根下
            node.is_cycle_break = True
            _add_top(node)
        else:
            parent_node = node_map[parent_code]
            parent_node.children.append(node)

    # 将顶层节点挂到根节点下（若根存在），否则顶层节点即树的 children
    top_level_nodes = [node_map[c] for c in top_level_codes]
    if root_node is not None:
        for n in top_level_nodes:
            root_node.children.append(n)
        children = [to_dict_v2(root_node)]
    else:
        children = [to_dict_v2(n) for n in top_level_nodes]

    return {
        "ultimateCode": ultimate_code,
        "ultimateName": ultimate_name,
        "rootProjectId": root_project_id,
        "children": children,
    }


def _has_cycle(
    start: TreeNode,
    node_map: dict[str, TreeNode],
    ultimate_code: str,
) -> bool:
    """从 start 沿 parent_company_code 链向上遍历，检测是否成环。

    走到 ultimate_code、空 parent、或组外 parent 即安全终止（无环）。
    """
    visited: set[str] = {start.company_code}
    current = start
    while True:
        parent_code = (current.parent_company_code or "").strip()
        if not parent_code or parent_code == ultimate_code:
            return False
        if parent_code not in node_map:
            return False
        if parent_code in visited:
            return True  # 成环
        visited.add(parent_code)
        current = node_map[parent_code]


async def build_tree_by_codes(
    db: AsyncSession,
    year: int | None = None,
    scope: str | None = None,
) -> dict:
    """从 projects 表按三代码构建集团架构森林。

    区别于 build_tree（parent_project_id 模式），本方法是全局森林：
    所有项目按 ultimate_company_code 分组成多棵树，无单一 root project_id。

    Args:
        db: 数据库会话
        year: 年度过滤（按 audit_period_end 年份），None 表示不过滤
        scope: report_scope 过滤（如 'consolidated'），None 表示全部

    Returns:
        {"trees": [...], "independents": [...]}（见 build_group_trees_from_projects）
    """
    stmt = sa.select(Project).where(Project.is_deleted == sa.false())
    if scope:
        stmt = stmt.where(Project.report_scope == scope)
    result = await db.execute(stmt)
    projects = list(result.scalars().all())
    forest = build_group_trees_from_projects(projects, year=year)
    # Phase 2（Task 14.1）：从 companies 表富集 shareholding / consol_method。
    # 优雅降级——查询失败或无匹配则节点保持 null，不影响树形结构。
    await _enrich_with_company_info(db, forest)
    return forest


async def _enrich_with_company_info(db: AsyncSession, forest: dict) -> None:
    """从 companies 表按 company_code 富集 shareholding / consol_method（就地修改节点字典）。

    一次查询取出全部活跃公司信息建映射，遍历树形节点字典写入 shareholding / consolMethod。
    Graceful degradation：companies 表查询失败（如 SQLite 无该表种子）或无匹配 →
    节点保持 None，不抛异常、不影响树形。
    """
    # 收集树形+独立节点中出现的所有 company_code
    codes: set[str] = set()

    def _collect(nodes: list[dict]) -> None:
        for n in nodes:
            code = n.get("companyCode")
            if code:
                codes.add(code)
            _collect(n.get("children") or [])

    for tree in forest.get("trees", []):
        _collect(tree.get("children") or [])
    _collect(forest.get("independents") or [])

    if not codes:
        return

    # 延迟导入避免循环依赖
    from app.models.consolidation_models import Company

    info_map: dict[str, dict] = {}
    try:
        stmt = sa.select(
            Company.company_code,
            Company.shareholding,
            Company.consol_method,
        ).where(
            Company.company_code.in_(codes),
            Company.is_active == sa.true(),
            Company.is_deleted == sa.false(),
        )
        rows = (await db.execute(stmt)).all()
        for company_code, shareholding, consol_method in rows:
            if not company_code or company_code in info_map:
                continue
            method_val = getattr(consol_method, "value", consol_method)
            info_map[company_code] = {
                "shareholding": float(shareholding) if shareholding is not None else None,
                "consolMethod": str(method_val) if method_val is not None else None,
            }
    except Exception:
        # 优雅降级：companies 表不可用 → 不富集
        return

    if not info_map:
        return

    def _apply(nodes: list[dict]) -> None:
        for n in nodes:
            info = info_map.get(n.get("companyCode") or "")
            if info:
                n["shareholding"] = info["shareholding"]
                n["consolMethod"] = info["consolMethod"]
            _apply(n.get("children") or [])

    for tree in forest.get("trees", []):
        _apply(tree.get("children") or [])
    _apply(forest.get("independents") or [])
