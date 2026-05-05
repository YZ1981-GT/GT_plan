<template>
  <div class="gt-adjustments gt-fade-in">
    <!-- 页面横幅 -->
    <GtPageHeader title="调整分录" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :badges="[{ value: `AJE ${summary?.aje_count || 0} 笔 · RJE ${summary?.rje_count || 0} 笔` }]"
        @unit-change="onProjectChange"
        @year-change="onYearChange"
      />
      <template #actions>
        <GtToolbar
          :show-export="true"
          :show-import="true"
          export-label="导出汇总"
          @export="onExportSummary"
          @import="showImportDialog = true"
        >
          <template #left>
            <el-button size="small" type="primary" @click="openCreateDialog">+ 新建分录</el-button>
            <div class="gt-adj-batch-toggle">
              <el-switch v-model="batchMode" size="small" active-text="批量模式" inactive-text="" />
              <el-badge v-if="batchPendingCount > 0" :value="batchPendingCount" :max="99" class="gt-adj-batch-badge">
                <el-button size="small" type="success" :loading="batchCommitting" @click="onBatchCommit">
                  📦 批量提交
                </el-button>
              </el-badge>
            </div>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

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
        <span class="gt-summary-label">{{ dictStore.label('adjustment_status', st as string) }}</span>
        <span class="gt-summary-value">{{ cnt }}</span>
      </div>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="AJE" name="aje" />
      <el-tab-pane label="RJE" name="rje" />
    </el-tabs>

    <!-- 科目过滤提示（从试算表跳转时显示） -->
    <el-alert
      v-if="filterAccount"
      type="info"
      show-icon
      :closable="true"
      style="margin-bottom: 12px"
      @close="filterAccount = ''; fetchEntries()"
    >
      <template #title>
        <span>当前仅显示科目 <strong>{{ filterAccount }}</strong> 的相关分录</span>
        <el-button size="small" text type="primary" style="margin-left: 8px" @click="filterAccount = ''; fetchEntries()">查看全部</el-button>
      </template>
    </el-alert>

    <!-- 分录列表 -->
    <el-alert
      v-if="!loading && entries.length === 0"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>暂无{{ activeTab === 'aje' ? '审计' : '重分类' }}调整分录</template>
      <div style="font-size: 12px; line-height: 1.6; margin-top: 4px">
        点击上方"新增"按钮创建调整分录。调整分录将自动更新试算表审定数和报表数据。
      </div>
    </el-alert>
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
          <el-tag size="small" :type="dictStore.type('adjustment_status', row.review_status)">{{ dictStore.label('adjustment_status', row.review_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)"
            :disabled="row.review_status === 'approved' || row.review_status === 'pending_review'">
            编辑
          </el-button>
          <el-button size="small" type="danger" @click="onDelete(row)"
            v-permission="'adjustment:delete'"
            :disabled="row.review_status === 'approved' || row.review_status === 'pending_review'">
            删除
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="转错报" width="110" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.review_status === 'rejected' && normalizeAdjustmentType(row.adjustment_type) === 'aje'"
            size="small"
            type="warning"
            :loading="convertingGroupId === row.entry_group_id"
            @click="onConvertToMisstatement(row)"
          >
            转错报
          </el-button>
          <span v-else class="gt-adj-col-placeholder">—</span>
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
    <el-dialog append-to-body v-model="showRejectDialog" title="驳回原因" width="520px" @open="onRejectDialogOpen">
      <!-- 模式切换 -->
      <div style="margin-bottom: 16px">
        <el-radio-group v-model="rejectMode" size="small">
          <el-radio-button value="unified">统一原因</el-radio-button>
          <el-radio-button value="individual">逐条原因</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 统一原因模式 -->
      <template v-if="rejectMode === 'unified'">
        <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请输入统一驳回原因" />
      </template>

      <!-- 逐条原因模式 -->
      <template v-else>
        <div style="font-size: 12px; color: #909399; margin-bottom: 8px">
          为每条分录填写独立驳回原因（留空时使用统一原因）
        </div>
        <el-input
          v-model="rejectReason"
          type="textarea"
          :rows="2"
          placeholder="统一原因（逐条留空时使用）"
          style="margin-bottom: 12px"
        />
        <div
          v-for="row in selectedRows"
          :key="row.entry_group_id"
          style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px"
        >
          <span style="min-width: 120px; font-size: 13px; color: #303133; flex-shrink: 0">
            {{ row.adjustment_no || row.entry_group_id?.slice(0, 8) }}
          </span>
          <el-input
            v-model="individualReasons[row.entry_group_id]"
            size="small"
            placeholder="此条驳回原因（可留空）"
            style="flex: 1"
          />
        </div>
      </template>

      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="primary" @click="batchReview('rejected')" :disabled="!rejectReason && rejectMode === 'unified'">确认驳回</el-button>
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
                  :label="`${opt.code} ${opt.name}`" :value="opt.code">
                  <span>{{ opt.code }} {{ opt.name }}</span>
                  <span v-if="opt.report_line" style="float:right;color:#999;font-size:11px;margin-left:8px">
                    → {{ opt.report_line }}
                  </span>
                </el-option>
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

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showImportDialog"
      import-type="adjustments"
      :project-id="projectId"
      :year="year"
      @imported="onImported"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmDelete } from '@/utils/confirm'
import {
  listAdjustments, createAdjustment, updateAdjustment, deleteAdjustment,
  reviewAdjustment, getAdjustmentSummary, getAccountDropdown, getProjectAuditYear,
  batchCommitAdjustments,
  convertAjeToMisstatement,
  type AdjustmentSummary, type AccountOption,
} from '@/services/auditPlatformApi'
import { useProjectStore } from '@/stores/project'
import { useDictStore } from '@/stores/dict'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { fmtAmount } from '@/utils/formatters'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import { ADJUSTMENT_STATUS, getStatusLabel } from '@/utils/statusMaps'
import { operationHistory } from '@/utils/operationHistory'
import { useAutoSave } from '@/composables/useAutoSave'

const route = useRoute()
const router = useRouter()
const dictStore = useDictStore()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const yearOptions = computed(() => projectStore.yearOptions)
const selectedYear = ref(projectStore.year)

function onProjectChange(pid: string) {
  router.push({ path: `/projects/${pid}/adjustments`, query: route.query })
}
function onYearChange(y: number) {
  selectedYear.value = y
  projectStore.changeYear(y)
  router.push({ path: route.path, query: { year: String(y) } })
}

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const showImportDialog = ref(false)
const submitLoading = ref(false)
const activeTab = ref('all')
const entries = ref<any[]>([])
const summary = ref<AdjustmentSummary | null>(null)
const selectedRows = ref<any[]>([])
const showRejectDialog = ref(false)
const rejectReason = ref('')
const rejectMode = ref<'unified' | 'individual'>('unified')
const individualReasons = ref<Record<string, string>>({})
const accountOptions = ref<AccountOption[]>([])

// 科目过滤（来自 route.query.account，支持从试算表跳转过来）
const filterAccount = ref(typeof route.query.account === 'string' ? route.query.account : '')

// Batch mode state
const batchMode = ref(false)
const batchPendingCount = ref(0)
const batchCommitting = ref(false)
// R1 需求 3 — AJE 一键转错报：正在转换的 entry_group_id（避免重复点击）
const convertingGroupId = ref<string>('')
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

const fmtAmt = fmtAmount

// ── 自动保存/草稿恢复 [R3.8] ──
const { clearDraft: clearAutoSaveDraft } = useAutoSave(
  `adjustment_form_${projectId.value}`,
  () => {
    if (!formDialogVisible.value) return null
    return {
      adjustment_type: form.value.adjustment_type,
      description: form.value.description,
      line_items: form.value.line_items,
      isEditing: isEditing.value,
      editingGroupId: editingGroupId.value,
    }
  },
  (data) => {
    if (!data) return
    form.value.adjustment_type = data.adjustment_type || 'aje'
    form.value.description = data.description || ''
    form.value.line_items = data.line_items || [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }]
    if (data.isEditing != null) isEditing.value = data.isEditing
    if (data.editingGroupId) editingGroupId.value = data.editingGroupId
    formDialogVisible.value = true
  },
  { enabled: formDialogVisible },
)



