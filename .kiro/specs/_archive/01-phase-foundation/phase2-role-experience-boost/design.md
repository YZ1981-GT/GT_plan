# Design Document — Phase 2 角色体验提升

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始设计 |

---

## Overview

本设计实现 Phase 2 五项角色体验提升：签字前 Gate Checklist、QC 风险热力图、底稿批量状态变更、Prefill 差异对比面板、复核意见优先级。五项功能分别服务合伙人/质控/项目经理/审计助理/复核流程，相互独立但共享后端基础设施（consistency_gate / prefill_engine / review 模型）。

---

## F1 签字前 Gate Checklist

### 架构设计

```
┌─────────────────────────────────────────────────┐
│ PartnerSignDecision.vue                          │
│   └─ SignGateChecklist.vue                       │
│       ├─ 自动检测项 (7 项，API 驱动)            │
│       │   └─ GET /api/projects/{pid}/sign-gate   │
│       └─ 手动确认项 (3 项，本地状态)            │
│                                                  │
│   └─ 签发按钮 (:disabled="!allPassed")          │
└─────────────────────────────────────────────────┘
```

### 后端 API

```python
# GET /api/projects/{project_id}/sign-gate
# Response:
{
  "checks": [
    {"id": "materiality_confirmed", "label": "重要性水平已确定", "auto": true, "passed": true},
    {"id": "misstatement_reviewed", "label": "错报汇总已审阅", "auto": true, "passed": true},
    {"id": "subsequent_events", "label": "后续事项已评估", "auto": true, "passed": false},
    {"id": "independence_signed", "label": "独立性声明已签署", "auto": true, "passed": true},
    {"id": "all_wp_signed", "label": "所有底稿已签字", "auto": true, "passed": false},
    {"id": "all_comments_closed", "label": "所有复核意见已关闭", "auto": true, "passed": true},
    {"id": "vr_blocking_passed", "label": "VR blocking 规则全部通过", "auto": true, "passed": true},
    {"id": "aje_approved", "label": "调整分录已审批", "auto": false, "passed": null},
    {"id": "notes_consistent", "label": "附注与报表一致", "auto": false, "passed": null},
    {"id": "mgmt_rep_obtained", "label": "管理层声明书已获取", "auto": false, "passed": null}
  ]
}
```

自动检测逻辑：
- `materiality_confirmed`：materiality 表有 confirmed_at 记录
- `misstatement_reviewed`：misstatements 表所有 status != 'pending'
- `subsequent_events`：subsequent_events 表有 reviewed_at 记录
- `independence_signed`：independence_declarations 表当前年度有签署记录
- `all_wp_signed`：working_papers 表无 status='draft'/'in_review' 的记录
- `all_comments_closed`：review_comments 表无 status='open' 的记录
- `vr_blocking_passed`：consistency_gate 最近一次检查无 blocking 失败

### 前端组件

```typescript
// SignGateChecklist.vue
interface GateItem {
  id: string
  label: string
  auto: boolean
  passed: boolean | null  // null = 待手动确认
}

const allPassed = computed(() =>
  gateItems.value.every(item => item.passed === true)
)
```

---

## F2 QC 风险热力图

### 后端聚合 API

```python
# GET /api/projects/{project_id}/qc/vr-heatmap
# Response:
{
  "matrix": [
    {"cycle": "D", "blocking": 2, "warning": 1, "info": 0},
    {"cycle": "E", "blocking": 0, "warning": 3, "info": 1},
    ...
  ],
  "total": {"blocking": 8, "warning": 15, "info": 5}
}
```

实现：查询 consistency_gate 最近一次全量检查结果，按 cycle + severity 分组 COUNT。

### 前端组件

```typescript
// VRHeatmap.vue — 使用 ECharts heatmap 图表类型
// 或纯 CSS grid（11 行 × 3 列，单元格背景色按数量映射）

// 颜色映射（致同品牌色系）
const COLOR_SCALE = {
  blocking: ['#fff', '#ffcdd2', '#ef5350', '#c62828'],  // 白→浅红→红→深红
  warning: ['#fff', '#fff3e0', '#ff9800', '#e65100'],   // 白→浅橙→橙→深橙
  info: ['#fff', '#f5f5f5', '#bdbdbd', '#616161'],      // 白→浅灰→灰→深灰
}
```

### ADR-F2: 纯 CSS Grid vs ECharts Heatmap

**决策**：使用纯 CSS Grid（11×3 表格），不用 ECharts heatmap。

**理由**：
1. 数据量极小（33 个单元格），ECharts 过重
2. 需要点击单元格跳转路由，CSS Grid + @click 更直接
3. 避免 ECharts 在 QCDashboard 中的 ResizeObserver 问题（已有前车之鉴）
4. 样式与致同品牌色系更容易精确控制

---

## F3 底稿批量状态变更

### 后端 API

```python
# POST /api/projects/{project_id}/workpapers/batch-status
# Request:
{
  "wp_ids": ["uuid1", "uuid2", ...],
  "action": "submit_review" | "return_to_draft" | "mark_complete",
  "comment": "批量提交复核"  # 可选
}
# Response:
{
  "success_count": 8,
  "skipped": [
    {"wp_id": "uuid3", "reason": "当前状态不允许此操作（已签字）"}
  ]
}
```

### 事务策略

```python
async with db.begin_nested():  # SAVEPOINT
    for wp_id in body.wp_ids:
        wp = await db.get(WorkingPaper, wp_id)
        if not can_transition(wp.status, body.action):
            skipped.append({"wp_id": str(wp_id), "reason": f"状态 {wp.status} 不允许 {body.action}"})
            continue
        wp.status = next_status(body.action)
        success_count += 1
    # 不回滚 skipped 项，仅跳过
```

