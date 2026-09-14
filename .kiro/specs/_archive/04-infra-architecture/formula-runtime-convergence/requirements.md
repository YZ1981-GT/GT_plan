# Requirements Document

## Introduction

`formula-runtime-convergence` 用于修复公式管理能力在真实运行期的闭环缺口。既有公式功能已经具备定义、地址解析、刷新治理、Draft 标记与界面组件，但代码核验表明，既有完成状态未能证明业务值真实写入、可逆回滚、可靠并发控制和真实角色验收。

本 Spec 收敛下列运行链路：

`公式定义 → 批量地址解析 → 批量真实取值 → 单一纯求值内核 → 领域写入 → 快照与治理元数据 → 事务提交 → 可靠失效通知 → 可逆回滚`

本 Requirements 文档是本阶段唯一交付物；本阶段不实现代码，不修改既有 design.md 或 tasks.md。后续 Design 和 Tasks 必须遵守本文的并行交付约束。

## Evidence Baseline

以下缺口已通过既有代码与测试实证，属于本 Spec 的必修范围：

1. 全局刷新在底稿和审定表范围可只生成 `RefreshUnit`、预设 Draft 单元或 Draft marker，未证明真实领域值写入。
2. rollback 可只恢复 marker 或返回快照内容，未在同一事务中恢复业务值与治理元数据。
3. `WpFormula` 保存定义时可写入 `last_computed_at`，导致保存与执行语义混淆。
4. `logic_check` #2、#5、#7 使用自比较或自适应容差，导致规则恒真。
5. `reference` 可在保存时复制源表达式，缺少执行期解引用或可靠固定版本语义。
6. ACNR resolve 结果未形成可证明的批量真实取值链。
7. 统一目标写入协议未完整覆盖 workpaper、adjudication、report、note。
8. 并发执行缺少完整 revision fingerprint、互斥写入和 CAS 保护。
9. all-or-nothing 与 partial-success 的事务边界不明确。
10. service 层项目 ownership 校验不足以独立阻止跨项目访问。
11. `GtRefreshScopeDialog` 未证明挂载生产宿主，前后端字段存在漂移风险。
12. 多个 evaluator 尚需收敛为单一纯内核与边界 adapter。
13. batch resolve/load 的 N+1 上界与运行 metrics 尚未形成验收契约。
14. PostgreSQL 与五角色 Playwright 测试存在 skip、同一 admin 复用或 catch 吞错导致的假绿风险。
15. 旧 Spec 的 100% 完成状态与上述缺口矛盾，需要证据化纠正。

## Non-goals

- 不新增审计循环、底稿类型或公式业务类型。
- 不扩展公式语法、函数白名单或运算符集合。
- 不重写 ACNR，也不建立平行地址注册中心。
- 不允许公式写入 `trial_balance` 之外的四表库叶子源；审定表仅可写 `audited_amount`。
- 不重做整个平台 UI；前端范围仅覆盖生产入口、契约一致性、结果与失败展示。
- 不以 mock-only、SQLite-only、默认跳过或吞错测试作为完成证据。
- 不因既有任务已标完成而推定本 Spec 的任何任务完成。

## Parallel Delivery Constraints

后续设计与任务计划必须支持多个子代理在同一 Wave 并行工作，并以文件所有权隔离冲突：

1. 每个实现任务必须声明 `dependsOn`、`ownerFiles`、`generatedFiles`、`forbiddenSharedFiles` 和独立验证命令。
2. 同一 Wave 内不同任务的 `ownerFiles ∪ generatedFiles` 交集必须为空。
3. `engine.py`、`draft_refresh_orchestrator.py`、`draft_refresh_service.py` 和刷新 router 等高冲突集成文件必须由后续串行集成任务独占。
4. Migration/ORM、四个领域 Adapter、生产宿主、OpenAPI 契约、PostgreSQL 验收和 Playwright 验收必须各有唯一文件 owner。
5. 共享接口必须由前置 contract 任务冻结；并行任务只能消费冻结接口，接口缺口由后续 integration 任务处理。
6. 独立任务通过不等于功能完成；只有串行集成、真实 PostgreSQL、真实五角色 Playwright 与完成治理全部通过后才允许更新完成状态。

