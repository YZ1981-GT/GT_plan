# Requirements Document

## Introduction

工时管理模块增强：自动采集平台内工作轨迹→生成草稿工时条目（P0）、支持二次编辑拆分/合并/跨日（P0）、平台外工作快捷录入+自然语言解析（P1）、时间轴 UI（P1）、审批流+统计看板（P2）。

核心目标：审计师不再手填已做过的事，平台从操作轨迹自动推断工时草稿，用户确认/调整后提交。

## Stakeholders

- 审计助理（主要填报人）
- 现场经理（审批人+负载分配）
- 业务合伙人（预算管控）

---

## Requirements

### Requirement 1: Auto-Collect Platform Activity

**Trigger:** 用户打开工时填报页 或 点击「自动采集」按钮 或 底稿保存时异步增量更新

**Behaviour:** 系统 SHALL 从以下数据源（按优先级排序）聚合操作轨迹：

**数据源优先级（复盘改进 A+B）：**
1. **SideTimerTab 已有条目**（source='timer'，精确到底稿+项目，最权威）→ 同 user+date+project+wp_code 已有 timer 条目时**跳过该段不再估算**（计时器优先规则）
2. **audit_log_entries**（有 user_id 权威，action_type 区分底稿编制/复核/调整/TB回写/附注同步/报告生成）→ 底稿编制时长估算的**主数据源**
3. **workpaper_extraction_log**（抽凭/截止测试执行）
4. **sampled_vouchers**（凭证检查执行）
5. **OnlyOffice WOPI callback**（会话时长）
6. **ai_content_log**（AI 复核/生成调用）
7. **checklist_responses**（仅作辅助信号"该底稿当日有变更"，**不作时长分配依据**——该表无 user_id 列，多人可编辑同一底稿无法归属）

**时长估算规则:**
- R1.1: 底稿编制=从 audit_log_entries 相邻操作间隔 ≤ 30min 视为连续工作累加（超 30min 截断为当次结束）
- R1.2: 复核/抽凭/AI 操作=按次计固定 0.25h（可配置 `WORK_HOUR_FIXED_ACTIVITY_DURATION`）
- R1.3: OnlyOffice 会话=从 WOPI open→callback close 取时长，上限 4h/次（防未关闭）
- R1.4: 同一项目同一天的多段工作累加合并为一条草稿条目
- R1.5: **计时器优先**——若该 user+date+project+wp_code 已有 source='timer' 条目，采集 skip 该段（复盘改进 B）
- R1.6: 单用户单日采集总量不超过 24h（超出截断+warning）

**触发方式（复盘改进 F）：**
- 用户手动触发：打开工时页/点按钮
- 底稿保存事件增量：WORKPAPER_SAVED 事件 handler 异步写一条 mini draft（不做全量采集）
- **无定时调度**（后端无 celery/APScheduler，不实现每日凌晨定时）

**Output:** 写入 `work_hour_entries` 表，`source='auto_collected'`，`status='draft'`

### Requirement 2: Draft Review and Confirmation

**Trigger:** 用户在工时填报页查看当日/本周工时

**Behaviour:** 系统 SHALL：
- R2.1: 优先展示草稿条目（`source='auto_collected'`+`status='draft'`），可视化标识"系统采集"
- R2.2: 用户可对草稿条目执行：确认（→submitted）、修改时长/描述后确认、删除
- R2.3: 已确认条目仍可编辑（修改时长/描述/项目/活动类型），直到被审批锁定
- R2.4: 草稿条目在下次采集时**不重复创建**（按 user_id+date+project_id+source_ref 幂等 + 计时器优先规则）

### Requirement 3: Split / Merge / Cross-Day Edit

**Trigger:** 用户对已有工时条目操作

