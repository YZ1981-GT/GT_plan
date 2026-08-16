<template>
<div class="d6-adjudication">
    <!-- 四表库取数溯源（消 dead output：消费 render 下发的 tb_source_codes；
         口径 = {{ dCycleBasisLabel('D6') }}） -->
    <WpFourTableSourcePanel
      :source-codes="dTbSourceCodes"
      gross-label="合同资产原值"
      provision-label="合同资产减值准备"
      fallback-row-code="BS-011"
      :hints="dSourceHints"
    />
  <el-skeleton v-if="!blocks.length" :rows="8" animated />

  <template v-if="blocks.length">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为 D6 合同资产审定表（科目1141/1403），含三区块：一、合同资产原值；二、合同资产坏账准备；三、合同资产净值。</p>
        <p>2. 区块一取自 D6-2 明细表按合同类型聚合，区块二取自 D6-3 减值准备明细按分类聚合，浅蓝背景单元格为跨sheet自动取数，不可手工编辑。</p>
        <p>3. 区块三净值 = 区块一原值 − 区块二坏账准备（灰色底纹列为自动计算，不可录入）；净值≠原值−坏账时黄色告警。</p>
        <p>4. 依 CAS14 收入准则确认合同资产，减值按 CAS22 ECL 模型计提；变动率超过30%需在审计说明中分析原因，并与试算平衡表核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认合同资产期末原值、坏账准备及净值的存在、完整与准确，评价按 CAS14/CAS22 计量的恰当性，并与试算平衡表核对一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:D6-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ blocks.length }} 区块</el-tag>
      </div>
    </div>

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
              <el-tag
                v-if="row.isFourTableSeed"
                size="small"
                type="success"
                effect="plain"
                style="margin-left:4px"
              >自动取数</el-tag>
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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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

    <!-- 核对行：与试算平衡表核对 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目1141）：</span>
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
            <GtIndexChip value="wp:D6-8" :context-project-id="projectId" />
            <GtIndexChip value="wp:D6-6" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 变动分析</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genExplanation">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D6-1-note-explanation')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析合同资产本期变动原因..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 计提充分性评价</span>
          <div class="opinion-actions">
            <GtIndexChip value="wp:D6-8" :context-project-id="projectId" />
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genImpairmentEval">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D6-1-note-impairmentEval')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.impairmentEval"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="结合D6-8 ECL测算结果评价坏账计提充分性..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">3. 长期挂账分析</span>
          <div class="opinion-actions">
            <GtIndexChip value="wp:D6-6" :context-project-id="projectId" />
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genLongTermReason">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D6-1-note-longTermReason')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.longTermReason"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析长期挂账合同资产的原因及期后结转情况..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">4. 审计结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D6-1-note-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对合同资产审定结果的总结性结论..."
        />
      </div>
    </el-card>
  </template>

  <AdjudicationBringInDialog
    v-model="bringInVisible"
    :matches="adjPull.matches.value"
    :row-options="bringInRowOptions"
    subject-label="1141 合同资产"
    :loading="adjPull.loading.value"
    @apply="onBringInApply"
  />
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
import { InfoFilled, Download } from '@element-plus/icons-vue'
import { useD6Adjudication, type AdjudicationBlock, type AdjudicationRow, type AdjudicationPrefillRow } from '../composables/useD6Adjudication'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { isChangeRateExceeding } from '../composables/useD6FormulaEngine'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import WpFourTableSourcePanel from '@/components/workpaper/shared/WpFourTableSourcePanel.vue'
import {
  pickDTbSourceCodes,
  normalizeDSlots,
  dCycleBasisLabel,
} from '../composables/dCycleAccountScope'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
  /** 四表库审定表预填（render 的 html_data.adjudication_prefill；灰度关/已填时为空）。 */
  adjudicationPrefill?: AdjudicationPrefillRow[]
  /**
   * render 下发的本 sheet `html_data`（含 `tb_source_codes` / `parent_check`）。
   *
   * 🔴 必须由宿主显式传入 —— 漏传不会报错、只会让四表取数溯源恒 `undefined`
   * （未声明属性会静默落到根元素当 HTML 属性，四层验证全绿）。
   *
   * D6 备抵是 `prefix_mismatch` 态的唯一活体样本（`1231-05` 在 `account_mapping`
   * 零反解 ⇒ 保留横杠标准码 ⇒ 在点号体系的 `tb_balance` 必然命中 0 行），
   * 当前结果「碰巧正确」，必须让它可见。
   */
  htmlData?: Record<string, any> | null
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const adjudicationPrefillRef = toRef(props, 'adjudicationPrefill') as unknown as Ref<AdjudicationPrefillRow[] | undefined>

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
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  adjudicationPrefill: adjudicationPrefillRef,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── 从集中登记带入调整（1141 合同资产，资产借方；带入区块一原值 dynamic 行期末 AJE/RJE） ─
// 合同资产科目为 1141；report_config 报表行 BS-011 四准则一致。原 `1402` 是在途物资
// （存货类），属误用。
const bringInRows = computed(() => {
  const block1 = blocks.value.find((b) => b.blockKey === 'block1')
  return (block1?.rows ?? [])
    .filter((r) => r.rowType === 'dynamic' && r.isEditable)
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.currentAje, rje: r.currentRje }))
})
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1141',
  direction: 'debit',
  subjectCode: '1141',
  wpCode: 'D6',
  subjectLabel: '合同资产(1141)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell('block1', rowKey, field === 'rje' ? 'currentRje' : 'currentAje', value),
  totalAudited: () => blocks.value.find((b) => b.blockKey === 'block3')?.blockTotalRow.currentAudited ?? 0,
})

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
  return [...block.rows, block.subtotalRow, block.deductionRow, block.blockTotalRow].filter(Boolean) as AdjudicationRow[]
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

function adjRowClassName(row: AdjudicationRow): string {
  if (!row) return ''
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

// ─── 四表库取数溯源（Task 16）────────────────────────────────────────
// 🔴 落点两套并存：D1/D2/D3/D5/D6/D7 写 `html_data` 顶层、D4 写
// `project_context` —— `pickDTbSourceCodes` 两层都读，只读一层会恒 undefined。
const dTbSourceCodes = computed(() =>
  normalizeDSlots(pickDTbSourceCodes(props.htmlData)),
)
const dSourceHints = [
  '取数口径：<code>期末余额</code>；标准码查试算平衡表、客户原始码查余额表。',
  '「本项目无此科目」与「余额为 0」是两回事 —— 前者金额显示为空，后者显示 0.00。',
]

</script>

<style scoped>
.d6-adjudication {
  padding: 16px;
}
.d6-adjudication :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-adjudication :deep(.el-table .cell) {
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

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
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
  align-items: center;
}
</style>
