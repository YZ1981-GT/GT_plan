# Requirements Document

## Introduction

本 feature 为程序委派建立服务端强制、fail-closed 的底稿与页面可见性隔离。Visibility_System 以 `wp_index_id` 约束底稿范围，以 `sheet_key` 约束页面范围，并通过统一 Wp_Bound_Gate、Action_Matrix、不可枚举拒绝、安全审计、稳定分页和证据门禁覆盖所有底稿绑定入口。Wp_Bound_Gate 统一调用 `resolve_wp_binding_and_access()`，先解析 Binding_Minimum，再返回资源绑定、角色、查询层明确产出的 `access_kind`、允许页面键与当前版本。

底稿主编与程序行执行人/操作复核人采用分层委派：`WorkingPaper.assigned_to` 保存 `user_id`，`ProcedureInstance.assigned_to` 保存 `staff_id`，两者仅通过目标项目中唯一 active staff↔user 映射表达同一自然人；`ProcedureRowTask` 仅保存程序行执行人和操作复核人，不产生额外 Staff_Projection。所有 Non_Admin_User 的授权均受 `scope_cycles` 上界约束。仓库权威表名为 `working_paper`、`wp_index`、`procedure_instances`、`procedure_row_tasks`、`staff_members` 与 `project_assignments`。

## Glossary

