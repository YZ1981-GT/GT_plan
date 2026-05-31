<template>
  <div class="gt-formula-history">
    <!-- 筛选栏 -->
    <div class="gt-fh-filter-bar">
      <el-input
        v-model="filterRowCode"
        size="small"
        placeholder="按行次筛选..."
        clearable
        style="width: 180px;"
      />
      <el-select v-model="filterAction" size="small" clearable placeholder="操作类型" style="width: 120px;">
        <el-option label="新增" value="create" />
        <el-option label="修改" value="update" />
        <el-option label="删除" value="delete" />
        <el-option label="执行" value="execute" />
      </el-select>
      <el-button size="small" :loading="loading" @click="loadHistory">🔄 刷新</el-button>
      <span class="gt-fh-count">共 {{ filteredEntries.length }} 条记录</span>
    </div>

    <!-- 依赖提示 -->
    <el-alert
      v-if="!specAReady"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
    >
      <template #title>
        <span>公式变更哈希链（spec A 阶段3）尚未完成，当前展示的是 formula_audit_log 懒建表数据。
        待 spec A 完成后将自动切换为哈希链 formula.changed 留痕。</span>
      </template>
    </el-alert>

    <!-- 时间线 -->
    <div v-if="filteredEntries.length" class="gt-fh-timeline">
      <el-timeline>
        <el-timeline-item
          v-for="entry in filteredEntries"
          :key="entry.id"
          :timestamp="formatTime(entry.created_at)"
          :type="actionColor(entry.action)"
          placement="top"
        >
          <div class="gt-fh-entry">
            <div class="gt-fh-entry-header">
              <el-tag :type="actionTagType(entry.action)" size="small">{{ actionLabel(entry.action) }}</el-tag>
              <span class="gt-fh-row-code">{{ entry.row_code }}</span>
              <span class="gt-fh-module">{{ moduleLabel(entry.module) }}</span>
            </div>
            <div v-if="entry.action === 'update' || entry.action === 'create' || entry.action === 'delete'" class="gt-fh-entry-body">
              <div v-if="entry.old_formula" class="gt-fh-formula-diff">
                <span class="gt-fh-label">旧公式：</span>
                <code class="gt-fh-old">{{ entry.old_formula }}</code>
              </div>
              <div v-if="entry.new_formula" class="gt-fh-formula-diff">
                <span class="gt-fh-label">新公式：</span>
                <code class="gt-fh-new">{{ entry.new_formula }}</code>
              </div>
            </div>
            <div v-if="entry.action === 'execute' && entry.result_value != null" class="gt-fh-entry-body">
              <span class="gt-fh-label">计算结果：</span>
              <span class="gt-fh-result">{{ entry.result_value }}</span>
            </div>
            <!-- 一键回滚按钮（仅 update/delete 且有 old_formula 时显示） -->
            <div v-if="canRollback(entry)" class="gt-fh-entry-actions">
              <el-button
                size="small"
                type="warning"
                text
                :loading="rollingBack === entry.id"
                @click="onRollback(entry)"
              >
                ↺ 一键回滚
              </el-button>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>

    <!-- 空状态 -->
    <el-empty v-else-if="!loading" description="暂无公式变更记录" />

    <!-- 加载中 -->
    <div v-if="loading" style="text-align: center; padding: 40px;">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <p style="margin-top: 8px; color: var(--gt-color-text-placeholder);">加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { formulaAuditLog } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface HistoryEntry {
  id: string
  module: string
  row_code: string
  action: string
  old_formula: string | null
  new_formula: string | null
  result_value: number | null
  trace: any[] | null
  created_at: string | null
}

const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  (e: 'rollback-applied', rowCode: string, formula: string): void
}>()

const loading = ref(false)
const entries = ref<HistoryEntry[]>([])
const filterRowCode = ref('')
const filterAction = ref('')
const rollingBack = ref<string | null>(null)

// spec A 阶段3 尚未完成，标记为 false
// 待 spec A 完成后改为动态检测（查 audit_log_entries WHERE action_type='formula.changed'）
const specAReady = ref(false)

