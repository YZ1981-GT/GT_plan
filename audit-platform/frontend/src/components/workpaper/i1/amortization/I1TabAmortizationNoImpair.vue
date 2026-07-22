<template>
  <div class="i1-tab-amort-no-impair">
    <div class="methodology-context">
      <p>
        <b>CAS6 剩余年限法（不含减值）：</b>
        期初净值 F＝原值−残值−累计摊销−期初减值；月摊销 K＝F÷剩余月数 J；
        本期摊销 M＝K×本期月数。与账面本期摊销核对差异。适用于本期无新减值重算场景。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实无形资产本期摊销额（剩余年限法，不含减值）计算准确性，验证摊销基数、剩余月数与账面一致。"
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
          style="width: 140px"
          @change="onPeriodChange"
        />
        <el-button size="small" :disabled="isReadonly" @click="recalcAll">重新测算</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-10" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">不含减值 · {{ currentRows.length }} 行</el-tag>
        <el-tag v-if="significantDiffCount > 0" size="small" type="danger">差异行 {{ significantDiffCount }}</el-tag>
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
          <span>I1-10 摊销测算表（不含减值·剩余年限法）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncFromDetail">
              同步I1-2参数
            </el-button>
            <el-button size="small" plain :disabled="isReadonly" data-testid="i1-10-sync-life" @click="handleSyncFromUsefulLife">
              应用I1-7寿命
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
        class="amort-table"
        :row-class-name="getRowClass"
        show-summary
        :summary-method="getSummaryRow"
      >
        <el-table-column type="index" label="#" width="40" fixed />
        <el-table-column prop="category" label="类别" width="100" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="handleFieldChange($index, 'category', $event)" />
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="明细项目" min-width="120" fixed show-overflow-tooltip>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="handleFieldChange($index, 'name', $event)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原值" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.cost"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'cost', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销期初" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.accAmortBegin"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'accAmortBegin', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.accAmortBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面累计摊销期末" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookAccAmortEnd"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'bookAccAmortEnd', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAccAmortEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面本期摊销" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookPeriodAmort"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'bookPeriodAmort', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookPeriodAmort) }}</span>
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
              style="width:100%"
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
              :precision="2"
              class="cell-input"
              @change="handleUsefulLifeChange($index, $event)"
            />
            <span v-else>{{ row.usefulLifeYears }}</span>
          </template>
        </el-table-column>
        <el-table-column label="残值" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.salvage"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'salvage', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.salvage) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初净值F" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="原值−残值−累计摊销−减值">{{ fmtAmt(row.beginNbv) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摊销期限(月)" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.usefulLifeMonths || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="测算到期日" width="100" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.fullAmortDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余月数J" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.remainingMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期月数" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期间四分支（已修正源表L虚增问题）">{{ row.periodMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月摊销额K" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="F÷J">{{ fmtAmt(row.monthlyAmortAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期摊销M" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" title="K×本期月数">{{ fmtAmt(row.periodAmortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期差异O" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': Math.abs(row.periodDiff) > 0.01 }" title="测算−账面">
              {{ fmtAmt(row.periodDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销(测算)" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.calcAccAmort) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计差异" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': Math.abs(row.accAmortDiff) > 0.01 }">
              {{ fmtAmt(row.accAmortDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="totals-bar">
        <span>测算本期合计: <b>{{ fmtAmt(summaryRow.periodTotal) }}</b></span>
        <span>账面本期合计: <b>{{ fmtAmt(totalBookPeriod) }}</b></span>
        <span>
          本期差异合计:
          <b :class="{ 'text-danger': Math.abs(totalPeriodDiff) > 0.01 }">{{ fmtAmt(totalPeriodDiff) }}</b>
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写：剩余月数核对、本期月数合理性、测算与账面差异原因；如有减值请切换 I1-11。"
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
        placeholder="A、剩余年限法摊销测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异。"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制提示</summary>
      <ul>
        <li>本表适用于<strong>本期无新减值重算</strong>；有减值请切换「含减值（I1-11）」。</li>
        <li>源表 L=DATEDIF(开始,截止)+1 会虚增已使用多年资产的「本期月数」，本表已改为期间四分支。</li>
        <li>K=F/J，M=K×本期月数，O=M−账面本期摊销。</li>
        <li>点击「同步I1-2」导入原值/累计摊销/取得日期/使用寿命/本期摊销。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabAmortizationNoImpair.vue — I1-10 摊销测算（不含减值·剩余年限法）
 * 对齐源表 F~O，修正本期月数虚增
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
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

switchBranch('noImpair', false)

const auditNote = ref('')
const auditConclusion = ref('')
const localPeriodBegin = ref('')
const localPeriodEnd = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

watch(() => props.allResponses, (responses) => {
  const item = responses.get('I1-10-note')
  if (item) auditNote.value = (item as any).remark ?? (item as any).conclusion ?? ''
  const conc = responses.get('I1-10-conclusion')
  if (conc) auditConclusion.value = (conc as any).remark ?? (conc as any).conclusion ?? ''
}, { immediate: true })

watch([periodBegin, periodEnd], ([b, e]) => {
  localPeriodBegin.value = b || ''
  localPeriodEnd.value = e || ''
}, { immediate: true })

const totalBookPeriod = computed(() =>
  currentRows.value.reduce((s, r) => s + (r.bookPeriodAmort ?? 0), 0),
)
const totalPeriodDiff = computed(() =>
  currentRows.value.reduce((s, r) => s + (r.periodDiff ?? 0), 0),
)
const significantDiffCount = computed(() =>
  currentRows.value.filter(r => Math.abs(r.periodDiff ?? 0) > 0.01 || Math.abs(r.accAmortDiff ?? 0) > 0.01).length,
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
  addRow({ name: '', cost: 0, salvage: 0, usefulLifeMonths: 0 })
}

async function handleSyncFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将从I1-2同步资产参数，现有手工调整可能被覆盖。是否继续？',
      '同步I1-2参数',
      { type: 'warning' },
    )
  } catch { return }

  const detailData = props.allResponses.get('I1-2-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessageBox.alert('未找到I1-2明细表数据。', '提示')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) {
      ElMessageBox.alert('I1-2明细表暂无资产数据。', '提示')
      return
    }
    const assetParams: I1AssetParams[] = parsed.map((item: any) => ({
      rowId: item.rowId ?? '',
      name: item.name ?? item.assetName ?? '',
      category: item.category ?? '',
      cost: Number(item.costEnd ?? item.cost ?? 0),
      salvageRate: Number(item.salvageRate ?? 0),
      usefulLifeMonths: Number(item.usefulLifeMonths ?? 0),
      accAmortBegin: Number(item.accAmortBegin ?? 0),
      accAmortEnd: Number(item.accAmortEnd ?? item.accAmortBegin ?? 0),
      impairmentEnd: 0,
      acquisitionDate: item.acquisitionDate ?? '',
      amortProvision: Number(item.amortProvision ?? 0),
    }))
    syncFromDetail(assetParams)
    ElMessage.success(`已同步 ${assetParams.length} 项`)
  } catch {
    ElMessageBox.alert('I1-2数据解析失败。', '错误')
  }
}

function handleSyncFromUsefulLife() {
  const r = syncFromUsefulLife()
  if (r.updated > 0) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleReview() { openReviewDialog('I1-10') }
function handleSaveNote() { emit('save', 'I1-10-note', auditNote.value) }
function handleSaveConclusion() { emit('save', 'I1-10-conclusion', auditConclusion.value) }

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
  return Math.abs(row.periodDiff ?? 0) > 0.01 || Math.abs(row.accAmortDiff ?? 0) > 0.01 ? 'diff-row' : ''
}

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const labelToKey: Record<string, keyof I1AmortizationRow> = {
    原值: 'cost',
    累计摊销期初: 'accAmortBegin',
    账面累计摊销期末: 'bookAccAmortEnd',
    账面本期摊销: 'bookPeriodAmort',
    残值: 'salvage',
    期初净值F: 'beginNbv',
    月摊销额K: 'monthlyAmortAmount',
    本期摊销M: 'periodAmortization',
    本期差异O: 'periodDiff',
    '累计摊销(测算)': 'calcAccAmort',
    累计差异: 'accAmortDiff',
  }
  return columns.map((col: any, index: number) => {
    if (index === 0) return '合计'
    const key = labelToKey[col.label]
    if (!key) return ''
    return fmtAmt(data.reduce((s, r) => s + Number((r as any)[key] ?? 0), 0))
  })
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-amort-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 3px solid var(--el-color-primary);
  background: #f0f7ff;
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
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }
.reconcile-alert { margin-bottom: 12px; }
.period-label { font-size: 12px; color: var(--el-text-color-secondary); }
.chip-wrap { display: inline-flex; }
.section-title { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.amort-table { font-size: 12px; }
.amort-table :deep(.diff-row) { background: var(--el-color-danger-light-9); }
.cell-input { width: 100%; }
.cell-input :deep(.el-input__inner) { text-align: right; font-size: 12px; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.totals-bar {
  display: flex; gap: 20px; padding: 10px 12px; margin-top: 12px;
  background: var(--el-fill-color-light); border-radius: 4px; flex-wrap: wrap;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
