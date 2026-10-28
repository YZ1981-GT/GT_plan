"""合并企业树的节点角色、类型、合并方式与展示名（spec consol-autotree-linkage-closure R2）。

从 ``consol_group_tree`` 拆出（该模块再导出全部名字，旧调用方不变）。

展示名规则（用户 2026-10-26 拍板）：
- 合并项目一次生成三个节点：``X（合并户）`` / ``X（差额户）`` / ``X（单体母公司户）``；
- 母公司有分公司时：``X（母公司户）``，下挂 ``X（母分差额户）`` / ``X（本部单体户）`` / 各分公司；
- 子公司、分公司自己有分公司（且不单列合并项目）时，其汇总节点为 ``X（汇总户）``；
- 其余数据节点（子公司、分公司）用企业原名。

节点键 ``{企业代码}:{角色}`` 与展示名无关，改名不迁移任何数据。
"""

from __future__ import annotations

ROLE_CONSOL = "consol"
ROLE_CONSOL_ELIM = "consol_elim"
ROLE_PARENT = "parent"
ROLE_HQ = "hq"
ROLE_BRANCH_ELIM = "branch_elim"
ROLE_SUBSIDIARY = "subsidiary"
ROLE_BRANCH = "branch"
ELIM_ROLES = frozenset({ROLE_CONSOL_ELIM, ROLE_BRANCH_ELIM})
# 代表「一个企业在树里的位置」的角色（统计合并方式、判断企业是否在树中用）
ENTITY_ROLES = frozenset({ROLE_CONSOL, ROLE_PARENT, ROLE_SUBSIDIARY, ROLE_BRANCH})

KIND_AGGREGATE = "aggregate"  # Σ 直接子节点
KIND_ELIM = "elim"            # 归属本节点的已审批分录
KIND_DATA = "data"            # 单体项目审定数

MODE_SUBSIDIARY = "subsidiary"
MODE_BRANCH = "branch"
MODE_MIXED = "mixed"
MODE_NONE = "none"
MODE_LABELS: dict[str, str] = {
    MODE_SUBSIDIARY: "母子合并",
    MODE_BRANCH: "总分汇总",
    MODE_MIXED: "母子合并＋总分汇总",
    MODE_NONE: "未识别到下级",
}

# 与 kind 无关的固定后缀；母公司按 kind 区分（单体母公司户 / 母公司户），汇总户见 display_name
_ROLE_SUFFIX: dict[str, str] = {
    ROLE_CONSOL: "（合并户）",
    ROLE_CONSOL_ELIM: "（差额户）",
    ROLE_HQ: "（本部单体户）",
    ROLE_BRANCH_ELIM: "（母分差额户）",
}
SUFFIX_PARENT_DATA = "（单体母公司户）"
SUFFIX_PARENT_AGGREGATE = "（母公司户）"
SUFFIX_AGGREGATE = "（汇总户）"


def node_key(company_code: str, role: str) -> str:
    return f"{company_code}:{role}"


def display_name(name: str, role: str, kind: str) -> str:
    """带角色后缀的展示名（design §3.2）。"""
    if role == ROLE_PARENT:
        return f"{name}{SUFFIX_PARENT_AGGREGATE if kind == KIND_AGGREGATE else SUFFIX_PARENT_DATA}"
    if role in _ROLE_SUFFIX:
        return f"{name}{_ROLE_SUFFIX[role]}"
    return f"{name}{SUFFIX_AGGREGATE}" if kind == KIND_AGGREGATE else name


def consol_label(name: str) -> str:
    """合并户的展示名（诊断文案引用「X（合并户）」时与节点展示名同一来源）。"""
    return display_name(name, ROLE_CONSOL, KIND_AGGREGATE)


__all__ = [
    "ELIM_ROLES",
    "ENTITY_ROLES",
    "KIND_AGGREGATE",
    "KIND_DATA",
    "KIND_ELIM",
    "MODE_BRANCH",
    "MODE_LABELS",
    "MODE_MIXED",
    "MODE_NONE",
    "MODE_SUBSIDIARY",
    "ROLE_BRANCH",
    "ROLE_BRANCH_ELIM",
    "ROLE_CONSOL",
    "ROLE_CONSOL_ELIM",
    "ROLE_HQ",
    "ROLE_PARENT",
    "ROLE_SUBSIDIARY",
    "SUFFIX_AGGREGATE",
    "SUFFIX_PARENT_AGGREGATE",
    "SUFFIX_PARENT_DATA",
    "consol_label",
    "display_name",
    "node_key",
]
