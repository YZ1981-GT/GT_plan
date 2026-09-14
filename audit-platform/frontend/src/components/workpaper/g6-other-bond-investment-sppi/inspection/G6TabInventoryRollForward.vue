<template>
  <div class="g6-tab-inventory-roll-forward">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：将盘点日实际持有数量倒轧至资产负债表日（基准日），验证期末其他债权投资对应有价证券的存在性与完整性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:G6-10" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ reconciliation.items.value.length }} 行</el-tag>
      <el-tag size="small" :type="directionTagType">{{ reconciliation.periodHint.value }}</el-tag>
      <el-button
        size="small"
        type="success"
        plain
        @click="guideVisible = true"
      >使用说明</el-button>
      <el-button
        v-if="!props.isReadonly"
        size="small"
        type="primary"
        plain
        @click="handleImportFromG69"
      >从 G6-9 带入盘点</el-button>
      <el-button
        v-if="!props.isReadonly"
        size="small"
        plain
        :loading="bookSyncing"
        @click="handleImportBookFromG62"
      >从 G6-2 带入账面</el-button>
      <el-button
        v-if="!props.isReadonly"
        size="small"
        plain
        @click="handleImportBookFromG69"
      >从 G6-9 带入账面</el-button>
    </div>

    <!-- 日期头 -->
    <el-form
      :model="reconciliation.header.value"
      label-width="100px"
      size="small"
      class="recon-header-form"
      :disabled="props.isReadonly"
    >
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="盘点日">
            <el-date-picker
              :model-value="reconciliation.header.value.countDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="监盘实际日期"
              @update:model-value="(v: string) => onHeaderChange({ countDate: v || '' })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="资产负债表日">
            <el-date-picker
              :model-value="reconciliation.header.value.balanceSheetDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="截止日 / 报表日"
              @update:model-value="(v: string) => onHeaderChange({ balanceSheetDate: v || '' })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="倒轧区间">
            <span class="period-hint">{{ reconciliation.periodHint.value }}</span>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <el-alert
      v-if="reconciliation.rollDirection.value === 'unknown'"
      type="warning"
      :closable="false"
      class="direction-alert"
      title="请填写盘点日与资产负债表日。未齐时按「期后盘点·倒推」计算：基准日数量 = 盘点日数量 − 期间净增加。"
    />
    <el-alert
      v-else-if="reconciliation.rollDirection.value === 'sameDay'"
      type="success"
      :closable="false"
      class="direction-alert"
      title="盘点日与资产负债表日相同，基准日数量等于盘点日数量；期间增减应为空或为零。"
    />

    <!-- ═══ 2区段Tab切换（行同步） ═══ -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'rollForward' }"
        @click="switchTab('rollForward')"
      >
        Tab1: 倒轧计算(10列)
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'changeDetail' }"
        @click="switchTab('changeDetail')"
      >
        Tab2: 增减明细(8列)
      </button>
    </div>

    <!-- ═══ Tab1: 倒轧计算(10列) ═══ -->
    <el-card v-if="activeTab === 'rollForward'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">盘点倒轧表 — 倒轧计算</span>
          <div class="section-actions">
            <el-tag v-if="reconciliation.varianceCount.value > 0" type="danger" size="small">
              {{ reconciliation.varianceCount.value }}项差异
            </el-tag>
            <el-button
              size="small"
              :disabled="props.isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-10-roll-forward')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="reconciliation.items.value"
        border
        size="small"
        class="recon-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        @current-change="handleTab1RowChange"
      >
        <!-- 证券名称 -->
        <el-table-column label="证券名称" min-width="140">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.securitiesName }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small" type="danger" link
                @click.stop="reconciliation.removeItem(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <!-- 证券代码 -->
        <el-table-column label="证券代码" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.securitiesCode"
              size="small"
              placeholder="代码"
            />
            <span v-else>{{ row.securitiesCode || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 盘点日数量 -->
        <el-table-column label="盘点日数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.countDateQuantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.countDateQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 增减 -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="期间持仓净增加（买入/转入为正，卖出/到期/转出为负）。有 Tab2 明细时自动汇总。" placement="top">
              <span>增减(净增加)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && !reconciliation.hasAutoChangeSource(row)"
              v-model="row.changeQuantity"
              size="small" :controls="false"
              style="width: 85px"
            />
            <span
              v-else
              class="formula-cell"
              :title="reconciliation.hasAutoChangeSource(row) ? '由 Tab2 增减明细自动汇总' : ''"
            >{{ row.changeQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 基准日数量（公式列） -->
        <el-table-column label="基准日数量" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :title="reportQtyFormulaTitle"
            >{{ row.reportDateQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 账面数量 -->
        <el-table-column label="账面数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.bookQuantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.bookQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 差异（公式列，红色高亮） -->
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :style="reconciliation.getVarianceCellStyle(row)"
              title="差异 = 基准日数量 - 账面数量"
            >{{ row.variance }}</span>
          </template>
        </el-table-column>
        <!-- 差异原因 -->
        <el-table-column label="差异原因" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.varianceReason"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="差异原因..."
              :class="{ 'variance-reason-required': reconciliation.isVarianceReasonMissing(row) }"
            />
            <span v-else>{{ row.varianceReason || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 差异结论 -->
        <el-table-column label="差异结论" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.varianceConclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="结论..."
              :class="{ 'variance-reason-required': reconciliation.isVarianceConclusionMissing(row) }"
            />
            <span v-else>{{ row.varianceConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 索引 -->
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.indexRef"
              size="small"
              placeholder="索引"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 备注 -->
        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 差异必填校验提示 -->
      <el-alert
        v-if="reconciliation.varianceValidationErrors.value.length > 0"
        type="warning"
        :closable="false"
        class="variance-alert"
      >
        <template #title>
          差异闭环提示：以下项目存在差异但未填写原因或结论
        </template>
        <ul class="variance-error-list">
          <li v-for="item in reconciliation.varianceValidationErrors.value" :key="item.row.id + item.field">
            {{ item.row.securitiesName }}（差异: {{ item.row.variance }}，缺{{ item.field === 'reason' ? '原因' : '结论' }}）
          </li>
        </ul>
      </el-alert>
    </el-card>

    <!-- ═══ Tab2: 增减明细 ═══ -->
    <el-card v-if="activeTab === 'changeDetail'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">盘点倒轧表 — 增减明细</span>
          <div class="section-actions">
            <el-tag
              size="small"
              :type="reconciliation.detailValidationErrors.value.length ? 'danger' : 'info'"
            >
              {{ reconciliation.changeDetailCount.value }}条明细
              <template v-if="reconciliation.detailValidationErrors.value.length">
                · {{ reconciliation.detailValidationErrors.value.length }}条待补全
              </template>
            </el-tag>
            <el-button
              size="small"
              :disabled="props.isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-10-change-detail')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="reconciliation.changeDetails.value"
        border
        size="small"
        class="recon-table"
        highlight-current-row
        row-key="id"
        :row-class-name="detailRowClassName"
      >
        <!-- 证券名称 -->
        <el-table-column label="证券名称" min-width="130">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.securitiesName }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small" type="danger" link
                @click.stop="reconciliation.removeChangeDetail(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="证券代码" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.securitiesCode"
              size="small"
              placeholder="代码"
            />
            <span v-else>{{ row.securitiesCode || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 日期 -->
        <el-table-column label="日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!props.isReadonly"
              v-model="row.date"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 110px"
            />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 交易类型 -->
        <el-table-column label="交易类型" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!props.isReadonly"
              v-model="row.transactionType"
              size="small"
              placeholder="选择"
              style="width: 100px"
            >
              <el-option
                v-for="opt in TRANSACTION_TYPE_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-else>{{ getTransactionTypeLabel(row.transactionType) }}</span>
          </template>
        </el-table-column>
        <!-- 数量 -->
        <el-table-column label="数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.quantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.quantity }}</span>
          </template>
        </el-table-column>
        <!-- 金额 -->
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.amount"
              size="small"
              style="width: 105px"
            />
            <span v-else>{{ fmtNum(row.amount) }}</span>
          </template>
        </el-table-column>
        <!-- 凭证号 -->
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.voucherNo"
              size="small"
              placeholder="凭证号"
            />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 经办人 -->
        <el-table-column label="经办人" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.handler"
              size="small"
              placeholder="经办人"
            />
            <span v-else>{{ row.handler || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 备注 -->
        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="reconciliation.detailValidationErrors.value.length > 0"
        type="warning"
        :closable="false"
        class="variance-alert"
      >
        <template #title>
          增减明细校验：请补全日期、交易类型、数量、凭证号，并确保证券在倒轧表中且日期落在倒轧区间
        </template>
        <ul class="variance-error-list">
          <li
            v-for="issue in reconciliation.detailValidationErrors.value.slice(0, 8)"
            :key="issue.detail.id"
          >
            第{{ issue.index + 1 }}行 {{ issue.detail.securitiesName || '(未命名)' }}：{{ issue.reasons.join('；') }}
          </li>
        </ul>
      </el-alert>
    </el-card>
    <div class="bottom-actions">
      <el-button
        v-if="!props.isReadonly"
        type="primary" size="small"
        @click="activeTab === 'rollForward' ? reconciliation.addItem() : reconciliation.addChangeDetail()"
      >
        + 新增行
      </el-button>
      <G6SppiImportExportDropdown
        v-if="wpId"
        :wp-id="wpId"
        sheet="G6-10"
        :disabled="props.isReadonly"
        @imported="onImported"
      />
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="props.isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述倒轧计算的执行情况及结果、盘点日至基准日增减明细的核对情况、差异原因追查、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="props.isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >✨ AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="reconciliation.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="props.isReadonly"
        placeholder="对盘点倒轧结果的审计结论..."
        @input="handleConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 本表用于将盘点日实际持有数量倒轧至资产负债表日（基准日），以验证期末证券存在性</p>
        <p>2. 请先填写盘点日与资产负债表日：期后盘点倒推（基准日=盘点日−净增加）；期前盘点顺推（基准日=盘点日+净增加）；同日则无需倒轧</p>
        <p>3. 净增加口径为两日之间持仓变动（买入/转入为正，卖出/到期/转出为负）；有 Tab2 明细时自动汇总，删光明细后自动清零</p>
        <p>4. 「从 G6-9 带入盘点」仅带入盘点日数量；账面数量可用「从 G6-2 带入账面」（优先）或「从 G6-9 带入账面」（须确认 G6-9 账面已是报表日口径）</p>
        <p>5. 差异不为零时必须填写差异原因与差异结论；未闭环将阻断审计结论保存（结论独立存储）</p>
        <p>6. 增减明细按证券代码/关联 ID/名称匹配主表；凭证号须与会计凭证一致</p>
      </div>
    </details>

    <G6InventoryRollForwardGuideDialog v-model="guideVisible" />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabInventoryRollForward.vue — G6-10 盘点倒轧表（2区段Tab + 行同步）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.4
 * Requirements: 6.2, 6.3, 6.4
 *
 * 功能：
 * - Tab1倒轧计算(10列): 证券名称|盘点日数量|增减|基准日数量(公式)|账面数量|差异(公式,红色)|差异原因|差异结论|索引|备注
 * - Tab2增减明细(8列): 证券名称|日期|交易类型(买入/卖出/到期/转让)|数量|金额|凭证号|经办人|备注
 * - 差异红色高亮 + 差异原因必填
 * - 2区段Tab行同步（selectedRowIndex）
 * - 动态行增删 + 导入导出 + AI辅助 + 审计结论 + 编制提示
 *
 * Props 对齐父级 GtG6OtherBondSppi 传入的 html-data / is-readonly（自加载走 useG6SppiFormData）
 */
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useG6SppiReconciliation,
  TRANSACTION_TYPE_OPTIONS,
  type ReconciliationHeader,
} from '../../composables/useG6SppiReconciliation'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import {
  fetchG62DetailRows,
  mapG62RowsToInventorySeeds,
  parseG6ChecklistPayload,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'
import G6InventoryRollForwardGuideDialog from './G6InventoryRollForwardGuideDialog.vue'
import type { ReconciliationItem, ReconciliationData } from '../../composables/useG6SppiReconciliation'

const props = defineProps<{
  htmlData: Record<string, any> | null
  isReadonly: boolean
  wpId: string
  projectId: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const reconciliation = useG6SppiReconciliation()
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)
const bookSyncing = ref(false)
const guideVisible = ref(false)

const DATA_KEY = 'G6-10-reconciliation-data'
const ROWS_KEY = 'G6-10-rows'
const CONCLUSION_KEY = 'G6-10-audit-conclusion'
const NOTE_KEY = 'G6-10-inventory-rollforward-audit-note'
const INV_DATA_KEY = 'G6-9-securities-inventory-data'
const INV_ROWS_KEY = 'G6-9-rows'

const activeTab = computed(() => reconciliation.activeTab.value)

const directionTagType = computed(() => {
  switch (reconciliation.rollDirection.value) {
    case 'sameDay': return 'success'
    case 'forward': return 'warning'
    case 'backward': return ''
    default: return 'info'
  }
})

const reportQtyFormulaTitle = computed(() => {
  switch (reconciliation.rollDirection.value) {
    case 'forward':
      return '基准日数量 = 盘点日数量 + 期间净增加（期前盘点·顺推）'
    case 'sameDay':
      return '基准日数量 = 盘点日数量（同日盘点）'
    case 'backward':
      return '基准日数量 = 盘点日数量 − 期间净增加（期后盘点·倒推）'
    default:
      return '基准日数量 = 盘点日数量 − 期间净增加（日期未齐，默认倒推）'
  }
})

function switchTab(tab: 'rollForward' | 'changeDetail'): void {
  reconciliation.switchTab(tab)
}

function onHeaderChange(patch: Partial<ReconciliationHeader>): void {
  if (props.isReadonly) return
  reconciliation.updateHeader(patch)
  handleSave()
}

const currentRowId = computed(() => {
  const rows = reconciliation.items.value
  if (rows.length === 0) return ''
  const idx = reconciliation.selectedRowIndex.value
  return rows[idx]?.id || rows[0]?.id || ''
})

function handleTab1RowChange(row: ReconciliationItem | null): void {
  if (!row) return
  const idx = reconciliation.items.value.findIndex(r => r.id === row.id)
  if (idx >= 0) reconciliation.selectRow(idx)
}

const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function loadConclusion(): void {
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.conclusion != null && String(conc.conclusion).trim() !== '') {
    reconciliation.auditConclusion.value = String(conc.conclusion)
    return
  }
  // 兼容：旧数据可能把结论嵌在 reconciliation-data 内
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary?.auditConclusion) {
    reconciliation.auditConclusion.value = String(primary.auditConclusion)
  }
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  loadConclusion()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData) {
    initFromData()
    loadConclusion()
  }
})

function initFromData(): void {
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary && (Array.isArray(primary.items) || Array.isArray(primary.changeDetails))) {
    reconciliation.loadData(primary as ReconciliationData)
    return
  }
  const rowsPayload = parseG6ChecklistPayload(formData.allResponses.value.get(ROWS_KEY))
  if (rowsPayload) {
    if (Array.isArray(rowsPayload.items) || Array.isArray(rowsPayload.changeDetails)) {
      reconciliation.loadData(rowsPayload as ReconciliationData)
      return
    }
    if (Array.isArray(rowsPayload) && rowsPayload.length) {
      reconciliation.loadFromFlatRows(rowsPayload)
      return
    }
  }
  const content = formData.parseContent()
  if (content.reconciliation) {
    const rec = content.reconciliation as any
    if (Array.isArray(rec.items) || Array.isArray(rec.changeDetails)) {
      reconciliation.loadData(rec as ReconciliationData)
    } else if (Array.isArray(rec)) {
      reconciliation.loadFromFlatRows(rec)
    } else if (Array.isArray(rec.rows)) {
      reconciliation.loadFromFlatRows(rec.rows)
    }
  }
}

/** 从 G6-9 带入盘点日数量（不覆盖账面数量） */
async function handleImportFromG69(): Promise<void> {
  if (props.isReadonly) return
  await formData.loadAll()
  const inv = parseG6ChecklistPayload(formData.allResponses.value.get(INV_DATA_KEY))
  if (inv?.items && Array.isArray(inv.items) && inv.items.length) {
    reconciliation.importFromInventory(inv.items)
    handleSave()
    return
  }
  const flat = parseG6ChecklistPayload(formData.allResponses.value.get(INV_ROWS_KEY))
  if (Array.isArray(flat) && flat.length) {
    reconciliation.importFromInventory(flat)
    handleSave()
    return
  }
  const content = formData.parseContent()
  const sheetInv = content.inventory as any
  if (sheetInv?.items && Array.isArray(sheetInv.items)) {
    reconciliation.importFromInventory(sheetInv.items)
    handleSave()
    return
  }
  reconciliation.importFromInventory(null)
}

/** 从 G6-2 带入报表日账面数量（不改盘点日数量） */
async function handleImportBookFromG62(): Promise<void> {
  if (props.isReadonly) return
  bookSyncing.value = true
  try {
    const rows = await fetchG62DetailRows(props.projectId, props.wpId)
    const seeds = mapG62RowsToInventorySeeds(rows)
    reconciliation.importBookFromSeeds(seeds, 'G6-2')
    handleSave()
  } catch {
    ElMessage.warning('同步 G6-2 失败，请稍后重试')
  } finally {
    bookSyncing.value = false
  }
}

/** 从 G6-9 带入账面（须确认已是报表日口径） */
async function handleImportBookFromG69(): Promise<void> {
  if (props.isReadonly) return
  try {
    await ElMessageBox.confirm(
      '将覆盖倒轧表「账面数量」。请确认 G6-9 账面已按资产负债表日维护（非盘点日账面）。是否继续？',
      '从 G6-9 带入账面',
      { confirmButtonText: '确认带入', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await formData.loadAll()
  const inv = parseG6ChecklistPayload(formData.allResponses.value.get(INV_DATA_KEY))
  const items = (inv?.items && Array.isArray(inv.items) ? inv.items : null)
    || (() => {
      const flat = parseG6ChecklistPayload(formData.allResponses.value.get(INV_ROWS_KEY))
      return Array.isArray(flat) ? flat : null
    })()
  if (!items?.length) {
    reconciliation.importBookFromSeeds(null, 'G6-9')
    return
  }
  reconciliation.importBookFromSeeds(
    items.map((r: any) => ({
      id: r.id,
      securitiesName: r.securitiesName || '',
      securitiesCode: r.securitiesCode || '',
      bookQuantity: r.bookQuantity,
    })),
    'G6-9',
  )
  handleSave()
}

async function onImported(): Promise<void> {
  await formData.loadAll()
  initFromData()
  loadConclusion()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  emit('imported')
}

/** 仅保存表格数据（不含审计结论） */
function handleSave(): void {
  if (props.isReadonly) return
  const nested = reconciliation.toJSON()
  formData.debouncedSaveBatch([
    { itemId: DATA_KEY, data: { conclusion: JSON.stringify(nested) } },
    { itemId: ROWS_KEY, data: { conclusion: JSON.stringify(nested) } },
  ])
}

onBeforeUnmount(() => {
  handleSave()
  formData.flushPending()
})

/** 审计结论独立持久化；未通过差异校验则拒绝写入 */
function handleConclusionInput(): void {
  if (props.isReadonly) return
  if (!reconciliation.assertVarianceValidForSave('保存审计结论')) {
    return
  }
  formData.saveImmediate(CONCLUSION_KEY, {
    conclusion: reconciliation.auditConclusion.value || '',
  })
}

watch(
  [() => reconciliation.items.value, () => reconciliation.changeDetails.value, () => reconciliation.header.value],
  () => { handleSave() },
  { deep: true },
)

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  if (!reconciliation.assertVarianceValidForSave('生成审计结论')) return
  const text = await generateAndConfirm(
    'reconciliation-conclusion',
    reconciliation.auditConclusion.value || '',
    {
      itemCount: reconciliation.items.value.length,
      varianceCount: reconciliation.varianceCount.value,
      changeDetailCount: reconciliation.changeDetailCount.value,
      rollDirection: reconciliation.rollDirection.value,
      periodHint: reconciliation.periodHint.value,
      header: reconciliation.header.value,
      items: reconciliation.items.value.map((r) => ({
        securitiesName: r.securitiesName,
        countDateQuantity: r.countDateQuantity,
        changeQuantity: r.changeQuantity,
        reportDateQuantity: r.reportDateQuantity,
        bookQuantity: r.bookQuantity,
        variance: r.variance,
        varianceReason: r.varianceReason,
        varianceConclusion: r.varianceConclusion,
      })),
      changeDetails: reconciliation.changeDetails.value.slice(0, 50),
      changeDetailsTruncated: reconciliation.changeDetails.value.length > 50,
    },
    'AI 盘点倒轧审计结论',
  )
  if (text) {
    reconciliation.auditConclusion.value = text
    handleConclusionInput()
  }
}

function getTransactionTypeLabel(value: string): string {
  const opt = TRANSACTION_TYPE_OPTIONS.find(o => o.value === value)
  return opt?.label || value || '-'
}

function detailRowClassName({ row }: { row: { id: string } }): string {
  const bad = reconciliation.detailValidationErrors.value.some((e) => e.detail.id === row.id)
  return bad ? 'detail-invalid-row' : ''
}

function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

defineExpose({
  toJSON: () => reconciliation.toJSON(),
  isVarianceValid: computed(() => reconciliation.isVarianceValid.value),
})
</script>

<style scoped>
.g6-tab-inventory-roll-forward {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}

.recon-header-form {
  margin-bottom: 8px;
  padding: 8px 12px 0;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.period-hint {
  color: #606266;
  font-size: 12px;
  line-height: 1.4;
}
.direction-alert {
  margin-bottom: 12px;
}

/* ─── Tab切换按钮 ─── */
.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 12px;
  border-bottom: 2px solid #e4e7ed;
}

.tab-btn {
  padding: 8px 20px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  border: none;
  background: transparent;
  color: #606266;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.2s, border-color 0.2s;
}

.tab-btn:hover {
  color: #409eff;
}

.tab-btn.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 600;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.recon-table {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 名称单元格 ─── */
.name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ─── 公式列样式（虚线下划线+cursor:help+tooltip来源） ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── 差异原因必填红色边框 ─── */
.variance-reason-required :deep(.el-textarea__inner) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

.recon-table :deep(.detail-invalid-row td) {
  background-color: #fff7ed !important;
}

/* ─── 差异校验提示 ─── */
.variance-alert {
  margin-top: 12px;
}

.variance-error-list {
  margin: 4px 0 0 16px;
  padding: 0;
  font-size: 12px;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}

.import-export-dropdown {
  margin-left: 8px;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
