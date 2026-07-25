<template>
  <div class="g1-adjudication" data-testid="g1-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G1-1 交易性金融资产审定表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-1"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" :disabled="isReadonly" @click="onSyncDetail">从 G1-2 汇总未审</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-3" /></span>
        <el-button size="small" @click="openReviewDialog('G1-1-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产（科目1501）投资成本、累计公允价值变动及账面余额的准确与完整，确认分类（交易性/划分为/指定为）列报恰当，为资产负债表及附注披露提供审定依据。"
      class="objective-alert"
    />

    <el-alert
      v-if="lastWritebackNet !== 0"
      type="success"
      :closable="false"
      class="writeback-alert"
      :title="`已自 G1-3 回写期末账项调整 ${fmt(lastWritebackNet)}（默认行：投资成本·交易性·其他）`"
    >
      <div class="writeback-actions">
        <span>多分类/多品种时请分摊，避免审定集中在「其他」。</span>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          @click="openAllocDialog"
        >
          分摊到明细行
        </el-button>
      </div>
    </el-alert>

    <el-dialog
      v-model="allocVisible"
      title="G1-3 回写净额分摊"
      width="560px"
      append-to-body
      destroy-on-close
    >
      <p class="alloc-hint">
        将净额 <b>{{ fmt(lastWritebackNet) }}</b> 分摊至「投资成本 · 交易性」下各品种。
        合计须接近净额；差额自动留在默认「其他」行。
      </p>
      <el-table :data="allocRows" border size="small" max-height="360">
        <el-table-column prop="label" label="目标行" min-width="220" />
        <el-table-column label="分摊金额" width="160">
          <template #default="{ row }">
            <el-input-number
              v-model="row.amount"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="alloc-input"
            />
          </template>
        </el-table-column>
      </el-table>
      <div class="alloc-sum">
        已填合计 {{ fmt(allocSum) }}
        <span :class="{ warn: Math.abs(allocSum - lastWritebackNet) > 0.05 }">
          （差额 {{ fmt(allocSum - lastWritebackNet) }}）
        </span>
      </div>
      <template #footer>
        <el-button @click="allocVisible = false">取消</el-button>
        <el-button type="primary" :disabled="isReadonly" @click="onApplyAlloc">应用分摊</el-button>
      </template>
    </el-dialog>
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>结构对齐模板：（一）投资成本 →（二）累计公允价值变动 →（三）账面余额＝成本＋累计 FV。</li>
        <li>可「从 G1-2 汇总未审」按会计分类×投资品种自动填入未审数，已有账项调整与原因分析保留。</li>
        <li>G1-3「确认调整」后，1501 净调整默认回写至「投资成本·交易性·其他」；可用「分摊到明细行」拆到债务/权益等品种。</li>
        <li>每层按「交易性 / 划分为 FVTPL / 指定为 FVTPL」× 品种明细展开；分类行与小计自动汇总。</li>
        <li>审定＝未审＋账项调整；变动额／变动率自动计算；|变动率|&gt;{{ Math.round(G1_CHANGE_RATE_THRESHOLD * 100) }}% 时原因分析必填。</li>
        <li>账面余额合计（减一年以上到期）应与试算平衡表 1501 勾稽，差异为 0。</li>
        <li>「带入调整」：可从集中登记按科目 1501 拉取调整分录，逐笔分配到各成本/公允价值明细行的期末账项调整，带入后审定数自动更新并联动附注。</li>
      </ul>
    </details>

    <el-table
      :data="rows"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="tableMaxHeight"
      style="width: 100%"
    >
      <el-table-column label="项目" min-width="280" fixed>
        <template #default="{ row }">
          <span :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }" :class="{ 'label-strong': row.kind !== 'leaf' }">
            {{ row.label }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => updateField(row.rowKey, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmt(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.openingAdjustment"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => updateField(row.rowKey, 'openingAdjustment', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + 账项调整">{{ fmt(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.closingUnadjusted"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => updateField(row.rowKey, 'closingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmt(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.closingAdjustment"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => updateField(row.rowKey, 'closingAdjustment', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + 账项调整">{{ fmt(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期与上期审定数比较" align="center">
        <el-table-column label="变动额" width="96" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.changeRate === 'N/A'">N/A</span>
            <span v-else-if="row.changeRate === ''">—</span>
            <span v-else :class="{ 'rate-warn': row.changeRateHighlight }">
              {{ (Number(row.changeRate) * 100).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !isReadonly"
            :model-value="row.reasonAnalysis"
            size="small"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
            :placeholder="row.reasonRequired ? `|变动率|>${Math.round(G1_CHANGE_RATE_THRESHOLD * 100)}% 必填` : ''"
            @change="(v: string) => updateField(row.rowKey, 'reasonAnalysis', v)"
          />
          <span v-else>{{ row.reasonAnalysis || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="tb-diff-row">
      <span>试算平衡表数（1501）：
        <el-input-number
          :model-value="trialBalanceAmount"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @update:model-value="(v: number) => updateTrialBalance(v ?? 0)"
        />
      </span>
      <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        差异数：{{ fmt(trialBalanceDiff) }}
        <template v-if="trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
      <span class="book-total-hint">账面余额合计审定：{{ fmt(totalRow.closingAudited) }}</span>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusion"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      note-placeholder="交易性金融资产审定说明（成本与累计 FV 构成、分类依据、重大波动原因、与试算表核对等）..."
      note-hint="评价投资成本、累计公允价值变动、分类列报及与试算表勾稽。"
      conclusion-hint="按 A/B/C 口径评价科目 1501 列报是否公允。"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1501 交易性金融资产"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useG1Adjudication } from '../../composables/useG1Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  htmlData?: any
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const tableMaxHeight = computed(() => Math.max(420, window.innerHeight - 320))
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  rows,
  totalRow,
  trialBalanceAmount,
  trialBalanceDiff,
  auditNote,
  conclusion,
  updateField,
  updateTrialBalance,
  syncFromDetail,
  lastWritebackNet,
  allocateWriteback,
  writebackAllocTargets,
  rowClassName,
  G1_CHANGE_RATE_THRESHOLD,
} = useG1Adjudication({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── 从集中登记带入调整（1501 交易性金融资产，资产借方；带入期末账项调整，单列合并 AJE/RJE） ───
const bringInRows = computed(() =>
  rows.value
    .filter((r) => r.editable && (r.section === 'cost' || r.section === 'fv'))
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.closingAdjustment, rje: r.closingAdjustment })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: (() =>
    props.htmlData?.project_context?.project_id
    ?? props.htmlData?.projectContext?.project_id
    ?? '') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1501',
  direction: 'debit',
  subjectCode: '1501',
  wpCode: 'G1',
  subjectLabel: '交易性金融资产(1501)',
  rows: bringInRows,
  updateCell: (rowKey: string, _field: any, value: number) =>
    updateField(rowKey, 'closingAdjustment', value),
  totalAudited: () => totalRow.value.closingAudited,
})

const allocVisible = ref(false)
const allocRows = ref<Array<{ rowKey: string; label: string; amount: number }>>([])
const allocSum = computed(() =>
  allocRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0),
)

function openAllocDialog() {
  const net = lastWritebackNet.value
  allocRows.value = writebackAllocTargets.map((t) => ({
    rowKey: t.rowKey,
    label: t.label,
    amount: t.rowKey.endsWith('-other') ? net : 0,
  }))
  allocVisible.value = true
}

function onApplyAlloc() {
  const res = allocateWriteback(
    allocRows.value.map((r) => ({ rowKey: r.rowKey, amount: Number(r.amount) || 0 })),
  )
  if (!res.ok) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success('已按明细行分摊回写净额')
  allocVisible.value = false
}

function onSyncDetail() {
  const n = syncFromDetail()
  if (!n) {
    ElMessage.warning('G1-2 无可用明细')
    return
  }
  ElMessage.success(`已汇总 ${n} 组分类×品种未审数（保留原调整）`)
}

function fmt(n: number): string {
  if (n === 0) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g1-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.writeback-alert { margin-bottom: 10px; }
.writeback-actions {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-top: 6px; font-size: 12px;
}
.alloc-hint { margin: 0 0 12px; font-size: 13px; color: #606266; }
.alloc-input { width: 140px; }
.alloc-sum { margin-top: 10px; font-size: 13px; }
.alloc-sum .warn { color: #e6a23c; font-weight: 600; }
.prep-hint { margin: 0 0 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
.label-strong { font-weight: 600; }
.tb-diff-row { display: flex; flex-wrap: wrap; gap: 24px; margin: 16px 0; align-items: center; }
.diff-red { color: #f56c6c; font-weight: 600; }
.book-total-hint { color: #606266; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
:deep(.row-section-header) { background: #f4f0fa !important; font-weight: 600; }
:deep(.row-class-header) { background: #faf8fc !important; }
:deep(.row-subtotal) { background: #f0f2f5 !important; font-weight: 600; }
:deep(.row-footer) { background: #fafafa !important; }
</style>
