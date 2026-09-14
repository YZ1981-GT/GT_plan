/**
 * h8RecoverableModel — H8-11 可收回金额纯函数与类型
 *
 * 对齐致同「使用权资产减值准备测试表-可收回金额」：
 *   一、公允净额（销售协议→活跃市场→估计 − 处置费用）
 *   二、预计未来现金流量现值（DCF + WACC/CAPM）
 *   三、可收回金额 = MAX(①,②)
 */
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  safeParseRows,
  type H4FairValueDisposal,
  type H4WaccParams,
} from './h4RecoverableModel'

export {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  safeParseRows,
}

/** 复用 H4 公允/处置费用结构（字段一致，仅语义改为使用权资产） */
export type H8FairValueDisposal = Omit<H4FairValueDisposal, 'materialName'> & {
  assetName: string
}

export type H8WaccParams = H4WaccParams

export interface H8DcfAssumptions {
  /** 手工折现率%（WACC 未就绪时回退） */
  discountRate: number
  forecastYears: number
  /** 永续增长率 g% */
  growthRate: number
  bookValue: number
  assetName: string
  growthRateBasis: string
  industryGrowthRate: number
  marketGrowthRate: number
  countryGrowthRate: number
  /** CAS8 默认税前 */
  usePreTaxRate: boolean
  /** 剩余租赁期（年，用于预测期校验） */
  remainingLeaseYears: number
  /** 增量借款利率%（可从 H8-6 带入，作为手工折现率快捷填充） */
  incrementalBorrowingRate: number
}

export interface H8DcfCashFlowRow {
  rowId: string
  year: number
  revenue: number
  cost: number
  netCashFlow: number
  discountFactor: number
  presentValue: number
}

export interface H8SensitivityRow {
  label: string
  [key: string]: number | string
}

export type H8RecoverableSourceKind = 'manual' | 'H8-10' | 'H8-2'

export interface H8RecoverableGroup {
  groupId: string
  name: string
  /** 合同号（与 H8-10/H8-2 匹配） */
  contractNo?: string
  bookValue: number
  source: H8RecoverableSourceKind
  sourceRowId?: string
  bookValuePending: boolean
  assumptions: H8DcfAssumptions
  waccParams: H8WaccParams
  fvDisposal: H8FairValueDisposal
  cashFlows: Array<{ year: number; revenue: number; cost: number }>
  note: string
  conclusion: string
  /** 缓存：供 H8-10 按组回填（与 _groupResult 同步） */
  _fairValueNet?: number
  _pvCashFlows?: number
}

export interface H8UpstreamCandidate {
  key: string
  source: H8RecoverableSourceKind
  sourceRowId: string
  name: string
  contractNo?: string
  bookValue: number
  bookValueReady: boolean
  remainingLeaseYears?: number
  hint: string
  /** H8-10 有迹象优先展示 */
  hasIndication?: boolean
}

export interface H810SyncCheck {
  name: string
  h10Recoverable: number
  h11Recoverable: number
  status: 'synced' | 'stale' | 'missing-h11' | 'no-test'
  message: string
}

const SYNC_TOLERANCE = 0.01

export function calcRecoverableAmount(fairValueNet: number, pvCashFlows: number): number {
  return Math.max(Number(fairValueNet) || 0, Number(pvCashFlows) || 0)
}

export function toH4FvShape(fv: H8FairValueDisposal): H4FairValueDisposal {
  return {
    materialName: fv.assetName,
    salesAgreementPrice: fv.salesAgreementPrice,
    salesAgreementNote: fv.salesAgreementNote,
    activeMarketPrice: fv.activeMarketPrice,
    activeMarketNote: fv.activeMarketNote,
    estimatedPrice: fv.estimatedPrice,
    estimatedNote: fv.estimatedNote,
    legalFees: fv.legalFees,
    relatedTaxes: fv.relatedTaxes,
    transportCosts: fv.transportCosts,
    directCosts: fv.directCosts,
    otherCosts: fv.otherCosts,
    auditNote: fv.auditNote,
  }
}

export function resolveH8FairValue(fv: H8FairValueDisposal): { value: number; source: string } {
  return resolveFairValue(toH4FvShape(fv))
}

export function calcH8DisposalTotal(fv: H8FairValueDisposal): number {
  return calcDisposalTotal(toH4FvShape(fv))
}

/** 预测期是否超过剩余租赁期 */
export function checkForecastVsLeaseTerm(
  forecastYears: number,
  remainingLeaseYears: number,
): string | null {
  if (remainingLeaseYears > 0 && forecastYears > remainingLeaseYears + 1e-9) {
    return `预测期(${forecastYears}年)超过剩余租赁期(${remainingLeaseYears}年)，使用权资产现金流量预测通常不应超过剩余租赁期`
  }
  return null
}

