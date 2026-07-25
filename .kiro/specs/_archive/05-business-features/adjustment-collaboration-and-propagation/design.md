# Design Document

## Overview

在 `workpaper-adjustment-centralization` 已建的集中登记之上，增加两条能力，均为增量、灰度可控、零回归：

- **Part A 协作接力**（分录组级）：新增协作实体（`adjustment_collaboration` + append-only `adjustment_collaboration_event`），以集中登记的 `entry_group_id` 为锚点，实现"转派→知晓→补充明细行→确认→回写推送"多人工作流，复用现有 `NotificationService` 推送。对 `origin='workpaper'` 分录组，活跃协作期间**锁定 re-sync** 防覆盖（复用既有 approved-lock 模式）。
- **Part B 明细表联动**（标注 + 弹窗带入）：**无新表**。明细表明细行按标准科目**读时匹配**集中登记的调整分录明细行，显示"受 N 笔调整影响"标注 + 跳转；提供带入弹窗（单行/多选合计/全部求和），把调整金额显式写入明细行既有调整列，并在明细行元数据记录来源引用供追溯。

**核心设计取舍**：

- 协作锚点选 **central `entry_group_id`**（而非底稿本地 item_id）：中央页是项目级共享真源，`entry_group_id` 天然分组，被指派人经协作通道编辑 `adjustment_entry`。协作是**受控的多人编辑通道**——不放开中央页对 workpaper-origin 的通用编辑（centralization 已禁用以防 re-sync 覆盖），而是通过协作锁 + 协作专用端点安全地允许协作补充。
- Part B **不持久化"影响"linkage**：标注为读时按 `standard_account_code` 匹配计算（无新表、无 drift、随调整变更自动刷新）。带入是显式动作，只写明细行既有调整列 + 在明细行 remark JSON 记来源引用（复用既有存储）。
- 明细表结构逐张不同，带入弹窗输出**通用载荷**（选定金额合计 + 调整类型 aje/rje + 来源分录明细引用），由各明细表 tab 映射到自身调整列。试点少量明细表，其余增量接入。

## Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │  集中登记 adjustments/adjustment_entry (既有) │
                          │  entry_group_id / origin / source_ref (V124)  │
                          └───────────────┬─────────────────────────────┘
                                          │ 锚点 entry_group_id
        Part A 协作接力                    ▼
  Adjustments.vue "转派补充"  ──▶ POST .../{entry_group_id}/collaboration/assign
                                          ▼
                            AdjustmentCollaborationService
                              │  create collaboration(status=pending, round)
                              │  event(assigned, append-only)      ← Req1/2/3
                              │  NotificationService.push(assignee) ← Req7
                              ▼
                       adjustment_collaboration (+ _event) [V125 新表]
                              │
   被指派人 收件箱/中央页 ──▶ acknowledge / contribute(编辑 entry) / confirm
                              │  contribute → 编辑 adjustment_entry + 平衡校验 + event快照
                              │  confirm    → status=confirmed + notify initiator + 释放协作锁
                              ▼
   AdjustmentSyncService.sync_from_workpaper
     └─[改] 活跃协作(origin=workpaper) → COLLABORATION_LOCKED(409)  ← Req3.2

        Part B 明细表联动 (无新表)
  明细表 X-2 明细行 (useXDetail)
     │  按 standard_account_code 读时匹配 central adjustments
     ├─▶ useAdjustmentDetailPropagation: "受N笔调整影响"标注 + 跳转   ← Req4
     └─▶ AdjustmentBringInDialog: 单行/多选合计/全部求和
            └─ emit {amount, adjustmentType, sourceEntryRefs}
               → 各明细表 tab 写入自身调整列 + remark 记来源引用       ← Req5
