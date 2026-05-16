<template>
  <div class="import-timeline">
    <div class="timeline-header">
      <h3>账套导入历史时间轴</h3>
      <div class="timeline-controls">
        <el-input-number
          v-model="year"
          :min="2000"
          :max="2100"
          :step="1"
          :controls="false"
          size="small"
          style="width: 80px"
        />
        <el-button size="small" :loading="loading" @click="fetchHistory">刷新</el-button>
      </div>
    </div>

    <div v-loading="loading" class="timeline-body">
      <el-timeline v-if="historyItems.length > 0">
        <el-timeline-item
          v-for="item in historyItems"
          :key="item.id"
          :timestamp="formatTime(item.performed_at || item.activated_at)"
          placement="top"
          :type="getTimelineType(item.action || item.status)"
          :hollow="item.action === 'rollback'"
        >
          <el-card shadow="hover" class="timeline-card">
            <div class="card-header">
              <el-tag
                :type="getStatusTagType(item.action || item.status)"
                size="small"
                effect="dark"
              >
                {{ getActionLabel(item.action || item.status) }}
              </el-tag>
              <span class="card-user" v-if="item.performed_by || item.activated_by">
                {{ item.performed_by || item.activated_by }}
              </span>
            </div>

            <div class="card-body">
              <!-- Dataset info -->
              <div v-if="item.dataset_id" class="card-row">
                <span class="card-label">数据集：</span>
                <span class="card-value mono">{{ item.dataset_id.slice(0, 8) }}...</span>
              </div>

              <!-- Row counts -->
              <div v-if="item.after_row_counts || item.record_summary" class="card-row">
                <span class="card-label">数据量：</span>
                <span class="card-value">
                  {{ formatRowCounts(item.after_row_counts || item.record_summary) }}
                </span>
              </div>

              <!-- Duration -->
              <div v-if="item.duration_ms" class="card-row">
                <span class="card-label">耗时：</span>
                <span class="card-value">{{ formatDuration(item.duration_ms) }}</span>
              </div>

              <!-- Reason -->
              <div v-if="item.reason" class="card-row">
                <span class="card-label">原因：</span>
                <span class="card-value">{{ item.reason }}</span>
              </div>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else description="暂无导入历史记录" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { ledger } from '@/services/apiPaths'

const props = defineProps<{
  projectId: string
  initialYear?: number
}>()

const year = ref(props.initialYear || new Date().getFullYear() - 1)
const loading = ref(false)
const historyItems = ref<any[]>([])

async function fetchHistory() {
  if (!props.projectId) return
  loading.value = true
  try {
    const data = await api.get(ledger.import.datasetsHistory(props.projectId), {
      params: { year: year.value },
    })
    historyItems.value = Array.isArray(data) ? data : (data as any)?.items || []
  } catch {
    historyItems.value = []
  } finally {
    loading.value = false
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return '-'
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

function formatRowCounts(counts: Record<string, number> | null): string {
  if (!counts) return '-'
  const parts: string[] = []
  const labels: Record<string, string> = {
    tb_balance: '余额',
    tb_ledger: '序时账',
    tb_aux_balance: '辅助余额',
    tb_aux_ledger: '辅助明细',
  }
  for (const [key, val] of Object.entries(counts)) {
    if (typeof val === 'number' && val > 0) {
      parts.push(`${labels[key] || key}: ${val.toLocaleString()}`)
    }
  }
  return parts.length > 0 ? parts.join(' / ') : '-'
}

function getTimelineType(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (action) {
    case 'activate': return 'success'
    case 'rollback': return 'warning'
    case 'force_unbind': return 'danger'
    case 'active': return 'success'
    case 'staged': return 'info'
    case 'superseded': return 'info'
    default: return 'primary'
  }
}

function getStatusTagType(action: string): 'success' | 'warning' | 'info' | 'danger' {
  switch (action) {
    case 'activate': return 'success'
    case 'active': return 'success'
    case 'rollback': return 'warning'
    case 'force_unbind': return 'danger'
    case 'superseded': return 'info'
    default: return 'info'
  }
}

function getActionLabel(action: string): string {
  switch (action) {
    case 'activate': return '激活'
    case 'rollback': return '回滚'
    case 'force_unbind': return '强制解绑'
    case 'active': return '当前活跃'
    case 'staged': return '暂存'
    case 'superseded': return '已替代'
    case 'rolled_back': return '已回滚'
    default: return action || '未知'
  }
}

watch(year, fetchHistory)
onMounted(fetchHistory)
</script>

<style scoped>
.import-timeline {
  padding: 0;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.timeline-header h3 {
  margin: 0;
  font-size: var(--gt-font-size-md);
  font-weight: 500;
}

.timeline-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-body {
  min-height: 200px;
}

.timeline-card {
  max-width: 400px;
}

.timeline-card :deep(.el-card__body) {
  padding: 12px 16px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.card-user {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: var(--gt-font-size-xs);
}

.card-label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.card-value {
  color: var(--el-text-color-primary);
}

.card-value.mono {
  font-family: monospace;
}
</style>
