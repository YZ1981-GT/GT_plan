<template>
  <div class="gt-adjustments gt-fade-in" :class="{ 'gt-fullscreen': isFullscreen }">
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
          <el-button size="small" plain @click="toggleFullscreen">{{ isFullscreen ? '退出全屏' : '全屏' }}</el-button>
          <template #left>
            <el-button size="small" type="primary" v-permission="'adjustment:create'" @click="openCreateDialog">+ 新建分录</el-button>
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

    <!-- 在线成员 [enterprise-linkage 3.2] -->
    <PresenceAvatars :project-id="projectId" view-name="adjustments" />

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
    <GtEditableTable
      ref="adjTableRef"
      :model-value="entries"
      :columns="adjColumns"
      :editable="false"
      :show-selection="true"
      :show-toolbar="true"
      :show-footer="true"
      :show-selection-bar="true"
      v-loading="loading"
      @selection-change="onSelectionChange"
    >
      <!-- 展开行：显示行项明细 -->
      <template #expand="{ row }">
        <div class="gt-adj-expand-detail">
          <table class="gt-adj-line-table">
            <thead>
              <tr><th>科目编码</th><th>科目名称</th><th style="text-align:center">方向</th><th style="text-align:right">金额</th></tr>
            </thead>
            <tbody>
              <tr v-for="(li, idx) in (row.line_items || [])" :key="idx">
                <td>{{ li.standard_account_code }}</td>
                <td>{{ li.account_name }}</td>
                <td style="text-align:center">
                  <span :class="li.debit_amount ? 'gt-adj-dir-dr' : 'gt-adj-dir-cr'">{{ li.debit_amount ? '借' : '贷' }}</span>
                </td>
                <td style="text-align:right" class="gt-amt">{{ fmtAmt(li.debit_amount || li.credit_amount) }}</td>
              </tr>
            </tbody>
          </table>
          <div class="gt-adj-expand-footer">
            <span v-if="row.description" class="gt-adj-expand-desc">📝 {{ row.description }}</span>
            <span class="gt-adj-expand-impact" v-if="row.line_items?.length">
              影响科目：{{ row.line_items.map((li: any) => li.account_name || li.standard_account_code).filter(Boolean).join('、') }}
            </span>
          </div>
        </div>
      </template>
      <template #col-adjustment_type="{ row }">
        <el-tag :type="normalizeAdjustmentType(row.adjustment_type) === 'aje' ? 'danger' : 'warning'" size="small">
          {{ formatAdjustmentType(row.adjustment_type) }}
        </el-tag>
      </template>
      <template #col-total_debit="{ row }">
        <GtAmountCell :value="row.total_debit" :clickable="true" @click="penetrate.toLedger(row.line_items?.[0]?.standard_account_code || '')" />
      </template>
      <template #col-total_credit="{ row }">
        <GtAmountCell :value="row.total_credit" :clickable="true" @click="penetrate.toLedger(row.line_items?.[0]?.standard_account_code || '')" />
      </template>
      <template #col-created_at="{ row }">{{ row.created_at?.slice(0, 10) }}</template>
      <template #col-review_status="{ row }">
        <GtStatusTag dict-key="adjustment_status" :value="row.review_status" />
        <!-- Spec A R1：已转错报但错报阈值变化时显示 stale 标志 -->
        <el-tooltip
          v-if="row.converted_to_misstatement_id && missStaleIdSet.has(row.converted_to_misstatement_id)"
          content="错报阈值已变更，建议重新评估"
          placement="top"
        >
          <span style="margin-left: 4px; cursor: help">🟡</span>
        </el-tooltip>
      </template>
      <template #extra-columns>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)"
              :disabled="row.review_status === ADJUSTMENT_STATUS.APPROVED || row.review_status === ADJUSTMENT_STATUS.PENDING_REVIEW">
              编辑
            </el-button>
            <el-button size="small" type="danger" @click="onDelete(row)"
              v-permission="'adjustment:delete'"
              :disabled="row.review_status === ADJUSTMENT_STATUS.APPROVED || row.review_status === ADJUSTMENT_STATUS.PENDING_REVIEW">
              删除
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="转错报" width="110" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.review_status === ADJUSTMENT_STATUS.REJECTED && normalizeAdjustmentType(row.adjustment_type) === ADJUSTMENT_TYPE.AJE"
              v-permission="'adjustment:convert_to_misstatement'"
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
      </template>
    </GtEditableTable>

    <!-- 批量复核操作 -->
    <div class="gt-adj-batch-actions" v-if="selectedRows.length > 0">
      <span>已选 {{ selectedRows.length }} 条</span>
      <el-button type="success" size="small" @click="batchReview('approved')">批量批准</el-button>
      <el-button type="warning" size="small" @click="showRejectDialog = true">批量驳回</el-button>
    </div>

    <!-- 批量模式浮动提交栏 -->
    <transition name="el-fade-in">
      <div v-if="batchMode && batchPendingCount > 0" class="gt-adj-batch-float-bar">
        <span>📦 批量模式：{{ batchPendingCount }} 笔待提交</span>
        <span style="font-size:11px;color:#909399">提交后将一次性触发试算表重算</span>
        <span style="flex:1" />
        <el-button size="small" @click="batchMode = false; batchPendingCount = 0">取消全部</el-button>
        <el-button size="small" type="success" :loading="batchCommitting" @click="onBatchCommit">
          ✓ 提交全部 ({{ batchPendingCount }})
        </el-button>
      </div>
    </transition>

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
        <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-bottom: 8px">
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
          <span style="min-width: 120px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text); flex-shrink: 0">
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
        <el-form-item label="快捷模板" v-if="!isEditing">
          <el-select v-model="selectedTemplate" placeholder="选择常用模板快速填充" clearable size="small" style="width:100%" @change="onTemplateSelect">
            <el-option-group label="AJE 常用">
              <el-option value="bad_debt" label="坏账准备计提" />
              <el-option value="depreciation" label="固定资产折旧" />
              <el-option value="amortization" label="无形资产摊销" />
              <el-option value="accrued_expense" label="预提费用" />
              <el-option value="revenue_cutoff" label="收入截止调整" />
            </el-option-group>
            <el-option-group label="RJE 常用">
              <el-option value="rcl_current_noncurrent" label="流动/非流动重分类" />
              <el-option value="rcl_ar_prepay" label="应收/预付重分类" />
              <el-option value="rcl_ap_advance" label="应付/预收重分类" />
            </el-option-group>
          </el-select>
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
                  <span v-if="opt.report_line" style="float: right; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); margin-left: 8px">
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

        <!-- 影响预判面板 [enterprise-linkage 3.8] -->
        <ImpactPreviewPanel :preview="impactPreview" :loading="impactLoading" />
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
import { ElMessage } from 'element-plus'
import { confirmDelete, confirmConvert, confirmDangerous } from '@/utils/confirm'
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
import PresenceAvatars from '@/components/PresenceAvatars.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import { operationHistory } from '@/utils/operationHistory'
import { useAutoSave } from '@/composables/useAutoSave'
import { usePasteImport } from '@/composables/usePasteImport'
import { parseApiError } from '@/composables/useApiError'
import { usePenetrate } from '@/composables/usePenetrate'
import { useFullscreen } from '@/composables/useFullscreen'
import { useEditMode } from '@/composables/useEditMode'
// Spec A R1：跨视图 stale 摘要
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
import { handleApiError } from '@/utils/errorHandler'
import * as P from '@/services/apiPaths'
import { ADJUSTMENT_STATUS, ADJUSTMENT_TYPE } from '@/constants/statusEnum'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtEditableTable from '@/components/common/GtEditableTable.vue'
import type { GtColumn } from '@/components/common/GtEditableTable.vue'
import ImpactPreviewPanel from '@/components/ImpactPreviewPanel.vue'
import { useImpactPreview } from '@/composables/useImpactPreview'

