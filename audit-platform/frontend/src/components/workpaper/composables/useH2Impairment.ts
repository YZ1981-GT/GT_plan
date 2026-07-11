/**
 * useH2Impairment — H2-15/16 减值组 composable
 *
 * H2-15 减值迹象6项判断(是/否/不适用+依据) + 减值测算表(账面/可收回/减值)
 * H2-16 DCF模型(假设+逐年现金流预测+折现+终值) + 敏感性矩阵 + 可收回金额MAX选取
 * 从H2-13取数停工工程自动标记减值迹象
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.14
 * Requirements: 12.1-12.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H2-15 减值迹象行（CAS8 六项） */
export interface ImpairmentSignRow {
  rowId: string
  /** 减值迹象描述 */
  indicator: string
  /** 是否存在（是/否/不适用） */
  exists: '是' | '否' | '不适用' | ''
  /** 判断依据/说明 */
  evidence: string
}

/** H2-15 减值测算行 */
export interface ImpairmentCalcRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 账面价值 */
  bookValue: number
  /** 可收回金额（可手工填入，或从H2-16带入） */
  recoverableAmount: number
  /** 减值金额（公式列：=MAX(账面-可收回, 0)） */
  impairmentAmount: number
  /** 评估方法 */
  method: string
  /** 备注 */
  remark: string
}

/** H2-16 DCF关键假设 */
export interface DcfAssumptions {
  /** 折现率(WACC,%) */
  discountRate: number
  /** 预测期(年) */
  forecastYears: number
  /** 永续增长率(%) */
  growthRate: number
  /** 处置费用率(%) */
  disposalCostRate: number
  /** 账面价值（用于敏感性红色对比） */
  bookValue: number
}

/** H2-16 逐年现金流预测行 */
export interface DcfCashFlowRow {
  rowId: string
  /** 年份序号(1..n) */
  year: number
  /** 收入预测 */
  revenue: number
  /** 成本预测 */
  cost: number
  /** 净现金流（公式列：=收入-成本） */
  netCashFlow: number
  /** 折现因子（公式列：=1/(1+r)^year） */
  discountFactor: number
  /** 现值（公式列：=净现金流×折现因子） */
  presentValue: number
}

/** 敏感性矩阵行（label + 各增长率列 g_<col>） */
export interface SensitivityRow {
  label: string
  [key: string]: number | string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNS_KEY = 'H2-15-impairment-signs'
const CALC_KEY = 'H2-15-test-rows'
const DCF_KEY = 'H2-16-dcf-assumptions'
const CASHFLOWS_KEY = 'H2-16-cashflows'
const FAIRVALUE_KEY = 'H2-16-fair-value'
const NOTE_KEY = 'H2-15-audit-note'
const CONCLUSION_KEY = 'H2-15-audit-conclusion'

/** 减值迹象6项（CAS8） */
const DEFAULT_SIGN_INDICATORS: string[] = [
  '资产市价大幅下跌，明显高于因时间推移或正常使用而预计的下跌',
  '技术、市场、经济或法律环境发生重大不利变化',
  '市场利率或其他市场投资报酬率上升，影响资产可收回金额',
  '资产已经陈旧过时或实体损坏（如长期停工）',
  '资产的用途发生重大不利变化（如闲置、终止使用或计划提前处置）',
  '内部报告证据表明资产的经济绩效已经低于或将低于预期',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Impairment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 当前区段（impairment=H2-15 / recoverable=H2-16），仅组件侧标识 */
  section?: 'impairment' | 'recoverable'
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const signRows = ref<ImpairmentSignRow[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])
  const assumptions = ref<DcfAssumptions>({
    discountRate: 10,
    forecastYears: 5,
    growthRate: 2,
    disposalCostRate: 0,
    bookValue: 0,
  })
  const cashFlowRows = ref<DcfCashFlowRow[]>([])
  const fairValueLessDisposal = ref(0)
  const auditNote = ref('')
  const conclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _num(v: any): number {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }

