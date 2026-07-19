<!--
  G3TabCalcCheck.vue — G3-4 测算及检查表（三区段）

  ① 增加测算：持股×DPS vs 账面已计；差异=账面−测算
  ② 减少检查：本期减少 vs 收现+其他减少
  ③ 期后收回：抽凭 + 核对勾选1–5 + 是否异常

  Spec: g3-dividend-receivable G3-4 强化（对齐致同 Excel）
-->
<template>
  <div class="g3-calc-check">
    <div class="section-head">
      <h3 class="sheet-title">G3-4 测算及检查表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" :disabled="isReadonly" @click="calcCheck.addRow()">＋ 新增</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="calcCheck.syncFromDetail()">
          从 G3-2 同步
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || calcCheck.totals.value.pushableVarianceCount === 0"
          @click="onPushToG33"
        >
          差异推送 G3-3
        </el-button>
        <el-button
          v-if="calcCheck.segment.value === 'subsequent'"
          size="small"
          type="success"
          :disabled="isReadonly"
          @click="openSamplingEngine"
        >
          使用抽凭引擎
        </el-button>
        <G3ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          :sheet="importSheet"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('G3-4-calc-check')">💬复核</el-button>
        <GtIndexChip value="wp:G3-4" :context-project-id="projectId" />
        <el-tag size="small" type="info">
          {{ rowCountLabel }}
        </el-tag>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：独立测算本期宣告应收股利并与账面已计数核对；检查本期减少是否对应收现或其他正当转出；通过期后收回抽查印证期末余额的存在性与准确性。"
    />

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="cross-ref-tip"
      title="若分红已在长期股权投资等底稿核实，请在「已在长投核实」选是并填写交叉索引，避免重复劳动；本表仍应对差异与期末余额做勾稽确认。"
    />

    <div v-if="cutoffDate || samplingYear" class="meta-bar">
      <el-tag v-if="cutoffDate" size="small" type="info">资产负债表日：{{ cutoffDate }}</el-tag>
      <el-tag v-if="samplingYear" size="small" type="success">期后抽凭年度：{{ samplingYear }}（默认 1–3 月）</el-tag>
    </div>

    <el-tabs v-model="calcCheck.segment.value" type="border-card" class="segment-tabs">
      <el-tab-pane
        v-for="seg in calcCheck.segments"
        :key="seg.key"
        :label="seg.label"
        :name="seg.key"
      />
    </el-tabs>

    <!-- ①② 被投资方行表 -->
    <el-table
      v-if="calcCheck.segment.value !== 'subsequent'"
      :data="calcCheck.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="mainRowClassName"
      class="calc-check-table"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <el-table-column label="被投资方" width="150" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => calcCheck.updateRow(row.id, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <el-table-column
        v-for="col in currentMainColumns"
        :key="col.prop"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : 'left'"
      >
        <template #default="{ row }">
          <template v-if="col.formula">
            <span class="formula-cell" :title="getMainFormulaTooltip(col.prop)">
              {{ fmtNum(row[col.prop]) }}
            </span>
          </template>
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              :model-value="row[col.prop]"
              type="date"
              size="small"
              :disabled="isReadonly"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => calcCheck.updateRow(row.id, { [col.prop]: v ?? '' })"
            />
          </template>
          <template v-else-if="col.type === 'number'">
            <el-input-number
              :model-value="row[col.prop] as number"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => calcCheck.updateRow(row.id, { [col.prop]: v ?? 0 })"
            />
          </template>
          <template v-else-if="col.type === 'yn'">
            <el-select
              :model-value="row[col.prop]"
              size="small"
              :disabled="isReadonly"
              clearable
              style="width:100%"
              @change="(v: string) => calcCheck.updateRow(row.id, { [col.prop]: v ?? '' })"
            >
              <el-option v-for="opt in YES_NO_OPTIONS" :key="opt.value || 'empty'" :value="opt.value" :label="opt.label" />
            </el-select>
          </template>
          <template v-else>
            <el-input
              :model-value="row[col.prop] as string"
              size="small"
              :disabled="isReadonly"
              :class="{ 'need-input': isReasonFieldMissing(row, col.prop) }"
              @change="(v: string) => calcCheck.updateRow(row.id, { [col.prop]: v })"
            />
          </template>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="calcCheck.removeRow(row.id)"><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- ③ 期后收回 -->
    <template v-else>
      <div class="check-hints">
        <span class="check-hints-title">核对内容：</span>
        <span v-for="(h, i) in CHECK_CONTENT_HINTS" :key="i" class="check-hint-item">{{ h }}</span>
      </div>
      <el-table
        :data="calcCheck.subsequentRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="subsequentRowClassName"
        class="calc-check-table"
      >
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ row }">
            <span>{{ row.seq }}</span>
            <el-tooltip v-if="calcCheck.isSamplingRow(row)" content="来源: 抽凭引擎" placement="top">
              <span class="sample-flag">📌</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column
          v-for="col in subsequentColumns"
          :key="col.prop"
          :label="col.label"
          :min-width="col.width"
          :align="col.type === 'number' || col.formula || col.type === 'check' ? 'center' : 'left'"
        >
          <template #default="{ row }">
            <template v-if="col.formula">
              <span class="formula-cell" title="金额 = 借方（优先）或贷方">{{ fmtNum(row[col.prop]) }}</span>
            </template>
            <template v-else-if="col.type === 'date'">
              <el-date-picker
                :model-value="row[col.prop]"
                type="date"
                size="small"
                :disabled="isReadonly"
                value-format="YYYY-MM-DD"
                style="width:100%"
                @update:model-value="(v: string) => calcCheck.updateSubsequentRow(row.id, { [col.prop]: v ?? '' })"
              />
            </template>
            <template v-else-if="col.type === 'number'">
              <el-input-number
                :model-value="row[col.prop] as number"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: number) => calcCheck.updateSubsequentRow(row.id, { [col.prop]: v ?? 0 })"
              />
            </template>
            <template v-else-if="col.type === 'check'">
              <el-select
                :model-value="row[col.prop]"
                size="small"
                :disabled="isReadonly"
                clearable
                style="width:100%"
                @change="(v: string) => calcCheck.updateSubsequentRow(row.id, { [col.prop]: v ?? '' })"
              >
                <el-option v-for="opt in CHECK_MARK_OPTIONS" :key="opt.value || 'empty'" :value="opt.value" :label="opt.label" />
              </el-select>
            </template>
            <template v-else-if="col.type === 'yn'">
              <el-select
                :model-value="row[col.prop]"
                size="small"
                :disabled="isReadonly"
                clearable
                style="width:100%"
                @change="(v: string) => calcCheck.updateSubsequentRow(row.id, { [col.prop]: v ?? '' })"
              >
                <el-option v-for="opt in YES_NO_OPTIONS" :key="opt.value || 'empty'" :value="opt.value" :label="opt.label" />
              </el-select>
            </template>
            <template v-else>
              <el-input
                :model-value="row[col.prop] as string"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => calcCheck.updateSubsequentRow(row.id, { [col.prop]: v })"
              />
            </template>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-icon class="delete-icon" @click="calcCheck.removeRow(row.id)"><Delete /></el-icon>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <div class="totals-bar">
      <span class="totals-label">合计</span>
      <template v-if="calcCheck.segment.value === 'increase'">
        <span class="total-item">测算：{{ fmtNum(calcCheck.totals.value.calculatedDividend) }}</span>
        <span class="total-item">账面已计：{{ fmtNum(calcCheck.totals.value.bookedAmount) }}</span>
        <span class="total-item">测算差异：{{ fmtNum(calcCheck.totals.value.calcVariance) }}</span>
        <span v-if="calcCheck.totals.value.varianceUnresolvedCount" class="total-item warn">
          待说明差异 {{ calcCheck.totals.value.varianceUnresolvedCount }} 笔
        </span>
      </template>
      <template v-else-if="calcCheck.segment.value === 'decrease'">
        <span class="total-item">本期减少：{{ fmtNum(calcCheck.totals.value.periodDecrease) }}</span>
        <span class="total-item">收现：{{ fmtNum(calcCheck.totals.value.cashReceived) }}</span>
        <span class="total-item">其他减少：{{ fmtNum(calcCheck.totals.value.otherDecreaseAmount) }}</span>
        <span class="total-item">减少差异：{{ fmtNum(calcCheck.totals.value.decreaseDiff) }}</span>
        <span v-if="calcCheck.totals.value.decreaseUnresolvedCount" class="total-item warn">
          待说明差异 {{ calcCheck.totals.value.decreaseUnresolvedCount }} 笔
        </span>
      </template>
      <template v-else>
        <span class="total-item">期后收回：{{ fmtNum(calcCheck.totals.value.subsequentAmount) }}</span>
        <span class="total-item">样本 {{ calcCheck.subsequentRows.value.length }} 笔</span>
        <span class="total-item" :class="{ warn: calcCheck.totals.value.subsequentAbnormalCount > 0 }">
          异常 {{ calcCheck.totals.value.subsequentAbnormalCount }} 笔
        </span>
        <span
          v-if="calcCheck.totals.value.subsequentCutoffInvalidCount > 0"
          class="total-item warn"
        >
          非期后日期 {{ calcCheck.totals.value.subsequentCutoffInvalidCount }} 笔
        </span>
      </template>
    </div>

    <G3AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="dividend-calc-note"
      conclusion-ai-section="dividend-calc-conclusion"
      :related-context="{
        测算行数: calcCheck.rows.value.length,
        测算差异合计: calcCheck.totals.value.calcVariance,
        待说明测算差异笔数: calcCheck.totals.value.varianceUnresolvedCount,
        减少差异合计: calcCheck.totals.value.decreaseDiff,
        待说明减少差异笔数: calcCheck.totals.value.decreaseUnresolvedCount,
        期后样本数: calcCheck.subsequentRows.value.length,
        期后异常笔数: calcCheck.totals.value.subsequentAbnormalCount,
        非期后日期笔数: calcCheck.totals.value.subsequentCutoffInvalidCount,
        可推送差异笔数: calcCheck.totals.value.pushableVarianceCount,
        资产负债表日: cutoffDate || '未设置',
      }"
      note-placeholder="填写审计说明：概述增加测算、减少核对与期后收回程序；说明测算/减少差异及拟调整事项；交叉索引至长期投资底稿（如适用）。"
      note-hint="覆盖增加差异、减少核对与期后抽查。"
      conclusion-hint="按 A/B/C 口径评价股利测算与检查结果。"
    />

    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. <b>增加测算</b>：应收股利(测算)=持股数量×每股股利；测算差异=账面已计股利−测算；|差异|&gt;100 橙亮，须填差异原因或索引（可指向 G3-3）。</p>
        <p>2. 若填写「被投资方分红总额」，系统用持股比例×总额做交叉验算，与股数×DPS 不一致时黄提示。</p>
        <p>3. <b>减少检查</b>：减少差异=本期减少−收现−其他减少金额；差异须有科目/原因/索引。</p>
        <p>4. <b>期后收回</b>：对期末余额做期后收现抽查；核对内容 1–5 逐项勾选；异常须说明。抽凭默认取资产负债表日次年，期间默认 1–3 月；填入时自动剔除截止日及以前凭证。</p>
        <p>5. 建议先「从 G3-2 同步」带入持股/分红/已收，再补账面已计与检查结论；同步不覆盖已填入账与原因。「差异推送 G3-3」生成调整草稿，仍须在 G3-3 核对借贷并确认。</p>
        <p>6. 期后收回印证存在性，不替代 G3-5 长期未收回可收回性评估。凭证日 ≤ 资产负债表日的行以红色提示「非期后」。</p>
        <p class="cas-basis">CAS 依据：重新计算与检查记录/文件（《中国注册会计师审计准则第 1301 号——审计证据》）；期后事项程序可提供余额存在性证据。</p>
      </div>
    </details>

    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎 - 科目1131应收股利（期后收回）"
      width="860px"
      destroy-on-close
      append-to-body
    >
      <el-alert
        v-if="cutoffDate || samplingYear"
        type="info"
        :closable="false"
        show-icon
        class="sampling-tip"
        :title="samplingTip"
      />
      <SamplingEngine
        v-if="showSamplingDialog && samplingYear != null"
        account-code="1131"
        phase="final"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        :initial-period-range="[1, 2, 3]"
        @filled="handleSamplingFilled"
      />
      <el-empty v-else-if="showSamplingDialog" description="未配置审计年度，无法确定期后抽凭年度。请在项目上下文设置审计年度/资产负债表日。" />
      <template #footer>
        <el-button @click="showSamplingDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef, inject, defineAsyncComponent, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import G3ImportExportDropdown from './G3ImportExportDropdown.vue'
