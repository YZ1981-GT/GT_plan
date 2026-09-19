/**
 * I1-5 无形资产增加检查 — 纯函数模型（对齐致同源表 19 列）
 *
 * 源表列组：
 * A 名称 | B 入账金额
 * C~E 购买 | F~H 股东投入 | I~L 融资性质 | M~O 企业合并 | P~Q 其他
 * R 备注 | S 附件
 *
 * 合计：B23=SUM(检查入账)；B24=明细本期增加；B25=B23/B24（检查比例）
 * 改进：B25 对分母为 0 返回 null，避免 #DIV/0!
 */
export type YnNa = 'Y' | 'N' | 'NA' | ''

export const I1_ADDITION_METHODS = [
  '购买',
  '股东投入',
  '融资性质购买',
  '企业合并',
  '自行开发',
  '其他',
] as const

export type I1AdditionMethod = (typeof I1_ADDITION_METHODS)[number] | string

export interface I1AdditionCheckRow {
  rowId: string
  /** A 资产名称 */
  name: string
  /** 取得方式（驱动高亮相关列组） */
  acquisitionMethod: I1AdditionMethod
  /** B 入账金额（外购应为不含税成本） */
  entryAmount: number
  entryDate: string
  voucherNo: string
  /** 交易对方（关联方核对） */
  counterparty: string

  // ── 购买 C~E + 价税分离 ──
  purchaseContractComplete: YnNa
  purchasePaymentApproved: YnNa
  purchaseEntryCorrect: YnNa
  /** 发票金额（不含税） */
  invoiceAmountExTax: number
  /** 进项税额 */
  inputVat: number
  /** 价税是否已正确分离入账（进项税不进无形资产成本） */
  vatSplitOk: YnNa

  // ── 股东投入 F~H（改进：批复含股东会/董事会，不只国资委）──
  investApproval: YnNa
  investProcedureComplete: YnNa
  investPriceFair: YnNa

  // ── 融资性质 I~L ──
  financeBookAmount: number
  financeEffectiveRate: number
  financeCost: number
  financeEntryCorrect: YnNa

  // ── 企业合并 M~O ──
  comboAmount: number
  comboRecognitionMet: YnNa
  /** PPA 专家复核结论 + 工作底稿索引 */
  comboPpaIndex: string

  // ── 其他 P~Q ──
  otherMethod: string
  otherCompliant: YnNa

  // ── 风险标记（审计问题解答第18号等）──
  isRelatedParty: YnNa
  relatedPartyName: string
  /** 关联方资金占用 / 融资性安排风险 */
  fundOccupationRisk: YnNa

  remark: string
  attachmentUrl: string
  ocrResult: string
  checkConclusion: string
  voucherSampleId: string
  sourceDetailRowId?: string
}

/** 证→账追查行（完整性认定） */
export interface I1TraceRow {
  rowId: string
  seq: number
  sourceType: string
  sourceRef: string
  sourceDate: string
  sourceParty: string
  sourceAmount: number
  recordedInBooks: YnNa
  bookVoucherNo: string
  bookAssetName: string
  bookAmount: number
  /** 差额 = 源金额 − 账面金额 */
  amountDiff: number
  checkResult: string
  remark: string
  indexRef: string
}

export const I1_TRACE_SOURCE_OPTS = [
  '合同', '发票', '权属证明', '验收/交接单', '评估报告', '决议/批复', '其他',
] as const

export interface I1AdditionSummary {
  checkedTotal: number
  periodTotal: number
  /** 检查比例 %；periodTotal<=0 时为 null（防 DIV/0） */
  coverageRate: number | null
  financeBookTotal: number
  financeCostTotal: number
  comboAmountTotal: number
  anomalyCount: number
  checkedCount: number
  relatedPartyCount: number
  fundRiskCount: number
  /** 外购：入账金额与发票不含税差 >1 */
  vatMismatchCount: number
  traceCount: number
  traceUnrecordedCount: number
}

/** 检查比例默认告警阈值（%） */
export const I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD = 20

/** 宽表列组（精简视图按取得方式显示） */
export type I1MethodColGroup = 'purchase' | 'invest' | 'finance' | 'combo' | 'other'

