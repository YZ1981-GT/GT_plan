/**
 * h4RecoverableModel — H4-8 可收回金额纯函数与类型（从 useH4Recoverable 拆出）
 */

const SYNC_TOLERANCE = 0.01

/** 公允价值 − 处置费用（对齐 Excel 第一节） */
export interface H4FairValueDisposal {
  materialName: string
  salesAgreementPrice: number
  salesAgreementNote: string
  activeMarketPrice: number
  activeMarketNote: string
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
export interface H4WaccParams {
  taxRate: number
  totalDebt: number
  totalEquity: number
  costOfDebt: number
  riskFreeRate: number
  beta: number
  marketReturn: number
}

/** H4-8 DCF 关键假设 */
export interface H4DcfAssumptions {
  discountRate: number
  forecastYears: number
  growthRate: number
  disposalCostRate: number
  bookValue: number
  materialName: string
  growthRateBasis: string
  industryGrowthRate: number
  marketGrowthRate: number
  countryGrowthRate: number
  usePreTaxRate: boolean
}

/** H4-8 逐年现金流预测行 */
export interface H4DcfCashFlowRow {
  rowId: string
  year: number
  revenue: number
  cost: number
  netCashFlow: number
  discountFactor: number
  presentValue: number
}

export interface H4SensitivityRow {
  label: string
  [key: string]: number | string
}

export type H4RecoverableSourceKind = 'manual' | 'H4-7' | 'H4-2' | 'H4-6'

export interface H4RecoverableGroup {
  groupId: string
  name: string
  bookValue: number
  source: H4RecoverableSourceKind
  sourceRowId?: string
  bookValuePending: boolean
  assumptions: H4DcfAssumptions
  waccParams: H4WaccParams
  fvDisposal: H4FairValueDisposal
  cashFlows: Array<{ year: number; revenue: number; cost: number }>
  note: string
  conclusion: string
}

export interface H4UpstreamCandidate {
  key: string
  source: H4RecoverableSourceKind
  sourceRowId: string
  name: string
  bookValue: number
  bookValueReady: boolean
  hint: string
}

/** H4-7 ↔ H4-8 回写一致性 */
export interface H48SyncCheck {
  name: string
  h7Recoverable: number
  h8Recoverable: number
  status: 'synced' | 'stale' | 'missing-h8' | 'no-test'
  message: string
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

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

export function resolveFairValue(fv: H4FairValueDisposal): { value: number; source: string } {
  if (fv.salesAgreementPrice > 0) return { value: fv.salesAgreementPrice, source: '销售协议价格' }
  if (fv.activeMarketPrice > 0) return { value: fv.activeMarketPrice, source: '活跃市场价格' }
  if (fv.estimatedPrice > 0) return { value: fv.estimatedPrice, source: '估计价格' }
  return { value: 0, source: '未确定' }
}

export function calcDisposalTotal(fv: H4FairValueDisposal): number {
  return (fv.legalFees || 0) + (fv.relatedTaxes || 0) + (fv.transportCosts || 0)
    + (fv.directCosts || 0) + (fv.otherCosts || 0)
}

export function safeParseRows(raw: unknown): any[] {
  if (raw == null) return []
  let data = raw
  if (typeof raw === 'string') {
    try { data = JSON.parse(raw) } catch { return [] }
  }
  return Array.isArray(data) ? data : []
}

export function buildH4UpstreamCandidates(opts: {
  h47Rows?: any[]
  h42Rows?: any[]
  h46Rows?: any[]
}): H4UpstreamCandidate[] {
  const out: H4UpstreamCandidate[] = []
  const seen = new Set<string>()

  for (const r of opts.h47Rows ?? []) {
    const name = String(r?.name ?? '').trim()
    if (!name) continue
    const key = `H4-7:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      key,
      source: 'H4-7',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: Number(r.bookValue) || 0,
      bookValueReady: Number(r.bookValue) > 0,
      hint: r.hasSign === '是' ? 'H4-7 测算（有迹象）' : 'H4-7 测算',
    })
  }

  for (const r of opts.h42Rows ?? []) {
    const name = String(r?.name ?? '').trim()
    if (!name) continue
    const endAmt = Number(r.bookValueEnd ?? r.endAmount ?? r.bookAmount) || 0
    const existing = out.find(c => c.name === name)
    if (existing) {
      if (!existing.bookValueReady && endAmt > 0) {
        existing.bookValue = endAmt
        existing.bookValueReady = true
        existing.hint += '；账面已由 H4-2 补齐'
      }
      continue
    }
    const key = `H4-2:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      key,
      source: 'H4-2',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: endAmt,
      bookValueReady: endAmt > 0,
      hint: endAmt > 0 ? 'H4-2 明细期末账面' : 'H4-2 明细（账面待核）',
    })
  }

  for (const r of opts.h46Rows ?? []) {
    const name = String(r?.name ?? '').trim()
    if (!name) continue
    const diffQty = Number(r.diffQuantity ?? r.diffQty) || 0
    const bookAmt = Number(r.bookAmount ?? r.bookAmt) || 0
    const hasAttention = diffQty !== 0 || bookAmt > 0
      || String(r?.qualityStatus ?? '').trim() !== ''
      || String(r?.idleStatus ?? '').trim() !== ''
    if (!hasAttention && diffQty === 0 && bookAmt === 0) continue

    const existing = out.find(c => c.name === name)
    if (existing) {
      existing.hint += '；H4-6 盘点关注'
      if (bookAmt > 0 && !(existing.bookValue > 0)) {
        existing.bookValue = bookAmt
        existing.bookValueReady = true
        existing.hint += '；账面已由 H4-6 补齐'
      }
      continue
    }
    const key = `H4-6:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      key,
      source: 'H4-6',
      sourceRowId: String(r.rowId ?? ''),
      name,
      bookValue: bookAmt,
      bookValueReady: bookAmt > 0,
      hint: bookAmt > 0
        ? 'H4-6 盘点关注（含账面）'
        : 'H4-6 盘点关注；账面请从 H4-2/H4-7 补录',
    })
  }

  return out
}

export function classifyH48SyncStatus(
  h47: { fairValueNet: number; pvCashFlows: number; recoverableAmount: number; hasSign: string },
  h48: { fairValueNet: number; pvCashFlows: number; recoverableAmount: number } | null,
): Pick<H48SyncCheck, 'status' | 'message'> {
  if (h47.hasSign === '否') {
    return { status: 'no-test', message: '无迹象，无需可收回测试' }
  }
  if (!h48) {
    return { status: 'missing-h8', message: 'H4-8 尚无同名物资组' }
  }
  const fvOk = Math.abs(h47.fairValueNet - h48.fairValueNet) < SYNC_TOLERANCE
  const pvOk = Math.abs(h47.pvCashFlows - h48.pvCashFlows) < SYNC_TOLERANCE
  if (fvOk && pvOk) {
    return { status: 'synced', message: '已与 H4-8 一致' }
  }
  return {
    status: 'stale',
    message: `与 H4-8 不一致（③差 ${Math.abs(h47.fairValueNet - h48.fairValueNet).toFixed(2)}，④差 ${Math.abs(h47.pvCashFlows - h48.pvCashFlows).toFixed(2)}）`,
  }
}

