# 核心数据库表：用途与使用位置

> 生成日期：2026-11-20。范围：业务核心表（约 60 张）。其余 300 多张内部表见文末说明。
> 字段明细见 `database-tables-columns.md`；业务域概览见 `database-tables.md`。
>
> **读法**
>
> - 「用到的页面」：前端组件文件名，是按表名在前端源码中的字面量匹配得到的，只能说明页面"可能用到"。标「待核实」的表示只能确定后端在用，页面要在浏览器里验证。
> - 「后端」：后端 `backend/app` 中引用该表的模块，同样是按表名或 ORM 类名匹配。
> - 标 **疑似冗余** 的表只是代码里找不到使用，**不等于可以删**，删除前要查生产库数据和计划中的功能。

## 一、用户、组织与权限

### `users` 系统用户 — 在「权限管理」页展示

- **是什么**：系统登录账号。
- **用到的页面**：`UserManagement.vue`（用户管理，列出和编辑账号）、`PermissionCenter.vue`（权限中心）、`DepartmentManagement.vue`（部门管理）。另有底稿列表 `WorkpaperList.vue` 显示负责人姓名。
- **后端**：`core.py`、`users.py`、`deps.py`（登录鉴权）、`audit_log.py`。
- **主要字段**：`id`（主键）、`username`（登录名）、`full_name`（全称）、`email`、`role`（系统角色）、`is_active`（是否启用）、`dept_id`（部门）、`parent_partner_id`（上级合伙人，指向 users 自己）。
- **状态**：在用。

**字段**（共 17 个，来源 `database-tables-columns.md`）：

| 字段                  | 中文名     | 说明                 | 类型         | 主键  | 可空  | 外键       |
| ------------------- | ------- | ------------------ | ---------- | --- | --- | -------- |
| `id`                | 主键      | 通用字段，见文首           | 编号         | 是   |     |          |
| `username`          | 登录名     | （据字段名）             | 文本（≤150 字） |     | 否   |          |
| `email`             | 邮箱      | （据字段名）             | 文本（≤255 字） |     | 否   |          |
| `hashed_password`   | 密码（加密后） | 不存明文               | 文本（≤255 字） |     | 否   |          |
| `role`              | 系统角色    | （据字段名）             | 枚举         |     | 否   |          |
| `office_code`       | 所属分所    | （据字段名）             | 文本（≤50 字）  |     | 是   |          |
| `is_active`         | 是否启用    | 停用后不能登录            | 是 / 否      |     | 否   |          |
| `language`          |         | 未查明                | 文本（≤10 字）  |     | 否   |          |
| `full_name`         | 全称名称    | 用户全名               | 文本（≤100 字） |     | 是   |          |
| `parent_partner_id` | 上级合伙人编号 | 所属合伙人ID；指向 `users` | 编号         |     | 是   | users.id |
| `dept_id`           | 部门编号    | （据字段名）             | 编号         |     | 是   |          |
| `is_deleted`        | 是否已删除   | 通用字段，见文首           | 是 / 否      |     | 否   |          |
| `deleted_at`        | 删除时间    | 通用字段，见文首           | 时间         |     | 是   |          |
| `created_at`        | 创建时间    | 通用字段，见文首           | 时间         |     | 否   |          |
| `updated_at`        | 更新时间    | 通用字段，见文首           | 时间         |     | 否   |          |
| `created_by`        | 创建人     | 通用字段，见文首           | 编号         |     | 是   | users.id |
| `updated_by`        | 修改人     | 通用字段，见文首           | 编号         |     | 是   | users.id |

### `sys_role` 角色（数据权限维度）

- **是什么**：角色定义，决定数据可见范围（data_scope）。
- **后端**：`sys_role.py`、`sys_permission.py`。
- **前端**：未发现表名字面量，通过接口使用，页面待核实。
- **状态**：在用。

**字段**（共 9 个，来源 `database-tables-columns.md`）：

| 字段           | 中文名   | 说明                                          | 类型         | 主键  | 可空  | 外键  |
| ------------ | ----- | ------------------------------------------- | ---------- | --- | --- | --- |
| `id`         | 主键    | 通用字段，见文首                                    | 整数         | 是   |     |     |
| `name`       | 名称    | 角色名称                                        | 文本（≤100 字） |     | 否   |     |
| `role_key`   | 角色键   | 角色标识，枚举角色与 UserRole 值一致                     | 文本（≤100 字） |     | 否   |     |
| `data_scope` | 数据范围  | 数据权限范围：1=全部 2=自定义项目 6=我参与的项目 5=仅本人（3/4 已废弃） | 整数         |     | 否   |     |
| `status`     | 状态    | 状态：0=正常 1=停用                                | 文本（≤10 字）  |     | 否   |     |
| `is_deleted` | 是否已删除 | 通用字段，见文首                                    | 是 / 否      |     | 否   |     |
| `deleted_at` | 删除时间  | 通用字段，见文首                                    | 时间         |     | 是   |     |
| `created_at` | 创建时间  | 通用字段，见文首                                    | 时间         |     | 否   |     |
| `updated_at` | 更新时间  | 通用字段，见文首                                    | 时间         |     | 否   |     |

### `sys_user_role` 账号-角色绑定

- **是什么**：用户和角色的多对多关系。
- **后端**：`sys_role.py`、`login_user.py`。
- **状态**：在用。

**字段**（共 2 个，来源 `database-tables-columns.md`）：

| 字段        | 中文名  | 说明                  | 类型  | 主键  | 可空  | 外键          |
| --------- | ---- | ------------------- | --- | --- | --- | ----------- |
| `user_id` | 用户   | 账号 id；指向 `users`    | 编号  | 是   |     | users.id    |
| `role_id` | 角色编号 | 角色 id；指向 `sys_role` | 整数  | 是   |     | sys_role.id |

### `sys_dept` 部门组织架构

- **是什么**：部门树。
- **后端**：`core.py`、`dept_head_visibility_service.py`（部门负责人可见范围）。
- **前端**：`DepartmentManagement.vue`（部门管理页，页面待核实是否直接读这张表）。
- **状态**：在用。

**字段**（共 10 个，来源 `database-tables-columns.md`）：

| 字段            | 中文名   | 说明                            | 类型         | 主键  | 可空  | 外键          |
| ------------- | ----- | ----------------------------- | ---------- | --- | --- | ----------- |
| `id`          | 主键    | 通用字段，见文首                      | 编号         | 是   |     |             |
| `name`        | 名称    | 部门名称（未软删范围内唯一）                | 文本（≤100 字） |     | 否   |             |
| `parent_id`   | 上级编号  | 父部门ID；指向 `sys_dept`           | 编号         |     | 是   | sys_dept.id |
| `head_id`     |       | 部门负责人，引用 users(id)；指向 `users` | 编号         |     | 是   | users.id    |
| `sort_order`  | 排序    | 排序顺序                          | 整数         |     | 否   |             |
| `description` | 说明    | 部门描述                          | 长文本        |     | 是   |             |
| `is_deleted`  | 是否已删除 | 通用字段，见文首                      | 是 / 否      |     | 否   |             |
| `deleted_at`  | 删除时间  | 通用字段，见文首                      | 时间         |     | 是   |             |
| `created_at`  | 创建时间  | 通用字段，见文首                      | 时间         |     | 否   |             |
| `updated_at`  | 更新时间  | 通用字段，见文首                      | 时间         |     | 否   |             |

### `project_users` 项目成员

- **是什么**：某个项目下的成员及其角色（鉴权主要依据）。
- **用到的页面**：`UserProjectRoleTree.vue`（用户-项目-角色树）。
- **后端**：`deps.py`（项目权限校验）、`core.py`、`sys_permission.py`。
- **状态**：在用，核心表。

**字段**（共 13 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名   | 说明                                                                                          | 类型    | 主键  | 可空  | 外键          |
| ------------------ | ----- | ------------------------------------------------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`               | 主键    | 通用字段，见文首                                                                                    | 编号    | 是   |     |             |
| `project_id`       | 项目    | 通用字段，见文首                                                                                    | 编号    |     | 否   | projects.id |
| `user_id`          | 用户    | 指向 `users`                                                                                  | 编号    |     | 否   | users.id    |
| `role`             | 角色    | 取值：`partner` 合伙人 / `manager` 经理 / `auditor` 审计员 / `qc` 质控 / `eqcr` EQCR 复核人 / `readonly` 只读 | 枚举    |     | 否   |             |
| `permission_level` | 权限级别  | 取值：`edit` 编辑 / `review` 复核中 / `readonly` 只读                                                 | 枚举    |     | 否   |             |
| `scope_cycles`     | 范围循环  | （据字段名）                                                                                      | 长文本   |     | 是   |             |
| `scope_accounts`   | 范围科目  | （据字段名）                                                                                      | 长文本   |     | 是   |             |
| `valid_from`       | 有效从   | （据字段名）                                                                                      | 日期    |     | 是   |             |
| `valid_to`         | 有效到   | （据字段名）                                                                                      | 日期    |     | 是   |             |
| `is_deleted`       | 是否已删除 | 通用字段，见文首                                                                                    | 是 / 否 |     | 否   |             |
| `deleted_at`       | 删除时间  | 通用字段，见文首                                                                                    | 时间    |     | 是   |             |
| `created_at`       | 创建时间  | 通用字段，见文首                                                                                    | 时间    |     | 否   |             |
| `updated_at`       | 更新时间  | 通用字段，见文首                                                                                    | 时间    |     | 否   |             |

### `temporary_grants` 临时授权

- **是什么**：临时给某人开的权限，有有效期。 注册。
- **后端**：`temporary_grant_models.py`、`collaboration.py`（只有 2 处引用）。
- **状态**：在用，但使用面很小，待核实。

**字段**（共 10 个，来源 `database-tables-columns.md`）：

| 字段               | 中文名  | 说明       | 类型        | 主键  | 可空  | 外键  |
| ---------------- | ---- | -------- | --------- | --- | --- | --- |
| `id`             | 主键   | 通用字段，见文首 | 编号        | 是   |     |     |
| `project_id`     | 项目   | 通用字段，见文首 | 编号        |     | 否   |     |
| `operation_code` | 操作编码 | （据字段名）   | 文本（≤64 字） |     | 否   |     |
| `grantee`        | 被授权人 | （据字段名）   | 编号        |     | 否   |     |
| `approver`       | 审批人  | （据字段名）   | 编号        |     | 否   |     |
| `reason`         | 原因   | （据字段名）   | 长文本       |     | 否   |     |
| `expires_at`     | 过期时间 | （据字段名）   | 时间        |     | 否   |     |
| `is_active`      | 是否启用 | （据字段名）   | 是 / 否     |     | 否   |     |
| `created_at`     | 创建时间 | 通用字段，见文首 | 时间        |     | 否   |     |
| `updated_at`     | 更新时间 | 通用字段，见文首 | 时间        |     | 否   |     |

### `project_creation_grants` 项目创建授权

- **是什么**：admin 授予 manager 对某个精确统一社会信用代码（USCC）建项的权限。只有 admin 能增删。被批量建项、项目向导、子公司挂接等多处调用。
- **后端**：`project_creation_grant_models.py`、`project_creation_grant_service`。
- **状态**：在用（新功能，2026-10 起）。

**字段**（共 15 个，来源 `database-tables-columns.md`）：

| 字段                | 中文名      | 说明                                                      | 类型        | 主键  | 可空  | 外键       |
| ----------------- | -------- | ------------------------------------------------------- | --------- | --- | --- | -------- |
| `id`              | 主键       | 通用字段，见文首                                                | 编号        | 是   |     |          |
| `grantee_user_id` | 被授权人用户编号 | 指向 `users`                                              | 编号        |     | 否   | users.id |
| `company_code`    | 公司代码     | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤18 字） |     | 否   |          |
| `valid_from`      | 有效从      | （据字段名）                                                  | 时间        |     | 否   |          |
| `valid_until`     | 有效截止     | （据字段名）                                                  | 时间        |     | 是   |          |
| `version`         | 版本号      | （据字段名）                                                  | 整数        |     | 否   |          |
| `source`          | 来源       | （据字段名）                                                  | 文本（≤48 字） |     | 否   |          |
| `reason`          | 原因       | （据字段名）                                                  | 长文本       |     | 否   |          |
| `granted_by`      | 授予人      | 指向 `users`                                              | 编号        |     | 是   | users.id |
| `revoked_by`      | 吊销人      | 指向 `users`                                              | 编号        |     | 是   | users.id |
| `revoked_at`      | 吊销时间     | （据字段名）                                                  | 时间        |     | 是   |          |
| `is_deleted`      | 是否已删除    | 通用字段，见文首                                                | 是 / 否     |     | 否   |          |
| `deleted_at`      | 删除时间     | 通用字段，见文首                                                | 时间        |     | 是   |          |
| `created_at`      | 创建时间     | 通用字段，见文首                                                | 时间        |     | 否   |          |
| `updated_at`      | 更新时间     | 通用字段，见文首                                                | 时间        |     | 否   |          |

### `user_display_preferences` 账号显示偏好

- **是什么**：每个用户一条，保存界面显示设置（一对一，user_id 为主键）。
- **后端**：`user_display_preferences.py`。
- **状态**：在用。

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                     | 中文名    | 说明                                      | 类型        | 主键  | 可空  | 外键       |
| ---------------------- | ------ | --------------------------------------- | --------- | --- | --- | -------- |
| `user_id`              | 用户     | 指向 `users`                              | 编号        | 是   |     | users.id |
| `amount_unit_override` | 金额单位覆盖 | 金额单位覆盖：null = 跟随项目                      | 文本（≤8 字）  |     | 是   |          |
| `font_size`            | 字体大小   | 显示字号：xs=11px, sm=12px, md=13px, lg=14px | 文本（≤4 字）  |     | 否   |          |
| `show_zero`            |        | 未查明                                     | 是 / 否     |     | 否   |          |
| `decimals`             |        | 小数位 0~6                                 | 整数        |     | 否   |          |
| `negative_red`         |        | 未查明                                     | 是 / 否     |     | 否   |          |
| `highlight_threshold`  |        | 变动高亮阈值 0~1，NUMERIC(5,4)                 | 数值（4 位小数） |     | 否   |          |
| `density`              |        | 表格密度                                    | 文本（≤16 字） |     | 否   |          |
| `grid_edit_mode`       |        | 表格编辑方式                                  | 文本（≤16 字） |     | 否   |          |
| `fixed_columns`        | 固定列    | （据字段名）                                  | JSON      |     | 否   |          |
| `revision`             | 修订号    | 乐观锁版本号                                  | 整数        |     | 否   |          |
| `updated_at`           | 更新时间   | 通用字段，见文首                                | 时间        |     | 是   |          |

### `service_identities` 系统作业主体

- **是什么**：给系统自动动作（迁移、OCR worker 等）用的"虚拟操作人"，不对应真实用户。
- **后端**：被 20 多张证据治理表通过外键引用（`actor_service_identity_id`），模型在 `evidence_governance_models.py`。
- **前端**：没有页面展示。
- **状态**：在用（后台使用，界面不可见）。

**字段**（共 7 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名  | 说明       | 类型         | 主键  | 可空  | 外键  |
| -------------- | ---- | -------- | ---------- | --- | --- | --- |
| `id`           | 主键   | 通用字段，见文首 | 编号         | 是   |     |     |
| `identity_key` | 身份键  | （据字段名）   | 文本（≤100 字） |     | 否   |     |
| `display_name` | 显示名称 | （据字段名）   | 文本（≤200 字） |     | 否   |     |
| `kind`         | 类别   | （据字段名）   | 文本（≤30 字）  |     | 否   |     |
| `description`  | 说明   | （据字段名）   | 长文本        |     | 是   |     |
| `is_active`    | 是否启用 | （据字段名）   | 是 / 否      |     | 否   |     |
| `created_at`   | 创建时间 | 通用字段，见文首 | 时间         |     | 否   |     |

## 二、项目与团队

### `projects` 项目

- **是什么**：一个审计项目（一家企业一个年度）。
- **用到的页面**：左侧项目列表 `MiddleProjectList.vue`、项目详情 `DetailProjectPanel.vue`、建项向导 `BasicInfoStep.vue`。
- **后端**：几乎所有业务模块都以 `project_id` 关联它。
- **状态**：在用，核心表。

**字段**（共 59 个，来源 `database-tables-columns.md`）：

| 字段                        | 中文名        | 说明                                                                                                                                                                   | 类型         | 主键  | 可空  | 外键                      |
| ------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --- | --- | ----------------------- |
| `id`                      | 主键         | 通用字段，见文首                                                                                                                                                             | 编号         | 是   |     |                         |
| `name`                    | 项目名称       | 如「陕西华氏医药有限公司_2026」                                                                                                                                                   | 文本（≤255 字） |     | 否   |                         |
| `client_name`             | 被审计单位名称    | （据字段名）                                                                                                                                                               | 文本（≤255 字） |     | 否   |                         |
| `audit_period_start`      | 审计期间起      | （据字段名）                                                                                                                                                               | 日期         |     | 是   |                         |
| `audit_period_end`        | 审计期间止      | 审计年度取它的年份；为空时很多功能提示「未设置审计年度」                                                                                                                                         | 日期         |     | 是   |                         |
| `project_type`            | 项目类型       | 取值：`annual` 年报审计 / `special` 专项审计 / `ipo` IPO / `internal_control` 内控审计 / `capital_verification` 验资 / `tax_audit` 税务审计 / `enterprise_income_tax_settlement` 企业所得税汇算  | 枚举         |     | 是   |                         |
| `materiality_level`       | 重要性水平（旧字段） | 重要性现在以 `materiality` 表为准                                                                                                                                             | 小数         |     | 是   |                         |
| `status`                  | 状态         | 取值：`created` 已创建 / `planning` 计划阶段 / `execution` 执行阶段 / `completion` 完成阶段 / `reporting` 报告阶段 / `archived` 已归档                                                        | 枚举         |     | 否   |                         |
| `manager_id`              | 经理编号       | 指向 `users`                                                                                                                                                           | 编号         |     | 是   | users.id                |
| `partner_id`              | 合伙人编号      | 指向 `users`                                                                                                                                                           | 编号         |     | 是   | users.id                |
| `version`                 | 版本号        | 每改一次加 1，防止两人同时改                                                                                                                                                      | 整数         |     | 否   |                         |
| `wizard_state`            | 建项向导数据     | 建项向导各步填写的内容                                                                                                                                                          | JSON       |     | 是   |                         |
| `accounting_standard_id`  | 会计准则编号     | 指向 `accounting_standards`                                                                                                                                            | 编号         |     | 是   | accounting_standards.id |
| `company_code`            | 公司代码       | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业                                                                                                              | 文本（≤50 字）  |     | 是   |                         |
| `short_name`              | 简称         | （据字段名）                                                                                                                                                               | 文本（≤100 字） |     | 是   |                         |
| `company_subtype`         | 企业子类型      | `type_a` / `type_b` / `type_c` / `type_d`，选审计报告模板用                                                                                                                   | 文本（≤10 字）  |     | 是   |                         |
| `business_category`       | 业务类别       | 质控业务分类码（A / A1~A8、B / B1~B6、C），NULL = 未填写；IPO / 再融资等是 scenario。；判定一律经 app.services.project_classification（不要按首字母 / 子串自行解释）。                                          | 文本（≤20 字）  |     | 是   |                         |
| `audit_type`              | 审计类型       | 选复核底稿模板（A21~A25）用                                                                                                                                                    | 文本（≤32 字）  |     | 是   |                         |
| `is_large_soe`            | 是否大型国企     | （据字段名）                                                                                                                                                               | 是 / 否      |     | 否   |                         |
| `audit_year`              | 审计年度       | 审计年度（物化列，唯一性索引依赖）                                                                                                                                                    | 整数         |     | 是   |                         |
| `template_type`           | 报表模板类型     | `soe` 国企版 / `listed` 上市版；决定用哪套报表和附注模板                                                                                                                                | 文本（≤20 字）  |     | 是   |                         |
| `report_scope`            | 报表范围       | `standalone` 单体 / `consolidated` 合并                                                                                                                                  | 文本（≤20 字）  |     | 是   |                         |
| `parent_company_name`     | 上级企业名称     | 合并企业树用                                                                                                                                                               | 文本（≤255 字） |     | 是   |                         |
| `parent_company_code`     | 上级企业代码     | 合并企业树用                                                                                                                                                               | 文本（≤50 字）  |     | 是   |                         |
| `ultimate_company_name`   | 最终控制方名称    | 合并企业树用                                                                                                                                                               | 文本（≤255 字） |     | 是   |                         |
| `ultimate_company_code`   | 最终控制方代码    | 合并企业树用                                                                                                                                                               | 文本（≤50 字）  |     | 是   |                         |
| `relation_to_parent`      | 与上级关系      | `subsidiary` 子公司（独立法人，合并时抵销）/ `branch` 分公司（并入母公司汇总）/ 空 = 未填                                                                                                          | 文本（≤20 字）  |     | 是   |                         |
| `parent_project_id`       | 上级合并项目     | 系统按企业三码自动算出，不要手工改；指向 `projects`                                                                                                                                      | 编号         |     | 是   | projects.id             |
| `consol_level`            | 合并层级       | （据字段名）                                                                                                                                                               | 整数         |     | 否   |                         |
| `consolidation_type`      | 合并方式（旧字段）  | 已不再使用                                                                                                                                                                | 文本（≤20 字）  |     | 是   |                         |
| `consol_lock`             | 合并锁定       | 锁定后合并相关数据不能改                                                                                                                                                         | 是 / 否      |     | 否   |                         |
| `consol_lock_by`          | 合并锁定人      | （据字段名）                                                                                                                                                               | 编号         |     | 是   | users.id                |
| `consol_lock_at`          | 合并锁定时间     | （据字段名）                                                                                                                                                               | 时间         |     | 是   |                         |
| `archived_at`             | 归档时间       | （据字段名）                                                                                                                                                               | 时间         |     | 是   |                         |
| `retention_until`         | 档案保留截止     | 归档后保留 10 年                                                                                                                                                           | 时间         |     | 是   |                         |
| `budget_hours`            | 预算工时       | （据字段名）                                                                                                                                                               | 整数         |     | 是   |                         |
| `contract_amount`         | 合同金额       | （据字段名）                                                                                                                                                               | 金额（2 位小数）  |     | 是   |                         |
| `budgeted_by`             | 预算设定人      | （据字段名）                                                                                                                                                               | 编号         |     | 是   | users.id                |
| `budgeted_at`             | 预算设定时间     | （据字段名）                                                                                                                                                               | 时间         |     | 是   |                         |
| `risk_level`              | 风险等级       | `high` 高 / `medium` 中 / `low` 低                                                                                                                                      | 文本（≤10 字）  |     | 是   |                         |
| `risk_level_updated_at`   | 风险级别更新时间   | （据字段名）                                                                                                                                                               | 时间         |     | 是   |                         |
| `scenario`                | 场景         | （据字段名）                                                                                                                                                               | 文本（≤20 字）  |     | 否   |                         |
| `has_foreign_currency`    | 是否有外币业务    | （据字段名）                                                                                                                                                               | 是 / 否      |     | 否   |                         |
| `prior_year_project_id`   | 上年项目       | 上年同一单位的项目，取上年数用                                                                                                                                                      | 编号         |     | 是   |                         |
| `migration_note`          | 迁移备注       | （据字段名）                                                                                                                                                               | 长文本        |     | 是   |                         |
| `applicable_standard_v2`  | 适用准则第二版    | 结构化统一准则状态源（单一真理源）；{entity_type: "soe"\|"listed"\|"private", scope: "standalone"\|"consolidated"；stage: "normal"\|"ipo"\|"transfer"\|"restructure"\|"fraud_response"} | JSON       |     | 是   |                         |
| `review_config`           | 复核配置       | 复核链配置: {"levels":2\|3\|4,"level_roles":{"L1":"manager","L2":"partner",...}}                                                                                          | JSON       |     | 是   |                         |
| `budget_config`           | 预算配置       | 工时预算配置: {"by_cycle":{"D":100,"E":80,...},"by_user":{"user_id":160,...},"total":800}                                                                                  | JSON       |     | 是   |                         |
| `amount_unit`             | 金额单位       | （据字段名）                                                                                                                                                               | 文本（≤8 字）   |     | 否   |                         |
| `current_audit_phase`     | 当前审计阶段     | （据字段名）                                                                                                                                                               | 文本（≤16 字）  |     | 否   |                         |
| `interim_cutoff_date`     | 预审截止日期     | 预审截止日                                                                                                                                                                | 日期         |     | 是   |                         |
| `acnr_registry_version`   | 地址库注册表版本   | 锁定的 ACNR 地址目录版本号（14 位 UTC 时间戳）；NULL = 未锁定，按当前目录解析                                                                                                                    | 文本（≤14 字）  |     | 是   |                         |
| `acnr_registry_locked_at` | 地址库注册表锁定时间 | ACNR 目录版本锁定时间；与 acnr_registry_version 同写同清                                                                                                                           | 时间         |     | 是   |                         |
| `is_deleted`              | 是否已删除      | 通用字段，见文首                                                                                                                                                             | 是 / 否      |     | 否   |                         |
| `deleted_at`              | 删除时间       | 通用字段，见文首                                                                                                                                                             | 时间         |     | 是   |                         |
| `created_at`              | 创建时间       | 通用字段，见文首                                                                                                                                                             | 时间         |     | 否   |                         |
| `updated_at`              | 更新时间       | 通用字段，见文首                                                                                                                                                             | 时间         |     | 否   |                         |
| `created_by`              | 创建人        | 通用字段，见文首                                                                                                                                                             | 编号         |     | 是   | users.id                |
| `updated_by`              | 修改人        | 通用字段，见文首                                                                                                                                                             | 编号         |     | 是   | users.id                |

### `project_assignments` 项目团队分配

- **是什么**：人员在项目中的分工（合伙人、经理、审计员等）。
- **用到的页面**：建项向导的团队步骤 `TeamAssignmentStep.vue`。
- **后端**：`assignments.py`、`staff_models.py`。
- **状态**：在用。

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段                | 中文名   | 说明                 | 类型        | 主键  | 可空  | 外键               |
| ----------------- | ----- | ------------------ | --------- | --- | --- | ---------------- |
| `id`              | 主键    | 通用字段，见文首           | 编号        | 是   |     |                  |
| `project_id`      | 项目    | 通用字段，见文首           | 编号        |     | 否   | projects.id      |
| `staff_id`        | 人员    | 指向 `staff_members` | 编号        |     | 否   | staff_members.id |
| `role`            | 角色    | （据字段名）             | 文本（≤30 字） |     | 否   |                  |
| `assigned_cycles` | 分配循环  | （据字段名）             | JSON      |     | 是   |                  |
| `assigned_at`     | 分配时间  | （据字段名）             | 时间        |     | 是   |                  |
| `assigned_by`     | 分配人   | 指向 `users`         | 编号        |     | 是   | users.id         |
| `is_deleted`      | 是否已删除 | 通用字段，见文首           | 是 / 否     |     | 否   |                  |
| `deleted_at`      | 删除时间  | 通用字段，见文首           | 时间        |     | 是   |                  |
| `created_at`      | 创建时间  | 通用字段，见文首           | 时间        |     | 否   |                  |
| `updated_at`      | 更新时间  | 通用字段，见文首           | 时间        |     | 否   |                  |

### `staff_members` 人员档案

- **是什么**：员工档案，可绑定登录账号。
- **用到的页面**：程序裁剪页 `ProcedureTrimming.vue`（选择编制人）。
- **后端**：`staff_models.py`、`account_package_models.py`。
- **状态**：在用。

**字段**（共 26 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名     | 说明                                          | 类型         | 主键  | 可空  | 外键               |
| --------------------- | ------- | ------------------------------------------- | ---------- | --- | --- | ---------------- |
| `id`                  | 主键      | 通用字段，见文首                                    | 编号         | 是   |     |                  |
| `user_id`             | 用户      | 指向 `users`                                  | 编号         |     | 是   | users.id         |
| `name`                | 名称      | （据字段名）                                      | 文本（≤100 字） |     | 否   |                  |
| `employee_no`         | 员工编号    | （据字段名）                                      | 文本（≤50 字）  |     | 是   |                  |
| `department`          | 部门      | （据字段名）                                      | 文本（≤100 字） |     | 是   |                  |
| `title`               | 标题      | （据字段名）                                      | 文本（≤50 字）  |     | 是   |                  |
| `partner_name`        | 合伙人名称   | （据字段名）                                      | 文本（≤100 字） |     | 是   |                  |
| `partner_id`          | 合伙人编号   | 指向 `staff_members`                          | 编号         |     | 是   | staff_members.id |
| `specialty`           |         | 未查明                                         | 文本（≤200 字） |     | 是   |                  |
| `phone`               | 电话      | （据字段名）                                      | 文本（≤30 字）  |     | 是   |                  |
| `email`               | 邮箱      | （据字段名）                                      | 文本（≤200 字） |     | 是   |                  |
| `join_date`           |         | 未查明                                         | 日期         |     | 是   |                  |
| `resume_data`         |         | 未查明                                         | JSON       |     | 是   |                  |
| `source`              | 来源      | `seed` 系统预置 / `custom` 自定义                  | 文本（≤20 字）  |     | 否   |                  |
| `role_level`          | 角色级别    | 费率等级: partner/manager/senior/auditor/intern | 文本（≤20 字）  |     | 是   |                  |
| `is_cpa`              | 是否注册会计师 | 是否注册会计师                                     | 是 / 否      |     | 是   |                  |
| `cpa_cert_no`         |         | CPA执业证书号                                    | 文本（≤50 字）  |     | 是   |                  |
| `audit_years`         | 审计年数    | 审计年限                                        | 整数         |     | 是   |                  |
| `qualifications`      |         | 专业资质列表 [CPA,CIA,CISA...]                    | JSON       |     | 是   |                  |
| `industry_experience` |         | 行业经验列表 [制造,金融,地产...]                        | JSON       |     | 是   |                  |
| `status`              | 状态      | 人员状态: active/on_leave/resigned              | 文本（≤20 字）  |     | 否   |                  |
| `avatar_url`          |         | 头像图片URL                                     | 文本（≤500 字） |     | 是   |                  |
| `is_deleted`          | 是否已删除   | 通用字段，见文首                                    | 是 / 否      |     | 否   |                  |
| `deleted_at`          | 删除时间    | 通用字段，见文首                                    | 时间         |     | 是   |                  |
| `created_at`          | 创建时间    | 通用字段，见文首                                    | 时间         |     | 否   |                  |
| `updated_at`          | 更新时间    | 通用字段，见文首                                    | 时间         |     | 否   |                  |

## 三、科目数据导入（四表）

### `account_chart` 科目表（标准科目 + 客户科目）

- **是什么**：科目主数据。
- **用到的页面**：账套导入向导 `AccountImportStep.vue`、列映射 `ManualColumnMapper.vue`。
- **后端**：`audit_platform_models.py`、`dataset_models.py`、`account_chart.py`。
- **状态**：在用。

**字段**（共 14 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名   | 说明                                                                         | 类型    | 主键  | 可空  | 外键          |
| -------------- | ----- | -------------------------------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`           | 主键    | 通用字段，见文首                                                                   | 编号    | 是   |     |             |
| `project_id`   | 项目    | 通用字段，见文首                                                                   | 编号    |     | 否   | projects.id |
| `account_code` | 科目编码  | （据字段名）                                                                     | 文本    |     | 否   |             |
| `account_name` | 科目名称  | （据字段名）                                                                     | 文本    |     | 否   |             |
| `direction`    | 方向    | 取值：`debit` 借 / `credit` 贷                                                  | 枚举    |     | 否   |             |
| `level`        | 级次    | （据字段名）                                                                     | 整数    |     | 否   |             |
| `category`     | 类别    | 取值：`asset` 资产 / `liability` 负债 / `equity` 权益 / `revenue` 收入 / `expense` 费用 | 枚举    |     | 否   |             |
| `parent_code`  | 上级编码  | （据字段名）                                                                     | 文本    |     | 是   |             |
| `source`       | 来源    | 取值：`standard` 标准科目 / `client` 客户科目                                         | 枚举    |     | 否   |             |
| `dataset_id`   | 账套版本  | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）                                      | 编号    |     | 是   |             |
| `is_deleted`   | 是否已删除 | 通用字段，见文首                                                                   | 是 / 否 |     | 否   |             |
| `deleted_at`   | 删除时间  | 通用字段，见文首                                                                   | 时间    |     | 是   |             |
| `created_at`   | 创建时间  | 通用字段，见文首                                                                   | 时间    |     | 否   |             |
| `updated_at`   | 更新时间  | 通用字段，见文首                                                                   | 时间    |     | 否   |             |

