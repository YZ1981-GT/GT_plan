<template>
  <div class="event-dlq-page">
    <GtPageHeader title="事件死信队列" :show-back="false">
      <template #actions>
        <el-button type="primary" size="small" :loading="loading" @click="fetchDLQ">
          刷新
        </el-button>
      </template>
    </GtPageHeader>
    <p class="page-desc">显示广播失败超过重试次数的事件，可手动重投。</p>

    <el-table
      v-loading="loading"
      :data="dlqEntries"
      stripe
      border
      size="small"
      style="width: 100%"
      empty-text="暂无死信事件"
    >
      <el-table-column prop="id" label="ID" width="80">
        <template #default="{ row }">
          <span class="mono-text">{{ (row.id || '').slice(0, 8) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="event_type" label="事件类型" width="220" />
      <el-table-column prop="project_id" label="项目 ID" width="160">
        <template #default="{ row }">
          <span class="mono-text">{{ (row.project_id || '').slice(0, 8) }}...</span>
        </template>
      </el-table-column>
      <el-table-column prop="failure_reason" label="失败原因" min-width="250">
        <template #default="{ row }">
          <el-tooltip :content="row.failure_reason" placement="top" :show-after="300">
            <span class="truncate-text">{{ row.failure_reason || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="attempt_count" label="重试次数" width="90" align="center" />
      <el-table-column prop="moved_to_dlq_at" label="进入 DLQ 时间" width="170">
        <template #default="{ row }">
          {{ formatDate(row.moved_to_dlq_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="resolved_at" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.resolved_at" type="success" size="small">已处理</el-tag>
          <el-tag v-else type="danger" size="small">待处理</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.resolved_at"
            link
            type="primary"
            size="small"
            :loading="reinjectingId === row.id"
            @click="onReinject(row)"
          >
            重投
          </el-button>
          <span v-else class="resolved-label">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { admin } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

// ─── Types ──────────────────────────────────────────────────────────────────

interface DLQEntry {
  id: string
  event_type: string
  project_id: string
  failure_reason: string | null
  attempt_count: number
  moved_to_dlq_at: string
  resolved_at: string | null
  payload?: Record<string, any>
}

// ─── State ──────────────────────────────────────────────────────────────────

const dlqEntries = ref<DLQEntry[]>([])
const loading = ref(false)
const reinjectingId = ref<string | null>(null)

// ─── Fetch ──────────────────────────────────────────────────────────────────

async function fetchDLQ() {
  loading.value = true
  try {
    const res = await api.get<DLQEntry[] | { items: DLQEntry[] }>(admin.importEventHealth)
    if (Array.isArray(res)) {
      dlqEntries.value = res
    } else if (res && Array.isArray((res as any).items)) {
      dlqEntries.value = (res as any).items
    } else {
      dlqEntries.value = []
    }
  } catch (e) {
    console.error('获取 DLQ 数据失败', e)
    dlqEntries.value = []
  } finally {
    loading.value = false
  }
}

// ─── Reinject ───────────────────────────────────────────────────────────────

async function onReinject(entry: DLQEntry) {
  reinjectingId.value = entry.id
  try {
    await api.post(admin.importEventReplay, { event_id: entry.id })
    ElMessage.success('事件已重投')
    // Refresh list
    await fetchDLQ()
  } catch (e: any) {
    handleApiError(e, '重投事件')
  } finally {
    reinjectingId.value = null
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  fetchDLQ()
})
</script>

<style scoped>
.event-dlq-page {
  padding: 20px 24px;
  max-width: 1400px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
}

.page-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  flex: 1;
}

.mono-text {
  font-family: monospace;
  font-size: 12px;
}

.truncate-text {
  display: inline-block;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resolved-label {
  color: var(--el-text-color-placeholder);
}
</style>
