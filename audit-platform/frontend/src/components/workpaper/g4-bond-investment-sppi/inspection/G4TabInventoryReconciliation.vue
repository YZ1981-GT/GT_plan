<template>
  <div class="g4-tab-inventory-reconciliation" data-testid="g4-inventory-reconciliation">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：将盘点日实存倒轧至资产负债表日，与账面结存核对，确认报表日债权投资对应证券的存在性与完整性；差异已查明并说明。"
      style="margin-bottom: 12px"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-7" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ items.length }} 行</el-tag>
      </div>
    </div>

    <div class="section-header">
      <div class="title-block">
        <h3 class="section-title">G4-8 有价证券盘点倒轧表</h3>
        <p class="section-sub">盘点日实存 − 增加 + 减少 = 报表日推算实存，再与账面勾稽</p>
      </div>
      <div class="section-actions">
        <el-button
          size="small"
          type="success"
          plain
          :disabled="isReadonly"
          @click="reconciliationLogic.importFromInventory()"
        >
          从 G4-7 带出
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="fillAiConclusion"
        >
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pushVarianceMemos">
          推送未解释差异至 G4-3
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-8盘点倒轧结存表')">复核</el-button>
      </div>
    </div>

    <details class="procedure-block">
      <summary>编制思路与程序（展开）</summary>
      <ol>
        <li>自 G4-7 带入盘点日实存（数量、面值、票面利率、到期日）。</li>
        <li>
          登记<strong>资产负债表日 → 盘点日</strong>期间增减（购入/处置/到期兑付等），并填写证据索引（交割单、对账单、日记账）。
        </li>
        <li>
          推算报表日实存：
          <b>报表日 = 盘点日 − 增加 + 减少</b>
          （增减口径为资产负债表日至盘点日；勿与「盘点日→报表日」方向混淆）。
        </li>
        <li>
          与账面结存（数量/面值/总计）勾稽；账面摊余成本列作参照，便于与 G4-1 / G4-4 账面价值勾对。
        </li>
        <li>数量或面值差异≠0 须填备注并追查；必要时交叉调整分录与 G4-3。</li>
      </ol>
    </details>

    <!-- 日期头 -->
    <el-form :model="header" label-width="100px" size="small" class="recon-header-form" :disabled="isReadonly">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="盘点日">
            <el-date-picker
              v-model="header.countDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="监盘实际日期"
              @change="reconciliationLogic.updateHeader({ countDate: header.countDate })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="资产负债表日">
            <el-date-picker
              v-model="header.balanceSheetDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="截止日 / 报表日"
              @change="reconciliationLogic.updateHeader({ balanceSheetDate: header.balanceSheetDate })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="倒轧区间">
            <span class="period-hint">{{ periodHint }}</span>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="stats-bar">
      倒轧证券 <b>{{ stats.total }}</b> 项 ·
      差异项 <b :class="{ warn: stats.withDiff > 0 }">{{ stats.withDiff }}</b> ·
      缺备注 <b :class="{ warn: stats.missingRemark > 0 }">{{ stats.missingRemark }}</b>
      <span class="total">
        报表日总计 {{ fmt(summary.reportTotalTotal) }} ·
        账面总计 {{ fmt(summary.bookTotalTotal) }} ·
        面值差异 {{ fmt(summary.varianceTotal) }} ·
        账面摊余成本 {{ fmt(summary.bookCarryingAmountTotal) }}
      </span>
    </div>

    <el-alert
      v-if="stats.withDiff > 0"
      type="warning"
      :closable="false"
      class="diff-alert"
      :title="`有 ${stats.withDiff} 项数量或面值差异≠0${stats.missingRemark ? `，其中 ${stats.missingRemark} 项未填备注` : ''}，请在「报表日实存+账面差异」区段追查并说明。`"
    />

    <el-segmented
      v-model="activeTab"
      :options="tabOptions"
      size="default"
      class="reconciliation-tabs"
      @change="(val: any) => reconciliationLogic.switchTab(val as any)"
    />

    <el-table
      :data="items"
      border
      stripe
      size="small"
      highlight-current-row
      :row-class-name="getRowClassName"
      class="reconciliation-table"
      @current-change="handleRowClick"
    >
      <!-- ═══ 盘点日实存 ═══ -->
      <template v-if="activeTab === 'countDate'">
        <el-table-column label="证券名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <el-input
              v-model="row.securitiesName"
              size="small"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { securitiesName: row.securitiesName })"
            />
          </template>
        </el-table-column>
        <el-table-column label="数量" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.countQuantity"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { countQuantity: row.countQuantity })"
            />
          </template>
        </el-table-column>
        <el-table-column label="面值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.countFaceValue"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { countFaceValue: row.countFaceValue })"
            />
          </template>
        </el-table-column>
        <el-table-column label="总计" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="总计 = 面值 × 数量" placement="top">
              <span class="formula-cell">{{ fmt(row.countTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.countCouponRate"
              size="small"
              :controls="false"
              :precision="4"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { countCouponRate: row.countCouponRate })"
            />
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="130">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.countMaturityDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { countMaturityDate: row.countMaturityDate })"
            />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 增减变动 ═══ -->
      <template v-if="activeTab === 'changes'">
        <el-table-column label="证券名称" prop="securitiesName" min-width="140" fixed="left" />
        <el-table-column label="增加·数量" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.increaseQuantity"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { increaseQuantity: row.increaseQuantity })"
            />
          </template>
        </el-table-column>
        <el-table-column label="增加·面值总额" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-model="row.increaseFaceTotal"
              size="small"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { increaseFaceTotal: row.increaseFaceTotal })"
            />
          </template>
        </el-table-column>
        <el-table-column label="减少·数量" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.decreaseQuantity"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { decreaseQuantity: row.decreaseQuantity })"
            />
          </template>
        </el-table-column>
        <el-table-column label="减少·面值总额" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-model="row.decreaseFaceTotal"
              size="small"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { decreaseFaceTotal: row.decreaseFaceTotal })"
            />
          </template>
        </el-table-column>
        <el-table-column label="证据索引" min-width="140">
          <template #default="{ row }">
            <el-input
              v-model="row.changeEvidenceRef"
              size="small"
              :disabled="isReadonly"
              placeholder="交割单/对账单索引"
              @change="reconciliationLogic.updateItem(row.id, { changeEvidenceRef: row.changeEvidenceRef })"
            />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 报表日实存+差异 ═══ -->
      <template v-if="activeTab === 'reportDate'">
        <el-table-column label="证券名称" prop="securitiesName" min-width="120" fixed="left" />
        <el-table-column label="报表日·数量" min-width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="报表日数量 = 盘点日数量 − 增加 + 减少" placement="top">
              <span class="formula-cell">{{ row.reportQuantity }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="报表日·面值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.reportFaceValue"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { reportFaceValue: row.reportFaceValue })"
            />
          </template>
        </el-table-column>
        <el-table-column label="报表日·总计" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="报表日总计 = 报表日面值 × 报表日数量" placement="top">
              <span class="formula-cell">{{ fmt(row.reportTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="继承盘点日票面利率（同种证券条款不变）" placement="top">
              <span class="formula-cell muted">{{ row.reportCouponRate }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="110">
          <template #default="{ row }">
            <el-tooltip content="继承盘点日到期日" placement="top">
              <span class="formula-cell muted">{{ row.reportMaturityDate || '—' }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面·数量" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.bookQuantity"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { bookQuantity: row.bookQuantity })"
            />
          </template>
        </el-table-column>
        <el-table-column label="账面·面值" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-model="row.bookFaceValue"
              size="small"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { bookFaceValue: row.bookFaceValue })"
            />
          </template>
        </el-table-column>
        <el-table-column label="账面·总计" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="有面值时按 面值×数量 自动计算" placement="top">
              <span class="formula-cell">{{ fmt(row.bookTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面摊余成本" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-model="row.bookCarryingAmount"
              size="small"
              :disabled="isReadonly"
              @change="reconciliationLogic.updateItem(row.id, { bookCarryingAmount: row.bookCarryingAmount })"
            />
          </template>
        </el-table-column>
        <el-table-column label="差异·数量" min-width="90" align="right">
          <template #default="{ row, $index }">
            <el-tooltip content="差异数量 = 报表日数量 − 账面数量" placement="top">
              <span :class="['formula-cell', { 'variance-red': varianceHighlights[$index] && Math.abs(row.varianceQuantity) >= 0.01 }]">
                {{ row.varianceQuantity }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异·面值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-tooltip content="差异面值 = 报表日总计 − 账面总计" placement="top">
              <span :class="['formula-cell', { 'variance-red': varianceHighlights[$index] }]">
                {{ fmt(row.variance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="150">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.remark"
              size="small"
              :disabled="isReadonly"
              :class="{ 'remark-required': varianceHighlights[$index] && !(row.remark || '').trim() }"
              :placeholder="varianceHighlights[$index] ? '差异非零，请填写说明' : ''"
              @change="reconciliationLogic.updateItem(row.id, { remark: row.remark })"
            />
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly || items.length <= 1"
            @click="reconciliationLogic.removeItem(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-row">
      <span class="summary-label">合计：</span>
      <template v-if="activeTab === 'countDate'">
        <span class="summary-item">数量 {{ summary.countQuantityTotal }}</span>
        <span class="summary-item">总计 {{ fmt(summary.countTotalTotal) }}</span>
      </template>
      <template v-if="activeTab === 'changes'">
        <span class="summary-item">增加数量 {{ summary.increaseQuantityTotal }}</span>
        <span class="summary-item">减少数量 {{ summary.decreaseQuantityTotal }}</span>
        <span class="summary-item">增加面值 {{ fmt(summary.increaseFaceTotalTotal) }}</span>
        <span class="summary-item">减少面值 {{ fmt(summary.decreaseFaceTotalTotal) }}</span>
      </template>
      <template v-if="activeTab === 'reportDate'">
        <span class="summary-item">报表日数量 {{ summary.reportQuantityTotal }}</span>
        <span class="summary-item">报表日总计 {{ fmt(summary.reportTotalTotal) }}</span>
        <span class="summary-item">账面总计 {{ fmt(summary.bookTotalTotal) }}</span>
        <span class="summary-item">摊余成本 {{ fmt(summary.bookCarryingAmountTotal) }}</span>
        <span :class="['summary-item', { 'variance-red': Math.abs(summary.varianceTotal) >= 0.01 }]">
          面值差异 {{ fmt(summary.varianceTotal) }}
        </span>
      </template>
    </div>

    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="reconciliationLogic.addItem()">
        + 新增倒轧行
      </el-button>
      <slot name="importExport">
        <G4SppiImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G4-8"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </slot>
    </div>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-placeholder="填写：（1）盘点日与报表日是否一致；（2）资产负债表日至盘点日增减核对及证据；（3）倒轧与账面勾稽、数量/面值差异处理；（4）账面摊余成本与 G4-1/G4-4 勾对情况。"
      @update:note="saveAuditNote"
      @update:conclusion="reconciliationLogic.setAuditConclusion"
    />

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 三区段 Tab 共享同一组行数据，切换仅改变列；点击行可跨 Tab 保持选中。</p>
        <p>2. 增减口径是「资产负债表日 → 盘点日」：购入记增加、处置/兑付记减少；推算公式为 报表日 = 盘点日 − 增加 + 减少。</p>
        <p>3. 票面利率与到期日以盘点日录入为准，报表日区段自动继承，无需重复填写。</p>
        <p>4. 「账面摊余成本」为参照列，用于与债权投资账面价值勾对；面值倒轧仍以数量/面值总额为准。</p>
        <p>5. 差异非零行红色高亮，备注必填；优先用「从 G4-7 带出」初始化盘点日实存。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G4TabInventoryReconciliation.vue — G4-8 有价证券盘点倒轧表（重构）
 *
 * - 3区段Tab：盘点日实存 / 增减（拆增加·减少） / 报表日+账面差异
 * - 倒轧公式对齐致同：报表日 = 盘点日 − 增加 + 减少
 * - 利率/到期日继承；证据索引；账面摊余成本参照；数量+面值双差异
 */
import { inject, toRef, computed, ref, watch } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4SppiImportExportDropdown from '../G4SppiImportExportDropdown.vue'
import { useG4SppiReconciliation, TAB_OPTIONS } from '@/composables/useG4SppiReconciliation'
import type { ReconciliationItem } from '@/composables/useG4SppiReconciliation'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { useG4SppiAiGenerate } from '../../composables/useG4SppiAiGenerate'
import {
  buildG48VarianceMemos,
  dispatchG4ExceptionDrafts,
} from '../../composables/g4ExceptionRouting'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'imported'): void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4SppiAiGenerate(wpIdRef)

const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
formData.loadAll()

const reconciliationLogic = useG4SppiReconciliation({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const {
  activeTab,
  selectedRowIndex,
  items,
  summary,
  stats,
  varianceHighlights,
  auditConclusion,
  header,
} = reconciliationLogic

const tabOptions = TAB_OPTIONS.map((t) => ({ label: t.label, value: t.key }))

const periodHint = computed(() => {
  const a = header.value.balanceSheetDate
  const b = header.value.countDate
  if (a && b) return `${a} → ${b}`
  if (a) return `${a} → 盘点日（待填）`
  if (b) return `报表日（待填） → ${b}`
  return '请填写资产负债表日与盘点日'
})

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'reconciliation-conclusion',
    auditConclusion.value || '',
    {
      行数: stats.value.total,
      差异项: stats.value.withDiff,
      报表日总计: summary.value.reportTotalTotal,
      账面总计: summary.value.bookTotalTotal,
      面值差异: summary.value.varianceTotal,
    },
    'AI 审计结论',
  )
  if (text) reconciliationLogic.setAuditConclusion(text)
}

function handleRowClick(row: ReconciliationItem | null): void {
  if (!row) return
  const idx = items.value.findIndex((i) => i.id === row.id)
  if (idx >= 0) reconciliationLogic.selectRow(idx)
}

function pushVarianceMemos(): void {
  const drafts = buildG48VarianceMemos(items.value)
  if (!drafts.length) {
    ElMessage.info('没有未解释的盘点倒轧差异')
    return
  }
  dispatchG4ExceptionDrafts(drafts, formData.allResponses.value)
  ElMessage.success(`已推送 ${drafts.length} 条 G4-3 差异备忘`)
}

function getRowClassName({ row, rowIndex }: { row: ReconciliationItem; rowIndex: number }): string {
  const classes: string[] = []
  if (rowIndex === selectedRowIndex.value) classes.push('selected-row')
  if (varianceHighlights.value[rowIndex]) classes.push('variance-highlight-row')
  return classes.join(' ')
}

const NOTE_KEY = 'G4-8-reconciliation-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  void formData.saveImmediate(NOTE_KEY, { conclusion: null, remark: val })
}
watch(
  () => formData.allResponses.value.get(NOTE_KEY)?.remark,
  (v) => {
    if (v != null) auditNote.value = v
  },
  { immediate: true },
)
</script>

<style scoped>
.g4-tab-inventory-reconciliation { font-size: var(--wp-font-size, 13px); }
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
}
.title-block { min-width: 0; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.section-actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.procedure-block {
  margin-bottom: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 8px 12px;
  background: #fafafa;
}
.procedure-block summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.procedure-block ol {
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}

.recon-header-form { margin-bottom: 8px; }
.period-hint {
  color: #606266;
  font-size: 12px;
}

.stats-bar {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: baseline;
}
.stats-bar b { color: #303133; }
.stats-bar b.warn { color: #e6a23c; }
.stats-bar .total { margin-left: auto; color: #909399; }

.diff-alert { margin-bottom: 10px; }

.reconciliation-tabs { margin-bottom: 12px; }

.reconciliation-table { margin-bottom: 8px; }
.reconciliation-table :deep(.selected-row) { background-color: #ecf5ff !important; }
.reconciliation-table :deep(.variance-highlight-row td) { background-color: #fef0f0 !important; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}
.formula-cell.muted {
  color: #909399;
  border-bottom-style: dotted;
}
.variance-red {
  color: #f56c6c;
  font-weight: 600;
}
.remark-required :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

.summary-row {
  padding: 8px 12px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  margin-bottom: 12px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: var(--wp-font-size, 13px);
}
.summary-label { font-weight: 600; color: #303133; }
.summary-item { color: #606266; }

.table-actions {
  display: flex;
  gap: 8px;
  margin: 8px 0 16px;
}

.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p { margin: 0; }
</style>