const route = useRoute()
const router = useRouter()
const penetrate = usePenetrate()
const { isFullscreen, toggleFullscreen } = useFullscreen()
const { isEditing: isPageEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

/** GtEditableTable 列配置 */
const adjColumns: GtColumn[] = [
  { prop: 'adjustment_no', label: '编号', width: 120 },
  { prop: 'adjustment_type', label: '类型', width: 70 },
  { prop: 'description', label: '摘要', minWidth: 200 },
  { prop: 'total_debit', label: '借方合计', width: 130, align: 'right' },
  { prop: 'total_credit', label: '贷方合计', width: 130, align: 'right' },
  { prop: 'created_at', label: '日期', width: 110 },
  { prop: 'review_status', label: '状态', width: 100 },
]
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

// Spec A R1：跨视图 stale 摘要（错报阈值变化时显示标志）
const projectIdRef = computed(() => projectId.value || '')
const { misstatements: missStaleSummary } = useStaleSummaryFull(projectIdRef, year)
const missStaleIdSet = computed(() => new Set(missStaleSummary.value.items.map((it: any) => it.id)))

const loading = ref(false)
const showImportDialog = ref(false)
const submitLoading = ref(false)
const activeTab = ref('all')
const entries = ref<any[]>([])
const summary = ref<AdjustmentSummary | null>(null)
const selectedRows = ref<any[]>([])

// ─── Impact Preview [enterprise-linkage 3.8] ─────────────────────────────────
const impactProjectId = projectId
const impactYear = computed(() => selectedYear.value ?? 2025)
const { preview: impactPreview, loading: impactLoading, fetchPreview } = useImpactPreview(impactProjectId, impactYear)

// R7-S3-08 Task 41 + R9 F10 Task 33：粘贴多行分录
const adjTableRef = ref<HTMLElement | null>(null)
usePasteImport({
  containerRef: adjTableRef,
  columns: [
    { key: 'standard_account_code', label: '科目编码' },
    { key: 'account_name', label: '科目名称' },
    { key: 'debit_amount', label: '借方' },
    { key: 'credit_amount', label: '贷方' },
    { key: 'summary', label: '摘要' },
  ],
  onInsert: async (rows) => {
    // 粘贴的行作为新分录的 line_items 创建
    const lineItems = rows.map(r => ({
      standard_account_code: r.standard_account_code || '',
      account_name: r.account_name || '',
      debit_amount: parseFloat(r.debit_amount) || 0,
      credit_amount: parseFloat(r.credit_amount) || 0,
    }))
    const summary = rows[0]?.summary || `粘贴导入 ${lineItems.length} 行`
    await createAdjustment(projectId.value, {
      adjustment_type: 'aje',
      year: year.value,
      description: summary,
      line_items: lineItems,
    })
    await fetchEntries()
    await fetchSummary()
  },
})
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
const selectedTemplate = ref('')
const form = ref({
  adjustment_type: 'aje',
  description: '',
  line_items: [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }],
})

