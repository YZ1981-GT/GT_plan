/**
 * G7-13 投资成本测试 — 纯函数模型（hydrate / recalc / G7-5 FV / 校验 / 廉价购买分录）
 */
import {
  calcGoodwill,
  calcInvestmentCost,
  calcShareOfNetAssets,
  parseNum,
} from './useG7EquityMethodFormulaEngine'
import type { InvestmentCostTestRow } from './useG7EquityMethodFormData'
import {
  G713_BARGAIN_SOURCE_KIND,
  type SuggestedAdjustmentLine,
} from '../g7-long-term-equity-method/calculation/g7EquityMethodCalcModel'
import { G7_GROSS_FALLBACK_STANDARD } from './g7AccountScope'

export type InvestmentCostRowLike = Partial<InvestmentCostTestRow> & {
  investeeName?: string
  investmentRatio?: number
}

const ROUND2 = (n: number) => Math.round(n * 100) / 100
const PENNY = 0.005

/** 兼容扁平数组 / {rows} / {data|items} */
export function parseInvestmentCostRowsPayload(raw: unknown): any[] {
  if (raw == null || raw === '') return []
  let parsed: unknown = raw
  if (typeof raw === 'string') {
    try { parsed = JSON.parse(raw) } catch { return [] }
  }
  if (Array.isArray(parsed)) return parsed
  if (parsed && typeof parsed === 'object') {
    const o = parsed as Record<string, unknown>
    if (Array.isArray(o.rows)) return o.rows
    if (Array.isArray(o.data)) return o.data
    if (Array.isArray(o.items)) return o.items
  }
  return []
}

export function createEmptyInvestmentCostRow(
  seq: number,
  investeeName = '',
): InvestmentCostTestRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    investeeId: '',
    investDate: '',
    mergeType: '非合并',
    consideration: 0,
    directCosts: 0,
    initialCost: 0,
    netAssetFairValue: 0,
    shareOfNetAssets: 0,
    difference: 0,
    differenceNature: '商誉',
    accountingTreatment: '',
    fvAdjustmentDetail: '',
    adjustedNetAssets: 0,
    adjustedShareOfNetAssets: 0,
    investmentRatio: 0,
    auditConclusion: '无差异',
    indexRef: '',
  }
}

/** 重算初始成本 / 享有份额 / 差额 / 差额性质；ratio 优先行内 investmentRatio */
export function recalcInvestmentCostRow(
  row: InvestmentCostRowLike,
  ratioFallback = 0,
): void {
  let ratio = parseNum(row.investmentRatio) || ratioFallback || 0
  // Excel / 旧存可能是百分数
  if (Math.abs(ratio) > 1.0001) ratio = ratio / 100
  if (ratio) row.investmentRatio = ratio

  row.initialCost = calcInvestmentCost(
    parseNum(row.consideration),
    parseNum(row.directCosts),
  )
  row.shareOfNetAssets = calcShareOfNetAssets(
    parseNum(row.netAssetFairValue),
    parseNum(row.investmentRatio) || ratio,
  )
  row.difference = calcGoodwill(
    parseNum(row.initialCost),
    parseNum(row.shareOfNetAssets),
  )
  row.differenceNature = parseNum(row.difference) >= 0 ? '商誉' : '营业外收入'

  // 调整后享有份额 = 调整后净资产 × 持股比例（与享有份额同口径）
  const adjNet = parseNum(row.adjustedNetAssets)
  const effectiveRatio = parseNum(row.investmentRatio) || ratio
  if (Math.abs(adjNet) > 0.005 && effectiveRatio) {
    row.adjustedShareOfNetAssets = calcShareOfNetAssets(adjNet, effectiveRatio)
  } else if (!(Math.abs(adjNet) > 0.005)) {
    // 未填调整后净资产时清空公式列，避免残留手填值误同步 FV
    row.adjustedShareOfNetAssets = 0
  }
}

