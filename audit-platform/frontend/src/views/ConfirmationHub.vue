<template>
  <div class="gt-confirmation-hub gt-fade-in">
    <GtPageHeader title="函证管理" :show-back="false">
      <template #actions>
        <el-button type="primary" size="small" @click="openCreate()">+ 新建函证</el-button>
      </template>
    </GtPageHeader>

    <!-- 函证清单表格 -->
    <el-table :data="confirmations" border size="small" style="width:100%" v-loading="loading">
      <el-table-column prop="counterparty" label="函证对象" min-width="160" />
      <el-table-column prop="confirm_type" label="类型" width="100">
        <template #default="{ row }">{{ typeLabel(row.confirm_type) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="账面金额" width="140" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.book_amount" /></template>
      </el-table-column>
      <el-table-column label="回函金额" width="140" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.confirmed_amount" /></template>
      </el-table-column>
      <el-table-column label="差异" width="130" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.diff_amount" /></template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="nextStatus(row.status) || row.status === 'returned'" size="small" type="primary" @click="doTransition(row)">
            {{ transitionLabel(row.status) }}
          </el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑弹窗 -->
    <el-dialog
      v-model="showFormDialog"
      :title="editRow ? '编辑函证' : '新建函证'"
      width="500px"
      append-to-body
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="函证类型" prop="confirm_type" required>
          <el-select v-model="form.confirm_type" placeholder="请选择类型">
            <el-option label="应收" value="receivable" />
            <el-option label="应付" value="payable" />
            <el-option label="银行" value="bank" />
            <el-option label="借款" value="loan" />
          </el-select>
        </el-form-item>
        <el-form-item label="函证对象" prop="counterparty" required>
          <el-input v-model="form.counterparty" placeholder="请输入函证对象名称" />
        </el-form-item>
        <el-form-item label="科目编码">
          <el-input v-model="form.account_code" placeholder="关联 TB 科目编码（可选）" />
        </el-form-item>
        <el-form-item label="账面金额">
          <el-input-number v-model="form.book_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="回函金额">
          <el-input-number v-model="form.confirmed_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="差异金额">
          <el-input-number v-model="form.diff_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="差异说明">
          <el-input v-model="form.diff_note" type="textarea" :rows="2" placeholder="差异原因说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFormDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- returned 状态选择弹窗（相符/差异） -->
    <el-dialog v-model="showReturnedChoice" title="回函结果" width="360px" append-to-body>
      <p>请选择回函结果：</p>
      <div class="gt-confirmation-hub__choice">
        <el-button type="success" @click="doReturnedTransition('matched')">相符（无差异）</el-button>
        <el-button type="warning" @click="doReturnedTransition('discrepancy')">差异</el-button>
      </div>
      <template #footer>
        <el-button @click="showReturnedChoice = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirm'
import { eventBus } from '@/utils/eventBus'
import { useProjectStore } from '@/stores/project'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

// ─── 数据 ───

interface ConfirmationItem {
  id: string
  confirm_type: string
  counterparty: string
  status: string
  book_amount: number | null
  confirmed_amount: number | null
  diff_amount: number | null
  diff_note: string | null
  account_code: string | null
  wp_id: string | null
}

const route = useRoute()
const projectStore = useProjectStore()
const projectId = computed(() => projectStore.projectId || (route.params.projectId as string) || '')

const loading = ref(false)
const confirmations = ref<ConfirmationItem[]>([])

// ─── 表单 ───

const showFormDialog = ref(false)
const editRow = ref<ConfirmationItem | null>(null)

const emptyForm = () => ({
  confirm_type: '',
  counterparty: '',
  account_code: '',
  book_amount: null as number | null,
  confirmed_amount: null as number | null,
  diff_amount: null as number | null,
  diff_note: '',
})
const form = ref(emptyForm())

// ─── returned 选择 ───

const showReturnedChoice = ref(false)
const returnedRow = ref<ConfirmationItem | null>(null)

// ─── 枚举映射 ───

