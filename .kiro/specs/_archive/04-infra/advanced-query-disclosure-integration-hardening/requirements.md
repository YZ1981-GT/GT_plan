# Requirements Document

## Introduction

本 spec 在既有 `advanced-query-module` 与附注能力之上做集成加固，不重造查询、ACNR、附注编辑器或历史文件解析。目标是封住项目授权与写权限，修正缓存身份和分页语义，让主 `/api/custom-query/execute` 兼容接入 `QueryOrchestrator`，并确保查询结果进入附注后的手工值、来源与追踪信息不丢失。

优先级：下列需求均为 **P0 本期交付**；“非目标”均为 **P2 明确不做**。

## Glossary

- **CanonicalQueryIdentity**：完整、稳定、与结果语义一一对应的查询身份。
- **主 execute**：现有 `POST /api/custom-query/execute` 兼容入口。
- **真实分页**：数据源层按稳定排序执行 limit/offset，并返回可信 total，而非先截断后在内存伪分页。
- **附注 mutation**：生成、更新、删除、恢复、状态变更等会修改附注数据的请求。
- **Manual / Provenance / Trace**：手工值保护标记、来源元数据和单元格追踪链。
- **响应式草稿隔离**：项目、年度或章节变化时，自动保存键与恢复目标同步变化且互不串扰。

## Requirements

### Requirement 1: 项目授权与对象归属

**User Story:** 作为项目成员，我希望查询与附注数据只能在我获授权的项目内读取，以避免跨项目泄露。

#### Acceptance Criteria
1. WHEN 已认证用户访问项目相关的指标、主 execute、模板执行、附注目录、详情、prior-year、trace 或自动取数端点时，THE SYSTEM SHALL 在读取缓存或业务数据前校验 readonly 项目权限。
2. WHEN 请求仅携带 `note_id`、模板 id 或其他对象 id 时，THE SYSTEM SHALL 先以最小字段解析其 `project_id`，再执行统一项目授权，且不得在 403 响应中泄露对象内容。
3. IF 用户无目标项目权限，THEN THE SYSTEM SHALL 返回 403，且不得读取查询缓存、返回部分数据或执行后续领域查询。
4. WHEN 查询涉及多个项目时，THE SYSTEM SHALL 对每个项目执行授权并仅允许显式授权集合进入执行计划。

### Requirement 2: edit 与 writeback 权限

**User Story:** 作为项目负责人，我希望附注编辑和查询回写只由具备相应写权限的成员执行。

#### Acceptance Criteria
1. WHEN 用户执行任一附注 mutation，THE SYSTEM SHALL 要求项目 `edit` 权限及现有操作级权限（适用时含 `note:edit` 与合并锁检查）。
2. WHEN 用户预览或确认高级查询回写，THE SYSTEM SHALL 要求目标项目 edit 权限与 writeback 操作权限，并逐一校验所有目标 `addr_id` 的项目归属。
3. IF 任一目标缺少 edit/writeback 权限或被项目锁阻止，THEN THE SYSTEM SHALL 拒绝整个 mutation/回写，不得产生部分写入。
4. WHILE 用户仅具 readonly 权限，THE SYSTEM SHALL 允许授权范围内查询和 trace，但 SHALL NOT 暴露可执行的编辑或回写操作。

### Requirement 3: CanonicalQueryIdentity 完整性

**User Story:** 作为查询用户，我希望语义不同的查询绝不共用缓存结果。

#### Acceptance Criteria
1. THE SYSTEM SHALL 以规范化后的 source、filters、columns、limit、offset、sort、group、pivot、ACNR 目标、项目、用户权限范围、schema version 与 query contract version 构造 CanonicalQueryIdentity。
2. WHEN 上述任一结果影响字段不同，THE SYSTEM SHALL 生成不同身份；WHEN 仅对象键顺序不同且语义相同，THE SYSTEM SHALL 生成相同身份。
3. WHEN columns 顺序、sort 优先级、group 维度顺序、pivot 行列定义或 ACNR 目标顺序具有业务语义时，THE SYSTEM SHALL 保留其顺序，不得排序抹平差异。
4. WHEN 缓存命中时，THE SYSTEM SHALL 返回与该完整身份直接执行所得相同的 columns、rows、total、manual/provenance/trace 元数据。
5. IF 身份构造发现未知或不可稳定序列化字段，THEN THE SYSTEM SHALL 绕过缓存并记录可观测告警，而不得使用不完整缓存键。
### Requirement 4: 真实分页与稳定排序

**User Story:** 作为审计人员，我希望翻页结果完整、稳定且不重复漏行。

