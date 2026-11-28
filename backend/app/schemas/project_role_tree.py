"""用户 → 项目 → 角色 三层树的响应 Schema（project-data-permission-isolation Task 1.1）

本 spec 是**纯读组装 + 可视化**：不新增表/列/迁移，不提供任何写入路径。
三层节点的数据真源：
  - `UserNode`    ← `users`（含 V149 补的 `full_name`）
  - `ProjectNode` ← `project_users` 按 project_id 分组 JOIN `projects`
  - `RoleNode`    ← `project_users.role` 及其权限字段

═══════════════════════════════════════════════════════════════════════════
🔴 枚举一律以**字符串**承载（`.value`），不用 Enum 类型
═══════════════════════════════════════════════════════════════════════════
与 `schemas/login_user.py::LoginUser.system_role` 同一取舍：这些模型要 JSON
序列化出去（且未来可能进缓存），Enum 对象不可直接序列化。用 str 还有一个好处 ——
前端拿到的就是 `"manager"` 这种稳定字面量，不受 Python 侧 Enum 改名影响。

⚠️ 但**不加 Literal 约束**：库里可能存在 ORM 枚举尚未收录的历史值（本仓
`ProjectUserRole` 就因 V109 补过 `eqcr`）。用 `str` 能如实透出，用 Literal
会在遇到历史值时抛 ValidationError、让整棵树打不开 —— 展示层遇到脏数据应当
"如实显示"而非"拒绝服务"。

Validates: Requirements 1.2, 2.2, 2.3, 5.1
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# effective_data_scope 的中文标签（Req 5.3）
# ---------------------------------------------------------------------------

DATA_SCOPE_LABELS: dict[int, str] = {
    1: "全部数据",
    2: "自定义项目",
    6: "我参与的项目",
    5: "仅本人数据",
}
"""`effective_data_scope` → 中文范围标签（Req 5.3）。

⚠️ **取值集合必须与 `data_scope_service.VALID_DATA_SCOPES` 一致**（1/2/5/6）。
   3/4 是已废弃的部门维度，`normalize_data_scope` 会把它们降级为 5 ⇒
   本字典**刻意不收录 3/4**：能走到展示层的值必然已被规整过，
   若这里也收录反而会掩盖"某处漏调 normalize"的问题。
   由 `tests/data_scope_participant/test_label_tables_consistency.py` 钉住一致性。

📌 **6「我参与的项目」是 2026-08-31 新增**
   （spec `data-scope-participant-visibility`）：语义 = 项目级可见集
   （5 来源并集），与 5「仅本人数据」的区别是前者含**被指派**的项目。

⚠️ **本仓有三份 data_scope 标签表**，加档时必须同步全部三处，否则漏改的那处
   会静默显示「未知范围」：
     ① 本文件（权限中心的项目角色树）
     ② `audit-platform/frontend/src/services/systemRoleApi.ts::DATA_SCOPE_LABELS`
     ③ 同文件的 `DATA_SCOPE_OPTIONS`（带 hint 的下拉选项）
   ⇒ 本档位加入时 ① 曾被漏掉（spec 的改动清单里没列它），
     靠 `test_project_role_tree_subtree.py` 的 sampled_from 扩到 6 之后才暴露。