export function methodToColGroup(method: string): I1MethodColGroup {
  const s = String(method || '').trim()
  if (/融资/.test(s)) return 'finance'
  if (/投|股东/.test(s)) return 'invest'
  if (/合并/.test(s)) return 'combo'
  if (/购买|购置|外购|购/.test(s)) return 'purchase'
  return 'other'
}

export function calcI1AdditionCoverage(checkedTotal: number, periodTotal: number): number | null {
  if (!(periodTotal > 0)) return null
  return Math.round((checkedTotal / periodTotal) * 10000) / 100
}

/** 发票价税合计 = 不含税 + 进项税 */
export function calcInvoiceInclTax(exTax: number, inputVat: number): number {
  return (Number(exTax) || 0) + (Number(inputVat) || 0)
}

/** 外购价税勾稽：入账金额应 ≈ 发票不含税（进项税不进成本） */
export function isI1VatMismatch(row: Pick<I1AdditionCheckRow, 'acquisitionMethod' | 'entryAmount' | 'invoiceAmountExTax'>): boolean {
  if (methodToColGroup(String(row.acquisitionMethod || '')) !== 'purchase') return false
  const ex = Number(row.invoiceAmountExTax) || 0
  if (!(ex > 0)) return false
  return Math.abs((Number(row.entryAmount) || 0) - ex) > 1
}

export function calcI1TraceAmountDiff(sourceAmount: number, bookAmount: number): number {
  return Math.round(((Number(sourceAmount) || 0) - (Number(bookAmount) || 0)) * 100) / 100
}

export function summarizeI1Addition(
  rows: I1AdditionCheckRow[],
  periodTotal: number,
  traceRows: I1TraceRow[] = [],
): I1AdditionSummary {
  let checkedTotal = 0
  let financeBookTotal = 0
  let financeCostTotal = 0
  let comboAmountTotal = 0
  let anomalyCount = 0
  let relatedPartyCount = 0
  let fundRiskCount = 0
  let vatMismatchCount = 0
  for (const r of rows) {
    checkedTotal += Number(r.entryAmount) || 0
    financeBookTotal += Number(r.financeBookAmount) || 0
    financeCostTotal += Number(r.financeCost) || 0
    comboAmountTotal += Number(r.comboAmount) || 0
    if (r.checkConclusion === '有异常') anomalyCount++
    if (r.isRelatedParty === 'Y') relatedPartyCount++
    if (r.fundOccupationRisk === 'Y') fundRiskCount++
    if (isI1VatMismatch(r)) vatMismatchCount++
  }
  const traceUnrecordedCount = (traceRows ?? []).filter(
    (t) => t.recordedInBooks === 'N' || t.checkResult === 'ERR' || Math.abs(Number(t.amountDiff) || 0) > 1,
  ).length
  return {
    checkedTotal,
    periodTotal: Math.max(Number(periodTotal) || 0, 0),
    coverageRate: calcI1AdditionCoverage(checkedTotal, periodTotal),
    financeBookTotal,
    financeCostTotal,
    comboAmountTotal,
    anomalyCount,
    checkedCount: rows.length,
    relatedPartyCount,
    fundRiskCount,
    vatMismatchCount,
    traceCount: (traceRows ?? []).length,
    traceUnrecordedCount,
  }
}

