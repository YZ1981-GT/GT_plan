<script setup lang="ts">
/**
 * F3TabAdjudication — F3-1 审定表（贷方科目 2201）
 * Spec: .kiro/specs/f3-notes-payable/ Task 6.1
 * 比照 D4TabAdjudication
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
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应付票据为贷方科目(2201)：期末未审 = 期初审定 + 贷方发生 - 借方发生。</p>
        <p>2. 审定 = 未审 + 账项调整 + 重分类。浅蓝背景为 F3-2 自动取数。</p>
        <p>3. 差异≠0 时标红，确认审定后回写试算表。</p>
      </div>
    </details>

    <el-alert v-if="detailCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ detailCrossValidation }}
    </el-alert>
    <el-alert v-if="hasDifference" type="error" :closable="false" class="cross-alert">
      审定合计与试算平衡表差异：{{ fmtAmount(differenceRow) }}元
    </el-alert>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="confirmAdjudication">确认审定</el-button>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F3-2" :context-project-id="projectId" />
      </div>
    </div>

    <el-table
      :data="[...dataRows, ...footerRows]"
      border
      size="small"
      :row-class-name="getRowClassName"
      style="width: 100%; font-size: 13px"
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
        <el-table-column label="审定" min-width="110" align="right">
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
        <el-table-column label="审定" min-width="110" align="right">
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

    <el-card class="audit-card" shadow="never">
      <template #header>审计说明 / 结论</template>
      <el-input v-model="auditNote" type="textarea" :rows="3" :disabled="isReadonly" placeholder="审计说明" />
      <el-input v-model="auditConclusion" type="textarea" :rows="2" :disabled="isReadonly" placeholder="审计结论" style="margin-top:8px" />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-adjudication { font-size: 13px; }
.guidance-details { margin-bottom: 12px; font-size: 13px; }
.cross-alert { margin-bottom: 8px; }
.section-toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; }
.formula-cell { background: #f5f7fa; border-bottom: 1px dashed #c0c4cc; cursor: help; }
.cross-sheet-cell { background: #ecf5ff; }
.subtotal-row-bg :deep(td) { font-weight: 600; background: #fafafa; }
.variance-row :deep(td) { color: #f56c6c; font-weight: 600; }
.audit-card { margin-top: 16px; }
.toolbar-right { display: flex; gap: 8px; }
</style>