function normalizeAdjustmentType(type: string) {
  return String(type || '').toLowerCase()
}

function formatAdjustmentType(type: string) {
  return normalizeAdjustmentType(type).toUpperCase()
}

async function ensureProjectYear() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  try {
    projectYear.value = await getProjectAuditYear(projectId.value)
  } catch {
    projectYear.value = null
  }
}

async function fetchEntries() {
  loading.value = true
  try {
    const opts: any = { page_size: 200 }
    if (activeTab.value !== 'all') opts.adjustment_type = activeTab.value
    const result = await listAdjustments(projectId.value, year.value, opts)
    let items = Array.isArray(result) ? result : (result.items || [])
    // 按科目过滤（来自试算表跳转的 account query 参数）
    if (filterAccount.value) {
      items = items.filter((e: any) =>
        e.line_items?.some((li: any) => li.standard_account_code === filterAccount.value)
      )
    }
    entries.value = items
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
      }, { batch_mode: batchMode.value })
      if (batchMode.value) {
        batchPendingCount.value++
        ElMessage.success(`创建成功（批量模式，待提交 ${batchPendingCount.value} 笔）`)
      } else {
        ElMessage.success('创建成功')
      }
    }
    formDialogVisible.value = false
    clearAutoSaveDraft()
    fetchEntries()
    fetchSummary()
  } finally {
    submitLoading.value = false
  }
}

