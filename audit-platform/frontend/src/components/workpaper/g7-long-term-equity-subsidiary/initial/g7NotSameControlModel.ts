import { useDecimalCalc } from '@/composables/useDecimalCalc'
import {
  extractSubsidiaryNamesFromG72,
  extractSubsidiaryNamesFromG74,
  type G7YesNo,
} from './g7SameControlModel'

export { extractSubsidiaryNamesFromG72, extractSubsidiaryNamesFromG74 }
export type { G7YesNo }

const moneyCalc = useDecimalCalc({ dp: 2 })
const ratioCalc = useDecimalCalc({ dp: 6 })

export type G7NotSameControlAuditConclusion = '' | '无差异' | '差异可接受' | '差异需调整'

/**
 * 1、合并方式取得（对齐源底稿 G7-9 第7—22行）
 * ①可辨认净资产FV ②持股比例 ③对价FV合计 ④原持股购买日FV
 * ⑤对价账面价值合计 ⑥初始成本=③+④ ⑦损益损益=③−⑤ ⑧商誉=⑥−①×②
 */
export interface G7NotSameControlMergerRow {
  id: string
  section: 'merger'
  seq: number
  investeeName: string
  acquisitionDate: string
  acquisitionDateEvidenceRef: string
  /** ① 被购买方可辨认净资产公允价值 */
  acquireeIdentifiableNetAssetsFV: number | null
  /** ② 合并后出资比例 */
  ownershipRatio: number | null
  /** ③ 对价FV明细 */
  cashConsideration: number | null
  nonCashAssetFV: number | null
  debtFV: number | null
  equitySecuritiesFV: number | null
  contingentConsiderationFV: number | null
  /** ③ 合计（公式） */
  totalConsiderationFV: number
  /** ④ 购买日之前持有的股权于购买日的公允价值 */
  priorHoldingFV: number | null
  /** ⑤ 付出对价的账面价值合计 */
  considerationBookValue: number | null
  /**
   * 直接相关中介费用（提示区A）：计入当期损益，不构成合并成本
   */
  acquisitionCostsExpensed: number | null
  /** ⑥=③+④ 个别/合并初始投资成本 */
  initialInvestmentCost: number
  /** ⑦=③−⑤ 付出对价FV与账面差额 → 当期损益 */
  considerationGainLoss: number
  /** ①×② 享有份额 */
  shareOfFV: number
  /** CAS20：少数股东权益按可辨认净资产FV份额 */
  nonControllingInterestShare: number
  /** ⑧=⑥−①×② 商誉/廉价购买利得 */
  goodwill: number
  /** 廉价购买利得时：是否已复核计量无误 */
  bargainPurchaseReviewed: G7YesNo
  bargainPurchaseReviewNote: string
  considerationEvidenceRef: string
  valuationReportRef: string
  indexRef: string
  auditConclusion: G7NotSameControlAuditConclusion
}

/**
 * 2、分步实现非同控（对齐源底稿第24—34行，不构成一揽子交易）
 * 每笔：①比例 ②对价 ③交易时NA FV ④=①×③ ⑤=②−④
 * 每笔：⑥权益法OCI等；公司汇总⑦=累计②+累计⑥
 */
export interface G7NotSameControlStepRow {
  id: string
  section: 'step'
  companyId: string
  companyName: string
  seq: number
  transactionNo: number
  transactionDate: string
  purchaseRatio: number | null
  considerationFV: number | null
  /** 每笔交易发生时被投资方可辨认净资产公允价值③ */
  netAssetsFVAtTxn: number | null
  /** ④=①×③（公式） */
  shareOfFVAtTxn: number
  /** ⑤=②−④（公式） */
  goodwillAtTxn: number
  /** 每笔：权益法OCI/损益调整/其他变动等⑥ */
  priorEquityMethodAdjustments: number | null
  /** 标记新口径为逐笔⑥；缺失时按旧版公司级字段迁移 */
  adjustmentScope: 'transaction'
  /** 公司级：原持股账面价值（备查，个别报表） */
  priorHoldingBookValue: number | null
  /** 公司级：原持股购买日FV（合并层重估备查） */
  priorHoldingFV: number | null
  isPackageDeal: G7YesNo
  notPackageBasis: string
  acquisitionDateEvidenceRef: string
  considerationEvidenceRef: string
  valuationReportRef: string
  indexRef: string
}

