<template>
<div class="d6-adjudication">
  <el-skeleton v-if="!blocks.length" :rows="8" animated />

  <template v-if="blocks.length">
    <!-- 编制提示 -->
    <details class="editing-hints">
      <summary>📋 编制提示</summary>
      <div class="hints-content">
        <p>本表为D6合同资产审定表，包含三个区块：一、合同资产原值；二、合同资产坏账准备；三、合同资产净值。</p>
        <p>区块一数据来源于D6-2明细表按合同类型聚合；区块二来源于D6-3减值准备明细按分类聚合。</p>
        <p>区块三=区块一-区块二（自动计算，不可编辑）。</p>
        <p>变动率超过30%的项目需重点关注并填写原因分析。差异≠0时需查明原因。</p>
      </div>
    </details>

    <!-- 交叉验证警告 -->
    <el-alert
      v-if="!netValueValidation.isValid"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:12px"
    >
      净值≠原值-坏账准备，差额：{{ fmtAmount(netValueValidation.diff) }}元
    </el-alert>

    <!-- 三区块审定表 -->
    <div v-for="(block, bIdx) in blocks" :key="block.blockKey" class="adjudication-block">
      <!-- 区块分割线 -->
      <div v-if="bIdx > 0" class="block-separator" />

      <!-- 区块标题 -->
      <h4 class="block-title">{{ block.blockTitle }}</h4>

      <el-table
        :data="getBlockDisplayRows(block)"
        size="small"
        border
        :row-class-name="({ row }: any) => adjRowClassName(row)"
        @cell-contextmenu="onCellContextMenu"
      >
        <!-- 项目 -->
        <el-table-column prop="label" label="项目" width="260" fixed>
          <template #default="{ row }">
            <span :class="labelClass(row)">
              {{ row.label }}
              <el-tooltip v-if="row.isFromCrossSheet" content="跨sheet自动取数" placement="top">
                <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
        </el-table-column>

        <!-- 期初未审 -->
        <el-table-column label="期初未审" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.priorUnadjusted"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'priorUnadjusted', v ?? 0)"
            />
            <span v-else :class="amtCellClass(row)">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- 期初AJE -->
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.priorAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'priorAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>

        <!-- 期初RJE -->
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.priorRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'priorRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>

        <!-- 期初审定 -->
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>

        <!-- 期末未审 -->
        <el-table-column label="期末未审" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.currentUnadjusted"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'currentUnadjusted', v ?? 0)"
            />
            <span v-else :class="amtCellClass(row)">{{ fmtAmount(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- 期末AJE -->
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.currentAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'currentAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.currentAje) }}</span>
          </template>
        </el-table-column>

        <!-- 期末RJE -->
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && row.rowType === 'dynamic'"
              :model-value="row.currentRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(block.blockKey, row.rowKey, 'currentRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.currentRje) }}</span>
          </template>
        </el-table-column>

        <!-- 期末审定 -->
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span class="auto-calc">{{ fmtAmount(row.currentAudited) }}</span>
          </template>
        </el-table-column>

        <!-- 变动额 -->
        <el-table-column label="变动额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-red': row.changeAmount !== 0 }">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 变动率 -->
        <el-table-column label="变动率" width="90" align="center">
          <template #default="{ row }">
            <span :class="{ 'rate-exceed': isRateExceed(row.changeRate) }">{{ fmtPercent(row.changeRate) }}</span>
          </template>
        </el-table-column>

        <!-- 原因分析 -->
        <el-table-column label="原因分析" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !isReadonly"
              :model-value="row.reasonAnalysis"
              size="small"
              @change="(v: string) => updateCell(block.blockKey, row.rowKey, 'reasonAnalysis', v)"
            />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column v-if="block.blockKey !== 'block3' && !isReadonly" label="" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.rowType === 'dynamic'"
              type="danger"
              text
              size="small"
              @click="removeDynamicRow(block.blockKey, row.rowKey)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 添加行按钮 -->
      <el-button
        v-if="block.blockKey !== 'block3' && !isReadonly"
        size="small"
        style="margin-top:8px"
        @click="addDynamicRow(block.blockKey)"
      >添加行</el-button>
    </div>

    <!-- 区块三底部：TB数 + 差异 -->
    <div class="tb-diff-section">
      <div class="tb-row">
        <span>试算平衡表数（科目1402）：</span>
        <span class="tb-amount">{{ fmtAmount(trialBalanceAmount) }}</span>
      </div>
      <div class="tb-row" :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        <span>差异：</span>
        <span>{{ fmtAmount(trialBalanceDiff) }}</span>
        <span v-if="trialBalanceDiff === 0" class="check-mark"> ✓</span>
        <span v-else class="cross-mark"> ✗</span>
      </div>
    </div>

    <!-- 审计说明区域 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>

      <div class="note-item">
        <label>变动分析：</label>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析合同资产本期变动原因..."
        />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genExplanation">🤖AI</el-button>
          <el-button size="small" @click="openReview('D6-1-note-explanation')">💬复核</el-button>
        </div>
      </div>

      <div class="note-item">
        <label>计提充分性评价：<GtIndexChip wp-code="D6-8" label="→D6-8" /></label>
        <el-input
          v-model="auditNotes.impairmentEval"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="结合D6-8 ECL测算结果评价坏账计提充分性..."
        />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genImpairmentEval">🤖AI</el-button>
          <el-button size="small" @click="openReview('D6-1-note-impairmentEval')">💬复核</el-button>
        </div>
      </div>

      <div class="note-item">
        <label>长期挂账分析：<GtIndexChip wp-code="D6-6" label="→D6-6" /></label>
        <el-input
          v-model="auditNotes.longTermReason"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析长期挂账合同资产的原因及期后结转情况..."
        />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genLongTermReason">🤖AI</el-button>
          <el-button size="small" @click="openReview('D6-1-note-longTermReason')">💬复核</el-button>
        </div>
      </div>
    </div>

    <!-- 审计结论 -->
    <div class="audit-conclusion-section">
      <h4>审计结论</h4>
      <el-input
        v-model="auditNotes.conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对合同资产审定结果的总结性结论..."
      />
      <div class="note-actions">
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genConclusion">🤖AI</el-button>
        <el-button size="small" @click="openReview('D6-1-note-conclusion')">💬复核</el-button>
      </div>
    </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabAdjudication.vue — 审定表 D6-1（三区块177公式）
 *
 * 三区块固定结构：一、原值 / 二、坏账准备 / 三、净值
 * 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
 * "减：列示于其他非流动资产"行浅蓝色背景 + tooltip
 * 跨sheet取数单元格浅蓝色标记 + tooltip
 * 变动率>30%红色高亮 + 差异≠0红色高亮
 * 交叉验证：净值小计≠原值小计-坏账小计时黄色警告
 *
 * Task: 16.1
 * Requirements: 2.1-2.10, 4.1-4.7, 26.1-26.6
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { useD6Adjudication, type AdjudicationBlock, type AdjudicationRow } from '../composables/useD6Adjudication'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { isChangeRateExceeding } from '../composables/useD6FormulaEngine'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'

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
  crossSheet: ReturnType<typeof useD6CrossSheet>
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  blocks,
  trialBalanceAmount,
  trialBalanceDiff,
  netValueValidation,
  auditNotes,
  updateCell,
  addDynamicRow,
  removeDynamicRow,
} = useD6Adjudication({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

async function genExplanation() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-change-analysis', auditNotes.value.explanation, {
    task: '合同资产本期变动分析',
    trialBalanceDiff: trialBalanceDiff.value,
    netValueValidationDiff: netValueValidation.value.diff,
  }, 'AI · 变动分析')
  if (text) auditNotes.value.explanation = text
}

async function genImpairmentEval() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('ecl-note', auditNotes.value.impairmentEval, {
    task: '合同资产坏账计提充分性评价',
    trialBalanceAmount: trialBalanceAmount.value,
  }, 'AI · 计提充分性评价')
  if (text) auditNotes.value.impairmentEval = text
}