import G3AuditTextCards from './G3AuditTextCards.vue'
import { G3DetailRevisionKey } from '../composables/g3InternalKeys'
import {
  useG3CalcCheck,
  G3_CALCCHECK_SEGMENTS,
  SEGMENT_SUBSEQUENT,
  CHECK_CONTENT_HINTS,
  CHECK_MARK_OPTIONS,
  YES_NO_OPTIONS,
  subsequentSamplingYear,
  isVarianceExceeding,
  isDecreaseDiffExceeding,
  needsVarianceReason,
  needsDecreaseExplain,
  isCrossCheckMismatch,
  isSubsequentCutoffInvalid,
} from '../composables/useG3CalcCheck'
import type { CalcCheckRow, CalcCheckColumn, SubsequentColumn, SubsequentRow } from '../composables/useG3CalcCheck'
import type { G3ImportableSheet } from '../composables/useG3ImportExport'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { SampledVoucher } from '../composables/useSamplingAlgorithms'

const SamplingEngine = defineAsyncComponent(
  () => import('../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  auditYear?: number | string | null
  cutoffDate?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const detailRevision = inject(G3DetailRevisionKey, null)
let lastDetailRevSeen = -1

const cutoffDate = computed(() => (props.cutoffDate || '').slice(0, 10))
const cutoffDateRef = computed(() => cutoffDate.value)
const samplingYear = computed(() => subsequentSamplingYear(props.auditYear ?? null))
const samplingTip = computed(() => {
  const parts: string[] = []
  if (cutoffDate.value) parts.push(`资产负债表日 ${cutoffDate.value}`)
  if (samplingYear.value != null) parts.push(`抽凭年度 ${samplingYear.value}、期间默认 1–3 月`)
  parts.push('填入时自动剔除截止日及以前凭证')
  return parts.join('；')
})

const calcCheck = useG3CalcCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  cutoffDate: cutoffDateRef,
})

