/**
 * useH2Impairment — H2-15/16 减值组 composable
 *
 * 减值迹象6项判断 + 测算表 + DCF模型
 * 敏感性分析矩阵 + 可收回金额MAX选取
 * 从H2-13取数停工工程列表
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.14
 * Requirements: 12.1-12.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcDcfPresentValue, calcTerminalValue } from './useH2InterestCapEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentSign {
  id: string
  label: string
  value: boolean
}

export interface ImpairmentTestRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 账面价值 */
  bookValue: number
  /** 公允价值 - 处置费用 */
  fairValueLessDisposal: number
  /** 使用价值(DCF) */
  valueInUse: number
  /** 可收回金额 = MAX(公允-处置, DCF) */
  recoverableAmount: number
  /** 减值金额 = MAX(账面-可收回, 0) */
  impairmentAmount: number
}

export interface DcfAssumptions {
  /** 折现率(%) */
  discountRate: number
  /** 预测期(年) */
  forecastYears: number
  /** 永续增长率(%) */
  growthRate: number
  /** 终值折现期数 */
  terminalPeriod: number
}

export interface DcfCashFlow {
  year: number
  amount: number
}

export interface SensitivityCell {
  discountRate: number
  growthRate: number
  presentValue: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNS_KEY = 'H2-15-impairment-signs'
const TEST_ROWS_KEY = 'H2-15-test-rows'
const DCF_KEY = 'H2-16-dcf-assumptions'
const CASHFLOWS_KEY = 'H2-16-cashflows'
const NOTE_KEY = 'H2-15-audit-note'
const CONCLUSION_KEY = 'H2-15-audit-conclusion'

/** 减值迹象6项（CAS8） */
const DEFAULT_SIGNS: ImpairmentSign[] = [
  { id: 'sign-1', label: '停工超过12个月', value: false },
  { id: 'sign-2', label: '技术淘汰', value: false },
  { id: 'sign-3', label: '预算超支>50%', value: false },
  { id: 'sign-4', label: '市场环境恶化', value: false },
  { id: 'sign-5', label: '用途变更', value: false },
  { id: 'sign-6', label: '其他迹象', value: false },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Impairment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const signs = ref<ImpairmentSign[]>([...DEFAULT_SIGNS])
  const testRows = ref<ImpairmentTestRow[]>([])
  const dcfAssumptions = ref<DcfAssumptions>({
    discountRate: 10,
    forecastYears: 5,
    growthRate: 2,
    terminalPeriod: 5,
  })
  const cashFlows = ref<DcfCashFlow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

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

  function _recalcTestRow(row: ImpairmentTestRow): void {
    row.recoverableAmount = Math.max(row.fairValueLessDisposal, row.valueInUse)
    row.impairmentAmount = Math.max(row.bookValue - row.recoverableAmount, 0)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    // 减值迹象
    const signsData = _getJson(SIGNS_KEY)
    if (Array.isArray(signsData) && signsData.length > 0) {
      signs.value = signsData.map((s: any, i: number) => ({
        id: s.id ?? DEFAULT_SIGNS[i]?.id ?? `sign-${i}`,
        label: s.label ?? DEFAULT_SIGNS[i]?.label ?? '',
        value: !!s.value,
      }))
    } else {
      signs.value = [...DEFAULT_SIGNS]
    }

    // 从H2-13取停工工程列表自动标记"停工超12个月"迹象
    const h2_13_resp = options.allResponses.value.get('H2-13-rows')
    const h2_13_raw = h2_13_resp?.remark ?? h2_13_resp?.conclusion
    if (h2_13_raw) {
      try {
        const checkRows = JSON.parse(h2_13_raw)
        if (Array.isArray(checkRows)) {
          const hasStopped = checkRows.some((r: any) => r.constructionStatus === '停工')
          if (hasStopped) {
            const sign1 = signs.value.find(s => s.id === 'sign-1')
            if (sign1) sign1.value = true
          }
        }
      } catch { /* ignore */ }
    }

    // 测算表
    const testData = _getJson(TEST_ROWS_KEY)
    if (Array.isArray(testData)) {
      testRows.value = testData.map((r: any) => {
        const row: ImpairmentTestRow = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          name: r.name ?? '',
          bookValue: Number(r.bookValue) || 0,
          fairValueLessDisposal: Number(r.fairValueLessDisposal) || 0,
          valueInUse: Number(r.valueInUse) || 0,
          recoverableAmount: 0,
          impairmentAmount: 0,
        }
        _recalcTestRow(row)
        return row
      })
    } else {
      testRows.value = []
    }

    // DCF假设
    const dcf = _getJson(DCF_KEY)
    if (dcf && typeof dcf === 'object') {
      dcfAssumptions.value = {
        discountRate: Number(dcf.discountRate) || 10,
        forecastYears: Number(dcf.forecastYears) || 5,
        growthRate: Number(dcf.growthRate) || 2,
        terminalPeriod: Number(dcf.terminalPeriod) || 5,
      }
    }

    // 现金流预测
    const cfs = _getJson(CASHFLOWS_KEY)
    if (Array.isArray(cfs)) {
      cashFlows.value = cfs.map((c: any) => ({
        year: Number(c.year) || 0,
        amount: Number(c.amount) || 0,
      }))
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 存在减值迹象的数量 */
  const signCount: ComputedRef<number> = computed(() =>
    signs.value.filter(s => s.value).length,
  )

  /** 是否需要做减值测试 (≥2项迹象) */
  const needsImpairmentTest: ComputedRef<boolean> = computed(() => signCount.value >= 2)

  /** 减值金额合计 */
  const totalImpairment: ComputedRef<number> = computed(() =>
    testRows.value.reduce((s, r) => s + r.impairmentAmount, 0),
  )

  /** DCF现值计算 */
  const dcfPresentValue: ComputedRef<number> = computed(() => {
    const rate = dcfAssumptions.value.discountRate / 100
    if (rate <= 0 || cashFlows.value.length === 0) return 0

    const cfAmounts = cashFlows.value.map(c => c.amount)
    const pv = calcDcfPresentValue(cfAmounts, rate)

    // 加终值
    const lastCF = cfAmounts[cfAmounts.length - 1] ?? 0
    const tv = calcTerminalValue(
      lastCF * (1 + dcfAssumptions.value.growthRate / 100),
      rate,
      dcfAssumptions.value.growthRate / 100,
    )
    // 终值折现到今天
    const tvPV = tv / Math.pow(1 + rate, cashFlows.value.length)

    return pv + tvPV
  })

  /** 敏感性分析矩阵 (折现率 × 增长率) */
  const sensitivityMatrix: ComputedRef<SensitivityCell[]> = computed(() => {
    const baseRate = dcfAssumptions.value.discountRate
    const baseGrowth = dcfAssumptions.value.growthRate
    const cfAmounts = cashFlows.value.map(c => c.amount)

    const rateSteps = [-2, -1, 0, 1, 2]
    const growthSteps = [-1, -0.5, 0, 0.5, 1]
    const cells: SensitivityCell[] = []

    for (const rStep of rateSteps) {
      for (const gStep of growthSteps) {
        const dr = (baseRate + rStep) / 100
        const gr = (baseGrowth + gStep) / 100
        if (dr <= 0 || dr <= gr) {
          cells.push({ discountRate: baseRate + rStep, growthRate: baseGrowth + gStep, presentValue: 0 })
          continue
        }
        const pv = calcDcfPresentValue(cfAmounts, dr)
        const lastCF = cfAmounts[cfAmounts.length - 1] ?? 0
        const tv = calcTerminalValue(lastCF * (1 + gr), dr, gr)
        const tvPV = tv / Math.pow(1 + dr, cfAmounts.length)
        cells.push({
          discountRate: baseRate + rStep,
          growthRate: baseGrowth + gStep,
          presentValue: pv + tvPV,
        })
      }
    }
    return cells
  })

  /** 从H2-13取数停工工程列表 */
  const stoppedProjectsFromH13: ComputedRef<string[]> = computed(() => {
    const resp = options.allResponses.value.get('H2-13-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []
    try {
      const rows = JSON.parse(raw)
      if (Array.isArray(rows)) {
        return rows
          .filter((r: any) => r.constructionStatus === '停工')
          .map((r: any) => r.name ?? '')
          .filter((n: string) => n)
      }
    } catch { /* ignore */ }
    return []
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateSign(signId: string, value: boolean): void {
    if (options.isReadonly.value) return
    const sign = signs.value.find(s => s.id === signId)
    if (sign) {
      sign.value = value
      options.onSave?.(SIGNS_KEY, signs.value)
    }
  }

  function addTestRow(name: string): void {
    if (options.isReadonly.value) return
    const row: ImpairmentTestRow = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name || '',
      bookValue: 0,
      fairValueLessDisposal: 0,
      valueInUse: 0,
      recoverableAmount: 0,
      impairmentAmount: 0,
    }
    testRows.value.push(row)
    _persistTestRows()
  }

  function removeTestRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = testRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      testRows.value.splice(idx, 1)
      _persistTestRows()
    }
  }

  function updateTestRow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = testRows.value.find(r => r.rowId === rowId)
    if (!row) return
    const formulaFields = ['recoverableAmount', 'impairmentAmount']
    if (formulaFields.includes(field)) return
    ;(row as any)[field] = field === 'name' ? String(value ?? '') : (Number(value) || 0)
    _recalcTestRow(row)
    _persistTestRows()
  }

  function updateDcfAssumptions(assumptions: Partial<DcfAssumptions>): void {
    if (options.isReadonly.value) return
    Object.assign(dcfAssumptions.value, assumptions)
    options.onSave?.(DCF_KEY, dcfAssumptions.value)
  }

  function addCashFlow(): void {
    if (options.isReadonly.value) return
    const nextYear = cashFlows.value.length > 0
      ? cashFlows.value[cashFlows.value.length - 1].year + 1
      : 1
    cashFlows.value.push({ year: nextYear, amount: 0 })
    options.onSave?.(CASHFLOWS_KEY, cashFlows.value)
  }

  function removeCashFlow(year: number): void {
    if (options.isReadonly.value) return
    const idx = cashFlows.value.findIndex(c => c.year === year)
    if (idx !== -1) {
      cashFlows.value.splice(idx, 1)
      options.onSave?.(CASHFLOWS_KEY, cashFlows.value)
    }
  }

  function updateCashFlow(year: number, amount: number): void {
    if (options.isReadonly.value) return
    const cf = cashFlows.value.find(c => c.year === year)
    if (cf) {
      cf.amount = Number(amount) || 0
      options.onSave?.(CASHFLOWS_KEY, cashFlows.value)
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persistTestRows(): void {
    options.onSave?.(TEST_ROWS_KEY, testRows.value.map(r => ({
      rowId: r.rowId, name: r.name, bookValue: r.bookValue,
      fairValueLessDisposal: r.fairValueLessDisposal, valueInUse: r.valueInUse,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    signs, testRows, dcfAssumptions, cashFlows, auditNote, auditConclusion,
    signCount, needsImpairmentTest, totalImpairment,
    dcfPresentValue, sensitivityMatrix, stoppedProjectsFromH13,
    updateSign, addTestRow, removeTestRow, updateTestRow,
    updateDcfAssumptions, addCashFlow, removeCashFlow, updateCashFlow,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2Impairment