  function _defaultSignRows(): ImpairmentSignRow[] {
    return DEFAULT_SIGN_INDICATORS.map((indicator, i) => ({
      rowId: `sign-${i + 1}`,
      indicator,
      exists: '',
      evidence: '',
    }))
  }

  function _recalcCalcRow(row: ImpairmentCalcRow): void {
    row.impairmentAmount = Math.max(row.bookValue - row.recoverableAmount, 0)
  }

  function _recalcCashFlowRow(row: DcfCashFlowRow): void {
    const r = assumptions.value.discountRate / 100
    row.netCashFlow = row.revenue - row.cost
    row.discountFactor = r > -1 ? 1 / Math.pow(1 + r, row.year) : 0
    row.presentValue = row.netCashFlow * row.discountFactor
  }

  function _recalcAllCashFlows(): void {
    for (const row of cashFlowRows.value) _recalcCashFlowRow(row)
  }

  /** 按预测期年数同步现金流行（补齐/裁剪，保留已填数据） */
  function _syncCashFlowRows(): void {
    const years = Math.max(1, Math.min(20, Math.round(assumptions.value.forecastYears || 1)))
    const existing = cashFlowRows.value
    const next: DcfCashFlowRow[] = []
    for (let y = 1; y <= years; y++) {
      const prev = existing.find(c => c.year === y)
      const row: DcfCashFlowRow = prev
        ? { ...prev, year: y }
        : {
            rowId: `cf-${y}`,
            year: y,
            revenue: 0,
            cost: 0,
            netCashFlow: 0,
            discountFactor: 0,
            presentValue: 0,
          }
      _recalcCashFlowRow(row)
      next.push(row)
    }
    cashFlowRows.value = next
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    // 减值迹象
    const signsData = _getJson(SIGNS_KEY)
    if (Array.isArray(signsData) && signsData.length > 0) {
      signRows.value = signsData.map((s: any, i: number) => ({
        rowId: s.rowId ?? `sign-${i + 1}`,
        indicator: s.indicator ?? DEFAULT_SIGN_INDICATORS[i] ?? '',
        exists: (s.exists === '是' || s.exists === '否' || s.exists === '不适用') ? s.exists : '',
        evidence: s.evidence ?? '',
      }))
    } else {
      signRows.value = _defaultSignRows()
    }

    // 从H2-13取停工工程自动标记"长期停工"迹象
    const h2_13_resp = options.allResponses.value.get('H2-13-rows')
    const h2_13_raw = h2_13_resp?.remark ?? h2_13_resp?.conclusion
    if (h2_13_raw) {
      try {
        const rows = JSON.parse(h2_13_raw)
        if (Array.isArray(rows) && rows.some((r: any) => r.constructionStatus === '停工')) {
          const s4 = signRows.value.find(s => s.rowId === 'sign-4')
          if (s4 && s4.exists === '') s4.exists = '是'
        }
      } catch { /* ignore */ }
    }

    // 减值测算表
    const calcData = _getJson(CALC_KEY)
    if (Array.isArray(calcData)) {
      calcRows.value = calcData.map((r: any) => {
        const row: ImpairmentCalcRow = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          name: r.name ?? '',
          bookValue: _num(r.bookValue),
          recoverableAmount: _num(r.recoverableAmount),
          impairmentAmount: 0,
          method: r.method ?? '',
          remark: r.remark ?? '',
        }
        _recalcCalcRow(row)
        return row
      })
    } else {
      calcRows.value = []
    }

    // DCF假设
    const dcf = _getJson(DCF_KEY)
    if (dcf && typeof dcf === 'object') {
      assumptions.value = {
        discountRate: _num(dcf.discountRate) || 10,
        forecastYears: _num(dcf.forecastYears) || 5,
        growthRate: _num(dcf.growthRate) || 2,
        disposalCostRate: _num(dcf.disposalCostRate),
        bookValue: _num(dcf.bookValue),
      }
    }

    // 公允价值-处置费用
    const fv = _getJson(FAIRVALUE_KEY)
    if (fv != null && typeof fv === 'object' && 'value' in fv) {
      fairValueLessDisposal.value = _num((fv as any).value)
    } else if (typeof fv === 'number') {
      fairValueLessDisposal.value = fv
    }

