import { parseNum } from '../../composables/useG7SubFormulaEngine'

export const PACKAGE_CRITERIA = [
  { key: 'judgmentSimultaneous', label: '交易同时或在考虑彼此影响的情况下订立' },
  { key: 'judgmentCompleteResult', label: '各次交易整体才能达成一项完整的商业结果' },
  { key: 'judgmentInterdependent', label: '一项交易的发生取决于其他至少一项交易' },
  { key: 'judgmentEconomicTogether', label: '单项交易不经济，但与其他交易一并考虑时经济' },
] as const

export type PackageJudgmentKey = (typeof PACKAGE_CRITERIA)[number]['key']
export type JudgmentAnswer = 'yes' | 'no' | 'na' | ''

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
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits
  return Math.round((value + Number.EPSILON) * factor) / factor
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
    auditConclusion: '',
  }
}

export function migratePackageRow(raw: Record<string, any>, seq: number): G7DisposalPackageRow {
  const row = { ...createPackageRow(seq), ...raw, seq }
  row.id = String(raw.id || `g7-12-saved-${seq}`)
  row.disposalRatio = parseNum(raw.disposalRatio ?? raw.transactionShareChange ?? raw.shareholdingChange ?? raw.shareChange)
  row.remainingShareholdingRatio = parseNum(raw.remainingShareholdingRatio)
  row.individualBookValue = parseNum(raw.individualBookValue ?? raw.lossDateBookValue ?? raw.bookValueAtLoss)
  row.residualFairValue = parseNum(raw.residualFairValue ?? raw.lossDateResidualFV ?? raw.remainingInvestmentFV ?? raw.remainingFV)
  row.packageJudgmentBasis = String(raw.packageJudgmentBasis ?? raw.packageBasis ?? '')
  return row
}

export function calculatePackageRow(row: G7DisposalPackageRow): G7PackageCalculated {
  const originalRatio = parseNum(row.originalShareholdingRatio)
  const disposalRatio = Math.abs(parseNum(row.disposalRatio))
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
  const priceShareDifference = round(parseNum(row.transactionPrice) - consolidatedNetAssetShare)
  const consolidatedRemeasurementGain = round(parseNum(row.residualFairValue) - residualBookValue)
  const consolidatedGain = round(
    parseNum(row.transactionPrice)
      + parseNum(row.residualFairValue)
      - parseNum(row.consolidatedNetAssets)
      - parseNum(row.goodwill)
      + parseNum(row.consolidatedRecyclableOci)
      + parseNum(row.priorStepDifference),
  )
  const equityRatio = parseNum(row.equityMethodRatio || row.remainingShareholdingRatio)

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
    openingRetainedEarnings: round(equityRatio * parseNum(row.preDisposalProfit) * 0.9),
    surplusReserve: round(equityRatio * parseNum(row.preDisposalProfit) * 0.1),
    investmentIncome: round(equityRatio * parseNum(row.currentProfit)),
    longTermInvestmentOci: round(equityRatio * parseNum(row.otherComprehensiveIncome)),
    longTermInvestmentOtherChanges: round(equityRatio * parseNum(row.otherEquityChanges)),
  }
}

export function validatePackageRows(rows: G7DisposalPackageRow[]): string[] {
  const errors: string[] = []
  rows.forEach((row, index) => {
    const label = row.investeeName || `第${index + 1}行`
    if (!row.investeeName && !row.transactionPrice && !row.individualBookValue) return
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
    }
  })
  return errors
}