export function hydrateInvestmentCostRows(raw: unknown): InvestmentCostTestRow[] {
  const list = parseInvestmentCostRowsPayload(raw)
  if (!list.length) return []
  const out: InvestmentCostTestRow[] = []
  for (let i = 0; i < list.length; i++) {
    const rawRow = list[i]
    const row: InvestmentCostTestRow = {
      ...createEmptyInvestmentCostRow(i + 1, String(rawRow.investeeName || '')),
      ...rawRow,
      seq: i + 1,
      id: rawRow.id || crypto.randomUUID(),
      investeeId: String(rawRow.investeeId ?? rawRow.investee_id ?? ''),
      investmentRatio: parseNum(rawRow.investmentRatio ?? rawRow.investment_ratio),
    }
    recalcInvestmentCostRow(row)
    out.push(row)
  }
  return out
}

export type G75NetAssetFvEntry = {
  investeeName: string
  investeeId: string
  /** 账面净资产/所有者权益（FV 代理，需评估复核） */
  bookNetAssets: number
  audited: boolean
}

/**
 * 从 G7-5 提取所有者权益/净资产本期金额，作为投资成本测试「净资产公允价值」代理。
 * 优先已审；同名多行取最后一条已审，否则取最后一条有效金额。
 */
export function extractNetAssetFvFromG75(g75Raw: unknown): G75NetAssetFvEntry[] {
  const parsed = typeof g75Raw === 'string'
    ? (() => { try { return JSON.parse(g75Raw) } catch { return null } })()
    : g75Raw
  if (parsed == null) return []

  type Item = {
    investeeName: string
    investeeId: string
    reportItem: string
    currentAmount: number
    auditStatus: string
  }
  const items: Item[] = []

  const pushItem = (r: any, fallbackName = '', fallbackId = '') => {
    const name = String(r.investeeName ?? r.investee_name ?? fallbackName ?? '').trim()
    const id = String(r.investeeId ?? r.investee_id ?? fallbackId ?? '').trim()
    items.push({
      investeeName: name,
      investeeId: id,
      reportItem: String(r.reportItem ?? r.report_item ?? ''),
      currentAmount: parseNum(r.currentAmount ?? r.current_amount),
      auditStatus: String(r.auditStatus ?? r.audit_status ?? '').trim(),
    })
  }

  if (Array.isArray((parsed as any)?.groups)) {
    for (const g of (parsed as any).groups) {
      const name = String(g.investeeName ?? g.name ?? '').trim()
      const id = String(g.investeeId ?? g.investee_id ?? '').trim()
      for (const r of g.rows || []) pushItem(r, name, id)
    }
  } else {
    const rows = Array.isArray(parsed)
      ? parsed
      : Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : []
    for (const r of rows) pushItem(r)
  }

  const byKey = new Map<string, G75NetAssetFvEntry>()
  for (const it of items) {
    if (!it.investeeName && !it.investeeId) continue
    if (!/所有者权益|净资产/.test(it.reportItem)) continue
    const audited = !it.auditStatus || it.auditStatus === '已审'
    const key = it.investeeId ? `id:${it.investeeId}` : `name:${it.investeeName}`
    const prev = byKey.get(key)
    // 已审覆盖未审；同级取后写
    if (prev && prev.audited && !audited) continue
    byKey.set(key, {
      investeeName: it.investeeName || prev?.investeeName || '',
      investeeId: it.investeeId || prev?.investeeId || '',
      bookNetAssets: ROUND2(it.currentAmount),
      audited,
    })
  }
  return [...byKey.values()]
}

export type InvestmentCostValidationIssue = {
  rowId: string
  investeeName: string
  level: 'warning' | 'error'
  code: string
  message: string
}