## Glossary

- **Formula_Runtime**：本 Spec 定义的统一公式运行时，负责从执行请求到事务提交或回滚的完整闭环。
- **Global_Refresh**：按用户选定范围批量执行公式并更新真实领域数据的全局刷新操作。
- **Refresh_Orchestrator**：校验刷新范围、构造执行计划并协调 Formula_Runtime 的编排服务。
- **Formula_Definition_Service**：负责 `WpFormula` 保存、读取、删除和定义版本管理的 service 层服务。
- **Formula_Lifecycle_State_Machine**：管理公式状态转换的状态机；状态集合为 `saved`、`validated`、`executing`、`succeeded`、`failed`、`stale`、`rolled_back`。
- **Canonical_Formula_Target**：公式引用或目标的规范身份，包含 domain、project_id、year、addr_id 和领域 locator。
- **ACNR**：地址坐标名称注册中心；为引用和目标返回 canonical addr_id 与领域定位信息。
- **Formula_Value_Loader**：接收 ACNR 批量解析结果并从真实领域存储批量读取值的服务。
- **Evaluation_Kernel**：无数据库、网络、时钟或领域写入副作用的单一 Decimal 公式求值内核。
- **Evaluator_Adapter**：把旧调用方输入转换为 Evaluation_Kernel 输入并转换返回结果的薄边界层。
- **Domain_Mutation_Adapter**：统一领域变更协议，包含 `prepare_many`、`apply_many`、`restore_many` 和 `read_versions`。
- **Workpaper_Adapter**：向底稿真实数据存储写入公式结果的 Domain_Mutation_Adapter。
- **Adjudication_Adapter**：向 `trial_balance.audited_amount` 写入审定结果的 Domain_Mutation_Adapter。
- **Report_Adapter**：向报表真实数据存储写入公式结果的 Domain_Mutation_Adapter。
- **Note_Adapter**：向附注中允许自动回填的真实单元写入公式结果的 Domain_Mutation_Adapter。
- **Formula_Mutation**：包含 target、before_value、after_value、expected_version 和 applied_version 的单个领域变更。
- **Execution_Run**：一次 Global_Refresh、公式批执行或回滚的持久化运行批次。
- **Governance_Metadata**：与业务值关联的 Draft marker、公式生命周期状态、stale 状态、计算时间、版本和审计信息。
- **Rollback_Snapshot**：保存 Formula_Mutation 及 Governance_Metadata 前后状态的可恢复快照。
- **Transaction_Coordinator**：协调领域写入、快照、治理元数据、审计和 Outbox 原子提交的服务。
- **Outbox**：与业务写入同事务保存、提交后可靠发布 stale 和 invalidation 事件的事务消息记录。
- **Revision_Fingerprint**：由项目、年度、范围、源数据 revision、公式定义 hash、预设 revision、ACNR registry version 和事务模式构成的完整幂等指纹。
- **Concurrency_Guard**：通过数据库锁、唯一约束和 CAS 防止重复或丢失更新的并发控制组件。
- **CAS**：Compare-And-Swap；仅在当前版本等于 expected_version 时应用写入或恢复。
- **All_Or_Nothing**：任一执行分区失败时整批不提交的默认事务模式。
- **Partial_Success**：调用方显式选择后，以确定性执行分区和 savepoint 隔离失败的事务模式。
- **Execution_Partition**：Partial_Success 模式中的最小提交隔离单元，由 scope 与 domain 的稳定组合标识。
- **Ownership_Guard**：在 service 与 adapter 层校验实体属于请求 project_id 的安全组件。
- **Refresh_API**：提供刷新范围发现、执行、状态查询与回滚的后端 OpenAPI 接口集合。
- **Refresh_Scope_Dialog**：生产前端组件 `GtRefreshScopeDialog`，用于选择范围并展示执行结果。
- **Production_Host**：生产页面宿主 `ThreeColumnLayout.vue`。
- **Runtime_Metrics**：Formula_Runtime 输出的低基数计数器、直方图和批量规模指标。
- **Acceptance_Test_Suite**：使用真实 PostgreSQL 与真实浏览器验证运行闭环的验收测试集合。
- **Five_Role_Fixture**：分别代表审计助理、现场经理、业务合伙人、质量控制复核合伙人和 EQCR 技术复核人的五个独立测试身份。
- **Legacy_Formula_Spec**：旧 `formula-management-library` Spec 及其完成状态记录。
- **Evidence_Ledger**：逐条记录需求、实现路径、测试证据、未解决缺口和状态的治理清单。
- **Spec_Completion_Guard**：依据 Evidence_Ledger 和强验收结果决定 Spec 是否可标记完成的治理检查。
- **Implementation_Plan**：后续 design/tasks 形成的依赖图、Wave、文件所有权和验证计划。