### `account_mapping` 科目映射关系

- **是什么**：客户科目映射到标准科目，是试算表取数的依据。
- **用到的页面**：`AccountMappingStep.vue`（导入向导）、试算表页 `TrialBalance.vue`。
- **后端**：`audit_platform_models.py`、`audit_platform_schemas.py`。
- **状态**：在用。

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段                      | 中文名    | 说明                                                                      | 类型    | 主键  | 可空  | 外键          |
| ----------------------- | ------ | ----------------------------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`                    | 主键     | 通用字段，见文首                                                                | 编号    | 是   |     |             |
| `project_id`            | 项目     | 通用字段，见文首                                                                | 编号    |     | 否   | projects.id |
| `original_account_code` | 客户科目编码 | 余额表里的编码；如 `1122.01`                                                     | 文本    |     | 否   |             |
| `original_account_name` | 客户科目名称 | （据字段名）                                                                  | 文本    |     | 是   |             |
| `standard_account_code` | 标准科目编码 | 映射到的标准科目；如 `1122`                                                       | 文本    |     | 否   |             |
| `mapping_type`          | 映射方式   | 怎么建立的这条映射；`auto_exact` 自动精确（相似度 ≥0.92）/ `auto_fuzzy` 自动模糊 / `manual` 人工 | 枚举    |     | 否   |             |
| `is_deleted`            | 是否已删除  | 通用字段，见文首                                                                | 是 / 否 |     | 否   |             |
| `deleted_at`            | 删除时间   | 通用字段，见文首                                                                | 时间    |     | 是   |             |
| `created_by`            | 创建人    | 通用字段，见文首                                                                | 编号    |     | 是   | users.id    |
| `created_at`            | 创建时间   | 通用字段，见文首                                                                | 时间    |     | 否   |             |
| `updated_at`            | 更新时间   | 通用字段，见文首                                                                | 时间    |     | 否   |             |

### `tb_balance` 科目余额表原始数据

- **是什么**：导入的科目余额表（借方/贷方/期初/期末等）。
- **用到的页面**：试算表 `TrialBalance.vue`、导入历史 `LedgerImportHistory.vue`、凭证穿透 `LedgerPenetration.vue`。
- **后端**：`audit_platform_models.py`、`dataset_models.py`、`config.py`。
- **状态**：在用，核心表。

**字段**（共 32 个，来源 `database-tables-columns.md`）：

| 字段                         | 中文名      | 说明                                                                                                                                                                                                   | 类型        | 主键  | 可空  | 外键                |
| -------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | --- | --- | ----------------- |
| `id`                       | 主键       | 通用字段，见文首                                                                                                                                                                                             | 编号        | 是   |     |                   |
| `tenant_id`                | 租户（预留）   | 通用字段，见文首                                                                                                                                                                                             | 文本（≤64 字） |     | 否   |                   |
| `project_id`               | 项目       | 通用字段，见文首                                                                                                                                                                                             | 编号        |     | 否   | projects.id       |
| `year`                     | 年度       | 通用字段，见文首                                                                                                                                                                                             | 整数        |     | 否   |                   |
| `company_code`             | 公司代码     | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业                                                                                                                                              | 文本        |     | 否   |                   |
| `account_code`             | 科目编码     | 客户原始编码，如 `1122.01`；文件「科目编码」列                                                                                                                                                                         | 文本        |     | 否   |                   |
| `account_name`             | 科目名称     | 如「应收账款_应收货款」；文件「科目名称」列                                                                                                                                                                               | 文本        |     | 是   |                   |
| `level`                    | 科目级次     | 第几级科目；按编码长度推：去掉分隔符后 ≤4 位为 1 级，≤6 位 2 级，≤8 位 3 级，≤10 位 4 级，更长 5 级                                                                                                                                     | 整数        |     | 是   |                   |
| `opening_balance`          | 期初余额     | 按「正常方向为正」存；优先取文件的年初借/贷，其次期初借/贷，其次单列期初余额                                                                                                                                                              | 金额（2 位小数） |     | 是   |                   |
| `opening_debit`            | 期初借方     | 文件里分列给出时的原值；原样                                                                                                                                                                                       | 金额（2 位小数） |     | 是   |                   |
| `opening_credit`           | 期初贷方     | 文件里分列给出时的原值；原样                                                                                                                                                                                       | 金额（2 位小数） |     | 是   |                   |
| `opening_qty`              | 期初数量     | 数量核算的科目才有                                                                                                                                                                                            | 数值（4 位小数） |     | 是   |                   |
| `opening_fc`               | 期初外币金额   | 外币核算的科目才有                                                                                                                                                                                            | 金额（2 位小数） |     | 是   |                   |
| `debit_amount`             | 本期借方发生额  | 优先取文件「本年累计」，没有才取「本期发生额」；原样，不改正负                                                                                                                                                                      | 金额（2 位小数） |     | 是   |                   |
| `credit_amount`            | 本期贷方发生额  | 优先取文件「本年累计」，没有才取「本期发生额」；原样，不改正负                                                                                                                                                                      | 金额（2 位小数） |     | 是   |                   |
| `closing_balance`          | 期末余额     | 按「正常方向为正」存；由期末借/贷或单列期末余额 + 方向列算出                                                                                                                                                                     | 金额（2 位小数） |     | 是   |                   |
| `closing_debit`            | 期末借方     | 文件分列给出时的原值；原样                                                                                                                                                                                        | 金额（2 位小数） |     | 是   |                   |
| `closing_credit`           | 期末贷方     | 文件分列给出时的原值；原样                                                                                                                                                                                        | 金额（2 位小数） |     | 是   |                   |
| `currency_code`            | 币种       | 文件没有就填 `CNY`                                                                                                                                                                                         | 文本（≤3 字）  |     | 否   |                   |
| `raw_extra`                | 原文件未映射列  | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}`                                                                                                                                                   | JSON      |     | 是   |                   |
| `import_batch_id`          | 导入批次     | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches`                                                                                                                                                           | 编号        |     | 是   | import_batches.id |
| `dataset_id`               | 账套版本     | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）                                                                                                                                                                | 编号        |     | 是   |                   |
| `opening_direction`        | 期初余额方向   | 余额实际在借方还是贷方；`debit` 借 / `credit` 贷                                                                                                                                                                   | 文本（≤10 字） |     | 是   |                   |
| `opening_direction_source` | 方向怎么判出来的 | `split_columns` 文件借贷分列、看哪边有数 / `explicit_direction` 文件有「方向」列 / `contra_account` 按备抵科目名称（累计折旧、坏账准备等）判 / `account_category_inferred` 按科目类别判 / `account_category_inferred_low_confidence` 科目名称为空、只能按编码判 | 文本（≤50 字） |     | 是   |                   |
| `closing_direction`        | 期末余额方向   | 余额实际在借方还是贷方；`debit` 借 / `credit` 贷                                                                                                                                                                   | 文本（≤10 字） |     | 是   |                   |
| `closing_direction_source` | 方向怎么判出来的 | `split_columns` 文件借贷分列、看哪边有数 / `explicit_direction` 文件有「方向」列 / `contra_account` 按备抵科目名称（累计折旧、坏账准备等）判 / `account_category_inferred` 按科目类别判 / `account_category_inferred_low_confidence` 科目名称为空、只能按编码判 | 文本（≤50 字） |     | 是   |                   |
| `sign_convention_version`  | 符号口径版本   | 现在导入的都是 `v2_category_natural_positive`（正常方向为正）；为空的是老数据，存的是借正贷负                                                                                                                                       | 文本（≤30 字） |     | 是   |                   |
| `sign_anomaly_flags`       | 方向异常标记   | 余额方向和科目正常方向相反时记下来，例如负债出现借方余额；例：`{"normal_direction": "credit", "conflicts": [{"period": "closing", "actual_direction": "debit", "stored_amount": -100}]}`；正常时为空                                      | JSON      |     | 是   |                   |
| `is_deleted`               | 是否已删除    | 通用字段，见文首                                                                                                                                                                                             | 是 / 否     |     | 否   |                   |
| `deleted_at`               | 删除时间     | 通用字段，见文首                                                                                                                                                                                             | 时间        |     | 是   |                   |
| `created_at`               | 创建时间     | 通用字段，见文首                                                                                                                                                                                             | 时间        |     | 否   |                   |
| `updated_at`               | 更新时间     | 通用字段，见文首                                                                                                                                                                                             | 时间        |     | 否   |                   |

### `tb_ledger` 序时账（凭证明细）

- **是什么**：导入的序时账逐行凭证。
- **用到的页面**：`LedgerImportHistory.vue`、`LedgerPenetration.vue`（序时账穿透）、`DataImportPanel.vue`。
- **后端**：`audit_platform_models.py`、`dataset_models.py`。
- **状态**：在用，核心表。

**字段**（共 31 个，来源 `database-tables-columns.md`）：

| 字段                       | 中文名      | 说明                                                          | 类型        | 主键  | 可空  | 外键                |
| ------------------------ | -------- | ----------------------------------------------------------- | --------- | --- | --- | ----------------- |
| `id`                     | 主键       | 通用字段，见文首                                                    | 编号        | 是   |     |                   |
| `tenant_id`              | 租户（预留）   | 通用字段，见文首                                                    | 文本（≤64 字） |     | 否   |                   |
| `project_id`             | 项目       | 通用字段，见文首                                                    | 编号        |     | 否   | projects.id       |
| `year`                   | 年度       | 通用字段，见文首                                                    | 整数        | 是   |     |                   |
| `company_code`           | 公司代码     | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业     | 文本        |     | 否   |                   |
| `voucher_date`           | 凭证日期     | 文件「记账日期 / 凭证日期」等列；为空的行不导入                                   | 日期        |     | 否   |                   |
| `voucher_no`             | 凭证号      | 为空的行不导入                                                     | 文本        |     | 否   |                   |
| `account_code`           | 科目编码     | 客户原始科目                                                      | 文本        |     | 否   |                   |
| `account_name`           | 科目名称     | 客户原始科目                                                      | 文本        |     | 是   |                   |
| `accounting_period`      | 会计期间（月份） | 1~12；文件「期间」列；没有就取凭证日期的月份                                    | 整数        |     | 是   |                   |
| `voucher_type`           | 凭证字      | 记 / 收 / 付 / 转 等；原样                                          | 文本（≤20 字） |     | 是   |                   |
| `entry_seq`              | 分录序号     | 凭证内第几行；原样                                                   | 整数        |     | 是   |                   |
| `debit_amount`           | 借方金额     | **该条分录**的金额；原样。注意不能映射成「借方合计 / 贷方合计」（那是整张凭证的合计），否则每行都会变成凭证总额 | 金额（2 位小数） |     | 是   |                   |
| `credit_amount`          | 贷方金额     | **该条分录**的金额；原样。注意不能映射成「借方合计 / 贷方合计」（那是整张凭证的合计），否则每行都会变成凭证总额 | 金额（2 位小数） |     | 是   |                   |
| `debit_qty`              | 借方数量     | 数量核算才有                                                      | 数值（4 位小数） |     | 是   |                   |
| `credit_qty`             | 贷方数量     | 数量核算才有                                                      | 数值（4 位小数） |     | 是   |                   |
| `debit_fc`               | 借方外币金额   | 外币核算才有                                                      | 金额（2 位小数） |     | 是   |                   |
| `credit_fc`              | 贷方外币金额   | 外币核算才有                                                      | 金额（2 位小数） |     | 是   |                   |
| `counterpart_account`    | 对方科目     | 原样                                                          | 文本        |     | 是   |                   |
| `summary`                | 摘要       | 原样                                                          | 长文本       |     | 是   |                   |
| `preparer`               | 制单人      | 原样                                                          | 文本        |     | 是   |                   |
| `currency_code`          | 币种编码     | （据字段名）                                                      | 文本（≤3 字）  |     | 否   |                   |
| `raw_extra`              | 原文件未映射列  | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}`          | JSON      |     | 是   |                   |
| `import_batch_id`        | 导入批次     | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches`                  | 编号        |     | 是   | import_batches.id |
| `dataset_id`             | 账套版本     | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）                       | 编号        |     | 是   |                   |
| `entry_direction`        | 分录方向     | 这条分录记在借方还是贷方；`debit` / `credit`；文件有方向列用方向列，否则看借贷哪边有数        | 文本（≤10 字） |     | 是   |                   |
| `entry_direction_source` | 方向怎么判出来的 | 同余额表                                                        | 文本（≤50 字） |     | 是   |                   |
| `is_deleted`             | 是否已删除    | 通用字段，见文首                                                    | 是 / 否     |     | 否   |                   |
| `deleted_at`             | 删除时间     | 通用字段，见文首                                                    | 时间        |     | 是   |                   |
| `created_at`             | 创建时间     | 通用字段，见文首                                                    | 时间        |     | 否   |                   |
| `updated_at`             | 更新时间     | 通用字段，见文首                                                    | 时间        |     | 否   |                   |

### `tb_aux_balance` 辅助核算余额

- **是什么**：按辅助核算维度（客户、供应商等）的余额。
- **用到的页面**：`AuxSummaryPanel.vue`、`LedgerPenetration.vue`、`DataImportPanel.vue`。
- **状态**：在用。

**字段**（共 38 个，来源 `database-tables-columns.md`）：

| 字段                         | 中文名     | 说明                                                       | 类型        | 主键  | 可空  | 外键                |
| -------------------------- | ------- | -------------------------------------------------------- | --------- | --- | --- | ----------------- |
| `id`                       | 主键      | 通用字段，见文首                                                 | 编号        | 是   |     |                   |
| `tenant_id`                | 租户（预留）  | 通用字段，见文首                                                 | 文本（≤64 字） |     | 否   |                   |
| `project_id`               | 项目      | 通用字段，见文首                                                 | 编号        |     | 否   | projects.id       |
| `year`                     | 年度      | 通用字段，见文首                                                 | 整数        |     | 否   |                   |
| `company_code`             | 公司代码    | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业  | 文本        |     | 否   |                   |
| `account_code`             | 科目编码    | （据字段名）                                                   | 文本        |     | 否   |                   |
| `account_name`             | 科目名称    | （据字段名）                                                   | 文本        |     | 是   |                   |
| `level`                    | 级次      | （据字段名）                                                   | 整数        |     | 是   |                   |
| `aux_type`                 | 维度类型    | 按什么核算；客户 / 供应商 / 部门 / 银行账户                               | 文本        |     | 否   |                   |
| `aux_type_name`            | 维度类型名称  | 文件里的原始叫法                                                 | 文本        |     | 是   |                   |
| `aux_code`                 | 维度编码    | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院                           | 文本        |     | 是   |                   |
| `aux_name`                 | 维度名称    | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院                           | 文本        |     | 是   |                   |
| `aux_dimensions_raw`       | 原始维度串   | 文件里的原文，一行有多个维度时会拆成多行，每行都带这个原文；`客户:C001 鞍钢总医院;部门:D01 销售部` | 长文本       |     | 是   |                   |
| `opening_balance`          | 期初余额    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `opening_debit`            | 期初借方    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `opening_credit`           | 期初贷方    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `opening_qty`              | 期初数量    | （据字段名）                                                   | 数值（4 位小数） |     | 是   |                   |
| `opening_fc`               | 期初外币    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `debit_amount`             | 借方金额    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `credit_amount`            | 贷方金额    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `closing_balance`          | 期末余额    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `closing_debit`            | 期末借方    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `closing_credit`           | 期末贷方    | （据字段名）                                                   | 金额（2 位小数） |     | 是   |                   |
| `currency_code`            | 币种编码    | （据字段名）                                                   | 文本（≤3 字）  |     | 否   |                   |
| `raw_extra`                | 原文件未映射列 | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}`       | JSON      |     | 是   |                   |
| `import_batch_id`          | 导入批次    | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches`               | 编号        |     | 是   | import_batches.id |
| `dataset_id`               | 账套版本    | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）                    | 编号        |     | 是   |                   |
| `opening_direction`        | 期初方向    | 符号约定方向字段                                                 | 文本（≤10 字） |     | 是   |                   |
| `opening_direction_source` | 期初方向来源  | （据字段名）                                                   | 文本（≤50 字） |     | 是   |                   |
| `closing_direction`        | 期末方向    | （据字段名）                                                   | 文本（≤10 字） |     | 是   |                   |
| `closing_direction_source` | 期末方向来源  | （据字段名）                                                   | 文本（≤50 字） |     | 是   |                   |
| `sign_convention_version`  | 符号约定版本  | （据字段名）                                                   | 文本（≤30 字） |     | 是   |                   |
| `sign_anomaly_flags`       | 符号异常标记  | （据字段名）                                                   | JSON      |     | 是   |                   |
| `is_deleted`               | 是否已删除   | 通用字段，见文首                                                 | 是 / 否     |     | 否   |                   |
| `deleted_at`               | 删除时间    | 通用字段，见文首                                                 | 时间        |     | 是   |                   |
| `accounting_period`        | 会计期间    | （据字段名）                                                   | 整数        |     | 是   |                   |
| `created_at`               | 创建时间    | 通用字段，见文首                                                 | 时间        |     | 否   |                   |
| `updated_at`               | 更新时间    | 通用字段，见文首                                                 | 时间        |     | 否   |                   |

### `trial_balance` 试算表（审定数汇总）

- **是什么**：每个科目的未审数、调整数、审定数，报表取数的权威来源。
- **用到的页面**：`TrialBalance.vue`（试算表页）、`LinkagePanoramaView.vue`（联动全景）、`WorkflowDashboard.vue`。
- **后端**：`audit_platform_models.py`、`workpaper_models.py`。
- **状态**：在用，核心表。

**字段**（共 20 个，来源 `database-tables-columns.md`）：

| 字段                      | 中文名    | 说明                                                                      | 类型        | 主键  | 可空  | 外键          |
| ----------------------- | ------ | ----------------------------------------------------------------------- | --------- | --- | --- | ----------- |
| `id`                    | 主键     | 通用字段，见文首                                                                | 编号        | 是   |     |             |
| `project_id`            | 项目     | 通用字段，见文首                                                                | 编号        |     | 否   | projects.id |
| `year`                  | 年度     | 通用字段，见文首                                                                | 整数        |     | 否   |             |
| `company_code`          | 公司代码   | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业                 | 文本        |     | 否   |             |
| `standard_account_code` | 标准科目编码 | 科目映射                                                                    | 文本        |     | 否   |             |
| `account_name`          | 科目名称   | 余额表同编码名称，没有再取标准科目表                                                      | 文本        |     | 是   |             |
| `account_category`      | 科目类别   | `asset` 资产 / `liability` 负债 / `equity` 权益 / `revenue` 收入 / `expense` 费用 | 枚举        |     | 否   |             |
| `unadjusted_amount`     | 未审数    | 客户账面数；余额表最明细科目按映射汇总；损益类取本期发生额（收入取贷方、费用取借方），不取期末                         | 金额（2 位小数） |     | 是   |             |
| `rje_adjustment`        | 重分类调整  | 已审批的重分类分录净额；同上                                                          | 金额（2 位小数） |     | 否   |             |
| `aje_adjustment`        | 审计调整   | 已审批的审计调整分录净额；调整分录汇总，按科目方向换算后的增减额                                        | 金额（2 位小数） |     | 否   |             |
| `audited_amount`        | 审定数    | **未审数 + 审计调整 + 重分类调整 + 底稿调整**                                           | 金额（2 位小数） |     | 是   |             |
| `wp_adjustment`         | 底稿调整   | 从审定表「发布到试算表」带来的差额；只有在底稿里点发布并确认才写入；重导账表、重算调整时保留不清零                       | 金额（2 位小数） |     | 否   |             |
| `wp_publish_base`       | 发布基数   | 发布那一刻的基数，用来算底稿调整差额；精确含义未查明                                              | 金额（2 位小数） |     | 是   |             |
| `wp_published_at`       | 最近发布时间 | 底稿最后一次发布到试算表的时间                                                         | 时间        |     | 是   |             |
| `opening_balance`       | 期初数    | 同上汇总；损益类为 0                                                             | 金额（2 位小数） |     | 是   |             |
| `currency_code`         | 币种     | 默认 `CNY`                                                                | 文本（≤3 字）  |     | 否   |             |
| `is_deleted`            | 是否已删除  | 通用字段，见文首                                                                | 是 / 否     |     | 否   |             |
| `deleted_at`            | 删除时间   | 通用字段，见文首                                                                | 时间        |     | 是   |             |
| `created_at`            | 创建时间   | 通用字段，见文首                                                                | 时间        |     | 否   |             |
| `updated_at`            | 更新时间   | 通用字段，见文首                                                                | 时间        |     | 否   |             |

### `ledger_datasets` 账套数据集版本

- **是什么**：一次导入的数据版本（staged → active → superseded），查询只看 active 版本。
- **后端**：`dataset_models.py`、`audit_platform_models.py`。
- **前端**：未发现表名字面量，版本切换通过接口。
- **状态**：在用。

**字段**（共 15 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名    | 说明                                                                                                    | 类型        | 主键  | 可空  | 外键                 |
| --------------------- | ------ | ----------------------------------------------------------------------------------------------------- | --------- | --- | --- | ------------------ |
| `id`                  | 主键     | 通用字段，见文首                                                                                              | 编号        | 是   |     |                    |
| `tenant_id`           | 租户（预留） | 通用字段，见文首                                                                                              | 文本（≤64 字） |     | 否   |                    |
| `project_id`          | 项目     | 通用字段，见文首                                                                                              | 编号        |     | 否   | projects.id        |
| `year`                | 年度     | 通用字段，见文首                                                                                              | 整数        |     | 否   |                    |
| `status`              | 版本状态   | 这个版本现在是否在用；`staged` 已写入未生效 / `active` 当前生效 / `superseded` 已被新版本替代 / `failed` 导入失败 / `rolled_back` 已回滚 | 枚举        |     | 否   |                    |
| `source_type`         | 来源     | 这个版本怎么来的；`import` 导入（默认）/ `migration` 迁移 / `rollback` 回滚                                              | 文本（≤50 字） |     | 否   |                    |
| `source_summary`      | 来源说明   | 导入了哪些文件、金额单位、追加导入时继承了哪几个月；JSON                                                                        | JSON      |     | 是   |                    |
| `record_summary`      | 行数统计   | 四张账表各写了多少行；例：`{"tb_balance": 435, "tb_ledger": 1681993, ...}`                                         | JSON      |     | 是   |                    |
| `validation_summary`  | 校验结果   | 导入校验发现几个问题、几个是拦截的；JSON                                                                                | JSON      |     | 是   |                    |
| `job_id`              | 导入任务   | 是哪一次导入任务产生的；指向导入任务表                                                                                   | 编号        |     | 是   | import_jobs.id     |
| `previous_dataset_id` | 上一版本   | 追加导入时基于哪个旧版本；指向本表                                                                                     | 编号        |     | 是   | ledger_datasets.id |
| `created_by`          | 创建人    | 通用字段，见文首                                                                                              | 编号        |     | 是   | users.id           |
| `created_at`          | 创建时间   | 通用字段，见文首                                                                                              | 时间        |     | 否   |                    |
| `activated_by`        | 生效人    | 谁、什么时候让它生效的                                                                                           | 编号        |     | 是   | users.id           |
| `activated_at`        | 生效时间   | 谁、什么时候让它生效的                                                                                           | 时间        |     | 是   |                    |

### `activation_records` 数据集激活/回滚记录

- **是什么**：记录数据版本的激活和回滚操作。
- **后端**：`dataset_models.py`。
- **状态**：在用。

**字段**（共 13 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名      | 说明                                                                                                                      | 类型        | 主键  | 可空  | 外键                 |
| --------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------- | --------- | --- | --- | ------------------ |
| `id`                  | 主键       | 通用字段，见文首                                                                                                                | 编号        | 是   |     |                    |
| `project_id`          | 项目       | 通用字段，见文首                                                                                                                | 编号        |     | 否   | projects.id        |
| `year`                | 年度       | 通用字段，见文首                                                                                                                | 整数        |     | 否   |                    |
| `dataset_id`          | 账套版本     | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）；指向 `ledger_datasets`                                                              | 编号        |     | 否   | ledger_datasets.id |
| `action`              | 动作       | 取值：`activate` 生效 / `rollback` 回滚 / `force_unbind` 强制解绑                                                                  | 枚举        |     | 否   |                    |
| `previous_dataset_id` | 上一账套版本编号 | 指向 `ledger_datasets`                                                                                                    | 编号        |     | 是   | ledger_datasets.id |
| `performed_by`        | 执行人      | 操作者与时间；指向 `users`                                                                                                       | 编号        |     | 是   | users.id           |
| `performed_at`        | 执行时间     | （据字段名）                                                                                                                  | 时间        |     | 否   |                    |
| `reason`              | 原因       | （据字段名）                                                                                                                  | 长文本       |     | 是   |                    |
| `ip_address`          | IP 地址地址  | 审计溯源扩展字段；用于"谁在什么时间、从哪里、花了多久激活哪个版本"的完整轨迹                                                                                 | 文本（≤64 字） |     | 是   |                    |
| `duration_ms`         | 耗时毫秒     | （据字段名）                                                                                                                  | 整数        |     | 是   |                    |
| `before_row_counts`   | 之前行计数    | 记录激活/回滚前后的四表行数，防静默数据损失；形如 {"tb_balance": 827, "tb_ledger": 1147414, "tb_aux_balance": 127618, "tb_aux_ledger": 2732674} | JSON      |     | 是   |                    |
| `after_row_counts`    | 之后行计数    | （据字段名）                                                                                                                  | JSON      |     | 是   |                    |

## 四、调整分录

### `adjustments` 审计调整分录（头表，AJE/RJE）

- **是什么**：一笔调整分录（审计调整或重分类）的头信息与状态。
- **用到的页面**：`Adjustments.vue`（调整分录大厅）、`CFSWorksheet.vue`（现金流量工作表）、`LinkagePanoramaView.vue`。
- **后端**：`audit_platform_models.py`、`adjustment_review_models.py`。
- **状态**：在用。

**字段**（共 30 个，来源 `database-tables-columns.md`）：

| 字段                          | 中文名    | 说明                                                                                  | 类型         | 主键  | 可空  | 外键                           |
| --------------------------- | ------ | ----------------------------------------------------------------------------------- | ---------- | --- | --- | ---------------------------- |
| `id`                        | 主键     | 通用字段，见文首                                                                            | 编号         | 是   |     |                              |
| `project_id`                | 项目     | 通用字段，见文首                                                                            | 编号         |     | 否   | projects.id                  |
| `year`                      | 年度     | 通用字段，见文首                                                                            | 整数         |     | 否   |                              |
| `company_code`              | 公司代码   | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业                             | 文本         |     | 否   |                              |
| `adjustment_no`             | 分录编号   | 如 `AJE-001`；手填或自动编号；同年度不能重复                                                         | 文本         |     | 否   |                              |
| `adjustment_type`           | 分录类型   | `aje` 审计调整 / `rje` 重分类调整                                                            | 枚举         |     | 否   |                              |
| `description`               | 摘要     | （据字段名）                                                                              | 长文本        |     | 是   |                              |
| `account_code`              | 科目     | 这一行的科目                                                                              | 文本         |     | 否   |                              |
| `account_name`              | 科目     | 这一行的科目                                                                              | 文本         |     | 是   |                              |
| `debit_amount`              | 借方金额   | 一行只能填一边，不能为负                                                                        | 金额（2 位小数）  |     | 是   |                              |
| `credit_amount`             | 贷方金额   | 一行只能填一边，不能为负                                                                        | 金额（2 位小数）  |     | 是   |                              |
| `entry_group_id`            | 分录组    | 同一笔分录的各行共用这个编号                                                                      | 编号         |     | 否   |                              |
| `content_revision`          | 内容修订号  | 分录内容每改一次加 1，只改状态不加；防止两人同时改                                                          | 整数         |     | 否   |                              |
| `audit_phase`               | 审计阶段   | 录入时项目处于哪个阶段；`preliminary` 预审 / `final` 年审（默认）                                       | 文本（≤16 字）  |     | 否   |                              |
| `external_reference`        | 外部编号   | 导入时文件里的编号                                                                           | 文本（≤120 字） |     | 是   |                              |
| `import_batch_id`           | 导入批次   | 从 Excel 导入的才有                                                                       | 编号         |     | 是   | adjustment_import_batches.id |
| `review_status`             | 复核状态   | `draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回。**只有已通过的才进试算表** | 枚举         |     | 否   |                              |
| `reviewer_id`               | 复核人    | （据字段名）                                                                              | 编号         |     | 是   | users.id                     |
| `reviewed_at`               | 复核时间   | （据字段名）                                                                              | 时间         |     | 是   |                              |
| `rejection_reason`          | 驳回原因   | （据字段名）                                                                              | 长文本        |     | 是   |                              |
| `passed_reason`             | 不予更正原因 | 客户不同意调整、作为未更正错报时填写                                                                  | 长文本        |     | 是   |                              |
| `passed_communication_date` | 沟通日期   | 与管理层沟通未更正错报的日期                                                                      | 时间         |     | 是   |                              |
| `origin`                    | 来源     | `manual` 手工录入（默认）/ `workpaper` 来自底稿。来自底稿的不再计入审计调整列，避免和底稿调整重复                        | 文本（≤20 字）  |     | 否   |                              |
| `source_ref`                | 来源底稿行  | 来自哪张底稿的哪一行；格式 `底稿id:行编号`                                                            | 文本（≤120 字） |     | 是   |                              |
| `is_deleted`                | 是否已删除  | 通用字段，见文首                                                                            | 是 / 否      |     | 否   |                              |
| `deleted_at`                | 删除时间   | 通用字段，见文首                                                                            | 时间         |     | 是   |                              |
| `created_by`                | 创建人    | 通用字段，见文首                                                                            | 编号         |     | 否   | users.id                     |
| `updated_by`                | 修改人    | 通用字段，见文首                                                                            | 编号         |     | 是   | users.id                     |
| `created_at`                | 创建时间   | 通用字段，见文首                                                                            | 时间         |     | 否   |                              |
| `updated_at`                | 更新时间   | 通用字段，见文首                                                                            | 时间         |     | 否   |                              |

