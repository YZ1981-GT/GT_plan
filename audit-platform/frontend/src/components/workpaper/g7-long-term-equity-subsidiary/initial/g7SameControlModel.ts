import { useDecimalCalc } from '@/composables/useDecimalCalc'
import {
  filterDecisionsByCombination,
  listG7ControlDecisions,
} from '../../composables/g7ControlJudgmentModel'
import { isG74SubsidiaryRow } from '../../composables/g7EquityMethodCrossSheet'

const moneyCalc = useDecimalCalc({ dp: 2 })
const ratioCalc = useDecimalCalc({ dp: 6 })

export type G7SameControlAuditConclusion = '' | '无差异' | '差异可接受' | '差异需调整'
export type G7YesNo = '' | '是' | '否'

export interface G7SameControlMergerRow {
  id: string
  section: 'merger'
  seq: number
  investeeName: string
  /** 合并日（consol first_consol_date / acquisitionDate） */
  acquisitionDate: string
  finalController: string
  ownerEquityBookValue: number | null
  ownershipRatio: number | null
  initialInvestmentCost: number
  cashConsideration: number | null
  nonCashAssetBookValue: number | null
  debtBookValue: number | null
  equitySecuritiesFaceValue: number | null
  contingentConsideration: number | null
  totalConsideration: number
  capitalReserveRetainedEarningsAdjustment: number
  adjustmentTreatment: string
  accountingPolicyConsistent: G7YesNo
  accountingPolicyNote: string
  availableCapitalReserve: number | null
  indexRef: string
  auditConclusion: G7SameControlAuditConclusion
}

export interface G7SameControlStepRow {
  id: string
  section: 'step'
  companyId: string
  companyName: string
  seq: number
  transactionNo: number
  transactionDate: string
  /** 取得控制权的合并日（公司级，各次交易行同步；缺省可用末次交易日） */
  acquisitionDate: string
  purchaseRatio: number | null
  consideration: number | null
  netAssetsBookValue: number | null
  /** 原持股账面价值（公司级字段，各次交易行同步） */
  priorHoldingBookValue: number | null
  priorInvestmentAdjustments: number | null
  isPackageDeal: G7YesNo
  notPackageBasis: string
  availableCapitalReserve: number | null
  indexRef: string
}

export interface G7SameControlReverseRow {
  id: string
  section: 'reverse'
  seq: number
  transactionContent: string
  accountingAcquirer: string
  acquirerShareholders: string
  accountingAcquiree: string
  acquireeOriginalShareholders: string
  reversePurchaseBasis: string
  businessDeterminationBasis: string
  indexRef: string
}

export type G7SameControlStoredRow =
  | G7SameControlMergerRow
  | G7SameControlStepRow
  | G7SameControlReverseRow

export interface G7SameControlStepSummary {
  companyId: string
  companyName: string
  acquisitionDate: string
  cumulativeRatio: number
  cumulativeConsideration: number
  priorHoldingBookValue: number
  cumulativePriorAdjustments: number
  mergerDateNetAssets: number
  initialInvestmentCost: number
  capitalReserveRetainedEarningsAdjustment: number
  isPackageDeal: G7YesNo
  notPackageBasis: string
  availableCapitalReserve: number | null
  indexRef: string
  adjustmentHint: string
}

export interface G7SameControlIssue {
  severity: 'error' | 'warning'
  rowId?: string
  message: string
}