## Requirements

### Requirement 1: 全局刷新真实领域写入

**User Story:** 作为审计人员，我希望全局刷新真实更新底稿、审定表、报表和附注，以便刷新结果可复核，而不是只有 `RefreshUnit` 或 Draft marker。

#### Acceptance Criteria

1. WHEN Global_Refresh 包含 workpaper 范围, THE Refresh_Orchestrator SHALL 通过 Workpaper_Adapter 写入底稿真实数据存储。
2. WHEN Global_Refresh 包含 adjudication 范围, THE Refresh_Orchestrator SHALL 通过 Adjudication_Adapter 写入对应科目的 `trial_balance.audited_amount`。
3. WHEN Global_Refresh 包含 report 或 note 范围, THE Refresh_Orchestrator SHALL 分别通过 Report_Adapter 或 Note_Adapter 写入对应真实领域存储。
4. WHEN Formula_Mutation 已由 Domain_Mutation_Adapter 成功提交, THE Formula_Runtime SHALL 将 Formula_Mutation 计入 `affected_count` 和 `applied_count`。
5. IF 执行单元仅生成 `RefreshUnit`、预设描述或 Draft marker 而未提交业务值, THEN THE Formula_Runtime SHALL 将执行单元记录为失败且保持 `affected_count` 与 `applied_count` 不变。
6. WHEN `logic_check` 或 `reasonability` 公式执行, THE Formula_Runtime SHALL 仅生成 Issue 或 Hint 结果并保持所有领域业务值不变。

### Requirement 2: 业务值与治理元数据同事务回滚

**User Story:** 作为业务合伙人，我希望回滚同时恢复真实业务值和治理元数据，以便错误刷新能够完整逆转且不会覆盖后续人工编辑。

#### Acceptance Criteria

1. WHEN Transaction_Coordinator 准备应用 Formula_Mutation, THE Transaction_Coordinator SHALL 在写入前保存业务值、业务版本和 Governance_Metadata 的 Rollback_Snapshot。
2. WHEN 用户回滚 Execution_Run, THE Transaction_Coordinator SHALL 在一个数据库事务中按写入逆序恢复业务值、Draft marker、生命周期状态、stale 状态、计算时间和版本元数据。
3. WHEN 回滚事务成功提交, THE Transaction_Coordinator SHALL 追加 `rolled_back` 审计记录并写入对应 Outbox 失效事件。
4. IF 任一目标当前版本不等于 Rollback_Snapshot 的 applied_version, THEN THE Concurrency_Guard SHALL 返回 HTTP 409 并保持全部业务值与 Governance_Metadata 不变。
5. IF 任一恢复步骤失败且事务模式为 All_Or_Nothing, THEN THE Transaction_Coordinator SHALL 回滚本次回滚事务并保持回滚前状态。
6. WHEN 同一 Execution_Run 被重复回滚, THE Transaction_Coordinator SHALL 返回首次成功回滚的幂等结果且不重复修改业务值。

### Requirement 3: WpFormula 保存与执行状态机

**User Story:** 作为复核人员，我希望公式保存与公式执行具有独立状态和时间语义，以便 `last_computed_at` 只证明真实成功计算。

#### Acceptance Criteria

