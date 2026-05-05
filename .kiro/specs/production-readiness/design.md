# 设计文档：生产就绪改进（production-readiness）

## 概述

本文档描述审计作业平台生产就绪改进的技术设计方案。平台面向会计师事务所，目标并发 6000 人，技术栈为 FastAPI + SQLAlchemy（异步）+ PostgreSQL + Redis（后端）、Vue 3 + TypeScript + Element Plus + Univer（前端）。

本次改进涵盖 12 个需求，按优先级分为四类：
- **P0（数据正确性）**：需求 1（底稿→附注同步）、需求 2（Dashboard 趋势图）、需求 3（Dirty 标记）
- **P1（核心流程）**：需求 4（复核收件箱导航）、需求 5（UUID→姓名映射）
- **P2（体验优化）**：需求 6（进度百分比）、需求 7（步骤引导）、需求 8（借贷平衡修正）
- **P3（生产部署）**：需求 9（PostgreSQL 迁移）、需求 10（Worker 拆分）、需求 11（路由前缀统一）、需求 12（压测验证）

---

## 架构

### 整体架构图

```mermaid
graph TB
    subgraph 前端 Vue3
        WE[WorkpaperEditor.vue<br/>底稿编辑器]
        DE[DisclosureEditor.vue<br/>附注编辑器]
        DB[Dashboard.vue<br/>仪表盘]
        WL[WorkpaperList.vue<br/>底稿列表]
        TB[TrialBalance.vue<br/>试算平衡表]
        LP[LedgerPenetration.vue<br/>账套穿透/导入入口]
        DL[DefaultLayout.vue<br/>主布局/导航菜单]
        EB[eventBus<br/>mitt 事件总线]
    end

    subgraph 后端 FastAPI
        DR[dashboard.py<br/>路由器]
        DS[dashboard_service.py<br/>服务层]
        RR[router_registry.py<br/>路由注册中心]
        ML[main.py lifespan<br/>生命周期编排]
        subgraph Workers
            SW[sla_worker.py]
            IW[import_recover_worker.py]
            OW[outbox_replay_worker.py]
        end
    end

    subgraph 数据层
        PG[(PostgreSQL)]
        RD[(Redis)]
    end

    WE -- emit workpaper:saved --> EB
    EB -- on workpaper:saved --> DE
    DB -- GET /api/dashboard/stats/trend --> DR
    DR --> DS --> PG
    ML --> SW
    ML --> IW
    ML --> OW
    RR -- prefix=/api --> 所有路由器
```

### 关键设计原则

1. **最小侵入**：优先在现有文件上扩展，不引入新的架构层
2. **前后端联动**：每个需求同时覆盖前端和后端变更
3. **向后兼容**：路由前缀统一不破坏现有 API 调用
4. **优雅降级**：Worker 异常不影响主应用，附注刷新失败提供手动重试

---

## 组件与接口

### 需求 1：底稿保存事件触发附注自动刷新

#### 设计方案

利用现有 `eventBus`（mitt）实现跨组件通信，无需引入新的通信机制。

**事件流：**
```
WorkpaperEditor.onSave() 成功
  → eventBus.emit('workpaper:saved', { projectId, wpId, year })
  → DisclosureEditor 监听 'workpaper:saved'
  → debounce(1000ms) 防抖
  → refreshDisclosureFromWorkpapers(projectId, year)
```

**eventBus.ts 新增事件类型：**
```typescript
// 新增到 Events 映射表
'workpaper:saved': WorkpaperSavedPayload

export interface WorkpaperSavedPayload {
  projectId: string
  wpId: string
  year?: number
}
```

**WorkpaperEditor.vue 修改点（`onSave` 函数末尾）：**
```typescript
// 保存成功后发布事件
dirty.value = false
ElMessage.success(result?.message || '保存成功')
eventBus.emit('workpaper:saved', {
  projectId: projectId.value,
  wpId: wpId.value,
  year: year.value,
})
```

**DisclosureEditor.vue 修改点（`onMounted` + `onBeforeUnmount`）：**
```typescript
// 使用原生 setTimeout 实现防抖，避免引入 @vueuse/core 依赖
let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null

const syncError = ref(false)

function onWorkpaperSaved(payload: WorkpaperSavedPayload) {
  if (payload.projectId !== projectId.value) return
  if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
  syncDebounceTimer = setTimeout(async () => {
    syncError.value = false
    try {
      await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
    } catch {
      syncError.value = true
    }
  }, 1000)
}

// onMounted 中注册
onMounted(() => {
  eventBus.on('workpaper:saved', onWorkpaperSaved)
})

// onBeforeUnmount 中清理
onBeforeUnmount(() => {
  eventBus.off('workpaper:saved', onWorkpaperSaved)
  if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
})
```

注意：`WorkpaperEditor.vue` 中若没有 `year` 变量，需从路由参数获取：
```typescript
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)
```

**同步失败提示 UI（DisclosureEditor.vue 模板）：**
```html
<el-alert
  v-if="syncError"
  type="error"
  title="底稿数据同步失败"
  description="无法自动从底稿刷新附注数据"
  show-icon
  :closable="false"
>
  <template #default>
    <el-button size="small" @click="onRefreshFromWP">手动重试</el-button>
  </template>
</el-alert>
```

### 需求 2：Dashboard 趋势图接入真实 API 数据

#### 后端：新增 `/api/dashboard/stats/trend` 接口

**文件：`backend/app/routers/dashboard.py`**（新增路由）
```python
@router.get("/stats/trend")
async def stats_trend(
    project_id: str | None = None,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = DashboardService(db)
    return await svc.get_stats_trend(project_id=project_id, days=days)
```

**文件：`backend/app/services/dashboard_service.py`**（新增方法）
```python
async def get_stats_trend(self, project_id: str | None, days: int = 7) -> dict:
    """近 N 天各状态底稿数量趋势（单次 SQL 聚合，避免 N 次查询）"""
    from app.models.workpaper_models import WorkingPaper
    from datetime import date, timedelta
    import sqlalchemy as sa

    start_date = date.today() - timedelta(days=days - 1)

    q = (
        sa.select(
            sa.func.date(WorkingPaper.updated_at).label("day"),
            WorkingPaper.status,
            sa.func.count(WorkingPaper.id).label("cnt"),
        )
        .where(
            WorkingPaper.is_deleted == sa.false(),
            sa.func.date(WorkingPaper.updated_at) >= start_date,
        )
        .group_by(sa.func.date(WorkingPaper.updated_at), WorkingPaper.status)
        .order_by(sa.func.date(WorkingPaper.updated_at))
    )
    if project_id:
        from uuid import UUID
        q = q.where(WorkingPaper.project_id == UUID(project_id))

    rows = (await self.db.execute(q)).all()

    # 预填所有日期（补全无数据的日期）
    trend: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        trend[d] = {}
    for r in rows:
        day_str = str(r.day)
        if day_str in trend:
            trend[day_str][r.status] = r.cnt

    return {"days": days, "trend": trend}
```

**响应格式：**
```json
{
  "days": 7,
  "trend": {
    "2025-05-01": { "review_passed": 3, "in_progress": 5 },
    "2025-05-02": { "review_passed": 4, "in_progress": 6 }
  }
}
```

#### 前端：Dashboard.vue 修改

**移除硬编码 sparkData，改为 API 调用：**
```typescript
// 删除 Mock sparkline data 块
// 新增
const trendData = ref<Record<string, Record<string, number>>>({})

async function loadTrendData() {
  try {
    const res = await httpApi.get('/api/dashboard/stats/trend', {
      params: { project_id: currentProjectId.value, days: 7 }
    })
    trendData.value = res.trend || {}
  } catch {
    trendLoadError.value = true
  }
}

// 从 trendData 提取各状态近 7 天数组
const sparkSeries = computed(() => {
  const days = Object.keys(trendData.value).sort()
  return {
    review_passed: days.map(d => trendData.value[d]?.review_passed ?? 0),
    in_progress:   days.map(d => trendData.value[d]?.in_progress ?? 0),
  }
})
```

**错误状态处理：**
```html
<template v-if="trendLoadError">
  <el-empty description="趋势数据加载失败" :image-size="60" />
</template>
<template v-else>
  <!-- 原有趋势图渲染，使用 sparkSeries 替代 sparkData -->
</template>
```

### 需求 3：底稿编辑器 Dirty 标记完整覆盖

#### 现状分析

当前 `WorkpaperEditor.vue` 中 `onCommandExecuted` 仅过滤 `set-range-values` 和 `set-cell` 两类命令，遗漏了公式输入和格式变更相关命令。

#### Univer 命令 ID 覆盖范围

根据 Univer 文档，需要覆盖的命令 ID 前缀：

| 类别 | 命令 ID 前缀/关键词 |
|------|-------------------|
| 单元格内容 | `set-range-values`, `set-cell` |
| 公式输入 | `set-formula`, `formula.`, `array-formula` |
| 格式变更 | `set-style`, `set-border`, `set-number-format`, `set-font` |
| 内容删除 | `clear-selection`, `delete-range` |
| 行列操作 | `insert-row`, `insert-col`, `remove-row`, `remove-col` |
| 合并单元格 | `merge-cells`, `unmerge-cells` |

**修改 `WorkpaperEditor.vue` 中的命令过滤逻辑：**
```typescript
// 替换现有的 onCommandExecuted 回调
const DIRTY_COMMAND_PATTERNS = [
  'set-range-values', 'set-cell',
  'set-formula', 'formula.', 'array-formula',
  'set-style', 'set-border', 'set-number-format', 'set-font',
  'clear-selection', 'delete-range',
  'insert-row', 'insert-col', 'remove-row', 'remove-col',
  'merge-cells', 'unmerge-cells',
]

univerAPI.onCommandExecuted((command: any) => {
  if (DIRTY_COMMAND_PATTERNS.some(p => command.id?.includes(p))) {
    dirty.value = true
  }
})
```

**未保存提示 UI（工具栏区域）：**
```html
<span v-if="dirty" class="gt-dirty-indicator">
  <el-icon><Warning /></el-icon> 有未保存的变更
</span>
```

**路由离开守卫（`onBeforeRouteLeave`）：**
```typescript
import { onBeforeRouteLeave } from 'vue-router'

onBeforeRouteLeave(async (to, from, next) => {
  if (!dirty.value) { next(); return }
  try {
    await ElMessageBox.confirm(
      '当前底稿有未保存的变更，离开将丢失这些变更。',
      '确认离开',
      { confirmButtonText: '放弃变更', cancelButtonText: '继续编辑', type: 'warning' }
    )
    next()
  } catch {
    next(false)
  }
})
```

---

### 需求 4：复核收件箱导航入口可达性

#### 现状分析

`DefaultLayout.vue` 使用 `ThreeColumnLayout` + `FourColumnCatalog` 组合布局，**没有传统的侧边栏导航菜单**。导航入口由 `ThreeColumnLayout` 内部管理，不能直接在 `DefaultLayout.vue` 模板里写 `<router-link>`。

实施前必须先读取 `ThreeColumnLayout.vue` 确认可用的 slot 结构，再决定具体插入位置。

#### 备选方案

**方案 A（推荐）**：在 `ThreeColumnLayout.vue` 的顶部导航栏或图标栏 slot 中添加入口。需先确认 `ThreeColumnLayout.vue` 是否暴露 `#header` 或 `#nav-icons` 等 slot。

**方案 B（兜底）**：在 `FourColumnCatalog.vue` 的顶部区域添加复核收件箱快捷入口，仅在项目上下文中可见。

**方案 C（最简）**：在 `DefaultLayout.vue` 的 `<template #detail>` 区域之外，通过 `ThreeColumnLayout` 的某个已有 slot 注入。

#### 实施步骤

**子任务 5.0（前置）**：读取 `ThreeColumnLayout.vue` 确认 slot 结构，根据实际 slot 选择方案 A/B/C。

**确认 slot 后的实现（以方案 A 为例）：**
```html
<!-- 在 ThreeColumnLayout 的导航 slot 中 -->
<template #nav-extra>
  <router-link
    v-if="roleStore.hasRole(['reviewer', 'partner', 'admin'])"
    to="/review-inbox"
    class="gt-nav-item"
  >
    <el-badge :value="pendingReviewCount" :hidden="pendingReviewCount === 0">
      <el-icon><Inbox /></el-icon>
      <span>复核收件箱</span>
    </el-badge>
  </router-link>
</template>
```

**pendingReviewCount 数据来源（DefaultLayout.vue script）：**
```typescript
import { useRoleContextStore } from '@/stores/roleContext'
import { getGlobalReviewInbox } from '@/services/pmApi'

const roleStore = useRoleContextStore()
const pendingReviewCount = ref(0)

async function loadPendingReviewCount() {
  if (!roleStore.hasRole(['reviewer', 'partner', 'admin'])) return
  try {
    const res = await getGlobalReviewInbox(1, 1)
    pendingReviewCount.value = res.total || 0
  } catch { /* 静默失败 */ }
}

onMounted(loadPendingReviewCount)
// 每 5 分钟刷新一次 badge
const badgeTimer = setInterval(loadPendingReviewCount, 5 * 60 * 1000)
onBeforeUnmount(() => clearInterval(badgeTimer))
```

### 需求 5：底稿列表负责人姓名显示

#### 现状分析

`WorkpaperList.vue` 中 `assigned_to` 字段直接展示 UUID 字符串（如 `{{ selectedWp.assigned_to || '未分配' }}`），`userOptions` 已有用户列表数据但未用于映射显示。

#### 设计方案

在底稿列表加载时批量请求用户信息，建立本地 `Map<uuid, displayName>` 缓存，所有 UUID 展示点统一通过 `resolveUserName(uuid)` 函数转换。

注意：`listUsers` 返回的用户对象字段为 `id`（UUID）和 `username`（用户名），映射 key 使用 `u.id`。

**WorkpaperList.vue 修改：**
```typescript
// 新增用户名映射 Map（key = UUID 字符串）
const userNameMap = ref<Map<string, string>>(new Map())

// 加载用户列表时同步建立映射
async function loadUserOptions() {
  try {
    const users = await listUsers()  // 已有接口，返回 { id: uuid, username: string, full_name?: string }
    userOptions.value = users
    userNameMap.value = new Map(
      users.map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默 */ }
}

// UUID → 姓名转换函数
function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}
```

**模板中替换所有 UUID 展示点：**
```html
<!-- 原来 -->
<el-descriptions-item label="编制人">{{ selectedWp.assigned_to || '未分配' }}</el-descriptions-item>

<!-- 修改后 -->
<el-descriptions-item label="编制人">{{ resolveUserName(selectedWp.assigned_to) }}</el-descriptions-item>
```