export interface G7SameControlValidationContext {
  /** G7-7 判定为「控制 + 同一控制下企业合并」的单位 */
  sameControlInvestees?: string[]
  /** G7-2 成本法/子公司名单 */
  detailInvestees?: string[]
  /** G7-4 子公司组名单 */
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

/** 一次合并⑤ / 分步⑥：按差额方向给出资本公积处理提示 */
export function describeCapitalReserveAdjustment(adjustment: number, mode: 'merger' | 'step'): string {
  if (Math.abs(adjustment) < 0.005) return '无差额'
  if (mode === 'merger') {
    // ⑤=③−④：正数=贷记资本公积；负数=冲减资本公积/留存收益
    return adjustment > 0
      ? '贷记资本公积（初始成本＞对价）'
      : '冲减资本公积，不足冲减留存收益（初始成本＜对价）'
  }
  // ⑥=②+原账面+③−⑤：正数=冲减资本公积；负数=贷记资本公积
  return adjustment > 0
    ? '冲减资本公积，不足冲减留存收益（对价+原账面＞初始成本）'
    : '贷记资本公积（对价+原账面＜初始成本）'
}

/**
 * 对价与初始成本差额过大（|差额| > 初始成本×50% 且初始成本>0）→ UI 橙色高亮。
 * 差额口径与⑤一致：|初始成本 − 对价合计|。
 */
export function isSameControlDifferenceLarge(
  initialCost: number,
  totalConsideration: number,
): boolean {
  const cost = amount(initialCost)
  if (cost <= 0) return false
  return Math.abs(cost - amount(totalConsideration)) > cost * 0.5
}

export function createSameControlMergerRow(seq: number, investeeName = ''): G7SameControlMergerRow {
  return recalcSameControlMergerRow({
    id: uid('g7-8-merger'),
    section: 'merger',
    seq,
    investeeName,
    acquisitionDate: '',
    finalController: '',
    ownerEquityBookValue: null,
    ownershipRatio: null,
    initialInvestmentCost: 0,
    cashConsideration: null,
    nonCashAssetBookValue: null,
    debtBookValue: null,
    equitySecuritiesFaceValue: null,
    contingentConsideration: null,
    totalConsideration: 0,
    capitalReserveRetainedEarningsAdjustment: 0,
    adjustmentTreatment: '',
    accountingPolicyConsistent: '',
    accountingPolicyNote: '',
    availableCapitalReserve: null,
    indexRef: '',
    auditConclusion: '',
  })
}

export function recalcSameControlMergerRow(row: G7SameControlMergerRow): G7SameControlMergerRow {
  row.initialInvestmentCost = Number(
    moneyCalc.mul(amount(row.ownerEquityBookValue), amount(row.ownershipRatio)),
  )
  row.totalConsideration = Number(moneyCalc.sum(
    amount(row.cashConsideration),
    amount(row.nonCashAssetBookValue),
    amount(row.debtBookValue),
    amount(row.equitySecuritiesFaceValue),
    amount(row.contingentConsideration),
  ))
  // 原底稿⑤=③-④：正数表示增加资本公积，负数表示冲减资本公积/留存收益。
  row.capitalReserveRetainedEarningsAdjustment = Number(
    moneyCalc.sub(row.initialInvestmentCost, row.totalConsideration),
  )
  return row
}

export function createSameControlStepRow(
  companyId: string,
  companyName: string,
  seq: number,
): G7SameControlStepRow {
  return {
    id: uid('g7-8-step'),
    section: 'step',
    companyId,
    companyName,
    seq,
    transactionNo: seq,
    transactionDate: '',
    acquisitionDate: '',
    purchaseRatio: null,
    consideration: null,
    netAssetsBookValue: null,
    priorHoldingBookValue: null,
    priorInvestmentAdjustments: null,
    isPackageDeal: '',
    notPackageBasis: '',
    availableCapitalReserve: null,
    indexRef: '',
  }
}

export function createSameControlReverseRow(seq: number): G7SameControlReverseRow {
  return {
    id: uid('g7-8-reverse'),
    section: 'reverse',
    seq,
    transactionContent: '',
    accountingAcquirer: '',
    acquirerShareholders: '',
    accountingAcquiree: '',
    acquireeOriginalShareholders: '',
    reversePurchaseBasis: '',
    businessDeterminationBasis: '',
    indexRef: '',
  }
}

export function summarizeSameControlSteps(rows: G7SameControlStepRow[]): G7SameControlStepSummary[] {
  const groups = new Map<string, G7SameControlStepRow[]>()
  for (const row of rows) {
    const key = row.companyId || row.companyName
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(row)
  }
  const summaries: G7SameControlStepSummary[] = []
  for (const [companyId, group] of groups) {
    const ordered = [...group].sort((a, b) => a.transactionNo - b.transactionNo || a.seq - b.seq)
    const last = ordered[ordered.length - 1]
    const cumulativeRatio = Number(ratioCalc.sum(...ordered.map(row => amount(row.purchaseRatio))))
    const cumulativeConsideration = Number(moneyCalc.sum(...ordered.map(row => amount(row.consideration))))
    const cumulativePriorAdjustments = Number(
      moneyCalc.sum(...ordered.map(row => amount(row.priorInvestmentAdjustments))),
    )
    // 公司级字段：取任一行已填值（同步写入）
    const priorHoldingBookValue = amount(
      ordered.find(row => row.priorHoldingBookValue != null)?.priorHoldingBookValue,
    )
    const mergerDateNetAssets = amount(last?.netAssetsBookValue)
    const initialInvestmentCost = Number(moneyCalc.mul(mergerDateNetAssets, cumulativeRatio))
    // ⑥=②+原持股账面价值+③−⑤，未填原账面时退化为原底稿②+③−⑤
    const capitalReserveRetainedEarningsAdjustment = Number(moneyCalc.sub(
      moneyCalc.sum(cumulativeConsideration, priorHoldingBookValue, cumulativePriorAdjustments),
      initialInvestmentCost,
    ))
    const isPackageDeal = asYesNo(ordered.find(row => row.isPackageDeal)?.isPackageDeal)
    const acquisitionDate = (
      ordered.find(row => row.acquisitionDate?.trim())?.acquisitionDate
      || last?.transactionDate
      || ''
    )
    summaries.push({
      companyId,
      companyName: last?.companyName ?? '',
      acquisitionDate,
      cumulativeRatio,
      cumulativeConsideration,
      priorHoldingBookValue,
      cumulativePriorAdjustments,
      mergerDateNetAssets,
      initialInvestmentCost,
      capitalReserveRetainedEarningsAdjustment,
      isPackageDeal,
      notPackageBasis: ordered.find(row => row.notPackageBasis.trim())?.notPackageBasis ?? '',
      availableCapitalReserve: ordered.find(row => row.availableCapitalReserve != null)?.availableCapitalReserve ?? null,
      indexRef: ordered.find(row => row.indexRef.trim())?.indexRef ?? '',
      adjustmentHint: describeCapitalReserveAdjustment(capitalReserveRetainedEarningsAdjustment, 'step'),
    })
  }
  return summaries
}

export function normalizeSameControlRows(payload: unknown): G7SameControlStoredRow[] {
  const rows: Record<string, any>[] = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as any)?.rows)
      ? (payload as any).rows
      : []
  const normalized: G7SameControlStoredRow[] = []
  for (let index = 0; index < rows.length; index += 1) {
    const raw = rows[index]
    if (raw.section === 'step') {
      normalized.push({
        ...createSameControlStepRow(
          String(raw.companyId || raw.companyName || uid('company')),
          String(raw.companyName || raw.investeeName || ''),
          Number(raw.seq || index + 1),
        ),
        ...raw,
        section: 'step',
        acquisitionDate: String(raw.acquisitionDate || raw.mergerDate || ''),
        purchaseRatio: nullableNumber(raw.purchaseRatio),
        consideration: nullableNumber(raw.consideration),
        netAssetsBookValue: nullableNumber(raw.netAssetsBookValue),
        priorHoldingBookValue: nullableNumber(raw.priorHoldingBookValue),
        priorInvestmentAdjustments: nullableNumber(raw.priorInvestmentAdjustments),
        isPackageDeal: asYesNo(raw.isPackageDeal),
        availableCapitalReserve: nullableNumber(raw.availableCapitalReserve),
      })
    } else if (raw.section === 'reverse') {
      normalized.push({
        ...createSameControlReverseRow(Number(raw.seq || index + 1)),
        ...raw,
        section: 'reverse',
      })
    } else {
      const row = createSameControlMergerRow(
        Number(raw.seq || index + 1),
        String(raw.investeeName || raw.investee_name || ''),
      )
      Object.assign(row, {
        ...raw,
        section: 'merger',
        acquisitionDate: String(raw.acquisitionDate || raw.mergerDate || ''),
        ownerEquityBookValue: nullableNumber(raw.ownerEquityBookValue ?? raw.acquireeNetAssets),
        ownershipRatio: nullableNumber(raw.ownershipRatio ?? raw.shareholdingRatio),
        cashConsideration: nullableNumber(raw.cashConsideration ?? raw.consideration),
        nonCashAssetBookValue: nullableNumber(raw.nonCashAssetBookValue),
        debtBookValue: nullableNumber(raw.debtBookValue),
        equitySecuritiesFaceValue: nullableNumber(raw.equitySecuritiesFaceValue),
        contingentConsideration: nullableNumber(raw.contingentConsideration),
        adjustmentTreatment: String(raw.adjustmentTreatment ?? raw.differenceHandling ?? ''),
        accountingPolicyConsistent: asYesNo(raw.accountingPolicyConsistent),
        accountingPolicyNote: String(raw.accountingPolicyNote ?? ''),
        availableCapitalReserve: nullableNumber(raw.availableCapitalReserve),
        indexRef: String(raw.indexRef ?? ''),
        auditConclusion: raw.auditConclusion ?? raw.audit_conclusion ?? '',
      })
      normalized.push(recalcSameControlMergerRow(row))
    }
  }
  return normalized
}