1. WHEN Formula_Definition_Service 保存或更新 `WpFormula` 定义, THE Formula_Definition_Service SHALL 写入定义版本并保持 `last_computed_at` 原值。
2. WHEN 新 `WpFormula` 定义持久化成功, THE Formula_Lifecycle_State_Machine SHALL 将公式状态置为 `saved`。
3. WHEN 引用与目标校验成功, THE Formula_Lifecycle_State_Machine SHALL 仅允许 `saved` 或 `stale` 状态转换为 `validated`。
4. WHEN 真实执行开始, THE Formula_Lifecycle_State_Machine SHALL 将 `validated` 状态转换为 `executing`。
5. WHEN 公式求值与结果处理均成功提交, THE Formula_Lifecycle_State_Machine SHALL 将 `executing` 状态转换为 `succeeded` 并写入提交时刻的 `last_computed_at`。
6. IF 求值失败、写入失败、执行被跳过或事务回滚, THEN THE Formula_Lifecycle_State_Machine SHALL 将执行记录置为对应失败状态并保持 `last_computed_at` 原值。
7. IF 状态转换不属于已定义的状态转换关系, THEN THE Formula_Lifecycle_State_Machine SHALL 拒绝状态转换并返回结构化状态错误。

### Requirement 4: logic_check 独立来源与可失败语义

**User Story:** 作为现场经理，我希望七条跨表勾稽使用独立数据来源并能够真实失败，以便异常不会被恒真表达式掩盖。

#### Acceptance Criteria

1. THE Formula_Runtime SHALL 使七条跨表勾稽中的左右比较值来自两个独立报表行、两个独立领域来源或一个真实业务谓词。
2. WHEN `logic_check` #2 执行, THE Formula_Runtime SHALL 比较“营业收入减营业成本”的计算结果与独立毛利报表行的值。
3. WHEN `logic_check` #5 执行, THE Formula_Runtime SHALL 比较所有者权益变动表期末合计与资产负债表所有者权益合计。
4. WHEN `logic_check` #7 执行, THE Formula_Runtime SHALL 直接判断货币资金值是否大于或等于零。
5. WHEN 七条跨表勾稽中的任一真实条件不成立, THE Formula_Runtime SHALL 为对应规则生成 Issue。
6. WHEN Acceptance_Test_Suite 验证任一跨表勾稽规则, THE Acceptance_Test_Suite SHALL 使用至少一个通过样例和一个失败样例。
7. WHEN 前端降级规则与后端规则处理相同输入, THE Acceptance_Test_Suite SHALL 断言两个结果的通过状态和问题标识一致。

### Requirement 5: reference 执行期解引用与版本语义

**User Story:** 作为公式复用者，我希望参照公式在执行时使用明确的源版本，以便源公式变化不会留下无治理的保存时副本。

实时参照表示每次执行使用源公式当前有效版本；固定版本参照表示执行绑定的源版本，并在源版本不匹配时进入 stale，而不是静默使用旧副本。

#### Acceptance Criteria

1. WHEN Formula_Definition_Service 保存 reference 公式, THE Formula_Definition_Service SHALL 保存源公式关系、参照模式和源项目身份，并将复制表达式排除为权威定义。
2. WHERE reference 公式使用实时参照, THE Formula_Runtime SHALL 在每次执行时解析源公式链并使用当前有效源版本。
3. WHERE reference 公式使用固定版本参照, THE Formula_Runtime SHALL 保存 source_version 与 source_hash 并在执行前验证 source_version 与 source_hash。
4. IF 固定版本参照的源版本或源 hash 已变化, THEN THE Formula_Lifecycle_State_Machine SHALL 将引用方置为 `stale` 并阻止领域写入。
5. IF reference 链出现环、悬空或跨项目源, THEN THE Formula_Runtime SHALL 返回包含引用路径的结构化错误并保持领域业务值不变。
6. WHEN 源公式定义变化, THE Transaction_Coordinator SHALL 在同一事务中写入使实时引用方和固定版本引用方可被标记 stale 的 Outbox 事件。

### Requirement 6: ACNR 批量解析进入真实 ValueLoader 链

**User Story:** 作为公式引擎维护者，我希望 ACNR 解析结果直接驱动真实批量取值，以便公式求值不使用占位值、marker 值或未验证缓存。

#### Acceptance Criteria

