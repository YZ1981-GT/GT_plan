<template>
  <div class="gt-pbc-panel">
    <div class="panel-header">
      <h3>PBC清单管理</h3>
      <el-button size="small" @click="fetchItems">刷新</el-button>
    </div>

    <!-- Summary -->
    <div class="pbc-summary">
      <el-tag type="success" size="small">已完成 {{ completedCount }} 项</el-tag>
      <el-tag type="warning" size="small">进行中 {{ pendingCount }} 项</el-tag>
      <el-tag type="danger" size="small">已逾期 {{ overdueCount }} 项</el-tag>
    </div>

    <!-- PBC Table -->
    <el-table :data="items" stripe size="small" v-loading="loading">
      <el-table-column prop="item_name" label="PBC名称" min-width="200" />
      <el-table-column prop="category" label="类别" width="140" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="getStatusTagType(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="due_date" label="截止日期" width="120" />
      <el-table-column prop="received_date" label="收到日期" width="120">
        <template #default="{ row }">
          <span v-if="row.received_date">{{ row.received_date }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openUpdateDialog(row)">
            更新状态
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Update Status Dialog -->
    <el-dialog append-to-body v-model="updateDialogVisible" title="更新PBC状态" width="420px">
      <el-form ref="updateFormRef" :model="updateForm" label-width="100px">
        <el-form-item label="PBC名称">
          <span class="form-text">{{ currentItem?.item_name }}</span>
        </el-form-item>
        <el-form-item label="当前状态">
          <el-tag :type="getStatusTagType(currentItem?.status)" size="small">
            {{ getStatusLabel(currentItem?.status) }}
          </el-tag>
        </el-form-item>
        <el-form-item label="新状态" prop="status">
          <el-select v-model="updateForm.status" placeholder="请选择新状态" style="width: 100%">
            <el-option label="已收到 (RECEIVED)" value="RECEIVED" />
            <el-option label="进行中 (IN_PROGRESS)" value="IN_PROGRESS" />
            <el-option label="待处理 (PENDING)" value="PENDING" />
            <el-option label="已逾期 (OVERDUE)" value="OVERDUE" />
            <el-option label="已完成 (COMPLETED)" value="COMPLETED" />
          </el-select>
        </el-form-item>
        <el-form-item label="收到日期" prop="received_date">
          <el-date-picker
            v-model="updateForm.received_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期（可选）"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="updateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleUpdateStatus">确认更新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { pbcApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'

const loading = ref(false)
const updating = ref(false)
const items = ref<any[]>([])
const updateDialogVisible = ref(false)
const currentItem = ref<any>(null)
const updateFormRef = ref<FormInstance>()

const updateForm = reactive({
  status: '',
  received_date: '',
})

// Mock PBC data
const mockItems = [
  { id: 'i1', item_name: '银行询证函', category: '银行', status: 'COMPLETED', due_date: '2025-01-31', received_date: '2025-01-28' },
  { id: 'i2', item_name: '应收账款函证', category: '往来', status: 'IN_PROGRESS', due_date: '2025-02-28', received_date: '' },
  { id: 'i3', item_name: '销售合同清单', category: '销售', status: 'PENDING', due_date: '2025-02-15', received_date: '' },
  { id: 'i4', item_name: '固定资产盘点表', category: '资产', status: 'OVERDUE', due_date: '2025-01-20', received_date: '' },
  { id: 'i5', item_name: '关联方交易明细', category: '关联', status: 'RECEIVED', due_date: '2025-02-28', received_date: '2025-02-10' },
  { id: 'i6', item_name: '会计报表及附注', category: '报表', status: 'PENDING', due_date: '2025-03-31', received_date: '' },
]

const completedCount = computed(() =>
  items.value.filter(i => i.status === 'COMPLETED' || i.status === 'RECEIVED').length
)
const pendingCount = computed(() =>
  items.value.filter(i => i.status === 'PENDING' || i.status === 'IN_PROGRESS').length
)
const overdueCount = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return items.value.filter(i => {
    const notDone = i.status !== 'COMPLETED' && i.status !== 'RECEIVED'
    return notDone && i.due_date < today
  }).length
})

function getStatusTagType(status: string) {
  const map: Record<string, string> = {
    COMPLETED: 'success',
    RECEIVED: 'success',
    IN_PROGRESS: 'warning',
    PENDING: 'warning',
    OVERDUE: 'danger',
  }
  return (map[status] ?? 'info') as any
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    COMPLETED: '已完成',
    RECEIVED: '已收到',
    IN_PROGRESS: '进行中',
    PENDING: '待处理',
    OVERDUE: '已逾期',
  }
  return map[status] ?? status
}

async function fetchItems() {
  loading.value = true
  try {
    const { data } = await pbcApi.getItems(projectId)
    items.value = data ?? []
  } catch {
    // Use mock data if API not ready
    items.value = [...mockItems]
  } finally {
    loading.value = false
  }
}

function openUpdateDialog(row: any) {
  currentItem.value = row
  updateForm.status = row.status
  updateForm.received_date = row.received_date ?? ''
  updateDialogVisible.value = true
}

async function handleUpdateStatus() {
  if (!currentItem.value) return

  updating.value = true
  try {
    const payload: any = { status: updateForm.status }
    if (updateForm.received_date) {
      payload.received_date = updateForm.received_date
    }

    await pbcApi.updateStatus(projectId, currentItem.value.id, payload)
    ElMessage.success('状态更新成功')
    currentItem.value.status = updateForm.status
    if (updateForm.received_date) {
      currentItem.value.received_date = updateForm.received_date
    }
    updateDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message ?? '更新失败')
  } finally {
    updating.value = false
  }
}

onMounted(() => {
  fetchItems()
})
</script>

<style scoped>
.gt-pbc-panel {}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.pbc-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.form-text {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}

.text-muted {
  color: var(--gt-color-info);
}
</style>