```

## Data Models

### V125 迁移（`V125__adjustment_collaboration.sql` + `R125` 回滚，幂等 information_schema/IF NOT EXISTS 守护）

**表 `adjustment_collaboration`**（协作记录，可变状态）：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK projects | |
| `year` | INT NOT NULL | |
| `entry_group_id` | UUID NOT NULL | 锚点：集中登记分录组 |
| `source_ref` | VARCHAR(120) NULL | workpaper-origin 组的溯源键（协作锁判定用） |
| `initiator_id` | UUID FK users NOT NULL | 发起人 |
| `assignee_id` | UUID FK users NOT NULL | 被指派人 |
| `status` | VARCHAR(20) DEFAULT `'pending'` NOT NULL | pending/acknowledged/contributed/confirmed/closed/rejected |
| `round` | INT DEFAULT 1 NOT NULL | 协作轮次（多轮再推） |
| `note` | TEXT NULL | 转派说明 |
| `rejection_reason` | TEXT NULL | 退回原因 |
| `is_deleted` / `created_at` / `updated_at` | | 软删 + 时间戳 |

索引：`(project_id, entry_group_id)`、`(assignee_id, status)`、`(project_id, status)`。
活跃唯一性（同组至多一条活跃协作）由服务层保证（重派更新既有活跃记录/递增 round，不建并存活跃行）；不加 DB 唯一约束以支持历史多轮。

**表 `adjustment_collaboration_event`**（append-only 历史）：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | |
| `collaboration_id` | UUID FK adjustment_collaboration NOT NULL | |
| `actor_id` | UUID FK users NOT NULL | 操作人 |
| `event_type` | VARCHAR(20) NOT NULL | assigned/reassigned/acknowledged/contributed/confirmed/rejected/commented/closed |
| `payload` | JSONB NULL | 快照：补充的明细行 diff / note / round |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

索引：`(collaboration_id, created_at)`。**append-only**：仅 INSERT，无 UPDATE/DELETE。

ORM `AdjustmentCollaboration` / `AdjustmentCollaborationEvent` 同步声明（drift=0）。

**Part B 无迁移**：明细表标注读时计算；带入写既有明细行调整列 + 明细行 remark JSON 增字段 `adjSourceRefs`（复用 checklist_responses 存储，无新表/无迁移）。

## Components and Interfaces

### 1. 数据模型落地（V125 + ORM）

见 §Data Models。迁移取号执行前以 `migration_status` 复核（当前最高 V124）。

### 2. `AdjustmentCollaborationService`（新增 `app/services/adjustment_collaboration_service.py`）

```python
async def assign(self, project_id, *, entry_group_id, assignee_id, initiator_id, note, year) -> Collab:
    """转派/重派。校验 assignee 为项目成员；分录组非 approved。
    活跃协作存在 → reassigned(更新 assignee + round 不变或递增) ；否则新建 pending。
    记 assigned/reassigned 事件 + 通知 assignee。"""

async def acknowledge(self, collaboration_id, actor) -> Collab      # pending→acknowledged
async def contribute(self, collaboration_id, actor, edits, note) -> Collab
    """应用明细行增删改到 entry_group（复用 AdjustmentService 写入）；借贷平衡校验；
    状态→contributed；append event(快照 diff)；通知 initiator。"""
async def confirm(self, collaboration_id, actor, note) -> Collab    # contributed→confirmed + 通知 initiator + 释放锁
async def reject(self, collaboration_id, actor, reason) -> Collab   # →rejected + 通知对方
async def start_new_round(self, project_id, entry_group_id, ...) -> Collab  # confirmed/rejected 后再推 round+1

async def get_active_by_group(self, project_id, entry_group_id) -> Collab | None
async def get_timeline(self, collaboration_id) -> list[Event]
async def list_inbox(self, project_id, assignee_id) -> list[Collab]  # 被指派人待办
```

状态机（合法转换白名单，非法 raise `CollaborationError('INVALID_TRANSITION')`）：
`pending→acknowledged→contributed→confirmed`；任意活跃态→`rejected`/`closed`；`confirmed`/`rejected`→（新轮）`pending`。

**协作锁**：`get_active_by_group` 返回状态 ∈ {pending, acknowledged, contributed} 视为"活跃"。

### 3. 路由（挂 `adjustments` router）

- `POST /api/projects/{pid}/adjustments/{entry_group_id}/collaboration/assign` — body {assignee_id, note, year}；非项目成员→400，approved→409。
- `POST /api/projects/{pid}/adjustments/collaboration/{cid}/acknowledge`
- `POST /api/projects/{pid}/adjustments/collaboration/{cid}/contribute` — body {edits:[{op,line...}], note}；不平衡→400。
- `POST /api/projects/{pid}/adjustments/collaboration/{cid}/confirm`
- `POST /api/projects/{pid}/adjustments/collaboration/{cid}/reject` — body {reason}
- `GET  /api/projects/{pid}/adjustments/collaboration/inbox` — 被指派人待办（当前用户）
- `GET  /api/projects/{pid}/adjustments/{entry_group_id}/collaboration` — 协作 + 事件时间线

授权：assign/reject 由 initiator 或 delegator 角色；acknowledge/contribute/confirm 由 assignee（或 delegator）；全部要求项目成员（`require_project_access`）。

### 4. `AdjustmentSyncService.sync_from_workpaper` 改动

在 approved-lock 检查旁增加协作锁：`origin='workpaper'` 且该 `source_ref` 对应分录组存在活跃协作 → raise `AdjustmentSyncError('COLLABORATION_LOCKED')`（router 转 409）。协作 confirmed/closed/rejected 后放行（零回归：无协作时逻辑逐位不变）。

### 5. `NotificationService` 复用

复用平台既有通知（`batch-assign-enhanced` 已用）。**Wave0 核实结论**：
- `NotificationService(db).send_notification(user_id, notification_type, title, content="", metadata={object_type,object_id}, db=None)` — **非阻塞**（失败返 None + warning，不抛）。`Notification` 模型仅 `related_object_type`/`related_object_id`（object_id 为 UUID）→ 无任意跳转 metadata。故**降级**：`object_type='adjustment_collaboration'` + `object_id=entry_group_id`，content 内嵌分录组编号/发起人；前端通知点击 → 路由集中调整页定位该分录组。
- 新增通知类型常量（`app/services/notification_types.py`）：`ADJ_COLLAB_ASSIGNED` / `ADJ_COLLAB_CONTRIBUTED` / `ADJ_COLLAB_CONFIRMED` / `ADJ_COLLAB_REJECTED`。
- **项目成员校验范式**（复用 batch_assign_enhanced）：admin 角色 bypass；否则 `StaffMember.user_id==uid & is_deleted=false → staff_id`，再 `ProjectAssignment(staff_id, project_id, is_deleted=false)` 存在即项目成员（转派对象校验用之，role 不限）。端点授权用 `app.deps.require_project_access`。

本 spec 只封装调用点：转派→assignee、补充/确认→initiator、退回→对方。

### 6. 前端 `useAdjustmentCollaboration`（新增共享 composable）

```ts
useAdjustmentCollaboration(opts:{ projectId, year })
→ { assign, acknowledge, contribute, confirm, reject,
    inbox: Ref<Collab[]>, refreshInbox,
    getGroupCollaboration(entryGroupId): Promise<{collab, timeline}> }
