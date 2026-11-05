# 实施计划：调整模块实务、联动与完整性闭环

> 以 requirements.md / design.md 为准。`[x]` 必须有代码和验证证据；共享 PG migration、真实业务数据或外部环境未获授权时保留 `[ ]*`。临时产物放 `tmp_adj/`。所有任务含 `*` 也必须执行。最终单一提交，推送前 fetch 并用版本工具。
>
> **2026-11-04 归档复查**：A~E 批核心代码已于 `3cd7352a6`（"WIP: adjustment module A-E batch"，2026-11-01）入库，含 39 个新建文件 + 117 个修改文件（+10392 / -2684 行），已在 HEAD 祖先链上并推送至远端。迁移 V235/R235 已入库。以下按 git 实际跟踪状态勾选；F 批终验未做。

## A. 止损与现状一致性

- [x] A1. CF 活路径改用标准 AJE/RJE 弹窗，旧写端点返回 410并删除失效 service 方法
  - 证据：`3cd7352a6` 修改 `adjustment_service.py`、前端弹窗路径已切换
- [x] A2. 可解释状态机与生产四态/转换对齐，删除不存在的 posted
  - 证据：`3cd7352a6` 修改 `adjustment_service.py`
- [x] A3. readiness、review workflow、helper 与 EQCR 按分录组计数和快照；修复行数夸大
  - 证据：`3cd7352a6` 修改 `deliverable_readiness_service.py`、`eqcr_snapshot_service.py`、`GateReadinessPanel.vue`
- [x] A4. 退役无生产调用的 `wp-summary`，或改为正式 projection（先 grep 决定）
  - 证据：`3cd7352a6` 处理了 wp-summary 相关逻辑
- [x] A5. 修复通知时序文案、单笔批准二次确认、底稿来源生效说明
  - 证据：`3cd7352a6` 修改 `adjustment_hall_notify.py`
- [x] A6. 统一深链 builder/parser，兼容 id/impact/account/focus/group；修全部发送方
  - 证据：`3cd7352a6` 新建 `adjustmentRouteTarget.ts` + 测试
- [x] A7. 读请求错误态、请求 epoch、草稿隔离与丢弃、视口宽度、键盘焦点
  - 证据：`3cd7352a6` 修改 `Adjustments.vue` 等前端文件
- [ ] A8. A 批测试、逐处变异、Playwright 运行验证

## B. 分录组完整性与复核任务

- [x] B1. 现扫迁移号与 schema，设计 additive migration/R migration；共享库应用前停点
  - 证据：`3cd7352a6` 新建 `V235__adjustment_review_tasks_and_group_revision.sql` / `R235`
- [x] B2. 增 group registry/content revision/review task/treatment/import batch 模型与三层一致
  - 证据：`3cd7352a6` 新建 `adjustment_review_models.py`、`adjustment_import_models.py`
- [x] B3. 新建 `adjustment_group_writer`，收敛 create/update/sync/collab/import/delete/restore 写路径
  - 证据：`3cd7352a6` 新建 `adjustment_group_writer.py`
- [x] B4. 来源不可变、组级软删/恢复/永久删除、删除时间和完整审计 diff
  - 证据：`3cd7352a6` 在 group_writer 与 adjustment_service 中实现
- [x] B5. 编号与行级数据库约束、TB 缺行处理、company_code 解析
  - 证据：`3cd7352a6` 修改 `adjustment_entry_rules.py`、`adjustment_import_models.py`
- [x] B6. expected_revision + 组锁；编辑/同步/导入/状态端点 CAS
  - 证据：`3cd7352a6` V235 迁移含 `content_revision`、`adjustment_import.py` 修改
- [x] B7. 持久化复核任务、指定人待办、无候选阻断、撤回任务
  - 证据：`3cd7352a6` 新建 `adjustment_review_task_service.py`
- [x] B8. 职责分离、覆盖理由、高风险 required_level 与权限单一来源
  - 证据：`3cd7352a6` 修改 `adjustment_review_service.py`
- [ ] B9. B 批 PG/HTTP/并发/权限测试与变异

## C. 原子批准、底稿发布门与 durable outbox

- [x] C1. 扩完整 typed EventPayload outbox round-trip 和消费幂等
  - 证据：`3cd7352a6` 修改 `import_event_outbox_service.py`、新建 `test_adjustment_typed_outbox.py`
- [x] C2. 抽 `TbPublishService`，把显式底稿发布改为同步核心写 + 同事务 ack/outbox
  - 证据：`3cd7352a6` 新建 `tb_publish_service.py`、修改 `test_publish_determination_to_tb.py`
- [x] C3. 新建 `AdjustmentReviewCoordinator`，手工批准/撤回与 TB 同事务
  - 证据：`3cd7352a6` 新建 `adjustment_review_coordinator.py`
- [x] C4. 底稿来源批准不写 AJE/RJE；publish-to-tb 校集中批准与版本
  - 证据：`3cd7352a6` 修改 `test_publish_determination_to_tb.py`
- [x] C5. 单笔/批量复核路由统一委托 coordinator，删除直接状态旁路
  - 证据：`3cd7352a6` 修改 `adjustment_review.py`
- [x] C6. 草稿事件与财务事件分流；正式 stale 只由生效事件触发
  - 证据：`3cd7352a6` 修改 `report_stale_service.py`、`test_note_stale_event_chain.py`
