# Sprint 2（P1）设计文档

## D1：navItems 动态化

文件：`layouts/ThreeColumnLayout.vue`

```ts
import { useRoleContextStore } from '@/stores/roleContext'

const roleStore = useRoleContextStore()

const ICON_MAP: Record<string, Component> = {
  Odometer, FolderOpened, User, Timer, DataAnalysis,
  Connection, Stamp, Box, Paperclip, UserFilled,
}

const FALLBACK_NAV = [ /* 当前硬编码 10 项 */ ]

function patchNavByRole(nav: NavItem[], role: string): NavItem[] {
  return nav.map(item => {
    if (item.key === 'mgmt-dashboard') {
      if (role === 'manager') return { ...item, path: '/dashboard/manager' }
      if (role === 'partner') return { ...item, path: '/dashboard/partner' }
    }
    return item
  })
}

const navItems = computed(() => {
  if (import.meta.env.VITE_DYNAMIC_NAV !== 'true') {
    return patchNavByRole(FALLBACK_NAV, roleStore.effectiveRole)
  }
  const backend = roleStore.navItems
  if (Array.isArray(backend) && backend.length > 0) {
    return backend.map(item => ({
      ...item,
      icon: ICON_MAP[item.icon] || FolderOpened,
    }))
  }
  return patchNavByRole(FALLBACK_NAV, roleStore.effectiveRole)
})
```

## D2：useEditingLock composable

文件：`composables/useEditingLock.ts`

```ts
import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export function useEditingLock(params: {
  resourceType: string
  resourceId: Ref<string>
  heartbeatMs?: number
}) {
  const locked = ref(false)
  const lockedBy = ref<string | null>(null)
  const isMine = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function acquire() {
    if (!params.resourceId.value) return
    const res = await api.post(`/api/editing-locks/acquire`, {
      resource_type: params.resourceType,
      resource_id: params.resourceId.value,
    })
    locked.value = true
    isMine.value = res?.acquired ?? false
    lockedBy.value = res?.locked_by_name ?? null
  }

  async function release() {
    if (!isMine.value) return
    await api.post(`/api/editing-locks/release`, {
      resource_type: params.resourceType,
      resource_id: params.resourceId.value,
    }).catch(() => {})
    locked.value = false
    isMine.value = false
  }

  async function heartbeat() {
    if (!isMine.value) return
    await api.post(`/api/editing-locks/heartbeat`, {
      resource_type: params.resourceType,
      resource_id: params.resourceId.value,
    }).catch(() => {})
  }

  onMounted(() => {
    acquire()
    timer = setInterval(heartbeat, params.heartbeatMs ?? 120_000)
    window.addEventListener('beforeunload', release)
  })

  onUnmounted(() => {
    release()
    if (timer) clearInterval(timer)
    window.removeEventListener('beforeunload', release)
  })

  return { locked, lockedBy, isMine, acquire, release }
}
```

## D3：useWorkpaperAutoSave

文件：`composables/useWorkpaperAutoSave.ts`

```ts
import { ref, onMounted, onUnmounted } from 'vue'

export function useWorkpaperAutoSave(onSave: () => Promise<void>, intervalMs = 120_000) {
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const lastError = ref<string | null>(null)
  const isDirty = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function markDirty() { isDirty.value = true }

  async function doSave() {
    if (!isDirty.value || saving.value) return
    saving.value = true
    lastError.value = null
    try {
      await onSave()
      isDirty.value = false
      lastSavedAt.value = new Date()
    } catch (e: any) {
      lastError.value = e.message || '保存失败'
    } finally {
      saving.value = false
    }
  }

  onMounted(() => { timer = setInterval(doSave, intervalMs) })
  onUnmounted(() => { if (timer) clearInterval(timer) })

  return { saving, lastSavedAt, lastError, isDirty, markDirty, doSave }
}
```

## D4：errorHandler.ts

文件：`utils/errorHandler.ts`

