"""服务层公共工具"""

from app.models.consolidation_models import Company
from app.models.consolidation_schemas import CompanyTreeNode


def build_company_tree(companies: list[Company]) -> list[CompanyTreeNode]:
    """从公司列表构建树形结构"""
    if not companies:
        return []

    # 构建节点映射
    node_map: dict[str, CompanyTreeNode] = {}
    for c in companies:
        node = CompanyTreeNode(
            id=str(c.id),
            company_code=c.company_code,
            company_name=c.company_name,
            parent_code=c.parent_code,
            ultimate_code=c.ultimate_code,
            consol_level=c.consol_level,
            shareholding=c.shareholding,
            consol_method=c.consol_method,
            functional_currency=c.functional_currency,
            is_active=c.is_active,
            children=[],
        )
        node_map[c.company_code] = node

    # 构建父子关系
    roots: list[CompanyTreeNode] = []
    for code, node in node_map.items():
        if node.parent_code and node.parent_code in node_map:
            node_map[node.parent_code].children.append(node)
        else:
            roots.append(node)

    # 按层级排序
    def sort_key(n: CompanyTreeNode) -> tuple[int, str]:
        return (n.consol_level or 0, n.company_code)

    def recursive_sort(nodes: list[CompanyTreeNode]) -> None:
        nodes.sort(key=sort_key)
        for n in nodes:
            if n.children:
                recursive_sort(n.children)

    recursive_sort(roots)
    return roots