export interface G7NotSameControlReverseRow {
  id: string
  section: 'reverse'
  seq: number
  transactionContent: string
  accountingAcquirer: string
  acquirerShareholders: string
  accountingAcquiree: string
  acquireeOriginalShareholders: string
  reversePurchaseBasis: string
  /** 是否构成业务 */
  constitutesBusiness: G7YesNo
  businessDeterminationBasis: string
  indexRef: string
}

export type G7NotSameControlStoredRow =
  | G7NotSameControlMergerRow
  | G7NotSameControlStepRow
  | G7NotSameControlReverseRow

export interface G7NotSameControlStepSummary {
  companyId: string
  companyName: string
  cumulativeRatio: number
  cumulativeConsiderationFV: number
  cumulativeShareOfFV: number
  cumulativeTxnGoodwill: number
  priorEquityMethodAdjustments: number
  priorHoldingBookValue: number
  priorHoldingFV: number
  remeasurementGain: number
  /** ⑦=累计②+⑥ 个别报表初始成本 */
  parentInitialCost: number
  isPackageDeal: G7YesNo
  notPackageBasis: string
  acquisitionDateEvidenceRef: string
  considerationEvidenceRef: string
  valuationReportRef: string
  indexRef: string
}

export interface G7NotSameControlIssue {
  severity: 'error' | 'warning'
  rowId?: string
  message: string
}

