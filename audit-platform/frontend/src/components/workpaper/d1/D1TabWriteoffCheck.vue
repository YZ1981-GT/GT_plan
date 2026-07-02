<script setup lang="ts">
/**
 * D1TabWriteoffCheck.vue — D1-16 坏账准备转回/核销检查表
 *
 * Spec: .kiro/specs/d1-writeoff-check/
 * Task: 3.1, 3.2, 3.3, 3.4
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - Section 1: 转回检查表（8列 el-table + 动态行 + SUM合计 + 核对区 + E>F预警）
 * - Section 2: 核销检查表（5列 el-table + 动态行 + SUM合计 + 核对区 + ECL预警）
 * - Section 3: 审计说明（textarea + 🤖AI + 💬复核）
 * - Section 4: 审计结论（textarea + 🤖AI + 💬复核 + 编制提示折叠）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 1.1-1.5, 2.1-2.6, 3.1-3.4, 4.1-4.5, 5.1-5.6, 6.1-6.4,
 *              7.1-7.5, 8.1-8.6, 9.1, 9.4, 12.1-12.7
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useD1WriteoffCheck,
  RECOVERY_METHODS,
  NOTE_NATURES,
  type ReversalRow,
  type WriteoffRow,
} from '../composables/useD1WriteoffCheck'
import { formatNegativeAmount } from '../composables/d1InspectionFormulas'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  displayPrefs: any
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const injectedDisplayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Dual Mode (HTML ↔ OnlyOffice) ──────────────────────────────────────────

const editorMode = ref<'html' | 'oo'>('html')
const ooHealthy = ref(true)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
])

const isOOMode = computed(() => editorMode.value === 'oo')
const ooSheetName = computed(() => props.sheetName || '坏账准备转回核销检查D1-16')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  reversalRows,
  addReversalRow,
  removeReversalRow,
  updateReversalRow,
  reversalTotalE,
  reversalTotalF,
  writeoffRows,
  addWriteoffRow,
  removeWriteoffRow,
  updateWriteoffRow,
  writeoffTotalC,
  d14ReversalTotal,
  d14WriteoffTotal,
  eclCurrentTotal,
  reversalDiff,
  writeoffDiff,
  reversalExceedsProvision,
  writeoffExceedsProvision,
  missingReversalFields,
  missingWriteoffFields,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
  isLoading,
  syncReversalToD14,
  syncWriteoffToD14,
} = useD1WriteoffCheck({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  saveDebouncedText: (item: ChecklistItem) => {
    http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items: [item] })
      .catch(() => { /* silent */ })
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return formatNegativeAmount(val)
  return injectedDisplayPrefs.fmtAmount(val)
}

function fmtAmountHtml(val: number): string {
  if (val === 0) return '-'
  if (val < 0) {
    const formatted = formatNegativeAmount(val)
    return `<span class="negative-amount">${formatted}</span>`
  }
  return injectedDisplayPrefs.fmtAmount(val)
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// ─── P1: 同步到D1-4 ─────────────────────────────────────────────────────────

async function onSyncReversalToD14() {
  try {
    await ElMessageBox.confirm(
      '将以本表合计覆盖D1-4坏账明细表的转回变动列，是否继续？',
      '同步确认',
      { confirmButtonText: '同步', cancelButtonText: '取消', type: 'warning' },
    )
    syncReversalToD14()
    ElMessage.success('已同步到D1-4')
  } catch { /* 用户取消 */ }
}

async function onSyncWriteoffToD14() {
  try {
    await ElMessageBox.confirm(
      '将以本表合计覆盖D1-4坏账明细表的核销变动列，是否继续？',
      '同步确认',
      { confirmButtonText: '同步', cancelButtonText: '取消', type: 'warning' },
    )
    syncWriteoffToD14()
    ElMessage.success('已同步到D1-4')
  } catch { /* 用户取消 */ }
}

// ─── P1: AI辅助生成 ─────────────────────────────────────────────────────────

const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)
const aiAvailable = ref(true)

onMounted(async () => {
  // AI 可用性检测（复用a171端点存在性即可，不额外检查LLM）
  try {
    await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
  } catch { /* AI可用性不影响主流程 */ }
})

