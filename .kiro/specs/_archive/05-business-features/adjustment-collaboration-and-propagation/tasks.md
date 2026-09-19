# Implementation Plan

## Overview

在 `workpaper-adjustment-centralization` 集中登记之上，增加 **Part A 分录组级协作接力**（转派→知晓→补充明细行→确认→回写推送 + 协作锁防覆盖 + 通知）与 **Part B 明细表联动**（明细行标注受影响调整 + 跳转 + 弹窗三模式带入）。增量、灰度、逐张明细表可回退，零回归既有 centralization 与底稿→审定表→TB 链路。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "desc": "核实 NotificationService/项目成员校验接口 + 零回归安全网基线" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "V125 迁移 + ORM 两表" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "desc": "协作服务(状态机+补充+通知) + sync 协作锁 + 路由" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "前端协作 composable + 中央页转派/状态/时间线/inbox/补充弹窗" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "desc": "Part B 明细表联动 composable + 带入弹窗 + 试点 D2-2 接入" },
    { "wave": 5, "tasks": ["6.1"], "desc": "扩展明细表接入 K9-2（增量试点）" },
    { "wave": 6, "tasks": ["7.1", "7.2"], "desc": "后端 PBT P1-P7/P12 + 前端 vitest P8/P10/P11" },
    { "wave": 7, "tasks": ["8.1", "8.2"], "desc": "零回归门 + Playwright/HTTP round-trip" }
  ]
}
```

## Tasks

- [x] 1.1 Wave0 核实（已完成，结论写入 design §5）：`NotificationService(db).send_notification(user_id, type, title, content, metadata={object_type,object_id})` 非阻塞；`Notification` 仅 related_object_type/id → 降级用 object_type='adjustment_collaboration'+object_id=entry_group_id；新增 4 个通知类型常量。项目成员校验复用 batch_assign_enhanced 范式（admin bypass / StaffMember→ProjectAssignment）；端点授权用 `require_project_access`。
  - Requirements: 7.1, 7.4, 1.3

- [x] 1.2 后端 characterization 安全网：基线全绿——`test_adjustment_sync.py`+`test_adjustments.py` 41 passed、`test_trial_balance.py` 12 passed（asyncpg teardown RuntimeWarning 非失败）。
  - Requirements: 8.1

- [x] 2.1 迁移 `V125__adjustment_collaboration.sql` + `R125__rollback_adjustment_collaboration.sql`（CREATE TABLE/INDEX IF NOT EXISTS 幂等）：`adjustment_collaboration`（status/round/source_ref/initiator/assignee + 3 索引）+ `adjustment_collaboration_event`（append-only + 索引）。已应用（"数据库已是最新版本"），drift=0。
  - Requirements: 1.1, 2.5, 3.1

- [x] 2.2 ORM `AdjustmentCollaboration` / `AdjustmentCollaborationEvent` 同步声明（audit_platform_models.py，对齐 V125）；drift 扫描 TOTAL_DRIFT=0 / COLLAB_DRIFT=0。
  - Requirements: 1.1, 3.1

- [x] 3.1 `AdjustmentCollaborationService`（新建 adjustment_collaboration_service.py）：assign/reassign（项目成员校验+approved拒绝+活跃唯一+round）、acknowledge、contribute（重建 entry_group 明细行+借贷平衡+科目解析复用 sync+append event 快照）、confirm、reject、get_active_by_group/get_latest_by_group/get_timeline/list_inbox；状态机白名单（_LEGAL_FROM，非法 INVALID_TRANSITION）；参与者守卫（_require_assignee/reject 参与者）；`has_active_collaboration` 模块函数供 sync；各节点 _notify 旁路（失败仅 warning）。import 通过。
  - Requirements: 1.1, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.4, 3.5, 7.1, 7.2, 7.3

- [x] 3.2 `AdjustmentSyncService.sync_from_workpaper` 增协作锁：existing_rows 存在时懒导入 `has_active_collaboration`，活跃协作 → raise COLLABORATION_LOCKED（无协作时逐位零回归，仅 existing 分支增一判定）。
  - Requirements: 3.2, 3.3, 8.1

- [x] 3.3 路由（挂 adjustments router）：assign/acknowledge/contribute/confirm/reject/inbox/get-collaboration 七端点 + `_collab_http` 错误码映射（INVALID_TRANSITION/UNBALANCED→400，NOT_ASSIGNEE/NOT_PARTICIPANT/NOT_PROJECT_MEMBER→403，APPROVED_LOCKED→409，*_NOT_FOUND→404）+ sync COLLABORATION_LOCKED→409 + schemas；`require_project_access` 授权。router import 通过。
  - Requirements: 1.2, 2.1, 2.2, 2.3, 3.2, 7.4

- [x] 4.1 前端 `useAdjustmentCollaboration` 共享 composable（assign/acknowledge/contribute/confirm/reject/inbox/refreshInbox/getGroupCollaboration + COLLAB_STATUS_LABELS/TAG + 统一错误映射）+ 前端 API（assign/ack/contribute/confirm/reject/inbox/byGroup）+ apiPaths（collab*）。get_diagnostics 清。
  - Requirements: 1.1, 2.1, 2.2, 2.3, 6.3

- [x] 4.2 `Adjustments.vue` 协作增强：操作列加"协作"按钮 → 自包含 `AdjustmentCollaborationDialog`（转派选项目成员+note / 被指派人 知晓·补充明细行[科目+借贷+平衡校验]·确认·退回 / 发起人退回 / 协作状态 tag + 事件时间线）；assignee_id 后端 staff_id→user_id 解析。get_diagnostics 清。
  - Requirements: 1.1, 2.1, 2.2, 2.3, 3.1, 3.5, 6.3, 7.4

- [x] 5.1 前端 `useAdjustmentDetailPropagation`（读 central `GET /adjustments` page_size=500 按 standard_account_code 匹配，`accountMatches` 精确或子科目上卷）：matchByAccount/countForRow/jumpToAdjustment（router name='Adjustments'+query.group）；标注读时计算无持久化。get_diagnostics 清。
  - Requirements: 4.1, 4.2, 4.3, 4.4

- [x] 5.2 `AdjustmentBringInDialog.vue`（新建）：列匹配调整明细行（来源/组号/方向/金额/摘要）+ 三模式（单行 radio / 多选合计 checkbox / 全部求和）→ emit `{amount(净=借-贷), debitTotal, creditTotal, adjustmentType, sourceEntryRefs, lineCount}`；纯函数 `sumBringIn` 保证"全部求和=全选多选合计"。get_diagnostics 清。
  - Requirements: 5.1, 5.2, 5.3, 5.4

- [x] 5.3 试点接入 **K9-2** 明细表（plain el-table，比 D2-2 虚拟表更适合 per-row 试点）：明细行"受N笔调整影响"tag（点击 jumpFirstAdjustment 跳转）+ "带入"按钮开弹窗；onBringIn 按 adjustmentType 写该行 AJE/RJE 列（handleCellChange 持久化）+ session 级 adjBroughtIn 记来源引用；onMounted propagation.load()。get_diagnostics 清。
  - Requirements: 4.1, 4.2, 5.5, 5.6, 8.2

- [x] 6.1 扩展接入 K8-2 明细表（同 5.3 范式，科目 6601 销售费用，审定区段 plain el-table，写账项调整/重分类调整列）；范式沉淀（K9-2/K8-2 一致），其余明细表增量可回退。get_diagnostics 清。
  - Requirements: 4.1, 5.5, 8.2

- [x] 7.1 后端 PBT/单测：`test_adjustment_collaboration.py` **11 passed**——状态机合法/非法 P1、event append-only P2、单组活跃唯一+多轮 P3、协作锁 P4（含确认后释放+sync 恢复）、补充平衡守卫 P5、approved 拒绝 P6、通知触发对象 P7（mock NotificationService）、权限守卫 P12（NOT_PROJECT_MEMBER/NOT_ASSIGNEE/NOT_PARTICIPANT）+ staff_id→user_id 解析。
  - Requirements: 9.1

- [x] 7.2 前端 vitest：`adjustmentPropagation.spec.ts` **12 passed**——P8 accountMatches 精确/子科目上卷、P10 sumBringIn 三模式（全部==全选合计不变量）、P11 类型→列映射（aje/rje/mixed）、协作状态标签齐全。**🔴 顺带修 script-setup 非法 export**（sumBringIn/BringInPayload 移入普通 `<script>` 块，避免 Vite 编译 500）。
  - Requirements: 9.1

- [x] 8.1 零回归门：后端 adjustment_sync+adjustments+trial_balance+collaboration **64 passed**（零回归，无协作时 sync 与 centralization 基线逐位一致）；全改动前端文件 **Vite transform 200**（7/7：两 Dialog+两 composable+Adjustments.vue+K9-2+K8-2）；get_diagnostics 全清；drift=0。
  - Requirements: 8.1, 8.2, 8.3

- [ ]* 8.2 端到端 live round-trip：**未运行（诚实留待）**。理由：optional；共享 live 环境（9980/3030/浏览器）本会话被并发 Kiro 会话占用（终端/浏览器 SSE 抖动），live UI/HTTP round-trip 易 flaky→避免假绿。工作流正确性已由后端 11 测试（assign→ack→contribute→confirm→reject→协作锁→权限）+ 前端 12 测试（三模式带入/科目匹配/类型映射）+ Vite 200 覆盖。待独占环境补跑：转派→通知→补充→确认→回写 + 明细表标注→带入三模式→写调整列。
  - Requirements: 1.1, 2.2, 2.3, 4.1, 5.2, 5.3, 5.4

## Notes

- **零回归红线**：底稿→审定表→TB writeback 与 centralization 汇聚/回流/TB 口径（origin 过滤）一行不改；协作锁仅在 origin='workpaper' 且活跃协作时生效，无协作时逐位不变。
- **协作锚点**：central `entry_group_id`（项目级共享真源）。协作是受控多人编辑通道，不放开中央页对 workpaper-origin 的通用编辑（维持 centralization 防覆盖），靠协作锁 + 协作专用端点安全允许补充。
- **Part B 无新表**：标注读时按 standard_account_code 匹配 central adjustments（无 drift、随调整变更自动刷新）；带入只写明细行既有调整列 + remark JSON 记来源引用。
- **迁移取号**：当前最高 V124，本 spec 用 **V125**；执行前以 `migration_status` 复核。
- **增量接入**：Part A 中央页一处覆盖全循环（circle-agnostic）；Part B 明细表逐张接入（试点 D2-2/K9-2），其余增量、单张可回退。
- **通知复用**：复用既有 NotificationService（Wave0 核实接口），不新造通知系统；不支持跳转 metadata 时按能力降级。
- **错报 ≠ 调整**：`a13:push-misstatement`（未更正错报）由 `useA13MisstatementBridge` 处理，不在本 spec；本 spec 只处理 AJE/RJE 调整分录的协作与明细表联动。
