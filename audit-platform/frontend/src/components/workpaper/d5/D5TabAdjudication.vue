<template>
<div class="d5-adjudication">
    <div class="import-export-bar">
      <el-button-group size="small">
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button :disabled="isReadonly">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>
    <!-- 审定表主体 -->
    <el-table
      :data="rows"
      size="small"
      border
      stripe
      @cell-contextmenu="onCellContextMenu"
    >
      <!-- 项目列 -->
      <el-table-column prop="label" label="项目" width="220" fixed>
        <template #default="{ row }">
          <span :class="rowLabelClass(row)">
            {{ row.label }}
            <el-tooltip
              v-if="row.rowKey === 'oci-change'"
              content="取自D5-4公允价值测算"
              placement="top"
            >
              <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
      </el-table-column>

      <!-- 期初未审 -->
      <el-table-column label="期初未审" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowKey, 'priorUnadjusted', val ?? 0)"
          />
          <span v-else :class="cellClass(row)">{{ fmtAmount(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- 期初AJE -->
      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- 期初RJE -->
      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <!-- 期初审定 -->
      <el-table-column label="期初审定" width="120" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 期末未审 -->
      <el-table-column label="期末未审" width="120" align="right">
        <template #default="{ row }">
          <span
            :class="cellClass(row)"
            :title="row.isFromCrossSheet ? '来源：D5-2明细表按类别聚合' : ''"
          >
            {{ fmtAmount(row.currentUnadjusted) }}
          </span>
        </template>
      </el-table-column>

      <!-- 期末AJE -->
      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.currentAje) }}</span>
        </template>
      </el-table-column>

      <!-- 期末RJE -->
      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.currentRje) }}</span>
        </template>
      </el-table-column>

      <!-- 期末审定 -->
      <el-table-column label="期末审定" width="120" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.currentAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 变动额 -->
      <el-table-column label="变动额" width="120" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 变动率 -->
      <el-table-column label="变动率" width="90" align="center">
        <template #default="{ row }">
          <span :class="{ 'rate-exceed': isRateExceeding(row.changeRate) }">
            {{ fmtRate(row.changeRate) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 试算平衡差异指示 -->
    <div class="tb-diff-row">
      <span>试算平衡表数：{{ fmtAmount(trialBalanceAmount) }}</span>
      <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        差异：{{ fmtAmount(trialBalanceDiff) }}
        <template v-if="trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 审计说明区域 -->
    <div class="audit-notes-section">
      <h4>
        审计说明
        <GtIndexChip wp-code="D5-4" label="→D5-4" />
        <GtIndexChip wp-code="D1-6" label="→D1-6" />
      </h4>
      <el-input
        v-model="auditNotes.explanation"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="分析应收款项融资本期变动原因，结合公允价值测算评价合理性..."
      />
      <div class="note-actions">
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genExplanation"
        >🤖AI</el-button>
      </div>
    </div>

    <!-- 审计结论区域 -->
    <div class="audit-conclusion-section">
      <h4>审计结论</h4>
      <el-input
        v-model="auditNotes.conclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="对应收款项融资审定结果的总结性结论..."
      />
      <div class="conclusion-actions">
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genConclusion"
        >🤖AI生成结论</el-button>
        <el-button size="small" @click="openReview('D5-adj-conclusion')">💬 复核</el-button>
      </div>
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabAdjudication.vue — D5-1 审定表
 *
 * el-table 固定7行结构 + 变动率>30%红色高亮 + 差异≠0红色高亮
 * "减:OCI变动"行浅蓝背景 + tooltip"取自D5-4公允价值测算"
 * 跨sheet自动取数单元格浅蓝色标记
 *
 * Task: 13.1
 * Requirements: 2.1-2.8, 3.4, 3.6, 3.7, 10.4-10.6
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { isChangeRateExceeding } from '../composables/useD5FormulaEngine'
import { useD5Adjudication } from '../composables/useD5Adjudication'
import { useD5AiGenerate } from '../composables/useD5AiGenerate'
import { useD5TabImportExport } from '../composables/useD5TabImportExport'
import type { useD5CrossSheet } from '../composables/useD5CrossSheet'
import type { ChecklistResponse } from '../composables/useD5FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD5CrossSheet>
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  trialBalanceAmount,
  trialBalanceDiff,
  auditNotes,
  updateCell,
} = useD5Adjudication({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD5AiGenerate(toRef(props, 'wpId'))

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { onExportTemplate, onExportData, onImportFile } = useD5TabImportExport(wpIdRef, 'D5-1')

async function genExplanation() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-change-analysis', auditNotes.value.explanation, {
    task: '应收款项融资本期变动分析',
    trialBalanceDiff: trialBalanceDiff.value,
  }, 'AI · 变动分析')
  if (text) auditNotes.value.explanation = text
}

async function genConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-conclusion', auditNotes.value.conclusion, {
    task: '应收款项融资审定审计结论',
    trialBalanceAmount: trialBalanceAmount.value,
    trialBalanceDiff: trialBalanceDiff.value,
  }, 'AI · 审计结论')
  if (text) auditNotes.value.conclusion = text
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceeding(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

function cellClass(row: any): Record<string, boolean> {
  return {
    'cross-sheet-cell': row.isFromCrossSheet,
    'computed-row': !row.isEditable,
    'oci-row': row.rowKey === 'oci-change',
  }
}

function rowLabelClass(row: any): Record<string, boolean> {
  return {
    'subtotal-label': row.rowKey === 'subtotal' || row.rowKey === 'fv-total',
    'oci-label': row.rowKey === 'oci-change',
    'diff-label': row.rowKey === 'difference',
  }
}

function onCellContextMenu(row: any, _col: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  openReviewDialog(`D5-adj-${row.rowKey}`)
}

function openReview(sectionId: string) {
  openReviewDialog(sectionId)
}
</script>

<style scoped>
.d5-adjudication {
  padding: 16px;
}

.import-export-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
}

.cross-sheet-cell {
  background: #ecf5ff;
  padding: 2px 6px;
  border-radius: 2px;
}

.computed-row {
  color: #909399;
}

.oci-row {
  background: #ecf5ff !important;
}

.subtotal-label {
  font-weight: 700;
}

.oci-label {
  color: #409eff;
  font-weight: 600;
}

.diff-label {
  font-weight: 600;
}

.rate-exceed {
  color: #f56c6c;
  font-weight: 600;
}

.diff-red {
  color: #f56c6c;
  font-weight: 600;
}

.tb-diff-row {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin: 16px 0;
  font-size: 13px;
}

.audit-notes-section,
.audit-conclusion-section {
  margin-top: 20px;
}

.audit-notes-section h4,
.audit-conclusion-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.note-actions,
.conclusion-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}


/* OCI行特殊浅蓝背景 */
:deep(.el-table__row) {
  &:nth-child(4) {
    background-color: #ecf5ff !important;
  }
}
</style>
