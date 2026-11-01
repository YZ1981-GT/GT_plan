"""合并范围成员 = 合并企业树里的子公司类企业 + 各级分公司（与合并计算同一棵树）。

consol-tree-three-code-autobuild 需求 11.3：成员取各项目三码 + 与上级关系推导出的合并企业树
（``consol_tree_service.build_tree``）里的下级企业，含经中间企业间接持有、按最终控制方挂靠的；
母公司（根企业）本身不是成员。非合并项目没有成员。

🔴 2026-10-31 用户拍板：**分公司要作为独立成员出现在合并范围和附注的子企业清单里**。
此前分公司被排除（「分公司并入所属企业汇总，不单独纳入合并范围」）⇒ 合并范围清单与附注
子企业清单里看不到分公司。改动只影响「清单/成员」口径，**不影响任何金额计算**：分公司的
金额仍然并入所属企业的汇总节点（``consol_calc_basis`` 的 aggregate 口径未动）。

会计口径不能混：分公司不是子公司。因此成员带 ``kind``（``subsidiary`` / ``branch``），
``tree_members`` 给全部成员，``tree_subsidiaries`` 仍只给子公司（文案要说「N 家子公司」的
地方继续用它），计数文案由调用方按两者分别呈现。

合并范围表（``consol_scope``）不再是成员来源（真库 0 行），只作同一企业代码的属性存放处（持股比例等）。
原先附注正文变量与程序表「确定合并范围」读那张表 ⇒ 子公司数恒 0、恒「待确定」
（spec consol-autotree-residual-closure R5.1）。逻辑原在 ``scope_diff_service._tree_members``。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

KIND_SUBSIDIARY = "subsidiary"
KIND_BRANCH = "branch"
# 成员口径：根企业（parent）不是成员，其余下级企业都是
MEMBER_KINDS = (KIND_SUBSIDIARY, KIND_BRANCH)


@dataclass(frozen=True)
class ScopeMember:
    company_code: str
    company_name: str | None
    # 带默认值：旧调用方/旧测试的两参构造 ScopeMember(code, name) 仍然成立
    kind: str = KIND_SUBSIDIARY

    @property
    def is_branch(self) -> bool:
        return self.kind == KIND_BRANCH


async def tree_members(db: AsyncSession, project_id: UUID) -> list[ScopeMember]:
    """本合并项目企业树中的全部下级企业（子公司 + 分公司），按树的展示顺序、同一企业只列一次。

    根企业（母公司本身）不是成员；根项目不存在返回空。
    """
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
        if not code or code in seen:
            continue
        kind = kinds.get(code)
        if kind in MEMBER_KINDS:
            seen.add(code)
            members.append(ScopeMember(code, node.company_name, kind))
    return members


async def tree_subsidiaries(db: AsyncSession, project_id: UUID) -> list[ScopeMember]:
    """只取子公司类企业（会计口径「子公司」，不含分公司）。

    需要「N 家子公司」这种明确会计表述的地方用这个；要完整成员清单（含分公司）用
    :func:`tree_members`。
    """
    return [m for m in await tree_members(db, project_id) if m.kind == KIND_SUBSIDIARY]


async def tree_branches(db: AsyncSession, project_id: UUID) -> list[ScopeMember]:
    """只取分公司。"""
    return [m for m in await tree_members(db, project_id) if m.kind == KIND_BRANCH]
