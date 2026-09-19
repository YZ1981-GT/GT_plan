/**
 * useH4Recoverable — H4-8 工程物资可收回金额 composable
 *
 * 对齐 Excel「工程物资减值准备测试表-可收回金额」：
 *   一、公允净额（三层次公允 + 处置费用明细）
 *   二、预计未来现金流量现值（DCF + WACC/CAPM）
 *   三、可收回金额 = MAX(①,②) → 回写 H4-7
 *   四、敏感性矩阵
 *
 * 纯函数/类型见 h4RecoverableModel.ts
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcRecoverableAmount } from './useH4FormulaEngine'
import type { H4RecoverableSourceKind, H4SensitivityRow } from './h4RecoverableModel'
import {
  recalcH4ImpairmentCalcRow,
  type H4ImpairmentCalcRow,
} from './useH4Impairment'
import type {
  H4FairValueDisposal,
  H4WaccParams,
  H4DcfAssumptions,
  H4DcfCashFlowRow,
  H4RecoverableGroup,
  H4UpstreamCandidate,
  H48SyncCheck,
} from './h4RecoverableModel'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  safeParseRows,
  buildH4UpstreamCandidates,
  classifyH48SyncStatus,
} from './h4RecoverableModel'

export type {
  H4FairValueDisposal,
  H4WaccParams,
  H4DcfAssumptions,
  H4DcfCashFlowRow,
  H4SensitivityRow,
  H4RecoverableSourceKind,
  H4RecoverableGroup,
  H4UpstreamCandidate,
  H48SyncCheck,
} from './h4RecoverableModel'
export {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  safeParseRows,
  buildH4UpstreamCandidates,
  classifyH48SyncStatus,
} from './h4RecoverableModel'

// ─── Response keys（持久化） ───────────────────────────────────────────────────

const GROUPS_KEY = 'H4-8-groups'
const ACTIVE_GROUP_KEY = 'H4-8-active-group'
const DCF_KEY = 'H4-8-dcf-assumptions'
const CASHFLOWS_KEY = 'H4-8-cashflows'
const FAIRVALUE_KEY = 'H4-8-fair-value'
const WACC_KEY = 'H4-8-wacc-params'
const REC_NOTE_KEY = 'H4-8-note'
const REC_CONCLUSION_KEY = 'H4-8-conclusion'
const H47_CALC_KEY = 'H4-7-calc-rows'
const H42_ROWS_KEY = 'H4-2-rows'
const H46_ROWS_KEY = 'H4-6-rows'

const LEGACY_DISCOUNT_KEY = 'H4-8-discount-rate'
const LEGACY_FORECAST_KEY = 'H4-8-forecast-years'
const LEGACY_DCF_KEY = 'H4-8-dcf-value'
const LEGACY_TV_KEY = 'H4-8-terminal-value'
const LEGACY_TOTAL_REC_KEY = 'H4-8-total-recoverable'
const LEGACY_BOOK_KEY = 'H4-8-book-value'

// ─── Internal helpers ─────────────────────────────────────────────────────────

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _newGroupId(): string {
  return `mat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _newRowId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _defaultFv(name = ''): H4FairValueDisposal {
  return {
    materialName: name,
    salesAgreementPrice: 0,
    salesAgreementNote: '',
    activeMarketPrice: 0,
    activeMarketNote: '',
    estimatedPrice: 0,
    estimatedNote: '',
    legalFees: 0,
    relatedTaxes: 0,
    transportCosts: 0,
    directCosts: 0,
    otherCosts: 0,
    auditNote: '',
  }
}

function _defaultWacc(): H4WaccParams {
  return {
    taxRate: 25,
    totalDebt: 0,
    totalEquity: 0,
    costOfDebt: 5,
    riskFreeRate: 2.5,
    beta: 1,
    marketReturn: 10,
  }
}

function _defaultAssumptions(): H4DcfAssumptions {
  return {
    discountRate: 10,
    forecastYears: 5,
    growthRate: 0,
    disposalCostRate: 0,
    bookValue: 0,
    materialName: '',
    growthRateBasis: '',
    industryGrowthRate: 0,
    marketGrowthRate: 0,
    countryGrowthRate: 0,
    usePreTaxRate: true,
  }
}

function _defaultGroup(name = '物资组-1'): H4RecoverableGroup {
  const assumptions = _defaultAssumptions()
  assumptions.materialName = name
  return {
    groupId: _newGroupId(),
    name,
    bookValue: 0,
    source: 'manual',
    bookValuePending: false,
    assumptions,
    waccParams: _defaultWacc(),
    fvDisposal: _defaultFv(name),
    cashFlows: [1, 2, 3, 4, 5].map(year => ({ year, revenue: 0, cost: 0 })),
    note: '',
    conclusion: '',
  }
}

function _emptyH47Row(partial: Partial<H4ImpairmentCalcRow> = {}): H4ImpairmentCalcRow {
  const row: H4ImpairmentCalcRow = {
    rowId: partial.rowId ?? _newRowId('h47'),
    category: partial.category ?? '',
    name: partial.name ?? '',
    hasSign: partial.hasSign === '是' || partial.hasSign === '否' ? partial.hasSign : '',
    signDesc: partial.signDesc ?? '',
    bookValue: _num(partial.bookValue),
    fairValueNet: _num(partial.fairValueNet),
    pvCashFlows: _num(partial.pvCashFlows),
    recoverableAmount: _num(partial.recoverableAmount),
    requiredProvision: 0,
    bookedProvision: _num(partial.bookedProvision),
    periodAdjustment: 0,
    wpIndex: partial.wpIndex ?? '',
    remark: partial.remark ?? '',
    sourceDetailRowId: partial.sourceDetailRowId,
  }
  recalcH4ImpairmentCalcRow(row)
  return row
}

function _mapH47Row(raw: any): H4ImpairmentCalcRow {
  return _emptyH47Row({
    rowId: raw.rowId,
    category: raw.category ?? '',
    name: raw.name ?? raw.materialName ?? '',
    hasSign: raw.hasSign === '是' || raw.hasSign === '否' ? raw.hasSign : '',
    signDesc: raw.signDesc ?? '',
    bookValue: raw.bookValue,
    fairValueNet: raw.fairValueNet ?? raw.fairValueLessDisposal,
    pvCashFlows: raw.pvCashFlows ?? raw.dcfValue,
    recoverableAmount: raw.recoverableAmount,
    bookedProvision: raw.bookedProvision ?? raw.alreadyProvided,
    wpIndex: raw.wpIndex ?? raw.indexRef ?? '',
    remark: raw.remark ?? '',
    sourceDetailRowId: raw.sourceDetailRowId,
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Recoverable(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>> | ComputedRef<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const assumptions = ref<H4DcfAssumptions>(_defaultAssumptions())
  const cashFlowRows = ref<H4DcfCashFlowRow[]>([])
  const fvDisposal = ref<H4FairValueDisposal>(_defaultFv())
  const waccParams = ref<H4WaccParams>(_defaultWacc())
  const recoverableNote = ref('')
  const recoverableConclusion = ref('')
  const groups = ref<H4RecoverableGroup[]>([_defaultGroup()])
  const activeGroupId = ref(groups.value[0].groupId)
  const h47CalcRows = ref<H4ImpairmentCalcRow[]>([])

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (raw == null || raw === '') return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(String(raw)) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return String(item?.remark ?? item?.conclusion ?? '')
  }

  function _effectiveRatePct(): number {
    const ke = calcCostOfEquity(
      waccParams.value.riskFreeRate,
      waccParams.value.beta,
      waccParams.value.marketReturn,
    )
    const waccAt = calcWaccAfterTax(
      waccParams.value.totalDebt,
      waccParams.value.totalEquity,
      ke,
      waccParams.value.costOfDebt,
      waccParams.value.taxRate,
    )
    if (waccAt > 0) {
      return assumptions.value.usePreTaxRate
        ? calcPreTaxDiscountRate(waccAt, waccParams.value.taxRate)
        : waccAt
    }
    return assumptions.value.discountRate || 0
  }

  function _recalcCashFlowRow(row: H4DcfCashFlowRow): void {
    const r = _effectiveRatePct() / 100
    row.netCashFlow = row.revenue - row.cost
    row.discountFactor = r > -1 ? 1 / Math.pow(1 + r, row.year) : 0
    row.presentValue = row.netCashFlow * row.discountFactor
  }

  function _recalcAllCashFlows(): void {
    for (const row of cashFlowRows.value) _recalcCashFlowRow(row)
  }

  function _syncCashFlowRows(): void {
    const years = Math.max(1, Math.min(20, Math.round(assumptions.value.forecastYears || 1)))
    const existing = cashFlowRows.value
    const next: H4DcfCashFlowRow[] = []
    for (let y = 1; y <= years; y++) {
      const prev = existing.find(c => c.year === y)
      const row: H4DcfCashFlowRow = prev
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

  function _snapshotActiveToGroup(g: H4RecoverableGroup): void {
    g.name = assumptions.value.materialName || g.name
    g.bookValue = assumptions.value.bookValue
    g.assumptions = { ...assumptions.value }
    g.waccParams = { ...waccParams.value }
    g.fvDisposal = { ...fvDisposal.value }
    g.cashFlows = cashFlowRows.value.map(c => ({
      year: c.year, revenue: c.revenue, cost: c.cost,
    }))
    g.note = recoverableNote.value
    g.conclusion = recoverableConclusion.value
  }

  function _loadGroupToActive(g: H4RecoverableGroup): void {
    assumptions.value = {
      ..._defaultAssumptions(),
      ...g.assumptions,
      materialName: g.name || g.assumptions.materialName,
      bookValue: g.bookValue || g.assumptions.bookValue,
    }
    waccParams.value = { ..._defaultWacc(), ...g.waccParams }
    fvDisposal.value = { ..._defaultFv(g.name), ...g.fvDisposal, materialName: g.name }
    cashFlowRows.value = (g.cashFlows?.length ? g.cashFlows : [1, 2, 3, 4, 5].map(year => ({ year, revenue: 0, cost: 0 })))
      .map((c, i) => {
        const row: H4DcfCashFlowRow = {
          rowId: `cf-${c.year || i + 1}`,
          year: c.year || i + 1,
          revenue: _num(c.revenue),
          cost: _num(c.cost),
          netCashFlow: 0,
          discountFactor: 0,
          presentValue: 0,
        }
        _recalcCashFlowRow(row)
        return row
      })
    _syncCashFlowRows()
    recoverableNote.value = g.note || ''
    recoverableConclusion.value = g.conclusion || ''
  }

  function _persistCashFlows(): void {
    options.onSave?.(CASHFLOWS_KEY, cashFlowRows.value.map(c => ({
      rowId: c.rowId, year: c.year, revenue: c.revenue, cost: c.cost,
    })))
  }

  function _persistFv(): void {
    options.onSave?.(FAIRVALUE_KEY, { ...fvDisposal.value })
  }

  function _persistLegacySummary(): void {
    options.onSave?.(LEGACY_DISCOUNT_KEY, effectiveDiscountRate.value)
    options.onSave?.(LEGACY_FORECAST_KEY, assumptions.value.forecastYears)
    options.onSave?.(LEGACY_DCF_KEY, totalPV.value)
    options.onSave?.(LEGACY_TV_KEY, tvPresent.value)
    options.onSave?.(LEGACY_TOTAL_REC_KEY, recoverableAmount.value)
    options.onSave?.(LEGACY_BOOK_KEY, assumptions.value.bookValue)
  }

  function _persistH47Calc(): void {
    const payload = h47CalcRows.value.map(r => ({
      rowId: r.rowId,
      category: r.category,
      name: r.name,
      hasSign: r.hasSign,
      signDesc: r.signDesc,
      bookValue: r.bookValue,
      fairValueNet: r.fairValueNet,
      pvCashFlows: r.pvCashFlows,
      recoverableAmount: r.recoverableAmount,
      requiredProvision: r.requiredProvision,
      bookedProvision: r.bookedProvision,
      periodAdjustment: r.periodAdjustment,
      wpIndex: r.wpIndex,
      remark: r.remark,
      sourceDetailRowId: r.sourceDetailRowId,
    }))
    options.onSave?.(H47_CALC_KEY, payload)
  }

  function _persistActiveGroup(): void {
    const g = groups.value.find(x => x.groupId === activeGroupId.value)
    if (!g) return
    _snapshotActiveToGroup(g)
    options.onSave?.(GROUPS_KEY, groups.value.map(x => ({ ...x })))
    options.onSave?.(ACTIVE_GROUP_KEY, activeGroupId.value)
    options.onSave?.(DCF_KEY, { ...assumptions.value })
    options.onSave?.(WACC_KEY, { ...waccParams.value })
    _persistFv()
    _persistCashFlows()
    options.onSave?.(REC_NOTE_KEY, recoverableNote.value)
    options.onSave?.(REC_CONCLUSION_KEY, recoverableConclusion.value)
    _persistLegacySummary()
  }

  function _groupResult(g: H4RecoverableGroup): {
    fairValueNet: number
    pvCashFlows: number
    recoverableAmount: number
  } {
    const fv = Math.max(resolveFairValue(g.fvDisposal).value - calcDisposalTotal(g.fvDisposal), 0)
    const ke = calcCostOfEquity(g.waccParams.riskFreeRate, g.waccParams.beta, g.waccParams.marketReturn)
    const waccAt = calcWaccAfterTax(
      g.waccParams.totalDebt, g.waccParams.totalEquity, ke, g.waccParams.costOfDebt, g.waccParams.taxRate,
    )
    let ratePct = g.assumptions.discountRate || 0
    if (waccAt > 0) {
      ratePct = g.assumptions.usePreTaxRate !== false
        ? calcPreTaxDiscountRate(waccAt, g.waccParams.taxRate)
        : waccAt
    }
    const r = ratePct / 100
    const growth = (g.assumptions.growthRate || 0) / 100
    const cfs = g.cashFlows || []
    let pv = 0
    for (const c of cfs) {
      const net = _num(c.revenue) - _num(c.cost)
      const year = _num(c.year) || 1
      if (r > -1) pv += net / Math.pow(1 + r, year)
    }
    let tvDisc = 0
    if (cfs.length > 0 && r > 0 && r > growth) {
      const last = cfs[cfs.length - 1]
      const lastNet = _num(last.revenue) - _num(last.cost)
      const tv = (lastNet * (1 + growth)) / (r - growth)
      tvDisc = tv / Math.pow(1 + r, cfs.length)
    }
    const totalDcf = pv + tvDisc
    return {
      fairValueNet: fv,
      pvCashFlows: totalDcf,
      recoverableAmount: calcRecoverableAmount(fv, totalDcf),
    }
  }

  function initFromAllResponses(): void {
    const calcRaw = _getJson(H47_CALC_KEY)
    h47CalcRows.value = Array.isArray(calcRaw) ? calcRaw.map(_mapH47Row) : []

    const groupsRaw = _getJson(GROUPS_KEY)
    if (Array.isArray(groupsRaw) && groupsRaw.length > 0) {
      groups.value = groupsRaw.map((g: any) => {
        const base = _defaultGroup(String(g.name || '物资组'))
        const rawAssumptions = g.assumptions || {}
        const mappedAssumptions = {
          ..._defaultAssumptions(),
          ...rawAssumptions,
          materialName: String(rawAssumptions.materialName ?? rawAssumptions.projectName ?? g.name ?? ''),
        }
        return {
          ...base,
          ...g,
          groupId: g.groupId || _newGroupId(),
          assumptions: mappedAssumptions,
          waccParams: { ..._defaultWacc(), ...(g.waccParams || {}) },
          fvDisposal: {
            ..._defaultFv(g.name),
            ...(g.fvDisposal || {}),
            materialName: String(g.fvDisposal?.materialName ?? g.fvDisposal?.projectName ?? g.name ?? ''),
          },
          cashFlows: Array.isArray(g.cashFlows) && g.cashFlows.length
            ? g.cashFlows
            : base.cashFlows,
          bookValuePending: Boolean(g.bookValuePending),
          source: (['manual', 'H4-7', 'H4-2', 'H4-6'].includes(g.source) ? g.source : 'manual') as H4RecoverableSourceKind,
        } as H4RecoverableGroup
      })
    } else {
      const migrated = _defaultGroup('物资组-1')
      const dcf = _getJson(DCF_KEY)
      if (dcf && typeof dcf === 'object') {
        migrated.assumptions = {
          ..._defaultAssumptions(),
          discountRate: _num(dcf.discountRate) || 10,
          forecastYears: _num(dcf.forecastYears) || 5,
          growthRate: dcf.growthRate != null ? _num(dcf.growthRate) : 0,
          disposalCostRate: _num(dcf.disposalCostRate),
          bookValue: _num(dcf.bookValue),
          materialName: String(dcf.materialName ?? dcf.projectName ?? ''),
          growthRateBasis: String(dcf.growthRateBasis ?? ''),
          industryGrowthRate: _num(dcf.industryGrowthRate),
          marketGrowthRate: _num(dcf.marketGrowthRate),
          countryGrowthRate: _num(dcf.countryGrowthRate),
          usePreTaxRate: dcf.usePreTaxRate !== false,
        }
        migrated.name = migrated.assumptions.materialName || migrated.name
        migrated.bookValue = migrated.assumptions.bookValue
      }
      const fvRaw = _getJson(FAIRVALUE_KEY)
      if (fvRaw != null && typeof fvRaw === 'object' && ('salesAgreementPrice' in fvRaw || 'estimatedPrice' in fvRaw || 'legalFees' in fvRaw)) {
        migrated.fvDisposal = { ..._defaultFv(migrated.name), ...fvRaw }
      } else if (fvRaw != null && typeof fvRaw === 'object' && 'value' in fvRaw) {
        migrated.fvDisposal = { ..._defaultFv(migrated.name), estimatedPrice: _num((fvRaw as any).value) }
      } else if (typeof fvRaw === 'number') {
        migrated.fvDisposal = { ..._defaultFv(migrated.name), estimatedPrice: fvRaw }
      }
      const waccRaw = _getJson(WACC_KEY)
      if (waccRaw && typeof waccRaw === 'object') {
        migrated.waccParams = { ..._defaultWacc(), ...waccRaw }
      }
      const cfs = _getJson(CASHFLOWS_KEY)
      if (Array.isArray(cfs) && cfs.length > 0) {
        migrated.cashFlows = cfs.map((c: any, i: number) => ({
          year: _num(c.year) || (i + 1),
          revenue: _num(c.revenue),
          cost: _num(c.cost),
        }))
      }
      migrated.note = _getString(REC_NOTE_KEY)
      migrated.conclusion = _getString(REC_CONCLUSION_KEY)
      groups.value = [migrated]
    }

    const activeParsed = _getJson(ACTIVE_GROUP_KEY)
    const activeId = typeof activeParsed === 'string'
      ? activeParsed
      : (_getString(ACTIVE_GROUP_KEY) || '')
    if (activeId && groups.value.some(g => g.groupId === activeId)) {
      activeGroupId.value = activeId
    } else {
      activeGroupId.value = groups.value[0].groupId
    }
    const active = groups.value.find(g => g.groupId === activeGroupId.value) || groups.value[0]
    _loadGroupToActive(active)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const fairValueResolved = computed(() => resolveFairValue(fvDisposal.value))
  const disposalTotal = computed(() => calcDisposalTotal(fvDisposal.value))
  const fairValueLessDisposal = computed(() =>
    Math.max(fairValueResolved.value.value - disposalTotal.value, 0),
  )

  const costOfEquity = computed(() =>
    calcCostOfEquity(waccParams.value.riskFreeRate, waccParams.value.beta, waccParams.value.marketReturn),
  )

  const waccAfterTax = computed(() =>
    calcWaccAfterTax(
      waccParams.value.totalDebt,
      waccParams.value.totalEquity,
      costOfEquity.value,
      waccParams.value.costOfDebt,
      waccParams.value.taxRate,
    ),
  )

  const preTaxDiscountRate = computed(() =>
    calcPreTaxDiscountRate(waccAfterTax.value, waccParams.value.taxRate),
  )

  const effectiveDiscountRate = computed(() => _effectiveRatePct())

  const rateInvalid = computed(() => {
    const r = effectiveDiscountRate.value / 100
    const g = assumptions.value.growthRate / 100
    return r <= 0 || r <= g
  })

  const growthWarnings = computed(() => {
    const msgs: string[] = []
    const g = assumptions.value.growthRate
    const industry = assumptions.value.industryGrowthRate
    const market = assumptions.value.marketGrowthRate
    const country = assumptions.value.countryGrowthRate
    if (g > 0 && !assumptions.value.growthRateBasis.trim()) {
      msgs.push('永续增长率大于0，请填写增长率确定依据（准则提示：通常应为0或负，除非有充分证据）')
    }
    if (industry > 0 && g > industry) {
      msgs.push(`永续增长率(${g}%)超过行业长期平均增长率(${industry}%)`)
    }
    if (market > 0 && g > market) {
      msgs.push(`永续增长率(${g}%)超过市场长期平均增长率(${market}%)`)
    }
    if (country > 0 && g > country) {
      msgs.push(`永续增长率(${g}%)超过国家/地区长期平均增长率(${country}%)`)
    }
    return msgs
  })

  const pvTotal: ComputedRef<number> = computed(() =>
    cashFlowRows.value.reduce((s, r) => s + r.presentValue, 0),
  )

  const tvPresent: ComputedRef<number> = computed(() => {
    if (rateInvalid.value) return 0
    const r = effectiveDiscountRate.value / 100
    const g = assumptions.value.growthRate / 100
    const n = cashFlowRows.value.length
    if (n === 0) return 0
    const lastNetCF = cashFlowRows.value[n - 1]?.netCashFlow ?? 0
    const tv = (lastNetCF * (1 + g)) / (r - g)
    return tv / Math.pow(1 + r, n)
  })

  const terminalValueUndiscounted = computed(() => {
    if (rateInvalid.value) return 0
    const r = effectiveDiscountRate.value / 100
    const g = assumptions.value.growthRate / 100
    const n = cashFlowRows.value.length
    if (n === 0) return 0
    const lastNetCF = cashFlowRows.value[n - 1]?.netCashFlow ?? 0
    return (lastNetCF * (1 + g)) / (r - g)
  })

  const totalPV: ComputedRef<number> = computed(() => pvTotal.value + tvPresent.value)

  const recoverableAmount: ComputedRef<number> = computed(() =>
    calcRecoverableAmount(fairValueLessDisposal.value, totalPV.value),
  )

  const recoverableSource = computed(() => {
    if (fairValueLessDisposal.value >= totalPV.value && fairValueLessDisposal.value > 0) {
      return '公允净额'
    }
    if (totalPV.value > 0) return '预计未来现金流量现值'
    return '未测算'
  })

  const impliedImpairment = computed(() =>
    Math.max(assumptions.value.bookValue - recoverableAmount.value, 0),
  )

  const activeGroup = computed(() =>
    groups.value.find(g => g.groupId === activeGroupId.value) || groups.value[0],
  )

  const upstreamCandidates = computed((): H4UpstreamCandidate[] => {
    const map = options.allResponses.value
    const h47 = h47CalcRows.value
    const h42 = safeParseRows(map.get(H42_ROWS_KEY)?.remark ?? map.get(H42_ROWS_KEY)?.conclusion)
    const h46 = safeParseRows(map.get(H46_ROWS_KEY)?.remark ?? map.get(H46_ROWS_KEY)?.conclusion)
    return buildH4UpstreamCandidates({ h47Rows: h47, h42Rows: h42, h46Rows: h46 })
  })

  const syncChecks = computed((): H48SyncCheck[] => {
    const byName = new Map<string, H4RecoverableGroup>()
    for (const g of groups.value) {
      const n = (g.name || '').trim()
      if (n) byName.set(n, g)
    }
    const activeName = assumptions.value.materialName.trim()
    if (activeName) {
      const live = activeGroup.value
      if (live) {
        byName.set(activeName, {
          ...live,
          name: activeName,
          bookValue: assumptions.value.bookValue,
          assumptions: { ...assumptions.value },
          waccParams: { ...waccParams.value },
          fvDisposal: { ...fvDisposal.value },
          cashFlows: cashFlowRows.value.map(c => ({ year: c.year, revenue: c.revenue, cost: c.cost })),
        })
      }
    }

    return h47CalcRows.value.map((row) => {
      const name = row.name.trim() || '未命名'
      const g = byName.get(name) || null
      const h48 = g ? _groupResult(g) : null
      const { status, message } = classifyH48SyncStatus(
        {
          fairValueNet: row.fairValueNet,
          pvCashFlows: row.pvCashFlows,
          recoverableAmount: row.recoverableAmount,
          hasSign: row.hasSign,
        },
        h48,
      )
      return {
        name,
        h7Recoverable: row.recoverableAmount,
        h8Recoverable: h48?.recoverableAmount ?? 0,
        status,
        message,
      }
    })
  })

  const staleSyncCount = computed(() =>
    syncChecks.value.filter(c => c.status === 'stale' || c.status === 'missing-h8').length,
  )

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

  const sensitivityCols: ComputedRef<string[]> = computed(() => {
    const baseG = assumptions.value.growthRate
    return [-1, -0.5, 0, 0.5, 1].map(step => (baseG + step).toFixed(1))
  })

  const sensitivityMatrix: ComputedRef<H4SensitivityRow[]> = computed(() => {
    const baseR = effectiveDiscountRate.value
    const cols = sensitivityCols.value
    return [-2, -1, 0, 1, 2].map(rStep => {
      const rate = baseR + rStep
      const row: H4SensitivityRow = { label: `r=${rate.toFixed(1)}%` }
      for (const col of cols) {
        const dcf = _pvAt(rate, parseFloat(col))
        row[`g_${col}`] = Math.max(fairValueLessDisposal.value, dcf)
      }
      return row
    })
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateAssumption(field: string, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'fairValueLessDisposal') {
      fvDisposal.value.estimatedPrice = _num(value)
      _persistActiveGroup()
      return
    }
    if (field in assumptions.value) {
      if (field === 'materialName' || field === 'growthRateBasis') {
        ;(assumptions.value as any)[field] = String(value ?? '')
      } else if (field === 'usePreTaxRate') {
        assumptions.value.usePreTaxRate = Boolean(value)
      } else {
        ;(assumptions.value as any)[field] = _num(value)
      }
      if (field === 'forecastYears') {
        _syncCashFlowRows()
      } else if (field === 'discountRate' || field === 'usePreTaxRate') {
        _recalcAllCashFlows()
      }
      if (field === 'materialName') {
        fvDisposal.value.materialName = String(value ?? '')
        const g = groups.value.find(x => x.groupId === activeGroupId.value)
        if (g) g.name = String(value ?? '')
      }
      if (field === 'bookValue') {
        const g = groups.value.find(x => x.groupId === activeGroupId.value)
        if (g) {
          g.bookValue = _num(value)
          g.bookValuePending = false
        }
      }
      _persistActiveGroup()
    }
  }

  function updateFvDisposal(partial: Partial<H4FairValueDisposal>): void {
    if (options.isReadonly.value) return
    Object.assign(fvDisposal.value, partial)
    _persistActiveGroup()
  }

  function updateWaccParams(partial: Partial<H4WaccParams>): void {
    if (options.isReadonly.value) return
    Object.assign(waccParams.value, partial)
    _recalcAllCashFlows()
    _persistActiveGroup()
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
    _persistActiveGroup()
  }

  function setActiveGroup(groupId: string): void {
    if (groupId === activeGroupId.value) return
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)
    const next = groups.value.find(g => g.groupId === groupId)
    if (!next) return
    activeGroupId.value = groupId
    _loadGroupToActive(next)
    _persistActiveGroup()
  }

  function addGroup(name?: string): string {
    if (options.isReadonly.value) return activeGroupId.value
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)
    const g = _defaultGroup(name || `物资组-${groups.value.length + 1}`)
    groups.value.push(g)
    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()
    return g.groupId
  }

  function removeActiveGroup(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    if (groups.value.length <= 1) return { ok: false, message: '至少保留一个物资组' }
    const idx = groups.value.findIndex(g => g.groupId === activeGroupId.value)
    if (idx < 0) return { ok: false, message: '未找到当前组' }
    groups.value.splice(idx, 1)
    activeGroupId.value = groups.value[Math.max(0, idx - 1)].groupId
    _loadGroupToActive(groups.value.find(g => g.groupId === activeGroupId.value)!)
    _persistActiveGroup()
    return { ok: true, message: '已删除当前物资组' }
  }

  function importUpstreamCandidate(key: string): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    const cand = upstreamCandidates.value.find(c => c.key === key)
    if (!cand) return { ok: false, message: '未找到候选物资（上游数据可能尚未就绪）' }

    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)

    let g = groups.value.find(x => x.name.trim() === cand.name)
    if (!g) {
      g = _defaultGroup(cand.name)
      g.source = cand.source
      g.sourceRowId = cand.sourceRowId
      groups.value.push(g)
    }
    g.name = cand.name
    g.source = cand.source
    g.sourceRowId = cand.sourceRowId
    g.bookValue = cand.bookValue
    g.bookValuePending = !cand.bookValueReady
    g.assumptions.materialName = cand.name
    g.assumptions.bookValue = cand.bookValue
    g.fvDisposal.materialName = cand.name

    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()

    const pendingTip = g.bookValuePending
      ? '；账面价值待补录（建议从 H4-2/H4-7 补齐）'
      : ''
    return { ok: true, message: `已载入「${cand.name}」（来源 ${cand.source}）${pendingTip}` }
  }

  function syncToH47(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式不可回写' }
    const name = assumptions.value.materialName.trim()
    let row = name
      ? h47CalcRows.value.find(r => r.name.trim() === name)
      : undefined
    if (!row && h47CalcRows.value.length === 1) {
      row = h47CalcRows.value[0]
    }
    if (!row) {
      if (!name && h47CalcRows.value.length === 0) {
        return { ok: false, message: '请先填写工程物资名称，或在 H4-7 新增测算行' }
      }
      row = _emptyH47Row({ name: name || '工程物资-1', hasSign: '是' })
      h47CalcRows.value.push(row)
    }
    row.fairValueNet = fairValueLessDisposal.value
    row.pvCashFlows = totalPV.value
    if (assumptions.value.bookValue > 0) {
      row.bookValue = assumptions.value.bookValue
    }
    if (name) row.name = name
    if (!row.hasSign) row.hasSign = '是'
    row.wpIndex = 'H4-8'
    row.remark = `由H4-8回写（③=${fairValueLessDisposal.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，④=${totalPV.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，取${recoverableSource.value}）`
    recalcH4ImpairmentCalcRow(row)
    _persistH47Calc()
    _persistActiveGroup()
    return {
      ok: true,
      message: `已回写「${row.name}」可收回金额 ${row.recoverableAmount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    }
  }

  function syncAllGroupsToH47(): { ok: boolean; synced: number; message: string } {
    if (options.isReadonly.value) return { ok: false, synced: 0, message: '只读模式' }
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)

    let synced = 0
    for (const g of groups.value) {
      const result = _groupResult(g)
      const name = (g.name || '').trim()
      if (!name && result.recoverableAmount <= 0) continue
      let row = name ? h47CalcRows.value.find(r => r.name.trim() === name) : undefined
      if (!row) {
        row = _emptyH47Row({ name: name || `物资组-${synced + 1}`, hasSign: '是' })
        h47CalcRows.value.push(row)
      }
      row.fairValueNet = result.fairValueNet
      row.pvCashFlows = result.pvCashFlows
      if (g.bookValue > 0) row.bookValue = g.bookValue
      if (name) row.name = name
      if (!row.hasSign) row.hasSign = '是'
      row.wpIndex = 'H4-8'
      row.remark = `由H4-8批量回写（组 ${g.groupId}）`
      recalcH4ImpairmentCalcRow(row)
      synced++
    }
    if (synced > 0) _persistH47Calc()
    _persistActiveGroup()
    return {
      ok: synced > 0,
      synced,
      message: synced > 0 ? `已批量回写 ${synced} 个物资组至 H4-7` : '没有可回写的物资组',
    }
  }

  function saveRecoverableNote(note: string): void {
    recoverableNote.value = note
    _persistActiveGroup()
  }

  function saveRecoverableConclusion(text: string): void {
    recoverableConclusion.value = text
    _persistActiveGroup()
  }

  return {
    groups,
    activeGroupId,
    activeGroup,
    assumptions,
    waccParams,
    fvDisposal,
    cashFlowRows,
    recoverableNote,
    recoverableConclusion,
    h47CalcRows,
    fairValueResolved,
    disposalTotal,
    fairValueLessDisposal,
    costOfEquity,
    waccAfterTax,
    preTaxDiscountRate,
    effectiveDiscountRate,
    rateInvalid,
    growthWarnings,
    pvTotal,
    terminalValueUndiscounted,
    tvPresent,
    totalPV,
    recoverableAmount,
    recoverableSource,
    impliedImpairment,
    upstreamCandidates,
    syncChecks,
    staleSyncCount,
    sensitivityCols,
    sensitivityMatrix,
    setActiveGroup,
    addGroup,
    removeActiveGroup,
    updateAssumption,
    updateCashFlowCell,
    updateFvDisposal,
    updateWaccParams,
    importUpstreamCandidate,
    syncToH47,
    syncAllGroupsToH47,
    saveRecoverableNote,
    saveRecoverableConclusion,
    initFromAllResponses,
  }
}

export default useH4Recoverable