### `adjustment_entries` 调整分录明细行

- **是什么**：分录的借贷明细行，独立于头表。
- **后端**：`audit_platform_models.py`、`adjustment_review_models.py`、`adjustment_amount_source.py`。
- **前端**：无表名字面量，通过接口，由大厅页间接使用。
- **状态**：在用。

**字段**（共 14 个，来源 `database-tables-columns.md`）：

| 字段                      | 中文名   | 说明                               | 类型        | 主键  | 可空  | 外键             |
| ----------------------- | ----- | -------------------------------- | --------- | --- | --- | -------------- |
| `id`                    | 主键    | 通用字段，见文首                         | 编号        | 是   |     |                |
| `adjustment_id`         | 所属分录  | 指向 `adjustments`                 | 编号        |     | 否   | adjustments.id |
| `entry_group_id`        | 分录组   | 同上                               | 编号        |     | 否   |                |
| `line_no`               | 行号    | 分录内第几行                           | 整数        |     | 否   |                |
| `standard_account_code` | 标准科目  | 汇总到试算表用的科目                       | 文本        |     | 否   |                |
| `detail_account_code`   | 明细科目  | 审计师选的明细科目，用于推送到底稿明细表；为空表示没有更细的明细 | 文本        |     | 是   |                |
| `account_name`          | 科目名称  | （据字段名）                           | 文本        |     | 是   |                |
| `report_line_code`      | 报表行   | 对应的报表行编码                         | 文本        |     | 是   |                |
| `debit_amount`          | 借方金额  | （据字段名）                           | 金额（2 位小数） |     | 否   |                |
| `credit_amount`         | 贷方金额  | （据字段名）                           | 金额（2 位小数） |     | 否   |                |
| `is_deleted`            | 是否已删除 | 通用字段，见文首                         | 是 / 否     |     | 否   |                |
| `deleted_at`            | 删除时间  | 通用字段，见文首                         | 时间        |     | 是   |                |
| `created_at`            | 创建时间  | 通用字段，见文首                         | 时间        |     | 否   |                |
| `updated_at`            | 更新时间  | 通用字段，见文首                         | 时间        |     | 否   |                |

