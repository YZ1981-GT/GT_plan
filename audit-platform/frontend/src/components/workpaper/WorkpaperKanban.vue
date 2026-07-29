<template>
  <div class="wp-kanban" v-loading="loading">
    <!-- 顶部统计 KPI 卡片（点击联动筛选） -->
    <div class="kanban-stats">
      <div class="kanban-stat-card" :class="{ 'is-active': !focusColumn }" @click="focusColumn = ''">
        <span class="kanban-stat-card__num">{{ stats.total }}</span>
        <span class="kanban-stat-card__label">总数</span>
      </div>
      <div
        class="kanban-stat-card kanban-stat-card--highlight"
        :title="`完成率 = 已通过 /（总数 − 不适用）\n已通过 ${columnCounts.completed} · 不适用 ${stats.not_applicable || 0} · 总数 ${stats.total}`"
      >
        <span class="kanban-stat-card__num">{{ stats.completion_rate }}%</span>
        <span class="kanban-stat-card__label">完成率</span>
        <el-progress :percentage="Number(stats.completion_rate) || 0" :stroke-width="4" :show-text="false" color="#fff" style="margin-top: 4px" />
      </div>
      <div class="kanban-stat-card" v-for="col in columns" :key="col.key"
        :class="{ 'is-active': focusColumn === col.key }"
        @click="focusColumn = focusColumn === col.key ? '' : col.key">
        <span class="kanban-stat-card__num" :style="{ color: columnColors[col.key] }">{{ columnCounts[col.key] }}</span>
        <span class="kanban-stat-card__label">{{ col.label }}</span>
      </div>
    </div>

    <!-- 视图切换：按状态 / 按人（负责人查看每人完成情况） -->
    <div class="kanban-toolbar">
      <el-segmented
        :model-value="viewMode"
        :options="viewOptions"
        size="small"
        @change="onViewChange"
      />
      <template v-if="viewMode === 'status'">
        <el-select
          v-model="cycleFilter" placeholder="全部循环" size="small" clearable filterable
          class="kanban-toolbar__cycle"
        >
          <el-option v-for="c in cycleOptions" :key="c" :label="c + ' 循环'" :value="c" />
        </el-select>
        <el-input
          v-model="keyword" placeholder="搜索编码 / 名称" size="small" clearable
          :prefix-icon="Search" class="kanban-toolbar__search"
        />
        <el-tag v-if="assigneeFilter" closable size="small" type="primary" @close="assigneeFilter = null">
          仅看：{{ assigneeFilter.name }}
        </el-tag>
        <span v-if="isFiltered" class="kanban-toolbar__hint">
          筛选后 {{ filteredTotal }} / {{ stats.total }}
        </span>
      </template>
      <span v-else class="kanban-toolbar__hint">
        共 {{ assigneeRows.length }} 人 · 按完成率排序 · 点击行查看该人底稿
      </span>
    </div>

    <!-- 按状态：看板列 -->
    <div v-if="viewMode === 'status'" class="kanban-columns" :class="{ 'has-focus': !!focusColumn }">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-column"
        :class="{ 'is-focused': focusColumn === col.key, 'is-dimmed': focusColumn && focusColumn !== col.key }"
      >
        <div class="column-header" :style="{ borderTopColor: columnColors[col.key] }">
          <span class="column-title">{{ col.label }}</span>
          <span class="column-count">{{ filteredKanbanData[col.key]?.length || 0 }}</span>
        </div>

        <div class="column-body">
          <div
            v-for="item in visibleItems(col.key)"
            :key="item.wp_code"
            class="kanban-card"
            :class="{ 'is-stale': item.stale }"
            @click="$emit('select', item)"
          >
            <div class="card-header">
              <span class="card-code">{{ item.wp_code }}</span>
              <span class="card-header__right">
                <el-tag v-if="item.stale" size="small" type="warning" effect="light" class="card-stale-tag">数据过期</el-tag>
                <span class="card-cycle-badge">{{ item.audit_cycle }}</span>
              </span>
            </div>
            <div class="card-name">{{ item.wp_name }}</div>
            <!-- 进度条 -->
            <div class="card-progress" v-if="item.total_steps">
              <el-progress
                :percentage="Math.round((item.completed_steps || 0) / item.total_steps * 100)"
                :stroke-width="3"
                :show-text="false"
                :color="columnColors[col.key]"
              />
              <span class="card-progress__text">{{ item.completed_steps || 0 }}/{{ item.total_steps }}</span>
            </div>
            <!-- 编制人 / 复核人 -->
            <div class="card-footer" v-if="item.assigned_to || item.reviewer">
              <span v-if="item.assigned_to" class="card-role">
                <el-icon :size="12"><User /></el-icon>
                <span class="card-assignee">{{ item.assigned_to_name || item.assigned_to?.slice(0, 8) }}</span>
              </span>
              <span v-if="item.reviewer" class="card-role card-role--reviewer">
                <el-icon :size="12"><Check /></el-icon>
                <span class="card-assignee">{{ item.reviewer_name || item.reviewer?.slice(0, 8) }}</span>
              </span>
              <span v-if="item.updated_at" class="card-time">{{ fmtRelTime(item.updated_at) }}</span>
            </div>
            <div class="card-footer card-actions" v-else-if="canAssign">
              <span v-if="item.updated_at" class="card-time">{{ fmtRelTime(item.updated_at) }}</span>
              <el-button size="small" text type="primary" @click.stop="$emit('assign', item)">
                分配
              </el-button>
            </div>
            <div class="card-footer" v-else>
              <span class="card-unassigned">未分配</span>
              <span v-if="item.updated_at" class="card-time">{{ fmtRelTime(item.updated_at) }}</span>
            </div>
          </div>

          <!-- 增量加载 -->
          <el-button
            v-if="hasMore(col.key)"
            text size="small" class="column-loadmore"
            @click="loadMore(col.key)"
          >
            加载更多（剩余 {{ remaining(col.key) }}）
          </el-button>

          <!-- 空态引导 -->
          <div v-if="!filteredKanbanData[col.key]?.length" class="column-empty">
            <div class="column-empty__icon">{{ isFiltered ? '🔍' : (col.key === 'completed' ? '🎉' : '📋') }}</div>
            <div class="column-empty__text">
              {{ isFiltered ? '当前筛选无匹配底稿' :
                 col.key === 'not_started' ? '所有底稿已开始编制' :
                 col.key === 'under_review' ? '暂无待复核底稿' :
                 col.key === 'completed' ? '暂无已通过底稿' : '暂无底稿' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 按人：每位编制人完成情况（负责人视角） -->
    <div v-else class="kanban-assignee">
      <el-table
        :data="assigneeRows"
        size="small"
        stripe
        empty-text="暂无可见底稿"
        style="width: 100%"
        class="kanban-assignee__table"
        @row-click="onAssigneeRowClick"
      >
        <el-table-column label="编制人" min-width="140">
          <template #default="{ row }">
            <div class="assignee-cell">
              <span class="assignee-avatar" :class="{ 'is-unassigned': !row.user_id }">
                {{ (row.name || '?').slice(0, 1) }}
              </span>
              <span class="assignee-name" :class="{ 'is-unassigned': !row.user_id }">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="待编制" width="90" align="center">
          <template #default="{ row }"><span :style="{ color: columnColors.not_started }">{{ row.not_started }}</span></template>
        </el-table-column>
        <el-table-column label="编制中" width="90" align="center">
          <template #default="{ row }"><span :style="{ color: columnColors.in_progress }">{{ row.in_progress }}</span></template>
        </el-table-column>
        <el-table-column label="待复核" width="90" align="center">
          <template #default="{ row }"><span :style="{ color: columnColors.under_review }">{{ row.under_review }}</span></template>
        </el-table-column>
        <el-table-column label="已通过" width="90" align="center">
          <template #default="{ row }"><span :style="{ color: columnColors.completed }">{{ row.completed }}</span></template>
        </el-table-column>
        <el-table-column label="合计" width="80" align="center">
          <template #default="{ row }"><strong>{{ row.total }}</strong></template>
        </el-table-column>
        <el-table-column label="完成率" min-width="180">
          <template #default="{ row }">
            <div class="assignee-progress">
              <el-progress
                :percentage="Number(row.completion_rate) || 0"
                :stroke-width="10"
                :text-inside="true"
                :color="progressColor(row.completion_rate)"
                style="flex: 1"
              />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { User, Check, Search } from '@element-plus/icons-vue'
import { getWorkpapersKanban } from '@/services/commonApi'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

const props = defineProps<{
  projectId: string
  auditCycle?: string
}>()

defineEmits<{
  'select': [item: any]
  'assign': [item: any]
}>()

// 委派/分配需项目经理及以上权限（与后端 batch-assign require review + delegator 对齐）
const { currentRole, projectRole } = usePermissionMatrix(props.projectId)
const canAssign = computed(() =>
  ['admin', 'partner', 'manager'].includes(currentRole.value) ||
  ['manager', 'partner'].includes(projectRole.value || '')
)

const loading = ref(false)
const focusColumn = ref('') // 点击 KPI 卡片聚焦对应列
// 筛选状态（仅"按状态"视图生效）
const cycleFilter = ref('')
const keyword = ref('')
const assigneeFilter = ref<{ id: string | null; name: string } | null>(null)
const PAGE_SIZE = 60
const visibleCount = ref<Record<string, number>>({
  not_started: PAGE_SIZE, in_progress: PAGE_SIZE, under_review: PAGE_SIZE, completed: PAGE_SIZE,
})
const viewMode = ref<'status' | 'assignee'>('status')
const viewOptions = [
  { label: '按状态', value: 'status' },
  { label: '按人', value: 'assignee' },
]
function onViewChange(v: any) { viewMode.value = v as 'status' | 'assignee' }

const kanbanData = ref<Record<string, any[]>>({
  not_started: [],
  in_progress: [],
  under_review: [],
  completed: [],
})
const stats = ref<any>({ total: 0, completion_rate: 0 })
const assigneeRows = ref<any[]>([])

const columns = [
  { key: 'not_started', label: '待编制', badgeType: 'info' as const },
  { key: 'in_progress', label: '编制中', badgeType: 'warning' as const },
  { key: 'under_review', label: '待复核', badgeType: '' as const },
  { key: 'completed', label: '已通过', badgeType: 'success' as const },
]

const columnColors: Record<string, string> = {
  not_started: '#909399', in_progress: '#e6a23c', under_review: '#4b2d77', completed: '#67c23a',
}
// KPI 卡片计数 = 后端全量（项目级真值，不随筛选变；筛选只影响下方列展示）
const columnCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const col of columns) {
    counts[col.key] = kanbanData.value[col.key]?.length || 0
  }
  return counts
})