async function onBatchCommit() {
  batchCommitting.value = true
  try {
    await batchCommitAdjustments(projectId.value, year.value)
    ElMessage.success(`批量提交成功，${batchPendingCount.value} 笔分录已触发重算`)
    batchPendingCount.value = 0
    batchMode.value = false
    fetchEntries()
    fetchSummary()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '批量提交失败')
  } finally {
    batchCommitting.value = false
  }
}

async function onDelete(row: any) {
  await confirmDelete('该分录')
  // 缓存分录数据用于撤销恢复
  const cachedRow = JSON.parse(JSON.stringify(row))
  await operationHistory.execute({
    description: `删除分录 ${row.adjustment_no}`,
    execute: async () => {
      await deleteAdjustment(projectId.value, row.entry_group_id)
      fetchEntries()
      fetchSummary()
    },
    undo: async () => {
      await createAdjustment(projectId.value, {
        adjustment_type: normalizeAdjustmentType(cachedRow.adjustment_type),
        year: year.value,
        description: cachedRow.description || '',
        line_items: (cachedRow.line_items || []).map((li: any) => ({
          standard_account_code: li.standard_account_code,
          account_name: li.account_name || '',
          debit_amount: parseFloat(li.debit_amount) || 0,
          credit_amount: parseFloat(li.credit_amount) || 0,
        })),
      })
      fetchEntries()
      fetchSummary()
    },
  })
}