### `adjustment_review_tasks` 调整分录复核任务

- **后端**：`adjustment_review_models.py`。
- **状态**：在用。

**字段**（共 20 个，来源 `database-tables-columns.md`）：

| 字段                            | 中文名      | 说明         | 类型        | 主键  | 可空  | 外键          |
| ----------------------------- | -------- | ---------- | --------- | --- | --- | ----------- |
| `id`                          | 主键       | 通用字段，见文首   | 编号        | 是   |     |             |
| `project_id`                  | 项目       | 通用字段，见文首   | 编号        |     | 否   | projects.id |
| `year`                        | 年度       | 通用字段，见文首   | 整数        |     | 否   |             |
| `entry_group_id`              | 分录组      | （据字段名）     | 编号        |     | 否   |             |
| `status`                      | 状态       | （据字段名）     | 文本（≤20 字） |     | 否   |             |
| `required_level`              | 必填级别     | （据字段名）     | 文本（≤16 字） |     | 否   |             |
| `revision`                    | 修订号      | （据字段名）     | 整数        |     | 否   |             |
| `group_content_revision`      | 组内容修订号   | （据字段名）     | 整数        |     | 否   |             |
| `assigned_reviewer_ids`       | 分配复核人列表  | （据字段名）     | JSON      |     | 否   |             |
| `submitted_by`                | 提交人      | 指向 `users` | 编号        |     | 否   | users.id    |
| `submitted_at`                | 提交时间     | （据字段名）     | 时间        |     | 否   |             |
| `submit_note`                 | 提交附注     | （据字段名）     | 长文本       |     | 是   |             |
| `decided_by`                  | 决定人      | 指向 `users` | 编号        |     | 是   | users.id    |
| `decided_at`                  | 决定时间     | （据字段名）     | 时间        |     | 是   |             |
| `decision_reason`             | 决定原因     | （据字段名）     | 长文本       |     | 是   |             |
| `self_review_override_reason` | 自身复核覆盖原因 | （据字段名）     | 长文本       |     | 是   |             |
| `is_deleted`                  | 是否已删除    | 通用字段，见文首   | 是 / 否     |     | 否   |             |
| `deleted_at`                  | 删除时间     | 通用字段，见文首   | 时间        |     | 是   |             |
| `created_at`                  | 创建时间     | 通用字段，见文首   | 时间        |     | 否   |             |
| `updated_at`                  | 更新时间     | 通用字段，见文首   | 时间        |     | 否   |             |

### `adjustment_collaboration` / `adjustment_collaboration_event` 调整分录协作与事件

- **是什么**：分录的转派、知晓、补充、确认记录，以及只追加的事件历史。
- **后端**：`audit_platform_models.py`。
- **状态**：在用（后端）。

**字段**（共 16 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名   | 说明                                                                                             | 类型         | 主键  | 可空  | 外键          |
| ------------------ | ----- | ---------------------------------------------------------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`               | 主键    | 通用字段，见文首                                                                                       | 编号         | 是   |     |             |
| `project_id`       | 项目    | 通用字段，见文首                                                                                       | 编号         |     | 否   | projects.id |
| `year`             | 年度    | 通用字段，见文首                                                                                       | 整数         |     | 否   |             |
| `entry_group_id`   | 分录组   | （据字段名）                                                                                         | 编号         |     | 否   |             |
| `source_ref`       | 来源引用  | （据字段名）                                                                                         | 文本（≤120 字） |     | 是   |             |
| `initiator_id`     | 发起人编号 | 指向 `users`                                                                                     | 编号         |     | 否   | users.id    |
| `assignee_id`      | 处理人编号 | 指向 `users`                                                                                     | 编号         |     | 否   | users.id    |
| `status`           | 状态    | `pending` 待处理/`acknowledged` 已知悉/`contributed` 已补充/`confirmed` 已确认/`closed` 已关闭/`rejected` 已驳回 | 文本（≤20 字）  |     | 否   |             |
| `round`            | 轮次    | （据字段名）                                                                                         | 整数         |     | 否   |             |
| `note`             | 附注    | （据字段名）                                                                                         | 长文本        |     | 是   |             |
| `rejection_reason` | 驳回原因  | （据字段名）                                                                                         | 长文本        |     | 是   |             |
| `is_deleted`       | 是否已删除 | 通用字段，见文首                                                                                       | 是 / 否      |     | 否   |             |
| `deleted_at`       | 删除时间  | 通用字段，见文首                                                                                       | 时间         |     | 是   |             |
| `created_by`       | 创建人   | 通用字段，见文首                                                                                       | 编号         |     | 是   | users.id    |
| `created_at`       | 创建时间  | 通用字段，见文首                                                                                       | 时间         |     | 否   |             |
| `updated_at`       | 更新时间  | 通用字段，见文首                                                                                       | 时间         |     | 否   |             |

## 五、底稿

### `working_paper` 底稿主表

- **是什么**：一份具体底稿（每个项目每个底稿一条）。
- **用到的页面**：`WorkpaperEditor.vue`、`RecycleBin.vue`（回收站）、`SignatureManagement.vue`（签字）、`WpTemplateDetail.vue`。
- **后端**：`workpaper_models.py`、`wopi.py`、`recycle_bin.py`。
- **状态**：在用，核心表。

**字段**（共 34 个，来源 `database-tables-columns.md`）：

| 字段                           | 中文名       | 说明                                                                                                                                                                                          | 类型        | 主键  | 可空  | 外键                 |
| ---------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | --- | --- | ------------------ |
| `id`                         | 主键        | 通用字段，见文首                                                                                                                                                                                    | 编号        | 是   |     |                    |
| `project_id`                 | 项目        | 通用字段，见文首                                                                                                                                                                                    | 编号        |     | 否   | projects.id        |
| `wp_index_id`                | 底稿目录      | 指向 `wp_index`                                                                                                                                                                               | 编号        |     | 否   | wp_index.id        |
| `file_path`                  | 文件位置      | 服务器上的 Excel 文件                                                                                                                                                                              | 文本        |     | 否   |                    |
| `source_type`                | 来源        | `template` 模板生成 / `manual` 手工新建 / `imported` 导入                                                                                                                                             | 枚举        |     | 否   |                    |
| `status`                     | 编制状态      | `draft` 编制中 / `edit_complete` 编制完成待提交 / `under_review` 复核中 / `revision_required` 退回修改 / `review_passed` 复核通过 / `archived` 已归档（另有两个旧值 `review_level1_passed`、`review_level2_passed` 只为兼容老数据） | 枚举        |     | 否   |                    |
| `review_status`              | 复核进度      | 到第几级复核、什么结果；`not_submitted` 未提交；`pending_levelN` 待 N 级复核；`levelN_in_progress` N 级复核中；`levelN_passed` N 级通过；`levelN_rejected` N 级退回（N = 1~4）                                                 | 枚举        |     | 否   |                    |
| `assigned_to`                | 编制人       | （据字段名）                                                                                                                                                                                      | 编号        |     | 是   | users.id           |
| `reviewer`                   | 复核人       | （据字段名）                                                                                                                                                                                      | 编号        |     | 是   | users.id           |
| `file_version`               | 文件版本      | 文件每保存一次加 1                                                                                                                                                                                  | 整数        |     | 否   |                    |
| `content_revision`           | 内容修订号     | 底稿内容每改一次加 1，用来防止两人同时改冲突                                                                                                                                                                     | 整数        |     | 否   |                    |
| `current_content_version_id` | 当前内容版本编号  | （据字段名）                                                                                                                                                                                      | 编号        |     | 是   |                    |
| `last_parsed_at`             | 解析时间      | 系统从文件里读出的数，内部用                                                                                                                                                                              | 时间        |     | 是   |                    |
| `parsed_data`                | 解析出的数据    | 系统从文件里读出的数，内部用                                                                                                                                                                              | JSON      |     | 是   |                    |
| `prefill_stale`              | 预填已过期     | 试算表变了，底稿里自动取的数需要刷新；是 / 否                                                                                                                                                                    | 是 / 否     |     | 否   |                    |
| `prefill_tb_snapshot`        | 上次预填时的试算表 | 用来对比试算表是否变过；`{科目: 审定数}`                                                                                                                                                                     | JSON      |     | 是   |                    |
| `rejection_reason`           | 退回原因      | （据字段名）                                                                                                                                                                                      | 长文本       |     | 是   |                    |
| `rejected_by`                | 退回人       | （据字段名）                                                                                                                                                                                      | 编号        |     | 是   | users.id           |
| `rejected_at`                | 退回时间      | （据字段名）                                                                                                                                                                                      | 时间        |     | 是   |                    |
| `is_deleted`                 | 是否已删除     | 通用字段，见文首                                                                                                                                                                                    | 是 / 否     |     | 否   |                    |
| `created_by`                 | 创建人       | 通用字段，见文首                                                                                                                                                                                    | 编号        |     | 是   | users.id           |
| `updated_by`                 | 修改人       | 通用字段，见文首                                                                                                                                                                                    | 编号        |     | 是   | users.id           |
| `created_at`                 | 创建时间      | 通用字段，见文首                                                                                                                                                                                    | 时间        |     | 否   |                    |
| `updated_at`                 | 更新时间      | 通用字段，见文首                                                                                                                                                                                    | 时间        |     | 否   |                    |
| `workflow_status`            |           | 取值和用途未查明                                                                                                                                                                                    | 文本（≤30 字） |     | 否   |                    |
| `explanation_status`         |           | 取值和用途未查明                                                                                                                                                                                    | 文本（≤30 字） |     | 否   |                    |
| `consistency_status`         | 数据一致性     | 底稿数和试算表是否一致；`unknown` 未检查 / `inconsistent` 不一致；其他取值未查明                                                                                                                                      | 文本（≤30 字） |     | 否   |                    |
| `quality_score`              | 质量评分      | 为空表示还没算                                                                                                                                                                                     | 整数        |     | 是   |                    |
| `procedure_completion_rate`  | 程序完成率     | 为空表示还没算                                                                                                                                                                                     | 金额（2 位小数） |     | 是   |                    |
| `last_parsed_sync_at`        |           | 取值和用途未查明                                                                                                                                                                                    | 时间        |     | 是   |                    |
| `partner_reviewed_at`        | 合伙人复核时间   | （据字段名）                                                                                                                                                                                      | 时间        |     | 是   |                    |
| `partner_reviewed_by`        | 复核人       | （据字段名）                                                                                                                                                                                      | 编号        |     | 是   | users.id           |
| `bound_dataset_id`           | 绑定的账套版本   | 首次生成底稿时用的账套版本                                                                                                                                                                               | 编号        |     | 是   | ledger_datasets.id |
| `dataset_bound_at`           | 绑定的账套版本   | 首次生成底稿时用的账套版本                                                                                                                                                                               | 时间        |     | 是   |                    |

### `wp_index` 底稿索引（wp_code）

- **是什么**：底稿编码（如 A1、D2-1）的登记表，底稿主表通过它关联编码。
- **用到的页面**：`WorkpaperList.vue`、`WorkpaperDelegationMatrix.vue`（委派矩阵）、`WorkpaperLifecycleView.vue`、`ProcedureTrimming.vue`。
- **后端**：189 处引用，被大量底稿相关模块使用。
- **状态**：在用，核心表。

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                | 中文名   | 说明                                                                                                                                          | 类型    | 主键  | 可空  | 外键          |
| ----------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`              | 主键    | 通用字段，见文首                                                                                                                                    | 编号    | 是   |     |             |
| `project_id`      | 项目    | 通用字段，见文首                                                                                                                                    | 编号    |     | 否   | projects.id |
| `wp_code`         | 底稿编码  | 如 `D2`、`E1-1`；同项目不重复                                                                                                                        | 文本    |     | 否   |             |
| `wp_name`         | 底稿名称  | （据字段名）                                                                                                                                      | 文本    |     | 否   |             |
| `audit_cycle`     | 审计循环  | 一般与底稿编码首字母一致；A 报表与调整 / B 控制了解 / C 控制测试 / D 销售与收款 / E 货币资金 / F 采购与存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 筹资 / M 所有者权益 / N 税费 / S 专项 | 文本    |     | 是   |             |
| `assigned_to`     | 编制人   | （据字段名）                                                                                                                                      | 编号    |     | 是   | users.id    |
| `reviewer`        | 复核人   | （据字段名）                                                                                                                                      | 编号    |     | 是   | users.id    |
| `status`          | 目录状态  | `not_started` 未开始 / `in_progress` 编制中 / `draft_complete` 初稿完成 / `review_passed` 复核通过 / `archived` 已归档                                       | 枚举    |     | 否   |             |
| `cross_ref_codes` | 交叉索引  | 引用了哪些其他底稿；结构未查明                                                                                                                             | JSON  |     | 是   |             |
| `is_deleted`      | 是否已删除 | 通用字段，见文首                                                                                                                                    | 是 / 否 |     | 否   |             |
| `created_at`      | 创建时间  | 通用字段，见文首                                                                                                                                    | 时间    |     | 否   |             |
| `updated_at`      | 更新时间  | 通用字段，见文首                                                                                                                                    | 时间    |     | 否   |             |

### `wp_template` 底稿模板

- **是什么**：底稿模板定义。
- **后端**：`workpaper_models.py`、`wp_optimization_models.py`、`recycle_bin.py`。
- **前端**：通过模板接口使用，页面待核实。
- **状态**：在用。

**字段**（共 14 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名   | 说明                                             | 类型    | 主键  | 可空  | 外键       |
| --------------------- | ----- | ---------------------------------------------- | ----- | --- | --- | -------- |
| `id`                  | 主键    | 通用字段，见文首                                       | 编号    | 是   |     |          |
| `template_code`       | 模板编码  | （据字段名）                                         | 文本    |     | 否   |          |
| `template_name`       | 模板名称  | （据字段名）                                         | 文本    |     | 否   |          |
| `audit_cycle`         | 审计循环  | （据字段名）                                         | 文本    |     | 是   |          |
| `applicable_standard` | 适用准则  | （据字段名）                                         | 文本    |     | 是   |          |
| `version_major`       |       | 未查明                                            | 整数    |     | 否   |          |
| `version_minor`       |       | 未查明                                            | 整数    |     | 否   |          |
| `status`              | 状态    | 取值：`draft` 草稿 / `published` 已发布 / `deprecated` | 枚举    |     | 否   |          |
| `file_path`           | 文件路径  | （据字段名）                                         | 文本    |     | 否   |          |
| `description`         | 说明    | （据字段名）                                         | 长文本   |     | 是   |          |
| `is_deleted`          | 是否已删除 | 通用字段，见文首                                       | 是 / 否 |     | 否   |          |
| `created_by`          | 创建人   | 通用字段，见文首                                       | 编号    |     | 是   | users.id |
| `created_at`          | 创建时间  | 通用字段，见文首                                       | 时间    |     | 否   |          |
| `updated_at`          | 更新时间  | 通用字段，见文首                                       | 时间    |     | 否   |          |

### `checklist_responses` 底稿检查表回答

- **是什么**：底稿中检查表（checklist）每一项的填写内容，是底稿数据的主要存储之一。
- **用到的页面**：大量 `GtXxx*.vue` 底稿组件（如 `GtA117CorrespondingData.vue`、`GtA17Summary.vue`、`GtB19Bundle.vue`）。
- **后端**：`a171_ai_generate.py`、`a176_docx_sync.py` 等约 400 处引用。
- **状态**：在用，核心表，使用面最广。

**字段**（共 10 个，来源 `V085__checklist_responses.sql` 与 `database-tables-columns.md`）：

| 字段           | 中文名   | 说明                 | 类型         | 主键  | 可空  | 外键               |
| ------------ | ----- | ------------------ | ---------- | --- | --- | ---------------- |
| `id`         | 主键    | 逐项记录的编号            | 编号         | 是   | 否   |                  |
| `project_id` | 项目编号  | 所属项目               | 编号         |     | 否   | projects.id      |
| `wp_id`      | 底稿编号  | 所属底稿               | 编号         |     | 否   | working_paper.id |
| `item_id`    | 检查项编号 | 检查表中的条目编码（同一底稿内唯一） | 文本（≤20 字）  |     | 否   |                  |
| `conclusion` | 结论    | 检查项的结论选择           | 文本（≤5 字）   |     | 是   |                  |
| `remark`     | 备注    | 填写人的文字说明           | 长文本        |     | 是   |                  |
| `wp_ref`     | 底稿引用  | 引用的其他底稿位置          | 文本（≤100 字） |     | 是   |                  |
| `updated_by` | 最后修改人 | 最后保存该条的用户          | 编号         |     | 是   | users.id         |
| `created_at` | 创建时间  | 通用字段               | 时间         |     | 否   |                  |
| `updated_at` | 更新时间  | 通用字段               | 时间         |     | 否   |                  |

唯一约束：`(wp_id, item_id)`。注：`conclusion` / `remark` 取值未逐项核实，以代码为准。

### `trial_balance_snapshots` 试算表快照

- **是什么**：某个时点试算表的快照。后端在用（重算时自动生成）
- **后端**：仅 `workpaper_models.py` 1 处引用。
- **状态**：**在用**，待确认是否还有写入。

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段              | 中文名   | 说明       | 类型        | 主键  | 可空  | 外键          |
| --------------- | ----- | -------- | --------- | --- | --- | ----------- |
| `id`            | 主键    | 通用字段，见文首 | 编号        | 是   |     |             |
| `project_id`    | 项目    | 通用字段，见文首 | 编号        |     | 否   | projects.id |
| `year`          | 年度    | 通用字段，见文首 | 整数        |     | 否   |             |
| `version_no`    | 版本编号  | （据字段名）   | 整数        |     | 否   |             |
| `trigger`       | 触发    | （据字段名）   | 文本（≤30 字） |     | 否   |             |
| `actor_id`      | 操作人编号 | （据字段名）   | 编号        |     | 是   |             |
| `content_hash`  | 内容哈希  | （据字段名）   | 文本（≤64 字） |     | 否   |             |
| `snapshot_data` | 快照数据  | （据字段名）   | JSON      |     | 否   |             |
| `row_count`     | 行数量   | （据字段名）   | 整数        |     | 否   |             |
| `audited_total` | 审定合计  | （据字段名）   | 数值        |     | 是   |             |
| `created_at`    | 创建时间  | 通用字段，见文首 | 时间        |     | 否   |             |

## 六、报表与附注

### `report_config` 报表配置（公式、映射）

- **是什么**：报表每个单元格的公式和取数配置。
- **用到的页面**：`ReportConfigEditor.vue`（报表配置编辑）、`ReportView.vue`（报表查看）、`TrialBalance.vue`。
- **后端**：`formula_setting_models.py`、`audit_platform_schemas.py` 等，129 处引用。
- **状态**：在用，核心表。

