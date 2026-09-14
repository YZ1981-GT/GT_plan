# Design Document

## Overview

工时自动采集+二次编辑系统。从平台操作轨迹自动推断工时草稿，用户确认/拆分/合并后提交审批。支持平台外工作快捷录入、自然语言解析、时间轴可视化、统计看板。

## Data Models

### WorkHourEntry 扩展（V130 迁移，additive 5 列）

现有 `work_hour_entries` 表新增 5 列（复盘改进 A/C/D 并入）：

```sql
-- V130 迁移（幂等 IF NOT EXISTS）
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS source_ref VARCHAR(200);
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS edit_history JSONB DEFAULT '[]';
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS activity_type VARCHAR(30);
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS time_slots JSONB;

-- 部分索引
CREATE INDEX IF NOT EXISTS idx_whe_source_date ON work_hour_entries(user_id, date, source) WHERE source = 'auto_collected';
CREATE INDEX IF NOT EXISTS idx_whe_timer_dedup ON work_hour_entries(user_id, date, project_id, wp_code) WHERE source = 'timer';
```

**列说明：**
| 列 | 类型 | 默认值 | 用途 |
|----|------|--------|------|
| source | VARCHAR(20) | 'manual' | manual/auto_collected/llm_parsed/timer |
| source_ref | VARCHAR(200) | NULL | 幂等键 `{source_type}:{object_id}:{date}` |
| edit_history | JSONB | '[]' | `[{at, by, action, before, after}]` |
| activity_type | VARCHAR(30) | NULL | 底稿编制/复核/抽凭/AI操作/会议/差旅/培训/其他 |
| time_slots | JSONB | NULL | `[{start:'09:30',end:'11:00',project_id:'...'}]` 推断时段 |

不改现有列/约束/索引，零回归。`activity_type` 为 NULL 时既有条目不受影响（外部工作 R4 必填）。

## Architecture

### 后端新增

1. **`work_hour_auto_collector.py`** — 核心采集服务
   - `collect_for_user(db, user_id, date_range)` → List[DraftEntry]
   - 数据源优先级：timer 已有 > audit_log > extraction_log > sampled_vouchers > wopi > ai_log > checklist(辅助)
   - `_estimate_editing_duration(timestamps)` — 相邻 ≤30min 间隔累加
   - `_check_timer_priority(db, user_id, date, project_id, wp_code)` — 计时器优先规则
   - `_dedup_and_persist(db, user_id, drafts)` — source_ref 幂等 upsert
   - `_infer_time_slots(audit_log_rows)` — 从时间戳推断时段写入 time_slots

2. **`work_hour_entry_ops.py`** — 拆分/合并/跨日操作
   - `split_entry(db, entry_id, splits)` — 状态守卫 + 总时长守恒 + edit_history
   - `merge_entries(db, entry_ids)` — 状态守卫 + 同项目同日 + edit_history
   - `cross_day_transfer(db, entry_id, target_date, hours)` — 状态守卫 + edit_history
   - **状态守卫（复盘改进 E）：仅 draft 可直接操作；submitted 返回 400 提示先退回；approved 禁止**

3. **`work_hour_nlp.py`** — 自然语言解析
   - `parse_natural_language(text, project_list)` → List[ParsedEntry]
   - 调用 `chat_completion`（vLLM），JSON 输出 schema

4. **事件驱动增量（复盘改进 F）**
   - `_on_workpaper_saved` handler：WORKPAPER_SAVED → 异步写 mini draft（该用户+该底稿+今日，增量 0.25h 或按间隔估算，不做全量采集）
   - **无定时调度器**

5. **路由新增**（`workhours.py` 追加）：
   - `POST /api/workhours/auto-collect` — 触发全量采集
   - `POST /api/workhours/{id}/split` — 拆分
   - `POST /api/workhours/merge` — 合并
   - `POST /api/workhours/{id}/cross-day` — 跨日转移
   - `POST /api/workhours/parse-natural-language` — 自然语言解析
   - `GET /api/workhours/timeline?date=` — 时间轴数据（带 time_slots）

### 前端新增

1. **`composables/useWorkHourAutoCollect.ts`** — 调用采集+展示草稿
2. **`composables/useWorkHourEntryOps.ts`** — 拆分/合并/跨日
3. **`composables/useWorkHourNlp.ts`** — 自然语言解析
4. **`WorkHourTimelineBar.vue`** — 日视图时间轴条形图（读 time_slots）
5. **`WorkHourSplitDialog.vue`** — 拆分弹窗（余额指示器+守恒校验）
6. **`WorkHourMergeConfirm.vue`** — 合并确认
7. **`WorkHourExternalEntryDialog.vue`** — 平台外工作快捷录入（含 activity_type）
8. **`WorkHourNlpInput.vue`** — 自然语言输入+预览卡片
9. **`WorkHourStatsDashboard.vue`** — 统计看板

## Components and Interfaces

### WorkHourAutoCollector