/** 行级校验：比例/差额性质/调整后份额/合并类型等 */
export function validateInvestmentCostRows(
  rows: InvestmentCostRowLike[],
): InvestmentCostValidationIssue[] {
  const issues: InvestmentCostValidationIssue[] = []
  for (const r of rows) {
    const name = String(r.investeeName || '').trim() || '(未命名)'
    const id = String(r.id || name)
    const ratio = parseNum(r.investmentRatio)
    const diff = parseNum(r.difference)
    const nature = String(r.differenceNature || '')
    const fv = parseNum(r.netAssetFairValue)
    const consideration = parseNum(r.consideration)
    const adjustedShare = parseNum(r.adjustedShareOfNetAssets)
    const adjustedNet = parseNum(r.adjustedNetAssets)

    if ((consideration > PENNY || fv > PENNY) && !(ratio > PENNY)) {
      issues.push({
        rowId: id,
        investeeName: name,
        level: 'error',
        code: 'missing-ratio',
        message: `${name}：已填对价/净资产但持股比例为空，享有份额将为 0`,
      })
    }
    if (diff > PENNY && nature.includes('营业外')) {
      issues.push({
        rowId: id,
        investeeName: name,
        level: 'warning',
        code: 'nature-mismatch-goodwill',
        message: `${name}：差额为正但性质为营业外收入，请复核`,
      })
    }
    if (diff < -PENNY && nature.includes('商誉')) {
      issues.push({
        rowId: id,
        investeeName: name,
        level: 'warning',
        code: 'nature-mismatch-bargain',
        message: `${name}：差额为负但性质为商誉，请复核`,
      })
    }
    if (
      Math.abs(adjustedNet) > PENNY
      && Math.abs(adjustedShare) > PENNY
      && !String(r.fvAdjustmentDetail || '').trim()
    ) {
      issues.push({
        rowId: id,
        investeeName: name,
        level: 'warning',
        code: 'fv-detail-empty',
        message: `${name}：已填调整后净资产但 FV 调整明细为空`,
      })
    }
    const mergeType = String(r.mergeType || '')
    if (mergeType && mergeType !== '合并' && mergeType !== '非合并') {
      issues.push({
        rowId: id,
        investeeName: name,
        level: 'warning',
        code: 'merge-type',
        message: `${name}：合并/非合并取值异常（${mergeType}）`,
      })
    }
  }
  return issues
}

/**
 * 廉价购买（负差额）→ 建议 AJE：借 长期股权投资 / 贷 营业外收入
 * 金额 = |差额|；仅草稿，需人工复核后入账。
 */
export function buildBargainSuggestedAdjustments(
  rows: InvestmentCostRowLike[],
): SuggestedAdjustmentLine[] {
  const out: SuggestedAdjustmentLine[] = []
  for (const r of rows) {
    const name = String(r.investeeName || '').trim()
    const diff = parseNum(r.difference)
    if (!name || !(diff < -PENNY)) continue
    const amt = ROUND2(Math.abs(diff))
    const desc = `【G7-13】${name} 廉价购买利得（调增初始投资成本）`
    const remark = `来源：G7-13差额=${diff};sourceKind=${G713_BARGAIN_SOURCE_KIND}`
    const baseId = `g713-bargain-${String(r.id || name).slice(0, 12)}`
    out.push({
      id: `${baseId}-dr`,
      investeeName: name,
      description: desc,
      category: '账项调整',
      reportItem: '长期股权投资',
      accountCode: G7_GROSS_FALLBACK_STANDARD,
      accountName: '长期股权投资',
      debitAmount: amt,
      creditAmount: 0,
      indexRef: String(r.indexRef || 'G7-13'),
      remark,
      source: 'bargainPurchase',
      sourceKind: G713_BARGAIN_SOURCE_KIND,
    })
    out.push({
      id: `${baseId}-cr`,
      investeeName: name,
      description: desc,
      category: '账项调整',
      reportItem: '营业外收入',
      accountCode: '6301',
      accountName: '营业外收入',
      debitAmount: 0,
      creditAmount: amt,
      indexRef: String(r.indexRef || 'G7-13'),
      remark,
      source: 'bargainPurchase',
      sourceKind: G713_BARGAIN_SOURCE_KIND,
    })
  }
  return out
}