#### Acceptance Criteria
1. WHEN 主 execute 接收 `limit` 与 `offset`，THE SYSTEM SHALL 在最终数据源查询/编排层执行真实分页，并返回未分页结果总数 `total`。
2. WHEN 客户端未提供 sort，THE SYSTEM SHALL 应用可重复的默认排序与唯一稳定 tie-breaker；WHEN 提供 sort，THE SYSTEM SHALL 在其后补唯一 tie-breaker。
3. FOR ALL 相邻有效页，同一查询快照中的行集合 SHALL 不重叠，且顺序拼接后等于相同排序下的未分页结果。
4. IF `limit` 越界、`offset < 0` 或 sort 字段无效，THEN THE SYSTEM SHALL 在执行前返回 422 描述性错误。
5. WHEN group 或 pivot 生效，THE SYSTEM SHALL 在聚合/透视语义完成后对最终结果分页，并使 `total` 表示最终结果行数。

### Requirement 5: 主 execute 兼容接入 QueryOrchestrator

**User Story:** 作为现有客户端，我希望升级后无需改造即可继续执行查询，同时获得统一编排能力。

#### Acceptance Criteria
1. WHEN 旧客户端向主 execute 提交既有 `QueryRequest` 字段，THE SYSTEM SHALL 通过兼容适配器调用 `QueryOrchestrator`，并保持既有成功字段、HTTP 状态与错误信封兼容。
2. WHEN 新客户端提交 sort、group、pivot 或 ACNR 目标，THE SYSTEM SHALL 将其无损传入 `QueryOrchestrator`，不得由旧 router 分支静默丢弃。
3. WHEN `QueryOrchestrator` 返回统一 `QueryResult`，THE SYSTEM SHALL 适配为主 execute 响应，并保留 columns、rows、total、limit、offset、warnings、provenance 与 trace。
4. IF 编排器拒绝请求，THEN THE SYSTEM SHALL 映射为既有可识别的 4xx 错误；IF 编排器发生未预期错误，THEN THE SYSTEM SHALL 回滚当前事务、记录关联 id 并返回 500，不得回退到结果语义不同的旧执行路径。
5. WHILE 兼容期存在，THE SYSTEM SHALL 只保留一个实际执行核心，旧入口不得并行执行第二套查询逻辑。

### Requirement 6: 模板作用域与共享兼容

**User Story:** 作为审计团队成员，我希望模板按私人、团队、项目或公开范围准确可见。

#### Acceptance Criteria
1. THE SYSTEM SHALL 支持 API 作用域 `private`、`team`、`project`、`public`，并仅将遗留输入 `global` 作为 `public` 的兼容别名。
2. WHEN scope 为 `private`，THE SYSTEM SHALL 仅允许所有者查看、编辑、删除和执行；WHEN 为 `team`，THE SYSTEM SHALL 仅允许当前团队授权成员使用。
3. WHEN scope 为 `project`，THE SYSTEM SHALL 要求 `shared_project_ids` 非空、去重且每个项目均通过分享者 edit 权限校验，并仅向这些项目的授权成员可见。
4. WHEN scope 为 `public` 或遗留 `global`，THE SYSTEM SHALL 按公开模板语义读取；新写入 SHALL 使用 canonical `public`，读取遗留 `global` 记录时 SHALL 等价归一为 `public`。
5. IF 用户编辑、删除、分享或执行不可见模板，THEN THE SYSTEM SHALL 返回 403；模板执行仍 SHALL 按当前用户项目权限重新授权。
6. THE SYSTEM SHALL 使用现有 `shared_project_ids` 与兼容配置表达项目分享，不新增数据库迁移。

### Requirement 7: 附注 mutation 事务与 EventBus 可观测性

**User Story:** 作为审计人员，我希望附注保存结果真实可靠，事件通知失败也不会被静默吞掉。

#### Acceptance Criteria
1. WHEN 附注 mutation 成功，THE SYSTEM SHALL 显式 commit 后返回成功；IF mutation 在 commit 前失败，THEN THE SYSTEM SHALL 显式 rollback 并返回失败。
2. WHEN 已提交 mutation 需要发布 EventBus 事件，THE SYSTEM SHALL 发布包含 project/year/section/mutation_id 的事件。
3. IF EventBus 发布失败，THEN THE SYSTEM SHALL 保留已提交业务数据、记录结构化错误与指标，并在响应 warnings 或可查询状态中暴露 `event_delivery_failed`，不得 `pass` 静默吞错或宣称事件已送达。
4. IF 数据库 commit 失败，THEN THE SYSTEM SHALL rollback 且不得发布成功事件。
5. WHEN 客户端以同一 mutation_id 重试，THE SYSTEM SHALL 避免重复业务 mutation 或重复成功事件。

