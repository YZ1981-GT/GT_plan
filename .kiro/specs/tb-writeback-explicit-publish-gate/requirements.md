# Requirements Document
（需求文档：TB 回写显式发布门 tb-writeback-explicit-publish-gate）

## Introduction

本 spec 把 `d4-dual-mode-formula-governance` Requirement 4.2 确立的"审定数回写试算表须显式确认 + 幂等 + 权限"范式，从 D4-1 推广到其余全部 D~N 审定表组件。现状实证（census 只读盘点 `census_writeback_call_sites.md`）：`trial-balance/writeback` 字面量命中 107 行真实 HTTP 调用，但按"组件的 TB 回写能力"去重后，**真正需完整改造的活路径约 48 处，死代码约 40+ 处（零消费的 FormData 重复定义 / J2 孤儿模块 / 零调用的共享工厂 / D4 残留监听器 / G6 变体端点 / H8 断链），另有 2 处假回写（K5/K7 只 emit 不写 TB）待产品决策**。采用用户拍板的**方案 B（逐组件改走显式发布端点 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`）**，而非在旧端点侧统一加门。改造须覆盖单科目、多科目、损益类发生额、形态 B（window CustomEvent）等各种形态，活路径完整改造、死代码删除收口，保留下游联动事件，最终收口旧端点并加 CI 守卫。

## Glossary

- **审定数（audited_amount）**：报表 / 审定表取数的权威字段；口径 = 未审数 + 账项调整(AJE) + 重分类调整(RJE)；损益类为直接给定的最终发生额。
- **绕过端点**：`PUT /api/projects/{project_id}/trial-balance/writeback`（旧的直写 TB 端点，无二次确认/无幂等）。
- **显式发布端点**：`POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（带 `publish_confirmed`+`publish_token` 的门控端点）。
- **回写 handler**：`_on_d_audit_determination_saved`，唯一有下游级联的 handler。
- **发布确认信号**：`WORKPAPER_SAVED` 事件 `extra` 中的 `publish_confirmed=True` + `confirmed_by` + `publish_token`。
- **形态 A / 形态 B**：composable 直调 `writebackTB` / 组件监听 window CustomEvent `{cycle}:writeback-trial-balance`。

## Requirements

### 需求 1：普通保存 / 双模式切换绝不写 TB

**用户故事**：作为审计人员，我希望日常保存底稿或切换编辑模式时不会意外改写报表底数，以免误触报表重算。

#### 验收标准

1. WHEN 任一 D~N 审定表组件执行普通保存（自动保存 / 手动保存 / debounce 保存）THEN 系统 SHALL 不修改 `trial_balance.audited_amount`。
2. WHEN 用户在 HTML ↔ OnlyOffice 之间切换双模式 THEN 系统 SHALL 不修改 `trial_balance.audited_amount`。
3. WHEN 普通保存发出 `WORKPAPER_SAVED` 事件 THEN 该事件 SHALL NOT 携带 `publish_confirmed=True`，且回写 handler SHALL 对 TB 为 no-op。

### 需求 2：审定数回写必须经显式用户确认

**用户故事**：作为审计人员，我希望把审定数发布到试算表是一个明确的、需二次确认的动作，以避免静默改写报表底数。

#### 验收标准

1. WHEN 用户在审定表组件触发"发布到试算表" THEN 系统 SHALL 弹出中文二次确认对话框（`ElMessageBox.confirm`），明示将写入 `trial_balance` 并触发下游报表 / 错报评价重算。
2. WHEN 用户取消二次确认 THEN 系统 SHALL 不发起任何回写请求、不 emit 任何联动事件、不修改 TB。
3. WHEN 用户确认发布 THEN 系统 SHALL 调用 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，SHALL NOT 调用 `PUT /api/projects/{project_id}/trial-balance/writeback`。
4. WHERE 组件此前经 window CustomEvent `{cycle}:writeback-trial-balance` 触发回写 THE 系统 SHALL 移除该 dispatch / listener 链，改由显式发布端点承载。

### 需求 3：服务端权限校验

**用户故事**：作为质控合伙人，我希望只有具底稿编辑权的人能把审定数发布到试算表，且服务端能独立验证，以防前端被绕过。

#### 验收标准

1. WHEN 发布请求到达 `publish-to-tb` 端点 THEN 系统 SHALL 经 `authorize_wp_edit`（review/edit 级）鉴权，对 qc/readonly/非成员 SHALL 返回 403。
2. IF 底稿所属项目处于合并锁定状态 THEN 系统 SHALL 返回 423 并拒绝回写。
3. WHEN 回写 handler 处理发布事件 THEN 系统 SHALL 用 `confirmed_by` 二次校验发布者具 `WORKPAPER_WRITE` 权限；IF `confirmed_by` 缺失或不可验证 THEN 系统 SHALL 拒绝回写。

### 需求 4：幂等与 durable ack

**用户故事**：作为审计人员，我希望重复点击"发布"不会把审定数写两次或重复触发下游级联。

#### 验收标准

1. WHEN 同一 `publish_token` 被投递多次 THEN 系统 SHALL 仅写一次 TB、仅级联一次（`tb_publish_ack` `publish_token` 唯一 + `ON CONFLICT DO NOTHING`）。
2. WHEN 前端未提供 `publish_token` THEN 端点 SHALL 由 `project/year/wp_code + 内容摘要` 合成稳定 token，使同一批数据重复提交共用同一 token。
3. WHEN 回写成功 THEN 系统 SHALL 在 `tb_publish_ack.accounts_updated` 回填实际更新行数供审计。

### 需求 5：多科目审定表回写

**用户故事**：作为审计人员，我希望多科目审定表（如 K1 应收+坏账准备、K6 资产+负债、H9 租赁负债+未确认融资费用）一次发布能正确写入全部相关科目。