**Behaviour:**
- R3.1: **拆分**——一条"底稿编制 4h"可拆为多条（审定表 2h + 明细表 2h），各自独立 wp_code+description，总时长不变（前端校验）
- R3.2: **合并**——选中同项目同日多条可合并为一条（时长相加，描述拼接）
- R3.3: **跨日调整**——可将某条目的部分时长移到前/后一天（原条目减少+目标日新建/追加，原条目→0h 时自动删除）
- R3.4: 所有操作须在 `edit_history` JSONB 记录审计轨迹（at/by/action/before/after）
- R3.5: **状态守卫（复盘改进 E）**——拆分/合并/跨日仅允许 `status='draft'` 条目直接操作；`submitted` 须先退回 draft 才能操作；`approved` 禁止操作（返回 400 + 中文提示）

### Requirement 4: External Work Quick Entry

**Trigger:** 用户点击「+ 平台外工作」

**Behaviour:**
- R4.1: 预设活动类型下拉（现场访谈/内部会议/差旅/培训/客户沟通/其他），点选后补时长和备注即可
- R4.2: `project_id` 可选（非项目级工作如培训/管理性事务允许不选）
- R4.3: 条目 `source='manual'`，与自动采集条目统一管理/审批流
- R4.4: 须填写 `activity_type`（复盘改进 C，新增字段）

### Requirement 5: Natural Language Input

**Trigger:** 用户点击「自然语言输入」或在输入框中输入自然语言描述

**Behaviour:**
- R5.1: 调用 vLLM `/ai/generate-text` 解析自然语言为结构化条目（project_name→匹配项目/activity_type/hours/description）
- R5.2: 解析结果展示为预览卡片（可修改后确认），不自动落库
- R5.3: 无法识别的项目名以 `project_id=null` 标"待关联"+黄标提示

### Requirement 6: Timeline UI

**Trigger:** 切换到日视图

**Behaviour:**
- R6.1: 在日视图显示 08:00-20:00 时间轴条形图（每 0.5h 一格）
- R6.2: 自动采集条目按真实时间段着色（从 audit_log 时间戳推断，存入 `time_slots` JSONB，复盘改进 D）
- R6.3: 手工条目无时间段时均匀分布在空闲格
- R6.4: 时间轴上可拖拽调整时长（拖边缘伸缩）

### Requirement 7: Approval Workflow Enhancement

**Trigger:** 用户提交工时 或 审批人操作

**Behaviour:**
- R7.1: 提交后条目 `status='submitted'`（锁定不可编辑，审批人可查看编辑历史）
- R7.2: 审批人退回（→draft+退回原因）、批准（→approved 锁定）
- R7.3: 已批准条目不可再编辑（仅 admin 可修改并记录）
- R7.4: 与既有 `WorkHourApprovalTab`/`workhour_approval.py` 统一（不新造流程）

### Requirement 8: Statistics Dashboard

**Trigger:** 切换到「统计」tab

**Behaviour:**
- R8.1: 周报视图（按项目/活动类型饼图+工时趋势折线+同比上周）
- R8.2: 月报导出（按项目/人员/活动类型汇总 xlsx）
- R8.3: 负载热力矩阵（7天×项目，格子颜色深浅=时长）

### Requirement 9: Zero Regression

- R9.1: 既有 `WorkHourEntry` 表结构 additive 扩展（不删列不改约束）
- R9.2: 既有 `WeeklyTimesheet` 手工填报+AI 预填+编辑记录功能逐字节不变
- R9.3: 既有审批流（batch-approve/approval tab）逐字节不变
- R9.4: 既有 SideTimerTab（底稿内计时器）逐字节不变
- R9.5: 自动采集 fail-open（数据源查询失败不阻断用户手工填报）

### Requirement 10: Correctness Properties

- 11 条可测属性（P1-P11），design 阶段细化

## Glossary

| 术语 | 含义 |
|------|------|
| 草稿 draft | source=auto_collected/llm_parsed，用户未确认 |
| 确认 submitted | 用户确认提交待审批 |
| 批准 approved | 审批人批准，锁定不可编辑 |
| source_ref | 幂等键：`{data_source}:{object_id}:{date}`，防重复采集 |
| 活动类型 activity_type | 底稿编制/复核/抽凭/AI操作/会议/差旅/培训/其他 |
| 时间段 time_slot | 08:00-20:00 按 0.5h 分格 |
| 计时器优先 | 同 user+date+project+wp_code 有 source='timer' 条目时采集 skip |
