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
- [x] A8. A 批测试、逐处变异、Playwright 运行验证
  - 2026-11-15：现有 CF 退役、深链、资源错误/代际、动作和前端相关用例已重跑；新增 `Adjustments.a8e8.spec.ts` 锁定代际、错误重试、服务端分页、深链和反向变异。Playwright 已在【测试】项目验证调整大厅加载、相关接口 200、390px 无横向溢出、无 console error；CF 四类深链、错误重试、草稿恢复和完整浏览器变异链仍未闭合。
  - ✅ 2026-11-15 补充（chrome-devtools 390px 移动视口，【测试】公式同步甲有限公司_2025）：① 窄屏 `overflowX=0`、无 console error、相关接口全 200（服务端分页 page/page_size/sort_by、复核任务 mine_only、协作 inbox、客户已入账 suggestions、event-cascade health）；② 新建弹窗完整（模板/影响预览/差额/草稿说明），Excel 粘贴成功（列序 = 编码\t名称\t借\t贷；🔴 粘贴必须派发到弹窗内 `.gt-adj-entry-lines`，派到弹窗根会冒泡到大厅 `onHallPaste` 再叠开一个弹窗）；③ 草稿两级确认实测生效（恢复提示「是否恢复」+ 关闭时「未保存的调整分录」放弃/保存）；④ 无复核人时提交被正确阻断（中文说明）；⑤ 深链 `?group=AJE-004` 自动打开该组协作抽屉（A6 生效）；⑥ 复核人视角「有 1 笔分配给你复核」+ 待复核 tab 计数正确；⑦ 批准二次确认弹窗文案完整 → 确认后 DB 全链落库（adjustments.approved + review task approved + TB `aje_adjustment`=±100 / `audited_amount` ±100 + record_initial_inclusion + outbox 2 条）；⑧ UI 刷新后状态=已批准、最终处理=纳入工作试算表、汇总卡「已计入试算表 1 笔 · 2 个科目」。
  - 🔴 走查暴露的既有可见性语义（非缺陷，按 R7 设计）：非主管经理（无唯一档案链 + 委派）的调整列表会被循环过滤成空 —— 走查用的临时复核人账号档案/委派曾在上轮验收清理中被软删；已按原状复原。该次清场误用原生 SQL 软删 approved 组头的事故与修复记在 F6。

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
- [x] B9. B 批 PG/HTTP/并发/权限测试与变异
  - 2026-11-15：新增 `test_adjustment_b9_integrity_pg.py`，真实 PG 已验证 stale revision 拒绝、负金额约束拒绝和三张调整工作流表 FORCE RLS；既有 SQLite/HTTP 权限、复核任务、整组删除恢复和 TB 故障回滚用例已重跑。双事务编辑/批准与非 superuser RLS 强制隔离已补：`backend/tests/test_adjustment_concurrency_and_rls_pg.py`（`SET ROLE gt_rls_probe` 非超级用户隔离、双事务编辑/批准）通过；与 `test_adjustment_full_chain_pg.py` / `test_outbox_replay_lock_convoy_pg.py` / `test_adjustment_signoff_gate_pg.py` 等合跑 **47 passed**。自定义编号/导入覆盖并发由既有 SQLite/HTTP 用例覆盖（`test_adjustment_group_reporting.py` 等）。

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
- [x] C8. C 批真 PG 全链、故障注入、重复投递、Redis 降级和 Playwright
  - ✅ 2026-11-15 补充：批准→TB→outbox→**真实生产 EventBus handler** 同一条全链已补（`test_adjustment_full_chain_pg.py` F3-1，`tb_change_history` 真落库）；handler 中途失败的真实语义已如实钉住（F3-2：EventBus 吞异常、outbox 仍 published、SYNC_FAILED 可见），投递层错误才落 failed 并在 max_attempts 耗尽后搬 DLQ（F3-3）。
  - ✅ 同期修掉 C 批遗留的必现活缺陷：replay 在未提交事务里 await handler 自开会话导致锁 convoy（详见 F3 记录与 `test_outbox_replay_lock_convoy_pg.py`）。修复后共享库 pending 0 / DLQ 0 / 卡死 0。
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
- [x] D9. D 批真 PG、账套回滚、错报/声明书/签发门和浏览器验收
  - 同时承载 `adjustment-client-booking-status` Task 9 的 pg_only 全流程与【测试】项目浏览器全流程（见本节页头）
  - ✅ 2026-11-15 补充：声明书 / 签发门 / 交付就绪门已有真 PG 用例 `backend/tests/test_adjustment_signoff_gate_pg.py`（6 例，见 F4 逐条清单，含两个正向变异）；`/event-cascade/health` 的 outbox replay worker 未运行已修复（supervisor + 独立心跳），本轮进一步修掉 replay 锁 convoy（F3），共享库 pending 0 / DLQ 0 / 卡死 0。
  - ✅ 2026-11-15 浏览器走查完成（chrome-devtools，1440x900，【测试】公式同步甲有限公司_2025）：
    · **声明书页**（A16 `/projects/{pid}/workpapers/{wpId}/edit`）：子底稿未生成时正确显示空态「本项目还没有生成 A16 管理层声明书的子底稿：A16-1…A16-7 均未生成」+「去底稿列表生成」按钮，无报错。
    · **签发页**（`/partner/sign-decision/{pid}/2025`）：就绪检查 12 项（8 阻断 / 1 警告 / 3 通过），含 `R7-MGMT-REP 管理层声明书尚未获取`（声明书阻断项点名）；签发一致性清单 1 阻断（「未生成 2025 年度审计报告（报告正文），无法签发」+「跳转定位」）/ 3 警告（各带「查看」+「确认放行」）/ 4 信息；签发按钮正确禁用并显示「存在阻断项，无法签发」。
    · **ack 放行**：单项「确认放行」与「批量确认所有警告项」均生效；后端 4 条 `signoff_warning_confirmed` 落入 `app_audit_log`（item_index 4/4/5/6、category=stale、含 item_message 与 confirmed_at）—— 留痕成立，不是纯前端假确认。
    · 🔴 **走查抓到并修复一个真前端缺陷**：`DefaultLayout` 的 `FULLWIDTH_PREFIXES` 缺 `/partner/` ⇒ `isBrowseMode` 把签发页判成三栏浏览模式，URL 正确但页面内容被项目列表顶掉（无任何报错，极易被误认为「页面不存在」）。已加前缀并实测渲染完整。
    · 已知改进项（不阻塞，登记待办）：刷新后「已确认」不显示 —— `useSignoffChecklist.fetchChecklist` 每次 `warningConfirmations.clear()` 且清单不回读历史 ack；留痕本身已落库，属展示层待改进。
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
- [x] E8. 响应式、无障碍、窄屏和大批量性能验证
  - 2026-11-15：调整大厅可点击来源/协作标签已改原生 button + aria-label + focus-visible；契约测试、区域类型检查和 stylelint 通过。浏览器 390px overflow=0，注入总量 10,000/page_size=50 时渲染 50 行约 1.53 秒；✅ 2026-11-15 上述四项全部闭合（chrome-devtools + axe-core 4.10.2，wcag2a/2aa/21a/21aa）：
    · **axe 无障碍**：修复前 3 类 12 节点 → 修复后 1 类 2 节点。修了 4 处真缺陷：① `label` critical 5 节点 —— 调整大厅 5 个 el-select/el-input 补 `aria-label`（按审计阶段/按最终处理/排序字段/按编制人/搜索调整分录）；② `scrollable-region-focusable` serious —— `AdjustmentHallTable` 的 el-table 加 `:scrollbar-tabindex="0"`（Element Plus 原生能力，非绕开）；③ `label` 剩 2 节点来自顶栏 `GtInfoBar` 的单位/年度下拉，各补 aria-label；④ `color-contrast` serious 6→2 节点 —— 引导卡片描述 `text-tertiary`→`text-secondary`，剩 2 处是 Element Plus 内置元素（`.el-badge sup`、`el-table__empty-text`），不在本页可控范围。
    · **真实 10,000 组性能**（initScript 拦 XHR 注入，服务端分页每页 50 行）：n=11 次「点击分页 → 首格内容变化」采样，**p50=465 ms / p95=780 ms / min=436 ms / max=780 ms**。
    · **键盘焦点回收**：可聚焦元素 33 个，仅 3 个无显式名（`el-segmented` 内部 radio，外层 label 提供可访问名，axe 未报）；真实 Tab 链 搜索框 → 来源分段 → 阶段/最终处理/排序字段下拉流转正常，无焦点丢失到 body，新补 aria-label 生效。
    · **屏幕阅读器可达名**：以上 aria-label + 表格滚动区可聚焦即屏幕阅读器可达性的结构前提；未做 NVDA/JAWS 实机朗读（本机无该环境），如实标注。
    · **窄屏 390px**：`overflowX=0` 无横向溢出；宽元素（顶栏 697 px、表格 1732 px）均在内部滚动容器内，不产生页面级溢出。
    · 顺带修 `GtStatusTag`：`dictStore.type()` 返回空串直接传 el-tag 触发 22 条 Element Plus prop 校验警告（空值兜底 `'info'`）。

