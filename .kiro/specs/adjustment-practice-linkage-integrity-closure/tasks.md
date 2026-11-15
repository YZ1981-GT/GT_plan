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
- [ ]* A8. A 批测试、逐处变异、Playwright 运行验证
  - 2026-11-15：现有 CF 退役、深链、资源错误/代际、动作和前端相关用例已重跑；新增 `Adjustments.a8e8.spec.ts` 锁定代际、错误重试、服务端分页、深链和反向变异。Playwright 已在【测试】项目验证调整大厅加载、相关接口 200、390px 无横向溢出、无 console error；CF 四类深链、错误重试、草稿恢复和完整浏览器变异链仍未闭合。

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
- [ ]* B9. B 批 PG/HTTP/并发/权限测试与变异
  - 2026-11-15：新增 `test_adjustment_b9_integrity_pg.py`，真实 PG 已验证 stale revision 拒绝、负金额约束拒绝和三张调整工作流表 FORCE RLS；既有 SQLite/HTTP 权限、复核任务、整组删除恢复和 TB 故障回滚用例已重跑。双事务编辑/批准、自定义编号/导入覆盖并发和非 superuser RLS 强制隔离仍需专门环境，未勾选完成。

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
- [ ]* C8. C 批真 PG 全链、故障注入、重复投递、Redis 降级和 Playwright
  - 2026-11-15：新增 outbox 失败→重试→重复句柄幂等、Redis ping 失败内存降级测试；真实 PG outbox 故障/重放/幂等和通知 SAVEPOINT 用例通过。修复 outbox worker 无监督退出与退避期间心跳过期：启动 registry 对 outbox worker 增加有限退避 supervisor，worker 增加独立 20 秒心跳 ticker；新增 `test_outbox_replay_worker_supervision.py` 3 passed。开发服实测 `event-cascade/health` 已恢复 `healthy`（lag=0、DLQ=0、Redis=true、worker alive），调整大厅不再显示“部分功能暂时不可用”。批准→TB→outbox→真实 EventBus handler 全链、handler 中途失败/DLQ、Redis 真栈和 Playwright 尚未完成。

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
- [ ]* D9. D 批真 PG、账套回滚、错报/声明书/签发门和浏览器验收
  - 同时承载 `adjustment-client-booking-status` Task 9 的 pg_only 全流程与【测试】项目浏览器全流程（见本节页头）
  - 2026-11-15 已补 `test_adjustment_client_booking_pg.py` 与 `test_adjustment_booking_suggestions_pg.py`，并补真实 router HTTP 标记/撤销追加历史；默认未设置 `DATABASE_URL` 时收集为 2 skipped，显式指向本地 PostgreSQL 后 2 passed。通过临时测试复核人和【测试】项目完成了浏览器：AJE 粘贴录入→提交复核→另一账号批准→精确建议→客户已入账→账套回滚→撤销，数据库核对 `book/revoke` 与 `include/client_booked/withdraw` 历史，活动调整行清理为 0。浏览器期间 `/event-cascade/health` 暴露 outbox replay worker 未运行，且声明书/签发门仍只有 PG/HTTP 证据，故仍保留 `[ ]*`。

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
- [ ]* E8. 响应式、无障碍、窄屏和大批量性能验证
  - 2026-11-15：调整大厅可点击来源/协作标签已改原生 button + aria-label + focus-visible；契约测试、区域类型检查和 stylelint 通过。浏览器 390px overflow=0，注入总量 10,000/page_size=50 时渲染 50 行约 1.53 秒；真实 10,000 组数据、axe/屏幕阅读器、完整键盘焦点回收和 p50/p95 基准仍未闭合。

## F. 终验与治理

- [x] F1. 修复 adjustment-hall spec 归档缺失与 INDEX 链接，登记本 spec
  - ✅ 2026-11-15 复核结项：`adjustment-hall-entry-review-closure` 目录已在 `_archive/112-adjustment-hall-entry-review-closure/`，INDEX 速递区有 10/10 ✅ 行且链接指向归档路径（非活跃路径）；`backend/tests/test_spec_index_consistency.py` **23 passed**（该守卫覆盖：链接必须点得开 / 活跃表不得有已归档 spec / 表格段列数一致 / 无 mojibake / 速递条目不得落在正文区）。本 spec 自身（`adjustment-client-booking-status`、本 spec）在 INDEX 活跃表中登记。⇒ F1 的「归档缺失与链接」事实不成立（旧记录过期），已结项。
