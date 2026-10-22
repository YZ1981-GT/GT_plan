<!--
  推送反向校验面板（spec: formula-management-deep-optimization · R5）。
  嵌入 FormulaPushPanel 的操作区域。
-->
<template>
  <div class="gt-fpv-panel">
    <div class="gt-fpv-header">
      <el-button size="small" :loading="loading" @click="onVerify">🔄 反向校验</el-button>
      <span v-if="data" class="gt-fpv-summary">
        <el-tag type="success" size="small">一致 {{ data.summary.consistent }}</el-tag>
        <el-tag v-if="data.summary.diverged" type="danger" size="small">偏差 {{ data.summary.diverged }}</el-tag>
        <el-tag v-if="data.summary.manual_override" type="warning" size="small">手工改 {{ data.summary.manual_override }}</el-tag>
        <el-tag v-if="data.summary.stale" type="info" size="small">待推送 {{ data.summary.stale }}</el-tag>
        <span class="gt-fpv-muted">共 {{ data.total }} 项</span>
      </span>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-top: 6px;" />

    <el-table v-if="data && data.items.length" :data="filteredItems" size="small" border max-height="340"
      style="margin-top: 8px;" :row-class-name="rowClass">
      <el-table-column prop="addr_id" label="地址" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="源头值" width="120" align="right">
        <template #default="{ row }">
          <span style="font-variant-numeric: tabular-nums;">{{ row.source_value ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已推送值" width="120" align="right">
        <template #default="{ row }">
          <span style="font-variant-numeric: tabular-nums;">{{ row.pushed_value ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="目标当前值" width="120" align="right">
        <template #default="{ row }">
          <span style="font-variant-numeric: tabular-nums;">{{ row.current_value ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="偏差" width="100" align="right">
        <template #default="{ row }">
          <span v-if="row.delta" style="color: var(--gt-color-danger); font-weight: 600;">{{ row.delta }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="data && data.items.length" style="margin-top: 4px; display: flex; gap: 6px;">
      <el-radio-group v-model="filter" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="diverged">仅偏差</el-radio-button>
        <el-radio-button value="manual_override">仅手工</el-radio-button>
        <el-radio-button value="stale">仅待推送</el-radio-button>
      </el-radio-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/services/apiProxy'
import { formulaPushVerify } from '@/services/apiPaths/formula'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{
  projectId: string
  year: number
}>()

const data = ref<any>(null)
const loading = ref(false)
const error = ref('')
const filter = ref('all')

async function onVerify() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.get(formulaPushVerify.verify(props.projectId, props.year))
  } catch (e: any) {
    error.value = handleApiError(e, { silent: true }) || '校验失败'
  } finally {
    loading.value = false
  }
}

const filteredItems = computed(() => {
  if (!data.value?.items) return []
  if (filter.value === 'all') return data.value.items
  return data.value.items.filter((i: any) => i.status === filter.value)
})

function statusType(s: string) {
  return s === 'consistent' ? 'success' : s === 'diverged' ? 'danger' : s === 'manual_override' ? 'warning' : 'info'
}
function statusLabel(s: string) {
  return { consistent: '一致', diverged: '偏差', manual_override: '手工改', stale: '待推送' }[s] || s
}
function rowClass({ row }: { row: any }) {
  return row.status === 'diverged' ? 'gt-fpv-row-danger' : ''
}
</script>

<style scoped>
.gt-fpv-panel { padding: 6px 0; }
.gt-fpv-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-fpv-summary { display: flex; gap: 4px; align-items: center; }
.gt-fpv-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
:deep(.gt-fpv-row-danger) { background: var(--gt-bg-danger-light, #fef0f0) !important; }
</style>