### Requirement 8: autosave 隔离与 manual/provenance/trace 保持

**User Story:** 作为附注编制人员，我希望跨项目、年度、章节切换时草稿不串写，自动取数也不覆盖手工判断和溯源。

#### Acceptance Criteria
1. THE SYSTEM SHALL 以 `project_id + year + section` 构成附注 Draft_Key；WHEN 任一部分响应式变化，THE SYSTEM SHALL 停止旧定时器、切换键、重新检查新上下文草稿且不得写入旧上下文。
2. WHEN 恢复草稿，THE SYSTEM SHALL 校验 payload 中的 project/year/section 与当前上下文完全一致；IF 不一致，THEN THE SYSTEM SHALL 拒绝恢复并保留两个草稿。
3. WHEN 查询结果自动填充附注，THE SYSTEM SHALL 保留并返回 Manual_Cell、provenance 与 trace 元数据，且不得覆盖 manual=true 的单元格。
4. WHEN 用户编辑自动填充单元格，THE SYSTEM SHALL 将其标记为 manual，并保留原 provenance/trace 作为历史来源而非删除。
5. WHEN 保存、刷新、分页、模板执行或重新打开章节，THE SYSTEM SHALL 保持 manual/provenance/trace 的语义与关联 `addr_id` 不变。
### Requirement 9: 历史上传能力诚实降级

**User Story:** 作为用户，我希望未实现的历史 Word/PDF 导入被明确禁用，而不是看到可点击但失败的假功能。

#### Acceptance Criteria
1. WHILE 历史 Word/PDF 真实解析未实现，THE SYSTEM SHALL 使上传/解析端点稳定返回 HTTP 501 与机器可读错误码 `HISTORICAL_UPLOAD_NOT_IMPLEMENTED`。
2. WHILE 后端能力为 501，THE SYSTEM SHALL 在能力发现结果中标记 `historical_upload=false`，前端 SHALL 禁用或隐藏上传操作并显示中文原因。
3. IF 客户端绕过前端直接调用该端点，THEN THE SYSTEM SHALL 不创建任务、不存文件、不修改附注或查询数据。
4. THE SYSTEM SHALL NOT 以空成功、模拟解析结果或 200 占位响应代替 501。

### Requirement 10: 验收证据与不假绿

**User Story:** 作为交付负责人，我希望只有真实执行通过的检查才能标记完成。

#### Acceptance Criteria
1. WHEN 任一 coding task 完成，THE SYSTEM SHALL 运行其对应的定向 pytest 或 Vitest；WHEN 涉及 Vue/Python 类型或语义，THE SYSTEM SHALL 对改动文件运行 diagnostics。
2. WHEN 全部实现完成，THE SYSTEM SHALL 运行相关 pytest、Vitest、diagnostics，并以 Playwright 实测两条中文主链。
3. THE 第一条中文主链 SHALL 覆盖“选择项目 → 高级查询指定 columns/sort/group/pivot → 翻至下一页 → ACNR/trace 下钻 → 保存 project 模板并验证可见性”。
4. THE 第二条中文主链 SHALL 覆盖“从查询定位附注 → 切换 project/year/section 验证草稿隔离 → 编辑 manual 单元格 → 保存并刷新 → provenance/trace 保持 → 历史上传入口禁用且直调返回 501”。
5. IF 任一命令未运行、被跳过、失败或仅由 mock 代替真实主链，THEN THE SYSTEM SHALL 保持对应任务为 `[ ]` 并记录阻塞原因，不得标记通过。
6. WHEN EventBus 故障路径被验收，THE SYSTEM SHALL 通过可控故障注入验证业务 commit 保留且 `event_delivery_failed` 可观测。

## 4. P2 非目标

本 spec 明确不包含：

1. 历史 Word/PDF 的真实解析、版式还原或 OCR 抽取。
2. 彻底拆分约 2371 行的 `DisclosureEditor`；本期只允许为状态隔离和能力门禁做最小接线。
3. 大查询异步导出、后台任务、进度 SSE 或下载中心。
4. 批量 writeback；本期只加固既有单次/当前预览确认路径。
5. 任何 DB migration 或 schema 变更。

## 5. 约束与完成定义

- 复用既有 `QueryOrchestrator`、`CanonicalQueryIdentity`/缓存能力、ACNR、`shared_project_ids`、附注服务与 EventBus，不建立平行实现。
- 兼容优先但不允许静默降级：旧请求可继续工作，新语义字段不得丢失。
- 所有 tasks 初始为 `[ ]`；即使标记为 optional `*` 的 PBT，本次也必须执行并通过后才能完成。
- 验收结果必须附命令、退出码或 Playwright 可复核证据；不得依据“代码看起来正确”假绿。