// 分录模板定义
const ADJUSTMENT_TEMPLATES: Record<string, { type: string; description: string; lines: { code: string; name: string; dr: number; cr: number }[] }> = {
  bad_debt: { type: 'aje', description: '计提坏账准备', lines: [
    { code: '6601', name: '资产减值损失', dr: 0, cr: 0 },
    { code: '1231', name: '坏账准备', dr: 0, cr: 0 },
  ]},
  depreciation: { type: 'aje', description: '补提折旧', lines: [
    { code: '6602', name: '管理费用-折旧', dr: 0, cr: 0 },
    { code: '1602', name: '累计折旧', dr: 0, cr: 0 },
  ]},
  amortization: { type: 'aje', description: '补提摊销', lines: [
    { code: '6602', name: '管理费用-摊销', dr: 0, cr: 0 },
    { code: '1702', name: '累计摊销', dr: 0, cr: 0 },
  ]},
  accrued_expense: { type: 'aje', description: '预提费用', lines: [
    { code: '6602', name: '管理费用', dr: 0, cr: 0 },
    { code: '2211', name: '应付职工薪酬', dr: 0, cr: 0 },
  ]},
  revenue_cutoff: { type: 'aje', description: '收入截止调整', lines: [
    { code: '5001', name: '主营业务收入', dr: 0, cr: 0 },
    { code: '2205', name: '合同负债', dr: 0, cr: 0 },
  ]},
  rcl_current_noncurrent: { type: 'rje', description: '一年内到期非流动资产重分类', lines: [
    { code: '1503', name: '一年内到期的非流动资产', dr: 0, cr: 0 },
    { code: '1511', name: '长期股权投资', dr: 0, cr: 0 },
  ]},
  rcl_ar_prepay: { type: 'rje', description: '应收/预付重分类', lines: [
    { code: '1123', name: '预付款项', dr: 0, cr: 0 },
    { code: '1122', name: '应收账款', dr: 0, cr: 0 },
  ]},
  rcl_ap_advance: { type: 'rje', description: '应付/预收重分类', lines: [
    { code: '2203', name: '预收款项', dr: 0, cr: 0 },
    { code: '2202', name: '应付账款', dr: 0, cr: 0 },
  ]},
}