function buildWriteoffContext(): string {
  const lines: string[] = []
  lines.push(`【D1-16 坏账准备转回/核销检查表数据摘要】`)
  lines.push(`转回笔数: ${reversalRows.value.length}`)
  lines.push(`转回金额合计: ${reversalTotalE.value}`)
  lines.push(`核销笔数: ${writeoffRows.value.length}`)
  lines.push(`核销金额合计: ${writeoffTotalC.value}`)
  lines.push(`与D1-4转回差异: ${reversalDiff.value !== null ? reversalDiff.value : '未加载'}`)
  lines.push(`与D1-4核销差异: ${writeoffDiff.value !== null ? writeoffDiff.value : '未加载'}`)
  lines.push(`核销是否超计提: ${writeoffExceedsProvision.value ? '是' : '否'}`)

  // 检查是否有E>F异常行
  const exceedsRows = reversalRows.value.filter(r => r.reversalAmount > 0 && r.reversalAmount > r.priorProvisionAmount)
  if (exceedsRows.length > 0) {
    lines.push(`转回超原计提行数: ${exceedsRows.length}`)
  }

  return lines.join('\n')
}

async function generateAuditNoteWithAI() {
  aiLoadingNote.value = true
  try {
    const context = buildWriteoffContext()
    const res = await http.post(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 16,
      chapter_title: 'D1-16 坏账准备转回/核销检查表-审计说明',
      guidance: '根据转回和核销检查数据，生成审计说明。包括：转回/核销笔数和金额、与D1-4核对结果、是否存在异常（转回超原计提、核销超计提）、需关注事项。',
      existing_content: context,
      knowledge_doc_ids: [],
    }, { _silent: true } as any)

    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI未生成内容'); return }

    await ElMessageBox.confirm(
      `AI生成的内容：\n\n${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`,
      'AI辅助生成',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    saveAuditNote(text)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('AI生成失败，请检查LLM服务是否可用')
    }
  } finally { aiLoadingNote.value = false }
}

async function generateAuditConclusionWithAI() {
  aiLoadingConclusion.value = true
  try {
    const context = buildWriteoffContext() + `\n【审计说明】${auditNote.value || '（未填写）'}`
    const res = await http.post(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 16,
      chapter_title: 'D1-16 坏账准备转回/核销检查表-审计结论',
      guidance: '根据审计说明和校验结果，生成审计结论。结论应明确表述：转回是否合理/核销程序是否完整/与D1-4是否一致/是否需要调整。',
      existing_content: context,
      knowledge_doc_ids: [],
    }, { _silent: true } as any)

    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI未生成内容'); return }

    await ElMessageBox.confirm(
      `AI生成的内容：\n\n${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`,
      'AI辅助生成',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    saveAuditConclusion(text)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('AI生成失败，请检查LLM服务是否可用')
    }
  } finally { aiLoadingConclusion.value = false }
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '坏账准备转回条件（CAS 22）：以前减记的金额后续恢复时转回，转回金额不超过原计提坏账准备的账面余额。',
  '核销审批程序要求：核销金额超过一定标准需经股东大会批准；中等金额经董事会批准；较小金额经总经理办公会审批。',
  '关联方核销的额外披露要求：涉及关联方的坏账核销，需在报表附注中单独披露关联方名称、关系、核销金额及原因。',
  '转回/核销对损益影响的分析要点：转回计入资产减值损失（收益方向），核销不影响损益但减少坏账准备余额，需关注对利润表的综合影响。',
]

</script>

