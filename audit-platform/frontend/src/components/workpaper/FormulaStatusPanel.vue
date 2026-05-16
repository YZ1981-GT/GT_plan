<script setup lang="ts">
/**
 * 公式状态展示面板（侧面板"公式"Tab）
 * 状态：🟢已填充 / 🟡已过期 / 🔴错误 / ⏳等待上游
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface FormulaItem {
  cell_ref: string
  sheet: string
  formula_type: string
  raw_args: string
  status: 'filled' | 'stale' | 'error' | 'waiting'
  value?: number | string | null
  error?: string
  source_ref?: string
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const formulas = ref<FormulaItem[]>([])
const loading = ref(false)
const filterStatus = ref<string>('all')

const statusIcon: Record<string, string> = {
  filled: '🟢',
  stale: '🟡',
  error: '🔴',
  waiting: '⏳',
}

const statusLabel: Record<string, string> = {
  filled: '已填充',
  stale: '已过期',
  error: '错误',
  waiting: '等待上游',
}

const filteredFormulas = computed(() => {
  if (filterStatus.value === 'all') return formulas.value
  return formulas.value.filter(f => f.status === filterStatus.value)
})

const statusCounts = computed(() => {
  const counts: Record<string, number> = { filled: 0, stale: 0, error: 0, waiting: 0 }
  for (const f of formulas.value) {
    counts[f.status] = (counts[f.status] || 0) + 1
  }
  return counts
})

async function loadFormulas() {
  loading.value = true
  try {
    const data = await api.get(`/api/projects/${props.projectId}/workpapers/${props.wpId}/formulas`)
    formulas.value = data?.formulas || []
  } catch {
    // 端点可能不存在，用空数据
    formulas.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadFormulas)
</script>

<template>
  <div class="formula-status-panel">
    <!-- 状态摘要 -->
    <div class="formula-summary">
      <span
        v-for="(count, status) in statusCounts"
        :key="status"
        class="summary-badge"
        :class="[`status-${status}`]"
        @click="filterStatus = filterStatus === status ? 'all' : (status as string)"
      >
        {{ statusIcon[status as string] }} {{ count }}
      </span>
    </div>

    <!-- 公式列表 -->
    <div v-loading="loading" class="formula-list">
      <div
        v-for="f in filteredFormulas"
        :key="`${f.sheet}!${f.cell_ref}`"
        class="formula-item"
        :class="[`item-${f.status}`]"
      >
        <div class="formula-header">
          <span class="formula-icon">{{ statusIcon[f.status] }}</span>
          <span class="formula-cell">{{ f.sheet }}!{{ f.cell_ref }}</span>
          <el-tag size="small" type="info">{{ f.formula_type }}</el-tag>
        </div>
        <div class="formula-detail">
          <span class="formula-expr">={{ f.formula_type }}({{ f.raw_args }})</span>
        </div>
        <div v-if="f.value != null" class="formula-value">
          = {{ typeof f.value === 'number' ? f.value.toLocaleString() : f.value }}
        </div>
        <div v-if="f.error" class="formula-error">
          {{ f.error }}
        </div>
      </div>

      <el-empty v-if="!loading && filteredFormulas.length === 0" description="暂无公式" />
    </div>
  </div>
</template>

<style scoped>
.formula-status-panel {
  padding: 8px;
}

.formula-summary {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 8px;
}

.summary-badge {
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
  padding: 2px 6px;
  border-radius: 4px;
  transition: background 0.2s;
}

.summary-badge:hover {
  background: var(--el-fill-color-light);
}

.formula-list {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}

.formula-item {
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 4px;
  border-left: 3px solid transparent;
  transition: background 0.15s;
}

.formula-item:hover {
  background: var(--el-fill-color-lighter);
}

.item-filled { border-left-color: #67c23a; }
.item-stale { border-left-color: #e6a23c; }
.item-error { border-left-color: #f56c6c; }
.item-waiting { border-left-color: #909399; }

.formula-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.formula-icon { font-size: var(--gt-font-size-xs); }
.formula-cell { font-weight: 500; font-size: var(--gt-font-size-sm); }

.formula-detail {
  margin-top: 2px;
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  font-family: 'Consolas', monospace;
}

.formula-value {
  margin-top: 2px;
  font-size: var(--gt-font-size-xs);
  color: var(--el-color-primary);
  font-family: 'Arial Narrow', sans-serif;
  font-variant-numeric: tabular-nums;
}

.formula-error {
  margin-top: 2px;
  font-size: var(--gt-font-size-xs);
  color: var(--el-color-danger);
}
</style>
