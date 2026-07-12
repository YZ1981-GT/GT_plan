<template>
<div class="d5-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表反映应收款项融资（科目1124）的审定过程，该科目以公允价值计量且其变动计入其他综合收益（FVOCI）。</p>
        <p>2. "期末未审"列取自 D5-2 明细表按类别聚合，"减：OCI变动"行取自 D5-4 公允价值测算，浅蓝背景单元格为跨sheet自动取数，不可手工编辑。</p>
        <p>3. 灰色底纹列为自动计算列（期初/期末审定数），不可手动录入。</p>
        <p>4. 变动率超过30%的项目请在审计说明中解释原因；审定完成后应与试算平衡表核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认应收款项融资期末余额的存在、完整与准确，评价公允价值计量及其变动计入其他综合收益（OCI）的恰当性，并与试算平衡表核对一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="onExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D5-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:D1-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
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
      <el-table-column label="期初审定" width="120" align="right" class-name="auto-calc-col">
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
      <el-table-column label="期末审定" width="120" align="right" class-name="auto-calc-col">
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

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目1124）：</span>
      <span>{{ fmtAmount(trialBalanceAmount) }}</span>
      <el-tag v-if="trialBalanceDiff !== 0" type="danger" size="small" class="diff-tag">差异 {{ fmtAmount(trialBalanceDiff) }}</el-tag>
      <el-tag v-else type="success" size="small" class="diff-tag">核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D5-4" :context-project-id="projectId" />
            <GtIndexChip value="wp:D1-6" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genExplanation">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D5-adj-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析应收款项融资本期变动原因，结合公允价值测算评价合理性..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D5-adj-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 7 }"
          :disabled="isReadonly"
          placeholder="对应收款项融资审定结果的总结性结论..."
        />
      </div>
    </el-card>
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
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD5CrossSheet>
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

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
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD5AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

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
  padding: 12px;
}
.d5-adjudication :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d5-adjudication :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
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

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #606266;
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

/* 核对行 */
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin: 16px 0;
  font-size: var(--wp-font-size, 13px);
}
.tb-label {
  color: #909399;
}
.diff-tag {
  margin-left: 8px;
}

/* 审计意见卡片 */
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

/* OCI行特殊浅蓝背景 */
:deep(.el-table__row) {
  &:nth-child(4) {
    background-color: #ecf5ff !important;
  }
}
</style>
