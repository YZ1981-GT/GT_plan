<script setup lang="ts">
/**
 * F3TabAdjudication — F3-1 审定表（贷方科目 2201）
 * Spec: .kiro/specs/f3-notes-payable/ Task 6.1
 * 比照 D4TabAdjudication（精美组件 gold-standard）
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF3Adjudication } from '../composables/useF3Adjudication'
import type { F3AdjudicationRow } from '../composables/useF3Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  crossSheet?: ReturnType<typeof import('../composables/useF3CrossSheet').useF3CrossSheet>
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  dataRows,
  subtotalRow,
  trialBalanceRow,
  differenceRow,
  detailCrossValidation,
  auditNote,
  auditConclusion,
  updateCell,
  publishAdjudicated,
} = useF3Adjudication({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  crossSheet: props.crossSheet,
})

const hasDifference = computed(() => Math.abs(differenceRow.value) > 0.005)

const footerRows = computed(() => [
  subtotalRow.value,
  {
    rowKey: 'tb',
    label: '试算表数(2201)',
    isFixed: true,
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    openingAdjusted: 0,
    periodCredit: 0,
    periodDebit: 0,
    closingUnadjusted: trialBalanceRow.value,
    closingAje: 0,
    closingRje: 0,
    closingAdjusted: trialBalanceRow.value,
    indexRef: '',
    isFromCrossSheet: true,
    isEditable: false,
  } as F3AdjudicationRow,
  {
    rowKey: 'variance',
    label: '差异',
    isFixed: true,
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    openingAdjusted: 0,
    periodCredit: 0,
    periodDebit: 0,
    closingUnadjusted: differenceRow.value,
    closingAje: 0,
    closingRje: 0,
    closingAdjusted: differenceRow.value,
    indexRef: '',
    isFromCrossSheet: false,
    isEditable: false,
  } as F3AdjudicationRow,
])

function getCellClass(row: F3AdjudicationRow, field: string): string {
  if (row.isFromCrossSheet) return 'cross-sheet-cell'
  if (['closingUnadjusted', 'closingAdjusted', 'openingAdjusted'].includes(field)) return 'formula-cell'
  return ''
}

function getRowClassName({ row }: { row: F3AdjudicationRow }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row-bg'
  if (row.rowKey === 'variance' && hasDifference.value) return 'variance-row'
  return ''
}

function confirmAdjudication() {
  publishAdjudicated()
  ElMessage.success('已确认审定并发布 EventBus(substantive:adjudicated)')
}
</script>

<template>
  <div class="f3-tab-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应付票据（科目2201）为贷方科目：期末未审 = 期初审定 + 本期贷方发生（开票承兑）- 本期借方发生（到期兑付）。</p>
        <p>2. 区分银行承兑汇票与商业承兑汇票分别列示；关注已到期未兑付票据是否转应付账款。</p>
        <p>3. 浅蓝背景为 F3-2 明细表自动取数，灰底虚线列为公式列（审定 = 未审 + 账项调整 + 重分类），不可手工编辑。</p>
        <p>4. 关联方开具/承兑的票据及保证金存款受限情况应在附注充分披露；差异≠0 时标红，确认审定后回写试算表。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：应付票据（2201）期末余额真实、完整、准确，银行/商业承兑分类恰当，审定数与试算平衡表核对一致。"
      class="objective-alert"
    />

    <el-alert v-if="detailCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ detailCrossValidation }}
    </el-alert>
    <el-alert v-if="hasDifference" type="error" :closable="false" class="cross-alert">
      审定合计与试算平衡表差异：{{ fmtAmount(differenceRow) }}元
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="confirmAdjudication">确认审定（回写TB）</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F3-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ dataRows.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="[...dataRows, ...footerRows]"
      border
      size="small"
      :row-class-name="getRowClassName"
      style="width: 100%"
    >
      <el-table-column prop="label" label="项目" min-width="140" fixed />

      <el-table-column label="期初" align="center">
        <el-table-column label="未审" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
              :model-value="row.openingUnadjusted"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowKey, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.openingAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowKey, 'openingAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.openingAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.openingRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowKey, 'openingRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.openingRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末" align="center">
        <el-table-column label="未审" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="getCellClass(row, 'closingUnadjusted')">{{ fmtAmount(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.closingAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowKey, 'closingAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.closingAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.closingRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowKey, 'closingRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.closingRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell audited-cell">{{ fmtAmount(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable && !isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateCell(row.rowKey, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目2201）：</span>
      <span>{{ fmtAmount(trialBalanceRow) }}</span>
      <el-tag v-if="hasDifference" type="danger" size="small">差异 {{ fmtAmount(differenceRow) }}</el-tag>
      <el-tag v-else type="success" size="small">核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式，比照 D4-1） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F3-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReviewDialog?.('F3-1-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明（应付票据构成、承兑类型、保证金存款受限、关联方票据等）..."
          :disabled="isReadonly"
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <el-button size="small" @click="openReviewDialog?.('F3-1-conclusion')">💬</el-button>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-adjudication {
  padding: 12px;
}
.f3-tab-adjudication :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.f3-tab-adjudication :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.cross-alert {
  margin-bottom: 8px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell {
  background: #f5f7fa;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.cross-sheet-cell {
  background: #ecf5ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.audited-cell {
  font-weight: 600;
}
:deep(.subtotal-row-bg td) {
  font-weight: 600;
  background: #fafafa !important;
}
:deep(.variance-row td) {
  color: #f56c6c;
  font-weight: 600;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin: 12px 0;
  font-size: 13px;
}
.tb-label {
  color: #909399;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