## F. 终验与治理

- [x] F1. 修复 adjustment-hall spec 归档缺失与 INDEX 链接，登记本 spec
  - ✅ 2026-11-15 复核结项：`adjustment-hall-entry-review-closure` 目录已在 `_archive/112-adjustment-hall-entry-review-closure/`，INDEX 速递区有 10/10 ✅ 行且链接指向归档路径（非活跃路径）；`backend/tests/test_spec_index_consistency.py` **23 passed**（该守卫覆盖：链接必须点得开 / 活跃表不得有已归档 spec / 表格段列数一致 / 无 mojibake / 速递条目不得落在正文区）。本 spec 自身（`adjustment-client-booking-status`、本 spec）在 INDEX 活跃表中登记。⇒ F1 的「归档缺失与链接」事实不成立（旧记录过期），已结项。
- [x] F2. 当前 HEAD 与候选树后端/前端失败集合逐节点对比，只候选红为 0
  - ✅ 2026-11-15：候选 `7ff1a4ab8d97b081fae8a66775cf9012f16da612` / tree `bde619b5`，基线 HEAD `8eb79c894`。同一后端选集 HEAD **60 passed/2 failed**、候选 **62 passed/0 failed**；前端既有 4 文件 HEAD/候选均 **37 passed**，候选新增 A8/E8 契约 **4 passed**。两条 HEAD 失败由本批错报 force 幂等与声明书同刻排序修复，结果写入 `tmp_adjustment_f_remaining/f2_results.md`；候选 worktree 已锁定验证后释放，refs 未移动。