1. WHEN Formula_Runtime 接收执行批次, THE Formula_Runtime SHALL 将 `addr_id`、`formula_ref` 和 `index_ref` 批量解析为 Canonical_Formula_Target。
2. WHEN ACNR 返回批量解析结果, THE Formula_Value_Loader SHALL 直接使用 canonical addr_id、domain 和领域 locator 从真实领域存储加载值。
3. WHEN 同一 Canonical_Formula_Target 在执行批次中重复出现, THE Formula_Runtime SHALL 对 Canonical_Formula_Target 只执行一次解析和一次批次内取值。
4. WHEN Formula_Value_Loader 完成加载, THE Formula_Runtime SHALL 将按 canonical addr_id 建立的真实值映射传入 Evaluation_Kernel。
5. IF ACNR 返回悬空地址、项目归属不一致或缺失领域 locator, THEN THE Formula_Runtime SHALL 在 Evaluation_Kernel 执行前返回结构化问题项并保持领域业务值不变。
6. IF Formula_Value_Loader 无法读取已解析目标的真实值, THEN THE Formula_Runtime SHALL 将目标记录为失败并保持该目标及依赖目标不变。

### Requirement 7: 四领域 TargetAdapter 覆盖

**User Story:** 作为平台开发者，我希望四个公式目标领域遵循统一的写入和恢复协议，以便执行、并发与回滚行为一致。

#### Acceptance Criteria

1. THE Formula_Runtime SHALL 提供 Workpaper_Adapter、Adjudication_Adapter、Report_Adapter 和 Note_Adapter 四个 Domain_Mutation_Adapter。
2. THE Domain_Mutation_Adapter SHALL 为批量目标提供 `prepare_many`、`apply_many`、`restore_many` 和 `read_versions` 操作。
3. WHEN Domain_Mutation_Adapter 准备 Formula_Mutation, THE Domain_Mutation_Adapter SHALL 返回 before_value、after_value 和 expected_version。
4. WHEN Adjudication_Adapter 应用 Formula_Mutation, THE Adjudication_Adapter SHALL 仅更新对应项目、年度和科目的 `trial_balance.audited_amount` 并保持 `unadjusted_amount` 不变。
5. WHEN Note_Adapter 应用 Formula_Mutation, THE Note_Adapter SHALL 仅更新被标记为允许自动回填的附注单元。
6. WHEN Formula_Runtime 处理四表库叶子源目标, THE Formula_Runtime SHALL 将四表库叶子源限制为只读取值并拒绝创建写入 Formula_Mutation。
7. WHEN Domain_Mutation_Adapter 恢复 Formula_Mutation, THE Domain_Mutation_Adapter SHALL 使用与原写入相同的领域 locator 和版本策略。

### Requirement 8: 并发锁、完整幂等指纹与 CAS

**User Story:** 作为业务合伙人，我希望重复点击和并发刷新只产生一次有效写入，并在任一输入 revision 变化时重新计算。

#### Acceptance Criteria

1. THE Formula_Runtime SHALL 使 Revision_Fingerprint 包含 project_id、year、排序后的 scopes、事务模式、四表源数据 revision、目标业务版本集合、公式定义 hash、reference source version/hash、预设 revision 和 ACNR registry version。
2. WHEN Revision_Fingerprint 的任一组成项变化, THE Formula_Runtime SHALL 生成不同指纹并执行新的 Execution_Run。
3. WHEN 相同 Revision_Fingerprint 的请求并发到达, THE Concurrency_Guard SHALL 通过 PostgreSQL 事务锁和唯一约束只允许一个 Execution_Run 成为 writer。
4. IF 相同 Revision_Fingerprint 的 Execution_Run 已成功完成, THEN THE Concurrency_Guard SHALL 返回已完成 Execution_Run 的幂等结果并保持业务值不变。
5. IF 相同 Revision_Fingerprint 的 Execution_Run 正在执行, THEN THE Concurrency_Guard SHALL 返回 HTTP 409 和当前 run_id 并保持业务值不变。
6. WHEN Domain_Mutation_Adapter 应用或恢复 Formula_Mutation, THE Concurrency_Guard SHALL 使用 CAS 比较 expected_version 与当前版本。
7. IF CAS 比较失败, THEN THE Concurrency_Guard SHALL 返回包含目标 identity、expected_version 和 current_version 的冲突明细并保持冲突目标不变。

### Requirement 9: All-or-nothing 与 Partial-success 事务契约

