/**
 * useH2Impairment — H2-15/16 减值组 composable
 *
 * H2-15 减值迹象6项判断 + 减值测算表
 * H2-16 对齐 Excel「在建工程减值准备测试表-可收回金额」：
 *   一、公允净额（三层次公允 + 处置费用明细）
 *   二、预计未来现金流量现值（DCF + WACC/CAPM）
 *   三、可收回金额 = MAX(①,②) → 回写 H2-15
 *   四、敏感性矩阵
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Requirements: 12.1-12.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  isCleanImpairmentConclusion,
} from './h2ImpairmentGate'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H2-15 减值迹象行（CAS8 六项） */
export interface ImpairmentSignRow {
  rowId: string
  indicator: string
  exists: '是' | '否' | '不适用' | ''
  evidence: string
}

/**
 * H2-15 减值测算行（对齐 Excel「在建工程减值测算表」列结构）
 * ⑤=MAX(③,④)  ⑥=MAX(②−⑤,0)  ⑧=⑥−⑦
 */
export interface ImpairmentCalcRow {
  rowId: string
  name: string
  /** 是否存在减值迹象 */
  hasSign: '是' | '否' | ''
  /** ① 减值迹象描述 */
  signDesc: string
  /** ② 账面价值 */
  bookValue: number
  /** ③ 公允价值减去处置费用后的净额 */
  fairValueNet: number
  /** ④ 预计未来现金流量现值 */
  pvCashFlows: number
  /** ⑤ 可收回金额 = MAX(③,④) */
  recoverableAmount: number
  /** ⑥ 期末应计提减值准备（当⑤＜②） */
  requiredProvision: number
  /** ⑦ 期末账面已计提减值准备 */
  bookedProvision: number
  /** ⑧ 本期应补提（CAS8 长期资产不得转回，⑧＜0 时预警） */
  periodAdjustment: number
  /** @deprecated 兼容旧字段，等同 requiredProvision */
  impairmentAmount: number
  method: string
  wpIndex: string
  remark: string
}

/** 公允价值 − 处置费用（对齐 Excel 第一节） */
export interface FairValueDisposal {
  projectName: string
  /** 1.销售协议价格 */
  salesAgreementPrice: number
  salesAgreementNote: string
  /** 2.活跃市场价格 */
  activeMarketPrice: number
  activeMarketNote: string
  /** 3.估计价格（无活跃市场时的最佳信息） */
  estimatedPrice: number
  estimatedNote: string
  legalFees: number
  relatedTaxes: number
  transportCosts: number
  directCosts: number
  otherCosts: number
  auditNote: string
}

/** WACC / CAPM 参数 */
export interface WaccParams {
  taxRate: number
  totalDebt: number
  totalEquity: number
  costOfDebt: number
  riskFreeRate: number
  beta: number
  marketReturn: number
}

/** H2-16 DCF 关键假设 */
export interface DcfAssumptions {
  /** 手工折现率(%)，WACC 未填时兜底 */
  discountRate: number
  forecastYears: number
  growthRate: number
  /** @deprecated 已由处置费用明细替代，仅兼容旧数据 */
  disposalCostRate: number
  bookValue: number
  projectName: string
  growthRateBasis: string
  industryGrowthRate: number
  countryGrowthRate: number
  /** true=使用税前折现率(CAS8) */
  usePreTaxRate: boolean
}

/** H2-16 逐年现金流预测行 */
export interface DcfCashFlowRow {
  rowId: string
  year: number
  revenue: number
  cost: number
  netCashFlow: number
  discountFactor: number
  presentValue: number
}

export interface SensitivityRow {
  label: string
  [key: string]: number | string
}

/** H2-16 多工程测试组来源（上游底稿未齐时允许 bookValuePending） */
export type RecoverableSourceKind = 'manual' | 'H2-15' | 'H2-13' | 'H2-2'

export interface RecoverableGroup {
  groupId: string
  name: string
  bookValue: number
  source: RecoverableSourceKind
  sourceRowId?: string
  /** 上游（如 H2-13）暂无账面时为 true，不阻断测算 */
  bookValuePending: boolean
  assumptions: DcfAssumptions
  waccParams: WaccParams
  fvDisposal: FairValueDisposal
  cashFlows: Array<{ year: number; revenue: number; cost: number }>
  note: string
  conclusion: string
}

/** 上游可选工程（容错：解析失败返回空列表，不抛错） */
export interface UpstreamCandidate {
  key: string
  source: RecoverableSourceKind
  sourceRowId: string
  name: string
  bookValue: number
  bookValueReady: boolean
  hint: string
}

