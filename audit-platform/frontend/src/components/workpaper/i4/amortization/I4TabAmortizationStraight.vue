<template>
  <div class="i4-tab-amortization-straight">
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：检查长期待摊费用的摊销是否正确——按直线法重算月摊销与本期摊销，与账面月摊/累计摊销比对差异。"
      class="objective-alert"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 设定摊销期初/期末，录入类别、明细、原值、开始使用日期、使用年限</div>
        <div class="guide-step"><span class="step-num">②</span> 系统推算月限、到期日、已摊/剩余/本期月数，测算月摊 = 原值 ÷ 月限</div>
        <div class="guide-step"><span class="step-num">③</span> 填入账面月摊销额与账面累计摊销，比对月摊差异与累计差异</div>
        <div class="guide-step"><span class="step-num">④</span> 差异重大时追查政策/起止时点，形成说明与结论</div>
      </div>
    </div>

    <!-- 摊销期间（源表第8行） -->
    <div class="period-row">
      <span class="period-label">摊销期初</span>
      <el-date-picker
        v-model="periodBegin"
        type="date"
        value-format="YYYY-MM-DD"
        size="small"
        :disabled="isReadonly"
        @change="recalcAll"
      />
      <span class="period-label">摊销期末</span>
      <el-date-picker
        v-model="periodEnd"
        type="date"
        value-format="YYYY-MM-DD"
        size="small"
        :disabled="isReadonly"
        @change="recalcAll"
      />
      <span class="period-hint">本期月数按「开始日/到期日/期初日/截止日」四分支计算，避免对老项目虚增</span>
    </div>

    <div class="toolbar-row">
      <el-dropdown trigger="click" :disabled="isReadonly">
        <el-button size="small" type="default">
          导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增项目</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncFromDetail">
        同步I4-2直线法项目
      </el-button>
      <span class="row-count">
        共 {{ rows.length }} 个项目 · 当期摊销合计 <b>{{ fmtAmt(totals.periodAmortization) }}</b>
        · 累计差异
        <b :class="{ 'text-danger': Math.abs(totals.accumDiff) > 0.01 }">{{ fmtAmt(totals.accumDiff) }}</b>
      </span>
    </div>

    <div class="matrix-wrapper">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        class="amort-table"
        :max-height="520"
        :row-class-name="getRowClass"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" fixed />

        <el-table-column prop="category" label="类别名称" min-width="120" fixed>
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              placeholder="如：使用权资产改良及维护支出"
              @blur="onCellBlur($index)"
            />
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="itemName" label="明细项目" min-width="120" fixed show-overflow-tooltip>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.itemName" size="small" @blur="onCellBlur($index)" />
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="originalAmount" label="原值" width="105" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.originalAmount"
              :controls="false"
              size="small"
              :precision="2"
              @change="recalcRow($index)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="bookAccumAmort" label="累计摊销" width="105" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookAccumAmort"
              :controls="false"
              size="small"
              :precision="2"
              @change="recalcRow($index)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAccumAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="startDate" label="开始使用日期" width="130">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.startDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="recalcRow($index)"
            />
            <span v-else>{{ row.startDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="usefulLife" label="使用年限" width="90" align="center">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              v-model="row.usefulLife"
              size="small"
              placeholder="5年"
              @change="recalcRow($index)"
            />
            <span v-else>{{ row.usefulLife || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="bookMonthlyAmort" label="账面月摊销额" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookMonthlyAmort"
              :controls="false"
              size="small"
              :precision="2"
              @change="recalcRow($index)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookMonthlyAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="使用月限" width="80" align="center">
          <template #default="{ row }">
            <span class="formula-cell" title="由使用年限解析（N年→N×12）">{{ row.lifeMonths || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="测算到期日" width="110" align="center">
          <template #default="{ row }">
            <span class="formula-cell" title="= 开始日 + 月限 − 1天">{{ row.fullAmortDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="已摊销月份" width="90" align="center">
          <template #default="{ row }">
            <span class="formula-cell" title="至截止日或到期日孰早">{{ row.monthsAmortized }}</span>
          </template>
        </el-table-column>

        <el-table-column label="剩余摊销月份" width="100" align="center">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-warn': row.remainingMonths <= 0 && row.lifeMonths > 0 }"
              title="= 月限 − 已摊月数"
            >{{ row.remainingMonths }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期摊销月份" width="100" align="center">
          <template #default="{ row }">
            <span class="formula-cell" title="期间四分支 ∩ 剩余月数">{{ row.periodMonths }}</span>
          </template>
        </el-table-column>

        <el-table-column label="测算月摊销额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 原值 ÷ 使用月限">{{ fmtAmt(row.calcMonthlyAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="当期摊销" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 测算月摊 × 本期月数">{{ fmtAmt(row.periodAmortization) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="月摊销额差异" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-danger': Math.abs(row.monthlyDiff) > 0.01 }"
              title="= 账面月摊 − 测算月摊"
            >{{ fmtAmt(row.monthlyDiff) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="累计摊销费用" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="测算累计 = 月摊 × 已摊月数">{{ fmtAmt(row.calcAccumAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="累计摊销额差异" width="120" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-danger': Math.abs(row.accumDiff) > 0.01 }"
              title="= 账面累计 − 测算累计"
            >{{ fmtAmt(row.accumDiff) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="remark" label="备注" width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @blur="onCellBlur($index)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleDeleteRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card v-if="categorySubtotals.length" shadow="never" class="subtotal-card">
      <template #header><div class="card-header"><span>其中（按类别小计）</span></div></template>
      <el-table :data="categorySubtotals" border size="small" max-height="220">
        <el-table-column prop="category" label="类别名称" min-width="160" />
        <el-table-column prop="count" label="项目数" width="80" align="center" />
        <el-table-column label="当期摊销" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.periodAmortization) }}</template>
        </el-table-column>
        <el-table-column label="累计差异" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': Math.abs(row.accumDiff) > 0.01 }">{{ fmtAmt(row.accumDiff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="totals-bar">
      <span>原值合计: <b>{{ fmtAmt(totals.originalAmount) }}</b></span>
      <span>当期摊销合计: <b>{{ fmtAmt(totals.periodAmortization) }}</b></span>
      <span>测算累计合计: <b>{{ fmtAmt(totals.calcAccumAmort) }}</b></span>
      <span>
        累计差异合计:
        <b :class="{ 'text-danger': Math.abs(totals.accumDiff) > 0.01 }">{{ fmtAmt(totals.accumDiff) }}</b>
      </span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="请说明：受益期限依据、起止时点核对、月摊/累计差异原因及是否需调整…"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" plain @click="fillConclusionDraft">填入结论模板</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、直线法摊销测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>直线法：测算月摊销额 = 原值 ÷ 使用月限；当期摊销 = 测算月摊 × 本期摊销月份。</li>
        <li>使用年限填「N年」或月数；系统解析为使用月限。测算到期日 = 开始使用日期 + 月限 − 1 天（开始日为空则不推算，避免 1900-1-0）。</li>
        <li>本期摊销月份按摊销期初/期末与项目起止的四分支重叠计算，并不超过剩余月数，避免对期初前已投入使用的项目虚增本期月数。</li>
        <li>月摊销额差异 = 账面月摊 − 测算月摊；累计摊销额差异 = 账面累计 − 测算累计。差异重大时追查受益期估计或起止时点，必要时提调整（I4-3）。</li>
        <li>受益期限须有依据：装修费不超过租赁期与使用年限孰短；开办费等通常 3~5 年；与 I4-4 政策检查结论一致。</li>
        <li>本表仅用于长期待摊费用直线法，不得套用无形资产使用寿命有限/不确定等判断规则（彼属 I1）。</li>
      </ol>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAmortizationStraight.vue — I4-6 直线法摊销测算表
 *
 * 对齐源 xlsx「摊销测算I4-6」：
 * 类别|明细|原值|累计摊销|开始使用日期|使用年限|账面月摊|
 * 使用月限|测算到期日|已摊月数|剩余月数|本期月数|测算月摊|当期摊销|
 * 月摊差异|累计摊销费用|累计差异
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 */
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { calcStraightLineAmortTest } from '../../composables/useI4AmortizationEngine'
import { calcSubtotal } from '../../composables/useI4FormulaEngine'
import { useI4ImportExport } from '../../composables/useI4ImportExport'

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

interface StraightAmortRow {
  rowId: string
  category: string
  itemName: string
  originalAmount: number
  bookAccumAmort: number
  startDate: string
  usefulLife: string
  bookMonthlyAmort: number
  lifeMonths: number
  fullAmortDate: string
  monthsAmortized: number
  remainingMonths: number
  periodMonths: number
  calcMonthlyAmort: number
  periodAmortization: number
  monthlyDiff: number
  calcAccumAmort: number
  accumDiff: number
  /** 跨表兼容 */
  yearTotal: number
  monthlyAmorts: number[]
  remark: string
}

interface CategorySubtotal {
  category: string
  count: number
  periodAmortization: number
  accumDiff: number
}

const PREFIX = 'I4-6'
const META_KEY = 'I4-6-period-meta'
const rows = ref<StraightAmortRow[]>([])
const periodBegin = ref('2025-01-01')
const periodEnd = ref('2025-12-31')
const fileInputRef = ref<HTMLInputElement | null>(null)

const importExport = useI4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => _load(),
})

function _defaultPeriodYear(): { begin: string; end: string } {
  const y = new Date().getFullYear()
  return { begin: `${y}-01-01`, end: `${y}-12-31` }
}

function _loadMeta(): void {
  const item = props.allResponses.get(META_KEY)
  if (item?.remark) {
    try {
      const m = JSON.parse(item.remark)
      if (m.periodBegin) periodBegin.value = m.periodBegin
      if (m.periodEnd) periodEnd.value = m.periodEnd
      return
    } catch { /* fallthrough */ }
  }
  const d = _defaultPeriodYear()
  periodBegin.value = d.begin
  periodEnd.value = d.end
}

function _saveMeta(): void {
  const payload = JSON.stringify({ periodBegin: periodBegin.value, periodEnd: periodEnd.value })
  props.allResponses.set(META_KEY, { item_id: META_KEY, conclusion: null, remark: payload })
  emit('save', META_KEY, payload)
}

function _load(): void {
  _loadMeta()
  const item = props.allResponses.get(`${PREFIX}-rows`)
  if (item?.remark) {
    try {
      const parsed = JSON.parse(item.remark)
      rows.value = Array.isArray(parsed) ? parsed.map(_ensureRow) : []
    } catch {
      rows.value = []
    }
  } else {
    rows.value = []
  }
}

function _ensureRow(r: any): StraightAmortRow {
  let usefulLife = r.usefulLife ?? ''
  if (!usefulLife && r.totalMonths) {
    const tm = Number(r.totalMonths) || 0
    usefulLife = tm > 0 && tm % 12 === 0 ? `${tm / 12}年` : String(tm)
  }

  const row: StraightAmortRow = {
    rowId: r.rowId || `i4s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    category: r.category ?? '',
    itemName: r.itemName ?? r.name ?? r.projectName ?? '',
    originalAmount: Number(r.originalAmount ?? 0) || 0,
    bookAccumAmort: Number(r.bookAccumAmort ?? r.priorAccumulated ?? r.accumulatedAmort ?? 0) || 0,
    startDate: r.startDate ?? r.incurredDate ?? '',
    usefulLife: String(usefulLife || ''),
    bookMonthlyAmort: Number(r.bookMonthlyAmort ?? r.monthlyAmort ?? 0) || 0,
    lifeMonths: 0,
    fullAmortDate: '',
    monthsAmortized: 0,
    remainingMonths: 0,
    periodMonths: 0,
    calcMonthlyAmort: 0,
    periodAmortization: 0,
    monthlyDiff: 0,
    calcAccumAmort: 0,
    accumDiff: 0,
    yearTotal: 0,
    monthlyAmorts: new Array(12).fill(0),
    remark: r.remark ?? '',
  }

  // 旧矩阵：若有 yearTotal 且无账面月摊，用 yearTotal/12 作参考账面月摊
  if (!r.bookMonthlyAmort && Array.isArray(r.monthly) && r.yearTotal) {
    row.bookMonthlyAmort = (Number(r.yearTotal) || 0) / 12
  }

  _recalcAll(row)
  return row
}

function _distributeMonthly(periodAmort: number, periodMonths: number): number[] {
  const arr = new Array(12).fill(0)
  if (periodMonths <= 0 || !periodAmort) return arr
  const m = periodAmort / periodMonths
  const n = Math.min(Math.round(periodMonths), 12)
  for (let i = 0; i < n; i++) arr[i] = Math.round((m + Number.EPSILON) * 100) / 100
  return arr
}

function _recalcAll(row: StraightAmortRow): void {
  const result = calcStraightLineAmortTest({
    originalAmount: row.originalAmount,
    usefulLife: row.usefulLife || row.lifeMonths,
    startDate: row.startDate,
    periodBegin: periodBegin.value,
    periodEnd: periodEnd.value,
    bookMonthlyAmort: row.bookMonthlyAmort,
    bookAccumAmort: row.bookAccumAmort,
  })
  row.lifeMonths = result.lifeMonths
  row.fullAmortDate = result.fullAmortDate
  row.monthsAmortized = result.monthsAmortized
  row.remainingMonths = result.remainingMonths
  row.periodMonths = result.periodMonths
  row.calcMonthlyAmort = result.calcMonthlyAmort
  row.periodAmortization = result.periodAmortization
  row.monthlyDiff = result.monthlyDiff
  row.calcAccumAmort = result.calcAccumAmort
  row.accumDiff = result.accumDiff
  row.yearTotal = result.periodAmortization
  row.monthlyAmorts = _distributeMonthly(result.periodAmortization, result.periodMonths)
}

watch(() => props.allResponses, () => _load(), { immediate: true })

function recalcRow(idx: number): void {
  const row = rows.value[idx]
  if (!row) return
  _recalcAll(row)
  _persist()
}

function recalcAll(): void {
  rows.value.forEach((r) => _recalcAll(r))
  _saveMeta()
  _persist()
}

function onCellBlur(_idx: number): void {
  _persist()
}

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入明细项目名称', '新增项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    const row = _ensureRow({ itemName: name, usefulLife: '5年' })
    rows.value.push(row)
    _persist()
  } catch { /* cancel */ }
}

function handleDeleteRow(idx: number): void {
  rows.value.splice(idx, 1)
  _persist()
}

function handleSyncFromDetail(): void {
  const detailItem = props.allResponses.get('I4-2-rows')
  let detailRows: any[] = []
  try {
    detailRows = detailItem?.remark ? JSON.parse(detailItem.remark) : []
    if (!Array.isArray(detailRows)) detailRows = []
  } catch {
    detailRows = []
  }

  const straightRows = detailRows.filter((r) => {
    const m = String(r.amortizationMethod ?? r.amortMethod ?? '')
    return !m || /直线|平均/.test(m) || !/工作量/.test(m)
  })

  if (!straightRows.length) {
    ElMessage.warning('I4-2 中未找到可用于直线法测算的项目')
    return
  }

  const byName = new Map(rows.value.map((r) => [r.itemName, r]))
  let added = 0
  let updated = 0

  for (const d of straightRows) {
    const name = String(d.name ?? d.projectName ?? d.itemName ?? '').trim()
    if (!name) continue
    const usefulLife = d.totalMonths
      ? (d.totalMonths % 12 === 0 ? `${d.totalMonths / 12}年` : String(d.totalMonths))
      : ''
    const existing = byName.get(name)
    if (existing) {
      existing.category = d.category ?? d.expenseType ?? existing.category
      existing.originalAmount = Number(d.originalAmount ?? existing.originalAmount) || 0
      existing.startDate = d.incurredDate ?? d.startDate ?? existing.startDate
      if (usefulLife) existing.usefulLife = usefulLife
      if (d.accAmortization != null) existing.bookAccumAmort = Number(d.accAmortization) || 0
      if (d.currentAmortization != null && existing.lifeMonths > 0) {
        // 用本期摊销反推账面月摊参考
        existing.bookMonthlyAmort = (Number(d.currentAmortization) || 0) / Math.max(existing.periodMonths || 12, 1)
      }
      _recalcAll(existing)
      updated++
    } else {
      const row = _ensureRow({
        category: d.category ?? d.expenseType ?? '',
        itemName: name,
        originalAmount: d.originalAmount ?? 0,
        startDate: d.incurredDate ?? d.startDate ?? '',
        usefulLife: usefulLife || '5年',
        bookAccumAmort: d.accAmortization ?? 0,
        bookMonthlyAmort: d.totalMonths ? (Number(d.originalAmount) || 0) / d.totalMonths : 0,
      })
      rows.value.push(row)
      byName.set(name, row)
      added++
    }
  }

  _persist()
  ElMessage.success(`已同步：新增 ${added}、更新 ${updated}`)
}

const totals = computed(() => ({
  originalAmount: calcSubtotal(rows.value.map((r) => r.originalAmount)),
  periodAmortization: calcSubtotal(rows.value.map((r) => r.periodAmortization)),
  calcAccumAmort: calcSubtotal(rows.value.map((r) => r.calcAccumAmort)),
  accumDiff: calcSubtotal(rows.value.map((r) => r.accumDiff)),
  monthlyDiff: calcSubtotal(rows.value.map((r) => r.monthlyDiff)),
}))

const categorySubtotals = computed<CategorySubtotal[]>(() => {
  const map = new Map<string, CategorySubtotal>()
  for (const r of rows.value) {
    const key = (r.category || '未分类').trim() || '未分类'
    const cur = map.get(key) || { category: key, count: 0, periodAmortization: 0, accumDiff: 0 }
    cur.count += 1
    cur.periodAmortization += r.periodAmortization
    cur.accumDiff += r.accumDiff
    map.set(key, cur)
  }
  return [...map.values()].sort((a, b) => a.category.localeCompare(b.category, 'zh'))
})

function getRowClass({ row }: { row: StraightAmortRow }): string {
  if (Math.abs(row.monthlyDiff) > 0.01 || Math.abs(row.accumDiff) > 0.01) return 'row-has-diff'
  if (row.remainingMonths <= 0 && row.lifeMonths > 0) return 'row-fully-amort'
  return ''
}

function getSummary({ columns }: { columns: any[]; data: StraightAmortRow[] }): string[] {
  return columns.map((col: any, colIdx: number) => {
    if (colIdx === 0) return '合计'
    const prop = col.property
    if (prop === 'originalAmount') return fmtAmt(totals.value.originalAmount)
    if (prop === 'bookAccumAmort') return fmtAmt(calcSubtotal(rows.value.map((r) => r.bookAccumAmort)))
    if (col.label === '当期摊销') return fmtAmt(totals.value.periodAmortization)
    if (col.label === '累计摊销费用') return fmtAmt(totals.value.calcAccumAmort)
    if (col.label === '累计摊销额差异') return fmtAmt(totals.value.accumDiff)
    if (col.label === '月摊销额差异') return fmtAmt(totals.value.monthlyDiff)
    return ''
  })
}

function handleExportTemplate(): void { importExport.exportTemplate('I4-6') }
function handleExportData(): void { importExport.exportData('I4-6') }
function triggerImport(): void { fileInputRef.value?.click() }
function onFileSelected(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) importExport.importData('I4-6', file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 1e-9) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function _persist(): void {
  emit('save', `${PREFIX}-rows`, JSON.stringify(rows.value))
}

const NOTE_KEY = 'I4-amortization-straight-audit-note'
const CONCLUSION_KEY = 'I4-amortization-straight-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  emit('save', CONCLUSION_KEY, val)
}

function fillConclusionDraft(): void {
  const hasDiff = Math.abs(totals.value.accumDiff) > 0.01 || Math.abs(totals.value.monthlyDiff) > 0.01
  const draft = hasDiff
    ? `B、经直线法重算，当期摊销合计 ${fmtAmt(totals.value.periodAmortization)}，累计差异合计 ${fmtAmt(totals.value.accumDiff)}；除下列差异外未见异常：\n1. `
    : 'A、经直线法重算，摊销测算准确，与账面无重大差异，相关计价和分摊认定可确认。'
  auditConclusion.value = draft
  saveAuditConclusion(draft)
  ElMessage.success('已填入结论模板')
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped>
.i4-tab-amortization-straight { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 14px; }
.i4-tab-amortization-straight :deep(.objective-alert .el-alert__content) { padding: 2px 0; }

.audit-note-card,
.subtotal-card { margin-bottom: 12px; }
.audit-note-card :deep(.el-card__header),
.subtotal-card :deep(.el-card__header) { padding: 8px 16px; background: #fafafa; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 500;
}

.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

.period-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.period-label { font-size: 13px; color: var(--el-text-color-regular); }
.period-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-left: 8px; }

.toolbar-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }

.matrix-wrapper { overflow-x: auto; margin-bottom: 12px; }
.amort-table { font-size: 12px; }
.amort-table :deep(.row-has-diff) { background: #fff7e6 !important; }
.amort-table :deep(.row-fully-amort) { background: #f0f9eb !important; }

.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.amount-cell { font-variant-numeric: tabular-nums; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.text-warn { color: var(--el-color-warning); font-weight: 600; }

.totals-bar {
  display: flex; flex-wrap: wrap; gap: 20px;
  padding: 10px 12px; margin-bottom: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: 13px;
}

.compile-hint { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 6px; line-height: 1.5; }
</style>
