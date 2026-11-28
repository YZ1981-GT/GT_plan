"""角色-数据权限体系 ORM（dept-role-data-permission Task 1.1）

三张表：`sys_role`（角色 + data_scope）· `sys_user_role`（账号↔角色多对多）·
`sys_role_project`（角色↔自定义项目多对多，仅 data_scope=2 使用）。

⚠️ 本模块**不定义任何部门相关 ORM**：
  - `sys_role_dept` 在本库既无表也无 ORM，且本 spec 采用项目维度方案 ⇒ 不建不定义
    （旧设计里"用 IF NOT EXISTS 保留 DB 表"的做法会实际建出一张废弃死表）。
  - `sys_dept` 表**已由 `account-field-completion` 的 V150 建出**，且已有 `Department`
    ORM（`app/models/core.py`）⇒ 本模块不重复定义、不引用；data_scope 解析链路
    完全不读部门。

📌 id 类型说明：`sys_role.id` 用**自增整型**而非全仓惯用的 UUID —— 这是 spec 明确
   的架构约束（对齐若依 RuoYi 的 `sys_role` 结构，`sys_user_role.role_id` /
   `sys_role_project.role_id` 均为 INT FK）。`user_id` / `project_id` 仍是 UUID，
   与 `users.id` / `projects.id` 对齐。

Validates: Requirements 3.7, 9.1, 11.1, 11.2
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

# ---------------------------------------------------------------------------
# data_scope 取值常量（唯一定义处，服务层与迁移 seed 都以此为准）
# ---------------------------------------------------------------------------

DATA_SCOPE_ALL = 1
"""全部数据 —— 不加过滤条件，可见全部未删除项目。"""

DATA_SCOPE_CUSTOM = 2
"""自定义项目 —— 取该账号所有 data_scope=2 角色在 sys_role_project 的项目并集。"""

DATA_SCOPE_SELF = 5
"""仅本人数据 —— 取 projects.created_by == 当前账号 id 的项目。

⚠️ 依赖 `projects.created_by` 有值。该列由 Task 1.6 补齐写入路径（`AuditMixin`
   不会自动填），历史项目行仍为 NULL ⇒ 老数据上本范围恒空集，属预期而非缺陷。
"""

DATA_SCOPE_PARTICIPANT = 6
"""我参与的项目 —— 取**项目级可见集**（`deps._project_level_visible_ids` 的 5 来源并集）。

即 `ProjectUser` ∪ `Project.partner_id` ∪ `Project.manager_id` ∪ `ProjectMember`
∪ `Project.created_by`，全部限未删除项目。

🔴 **与 `DATA_SCOPE_SELF`(5) 的区别，这是本档存在的全部理由**：
   5 只认「我**创建**的」，6 认「我**参与**的」。被指派为项目经理／现场负责人
   但不是创建人的账号，在 scope=5 下最终可见集为**空**（真库实测
   `xingzihao2`/`xingzihao3` 均为 0）—— 因为最终可见 = 项目级 ∩ 数据权限，
   而项目级认成员关系、scope=5 只认 created_by，两者几乎不相交。

⚠️ **为什么不直接放宽 scope=5 的语义**：上游 `dept-role-data-permission`
   Req 6.4 与文首「禁止的绕法」**明文禁止** ——「不得改用 `project_users` /
   `partner_id` / `manager_id` 充当『仅本人』的依据 …… 替换等于本条数据权限
   从未实现，且会让 data_scope=5 与 data_scope=2 在结果上难以区分」。
   ⇒ 本档是**扩展**而非替换，scope=5 的语义一字未动。

⚠️ **为什么取值用 6 而不复用 3/4**：3/4 在 `DEPRECATED_DATA_SCOPES` 里，
   `normalize_data_scope` 会把它们降级为 5 并告警。复用必与既有降级逻辑冲突。
   6 是当前未被占用的最小正整数。

⚠️ **权限序上 6 排在 5 之前**（见 `data_scope_service.PRIORITY_ORDER`）：
   `created_by` 本身就是项目级 5 来源之一 ⇒ `scope5 结果 ⊆ scope6 结果`
   对任意账号、任意数据状态**恒成立** ⇒ 6 的可见范围恒不小于 5。
