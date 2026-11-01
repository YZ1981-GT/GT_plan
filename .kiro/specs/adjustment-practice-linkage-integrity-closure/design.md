# 设计文档：调整模块实务、联动与完整性闭环

## 1. 设计原则

1. **会计事实优先。** `approved` 不能只是状态字段；对手工分录，它必须与 TB 调整列同事务成立。
2. **来源分工不等于双重生效。** 手工分录写 AJE/RJE，底稿来源经显式发布写 `wp_adjustment`，但两者都受集中复核约束。
3. **业务状态与派生状态分开。** review、treatment、calculation 各自建模。
4. **分录组是一等实体。** 所有锁、权限、恢复、审计、任务和导出以 `entry_group_id` 为单位。
5. **关键写同步，非关键派生耐久异步。** TB 属批准语义；报表/附注/公式属可重试下游。
6. **复用平台组件。** VoucherKey、EvidenceRef、AttachmentVersion、durable outbox、项目门禁和合并锁均复用现有实现。

## 2. 现状确认

| 事实 | 当前实现 | 结论 |
|---|---|---|
| 手工批准 | 状态 commit 后 best-effort 发 `ADJUSTMENT_APPROVED` | 存在批准成功但 TB 未更新窗口 |
| 底稿来源 | 集中重算排除 `origin=workpaper`，底稿发布写 `wp_adjustment` | 保留四分量，但发布门需校集中复核 |
| EventBus | debounce；handlers 后才写 Redis Stream | 不能作为业务事务 outbox |
| 分录模型 | `adjustments` 与 `adjustment_entries` 双写行数据 | 先加组级封装和约束，后做头表迁移 |
| reviewer_ids | 只发通知 | 需持久任务 |
| 客户已入账 | spec 已有，0/9 | 在基础设施后实施 |
| 证据 | 无 adjustment adapter | 扩 EvidenceRef typed adapter |
| CF 快捷创建 | 使用不存在的 enum/字段/状态 | 立即下线写端点，改开标准弹窗 |

## 3. 目标状态模型

### 3.1 Review task

新增 `adjustment_review_tasks`：

- `id, project_id, year, entry_group_id`；
- `status ∈ pending/approved/rejected/withdrawn/stale`；
- `required_level ∈ manager/partner`；
- `revision`；
- `group_content_revision`；
- `assigned_reviewer_ids JSONB`；
- `submitted_by/submitted_at/decided_by/decided_at`；
- `submit_note/decision_reason/self_review_override_reason`；
- `is_deleted/deleted_at/created_at/updated_at`。

同一分录组最多一个 active pending task。批准时锁 task 和分录组，核对版本。

### 3.2 Financial treatment

新增追加式 `adjustment_treatment_events`：

- action：`include_in_working_tb/client_booked/unadjusted_misstatement/withdraw`；
- `entry_group_id, project_id, year`；
- `dataset_id, voucher_keys, misstatement_id`；
- `reason, created_by, created_at`。

当前处理状态由最新事件派生。客户已入账可沿用既有 `adjustment_client_bookings` 设计；最终由统一 facade 输出 treatment projection，避免调用方分别解释两张表。

### 3.3 Calculation state

新增 `adjustment_calculation_runs` 或复用 outbox 聚合投影：

- `entry_group_id, trigger, status, account_codes`；
- `tb_committed_at, downstream_status, last_error, retry_count`；
- `outbox_ids`。

首批允许以 outbox + `tb_committed_at` 读时聚合，不急于新建独立状态表。

## 4. ADR

### ADR-ADJC-001：CF 差异不自动造会计分录

`CfMainTable` 打开 `AdjustmentEntryDialog`，只预填摘要和来源提示。旧写端点返回 410。理由：只有差异金额无法安全推断借贷科目。

### ADR-ADJC-002：先组级封装，后迁移真正头表

本轮先给 `Adjustment` 增 `content_revision`，建立 `adjustment_group_writer.py`，所有写路径统一调用。数据库约束覆盖可表达的不变量。真正 `adjustment_groups` 头表作为迁移后半段，只有全部读取方切到统一 projection 后再启用，避免大爆炸替换。

