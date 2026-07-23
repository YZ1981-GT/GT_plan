<template>
  <div class="i4-tab-amortization-units">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认长期待摊费用本期摊销金额是否合理——按工作量法重算摊销，与账面比对差异，并核实工作量数据来源可靠。"
      class="objective-alert"
    />

    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 录入类别/明细、原值、开始使用日期、工作标准（总预计工作量）</div>
        <div class="guide-step"><span class="step-num">②</span> 系统自动算摊销标准 = 原值 ÷ 工作标准</div>
        <div class="guide-step"><span class="step-num">③</span> 填入本期/累计工作量 → 测算摊销额 = 工作量 × 摊销标准</div>
        <div class="guide-step"><span class="step-num">④</span> 填入账面摊销 → 差异 = 测算 − 账面；关注重大差异并形成结论</div>
      </div>
    </div>

    <!-- 工具栏 -->
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
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
        + 新增项目
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncFromDetail">
        同步I4-2工作量法项目
      </el-button>
      <span class="row-count">共 {{ rows.length }} 个项目 · 本期差异合计
        <b :class="{ 'text-danger': Math.abs(totals.periodDiff) > 0.01 }">{{ fmtAmt(totals.periodDiff) }}</b>
      </span>
    </div>

    <!-- 主测算表：对齐源表 I4-7 列结构 -->
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

        <el-table-column prop="category" label="类别名称" min-width="130" fixed>
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

        <el-table-column prop="originalAmount" label="原值" width="110" align="right">
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

        <el-table-column prop="startDate" label="开始使用日期" width="130">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.startDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="onCellBlur($index)"
            />
            <span v-else>{{ row.startDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="workStandard" label="工作标准" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.workStandard"
              :controls="false"
              :min="0"
              size="small"
              @change="recalcRow($index)"
            />
            <span v-else>{{ row.workStandard || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="摊销标准" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 原值 ÷ 工作标准">{{ fmtAmt(row.amortStandard) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="工作量">
          <el-table-column prop="periodUnits" label="本期" width="90" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.periodUnits"
                :controls="false"
                :min="0"
                size="small"
                @change="recalcRow($index)"
              />
              <span v-else>{{ row.periodUnits || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accumUnits" label="累计" width="90" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.accumUnits"
                :controls="false"
                :min="0"
                size="small"
                @change="recalcRow($index)"
              />
              <span v-else>{{ row.accumUnits || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="测算摊销额">
          <el-table-column label="测算本年" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="= 本期工作量 × 摊销标准">{{ fmtAmt(row.calcPeriodAmort) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="测算累计" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="= 累计工作量 × 摊销标准">{{ fmtAmt(row.calcAccumAmort) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="账面摊销额">
          <el-table-column prop="bookPeriodAmort" label="本期" width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.bookPeriodAmort"
                :controls="false"
                size="small"
                :precision="2"
                @change="recalcRow($index)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookPeriodAmort) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookAccumAmort" label="累计" width="110" align="right">
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
        </el-table-column>

        <el-table-column label="摊销额差异">
          <el-table-column label="本期" width="100" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :class="{ 'text-danger': Math.abs(row.periodDiff) > 0.01 }"
                title="= 测算本年 − 账面本期"
              >{{ fmtAmt(row.periodDiff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计" width="100" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :class="{ 'text-danger': Math.abs(row.accumDiff) > 0.01 }"
                title="= 测算累计 − 账面累计"
              >{{ fmtAmt(row.accumDiff) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="remark" label="备注" width="110">
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

    <!-- 其中：按类别小计（对齐源表「其中」区） -->
    <el-card v-if="categorySubtotals.length" shadow="never" class="subtotal-card">
      <template #header><div class="card-header"><span>其中（按类别小计）</span></div></template>
      <el-table :data="categorySubtotals" border size="small" max-height="220">
        <el-table-column prop="category" label="类别名称" min-width="160" />
        <el-table-column prop="count" label="项目数" width="80" align="center" />
        <el-table-column label="测算本年" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.calcPeriodAmort) }}</template>
        </el-table-column>
        <el-table-column label="账面本期" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.bookPeriodAmort) }}</template>
        </el-table-column>
        <el-table-column label="本期差异" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': Math.abs(row.periodDiff) > 0.01 }">{{ fmtAmt(row.periodDiff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="totals-bar">
      <span>测算本年合计: <b>{{ fmtAmt(totals.calcPeriodAmort) }}</b></span>
      <span>账面本期合计: <b>{{ fmtAmt(totals.bookPeriodAmort) }}</b></span>
      <span>
        本期差异合计:
        <b :class="{ 'text-danger': Math.abs(totals.periodDiff) > 0.01 }">{{ fmtAmt(totals.periodDiff) }}</b>
      </span>
      <span>
        累计差异合计:
        <b :class="{ 'text-danger': Math.abs(totals.accumDiff) > 0.01 }">{{ fmtAmt(totals.accumDiff) }}</b>
      </span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="请说明：工作量数据来源（生产统计/合同产量等）、工作标准确定依据、测算与账面差异原因及是否需调整…"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
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
        placeholder="A、工作量法摊销测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制说明：纠偏为长期待摊费用（源表误粘贴无形资产条款） -->
    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>工作量法适用于受益与产出/使用量直接相关的长期待摊费用（如模具费按产量、矿区权益按采矿量、装修费按特定产出）。</li>
        <li>摊销标准 = 原值 ÷ 工作标准；测算本年摊销 = 本期工作量 × 摊销标准；测算累计 = 累计工作量 × 摊销标准（等价于 原值 × 工作量/工作标准）。</li>
        <li>工作标准与实际工作量须有客观依据（生产台账、产量统计、合同约定等），并与 I4-4 摊销政策检查结论一致。</li>
        <li>差异 = 测算 − 账面；本期或累计差异重大时，追查工作量计量错误、政策误用或需提调整分录（I4-3）。</li>
        <li>累计工作量不得超过工作标准；超额部分应说明是否需变更估计（未来适用法）或转销剩余余额。</li>
        <li>本表仅用于长期待摊费用，不得套用无形资产使用寿命有限/不确定等判断规则（彼属 I1）。</li>
      </ol>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAmortizationUnits.vue — I4-7 工作量法摊销测算表
 *
 * 对齐源 xlsx「摊销测算表I4-7（工作量法）」：
 * 类别|明细|原值|开始使用日期|工作标准|摊销标准|工作量(本期/累计)|
 * 测算摊销(本年/累计)|账面摊销(本期/累计)|差异(本期/累计)
 *
 * 公式（源表）：
 *   F摊销标准 = C原值 / E工作标准
 *   I测算本年 = G本期量 × F
 *   J测算累计 = H累计量 × F
 *   M本期差异 = I − K；N累计差异 = J − L
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 */
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  calcAmortStandard,
  calcUnitsAmortByStandard,
  calcAmortDiff,
  calcAmortizationRate,
} from '../../composables/useI4AmortizationEngine'
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

interface UnitsAmortRow {
  rowId: string
  category: string
  itemName: string
  originalAmount: number
  startDate: string
  workStandard: number
  amortStandard: number
  periodUnits: number
  accumUnits: number
  calcPeriodAmort: number
  calcAccumAmort: number
  bookPeriodAmort: number
  bookAccumAmort: number
  periodDiff: number
  accumDiff: number
  remainingUnits: number
  endingBalance: number
  amortRate: number
  /** 跨表兼容：等同 calcPeriodAmort */
  yearTotal: number
  remark: string
}

interface CategorySubtotal {
  category: string
  count: number
  calcPeriodAmort: number
  bookPeriodAmort: number
  periodDiff: number
}

const PREFIX = 'I4-7'
const rows = ref<UnitsAmortRow[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

const importExport = useI4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => _load(),
})

function _load(): void {
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

/** 兼容旧版 12 月矩阵字段 */
function _ensureRow(r: any): UnitsAmortRow {
  const originalAmount = Number(r.originalAmount ?? 0) || 0
  const workStandard = Number(r.workStandard ?? r.totalUnits ?? 0) || 0
  let periodUnits = Number(r.periodUnits ?? r.currentUnits ?? 0) || 0
  let accumUnits = Number(r.accumUnits ?? r.completedUnits ?? 0) || 0

  // 旧矩阵：monthlyUnits 年合计工作量 → 本期；无累计则用本期
  if ((!periodUnits || !accumUnits) && Array.isArray(r.monthlyUnits)) {
    const yearUnits = (r.monthlyUnits as number[]).reduce((s, u) => s + (Number(u) || 0), 0)
    if (!periodUnits) periodUnits = yearUnits
    if (!accumUnits) accumUnits = yearUnits + (Number(r.priorAccumulatedUnits) || 0)
  }

  const bookPeriodAmort = Number(r.bookPeriodAmort ?? 0) || 0
  let bookAccumAmort = Number(r.bookAccumAmort ?? r.priorAccumulated ?? 0) || 0
  // 旧矩阵累计摊销若仅有 prior+year，可作账面累计初值（仅当未单独录入账面）
  if (!r.bookAccumAmort && Array.isArray(r.monthlyAmort) && r.priorAccumulated != null) {
    const yearAmort = (r.monthlyAmort as number[]).reduce((s, u) => s + (Number(u) || 0), 0)
    bookAccumAmort = (Number(r.priorAccumulated) || 0) + yearAmort
  }

  const row: UnitsAmortRow = {
    rowId: r.rowId || `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    category: r.category ?? '',
    itemName: r.itemName ?? r.name ?? r.projectName ?? '',
    originalAmount,
    startDate: r.startDate ?? r.incurredDate ?? '',
    workStandard,
    amortStandard: 0,
    periodUnits,
    accumUnits,
    calcPeriodAmort: 0,
    calcAccumAmort: 0,
    bookPeriodAmort,
    bookAccumAmort,
    periodDiff: 0,
    accumDiff: 0,
    remainingUnits: 0,
    endingBalance: 0,
    amortRate: 0,
    yearTotal: 0,
    remark: r.remark ?? '',
  }
  _recalcAll(row)
  return row
}

function _recalcAll(row: UnitsAmortRow): void {
  row.amortStandard = calcAmortStandard(row.originalAmount, row.workStandard)
  row.calcPeriodAmort = calcUnitsAmortByStandard(row.periodUnits, row.amortStandard)
  row.calcAccumAmort = calcUnitsAmortByStandard(row.accumUnits, row.amortStandard)
  row.periodDiff = calcAmortDiff(row.calcPeriodAmort, row.bookPeriodAmort)
  row.accumDiff = calcAmortDiff(row.calcAccumAmort, row.bookAccumAmort)
  row.remainingUnits = Math.max(0, row.workStandard - row.accumUnits)
  row.endingBalance = row.originalAmount - row.calcAccumAmort
  row.amortRate = row.workStandard > 0
    ? calcAmortizationRate(row.accumUnits, row.workStandard)
    : 0
  row.yearTotal = row.calcPeriodAmort
}

watch(() => props.allResponses, () => _load(), { immediate: true })

function recalcRow(idx: number): void {
  const row = rows.value[idx]
  if (!row) return
  _recalcAll(row)
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
    const newRow: UnitsAmortRow = {
      rowId: `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category: '',
      itemName: name,
      originalAmount: 0,
      startDate: '',
      workStandard: 0,
      amortStandard: 0,
      periodUnits: 0,
      accumUnits: 0,
      calcPeriodAmort: 0,
      calcAccumAmort: 0,
      bookPeriodAmort: 0,
      bookAccumAmort: 0,
      periodDiff: 0,
      accumDiff: 0,
      remainingUnits: 0,
      endingBalance: 0,
      amortRate: 0,
      yearTotal: 0,
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  } catch { /* cancel */ }
}

function handleDeleteRow(idx: number): void {
  rows.value.splice(idx, 1)
  _persist()
}

/** 从 I4-2 明细表同步「工作量法」项目（保留已填工作量/账面） */
function handleSyncFromDetail(): void {
  const detailItem = props.allResponses.get('I4-2-rows')
  let detailRows: any[] = []
  try {
    detailRows = detailItem?.remark ? JSON.parse(detailItem.remark) : []
    if (!Array.isArray(detailRows)) detailRows = []
  } catch {
    detailRows = []
  }

  const unitsRows = detailRows.filter((r) => {
    const m = String(r.amortizationMethod ?? r.amortMethod ?? '')
    return /工作量/.test(m)
  })

  if (!unitsRows.length) {
    ElMessage.warning('I4-2 中未找到摊销方法为「工作量法」的项目')
    return
  }

  const byName = new Map(rows.value.map((r) => [r.itemName, r]))
  let added = 0
  let updated = 0

  for (const d of unitsRows) {
    const name = String(d.name ?? d.projectName ?? d.itemName ?? '').trim()
    if (!name) continue
    const existing = byName.get(name)
    if (existing) {
      existing.category = d.category ?? d.expenseType ?? existing.category
      existing.originalAmount = Number(d.originalAmount ?? existing.originalAmount) || 0
      existing.startDate = d.incurredDate ?? d.startDate ?? existing.startDate
      if (d.currentAmortization != null) existing.bookPeriodAmort = Number(d.currentAmortization) || 0
      if (d.accAmortization != null) existing.bookAccumAmort = Number(d.accAmortization) || 0
      _recalcAll(existing)
      updated++
    } else {
      const row = _ensureRow({
        category: d.category ?? d.expenseType ?? '',
        itemName: name,
        originalAmount: d.originalAmount ?? 0,
        startDate: d.incurredDate ?? d.startDate ?? '',
        bookPeriodAmort: d.currentAmortization ?? 0,
        bookAccumAmort: d.accAmortization ?? 0,
        workStandard: d.totalUnits ?? 0,
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
  calcPeriodAmort: calcSubtotal(rows.value.map((r) => r.calcPeriodAmort)),
  bookPeriodAmort: calcSubtotal(rows.value.map((r) => r.bookPeriodAmort)),
  periodDiff: calcSubtotal(rows.value.map((r) => r.periodDiff)),
  accumDiff: calcSubtotal(rows.value.map((r) => r.accumDiff)),
  originalAmount: calcSubtotal(rows.value.map((r) => r.originalAmount)),
  calcAccumAmort: calcSubtotal(rows.value.map((r) => r.calcAccumAmort)),
  bookAccumAmort: calcSubtotal(rows.value.map((r) => r.bookAccumAmort)),
}))

const categorySubtotals = computed<CategorySubtotal[]>(() => {
  const map = new Map<string, CategorySubtotal>()
  for (const r of rows.value) {
    const key = (r.category || '未分类').trim() || '未分类'
    const cur = map.get(key) || {
      category: key,
      count: 0,
      calcPeriodAmort: 0,
      bookPeriodAmort: 0,
      periodDiff: 0,
    }
    cur.count += 1
    cur.calcPeriodAmort += r.calcPeriodAmort
    cur.bookPeriodAmort += r.bookPeriodAmort
    cur.periodDiff += r.periodDiff
    map.set(key, cur)
  }
  return [...map.values()].sort((a, b) => a.category.localeCompare(b.category, 'zh'))
})

function getRowClass({ row }: { row: UnitsAmortRow }): string {
  if (Math.abs(row.periodDiff) > 0.01 || Math.abs(row.accumDiff) > 0.01) return 'row-has-diff'
  if (row.workStandard > 0 && row.accumUnits > row.workStandard) return 'row-over-units'
  return ''
}

function getSummary({ columns }: { columns: any[]; data: UnitsAmortRow[] }): string[] {
  const sums: string[] = []
  columns.forEach((col: any, colIdx: number) => {
    if (colIdx === 0) { sums[colIdx] = '合计'; return }
    const prop = col.property
    if (prop === 'originalAmount') sums[colIdx] = fmtAmt(totals.value.originalAmount)
    else if (prop === 'periodUnits' || prop === 'accumUnits') sums[colIdx] = ''
    else if (col.label === '测算本年') sums[colIdx] = fmtAmt(totals.value.calcPeriodAmort)
    else if (col.label === '测算累计') sums[colIdx] = fmtAmt(totals.value.calcAccumAmort)
    else if (prop === 'bookPeriodAmort') sums[colIdx] = fmtAmt(totals.value.bookPeriodAmort)
    else if (prop === 'bookAccumAmort') sums[colIdx] = fmtAmt(totals.value.bookAccumAmort)
    else if (col.label === '本期' && colIdx > 10) sums[colIdx] = fmtAmt(totals.value.periodDiff)
    else if (col.label === '累计' && colIdx > 10) sums[colIdx] = fmtAmt(totals.value.accumDiff)
    else sums[colIdx] = ''
  })
  return sums
}

function handleExportTemplate(): void { importExport.exportTemplate('I4-7') }
function handleExportData(): void { importExport.exportData('I4-7') }
function triggerImport(): void { fileInputRef.value?.click() }
function onFileSelected(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) importExport.importData('I4-7', file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 1e-9) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function _persist(): void {
  emit('save', `${PREFIX}-rows`, JSON.stringify(rows.value))
}

const NOTE_KEY = 'I4-amortization-units-audit-note'
const CONCLUSION_KEY = 'I4-amortization-units-audit-conclusion'
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
  const hasDiff = Math.abs(totals.value.periodDiff) > 0.01 || Math.abs(totals.value.accumDiff) > 0.01
  const draft = hasDiff
    ? `B、经工作量法重算，本期差异合计 ${fmtAmt(totals.value.periodDiff)}、累计差异合计 ${fmtAmt(totals.value.accumDiff)}；除下列差异外未见异常：\n1. `
    : 'A、经工作量法重算，摊销测算准确，与账面无重大差异，相关计价和分摊认定可确认。'
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
.i4-tab-amortization-units { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 14px; }
.i4-tab-amortization-units :deep(.objective-alert .el-alert__content) { padding: 2px 0; }

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

.toolbar-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }

.matrix-wrapper { overflow-x: auto; margin-bottom: 12px; }
.amort-table { font-size: 12px; }
.amort-table :deep(.row-has-diff) { background: #fff7e6 !important; }
.amort-table :deep(.row-over-units) { background: #fef0f0 !important; }

.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.amount-cell { font-variant-numeric: tabular-nums; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }

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