"""

DATA_SCOPE_DEPT = 3
"""（已废弃）本部门 —— 部门维度不实现。解析层降级为 SELF，创建/修改层拒绝。"""

DATA_SCOPE_DEPT_AND_CHILD = 4
"""（已废弃）本部门及以下 —— 同上。"""

VALID_DATA_SCOPES = frozenset({
    DATA_SCOPE_ALL,
    DATA_SCOPE_CUSTOM,
    DATA_SCOPE_PARTICIPANT,
    DATA_SCOPE_SELF,
})
"""创建/修改角色时接受的取值集合。3/4 已废弃，提交时应被拒（Req 3.2）。

⚠️ 本集合与 `data_scope_service.PRIORITY_ORDER` 的**键集必须相等** ——
   加了合法值却忘了排优先级，`compute_effective_data_scope` 会在
   `PRIORITY_ORDER[s]` 处抛 `KeyError`（运行时才炸）。
   由 `tests/data_scope_participant/test_baseline_three_scopes.py::
   test_priority_order_covers_every_valid_scope` 钉住。
"""

DEPRECATED_DATA_SCOPES = frozenset({DATA_SCOPE_DEPT, DATA_SCOPE_DEPT_AND_CHILD})
"""已废弃取值。解析层遇到时按最小权限（SELF）处理并记 warning（Req 6.5 / 12.3）。"""

ROLE_STATUS_ENABLED = "0"
"""角色启用（沿用若依约定：'0' 正常 / '1' 停用）。"""

ROLE_STATUS_DISABLED = "1"


class SysRole(Base, SoftDeleteMixin, TimestampMixin):
    """角色（数据权限维度）。

    与现有硬编码枚举 `UserRole`（存在 `users.role` 列）**双轨并存**：
    枚举角色保留以兼容旧代码，本表负责数据权限；V156 会把 7 个枚举值 seed 成本表记录。
    """

    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="角色名称"
    )
    role_key: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="角色标识，枚举角色与 UserRole 值一致"
    )
    data_scope: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
        comment=(
            "数据权限范围：1=全部 2=自定义项目 6=我参与的项目 5=仅本人"
            "（3/4 已废弃）"
        ),
    )
    """数据权限范围。取值常量见本模块顶部的 `DATA_SCOPE_*`。

    ⚠️ **无 CHECK 约束**（刻意）：库里可能存在历史脏值 3/4，前端的角色编辑
       弹窗需要能回显它们再让管理员改正（`RoleDataScopeManager.spec.ts` D 层
       有对应判据）。加 CHECK 会让那些历史行无法被读出/更新。
       合法性校验的**唯一入口**是 `role_service.validate_data_scope`（抛 400）。
    """
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'0'"),
        comment="状态：0=正常 1=停用",
    )

    __table_args__ = (
        # role_key 在未删除记录内唯一（Req 3.3）。软删后可复用同名 key，
        # 故用 partial unique index 而非表级 UNIQUE 约束 —— 与 sys_dept.code 同一手法。
        Index(
            "idx_sys_role_key",
            "role_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SysRole id={self.id} role_key={self.role_key!r} "
            f"data_scope={self.data_scope}>"
        )


class SysUserRole(Base):
    """账号-角色多对多绑定。

    无软删/时间戳：绑定关系用**覆盖写**语义维护（删旧插新，Req 4.1），
    保留历史行反而会让"当前生效角色"产生歧义。
    """

    __tablename__ = "sys_user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, comment="账号 id"
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id"), primary_key=True, comment="角色 id"
    )

    __table_args__ = (
        Index("idx_sys_user_role_user", "user_id"),
        Index("idx_sys_user_role_role", "role_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SysUserRole user_id={self.user_id} role_id={self.role_id}>"


class SysRoleProject(Base):
    """角色-自定义项目多对多（仅 data_scope=2 使用）。

    替代原设计的 `sys_role_dept`：自定义数据权限范围由"角色直接勾选已有项目"决定，
    而不是"角色勾选部门 → 部门下的人/项目"。同样用覆盖写语义（Req 3.4 / 3.5）。
    """

    __tablename__ = "sys_role_project"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("sys_role.id"), primary_key=True, comment="角色 id"
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), primary_key=True, comment="项目 id"
    )

    __table_args__ = (
        # 主查询方向恒为「按 role_id 取项目集合」（组装 LoginUser.custom_project_ids），
        # 复合主键的前导列已是 role_id，此索引为显式声明（与迁移 V157 一致）
        Index("idx_sys_role_project_role", "role_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SysRoleProject role_id={self.role_id} project_id={self.project_id}>"
