<template>
  <div class="gt-approval-table">
    <div class="gt-approval-actions" v-if="selectedIds.length > 0">
      <span class="gt-batch-info">已选 {{ selectedIds.length }} 条</span>
      <el-button type="success" size="small" @click="batchApprove">批量通过</el-button>
      <el-button type="danger" size="small" @click="showRejectDialog = true">批量退回</el-button>
    </div>

    <el-table
      :data="items"
      v-loading="loading"
      border
      stripe
      @selection-change="onSelectionChange"
      :row-class-name="rowClassName"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column prop="user_name" label="填报人" width="100" />
      <el-table-column prop="date" label="日期" width="110" sortable />
      <el-table-column prop="hours" label="小时" width="70" align="right" />
      <el-table-column prop="cycle" label="循环" width="70" align="center" />
      <el-table-column prop="wp_code" label="底稿" width="100" />
      <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      <el-table-column label="底稿进度" width="120" align="center">
        <template #default="{ row }">
          <el-progress
            :percentage="row.wp_progress_pct"
            :stroke-width="6"
            :color="row.wp_progress_pct < 30 ? '#F56C6C' : row.wp_progress_pct < 70 ? '#E6A23C' : '#67C23A'"
          />
        </template>
      </el-table-column>
      <el-table-column label="警告" width="70" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.is_warning" color="#E6A23C" :size="18">
            <span>⚠</span>
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 退回原因弹窗 -->
    <el-dialog v-model="showRejectDialog" title="退回原因" width="400px">
      <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请输入退回原因（可选）" />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="danger" @click="batchReject">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface ApprovalItem {
  entry_id: string
  user_id: string
  user_name: string
  date: string
  hours: number
  cycle: string
  wp_code: string | null
  description: string | null
  wp_progress_pct: number
  is_warning: boolean
  /** 是否加班行（hours > 8 通常视为加班，由后端标记） */
  is_overtime?: boolean
}

const route = useRoute()
const projectId = route.params.id as string

const loading = ref(false)
const items = ref<ApprovalItem[]>([])
const selectedIds = ref<string[]>([])
const showRejectDialog = ref(false)
const rejectReason = ref('')

function onSelectionChange(rows: ApprovalItem[]) {
  selectedIds.value = rows.map(r => r.entry_id)
}

function rowClassName({ row }: { row: ApprovalItem }) {
  const classes: string[] = []
  if (row.is_overtime) classes.push('gt-overtime-row')
  if (row.is_warning) classes.push('gt-warning-row')
  return classes.join(' ')
}

async function loadData() {
  loading.value = true
  try {
    const res = await api.get(`/api/projects/${projectId}/workhours/approval`) as { items: ApprovalItem[] }
    items.value = res.items || []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function batchApprove() {
  if (selectedIds.value.length === 0) return
  try {
    await api.post(`/api/projects/${projectId}/workhours/approval/approve`, {
      entry_ids: selectedIds.value,
    })
    ElMessage.success(`已通过 ${selectedIds.value.length} 条工时`)
    selectedIds.value = []
    await loadData()
  } catch (e: any) {
    handleApiError(e, '审批工时')
  }
}

async function batchReject() {
  if (selectedIds.value.length === 0) return
  try {
    await api.post(`/api/projects/${projectId}/workhours/approval/reject`, {
      entry_ids: selectedIds.value,
      reason: rejectReason.value || null,
    })
    ElMessage.success(`已退回 ${selectedIds.value.length} 条工时`)
    selectedIds.value = []
    rejectReason.value = ''
    showRejectDialog.value = false
    await loadData()
  } catch (e: any) {
    handleApiError(e, '退回工时')
  }
}

onMounted(loadData)
</script>

<style scoped>
.gt-approval-table { padding: 16px; }
.gt-approval-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: var(--gt-bg-success, #f0f9eb);
  border: 1px solid var(--gt-color-border-success, #c2e7b0);
  border-radius: var(--gt-radius-md);
}
.gt-batch-info { font-size: 13px; font-weight: 500; }
:deep(.gt-warning-row) { background-color: #fff7e6 !important; }
:deep(.gt-overtime-row) { background-color: #ffe6e6 !important; }
</style>