- **Visibility_System（可见性系统）**：对底稿可见性、动作权限、资源绑定和拒绝响应作出服务端权威判定的系统。
- **Wp_Bound_Gate（底稿资源统一门）**：所有能够读取、修改、生成、下载、预览、转换、复核或推理某一底稿资源的入口必须调用的统一服务端授权门。
- **Visibility_Unit（可见性单元）**：底稿范围授权的稳定粒度，取 `wp_index_id`。
- **Sheet_Key（页面键）**：在一个 `wp_index_id` 内稳定标识程序行映射页面的服务端权威键。
- **Page_Visibility_Set（页面可见集）**：当前用户在某一 `wp_index_id` 内可访问的 Sheet_Key 集合。
- **ProcedureRowTask（程序行任务）**：以稳定程序行标识承载 Row_Assignee、Operation_Reviewer 和程序行映射 Sheet_Key 的行级委派记录。
- **Admin_User（管理员用户）**：具有 system `admin` 身份的用户，是唯一不受 `scope_cycles` 上界约束的用户类别。
- **Non_Admin_User（非管理员用户）**：除 Admin_User 外的所有用户，包括 Supervisor 与 Restricted_User。
- **Restricted_User（受限用户）**：底稿可见范围受委派和历史参与共同限制的 Non_Admin_User，包括审计助理、仅承担程序行一级复核的 Operation_Reviewer、readonly 与无法可靠分类的用户。
- **Supervisor（主管用户）**：在当前项目具备唯一 active staff↔user 映射、唯一 active 项目成员链路且角色为 `partner`、`signing_partner`、`manager`、`qc` 或 `eqcr` 的 Non_Admin_User。
- **Operation_Reviewer（操作复核人）**：由 `ProcedureRowTask.reviewer_staff_id` 表示的程序行一级复核人，不等同于 Supervisor。
- **scope_cycles**：Non_Admin_User 在当前项目可访问审计循环的集合，是任何底稿级授权的粗粒度上界。
- **Workpaper_Lead（底稿主编）**：负责整张底稿编制的人员；权威字段是保存 `user_id` 的 `WorkingPaper.assigned_to`。
- **Staff_Projection（staff 投影）**：`ProcedureInstance.assigned_to` 保存的 Workpaper_Lead staff 表示；Staff_Projection 与 `WorkingPaper.assigned_to` 仅通过唯一 active staff↔user 映射指向同一自然人，字段值直接相等不构成同人判定。
- **Row_Assignee（程序执行人）**：由 `ProcedureRowTask.assignee_staff_id` 表示的程序行执行人。
- **Delegated_Set（委派集）**：Workpaper_Lead 对应 `wp_index_id` 集合与 active、非取消、非软删 `ProcedureRowTask` 的 Row_Assignee/Operation_Reviewer 对应 `wp_index_id` 集合之并集。
- **History_Set（历史参与集）**：当前用户曾作为 Workpaper_Lead、Row_Assignee 或 Operation_Reviewer 参与过的去重 `wp_index_id` 集合。
- **Restricted_Visible_Set（受限可见集）**：固定定义为 `(Delegated_Set ∪ History_Set) ∩ scope_cycles`。
- **History_Only_Read_Set（历史只读集）**：固定定义为 `(History_Set ∩ scope_cycles) \ Delegated_Set`。
- **Current_Version（当前版本）**：某 `wp_index_id` 当前生效的底稿版本，不表示历史参与期间版本。
- **Action_Matrix（动作矩阵）**：按用户类别、参与身份、具体 route、HTTP method、动作类别、源状态和目标状态定义完整允许条目的唯一服务端授权矩阵。
- **Access_Grant（访问授权项）**：恰好包含一个已登记 `access_kind`、其来源身份、允许页面和动作范围的独立授权项；同一资源可产生多个 Access_Grant，但每个 Access_Grant 必须独立完整命中 Action_Matrix 后才可并集合并。
- **Review_Whitelist（复核白名单）**：Action_Matrix 中专门授予 Operation_Reviewer 的完整复核条目集合。
- **Wp_Bound_Resource（底稿绑定资源）**：能够通过 `wp_id`、`wp_index_id`、`wp_code`、`sheet_name`、`version`、附件、文件、复核对象、AI 上下文或其组合定位到具体底稿的数据或操作。
- **Binding_Minimum（绑定解析最小信息）**：Wp_Bound_Gate 作出判定前，为唯一解析资源绑定所必需且不包含业务内容、非绑定敏感元数据或可推断信息的最小服务端信息。
- **Wp_Binding_Access_Resolver（绑定与访问解析器）**：唯一服务端函数 `resolve_wp_binding_and_access()`；函数先解析 Binding_Minimum，再返回 `binding`、`role`、`access_kind`、`allowed_sheet_keys` 与 `current_version`。
- **access_kind（访问种类）**：查询层或 SQL 对当前资源绑定与参与身份明确产出的访问类别；`access_kind` 不得仅由应用层集合包含关系推断。
- **External_Not_Found（外部统一不可见响应）**：Wp_Bound_Resource 不存在、跨项目、越权或当前用户无权访问请求版本时，对外固定返回 HTTP 404 与仅含 `detail` 的响应体 `{"detail":"资源不存在或不可访问"}`。
- **Security_Audit（内部安全审计）**：仅对授权审计人员可见的可靠内部记录，保留 `not_found`、`cross_project`、`out_of_scope`、`not_delegated`、`sheet_unmapped`、`action_denied`、`historical_version`、`binding_conflict`、`token_invalid` 或 `rate_limited` 等真实拒绝原因。
- **Security_Audit_Outbox（安全审计发件箱）**：与拒绝事实可靠关联、支持提交后持久投递 Security_Audit 的内部记录通道。
- **Operational_Alert（运维告警）**：安全审计或安全配置异常时发送到既有运维监控渠道、且不改变访问拒绝结果的告警。
- **Procedure_Wp_Resolver（程序底稿解析器）**：把标准 procedure 或自定义 procedure 的全部已提供绑定来源唯一且一致地解析为 `wp_index_id` 的服务端权威解析能力。
- **Delegation_Transaction（委派事务）**：写入、转派或清空底稿主编层或程序行层委派时执行的原子事务。
- **Scope_Expansion（scope 扩权）**：由通过既有项目委派权限校验的用户显式发起、为跨循环委派增加目标用户 `scope_cycles` 的受控事务操作。
- **Route_Coverage_Ledger（路由覆盖台账）**：固定记录每个具体 route 与 HTTP method、动作类别、资源解析方式、Wp_Bound_Gate 接入点、Action_Matrix 条目和测试证据的清单。
- **Route_Drift_Guard（路由漂移守卫）**：在 CI 中通过服务端生产路由抽象语法树检查新增或变更的 wp-bound route 是否已登记并接入统一门的守卫。
- **Token_Binding_Claims（令牌绑定声明）**：OnlyOffice/WOPI JWT 中与 URL 请求绑定且值均非空的 `wp_id`、`sheet_name`、`wp_code`、`version` 和 `action` 声明。
- **JWT_Lifetime（JWT 时效）**：由安全配置定义的有限正值；具体值在验收开始前冻结并写入 Evidence_Manifest。
- **Visibility_Mode（可见性模式）**：前端用于选择“我的委派底稿”等展示方式的 UX 参数，不参与服务端安全判定。
- **My_Procedure_Tasks（我的程序任务）**：仅查询当前用户作为 Row_Assignee 或 Operation_Reviewer 的 `ProcedureRowTask` 列表。
- **My_Lead_Workpapers（我的主编底稿）**：独立查询当前用户作为 Workpaper_Lead 的底稿区块或列表。
- **Pagination_Contract（分页契约）**：列表请求使用 `page`、`page_size` 和 `sort`；响应使用且仅使用顶层字段 `{items,total,stats,page,page_size}`。
- **stats（过滤后统计）**：Pagination_Contract 中基于可见性与业务筛选后、按 `wp_index_id` 去重且分页前的完整集合计算的 `{by_index_status,by_file_status}` 计数对象。
- **Stable_Sort（稳定排序）**：对请求排序字段采用明确空值顺序，并追加唯一 `wp_index_id` 升序作为最终排序键。
- **index_status（索引状态）**：`wp_index_id` 对应目录或适用性层面的状态。
- **file_status（文件状态）**：具体 WorkingPaper Current_Version 的文件或编制工作流状态。
- **Entry_Family（入口族）**：Requirement 8.5 至 Requirement 8.16 定义的完整入口分类，包括列表、详情、render-config、HTML、checklist、文件、下载、预览、导入、导出、附件、OnlyOffice/WOPI 配置、读取、保存、回调、转换、复核、批注、状态、AI、procedure 任务、版本、历史、快照、跨底稿引用、批量与后台任务。
- **Evidence_Manifest（证据清单）**：固定路径 `.kiro/specs/procedure-delegation-visibility-isolation/evidence/manifest.json` 的验收证据索引。
- **Evidence_Schema（证据模式）**：固定路径 `.kiro/specs/procedure-delegation-visibility-isolation/evidence/manifest.schema.json` 的 JSON Schema。
- **Criterion_Run（验收运行）**：某一 requirement criterion 的一次有序执行记录；失败后重跑产生新的 Criterion_Run，不覆盖先前记录。
- **Completion_Guard（完成守卫）**：在任务完成前验证 Evidence_Manifest、Evidence_Schema、证据哈希和必做验收结果的自动门禁。
- **Smoke_Profile（本地冒烟配置）**：开发者本地快速运行的 PBT 配置，`max_examples=5`，不得作为完成证据。
- **Correctness_Profile（CI 正确性配置）**：CI 验证核心正确性属性的 PBT 配置，每条适用属性至少生成 100 个有效样例。
- **Performance_Profile（性能配置）**：以 6000 个并发已认证用户为目标负载，记录列表与单资源授权延迟、错误率、拒绝正确率、限流行为和缓存一致性的容量测试配置。
- **Rate_Limit_Profile（限流配置）**：由 Performance_Profile 容量测试结果确定并版本化保存的每用户、每项目和每入口族限流阈值集合。
- **Workpaper_List（底稿列表服务）**：按服务端可见性、状态、排序和分页契约返回底稿列表的服务。
- **Frontend（前端）**：向用户呈现底稿、委派、状态与拒绝结果的客户端界面，不构成安全边界。
- **PBT_Suite（属性测试套件）**：以生成式输入验证本 feature 核心不变量的测试集合。
- **integration suite（集成测试套件）**：以代表性示例验证数据库、路由、令牌和外部编辑协议边界的测试集合。
- **acceptance suite（验收测试套件）**：验证角色行为、入口覆盖、性能与证据完整性的发布验收集合。
- **Implementation_Plan（实施计划）**：本 requirements-first feature 后续任务阶段生成的 `tasks.md`。
- **Specification_Governance（规格治理门禁）**：依据必做任务、CI 和 Completion_Guard 判定 feature 是否允许声明完成的治理能力。

## Requirements

### Requirement 1: 唯一角色分类与非管理员 scope 上界

**User Story:** 作为安全负责人，我希望所有服务端入口使用同一角色分类和 scope 上界，以便角色异常时系统保持 fail-closed。

#### Acceptance Criteria