    // 现金流预测
    const cfs = _getJson(CASHFLOWS_KEY)
    if (Array.isArray(cfs) && cfs.length > 0) {
      cashFlowRows.value = cfs.map((c: any, i: number) => {
        const row: DcfCashFlowRow = {
          rowId: c.rowId ?? `cf-${i + 1}`,
          year: _num(c.year) || (i + 1),
          revenue: _num(c.revenue),
          cost: _num(c.cost),
          netCashFlow: 0,
          discountFactor: 0,
          presentValue: 0,
        }
        _recalcCashFlowRow(row)
        return row
      })
    }
    // 确保与预测期年数一致
    _syncCashFlowRows()

    auditNote.value = _getString(NOTE_KEY)
    conclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: H2-15 ───────────────────────────────────────────────────────

  /** 是否存在减值迹象（任一"是"） */
  const hasImpairmentSign: ComputedRef<boolean> = computed(() =>
    signRows.value.some(s => s.exists === '是'),
  )

  /** 减值金额合计 */
  const totalImpairment: ComputedRef<number> = computed(() =>
    calcRows.value.reduce((s, r) => s + r.impairmentAmount, 0),
  )

  // ─── Computed: H2-16 DCF ───────────────────────────────────────────────────

  /** 预测期现金流现值合计 */
  const pvTotal: ComputedRef<number> = computed(() =>
    cashFlowRows.value.reduce((s, r) => s + r.presentValue, 0),
  )

  /** 终值现值（Gordon永续增长，折现到今天） */
  const tvPresent: ComputedRef<number> = computed(() => {
    const r = assumptions.value.discountRate / 100
    const g = assumptions.value.growthRate / 100
    const n = cashFlowRows.value.length
    if (n === 0 || r <= g || r <= 0) return 0
    const lastNetCF = cashFlowRows.value[n - 1]?.netCashFlow ?? 0
    const tv = (lastNetCF * (1 + g)) / (r - g)
    return tv / Math.pow(1 + r, n)
  })

  /** 预计未来现金流量现值(A) = 预测期现值 + 终值现值 */
  const totalPV: ComputedRef<number> = computed(() => pvTotal.value + tvPresent.value)

  /** 可收回金额 = MAX(使用价值A, 公允价值-处置费用B) */
  const recoverableAmount: ComputedRef<number> = computed(() =>
    Math.max(totalPV.value, fairValueLessDisposal.value),
  )

  // ─── Computed: 敏感性矩阵 ──────────────────────────────────────────────────

  /** 计算给定折现率/增长率下的现值（预测期现值+终值现值） */
  function _pvAt(discountPct: number, growthPct: number): number {
    const r = discountPct / 100
    const g = growthPct / 100
    if (r <= 0) return 0
    let pv = 0
    for (const row of cashFlowRows.value) {
      pv += row.netCashFlow / Math.pow(1 + r, row.year)
    }
    const n = cashFlowRows.value.length
    if (n > 0 && r > g) {
      const lastNetCF = cashFlowRows.value[n - 1]?.netCashFlow ?? 0
      const tv = (lastNetCF * (1 + g)) / (r - g)
      pv += tv / Math.pow(1 + r, n)
    }
    return pv
  }

  /** 敏感性列（增长率档位标签，如 "1.0" "1.5" ...） */
  const sensitivityCols: ComputedRef<string[]> = computed(() => {
    const baseG = assumptions.value.growthRate
    return [-1, -0.5, 0, 0.5, 1].map(step => (baseG + step).toFixed(1))
  })

  /** 敏感性矩阵：行=折现率档位，列=增长率档位（key: g_<col>） */
  const sensitivityMatrix: ComputedRef<SensitivityRow[]> = computed(() => {
    const baseR = assumptions.value.discountRate
    const cols = sensitivityCols.value
    return [-2, -1, 0, 1, 2].map(rStep => {
      const rate = baseR + rStep
      const row: SensitivityRow = { label: `r=${rate.toFixed(1)}%` }
      for (const col of cols) {
        row[`g_${col}`] = _pvAt(rate, parseFloat(col))
      }
      return row
    })
  })