注意：批量操作不触发版本锁（版本锁仅保护 parsed_data 内容变更，状态变更是独立字段）。

### 前端组件

```
┌─────────────────────────────────────────────────┐
│ WorkpaperList.vue                                │
│   ├─ BatchActionBar.vue (v-if="selectedCount>0")│
│   │   └─ "已选 N 个" + [提交复核] [退回] [完成] │
│   └─ el-table (新增 type="selection" 列)        │
└─────────────────────────────────────────────────┘
```

---

## F4 Prefill 差异对比面板

### ADR-F4: dry_run 模式 vs 独立 preview 函数

**决策**：在现有 `prefill_workpaper_real` 中增加 `dry_run: bool = False` 参数，而非新建独立函数。

**理由**：
1. prefill_engine 是"计算即写入 structure.json"的紧耦合模式（代码锚定确认）
2. 新建独立函数会导致大量代码重复（公式解析+执行逻辑完全相同）
3. dry_run 模式仅跳过"写入 structure.json"步骤，收集 diff 列表返回
4. 向后兼容：dry_run 默认 False，现有调用方无需修改

### 后端 API 改造

```python
# POST /api/projects/{pid}/working-papers/{wp_id}/prefill/preview
# 内部调用 prefill_workpaper_real(db, project_id, year, wp_id, dry_run=True)
# Response:
{
  "changes": [...],
  "summary": { "total_changes": 15, "new_cells": 3, "modified_cells": 12, "highlight_count": 2 }
}

# POST /api/projects/{pid}/working-papers/{wp_id}/prefill/apply
# Request: { "accepted_cells": ["E5", "E6", "F3", ...] }
# 内部：仅对 accepted_cells 执行写入 structure.json
```

### 前端组件

```
┌─────────────────────────────────────────────────┐
│ PrefillDiffPanel.vue (el-dialog, 宽度 800px)    │
│   ├─ 汇总统计栏                                 │
│   ├─ el-table (changes 列表)                    │
│   │   ├─ checkbox 列（逐项选择）                │
│   │   ├─ sheet 列                               │
│   │   ├─ cell 位置列                            │
│   │   ├─ 旧值列 (红色删除线)                    │
│   │   ├─ 新值列 (绿色)                          │
│   │   └─ 变动幅度列 (≥20% 黄色高亮)            │
│   └─ 底部按钮：[全部接受] [应用选中] [取消]     │
└─────────────────────────────────────────────────┘
```

---

## F5 复核意见优先级

### 数据库变更

```sql
-- V00X__add_review_priority.sql（编号实施时动态确定 max+1）
ALTER TABLE review_records ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'suggest';
-- CHECK (priority IN ('must_fix', 'suggest', 'info'))
```

### 前端组件改造

ReviewWorkbench.vue 中的意见录入表单新增优先级选择器：

```html
<el-radio-group v-model="newComment.priority" size="small">
  <el-radio-button value="must_fix">🔴 必须修改</el-radio-button>
  <el-radio-button value="suggest">🟠 建议修改</el-radio-button>
  <el-radio-button value="info">⚪ 仅供参考</el-radio-button>
</el-radio-group>
```

### 提交拦截逻辑

```typescript
// WorkpaperEditor.vue onSubmitForReview()
const openMustFix = await reviewApi.getOpenComments(wpId, { priority: 'must_fix' })
if (openMustFix.length > 0) {
  ElMessage.warning(`还有 ${openMustFix.length} 条"必须修改"意见未处理，请先处理后再提交`)
  return
}
```

---

## Error Handling

| 场景 | 处理方式 |
|------|---------|
| F1 Gate API 超时 | 自动检测项显示"检测中..."，不阻塞手动项 |
| F2 热力图 API 无数据 | 显示全白矩阵 + "暂无 VR 检查结果"提示 |
| F3 批量操作部分失败 | 显示成功数 + 跳过列表（不回滚成功项） |
| F4 prefill preview 超时 | 提示"计算超时，请稍后重试"，不自动覆盖 |
| F5 优先级字段缺失（旧数据） | 默认视为 suggest（向后兼容） |

---

## 测试策略

### 后端测试

| 文件 | 覆盖 |
|------|------|
| `test_sign_gate_checklist.py` | F1：7 项自动检测逻辑 + 全通过/部分失败 |
| `test_vr_heatmap_aggregation.py` | F2：按循环×severity 聚合 + 空数据 |
| `test_batch_status_change.py` | F3：批量提交/退回/完成 + 部分跳过 + 权限 |
| `test_prefill_preview.py` | F4：preview 返回 diff + apply 写入 + 变动幅度计算 |
| `test_review_priority.py` | F5：优先级 CRUD + must_fix 拦截 |

### 前端测试

| 文件 | 覆盖 |
|------|------|
| `SignGateChecklist.spec.ts` | F1：渲染 10 项 + 全通过启用按钮 + 部分失败禁用 |
| `VRHeatmap.spec.ts` | F2：矩阵渲染 + 颜色映射 + 点击跳转 |
| `BatchActionBar.spec.ts` | F3：选中计数 + 操作按钮 + 确认弹窗 |
| `PrefillDiffPanel.spec.ts` | F4：diff 列表渲染 + 高亮 + 全部接受/逐项 |
| `ReviewPrioritySelector.spec.ts` | F5：优先级选择 + 排序 + 拦截提示 |
