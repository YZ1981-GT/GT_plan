"""
Permission Matrix Service (P0-4)

系统角色 × 项目职责 → 操作权限集合。
纯 Python 实现，不依赖 DB，作为权限判断的单一真源。

Operation Codes (首批 7 个):
- project:view   — 查看项目基本信息
- wp:edit        — 编辑底稿
- wp:review      — 复核底稿
- report:edit    — 编辑报表
- report:sign    — 签发报表
- note:edit      — 编辑附注
- archive:manage — 管理归档
"""

from __future__ import annotations

# ─── 角色别名 → 系统角色（归一化的单一真源） ─────────────────────────────────
ROLE_ALIAS_MAP: dict[str, str] = {
    # 审计 5 角色 → 系统角色
    "assistant": "auditor",
    "auditor": "auditor",
    "manager": "manager",
    # 现场经理（独立系统角色，权限等同项目经理）。
    #
    # 🔴 **用别名而不是在 `ROLE_OPERATIONS` 复制一份 manager 的权限集**：
    #    复制的两份在日后有人改 manager 权限时会**静默漂移**——
    #    不报错、不打红，只表现为「现场经理少了个按钮」，极难定位。
    #    别名下 site_lead 的操作集**恒等于** manager，无需维护第二处。
    #    ⚠️ 别名对 `deps.py::require_role` **无效**（它是字面比对）⇒ 硬编码门禁
    #       仍须逐个显式补 "site_lead"。
    "site_lead": "manager",
    "partner": "partner",
    "signing_partner": "partner",
    "qc_partner": "qc",
    "qc": "qc",
    "qc_reviewer": "qc",
    "quality_control": "qc",
    "eqcr": "eqcr",
    # admin 保留
    "admin": "admin",
}


def normalize_role(role: str) -> str:
    """将审计角色名/别名归一化为系统角色名。

    对 `UserRole` 的 8 个枚举值，**只有 `site_lead → manager` 一处发生变化**，
    其余 7 个恒等 ⇒ 在既有查表处插入本函数对现有角色行为零影响。

    🔴 **本函数必须在「以角色名为键的 dict 查表处」调用，而不是只在包装层调**。
       实测教训：本仓曾有**两层同名函数** ——
       `app.permissions.permission_matrix.get_operations_for_role`（过归一化）
       与本模块的 `get_allowed_operations`（不过）⇒ 守卫从上层 import 全绿，
       而生产代码 `deps.require_operation` 调的是下层，
       导致 `site_lead` 在 **9 个写端点**静默 403。

       同类形态本仓共 **6 处**（均已修）：
         1. 本模块 `get_allowed_operations`（← `deps.require_operation` 的根因）
         2. `api/users.py` 的 `ROLE_PERMISSION_MATRIX`（`/users/me` 的权限列表）
         3. `routers/project_permissions.py` 的 `SYSTEM_ROLE_PERMISSIONS`
         4. `services/role_context_service.py` 的 `_ROLE_PRIORITY`
         5. `services/wp_cell_lock_service.py` 的 `role_hierarchy`
         6. `services/role_workbench_facade.py` 的 `ROLE_SECTION_REGISTRY`

    Args:
        role: 原始角色字符串（如 "assistant", "qc_partner", "site_lead"）

    Returns:
        系统角色名（如 "auditor", "qc", "manager"）。未登记的别名原样返回
        （大小写归一 + 去空格后），由调用方的 `.get(..., 默认值)` 兜底。
    """
    r = role.lower().strip()
    return ROLE_ALIAS_MAP.get(r, r)


# ─── 工时审批角色白名单（单一真源） ─────────────────────────
# 工时审批类端点（全局 + 项目级）的角色门禁必须引用本常量，
# 禁止在 router 里各自手写四元组。
WORKHOUR_APPROVER_ROLES: list[str] = ["admin", "partner", "manager", "site_lead"]


# ─── 首批 7 个 Operation Codes ───────────────────────────────────────────────
OPERATION_CODES: list[str] = [
    "project:view",
    "wp:edit",
    "wp:review",
    "report:edit",
    "report:sign",
    "note:edit",
    "archive:manage",
]

