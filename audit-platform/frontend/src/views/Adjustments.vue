<template>
  <div class="gt-adjustments gt-fade-in">
    <div class="gt-adj-header">
      <h2 class="gt-page-title">调整分录</h2>
      <el-button type="primary" @click="openCreateDialog">新建分录</el-button>
    </div>

    <!-- 汇总面板 -->
    <div class="gt-summary-panel" v-if="summary">
      <div class="gt-summary-card">
        <span class="gt-summary-label">AJE</span>
        <span class="gt-summary-value">{{ summary.aje_count }} 笔</span>
        <span class="gt-summary-sub">借 {{ fmtAmt(summary.aje_total_debit) }} / 贷 {{ fmtAmt(summary.aje_total_credit) }}</span>
      </div>
      <div class="gt-summary-card">
        <span class="gt-summary-label">RJE</span>
        <span class="gt-summary-value">{{ summary.rje_count }} 笔</span>
        <span class="gt-summary-sub">借 {{ fmtAmt(summary.rje_total_debit) }} / 贷 {{ fmtAmt(summary.rje_total_credit) }}</span>
      </div>
      <div class="gt-summary-card" v-for="(cnt, st) in summary.status_counts" :key="st">
        <span class="gt-summary-label">{{ statusLabel(st) }}</span>
        <span class="gt-summary-value">{{ cnt }}</span>
      </div>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="AJE" name="aje" />
      <el-tab-pane label="RJE" name="rje" />
    </el-tabs>

    <!-- 分录列表 -->
    <el-table :data="entries" v-loading="loading" border stripe style="width: 100%"
      @selection-change="onSelectionChange">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="adjustment_no" label="编号" width="120" />
      <el-table-column prop="adjustment_type" label="类型" width="70">
        <template #default="{ row }">
          <el-tag :type="normalizeAdjustmentType(row.adjustment_type) === 'aje' ? 'danger' : 'warning'" size="small">
            {{ formatAdjustmentType(row.adjustment_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column label="借方合计" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.total_debit) }}</template>
      </el-table-column>
      <el-table-column label="贷方合计" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.total_credit) }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="日期" width="110">
        <template #default="{ row }">{{ row.created_at?.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column prop="review_status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.review_status)" size="small">
            {{ statusLabel(row.review_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)"
            :disabled="row.review_status === 'approved' || row.review_status === 'pending_review'">
            编辑
          </el-button>
          <el-button size="small" type="danger" @click="onDelete(row)"
            :disabled="row.review_status === 'approved' || row.review_status === 'pending_review'">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 批量复核操作 -->
    <div class="gt-adj-batch-actions" v-if="selectedRows.length > 0">
      <span>已选 {{ selectedRows.length }} 条</span>
      <el-button type="success" size="small" @click="batchReview('approved')">批量批准</el-button>
      <el-button type="warning" size="small" @click="showRejectDialog = true">批量驳回</el-button>
    </div>

    <!-- 驳回原因弹窗 -->
    <el-dialog append-to-body v-model="showRejectDialog" title="驳回原因" width="400px">
      <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请输入驳回原因" />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="primary" @click="batchReview('rejected')" :disabled="!rejectReason">确认驳回</el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑分录弹窗 -->
    <el-dialog append-to-body v-model="formDialogVisible" :title="isEditing ? '编辑分录' : '新建分录'" width="800px" destroy-on-close>
      <el-form :model="form" label-width="90px">
        <el-form-item label="类型" v-if="!isEditing">
          <el-radio-group v-model="form.adjustment_type">
            <el-radio value="aje">AJE</el-radio>
            <el-radio value="rje">RJE</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.description" placeholder="调整说明" />
        </el-form-item>

        <!-- 动态行项 -->
        <div class="gt-adj-line-items-header">
          <span>行项明细</span>
          <el-button size="small" @click="addLine">+ 添加行</el-button>
        </div>
        <el-table :data="form.line_items" border size="small" style="margin-bottom: 12px">
          <el-table-column label="科目" min-width="200">
            <template #default="{ row, $index }">
              <el-select v-model="row.standard_account_code" filterable placeholder="选择科目"
                style="width: 100%" @change="onAccountSelect($index)">
                <el-option v-for="opt in accountOptions" :key="opt.code"
                  :label="`${opt.code} ${opt.name}`" :value="opt.code" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="借方" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false"
                style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="贷方" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false"
                style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column width="60">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="removeLine($index)"
                :disabled="form.line_items.length <= 1">✕</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 借贷差额 -->
        <div class="gt-adj-balance-diff" :class="{ 'gt-adj-unbalanced': balanceDiff !== 0 }">
          借方合计: {{ totalDebit.toFixed(2) }} | 贷方合计: {{ totalCredit.toFixed(2) }}
          | 差额: {{ balanceDiff.toFixed(2) }}
        </div>
      </el-form>
      <template #footer>
        <el-button @click="formDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit" :disabled="balanceDiff !== 0" :loading="submitLoading">
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listAdjustments, createAdjustment, updateAdjustment, deleteAdjustment,
  reviewAdjustment, getAdjustmentSummary, getAccountDropdown,
  type AdjustmentSummary, type AccountOption,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const submitLoading = ref(false)
const activeTab = ref('all')
const entries = ref<any[]>([])
const summary = ref<AdjustmentSummary | null>(null)
const selectedRows = ref<any[]>([])
const showRejectDialog = ref(false)
const rejectReason = ref('')
const accountOptions = ref<AccountOption[]>([])

// Form state
const formDialogVisible = ref(false)
const isEditing = ref(false)
const editingGroupId = ref('')
const form = ref({
  adjustment_type: 'aje',
  description: '',
  line_items: [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }],
})

const totalDebit = computed(() => form.value.line_items.reduce((s, l) => s + (l.debit_amount || 0), 0))
const totalCredit = computed(() => form.value.line_items.reduce((s, l) => s + (l.credit_amount || 0), 0))
const balanceDiff = computed(() => Math.round((totalDebit.value - totalCredit.value) * 100) / 100)

function fmtAmt(v: string | number | null | undefined): string {
  const n = typeof v === 'string' ? parseFloat(v) || 0 : (v ?? 0)
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(s: string) {
  const m: Record<string, string> = { draft: 'info', pending_review: 'warning', approved: 'success', rejected: 'danger' }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = { draft: '草稿', pending_review: '待复核', approved: '已批准', rejected: '已驳回' }
  return m[s] || s
}

function normalizeAdjustmentType(type: string) {
  return String(type || '').toLowerCase()
}

function formatAdjustmentType(type: string) {
  return normalizeAdjustmentType(type).toUpperCase()
}

async function fetchEntries() {
  loading.value = true
  try {
    const opts: any = { page_size: 200 }
    if (activeTab.value !== 'all') opts.adjustment_type = activeTab.value
    const result = await listAdjustments(projectId.value, year.value, opts)
    entries.value = Array.isArray(result) ? result : (result.items || [])
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  try {
    summary.value = await getAdjustmentSummary(projectId.value, year.value)
  } catch { /* ignore */ }
}

async function fetchAccountOptions() {
  try {
    accountOptions.value = await getAccountDropdown(projectId.value)
  } catch { /* ignore */ }
}

function onTabChange() { fetchEntries() }
function onSelectionChange(rows: any[]) { selectedRows.value = rows }

function addLine() {
  form.value.line_items.push({ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 })
}

function removeLine(idx: number) {
  form.value.line_items.splice(idx, 1)
}

function onAccountSelect(idx: number) {
  const code = form.value.line_items[idx].standard_account_code
  const opt = accountOptions.value.find(o => o.code === code)
  if (opt) form.value.line_items[idx].account_name = opt.name
}

function openCreateDialog() {
  isEditing.value = false
  editingGroupId.value = ''
  form.value = {
    adjustment_type: 'aje',
    description: '',
    line_items: [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }],
  }
  formDialogVisible.value = true
}

function openEditDialog(row: any) {
  isEditing.value = true
  editingGroupId.value = row.entry_group_id
  form.value = {
    adjustment_type: normalizeAdjustmentType(row.adjustment_type),
    description: row.description || '',
    line_items: (row.line_items || []).map((li: any) => ({
      standard_account_code: li.standard_account_code,
      account_name: li.account_name || '',
      debit_amount: parseFloat(li.debit_amount) || 0,
      credit_amount: parseFloat(li.credit_amount) || 0,
    })),
  }
  if (!form.value.line_items.length) {
    form.value.line_items = [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }]
  }
  formDialogVisible.value = true
}

async function onSubmit() {
  submitLoading.value = true
  try {
    if (isEditing.value) {
      await updateAdjustment(projectId.value, editingGroupId.value, {
        description: form.value.description,
        line_items: form.value.line_items,
      })
      ElMessage.success('保存成功')
    } else {
      await createAdjustment(projectId.value, {
        adjustment_type: form.value.adjustment_type,
        year: year.value,
        description: form.value.description,
        line_items: form.value.line_items,
      })
      ElMessage.success('创建成功')
    }
    formDialogVisible.value = false
    fetchEntries()
    fetchSummary()
  } finally {
    submitLoading.value = false
  }
}

async function onDelete(row: any) {
  await ElMessageBox.confirm('确定删除该分录？', '确认')
  await deleteAdjustment(projectId.value, row.entry_group_id)
  ElMessage.success('删除成功')
  fetchEntries()
  fetchSummary()
}

async function batchReview(status: string) {
  const rows = selectedRows.value.filter(r =>
    status === 'approved' ? r.review_status === 'pending_review' :
    status === 'rejected' ? r.review_status === 'pending_review' : true
  )
  if (!rows.length) {
    ElMessage.warning('没有可操作的分录')
    return
  }
  for (const row of rows) {
    await reviewAdjustment(projectId.value, row.entry_group_id, {
      status,
      reason: status === 'rejected' ? rejectReason.value : undefined,
    })
  }
  ElMessage.success(`已${status === 'approved' ? '批准' : '驳回'} ${rows.length} 条`)
  showRejectDialog.value = false
  rejectReason.value = ''
  selectedRows.value = []
  fetchEntries()
  fetchSummary()
}

onMounted(() => {
  fetchEntries()
  fetchSummary()
  fetchAccountOptions()
})
</script>

<style scoped>
.gt-adjustments { padding: var(--gt-space-4); }
.gt-adj-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-summary-panel { display: flex; gap: var(--gt-space-3); margin-bottom: var(--gt-space-4); flex-wrap: wrap; }
.gt-summary-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-sm); padding: var(--gt-space-3) var(--gt-space-4);
  box-shadow: var(--gt-shadow-sm); min-width: 120px; text-align: center;
}
.gt-summary-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-summary-value { display: block; font-size: var(--gt-font-size-xl); font-weight: 600; color: var(--gt-color-primary); }
.gt-summary-sub { display: block; font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-adj-batch-actions { display: flex; align-items: center; gap: var(--gt-space-2); margin-top: var(--gt-space-3); }
.gt-adj-line-items-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-2); font-weight: 600; }
.gt-adj-balance-diff { text-align: right; font-size: var(--gt-font-size-sm); color: var(--gt-color-success); }
.gt-adj-balance-diff.gt-adj-unbalanced { color: var(--gt-color-coral); font-weight: 600; }
</style>