```ts
import { ElMessage, ElNotification } from 'element-plus'

export function handleApiError(e: any, context: string) {
  const status = e?.response?.status || e?.status
  const traceId = e?.response?.headers?.['x-request-id'] || ''
  const detail = e?.response?.data?.detail || e?.data?.detail

  if (!status) {
    ElMessage.error(`${context}：网络不通，请检查连接`)
    return
  }
  if (status === 401) return // http.ts 已处理刷新
  if (status === 403) {
    ElMessage.warning(`${context}：无权操作`)
    return
  }
  if (status === 404) {
    ElMessage.warning(`${context}：资源不存在`)
    return
  }
  if (status === 409) {
    const msg = detail?.message || '数据冲突'
    ElNotification({ title: '冲突', message: msg, type: 'warning' })
    return
  }
  // 5xx
  ElNotification({
    title: `${context}失败`,
    message: `系统错误，请联系管理员${traceId ? `（trace: ${traceId}）` : ''}`,
    type: 'error',
    duration: 8000,
  })
}
```

## D5：ShortcutHelpDialog

文件：`components/common/ShortcutHelpDialog.vue`

```vue
<template>
  <el-dialog v-model="visible" title="键盘快捷键" width="480" append-to-body>
    <el-input v-model="search" placeholder="搜索快捷键..." clearable style="margin-bottom: 12px" />
    <div v-for="(group, scope) in grouped" :key="scope" class="gt-shortcut-group">
      <h4>{{ scope }}</h4>
      <div v-for="s in group" :key="s.key" class="gt-shortcut-row">
        <kbd>{{ s.key }}</kbd>
        <span>{{ s.description }}</span>
      </div>
    </div>
  </el-dialog>
</template>
```

## D6：Stale 三态

TrialBalance.vue 一致性列模板改为：
```vue
<template #default="{ row }">
  <span v-if="row.wp_consistency?.status === 'consistent'" style="color: var(--gt-color-success)">✅</span>
  <span v-else-if="row.wp_consistency?.status === 'inconsistent'" style="color: var(--gt-color-coral)">⚠️</span>
  <el-tooltip v-else-if="row.wp_consistency?.status === 'stale'" content="上游数据已变更，需重算">
    <span style="color: var(--gt-color-teal); cursor: pointer" @click="onRecalcWp(row)">🔄</span>
  </el-tooltip>
  <span v-else style="color: #ccc">—</span>
</template>
```

## D7：useEditMode 接入模式

文件：各编辑页统一接入模式

```ts
// 在 <script setup> 中
import { useEditMode } from '@/composables/useEditMode'
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

// GtToolbar 绑定
// :show-edit-toggle="true" :is-editing="isEditing" @edit-toggle="isEditing ? exitEdit() : enterEdit()"

// 路由拦截（useEditMode 内部已通过 onBeforeRouteLeave 实现）
// 未保存时自动调用 confirmLeave
```

编辑模式黄色横条 CSS（`styles/gt-polish.css` 追加）：
```css
.gt-edit-mode-ribbon {
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(90deg, #fff8e6 0%, #fff3cd 100%);
  border-bottom: 1px solid #ffc107;
  font-size: 12px;
  color: #856404;
  font-weight: 500;
}
```

## D8：工时 Tab 布局

文件：`views/WorkHoursPage.vue`

```vue
<template>
  <div class="gt-workhours gt-fade-in">
    <GtPageHeader title="工时管理" />
    <el-tabs v-model="activeTab">
      <el-tab-pane label="我的填报" name="mine">
        <!-- 现有 WorkHoursPage 填报内容 -->
      </el-tab-pane>
      <el-tab-pane v-if="can('approve_workhours')" label="待审批" name="approve">
        <!-- 从 WorkHoursApproval.vue 迁入的内容 -->
      </el-tab-pane>
      <el-tab-pane label="统计" name="stats">
        <!-- 本周/本月统计卡片 -->
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

## D9：右键菜单各视图注入清单

通过 CellContextMenu 的默认 slot 注入：

```vue
<!-- TrialBalance.vue -->
<CellContextMenu ...>
  <div class="gt-ucell-ctx-divider" />
  <div class="gt-ucell-ctx-item" @click="penetrate.toLedger(row.account_code)">
    <span class="gt-ucell-ctx-icon">📖</span> 穿透到序时账
  </div>
  <div class="gt-ucell-ctx-item" @click="penetrate.toWorkpaper(row.wp_code)">
    <span class="gt-ucell-ctx-icon">📋</span> 打开底稿
  </div>
  <div class="gt-ucell-ctx-item" @click="penetrate.toAdjustment(row.account_code)">
    <span class="gt-ucell-ctx-icon">✏️</span> 查看调整分录
  </div>
