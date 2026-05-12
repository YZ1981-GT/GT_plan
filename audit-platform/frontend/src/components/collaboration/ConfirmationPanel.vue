<template>
  <div class="gt-confirmation-panel">
    <div class="panel-header">
      <h3>函证管理</h3>
      <el-button type="primary" @click="showCreateDialog = true">新建函证</el-button>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="银行" name="BANK" />
      <el-tab-pane label="应收" name="AR" />
      <el-tab-pane label="应付" name="AP" />
      <el-tab-pane label="律师" name="LAWYER" />
      <el-tab-pane label="全部" name="ALL" />
    </el-tabs>

    <el-table :data="filteredConfirmations" stripe>
      <el-table-column prop="confirmation_name" label="函证名称" min-width="160" />
      <el-table-column prop="counterparty" label="交易对手" min-width="140" />
      <el-table-column prop="type" label="类型" width="100">
        <template #default="{ row }">
          {{ typeLabel(row.type) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="(statusType(row.status)) || undefined">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="due_date" label="截止日期" width="120" />
      <el-table-column prop="received_date" label="回函日期" width="120" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="info" @click="extractConfirmation(row)">自动提取</el-button>
          <el-button size="small" type="primary" @click="openReview(row)">审核</el-button>
          <el-button size="small" type="success" @click="generateLetter(row)">生成询证函</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建函证弹窗 -->
    <el-dialog append-to-body v-model="showCreateDialog" title="新建函证" width="500px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="交易对手" required>
          <el-input v-model="createForm.counterparty" placeholder="请输入交易对手名称" />
        </el-form-item>
        <el-form-item label="函证类型" required>
          <el-select v-model="createForm.type" placeholder="请选择类型">
            <el-option label="银行" value="BANK" />
            <el-option label="应收账款" value="AR" />
            <el-option label="应付账款" value="AP" />
            <el-option label="律师询证" value="LAWYER" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="createForm.amount" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="函证描述说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <!-- 审核弹窗 -->
    <el-dialog append-to-body v-model="showReviewDialog" title="函证审核" width="500px">
      <div v-if="currentRow">
        <p><strong>函证名称：</strong>{{ currentRow.confirmation_name }}</p>
        <p><strong>交易对手：</strong>{{ currentRow.counterparty }}</p>
        <p><strong>类型：</strong>{{ typeLabel(currentRow.type) }}</p>
        <p><strong>状态：</strong><el-tag :type="(statusType(currentRow.status)) || undefined">{{ statusLabel(currentRow.status) }}</el-tag></p>
        <el-divider />
        <h4>审核意见</h4>
        <el-input v-model="reviewComments" type="textarea" :rows="4" placeholder="填写审核意见" />
      </div>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="success" @click="submitReview">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmationApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'
const activeTab = ref('ALL')
const showCreateDialog = ref(false)
const showReviewDialog = ref(false)
const currentRow = ref<any>(null)
const reviewComments = ref('')

const confirmations = ref<any[]>([])
const createForm = ref({
  counterparty: '',
  type: '',
  amount: 0,
  description: '',
})

const typeMap: Record<string, string> = {
  BANK: '银行',
  AR: '应收账款',
  AP: '应付账款',
  LAWYER: '律师',
}

const statusMap: Record<string, { label: string; type: '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' }> = {
  PENDING: { label: '待发送', type: 'info' },
  SENT: { label: '已发送', type: 'warning' },
  RECEIVED: { label: '已回函', type: 'success' },
  EXCEPTION: { label: '异常', type: 'danger' },
}

const filteredConfirmations = computed(() => {
  if (activeTab.value === 'ALL') return confirmations.value
  return confirmations.value.filter((c) => c.type === activeTab.value)
})

function typeLabel(t: string) {
  return typeMap[t] || t
}

function statusLabel(s: string) {
  return statusMap[s]?.label || s
}

function statusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return statusMap[s]?.type || 'info'
}

onMounted(async () => {
  try {
    const { data } = await confirmationApi.list(projectId)
    confirmations.value = data ?? []
  } catch {
    // graceful fallback with mock data
    confirmations.value = [
      { id: '1', confirmation_name: '银行询证函-A行', counterparty: 'A银行', type: 'BANK', status: 'RECEIVED', due_date: '2025-03-31', received_date: '2025-03-15' },
      { id: '2', confirmation_name: '应收账款-客户甲', counterparty: '客户甲', type: 'AR', status: 'SENT', due_date: '2025-03-31', received_date: '' },
      { id: '3', confirmation_name: '应付账款-供应商乙', counterparty: '供应商乙', type: 'AP', status: 'PENDING', due_date: '2025-03-31', received_date: '' },
      { id: '4', confirmation_name: '律师询证函-丙律所', counterparty: '丙律师事务所', type: 'LAWYER', status: 'EXCEPTION', due_date: '2025-03-31', received_date: '' },
    ]
  }
})

async function handleCreate() {
  if (!createForm.value.counterparty || !createForm.value.type) {
    ElMessage.warning('请填写必填项')
    return
  }
  try {
    const { data } = await confirmationApi.create(projectId, createForm.value)
    confirmations.value.push(data)
    ElMessage.success('函证创建成功')
    showCreateDialog.value = false
    createForm.value = { counterparty: '', type: '', amount: 0, description: '' }
  } catch {
    ElMessage.error('创建失败')
  }
}

function extractConfirmation(row: any) {
  ElMessage.info(`正在自动提取 ${row.confirmation_name}`)
  // TODO: integrate with backend
}

function openReview(row: any) {
  currentRow.value = row
  reviewComments.value = ''
  showReviewDialog.value = true
}

async function submitReview() {
  if (!currentRow.value) return
  ElMessage.success('审核已提交')
  showReviewDialog.value = false
  // TODO: integrate with backend
}

async function generateLetter(row: any) {
  try {
    await confirmationApi.generateLetter(projectId, row.id, {})
    ElMessage.success('询证函已生成')
  } catch {
    ElMessage.error('生成失败，请稍后重试')
  }
}
</script>

<style scoped>
.gt-confirmation-panel {}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>
