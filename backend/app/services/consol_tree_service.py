"""合并报表树形服务 — 三码体系构建企业树

build_tree: 以合并项目为根按三码推导企业树（委托 consol_group_tree；11 个 consol 服务依赖，签名不变）
build_tree_view: 合并页企业树接口载荷 {tree, mode, mode_label, diagnostics, year}
build_group_trees_from_projects / build_tree_by_codes: 集团架构森林（委托 group_forest，企业实体 + 可见性）
find_node: 按 company_code（首个节点）或 node_key 查找节点
find_node_by_key / iter_nodes: 按 node_key 查找 / 先序遍历
worksheet_key: 节点在差额表里的键（node_key，旧式节点退回企业代码）
get_descendants: 获取所有后代节点
to_dict: 树→JSON（保留旧字段，consol 服务依赖）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project


@dataclass
class TreeNode:
    """企业树节点

    基础字段（project_id..children）被现有 11 个 consol 服务依赖，顺序/语义不可变更。
    容错/展示标记字段（is_detached..report_scope）为 group-tree-architecture 新增，
    均带默认值，不影响现有以关键字构造 TreeNode 的代码。

    consol-tree-three-code-autobuild（ADR-CTREE-002）追加 ``node_key..diagnostics``：
    合并树按三码推导，同一企业可以不同角色出现（合并户 / 母公司户 / 本部），
    ``node_key = {企业代码}:{角色}`` 才是树内唯一键；差额节点与有分公司的汇总节点没有
    自己的项目，``project_id`` 为 None（差额节点的分录承载项目见 ``host_project_id``）。
    """
    project_id: UUID | None
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
    # 森林改为 group_forest 直接产出字典后，合并树不再填这两个字段（保留以兼容旧构造方）
    shareholding: float | None = None    # 持股比例（如 100.00）
    consol_method: str | None = None     # 合并方式（ConsolMethod 枚举值：full/equity/proportional）
    # --- 三码推导合并树（consol-tree-three-code-autobuild，均带默认值）---
    node_key: str = ""                   # {企业代码}:{角色}，树内唯一
    role: str = ""                       # consol/consol_elim/parent/hq/branch_elim/subsidiary/branch
    kind: str = "data"                   # aggregate（Σ子节点）/ elim（归属分录）/ data（单体审定数）
    display_name: str = ""               # 带角色后缀的展示名，如「某集团（合并差额）」
    relation: str | None = None          # 与上级关系 subsidiary/branch（信息展示，不决定金额）
    host_project_id: UUID | None = None  # 差额节点：承载其分录的合并项目
    flags: list[str] = field(default_factory=list)  # detached/cycle_break/relation_defaulted/...
    via: list[str] = field(default_factory=list)    # 经中间企业间接持有（企业代码，外层在前）
    mode: str | None = None              # 合并节点：subsidiary/branch/mixed/none
    diagnostics: list[dict] = field(default_factory=list)  # 仅根节点：整棵树的诊断


async def build_tree(db: AsyncSession, root_project_id: UUID) -> TreeNode | None:
    """以合并项目为根构建企业树（签名不变，11 个 consol 服务依赖）。

    consol-tree-three-code-autobuild（ADR-CTREE-001）起按同年度项目的三码 + 与上级关系
    实时推导（``consol_group_tree.derive_group_tree``），**不再读 parent_project_id**：
    合并户一次生成「合并 / 合并差额 / 母公司」三个节点，母公司有分公司时再展开
    「本部 / 母分差额 / 各分公司」。整棵树的合并方式记在根节点 ``mode``，诊断记在
    根节点 ``diagnostics``（dict 列表）。根项目不存在返回 None。
    """
    from app.services.consol_group_tree import build_group_tree

    result = await build_group_tree(db, root_project_id)
    if result is None or result.root is None:
        return None
    root = result.root
    root.diagnostics = [d.to_dict() for d in result.diagnostics]
    return root


def iter_nodes(root: TreeNode):
    """先序遍历（含根）。子节点顺序即展示顺序，结果确定。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def find_node_by_key(root: TreeNode, node_key: str) -> TreeNode | None:
    """按 node_key（``{企业代码}:{角色}``）查找节点。"""
    for node in iter_nodes(root):
        if node.node_key == node_key:
            return node
    return None