// 循环下拉选项：所有列出现过的 audit_cycle 去重（自然排序）
const cycleOptions = computed(() => {
  const set = new Set<string>()
  for (const col of columns) {
    for (const it of kanbanData.value[col.key] || []) {
      if (it.audit_cycle) set.add(it.audit_cycle)
    }
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
})

const isFiltered = computed(() => !!(cycleFilter.value || keyword.value.trim() || assigneeFilter.value))

// 筛选后的看板数据（循环 + 关键词 + 按人）——仅影响下方列
const filteredKanbanData = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const af = assigneeFilter.value
  const out: Record<string, any[]> = {}
  for (const col of columns) {
    let arr = kanbanData.value[col.key] || []
    if (cycleFilter.value) arr = arr.filter((it) => it.audit_cycle === cycleFilter.value)
    if (kw) arr = arr.filter((it) =>
      (it.wp_code || '').toLowerCase().includes(kw) || (it.wp_name || '').toLowerCase().includes(kw))
    if (af) arr = arr.filter((it) => (it.assigned_to || null) === af.id)
    out[col.key] = arr
  }
  return out
})

const filteredTotal = computed(() =>
  columns.reduce((s, col) => s + (filteredKanbanData.value[col.key]?.length || 0), 0))

// 增量渲染：每列先渲染 PAGE_SIZE 张，其余按需加载
function visibleItems(key: string) {
  return (filteredKanbanData.value[key] || []).slice(0, visibleCount.value[key] || PAGE_SIZE)
}
function remaining(key: string) {
  return Math.max((filteredKanbanData.value[key]?.length || 0) - (visibleCount.value[key] || PAGE_SIZE), 0)
}
function hasMore(key: string) { return remaining(key) > 0 }
function loadMore(key: string) {
  visibleCount.value = { ...visibleCount.value, [key]: (visibleCount.value[key] || PAGE_SIZE) + PAGE_SIZE }
}

