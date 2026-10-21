"""需求 2.5 的角色映射期望表（partner-manager-edit-permission）：委派角色 →（项目角色，项目级别）。

按需求 2.1、2.2 原文逐键写死，不从生产代码推导：这份表用来钉住 ``assignment_service.ROLE_MAP``，
从 ``ROLE_MAP`` 推出来就成了拿它自己比自己。取值写枚举的字符串值（与 ``project_users`` 的存储口径相同）。

使用方：``test_phase8_endpoint_role_levels.py`` 与 ``test_deliverable_generation_membership_auth.py`` 的前提测试
共用这一份，两处的期望表因此必然一致。文件名不以 ``test_`` 开头，pytest 不收集；导入写
``from tests.role_map_expected import ...``。
"""
from __future__ import annotations

# 四个别名集合（需求术语表）的全部键及取值。需求 2.5 另要求列入「ROLE_MAP 中现有、取值为 (readonly, readonly)
# 的键」：任务 2.1 现算为 0 个，所以这里没有。未登记的委派角色由 UNMAPPED_ROLE 兜底，不是 ROLE_MAP 的键。
EXPECTED_ROLE_MAP: dict[str, tuple[str, str]] = {
    # 合伙人 / 经理别名集合 → edit 级（需求 2.1）
    "signing_partner": ("partner", "edit"),
    "partner": ("partner", "edit"),
    "合伙人": ("partner", "edit"),
    "manager": ("manager", "edit"),
    "项目经理": ("manager", "edit"),
    # 质控别名集合 → review 级（需求 2.2）
    "qc": ("qc", "review"),
    "质控": ("qc", "review"),
    # EQCR 别名集合 → (partner, review)（需求 2.2）
    "eqcr": ("partner", "review"),
    "独立复核合伙人": ("partner", "review"),
    # 审计员别名集合 → edit 级（需求 2.2）
    "auditor": ("auditor", "edit"),
    "审计员": ("auditor", "edit"),
    "assistant": ("auditor", "edit"),
    "助理": ("auditor", "edit"),
}

# EQCR 别名集合（需求术语表）。取值为 (partner, review) 的键必须恰是这两个：生产代码的
# EQCR_ROLE_ALIASES 按这个取值从 ROLE_MAP 推导（需求 2.5、7.2）。
EXPECTED_EQCR_ALIASES: frozenset[str] = frozenset({"eqcr", "独立复核合伙人"})