### ADR-ADJC-003：批准必须基于任务和 CAS

提交创建 task；批准请求带 task id、task revision、group content revision。无任务、任务过期、非指定复核人、自审无覆盖理由均 409/403。普通经理任务完成即批准；partner 级任务需要合伙人完成。

### ADR-ADJC-004：手工批准与 TB 同事务

`AdjustmentReviewCoordinator.approve_manual()`：

1. 锁 task、组行和受影响 TB 行；
2. 校验版本、权限、职责分离、证据和高风险层级；
3. 状态改 approved；
4. `recalc_adjustments` + `recalc_audited`；
5. 逐科目核对 TB 行都存在；
6. 写通知、审计和 durable outbox；
7. router commit；
8. commit 后 publish pending。

任何步骤失败整笔回滚。

### ADR-ADJC-005：底稿来源批准是发布前置，不直接写 TB

`origin=workpaper` 仍排除于 AJE/RJE。批准只完成集中复核。`publish_determination_to_tb` 根据 `wp_id + 发布科目` 查相关 active workpaper 分录组；存在未批准或版本已变化的组则 409。校验通过后继续使用 `tb_audited_writer.publish_rows()` 计算 `wp_adjustment`。

这是兼容现有四分量模型的最小改法。后续统一账簿时再消除本地金额副本。

### ADR-ADJC-006：TB 发布改同步核心写 + outbox

从 WORKPAPER_SAVED handler 抽出 `TbPublishService.apply()`：权限与载荷在 router 校验，ack、`publish_rows` 和 outbox 在同事务；响应只有实际写完才 `published=true`。旧事件 handler 保留兼容，识别 `tb_write_committed=true` 后不重复写。

### ADR-ADJC-007：完整 typed outbox

扩 `DurableEventOutboxService.enqueue_event(EventPayload)`，payload 使用版本化 envelope 保存 EventPayload 全字段。`ImportEventOutboxService._deliver` 完整恢复，不把 `account_codes` 塞进 `extra`。旧 `enqueue` 保持兼容。

对调整链使用消费幂等键：

- `adjustment.approved:entry_group_id:revision`；
- `adjustment.review_revoked:entry_group_id:revision`；
- `trial_balance.updated:project:year:calculation_run`。

### ADR-ADJC-008：草稿事件与财务事件分流

`ADJUSTMENT_CREATED/UPDATED/DELETED` 只刷新大厅、待办、影响预览和来源状态；不标正式输出 stale。正式 stale 只订阅 approved/revoked/client-booking-changed/TB-updated。

### ADR-ADJC-009：未更正错报只认正式记录

新转换入口允许“复核通过后选择不予更正”，创建 `UnadjustedMisstatement` 并写 treatment event。旧 `passed_reason` 读取方迁移到统一 misstatement service；完成后列只作历史兼容。

### ADR-ADJC-010：重要性与证据驱动复核

风险判定服务输出：

- 金额与明显微小/执行/整体重要性比值；
- 规则标志：收入、关联方、管理层凌驾、估计、期末手工、异常凭证；
- required_level；
- evidence_required。

不能自动判断税务和现金流时输出待判断项，不伪造结论。

## 5. 关键服务

### 5.1 `adjustment_group_writer.py`

统一 create/replace/soft_delete/restore：

- 组级锁和版本；
- 头/明细双写；
- 来源字段保护；
- 删除时间与操作者；
- 组完整性检查；
- 写审计 diff；
- 不 commit、不直接发 EventBus。

### 5.2 `adjustment_review_task_service.py`

提交、撤回、候选复核人、待办、任务过期。指定人是授权与待办依据，不再只是通知名单。

### 5.3 `adjustment_review_coordinator.py`

唯一批准/驳回/撤回复核入口。单笔与批量路由都委托它。批量保留逐笔 SAVEPOINT，但每笔的“状态 + TB + 通知 + outbox”不可拆。

### 5.4 `tb_publish_service.py`

