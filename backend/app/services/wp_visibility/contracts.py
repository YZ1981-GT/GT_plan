"""可见性隔离核心契约 · 角色分类结果（Task 3 / 组件 C3）

Feature: procedure-delegation-visibility-isolation
Requirements: 1.1–1.11（唯一角色分类与 Non_Admin scope 上界）
Design: "Role Classification" + Property 1 / Property 5

本模块只承载 **角色分类** 契约：``VisibilityRole`` 与 ``VisibilityContext``。
ResourceRef / WpBoundRequest / AccessGrant / WpAccessContext 等门与查询契约由后续任务
（C2/C5/C8）在同 package 扩展，避免与本任务冲突。
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


class VisibilityRole(str, enum.Enum):
    """唯一用户分类（每个服务端入口输出且仅输出其一，Req 1.1）。

    - ``admin``：system ``admin``，唯一忽略 ``scope_cycles`` 上界（Req 1.2/1.8）。
    - ``supervisor``：Non_Admin 且同时满足唯一 active StaffMember + 唯一 active
      ProjectAssignment（角色权威）+ 唯一 active ProjectUser（scope 权威）（Req 1.3）。
    - ``restricted``：其余全部 Non_Admin，含 fail-closed 兜底（Req 1.4/1.5）。
    """

    admin = "admin"
    supervisor = "supervisor"
    restricted = "restricted"


@dataclass(frozen=True)
class VisibilityContext:
    """角色分类的不可变结果。

    - ``role``：``VisibilityRole`` 之一且唯一。
    - ``is_admin``：等价于 ``role is VisibilityRole.admin``；显式冗余供 gate 快速判定。
    - ``scope_cycles``：Non_Admin 的底稿可见性粗粒度上界（frozenset）。仅对 Non_Admin
      有意义；Admin 忽略 scope，恒为空 frozenset（Req 1.8）。缺失/查询失败一律空集（Req 1.9/1.10）。
    """

    user_id: UUID
    project_id: UUID
    role: VisibilityRole
    is_admin: bool
    scope_cycles: frozenset[str]

    def __post_init__(self) -> None:  # noqa: D401 — 契约一致性守卫
        # is_admin 必须与 role 一致，避免下游误判。
        if self.is_admin != (self.role is VisibilityRole.admin):
            raise ValueError("VisibilityContext.is_admin 与 role 不一致")
        # Admin 忽略 scope：恒为空集（Req 1.8）。
        if self.is_admin and self.scope_cycles:
            raise ValueError("Admin_User 不得携带 scope_cycles（忽略 scope 上界）")


# ---------------------------------------------------------------------------
# AccessGrant 契约（C5 VisibilityQuery / C8 Wp_Bound_Gate 共用；Task 5 冻结）
#
# Feature: procedure-delegation-visibility-isolation
# Requirements: 5.15–5.16（每个独立身份产出且仅产出一个已登记 access_kind 的 grant；
#   未登记 kind 丢弃该 grant，无其他完整允许项时判不可访问）、7.9–7.10（逐 grant 完整命中
#   矩阵后才并集页面与动作，禁止跨身份拼接）。
# Design: "AccessGrant query" / "Core contracts and gate"（AccessGrant frozen dataclass）/
#   Property 8（每个 grant 只有一个已登记 kind，未知 kind 丢弃，多 grant 只能并集）。
# ---------------------------------------------------------------------------

# 页面范围全集哨兵：``allowed_sheet_keys == ALL_PAGES`` 表示整张底稿全部当前页面
# （lead / admin / supervisor_scope / lead_history 用）。
ALL_PAGES: Literal["all"] = "all"

# 已登记 access_kind 全集（Req 5.15/5.16）。查询层只允许产出这些 kind；
# 任何其他值一律作为未登记 grant 丢弃（``build_access_grant`` 返回 None）。
REGISTERED_ACCESS_KINDS: frozenset[str] = frozenset(
    {
        "admin",
        "supervisor_scope",
        "lead",
        "assignee",
        "reviewer",
        "lead_history",
        "row_history",
    }
)

# 只读 access_kind（History_Only：仅读 Current_Version，任何写动作/历史版本对外 404）。
READONLY_ACCESS_KINDS: frozenset[str] = frozenset({"lead_history", "row_history"})

# 页面范围恒为全集（all pages）的 access_kind（Req 5.10/5.17；admin/supervisor 覆盖 scope 内整稿）。
ALL_PAGE_ACCESS_KINDS: frozenset[str] = frozenset(
    {"admin", "supervisor_scope", "lead", "lead_history"}
)


@dataclass(frozen=True)
class AccessGrant:
    """单个访问授权项（不可变）。

    - ``access_kind``：恰好一个已登记 kind（``REGISTERED_ACCESS_KINDS`` 之一）。
    - ``identity``：该 grant 的来源身份（acting principal 标识，供审计/矩阵；如 user_id/staff_id 字符串）。
    - ``allowed_sheet_keys``：允许页面集合（``frozenset[str]``）或全集哨兵 ``ALL_PAGES``。
    - ``readonly``：True 表示该 grant 仅允许读取 Current_Version（History_Only），一切写动作被拒。

    每个 grant 必须独立完整命中 Action_Matrix 后才可并集；禁止跨 grant 拼接矩阵维度（Req 7.9/7.10）。
    """

    access_kind: str
    identity: str
    allowed_sheet_keys: frozenset[str] | Literal["all"]
    readonly: bool

    def __post_init__(self) -> None:  # noqa: D401 — 契约一致性守卫
        if self.access_kind not in REGISTERED_ACCESS_KINDS:
            # 未登记 kind 不得构造 AccessGrant（防止绕过 Req 5.16 的丢弃语义）。
            raise ValueError(f"未登记 access_kind: {self.access_kind!r}")
        if self.allowed_sheet_keys != ALL_PAGES and not isinstance(
            self.allowed_sheet_keys, frozenset
        ):
            raise ValueError("allowed_sheet_keys 必须为 frozenset[str] 或 'all'")

    def covers_sheet(self, sheet_key: str | None) -> bool:
        """该 grant 是否覆盖给定 sheet_key（``ALL_PAGES`` 覆盖任意页面）。"""
        if self.allowed_sheet_keys == ALL_PAGES:
            return True
        if sheet_key is None:
            return False
        return sheet_key in self.allowed_sheet_keys


def build_access_grant(
    access_kind: str,
    identity: str,
    allowed_sheet_keys: frozenset[str] | Literal["all"],
    readonly: bool,
) -> AccessGrant | None:
    """构造 grant；未登记 ``access_kind`` 返回 None（丢弃该 grant，Req 5.16 / Property 8）。

    查询层与 gate 统一经此工厂产出 grant，从而"未知 kind → 丢弃"是唯一路径，
    不会因构造异常而 500 或误放行。
    """
    if access_kind not in REGISTERED_ACCESS_KINDS:
        return None
    return AccessGrant(
        access_kind=access_kind,
        identity=identity,
        allowed_sheet_keys=allowed_sheet_keys,
        readonly=readonly,
    )


# ---------------------------------------------------------------------------
# 门与请求契约（C2 Contracts / C8 Wp_Bound_Gate；Task 6 冻结）
#
# Feature: procedure-delegation-visibility-isolation
# Requirements: 8.1–8.4（读正文/副作用前授权、Binding_Minimum、页面/绑定一致性）、
#   8.18–8.19（统一 resolve_wp_binding_and_access，先解析 Binding_Minimum 再返回 binding/role/
#   access_kind/allowed_sheet_keys/current_version）、9.1–9.7（External_Not_Found 统一 404）。
# Design: 组件 C2/C8 / "Core contracts and gate"（ResourceRef / WpBoundRequest / WpAccessContext）。
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceRef:
    """底稿绑定资源的定位标识（Binding_Minimum 输入）。

    - 服务端可解析的 identity 来源（``wp_id`` / ``wp_index_id`` / ``wp_code`` /
      ``procedure_*`` / ``procedure_code``）供 ``ProcedureWpResolver`` 联合解析唯一 ``wp_index_id``。
    - ``project_id`` 可空：URL 未带项目时由 gate 从最强 identity 反查（Req "无 project_id 反查"）。
    - ``client_*`` 为客户端显式声明的绑定（页面 / 版本 / wp / wp_index），gate 用于与服务端解析
      结果一致性校验（Req 8.4：不一致即拒绝）。
    仅承载定位标识，不含业务正文 / 名称 / 文件字节。
    """

    project_id: UUID | None = None
    wp_id: UUID | None = None
    wp_index_id: UUID | None = None
    wp_code: str | None = None
    procedure_instance_id: UUID | None = None
    procedure_row_task_id: UUID | None = None
    procedure_code: str | None = None
    audit_cycle: str | None = None
    # 客户端显式声明的绑定（供一致性校验，Req 8.4）
    client_wp_id: UUID | None = None
    client_wp_index_id: UUID | None = None


@dataclass(frozen=True)
class WpBoundRequest:
    """统一门请求（HTTP / callback / worker / retry / dead_letter 共用）。

    ``entrypoint`` 是稳定入口标识（Action_Matrix 的 entrypoint 维度，与 route 解耦，供 Task 16
    Route_Coverage_Ledger 静态映射）。``action`` 是语义动作类别；``source_state`` / ``target_state``
    描述状态迁移（无迁移用已登记的 ``"none"``，Req 7.8）。``requested_sheet_key`` / ``requested_version``
    是客户端请求的页面 / 版本；``token_claims`` 为 OnlyOffice/WOPI 令牌声明（Req 10）。
    ``review_reason`` 供 reviewer ``changes_requested`` 白名单校验（reason 必填）。
    """

    entry_kind: Literal["http", "callback", "worker", "retry", "dead_letter"]
    entrypoint: str
    action: str
    resource_ref: ResourceRef
    route_name: str | None = None
    method: str | None = None
    entry_family: str | None = None
    requested_sheet_key: str | None = None
    requested_version: str | None = None
    source_state: str = "none"
    target_state: str = "none"
    token_claims: Mapping[str, str] | None = None
    review_reason: str | None = None
    request_id: str | None = None
    # OnlyOffice/WOPI 原始签名令牌（Task 11 / 组件 C11 EditorSecurity）。存在时 gate 走全量校验
    # （签名/过期/jti/非空/逐 claim 绑定，Req 10.1–10.5/10.8）；仅有 ``token_claims`` dict 时走
    # 一致性绑定校验。附加此可选字段为纯 additive，不影响既有非编辑器入口。
    signed_token: str | None = None


@dataclass(frozen=True)
class WpAccessContext:
    """统一门 allow 结果（Req 8.19：binding / role / access_kind / allowed_sheet_keys / current_version）。

    - ``access_kinds``：促成本次 allow 的 **全部** 已命中 grant 的 access_kind 并集（多身份并集，Req 7.10）。
    - ``allowed_sheet_keys``：命中 grant 的页面并集（``ALL_PAGES`` 或 frozenset）。
    - ``resolved_sheet_key``：本次请求解析到的稳定 sheet_key（无页面级请求时为 None）。
    - ``current_version``：Current_Version（nullable wp → None，即"底稿尚未生成"）。
    - ``readonly``：True 表示本次仅由 readonly grant（History_Only）授权，写动作已被拒。
    """

    project_id: UUID
    wp_index_id: UUID
    role: VisibilityRole
    access_kinds: frozenset[str]
    allowed_sheet_keys: frozenset[str] | Literal["all"]
    resolved_sheet_key: str | None
    current_version: str | None
    readonly: bool
    wp_id: UUID | None = None