**User Story:** 作为刷新触发者，我希望明确知道批次采用整批原子提交还是分区部分成功，以便正确处理失败结果。

#### Acceptance Criteria

1. THE Refresh_API SHALL 将 All_Or_Nothing 设为默认事务模式。
2. IF All_Or_Nothing 模式中的任一解析、取值、求值、prepare、CAS 或 apply 步骤失败, THEN THE Transaction_Coordinator SHALL 回滚本次 Execution_Run 的业务写入、Rollback_Snapshot、成功审计、Governance_Metadata 和 Outbox。
3. WHERE 调用方显式选择 Partial_Success, THE Transaction_Coordinator SHALL 按 Execution_Partition 建立 savepoint 并隔离不同 Execution_Partition 的提交结果。
4. WHEN Partial_Success 模式完成, THE Refresh_API SHALL 返回每个 Execution_Partition 的 `applied`、`failed` 或 `skipped` 状态以及结构化失败原因。
5. IF 调用方未显式选择 Partial_Success, THEN THE Refresh_API SHALL 按 All_Or_Nothing 执行且不从 warning 或异常 catch 推断部分成功。
6. WHEN Execution_Run 提交完成, THE Refresh_API SHALL 使 `status` 与数据库已提交事实一致，并将空 mutation 批次标识为 `no_effect` 而非 `success`。

### Requirement 10: Service 层项目 Ownership

**User Story:** 作为安全负责人，我希望绕过路由直接调用 service 时仍无法跨项目读取、修改或执行公式。

#### Acceptance Criteria

1. WHEN Formula_Definition_Service 处理 save、list、delete 或 execute 操作, THE Ownership_Guard SHALL 校验 wp_id、formula_id 和请求 project_id 的归属关系。
2. WHEN Formula_Runtime 解析 reference、引用或目标, THE Ownership_Guard SHALL 校验源公式、Canonical_Formula_Target 和 Execution_Run 属于同一授权 project_id。
3. WHEN Domain_Mutation_Adapter 执行 prepare_many 或 restore_many, THE Ownership_Guard SHALL 再次校验每个目标的 project_id。
4. IF 任一实体不属于请求 project_id, THEN THE Ownership_Guard SHALL 拒绝操作、保持所有业务值不变并返回不包含目标敏感元数据的授权错误。
5. WHEN Refresh_API 已通过角色门禁, THE Ownership_Guard SHALL 继续执行 service 层 ownership 校验。
6. IF 调用方仅提供 formula_id 或 wp_id 而未提供 project_id, THEN THE Formula_Definition_Service SHALL 拒绝写入与执行操作。

### Requirement 11: 生产宿主与 OpenAPI 单一契约

**User Story:** 作为业务合伙人，我希望在生产页面打开刷新弹窗并看到与后端事实一致的结果，以便全局刷新功能真实可达且结果可解释。

#### Acceptance Criteria

1. THE Production_Host SHALL 挂载 Refresh_Scope_Dialog 并向 Refresh_Scope_Dialog 提供当前 project_id 与 year。
2. WHEN 当前角色属于业务合伙人或质量控制复核合伙人, THE Production_Host SHALL 显示可操作的 `GtRefreshScopeDialog` 入口。
3. WHEN 当前角色不具备 Global_Refresh 权限, THE Production_Host SHALL 隐藏入口且 Refresh_API SHALL 独立拒绝未授权请求。
4. THE Refresh_API SHALL 在 OpenAPI schema 中定义 `status`、`run_id`、`affected_count`、`applied_count`、`failed_count`、`skipped_count`、`failures`、`warnings`、`idempotent` 和 `rollback_available`。
5. THE Refresh_Scope_Dialog SHALL 使用 Refresh_API 的 OpenAPI schema 生成或校验前端类型，并使用与 schema 相同的字段名称。
6. WHEN Refresh_API 返回预设套用结果, THE Refresh_API SHALL 使用 `preset_count`、`presetted_pages` 和 `pending_pages` 字段。
7. WHEN Refresh_API 返回失败、冲突或 Partial_Success, THE Refresh_Scope_Dialog SHALL 展示对应状态与失败明细并避免显示统一成功提示。
8. IF 前后端 OpenAPI 契约发生不兼容漂移, THEN THE Acceptance_Test_Suite SHALL 使契约验证失败。