```

### 7. `Adjustments.vue` 集中管理页增强

- 每分录组操作区加"转派补充"（选人 el-select 项目成员 + note）。
- 列表加协作状态列/标记（待知晓/已知晓/已补充/已确认/已退回）+ 被指派人。
- 顶部筛选加"编制人 / 被指派人"（Req6.2）。
- 协作历史抽屉（事件时间线）。
- 被指派人视角：inbox 入口（通知跳转落地）+ 补充弹窗（编辑 entry 明细行 + 平衡校验 + 提交/确认）。

### 8. Part B — 明细表联动（前端为主，无新表）

**`useAdjustmentDetailPropagation`（新增共享 composable）**：
```ts
useAdjustmentDetailPropagation(opts:{ projectId, year })
→ {
  matchByAccount(stdCode): AdjustmentLineMatch[]   // 读 central list_entries 按科目匹配
  countForRow(stdCode): number                     // "受N笔影响"
  jumpToAdjustment(entryGroupId): void             // 跳转集中页定位
}
```
数据源：复用既有 `GET /adjustments`（返回 line_items 含 standard_account_code），前端按科目过滤匹配（项目级，跨循环可达）。

**`AdjustmentBringInDialog.vue`（新增）**：列出该科目匹配的调整明细行（来源底稿/组号/方向/金额/摘要）+ 三模式选择（单行 radio / 多选 checkbox 合计 / 全部求和）→ emit `{ amount, adjustmentType, sourceEntryRefs }`。

**明细表接入（试点 D2-2，扩展 K9-2 等）**：明细行加"受N笔调整影响"标注 chip（点击跳转）+ "带入调整"按钮开弹窗；`onBringIn(payload)` 写入该行调整列（按 adjustmentType→账项调整/重分类调整，按方向定正负）+ 在行 remark JSON 记 `adjSourceRefs`（Req5.6 追溯 + 可重带）。

## Correctness Properties

### Property 1: 协作状态机合法转换
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 9.1**
仅白名单转换（pending→acknowledged→contributed→confirmed，活跃→rejected/closed，confirmed/rejected→新轮 pending）被接受；非法转换 raise INVALID_TRANSITION，状态不变。

### Property 2: 协作事件 append-only
**Validates: Requirements 1.1, 2.5, 3.1, 9.1**
每次 assign/acknowledge/contribute/confirm/reject 产生恰好一条新 event；历史 event 永不被 UPDATE/DELETE；多轮 round 的历史事件全保留。

### Property 3: 单组至多一条活跃协作 + 多轮
**Validates: Requirements 1.4, 2.5**
同 entry_group_id 在任一时刻活跃协作记录 ≤ 1；重派更新既有活跃记录而非新建并存；confirmed/rejected 后可再开新轮（round 递增）。

### Property 4: 协作锁防覆盖
**Validates: Requirements 3.2, 3.3, 9.1**
`origin='workpaper'` 分录组存在活跃协作时，`sync_from_workpaper` 该 source_ref 返回 COLLABORATION_LOCKED；协作非活跃时 sync 行为与改动前逐位一致。

### Property 5: 补充借贷平衡守卫
**Validates: Requirements 3.5, 9.1**
contribute/confirm 后分录组借贷不平衡时拒绝，返回差额；平衡时通过。

### Property 6: approved 不可协作
**Validates: Requirements 3.4**
分录组复核状态为 approved 时 assign 被拒绝。

### Property 7: 通知触发到正确对象
**Validates: Requirements 1.2, 2.2, 2.3, 7.1, 7.2, 7.3, 9.1**
assign/reassign→assignee；contributed/confirmed→initiator；rejected→对方（含 reason）。

### Property 8: 明细表标注科目匹配
**Validates: Requirements 4.1, 4.3, 9.1**
明细行标注计数 = 集中登记中 standard_account_code 与该行科目匹配的调整明细行数；无匹配时计数为 0（不标注）。

### Property 9: 明细表标注读时刷新（无陈旧持久化）
**Validates: Requirements 4.4**
调整新增/删除/金额变更后，明细表标注在下次加载反映最新匹配（标注非持久化）。

### Property 10: 带入三模式金额正确
**Validates: Requirements 5.2, 5.3, 5.4, 9.1**
单行带入=选定单行金额；多选合计=勾选行金额之和；全部求和=匹配全部行金额之和；三者对同一集合满足"全部求和=全选多选合计"。

### Property 11: 带入只写调整列且方向正确
**Validates: Requirements 5.5, 5.6, 9.1**
带入仅修改明细行调整列（按 aje/rje 对应列、按借贷方向定正负），不改其他字段；重带覆盖且记录来源引用；可撤销。

### Property 12: 权限守卫
**Validates: Requirements 1.3, 9.1**
assign/reject 限 initiator/delegator；acknowledge/contribute/confirm 限 assignee/delegator；非项目成员被拒。

### Property 13: 零回归
**Validates: Requirements 8.1, 8.2, 8.3**
未使用协作/带入时，centralization 汇聚/回流/TB 口径与底稿链路、集中调整 CRUD/复核/导出逐位不变；单张明细表接入失败不影响其他与既有链路。

## Error Handling

- `INVALID_TRANSITION` → 400（非法状态转换）。
- `NOT_PROJECT_MEMBER` → 400（转派对象非项目成员）。
- `APPROVED_LOCKED` → 409（approved 组不可协作）。
- `COLLABORATION_LOCKED` → 409（活跃协作期间底稿 re-sync 被拒）。
- `UNBALANCED` → 400（补充后不平衡，带差额）。
- 通知推送失败 → 仅记 warning，**不阻断**协作状态转换（通知是旁路）。
- 带入/协作端点整体失败 → 前端 toast，不阻断底稿保存与集中调整既有操作（Req8.3）。

## Testing Strategy

- **后端 pytest + PBT（hypothesis, max_examples=5）**：状态机合法/非法转换（P1）、event append-only（P2）、单组活跃唯一+多轮（P3）、协作锁（P4，含无协作零回归对比）、补充平衡守卫（P5）、approved 拒绝（P6）、通知触发对象（P7，mock NotificationService 断言调用）、权限守卫（P12）。
- **后端零回归**：`sync_from_workpaper` 无协作时与 centralization 基线逐位一致；`recalc`/CRUD/复核/导出全绿（P13）。
- **前端 vitest**：带入三模式金额纯函数（P10，含"全部=全选合计"不变量）、带入只写调整列映射（P11）、明细表标注按科目匹配计数（P8）、状态机前端守卫。
- **零回归门**：adjustments/adjustment_sync/trial_balance/misstatement 后端全绿；改动前端文件 Vite transform 200；get_diagnostics 全清。
- **Playwright（optional）**：转派→通知→被指派人补充→确认→回写通知→发起人可见；明细表标注→带入弹窗三模式→写入调整列 round-trip（改用鉴权 HTTP round-trip 兜底若 UI flaky，创建后清理无污染）。

## Migration & Rollout

- **V125**：`adjustment_collaboration` + `adjustment_collaboration_event`（幂等 + R125 回滚）。ORM 同步 drift=0。执行前 `migration_status` 复核取号。
- **灰度/增量**：Part A 协作为中央页新增动作（不影响未使用者）；Part B 明细表联动逐张接入（试点 D2-2 → K9-2 → 其余），单张可回退。
- **回退**：移除中央页"转派"入口即停用协作（协作锁对无协作零影响）；移除明细表标注/带入按钮即停用联动。