def find_node(root: TreeNode, company_code: str) -> TreeNode | None:
    """在树中按 company_code 查找节点（DFS 先序）。

    兼容两种入参（consol-tree-three-code-autobuild）：
    - ``node_key``（含冒号）⇒ 精确匹配该节点；
    - 纯企业代码 ⇒ 该代码的**首个**节点。三码树里同一企业可有多个角色，先序下首个即
      「合并」节点（有合并项目时）或其数据节点 —— 与旧调用方「按代码取该企业」的语义一致。
    """
    if ":" in company_code:
        return find_node_by_key(root, company_code)
    for node in iter_nodes(root):
        if node.company_code == company_code:
            return node
    return None


def worksheet_key(node: TreeNode) -> str:
    """节点在差额表 ``node_company_code`` 列里的键：``node_key``（ADR-CTREE-002）。

    旧式手工构造的节点（没有 node_key）退回企业代码，兼容旧调用方与旧测试。
    """
    return node.node_key or node.company_code


def get_descendants(node: TreeNode) -> list[TreeNode]:
    """获取节点的所有后代（不含自身）"""
    result: list[TreeNode] = []
    for child in node.children:
        result.append(child)
        result.extend(get_descendants(child))
    return result


def to_dict(node: TreeNode) -> dict:
    """树节点→JSON 字典。

    旧字段（project_id..children）键名与语义不动（11 个 consol 服务依赖）；
    三码合并树追加 node_key/role/kind/display_name/relation/host_project_id/flags/via/mode。
    没有项目的节点（差额、有分公司的汇总）``project_id`` 为 None（旧实现恒有项目）。
    """
    return {
        "project_id": str(node.project_id) if node.project_id else None,
        "company_code": node.company_code,
        "company_name": node.company_name,
        "parent_company_code": node.parent_company_code,
        "ultimate_company_code": node.ultimate_company_code,
        "consol_level": node.consol_level,
        "children": [to_dict(c) for c in node.children],
        "node_key": node.node_key,
        "role": node.role,
        "kind": node.kind,
        "display_name": node.display_name or node.company_name,
        "relation": node.relation,
        "host_project_id": str(node.host_project_id) if node.host_project_id else None,
        "flags": list(node.flags),
        "via": list(node.via),
        "mode": node.mode,
    }


async def build_tree_view(db: AsyncSession, root_project_id: UUID) -> dict | None:
    """合并页企业树接口载荷（``GET /api/consolidation/worksheet/tree``，需求 3 / 4.4 / 9.4）。

    ``{tree, mode, mode_label, diagnostics, year}``：树与合并方式识别来自三码推导；诊断 = 企业树推导诊断
    + 本树分录中找不到归属节点的分录（与重算同一归属函数，需求 6.4）。根项目不存在返回 None。
    """
    from app.services.consol_calc_basis import load_orphan_diagnostics
    from app.services.consol_group_tree import (
        MODE_LABELS,
        MODE_NONE,
        ROLE_CONSOL,
        build_group_tree,
        sort_diagnostics,
    )

    result = await build_group_tree(db, root_project_id)
    if result is None or result.root is None:
        return None
    diagnostics = list(result.diagnostics)
    if result.year is not None and result.root.role == ROLE_CONSOL:
        diagnostics.extend(await load_orphan_diagnostics(db, result.root, result.year))
    mode = result.mode or MODE_NONE
    return {
        "tree": to_dict(result.root),
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, MODE_LABELS[MODE_NONE]),
        "diagnostics": [d.to_dict() for d in sort_diagnostics(diagnostics)],
        "year": result.year,
    }


def build_group_trees_from_projects(
    projects: list[Project],
    year: int | None = None,
    *,
    scope: str | None = None,
) -> dict:
    """扁平项目 → 集团架构森林（纯函数；``GET /api/projects/tree`` 与批量导入预览共用，需求 8.6）。

    consol-tree-three-code-autobuild 任务 9.2 起委托 ``group_forest.build_forest``：以企业为节点
    （同代码同年度的合并与单户项目合为一个节点）、年度按平台统一解析、未传年度时按（控制方, 年度）分树，
    上级边与合并企业树同源。返回 ``{"trees": [...], "independents": [...]}``。
    """
    from app.services.group_forest import build_forest

    return build_forest(projects, year=year, scope=scope)


async def build_tree_by_codes(
    db: AsyncSession,
    year: int | None = None,
    scope: str | None = None,
    *,
    user: object | None = None,
) -> dict:
    """从 projects 表构建集团架构森林（``GET /api/projects/tree``）。

    ``user`` 非空 ⇒ 只含该用户可见的项目（admin/partner 全部，其余角色仅参与的项目，需求 8.3）；
    ``scope`` 为报表类型筛选；节点从 companies 表富集持股比例 / 合并方式（查询失败降级为空）。
    """
    from app.services.group_forest import load_forest

    return await load_forest(db, year=year, scope=scope, user=user)