"""

_UNKNOWN_SCOPE_LABEL = "未知范围"


def data_scope_label(scope: int) -> str:
    """取 `effective_data_scope` 的中文标签，未知值返回「未知范围」而不抛异常。

    🔴 **不抛异常是刻意的**：这是纯展示字段，若因一个脏 scope 值让整个
       用户子树接口 500，代价远大于显示一行"未知范围"。真正的规整责任在
       `data_scope_service.normalize_data_scope`，那里会记 warning。
    """
    return DATA_SCOPE_LABELS.get(scope, _UNKNOWN_SCOPE_LABEL)


# ---------------------------------------------------------------------------
# 第 3 层：角色节点（叶子）
# ---------------------------------------------------------------------------


class RoleNode(BaseModel):
    """树第 3 层（叶子）：账号在某项目下的项目角色。

    `project_users` 对 `(project_id, user_id)` 有部分唯一索引
    （`where is_deleted = false`）⇒ **同一账号在同一项目恒只有一条角色记录**，
    故 `ProjectNode.role` 是单个对象而非列表。
    """

    model_config = ConfigDict(from_attributes=True)

    role: str
    """`ProjectUserRole` 的 `.value`：partner/manager/auditor/qc/eqcr/readonly。"""

    permission_level: str
    """`PermissionLevel` 的 `.value`：edit/review/readonly（edit > review > readonly）。"""

    valid_from: date | None = None
    valid_to: date | None = None

    scope_cycles: str | None = None
    """⚠️ 库里是 **`Text` 而非 JSONB/ARRAY** ⇒ 原样透出字符串，**不在此解析**。

    `deps.py::get_user_scope_cycles` 用 `sc.split(",")` 解析它。本 spec 是只读
    展示，若在这里也解析一遍就成了第二套口径，两处一旦漂移会让"树上显示的循环
    范围"与"实际生效的过滤"不一致 —— 那种不一致比不解析更糟。
    """

    scope_accounts: str | None = None
    """同 `scope_cycles`：`Text` 原样透出。"""


# ---------------------------------------------------------------------------
# 第 2 层：项目节点
# ---------------------------------------------------------------------------


class ProjectNode(BaseModel):
    """树第 2 层：账号参与的一个项目。"""

    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    name: str
    client_name: str
    status: str
    """`ProjectStatus` 的 `.value`：created/planning/execution/completion/reporting/archived。"""

    out_of_scope: bool = False
    """该项目**不在**目标账号数据权限可见集内（Req 5.4 的视觉标记依据）。

    🔴 **语义是"项目级可见但数据权限不可见"**，即：账号在 `project_users` 里
       有这个项目的绑定行（所以它出现在树上），但 `resolve_scope_project_ids`
       算出的集合里没有它 ⇒ 该账号实际打不开这个项目。
       这个"配了角色却看不到"的矛盾状态正是本字段要暴露的东西。

    ⚠️ **`resolve_scope_project_ids` 返回 `None` 时（scope=1 不过滤），
       所有节点的本字段都必须是 `False`** —— `None` 与空集语义相反，
       误把 `None` 当空集会让管理员看到"全部项目都不可见"的假象。
    """

    role: RoleNode


# ---------------------------------------------------------------------------
# 第 1 层：用户节点
# ---------------------------------------------------------------------------


class UserNode(BaseModel):
    """树第 1 层：一个账号。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    full_name: str | None = None
    """V149（account-field-completion）补的列，nullable ⇒ 历史账号可能为空。"""

    email: str
    system_role: str
    """`users.role`（`UserRole`）的 `.value`：admin/partner/manager/auditor/qc/eqcr/readonly。

    ⚠️ 实测本仓 `UserRole` 是 **7 值、无 `site_lead`**（spec 首版误列为 8 值）。
       按 8 值假设写前端分支会产出恒不命中的死代码。
    """

    is_active: bool

    has_children: bool = False
    """该账号是否有可展开的项目层（Req 1.3）。

    🔴 **无项目的账号必须仍然返回**（`has_children=False`），不能因为"展开是空的"
       就把它从根层过滤掉 —— 管理员需要看到"这个账号没有任何项目角色"这个事实，
       那往往正是要排查的问题。

    ⚠️ 由 `list_user_nodes` 用**一次聚合查询**对整页批量计算，
       不是逐个账号查（那是根层 N+1，6000 账号规模下会打爆）。
    """


class UserNodePage(BaseModel):
    """根层分页响应（Req 1.5）。"""

    model_config = ConfigDict(from_attributes=True)

    items: list[UserNode] = Field(default_factory=list)
    total: int
    """**过滤后**的未删除账号总数（不是当前页条数，也不是全库总数）。

    搜索条件生效时 `total` 必须是搜索结果的总数 —— 否则前端分页器会算出
    不存在的页码。
    """


# ---------------------------------------------------------------------------
# 单用户子树（懒加载第二段）
# ---------------------------------------------------------------------------


class UserSubtree(BaseModel):
    """展开某账号时返回的项目层 + 角色层 + 数据权限视角（Req 2.1~2.3, 5.1~5.3）。"""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID

    effective_data_scope: int
    """目标账号最终生效的数据权限范围，恒 ∈ {1, 2, 5, 6}。

    由 `assemble_login_user(target_user, db)` 组装、
    `compute_effective_data_scope` 算出 —— **本 spec 不重算**（Req 5.5）。
    重算会与 dept-role 的口径漂移，而权限口径漂移是最难排查的一类缺陷。
    """

    effective_data_scope_label: str
    """`effective_data_scope` 的中文标签，由 `data_scope_label()` 生成。"""

    projects: list[ProjectNode] = Field(default_factory=list)
    """该账号参与的项目（含 `out_of_scope` 标记）。空列表 = 未参与任何项目。"""


__all__ = [
    "DATA_SCOPE_LABELS",
    "ProjectNode",
    "RoleNode",
    "UserNode",
    "UserNodePage",
    "UserSubtree",
    "data_scope_label",
]