```python
class WorkHourAutoCollector:
    """平台操作轨迹→工时草稿聚合器"""

    async def collect_for_user(self, db, user_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """采集指定日期范围，返回草稿列表。计时器优先+fail-open。"""

    async def _check_timer_priority(self, db, user_id, date, project_id, wp_code) -> bool:
        """检查是否已有 source='timer' 条目，有则 skip（复盘改进 B）"""

    async def _collect_from_audit_log(self, db, user_id, date_from, date_to) -> list[RawActivity]:
        """主数据源：从 audit_log_entries 聚合（复盘改进 A）"""

    async def _estimate_editing_duration(self, timestamps: list[datetime]) -> Decimal:
        """相邻间隔 ≤30min 累加"""

    async def _infer_time_slots(self, activities: list[RawActivity]) -> list[dict]:
        """从时间戳推断时段 [{start,end}]（复盘改进 D）"""

    async def _dedup_and_persist(self, db, user_id, drafts) -> int:
        """source_ref 幂等 upsert + 计时器优先检查"""
```

### WorkHourEntryOps

```python
class WorkHourEntryOps:
    """工时条目拆分/合并/跨日操作（含状态守卫）"""

    def _assert_editable(self, entry: WorkHourEntry) -> None:
        """状态守卫：仅 draft 可操作，submitted/approved 返回 400（复盘改进 E）"""

    async def split_entry(self, db, entry_id: UUID, splits: list[dict]) -> list[WorkHourEntry]:
        """拆分：_assert_editable + 总时长守恒 + 软删原条目 + 新建 N 条"""

    async def merge_entries(self, db, entry_ids: list[UUID]) -> WorkHourEntry:
        """合并：_assert_editable(each) + 同项目同日 + 新建 1 条"""

    async def cross_day_transfer(self, db, entry_id: UUID, target_date: date, hours: Decimal) -> tuple:
        """跨日：_assert_editable + 原条目减 + 目标日 upsert"""
```

## Correctness Properties

### Property 1: Idempotent Collection
二次采集同一 user_id+date 范围，若操作轨迹不变，不产出额外条目（source_ref 幂等）。
**Validates: Requirements 2.4**

### Property 2: Duration Conservation on Split
拆分后各子条目时长之和 === 原条目时长（Decimal 精度 0.01）。
**Validates: Requirements 3.1**

### Property 3: Duration Conservation on Merge
合并后条目时长 === 原各条目时长之和。
**Validates: Requirements 3.2**

### Property 4: Cross-Day Balance
跨日转移后：source_entry.hours_减少 + target_entry.hours_增加 === transfer_hours。
**Validates: Requirements 3.3**

### Property 5: Edit History Append-Only
edit_history JSONB 只追加不删改，每条操作须包含 at/by/action/before/after。
**Validates: Requirements 3.4**

### Property 6: Fail-Open Collection
任一数据源 resolver 抛异常，不阻断其他数据源采集，不阻断用户手工填报。
**Validates: Requirements 9.5**

### Property 7: Status Machine Integrity
状态转换严格：draft→submitted→approved|rejected(→draft)；approved 不可再编辑；**拆分/合并/跨日仅 draft 可操作**。
**Validates: Requirements 7.1-7.3, 3.5**

### Property 8: NLP Parse Preview Only
自然语言解析结果不直接落库，必须经用户确认后才写入（source='llm_parsed' + status='draft'）。
**Validates: Requirements 5.2**

### Property 9: Daily Cap 24h
单用户单日工时总和不得超过 24h（含自动采集+手工+计时器）。超出时采集侧截断+warning。
**Validates: Requirements 1.6**

### Property 10: Timer Priority
同 user+date+project+wp_code 若已有 source='timer' 条目，auto-collect 不为该段产出草稿。
**Validates: Requirements 1.5**

### Property 11: Zero Regression
既有前端组件（WeeklyTimesheet/SideTimerTab/WorkHourApprovalTab/BudgetCompareChart）行为逐字节不变。
**Validates: Requirements 9**

## Error Handling

- 数据源查询失败：fail-open，记 warning 日志，返回已成功采集的部分
- NLP 解析失败/超时：返回空结果+用户提示"解析失败，请手动填写"
- 拆分/合并/跨日状态守卫失败：400 + 清晰中文消息（"该条目已提交，请先退回草稿状态再操作"）
- 拆分时长不守恒：400 + "拆分后总时长(X)与原时长(Y)不一致"
- 迁移 V130 幂等（`IF NOT EXISTS` + information_schema 守护）
- WORKPAPER_SAVED 增量 handler 异常：fail-open 不阻断保存

## Testing Strategy

- P1/P10: Hypothesis PBT（幂等+计时器优先）
- P2/P3/P4: Hypothesis PBT（时长守恒三种操作）
- P5: 单测（edit_history 只追加）
- P6: 集成测试 mock 各数据源分别失败
- P7: 状态机测试（全转换路径 + 拆分/合并/跨日守卫）
- P8/P9: 单测
- P11: 前端 vitest（WeeklyTimesheet 行为守卫）+ Vite transform 200
- Playwright E2E: 采集→预览→拆分→确认→审批全链路