/** H2-15 ↔ H2-16 回写一致性 */
export interface H216SyncCheck {
  name: string
  h15FairValueNet: number
  h16FairValueNet: number
  h15Pv: number
  h16Pv: number
  h15Recoverable: number
  h16Recoverable: number
  status: 'synced' | 'stale' | 'missing-h16' | 'no-test'
  message: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNS_KEY = 'H2-15-impairment-signs'
const CALC_KEY = 'H2-15-test-rows'
const DCF_KEY = 'H2-16-dcf-assumptions'
const CASHFLOWS_KEY = 'H2-16-cashflows'
const FAIRVALUE_KEY = 'H2-16-fair-value'
const WACC_KEY = 'H2-16-wacc-params'
const GROUPS_KEY = 'H2-16-groups'
const ACTIVE_GROUP_KEY = 'H2-16-active-group'
const NOTE_KEY = 'H2-15-audit-note'
const CONCLUSION_KEY = 'H2-15-audit-conclusion'
const REC_NOTE_KEY = 'H2-16-audit-note'
const REC_CONCLUSION_KEY = 'H2-16-audit-conclusion'
const H21_ROWS_KEY = 'H2-1-rows'
const H22_ROWS_KEY = 'H2-2-rows'
const H23_ROWS_KEY = 'H2-3-rows'
/** H2-3 自动草稿标记（重复推送时先清理） */
export const H215_AJE_MARKER = 'H2-15-aje-auto'

const SYNC_TOLERANCE = 0.01

const DEFAULT_SIGN_INDICATORS: string[] = [
  '资产市价大幅下跌，明显高于因时间推移或正常使用而预计的下跌',
  '技术、市场、经济或法律环境发生重大不利变化',
  '市场利率或其他市场投资报酬率上升，影响资产可收回金额',
  '资产已经陈旧过时或实体损坏（如长期停工）',
  '资产的用途发生重大不利变化（如闲置、终止使用或计划提前处置）',
  '内部报告证据表明资产的经济绩效已经低于或将低于预期',
]

// ─── Pure helpers（导出供单测） ──────────────────────────────────────────────

export function calcCostOfEquity(rf: number, beta: number, rm: number): number {
  return rf + beta * (rm - rf)
}

export function calcWaccAfterTax(
  totalDebt: number,
  totalEquity: number,
  costOfEquity: number,
  costOfDebt: number,
  taxRate: number,
): number {
  const total = totalDebt + totalEquity
  if (total <= 0) return 0
  const t = taxRate / 100
  return (totalEquity / total) * costOfEquity + (totalDebt / total) * costOfDebt * (1 - t)
}

export function calcPreTaxDiscountRate(waccAfterTax: number, taxRate: number): number {
  const t = taxRate / 100
  if (t >= 1) return waccAfterTax
  return waccAfterTax / (1 - t)
}

export function resolveFairValue(fv: FairValueDisposal): { value: number; source: string } {
  if (fv.salesAgreementPrice > 0) return { value: fv.salesAgreementPrice, source: '销售协议价格' }
  if (fv.activeMarketPrice > 0) return { value: fv.activeMarketPrice, source: '活跃市场价格' }
  if (fv.estimatedPrice > 0) return { value: fv.estimatedPrice, source: '估计价格' }
  return { value: 0, source: '未确定' }
}

export function calcDisposalTotal(fv: FairValueDisposal): number {
  return (fv.legalFees || 0) + (fv.relatedTaxes || 0) + (fv.transportCosts || 0)
    + (fv.directCosts || 0) + (fv.otherCosts || 0)
}

/** 由 H2-15 ⑧本期补提生成借贷分录草稿（仅补提，不含冲回） */
export function buildImpairmentAjePair(opts: {
  projectName: string
  amount: number
  seqStart: number
}): Array<{
  rowId: string
  seq: number
  description: string
  category: '账项调整'
  entryType: 'AJE'
  reportItem: string
  accountCode: string
  accountName: string
  summary: string
  debit: number
  credit: number
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}> {
  const amt = Math.round(opts.amount * 100) / 100
  if (amt <= 0) return []
  const name = opts.projectName.trim() || '在建工程'
  const desc = `补提在建工程减值准备-${name}`
  const baseId = `h215-aje-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  return [
    {
      rowId: `${baseId}-dr`,
      seq: opts.seqStart,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '资产减值损失',
      accountCode: '6701',
      accountName: '资产减值损失',
      summary: desc,
      debit: amt,
      credit: 0,
      debitAmount: amt,
      creditAmount: 0,
      indexRef: 'H2-15',
      remark: H215_AJE_MARKER,
    },
    {
      rowId: `${baseId}-cr`,
      seq: opts.seqStart + 1,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '在建工程',
      accountCode: '1604',
      accountName: '在建工程减值准备',
      summary: desc,
      debit: 0,
      credit: amt,
      debitAmount: 0,
      creditAmount: amt,
      indexRef: 'H2-15',
      remark: H215_AJE_MARKER,
    },
  ]
}

function _defaultFv(name = ''): FairValueDisposal {
  return {
    projectName: name,
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

function _defaultWacc(): WaccParams {
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

function _defaultAssumptions(): DcfAssumptions {
  return {
    discountRate: 10,
    forecastYears: 5,
    growthRate: 0, // CAS：稳定期增长率通常为0或负，除非有充分依据
    disposalCostRate: 0,
    bookValue: 0,
    projectName: '',
    growthRateBasis: '',
    industryGrowthRate: 0,
    countryGrowthRate: 0,
    usePreTaxRate: true,
  }
}

function _newGroupId(): string {
  return `cgu-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _defaultGroup(name = '工程组-1'): RecoverableGroup {
  const assumptions = _defaultAssumptions()
  assumptions.projectName = name
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

/** 安全解析上游 JSON 数组；失败返回 []，不抛错（上游底稿未修好时的容错） */
export function safeParseRows(raw: unknown): any[] {
  if (raw == null) return []
  let data = raw
  if (typeof raw === 'string') {
    try { data = JSON.parse(raw) } catch { return [] }
  }
  return Array.isArray(data) ? data : []
}

export function buildUpstreamCandidates(opts: {
  h215Rows?: any[]
  h213Rows?: any[]
  h22Rows?: any[]
}): UpstreamCandidate[] {
  const out: UpstreamCandidate[] = []
  const seen = new Set<string>()

  for (const r of opts.h215Rows ?? []) {
    const name = String(r?.name ?? '').trim()
    if (!name) continue
    const key = `H2-15:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      key,
      source: 'H2-15',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: Number(r.bookValue) || 0,
      bookValueReady: Number(r.bookValue) > 0,
      hint: r.hasSign === '是' ? 'H2-15 测算（有迹象）' : 'H2-15 测算',
    })
  }

  // H2-2 账面净值：按名称补齐已有候选，或新增
  for (const r of opts.h22Rows ?? []) {
    const name = String(r?.name ?? '').trim()
    if (!name) continue
    const net = Number(r.netValue ?? r.cipEnd) || 0
    const existing = out.find(c => c.name === name)
    if (existing) {
      if (!existing.bookValueReady && net > 0) {
        existing.bookValue = net
        existing.bookValueReady = true
        existing.hint += '；账面已由 H2-2 补齐'
      }
      continue
    }
    const key = `H2-2:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      key,
      source: 'H2-2',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: net,
      bookValueReady: net > 0,
      hint: net > 0 ? 'H2-2 明细账面净值' : 'H2-2 明细（账面待核）',
    })
  }

  // H2-13 停工：优先取账面金额；仅提供名称线索时不覆盖已有账面
  for (const r of opts.h213Rows ?? []) {
    const stopped =
      r?.constructionStatus === '停工'
      || String(r?.stopDuration ?? '').trim() !== ''
      || String(r?.stopReason ?? '').trim() !== ''
      || r?.isStopped === '是'
      || r?.isStopped === true
    if (!stopped) continue
    const name = String(r?.projectName ?? r?.name ?? '').trim()
    if (!name) continue
    const existing = out.find(c => c.name === name)
    if (existing) {
      existing.hint += '；H2-13 标记停工'
      const maybeBook = Number(r.bookAmount ?? r.bookValue ?? r.carryingAmount) || 0
      if (maybeBook > 0 && !(existing.bookValue > 0)) {
        existing.bookValue = maybeBook
        existing.bookValueReady = true
        existing.hint += '；账面已由 H2-13 补齐'
      }
      continue
    }
    const key = `H2-13:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    const maybeBook = Number(r.bookAmount ?? r.bookValue ?? r.carryingAmount) || 0
    out.push({
      key,
      source: 'H2-13',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: maybeBook,
      bookValueReady: maybeBook > 0,
      hint: maybeBook > 0
        ? 'H2-13 停工（含账面金额）'
        : 'H2-13 停工；账面请从 H2-2/H2-15 补录',
    })
  }

  return out
}

export function classifySyncStatus(
  h15: { fairValueNet: number; pvCashFlows: number; recoverableAmount: number; hasSign: string },
  h16: { fairValueNet: number; pvCashFlows: number; recoverableAmount: number } | null,
): Pick<H216SyncCheck, 'status' | 'message'> {
  if (h15.hasSign === '否') {
    return { status: 'no-test', message: '无迹象，无需可收回测试' }
  }
  if (!h16) {
    return { status: 'missing-h16', message: 'H2-16 尚无同名工程组' }
  }
  const fvOk = Math.abs(h15.fairValueNet - h16.fairValueNet) < SYNC_TOLERANCE
  const pvOk = Math.abs(h15.pvCashFlows - h16.pvCashFlows) < SYNC_TOLERANCE
  if (fvOk && pvOk) {
    return { status: 'synced', message: '已与 H2-16 一致' }
  }
  return {
    status: 'stale',
    message: `与 H2-16 不一致（③差 ${Math.abs(h15.fairValueNet - h16.fairValueNet).toFixed(2)}，④差 ${Math.abs(h15.pvCashFlows - h16.pvCashFlows).toFixed(2)}）`,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Impairment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  section?: 'impairment' | 'recoverable'
  onSave?: (itemId: string, value: any) => void
}) {
  const signRows = ref<ImpairmentSignRow[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])
  const assumptions = ref<DcfAssumptions>(_defaultAssumptions())
  const cashFlowRows = ref<DcfCashFlowRow[]>([])
  const fvDisposal = ref<FairValueDisposal>(_defaultFv())
  const waccParams = ref<WaccParams>(_defaultWacc())
  const auditNote = ref('')
  const conclusion = ref('')
  const recoverableNote = ref('')
  const recoverableConclusion = ref('')
  const groups = ref<RecoverableGroup[]>([_defaultGroup()])
  const activeGroupId = ref(groups.value[0].groupId)

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
    // 无迹象时一般不做减值测试：可收回金额视同不低于账面，应提=已提（维持现状）
    if (row.hasSign === '否') {
      row.recoverableAmount = row.bookValue
      row.requiredProvision = Math.max(row.bookedProvision, 0)
      row.periodAdjustment = 0
      row.impairmentAmount = row.requiredProvision
      return
    }
    // ⑤ = MAX(③, ④)；若仅有旧版可收回金额而无分项，保留可收回金额
    const hasSplit = row.fairValueNet > 0 || row.pvCashFlows > 0
    if (hasSplit) {
      row.recoverableAmount = Math.max(row.fairValueNet, row.pvCashFlows)
    }
    // ⑥ = MAX(② − ⑤, 0)（修正 Excel 表头误写「⑤−②」）
    row.requiredProvision = Math.max(row.bookValue - row.recoverableAmount, 0)
    // ⑧ = ⑥ − ⑦
    row.periodAdjustment = row.requiredProvision - row.bookedProvision
    row.impairmentAmount = row.requiredProvision
  }

  function _emptyCalcRow(name = ''): ImpairmentCalcRow {
    return {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      hasSign: '',
      signDesc: '',
      bookValue: 0,
      fairValueNet: 0,
      pvCashFlows: 0,
      recoverableAmount: 0,
      requiredProvision: 0,
      bookedProvision: 0,
      periodAdjustment: 0,
      impairmentAmount: 0,
      method: '',
      wpIndex: '',
      remark: '',
    }
  }

  function _mapCalcRow(r: any): ImpairmentCalcRow {
    const fairValueNet = _num(r.fairValueNet)
    const pvCashFlows = _num(r.pvCashFlows)
    const legacyRec = _num(r.recoverableAmount)
    const bookedProvision = _num(r.bookedProvision)
    const row: ImpairmentCalcRow = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      name: r.name ?? '',
      hasSign: (r.hasSign === '是' || r.hasSign === '否') ? r.hasSign : '',
      signDesc: String(r.signDesc ?? ''),
      bookValue: _num(r.bookValue),
      fairValueNet,
      pvCashFlows,
      // 兼容旧数据：仅有 recoverableAmount 时作为⑤
      recoverableAmount: (fairValueNet > 0 || pvCashFlows > 0)
        ? Math.max(fairValueNet, pvCashFlows)
        : legacyRec,
      requiredProvision: 0,
      bookedProvision,
      periodAdjustment: 0,
      impairmentAmount: 0,
      method: r.method ?? '',
      wpIndex: String(r.wpIndex ?? ''),
      remark: r.remark ?? '',
    }
    _recalcCalcRow(row)
    return row
  }

  function _effectiveRatePct(): number {
    const ke = calcCostOfEquity(waccParams.value.riskFreeRate, waccParams.value.beta, waccParams.value.marketReturn)
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

  function _recalcCashFlowRow(row: DcfCashFlowRow): void {
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

  function _snapshotActiveToGroup(g: RecoverableGroup): void {
    g.name = assumptions.value.projectName || g.name
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

  function _loadGroupToActive(g: RecoverableGroup): void {
    assumptions.value = {
      ..._defaultAssumptions(),
      ...g.assumptions,
      projectName: g.name || g.assumptions.projectName,
      bookValue: g.bookValue || g.assumptions.bookValue,
    }
    waccParams.value = { ..._defaultWacc(), ...g.waccParams }
    fvDisposal.value = { ..._defaultFv(g.name), ...g.fvDisposal, projectName: g.name }
    cashFlowRows.value = (g.cashFlows?.length ? g.cashFlows : [1, 2, 3, 4, 5].map(year => ({ year, revenue: 0, cost: 0 })))
      .map((c, i) => {
        const row: DcfCashFlowRow = {
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
    // 兼容旧单组键（当前活动组）
    options.onSave?.(DCF_KEY, { ...assumptions.value })
    options.onSave?.(WACC_KEY, { ...waccParams.value })
    _persistFv()
    _persistCashFlows()
    options.onSave?.(REC_NOTE_KEY, recoverableNote.value)
    options.onSave?.(REC_CONCLUSION_KEY, recoverableConclusion.value)
  }

  function _groupResult(g: RecoverableGroup): { fairValueNet: number; pvCashFlows: number; recoverableAmount: number } {
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
      recoverableAmount: Math.max(fv, totalDcf),
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
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

    // H2-13 停工自动标记迹象（容错：解析失败忽略）
    const h213Rows = safeParseRows(
      options.allResponses.value.get('H2-13-rows')?.remark
      ?? options.allResponses.value.get('H2-13-rows')?.conclusion,
    )
    if (h213Rows.some((r: any) =>
      r.constructionStatus === '停工'
      || String(r.stopDuration ?? '').trim()
      || String(r.stopReason ?? '').trim()
      || r.isStopped === '是'
      || r.isStopped === true
    )) {
      const s4 = signRows.value.find(s => s.rowId === 'sign-4')
      if (s4 && s4.exists === '') s4.exists = '是'
    }

    const calcData = _getJson(CALC_KEY)
    if (Array.isArray(calcData)) {
      calcRows.value = calcData.map((r: any) => _mapCalcRow(r))
    } else {
      calcRows.value = []
    }

    // 多工程组：优先 GROUPS_KEY；否则从旧单组键迁移
    const groupsRaw = _getJson(GROUPS_KEY)
    if (Array.isArray(groupsRaw) && groupsRaw.length > 0) {
      groups.value = groupsRaw.map((g: any) => {
        const base = _defaultGroup(String(g.name || '工程组'))
        return {
          ...base,
          ...g,
          groupId: g.groupId || _newGroupId(),
          assumptions: { ..._defaultAssumptions(), ...(g.assumptions || {}) },
          waccParams: { ..._defaultWacc(), ...(g.waccParams || {}) },
          fvDisposal: { ..._defaultFv(g.name), ...(g.fvDisposal || {}) },
          cashFlows: Array.isArray(g.cashFlows) && g.cashFlows.length
            ? g.cashFlows
            : base.cashFlows,
          bookValuePending: Boolean(g.bookValuePending),
          source: (['manual', 'H2-15', 'H2-13', 'H2-2'].includes(g.source) ? g.source : 'manual') as RecoverableSourceKind,
        } as RecoverableGroup
      })
    } else {
      // 迁移旧单组
      const migrated = _defaultGroup('工程组-1')
      const dcf = _getJson(DCF_KEY)
      if (dcf && typeof dcf === 'object') {
        migrated.assumptions = {
          ..._defaultAssumptions(),
          discountRate: _num(dcf.discountRate) || 10,
          forecastYears: _num(dcf.forecastYears) || 5,
          growthRate: dcf.growthRate != null ? _num(dcf.growthRate) : 0,
          disposalCostRate: _num(dcf.disposalCostRate),
          bookValue: _num(dcf.bookValue),
          projectName: String(dcf.projectName ?? ''),
          growthRateBasis: String(dcf.growthRateBasis ?? ''),
          industryGrowthRate: _num(dcf.industryGrowthRate),
          countryGrowthRate: _num(dcf.countryGrowthRate),
          usePreTaxRate: dcf.usePreTaxRate !== false,
        }
        migrated.name = migrated.assumptions.projectName || migrated.name
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

    auditNote.value = _getString(NOTE_KEY)
    conclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: H2-15 ───────────────────────────────────────────────────────

  const hasImpairmentSign: ComputedRef<boolean> = computed(() =>
    signRows.value.some(s => s.exists === '是'),
  )

  const signYesCount: ComputedRef<number> = computed(() =>
    signRows.value.filter(s => s.exists === '是').length,
  )

  /** 迹象≥2项时须完成 H2-16（需求 12.5） */
  const needsRecoverableTest: ComputedRef<boolean> = computed(() => signYesCount.value >= 2)

  /** H2-16 是否已实质完成（结论或工程组/回写测算已有可收回金额） */
  const recoverableGateSatisfied: ComputedRef<boolean> = computed(() => {
    if (!needsRecoverableTest.value) return true
    if ((recoverableConclusion.value || '').trim()) return true
    if (groups.value.some((g) => {
      if ((g.conclusion || '').trim()) return true
      const fv = resolveFairValue(g.fvDisposal).value
      const hasCf = (g.cashFlows || []).some((c) => (c.revenue || 0) > 0 || (c.cost || 0) > 0)
      return fv > 0 || hasCf
    })) {
      return true
    }
    const signed = calcRows.value.filter((r) => r.hasSign === '是')
    if (
      signed.length > 0
      && signed.every((r) => r.recoverableAmount > 0 || r.fairValueNet > 0 || r.pvCashFlows > 0)
    ) {
      return true
    }
    return false
  })

  /** 门禁阻断：须做 H2-16 且尚未完成 */
  const impairmentGateBlocked: ComputedRef<boolean> = computed(
    () => needsRecoverableTest.value && !recoverableGateSatisfied.value,
  )

  const totalBookValue: ComputedRef<number> = computed(() =>
    calcRows.value.reduce((s, r) => s + r.bookValue, 0),
  )

  const totalRequiredProvision: ComputedRef<number> = computed(() =>
    calcRows.value.reduce((s, r) => s + r.requiredProvision, 0),
  )

  const totalBookedProvision: ComputedRef<number> = computed(() =>
    calcRows.value.reduce((s, r) => s + r.bookedProvision, 0),
  )

  const totalPeriodAdjustment: ComputedRef<number> = computed(() =>
    calcRows.value.reduce((s, r) => s + r.periodAdjustment, 0),
  )

  /** 兼容旧 UI：减值合计 = 应提合计 */
  const totalImpairment: ComputedRef<number> = computed(() => totalRequiredProvision.value)

  /** CAS8：长期资产减值不得转回 */
  const cas8ReversalRows: ComputedRef<ImpairmentCalcRow[]> = computed(() =>
    calcRows.value.filter(r => r.periodAdjustment < -0.005),
  )

  const missingRecoverableRows: ComputedRef<ImpairmentCalcRow[]> = computed(() =>
    calcRows.value.filter(r =>
      r.hasSign === '是'
      && r.bookValue > 0
      && r.fairValueNet <= 0
      && r.pvCashFlows <= 0
      && r.recoverableAmount <= 0,
    ),
  )

  /** ⑧>0 需补提的工程（可生成 AJE） */
  const supplementRows: ComputedRef<ImpairmentCalcRow[]> = computed(() =>
    calcRows.value.filter(r => r.periodAdjustment > 0.005),
  )

  const totalSupplement: ComputedRef<number> = computed(() =>
    supplementRows.value.reduce((s, r) => s + r.periodAdjustment, 0),
  )

  // ─── Computed: 公允净额 ────────────────────────────────────────────────────

  const fairValueResolved = computed(() => resolveFairValue(fvDisposal.value))
  const disposalTotal = computed(() => calcDisposalTotal(fvDisposal.value))
  /** 公允价值减去处置费用后的净额（不低于0） */
  const fairValueLessDisposal = computed(() =>
    Math.max(fairValueResolved.value.value - disposalTotal.value, 0),
  )

  // ─── Computed: WACC / DCF ──────────────────────────────────────────────────

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

  /** 增长率预警：g > 外部基准或 >0 且无依据 */
  const growthWarnings = computed(() => {
    const msgs: string[] = []
    const g = assumptions.value.growthRate
    const industry = assumptions.value.industryGrowthRate
    const country = assumptions.value.countryGrowthRate
    if (g > 0 && !assumptions.value.growthRateBasis.trim()) {
      msgs.push('永续增长率大于0，请填写增长率确定依据（准则提示：通常应为0或负，除非有充分证据）')
    }
    if (industry > 0 && g > industry) {
      msgs.push(`永续增长率(${g}%)超过行业长期平均增长率(${industry}%)`)
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
    Math.max(totalPV.value, fairValueLessDisposal.value),
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

  /** 上游候选（H2-15 优先；H2-13/H2-2 容错，解析失败视为空） */
  const upstreamCandidates = computed((): UpstreamCandidate[] => {
    const map = options.allResponses.value
    const h215 = calcRows.value
    const h213 = safeParseRows(map.get('H2-13-rows')?.remark ?? map.get('H2-13-rows')?.conclusion)
    const h22 = safeParseRows(map.get('H2-2-rows')?.remark ?? map.get('H2-2-rows')?.conclusion)
    return buildUpstreamCandidates({ h215Rows: h215, h213Rows: h213, h22Rows: h22 })
  })

  /** H2-15 与 H2-16 各组结果对照 */
  const syncChecks = computed((): H216SyncCheck[] => {
    const byName = new Map<string, RecoverableGroup>()
    for (const g of groups.value) {
      const n = (g.name || '').trim()
      if (n) byName.set(n, g)
    }
    // 把当前活动组最新结果合并进去（未 persist 前也能校验）
    const activeName = assumptions.value.projectName.trim()
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

    return calcRows.value.map((row) => {
      const name = row.name.trim() || '未命名'
      const g = byName.get(name) || null
      const h16 = g ? _groupResult(g) : null
      const { status, message } = classifySyncStatus(
        {
          fairValueNet: row.fairValueNet,
          pvCashFlows: row.pvCashFlows,
          recoverableAmount: row.recoverableAmount,
          hasSign: row.hasSign,
        },
        h16,
      )
      return {
        name,
        h15FairValueNet: row.fairValueNet,
        h16FairValueNet: h16?.fairValueNet ?? 0,
        h15Pv: row.pvCashFlows,
        h16Pv: h16?.pvCashFlows ?? 0,
        h15Recoverable: row.recoverableAmount,
        h16Recoverable: h16?.recoverableAmount ?? 0,
        status,
        message,
      }
    })
  })

  const staleSyncCount = computed(() =>
    syncChecks.value.filter(c => c.status === 'stale' || c.status === 'missing-h16').length,
  )

  // ─── Computed: 敏感性矩阵 ──────────────────────────────────────────────────

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

  const sensitivityMatrix: ComputedRef<SensitivityRow[]> = computed(() => {
    const baseR = effectiveDiscountRate.value
    const cols = sensitivityCols.value
    return [-2, -1, 0, 1, 2].map(rStep => {
      const rate = baseR + rStep
      const row: SensitivityRow = { label: `r=${rate.toFixed(1)}%` }
      for (const col of cols) {
        const dcf = _pvAt(rate, parseFloat(col))
        row[`g_${col}`] = Math.max(fairValueLessDisposal.value, dcf)
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

  function addCalcRow(name?: string): void {
    if (options.isReadonly.value) return
    calcRows.value.push(_emptyCalcRow(name || ''))
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
    // 公式列只读
    const formulaFields = ['recoverableAmount', 'requiredProvision', 'periodAdjustment', 'impairmentAmount']
    if (formulaFields.includes(field)) return
    if (field === 'hasSign') {
      row.hasSign = (value === '是' || value === '否') ? value : ''
    } else if (['bookValue', 'fairValueNet', 'pvCashFlows', 'bookedProvision'].includes(field)) {
      ;(row as any)[field] = _num(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcCalcRow(row)
    _persistCalc()
  }

  /** 从 H2-13 停工工程带入测算行 */
  function importStoppedFromH213(): { ok: boolean; added: number; message: string } {
    if (options.isReadonly.value) return { ok: false, added: 0, message: '只读模式' }
    const h2_13_resp = options.allResponses.value.get('H2-13-rows')
    const raw = h2_13_resp?.remark ?? h2_13_resp?.conclusion
    if (!raw) return { ok: false, added: 0, message: 'H2-13 暂无盘点行数据' }
    let rows: any[]
    try {
      rows = JSON.parse(raw)
    } catch {
      return { ok: false, added: 0, message: 'H2-13 数据解析失败' }
    }
    if (!Array.isArray(rows)) return { ok: false, added: 0, message: 'H2-13 数据格式异常' }
    const stopped = rows.filter((r: any) =>
      r.constructionStatus === '停工'
      || String(r.stopDuration ?? '').trim()
      || String(r.stopReason ?? '').trim()
      || r.isStopped === '是'
      || r.isStopped === true
    )
    if (stopped.length === 0) return { ok: false, added: 0, message: 'H2-13 未发现停工工程' }
    let added = 0
    for (const s of stopped) {
      const name = String(s.projectName ?? s.name ?? '').trim()
      if (!name) continue
      if (calcRows.value.some(r => r.name.trim() === name)) continue
      const row = _emptyCalcRow(name)
      row.hasSign = '是'
      const stopHint = [s.stopDuration, s.stopReason].filter(Boolean).join('；')
      row.signDesc = stopHint
        ? `H2-13 停工（${stopHint}）`
        : 'H2-13 盘点状态为停工'
      row.bookValue = _num(s.bookAmount ?? s.bookValue ?? s.carryingAmount)
      row.wpIndex = 'H2-13'
      calcRows.value.push(row)
      added++
    }
    if (added > 0) _persistCalc()
    return {
      ok: added > 0,
      added,
      message: added > 0
        ? `已从 H2-13 带入 ${added} 个停工工程`
        : '停工工程已在测算表中，未新增',
    }
  }

  /**
   * 从 H2-2 明细带入②账面价值（cipEnd/endAudited）与⑦已提减值（impairmentEnd）；
   * H2-2 为空时回退 H2-1 审定表工程行（仅账面，已提为0或保留原值）。
   */
  function importBookValuesFromH2(): {
    ok: boolean
    updated: number
    added: number
    source: 'H2-2' | 'H2-1' | ''
    h1Diff: number | null
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, updated: 0, added: 0, source: '', h1Diff: null, message: '只读模式' }
    }

    const detailRaw = _getJson(H22_ROWS_KEY)
    const detailProjects: Array<{ name: string; bookValue: number; bookedProvision: number }> = []
    if (Array.isArray(detailRaw)) {
      for (const r of detailRaw) {
        const name = String(r?.name ?? '').trim()
        if (!name || r?.isSubtotal || r?.isTotal) continue
        const endAudited = _num(r.endAudited)
        const cipEnd = _num(r.cipEnd)
        const bookValue = endAudited > 0 ? endAudited : cipEnd
        if (bookValue <= 0 && _num(r.impairmentEnd) <= 0) continue
        detailProjects.push({
          name,
          bookValue,
          bookedProvision: _num(r.impairmentEnd),
        })
      }
    }

    let source: 'H2-2' | 'H2-1' | '' = ''
    let projects = detailProjects
    if (projects.length > 0) {
      source = 'H2-2'
    } else {
      const adjRaw = _getJson(H21_ROWS_KEY)
      if (Array.isArray(adjRaw)) {
        for (const r of adjRaw) {
          const name = String(r?.name ?? '').trim()
          if (!name || r?.isSubtotal || r?.isTotal) continue
          const bookValue = _num(r.endAudited) || _num(r.endUnadjusted)
          if (bookValue <= 0) continue
          projects.push({ name, bookValue, bookedProvision: 0 })
        }
      }
      if (projects.length > 0) source = 'H2-1'
    }

    if (projects.length === 0) {
      return {
        ok: false, updated: 0, added: 0, source: '', h1Diff: null,
        message: 'H2-2/H2-1 暂无可带入的工程项目',
      }
    }

    let updated = 0
    let added = 0
    for (const p of projects) {
      let row = calcRows.value.find(r => r.name.trim() === p.name)
      if (!row) {
        row = _emptyCalcRow(p.name)
        calcRows.value.push(row)
        added++
      } else {
        updated++
      }
      row.bookValue = p.bookValue
      // H2-2 有减值期末则覆盖⑦；H2-1 回退时不覆盖已有⑦
      if (source === 'H2-2' || row.bookedProvision === 0) {
        row.bookedProvision = p.bookedProvision
      }
      if (!row.wpIndex) row.wpIndex = source
      _recalcCalcRow(row)
    }
    _persistCalc()

    // 与 H2-1 审定合计勾稽（排除小计/合计行）
    let h1Total = 0
    const h1Raw = _getJson(H21_ROWS_KEY)
    if (Array.isArray(h1Raw)) {
      for (const r of h1Raw) {
        if (r?.isSubtotal || r?.isTotal) continue
        const name = String(r?.name ?? '').trim()
        if (!name) continue
        h1Total += _num(r.endAudited) || _num(r.endUnadjusted)
      }
    }
    const importedBook = projects.reduce((s, p) => s + p.bookValue, 0)
    const h1Diff = h1Total > 0 ? importedBook - h1Total : null

    let message = `已从 ${source} 更新 ${updated} 项、新增 ${added} 项（②账面 / ⑦已提）`
    if (h1Diff != null && Math.abs(h1Diff) >= 0.01) {
      message += `；与 H2-1 审定合计差异 ${h1Diff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，请核对`
    }
    return { ok: true, updated, added, source, h1Diff, message }
  }

  /**
   * ⑧>0 的工程一键生成补提 AJE 草稿并写入 H2-3；
   * ⑧<0（拟冲回）按 CAS8 跳过不生成。重复推送会先清理旧自动草稿。
   */
  function pushAjeDraftToH23(): {
    ok: boolean
    added: number
    skippedReversal: number
    amount: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, skippedReversal: 0, amount: 0, message: '只读模式' }
    }
    const toPush = supplementRows.value
    const skippedReversal = cas8ReversalRows.value.length
    if (toPush.length === 0) {
      return {
        ok: false,
        added: 0,
        skippedReversal,
        amount: 0,
        message: skippedReversal > 0
          ? `无补提项；有 ${skippedReversal} 项⑧为负（CAS8不得转回），未生成冲回分录`
          : '本期⑧均为0，无需生成调整分录',
      }
    }

    let existing: any[] = []
    const raw = _getJson(H23_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw

    // 清理本底稿上次自动草稿
    existing = existing.filter((r: any) => r?.remark !== H215_AJE_MARKER)

    let seq = existing.reduce((m: number, r: any) => Math.max(m, _num(r.seq)), 0) + 1
    const newRows: any[] = []
    for (const calc of toPush) {
      const pair = buildImpairmentAjePair({
        projectName: calc.name,
        amount: calc.periodAdjustment,
        seqStart: seq,
      })
      newRows.push(...pair)
      seq += pair.length
    }

    const merged = [...existing, ...newRows].map((r, i) => ({ ...r, seq: i + 1 }))
    options.onSave?.(H23_ROWS_KEY, merged)

    const amount = toPush.reduce((s, r) => s + r.periodAdjustment, 0)
    let message = `已向 H2-3 推送 ${newRows.length} 条 AJE 草稿（补提合计 ${amount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}）`
    if (skippedReversal > 0) {
      message += `；另有 ${skippedReversal} 项拟冲回已跳过（CAS8）`
    }
    return { ok: true, added: newRows.length, skippedReversal, amount, message }
  }

  // ─── Actions: H2-16 ────────────────────────────────────────────────────────

  function updateAssumption(field: string, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'fairValueLessDisposal') {
      fvDisposal.value.estimatedPrice = _num(value)
      _persistActiveGroup()
      return
    }
    if (field in assumptions.value) {
      if (field === 'projectName' || field === 'growthRateBasis') {
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
      if (field === 'projectName') {
        fvDisposal.value.projectName = String(value ?? '')
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

  function updateFvDisposal(partial: Partial<FairValueDisposal>): void {
    if (options.isReadonly.value) return
    Object.assign(fvDisposal.value, partial)
    _persistActiveGroup()
  }

  function updateWaccParams(partial: Partial<WaccParams>): void {
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
    const g = _defaultGroup(name || `工程组-${groups.value.length + 1}`)
    groups.value.push(g)
    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()
    return g.groupId
  }

  function removeActiveGroup(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    if (groups.value.length <= 1) return { ok: false, message: '至少保留一个工程组' }
    const idx = groups.value.findIndex(g => g.groupId === activeGroupId.value)
    if (idx < 0) return { ok: false, message: '未找到当前组' }
    groups.value.splice(idx, 1)
    activeGroupId.value = groups.value[Math.max(0, idx - 1)].groupId
    _loadGroupToActive(groups.value.find(g => g.groupId === activeGroupId.value)!)
    _persistActiveGroup()
    return { ok: true, message: '已删除当前工程组' }
  }

  /** 从上游候选创建/切换工程组（H2-13 无账面也不阻断） */
  function importUpstreamCandidate(key: string): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    const cand = upstreamCandidates.value.find(c => c.key === key)
    if (!cand) return { ok: false, message: '未找到候选工程（上游数据可能尚未就绪）' }

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
    g.assumptions.projectName = cand.name
    g.assumptions.bookValue = cand.bookValue
    g.fvDisposal.projectName = cand.name

    activeGroupId.value = g.groupId
    _loadGroupToActive(g)
    _persistActiveGroup()

    const pendingTip = g.bookValuePending
      ? '；账面价值待补录（H2-13 当前无可靠账面列，建议从 H2-2/H2-15 补齐）'
      : ''
    return { ok: true, message: `已载入「${cand.name}」（来源 ${cand.source}）${pendingTip}` }
  }

  /** 从 H2-15 测算行带入账面价值与工程名称（兼容旧 API） */
  function importFromH215(rowId?: string): boolean {
    if (options.isReadonly.value) return false
    const target = rowId
      ? calcRows.value.find(r => r.rowId === rowId)
      : calcRows.value[0]
    if (!target) return false
    const key = `H2-15:${target.name.trim()}`
    // 若不在候选中，临时构造
    const found = upstreamCandidates.value.find(c => c.key === key || (c.source === 'H2-15' && c.sourceRowId === target.rowId))
    if (found) {
      return importUpstreamCandidate(found.key).ok
    }
    assumptions.value.projectName = target.name
    assumptions.value.bookValue = target.bookValue
    fvDisposal.value.projectName = target.name
    const g = groups.value.find(x => x.groupId === activeGroupId.value)
    if (g) {
      g.name = target.name
      g.bookValue = target.bookValue
      g.bookValuePending = !(target.bookValue > 0)
      g.source = 'H2-15'
      g.sourceRowId = target.rowId
    }
    _persistActiveGroup()
    return true
  }

  /**
   * 将可收回金额回写至 H2-15 同名工程行；
   * 写入③公允净额、④现值，⑤由公式计算；无匹配时回写首行或新增一行。
   */
  function syncToH215(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式不可回写' }
    const name = assumptions.value.projectName.trim()
    let row = name
      ? calcRows.value.find(r => r.name.trim() === name)
      : undefined
    if (!row && calcRows.value.length === 1) {
      row = calcRows.value[0]
    }
    if (!row) {
      if (!name && calcRows.value.length === 0) {
        return { ok: false, message: '请先填写工程项目名称，或在 H2-15 新增测算行' }
      }
      addCalcRow(name || '在建工程-1')
      row = calcRows.value[calcRows.value.length - 1]
    }
    row.fairValueNet = fairValueLessDisposal.value
    row.pvCashFlows = totalPV.value
    if (assumptions.value.bookValue > 0) {
      row.bookValue = assumptions.value.bookValue
    }
    if (name) row.name = name
    if (!row.hasSign) row.hasSign = '是'
    row.method = recoverableSource.value === '公允净额' ? '市场比较' : 'DCF'
    row.wpIndex = 'H2-16'
    row.remark = `由H2-16回写（③=${fairValueLessDisposal.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，④=${totalPV.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，取${recoverableSource.value}）`
    _recalcCalcRow(row)
    _persistCalc()
    _persistActiveGroup()
    return {
      ok: true,
      message: `已回写「${row.name}」可收回金额 ${row.recoverableAmount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    }
  }

  /** 批量回写全部工程组至 H2-15 */
  function syncAllGroupsToH215(): { ok: boolean; synced: number; message: string } {
    if (options.isReadonly.value) return { ok: false, synced: 0, message: '只读模式' }
    const cur = groups.value.find(g => g.groupId === activeGroupId.value)
    if (cur) _snapshotActiveToGroup(cur)

    let synced = 0
    for (const g of groups.value) {
      const result = _groupResult(g)
      const name = (g.name || '').trim()
      if (!name && result.recoverableAmount <= 0) continue
      let row = name ? calcRows.value.find(r => r.name.trim() === name) : undefined
      if (!row) {
        row = _emptyCalcRow(name || `工程组-${synced + 1}`)
        calcRows.value.push(row)
      }
      row.fairValueNet = result.fairValueNet
      row.pvCashFlows = result.pvCashFlows
      if (g.bookValue > 0) row.bookValue = g.bookValue
      if (name) row.name = name
      if (!row.hasSign) row.hasSign = '是'
      row.method = result.fairValueNet >= result.pvCashFlows && result.fairValueNet > 0 ? '市场比较' : 'DCF'
      row.wpIndex = 'H2-16'
      row.remark = `由H2-16批量回写（组 ${g.groupId}）`
      _recalcCalcRow(row)
      synced++
    }
    if (synced > 0) _persistCalc()
    _persistActiveGroup()
    return {
      ok: synced > 0,
      synced,
      message: synced > 0 ? `已批量回写 ${synced} 个工程组至 H2-15` : '没有可回写的工程组',
    }
  }

  function saveConclusion(text: string): { ok: boolean; message?: string } {
    const trimmed = (text || '').trim()
    if (impairmentGateBlocked.value && isCleanImpairmentConclusion(trimmed)) {
      return {
        ok: false,
        message:
          '减值迹象≥2项且 H2-16 未完成：不可使用「未见异常/计提充分」类结论。请先完成 H2-16，或改用范围受限结论。',
      }
    }
    conclusion.value = text
    options.onSave?.(CONCLUSION_KEY, text)
    return { ok: true }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveRecoverableNote(note: string): void {
    recoverableNote.value = note
    _persistActiveGroup()
  }

  function saveRecoverableConclusion(text: string): void {
    recoverableConclusion.value = text
    _persistActiveGroup()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSigns(): void {
    options.onSave?.(SIGNS_KEY, signRows.value.map(s => ({
      rowId: s.rowId, indicator: s.indicator, exists: s.exists, evidence: s.evidence,
    })))
  }

  function _persistCalc(): void {
    options.onSave?.(CALC_KEY, calcRows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      hasSign: r.hasSign,
      signDesc: r.signDesc,
      bookValue: r.bookValue,
      fairValueNet: r.fairValueNet,
      pvCashFlows: r.pvCashFlows,
      recoverableAmount: r.recoverableAmount,
      bookedProvision: r.bookedProvision,
      method: r.method,
      wpIndex: r.wpIndex,
      remark: r.remark,
    })))
  }

  function _persistCashFlows(): void {
    options.onSave?.(CASHFLOWS_KEY, cashFlowRows.value.map(c => ({
      rowId: c.rowId, year: c.year, revenue: c.revenue, cost: c.cost,
    })))
  }

  function _persistFv(): void {
    options.onSave?.(FAIRVALUE_KEY, { ...fvDisposal.value })
  }

  return {
    // State
    signRows, calcRows, assumptions, cashFlowRows, fvDisposal, waccParams,
    auditNote, conclusion, recoverableNote, recoverableConclusion,
    groups, activeGroupId, activeGroup,
    // Computed: H2-15
    hasImpairmentSign, signYesCount, needsRecoverableTest,
    recoverableGateSatisfied, impairmentGateBlocked,
    totalBookValue, totalRequiredProvision, totalBookedProvision, totalPeriodAdjustment,
    totalImpairment, cas8ReversalRows, missingRecoverableRows,
    supplementRows, totalSupplement,
    // Computed: H2-16 公允/WACC/DCF
    fairValueResolved, disposalTotal, fairValueLessDisposal,
    costOfEquity, waccAfterTax, preTaxDiscountRate, effectiveDiscountRate, rateInvalid,
    growthWarnings,
    pvTotal, tvPresent, terminalValueUndiscounted, totalPV,
    recoverableAmount, recoverableSource, impliedImpairment,
    sensitivityCols, sensitivityMatrix,
    upstreamCandidates, syncChecks, staleSyncCount,
    // Actions
    updateSignCell,
    addCalcRow, removeCalcRow, updateCalcCell,
    importStoppedFromH213, importBookValuesFromH2, pushAjeDraftToH23,
    updateAssumption, updateFvDisposal, updateWaccParams, updateCashFlowCell,
    setActiveGroup, addGroup, removeActiveGroup,
    importUpstreamCandidate, importFromH215, syncToH215, syncAllGroupsToH215,
    saveConclusion, saveNote, saveRecoverableNote, saveRecoverableConclusion,
    initFromAllResponses,
  }
}

export default useH2Impairment