const filteredEntries = computed(() => {
  let result = entries.value
  if (filterRowCode.value.trim()) {
    const q = filterRowCode.value.trim().toLowerCase()
    result = result.filter(e => (e.row_code || '').toLowerCase().includes(q))
  }
  if (filterAction.value) {
    result = result.filter(e => e.action === filterAction.value)
  }
  return result
})

async function loadHistory() {
  if (!props.projectId || !props.year) return
  loading.value = true
  try {
    const data = await api.get(formulaAuditLog.list(props.projectId, props.year), {
      params: { limit: 200 },
      validateStatus: (s: number) => s < 600,
    })
    entries.value = Array.isArray(data) ? data : []
  } catch (e) {
    // 表可能不存在（spec A 未完成），静默处理
    entries.value = []
  } finally {
    loading.value = false
  }
}

function canRollback(entry: HistoryEntry): boolean {
  return (entry.action === 'update' || entry.action === 'delete') && !!entry.old_formula
}

async function onRollback(entry: HistoryEntry) {
  if (!entry.old_formula) return
  try {
    await ElMessageBox.confirm(
      `确认将行次 "${entry.row_code}" 的公式回滚为：\n\n${entry.old_formula}\n\n此操作将覆盖当前公式。`,
      '一键回滚确认',
      { confirmButtonText: '确认回滚', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  rollingBack.value = entry.id
  try {
    await api.post(formulaAuditLog.rollback(props.projectId, props.year), {
      row_code: entry.row_code,
      module: entry.module,
      target_formula: entry.old_formula,
      source_log_id: entry.id,
    }, { validateStatus: (s: number) => s < 600 })

    ElMessage.success(`已回滚行次 "${entry.row_code}" 的公式`)
    emit('rollback-applied', entry.row_code, entry.old_formula)
    // 刷新历史
    await loadHistory()
  } catch (e) {
    handleApiError(e, '回滚失败')
  } finally {
    rollingBack.value = null
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ts
  }
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    create: '新增', update: '修改', delete: '删除', execute: '执行',
  }
  return map[action] || action
}

function actionTagType(action: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    create: 'success', update: 'warning', delete: 'danger', execute: 'info',
  }
  return map[action] || ''
}

function actionColor(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' | undefined {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    create: 'success', update: 'warning', delete: 'danger', execute: 'info',
  }
  return map[action] || undefined
}

function moduleLabel(module: string): string {
  const map: Record<string, string> = {
    report: '报表', consol: '合并', note: '附注', wp: '底稿',
  }
  return map[module] || module
}

// 组件挂载时自动加载
onMounted(() => {
  loadHistory()
})

// 监听 projectId/year 变化重新加载
watch(() => [props.projectId, props.year], () => {
  loadHistory()
})
</script>

<style scoped>
.gt-formula-history {
  padding: 8px;
  height: 100%;
  overflow-y: auto;
}
.gt-fh-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.gt-fh-count {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
  margin-left: auto;
}
.gt-fh-timeline {
  max-height: calc(100vh - 400px);
  overflow-y: auto;
  padding: 0 8px;
}
.gt-fh-entry {
  padding: 4px 0;
}
.gt-fh-entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.gt-fh-row-code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-regular);
}
.gt-fh-module {
  font-size: 11px;
  color: var(--gt-color-text-placeholder);
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
}
.gt-fh-entry-body {
  margin-top: 4px;
  padding-left: 4px;
}
.gt-fh-formula-diff {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 2px;
}
.gt-fh-label {
  font-size: 11px;
  color: var(--gt-color-text-secondary);
  white-space: nowrap;
}
.gt-fh-old {
  font-size: 12px;
  color: var(--gt-color-danger);
  text-decoration: line-through;
  word-break: break-all;
}
.gt-fh-new {
  font-size: 12px;
  color: var(--gt-color-success);
  word-break: break-all;
}
.gt-fh-result {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-fh-entry-actions {
  margin-top: 4px;
}
</style>