树形节点中同样替换：
```html
<!-- 树节点 label 中的 assigned_to 展示 -->
{{ resolveUserName(node.assigned_to) }}
```

---

### 需求 6：底稿列表整体进度百分比

#### 设计方案

纯前端计算，基于已加载的底稿列表数据中 `status` 字段统计，无需新增后端接口。

注意：`WorkpaperList.vue` 中没有 `filteredWorkpapers` computed，筛选状态由 `filterCycle`、`filterStatus`、`searchKeyword` 等 ref 控制，实际渲染的是 `treeData`（树形结构）。进度计算基于 `wpList`（原始底稿列表），筛选进度需手动过滤。

`edit_complete` 不算"已完成"，完成状态应为 `review_passed` 或 `archived`。

**WorkpaperList.vue 新增计算属性：**
```typescript
// 定义"已完成"状态集合（edit_complete 不算完成，需通过复核才算）
const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])

// 全量进度（基于 wpList 所有底稿）
const totalProgress = computed(() => {
  if (!wpList.value.length) return { completed: 0, total: 0, percent: 0 }
  const completed = wpList.value.filter(w => COMPLETED_STATUSES.has(w.status || '')).length
  return {
    completed,
    total: wpList.value.length,
    percent: Math.floor((completed / wpList.value.length) * 100),
  }
})

// 筛选后进度（基于现有筛选条件过滤 wpList）
const filteredWpList = computed(() => {
  return wpList.value.filter(w => {
    if (filterCycle.value && w.audit_cycle !== filterCycle.value) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      return w.wp_code?.toLowerCase().includes(kw) || w.wp_name?.toLowerCase().includes(kw)
    }
    return true
  })
})

const filteredProgress = computed(() => {
  if (!filteredWpList.value.length) return { completed: 0, total: 0, percent: 0 }
  const completed = filteredWpList.value.filter(w => COMPLETED_STATUSES.has(w.status || '')).length
  return {
    completed,
    total: filteredWpList.value.length,
    percent: Math.floor((completed / filteredWpList.value.length) * 100),
  }
})

// 是否有筛选条件
const hasFilter = computed(() =>
  !!(filterCycle.value || filterStatus.value || searchKeyword.value)
)
```
```

**模板中添加进度指示器（页面顶部）：**
```html
<div class="gt-progress-bar">
  <span class="gt-progress-label">
    总体进度：{{ totalProgress.completed }}/{{ totalProgress.total }}
  </span>
  <el-progress
    :percentage="totalProgress.percent"
    :stroke-width="10"
    style="width: 200px; display: inline-block"
  />
  <span class="gt-progress-pct">{{ totalProgress.percent }}%</span>
  <el-divider direction="vertical" v-if="hasFilter" />
  <span v-if="hasFilter" class="gt-progress-label gt-progress-filtered">
    筛选结果：{{ filteredProgress.percent }}%
    （{{ filteredProgress.completed }}/{{ filteredProgress.total }}）
  </span>
</div>
```

### 需求 7：项目启动流程步骤引导

#### 现状分析

`LedgerPenetration.vue` 中导入功能通过 `goToImport()` 跳转到 `LedgerImportHistory` 页面实现，不是在当前页面内弹窗。步骤引导需要跨页面状态，不能只在 `LedgerPenetration.vue` 内部实现。

最可落地的方案：在 `TrialBalance.vue` 的空数据提示区域（已有 `rows.length === 0` 的引导提示）扩展为步骤条，因为试算表是整个流程的终点，用户在这里最需要知道"还差哪一步"。步骤状态通过 `localStorage` 持久化，key 为 `setup_step_{projectId}`。

#### 设计方案

**TrialBalance.vue 新增步骤状态（空数据时显示）：**
```typescript
type SetupStep = 0 | 1 | 2 | 3  // 0=导入, 1=映射, 2=重算, 3=完成

// 从 localStorage 恢复步骤状态
const setupCurrentStep = computed({
  get: () => {
    const saved = localStorage.getItem(`setup_step_${projectId.value}`)
    return saved ? parseInt(saved) : 0
  },
  set: (val: number) => {
    localStorage.setItem(`setup_step_${projectId.value}`, String(val))
  }
})

// 步骤状态数组（基于 setupCurrentStep 推导）
const setupStepStatus = computed(() =>
  [0, 1, 2].map(i =>
    i < setupCurrentStep.value ? 'finish' :
    i === setupCurrentStep.value ? 'process' : 'wait'
  ) as ('wait' | 'process' | 'finish')[]
)

// 是否显示步骤引导（试算表无数据时显示）
const showSetupGuide = computed(() => rows.value.length === 0)
```

**模板中扩展空数据区域（替换原有 el-alert）：**
```html
<div v-if="showSetupGuide" class="gt-setup-guide">
  <el-steps :active="setupCurrentStep" finish-status="success" align-center>
    <el-step title="数据导入" description="上传账套 Excel/CSV" :status="setupStepStatus[0]" />
    <el-step title="科目映射" description="确认科目分类映射" :status="setupStepStatus[1]" />
    <el-step title="重新计算" description="触发试算表重算" :status="setupStepStatus[2]" />
  </el-steps>

  <div class="gt-setup-actions" style="margin-top: 16px; text-align: center">
    <el-button
      v-if="setupCurrentStep === 0"
      type="primary"
      @click="$router.push(`/projects/${projectId}/ledger`)"
    >
      前往导入数据
    </el-button>
    <el-button
      v-else-if="setupCurrentStep === 1"
      type="primary"
      @click="$router.push(`/projects/${projectId}/ledger?tab=mapping`)"
    >
      前往科目映射
    </el-button>
    <el-button
      v-else-if="setupCurrentStep === 2"
      type="primary"
      @click="onRecalc"
    >
      立即重新计算
    </el-button>
  </div>
</div>
```

**步骤推进函数（在各完成回调中调用）：**
```typescript
function advanceSetupStep() {
  if (setupCurrentStep.value < 3) {
    setupCurrentStep.value = setupCurrentStep.value + 1
  }
}
```

---

### 需求 8：借贷平衡指示器损益类科目修正

#### 现状分析

`TrialBalance.vue` 中 `isBalanced` 仅计算 `asset` vs `liability + equity`，未纳入 `income`（收入）、`cost`（成本）、`expense`（费用）类科目。

#### 修正后的计算逻辑

会计恒等式为：**资产 = 负债 + 权益 + 损益净额**（收入 - 成本 - 费用），这在任何时点都成立，无需区分期中/期末模式。`projectStore.currentProject` 中没有 `audit_type` 字段，不应依赖该字段。

**TrialBalance.vue 修改：**
```typescript
// 损益净额（收入 - 成本 - 费用）
const incomeNetAmount = computed(() => {
  const liabEquity = rows.value
    .filter(r => ['liability', 'equity'].includes(r.account_category || ''))
    .reduce((s, r) => s + num(r.audited_amount), 0)
  const incomeNet = rows.value
    .filter(r => ['income', 'cost', 'expense'].includes(r.account_category || ''))
    .reduce((s, r) => s + num(r.audited_amount), 0)
  return liabEquity + incomeNet
})

// 修正后的负债权益侧合计（始终含损益净额）
const liabEquityTotal = computed(() => incomeNetAmount.value)

// isBalanced 逻辑不变，差额计算自动正确
const balanceDiff = computed(() => assetTotal.value - liabEquityTotal.value)
const isBalanced = computed(() => {
  if (!rows.value.length) return true
  return Math.abs(balanceDiff.value) < 1
})
```

**Tooltip 文案更新（固定显示完整会计恒等式）：**
```html
<el-tooltip
  :content="isBalanced
    ? '资产 = 负债 + 权益 + 损益净额'
    : `差额：${fmt(Math.abs(balanceDiff))} 元`"
>
```

### 需求 9：数据库迁移至 PostgreSQL

#### 现状分析

- 系统已有 Alembic 迁移框架（`backend/app/migrations/`）和自定义 `MigrationRunner`
- `settings.DATABASE_URL` 已支持环境变量切换
- 需要验证 144 张表的迁移脚本完整性

#### 迁移策略

**步骤 1：验证 Alembic 迁移脚本完整性**

```bash
# 在 PostgreSQL 测试环境执行
cd backend
DATABASE_URL="postgresql+asyncpg://user:pass@localhost/audit_test" \
  python -m alembic upgrade head

# 验证表数量
python -c "
import asyncio
from app.core.database import async_session
from sqlalchemy import text

async def check():
    async with async_session() as db:
        result = await db.execute(text(
            \"SELECT count(*) FROM information_schema.tables \"
            \"WHERE table_schema='public'\"
        ))
        print('表数量:', result.scalar())

asyncio.run(check())
"
```

**步骤 2：补全缺失的迁移脚本**

若发现表数量不足 144，需为缺失的模型生成迁移：
```bash
python -m alembic revision --autogenerate -m "add_missing_tables"
python -m alembic upgrade head
```

**步骤 3：环境变量配置**

`.env.example` 中添加说明：
```bash
# 生产环境（PostgreSQL）
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/audit_db

# 开发环境（SQLite，可选）
# DATABASE_URL=sqlite+aiosqlite:///./audit.db
```

**步骤 4：SQLAlchemy 方言兼容性检查**

PostgreSQL 与 SQLite 的差异点：
- `JSON` 类型：两者均支持，无需修改
- `ARRAY` 类型：若有使用需确认（PostgreSQL 原生支持，SQLite 不支持）
- `RETURNING` 子句：asyncpg 支持，aiosqlite 不支持（检查现有代码）
- 大小写敏感：PostgreSQL 标识符默认小写，检查模型定义

**步骤 5：连接池配置（生产环境）**

`backend/app/core/database.py` 中针对 PostgreSQL 优化连接池：
```python
if settings.DATABASE_URL.startswith("postgresql"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=20,          # 基础连接数
        max_overflow=80,       # 最大溢出（总计 100 连接）
        pool_timeout=30,
        pool_recycle=1800,
        echo=False,
    )
```

---

### 需求 10：后台定时任务模块化拆分

#### 目标结构

```
backend/app/workers/
├── __init__.py
├── import_worker.py          # 已有
├── sla_worker.py             # 新增：SLA 超时检查
├── import_recover_worker.py  # 新增：导入任务恢复
└── outbox_replay_worker.py   # 新增：Outbox 重放
```

#### sla_worker.py

```python
"""SLA 超时检查 Worker — 每 15 分钟检查一次"""
import asyncio
import logging

logger = logging.getLogger("sla_check")

