<template>
  <div class="elimination-list">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" @click="onCreate" plain>
          <el-icon><Plus /></el-icon> 新建分录
        </el-button>
        <el-button
          :disabled="!selectedIds.length"
          @click="onBatchApprove"
          :loading="batchLoading"
        >
          批量审批
        </el-button>
        <el-button
          :disabled="!selectedIds.length"
          type="danger"
          @click="onBatchReject"
          :loading="batchLoading"
        >
          批量驳回
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-date-picker
          v-model="filterYear"
          type="year"
          placeholder="筛选期间"
          value-format="YYYY"
          style="width: 130px"
          @change="onRefresh"
        />
        <el-button :loading="loading" @click="onRefresh" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button @click="onCarryForward" :disabled="!selectedEntries.length" plain>
          <el-icon><DArrowRight /></el-icon> 结转至下一期
        </el-button>
      </div>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange" class="gt-tabs">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="投资类" name="investment" />
      <el-tab-pane label="往来类" name="ar_ap" />
      <el-tab-pane label="交易类" name="transaction" />
      <el-tab-pane label="内部收入类" name="internal_income" />
      <el-tab-pane label="其他" name="other" />
    </el-tabs>

    <!-- 汇总统计 -->
    <div class="summary-bar" v-if="summary">
      <span class="summary-item">
        <span class="summary-label">合计借方：</span>
        <span class="debit">{{ formatNum(summary.total_debit) }}</span>
      </span>
      <span class="summary-item">
        <span class="summary-label">合计贷方：</span>
        <span class="credit">{{ formatNum(summary.total_credit) }}</span>
      </span>
      <span class="summary-item">
        <span class="summary-label">分录数量：</span>
        <span class="count">{{ summary.total_count }}</span>
      </span>
    </div>

    <!-- 列表 -->
    <el-table
      ref="tableRef"
      :data="displayEntries"
      v-loading="loading"
      border
      stripe
      size="small"
      row-key="id"
      @selection-change="onSelectionChange"
      :max-height="tableMaxHeight"
      class="elimination-table"
    >
      <el-table-column type="selection" width="45" />

      <!-- 分录编号 -->
      <el-table-column prop="entry_no" label="分录编号" width="140" fixed />

      <!-- 期间 -->
      <el-table-column prop="year" label="期间" width="90" align="center">
        <template #default="{ row }">{{ row.year }}年</template>
      </el-table-column>

      <!-- 类型 -->
      <el-table-column prop="entry_type" label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="entryTypeTagType(row.entry_type)">
            {{ entryTypeLabel(row.entry_type) }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 关联公司 -->
      <el-table-column label="关联公司" min-width="180">
        <template #default="{ row }">
          <el-tag
            v-for="(name, i) in (row.related_company_names || row.related_company_codes || [])"
            :key="i"
            size="small"
            style="margin-right: 4px; margin-bottom: 2px"
          >
            {{ name }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 借方合计 -->
      <el-table-column label="借方合计" width="140" align="right">
        <template #default="{ row }">
          <span class="debit">{{ formatNum(entryDebit(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 贷方合计 -->
      <el-table-column label="贷方合计" width="140" align="right">
        <template #default="{ row }">
          <span class="credit">{{ formatNum(entryCredit(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 状态 -->
      <el-table-column prop="review_status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.review_status)">
            {{ statusLabel(row.review_status) }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 创建人 -->
      <el-table-column prop="created_by" label="创建人" width="100" align="center">
        <template #default="{ row }">{{ row.created_by || '—' }}</template>
      </el-table-column>

      <!-- 创建日期 -->
      <el-table-column prop="created_at" label="创建日期" width="110" align="center">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="200" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="onEdit(row)">编辑</el-button>
          <el-button
            v-if="row.review_status === 'draft' || row.review_status === 'pending_review'"
            type="success"
            size="small"
            text
            @click="onApprove(row)"
          >
            复核
          </el-button>
          <el-popconfirm
            :title="`确定驳回分录 ${row.entry_no} 吗？`"
            confirm-button-text="确定驳回"
            cancel-button-text="取消"
            @confirm="onReject(row)"
            v-if="row.review_status !== 'rejected'"
          >
            <template #reference>
              <el-button type="danger" size="small" text>驳回</el-button>
            </template>
            <template #default>
              <div class="reject-form">
                <el-input
                  v-model="rejectReason"
                  type="textarea"
                  :rows="3"
                  placeholder="请输入驳回原因"
                />
              </div>
            </template>
          </el-popconfirm>
          <el-button
            type="danger"
            size="small"
            text
            @click="onDelete(row)"
            :loading="deletingId === row.id"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分录编辑弹窗 -->
    <EliminationEntryForm
      v-model:visible="formVisible"
      :entry="currentEntry"
      :project-id="projectId"
      @saved="onSaved"
    />

    <!-- 结转弹窗 -->
    <el-dialog v-model="carryForwardVisible" title="结转至下一期" width="500px" class="gt-dialog">
      <el-form :model="carryForwardForm" label-width="100px">
        <el-form-item label="目标期间">
          <el-date-picker
            v-model="carryForwardForm.targetYear"
            type="year"
            placeholder="选择目标年份"
            value-format="YYYY"
            :clearable="false"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结转说明">
          <el-input
            v-model="carryForwardForm.description"
            type="textarea"
            :rows="3"
            placeholder="说明结转操作"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="carryForwardVisible = false">取消</el-button>
        <el-button type="primary" :loading="carryForwardLoading" @click="onConfirmCarryForward">
          确认结转
        </el-button>
      </template>
    </el-dialog>

    <!-- 驳回原因弹窗 -->
    <el-dialog v-model="rejectVisible" title="驳回原因" width="450px" class="gt-dialog">
      <el-form>
        <el-form-item label="驳回原因">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="4"
            placeholder="请输入驳回原因（必填）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" :loading="rejectLoading" @click="onConfirmReject">
          确认驳回
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, DArrowRight } from '@element-plus/icons-vue'
import EliminationEntryForm from './EliminationEntryForm.vue'
import {
  getEliminationEntries,
  approveEliminationEntry,
  rejectEliminationEntry,
  deleteEliminationEntry,
  carryForwardElimination,
  batchApproveEliminationEntries,
  batchRejectEliminationEntries,
  getEliminationSummary,
  type EliminationEntry,
  type EliminationEntryType,
  type EliminationListFilter,
  type EliminationSummary,
  type ReviewStatus,
} from '@/services/consolidationApi'

// ─── Props ─────────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const loading = ref(false)
const batchLoading = ref(false)
const deletingId = ref<string | null>(null)
const rejectLoading = ref(false)
const carryForwardLoading = ref(false)

const allEntries = ref<EliminationEntry[]>([])
const selectedIds = ref<string[]>([])
const selectedEntries = ref<EliminationEntry[]>([])
const filterYear = ref<string>(String(new Date().getFullYear()))
const activeTab = ref<string>('all')
const summary = ref<EliminationSummary | null>(null)

const tableRef = ref()
const tableMaxHeight = computed(() => Math.max(400, window.innerHeight - 360))

// 表单状态
const formVisible = ref(false)
const currentEntry = ref<EliminationEntry | null>(null)

// 驳回状态
const rejectVisible = ref(false)
const rejectTargetEntry = ref<EliminationEntry | null>(null)
const rejectReason = ref('')

// 结转状态
const carryForwardVisible = ref(false)
const carryForwardForm = ref({
  targetYear: String(new Date().getFullYear() + 1),
  description: '',
})

// ─── Computed ────────────────────────────────────────────────────────────────
const displayEntries = computed(() => {
  let entries = allEntries.value
  if (filterYear.value) {
    entries = entries.filter(e => String(e.year) === filterYear.value)
  }
  if (activeTab.value !== 'all') {
    entries = entries.filter(e => e.entry_type === activeTab.value)
  }
  return entries
})

// ─── Methods ─────────────────────────────────────────────────────────────────
function formatNum(v: number) {
  if (!v && v !== 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(dateStr: string) {
  if (!dateStr) return '—'
  return dateStr.slice(0, 10)
}

function entryTypeLabel(type: string) {
  const map: Record<string, string> = {
    investment: '投资类',
    ar_ap: '往来类',
    transaction: '交易类',
    internal_income: '内部收入类',
    other: '其他',
  }
  return map[type] || type
}

function entryTypeTagType(type: string) {
  const map: Record<string, string> = {
    investment: 'success',
    ar_ap: 'warning',
    transaction: 'primary',
    internal_income: 'info',
    other: '',
  }
  return map[type] || ''
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草稿',
    pending_review: '待复核',
    approved: '已复核',
    rejected: '驳回',
  }
  return map[status] || status
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    draft: 'info',
    pending_review: 'warning',
    approved: 'success',
    rejected: 'danger',
  }
  return map[status] || ''
}

function entryDebit(entry: EliminationEntry) {
  return entry.lines
    .filter(l => (l.debit_amount || 0) > 0)
    .reduce((sum, l) => sum + (l.debit_amount || 0), 0)
}

function entryCredit(entry: EliminationEntry) {
  return entry.lines
    .filter(l => (l.credit_amount || 0) > 0)
    .reduce((sum, l) => sum + (l.credit_amount || 0), 0)
}

async function loadData() {
  loading.value = true
  try {
    const filter: EliminationListFilter = {}
    if (filterYear.value) filter.year = Number(filterYear.value)
    if (activeTab.value !== 'all') filter.entry_type = activeTab.value as EliminationEntryType
    allEntries.value = await getEliminationEntries(props.projectId, filter)

    // 加载汇总
    if (filterYear.value) {
      summary.value = await getEliminationSummary(props.projectId, Number(filterYear.value))
    }
  } catch (e) {
    ElMessage.error('加载抵消分录列表失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onRefresh() {
  loadData()
}

function onTabChange() {
  loadData()
}

function onSelectionChange(selection: EliminationEntry[]) {
  selectedIds.value = selection.map(e => e.id)
  selectedEntries.value = selection
}

function onCreate() {
  currentEntry.value = null
  formVisible.value = true
}

function onEdit(entry: EliminationEntry) {
  currentEntry.value = entry
  formVisible.value = true
}

async function onApprove(entry: EliminationEntry) {
  try {
    await ElMessageBox.confirm(
      `确定复核分录 ${entry.entry_no} 吗？`,
      '复核确认',
      { confirmButtonText: '确定复核', cancelButtonText: '取消', type: 'info' }
    )
    await approveEliminationEntry(entry.id, props.projectId)
    ElMessage.success('复核成功')
    onRefresh()
  } catch (e) {
    // 用户取消
  }
}

function onReject(entry: EliminationEntry) {
  rejectTargetEntry.value = entry
  rejectReason.value = ''
  rejectVisible.value = true
}

async function onConfirmReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写驳回原因')
    return
  }
  if (!rejectTargetEntry.value) return
  rejectLoading.value = true
  try {
    await rejectEliminationEntry(rejectTargetEntry.value.id, props.projectId, rejectReason.value)
    ElMessage.success('驳回成功')
    rejectVisible.value = false
    onRefresh()
  } catch (e) {
    ElMessage.error('驳回失败')
    console.error(e)
  } finally {
    rejectLoading.value = false
  }
}

async function onDelete(entry: EliminationEntry) {
  try {
    await ElMessageBox.confirm(
      `确定删除分录 ${entry.entry_no} 吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
    deletingId.value = entry.id
    await deleteEliminationEntry(entry.id, props.projectId)
    ElMessage.success('删除成功')
    onRefresh()
  } catch (e) {
    // 用户取消
  } finally {
    deletingId.value = null
  }
}

async function onBatchApprove() {
  if (!selectedIds.value.length) return
  batchLoading.value = true
  try {
    const result = await batchApproveEliminationEntries(selectedIds.value, props.projectId)
    if (result.approved?.length) {
      ElMessage.success(`成功审批 ${result.approved.length} 条`)
    }
    if (result.failed?.length) {
      ElMessage.warning(`${result.failed.length} 条审批失败`)
    }
    tableRef.value?.clearSelection()
    onRefresh()
  } catch (e) {
    ElMessage.error('批量审批失败')
    console.error(e)
  } finally {
    batchLoading.value = false
  }
}

async function onBatchReject() {
  if (!selectedIds.value.length) return
  rejectTargetEntry.value = null
  rejectReason.value = ''
  rejectVisible.value = true
}

function onCarryForward() {
  if (!selectedEntries.value.length) return
  carryForwardForm.value = {
    targetYear: String(new Date().getFullYear() + 1),
    description: '',
  }
  carryForwardVisible.value = true
}

async function onConfirmCarryForward() {
  if (!selectedEntries.value.length) return
  carryForwardLoading.value = true
  try {
    const results: string[] = []
    const errors: string[] = []
    for (const entry of selectedEntries.value) {
      if (entry.review_status !== 'approved') {
        errors.push(`${entry.entry_no} 未复核，无法结转`)
        continue
      }
      try {
        await carryForwardElimination(entry.id, props.projectId, Number(carryForwardForm.value.targetYear))
        results.push(entry.entry_no)
      } catch {
        errors.push(`${entry.entry_no} 结转失败`)
      }
    }
    if (results.length) {
      ElMessage.success(`成功结转 ${results.length} 条：${results.join(', ')}`)
    }
    if (errors.length) {
      ElMessage.warning(`${errors.length} 条失败：${errors.join('; ')}`)
    }
    carryForwardVisible.value = false
    onRefresh()
  } finally {
    carryForwardLoading.value = false
  }
}

function onSaved() {
  onRefresh()
}

onMounted(() => loadData())
</script>

<style scoped>
.elimination-list {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-2);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.summary-bar {
  display: flex;
  align-items: center;
  gap: var(--gt-space-6);
  padding: var(--gt-space-2) var(--gt-space-4);
  background: #f8f7fc;
  border-radius: var(--gt-radius-sm);
  font-size: 13px;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-1);
}

.summary-label {
  font-weight: 600;
  color: #555;
}

.debit { color: var(--gt-color-coral, #FF5149); }
.credit { color: var(--gt-color-teal, #0094B3); }
.count { font-weight: 700; color: var(--gt-color-primary); }

.reject-form {
  padding: var(--gt-space-2);
}

.gt-tabs :deep(.el-tabs__item) {
  font-weight: 500;
}

.gt-dialog :deep(.el-dialog__header) {
  background: var(--gt-color-primary);
  color: #fff;
}

.elimination-table :deep(.el-table__row--striped) {
  background: #fafafa;
}
</style>