export interface G7NotSameControlValidationContext {
  notSameControlInvestees?: string[]
  detailInvestees?: string[]
  basicInfoInvestees?: string[]
}

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function nullableNumber(value: unknown): number | null {
  if (value === '' || value == null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function amount(value: unknown): number {
  return nullableNumber(value) ?? 0
}

function asYesNo(value: unknown): G7YesNo {
  return value === '是' || value === '否' ? value : ''
}

export function describeGoodwill(goodwill: number): string {
  if (Math.abs(goodwill) < 0.005) return '无商誉/无廉价购买利得'
  return goodwill > 0
    ? '确认商誉（⑧＞0）'
    : '廉价购买利得（⑧＜0），须复核计量后计入营业外收入'
}

export function createNotSameControlMergerRow(
  seq: number,
  investeeName = '',
): G7NotSameControlMergerRow {
  return recalcNotSameControlMergerRow({
    id: uid('g7-9-merger'),
    section: 'merger',
    seq,
    investeeName,
    acquisitionDate: '',
    acquisitionDateEvidenceRef: '',
    acquireeIdentifiableNetAssetsFV: null,
    ownershipRatio: null,
    cashConsideration: null,
    nonCashAssetFV: null,
    debtFV: null,
    equitySecuritiesFV: null,
    contingentConsiderationFV: null,
    totalConsiderationFV: 0,
    priorHoldingFV: null,
    considerationBookValue: null,
    acquisitionCostsExpensed: null,
    initialInvestmentCost: 0,
    considerationGainLoss: 0,
    shareOfFV: 0,
    nonControllingInterestShare: 0,
    goodwill: 0,
    bargainPurchaseReviewed: '',
    bargainPurchaseReviewNote: '',
    considerationEvidenceRef: '',
    valuationReportRef: '',
    indexRef: '',
    auditConclusion: '',
  })
}

/** 对齐源底稿：③合计；⑥=③+④；⑦=③−⑤；⑧=⑥−①×② */
export function recalcNotSameControlMergerRow(
  row: G7NotSameControlMergerRow,
): G7NotSameControlMergerRow {
  row.totalConsiderationFV = Number(moneyCalc.sum(
    amount(row.cashConsideration),
    amount(row.nonCashAssetFV),
    amount(row.debtFV),
    amount(row.equitySecuritiesFV),
    amount(row.contingentConsiderationFV),
  ))
  row.initialInvestmentCost = Number(moneyCalc.sum(
    row.totalConsiderationFV,
    amount(row.priorHoldingFV),
  ))
  row.considerationGainLoss = Number(moneyCalc.sub(
    row.totalConsiderationFV,
    amount(row.considerationBookValue),
  ))
  row.shareOfFV = Number(moneyCalc.mul(
    amount(row.acquireeIdentifiableNetAssetsFV),
    amount(row.ownershipRatio),
  ))
  row.nonControllingInterestShare = Number(moneyCalc.mul(
    amount(row.acquireeIdentifiableNetAssetsFV),
    Math.max(0, 1 - amount(row.ownershipRatio)),
  ))
  row.goodwill = Number(moneyCalc.sub(row.initialInvestmentCost, row.shareOfFV))
  return row
}

export function createNotSameControlStepRow(
  companyId: string,
  companyName: string,
  seq: number,
): G7NotSameControlStepRow {
  return recalcNotSameControlStepRow({
    id: uid('g7-9-step'),
    section: 'step',
    companyId,
    companyName,
    seq,
    transactionNo: seq,
    transactionDate: '',
    purchaseRatio: null,
    considerationFV: null,
    netAssetsFVAtTxn: null,
    shareOfFVAtTxn: 0,
    goodwillAtTxn: 0,
    priorEquityMethodAdjustments: null,
    adjustmentScope: 'transaction',
    priorHoldingBookValue: null,
    priorHoldingFV: null,
    isPackageDeal: '',
    notPackageBasis: '',
    acquisitionDateEvidenceRef: '',
    considerationEvidenceRef: '',
    valuationReportRef: '',
    indexRef: '',
  })
}

export function recalcNotSameControlStepRow(
  row: G7NotSameControlStepRow,
): G7NotSameControlStepRow {
  row.shareOfFVAtTxn = Number(moneyCalc.mul(
    amount(row.purchaseRatio),
    amount(row.netAssetsFVAtTxn),
  ))
  row.goodwillAtTxn = Number(moneyCalc.sub(
    amount(row.considerationFV),
    row.shareOfFVAtTxn,
  ))
  return row
}

export function createNotSameControlReverseRow(seq: number): G7NotSameControlReverseRow {
  return {
    id: uid('g7-9-reverse'),
    section: 'reverse',
    seq,
    transactionContent: '',
    accountingAcquirer: '',
    acquirerShareholders: '',
    accountingAcquiree: '',
    acquireeOriginalShareholders: '',
    reversePurchaseBasis: '',
    constitutesBusiness: '',
    businessDeterminationBasis: '',
    indexRef: '',
  }
}

export function summarizeNotSameControlSteps(
  rows: G7NotSameControlStepRow[],
): G7NotSameControlStepSummary[] {
  const groups = new Map<string, G7NotSameControlStepRow[]>()
  for (const row of rows) {
    const key = row.companyId || row.companyName
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(row)
  }
  const summaries: G7NotSameControlStepSummary[] = []
  for (const [companyId, group] of groups) {
    const ordered = [...group].sort((a, b) => a.transactionNo - b.transactionNo || a.seq - b.seq)
    ordered.forEach(recalcNotSameControlStepRow)
    const last = ordered[ordered.length - 1]
    const cumulativeRatio = Number(ratioCalc.sum(...ordered.map(row => amount(row.purchaseRatio))))
    const cumulativeConsiderationFV = Number(
      moneyCalc.sum(...ordered.map(row => amount(row.considerationFV))),
    )
    const cumulativeShareOfFV = Number(
      moneyCalc.sum(...ordered.map(row => amount(row.shareOfFVAtTxn))),
    )
    const cumulativeTxnGoodwill = Number(
      moneyCalc.sum(...ordered.map(row => amount(row.goodwillAtTxn))),
    )
    const priorEquityMethodAdjustments = Number(
      moneyCalc.sum(...ordered.map(row => amount(row.priorEquityMethodAdjustments))),
    )
    const priorHoldingBookValue = amount(
      ordered.find(row => row.priorHoldingBookValue != null)?.priorHoldingBookValue,
    )
    const priorHoldingFV = amount(
      ordered.find(row => row.priorHoldingFV != null)?.priorHoldingFV,
    )
    const remeasurementGain = Number(moneyCalc.sub(priorHoldingFV, priorHoldingBookValue))
    // 源底稿⑦=累计②+⑥
    const parentInitialCost = Number(moneyCalc.sum(
      cumulativeConsiderationFV,
      priorEquityMethodAdjustments,
    ))
    const isPackageDeal = asYesNo(ordered.find(row => row.isPackageDeal)?.isPackageDeal)
    summaries.push({
      companyId,
      companyName: last?.companyName ?? '',
      cumulativeRatio,
      cumulativeConsiderationFV,
      cumulativeShareOfFV,
      cumulativeTxnGoodwill,
      priorEquityMethodAdjustments,
      priorHoldingBookValue,
      priorHoldingFV,
      remeasurementGain,
      parentInitialCost,
      isPackageDeal,
      notPackageBasis: ordered.find(row => row.notPackageBasis.trim())?.notPackageBasis ?? '',
      acquisitionDateEvidenceRef: ordered.find(row => row.acquisitionDateEvidenceRef.trim())?.acquisitionDateEvidenceRef ?? '',
      considerationEvidenceRef: ordered.find(row => row.considerationEvidenceRef.trim())?.considerationEvidenceRef ?? '',
      valuationReportRef: ordered.find(row => row.valuationReportRef.trim())?.valuationReportRef ?? '',
      indexRef: ordered.find(row => row.indexRef.trim())?.indexRef ?? '',
    })
  }
  return summaries
}

function migrateLegacyFlatRow(raw: Record<string, any>, index: number): G7NotSameControlMergerRow {
  const row = createNotSameControlMergerRow(
    Number(raw.seq || index + 1),
    String(raw.investeeName || raw.investee_name || ''),
  )
  Object.assign(row, {
    acquisitionDate: String(raw.acquisitionDate || ''),
    acquisitionDateEvidenceRef: String(raw.acquisitionDateEvidenceRef ?? ''),
    cashConsideration: nullableNumber(raw.cashConsideration ?? raw.consideration),
    nonCashAssetFV: nullableNumber(raw.nonCashAssetFV),
    debtFV: nullableNumber(raw.debtFV),
    equitySecuritiesFV: nullableNumber(raw.equitySecuritiesFV),
    contingentConsiderationFV: nullableNumber(raw.contingentConsiderationFV),
    priorHoldingFV: nullableNumber(raw.priorHoldingFV),
    considerationBookValue: nullableNumber(raw.considerationBookValue),
    acquisitionCostsExpensed: nullableNumber(raw.acquisitionCostsExpensed ?? raw.directFees),
    acquireeIdentifiableNetAssetsFV: nullableNumber(
      raw.acquireeIdentifiableNetAssetsFV ?? raw.acquireeNetAssetsFV,
    ),
    ownershipRatio: nullableNumber(raw.ownershipRatio ?? raw.shareholdingRatio),
    bargainPurchaseReviewed: asYesNo(raw.bargainPurchaseReviewed),
    bargainPurchaseReviewNote: String(raw.bargainPurchaseReviewNote ?? ''),
    considerationEvidenceRef: String(raw.considerationEvidenceRef ?? ''),
    valuationReportRef: String(raw.valuationReportRef ?? ''),
    indexRef: String(raw.indexRef ?? ''),
    auditConclusion: raw.auditConclusion ?? '',
  })
  return recalcNotSameControlMergerRow(row)
}

export function normalizeNotSameControlRows(payload: unknown): G7NotSameControlStoredRow[] {
  const rows: Record<string, any>[] = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as any)?.rows)
      ? (payload as any).rows
      : []
  const normalized: G7NotSameControlStoredRow[] = []
  const generatedCompanyIds = new Map<string, string>()
  const legacyStepGroups = new Map<string, G7NotSameControlStepRow[]>()
  for (let index = 0; index < rows.length; index += 1) {
    const raw = rows[index]
    if (raw.section === 'step') {
      const companyName = String(raw.companyName ?? raw.investeeName ?? '').trim()
      const suppliedCompanyId = String(raw.companyId ?? '').trim()
      const companyKey = suppliedCompanyId || companyName || `row-${index + 1}`
      if (!generatedCompanyIds.has(companyKey)) {
        generatedCompanyIds.set(companyKey, suppliedCompanyId || uid('step-company'))
      }
      const companyId = generatedCompanyIds.get(companyKey)!
      const step = {
        ...createNotSameControlStepRow(
          companyId,
          companyName,
          Number(raw.seq || index + 1),
        ),
        ...raw,
        section: 'step' as const,
        companyId,
        companyName,
        id: String(raw.id || uid('g7-9-step')),
        transactionNo: Number(raw.transactionNo || raw.seq || index + 1),
        transactionDate: String(raw.transactionDate ?? ''),
        purchaseRatio: nullableNumber(raw.purchaseRatio),
        considerationFV: nullableNumber(raw.considerationFV ?? raw.consideration),
        netAssetsFVAtTxn: nullableNumber(
          raw.netAssetsFVAtTxn ?? raw.netAssetsBookValueAtTxn ?? raw.netAssetsBookValue,
        ),
        priorEquityMethodAdjustments: nullableNumber(
          raw.priorEquityMethodAdjustments ?? raw.priorOCIReclassify,
        ),
        adjustmentScope: 'transaction' as const,
        priorHoldingBookValue: nullableNumber(raw.priorHoldingBookValue),
        priorHoldingFV: nullableNumber(raw.priorHoldingFV),
        isPackageDeal: asYesNo(raw.isPackageDeal),
        notPackageBasis: String(raw.notPackageBasis ?? ''),
        acquisitionDateEvidenceRef: String(raw.acquisitionDateEvidenceRef ?? ''),
        considerationEvidenceRef: String(raw.considerationEvidenceRef ?? ''),
        valuationReportRef: String(raw.valuationReportRef ?? ''),
        indexRef: String(raw.indexRef ?? ''),
      }
      const normalizedStep = recalcNotSameControlStepRow(step)
      normalized.push(normalizedStep)
      if (raw.adjustmentScope !== 'transaction') {
        if (!legacyStepGroups.has(companyId)) legacyStepGroups.set(companyId, [])
        legacyStepGroups.get(companyId)!.push(normalizedStep)
      }
    } else if (raw.section === 'reverse') {
      normalized.push({
        ...createNotSameControlReverseRow(Number(raw.seq || index + 1)),
        ...raw,
        section: 'reverse',
        transactionContent: String(raw.transactionContent ?? ''),
        accountingAcquirer: String(raw.accountingAcquirer ?? ''),
        acquirerShareholders: String(raw.acquirerShareholders ?? ''),
        accountingAcquiree: String(raw.accountingAcquiree ?? ''),
        acquireeOriginalShareholders: String(raw.acquireeOriginalShareholders ?? ''),
        reversePurchaseBasis: String(raw.reversePurchaseBasis ?? ''),
        constitutesBusiness: asYesNo(raw.constitutesBusiness),
        businessDeterminationBasis: String(raw.businessDeterminationBasis ?? ''),
        indexRef: String(raw.indexRef ?? ''),
      })
    } else {
      normalized.push(migrateLegacyFlatRow(raw, index))
    }
  }
  // 旧版把⑥作为公司级字段复制到每一行；首次加载时只保留一份，避免改为逐笔求和后重复计算。
  for (const group of legacyStepGroups.values()) {
    const populated = group.filter(row => row.priorEquityMethodAdjustments != null)
    if (populated.length > 1 && populated.every(
      row => row.priorEquityMethodAdjustments === populated[0].priorEquityMethodAdjustments,
    )) {
      populated.slice(1).forEach(row => { row.priorEquityMethodAdjustments = null })
    }
  }
  return normalized
}