async function genLongTermReason() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-aging-reason', auditNotes.value.longTermReason, {
    task: '长期挂账合同资产原因分析',
  }, 'AI · 长期挂账分析')
  if (text) auditNotes.value.longTermReason = text
}

async function genConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-conclusion', auditNotes.value.conclusion, {
    task: '合同资产审定审计结论',
    trialBalanceAmount: trialBalanceAmount.value,
    trialBalanceDiff: trialBalanceDiff.value,
  }, 'AI · 审计结论')
  if (text) auditNotes.value.conclusion = text
}

// ─── Display Helpers ─────────────────────────────────────────────────────────

function getBlockDisplayRows(block: AdjudicationBlock): AdjudicationRow[] {
  return [...block.rows, block.subtotalRow, block.deductionRow, block.blockTotalRow]
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceed(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

function labelClass(row: AdjudicationRow): Record<string, boolean> {
  return {
    'label-bold': row.rowType === 'subtotal' || row.rowType === 'block_total',
    'label-deduction': row.isDeduction,
  }
}

function amtCellClass(row: AdjudicationRow): Record<string, boolean> {
  return { 'cross-sheet-cell': row.isFromCrossSheet }
}

function adjRowClassName({ row }: { row: AdjudicationRow }): string {
  if (row.isDeduction) return 'deduction-row'
  if (row.rowType === 'block_total') return 'block-total-row'
  return ''
}

function onCellContextMenu(row: AdjudicationRow, _col: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  openReviewDialog(`D6-1-adj-${row.rowKey}`)
}

function openReview(sectionId: string) {
  openReviewDialog(sectionId)
}
</script>

<style scoped>
.d6-adjudication {
  padding: 16px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.editing-hints {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}

.editing-hints summary {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}

.hints-content {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.hints-content p { margin: 0 0 4px; }

.adjudication-block { margin-bottom: 8px; }

.block-separator {
  height: 2px;
  background: #303133;
  margin: 16px 0;
}

.block-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 8px;
  color: #303133;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}

.cross-sheet-cell {
  background: #ecf5ff;
  padding: 2px 6px;
  border-radius: 2px;
}

.label-bold { font-weight: 700; }
.label-deduction { color: #409eff; }

.rate-exceed { color: #f56c6c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 600; }

:deep(.deduction-row) { background-color: #ecf5ff !important; }
:deep(.block-total-row) { background-color: #fafafa !important; font-weight: 600; }

.tb-diff-section {
  margin: 16px 0;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  gap: 32px;
  font-size: 13px;
}

.tb-row { display: flex; align-items: center; gap: 4px; }
.tb-amount { font-weight: 600; }
.check-mark { color: #67c23a; }
.cross-mark { color: #f56c6c; }

.audit-notes-section, .audit-conclusion-section { margin-top: 20px; }
.audit-notes-section h4, .audit-conclusion-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.note-item { margin-bottom: 16px; }
.note-item label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
</style>
