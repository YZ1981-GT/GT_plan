"""合并范围成员 = 合并企业树里的子公司类企业（与合并计算同一棵树）。

consol-tree-three-code-autobuild 需求 11.3：成员取各项目三码 + 与上级关系推导出的合并企业树
（``consol_tree_service.build_tree``）里的子公司类企业，含经中间企业间接持有、按最终控制方挂靠的；
母公司本身与各级分公司不是成员（分公司并入所属企业汇总，不单独纳入合并范围）。非合并项目没有成员。

合并范围表（``consol_scope``）不再是成员来源（真库 0 行），只作同一企业代码的属性存放处（持股比例等）。
原先附注正文变量与程序表「确定合并范围」读那张表 ⇒ 子公司数恒 0、恒「待确定」
（spec consol-autotree-residual-closure R5.1）。逻辑原在 ``scope_diff_service._tree_members``。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ScopeMember:
    company_code: str
    company_name: str | None


async def tree_subsidiaries(db: AsyncSession, project_id: UUID) -> list[ScopeMember]:
    """本合并项目企业树中的子公司类企业，按树的展示顺序、同一企业只列一次；根项目不存在返回空。"""
    from app.services.consol_calc_basis import entity_kinds
    from app.services.consol_tree_service import build_tree, iter_nodes

    tree = await build_tree(db, project_id)
    if tree is None:
        return []
    kinds = entity_kinds(tree)
    seen: set[str] = set()
    members: list[ScopeMember] = []
    for node in iter_nodes(tree):
        code = (node.company_code or "").strip()
        if code and code not in seen and kinds.get(code) == "subsidiary":
            seen.add(code)
            members.append(ScopeMember(code, node.company_name))
    return members
