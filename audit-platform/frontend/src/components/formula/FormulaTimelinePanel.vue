<!--
  公式版本时间轴面板（spec: formula-management-deep-optimization · R6）。
  竖向时间轴 + 按类型着色图标 + 点击展开详情。
  嵌入 FormulaManagerDialog 的历史 Tab 或独立 Tab。
-->
<template>
  <div v-loading="loading" class="gt-ftl-panel">
    <div class="gt-ftl-header">
      <span class="gt-ftl-title">📜 公式版本时间轴</span>
      <el-button size="small" @click="load">刷新</el-button>
      <span class="gt-ftl-muted">{{ events.length }} 条事件</span>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <!-- 类型过滤 -->
    <div v-if="events.length" class="gt-ftl-filters">
      <el-checkbox-group v-model="activeTypes" size="small">
        <el-checkbox-button v-for="(meta, type) in eventTypes" :key="type" :value="type">
          {{ meta.icon }} {{ meta.label }}
        </el-checkbox-button>
      </el-checkbox-group>
    </div>

    <!-- 时间轴 -->
    <div v-if="filteredEvents.length" class="gt-ftl-timeline">
      <div v-for="(evt, i) in filteredEvents" :key="i" class="gt-ftl-item" @click="toggleDetail(i)">
        <div class="gt-ftl-dot" :style="{ background: dotColor(evt.type) }">
          {{ eventTypes[evt.type]?.icon || '●' }}
        </div>
        <div class="gt-ftl-content">
          <div class="gt-ftl-time">{{ fmtTime(evt.timestamp) }}</div>
          <div class="gt-ftl-summary">{{ evt.summary }}</div>
          <div v-if="evt.user_id" class="gt-ftl-user">操作人: {{ evt.user_id }}</div>
          <!-- 展开详情 -->
          <div v-if="expandedIdx === i && evt.detail" class="gt-ftl-detail">
            <pre class="gt-ftl-json">{{ JSON.stringify(evt.detail, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else-if="!loading" description="暂无公式变更事件" :image-size="48" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { formulaTimeline } from '@/services/apiPaths/formula'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'

const props = defineProps<{
  projectId: string
  year: number
}>()

const events = ref<any[]>([])
const eventTypes = ref<Record<string, any>>({})
const loading = ref(false)
const error = ref('')
const expandedIdx = ref<number | null>(null)
const activeTypes = ref<string[]>([
  'formula_changed', 'global_publish', 'template_update', 'push_run', 'conflict_resolved',
])

async function load() {
  if (!props.projectId || !props.year) return
  loading.value = true
  error.value = ''
  try {
    // 错误由本面板自己显示：请求带 _silent；原先 handleApiError(e, { silent: true }) 把对象当操作名、返回 void ⇒
    // 弹「[object Object]：…」且面板只剩「加载失败」（spec formula-fetch-followup 7.2）
    const data = await api.get(formulaTimeline.list(props.projectId, props.year), { _silent: true } as any)
    events.value = data.events || []
    eventTypes.value = data.event_types || {}
  } catch (e: any) {
    error.value = formulaErrorText(e, '加载失败')
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.year], load, { immediate: true })

const filteredEvents = computed(() =>
  events.value.filter(e => activeTypes.value.includes(e.type))
)

function toggleDetail(idx: number) {
  expandedIdx.value = expandedIdx.value === idx ? null : idx
}

function fmtTime(ts: string | null) {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch { return ts }
}

const TYPE_COLORS: Record<string, string> = {
  formula_changed: '#e6a23c',
  global_publish: '#409eff',
  template_update: '#9b59b6',
  push_run: '#67c23a',
  conflict_resolved: '#f56c6c',
}
function dotColor(type: string) { return TYPE_COLORS[type] || '#909399' }
</script>

<style scoped>
.gt-ftl-panel { padding: 8px 0; }
.gt-ftl-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gt-ftl-title { font-weight: 600; font-size: var(--gt-font-size-sm); }
.gt-ftl-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ftl-filters { margin-bottom: 8px; }
.gt-ftl-timeline { position: relative; padding-left: 28px; max-height: 500px; overflow-y: auto; }
.gt-ftl-timeline::before { content: ''; position: absolute; left: 13px; top: 0; bottom: 0; width: 2px; background: var(--gt-color-border-light); }
.gt-ftl-item { position: relative; padding: 6px 0 12px; cursor: pointer; }
.gt-ftl-item:hover .gt-ftl-content { background: var(--gt-bg-overlay); }
.gt-ftl-dot { position: absolute; left: -24px; top: 6px; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; z-index: 1; }
.gt-ftl-content { padding: 4px 8px; border-radius: 4px; transition: background 0.15s; }
.gt-ftl-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); }
.gt-ftl-summary { font-size: var(--gt-font-size-sm); margin: 2px 0; }
.gt-ftl-user { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ftl-detail { margin-top: 4px; padding: 6px; background: var(--gt-bg-info); border-radius: 4px; }
.gt-ftl-json { font-size: 11px; margin: 0; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
</style>