function onTemplateSelect(key: string) {
  if (!key) return
  const tpl = ADJUSTMENT_TEMPLATES[key]
  if (!tpl) return
  form.value.adjustment_type = tpl.type
  form.value.description = tpl.description
  form.value.line_items = tpl.lines.map(l => ({
    standard_account_code: l.code,
    account_name: l.name,
    debit_amount: l.dr,
    credit_amount: l.cr,
  }))
}

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
  // [enterprise-linkage 3.8] Fetch impact preview when account changes
  if (code) fetchPreview(code)
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
      _showImpactFeedback()
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
        _showImpactFeedback()
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

/** 显示分录对试算表的影响反馈 */
function _showImpactFeedback() {
  const accounts = form.value.line_items
    .map(li => li.account_name || li.standard_account_code)
    .filter(Boolean)
  if (!accounts.length) return
  const type = form.value.adjustment_type === 'aje' ? '审计调整' : '重分类'
  ElMessage({
    type: 'info',
    message: `${type}已更新试算表：${accounts.join('、')}`,
    duration: 4000,
    showClose: true,
  })
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
    handleApiError(e, '批量提交')
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
    await confirmConvert('该分录', '未更正错报')
  } catch {
    return
  }

  convertingGroupId.value = row.entry_group_id
  try {
    const res = await convertAjeToMisstatement(projectId.value, row.entry_group_id)
    ElMessage.success(`已转为错报（净额 ${res.net_amount}）`)
    try {
      await confirmDangerous('是否立即查看《未更正错报汇总表》？', '转换成功')
      router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
    } catch {
      /* 用户选择稍后，不跳转 */
    }
  } catch (err: any) {
    // R1 Bug Fix 8: 使用 parseApiError 统一解析
    const parsed = parseApiError(err)
    if (parsed.code === 'ALREADY_CONVERTED') {
      try {
        await confirmDangerous('该分录已转为未更正错报，是否跳转查看？', '已转换')
        router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
      } catch {
        /* 用户选择关闭 */
      }
    } else {
      handleApiError({ response: { status: 400, data: { detail: parsed.message || '转换失败' } } }, '转换错报')
    }
  } finally {
    convertingGroupId.value = ''
  }
}

async function batchReview(status: string) {
  const eligible = selectedRows.value.filter(r => r.review_status === ADJUSTMENT_STATUS.PENDING_REVIEW)
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
      `${P.adjustments.exportSummary(projectId.value)}?year=${year.value}&format=excel`,
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

/* 展开行明细 */
.gt-adj-expand-detail {
  padding: 8px 16px 8px 48px;
  background: #faf8fd;
}
.gt-adj-line-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.gt-adj-line-table th {
  background: #f0edf5;
  padding: 4px 8px;
  font-weight: 600;
  text-align: left;
  border-bottom: 1px solid #e8e4f0;
}
.gt-adj-line-table td {
  padding: 4px 8px;
  border-bottom: 1px solid #f0f0f0;
}
.gt-adj-expand-footer {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 11px;
  color: #909399;
}
.gt-adj-expand-desc { color: #606266; }
.gt-adj-expand-impact { color: #4b2d77; font-weight: 500; }
.gt-adj-dir-dr { color: #f56c6c; font-weight: 600; }
.gt-adj-dir-cr { color: #409eff; font-weight: 600; }

/* 批量模式浮动提交栏 */
.gt-adj-batch-float-bar {
  position: fixed;
  bottom: 0;
  left: 220px;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  background: linear-gradient(135deg, #f8f6fb, #ece4f5);
  border-top: 2px solid #4b2d77;
  box-shadow: 0 -4px 12px rgba(75, 45, 119, 0.1);
  font-size: 13px;
  font-weight: 600;
  color: #4b2d77;
}

:deep(.el-tabs__item.is-active) { font-weight: 600; }
</style>