function normName(name: string): string {
  return name.trim()
}

function pushCapitalReserveShortage(
  issues: G7SameControlIssue[],
  label: string,
  adjustment: number,
  available: number | null,
  mode: 'merger' | 'step',
  rowId?: string,
): void {
  if (available == null) return
  // 需要冲减资本公积的方向才校验余额
  const needCharge = mode === 'merger' ? adjustment < 0 : adjustment > 0
  if (!needCharge) return
  const charge = Math.abs(adjustment)
  if (charge > available + 0.005) {
    issues.push({
      severity: 'warning',
      rowId,
      message: `「${label}」需冲减资本公积 ${charge.toFixed(2)}，超过可用资本公积 ${available.toFixed(2)}，不足部分应冲减留存收益并在附注披露`,
    })
  }
}

export function validateSameControlRows(
  rows: G7SameControlStoredRow[],
  context: G7SameControlValidationContext = {},
): G7SameControlIssue[] {
  const issues: G7SameControlIssue[] = []
  const mergerRows = rows.filter((row): row is G7SameControlMergerRow => row.section === 'merger')
  const stepRows = rows.filter((row): row is G7SameControlStepRow => row.section === 'step')
  const reverseRows = rows.filter((row): row is G7SameControlReverseRow => row.section === 'reverse')

  const mergerNames = new Set<string>()
  for (const row of mergerRows) {
    const name = normName(row.investeeName)
    if (!name) {
      issues.push({ severity: 'error', rowId: row.id, message: `一次合并第${row.seq}行公司名称不能为空` })
    } else if (mergerNames.has(name)) {
      issues.push({ severity: 'error', rowId: row.id, message: `公司「${name}」在一次合并中重复` })
    } else {
      mergerNames.add(name)
    }
    if (!row.finalController.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写最终控制方` })
    }
    if (!row.acquisitionDate.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未填写合并日` })
    }
    if (row.ownershipRatio == null || row.ownershipRatio < 0 || row.ownershipRatio > 1) {
      issues.push({ severity: 'error', rowId: row.id, message: `「${name || row.seq}」出资比例应为0～1` })
    }
    if (row.capitalReserveRetainedEarningsAdjustment !== 0 && !row.adjustmentTreatment.trim()) {
      issues.push({
        severity: 'warning',
        rowId: row.id,
        message: `「${name || row.seq}」存在差额，需说明资本公积/留存收益处理（${describeCapitalReserveAdjustment(row.capitalReserveRetainedEarningsAdjustment, 'merger')}）`,
      })
    }
    if (!row.accountingPolicyConsistent) {
      issues.push({ severity: 'warning', rowId: row.id, message: `「${name || row.seq}」未确认合并前会计政策是否一致` })
    } else if (row.accountingPolicyConsistent === '否' && !row.accountingPolicyNote.trim()) {
      issues.push({
        severity: 'error',
        rowId: row.id,
        message: `「${name || row.seq}」会计政策不一致，须填写统一政策调整说明`,
      })
    }
    pushCapitalReserveShortage(
      issues,
      name || String(row.seq),
      row.capitalReserveRetainedEarningsAdjustment,
      row.availableCapitalReserve,
      'merger',
      row.id,
    )
  }

  const stepCompanyNames = new Set<string>()
  for (const summary of summarizeSameControlSteps(stepRows)) {
    const name = normName(summary.companyName)
    if (!name) {
      issues.push({ severity: 'error', message: '分步合并公司名称不能为空' })
    } else {
      stepCompanyNames.add(name)
    }
    if (summary.cumulativeRatio <= 0 || summary.cumulativeRatio > 1) {
      issues.push({ severity: 'error', message: `「${name}」累计购买比例应为0～1` })
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
    if (summary.priorHoldingBookValue === 0 && stepRows.some(r => (r.companyId === summary.companyId) && r.consideration != null)) {
      issues.push({
        severity: 'warning',
        message: `「${name}」未填写原持股账面价值，⑥勾稽可能不完整`,
      })
    }
    if (!summary.acquisitionDate.trim()) {
      issues.push({ severity: 'warning', message: `「${name}」未填写合并日（取得控制权日）` })
    }
    pushCapitalReserveShortage(
      issues,
      name,
      summary.capitalReserveRetainedEarningsAdjustment,
      summary.availableCapitalReserve,
      'step',
    )
  }

  // 一次合并 ↔ 分步合并互斥
  for (const name of mergerNames) {
    if (stepCompanyNames.has(name)) {
      issues.push({
        severity: 'error',
        message: `公司「${name}」同时出现在一次合并与分步合并，请只保留一种取得方式`,
      })
    }
  }

  // 与 G7-7 / G7-2 / G7-4 名单核对
  const testedNames = [...mergerNames, ...stepCompanyNames]
  const sameControlSet = new Set((context.sameControlInvestees ?? []).map(normName).filter(Boolean))
  const detailSet = new Set((context.detailInvestees ?? []).map(normName).filter(Boolean))
  const basicSet = new Set((context.basicInfoInvestees ?? []).map(normName).filter(Boolean))

  if (sameControlSet.size > 0) {
    for (const name of testedNames) {
      if (!sameControlSet.has(name)) {
        issues.push({
          severity: 'warning',
          message: `「${name}」未在 G7-7 判定为「控制+同一控制下企业合并」，请核对是否应列入 G7-8`,
        })
      }
    }
    for (const name of sameControlSet) {
      if (!testedNames.includes(name)) {
        issues.push({
          severity: 'warning',
          message: `G7-7 同控单位「${name}」尚未纳入 G7-8 初始计量测试`,
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
    if (!row.businessDeterminationBasis.trim()) {
      issues.push({ severity: 'warning', rowId: row.id, message: `反向购买第${row.seq}行需判断会计上的被购买方是否构成业务` })
    }
  }
  return issues
}

/** 从 G7-7 持久化 JSON 提取同控（控制+同一控制）被投资单位 */
export function extractSameControlInvesteesFromG7Judgment(payload: unknown): string[] {
  return filterDecisionsByCombination(listG7ControlDecisions(payload), '同一控制下企业合并')
}

/** 从 G7-2 明细 payload 提取子公司名称 */
export function extractSubsidiaryNamesFromG72(payload: unknown): string[] {
  let data = payload
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return [] }
  }
  const rows: any[] = Array.isArray(data)
    ? data
    : Array.isArray((data as any)?.rows)
      ? (data as any).rows
      : []
  return [...new Set(
    rows
      .filter((raw) => {
        const section = String(raw.section || '')
        const controlType = String(raw.controlType || '')
        return section === 'cost' || controlType === '子公司'
      })
      .map(raw => String(raw.investeeName || raw.investee_name || '').trim())
      .filter(Boolean),
  )]
}

/** 从 G7-4 基本信息 payload 提取子公司组名称（与 loadSubsidiaryInvestees 同口径） */
export function extractSubsidiaryNamesFromG74(payload: unknown): string[] {
  let data = payload
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return [] }
  }
  const rows: any[] = Array.isArray(data)
    ? data
    : Array.isArray((data as any)?.rows)
      ? (data as any).rows
      : []
  return [...new Set(
    rows
      .filter(raw => isG74SubsidiaryRow(raw || {}))
      .map(raw => String(raw.investeeName || raw.investee_name || raw.companyName || '').trim())
      .filter(Boolean),
  )]
}

/** 将 G7-7 同控名单同步进一次合并区（已存在则跳过） */
export function syncMergerRowsFromSameControlNames(
  existing: G7SameControlMergerRow[],
  names: string[],
): { rows: G7SameControlMergerRow[]; added: number } {
  const rows = [...existing]
  const have = new Set(rows.map(r => normName(r.investeeName)))
  let added = 0
  for (const name of names) {
    const n = normName(name)
    if (!n || have.has(n)) continue
    rows.push(createSameControlMergerRow(rows.length + 1, n))
    have.add(n)
    added += 1
  }
  rows.forEach((row, i) => { row.seq = i + 1 })
  return { rows, added }
}
