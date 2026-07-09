<script setup lang="ts">
/**
 * D1TabAdjudication.vue — 审定表D1-1 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 8.1
 *
 * 渲染三区块 el-table（原值/坏账/净值），每区块含明细行+小计行。
 * 跨sheet自动取数浅蓝色背景 + 变动率>30%红色高亮 + 试算平衡表差异。
 * 审计说明/结论区域 + AI生成 + 复核对话入口。
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useD1Adjudication,
  type AdjudicationDetailRow,
  type AdjudicationSection,
} from '../composables/useD1Adjudication'
import { isChangeRateExceeding } from '../composables/useD1FormulaEngine'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((params: { sectionId: string; sectionLabel: string; relatedData?: Record<string, unknown> }) => void) | null>('openReviewDialog', null)
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-1')

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  adjudicationSections,
  crossSheetStatus,
  trialBalanceDiff,
  auditNote,
  auditConclusion,
  autoChangeDescription,
  updateCell,
  saveAuditNote,
  saveAuditConclusion,
  aiGenerateNote,
  aiGenerateConclusion,
} = useD1Adjudication({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  loadSubWorkpaperData: async () => ({}),
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  openReviewDialog: openReviewDialog ?? undefined,
})

// ─── Loading & Active Threads ────────────────────────────────────────────────

const loading = ref(true)
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

onMounted(() => {
  loading.value = false
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

function fmtRate(rate: number | ''): string {
  if (rate === '') return '-'
  return (rate * 100).toFixed(2) + '%'
}

function isRateExceeding(rate: number | ''): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getAllRows(section: AdjudicationSection): AdjudicationDetailRow[] {
  return [...section.rows, section.subtotalRow]
}

function getRowClass({ row }: { row: AdjudicationDetailRow }): string {
  if (!row.isEditable) return 'is-summary'
  return ''
}

function getCellClass(row: AdjudicationDetailRow, field: string): string {
  const classes: string[] = []
  if (row.isFromCrossSheet && ['priorUnadjusted', 'currentUnadjusted'].includes(field)) {
    classes.push('cross-sheet-cell')
  }
  if (field === 'changeRate' && isRateExceeding(row.changeRate)) {
    classes.push('rate-warning')
  }
  return classes.join(' ')
}

function getCrossSheetTooltip(row: AdjudicationDetailRow): string {
  if (!row.isFromCrossSheet) return ''
  if (row.rowKey.startsWith('gross-')) return `取自D1-2 ${row.label}行`
  if (row.rowKey.startsWith('bd-')) return `取自D1-4 坏账准备${row.label}行`
  if (row.rowKey.startsWith('net-')) return '自动计算: 原值 - 坏账准备'
  return ''
}

// ─── Context Menu ────────────────────────────────────────────────────────────

function handleCellContextMenu(row: AdjudicationDetailRow, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  openReviewDialog({
    sectionId: `D1-adj-${row.rowKey}-${field}`,
    sectionLabel: `D1-1 审定表 ${row.label} - ${column?.label || field}`,
    relatedData: { rowKey: row.rowKey, field, value: (row as any)[field] },
  })
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiNote() {
  aiNoteLoading.value = true
  try {
    const text = await aiGenerateNote()
    if (text) {
      saveAuditNote(text)
      ElMessage.success('AI已生成审计说明')
    }
  } catch { ElMessage.warning('AI生成失败，请重试') }
  finally { aiNoteLoading.value = false }
}

async function handleAiConclusion() {
  aiConclusionLoading.value = true
  try {
    const text = await aiGenerateConclusion()
    if (text) {
      saveAuditConclusion(text)
      ElMessage.success('AI已生成审计结论')
    }
  } catch { ElMessage.warning('AI生成失败，请重试') }
  finally { aiConclusionLoading.value = false }
}

</script>

<template>
  <div class="d1-tab-adjudication">
    <div class="tab-header">
      <h4>审定表 D1-1</h4>
      <div class="toolbar-right">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>
    <!-- Loading skeleton -->
    <el-skeleton v-if="loading" :rows="12" animated />

    <template v-else>
      <!-- 三区块审定表 -->
      <div v-for="section in adjudicationSections" :key="section.sectionKey" class="section-block">
        <h4 class="section-title">{{ section.sectionLabel }}</h4>
        <el-table
          :data="getAllRows(section)"
          border
          size="small"
          :row-class-name="getRowClass"
          @cell-contextmenu="handleCellContextMenu"
        >
          <el-table-column label="项目" prop="label" width="140" fixed>
            <template #default="{ row }">
              {{ row.label }}
              <GtReviewDot v-if="row.rowKey" row-prefix="D1-adj" :row-key="row.rowKey" />
            </template>
          </el-table-column>

          <!-- 期初 -->
          <el-table-column label="期初未审" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.isFromCrossSheet" :content="getCrossSheetTooltip(row)" placement="top">
                <span :class="getCellClass(row, 'priorUnadjusted')" v-html="fmtAmount(row.priorUnadjusted)" />
              </el-tooltip>
              <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
            </template>
          </el-table-column>
          <el-table-column label="期初AJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.priorAje"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number) => updateCell(row.rowKey, 'prior-aje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.priorAje)" />
            </template>
          </el-table-column>
          <el-table-column label="期初RJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.priorRje"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number) => updateCell(row.rowKey, 'prior-rje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.priorRje)" />
            </template>
          </el-table-column>
          <el-table-column label="期初审定" width="110" align="right">
            <template #default="{ row }">
              <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
            </template>
          </el-table-column>

          <!-- 期末 -->
          <el-table-column label="期末未审" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.isFromCrossSheet" :content="getCrossSheetTooltip(row)" placement="top">
                <span :class="getCellClass(row, 'currentUnadjusted')" v-html="fmtAmount(row.currentUnadjusted)" />
              </el-tooltip>
              <el-input-number
                v-else-if="row.isEditable && !isReadonly"
                :model-value="row.currentUnadjusted"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number) => updateCell(row.rowKey, 'current-unadj', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentUnadjusted)" />
            </template>
          </el-table-column>
          <el-table-column label="期末AJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentAje"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number) => updateCell(row.rowKey, 'current-aje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentAje)" />
            </template>
          </el-table-column>
          <el-table-column label="期末RJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentRje"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number) => updateCell(row.rowKey, 'current-rje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentRje)" />
            </template>
          </el-table-column>
          <el-table-column label="期末审定" width="110" align="right">
            <template #default="{ row }">
              <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
            </template>
          </el-table-column>

          <!-- 变动 -->
          <el-table-column label="增减变动额" width="120" align="right">
            <template #default="{ row }">
              <span v-html="fmtAmount(row.change)" />
            </template>
          </el-table-column>
          <el-table-column label="增减比例" width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'rate-warning': isRateExceeding(row.changeRate) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="原因分析" min-width="140">
            <template #default="{ row }">
              <el-input
                v-if="row.isEditable && !isReadonly"
                :model-value="row.reasonAnalysis"
                size="small"
                @change="(v: string) => updateCell(row.rowKey, 'reason', v as any)"
              />
              <span v-else>{{ row.reasonAnalysis || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 试算平衡表 -->
      <div class="trial-balance-section">
        <h4 class="section-title">试算平衡表核对</h4>
        <div class="tb-row">
          <span class="tb-label">试算平衡表数:</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="trialBalanceDiff.tbAmount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell('tb', 'amount', v || 0)"
          />
          <span v-else v-html="fmtAmount(trialBalanceDiff.tbAmount)" />
        </div>
        <div class="tb-row">
          <span class="tb-label">审定表审定数:</span>
          <span style="font-weight: 600" v-html="fmtAmount(trialBalanceDiff.auditedAmount)" />
        </div>
        <div class="tb-row" :class="{ 'diff-warning': trialBalanceDiff.diff !== 0 }">
          <span class="tb-label">差异:</span>
          <span v-html="fmtAmount(trialBalanceDiff.diff)" />
          <el-tag v-if="trialBalanceDiff.diff === 0" type="success" size="small" style="margin-left:8px">✓ 一致</el-tag>
          <el-tag v-else type="danger" size="small" style="margin-left:8px">✗ 存在差异</el-tag>
        </div>
      </div>

      <!-- 1.审计说明 -->
      <div class="audit-note-section">
        <h4 class="section-title">1.审计说明</h4>
        <p class="auto-description">{{ autoChangeDescription }}</p>
        <div class="note-area">
          <span class="red-label">主要原因（比例超过30%的）：</span>
          <div class="note-input-row">
            <el-input
              v-model="auditNote"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="请输入审计说明..."
              @change="saveAuditNote(auditNote)"
            />
            <div class="note-actions">
              <el-button size="small" :loading="aiNoteLoading" :disabled="isReadonly" @click="handleAiNote">🤖AI</el-button>
              <GtReviewTrigger section-id="D1-adj-audit-note" />
            </div>
          </div>
        </div>
      </div>

      <!-- 2.审计结论 -->
      <div class="audit-conclusion-section">
        <h4 class="section-title">2.审计结论</h4>
        <div class="note-input-row">
          <el-input
            v-model="auditConclusion"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="请输入审计结论..."
            @change="saveAuditConclusion(auditConclusion)"
          />
          <div class="note-actions">
            <el-button size="small" :loading="aiConclusionLoading" :disabled="isReadonly" @click="handleAiConclusion">🤖AI</el-button>
            <GtReviewTrigger section-id="D1-adj-audit-conclusion" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-adjudication {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.section-block {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #303133;
}

/* 小计行/净值行不可编辑样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 跨sheet自动取数单元格浅蓝色背景 */
.cross-sheet-cell {
  background-color: #ecf5ff;
  padding: 2px 4px;
  border-radius: 2px;
}

/* 变动率>30%红色高亮 */
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 试算平衡表 */
.trial-balance-section {
  margin: 20px 0;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.tb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 13px;
}

.tb-label {
  width: 120px;
  color: #606266;
}

.diff-warning {
  color: #f56c6c;
  font-weight: 600;
}

/* 审计说明/结论 */
.audit-note-section,
.audit-conclusion-section {
  margin: 20px 0;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.auto-description {
  font-size: 13px;
  color: #606266;
  margin: 0 0 8px 0;
}

.red-label {
  color: #f56c6c;
  font-weight: 600;
  font-size: 13px;
}

.note-area {
  margin-top: 8px;
}

.note-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 6px;
}

.note-input-row .el-textarea {
  flex: 1;
}

.note-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

</style>
