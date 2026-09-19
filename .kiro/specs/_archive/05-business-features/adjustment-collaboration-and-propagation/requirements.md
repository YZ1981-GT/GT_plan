# Requirements Document

## Introduction

前置 spec `workpaper-adjustment-centralization` 已把 81 张底稿调整分录 tab **汇聚**到集中式登记（`adjustments`/`adjustment_entry` 表，`origin='workpaper'`，`source_ref={wp_id}:{item_id}`），并做了复核状态**回流**与 TB 口径唯一（`origin='workpaper'` 不进 recalc）。但 2026-07-25 复盘发现，面向"多人协作编制调整分录"这一刚性场景仍有三大空白：

1. **无协作接力**：`adjustments` 模型只有 `created_by/updated_by/reviewer_id`，没有协作者/指派/待补充字段；调整分录服务里 `grep Notification/assign/collaborat` 零匹配。一笔调整分录常涉及多人（发起人搭骨架、相关循环负责人补明细），当前无法"整组转给某人补充并确认"，也无推送通知。
2. **底稿级不自动共享 / 无按人视图**：中央页 `Adjustments.vue` 虽项目级共享，但底稿分录须手动"同步到集中登记"才可见；且未按编制人/协作者分组，看不到"每个人各自负责的调整"。
3. **调整分录不联动明细表**：`adjustment:created` 只流向 A13/recalc，`substantive:adjudicated` 流向附注；**明细表（X-2）既不标注"此行受某调整影响"，也不能把调整金额带入明细行调整列**，审计师需在明细表手工重录调整。

**用户明确的两项设计决策（本 spec 据此展开）**：

- **协作接力粒度 = 分录组级**：把整个调整分录组转派给某项目成员，让其**知晓（acknowledge）+ 补充明细行 + 确认（confirm）**；确认后回写推送给发起人，支持多轮再推。协作在分录组级发起，但被指派人的实际工作落在**明细行级**（增删改 `adjustment_entry` 行）。
- **推明细表语义 = 标注/提示 + 弹窗带入（非自动写入）**：在对应明细表的明细行处标注"此行受某调整分录影响"（可跳转到该调整），并提供**弹窗**让用户自定义把调整金额**带入**明细行调整列，带入模式三选：**单行带入 / 选定多行合计带入 / 全部求和带入**。带入是用户主动选择的显式动作，不静默自动写入。

**零回归红线**：不破坏 `workpaper-adjustment-centralization` 既有汇聚/回流/TB 口径链路，不破坏底稿→审定表→TB writeback 链路。协作与带入均为增量、可回退、灰度可控。

## Glossary

| 术语 | 含义 |
|------|------|
| 分录组 | 集中登记中同 `entry_group_id` 的一组 `adjustment`/`adjustment_entry`（一笔调整的借贷多行） |
| 协作接力 | 发起人把某分录组转派给项目成员补充+确认的多人工作流 |
| 发起人 (initiator) | 转派协作的人（通常调整分录的编制人） |
| 被指派人 (assignee) | 收到转派、需补充明细行并确认的项目成员 |
| 协作状态 | `pending`（待知晓）→`acknowledged`（已知晓）→`contributed`（已补充）→`confirmed`（已确认）→`closed`；旁支 `rejected`（退回） |
| 协作事件 | append-only 的协作历史记录（转派/知晓/补充/确认/退回/评论/关闭），防覆盖 |
| 补充 (contribute) | 被指派人在协作通道对分录组明细行（`adjustment_entry`）的增删改 |
| 协作锁 | 分录组存在活跃协作时，对 `origin='workpaper'` 的 `sync_from_workpaper` 加锁（防底稿 re-sync 覆盖协作补充） |
| 明细表联动 | 在明细表（X-2）明细行标注受影响的调整分录并支持跳转 |
| 带入 | 用户经弹窗把调整分录金额填入明细表明细行调整列的显式动作 |
| 带入模式 | 单行带入 / 多选合计带入 / 全部求和带入 |
| centralization spec | 前置 spec `workpaper-adjustment-centralization`（本 spec 直接扩展它） |

## Requirements

### Requirement 1: 分录组级协作转派

