<!--
  公式变更联动状态（spec formula-management-repair-closure R1.4）：本项目最近公式变更推到报表 / 底稿 / 附注等下游的结果。
  数据源 `GET /api/projects/{pid}/formula-settings/propagation`（公式域耐久事件 + 死信）。
  处理中自动轮询（间隔 3 秒、最多 20 次）；有失败时点开看每条的类别、尝试次数、原因、是否已停止自动重试。
  读取失败如实显示「联动状态未知」，不隐藏、不当作正常。
-->
<template>
  <el-popover v-if="projectId" placement="bottom-end" :width="520" trigger="click" :disabled="!expandable">
    <template #reference>
      <el-tag size="small" effect="plain" :type="view.type" data-testid="fm-propagation-status"
        :class="['gt-fps-tag', { 'gt-fps-tag--clickable': expandable }]" :title="view.title">
        {{ view.label }}
      </el-tag>
    </template>
    <div class="gt-fps-panel" data-testid="fm-propagation-detail">
      <div class="gt-fps-summary">{{ summaryText }}</div>
      <el-table :data="status?.recent_failures || []" size="small" max-height="280" border>
        <el-table-column prop="domain_label" label="类别" width="90" />
        <el-table-column label="尝试" width="96">
          <template #default="{ row }">{{ row.attempt_count }} 次{{ row.gave_up ? '·已停止' : '' }}</template>
        </el-table-column>
        <el-table-column prop="last_error" label="原因" min-width="220" show-overflow-tooltip />
        <el-table-column label="时间" width="96">
          <template #default="{ row }">{{ shortTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="gt-fps-actions">
        <el-button size="small" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formulaSettingsApi } from '@/services/formulaSettingsApi'
import { formulaErrorText, type PropagationStatus } from '@/composables/formula/useFormulaSettings'
import { parseServerTime } from '@/utils/formatters'

defineOptions({ name: 'FormulaPropagationStatus' })

const props = withDefaults(defineProps<{ projectId?: string }>(), { projectId: '' })

/** 处理中时的轮询间隔与上限：后台投递通常几秒内完成，上限防止停在「处理中」时无限请求 */
const POLL_MS = 3000
const POLL_MAX = 20

const status = ref<PropagationStatus | null>(null)
const loadError = ref('')
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
let polls = 0
/** 每次请求的序号：切项目 / 连续刷新时丢弃晚到的旧响应 */
let seq = 0

const expandable = computed(() => !!status.value && status.value.recent_failures.length > 0)

/** 服务端时间（UTC，可能不带时区后缀）→ 本地「MM-DD HH:mm」 */
function shortTime(ts: string | null | undefined): string {
  if (!ts) return '—'
  const d = parseServerTime(ts)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const view = computed<{ label: string; type: 'success' | 'warning' | 'danger' | 'info'; title: string }>(() => {
  if (loadError.value) return { label: '联动状态未知', type: 'info', title: loadError.value }
  const s = status.value
  if (!s) return { label: '联动状态读取中', type: 'info', title: '' }
  if (s.state === 'failed') {
    const tail = s.dead_letter ? `，${s.dead_letter} 条需人工处理` : ''
    return { label: `联动失败 ${s.counts.failed}${tail}`, type: 'danger', title: '点击查看失败原因' }
  }
  if (s.state === 'running') return { label: `联动处理中 ${s.counts.pending}`, type: 'warning', title: '公式变更正在推到下游' }
  return { label: '联动已完成', type: 'success', title: s.last_published_at ? `最近一次完成：${shortTime(s.last_published_at)}` : '' }
})

const summaryText = computed(() => {
  const s = status.value
  if (!s) return ''
  const parts = [`处理中 ${s.counts.pending}`, `失败 ${s.counts.failed}（自动重试中 ${s.retrying}、已停止 ${s.gave_up}）`]
  if (s.dead_letter) parts.push(`死信 ${s.dead_letter}`)
  return `最近 ${s.window} 条公式变更：${parts.join('，')}。已停止自动重试的需检查原因后重新保存公式或联系管理员。`
})

function stopPolling() {
  if (timer) clearTimeout(timer)
  timer = null
}

async function refresh(): Promise<void> {
  const pid = props.projectId
  if (!pid) return
  stopPolling()
  const mine = ++seq
  loading.value = true
  try {
    const data = await formulaSettingsApi.propagation(pid)
    if (mine !== seq) return
    status.value = data
    loadError.value = ''
  } catch (e: any) {
    if (mine !== seq) return
    loadError.value = formulaErrorText(e, '联动状态读取失败')
  } finally {
    if (mine === seq) loading.value = false
  }
  if (mine === seq && status.value?.state === 'running' && polls < POLL_MAX) {
    polls += 1
    timer = setTimeout(() => { void refresh() }, POLL_MS)
  }
}

/** 宿主保存 / 订阅 / 应用后调用：重新开始一轮轮询 */
function restart(): Promise<void> {
  polls = 0
  return refresh()
}

watch(() => props.projectId, () => {
  status.value = null
  loadError.value = ''
  void restart()
}, { immediate: true })

onBeforeUnmount(() => {
  seq += 1
  stopPolling()
})

defineExpose({ refresh: restart, status, loadError })
</script>

<style scoped>
.gt-fps-tag { margin-left: 6px; }
.gt-fps-tag--clickable { cursor: pointer; }
.gt-fps-panel { display: flex; flex-direction: column; gap: 8px; }
.gt-fps-summary { font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.6; }
.gt-fps-actions { display: flex; justify-content: flex-end; }
</style>
