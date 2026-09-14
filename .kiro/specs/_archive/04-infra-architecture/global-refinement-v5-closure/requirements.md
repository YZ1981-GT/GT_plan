# Requirements Document

## Introduction

本 spec 是 v5.0 全局复盘（`docs/GLOBAL_REFINEMENT_PROPOSAL_v4.md`）确认的统一收口需求文档，补齐 M1 一致性收口出列后剩余的 4 个经代码实证的真实缺口，聚焦"联动闭环 + 并发安全 + 功能补全"。四个能力域分别为：

1. **T5｜金额单元格右键数字溯源**——六大数据页金额列已 100% 接入 GtAmountCell，但缺单元格级即时反查入口。复用现有反向溯源基建（`trace_event_service`/`report_trace_service`/`unified_lineage_service` 后端，`useCellLocate`/`CellTraceDialog`/eventBus `workpaper:locate-cell` 前端），不新建端点。
2. **T5/T6｜stale 全局自动刷新 + 年度联动**——`useProjectEvents` 当前仅接入约 6 个文件（TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex 等）。复用 `useProjectEvents`（SSE 项目级事件流）与 eventBus 既有事件（`trial-balance:updated`/`adjustment:saved`/`year:changed`），让六大数据页（四表/报表/底稿/调整/错报/附注）上游变更后自动刷新或提示重算，并实现年度切换全局联动。
3. **T8｜通用编辑锁（resource_type）**——后端现有 `workpaper_editing_locks`（底稿专用）+ `adjustment_editing_locks`（调整专用）两套专用表；前端 `useEditingLock` 接入 4 文件但仅 WorkpaperEditor 是真后端锁，DisclosureEditor/AuditReportEditor 是前端降级检测（存在互相覆盖风险）。新建后端通用 `editing_locks` 表（resource_type + resource_id + holder + heartbeat + 过期）+ 通用锁端点，让附注/报告编辑器改用真后端锁。并发安全硬需求。
4. **T12｜函证模块（confirmation）**——`backend/app/routers/confirmations.py` 仍是 18 行 developing stub。实现审计函证全流程：函证清单管理 + 函证状态机 + 与底稿/TB 关联 + 回函差异记录，复用 eventBus 既有 `confirmation:received` 事件。

所有能力域遵守三层一致（DB 迁移 + ORM `Mapped[]` + service 方法）、UI 全中文、金额用 GtAmountCell、GT 紫令牌、PBT `max_examples=5`、文件大小门禁等项目铁律。

## Glossary

- **GtAmountCell**: 前端统一金额展示组件，已 100% 接入六大数据页金额列。
- **六大数据页**: 四表（TrialBalance/试算平衡表相关）、报表（ReportView）、底稿（WorkpaperEditor）、调整（调整分录页）、错报（misstatement/错报页）、附注（DisclosureEditor）。
- **Trace_Backend**: 现有后端反向溯源基建集合，含 `trace_event_service`、`report_trace_service`、`wp_trace_service`、`unified_lineage_service`，输出 `LocateTarget` 格式。
- **useCellLocate**: 前端单元格定位 composable，提供 `locateCell`。
- **CellTraceDialog**: 前端单元格溯源弹窗组件（`components/notes/CellTraceDialog.vue`）。
- **locate-cell 事件**: eventBus 的 `workpaper:locate-cell` 事件，载荷含 `wpId`/`sheetName`/`cellRef`。
- **useProjectEvents**: 前端 composable，订阅 eventBus `sse:sync-event`，按 projectId 过滤分发项目级 SSE 事件。
- **stale 标记**: 数据页上游变更后标识当前展示数据已过期的 UI 状态。
- **Editing_Lock_Backend**: 本 spec 新建的后端通用编辑锁子系统，含 `editing_locks` 表 + ORM + service + 通用锁端点。
- **resource_type**: 通用锁资源类型字段（如 `disclosure_note`/`audit_report`/`workpaper`）。
- **useEditingLock**: 前端编辑锁 composable，接入编辑器视图。
- **Confirmation_Module**: 本 spec 实现的函证模块，含函证清单管理 + 状态机 + 关联 + 差异记录。
- **函证状态机**: 待发函 → 已发函 → 已回函 → 差异/相符 的状态流转。
- **confirmation:received 事件**: eventBus 既有事件，函证回函后触发（E1-3 标记已函证）。
- **D6 迁移系统**: 运行时迁移系统，`V*.sql` + `R*.sql` 配对，CREATE/ALTER 必 `IF NOT EXISTS`，当前最高 V056，本 spec 新建从 V057 起。
- **三层一致**: DB 迁移（V057+/R057+ 配对）+ ORM `Mapped[]` + service 方法，缺一即伪绿。
- **PBT**: Property-Based Test（基于属性的测试），hypothesis `max_examples=5`。
- **check_file_size.py**: 文件大小门禁脚本（`backend/scripts/check/check_file_size.py`），新增/改动后必跑。