/** G3-2 变更后进入本页：若已有测算行则静默重同步 */
function softSyncFromDetailIfNeeded() {
  if (props.isReadonly || !detailRevision) return
  const rev = detailRevision.value
  if (rev <= lastDetailRevSeen) return
  lastDetailRevSeen = rev
  const hasRows = calcCheck.rows.value.some((r) => r.investeeName.trim() || r.detailRowId)
  if (!hasRows) return
  calcCheck.syncFromDetail({ quiet: true })
}

onMounted(() => softSyncFromDetailIfNeeded())
if (detailRevision) watch(detailRevision, () => softSyncFromDetailIfNeeded())

const importSheet = computed<G3ImportableSheet>(() =>
  calcCheck.segment.value === 'subsequent' ? 'G3-4-subsequent' : 'G3-4',
)

const rowCountLabel = computed(() => {
  if (calcCheck.segment.value === 'subsequent') {
    return `期后 ${calcCheck.subsequentRows.value.length} 行`
  }
  return `测算 ${calcCheck.rows.value.length} 行`
})

const CONCLUSION_KEY = 'G3-4-calccheck-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'G3-4-calccheck-conclusion'
const auditConclusion = ref(
  props.allResponses.get(CONCLUSION_KEY)?.remark
  ?? props.allResponses.get(LEGACY_CONCLUSION_KEY)?.conclusion
  ?? '',
)
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: v })
})

