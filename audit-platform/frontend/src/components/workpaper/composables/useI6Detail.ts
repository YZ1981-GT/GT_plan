/**
 * useI6Detail — I6-2 研发费用明细表 composable（月度12列横向宽表 + 趋势图数据）
 *
 * 结构：44行×65列（固定列 + 12月份列 + 汇总/辅助列）
 *
 * 列结构（A~Z，26列逻辑分组）：
 *   A: 类别/项目名称（固定列）
 *   B~M: 1月~12月各月金额（月度12列）
 *   N: 本期未审合计 = SUM(B:M)
 *   O: 账项调整 AJE
 *   P: 重分类调整 RJE
 *   Q: 本期审定数 = N + O + P
 *   R: 各项目占比 = Q / Q_total × 100
 *   S: 与相关科目勾稽
 *   T: 上期未审
 *   U: 上期AJE
 *   V: 上期RJE
 *   W: 上期审定 = T + U + V
 *   X: 个别报表下的重分类
 *   Y: 合并报表下的重分类
 *   Z: 备注
 *
 * 核心功能：
 *   - 月度12列横向滚动（固定前2列）
 *   - 合计行(底部) = 各列SUM
 *   - 趋势折线图数据（ECharts）：12个月金额数组（顶部可折叠）
 *   - 动态行增删（研发项目）
 *   - 异常检测：月度变动率超±30%高亮
 *   - 持久化：JSON → checklist_responses item_id "I6-2-detail-rows"
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.4
 * Requirements: 3.1-3.7, 9.1-9.2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcMonthlyTotal,
  calcAuditedAmount,
  calcChangeRate,
} from './useI6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细行存储结构（仅原始输入字段） */
export interface I6DetailStoredRow {
  id: string
  /** A列：研发项目/费用类别 */
  category: string
  /** B~M列：1月~12月金额 */
  months: number[]
  /** O列：账项调整 AJE */
  aje: number
  /** P列：重分类调整 RJE */
  rje: number
  /** S列：与相关科目勾稽 */
  reconciliation: string
  /** T列：上期未审 */
  priorUnadj: number
  /** U列：上期AJE */
  priorAje: number
  /** V列：上期RJE */
  priorRje: number
  /** X列：个别报表下的重分类 */
  individualReclass: number
  /** Y列：合并报表下的重分类 */
  consolidatedReclass: number
  /** Z列：备注 */
  remark: string
}

/** 明细行计算完整结构（含公式列） */
export interface I6DetailRow extends I6DetailStoredRow {
  /** N列：本期未审合计 = SUM(1月~12月) */
  unadjTotal: number
  /** Q列：本期审定数 = N + O + P */
  auditedAmount: number
  /** R列：各项目占比 = Q / Q_total × 100 (%) */
  ratio: number | null
  /** W列：上期审定 = T + U + V */
  priorAudited: number
  /** 月度变动率超阈值标记（用于高亮） */
  anomalyHighlight: boolean
}

/** 合计行结构 */
export interface I6DetailTotalRow {
  /** 12个月各月合计 */
  months: number[]
  /** 本期未审合计 */
  unadjTotal: number
  /** AJE合计 */
  aje: number
  /** RJE合计 */
  rje: number
  /** 审定数合计 */
  auditedAmount: number
  /** 上期未审合计 */
  priorUnadj: number
  /** 上期AJE合计 */
  priorAje: number
  /** 上期RJE合计 */
  priorRje: number
  /** 上期审定合计 */
  priorAudited: number
  /** 个别报表重分类合计 */
  individualReclass: number
  /** 合并报表重分类合计 */
  consolidatedReclass: number
}

/** ECharts 趋势图数据结构 */
export interface I6TrendChartData {
  /** X轴：月份标签 */
  xAxis: string[]
  /** 系列数据（每个研发项目一条线 + 合计线） */
  series: Array<{
    name: string
    data: number[]
    type: 'line'
    /** 合计线加粗 */
    lineStyle?: { width: number }
    /** 异常月份标记点 */
    markPoint?: { data: Array<{ xAxis: number; yAxis: number; symbolSize: number }> }
  }>
  /** 合计线12个月数据（简化访问） */
  totalMonthly: number[]
}

