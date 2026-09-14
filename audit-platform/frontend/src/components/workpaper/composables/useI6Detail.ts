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
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcMonthlyTotal,
  calcAuditedAmount,
  calcChangeRate,
} from './useI6FormulaEngine'
import {
  applyAjeToI62Detail,
  aggregateI63Nets,
  buildI63DraftsFromDetail,
} from './i6AdjustmentModel'
import { mergeI63LinesSkippingExisting } from './i6AdjDraftHelpers'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细行存储结构（仅原始输入字段） */
export interface I6DetailStoredRow {
  id: string
  /** A列：项目类别（研发项目/明细行标识，供 I6-1 审定表引用） */
  category: string
  /** X列：费用性质（人工费/材料费等，供附注披露 SUMIF） */
  expenseNature: string
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
const I63_ROWS_KEY = 'I6-3-rows'
/** 旧版 I6TabDetail 使用的存储键（迁移后不再写入） */
const LEGACY_STORAGE_KEY = 'I6-2-rows'
export const NOTE_KEY = 'I6-2-audit-note'
export const CONCLUSION_KEY = 'I6-2-audit-conclusion'
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
/** 月度变动率异常阈值（±30%） */
const ANOMALY_THRESHOLD = 30

/** 对齐致同 Excel：A列=项目类别，X列=费用性质；默认各一行对应一种费用性质 */
export const I6_DETAIL_DEFAULT_CATEGORIES = [
  '人工费',
  '材料费',
  '制造费用分摊',
  '无形资产摊销',
  '设计费',
  '装备调试费',
  '委外研发费',
  '其他',
] as const

/** 区段 Tab（宽表拆段，提升可操作性） */
export type I6DetailTabKey = 'monthly' | 'audit' | 'linkage'
export const DETAIL_TABS: Array<{ key: I6DetailTabKey; label: string }> = [
  { key: 'monthly', label: '月度明细' },
  { key: 'audit', label: '调整审定' },
  { key: 'linkage', label: '分析勾稽' },
]

/** 审计说明编制指引（对齐 Excel 第三节） */
export const I6_DETAIL_AUDIT_PROCEDURES = [
  '研发支出与研发费用区分：研发支出为资产负债类科目，研发费用为损益类科目；期末结转后形成本期研发费用。',
  '（1）检查会计政策运用是否一贯，参见 I3-4 会计政策检查表。',
  '（2）执行分析性复核：研发变动、占收入比、人均费用、预算对比等，参见 I2-5 分析表。',
  '（3）检查资本化时点支持性文件，参见 I3-6 资本化检查表。',
  '（4）获取/编制研发项目明细，参见 I2-7 项目明细表。',
  '（5）检查材料投入：I2-8；检查研发人员工时：I2-9、I2-10。',
  '（6）检查委外研发：I2-11。',
] as const

// ─── Column Definitions ──────────────────────────────────────────────────────

/** 固定列定义（左侧固定不滚动） */
export const FIXED_COLUMNS: I6DetailColumnDef[] = [
  { key: 'category', label: '项目类别(A)', editable: true, type: 'text', width: 140, fixed: 'left' },
  { key: 'expenseNature', label: '费用性质(X)', editable: true, type: 'text', width: 120, fixed: 'left' },
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

function makeDefaultRow(category: string, expenseNature?: string): I6DetailStoredRow {
  const nature = expenseNature || category
  return {
    id: `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: category || nature,
    expenseNature: nature,
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
}

function makeDefaultRows(): I6DetailStoredRow[] {
  return I6_DETAIL_DEFAULT_CATEGORIES.map((c) => makeDefaultRow(c, c))
}

/** 旧版 I6-2-rows（按研发项目）→ 新版 I6-2-detail-rows（按费用类别） */
function migrateLegacyRows(raw: any[]): I6DetailStoredRow[] {
  return raw.map((r) => {
    const months = Array.isArray(r.months)
      ? r.months.slice(0, 12).map(parseNum)
      : new Array(12).fill(0)
    while (months.length < 12) months.push(0)
    return {
      id: r.rowId ?? r.id ?? `row-${Math.random().toString(36).slice(2, 8)}`,
      category: String(r.category ?? r.name ?? r.projectName ?? '').trim(),
      expenseNature: String(r.expenseNature ?? r.col_x ?? r.category ?? r.name ?? '').trim(),
      months,
      aje: parseNum(r.aje),
      rje: parseNum(r.rje),
      reconciliation: String(r.reconciliation ?? ''),
      priorUnadj: parseNum(r.priorUnadj ?? r.priorAmount),
      priorAje: parseNum(r.priorAje),
      priorRje: parseNum(r.priorRje),
      individualReclass: parseNum(r.individualReclass),
      consolidatedReclass: parseNum(r.consolidatedReclass),
      remark: String(r.remark ?? r.code ?? ''),
    }
  }).filter((r) => r.category && r.category !== '合计')
}

function normalizeStoredRow(raw: any): I6DetailStoredRow {
  const months = Array.isArray(raw.months)
    ? raw.months.slice(0, 12).map(parseNum)
    : new Array(12).fill(0)
  // 补齐到12个月
  while (months.length < 12) months.push(0)

  return {
    id: raw.id ?? raw.rowId ?? `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: String(raw.category ?? raw.name ?? raw.projectName ?? ''),
    expenseNature: String(raw.expenseNature ?? raw.col_x ?? raw.category ?? '').trim(),
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

/** 检测月度异常：某月与前月变动率超阈值
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

/**
 * 将 TB 6602 未审发生额分配至各行（写入 12 月列，与 I1-9 摊销回填一致）
 * 多行时按上期审定占比分配；上期为 0 时平均分配
 */
export function allocateTbNetToDetailRows(
  rows: I6DetailStoredRow[],
  tbNet: number,
): { rows: I6DetailStoredRow[]; allocated: number[] } {
  if (!rows.length || !Number.isFinite(tbNet)) return { rows, allocated: [] }

  const priorBases = rows.map((r) => Math.abs(calcAuditedAmount(r.priorUnadj, r.priorAje, r.priorRje)))
  const totalPrior = priorBases.reduce((a, b) => a + b, 0)
  const allocated = new Array<number>(rows.length).fill(0)

  if (rows.length === 1) {
    allocated[0] = Math.round(tbNet * 100) / 100
  } else if (totalPrior > 0.005) {
    let remain = tbNet
    for (let i = 0; i < rows.length; i++) {
      const isLast = i === rows.length - 1
      const amt = isLast
        ? Math.round(remain * 100) / 100
        : Math.round((tbNet * priorBases[i] / totalPrior) * 100) / 100
      allocated[i] = amt
      remain -= amt
    }
  } else {
    const avg = tbNet / rows.length
    let remain = tbNet
    for (let i = 0; i < rows.length; i++) {
      const isLast = i === rows.length - 1
      const amt = isLast ? Math.round(remain * 100) / 100 : Math.round(avg * 100) / 100
      allocated[i] = amt
      remain -= amt
    }
  }

  const next = rows.map((row, i) => {
    const months = new Array(12).fill(0)
    months[11] = allocated[i]
    return { ...row, months }
  })
  return { rows: next, allocated }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Detail(options: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  isReadonly?: Ref<boolean>
  tbData?: Ref<{ unadjusted6602: number; audited6602?: number }>
}) {
  const { allResponses, onSave, isReadonly, tbData } = options
  const readonly = isReadonly ?? computed(() => false)

  // ─── Internal State ────────────────────────────────────────────────────────

  const storedRows = ref<I6DetailStoredRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _load(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    const parsed = safeParse(raw)
    if (parsed.length > 0) {
      storedRows.value = parsed
      return
    }
    const legacyItem = allResponses.value.get(LEGACY_STORAGE_KEY)
    const legacyRaw = legacyItem?.remark ?? (typeof legacyItem === 'string' ? legacyItem : null)
    const legacyParsed = legacyRaw ? safeParse(legacyRaw) : []
    if (legacyParsed.length > 0) {
      storedRows.value = migrateLegacyRows(legacyParsed)
      _persist()
      return
    }
    storedRows.value = makeDefaultRows()
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

  /** 各月比例行：各月合计 / 全年审定合计 × 100（%） */
  const monthlyRatios: ComputedRef<(number | null)[]> = computed(() => {
    const annual = totalRow.value.auditedAmount
    if (annual === 0) return new Array(12).fill(null)
    return totalRow.value.months.map((m) => (m / annual) * 100)
  })

  /** 与 I6-1 审定表合计勾稽（允许 ±0.01） */
  const adjudicationCrossCheck = computed(() => {
    const detailAudited = totalRow.value.auditedAmount
    const adjItem = allResponses.value.get('I6-1-rows') || allResponses.value.get('I6-adj-rows')
    const adjRaw = adjItem?.remark
    if (!adjRaw) return { hasData: false, detailAudited, adjudicationTotal: 0, diff: 0, isBalanced: true }
    try {
      const rows = JSON.parse(adjRaw)
      if (!Array.isArray(rows)) return { hasData: false, detailAudited, adjudicationTotal: 0, diff: 0, isBalanced: true }
      const adjudicationTotal = rows
        .filter((r: any) => !r.isTotal && String(r.类别 || r.category || '') !== '合计')
        .reduce((s: number, r: any) => s + parseNum(r.本期审定 ?? r.auditedAmount), 0)
      const diff = detailAudited - adjudicationTotal
      return {
        hasData: adjudicationTotal !== 0 || detailAudited !== 0,
        detailAudited,
        adjudicationTotal,
        diff,
        isBalanced: Math.abs(diff) <= 0.01,
      }
    } catch {
      return { hasData: false, detailAudited, adjudicationTotal: 0, diff: 0, isBalanced: true }
    }
  })

  /** 与 TB 6602 未审发生额勾稽 */
  const tbCrossCheck = computed(() => {
    const tbNet = tbData?.value?.unadjusted6602 ?? 0
    const detailUnadj = totalRow.value.unadjTotal
    const diff = detailUnadj - tbNet
    return {
      hasData: Math.abs(tbNet) > 0.005 || Math.abs(detailUnadj) > 0.005,
      tbNet,
      detailUnadj,
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
    }
  })

  /** 与 I6-3 调整分录 AJE/RJE 勾稽 */
  const i63CrossCheck = computed(() => {
    const item = allResponses.value.get(I63_ROWS_KEY)
    const raw = item?.remark
    let adjRows: any[] = []
    try { adjRows = raw ? JSON.parse(raw) : [] } catch { adjRows = [] }
    if (!Array.isArray(adjRows) || !adjRows.length) {
      return { hasData: false, isBalanced: true, detailAje: totalRow.value.aje, detailRje: totalRow.value.rje, i63Aje: 0, i63Rje: 0, diffAje: 0, diffRje: 0 }
    }
    const nets = aggregateI63Nets(adjRows)
    const diffAje = totalRow.value.aje - nets.ajeNet
    const diffRje = totalRow.value.rje - nets.rjeNet
    return {
      hasData: true,
      isBalanced: Math.abs(diffAje) <= 0.01 && Math.abs(diffRje) <= 0.01,
      detailAje: totalRow.value.aje,
      detailRje: totalRow.value.rje,
      i63Aje: nets.ajeNet,
      i63Rje: nets.rjeNet,
      diffAje,
      diffRje,
    }
  })

  function _parseI63Rows(): any[] {
    const item = allResponses.value.get(I63_ROWS_KEY)
    const raw = item?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /** 从 I6-3 同步 AJE/RJE 至明细行 */
  function syncAjeFromI63(adjRows?: any[]): {
    ok: boolean
    message: string
    approx?: boolean
  } {
    if (readonly.value) return { ok: false, message: '只读' }
    const source = adjRows?.length ? adjRows : _parseI63Rows()
    if (!source.length) return { ok: false, message: 'I6-3 无调整分录可同步' }
    const result = applyAjeToI62Detail(storedRows.value, source)
    storedRows.value = result.rows as I6DetailStoredRow[]
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      return { ok: false, message: 'I6-3 中无 6602 研发费用相关调整' }
    }
    return {
      ok: true,
      approx: result.approx,
      message: result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核附注项目）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}`,
    }
  }

  /** 将 I6-2 明细 AJE/RJE 推送为 I6-3 平衡分录 */
  function pushAjeToI63(): { ok: boolean; message: string; added: number } {
    if (readonly.value) return { ok: false, message: '只读', added: 0 }
    const drafts = buildI63DraftsFromDetail(storedRows.value)
    if (!drafts.length) return { ok: false, message: '明细表无 AJE/RJE 可推送', added: 0 }
    const existing = _parseI63Rows()
    const { merged, added } = mergeI63LinesSkippingExisting(existing, drafts)
    if (!added) return { ok: false, message: '对应分录已存在于 I6-3', added: 0 }
    if (onSave) onSave(I63_ROWS_KEY, merged)
    const existingResp = allResponses.value.get(I63_ROWS_KEY) || { item_id: I63_ROWS_KEY }
    allResponses.value.set(I63_ROWS_KEY, { ...existingResp, item_id: I63_ROWS_KEY, remark: JSON.stringify(merged) })
    try {
      window.dispatchEvent(new CustomEvent('i6:adjustment-writeback', {
        detail: { source: 'I6-2', rows: merged, entries: merged },
      }))
    } catch { /* ignore */ }
    return {
      ok: true,
      message: `已向 I6-3 推送 ${added} 行平衡分录（借贷已配对，请复核对方科目）`,
      added,
    }
  }

  /**
   * 从 TB 6602 写入各行未审发生额（12 月列）
   * @param tbUnadjustedNet 未审净发生额；缺省时取 tbData.unadjusted6602
   */
  function applyTbData(tbUnadjustedNet?: number): { ok: boolean; message: string } {
    if (readonly.value) return { ok: false, message: '只读' }
    const tbNet = tbUnadjustedNet ?? tbData?.value?.unadjusted6602 ?? 0
    if (!Number.isFinite(tbNet)) return { ok: false, message: 'TB 发生额无效' }
    if (!storedRows.value.length) return { ok: false, message: '明细表无行可写入' }
    const { rows: next, allocated } = allocateTbNetToDetailRows(storedRows.value, tbNet)
    storedRows.value = next
    _persist()
    const mode = storedRows.value.length === 1
      ? '单行'
      : (storedRows.value.some((r) => calcAuditedAmount(r.priorUnadj, r.priorAje, r.priorRje) !== 0)
        ? '按上期审定占比'
        : '平均分配')
    return {
      ok: true,
      message: `已从 TB 6602 写入未审合计 ${tbNet.toLocaleString('zh-CN')}（${mode}，${allocated.length} 行，计入 12 月）`,
    }
  }

  function onAdjustmentWriteback(): void {
    if (readonly.value) return
    syncAjeFromI63()
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      window.addEventListener('i6:adjustment-writeback', onAdjustmentWriteback)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('i6:adjustment-writeback', onAdjustmentWriteback)
    })
  }

  // ─── Computed: 趋势折线图数据（ECharts）───────────────────────────────────

  const trendChartData: ComputedRef<I6TrendChartData> = computed(() => {
    const totalMonthly = totalRow.value.months
    const anomalyTotalIndices = detectAnomalyMonthsForRow(totalMonthly)

    const series: I6TrendChartData['series'] = []

    // 每个研发项目一条线
    for (const row of storedRows.value) {
      series.push({
        name: row.expenseNature || row.category || '未命名',
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
    } else if (key === 'expenseNature') {
      row.expenseNature = String(value ?? '')
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

  function addRow(category: string, expenseNature?: string): void {
    if (readonly.value || !category) return
    const nature = (expenseNature || category).trim()
    const newRow: I6DetailStoredRow = {
      id: `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      category: category.trim(),
      expenseNature: nature,
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

  /** 导入后批量替换行 */
  function replaceRows(next: I6DetailStoredRow[]): void {
    if (readonly.value) return
    storedRows.value = next.map(normalizeStoredRow)
    _persist()
  }

  /** 从 I1-9 回填「无形资产摊销」行 */
  function applyI1AmortAmount(amount: number, keywords: string[] = ['无形资产摊销']): {
    ok: boolean
    message: string
  } {
    if (readonly.value) return { ok: false, message: '只读' }
    const hit = storedRows.value.find((r) =>
      keywords.some((k) => String(r.expenseNature || r.category || '').includes(k)),
    )
    if (!hit) {
      return { ok: false, message: '未找到「无形资产摊销」明细行' }
    }
    const months = new Array(12).fill(0)
    months[11] = amount
    hit.months = months
    storedRows.value = [...storedRows.value]
    _persist()
    return { ok: true, message: `已回填「${hit.category}」= ${amount.toFixed(2)}` }
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
    /** 各月占全年审定比（%） */
    monthlyRatios,
    /** 与 I6-1 审定合计勾稽 */
    adjudicationCrossCheck,
    /** 与 TB 6602 未审发生额勾稽 */
    tbCrossCheck,
    /** 与 I6-3 AJE/RJE 勾稽 */
    i63CrossCheck,
    /** 从 TB 6602 写入未审发生额 */
    applyTbData,
    /** 从 I6-3 同步 AJE/RJE */
    syncAjeFromI63,
    /** 推送明细 AJE/RJE 至 I6-3 草稿 */
    pushAjeToI63,
    /** 动态行添加 */
    addRow,
    /** 动态行删除 */
    removeRow,
    /** 导入批量替换 */
    replaceRows,
    /** 从 I1-9 回填无形资产摊销 */
    applyI1AmortAmount,
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
    /** 存储键 */
    storageKey: STORAGE_KEY,
  }
}

export default useI6Detail
