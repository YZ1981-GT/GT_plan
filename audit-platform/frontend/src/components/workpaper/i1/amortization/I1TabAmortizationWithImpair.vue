<template>
  <div class="i1-tab-amort-with-impair">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><b>CAS6剩余年限法（含减值）：</b>减值后月摊销 = (原值 - 残值 - 累计摊销 - 减值准备) ÷ 剩余月数。在减值发生月重新计算摊销基数，减值后各月使用新的月摊销额。适用于已计提减值准备的无形资产。63公式。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实含减值情形下无形资产摊销的重算基数与计算准确性，验证减值发生月后摊销基数调整的恰当性，确保摊销费用列报准确。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ currentRows.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I1-11 摊销测算表（含减值）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSyncFromDetail">
              同步I1-2参数
            </el-button>
            <el-button size="small" type="default" link @click="handleReview">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="currentRows"
        border
        stripe
        size="small"
        max-height="520"
        class="amort-matrix-table"
        show-summary
        :summary-method="getSummaryRow"
      >
        <el-table-column type="index" label="#" width="35" fixed />
        <el-table-column prop="name" label="资产名称" width="120" fixed show-overflow-tooltip />
        <el-table-column label="原值" width="100" align="right" fixed>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.cost"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'cost', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="残值" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.salvage"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'salvage', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.salvage) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.accAmortBegin"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'accAmortBegin', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.accAmortBegin) }}</span>
          </template>
        </el-table-column>
        <!-- 减值准备列 -->
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairment"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'impairment', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余月数" width="75" align="center">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.remainingMonths"
              :controls="false"
              size="small"
              :min="0"
              :max="600"
              class="cell-input"
              @change="handleRemainingChange($index, $event)"
            />
            <span v-else>{{ row.remainingMonths }}</span>
          </template>
        </el-table-column>
        <!-- 减值发生月 -->
        <el-table-column label="减值发生月" width="90" align="center">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairmentMonth"
              :controls="false"
              size="small"
              :min="0"
              :max="28"
              class="cell-input impair-month-input"
              @change="handleImpairMonthChange($index, row.impairmentMonth, row.impairmentAmountAtMonth)"
            />
            <span v-else :class="{ 'impair-month-highlight': row.impairmentMonth > 0 }">
              {{ row.impairmentMonth > 0 ? `第${row.impairmentMonth}月` : '-' }}
            </span>
          </template>
        </el-table-column>
        <!-- 减值金额 -->
        <el-table-column label="减值金额" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairmentAmountAtMonth"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleImpairMonthChange($index, row.impairmentMonth, $event ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentAmountAtMonth) }}</span>
          </template>
        </el-table-column>
        <!-- 月摊销额 -->
        <el-table-column label="月摊销额" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="减值后月摊销=(原值-残值-累计摊销-减值)÷剩余月数"
            >{{ fmtAmt(row.monthlyAmortAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 28个月列 -->
        <el-table-column
          v-for="m in MATRIX_COLUMNS"
          :key="m"
          :label="`第${m}月`"
          width="78"
          align="right"
          :class-name="getMonthColumnClass(m)"
        >
          <template #default="{ row }">
            <span
              :class="[
                'formula-cell',
                { 'impair-recalc-cell': row.impairmentMonth === m }
              ]"
              :title="getMonthTooltip(row, m)"
            >{{ fmtAmt(row.monthlyAmort[m - 1]) }}</span>
          </template>
        </el-table-column>

        <!-- 本期合计 -->
        <el-table-column label="本期合计" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="本期合计=SUM(第1月~第28月)"
            >{{ fmtAmt(row.periodAmortization) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行独立展示 -->
      <div class="totals-bar">
        <span>摊销合计: <b class="amount-cell">{{ fmtAmt(summaryRow.periodTotal) }}</b></span>
        <span>减值合计: <b class="amount-cell impair-amount">{{ fmtAmt(totalImpairment) }}</b></span>
        <span>资产数: <b>{{ currentRows.length }}</b> 项</span>
        <span v-if="impairmentCount > 0" class="impair-badge">
          含减值资产: {{ impairmentCount }} 项
        </span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：减值对摊销测算的影响、减值发生月后重算基数核对情况、差异原因分析等。"
        @blur="handleSaveNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：含减值情形下摊销重算基数与计算准确，减值后各月摊销额恰当，未见异常等。"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>含减值剩余年限法：月摊销 = (原值 - 残值 - 累计摊销 - 减值准备) ÷ 剩余月数</li>
        <li>"减值发生月"：填写1~28之间的月份编号（0表示无减值）</li>
        <li>"减值金额"：填写该月新增计提的减值准备金额</li>
        <li>减值发生月之后的月份将使用新的摊销基数重算（红色高亮"重算基数"）</li>
        <li>28列对应审计期间内每月的摊销额</li>
        <li>若资产已摊销完毕（剩余月数≤0），该行摊销额显示为0</li>
        <li>点击"同步I1-2参数"可从明细表自动导入资产信息（含减值期末余额）</li>
        <li>如无减值情况请切换到"不含减值（I1-10）"分支</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useI1Amortization, type I1AmortizationRow, type I1AssetParams } from '../../composables/useI1Amortization'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  currentRows,
  currentItemId,
  summaryRow,
  MATRIX_COLUMNS,
  recalcAll,
  recalcRow,
  syncFromDetail,
  updateRowField,
  setImpairmentMonth,
} = useI1Amortization(toRef(props, 'wpId'), allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── State ───────────────────────────────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

// Load note / conclusion from allResponses
watch(() => props.allResponses, (responses) => {
  const item = responses.get('I1-11-note')
  if (item) {
    auditNote.value = (item as any).remark ?? (item as any).conclusion ?? ''
  }
  const conc = responses.get('I1-11-conclusion')
  if (conc) {
    auditConclusion.value = (conc as any).remark ?? (conc as any).conclusion ?? ''
  }
}, { immediate: true })

// ─── Computed ────────────────────────────────────────────────────────────────

/** 含减值的资产数量 */
const impairmentCount = computed(() => {
  return currentRows.value.filter(r => r.impairment > 0 || r.impairmentAmountAtMonth > 0).length
})

/** 减值准备总额 */
const totalImpairment = computed(() => {
  return currentRows.value.reduce((sum, r) => sum + (r.impairment ?? 0), 0)
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleFieldChange(rowIndex: number, field: keyof I1AmortizationRow, value: number | null) {
  updateRowField(rowIndex, field, value ?? 0)
}

function handleRemainingChange(rowIndex: number, value: number | null) {
  const rows = currentRows.value
  const row = rows[rowIndex]
  if (!row) return
  row.remainingMonths = value ?? 0
  row.usefulLifeMonths = row.usedMonths + (value ?? 0)
  recalcRow(rowIndex)
}

function handleImpairMonthChange(rowIndex: number, month: number, amount: number) {
  setImpairmentMonth(rowIndex, month ?? 0, amount ?? 0)
}

async function handleSyncFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将从I1-2明细表同步资产参数（名称/原值/残值/使用寿命/减值准备），现有手工调整将被覆盖。是否继续？',
      '同步I1-2参数',
      { confirmButtonText: '确定同步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  // Extract asset params from allResponses I1-2 detail data
  const detailData = props.allResponses.get('I1-2-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessageBox.alert('未找到I1-2明细表数据，请先完善明细表。', '提示')
    return
  }

  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessageBox.alert('I1-2明细表暂无资产数据。', '提示')
      return
    }
    const assetParams: I1AssetParams[] = parsed.map((item: any) => ({
      rowId: item.rowId ?? '',
      name: item.name ?? item.assetName ?? '',
      cost: Number(item.cost ?? item.originalCost ?? 0),
      salvageRate: Number(item.salvageRate ?? 0),
      usefulLifeMonths: Number(item.usefulLifeMonths ?? item.usefulLife ?? 0),
      accAmortBegin: Number(item.accAmortBegin ?? item.accumulatedAmort ?? 0),
      impairmentEnd: Number(item.impairmentEnd ?? item.impairment ?? 0),
    }))
    syncFromDetail(assetParams)
  } catch {
    ElMessageBox.alert('I1-2明细表数据解析失败。', '错误')
  }
}

function handleReview() {
  openReviewDialog('I1-11')
}

function handleSaveNote() {
  emit('save', 'I1-11-note', auditNote.value)
}

function handleSaveConclusion() {
  emit('save', 'I1-11-conclusion', auditConclusion.value)
}

// ─── Month column helpers ────────────────────────────────────────────────────

function getMonthColumnClass(month: number): string {
  // Check if any row has impairment at this month
  const hasImpair = currentRows.value.some(r => r.impairmentMonth === month)
  return hasImpair ? 'impair-month-col' : ''
}

function getMonthTooltip(row: I1AmortizationRow, month: number): string {
  if (row.impairmentMonth === month) {
    return `第${month}月 — 减值发生月，重算基数=(原值-残值-累计摊销-减值)÷剩余月数`
  }
  if (row.impairmentMonth > 0 && month > row.impairmentMonth) {
    return `第${month}月 — 使用减值后新基数计算`
  }
  return `第${month}月摊销额`
}

// ─── Summary method for el-table ─────────────────────────────────────────────

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const sums: string[] = []
  // Column mapping for with-impair variant:
  // 0: index, 1: name, 2: cost, 3: salvage, 4: accAmortBegin,
  // 5: impairment, 6: remainingMonths, 7: impairmentMonth, 8: impairmentAmountAtMonth,
  // 9: monthlyAmortAmount, 10~37: months, 38: periodAmortization
  columns.forEach((col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (index === 1) { sums[index] = ''; return }
    // cost
    if (index === 2) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.cost ?? 0), 0)); return }
    // salvage
    if (index === 3) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.salvage ?? 0), 0)); return }
    // accAmortBegin
    if (index === 4) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.accAmortBegin ?? 0), 0)); return }
    // impairment
    if (index === 5) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.impairment ?? 0), 0)); return }
    // remainingMonths — no sum
    if (index === 6) { sums[index] = '-'; return }
    // impairmentMonth — no sum
    if (index === 7) { sums[index] = '-'; return }
    // impairmentAmountAtMonth
    if (index === 8) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.impairmentAmountAtMonth ?? 0), 0)); return }
    // monthlyAmortAmount
    if (index === 9) { sums[index] = fmtAmt(data.reduce((s, r) => s + (r.monthlyAmortAmount ?? 0), 0)); return }
    // month columns (index 10 to 10+27=37)
    const monthIdx = index - 10
    if (monthIdx >= 0 && monthIdx < 28) {
      sums[index] = fmtAmt(summaryRow.value.monthlyTotals[monthIdx] ?? 0)
      return
    }
    // periodAmortization (index 38)
    if (index === 38) {
      sums[index] = fmtAmt(summaryRow.value.periodTotal)
      return
    }
    sums[index] = ''
  })
  return sums
}

// ─── Util ────────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-amort-with-impair {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
}

.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.amort-matrix-table {
  font-size: 12px;
}

.amort-matrix-table :deep(.el-table__footer) {
  font-weight: 600;
  background: var(--el-fill-color-light);
}

.cell-input {
  width: 100%;
}

.cell-input :deep(.el-input__inner) {
  text-align: right;
  font-size: 12px;
}

.impair-month-input :deep(.el-input__inner) {
  text-align: center;
}

.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 减值发生月红色高亮 */
.impair-recalc-cell {
  color: var(--el-color-danger);
  font-weight: 600;
  border-bottom-color: var(--el-color-danger);
  position: relative;
}

.impair-recalc-cell::after {
  content: '重算';
  position: absolute;
  top: -14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--el-color-danger);
  white-space: nowrap;
  font-weight: 400;
}

.impair-month-highlight {
  color: var(--el-color-danger);
  font-weight: 600;
}

.impair-amount {
  color: var(--el-color-danger);
}

.impair-badge {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.totals-bar {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  align-items: center;
}

.note-card {
  margin-top: 12px;
}

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}

.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