### Requirement 12: 单一纯求值内核与边界 Adapter

**User Story:** 作为架构维护者，我希望所有公式共享同一求值语义，以便不同调用路径不会产生不同结果。

#### Acceptance Criteria

1. THE Evaluation_Kernel SHALL 仅接收公式定义和已加载值并返回确定性结果，不访问数据库、网络、系统时钟或领域写入接口。
2. THE Formula_Runtime SHALL 将所有新公式执行路径委托给唯一 Evaluation_Kernel。
3. WHEN 旧 evaluator 调用仍需兼容, THE Evaluator_Adapter SHALL 仅转换输入输出并委托 Evaluation_Kernel。
4. WHEN 相同公式定义和相同值映射重复传入 Evaluation_Kernel, THE Evaluation_Kernel SHALL 返回相同数值、Issue、Hint 和错误分类。
5. THE Acceptance_Test_Suite SHALL 通过静态治理检查阻止新增绕过 Evaluation_Kernel 的 evaluator 或直接消费者。
6. WHEN Evaluation_Kernel 返回结果, THE Domain_Mutation_Adapter SHALL 在内核边界之外执行领域写入、版本控制和审计处理。

### Requirement 13: 批量性能与运行 Metrics

**User Story:** 作为平台运维人员，我希望解析、取值和写入按批次执行并可观测，以便识别 N+1、慢批次和异常失败率。

本需求使用 N 表示公式数量、U 表示唯一 canonical 引用数量、D 表示实际涉及的 domain 数量、B 表示大于零的配置批大小、M 表示待写入 mutation 数量。

#### Acceptance Criteria

1. WHEN 执行包含 N 条公式和 U 个唯一引用的批次, THE Formula_Runtime SHALL 按唯一引用集合而非按公式逐条调用 ACNR。
2. WHEN ACNR 支持批量解析且批大小为 B, THE Formula_Runtime SHALL 使 ACNR 解析调用次数不超过 `ceil(U / B)`。
3. WHEN Formula_Value_Loader 为 D 个 domain 加载 U 个唯一引用且批大小为 B, THE Formula_Value_Loader SHALL 使领域读取 round-trip 次数不超过各 domain 的 `ceil(U_domain / B)` 之和。
4. WHEN Domain_Mutation_Adapter 应用 M 个 Formula_Mutation 且批大小为 B, THE Domain_Mutation_Adapter SHALL 按 domain 批量写入并避免逐公式逐引用写入模式。
5. WHEN Execution_Run 完成或失败, THE Runtime_Metrics SHALL 记录批次耗时、公式数、唯一引用数、resolve 批次数、value-load 批次数、数据库 round-trip 数、applied 数、failed 数、CAS 冲突数和 rollback 数。
6. THE Runtime_Metrics SHALL 使用 domain、事务模式、结果状态和错误分类作为允许标签，并排除 project_id、formula_id、addr_id、run_id 和用户标识等高基数标签。
7. IF 测试批次出现超过规定上界的 resolve 或 value-load round-trip, THEN THE Acceptance_Test_Suite SHALL 报告 N+1 回归并失败。

### Requirement 14: 真实 PostgreSQL 与五角色 Playwright 强验收

**User Story:** 作为项目负责人，我希望真实数据库和五个独立角色证明运行闭环，以便禁止 skip、吞错和单一 admin 复用产生假绿。

#### Acceptance Criteria