**字段**（共 26 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名    | 说明                                                                                                                                                                                    | 类型         | 主键  | 可空  | 外键  |
| --------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --- | --- | --- |
| `id`                  | 主键     | 通用字段，见文首                                                                                                                                                                              | 编号         | 是   |     |     |
| `report_type`         | 报表     | 属于哪张报表；`balance_sheet` 资产负债表 / `income_statement` 利润表 / `cash_flow_statement` 现金流量表 / `equity_statement` 所有者权益变动表 / `cash_flow_supplement` 现金流量表补充资料 / `impairment_provision` 资产减值准备表 | 枚举         |     | 否   |     |
| `row_number`          | 行次     | 显示顺序                                                                                                                                                                                  | 整数         |     | 否   |     |
| `row_code`            | 行编码    | 如 `BS-008`；资产负债表 BS、利润表 IS、现金流量表 CFS、权益变动表 EQ、补充资料 CFSS、减值准备表 IMP                                                                                                                     | 文本         |     | 否   |     |
| `row_name`            | 行名称    | 如「应收账款」                                                                                                                                                                               | 文本         |     | 否   |     |
| `indent_level`        | 缩进层级   | 显示时缩进几格                                                                                                                                                                               | 整数         |     | 否   |     |
| `formula`             | 取数公式   | 如 `TB('1122','期末余额')-TB('1231','期末余额')` = 应收账款减坏账准备；为空表示手工填或标题行                                                                                                                       | 长文本        |     | 是   |     |
| `formula_category`    | 公式用途   | `auto_calc` 取数 / `logic_check` 逻辑审核 / `reasonability` 合理性提示                                                                                                                           | 文本（≤20 字）  |     | 是   |     |
| `formula_description` | 公式说明   | 给人看的简短说明                                                                                                                                                                              | 文本（≤200 字） |     | 是   |     |
| `formula_source`      | 公式来源   | 如「试算表审定数」「报表行次引用」「手工填列」                                                                                                                                                               | 文本（≤100 字） |     | 是   |     |
| `applicable_standard` | 适用范围   | 这行属于哪套报表；`soe_standalone` 国企单体 / `soe_consolidated` 国企合并 / `listed_standalone` 上市单体 / `listed_consolidated` 上市合并 / `project:项目id` 某项目改过的公式                                            | 文本         |     | 否   |     |
| `is_total_row`        | 是否合计行  | 是 / 否                                                                                                                                                                                 | 是 / 否      |     | 否   |     |
| `parent_row_code`     | 上级行    | （据字段名）                                                                                                                                                                                | 文本         |     | 是   |     |
| `is_deleted`          | 是否已删除  | 通用字段，见文首                                                                                                                                                                              | 是 / 否      |     | 否   |     |
| `aje_formula`         | 调整列公式  | 试算平衡表里这一行的审计调整 / 重分类列怎么算；为空时按公式里的科目自动汇总                                                                                                                                               | 长文本        |     | 是   |     |
| `rje_formula`         | 调整列公式  | 试算平衡表里这一行的审计调整 / 重分类列怎么算；为空时按公式里的科目自动汇总                                                                                                                                               | 长文本        |     | 是   |     |
| `is_stale`            | 待更新    | 全局公式更新后，项目这一行被标记需要处理                                                                                                                                                                  | 是 / 否      |     | 否   |     |
| `formula_version`     | 版本号    | 每改一次加 1，防止两人同时改                                                                                                                                                                       | 整数         |     | 否   |     |
| `created_at`          | 创建时间   | 通用字段，见文首                                                                                                                                                                              | 时间         |     | 否   |     |
| `updated_at`          | 更新时间   | 通用字段，见文首                                                                                                                                                                              | 时间         |     | 否   |     |
| `updated_by`          | 修改人    | 通用字段，见文首                                                                                                                                                                              | 编号         |     | 是   |     |
| `base_version`        | 上游版本   | 用来判断项目是否改过、全局更新后是否冲突                                                                                                                                                                  | 整数         |     | 是   |     |
| `base_definition`     | 上游公式快照 | 用来判断项目是否改过、全局更新后是否冲突                                                                                                                                                                  | JSON       |     | 是   |     |
| `pinned`              | 是否固定   | 项目选择「暂不跟随」全局公式更新时为是                                                                                                                                                                   | 是 / 否      |     | 否   |     |
| `base_origin`         | 跟随的上游  | 项目公式基于哪一层；`global` 全局 / `template` 公式模板                                                                                                                                               | 文本（≤16 字）  |     | 是   |     |
| `base_template_id`    | 上游模板   | 用来判断项目是否改过、全局更新后是否冲突                                                                                                                                                                  | 编号         |     | 是   |     |

### `financial_report` 财务报表

- **是什么**：生成的财务报表（三大报表等）。
- **用到的页面**：`AuditReportEditor.vue`、`DeliverableCenter.vue`（交付中心）、`LinkagePanoramaView.vue`。
- **后端**：`phase13_models.py`、`consol_workpaper_instance_models.py`。
- **状态**：在用。

**字段**（共 22 个，来源 `database-tables-columns.md`）：

| 字段                      | 中文名   | 说明                                                        | 类型         | 主键  | 可空  | 外键                       |
| ----------------------- | ----- | --------------------------------------------------------- | ---------- | --- | --- | ------------------------ |
| `id`                    | 主键    | 通用字段，见文首                                                  | 编号         | 是   |     |                          |
| `project_id`            | 项目    | 通用字段，见文首                                                  | 编号         |     | 否   | projects.id              |
| `year`                  | 年度    | 通用字段，见文首                                                  | 整数         |     | 否   |                          |
| `report_type`           | 报表    | 同 `report_config`                                         | 枚举         |     | 否   |                          |
| `row_code`              | 行编码   | 同 `report_config`                                         | 文本         |     | 否   |                          |
| `row_name`              | 行名称   | 同 `report_config`                                         | 文本         |     | 是   |                          |
| `current_period_amount` | 本期金额  | 按公式算出的期末数或本期数；计算失败时保留旧值，新行为空，不写 0                         | 金额（2 位小数）  |     | 是   |                          |
| `prior_period_amount`   | 上期金额  | 资产负债表取本年期初数；利润表等取上年数；没有来源时为空                              | 金额（2 位小数）  |     | 是   |                          |
| `formula_used`          | 使用的公式 | 生成时实际用的公式                                                 | 长文本        |     | 是   |                          |
| `source_accounts`       | 涉及科目  | 公式用到了哪些标准科目，例 `["1122","1231"]`；权益变动表、减值准备表这里存的是人工编辑的矩阵数据 | JSON       |     | 是   |                          |
| `generated_at`          | 生成时间  | （据字段名）                                                    | 时间         |     | 是   |                          |
| `indent_level`          | 缩进    | 同 `report_config`                                         | 整数         |     | 否   |                          |
| `is_total_row`          | 合计行   | 同 `report_config`                                         | 是 / 否      |     | 否   |                          |
| `is_stale`              | 已过期   | 计算失败或上游数据变了，需要重新生成                                        | 是 / 否      |     | 否   |                          |
| `blank_reason`          | 留空原因  | 金额为空时写明原因；如「母公司汇总上年数未结转」                                  | 长文本        |     | 是   |                          |
| `calc_version`          | 计算版本  | 追溯是哪一次生成写的；系统内部用                                          | 整数         |     | 是   |                          |
| `calc_error`            | 失败原因  | 计算失败时的原因；成功时为空                                            | 文本（≤500 字） |     | 是   |                          |
| `run_id`                | 生成批次  | 追溯是哪一次生成写的；系统内部用                                          | 编号         |     | 是   | report_generation_run.id |
| `provenance`            | 来源记录  | 追溯是哪一次生成写的；系统内部用                                          | JSON       |     | 是   |                          |
| `is_deleted`            | 是否已删除 | 通用字段，见文首                                                  | 是 / 否      |     | 否   |                          |
| `created_at`            | 创建时间  | 通用字段，见文首                                                  | 时间         |     | 否   |                          |
| `updated_at`            | 更新时间  | 通用字段，见文首                                                  | 时间         |     | 否   |                          |

### `disclosure_notes` 附注

- **是什么**：财务报表附注的章节内容。
- **用到的页面**：`DeliverableCenter.vue`、`PDFExportPanel.vue`（导出）、`LinkagePanoramaView.vue`。
- **后端**：`note_trim_models.py`，108 处引用。
- **状态**：在用，核心表。

**字段**（共 38 个，来源 `database-tables-columns.md`）：

| 字段                        | 中文名       | 说明                                                                                                        | 类型         | 主键  | 可空  | 外键                 |
| ------------------------- | --------- | --------------------------------------------------------------------------------------------------------- | ---------- | --- | --- | ------------------ |
| `id`                      | 主键        | 通用字段，见文首                                                                                                  | 编号         | 是   |     |                    |
| `project_id`              | 项目        | 通用字段，见文首                                                                                                  | 编号         |     | 否   | projects.id        |
| `year`                    | 年度        | 通用字段，见文首                                                                                                  | 整数         |     | 否   |                    |
| `note_section`            | 章节号       | 如 `五、5`；同项目同年度不重复                                                                                         | 文本         |     | 否   |                    |
| `section_title`           | 章节标题      | 如「应收账款」                                                                                                   | 文本         |     | 否   |                    |
| `section_id`              | 章节编号      | 组成附注目录树                                                                                                   | 文本（≤100 字） |     | 是   |                    |
| `level`                   | 层级        | 组成附注目录树                                                                                                   | 整数         |     | 是   |                    |
| `parent_section_id`       | 上级章节      | 组成附注目录树                                                                                                   | 文本（≤100 字） |     | 是   |                    |
| `sort_index`              | 排序        | （据字段名）                                                                                                    | 整数         |     | 否   |                    |
| `auto_numbering`          | 自动编号      | 章节号是自动排还是手工固定                                                                                             | 是 / 否      |     | 否   |                    |
| `lock_number`             | 锁定编号      | 章节号是自动排还是手工固定                                                                                             | 是 / 否      |     | 否   |                    |
| `locked_number`           | 锁定的编号     | 章节号是自动排还是手工固定                                                                                             | 文本（≤50 字）  |     | 是   |                    |
| `account_name`            | 对应科目      | （据字段名）                                                                                                    | 文本         |     | 是   |                    |
| `content_type`            | 内容类型      | `table` 表格 / `text` 文字 / `mixed` 表格加文字                                                                    | 枚举         |     | 是   |                    |
| `table_data`              | 表格内容      | 表格的行、列、数值，以及每个格是自动取数、手工填写还是锁定；JSON                                                                        | JSON       |     | 是   |                    |
| `text_content`            | 正文        | 文字说明                                                                                                      | 长文本        |     | 是   |                    |
| `guidance_text`           | 编制指引      | 提示怎么写                                                                                                     | 长文本        |     | 是   |                    |
| `source_template`         | 模板版本      | `soe` 国企版 / `listed` 上市版                                                                                  | 枚举         |     | 是   |                    |
| `status`                  | 状态        | `draft` 草稿 / `confirmed` 已确认                                                                              | 枚举         |     | 否   |                    |
| `sort_order`              | 排序        | （据字段名）                                                                                                    | 整数         |     | 是   |                    |
| `is_deleted`              | 是否已删除     | 通用字段，见文首                                                                                                  | 是 / 否      |     | 否   |                    |
| `is_stale`                | 待刷新       | 上游数据变了，附注需要刷新                                                                                             | 是 / 否      |     | 否   |                    |
| `stale_source`            | 什么变了      | `trial_balance` 试算表 / `report` 报表 / `report_fallback` 报表（整体标记）/ `workpaper` 或 `workpaper_saved` 底稿；为空是老数据 | 文本（≤32 字）  |     | 是   |                    |
| `bound_dataset_id`        | 绑定的账套版本   | 生成附注时用的是哪个账套版本                                                                                            | 编号         |     | 是   | ledger_datasets.id |
| `dataset_bound_at`        | 绑定时间      | 生成附注时用的是哪个账套版本                                                                                            | 时间         |     | 是   |                    |
| `is_empty`                | 本期无此项     | 是 / 否                                                                                                     | 是 / 否      |     | 否   |                    |
| `template_lineage`        | 模板来源      | 系统内部用；结构未查明                                                                                               | JSON       |     | 是   |                    |
| `is_local_override`       | 本项目改过模板   | （据字段名）                                                                                                    | 是 / 否      |     | 否   |                    |
| `text_template_vars`      | 正文变量      | 系统内部用；结构未查明                                                                                               | JSON       |     | 是   |                    |
| `source_project_id`       | 来源项目      | 合并附注穿透到子企业用                                                                                               | 编号         |     | 是   |                    |
| `consolidation_breakdown` | 合并明细      | 合并附注穿透到子企业用                                                                                               | JSON       |     | 是   |                    |
| `last_sync_source`        | 最近一次谁更新的数 | `workpaper` 底稿推送 / `workpaper_html` 网页底稿推送 / `formula_push` 公式推送                                          | 文本（≤50 字）  |     | 是   |                    |
| `last_sync_wp_id`         | 最近同步的底稿   | （据字段名）                                                                                                    | 编号         |     | 是   | working_paper.id   |
| `last_sync_at`            | 时间        | （据字段名）                                                                                                    | 时间         |     | 是   |                    |
| `last_sync_user_id`       | 操作人       | （据字段名）                                                                                                    | 编号         |     | 是   | users.id           |
| `created_at`              | 创建时间      | 通用字段，见文首                                                                                                  | 时间         |     | 否   |                    |
| `updated_at`              | 更新时间      | 通用字段，见文首                                                                                                  | 时间         |     | 否   |                    |
| `updated_by`              | 修改人       | 通用字段，见文首                                                                                                  | 编号         |     | 是   | users.id           |

### `account_note_mapping` 科目→附注行映射

- **是什么**：把科目金额填到附注表格行的映射。
- **后端**：`account_note_mapping_models.py`。
- **状态**：在用。

**字段**（共 8 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名  | 说明       | 类型         | 主键  | 可空  | 外键  |
| -------------- | ---- | -------- | ---------- | --- | --- | --- |
| `id`           | 主键   | 通用字段，见文首 | 编号         | 是   |     |     |
| `project_id`   | 项目   | 通用字段，见文首 | 编号         |     | 否   |     |
| `account_name` | 科目名称 | （据字段名）   | 文本（≤200 字） |     | 否   |     |
| `section_id`   | 章节编号 | （据字段名）   | 文本（≤50 字）  |     | 否   |     |
| `row_name`     | 行名称  | （据字段名）   | 文本（≤200 字） |     | 否   |     |
| `col_index`    | 列序号  | （据字段名）   | 整数         |     | 否   |     |
| `mapping_type` | 映射类型 | （据字段名）   | 文本（≤20 字）  |     | 否   |     |
| `created_at`   | 创建时间 | 通用字段，见文首 | 时间         |     | 否   |     |

### `audit_report` 审计报告 / `audit_report_template` 审计报告段落模板

- **是什么**：审计报告正文及段落模板。
- **后端**：`report_models.py`。
- **前端**：待核实。
- **状态**：在用（后端）。

**字段**（共 25 个，来源 `database-tables-columns.md`）：

| 字段                           | 中文名      | 说明                                                                                | 类型        | 主键  | 可空  | 外键                 |
| ---------------------------- | -------- | --------------------------------------------------------------------------------- | --------- | --- | --- | ------------------ |
| `id`                         | 主键       | 通用字段，见文首                                                                          | 编号        | 是   |     |                    |
| `project_id`                 | 项目       | 通用字段，见文首                                                                          | 编号        |     | 否   | projects.id        |
| `year`                       | 年度       | 通用字段，见文首                                                                          | 整数        |     | 否   |                    |
| `opinion_type`               | 意见类型     | 取值：`unqualified` 无保留意见 / `qualified` 保留意见 / `adverse` 否定意见 / `disclaimer` 无法表示意见  | 枚举        |     | 否   |                    |
| `company_type`               | 公司类型     | 取值：`listed` 上市 / `non_listed` 非上市                                                 | 枚举        |     | 否   |                    |
| `report_date`                | 报表日期     | （据字段名）                                                                            | 日期        |     | 是   |                    |
| `signing_partner`            | 签字合伙人    | （据字段名）                                                                            | 文本        |     | 是   |                    |
| `paragraphs`                 | 段落       | （据字段名）                                                                            | JSON      |     | 是   |                    |
| `financial_data`             | 财务数据     | （据字段名）                                                                            | JSON      |     | 是   |                    |
| `status`                     | 状态       | 取值：`draft` 草稿 / `review` 复核中 / `eqcr_approved` EQCR 已通过 / `final` 定稿              | 枚举        |     | 否   |                    |
| `is_deleted`                 | 是否已删除    | 通用字段，见文首                                                                          | 是 / 否     |     | 否   |                    |
| `is_stale`                   | 是否过期     | （据字段名）                                                                            | 是 / 否     |     | 否   |                    |
| `bound_dataset_id`           | 绑定账套版本编号 | 下游快照绑定；AuditReport 绑定时机特殊：不是创建时，而是 status 转 final 时锁定（签字级合规）；指向 `ledger_datasets` | 编号        |     | 是   | ledger_datasets.id |
| `dataset_bound_at`           | 账套版本绑定时间 | （据字段名）                                                                            | 时间        |     | 是   |                    |
| `created_at`                 | 创建时间     | 通用字段，见文首                                                                          | 时间        |     | 否   |                    |
| `updated_at`                 | 更新时间     | 通用字段，见文首                                                                          | 时间        |     | 否   |                    |
| `created_by`                 | 创建人      | 通用字段，见文首                                                                          | 编号        |     | 是   | users.id           |
| `updated_by`                 | 修改人      | 通用字段，见文首                                                                          | 编号        |     | 是   | users.id           |
| `report_body_json`           | 报表正文JSON | deliverable-center                                                                | JSON      |     | 是   |                    |
| `is_pie`                     | 是否饼图     | （据字段名）                                                                            | 是 / 否     |     | 是   |                    |
| `prior_period_info`          | 上期期间信息   | （据字段名）                                                                            | 文本（≤40 字） |     | 是   |                    |
| `company_subtype`            | 公司子类型    | 企业子类型 + 模板详简版 + manifest 模板版本                                                     | 文本（≤10 字） |     | 是   |                    |
| `template_variant`           | 模板变体     | （据字段名）                                                                            | 文本（≤10 字） |     | 是   |                    |
| `template_version`           | 模板版本     | （据字段名）                                                                            | 文本（≤20 字） |     | 是   |                    |
| `representation_letter_date` | 表示形式函件日期 | CW-76: 管理层声明书签署日期（A16 signed 时用户必填，push 到此处）                                      | 日期        |     | 是   |                    |

## 七、附件、证据与函证

### `attachments` 附件

- **是什么**：上传的凭证、函证回函等文件的记录。
- **用到的页面**：`AttachmentHub.vue`、`AttachmentManagement.vue`、`DefaultLayout.vue`。
- **后端**：`attachment_models.py`，65 处引用。
- **状态**：在用，核心表。

**字段**（共 38 个，来源 `database-tables-columns.md`）：