**User Story:** 作为调整分录发起人，我希望把一整组调整分录转派给某位项目成员，让他知晓并补充其负责的明细，以便多人协作完成一笔涉及多方的调整。

#### Acceptance Criteria

1. WHEN 发起人在集中调整页对某分录组发起"转派补充"并选定被指派人 THEN 系统 SHALL 创建一条协作记录（关联该 `entry_group_id`、`initiator_id`、`assignee_id`、初始状态 `pending`）并记录一条 `assigned` 协作事件。
2. WHEN 协作记录创建成功 THEN 系统 SHALL 向被指派人推送通知（含分录组编号、来源底稿、发起人、可跳转到该分录组）。
3. WHERE 被指派人不是该项目成员 THE 系统 SHALL 拒绝转派并给出明确提示（协作对象必须为项目成员）。
4. WHEN 分录组已存在活跃协作（未 `closed`/`rejected`）THEN 再次转派 SHALL 视为"重派"（`reassigned` 事件 + 通知新被指派人），不产生并存的多条活跃协作记录。

### Requirement 2: 协作接力状态机与回写推送

**User Story:** 作为被指派人，我希望有清晰的"知晓→补充→确认"流程，确认后自动通知发起人；作为发起人，我希望能看到进度并在需要时再次转派。

#### Acceptance Criteria

1. WHEN 被指派人打开协作 THEN 系统 SHALL 允许其将状态由 `pending` 推进为 `acknowledged`（记 `acknowledged` 事件）。
2. WHEN 被指派人完成明细补充并提交 THEN 系统 SHALL 将状态推进为 `contributed`（记 `contributed` 事件，携补充快照）并向发起人推送通知。
3. WHEN 被指派人确认其补充无误 THEN 系统 SHALL 将状态推进为 `confirmed`（记 `confirmed` 事件）并向发起人推送"已确认"通知。
4. WHERE 状态转换非法（如 `pending` 直接跳到 `confirmed`）THE 系统 SHALL 拒绝该转换并返回明确错误，不静默改状态。
5. WHEN 发起人对已确认/退回的分录组再次转派 THEN 系统 SHALL 开启新一轮协作（`round` 递增），历史轮次的协作事件 SHALL 完整保留。

### Requirement 3: 协作补充明细行且不覆盖底稿真源

**User Story:** 作为被指派人，我希望在协作通道直接补充/修改调整分录的明细行；作为平台维护者，我要求协作补充不被底稿 re-sync 静默覆盖。

#### Acceptance Criteria

1. WHEN 被指派人在协作通道补充明细行（增/删/改 `adjustment_entry`）THEN 系统 SHALL 将补充应用到该分录组，并将本次补充作为快照记入协作事件（append-only，不覆盖历史）。
2. WHERE 分录组 `origin='workpaper'` 且存在活跃协作 THE `AdjustmentSyncService.sync_from_workpaper` 对该 `source_ref` 的再同步 SHALL 被拒绝（`COLLABORATION_LOCKED`，409），防止底稿 re-sync 覆盖协作补充。
3. WHEN 协作 `confirmed`/`closed`/`rejected`（协作锁释放）THEN 底稿 re-sync SHALL 恢复正常。
4. WHERE 分录组复核状态为 `approved` THE 系统 SHALL 拒绝发起协作补充（对齐既有 approved 不可逆约束）。
5. WHEN 补充后提交或确认 THEN 系统 SHALL 校验分录组借贷平衡，不平衡时拒绝提交并提示差额。

### Requirement 4: 明细表明细行标注受影响调整并可跳转

**User Story:** 作为审计师，我希望在明细表的明细行上看到"此行受某调整分录影响"的标注并能跳转到该调整，以便随时追溯调整来源。

#### Acceptance Criteria

1. WHEN 明细表某明细行对应的标准科目存在集中登记的调整分录明细行（同标准科目）THEN 系统 SHALL 在该明细行显示"受 N 笔调整影响"的标注。
2. WHEN 用户点击该标注 THEN 系统 SHALL 提供跳转到对应调整分录（集中调整页定位到该分录组）的入口。
3. WHERE 某明细行对应科目无任何匹配调整 THE 系统 SHALL NOT 显示标注（不产生噪声）。
4. WHEN 集中登记的调整发生变化（新增/删除/金额变更）THEN 明细表标注 SHALL 在下次加载/刷新时反映最新匹配结果（标注为读时计算，无陈旧持久化）。