1. THE Visibility_System SHALL 在每个服务端入口为当前用户输出且仅输出 Admin_User、Supervisor 或 Restricted_User 中的一个分类。
2. THE Visibility_System SHALL 将 system `admin` 判定为 Admin_User。
3. WHEN Non_Admin_User 在当前项目具有唯一 active staff↔user 映射、唯一 active 项目成员链路且角色为 `partner`、`signing_partner`、`manager`、`qc` 或 `eqcr`，THE Visibility_System SHALL 将 Non_Admin_User 判定为 Supervisor。
4. WHEN Non_Admin_User 不满足 Requirement 1.3，THE Visibility_System SHALL 将 Non_Admin_User 判定为 Restricted_User。
5. IF 用户角色未知、角色未登记、active staff↔user 映射数量不为一、active 项目成员链路数量不为一或角色查询失败，THEN THE Visibility_System SHALL 将用户判定为 Restricted_User。
6. THE Visibility_System SHALL 对所有 Non_Admin_User 使用 `scope_cycles` 作为底稿可见性的粗粒度上界。
7. THE Visibility_System SHALL 对每个 Non_Admin_User 强制应用 `scope_cycles` 上界。
8. WHEN Admin_User 请求当前项目的 Wp_Bound_Resource，THE Visibility_System SHALL 在可见范围计算中忽略 `scope_cycles` 约束并继续应用 Admin_User 的 Action_Matrix。
9. IF Non_Admin_User 的 `scope_cycles` 缺失，THEN THE Visibility_System SHALL 将 Non_Admin_User 的 `scope_cycles` 解释为空集合。
10. IF Non_Admin_User 的 `scope_cycles` 查询失败，THEN THE Visibility_System SHALL 将 Non_Admin_User 的 `scope_cycles` 解释为空集合。
11. WHEN 用户输入同时满足多个分类候选条件，THE Visibility_System SHALL 依据 Requirement 1.2 至 Requirement 1.5 的顺序产生唯一分类结果。

### Requirement 2: 两层委派语义与权威字段

**User Story:** 作为项目负责人，我希望底稿主编与程序行执行/复核分层但联动，以便职责清晰且不会产生孤儿委派。

#### Acceptance Criteria

1. THE Visibility_System SHALL 将 Workpaper_Lead 与 Row_Assignee/Operation_Reviewer 作为两个独立委派层。
2. THE Visibility_System SHALL 将保存 `users.id` 类型 `user_id` 的 `WorkingPaper.assigned_to` 作为 Workpaper_Lead 的唯一权威字段。
3. THE Visibility_System SHALL 将保存 `staff_members.id` 类型 `staff_id` 的 `ProcedureInstance.assigned_to` 仅作为 Workpaper_Lead 的 Staff_Projection。
4. WHEN Workpaper_Lead 委派成功提交，THE Delegation_Transaction SHALL 通过目标项目中唯一 active staff↔user 映射使 `WorkingPaper.assigned_to` 与 `ProcedureInstance.assigned_to` 表达同一自然人。
5. WHEN Delegation_Transaction 校验 Requirement 2.4，THE Delegation_Transaction SHALL 使用 staff↔user 映射关系作为唯一同人判定依据。
6. IF Delegation_Transaction 使用 `WorkingPaper.assigned_to` 与 `ProcedureInstance.assigned_to` 的字段值直接相等作为同人判定，THEN THE Delegation_Transaction SHALL 拒绝提交。
7. THE Visibility_System SHALL 将 `ProcedureRowTask.assignee_staff_id` 作为 Row_Assignee 的权威字段。
8. THE Visibility_System SHALL 将 `ProcedureRowTask.reviewer_staff_id` 作为 Operation_Reviewer 的权威字段。
9. THE ProcedureRowTask SHALL 仅以 `assignee_staff_id` 与 `reviewer_staff_id` 表达程序行人员角色。
10. THE Visibility_System SHALL 将 Staff_Projection 限定为 Workpaper_Lead 的 `ProcedureInstance.assigned_to`。
11. WHEN 任一委派层缺少委派值，THE Visibility_System SHALL 保持另一委派层的现有值不变。
12. WHEN 任一委派层发生变更，THE Visibility_System SHALL 保持另一委派层的现有值不变。
13. WHEN 程序行层委派发生变更，THE Delegation_Transaction SHALL 保留 Workpaper_Lead 与 `ProcedureInstance.assigned_to` 不变。
14. WHEN Workpaper_Lead 委派发生变更，THE Delegation_Transaction SHALL 保留全部 ProcedureRowTask 的 Row_Assignee 与 Operation_Reviewer 不变。
15. IF `WorkingPaper.assigned_to` 或 `ProcedureInstance.assigned_to` 的更新失败，THEN THE Delegation_Transaction SHALL 回滚全部 Workpaper_Lead 事务内变更。

### Requirement 3: staff_id 与 user_id 映射事务不变量

**User Story:** 作为平台维护者，我希望委派写入只接受唯一、有效且同项目的人员映射，以便权威字段与投影不会分歧。

#### Acceptance Criteria

1. WHEN Delegation_Transaction 接收非空 `staff_id`，THE Delegation_Transaction SHALL 要求目标项目内恰有一个匹配的 StaffMember。
2. WHEN Delegation_Transaction 解析目标项目内的 StaffMember，THE Delegation_Transaction SHALL 要求 StaffMember 为 active。
3. WHEN Delegation_Transaction 解析目标项目内的 active StaffMember，THE Delegation_Transaction SHALL 要求 `StaffMember.user_id` 非空。
4. WHEN Delegation_Transaction 解析非空 `staff_id`，THE Delegation_Transaction SHALL 要求对应 `user_id` 在目标项目唯一映射到该 active StaffMember。
5. IF Requirement 3.1 至 Requirement 3.4 中任一映射条件不成立，THEN THE Delegation_Transaction SHALL 拒绝委派并回滚全部事务内变更。
6. IF `staff_id` 仅能在目标项目之外解析到 active StaffMember，THEN THE Delegation_Transaction SHALL 拒绝跨项目委派并回滚全部事务内变更。
7. WHEN Delegation_Transaction 接收清空请求，THE Delegation_Transaction SHALL 要求请求明确指定 Workpaper_Lead、Row_Assignee 或 Operation_Reviewer 目标层。
8. WHEN Delegation_Transaction 接收程序行层清空请求，THE Delegation_Transaction SHALL 要求请求明确指定目标 ProcedureRowTask。
9. WHEN Delegation_Transaction 清空 Workpaper_Lead，THE Delegation_Transaction SHALL 在同一事务中清空 `WorkingPaper.assigned_to` 与 Staff_Projection。
10. WHEN Delegation_Transaction 清空 Row_Assignee，THE Delegation_Transaction SHALL 清空目标 ProcedureRowTask 的 `assignee_staff_id`。
11. WHEN Delegation_Transaction 清空 Operation_Reviewer，THE Delegation_Transaction SHALL 清空目标 ProcedureRowTask 的 `reviewer_staff_id`。
12. WHEN Delegation_Transaction 清空程序行角色，THE Delegation_Transaction SHALL 保留另一程序行角色、Workpaper_Lead 与 Staff_Projection 不变。
13. WHEN Delegation_Transaction 写入、转派或清空委派，THE Delegation_Transaction SHALL 在同一事务中记录 actor、project、wp_index_id、目标层、目标 ProcedureRowTask、旧 `staff_id`、新 `staff_id`、旧 `user_id`、新 `user_id` 和时间。
14. IF 任一委派字段、Staff_Projection、历史、scope 或审计记录写入失败，THEN THE Delegation_Transaction SHALL 逐字段回滚全部事务内变更。
15. THE Delegation_Transaction SHALL 拒绝以 Row_Assignee 或 Operation_Reviewer 的 `staff_id` 更新 Staff_Projection。