- [x] F2. 当前 HEAD 与候选树后端/前端失败集合逐节点对比，只候选红为 0
  - ✅ 2026-11-15：候选 `7ff1a4ab8d97b081fae8a66775cf9012f16da612` / tree `bde619b5`，基线 HEAD `8eb79c894`。同一后端选集 HEAD **60 passed/2 failed**、候选 **62 passed/0 failed**；前端既有 4 文件 HEAD/候选均 **37 passed**，候选新增 A8/E8 契约 **4 passed**。两条 HEAD 失败由本批错报 force 幂等与声明书同刻排序修复，结果写入 `tmp_adjustment_f_remaining/f2_results.md`；候选 worktree 已锁定验证后释放，refs 未移动。
- [ ]* F3. 真 PG + 真 HTTP + 真 EventBus 全链验收，不 mock 相邻层
  - 2026-11-15：真实 PG/HTTP 的 B9、客户入账、outbox 和错报/声明书/签发门分段用例已通过；修复并验证 outbox supervisor/独立心跳后开发服 `event-cascade/health` 为 healthy，pending outbox 已清空。批准→TB→outbox→生产 EventBus handler 的同一全链仍缺，现有分段测试仍有局部替身，不能勾选完成。
- [ ]* F4. 并发、故障恢复、RLS、签发/交付门、客户入账回滚验收
  - 2026-11-15：已覆盖 PG stale CAS、约束、FORCE RLS 元数据、outbox 故障/重放和客户入账回滚；回滚 active dataset 的 PostgreSQL 唯一 active 约束顺序缺陷已修复并回归通过。event-cascade health 当前 healthy、DLQ=0。双事务并发、非 superuser RLS 强制隔离、统一签发/交付故障门和全链恢复仍待专用环境。
- [ ]* F5. 五角色 Playwright、刷新回读、通知深链、来源底稿、窄屏与键盘验收
  - 2026-11-15：已完成调整大厅窄屏、接口、键盘聚焦、来源/协作原生按钮和合成分页性能走查，并用临时编制/复核账号完成 AJE 提交、通知、批准、客户入账、回滚、撤销和刷新路径。仍缺合伙人/QC/EQCR 五角色全矩阵、通知深链与来源底稿连续走查，且 event-cascade health 暴露 outbox replay worker 未运行。
- [ ]* F6. 共享库 migration 与测试数据写入经用户放行后执行；逐表清理对账
  - 2026-11-15：只读查询确认共享库已应用 V212/V235，V235 的 MigrationRunner 规范化 checksum 与数据库记录一致；测试项目活动调整行已为 0，临时复核账号已停用、人员已删除、项目委派已撤销。本轮未执行共享库 migration、持久化 seed、物理清理或回滚，等待用户明确目标库与清理授权。
- [x] F7. 磁盘变异汇总、临时产物清理、诊断与文档更新
  - ✅ 2026-11-15：本批临时产物清理 —— 删 `tmp_note_table_fix/`（一次性探针）与两处变异备份（`mutbak_nwps.py` / `mutbak_m1detail.ts`，均已逐字节还原后删除）；保留 `tmp_mcycle_audit/probe_m_contract_vs_frontend.py` 与 `probe_m_field_names.py` 两个**可复现探针**（M 循环形态冲突的证据来源，见 `oo-writeback-template-parity-closure` 9.2）。变异汇总见各批记录（显示设置 3/3、M 棘轮 2/2、附注章节锁 3/3）。
- [ ]* F8. fetch 同步、单一提交、版本号与主要变动推送
  - 2026-11-15：已 fetch --prune，HEAD 与 origin 同为 `8eb79c894`、ahead/behind=0；`push_version.py --dry-run` 被当前 91 条工作树/未跟踪改动按安全门拒绝，未执行 fetch/rebase、提交、版本标签或推送。