## Requirements

### 能力域 A｜T5 金额单元格右键"数字溯源"

### Requirement 1: 金额单元格右键溯源入口

**User Story:** 作为审计助理，我想在任意数据页的金额单元格上右键点击"数字溯源"，以便即时查看该数字的来源链而无需手动跳转底稿。

#### Acceptance Criteria

1. WHERE 金额单元格使用 GtAmountCell 渲染，THE GtAmountCell SHALL 在单元格上提供右键上下文菜单（`@contextmenu` 绑定）。
2. WHEN 用户在金额单元格上右键点击，THE GtAmountCell SHALL 显示含"数字溯源"项的中文上下文菜单。
3. WHEN 用户点击"数字溯源"菜单项，THE GtAmountCell SHALL 触发 eventBus `workpaper:locate-cell` 事件或打开 CellTraceDialog，载荷包含定位该单元格所需的标识（项目、对象类型、对象标识、单元格引用）。
4. WHERE 单元格无可溯源来源，THE GtAmountCell SHALL 显示中文提示"该数字暂无溯源信息"并不展示空白弹窗。

### Requirement 2: 来源链展示

**User Story:** 作为项目经理，我想看到金额从报表行到 TB 科目再到序时账/凭证的完整来源链，以便核对数字勾稽关系。

#### Acceptance Criteria

1. WHEN 数字溯源被触发，THE Trace_Backend SHALL 通过现有 `unified_lineage_service` / `report_trace_service` 返回 `LocateTarget` 格式的来源链。
2. WHEN 来源链返回，THE CellTraceDialog SHALL 按层级展示来源节点（报表行 → TB 科目 → 序时账/凭证）。
3. WHEN 用户点击来源链中的某个底稿/试算表节点，THE CellTraceDialog SHALL 通过 eventBus `workpaper:locate-cell` 或路由跳转定位到该节点。
4. IF 后端溯源查询失败，THEN THE CellTraceDialog SHALL 通过 handleApiError 展示中文错误提示并保持页面可用。

### Requirement 3: 复用现有溯源端点

**User Story:** 作为质控，我想确认溯源功能复用现有后端基建而非新增重复端点，以便维持单一溯源真源。

#### Acceptance Criteria

1. THE Trace_Backend SHALL 复用现有 `trace_event_service` / `report_trace_service` / `unified_lineage_service`，不新增独立的溯源 router。
2. WHERE 需要前端定位，THE 前端 SHALL 复用现有 `useCellLocate` / `CellTraceDialog` / eventBus `workpaper:locate-cell`，不新增重复 composable。

---

### 能力域 B｜T5/T6 stale 全局自动刷新 + 年度联动

### Requirement 4: 六大数据页接入项目级事件流

**User Story:** 作为审计助理，我想让所有数据页在上游数据变更后自动感知，以便始终看到最新数据而非陈旧缓存。

#### Acceptance Criteria

1. THE 六大数据页（四表、报表、底稿、调整、错报、附注）SHALL 全部 import 并调用 `useProjectEvents`，使接入文件数从 6 增加到 12 个或以上。
2. WHEN 上游数据变更事件（`trial-balance:updated` / `adjustment:saved` / `dataset:activated` / `dataset:rolledback`）到达且 projectId 匹配，THE 对应数据页 SHALL 自动重新拉取数据或将 stale 标记置为真。
3. WHERE 数据页选择提示而非自动刷新，THE 数据页 SHALL 显示中文 stale 提示（如"上游数据已变更，建议重新计算"）并提供刷新操作入口。
4. WHEN 接收到的事件 projectId 与当前页不匹配，THE useProjectEvents SHALL 忽略该事件不触发刷新。

