<template>
  <div class="i1-tab-amort-with-impair">
    <div class="methodology-context">
      <p>
        <b>CAS6 剩余年限法（含减值）：</b>
        减值前月摊销＝原值÷摊销期限月；减值后月摊销＝(原值−残值−减值时累计摊销−减值准备)÷剩余月数。
        本期摊销＝减值前月数×原月摊销＋减值后月数×新月摊销。对齐源表 I1-11 分段公式。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：检查无形资产本期计提的摊销是否合理；核实含减值情形下重算基数与分段月数，核对测算与账面差异。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="period-label">期初日</span>
        <el-date-picker
          v-model="localPeriodBegin"
          type="date"
          value-format="YYYY-MM-DD"
          size="small"
          :disabled="isReadonly"
          placeholder="期初"
          style="width: 140px"
          @change="onPeriodChange"
        />
        <span class="period-label">截止日</span>
        <el-date-picker
          v-model="localPeriodEnd"
          type="date"
          value-format="YYYY-MM-DD"
          size="small"
          :disabled="isReadonly"
          placeholder="截止日"
          style="width: 140px"
          @change="onPeriodChange"
        />
        <el-button size="small" :disabled="isReadonly" @click="recalcAll">重新测算</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="warning">含减值 · {{ currentRows.length }} 行</el-tag>
        <el-tag v-if="significantDiffCount > 0" size="small" type="danger">
          差异行 {{ significantDiffCount }}
        </el-tag>
        <el-tag size="small" type="info">减值合计 {{ fmtAmt(totalImpairment) }}</el-tag>
        <el-tag
          size="small"
          :type="amortReconcile.matchedAdj ? 'success' : 'warning'"
          class="nav-chip"
          @click="emit('navigate-sheet', 'I1-1')"
        >
          {{ amortReconcile.matchedAdj ? 'I1-1本期计提已勾稽' : 'I1-1本期计提待勾稽' }}
        </el-tag>
        <el-tag
          v-if="amortReconcile.allocTotal !== 0"
          size="small"
          :type="amortReconcile.matchedAlloc ? 'success' : 'warning'"
          class="nav-chip"
          @click="emit('navigate-sheet', 'I1-9')"
        >
          {{ amortReconcile.matchedAlloc ? 'I1-9分配已勾稽' : 'I1-9分配待勾稽' }}
        </el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-1')">← I1-1</el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-9')">I1-9 →</el-tag>
      </div>
    </div>

    <el-alert
      v-if="!amortReconcile.matchedAdj && amortReconcile.periodAmortTotal !== 0"
      type="warning"
      :closable="false"
      show-icon
      class="reconcile-alert"
      :title="`测算本期合计 ${fmtAmt(amortReconcile.periodAmortTotal)} 与 I1-1 摊销本期增加 ${fmtAmt(amortReconcile.adjudicatedProvision)} 差异 ${fmtAmt(amortReconcile.vsAdjDiff)}`"
    />

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I1-11 累计摊销测算表（含减值）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
              + 新增行
            </el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncFromDetail">
              同步I1-2参数
            </el-button>
            <el-button size="small" plain :disabled="isReadonly" data-testid="i1-11-sync-life" @click="handleSyncFromUsefulLife">
              应用I1-7寿命
            </el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleSyncFromI12">
              联动I1-12
            </el-button>
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
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
        :row-class-name="getRowClass"
        show-summary
        :summary-method="getSummaryRow"
      >
        <el-table-column type="index" label="#" width="40" fixed />
        <el-table-column prop="category" label="无形资产类别" width="110" fixed>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              clearable
              @change="handleFieldChange($index, 'category', $event)"
            >
              <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="明细项目" min-width="120" fixed show-overflow-tooltip>
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              v-model="row.name"
              size="small"
              @change="handleFieldChange($index, 'name', $event)"
            />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原值" width="100" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.cost"
              size="small"
              class="cell-input"
              @change="handleFieldChange($index, 'cost', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面累计摊销" width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.bookAccAmortEnd"
              size="small"
              class="cell-input"
              @change="handleFieldChange($index, 'bookAccAmortEnd', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAccAmortEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.impairment"
              size="small"
              class="cell-input"
              @change="handleFieldChange($index, 'impairment', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提减值准备日期" width="130">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.impairmentDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="handleFieldChange($index, 'impairmentDate', $event)"
            />
            <span v-else>{{ row.impairmentDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始使用日期" width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.startDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="handleFieldChange($index, 'startDate', $event)"
            />
            <span v-else>{{ row.startDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用期限(年)" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.usefulLifeYears"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleUsefulLifeChange($index, $event)"
            />
            <span v-else>{{ row.usefulLifeYears }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面月摊销额" width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.bookMonthly"
              size="small"
              class="cell-input"
              @change="handleFieldChange($index, 'bookMonthly', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookMonthly) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摊销期限(月)" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="使用期限×12">{{ row.usefulLifeMonths || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="测算到期日" width="100" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.fullAmortDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已摊销月份" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.monthsAmortized }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余摊销月份" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.remainingMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="截止减值日累计摊销月" width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'impair-month-highlight': row.monthsToImpairment > 0 }">
              {{ row.monthsToImpairment || '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="本期摊销月份" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="源表原「本期折旧月份」，已改为摊销">{{ row.periodMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值前月数" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.monthsBeforeImpairment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值后月数" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.monthsAfterImpairment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值前月摊销额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="(原值−残值)÷摊销期限月">{{ fmtAmt(row.preMonthly) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值时测算累计摊销" width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.accAmortAtImpairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值后月摊销额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-cell impair-recalc-cell"
              title="(原值−残值−减值时累计摊销−减值)÷剩余月数"
            >{{ fmtAmt(row.postMonthly) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当期摊销费用" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="减值前月数×原月摊销＋减值后月数×新月摊销"
            >{{ fmtAmt(row.periodAmortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月摊销额差异" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-danger': Math.abs(row.monthlyDiff) > 0.01 }"
              title="账面月摊销−减值后月摊销"
            >{{ fmtAmt(row.monthlyDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销(测算)" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.calcAccAmort) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销差异" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-danger': Math.abs(row.accAmortDiff) > 0.01 }"
              title="账面累计摊销−测算累计摊销"
            >{{ fmtAmt(row.accAmortDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleRemoveRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="totals-bar">
        <span>测算本期合计: <b class="amount-cell">{{ fmtAmt(summaryRow.periodTotal) }}</b></span>
        <span>账面月摊销合计: <b class="amount-cell">{{ fmtAmt(totalBookMonthly) }}</b></span>
        <span>
          累计差异合计:
          <b class="amount-cell" :class="{ 'text-danger': Math.abs(totalAccDiff) > 0.01 }">
            {{ fmtAmt(totalAccDiff) }}
          </b>
        </span>
        <span>减值合计: <b class="amount-cell impair-amount">{{ fmtAmt(totalImpairment) }}</b></span>
        <span v-if="impairmentCount > 0" class="impair-badge">含减值资产: {{ impairmentCount }} 项</span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：减值时点与金额来源（I1-12）、分段月数合理性、测算与账面差异原因等。"
        @blur="handleSaveNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="A、含减值摊销测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制提示</summary>
      <ul>
        <li>本表适用于<strong>已计提减值</strong>的无形资产；无减值请切换「不含减值（I1-10）」。</li>
        <li>减值后月摊销＝(原值−残值−减值时累计摊销−减值准备)÷剩余月数。</li>
        <li>当期摊销＝减值前月数×减值前月摊销＋减值后月数×减值后月摊销。</li>
        <li>源表「本期折旧月份」已统一为「本期摊销月份」；期间起止日驱动月数推算（对齐 DATEDIF）。</li>
        <li>行级「计提减值准备日期」优于源表全局减值日，便于逐项复核。</li>
        <li>点击「同步I1-2参数」导入原值/累计摊销/减值/取得日期/使用寿命。</li>
        <li>「联动I1-12」按名称回写⑦已计提；若有⑧补提则默认减值日=截止日。</li>
        <li>差异列红色高亮时，应分析后决定调整或披露。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * I1TabAmortizationWithImpair.vue — I1-11 摊销测算表（含减值）
 * 对齐源 xlsx「累计摊销测算表 I1-11」分段逻辑（Q~W + 月数 I~P）
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI1Amortization, type I1AmortizationRow, type I1AssetParams } from '../../composables/useI1Amortization'
import GtIndexChip from '../../GtIndexChip.vue'

const CATEGORIES = [
  '土地使用权',
  '房屋使用权',
  '专利权',
  '非专利技术',
  '商标权',
  '著作权',
  '特许权',
  '软件',
  '矿产权',
  '数据资源',
  '其他',
]

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

const allResponsesRef = computed(() => props.allResponses)

const {
  currentRows,
  summaryRow,
  periodBegin,
  periodEnd,
  amortReconcile,
  recalcAll,
  syncFromDetail,
  syncFromUsefulLife,
  syncFromImpairment,
  updateRowField,
  setPeriod,
  addRow,
  removeRow,
  switchBranch,
  exportXlsx,
  importXlsx,
} = useI1Amortization(toRef(props, 'wpId'), allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

switchBranch('withImpair', false)

const auditNote = ref('')
const auditConclusion = ref('')
const localPeriodBegin = ref('')
const localPeriodEnd = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

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

watch([periodBegin, periodEnd], ([b, e]) => {
  localPeriodBegin.value = b || ''
  localPeriodEnd.value = e || ''
}, { immediate: true })

const impairmentCount = computed(() =>
  currentRows.value.filter(r => (r.impairment ?? 0) > 0 || !!r.impairmentDate).length,
)

const totalImpairment = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.impairment ?? 0), 0),
)

const totalBookMonthly = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.bookMonthly ?? 0), 0),
)

const totalAccDiff = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.accAmortDiff ?? 0), 0),
)

const significantDiffCount = computed(() =>
  currentRows.value.filter(r => Math.abs(r.accAmortDiff ?? 0) > 0.01 || Math.abs(r.monthlyDiff ?? 0) > 0.01).length,
)

function handleFieldChange(rowIndex: number, field: keyof I1AmortizationRow, value: number | string | null) {
  updateRowField(rowIndex, field, value ?? (typeof value === 'number' ? 0 : ''))
}

function handleUsefulLifeChange(rowIndex: number, value: number | null) {
  const years = value ?? 0
  updateRowField(rowIndex, 'usefulLifeYears', years)
  updateRowField(rowIndex, 'usefulLifeMonths', Math.round(years * 12))
}

function onPeriodChange() {
  setPeriod(localPeriodBegin.value || '', localPeriodEnd.value || '')
}

function handleAddRow() {
  addRow({
    name: '',
    cost: 0,
    salvage: 0,
    usefulLifeMonths: 0,
  })
}

function handleRemoveRow(index: number) {
  removeRow(index)
}

async function handleSyncFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将从I1-2明细表同步资产参数（类别/名称/原值/累计摊销/减值/取得日期/使用寿命），现有手工调整的日期与账面月摊销将被尽量保留。是否继续？',
      '同步I1-2参数',
      { confirmButtonText: '确定同步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

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
      category: item.category ?? '',
      cost: Number(item.costEnd ?? item.cost ?? item.originalCost ?? 0),
      salvageRate: Number(item.salvageRate ?? 0),
      usefulLifeMonths: Number(item.usefulLifeMonths ?? item.usefulLife ?? 0),
      accAmortBegin: Number(item.accAmortBegin ?? item.accumulatedAmort ?? 0),
      accAmortEnd: Number(item.accAmortEnd ?? item.accAmortBegin ?? 0),
      impairmentEnd: Number(item.impairmentEnd ?? item.impairment ?? 0),
      acquisitionDate: item.acquisitionDate ?? item.startDate ?? '',
      amortProvision: Number(item.amortProvision ?? 0),
    }))
    syncFromDetail(assetParams)
  } catch {
    ElMessageBox.alert('I1-2明细表数据解析失败。', '错误')
  }
}

function handleSyncFromUsefulLife() {
  const r = syncFromUsefulLife()
  if (r.updated > 0) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
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

async function handleSyncFromI12() {
  const detailData = props.allResponses.get('I1-12-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessage.warning('未找到 I1-12 数据，请先完成减值测试。')
    return
  }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(parsed) || !parsed.length) {
      ElMessage.warning('I1-12 暂无行数据。')
      return
    }
    const r = syncFromImpairment(
      parsed.map((item: any) => ({
        rowId: item.rowId ?? item.sourceDetailRowId,
        name: item.name ?? '',
        category: item.category ?? '',
        cost: Number(item.cost ?? 0),
        accAmort: Number(item.accAmort ?? 0),
        alreadyProvided: Number(item.alreadyProvided ?? item.impairmentProvision ?? 0),
        supplement: Number(item.supplement ?? 0),
      })),
      { defaultImpairmentDate: localPeriodEnd.value || periodEnd.value, createMissing: true },
    )
    ElMessage({ type: r.linked + r.added > 0 ? 'success' : 'warning', message: r.message })
  } catch {
    ElMessage.error('I1-12 数据解析失败')
  }
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportXlsx('template')
  else if (cmd === 'export-data') await exportXlsx('data')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const r = await importXlsx(file, true)
    ElMessage.success(`已导入 ${r.imported} 行`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  }
}

function getRowClass({ row }: { row: I1AmortizationRow }) {
  if (Math.abs(row.accAmortDiff ?? 0) > 0.01 || Math.abs(row.monthlyDiff ?? 0) > 0.01) {
    return 'diff-row'
  }
  if ((row.impairment ?? 0) > 0) return 'impair-row'
  return ''
}

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const sumKeys: Partial<Record<string, keyof I1AmortizationRow>> = {
    cost: 'cost',
    bookAccAmortEnd: 'bookAccAmortEnd',
    impairment: 'impairment',
    bookMonthly: 'bookMonthly',
    periodAmortization: 'periodAmortization',
    monthlyDiff: 'monthlyDiff',
    calcAccAmort: 'calcAccAmort',
    accAmortDiff: 'accAmortDiff',
    preMonthly: 'preMonthly',
    postMonthly: 'postMonthly',
    accAmortAtImpairment: 'accAmortAtImpairment',
  }
  const labelToKey: Record<string, keyof I1AmortizationRow> = {
    原值: 'cost',
    账面累计摊销: 'bookAccAmortEnd',
    减值准备: 'impairment',
    账面月摊销额: 'bookMonthly',
    当期摊销费用: 'periodAmortization',
    月摊销额差异: 'monthlyDiff',
    '累计摊销(测算)': 'calcAccAmort',
    累计摊销差异: 'accAmortDiff',
    减值前月摊销额: 'preMonthly',
    减值后月摊销额: 'postMonthly',
    减值时测算累计摊销: 'accAmortAtImpairment',
  }

  return columns.map((col: any, index: number) => {
    if (index === 0) return '合计'
    const key = (col.property && sumKeys[col.property]) || labelToKey[col.label]
    if (!key) return ''
    const total = data.reduce((s, r) => s + Number((r as any)[key] ?? 0), 0)
    return fmtAmt(total)
  })
}

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
.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.nav-chip { cursor: pointer; }
.reconcile-alert { margin-bottom: 12px; }
.period-label { font-size: 12px; color: var(--el-text-color-secondary); }
.chip-wrap { display: inline-flex; align-items: center; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.title-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.amort-matrix-table { font-size: 12px; }
.amort-matrix-table :deep(.el-table__footer) {
  font-weight: 600;
  background: var(--el-fill-color-light);
}
.amort-matrix-table :deep(.diff-row) { background: var(--el-color-danger-light-9); }
.amort-matrix-table :deep(.impair-row) { background: #fff7e6; }

.cell-input { width: 100%; }
.cell-input :deep(.el-input__inner) {
  text-align: right;
  font-size: 12px;
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

.impair-recalc-cell {
  color: var(--el-color-danger);
  font-weight: 600;
  border-bottom-color: var(--el-color-danger);
}

.impair-month-highlight {
  color: var(--el-color-danger);
  font-weight: 600;
}

.impair-amount { color: var(--el-color-danger); }
.text-danger { color: var(--el-color-danger); font-weight: 600; }

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
  gap: 20px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  align-items: center;
  flex-wrap: wrap;
}

.note-card { margin-top: 12px; }

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