const NOTE_KEY = 'G3-4-calccheck-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { conclusion: null, remark: v })
})

const currentMainColumns = computed<CalcCheckColumn[]>(() => {
  const seg = G3_CALCCHECK_SEGMENTS.find((s) => s.key === calcCheck.segment.value)
  if (!seg || calcCheck.segment.value === 'subsequent') return []
  return (seg.columns as CalcCheckColumn[]).filter(
    (c) => c.prop !== 'seq' && c.prop !== 'investeeName',
  )
})

const subsequentColumns = computed<SubsequentColumn[]>(() =>
  SEGMENT_SUBSEQUENT.filter((c) => c.prop !== 'seq'),
)

function mainRowClassName({ row }: { row: CalcCheckRow }): string {
  const classes: string[] = []
  if (calcCheck.segment.value === 'increase') {
    if (isVarianceExceeding(row)) classes.push('row-variance-exceed')
    if (needsVarianceReason(row)) classes.push('row-need-reason')
    if (isCrossCheckMismatch(row)) classes.push('row-cross-mismatch')
  } else if (calcCheck.segment.value === 'decrease') {
    if (isDecreaseDiffExceeding(row)) classes.push('row-variance-exceed')
    if (needsDecreaseExplain(row)) classes.push('row-need-reason')
  }
  return classes.join(' ')
}

function subsequentRowClassName({ row }: { row: SubsequentRow }): string {
  const classes: string[] = []
  if (row.isAbnormal === '是') classes.push('row-abnormal')
  if (isSubsequentCutoffInvalid(row, cutoffDate.value)) classes.push('row-cutoff-invalid')
  return classes.join(' ')
}