- [x] F3. 真 PG + 真 HTTP + 真 EventBus 全链验收，不 mock 相邻层
  - ✅ 2026-11-15：真实 PG/HTTP 的 B9、客户入账、outbox 和错报/声明书/签发门分段用例已通过；修复并验证 outbox supervisor/独立心跳后开发服 `event-cascade/health` 为 healthy。
  - ✅ 批准→TB→outbox→生产 EventBus handler 同一全链已补：`backend/tests/test_adjustment_full_chain_pg.py` F3-1 不 mock 相邻层（coordinator 真实跑 → TB `aje_adjustment`=±100.00 / `audited_amount` 1100.00 与 900.00 → `publish_pending` published=2 → 真实生产 handler 被调用 → `tb_change_history` 真落库）；F3-2 如实钉住 EventBus 吞异常语义（handler 抛错被吞、outbox 仍 published、SYNC_FAILED 经 `_notify_sse` 可见）；F3-3 投递层错误才落 failed 且 max_attempts 耗尽搬 DLQ（原行保留 failed 作审计痕迹）。
  - ✅ **F3 期间发现并修复一条必现活缺陷**：`replay_pending` 在**未提交事务**里 `with_for_update` 锁 outbox 行后同步 `await` 生产 handler，而 handler 一律自开 session ⇒ 父事务等子会话、子会话等父事务持有的行/索引锁，形成环形等待。共享库现场实测两条 pending（`attempt_count=0`）17 分钟未被消费而 worker 心跳正常（健康页 healthy），只有 `pg_stat_activity` 能看到 `idle in transaction` 持 txid 卡住两个 handler 会话；清掉三个会话后 55 秒以新 PID 复现。修法 = 唯一派发口 `_deliver` 在 await handler 前先 `commit()` 释放全部行锁（`ImportEventOutboxService._release_locks_before_deliver`），认领行与 `attempt_count` 由这次提交保留、重放幂等不变。修复后共享库 2 条历史 pending 全消费（published 494→496）、0 卡死会话、0 阻塞对。
  - 守卫 `backend/tests/test_outbox_replay_lock_convoy_pg.py`（2 例）：核心判据**不是**「30s 内返回」（那种断言变异后仍绿 —— 2026-11-15 实测去掉修复仍 0.1s 返回，是假绿），而是「handler 被调用那一刻，另一连接对该 outbox 行 `SELECT … FOR UPDATE NOWAIT` 必须立刻成功」。变异（去掉派发前 commit）后以 `LockNotAvailableError` 精确报红，逐字节还原后 2 passed。