function normName(name: string): string {
  return name.trim()
}

export function validateNotSameControlRows(
  rows: G7NotSameControlStoredRow[],
  context: G7NotSameControlValidationContext = {},
): G7NotSameControlIssue[] {
  const issues: G7NotSameControlIssue[] = []
  const mergerRows = rows.filter((row): row is G7NotSameControlMergerRow => row.section === 'merger')
  const stepRows = rows.filter((row): row is G7NotSameControlStepRow => row.section === 'step')
  const reverseRows = rows.filter((row): row is G7NotSameControlReverseRow => row.section === 'reverse')

  const mergerNames = new Set<string>()
  for (const row of mergerRows) {
    const name = normName(row.investeeName)
    if (!name) {
      issues.push({ severity: 'error', rowId: row.id, message: `一次购买第${row.seq}行公司名称不能为空` })
    } else if (mergerNames.has(name)) {
      issues.push({ severity: 'error', rowId: row.id, message: `公司「${name}」在一次购买中重复` })
    } else {
      mergerNames.add(name)
    }
    if (!row.acquisitionDate) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写购买日` })
    } else if (!row.acquisitionDateEvidenceRef.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写购买日认定证据索引` })
    }
    if (row.ownershipRatio == null || row.ownershipRatio < 0 || row.ownershipRatio > 1) {
      issues.push({ severity: 'error', rowId: row.id, message: `「${name || row.seq}」持股比例应为0～1` })
    }
    if (row.totalConsiderationFV === 0 && row.acquireeIdentifiableNetAssetsFV == null) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        message: `「${name || row.seq}」合并对价与可辨认净资产公允价值均未填写`,
      })
    }
    if (row.totalConsiderationFV !== 0 && row.considerationBookValue == null) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        message: `「${name || row.seq}」未填写对价账面价值⑤，无法计算⑦损益`,
      })
    }
    if (row.totalConsiderationFV !== 0 && !row.considerationEvidenceRef.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写合并对价证据索引` })
    }
    if (row.acquireeIdentifiableNetAssetsFV != null && !row.valuationReportRef.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写评估报告/公允价值证据索引` })
    }
    if (amount(row.acquisitionCostsExpensed) > 0) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        // eslint-disable-next-line gt-audit/no-amount-toFixed -- 校验文案中的金额提示
        message: `「${name || row.seq}」直接相关费用 ${amount(row.acquisitionCostsExpensed).toFixed(2)} 应按 CAS20 计入当期损益，已不纳入⑥/⑧`,
      })
    }
    // 廉价购买利得硬校验
    if (row.goodwill < -0.005) {
      if (row.bargainPurchaseReviewed !== '是') {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${name || row.seq}」存在廉价购买利得，须勾选「已复核计量无误」后方可确认营业外收入`,
        })
      }
      if (!row.bargainPurchaseReviewNote.trim()) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${name || row.seq}」廉价购买利得应说明复核过程（可辨认资产/负债是否完整、FV是否可靠）`,
        })
      }
    }
  }

  const stepCompanyNames = new Set<string>()
  for (const summary of summarizeNotSameControlSteps(stepRows)) {
    const name = normName(summary.companyName)
    if (!name) {
      issues.push({ severity: 'error', message: '分步合并公司名称不能为空' })
    } else {
      stepCompanyNames.add(name)
    }
    if (summary.cumulativeRatio <= 0 || summary.cumulativeRatio > 1) {
      issues.push({ severity: 'error', message: `「${name}」累计持股比例应为0～1` })
    }
    if (summary.isPackageDeal === '是') {
      issues.push({
        severity: 'error',
        message: `「${name}」已判定构成一揽子交易，应作为一次取得控制权处理，不适用分步合并区段`,
      })
    } else if (summary.isPackageDeal === '否' && !summary.notPackageBasis.trim()) {
      issues.push({ severity: 'warning', message: `「${name}」需说明不构成一揽子交易的依据` })
    } else if (!summary.isPackageDeal) {
      issues.push({ severity: 'warning', message: `「${name}」未选择是否构成一揽子交易` })
    }
    if (!summary.acquisitionDateEvidenceRef.trim()) {
      issues.push({ severity: 'warning', message: `「${name}」分步合并未填写购买日认定证据索引` })
    }
    if (summary.cumulativeConsiderationFV !== 0 && !summary.considerationEvidenceRef.trim()) {
      issues.push({ severity: 'warning', message: `「${name}」分步合并未填写对价证据索引` })
    }
  }

  for (const name of mergerNames) {
    if (stepCompanyNames.has(name)) {
      issues.push({
        severity: 'error',
        message: `公司「${name}」同时出现在一次购买与分步合并，请只保留一种取得方式`,
      })
    }
  }

  const testedNames = [...mergerNames, ...stepCompanyNames]
  const notSameSet = new Set((context.notSameControlInvestees ?? []).map(normName).filter(Boolean))
  const detailSet = new Set((context.detailInvestees ?? []).map(normName).filter(Boolean))
  const basicSet = new Set((context.basicInfoInvestees ?? []).map(normName).filter(Boolean))

  if (notSameSet.size > 0) {
    for (const name of testedNames) {
      if (!notSameSet.has(name)) {
        issues.push({
          severity: 'warning',
          message: `「${name}」未在 G7-7 判定为「控制+非同一控制下企业合并」，请核对是否应列入 G7-9`,
        })
      }
    }
    for (const name of notSameSet) {
      if (!testedNames.includes(name)) {
        issues.push({
          severity: 'warning',
          message: `G7-7 非同控单位「${name}」尚未纳入 G7-9 初始计量测试`,
        })
      }
    }
  }

  const roster = new Set([...detailSet, ...basicSet])
  if (roster.size > 0) {
    for (const name of testedNames) {
      if (!roster.has(name)) {
        issues.push({
          severity: 'warning',
          message: `「${name}」未出现在 G7-2/G7-4 子公司名单中，请核对明细或基本信息`,
        })
      }
    }
  }

  for (const row of reverseRows) {
    if (!row.transactionContent.trim()) {
      issues.push({ severity: 'error', rowId: row.id, message: `反向购买第${row.seq}行交易内容不能为空` })
    }
    if (!row.reversePurchaseBasis.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `反向购买第${row.seq}行需填写判断依据` })
    }
    if (!row.constitutesBusiness) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        message: `反向购买第${row.seq}行须选择会计上的被购买方是否构成业务`,
      })
    } else if (!row.businessDeterminationBasis.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        message: `反向购买第${row.seq}行需填写是否构成业务的判断依据`,
      })
    }
    if (row.constitutesBusiness === '否') {
      issues.push({
        severity: 'error',
        rowId: row.id,
        message: `反向购买第${row.seq}行不构成业务时，应按资产购置处理，不得确认商誉`,
      })
    }
  }
  return issues
}

export function extractNotSameControlInvesteesFromG7Judgment(payload: unknown): string[] {
  let data = payload
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return [] }
  }
  const root = (data as any)?.controlJudgment ?? data
  const decision = root?.decision
  if (!decision) return []
  const name = String(decision.investeeName || '').trim()
  if (!name) return []
  if (decision.relationshipType === '控制' && decision.combinationType === '非同一控制下企业合并') {
    return [name]
  }
  return []
}

export function syncMergerRowsFromNotSameControlNames(
  existing: G7NotSameControlMergerRow[],
  names: string[],
): { rows: G7NotSameControlMergerRow[]; added: number } {
  const rows = [...existing]
  const have = new Set(rows.map(r => normName(r.investeeName)))
  let added = 0
  for (const name of names) {
    const n = normName(name)
    if (!n || have.has(n)) continue
    rows.push(createNotSameControlMergerRow(rows.length + 1, n))
    have.add(n)
    added += 1
  }
  rows.forEach((row, i) => { row.seq = i + 1 })
  return { rows, added }
}