### Requirement 4: 标准与自定义 procedure 的 wp_index 统一解析

**User Story:** 作为程序委派人，我希望标准与自定义程序都唯一落到同一底稿索引，以便可见性计算没有歧义。

#### Acceptance Criteria

1. WHEN 标准 procedure 参与委派、查询或授权，THE Procedure_Wp_Resolver SHALL 在目标项目内解析标准 procedure 的唯一 `wp_index_id`。
2. WHEN 自定义 procedure 参与委派、查询或授权，THE Procedure_Wp_Resolver SHALL 在目标项目内解析自定义 procedure 的唯一 `wp_index_id`。
3. WHEN Procedure_Wp_Resolver 解析 procedure，THE Procedure_Wp_Resolver SHALL 将 project、procedure、`wp_code`、既有 `wp_index_id` 绑定和全部已提供绑定来源作为联合解析上下文。
4. WHEN procedure 提供 `sheet_name`，THE Procedure_Wp_Resolver SHALL 仅在 Requirement 4.3 的联合解析上下文内解释 `sheet_name`。
5. IF procedure 仅以 `sheet_name` 产生全局唯一候选，THEN THE Procedure_Wp_Resolver SHALL 拒绝该候选。
6. WHEN procedure 提供多个绑定来源，THE Procedure_Wp_Resolver SHALL 对每个来源分别产生唯一 `wp_index_id` 并要求全部结果一致。
7. THE Visibility_System SHALL 仅使用 Procedure_Wp_Resolver 的唯一一致 `wp_index_id` 结果计算底稿可见性。
8. IF 任一已提供绑定来源得到零个候选 `wp_index_id`，THEN THE Procedure_Wp_Resolver SHALL fail-closed 拒绝解析。
9. IF 任一已提供绑定来源得到多个候选 `wp_index_id`，THEN THE Procedure_Wp_Resolver SHALL fail-closed 拒绝解析。
10. IF procedure 的已提供绑定来源解析到不同 `wp_index_id`，THEN THE Procedure_Wp_Resolver SHALL fail-closed 拒绝解析。
11. WHEN Procedure_Wp_Resolver 拒绝解析，THE Visibility_System SHALL 拒绝委派、可见性扩展、底稿读取和底稿写入。
12. WHEN Procedure_Wp_Resolver 拒绝解析，THE Visibility_System SHALL 保持 procedure、底稿、委派、历史和 scope 数据不变。
13. WHEN Procedure_Wp_Resolver 拒绝解析，THE Security_Audit_Outbox SHALL 可靠记录 `binding_conflict` 及全部已提供绑定标识符。
14. IF Security_Audit_Outbox 写入或投递失败，THEN THE Visibility_System SHALL 保持请求拒绝并产生 Operational_Alert。

### Requirement 5: 固定可见集公式、页面隔离与历史当前版本只读

**User Story:** 作为受限用户，我希望可见范围严格等于委派、历史、scope 和页面映射的集合规则，以便任何单一来源无法扩大权限。

#### Acceptance Criteria

1. THE Visibility_System SHALL 按 `wp_index_id` 计算 Delegated_Set。
2. THE Visibility_System SHALL 按 `wp_index_id` 计算 History_Set。
3. WHEN Visibility_System 计算 Restricted_User 的可见集，THE Visibility_System SHALL 使用 `(Delegated_Set ∪ History_Set) ∩ scope_cycles` 作为唯一底稿范围公式。
4. WHEN Visibility_System 合并 Delegated_Set 与 History_Set，THE Visibility_System SHALL 按 `wp_index_id` 去重。
5. WHEN Admin_User 请求当前项目的 Wp_Bound_Resource，THE Visibility_System SHALL 按 Admin_User 的 Action_Matrix 完整允许项判定访问。
6. WHEN Supervisor 请求 `scope_cycles` 内的 Wp_Bound_Resource，THE Visibility_System SHALL 按 Supervisor 的 Action_Matrix 完整允许项判定访问。
7. WHEN Restricted_User 请求 Delegated_Set 内的 Wp_Bound_Resource，THE Visibility_System SHALL 按 Restricted_User 的 Action_Matrix 完整允许项判定访问。
8. WHEN Row_Assignee 或 Operation_Reviewer 仅凭程序行层身份请求 Wp_Bound_Resource，THE Visibility_System SHALL 将 Page_Visibility_Set 限定为对应 ProcedureRowTask 映射的 Sheet_Key 集合。
9. WHEN Row_Assignee 或 Operation_Reviewer 仅凭程序行层身份请求某一 `wp_index_id` 的未映射 Sheet_Key，THE Visibility_System SHALL 返回 External_Not_Found。
10. WHEN Workpaper_Lead 请求 Workpaper_Lead 对应 `wp_index_id` 的页面，THE Visibility_System SHALL 按 Workpaper_Lead 的 Action_Matrix 完整允许项判定整张底稿的 Sheet_Key 访问。
11. WHEN 用户同时具有 Workpaper_Lead 与程序行层身份，THE Visibility_System SHALL 依据各身份独立命中的 Action_Matrix 完整允许项合并 Page_Visibility_Set。
12. WHEN Restricted_User 仅因 History_Set 获得某一 `wp_index_id` 的可见性，THE Visibility_System SHALL 仅允许读取该 `wp_index_id` 的 Current_Version。
13. IF History_Only_Read_Set 中的用户请求历史版本，THEN THE Visibility_System SHALL 返回 External_Not_Found。
14. IF History_Only_Read_Set 中的用户请求任一写动作，THEN THE Visibility_System SHALL 返回 External_Not_Found。
15. WHEN Visibility_System 解析某一 Wp_Bound_Resource，THE Visibility_System SHALL 为每个独立身份产出且仅产出一个已登记 `access_kind` 的 Access_Grant。
16. IF 任一 Access_Grant 未产出已登记 `access_kind`，THEN THE Visibility_System SHALL 丢弃该 Access_Grant 并在没有其他完整允许项时将该 Wp_Bound_Resource 判定为不可访问。
17. WHEN History_Only_Read_Set 中的 Workpaper_Lead 历史参与者读取 Current_Version，THE Visibility_System SHALL 将 Page_Visibility_Set 限定为该底稿全部当前页面。
18. WHEN History_Only_Read_Set 中的 Row_Assignee 或 Operation_Reviewer 历史参与者读取 Current_Version，THE Visibility_System SHALL 将 Page_Visibility_Set 限定为不可变委派历史快照记录的 Sheet_Key。

