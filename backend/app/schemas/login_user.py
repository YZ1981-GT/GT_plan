"""LoginUser —— 登录态鉴权上下文（dept-role-data-permission Task 7.1）

登录成功后组装一次、缓存进 Redis，后续请求直接取用，避免每个请求都重查
「账号 → 全部角色 → 每角色 data_scope → sys_role_project 并集」这条链路。

📌 **`LoginUser` 必须满足 `data_scope_service.ScopeContext` 协议**
   （`user_id` / `effective_data_scope` / `custom_project_ids` 三个属性）。
   Task 2 刻意用 Protocol 而非 import 本模块，以保持纯逻辑层可独立测试；
   本模块反过来也**不** import `ScopeContext` —— 结构化协议靠字段名匹配，
   不需要显式继承。文件末尾有一条运行时自检确保两者不脱钩。

Validates: Requirements 5.1
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoleScope(BaseModel):
    """账号绑定的单个角色及其数据权限范围。"""

    model_config = ConfigDict(from_attributes=True)

    role_id: int
    role_key: str
    data_scope: int
    """该角色配置的原始 data_scope。

    ⚠️ 这里保留**原始值**（可能是库里的脏数据 3/4），不在此处规整 ——
       规整发生在 `compute_effective_data_scope` 里并会记 warning。
       若在本层就悄悄改成 5，日后排查「为什么这个角色的范围不生效」时
       会看不到任何线索。
    """


class LoginUser(BaseModel):
    """登录态的完整鉴权上下文。

    字段来源：
      - `user_id` / `username` / `system_role`：`users` 表
      - `roles`：`sys_user_role` JOIN `sys_role`（仅未删除角色）
      - `custom_project_ids`：该账号所有 **data_scope=2** 角色在
        `sys_role_project` 的项目**并集**（Req 6.2）
      - `effective_data_scope`：`compute_effective_data_scope(各角色 data_scope,
        fallback=users.role 对应 seed 角色的 data_scope)`
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    username: str

    system_role: str
    """`users.role` 枚举值（如 admin/partner/manager…）。

    保留它有两个用途：
      1. `get_visible_project_ids` 的 admin/partner **短路分支**判据（Req 8.2）
      2. 账号未绑定任何角色时的**回退**依据（Req 10.5）
    ⚠️ 存字符串而非枚举对象：本模型要 JSON 序列化进 Redis，枚举对象不可直接序列化。
    """

    roles: list[RoleScope] = Field(default_factory=list)
    """账号绑定的全部未删除角色。空列表 = 未绑定任何角色（走 Req 10.5 回退）。"""

    custom_project_ids: list[UUID] = Field(default_factory=list)
    """data_scope=2 角色的自定义项目并集。

    🔴 **空列表在 scope=2 下意味着「什么都不可见」，不是「不限制」**
       （Req 9.4 / 12.1）。`resolve_scope_project_ids` 会返回空集而非 None。
       用 list 而非 set 是为了 JSON 可序列化；语义上是集合（已去重）。
    """

    effective_data_scope: int
    """多角色叠加后的最终数据权限范围，恒 ∈ {1, 2, 5}。

    由 `compute_effective_data_scope` 算出（取最大权限 = PRIORITY_ORDER 的 argmin）。
    ⚠️ **不要在读取侧重算**：重算会与组装时的口径漂移（例如角色在两次之间被改动），
       导致同一请求内前后两处判断不一致。要刷新就走缓存失效。
    """

    def is_admin_system_role(self) -> bool:
        """是否为 admin —— `get_visible_project_ids` 的短路分支判据（Req 8.2）。

        放在这里而不是散落在调用处，避免各处各写一遍字符串字面量。

        🔴 **partner 刻意不在此列**（`partner-project-visibility-scope` Req 6.1/6.2）。
           合伙人的项目可见范围已收紧为「五来源并集」（本人创建 / 下属创建 /
           本人签字 / 被委派底稿 / 被团队委派），由
           `services/partner_visibility_service.partner_visible_project_ids()` 计算。
           若让 partner 在此返回 True，data_scope 短路会直接返回**全部**未删除项目，
           把那份收紧整个绕过去 ⇒ 收紧形同虚设。

        ⚠️ **本方法原名 `is_privileged_system_role()`、原判据 `in ("admin","partner")`。**
           改名是刻意的：留着「privileged」会与实际含义（只有 admin）脱节，
           后来人容易顺手把 partner 加回来。名字里写死 admin，误加时立刻显得不自然。

        ⚠️ **不要靠改「权限地板」来实现收紧**：`assemble_login_user` 的 Req 10.6
           仍会把 partner 的 `effective_data_scope` 抬到 1，这是无害的 ——
           partner 因本方法返回 False 而走进 AND 交集逻辑，
           此时 scope=1 表示「数据权限不额外过滤」⇒ 交集 = 项目级可见集 = 收紧后的五来源。
        """
        return self.system_role == "admin"


__all__ = ["LoginUser", "RoleScope"]


def _assert_satisfies_scope_context() -> None:
    """自检：`LoginUser` 的字段名必须与 `ScopeContext` 协议对齐。

    Task 2 的 `resolve_scope_project_ids` 通过 `getattr` 读这三个字段。
    字段一旦改名（如 `custom_project_ids` → `custom_projects`），
    那边会静默取到 None 并按空集处理 —— **不报错、但权限全错**。
    故在 import 时就做一次结构检查，让脱钩立刻暴露。
    """
    required = ("user_id", "effective_data_scope", "custom_project_ids")
    missing = [f for f in required if f not in LoginUser.model_fields]
    if missing:  # pragma: no cover - 只在字段被改名时触发
        raise RuntimeError(
            f"LoginUser 缺少 ScopeContext 协议要求的字段 {missing} —— "
            "data_scope_service.resolve_scope_project_ids 会静默取到 None "
            "并按空集处理（不报错但权限全错）。请同步修改两处。"
        )


_assert_satisfies_scope_context()