| 字段                          | 中文名           | 说明                                                                                      | 类型         | 主键  | 可空  | 外键                    |
| --------------------------- | ------------- | --------------------------------------------------------------------------------------- | ---------- | --- | --- | --------------------- |
| `id`                        | 主键            | 通用字段，见文首                                                                                | 编号         | 是   |     |                       |
| `project_id`                | 项目            | 通用字段，见文首                                                                                | 编号         |     | 否   | projects.id           |
| `file_name`                 | 文件名           | （据字段名）                                                                                  | 文本（≤255 字） |     | 否   |                       |
| `file_path`                 | 文件路径          | （据字段名）                                                                                  | 文本（≤500 字） |     | 否   |                       |
| `file_type`                 | 文件类型          | （据字段名）                                                                                  | 文本（≤50 字）  |     | 否   |                       |
| `file_size`                 | 文件大小          | （据字段名）                                                                                  | 整数         |     | 否   |                       |
| `attachment_type`           | 附件类型          | （据字段名）                                                                                  | 文本（≤50 字）  |     | 否   |                       |
| `reference_id`              | 引用编号          | （据字段名）                                                                                  | 编号         |     | 是   |                       |
| `reference_type`            | 引用类型          | （据字段名）                                                                                  | 文本（≤50 字）  |     | 是   |                       |
| `storage_type`              | 存储类型          | （据字段名）                                                                                  | 文本（≤20 字）  |     | 否   |                       |
| `paperless_document_id`     | Paperless文档编号 | （据字段名）                                                                                  | 整数         |     | 是   |                       |
| `ocr_status`                | 识别状态          | （据字段名）                                                                                  | 文本（≤20 字）  |     | 否   |                       |
| `ocr_text`                  | 识别文本          | （据字段名）                                                                                  | 长文本        |     | 是   |                       |
| `ocr_fields_cache`          | 识别字段缓存        | （据字段名）                                                                                  | JSON       |     | 是   |                       |
| `is_deleted`                | 是否已删除         | 通用字段，见文首                                                                                | 是 / 否      |     | 否   |                       |
| `created_by`                | 创建人           | 通用字段，见文首                                                                                | 编号         |     | 是   | users.id              |
| `created_at`                | 创建时间          | 通用字段，见文首                                                                                | 时间         |     | 否   |                       |
| `updated_at`                | 更新时间          | 通用字段，见文首                                                                                | 时间         |     | 否   |                       |
| `version`                   | 版本号           | AT-3 版本管理                                                                               | 整数         |     | 否   |                       |
| `previous_version_id`       | 上一版本编号        | （据字段名）                                                                                  | 编号         |     | 是   |                       |
| `audit_year`                | 审计年度          | （据字段名）                                                                                  | 整数         |     | 是   |                       |
| `original_file_name`        | 原始文件名称        | （据字段名）                                                                                  | 文本（≤500 字） |     | 是   |                       |
| `source_type`               | 来源类型          | （据字段名）                                                                                  | 文本（≤50 字）  |     | 是   |                       |
| `obtained_at`               | 取得时间          | （据字段名）                                                                                  | 时间         |     | 是   |                       |
| `provider`                  | 提供方           | （据字段名）                                                                                  | 文本（≤200 字） |     | 是   |                       |
| `is_key_evidence`           | 是否键证据         | （据字段名）                                                                                  | 是 / 否      |     | 否   |                       |
| `metadata_status`           | 元数据状态         | （据字段名）                                                                                  | 文本（≤20 字）  |     | 否   |                       |
| `metadata_missing`          | 元数据缺失         | （据字段名）                                                                                  | JSON       |     | 是   |                       |
| `state`                     | 状态            | （据字段名）                                                                                  | 文本（≤20 字）  |     | 否   |                       |
| `current_version_id`        | 当前版本编号        | （据字段名）                                                                                  | 编号         |     | 是   |                       |
| `actor_type`                | 操作人类型         | （据字段名）                                                                                  | 文本（≤20 字）  |     | 是   |                       |
| `actor_user_id`             | 操作人用户编号       | 指向 `users`                                                                              | 编号         |     | 是   | users.id              |
| `actor_service_identity_id` | 操作人服务身份编号     | 指向 `service_identities`                                                                 | 编号         |     | 是   | service_identities.id |
| `original_creator_unknown`  | 原始创建人未知       | （据字段名）                                                                                  | 是 / 否      |     | 否   |                       |
| `ocr_confirmed_sha256`      | 识别确认SHA256 哈希 | 识别文本确认留痕；确认有效 = ocr_confirmed_sha256 等于当前全文 sha256（判定在 services/attachment_ocr_text.py） | 文本（≤64 字）  |     | 是   |                       |
| `ocr_confirmed_by`          | 识别确认人         | 指向 `users`                                                                              | 编号         |     | 是   | users.id              |
| `ocr_confirmed_at`          | 识别确认时间        | （据字段名）                                                                                  | 时间         |     | 是   |                       |
| `ocr_confirmed_edited`      | 识别确认编辑        | （据字段名）                                                                                  | 是 / 否      |     | 是   |                       |

### `attachment_working_paper` 附件-底稿关联

- **后端**：`attachment_models.py`。
- **状态**：在用。

**字段**（共 10 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名  | 说明                               | 类型         | 主键  | 可空  | 外键               |
| ------------------ | ---- | -------------------------------- | ---------- | --- | --- | ---------------- |
| `id`               | 主键   | 通用字段，见文首                         | 编号         | 是   |     |                  |
| `attachment_id`    | 附件编号 | 指向 `attachments`                 | 编号         |     | 否   | attachments.id   |
| `wp_id`            | 底稿   | 指向 `working_paper`               | 编号         |     | 否   | working_paper.id |
| `association_type` | 关联类型 | （据字段名）                           | 文本（≤50 字）  |     | 否   |                  |
| `notes`            | 备注   | （据字段名）                           | 长文本        |     | 是   |                  |
| `row_ref`          | 行引用  | 行级绑定（格式 "{sheet_name}:{row_id}"） | 文本（≤100 字） |     | 是   |                  |
| `created_by`       | 创建人  | 通用字段，见文首                         | 编号         |     | 是   | users.id         |
| `created_at`       | 创建时间 | 通用字段，见文首                         | 时间         |     | 否   |                  |
| `description`      | 说明   | （据字段名）                           | 长文本        |     | 是   |                  |
| `working_paper_id` | 底稿   | （据字段名）                           | 编号         |     | 是   |                  |

### `attachment_versions` 附件不可变版本快照

- **后端**：`evidence_governance_models.py`、`asset_blob_models.py`、`evidence_ref_router.py`。
- **前端**：无页面字面量。
- **状态**：在用（后台）。

**字段**（共 19 个，来源 `database-tables-columns.md`）：

| 字段                          | 中文名       | 说明                      | 类型         | 主键  | 可空  | 外键                    |
| --------------------------- | --------- | ----------------------- | ---------- | --- | --- | --------------------- |
| `id`                        | 主键        | 通用字段，见文首                | 编号         | 是   |     |                       |
| `attachment_id`             | 附件编号      | （据字段名）                  | 编号         |     | 否   |                       |
| `project_id`                | 项目        | 通用字段，见文首                | 编号         |     | 否   |                       |
| `audit_year`                | 审计年度      | （据字段名）                  | 整数         |     | 是   |                       |
| `version_no`                | 版本编号      | （据字段名）                  | 整数         |     | 否   |                       |
| `storage_type`              | 存储类型      | （据字段名）                  | 文本（≤20 字）  |     | 否   |                       |
| `storage_key`               | 存储键       | （据字段名）                  | 文本（≤500 字） |     | 是   |                       |
| `media_type`                | 媒体类型      | （据字段名）                  | 文本（≤100 字） |     | 是   |                       |
| `byte_size`                 | 字节大小      | （据字段名）                  | 整数         |     | 是   |                       |
| `content_hash`              | 内容哈希      | （据字段名）                  | 文本（≤64 字）  |     | 是   |                       |
| `blob_id`                   | 文件内容编号    | 指向 `asset_blobs`        | 编号         |     | 是   | asset_blobs.id        |
| `config_snapshot`           | 配置快照      | （据字段名）                  | JSON       |     | 是   |                       |
| `availability`              | 可用性       | （据字段名）                  | 文本（≤20 字）  |     | 否   |                       |
| `previous_version_id`       | 上一版本编号    | （据字段名）                  | 编号         |     | 是   |                       |
| `actor_type`                | 操作人类型     | （据字段名）                  | 文本（≤20 字）  |     | 否   |                       |
| `actor_user_id`             | 操作人用户编号   | 指向 `users`              | 编号         |     | 是   | users.id              |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号         |     | 是   | service_identities.id |
| `original_creator_unknown`  | 原始创建人未知   | （据字段名）                  | 是 / 否      |     | 否   |                       |
| `created_at`                | 创建时间      | 通用字段，见文首                | 时间         |     | 否   |                       |

### `asset_blobs` 文件内容库

- **是什么**：按内容哈希去重保存的文件实体。附件版本、知识库文档、AI 会话资源
- **后端**：`asset_blob_models.py`。
- **状态**：在用（后台）。

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                          | 中文名       | 说明                      | 类型         | 主键  | 可空  | 外键                    |
| --------------------------- | --------- | ----------------------- | ---------- | --- | --- | --------------------- |
| `id`                        | 主键        | 通用字段，见文首                | 编号         | 是   |     |                       |
| `content_hash`              | 内容哈希      | （据字段名）                  | 文本（≤64 字）  |     | 否   |                       |
| `byte_size`                 | 字节大小      | （据字段名）                  | 整数         |     | 否   |                       |
| `detected_media_type`       | 检测到媒体类型   | （据字段名）                  | 文本（≤128 字） |     | 是   |                       |
| `storage_type`              | 存储类型      | （据字段名）                  | 文本（≤24 字）  |     | 否   |                       |
| `storage_key`               | 存储键       | （据字段名）                  | 长文本        |     | 否   |                       |
| `ingress_policy_version`    | 入口策略版本    | （据字段名）                  | 文本（≤32 字）  |     | 否   |                       |
| `security_status`           | 安全状态      | （据字段名）                  | 文本（≤20 字）  |     | 否   |                       |
| `actor_type`                | 操作人类型     | （据字段名）                  | 文本（≤20 字）  |     | 否   |                       |
| `actor_user_id`             | 操作人用户编号   | 指向 `users`              | 编号         |     | 是   | users.id              |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号         |     | 是   | service_identities.id |
| `created_at`                | 创建时间      | 通用字段，见文首                | 时间         |     | 否   |                       |

### `archive_jobs` 归档作业 / `archive_manifests` 归档清单

- **是什么**：归档任务及其 manifest（证据清单）。
- **后端**：`archive_models.py`、`evidence_governance_models.py`。
- **状态**：在用（后台）。

**字段**（共 20 个，来源 `database-tables-columns.md`）：

| 字段                       | 中文名    | 说明                                                                                         | 类型         | 主键  | 可空  | 外键          |
| ------------------------ | ------ | ------------------------------------------------------------------------------------------ | ---------- | --- | --- | ----------- |
| `id`                     | 主键     | 通用字段，见文首                                                                                   | 编号         | 是   |     |             |
| `project_id`             | 项目     | 通用字段，见文首                                                                                   | 编号         |     | 否   | projects.id |
| `scope`                  | 范围     | '`final` 定稿' \| '`interim` 预审'                                                             | 文本（≤20 字）  |     | 否   |             |
| `status`                 | 状态     | '`queued` 排队中' \| '`running` 运行中' \| '`succeeded` 成功' \| '`failed` 失败' \| '`partial` 部分成功' | 文本（≤20 字）  |     | 否   |             |
| `push_to_cloud`          | 推送到云端  | （据字段名）                                                                                     | 是 / 否      |     | 否   |             |
| `purge_local`            | 清除本地   | （据字段名）                                                                                     | 是 / 否      |     | 否   |             |
| `gate_eval_id`           | 门禁评估编号 | （据字段名）                                                                                     | 编号         |     | 是   |             |
| `last_succeeded_section` | 最近成功章节 | （据字段名）                                                                                     | 文本（≤16 字）  |     | 是   |             |
| `failed_section`         | 失败章节   | （据字段名）                                                                                     | 文本（≤16 字）  |     | 是   |             |
| `failed_reason`          | 失败原因   | （据字段名）                                                                                     | 长文本        |     | 是   |             |
| `section_progress`       | 章节进度   | （据字段名）                                                                                     | JSON       |     | 是   |             |
| `output_url`             | 输出地址   | （据字段名）                                                                                     | 文本（≤500 字） |     | 是   |             |
| `manifest_hash`          | 清单哈希   | （据字段名）                                                                                     | 文本（≤64 字）  |     | 是   |             |
| `started_at`             | 开始时间   | （据字段名）                                                                                     | 时间         |     | 是   |             |
| `finished_at`            | 结束时间   | （据字段名）                                                                                     | 时间         |     | 是   |             |
| `initiated_by`           | 发起人    | 指向 `users`                                                                                 | 编号         |     | 是   | users.id    |
| `is_deleted`             | 是否已删除  | 通用字段，见文首                                                                                   | 是 / 否      |     | 否   |             |
| `deleted_at`             | 删除时间   | 通用字段，见文首                                                                                   | 时间         |     | 是   |             |
| `created_at`             | 创建时间   | 通用字段，见文首                                                                                   | 时间         |     | 否   |             |
| `updated_at`             | 更新时间   | 通用字段，见文首                                                                                   | 时间         |     | 否   |             |

### `confirmation_letters` 函证信

- **是什么**：函证信的登记。
- **后端**：仅 `collaboration_models.py` 1 处定义，无读写代码。
- **状态**：**疑似冗余**。函证的实际使用在附件与底稿相关表中，待确认。

**字段**（共 9 个，来源 `database-tables-columns.md`）：

| 字段                     | 中文名    | 说明                      | 类型         | 主键  | 可空  | 外键                    |
| ---------------------- | ------ | ----------------------- | ---------- | --- | --- | --------------------- |
| `id`                   | 主键     | 通用字段，见文首                | 编号         | 是   |     |                       |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号         |     | 否   | confirmation_lists.id |
| `letter_format`        | 函件格式   | （据字段名）                  | 文本（≤50 字）  |     | 否   |                       |
| `recipient_name`       | 接收人名称  | （据字段名）                  | 文本（≤200 字） |     | 否   |                       |
| `recipient_address`    | 接收人地址  | （据字段名）                  | 长文本        |     | 是   |                       |
| `content`              | 内容     | （据字段名）                  | 长文本        |     | 是   |                       |
| `template_id`          | 模板编号   | （据字段名）                  | 编号         |     | 是   |                       |
| `created_at`           | 创建时间   | 通用字段，见文首                | 时间         |     | 否   |                       |
| `updated_at`           | 更新时间   | 通用字段，见文首                | 时间         |     | 否   |                       |

## 八、通知、审计日志、AI 与其他

### `notifications` 站内通知

- **用到的页面**：`NotificationCenter.vue`、`NotificationList.vue`、`DefaultLayout.vue`。
- **后端**：`collaboration_models.py`、`core.py`。
- **状态**：在用。

**字段**（共 14 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名     | 说明                                                                                          | 类型         | 主键  | 可空  | 外键       |
| --------------------- | ------- | ------------------------------------------------------------------------------------------- | ---------- | --- | --- | -------- |
| `id`                  | 主键      | 通用字段，见文首                                                                                    | 编号         | 是   |     |          |
| `recipient_id`        | 接收人编号   | 指向 `users`                                                                                  | 编号         |     | 否   | users.id |
| `message_type`        | 消息类型    | （据字段名）                                                                                      | 文本（≤50 字）  |     | 否   |          |
| `title`               | 标题      | （据字段名）                                                                                      | 文本（≤255 字） |     | 否   |          |
| `content`             | 内容      | （据字段名）                                                                                      | 长文本        |     | 是   |          |
| `related_object_type` | 相关对象类型  | （据字段名）                                                                                      | 文本（≤100 字） |     | 是   |          |
| `related_object_id`   | 相关对象编号  | （据字段名）                                                                                      | 编号         |     | 是   |          |
| `is_read`             | 是否已读    | （据字段名）                                                                                      | 是 / 否      |     | 否   |          |
| `read_at`             | 已读时间    | （据字段名）                                                                                      | 时间         |     | 是   |          |
| `created_at`          | 创建时间    | 通用字段，见文首                                                                                    | 时间         |     | 否   |          |
| `event_id`            | 事件编号    | 聚合通知扩展（；additive-only：event_id+recipient_user_id 去重、dedup_key、metadata 驱动跳转（不解析中文 content）。 | 文本（≤128 字） |     | 是   |          |
| `recipient_user_id`   | 接收人用户编号 | 指向 `users`                                                                                  | 编号         |     | 是   | users.id |
| `dedup_key`           | 去重键     | （据字段名）                                                                                      | 文本（≤200 字） |     | 是   |          |
| `metadata`            | 元数据     | （据字段名）                                                                                      | JSON       |     | 是   |          |

### `audit_log_entries` 审计日志（不可变追加）

- **是什么**：操作留痕，哈希链保证不可篡改。
- **是什么补充**：公式变更审计 API（`/api/formula-audit-log/...`，旧 `formula_audit_log` 表已收口，不再是独立表）的数据也写在这张表（`action_type='formula.changed'`）。
- **后端**：`audit_log_models.py`、`formula_audit_log.py`（路由）、`qc_audit_log_compliance.py`。
- **前端**：无页面字面量（日志查看页待核实）。
- **状态**：在用。

**字段**（共 13 个，来源 `database-tables-columns.md`）：

| 字段            | 中文名   | 说明       | 类型         | 主键  | 可空  | 外键  |
| ------------- | ----- | -------- | ---------- | --- | --- | --- |
| `id`          | 主键    | 通用字段，见文首 | 编号         | 是   |     |     |
| `ts`          | 时间戳   | （据字段名）   | 时间         |     | 否   |     |
| `user_id`     | 用户    | （据字段名）   | 编号         |     | 是   |     |
| `session_id`  | 会话编号  | （据字段名）   | 文本（≤128 字） |     | 是   |     |
| `action_type` | 动作类型  | （据字段名）   | 文本（≤64 字）  |     | 否   |     |
| `object_type` | 对象类型  | （据字段名）   | 文本（≤64 字）  |     | 否   |     |
| `object_id`   | 对象编号  | （据字段名）   | 编号         |     | 是   |     |
| `payload`     | 数据内容  | （据字段名）   | JSON       |     | 是   |     |
| `ip`          | IP 地址 | （据字段名）   | 文本（≤45 字）  |     | 是   |     |
| `ua`          | 浏览器标识 | （据字段名）   | 长文本        |     | 是   |     |
| `trace_id`    | 追踪号   | （据字段名）   | 文本（≤64 字）  |     | 是   |     |
| `prev_hash`   | 上一哈希  | （据字段名）   | 文本（≤64 字）  |     | 否   |     |
| `entry_hash`  | 条目哈希  | （据字段名）   | 文本（≤64 字）  |     | 否   |     |

### `editing_locks` 编辑锁

- **后端**：`editing_lock_models.py`、`collaboration.py`。
- **状态**：在用。

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段                | 中文名   | 说明                | 类型         | 主键  | 可空  | 外键       |
| ----------------- | ----- | ----------------- | ---------- | --- | --- | -------- |
| `id`              | 主键    | 通用字段，见文首          | 编号         | 是   |     |          |
| `resource_type`   | 资源类型  | （据字段名）            | 文本（≤50 字）  |     | 否   |          |
| `resource_id`     | 资源编号  | （据字段名）            | 文本（≤255 字） |     | 否   |          |
| `holder_id`       | 持有人编号 | 指向 `users`        | 编号         |     | 否   | users.id |
| `holder_name`     | 持有人名称 | （据字段名）            | 文本（≤255 字） |     | 是   |          |
| `acquired_at`     | 获取时间  | （据字段名）            | 时间         |     | 否   |          |
| `heartbeat_at`    | 心跳时间  | （据字段名）            | 时间         |     | 否   |          |
| `released_at`     | 解除时间  | （据字段名）            | 时间         |     | 是   |          |
| `client_instance` | 客户实例  | 客户端实例标识（多窗口编辑锁隔离） | 文本（≤64 字）  |     | 是   |          |
| `created_at`      | 创建时间  | 通用字段，见文首          | 时间         |     | 否   |          |
| `updated_at`      | 更新时间  | 通用字段，见文首          | 时间         |     | 否   |          |

### `ai_chat_session` AI 对话会话 / `ai_chat_message` 消息 / `ai_chat_runs` 执行记录

- **是什么**：AI 助手的会话与执行记录。
- **后端**：`ai_models.py`、`doc_chat_persistence.py`、`asset_blob_models.py`。
- **前端**：通过 AI 相关接口使用，页面待核实。
- **状态**：在用。

**字段**（共 17 个，来源 `database-tables-columns.md`）：