export function emptyI1AdditionRow(partial?: Partial<I1AdditionCheckRow>): I1AdditionCheckRow {
  return {
    rowId: partial?.rowId ?? `i1add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    name: '',
    acquisitionMethod: '',
    entryAmount: 0,
    entryDate: '',
    voucherNo: '',
    counterparty: '',
    purchaseContractComplete: '',
    purchasePaymentApproved: '',
    purchaseEntryCorrect: '',
    invoiceAmountExTax: 0,
    inputVat: 0,
    vatSplitOk: '',
    investApproval: '',
    investProcedureComplete: '',
    investPriceFair: '',
    financeBookAmount: 0,
    financeEffectiveRate: 0,
    financeCost: 0,
    financeEntryCorrect: '',
    comboAmount: 0,
    comboRecognitionMet: '',
    comboPpaIndex: '',
    otherMethod: '',
    otherCompliant: '',
    isRelatedParty: '',
    relatedPartyName: '',
    fundOccupationRisk: '',
    remark: '',
    attachmentUrl: '',
    ocrResult: '',
    checkConclusion: '',
    voucherSampleId: '',
    ...partial,
  }
}

export function normalizeI1AdditionRow(raw: any): I1AdditionCheckRow {
  return emptyI1AdditionRow({
    rowId: raw?.rowId,
    name: String(raw?.name ?? ''),
    acquisitionMethod: String(raw?.acquisitionMethod ?? ''),
    entryAmount: Number(raw?.entryAmount) || 0,
    entryDate: String(raw?.entryDate ?? ''),
    voucherNo: String(raw?.voucherNo ?? raw?.contractInvoiceNo ?? ''),
    counterparty: String(raw?.counterparty ?? ''),
    purchaseContractComplete: (raw?.purchaseContractComplete ?? '') as YnNa,
    purchasePaymentApproved: (raw?.purchasePaymentApproved ?? '') as YnNa,
    purchaseEntryCorrect: (raw?.purchaseEntryCorrect ?? '') as YnNa,
    invoiceAmountExTax: Number(raw?.invoiceAmountExTax) || 0,
    inputVat: Number(raw?.inputVat) || 0,
    vatSplitOk: (raw?.vatSplitOk ?? '') as YnNa,
    investApproval: (raw?.investApproval ?? '') as YnNa,
    investProcedureComplete: (raw?.investProcedureComplete ?? '') as YnNa,
    investPriceFair: (raw?.investPriceFair ?? '') as YnNa,
    financeBookAmount: Number(raw?.financeBookAmount) || 0,
    financeEffectiveRate: Number(raw?.financeEffectiveRate) || 0,
    financeCost: Number(raw?.financeCost) || 0,
    financeEntryCorrect: (raw?.financeEntryCorrect ?? '') as YnNa,
    comboAmount: Number(raw?.comboAmount) || 0,
    comboRecognitionMet: (raw?.comboRecognitionMet ?? '') as YnNa,
    comboPpaIndex: String(raw?.comboPpaIndex ?? ''),
    otherMethod: String(raw?.otherMethod ?? ''),
    otherCompliant: (raw?.otherCompliant ?? '') as YnNa,
    isRelatedParty: (raw?.isRelatedParty ?? '') as YnNa,
    relatedPartyName: String(raw?.relatedPartyName ?? ''),
    fundOccupationRisk: (raw?.fundOccupationRisk ?? '') as YnNa,
    remark: String(raw?.remark ?? ''),
    attachmentUrl: String(raw?.attachmentUrl ?? ''),
    ocrResult: String(raw?.ocrResult ?? ''),
    checkConclusion: String(raw?.checkConclusion ?? ''),
    voucherSampleId: String(raw?.voucherSampleId ?? ''),
    sourceDetailRowId: raw?.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
  })
}

export function emptyI1TraceRow(partial?: Partial<I1TraceRow>): I1TraceRow {
  const sourceAmount = Number(partial?.sourceAmount) || 0
  const bookAmount = Number(partial?.bookAmount) || 0
  const amountDiff = partial?.amountDiff != null
    ? Number(partial.amountDiff) || 0
    : calcI1TraceAmountDiff(sourceAmount, bookAmount)
  return {
    rowId: partial?.rowId ?? `i1tr-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq: partial?.seq ?? 1,
    sourceType: partial?.sourceType ?? '',
    sourceRef: partial?.sourceRef ?? '',
    sourceDate: partial?.sourceDate ?? '',
    sourceParty: partial?.sourceParty ?? '',
    sourceAmount,
    recordedInBooks: (partial?.recordedInBooks ?? '') as YnNa,
    bookVoucherNo: partial?.bookVoucherNo ?? '',
    bookAssetName: partial?.bookAssetName ?? '',
    bookAmount,
    amountDiff,
    checkResult: partial?.checkResult ?? '',
    remark: partial?.remark ?? '',
    indexRef: partial?.indexRef ?? '',
  }
}

