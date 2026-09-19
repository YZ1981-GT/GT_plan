/**
 * G7-16 未确认投资损失 — 纯函数模型（CAS2 第44条瀑布、校验、hydrate）
 */
import { parseNum } from './useG7EquityMethodFormulaEngine'
import type { UnrecognizedLossRow } from './useG7EquityMethodFormData'

export type UnrecognizedLossRowLike = Partial<UnrecognizedLossRow> & {
  investeeName?: string
  allocationManual?: boolean
  currentChangeManual?: boolean
}

export interface UnrecognizedLossValidationIssue {
  level: 'error' | 'warning'
  investeeName: string
  message: string
}

const ROUND2 = (n: number) => Math.round(n * 100) / 100

/** 从 checklist 原始值解析行数组（兼容扁平数组 / {rows} / {data|items}） */
export function parseUnrecognizedLossRowsPayload(raw: unknown): any[] {
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

/**
 * CAS2 第44条瀑布：超额亏损依次冲减 投资→长应收→其他权益；
 * 预计负债需职业判断，默认不自动确认（剩余记入未确认损失）。
 */
export function allocateExcessLossWaterfall(row: UnrecognizedLossRowLike): {
  reduceInvestment: number
  reduceLongTermReceivable: number
  reduceOtherEquity: number
  recognizeEstimatedLiability: number
} {
  let remaining = Math.max(0, parseNum(row.excessLoss))
  const reduceInvestment = ROUND2(Math.min(remaining, Math.max(0, parseNum(row.investmentBookValue))))
  remaining = ROUND2(remaining - reduceInvestment)
  const reduceLongTermReceivable = ROUND2(Math.min(remaining, Math.max(0, parseNum(row.longTermReceivable))))
  remaining = ROUND2(remaining - reduceLongTermReceivable)
  const reduceOtherEquity = ROUND2(Math.min(remaining, Math.max(0, parseNum(row.otherLongTermEquity))))
  // 不自动确认预计负债（保留判断空间）
  return {
    reduceInvestment,
    reduceLongTermReceivable,
    reduceOtherEquity,
    recognizeEstimatedLiability: parseNum(row.recognizeEstimatedLiability) || 0,
  }
}

/** 重算合计/超额/未确认/本期变动；可选自动瀑布（非手工锁定时） */
export function recalcUnrecognizedLossRow(
  row: UnrecognizedLossRowLike,
  opts?: { applyWaterfall?: boolean },
): void {
  row.totalLongTermEquity = ROUND2(
    parseNum(row.investmentBookValue)
    + parseNum(row.longTermReceivable)
    + parseNum(row.otherLongTermEquity)
    + parseNum(row.estimatedLiability),
  )

  const diff = parseNum(row.cumulativeLoss) - parseNum(row.totalLongTermEquity)
  row.excessLoss = ROUND2(Math.max(0, diff))

  const applyWaterfall = opts?.applyWaterfall ?? !row.allocationManual
  if (applyWaterfall && parseNum(row.excessLoss) > 0) {
    const alloc = allocateExcessLossWaterfall(row)
    row.reduceInvestment = alloc.reduceInvestment
    row.reduceLongTermReceivable = alloc.reduceLongTermReceivable
    row.reduceOtherEquity = alloc.reduceOtherEquity
    // recognizeEstimatedLiability 保留手工值
  } else if (parseNum(row.excessLoss) <= 0 && !row.allocationManual) {
    row.reduceInvestment = 0
    row.reduceLongTermReceivable = 0
    row.reduceOtherEquity = 0
    row.recognizeEstimatedLiability = 0
  }

  row.unrecognizedLoss = ROUND2(Math.max(0,
    parseNum(row.excessLoss)
    - parseNum(row.reduceInvestment)
    - parseNum(row.reduceLongTermReceivable)
    - parseNum(row.reduceOtherEquity)
    - parseNum(row.recognizeEstimatedLiability),
  ))

  if (!row.currentChangeManual) {
    row.currentChange = ROUND2(
      parseNum(row.unrecognizedLoss) - parseNum(row.priorCumulative),
    )
  }
}

export function validateUnrecognizedLossRows(
  rows: UnrecognizedLossRowLike[],
): UnrecognizedLossValidationIssue[] {
  const issues: UnrecognizedLossValidationIssue[] = []
  for (const row of rows) {
    const name = String(row.investeeName || '（未命名）')
    const excess = parseNum(row.excessLoss)
    const r1 = parseNum(row.reduceInvestment)
    const r2 = parseNum(row.reduceLongTermReceivable)
    const r3 = parseNum(row.reduceOtherEquity)
    const r4 = parseNum(row.recognizeEstimatedLiability)
    const sum = ROUND2(r1 + r2 + r3 + r4)

    if (r1 > parseNum(row.investmentBookValue) + 0.005) {
      issues.push({
        level: 'error',
        investeeName: name,
        message: `冲减投资 ${r1} 超过投资账面 ${parseNum(row.investmentBookValue)}`,
      })
    }
    if (r2 > parseNum(row.longTermReceivable) + 0.005) {
      issues.push({
        level: 'error',
        investeeName: name,
        message: `冲减长应收 ${r2} 超过长期应收款 ${parseNum(row.longTermReceivable)}`,
      })
    }
    if (r3 > parseNum(row.otherLongTermEquity) + 0.005) {
      issues.push({
        level: 'error',
        investeeName: name,
        message: `冲减其他权益 ${r3} 超过其他实质长期权益 ${parseNum(row.otherLongTermEquity)}`,
      })
    }
    if (excess > 0 && sum > excess + 0.005) {
      issues.push({
        level: 'error',
        investeeName: name,
        message: `各项冲减合计 ${sum} 超过超额亏损 ${excess}`,
      })
    }
    if (excess > 0 && sum + 0.005 < excess && parseNum(row.unrecognizedLoss) <= 0) {
      issues.push({
        level: 'warning',
        investeeName: name,
        message: '超额亏损未完全分配且未确认损失为0，请复核冲减与备查登记',
      })
    }
    // 利润恢复：本期变动为负时提示反序恢复
    if (parseNum(row.currentChange) < -0.005) {
      issues.push({
        level: 'warning',
        investeeName: name,
        message: '本期变动为负（利润恢复），应按相反顺序恢复：先预计负债→长应收→投资',
      })
    }
  }
  return issues
}

/**
 * 利润恢复：按 CAS2 相反顺序冲回已冲减金额（预计负债→其他权益→长应收→投资）。
 * recoverAmount 默认取 MAX(0, 上期累计−期末未确认, −min(0,本期变动))。
 */
export function applyProfitRecoveryReverseOrder(
  row: UnrecognizedLossRowLike,
  recoverAmount?: number,
): {
  recovered: number
  detail: { liability: number; other: number; receivable: number; investment: number }
} {
  const fromPriorGap = Math.max(
    0,
    parseNum(row.priorCumulative) - parseNum(row.unrecognizedLoss),
  )
  const fromChange = Math.max(0, -Math.min(0, parseNum(row.currentChange)))
  let remaining = ROUND2(
    recoverAmount != null ? Math.max(0, recoverAmount) : Math.max(fromPriorGap, fromChange),
  )
  const detail = { liability: 0, other: 0, receivable: 0, investment: 0 }
  if (remaining <= 0) {
    return { recovered: 0, detail }
  }

  const take = (available: number): number => {
    const amt = ROUND2(Math.min(remaining, Math.max(0, available)))
    remaining = ROUND2(remaining - amt)
    return amt
  }

  detail.liability = take(parseNum(row.recognizeEstimatedLiability))
  row.recognizeEstimatedLiability = ROUND2(
    parseNum(row.recognizeEstimatedLiability) - detail.liability,
  )
  detail.other = take(parseNum(row.reduceOtherEquity))
  row.reduceOtherEquity = ROUND2(parseNum(row.reduceOtherEquity) - detail.other)
  detail.receivable = take(parseNum(row.reduceLongTermReceivable))
  row.reduceLongTermReceivable = ROUND2(
    parseNum(row.reduceLongTermReceivable) - detail.receivable,
  )
  detail.investment = take(parseNum(row.reduceInvestment))
  row.reduceInvestment = ROUND2(parseNum(row.reduceInvestment) - detail.investment)

  row.allocationManual = true
  recalcUnrecognizedLossRow(row, { applyWaterfall: false })
  const recovered = ROUND2(
    detail.liability + detail.other + detail.receivable + detail.investment,
  )
  return { recovered, detail }
}

/**
 * 从上期/期初 G7-16（或披露口径行）提取 priorCumulative：
 * 优先 priorCumulative/closingCumulative，否则用 unrecognizedLoss 作为上期期末。
 */
export function extractPriorCumulativeMap(raw: unknown): Map<string, number> {
  const result = new Map<string, number>()
  for (const r of parseUnrecognizedLossRowsPayload(raw)) {
    const name = String(r.investeeName ?? r.investee_name ?? '').trim()
    if (!name) continue
    const prior = r.priorCumulative ?? r.prior_cumulative
    const closing = r.closingCumulative ?? r.closing_cumulative ?? r.unrecognizedLoss ?? r.unrecognized_loss
    if (prior != null && prior !== '') {
      result.set(name, ROUND2(Math.max(0, parseNum(prior))))
    } else if (closing != null && closing !== '') {
      result.set(name, ROUND2(Math.max(0, parseNum(closing))))
    }
  }
  return result
}

/** 从关联行提取长期应收（实质净投资）候选 */
export function extractLongTermReceivableFromRelated(row: Record<string, unknown> | null | undefined): number {
  if (!row) return 0
  return ROUND2(Math.max(0, parseNum(
    row.longTermReceivable
    ?? row.long_term_receivable
    ?? row.ltReceivable
    ?? row.substantiveLongTermReceivable
    ?? row.netInvestmentReceivable,
  )))
}

/**
 * 从 G7-5 财务信息提取「累计亏损」代理值：
 * 优先报表项目名含「累计亏损」；否则取负的未分配利润绝对值；再否则取负净资产绝对值。
 */
export function extractCumulativeLossFromG75(
  g75Raw: unknown,
): Map<string, number> {
  const result = new Map<string, number>()
  const parsed = typeof g75Raw === 'string'
    ? (() => { try { return JSON.parse(g75Raw) } catch { return null } })()
    : g75Raw
  if (parsed == null) return result

  type Item = { investeeName: string; reportItem: string; currentAmount: number }
  const items: Item[] = []

  if (Array.isArray((parsed as any)?.groups)) {
    for (const g of (parsed as any).groups) {
      const name = String(g.investeeName ?? g.name ?? '').trim()
      for (const r of g.rows || []) {
        items.push({
          investeeName: name,
          reportItem: String(r.reportItem ?? r.report_item ?? ''),
          currentAmount: parseNum(r.currentAmount ?? r.current_amount),
        })
      }
    }
  } else {
    const rows = Array.isArray(parsed)
      ? parsed
      : Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : []
    for (const r of rows) {
      items.push({
        investeeName: String(r.investeeName ?? r.investee_name ?? '').trim(),
        reportItem: String(r.reportItem ?? r.report_item ?? ''),
        currentAmount: parseNum(r.currentAmount ?? r.current_amount),
      })
    }
  }

  const byName = new Map<string, Item[]>()
  for (const it of items) {
    if (!it.investeeName) continue
    const list = byName.get(it.investeeName) || []
    list.push(it)
    byName.set(it.investeeName, list)
  }

  for (const [name, list] of byName) {
    const explicit = list.find(i => /累计亏损/.test(i.reportItem))
    if (explicit) {
      result.set(name, ROUND2(Math.abs(explicit.currentAmount)))
      continue
    }
    const re = list.find(i => /未分配利润/.test(i.reportItem))
    if (re && re.currentAmount < 0) {
      result.set(name, ROUND2(Math.abs(re.currentAmount)))
      continue
    }
    const equity = list.find(i => /所有者权益|净资产/.test(i.reportItem))
    if (equity && equity.currentAmount < 0) {
      result.set(name, ROUND2(Math.abs(equity.currentAmount)))
    }
  }
  return result
}