#### 验收标准

1. WHEN 多科目审定表发布 THEN 系统 SHALL 在单次发布中回写全部相关科目，各科目对应各自审定数。
2. WHERE 科目码随项目动态变化（如 K6 取自 `tb_source_codes`）THE 系统 SHALL 由前端按当前项目解析科目码后透传，端点 SHALL NOT 硬编码科目。
3. WHEN 多科目发布幂等重放 THEN 每个科目 SHALL 最多被该次发布写一次。

### 需求 6：损益类发生额回写

**用户故事**：作为审计人员，我希望损益类发生额审定表（如 K12 科目 6301、K13 科目 6711）能把前端已算好的最终发生额直接发布，无需拆成未审+AJE+RJE 三分量。

#### 验收标准

1. WHEN 发生额形态组件发布 THEN 系统 SHALL 接受前端预算好的最终 `audited_amount`（`writeback_rows` 路径），SHALL NOT 强制从三分量重算。
2. WHERE 回写行为发生额 THE 请求 SHALL 可携带 `amount_kind="occurrence"` 语义标注，供审计日志区分。
3. WHEN 发生额发布落库 THEN 系统 SHALL 与余额类走相同的 `WORKPAPER_SAVED`（`publish_confirmed=True`）+ handler + 幂等路径。

### 需求 7：端点入参向后兼容扩展

**用户故事**：作为平台维护者，我希望扩展 `publish-to-tb` 端点以支持发生额/多科目预算行，同时不破坏 D4-1 已用的三分量路径。

#### 验收标准

1. WHEN 请求携带 `html_data.audit_rows`（原三分量形态）THEN 端点 SHALL 保持原有 `未审+AJE+RJE` 重算行为不变（D4-1 零回归）。
2. WHEN 请求携带 `writeback_rows`（预算行形态）THEN 端点 SHALL 直接以其构造 `parsed_data.rows`，跳过三分量重算。
3. WHEN 二者最终发布 THEN 端点 SHALL 产出结构一致的 `WORKPAPER_SAVED`（`publish_confirmed=True` + `confirmed_by` + `publish_token` + `parsed_data.rows`）。
4. IF `sheet_name` 无法经 `extract_determination_wp_code` 解出 `[D-N]{n}-1` THEN 端点 SHALL 返回 400 并拒绝发布。

### 需求 8：下游联动事件保留

**用户故事**：作为审计人员，我希望审定数发布后附注等下游模块仍能自动刷新，改造不能破坏既有联动。

#### 验收标准

1. WHEN 组件成功发布审定数 THEN 系统 SHALL 仍 emit `substantive:adjudicated`（携 accountCode/auditedAmount/wpCode/timestamp）。
2. WHERE 一个**真实被消费**的组件此前额外发服务端事件（如活路径的 `POST /events/publish` 或跨模块联动）THE 系统 SHALL 保留这些联动。（设计阶段 census 实证：J2 整个 composable 模块 `composables/workpaper/j2/` 是无渲染宿主 import 的孤儿链，其 `events/publish` + `actuarial:assumption-changed → B51` 均在死代码内，J2 真实宿主 `J2TabAdjudication.vue` 无 TB 回写；故 J2 按死代码清理处理，本条不适用于 J2。）
3. WHEN `substantive:adjudicated` 被 emit THEN 其下游消费方（附注 `useDisclosureSection` / `useL1DisclosureData` / F5-7 校验区）SHALL 继续正常刷新，行为不回归。
4. WHILE 改造移除 `{cycle}:writeback-trial-balance` listener THE 系统 SHALL 保留同组件注册的其他事件监听（如 `{cycle}:save-items`）。

### 需求 9：绕过端点迁移完成后收口

**用户故事**：作为平台维护者，我希望所有前端迁移完成后，旧的绕过端点不再被前端直调，且有 CI 守卫防止回潮。

#### 验收标准

1. WHEN 全部 D~N 组件迁移完成 THEN `audit-platform/frontend/src/**` 中 `trial-balance/writeback` 字面量命中数 SHALL 为 0；且 census 实证的 TB 回写变体端点（`useG6MainFormData` 用 `POST /api/projects/{pid}/trial_balance`）SHALL 一并清理，使其命中数亦为 0。
2. THE 系统 SHALL 提供 CI 守卫，断言前端源码中无 `trial-balance/writeback` 直调（并覆盖 `trial_balance` 变体端点直调）；新增直调 SHALL 使 CI 失败。
3. WHEN 前端零调用经 grep 确认且无服务内部合法调用方 THEN 系统 SHALL 删除或降级旧端点 `writeback_audited_amount`（降级为仅接受 `publish_confirmed` 内部调用或直接移除，由收口任务据实证决策）。

## 非目标（Out of Scope）

1. **不改 S 类独立回写服务**：`SEstimateTBWritebackService` / `STransactionTBWritebackService` 及其 router（`s_estimate_calculation` / `s_transaction_calculation`）与本 spec 正交，全程不触碰。
2. **不做端点侧统一加门**：用户明确选方案 B（逐组件改走显式端点），不在旧 `writeback_audited_amount` 端点内部加 `publish_confirmed` 门后让各 composable 照旧调用。
3. **不新造平台机制**：复用既有 `publish-to-tb` 端点、`_on_d_audit_determination_saved` handler、`tb_publish_ack`（V162）、`crossWpEventBridge`；不新增表、不新增事件类型。
4. **不改处置/函证等正交联动**：`disposal:completed` / `h1:disposal-completed` / 函证联动不在本 spec 范围。
5. **不实施本 spec 之外的口径修正**：审定数口径（正数口径、发生额取数）沿用现状，不借机重构。