### Requirement 5: 年度切换全局联动

**User Story:** 作为项目经理，我想切换审计年度时所有数据页同步刷新到该年度数据，以便跨年度查看时数据一致。

#### Acceptance Criteria

1. WHEN eventBus `year:changed` 事件触发且 projectId 匹配，THE 六大数据页 SHALL 按新年度重新拉取数据。
2. FOR ALL 接收 `year:changed` 的数据页，WHEN 事件 projectId 与当前页匹配，THE 数据页 SHALL 触发刷新（事件分发不变量：projectId 匹配即分发，不匹配即忽略）。
3. WHILE 数据页正在按新年度刷新，THE 数据页 SHALL 显示中文加载状态。

---

### 能力域 C｜T8 通用编辑锁（resource_type）

### Requirement 6: 通用编辑锁表与三层一致

**User Story:** 作为质控，我想后端提供支持 resource_type 的通用编辑锁表，以便附注/报告等任意资源都能用同一套真锁机制。

#### Acceptance Criteria

1. THE Editing_Lock_Backend SHALL 提供从 V057 起的迁移文件（`V057__*.sql` + `R057__*.sql` 配对），且 CREATE TABLE 使用 `IF NOT EXISTS`。
2. THE `editing_locks` 表 SHALL 包含字段 resource_type、resource_id、holder（持有人标识）、heartbeat（心跳时间）、过期/释放标记。
3. THE Editing_Lock_Backend SHALL 提供对应 ORM 模型（`Mapped[]` 类型标注）与 service 方法，保证三层一致（迁移 + ORM + service）。
4. THE `editing_locks` 表 SHALL 对 (resource_type, resource_id) 建立索引以支持锁查询。

### Requirement 7: 通用锁端点

**User Story:** 作为审计助理，我想在编辑资源前获取锁、编辑中续约、编辑完释放，以便其他人知道我正在编辑。

#### Acceptance Criteria

1. THE Editing_Lock_Backend SHALL 提供 acquire 端点，WHEN 资源无活跃锁，THE 端点 SHALL 创建锁并返回持有成功。
2. THE Editing_Lock_Backend SHALL 提供 release 端点，WHEN 持有人释放锁，THE 端点 SHALL 标记锁为已释放。
3. THE Editing_Lock_Backend SHALL 提供 heartbeat 端点，WHEN 持有人续约，THE 端点 SHALL 更新锁的 heartbeat 时间。
4. THE Editing_Lock_Backend SHALL 提供 force-acquire 端点，WHEN 调用强抢，THE 端点 SHALL 释放原锁、创建新锁并返回前持有人信息。

### Requirement 8: 并发安全不变量

**User Story:** 作为质控，我想保证同一资源同一时刻只有一个有效编辑锁，以便两人不会互相覆盖编辑内容。

#### Acceptance Criteria

1. FOR ALL acquire 请求序列作用于同一 (resource_type, resource_id)，THE Editing_Lock_Backend SHALL 保证活跃锁数量不超过 1（并发安全不变量）。
2. WHEN 第二人对已被持有的资源调用 acquire，THE Editing_Lock_Backend SHALL 拒绝并返回当前锁持有人信息。
3. IF 锁的 heartbeat 超过过期阈值，THEN THE Editing_Lock_Backend SHALL 视该锁为过期，使后续 acquire 可成功获取（过期锁不阻塞新 acquire）。

### Requirement 9: 附注/报告编辑器接入真锁

**User Story:** 作为审计助理，我想在编辑附注或审计报告时获得真后端锁保护，以便两人并发编辑时第二人看到只读和锁持有人提示。

#### Acceptance Criteria