### Requirement 6: 跨循环 scope 扩权事务

**User Story:** 作为项目委派人，我希望跨循环委派通过显式 scope 扩权完成，以便 scope 变化可追溯且不会被委派隐式扩大。

#### Acceptance Criteria

1. IF 目标 `wp_index_id` 不属于被委派人的 `scope_cycles`，THEN THE Visibility_System SHALL 拒绝未包含 Scope_Expansion 的委派请求。
2. WHEN 具有既有项目委派权限的授权人发起跨循环委派，THE Visibility_System SHALL 要求授权人显式选择 Scope_Expansion。
3. WHEN 授权人选择 Scope_Expansion，THE Visibility_System SHALL 要求非空扩权理由。
4. WHEN Scope_Expansion 成功提交，THE Delegation_Transaction SHALL 在同一事务中写入原 `scope_cycles` 与目标循环的并集。
5. WHEN Scope_Expansion 成功提交，THE Delegation_Transaction SHALL 在同一事务中写入委派。
6. WHEN Scope_Expansion 成功提交，THE Delegation_Transaction SHALL 在同一事务中写入包含授权人、被委派人、目标循环、理由、旧 scope 和新 scope 的审计记录。
7. IF scope 并集、委派或审计中的任一步骤失败，THEN THE Delegation_Transaction SHALL 回滚全部 Scope_Expansion 事务内变更。
8. WHEN 委派被撤销，THE Visibility_System SHALL 保持 `scope_cycles` 不变。

### Requirement 7: 完整动作矩阵与多身份合并

**User Story:** 作为安全负责人，我希望动作授权只能命中完整矩阵条目，以便用户无法通过模糊 route 或多身份拼接获得权限。

#### Acceptance Criteria

1. THE Action_Matrix SHALL 将用户分类、参与身份、精确 route、HTTP method、action、source state 和 target state 作为一个完整允许项的共同匹配维度。
2. WHEN 请求的全部维度匹配同一个完整允许项，THE Visibility_System SHALL 允许该允许项定义的动作。
3. IF 请求任一维度未匹配同一个完整允许项，THEN THE Visibility_System SHALL 拒绝该动作。
4. THE Visibility_System SHALL 将未登记动作、未登记 route、未登记 method 和未登记状态迁移默认判定为拒绝。
5. WHEN Operation_Reviewer 发起复核动作，THE Visibility_System SHALL 要求请求同时命中 Action_Matrix 完整允许项与 Review_Whitelist 完整允许项。
6. WHEN 用户同时具有多个参与身份，THE Visibility_System SHALL 仅合并各身份独立命中的完整允许项。
7. IF 请求需要从不同身份分别取得允许项的部分维度，THEN THE Visibility_System SHALL 拒绝跨身份拼接。
8. WHEN action 不包含状态迁移，THE Action_Matrix SHALL 使用已登记的无迁移 source state 与 target state 值完成匹配。
9. WHEN 同一 Wp_Bound_Resource 产生多个 Access_Grant，THE Visibility_System SHALL 逐个使用该 Access_Grant 自身的 `access_kind`、页面范围与动作范围匹配完整 Action_Matrix 条目。
10. WHEN 多个 Access_Grant 分别命中完整允许项，THE Visibility_System SHALL 仅并集合并这些完整允许项的页面与动作结果。

### Requirement 8: 全入口前置统一门与最小绑定解析

**User Story:** 作为安全负责人，我希望所有底稿绑定入口在读取敏感数据或产生副作用前经过统一门，以便不存在旁路入口。

#### Acceptance Criteria

1. WHEN 服务端入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 在读取敏感元数据、业务内容或产生副作用之前完成授权判定。
2. WHILE Wp_Bound_Gate 尚未完成授权判定，THE Visibility_System SHALL 仅读取 Binding_Minimum 所需的最少关系。
3. WHEN Wp_Bound_Gate 判定页面级资源，THE Wp_Bound_Gate SHALL 校验服务端解析的 `wp_index_id` 与 Sheet_Key 均属于当前请求的允许范围。
4. IF 客户端提供的附件、页面、版本或编辑器绑定与服务端解析绑定不一致，THEN THE Wp_Bound_Gate SHALL 拒绝请求。
5. WHEN 底稿列表、详情、render-config、HTML 渲染或 checklist 入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
6. WHEN 文件内容、下载、预览、导入、导出或转换入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
7. WHEN 附件上传、读取、下载或删除入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
8. WHEN 编辑器配置、文件读取、保存、回调或转换入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
9. WHEN OnlyOffice 或 WOPI 配置、读取、保存、回调或转换入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
10. WHEN 复核、批注、结论或状态迁移入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
11. WHEN AI 上下文、生成、总结或推理入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
12. WHEN procedure 委派、任务查询或任务动作入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
13. WHEN 单项入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该资源执行独立 gate 判定。
14. WHEN 批量、导入、导出或嵌套资源入口处理一个或多个 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对每个资源执行独立 gate 判定。
15. WHEN 版本、历史、快照或跨底稿引用入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对该入口执行独立 gate 判定。
16. WHEN 回调、后台任务或延迟任务处理一个或多个 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 对每个资源重新执行 gate 判定。
17. WHEN 任一 Entry_Family 新增或变更入口，THE Visibility_System SHALL 要求该入口在提供服务前接入 Wp_Bound_Gate 与 Action_Matrix。
18. WHEN 任一服务端入口处理 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 统一调用 `resolve_wp_binding_and_access()`。
19. WHEN `resolve_wp_binding_and_access()` 处理 Wp_Bound_Resource，THE Wp_Binding_Access_Resolver SHALL 先解析 Binding_Minimum，再返回 `binding`、`role`、查询层明确产出的 `access_kind`、`allowed_sheet_keys` 与 `current_version`。

### Requirement 9: 外部不可枚举拒绝与内部真实审计

**User Story:** 作为安全负责人，我希望不存在、跨项目、越权和历史版本拒绝的外部表现完全一致，同时内部保留真实原因，以便阻止资源枚举并支持调查。