/** 列定义（供Vue组件渲染使用） */
export interface I6DetailColumnDef {
  key: string
  label: string
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'percent'
  width?: number
  tooltip?: string
  fixed?: 'left' | 'right'
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'I6-2-detail-rows'
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
/** 月度变动率异常阈值（±30%） */
const ANOMALY_THRESHOLD = 30

// ─── Column Definitions ──────────────────────────────────────────────────────

/** 固定列定义（左侧固定不滚动） */
export const FIXED_COLUMNS: I6DetailColumnDef[] = [
  { key: 'category', label: '类别/项目', editable: true, type: 'text', width: 180, fixed: 'left' },
]

/** 月度12列定义（可横向滚动） */
export const MONTHLY_COLUMNS: I6DetailColumnDef[] = MONTH_LABELS.map((label, i) => ({
  key: `month_${i}`,
  label,
  editable: true,
  type: 'number' as const,
  width: 100,
}))

/** 汇总/辅助列定义 */
export const SUMMARY_COLUMNS: I6DetailColumnDef[] = [
  { key: 'unadjTotal', label: '本期未审合计', editable: false, type: 'formula', width: 130, tooltip: 'SUM(1月~12月)' },
  { key: 'aje', label: '账项调整AJE', editable: true, type: 'number', width: 120 },
  { key: 'rje', label: '重分类调整RJE', editable: true, type: 'number', width: 120 },
  { key: 'auditedAmount', label: '本期审定数', editable: false, type: 'formula', width: 130, tooltip: '未审合计+AJE+RJE' },
  { key: 'ratio', label: '占比(%)', editable: false, type: 'percent', width: 90, tooltip: '本项审定/合计审定×100' },
  { key: 'reconciliation', label: '科目勾稽', editable: true, type: 'text', width: 120 },
  { key: 'priorUnadj', label: '上期未审', editable: true, type: 'number', width: 110 },
  { key: 'priorAje', label: '上期AJE', editable: true, type: 'number', width: 100 },
  { key: 'priorRje', label: '上期RJE', editable: true, type: 'number', width: 100 },
  { key: 'priorAudited', label: '上期审定', editable: false, type: 'formula', width: 110, tooltip: '上期未审+上期AJE+上期RJE' },
  { key: 'individualReclass', label: '个别重分类', editable: true, type: 'number', width: 110 },
  { key: 'consolidatedReclass', label: '合并重分类', editable: true, type: 'number', width: 110 },
  { key: 'remark', label: '备注', editable: true, type: 'text', width: 150 },
]

/** 全部列定义（平铺） */
export const ALL_COLUMNS: I6DetailColumnDef[] = [
  ...FIXED_COLUMNS,
  ...MONTHLY_COLUMNS,
  ...SUMMARY_COLUMNS,
]

// ─── Helper Functions ────────────────────────────────────────────────────────

function safeParse(jsonStr: string | null | undefined): I6DetailStoredRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeStoredRow)
  } catch {
    return []
  }
}