1. THE DisclosureEditor SHALL 通过 `useEditingLock` 调用通用锁端点（resource_type=`disclosure_note`），替换原前端降级检测。
2. THE AuditReportEditor SHALL 通过 `useEditingLock` 调用通用锁端点（resource_type=`audit_report`），替换原前端降级检测。
3. WHEN 第二人打开已被锁定的附注或报告，THE 编辑器 SHALL 进入只读状态并显示中文锁持有人提示。
4. WHEN 锁被强抢，THE 原持有人编辑器 SHALL 通过 eventBus `editing-lock:taken-over` 收到通知并提示。

---

### 能力域 D｜T12 函证模块

### Requirement 10: 函证清单管理

**User Story:** 作为审计助理，我想管理项目的函证清单（应收/应付/银行/借款等类型），以便统一跟踪每封询证函。

#### Acceptance Criteria

1. THE Confirmation_Module SHALL 提供从 V057 起的迁移（与编辑锁迁移按数字顺序排号，避免撞号）、ORM 模型（`Mapped[]`）与 service 方法，保证三层一致。
2. THE Confirmation_Module SHALL 支持函证类型枚举（应收、应付、银行、借款）。
3. WHEN 用户创建函证记录，THE Confirmation_Module SHALL 持久化函证并返回函证标识。
4. WHEN 用户查询项目函证列表，THE Confirmation_Module SHALL 返回该项目的函证清单（替换原 `{status:"developing"}` stub）。
5. WHEN 用户更新或删除函证记录，THE Confirmation_Module SHALL 持久化变更。

### Requirement 11: 函证状态机

**User Story:** 作为项目经理，我想函证按"待发函→已发函→已回函→差异/相符"流转，以便掌握每封函证进度。

#### Acceptance Criteria

1. THE Confirmation_Module SHALL 定义函证状态枚举：待发函、已发函、已回函、相符、差异。
2. WHEN 用户推进函证状态，THE Confirmation_Module SHALL 仅允许合法状态转换（待发函→已发函→已回函→相符/差异）。
3. IF 用户尝试非法状态转换，THEN THE Confirmation_Module SHALL 拒绝并返回中文错误说明。
4. WHEN 函证回函登记完成，THE Confirmation_Module SHALL 触发 eventBus `confirmation:received` 事件。

### Requirement 12: 函证关联与差异记录

**User Story:** 作为审计助理，我想把函证关联到底稿/TB 科目并记录回函差异，以便差异可追溯到具体科目。

#### Acceptance Criteria

1. WHEN 创建函证，THE Confirmation_Module SHALL 支持关联底稿标识与 TB 科目编码并持久化关联字段。
2. WHEN 回函与账面存在差异，THE Confirmation_Module SHALL 记录差异金额与差异说明。
3. WHEN 查询函证详情，THE Confirmation_Module SHALL 返回关联底稿/TB 信息与差异记录。

---

### 非功能约束（跨能力域）

### Requirement 13: UI 全中文与视觉规范

**User Story:** 作为致同审计用户，我想所有界面文本为中文且视觉统一，以便符合致同审计场景使用习惯。

#### Acceptance Criteria

1. THE 本 spec 新增/改动的前端 SHALL 使用中文展示所有用户可见文本（技术术语 SQL/PDF/API/UUID 等保留英文）。
2. THE 本 spec 新增/改动的金额展示 SHALL 使用 GtAmountCell 组件。
3. THE 本 spec 新增/改动的 UI 样式 SHALL 使用 GT 紫令牌（`--gt-color-primary` 等），不使用 Element 默认蓝作 fallback。

### Requirement 14: 测试与门禁约束

**User Story:** 作为质控，我想所有新增逻辑有可验收测试且不触发治理回退，以便交付质量可证。

#### Acceptance Criteria

1. THE 本 spec 新增的 hypothesis 属性测试 SHALL 配置 `settings(max_examples=5)`，不使用默认 100。
2. WHEN 新增或改动文件后，THE check_file_size.py SHALL 以 exit 0 通过（撑大文件优先抽伴生模块而非抬基线）。
3. THE 本 spec 新增的每条核心需求 SHALL 有可验收证据（grep 命中数 / 测试通过 / 真实样本跑通）。
4. THE 本 spec 新增的后端能力 SHALL 满足三层一致（DB 迁移 + ORM `Mapped[]` + service 方法），任一缺失视为伪绿不通过。
