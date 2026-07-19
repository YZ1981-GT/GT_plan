<template>
  <div class="workhour-entry-list">
    <!-- 工具栏：左=筛选 右=批量提交 -->
    <div class="workhour-entry-list__toolbar">
      <div class="workhour-entry-list__filters">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          size="small"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          :shortcuts="dateShortcuts"
          @change="loadEntries"
        />
        <el-select
          v-model="statusFilter"
          size="small"
          placeholder="状态筛选"
          clearable
          @change="loadEntries"
        >
          <el-option
            v-for="(label, key) in statusLabelMap"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
      </div>
      <div class="workhour-entry-list__actions">
        <el-button
          type="primary"
          size="small"
          :disabled="selectedDraftIds.length === 0"
          @click="handleBatchSubmit"
          :loading="submitting"
        >
          批量提交（{{ selectedDraftIds.length }}）
        </el-button>
      </div>
    </div>

    <!-- 数据表格 -->
    <el-table
      ref="tableRef"
      :data="entries"
      v-loading="loading"
      size="small"
      @selection-change="onSelectionChange"
      row-key="id"
    >
      <el-table-column
        type="selection"
        width="40"
        :selectable="isDraftRow"
      />
      <el-table-column prop="date" label="日期" width="110" sortable />
      <el-table-column prop="cycle" label="循环" width="70" align="center" />
      <el-table-column prop="wp_code" label="底稿" width="110" show-overflow-tooltip />
      <el-table-column prop="procedure" label="程序" min-width="140" show-overflow-tooltip />
      <el-table-column prop="hours" label="小时" width="70" align="right">
        <template #default="{ row }">
          {{ row.hours?.toFixed(1) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabelMap[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="center">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            :disabled="row.status !== 'draft'"
            @click="handleEdit(row)"
          >
            编辑
          </el-button>
          <el-popconfirm
            title="确定删除此条工时记录？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="handleDelete(row)"
          >
            <template #reference>
              <el-button
                link
                type="danger"
                size="small"
                :disabled="row.status !== 'draft'"
              >
                删除
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listEntries,
  deleteEntry,
  batchSubmitEntries,
  type WorkHourEntryRecord,
} from '@/services/staffApi'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'edit', entryId: string): void
}>()

// ── 状态映射 ──
const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  submitted: '已提交',
  approved: '已批准',
  rejected: '已退回',
}

function statusTagType(status: string): '' | 'info' | 'success' | 'warning' | 'danger' {
  switch (status) {
    case 'draft': return 'info'
    case 'submitted': return ''
    case 'approved': return 'success'
    case 'rejected': return 'danger'
    default: return 'info'
  }
}

// ── 日期快捷 ──
const dateShortcuts = [
  { text: '本周', value: () => {
    const now = new Date()
    const day = now.getDay() || 7
    const start = new Date(now)
    start.setDate(now.getDate() - day + 1)
    return [start, now]
  }},
  { text: '本月', value: () => {
    const now = new Date()
    return [new Date(now.getFullYear(), now.getMonth(), 1), now]
  }},
  { text: '近30天', value: () => {
    const now = new Date()
    const start = new Date()
    start.setDate(now.getDate() - 30)
    return [start, now]
  }},
]

// ── 数据 ──
const loading = ref(false)
const submitting = ref(false)
const entries = ref<WorkHourEntryRecord[]>([])
const dateRange = ref<[string, string] | null>(null)
const statusFilter = ref<string>('')
const selectedRows = ref<WorkHourEntryRecord[]>([])
const tableRef = ref()

const selectedDraftIds = computed(() =>
  selectedRows.value
    .filter(r => r.status === 'draft')
    .map(r => r.id)
)

// ── 方法 ──
function isDraftRow(row: WorkHourEntryRecord): boolean {
  return row.status === 'draft'
}

function onSelectionChange(rows: WorkHourEntryRecord[]) {
  selectedRows.value = rows
}

async function loadEntries() {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (dateRange.value && dateRange.value[0]) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }
    entries.value = await listEntries(props.projectId, params)
  } catch (e: any) {
    handleApiError(e, '加载工时列表')
  } finally {
    loading.value = false
  }
}

function handleEdit(row: WorkHourEntryRecord) {
  emit('edit', row.id)
}

async function handleDelete(row: WorkHourEntryRecord) {
  try {
    await deleteEntry(props.projectId, row.id)
    ElMessage.success('删除成功')
    await loadEntries()
  } catch (e: any) {
    handleApiError(e, '删除工时条目')
  }
}

async function handleBatchSubmit() {
  if (selectedDraftIds.value.length === 0) return
  submitting.value = true
  try {
    const result = await batchSubmitEntries(props.projectId, selectedDraftIds.value)
    ElMessage.success(`已提交 ${result.submitted_count} 条工时`)
    selectedRows.value = []
    await loadEntries()
  } catch (e: any) {
    handleApiError(e, '批量提交工时')
  } finally {
    submitting.value = false
  }
}

// ── 生命周期 ──
onMounted(loadEntries)

// 暴露刷新方法供父组件调用
defineExpose({ reload: loadEntries })
</script>

<style scoped>
.workhour-entry-list {
  font-size: 13px;
}

.workhour-entry-list__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
}

.workhour-entry-list__filters {
  display: flex;
  align-items: center;
  gap: 10px;
}

.workhour-entry-list__actions {
  flex-shrink: 0;
}

:deep(.el-table) {
  font-size: 13px;
}
</style>
