import { parseNum } from '../../composables/useG7SubFormulaEngine'

export const PACKAGE_CRITERIA = [
  { key: 'judgmentSimultaneous', label: '交易同时或在考虑彼此影响的情况下订立' },
  { key: 'judgmentCompleteResult', label: '各次交易整体才能达成一项完整的商业结果' },
  { key: 'judgmentInterdependent', label: '一项交易的发生取决于其他至少一项交易' },
  { key: 'judgmentEconomicTogether', label: '单项交易不经济，但与其他交易一并考虑时经济' },
] as const

export type PackageJudgmentKey = (typeof PACKAGE_CRITERIA)[number]['key']
export type JudgmentAnswer = 'yes' | 'no' | 'na' | ''

/** 一揽子分步 — 各次交易 */
export interface G7PackageStep {
  id: string
  seq: number
  stepDate: string
  consideration: number
  shareChange: number
  note: string
}

export interface G7DisposalPackageRow {
  id: string
  seq: number
  investeeName: string
  registeredPlace: string
  businessNature: string
  originalShareholdingRatio: number
  votingRatio: number
  disposalReason: string
  judgmentSimultaneous: JudgmentAnswer
  judgmentCompleteResult: JudgmentAnswer
  judgmentInterdependent: JudgmentAnswer
  judgmentEconomicTogether: JudgmentAnswer
  packageJudgmentConclusion: JudgmentAnswer
  packageJudgmentBasis: string
  /** 各次交易明细；有值时累计回写 transactionPrice / disposalRatio */
  steps: G7PackageStep[]
  transactionDate: string
  transactionPrice: number
  disposalRatio: number
  remainingShareholdingRatio: number
  remainingInterestType: string
  disposalMethod: string
  lossOfControlDate: string
  lossOfControlBasis: string
  evidenceObtained: string
  indexRef: string
  individualBookValue: number
  residualFairValue: number
  associateJointVentureRecyclableOci: number
  financialAssetRecyclableOci: number
  nonRecyclableOci: number
  consolidatedNetAssets: number
  goodwill: number
  residualFairValueMethod: string
  consolidatedRecyclableOci: number
  priorStepDifference: number
  equityMethodRatio: number
  preDisposalProfit: number
  currentProfit: number
  otherComprehensiveIncome: number
  otherEquityChanges: number
  /** 盈余公积计提比例，默认 0.1（可按章程调整） */
  surplusReserveRate: number
  auditConclusion: string
}

export interface G7PackageCalculated {
  remainingRatio: number
  disposedBookValue: number
  residualBookValue: number
  remeasurementGain: number
  individualGain: number
  transferToEquity: number
  consolidatedNetAssetShare: number
  priceShareDifference: number
  consolidatedRemeasurementGain: number
  consolidatedGain: number
  openingRetainedEarnings: number
  surplusReserve: number
  investmentIncome: number
  longTermInvestmentOci: number
  longTermInvestmentOtherChanges: number
  cumulativePrice: number
  cumulativeShareChange: number
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits
  return Math.round((value + Number.EPSILON) * factor) / factor
}