### Requirement 5: 弹窗带入调整分录到明细行（三模式）

**User Story:** 作为审计师，我希望通过弹窗把调整分录金额带入明细表明细行的调整列，并能自定义选择单行、多行合计或全部求和，以便高效准确地把调整落到明细。

#### Acceptance Criteria

1. WHEN 用户在明细行触发"带入调整" THEN 系统 SHALL 弹出弹窗列出该行对应科目匹配的调整分录明细行（含来源底稿/分录组编号、方向、金额、摘要）。
2. WHEN 用户选择"单行带入" THEN 系统 SHALL 把选定的单条调整明细行金额带入该明细行调整列。
3. WHEN 用户选择"多选合计带入" THEN 系统 SHALL 把用户勾选的多条调整明细行金额**合计**后带入。
4. WHEN 用户选择"全部求和带入" THEN 系统 SHALL 把该科目匹配的全部调整明细行金额**求和**后带入。
5. WHEN 带入执行 THEN 系统 SHALL 仅写入明细行的调整列（账项调整/重分类调整，按调整类型对应），并按借贷方向确定正负号，不覆盖该行其他字段。
6. WHERE 该明细行已带入过调整 THE 系统 SHALL 支持覆盖/重新带入，并记录本次带入的来源分录明细引用（供审计追溯，可撤销/重带）。

### Requirement 6: 全员共享可见与按人视图

**User Story:** 作为业务合伙人/质控，我希望在集中调整页看到项目组每个人的调整分录及协作进度，并能按编制人/被指派人筛选。

#### Acceptance Criteria

1. WHEN 打开集中调整页 THEN 项目成员 SHALL 看到项目内全部调整分录（受既有 `scope_cycles` 循环可见性约束），含编制人、协作状态、被指派人。
2. WHEN 用户按编制人或被指派人筛选 THEN 系统 SHALL 只展示对应人员相关的分录组。
3. WHEN 分录组存在协作 THEN 集中调整页 SHALL 展示协作状态标记（待知晓/已知晓/已补充/已确认/已退回）并提供查看协作历史（事件时间线）的入口。

### Requirement 7: 通知推送贯穿协作节点

**User Story:** 作为协作参与者，我希望在转派、补充、确认、退回等关键节点收到可跳转的通知，避免遗漏。

#### Acceptance Criteria

1. WHEN 转派/重派发生 THEN 系统 SHALL 推送通知给被指派人。
2. WHEN 补充完成或确认完成 THEN 系统 SHALL 推送通知给发起人。
3. WHEN 退回（rejected）发生 THEN 系统 SHALL 推送通知给对方并携退回原因。
4. WHEN 用户点击通知 THEN 系统 SHALL 能定位到对应分录组/协作。

### Requirement 8: 零回归与增量可回退

**User Story:** 作为平台维护者，我要求本改动不破坏 centralization 既有链路与底稿→审定表→TB 链路，且可逐步回退。

#### Acceptance Criteria

1. WHEN 未使用协作/带入功能 THEN centralization 的汇聚/回流/TB 口径与底稿链路行为 SHALL 与改动前逐位一致。
2. WHERE 明细表联动逐张接入 THE 每张明细表的接入 SHALL 独立可回退，单张失败不影响其他明细表与既有链路。
3. WHEN 协作或带入的任一后端调用失败 THEN 系统 SHALL 不阻断底稿保存与集中调整既有 CRUD/复核/导出。

### Requirement 9: 正确性属性可测

**User Story:** 作为质量负责人，我要求关键不变量有属性测试守卫。

#### Acceptance Criteria

1. WHEN 执行测试套件 THEN 系统 SHALL 覆盖：协作状态机合法转换、协作事件 append-only、协作锁防覆盖、补充借贷平衡守卫、带入三模式金额正确、明细表标注科目匹配、带入只写调整列、权限守卫、通知触发、零回归等属性。