1. WHEN Acceptance_Test_Suite 验证成功执行, THE Acceptance_Test_Suite SHALL 使用真实 PostgreSQL 记录并断言执行前值、执行后值和提交后的 Governance_Metadata。
2. WHEN Acceptance_Test_Suite 验证回滚, THE Acceptance_Test_Suite SHALL 在真实 PostgreSQL 中断言回滚后业务值与 Governance_Metadata 等于执行前状态，并断言回滚审计与 Outbox 状态。
3. THE Five_Role_Fixture SHALL 提供五个不同的登录身份，分别对应审计助理、现场经理、业务合伙人、质量控制复核合伙人和 EQCR 技术复核人。
4. WHEN Playwright 验证 Global_Refresh, THE Acceptance_Test_Suite SHALL 使用业务合伙人执行刷新，并使用其余四个角色验证权限、结果可见性、复核状态与技术复核证据。
5. IF Five_Role_Fixture、真实 PostgreSQL 或生产宿主不可用, THEN THE Acceptance_Test_Suite SHALL 失败并报告环境缺口。
6. THE Acceptance_Test_Suite SHALL 使核心验收测试保持启用，并将 `skip`、`fixme`、条件跳过、catch 后忽略失败和元素不可见即绕过断言视为测试失败。
7. WHEN Playwright 触发 Refresh_API, THE Acceptance_Test_Suite SHALL 等待并断言明确的 HTTP 状态、run_id、业务值变化和 UI 结果明细。
8. IF 浏览器 console 出现未列入明确静态白名单的 error, THEN THE Acceptance_Test_Suite SHALL 失败并输出 console error。

### Requirement 15: 旧 Spec 假绿状态纠正

**User Story:** 作为治理负责人，我希望旧 Spec 的完成状态与可验证事实一致，以便 100% 状态不会掩盖运行时缺口。

#### Acceptance Criteria

1. WHEN 本 Spec 进入设计阶段, THE Evidence_Ledger SHALL 将十五类已实证缺口逐项映射到 Legacy_Formula_Spec 的需求、实现路径和测试证据。
2. IF Legacy_Formula_Spec 的“完成”条目缺少真实业务写入、真实回滚、强验收或对应证据, THEN THE Evidence_Ledger SHALL 将条目标记为 `unverified` 或 `gap`。
3. WHEN Evidence_Ledger 存在 `unverified` 或 `gap` 条目, THE Spec_Completion_Guard SHALL 将 Legacy_Formula_Spec 的无条件 100% 完成声明纠正为 `needs-remediation`。
4. WHEN 某缺口由本 Spec 完成修复, THE Evidence_Ledger SHALL 记录对应代码、真实 PostgreSQL 测试、Playwright 测试和 CI 运行标识。
5. IF 仅 mock、SQLite、默认跳过或吞错测试通过, THEN THE Spec_Completion_Guard SHALL 保持对应条目为未验证。
6. WHEN Evidence_Ledger 的全部缺口具备强验收证据, THE Spec_Completion_Guard SHALL 允许治理状态更新为完成并保留历史纠正记录。
7. THE Spec_Completion_Guard SHALL 保持本 Spec 的所有实现任务为未完成，直到对应任务的独立验证与依赖验收均通过。

### Requirement 16: 最大化子代理并行的实现计划

**User Story:** 作为交付负责人，我希望后续设计和任务计划按文件所有权最大化安全并行，以便多个子代理能同时开发而不互相覆盖。

#### Acceptance Criteria

1. THE Implementation_Plan SHALL 为每个实现任务声明 `dependsOn`、`ownerFiles`、`generatedFiles`、`forbiddenSharedFiles` 和独立验证命令。
2. WHEN 两个任务不存在数据、接口或文件依赖, THE Implementation_Plan SHALL 将两个任务安排在同一最早可执行 Wave。
3. WHEN 两个任务位于同一 Wave, THE Implementation_Plan SHALL 使两个任务的 `ownerFiles` 与 `generatedFiles` 集合互不相交。
4. WHEN 任务涉及共享接口, THE Implementation_Plan SHALL 先安排 contract 冻结任务，再并行安排只消费 contract 的实现任务。
5. WHEN 任务涉及高冲突集成文件, THE Implementation_Plan SHALL 为每个高冲突文件指定唯一串行 owner 并禁止同 Wave 的其他任务修改高冲突文件。
6. WHEN 并行任务完成, THE Implementation_Plan SHALL 安排独立 integration 任务执行跨领域组装、OpenAPI 对齐、真实 PostgreSQL 验收和五角色 Playwright 验收。
7. IF 子代理发现 ownerFiles 之外的修改需求, THEN THE Implementation_Plan SHALL 要求子代理记录接口缺口并由后续唯一 owner 处理。
8. THE Implementation_Plan SHALL 以关键路径最短和同 Wave 文件交集为空作为并行度优化约束。
