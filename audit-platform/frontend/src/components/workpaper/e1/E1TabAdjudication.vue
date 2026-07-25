<script setup lang="ts">
/**
 * E1TabAdjudication.vue — E1-1 货币资金审定表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.1
 *
 * 渲染：
 * - 固定项目行矩阵 el-table（项目名称 | 期初未审数 | 期初账项调整 | 期初审定数 |
 *   期末未审数 | 期末账项调整 | 期末审定数 | 变动额 | 变动率 | 原因分析）
 * - 变动率>30% → 红色高亮
 * - 合计/试算平衡/差异行 → bold背景
 * - AI按钮生成原因分析
 * - el-skeleton加载占位
 *
 * Requirements: 1.1-1.7, 12.1-12.5
 */
import { ref, inject, toRef, onMounted, watch, type Ref } from 'vue'
import {
  useE1Adjudication,
  type UseE1BaseOptions,
  type AdjRow,
} from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  diffRow,
  isLoading,
  isRateExceeding,
  hasDifference,
  saveVarianceNote,
} = useE1Adjudication(options)

const wpIdRef = toRef(props, 'wpId') as Ref<string>
const { generateText, isGenerating } = useE1AiGenerate(wpIdRef)

// ─── AI Generation ───────────────────────────────────────────────────────────

async function handleAiGenerate(row: AdjRow): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: `e1-adjudication-variance-${row.itemKey}`,
    prompt: '根据该项目期初、期末审定数和变动情况，生成简洁、风险导向且可追溯的原因分析；超过30%的变动需说明主要驱动因素和已执行程序。',
    context: {
      项目: row.itemName,
      期初审定数: row.openingAudited,
      期末审定数: row.endingAudited,
      变动额: row.changeAmount,
      变动率: row.changeRate,
      当前说明: row.varianceNote,
    },
    existingContent: row.varianceNote,
    confirmTitle: '确认填入原因分析',
  })
  if (text) saveVarianceNote(row.itemKey, text)
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = 'E1-adj-audit-note'
const CONCLUSION_KEY = 'E1-adj-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const selectedConclusionTemplate = ref('')
const conclusionTemplates = [
  { value: 'A', label: 'A—核对一致', text: '经审计，货币资金在资产负债表日存在，应当记录的货币资金已完整、准确记录，审定数与试算平衡表核对一致。' },
  { value: 'B', label: 'B—调整后认可', text: '除已提请调整并经被审计单位处理的事项外，货币资金在资产负债表日存在，应当记录的货币资金已完整、准确记录，调整后审定数可以认定。' },
  { value: 'C', label: 'C—需进一步核查', text: '由于存在尚未解决的重大差异或审计证据受限，目前尚不能确认货币资金已完整、准确记录，需进一步执行审计程序并评价相关影响。' },
]

function hydrateNarratives(): void {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}
onMounted(hydrateNarratives)
watch(() => props.allResponses, hydrateNarratives)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}

