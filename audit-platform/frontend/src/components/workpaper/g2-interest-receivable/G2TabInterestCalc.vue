<template>
  <div class="g2-interest-calc">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表独立测算应收利息，验证企业利息计提金额的准确性与完整性。</p>
        <p>2. 应计利息④ = 账面金额① × 票面年利率② × 计息天数③ / <strong>365</strong>（债券惯例，非 360 天）。</p>
        <p>3. 差异⑦ = 应计利息④ − 已计利息⑥；|差异| &gt; {{ calc.VARIANCE_THRESHOLD }} 元橙色高亮，须填写差异原因。</p>
        <p>4. 「已到期可收取⑤」对应报表「应收利息」口径；勾选「实际利率法」后利息进工具账面余额、⑤清零且不进 1132 勾稽。</p>
        <p>5. 从 G2-2 取数时按投资种类智能预填 EIR（债权投资/其他债权投资默认勾选，定期存款/委托贷款不勾）。</p>
        <p>6. ⑤合计（排除实际利率法）应与 G2-1 原值审定勾稽；导入导出列已含⑤/差异原因/EIR。</p>
        <p>7. 「写入 G2-1 对照」将⑤合计/差额写入 G2-1 审计说明（不改审定数，可重复覆盖对照块）。</p>
        <p>8. 依据：CAS 22《金融工具确认和计量》（实际利率法、应收利息确认）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="一、审计目标：确认应收利息的计算是否正确，独立测算应计利息并与企业已计利息核对，识别少计/多计风险。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-5 应收利息测算表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="calc.addRow()">新增测算行</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="onPullFromDetail">
          从 G2-2 取数
        </el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="onPushToG21">
          写入 G2-1 对照
        </el-button>
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-5"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ calc.dataRows.value.length }} 行</el-tag>
        <el-tag v-if="calc.warningCount.value > 0" size="small" type="warning">
          异常 {{ calc.warningCount.value }}
        </el-tag>
        <el-button size="small" @click="openReviewDialog('G2-5-interest-calc')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="calc.crossCheck.value.detailRowCount > 0 && !calc.crossCheck.value.matched"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`与 G2-2 计息勾稽差异：本表应计 ${fmtNum(calc.crossCheck.value.calcAccruedTotal)} ≠ 明细测算 ${fmtNum(calc.crossCheck.value.detailAccruedTotal)}（差额 ${fmtNum(calc.crossCheck.value.diff)}）`"
    />
    <el-alert
      v-else-if="calc.crossCheck.value.detailRowCount > 0 && calc.crossCheck.value.matched"
      type="success"
      :closable="false"
      class="tie-alert"
      title="与 G2-2 明细计息基础勾稽一致"
    />
    <el-alert
      v-if="calc.missingReasonCount.value > 0"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`有 ${calc.missingReasonCount.value} 行 |差异| > ${calc.VARIANCE_THRESHOLD} 元尚未填写差异原因`"
    />
    <el-alert
      v-if="calc.adjTieOut.value.hasAdjData && !calc.adjTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-alert"
    >
      <template #title>
        <span>
          与 G2-1 原值勾稽差异：本表计入1132的⑤ {{ fmtNum(calc.adjTieOut.value.maturedFor1132) }}
          ≠ 审定原值 {{ fmtNum(calc.adjTieOut.value.adjGrossEnd) }}
          （差额 {{ fmtNum(calc.adjTieOut.value.diff) }}）
        </span>
        <el-button
          size="small"
          type="warning"
          link
          :disabled="isReadonly"
          style="margin-left: 8px"
          @click="onPushToG21"
        >
          写入对照说明
        </el-button>
      </template>
    </el-alert>
    <el-alert
      v-else-if="calc.adjTieOut.value.hasAdjData && calc.adjTieOut.value.matched"
      type="success"
      :closable="false"
      class="tie-alert"
      title="与 G2-1 原值审定勾稽一致（⑤已到期可收取 ↔ 应收利息原值）"
    />
    <el-alert
      v-if="calc.totals.value.eirRowCount > 0"
      type="info"
      :closable="false"
      class="tie-alert"
      :title="`实际利率法 ${calc.totals.value.eirRowCount} 行：应计利息 ${fmtNum(calc.totals.value.eirAccruedTotal)} 计入金融工具账面余额，不进科目 1132`"
    />

    <div class="section-label">二、审计过程</div>

    <el-table
      :data="calc.dataRows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
    >
      <el-table-column label="序号" prop="seq" width="50" align="center" fixed />
      <el-table-column label="投资项目" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investTarget"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => calc.updateCell(row.id, 'investTarget', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="实际利率法" width="88" align="center">
        <template #header>
          <div>实际利率法</div>
          <div class="col-sub">进工具余额</div>
        </template>
        <template #default="{ row }">
          <el-checkbox
            :model-value="row.eirInInstrument"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => calc.setEirInInstrument(row.id, Boolean(v))"
          />
        </template>
      </el-table-column>
      <el-table-column label="账面金额①" width="118" align="right">
        <template #default="{ row }">
          <WpAmountInput
            :model-value="row.faceValue"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'faceValue', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="票面年利率②" width="108" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.couponRate"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            :precision="4"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'couponRate', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="计息开始日期" width="128">
        <template #default="{ row }">
          <el-date-picker
            :model-value="row.accrualStart"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => calc.updateCell(row.id, 'accrualStart', v ?? '')"
          />
        </template>
      </el-table-column>
      <el-table-column label="计息结束日期" width="128">
        <template #default="{ row }">
          <el-date-picker
            :model-value="row.accrualEnd"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => calc.updateCell(row.id, 'accrualEnd', v ?? '')"
          />
        </template>
      </el-table-column>
      <el-table-column label="计息天数③" width="88" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="③ = 结束日 − 开始日">{{ row.accruedDays || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应计利息④" width="118" align="right" class-name="auto-calc-col">
        <template #header>
          <div>应计利息④</div>
          <div class="col-sub">①×②×③/365</div>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" title="④ = ① × ② × ③ / 365">{{ fmtNum(row.calculatedInterest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="其中：已到期可收取⑤" width="128" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!row.eirInInstrument"
            :model-value="row.maturedCollectible"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            :class="{ 'input-warn': calc.isMaturedOverAccrued(row) }"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'maturedCollectible', v ?? 0)"
          />
          <span v-else class="eir-muted" title="实际利率法：不进 1132">—</span>
        </template>
      </el-table-column>
      <el-table-column label="已计利息⑥" width="118" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.companyAccrual"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'companyAccrual', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="差异⑦" width="108" align="right" class-name="auto-calc-col">
        <template #header>
          <div>差异⑦</div>
          <div class="col-sub">④−⑥</div>
        </template>
        <template #default="{ row }">
          <span
            :class="['formula-cell', { 'variance-warn': calc.isVarianceWarning(row) }]"
            title="⑦ = ④应计利息 − ⑥已计利息"
          >
            {{ fmtNum(row.variance) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="差异原因" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.varianceReason"
            size="small"
            :disabled="isReadonly"
            :placeholder="calc.isVarianceReasonRequired(row) ? '必填：说明差异原因' : '差异原因'"
            :class="{ 'reason-required': calc.isVarianceReasonRequired(row) }"
            @change="(v: string) => calc.updateCell(row.id, 'varianceReason', v)"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="calc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">测算合计</span>
        账面金额 {{ fmtNum(calc.totals.value.faceValue) }} ·
        应计利息④ {{ fmtNum(calc.totals.value.calculatedInterest) }} ·
        已到期可收取⑤ {{ fmtNum(calc.totals.value.maturedCollectible) }} ·
        <span class="hl-1132">计入1132 {{ fmtNum(calc.totals.value.maturedFor1132) }}</span>
        ·
        已计利息⑥ {{ fmtNum(calc.totals.value.companyAccrual) }} ·
        差异⑦ {{ fmtNum(calc.totals.value.variance) }}
      </div>
      <div v-if="calc.totals.value.eirRowCount > 0" class="eir-total">
        其中实际利率法 {{ calc.totals.value.eirRowCount }} 行应计 {{ fmtNum(calc.totals.value.eirAccruedTotal) }}（进工具账面，不进 1132）
      </div>
    </div>

    <p class="excel-footnote">
      注：应收利息仅反映资产负债表日已到期可收取但尚未收到的利息。对于按实际利率法核算的金融工具，其利息应计入相应金融工具的账面余额。
    </p>

    <div class="section-label">三、审计说明 / 四、审计结论</div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="interest-calc-note"
      conclusion-ai-section="interest-calc-conclusion"
      :related-context="{
        测算行数: calc.dataRows.value.length,
        应计利息合计: calc.totals.value.calculatedInterest,
        已到期可收取合计: calc.totals.value.maturedCollectible,
        计入1132: calc.totals.value.maturedFor1132,
        实际利率法行数: calc.totals.value.eirRowCount,
        已计利息合计: calc.totals.value.companyAccrual,
        差异合计: calc.totals.value.variance,
        异常行数: calc.warningCount.value,
        G2_1勾稽: calc.adjTieOut.value.matched ? '一致' : '差异',
      }"
      note-placeholder="填写审计说明：（1）独立测算程序与 365 天基准；（2）与企业已计利息差异及原因；（3）已到期可收取与 G2-1/报表应收利息勾稽；（4）实际利率法项目利息进工具余额情况；（5）与 G2-2 交叉核对。"
      note-hint="覆盖应计利息测算、已到期可收取口径、实际利率法排除、差异分析及与审定表勾稽。"
      conclusion-placeholder="评价利息计提准确性（可按 A/B/C 口径），并说明对审定表/附注的影响。"
      conclusion-hint="按 A/B/C 口径评价利息计提准确性；重大差异须说明调整建议。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, toRef, computed, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG2InterestCalc } from '../composables/useG2InterestCalc'
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
const projectId = computed(() => props.projectId ?? '')

const calc = useG2InterestCalc({
  wpId: computed(() => props.wpId ?? ''),
  projectId: computed(() => props.projectId ?? ''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtNum(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v !== 'number' || !Number.isFinite(v)) return String(v ?? '—')
  if (v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: { id: string } }) {
  const r = calc.dataRows.value.find((x) => x.id === row.id)
  if (!r) return ''
  if (r.eirInInstrument) return 'row-eir'
  if (calc.isMaturedOverAccrued(r) || calc.isVarianceReasonRequired(r)) return 'row-warn'
  if (calc.isVarianceWarning(r)) return 'row-variance'
  return ''
}

async function onPullFromDetail() {
  if (props.isReadonly) return
  const hasRows = calc.dataRows.value.length > 0
  if (hasRows) {
    try {
      await ElMessageBox.confirm(
        '将用 G2-2 明细中含计息基础的行覆盖本表测算数据，是否继续？',
        '从 G2-2 取数',
        { type: 'warning', confirmButtonText: '覆盖取数', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  const { pulled } = calc.pullFromDetail(true)
  if (pulled === 0) {
    ElMessage.warning('G2-2 明细中暂无可取的计息行（需面值/利率/起止日）')
    return
  }
  ElMessage.success(`已从 G2-2 拉取 ${pulled} 行测算数据`)
}

function onPushToG21() {
  if (props.isReadonly) return
  const res = calc.pushCrossRefToG21()
  if (!res.ok) {
    ElMessage.warning('当前只读，无法写入')
    return
  }
  if (res.matched) {
    ElMessage.success(`已写入 G2-1 审计说明：计入1132的⑤ = ${fmtNum(res.maturedFor1132)}（勾稽一致）`)
  } else {
    ElMessage.warning(`已写入 G2-1 对照说明：⑤ = ${fmtNum(res.maturedFor1132)}，与审定原值存在差额，请在 G2-1 核查`)
  }
}

const NOTE_KEY = 'G2-5-audit-note'
const CONCLUSION_KEY = 'G2-5-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (v != null) auditNote.value = v })
watch(() => props.allResponses.get(CONCLUSION_KEY)?.remark, (v) => { if (v != null) auditConclusion.value = v })
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})
</script>

<style scoped>
.g2-interest-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-interest-calc :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.g2-interest-calc :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert, .tie-alert { margin-bottom: 10px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-label {
  margin: 10px 0 6px;
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}
.col-sub { font-size: 11px; color: #909399; font-weight: 400; line-height: 1.2; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-variant-numeric: tabular-nums; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.variance-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.input-warn :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.g2-interest-calc :deep(.row-variance) { background: #fdf6ec; }
.g2-interest-calc :deep(.row-warn) { background: #fef0f0; }
.g2-interest-calc :deep(.row-eir) { background: #f0f9eb; }
.eir-muted { color: #909399; }
.hl-1132 { color: #409eff; }
.eir-total { margin-top: 4px; font-size: 12px; color: #67c23a; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #dcdfe6;
  font-weight: 600;
  color: #303133;
}
.excel-footnote {
  margin: 10px 0 4px;
  padding: 8px 10px;
  font-size: 12px;
  color: #606266;
  background: #fafafa;
  border-left: 3px solid #c0c4cc;
  line-height: 1.5;
}
</style>
