<!--
  LogViewerPanel.vue — 日志集中查看 [proposal-remaining-18 / MT-8 / 任务 5.7]

  目标：
  - 在 SystemSettings 新增"日志查看"Tab，仅 admin 可见
  - 表格显示 timestamp / level / module / message
  - 顶部过滤：级别下拉 + 关键字搜索 + 行数选择（100/500/1000/5000）
  - 后端：GET /api/admin/logs?lines=N&level=X&search=Y

  特性：
  - 默认读取 1000 行最新日志（按时间正序）
  - 行数上限 5000（防 OOM，与后端约定一致）
  - 等级 row class 着色：ERROR/CRITICAL 红，WARNING 橙，DEBUG 灰
  - "无日志文件"状态友好提示（启动后未触发任何日志时）
-->
<template>
  <div class="gt-logs">
    <!-- 顶部工具栏 -->
    <div class="gt-logs-toolbar">
      <span class="gt-logs-stats">
        共 <span class="gt-amt">{{ items.length }}</span> 条
        <span v-if="skippedLines > 0" class="gt-logs-skip">
          · 跳过非法行 <span class="gt-amt">{{ skippedLines }}</span>
        </span>
        <span v-if="logFile" class="gt-logs-file" :title="logFile">
          · 文件 <code>{{ logFile }}</code>
        </span>
      </span>
      <div class="gt-logs-spacer" />

      <el-select
        v-model="levelFilter"
        size="small"
        clearable
        placeholder="全部级别"
        class="gt-logs-level"
        @change="loadLogs"
      >
        <el-option label="DEBUG" value="DEBUG" />
        <el-option label="INFO" value="INFO" />
        <el-option label="WARNING" value="WARNING" />
        <el-option label="ERROR" value="ERROR" />
        <el-option label="CRITICAL" value="CRITICAL" />
      </el-select>

      <el-input
        v-model="searchInput"
        size="small"
        placeholder="搜索 message"
        clearable
        class="gt-logs-search"
        @keyup.enter="loadLogs"
        @clear="loadLogs"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="linesLimit"
        size="small"
        class="gt-logs-lines"
        @change="loadLogs"
      >
        <el-option label="100 行" :value="100" />
        <el-option label="500 行" :value="500" />
        <el-option label="1000 行" :value="1000" />
        <el-option label="5000 行" :value="5000" />
      </el-select>

      <el-button
        size="small"
        :loading="loading"
        round
        @click="loadLogs"
      >
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 状态提示 -->
    <el-alert
      v-if="status === 'no_log_file'"
      type="info"
      :closable="false"
      show-icon
      title="日志文件尚未生成"
      :description="`后端启动后写入第一条日志才会创建文件（${logFile || 'logs/app.jsonl'}）。请触发任意 API 调用后再刷新。`"
      style="margin-bottom: 12px"
    />

    <!-- 日志表格 -->
    <div v-loading="loading" class="gt-logs-body">
      <el-table
        :data="items"
        size="small"
        :row-class-name="rowClass"
        :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
        class="gt-logs-table"
        empty-text="无匹配日志"
      >
        <el-table-column label="时间" width="200">
          <template #default="{ row }">
            <span class="gt-logs-ts">{{ formatTimestamp(row.timestamp) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="100">
          <template #default="{ row }">
            <el-tag
              :type="levelTagType(row.level)"
              size="small"
              effect="light"
              :class="`gt-logs-level-${(row.level || '').toLowerCase()}`"
            >
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="220">
          <template #default="{ row }">
            <span class="gt-logs-module">{{ row.module || '—' }}</span>
            <span v-if="row.function && row.function !== '—'" class="gt-logs-fn">
              · {{ row.function }}
              <span v-if="row.line">:{{ row.line }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="消息" min-width="400" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-logs-msg">{{ row.message }}</span>
          </template>
        </el-table-column>
        <el-table-column label="logger" width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="gt-logs-logger">{{ row.logger }}</code>
          </template>
        </el-table-column>
        <el-table-column label="request_id" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <code v-if="row.request_id && row.request_id !== '-'" class="gt-logs-rid">{{ row.request_id }}</code>
            <span v-else class="gt-logs-rid-empty">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { adminLogs as P_logs } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface LogEntry {
  timestamp: string
  level: string
  logger: string
  message: string
  module?: string
  function?: string
  line?: number
  request_id?: string
  exception?: string
}

interface LogsResponse {
  items: LogEntry[]
  total: number
  log_file: string
  log_file_exists: boolean
  skipped_lines: number
  status: 'ok' | 'no_log_file'
}

const loading = ref(false)
const items = ref<LogEntry[]>([])
const status = ref<'ok' | 'no_log_file' | ''>('')
const logFile = ref('')
const skippedLines = ref(0)

const levelFilter = ref<string>('')
const searchInput = ref('')
const linesLimit = ref<number>(1000)

async function loadLogs(): Promise<void> {
  loading.value = true
  try {
    const params: Record<string, string | number> = {
      lines: linesLimit.value,
    }
    if (levelFilter.value) params.level = levelFilter.value
    if (searchInput.value && searchInput.value.trim()) {
      params.search = searchInput.value.trim()
    }

    const res = await api.get<LogsResponse>(P_logs.recent, { params })
    items.value = Array.isArray(res?.items) ? res.items : []
    status.value = res?.status ?? ''
    logFile.value = res?.log_file ?? ''
    skippedLines.value = res?.skipped_lines ?? 0
  } catch (e: any) {
    handleApiError(e, '加载日志')
    items.value = []
  } finally {
    loading.value = false
  }
}

function formatTimestamp(ts: string): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    const pad = (n: number) => String(n).padStart(2, '0')
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms}`
  } catch {
    return ts
  }
}

function levelTagType(level: string): 'info' | 'success' | 'warning' | 'danger' {
  const lv = (level || '').toUpperCase()
  if (lv === 'ERROR' || lv === 'CRITICAL') return 'danger'
  if (lv === 'WARNING') return 'warning'
  if (lv === 'INFO') return 'success'
  return 'info' // DEBUG / 其他
}

function rowClass({ row }: { row: LogEntry }): string {
  const lv = (row.level || '').toUpperCase()
  if (lv === 'ERROR' || lv === 'CRITICAL') return 'gt-logs-row-error'
  if (lv === 'WARNING') return 'gt-logs-row-warning'
  return ''
}

// 暴露给测试
defineExpose({ loadLogs, items, status, levelFilter, searchInput, linesLimit })

onMounted(loadLogs)
</script>

<style scoped>
.gt-logs {
  padding: 12px 0;
}
.gt-logs-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gt-logs-stats {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
.gt-logs-skip {
  color: var(--gt-color-warning, #e6a23c);
  margin-left: 6px;
}
.gt-logs-file {
  margin-left: 6px;
  color: var(--gt-color-text-tertiary);
}
.gt-logs-file code {
  background: var(--gt-color-border-lighter);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
}
.gt-logs-spacer { flex: 1; }
.gt-logs-level { width: 130px; }
.gt-logs-search { width: 240px; }
.gt-logs-lines { width: 110px; }

.gt-logs-body { background: var(--gt-color-bg-white); border-radius: 4px; }
.gt-logs-table {
  font-size: var(--gt-font-size-sm);
}
.gt-logs-ts {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--gt-color-text-secondary);
}
.gt-logs-module {
  font-weight: 500;
  color: var(--gt-color-text-primary);
}
.gt-logs-fn {
  margin-left: 4px;
  color: var(--gt-color-text-tertiary);
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: var(--gt-font-size-xs);
}
.gt-logs-msg {
  word-break: break-all;
  white-space: pre-wrap;
}
.gt-logs-logger {
  font-size: var(--gt-font-size-xs);
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--gt-color-text-tertiary);
}
.gt-logs-rid {
  font-size: var(--gt-font-size-xs);
  font-family: 'Consolas', 'Monaco', monospace;
  background: var(--gt-color-border-lighter);
  padding: 1px 4px;
  border-radius: 3px;
}
.gt-logs-rid-empty {
  color: var(--gt-color-text-placeholder);
}

:deep(.gt-logs-row-error) {
  background-color: rgba(245, 108, 108, 0.06);
}
:deep(.gt-logs-row-warning) {
  background-color: rgba(230, 162, 60, 0.06);
}
</style>