function isReasonFieldMissing(row: CalcCheckRow, prop: keyof CalcCheckRow): boolean {
  if (prop === 'varianceReason' || prop === 'indexNo') return needsVarianceReason(row)
  if (prop === 'decreaseIndexNo' || prop === 'decreaseRemark') return needsDecreaseExplain(row)
  return false
}

function getMainFormulaTooltip(prop: keyof CalcCheckRow): string {
  const tooltips: Partial<Record<keyof CalcCheckRow, string>> = {
    calculatedDividend: '应收股利(测算) = 持股数量 × 每股股利',
    calcByRatio: '比例×总额验算 = 持股比例(%) / 100 × 被投资方分红总额',
    calcVariance: '测算差异 = 账面已计股利 − 应收股利(测算)',
    decreaseDiff: '减少差异 = 本期减少 − 收现金额 − 其他减少金额',
  }
  return tooltips[prop] ?? '公式计算'
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

const showSamplingDialog = ref(false)

function openSamplingEngine() {
  if (samplingYear.value == null) {
    ElMessage.warning('未配置审计年度，无法打开期后抽凭（需推导次年）')
    return
  }
  showSamplingDialog.value = true
}

async function onPushToG33() {
  if (props.isReadonly) return
  try {
    await ElMessageBox.confirm(
      `将推送 ${calcCheck.totals.value.pushableVarianceCount} 个被投资方的测算/减少差异草稿至 G3-3。推送后请打开 G3-3 核对借贷并点「确认调整」。是否继续？`,
      '差异推送 G3-3',
      { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  calcCheck.pushVariancesToAdjustment()
}

function handleSamplingFilled(payload: { samples: SampledVoucher[] } | SampledVoucher[]) {
  const samples = Array.isArray(payload) ? payload : (payload?.samples ?? [])
  if (!samples.length) return
  const mapped = samples.map((s) => {
    const debit = parseFloat(s.debitAmount ?? '0') || 0
    const credit = parseFloat(s.creditAmount ?? '0') || 0
    return {
      voucherDate: s.voucherDate ?? '',
      voucherNo: s.voucherNo ?? '',
      summary: s.summary ?? '',
      counterAccount: s.counterpartAccount ?? '',
      debitAmount: debit,
      creditAmount: credit,
      amount: debit || credit,
      investeeName: s.accountName ?? '',
    }
  })
  const { filled } = calcCheck.fillFromSamples(mapped, { cutoffDate: cutoffDate.value })
  showSamplingDialog.value = false
  if (filled > 0) ElMessage.success(`已填入 ${filled} 条期后抽凭样本`)
}

function onImported() {
  calcCheck.loadAll()
  emit('imported')
}
</script>

<style scoped>
.g3-calc-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.segment-tabs {
  margin-bottom: 0;
}

.segment-tabs :deep(.el-tabs__content) {
  display: none;
}

.calc-check-table {
  border-top: none;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
}

:deep(.row-variance-exceed) {
  background-color: #fdf6ec !important;
}
:deep(.row-variance-exceed td) {
  background-color: #fdf6ec !important;
}
:deep(.row-need-reason) {
  box-shadow: inset 3px 0 0 #e6a23c;
}
:deep(.row-cross-mismatch td) {
  background-color: #fdf6ec !important;
}
:deep(.row-abnormal) {
  background-color: #fef0f0 !important;
}
:deep(.row-abnormal td) {
  background-color: #fef0f0 !important;
}
:deep(.row-cutoff-invalid) {
  background-color: #fde2e2 !important;
}
:deep(.row-cutoff-invalid td) {
  background-color: #fde2e2 !important;
}

.meta-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.sampling-tip {
  margin-bottom: 10px;
}

.need-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.sample-flag {
  margin-left: 4px;
  font-size: 12px;
}

.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

.totals-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  flex-wrap: wrap;
}
.totals-label {
  color: #303133;
  min-width: 36px;
}
.total-item {
  color: #606266;
}
.total-item.warn {
  color: #e6a23c;
}

.audit-objective {
  margin-bottom: 8px;
}
.cross-ref-tip {
  margin-bottom: 12px;
}

.check-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 8px 10px;
  background: #f4f4f5;
  border: 1px solid #e4e7ed;
  border-top: none;
  font-size: 12px;
  color: #606266;
}
.check-hints-title {
  font-weight: 600;
  color: #303133;
}
.check-hint-item {
  white-space: nowrap;
}

.guidance-details {
  margin-top: 12px;
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
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