async def run(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.sleep(900)
            if stop_event.is_set():
                break
            from app.core.database import async_session
            from app.services.issue_ticket_service import issue_ticket_service
            async with async_session() as db:
                escalated = await issue_ticket_service.check_sla_timeout(db)
                if escalated:
                    await db.commit()
                    logger.info("[SLA] auto-escalated %d issues", len(escalated))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[SLA] check loop error: %s", e)
```

#### import_recover_worker.py

```python
"""导入任务恢复 Worker — 每 30 秒检查一次"""
import asyncio
import logging
from app.core.config import settings

logger = logging.getLogger("import_recover")

async def run(stop_event: asyncio.Event) -> None:
    if not settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
        return
    while not stop_event.is_set():
        try:
            from app.services.import_job_runner import ImportJobRunner
            await ImportJobRunner.recover_jobs()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[ImportRecover] loop error: %s", e)
```

#### outbox_replay_worker.py

将 `main.py` 中 `_outbox_replay_loop` 的完整逻辑迁移至此文件，函数签名改为 `async def run(stop_event: asyncio.Event) -> None`，内部将 `while True` 改为 `while not stop_event.is_set()`。

#### 精简后的 main.py lifespan（目标 ~25 行）

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level="INFO", json_format=False)
    await _run_migrations()
    register_event_handlers()
    _register_phase_handlers()

    stop_event = asyncio.Event()
    tasks = await _start_workers(stop_event)

    yield

    stop_event.set()
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    from app.core.database import dispose_engine
    await dispose_engine()
```

辅助函数提取到 `main.py` 顶部（私有函数，不影响模块接口）：
- `_run_migrations()` — 数据库迁移逻辑
- `_register_phase_handlers()` — Phase 14/15 事件处理器注册
- `_start_workers(stop_event)` — 启动所有 worker，返回 task 列表

### 需求 11：路由前缀规范统一

#### 实际代码现状（已验证）

| 路由器文件 | 内部 prefix | 注册方式 | 最终路径 |
|-----------|------------|---------|---------|
| `gate.py` | `/gate` | 域 7，无额外前缀 → 需加 `/api` | `/api/gate/...` |
| `trace.py` | `/trace` | 域 7，无额外前缀 → 需加 `/api` | `/api/trace/...` |
| `sod.py` | `/sod` | 域 7，无额外前缀 → 需加 `/api` | `/api/sod/...` |
| `task_tree.py` | `/task-tree` | Phase 15，已加 `prefix="/api"` | `/api/task-tree/...` ✓ |
| `issues.py` | `/issues` | Phase 15，已加 `prefix="/api"` | `/api/issues/...` ✓ |
| `task_events.py` | `/task-events` | Phase 15，已加 `prefix="/api"` | `/api/task-events/...` ✓ |
| `version_line.py` | `/version-line` | Phase 16，已加 `prefix="/api"` | `/api/version-line/...` ✓ |
| `offline_conflicts.py` | `/offline/conflicts` | Phase 16，已加 `prefix="/api"` | `/api/offline/conflicts/...` ✓ |
| `dashboard.py` | `/api/dashboard` | 域 7，**不加额外前缀** | `/api/dashboard/...` ✓ |

#### 真正需要修复的问题

**只有一件事**：删除 Phase 14 的 `hasattr` 补丁，改为直接 `prefix="/api"`。

Phase 15/16 路由器已经正确注册（内部无 `/api`，注册时加 `prefix="/api"`），**无需修改**。

`dashboard.py` 内部带 `/api/dashboard`，注册时不加额外前缀，路径正确，**无需修改**。

#### router_registry.py 修改

```python
# 原来（Phase 14 hasattr 补丁）：
for r in [gate_router, trace_router, sod_router]:
    app.include_router(
        r,
        prefix="/api" if not hasattr(r, 'prefix') or not r.prefix.startswith('/api') else "",
        tags=["门禁与治理"]
    )

# 修改后（直接加 /api，因为 gate/trace/sod 内部都没有 /api）：
for r in [gate_router, trace_router, sod_router]:
    app.include_router(r, prefix="/api", tags=["门禁与治理"])
```

**注释规范（router_registry.py 文件头）：**
```python
"""路由注册表 — 按业务域分组

路由前缀规范（IMPORTANT）：
  - 标准做法：路由器内部 prefix 只声明业务路径（如 prefix="/gate"），
    本文件在 include_router 时统一添加 prefix="/api"
  - 最终路径 = /api + 路由器内部路径 + 端点路径

已知例外（不要修改）：
  - dashboard.py：内部 prefix="/api/dashboard"，注册时不加额外前缀
  - /wopi 路由：不加 /api 前缀（WOPI 协议要求）
  - /api/version：直接定义在 main.py（版本探针）
"""
```

---

### 需求 12：6000 人并发压测验证

#### 压测方案

使用现有 `load_test.py`，针对核心业务接口进行压测。

**压测目标接口：**
1. `POST /api/auth/login` — 登录
2. `GET /api/projects/{id}/working-papers` — 底稿列表
3. `GET /api/projects/{id}/working-papers/{wp_id}` — 底稿详情
4. `GET /api/projects/{id}/disclosure-notes` — 附注查询
5. `GET /api/dashboard/overview` — 仪表盘概览

**性能目标：**
- 平均响应时间 ≤ 2000ms
- P99 响应时间 ≤ 5000ms
- 错误率 < 1%（HTTP 5xx）

**压测前置条件：**
- PostgreSQL 已就绪（SQLite 不支持高并发）
- Redis 已就绪（缓存层）
- 数据库中有足够的测试数据（至少 10 个项目，每项目 80+ 底稿）

**报告输出格式：**
```json
{
  "summary": {
    "total_requests": 60000,
    "duration_seconds": 60,
    "tps": 1000,
    "avg_response_ms": 450,
    "p95_response_ms": 1200,
    "p99_response_ms": 2800,
    "error_rate": 0.003
  },
  "endpoints": [
    {
      "path": "/api/projects/{id}/working-papers",
      "avg_ms": 380,
      "p99_ms": 1800,
      "error_rate": 0.001
    }
  ],
  "bottlenecks": [],
  "slow_queries": []
}
```

---

## 数据模型

### 新增：WorkpaperSavedPayload（前端事件类型）

```typescript
// eventBus.ts 新增
export interface WorkpaperSavedPayload {
  projectId: string   // 项目 ID
  wpId: string        // 底稿 ID
  year?: number       // 审计年度（可选，用于附注刷新定位）
}
```

### 新增：趋势图 API 响应模型

```python
# backend/app/schemas/dashboard_schemas.py 新增
class TrendDayData(BaseModel):
    date: str                          # ISO 日期字符串
    status_counts: dict[str, int]      # { status: count }

class StatsTrendResponse(BaseModel):
    days: int
    trend: dict[str, dict[str, int]]   # { date: { status: count } }
```

### 修改：TrialBalance 行数据模型

```typescript
// 前端 TrialBalance 行类型新增 account_category 枚举值
type AccountCategory =
  | 'asset'      // 资产
  | 'liability'  // 负债
  | 'equity'     // 权益
  | 'income'     // 收入（新增参与平衡计算）
  | 'cost'       // 成本（新增参与平衡计算）
  | 'expense'    // 费用（新增参与平衡计算）
```

---

## 正确性属性

*属性（Property）是在系统所有有效执行中都应成立的特征或行为——本质上是关于系统应该做什么的形式化陈述。属性是人类可读规范与机器可验证正确性保证之间的桥梁。*

### 属性 1：底稿保存事件传播

*对任意*底稿保存操作，`onSave` 成功完成后，`eventBus` 上应能收到 `workpaper:saved` 事件，且事件载荷中的 `projectId` 和 `wpId` 与保存操作的参数一致。

**验证：需求 1.1**

---

### 属性 2：附注刷新防抖

*对任意* N 次在 1 秒内连续触发的 `workpaper:saved` 事件，`refreshDisclosureFromWorkpapers` 函数的实际调用次数应恰好为 1。

**验证：需求 1.5**

---

### 属性 3：趋势图数据与 API 响应一致

*对任意*后端返回的趋势图数据，Dashboard 渲染的折线图数据点数值应与 API 响应中对应日期的状态计数完全一致。

**验证：需求 2.3**

---

### 属性 4：编辑命令触发 Dirty 标记

*对任意* Univer 命令 ID 属于 `DIRTY_COMMAND_PATTERNS` 集合的命令执行事件，`dirty.value` 应在 `onCommandExecuted` 回调执行后立即变为 `true`。

**验证：需求 3.1、3.2、3.6**

---

### 属性 5：保存后 Dirty 标记重置

*对任意*底稿保存成功操作，`dirty.value` 应在保存完成后变为 `false`。

**验证：需求 3.5**

---

### 属性 6：复核收件箱入口权限控制

*对任意*用户角色，当且仅当角色为 `reviewer`、`partner` 或 `admin` 时，导航菜单中应显示"复核收件箱"入口；其他角色不应显示该入口。

**验证：需求 4.1、4.4**

---

### 属性 7：复核收件箱 Badge 数量一致性

*对任意*已登录的 reviewer 用户，导航菜单中"复核收件箱"角标显示的数量应等于 `getGlobalReviewInbox` 接口返回的 `total` 值。

**验证：需求 4.3、4.5**

---

### 属性 8：UUID 到姓名映射完整性

*对任意*底稿列表中的 `assigned_to` 字段值，若该 UUID 存在于用户列表中，则显示文本应为对应用户的 `display_name`；若不存在，则显示文本应为"未知用户"；若为 `null`，则显示文本应为"未分配"。

**验证：需求 5.1、5.2、5.3**

---

### 属性 9：进度百分比计算正确性

*对任意*底稿列表数据，进度百分比应等于 `Math.floor(完成数 / 总数 * 100)`，其中完成数为 `status` 属于 `COMPLETED_STATUSES` 集合的底稿数量，且全量进度和筛选进度应分别基于各自的数据集独立计算。

**验证：需求 6.2、6.4**

---

### 属性 10：步骤状态单调递进

*对任意*项目启动流程，步骤状态转换应满足单调性：完成步骤 N 后，步骤 N 的状态变为 `finish`，步骤 N+1 的状态变为 `process`，且不可跳过或回退（除非当前步骤失败）。

**验证：需求 7.2、7.3**

---

### 属性 11：借贷平衡计算正确性

*对任意*试算表数据，`isBalanced` 的计算应始终纳入损益类科目净额，使得 `资产合计 ≈ 负债合计 + 权益合计 + 损益净额`（误差 < 1 元）。

**验证：需求 8.1、8.3、8.4**

---

### 属性 12：数据库迁移完整性

*对任意*全新 PostgreSQL 数据库，执行 `alembic upgrade head` 后，`information_schema.tables` 中 `table_schema='public'` 的表数量应不少于 144。

**验证：需求 9.2**

---

### 属性 13：Worker 异常隔离

*对任意* Worker 模块在单次执行周期中抛出的未捕获异常，该异常不应导致 FastAPI 主应用崩溃，且该 Worker 应在下一个调度周期继续执行（`stop_event` 未被设置时）。

**验证：需求 10.5**

---

### 属性 14：路由前缀规范一致性

*对任意*通过 `router_registry.py` 注册的 Phase 14 路由器（gate/trace/sod），其注册方式应为直接 `prefix="/api"`，不得使用 `hasattr` 运行时判断；所有业务 API 端点的完整路径应以 `/api/` 开头（WOPI 路由和 dashboard 路由除外）。

**验证：需求 11.1、11.2、11.4**

---

## 错误处理

### 附注同步失败（需求 1）

| 场景 | 处理方式 |
|------|---------|
| `refreshDisclosureFromWorkpapers` 网络超时 | `syncError.value = true`，显示失败提示和手动重试按钮 |
| 附注页面未打开时收到 `workpaper:saved` 事件 | 事件监听器未注册，自然忽略 |
| 防抖期间页面被销毁 | `onBeforeUnmount` 中 `eventBus.off` 清理，防止内存泄漏 |

### Dashboard 趋势图失败（需求 2）

| 场景 | 处理方式 |
|------|---------|
| API 请求失败 | `trendLoadError.value = true`，隐藏趋势图区域，显示错误提示 |
| 返回数据为空 | 显示空状态，不展示任何模拟数据 |

### Worker 异常（需求 10）

| 场景 | 处理方式 |
|------|---------|
| Worker 单次执行抛出异常 | `try/except` 捕获，记录 warning 日志，继续下一周期 |
| Worker 被 `CancelledError` | `break` 退出循环，优雅停止 |
| `stop_event` 设置后 Worker 仍在 sleep | `asyncio.wait_for` 或检查 `stop_event.is_set()` |

### 路由前缀迁移（需求 11）

| 场景 | 处理方式 |
|------|---------|
| 路由器内部已有 `/api` 前缀 | 迁移时去掉内部前缀，registry 统一添加 |
| 前端 API 调用路径 | 前端统一使用 `/api/xxx`，不受影响 |
| 迁移后 404 | 启动时打印所有路由列表，逐一验证 |

---

## 测试策略

### 双轨测试方法

本项目采用单元测试 + 属性测试双轨方法：
- **单元测试**：验证具体示例、边界情况和错误处理
- **属性测试**：验证跨所有输入的通用属性（使用 Hypothesis）

### 后端属性测试（Python + Hypothesis）

**属性测试库**：`hypothesis`（已在项目中使用，见 `.hypothesis/` 目录）

**配置**：每个属性测试最少运行 100 次（`@settings(max_examples=100)`）

**标注格式**：
```python
# Feature: production-readiness, Property 12: 数据库迁移完整性
# Feature: production-readiness, Property 13: Worker 异常隔离
# Feature: production-readiness, Property 14: 路由前缀规范一致性
```

**示例：属性 13 Worker 异常隔离测试**
```python
from hypothesis import given, settings, strategies as st

@given(error_message=st.text(min_size=1))
@settings(max_examples=100)
async def test_worker_exception_isolation(error_message: str):
    """Feature: production-readiness, Property 13: Worker 异常隔离"""
    stop_event = asyncio.Event()
    call_count = 0

    async def failing_operation():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError(error_message)

    # Worker 应在第一次失败后继续运行第二次
    await run_worker_once_with_recovery(failing_operation, stop_event)
    assert call_count >= 2  # 至少执行了两次（第一次失败，第二次重试）
```

**示例：属性 14 路由前缀规范测试**
```python
@given(st.just(None))  # 无需随机输入，检查静态配置
@settings(max_examples=1)
def test_router_prefix_convention(_):
    """Feature: production-readiness, Property 14: 路由前缀规范一致性"""
    from app.router_registry import register_all_routers
    from fastapi import FastAPI
    app = FastAPI()
    register_all_routers(app)
    for route in app.routes:
        if hasattr(route, 'path') and route.path.startswith('/api/'):
            # 所有业务路由应以 /api/ 开头
            assert not route.path.startswith('/api/api/'), \
                f"双重 /api 前缀: {route.path}"
```

### 前端属性测试（Vitest + fast-check）

**属性测试库**：`fast-check`（需安装：`npm install -D fast-check`）

**配置**：每个属性测试最少运行 100 次（`{ numRuns: 100 }`）

**标注格式**：
```typescript
// Feature: production-readiness, Property N: 属性描述
```

**示例：属性 9 进度百分比计算测试**
```typescript
import * as fc from 'fast-check'

test('Feature: production-readiness, Property 9: 进度百分比计算正确性', () => {
  fc.assert(fc.property(
    fc.array(fc.record({
      id: fc.uuid(),
      status: fc.constantFrom('not_started', 'in_progress', 'review_passed', 'archived'),
    }), { minLength: 1 }),
    (workpapers) => {
      const COMPLETED = new Set(['review_passed', 'archived'])
      const completed = workpapers.filter(w => COMPLETED.has(w.status)).length
      const expected = Math.floor((completed / workpapers.length) * 100)
      const actual = calcProgress(workpapers)
      return actual.percent === expected
    }
  ), { numRuns: 100 })
})
```

**示例：属性 11 借贷平衡计算测试**
```typescript
test('Feature: production-readiness, Property 11: 借贷平衡计算正确性', () => {
  fc.assert(fc.property(
    fc.array(fc.record({
      account_category: fc.constantFrom('asset', 'liability', 'equity', 'income', 'cost', 'expense'),
      audited_amount: fc.float({ min: -1e6, max: 1e6 }),
    })),
    (rows) => {
      const result = calcIsBalanced(rows)
      const asset = rows.filter(r => r.account_category === 'asset')
                        .reduce((s, r) => s + r.audited_amount, 0)
      const liabEquity = rows.filter(r => ['liability', 'equity'].includes(r.account_category))
                             .reduce((s, r) => s + r.audited_amount, 0)
      const incomeNet = rows.filter(r => ['income', 'cost', 'expense'].includes(r.account_category))
                            .reduce((s, r) => s + r.audited_amount, 0)
      const rhs = liabEquity + incomeNet
      const expectedBalanced = Math.abs(asset - rhs) < 1
      return result.isBalanced === expectedBalanced
    }
  ), { numRuns: 100 })
})
```

### 单元测试重点

| 需求 | 测试重点 | 测试类型 |
|------|---------|---------|
| 需求 1 | 附注刷新失败时显示错误提示和重试按钮 | 示例测试 |
| 需求 2 | API 失败时隐藏趋势图区域 | 示例测试 |
| 需求 3 | dirty=true 时路由离开弹出确认框 | 示例测试 |
| 需求 4 | 点击复核收件箱入口跳转到 /review-inbox | 示例测试 |
| 需求 7 | 步骤失败时显示错误标记和重试按钮 | 示例测试 |
| 需求 9 | Alembic 迁移失败时回滚并输出日志 | 示例测试 |
| 需求 10 | 应用启动后所有 worker task 处于运行状态 | 示例测试 |
| 需求 12 | 压测报告包含 TPS、P95/P99、错误率字段 | 示例测试 |

---

## 涉及文件变更清单

### P0 — 数据正确性

#### 需求 1：底稿→附注同步

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/utils/eventBus.ts` | 修改 | 新增 `WorkpaperSavedPayload` 接口和 `workpaper:saved` 事件类型 |
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 修改 | `onSave` 成功后 `emit('workpaper:saved', ...)` |
| `audit-platform/frontend/src/views/DisclosureEditor.vue` | 修改 | `onMounted` 注册防抖监听器，`onBeforeUnmount` 清理，新增 `syncError` 状态和失败提示 UI |

#### 需求 2：Dashboard 趋势图

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/routers/dashboard.py` | 修改 | 新增 `GET /stats/trend` 端点 |
| `backend/app/services/dashboard_service.py` | 修改 | 新增 `get_stats_trend()` 方法 |
| `audit-platform/frontend/src/views/Dashboard.vue` | 修改 | 删除硬编码 `sparkData`，改为 API 调用，新增错误状态处理 |

#### 需求 3：Dirty 标记完整覆盖

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 修改 | 扩展 `DIRTY_COMMAND_PATTERNS` 数组，新增未保存提示 UI，新增 `onBeforeRouteLeave` 守卫 |

---

### P1 — 核心流程

#### 需求 4：复核收件箱导航

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/layouts/DefaultLayout.vue` | 修改 | 新增复核收件箱导航入口（含 badge），`v-permission` 控制可见性，定时刷新 badge 数量 |

#### 需求 5：UUID→姓名映射

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperList.vue` | 修改 | 新增 `userNameMap`，`loadUserOptions` 时建立映射，所有 `assigned_to` 展示点改用 `resolveUserName()` |

---

### P2 — 体验优化

#### 需求 6：进度百分比

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperList.vue` | 修改 | 新增 `totalProgress`、`filteredProgress` 计算属性，新增进度指示器 UI |

#### 需求 7：步骤引导

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/TrialBalance.vue` | 修改 | 在空数据区域添加 `el-steps` 步骤条，步骤状态通过 `localStorage` 持久化（key: `setup_step_{projectId}`），提供各步骤跳转按钮 |

#### 需求 8：借贷平衡修正

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/TrialBalance.vue` | 修改 | 新增 `incomeNetAmount` 计算属性，修改 `liabEquityTotal` 纳入损益净额（期中模式），更新 tooltip 文案 |

---

### P3 — 生产部署

#### 需求 9：PostgreSQL 迁移

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/core/database.py` | 修改 | 针对 PostgreSQL 配置连接池参数（`pool_size=20, max_overflow=80`） |
| `backend/app/migrations/` | 修改 | 验证并补全 Alembic 迁移脚本，确保覆盖全部 144 张表 |
| `.env.example` | 修改 | 添加 PostgreSQL `DATABASE_URL` 示例和说明注释 |
| `backend/.env` | 修改 | 生产环境切换 `DATABASE_URL` 为 PostgreSQL 连接串 |

#### 需求 10：Worker 拆分

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/workers/sla_worker.py` | 新增 | SLA 超时检查 Worker，`async def run(stop_event)` |
| `backend/app/workers/import_recover_worker.py` | 新增 | 导入任务恢复 Worker，`async def run(stop_event)` |
| `backend/app/workers/outbox_replay_worker.py` | 新增 | Outbox 重放 Worker，`async def run(stop_event)` |
| `backend/app/main.py` | 修改 | 提取 `_run_migrations()`、`_register_phase_handlers()`、`_start_workers()` 辅助函数，lifespan 精简至 ~25 行 |

#### 需求 11：路由前缀统一

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/router_registry.py` | 修改 | 删除 Phase 14 `hasattr` 补丁，改为直接 `app.include_router(r, prefix="/api", ...)` 注册 gate/trace/sod，添加规范注释（含 dashboard 例外说明） |

#### 需求 12：压测验证

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `load_test.py` | 修改 | 确认覆盖 5 个核心接口，输出包含 TPS/P95/P99/错误率的完整报告 |

---

## 实施顺序建议

按优先级和依赖关系，建议以下实施顺序：

```
Sprint 1（P0，约 2 天）：
  需求 3（Dirty 标记）→ 需求 1（附注同步）→ 需求 2（Dashboard 趋势图）

Sprint 2（P1+P2，约 2 天）：
  需求 4（复核收件箱）→ 需求 5（UUID 映射）→ 需求 6（进度百分比）→ 需求 8（借贷平衡）

Sprint 3（P2+P3 前置，约 1 天）：
  需求 7（步骤引导）→ 需求 11（路由前缀）→ 需求 10（Worker 拆分）

Sprint 4（P3 核心，约 2 天）：
  需求 9（PostgreSQL 迁移）→ 需求 12（压测验证）
```

---

## 需求 13-16：底稿四式联动与 Univer 功能完整性

### 需求 13：底稿编辑器公式计算引擎集成

#### 问题根因

当前 `WorkpaperEditor.vue` 只使用了 `UniverSheetsCorePreset`（最基础预设），缺少公式计算引擎。`=SUM(A1:A10)` 等公式只显示字符串，不计算结果，对审计底稿是致命缺陷——审定表合计行全靠公式。

#### 设计方案

**安装依赖：**
```bash
npm install @univerjs/preset-sheets-formula
```

**修改 `WorkpaperEditor.vue` 的 `createUniver` 调用：**
```typescript
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import { UniverSheetsFormulaPreset } from '@univerjs/preset-sheets-formula'
// @ts-ignore
import UniverPresetSheetsFormulaZhCN from '@univerjs/preset-sheets-formula/lib/locales/zh-CN'
import '@univerjs/preset-sheets-formula/lib/index.css'

const { univerAPI: api, univer } = createUniver({
  locale: LocaleType.ZH_CN,
  locales: {
    [LocaleType.ZH_CN]: mergeLocales(
      UniverPresetSheetsCoreZhCN,
      UniverPresetSheetsFormulaZhCN,  // 新增
    ),
  },
  presets: [
    UniverSheetsCorePreset({ container: univerContainer.value }),
    UniverSheetsFormulaPreset(),  // 新增：公式计算引擎
  ],
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/package.json` | 修改 | 新增 `@univerjs/preset-sheets-formula` 依赖 |
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 修改 | 添加 `UniverSheetsFormulaPreset` 和对应 locale |

---

### 需求 14：底稿编辑器错误信息修正

#### 问题根因

`onSyncStructure` 先调用 `onSave()`，若保存失败，`onSave()` 内部已显示"保存失败"提示，但 `onSyncStructure` 的 catch 块又显示"同步失败"，用户看到两条错误，第二条掩盖真实原因。

#### 设计方案

**`onSave` 改为返回 boolean：**
```typescript
async function onSave(): Promise<boolean> {
  if (!univerAPI || !wpDetail.value) return false
  saving.value = true
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')
    const snapshot = workbook.getSnapshot()
    const data = await httpApi.post(
      `/api/projects/${projectId.value}/working-papers/${wpId.value}/univer-save`,
      { snapshot },
    )
    dirty.value = false
    ElMessage.success(data?.message || '保存成功')
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    return true
  } catch (err: any) {
    ElMessage.error('保存失败: ' + (err?.response?.data?.detail || err?.message || ''))
    return false
  } finally {
    saving.value = false
  }
}
```

**`onSyncStructure` 判断返回值：**
```typescript
async function onSyncStructure() {
  syncLoading.value = true
  try {
    if (dirty.value) {
      const saveOk = await onSave()
      if (!saveOk) return  // 保存失败时直接返回，不显示"同步失败"
    }
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    ElMessage.success('公式坐标已同步')
  } catch (err: any) {
    ElMessage.error('同步失败: ' + (err?.message || ''))
  } finally {
    syncLoading.value = false
  }
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 修改 | `onSave` 改为返回 `Promise<boolean>`，`onSyncStructure` 判断返回值后决定是否继续 |

---

### 需求 15：底稿 xlsx 模板公式值预加载

#### 问题根因

`xlsx_to_univer.py` 中 `_convert_cell` 对公式单元格设置 `result["v"] = ""`（空字符串），导致 Univer 加载时公式单元格显示空白，需手动触发重算才能看到数值。

`openpyxl` 支持 `data_only=True` 模式读取 Excel 上次保存时的计算值，可用于预填 `v` 字段。

#### 设计方案

**`xlsx_to_univer.py` 双次加载：**
```python
def xlsx_to_univer_data(file_path: str, max_rows: int = 5000) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return _empty_workbook("Sheet1")

    try:
        wb_formula = load_workbook(str(path), data_only=False)  # 获取公式字符串
        wb_value = load_workbook(str(path), data_only=True)     # 获取上次计算值
    except Exception as e:
        logger.warning("无法解析 xlsx: %s", e)
        return _empty_workbook("Sheet1")

    # 遍历时同时传入两个 workbook 对应的 cell
    # ...（其余逻辑不变，_convert_cell 接收额外的 value_cell 参数）
```

**`_convert_cell` 修改：**
```python
def _convert_cell(cell: Cell, value_cell: Cell | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}

    val = cell.value
    if val is not None:
        if isinstance(val, (int, float)):
            result["v"] = val
            result["t"] = 2
        elif isinstance(val, bool):
            result["v"] = 1 if val else 0
            result["t"] = 4
        else:
            result["v"] = str(val)
            result["t"] = 1

    # 公式处理：保留公式字符串，同时用 data_only 版本的计算值作为初始显示值
    if isinstance(cell.value, str) and cell.value.startswith("="):
        result["f"] = cell.value
        # 使用上次计算值（而非空字符串）
        if value_cell is not None and value_cell.value is not None:
            v = value_cell.value
            if isinstance(v, (int, float)):
                result["v"] = v
                result["t"] = 2
            elif isinstance(v, bool):
                result["v"] = 1 if v else 0
                result["t"] = 4
            else:
                result["v"] = str(v)
                result["t"] = 1
        else:
            result["v"] = ""  # 无计算值时保持空字符串，由 Univer 公式引擎重算

    style = _convert_style(cell)
    if style:
        result["s"] = style

    return result
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/xlsx_to_univer.py` | 修改 | `xlsx_to_univer_data` 双次加载 xlsx（公式版 + 计算值版），`_convert_cell` 新增 `value_cell` 参数，公式单元格 `v` 字段使用计算值 |

---

### 需求 16：底稿导出 PDF

#### 设计方案

**后端新增端点（`working_paper.py`）：**

使用 LibreOffice headless 将 xlsx 转换为 PDF（服务器需安装 LibreOffice）。若 LibreOffice 不可用，降级为 `reportlab` 纯文本 PDF。

```python
@router.get("/working-papers/{wp_id}/export-pdf")
async def export_workpaper_pdf(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """将底稿 xlsx 导出为 PDF（使用 LibreOffice headless 转换）"""
    import subprocess
    import tempfile
    from pathlib import Path

    result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")
    if not wp.file_path:
        raise HTTPException(status_code=404, detail="底稿文件不存在")

    fp = Path(wp.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="底稿文件不存在")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf",
                 "--outdir", tmpdir, str(fp)],
                timeout=60,
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise HTTPException(status_code=500, detail=f"PDF 转换失败: {e}")

        pdf_path = Path(tmpdir) / (fp.stem + ".pdf")
        if not pdf_path.exists():
            raise HTTPException(status_code=500, detail="PDF 文件生成失败")

        pdf_bytes = pdf_path.read_bytes()

    from urllib.parse import quote
    pdf_name = fp.stem + ".pdf"
    utf8_name = quote(pdf_name, safe="")
    ascii_name = pdf_name.encode("ascii", "ignore").decode() or "workpaper.pdf"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
```

**前端 `WorkpaperEditor.vue` 工具栏新增按钮：**
```html
<el-button size="small" @click="onExportPdf" :loading="exportingPdf">📄 导出 PDF</el-button>
```

```typescript
const exportingPdf = ref(false)

async function onExportPdf() {
  exportingPdf.value = true
  try {
    const url = `/api/projects/${projectId.value}/working-papers/${wpId.value}/export-pdf`
    const response = await httpApi.get(url, { responseType: 'blob' })
    const blob = new Blob([response], { type: 'application/pdf' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${wpDetail.value?.wp_code || 'workpaper'}.pdf`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch {
    ElMessage.error('导出 PDF 失败')
  } finally {
    exportingPdf.value = false
  }
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/routers/working_paper.py` | 修改 | 新增 `GET /working-papers/{wp_id}/export-pdf` 端点，使用 LibreOffice headless 转换 |
| `audit-platform/frontend/src/views/WorkpaperEditor.vue` | 修改 | 工具栏新增"导出 PDF"按钮，`onExportPdf` 函数触发下载 |

---

### 错误处理补充（需求 13-16）

| 需求 | 场景 | 处理方式 |
|------|------|---------|
| 需求 13 | `@univerjs/preset-sheets-formula` 包不存在 | 安装依赖后重新构建，构建失败时检查版本兼容性 |
| 需求 14 | `onSave` 返回 false 后 `onSyncStructure` 直接 return | 不显示额外错误，用户已看到"保存失败"提示 |
| 需求 15 | xlsx 无计算值（从未在 Excel 中打开过） | `value_cell.value` 为 None，`v` 字段保持空字符串，由 Univer 公式引擎重算 |
| 需求 16 | LibreOffice 未安装 | 返回 HTTP 500，提示"PDF 转换失败: LibreOffice 未安装" |
| 需求 16 | xlsx 文件损坏 | LibreOffice 转换失败，返回 HTTP 500 |
| 需求 16 | 转换超时（>60s） | `subprocess.TimeoutExpired`，返回 HTTP 500 |

---

### 正确性属性补充（需求 13-16）

#### 属性 15：公式计算引擎加载

*对任意*含公式的底稿，Univer 初始化完成后，公式单元格的显示值应为计算结果（数值或字符串），不得为公式字符串本身（如 `=SUM(A1:A10)`）。

**验证：需求 13.2**

---

#### 属性 16：保存函数返回值语义

*对任意*底稿保存操作，`onSave()` 返回 `true` 当且仅当后端 API 返回成功响应；返回 `false` 当且仅当发生网络错误或后端返回错误状态码。

**验证：需求 14.2**

---

#### 属性 17：公式值预加载完整性

*对任意*含公式且已在 Excel 中计算过的 xlsx 文件，`xlsx_to_univer_data` 转换后，公式单元格的 `v` 字段应等于 `data_only=True` 模式下 openpyxl 读取到的计算值（非 None 时）。

**验证：需求 15.1**

---

#### 属性 18：PDF 导出内容完整性

*对任意*存在有效 xlsx 文件的底稿，`export-pdf` 端点返回的 PDF 文件大小应大于 0 字节，且 Content-Type 应为 `application/pdf`。

**验证：需求 16.2、16.3**


---

## 需求 17-25：生产就绪补充改进

### 需求 17：报表权益变动表和资产减值准备表数据填充

#### 问题根因

`ReportView.vue` 中权益变动表（`equity_statement`）和资产减值准备表（`impairment_provision`）的 `<tbody>` 全部硬编码为 `-`，不是"暂无数据"，是真正的空壳。上市公司审计必须出具这两张表。

#### 设计方案

后端 `reports.py` 路由已有 `GET /api/projects/{id}/reports/{report_type}` 接口，需确认 `equity_statement` 和 `impairment_provision` 两种 `report_type` 是否有对应的数据生成逻辑。若已有，前端只需改为数据驱动渲染；若无，需在后端补充对应的数据聚合逻辑。

**前端 `ReportView.vue` 修改：**

权益变动表 `<tbody>` 改为从 `rows` 数据中读取对应列的值：
```html
<!-- 原来（硬编码） -->
<td>-</td><td>-</td><td>-</td>

<!-- 修改后（数据驱动） -->
<td>{{ fmt(row.share_capital) }}</td>
<td>{{ fmt(row.capital_reserve) }}</td>
<td>{{ fmt(row.retained_earnings) }}</td>
```

资产减值准备表同理，从 `impairmentRows` 数据中读取各列金额，无数据时显示 `0` 而非 `-`。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/ReportView.vue` | 修改 | 权益变动表和资产减值准备表 tbody 改为数据驱动，无数据时显示 0 |

---

### 需求 18：ReviewInbox 查看按钮跳转修正

#### 问题根因

`ReviewInbox.vue` 的 `goToWorkpaper` 函数跳转到底稿列表页（`WorkpaperList`）而非底稿编辑器（`WorkpaperEditor`），复核人需要再次在列表里找到底稿才能查看。

#### 设计方案

```typescript
// 修改 ReviewInbox.vue 中的 goToWorkpaper 函数
function goToWorkpaper(row: ReviewInboxItem) {
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: row.project_id, wpId: row.id }
  })
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/ReviewInbox.vue` | 修改 | `goToWorkpaper` 函数改为跳转到 `WorkpaperEditor`，路径为 `/projects/{project_id}/workpapers/{wp_id}/edit` |

---

### 需求 19：AuditCheckDashboard N+1 请求优化

#### 问题根因

`AuditCheckDashboard.vue` 对每份底稿串行发一个 `POST /fine-extract` 请求，80+ 底稿会导致页面卡死 30-60 秒。

#### 设计方案

**后端新增批量汇总端点（`wp_fine_rules.py`）：**
```python
@router.get("/projects/{project_id}/fine-checks/summary")
async def get_fine_checks_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量返回项目所有底稿的精细化检查结果汇总"""
    svc = WpFineRulesService(db)
    return await svc.get_all_fine_checks(project_id)
```

**前端 `AuditCheckDashboard.vue` 改为调用批量接口：**
```typescript
// 删除原有 for (const wp of wpList) 循环
// 改为单次批量请求
async function loadAllFineChecks() {
  loading.value = true
  try {
    const result = await httpApi.get(
      `/api/projects/${projectId.value}/fine-checks/summary`
    )
    fineCheckResults.value = result.items || []
  } finally {
    loading.value = false
  }
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/routers/wp_fine_rules.py` | 修改 | 新增 `GET /projects/{project_id}/fine-checks/summary` 批量汇总端点 |
| `audit-platform/frontend/src/views/AuditCheckDashboard.vue` | 修改 | 删除 `for (const wp of wpList)` 串行循环，改为调用批量接口 |

---

### 需求 20：错报超限联动 QC 门禁

#### 问题根因

`Misstatements.vue` 的超限预警只是一个 `el-alert`，不联动 QC 门禁，审计员可能在错报超限的情况下仍然提交复核并出具无保留意见。

#### 设计方案

**后端 `gate_rules_phase14.py` 新增门禁规则：**
```python
async def check_misstatement_exceeds_materiality(
    project_id: UUID, db: AsyncSession
) -> GateCheckResult:
    """检查未更正错报是否超过整体重要性水平"""
    # 查询 misstatements 表累计金额
    total_q = sa.select(sa.func.sum(Misstatement.amount)).where(
        Misstatement.project_id == project_id,
        Misstatement.is_corrected == sa.false(),
    )
    total = (await db.execute(total_q)).scalar() or 0

    # 查询 materiality 表整体重要性
    mat_q = sa.select(Materiality.overall_materiality).where(
        Materiality.project_id == project_id
    )
    overall = (await db.execute(mat_q)).scalar() or 0

    if overall > 0 and abs(total) > overall:
        return GateCheckResult(
            passed=False,
            reason=f"未更正错报（{total:,.2f}）超过整体重要性水平（{overall:,.2f}）",
        )
    return GateCheckResult(passed=True)
```

**前端 `AuditReportEditor.vue` 新增警告横幅：**
```typescript
const misstatementWarning = ref(false)

onMounted(async () => {
  try {
    const res = await httpApi.get(
      `/api/projects/${projectId.value}/misstatements/summary`
    )
    misstatementWarning.value = res.exceeds_materiality === true
  } catch { /* 静默失败 */ }
})
```

```html
<el-alert
  v-if="misstatementWarning"
  type="error"
  title="未更正错报超过重要性水平"
  description="当前项目存在超过整体重要性水平的未更正错报，请在出具审计报告前处理。"
  show-icon
  :closable="false"
  style="margin-bottom: 16px"
/>
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/gate_rules_phase14.py` | 修改 | 新增 `check_misstatement_exceeds_materiality` 门禁规则，集成到门禁检查链 |
| `audit-platform/frontend/src/views/AuditReportEditor.vue` | 修改 | `onMounted` 时调用 `misstatements/summary`，`exceeds_materiality` 为 true 时显示警告横幅 |

---

### 需求 21：重要性变更后试算表标记自动更新

#### 问题根因

重要性水平变更后，试算表里的 `exceeds_materiality` 标记不会自动更新，需要手动点"全量重算"才能刷新。

#### 设计方案

**后端 `materiality.py` 路由保存后发布事件：**
```python
# 保存重要性水平后，触发试算表 exceeds_materiality 批量更新
@router.post("/projects/{project_id}/materiality")
async def save_materiality(project_id: UUID, data: MaterialityIn, db: AsyncSession = ...):
    # ... 保存逻辑 ...
    # 触发试算表标记更新
    await trial_balance_service.update_exceeds_materiality_flags(project_id, db)
    await db.commit()
    return {"message": "重要性水平已保存"}
```

**前端 `Materiality.vue` 保存成功后通知试算表刷新：**
```typescript
async function onSave() {
  await httpApi.post(`/api/projects/${projectId.value}/materiality`, form.value)
  ElMessage.success('重要性水平已保存')
  // 通知试算表刷新
  eventBus.emit('materiality:changed', { projectId: projectId.value })
}
```

**前端 `TrialBalance.vue` 监听事件并刷新：**
```typescript
onMounted(() => {
  eventBus.on('materiality:changed', onMaterialityChanged)
})
onBeforeUnmount(() => {
  eventBus.off('materiality:changed', onMaterialityChanged)
})

async function onMaterialityChanged(payload: { projectId: string }) {
  if (payload.projectId !== projectId.value) return
  await loadRows()  // 重新加载试算表数据
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/routers/materiality.py` | 修改 | 保存重要性水平后调用 `trial_balance_service.update_exceeds_materiality_flags` |
| `audit-platform/frontend/src/views/Materiality.vue` | 修改 | 保存成功后 `eventBus.emit('materiality:changed', { projectId })` |
| `audit-platform/frontend/src/views/TrialBalance.vue` | 修改 | 监听 `materiality:changed` 事件，触发时重新加载试算表数据 |

---

### 需求 22：账套导入完成通知

#### 问题根因

`LedgerPenetration.vue` 导入完成后无通知机制，用户不知道后台导入是否完成，需要反复刷新页面确认。

#### 设计方案

前端在导入任务提交后，启动轮询（每 3 秒查询一次导入任务状态），直到状态变为 `completed` 或 `failed`。

```typescript
let pollTimer: ReturnType<typeof setInterval> | null = null

async function startImportPolling(jobId: string) {
  pollTimer = setInterval(async () => {
    try {
      const res = await httpApi.get(
        `/api/projects/${projectId.value}/ledger/import-status/${jobId}`
      )
      if (res.status === 'completed') {
        clearInterval(pollTimer!)
        pollTimer = null
        ElNotification.success({ title: '导入完成', message: '账套数据导入完成，正在刷新...' })
        await loadLedgerData()  // 自动刷新余额表
      } else if (res.status === 'failed') {
        clearInterval(pollTimer!)
        pollTimer = null
        ElNotification.error({ title: '导入失败', message: res.error || '账套数据导入失败' })
      }
    } catch { /* 静默失败，继续轮询 */ }
  }, 3000)
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/LedgerPenetration.vue` | 修改 | 导入任务提交后启动 3 秒轮询，状态变为 `completed` 时显示 `ElNotification` 并自动刷新数据列表 |

---

### 需求 23：底稿工作台 AI 分析本地缓存

#### 问题根因

`WorkpaperWorkbench.vue` 每次切换底稿节点都重新请求 AI 分析，无本地缓存，vLLM 响应慢时用户体验差。

#### 设计方案

```typescript
// WorkpaperWorkbench.vue 新增缓存 Map
const aiAnalysisCache = ref<Map<string, any>>(new Map())

async function loadAiAnalysis(m: WpAccountMapping) {
  const cacheKey = m.wp_code
  if (aiAnalysisCache.value.has(cacheKey)) {
    aiAnalysis.value = aiAnalysisCache.value.get(cacheKey)
    return
  }
  aiLoading.value = true
  try {
    // ... 原有请求逻辑 ...
    aiAnalysisCache.value.set(cacheKey, aiAnalysis.value)
  } finally {
    aiLoading.value = false
  }
}
```

缓存在当前页面会话内有效（`ref` 生命周期与组件一致），页面刷新后自动清空。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperWorkbench.vue` | 修改 | 新增 `aiAnalysisCache` Map，`loadAiAnalysis` 命中缓存时直接返回，跳过网络请求 |

---

### 需求 24：报表对比视图新增上年审定数列

#### 问题根因

`ReportView.vue` 的对比视图（`reportMode === 'compare'`）只有"未审金额/调整影响/已审金额"三列，缺少"上年审定数"列，无法做分析性复核。

#### 设计方案

后端 `reports.py` 的对比模式接口已返回 `prior_period_amount` 字段，前端只需在对比视图表格中新增一列：

```html
<!-- 对比视图表头新增 -->
<th>上年审定数</th>

<!-- 对比视图数据行新增 -->
<td>{{ fmt(row.prior_period_amount) }}</td>
```

`compareRows` 数据中已有 `prior_period_amount` 字段，直接使用，无需后端改动。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/ReportView.vue` | 修改 | 对比视图表格新增"上年审定数"列，使用 `row.prior_period_amount` 字段 |

---

### 需求 25：序时账异常凭证视觉标记

#### 问题根因

`LedgerPenetration.vue` 的序时账表格没有对异常凭证（超重要性金额、期末凭证、红字冲销）做视觉标记，审计员需要逐行扫描。

#### 设计方案

扩展 `LedgerPenetration.vue` 的行样式函数，新增三种异常标记：

```typescript
// 从 projectStore 获取重要性水平和审计期末
const performanceMateriality = computed(
  () => projectStore.currentProject?.performance_materiality ?? 0
)
const auditPeriodEnd = computed(
  () => projectStore.currentProject?.audit_period_end ?? ''
)

function ledgerRowClass(row: LedgerEntry): string {
  const classes: string[] = []

  // 1. 金额超重要性：橙色背景
  const pm = performanceMateriality.value
  if (pm > 0 && (Math.abs(row.debit_amount ?? 0) > pm || Math.abs(row.credit_amount ?? 0) > pm)) {
    classes.push('gt-ledger-row--over-materiality')
  }

  // 2. 期末最后 5 个工作日：截止标记（通过 CSS class 触发 ::after 伪元素）
  if (auditPeriodEnd.value && row.voucher_date) {
    const end = new Date(auditPeriodEnd.value)
    const vDate = new Date(row.voucher_date)
    const diffDays = Math.floor((end.getTime() - vDate.getTime()) / 86400000)
    if (diffDays >= 0 && diffDays <= 6) {  // 约 5 个工作日（含周末缓冲）
      classes.push('gt-ledger-row--period-end')
    }
  }

  // 3. 红字冲销：红色文字
  if ((row.debit_amount ?? 0) < 0 || (row.credit_amount ?? 0) < 0) {
    classes.push('gt-ledger-row--red-reversal')
  }

  return classes.join(' ')
}
```

**CSS 样式（在组件 `<style scoped>` 中添加）：**
```css
.gt-ledger-row--over-materiality td {
  background-color: #fff7e6;
}
.gt-ledger-row--over-materiality td:first-child::before {
  content: '⚠';
  margin-right: 4px;
  color: #fa8c16;
}
.gt-ledger-row--period-end td:first-child::after {
  content: '截止';
  margin-left: 4px;
  font-size: 10px;
  color: #1890ff;
  border: 1px solid #1890ff;
  border-radius: 2px;
  padding: 0 2px;
}
.gt-ledger-row--red-reversal td {
  color: #f5222d;
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/LedgerPenetration.vue` | 修改 | 扩展 `ledgerRowClass` 函数，新增超重要性/期末/红字三种异常标记样式 |

---

### 正确性属性补充（需求 17-25）

#### 属性 19：报表数据驱动渲染

*对任意*后端返回的权益变动表或资产减值准备表数据，`ReportView` 渲染的单元格内容应与 API 响应中对应字段的值一致，不得出现硬编码的"-"字符。

**验证：需求 17.1、17.2、17.3**

---

#### 属性 20：ReviewInbox 跳转路径正确性

*对任意*复核收件箱条目，点击"查看"后路由跳转的目标路径应包含 `workpapers/{wp_id}/edit`，不得跳转到底稿列表页。

**验证：需求 18.1、18.2**

---

#### 属性 21：批量接口请求次数

*对任意*包含 N 份底稿的项目（N ≥ 1），`AuditCheckDashboard` 加载时发出的 HTTP 请求次数应恰好为 1（批量接口），不得为 N 次。

**验证：需求 19.2**

---

#### 属性 22：错报超限门禁阻断

*对任意*未更正错报累计金额超过整体重要性水平的项目，门禁检查结果的 `passed` 字段应为 `false`，且 `reason` 字段应包含"未更正错报超过重要性水平"。

**验证：需求 20.1**

---

#### 属性 23：重要性变更后标记一致性

*对任意*重要性水平变更操作，变更完成后试算表中每条科目的 `exceeds_materiality` 字段应与新重要性水平下的实际计算结果一致。

**验证：需求 21.1、21.2**

---

#### 属性 24：AI 分析缓存命中幂等性

*对任意*已缓存的底稿 `wp_code`，多次调用 `loadAiAnalysis` 返回的结果应完全相同，且不触发额外的网络请求。

**验证：需求 23.1**

---

### 错误处理补充（需求 17-25）

| 需求 | 场景 | 处理方式 |
|------|------|---------|
| 需求 17 | 后端无 `equity_statement` 数据 | 显示 0，不显示 `-` |
| 需求 18 | `WorkpaperEditor` 路由名称不匹配 | 检查 router 中实际路由名称，确保 `name: 'WorkpaperEditor'` 存在 |
| 需求 19 | 批量接口超时 | 显示加载失败提示，提供重试按钮 |
| 需求 20 | `misstatements/summary` 接口不存在 | 静默失败，不显示警告横幅（不阻断正常流程） |
| 需求 21 | `update_exceeds_materiality_flags` 执行失败 | 记录错误日志，不阻断重要性保存操作 |
| 需求 22 | 轮询超时（超过 10 分钟） | 停止轮询，显示"导入状态未知，请手动刷新"提示 |
| 需求 22 | 页面销毁时轮询仍在运行 | `onBeforeUnmount` 中 `clearInterval` 清理 |
| 需求 23 | AI 分析请求失败 | 不写入缓存，下次切换时重新请求 |
| 需求 25 | `projectStore.currentProject` 无重要性水平字段 | `performanceMateriality` 默认为 0，跳过超重要性标记 |


---

## 需求 26-32：P1/P2 补充改进

### 需求 26：QC 项目汇总 N+1 查询优化

#### 问题根因

`qc_engine.py` 的 `get_project_summary` 方法在循环中对每份底稿单独查询一次 `wp_qc_results`，80+ 底稿会产生 80+ 次数据库查询，`QCDashboard.vue` 加载时明显卡顿。

#### 设计方案

用一次带子查询的 SQL 替换循环，先取每份底稿的最新 QC 时间戳，再 JOIN 回原表取完整记录：

```python
# backend/app/services/qc_engine.py — get_project_summary 方法
latest_qc_subq = (
    sa.select(
        WpQcResult.working_paper_id,
        sa.func.max(WpQcResult.check_timestamp).label("latest_ts"),
    )
    .group_by(WpQcResult.working_paper_id)
    .subquery()
)
q = (
    sa.select(WpQcResult)
    .join(latest_qc_subq, sa.and_(
        WpQcResult.working_paper_id == latest_qc_subq.c.working_paper_id,
        WpQcResult.check_timestamp == latest_qc_subq.c.latest_ts,
    ))
    .where(WpQcResult.working_paper_id.in_(wp_ids))
)
results = (await db.execute(q)).scalars().all()
# 构建 {wp_id: WpQcResult} 映射，替换原有循环查询
qc_map = {str(r.working_paper_id): r for r in results}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/qc_engine.py` | 修改 | `get_project_summary` 改为单次批量查询，用子查询取每份底稿最新 QC 结果 |

---

### 需求 27：审计报告定稿后端状态保护

#### 问题根因

`AuditReportEditor.vue` 用 `:disabled` 禁用了前端输入框，但后端 `updateAuditReportParagraph` 接口没有校验 `status === 'final'`，定稿后的报告仍可通过 API 直接修改段落内容。

#### 设计方案

在 `audit_report.py` 路由的 `update_paragraph` 和 `update_status` 端点中添加状态校验：

```python
# backend/app/routers/audit_report.py — update_paragraph 端点
report = await get_report_or_404(project_id, db)
if report.status == 'final':
    raise HTTPException(
        status_code=403,
        detail="报告已定稿，不允许修改段落内容"
    )

# update_status 端点：禁止从 final 回退到 review
if report.status == 'final' and data.status == 'review':
    raise HTTPException(
        status_code=403,
        detail="报告已定稿，不允许将状态回退至复核中"
    )
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/routers/audit_report.py` | 修改 | `update_paragraph` 和 `update_status` 端点添加 `final` 状态保护，返回 HTTP 403 |

---

### 需求 28：QC-16 数据一致性规则字段修正

#### 问题根因

`DataReferenceConsistencyRule`（QC-16）使用了不存在的字段 `audited_debit` 和 `audited_credit`，而 `TrialBalance` 模型实际字段是 `audited_amount`（净额）。该规则永远不会触发，是死代码。

#### 设计方案

修正字段名，并修正查询逻辑——通过 `wp_mapping` 找到底稿对应的标准科目，再从 `TrialBalance` 取该科目的 `audited_amount`：

```python
# backend/app/services/qc_engine.py — DataReferenceConsistencyRule.check
# 1. 通过 wp_mapping 找到底稿对应的标准科目 code
account_code = context.working_paper.account_code  # 或从 mapping 取

# 2. 查询 TrialBalance 对应科目的 audited_amount
tb_q = sa.select(TrialBalance).where(
    TrialBalance.project_id == context.working_paper.project_id,
    TrialBalance.account_code == account_code,
)
tb = (await context.db.execute(tb_q)).scalar_one_or_none()
if tb is None:
    return []  # 无对应科目，跳过

# 3. 修正字段名：使用 audited_amount 而非 audited_debit/credit
tb_amt = float(tb.audited_amount or 0)
wp_amount = float((context.working_paper.parsed_data or {}).get("audited_amount") or 0)
diff = abs(wp_amount - tb_amt)
if diff > 0.01:
    return [QCFindingItem(
        rule_id="QC-16",
        level="blocking",
        message=f"底稿审定数（{wp_amount:,.2f}）与试算表（{tb_amt:,.2f}）差异 {diff:,.2f} 元",
    )]
return []
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/qc_engine.py` | 修改 | `DataReferenceConsistencyRule.check` 修正字段名（`audited_amount`）和查询逻辑（按科目 code 查询） |

---

### 需求 29：底稿汇总年度从项目上下文获取

#### 问题根因

`WorkpaperSummary.vue` 的年度硬编码为 `new Date().getFullYear()`，审计员在 2026 年做 2025 年度审计时，汇总会查不到数据。

#### 设计方案

从 `projectStore.year` 获取审计年度，`projectStore.year` 不存在时才降级为当前年份：

```typescript
// audit-platform/frontend/src/views/WorkpaperSummary.vue
import { useProjectStore } from '@/stores/project'
const projectStore = useProjectStore()

// 替换硬编码年度
const year = computed(() => projectStore.year || new Date().getFullYear())

// doGenerate 中使用 year.value
const result = await generateWorkpaperSummary(projectId, {
  year: year.value,
  // ...其他参数不变
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkpaperSummary.vue` | 修改 | 年度改为从 `projectStore.year` 获取，删除 `new Date().getFullYear()` 硬编码 |

---

### 需求 30：审计报告导出 Word 入口

#### 问题根因

`AuditReportEditor.vue` 工具栏没有导出功能，但后端 `word_export.py` 已有 Word 导出路由，前端未集成入口。

#### 设计方案

在 `AuditReportEditor.vue` 工具栏新增"导出 Word"按钮，调用已有的 `word_export.py` 接口：

```html
<!-- AuditReportEditor.vue 工具栏 -->
<el-button size="small" @click="onExportWord" :loading="exportingWord" round>
  导出 Word
</el-button>
```

```typescript
const exportingWord = ref(false)

async function onExportWord() {
  if (!report.value) return
  exportingWord.value = true
  try {
    const url = `/api/projects/${projectId.value}/audit-report/export-word?year=${year.value}`
    const response = await httpApi.get(url, { responseType: 'blob' })
    const blob = new Blob([response], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `审计报告_${year.value}.docx`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exportingWord.value = false
  }
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/AuditReportEditor.vue` | 修改 | 工具栏新增"导出 Word"按钮，`onExportWord` 函数调用后端已有接口并触发浏览器下载 |

---

### 需求 31：QC-17 附件充分性规则改用 ORM 查询

#### 问题根因

`AttachmentSufficiencyRule`（QC-17）使用裸 SQL（`sa.text`）查询 `attachment_working_paper` 表，且用 `except Exception: count = 0` 静默吞掉所有错误。如果表名或字段名变更，规则会静默失败，永远返回"有附件"。

#### 设计方案

改用 SQLAlchemy ORM 模型查询，异常时记录 warning 日志并返回空发现列表：

```python
# backend/app/services/qc_engine.py — AttachmentSufficiencyRule.check
import logging
logger = logging.getLogger(__name__)

try:
    from app.models.attachment_models import AttachmentWorkpaper  # 或对应关联模型
    count_q = (
        sa.select(sa.func.count())
        .select_from(AttachmentWorkpaper)
        .where(AttachmentWorkpaper.working_paper_id == context.working_paper.id)
    )
    count = (await context.db.execute(count_q)).scalar() or 0
except Exception as e:
    logger.warning("[QC-17] 查询附件关联失败，跳过检查: %s", e)
    return []  # 查询失败时返回空发现，不静默置 count=0

if count == 0:
    return [QCFindingItem(
        rule_id="QC-17",
        level="warning",
        message="底稿未关联任何附件，请确认附件充分性",
    )]
return []
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/qc_engine.py` | 修改 | `AttachmentSufficiencyRule.check` 改用 ORM 模型查询，异常时记录 warning 日志并返回空列表，删除 `except Exception: count = 0` 静默处理 |

---

### 需求 32：调整分录批量驳回支持逐条原因

#### 问题根因

`Adjustments.vue` 的批量驳回功能所有分录共用同一个 `rejectReason`，在审计实务中每条分录的驳回原因应该可以不同。

#### 设计方案

批量驳回弹窗新增两种模式切换：统一原因（默认）和逐条填写。

```html
<!-- Adjustments.vue 批量驳回弹窗内容 -->
<el-radio-group v-model="rejectMode" style="margin-bottom: 12px">
  <el-radio value="unified">统一原因</el-radio>
  <el-radio value="individual">逐条填写</el-radio>
</el-radio-group>

<!-- 统一原因模式 -->
<el-input
  v-if="rejectMode === 'unified'"
  v-model="rejectReason"
  type="textarea"
  :rows="3"
  placeholder="请输入驳回原因"
/>

<!-- 逐条填写模式 -->
<div v-else>
  <div
    v-for="row in selectedRows"
    :key="row.id"
    style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px"
  >
    <span style="min-width: 100px; flex-shrink: 0">{{ row.adjustment_no }}</span>
    <el-input
      v-model="individualReasons[row.id]"
      placeholder="驳回原因"
      size="small"
    />
  </div>
</div>
```

```typescript
// Adjustments.vue script 新增
const rejectMode = ref<'unified' | 'individual'>('unified')
const individualReasons = ref<Record<string, string>>({})

// 打开弹窗时初始化逐条原因
function openBatchRejectDialog() {
  rejectMode.value = 'unified'
  rejectReason.value = ''
  individualReasons.value = Object.fromEntries(
    selectedRows.value.map(r => [r.id, ''])
  )
  batchRejectVisible.value = true
}

// 提交时根据模式构建每条分录的原因
async function confirmBatchReject() {
  const rejectPayload = selectedRows.value.map(row => ({
    id: row.id,
    reason: rejectMode.value === 'unified'
      ? rejectReason.value
      : (individualReasons.value[row.id] || rejectReason.value),
  }))
  // 调用后端批量驳回接口，传入 rejectPayload
  await batchRejectAdjustments(projectId.value, rejectPayload)
  batchRejectVisible.value = false
  await loadAdjustments()
}
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/Adjustments.vue` | 修改 | 批量驳回弹窗新增 `rejectMode` 切换（统一/逐条），逐条模式展示每条分录的独立输入框，提交时按模式构建驳回原因 |

---

### 正确性属性补充（需求 26-32）

#### 属性 25：QC 汇总查询次数

*对任意*包含 N 份底稿的项目（N ≥ 1），`get_project_summary` 执行时发出的数据库查询次数应为常数（不随 N 增长），不得为 N 次。

**验证：需求 26.1**

---

#### 属性 26：定稿报告不可变性

*对任意*状态为 `final` 的审计报告，`updateAuditReportParagraph` 和将状态回退至 `review` 的 `updateAuditReportStatus` 请求均应返回 HTTP 403，报告内容不得发生变更。

**验证：需求 27.1、27.2**

---

#### 属性 27：QC-16 字段正确性

*对任意*底稿审定数与试算表 `audited_amount` 差异超过 0.01 元的情况，QC-16 规则应产生阻断级发现；差异不超过 0.01 元时，不应产生发现。

**验证：需求 28.1、28.2**

---

#### 属性 28：汇总年度与项目一致性

*对任意*项目上下文中 `projectStore.year` 有值的情况，`WorkpaperSummary` 使用的年度应等于 `projectStore.year`，不得使用系统当前年份。

**验证：需求 29.1**

---

#### 属性 29：QC-17 查询失败不静默

*对任意* ORM 查询抛出异常的情况，QC-17 规则应记录 warning 日志并返回空发现列表，不得将 `count` 静默置为 0 后继续执行后续逻辑。

**验证：需求 31.1、31.2**

---

### 错误处理补充（需求 26-32）

| 需求 | 场景 | 处理方式 |
|------|------|---------|
| 需求 26 | `wp_ids` 为空列表 | 直接返回空汇总，不执行子查询 |
| 需求 27 | 报告不存在 | 返回 HTTP 404，与现有逻辑一致 |
| 需求 28 | 底稿无对应试算表科目 | 返回空发现列表，不产生误报 |
| 需求 29 | `projectStore.year` 为 0 或 null | 降级为 `new Date().getFullYear()`，保持向后兼容 |
| 需求 30 | Word 导出接口返回错误 | `ElMessage.error('导出失败')`，不阻断其他操作 |
| 需求 31 | ORM 模型导入失败（模型路径变更） | 记录 warning 日志，返回空发现列表 |
| 需求 32 | 逐条模式下某条分录原因为空 | 降级使用统一原因（若有），否则以空字符串提交 |


---

## 需求 33-40：P0/P1/P2 补充改进

### 需求 33：PBC 清单和函证管理后端路由注册

#### 问题根因

`CollaborationIndex.vue` 的 PBC 清单和函证管理 Tab 前端 UI 已完成，但后端路由未注册到 `router_registry.py`，导致数据永远为空。PBC 清单（向客户索取资料清单）和函证管理（银行函证、应收账款函证）是审计项目管理的核心工具。

#### 设计方案

**步骤 1：检查后端路由文件是否存在**

检查 `backend/app/routers/` 目录下是否已有 `pbc.py`（PBC 清单）和 `confirmations.py`（函证管理）路由文件。

**若路由文件已存在但未注册：**

在 `router_registry.py` 中添加注册：
```python
from app.routers.pbc import router as pbc_router
from app.routers.confirmations import router as confirmations_router

# 在适当位置添加
app.include_router(pbc_router, prefix="/api", tags=["PBC清单"])
app.include_router(confirmations_router, prefix="/api", tags=["函证管理"])
```

**若路由文件不存在，需新建：**

`backend/app/routers/pbc.py`（最小骨架）：
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db, get_current_user
from uuid import UUID

router = APIRouter(prefix="/projects/{project_id}/pbc")

@router.get("")
async def list_pbc_items(project_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    # 查询 pbc_items 表（或对应模型）
    return {"items": []}
```

`backend/app/routers/confirmations.py`（最小骨架）：
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db, get_current_user
from uuid import UUID

router = APIRouter(prefix="/projects/{project_id}/confirmations")

@router.get("")
async def list_confirmations(project_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return {"items": []}
```

**前端 `CollaborationIndex.vue` `onMounted` 补充加载逻辑：**
```typescript
onMounted(async () => {
  // 已有逻辑保持不变
  // 新增：加载 PBC 清单
  try {
    const pbcRes = await httpApi.get(`/api/projects/${projectId.value}/pbc`)
    pbcItems.value = pbcRes.items || []
  } catch { pbcItems.value = [] }

  // 新增：加载函证列表
  try {
    const confRes = await httpApi.get(`/api/projects/${projectId.value}/confirmations`)
    confirmations.value = confRes.items || []
  } catch { confirmations.value = [] }
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/router_registry.py` | 修改 | 注册 PBC 清单和函证管理路由（`pbc_router`、`confirmations_router`） |
| `backend/app/routers/pbc.py` | 新增或确认 | PBC 清单路由（若不存在则新建最小骨架） |
| `backend/app/routers/confirmations.py` | 新增或确认 | 函证管理路由（若不存在则新建最小骨架） |
| `audit-platform/frontend/src/views/CollaborationIndex.vue` | 修改 | `onMounted` 中补充 PBC 和函证数据加载逻辑 |

---

### 需求 34：进度看板卡片直接跳转底稿编辑器

#### 问题根因

`ProjectProgressBoard.vue` 的看板卡片点击后跳转到底稿列表页（`/projects/{id}/workpapers`），而不是直接打开对应底稿编辑器。与 `ReviewInbox.vue` 的同类问题一致（需求 18 已修复 ReviewInbox）。

#### 设计方案

修改 `ProjectProgressBoard.vue` 中的 `goToWorkpaper` 函数，优先使用底稿 `id` 直接跳转到编辑器，无 `id` 时降级跳转到列表页：

```typescript
function goToWorkpaper(item: BoardItem) {
  if (item.id) {
    router.push({
      name: 'WorkpaperEditor',
      params: { projectId: projectId.value, wpId: item.id }
    })
  } else {
    // 无 wp_id 时降级跳转到列表页
    router.push(`/projects/${projectId.value}/workpapers`)
  }
}
```

实施前需确认 router 中 `WorkpaperEditor` 路由的实际 `name` 值（与需求 18 一致）。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/ProjectProgressBoard.vue` | 修改 | `goToWorkpaper` 函数改为优先跳转到 `WorkpaperEditor`，无 `id` 时降级跳转列表页 |

---

### 需求 35：个人工作台待办和工时数据加载

#### 问题根因

`PersonalDashboard.vue` 的"我的待办"（`todos`）和"本周工时"（`weekHours`）两个卡片永远为空，`onMounted` 中没有加载这两项数据的逻辑。

#### 设计方案

在 `PersonalDashboard.vue` 的 `onMounted` 中补充待办和工时加载逻辑：

```typescript
onMounted(async () => {
  // 已有逻辑：加载我的项目
  try { myProjects.value = await getMyAssignments() } catch { myProjects.value = [] }

  // 新增：加载待办（从 getMyTodos 或 getMyProcedureTasks）
  try { todos.value = await getMyTodos() } catch { todos.value = [] }

  // 新增：加载本周工时
  try {
    const staffInfo = await getMyStaffId()
    if (staffInfo?.staff_id) {
      const today = new Date()
      const weekStart = new Date(today)
      weekStart.setDate(today.getDate() - today.getDay() + 1)
      weekHours.value = await listWorkHours(staffInfo.staff_id, {
        start_date: weekStart.toISOString().slice(0, 10),
        end_date: today.toISOString().slice(0, 10),
      })
    }
  } catch { weekHours.value = [] }
})
```

注意：`getMyTodos`、`getMyStaffId`、`listWorkHours` 需确认是否已在 services 中存在，若不存在需新增对应 API 调用函数。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/PersonalDashboard.vue` | 修改 | `onMounted` 中补充待办（`getMyTodos`）和本周工时（`listWorkHours`）加载逻辑 |

---

### 需求 36：抽样增强年度从项目上下文获取

#### 问题根因

`SamplingEnhanced.vue` 的截止性测试年度硬编码为 `2025`，与 `WorkpaperSummary.vue` 同样的问题（需求 29 已修复 WorkpaperSummary）。跨年审计时查不到数据。

#### 设计方案

与需求 29 方案一致，从 `projectStore.year` 获取审计年度：

```typescript
// SamplingEnhanced.vue
import { useProjectStore } from '@/stores/project'
const projectStore = useProjectStore()

const cutoffForm = ref({
  codes: '6001',
  year: projectStore.year || new Date().getFullYear() - 1,  // 改为动态年度
  // ...其他字段不变
})
```

注意：`projectStore.year` 不存在时降级为 `new Date().getFullYear() - 1`（上一年度，符合审计惯例）。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/SamplingEnhanced.vue` | 修改 | 年度改为从 `projectStore.year` 获取，删除硬编码 `2025` |

---

### 需求 37：审计程序裁剪"参照其他单位"改为下拉选择

#### 问题根因

`ProcedureTrimming.vue` 的"参照其他单位"功能需要手动输入项目 ID（UUID），审计员不知道其他项目的 UUID，功能实际不可用。

#### 设计方案

将参照弹窗中的 UUID 输入框改为从 `listProjects()` 加载的下拉选择框：

```html
<!-- 修改 ProcedureTrimming.vue 参照弹窗 -->
<el-form-item label="参照项目">
  <el-select
    v-model="refProjectId"
    filterable
    placeholder="选择参照项目"
    style="width: 100%"
  >
    <el-option
      v-for="p in projectOptions"
      :key="p.id"
      :label="p.name || p.client_name"
      :value="p.id"
    />
  </el-select>
</el-form-item>
```

```typescript
// 加载项目列表
const projectOptions = ref<any[]>([])

onMounted(async () => {
  try { projectOptions.value = await listProjects() } catch { /* ignore */ }
  await loadProcedures()
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/ProcedureTrimming.vue` | 修改 | 参照弹窗改为 `el-select` 下拉选择，`onMounted` 中调用 `listProjects()` 加载项目列表 |

---

### 需求 38：工时编辑功能修正

#### 问题根因

`WorkHoursPage.vue` 的 `editHour` 函数将表单数据填入后打开"填报"弹窗，但 `submitHour` 调用的是 `createWorkHour`（创建），而非 `updateWorkHour`（更新）。编辑操作实际上会创建一条新记录，导致数据重复。

#### 设计方案

新增 `editingHourId` 状态区分编辑/新建模式，`submitHour` 根据该状态调用不同接口：

```typescript
// WorkHoursPage.vue 新增编辑状态
const editingHourId = ref<string | null>(null)

function editHour(row: WorkHourRecord) {
  editingHourId.value = row.id  // 记录正在编辑的记录 ID
  form.value = {
    work_date: row.work_date,
    project_id: row.project_id,
    hours: row.hours,
    description: row.description || '',
  }
  showCreateDialog.value = true
}

async function submitHour() {
  if (editingHourId.value) {
    // 编辑模式：调用更新接口
    await updateWorkHour(editingHourId.value, {
      hours: form.value.hours,
      description: form.value.description,
    })
    ElMessage.success('工时已更新')
    editingHourId.value = null
  } else {
    // 新建模式：调用创建接口
    const res = await createWorkHour(currentStaffId.value, form.value)
    warnings.value = res.warnings || []
    if (warnings.value.length === 0) ElMessage.success('工时已保存')
  }
  showCreateDialog.value = false
  form.value = { work_date: '', project_id: '', hours: 8, description: '' }
  await loadHours()
}
```

弹窗标题和提交按钮文案根据模式动态切换：
```html
<el-dialog :title="editingHourId ? '编辑工时' : '填报工时'" ...>
  ...
  <el-button type="primary" @click="submitHour">
    {{ editingHourId ? '更新' : '保存' }}
  </el-button>
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/WorkHoursPage.vue` | 修改 | 新增 `editingHourId` 状态，`editHour` 记录编辑 ID，`submitHour` 根据编辑状态调用 `updateWorkHour` 或 `createWorkHour`，弹窗按钮文案动态切换 |

---

### 需求 39：知识库文档预览携带认证头

#### 问题根因

`KnowledgeBase.vue` 的图片和 PDF 预览直接使用裸 URL 赋值给 `<img src>` 或 `<iframe src>`，不携带 Authorization 头。在需要认证的环境下，预览请求会返回 401，导致预览失败。

#### 设计方案

改为通过 `httpApi` 获取 blob，创建 Object URL 后赋值给 `previewUrl`，确保请求携带认证头：

```typescript
// KnowledgeBase.vue 修改预览逻辑
async function onPreviewDoc(doc: any) {
  previewDoc.value = doc
  previewUrl.value = ''
  previewText.value = null

  if (isImageFile(doc) || isPdfFile(doc)) {
    // 用 httpApi 获取 blob，创建 Object URL（携带认证头）
    try {
      const response = await httpApi.get(
        `/api/knowledge-library/documents/${doc.id}/download`,
        { responseType: 'blob' }
      )
      const blob = new Blob([response], {
        type: isPdfFile(doc) ? 'application/pdf' : 'image/*'
      })
      previewUrl.value = URL.createObjectURL(blob)
    } catch {
      ElMessage.error('预览加载失败')
    }
  }
  // ...其余逻辑不变（文本文件等）
}

// onBeforeUnmount 中清理 Object URL，防止内存泄漏
onBeforeUnmount(() => {
  if (previewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl.value)
  }
})
```

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/KnowledgeBase.vue` | 修改 | 图片/PDF 预览改为通过 `httpApi` 获取 blob 并创建 Object URL，`onBeforeUnmount` 中清理 Object URL |

---

### 需求 40：QC 归档检查结果缓存

#### 问题根因

`QCDashboard.vue` 的归档检查每次点击"执行归档前检查"都重新计算，没有缓存上次结果。对于大项目，这个检查可能很慢，且用户可能只是想查看上次的结果。

#### 设计方案

切换到"归档检查"Tab 时先尝试加载上次结果（GET 接口），不自动重新执行检查；提供"重新检查"按钮供用户手动触发：

```typescript
// QCDashboard.vue 修改归档检查逻辑
watch(activeTab, async (tab) => {
  if (tab === 'archive' && !archiveResult.value) {
    // 尝试加载上次结果（GET 接口，不重新执行检查）
    try {
      archiveResult.value = await getArchiveReadiness(projectId.value)
    } catch { /* 无上次结果，显示"执行检查"按钮 */ }
  }
})

// 手动触发重新检查
async function loadArchive() {
  archiveLoading.value = true
  try {
    archiveResult.value = await runArchiveReadinessCheck(projectId.value)
  } finally {
    archiveLoading.value = false
  }
}
```

模板中添加上次检查时间和"重新检查"按钮：
```html
<div v-if="archiveResult" class="archive-panel">
  <div class="archive-meta" v-if="archiveResult.checked_at">
    上次检查：{{ new Date(archiveResult.checked_at).toLocaleString('zh-CN') }}
    <el-button size="small" @click="loadArchive" :loading="archiveLoading">
      重新检查
    </el-button>
  </div>
  <!-- 原有检查结果展示不变 -->
</div>
<div v-else-if="!archiveLoading" class="archive-empty">
  <el-button type="primary" @click="loadArchive" :loading="archiveLoading">
    执行归档前检查
  </el-button>
</div>
```

注意：需区分 `getArchiveReadiness`（GET，加载上次结果）和 `runArchiveReadinessCheck`（POST，重新执行检查）两个接口。若后端只有一个接口，需在后端拆分或通过参数区分。

**文件变更：**

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `audit-platform/frontend/src/views/QCDashboard.vue` | 修改 | 切换到归档 Tab 时先 GET 加载上次结果，添加"重新检查"按钮和上次检查时间显示，`loadArchive` 函数手动触发重新检查 |

---

### 正确性属性补充（需求 33-40）

#### 属性 30：PBC 和函证路由可达性

*对任意*已注册的 PBC 和函证路由，`GET /api/projects/{id}/pbc` 和 `GET /api/projects/{id}/confirmations` 应返回 HTTP 200，不得返回 404。

**验证：需求 33.1、33.2、33.3**

---

#### 属性 31：看板跳转路径正确性

*对任意*包含有效 `id` 字段的看板卡片，点击后路由跳转的目标路径应包含 `workpapers/{wp_id}/edit`，不得跳转到底稿列表页。

**验证：需求 34.1、34.2**

---

#### 属性 32：工时编辑幂等性

*对任意*已存在的工时记录，执行编辑并保存后，数据库中该记录的数量应保持不变（不增加），且记录内容应反映最新修改值。

**验证：需求 38.1**

---

#### 属性 33：预览 URL 认证完整性

*对任意*需要认证的文档预览请求，`previewUrl` 应为 `blob:` 协议的 Object URL，不得为直接指向后端的裸 HTTP URL。

**验证：需求 39.1**

---

#### 属性 34：归档检查缓存一致性

*对任意*已有上次检查结果的项目，切换到"归档检查"Tab 时不应触发新的检查请求，`archiveResult` 应等于上次检查的结果。

**验证：需求 40.1**

---

### 错误处理补充（需求 33-40）

| 需求 | 场景 | 处理方式 |
|------|------|---------|
| 需求 33 | 路由文件不存在 | 新建最小骨架路由文件，返回空列表，不阻断前端渲染 |
| 需求 34 | `item.id` 为空或 undefined | 降级跳转到底稿列表页 `/projects/{id}/workpapers` |
| 需求 35 | `getMyTodos` 接口不存在 | `catch` 静默处理，`todos.value = []`，不阻断页面加载 |
| 需求 35 | `getMyStaffId` 返回无 `staff_id` | 跳过工时加载，`weekHours.value = []` |
| 需求 36 | `projectStore.year` 为 0 或 null | 降级为 `new Date().getFullYear() - 1` |
| 需求 37 | `listProjects()` 请求失败 | `catch` 静默处理，`projectOptions.value = []`，下拉框显示空 |
| 需求 38 | `updateWorkHour` 接口不存在 | 检查 services 中是否已有该函数，若无则新增 |
| 需求 39 | blob 请求失败（401/403/500） | `ElMessage.error('预览加载失败')`，`previewUrl.value` 保持空字符串 |
| 需求 39 | 组件销毁时 Object URL 未清理 | `onBeforeUnmount` 中检查 `blob:` 前缀后调用 `URL.revokeObjectURL` |
| 需求 40 | 后端无 GET 归档结果接口 | `catch` 静默处理，显示"执行检查"按钮，等待用户手动触发 |
| 需求 40 | 重新检查请求失败 | `ElMessage.error('检查失败')`，保留上次结果不清空 |


---

## 新增需求设计（需求 41-46）

### 需求 41：底稿列表编制人筛选下拉框填充

#### 现状分析

`WorkpaperList.vue` 中 `filterAssignee` 的 `el-select` 只有一个硬编码的 `<el-option label="全部" value="" />`，`userOptions` 虽然在看板分配弹窗中按需加载，但没有在 `onMounted` 时加载，也没有填充到筛选下拉框。

#### 设计方案

在 `onMounted` 中调用 `listUsers()` 加载用户列表，同时填充 `userOptions`（用于分配弹窗）和 `userNameMap`（用于 UUID→姓名映射），筛选下拉框直接绑定 `userOptions`。

**WorkpaperList.vue 修改：**
```typescript
// onMounted 中补充用户列表加载
onMounted(async () => {
  await fetchData()
  // 加载用户列表（同时用于筛选下拉框和 UUID→姓名映射）
  try {
    const users = await listUsers()
    userOptions.value = users
    userNameMap.value = new Map(
      users.map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默 */ }
  // ... 其他初始化
})
```

**模板中替换编制人筛选下拉框：**
```html
<!-- 原来（只有"全部"） -->
<el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 130px">
  <el-option label="全部" value="" />
</el-select>

<!-- 修改后（动态填充用户列表） -->
<el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 130px">
  <el-option
    v-for="u in userOptions"
    :key="u.id"
    :label="u.full_name || u.username"
    :value="u.id"
  />
</el-select>
```

注意：`filterAssignee` 的值改为 UUID（`u.id`），`treeData` computed 中的 `filterAssignee.value && w.assigned_to !== filterAssignee.value` 逻辑不变，因为 `assigned_to` 字段本身就是 UUID。

---

### 需求 42：底稿编辑器状态栏姓名显示

#### 现状分析

`WorkpaperEditor.vue` 状态栏直接显示 `wpDetail.assigned_to` 和 `wpDetail.reviewer`，这两个字段可能是 UUID 字符串（取决于后端返回格式）。

#### 设计方案

在 `WorkpaperEditor.vue` 中加载底稿详情后，额外请求用户信息建立映射，或直接在加载底稿时通过 `listUsers()` 建立本地缓存。

**WorkpaperEditor.vue 修改：**
```typescript
import { listUsers } from '@/services/commonApi'

const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? uuid  // 降级显示 UUID（不显示"未知用户"，因为可能是用户名字符串）
}

// 在 initUniver 中，加载底稿详情后异步加载用户映射
async function loadUserMap() {
  try {
    const users = await listUsers()
    userNameMap.value = new Map(
      users.map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默 */ }
}

// initUniver 中调用（非阻塞）
loadUserMap()
```

**模板状态栏修改：**
```html
<!-- 原来 -->
<span>编制人: {{ wpDetail.assigned_to || '未分配' }}</span>
<span>复核人: {{ wpDetail.reviewer || '未分配' }}</span>

<!-- 修改后 -->
<span>编制人: {{ resolveUserName(wpDetail.assigned_to) }}</span>
<span>复核人: {{ resolveUserName(wpDetail.reviewer) }}</span>
```

---

### 需求 43：底稿编辑器版本历史入口

#### 设计方案

在工具栏右侧新增"版本历史"按钮，点击后以侧边抽屉（`el-drawer`）展示版本列表。

**WorkpaperEditor.vue 修改：**
```typescript
const showVersionDrawer = ref(false)
const versionList = ref<any[]>([])
const versionLoading = ref(false)

async function onShowVersions() {
  showVersionDrawer.value = true
  versionLoading.value = true
  try {
    const data = await httpApi.get(`/api/workpapers/${wpId.value}/versions`)
    versionList.value = Array.isArray(data) ? data : (data.versions || [])
  } catch {
    ElMessage.error('加载版本历史失败')
    versionList.value = []
  } finally {
    versionLoading.value = false
  }
}
```

**模板新增按钮和抽屉：**
```html
<!-- 工具栏新增按钮 -->
<el-button size="small" @click="onShowVersions">📋 版本历史</el-button>

<!-- 版本历史抽屉 -->
<el-drawer v-model="showVersionDrawer" title="版本历史" size="320px" :append-to-body="true">
  <div v-loading="versionLoading">
    <el-timeline v-if="versionList.length">
      <el-timeline-item
        v-for="v in versionList"
        :key="v.version"
        :timestamp="v.saved_at?.slice(0, 19) || '-'"
        placement="top"
      >
        <div style="font-size: 13px">v{{ v.version }}</div>
        <div style="font-size: 11px; color: #999">{{ v.saved_by || '系统' }}</div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="暂无版本记录" />
  </div>
</el-drawer>
```

---

### 需求 44：底稿编辑器自动保存

#### 设计方案

复用项目已有的 `useAutoSave` composable（附注编辑器在用），传入 `dirty` ref 和 `onSave` 函数。

**WorkpaperEditor.vue 修改：**
```typescript
import { useAutoSave } from '@/composables/useAutoSave'

// 在 initUniver 完成后启动自动保存（需要 univerAPI 已初始化）
// 注意：useAutoSave 需要 projectId 前缀避免跨项目冲突
const { startAutoSave, stopAutoSave } = useAutoSave({
  key: `wp_autosave_${projectId.value}_${wpId.value}`,
  dirty,
  onSave: async () => {
    await onSave()
  },
  interval: 30000,  // 30 秒
  onSuccess: () => {
    // 状态栏显示"已自动保存"（3 秒后消失）
    autoSaveMsg.value = '已自动保存'
    setTimeout(() => { autoSaveMsg.value = '' }, 3000)
  },
  onError: () => { /* 静默忽略 */ },
})

const autoSaveMsg = ref('')

// initUniver 完成后启动
onMounted(() => {
  // initUniver 是异步的，在 loading.value = false 后启动
})

// 在 loading.value 变为 false 时启动（watch）
watch(loading, (val) => {
  if (!val) startAutoSave()
})

onUnmounted(() => {
  stopAutoSave()
})
```

**状态栏新增自动保存提示：**
```html
<span v-if="autoSaveMsg" style="color: #67c23a">✓ {{ autoSaveMsg }}</span>
```

---

### 需求 45：底稿并发编辑版本冲突检测

#### 设计方案

**后端 `univer-save` 端点修改（`working_paper.py`）：**
```python
@router.post("/working-papers/{wp_id}/univer-save")
async def save_univer_data(
    project_id: UUID,
    wp_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    snapshot = body.get("snapshot")
    expected_version = body.get("expected_version")  # 新增：客户端期望的版本号

    # ... 查询 wp ...

    # 并发冲突检测（仅当客户端传入 expected_version 时检查）
    if expected_version is not None and wp.file_version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "version_conflict",
                "message": f"底稿已被他人修改（服务器版本 v{wp.file_version}，您的版本 v{expected_version}），请刷新后重试",
                "server_version": wp.file_version,
                "expected_version": expected_version,
            }
        )
    # ... 后续保存逻辑不变 ...
```

**前端 `WorkpaperEditor.vue` 修改（`onSave` 函数）：**
```typescript
async function onSave(): Promise<boolean> {
  if (!univerAPI || !wpDetail.value) return false
  saving.value = true
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')
    const snapshot = workbook.getSnapshot()

    const data = await httpApi.post(
      `/api/projects/${projectId.value}/working-papers/${wpId.value}/univer-save`,
      {
        snapshot,
        expected_version: wpDetail.value.file_version,  // 新增：携带当前版本号
      },
    )
    dirty.value = false
    ElMessage.success(data?.message || '保存成功')
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    return true
  } catch (err: any) {
    if (err?.response?.status === 409) {
      // 版本冲突处理
      const detail = err.response.data?.detail || {}
      try {
        await ElMessageBox.confirm(
          detail.message || '底稿已被他人修改，请选择操作',
          '版本冲突',
          {
            confirmButtonText: '刷新并放弃本地修改',
            cancelButtonText: '强制覆盖',
            type: 'warning',
          }
        )
        // 用户选择刷新：重新加载底稿数据
        dirty.value = false
        await initUniver()
      } catch {
        // 用户选择强制覆盖：不传 expected_version，直接保存
        await httpApi.post(
          `/api/projects/${projectId.value}/working-papers/${wpId.value}/univer-save`,
          { snapshot: univerAPI.getActiveWorkbook()?.getSnapshot() },
        )
        dirty.value = false
        wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
      }
    } else {
      ElMessage.error('保存失败: ' + (err?.response?.data?.detail || err?.message || ''))
    }
    return false
  } finally {
    saving.value = false
  }
}
```

---

### 需求 46：预填充引擎保留公式字段

#### 现状分析

`prefill_engine.py` 中 `prefill_workpaper_real` 函数在写入计算值时执行 `cell_obj.value = value`，这会将 Excel 单元格的公式字符串替换为静态数字，同时将原公式移入 comment。这破坏了五环联动：底稿中的 `=TB()` 公式被覆盖后，下次重算时无法重新取数。

#### 设计方案

预填充的正确做法是：**只更新 Univer JSON 数据中的 `v` 字段（显示值），保留 `f` 字段（公式）**。预填充不应修改 xlsx 文件本身，而应修改 Univer 数据层。

**修改策略：**

预填充引擎应改为操作 Univer 数据（`structure.json` 或直接调用 `univer-save` 端点），而非直接修改 xlsx 文件。

**`prefill_engine.py` 修改（`prefill_workpaper_real` 函数）：**
```python
# 写入单元格时，不再覆盖公式，改为写入 Univer 数据的 v 字段
# 原来（破坏公式）：
cell_obj.value = value  # 覆盖公式为静态数字

# 修改后（保留公式，只更新 structure.json 中的 v 字段）：
# 1. 不修改 xlsx 文件
# 2. 更新 structure.json 中对应单元格的 v 字段
structure_path = fp.with_suffix(".structure.json")
if structure_path.exists():
    import json
    with open(structure_path, "r", encoding="utf-8") as sf:
        structure = json.load(sf)
    # 找到对应 sheet 和单元格，只更新 v 字段
    sheet_data = structure.get("sheets", {}).get(f["sheet"], {})
    cell_data = sheet_data.get("cellData", {})
    row_idx = str(cell_obj.row - 1)  # 0-indexed
    col_idx = str(cell_obj.column - 1)
    if row_idx not in cell_data:
        cell_data[row_idx] = {}
    if col_idx not in cell_data[row_idx]:
        cell_data[row_idx][col_idx] = {}
    cell_data[row_idx][col_idx]["v"] = value  # 只更新 v，不动 f
    with open(structure_path, "w", encoding="utf-8") as sf:
        json.dump(structure, sf, ensure_ascii=False, indent=2)
    filled += 1
```

注意：此方案需要 `structure.json` 已存在（底稿已通过 Univer 保存过一次）。若 `structure.json` 不存在，降级为原有行为（写入 xlsx），但不移入 comment。

---

### 新增正确性属性（需求 41-46）

#### 属性 35：编制人筛选下拉框数据完整性

*对任意*已加载用户列表的底稿列表页，"编制人"筛选下拉框中的选项数量应等于 `listUsers()` 返回的用户数量，且每个选项的 `value` 应为对应用户的 UUID。

**验证：需求 41.1、41.2**

---

#### 属性 36：底稿编辑器状态栏姓名一致性

*对任意*底稿的 `assigned_to` UUID，若该 UUID 存在于用户列表中，则状态栏显示的编制人姓名应与 `listUsers()` 返回的对应用户 `full_name || username` 一致。

**验证：需求 42.1、42.2**

---

#### 属性 37：版本冲突检测正确性

*对任意*两个并发保存请求（携带相同的 `expected_version`），后到达服务器的请求应收到 HTTP 409 响应，且响应中的 `server_version` 应等于先到达请求保存后的版本号。

**验证：需求 45.1、45.2**

---

#### 属性 38：预填充不破坏公式

*对任意*含 `=TB()`/`=WP()`/`=AUX()` 公式的底稿，预填充操作完成后，`structure.json` 中对应单元格的 `f` 字段应保持不变，`v` 字段应等于公式的计算结果。

**验证：需求 46.1、46.2**

---

### 错误处理补充（需求 41-46）

| 需求 | 场景 | 处理方式 |
|------|------|---------|
| 需求 41 | `listUsers()` 请求失败 | `catch` 静默处理，筛选下拉框只显示"全部"，不阻断页面加载 |
| 需求 42 | `listUsers()` 请求失败 | `catch` 静默处理，状态栏降级显示原始 UUID 或"未分配" |
| 需求 43 | `GET /api/workpapers/{wp_id}/versions` 失败 | `ElMessage.error('加载版本历史失败')`，抽屉显示空状态 |
| 需求 44 | `useAutoSave` 自动保存失败 | 静默忽略，保留 `dirty` 标记，等待下次触发或用户手动保存 |
| 需求 45 | 用户选择"强制覆盖"后再次失败 | `ElMessage.error('保存失败')`，保留 `dirty` 标记 |
| 需求 46 | `structure.json` 不存在 | 降级为写入 xlsx 但不移入 comment，记录 warning 日志 |