| 字段                  | 中文名    | 说明                                                             | 类型         | 主键  | 可空  | 外键          |
| ------------------- | ------ | -------------------------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`                | 主键     | 通用字段，见文首                                                       | 编号         | 是   |     |             |
| `project_id`        | 项目     | 通用字段，见文首                                                       | 编号         |     | 是   | projects.id |
| `session_type`      | 会话类型   | 取值：`general` / `contract` / `workpaper` 底稿 / `confirmation` 函证 | 枚举         |     | 否   |             |
| `title`             | 标题     | （据字段名）                                                         | 文本（≤200 字） |     | 是   |             |
| `user_id`           | 用户     | 指向 `users`                                                     | 编号         |     | 是   | users.id    |
| `session_key`       | 会话键    | 服务端规范化定位 hash；唯一真源 = ai_chat.persistence.build_session_key。    | 文本（≤64 字）  |     | 是   |             |
| `host_type`         | 宿主类型   | （据字段名）                                                         | 文本（≤32 字）  |     | 是   |             |
| `host_id`           | 宿主编号   | 全局知识模式使用 GLOBAL_KNOWLEDGE_HOST_ID sentinel，不用空字符串。             | 文本（≤128 字） |     | 是   |             |
| `audit_year`        | 审计年度   | （据字段名）                                                         | 整数         |     | 是   |             |
| `engine_preference` | 引擎偏好   | （据字段名）                                                         | 文本（≤32 字）  |     | 是   |             |
| `review_mode`       | 复核模式   | （据字段名）                                                         | 是 / 否      |     | 否   |             |
| `last_message_at`   | 最近消息时间 | （据字段名）                                                         | 时间         |     | 是   |             |
| `total_messages`    | 合计消息   | （据字段名）                                                         | 整数         |     | 否   |             |
| `total_tokens`      | 合计令牌数  | （据字段名）                                                         | 整数         |     | 否   |             |
| `context_summary`   | 上下文摘要  | （据字段名）                                                         | 长文本        |     | 是   |             |
| `created_at`        | 创建时间   | 通用字段，见文首                                                       | 时间         |     | 否   |             |
| `updated_at`        | 更新时间   | 通用字段，见文首                                                       | 时间         |     | 否   |             |

### `knowledge_documents` 知识库文档

- **后端**：`knowledge_models.py`，`migration_drift_ledger.py`。
- **状态**：在用。

**字段**（共 24 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名    | 说明                                                                                                                                                               | 类型         | 主键  | 可空  | 外键                   |
| --------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --- | --- | -------------------- |
| `id`                  | 主键     | 通用字段，见文首                                                                                                                                                         | 编号         | 是   |     |                      |
| `folder_id`           | 文件夹编号  | 指向 `knowledge_folders`                                                                                                                                           | 编号         |     | 否   | knowledge_folders.id |
| `name`                | 名称     | （据字段名）                                                                                                                                                           | 文本（≤500 字） |     | 否   |                      |
| `file_type`           | 文件类型   | pdf/docx/md/xlsx                                                                                                                                                 | 文本（≤20 字）  |     | 是   |                      |
| `file_size`           | 文件大小   | （据字段名）                                                                                                                                                           | 整数         |     | 否   |                      |
| `storage_path`        | 存储路径   | 文件存储路径                                                                                                                                                           | 长文本        |     | 是   |                      |
| `blob_id`             | 文件内容编号 | 指向 `asset_blobs`                                                                                                                                                 | 编号         |     | 是   | asset_blobs.id       |
| `content_text`        | 内容文本   | 内容（小文件直接存文本，大文件存路径）；文本内容（供 RAG 检索）                                                                                                                               | 长文本        |     | 是   |                      |
| `content_summary`     | 内容摘要   | 摘要                                                                                                                                                               | 长文本        |     | 是   |                      |
| `access_level`        | 访问级别   | 权限（继承文件夹权限，或单独设置）；None = 继承文件夹权限；取值：`public` 公开 / `project_group` 项目组 / `private` 民营                                                                             | 枚举         |     | 是   |                      |
| `project_ids`         | 项目列表   | （据字段名）                                                                                                                                                           | JSON       |     | 是   |                      |
| `tags`                | 标签     | 元数据；标签                                                                                                                                                           | JSON       |     | 是   |                      |
| `created_by`          | 创建人    | 通用字段，见文首                                                                                                                                                         | 编号         |     | 是   | users.id             |
| `created_at`          | 创建时间   | 通用字段，见文首                                                                                                                                                         | 时间         |     | 否   |                      |
| `updated_at`          | 更新时间   | 通用字段，见文首                                                                                                                                                         | 时间         |     | 否   |                      |
| `is_deleted`          | 是否已删除  | 通用字段，见文首                                                                                                                                                         | 是 / 否      |     | 否   |                      |
| `version`             | 版本号    | AT-3 KB 接入：版本管理                                                                                                                                                  | 整数         |     | 否   |                      |
| `previous_version_id` | 上一版本编号 | （据字段名）                                                                                                                                                           | 编号         |     | 是   |                      |
| `index_status`        | 序号状态   | 索引状态追踪                                                                                                                                                           | 文本（≤30 字）  |     | 是   |                      |
| `index_error`         | 序号错误   | （据字段名）                                                                                                                                                           | 长文本        |     | 是   |                      |
| `ocr_status`          | 识别状态   | ocr_status：None = 不需要 / 不适用；pending / running / done / empty / failed（取值见 KNOWLEDGE_OCR_STATUSES）。；ocr_due_at：pending 时 = 下次可尝试时间（退避）；running 时 = 租约到期（过期可被重新认领… | 文本（≤16 字）  |     | 是   |                      |
| `ocr_attempts`        | 识别尝试次数 | （据字段名）                                                                                                                                                           | 整数         |     | 否   |                      |
| `ocr_error`           | 识别错误   | （据字段名）                                                                                                                                                           | 长文本        |     | 是   |                      |
| `ocr_due_at`          | 识别到期时间 | （据字段名）                                                                                                                                                           | 时间         |     | 是   |                      |

## 九、冗余（25个）

| 表名                                                                                                                    | 是什么                           | 依据                                                                           |
| --------------------------------------------------------------------------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------- |
| `confirmation_letters`                                                                                                | 函证信登记                         | 仅定义处 1 次引用，无读写                                                               |
| `trial_balance_snapshots`                                                                                             | 试算表快照                         | 仅 1 处引用，疑似无写入                                                                |
| `ai_evidence_chains`                                                                                                  | AI 证据链                        | 仅被 `ai_evidence_items` 外键引用，无读写代码                                            |
| `confirmation_lists`                                                                                                  | 函证清单                          | 仅被外键引用，无读写代码                                                                 |
| `archive_checklists`                                                                                                  | 归档检查表                         | 仅定义处，无引用                                                                     |
| `archive_modifications`                                                                                               | 归档修改记录                        | 仅定义处，无引用                                                                     |
| `audit_procedures`                                                                                                    | 审计程序                          | 仅定义处，无引用（程序功能由 `checklist_responses` 等承担）                                    |
| `management_letters`                                                                                                  | 管理建议书                         | 仅定义处，无引用                                                                     |
| `project_sync`                                                                                                        | 项目同步                          | 仅定义处，无引用                                                                     |
| `se_checklist`                                                                                                        | SE 检查表                        | 仅定义处，无引用                                                                     |
| `sync_logs`                                                                                                           | 同步日志                          | 仅定义处，无引用                                                                     |
| `qc_inspection_records`                                                                                               | 质控检查记录                        | 仅定义处，无引用                                                                     |
| `wp_edit_sessions`                                                                                                    | 底稿编辑会话                        | 仅定义处，无引用                                                                     |
| `wp_recommendation_feedback`                                                                                          | 底稿推荐反馈                        | 仅定义处，无引用                                                                     |
| `risk_assessments` / `workpaper_review_records` / `custom_workbook_unit_authorities` / `procedure_template_revisions` | —                             | 仅测试使用，业务代码未引用                                                                |
| `budget_hours` / `risk_matrix_records`                                                                                | —                             | 仅前端字面量，无后端引用                                                                 |
| `ai_analysis_item` / `ai_evidence_items`                                                                              | AI 分析条目 / AI 证据项              | 无后端引用（`ai_evidence_items` 被上面的链表外键引用）                                        |
| `ai_chat_mcp_call_log` / `ai_chat_mcp_token_revocations` / `working_paper_oo_content_revision`                        | MCP 调用日志 / MCP 令牌撤销 / OO 内容修订 | 仅迁移中建表，没有 ORM 映射。`ai_chat_mcp_*` 在 `schema_drift_detector.py` 白名单中，注释说明是有意暂缓 |

> 注：以上清单来自第一轮静态扫描，个别结论（如 `ai_evidence_items` 是否真的无引用）在后续检查中有修正。删除任何表前，都要先查生产库是否有数据。

## 十、其余内部表

未在本文展开的约 300 张表，多为：

- 账套导入、公式、ACNR（地址坐标名称库）等内部配置或缓存表；
- AI 能力、证据治理、归档等后台表（只在后端使用，界面不可见）；
- 各循环底稿专用的 `gt_*` 数据表。

这些表的用途、外键关系见 `database-tables.md`（按业务域分组）和 `database-tables-columns.md`（字段明细）。如需逐张表展开，可以按业务域继续细化。

## 十一、疑似冗余表的字段

以下表在第九节列出，这里补充其字段（来源同上）。无 ORM 的表仅在迁移中建表，字段文档未收录。

### `ai_evidence_chains`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名   | 说明       | 类型        | 主键  | 可空  | 外键          |
| ------------------ | ----- | -------- | --------- | --- | --- | ----------- |
| `id`               | 主键    | 通用字段，见文首 | 编号        | 是   |     |             |
| `project_id`       | 项目    | 通用字段，见文首 | 编号        |     | 否   | projects.id |
| `chain_type`       | 链类型   | （据字段名）   | 文本        |     | 否   |             |
| `source_type`      | 来源类型  | （据字段名）   | 文本        |     | 是   |             |
| `source_id`        | 来源编号  | （据字段名）   | 编号        |     | 是   |             |
| `title`            | 标题    | （据字段名）   | 文本        |     | 否   |             |
| `description`      | 说明    | （据字段名）   | 长文本       |     | 是   |             |
| `confidence_score` | 置信度评分 | （据字段名）   | 金额（2 位小数） |     | 是   |             |
| `risk_level`       | 风险级别  | （据字段名）   | 文本        |     | 是   |             |
| `status`           | 状态    | （据字段名）   | 文本        |     | 否   |             |
| `is_deleted`       | 是否已删除 | 通用字段，见文首 | 是 / 否     |     | 否   |             |
| `created_at`       | 创建时间  | 通用字段，见文首 | 时间        |     | 否   |             |

### `confirmation_lists`

**字段**（共 19 个，来源 `database-tables-columns.md`）：

| 字段                     | 中文名    | 说明                                                                      | 类型         | 主键  | 可空  | 外键          |
| ---------------------- | ------ | ----------------------------------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`                   | 主键     | 通用字段，见文首                                                                | 编号         | 是   |     |             |
| `project_id`           | 项目     | 通用字段，见文首                                                                | 编号         |     | 否   | projects.id |
| `confirmation_type`    | 函证类型   | 取值：`bank` / `customer` / `vendor` / `lawyer` / `other` 其他               | 枚举         |     | 否   |             |
| `confirmation_code`    | 函证编码   | （据字段名）                                                                  | 文本（≤50 字）  |     | 否   |             |
| `counterparty_name`    | 对方单位名称 | （据字段名）                                                                  | 文本（≤200 字） |     | 否   |             |
| `counterparty_address` | 对方单位地址 | （据字段名）                                                                  | 长文本        |     | 是   |             |
| `contact_person`       | 联系人人   | （据字段名）                                                                  | 文本（≤100 字） |     | 是   |             |
| `contact_email`        | 联系人邮箱  | （据字段名）                                                                  | 文本（≤200 字） |     | 是   |             |
| `balance_or_amount`    | 余额或金额  | （据字段名）                                                                  | 金额（2 位小数）  |     | 是   |             |
| `as_of_date`           | 日期     | （据字段名）                                                                  | 日期         |     | 是   |             |
| `list_status`          | 列表状态   | 取值：`draft` 草稿 / `approved` 已通过 / `sent` 已发送 / `received` / `reconciled` | 枚举         |     | 否   |             |
| `approved_by`          | 批准人    | 指向 `users`                                                              | 编号         |     | 是   | users.id    |
| `approved_at`          | 批准时间   | （据字段名）                                                                  | 时间         |     | 是   |             |
| `sent_at`              | 发送时间   | （据字段名）                                                                  | 时间         |     | 是   |             |
| `due_date`             | 到期日期   | （据字段名）                                                                  | 日期         |     | 是   |             |
| `is_deleted`           | 是否已删除  | 通用字段，见文首                                                                | 是 / 否      |     | 否   |             |
| `created_at`           | 创建时间   | 通用字段，见文首                                                                | 时间         |     | 否   |             |
| `updated_at`           | 更新时间   | 通用字段，见文首                                                                | 时间         |     | 否   |             |
| `created_by`           | 创建人    | 通用字段，见文首                                                                | 编号         |     | 是   | users.id    |

### `archive_checklists`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名   | 说明                                             | 类型         | 主键  | 可空  | 外键          |
| -------------- | ----- | ---------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`           | 主键    | 通用字段，见文首                                       | 编号         | 是   |     |             |
| `project_id`   | 项目    | 通用字段，见文首                                       | 编号         |     | 否   | projects.id |
| `item_code`    | 项编码   | （据字段名）                                         | 文本（≤50 字）  |     | 否   |             |
| `item_name`    | 项名称   | （据字段名）                                         | 文本（≤200 字） |     | 否   |             |
| `category`     | 类别    | （据字段名）                                         | 文本（≤100 字） |     | 是   |             |
| `check_status` | 检查状态  | 取值：`pending` 待处理 / `pass_` / `fail` 不通过 / `na` | 枚举         |     | 否   |             |
| `checked_by`   | 检查人   | 指向 `users`                                     | 编号         |     | 是   | users.id    |
| `checked_at`   | 检查时间  | （据字段名）                                         | 时间         |     | 是   |             |
| `notes`        | 备注    | （据字段名）                                         | 长文本        |     | 是   |             |
| `is_deleted`   | 是否已删除 | 通用字段，见文首                                       | 是 / 否      |     | 否   |             |
| `created_at`   | 创建时间  | 通用字段，见文首                                       | 时间         |     | 否   |             |
| `updated_at`   | 更新时间  | 通用字段，见文首                                       | 时间         |     | 否   |             |

### `archive_modifications`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                  | 中文名   | 说明                                                 | 类型    | 主键  | 可空  | 外键          |
| ------------------- | ----- | -------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`                | 主键    | 通用字段，见文首                                           | 编号    | 是   |     |             |
| `project_id`        | 项目    | 通用字段，见文首                                           | 编号    |     | 否   | projects.id |
| `modification_type` | 修改类型  | 取值：`addition` / `deletion` / `replacement`         | 枚举    |     | 否   |             |
| `description`       | 说明    | （据字段名）                                             | 长文本   |     | 否   |             |
| `request_reason`    | 请求原因  | （据字段名）                                             | 长文本   |     | 是   |             |
| `approval_status`   | 审批状态  | 取值：`pending` 待处理 / `approved` 已通过 / `rejected` 已驳回 | 枚举    |     | 否   |             |
| `approved_by`       | 批准人   | 指向 `users`                                         | 编号    |     | 是   | users.id    |
| `approved_at`       | 批准时间  | （据字段名）                                             | 时间    |     | 是   |             |
| `is_deleted`        | 是否已删除 | 通用字段，见文首                                           | 是 / 否 |     | 否   |             |
| `created_at`        | 创建时间  | 通用字段，见文首                                           | 时间    |     | 否   |             |
| `updated_at`        | 更新时间  | 通用字段，见文首                                           | 时间    |     | 否   |             |
| `created_by`        | 创建人   | 通用字段，见文首                                           | 编号    |     | 是   | users.id    |

### `audit_procedures`

