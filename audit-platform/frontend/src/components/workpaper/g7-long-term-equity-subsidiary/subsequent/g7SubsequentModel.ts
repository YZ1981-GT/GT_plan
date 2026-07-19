/**
 * G7-10 子公司后续计量测试表 — 数据模型（对齐致同源模板三区段）
 *
 * 1、被投资单位分配股利测算
 * 2、购买少数股东股权的处理（个别成本法 + 合并权益性交易）
 * 3、处置子公司权益但不丧失控制权（个别确认损益 + 合并调权益）
 */

import {
  calcConsiderationTotal,
  calcCostMethodIncome,
  calcDividendVariance,
  calcNciEquityAdjustment,
  calcNciPurchaseShare,
  calcPartialDisposalConsolAdjustment,
  calcPartialDisposalConsolShare,
  calcPartialDisposalIndividualGain,
  parseNum,
} from '../../composables/useG7SubFormulaEngine'

export type G7SubsequentAuditConclusion = '' | '无差异' | '差异可接受' | '需进一步调查' | '需调整'

export interface G7DividendRow {
  id: string
  section: 'dividend'
  seq: number
  companyName: string
  distributionPlan: string
  shareholdingRatio: number | null
  declarationDate: string
  dividendPolicy: string
  declaredAmount: number | null
  entitledDividend: number
  recordedDividend: number | null
  variance: number
  auditConclusion: G7SubsequentAuditConclusion
}

export interface G7NciPurchaseRow {
  id: string
  section: 'nci'
  seq: number
  companyName: string
  /** 购买前长投账面 */
  priorCarryingAmount: number | null
  originalRatio: number | null
  /** ① 新增持股比例 */
  addedRatio: number | null
  costCash: number | null
  costNonCashFV: number | null
  costDebtBV: number | null
  costEquityFace: number | null
  costContingent: number | null
  /** ② 购买成本合计 */
  purchaseCost: number
  /** 购买后长投账面 = 购买前 + ② */
  carryingAfterPurchase: number
  /** ③ 自购买日持续计算可辨认净资产FV */
  netAssetsFV: number | null
  /** ④ = ③ × ① */
  shareOfNetAssets: number
  /** ⑤ = ② − ④ */
  equityAdjustment: number
  adjCapitalReserve: number | null
  adjSurplusReserve: number | null
  adjRetainedEarnings: number | null
  indexRef: string
  auditConclusion: G7SubsequentAuditConclusion
}

export interface G7PartialDisposalRow {
  id: string
  section: 'partialDisposal'
  seq: number
  companyName: string
  /** ① 处置日长投账面 */
  bookValueAtDisposal: number | null
  /** ② 原持股比例 */
  originalRatio: number | null
  /** ③ 减少的持股比例 */
  reducedRatio: number | null
  considerationCash: number | null
  considerationNonCashFV: number | null
  considerationDebtBV: number | null
  considerationEquityFace: number | null
  considerationContingent: number | null
  /** ④ 处置对价合计 */
  consideration: number
  /** ⑤ = ④ − ① × ③ / ② */
  individualGain: number
  /** ⑥ 自购买日持续计算可辨认净资产FV */
  netAssetsFV: number | null
  /** ⑦ = ⑥ × ③ */
  consolShare: number
  /** ⑧ = ④ − ⑦ */
  consolEquityAdj: number
  adjCapitalReserve: number | null
  adjSurplusReserve: number | null
  adjRetainedEarnings: number | null
  indexRef: string
  auditConclusion: G7SubsequentAuditConclusion
}

export type G7SubsequentStoredRow = G7DividendRow | G7NciPurchaseRow | G7PartialDisposalRow