  // ─── Actions: H2-15 迹象 ───────────────────────────────────────────────────

  function updateSignCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = signRows.value.find(s => s.rowId === rowId)
    if (!row) return
    if (field === 'exists') {
      row.exists = (value === '是' || value === '否' || value === '不适用') ? value : ''
    } else if (field === 'indicator' || field === 'evidence') {
      ;(row as any)[field] = String(value ?? '')
    }
    _persistSigns()
  }

  // ─── Actions: H2-15 测算 ───────────────────────────────────────────────────

  function addCalcRow(name?: string): void {
    if (options.isReadonly.value) return
    calcRows.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name || '',
      bookValue: 0,
      recoverableAmount: 0,
      impairmentAmount: 0,
      method: '',
      remark: '',
    })
    _persistCalc()
  }

  function removeCalcRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = calcRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      calcRows.value.splice(idx, 1)
      _persistCalc()
    }
  }

  function updateCalcCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = calcRows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (field === 'impairmentAmount') return // 公式列
    const numFields = ['bookValue', 'recoverableAmount']
    if (numFields.includes(field)) {
      ;(row as any)[field] = _num(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcCalcRow(row)
    _persistCalc()
  }

  // ─── Actions: H2-16 假设/现金流 ────────────────────────────────────────────

  function updateAssumption(field: string, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'fairValueLessDisposal') {
      fairValueLessDisposal.value = _num(value)
      options.onSave?.(FAIRVALUE_KEY, { value: fairValueLessDisposal.value })
      return
    }
    if (field in assumptions.value) {
      ;(assumptions.value as any)[field] = _num(value)
      // 折现率/预测期变化需重算现金流
      if (field === 'forecastYears') {
        _syncCashFlowRows()
      } else if (field === 'discountRate') {
        _recalcAllCashFlows()
      }
      options.onSave?.(DCF_KEY, assumptions.value)
    }
  }

  function updateCashFlowCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = cashFlowRows.value.find(c => c.rowId === rowId)
    if (!row) return
    const formulaFields = ['netCashFlow', 'discountFactor', 'presentValue']
    if (formulaFields.includes(field)) return
    if (field === 'revenue' || field === 'cost' || field === 'year') {
      ;(row as any)[field] = _num(value)
    }
    _recalcCashFlowRow(row)
    _persistCashFlows()
  }

  // ─── Actions: 结论/说明 ────────────────────────────────────────────────────

  function saveConclusion(text: string): void {
    conclusion.value = text
    options.onSave?.(CONCLUSION_KEY, text)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSigns(): void {
    options.onSave?.(SIGNS_KEY, signRows.value.map(s => ({
      rowId: s.rowId, indicator: s.indicator, exists: s.exists, evidence: s.evidence,
    })))
  }

  function _persistCalc(): void {
    options.onSave?.(CALC_KEY, calcRows.value.map(r => ({
      rowId: r.rowId, name: r.name, bookValue: r.bookValue,
      recoverableAmount: r.recoverableAmount, method: r.method, remark: r.remark,
    })))
  }

  function _persistCashFlows(): void {
    options.onSave?.(CASHFLOWS_KEY, cashFlowRows.value.map(c => ({
      rowId: c.rowId, year: c.year, revenue: c.revenue, cost: c.cost,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    signRows, calcRows, assumptions, cashFlowRows, fairValueLessDisposal,
    auditNote, conclusion,
    // Computed: H2-15
    hasImpairmentSign, totalImpairment,
    // Computed: H2-16
    pvTotal, tvPresent, totalPV, recoverableAmount,
    sensitivityCols, sensitivityMatrix,
    // Actions
    updateSignCell,
    addCalcRow, removeCalcRow, updateCalcCell,
    updateAssumption, updateCashFlowCell,
    saveConclusion, saveNote,
    initFromAllResponses,
  }
}

export default useH2Impairment