#### Acceptance Criteria

1. IF Wp_Bound_Resource 不存在，THEN THE Visibility_System SHALL 返回 External_Not_Found。
2. IF Wp_Bound_Resource 属于其他项目，THEN THE Visibility_System SHALL 返回 External_Not_Found。
3. IF 当前用户无权访问 Wp_Bound_Resource，THEN THE Visibility_System SHALL 返回 External_Not_Found。
4. IF 当前用户请求无权访问的 Sheet_Key，THEN THE Visibility_System SHALL 返回 External_Not_Found。
5. IF 当前用户请求无权访问的历史版本，THEN THE Visibility_System SHALL 返回 External_Not_Found。
6. WHEN Visibility_System 返回 External_Not_Found，THE Visibility_System SHALL 返回 HTTP 404。
7. WHEN Visibility_System 返回 External_Not_Found，THE Visibility_System SHALL 返回且仅返回 `{"detail":"资源不存在或不可访问"}`。
8. WHEN Visibility_System 拒绝一次请求，THE Security_Audit_Outbox SHALL 可靠记录该次拒绝的真实内部原因。
9. WHEN Security_Audit_Outbox 记录真实内部原因，THE Security_Audit SHALL 使用 `not_found`、`cross_project`、`out_of_scope`、`not_delegated`、`sheet_unmapped`、`action_denied`、`historical_version`、`binding_conflict`、`token_invalid` 或 `rate_limited` 中与事实一致的值。
10. IF Security_Audit_Outbox 写入失败，THEN THE Visibility_System SHALL 保持 External_Not_Found 或不依赖资源存在性的限流响应之状态码与响应体不变并产生 Operational_Alert。
11. IF Security_Audit_Outbox 投递 Security_Audit 失败，THEN THE Visibility_System SHALL 保持 External_Not_Found 或不依赖资源存在性的限流响应之状态码与响应体不变并产生 Operational_Alert。

### Requirement 10: OnlyOffice/WOPI 令牌绑定与回调重校验

**User Story:** 作为平台维护者，我希望编辑令牌与具体底稿、版本和动作严格绑定，以便令牌不能跨资源或跨动作复用。

#### Acceptance Criteria

1. WHEN Visibility_System 接收 OnlyOffice 或 WOPI 请求，THE Visibility_System SHALL 要求 Token_Binding_Claims 完整且每个 claim 非空。
2. WHEN Visibility_System 接收 OnlyOffice 或 WOPI 请求，THE Visibility_System SHALL 要求令牌签名校验通过。
3. WHEN Visibility_System 接收 OnlyOffice 或 WOPI 请求，THE Visibility_System SHALL 要求令牌过期校验通过。
4. WHEN Token_Binding_Claims 通过格式、签名和过期校验，THE Visibility_System SHALL 将每个 claim 逐一绑定到 URL 参数与服务端解析资源。
5. IF 任一 claim 与 URL 参数或服务端解析资源不一致，THEN THE Visibility_System SHALL 拒绝请求并记录 `token_invalid`。
6. WHEN callback 准备写入 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 重新校验 Current_Version。
7. WHEN callback 准备写入 Wp_Bound_Resource，THE Wp_Bound_Gate SHALL 重新校验 Action_Matrix 与 claim 中的 `action`。
8. IF 只读令牌请求写动作，THEN THE Wp_Bound_Gate SHALL 拒绝写入。
9. IF 令牌 secret 或安全配置缺失，THEN THE Visibility_System SHALL fail-closed 拒绝请求。
10. THE Visibility_System SHALL 从验收前冻结的安全配置读取有限正值 JWT_Lifetime。
11. WHEN JWT_Lifetime 配置被用于验收，THE Evidence_Manifest SHALL 记录配置标识和值。

### Requirement 11: 过滤后分页、稳定排序与独立任务视图

**User Story:** 作为底稿使用者，我希望分页、统计和任务视图都基于同一可见集合，以便列表不会泄露或漏算数据。

#### Acceptance Criteria

1. WHEN Workpaper_List 处理列表请求，THE Workpaper_List SHALL 先应用可见性过滤与业务过滤。
2. WHEN Workpaper_List 完成过滤，THE Workpaper_List SHALL 在排序、分页、total 和 stats 计算前按 `wp_index_id` 去重。
3. WHEN Workpaper_List 计算 total，THE Workpaper_List SHALL 使用过滤且去重后的完整集合。
4. WHEN Workpaper_List 计算 stats，THE Workpaper_List SHALL 使用过滤且去重后的分页前完整集合。
5. WHEN 过滤且去重后的完整集合为空，THE Workpaper_List SHALL 返回 `stats={"by_index_status":{},"by_file_status":{}}`。
6. WHEN Workpaper_List 返回分页结果，THE Workpaper_List SHALL 使用且仅使用顶层字段 `{items,total,stats,page,page_size}`。
7. IF `page` 不是正整数、`page_size` 不是配置范围内的正整数或 `sort` 未登记，THEN THE Workpaper_List SHALL 在执行底稿数据查询前返回 HTTP 422。
8. WHEN Workpaper_List 对请求排序字段排序，THE Workpaper_List SHALL 对该字段使用 nulls-last。
9. WHEN Workpaper_List 对结果应用 Stable_Sort，THE Workpaper_List SHALL 追加 `wp_index_id` 升序作为最终排序键。
10. WHEN My_Procedure_Tasks 返回任务，THE My_Procedure_Tasks SHALL 仅包含当前用户作为 Row_Assignee 或 Operation_Reviewer 的 ProcedureRowTask。
11. THE My_Procedure_Tasks SHALL 不合成 Workpaper_Lead 项目。
12. WHEN My_Lead_Workpapers 返回底稿，THE My_Lead_Workpapers SHALL 仅包含当前用户作为 Workpaper_Lead 的底稿。
13. THE My_Lead_Workpapers SHALL 复用 Pagination_Contract、过滤顺序、去重规则、Stable_Sort 和 stats 契约。

### Requirement 12: 展示模式、状态字段与前端拒绝行为

**User Story:** 作为前端使用者，我希望展示参数与授权解耦且状态字段明确，以便界面行为可预测而不改变服务端权限。

#### Acceptance Criteria