- [x] F4. 并发、故障恢复、RLS、签发/交付门、客户入账回滚验收
  - ✅ 2026-11-15：已覆盖 PG stale CAS、约束、FORCE RLS 元数据、outbox 故障/重放和客户入账回滚；回滚 active dataset 的 PostgreSQL 唯一 active 约束顺序缺陷已修复并回归通过。
  - ✅ 双事务并发 + 非 superuser RLS 强制隔离：`backend/tests/test_adjustment_concurrency_and_rls_pg.py`（双事务编辑/批准、`SET ROLE gt_rls_probe` 非超级用户隔离）＋ `test_adjustment_full_chain_pg.py` F3-4 残留守卫（孤儿分录/孤儿组行/复核人账号）。
  - ✅ 签发/交付故障门：`backend/tests/test_adjustment_signoff_gate_pg.py` 6 例 —— 签发门对草稿/待复核调整列 blocking（逐笔点名编号）· 对照组全批准后不再 blocking（防恒红）· 交付就绪门按分录组计数（2 组 4 行 ⇒ count=2/line_count=4）＋ upstream_not_ready 阻断项 · R1-AJE-UNCONVERTED 对已驳回未转错报给 warning · 转错报后不再命中 · 发布门 `effective_booking_impacts_for_accounts` 交出客户已入账组、带 ack 后为空。变异：签发门 `_check_adjustments` 恒 info → 首例红；交付门 `if False and unconfirmed>0` → 计数例红。
  - ✅ 全链恢复（含上述 F3 死锁根因修复）：清理僵死会话后共享库 pending 0 / DLQ 0 / 卡死事务 0，`event-cascade/health` healthy。
  - 结论：本任务可勾选。「真实 6000 VU 压测」与「真实业务合并集团数据 UAT」属外部环境依赖，不在本任务范围。
- [x] F5. 五角色 Playwright、刷新回读、通知深链、来源底稿、窄屏与键盘验收
  - 2026-11-15：已完成调整大厅窄屏、接口、键盘聚焦、来源/协作原生按钮和合成分页性能走查，并用临时编制/复核账号完成 AJE 提交、通知、批准、客户入账、回滚、撤销和刷新路径。仍缺合伙人/QC/EQCR 五角色全矩阵、通知深链与来源底稿连续走查；本地复核记录 worker supervisor 修复后 event-cascade health 已恢复 healthy，远端复核记录此前曾暴露 outbox replay worker 未运行，两个时间点均保留。
  - ✅ 2026-11-15 五角色矩阵闭合（API + 浏览器双证；口径 = `get_user_scope_cycles` → `resolve_member_scope`，主管角色为 `SUPERVISOR_ROLES` = partner/manager/qc/eqcr）：admin / partner / manager / qc / eqcr 均看到全部 2 组；**auditor_in（分配 D/E）看到 2 组、auditor_out（只分配 M）只看到 1 组** —— 受限可见性精确生效，浏览器上 auditor_out 只看到 `AJE-F5M` 行、看不到 D/E 的 `AJE-F5`；所有非审批角色调 approve 端点均 **403**（职责分离生效）。
  - 🔴 **本轮抓到并修复一个真后端缺陷**：`GET /api/projects/{pid}/adjustments/summary` 未按用户循环范围过滤（`svc.get_summary(project_id, year)` 不带 scope），导致受限用户计数卡显示「审计调整 2 笔」而列表只有 1 组。修法：service 增可选 `allowed_codes`（`None` 保持既有调用方行为）+ 抽出 `_summary_filters` 公共 where；router 按列表端点同一口径（`get_user_scope_cycles` → `get_codes_by_cycles`）传入。离进程直调验证：不限 aje=2 / M 范围 aje=1 / 空集 aje=0（PASS）。
  - 夹具踩坑实证（避免后来者重犯）：`project_users.scope_cycles` 是 **VARCHAR 非数组**（传 list 报 asyncpg `invalid input`）；`resolve_member_scope` 的 roles 来自 **`ProjectAssignment.role`**（`app.models.staff_models`，不是 `audit_platform_models`）而非 `ProjectUser.role`，主管判定需 `unique_chain(len(staff_ids)==1 and len(member_rows)==1) and roles & SUPERVISOR_ROLES`；`staff_members` 是全局档案，无 `project_id`/`role` 列。
  - 清理对账：F5 夹具软删时漏同步 `adjustment_entries` ⇒ 4 条孤儿明细，已按组头 `deleted_at` 同步软删；全局孤儿 0、`uat_f5_*` 账号 0 活跃。