抽取现有 publish-to-TB handler：

- `validate_workpaper_adjustments_approved`；
- `publish_rows`；
- `tb_publish_ack`；
- `TRIAL_BALANCE_UPDATED` outbox；
- 返回逐科目 updated/skipped，任何预期科目 skip 时 fail closed。

### 5.5 `adjustment_projection.py`

列表、导出、readiness、EQCR、签发门和底稿状态统一使用组级 projection，禁止各自 `min()` 或按行计数。

## 6. 数据库设计

迁移号实施时按 `max(磁盘含未跟踪, 共享库 schema_version) + 1` 获取。

首个 additive migration：

- `adjustments.content_revision INTEGER NOT NULL DEFAULT 1`；
- `adjustment_review_tasks`；
- `adjustment_treatment_events`；
- `adjustment_import_batches`；
- active 编号唯一索引，可通过组投影辅助表或 trigger 实现；
- `adjustment_entries(entry_group_id, line_no)` active 唯一；
- 借贷金额 CHECK；
- 必要的项目/年度/状态索引；
- RLS 与 rollback migration。

若直接在重复行表上无法安全表达“编号按组唯一”，则先建轻量 `adjustment_group_registry(entry_group_id PK, project_id, year, adjustment_no, origin, source_ref, content_revision, ...)`，由 writer 维护；它同时成为后续完整头表迁移起点。

## 7. 前端设计

### 7.1 权限

`HallPerms` 扩为独立动作能力，不再用 `writable` 先整体短路 review。项目归档、合并锁和 calculation pending 是独立状态。

### 7.2 列表与待办

服务端 query 支持筛选、排序、游标或稳定分页。顶部区分：

- 分配给我的复核；
- 团队待复核；
- 已批准但下游失败；
- 疑似客户已入账；
- 待形成最终处理。

### 7.3 录入和批准

录入显示重要性、影响和证据。批准弹窗展示 before/after TB、受影响报表行、来源、证据、风险和自审检查。底稿来源显示“批准后允许来源底稿发布”，不再声称立即计入。

### 7.4 错误与恢复

每类读请求使用 `{status, data, error, lastSuccessAt, requestEpoch}`。旧响应按 project/year/epoch 丢弃。草稿按上下文分 key，关闭时明确保存或丢弃。

### 7.5 深链

建立 `adjustmentRouteTarget.ts` 统一 build/parse，兼容旧 `id`；所有发送方只调用 builder。`impact` 定位后自动打开影响弹窗。

## 8. 迁移与兼容

1. 存量 workpaper 分录不自动补发 TB。其已发布状态保持；下一次内容变化或重新发布时进入新门。
2. 存量无 task 的 pending_review 分录生成 legacy task，候选复核人为空时标 `needs_assignment`，不自动批准。
3. `passed_reason` 存量生成 misstatement 候选报告，人工确认后迁移，不自动创建正式错报。
4. 旧 API 在一个兼容期内返回 410 或薄委托，不保留第二条写路径。
5. 所有 migration 都有 R 文件；共享库写入前停点征得用户放行。

## 9. 测试策略

- 单元：金额、组 projection、状态真值表、风险路由、深链、草稿 key。
- SQLite 真 HTTP：权限、状态、错误信封、批量部分成功。
- PG 回滚事务：锁、CAS、约束、RLS、原子批准、publish ack、客户入账。
- durable outbox：完整 payload、失败重试、重复投递、DLQ。
- 变异：移除 source guard、版本检查、TB 原子调用、client booking 条件、evidence gate、distinct group 均应见红。
- Playwright：五角色、刷新回读、通知深链、底稿门、并发冲突、窄屏和键盘。

## 10. 交付分批

A. 止损与可见一致性；B. 组完整性与 review task；C. 原子批准与底稿发布门；D. 客户已入账与错报；E. 重要性证据与工作台；F. 全链验收与迁移。每批完成后持续进入下一批，不因分批而等待人工确认；只有共享 PG migration、真实业务数据写入或产品裁决冲突才停。
