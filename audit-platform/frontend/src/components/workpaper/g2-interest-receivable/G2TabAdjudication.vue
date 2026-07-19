<template>
  <div class="g2-adjudication" data-testid="g2-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G2-1 应收利息审定表</h3>
      <div class="head-actions tab-toolbar">
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-1"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" :disabled="isReadonly" :loading="syncing" @click="onSyncSupporting">
          从 G2-2/G2-3 汇总未审
        </el-button>
        <el-button size="small" :disabled="isReadonly" :loading="tbLoading" @click="onFetchTb">
          取试算 1132
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-3" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-4" /></span>
        <el-button size="small" @click="openReviewDialog('G2-1-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实应收利息（科目1132）原值、坏账准备及净值的存在、完整与准确，确认单项/组合计提划分恰当，为报表列报及附注披露提供审定依据。"
      class="objective-alert"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>可「从 G2-2/G2-3 汇总未审」：原值按减值阶段归集（Stage3→单项，其余→组合）；坏账取 G2-3 单项/组合审定；已有账项调整保留。</li>
        <li>G2-4「确认调整」后，净调整自动回写至「原值·按组合」期末账项调整（可再手工分摊）。</li>
        <li>结构对齐模板：（一）应收利息原值 →（二）坏账准备 →（三）净值＝原值−坏账。</li>
        <li>原值/坏账按「单项计提 / 按组合计提」展开；小计与净值自动汇总。</li>
        <li>审定＝本账数＋账项调整；变动额／变动率自动计算；|变动率|&gt;{{ Math.round(G2_CHANGE_RATE_THRESHOLD * 100) }}% 时差异分析必填。</li>
        <li>合计（净值）应与试算平衡表 1132 勾稽，差异为 0；可点「取试算 1132」。</li>
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
      <el-table-column label="项目" min-width="220" fixed>
        <template #default="{ row }">
          <span
            :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }"
            :class="{ 'label-strong': row.kind !== 'leaf' }"
          >
            {{ row.label }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="本账数" width="110" align="right">
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
        <el-table-column label="账项调整" width="100" align="right">
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
        <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 本账 + 账项调整">{{ fmt(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="本账数" width="110" align="right">
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
        <el-table-column label="账项调整" width="100" align="right">
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
        <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 本账 + 账项调整">{{ fmt(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期与上期审定数比较" align="center">
        <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'rate-warn': row.changeRateHighlight }]">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="差异分析" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !isReadonly"
            :model-value="row.reasonAnalysis"
            size="small"
            :placeholder="row.reasonRequired ? '变动率超阈值，请说明原因' : '可选填'"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
            @update:model-value="(v: string) => updateField(row.rowKey, 'reasonAnalysis', v)"
          />
          <span v-else-if="row.reasonAnalysis">{{ row.reasonAnalysis }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（1132）：</span>
      <el-input-number
        :model-value="adj.trialBalanceAmount.value"
        size="small"
        :controls="false"
        :disabled="isReadonly"
        style="width: 140px"
        @update:model-value="(v: number) => adj.setTrialBalance(v ?? 0)"
      />
      <span :class="['diff-value', { 'diff-red': adj.hasVarianceHighlight.value }]">
        差异：{{ fmt(adj.variance.value) }}
        <template v-if="!adj.hasVarianceHighlight.value"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="adj.auditNote.value"
      :conclusion="adj.auditConclusion.value"
      @update:note="(v: string) => { adj.auditNote.value = v }"
      @update:conclusion="(v: string) => { adj.auditConclusion.value = v }"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      :related-context="{
        审定合计: adj.subtotalRow.value?.closingAudited,
        试算表数: adj.trialBalanceAmount.value,
        差异: adj.variance.value,
        变动额: adj.subtotalRow.value?.changeAmount,
        变动率: fmtRate(adj.subtotalRow.value?.changeRate),
      }"
      note-placeholder="填写审计说明：（1）期末余额较期初变动幅度及主要原因；（2）账龄一年以上未收回款项及处理；（3）单项/组合计提政策与测算；（4）与试算勾稽及拟调整事项。"
      note-hint="覆盖原值/坏账/净值审定、变动分析、长期挂账及试算勾稽。"
      conclusion-hint="按 A/B/C 口径评价科目 1132 审定结果。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useG2Adjudication,
  G2_CHANGE_RATE_THRESHOLD,
  type G2AdjEditableField,
} from '../composables/useG2Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpId = computed(() => props.wpId ?? '')

const adj = useG2Adjudication({
  wpId: toRef(props, 'wpId', ''),
  projectId: toRef(props, 'projectId', ''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const rows = computed(() => adj.dataRows.value)
const syncing = ref(false)
const tbLoading = ref(false)
const tableMaxHeight = 520

function onSyncSupporting() {
  syncing.value = true
  try {
    const r = adj.syncFromSupporting()
    ElMessage.success(
      `已汇总：明细 ${r.gross} 行、坏账 ${r.provision} 行 → 未审本账（账项调整已保留）`,
    )
  } finally {
    syncing.value = false
  }
}

async function onFetchTb() {
  tbLoading.value = true
  try {
    const amount = await adj.fetchTrialBalance()
    if (amount == null) {
      ElMessage.warning('未取到试算 1132，请确认项目已导入试算平衡表')
    } else {
      ElMessage.success(`试算 1132：${fmt(amount)}（已写入核对参考）`)
    }
  } finally {
    tbLoading.value = false
  }
}

function updateField(rowKey: string, field: G2AdjEditableField, value: number | string) {
  adj.updateField(rowKey, field, value)
}

function rowClassName({ row }: { row: { kind: string } }) {
  if (row.kind === 'section_header' || row.kind === 'net_row' || row.kind === 'footer') {
    return 'row-section'
  }
  if (row.kind === 'section_subtotal') return 'row-subtotal'
  return ''
}

function fmt(v: unknown): string {
  return typeof v === 'number'
    ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(v ?? '')
}

function fmtRate(v: number | '' | 'N/A' | undefined): string {
  if (v === '' || v === undefined) return ''
  if (v === 'N/A') return 'N/A'
  return `${(v * 100).toFixed(2)}%`
}
</script>

<style scoped>
.g2-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.objective-alert { margin-bottom: 10px; }
.prep-hint { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; color: #606266; line-height: 1.6; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.label-strong { font-weight: 600; }
:deep(.row-section) { background: #f0f5ff !important; font-weight: 600; }
:deep(.row-subtotal) { background: #fafafa !important; font-weight: 600; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.tb-diff-row { display: flex; gap: 16px; margin: 16px 0; align-items: center; font-size: var(--wp-font-size, 13px); }
.tb-label { font-weight: 500; }
.diff-value { font-weight: 600; }
.diff-red { color: #f56c6c; }
.chip-wrap { display: inline-flex; align-items: center; }
</style>