// R1 需求 3 / Task 10 — 将被驳回的 AJE 一键转为未更正错报
async function onConvertToMisstatement(row: any) {
  if (row.review_status !== 'rejected' || normalizeAdjustmentType(row.adjustment_type) !== 'aje') {
    return
  }
  try {
    await ElMessageBox.confirm(
      `将该分录（${row.adjustment_no || row.entry_group_id?.slice(0, 8)}）转为未更正错报？转换后该条目将出现在《未更正错报汇总表》中。`,
      '确认转错报',
      { confirmButtonText: '确认转换', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  convertingGroupId.value = row.entry_group_id
  try {
    const res = await convertAjeToMisstatement(projectId.value, row.entry_group_id)
    ElMessage.success(`已转为错报（净额 ${res.net_amount}）`)
    try {
      await ElMessageBox.confirm(
        '是否立即查看《未更正错报汇总表》？',
        '转换成功',
        { confirmButtonText: '立即查看', cancelButtonText: '稍后', type: 'success' },
      )
      router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
    } catch {
      /* 用户选择稍后，不跳转 */
    }
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail
    if (status === 409 && detail && typeof detail === 'object' && detail.error_code === 'ALREADY_CONVERTED') {
      try {
        await ElMessageBox.confirm(
          '该分录已转为未更正错报，是否跳转查看？',
          '已转换',
          { confirmButtonText: '跳转查看', cancelButtonText: '关闭', type: 'info' },
        )
        router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
      } catch {
        /* 用户选择关闭 */
      }
    } else {
      const msg = typeof detail === 'string' ? detail : (detail?.message || err?.message || '转换失败')
      ElMessage.error(msg)
    }
  } finally {
    convertingGroupId.value = ''
  }
}

async function batchReview(status: string) {
  const eligible = selectedRows.value.filter(r => r.review_status === 'pending_review')
  const skipped = selectedRows.value.length - eligible.length
  if (skipped > 0) {
    ElMessage.warning(`已跳过 ${skipped} 条非待复核状态的分录`)
  }
  const rows = eligible
  if (!rows.length) {
    ElMessage.warning('没有可操作的分录')
    return
  }
  for (const row of rows) {
    let reason: string | undefined
    if (status === 'rejected') {
      if (rejectMode.value === 'individual') {
        const individual = individualReasons.value[row.entry_group_id]?.trim()
        reason = individual || rejectReason.value || undefined
      } else {
        reason = rejectReason.value || undefined
      }
    }
    await reviewAdjustment(projectId.value, row.entry_group_id, {
      status,
      reason,
    })
  }
  ElMessage.success(`已${status === 'approved' ? '批准' : '驳回'} ${rows.length} 条`)
  showRejectDialog.value = false
  rejectReason.value = ''
  individualReasons.value = {}
  rejectMode.value = 'unified'
  selectedRows.value = []
  fetchEntries()
  fetchSummary()
}

function onRejectDialogOpen() {
  // 初始化逐条原因（每条分录 id 对应空字符串）
  const reasons: Record<string, string> = {}
  for (const row of selectedRows.value) {
    reasons[row.entry_group_id] = ''
  }
  individualReasons.value = reasons
}

function onImported() {
  showImportDialog.value = false
  fetchEntries()
}

function onExportSummary() {
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    downloadFileAsBlob(
      `/api/projects/${projectId.value}/adjustments/export-summary?year=${year.value}&format=excel`,
      `审计调整汇总_${year.value}.xlsx`
    )
  })
}

watch(
  () => [projectId.value, routeYear.value],
  async () => {
    await ensureProjectYear()
    projectStore.syncFromRoute(route)
    selectedYear.value = year.value
    // 同步科目过滤参数
    filterAccount.value = typeof route.query.account === 'string' ? route.query.account : ''
    await fetchEntries()
    await fetchSummary()
    await fetchAccountOptions()
    if (!projectOptions.value.length) projectStore.loadProjectOptions()
  },
  { immediate: true }
)
</script>

<style scoped>
.gt-adjustments { padding: var(--gt-space-5); }

/* 批量模式 */
.gt-adj-batch-toggle {
  display: flex; align-items: center; gap: 10px;
}
.gt-adj-batch-toggle :deep(.el-switch__label) { color: rgba(255,255,255,0.85); font-size: 12px; }
.gt-adj-batch-toggle :deep(.el-switch.is-checked .el-switch__core) { background-color: rgba(255,255,255,0.35); border-color: rgba(255,255,255,0.5); }
.gt-adj-batch-badge :deep(.el-badge__content) { z-index: 2; }
.gt-adj-batch-toggle .el-button--success { background: rgba(103, 194, 58, 0.85); border-color: rgba(103, 194, 58, 0.6); color: #fff; }

/* 汇总面板 */
.gt-summary-panel { display: flex; gap: var(--gt-space-3); margin-bottom: var(--gt-space-5); flex-wrap: wrap; }
.gt-summary-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4) var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm); min-width: 140px; text-align: center;
  border: 1px solid rgba(75, 45, 119, 0.04);
  transition: all var(--gt-transition-base);
  position: relative; overflow: hidden;
}
.gt-summary-card:hover { transform: translateY(-2px); box-shadow: var(--gt-shadow-md); }
.gt-summary-card::after {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--gt-gradient-primary);
  opacity: 0;
  transition: opacity var(--gt-transition-fast);
}
.gt-summary-card:hover::after { opacity: 1; }
.gt-summary-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.gt-summary-value { display: block; font-size: var(--gt-font-size-2xl); font-weight: 800; color: var(--gt-color-primary); margin: 4px 0; letter-spacing: -0.5px; }
.gt-summary-sub { display: block; font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }

/* 批量操作 */
.gt-adj-batch-actions {
  display: flex; align-items: center; gap: var(--gt-space-3);
  margin-top: var(--gt-space-4);
  padding: var(--gt-space-3) var(--gt-space-4);
  background: linear-gradient(135deg, #f8f6fb, #f4f0fa);
  border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.08);
}

/* 行项明细 */
.gt-adj-line-items-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-2); font-weight: 600;
  padding-bottom: var(--gt-space-2);
  border-bottom: 1px solid rgba(75, 45, 119, 0.06);
}

/* 借贷差额 */
.gt-adj-balance-diff {
  text-align: right; font-size: var(--gt-font-size-sm);
  padding: var(--gt-space-2) var(--gt-space-3);
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-success-light);
  color: var(--gt-color-success); font-weight: 600;
  margin-top: var(--gt-space-2);
}
.gt-adj-balance-diff.gt-adj-unbalanced {
  background: var(--gt-color-coral-light);
  color: var(--gt-color-coral);
}

.gt-adj-col-placeholder {
  color: var(--gt-color-text-tertiary, #909399);
}

:deep(.el-tabs__item.is-active) { font-weight: 600; }
</style>