</CellContextMenu>

<!-- ReportView.vue -->
<CellContextMenu ...>
  <div class="gt-ucell-ctx-divider" />
  <div class="gt-ucell-ctx-item" @click="drillReportRow(row)">
    <span class="gt-ucell-ctx-icon">🔍</span> 穿透到行明细
  </div>
  <div class="gt-ucell-ctx-item" @click="showRowFormula(row)">
    <span class="gt-ucell-ctx-icon">ƒx</span> 查看行公式
  </div>
</CellContextMenu>

<!-- Adjustments.vue -->
<CellContextMenu ...>
  <div class="gt-ucell-ctx-divider" />
  <div class="gt-ucell-ctx-item" @click="convertToMisstatement(row)">
    <span class="gt-ucell-ctx-icon">⚠️</span> 转为未更正错报
  </div>
</CellContextMenu>

<!-- DisclosureEditor.vue -->
<CellContextMenu ...>
  <div class="gt-ucell-ctx-divider" />
  <div class="gt-ucell-ctx-item" @click="fetchDataToCell(row, col)">
    <span class="gt-ucell-ctx-icon">📥</span> 取数到该单元格
  </div>
</CellContextMenu>

<!-- ConsolidationIndex.vue -->
<CellContextMenu ...>
  <div class="gt-ucell-ctx-divider" />
  <div class="gt-ucell-ctx-item" @click="drillToCompanies(row)">
    <span class="gt-ucell-ctx-icon">🏢</span> 穿透到企业构成
  </div>
</CellContextMenu>
```

## D10：operationHistory.cell_edit 结构

文件：`utils/operationHistory.ts` 扩展

```ts
interface CellEditOperation extends Operation {
  type: 'cell_edit'
  cellRef: string          // e.g. "row3.col_amount"
  oldValue: any
  newValue: any
  tableId: string          // 表格实例标识
}

// GtEditableTable @change handler:
function onCellChange(rowIdx: number, colKey: string, oldVal: any, newVal: any) {
  operationHistory.execute({
    type: 'cell_edit',
    description: `修改 [${rowIdx}].${colKey}`,
    execute: async () => { /* 已经改了，noop */ },
    undo: async () => {
      // 恢复旧值
      tableData.value[rowIdx][colKey] = oldVal
      // 触发后端保存（如需要）
    },
  })
}
```

## D11：Trace ID 存储与展示

文件：`utils/http.ts` 响应拦截器追加

```ts
// 模块级变量
let lastTraceId = ''
export function getLastTraceId() { return lastTraceId }

// 在响应拦截器中
http.interceptors.response.use(
  (response) => {
    lastTraceId = response.headers['x-request-id'] || ''
    // ... 现有解包逻辑
    return response
  },
  (error) => {
    lastTraceId = error?.response?.headers?.['x-request-id'] || ''
    // ... 现有错误处理
    return Promise.reject(error)
  }
)
```

errorHandler.ts 中引用：
```ts
import { getLastTraceId } from '@/utils/http'

// 5xx 分支
const traceId = getLastTraceId()
ElNotification({
  title: `${context}失败`,
  dangerouslyUseHTMLString: true,
  message: `系统错误，请联系管理员<br/><small style="cursor:pointer;color:#4b2d77" onclick="navigator.clipboard.writeText('${traceId}')">trace: ${traceId} 📋</small>`,
  type: 'error',
  duration: 10000,
})
```
