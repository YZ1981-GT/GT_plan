/**
 * useH8Recoverable — H8-11 使用权资产可收回金额 composable
 *
 * 对齐 Excel「使用权资产减值准备测试表-可收回金额」：
 *   一、公允净额 → 二、DCF/WACC → 三、MAX → 敏感性 → 回写 H8-10
 * 兼容旧版 H8-11-params（年金简化模型）迁移。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  H8FairValueDisposal,
  H8WaccParams,
  H8DcfAssumptions,
  H8DcfCashFlowRow,
  H8RecoverableGroup,
  H8UpstreamCandidate,
  H810SyncCheck,
  H8SensitivityRow,
} from './h8RecoverableModel'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveH8FairValue,
  calcH8DisposalTotal,
  calcRecoverableAmount,
  safeParseRows,
  buildH8UpstreamCandidates,
  classifyH810SyncStatus,
  checkForecastVsLeaseTerm,
  migrateLegacyH811Params,
  estimateRemainingLeaseYears,
} from './h8RecoverableModel'
import {
  upsertH810RowFromRecoverable,
  emptyH8ImpairmentRow,
  recomputeH8ImpairmentRow,
  type H8ImpairmentCalcRow,
} from './useH8Impairment'

export type {
  H8FairValueDisposal,
  H8WaccParams,
  H8DcfAssumptions,
  H8DcfCashFlowRow,
  H8RecoverableGroup,
  H8UpstreamCandidate,
  H810SyncCheck,
  H8SensitivityRow,
} from './h8RecoverableModel'
export {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveH8FairValue,
  calcH8DisposalTotal,
  calcRecoverableAmount,
  checkForecastVsLeaseTerm,
} from './h8RecoverableModel'

// ─── Response keys ───────────────────────────────────────────────────────────

const GROUPS_KEY = 'H8-11-groups'
const ACTIVE_GROUP_KEY = 'H8-11-active-group'
const DCF_KEY = 'H8-11-dcf-assumptions'
const CASHFLOWS_KEY = 'H8-11-cashflows'
const FAIRVALUE_KEY = 'H8-11-fair-value'
const WACC_KEY = 'H8-11-wacc-params'
const REC_NOTE_KEY = 'H8-recoverable-audit-note'
const REC_CONCLUSION_KEY = 'H8-recoverable-audit-conclusion'
const LEGACY_PARAMS_KEY = 'H8-11-params'
const H810_PARAMS_KEY = 'H8-10-params'
const H810_ROWS_KEY = 'H8-10-rows'
const H82_ROWS_KEY = 'H8-2-rows'

const LEGACY_TOTAL_REC_KEY = 'H8-11-total-recoverable'

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _newGroupId(): string {
  return `rou-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _defaultFv(name = ''): H8FairValueDisposal {
  return {
    assetName: name,
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

function _defaultWacc(): H8WaccParams {
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

function _defaultAssumptions(): H8DcfAssumptions {
  return {
    discountRate: 10,
    forecastYears: 5,
    growthRate: 0,
    bookValue: 0,
    assetName: '',
    growthRateBasis: '',
    industryGrowthRate: 0,
    marketGrowthRate: 0,
    countryGrowthRate: 0,
    usePreTaxRate: true,
    remainingLeaseYears: 0,
    incrementalBorrowingRate: 0,
  }
}

function _defaultGroup(name = '资产组-1'): H8RecoverableGroup {
  const assumptions = _defaultAssumptions()
  assumptions.assetName = name
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

export function useH8Recoverable(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>> | ComputedRef<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const assumptions = ref<H8DcfAssumptions>(_defaultAssumptions())
  const cashFlowRows = ref<H8DcfCashFlowRow[]>([])
  const fvDisposal = ref<H8FairValueDisposal>(_defaultFv())
  const waccParams = ref<H8WaccParams>(_defaultWacc())
  const recoverableNote = ref('')
  const recoverableConclusion = ref('')
  const groups = ref<H8RecoverableGroup[]>([_defaultGroup()])
  const activeGroupId = ref(groups.value[0].groupId)
  const h10Params = ref<Record<string, any>>({})

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
    // 优先增量借款利率，再手工折现率（避免 Excel #DIV/0!）
    if (assumptions.value.incrementalBorrowingRate > 0) {
      return assumptions.value.incrementalBorrowingRate
    }
    return assumptions.value.discountRate || 0
  }

  function _recalcCashFlowRow(row: H8DcfCashFlowRow): void {
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
    const next: H8DcfCashFlowRow[] = []
    for (let y = 1; y <= years; y++) {
      const prev = existing.find(c => c.year === y)
      const row: H8DcfCashFlowRow = prev
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

  function _snapshotActiveToGroup(g: H8RecoverableGroup): void {
    g.name = assumptions.value.assetName || g.name
    g.bookValue = assumptions.value.bookValue
    g.assumptions = { ...assumptions.value }
    g.waccParams = { ...waccParams.value }
    g.fvDisposal = { ...fvDisposal.value }
    g.cashFlows = cashFlowRows.value.map(c => ({
      year: c.year, revenue: c.revenue, cost: c.cost,
    }))
    g.note = recoverableNote.value
    g.conclusion = recoverableConclusion.value
    // 缓存供 H8-10 applyH811GroupsToRows 直接取数（不依赖下方 computed 初始化顺序）
    const r = _groupResult(g)
    g._fairValueNet = r.fairValueNet
    g._pvCashFlows = r.pvCashFlows
  }

  function _loadGroupToActive(g: H8RecoverableGroup): void {
    assumptions.value = {
      ..._defaultAssumptions(),
      ...g.assumptions,
      assetName: g.name || g.assumptions.assetName,
      bookValue: g.bookValue || g.assumptions.bookValue,
    }
    waccParams.value = { ..._defaultWacc(), ...g.waccParams }
    fvDisposal.value = { ..._defaultFv(g.name), ...g.fvDisposal, assetName: g.name }
    cashFlowRows.value = (g.cashFlows?.length
      ? g.cashFlows
      : [1, 2, 3, 4, 5].map(year => ({ year, revenue: 0, cost: 0 }))
    ).map((c, i) => {
      const row: H8DcfCashFlowRow = {
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

  function _persistActiveGroup(): void {
    const g = groups.value.find(x => x.groupId === activeGroupId.value)
    if (!g) return
    _snapshotActiveToGroup(g)
    options.onSave?.(GROUPS_KEY, groups.value.map(x => ({ ...x })))
    options.onSave?.(ACTIVE_GROUP_KEY, activeGroupId.value)
    options.onSave?.(DCF_KEY, { ...assumptions.value })
    options.onSave?.(WACC_KEY, { ...waccParams.value })
    options.onSave?.(FAIRVALUE_KEY, { ...fvDisposal.value })
    options.onSave?.(CASHFLOWS_KEY, cashFlowRows.value.map(c => ({
      rowId: c.rowId, year: c.year, revenue: c.revenue, cost: c.cost,
    })))
    options.onSave?.(REC_NOTE_KEY, recoverableNote.value)
    options.onSave?.(REC_CONCLUSION_KEY, recoverableConclusion.value)
    options.onSave?.(LEGACY_TOTAL_REC_KEY, recoverableAmount.value)
    // 兼容旧键：同步摘要参数
    options.onSave?.(LEGACY_PARAMS_KEY, JSON.stringify({
      discountRate: effectiveDiscountRate.value / 100,
      forecastYears: assumptions.value.forecastYears,
      annualCashFlow: cashFlowRows.value[0]?.netCashFlow ?? 0,
      terminalValue: terminalValueUndiscounted.value,
      bookValue: assumptions.value.bookValue,
      recoverableAmount: recoverableAmount.value,
      fairValueNet: fairValueLessDisposal.value,
      pvCashFlows: totalPV.value,
    }))
  }

  function _groupResult(g: H8RecoverableGroup): {
    fairValueNet: number
    pvCashFlows: number
    recoverableAmount: number
  } {
    const fv = Math.max(resolveH8FairValue(g.fvDisposal).value - calcH8DisposalTotal(g.fvDisposal), 0)
    const ke = calcCostOfEquity(g.waccParams.riskFreeRate, g.waccParams.beta, g.waccParams.marketReturn)
    const waccAt = calcWaccAfterTax(
      g.waccParams.totalDebt, g.waccParams.totalEquity, ke, g.waccParams.costOfDebt, g.waccParams.taxRate,
    )
    let ratePct = g.assumptions.discountRate || 0
    if (waccAt > 0) {
      ratePct = g.assumptions.usePreTaxRate !== false
        ? calcPreTaxDiscountRate(waccAt, g.waccParams.taxRate)
        : waccAt
    } else if (g.assumptions.incrementalBorrowingRate > 0) {
      ratePct = g.assumptions.incrementalBorrowingRate
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
    const h10Raw = _getJson(H810_PARAMS_KEY)
    h10Params.value = h10Raw && typeof h10Raw === 'object' ? { ...h10Raw } : {}

    const groupsRaw = _getJson(GROUPS_KEY)
    if (Array.isArray(groupsRaw) && groupsRaw.length > 0) {
      groups.value = groupsRaw.map((g: any) => {
        const base = _defaultGroup(String(g.name || '资产组'))
        const rawAssumptions = g.assumptions || {}
        return {
          ...base,
          ...g,
          groupId: g.groupId || _newGroupId(),
          assumptions: {
            ..._defaultAssumptions(),
            ...rawAssumptions,
            assetName: String(rawAssumptions.assetName ?? g.name ?? ''),
          },
          waccParams: { ..._defaultWacc(), ...(g.waccParams || {}) },
          fvDisposal: {
            ..._defaultFv(g.name),
            ...(g.fvDisposal || {}),
            assetName: String(g.fvDisposal?.assetName ?? g.name ?? ''),
          },
          cashFlows: Array.isArray(g.cashFlows) && g.cashFlows.length ? g.cashFlows : base.cashFlows,
          bookValuePending: Boolean(g.bookValuePending),
          source: (['manual', 'H8-10', 'H8-2'].includes(g.source) ? g.source : 'manual') as H8RecoverableGroup['source'],
        } as H8RecoverableGroup
      })
    } else {
      const migrated = _defaultGroup('资产组-1')
      const dcf = _getJson(DCF_KEY)
      if (dcf && typeof dcf === 'object') {
        migrated.assumptions = {
          ..._defaultAssumptions(),
          ...dcf,
          assetName: String(dcf.assetName ?? ''),
        }
        migrated.name = migrated.assumptions.assetName || migrated.name
        migrated.bookValue = migrated.assumptions.bookValue
      }

      // 旧版年金参数迁移
      const legacy = _getJson(LEGACY_PARAMS_KEY)
      if (legacy && typeof legacy === 'object') {
        const m = migrateLegacyH811Params(legacy)
        if (!dcf) {
          migrated.assumptions.discountRate = m.discountRate ?? 10
          migrated.assumptions.forecastYears = m.forecastYears ?? 5
        }
        if (m.bookValue) migrated.assumptions.bookValue = _num((legacy as any).bookValue)
        if (_num(m.annualCashFlow) > 0) {
          const n = migrated.assumptions.forecastYears || 5
          const cf = _num(m.annualCashFlow)
          migrated.cashFlows = Array.from({ length: n }, (_, i) => ({
            year: i + 1,
            revenue: cf,
            cost: 0,
          }))
          // 残值摊入最后一年流出的反向：作为第 n 年额外流入近似
          if (_num(m.terminalValue) > 0) {
            const last = migrated.cashFlows[migrated.cashFlows.length - 1]
            last.revenue += _num(m.terminalValue)
          }
        }
        if (_num((legacy as any).bookValue) > 0) {
          migrated.bookValue = _num((legacy as any).bookValue)
          migrated.assumptions.bookValue = migrated.bookValue
        }
      }

      const fvRaw = _getJson(FAIRVALUE_KEY)
      if (fvRaw && typeof fvRaw === 'object') {
        migrated.fvDisposal = { ..._defaultFv(migrated.name), ...fvRaw, assetName: migrated.name }
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

      // 从 H8-10 带入账面
      if (h10Params.value.bookValue && !migrated.bookValue) {
        migrated.bookValue = _num(h10Params.value.bookValue)
        migrated.assumptions.bookValue = migrated.bookValue
        migrated.source = 'H8-10'
      }

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

    // 审计说明兼容
    if (!recoverableNote.value) recoverableNote.value = _getString(REC_NOTE_KEY)
    if (!recoverableConclusion.value) recoverableConclusion.value = _getString(REC_CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const fairValueResolved = computed(() => resolveH8FairValue(fvDisposal.value))
  const disposalTotal = computed(() => calcH8DisposalTotal(fvDisposal.value))
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
    const leaseWarn = checkForecastVsLeaseTerm(
      assumptions.value.forecastYears,
      assumptions.value.remainingLeaseYears,
    )
    if (leaseWarn) msgs.push(leaseWarn)
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

  const upstreamCandidates = computed((): H8UpstreamCandidate[] => {
    const map = options.allResponses.value
    const h2 = safeParseRows(map.get(H82_ROWS_KEY)?.remark ?? map.get(H82_ROWS_KEY)?.conclusion)
    const h10Rows = safeParseRows(map.get(H810_ROWS_KEY)?.remark ?? map.get(H810_ROWS_KEY)?.conclusion)
    return buildH8UpstreamCandidates({
      h10Params: h10Params.value,
      h10Rows,
      h2Rows: h2,
    })
  })

  const syncChecks = computed((): H810SyncCheck[] => {
    const map = options.allResponses.value
    const h10Rows = safeParseRows(map.get(H810_ROWS_KEY)?.remark ?? map.get(H810_ROWS_KEY)?.conclusion)
    const checks: H810SyncCheck[] = []
    const covered = new Set<string>()

    const findGroup = (name: string, contractNo?: string) => {
      const cn = (contractNo || '').trim()
      if (cn) {
        const byC = groups.value.find(g => (g.contractNo || '').trim() === cn)
        if (byC) return byC
      }
      const n = name.trim()
      return groups.value.find(g =>
        (g.name || '').trim() === n
        || (g.assumptions?.assetName || '').trim() === n,
      )
    }

    for (const r of h10Rows) {
      const name = String(r?.assetName || r?.contractNo || '').trim()
      if (!name) continue
      const need = r.hasIndication === 'Y' || (Number(r.recoverableAmount) || 0) > 0
      if (!need) continue
      const g = findGroup(name, String(r.contractNo || ''))
      const live = g ? _groupResult(g) : null
      // 若为当前活动组，用实时计算更准
      const isActive = g && g.groupId === activeGroupId.value
      const h11Rec = isActive
        ? recoverableAmount.value
        : (live?.recoverableAmount ?? 0)
      const { status, message } = classifyH810SyncStatus(
        {
          recoverableAmount: Number(r.recoverableAmount) || 0,
          hasSign: r.hasIndication === 'Y' ? '是' : '否',
        },
        h11Rec > 0 ? { recoverableAmount: h11Rec } : null,
      )
      checks.push({
        name,
        h10Recoverable: Number(r.recoverableAmount) || 0,
        h11Recoverable: h11Rec,
        status,
        message,
      })
      covered.add(name)
      if (g?.groupId) covered.add(g.groupId)
    }

    // 无行级 H8-10 时回退摘要比对
    if (!checks.length) {
      const name = assumptions.value.assetName.trim() || '使用权资产（H8-10）'
      const h10Rec = _num(h10Params.value.recoverableAmount)
      const live = {
        recoverableAmount: recoverableAmount.value,
      }
      const hasSign = h10Params.value.impairmentSign && h10Params.value.impairmentSign !== '无'
        ? '是'
        : (h10Rec > 0 ? '是' : '否')
      const { status, message } = classifyH810SyncStatus(
        { recoverableAmount: h10Rec, hasSign },
        live.recoverableAmount > 0 ? live : null,
      )
      checks.push({
        name,
        h10Recoverable: h10Rec,
        h11Recoverable: live.recoverableAmount,
        status,
        message,
      })
    }

    return checks
  })

  const staleSyncCount = computed(() =>
    syncChecks.value.filter(c => c.status === 'stale' || c.status === 'missing-h11').length,
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

  const sensitivityMatrix: ComputedRef<H8SensitivityRow[]> = computed(() => {
    const baseR = effectiveDiscountRate.value
    const cols = sensitivityCols.value
    return [-2, -1, 0, 1, 2].map(rStep => {
      const rate = baseR + rStep
      const row: H8SensitivityRow = { label: `r=${rate.toFixed(1)}%` }
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
    if (!(field in assumptions.value)) return
    if (field === 'assetName' || field === 'growthRateBasis') {
      ;(assumptions.value as any)[field] = String(value ?? '')
    } else if (field === 'usePreTaxRate') {
      assumptions.value.usePreTaxRate = Boolean(value)
    } else {
      ;(assumptions.value as any)[field] = _num(value)
    }
    if (field === 'forecastYears') _syncCashFlowRows()
    else if (
      field === 'discountRate'
      || field === 'usePreTaxRate'
      || field === 'incrementalBorrowingRate'
    ) {
      _recalcAllCashFlows()
    }
    if (field === 'assetName') {
      fvDisposal.value.assetName = String(value ?? '')
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

  function updateContractNo(contractNo: string): void {
    if (options.isReadonly.value) return
    const g = groups.value.find(x => x.groupId === activeGroupId.value)
    if (!g) return
    g.contractNo = String(contractNo ?? '').trim()
    _persistActiveGroup()
  }

  function updateFvDisposal(partial: Partial<H8FairValueDisposal>): void {
    if (options.isReadonly.value) return
    Object.assign(fvDisposal.value, partial)
    _persistActiveGroup()
  }

  function updateWaccParams(partial: Partial<H8WaccParams>): void {
    if (options.isReadonly.value) return
    Object.assign(waccParams.value, partial)
    _recalcAllCashFlows()
    _persistActiveGroup()
  }

  function updateCashFlowCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = cashFlowRows.value.find(c => c.rowId === rowId)
    if (!row) return
    if (['netCashFlow', 'discountFactor', 'presentValue'].includes(field)) return
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
    const g = _defaultGroup(name || `资产组-${groups.value.length + 1}`)
    groups.value.push(g)
    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()
    return g.groupId
  }

  function removeActiveGroup(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    if (groups.value.length <= 1) return { ok: false, message: '至少保留一个资产组' }
    const idx = groups.value.findIndex(g => g.groupId === activeGroupId.value)
    if (idx < 0) return { ok: false, message: '未找到当前组' }
    groups.value.splice(idx, 1)
    activeGroupId.value = groups.value[Math.max(0, idx - 1)].groupId
    _loadGroupToActive(groups.value.find(g => g.groupId === activeGroupId.value)!)
    _persistActiveGroup()
    return { ok: true, message: '已删除当前资产组' }
  }

  function importUpstreamCandidate(key: string): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    const cand = upstreamCandidates.value.find(c => c.key === key)
    if (!cand) return { ok: false, message: '未找到上游候选（请先完成 H8-2 / H8-10）' }

    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)

    let g = groups.value.find(x =>
      (cand.contractNo && (x.contractNo || '').trim() === cand.contractNo)
      || x.name.trim() === cand.name,
    )
    if (!g) {
      g = _defaultGroup(cand.name)
      groups.value.push(g)
    }
    g.name = cand.name
    g.contractNo = cand.contractNo || g.contractNo || ''
    g.source = cand.source
    g.sourceRowId = cand.sourceRowId
    g.bookValue = cand.bookValue
    g.bookValuePending = !cand.bookValueReady
    g.assumptions.assetName = cand.name
    g.assumptions.bookValue = cand.bookValue
    if (cand.remainingLeaseYears && cand.remainingLeaseYears > 0) {
      g.assumptions.remainingLeaseYears = cand.remainingLeaseYears
      // 预测期默认不超过剩余租赁期与 5 年
      g.assumptions.forecastYears = Math.max(
        1,
        Math.min(5, Math.ceil(cand.remainingLeaseYears)),
      )
    }
    g.fvDisposal.assetName = cand.name

    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()
    return {
      ok: true,
      message: `已载入「${cand.name}」（来源 ${cand.source}）${g.bookValuePending ? '；账面待补录' : ''}${cand.remainingLeaseYears ? `；剩余租赁期 ${cand.remainingLeaseYears} 年` : ''}`,
    }
  }

  /**
   * 从 H8-10「有迹象」行批量建资产组（已存在则更新账面/合同号）
   */
  function seedGroupsFromH810Indications(): { ok: boolean; message: string; count: number } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式', count: 0 }
    const rows = _loadH810Rows().filter(r => r.hasIndication === 'Y')
    if (!rows.length) {
      return { ok: false, message: 'H8-10 暂无「有迹象」行，请先完成迹象评估', count: 0 }
    }
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)

    let added = 0
    let updated = 0
    for (const r of rows) {
      const name = (r.assetName || r.contractNo || '').trim()
      if (!name) continue
      let g = groups.value.find(x =>
        (r.contractNo && (x.contractNo || '').trim() === r.contractNo.trim())
        || (x.name || '').trim() === name
        || (x.sourceRowId && x.sourceRowId === r.rowId),
      )
      if (!g) {
        g = _defaultGroup(name)
        groups.value.push(g)
        added++
      } else {
        updated++
      }
      g.name = name
      g.contractNo = r.contractNo || g.contractNo || ''
      g.bookValue = r.bookValue || g.bookValue
      g.bookValuePending = !(r.bookValue > 0)
      g.source = 'H8-10'
      g.sourceRowId = r.rowId || g.sourceRowId
      g.assumptions.assetName = name
      g.assumptions.bookValue = g.bookValue
      g.fvDisposal.assetName = name
    }

    // 切到第一个新建/更新的有迹象组
    const first = groups.value.find(g =>
      rows.some(r =>
        (r.contractNo && g.contractNo === r.contractNo)
        || g.name === (r.assetName || r.contractNo),
      ),
    )
    if (first) {
      activeGroupId.value = first.groupId
      _loadGroupToActive(first)
    }
    _persistActiveGroup()
    return {
      ok: true,
      message: `已从 H8-10 有迹象行同步：新增 ${added}、更新 ${updated}`,
      count: added + updated,
    }
  }

  function applyIbrAsDiscountRate(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    const ibr = assumptions.value.incrementalBorrowingRate
    if (ibr <= 0) return { ok: false, message: '请先填写增量借款利率（可与 H8-6 一致）' }
    assumptions.value.discountRate = ibr
    _recalcAllCashFlows()
    _persistActiveGroup()
    return { ok: true, message: `已将手工折现率设为增量借款利率 ${ibr}%` }
  }

  function _loadH810Rows(): H8ImpairmentCalcRow[] {
    const raw = options.allResponses.value.get(H810_ROWS_KEY)
    const parsed = safeParseRows(raw?.remark ?? raw?.conclusion)
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map((r: any) => recomputeH8ImpairmentRow({ ...emptyH8ImpairmentRow(), ...r }))
    }
    return []
  }

  function _persistH810Rows(nextRows: H8ImpairmentCalcRow[]): void {
    options.onSave?.(H810_ROWS_KEY, JSON.stringify(nextRows))
  }

  function syncToH810(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式不可回写' }
    if (recoverableAmount.value <= 0) {
      return { ok: false, message: '可收回金额尚未测算，请先完成公允净额或 DCF' }
    }
    const assetName = assumptions.value.assetName || h10Params.value.assetName || activeGroup.value?.name || '使用权资产'
    const next = {
      ...h10Params.value,
      assetName,
      bookValue: assumptions.value.bookValue || h10Params.value.bookValue || 0,
      recoverableAmount: recoverableAmount.value,
      fairValueNet: fairValueLessDisposal.value,
      pvCashFlows: totalPV.value,
      recoverableSource: recoverableSource.value,
      impairmentSign: h10Params.value.impairmentSign || '其他',
    }
    h10Params.value = next
    options.onSave?.(H810_PARAMS_KEY, JSON.stringify(next))

    // 行级回写 H8-10-rows（与 H8TabImpairment 对齐）
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    const rows = upsertH810RowFromRecoverable(_loadH810Rows(), {
      assetName,
      bookValue: next.bookValue,
      fairValueNet: fairValueLessDisposal.value,
      pvCashFlows: totalPV.value,
      sourceRowId: cur?.sourceRowId,
    })
    _persistH810Rows(rows)

    _persistActiveGroup()
    return {
      ok: true,
      message: `已回写 H8-10 可收回金额 ${recoverableAmount.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}（取自${recoverableSource.value}）`,
    }
  }

  function syncAllGroupsToH810(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式不可回写' }
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)
    let synced = 0
    let totalRec = 0
    let totalBook = 0
    let totalFv = 0
    let totalPv = 0
    let rows = _loadH810Rows()
    for (const g of groups.value) {
      const r = _groupResult(g)
      g._fairValueNet = r.fairValueNet
      g._pvCashFlows = r.pvCashFlows
      if (r.recoverableAmount > 0) {
        synced++
        totalRec += r.recoverableAmount
        totalBook += g.bookValue || g.assumptions.bookValue || 0
        totalFv += r.fairValueNet
        totalPv += r.pvCashFlows
        rows = upsertH810RowFromRecoverable(rows, {
          assetName: g.name || g.assumptions.assetName || `资产组${synced}`,
          bookValue: g.bookValue || g.assumptions.bookValue || 0,
          fairValueNet: r.fairValueNet,
          pvCashFlows: r.pvCashFlows,
          sourceRowId: g.sourceRowId,
        })
      }
    }
    if (synced === 0) return { ok: false, message: '各资产组均未完成测算' }
    _persistH810Rows(rows)

    const useTotal = groups.value.length > 1
    const payload = {
      ...h10Params.value,
      assetName: useTotal
        ? `多资产组合计(${synced})`
        : (assumptions.value.assetName || groups.value[0].name),
      bookValue: useTotal ? totalBook : assumptions.value.bookValue,
      recoverableAmount: useTotal ? totalRec : recoverableAmount.value,
      fairValueNet: useTotal ? totalFv : fairValueLessDisposal.value,
      pvCashFlows: useTotal ? totalPv : totalPV.value,
      recoverableSource: useTotal ? '多组合计' : recoverableSource.value,
      impairmentSign: h10Params.value.impairmentSign || '其他',
    }
    h10Params.value = payload
    options.onSave?.(H810_PARAMS_KEY, JSON.stringify(payload))
    _persistActiveGroup()
    return { ok: true, message: `已回写 ${synced} 个资产组结果至 H8-10（行级+摘要）` }
  }

  function saveRecoverableNote(text: string): void {
    if (options.isReadonly.value) return
    recoverableNote.value = text
    _persistActiveGroup()
  }

  function saveRecoverableConclusion(text: string): void {
    if (options.isReadonly.value) return
    recoverableConclusion.value = text
    _persistActiveGroup()
  }

  function buildConclusionDraft(): string {
    const leaseWarn = checkForecastVsLeaseTerm(
      assumptions.value.forecastYears,
      assumptions.value.remainingLeaseYears,
    )
    const impair = impliedImpairment.value
    return [
      `经测算，使用权资产「${assumptions.value.assetName || activeGroup.value?.name || ''}」`,
      `可收回金额为 ${recoverableAmount.value.toFixed(2)} 元（取自${recoverableSource.value}：`,
      `公允净额 ${fairValueLessDisposal.value.toFixed(2)} / 使用价值 ${totalPV.value.toFixed(2)}）；`,
      `账面价值 ${assumptions.value.bookValue.toFixed(2)} 元，`,
      impair > 0.01
        ? `应计提减值 ${impair.toFixed(2)} 元，建议回写 H8-10 并切换 H8-8 含减值版本重算折旧；`
        : `可收回金额不低于账面价值，本期无需计提减值；`,
      leaseWarn ? `需关注：${leaseWarn}；` : '',
      growthWarnings.value.length ? `增长率/预测期提示 ${growthWarnings.value.length} 项已复核□；` : '',
      `减值一经确认不得转回（CAS8）。`,
    ].filter(Boolean).join('')
  }

  return {
    assumptions,
    cashFlowRows,
    fvDisposal,
    waccParams,
    recoverableNote,
    recoverableConclusion,
    groups,
    activeGroupId,
    activeGroup,
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
    tvPresent,
    terminalValueUndiscounted,
    totalPV,
    recoverableAmount,
    recoverableSource,
    impliedImpairment,
    upstreamCandidates,
    syncChecks,
    staleSyncCount,
    sensitivityCols,
    sensitivityMatrix,
    updateAssumption,
    updateContractNo,
    updateFvDisposal,
    updateWaccParams,
    updateCashFlowCell,
    setActiveGroup,
    addGroup,
    removeActiveGroup,
    importUpstreamCandidate,
    seedGroupsFromH810Indications,
    applyIbrAsDiscountRate,
    syncToH810,
    syncAllGroupsToH810,
    saveRecoverableNote,
    saveRecoverableConclusion,
    buildConclusionDraft,
  }
}

export default useH8Recoverable