export interface G7SubsequentIssue {
  severity: 'error' | 'warning'
  rowId?: string
  message: string
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

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

export function createDividendRow(seq: number, companyName = ''): G7DividendRow {
  return recalcDividendRow({
    id: uid('div'),
    section: 'dividend',
    seq,
    companyName,
    distributionPlan: '',
    shareholdingRatio: null,
    declarationDate: '',
    dividendPolicy: '',
    declaredAmount: null,
    entitledDividend: 0,
    recordedDividend: null,
    variance: 0,
    auditConclusion: '',
  })
}

export function createNciPurchaseRow(seq: number, companyName = ''): G7NciPurchaseRow {
  return recalcNciPurchaseRow({
    id: uid('nci'),
    section: 'nci',
    seq,
    companyName,
    priorCarryingAmount: null,
    originalRatio: null,
    addedRatio: null,
    costCash: null,
    costNonCashFV: null,
    costDebtBV: null,
    costEquityFace: null,
    costContingent: null,
    purchaseCost: 0,
    carryingAfterPurchase: 0,
    netAssetsFV: null,
    shareOfNetAssets: 0,
    equityAdjustment: 0,
    adjCapitalReserve: null,
    adjSurplusReserve: null,
    adjRetainedEarnings: null,
    indexRef: '',
    auditConclusion: '',
  })
}

export function createPartialDisposalRow(seq: number, companyName = ''): G7PartialDisposalRow {
  return recalcPartialDisposalRow({
    id: uid('pd'),
    section: 'partialDisposal',
    seq,
    companyName,
    bookValueAtDisposal: null,
    originalRatio: null,
    reducedRatio: null,
    considerationCash: null,
    considerationNonCashFV: null,
    considerationDebtBV: null,
    considerationEquityFace: null,
    considerationContingent: null,
    consideration: 0,
    individualGain: 0,
    netAssetsFV: null,
    consolShare: 0,
    consolEquityAdj: 0,
    adjCapitalReserve: null,
    adjSurplusReserve: null,
    adjRetainedEarnings: null,
    indexRef: '',
    auditConclusion: '',
  })
}

export function recalcDividendRow(row: G7DividendRow): G7DividendRow {
  const entitled = calcCostMethodIncome(row.declaredAmount ?? 0, row.shareholdingRatio ?? 0)
  const variance = calcDividendVariance(entitled, row.recordedDividend ?? 0)
  return { ...row, entitledDividend: entitled, variance }
}

export function recalcNciPurchaseRow(row: G7NciPurchaseRow): G7NciPurchaseRow {
  const purchaseCost = calcConsiderationTotal(
    row.costCash ?? 0,
    row.costNonCashFV ?? 0,
    row.costDebtBV ?? 0,
    row.costEquityFace ?? 0,
    row.costContingent ?? 0,
  )
  const shareOfNetAssets = calcNciPurchaseShare(row.netAssetsFV ?? 0, row.addedRatio ?? 0)
  const equityAdjustment = calcNciEquityAdjustment(purchaseCost, shareOfNetAssets)
  const carryingAfterPurchase = round2(parseNum(row.priorCarryingAmount) + purchaseCost)
  return {
    ...row,
    purchaseCost,
    shareOfNetAssets,
    equityAdjustment,
    carryingAfterPurchase,
  }
}

export function recalcPartialDisposalRow(row: G7PartialDisposalRow): G7PartialDisposalRow {
  const consideration = calcConsiderationTotal(
    row.considerationCash ?? 0,
    row.considerationNonCashFV ?? 0,
    row.considerationDebtBV ?? 0,
    row.considerationEquityFace ?? 0,
    row.considerationContingent ?? 0,
  )
  const individualGain = calcPartialDisposalIndividualGain(
    consideration,
    row.bookValueAtDisposal ?? 0,
    row.reducedRatio ?? 0,
    row.originalRatio ?? 0,
  )
  const consolShare = calcPartialDisposalConsolShare(row.netAssetsFV ?? 0, row.reducedRatio ?? 0)
  const consolEquityAdj = calcPartialDisposalConsolAdjustment(consideration, consolShare)
  return {
    ...row,
    consideration,
    individualGain,
    consolShare,
    consolEquityAdj,
  }
}

/** 兼容旧版成本法滚存行 → 迁移为股利测算行 */
export function migrateLegacyCostMethodRow(raw: Record<string, any>, seq: number): G7DividendRow {
  return recalcDividendRow({
    ...createDividendRow(seq, raw.investeeName || raw.companyName || ''),
    shareholdingRatio: nullableNumber(raw.shareholdingRatio),
    declaredAmount: nullableNumber(raw.declaredDividend ?? raw.declaredAmount),
    recordedDividend: nullableNumber(raw.recordedDividend ?? raw.investmentIncome),
    auditConclusion: (raw.auditConclusion as G7SubsequentAuditConclusion) || '',
  })
}

export function normalizeSubsequentRows(rawRows: unknown[]): G7SubsequentStoredRow[] {
  if (!Array.isArray(rawRows) || rawRows.length === 0) return []
  const result: G7SubsequentStoredRow[] = []
  let divSeq = 0
  let nciSeq = 0
  let pdSeq = 0

  for (const raw of rawRows) {
    if (!raw || typeof raw !== 'object') continue
    const r = raw as Record<string, any>
    const section = r.section as string | undefined

    if (section === 'nci') {
      nciSeq += 1
      result.push(recalcNciPurchaseRow({
        ...createNciPurchaseRow(nciSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('nci'),
        section: 'nci',
        seq: nciSeq,
      }))
      continue
    }

    if (section === 'partialDisposal') {
      pdSeq += 1
      result.push(recalcPartialDisposalRow({
        ...createPartialDisposalRow(pdSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('pd'),
        section: 'partialDisposal',
        seq: pdSeq,
      }))
      continue
    }

    if (section === 'dividend') {
      divSeq += 1
      result.push(recalcDividendRow({
        ...createDividendRow(divSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('div'),
        section: 'dividend',
        seq: divSeq,
      }))
      continue
    }

    // 无 section：按特征字段推断
    if (r.addedRatio != null || (r.purchaseCost != null && r.priorCarryingAmount != null)) {
      nciSeq += 1
      result.push(recalcNciPurchaseRow({
        ...createNciPurchaseRow(nciSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('nci'),
        section: 'nci',
        seq: nciSeq,
      }))
      continue
    }

    if (r.reducedRatio != null || r.bookValueAtDisposal != null) {
      pdSeq += 1
      result.push(recalcPartialDisposalRow({
        ...createPartialDisposalRow(pdSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('pd'),
        section: 'partialDisposal',
        seq: pdSeq,
      }))
      continue
    }

    if (r.declaredAmount != null || r.declarationDate != null || r.distributionPlan != null) {
      divSeq += 1
      result.push(recalcDividendRow({
        ...createDividendRow(divSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('div'),
        section: 'dividend',
        seq: divSeq,
      }))
      continue
    }

    // 旧版成本法滚存：有 openingBalance / closingBalance 等字段
    if (r.openingBalance != null || r.closingBalance != null || r.declaredDividend != null) {
      divSeq += 1
      result.push(migrateLegacyCostMethodRow(r, divSeq))
      continue
    }

    // 兜底：有公司名则进股利区
    if (r.companyName || r.investeeName) {
      divSeq += 1
      result.push(recalcDividendRow({
        ...createDividendRow(divSeq, r.companyName || r.investeeName || ''),
        ...r,
        id: r.id || uid('div'),
        section: 'dividend',
        seq: divSeq,
      }))
    }
  }
  return result
}

export function validateSubsequentRows(
  rows: G7SubsequentStoredRow[],
  opts?: { materialityLevel?: number },
): G7SubsequentIssue[] {
  const issues: G7SubsequentIssue[] = []
  const materiality = parseNum(opts?.materialityLevel)

  for (const row of rows) {
    if (row.section === 'dividend') {
      if (!row.companyName.trim()) {
        issues.push({ severity: 'warning', rowId: row.id, message: `股利测算第${row.seq}行：公司名称为空` })
      }
      const ratio = row.shareholdingRatio
      if (ratio != null && (ratio < 0 || ratio > 1)) {
        issues.push({ severity: 'error', rowId: row.id, message: `「${row.companyName || row.seq}」持股比例应在 0~1` })
      }
      if (Math.abs(row.variance) > 0.01) {
        const overMateriality = materiality > 0 && Math.abs(row.variance) > materiality
        issues.push({
          severity: overMateriality ? 'error' : 'warning',
          rowId: row.id,
          message: overMateriality
            ? `「${row.companyName || row.seq}」股利差异 ${row.variance.toLocaleString('zh-CN')} 超过重要性水平`
            : `「${row.companyName || row.seq}」应享股利与入账差异 ${row.variance.toLocaleString('zh-CN')}`,
        })
      }
    }

    if (row.section === 'nci') {
      if (!row.companyName.trim()) {
        issues.push({ severity: 'warning', rowId: row.id, message: `购买少数股权第${row.seq}行：公司名称为空` })
      }
      const added = row.addedRatio
      if (added != null && (added <= 0 || added > 1)) {
        issues.push({ severity: 'error', rowId: row.id, message: `「${row.companyName || row.seq}」新增持股比例①应在 (0,1]` })
      }
      const orig = row.originalRatio ?? 0
      if (orig > 0 && added != null && orig + added > 1.000001) {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」原持股+新增持股不能超过 100%`,
        })
      }
      const adjSum = round2(
        parseNum(row.adjCapitalReserve) + parseNum(row.adjSurplusReserve) + parseNum(row.adjRetainedEarnings),
      )
      const hasSplit =
        row.adjCapitalReserve != null || row.adjSurplusReserve != null || row.adjRetainedEarnings != null
      if (hasSplit && Math.abs(adjSum - row.equityAdjustment) > 0.01) {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」资本公积/盈余公积/未分配利润分拆合计 ≠ 权益调整⑤`,
        })
      } else if (!hasSplit && Math.abs(row.equityAdjustment) > 0.01) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」权益调整⑤未分拆至资本公积/留存收益（可点「一键填资本公积」）`,
        })
      }
      if (materiality > 0 && Math.abs(row.equityAdjustment) > materiality) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」合并权益调整⑤绝对值超过重要性水平`,
        })
      }
    }

    if (row.section === 'partialDisposal') {
      if (!row.companyName.trim()) {
        issues.push({ severity: 'warning', rowId: row.id, message: `不丧失控制权处置第${row.seq}行：公司名称为空` })
      }
      const orig = row.originalRatio ?? 0
      const reduced = row.reducedRatio ?? 0
      const remaining = orig - reduced
      if (orig > 0 && reduced > orig) {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」减少持股比例③不能大于原持股比例②`,
        })
      }
      if (orig > 0 && reduced > 0 && remaining <= 0) {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」处置后应仍保持控制（剩余比例须 > 0）；丧失控制权请用 G7-11/G7-12`,
        })
      } else if (orig > 0 && reduced > 0 && remaining > 0 && remaining <= 0.5) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」处置后剩余持股 ${(remaining * 100).toFixed(2)}% ≤ 50%，请复核是否仍保持控制；若丧失控制请改用 G7-11/G7-12`,
        })
      }
      const adjSum = round2(
        parseNum(row.adjCapitalReserve) + parseNum(row.adjSurplusReserve) + parseNum(row.adjRetainedEarnings),
      )
      const hasSplit =
        row.adjCapitalReserve != null || row.adjSurplusReserve != null || row.adjRetainedEarnings != null
      if (hasSplit && Math.abs(adjSum - row.consolEquityAdj) > 0.01) {
        issues.push({
          severity: 'error',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」合并权益调整分拆合计 ≠ ⑧`,
        })
      } else if (!hasSplit && Math.abs(row.consolEquityAdj) > 0.01) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」合并权益调整⑧未分拆（可点「一键填资本公积」）`,
        })
      }
      if (materiality > 0 && Math.abs(row.consolEquityAdj) > materiality) {
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${row.companyName || row.seq}」合并权益调整⑧绝对值超过重要性水平`,
        })
      }
    }
  }

  return issues
}