# ─── 系统角色 → 允许操作映射 ─────────────────────────────────────────────────
# 角色继承: admin > partner > manager > auditor
#           admin > partner > qc > auditor
#           eqcr 独立（只读 + 特定复核权限）
ROLE_OPERATIONS: dict[str, set[str]] = {
    "admin": set(OPERATION_CODES),  # admin 拥有全部操作
    "partner": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "report:sign",
        "note:edit",
        "archive:manage",
    },
    "manager": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "note:edit",
    },
    "auditor": {
        "project:view",
        "wp:edit",
        "note:edit",
    },
    "qc": {
        "project:view",
        "wp:review",
        "report:edit",
    },
    "eqcr": {
        "project:view",
        "wp:review",
    },
}

# ─── P0-4.3: 项目职责 → 额外操作映射 ────────────────────────────────────────
PROJECT_ROLE_OPERATIONS: dict[str, set[str]] = {
    "preparer": {
        "project:view",
        "wp:edit",
        "note:edit",
    },
    "reviewer": {
        "project:view",
        "wp:review",
        "report:edit",
    },
    "manager": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "note:edit",
    },
    "partner": {
        "project:view",
        "wp:edit",
        "wp:review",
        "report:edit",
        "report:sign",
        "note:edit",
        "archive:manage",
    },
    "eqcr": {
        "project:view",
        "wp:review",
    },
}


def get_allowed_operations(
    system_role: str,
    project_role: str | None = None,
) -> set[str]:
    """
    根据系统角色和可选的项目职责，返回允许的操作集合。

    P0-4.3: 将系统角色 + 项目职责解析为 operation set（并集）。

    Args:
        system_role: 系统级角色 (admin/partner/manager/site_lead/auditor/qc/eqcr)
            —— 也接受别名（assistant / qc_partner / signing_partner 等），
            内部经 `normalize_role` 归一化。
        project_role: 项目级职责 (preparer/reviewer/manager/partner/eqcr)

    Returns:
        允许的操作 code 集合
    """
    # 🔴 **必须过 `normalize_role`，不能只 `lower().strip()`**。
    #    原实现是字面查表 ⇒ `ROLE_OPERATIONS` 无 `site_lead` 键 ⇒ 现场经理拿到
    #    **空集** ⇒ `can()` 对任何 operation 都 False ⇒ `deps.require_operation`
    #    把 site_lead 拦在 **9 个写端点**外（底稿保存 / 报表生成 / 调整分录 / 附注编辑）。
    #
    #    ⚠️ 修在**本函数**而不是各调用方：service 层三个公开入口
    #       （`can` / `why_cannot` / `get_permission_matrix`）全部汇聚到这里，
    #       改一处即全覆盖；而修调用方会漏掉日后新增的入口。
    role = normalize_role(system_role)
    base_ops = ROLE_OPERATIONS.get(role, set())

    # P0-4.3: project_role 叠加额外权限
    if project_role:
        pr = project_role.lower().strip()
        project_ops = PROJECT_ROLE_OPERATIONS.get(pr, set())
        return base_ops | project_ops

    return set(base_ops)  # 返回副本，避免外部修改


def can(
    system_role: str,
    project_role: str | None,
    operation: str,
) -> bool:
    """
    判断指定角色组合是否允许执行某操作。
    """
    allowed = get_allowed_operations(system_role, project_role)
    return operation in allowed


def why_cannot(
    system_role: str,
    project_role: str | None,
    operation: str,
) -> str | None:
    """
    返回不能执行操作的原因，如果可以执行则返回 None。
    """
    if can(system_role, project_role, operation):
        return None

    role_desc = system_role
    if project_role:
        role_desc = f"{system_role}(项目职责: {project_role})"

    return f"角色 {role_desc} 无 {operation} 权限"


def get_permission_matrix(
    system_role: str,
    project_role: str | None = None,
) -> dict:
    """
    P0-4.4: 返回完整的权限矩阵响应（供 API 端点使用）。
    """
    allowed = get_allowed_operations(system_role, project_role)
    denied = set(OPERATION_CODES) - allowed
    return {
        "operations": sorted(allowed),
        "denied_operations": sorted(denied),
        "system_role": system_role,
        "project_role": project_role,
        "all_operation_codes": OPERATION_CODES,
    }