1. WHEN 客户端提供 Visibility_Mode，THE Visibility_System SHALL 使用相同用户分类、scope、可见集公式、Wp_Bound_Gate 和 Action_Matrix 判定授权。
2. THE Visibility_System SHALL 使 Visibility_Mode 对授权既不放宽也不收紧。
3. WHEN 客户端提供用户身份、角色或参与身份字段，THE Visibility_System SHALL 忽略客户端字段并使用服务端权威身份。
4. WHEN Workpaper_List 返回状态，THE Workpaper_List SHALL 分别返回 `index_status` 与 `file_status`。
5. THE Workpaper_List SHALL 使用 `index_status` 与 `file_status` 替代含义不明确的 `status`。
6. WHEN 状态字段迁移发生，THE Visibility_System SHALL 明确记录每个 legacy source 字段及对应的 `index_status` 或 `file_status` target 字段。
7. WHEN Frontend 收到 External_Not_Found，THE Frontend SHALL 显示“资源不存在或不可访问”且不显示内部拒绝原因。
8. WHEN Frontend 收到授权范围内的 nullable `wp_id`，THE Frontend SHALL 显示“底稿尚未生成”状态。
9. WHILE `wp_id` 为空，THE Frontend SHALL 禁用依赖具体 Wp_Bound_Resource 的读取与写入动作。
10. THE Frontend SHALL 为 Requirement 12.7 至 Requirement 12.9 提供可重复执行的行为验证。

### Requirement 13: 路由覆盖台账与 CI 漂移阻断

**User Story:** 作为平台维护者，我希望生产路由与授权台账由 CI 持续核对，以便新增入口不会绕过统一门。

#### Acceptance Criteria

1. THE Route_Coverage_Ledger SHALL 为每个具体 route 与 HTTP method 登记唯一记录。
2. THE Route_Coverage_Ledger SHALL 为每条记录填写动作类别、资源解析方式、Wp_Bound_Gate 接入点、Action_Matrix 完整条目和测试证据。
3. WHEN Route_Drift_Guard 扫描服务端生产路由，THE Route_Drift_Guard SHALL 解析路由抽象语法树。
4. WHEN Route_Drift_Guard 比较生产路由与 Route_Coverage_Ledger，THE Route_Drift_Guard SHALL 规范化 decorator、registry 注册形式和 path 参数名称。
5. IF 生产 route 与 method 未登记，THEN THE Route_Drift_Guard SHALL 阻断 CI。
6. IF 已登记生产 route 未接入 Wp_Bound_Gate，THEN THE Route_Drift_Guard SHALL 阻断 CI。
7. IF 已登记生产 route 缺少 Action_Matrix 完整条目，THEN THE Route_Drift_Guard SHALL 阻断 CI。
8. IF Route_Coverage_Ledger 存在 stale 记录或重复 route+method 记录，THEN THE Route_Drift_Guard SHALL 阻断 CI。
9. IF 动态路由无法静态解析且 Route_Coverage_Ledger 未登记显式动态路由清单，THEN THE Route_Drift_Guard SHALL 阻断 CI。
10. WHEN Route_Coverage_Ledger 登记测试证据，THE Route_Coverage_Ledger SHALL 指向本次 CI 运行中通过的测试结果。
11. IF 台账测试证据未指向本次 CI 运行，THEN THE Route_Drift_Guard SHALL 阻断 CI。
12. THE Route_Coverage_Ledger SHALL 逐 Entry_Family 登记 Requirement 8.5 至 Requirement 8.16 覆盖的全部具体 route 与 HTTP method。
13. WHEN Entry_Family 包含 callback、background、retry 或 dead-letter 执行器，THE Route_Coverage_Ledger SHALL 以 `kind`、稳定 `entrypoint` 和 callable 登记非 HTTP 执行入口。
14. IF 新增或变更的 callback、background、retry 或 dead-letter callable 未登记或未在执行时重新调用 Wp_Bound_Gate，THEN THE Route_Drift_Guard SHALL 阻断 CI。
15. WHEN Route_Coverage_Ledger 登记稳定 test id，THE Evidence_Manifest SHALL 将该 test id 绑定到本次 CI 运行和证据 artifact。

### Requirement 14: 6000 并发性能、配置化限流与缓存收敛

**User Story:** 作为平台运营者，我希望可见性隔离在目标并发下保持可用且 fail-closed，以便高负载不会转化为越权。

#### Acceptance Criteria

1. THE Performance_Profile SHALL 以 6000 个并发已认证用户为目标负载。
2. WHEN Performance_Profile 执行底稿列表场景，THE Visibility_System SHALL 使服务端列表延迟 p95 不超过 2 秒。
3. WHEN Performance_Profile 执行单资源 gate 场景，THE Wp_Bound_Gate SHALL 使服务端授权延迟 p95 不超过 1 秒。
4. WHEN Performance_Profile 执行预期成功请求，THE Visibility_System SHALL 使服务端错误率不超过 1%。
5. WHEN Performance_Profile 执行越权请求，THE Visibility_System SHALL 使错误允许数等于 0。
6. WHEN Performance_Profile 完成 6000 并发容量测试，THE Performance_Profile SHALL 依据测量结果确定每用户、每项目和每 Entry_Family 的 Rate_Limit_Profile 阈值。
7. THE Rate_Limit_Profile SHALL 使用可版本化配置保存每用户、每项目和每 Entry_Family 的限流阈值。
8. THE Visibility_System SHALL 仅从 Rate_Limit_Profile 读取每用户、每项目和每 Entry_Family 的限流阈值。
9. THE Rate_Limit_Profile SHALL 以 6000 并发容量测试结果替代固定每用户、每项目或每 Entry_Family 10 RPS 基线。
10. WHEN 请求超过 Rate_Limit_Profile 阈值，THE Visibility_System SHALL 返回 HTTP 429。
11. WHEN 请求处于全部 Rate_Limit_Profile 阈值内，THE Visibility_System SHALL 继续执行正常 route 判定且不返回限流响应。
12. WHEN Visibility_System 返回 HTTP 429，THE Visibility_System SHALL 返回有效 `Retry-After`。
13. WHEN 权限、委派、scope 或角色变更事务提交，THE Visibility_System SHALL 在 1 秒内使权限缓存反映提交后的授权结果。
14. WHEN 委派或权限被撤销，THE Visibility_System SHALL 在 1 秒内使权限缓存拒绝已撤销访问。
15. IF 权限缓存缺失、过期或传播失败，THEN THE Visibility_System SHALL fail-closed 重新取得权威授权结果或拒绝请求。
16. THE Performance_Profile SHALL 以可版本化配置固定 ramp、项目分布、请求速率、数据规模、动作组合和负载持续方式。
17. WHEN Performance_Profile 产生验收证据，THE Evidence_Manifest SHALL 记录 Performance_Profile 版本、Rate_Limit_Profile 版本、配置摘要和测量结果。
18. WHEN 已认证请求超过 Rate_Limit_Profile 阈值，THE Visibility_System SHALL 在读取或判定目标 Wp_Bound_Resource 是否存在之前，仅依据 principal、project 和 Entry_Family 返回不依赖资源存在性的 HTTP 429。
19. WHEN 请求未被 Requirement 14.18 限流且进入 Wp_Bound_Gate，THE Visibility_System SHALL 对全部资源不可见原因应用 External_Not_Found。
20. WHEN 权限、委派、history、scope、角色或项目成员变更，THE Visibility_System SHALL 在同一数据库事务中持久递增 policy epoch 并写入 invalidation outbox。
21. WHEN invalidation outbox 提交后投递失败，THE Visibility_System SHALL 通过最多 1 秒的持久 policy epoch 校验发现 stale cache 并重新取得权威授权结果或拒绝请求。

