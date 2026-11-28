# 数据表字段明细（带中文说明）

> 2026-11-20 重写：每个字段加了「中文名」和「说明」，类型改成中文。表的分组与概览见 `database-tables.md`。
> 主链 19 张核心表的字段说明经人工核对，更详细的取值说明见 `analysis/data-rules-inventory/appendix-f-field-dictionary.md`。

## 说明从哪来

| 标记 | 含义 |
|---|---|
| 无标记 | 人工核对过，或来自代码里紧挨着字段的注释、枚举定义 |
| （据字段名） | 代码里没有说明，按英文字段名翻译的，可能不准 |
| 未查明 | 字段名也看不出意思，需要再查代码 |

**每张表都有的字段**（各表不再重复解释）：`id` 主键；`project_id` 所属项目；`year` 年度；`is_deleted` / `deleted_at` 是否删除 / 删除时间（只打标记不真删）；`created_at` / `updated_at` 创建 / 更新时间（UTC，比北京时间晚 8 小时）；`created_by` / `updated_by` 创建人 / 修改人；`tenant_id` 多租户预留，恒为 `default`。

**金额正负号**：四张账表的借方、贷方按原文件存；余额、试算表、报表金额按「科目正常方向为正」存，资产费用借方为正、负债权益收入贷方为正，方向反了才是负数。

**类型**：编号 = 系统生成的唯一编号（UUID）；金额 = 保留 2 位小数；JSON = 一段结构化数据，里面可以放多个值；枚举 = 只能取固定几个值。

## 目录

- [U. 用户、组织与权限（10 张）](#u-group)
- [P. 项目、团队与工时（17 张）](#p-group)
- [D. 账套导入与四表数据（17 张）](#d-group)
- [T. 试算表、调整分录与重要性（19 张）](#t-group)
- [M. 审计计划与执行事项（17 张）](#m-group)
- [R. 审计程序、裁剪与委派（14 张）](#r-group)
- [W. 底稿与模板（33 张）](#w-group)
- [S. 底稿同步与在线编辑（33 张）](#s-group)
- [F. 公式、取数与校验（17 张）](#f-group)
- [N. 报表与附注（23 张）](#n-group)
- [C. 合并（32 张）](#c-group)
- [Q. 复核、质控、EQCR 与签发（27 张）](#q-group)
- [E. 附件、证据、OCR 与函证（45 张）](#e-group)
- [A. 交付件、导出与归档（14 张）](#a-group)
- [K. 知识库与编制指引（11 张）](#k-group)
- [I. AI（25 张）](#i-group)
- [X. 平台基础设施（事件、任务、日志、配置）（20 张）](#x-group)
- [附：只在迁移 SQL 中建的表](#附只在迁移-sql-中建的表)

<a id="u-group"></a>
## U. 用户、组织与权限

### `partner_rotation_overrides` 合伙人轮换 Override

模型：`rotation_models.PartnerRotationOverride`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `staff_id` | 人员 | 指向 `users` | 编号 |  | 否 | users.id |
| `client_name` | 客户名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `original_years` | 原始年数 | （据字段名） | 整数 |  | 否 |  |
| `override_reason` | 覆盖原因 | （据字段名） | 长文本 |  | 否 |  |
| `approved_by_compliance_partner` | 批准人合规合伙人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approved_by_chief_risk_partner` | 批准人首席风险合伙人 | 指向 `users` | 编号 |  | 是 | users.id |
| `override_expires_at` | 覆盖过期时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_creation_grants` admin 授予 manager 对一个精确 USCC 的项目创建权。

模型：`project_creation_grant_models.ProjectCreationGrant`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `grantee_user_id` | 被授权人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤18 字） |  | 否 |  |
| `valid_from` | 有效从 | （据字段名） | 时间 |  | 否 |  |
| `valid_until` | 有效截止 | （据字段名） | 时间 |  | 是 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `source` | 来源 | （据字段名） | 文本（≤48 字） |  | 否 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 否 |  |
| `granted_by` | 授予人 | 指向 `users` | 编号 |  | 是 | users.id |
| `revoked_by` | 吊销人 | 指向 `users` | 编号 |  | 是 | users.id |
| `revoked_at` | 吊销时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `service_identities` 系统作业主体（Service Identity）—— actor XOR 的 service 侧 FK 目标。

模型：`evidence_governance_models.ServiceIdentity`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `identity_key` | 身份键 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `display_name` | 显示名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `kind` | 类别 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sys_dept` 部门组织架构

模型：`core.Department`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | 部门名称（未软删范围内唯一） | 文本（≤100 字） |  | 否 |  |
| `parent_id` | 上级编号 | 父部门ID；指向 `sys_dept` | 编号 |  | 是 | sys_dept.id |
| `head_id` |  | 部门负责人，引用 users(id)；指向 `users` | 编号 |  | 是 | users.id |
| `sort_order` | 排序 | 排序顺序 | 整数 |  | 否 |  |
| `description` | 说明 | 部门描述 | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sys_role` 角色（数据权限维度）。

模型：`sys_permission.SysRole`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 整数 | 是 |  |  |
| `name` | 名称 | 角色名称 | 文本（≤100 字） |  | 否 |  |
| `role_key` | 角色键 | 角色标识，枚举角色与 UserRole 值一致 | 文本（≤100 字） |  | 否 |  |
| `data_scope` | 数据范围 | 数据权限范围：1=全部 2=自定义项目 6=我参与的项目 5=仅本人（3/4 已废弃） | 整数 |  | 否 |  |
| `status` | 状态 | 状态：0=正常 1=停用 | 文本（≤10 字） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sys_role_project` 角色-自定义项目多对多（仅 data_scope=2 使用）。

模型：`sys_permission.SysRoleProject`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `role_id` | 角色编号 | 角色 id；指向 `sys_role` | 整数 | 是 |  | sys_role.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 | 是 |  | projects.id |

### `sys_user_role` 账号-角色多对多绑定。

模型：`sys_permission.SysUserRole`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `user_id` | 用户 | 账号 id；指向 `users` | 编号 | 是 |  | users.id |
| `role_id` | 角色编号 | 角色 id；指向 `sys_role` | 整数 | 是 |  | sys_role.id |

### `temporary_grants` 临时授权记录

模型：`temporary_grant_models.TemporaryGrant`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `operation_code` | 操作编码 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `grantee` | 被授权人 | （据字段名） | 编号 |  | 否 |  |
| `approver` | 审批人 | （据字段名） | 编号 |  | 否 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 否 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `user_display_preferences` 账号级显示偏好（一对一，user_id 主键）。

模型：`user_display_preferences.UserDisplayPreferences`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `user_id` | 用户 | 指向 `users` | 编号 | 是 |  | users.id |
| `amount_unit_override` | 金额单位覆盖 | 金额单位覆盖：null = 跟随项目 | 文本（≤8 字） |  | 是 |  |
| `font_size` | 字体大小 | 显示字号：xs=11px, sm=12px, md=13px, lg=14px | 文本（≤4 字） |  | 否 |  |
| `show_zero` |  | 未查明 | 是 / 否 |  | 否 |  |
| `decimals` |  | 小数位 0~6 | 整数 |  | 否 |  |
| `negative_red` |  | 未查明 | 是 / 否 |  | 否 |  |
| `highlight_threshold` |  | 变动高亮阈值 0~1，NUMERIC(5,4) | 数值（4 位小数） |  | 否 |  |
| `density` |  | 表格密度 | 文本（≤16 字） |  | 否 |  |
| `grid_edit_mode` |  | 表格编辑方式 | 文本（≤16 字） |  | 否 |  |
| `fixed_columns` | 固定列 | （据字段名） | JSON |  | 否 |  |
| `revision` | 修订号 | 乐观锁版本号 | 整数 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `users` 系统用户

模型：`core.User`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `username` | 登录名 | （据字段名） | 文本（≤150 字） |  | 否 |  |
| `email` | 邮箱 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `hashed_password` | 密码（加密后） | 不存明文 | 文本（≤255 字） |  | 否 |  |
| `role` | 系统角色 | （据字段名） | 枚举 |  | 否 |  |
| `office_code` | 所属分所 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `is_active` | 是否启用 | 停用后不能登录 | 是 / 否 |  | 否 |  |
| `language` |  | 未查明 | 文本（≤10 字） |  | 否 |  |
| `full_name` | 全称名称 | 用户全名 | 文本（≤100 字） |  | 是 |  |
| `parent_partner_id` | 上级合伙人编号 | 所属合伙人ID；指向 `users` | 编号 |  | 是 | users.id |
| `dept_id` | 部门编号 | （据字段名） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

<a id="p-group"></a>
## P. 项目、团队与工时

### `budget_hours` 预算工时

模型：`collaboration_models.BudgetHours`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `phase` | 阶段 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `planned_hours` | 计划工时 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `actual_hours` | 实际工时 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `check_ins` 

模型：`phase10_models.CheckIn`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `staff_id` | 人员 | 指向 `staff_members` | 编号 |  | 否 | staff_members.id |
| `check_time` | 检查时间 | （据字段名） | 时间 |  | 否 |  |
| `latitude` | 纬度 | （据字段名） | 数值（7 位小数） |  | 是 |  |
| `longitude` | 经度 | （据字段名） | 数值（7 位小数） |  | 是 |  |
| `location_name` | 地点名称 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `check_type` | 检查类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `forum_comments` 

模型：`phase10_models.ForumComment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `post_id` | 帖子编号 | 指向 `forum_posts` | 编号 |  | 否 | forum_posts.id |
| `author_id` | 作者编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `content` | 内容 | （据字段名） | 长文本 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `forum_posts` 

模型：`phase10_models.ForumPost`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `author_id` | 作者编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `is_anonymous` | 是否匿名 | （据字段名） | 是 / 否 |  | 否 |  |
| `category` | 类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 否 |  |
| `like_count` | 点赞数量 | （据字段名） | 整数 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `handover_records` 人员交接记录

模型：`handover_models.HandoverRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `from_staff_id` | 从人员编号 | 交接双方；指向 `users` | 编号 |  | 否 | users.id |
| `to_staff_id` | 到人员编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `scope` | 范围 | 交接范围: all / by_project | 文本（≤20 字） |  | 否 |  |
| `project_ids` | 项目列表 | scope=by_project 时指定的项目 ID 列表 | JSON |  | 是 |  |
| `reason_code` | 原因编码 | 原因码: resignation / long_leave / rotation / other | 文本（≤30 字） |  | 否 |  |
| `reason_detail` | 原因明细 | 原因详情 | 长文本 |  | 是 |  |
| `effective_date` | 生效日期 | 交接生效日期 | 日期 |  | 否 |  |
| `workpapers_moved` | 底稿迁移 | （据字段名） | 整数 |  | 否 |  |
| `issues_moved` | 问题迁移 | （据字段名） | 整数 |  | 否 |  |
| `assignments_moved` | 委派迁移 | （据字段名） | 整数 |  | 否 |  |
| `executed_by` | 执行人 | 执行交接的操作人；指向 `users` | 编号 |  | 否 | users.id |
| `executed_at` | 执行时间 | 执行时间 | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `notifications` 系统通知

模型：`core.Notification`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `recipient_id` | 接收人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `message_type` | 消息类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 是 |  |
| `related_object_type` | 相关对象类型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `related_object_id` | 相关对象编号 | （据字段名） | 编号 |  | 是 |  |
| `is_read` | 是否已读 | （据字段名） | 是 / 否 |  | 否 |  |
| `read_at` | 已读时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `event_id` | 事件编号 | 聚合通知扩展（；additive-only：event_id+recipient_user_id 去重、dedup_key、metadata 驱动跳转（不解析中文 content）。 | 文本（≤128 字） |  | 是 |  |
| `recipient_user_id` | 接收人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `dedup_key` | 去重键 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `metadata` | 元数据 | （据字段名） | JSON |  | 是 |  |

### `project_assignments` 项目团队委派

模型：`staff_models.ProjectAssignment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `staff_id` | 人员 | 指向 `staff_members` | 编号 |  | 否 | staff_members.id |
| `role` | 角色 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `assigned_cycles` | 分配循环 | （据字段名） | JSON |  | 是 |  |
| `assigned_at` | 分配时间 | （据字段名） | 时间 |  | 是 |  |
| `assigned_by` | 分配人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_batch_import_plans` 一次上传产生的规范化计划、预览与可重放最终回执。

模型：`batch_project_models.ProjectBatchImportPlan`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `mode` | 模式 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 长文本 |  | 否 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `template_version` | 模板版本 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `rows` | 行 | （据字段名） | JSON |  | 否 |  |
| `tree_preview` | 树预览 | （据字段名） | JSON |  | 否 |  |
| `summary` | 摘要 | （据字段名） | JSON |  | 否 |  |
| `warnings` | 警告 | （据字段名） | JSON |  | 否 |  |
| `receipt` | 回执 | （据字段名） | JSON |  | 是 |  |
| `public_error` | 公开错误 | （据字段名） | 长文本 |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `applied_at` | 已应用时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_sync` 项目同步状态

模型：`collaboration_models.ProjectSync`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `global_version` | 全局版本 | （据字段名） | 整数 |  | 否 |  |
| `sync_status` | 同步状态 | 取值：`IDLE` / `SYNCING` / `SYNCED` / `CONFLICT` / `ERROR` | 枚举 |  | 否 |  |
| `is_locked` | 是否锁定 | （据字段名） | 是 / 否 |  | 否 |  |
| `locked_by` | 锁定人 | 指向 `users` | 编号 |  | 是 | users.id |
| `locked_at` | 锁定时间 | （据字段名） | 时间 |  | 是 |  |
| `last_synced_at` | 最近同步时间 | （据字段名） | 时间 |  | 是 |  |
| `last_synced_by` | 最近同步人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_timeline` 项目时间线/里程碑

模型：`collaboration_models.ProjectTimeline`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `milestone_type` | 里程碑类型 | 取值：`PLANNING` / `FIELDWORK` / `REVIEW` / `REPORT` / `COMPLETION` | 枚举 |  | 否 |  |
| `milestone_name` | 里程碑名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `planned_date` | 计划日期 | （据字段名） | 日期 |  | 是 |  |
| `actual_date` | 实际日期 | （据字段名） | 日期 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_users` 项目成员关联

模型：`core.ProjectUser`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `role` | 角色 | 取值：`partner` 合伙人 / `manager` 经理 / `auditor` 审计员 / `qc` 质控 / `eqcr` EQCR 复核人 / `readonly` 只读 | 枚举 |  | 否 |  |
| `permission_level` | 权限级别 | 取值：`edit` 编辑 / `review` 复核中 / `readonly` 只读 | 枚举 |  | 否 |  |
| `scope_cycles` | 范围循环 | （据字段名） | 长文本 |  | 是 |  |
| `scope_accounts` | 范围科目 | （据字段名） | 长文本 |  | 是 |  |
| `valid_from` | 有效从 | （据字段名） | 日期 |  | 是 |  |
| `valid_to` | 有效到 | （据字段名） | 日期 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `projects` 审计项目

模型：`core.Project`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 项目名称 | 如「陕西华氏医药有限公司_2026」 | 文本（≤255 字） |  | 否 |  |
| `client_name` | 被审计单位名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `audit_period_start` | 审计期间起 | （据字段名） | 日期 |  | 是 |  |
| `audit_period_end` | 审计期间止 | 审计年度取它的年份；为空时很多功能提示「未设置审计年度」 | 日期 |  | 是 |  |
| `project_type` | 项目类型 | 取值：`annual` 年报审计 / `special` 专项审计 / `ipo` IPO / `internal_control` 内控审计 / `capital_verification` 验资 / `tax_audit` 税务审计 / `enterprise_income_tax_settlement` 企业所得税汇算 | 枚举 |  | 是 |  |
| `materiality_level` | 重要性水平（旧字段） | 重要性现在以 `materiality` 表为准 | 小数 |  | 是 |  |
| `status` | 状态 | 取值：`created` 已创建 / `planning` 计划阶段 / `execution` 执行阶段 / `completion` 完成阶段 / `reporting` 报告阶段 / `archived` 已归档 | 枚举 |  | 否 |  |
| `manager_id` | 经理编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `partner_id` | 合伙人编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `version` | 版本号 | 每改一次加 1，防止两人同时改 | 整数 |  | 否 |  |
| `wizard_state` | 建项向导数据 | 建项向导各步填写的内容 | JSON |  | 是 |  |
| `accounting_standard_id` | 会计准则编号 | 指向 `accounting_standards` | 编号 |  | 是 | accounting_standards.id |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤50 字） |  | 是 |  |
| `short_name` | 简称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `company_subtype` | 企业子类型 | `type_a` / `type_b` / `type_c` / `type_d`，选审计报告模板用 | 文本（≤10 字） |  | 是 |  |
| `business_category` | 业务类别 | 质控业务分类码（A / A1~A8、B / B1~B6、C），NULL = 未填写；IPO / 再融资等是 scenario。；判定一律经 app.services.project_classification（不要按首字母 / 子串自行解释）。 | 文本（≤20 字） |  | 是 |  |
| `audit_type` | 审计类型 | 选复核底稿模板（A21~A25）用 | 文本（≤32 字） |  | 是 |  |
| `is_large_soe` | 是否大型国企 | （据字段名） | 是 / 否 |  | 否 |  |
| `audit_year` | 审计年度 | 审计年度（物化列，唯一性索引依赖） | 整数 |  | 是 |  |
| `template_type` | 报表模板类型 | `soe` 国企版 / `listed` 上市版；决定用哪套报表和附注模板 | 文本（≤20 字） |  | 是 |  |
| `report_scope` | 报表范围 | `standalone` 单体 / `consolidated` 合并 | 文本（≤20 字） |  | 是 |  |
| `parent_company_name` | 上级企业名称 | 合并企业树用 | 文本（≤255 字） |  | 是 |  |
| `parent_company_code` | 上级企业代码 | 合并企业树用 | 文本（≤50 字） |  | 是 |  |
| `ultimate_company_name` | 最终控制方名称 | 合并企业树用 | 文本（≤255 字） |  | 是 |  |
| `ultimate_company_code` | 最终控制方代码 | 合并企业树用 | 文本（≤50 字） |  | 是 |  |
| `relation_to_parent` | 与上级关系 | `subsidiary` 子公司（独立法人，合并时抵销）/ `branch` 分公司（并入母公司汇总）/ 空 = 未填 | 文本（≤20 字） |  | 是 |  |
| `parent_project_id` | 上级合并项目 | 系统按企业三码自动算出，不要手工改；指向 `projects` | 编号 |  | 是 | projects.id |
| `consol_level` | 合并层级 | （据字段名） | 整数 |  | 否 |  |
| `consolidation_type` | 合并方式（旧字段） | 已不再使用 | 文本（≤20 字） |  | 是 |  |
| `consol_lock` | 合并锁定 | 锁定后合并相关数据不能改 | 是 / 否 |  | 否 |  |
| `consol_lock_by` | 合并锁定人 | （据字段名） | 编号 |  | 是 | users.id |
| `consol_lock_at` | 合并锁定时间 | （据字段名） | 时间 |  | 是 |  |
| `archived_at` | 归档时间 | 归档时间（归档保留期起算，见归档规则） | 时间 |  | 是 |  |
| `retention_until` | 档案保留截止 | 归档后保留 10 年 | 时间 |  | 是 |  |
| `budget_hours` | 预算工时 | 项目预算工时 | 整数 |  | 是 |  |
| `contract_amount` | 合同金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `budgeted_by` | 预算设定人 | （据字段名） | 编号 |  | 是 | users.id |
| `budgeted_at` | 预算设定时间 | （据字段名） | 时间 |  | 是 |  |
| `risk_level` | 风险等级 | `high` 高 / `medium` 中 / `low` 低 | 文本（≤10 字） |  | 是 |  |
| `risk_level_updated_at` | 风险级别更新时间 | （据字段名） | 时间 |  | 是 |  |
| `scenario` | 场景 | 项目场景（用于裁剪程序，如标准/专项等） | 文本（≤20 字） |  | 否 |  |
| `has_foreign_currency` | 是否有外币业务 | （据字段名） | 是 / 否 |  | 否 |  |
| `prior_year_project_id` | 上年项目 | 上年同一单位的项目，取上年数用 | 编号 |  | 是 |  |
| `migration_note` | 迁移备注 | （据字段名） | 长文本 |  | 是 |  |
| `applicable_standard_v2` | 适用准则第二版 | 结构化统一准则状态源（单一真理源）；{entity_type: "soe"\|"listed"\|"private", scope: "standalone"\|"consolidated"；stage: "normal"\|"ipo"\|"transfer"\|"restructure"\|"fraud_response"} | JSON |  | 是 |  |
| `review_config` | 复核配置 | 复核链配置: {"levels":2\|3\|4,"level_roles":{"L1":"manager","L2":"partner",...}} | JSON |  | 是 |  |
| `budget_config` | 预算配置 | 工时预算配置: {"by_cycle":{"D":100,"E":80,...},"by_user":{"user_id":160,...},"total":800} | JSON |  | 是 |  |
| `amount_unit` | 金额单位 | 金额单位：元 / 千元 / 万元三选一，默认元；正式导出以此为准，「跟随项目」的显示偏好读此值 | 文本（≤8 字） |  | 否 |  |
| `current_audit_phase` | 当前审计阶段 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `interim_cutoff_date` | 预审截止日期 | 预审截止日 | 日期 |  | 是 |  |
| `acnr_registry_version` | 地址库注册表版本 | 锁定的 ACNR 地址目录版本号（14 位 UTC 时间戳）；NULL = 未锁定，按当前目录解析 | 文本（≤14 字） |  | 是 |  |
| `acnr_registry_locked_at` | 地址库注册表锁定时间 | ACNR 目录版本锁定时间；与 acnr_registry_version 同写同清 | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `staff_members` 全局人员库

模型：`staff_models.StaffMember`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 是 | users.id |
| `name` | 名称 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `employee_no` | 员工编号 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `department` | 部门 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `title` | 标题 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `partner_name` | 合伙人名称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `partner_id` | 合伙人编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `specialty` |  | 未查明 | 文本（≤200 字） |  | 是 |  |
| `phone` | 电话 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `email` | 邮箱 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `join_date` |  | 未查明 | 日期 |  | 是 |  |
| `resume_data` |  | 未查明 | JSON |  | 是 |  |
| `source` | 来源 | `seed` 系统预置 / `custom` 自定义 | 文本（≤20 字） |  | 否 |  |
| `role_level` | 角色级别 | 费率等级: partner/manager/senior/auditor/intern | 文本（≤20 字） |  | 是 |  |
| `is_cpa` | 是否注册会计师 | 是否注册会计师 | 是 / 否 |  | 是 |  |
| `cpa_cert_no` |  | CPA执业证书号 | 文本（≤50 字） |  | 是 |  |
| `audit_years` | 审计年数 | 审计年限 | 整数 |  | 是 |  |
| `qualifications` |  | 专业资质列表 [CPA,CIA,CISA...] | JSON |  | 是 |  |
| `industry_experience` |  | 行业经验列表 [制造,金融,地产...] | JSON |  | 是 |  |
| `status` | 状态 | 人员状态: active/on_leave/resigned | 文本（≤20 字） |  | 否 |  |
| `avatar_url` |  | 头像图片URL | 文本（≤500 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sync_logs` 同步日志

模型：`collaboration_models.SyncLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `sync_type` | 同步类型 | 取值：`UPLOAD` / `DOWNLOAD` / `CONFLICT_RESOLUTION` / `LOCK` / `UNLOCK` / `EXPORT` / `IMPORT` | 枚举 |  | 否 |  |
| `version_before` | 版本之前 | （据字段名） | 整数 |  | 是 |  |
| `version_after` | 版本之后 | （据字段名） | 整数 |  | 是 |  |
| `details` | 明细 | （据字段名） | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `task_tree_nodes` 四级任务树节点：unit/account/workpaper/evidence

模型：`phase15_models.TaskTreeNode`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `node_level` | 节点级别 | `unit` 单位/`account` 科目/`workpaper` 底稿/`evidence` 证据 | 文本（≤16 字） |  | 否 |  |
| `parent_id` | 上级编号 | （据字段名） | 编号 |  | 是 |  |
| `ref_id` | 引用编号 | 关联业务对象ID | 编号 |  | 否 |  |
| `status` | 状态 | `pending` 待处理/`in_progress` 进行中/`blocked` 被阻止/`done` 完成 | 文本（≤16 字） |  | 否 |  |
| `assignee_id` | 处理人编号 | （据字段名） | 编号 |  | 是 |  |
| `due_at` | 到期时间 | （据字段名） | 时间 |  | 是 |  |
| `meta` | 元数据 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `work_hour_entries` 工时填报条目（三级粒度）

模型：`workhour_entry_models.WorkHourEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `date` | 日期 | （据字段名） | 日期 |  | 否 |  |
| `hours` | 工时 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `cycle` | 循环 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `procedure` | 程序 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 是 |  |
| `approved_by` | 批准人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |
| `rejected_reason` | 驳回原因 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `source` | 来源 | 工时自动采集+二次编辑扩展 | 文本（≤20 字） |  | 否 |  |
| `source_ref` | 来源引用 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `edit_history` |  | 未查明 | JSON |  | 是 |  |
| `activity_type` |  | 未查明 | 文本（≤30 字） |  | 是 |  |
| `time_slots` | 时间位置 | （据字段名） | JSON |  | 是 |  |

### `work_hours` 工时记录 — DEPRECATED: V117 迁移后由 work_hour_entries 替代。

模型：`staff_models.WorkHour`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `staff_id` | 人员 | 指向 `staff_members` | 编号 |  | 否 | staff_members.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `work_date` | 工作日期 | （据字段名） | 日期 |  | 否 |  |
| `hours` | 工时 | （据字段名） | 数值 |  | 否 |  |
| `start_time` | 起始时间 | （据字段名） | TIME WITHOUT TIME ZONE |  | 是 |  |
| `end_time` | 截止时间 | （据字段名） | TIME WITHOUT TIME ZONE |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `ai_suggested` | AI建议 | （据字段名） | 是 / 否 |  | 否 |  |
| `purpose` | 用途 | 工时用途分类（允许值：preparation\|review\|eqcr\|training\|admin） | 文本（≤20 字） |  | 是 |  |
| `rejected_reason` | 驳回原因 | 退回原因（rejected 状态时填写） | 长文本 |  | 是 |  |
| `approved_by` | 批准人 | 审批人；指向 `users` | 编号 |  | 是 | users.id |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="d-group"></a>
## D. 账套导入与四表数据

### `account_chart` 科目表（标准科目 + 客户科目）

模型：`audit_platform_models.AccountChart`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `account_code` | 科目编码 | （据字段名） | 文本 |  | 否 |  |
| `account_name` | 科目名称 | （据字段名） | 文本 |  | 否 |  |
| `direction` | 方向 | 取值：`debit` 借 / `credit` 贷 | 枚举 |  | 否 |  |
| `level` | 级次 | （据字段名） | 整数 |  | 否 |  |
| `category` | 类别 | 取值：`asset` 资产 / `liability` 负债 / `equity` 权益 / `revenue` 收入 / `expense` 费用 | 枚举 |  | 否 |  |
| `parent_code` | 上级编码 | （据字段名） | 文本 |  | 是 |  |
| `source` | 来源 | 取值：`standard` 标准科目 / `client` 客户科目 | 枚举 |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `account_mapping` 科目映射关系

模型：`audit_platform_models.AccountMapping`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `original_account_code` | 客户科目编码 | 余额表里的编码；如 `1122.01` | 文本 |  | 否 |  |
| `original_account_name` | 客户科目名称 | （据字段名） | 文本 |  | 是 |  |
| `standard_account_code` | 标准科目编码 | 映射到的标准科目；如 `1122` | 文本 |  | 否 |  |
| `mapping_type` | 映射方式 | 怎么建立的这条映射；`auto_exact` 自动精确（相似度 ≥0.92）/ `auto_fuzzy` 自动模糊 / `manual` 人工 | 枚举 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `activation_records` 激活/回滚操作留痕

模型：`dataset_models.ActivationRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）；指向 `ledger_datasets` | 编号 |  | 否 | ledger_datasets.id |
| `action` | 动作 | 取值：`activate` 生效 / `rollback` 回滚 / `force_unbind` 强制解绑 | 枚举 |  | 否 |  |
| `previous_dataset_id` | 上一账套版本编号 | 指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `performed_by` | 执行人 | 操作者与时间；指向 `users` | 编号 |  | 是 | users.id |
| `performed_at` | 执行时间 | （据字段名） | 时间 |  | 否 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `ip_address` | IP 地址地址 | 审计溯源扩展字段；用于"谁在什么时间、从哪里、花了多久激活哪个版本"的完整轨迹 | 文本（≤64 字） |  | 是 |  |
| `duration_ms` | 耗时毫秒 | （据字段名） | 整数 |  | 是 |  |
| `before_row_counts` | 之前行计数 | 记录激活/回滚前后的四表行数，防静默数据损失；形如 {"tb_balance": 827, "tb_ledger": 1147414, "tb_aux_balance": 127618, "tb_aux_ledger": 2732674} | JSON |  | 是 |  |
| `after_row_counts` | 之后行计数 | （据字段名） | JSON |  | 是 |  |

### `direction_override` 方向覆盖 overlay 表 — 用户确认/修正方向时记录，不改写原始四表导入行。

模型：`audit_platform_models.DirectionOverride`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 否 |  |
| `table_name` | 表名称 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `record_id` | 记录编号 | （据字段名） | 编号 |  | 否 |  |
| `original_direction` | 原始方向 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `override_direction` | 覆盖方向 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `override_reason` | 覆盖原因 | （据字段名） | 长文本 |  | 否 |  |
| `override_by` | 覆盖（关联记录） | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `override_at` | 覆盖时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `event_outbox_dlq` 事件广播死信队列（F45）。

模型：`dataset_models.EventOutboxDLQ`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `original_event_id` | 原始事件编号 | 指向 `import_event_outbox` | 编号 |  | 是 | import_event_outbox.id |
| `event_type` | 事件类型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `failure_reason` | 失败原因 | （据字段名） | 长文本 |  | 是 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `moved_to_dlq_at` | 迁移到死信时间 | （据字段名） | 时间 |  | 否 |  |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `resolved_by` | 解决人 | 指向 `users` | 编号 |  | 是 | users.id |

### `import_artifacts` 上传产物 — 平台级文件引用

模型：`dataset_models.ImportArtifact`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `upload_token` | 上传令牌 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | 取值：`active` 生效 / `expired` 已过期 / `consumed` 已使用 | 枚举 |  | 否 |  |
| `storage_uri` | 存储地址 | 存储信息；local:///path/to/bundle 或 s3://bucket/key | 长文本 |  | 否 |  |
| `checksum` | 校验和 | SHA256 | 文本（≤128 字） |  | 是 |  |
| `total_size_bytes` | 合计大小字节数 | （据字段名） | 整数 |  | 否 |  |
| `file_manifest` | 文件清单 | 文件清单 | JSON |  | 是 |  |
| `file_count` | 文件数量 | 治理 | 整数 |  | 否 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 是 |  |
| `retention_class` | 保留类 | archived ：10 年过期，元数据永久保留；legal_hold ：法定保留，永不删除；由 DatasetService.activate → compute_retention_class 联动决策（F53 /。 | 文本（≤20 字） |  | 否 |  |
| `retention_expires_at` | 保留过期时间 | （据字段名） | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `import_batches` 导入批次

模型：`audit_platform_models.ImportBatch`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `source_type` | 来源类型 | （据字段名） | 文本 |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 文本 |  | 否 |  |
| `data_type` | 数据类型 | （据字段名） | 文本 |  | 否 |  |
| `record_count` | 记录数量 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | 取值：`pending` 待处理 / `processing` 处理中 / `completed` 已完成 / `failed` 失败 / `rolled_back` 已回滚 | 枚举 |  | 否 |  |
| `validation_summary` | 校验摘要 | （据字段名） | JSON |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 是 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `import_column_mapping_history` 列映射历史记录（F52 / Sprint 8.34 扩展版）。

模型：`column_mapping_models.ImportColumnMappingHistory`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `software_fingerprint` | 软件指纹 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `table_type` | 表类型 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `column_mapping` | 列映射 | （据字段名） | JSON |  | 否 |  |
| `used_count` | 已用数量 | （据字段名） | 整数 |  | 否 |  |
| `last_used_at` | 最近已用时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `file_fingerprint` | 文件指纹 | 细粒度文件指纹（sha1(sheet_name + header[:20] + software_hint)）。；老数据 NULL；仅 detect 阶段新建记录时填。 | 文本（≤40 字） |  | 是 |  |
| `override_parent_id` | 覆盖上级编号 | 历史链父记录（保留覆盖溯源）。；ondelete="SET NULL" 让旧父记录删除时不触发级联删除整条链。；指向 `import_column_mapping_history` | 编号 |  | 是 | import_column_mapping_history.id |

### `import_event_consumptions` 事件消费幂等记录。

模型：`dataset_models.ImportEventConsumption`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `event_id` | 事件编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `handler_name` | 处理程序名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `consumed_at` | 已消费时间 | （据字段名） | 时间 |  | 否 |  |

### `import_event_outbox` 导入域事件 outbox。

模型：`dataset_models.ImportEventOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `status` | 状态 | 取值：`pending` 待处理 / `published` 已发布 / `failed` 失败 | 枚举 |  | 否 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `last_error` | 最近错误 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 是 |  |

### `import_jobs` 导入作业 — 关注任务执行过程

模型：`dataset_models.ImportJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `status` | 状态 | 取值：`pending` 待处理 / `queued` 排队中 / `running` 运行中 / `validating` 校验中 / `writing` 写入中 / `activating` 生效中 / `completed` 已完成 / `failed` 失败 / `canceled` 已取消 / `timed_out` 超时 / `interrupted` 已中断 | 枚举 |  | 否 |  |
| `artifact_id` | 产物编号 | 作业配置；指向 `import_artifacts` | 编号 |  | 是 | import_artifacts.id |
| `custom_mapping` | 自定义映射 | （据字段名） | JSON |  | 是 |  |
| `options` | 选项 | （据字段名） | JSON |  | 是 |  |
| `progress_pct` | 进度百分比 | 进度 | 整数 |  | 否 |  |
| `progress_message` | 进度消息 | （据字段名） | 长文本 |  | 是 |  |
| `current_phase` | 当前阶段 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `result_summary` | 结果摘要 | 结果 | JSON |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `retry_count` | 重试次数 | （据字段名） | 整数 |  | 否 |  |
| `max_retries` | 最大重试次数 | （据字段名） | 整数 |  | 否 |  |
| `heartbeat_at` | 心跳时间 | 心跳（durable job 用） | 时间 |  | 是 |  |
| `timeout_seconds` | 超时秒 | 默认 10 分钟超时 | 整数 |  | 否 |  |
| `version` | 版本号 | P1-Q1: 乐观锁版本号（防并发 cancel/retry 竞态）；每次 status/progress 更新时 +1，端点调用时传入预期版本号做 WHERE 守卫 | 整数 |  | 否 |  |
| `force_submit` | 强制提交 | detect 阶段若返回 EMPTY_LEDGER_WARNING / SUSPICIOUS_DATASET_SIZE，submit | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `cancel_requested` | 取消请求 | 跨 worker 取消信号 | 是 / 否 |  | 否 |  |
| `creator_chain` | 创建人链 | 接管链路记录；格式: [{"user_id": "A", "action": "create", "at": "..."}, ...] | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |

### `ledger_datasets` 业务级数据集版本

模型：`dataset_models.LedgerDataset`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 文本（≤64 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `status` | 版本状态 | 这个版本现在是否在用；`staged` 已写入未生效 / `active` 当前生效 / `superseded` 已被新版本替代 / `failed` 导入失败 / `rolled_back` 已回滚 | 枚举 |  | 否 |  |
| `source_type` | 来源 | 这个版本怎么来的；`import` 导入（默认）/ `migration` 迁移 / `rollback` 回滚 | 文本（≤50 字） |  | 否 |  |
| `source_summary` | 来源说明 | 导入了哪些文件、金额单位、追加导入时继承了哪几个月；JSON | JSON |  | 是 |  |
| `record_summary` | 行数统计 | 四张账表各写了多少行；例：`{"tb_balance": 435, "tb_ledger": 1681993, ...}` | JSON |  | 是 |  |
| `validation_summary` | 校验结果 | 导入校验发现几个问题、几个是拦截的；JSON | JSON |  | 是 |  |
| `job_id` | 导入任务 | 是哪一次导入任务产生的；指向导入任务表 | 编号 |  | 是 | import_jobs.id |
| `previous_dataset_id` | 上一版本 | 追加导入时基于哪个旧版本；指向本表 | 编号 |  | 是 | ledger_datasets.id |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `activated_by` | 生效人 | 谁、什么时候让它生效的 | 编号 |  | 是 | users.id |
| `activated_at` | 生效时间 | 谁、什么时候让它生效的 | 时间 |  | 是 |  |

### `ledger_import_attempts` 一次账套导入 attempt 的最小不可变合同与状态记录。

模型：`dataset_models.LedgerImportAttempt`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）；指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `base_dataset_id` | 基准账套版本编号 | 指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `base_unit_contract_digest` | 基准单位契约摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `upload_token` | 上传令牌 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | 取值：`building` / `sealed` / `activating` 生效中 / `activated` / `cleanup_pending` / `cleanup_done` | 枚举 |  | 否 |  |
| `current_phase` | 当前阶段 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `payload_style` | 数据样式 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `unit_confirmation` | 单位函证 | （据字段名） | JSON |  | 否 |  |
| `unit_contract_digest` | 单位契约摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `bundle_digest` | 包摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `failure_code` | 失败编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |

### `tb_aux_balance` 辅助余额表

模型：`audit_platform_models.TbAuxBalance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 文本（≤64 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `account_code` | 科目编码 | （据字段名） | 文本 |  | 否 |  |
| `account_name` | 科目名称 | （据字段名） | 文本 |  | 是 |  |
| `level` | 级次 | （据字段名） | 整数 |  | 是 |  |
| `aux_type` | 维度类型 | 按什么核算；客户 / 供应商 / 部门 / 银行账户 | 文本 |  | 否 |  |
| `aux_type_name` | 维度类型名称 | 文件里的原始叫法 | 文本 |  | 是 |  |
| `aux_code` | 维度编码 | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院 | 文本 |  | 是 |  |
| `aux_name` | 维度名称 | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院 | 文本 |  | 是 |  |
| `aux_dimensions_raw` | 原始维度串 | 文件里的原文，一行有多个维度时会拆成多行，每行都带这个原文；`客户:C001 鞍钢总医院;部门:D01 销售部` | 长文本 |  | 是 |  |
| `opening_balance` | 期初余额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `opening_debit` | 期初借方 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `opening_credit` | 期初贷方 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `opening_qty` | 期初数量 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `opening_fc` | 期初外币 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `debit_amount` | 借方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 贷方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `closing_balance` | 期末余额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `closing_debit` | 期末借方 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `closing_credit` | 期末贷方 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `currency_code` | 币种编码 | （据字段名） | 文本（≤3 字） |  | 否 |  |
| `raw_extra` | 原文件未映射列 | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}` | JSON |  | 是 |  |
| `import_batch_id` | 导入批次 | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches` | 编号 |  | 是 | import_batches.id |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `opening_direction` | 期初方向 | 符号约定方向字段 | 文本（≤10 字） |  | 是 |  |
| `opening_direction_source` | 期初方向来源 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `closing_direction` | 期末方向 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `closing_direction_source` | 期末方向来源 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `sign_convention_version` | 符号约定版本 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `sign_anomaly_flags` | 符号异常标记 | （据字段名） | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `accounting_period` | 会计期间 | （据字段名） | 整数 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `tb_aux_ledger` 辅助明细账 — 按 year 分区

模型：`audit_platform_models.TbAuxLedger`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 文本（≤64 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 | 是 |  |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `voucher_date` | 凭证日期 | （据字段名） | 日期 |  | 是 |  |
| `voucher_no` | 凭证编号 | （据字段名） | 文本 |  | 是 |  |
| `account_code` | 科目编码 | （据字段名） | 文本 |  | 否 |  |
| `account_name` | 科目名称 | （据字段名） | 文本 |  | 是 |  |
| `aux_type` | 维度类型 | 按什么核算；客户 / 供应商 / 部门 / 银行账户 | 文本 |  | 是 |  |
| `aux_type_name` | 维度类型名称 | 文件里的原始叫法 | 文本 |  | 是 |  |
| `aux_code` | 维度编码 | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院 | 文本 |  | 是 |  |
| `aux_name` | 维度名称 | 具体哪个客户、哪个部门；`C001` / 鞍钢集团公司总医院 | 文本 |  | 是 |  |
| `accounting_period` | 会计期间 | 会计月份 | 整数 |  | 是 |  |
| `voucher_type` | 凭证类型 | 凭证类型 | 文本（≤20 字） |  | 是 |  |
| `debit_amount` | 借方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 贷方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `debit_qty` | 借方数量 | 借方数量 | 数值（4 位小数） |  | 是 |  |
| `credit_qty` | 贷方数量 | 贷方数量 | 数值（4 位小数） |  | 是 |  |
| `debit_fc` | 借方外币 | 借方外币 | 金额（2 位小数） |  | 是 |  |
| `credit_fc` | 贷方外币 | 贷方外币 | 金额（2 位小数） |  | 是 |  |
| `summary` | 摘要 | （据字段名） | 长文本 |  | 是 |  |
| `preparer` |  | 未查明 | 文本 |  | 是 |  |
| `currency_code` | 币种编码 | （据字段名） | 文本（≤3 字） |  | 否 |  |
| `raw_extra` | 原文件未映射列 | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}` | JSON |  | 是 |  |
| `import_batch_id` | 导入批次 | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches` | 编号 |  | 是 | import_batches.id |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `entry_direction` | 条目方向 | 符号约定方向字段 | 文本（≤10 字） |  | 是 |  |
| `entry_direction_source` | 条目方向来源 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `aux_dimensions_raw` | 原始维度串 | 文件里的原文，一行有多个维度时会拆成多行，每行都带这个原文；`客户:C001 鞍钢总医院;部门:D01 销售部` | 长文本 |  | 是 |  |

### `tb_balance` 科目余额表

模型：`audit_platform_models.TbBalance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 文本（≤64 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `account_code` | 科目编码 | 客户原始编码，如 `1122.01`；文件「科目编码」列 | 文本 |  | 否 |  |
| `account_name` | 科目名称 | 如「应收账款_应收货款」；文件「科目名称」列 | 文本 |  | 是 |  |
| `level` | 科目级次 | 第几级科目；按编码长度推：去掉分隔符后 ≤4 位为 1 级，≤6 位 2 级，≤8 位 3 级，≤10 位 4 级，更长 5 级 | 整数 |  | 是 |  |
| `opening_balance` | 期初余额 | 按「正常方向为正」存；优先取文件的年初借/贷，其次期初借/贷，其次单列期初余额 | 金额（2 位小数） |  | 是 |  |
| `opening_debit` | 期初借方 | 文件里分列给出时的原值；原样 | 金额（2 位小数） |  | 是 |  |
| `opening_credit` | 期初贷方 | 文件里分列给出时的原值；原样 | 金额（2 位小数） |  | 是 |  |
| `opening_qty` | 期初数量 | 数量核算的科目才有 | 数值（4 位小数） |  | 是 |  |
| `opening_fc` | 期初外币金额 | 外币核算的科目才有 | 金额（2 位小数） |  | 是 |  |
| `debit_amount` | 本期借方发生额 | 优先取文件「本年累计」，没有才取「本期发生额」；原样，不改正负 | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 本期贷方发生额 | 优先取文件「本年累计」，没有才取「本期发生额」；原样，不改正负 | 金额（2 位小数） |  | 是 |  |
| `closing_balance` | 期末余额 | 按「正常方向为正」存；由期末借/贷或单列期末余额 + 方向列算出 | 金额（2 位小数） |  | 是 |  |
| `closing_debit` | 期末借方 | 文件分列给出时的原值；原样 | 金额（2 位小数） |  | 是 |  |
| `closing_credit` | 期末贷方 | 文件分列给出时的原值；原样 | 金额（2 位小数） |  | 是 |  |
| `currency_code` | 币种 | 文件没有就填 `CNY` | 文本（≤3 字） |  | 否 |  |
| `raw_extra` | 原文件未映射列 | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}` | JSON |  | 是 |  |
| `import_batch_id` | 导入批次 | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches` | 编号 |  | 是 | import_batches.id |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `opening_direction` | 期初余额方向 | 余额实际在借方还是贷方；`debit` 借 / `credit` 贷 | 文本（≤10 字） |  | 是 |  |
| `opening_direction_source` | 方向怎么判出来的 | `split_columns` 文件借贷分列、看哪边有数 / `explicit_direction` 文件有「方向」列 / `contra_account` 按备抵科目名称（累计折旧、坏账准备等）判 / `account_category_inferred` 按科目类别判 / `account_category_inferred_low_confidence` 科目名称为空、只能按编码判 | 文本（≤50 字） |  | 是 |  |
| `closing_direction` | 期末余额方向 | 余额实际在借方还是贷方；`debit` 借 / `credit` 贷 | 文本（≤10 字） |  | 是 |  |
| `closing_direction_source` | 方向怎么判出来的 | `split_columns` 文件借贷分列、看哪边有数 / `explicit_direction` 文件有「方向」列 / `contra_account` 按备抵科目名称（累计折旧、坏账准备等）判 / `account_category_inferred` 按科目类别判 / `account_category_inferred_low_confidence` 科目名称为空、只能按编码判 | 文本（≤50 字） |  | 是 |  |
| `sign_convention_version` | 符号口径版本 | 现在导入的都是 `v2_category_natural_positive`（正常方向为正）；为空的是老数据，存的是借正贷负 | 文本（≤30 字） |  | 是 |  |
| `sign_anomaly_flags` | 方向异常标记 | 余额方向和科目正常方向相反时记下来，例如负债出现借方余额；例：`{"normal_direction": "credit", "conflicts": [{"period": "closing", "actual_direction": "debit", "stored_amount": -100}]}`；正常时为空 | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `tb_ledger` 序时账（总账明细）— 按 year 分区

模型：`audit_platform_models.TbLedger`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 文本（≤64 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 | 是 |  |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `voucher_date` | 凭证日期 | 文件「记账日期 / 凭证日期」等列；为空的行不导入 | 日期 |  | 否 |  |
| `voucher_no` | 凭证号 | 为空的行不导入 | 文本 |  | 否 |  |
| `account_code` | 科目编码 | 客户原始科目 | 文本 |  | 否 |  |
| `account_name` | 科目名称 | 客户原始科目 | 文本 |  | 是 |  |
| `accounting_period` | 会计期间（月份） | 1~12；文件「期间」列；没有就取凭证日期的月份 | 整数 |  | 是 |  |
| `voucher_type` | 凭证字 | 记 / 收 / 付 / 转 等；原样 | 文本（≤20 字） |  | 是 |  |
| `entry_seq` | 分录序号 | 凭证内第几行；原样 | 整数 |  | 是 |  |
| `debit_amount` | 借方金额 | **该条分录**的金额；原样。注意不能映射成「借方合计 / 贷方合计」（那是整张凭证的合计），否则每行都会变成凭证总额 | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 贷方金额 | **该条分录**的金额；原样。注意不能映射成「借方合计 / 贷方合计」（那是整张凭证的合计），否则每行都会变成凭证总额 | 金额（2 位小数） |  | 是 |  |
| `debit_qty` | 借方数量 | 数量核算才有 | 数值（4 位小数） |  | 是 |  |
| `credit_qty` | 贷方数量 | 数量核算才有 | 数值（4 位小数） |  | 是 |  |
| `debit_fc` | 借方外币金额 | 外币核算才有 | 金额（2 位小数） |  | 是 |  |
| `credit_fc` | 贷方外币金额 | 外币核算才有 | 金额（2 位小数） |  | 是 |  |
| `counterpart_account` | 对方科目 | 原样 | 文本 |  | 是 |  |
| `summary` | 摘要 | 原样 | 长文本 |  | 是 |  |
| `preparer` | 制单人 | 原样 | 文本 |  | 是 |  |
| `currency_code` | 币种编码 | （据字段名） | 文本（≤3 字） |  | 否 |  |
| `raw_extra` | 原文件未映射列 | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}` | JSON |  | 是 |  |
| `import_batch_id` | 导入批次 | 写库时的内部批次号，排查问题用，业务上不用看；指向 `import_batches` | 编号 |  | 是 | import_batches.id |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `entry_direction` | 分录方向 | 这条分录记在借方还是贷方；`debit` / `credit`；文件有方向列用方向列，否则看借贷哪边有数 | 文本（≤10 字） |  | 是 |  |
| `entry_direction_source` | 方向怎么判出来的 | 同余额表 | 文本（≤50 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="t-group"></a>
## T. 试算表、调整分录与重要性

### `adjustment_client_bookings` 客户已入账的追加式标记/撤销历史。

模型：`adjustment_review_models.AdjustmentClientBooking`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 否 |  |
| `action` | 动作 | （据字段名） | 文本（≤12 字） |  | 否 |  |
| `sequence` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `voucher_keys` | 凭证键 | （据字段名） | JSON |  | 否 |  |
| `booked_dataset_id` | 已入账账套版本编号 | 指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_collaboration` 调整分录协作记录（分录组级转派→知晓→补充→确认）。

模型：`audit_platform_models.AdjustmentCollaboration`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 否 |  |
| `source_ref` | 来源引用 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `initiator_id` | 发起人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `assignee_id` | 处理人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `status` | 状态 | `pending` 待处理/`acknowledged` 已知悉/`contributed` 已补充/`confirmed` 已确认/`closed` 已关闭/`rejected` 已驳回 | 文本（≤20 字） |  | 否 |  |
| `round` | 轮次 | （据字段名） | 整数 |  | 否 |  |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `rejection_reason` | 驳回原因 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_collaboration_event` 协作历史事件（append-only，仅 INSERT）。

模型：`audit_platform_models.AdjustmentCollaborationEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `collaboration_id` | 协作编号 | 指向 `adjustment_collaboration` | 编号 |  | 否 | adjustment_collaboration.id |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `event_type` | 事件类型 | `assigned` 已分派/`reassigned` 已改派/`acknowledged` 已知悉/`contributed` 已补充/`confirmed` 已确认/`rejected` 已驳回/`commented` 已评论/`closed` 已关闭 | 文本（≤20 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_editing_locks` 

模型：`enterprise_linkage_models.AdjustmentEditingLock`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 否 |  |
| `locked_by` | 锁定人 | 指向 `users` | 编号 |  | 否 | users.id |
| `locked_by_name` | 锁定人名称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `acquired_at` | 获取时间 | （据字段名） | 时间 |  | 否 |  |
| `heartbeat_at` | 心跳时间 | （据字段名） | 时间 |  | 否 |  |
| `released_at` | 解除时间 | （据字段名） | 时间 |  | 是 |  |

### `adjustment_entries` 调整分录明细行（独立于 adjustments 头表）

模型：`audit_platform_models.AdjustmentEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `adjustment_id` | 所属分录 | 指向 `adjustments` | 编号 |  | 否 | adjustments.id |
| `entry_group_id` | 分录组 | 同上 | 编号 |  | 否 |  |
| `line_no` | 行号 | 分录内第几行 | 整数 |  | 否 |  |
| `standard_account_code` | 标准科目 | 汇总到试算表用的科目 | 文本 |  | 否 |  |
| `detail_account_code` | 明细科目 | 审计师选的明细科目，用于推送到底稿明细表；为空表示没有更细的明细 | 文本 |  | 是 |  |
| `account_name` | 科目名称 | （据字段名） | 文本 |  | 是 |  |
| `report_line_code` | 报表行 | 对应的报表行编码 | 文本 |  | 是 |  |
| `debit_amount` | 借方金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `credit_amount` | 贷方金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_import_batches` 

模型：`adjustment_import_models.AdjustmentImportBatch`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `mode` | 模式 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `summary` | 摘要 | （据字段名） | JSON |  | 否 |  |
| `uploaded_by` | 上传人 | 指向 `users` | 编号 |  | 否 | users.id |
| `parent_batch_id` | 上级批次编号 | 指向 `adjustment_import_batches` | 编号 |  | 是 | adjustment_import_batches.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |

### `adjustment_import_group_results` 

模型：`adjustment_import_models.AdjustmentImportGroupResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `batch_id` | 批次编号 | 指向 `adjustment_import_batches` | 编号 |  | 否 | adjustment_import_batches.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `group_key` | 组键 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `external_reference` | 外部引用 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `source_rows` | 来源行 | （据字段名） | JSON |  | 否 |  |
| `action` | 动作 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 是 |  |
| `error` | 错误 | （据字段名） | 长文本 |  | 是 |  |
| `warnings` | 警告 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_review_tasks` 一笔调整分录的一轮持久化复核任务。

模型：`adjustment_review_models.AdjustmentReviewTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `required_level` | 必填级别 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `group_content_revision` | 组内容修订号 | （据字段名） | 整数 |  | 否 |  |
| `assigned_reviewer_ids` | 分配复核人列表 | （据字段名） | JSON |  | 否 |  |
| `submitted_by` | 提交人 | 指向 `users` | 编号 |  | 否 | users.id |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 否 |  |
| `submit_note` | 提交附注 | （据字段名） | 长文本 |  | 是 |  |
| `decided_by` | 决定人 | 指向 `users` | 编号 |  | 是 | users.id |
| `decided_at` | 决定时间 | （据字段名） | 时间 |  | 是 |  |
| `decision_reason` | 决定原因 | （据字段名） | 长文本 |  | 是 |  |
| `self_review_override_reason` | 自身复核覆盖原因 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustment_treatment_events` 调整财务处理的追加式事件，不覆盖历史。

模型：`adjustment_review_models.AdjustmentTreatmentEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 否 |  |
| `sequence` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `action` | 动作 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`）；指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `voucher_keys` | 凭证键 | （据字段名） | JSON |  | 否 |  |
| `misstatement_id` | 错报编号 | 指向 `unadjusted_misstatements` | 编号 |  | 是 | unadjusted_misstatements.id |
| `client_booking_id` | 客户入账编号 | 指向 `adjustment_client_bookings` | 编号 |  | 是 | adjustment_client_bookings.id |
| `reverses_event_id` | 冲回事件编号 | 指向 `adjustment_treatment_events` | 编号 |  | 是 | adjustment_treatment_events.id |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `adjustments` 审计调整分录（AJE / RJE）

模型：`audit_platform_models.Adjustment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `adjustment_no` | 分录编号 | 如 `AJE-001`；手填或自动编号；同年度不能重复 | 文本 |  | 否 |  |
| `adjustment_type` | 分录类型 | `aje` 审计调整 / `rje` 重分类调整 | 枚举 |  | 否 |  |
| `description` | 摘要 | （据字段名） | 长文本 |  | 是 |  |
| `account_code` | 科目 | 这一行的科目 | 文本 |  | 否 |  |
| `account_name` | 科目 | 这一行的科目 | 文本 |  | 是 |  |
| `debit_amount` | 借方金额 | 一行只能填一边，不能为负 | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 贷方金额 | 一行只能填一边，不能为负 | 金额（2 位小数） |  | 是 |  |
| `entry_group_id` | 分录组 | 同一笔分录的各行共用这个编号 | 编号 |  | 否 |  |
| `content_revision` | 内容修订号 | 分录内容每改一次加 1，只改状态不加；防止两人同时改 | 整数 |  | 否 |  |
| `audit_phase` | 审计阶段 | 录入时项目处于哪个阶段；`preliminary` 预审 / `final` 年审（默认） | 文本（≤16 字） |  | 否 |  |
| `external_reference` | 外部编号 | 导入时文件里的编号 | 文本（≤120 字） |  | 是 |  |
| `import_batch_id` | 导入批次 | 从 Excel 导入的才有 | 编号 |  | 是 | adjustment_import_batches.id |
| `review_status` | 复核状态 | `draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回。**只有已通过的才进试算表** | 枚举 |  | 否 |  |
| `reviewer_id` | 复核人 | （据字段名） | 编号 |  | 是 | users.id |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `rejection_reason` | 驳回原因 | （据字段名） | 长文本 |  | 是 |  |
| `passed_reason` | 不予更正原因 | 客户不同意调整、作为未更正错报时填写 | 长文本 |  | 是 |  |
| `passed_communication_date` | 沟通日期 | 与管理层沟通未更正错报的日期 | 时间 |  | 是 |  |
| `origin` | 来源 | `manual` 手工录入（默认）/ `workpaper` 来自底稿。来自底稿的不再计入审计调整列，避免和底稿调整重复 | 文本（≤20 字） |  | 否 |  |
| `source_ref` | 来源底稿行 | 来自哪张底稿的哪一行；格式 `底稿id:行编号` | 文本（≤120 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `event_cascade_log` 

模型：`enterprise_linkage_models.EventCascadeLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `trigger_event` | 触发事件 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `trigger_payload` | 触发数据 | （据字段名） | JSON |  | 是 |  |
| `steps` | 步骤 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `total_duration_ms` | 合计耗时毫秒 | （据字段名） | 整数 |  | 是 |  |

### `materiality` 重要性水平

模型：`audit_platform_models.Materiality`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `benchmark_type` | 基准类型 | （据字段名） | 文本 |  | 否 |  |
| `benchmark_amount` | 基准金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `overall_percentage` | 整体百分比 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `overall_materiality` | 整体重要性 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `performance_ratio` | 执行比例 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `performance_materiality` | 执行重要性 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `trivial_ratio` | 明显微小比例 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `trivial_threshold` | 明显微小阈值 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `is_override` | 是否覆盖 | （据字段名） | 是 / 否 |  | 否 |  |
| `override_reason` | 覆盖原因 | （据字段名） | 长文本 |  | 是 |  |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `calculated_by` | 计算人 | 指向 `users` | 编号 |  | 是 | users.id |
| `calculated_at` | 计算时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `t_account_entries` T型账户分录

模型：`t_account_models.TAccountEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `t_account_id` |  | 指向 `t_accounts` | 编号 |  | 否 | t_accounts.id |
| `entry_type` | 条目类型 | `debit` 借 / `credit` 贷 | 文本（≤10 字） |  | 否 |  |
| `amount` | 金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `reference_id` | 引用编号 | （据字段名） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `debit_amount` | 借方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `credit_amount` | 贷方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `entry_date` | 条目日期 | （据字段名） | 日期 |  | 是 |  |
| `cfs_category` |  | 未查明 | 文本（≤50 字） |  | 是 |  |
| `counterpart_account` |  | 未查明 | 文本（≤100 字） |  | 是 |  |

### `t_accounts` T型账户

模型：`t_account_models.TAccount`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `account_code` | 科目编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `account_name` | 科目名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `account_type` | 科目类型 | `asset` 资产/`liability` 负债/`equity` 权益/`revenue` 收入/`expense` 费用 | 文本（≤50 字） |  | 否 |  |
| `opening_balance` | 期初余额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `tb_change_history` 

模型：`enterprise_linkage_models.TbChangeHistory`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `row_code` | 行编码 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `operation_type` | 操作类型 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `operator_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `operator_name` | 操作人名称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `delta_amount` | 差值金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `audited_after` | 审定之后 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `source_adjustment_id` | 来源调整编号 | （据字段名） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `tb_publish_ack` 审定表→试算表"发布"耐久确认/幂等表（对应迁移 V162）。

模型：`audit_platform_models.TbPublishAck`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `wp_code` | 底稿编码 | 从哪张审定表发布的 | 文本（≤32 字） |  | 否 |  |
| `publish_token` | 发布凭证 | 每次确认生成一个，重复提交时识别为同一次 | 文本（≤128 字） |  | 否 |  |
| `confirmed_by` | 确认人 | （据字段名） | 编号 |  | 是 |  |
| `accounts_updated` | 更新科目数 | 这次改了试算表几个科目 | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `trial_balance` 试算表（四列结构）

模型：`audit_platform_models.TrialBalance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `standard_account_code` | 标准科目编码 | 科目映射 | 文本 |  | 否 |  |
| `account_name` | 科目名称 | 余额表同编码名称，没有再取标准科目表 | 文本 |  | 是 |  |
| `account_category` | 科目类别 | `asset` 资产 / `liability` 负债 / `equity` 权益 / `revenue` 收入 / `expense` 费用 | 枚举 |  | 否 |  |
| `unadjusted_amount` | 未审数 | 客户账面数；余额表最明细科目按映射汇总；损益类取本期发生额（收入取贷方、费用取借方），不取期末 | 金额（2 位小数） |  | 是 |  |
| `rje_adjustment` | 重分类调整 | 已审批的重分类分录净额；同上 | 金额（2 位小数） |  | 否 |  |
| `aje_adjustment` | 审计调整 | 已审批的审计调整分录净额；调整分录汇总，按科目方向换算后的增减额 | 金额（2 位小数） |  | 否 |  |
| `audited_amount` | 审定数 | **未审数 + 审计调整 + 重分类调整 + 底稿调整** | 金额（2 位小数） |  | 是 |  |
| `wp_adjustment` | 底稿调整 | 从审定表「发布到试算表」带来的差额；只有在底稿里点发布并确认才写入；重导账表、重算调整时保留不清零 | 金额（2 位小数） |  | 否 |  |
| `wp_publish_base` | 发布基数 | 发布那一刻的基数，用来算底稿调整差额；精确含义未查明 | 金额（2 位小数） |  | 是 |  |
| `wp_published_at` | 最近发布时间 | 底稿最后一次发布到试算表的时间 | 时间 |  | 是 |  |
| `opening_balance` | 期初数 | 同上汇总；损益类为 0 | 金额（2 位小数） |  | 是 |  |
| `currency_code` | 币种 | 默认 `CNY` | 文本（≤3 字） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `trial_balance_snapshots` 试算平衡表版本快照 - 记录每次审定表变更时的试算表完整状态

模型：`workpaper_models.TrialBalanceSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `trigger` | 触发 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 是 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `snapshot_data` | 快照数据 | （据字段名） | JSON |  | 否 |  |
| `row_count` | 行数量 | （据字段名） | 整数 |  | 否 |  |
| `audited_total` | 审定合计 | （据字段名） | 数值 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `unadjusted_misstatements` 未更正错报汇总

模型：`audit_platform_models.UnadjustedMisstatement`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `source_adjustment_id` | 来源调整编号 | 指向 `adjustments` | 编号 |  | 是 | adjustments.id |
| `misstatement_description` | 错报说明 | （据字段名） | 长文本 |  | 否 |  |
| `affected_account_code` | 受影响科目编码 | （据字段名） | 文本 |  | 是 |  |
| `affected_account_name` | 受影响科目名称 | （据字段名） | 文本 |  | 是 |  |
| `misstatement_amount` | 错报金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `misstatement_type` | 错报类型 | 取值：`factual` / `judgmental` / `projected` | 枚举 |  | 否 |  |
| `management_reason` | 管理原因 | （据字段名） | 长文本 |  | 是 |  |
| `management_communication_at` |  | 未查明 | 时间 |  | 是 |  |
| `auditor_evaluation` | 审计师评价 | （据字段名） | 长文本 |  | 是 |  |
| `is_carried_forward` |  | 未查明 | 是 / 否 |  | 否 |  |
| `prior_year_id` | 上期年度编号 | 指向 `unadjusted_misstatements` | 编号 |  | 是 | unadjusted_misstatements.id |
| `prior_year_status` | 上期年度状态 | A13 聚合 - 上年结转状态 | 文本（≤20 字） |  | 否 |  |
| `source_wp_code` | 来源底稿编码 | A13 聚合 - 来源底稿编码 | 文本（≤20 字） |  | 是 |  |
| `source_identity` | 来源身份 | B3: durable 幂等键（底稿推送错报来源身份串，同项目唯一，软删除除外） | 文本（≤200 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `bound_dataset_id` | 绑定账套版本编号 | 下游快照绑定（创建时绑定当前 active dataset）；指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `dataset_bound_at` | 账套版本绑定时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

<a id="m-group"></a>
## M. 审计计划与执行事项

### `audit_findings` 

模型：`collaboration_models.AuditFinding`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `finding_code` | 发现编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `finding_description` | 发现说明 | （据字段名） | 长文本 |  | 是 |  |
| `severity` | 严重程度 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `affected_account` | 受影响科目 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `finding_amount` | 发现金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `management_response` | 管理回复 | （据字段名） | 长文本 |  | 是 |  |
| `final_treatment` | 最终处理方式 | 取值：`adjusted` 已调整 / `unadjusted` / `disclosed` / `no_action` | 枚举 |  | 是 |  |
| `related_adjustment_ids` | 相关调整列表 | （据字段名） | JSON |  | 是 |  |
| `related_wp_code` | 相关底稿编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `audit_plans` 

模型：`collaboration_models.AuditPlan`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `plan_version` | 计划版本 | （据字段名） | 整数 |  | 否 |  |
| `audit_strategy` | 审计策略 | （据字段名） | 长文本 |  | 是 |  |
| `planned_start_date` | 计划起始日期 | （据字段名） | 日期 |  | 是 |  |
| `planned_end_date` | 计划截止日期 | （据字段名） | 日期 |  | 是 |  |
| `key_focus_areas` | 键焦点领域 | （据字段名） | JSON |  | 是 |  |
| `team_assignment_summary` | 团队委派摘要 | （据字段名） | JSON |  | 是 |  |
| `materiality_reference` | 重要性引用 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | 取值：`draft` 草稿 / `approved` 已通过 / `revised` | 枚举 |  | 否 |  |
| `approved_by` | 批准人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `audit_procedures` 

模型：`collaboration_models.AuditProcedure`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `procedure_code` | 程序编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `procedure_name` | 程序名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `procedure_type` | 程序类型 | 取值：`risk_assessment` 风险评估 / `control_test` 控制测试 / `substantive` 实质性程序 | 枚举 |  | 否 |  |
| `audit_cycle` | 审计循环 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `account_code` | 科目编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `execution_status` | 执行状态 | 取值：`not_started` 未开始 / `in_progress` 进行中 / `completed` 已完成 / `not_applicable` 不适用 | 枚举 |  | 否 |  |
| `executed_by` | 执行人 | 指向 `users` | 编号 |  | 是 | users.id |
| `executed_at` | 执行时间 | （据字段名） | 日期 |  | 是 |  |
| `conclusion` | 结论 | （据字段名） | 长文本 |  | 是 |  |
| `related_wp_code` | 相关底稿编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `related_risk_id` | 相关风险编号 | （据字段名） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `going_concern_evaluations` 

模型：`collaboration_models.GoingConcernEvaluation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `evaluation_date` | 评价日期 | （据字段名） | 日期 |  | 否 |  |
| `conclusion` | 结论 | 取值：`no_material_uncertainty` / `material_uncertainty_disclosed` / `qualified` 保留意见 / `adverse` 否定意见 | 枚举 |  | 否 |  |
| `key_indicators` | 键迹象 | （据字段名） | JSON |  | 是 |  |
| `management_plan` | 管理计划 | （据字段名） | 长文本 |  | 是 |  |
| `auditor_conclusion` | 审计师结论 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `going_concern_indicators` 

模型：`collaboration_models.GoingConcernIndicator`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `evaluation_id` | 评价编号 | 指向 `going_concern_evaluations` | 编号 |  | 否 | going_concern_evaluations.id |
| `indicator_type` | 迹象类型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `indicator_value` | 迹象值 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `threshold` | 阈值 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `is_triggered` | 是否触发 | （据字段名） | 是 / 否 |  | 否 |  |
| `severity` | 严重程度 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `interim_survival_checks` 

模型：`audit_phase_models.InterimSurvivalCheck`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `working_paper_id` | 底稿 | （据字段名） | 编号 |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 否 |  |
| `total` | 合计 | （据字段名） | 整数 |  | 否 |  |
| `unchanged` | 未变 | （据字段名） | 整数 |  | 否 |  |
| `changed` | 变更 | （据字段名） | 整数 |  | 否 |  |
| `deleted` | 删除 | （据字段名） | 整数 |  | 否 |  |
| `renumbered` | 重编号 | （据字段名） | 整数 |  | 否 |  |
| `unacked` | 未确认 | 非「未变」且尚未逐行确认的行数 | 整数 |  | 否 |  |
| `checked_by` | 检查人 | （据字段名） | 编号 |  | 是 |  |
| `checked_at` | 检查时间 | （据字段名） | 时间 |  | 否 |  |

### `management_letters` 

模型：`collaboration_models.ManagementLetter`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `letter_code` | 函件编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `issue_number` | 问题编号 | （据字段名） | 整数 |  | 否 |  |
| `issue_type` | 问题类型 | 取值：`control_deficiency` / `process_improvement` / `compliance` / `other` 其他 | 枚举 |  | 否 |  |
| `issue_title` | 问题标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `issue_description` | 问题说明 | （据字段名） | 长文本 |  | 是 |  |
| `recommendation` | 推荐 | （据字段名） | 长文本 |  | 是 |  |
| `management_response` | 管理回复 | （据字段名） | 长文本 |  | 是 |  |
| `response_by` | 回复人 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `response_date` | 回复日期 | （据字段名） | 日期 |  | 是 |  |
| `follow_up_status` | 跟进状态 | 取值：`open` 未处理 / `in_progress` 进行中 / `resolved` 已解决 / `accepted_risk` | 枚举 |  | 否 |  |
| `prior_year_item_id` | 上期年度项编号 | （据字段名） | 编号 |  | 是 |  |
| `is_prior_year_carryforward` | 是否上期年度结转 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `pbc_checklist` PBC 清单项

模型：`collaboration_models.PBCChecklist`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `item_name` | 项名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `item_description` | 项说明 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | 取值：`PENDING` / `RECEIVED` / `REVIEWED` / `REJECTED` | 枚举 |  | 否 |  |
| `category` | 类别 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `cycle_code` | 循环编码 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `due_date` | 到期日期 | （据字段名） | 日期 |  | 是 |  |
| `requested_date` | 请求日期 | （据字段名） | 日期 |  | 是 |  |
| `received_date` | 收到日期 | （据字段名） | 日期 |  | 是 |  |
| `requested_by` | 请求人 | 指向 `users` | 编号 |  | 是 | users.id |
| `received_by` | 收到人 | 指向 `users` | 编号 |  | 是 | users.id |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `related_party_registry` 关联方主数据（项目级）。

模型：`related_party_models.RelatedPartyRegistry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `relation_type` | 关系类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `is_controlled_by_same_party` |  | 未查明 | 是 / 否 |  | 否 |  |
| `detail` | 明细 | 源模板 B19-1 描述性字段（企业类型/注册地/法人代表/业务性质/注册资本/持股比例%）；不参与各循环关联方核对（核对仅用 name），仅供披露与台账展示。 | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `related_party_transactions` 关联方交易明细。

模型：`related_party_models.RelatedPartyTransaction`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `related_party_id` | 相关方编号 | 指向 `related_party_registry` | 编号 |  | 否 | related_party_registry.id |
| `amount` | 金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `transaction_type` | 交易类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `is_arms_length` |  | 未查明 | 是 / 否 |  | 是 |  |
| `evidence_refs` | 证据引用 | （据字段名） | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `risk_assessments` 

模型：`collaboration_models.RiskAssessment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `assertion_level` | 认定级别 | 取值：`existence` / `completeness` / `accuracy` / `cutoff` / `classification` / `occurrence` / `rights_obligations` / `valuation` | 枚举 |  | 否 |  |
| `account_or_cycle` | 科目或循环 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `inherent_risk` | 固有风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `control_risk` | 控制风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `combined_risk` | 合并后风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `is_significant_risk` | 是否重大风险 | （据字段名） | 是 / 否 |  | 否 |  |
| `risk_description` | 风险说明 | （据字段名） | 长文本 |  | 是 |  |
| `response_strategy` | 回复策略 | （据字段名） | 长文本 |  | 是 |  |
| `related_audit_procedures` | 相关审计程序 | （据字段名） | JSON |  | 是 |  |
| `review_status` | 复核状态 | 取值：`draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回 | 枚举 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `risk_matrix_records` 

模型：`collaboration_models.RiskMatrixRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `inherent_risk` | 固有风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `control_risk` | 控制风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `combined_risk` | 合并后风险 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 否 |  |
| `inherent_risk_score` | 固有风险评分 | （据字段名） | 整数 |  | 否 |  |
| `control_risk_score` | 控制风险评分 | （据字段名） | 整数 |  | 否 |  |
| `combined_risk_score` | 合并后风险评分 | （据字段名） | 整数 |  | 否 |  |
| `mitigation_notes` |  | 未查明 | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sampled_vouchers` 抽样凭证（抽凭联动）

模型：`workpaper_models.SampledVoucher`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `voucher_no` | 凭证编号 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `voucher_date` | 凭证日期 | 单个凭证号最多对应 83 个不同日期；`(voucher_date, voucher_no)` 才唯一定位一张凭证；（该粒度下借贷 100% 平衡实证）。NULL = 历史行或未提供日期的手工标记，回拉分录时；退化为按年度匹配，可能命中同号别张凭证。 | 日期 |  | 是 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 是 |  |
| `voucher_type` | 凭证类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `phase` | 阶段 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `account_code` | 科目编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `sampling_record_id` | 抽样记录编号 | （据字段名） | 编号 |  | 是 |  |
| `working_paper_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `batch_id` | 批次编号 | 抽凭批次标识；NULL = 非抽凭引擎来源（如 ledger_penetration 穿透页手工标记）。；同批次同凭证由部分唯一索引 uq_sampled_vouchers_batch 防重；不同 batch_id 的；同一凭证**允许共存** —— 那正是「该凭证被抽过两次」这一需要被发现的事实。 | 编号 |  | 是 |  |
| `sampled_by` | 抽中人 | 指向 `users` | 编号 |  | 是 | users.id |
| `sampled_at` | 抽中时间 | （据字段名） | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sampling_config` 抽样配置

模型：`workpaper_models.SamplingConfig`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `config_name` | 配置名称 | （据字段名） | 文本 |  | 否 |  |
| `sampling_type` | 抽样类型 | 取值：`statistical` / `non_statistical` | 枚举 |  | 否 |  |
| `sampling_method` | 抽样方法 | 取值：`mus` / `attribute` / `random` / `systematic` / `stratified` | 枚举 |  | 否 |  |
| `applicable_scenario` | 适用场景 | 取值：`control_test` 控制测试 / `substantive_test` | 枚举 |  | 否 |  |
| `confidence_level` | 置信度级别 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `expected_deviation_rate` | 预期偏差比率 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `tolerable_deviation_rate` | 可容忍偏差比率 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `tolerable_misstatement` | 可容忍错报 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `population_amount` | 总体金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `population_count` | 总体数量 | （据字段名） | 整数 |  | 是 |  |
| `calculated_sample_size` | 计算样本大小 | （据字段名） | 整数 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `sampling_records` 抽样记录

模型：`workpaper_models.SamplingRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `sampling_config_id` | 抽样配置编号 | 指向 `sampling_config` | 编号 |  | 是 | sampling_config.id |
| `sampling_purpose` | 抽样用途 | （据字段名） | 长文本 |  | 否 |  |
| `population_description` | 总体说明 | （据字段名） | 长文本 |  | 否 |  |
| `population_total_amount` | 总体合计金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `population_total_count` | 总体合计数量 | （据字段名） | 整数 |  | 是 |  |
| `sample_size` | 样本大小 | （据字段名） | 整数 |  | 否 |  |
| `sampling_method_description` | 抽样方法说明 | （据字段名） | 长文本 |  | 是 |  |
| `deviations_found` |  | 未查明 | 整数 |  | 是 |  |
| `misstatements_found` | 错报找到 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `projected_misstatement` |  | 未查明 | 金额（2 位小数） |  | 是 |  |
| `upper_misstatement_limit` |  | 未查明 | 金额（2 位小数） |  | 是 |  |
| `conclusion` | 结论 | （据字段名） | 长文本 |  | 是 |  |
| `batch_id` | 批次编号 | 权威留痕仍是 workpaper_extraction_log.extraction_criteria；本表是可查询侧投影；支撑项目级/QC 级「所有抽样是否都有总体描述/样本量依据/结论」的一次性查询。 | 编号 |  | 是 |  |
| `sampling_method` | 抽样方法 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `random_seed` |  | 未查明 | 整数 |  | 是 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `se_checklist` 

模型：`collaboration_models.SEChecklist`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `item_code` | 项编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 否 |  |
| `is_completed` | 是否完成 | （据字段名） | 是 / 否 |  | 否 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_by` | 完成人 | 指向 `users` | 编号 |  | 是 | users.id |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `subsequent_events` 

模型：`collaboration_models.SubsequentEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `event_date` | 事件日期 | （据字段名） | 日期 |  | 否 |  |
| `event_type` | 事件类型 | 取值：`adjusting` / `non_adjusting` | 枚举 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `financial_impact` | 财务影响 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `adjustment_posted` |  | 未查明 | 是 / 否 |  | 否 |  |
| `audit_response` | 审计回复 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

<a id="r-group"></a>
## R. 审计程序、裁剪与委派

### `account_package_program_status` 科目工作包程序状态

模型：`account_package_models.AccountPackageProgramStatus`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `account_package_id` | 科目包编号 | 工作包 ID，如 D1_notes_receivable | 文本（≤100 字） |  | 否 |  |
| `program_code` | 程序表编码 | 程序编号，如 D1A, D1-12 | 文本（≤50 字） |  | 否 |  |
| `applicable` | 适用 | 是否适用 | 是 / 否 |  | 否 |  |
| `status` | 状态 | `pending` 待处理\|`in_progress` 进行中\|`completed` 已完成\|`reviewed` 已复核 | 文本（≤30 字） |  | 否 |  |
| `evidence` | 证据 | 审计证据描述 | 长文本 |  | 是 |  |
| `review_result` | 复核结果 | `pass` 通过\|`fail` 不通过\|`conditional` 有条件通过 | 文本（≤30 字） |  | 是 |  |
| `conclusion` | 结论 | 程序结论 | 长文本 |  | 是 |  |
| `not_applicable_reason` | 不适用原因 | 不适用理由（applicable=False 时必填） | 长文本 |  | 是 |  |
| `reviewer` | 复核人 | 复核人；指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `reviewed_at` | 复核时间 | 复核时间 | 时间 |  | 是 |  |
| `updated_by` | 修改（关联记录） | 通用字段，见文首 | 编号 |  | 是 | staff_members.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_instances` 审计程序实例（裁剪后的程序步骤）

模型：`procedure_models.ProcedureInstance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_cycle` | 审计循环 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `procedure_code` | 程序编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `procedure_name` | 程序名称 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `parent_id` | 上级编号 | 指向 `procedure_instances` | 编号 |  | 是 | procedure_instances.id |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `skip_reason` | 跳过原因 | （据字段名） | 长文本 |  | 是 |  |
| `is_custom` | 是否自定义 | （据字段名） | 是 / 否 |  | 否 |  |
| `assigned_to` | 分配到 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `assigned_at` | 分配时间 | （据字段名） | 时间 |  | 是 |  |
| `execution_status` | 执行状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `suggestion_state` | 建议状态 | 方案快照**（`裁剪方案-D-20260706` 等），键空间是 procedure_instance UUID；把「当前建议态」塞进历史快照语义错位。建议态跟着**程序实例**走。 | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_operation_previews` 敏感操作 server-side 一次性预览凭证（裁剪/委派/转派）。

模型：`procedure_models.ProcedureOperationPreview`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `operation` | 操作 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `request_payload_snapshot` | 请求数据快照 | （据字段名） | JSON |  | 否 |  |
| `target_versions` | 目标版本 | （据字段名） | JSON |  | 否 |  |
| `membership_snapshot` | 成员关系快照 | （据字段名） | JSON |  | 否 |  |
| `membership_snapshot_hash` | 成员关系快照哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `scheme_revision` | 方案修订号 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `consumed_at` | 已消费时间 | （据字段名） | 时间 |  | 是 |  |
| `consumed_request_id` | 已消费请求编号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `result` | 结果 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_row_definition_revisions` Revision membership: 哪些 definition_key 属于 (template_code, revision_hash)。

模型：`procedure_models.ProcedureRowDefinitionRevision`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_code` | 模板编码 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `revision_hash` | 修订号哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤160 字） |  | 否 |  |
| `definition_key` | 定义键 | 指向 `procedure_row_definitions` | 文本（≤200 字） |  | 否 | procedure_row_definitions.definition_key |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_row_definitions` 模板级程序行定义真源（跨项目稳定）。

模型：`procedure_models.ProcedureRowDefinition`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `definition_key` | 定义键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `template_code` | 模板编码 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `template_revision_hash` | 模板修订号哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤160 字） |  | 否 |  |
| `source_locator` | 来源定位 | （据字段名） | JSON |  | 否 |  |
| `program_no` | 程序表编号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `procedure_text` | 程序文本 | （据字段名） | 长文本 |  | 否 |  |
| `ref_snapshot` | 引用快照 | （据字段名） | JSON |  | 否 |  |
| `legacy_aliases` | 旧版别名 | （据字段名） | JSON |  | 否 |  |
| `normalized_content` | 规范化内容 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_row_task_history` 程序行任务追加式历史（不可覆盖）。

模型：`procedure_models.ProcedureRowTaskHistory`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `task_id` | 任务编号 | 指向 `procedure_row_tasks` | 编号 |  | 否 | procedure_row_tasks.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `event_type` | 事件类型 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `from_status` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_status` | 到状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `old_assignee_staff_id` | 旧处理人人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `new_assignee_staff_id` | 新处理人人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `old_reviewer_staff_id` | 旧复核人人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `new_reviewer_staff_id` | 新复核人人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `assignment_version` | 委派版本 | （据字段名） | 整数 |  | 否 |  |
| `lock_version` | 锁版本 | （据字段名） | 整数 |  | 否 |  |
| `definition_revision_hash` | 定义修订号哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `audit_cycle_snapshot` | 审计循环快照 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_row_tasks` 项目级程序行任务真源（先委派后生成底稿）。

模型：`procedure_models.ProcedureRowTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `definition_key` | 定义键 | 指向 `procedure_row_definitions` | 文本（≤200 字） |  | 否 | procedure_row_definitions.definition_key |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤160 字） |  | 否 |  |
| `wp_code` | 底稿编码 | 审计/展示快照 | 文本（≤80 字） |  | 是 |  |
| `sheet_name` | 表页名称 | （据字段名） | 文本（≤300 字） |  | 是 |  |
| `program_no` | 程序表编号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `procedure_text` | 程序文本 | （据字段名） | 长文本 |  | 是 |  |
| `ref_snapshot` | 引用快照 | （据字段名） | JSON |  | 否 |  |
| `definition_revision_hash` | 定义修订号哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `audit_cycle_snapshot` | 审计循环快照 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `applicability_status` | 适用性状态 | 适用性与独立状态机 | 文本（≤20 字） |  | 否 |  |
| `workflow_status` | 流程状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `assignee_staff_id` | 处理人人员编号 | 参与者；指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `reviewer_staff_id` | 复核人人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `assignment_version` | 委派版本 | 版本与并发 | 整数 |  | 否 |  |
| `lock_version` | 锁版本 | （据字段名） | 整数 |  | 否 |  |
| `due_at` | 到期时间 | SLA 时间戳 | 时间 |  | 是 |  |
| `assigned_at` | 分配时间 | （据字段名） | 时间 |  | 是 |  |
| `acknowledged_at` | 知悉时间 | （据字段名） | 时间 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 是 |  |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `cancelled_at` | 取消时间 | （据字段名） | 时间 |  | 是 |  |
| `execution_summary` | 执行摘要 | 提交材料 | 长文本 |  | 是 |  |
| `evidence_snapshot` | 证据快照 | （据字段名） | JSON |  | 否 |  |
| `migration_confidence` | 迁移置信度 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `migration_detail` | 迁移明细 | （据字段名） | JSON |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_template_revisions` Current-revision registry；每个 template_code 最多一个 active current。

模型：`procedure_models.ProcedureTemplateRevision`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_code` | 模板编码 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `revision_hash` | 修订号哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `is_current` | 是否当前 | （据字段名） | 是 / 否 |  | 否 |  |
| `supersedes_revision_hash` | 替代修订号哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `activated_at` | 生效时间 | （据字段名） | 时间 |  | 是 |  |
| `activated_by` | 生效人 | 指向 `users` | 编号 |  | 是 | users.id |
| `reconcile_detail` | 核对明细 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_trim_cycle_confirmations` 每项目每循环当前粗裁确认投影；历史真源仍是 consumed preview。

模型：`procedure_models.ProcedureTrimCycleConfirmation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `project_id` | 项目 | 通用字段，见文首 | 编号 | 是 |  | projects.id |
| `audit_cycle` | 审计循环 | （据字段名） | 文本（≤10 字） | 是 |  |  |
| `source_preview_id` | 来源预览编号 | 指向 `procedure_operation_previews` | 编号 |  | 否 | procedure_operation_previews.id |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 否 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 否 |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `cycle_revision_hash` | 循环修订号哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `revision_no` | 修订号编号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `procedure_trim_schemes` 审计程序裁剪方案

模型：`procedure_models.ProcedureTrimScheme`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_cycle` | 审计循环 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `scheme_name` | 方案名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `trim_data` | 裁剪数据 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_delegation_history` History_Set 唯一来源：append-only 委派历史快照。

模型：`wp_visibility_models.WorkpaperDelegationHistory`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `layer` | 层级 | 委派层与目标角色；'lead' \| 'row' | 文本（≤20 字） |  | 否 |  |
| `target_role` | 目标角色 | 'lead' \| 'assignee' \| 'reviewer' | 文本（≤20 字） |  | 否 |  |
| `action` | 动作 | 'assign' \| 'reassign' \| 'clear' | 文本（≤20 字） |  | 否 |  |
| `task_id` | 任务编号 | 指向 `procedure_row_tasks` | 编号 |  | 是 | procedure_row_tasks.id |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤160 字） |  | 是 |  |
| `old_user_id` | 旧用户编号 | 事件时身份快照（同一自然人 user+staff 均固定）；指向 `users` | 编号 |  | 是 | users.id |
| `new_user_id` | 新用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `old_staff_id` | 旧人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `new_staff_id` | 新人员编号 | 指向 `staff_members` | 编号 |  | 是 | staff_members.id |
| `actor_user_id` | 操作人用户编号 | 操作人与理由；指向 `users` | 编号 |  | 否 | users.id |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `scope_before` | 范围之前 | scope 快照（脱敏为 audit_cycle 列表） | JSON |  | 否 |  |
| `scope_after` | 范围之后 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_access_security_outbox` 内部安全审计发件箱（append-only）：保留真实拒绝原因，对外统一 404/429。

模型：`wp_visibility_models.WpAccessSecurityOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 是 | wp_index.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤160 字） |  | 是 |  |
| `requested_version` | 请求版本 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `entrypoint` |  | 入口与动作 | 文本（≤200 字） |  | 否 |  |
| `entry_family` |  | 未查明 | 文本（≤60 字） |  | 是 |  |
| `route_name` | 路由名称 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `http_method` |  | 未查明 | 文本（≤10 字） |  | 是 |  |
| `action` | 动作 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `reason` | 原因 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `delivery_state` | 投递状态 | enqueue 期投递元数据 | 文本（≤20 字） |  | 否 |  |
| `delivery_attempt` | 投递尝试 | （据字段名） | 整数 |  | 否 |  |
| `detail` | 明细 | 脱敏 detail | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_visibility_invalidation_outbox` 可见性失效发件箱（append-only）：与 policy epoch 递增同事务写入。

模型：`wp_visibility_models.WpVisibilityInvalidationOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `epoch` | 代次 | （据字段名） | 整数 |  | 否 |  |
| `change_type` | 变更类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `delivery_state` | 投递状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `delivery_attempt` | 投递尝试 | （据字段名） | 整数 |  | 否 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_visibility_policy_epoch` 每项目持久单调 policy epoch（可变；BEFORE UPDATE 触发器强制非递减）。

模型：`wp_visibility_models.WpVisibilityPolicyEpoch`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `project_id` | 项目 | 通用字段，见文首 | 编号 | 是 |  | projects.id |
| `epoch` | 代次 | （据字段名） | 整数 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="w-group"></a>
## W. 底稿与模板

### `aging_segments` 账龄段枚举配置（每个底稿一条，关联 wp_index_id）

模型：`aging_segment_model.AgingSegment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `preset` | 预设 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `segments` | 分段 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `bad_debt_detail_rows` 坏账准备明细表 D2-3 嵌套行（父行与子行统一存储）

模型：`bad_debt_models.BadDebtDetailRow`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `parent_row_id` | 上级行编号 | 指向 `bad_debt_detail_rows` | 编号 |  | 是 | bad_debt_detail_rows.id |
| `provision_method` | 准备方法 | 计提方法枚举(仅父行): INDIVIDUAL\|CREDIT_RISK_AGING\|CREDIT_RISK_OTHER\|OTHER | 文本（≤30 字） |  | 是 |  |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 否 |  |
| `row_label` | 行显示名 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `amount_b` |  | 期初未审数 | 金额（2 位小数） |  | 是 |  |
| `amount_c` |  | 期初账项调整 | 金额（2 位小数） |  | 是 |  |
| `amount_d` |  | 重分类调整(期初) | 金额（2 位小数） |  | 是 |  |
| `amount_e` |  | 期初审定数 | 金额（2 位小数） |  | 是 |  |
| `amount_f` |  | 本期计提 | 金额（2 位小数） |  | 是 |  |
| `amount_g` |  | 其他增加 | 金额（2 位小数） |  | 是 |  |
| `amount_h` |  | 本期转回 | 金额（2 位小数） |  | 是 |  |
| `amount_i` |  | 核销 | 金额（2 位小数） |  | 是 |  |
| `amount_j` |  | 其他减少 | 金额（2 位小数） |  | 是 |  |
| `amount_k` |  | 期末未审数 | 金额（2 位小数） |  | 是 |  |
| `amount_l` |  | 期末账项调整 | 金额（2 位小数） |  | 是 |  |
| `amount_m` |  | 重分类调整(期末) | 金额（2 位小数） |  | 是 |  |
| `amount_n` |  | 期末审定数 | 金额（2 位小数） |  | 是 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `cf_verification_results` CF 核查结果缓存 + 用户差异说明

模型：`cf_verification_models.CfVerificationResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `check_type` | 检查类型 | `cash_equivalents` 现金等价物/`reconciliation` 勾稽核对/`main_table` 主表/`supplementary` 补充资料 | 文本（≤50 字） |  | 否 |  |
| `item_code` | 项编码 | CFS-002 等 | 文本（≤20 字） |  | 是 |  |
| `reported_amount` | 报告金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `calculated_amount` | 计算金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `difference` | 差额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `pass` | 通过 | （据字段名） | 是 / 否 |  | 是 |  |
| `explanation` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `result_data` | 结果数据 | （据字段名） | JSON |  | 是 |  |
| `calculated_at` | 计算时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `custom_workbook_unit_authorities` 

模型：`custom_workbook_unit_authority.CustomWorkbookUnitAuthority`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `workbook_sha256` | 工作簿SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `manifest` | 清单 | （据字段名） | JSON |  | 否 |  |
| `manifest_digest` | 清单摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `draft_marker` 初稿标记（V100 formula-management-library）。

模型：`workpaper_models.DraftMarker`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `unit_scope` | 单位范围 | 数据单元定位（如 audit_sheet:{wp_id}:{cell} / report:{row_code}） | 文本（≤255 字） |  | 否 |  |
| `state` | 状态 | state ∈ {`draft` 草稿, `human_edited` 人工改过} | 文本（≤20 字） |  | 否 |  |
| `refresh_id` | 刷新编号 | 关联生成它的刷新批次 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `draft_refresh_audit` 初稿刷新审计留痕（append-only，V100 formula-management-library）。

模型：`workpaper_models.DraftRefreshAudit`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `operator_id` | 操作人编号 | （据字段名） | 编号 |  | 否 |  |
| `operator_role` | 操作人角色 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `operated_at` | 操作时间 | （据字段名） | 时间 |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `tb_snapshot_hash` | 试算表快照哈希 | 幂等键 | 文本（≤64 字） |  | 否 |  |
| `affected_count` | 受影响数量 | （据字段名） | 整数 |  | 否 |  |
| `result_status` | 结果状态 | result_status ∈ {`success` 成功, `blocked` 被阻止, `rolled_back` 已回滚} | 文本（≤20 字） |  | 否 |  |
| `detail` | 明细 | `'{}'` 在 PG/SQLite 双方言下都能解析为合法空 JSON 对象（同 custom_query_models 约定）。 | JSON |  | 否 |  |
| `revision_fingerprint` | 修订号指纹 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `transaction_mode` | 交易模式 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `failure_detail` | 失败明细 | （据字段名） | JSON |  | 是 |  |

### `draft_refresh_snapshot` 初稿刷新回滚快照（V100 formula-management-library）。

模型：`workpaper_models.DraftRefreshSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `refresh_id` | 刷新编号 | 指向 `draft_refresh_audit` | 编号 |  | 否 | draft_refresh_audit.id |
| `unit_scope` | 单位范围 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `before_value` | 之前值 | 覆盖前内容（供回滚恢复） | JSON |  | 否 |  |
| `editor_id` | 编辑人编号 | 被覆盖的人工编辑者标识（Req 4.3） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `domain` | 域 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `target_locator` | 目标定位 | （据字段名） | JSON |  | 是 |  |
| `after_value` | 之后值 | （据字段名） | JSON |  | 是 |  |
| `before_version` | 之前版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `after_version` | 之后版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `source_formula_id` | 来源公式编号 | 公式 Runtime 追踪字段：公式来源与本次绑定范围快照 | 编号 |  | 是 |  |
| `source_scope` | 来源范围 | （据字段名） | JSON |  | 是 |  |
| `restored_at` | 恢复时间 | （据字段名） | 时间 |  | 是 |  |

### `editing_locks` 通用编辑锁

模型：`editing_lock_models.EditingLock`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `resource_type` | 资源类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `resource_id` | 资源编号 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `holder_id` | 持有人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `holder_name` | 持有人名称 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `acquired_at` | 获取时间 | （据字段名） | 时间 |  | 否 |  |
| `heartbeat_at` | 心跳时间 | （据字段名） | 时间 |  | 否 |  |
| `released_at` | 解除时间 | （据字段名） | 时间 |  | 是 |  |
| `client_instance` | 客户实例 | 客户端实例标识（多窗口编辑锁隔离） | 文本（≤64 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `gt_wp_coding` 致同底稿编码

模型：`gt_coding_models.GTWpCoding`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `code_prefix` | 编码前缀 | （据字段名） | 文本 |  | 否 |  |
| `code_range` | 编码区域 | （据字段名） | 文本 |  | 否 |  |
| `cycle_name` | 循环名称 | （据字段名） | 文本 |  | 否 |  |
| `wp_type` | 底稿类型 | 。；取值：`preliminary` 预审 / `risk_assessment` 风险评估 / `control_test` 控制测试 / `substantive` 实质性程序 / `completion` 完成阶段 / `specific` / `general` / `permanent` | 枚举 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `parent_cycle` | 上级循环 | （据字段名） | 文本 |  | 是 |  |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_template_selections` 项目模板选择记录

模型：`template_library_models.ProjectTemplateSelection`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `template_id` | 模板编号 | 指向 `template_library` | 编号 |  | 否 | template_library.id |
| `template_type` | 模板类型 | 取值：`report_soe` / `report_listed` / `workpaper_preset` / `workpaper_custom` | 枚举 |  | 否 |  |
| `pulled_at` | 拉取时间 | 拉取状态；拉取到项目的时间 | 时间 |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `linked_trial_balance` | 关联试算余额 | 联动状态；是否已与试算表联动 | 是 / 否 |  | 否 |  |
| `linked_adjustments` | 关联调整 | 是否已与调整分录联动 | 是 / 否 |  | 否 |  |
| `linked_attachments` | 关联附件 | 是否已与附件联动 | 是 / 否 |  | 否 |  |
| `last_sync_at` | 最近同步时间 | 最后同步时间 | 时间 |  | 是 |  |
| `selected_by` | 选中人 | 元数据；指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_workbook_instance` 

模型：`project_workbook_models.ProjectWorkbookInstanceRow`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `workbook_instance_id` | 工作簿实例编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `organization_id` | 组织编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 文本（≤128 字） |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `workbook_lineage_id` | 工作簿血缘编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `pinned_template_version_id` | 固定模板版本编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `current_artifact_id` | 当前产物编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `content_revision` | 内容修订号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `representation_revision` | 表示形式修订号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `workbook_generation` | 工作簿生成代次 | （据字段名） | 整数 |  | 否 |  |
| `onlyoffice_room_id` | 在线编辑房间编号 | （据字段名） | 文本（≤256 字） |  | 是 |  |
| `context_fingerprint` | 上下文指纹 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `authorization_epoch` | 授权代次 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_workbook_sheet_entry` 

模型：`project_workbook_models.ProjectWorkbookSheetEntryRow`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤256 字） |  | 否 |  |
| `workbook_instance_id` | 工作簿实例编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `sheet_uid` | 表页编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `sheet_code` | 表页编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `component_type` | 组成部分类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `projection_mode` | 投影模式 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `manifest_version` | 清单版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `guidance_revision` | 编制指引修订号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `projection_generation` | 投影生成代次 | child 派生 projection 世代——随 workbook_generation 推进而刷新，但 entry_id 不变 | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_workpaper_sheet_override` 项目级底稿 sheet 归类覆盖

模型：`project_wp_sheet_override.ProjectWorkpaperSheetOverride`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `sheet_name` | 表页名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `class_override` | 类覆盖 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `scope_override` | 范围覆盖 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `schema_override` | 结构覆盖 | （据字段名） | JSON |  | 是 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `template_library` 模板库条目

模型：`template_library_models.TemplateLibraryItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | 模板基本信息 | 文本（≤300 字） |  | 否 |  |
| `template_type` | 模板类型 | 取值：`report_soe` / `report_listed` / `workpaper_preset` / `workpaper_custom` | 枚举 |  | 否 |  |
| `level` | 级次 | 取值：`firm_default` / `group_custom` / `project` | 枚举 |  | 否 |  |
| `group_id` | 组编号 | 归属；集团定制时的集团项目ID | 编号 |  | 是 |  |
| `group_name` | 组名称 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `source_template_id` | 来源模板编号 | 来源追溯；从哪个模板派生（集团从事务所派生，项目从集团派生）；指向 `template_library` | 编号 |  | 是 | template_library.id |
| `version` | 版本号 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `file_path` | 文件路径 | 文件信息；文件存储路径 | 长文本 |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 否 |  |
| `knowledge_folder_id` | 知识库文件夹编号 | 关联知识库文件夹 | 编号 |  | 是 |  |
| `wp_code` | 底稿编码 | 底稿专用字段；底稿编号如E1-1 | 文本（≤20 字） |  | 是 |  |
| `audit_cycle` | 审计循环 | 审计循环如E/D/H | 文本（≤10 字） |  | 是 |  |
| `account_codes` | 科目编码 | 关联科目编码 | JSON |  | 是 |  |
| `report_scope` | 报表范围 | 报告专用字段；consolidated/standalone | 文本（≤20 字） |  | 是 |  |
| `opinion_type` | 意见类型 | `standard` 标准科目/`qualified` 保留意见/... | 文本（≤20 字） |  | 是 |  |
| `description` | 说明 | 描述与标签 | 长文本 |  | 是 |  |
| `tags` | 标签 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |

### `working_paper` 底稿文件

模型：`workpaper_models.WorkingPaper`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `file_path` | 文件位置 | 服务器上的 Excel 文件 | 文本 |  | 否 |  |
| `source_type` | 来源 | `template` 模板生成 / `manual` 手工新建 / `imported` 导入 | 枚举 |  | 否 |  |
| `status` | 编制状态 | `draft` 编制中 / `edit_complete` 编制完成待提交 / `under_review` 复核中 / `revision_required` 退回修改 / `review_passed` 复核通过 / `archived` 已归档（另有两个旧值 `review_level1_passed`、`review_level2_passed` 只为兼容老数据） | 枚举 |  | 否 |  |
| `review_status` | 复核进度 | 到第几级复核、什么结果；`not_submitted` 未提交；`pending_levelN` 待 N 级复核；`levelN_in_progress` N 级复核中；`levelN_passed` N 级通过；`levelN_rejected` N 级退回（N = 1~4） | 枚举 |  | 否 |  |
| `assigned_to` | 编制人 | （据字段名） | 编号 |  | 是 | users.id |
| `reviewer` | 复核人 | （据字段名） | 编号 |  | 是 | users.id |
| `file_version` | 文件版本 | 文件每保存一次加 1 | 整数 |  | 否 |  |
| `content_revision` | 内容修订号 | 底稿内容每改一次加 1，用来防止两人同时改冲突 | 整数 |  | 否 |  |
| `current_content_version_id` | 当前内容版本编号 | （据字段名） | 编号 |  | 是 |  |
| `last_parsed_at` | 解析时间 | 系统从文件里读出的数，内部用 | 时间 |  | 是 |  |
| `parsed_data` | 解析出的数据 | 系统从文件里读出的数，内部用 | JSON |  | 是 |  |
| `prefill_stale` | 预填已过期 | 试算表变了，底稿里自动取的数需要刷新；是 / 否 | 是 / 否 |  | 否 |  |
| `prefill_tb_snapshot` | 上次预填时的试算表 | 用来对比试算表是否变过；`{科目: 审定数}` | JSON |  | 是 |  |
| `rejection_reason` | 退回原因 | （据字段名） | 长文本 |  | 是 |  |
| `rejected_by` | 退回人 | （据字段名） | 编号 |  | 是 | users.id |
| `rejected_at` | 退回时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `workflow_status` |  | 取值和用途未查明 | 文本（≤30 字） |  | 否 |  |
| `explanation_status` |  | 取值和用途未查明 | 文本（≤30 字） |  | 否 |  |
| `consistency_status` | 数据一致性 | 底稿数和试算表是否一致；`unknown` 未检查 / `inconsistent` 不一致；其他取值未查明 | 文本（≤30 字） |  | 否 |  |
| `quality_score` | 质量评分 | 为空表示还没算 | 整数 |  | 是 |  |
| `procedure_completion_rate` | 程序完成率 | 为空表示还没算 | 金额（2 位小数） |  | 是 |  |
| `last_parsed_sync_at` |  | 取值和用途未查明 | 时间 |  | 是 |  |
| `partner_reviewed_at` | 合伙人复核时间 | （据字段名） | 时间 |  | 是 |  |
| `partner_reviewed_by` | 复核人 | （据字段名） | 编号 |  | 是 | users.id |
| `bound_dataset_id` | 绑定的账套版本 | 首次生成底稿时用的账套版本 | 编号 |  | 是 | ledger_datasets.id |
| `dataset_bound_at` | 绑定的账套版本 | 首次生成底稿时用的账套版本 | 时间 |  | 是 |  |

### `workpaper_extraction_log` 底稿提取日志 — 记录截止测试/抽凭引擎的执行留痕和填充前快照，支持撤销功能。

模型：`audit_platform_models.WorkpaperExtractionLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `workpaper_id` | 底稿编号 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `user_id` | 用户 | （据字段名） | 编号 |  | 否 |  |
| `extraction_type` | 提取类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `extraction_criteria` |  | 未查明 | JSON |  | 否 |  |
| `total_matched` | 合计匹配 | （据字段名） | 整数 |  | 否 |  |
| `filled_count` |  | 未查明 | 整数 |  | 否 |  |
| `fill_mode` | 填充模式 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `before_data` | 之前数据 | （据字段名） | JSON |  | 是 |  |
| `is_undone` | 是否撤销 | （据字段名） | 是 / 否 |  | 否 |  |
| `batch_id` | 批次编号 | （据字段名） | 编号 |  | 是 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 长文本 |  | 是 |  |
| `row_version` | 行版本 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 长文本 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_field_overrides` 统一字段覆盖值

模型：`workpaper_field_override_models.WorkpaperFieldOverride`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `item_key` | 项键 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `field` | 字段 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `value` | 值 | （据字段名） | JSON |  | 是 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_generation_items` 生成操作内的一份底稿及其可恢复文件 manifest。

模型：`wp_generation_models.WorkpaperGenerationItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `operation_id` | 操作编号 | 指向 `workpaper_generation_operations` | 编号 |  | 否 | workpaper_generation_operations.id |
| `ordinal` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `wp_name` | 底稿名称 | （据字段名） | 长文本 |  | 否 |  |
| `audit_cycle` | 审计循环 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `wp_index_id` | 底稿目录 | （据字段名） | 编号 |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 否 |  |
| `template_source` | 模板来源 | （据字段名） | JSON |  | 是 |  |
| `template_fingerprint` | 模板指纹 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `staging_path` |  | 未查明 | 长文本 |  | 是 |  |
| `final_path` | 最终路径 | （据字段名） | 长文本 |  | 是 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `from_template` | 从模板 | （据字段名） | 是 / 否 |  | 否 |  |
| `header_prepared` | 表头编制 | （据字段名） | 是 / 否 |  | 否 |  |
| `header_issue` | 表头问题 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `error` | 错误 | （据字段名） | 长文本 |  | 是 |  |

### `workpaper_generation_operations` 一次可恢复的底稿生成操作。

模型：`wp_generation_models.WorkpaperGenerationOperation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `kind` | 类别 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `template_set_id` | 模板集编号 | 指向 `wp_template_set` | 编号 |  | 是 | wp_template_set.id |
| `failure_policy` | 失败策略 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `request_payload` | 请求数据 | （据字段名） | JSON |  | 否 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `scope_revision` | 范围修订号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `lease_token` | 租约令牌 | （据字段名） | 编号 |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |
| `attempt` | 尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `progress_total` | 进度合计 | （据字段名） | 整数 |  | 否 |  |
| `progress_done` | 进度完成 | （据字段名） | 整数 |  | 否 |  |
| `receipt` | 回执 | （据字段名） | JSON |  | 是 |  |
| `public_error` | 公开错误 | （据字段名） | 长文本 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_lifecycle_events` 一张底稿（wp_index + 名下 working_paper）的一次移入 / 恢复回收站。

模型：`workpaper_lifecycle_models.WorkpaperLifecycleEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_index_id` | 底稿目录 | （据字段名） | 编号 |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本 |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `kind` | 类别 | 原因类别：trim（程序裁剪）/ standard_conversion（准则切换）/ 空（回收站手工恢复不限原因时取最后一次移入的类别） | 长文本 |  | 否 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | （据字段名） | 编号 |  | 是 |  |
| `request_id` | 请求号 | （据字段名） | 长文本 |  | 是 |  |
| `working_paper_ids` | 底稿列表 | （据字段名） | JSON |  | 否 |  |
| `trim_codes` | 裁剪编码 | 导致移入的程序行编码（如 H3-2 ← H3），恢复事件为空 | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_procedures` 审计程序清单

模型：`wp_optimization_models.WorkpaperProcedure`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `procedure_id` | 程序编号 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 否 |  |
| `category` | 类别 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `is_mandatory` |  | 未查明 | 是 / 否 |  | 否 |  |
| `applicable_project_types` | 适用项目类型 | （据字段名） | JSON |  | 是 |  |
| `depends_on` | 依赖 | （据字段名） | JSON |  | 是 |  |
| `evidence_type` | 证据类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `completed_by` | 完成人 | （据字段名） | 编号 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `trimmed_by` | 裁剪人 | （据字段名） | 编号 |  | 是 |  |
| `trimmed_at` | 裁剪时间 | （据字段名） | 时间 |  | 是 |  |
| `trim_reason` | 裁剪原因 | （据字段名） | 长文本 |  | 是 |  |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_row_name_mapping` 一行的行名对齐映射（版本行）。

模型：`workpaper_row_name_mapping_models.WorkpaperRowNameMapping`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `sheet_code` | 表页编码 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `row_key` | 行键 | （据字段名） | 文本（≤256 字） |  | 否 |  |
| `targets` |  | 目标身份数组（展示 + 快照）；可查询明细见 WorkpaperRowNameMappingTarget | JSON |  | 否 |  |
| `match_state` | 匹配状态 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `dataset_fingerprint` | 账套版本指纹 | stale 指纹 | 文本（≤128 字） |  | 是 |  |
| `mapping_version` | 映射版本 | 版本 / 幂等 / 乐观锁 | 整数 |  | 否 |  |
| `base_mapping_version` | 基准映射版本 | （据字段名） | 整数 |  | 是 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `is_active` | 是否启用 | 版本链与留痕 | 是 / 否 |  | 否 |  |
| `superseded_from` | 被替代从 | 指向 `workpaper_row_name_mapping` | 编号 |  | 是 | workpaper_row_name_mapping.id |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_row_name_mapping_target` 映射目标身份明细（让身份可 SQL 查询：判 stale / 多对一交集）。

模型：`workpaper_row_name_mapping_models.WorkpaperRowNameMappingTarget`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `mapping_id` | 映射编号 | 指向 `workpaper_row_name_mapping` | 编号 |  | 否 | workpaper_row_name_mapping.id |
| `source_kind` | 来源类别 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `account_code` | 科目编码 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `aux_type` | 辅助类型 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `aux_name` | 辅助名称 | （据字段名） | 文本（≤256 字） |  | 否 |  |
| `dimension_key` | 维度键 | （据字段名） | 文本（≤512 字） |  | 否 |  |
| `dataset_id` | 账套版本 | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_sheet_classification` 底稿 sheet 归类（9 类：A~I）

模型：`workpaper_models.WorkpaperSheetClassification`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `sheet_name` | 表页名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `class_code` | 类编码 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `class` | 类 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `is_real_workpaper` |  | 未查明 | 是 / 否 |  | 否 |  |
| `exclude_from_archive` | 排除从归档 | （据字段名） | 是 / 否 |  | 否 |  |
| `exclude_from_progress` | 排除从进度 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_static_doc` |  | 未查明 | 是 / 否 |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `delegated_module` |  | 未查明 | 文本（≤50 字） |  | 是 |  |
| `template_version_id` | 模板版本编号 | 指向 `workpaper_template_version` | 编号 |  | 是 | workpaper_template_version.id |
| `render_schema_path` | 渲染结构路径 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `functional_type` | 记账类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_snapshots` 底稿版本快照 — field-level 数据版本历史，支持时间线展示、diff 对比、回滚。

模型：`audit_platform_models.WorkpaperSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `workpaper_id` | 底稿编号 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `user_id` | 用户 | （据字段名） | 编号 |  | 否 |  |
| `snapshot_type` | 快照类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `change_summary` | 变更摘要 | （据字段名） | 长文本 |  | 是 |  |
| `data_json` | 数据JSON | （据字段名） | JSON |  | 否 |  |
| `item_count` | 项数量 | （据字段名） | 整数 |  | 否 |  |
| `data_size_bytes` | 数据大小字节数 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_locked` | 是否锁定 | （据字段名） | 是 / 否 |  | 否 |  |
| `bound_dataset_id` | 绑定账套版本编号 | （据字段名） | 编号 |  | 是 |  |

### `workpaper_template_version` 底稿模板版本

模型：`workpaper_template_version.WorkpaperTemplateVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `version` | 版本号 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `release_date` | 解除日期 | （据字段名） | 日期 |  | 否 |  |
| `source` | 来源 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `is_current` | 是否当前 | （据字段名） | 是 / 否 |  | 否 |  |
| `parent_version_id` | 上级版本编号 | 指向 `workpaper_template_version` | 编号 |  | 是 | workpaper_template_version.id |
| `changelog` |  | 未查明 | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_cross_ref` 底稿交叉引用

模型：`workpaper_models.WpCrossRef`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `source_wp_id` | 来源底稿编号 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `target_wp_code` | 目标底稿编码 | （据字段名） | 文本 |  | 否 |  |
| `cell_reference` | 单元格引用 | （据字段名） | 文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_index` 底稿索引

模型：`workpaper_models.WpIndex`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_code` | 底稿编码 | 如 `D2`、`E1-1`；同项目不重复 | 文本 |  | 否 |  |
| `wp_name` | 底稿名称 | （据字段名） | 文本 |  | 否 |  |
| `audit_cycle` | 审计循环 | 一般与底稿编码首字母一致；A 报表与调整 / B 控制了解 / C 控制测试 / D 销售与收款 / E 货币资金 / F 采购与存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 筹资 / M 所有者权益 / N 税费 / S 专项 | 文本 |  | 是 |  |
| `assigned_to` | 编制人 | （据字段名） | 编号 |  | 是 | users.id |
| `reviewer` | 复核人 | （据字段名） | 编号 |  | 是 | users.id |
| `status` | 目录状态 | `not_started` 未开始 / `in_progress` 编制中 / `draft_complete` 初稿完成 / `review_passed` 复核通过 / `archived` 已归档 | 枚举 |  | 否 |  |
| `cross_ref_codes` | 交叉索引 | 引用了哪些其他底稿；结构未查明 | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_template` 底稿模板

模型：`workpaper_models.WpTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_code` | 模板编码 | （据字段名） | 文本 |  | 否 |  |
| `template_name` | 模板名称 | （据字段名） | 文本 |  | 否 |  |
| `audit_cycle` | 审计循环 | （据字段名） | 文本 |  | 是 |  |
| `applicable_standard` | 适用准则 | （据字段名） | 文本 |  | 是 |  |
| `version_major` |  | 未查明 | 整数 |  | 否 |  |
| `version_minor` |  | 未查明 | 整数 |  | 否 |  |
| `status` | 状态 | 取值：`draft` 草稿 / `published` 已发布 / `deprecated` | 枚举 |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 文本 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_template_custom` 自定义底稿模板

模型：`extension_models.WpTemplateCustom`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `template_name` | 模板名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `category` | 类别 | industry/`client` 客户科目/personal | 文本（≤50 字） |  | 否 |  |
| `template_file_path` | 模板文件路径 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `is_published` | 是否发布 | （据字段名） | 是 / 否 |  | 否 |  |
| `version` | 版本号 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `formula_valid` | 公式有效 | （据字段名） | 是 / 否 |  | 是 |  |

### `wp_template_meta` 模板元数据（命名区域定义）

模型：`workpaper_models.WpTemplateMeta`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_id` | 模板编号 | 指向 `wp_template` | 编号 |  | 否 | wp_template.id |
| `range_name` | 区域名称 | （据字段名） | 文本 |  | 否 |  |
| `region_type` | 地区类型 | 取值：`formula` / `manual` 手工 / `ai_fill` / `conclusion` / `cross_ref` | 枚举 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_template_metadata` 底稿模板元数据

模型：`wp_optimization_models.WpTemplateMetadata`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_id` | 模板编号 | 指向 `wp_template` | 编号 |  | 是 | wp_template.id |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `component_type` | 组成部分类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `audit_stage` | 审计阶段 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `cycle` | 循环 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `file_format` | 文件格式 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `procedure_steps` | 程序步骤 | （据字段名） | JSON |  | 是 |  |
| `guidance_text` | 编制指引文本 | （据字段名） | 长文本 |  | 是 |  |
| `formula_cells` | 公式单元格 | （据字段名） | JSON |  | 是 |  |
| `required_regions` |  | 未查明 | JSON |  | 是 |  |
| `linked_accounts` | 关联科目 | （据字段名） | JSON |  | 是 |  |
| `note_section` | 附注章节号 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `conclusion_cell` | 结论单元格 | （据字段名） | JSON |  | 是 |  |
| `audit_objective` | 审计目标 | （据字段名） | 长文本 |  | 是 |  |
| `related_assertions` | 相关认定 | （据字段名） | JSON |  | 是 |  |
| `procedure_flow_config` | 程序流量配置 | （据字段名） | 长文本 |  | 是 |  |
| `header_cells` | 表头单元格 | E1 | JSON |  | 是 |  |
| `llm_prompts` |  | 未查明 | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_template_set` 底稿模板集

模型：`workpaper_models.WpTemplateSet`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `set_name` | 集名称 | （据字段名） | 文本 |  | 否 |  |
| `template_codes` | 模板编码 | （据字段名） | JSON |  | 是 |  |
| `applicable_audit_type` | 适用审计类型 | （据字段名） | 文本 |  | 是 |  |
| `applicable_standard` | 适用准则 | （据字段名） | 文本 |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="s-group"></a>
## S. 底稿同步与在线编辑

### `evidence_hash_checks` 

模型：`phase16_models.EvidenceHashCheck`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `export_id` | 导出编号 | export_id 业务上是字符串标识符（rc_enhanced 生成 `exp_rc_日期_hex` / archive 用 str(job.id)） | 文本（≤64 字） |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 长文本 |  | 否 |  |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `signature_digest` | 签名摘要哈希 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `check_status` | 检查状态 | `passed` 通过/`failed` 失败 | 文本（≤16 字） |  | 否 |  |
| `checked_at` | 检查时间 | （据字段名） | 时间 |  | 否 |  |

### `offline_conflicts` 

模型：`phase16_models.OfflineConflict`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 否 |  |
| `procedure_id` | 程序编号 | （据字段名） | 编号 |  | 否 |  |
| `field_name` | 字段名称 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `local_value` | 本地值 | （据字段名） | JSON |  | 是 |  |
| `remote_value` | 远程值 | （据字段名） | JSON |  | 是 |  |
| `merged_value` | 合并值 | （据字段名） | JSON |  | 是 |  |
| `status` | 状态 | `open` 未处理/`resolved` 已解决/`rejected` 已驳回 | 文本（≤16 字） |  | 否 |  |
| `resolver_id` | 取数函数编号 | （据字段名） | 编号 |  | 是 |  |
| `reason_code` | 原因编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `qc_replay_job_id` | 质控重放任务编号 | （据字段名） | 编号 |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |

### `version_line_stamps` 

模型：`phase16_models.VersionLineStamp`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `object_type` | 对象类型 | report/note/`workpaper` 底稿/procedure | 文本（≤32 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 否 |  |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `source_snapshot_id` | 来源快照编号 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_artifact` 内容寻址不可变文件登记表。

模型：`workpaper_sync_models.WorkpaperArtifact`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `kind` | 类别 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `relative_path` |  | 未查明 | 长文本 |  | 否 |  |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `size_bytes` | 大小字节数 | （据字段名） | 整数 |  | 否 |  |
| `document_type` | 文档类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `retention_class` | 保留类 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `legal_hold` | 法律保全 | （据字段名） | 是 / 否 |  | 否 |  |
| `source_delivery_id` | 来源投递编号 | 指向 `working_paper_callback_delivery` | 编号 |  | 是 | working_paper_callback_delivery.id |
| `created_by_operation_id` | 创建人操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `durable_at` | 持久时间 | （据字段名） | 时间 |  | 是 |  |
| `quarantined_at` |  | 未查明 | 时间 |  | 是 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 是 |  |
| `orphaned_at` |  | 未查明 | 时间 |  | 是 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_callback_delivery` 每次 callback 投递。归属只以 immutable `durable_at` 判定。

模型：`workpaper_sync_models.WorkpaperCallbackDelivery`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `application_id` | 应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `forcesave_request_id` | 强制保存请求编号 | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `callback_recovery_case_id` | 回调恢复案例编号 | 指向 `working_paper_callback_recovery_case` | 编号 |  | 是 | working_paper_callback_recovery_case.id |
| `route_credential_id` |  | 未查明 | 编号 |  | 否 |  |
| `callback_status` | 回调状态 | （据字段名） | 整数 |  | 否 |  |
| `delivery_key` | 投递键 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `payload_sha256` | 数据SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `oo_users_digest` | 在线编辑用户摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `correlation_result` | 关联结果 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `incoming_artifact_id` | 收到的产物编号 | 指向 `working_paper_artifact` | 编号 |  | 是 | working_paper_artifact.id |
| `response_error` | 回复错误 | （据字段名） | 整数 |  | 是 |  |
| `received_at` | 收到时间 | （据字段名） | 时间 |  | 否 |  |
| `durable_at` | 持久时间 | （据字段名） | 时间 |  | 是 |  |
| `responded_at` | 回复时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_callback_recovery_case` 无法唯一归组的 durable incoming 的可审计恢复案例。claim 前三实体恒空。

模型：`workpaper_sync_models.WorkpaperCallbackRecoveryCase`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `source_delivery_key` | 来源投递键 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `incoming_artifact_id` | 收到的产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `reason` | 原因 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `candidate_confirmation_digest` | 候选函证摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `candidate_contributor_digest` | 候选参与者摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `claimed_by_participant_id` | 领取人参与者编号 | 指向 `working_paper_oo_participant` | 编号 |  | 是 | working_paper_oo_participant.id |
| `prior_confirmation_id` | 上期函证编号 | 指向 `working_paper_oo_client_confirmation` | 编号 |  | 是 | working_paper_oo_client_confirmation.id |
| `recovery_request_id` | 恢复请求编号 | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `application_id` | 应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `claimed_definition_bundle_id` | 领取定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 是 | working_paper_sync_definition_bundle.id |
| `claimed_definition_bundle_sha256` | 领取定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `claimed_at` | 领取时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_callback_recovery_case_event` recovery case 的独立 append-only timeline（与 operation timeline 分离）。

模型：`workpaper_sync_models.WorkpaperCallbackRecoveryCaseEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 整数 | 是 |  |  |
| `case_id` | 案例编号 | 指向 `working_paper_callback_recovery_case` | 编号 |  | 否 | working_paper_callback_recovery_case.id |
| `sequence_no` | 序号编号 | （据字段名） | 整数 |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 是 |  |
| `authorization_result` | 授权结果 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `prior_confirmation_id` | 上期函证编号 | 指向 `working_paper_oo_client_confirmation` | 编号 |  | 是 | working_paper_oo_client_confirmation.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `occurred_at` | 发生时间 | （据字段名） | 时间 |  | 否 |  |

### `working_paper_content_application` durable incoming 对业务状态的一次逻辑应用；`application_key` 的唯一 owner。

模型：`workpaper_sync_models.WorkpaperContentApplication`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `origin_request_id` | 来源请求编号 | 指向 `working_paper_forcesave_request` | 编号 |  | 否 | working_paper_forcesave_request.id |
| `application_key` | 应用键 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `client_edit_epoch` | 客户编辑代次 | （据字段名） | 整数 |  | 否 |  |
| `origin_request_sequence` | 来源请求序号 | （据字段名） | 整数 |  | 否 |  |
| `effective_request_sequence` | 生效请求序号 | （据字段名） | 整数 |  | 否 |  |
| `base_version_id` | 基准版本编号 | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `base_representation_id` | 基准表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 否 | working_paper_content_representation.id |
| `current_revision` | 当前修订号 | （据字段名） | 整数 |  | 否 |  |
| `result_revision` | 结果修订号 | （据字段名） | 整数 |  | 是 |  |
| `incoming_artifact_id` | 收到的产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `incoming_sha256` | 收到的SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `incoming_projection_sha256` | 收到的投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `merged_projection_sha256` | 合并投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `result_representation_id` | 结果表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 是 | working_paper_content_representation.id |
| `result_artifact_sha256` | 结果产物SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 否 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_id` | 权威来源模型定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `adapter_id` | 适配器编号 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `adapter_build_digest` | 适配器构建摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `contributor_snapshot_digest` | 参与者快照摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `conflict_count` | 冲突数量 | （据字段名） | 整数 |  | 否 |  |
| `conflict_set_digest` | 冲突集摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `superseded_by_application_id` | 被替代人应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `logical_result_code` | 逻辑结果编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `durable_at` | 持久时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_content_application_event` application 的 append-only timeline（含 `sequence_folded` 审计）。

模型：`workpaper_sync_models.WorkpaperContentApplicationEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 整数 | 是 |  |  |
| `application_id` | 应用编号 | 指向 `working_paper_content_application` | 编号 |  | 否 | working_paper_content_application.id |
| `sequence_no` | 序号编号 | （据字段名） | 整数 |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `folded_request_id` |  | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `origin_request_sequence` | 来源请求序号 | （据字段名） | 整数 |  | 否 |  |
| `effective_request_sequence` | 生效请求序号 | （据字段名） | 整数 |  | 否 |  |
| `room_latest_durable_sequence` | 房间最新持久序号 | （据字段名） | 整数 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `occurred_at` | 发生时间 | （据字段名） | 时间 |  | 否 |  |

### `working_paper_content_representation` 同一 content version 的 1:N immutable OOXML representation generation。

模型：`workpaper_sync_models.WorkpaperContentRepresentation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `content_version_id` | 内容版本编号 | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `parent_representation_id` | 上级表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 是 | working_paper_content_representation.id |
| `document_type` | 文档类型 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `artifact_id` | 产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `artifact_sha256` | 产物SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 否 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_id` | 权威来源模型定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `adapter_id` | 适配器编号 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `adapter_build_digest` | 适配器构建摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `structure_hash` | 结构哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `identity_inventory_sha256` | 身份存货SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `reason` | 原因 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_content_revision_backfill_ledger` V151 revision 0 回填台账：只记录，不创建 content version/representation。

模型：`workpaper_sync_models.WorkpaperContentRevisionBackfillLedger`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 | 是 |  | working_paper.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `backfilled_content_revision` | 回填内容修订号 | （据字段名） | 整数 |  | 否 |  |
| `legacy_file_version` | 旧版文件版本 | （据字段名） | 整数 |  | 是 |  |
| `had_parsed_data` |  | 未查明 | 是 / 否 |  | 否 |  |
| `entry_verification_state` |  | 未查明 | 文本（≤20 字） |  | 否 |  |
| `content_version_created` | 内容版本创建 | （据字段名） | 是 / 否 |  | 否 |  |
| `representation_created` | 表示形式创建 | （据字段名） | 是 / 否 |  | 否 |  |
| `migration_version` | 迁移版本 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `backfilled_at` | 回填时间 | （据字段名） | 时间 |  | 否 |  |

### `working_paper_content_version` immutable 业务内容版本。`revision` 只因业务 projection/权威内容变化递增。

模型：`workpaper_sync_models.WorkpaperContentVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `parent_version_id` | 上级版本编号 | 指向 `working_paper_content_version` | 编号 |  | 是 | working_paper_content_version.id |
| `source` | 来源 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `projection_artifact_id` | 投影产物编号 | 指向 `working_paper_artifact` | 编号 |  | 是 | working_paper_artifact.id |
| `projection_sha256` | 投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `authoritative_artifact_id` | 权威产物编号 | 指向 `working_paper_artifact` | 编号 |  | 是 | working_paper_artifact.id |
| `authoritative_artifact_sha256` | 权威产物SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `export_surface_class` |  | 底稿内容版本的正式导出/数据交换单位证据。 | 文本（≤20 字） |  | 是 |  |
| `unit_policy_snapshot` | 单位策略快照 | （据字段名） | JSON |  | 是 |  |
| `unit_policy_digest` | 单位策略摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `source_storage_unit` | 来源存储单位 | （据字段名） | 文本（≤16 字） |  | 是 |  |

### `working_paper_entry_evidence_scenario` 逐 scenario 证据行。download-only/recovery-reject 场景 operation/application 恒空。

模型：`workpaper_sync_models.WorkpaperEntryEvidenceScenario`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `run_id` | 运行编号 | 指向 `working_paper_sync_test_run` | 编号 |  | 否 | working_paper_sync_test_run.id |
| `scenario_id` | 场景编号 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `ordinal` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `scenario_kind` | 场景类别 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `result` | 结果 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `operation_ids` | 操作列表 | test_archive_orchestrator(15) + test_archive_deprecated(3) 共 60 例。 | JSON |  | 否 |  |
| `application_ids` | 应用列表 | （据字段名） | JSON |  | 否 |  |
| `recovery_case_ids` | 恢复案例列表 | （据字段名） | JSON |  | 否 |  |
| `content_version_ids` | 内容版本列表 | （据字段名） | JSON |  | 否 |  |
| `representation_ids` | 表示形式列表 | （据字段名） | JSON |  | 否 |  |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `trace_bundle_artifact_id` | 追踪包产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `trace_bundle_sha256` | 追踪包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `server_timeline_digest` |  | 未查明 | 文本（≤64 字） |  | 否 |  |
| `database_snapshot_digest` |  | 未查明 | 文本（≤64 字） |  | 否 |  |
| `browser_build` | 浏览器构建 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_forcesave_request` Command Service 调用前冻结的 request。

模型：`workpaper_sync_models.WorkpaperForcesaveRequest`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `request_sequence` | 请求序号 | （据字段名） | 整数 |  | 否 |  |
| `kind` | 类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `initiated_by_participant_id` | 发起人参与者编号 | 指向 `working_paper_oo_participant` | 编号 |  | 否 | working_paper_oo_participant.id |
| `initiator_permission_epoch` | 发起人权限代次 | （据字段名） | 整数 |  | 否 |  |
| `client_edit_epoch` | 客户编辑代次 | （据字段名） | 整数 |  | 否 |  |
| `write_fence_epoch` | 写入围栏代次 | （据字段名） | 整数 |  | 否 |  |
| `client_base_version_id` | 客户基准版本编号 | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `client_base_representation_id` | 客户基准表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 否 | working_paper_content_representation.id |
| `client_base_projection_sha256` | 客户基准投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 否 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_id` | 权威来源模型定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `adapter_build_digest` | 适配器构建摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `contributor_snapshot_digest` | 参与者快照摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `frozen_request_fingerprint` | 冻结请求指纹 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `accepted_at` | 接受时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_oo_client_confirmation` DocEditor `onDocumentReady` 后的 descriptor 逐项确认。

模型：`workpaper_sync_models.WorkpaperOoClientConfirmation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `participant_id` | 参与者编号 | 指向 `working_paper_oo_participant` | 编号 |  | 否 | working_paper_oo_participant.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `doc_key` | 文档键 | （据字段名） | 文本（≤150 字） |  | 否 |  |
| `representation_id` | 表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 否 | working_paper_content_representation.id |
| `artifact_sha256` | 产物SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `content_version_id` | 内容版本编号 | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `projection_sha256` | 投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 否 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `bundle_slots_digest` | 包位置摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `write_fence_epoch` | 写入围栏代次 | （据字段名） | 整数 |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 否 |  |
| `invalidated_at` |  | 未查明 | 时间 |  | 是 |  |

### `working_paper_oo_close_intent` clean close intent；只有 reconciler 可把 deterministic leader CAS 提升为 close_capture。

模型：`workpaper_sync_models.WorkpaperOoCloseIntent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `participant_id` | 参与者编号 | 指向 `working_paper_oo_participant` | 编号 |  | 否 | working_paper_oo_participant.id |
| `client_confirmation_id` | 客户函证编号 | 指向 `working_paper_oo_client_confirmation` | 编号 |  | 否 | working_paper_oo_client_confirmation.id |
| `intent_sequence` | 意图序号 | （据字段名） | 整数 |  | 否 |  |
| `barrier_epoch` | 屏障代次 | （据字段名） | 整数 |  | 否 |  |
| `eligibility_epoch` | 适用性代次 | （据字段名） | 整数 |  | 否 |  |
| `ordinary_forcesave_request_id` |  | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `promoted_request_id` |  | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `reconciled_at` |  | 未查明 | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_oo_close_intent_event` close intent 的 append-only eligibility/leader timeline。

模型：`workpaper_sync_models.WorkpaperOoCloseIntentEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 整数 | 是 |  |  |
| `intent_id` | 意图编号 | 指向 `working_paper_oo_close_intent` | 编号 |  | 否 | working_paper_oo_close_intent.id |
| `sequence_no` | 序号编号 | （据字段名） | 整数 |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `eligibility_epoch` | 适用性代次 | （据字段名） | 整数 |  | 否 |  |
| `eligibility_digest` | 适用性摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 是 |  |
| `authorization_result` | 授权结果 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `occurred_at` | 发生时间 | （据字段名） | 时间 |  | 否 |  |

### `working_paper_oo_participant` 逐用户 participant lease。`closing` 是 close intent 创建时的原子中间态。

模型：`workpaper_sync_models.WorkpaperOoParticipant`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 否 | working_paper_oo_room.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `mode` | 模式 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `permission_epoch` | 权限代次 | （据字段名） | 整数 |  | 否 |  |
| `joined_write_fence_epoch` |  | 未查明 | 整数 |  | 否 |  |
| `lease_token_hash` | 租约令牌哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `revoked_at` | 吊销时间 | （据字段名） | 时间 |  | 是 |  |
| `left_at` | 剩余时间 | （据字段名） | 时间 |  | 是 |  |
| `oo_drop_confirmed_at` |  | 未查明 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_oo_room` 共享 OO room：server last-applied 与 client-confirmed 是两套独立指针。

模型：`workpaper_sync_models.WorkpaperOoRoom`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `doc_key` | 文档键 | （据字段名） | 文本（≤150 字） |  | 否 |  |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 否 |  |
| `opened_base_version_id` |  | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `last_applied_version_id` | 最近已应用版本编号 | 指向 `working_paper_content_version` | 编号 |  | 是 | working_paper_content_version.id |
| `client_confirmed_base_version_id` | 客户确认基准版本编号 | 指向 `working_paper_content_version` | 编号 |  | 是 | working_paper_content_version.id |
| `client_confirmed_representation_id` | 客户确认表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 是 | working_paper_content_representation.id |
| `client_confirmed_definition_bundle_id` | 客户确认定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 是 | working_paper_sync_definition_bundle.id |
| `client_confirmed_definition_bundle_sha256` | 客户确认定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `client_confirmed_projection_sha256` | 客户确认投影SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `latest_request_sequence` | 最新请求序号 | （据字段名） | 整数 |  | 否 |  |
| `latest_durable_sequence` | 最新持久序号 | （据字段名） | 整数 |  | 否 |  |
| `latest_durable_application_id` | 最新持久应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `write_fence_epoch` | 写入围栏代次 | （据字段名） | 整数 |  | 否 |  |
| `close_barrier_epoch` | 关闭屏障代次 | （据字段名） | 整数 |  | 否 |  |
| `close_leader_intent_id` | 关闭负责人意图编号 | 指向 `working_paper_oo_close_intent` | 编号 |  | 是 | working_paper_oo_close_intent.id |
| `close_leader_eligibility_epoch` | 关闭负责人适用性代次 | （据字段名） | 整数 |  | 否 |  |
| `close_leader_eligibility_digest` | 关闭负责人适用性摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `refresh_required_at` | 刷新必填时间 | （据字段名） | 时间 |  | 是 |  |
| `refresh_reason` | 刷新原因 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `superseded_at` | 被替代时间 | （据字段名） | 时间 |  | 是 |  |
| `closed_at` | 关闭时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_pending_mutation` HTML flush 产生的短 TTL 单次逻辑消费 mutation token。

模型：`workpaper_sync_models.WorkpaperPendingMutation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `expected_revision` | 预期修订号 | （据字段名） | 整数 |  | 否 |  |
| `payload_artifact_id` | 数据产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `payload_sha256` | 数据SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `result_operation_id` | 结果操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `result_content_version_id` | 结果内容版本编号 | 指向 `working_paper_content_version` | 编号 |  | 是 | working_paper_content_version.id |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `committed_at` |  | 未查明 | 时间 |  | 是 |  |

### `working_paper_representation_candidate_event` candidate contract/bundle attach 的 append-only 审计事件（V153）。

模型：`workpaper_sync_models.WorkpaperRepresentationCandidateEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `candidate_id` | 候选编号 | 指向 `working_paper_representation_upgrade_candidate` | 编号 |  | 否 | working_paper_representation_upgrade_candidate.id |
| `sequence_no` | 序号编号 | （据字段名） | 整数 |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `contract_definition_id` | 契约定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 是 | working_paper_sync_definition_artifact.id |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 是 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `correlation_id` | 关联编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_representation_upgrade_candidate` non-current representation 升级候选：resolver/room/current pointer 均不得读取。

模型：`workpaper_sync_models.WorkpaperRepresentationUpgradeCandidate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `content_version_id` | 内容版本编号 | 指向 `working_paper_content_version` | 编号 |  | 否 | working_paper_content_version.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `source_representation_id` | 来源表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 否 | working_paper_content_representation.id |
| `staged_artifact_id` | 暂存产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `staged_artifact_sha256` | 暂存产物SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `template_definition_id` | 模板定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `instrumentation_definition_id` | 监测定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `target_contract_definition_id` | 目标契约定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 是 | working_paper_sync_definition_artifact.id |
| `target_definition_bundle_id` | 目标定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 是 | working_paper_sync_definition_bundle.id |
| `finalized_representation_id` | 定稿表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 是 | working_paper_content_representation.id |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `visible_equivalence_report_sha256` |  | 未查明 | 文本（≤64 字） |  | 是 |  |
| `rollback_source_sha256` |  | 未查明 | 文本（≤64 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `finalized_at` | 定稿时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_sync_conflict` 字段级冲突记录（双侧可追溯 + canonical application fence）。

模型：`workpaper_sync_models.WorkpaperSyncConflict`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 否 | working_paper_sync_operation.id |
| `client_edit_epoch` | 客户编辑代次 | （据字段名） | 整数 |  | 否 |  |
| `canonical_application_id` | 规范应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `effective_request_sequence` | 生效请求序号 | （据字段名） | 整数 |  | 是 |  |
| `stable_field_key` | 稳定字段键 | （据字段名） | 文本（≤300 字） |  | 否 |  |
| `business_label` | 业务显示名 | （据字段名） | 文本（≤300 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `table_key` | 表键 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `row_key` | 行键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `json_pointer` |  | 未查明 | 长文本 |  | 否 |  |
| `oo_location` | 在线编辑地点 | （据字段名） | 长文本 |  | 否 |  |
| `field_source` | 字段来源 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `protection_policy` |  | 未查明 | 文本（≤40 字） |  | 否 |  |
| `suggested_action` | 建议动作 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `conflict_kind` | 冲突类别 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `schema_anomaly` | 结构异常 | 新增：它决定这条冲突能否靠「选一侧 / 输入合并值」收敛，此前列投影漏了它 | 文本（≤60 字） |  | 是 |  |
| `base_value` | 基准值 | （据字段名） | JSON |  | 是 |  |
| `current_value` | 当前值 | （据字段名） | JSON |  | 是 |  |
| `incoming_value` | 收到的值 | （据字段名） | JSON |  | 是 |  |
| `resolution` | 处理结果 | （据字段名） | JSON |  | 是 |  |
| `resolved_value` | 解决值 | （据字段名） | JSON |  | 是 |  |
| `resolved_by` | 解决人 | 指向 `users` | 编号 |  | 是 | users.id |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `superseded_at` | 被替代时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_sync_definition_artifact` immutable template / instrumentation / contract / authority_model 定义快照。

模型：`workpaper_sync_models.WorkpaperSyncDefinitionArtifact`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `kind` | 类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `logical_id` | 逻辑编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `semantic_version` |  | 未查明 | 文本（≤50 字） |  | 否 |  |
| `blob_artifact_id` | 文件内容产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `structure_hash` | 结构哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `authority_model_type` | 权威来源模型类型 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `source_commit` | 来源提交 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `supersedes_id` | 替代编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 是 | working_paper_sync_definition_artifact.id |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_sync_definition_bundle` authority model + template/instrumentation/contract 三类 typed canonical slots。

模型：`workpaper_sync_models.WorkpaperSyncDefinitionBundle`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `schema_version` | 结构版本 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `authority_model_definition_id` | 权威来源模型定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `template_slot_type` | 模板位置类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `template_slot_ref` | 模板位置引用 | （据字段名） | 长文本 |  | 否 |  |
| `template_slot_digest` | 模板位置摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `instrumentation_slot_type` | 监测位置类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `instrumentation_slot_ref` | 监测位置引用 | （据字段名） | 长文本 |  | 否 |  |
| `instrumentation_slot_digest` | 监测位置摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `contract_slot_type` | 契约位置类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `contract_slot_ref` | 契约位置引用 | （据字段名） | 长文本 |  | 否 |  |
| `contract_slot_digest` | 契约位置摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `canonical_payload_artifact_id` | 规范数据产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `canonical_payload_sha256` | 规范数据SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |

### `working_paper_sync_definition_null_marker` optional child 的版本化 typed null marker registry（禁 SQL NULL/空串/全零 hash）。

模型：`workpaper_sync_models.WorkpaperSyncDefinitionNullMarker`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `marker_id` | 标记编号 | （据字段名） | 文本（≤80 字） | 是 |  |  |
| `applies_to_slot` |  | 未查明 | 文本（≤20 字） |  | 否 |  |
| `marker_version` | 标记版本 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `canonical_payload` | 规范数据 | （据字段名） | 长文本 |  | 否 |  |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_sync_entry_state` entry 级 current representation pointer（candidate 不可引用）。

模型：`workpaper_sync_models.WorkpaperSyncEntryState`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 | 是 |  | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） | 是 |  |  |
| `current_representation_id` | 当前表示形式编号 | 指向 `working_paper_content_representation` | 编号 |  | 否 | working_paper_content_representation.id |
| `representation_generation` | 表示形式生成代次 | （据字段名） | 整数 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_sync_operation` 用户轮询/执行/timeline 容器；**不承担** application identity。

模型：`workpaper_sync_models.WorkpaperSyncOperation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `room_id` | 房间编号 | 指向 `working_paper_oo_room` | 编号 |  | 是 | working_paper_oo_room.id |
| `forcesave_request_id` | 强制保存请求编号 | 指向 `working_paper_forcesave_request` | 编号 |  | 是 | working_paper_forcesave_request.id |
| `application_id` | 应用编号 | 指向 `working_paper_content_application` | 编号 |  | 是 | working_paper_content_application.id |
| `duplicate_of_operation_id` |  | 指向 `working_paper_sync_operation` | 编号 |  | 是 | working_paper_sync_operation.id |
| `initiated_by_participant_id` | 发起人参与者编号 | 指向 `working_paper_oo_participant` | 编号 |  | 是 | working_paper_oo_participant.id |
| `direction` | 方向 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `definition_bundle_id` | 定义包编号 | 指向 `working_paper_sync_definition_bundle` | 编号 |  | 否 | working_paper_sync_definition_bundle.id |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_id` | 权威来源模型定义编号 | 指向 `working_paper_sync_definition_artifact` | 编号 |  | 否 | working_paper_sync_definition_artifact.id |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `error_stage` | 错误阶段 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `error_detail` | 错误明细 | （据字段名） | 长文本 |  | 是 |  |
| `accepted_at` | 接受时间 | （据字段名） | 时间 |  | 是 |  |
| `application_bound_at` | 应用绑定时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `working_paper_sync_operation_contributor` 聚合 callback 的 contributor 快照（initiator / route / contributor 三者分离）。

模型：`workpaper_sync_models.WorkpaperSyncOperationContributor`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 | 是 |  | working_paper_sync_operation.id |
| `participant_id` | 参与者编号 | 指向 `working_paper_oo_participant` | 编号 | 是 |  | working_paper_oo_participant.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `permission_epoch` | 权限代次 | （据字段名） | 整数 |  | 否 |  |
| `source` | 来源 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `confidence` | 置信度 | （据字段名） | 文本（≤20 字） |  | 否 |  |

### `working_paper_sync_operation_event` operation 的 append-only transition event（current state 只是它的投影）。

模型：`workpaper_sync_models.WorkpaperSyncOperationEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 整数 | 是 |  |  |
| `operation_id` | 操作编号 | 指向 `working_paper_sync_operation` | 编号 |  | 否 | working_paper_sync_operation.id |
| `sequence_no` | 序号编号 | （据字段名） | 整数 |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `stage` | 阶段 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤60 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 是 |  |
| `correlation_id` | 关联编号 | （据字段名） | 编号 |  | 是 |  |
| `client_edit_epoch` | 客户编辑代次 | （据字段名） | 整数 |  | 是 |  |
| `origin_request_sequence` | 来源请求序号 | （据字段名） | 整数 |  | 是 |  |
| `effective_request_sequence` | 生效请求序号 | （据字段名） | 整数 |  | 是 |  |
| `superseded_by` | 被替代人 | （据字段名） | 编号 |  | 是 |  |
| `detail_digest` | 明细摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `occurred_at` | 发生时间 | （据字段名） | 时间 |  | 否 |  |

### `working_paper_sync_scope_index` authorization-before-business-read 的非敏感归属索引。

模型：`workpaper_sync_models.WorkpaperSyncScopeIndex`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `resource_kind` | 资源类别 | （据字段名） | 文本（≤40 字） | 是 |  |  |
| `resource_id` | 资源编号 | （据字段名） | 长文本 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `room_id` | 房间编号 | （据字段名） | 编号 |  | 是 |  |
| `generation` | 生成代次 | （据字段名） | 整数 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `retired_at` |  | 未查明 | 时间 |  | 是 |  |

### `working_paper_sync_test_run` 一次可复现验收执行（source-backed capability identity，禁自由文本覆写）。

模型：`workpaper_sync_models.WorkpaperSyncTestRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `source_commit` | 来源提交 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `runner_version` |  | 未查明 | 文本（≤40 字） |  | 否 |  |
| `manifest_source_digest` | 清单来源摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `editability` |  | 未查明 | 文本（≤20 字） |  | 否 |  |
| `room_model` | 房间模型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `scenario_profile_digest` |  | 未查明 | 文本（≤64 字） |  | 否 |  |
| `onlyoffice_build` | 在线编辑构建 | （据字段名） | 文本（≤60 字） |  | 否 |  |
| `browser_build` | 浏览器构建 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `environment_digest` |  | 未查明 | 文本（≤64 字） |  | 否 |  |
| `required_scenario_set_digest` | 必填场景集摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `authority_model_definition_sha256` | 权威来源模型定义SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_bundle_sha256` | 定义包SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `run_manifest_artifact_id` | 运行清单产物编号 | 指向 `working_paper_artifact` | 编号 |  | 否 | working_paper_artifact.id |
| `run_manifest_sha256` | 运行清单SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `aggregate_result` | 汇总结果 | （据字段名） | 文本（≤20 字） |  | 否 |  |

### `wp_edit_sessions` 底稿编辑时间采集（WOPI lock/unlock 自动记录）。

模型：`phase12_models.WpEditSession`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `ended_at` |  | 未查明 | 时间 |  | 是 |  |
| `duration_seconds` | 耗时秒 | （据字段名） | 整数 |  | 是 |  |
| `source` | 来源 | （据字段名） | 文本（≤30 字） |  | 否 |  |

<a id="f-group"></a>
## F. 公式、取数与校验

### `acnr_invalidation_epoch` ACNR Durable_Epoch — per-project 失效计数器（DB 权威，Redis 仅 fan-out）。

模型：`acnr_invalidation_model.AcnrInvalidationEpoch`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `project_id` | 项目 | 通用字段，见文首 | 编号 | 是 |  |  |
| `epoch` | 代次 | （据字段名） | 整数 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `acnr_invalidation_outbox` ACNR Invalidation_Outbox — 业务变更同事务写入，dispatcher 至少一次投递。

模型：`acnr_invalidation_model.AcnrInvalidationOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `domain` | 域 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `dispatched_at` | 分发时间 | （据字段名） | 时间 |  | 是 |  |
| `attempts` | 尝试次数 | （据字段名） | 整数 |  | 否 |  |

### `acnr_project_overlay` ACNR L2 ProjectOverlay 持久化 — 项目级别名/CUST覆盖/binding。

模型：`acnr_overlay_model.AcnrProjectOverlay`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `parent_wp_code` | 上级底稿编码 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `sheet_code` | 表页编码 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `overlay_type` | 覆盖层类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 否 |  |
| `reason` | 原因 | overlay 治理字段（持久化，重启后 is_expired 生效）+ 乐观并发 revision | 长文本 |  | 是 |  |
| `owner` | 负责人 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 日期 |  | 是 |  |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `chain_executions` 全链路执行记录

模型：`chain_execution.ChainExecution`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `steps` | 步骤 | （据字段名） | JSON |  | 否 |  |
| `trigger_type` | 触发类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `triggered_by` | 触发人 | （据字段名） | 编号 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `total_duration_ms` | 合计耗时毫秒 | （据字段名） | 整数 |  | 是 |  |
| `snapshot_before` | 快照之前 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consistency_gate_acknowledgements` 门禁逐项确认留痕表

模型：`gate_acknowledgement_models.GateAcknowledgement`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `check_name` | 检查名称 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `branch_id` | 分支编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `result_fingerprint` | 结果指纹 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 否 |  |
| `acknowledged_by` | 知悉人 | （据字段名） | 编号 |  | 否 |  |
| `acknowledged_role` | 知悉角色 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `revoked_at` | 吊销时间 | （据字段名） | 时间 |  | 是 |  |
| `revoked_by` | 吊销人 | （据字段名） | 编号 |  | 是 |  |

### `cross_check_results` 跨科目校验结果

模型：`wp_optimization_models.CrossCheckResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `rule_id` | 规则编号 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `left_amount` | 剩余金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `right_amount` | 右金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `difference` | 差额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `details` | 明细 | （据字段名） | JSON |  | 是 |  |
| `checked_at` | 检查时间 | （据字段名） | 时间 |  | 否 |  |

### `formula_publish` 发布记录。``status=pending`` 承载非 admin 提交的全局候选（admin 审核后执行）。

模型：`formula_setting_models.FormulaPublish`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `domain` | 域 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `target` | 目标 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `template_id` | 模板编号 | （据字段名） | 编号 |  | 是 |  |
| `source` | 来源 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `source_project_id` | 来源项目编号 | （据字段名） | 编号 |  | 是 |  |
| `request_id` | 请求号 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `change_set` | 变更集 | （据字段名） | JSON |  | 否 |  |
| `summary` | 摘要 | （据字段名） | JSON |  | 否 |  |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `published_by` | 发布人 | （据字段名） | 编号 |  | 是 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 否 |  |
| `reviewed_by` | 复核人 | （据字段名） | 编号 |  | 是 |  |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |

### `formula_push_run` 公式推送运行记录（面板「最近推送」）。

模型：`formula_push_models.FormulaPushRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `trigger_source` | 触发来源 | TRIAL_BALANCE_UPDATED / WORKPAPER_SAVED / `manual` 手工 | 文本（≤40 字） |  | 否 |  |
| `triggered_by` | 触发人 | 手动触发的用户；事件触发为 NULL | 编号 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `written_count` | 写入数量 | （据字段名） | 整数 |  | 否 |  |
| `unchanged_count` | 未变数量 | （据字段名） | 整数 |  | 否 |  |
| `kept_count` | 保留数量 | （据字段名） | 整数 |  | 否 |  |
| `skipped_count` | 跳过数量 | （据字段名） | 整数 |  | 否 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `formula_push_state` 公式推送目标级状态。

模型：`formula_push_models.FormulaPushState`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `addr_id` | 目标格子 | 推到哪个格子；底稿如 `E1/E1-1/行/字段`；附注如 `note://五、1/表/行.end` | 文本（≤512 字） |  | 否 |  |
| `rule_id` | 推送规则 | 用的哪条规则 | 文本（≤128 字） |  | 否 |  |
| `domain` | 目标类型 | `workpaper` 底稿 / `note` 附注 | 文本（≤20 字） |  | 否 |  |
| `wp_id` | 目标底稿 | （据字段名） | 编号 |  | 是 | working_paper.id |
| `note_section` | 附注章节 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `last_pushed_value` | 上次推送的值 | 系统上次写进去的数。格子当前值和它不一样，说明人改过，系统就不再覆盖；为空表示从没推送过 | JSON |  | 是 |  |
| `last_formula_value` | 最近公式值 | 按字段名理解，代码里没有说明 | JSON |  | 是 |  |
| `current_value` | 格子当前值 | 按字段名理解，代码里没有说明 | JSON |  | 是 |  |
| `provenance` | 来源记录 | 计算尝试 + 最终值状态双层来源信封。 | JSON |  | 是 |  |
| `state` | 格子状态 | `auto` 自动 / `manual` 人工改过 / `locked` 锁定 / `pending_confirm` 待确认 | 文本（≤20 字） |  | 否 |  |
| `last_run_id` | 最近推送批次 | （据字段名） | 编号 |  | 是 | formula_push_run.id |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_by` | 最后处理人 | 人工采用或锁定时记人，系统推送时为空 | 编号 |  | 是 |  |

### `formula_runtime_outbox` 公式运行时事务 Outbox — 与业务写入同事务提交，提交后可靠发布 stale/invalidation 事件。

模型：`workpaper_models.FormulaRuntimeOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `event_key` | 事件键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `run_id` | 运行编号 | 指向 `draft_refresh_audit` | 编号 |  | 否 | draft_refresh_audit.id |
| `event_type` | 事件类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 否 |  |
| `attempts` | 尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `delivered_at` | 已投递时间 | （据字段名） | 时间 |  | 是 |  |
| `last_error` | 最近错误 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `formula_setting` 统一公式设置行：``layer`` = global（全局）/ project（本项目适配）/ template（模板）。

模型：`formula_setting_models.FormulaSetting`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `domain` | 域 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `layer` | 层级 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `template_id` | 模板编号 | 指向 `formula_template` | 编号 |  | 是 | formula_template.id |
| `slot_key` | 位置键 | （据字段名） | 长文本 |  | 否 |  |
| `slot_label` | 位置显示名 | （据字段名） | 长文本 |  | 是 |  |
| `definition` | 定义 | （据字段名） | JSON |  | 否 |  |
| `definition_hash` | 定义哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `base_version` | 基准版本 | （据字段名） | 整数 |  | 是 |  |
| `base_definition` | 基准定义 | （据字段名） | JSON |  | 是 |  |
| `pinned` | 固定 | （据字段名） | 是 / 否 |  | 否 |  |
| `base_origin` | 基准来源 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `base_template_id` | 基准模板编号 | （据字段名） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `formula_sync_item` 待项目确认的同步事项。同一项目同一公式位只保留一条 pending（后续发布更新它）。

模型：`formula_setting_models.FormulaSyncItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `domain` | 域 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `slot_key` | 位置键 | （据字段名） | 长文本 |  | 否 |  |
| `slot_label` | 位置显示名 | （据字段名） | 长文本 |  | 是 |  |
| `reason` | 原因 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `upstream_origin` | 上游来源 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `upstream_template_id` | 上游模板编号 | （据字段名） | 编号 |  | 是 |  |
| `base_definition` | 基准定义 | （据字段名） | JSON |  | 是 |  |
| `upstream_definition` | 上游定义 | （据字段名） | JSON |  | 是 |  |
| `local_definition` | 本地定义 | （据字段名） | JSON |  | 是 |  |
| `upstream_version` | 上游版本 | （据字段名） | 整数 |  | 是 |  |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `publish_id` | 发布编号 | （据字段名） | 编号 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `resolution` | 处理结果 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `resolved_definition` | 解决定义 | （据字段名） | JSON |  | 是 |  |
| `resolved_by` | 解决人 | （据字段名） | 编号 |  | 是 |  |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `formula_template` 可共享的公式模板（名称 / 共享范围 / 适用准则 / 当前版本）。

模型：`formula_setting_models.FormulaTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `share_scope` | 股份范围 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `owner_user_id` | 负责人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `owner_project_id` | 负责人项目编号 | 指向 `projects` | 编号 |  | 是 | projects.id |
| `applicable_scope` | 适用范围 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `domains` | 域 | （据字段名） | JSON |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `formula_template_subscription` 项目订阅模板（每个项目每个域最多一个有效订阅）。

模型：`formula_setting_models.FormulaTemplateSubscription`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `domain` | 域 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `template_id` | 模板编号 | 指向 `formula_template` | 编号 |  | 否 | formula_template.id |
| `template_version` | 模板版本 | （据字段名） | 整数 |  | 否 |  |
| `pinned` | 固定 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `subscribed_by` | 订阅人 | （据字段名） | 编号 |  | 是 |  |
| `subscribed_at` | 订阅时间 | （据字段名） | 时间 |  | 否 |  |
| `unsubscribed_at` | 退订时间 | （据字段名） | 时间 |  | 是 |  |

### `formula_template_version` 模板每次发布的冻结快照（三方比对、回看、暂缓订阅者读取）。

模型：`formula_setting_models.FormulaTemplateVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_id` | 模板编号 | 指向 `formula_template` | 编号 |  | 否 | formula_template.id |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `snapshot` | 快照 | （据字段名） | JSON |  | 否 |  |
| `change_set` | 变更集 | （据字段名） | JSON |  | 否 |  |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `published_by` | 发布人 | （据字段名） | 编号 |  | 是 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 否 |  |

### `note_formula_run` 一个章节一次附注公式执行的可查询运行记录。

模型：`note_formula_models.NoteFormulaRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `note_section` | 附注章节号 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `trigger` | 触发 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `triggered_by` | 触发人 | 指向 `users` | 编号 |  | 是 | users.id |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `executed_count` | 执行数量 | （据字段名） | 整数 |  | 否 |  |
| `updated_count` | 更新数量 | （据字段名） | 整数 |  | 否 |  |
| `failed_count` | 失败数量 | （据字段名） | 整数 |  | 否 |  |
| `error_summary` | 错误摘要 | （据字段名） | 长文本 |  | 是 |  |

### `wp_formula` 自定义底稿公式绑定（独立表，custom-workpaper-formula-binding）

模型：`workpaper_models.WpFormula`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `sheet_name` | 表页名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `target_cell` | 目标单元格 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `expression` | 表达式 | （据字段名） | 长文本 |  | 否 |  |
| `category` | 类别 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `formula_type` | 公式类型 | 三类型公式治理 + 最近计算时间 + 规范化引用 + 初稿语义/来源标记。；formula_type ∈ {auto_calc, logic_check, reasonability} | 文本（≤20 字） |  | 否 |  |
| `lifecycle_state` | 生命周期状态 | lifecycle_state ∈ {saved, validated, executing, `succeeded` 成功, `failed` 失败, stale, `rolled_back` 已回滚} | 文本（≤20 字） |  | 否 |  |
| `definition_version` | 定义版本 | 定义版本：每次保存定义递增 | 整数 |  | 否 |  |
| `definition_hash` | 定义哈希 | 定义 hash：由影响执行的定义字段（expression, formula_type, refs）计算 | 文本（≤64 字） |  | 是 |  |
| `last_computed_at` | 最近计算时间 | （据字段名） | 时间 |  | 是 |  |
| `refs` | 引用 | 都能解析为合法空 JSON 数组（同 custom_query_models / review_template_models 约定）。 | JSON |  | 否 |  |
| `issue_description` | 问题说明 | （据字段名） | 长文本 |  | 是 |  |
| `hint_text` |  | 未查明 | 长文本 |  | 是 |  |
| `formula_source` | 公式来源 | formula_source ∈ {preset, `custom` 自定义, reference} | 文本（≤20 字） |  | 否 |  |
| `reference_formula_id` | 引用公式编号 | reference 来源指向被参照源公式；非 reference 来源为 NULL | 编号 |  | 是 |  |
| `source_scope` | 来源范围 | 公式来源范围与可审阅绑定；与页面分类 formula_scope_query 解耦。 | JSON |  | 是 |  |
| `binding` |  | 未查明 | JSON |  | 是 |  |
| `stable_sheet_key` | 稳定表页键 | 目标 identity = (wp_id, stable_sheet_key, row_key, field_key)；preset_version 不入。；旧列 sheet_name/target_cell + 旧唯一索引保留一版过渡（双写共存）。；needs_review：target_cell 无法安全解析为 … | 文本（≤255 字） |  | 是 |  |
| `row_key` | 行键 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `field_key` | 字段键 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `stable_key_needs_review` | 稳定键需要复核 | （据字段名） | 是 / 否 |  | 否 |  |
| `base_version` | 基准版本 | （据字段名） | 整数 |  | 是 |  |
| `base_definition` | 基准定义 | （据字段名） | JSON |  | 是 |  |
| `pinned` | 固定 | （据字段名） | 是 / 否 |  | 否 |  |
| `base_origin` | 基准来源 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `base_template_id` | 基准模板编号 | （据字段名） | 编号 |  | 是 |  |

<a id="n-group"></a>
## N. 报表与附注

### `account_note_mapping` 科目→附注行映射 — 维护科目名称到附注表格行的映射关系

模型：`account_note_mapping_models.AccountNoteMapping`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `account_name` | 科目名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `section_id` | 章节编号 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `row_name` | 行名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `col_index` | 列序号 | （据字段名） | 整数 |  | 否 |  |
| `mapping_type` | 映射类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `accounting_standards` 会计准则

模型：`extension_models.AccountingStandard`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `standard_code` | 准则编码 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `standard_name` | 准则名称 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `standard_description` | 准则说明 | （据字段名） | 长文本 |  | 是 |  |
| `effective_date` | 生效日期 | （据字段名） | 日期 |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `audit_report` 审计报告

模型：`report_models.AuditReport`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `opinion_type` | 意见类型 | 取值：`unqualified` 无保留意见 / `qualified` 保留意见 / `adverse` 否定意见 / `disclaimer` 无法表示意见 | 枚举 |  | 否 |  |
| `company_type` | 公司类型 | 取值：`listed` 上市 / `non_listed` 非上市 | 枚举 |  | 否 |  |
| `report_date` | 报表日期 | （据字段名） | 日期 |  | 是 |  |
| `signing_partner` | 签字合伙人 | （据字段名） | 文本 |  | 是 |  |
| `paragraphs` | 段落 | （据字段名） | JSON |  | 是 |  |
| `financial_data` | 财务数据 | （据字段名） | JSON |  | 是 |  |
| `status` | 状态 | 取值：`draft` 草稿 / `review` 复核中 / `eqcr_approved` EQCR 已通过 / `final` 定稿 | 枚举 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `bound_dataset_id` | 绑定账套版本编号 | 下游快照绑定；AuditReport 绑定时机特殊：不是创建时，而是 status 转 final 时锁定（签字级合规）；指向 `ledger_datasets` | 编号 |  | 是 | ledger_datasets.id |
| `dataset_bound_at` | 账套版本绑定时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `report_body_json` | 报表正文JSON | deliverable-center | JSON |  | 是 |  |
| `is_pie` | 是否饼图 | （据字段名） | 是 / 否 |  | 是 |  |
| `prior_period_info` | 上期期间信息 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `company_subtype` | 公司子类型 | 企业子类型 + 模板详简版 + manifest 模板版本 | 文本（≤10 字） |  | 是 |  |
| `template_variant` | 模板变体 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `template_version` | 模板版本 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `representation_letter_date` | 表示形式函件日期 | CW-76: 管理层声明书签署日期（A16 signed 时用户必填，push 到此处） | 日期 |  | 是 |  |

### `audit_report_template` 审计报告段落模板

模型：`report_models.AuditReportTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `opinion_type` | 意见类型 | 取值：`unqualified` 无保留意见 / `qualified` 保留意见 / `adverse` 否定意见 / `disclaimer` 无法表示意见 | 枚举 |  | 否 |  |
| `company_type` | 公司类型 | 取值：`listed` 上市 / `non_listed` 非上市 | 枚举 |  | 否 |  |
| `section_name` | 章节名称 | （据字段名） | 文本 |  | 否 |  |
| `section_order` | 章节顺序 | （据字段名） | 整数 |  | 否 |  |
| `template_text` | 模板文本 | （据字段名） | 长文本 |  | 否 |  |
| `is_required` | 是否必填 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `cfs_adjustments` 现金流量表调整分录

模型：`report_models.CfsAdjustment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `adjustment_no` | 调整编号 | （据字段名） | 文本 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `debit_account` | 借方科目 | （据字段名） | 文本 |  | 否 |  |
| `credit_account` | 贷方科目 | （据字段名） | 文本 |  | 否 |  |
| `amount` | 金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `cash_flow_category` | 现金流量类别 | 取值：`operating` 经营活动 / `investing` 投资活动 / `financing` 筹资活动 / `supplementary` 补充资料 | 枚举 |  | 是 |  |
| `cash_flow_line_item` | 现金流量行项 | （据字段名） | 文本 |  | 是 |  |
| `entry_group_id` | 分录组 | （据字段名） | 编号 |  | 是 |  |
| `is_auto_generated` | 是否自动生成 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `disclosure_notes` 财务报表附注

模型：`report_models.DisclosureNote`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `note_section` | 章节号 | 如 `五、5`；同项目同年度不重复 | 文本 |  | 否 |  |
| `section_title` | 章节标题 | 如「应收账款」 | 文本 |  | 否 |  |
| `section_id` | 章节编号 | 组成附注目录树 | 文本（≤100 字） |  | 是 |  |
| `level` | 层级 | 组成附注目录树 | 整数 |  | 是 |  |
| `parent_section_id` | 上级章节 | 组成附注目录树 | 文本（≤100 字） |  | 是 |  |
| `sort_index` | 排序 | （据字段名） | 整数 |  | 否 |  |
| `auto_numbering` | 自动编号 | 章节号是自动排还是手工固定 | 是 / 否 |  | 否 |  |
| `lock_number` | 锁定编号 | 章节号是自动排还是手工固定 | 是 / 否 |  | 否 |  |
| `locked_number` | 锁定的编号 | 章节号是自动排还是手工固定 | 文本（≤50 字） |  | 是 |  |
| `account_name` | 对应科目 | （据字段名） | 文本 |  | 是 |  |
| `content_type` | 内容类型 | `table` 表格 / `text` 文字 / `mixed` 表格加文字 | 枚举 |  | 是 |  |
| `table_data` | 表格内容 | 表格的行、列、数值，以及每个格是自动取数、手工填写还是锁定；JSON | JSON |  | 是 |  |
| `text_content` | 正文 | 文字说明 | 长文本 |  | 是 |  |
| `guidance_text` | 编制指引 | 提示怎么写 | 长文本 |  | 是 |  |
| `source_template` | 模板版本 | `soe` 国企版 / `listed` 上市版 | 枚举 |  | 是 |  |
| `status` | 状态 | `draft` 草稿 / `confirmed` 已确认 | 枚举 |  | 否 |  |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `is_stale` | 待刷新 | 上游数据变了，附注需要刷新 | 是 / 否 |  | 否 |  |
| `stale_source` | 什么变了 | `trial_balance` 试算表 / `report` 报表 / `report_fallback` 报表（整体标记）/ `workpaper` 或 `workpaper_saved` 底稿；为空是老数据 | 文本（≤32 字） |  | 是 |  |
| `bound_dataset_id` | 绑定的账套版本 | 生成附注时用的是哪个账套版本 | 编号 |  | 是 | ledger_datasets.id |
| `dataset_bound_at` | 绑定时间 | 生成附注时用的是哪个账套版本 | 时间 |  | 是 |  |
| `is_empty` | 本期无此项 | 是 / 否 | 是 / 否 |  | 否 |  |
| `template_lineage` | 模板来源 | 系统内部用；结构未查明 | JSON |  | 是 |  |
| `is_local_override` | 本项目改过模板 | （据字段名） | 是 / 否 |  | 否 |  |
| `text_template_vars` | 正文变量 | 系统内部用；结构未查明 | JSON |  | 是 |  |
| `source_project_id` | 来源项目 | 合并附注穿透到子企业用 | 编号 |  | 是 |  |
| `consolidation_breakdown` | 合并明细 | 合并附注穿透到子企业用 | JSON |  | 是 |  |
| `last_sync_source` | 最近一次谁更新的数 | `workpaper` 底稿推送 / `workpaper_html` 网页底稿推送 / `formula_push` 公式推送 | 文本（≤50 字） |  | 是 |  |
| `last_sync_wp_id` | 最近同步的底稿 | （据字段名） | 编号 |  | 是 | working_paper.id |
| `last_sync_at` | 时间 | （据字段名） | 时间 |  | 是 |  |
| `last_sync_user_id` | 操作人 | （据字段名） | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `fill_preview_sessions` 报告正文模板填充 preview 会话（audit-report-template-integration V066）

模型：`report_models.FillPreviewSession`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `opinion_type` | 意见类型 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `company_subtype` | 公司子类型 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `template_variant` | 模板变体 | （据字段名） | 文本（≤10 字） |  | 是 |  |
| `template_version` | 模板版本 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `working_path` | 路径 | （据字段名） | 长文本 |  | 是 |  |
| `optional_sections_json` | 可选章节JSON | （据字段名） | JSON |  | 是 |  |
| `missing_fields` | 缺失字段 | （据字段名） | JSON |  | 是 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `financial_report` 生成的财务报表数据

模型：`report_models.FinancialReport`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `report_type` | 报表 | 同 `report_config` | 枚举 |  | 否 |  |
| `row_code` | 行编码 | 同 `report_config` | 文本 |  | 否 |  |
| `row_name` | 行名称 | 同 `report_config` | 文本 |  | 是 |  |
| `current_period_amount` | 本期金额 | 按公式算出的期末数或本期数；计算失败时保留旧值，新行为空，不写 0 | 金额（2 位小数） |  | 是 |  |
| `prior_period_amount` | 上期金额 | 资产负债表取本年期初数；利润表等取上年数；没有来源时为空 | 金额（2 位小数） |  | 是 |  |
| `formula_used` | 使用的公式 | 生成时实际用的公式 | 长文本 |  | 是 |  |
| `source_accounts` | 涉及科目 | 公式用到了哪些标准科目，例 `["1122","1231"]`；权益变动表、减值准备表这里存的是人工编辑的矩阵数据 | JSON |  | 是 |  |
| `generated_at` | 生成时间 | （据字段名） | 时间 |  | 是 |  |
| `indent_level` | 缩进 | 同 `report_config` | 整数 |  | 否 |  |
| `is_total_row` | 合计行 | 同 `report_config` | 是 / 否 |  | 否 |  |
| `is_stale` | 已过期 | 计算失败或上游数据变了，需要重新生成 | 是 / 否 |  | 否 |  |
| `blank_reason` | 留空原因 | 金额为空时写明原因；如「母公司汇总上年数未结转」 | 长文本 |  | 是 |  |
| `calc_version` | 计算版本 | 追溯是哪一次生成写的；系统内部用 | 整数 |  | 是 |  |
| `calc_error` | 失败原因 | 计算失败时的原因；成功时为空 | 文本（≤500 字） |  | 是 |  |
| `run_id` | 生成批次 | 追溯是哪一次生成写的；系统内部用 | 编号 |  | 是 | report_generation_run.id |
| `provenance` | 来源记录 | 追溯是哪一次生成写的；系统内部用 | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `group_note_template_baseline` 集团附注模板基线（D6）

模型：`report_models.GroupNoteTemplateBaseline`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `parent_project_id` | 上级项目编号 | 指向 `projects` | 编号 |  | 否 | projects.id |
| `version` | 版本号 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `parent_baseline_id` | 上级基线编号 | 指向 `group_note_template_baseline` | 编号 |  | 是 | group_note_template_baseline.id |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `sections_data` | 章节数据 | （据字段名） | JSON |  | 否 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `note_account_mappings` 附注科目对照映射 — 报表行次 → 附注章节 → 表格的三级映射

模型：`note_account_mapping.NoteAccountMapping`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 文本（≤36 字） | 是 |  |  |
| `template_type` | 模板类型 | `soe` 国企版 / `listed` 上市 | 文本（≤20 字） |  | 否 |  |
| `report_row_code` | 报表行编码 | BS-002 | 文本（≤50 字） |  | 否 |  |
| `note_section_code` | 附注章节编码 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `table_index` | 表序号 | （据字段名） | 整数 |  | 否 |  |
| `validation_role` | 校验角色 | 余额/宽表/交叉/其中项/描述 | 文本（≤30 字） |  | 是 |  |
| `wp_code` | 底稿编码 | E1/D2/F2 | 文本（≤30 字） |  | 是 |  |
| `fetch_mode` | 获取模式 | `total` 合计/`detail` 明细/`category` 分类/`change` 变动 | 文本（≤30 字） |  | 是 |  |

### `note_content_template_versions` 模板的不可变正文快照。

模型：`note_content_template_models.NoteContentTemplateVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_id` | 模板编号 | 指向 `note_content_templates` | 编号 |  | 否 | note_content_templates.id |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `schema_version` | 结构版本 | （据字段名） | 整数 |  | 否 |  |
| `source_project_id` | 来源项目编号 | 指向 `projects` | 编号 |  | 否 | projects.id |
| `source_year` | 来源年度 | （据字段名） | 整数 |  | 否 |  |
| `source_project_name` | 来源项目名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `report_scope` | 报表范围 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `sections_data` | 章节数据 | （据字段名） | JSON |  | 否 |  |
| `quality_summary` | 质量摘要 | （据字段名） | JSON |  | 否 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `byte_size` | 字节大小 | （据字段名） | 整数 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `note_content_templates` 个人或集团可见的附注内容模板目录。

模型：`note_content_template_models.NoteContentTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `owner_scope` | 负责人范围 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `owner_user_id` | 负责人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `owner_group_project_id` | 负责人组项目编号 | 指向 `projects` | 编号 |  | 是 | projects.id |
| `current_version_id` | 当前版本编号 | 指向 `note_content_template_versions` | 编号 |  | 是 | note_content_template_versions.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `note_section_instances` 附注章节实例（裁剪后的章节）

模型：`note_trim_models.NoteSectionInstance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `template_type` | 模板类型 | `soe` 国企版 / `listed` 上市 | 文本（≤20 字） |  | 否 |  |
| `section_number` | 章节编号 | 不限长：裁剪页写入口径过滤后的全部种子章节，叙述性章节以标题作编号（现算最长 42 字） | 文本 |  | 否 |  |
| `section_title` | 章节标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `status` | 状态 | `retain` 保留 / `skip` 跳过 / `not_applicable` 不适用 | 文本（≤20 字） |  | 否 |  |
| `skip_reason` | 跳过原因 | （据字段名） | 长文本 |  | 是 |  |
| `sort_order` | 排序 | （据字段名） | 整数 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `note_section_version_tree` 章节版本树（D11）

模型：`report_models.NoteSectionVersionTree`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `note_section_id` | 附注章节编号 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `branch` | 分支 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `parent_node_id` | 上级节点编号 | 指向 `note_section_version_tree` | 编号 |  | 是 | note_section_version_tree.id |
| `snapshot_data` | 快照数据 | （据字段名） | JSON |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `label` | 显示名 | （据字段名） | 文本（≤200 字） |  | 是 |  |

### `note_text_batch_applications` 一次成功的附注正文原子批量应用审计。

模型：`note_content_template_models.NoteTextBatchApplication`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `source_kind` | 来源类别 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `template_version_id` | 模板版本编号 | 指向 `note_content_template_versions` | 编号 |  | 是 | note_content_template_versions.id |
| `source_metadata` | 来源元数据 | （据字段名） | JSON |  | 否 |  |
| `target_project_id` | 目标项目编号 | 指向 `projects` | 编号 |  | 否 | projects.id |
| `target_year` | 目标年度 | （据字段名） | 整数 |  | 否 |  |
| `mutation_id` | 变更编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `request_fingerprint` | 请求指纹 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `preview_digest` | 预览摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `applied_count` | 已应用数量 | （据字段名） | 整数 |  | 否 |  |
| `mode_summary` | 模式摘要 | （据字段名） | JSON |  | 否 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `applied_by` | 已应用人 | 指向 `users` | 编号 |  | 是 | users.id |
| `applied_at` | 已应用时间 | （据字段名） | 时间 |  | 否 |  |

### `note_trim_schemes` 附注裁剪方案

模型：`note_trim_models.NoteTrimScheme`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `scheme_name` | 方案名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `trim_data` | 裁剪数据 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `note_validation_results` 附注校验结果

模型：`report_models.NoteValidationResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `validation_timestamp` | 校验时间戳 | （据字段名） | 时间 |  | 否 |  |
| `findings` | 发现 | （据字段名） | JSON |  | 否 |  |
| `error_count` | 错误数量 | （据字段名） | 整数 |  | 否 |  |
| `warning_count` | 警告数量 | （据字段名） | 整数 |  | 否 |  |
| `info_count` | 信息数量 | （据字段名） | 整数 |  | 否 |  |
| `validated_by` | 已校验人 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `report_config` 报表格式配置（行次定义+取数公式）；V199 formula_version：全局行 = 定义版本、项目行 = 本地修订号（CAS）

模型：`report_models.ReportConfig`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `report_type` | 报表 | 属于哪张报表；`balance_sheet` 资产负债表 / `income_statement` 利润表 / `cash_flow_statement` 现金流量表 / `equity_statement` 所有者权益变动表 / `cash_flow_supplement` 现金流量表补充资料 / `impairment_provision` 资产减值准备表 | 枚举 |  | 否 |  |
| `row_number` | 行次 | 显示顺序 | 整数 |  | 否 |  |
| `row_code` | 行编码 | 如 `BS-008`；资产负债表 BS、利润表 IS、现金流量表 CFS、权益变动表 EQ、补充资料 CFSS、减值准备表 IMP | 文本 |  | 否 |  |
| `row_name` | 行名称 | 如「应收账款」 | 文本 |  | 否 |  |
| `indent_level` | 缩进层级 | 显示时缩进几格 | 整数 |  | 否 |  |
| `formula` | 取数公式 | 如 `TB('1122','期末余额')-TB('1231','期末余额')` = 应收账款减坏账准备；为空表示手工填或标题行 | 长文本 |  | 是 |  |
| `formula_category` | 公式用途 | `auto_calc` 取数 / `logic_check` 逻辑审核 / `reasonability` 合理性提示 | 文本（≤20 字） |  | 是 |  |
| `formula_description` | 公式说明 | 给人看的简短说明 | 文本（≤200 字） |  | 是 |  |
| `formula_source` | 公式来源 | 如「试算表审定数」「报表行次引用」「手工填列」 | 文本（≤100 字） |  | 是 |  |
| `applicable_standard` | 适用范围 | 这行属于哪套报表；`soe_standalone` 国企单体 / `soe_consolidated` 国企合并 / `listed_standalone` 上市单体 / `listed_consolidated` 上市合并 / `project:项目id` 某项目改过的公式 | 文本 |  | 否 |  |
| `is_total_row` | 是否合计行 | 是 / 否 | 是 / 否 |  | 否 |  |
| `parent_row_code` | 上级行 | （据字段名） | 文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `aje_formula` | 调整列公式 | 试算平衡表里这一行的审计调整 / 重分类列怎么算；为空时按公式里的科目自动汇总 | 长文本 |  | 是 |  |
| `rje_formula` | 调整列公式 | 试算平衡表里这一行的审计调整 / 重分类列怎么算；为空时按公式里的科目自动汇总 | 长文本 |  | 是 |  |
| `is_stale` | 待更新 | 全局公式更新后，项目这一行被标记需要处理 | 是 / 否 |  | 否 |  |
| `formula_version` | 版本号 | 每改一次加 1，防止两人同时改 | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `base_version` | 上游版本 | 用来判断项目是否改过、全局更新后是否冲突 | 整数 |  | 是 |  |
| `base_definition` | 上游公式快照 | 用来判断项目是否改过、全局更新后是否冲突 | JSON |  | 是 |  |
| `pinned` | 是否固定 | 项目选择「暂不跟随」全局公式更新时为是 | 是 / 否 |  | 否 |  |
| `base_origin` | 跟随的上游 | 项目公式基于哪一层；`global` 全局 / `template` 公式模板 | 文本（≤16 字） |  | 是 |  |
| `base_template_id` | 上游模板 | 用来判断项目是否改过、全局更新后是否冲突 | 编号 |  | 是 |  |

### `report_config_baseline` 报表配置主模板回填候选（项目优化→主模板评审通道）

模型：`report_models.ReportConfigBaseline`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `standard` | 准则 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `report_type` | 报表类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `row_code` | 行编码 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `candidate_formula` | 候选公式 | （据字段名） | 长文本 |  | 是 |  |
| `source_project_id` | 来源项目编号 | （据字段名） | 编号 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `submitted_by` | 提交人 | （据字段名） | 编号 |  | 是 |  |
| `reviewed_by` | 复核人 | （据字段名） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `report_format_templates` 

模型：`phase10_models.ReportFormatTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_name` | 模板名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `template_type` | 模板类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `config` | 配置 | （据字段名） | JSON |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `is_default` | 是否默认 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `report_generation_run` 一次报表计算的不可变运行摘要与规范行快照。

模型：`report_generation_models.ReportGenerationRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `trigger` | 触发 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `triggered_by` | 触发人 | 指向 `users` | 编号 |  | 是 | users.id |
| `operation_id` | 操作编号 | 指向 `consol_operation` | 编号 |  | 是 | consol_operation.id |
| `operation_revision` | 操作修订号 | （据字段名） | 整数 |  | 是 |  |
| `node_key` | 节点键 | （据字段名） | 文本（≤160 字） |  | 是 |  |
| `applicable_standard` | 适用准则 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `calc_version` |  | 未查明 | 整数 |  | 否 |  |
| `changed_rows` | 变更行 | （据字段名） | 整数 |  | 否 |  |
| `recomputed_rows` |  | 未查明 | 整数 |  | 否 |  |
| `failed_rows` | 失败行 | （据字段名） | 整数 |  | 否 |  |
| `row_count` | 行数量 | （据字段名） | 整数 |  | 否 |  |
| `report_types` | 报表类型 | （据字段名） | JSON |  | 否 |  |
| `input_digest` | 输入摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `row_digest` | 行摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `rows_json` | 行JSON | （据字段名） | JSON |  | 否 |  |
| `provenance` | 来源记录 | （据字段名） | JSON |  | 否 |  |
| `error` | 错误 | （据字段名） | 长文本 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `report_line_mapping` 报表行次映射（标准科目→报表行次）

模型：`audit_platform_models.ReportLineMapping`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `standard_account_code` | 标准科目编码 | （据字段名） | 文本 |  | 否 |  |
| `report_type` | 报表类型 | 取值：`balance_sheet` 资产负债表 / `income_statement` 利润表 / `cash_flow` | 枚举 |  | 否 |  |
| `report_line_code` | 报表行编码 | （据字段名） | 文本 |  | 否 |  |
| `report_line_name` | 报表行名称 | （据字段名） | 文本 |  | 否 |  |
| `report_line_level` | 报表行级别 | （据字段名） | 整数 |  | 否 |  |
| `parent_line_code` | 上级行编码 | （据字段名） | 文本 |  | 是 |  |
| `mapping_sign` | 映射符号 | 行次聚合方向：'add' 加项 / 'subtract' 减项(备抵科目，如累计折旧/减值/库存股)。；v2 符号约定下备抵科目存自然正数，聚合到报表行次时须减去，否则净值虚增。 | 文本 |  | 否 |  |
| `mapping_type` | 映射类型 | 取值：`ai_suggested` AI 建议 / `manual` 手工 / `reference_copied` 从其他项目复制 | 枚举 |  | 否 |  |
| `is_confirmed` | 是否确认 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `report_snapshot` 报表数据快照（导出时从快照读取，不重复计算）

模型：`phase13_models.ReportSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `report_type` | 报表类型 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `generated_at` | 生成时间 | （据字段名） | 时间 |  | 否 |  |
| `data` | 数据 | （据字段名） | JSON |  | 是 |  |
| `source_trial_balance_hash` | 来源试算余额哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |

<a id="c-group"></a>
## C. 合并

### `companies` 公司信息表

模型：`consolidation_models.Company`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `company_name` | 公司名称 | （据字段名） | 文本 |  | 否 |  |
| `parent_code` | 上级编码 | （据字段名） | 文本 |  | 是 |  |
| `ultimate_code` | 最终控制方编码 | （据字段名） | 文本 |  | 否 |  |
| `consol_level` | 合并级别 | （据字段名） | 整数 |  | 否 |  |
| `shareholding` | 持股 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `consol_method` | 合并方法 | 取值：`full` / `equity` 权益 / `proportional` | 枚举 |  | 是 |  |
| `acquisition_date` | 收购日期 | （据字段名） | 日期 |  | 是 |  |
| `disposal_date` | 处置日期 | （据字段名） | 日期 |  | 是 |  |
| `functional_currency` | 记账币种 | （据字段名） | 文本（≤3 字） |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `component_auditors` 组成部分审计师表

模型：`consolidation_models.ComponentAuditor`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `firm_name` | 事务所名称 | （据字段名） | 文本 |  | 否 |  |
| `contact_person` | 联系人人 | （据字段名） | 文本 |  | 是 |  |
| `contact_info` | 联系人信息 | （据字段名） | 文本 |  | 是 |  |
| `competence_rating` | 胜任能力评级 | 取值：`reliable` 可信赖 / `additional_procedures_needed` 需追加程序 / `unreliable` 不可信赖 | 枚举 |  | 是 |  |
| `rating_basis` | 评级依据 | （据字段名） | 长文本 |  | 是 |  |
| `independence_confirmed` | 独立性确认 | （据字段名） | 是 / 否 |  | 否 |  |
| `independence_date` | 独立性日期 | （据字段名） | 日期 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `component_instructions` 组成部分审计指令表

模型：`consolidation_models.ComponentInstruction`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `component_auditor_id` | 组成部分审计师编号 | 指向 `component_auditors` | 编号 |  | 否 | component_auditors.id |
| `instruction_date` | 指令日期 | （据字段名） | 日期 |  | 是 |  |
| `due_date` | 到期日期 | （据字段名） | 日期 |  | 是 |  |
| `materiality_level` | 重要性级别 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `audit_scope_description` | 审计范围说明 | （据字段名） | 长文本 |  | 是 |  |
| `reporting_format` | 报告格式 | （据字段名） | 长文本 |  | 是 |  |
| `special_attention_items` | 特殊关注项 | （据字段名） | 长文本 |  | 是 |  |
| `instruction_file_path` | 指令文件路径 | （据字段名） | 文本 |  | 是 |  |
| `status` | 状态 | 取值：`draft` 草稿 / `sent` 已发送 / `acknowledged` 已知悉 | 枚举 |  | 否 |  |
| `sent_at` | 发送时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `component_results` 组成部分审计结果表

模型：`consolidation_models.ComponentResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `component_auditor_id` | 组成部分审计师编号 | 指向 `component_auditors` | 编号 |  | 否 | component_auditors.id |
| `received_date` | 收到日期 | （据字段名） | 日期 |  | 是 |  |
| `opinion_type` | 意见类型 | 取值：`unqualified` 无保留意见 / `qualified` 保留意见 / `adverse` 否定意见 / `disclaimer` 无法表示意见 | 枚举 |  | 是 |  |
| `identified_misstatements` | 识别出错报 | （据字段名） | JSON |  | 是 |  |
| `significant_findings` | 重大发现 | （据字段名） | 长文本 |  | 是 |  |
| `result_file_path` | 结果文件路径 | （据字段名） | 文本 |  | 是 |  |
| `group_team_evaluation` | 组团队评价 | （据字段名） | 长文本 |  | 是 |  |
| `needs_additional_procedures` | 需要追加程序 | （据字段名） | 是 / 否 |  | 否 |  |
| `evaluation_status` | 评价状态 | 取值：`pending` 待处理 / `accepted` 已接受 / `requires_followup` 需跟进 | 枚举 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_artifact` 绑定已发布 report run 的不可变合并 Excel artifact。

模型：`report_generation_models.ConsolArtifact`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `operation_id` | 操作编号 | 指向 `consol_operation` | 编号 |  | 是 | consol_operation.id |
| `operation_revision` | 操作修订号 | （据字段名） | 整数 |  | 是 |  |
| `report_run_id` | 报表运行编号 | 指向 `report_generation_run` | 编号 |  | 否 | report_generation_run.id |
| `node_key` | 节点键 | （据字段名） | 文本（≤160 字） |  | 否 |  |
| `kind` | 类别 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `storage_path` | 存储路径 | （据字段名） | 长文本 |  | 是 |  |
| `content_type` | 内容类型 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `size_bytes` | 大小字节数 | （据字段名） | 整数 |  | 是 |  |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `manifest_json` | 清单JSON | （据字段名） | JSON |  | 否 |  |
| `error` | 错误 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `ready_at` | 就绪时间 | （据字段名） | 时间 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_cell_comments` 单元格批注与复核标记 — 支持所有模块的单元格级批注和复核状态持久化

模型：`consol_cell_comment_models.ConsolCellComment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `module` | 模块 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `row_idx` | 行序号 | （据字段名） | 整数 |  | 否 |  |
| `col_idx` | 列序号 | （据字段名） | 整数 |  | 否 |  |
| `comment_type` | 意见类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `comment` | 意见 | （据字段名） | 长文本 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `row_name` | 行名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `col_name` | 列名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_note_data` 合并附注用户数据存储 — 按项目+年度+章节存储用户编辑的附注数据

模型：`consol_note_data_models.ConsolNoteData`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `section_id` | 章节编号 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `node_key` | 节点键 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `data` | 数据 | （据字段名） | JSON |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_stale` | 是否过期 | 合并推送后置真（合并数已变化，附注数据待更新）；「按公式填入」后清除 | 是 / 否 |  | 否 |  |
| `stale_reason` | 过期原因 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `stale_at` | 过期时间 | （据字段名） | 时间 |  | 是 |  |
| `cell_state` | 单元格状态 | 持久化状态（与 formula_push 三态对等） | 文本（≤20 字） |  | 否 |  |
| `locked_cells` | 锁定单元格 | 被锁定的单元格坐标列表 [{row_index, col_index}] | JSON |  | 否 |  |
| `last_formula_run_id` | 最近公式运行编号 | 最近一次公式刷新的运行批次 | 编号 |  | 是 |  |
| `last_formula_value` | 最近公式值 | 最近一次公式刷新写入的值快照（用于对比 current vs formula） | JSON |  | 是 |  |
| `source_mode` | 来源模式 | 来源投影（整章级快速分类，格级所有权仍以 data 内嵌字段为准） | 文本（≤30 字） |  | 是 |  |
| `source_operation_id` | 来源操作编号 | （据字段名） | 编号 |  | 是 |  |
| `source_revision` | 来源修订号 | （据字段名） | 整数 |  | 是 |  |
| `source_digest` | 来源摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |

### `consol_note_detail_template` 合并附注明细模板——按 template_type + section_id 组织。

模型：`consol_note_mapping_models.ConsolNoteDetailTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `section_id` | 章节编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `visibility` | 可见性 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |

### `consol_note_detail_template_version` 模板不可变版本。rows JSONB 格式：

模型：`consol_note_mapping_models.ConsolNoteDetailTemplateVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_id` | 模板编号 | 指向 `consol_note_detail_template` | 编号 |  | 否 | consol_note_detail_template.id |
| `version_number` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `rows` | 行 | （据字段名） | JSON |  | 否 |  |
| `change_note` | 变更附注 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_note_formula` 合并附注单元格取数公式（语法同报表公式：TB / SUM_TB / REPORT / ROW）。

模型：`consol_push_models.ConsolNoteFormula`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `section_id` | 章节编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `row_index` | 行序号 | （据字段名） | 整数 |  | 否 |  |
| `col_index` | 列序号 | （据字段名） | 整数 |  | 否 |  |
| `formula` | 公式 | （据字段名） | 长文本 |  | 否 |  |
| `source` | 来源 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |

### `consol_note_mapping_binding` 企业级绑定——记录每家企业确认使用哪条规则，以及绑定时的来源结构指纹。

模型：`consol_note_mapping_models.ConsolNoteMappingBinding`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `section_id` | 章节编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `entity_node_key` | 单位节点键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `entity_project_id` | 单位项目编号 | （据字段名） | 编号 |  | 否 |  |
| `rule_id` | 规则编号 | 指向 `consol_note_mapping_rule` | 编号 |  | 否 | consol_note_mapping_rule.id |
| `bound_source_hash` | 绑定来源哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `bound_at` | 绑定时间 | （据字段名） | 时间 |  | 否 |  |

### `consol_note_mapping_rule` 映射规则。mappings JSONB 格式：

模型：`consol_note_mapping_models.ConsolNoteMappingRule`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `section_id` | 章节编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `template_version_id` | 模板版本编号 | 指向 `consol_note_detail_template_version` | 编号 |  | 否 | consol_note_detail_template_version.id |
| `source_structure_hash` | 来源结构哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `version_number` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `mappings` | 映射 | （据字段名） | JSON |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_note_template_binding` 项目绑定到某一模板版本——一个项目一个章节只绑一个版本。

模型：`consol_note_mapping_models.ConsolNoteTemplateBinding`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `section_id` | 章节编号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `template_version_id` | 模板版本编号 | 指向 `consol_note_detail_template_version` | 编号 |  | 否 | consol_note_detail_template_version.id |
| `bound_by` | 绑定人 | 指向 `users` | 编号 |  | 是 | users.id |
| `bound_at` | 绑定时间 | （据字段名） | 时间 |  | 否 |  |

### `consol_note_template_push_log` 合并附注模板推送日志 —— 仅 ORM 映射，写入走 raw SQL。

模型：`consolidation_models.ConsolNoteTemplatePushLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `consol_project_id` | 合并项目编号 | （据字段名） | 编号 |  | 否 |  |
| `section_id` | 章节编号 | （据字段名） | 长文本 |  | 否 |  |
| `template_version_id` | 模板版本编号 | （据字段名） | 编号 |  | 否 |  |
| `pushed_by` | 推送人 | （据字段名） | 编号 |  | 是 |  |
| `pushed_at` | 推送时间 | （据字段名） | 时间 |  | 否 |  |
| `entity_count` | 单位数量 | （据字段名） | 整数 |  | 否 |  |
| `success_count` | 成功数量 | （据字段名） | 整数 |  | 否 |  |
| `failure_count` | 失败数量 | （据字段名） | 整数 |  | 否 |  |
| `failures` | 失败 | "unrecognized token"（回收站 / WOPI 等 SQLite 用例因此全挂）。`'[]'` 在 PG/SQLite 双方言下都能解析为 | JSON |  | 是 |  |

### `consol_operation` 一次可恢复、可比较输入版本的合并运行。

模型：`consol_operation_models.ConsolOperation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `operation_type` | 操作类型 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `idempotency_keys` | 幂等键 | （据字段名） | JSON |  | 否 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `request_payload` | 请求数据 | （据字段名） | JSON |  | 否 |  |
| `context_json` | 上下文JSON | （据字段名） | JSON |  | 否 |  |
| `version_vector` | 版本向量 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `attempt` | 尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `lease_owner` | 租约负责人 | （据字段名） | 编号 |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |
| `heartbeat_at` | 心跳时间 | （据字段名） | 时间 |  | 是 |  |
| `steps` | 步骤 | （据字段名） | JSON |  | 否 |  |
| `errors` | 错误 | （据字段名） | JSON |  | 否 |  |
| `result_refs` | 结果引用 | （据字段名） | JSON |  | 否 |  |
| `metrics` | 指标 | （据字段名） | JSON |  | 否 |  |
| `trigger_source` | 触发来源 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `triggered_by` | 触发人 | 指向 `users` | 编号 |  | 是 | users.id |
| `queued_at` | 排队时间 | （据字段名） | 时间 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `superseded_by` | 被替代（关联记录） | 指向 `consol_operation` | 编号 |  | 是 | consol_operation.id |

### `consol_push_run` 合并推送运行记录（公式管理「合并推送」页）。

模型：`consol_push_models.ConsolPushRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `operation_id` | 操作编号 | 指向 `consol_operation` | 编号 |  | 是 | consol_operation.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `trigger_source` | 触发来源 | `elimination_approved` 抵销分录通过 / `elimination_revoked` 抵销分录撤销 / `formula_changed` 公式变更 / `manual` 手工 | 文本（≤40 字） |  | 否 |  |
| `triggered_by` | 触发人 | 手动触发的用户；事件触发为 NULL | 编号 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `steps` | 步骤 | [{project_id, project_name, step, status, `detail` 明细}] | JSON |  | 否 |  |
| `warnings` | 警告 | （据字段名） | JSON |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `consol_query_template` 自定义查询模板

模型：`consolidation_models.ConsolQueryTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `row_dimension` | 行维度 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `col_dimension` | 列维度 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `value_field` | 值字段 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `filters` | 筛选条件 | （据字段名） | JSON |  | 是 |  |
| `transpose` | 转置 | （据字段名） | 是 / 否 |  | 否 |  |
| `aggregation_mode` | 汇总模式 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_scope` 合并范围表

模型：`consolidation_models.ConsolScope`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `company_name` | 公司名称 | （据字段名） | 文本 |  | 是 |  |
| `company_type` | 公司类型 | 取值：`parent` / `subsidiary` 子公司 / `associate` 联营企业 / `joint_venture` 合营企业 | 枚举 |  | 是 |  |
| `ownership_ratio` | 持股比例 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `is_included` | 是否纳入 | （据字段名） | 是 / 否 |  | 否 |  |
| `inclusion_reason` | 纳入原因 | 取值：`subsidiary` 子公司 / `associate` 联营企业 / `joint_venture` 合营企业 / `special_purpose` 特殊目的主体 | 枚举 |  | 是 |  |
| `exclusion_reason` | 排除原因 | （据字段名） | 长文本 |  | 是 |  |
| `scope_change_type` | 范围变更类型 | 取值：`none` / `new_inclusion` / `exclusion` / `method_change` | 枚举 |  | 否 |  |
| `scope_change_description` | 范围变更说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_scope_confirmation_nodes` 某确认版本中的角色投影；不是 projects 或金额数据的副本。

模型：`consol_scope_confirmation_models.ConsolScopeConfirmationNode`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_id` | 函证编号 | 指向 `consol_scope_confirmations` | 编号 |  | 否 | consol_scope_confirmations.id |
| `node_key` | 节点键 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `role` | 角色 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `kind` | 类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤100 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `host_project_id` | 宿主项目编号 | 指向 `projects` | 编号 |  | 是 | projects.id |
| `parent_node_key` | 上级节点键 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `position` | 职位 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_scope_confirmations` 合并企业树版本（V183 起名「范围确认」；V206 起推送时自动记录，手动记录仍可）。

模型：`consol_scope_confirmation_models.ConsolScopeConfirmation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `report_scope` | 报表范围 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `revision` | 修订号 | （据字段名） | 整数 |  | 否 |  |
| `fingerprint` | 指纹 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `canonical_payload` | 规范数据 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `confirmed_by` | 确认人 | 自动记录的版本可能没有触发人（系统）⇒ 可空；手动记录（user）仍写记录人；指向 `users` | 编号 |  | 是 | users.id |
| `confirmation_mode` | 函证模式 | 记录方式 user（手动「记录为新版本」/ 旧确认）/ auto（推送时自动记录） | 文本（≤10 字） |  | 否 |  |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_snapshots` 

模型：`phase10_models.ConsolSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `snapshot_data` | 快照数据 | （据字段名） | JSON |  | 否 |  |
| `trigger_reason` | 触发原因 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `diff_summary` | 差异摘要 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_trial` 合并试算表

模型：`consolidation_models.ConsolTrial`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `standard_account_code` | 标准科目 | （据字段名） | 文本 |  | 否 |  |
| `account_name` | 标准科目 | （据字段名） | 文本 |  | 是 |  |
| `account_category` | 科目类别 | 同试算表 | 枚举 |  | 是 |  |
| `individual_sum` | 个别报表汇总 | 合并范围内各子企业审定数相加 | 金额（2 位小数） |  | 否 |  |
| `consol_adjustment` | 合并调整 | 已审批的合并调整分录（存在 `elimination_entries`） | 金额（2 位小数） |  | 否 |  |
| `consol_elimination` | 合并抵销 | 已审批的抵销分录（存在 `elimination_entries`） | 金额（2 位小数） |  | 否 |  |
| `consol_amount` | 合并数 | **个别汇总 + 合并调整 + 合并抵销** | 金额（2 位小数） |  | 否 |  |
| `consolidation_breakdown` | 按企业拆分 | 每家子企业贡献了多少，例 `{"by_company": [{"company_code": "...", "amount": ...}]}` | JSON |  | 是 |  |
| `is_stale` | 待重算 | 子企业试算表变了，需要重新汇总 | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_workpaper_instance` 合并项目/年度与 A3-CONSOL 薄底稿壳的关联及最近正式产物指针。

模型：`consol_workpaper_instance_models.ConsolWorkpaperInstance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | 编号 |  | 否 | wp_index.id |
| `latest_operation_id` | 最新操作编号 | 指向 `consol_operation` | 编号 |  | 是 | consol_operation.id |
| `latest_artifact_id` | 最新产物编号 | 指向 `consol_artifact` | 编号 |  | 是 | consol_artifact.id |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_worksheet` 合并差额表 — 每个企业树节点 × 科目 × 年度一行。

模型：`consolidation_models.ConsolWorksheet`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `node_company_code` | 节点 | 格式 `企业代码:角色`，角色有 `consol` 合并户 / `consol_elim` 合并差额 / `parent` 母公司户 | 文本（≤50 字） |  | 否 |  |
| `account_code` | 科目 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `adjustment_debit` | 调整借方合计 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `adjustment_credit` | 调整贷方合计 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `elimination_debit` | 抵销借方合计 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `elimination_credit` | 抵销贷方合计 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `net_difference` | 本节点差额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `children_amount_sum` | 下级合计 | 下级节点金额相加 | 金额（2 位小数） |  | 否 |  |
| `consolidated_amount` | 合并数 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `consol_worksheet_data` 合并工作底稿数据存储 — 通用 JSON 存储，支持所有 16 张表

模型：`consol_worksheet_data_models.ConsolWorksheetData`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `data` | 数据 | （据字段名） | JSON |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |

### `elimination_entries` 抵消分录表

模型：`consolidation_models.EliminationEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `entry_no` | 分录编号 | （据字段名） | 文本 |  | 否 |  |
| `entry_type` | 分录类型 | `equity` 权益抵销 / `internal_trade` 内部交易 / `internal_ar_ap` 内部往来 / `unrealized_profit` 未实现利润 / `other` 其他 | 枚举 |  | 否 |  |
| `description` | 科目、借贷金额、摘要 | （据字段名） | 长文本 |  | 是 |  |
| `account_code` | 科目、借贷金额、摘要 | （据字段名） | 文本 |  | 否 |  |
| `account_name` | 科目、借贷金额、摘要 | （据字段名） | 文本 |  | 是 |  |
| `debit_amount` | 科目、借贷金额、摘要 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `credit_amount` | 科目、借贷金额、摘要 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `lines` | 分录明细 | 多行借贷的明细；JSON | JSON |  | 是 |  |
| `entry_group_id` | 分录组 | 同一笔分录共用 | 编号 |  | 否 |  |
| `related_company_codes` | 相关企业 | 只用于查询筛选，不影响金额 | JSON |  | 是 |  |
| `branch_entity_code` | 归属节点 | 记在哪个差额节点；为空 = 本合并项目的「合并差额」；有值 = 该企业的「母分差额」 | 文本（≤50 字） |  | 是 |  |
| `origin` | 来源 | 手工录入还是合并底稿生成；为空 = 手工；`ws_` 开头 = 合并工作底稿生成的草稿；`legacy_sheet` = 旧版明细表转入 | 文本（≤40 字） |  | 是 |  |
| `origin_key` | 来源键 | 手工录入还是合并底稿生成；为空 = 手工；`ws_` 开头 = 合并工作底稿生成的草稿；`legacy_sheet` = 旧版明细表转入 | 文本（≤200 字） |  | 是 |  |
| `source_version` | 来源版本 | 工作表自动生成草稿所绑定的来源版本向量摘要。 | JSON |  | 是 |  |
| `source_digest` | 来源摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `is_continuous` | 是否延续上年 | 连续编制的抵销分录 | 是 / 否 |  | 否 |  |
| `prior_year_entry_id` | 对应上年分录 | 连续编制的抵销分录 | 编号 |  | 是 |  |
| `review_status` | 复核状态 | `draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回。只有已通过的进合并数 | 枚举 |  | 否 |  |
| `reviewer_id` | 复核人 | （据字段名） | 编号 |  | 是 | users.id |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `forex_translation` 外币折算表

模型：`consolidation_models.ForexTranslation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本 |  | 否 |  |
| `functional_currency` | 记账币种 | （据字段名） | 文本（≤3 字） |  | 否 |  |
| `reporting_currency` | 报告币种 | （据字段名） | 文本（≤3 字） |  | 是 |  |
| `bs_closing_rate` | 资产负债表期末比率 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `pl_average_rate` | 利润表平均比率 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `equity_historical_rate` | 权益历史比率 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `opening_retained_earnings_translated` | 期初留存收益折算后 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `translation_difference` | 折算差额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `translation_difference_oci` | 折算差额其他综合收益 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `goodwill_calc` 商誉计算表

模型：`consolidation_models.GoodwillCalc`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `subsidiary_company_code` | 子公司公司编码 | （据字段名） | 文本 |  | 否 |  |
| `acquisition_date` | 收购日期 | （据字段名） | 日期 |  | 是 |  |
| `acquisition_cost` | 收购成本 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `identifiable_net_assets_fv` | 可辨认净额资产公允价值 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `parent_share_ratio` | 上级股份比例 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `goodwill_amount` | 商誉金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `accumulated_impairment` | 累计减值 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `current_year_impairment` | 当前年度减值 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `carrying_amount` | 账面金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `is_negative_goodwill` | 是否负数商誉 | （据字段名） | 是 / 否 |  | 否 |  |
| `negative_goodwill_treatment` | 负数商誉处理方式 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `internal_ar_ap` 内部往来表

模型：`consolidation_models.InternalArAp`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `debtor_company_code` | 债务方公司编码 | （据字段名） | 文本 |  | 否 |  |
| `creditor_company_code` | 债权方公司编码 | （据字段名） | 文本 |  | 否 |  |
| `debtor_amount` | 债务方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `creditor_amount` | 债权方金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `difference_amount` | 差额金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `difference_reason` | 差额原因 | （据字段名） | 长文本 |  | 是 |  |
| `reconciliation_status` | 核对状态 | 取值：`matched` 已核对一致 / `unmatched` 未核对一致 / `adjusted` 已调整 | 枚举 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `internal_trade` 内部交易表

模型：`consolidation_models.InternalTrade`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `seller_company_code` | 卖方公司编码 | （据字段名） | 文本 |  | 否 |  |
| `buyer_company_code` | 买方公司编码 | （据字段名） | 文本 |  | 否 |  |
| `trade_type` | 交易类型 | 取值：`goods` 商品 / `services` 服务 / `assets` 资产 / `other` 其他 | 枚举 |  | 是 |  |
| `trade_amount` | 交易金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `cost_amount` | 成本金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `unrealized_profit` | 未实现利润 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `inventory_remaining_ratio` | 存货剩余比例 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `minority_interest` 少数股东权益表

模型：`consolidation_models.MinorityInterest`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `subsidiary_company_code` | 子公司公司编码 | （据字段名） | 文本 |  | 否 |  |
| `subsidiary_net_assets` | 子公司净额资产 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `minority_share_ratio` | 少数股东股份比例 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `minority_equity` | 少数股东权益 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `subsidiary_net_profit` | 子公司净额利润 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `minority_profit` | 少数股东利润 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `minority_equity_opening` | 少数股东权益期初 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `minority_equity_movement` | 少数股东权益变动 | （据字段名） | JSON |  | 是 |  |
| `is_excess_loss` | 是否超出损失 | （据字段名） | 是 / 否 |  | 否 |  |
| `excess_loss_amount` | 超出损失金额 | （据字段名） | 金额（2 位小数） |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `share_change_event` 动态股比变动事件。

模型：`share_change_event_models.ShareChangeEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤50 字） |  | 否 |  |
| `node_key` | 节点键 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `effective_date` | 生效日期 | （据字段名） | 日期 |  | 是 |  |
| `sequence` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `before_ratio` | 之前比例 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `after_ratio` | 之后比例 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `ratio_delta` | 比例差值 | （据字段名） | 数值（6 位小数） |  | 是 |  |
| `change_type` | 变更类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `amount` | 金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `equity_adjustment` | 权益调整 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `source_type` | 来源类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `source_row_id` | 来源行编号 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `source_sheet_key` | 来源表页键 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `review_status` | 复核状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `calculation_version` |  | 未查明 | 整数 |  | 否 |  |
| `detail` | 明细 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="q-group"></a>
## Q. 复核、质控、EQCR 与签发

### `annual_independence_declarations` 年度独立性声明（R5 需求 12）+ 项目级独立性声明（R1 需求 10 合并）。

模型：`independence_models.AnnualIndependenceDeclaration`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `declarant_id` | 声明人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `declaration_year` | 声明年度 | （据字段名） | 整数 |  | 否 |  |
| `answers` | 答复 | （据字段名） | JSON |  | 是 |  |
| `attachments` | 附件 | （据字段名） | JSON |  | 是 |  |
| `risk_flagged_count` | 风险已标记数量 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 是 |  |
| `signed_at` | 签字时间 | （据字段名） | 时间 |  | 是 |  |
| `signature_record_id` | 签名记录编号 | （据字段名） | 编号 |  | 是 |  |
| `reviewed_by_qc_id` | 复核人质控编号 | （据字段名） | 编号 |  | 是 |  |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `audit_check_signoff` 审计检查复核门禁签认（audit-check-review-gate-hardening / V126）。

模型：`audit_platform_models.AuditCheckSignoff`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `signed_by` | 签字人 | （据字段名） | 编号 |  | 否 |  |
| `signed_by_name` | 签字人名称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `signed_at` | 签字时间 | （据字段名） | 时间 |  | 否 |  |
| `summary_snapshot` | 摘要快照 | {decided,`passed` 通过,`failed` 失败,uncovered,pass_rate,blocking_count} | JSON |  | 否 |  |
| `blocking_present` | 阻断存在 | （据字段名） | 是 / 否 |  | 否 |  |
| `note` | 附注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |

### `cell_annotations` 

模型：`phase10_models.CellAnnotation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `object_type` | 对象类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 否 |  |
| `annotation_type` | 批注类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `cell_ref` | 单元格引用 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 否 |  |
| `priority` | 优先级 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `author_id` | 作者编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `mentioned_user_ids` | 提及用户列表 | （据字段名） | JSON |  | 是 |  |
| `linked_annotation_id` | 关联批注编号 | （据字段名） | 编号 |  | 是 |  |
| `conversation_id` | 会话编号 | （据字段名） | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `eqcr_disagreement_resolutions` EQCR 与项目组意见不一致时触发的合议结论。

模型：`eqcr_models.EqcrDisagreementResolution`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `eqcr_opinion_id` | EQCR 复核意见编号 | 指向 `eqcr_opinions` | 编号 |  | 否 | eqcr_opinions.id |
| `participants` | 参与者 | （据字段名） | JSON |  | 是 |  |
| `resolution` | 处理结果 | （据字段名） | 长文本 |  | 是 |  |
| `resolution_verdict` | 处理结果结论 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `eqcr_opinions` EQCR 对判断类事项的意见留痕。

模型：`eqcr_models.EqcrOpinion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `domain` | 域 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `verdict` | 结论 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `comment` | 意见 | （据字段名） | 长文本 |  | 是 |  |
| `extra_payload` | 额外数据 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `eqcr_review_notes` EQCR 独立复核笔记（默认仅 EQCR 可见）。

模型：`eqcr_models.EqcrReviewNote`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 是 |  |
| `shared_to_team` | 共享到团队 | （据字段名） | 是 / 否 |  | 否 |  |
| `shared_at` | 共享时间 | （据字段名） | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `eqcr_shadow_computations` EQCR 独立跑一遍勾稽的结果永久留痕。

模型：`eqcr_models.EqcrShadowComputation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `computation_type` | 计算类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `params` | 参数 | （据字段名） | JSON |  | 是 |  |
| `result` | 结果 | （据字段名） | JSON |  | 是 |  |
| `team_result_snapshot` | 团队结果快照 | （据字段名） | JSON |  | 是 |  |
| `has_diff` | 是否有差异 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `eqcr_snapshots` EQCR 快照 — 聚合项目数据供独立复核使用。

模型：`eqcr_models.EqcrSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `snapshot_data` | 快照数据 | （据字段名） | JSON |  | 是 |  |
| `is_current` | 是否当前 | （据字段名） | 是 / 否 |  | 否 |  |
| `judgments` | 判断 | 5 维度结构化判断 | JSON |  | 是 |  |

### `gate_decisions` 门禁决策记录表

模型：`phase14_models.GateDecision`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `gate_type` | 门禁类型 | `submit_review` 提交复核/`sign_off` 签字/`export_package` 导出包 | 文本（≤32 字） |  | 否 |  |
| `decision` | 决定 | `allow` 放行/`warn` 警告/`block` 拦截 | 文本（≤16 字） |  | 否 |  |
| `hit_rules` | 命中规则 | [{rule_code, error_code, severity, message, location, suggested_action}] | JSON |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 否 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `context` | 上下文 | （据字段名） | JSON |  | 是 |  |

### `gate_rule_configs` 门禁规则配置表 — 平台强制 vs 租户可配置分层

模型：`phase14_models.GateRuleConfig`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `rule_code` | 规则编码 | QC-15 ~ QC-26 / CONSISTENCY-BLOCK | 文本（≤32 字） |  | 否 |  |
| `config_level` | 配置级别 | `platform` 平台 / `tenant` 租户 | 文本（≤16 字） |  | 否 |  |
| `threshold_key` | 阈值键 | 如 consistency_diff_threshold / ocr_confidence_threshold | 文本（≤64 字） |  | 否 |  |
| `threshold_value` | 阈值值 | 阈值字符串，由规则自行解析 | 文本（≤128 字） |  | 否 |  |
| `tenant_id` | 租户（预留） | 通用字段，见文首 | 编号 |  | 是 |  |
| `description` | 说明 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `independence_signing_tasks` A17-7 独立性声明书电子签署任务

模型：`review_workflow_models.IndependenceSigningTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `user_id` | 用户 | （据字段名） | 编号 |  | 否 |  |
| `template_code` | 模板编码 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `signed_at` | 签字时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `issue_tickets` 统一问题单（对齐 v2 4.5.15A）

模型：`phase15_models.IssueTicket`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `task_node_id` | 任务节点编号 | （据字段名） | 编号 |  | 是 |  |
| `conversation_id` | 会话编号 | （据字段名） | 编号 |  | 是 |  |
| `source` | 来源 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `source_ref_id` | 来源引用编号 | 源对象 ID，用于双向追溯（如对应 ReviewRecord.id） | 编号 |  | 是 |  |
| `severity` | 严重程度 | `blocker` 阻断/`major` 重要/`minor` 一般/`suggestion` 建议 | 文本（≤16 字） |  | 否 |  |
| `category` | 类别 | `data_mismatch` 数据不一致/`evidence_missing` 证据缺失/... | 文本（≤64 字） |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `owner_id` | 负责人编号 | （据字段名） | 编号 |  | 否 |  |
| `due_at` | 到期时间 | （据字段名） | 时间 |  | 是 |  |
| `entity_id` | 单位编号 | （据字段名） | 编号 |  | 是 |  |
| `account_code` | 科目编码 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `status` | 状态 | `open` 未处理/`in_fix` 整改中/`pending_recheck` 待复查/`closed` 已关闭/`rejected` 已驳回 | 文本（≤20 字） |  | 否 |  |
| `thread_id` | 线程编号 | （据字段名） | 编号 |  | 是 |  |
| `evidence_refs` | 证据引用 | （据字段名） | JSON |  | 是 |  |
| `reason_code` | 原因编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `closed_at` | 关闭时间 | （据字段名） | 时间 |  | 是 |  |

### `project_quality_ratings` 项目质量评级

模型：`qc_rating_models.ProjectQualityRating`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `rating` | 评级 | 'A' \| 'B' \| 'C' \| 'D' | 文本（≤1 字） |  | 否 |  |
| `score` | 评分 | 0-100 综合得分 | 整数 |  | 否 |  |
| `dimensions` | 维度 | 各维度得分明细 {qc_pass_rate: 85, review_depth: 72, ...} | JSON |  | 是 |  |
| `computed_at` | 计算时间 | （据字段名） | 时间 |  | 否 |  |
| `computed_by_rule_version` | 计算人规则版本 | （据字段名） | 整数 |  | 否 |  |
| `override_by` | 覆盖人 | 人工 override 字段 | 编号 |  | 是 |  |
| `override_rating` | 覆盖评级 | 人工覆盖评级 | 文本（≤1 字） |  | 是 |  |
| `override_reason` | 覆盖原因 | 覆盖原因说明 | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `qc_inspection_items` 质控抽查子项

模型：`qc_inspection_models.QcInspectionItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `inspection_id` | 检查编号 | 指向 `qc_inspections` | 编号 |  | 否 | qc_inspections.id |
| `wp_id` | 底稿 | 被抽查的底稿 ID | 编号 |  | 否 |  |
| `status` | 状态 | '`pending` 待处理' \| '`in_review` 复核中' \| '`completed` 已完成' | 文本（≤20 字） |  | 否 |  |
| `findings` | 发现 | 发现的问题列表 | JSON |  | 是 |  |
| `qc_verdict` | 质控结论 | '`pass` 通过' \| '`fail` 不通过' \| 'conditional_pass' | 文本（≤20 字） |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `qc_inspection_records` 质控独立复核记录

模型：`qc_inspection_models.QcInspectionRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `inspection_item_id` | 检查项编号 | 指向 `qc_inspection_items` | 编号 |  | 否 | qc_inspection_items.id |
| `comment` | 意见 | （据字段名） | 长文本 |  | 否 |  |
| `severity` | 严重程度 | '`blocking` 阻断' \| '`warning` 警告' \| '`info` 提示' | 文本（≤20 字） |  | 否 |  |
| `cell_ref` | 单元格引用 | 单元格引用，如 'E5' | 文本（≤20 字） |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `qc_inspections` 质控抽查批次

模型：`qc_inspection_models.QcInspection`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `strategy` | 策略 | 'random' \| 'risk_based' \| 'full_cycle' \| '`mixed` 表格加文字' | 文本（≤30 字） |  | 否 |  |
| `params` | 参数 | 策略参数，如 {ratio: 0.1, cycles: ['D']} | JSON |  | 是 |  |
| `reviewer_id` | 复核人编号 | 质控复核人 | 编号 |  | 否 |  |
| `status` | 状态 | '`created` 已创建' \| '`in_progress` 进行中' \| '`completed` 已完成' \| '`cancelled` 已取消' | 文本（≤20 字） |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `report_url` | 报表地址 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `qc_rule_definitions` QC 规则定义表 — 元数据 + 开关

模型：`qc_rule_models.QcRuleDefinition`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `rule_code` | 规则编码 | QC-01 ~ QC-26 | 文本（≤30 字） |  | 否 |  |
| `severity` | 严重程度 | `blocking` 阻断 \| `warning` 警告 \| `info` 提示 | 文本（≤20 字） |  | 否 |  |
| `scope` | 范围 | `workpaper` 底稿 \| project \| `submit_review` 提交复核 \| `sign_off` 签字 \| `export_package` 导出包 \| eqcr_approval | 文本（≤30 字） |  | 否 |  |
| `category` | 类别 | 分类标签 | 文本（≤50 字） |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `standard_ref` | 准则引用 | （据字段名） | JSON |  | 是 |  |
| `expression_type` | 表达式类型 | python \| jsonpath \| sql \| regex | 文本（≤20 字） |  | 否 |  |
| `expression` | 表达式 | Python dotted path 或表达式 | 长文本 |  | 是 |  |
| `parameters_schema` | 参数结构 | JSON Schema for rule params | JSON |  | 是 |  |
| `enabled` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `review_checklist_records` 复核检查表记录（A21~A25 各级勾选+意见）

模型：`review_workflow_models.ReviewChecklistRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `template_code` | 模板编码 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `reviewer_id` | 复核人编号 | （据字段名） | 编号 |  | 否 |  |
| `items` | 项 | （据字段名） | JSON |  | 否 |  |
| `opinion` | 意见 | （据字段名） | 长文本 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `review_conversations` 

模型：`phase10_models.ReviewConversation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `initiator_id` | 发起人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `target_id` | 目标编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `related_object_type` | 相关对象类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `related_object_id` | 相关对象编号 | （据字段名） | 编号 |  | 是 |  |
| `cell_ref` | 单元格引用 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `closed_at` | 关闭时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `resolved_at` | 解决时间 | 扩展列 | 时间 |  | 是 |  |
| `resolution_code` | 处理结果编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `sla_due_at` |  | 未查明 | 时间 |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `priority` | 优先级 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `resolved_by` | 解决人 | （据字段名） | 编号 |  | 是 |  |
| `checklist_ref` | 清单引用 | 关联 A21~A25 检查要点 | 文本（≤20 字） |  | 是 |  |

### `review_messages` 

模型：`phase10_models.ReviewMessage`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `conversation_id` | 会话编号 | 指向 `review_conversations` | 编号 |  | 否 | review_conversations.id |
| `sender_id` | 发送人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `content` | 内容 | （据字段名） | 长文本 |  | 否 |  |
| `message_type` | 消息类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `attachment_path` | 附件路径 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `finding_id` | 发现编号 | （据字段名） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `trace_id` | 追踪号 | 扩展列 | 文本（≤100 字） |  | 是 |  |
| `reply_to` | 回函到 | （据字段名） | 编号 |  | 是 |  |
| `redaction_flag` |  | 未查明 | 是 / 否 |  | 否 |  |
| `edited_at` | 编辑时间 | （据字段名） | 时间 |  | 是 |  |
| `reason_code` | 原因编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `message_version` | 消息版本 | （据字段名） | 整数 |  | 否 |  |
| `mentions` |  | 未查明 | JSON |  | 是 |  |
| `thread_id` | 线程编号 | （据字段名） | 编号 |  | 是 |  |
| `sender_role` | 发送人角色 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_user_id` | 目标用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `target_user_name` | 目标用户名称 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `target_role` | 目标角色 | （据字段名） | 文本（≤50 字） |  | 是 |  |

### `review_records` 复核批注

模型：`workpaper_models.ReviewRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `cell_reference` | 单元格引用 | （据字段名） | 文本 |  | 是 |  |
| `comment_text` | 意见文本 | （据字段名） | 长文本 |  | 否 |  |
| `commenter_id` |  | 指向 `users` | 编号 |  | 否 | users.id |
| `status` | 状态 | 取值：`open` 未处理 / `replied` 已回复 / `resolved` 已解决 | 枚举 |  | 否 |  |
| `reply_text` | 回函文本 | （据字段名） | 长文本 |  | 是 |  |
| `replier_id` |  | 指向 `users` | 编号 |  | 是 | users.id |
| `replied_at` |  | 未查明 | 时间 |  | 是 |  |
| `resolved_by` | 解决人 | 指向 `users` | 编号 |  | 是 | users.id |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `conversation_id` | 会话编号 | 关联的多轮讨论链（可选）；指向 `review_conversations` | 编号 |  | 是 | review_conversations.id |
| `priority` | 优先级 | must_fix=必须修改 / suggest=建议修改 / info=仅供参考 | 文本（≤10 字） |  | 否 |  |
| `source_sheet` | 来源表页 | 源 sheet 名（复核模板的复核记录 sheet） | 文本（≤100 字） |  | 是 |  |
| `target_sheet` | 目标表页 | 目标 sheet 名（被复核底稿） | 文本（≤100 字） |  | 是 |  |
| `target_cell` | 目标单元格 | 目标 cell（如 R41） | 文本（≤50 字） |  | 是 |  |
| `review_layer` | 复核层级 | 复核层级: L1/L2/L3/L4/L5/committee/it/tax | 文本（≤20 字） |  | 是 |  |
| `evidence_refs` | 证据引用 | 关联的 EvidenceRef 列表（底稿单元格、附件、报告段落、附注表格） | JSON |  | 是 |  |
| `close_evidence_refs` | 关闭证据引用 | 关闭依据 EvidenceRef 列表（重大复核意见关闭时必填） | JSON |  | 是 |  |
| `close_reason` | 关闭原因 | 关闭说明（重大复核意见关闭时必填） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `review_templates` 复核意见模板

模型：`review_template_models.ReviewTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 否 |  |
| `applicable_cycles` | 适用循环 | （据字段名） | JSON |  | 否 |  |
| `priority_tag` |  | 未查明 | 文本（≤20 字） |  | 否 |  |
| `use_count` | 使用数量 | （据字段名） | 整数 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `review_threads` V095: 复核对话线程 — 每个底稿区域一个线程

模型：`phase10_models.ReviewThread`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `section_id` | 章节编号 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `thread_key` | 线程键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `reviewer_metrics_snapshots` 复核人深度指标快照

模型：`qc_rating_models.ReviewerMetricsSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `reviewer_id` | 复核人编号 | （据字段名） | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `snapshot_date` | 快照日期 | （据字段名） | 日期 |  | 否 |  |
| `avg_review_time_min` | 平均复核时间最小 | （据字段名） | 小数 |  | 是 |  |
| `avg_comments_per_wp` |  | 未查明 | 小数 |  | 是 |  |
| `rejection_rate` | 驳回比率 | 0.0 ~ 1.0 | 小数 |  | 是 |  |
| `qc_rule_catch_rate` |  | 0.0 ~ 1.0 | 小数 |  | 是 |  |
| `sampled_rework_rate` |  | 0.0 ~ 1.0 | 小数 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `signature_records` 签名记录

模型：`extension_models.SignatureRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `object_type` | 对象类型 | `working_paper` 底稿/`adjustment` 调整分录/`audit_report` 审计报告 | 文本（≤50 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 否 |  |
| `signer_id` | 签字人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `signature_level` | 签名级别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `required_order` | 必填顺序 | 三级/多级签字顺序与前置依赖（R5 扩至 order=4/5 EQCR + 归档签字） | 整数 |  | 是 |  |
| `required_role` | 必填角色 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `prerequisite_signature_ids` |  | 未查明 | JSON |  | 是 |  |
| `signature_data` | 签名数据 | （据字段名） | JSON |  | 是 |  |
| `signature_timestamp` | 签名时间戳 | （据字段名） | 时间 |  | 是 |  |
| `ip_address` | IP 地址地址 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `workpaper_review_records` 工作底稿复核记录

模型：`collaboration_models.WorkpaperReviewRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `workpaper_id` | 底稿编号 | （据字段名） | 编号 |  | 否 |  |
| `workpaper_type` | 底稿类型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `reviewer_id` | 复核人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `review_date` | 复核日期 | （据字段名） | 时间 |  | 否 |  |
| `review_status` | 复核状态 | 必须用同一个 ReviewStatus。原先映射 ApprovalStatus(pending/…) 时写入 pending 抛；InvalidTextRepresentation。；取值：`draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回 | 枚举 |  | 否 |  |
| `comments` | 意见 | （据字段名） | 长文本 |  | 是 |  |
| `issues_found` | 问题找到 | （据字段名） | 整数 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_qc_results` 底稿质量自检结果

模型：`workpaper_models.WpQcResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `check_timestamp` | 检查时间戳 | （据字段名） | 时间 |  | 否 |  |
| `findings` | 发现 | （据字段名） | JSON |  | 否 |  |
| `passed` |  | 未查明 | 是 / 否 |  | 否 |  |
| `blocking_count` | 阻断数量 | （据字段名） | 整数 |  | 否 |  |
| `warning_count` | 警告数量 | （据字段名） | 整数 |  | 否 |  |
| `info_count` | 信息数量 | （据字段名） | 整数 |  | 否 |  |
| `checked_by` | 检查人 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="e-group"></a>
## E. 附件、证据、OCR 与函证

### `archive_manifest_edges` ArchiveManifestEdge（design §4.6；R11/P23）—— manifest 冻结的证据图边；append-only。

模型：`evidence_governance_models.ArchiveManifestEdge`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `archive_manifest_id` | 归档清单编号 | 指向 `archive_manifests` | 编号 |  | 否 | archive_manifests.id |
| `source_type` | 来源类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `source_id` | 来源编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `target_type` | 目标类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `relation` | 关系 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `edge_hash` | 边哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `archive_manifest_entries` ArchiveManifestEntry（design §4.6；R11/P23）—— manifest 覆盖的证据节点；append-only。

模型：`evidence_governance_models.ArchiveManifestEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `archive_manifest_id` | 归档清单编号 | 指向 `archive_manifests` | 编号 |  | 否 | archive_manifests.id |
| `node_type` | 节点类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `node_id` | 节点编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `node_version` | 节点版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `node_hash` | 节点哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `node_state` | 节点状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `archive_manifests` ArchiveManifest（design §4.6/§5.5；R11/P24）—— sealed 后不可变，每次归档递增版本。

模型：`evidence_governance_models.ArchiveManifest`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `watermark` | 水印 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `policy_version` | 策略版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `retention_policy_version` | 保留策略版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `package_hash` | 包哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `blocking_difference_report` | 阻断差额报表 | （据字段名） | JSON |  | 是 |  |
| `sealed_at` | 已封存时间 | （据字段名） | 时间 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `attachment_lineage` 附件溯源关联

模型：`attachment_lineage_model.AttachmentLineage`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `attachment_id` | 附件编号 | （据字段名） | 编号 |  | 否 |  |
| `target_type` | 目标类型 | `wp_cell` 底稿单元格 / `report_row` 报表行 / `note_section` 附注章节 | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 编号 |  | 是 |  |
| `target_ref` | 目标引用 | 精确位置引用，如 "D2-3!B5" | 文本（≤200 字） |  | 是 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `attachment_versions` 不可变内容快照（design §4.3）。

模型：`evidence_governance_models.AttachmentVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `attachment_id` | 附件编号 | （据字段名） | 编号 |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `storage_type` | 存储类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `storage_key` | 存储键 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `media_type` | 媒体类型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `byte_size` | 字节大小 | （据字段名） | 整数 |  | 是 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `blob_id` | 文件内容编号 | 指向 `asset_blobs` | 编号 |  | 是 | asset_blobs.id |
| `config_snapshot` | 配置快照 | （据字段名） | JSON |  | 是 |  |
| `availability` | 可用性 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `previous_version_id` | 上一版本编号 | （据字段名） | 编号 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `original_creator_unknown` | 原始创建人未知 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `attachment_working_paper` 附件-底稿关联

模型：`attachment_models.AttachmentWorkingPaper`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `attachment_id` | 附件编号 | 指向 `attachments` | 编号 |  | 否 | attachments.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `association_type` | 关联类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `row_ref` | 行引用 | 行级绑定（格式 "{sheet_name}:{row_id}"） | 文本（≤100 字） |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `working_paper_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |

### `attachments` 附件

模型：`attachment_models.Attachment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `file_name` | 文件名 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `file_type` | 文件类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 否 |  |
| `attachment_type` | 附件类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `reference_id` | 引用编号 | （据字段名） | 编号 |  | 是 |  |
| `reference_type` | 引用类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `storage_type` | 存储类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `paperless_document_id` | Paperless文档编号 | （据字段名） | 整数 |  | 是 |  |
| `ocr_status` | 识别状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `ocr_text` | 识别文本 | （据字段名） | 长文本 |  | 是 |  |
| `ocr_fields_cache` | 识别字段缓存 | （据字段名） | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `version` | 版本号 | AT-3 版本管理 | 整数 |  | 否 |  |
| `previous_version_id` | 上一版本编号 | （据字段名） | 编号 |  | 是 |  |
| `audit_year` | 审计年度 | 审计年度（早期兼容列，保留；治理字段见证据治理设计） | 整数 |  | 是 |  |
| `original_file_name` | 原始文件名称 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `source_type` | 来源类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `obtained_at` | 取得时间 | （据字段名） | 时间 |  | 是 |  |
| `provider` | 提供方 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `is_key_evidence` | 是否键证据 | （据字段名） | 是 / 否 |  | 否 |  |
| `metadata_status` | 元数据状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `metadata_missing` | 元数据缺失 | （据字段名） | JSON |  | 是 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `current_version_id` | 当前版本编号 | （据字段名） | 编号 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `original_creator_unknown` | 原始创建人未知 | （据字段名） | 是 / 否 |  | 否 |  |
| `ocr_confirmed_sha256` | 识别确认SHA256 哈希 | 识别文本确认留痕；确认有效 = ocr_confirmed_sha256 等于当前全文 sha256（判定在 services/attachment_ocr_text.py） | 文本（≤64 字） |  | 是 |  |
| `ocr_confirmed_by` | 识别确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `ocr_confirmed_at` | 识别确认时间 | （据字段名） | 时间 |  | 是 |  |
| `ocr_confirmed_edited` | 识别确认编辑 | （据字段名） | 是 / 否 |  | 是 |  |

### `citation_snapshots` CitationSnapshot（design §4.6；R7/P15/P16）—— 不可变（immutable 触发器）。

模型：`evidence_governance_models.CitationSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ai_content_log_id` | AI内容日志编号 | 指向 `ai_content_log` | 编号 |  | 否 | ai_content_log.id |
| `evidence_ref_id` | 证据引用编号 | 指向 `evidence_refs` | 编号 |  | 否 | evidence_refs.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `target_version` | 目标版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `target_hash` | 目标哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `page` | 页 | （据字段名） | 整数 |  | 是 |  |
| `region` | 地区 | （据字段名） | JSON |  | 是 |  |
| `excerpt_hash` | 摘录哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `index_version` | 序号版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `locator_version` | 定位版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_action_log` 函证操作审计留痕（append-only，DB 触发器禁 UPDATE/DELETE）

模型：`confirmation_models.ConfirmationActionLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_id` | 函证编号 | （据字段名） | 编号 |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `action` | 动作 | `reverse` 冲回 / `apply_reply` 登记回函 / `match_assign` 匹配分配 / `attachment_link` 挂附件 / `attachment_unlink` 解除附件 | 文本（≤24 字） |  | 否 |  |
| `from_status` | 从状态 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `to_status` | 到状态 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `ocr_original` | 识别原始 | （据字段名） | JSON |  | 是 |  |
| `final_value` | 最终值 | （据字段名） | JSON |  | 是 |  |
| `attachment_id` | 附件编号 | （据字段名） | 编号 |  | 是 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_ai_check` 函证AI检查

模型：`ai_models.ConfirmationAICheck`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号 |  | 否 | confirmation_lists.id |
| `check_type` | 检查类型 | 取值：`address_verify` / `reply_ocr` / `amount_compare` / `seal_check` | 枚举 |  | 否 |  |
| `check_result` | 检查结果 | （据字段名） | JSON |  | 是 |  |
| `risk_level` | 风险级别 | 取值：`high` 高 / `medium` 中 / `low` 低 / `pass_` | 枚举 |  | 是 |  |
| `human_confirmed` | 人工确认 | （据字段名） | 是 / 否 |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_attachment_link` 函证↔附件关联（含角色、强配对、匹配状态）

模型：`confirmation_models.ConfirmationAttachmentLink`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_id` | 函证编号 | 指向 `confirmations` | 编号 |  | 否 | confirmations.id |
| `attachment_id` | 附件编号 | 指向 `attachments` | 编号 |  | 否 | attachments.id |
| `role` | 角色 | `outbound` 发出 / `inbound` 收回 | 文本（≤10 字） |  | 否 |  |
| `paired_outbound_attachment_id` | 配对发出附件编号 | 回函件强绑到具体某份发函件（role=inbound 时必填） | 编号 |  | 是 |  |
| `match_status` | 匹配状态 | manual / auto / pending（人工队列）/ assigned | 文本（≤12 字） |  | 否 |  |
| `match_evidence` | 匹配证据 | （据字段名） | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_attachments` 

模型：`collaboration_models.ConfirmationAttachment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号 |  | 否 | confirmation_lists.id |
| `file_name` | 文件名 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `uploaded_by` | 上传人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_letters` 询证函模板/内容

模型：`collaboration_models.ConfirmationLetter`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号 |  | 否 | confirmation_lists.id |
| `letter_format` | 函件格式 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `recipient_name` | 接收人名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `recipient_address` | 接收人地址 | （据字段名） | 长文本 |  | 是 |  |
| `content` | 内容 | （据字段名） | 长文本 |  | 是 |  |
| `template_id` | 模板编号 | （据字段名） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_lists` 

模型：`collaboration_models.ConfirmationList`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `confirmation_type` | 函证类型 | 取值：`bank` / `customer` / `vendor` / `lawyer` / `other` 其他 | 枚举 |  | 否 |  |
| `confirmation_code` | 函证编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `counterparty_name` | 对方单位名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `counterparty_address` | 对方单位地址 | （据字段名） | 长文本 |  | 是 |  |
| `contact_person` | 联系人人 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `contact_email` | 联系人邮箱 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `balance_or_amount` | 余额或金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `as_of_date` | 日期 | （据字段名） | 日期 |  | 是 |  |
| `list_status` | 列表状态 | 取值：`draft` 草稿 / `approved` 已通过 / `sent` 已发送 / `received` / `reconciled` | 枚举 |  | 否 |  |
| `approved_by` | 批准人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |
| `sent_at` | 发送时间 | （据字段名） | 时间 |  | 是 |  |
| `due_date` | 到期日期 | （据字段名） | 日期 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `confirmation_results` 

模型：`collaboration_models.ConfirmationResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号 |  | 否 | confirmation_lists.id |
| `result_status` | 结果状态 | 取值：`confirmed` 已确认 / `discrepancy` / `no_response` / `alternative_procedures` | 枚举 |  | 否 |  |
| `confirmed_amount` | 确认金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `discrepancy_amount` | 差异金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `discrepancy_reason` | 差异原因 | （据字段名） | 长文本 |  | 是 |  |
| `alternative_procedures_performed` | 替代程序执行 | （据字段名） | 长文本 |  | 是 |  |
| `received_at` | 收到时间 | （据字段名） | 时间 |  | 是 |  |
| `received_by` | 收到人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmation_summaries` 询证函汇总

模型：`collaboration_models.ConfirmationSummary`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `confirmation_list_id` | 函证列表编号 | 指向 `confirmation_lists` | 编号 |  | 否 | confirmation_lists.id |
| `total_sent` | 合计发送 | （据字段名） | 整数 |  | 否 |  |
| `total_received` | 合计收到 | （据字段名） | 整数 |  | 否 |  |
| `total_agreed` | 合计核对一致 | （据字段名） | 整数 |  | 否 |  |
| `total_discrepancies` | 合计差异 | （据字段名） | 整数 |  | 否 |  |
| `summary_notes` | 摘要附注 | （据字段名） | 长文本 |  | 是 |  |
| `prepared_by` | 编制人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `confirmations` 函证记录

模型：`confirmation_models.Confirmation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `confirm_type` | 确认类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `counterparty` | 对方单位 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 是 | working_paper.id |
| `account_code` | 科目编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `book_amount` | 账面金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `confirmed_amount` | 确认金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `diff_amount` | 差异金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `diff_note` | 差异附注 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `sent_date` | 发送日期 | additive: 发函/回函日期 | 日期 |  | 是 |  |
| `reply_date` | 回函日期 | （据字段名） | 日期 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `dispatch_records` 分发记录 — 描述「哪条函证行被分发到了哪个下游底稿」

模型：`dispatch_models.DispatchRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `confirm_index` | 确认序号 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target` | 目标 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `entity_name` | 单位名称 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `account_type` | 科目类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `amount` | 金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 是 |  |
| `dispatched_by` | 分发人 | 指向 `users` | 编号 |  | 否 | users.id |
| `dispatched_at` | 分发时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `document_extracted` 单据结构化提取数据

模型：`ai_models.DocumentExtracted`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `document_scan_id` | 文档扫描编号 | 指向 `document_scan` | 编号 |  | 否 | document_scan.id |
| `field_name` | 字段名称 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `field_value` | 字段值 | （据字段名） | 长文本 |  | 是 |  |
| `confidence_score` | 置信度评分 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `human_confirmed` | 人工确认 | （据字段名） | 是 / 否 |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `document_match` 单据与账面数据匹配

模型：`ai_models.DocumentMatch`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `document_scan_id` | 文档扫描编号 | 指向 `document_scan` | 编号 |  | 否 | document_scan.id |
| `matched_voucher_no` | 匹配凭证编号 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `matched_account_code` | 匹配科目编码 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `matched_amount` | 匹配金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `match_result` | 匹配结果 | 取值：`matched` 已核对一致 / `mismatched` / `unmatched` 未核对一致 | 枚举 |  | 否 |  |
| `difference_amount` | 差额金额 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `difference_description` | 差额说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `document_scan` 单据扫描件

模型：`ai_models.DocumentScan`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `company_code` | 公司代码 | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 | 文本（≤50 字） |  | 是 |  |
| `year` | 年度 | 通用字段，见文首 | 文本（≤4 字） |  | 是 |  |
| `file_path` | 文件路径 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `document_type` | 文档类型 | 取值：`sales_invoice` / `purchase_invoice` / `bank_receipt` / `bank_statement` / `outbound_order` / `inbound_order` / `logistics_order` / `voucher` / `expense_report` / `toll_invoice` / `contract` / `customs_declaration` / `unknown` 未知 | 枚举 |  | 否 |  |
| `recognition_status` | 识别状态 | 取值：`pending` 待处理 / `processing` 处理中 / `completed` 已完成 / `failed` 失败 | 枚举 |  | 否 |  |
| `uploaded_by` | 上传人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_audit_command_roots` command-root（design §7.1；R12/P25）—— 每敏感命令+幂等键+scope 恰一个 root。

模型：`evidence_governance_models.EvidenceAuditCommandRoot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `command_type` | 命令类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `result` | 结果 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `reason_code` | 原因编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_audit_transitions` command-root 的多行 transition 审计（design §7.1；R12/P25）—— append-only。

模型：`evidence_governance_models.EvidenceAuditTransition`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 否 | evidence_audit_command_roots.id |
| `transition_type` | 状态变化类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `from_state` | 从状态 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `metadata_redacted` | 元数据脱敏 | （据字段名） | JSON |  | 是 |  |
| `at` | 时间 | （据字段名） | 时间 |  | 否 |  |

### `evidence_chain` 证据链

模型：`ai_models.EvidenceChain`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `chain_type` | 链类型 | 取值：`revenue` 收入 / `purchase` / `expense` 费用 | 枚举 |  | 否 |  |
| `source_document_id` | 来源文档编号 | （据字段名） | 编号 |  | 否 |  |
| `target_document_id` | 目标文档编号 | （据字段名） | 编号 |  | 是 |  |
| `chain_step` | 链步骤 | （据字段名） | 整数 |  | 否 |  |
| `match_status` | 匹配状态 | 取值：`matched` 已核对一致 / `mismatched` / `missing` | 枚举 |  | 否 |  |
| `mismatch_description` | 不一致说明 | （据字段名） | 长文本 |  | 是 |  |
| `risk_level` | 风险级别 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_dependencies` 统一依赖图的动态边 source→target（design §4.4；R9/P20）。

模型：`evidence_governance_models.EvidenceDependency`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 否 |  |
| `source_type` | 来源类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `source_id` | 来源编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `source_version` | 来源版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `target_type` | 目标类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `target_version` | 目标版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `acnr_addr_id` | 地址库地址编号 | （据字段名） | 文本（≤300 字） |  | 是 |  |
| `relation` | 关系 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `edge_hash` | 边哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `evidence_ref_id` | 证据引用编号 | 指向 `evidence_refs` | 编号 |  | 是 | evidence_refs.id |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_inbox` inbox（design §5.4；R12）—— 按 event_id 幂等消费，避免重复副作用。

模型：`evidence_governance_models.EvidenceInbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `event_id` | 事件编号 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `processed_at` | 处理时间 | （据字段名） | 时间 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_links` 证据链

模型：`wp_optimization_models.EvidenceLink`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `sheet_name` | 表页名称 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `cell_ref` | 单元格引用 | 放宽到 100：A1 单元格 / item:{槽位} / row:{行 id} | 文本（≤100 字） |  | 是 |  |
| `attachment_id` | 附件编号 | 指向 `attachments` | 编号 |  | 否 | attachments.id |
| `page_ref` | 页引用 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `evidence_type` | 证据类型 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `check_conclusion` | 检查结论 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `voucher_key` | 凭证键 | 凭证键规范串（voucher_identity.VoucherKey.to_str）：凭证检查行的原件按凭证身份挂；同一张凭证在别的底稿里可查到并引用 | 长文本 |  | 是 |  |
| `contract_key` | 契约键 | 同一份合同在别的底稿里可查到并引用（Spec F FEAT-001 F2） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_migration_checkpoints` 迁移 checkpoint（design §8.2 M1；R14/P28）—— batch_key 幂等，重跑从检查点恢复不重复对象。

模型：`evidence_governance_models.EvidenceMigrationCheckpoint`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `migration_version` | 迁移版本 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `batch_key` | 批次键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `partition_key` | 分区键 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `input_hash` | 输入哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `cursor_position` | 游标职位 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `processed_count` | 处理数量 | （据字段名） | 整数 |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_outbox` 事务性 outbox（design §5.4/§7.1；R12/R9）—— 按 event_id 幂等，有界退避 + dead_letter。

模型：`evidence_governance_models.EvidenceOutbox`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `event_id` | 事件编号 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `next_attempt_at` | 下一尝试时间 | （据字段名） | 时间 |  | 是 |  |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 是 | evidence_audit_command_roots.id |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_quality_snapshots` 质量快照（design §9；R16/P30）—— 固定不可变快照（immutable 触发器），可复算。

模型：`evidence_governance_models.EvidenceQualitySnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `snapshot_key` | 快照键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `metrics` | 指标 | （据字段名） | JSON |  | 否 |  |
| `aging_buckets` | 账龄分段 | （据字段名） | JSON |  | 是 |  |
| `issue_list` | 问题列表 | （据字段名） | JSON |  | 是 |  |
| `input_hash` | 输入哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `computed_at` | 计算时间 | （据字段名） | 时间 |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_quarantine_handles` 隔离/暂存句柄 —— 内容不可公开读取（design §4.0）。

模型：`evidence_governance_models.QuarantineHandle`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `upload_attempt_id` | 上传尝试编号 | 指向 `evidence_upload_attempts` | 编号 |  | 否 | evidence_upload_attempts.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `storage_key` | 存储键 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `handle_state` | 句柄状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `byte_size` | 字节大小 | （据字段名） | 整数 |  | 是 |  |
| `detected_media_type` | 检测到媒体类型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `is_publicly_readable` | 是否公开可读 | （据字段名） | 是 / 否 |  | 否 |  |
| `purged_at` | 清除时间 | （据字段名） | 时间 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_refs` 持久 EvidenceRef（design §4.4；R3.1）—— 可查询、可保留的持久记录（非 per-request DTO）。

模型：`evidence_governance_models.EvidenceRef`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 否 |  |
| `source_type` | 来源类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `source_id` | 来源编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `source_version` | 来源版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `evidence_type` | 证据类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `evidence_id` | 证据编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `attachment_version_id` | 附件版本编号 | 指向 `attachment_versions` | 编号 |  | 是 | attachment_versions.id |
| `target_version` | 目标版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `target_hash` | 目标哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `label` | 显示名 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `context` | 上下文 | （据字段名） | JSON |  | 是 |  |
| `intent_hash` | 意图哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `deactivation_reason` | 停用原因 | （据字段名） | 长文本 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `original_creator_unknown` | 原始创建人未知 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_tombstones` 不可变墓碑 —— 对象被清理后保留的永久审计痕迹。

模型：`evidence_governance_models.EvidenceTombstone`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `original_object_type` | 原始对象类型 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `original_object_id` | 原始对象编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `purge_reason` | 清除原因 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `purged_by_user_id` | 清除人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `purged_at` | 清除时间 | （据字段名） | 时间 |  | 否 |  |
| `metadata_redacted` | 元数据脱敏 | （据字段名） | JSON |  | 是 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `retention_policy_version` | 保留策略版本 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `legal_hold_release_id` | 法律保全解除编号 | （据字段名） | 编号 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `evidence_upload_attempts` UploadAttempt —— 内容验证前的最小上传审计（design §4.0 / R1.1 / R12）。

模型：`evidence_governance_models.UploadAttempt`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `sanitized_file_name` | 脱敏文件名称 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `declared_media_type` | 声明媒体类型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `detected_media_type` | 检测到媒体类型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `received_byte_size` | 收到字节大小 | （据字段名） | 整数 |  | 是 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `validation_outcome` | 校验结果 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `failure_category` | 失败类别 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `command_root_id` | 命令根编号 | （据字段名） | 编号 |  | 是 |  |
| `attempted_at` | 尝试时间 | （据字段名） | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `legacy_attachment_alias` 旧附件 ID → (新聚合根, 确定版本) 解析别名（design §4.1）。

模型：`evidence_governance_models.LegacyAttachmentAlias`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `old_attachment_id` | 旧附件编号 | （据字段名） | 编号 | 是 |  |  |
| `attachment_id` | 附件编号 | （据字段名） | 编号 |  | 否 |  |
| `attachment_version_id` | 附件版本编号 | （据字段名） | 编号 |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 否 |  |
| `resolution_kind` | 处理结果类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `legal_hold_scopes` LegalHoldScope（design §4.6；R13/P26）—— 固化 direct/transitive 范围；范围历史不删除。

模型：`evidence_governance_models.LegalHoldScope`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `legal_hold_id` | 法律保全编号 | 指向 `legal_holds` | 编号 |  | 否 | legal_holds.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `node_type` | 节点类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `node_id` | 节点编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `scope_kind` | 范围类别 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `is_active` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `legal_holds` LegalHold（design §4.6/§5.5；R13/P26/P27）—— released_by_user_id 人工专属（released 时 CHECK 非空）。

模型：`evidence_governance_models.LegalHold`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `reason` | 原因 | （据字段名） | 长文本 |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `graph_watermark` | 图水印 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `release_reason` | 解除原因 | （据字段名） | 长文本 |  | 是 |  |
| `released_by_user_id` | 解除人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `released_at` | 解除时间 | （据字段名） | 时间 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ocr_confirmations` OCRConfirmation（design §4.5；R6.2/P12）—— append-only 人工确认修订。

模型：`evidence_governance_models.OcrConfirmation`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ocr_job_id` | 识别任务编号 | 指向 `ocr_jobs` | 编号 |  | 否 | ocr_jobs.id |
| `ocr_result_id` | 识别结果编号 | 指向 `ocr_results` | 编号 |  | 否 | ocr_results.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `field_key` | 字段键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `is_required` | 是否必填 | （据字段名） | 是 / 否 |  | 否 |  |
| `original_value` | 原始值 | （据字段名） | 长文本 |  | 是 |  |
| `confirmed_value` | 确认值 | （据字段名） | 长文本 |  | 是 |  |
| `decision` | 决定 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `is_current` | 是否当前 | （据字段名） | 是 / 否 |  | 否 |  |
| `revision_no` | 修订号编号 | （据字段名） | 整数 |  | 否 |  |
| `confirmed_by_user_id` | 确认人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 否 |  |

### `ocr_job_transitions` OCRJobTransition（design §4.5）—— 每次状态迁移一条，关联 command-root；append-only。

模型：`evidence_governance_models.OcrJobTransition`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ocr_job_id` | 识别任务编号 | 指向 `ocr_jobs` | 编号 |  | 否 | ocr_jobs.id |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 是 | evidence_audit_command_roots.id |
| `from_state` | 从状态 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `to_state` | 到状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `progress` | 进度 | （据字段名） | 整数 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `at` | 时间 | （据字段名） | 时间 |  | 否 |  |

### `ocr_jobs` OCRJob（design §4.5；R5/P9）—— 绑定确定版本/hash/config/幂等键/lease/actor。

模型：`evidence_governance_models.OcrJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `attachment_id` | 附件编号 | （据字段名） | 编号 |  | 否 |  |
| `attachment_version_id` | 附件版本编号 | 指向 `attachment_versions` | 编号 |  | 否 | attachment_versions.id |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `parse_config` | 解析配置 | （据字段名） | JSON |  | 是 |  |
| `parse_config_version` | 解析配置版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `progress` | 进度 | （据字段名） | 整数 |  | 否 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `max_attempts` | 最大尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `lease_owner` | 租约负责人 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |
| `next_retry_at` | 下一重试时间 | （据字段名） | 时间 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 是 | evidence_audit_command_roots.id |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ocr_results` OCRResult（design §4.5；R6.1/P11）—— 不可变原始识别结果（immutable 触发器）。

模型：`evidence_governance_models.OcrResult`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ocr_job_id` | 识别任务编号 | 指向 `ocr_jobs` | 编号 |  | 否 | ocr_jobs.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `attachment_version_id` | 附件版本编号 | 指向 `attachment_versions` | 编号 |  | 否 | attachment_versions.id |
| `source_content_hash` | 来源内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `raw_text` | 原始文本 | （据字段名） | 长文本 |  | 是 |  |
| `pages` | 页数 | （据字段名） | JSON |  | 是 |  |
| `fields` | 字段 | （据字段名） | JSON |  | 是 |  |
| `confidence` | 置信度 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `page` | 页 | （据字段名） | 整数 |  | 是 |  |
| `region` | 地区 | （据字段名） | JSON |  | 是 |  |
| `engine` | 引擎 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `model_version` | 模型版本 | （据字段名） | 文本（≤120 字） |  | 是 |  |
| `config_version` | 配置版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `result_hash` | 结果哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ocr_writeback_staging` staged-external 写回暂存（design §4.5；R6.4/P13）—— 目标模块以幂等键消费后回执推进。

模型：`evidence_governance_models.OcrWritebackStaging`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ocr_writeback_id` | 识别回写编号 | 指向 `ocr_writebacks` | 编号 |  | 否 | ocr_writebacks.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `target_type` | 目标类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 否 |  |
| `payload_hash` | 数据哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `consume_state` | 消费状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `consumed_at` | 已消费时间 | （据字段名） | 时间 |  | 是 |  |
| `receipt` | 回执 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ocr_writebacks` OCRWriteback（design §4.5；R6.4/P13/P14）—— 目标版本/mapping/confirmation IDs/幂等/payload hash。

模型：`evidence_governance_models.OcrWriteback`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ocr_job_id` | 识别任务编号 | 指向 `ocr_jobs` | 编号 |  | 否 | ocr_jobs.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `target_type` | 目标类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `target_version` | 目标版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `write_mode` | 写入模式 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `field_mapping` | 字段映射 | （据字段名） | JSON |  | 否 |  |
| `confirmation_ids` | 函证列表 | （据字段名） | JSON |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `payload_hash` | 数据哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `result` | 结果 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 是 | evidence_audit_command_roots.id |
| `written_by_user_id` | 写入人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `review_closes` ReviewClose（design §4.6；R10.2/P21）—— closed_by_user_id NOT NULL（人工专属）。

模型：`evidence_governance_models.ReviewClose`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `review_id` | 复核编号 | （据字段名） | 编号 |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `close_note` | 关闭附注 | （据字段名） | 长文本 |  | 否 |  |
| `closed_by_user_id` | 关闭人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `command_root_id` | 命令根编号 | 指向 `evidence_audit_command_roots` | 编号 |  | 是 | evidence_audit_command_roots.id |
| `reopened` | 重开 | （据字段名） | 是 / 否 |  | 否 |  |
| `reopened_at` | 重开时间 | （据字段名） | 时间 |  | 是 |  |
| `closed_at` | 关闭时间 | （据字段名） | 时间 |  | 否 |  |

### `review_evidence_snapshots` ReviewEvidenceSnapshot（design §4.6；R10/P22）—— 冻结提出/关闭时 ref/version/hash/locator。

模型：`evidence_governance_models.ReviewEvidenceSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `review_id` | 复核编号 | （据字段名） | 编号 |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `evidence_ref_id` | 证据引用编号 | 指向 `evidence_refs` | 编号 |  | 否 | evidence_refs.id |
| `target_version` | 目标版本 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `target_hash` | 目标哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `locator` | 定位 | （据字段名） | JSON |  | 是 |  |
| `snapshot_phase` | 快照阶段 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="a-group"></a>
## A. 交付件、导出与归档

### `archive_checklists` 

模型：`collaboration_models.ArchiveChecklist`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `item_code` | 项编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `item_name` | 项名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `category` | 类别 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `check_status` | 检查状态 | 取值：`pending` 待处理 / `pass_` / `fail` 不通过 / `na` | 枚举 |  | 否 |  |
| `checked_by` | 检查人 | 指向 `users` | 编号 |  | 是 | users.id |
| `checked_at` | 检查时间 | （据字段名） | 时间 |  | 是 |  |
| `notes` | 备注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `archive_jobs` 归档编排作业

模型：`archive_models.ArchiveJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `scope` | 范围 | '`final` 定稿' \| '`interim` 预审' | 文本（≤20 字） |  | 否 |  |
| `status` | 状态 | '`queued` 排队中' \| '`running` 运行中' \| '`succeeded` 成功' \| '`failed` 失败' \| '`partial` 部分成功' | 文本（≤20 字） |  | 否 |  |
| `push_to_cloud` | 推送到云端 | （据字段名） | 是 / 否 |  | 否 |  |
| `purge_local` | 清除本地 | （据字段名） | 是 / 否 |  | 否 |  |
| `gate_eval_id` | 门禁评估编号 | （据字段名） | 编号 |  | 是 |  |
| `last_succeeded_section` | 最近成功章节 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `failed_section` | 失败章节 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `failed_reason` | 失败原因 | （据字段名） | 长文本 |  | 是 |  |
| `section_progress` | 章节进度 | （据字段名） | JSON |  | 是 |  |
| `output_url` | 输出地址 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `manifest_hash` | 清单哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `initiated_by` | 发起人 | 指向 `users` | 编号 |  | 是 | users.id |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `archive_modifications` 

模型：`collaboration_models.ArchiveModification`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `modification_type` | 修改类型 | 取值：`addition` / `deletion` / `replacement` | 枚举 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 否 |  |
| `request_reason` | 请求原因 | （据字段名） | 长文本 |  | 是 |  |
| `approval_status` | 审批状态 | 取值：`pending` 待处理 / `approved` 已通过 / `rejected` 已驳回 | 枚举 |  | 否 |  |
| `approved_by` | 批准人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |

### `deliverable_section_state` 出品物章节级状态承载表（V067）。

模型：`audit_platform_models.DeliverableSectionState`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `word_export_task_id` | Word导出任务编号 | （据字段名） | 编号 |  | 否 |  |
| `version_no` | 版本编号 | 记录列，不入主键/唯一约束 | 整数 |  | 是 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `section_code` | 章节编码 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `source_snapshot_hash` | 来源快照哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `last_writeback_baseline_hash` | 最近回写基线哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `anchor_name` | 锚点名称 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `rendered_block_hash` | 渲染块哈希 | 历史缺陷正是拿 source_snapshot_hash 去比块内文字致刷新恒要求确认覆盖。；计算入口单一真源 = section_anchor_utils.block_text_hash；NULL=存量交付件。 | 文本（≤64 字） |  | 是 |  |
| `text_baseline` | 文本基线 | 正文回填基线与正文区外结构指纹。source_snapshot_hash 含 TB 金额，不能再拿它判文字冲突。 | 长文本 |  | 是 |  |
| `text_source_hash` | 文本来源哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `outside_hash` | 范围外哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `text_render_context` | 文本渲染上下文 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `deliverable_snapshots` 不可变交付快照。

模型：`phase13_models.DeliverableSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `digest` | 摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |

### `export_job_attempts` 后台导出任务 attempt 历史。

模型：`phase13_models.ExportJobAttempt`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `job_id` | 任务编号 | 指向 `export_jobs_v2` | 编号 |  | 否 | export_jobs_v2.id |
| `item_id` | 填写项编号 | 指向 `export_job_items_v2` | 编号 |  | 否 | export_job_items_v2.id |
| `attempt_no` | 尝试编号 | （据字段名） | 整数 |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `snapshot_id` | 快照编号 | （据字段名） | 编号 |  | 是 |  |
| `error_type` | 错误类型 | （据字段名） | 长文本 |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `diagnostic_detail` | 诊断明细 | （据字段名） | 长文本 |  | 是 |  |
| `file_path` | 文件路径 | （据字段名） | 长文本 |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `version_id` | 版本编号 | （据字段名） | 编号 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `trigger_source` | 触发来源 | （据字段名） | 文本（≤30 字） |  | 是 |  |

### `export_job_items_v2` 后台导出任务明细

模型：`phase13_models.ExportJobItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `job_id` | 任务编号 | 指向 `export_jobs_v2` | 编号 |  | 否 | export_jobs_v2.id |
| `word_export_task_id` | Word导出任务编号 | 指向 `word_export_task` | 编号 |  | 是 | word_export_task.id |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `step_key` | 步骤键 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `sequence` | 序号 | （据字段名） | 整数 |  | 是 |  |
| `snapshot_id` | 快照编号 | （据字段名） | 编号 |  | 是 |  |
| `version_id` | 版本编号 | （据字段名） | 编号 |  | 是 |  |
| `file_path` | 文件路径 | （据字段名） | 长文本 |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `last_attempt_id` | 最近尝试编号 | （据字段名） | 编号 |  | 是 |  |

### `export_jobs_v2` 后台导出任务（全套导出/批量渲染/重试/三件套）

模型：`phase13_models.ExportJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `job_type` | 任务类型 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `progress_total` | 进度合计 | （据字段名） | 整数 |  | 否 |  |
| `progress_done` | 进度完成 | （据字段名） | 整数 |  | 否 |  |
| `failed_count` | 失败数量 | （据字段名） | 整数 |  | 否 |  |
| `initiated_by` | 发起人 | 指向 `users` | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `snapshot_id` | 快照编号 | （据字段名） | 编号 |  | 是 |  |
| `readiness` | 就绪情况 | （据字段名） | JSON |  | 是 |  |
| `kind` | 类别 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `trio_total` | 三件套合计 | （据字段名） | 整数 |  | 否 |  |
| `trio_succeeded` | 三件套成功 | （据字段名） | 整数 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `export_tasks` PDF导出任务

模型：`report_models.ExportTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `task_type` | 任务类型 | 取值：`single_document` 单个文档 / `full_archive` 完整归档包 | 枚举 |  | 否 |  |
| `document_type` | 文档类型 | （据字段名） | 文本 |  | 是 |  |
| `export_year` | 导出年度 | 正式导出单位策略证据。 | 整数 |  | 是 |  |
| `document_types` | 文档类型 | （据字段名） | JSON |  | 否 |  |
| `unit_policy_snapshot` | 单位策略快照 | （据字段名） | JSON |  | 是 |  |
| `status` | 状态 | 取值：`queued` 排队中 / `processing` 处理中 / `completed` 已完成 / `failed` 失败 | 枚举 |  | 否 |  |
| `progress_percentage` | 进度百分比 | （据字段名） | 整数 |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 文本 |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `password_protected` | 密码受保护 | （据字段名） | 是 / 否 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `regulatory_filing` 监管备案

模型：`extension_models.RegulatoryFiling`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `filing_type` | 报送类型 | `cicpa_report` 中注协报备/`archival_standard` 归档标准 | 文本（≤50 字） |  | 否 |  |
| `filing_status` | 报送状态 | `submitted` 已提交/`pending` 待处理/`approved` 已通过/`rejected` 已驳回 | 文本（≤50 字） |  | 否 |  |
| `submission_data` | 提交数据 | （据字段名） | JSON |  | 是 |  |
| `response_data` | 回复数据 | （据字段名） | JSON |  | 是 |  |
| `submitted_at` | 提交时间 | （据字段名） | 时间 |  | 是 |  |
| `responded_at` | 回复时间 | （据字段名） | 时间 |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `word_export_task` Word导出主任务

模型：`phase13_models.WordExportTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `doc_type` | 文档类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 长文本 |  | 是 |  |
| `template_type` | 模板类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `snapshot_id` | 快照编号 | （据字段名） | 编号 |  | 是 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `cache_key` | 缓存键 | 批量简报缓存键 MD5 | 文本（≤64 字） |  | 是 |  |
| `file_size` | 文件大小 | deliverable-center | 整数 |  | 是 |  |
| `html_path` | 网页内容路径 | （据字段名） | 长文本 |  | 是 |  |
| `report_body_json` | 报表正文JSON | （据字段名） | JSON |  | 是 |  |
| `opinion_type` | 意见类型 | （据字段名） | 文本（≤30 字） |  | 是 |  |
| `company_type` | 公司类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `doc_subtype` | 文档子类型 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `is_pie` | 是否饼图 | （据字段名） | 是 / 否 |  | 是 |  |
| `source_snapshot_refs` | 来源快照引用 | （据字段名） | JSON |  | 是 |  |
| `selected_sections` | 选中章节 | （据字段名） | JSON |  | 是 |  |
| `report_date` | 报表日期 | （据字段名） | 日期 |  | 是 |  |
| `prior_period_info` | 上期期间信息 | （据字段名） | 文本（≤40 字） |  | 是 |  |
| `approval_by` | 审批人 | 指向 `users` | 编号 |  | 是 | users.id |
| `approval_at` | 审批时间 | （据字段名） | 时间 |  | 是 |  |
| `reject_reason` | 驳回原因 | （据字段名） | 长文本 |  | 是 |  |
| `signed_by` | 签字人 | 指向 `users` | 编号 |  | 是 | users.id |
| `signed_at` | 签字时间 | （据字段名） | 时间 |  | 是 |  |
| `sign_type` | 符号类型 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `archived_at` | 归档时间 | （据字段名） | 时间 |  | 是 |  |

### `word_export_task_versions` Word导出版本快照

模型：`phase13_models.WordExportTaskVersion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `word_export_task_id` | Word导出任务编号 | 指向 `word_export_task` | 编号 |  | 否 | word_export_task.id |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `file_path` | 文件路径 | （据字段名） | 长文本 |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `html_path` | 网页内容路径 | deliverable-center | 长文本 |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 是 |  |
| `file_hash` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `hash_chain_entry_id` | 哈希链条目编号 | （据字段名） | 编号 |  | 是 |  |
| `source_snapshot_refs` | 来源快照引用 | （据字段名） | JSON |  | 是 |  |
| `selected_sections` | 选中章节 | （据字段名） | JSON |  | 是 |  |
| `created_via` |  | 未查明 | 文本（≤20 字） |  | 是 |  |
| `edited_by` | 编辑人 | 实际编辑人与编辑时间。NULL = 未知 —— **禁止回退 created_by 展示**；created_by 在 OO 回调场景只是「回调处理占位」，把它当编辑人会让版本链上；所有在线编辑版本作者都变成交付物创建人（历史缺陷）。；指向 `users` | 编号 |  | 是 | users.id |
| `edited_at` | 编辑时间 | （据字段名） | 时间 |  | 是 |  |
| `base_version_no` | 基准版本编号 | OO 会话底版 / key 与渲染上下文。；base_version_no + oo_doc_key 让回调能识别「编辑期间已有刷新/再生成」；仍保存用户编辑但显式标陈旧底版。 | 整数 |  | 是 |  |
| `oo_doc_key` | 在线编辑文档键 | （据字段名） | 文本（≤160 字） |  | 是 |  |
| `snapshot_id` | 快照编号 | trio snapshot 关联与文件完整性校验（ALTER varchar→uuid） | 编号 |  | 是 |  |
| `file_sha256` | 文件SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `render_context` | 渲染上下文 | 附注交叉引用显示编号等文档级上下文；OO 保存版本继承底版，供文字回填重放。 | JSON |  | 是 |  |
| `drift_report` |  | {"diffs": [...]} = 已比对；非空即有手工改动 → 拒绝；空数组 → 放行 | JSON |  | 是 |  |
| `unit_policy_snapshot` | 单位策略快照 | 正式附注版本的单位策略快照与摘要；两列由数据库约束成对存在。 | JSON |  | 是 |  |
| `unit_policy_digest` | 单位策略摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |

### `wp_export_snapshot` 底稿导出快照 — 记录每次导出时的内容哈希，用于导入冲突检测

模型：`wp_export_models.WpExportSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `file_version` | 文件版本 | （据字段名） | 整数 |  | 否 |  |
| `snapshot_hash` | 快照哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `exported_by` | 导出人 | 指向 `users` | 编号 |  | 是 | users.id |
| `exported_at` | 导出时间 | （据字段名） | 时间 |  | 否 |  |
| `file_format` | 文件格式 | （据字段名） | 文本（≤10 字） |  | 否 |  |
| `file_size_bytes` | 文件大小字节数 | （据字段名） | 整数 |  | 是 |  |
| `metadata_bundle` | 元数据包 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_version_archive` 底稿版本归档 — 记录版本元数据（文件可能已清理但元数据保留）

模型：`wp_export_models.WpVersionArchive`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `working_paper_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 否 |  |
| `source` | 来源 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `file_size_bytes` | 文件大小字节数 | （据字段名） | 整数 |  | 是 |  |
| `archive_path` | 归档路径 | （据字段名） | 长文本 |  | 是 |  |
| `file_retained` | 文件留存 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="k-group"></a>
## K. 知识库与编制指引

### `guidance_consumer_ack` durable、幂等的 ConsumerAck ledger 行。

模型：`guidance_handoff_ack_models.GuidanceConsumerAck`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ack_id` | 确认编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `handoff_id` | 交接编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `handoff_digest` | 交接摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `consumer` | 消费方 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `consumer_version` | 消费方版本 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `verdict` | 结论 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `validated_digests_json` | 已校验摘要哈希JSON | sha256 of the digests actually validated during verification（authority；artifact / mapping / formulaBoundary / guidance），供跨消费方复核。 | JSON |  | 否 |  |
| `reason_codes_json` | 原因编码JSON | 结构化 reason 码（REJECTED 时非空；ACCEPTED 时为空列表）。 | JSON |  | 否 |  |
| `recorded_at` | 记录时间 | （据字段名） | 时间 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `guidance_exemption_record` guidance 有效豁免记录。

模型：`guidance_publication_models.GuidanceExemptionRecord`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `scope_type` | 范围类型 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤512 字） |  | 是 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `entry_ids_json` | 条目列表JSON | （据字段名） | JSON |  | 否 |  |
| `reason` | 原因 | （据字段名） | 文本（≤256 字） |  | 否 |  |
| `owner_user_id` | 负责人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `approver_user_id` | 审批人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `approved_at` | 批准时间 | （据字段名） | 时间 |  | 否 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 否 |  |
| `source_digest` | 来源摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `revoked_at` | 吊销时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `guidance_handoff_visibility` finalize visibility saga 的 guidance 侧视图。

模型：`guidance_handoff_ack_models.GuidanceHandoffVisibility`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `handoff_id` | 交接编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `handoff_digest` | 交接摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `organization_id` | 组织编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 文本（≤128 字） |  | 是 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤512 字） |  | 否 |  |
| `sheet_uid` | 表页编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `state` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `decisive_ack_id` | 决定性确认编号 | 反映本次判定所依据的 ACK ledger 行 ack_id（REJECTED/PENDING 时可能为空）。 | 文本（≤128 字） |  | 是 |  |
| `reason_codes_json` | 原因编码JSON | （据字段名） | JSON |  | 否 |  |
| `superseded_by` | 被替代人 | supersede 链：新 handoff_digest ACTIVE 后旧行标 stale（写入被取代者 id）。 | 编号 |  | 是 |  |
| `stale` | 过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `guidance_publication` guidance 发布主体。

模型：`guidance_publication_models.GuidancePublication`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `lineage_id` | 血缘编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `version` | 版本号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `content_json` | 内容JSON | （据字段名） | JSON |  | 否 |  |
| `source_refs_json` | 来源引用JSON | （据字段名） | JSON |  | 否 |  |
| `content_digest` | 内容摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `source_digest` | 来源摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `schema_ref` | 结构引用 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `review_status` | 复核状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `author_user_id` | 作者用户编号 | （据字段名） | 编号 |  | 否 |  |
| `reviewer_user_id` | 复核人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 是 |  |
| `withdrawn_at` | 撤回时间 | （据字段名） | 时间 |  | 是 |  |
| `withdrawn_reason` | 撤回原因 | （据字段名） | 文本（≤256 字） |  | 是 |  |
| `superseded_by` | 被替代（关联记录） | 指向 `guidance_publication` | 编号 |  | 是 | guidance_publication.id |
| `reason` | 原因 | （据字段名） | 文本（≤256 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `guidance_publication_event` 发布生命周期事件。

模型：`guidance_publication_models.GuidancePublicationEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `publication_id` | 发布编号 | 指向 `guidance_publication` | 编号 |  | 否 | guidance_publication.id |
| `event_type` | 事件类型 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `from_status` | 从状态 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `to_status` | 到状态 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `reviewer_user_id` | 复核人用户编号 | （据字段名） | 编号 |  | 是 |  |
| `reason` | 原因 | （据字段名） | 文本（≤256 字） |  | 是 |  |
| `diff_json` | 差异JSON | （据字段名） | JSON |  | 否 |  |
| `before_digest` | 之前摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `after_digest` | 之后摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `audit_ref` | 审计引用 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `outbox_ref` | 待发事件引用 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `knowledge_documents` 知识库文档

模型：`knowledge_models.KnowledgeDocument`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `folder_id` | 文件夹编号 | 指向 `knowledge_folders` | 编号 |  | 否 | knowledge_folders.id |
| `name` | 名称 | （据字段名） | 文本（≤500 字） |  | 否 |  |
| `file_type` | 文件类型 | pdf/docx/md/xlsx | 文本（≤20 字） |  | 是 |  |
| `file_size` | 文件大小 | （据字段名） | 整数 |  | 否 |  |
| `storage_path` | 存储路径 | 文件存储路径 | 长文本 |  | 是 |  |
| `blob_id` | 文件内容编号 | 指向 `asset_blobs` | 编号 |  | 是 | asset_blobs.id |
| `content_text` | 内容文本 | 内容（小文件直接存文本，大文件存路径）；文本内容（供 RAG 检索） | 长文本 |  | 是 |  |
| `content_summary` | 内容摘要 | 摘要 | 长文本 |  | 是 |  |
| `access_level` | 访问级别 | 权限（继承文件夹权限，或单独设置）；None = 继承文件夹权限；取值：`public` 公开 / `project_group` 项目组 / `private` 民营 | 枚举 |  | 是 |  |
| `project_ids` | 项目列表 | （据字段名） | JSON |  | 是 |  |
| `tags` | 标签 | 元数据；标签 | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `version` | 版本号 | AT-3 KB 接入：版本管理 | 整数 |  | 否 |  |
| `previous_version_id` | 上一版本编号 | （据字段名） | 编号 |  | 是 |  |
| `index_status` | 序号状态 | 索引状态追踪 | 文本（≤30 字） |  | 是 |  |
| `index_error` | 序号错误 | （据字段名） | 长文本 |  | 是 |  |
| `ocr_status` | 识别状态 | ocr_status：None = 不需要 / 不适用；pending / running / done / empty / failed（取值见 KNOWLEDGE_OCR_STATUSES）。；ocr_due_at：pending 时 = 下次可尝试时间（退避）；running 时 = 租约到期（过期可被重新认领… | 文本（≤16 字） |  | 是 |  |
| `ocr_attempts` | 识别尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `ocr_error` | 识别错误 | （据字段名） | 长文本 |  | 是 |  |
| `ocr_due_at` | 识别到期时间 | （据字段名） | 时间 |  | 是 |  |

### `knowledge_evidence_promotions` 

模型：`asset_blob_models.KnowledgeEvidencePromotion`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `source_document_id` | 来源文档编号 | 指向 `knowledge_documents` | 编号 |  | 否 | knowledge_documents.id |
| `source_document_version` | 来源文档版本 | （据字段名） | 整数 |  | 否 |  |
| `source_blob_id` | 来源文件内容编号 | 指向 `asset_blobs` | 编号 |  | 否 | asset_blobs.id |
| `source_hash` | 来源哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `target_attachment_id` | 目标附件编号 | 指向 `attachments` | 编号 |  | 否 | attachments.id |
| `target_attachment_version_id` | 目标附件版本编号 | 指向 `attachment_versions` | 编号 |  | 否 | attachment_versions.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `knowledge_folders` 知识库文件夹（树形目录）

模型：`knowledge_models.KnowledgeFolder`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `parent_id` | 上级编号 | None = 顶级文件夹；指向 `knowledge_folders` | 编号 |  | 是 | knowledge_folders.id |
| `category` | 类别 | 预制分类（如 accounting_standards），自定义文件夹为 None | 文本（≤50 字） |  | 是 |  |
| `system_key` | 系统键 | 系统文件夹定位键（project:{pid} / project:{pid}:{slot}），用户文件夹为 None。；部分唯一索引 uq_knowledge_folders_system_key 只约束未删除行。 | 文本（≤120 字） |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `access_level` | 访问级别 | 权限；取值：`public` 公开 / `project_group` 项目组 / `private` 民营 | 枚举 |  | 否 |  |
| `project_ids` | 项目列表 | access_level=project_group 时，允许访问的项目 ID 列表 | JSON |  | 是 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |

### `knowledge_index` 知识库索引

模型：`ai_models.KnowledgeIndex`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `source_type` | 来源类型 | 取值：`trial_balance` / `journal` / `auxiliary` / `contract` / `document_scan` / `workpaper` 底稿 / `adjustment` 调整分录 / `elimination` / `confirmation` 函证 / `review_comment` 复核意见 / `prior_year_summary` / `knowledge_doc` / `address_coordinate` | 枚举 |  | 否 |  |
| `source_id` | 来源编号 | （据字段名） | 编号 |  | 否 |  |
| `content_text` | 内容文本 | （据字段名） | 长文本 |  | 否 |  |
| `embedding_vector` | 向量向量 | 逗号串向量（pgvector 不可用时的检索来源；起 TEXT，原 VARCHAR(5000) 写不下真实维度） | 长文本 |  | 是 |  |
| `embedding_vec` | 向量向量 | pgvector 列（/ ，扩展不可用时不存在；读取一律 defer） | VECTOR(1024) |  | 是 |  |
| `embedding_model` | 向量模型 | 生成该向量的模型签名「模型名@维度」：检索只与同签名分块比较 | 文本（≤200 字） |  | 是 |  |
| `chunk_index` | 分块序号 | （据字段名） | 整数 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `doc_version` | 文档版本 | （据字段名） | 整数 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `project_guidance_supplement` 项目级 guidance 补充。

模型：`guidance_publication_models.ProjectGuidanceSupplement`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `entry_id` | 条目编号 | （据字段名） | 文本（≤512 字） |  | 否 |  |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `sheet_key` | 表页键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `supplement_version` | 补充版本 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `content_json` | 内容JSON | （据字段名） | JSON |  | 否 |  |
| `content_digest` | 内容摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `base_publication_id` | 基准发布编号 | 指向 `guidance_publication` | 编号 |  | 是 | guidance_publication.id |
| `base_content_digest` | 基准内容摘要哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `project_evidence_json` | 项目证据JSON | （据字段名） | JSON |  | 否 |  |
| `evidence_digest` | 证据摘要哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `author_user_id` | 作者用户编号 | （据字段名） | 编号 |  | 否 |  |
| `reviewer_user_id` | 复核人用户编号 | （据字段名） | 编号 |  | 否 |  |
| `reviewed_at` | 复核时间 | （据字段名） | 时间 |  | 是 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 是 |  |
| `reason` | 原因 | （据字段名） | 文本（≤256 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `qc_case_library` QC 案例库条目

模型：`qc_case_library_models.QcCaseLibrary`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `category` | 类别 | 案例分类，如 '底稿完整性' / '数据准确性' | 文本（≤50 字） |  | 否 |  |
| `severity` | 严重程度 | '`blocking` 阻断' \| '`warning` 警告' \| '`info` 提示' | 文本（≤20 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 否 |  |
| `lessons_learned` | 经验 | 经验教训 | 长文本 |  | 是 |  |
| `related_wp_refs` | 相关底稿引用 | 脱敏后的底稿引用 [{wp_code, cycle, snippet}] | JSON |  | 是 |  |
| `related_standards` | 相关准则 | 关联准则 [{code: '1301', section: '6.2', name: '审计工作底稿'}] | JSON |  | 是 |  |
| `published_by` | 发布人 | （据字段名） | 编号 |  | 否 |  |
| `published_at` | 发布时间 | （据字段名） | 时间 |  | 否 |  |
| `review_count` | 复核数量 | 阅读计数 | 整数 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

<a id="i-group"></a>
## I. AI

### `ai_analysis_item` AI分析报告条目

模型：`ai_models.AIAnalysisItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `report_id` | 报表编号 | 指向 `ai_analysis_report` | 编号 |  | 否 | ai_analysis_report.id |
| `clause_type` | 条款类型 | 取值：`amount` / `payment_terms` / `delivery_terms` / `penalty` / `guarantee` / `pledge` / `related_party` / `special_terms` / `pricing` / `duration` | 枚举 |  | 是 |  |
| `clause_text` | 条款文本 | （据字段名） | 长文本 |  | 否 |  |
| `extraction_result` | 提取结果 | （据字段名） | JSON |  | 是 |  |
| `risk_flag` | 风险标记 | （据字段名） | 是 / 否 |  | 否 |  |
| `risk_reason` | 风险原因 | （据字段名） | 长文本 |  | 是 |  |
| `confidence_score` | 置信度评分 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `human_confirmed` | 人工确认 | （据字段名） | 是 / 否 |  | 否 |  |
| `human_note` | 人工附注 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_analysis_report` AI分析报告

模型：`ai_models.AIAnalysisReport`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `document_type` | 文档类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `document_name` | 文档名称 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `summary` | 摘要 | （据字段名） | 长文本 |  | 是 |  |
| `key_findings` | 键发现 | （据字段名） | JSON |  | 是 |  |
| `risk_indicators` | 风险迹象 | （据字段名） | JSON |  | 是 |  |
| `confidence_score` | 置信度评分 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `status` | 状态 | 取值：`pending` 待处理 / `analyzing` / `completed` 已完成 / `failed` 失败 | 枚举 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_action_receipts` note save / adopt 的通用幂等收据（Req 8.2/8.3 · Property 21）。

模型：`ai_models.AIChatActionReceipt`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `action_type` | 动作类型 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `session_id` | 会话编号 | 指向 `ai_chat_session` | 编号 |  | 否 | ai_chat_session.id |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `source_message_hash` | 来源消息哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `result_resource_id` | 结果资源编号 | （据字段名） | 编号 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_attachments` 会话附件 metadata（Req 7.3）。

模型：`ai_models.AIChatAttachment`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `owner_id` | 负责人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `session_id` | 会话编号 | 指向 `ai_chat_session` | 编号 |  | 否 | ai_chat_session.id |
| `run_id` | 运行编号 | 指向 `ai_chat_runs` | 编号 |  | 是 | ai_chat_runs.id |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `original_name` | 原始名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `storage_name` | 存储名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `mime_type` | 文件类型 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `size_bytes` | 大小字节数 | （据字段名） | 整数 |  | 否 |  |
| `ocr_status` | 识别状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `ocr_text_protected` | 识别文本受保护 | （据字段名） | 长文本 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `expires_at` | 过期时间 | （据字段名） | 时间 |  | 是 |  |
| `legal_hold` | 法律保全 | （据字段名） | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `ai_chat_history` AI对话历史

模型：`ai_models.AIChatHistory`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `conversation_id` | 会话编号 | （据字段名） | 编号 |  | 否 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 是 | users.id |
| `role` | 角色 | 取值：`user` 用户 / `assistant` / `system` 系统 | 枚举 |  | 否 |  |
| `message_text` | 消息文本 | （据字段名） | 长文本 |  | 否 |  |
| `referenced_sources` | 被引用来源 | （据字段名） | JSON |  | 是 |  |
| `model_used` | 模型已用 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `token_count` | 令牌数量 | （据字段名） | 整数 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_message` AI问答消息（详细消息记录）

模型：`ai_models.AIChatMessage`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `session_id` | 会话编号 | 指向 `ai_chat_session` | 编号 |  | 否 | ai_chat_session.id |
| `seq` | 序号 | （据字段名） | 整数 |  | 是 |  |
| `role` | 角色 | 取值：`user` 用户 / `assistant` / `system` 系统 | 枚举 |  | 否 |  |
| `message_text` | 消息文本 | （据字段名） | 长文本 |  | 否 |  |
| `referenced_sources` | 被引用来源 | citations 的唯一存放位置（勿新增 citations 列）。 | JSON |  | 是 |  |
| `model_used` | 模型已用 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `tokens_used` | 令牌数已用 | （据字段名） | 整数 |  | 是 |  |
| `latency_ms` | 延迟毫秒 | （据字段名） | 整数 |  | 是 |  |
| `run_id` | 运行编号 | 指向 `ai_chat_runs` | 编号 |  | 是 | ai_chat_runs.id |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `context_manifest` | 上下文清单 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_run_resources` 

模型：`asset_blob_models.AiChatRunResource`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `run_id` | 运行编号 | 指向 `ai_chat_runs` | 编号 |  | 否 | ai_chat_runs.id |
| `session_id` | 会话编号 | 指向 `ai_chat_session` | 编号 |  | 否 | ai_chat_session.id |
| `resource_kind` | 资源类别 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `resource_id` | 资源编号 | （据字段名） | 编号 |  | 否 |  |
| `attachment_version_id` | 附件版本编号 | 指向 `attachment_versions` | 编号 |  | 是 | attachment_versions.id |
| `blob_id` | 文件内容编号 | 指向 `asset_blobs` | 编号 |  | 是 | asset_blobs.id |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_runs` Chat Run —— 一次模型/Agent 执行的持久化摘要。

模型：`ai_models.AIChatRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `session_id` | 会话编号 | 指向 `ai_chat_session` | 编号 |  | 否 | ai_chat_session.id |
| `request_id` | 请求号 | （据字段名） | 编号 |  | 否 |  |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `host_type` | 宿主类型 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `host_id` | 宿主编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `engine` | 引擎 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `capability_snapshot` | 能力快照 | （据字段名） | JSON |  | 是 |  |
| `context_request_snapshot` | 上下文请求快照 | 重启恢复所需的最小请求快照，只含 mention/附件 ID、复核开关和 sheet。 | JSON |  | 是 |  |
| `queued_at` | 排队时间 | （据字段名） | 时间 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `cancel_requested_at` | 取消请求时间 | （据字段名） | 时间 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `usage` | 用量 | （据字段名） | JSON |  | 是 |  |
| `latency_ms` | 延迟毫秒 | （据字段名） | 整数 |  | 是 |  |
| `retry_count` | 重试次数 | （据字段名） | 整数 |  | 否 |  |
| `lease_owner` | 租约负责人 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |

### `ai_chat_session` AI问答会话（会话维度聚合）

模型：`ai_models.AIChatSession`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `session_type` | 会话类型 | 取值：`general` / `contract` / `workpaper` 底稿 / `confirmation` 函证 | 枚举 |  | 否 |  |
| `title` | 标题 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 是 | users.id |
| `session_key` | 会话键 | 服务端规范化定位 hash；唯一真源 = ai_chat.persistence.build_session_key。 | 文本（≤64 字） |  | 是 |  |
| `host_type` | 宿主类型 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `host_id` | 宿主编号 | 全局知识模式使用 GLOBAL_KNOWLEDGE_HOST_ID sentinel，不用空字符串。 | 文本（≤128 字） |  | 是 |  |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `engine_preference` | 引擎偏好 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `review_mode` | 复核模式 | （据字段名） | 是 / 否 |  | 否 |  |
| `last_message_at` | 最近消息时间 | （据字段名） | 时间 |  | 是 |  |
| `total_messages` | 合计消息 | （据字段名） | 整数 |  | 否 |  |
| `total_tokens` | 合计令牌数 | （据字段名） | 整数 |  | 否 |  |
| `context_summary` | 上下文摘要 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_chat_tool_calls` 工具调用摘要（Req 11.10：每次调用产生 started + finished/failed 记录）。

模型：`ai_models.AIChatToolCall`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `run_id` | 运行编号 | 指向 `ai_chat_runs` | 编号 |  | 否 | ai_chat_runs.id |
| `parent_call_id` | 上级调用编号 | 指向 `ai_chat_tool_calls` | 编号 |  | 是 | ai_chat_tool_calls.id |
| `tool_call_id` | 工具调用编号 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `tool_name` | 工具名称 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `arg_hash` | 参数哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `result_bytes` | 结果字节数 | （据字段名） | 整数 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `ai_confirmation_audit` AI函证审核记录

模型：`ai_models.AIConfirmationAudit`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `confirmation_type` | 函证类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `original_content` | 原始内容 | （据字段名） | 长文本 |  | 否 |  |
| `response_content` | 回复内容 | （据字段名） | 长文本 |  | 是 |  |
| `audit_period` | 审计期间 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `audit_result` | 审计结果 | （据字段名） | JSON |  | 是 |  |
| `status` | 状态 | 取值：`pending` 待处理 / `accepted` 已接受 / `modified` / `rejected` 已驳回 / `regenerated` | 枚举 |  | 否 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_content` AI生成内容

模型：`ai_models.AIContent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `workpaper_id` | 底稿编号 | （据字段名） | 编号 |  | 是 |  |
| `content_type` | 内容类型 | 取值：`data_fill` / `analytical_review` / `risk_alert` / `test_summary` / `note_draft` / `review_finding` | 枚举 |  | 否 |  |
| `content_text` | 内容文本 | （据字段名） | 长文本 |  | 否 |  |
| `data_sources` | 数据来源 | （据字段名） | JSON |  | 是 |  |
| `generation_model` | 生成代次模型 | （据字段名） | 文本（≤100 字） |  | 是 |  |
| `generation_time` | 生成代次时间 | （据字段名） | 时间 |  | 是 |  |
| `confidence_level` | 置信度级别 | 取值：`high` 高 / `medium` 中 / `low` 低 | 枚举 |  | 是 |  |
| `confirmation_status` | 函证状态 | 取值：`pending` 待处理 / `accepted` 已接受 / `modified` / `rejected` 已驳回 / `regenerated` | 枚举 |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `modification_note` | 修改附注 | （据字段名） | 长文本 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_content_governance` AiContentGovernance（design §4.6 / AIEvidenceGate；R8/P17/P18/P19）—— AI 全入口内容治理。

模型：`evidence_governance_models.AiContentGovernance`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `audit_year` | 审计年度 | （据字段名） | 整数 |  | 是 |  |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `entry_point` | 条目点 | （据字段名） | 文本（≤80 字） |  | 否 |  |
| `prompt_hash` | 提示词哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `model_name` | 模型名称 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `service_status` | 服务状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `output_text` | 输出文本 | （据字段名） | 长文本 |  | 是 |  |
| `output_hash` | 输出哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `target_cell` | 目标单元格 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `evidence_refs` | 证据引用 | （据字段名） | JSON |  | 是 |  |
| `citation_snapshots` | 引用快照 | （据字段名） | JSON |  | 是 |  |
| `lifecycle_status` | 生命周期状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `content_version` | 内容版本 | （据字段名） | 整数 |  | 否 |  |
| `previous_version_id` | 上一版本编号 | 指向 `ai_content_governance` | 编号 |  | 是 | ai_content_governance.id |
| `reject_reason` | 驳回原因 | （据字段名） | 长文本 |  | 是 |  |
| `confirmed_by_user_id` | 确认人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_content_log` AI 生成内容溯源日志 — 字段级追踪 AI 输出及人工确认状态

模型：`v3_refinement_models.AiContentLog`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_id` | 底稿 | （据字段名） | 编号 |  | 是 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `target_cell` | 目标单元格 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `prompt_hash` | 提示词哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `model` | 模型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `confidence` | 置信度 | （据字段名） | 数值（4 位小数） |  | 是 |  |
| `generated_content` | 生成内容 | （据字段名） | 长文本 |  | 否 |  |
| `revised_content` | 修订内容 | （据字段名） | 长文本 |  | 是 |  |
| `confirm_action` | 确认动作 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |
| `generated_at` | 生成时间 | （据字段名） | 时间 |  | 否 |  |
| `service_status` | 服务状态 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `output_hash` | 输出哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `evidence_ref_id` | 证据引用编号 | 指向 `evidence_refs` | 编号 |  | 是 | evidence_refs.id |
| `citation_snapshot_id` | 引用快照编号 | metadata.drop_all 无法为环排序（SAWarning + fixture teardown 失败）。给环中这一条边标；指向 `citation_snapshots` | 编号 |  | 是 | citation_snapshots.id |
| `is_stale` | 是否过期 | （据字段名） | 是 / 否 |  | 否 |  |
| `stale_reason` | 过期原因 | （据字段名） | 长文本 |  | 是 |  |
| `generation_id` | 生成代次编号 | DraftArtifact facade：继续复用本表作为唯一待确认状态机。 | 编号 |  | 是 |  |
| `task_code` | 任务编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `source_message_id` | 来源消息编号 | 指向 `ai_chat_message` | 编号 |  | 是 | ai_chat_message.id |
| `prompt_version` | 提示词版本 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `context_manifest` | 上下文清单 | （据字段名） | JSON |  | 是 |  |
| `target_locator` | 目标定位 | （据字段名） | JSON |  | 是 |  |
| `baseline_version` | 基线版本 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `before_hash` | 之前哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `before_content` | 之前内容 | （据字段名） | 长文本 |  | 是 |  |
| `proposed_hash` | 拟议哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `preview_diff` | 预览差异 | （据字段名） | JSON |  | 是 |  |
| `artifact_version` | 产物版本 | （据字段名） | 整数 |  | 否 |  |
| `writeback_status` | 回写状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `applied_version` | 已应用版本 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `applied_hash` | 已应用哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `writeback_receipt` | 回写回执 | （据字段名） | JSON |  | 是 |  |
| `undone_by` | 撤销人 | 指向 `users` | 编号 |  | 是 | users.id |
| `undone_at` | 撤销时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_evidence_chains` AI证据链

模型：`ai_models.AIEvidenceChain`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `chain_type` | 链类型 | （据字段名） | 文本 |  | 否 |  |
| `source_type` | 来源类型 | （据字段名） | 文本 |  | 是 |  |
| `source_id` | 来源编号 | （据字段名） | 编号 |  | 是 |  |
| `title` | 标题 | （据字段名） | 文本 |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `confidence_score` | 置信度评分 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `risk_level` | 风险级别 | （据字段名） | 文本 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_evidence_items` AI证据项

模型：`ai_models.AIEvidenceItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `chain_id` | 链编号 | 指向 `ai_evidence_chains` | 编号 |  | 否 | ai_evidence_chains.id |
| `evidence_type` | 证据类型 | （据字段名） | 文本 |  | 否 |  |
| `document_id` | 文档编号 | （据字段名） | 编号 |  | 是 |  |
| `document_name` | 文档名称 | （据字段名） | 文本 |  | 是 |  |
| `field_path` | 字段路径 | （据字段名） | 文本 |  | 是 |  |
| `field_value` | 字段值 | （据字段名） | 长文本 |  | 是 |  |
| `page_number` | 页编号 | （据字段名） | 整数 |  | 是 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `confidence` | 置信度 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_knowledge_base` AI知识库文档索引

模型：`ai_models.AIKnowledgeBase`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `doc_uuid` | 文档 | （据字段名） | 编号 |  | 否 |  |
| `source_type` | 来源类型 | 取值：`workpaper` 底稿 / `contract` / `confirmation` 函证 / `document` / `report` | 枚举 |  | 否 |  |
| `chunk_index` | 分块序号 | （据字段名） | 整数 |  | 是 |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_model_config` AI模型配置

模型：`ai_models.AIModelConfig`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `preset_key` | 预设键 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `model_name` | 模型名称 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `model_type` | 模型类型 | 取值：`chat` / `embedding` / `ocr` / `rerank` | 枚举 |  | 否 |  |
| `provider` | 提供方 | 取值：`ollama` / `openai_compatible` / `paddleocr` / `deepseek` / `zhipu` / `qwen` / `azure_openai` / `custom` 自定义 | 枚举 |  | 否 |  |
| `endpoint_url` | 端点地址 | （据字段名） | 文本（≤500 字） |  | 是 |  |
| `api_key_ciphertext` | 接口键密文 | v1: 前缀的 Fernet 密文；禁止存储明文 API Key | 长文本 |  | 是 |  |
| `api_key_updated_at` | 接口键更新时间 | （据字段名） | 时间 |  | 是 |  |
| `reasoning_effort` | 推理强度 | （据字段名） | 文本（≤16 字） |  | 是 |  |
| `api_path` | 接口路径 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `ocr_capability` | 识别能力 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `ocr_protocol` | 识别协议 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `auth_scheme` | 认证方案 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `auth_header_name` | 认证表头名称 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `request_timeout_seconds` | 请求超时秒 | （据字段名） | 整数 |  | 是 |  |
| `deployment` | 部署位置 | local / server；由 classify_deployment 按端点推导写入。 | 文本（≤16 字） |  | 否 |  |
| `trust_zone` | 信任域 | 信任域与部署位置正交：server 可是事务所私有服务，也可是不允许客户数据的受限端点。 | 文本（≤32 字） |  | 否 |  |
| `client_data_allowed` | 客户数据允许 | （据字段名） | 是 / 否 |  | 否 |  |
| `mask_policy` | 掩码策略 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `is_active` | 是否启用 | 参与路由（起不再是「唯一生效」）：唯一索引按部署位置约束。 | 是 / 否 |  | 否 |  |
| `context_window` | 上下文窗口 | （据字段名） | 整数 |  | 是 |  |
| `performance_notes` | 执行附注 | （据字段名） | 长文本 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `ai_plugins` AI插件

模型：`extension_models.AIPlugin`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `plugin_id` | 插件编号 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `plugin_name` | 插件名称 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `plugin_version` | 插件版本 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `plugin_description` | 插件说明 | （据字段名） | 长文本 |  | 是 |  |
| `is_enabled` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `config` | 配置 | （据字段名） | JSON |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_task_items` 

模型：`ai_task_job_models.AiTaskItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `job_id` | 任务编号 | 指向 `ai_task_jobs` | 编号 |  | 否 | ai_task_jobs.id |
| `ordinal` | 序号 | （据字段名） | 整数 |  | 否 |  |
| `target_type` | 目标类型 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 编号 |  | 否 |  |
| `target_key` | 目标键 | （据字段名） | 文本（≤200 字） |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `generation_id` | 生成代次编号 | （据字段名） | 编号 |  | 否 |  |
| `message_id` | 消息编号 | 指向 `ai_chat_message` | 编号 |  | 是 | ai_chat_message.id |
| `baseline_version` | 基线版本 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `before_hash` | 之前哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `request_payload` | 请求数据 | （据字段名） | JSON |  | 否 |  |
| `result_summary` | 结果摘要 | （据字段名） | JSON |  | 是 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `max_attempts` | 最大尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `next_attempt_at` | 下一尝试时间 | （据字段名） | 时间 |  | 是 |  |
| `lease_owner` | 租约负责人 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `lease_token` | 租约令牌 | （据字段名） | 编号 |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_task_jobs` 

模型：`ai_task_job_models.AiTaskJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 否 |  |
| `task_kind` | 任务类别 | （据字段名） | 文本（≤40 字） |  | 否 |  |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `request_payload` | 请求数据 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `cancel_requested_at` | 取消请求时间 | （据字段名） | 时间 |  | 是 |  |
| `progress_total` | 进度合计 | （据字段名） | 整数 |  | 否 |  |
| `progress_done` | 进度完成 | （据字段名） | 整数 |  | 否 |  |
| `failed_count` | 失败数量 | （据字段名） | 整数 |  | 否 |  |
| `cancelled_count` | 取消数量 | （据字段名） | 整数 |  | 否 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_workpaper_fills` AI底稿填充记录

模型：`ai_models.AIWorkpaperFill`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `task_id` | 任务编号 | 指向 `ai_workpaper_tasks` | 编号 |  | 是 | ai_workpaper_tasks.id |
| `workpaper_id` | 底稿编号 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `field_path` | 字段路径 | （据字段名） | 文本 |  | 否 |  |
| `field_value` | 字段值 | （据字段名） | 长文本 |  | 是 |  |
| `fill_type` | 填充类型 | （据字段名） | 文本 |  | 否 |  |
| `confidence` | 置信度 | （据字段名） | 金额（2 位小数） |  | 是 |  |
| `model_name` | 模型名称 | （据字段名） | 文本 |  | 是 |  |
| `human_reviewed` | 人工复核 | （据字段名） | 是 / 否 |  | 否 |  |
| `human_value` | 人工值 | （据字段名） | 长文本 |  | 是 |  |
| `is_ai_generated` | 是否AI生成 | （据字段名） | 是 / 否 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `ai_workpaper_tasks` AI底稿填充任务

模型：`ai_models.AIWorkpaperTask`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `workpaper_id` | 底稿编号 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `task_type` | 任务类型 | （据字段名） | 文本 |  | 否 |  |
| `status` | 状态 | 取值：`PENDING` / `PROCESSING` / `COMPLETED` / `FAILED` | 枚举 |  | 否 |  |
| `request_data` | 请求数据 | （据字段名） | JSON |  | 是 |  |
| `result_data` | 结果数据 | （据字段名） | JSON |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `completed_at` | 完成时间 | （据字段名） | 时间 |  | 是 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `wp_ai_generations` AI生成历史记录，完整留痕每次生成的prompt/model/输出/确认信息。

模型：`phase12_models.WpAiGeneration`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `prompt_version` | 提示词版本 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `model` | 模型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `input_hash` | 输入哈希 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `output_text` | 输出文本 | （据字段名） | 长文本 |  | 是 |  |
| `output_structured` |  | 未查明 | JSON |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `confirmed_by` | 确认人 | 指向 `users` | 编号 |  | 是 | users.id |
| `confirmed_at` | 确认时间 | （据字段名） | 时间 |  | 是 |  |

### `wp_recommendation_feedback` 底稿推荐反馈记录（采纳/跳过/手动添加）。

模型：`phase12_models.WpRecommendationFeedback`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `wp_code` | 底稿编码 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `action` | 动作 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `action_by` | 动作人 | 指向 `users` | 编号 |  | 是 | users.id |
| `action_at` | 动作时间 | （据字段名） | 时间 |  | 否 |  |
| `project_type` | 项目类型 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `industry` | 行业 | （据字段名） | 文本（≤100 字） |  | 是 |  |

<a id="x-group"></a>
## X. 平台基础设施（事件、任务、日志、配置）

### `advanced_query_writeback` 高级查询回写身份 / 审计记录表 [advanced-query-module Task 1.3]

模型：`custom_query_models.AdvancedQueryWriteback`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `addr_id` | 地址编号 | addr_id: {wp_code}/{sheet_code}/{coordinate_key}（R3.1） | 长文本 |  | 否 |  |
| `wp_id` | 底稿 | wp_id: resolve_instance 附加（可空） | 编号 |  | 是 |  |
| `old_value` | 旧值 | （据字段名） | JSON |  | 是 |  |
| `new_value` | 新值 | （据字段名） | JSON |  | 是 |  |
| `operator_id` | 操作人编号 | （据字段名） | 编号 |  | 否 |  |
| `result` | 结果 | result: `success` 成功/`failed` 失败 | 长文本 |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `asset_blobs` 

模型：`asset_blob_models.AssetBlob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `content_hash` | 内容哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `byte_size` | 字节大小 | （据字段名） | 整数 |  | 否 |  |
| `detected_media_type` | 检测到媒体类型 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `storage_type` | 存储类型 | （据字段名） | 文本（≤24 字） |  | 否 |  |
| `storage_key` | 存储键 | （据字段名） | 长文本 |  | 否 |  |
| `ingress_policy_version` | 入口策略版本 | （据字段名） | 文本（≤32 字） |  | 否 |  |
| `security_status` | 安全状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_type` | 操作人类型 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `actor_user_id` | 操作人用户编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `actor_service_identity_id` | 操作人服务身份编号 | 指向 `service_identities` | 编号 |  | 是 | service_identities.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `audit_chain_head` 每条审计链的事务内权威链尾。

模型：`audit_log_models.AuditChainHead`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `chain_key` | 链键 | （据字段名） | 文本（≤80 字） | 是 |  |  |
| `tail_entry_id` | 末尾条目编号 | （据字段名） | 编号 |  | 否 |  |
| `tail_hash` | 末尾哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `entry_count` | 条目数量 | （据字段名） | 整数 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `audit_log_entries` 审计日志条目 — 不可变追加式

模型：`audit_log_models.AuditLogEntry`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `ts` | 时间戳 | （据字段名） | 时间 |  | 否 |  |
| `user_id` | 用户 | （据字段名） | 编号 |  | 是 |  |
| `session_id` | 会话编号 | （据字段名） | 文本（≤128 字） |  | 是 |  |
| `action_type` | 动作类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `object_type` | 对象类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 是 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `ip` | IP 地址 | （据字段名） | 文本（≤45 字） |  | 是 |  |
| `ua` | 浏览器标识 | （据字段名） | 长文本 |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `prev_hash` | 上一哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `entry_hash` | 条目哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |

### `background_job_items` 后台长任务明细项。

模型：`phase12_models.BackgroundJobItem`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `job_id` | 任务编号 | 指向 `background_jobs` | 编号 |  | 否 | background_jobs.id |
| `wp_id` | 底稿 | 指向 `working_paper` | 编号 |  | 否 | working_paper.id |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |

### `background_jobs` 后台长任务主表（批量刷新/生成/提交/下载等）。

模型：`phase12_models.BackgroundJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `job_type` | 任务类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤30 字） |  | 否 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 是 |  |
| `progress_total` | 进度合计 | （据字段名） | 整数 |  | 否 |  |
| `progress_done` | 进度完成 | （据字段名） | 整数 |  | 否 |  |
| `failed_count` | 失败数量 | （据字段名） | 整数 |  | 否 |  |
| `initiated_by` | 发起人 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `config_references` 配置引用记录——记录哪个项目引用了哪个模板

模型：`shared_config_models.ConfigReference`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `template_id` | 模板编号 | 指向 `shared_config_templates` | 编号 |  | 否 | shared_config_templates.id |
| `config_type` | 配置类型 | 配置类型 | 文本（≤50 字） |  | 否 |  |
| `applied_at` | 已应用时间 | 引用时间 | 时间 |  | 是 |  |
| `applied_by` | 已应用人 | 操作人；指向 `users` | 编号 |  | 是 | users.id |
| `is_customized` | 是否已定制 | 引用后是否做了本地修改 | 是 / 否 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `cross_module_conflicts` 跨模块冲突调解记录 — 上游数据变更与手工覆盖的冲突追踪

模型：`v3_refinement_models.CrossModuleConflict`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `source_module` | 来源模块 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `source_id` | 来源编号 | （据字段名） | 编号 |  | 否 |  |
| `target_module` | 目标模块 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `target_id` | 目标编号 | （据字段名） | 编号 |  | 否 |  |
| `target_field` | 目标字段 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `upstream_value` | 上游值 | （据字段名） | 长文本 |  | 是 |  |
| `manual_value` | 手工值 | （据字段名） | 长文本 |  | 是 |  |
| `final_value` | 最终值 | （据字段名） | 长文本 |  | 是 |  |
| `resolution` | 处理结果 | （据字段名） | 文本（≤20 字） |  | 是 |  |
| `resolved_by` | 解决人 | 指向 `users` | 编号 |  | 是 | users.id |
| `resolved_at` | 解决时间 | （据字段名） | 时间 |  | 是 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `custom_query_templates` 自定义查询模板。

模型：`custom_query_models.CustomQueryTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `data_source` | 数据来源 | （据字段名） | 文本（≤50 字） |  | 是 |  |
| `config` | 配置 | JSON 字面量在 PG/SQLite 双方言下都能解析为合法 JSON 对象 | JSON |  | 否 |  |
| `scope` | 范围 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `shared_project_ids` | 共享项目列表 | 显式 default 使 INSERT 自带空列表，两种方言行为一致。 | 编号 |  | 否 |  |
| `tags` | 标签 | （据字段名） | 长文本 |  | 否 |  |
| `use_count` | 使用数量 | （据字段名） | 整数 |  | 否 |  |
| `last_used_at` | 最近已用时间 | （据字段名） | 时间 |  | 是 |  |
| `creator_id` | 创建人编号 | 指向 `users` | 编号 |  | 是 | users.id |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 否 | users.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `enum_dict_overrides` 枚举字典覆盖（label / color 可改，value 不可改）

模型：`enum_dict_override_models.EnumDictOverride`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `dict_key` | 字典键 | （据字段名） | 文本（≤64 字） | 是 |  |  |
| `value` | 值 | （据字段名） | 文本（≤64 字） | 是 |  |  |
| `label_override` | 显示名覆盖 | （据字段名） | 文本（≤255 字） |  | 是 |  |
| `color_override` | 颜色覆盖 | （据字段名） | 文本（≤32 字） |  | 是 |  |
| `updated_by` | 修改人 | 通用字段，见文首 | 编号 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `feature_flags` Feature flag 功能开关（zero-downtime-deployment 组件 8）。

模型：`audit_platform_models.FeatureFlag`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `flag_key` | 标记键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `description` | 说明 | （据字段名） | 长文本 |  | 是 |  |
| `enabled` | 是否启用 | （据字段名） | 是 / 否 |  | 否 |  |
| `rollout_percentage` | 灰度百分比 | （据字段名） | 整数 |  | 否 |  |
| `whitelist_user_ids` | 白名单用户列表 | （据字段名） | JSON |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `logs` 操作日志

模型：`core.Log`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 是 | users.id |
| `action_type` | 动作类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `object_type` | 对象类型 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 是 |  |
| `old_value` | 旧值 | （据字段名） | JSON |  | 是 |  |
| `new_value` | 新值 | （据字段名） | JSON |  | 是 |  |
| `ip_address` | IP 地址地址 | （据字段名） | 文本（≤45 字） |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `platform_job_attempts` 

模型：`platform_job_models.PlatformJobAttempt`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `job_id` | 任务编号 | 指向 `platform_jobs` | 编号 |  | 否 | platform_jobs.id |
| `attempt_no` | 尝试编号 | （据字段名） | 整数 |  | 否 |  |
| `lease_token` | 租约令牌 | （据字段名） | 编号 |  | 否 |  |
| `worker_id` | 工作进程编号 | （据字段名） | 文本（≤160 字） |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 否 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |

### `platform_jobs` 

模型：`platform_job_models.PlatformJob`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `operation` | 操作 | （据字段名） | 文本（≤48 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `actor_id` | 操作人编号 | 指向 `users` | 编号 |  | 否 | users.id |
| `idempotency_key` | 幂等键 | （据字段名） | 文本（≤128 字） |  | 否 |  |
| `request_hash` | 请求哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `payload_ref` | 数据引用 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤20 字） |  | 否 |  |
| `stage` | 阶段 | （据字段名） | 文本（≤64 字） |  | 是 |  |
| `progress_current` | 进度当前 | （据字段名） | 整数 |  | 否 |  |
| `progress_total` | 进度合计 | （据字段名） | 整数 |  | 否 |  |
| `progress_message` | 进度消息 | （据字段名） | 长文本 |  | 是 |  |
| `reserved_bytes` | 预留字节数 | （据字段名） | 整数 |  | 否 |  |
| `result_ref` | 结果引用 | （据字段名） | JSON |  | 是 |  |
| `error_code` | 错误编码 | （据字段名） | 文本（≤80 字） |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `attempt_count` | 尝试数量 | （据字段名） | 整数 |  | 否 |  |
| `max_attempts` | 最大尝试次数 | （据字段名） | 整数 |  | 否 |  |
| `next_attempt_at` | 下一尝试时间 | （据字段名） | 时间 |  | 是 |  |
| `lease_owner` | 租约负责人 | （据字段名） | 文本（≤160 字） |  | 是 |  |
| `lease_token` | 租约令牌 | （据字段名） | 编号 |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | （据字段名） | 时间 |  | 是 |  |
| `heartbeat_at` | 心跳时间 | （据字段名） | 时间 |  | 是 |  |
| `cancel_requested_at` | 取消请求时间 | （据字段名） | 时间 |  | 是 |  |
| `version` | 版本号 | （据字段名） | 整数 |  | 否 |  |
| `queued_at` | 排队时间 | （据字段名） | 时间 |  | 否 |  |
| `started_at` | 开始时间 | （据字段名） | 时间 |  | 是 |  |
| `finished_at` | 结束时间 | （据字段名） | 时间 |  | 是 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `query_artifacts` 一次「导出全部」生成的不可变查询证据清单。

模型：`query_evidence_models.QueryArtifact`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `run_id` | 运行编号 | 指向 `query_runs` | 编号 |  | 是 | query_runs.id |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `entry` | 条目 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `source_key` | 来源键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `definition_hash` | 定义哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `version_vector` | 版本向量 | （据字段名） | JSON |  | 否 |  |
| `vector_hash` | 向量哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `scope` | 范围 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `file_name` | 文件名 | （据字段名） | 文本（≤255 字） |  | 否 |  |
| `storage_key` | 存储键 | （据字段名） | 长文本 |  | 否 |  |
| `media_type` | 媒体类型 | （据字段名） | 文本（≤120 字） |  | 否 |  |
| `byte_size` | 字节大小 | （据字段名） | 整数 |  | 否 |  |
| `sha256` | 文件哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `row_count` | 行数量 | （据字段名） | 整数 |  | 否 |  |
| `columns` | 列 | （据字段名） | JSON |  | 否 |  |
| `manifest` | 清单 | （据字段名） | JSON |  | 否 |  |
| `manifest_sha256` | 清单SHA256 哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `retention_until` | 保留截止 | （据字段名） | 时间 |  | 否 |  |
| `purged_at` | 清除时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `query_runs` 一次查询定义在一个来源版本上的不可变运行记录。

模型：`query_evidence_models.QueryRun`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `entry` | 条目 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `origin` | 来源 | （据字段名） | 文本（≤16 字） |  | 否 |  |
| `template_id` | 模板编号 | （据字段名） | 编号 |  | 是 |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 是 | projects.id |
| `year` | 年度 | 通用字段，见文首 | 整数 |  | 是 |  |
| `source_key` | 来源键 | （据字段名） | 文本（≤200 字） |  | 否 |  |
| `definition` | 定义 | （据字段名） | JSON |  | 否 |  |
| `definition_hash` | 定义哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `definition_version` | 定义版本 | （据字段名） | 整数 |  | 否 |  |
| `scope` | 范围 | （据字段名） | JSON |  | 否 |  |
| `labels` | 标签 | （据字段名） | JSON |  | 否 |  |
| `version_vector` | 版本向量 | （据字段名） | JSON |  | 否 |  |
| `vector_hash` | 向量哈希 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `vector_weak` | 向量弱 | （据字段名） | 是 / 否 |  | 否 |  |
| `captured_at` | 采集时间 | （据字段名） | 时间 |  | 否 |  |
| `execution_count` | 执行数量 | （据字段名） | 整数 |  | 否 |  |
| `first_executed_at` | 首次执行时间 | （据字段名） | 时间 |  | 否 |  |
| `last_executed_at` | 最近执行时间 | （据字段名） | 时间 |  | 否 |  |
| `last_total` | 最近合计 | （据字段名） | 整数 |  | 是 |  |
| `last_warnings` | 最近警告 | （据字段名） | JSON |  | 否 |  |
| `hidden_at` | 隐藏时间 | （据字段名） | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |

### `shared_config_templates` 共享配置模板

模型：`shared_config_models.SharedConfigTemplate`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `name` | 名称 | 模板名称 | 文本（≤200 字） |  | 否 |  |
| `description` | 说明 | 模板说明 | 长文本 |  | 是 |  |
| `config_type` | 配置类型 | 配置类型 | 文本（≤50 字） |  | 否 |  |
| `owner_type` | 负责人类型 | 所有者类型: system/group/personal | 文本（≤20 字） |  | 否 |  |
| `owner_user_id` | 负责人用户编号 | 个人模板的所有者；指向 `users` | 编号 |  | 是 | users.id |
| `owner_project_id` | 负责人项目编号 | 集团模板的所属项目；指向 `projects` | 编号 |  | 是 | projects.id |
| `owner_project_name` | 负责人项目名称 | 集团/项目名称（冗余，方便展示） | 文本（≤200 字） |  | 是 |  |
| `config_data` | 配置数据 | 配置数据JSON | JSON |  | 否 |  |
| `config_version` | 配置版本 | 版本号 | 整数 |  | 是 |  |
| `applicable_standard` | 适用准则 | 适用标准: soe/listed/both | 文本（≤50 字） |  | 是 |  |
| `is_public` | 是否公开 | 是否公开（所有人可见） | 是 / 否 |  | 是 |  |
| `allowed_project_ids` | 允许项目列表 | 允许引用的项目ID列表（空=不限制） | JSON |  | 是 |  |
| `reference_count` | 引用数量 | 被引用次数 | 整数 |  | 是 |  |
| `last_referenced_at` | 最近被引用时间 | 最后被引用时间 | 时间 |  | 是 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `updated_at` | 更新时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `is_deleted` | 是否已删除 | 通用字段，见文首 | 是 / 否 |  | 否 |  |
| `deleted_at` | 删除时间 | 通用字段，见文首 | 时间 |  | 是 |  |

### `task_events` 事件总线与补偿队列

模型：`phase15_models.TaskEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `task_node_id` | 任务节点编号 | （据字段名） | 编号 |  | 是 |  |
| `payload` | 数据内容 | （据字段名） | JSON |  | 否 |  |
| `status` | 状态 | `queued` 排队中/replaying/`succeeded` 成功/`failed` 失败/dead_letter | 文本（≤16 字） |  | 否 |  |
| `retry_count` | 重试次数 | （据字段名） | 整数 |  | 否 |  |
| `max_retries` | 最大重试次数 | （据字段名） | 整数 |  | 否 |  |
| `next_retry_at` | 下一重试时间 | （据字段名） | 时间 |  | 是 |  |
| `error_message` | 错误信息 | （据字段名） | 长文本 |  | 是 |  |
| `trace_id` | 追踪号 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `aggregate_type` | 汇总类型 | 聚合类型，如 procedure_row_task | 文本（≤40 字） |  | 是 |  |
| `aggregate_id` | 汇总编号 | 聚合实例 id | 编号 |  | 是 |  |
| `aggregate_version` | 汇总版本 | aggregate 内单调版本，按序投递 | 整数 |  | 是 |  |
| `idempotency_key` | 幂等键 | 幂等键，全局唯一（部分唯一索引） | 文本（≤128 字） |  | 是 |  |
| `delegation_batch_id` | 委派批次编号 | 批量委派批次 id，用于通知聚合 | 编号 |  | 是 |  |
| `available_at` |  | 可领取时间（退避） | 时间 |  | 是 |  |
| `lease_expires_at` | 租约过期时间 | 领取租约到期时间 | 时间 |  | 是 |  |
| `claimed_by` | 领取人 | 领取者标识 | 文本（≤80 字） |  | 是 |  |
| `processed_at` | 处理时间 | 投递完成时间 | 时间 |  | 是 |  |
| `dead_letter_at` |  | 进入死信时间 | 时间 |  | 是 |  |
| `last_error` | 最近错误 | 最近一次失败原因 | 长文本 |  | 是 |  |

### `time_machine_snapshots` 时光机增量快照 — RFC 6902 JSON Patch 反向 diff

模型：`v3_refinement_models.TimeMachineSnapshot`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `instance_id` | 实例编号 | （据字段名） | 编号 |  | 否 |  |
| `instance_type` | 实例类型 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `user_id` | 用户 | 指向 `users` | 编号 |  | 否 | users.id |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 | projects.id |
| `diff_json` | 差异JSON | （据字段名） | JSON |  | 否 |  |
| `parent_snapshot_id` | 上级快照编号 | 指向 `time_machine_snapshots` | 编号 |  | 是 | time_machine_snapshots.id |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |
| `diff_patch` |  | 未查明 | JSON |  | 是 |  |
| `module` | 模块 | （据字段名） | 文本（≤50 字） |  | 否 |  |
| `snapshot_data` | 快照数据 | 都能解析为合法空 JSON 对象（同 report_models / custom_query_models 约定）。 | JSON |  | 否 |  |
| `created_by` | 创建人 | 通用字段，见文首 | 编号 |  | 是 |  |

### `trace_events` 统一过程留痕主表

模型：`phase14_models.TraceEvent`

| 字段 | 中文名 | 说明 | 类型 | 主键 | 可空 | 外键 |
|---|---|---|---|---|---|---|
| `id` | 主键 | 通用字段，见文首 | 编号 | 是 |  |  |
| `project_id` | 项目 | 通用字段，见文首 | 编号 |  | 否 |  |
| `event_type` | 事件类型 | （据字段名） | 文本（≤64 字） |  | 否 |  |
| `object_type` | 对象类型 | `workpaper` 底稿/`adjustment` 调整分录/report/note/procedure/conversation/`export` 导出/gate_decision/issue_ticket/offline_conflict | 文本（≤32 字） |  | 否 |  |
| `object_id` | 对象编号 | （据字段名） | 编号 |  | 否 |  |
| `actor_id` | 操作人编号 | （据字段名） | 编号 |  | 否 |  |
| `actor_role` | 操作人角色 | assistant/`manager` 经理/`partner` 合伙人/`qc` 质控/`admin` 管理员 | 文本（≤32 字） |  | 是 |  |
| `action` | 动作 | （据字段名） | 文本（≤100 字） |  | 否 |  |
| `decision` | 决定 | allow/block/warn - 门禁/SoD场景 | 文本（≤16 字） |  | 是 |  |
| `reason_code` | 原因编码 | 对齐 v2 4.5.6 统一原因码 | 文本（≤64 字） |  | 是 |  |
| `from_status` | 从状态 | 状态流转起始状态 | 文本（≤32 字） |  | 是 |  |
| `to_status` | 到状态 | 状态流转目标状态 | 文本（≤32 字） |  | 是 |  |
| `before_snapshot` | 之前快照 | （据字段名） | JSON |  | 是 |  |
| `after_snapshot` | 之后快照 | （据字段名） | JSON |  | 是 |  |
| `content_hash` | 内容哈希 | 对象内容 SHA-256（取证用） | 文本（≤64 字） |  | 是 |  |
| `version_no` | 版本编号 | （据字段名） | 整数 |  | 是 |  |
| `trace_id` | 追踪号 | 格式: trc_{yyyyMMddHHmmss}_{uuid[:12]} | 文本（≤64 字） |  | 否 |  |
| `created_at` | 创建时间 | 通用字段，见文首 | 时间 |  | 否 |  |

## 附：只在迁移 SQL 中建的表

### `ai_chat_mcp_call_log`

建表迁移：`V149__ai_chat_mcp_scoped_tokens.sql`。AI 对话经 MCP 调用工具的日志

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  run_id UUID NOT NULL
  tool_call_id VARCHAR(128) NOT NULL
  tool_name VARCHAR(64) NOT NULL
  token_id VARCHAR(32) NOT NULL
  user_id UUID NOT NULL
  project_id UUID NOT NULL
  status VARCHAR(20) NOT NULL DEFAULT 'started'
  result_bytes INTEGER NOT NULL DEFAULT 0
  duration_ms INTEGER NOT NULL DEFAULT 0
  error_code VARCHAR(64)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `ai_chat_mcp_token_revocations`

建表迁移：`V149__ai_chat_mcp_scoped_tokens.sql`。MCP 作用域令牌的吊销记录

```sql
  token_id VARCHAR(32) PRIMARY KEY
  run_id UUID NOT NULL
  user_id UUID NOT NULL
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT now()
  reason VARCHAR(64) NOT NULL DEFAULT 'run_terminal'
```

### `app_audit_log`

建表迁移：`V050__audit_log_table.sql`。轻量操作审计（密码确认、EQCR 判断、质控报告导出等写入）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id UUID
  action VARCHAR(100) NOT NULL
  resource_type VARCHAR(64)
  resource_id VARCHAR(64)
  details JSONB
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `checklist_responses`

建表迁移：`V085__checklist_responses.sql`。底稿检查表 / HTML 表单逐项填写内容，按 (wp_id, item_id) 唯一；最初为 A1-15/A1-16 核对表建，现为各底稿通用

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  project_id UUID NOT NULL REFERENCES projects(id)
  wp_id UUID NOT NULL REFERENCES working_paper(id)
  item_id VARCHAR(20) NOT NULL
  conclusion VARCHAR(5)
  remark TEXT
  wp_ref VARCHAR(100)
  updated_by UUID REFERENCES users(id)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  UNIQUE(wp_id, item_id)
```

### `custom_account_packages`

建表迁移：`V090__custom_account_packages.sql`。项目级 / 事务所级自定义科目工作包（导出模板→编辑→导入）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  scope VARCHAR(16) NOT NULL
  scope_id UUID NOT NULL
  wp_code VARCHAR(32) NOT NULL
  industry VARCHAR(32)
  package_json JSONB NOT NULL
  created_by UUID
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  is_deleted BOOLEAN NOT NULL DEFAULT false
  CONSTRAINT uq_custom_account_pkg UNIQUE (scope, scope_id, wp_code)
```

### `data_snapshots`

建表迁移：`V046__note_lazy_tables.sql`。附注相关数据快照（V046 补建的懒建表）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  project_id UUID NOT NULL
  year INT NOT NULL
  snapshot_data JSONB NOT NULL
  data_hash VARCHAR(64)
  created_at TIMESTAMPTZ DEFAULT now()
```

### `group_note_templates`

建表迁移：`V046__note_lazy_tables.sql`。集团附注模板（V046 补建）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  name VARCHAR(200) NOT NULL
  template_data JSONB NOT NULL
  created_by UUID
  created_at TIMESTAMP DEFAULT now()
```

### `note_section_locks`

建表迁移：`V046__note_lazy_tables.sql`。附注章节锁（V046 补建）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  project_id UUID NOT NULL
  year INT NOT NULL
  section_code VARCHAR(100) NOT NULL
  locked_by UUID
  locked_by_name VARCHAR(150)
  acquired_at TIMESTAMPTZ DEFAULT now()
  heartbeat_at TIMESTAMPTZ DEFAULT now()
  released_at TIMESTAMPTZ
```

### `note_section_templates`

建表迁移：`V046__note_lazy_tables.sql`。附注章节模板（V046 补建）

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  name VARCHAR(200) NOT NULL
  template_data JSONB NOT NULL
  created_at TIMESTAMP DEFAULT now()
```

### `procedure_instance_identity_v217_backup`

建表迁移：`V225__procedure_identity_and_trim_confirmation.sql`。程序实例身份归一前的备份

```sql
  instance_id UUID PRIMARY KEY REFERENCES procedure_instances(id) ON DELETE CASCADE
  old_audit_cycle VARCHAR(10) NOT NULL
  old_procedure_code VARCHAR(50) NOT NULL
  old_wp_code VARCHAR(50)
  backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `project_classification_v219_backup`

建表迁移：`V219__project_category_scenario_split.sql`。项目质控分类 / 专项场景拆分前的备份

```sql
  project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE
  old_business_category VARCHAR(20)
  old_scenario VARCHAR(20) NOT NULL
  backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `project_user_level_backfill`

建表迁移：`V203__partner_manager_edit_level_backfill.sql`。合伙人、经理项目级别回填前的备份

```sql
  project_user_id UUID PRIMARY KEY
  prior_role projectuserrole NOT NULL
  prior_permission_level permissionlevel NOT NULL
  target_role projectuserrole NOT NULL
  target_permission_level permissionlevel NOT NULL
  rule VARCHAR(20) NOT NULL
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `schema_drift_log`

建表迁移：`V026__schema_drift_log.sql`。ORM 与数据库结构漂移的检测记录

```sql
  id SERIAL PRIMARY KEY
  table_name VARCHAR(100) NOT NULL
  column_name VARCHAR(100)
  drift_type VARCHAR(50) NOT NULL
  detail TEXT
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### `schema_migration_failures`

建表迁移：`V025__schema_migration_failures.sql`。迁移执行失败记录

```sql
  version VARCHAR(20) PRIMARY KEY
  filename VARCHAR(255) NOT NULL
  error_type VARCHAR(100) NOT NULL
  error_message TEXT NOT NULL
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  attempt_count INTEGER NOT NULL DEFAULT 1
```

### `schema_version`

建表迁移：`V002__add_schema_version.sql`。已执行的迁移版本（MigrationRunner 记账表）

```sql
  id SERIAL PRIMARY KEY
  version VARCHAR(20) NOT NULL UNIQUE
  filename VARCHAR(255) NOT NULL
  applied_at TIMESTAMP NOT NULL DEFAULT NOW()
  checksum VARCHAR(64) NOT NULL
```

### `system_settings`

建表迁移：`V048__system_settings_kv.sql`。系统级键值配置

```sql
  key VARCHAR(100) PRIMARY KEY
  value TEXT
  description VARCHAR(500)
  updated_by UUID
  updated_at TIMESTAMPTZ DEFAULT now()
  created_at TIMESTAMPTZ DEFAULT now()
```

### `tb_aux_balance_summary`

建表迁移：`V207__restore_tb_aux_balance_summary.sql`。辅助余额汇总表

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  project_id UUID NOT NULL
  year INTEGER NOT NULL
  dim_type VARCHAR(64)
  account_code VARCHAR(64)
  account_name VARCHAR(255)
  aux_code VARCHAR(128)
  aux_name VARCHAR(255)
  record_count INTEGER DEFAULT 0
  opening_balance NUMERIC
  debit_amount NUMERIC
  credit_amount NUMERIC
  closing_balance NUMERIC
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
  opening_direction VARCHAR(10)
  closing_direction VARCHAR(10)
```

### `working_paper_oo_content_revision`

建表迁移：`V155__oo_content_revision.sql`。底稿 OnlyOffice 内容修订号

```sql
  wp_id UUID NOT NULL
  entry_id VARCHAR(512) NOT NULL
  revision BIGINT NOT NULL DEFAULT 0
  reason VARCHAR(128)
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  PRIMARY KEY (wp_id, entry_id)
```

### `workpaper_template_override_version`

建表迁移：`V154__workpaper_template_override_version.sql`。底稿模板覆盖层的版本

```sql
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  wp_code TEXT NOT NULL
  authoritative_stem TEXT NOT NULL
  scope VARCHAR(20) NOT NULL
  project_id UUID REFERENCES projects(id) ON DELETE RESTRICT
  group_id UUID
  file_relpath TEXT NOT NULL
  extension VARCHAR(10) NOT NULL
  sha256 CHAR(64) NOT NULL
  is_current BOOLEAN NOT NULL DEFAULT false
  parent_version_id UUID REFERENCES workpaper_template_override_version(id) ON DELETE RESTRICT
  created_by UUID REFERENCES users(id) ON DELETE SET NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  CONSTRAINT ck_wptov_scope CHECK (scope IN ('firm_default', 'group_custom', 'project'))
  CONSTRAINT ck_wptov_scope_ids CHECK ( (scope = 'project' AND project_id IS NOT NULL AND group_id IS NULL) OR (scope = 'group_custom' AND group_id IS NOT NULL AND project_id IS NULL) OR (scope = 'firm_default' AND project_id IS NULL AND group_id IS NULL) )
  CONSTRAINT ck_wptov_sha256 CHECK (wpsync_is_digest(sha256))
  CONSTRAINT ck_wptov_wp_code_non_empty CHECK (length(btrim(wp_code)) > 0)
  CONSTRAINT ck_wptov_stem_non_empty CHECK (length(btrim(authoritative_stem)) > 0)
  CONSTRAINT ck_wptov_extension_form CHECK (extension ~ '^\.[a-z0-9]+$')
  CONSTRAINT ck_wptov_relpath_matches_extension CHECK (file_relpath LIKE '%' || extension)
  CONSTRAINT ck_wptov_relpath_no_escape CHECK ( file_relpath NOT LIKE '%..%' AND file_relpath NOT LIKE '/%' AND position('\' in file_relpath) = 0 AND file_relpath !~ '^[A-Za-z]:' AND length(btrim(file_relpath)) > 0 )
  CONSTRAINT ck_wptov_no_self_parent CHECK (parent_version_id IS NULL OR parent_version_id <> id)
```

### `wp_migration_snapshots`

建表迁移：`V031__wp_migration_snapshots.sql`。底稿模板迁移前快照

```sql
  id UUID PRIMARY KEY
  wp_id UUID NOT NULL
  parsed_data_snapshot JSONB NOT NULL
  migration_reason VARCHAR(100) NOT NULL DEFAULT 'template_upgrade'
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
```

### `wp_sheet_locks`

建表迁移：`V027__wp_sheet_locks.sql`。HTML 渲染器的 sheet 级协作锁

```sql
  id VARCHAR(36) PRIMARY KEY
  wp_id VARCHAR(36) NOT NULL
  sheet_name VARCHAR(200) NOT NULL
  locked_by VARCHAR(36) NOT NULL
  locked_by_name VARCHAR(100) DEFAULT ''
  acquired_at TIMESTAMP WITH TIME ZONE NOT NULL
  heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL
  released_at TIMESTAMP WITH TIME ZONE
```