export function buildH8UpstreamCandidates(opts: {
  h10Params?: any
  h10Rows?: any[]
  h2Rows?: any[]
}): H8UpstreamCandidate[] {
  const out: H8UpstreamCandidate[] = []
  const seen = new Set<string>()

  for (const r of opts.h10Rows ?? []) {
    const name = String(r?.assetName || r?.contractNo || '').trim()
    if (!name) continue
    const book = Number(r.bookValue) || 0
    const key = `H8-10:${r.rowId || name}`
    if (seen.has(key)) continue
    seen.add(key)
    const hasIndication = r.hasIndication === 'Y'
    out.push({
      key,
      source: 'H8-10',
      sourceRowId: String(r.rowId ?? name),
      name,
      contractNo: String(r.contractNo || '').trim() || undefined,
      bookValue: book,
      bookValueReady: book > 0,
      hasIndication,
      hint: hasIndication
        ? `H8-10 有迹象（优先测试）${r.indexRef ? ` · ${r.indexRef}` : ''}`
        : 'H8-10 行级测算',
    })
  }

  const p = opts.h10Params
  if (p && typeof p === 'object' && !(opts.h10Rows && opts.h10Rows.length)) {
    const book = Number(p.bookValue) || 0
    const name = String(p.assetName || p.name || '').trim() || '使用权资产（H8-10）'
    const key = `H8-10:${name}`
    seen.add(key)
    const hasIndication = !!(p.impairmentSign && p.impairmentSign !== '无')
    out.push({
      key,
      source: 'H8-10',
      sourceRowId: 'H8-10-params',
      name,
      bookValue: book,
      bookValueReady: book > 0,
      hasIndication,
      hint: hasIndication
        ? `H8-10 减值测算（迹象：${p.impairmentSign}）`
        : 'H8-10 减值测算',
    })
  }

  for (const r of opts.h2Rows ?? []) {
    const name = String(r?.assetName || r?.contractNo || '').trim()
    if (!name) continue
    const cost = Number(r.initialAmount) || 0
    const accDep = Number(r.accDepEnd) || ((Number(r.accDepBegin) || 0) + (Number(r.depCurrentPeriod) || 0))
    const bookFromCost = cost > 0 ? Math.max(cost - accDep, 0) : 0
    const net = bookFromCost > 0 ? bookFromCost : (Number(r.netValue) || 0)
    const key = `H8-2:${r.rowId || name}`
    if (seen.has(key)) continue
    seen.add(key)
    const remainingLeaseYears = estimateRemainingLeaseYears(String(r.endDate || r.leaseEndDate || ''))
    out.push({
      key,
      source: 'H8-2',
      sourceRowId: String(r.rowId ?? ''),
      name,
      contractNo: String(r.contractNo || '').trim() || undefined,
      bookValue: net,
      bookValueReady: net > 0,
      remainingLeaseYears: remainingLeaseYears || undefined,
      hint: net > 0
        ? `H8-2 账面②=入账值−累计折旧（合同 ${r.contractNo || '-'}）`
        : 'H8-2 明细（账面待核）',
    })
  }

  // 有迹象的 H8-10 行排前，便于优先载入
  out.sort((a, b) => Number(!!b.hasIndication) - Number(!!a.hasIndication))
  return out
}

/** 由到期日估算剩余租赁期（年，保留1位） */
export function estimateRemainingLeaseYears(endDate: string, asOf = new Date()): number {
  if (!endDate?.trim()) return 0
  const end = new Date(endDate)
  if (Number.isNaN(end.getTime())) return 0
  const years = (end.getTime() - asOf.getTime()) / (365.25 * 24 * 3600 * 1000)
  return Math.max(0, Math.round(years * 10) / 10)
}

export function classifyH810SyncStatus(
  h10: { recoverableAmount: number; hasSign?: string },
  h11: { recoverableAmount: number } | null,
): { status: H810SyncCheck['status']; message: string } {
  const needTest = h10.hasSign === '是' || (Number(h10.recoverableAmount) || 0) > 0
  if (!needTest && (!h11 || h11.recoverableAmount <= 0)) {
    return { status: 'no-test', message: '无需测试或尚未测算' }
  }
  if (!h11 || h11.recoverableAmount <= 0) {
    return { status: 'missing-h11', message: 'H8-10 需可收回金额，但 H8-11 尚未完成测算' }
  }
  const diff = Math.abs((Number(h10.recoverableAmount) || 0) - h11.recoverableAmount)
  if (diff <= SYNC_TOLERANCE) {
    return { status: 'synced', message: 'H8-10 与 H8-11 可收回金额一致' }
  }
  return {
    status: 'stale',
    message: `不一致：H8-10=${h10.recoverableAmount.toLocaleString('zh-CN')}，H8-11=${h11.recoverableAmount.toLocaleString('zh-CN')}`,
  }
}

/** 将旧版 H8-11-params（年金简化模型）迁移为组假设 */
export function migrateLegacyH811Params(raw: any): Partial<H8DcfAssumptions> & {
  annualCashFlow?: number
  terminalValue?: number
} {
  if (!raw || typeof raw !== 'object') return {}
  const rateRaw = Number(raw.discountRate)
  // 旧版存小数(0.05)，新版存百分数(5)
  const discountRate = rateRaw > 0 && rateRaw < 1 ? rateRaw * 100 : (rateRaw || 10)
  return {
    discountRate,
    forecastYears: Number(raw.forecastYears) || 5,
    annualCashFlow: Number(raw.annualCashFlow) || 0,
    terminalValue: Number(raw.terminalValue) || 0,
  }
}