export function createPackageStep(seq: number): G7PackageStep {
  return {
    id: `g7-12-step-${Date.now()}-${seq}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    stepDate: '',
    consideration: 0,
    shareChange: 0,
    note: '',
  }
}

export function createPackageRow(seq: number): G7DisposalPackageRow {
  return {
    id: `g7-12-${Date.now()}-${seq}`,
    seq,
    investeeName: '',
    registeredPlace: '',
    businessNature: '',
    originalShareholdingRatio: 0,
    votingRatio: 0,
    disposalReason: '',
    judgmentSimultaneous: '',
    judgmentCompleteResult: '',
    judgmentInterdependent: '',
    judgmentEconomicTogether: '',
    packageJudgmentConclusion: '',
    packageJudgmentBasis: '',
    steps: [],
    transactionDate: '',
    transactionPrice: 0,
    disposalRatio: 0,
    remainingShareholdingRatio: 0,
    remainingInterestType: '',
    disposalMethod: '',
    lossOfControlDate: '',
    lossOfControlBasis: '',
    evidenceObtained: '',
    indexRef: '',
    individualBookValue: 0,
    residualFairValue: 0,
    associateJointVentureRecyclableOci: 0,
    financialAssetRecyclableOci: 0,
    nonRecyclableOci: 0,
    consolidatedNetAssets: 0,
    goodwill: 0,
    residualFairValueMethod: '',
    consolidatedRecyclableOci: 0,
    priorStepDifference: 0,
    equityMethodRatio: 0,
    preDisposalProfit: 0,
    currentProfit: 0,
    otherComprehensiveIncome: 0,
    otherEquityChanges: 0,
    surplusReserveRate: 0.1,
    auditConclusion: '',
  }
}

/** 各次交易累计 → 回写主表对价/处置比例 */
export function syncRowFromSteps(row: G7DisposalPackageRow): void {
  const steps = Array.isArray(row.steps) ? row.steps : []
  if (!steps.length) return
  const cumulativePrice = round(steps.reduce((s, step) => s + parseNum(step.consideration), 0))
  const cumulativeShare = round(
    steps.reduce((s, step) => s + Math.abs(parseNum(step.shareChange)), 0),
    6,
  )
  row.transactionPrice = cumulativePrice
  row.disposalRatio = cumulativeShare
  const dated = [...steps].filter(s => s.stepDate).sort((a, b) => a.stepDate.localeCompare(b.stepDate))
  if (dated.length) {
    if (!row.transactionDate) row.transactionDate = dated[0].stepDate
    if (!row.lossOfControlDate) row.lossOfControlDate = dated[dated.length - 1].stepDate
  }
  row.remainingShareholdingRatio = round(
    Math.max(0, parseNum(row.originalShareholdingRatio) - cumulativeShare),
    6,
  )
  if (!row.equityMethodRatio) row.equityMethodRatio = row.remainingShareholdingRatio
}

export function migratePackageRow(raw: Record<string, any>, seq: number): G7DisposalPackageRow {
  const row = { ...createPackageRow(seq), ...raw, seq }
  row.id = String(raw.id || `g7-12-saved-${seq}`)
  row.disposalRatio = parseNum(raw.disposalRatio ?? raw.transactionShareChange ?? raw.shareholdingChange ?? raw.shareChange)
  row.remainingShareholdingRatio = parseNum(raw.remainingShareholdingRatio)
  row.individualBookValue = parseNum(raw.individualBookValue ?? raw.lossDateBookValue ?? raw.bookValueAtLoss)
  row.residualFairValue = parseNum(raw.residualFairValue ?? raw.lossDateResidualFV ?? raw.remainingInvestmentFV ?? raw.remainingFV)
  row.packageJudgmentBasis = String(raw.packageJudgmentBasis ?? raw.packageBasis ?? '')
  row.surplusReserveRate = parseNum(raw.surplusReserveRate) || 0.1
  const rawSteps = Array.isArray(raw.steps) ? raw.steps : []
  row.steps = rawSteps.map((s: any, i: number) => ({
    ...createPackageStep(i + 1),
    ...s,
    id: String(s?.id || `g7-12-step-saved-${seq}-${i + 1}`),
    seq: i + 1,
    consideration: parseNum(s?.consideration),
    shareChange: parseNum(s?.shareChange),
    stepDate: String(s?.stepDate ?? ''),
    note: String(s?.note ?? ''),
  }))
  if (row.steps.length) syncRowFromSteps(row)
  return row
}

export function calculatePackageRow(row: G7DisposalPackageRow): G7PackageCalculated {
  if (Array.isArray(row.steps) && row.steps.length) {
    // 只读累计展示；不在纯函数内 mutate
  }
  const steps = Array.isArray(row.steps) ? row.steps : []
  const cumulativePrice = steps.length
    ? round(steps.reduce((s, step) => s + parseNum(step.consideration), 0))
    : parseNum(row.transactionPrice)
  const cumulativeShareChange = steps.length
    ? round(steps.reduce((s, step) => s + Math.abs(parseNum(step.shareChange)), 0), 6)
    : Math.abs(parseNum(row.disposalRatio))

  const originalRatio = parseNum(row.originalShareholdingRatio)
  const disposalRatio = cumulativeShareChange
  const transactionPrice = cumulativePrice
  const remainingRatio = round(Math.max(0, originalRatio - disposalRatio), 6)
  const ratioOfOriginal = originalRatio === 0 ? 0 : disposalRatio / originalRatio
  const disposedBookValue = round(parseNum(row.individualBookValue) * ratioOfOriginal)
  const residualBookValue = round(parseNum(row.individualBookValue) - disposedBookValue)
  const remeasurementGain = round(parseNum(row.residualFairValue) - residualBookValue)
  const recyclableOci = round(
    parseNum(row.associateJointVentureRecyclableOci) * ratioOfOriginal
      + parseNum(row.financialAssetRecyclableOci),
  )
  const individualGain = round(remeasurementGain + recyclableOci)
  const transferToEquity = round(parseNum(row.nonRecyclableOci) * ratioOfOriginal)
  const consolidatedNetAssetShare = round(parseNum(row.consolidatedNetAssets) * ratioOfOriginal)
  const priceShareDifference = round(transactionPrice - consolidatedNetAssetShare)
  const consolidatedRemeasurementGain = round(parseNum(row.residualFairValue) - residualBookValue)
  const consolidatedGain = round(
    transactionPrice
      + parseNum(row.residualFairValue)
      - parseNum(row.consolidatedNetAssets)
      - parseNum(row.goodwill)
      + parseNum(row.consolidatedRecyclableOci)
      + parseNum(row.priorStepDifference),
  )
  const equityRatio = parseNum(row.equityMethodRatio || row.remainingShareholdingRatio)
  let surplusRate = parseNum(row.surplusReserveRate)
  if (surplusRate <= 0 || surplusRate >= 1) surplusRate = 0.1

  return {
    remainingRatio,
    disposedBookValue,
    residualBookValue,
    remeasurementGain,
    individualGain,
    transferToEquity,
    consolidatedNetAssetShare,
    priceShareDifference,
    consolidatedRemeasurementGain,
    consolidatedGain,
    openingRetainedEarnings: round(equityRatio * parseNum(row.preDisposalProfit) * (1 - surplusRate)),
    surplusReserve: round(equityRatio * parseNum(row.preDisposalProfit) * surplusRate),
    investmentIncome: round(equityRatio * parseNum(row.currentProfit)),
    longTermInvestmentOci: round(equityRatio * parseNum(row.otherComprehensiveIncome)),
    longTermInvestmentOtherChanges: round(equityRatio * parseNum(row.otherEquityChanges)),
    cumulativePrice,
    cumulativeShareChange,
  }
}

export function validatePackageRows(rows: G7DisposalPackageRow[]): string[] {
  const errors: string[] = []
  rows.forEach((row, index) => {
    const label = row.investeeName || `第${index + 1}行`
    if (!row.investeeName && !row.transactionPrice && !row.individualBookValue && !(row.steps?.length)) return
    if (!row.packageJudgmentConclusion) errors.push(`${label}：未形成一揽子交易判断结论`)
    if (!row.packageJudgmentBasis.trim()) errors.push(`${label}：未记录一揽子交易判断依据`)
    if (!row.lossOfControlDate || !row.lossOfControlBasis.trim()) errors.push(`${label}：丧失控制权时点或依据不完整`)
    if (!row.evidenceObtained.trim()) errors.push(`${label}：未记录取得的查验资料`)
    const calculated = calculatePackageRow(row)
    if (
      row.remainingShareholdingRatio !== 0
      && Math.abs(parseNum(row.remainingShareholdingRatio) - calculated.remainingRatio) > 0.0001
    ) {
      errors.push(`${label}：剩余持股比例与原比例减处置比例不一致`)
    }
    if (row.packageJudgmentConclusion === 'yes') {
      const yesCount = PACKAGE_CRITERIA.filter((item) => row[item.key] === 'yes').length
      if (yesCount === 0) errors.push(`${label}：结论为一揽子交易，但四项判断均未选择“是”`)
      if (!(row.steps?.length) && !row.priorStepDifference && parseNum(row.transactionPrice) > 0) {
        // soft hint via warning-style message（仍计入待完善）
        errors.push(`${label}：一揽子交易建议录入「各次交易明细」，或填写前序交易差额`)
      }
    }
  })
  return errors
}