function normalizeStoredRow(raw: any): I6DetailStoredRow {
  const months = Array.isArray(raw.months)
    ? raw.months.slice(0, 12).map(parseNum)
    : new Array(12).fill(0)
  // 补齐到12个月
  while (months.length < 12) months.push(0)

  return {
    id: raw.id ?? `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: String(raw.category ?? ''),
    months,
    aje: parseNum(raw.aje),
    rje: parseNum(raw.rje),
    reconciliation: String(raw.reconciliation ?? ''),
    priorUnadj: parseNum(raw.priorUnadj),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    individualReclass: parseNum(raw.individualReclass),
    consolidatedReclass: parseNum(raw.consolidatedReclass),
    remark: String(raw.remark ?? ''),
  }
}

/**
 * 检测月度异常：某月与前月变动率超阈值
 * 返回异常月份索引数组（0-based, 0=1月）
 */
function detectAnomalyMonthsForRow(months: number[]): number[] {
  const anomalies: number[] = []
  for (let i = 1; i < months.length; i++) {
    const prior = months[i - 1]
    const current = months[i]
    const rate = calcChangeRate(current, prior)
    if (rate !== null && Math.abs(rate) > ANOMALY_THRESHOLD) {
      anomalies.push(i)
    }
  }
  return anomalies
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Detail(options: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, onSave, isReadonly } = options
  const readonly = isReadonly ?? computed(() => false)

  // ─── Internal State ────────────────────────────────────────────────────────

  const storedRows = ref<I6DetailStoredRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _load(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    storedRows.value = safeParse(raw)
  }

  watch(allResponses, () => _load(), { immediate: true })

  // ─── Computed: 审定总额（用于占比计算）─────────────────────────────────────

  const totalAuditedAmount = computed(() => {
    return calcSubtotal(storedRows.value.map((r) => {
      const unadj = calcMonthlyTotal(r.months)
      return calcAuditedAmount(unadj, r.aje, r.rje)
    }))
  })

  // ─── Computed: 完整行（含公式列）───────────────────────────────────────────

  const rows: ComputedRef<I6DetailRow[]> = computed(() => {
    return storedRows.value.map((stored) => {
      const unadjTotal = calcMonthlyTotal(stored.months)
      const auditedAmount = calcAuditedAmount(unadjTotal, stored.aje, stored.rje)
      const priorAudited = calcAuditedAmount(stored.priorUnadj, stored.priorAje, stored.priorRje)
      const ratio = totalAuditedAmount.value === 0
        ? null
        : (auditedAmount / totalAuditedAmount.value) * 100
      const anomalyIndices = detectAnomalyMonthsForRow(stored.months)

      return {
        ...stored,
        unadjTotal,
        auditedAmount,
        ratio,
        priorAudited,
        anomalyHighlight: anomalyIndices.length > 0,
      }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<I6DetailTotalRow> = computed(() => {
    const all = storedRows.value
    const monthTotals = new Array(12).fill(0)
    let ajeTotal = 0
    let rjeTotal = 0
    let priorUnadjTotal = 0
    let priorAjeTotal = 0
    let priorRjeTotal = 0
    let individualTotal = 0
    let consolidatedTotal = 0

    for (const r of all) {
      for (let i = 0; i < 12; i++) {
        monthTotals[i] += parseNum(r.months[i])
      }
      ajeTotal += parseNum(r.aje)
      rjeTotal += parseNum(r.rje)
      priorUnadjTotal += parseNum(r.priorUnadj)
      priorAjeTotal += parseNum(r.priorAje)
      priorRjeTotal += parseNum(r.priorRje)
      individualTotal += parseNum(r.individualReclass)
      consolidatedTotal += parseNum(r.consolidatedReclass)
    }

    const unadjTotal = calcMonthlyTotal(monthTotals)
    const auditedAmount = calcAuditedAmount(unadjTotal, ajeTotal, rjeTotal)
    const priorAudited = calcAuditedAmount(priorUnadjTotal, priorAjeTotal, priorRjeTotal)

    return {
      months: monthTotals,
      unadjTotal,
      aje: ajeTotal,
      rje: rjeTotal,
      auditedAmount,
      priorUnadj: priorUnadjTotal,
      priorAje: priorAjeTotal,
      priorRje: priorRjeTotal,
      priorAudited,
      individualReclass: individualTotal,
      consolidatedReclass: consolidatedTotal,
    }
  })

  // ─── Computed: 月度合计数组（12个月，供交叉校验用）─────────────────────────

  const monthlyTotals: ComputedRef<number[]> = computed(() => totalRow.value.months)

  // ─── Computed: 趋势折线图数据（ECharts）───────────────────────────────────

  const trendChartData: ComputedRef<I6TrendChartData> = computed(() => {
    const totalMonthly = totalRow.value.months
    const anomalyTotalIndices = detectAnomalyMonthsForRow(totalMonthly)

    const series: I6TrendChartData['series'] = []

    // 每个研发项目一条线
    for (const row of storedRows.value) {
      series.push({
        name: row.category || '未命名',
        data: [...row.months],
        type: 'line',
      })
    }

    // 合计线（加粗 + 异常标记点）
    const markPointData = anomalyTotalIndices.map((idx) => ({
      xAxis: idx,
      yAxis: totalMonthly[idx],
      symbolSize: 12,
    }))

    series.push({
      name: '合计',
      data: [...totalMonthly],
      type: 'line',
      lineStyle: { width: 3 },
      markPoint: markPointData.length > 0 ? { data: markPointData } : undefined,
    })

    return {
      xAxis: [...MONTH_LABELS],
      series,
      totalMonthly: [...totalMonthly],
    }
  })

  // ─── Computed: 异常月份（全局合计行）───────────────────────────────────────

  const anomalyMonths: ComputedRef<number[]> = computed(() => {
    return detectAnomalyMonthsForRow(totalRow.value.months)
  })

  // ─── Actions: 更新单元格 ──────────────────────────────────────────────────

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const idx = storedRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = storedRows.value[idx]

    // 月度列：month_0 ~ month_11
    const monthMatch = /^month_(\d{1,2})$/.exec(key)
    if (monthMatch) {
      const mIdx = Number(monthMatch[1])
      if (mIdx >= 0 && mIdx < 12) {
        row.months[mIdx] = parseNum(value)
      }
    } else if (key === 'category') {
      row.category = String(value ?? '')
    } else if (key === 'aje') {
      row.aje = parseNum(value)
    } else if (key === 'rje') {
      row.rje = parseNum(value)
    } else if (key === 'reconciliation') {
      row.reconciliation = String(value ?? '')
    } else if (key === 'priorUnadj') {
      row.priorUnadj = parseNum(value)
    } else if (key === 'priorAje') {
      row.priorAje = parseNum(value)
    } else if (key === 'priorRje') {
      row.priorRje = parseNum(value)
    } else if (key === 'individualReclass') {
      row.individualReclass = parseNum(value)
    } else if (key === 'consolidatedReclass') {
      row.consolidatedReclass = parseNum(value)
    } else if (key === 'remark') {
      row.remark = String(value ?? '')
    }

    // 触发响应式更新
    storedRows.value = [...storedRows.value]
    _persist()
  }

  // ─── Actions: 动态行增删 ──────────────────────────────────────────────────

  function addRow(category: string): void {
    if (readonly.value || !category) return
    const newRow: I6DetailStoredRow = {
      id: `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      category,
      months: new Array(12).fill(0),
      aje: 0,
      rje: 0,
      reconciliation: '',
      priorUnadj: 0,
      priorAje: 0,
      priorRje: 0,
      individualReclass: 0,
      consolidatedReclass: 0,
      remark: '',
    }
    storedRows.value = [...storedRows.value, newRow]
    _persist()
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    storedRows.value = storedRows.value.filter((r) => r.id !== id)
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(STORAGE_KEY, JSON.stringify(storedRows.value))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    /** 完整行（含公式列） */
    rows,
    /** 合计行 */
    totalRow,
    /** 趋势折线图数据（ECharts格式） */
    trendChartData,
    /** 月度合计数组（12个月） */
    monthlyTotals,
    /** 动态行添加 */
    addRow,
    /** 动态行删除 */
    removeRow,
    /** 更新单元格 */
    updateCell,
    /** 异常月份索引（合计行级别） */
    anomalyMonths,
    /** 列定义导出 */
    fixedColumns: FIXED_COLUMNS,
    monthlyColumns: MONTHLY_COLUMNS,
    summaryColumns: SUMMARY_COLUMNS,
    allColumns: ALL_COLUMNS,
    /** 月份标签 */
    monthLabels: MONTH_LABELS,
  }
}

export default useI6Detail