**字段**（共 17 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名    | 说明                                                                                | 类型         | 主键  | 可空  | 外键          |
| ------------------ | ------ | --------------------------------------------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`               | 主键     | 通用字段，见文首                                                                          | 编号         | 是   |     |             |
| `project_id`       | 项目     | 通用字段，见文首                                                                          | 编号         |     | 否   | projects.id |
| `procedure_code`   | 程序编码   | （据字段名）                                                                            | 文本（≤50 字）  |     | 否   |             |
| `procedure_name`   | 程序名称   | （据字段名）                                                                            | 文本（≤200 字） |     | 否   |             |
| `procedure_type`   | 程序类型   | 取值：`risk_assessment` 风险评估 / `control_test` 控制测试 / `substantive` 实质性程序             | 枚举         |     | 否   |             |
| `audit_cycle`      | 审计循环   | （据字段名）                                                                            | 文本（≤100 字） |     | 是   |             |
| `account_code`     | 科目编码   | （据字段名）                                                                            | 文本（≤50 字）  |     | 是   |             |
| `description`      | 说明     | （据字段名）                                                                            | 长文本        |     | 是   |             |
| `execution_status` | 执行状态   | 取值：`not_started` 未开始 / `in_progress` 进行中 / `completed` 已完成 / `not_applicable` 不适用 | 枚举         |     | 否   |             |
| `executed_by`      | 执行人    | 指向 `users`                                                                        | 编号         |     | 是   | users.id    |
| `executed_at`      | 执行时间   | （据字段名）                                                                            | 日期         |     | 是   |             |
| `conclusion`       | 结论     | （据字段名）                                                                            | 长文本        |     | 是   |             |
| `related_wp_code`  | 相关底稿编码 | （据字段名）                                                                            | 文本（≤50 字）  |     | 是   |             |
| `related_risk_id`  | 相关风险编号 | （据字段名）                                                                            | 编号         |     | 是   |             |
| `is_deleted`       | 是否已删除  | 通用字段，见文首                                                                          | 是 / 否      |     | 否   |             |
| `created_at`       | 创建时间   | 通用字段，见文首                                                                          | 时间         |     | 否   |             |
| `updated_at`       | 更新时间   | 通用字段，见文首                                                                          | 时间         |     | 否   |             |

### `management_letters`

**字段**（共 18 个，来源 `database-tables-columns.md`）：

| 字段                           | 中文名      | 说明                                                                          | 类型         | 主键  | 可空  | 外键          |
| ---------------------------- | -------- | --------------------------------------------------------------------------- | ---------- | --- | --- | ----------- |
| `id`                         | 主键       | 通用字段，见文首                                                                    | 编号         | 是   |     |             |
| `project_id`                 | 项目       | 通用字段，见文首                                                                    | 编号         |     | 否   | projects.id |
| `letter_code`                | 函件编码     | （据字段名）                                                                      | 文本（≤50 字）  |     | 否   |             |
| `issue_number`               | 问题编号     | （据字段名）                                                                      | 整数         |     | 否   |             |
| `issue_type`                 | 问题类型     | 取值：`control_deficiency` / `process_improvement` / `compliance` / `other` 其他 | 枚举         |     | 否   |             |
| `issue_title`                | 问题标题     | （据字段名）                                                                      | 文本（≤200 字） |     | 否   |             |
| `issue_description`          | 问题说明     | （据字段名）                                                                      | 长文本        |     | 是   |             |
| `recommendation`             | 推荐       | （据字段名）                                                                      | 长文本        |     | 是   |             |
| `management_response`        | 管理回复     | （据字段名）                                                                      | 长文本        |     | 是   |             |
| `response_by`                | 回复人      | （据字段名）                                                                      | 文本（≤100 字） |     | 是   |             |
| `response_date`              | 回复日期     | （据字段名）                                                                      | 日期         |     | 是   |             |
| `follow_up_status`           | 跟进状态     | 取值：`open` 未处理 / `in_progress` 进行中 / `resolved` 已解决 / `accepted_risk`        | 枚举         |     | 否   |             |
| `prior_year_item_id`         | 上期年度项编号  | （据字段名）                                                                      | 编号         |     | 是   |             |
| `is_prior_year_carryforward` | 是否上期年度结转 | （据字段名）                                                                      | 是 / 否      |     | 否   |             |
| `is_deleted`                 | 是否已删除    | 通用字段，见文首                                                                    | 是 / 否      |     | 否   |             |
| `created_at`                 | 创建时间     | 通用字段，见文首                                                                    | 时间         |     | 否   |             |
| `updated_at`                 | 更新时间     | 通用字段，见文首                                                                    | 时间         |     | 否   |             |
| `created_by`                 | 创建人      | 通用字段，见文首                                                                    | 编号         |     | 是   | users.id    |

### `project_sync`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段               | 中文名    | 说明                                                      | 类型    | 主键  | 可空  | 外键          |
| ---------------- | ------ | ------------------------------------------------------- | ----- | --- | --- | ----------- |
| `id`             | 主键     | 通用字段，见文首                                                | 编号    | 是   |     |             |
| `project_id`     | 项目     | 通用字段，见文首                                                | 编号    |     | 否   | projects.id |
| `global_version` | 全局版本   | （据字段名）                                                  | 整数    |     | 否   |             |
| `sync_status`    | 同步状态   | 取值：`IDLE` / `SYNCING` / `SYNCED` / `CONFLICT` / `ERROR` | 枚举    |     | 否   |             |
| `is_locked`      | 是否锁定   | （据字段名）                                                  | 是 / 否 |     | 否   |             |
| `locked_by`      | 锁定人    | 指向 `users`                                              | 编号    |     | 是   | users.id    |
| `locked_at`      | 锁定时间   | （据字段名）                                                  | 时间    |     | 是   |             |
| `last_synced_at` | 最近同步时间 | （据字段名）                                                  | 时间    |     | 是   |             |
| `last_synced_by` | 最近同步人  | 指向 `users`                                              | 编号    |     | 是   | users.id    |
| `is_deleted`     | 是否已删除  | 通用字段，见文首                                                | 是 / 否 |     | 否   |             |
| `created_at`     | 创建时间   | 通用字段，见文首                                                | 时间    |     | 否   |             |
| `updated_at`     | 更新时间   | 通用字段，见文首                                                | 时间    |     | 否   |             |

### `se_checklist`

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名   | 说明         | 类型        | 主键  | 可空  | 外键          |
| -------------- | ----- | ---------- | --------- | --- | --- | ----------- |
| `id`           | 主键    | 通用字段，见文首   | 编号        | 是   |     |             |
| `project_id`   | 项目    | 通用字段，见文首   | 编号        |     | 否   | projects.id |
| `item_code`    | 项编码   | （据字段名）     | 文本（≤50 字） |     | 是   |             |
| `description`  | 说明    | （据字段名）     | 长文本       |     | 否   |             |
| `is_completed` | 是否完成  | （据字段名）     | 是 / 否     |     | 否   |             |
| `completed_at` | 完成时间  | （据字段名）     | 时间        |     | 是   |             |
| `completed_by` | 完成人   | 指向 `users` | 编号        |     | 是   | users.id    |
| `notes`        | 备注    | （据字段名）     | 长文本       |     | 是   |             |
| `is_deleted`   | 是否已删除 | 通用字段，见文首   | 是 / 否     |     | 否   |             |
| `created_at`   | 创建时间  | 通用字段，见文首   | 时间        |     | 否   |             |
| `updated_at`   | 更新时间  | 通用字段，见文首   | 时间        |     | 否   |             |

### `sync_logs`

**字段**（共 9 个，来源 `database-tables-columns.md`）：

| 字段               | 中文名   | 说明                                                                                         | 类型    | 主键  | 可空  | 外键          |
| ---------------- | ----- | ------------------------------------------------------------------------------------------ | ----- | --- | --- | ----------- |
| `id`             | 主键    | 通用字段，见文首                                                                                   | 编号    | 是   |     |             |
| `project_id`     | 项目    | 通用字段，见文首                                                                                   | 编号    |     | 否   | projects.id |
| `user_id`        | 用户    | 指向 `users`                                                                                 | 编号    |     | 否   | users.id    |
| `sync_type`      | 同步类型  | 取值：`UPLOAD` / `DOWNLOAD` / `CONFLICT_RESOLUTION` / `LOCK` / `UNLOCK` / `EXPORT` / `IMPORT` | 枚举    |     | 否   |             |
| `version_before` | 版本之前  | （据字段名）                                                                                     | 整数    |     | 是   |             |
| `version_after`  | 版本之后  | （据字段名）                                                                                     | 整数    |     | 是   |             |
| `details`        | 明细    | （据字段名）                                                                                     | JSON  |     | 是   |             |
| `is_deleted`     | 是否已删除 | 通用字段，见文首                                                                                   | 是 / 否 |     | 否   |             |
| `created_at`     | 创建时间  | 通用字段，见文首                                                                                   | 时间    |     | 否   |             |

### `qc_inspection_records`

**字段**（共 8 个，来源 `database-tables-columns.md`）：

| 字段                   | 中文名   | 说明                                               | 类型        | 主键  | 可空  | 外键                     |
| -------------------- | ----- | ------------------------------------------------ | --------- | --- | --- | ---------------------- |
| `id`                 | 主键    | 通用字段，见文首                                         | 编号        | 是   |     |                        |
| `inspection_item_id` | 检查项编号 | 指向 `qc_inspection_items`                         | 编号        |     | 否   | qc_inspection_items.id |
| `comment`            | 意见    | （据字段名）                                           | 长文本       |     | 否   |                        |
| `severity`           | 严重程度  | '`blocking` 阻断' \| '`warning` 警告' \| '`info` 提示' | 文本（≤20 字） |     | 否   |                        |
| `cell_ref`           | 单元格引用 | 单元格引用，如 'E5'                                     | 文本（≤20 字） |     | 是   |                        |
| `created_by`         | 创建人   | 通用字段，见文首                                         | 编号        |     | 否   |                        |
| `created_at`         | 创建时间  | 通用字段，见文首                                         | 时间        |     | 否   |                        |
| `updated_at`         | 更新时间  | 通用字段，见文首                                         | 时间        |     | 否   |                        |

### `wp_edit_sessions`

**字段**（共 7 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名  | 说明                 | 类型        | 主键  | 可空  | 外键               |
| ------------------ | ---- | ------------------ | --------- | --- | --- | ---------------- |
| `id`               | 主键   | 通用字段，见文首           | 编号        | 是   |     |                  |
| `wp_id`            | 底稿   | 指向 `working_paper` | 编号        |     | 否   | working_paper.id |
| `user_id`          | 用户   | 指向 `users`         | 编号        |     | 否   | users.id         |
| `started_at`       | 开始时间 | （据字段名）             | 时间        |     | 否   |                  |
| `ended_at`         |      | 未查明                | 时间        |     | 是   |                  |
| `duration_seconds` | 耗时秒  | （据字段名）             | 整数        |     | 是   |                  |
| `source`           | 来源   | （据字段名）             | 文本（≤30 字） |     | 否   |                  |

### `wp_recommendation_feedback`

**字段**（共 8 个，来源 `database-tables-columns.md`）：

| 字段             | 中文名  | 说明         | 类型         | 主键  | 可空  | 外键          |
| -------------- | ---- | ---------- | ---------- | --- | --- | ----------- |
| `id`           | 主键   | 通用字段，见文首   | 编号         | 是   |     |             |
| `project_id`   | 项目   | 通用字段，见文首   | 编号         |     | 否   | projects.id |
| `wp_code`      | 底稿编码 | （据字段名）     | 文本（≤50 字）  |     | 否   |             |
| `action`       | 动作   | （据字段名）     | 文本（≤30 字）  |     | 否   |             |
| `action_by`    | 动作人  | 指向 `users` | 编号         |     | 是   | users.id    |
| `action_at`    | 动作时间 | （据字段名）     | 时间         |     | 否   |             |
| `project_type` | 项目类型 | （据字段名）     | 文本（≤50 字）  |     | 是   |             |
| `industry`     | 行业   | （据字段名）     | 文本（≤100 字） |     | 是   |             |

### `risk_assessments`

**字段**（共 16 个，来源 `database-tables-columns.md`）：

| 字段                         | 中文名    | 说明                                                                                                                             | 类型         | 主键  | 可空  | 外键          |
| -------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------ | ---------- | --- | --- | ----------- |
| `id`                       | 主键     | 通用字段，见文首                                                                                                                       | 编号         | 是   |     |             |
| `project_id`               | 项目     | 通用字段，见文首                                                                                                                       | 编号         |     | 否   | projects.id |
| `assertion_level`          | 认定级别   | 取值：`existence` / `completeness` / `accuracy` / `cutoff` / `classification` / `occurrence` / `rights_obligations` / `valuation` | 枚举         |     | 否   |             |
| `account_or_cycle`         | 科目或循环  | （据字段名）                                                                                                                         | 文本（≤100 字） |     | 否   |             |
| `inherent_risk`            | 固有风险   | 取值：`high` 高 / `medium` 中 / `low` 低                                                                                             | 枚举         |     | 否   |             |
| `control_risk`             | 控制风险   | 取值：`high` 高 / `medium` 中 / `low` 低                                                                                             | 枚举         |     | 否   |             |
| `combined_risk`            | 合并后风险  | 取值：`high` 高 / `medium` 中 / `low` 低                                                                                             | 枚举         |     | 否   |             |
| `is_significant_risk`      | 是否重大风险 | （据字段名）                                                                                                                         | 是 / 否      |     | 否   |             |
| `risk_description`         | 风险说明   | （据字段名）                                                                                                                         | 长文本        |     | 是   |             |
| `response_strategy`        | 回复策略   | （据字段名）                                                                                                                         | 长文本        |     | 是   |             |
| `related_audit_procedures` | 相关审计程序 | （据字段名）                                                                                                                         | JSON       |     | 是   |             |
| `review_status`            | 复核状态   | 取值：`draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回                                                         | 枚举         |     | 否   |             |
| `is_deleted`               | 是否已删除  | 通用字段，见文首                                                                                                                       | 是 / 否      |     | 否   |             |
| `created_at`               | 创建时间   | 通用字段，见文首                                                                                                                       | 时间         |     | 否   |             |
| `updated_at`               | 更新时间   | 通用字段，见文首                                                                                                                       | 时间         |     | 否   |             |
| `created_by`               | 创建人    | 通用字段，见文首                                                                                                                       | 编号         |     | 是   | users.id    |

### `workpaper_review_records`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段               | 中文名   | 说明                                                                                                                                                                 | 类型         | 主键  | 可空  | 外键          |
| ---------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- | --- | --- | ----------- |
| `id`             | 主键    | 通用字段，见文首                                                                                                                                                           | 编号         | 是   |     |             |
| `project_id`     | 项目    | 通用字段，见文首                                                                                                                                                           | 编号         |     | 否   | projects.id |
| `workpaper_id`   | 底稿编号  | （据字段名）                                                                                                                                                             | 编号         |     | 否   |             |
| `workpaper_type` | 底稿类型  | （据字段名）                                                                                                                                                             | 文本（≤100 字） |     | 否   |             |
| `reviewer_id`    | 复核人编号 | 指向 `users`                                                                                                                                                         | 编号         |     | 否   | users.id    |
| `review_date`    | 复核日期  | （据字段名）                                                                                                                                                             | 时间         |     | 否   |             |
| `review_status`  | 复核状态  | 必须用同一个 ReviewStatus。原先映射 ApprovalStatus(pending/…) 时写入 pending 抛；InvalidTextRepresentation。；取值：`draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回 | 枚举         |     | 否   |             |
| `comments`       | 意见    | （据字段名）                                                                                                                                                             | 长文本        |     | 是   |             |
| `issues_found`   | 问题找到  | （据字段名）                                                                                                                                                             | 整数         |     | 否   |             |
| `is_deleted`     | 是否已删除 | 通用字段，见文首                                                                                                                                                           | 是 / 否      |     | 否   |             |
| `created_at`     | 创建时间  | 通用字段，见文首                                                                                                                                                           | 时间         |     | 否   |             |
| `updated_at`     | 更新时间  | 通用字段，见文首                                                                                                                                                           | 时间         |     | 否   |             |

### `custom_workbook_unit_authorities`

**字段**（共 7 个，来源 `database-tables-columns.md`）：

| 字段                 | 中文名          | 说明                 | 类型        | 主键  | 可空  | 外键               |
| ------------------ | ------------ | ------------------ | --------- | --- | --- | ---------------- |
| `id`               | 主键           | 通用字段，见文首           | 编号        | 是   |     |                  |
| `working_paper_id` | 底稿           | 指向 `working_paper` | 编号        |     | 否   | working_paper.id |
| `workbook_sha256`  | 工作簿SHA256 哈希 | （据字段名）             | 文本（≤64 字） |     | 否   |                  |
| `manifest`         | 清单           | （据字段名）             | JSON      |     | 否   |                  |
| `manifest_digest`  | 清单摘要哈希       | （据字段名）             | 文本（≤64 字） |     | 否   |                  |
| `created_by`       | 创建人          | 通用字段，见文首           | 编号        |     | 否   | users.id         |
| `created_at`       | 创建时间         | 通用字段，见文首           | 时间        |     | 否   |                  |

### `procedure_template_revisions`

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段                         | 中文名     | 说明         | 类型        | 主键  | 可空  | 外键       |
| -------------------------- | ------- | ---------- | --------- | --- | --- | -------- |
| `id`                       | 主键      | 通用字段，见文首   | 编号        | 是   |     |          |
| `template_code`            | 模板编码    | （据字段名）     | 文本（≤80 字） |     | 否   |          |
| `revision_hash`            | 修订号哈希   | （据字段名）     | 文本（≤64 字） |     | 否   |          |
| `status`                   | 状态      | （据字段名）     | 文本（≤24 字） |     | 否   |          |
| `is_current`               | 是否当前    | （据字段名）     | 是 / 否     |     | 否   |          |
| `supersedes_revision_hash` | 替代修订号哈希 | （据字段名）     | 文本（≤64 字） |     | 是   |          |
| `activated_at`             | 生效时间    | （据字段名）     | 时间        |     | 是   |          |
| `activated_by`             | 生效人     | 指向 `users` | 编号        |     | 是   | users.id |
| `reconcile_detail`         | 核对明细    | （据字段名）     | JSON      |     | 否   |          |
| `created_at`               | 创建时间    | 通用字段，见文首   | 时间        |     | 否   |          |
| `updated_at`               | 更新时间    | 通用字段，见文首   | 时间        |     | 否   |          |

### `budget_hours`

**字段**（共 8 个，来源 `database-tables-columns.md`）：

| 字段              | 中文名   | 说明       | 类型         | 主键  | 可空  | 外键          |
| --------------- | ----- | -------- | ---------- | --- | --- | ----------- |
| `id`            | 主键    | 通用字段，见文首 | 编号         | 是   |     |             |
| `project_id`    | 项目    | 通用字段，见文首 | 编号         |     | 否   | projects.id |
| `phase`         | 阶段    | （据字段名）   | 文本（≤100 字） |     | 否   |             |
| `planned_hours` | 计划工时  | （据字段名）   | 金额（2 位小数）  |     | 否   |             |
| `actual_hours`  | 实际工时  | （据字段名）   | 金额（2 位小数）  |     | 否   |             |
| `is_deleted`    | 是否已删除 | 通用字段，见文首 | 是 / 否      |     | 否   |             |
| `created_at`    | 创建时间  | 通用字段，见文首 | 时间         |     | 否   |             |
| `updated_at`    | 更新时间  | 通用字段，见文首 | 时间         |     | 否   |             |

### `risk_matrix_records`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段                    | 中文名     | 说明                                 | 类型    | 主键  | 可空  | 外键          |
| --------------------- | ------- | ---------------------------------- | ----- | --- | --- | ----------- |
| `id`                  | 主键      | 通用字段，见文首                           | 编号    | 是   |     |             |
| `project_id`          | 项目      | 通用字段，见文首                           | 编号    |     | 否   | projects.id |
| `inherent_risk`       | 固有风险    | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举    |     | 否   |             |
| `control_risk`        | 控制风险    | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举    |     | 否   |             |
| `combined_risk`       | 合并后风险   | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举    |     | 否   |             |
| `inherent_risk_score` | 固有风险评分  | （据字段名）                             | 整数    |     | 否   |             |
| `control_risk_score`  | 控制风险评分  | （据字段名）                             | 整数    |     | 否   |             |
| `combined_risk_score` | 合并后风险评分 | （据字段名）                             | 整数    |     | 否   |             |
| `mitigation_notes`    |         | 未查明                                | 长文本   |     | 是   |             |
| `is_deleted`          | 是否已删除   | 通用字段，见文首                           | 是 / 否 |     | 否   |             |
| `created_at`          | 创建时间    | 通用字段，见文首                           | 时间    |     | 否   |             |
| `updated_at`          | 更新时间    | 通用字段，见文首                           | 时间    |     | 否   |             |

### `ai_analysis_item`

**字段**（共 11 个，来源 `database-tables-columns.md`）：

| 字段                  | 中文名   | 说明                                                                                                                                                 | 类型        | 主键  | 可空  | 外键                    |
| ------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | --- | --- | --------------------- |
| `id`                | 主键    | 通用字段，见文首                                                                                                                                           | 编号        | 是   |     |                       |
| `report_id`         | 报表编号  | 指向 `ai_analysis_report`                                                                                                                            | 编号        |     | 否   | ai_analysis_report.id |
| `clause_type`       | 条款类型  | 取值：`amount` / `payment_terms` / `delivery_terms` / `penalty` / `guarantee` / `pledge` / `related_party` / `special_terms` / `pricing` / `duration` | 枚举        |     | 是   |                       |
| `clause_text`       | 条款文本  | （据字段名）                                                                                                                                             | 长文本       |     | 否   |                       |
| `extraction_result` | 提取结果  | （据字段名）                                                                                                                                             | JSON      |     | 是   |                       |
| `risk_flag`         | 风险标记  | （据字段名）                                                                                                                                             | 是 / 否     |     | 否   |                       |
| `risk_reason`       | 风险原因  | （据字段名）                                                                                                                                             | 长文本       |     | 是   |                       |
| `confidence_score`  | 置信度评分 | （据字段名）                                                                                                                                             | 金额（2 位小数） |     | 是   |                       |
| `human_confirmed`   | 人工确认  | （据字段名）                                                                                                                                             | 是 / 否     |     | 否   |                       |
| `human_note`        | 人工附注  | （据字段名）                                                                                                                                             | 长文本       |     | 是   |                       |
| `created_at`        | 创建时间  | 通用字段，见文首                                                                                                                                           | 时间        |     | 否   |                       |

### `ai_evidence_items`

**字段**（共 12 个，来源 `database-tables-columns.md`）：

| 字段              | 中文名   | 说明                      | 类型        | 主键  | 可空  | 外键                    |
| --------------- | ----- | ----------------------- | --------- | --- | --- | --------------------- |
| `id`            | 主键    | 通用字段，见文首                | 编号        | 是   |     |                       |
| `chain_id`      | 链编号   | 指向 `ai_evidence_chains` | 编号        |     | 否   | ai_evidence_chains.id |
| `evidence_type` | 证据类型  | （据字段名）                  | 文本        |     | 否   |                       |
| `document_id`   | 文档编号  | （据字段名）                  | 编号        |     | 是   |                       |
| `document_name` | 文档名称  | （据字段名）                  | 文本        |     | 是   |                       |
| `field_path`    | 字段路径  | （据字段名）                  | 文本        |     | 是   |                       |
| `field_value`   | 字段值   | （据字段名）                  | 长文本       |     | 是   |                       |
| `page_number`   | 页编号   | （据字段名）                  | 整数        |     | 是   |                       |
| `description`   | 说明    | （据字段名）                  | 长文本       |     | 是   |                       |
| `confidence`    | 置信度   | （据字段名）                  | 金额（2 位小数） |     | 是   |                       |
| `is_deleted`    | 是否已删除 | 通用字段，见文首                | 是 / 否     |     | 否   |                       |
| `created_at`    | 创建时间  | 通用字段，见文首                | 时间        |     | 否   |                       |

### `ai_chat_mcp_call_log`

**字段**（来自建表迁移）：

来源 `V149__ai_chat_mcp_scoped_tokens.sql`，无 ORM 映射（已在 schema 漂移白名单中）。

| 字段             | 中文名    | 说明              | 类型         | 主键  | 可空  | 外键  |
| -------------- | ------ | --------------- | ---------- | --- | --- | --- |
| `id`           | 主键     | 记录编号            | 编号         | 是   | 否   |     |
| `run_id`       | 执行编号   | 所属 AI 执行        | 编号         |     | 否   |     |
| `tool_call_id` | 工具调用编号 | 本次工具调用的标识       | 文本（≤128 字） |     | 否   |     |
| `tool_name`    | 工具名称   | 被调用的工具          | 文本（≤64 字）  |     | 否   |     |
| `token_id`     | 令牌编号   | 使用的临时令牌         | 文本（≤32 字）  |     | 否   |     |
| `user_id`      | 用户编号   | 发起人             | 编号         |     | 否   |     |
| `project_id`   | 项目编号   | 所属项目            | 编号         |     | 否   |     |
| `status`       | 状态     | 调用状态，默认 started | 文本（≤20 字）  |     | 否   |     |
| `result_bytes` | 结果字节数  | 返回内容大小          | 整数         |     | 否   |     |
| `duration_ms`  | 耗时（毫秒） | 调用耗时            | 整数         |     | 否   |     |
| `error_code`   | 错误码    | 失败时的错误码         | 文本（≤64 字）  |     | 是   |     |
| `created_at`   | 创建时间   | 通用字段            | 时间         |     | 否   |     |

### `ai_chat_mcp_token_revocations`

**字段**（来自建表迁移）：

来源 `V149__ai_chat_mcp_scoped_tokens.sql`，无 ORM 映射。

| 字段           | 中文名  | 说明                    | 类型        | 主键  | 可空  | 外键  |
| ------------ | ---- | --------------------- | --------- | --- | --- | --- |
| `token_id`   | 令牌编号 | 被撤销的令牌（主键）            | 文本（≤32 字） | 是   | 否   |     |
| `run_id`     | 执行编号 | 所属 AI 执行              | 编号        |     | 否   |     |
| `user_id`    | 用户编号 | 令牌所属用户                | 编号        |     | 否   |     |
| `revoked_at` | 撤销时间 | 撤销的时间点                | 时间        |     | 否   |     |
| `reason`     | 撤销原因 | 默认 run_terminal（执行结束） | 文本（≤64 字） |     | 否   |     |

### `working_paper_oo_content_revision`

**字段**（来自建表迁移）：

来源 `V155__oo_content_revision.sql`，无 ORM 映射。

| 字段           | 中文名  | 说明                              | 类型         | 主键  | 可空  | 外键  |
| ------------ | ---- | ------------------------------- | ---------- | --- | --- | --- |
| `wp_id`      | 底稿编号 | 所属底稿（与 `entry_id` 组成主键）         | 编号         | 是   | 否   |     |
| `entry_id`   | 条目编号 | OnlyOffice 内容条目（与 `wp_id` 组成主键） | 文本（≤512 字） | 是   | 否   |     |
| `revision`   | 修订号  | 内容版本号，默认 0                      | 整数         |     | 否   |     |
| `reason`     | 修订原因 | 变更说明                            | 文本（≤128 字） |     | 是   |     |
| `updated_at` | 更新时间 | 通用字段                            | 时间         |     | 否   |     |