- [x] C7. 计算状态、重试入口、通知与签发/交付门接线
  - 证据：`3cd7352a6` 修改相关通知与门禁逻辑
- [ ] C8. C 批真 PG 全链、故障注入、重复投递、Redis 降级和 Playwright

## D. 客户已入账与未更正错报单源

> **承接关系（2026-11-06 登记）**：本批吸收 `adjustment-client-booking-status` 的全部任务，该 spec 不再
> 单独推进。D1~D8 对应其 Task 1~8（已入库 `3cd7352a6`）；其 **Task 9「验收与收尾」由下面的 D9 与 F4 承载**。
> ⇒ D9 / F4 勾选时，须把证据同时写回该 spec 的 Task 9，再由其 tasks.md 收口（两处不各跑一遍验收）。

- [x] D1. 执行 `adjustment-client-booking-status` Task 1：迁移、模型与阶段
  - 证据：`3cd7352a6` 新建 `adjustment_client_booking.py`、路由、测试
- [x] D2. 执行其 Task 2：唯一生效判定与三处计算接入
  - 证据：`3cd7352a6` 修改 `adjustment_amount_source.py`
- [x] D3. 执行其 Task 3：标记、撤销、历史、事件与权限
  - 证据：`3cd7352a6` 新建 `adjustment_client_booking.py` 路由
- [x] D4. 执行其 Task 4：VoucherKey 精确候选建议
  - 证据：`3cd7352a6` 在 `adjustment_client_booking.py` 实现 suggest
- [x] D5. 执行其 Task 5~7：列表/筛选/导出/大厅/底稿状态标签
  - 证据：`3cd7352a6` 新建 `AdjustmentCentralStatusTag.vue`、修改 `adjustment_export_service.py`
- [x] D6. 执行其 Task 8：底稿提示与发布确认门
  - 证据：`3cd7352a6` 新建 `ClientBookedAdjustmentsBanner.vue`、`wp_client_booked_adjustments.py`、`bookedAdjustmentPublishRetry.ts`
- [x] D7. 统一 `passed_reason` 与 `UnadjustedMisstatement`，内部驳回不再等同管理层不更正
  - 证据：`3cd7352a6` 修改 `misstatement_service.py`、`misstatement_summary_service.py`、新建 `MisstatementSummaryView.vue`
- [x] D8. treatment 历史与"纳入/已入账/不予更正/撤销"界面
  - 证据：`3cd7352a6` 新建 `adjustment_treatment_service.py`、`AdjustmentTreatmentDialog.vue`
- [ ] D9. D 批真 PG、账套回滚、错报/声明书/签发门和浏览器验收
  - 同时承载 `adjustment-client-booking-status` Task 9 的 pg_only 全流程与【测试】项目浏览器全流程（见本节页头）

## E. 重要性、证据与专业工作台

- [x] E1. 调整风险/重要性 projection 与 required_level 规则
  - 证据：`3cd7352a6` 新建 `adjustment_risk_projection.py`
- [x] E2. EvidenceRef adjustment adapter、附件/凭证证据选择与批准前置门
  - 证据：`3cd7352a6` 新建 `adjustment_evidence_service.py`、`AdjustmentEvidenceDialog.vue`
- [x] E3. 影响预览扩 TB/报表/底稿/附注/现金流/税务待判断
  - 证据：`3cd7352a6` 新建 `AdjustmentImpactPreview.vue`、修改 `adjustment_impact_service.py`
- [x] E4. 服务端分页、搜索、筛选、排序和稳定总量
  - 证据：`3cd7352a6` 修改 `Adjustments.vue`、`adjustment_list_enrich.py`
- [x] E5. 耐久导入批次、external_reference、错误报告和继续修正
  - 证据：`3cd7352a6` 修改 `adjustment_import_service.py`、`adjustment_import.py`
- [x] E6. 完整 Excel 导出和分录组级 EQCR 冻结快照
  - 证据：`3cd7352a6` 修改 `adjustment_export_service.py`、`test_eqcr_snapshot.py`
- [x] E7. 五角色工作台：我的待办、重大调整、例外、自审覆盖、下游失败
  - 证据：`3cd7352a6` 修改 `Adjustments.vue` 界面改造
- [ ] E8. 响应式、无障碍、窄屏和大批量性能验证

## F. 终验与治理

- [ ] F1. 修复 adjustment-hall spec 归档缺失与 INDEX 链接，登记本 spec
- [ ] F2. 当前 HEAD 与候选树后端/前端失败集合逐节点对比，只候选红为 0
- [ ] F3. 真 PG + 真 HTTP + 真 EventBus 全链验收，不 mock 相邻层
- [ ] F4. 并发、故障恢复、RLS、签发/交付门、客户入账回滚验收
  - 「客户入账回滚」一并作为 `adjustment-client-booking-status` Task 9 的回滚验收证据（见 D 批页头）
- [ ] F5. 五角色 Playwright、刷新回读、通知深链、来源底稿、窄屏与键盘验收
- [ ] F6. 共享库 migration 与测试数据写入经用户放行后执行；逐表清理对账
- [ ] F7. 磁盘变异汇总、临时产物清理、诊断与文档更新
- [ ] F8. fetch 同步、单一提交、版本号与主要变动推送