// 筛选变化时重置各列渲染上限，避免上次滚动残留
watch([cycleFilter, keyword, assigneeFilter], () => {
  visibleCount.value = {
    not_started: PAGE_SIZE, in_progress: PAGE_SIZE, under_review: PAGE_SIZE, completed: PAGE_SIZE,
  }
})

// 按人视图点击行 → 切回按状态并只看该人底稿（未分配行 id=null）
function onAssigneeRowClick(row: any) {
  assigneeFilter.value = { id: row.user_id || null, name: row.name || '未分配' }
  viewMode.value = 'status'
  focusColumn.value = ''
}

// 相对时间（更新于）——无外部依赖，纯本地格式化
function fmtRelTime(iso: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min}分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day}天前`
  return new Date(iso).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function progressColor(rate: number) {
  const r = Number(rate) || 0
  if (r >= 80) return '#67c23a'
  if (r >= 40) return '#e6a23c'
  return '#909399'
}

async function loadKanban() {
  loading.value = true
  try {
    const result = await getWorkpapersKanban(props.projectId, props.auditCycle)
    kanbanData.value = result.kanban || {}
    stats.value = result.stats || { total: 0, completion_rate: 0 }
    assigneeRows.value = result.by_assignee || []
  } catch {
    kanbanData.value = { not_started: [], in_progress: [], under_review: [], completed: [] }
    assigneeRows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadKanban)

defineExpose({ refresh: loadKanban })
</script>

<style scoped>
.wp-kanban { height: 100%; display: flex; flex-direction: column; background: var(--gt-color-bg, #f8f6fc); }

/* 统计栏 — KPI 卡片 */
.kanban-stats {
  display: flex; gap: 12px; padding: 14px 16px; flex-wrap: wrap;
}
.kanban-stat-card {
  flex: 1; min-width: 80px; padding: 12px 16px; text-align: center;
  background: var(--gt-color-bg-white); border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s;
}
.kanban-stat-card:hover { border-color: var(--gt-color-primary); }
.kanban-stat-card.is-active { border-color: var(--gt-color-primary); box-shadow: 0 0 0 2px rgba(103, 80, 164, 0.15); }
.kanban-stat-card--highlight {
  background: linear-gradient(135deg, #6750A4 0%, #8b5cf6 100%);
  border: none; box-shadow: 0 4px 12px rgba(103, 80, 164, 0.25);
}
.kanban-stat-card--highlight .kanban-stat-card__num { color: #fff; }
.kanban-stat-card--highlight .kanban-stat-card__label { color: rgba(255,255,255,0.85); }
.kanban-stat-card__num { display: block; font-size: 22px; font-weight: 800; color: var(--gt-color-text-primary); line-height: 1.2; }
.kanban-stat-card__label { font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }

/* 工具栏 — 视图切换 */
.kanban-toolbar {
  display: flex; align-items: center; gap: 12px; padding: 0 16px 10px;
}
.kanban-toolbar__hint { font-size: 12px; color: var(--gt-color-text-tertiary); }
.kanban-toolbar__cycle { width: 140px; }
.kanban-toolbar__search { width: 190px; }

/* 看板列 */
.kanban-columns {
  flex: 1; display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; padding: 0 16px 16px; overflow: auto;
}

.kanban-column {
  background: var(--gt-color-bg-white); border-radius: 12px; display: flex; flex-direction: column;
  min-height: 200px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  transition: all 0.2s ease;
}
.kanban-column.is-focused { box-shadow: 0 4px 16px rgba(103, 80, 164, 0.12); transform: scale(1.01); }
.kanban-column.is-dimmed { opacity: 0.4; transform: scale(0.98); }

.column-header {
  padding: 12px 14px; display: flex; align-items: center; justify-content: space-between;
  border-top: 4px solid var(--gt-color-info); border-radius: 12px 12px 0 0;
  background: var(--gt-color-bg, #fafafa);
}
.column-title { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-text); }
.column-count {
  font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
  background: var(--gt-color-bg-white); color: var(--gt-color-text-secondary);
  border: 1px solid var(--gt-color-border-light, #e8e8e8);
}
.column-body { flex: 1; padding: 10px; overflow-y: auto; }

/* 空态 */
.column-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 30px 0; gap: 8px;
}
.column-empty__icon { font-size: 28px; opacity: 0.5; }
.column-empty__text { font-size: 12px; color: var(--gt-color-text-placeholder); }

/* 卡片 */
.kanban-card {
  background: var(--gt-color-bg-white); border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;
  border: 1px solid var(--gt-color-border-light, #f0f0f0); cursor: pointer;
  transition: all 0.2s ease;
}
.kanban-card:hover {
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.1);
  border-color: var(--gt-color-primary); transform: translateY(-1px);
}
.kanban-card.is-stale { border-left: 3px solid var(--gt-color-warning, #e6a23c); }

.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; gap: 6px; }
.card-header__right { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
.card-stale-tag { transform: scale(0.85); transform-origin: right center; }
.card-code { font-weight: 700; font-size: var(--wp-font-size, 13px); color: var(--gt-color-primary); }
.card-cycle-badge {
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  background: var(--gt-color-primary-bg, #f0e6ff); color: var(--gt-color-primary);
}
.card-time { font-size: 10px; color: var(--gt-color-text-placeholder); margin-left: auto; white-space: nowrap; }
.column-loadmore { width: 100%; margin-top: 2px; color: var(--gt-color-primary); }
.card-name { font-size: var(--wp-font-size, 13px); color: var(--gt-color-text); line-height: 1.4; }
.card-progress { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.card-progress__text { font-size: 10px; color: var(--gt-color-text-tertiary); white-space: nowrap; }
.card-footer { display: flex; align-items: center; gap: 12px; margin-top: 8px; font-size: 12px; color: var(--gt-color-text-tertiary); flex-wrap: wrap; }
.card-role { display: inline-flex; align-items: center; gap: 4px; }
.card-role--reviewer { color: var(--gt-color-primary); }
.card-actions { justify-content: flex-end; }
.card-assignee { color: var(--gt-color-text-secondary); font-weight: 500; }
.card-unassigned { color: var(--gt-color-text-placeholder); font-style: italic; }

/* 按人视图 */
.kanban-assignee { flex: 1; padding: 0 16px 16px; overflow: auto; }
.assignee-cell { display: flex; align-items: center; gap: 8px; }
.assignee-avatar {
  width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  background: var(--gt-color-primary, #4b2d77); color: #fff; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.assignee-avatar.is-unassigned { background: var(--gt-color-text-placeholder, #c0c4cc); }
.assignee-name { font-size: var(--wp-font-size, 13px); font-weight: 500; color: var(--gt-color-text); }
.assignee-name.is-unassigned { color: var(--gt-color-text-tertiary); font-style: italic; }
.assignee-progress { display: flex; align-items: center; }
:deep(.kanban-assignee .el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.kanban-assignee__table .el-table__row) { cursor: pointer; }
</style>
