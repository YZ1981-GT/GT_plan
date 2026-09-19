/**
 * i1RecoverableModel — I1-13 可收回金额纯函数与类型
 *
 * 对齐致同「无形资产减值准备测试表-可收回金额」Excel（I1-13）：
 *   一、公允净额：N = IF(销售协议>0,协议,IF(活跃市场>0,市场,估计)) − Σ处置费用
 *   二、预计未来现金流量现值：DCF + WACC/CAPM（税前折现率默认）
 *   三、可收回金额 = MAX(公允净额, 使用价值)  对应源表 N23=MAX(N14,N20)
 */
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  type H4FairValueDisposal,
  type H4WaccParams,
} from './h4RecoverableModel'
import {
  calcDcfPresentValue,
  calcTerminalValue,
  calcRecoverableAmount,
} from './useI1AmortizationEngine'

export {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  calcRecoverableAmount,
}

export const DCF_FORECAST_YEARS = 5

/** 公允价值 − 处置费用（对齐 Excel 第一节） */
export interface I1FairValueDisposal {
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

/** WACC/CAPM 参数（百分比口径，与 H4/H8 一致：25=25%） */
export interface I1WaccParams {
  taxRate: number
  totalDebt: number
  totalEquity: number
  costOfDebt: number
  riskFreeRate: number
  beta: number
  marketReturn: number
}

export function defaultFvDisposal(): I1FairValueDisposal {
  return {
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

export function defaultWaccParams(): I1WaccParams {
  return {
    taxRate: 25,
    totalDebt: 0,
    totalEquity: 0,
    costOfDebt: 0,
    riskFreeRate: 0,
    beta: 1,
    marketReturn: 0,
  }
}

function toH4Fv(fv: I1FairValueDisposal): H4FairValueDisposal {
  return {
    materialName: '',
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

export function resolveI1FairValue(fv: I1FairValueDisposal): { value: number; source: string } {
  return resolveFairValue(toH4Fv(fv))
}

export function calcI1DisposalTotal(fv: I1FairValueDisposal): number {
  return calcDisposalTotal(toH4Fv(fv))
}

/** 公允净额 = 选用公允 − 处置费用合计（Excel N11） */
export function calcFairValueNet(fv: I1FairValueDisposal): number {
  const { value } = resolveI1FairValue(fv)
  return value - calcI1DisposalTotal(fv)
}

/**
 * 是否已填写公允明细（用于兼容旧数据：仅有 flat fairValueLessDisposal）
 */
export function hasFvDetail(fv: I1FairValueDisposal | undefined | null): boolean {
  if (!fv) return false
  return (
    fv.salesAgreementPrice > 0
    || fv.activeMarketPrice > 0
    || fv.estimatedPrice > 0
    || calcI1DisposalTotal(fv) > 0
  )
}

export function normalizeFvDisposal(raw: any): I1FairValueDisposal {
  const d = defaultFvDisposal()
  if (!raw || typeof raw !== 'object') return d
  return {
    salesAgreementPrice: Number(raw.salesAgreementPrice) || 0,
    salesAgreementNote: String(raw.salesAgreementNote ?? ''),
    activeMarketPrice: Number(raw.activeMarketPrice) || 0,
    activeMarketNote: String(raw.activeMarketNote ?? ''),
    estimatedPrice: Number(raw.estimatedPrice) || 0,
    estimatedNote: String(raw.estimatedNote ?? ''),
    legalFees: Number(raw.legalFees) || 0,
    relatedTaxes: Number(raw.relatedTaxes) || 0,
    transportCosts: Number(raw.transportCosts) || 0,
    directCosts: Number(raw.directCosts) || 0,
    otherCosts: Number(raw.otherCosts) || 0,
    auditNote: String(raw.auditNote ?? ''),
  }
}

export function normalizeWaccParams(raw: any): I1WaccParams {
  const d = defaultWaccParams()
  if (!raw || typeof raw !== 'object') return d
  return {
    taxRate: Number(raw.taxRate) || 0,
    totalDebt: Number(raw.totalDebt) || 0,
    totalEquity: Number(raw.totalEquity) || 0,
    costOfDebt: Number(raw.costOfDebt) || 0,
    riskFreeRate: Number(raw.riskFreeRate) || 0,
    beta: Number(raw.beta) || 0,
    marketReturn: Number(raw.marketReturn) || 0,
  }
}

/**
 * 有效折现率（小数口径，如 0.10）。
 * WACC 就绪时取税前/税后；否则回退手工折现率。
 */
export function calcEffectiveDiscountRate(
  wacc: I1WaccParams,
  manualDiscountRate: number,
  usePreTaxRate: boolean,
): {
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveRate: number
  fromWacc: boolean
} {
  const ke = calcCostOfEquity(wacc.riskFreeRate, wacc.beta, wacc.marketReturn)
  const waccAt = calcWaccAfterTax(
    wacc.totalDebt,
    wacc.totalEquity,
    ke,
    wacc.costOfDebt,
    wacc.taxRate,
  )
  const preTax = calcPreTaxDiscountRate(waccAt, wacc.taxRate)
  const fromWacc = waccAt > 0
  const effectivePct = fromWacc
    ? (usePreTaxRate ? preTax : waccAt)
    : manualDiscountRate * 100
  return {
    costOfEquity: ke,
    waccAfterTax: waccAt,
    preTaxDiscountRate: preTax,
    effectiveRate: effectivePct / 100,
    fromWacc,
  }
}

export interface I1DcfCalcResult {
  terminalValue: number
  valueInUse: number
  recoverableAmount: number
  discountedCashFlows: number[]
  discountedTerminalValue: number
  discountFactors: number[]
  pvForecast: number
  fairValueLessDisposal: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
}

/**
 * 完整 I1-13 测算（对齐 Excel 公式链）
 */
export function calcI1RecoverableResult(opts: {
  cashFlows: number[]
  manualDiscountRate: number
  growthRate: number
  fvDisposal: I1FairValueDisposal
  waccParams: I1WaccParams
  usePreTaxRate: boolean
  /** 旧数据兼容：无公允明细时直接用该净额 */
  legacyFairValueNet?: number
}): I1DcfCalcResult {
  const fvResolved = resolveI1FairValue(opts.fvDisposal)
  const disposalTotal = calcI1DisposalTotal(opts.fvDisposal)
  const hasDetail = hasFvDetail(opts.fvDisposal)
  const fairValueLessDisposal = hasDetail
    ? fvResolved.value - disposalTotal
    : (Number(opts.legacyFairValueNet) || 0)
  const fairValueSource = hasDetail ? fvResolved.source : (fairValueLessDisposal > 0 ? '手工净额' : '未确定')

  const rateInfo = calcEffectiveDiscountRate(
    opts.waccParams,
    opts.manualDiscountRate,
    opts.usePreTaxRate,
  )
  const r = rateInfo.effectiveRate
  const g = opts.growthRate
  const rateInvalid = r <= 0 || r <= g

  const cashFlows = opts.cashFlows
  const discountFactors: number[] = []
  const discountedCashFlows: number[] = []
  for (let i = 0; i < cashFlows.length; i++) {
    const factor = r > 0 ? 1 / Math.pow(1 + r, i + 1) : 1
    discountFactors.push(factor)
    discountedCashFlows.push(cashFlows[i] * factor)
  }

  const pvForecast = calcDcfPresentValue(cashFlows, r)
  const lastCF = cashFlows.length > 0 ? cashFlows[cashFlows.length - 1] : 0
  const perpetuityCF = lastCF * (1 + g)
  const terminalValue = rateInvalid ? 0 : calcTerminalValue(perpetuityCF, r, g)
  const n = cashFlows.length
  const discountedTerminalValue = !rateInvalid && r > 0 && n > 0
    ? terminalValue / Math.pow(1 + r, n)
    : 0
  const valueInUse = pvForecast + discountedTerminalValue
  const recoverableAmount = calcRecoverableAmount(fairValueLessDisposal, valueInUse)

  let recoverableSource = '未测算'
  if (recoverableAmount > 0) {
    if (fairValueLessDisposal >= valueInUse && fairValueLessDisposal > 0) {
      recoverableSource = '公允净额'
    } else if (valueInUse > 0) {
      recoverableSource = '使用价值(DCF)'
    }
  }

  return {
    terminalValue,
    valueInUse,
    recoverableAmount,
    discountedCashFlows,
    discountedTerminalValue,
    discountFactors,
    pvForecast,
    fairValueLessDisposal,
    fairValueSource,
    disposalTotal,
    recoverableSource,
    costOfEquity: rateInfo.costOfEquity,
    waccAfterTax: rateInfo.waccAfterTax,
    preTaxDiscountRate: rateInfo.preTaxDiscountRate,
    effectiveDiscountRate: r,
    rateInvalid,
  }
}

export function buildI1ConclusionDraft(opts: {
  assetName: string
  fairValueNet: number
  valueInUse: number
  recoverableAmount: number
  recoverableSource: string
  bookValue: number
  effectiveDiscountRate: number
  growthRate: number
  fromWacc: boolean
}): string {
  const impair = Math.max((opts.bookValue || 0) - opts.recoverableAmount, 0)
  return [
    `经测算，无形资产「${opts.assetName || '未命名'}」`,
    `可收回金额为 ${opts.recoverableAmount.toFixed(2)} 元（取自${opts.recoverableSource}：`,
    `公允净额 ${opts.fairValueNet.toFixed(2)} / 使用价值 ${opts.valueInUse.toFixed(2)}）；`,
    opts.bookValue > 0
      ? `账面净值 ${opts.bookValue.toFixed(2)} 元，`
      : '',
    impair > 0.01
      ? `应计提减值 ${impair.toFixed(2)} 元，建议联动回写 I1-12 并关注 I1-11 含减值摊销；`
      : `可收回金额不低于账面净值，本期无需计提减值；`,
    `折现率 ${(opts.effectiveDiscountRate * 100).toFixed(2)}%（${opts.fromWacc ? 'WACC' : '手工'}）、`,
    `永续增长率 ${(opts.growthRate * 100).toFixed(2)}% 已复核□。`,
  ].filter(Boolean).join('')
}

// ─── WACC 口径防呆 / I1-12↔I1-13 一致性 ─────────────────────────────────────

const SYNC_TOLERANCE = 0.01

/** WACC 参数校验警告（百分比口径） */
export function validateWaccParams(wacc: I1WaccParams): string[] {
  const msgs: string[] = []
  const { taxRate, costOfDebt, riskFreeRate, beta, marketReturn, totalDebt, totalEquity } = wacc
  const hasCapital = (totalDebt || 0) + (totalEquity || 0) > 0

  if (taxRate > 0 && (taxRate < 5 || taxRate > 40)) {
    msgs.push(`所得税率 t=${taxRate}% 异常（常见 15%~25%；请确认已按百分比填写）`)
  }
  if (riskFreeRate > 0 && riskFreeRate < 0.5) {
    msgs.push(`无风险利率 Rf=${riskFreeRate} 过小，疑似填成小数（应填百分比，如国债 2.5 表示 2.5%）`)
  } else if (riskFreeRate > 15) {
    msgs.push(`无风险利率 Rf=${riskFreeRate}% 偏高，请复核取值`)
  }
  if (marketReturn > 0 && marketReturn < 1) {
    msgs.push(`市场回报 Rm=${marketReturn} 过小，疑似填成小数（应填如 8 表示 8%，勿填 0.08 或 1.10）`)
  } else if (marketReturn > 0 && marketReturn < 4) {
    msgs.push(`市场回报 Rm=${marketReturn}% 偏低；若误将风险溢价当 Rm，请改为完整市场回报率`)
  } else if (marketReturn > 25) {
    msgs.push(`市场回报 Rm=${marketReturn}% 异常偏高（常见 6%~12%；源表示例 1.10/110% 即为口径错误）`)
  }
  if (costOfDebt > 0 && costOfDebt < 0.5) {
    msgs.push(`债务成本 Kd=${costOfDebt} 过小，疑似填成小数（应填百分比，如 5 表示 5%）`)
  } else if (costOfDebt > 30) {
    msgs.push(`债务成本 Kd=${costOfDebt}% 偏高，请复核`)
  }
  if (beta > 0 && (beta < 0.2 || beta > 3)) {
    msgs.push(`β=${beta} 偏离常见区间(0.5~2.0)，请复核`)
  }
  if (hasCapital && marketReturn > 0 && riskFreeRate > 0 && marketReturn <= riskFreeRate) {
    msgs.push(`市场回报 Rm(${marketReturn}%) ≤ 无风险利率 Rf(${riskFreeRate}%)，权益风险溢价为负，请复核`)
  }
  if (hasCapital && riskFreeRate === 0 && marketReturn === 0 && costOfDebt === 0) {
    msgs.push('已填 D/E 但 Rf/Rm/Kd 均为 0，WACC 无意义，请补全或改用手工折现率')
  }
  return msgs
}

export type I113SyncStatus = 'synced' | 'stale' | 'missing-i13' | 'no-test'

export interface I113SyncCheck {
  name: string
  needTest: boolean
  i12Recoverable: number
  i12FairValue: number
  i12Dcf: number
  i13Recoverable: number
  i13FairValue: number
  i13Dcf: number
  status: I113SyncStatus
  message: string
}

/**
 * 分类 I1-12 与 I1-13 回写一致性（对齐 H8 sync）
 */
export function classifyI113SyncStatus(
  i12: {
    needTest: boolean
    fairValueLessDisposal: number
    dcfValue: number
    recoverableAmount: number
  },
  i13: {
    fairValueLessDisposal: number
    valueInUse: number
    recoverableAmount: number
  } | null,
): Pick<I113SyncCheck, 'status' | 'message'> {
  if (!i12.needTest) {
    return { status: 'no-test', message: '无须测试' }
  }
  if (!i13) {
    return { status: 'missing-i13', message: 'I1-13 尚无同名测算组' }
  }
  if (i13.recoverableAmount <= 0 && i12.recoverableAmount <= 0) {
    return { status: 'missing-i13', message: '须测试但可收回金额尚未测算' }
  }
  const fvOk = Math.abs(i12.fairValueLessDisposal - i13.fairValueLessDisposal) < SYNC_TOLERANCE
  const dcfOk = Math.abs(i12.dcfValue - i13.valueInUse) < SYNC_TOLERANCE
  const recOk = Math.abs(i12.recoverableAmount - i13.recoverableAmount) < SYNC_TOLERANCE
  if (fvOk && dcfOk && recOk) {
    return { status: 'synced', message: '已与 I1-13 一致' }
  }
  const parts: string[] = []
  if (!fvOk) parts.push(`③差 ${Math.abs(i12.fairValueLessDisposal - i13.fairValueLessDisposal).toFixed(2)}`)
  if (!dcfOk) parts.push(`④差 ${Math.abs(i12.dcfValue - i13.valueInUse).toFixed(2)}`)
  if (!recOk) parts.push(`⑤差 ${Math.abs(i12.recoverableAmount - i13.recoverableAmount).toFixed(2)}`)
  return { status: 'stale', message: `与 I1-13 不一致（${parts.join('，')}），请联动回写` }
}

export function buildI113SyncChecks(
  impairmentRows: Array<{
    name: string
    needTest: boolean
    fairValueLessDisposal: number
    dcfValue: number
    recoverableAmount: number
  }>,
  recoverableRows: Array<{
    name: string
    fairValueLessDisposal: number
    valueInUse: number
    recoverableAmount: number
  }>,
): I113SyncCheck[] {
  const byName = new Map<string, (typeof recoverableRows)[0]>()
  for (const r of recoverableRows) {
    const key = (r.name || '').trim()
    if (key) byName.set(key, r)
  }

  const out: I113SyncCheck[] = []
  const seen = new Set<string>()

  for (const row of impairmentRows) {
    const name = (row.name || '').trim()
    if (!name) continue
    seen.add(name)
    const i13 = byName.get(name) ?? null
    const { status, message } = classifyI113SyncStatus(row, i13)
    out.push({
      name,
      needTest: row.needTest,
      i12Recoverable: row.recoverableAmount,
      i12FairValue: row.fairValueLessDisposal,
      i12Dcf: row.dcfValue,
      i13Recoverable: i13?.recoverableAmount ?? 0,
      i13FairValue: i13?.fairValueLessDisposal ?? 0,
      i13Dcf: i13?.valueInUse ?? 0,
      status,
      message,
    })
  }

  // I1-13 有、I1-12 无的孤立测算
  for (const r of recoverableRows) {
    const name = (r.name || '').trim()
    if (!name || seen.has(name)) continue
    out.push({
      name,
      needTest: false,
      i12Recoverable: 0,
      i12FairValue: 0,
      i12Dcf: 0,
      i13Recoverable: r.recoverableAmount,
      i13FairValue: r.fairValueLessDisposal,
      i13Dcf: r.valueInUse,
      status: 'stale',
      message: 'I1-13 有测算但 I1-12 无同名行',
    })
  }

  return out
}

/** 供 H4WaccParams 兼容调用 */
export type { H4WaccParams }