<template>
  <div class="d1-tab-writeoff-check">
    <!-- Mode Switcher -->
    <div class="mode-switcher">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tooltip v-if="!ooHealthy" content="OnlyOffice服务不可用" placement="top">
        <span class="oo-disabled-hint">⚠️</span>
      </el-tooltip>
    </div>

    <!-- Loading skeleton -->
    <el-skeleton v-if="isLoading" :rows="8" animated />

    <!-- OnlyOffice mode -->
    <GtOnlyOfficeSheet
      v-if="isOOMode"
      :wp-id="wpId"
      :sheet-name="ooSheetName"
      :project-id="projectId"
    />

    <!-- HTML Structured mode -->
    <template v-if="!isOOMode && !isLoading">
      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <!-- Section 1: 转回检查 -->
      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <section class="reversal-section">
        <h3 class="section-heading">(一)本期重要的坏账准备转回检查</h3>
        <div class="section-stat">
          共{{ reversalRows.length }}笔转回，合计金额{{ fmtAmount(reversalTotalE) }}元
        </div>

        <!-- 8列转回表格 -->
        <el-table
          :data="reversalRows"
          border
          size="small"
          max-height="420"
          class="writeoff-table"
          style="width: 100%"
        >
          <!-- A: 单位名称 -->
          <el-table-column label="单位名称" width="150">
            <template #default="{ row }: { row: ReversalRow }">
              <el-input
                :model-value="row.unitName"
                size="small"
                placeholder="单位名称"
                :disabled="isReadonly"
                @change="(v: string) => updateReversalRow(row.id, 'unitName', v || '')"
              />
            </template>
          </el-table-column>

          <!-- B: 转回原因 -->
          <el-table-column label="转回原因" min-width="120">
            <template #default="{ row }: { row: ReversalRow }">
              <div class="cell-with-star">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.reason"
                  placeholder="转回原因..."
                  :disabled="isReadonly"
                  @change="(v: string) => updateReversalRow(row.id, 'reason', v || '')"
                />
                <span
                  v-if="row.reversalAmount > 0 && !row.reason.trim()"
                  class="required-star"
                >*</span>
              </div>
            </template>
          </el-table-column>

          <!-- C: 收回方式 -->
          <el-table-column label="收回方式" width="100">
            <template #default="{ row }: { row: ReversalRow }">
              <el-select
                :model-value="row.recoveryMethod"
                placeholder="选择"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateReversalRow(row.id, 'recoveryMethod', v || '')"
              >
                <el-option v-for="o in RECOVERY_METHODS" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>

          <!-- D: 原依据 -->
          <el-table-column label="原依据" min-width="120">
            <template #default="{ row }: { row: ReversalRow }">
              <el-input
                type="textarea"
                :rows="2"
                :model-value="row.originalBasis"
                placeholder="原确定坏账准备的依据..."
                :disabled="isReadonly"
                @change="(v: string) => updateReversalRow(row.id, 'originalBasis', v || '')"
              />
            </template>
          </el-table-column>

          <!-- E: 转回金额 -->
          <el-table-column label="转回金额" width="110" align="right">
            <template #default="{ row }: { row: ReversalRow }">
              <el-tooltip
                v-if="reversalExceedsProvision(row)"
                content="转回金额超过原计提金额，请核实"
                placement="top"
              >
                <el-input-number
                  :model-value="row.reversalAmount"
                  size="small"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  class="exceeds-provision"
                  style="width: 100%"
                  @change="(v: number) => updateReversalRow(row.id, 'reversalAmount', v || 0)"
                />
              </el-tooltip>
              <el-input-number
                v-else
                :model-value="row.reversalAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateReversalRow(row.id, 'reversalAmount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- F: 原计提 -->
          <el-table-column label="原计提" width="110" align="right">
            <template #default="{ row }: { row: ReversalRow }">
              <el-input-number
                :model-value="row.priorProvisionAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateReversalRow(row.id, 'priorProvisionAmount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- G: 合理性分析 -->
          <el-table-column label="合理性分析" min-width="120">
            <template #default="{ row }: { row: ReversalRow }">
              <div class="cell-with-star">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.reasonabilityAnalysis"
                  placeholder="合理性分析..."
                  :disabled="isReadonly"
                  @change="(v: string) => updateReversalRow(row.id, 'reasonabilityAnalysis', v || '')"
                />
                <span
                  v-if="row.reversalAmount > 0 && !row.reasonabilityAnalysis.trim()"
                  class="required-star"
                >*</span>
              </div>
            </template>
          </el-table-column>

          <!-- H: 索引号 -->
          <el-table-column label="索引号" width="80">
            <template #default="{ row }: { row: ReversalRow }">
              <div class="index-cell">
                <el-input
                  :model-value="row.indexRef"
                  size="small"
                  placeholder="索引号"
                  :disabled="isReadonly"
                  @change="(v: string) => updateReversalRow(row.id, 'indexRef', v || '')"
                />
                <GtIndexChip
                  v-if="row.indexRef"
                  :value="row.indexRef"
                  :context-project-id="projectId"
                />
              </div>
            </template>
          </el-table-column>

          <!-- 操作列：删除 -->
          <el-table-column label="" width="50" fixed="right">
            <template #default="{ row }: { row: ReversalRow }">
              <el-popconfirm
                title="确定删除该行？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="removeReversalRow(row.id)"
              >
                <template #reference>
                  <el-button
                    v-if="!isReadonly"
                    type="danger"
                    size="small"
                    text
                    class="delete-btn"
                  >
                    ✕
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加按钮 -->
        <div class="table-toolbar">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addReversalRow">
            + 添加转回项
          </el-button>
        </div>

        <!-- 合计行 -->
        <div class="sum-row">
          <span class="sum-label">合计：</span>
          <span class="sum-item">E转回金额 = <strong v-html="fmtAmountHtml(reversalTotalE)" /></span>
          <span class="sum-item">F原计提 = <strong v-html="fmtAmountHtml(reversalTotalF)" /></span>
        </div>

        <!-- 核对区 -->
        <table class="recon-table">
          <thead>
            <tr>
              <th>本表转回合计</th>
              <th>D1-4转回变动合计</th>
              <th>差异</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="recon-num" v-html="fmtAmountHtml(reversalTotalE)" />
              <td class="recon-num">
                <template v-if="d14ReversalTotal !== null">
                  <span v-html="fmtAmountHtml(d14ReversalTotal)" />
                </template>
                <template v-else>
                  <el-tooltip content="D1-4审定表数据未加载" placement="top">
                    <span class="cross-spec-warn">- ⚠️</span>
                  </el-tooltip>
                </template>
              </td>
              <td class="recon-num" :class="{ 'diff-nonzero': reversalDiff !== null && reversalDiff !== 0 }">
                <template v-if="reversalDiff !== null">
                  <span v-html="fmtAmountHtml(reversalDiff)" />
                </template>
                <template v-else>-</template>
              </td>
              <td v-if="reversalDiff !== null && reversalDiff !== 0">
                <el-button size="small" type="warning" @click="onSyncReversalToD14" :disabled="isReadonly">
                  同步到D1-4
                </el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <el-divider />

      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <!-- Section 2: 核销检查 -->
      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <section class="writeoff-section">
        <h3 class="section-heading">(二)本期重要的核销应收票据检查</h3>
        <div class="section-stat">
          共{{ writeoffRows.length }}笔核销，合计金额{{ fmtAmount(writeoffTotalC) }}元
        </div>

        <!-- 5列核销表格 -->
        <el-table
          :data="writeoffRows"
          border
          size="small"
          max-height="420"
          class="writeoff-table"
          style="width: 100%"
        >
          <!-- A: 单位名称 -->
          <el-table-column label="单位名称" width="150">
            <template #default="{ row }: { row: WriteoffRow }">
              <el-input
                :model-value="row.unitName"
                size="small"
                placeholder="单位名称"
                :disabled="isReadonly"
                @change="(v: string) => updateWriteoffRow(row.id, 'unitName', v || '')"
              />
            </template>
          </el-table-column>

          <!-- B: 性质 -->
          <el-table-column label="性质" width="120">
            <template #default="{ row }: { row: WriteoffRow }">
              <el-select
                :model-value="row.noteNature"
                placeholder="选择"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateWriteoffRow(row.id, 'noteNature', v || '')"
              >
                <el-option v-for="o in NOTE_NATURES" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>

          <!-- C: 核销金额 -->
          <el-table-column label="核销金额" width="120" align="right">
            <template #default="{ row }: { row: WriteoffRow }">
              <el-input-number
                :model-value="row.writeoffAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateWriteoffRow(row.id, 'writeoffAmount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- D: 核销原因 -->
          <el-table-column label="核销原因" min-width="150">
            <template #default="{ row }: { row: WriteoffRow }">
              <div class="cell-with-star">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.writeoffReason"
                  placeholder="核销原因..."
                  :disabled="isReadonly"
                  @change="(v: string) => updateWriteoffRow(row.id, 'writeoffReason', v || '')"
                />
                <span
                  v-if="row.writeoffAmount > 0 && !row.writeoffReason.trim()"
                  class="required-star"
                >*</span>
              </div>
            </template>
          </el-table-column>

          <!-- E: 核销程序 -->
          <el-table-column label="核销程序" min-width="150">
            <template #default="{ row }: { row: WriteoffRow }">
              <div class="cell-with-star">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.writeoffProcedure"
                  placeholder="履行的核销程序..."
                  :disabled="isReadonly"
                  @change="(v: string) => updateWriteoffRow(row.id, 'writeoffProcedure', v || '')"
                />
                <span
                  v-if="row.writeoffAmount > 0 && !row.writeoffProcedure.trim()"
                  class="required-star"
                >*</span>
              </div>
            </template>
          </el-table-column>

          <!-- 操作列：删除 -->
          <el-table-column label="" width="50" fixed="right">
            <template #default="{ row }: { row: WriteoffRow }">
              <el-popconfirm
                title="确定删除该行？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="removeWriteoffRow(row.id)"
              >
                <template #reference>
                  <el-button
                    v-if="!isReadonly"
                    type="danger"
                    size="small"
                    text
                    class="delete-btn"
                  >
                    ✕
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加按钮 -->
        <div class="table-toolbar">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addWriteoffRow">
            + 添加核销项
          </el-button>
        </div>

        <!-- 合计行 -->
        <div class="sum-row">
          <span class="sum-label">合计：</span>
          <span class="sum-item">C核销金额 = <strong v-html="fmtAmountHtml(writeoffTotalC)" /></span>
        </div>

        <!-- 核对区 -->
        <table class="recon-table">
          <thead>
            <tr>
              <th>本表核销合计</th>
              <th>D1-4核销变动合计</th>
              <th>差异</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="recon-num" v-html="fmtAmountHtml(writeoffTotalC)" />
              <td class="recon-num">
                <template v-if="d14WriteoffTotal !== null">
                  <span v-html="fmtAmountHtml(d14WriteoffTotal)" />
                </template>
                <template v-else>
                  <el-tooltip content="D1-4审定表数据未加载" placement="top">
                    <span class="cross-spec-warn">- ⚠️</span>
                  </el-tooltip>
                </template>
              </td>
              <td class="recon-num" :class="{ 'diff-nonzero': writeoffDiff !== null && writeoffDiff !== 0 }">
                <template v-if="writeoffDiff !== null">
                  <span v-html="fmtAmountHtml(writeoffDiff)" />
                </template>
                <template v-else>-</template>
              </td>
              <td v-if="writeoffDiff !== null && writeoffDiff !== 0">
                <el-button size="small" type="warning" @click="onSyncWriteoffToD14" :disabled="isReadonly">
                  同步到D1-4
                </el-button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- ECL 预警 -->
        <div v-if="writeoffExceedsProvision" class="ecl-warning">
          ⚠️ 核销金额超过本期计提总额，请关注坏账准备充足性
        </div>
      </section>

      <el-divider />

      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <!-- Section 3: 审计说明 -->
      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <section class="audit-note-section">
        <h3 class="section-heading">三、审计说明</h3>
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
            <el-button size="small" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateAuditNoteWithAI">
              🤖 AI
            </el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-writeoff-audit-note')"
          >
            💬 复核
          </el-button>
        </div>
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
      </section>

      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <!-- Section 4: 审计结论 -->
      <!-- ═══════════════════════════════════════════════════════════════════ -->
      <section class="audit-conclusion-section">
        <h3 class="section-heading">四、审计结论</h3>
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
            <el-button size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateAuditConclusionWithAI">
              🤖 AI
            </el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-writeoff-audit-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />

        <!-- 编制提示折叠区 -->
        <details class="guidance-fold">
          <summary>📋 编制提示</summary>
          <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
        </details>
      </section>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-writeoff-check {
  padding: 12px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

/* 段落标题 */
.section-heading {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px;
}

/* 统计标签 */
.section-stat {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

/* 表格工具栏 */
.table-toolbar {
  display: flex;
  align-items: center;
  margin: 8px 0;
  gap: 12px;
}

/* 表格样式 */
.writeoff-table {
  margin-bottom: 4px;
}

:deep(.writeoff-table .el-textarea__inner) {
  min-height: 60px !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 合计行 */
.sum-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
}

.sum-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.sum-item {
  font-size: 13px;
  color: #606266;
}

.sum-item strong {
  font-size: 14px;
  color: #303133;
}

/* 核对区表格 */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 12px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.diff-nonzero {
  color: #f56c6c !important;
  font-weight: 600;
}

/* 跨Spec数据未加载警告 */
.cross-spec-warn {
  color: #e6a23c;
  font-size: 13px;
}

/* 必填星号 */
.cell-with-star {
  position: relative;
}

.required-star {
  color: #f56c6c;
  position: absolute;
  top: 0;
  right: 2px;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}

/* E>F 预警橙色边框 */
.exceeds-provision {
  border: 1px solid #e6a23c;
  border-radius: 4px;
}

:deep(.exceeds-provision .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

/* ECL 预警 */
.ecl-warning {
  color: #e6a23c;
  background: #fdf6ec;
  padding: 8px 12px;
  border-radius: 4px;
  margin-top: 8px;
  font-size: 13px;
}

/* 索引号单元格 */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

/* 删除按钮 */
.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* 审计说明/结论 */
.audit-note-section,
.audit-conclusion-section {
  margin-bottom: 12px;
}

.note-actions {
  margin-bottom: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