- [x] F6. 共享库 migration 与测试数据写入经用户放行后执行；逐表清理对账
  - ✅ 2026-11-15：只读查询确认共享库已应用 V212/V235，V235 的 MigrationRunner 规范化 checksum 与数据库记录一致。本轮**未新建**共享库 migration、未执行持久化 seed、未做物理清理或回滚。
  - ✅ 逐表对账（修复走查残留后）：`adjustment_entries` 活跃 10（= 重药安徽真实数据）· 孤儿活跃明细 0 · `import_event_outbox` pending 0 / published 497 · `event_outbox_dlq` 0 · `idle in transaction` >30s 0 · 活跃项目 20。
  - 🔴 走查操作失误已修复并留痕：A8/E8 浏览器走查清场时用原生 SQL 绕过状态校验软删了 **approved** 的 AJE-004 组头，而 `delete_entry` 只允许 draft/rejected，正常路径走不到，导致 2 条 `adjustment_entries` 仍活跃（组头已软删）—— 这不是代码缺陷，是操作错误。已按组头 `deleted_at` 同步软删该 2 行（前置核对 2 活跃/0 组头活跃 → UPDATE 2 → 后置核对 remaining_active=0）。今后清场一律走平台端点，不再用原生 SQL 软删业务行。
- [x] F7. 磁盘变异汇总、临时产物清理、诊断与文档更新
  - ✅ 2026-11-15：本批临时产物清理 —— 删 `tmp_note_table_fix/`（一次性探针）与两处变异备份（`mutbak_nwps.py` / `mutbak_m1detail.ts`，均已逐字节还原后删除）；保留 `tmp_mcycle_audit/probe_m_contract_vs_frontend.py` 与 `probe_m_field_names.py` 两个**可复现探针**（M 循环形态冲突的证据来源，见 `oo-writeback-template-parity-closure` 9.2）。变异汇总见各批记录（显示设置 3/3、M 棘轮 2/2、附注章节锁 3/3）。
- [x] F8. fetch 同步、单一提交、版本号与主要变动推送
  - 2026-11-15（早先）：通过独立候选 worktree 生成单一 Conventional Commit `f52d97a5d`，`push_version.py` 原子推送分支并生成附注标签 `v1.0.194`。
  - 2026-11-15（本轮 F3/F4 死锁修复）：改动 `backend/app/services/import_event_outbox_service.py` + 新增 `backend/tests/test_outbox_replay_lock_convoy_pg.py` + 修改 `test_adjustment_full_chain_pg.py` / `test_adjustment_signoff_gate_pg.py` / `test_adjustment_concurrency_and_rls_pg.py` / `test_adjustment_group_reporting.py`，✅ **已提交并推送**：单提交 `7039f37d5`（17 files / +2101 / -46），pre-commit 三门全过（gitleaks / 文件行数门 / UTF-8 完整性），`push_version.py` 原子推送分支 + 附注标签 **`v1.0.226`**，`git merge-base --is-ancestor 7039f37d5 origin/...` = YES（远端祖先链已确认）。
    · 回归：后端选集 **54 passed**、PG 选集（含新增守卫）**47 passed / 70 passed**；`npm run typecheck` 全量 6974 → 6972、本批 5 个改动文件 **0 条错误**；暂存树自洽 2 道门 exit 0。
    · 过程留痕（供后续参考）：① 行数门拦下 `adjustment_service.py` 1015 行 > whitelist 958+5%(1005) ⇒ 按规范抽伴生模块 `adjustment_summary_filters.py`（不抬白名单），主文件回到 1005 行；② 并发会话 reset 掉暂存的 16 个文件（首次提交报 `no changes added`），重新精确 add 后成功，他人暂存的 INDEX.md 全程未受影响；③ 工作树有他人未跟踪文件 ⇒ pre-push 拒推，改用临时分离头 worktree 推送，用完 `worktree remove` + `prune`。