### Requirement 15: 固定证据清单、追加记录与完成阻断

**User Story:** 作为验收负责人，我希望完成状态由可验证且防篡改的证据控制，以便失败记录不会被覆盖且伪造产物不能通过。

#### Acceptance Criteria

1. THE Evidence_Manifest SHALL 使用固定路径 `.kiro/specs/procedure-delegation-visibility-isolation/evidence/manifest.json`。
2. THE Evidence_Schema SHALL 使用固定路径 `.kiro/specs/procedure-delegation-visibility-isolation/evidence/manifest.schema.json`。
3. WHEN Criterion_Run 产生结果，THE Evidence_Manifest SHALL 追加新的有序记录。
4. WHEN 失败 Criterion_Run 被重跑，THE Evidence_Manifest SHALL 保留先前失败记录。
5. WHEN Evidence_Manifest 引用 artifact，THE Evidence_Manifest SHALL 使用 spec 目录内的相对路径。
6. IF artifact 相对路径包含 `..` 路径段，THEN THE Completion_Guard SHALL 拒绝该 artifact。
7. WHEN Completion_Guard 校验证据，THE Completion_Guard SHALL 对 artifact 原始字节重新计算 SHA-256。
8. WHEN Completion_Guard 校验证据，THE Completion_Guard SHALL 对 artifact 原始字节重新计算 size。
9. IF Evidence_Manifest、Evidence_Schema 或必需 artifact 缺失，THEN THE Completion_Guard SHALL 阻断 feature 完成。
10. IF Evidence_Manifest 不符合 Evidence_Schema，THEN THE Completion_Guard SHALL 阻断 feature 完成。
11. IF artifact 的重算 SHA-256 或 size 与 Evidence_Manifest 不一致，THEN THE Completion_Guard SHALL 阻断 feature 完成。
12. IF 任一必做 criterion 的最新 Criterion_Run 结果不为 `passed`，THEN THE Completion_Guard SHALL 阻断 feature 完成。

### Requirement 16: 同源属性测试、角色新上下文与叶子任务证据

**User Story:** 作为质量负责人，我希望冒烟与 CI 使用同一属性定义且每个必做任务有证据，以便快速反馈不会替代正确性验收。

#### Acceptance Criteria

1. THE Smoke_Profile SHALL 收集与 Correctness_Profile 相同的适用属性测试。
2. THE Smoke_Profile SHALL 对每条适用属性使用 `max_examples=5`。
3. THE Specification_Governance SHALL 将 Smoke_Profile 结果排除在 feature 完成证据之外。
4. THE Correctness_Profile SHALL 对每条适用属性生成至少 100 个有效样例。
5. THE PBT_Suite SHALL 验证 `(Delegated_Set ∪ History_Set) ∩ scope_cycles` 公式与按 `wp_index_id` 去重不变量。
6. THE PBT_Suite SHALL 验证过滤、去重、排序、分页、total 和 stats 的顺序不变量。
7. THE PBT_Suite SHALL 验证 `WorkingPaper.assigned_to` 的 `user_id` 与 `ProcedureInstance.assigned_to` 的 `staff_id` 通过唯一 active staff↔user 映射表达同一自然人的事务原子性。
8. THE PBT_Suite SHALL 验证 Row_Assignee 与 Operation_Reviewer 不产生额外 Staff_Projection。
9. THE PBT_Suite SHALL 验证清空 Row_Assignee 或 Operation_Reviewer 保留另一程序行角色、Workpaper_Lead 与 Staff_Projection 的不变量。
10. THE PBT_Suite SHALL 验证 Procedure_Wp_Resolver 的 `sheet_name` 联合上下文、零候选、多候选与来源冲突 fail-closed 属性。
11. THE PBT_Suite SHALL 验证 Action_Matrix 完整项匹配、多身份完整允许项并集与跨身份禁止拼接属性。
12. THE PBT_Suite SHALL 验证 Row_Assignee 与 Operation_Reviewer 的 Page_Visibility_Set 仅包含被委派程序行映射的 Sheet_Key。
13. THE PBT_Suite SHALL 验证 Workpaper_Lead 依据 Action_Matrix 访问整张底稿 Sheet_Key 的属性。
14. THE PBT_Suite SHALL 验证 Token_Binding_Claims 的完整性、非空性、URL 绑定、资源绑定与 action 绑定属性。
15. THE integration suite SHALL 验证不存在、跨项目、越权、未映射 Sheet_Key 与历史版本拒绝均返回完全相同的 External_Not_Found。
16. THE integration suite SHALL 验证 Security_Audit_Outbox 写入或投递失败时 External_Not_Found 不变且产生 Operational_Alert。
17. THE acceptance suite SHALL 验证所有 Entry_Family 的单项、批量、附件、编辑器回调、AI、版本和后台入口均经过 Wp_Bound_Gate。
18. THE acceptance suite SHALL 验证 Rate_Limit_Profile 阈值来自 6000 并发容量测试配置。
19. WHEN acceptance suite 验证任一角色，THE acceptance suite SHALL 为该角色创建新的浏览器 context 并从 fresh navigation 开始。
20. THE acceptance suite SHALL 分别验证 Admin_User、Supervisor、Workpaper_Lead、Row_Assignee、Operation_Reviewer 与 History_Only_Read_Set 用户的允许和拒绝行为。
21. THE Specification_Governance SHALL 将 Implementation_Plan 中每个叶子任务标记为必做。
22. WHEN 叶子任务完成，THE Evidence_Manifest SHALL 为该叶子任务记录本次运行的证据引用。
23. IF 任一叶子任务缺失通过证据，THEN THE Specification_Governance SHALL 立即阻断 feature 完成。
24. WHEN 每个叶子任务均存在证据且 Completion_Guard 的全部条件通过，THE Specification_Governance SHALL 无需额外人工批准即允许 feature 完成。