export function normalizeI1TraceRow(raw: any, idx = 0): I1TraceRow {
  const sourceAmount = Number(raw?.sourceAmount) || 0
  const bookAmount = Number(raw?.bookAmount) || 0
  return emptyI1TraceRow({
    rowId: raw?.rowId,
    seq: Number(raw?.seq) || idx + 1,
    sourceType: String(raw?.sourceType ?? ''),
    sourceRef: String(raw?.sourceRef ?? ''),
    sourceDate: String(raw?.sourceDate ?? ''),
    sourceParty: String(raw?.sourceParty ?? ''),
    sourceAmount,
    recordedInBooks: (raw?.recordedInBooks ?? '') as YnNa,
    bookVoucherNo: String(raw?.bookVoucherNo ?? ''),
    bookAssetName: String(raw?.bookAssetName ?? ''),
    bookAmount,
    amountDiff: calcI1TraceAmountDiff(sourceAmount, bookAmount),
    checkResult: String(raw?.checkResult ?? ''),
    remark: String(raw?.remark ?? ''),
    indexRef: String(raw?.indexRef ?? ''),
  })
}

/** 从账→证样本生成证→账追查行（去重 sourceRef+名称） */
export function seedI1TraceFromCheckRows(checkRows: I1AdditionCheckRow[]): I1TraceRow[] {
  const out: I1TraceRow[] = []
  let seq = 1
  for (const r of checkRows ?? []) {
    if (!String(r?.name || '').trim()) continue
    out.push(emptyI1TraceRow({
      seq: seq++,
      sourceType: r.voucherNo ? '发票' : '合同',
      sourceRef: r.voucherNo || '',
      sourceDate: r.entryDate || '',
      sourceParty: r.counterparty || r.relatedPartyName || '',
      sourceAmount: Number(r.invoiceAmountExTax) > 0
        ? Number(r.invoiceAmountExTax)
        : (Number(r.entryAmount) || 0),
      recordedInBooks: 'Y',
      bookVoucherNo: r.voucherNo || '',
      bookAssetName: r.name,
      bookAmount: Number(r.entryAmount) || 0,
      checkResult: 'OK',
      remark: '自账→证样本生成',
    }))
  }
  return out
}

/** 精简视图：当前样本涉及的列组并集；无样本时默认展示「购买」 */
export function collectActiveColGroups(
  rows: Array<{ acquisitionMethod?: string }>,
): Set<I1MethodColGroup> {
  const set = new Set<I1MethodColGroup>()
  for (const r of rows ?? []) set.add(methodToColGroup(r.acquisitionMethod || ''))
  if (!set.size) set.add('purchase')
  return set
}

export function shouldShowColGroup(
  group: I1MethodColGroup,
  mode: 'compact' | 'full',
  rows: Array<{ acquisitionMethod?: string }>,
): boolean {
  if (mode === 'full') return true
  return collectActiveColGroups(rows).has(group)
}

/** I2 → I1 资本化转入明细 */
export interface I2CapitalizationTransferItem {
  projectName?: string
  amount?: number
  transferDate?: string
  transferAssetName?: string
  sourceRowId?: string
}

/** 从 I2 资本化转入明细生成 I1-5 检查行 */
export function seedI1AdditionFromI2Transfer(
  items: I2CapitalizationTransferItem[],
): I1AdditionCheckRow[] {
  const out: I1AdditionCheckRow[] = []
  for (const it of items ?? []) {
    const amount = Number(it?.amount) || 0
    if (!(amount > 0)) continue
    const name = String(it?.transferAssetName || it?.projectName || '').trim()
    if (!name) continue
    out.push(emptyI1AdditionRow({
      name,
      acquisitionMethod: '自行开发',
      entryAmount: amount,
      entryDate: String(it?.transferDate ?? ''),
      otherMethod: 'I2开发支出资本化转入',
      remark: '自I2资本化转入',
      sourceDetailRowId: it?.sourceRowId ? `i2:${it.sourceRowId}` : undefined,
    }))
  }
  return out
}