/** 一键将权益调整全额填入资本公积（盈余公积/未分配利润清零） */
export function fillNciEquitySplitToCapitalReserve(row: G7NciPurchaseRow): G7NciPurchaseRow {
  return {
    ...row,
    adjCapitalReserve: row.equityAdjustment,
    adjSurplusReserve: 0,
    adjRetainedEarnings: 0,
  }
}

export function fillPartialDisposalEquitySplitToCapitalReserve(row: G7PartialDisposalRow): G7PartialDisposalRow {
  return {
    ...row,
    adjCapitalReserve: row.consolEquityAdj,
    adjSurplusReserve: 0,
    adjRetainedEarnings: 0,
  }
}

/** 解析持久化载荷：兼容旧版纯数组 / 新版 { rows, materialityLevel } */
export function parseSubsequentPayload(raw: unknown): {
  rows: G7SubsequentStoredRow[]
  materialityLevel: number
} {
  if (raw == null || raw === '') return { rows: [], materialityLevel: 0 }
  let parsed: any = raw
  if (typeof raw === 'string') {
    try { parsed = JSON.parse(raw) } catch { return { rows: [], materialityLevel: 0 } }
  }
  if (Array.isArray(parsed)) {
    return { rows: normalizeSubsequentRows(parsed), materialityLevel: 0 }
  }
  if (parsed && typeof parsed === 'object') {
    const rows = Array.isArray(parsed.rows) ? normalizeSubsequentRows(parsed.rows) : []
    return {
      rows,
      materialityLevel: parseNum(parsed.materialityLevel ?? parsed.materiality_level),
    }
  }
  return { rows: [], materialityLevel: 0 }
}