const TYPE_LABELS: Record<string, string> = {
  receivable: '应收',
  payable: '应付',
  bank: '银行',
  loan: '借款',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待发函',
  sent: '已发函',
  returned: '已回函',
  matched: '相符',
  discrepancy: '差异',
}

function typeLabel(t: string): string {
  return TYPE_LABELS[t] || t
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

function statusTagType(s: string): 'success' | 'warning' | 'info' | 'danger' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | undefined> = {
    pending: 'info',
    sent: 'warning',
    returned: undefined,
    matched: 'success',
    discrepancy: 'danger',
  }
  return map[s]
}

// ─── 状态推进逻辑 ───

function nextStatus(status: string): string | null {
  const map: Record<string, string | null> = {
    pending: 'sent',
    sent: 'returned',
    returned: null, // 特殊处理：需选相符/差异
    matched: null,
    discrepancy: null,
  }
  return map[status] ?? null
}

function transitionLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '发函',
    sent: '登记回函',
    returned: '确认结果',
  }
  return map[status] || '推进'
}

async function doTransition(row: ConfirmationItem) {
  if (row.status === 'returned') {
    // 已回函 → 需选相符/差异
    returnedRow.value = row
    showReturnedChoice.value = true
    return
  }
  const target = nextStatus(row.status)
  if (!target) return
  await executeTransition(row, target)
}

async function doReturnedTransition(target: 'matched' | 'discrepancy') {
  if (!returnedRow.value) return
  await executeTransition(returnedRow.value, target)
  showReturnedChoice.value = false
  returnedRow.value = null
}

async function executeTransition(row: ConfirmationItem, target: string) {
  try {
    await api.post(`/api/projects/${projectId.value}/confirmations/${row.id}/transition`, {
      target_status: target,
    })
    // 回函登记成功 emit eventBus
    if (target === 'returned') {
      eventBus.emit('confirmation:received', {
        projectId: projectId.value,
        confirmationId: row.id,
        accountCode: row.account_code || undefined,
      })
    }
    ElMessage.success('状态更新成功')
    await fetchList()
  } catch (e) {
    handleApiError(e, '状态推进')
  }
}

// ─── CRUD ───

async function fetchList() {
  loading.value = true
  try {
    const res = await api.get(`/api/projects/${projectId.value}/confirmations`)
    confirmations.value = res.items ?? []
  } catch (e) {
    handleApiError(e, '获取函证列表')
  } finally {
    loading.value = false
  }
}

function openEdit(row: ConfirmationItem) {
  editRow.value = row
  form.value = {
    confirm_type: row.confirm_type,
    counterparty: row.counterparty,
    account_code: row.account_code || '',
    book_amount: row.book_amount,
    confirmed_amount: row.confirmed_amount,
    diff_amount: row.diff_amount,
    diff_note: row.diff_note || '',
  }
  showFormDialog.value = true
}

function openCreate() {
  editRow.value = null
  form.value = emptyForm()
  showFormDialog.value = true
}

async function handleSubmit() {
  if (!form.value.confirm_type || !form.value.counterparty) {
    ElMessage.warning('请填写必填项（类型和函证对象）')
    return
  }
  try {
    if (editRow.value) {
      await api.put(`/api/projects/${projectId.value}/confirmations/${editRow.value.id}`, form.value)
      ElMessage.success('更新成功')
    } else {
      await api.post(`/api/projects/${projectId.value}/confirmations`, form.value)
      ElMessage.success('创建成功')
    }
    showFormDialog.value = false
    await fetchList()
  } catch (e) {
    handleApiError(e, editRow.value ? '更新函证' : '创建函证')
  }
}

async function onDelete(row: ConfirmationItem) {
  try {
    await confirmDelete({ name: `函证「${row.counterparty}」` })
  } catch {
    return // 用户取消
  }
  try {
    await api.delete(`/api/projects/${projectId.value}/confirmations/${row.id}`)
    ElMessage.success('删除成功')
    await fetchList()
  } catch (e) {
    handleApiError(e, '删除函证')
  }
}

// ─── 生命周期 ───

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
.gt-confirmation-hub {
  padding: var(--gt-space-4);
}

.gt-confirmation-hub__choice {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin: 16px 0;
}
</style>