/** I1-2 costIncreaseMethod / 旧字段 → I1-5 取得方式 */
export function mapDetailIncreaseMethodToAddition(methodRaw: string): I1AdditionMethod {
  const s = String(methodRaw || '').trim()
  if (!s) return '其他'
  // 更具体的匹配优先（避免「融资性质购买」被「购买」吃掉）
  if (/融资/.test(s)) return '融资性质购买'
  if (/投|股东/.test(s)) return '股东投入'
  if (s === '企业合并增加' || /合并/.test(s)) return '企业合并'
  if (s === '内部研发' || /开发|自行|研发/.test(s)) return '自行开发'
  if (s === '购置' || /外购|购买|购/.test(s)) return '购买'
  if (s === '其他增加') return '其他'
  return s
}

/** 从 I1-2 明细带入本期增加>0 的行 */
export function seedI1AdditionFromDetail(detailRows: any[]): I1AdditionCheckRow[] {
  const out: I1AdditionCheckRow[] = []
  for (const r of detailRows ?? []) {
    const increase = Number(r?.costIncrease ?? r?.increase ?? 0)
    if (!(increase > 0)) continue
    const name = String(r?.name || '').trim()
    if (!name) continue
    // 优先 costIncreaseMethod（I1-2 原值区段），兼容旧 acquisitionMethod
    const methodRaw = String(
      r?.costIncreaseMethod || r?.acquisitionMethod || r?.amortizationMethod || '',
    ).trim()
    const method = mapDetailIncreaseMethodToAddition(methodRaw)

    out.push(emptyI1AdditionRow({
      name,
      acquisitionMethod: method,
      entryAmount: increase,
      entryDate: String(r?.acquisitionDate ?? ''),
      sourceDetailRowId: String(r?.rowId ?? ''),
      remark: '自I1-2本期增加带入',
    }))
  }
  return out
}

export const I1_ADDITION_EXPORT_HEADERS = [
  '资产名称', '入账金额', '取得方式', '入账日期', '凭证号', '交易对方',
  '购买-合同齐全', '购买-支付审批', '购买-入账正确',
  '购买-发票不含税', '购买-进项税额', '购买-价税分离正确',
  '投入-批复手续', '投入-手续齐全', '投入-价格公允',
  '融资-入账金额', '融资-实际利率', '融资-融资费用', '融资-入账正确',
  '合并-合并金额', '合并-确认条件', '合并-PPA索引',
  '其他-方式', '其他-符合规定',
  '关联方', '关联方名称', '资金占用风险',
  '审查结论', '备注',
] as const

export function rowToExportRecord(row: I1AdditionCheckRow): Record<string, string | number> {
  return {
    资产名称: row.name,
    入账金额: row.entryAmount,
    取得方式: row.acquisitionMethod,
    入账日期: row.entryDate,
    凭证号: row.voucherNo,
    交易对方: row.counterparty,
    '购买-合同齐全': row.purchaseContractComplete,
    '购买-支付审批': row.purchasePaymentApproved,
    '购买-入账正确': row.purchaseEntryCorrect,
    '购买-发票不含税': row.invoiceAmountExTax,
    '购买-进项税额': row.inputVat,
    '购买-价税分离正确': row.vatSplitOk,
    '投入-批复手续': row.investApproval,
    '投入-手续齐全': row.investProcedureComplete,
    '投入-价格公允': row.investPriceFair,
    '融资-入账金额': row.financeBookAmount,
    '融资-实际利率': row.financeEffectiveRate,
    '融资-融资费用': row.financeCost,
    '融资-入账正确': row.financeEntryCorrect,
    '合并-合并金额': row.comboAmount,
    '合并-确认条件': row.comboRecognitionMet,
    '合并-PPA索引': row.comboPpaIndex,
    '其他-方式': row.otherMethod,
    '其他-符合规定': row.otherCompliant,
    关联方: row.isRelatedParty,
    关联方名称: row.relatedPartyName,
    资金占用风险: row.fundOccupationRisk,
    审查结论: row.checkConclusion,
    备注: row.remark,
  }
}