function applyConclusionTemplate(code: string): void {
  const template = conclusionTemplates.find(item => item.value === code)
  if (template) saveAuditConclusion(template.text)
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-adjudication-note',
    prompt: '结合货币资金审定表各项目期初期末变动、应计利息分项及试算平衡表差异，生成专业审计说明，说明数据来源、核对程序、异常及处理。',
    context: { 审定表: rows.value, 试算平衡差异: diffRow.value.endingAudited },
    existingContent: auditNote.value,
    confirmTitle: '确认填入审计说明',
  })
  if (text) saveAuditNote(text)
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-adjudication-conclusion',
    prompt: '根据审定表核对结果、未解决差异和审计说明，生成审慎的审计结论；不得在存在未解决重大差异时给出无保留式结论。',
    context: { 是否存在差异: hasDifference(), 差异金额: diffRow.value.endingAudited, 审计说明: auditNote.value },
    existingContent: auditConclusion.value,
    confirmTitle: '确认填入审计结论',
  })
  if (text) saveAuditConclusion(text)
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtRate(rate: number | ''): string {
  if (rate === '' || rate === 0) return '-'
  return (rate * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: AdjRow }): string {
  const classes: string[] = []
  if (row.isSubtotal || row.itemKey === 'total' || row.itemKey === 'tb_amount' || row.itemKey === 'diff') {
    classes.push('e1-adj-subtotal-row')
  }
  if (isRateExceeding(row)) {
    classes.push('e1-adj-red-highlight')
  }
  if (row.itemKey === 'diff' && hasDifference()) {
    classes.push('e1-adj-red-highlight')
  }
  return classes.join(' ')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
// (hydration handled inside composable + audit note/conclusion onMounted above)
</script>

<template>
  <div class="e1-tab-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总货币资金各项目（库存现金1001、银行存款1002、其他货币资金1012、数字货币）的期初、期末审定过程。</p>
        <p>2. 审定数 = 未审数 + 账项调整；灰色底纹列（期初/期末审定数）为自动计算，不可手工录入。</p>
        <p>3. 未审数取自 E1-2 现金明细、E1-3 银行存款明细、E1-4 数字货币明细（跨sheet自动取数）；账项调整取自 E1-5 调整分录。</p>
        <p>4. 变动率超过30%的项目请在"原因分析"列说明；审定合计应与试算平衡表核对一致，差异≠0时须查明原因。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认货币资金在资产负债表日存在，应当记录的货币资金均已完整、准确记录，并与试算平衡表核对一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-20" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="12" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :row-class-name="getRowClass"
          style="width: 100%"
          max-height="680"
        >
          <!-- 项目名称 -->
          <el-table-column
            prop="itemName"
            label="项目名称"
            fixed="left"
            width="240"
          >
            <template #default="{ row }">
              <span :class="{ 'font-bold': row.isSubtotal || row.isReadonly }">
                {{ row.itemName }}
              </span>
              <div v-if="row.sourceWpCode" class="source-hint">
                <el-tag size="small" type="info" effect="plain">来自 {{ row.sourceWpCode }}</el-tag>
                <GtIndexChip :value="`wp:${row.sourceWpCode}`" :context-project-id="projectId" />
              </div>
            </template>
          </el-table-column>

          <!-- 期初未审数 -->
          <el-table-column label="期初未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期初账项调整 -->
          <el-table-column label="期初账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期初审定数 -->
          <el-table-column label="期初审定数" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.openingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 期末未审数 -->
          <el-table-column label="期末未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期末账项调整 -->
          <el-table-column label="期末账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期末审定数 -->
          <el-table-column label="期末审定数" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.endingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 变动额 -->
          <el-table-column label="变动额" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.changeAmount) }}
            </template>
          </el-table-column>

          <!-- 变动率 -->
          <el-table-column label="变动率" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'red-text': isRateExceeding(row) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="220" class-name="variance-note-col">
            <template #default="{ row }">
              <div v-if="['total', 'tb_amount'].includes(row.itemKey)" class="readonly-cell">
                {{ row.varianceNote || '-' }}
              </div>
              <div v-else class="note-cell">
                <el-input
                  type="textarea"
                  :model-value="row.varianceNote"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="填写原因分析"
                  @change="(val: string) => saveVarianceNote(row.itemKey, val)"
                />
                <el-button
                  v-if="!isReadonly"
                  :loading="isGenerating(`e1-adjudication-variance-${row.itemKey}`)"
                  size="small"
                  type="primary"
                  text
                  class="ai-btn"
                  @click="handleAiGenerate(row)"
                >
                  🤖
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 核对行 -->
        <div class="tb-check-row">
          <span class="tb-label">审定合计与试算平衡表核对（科目1001/1002/1012）：</span>
          <el-tag v-if="hasDifference()" type="danger" size="small">差异 {{ displayPrefs.fmtAmount(diffRow.endingAudited) }}</el-tag>
          <el-tag v-else type="success" size="small">核对一致</el-tag>
        </div>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                text
                :loading="isGenerating('e1-adjudication-note')"
                @click="generateAuditNote"
              >🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明..."
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
              <div class="conclusion-actions">
                <el-select
                  v-if="!isReadonly"
                  v-model="selectedConclusionTemplate"
                  size="small"
                  clearable
                  placeholder="套用结论模板"
                  style="width: 150px"
                  @change="applyConclusionTemplate"
                >
                  <el-option v-for="item in conclusionTemplates" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
                <el-button
                  v-if="!isReadonly"
                  size="small"
                  type="primary"
                  text
                  :loading="isGenerating('e1-adjudication-conclusion')"
                  @click="generateAuditConclusion"
                >🤖 AI辅助</el-button>
              </div>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论..."
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-adjudication {
  padding: 12px 0;
}
.e1-tab-adjudication :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-adjudication :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
/* 🔴 数值列(右对齐)防折行：金额一律单行显示；数值字号调小到 12px（比正文小1号，
   14 位数如 -18,241,563.19 在 130px 列内单行可容）+ 等宽数字对齐。文本列(原因分析)保持换行。 */
.e1-tab-adjudication :deep(.el-table td.is-right .cell) {
  white-space: nowrap !important;
  font-variant-numeric: tabular-nums;
  font-size: 12px !important;
}
/* 🔴 原因分析列字号统一 12px（含只读文本、textarea 输入、AI 按钮） */
.e1-tab-adjudication :deep(.el-table td.variance-note-col .cell),
.e1-tab-adjudication :deep(.el-table td.variance-note-col .cell .el-textarea__inner),
.e1-tab-adjudication :deep(.el-table td.variance-note-col .cell .readonly-cell),
.e1-tab-adjudication :deep(.el-table td.variance-note-col .cell .note-cell) {
  font-size: 12px !important;
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
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
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
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 12px;
  font-size: var(--wp-font-size, 13px);
}
.tb-label {
  color: #909399;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.red-text {
  color: #f56c6c;
  font-weight: 600;
}
.readonly-cell {
  color: #909399;
}
.note-cell {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.note-cell .el-textarea {
  flex: 1;
}
.ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}
.font-bold {
  font-weight: 700;
}
.source-hint { display: flex; align-items: center; gap: 4px; margin-top: 3px; }
.conclusion-actions { display: flex; align-items: center; gap: 8px; }

.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

:deep(.e1-adj-subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 700;
}
:deep(.e1-adj-red-highlight) {
  background-color: #fef0f0 !important;
}
:deep(.e1-adj-red-highlight td) {
  color: #f56c6c;
}
</style>
