/**
 * G10 底稿目录 — 跨表勾稽汇总（CHK-01 ~ CHK-11）
 */
import { G10_ADJUDICATION_ITEMS, G10_LIABILITY_LINE_SUFFIXES } from './g10AdjudicationItems'
import { G10_ADJ_ROWS_KEY, parseG10AdjStore, g10RowClosingAdjusted, g10RowOpeningAdjusted, compareG10Adj3VsG101Writeback, summarizeG10Adjustment } from './g10AdjStorage'
import { G10_CHANGE_RATE_THRESHOLD } from './g10Constants'
import { calcBookSectionTotal, G10_DETAIL_ROWS_KEY, G10_FV_DIFF_THRESHOLD, parseG10DetailRows } from './g10CrossHelpers'
import {
  evaluateG10DerivativeWizard,
  parseG10DerivativeWizardState,
} from './g10DerivativeDecision'
import {
  G10_ADJUDICATED_KEY,
  G10_CROSS_TOLERANCE,
  G10_DETAIL_KEY,
  buildG10DisclosureAmountsFromResponses,
  movementClosingSum,
  soeCurrentSum,
  defaultG10ListedDiscStore,
  defaultG10SoeDiscStore,
} from './g10DisclosureFromAdj'
import { G10_FV_KEY, G10_ADJ_KEY } from './g10FvCrossHelpers'
import {
  calcG10SampleAbsAmount,
  g10VoucherInspectionRatio,
  parseG10SamplingParams,
} from './g10VoucherConstants'
import { listG10Fv5VsG96AssetMismatches } from './g10L3CrossHelpers'
import { countG10AdjBySource } from './g10AdjSource'
import {
  calcAdjustedAmount,
  calcBookFromParts,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
  parseNum,
} from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export type G10CrossCheckStatus = 'ok' | 'warn' | 'error' | 'info'

export interface G10CrossCheckItem {
  code: string
  name: string
  status: G10CrossCheckStatus
  detail: string
}

function buildAdjRow(store: ReturnType<typeof parseG10AdjStore>, rowKey: string) {
  const raw = store[rowKey] ?? {}
  const openingAdjusted = g10RowOpeningAdjusted(raw)
  const closingAdjusted = g10RowClosingAdjusted(raw)
  const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
  return {
    rowKey,
    openingAdjusted,
    closingAdjusted,
    changeRate,
    reasonAnalysis: String(raw.reasonAnalysis ?? ''),
    reasonRequired: isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD),
  }
}

function findThreePartMismatches(store: ReturnType<typeof parseG10AdjStore>): number {
  let n = 0
  for (const suffix of G10_LIABILITY_LINE_SUFFIXES) {
    if (suffix === 'trading_liability' || suffix === 'designated_fvtpl') continue
    const init = buildAdjRow(store, `init_${suffix}`)
    const fv = buildAdjRow(store, `fv_${suffix}`)
    const book = buildAdjRow(store, `book_${suffix}`)
    for (const field of ['openingAdjusted', 'closingAdjusted'] as const) {
      const initVal = init[field]
      const fvVal = fv[field]
      const bookVal = book[field]
      if (Math.abs(initVal) < 0.01 && Math.abs(fvVal) < 0.01 && Math.abs(bookVal) < 0.01) continue
      if (Math.abs(calcBookFromParts(initVal, fvVal) - bookVal) > G10_CROSS_TOLERANCE) n += 1
    }
  }
  return n
}

function parseDetailClosingTotal(json: string | null | undefined): number | null {
  if (!json) return null
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr) || !arr.length) return null
    return calcSubtotal(arr.map((r: any) => parseNum(r.closingAdjusted ?? r.closingBalance)))
  } catch {
    return null
  }
}

function disclosureListedClosing(m: Map<string, ChecklistResponse>): number | null {
  const raw = m.get('G10-disclosure-listed')?.remark
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed?.version === 2) return movementClosingSum(parsed as ReturnType<typeof defaultG10ListedDiscStore>)
  } catch { /* ignore */ }
  return null
}

function disclosureSoeClosing(m: Map<string, ChecklistResponse>): number | null {
  const raw = m.get('G10-disclosure-soe')?.remark
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed?.version === 2) return soeCurrentSum(parsed as ReturnType<typeof defaultG10SoeDiscStore>)
  } catch { /* ignore */ }
  return null
}

function parseJsonRows(json: string | null | undefined): any[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
    return []
  } catch {
    return []
  }
}

function fvAuditedTotal(m: Map<string, ChecklistResponse>): number | null {
  const rows = parseJsonRows(m.get(G10_FV_KEY)?.remark)
  if (!rows.length) return null
  return calcSubtotal(rows.map((r) => parseNum(r.closingAuditedFV)))
}

function fvL3AuditedTotal(m: Map<string, ChecklistResponse>): number | null {
  const rows = parseJsonRows(m.get(G10_FV_KEY)?.remark)
    .filter((r) => String(r.fairValueLevel ?? '').trim() === 'Level3')
  if (!rows.length) return null
  return calcSubtotal(rows.map((r) => parseNum(r.closingAuditedFV)))
}

function l3ReportedClosingTotal(m: Map<string, ChecklistResponse>): number | null {
  const rows = parseJsonRows(m.get('G10-l3-rows')?.remark)
  if (!rows.length) return null
  return calcSubtotal(rows.map((r) => parseNum(r.reportedClosing)))
}

function l3VarianceRowCount(m: Map<string, ChecklistResponse>): number {
  return parseJsonRows(m.get('G10-l3-rows')?.remark)
    .filter((r) => Math.abs(parseNum(r.reportedClosing) - parseNum(r.closingBalance)) > G10_FV_DIFF_THRESHOLD)
    .length
}

function voucherLowRatioScopes(m: Map<string, ChecklistResponse>): string[] {
  const params = parseG10SamplingParams(m.get('G10-vc-params')?.remark)
  const rows = parseJsonRows(m.get('G10-voucher-rows')?.remark)
  const low: string[] = []
  for (const scope of ['current', 'subsequent'] as const) {
    const scopeRows = rows.filter((r) => (r.periodScope ?? 'current') === scope)
    const pop = params[scope].populationAmount
    const ratio = g10VoucherInspectionRatio(calcG10SampleAbsAmount(scopeRows), pop)
    if (pop > 0.005 && ratio != null && ratio < 0.3) {
      low.push(scope === 'current' ? '本期' : '期后')
    }
  }
  return low
}

function derivativeMissingCompliance(m: Map<string, ChecklistResponse>): number {
  return parseJsonRows(m.get('G10-derivative-rows')?.remark)
    .filter((r) => !r.compliance).length
}

function countG10ZeroAmountMemoGroups(rows: Record<string, unknown>[]): number {
  const bySummary = new Map<string, { debit: number; credit: number }>()
  for (const row of rows) {
    const summary = String((row as { summary?: string }).summary || '').trim()
    if (!summary) continue
    const bucket = bySummary.get(summary) ?? { debit: 0, credit: 0 }
    bucket.debit += parseNum((row as { debitAmount?: number }).debitAmount)
    bucket.credit += parseNum((row as { creditAmount?: number }).creditAmount)
    bySummary.set(summary, bucket)
  }
  let n = 0
  for (const v of bySummary.values()) {
    if (Math.abs(v.debit) < 0.005 && Math.abs(v.credit) < 0.005) n += 1
  }
  return n
}

/** 汇总 G10 跨表勾稽状态，供底稿目录看板 */
export function summarizeG10CrossChecks(m: Map<string, ChecklistResponse>): G10CrossCheckItem[] {
  const store = parseG10AdjStore(m.get(G10_ADJ_ROWS_KEY)?.remark)
  const bookTotal = calcBookSectionTotal(store)
  const tb = parseNum(m.get('G10-adj-tb')?.remark)
  const hasTb = m.has('G10-adj-tb')
  const tbVariance = bookTotal - tb

  const threePartCount = findThreePartMismatches(store)

  const detailTotal = parseDetailClosingTotal(m.get(G10_DETAIL_KEY)?.remark)
  const detailVariance = detailTotal != null ? bookTotal - detailTotal : null

  const missingReasons = G10_ADJUDICATION_ITEMS
    .map((d) => buildAdjRow(store, d.rowKey))
    .filter((r) => r.reasonRequired && !r.reasonAnalysis.trim()).length

  const adjudicated = parseNum(m.get(G10_ADJUDICATED_KEY)?.conclusion)
  const listedClosing = disclosureListedClosing(m)
  const soeClosing = disclosureSoeClosing(m)

  const items: G10CrossCheckItem[] = []

  if (!hasTb) {
    items.push({
      code: 'G10-CHK-01',
      name: '试算表勾稽',
      status: 'info',
      detail: '试算表数未录入',
    })
  } else if (Math.abs(tbVariance) > G10_CROSS_TOLERANCE) {
    items.push({
      code: 'G10-CHK-01',
      name: '试算表勾稽',
      status: 'error',
      detail: `(三)合计 ${bookTotal.toFixed(2)} 与试算表 ${tb.toFixed(2)} 差异 ${tbVariance.toFixed(2)}`,
    })
  } else {
    items.push({
      code: 'G10-CHK-01',
      name: '试算表勾稽',
      status: 'ok',
      detail: `与试算表 ${tb.toFixed(2)} 一致`,
    })
  }

  items.push({
    code: 'G10-CHK-02',
    name: '三部分勾稽',
    status: threePartCount > 0 ? 'warn' : 'ok',
    detail: threePartCount > 0 ? `${threePartCount} 处分项 (三)≠(一)+(二)` : '(一)+(二)=(三) 分项一致',
  })

  if (detailTotal == null) {
    items.push({
      code: 'G10-CHK-03',
      name: '明细表勾稽',
      status: 'info',
      detail: 'G10-2 无明细或未填审定合计',
    })
  } else if (detailVariance != null && Math.abs(detailVariance) > G10_CROSS_TOLERANCE) {
    items.push({
      code: 'G10-CHK-03',
      name: '明细表勾稽',
      status: 'warn',
      detail: `G10-1 ${bookTotal.toFixed(2)} vs G10-2 ${detailTotal.toFixed(2)} 差 ${detailVariance.toFixed(2)}`,
    })
  } else {
    items.push({
      code: 'G10-CHK-03',
      name: '明细表勾稽',
      status: 'ok',
      detail: `明细审定合计 ${detailTotal!.toFixed(2)} 一致`,
    })
  }

  items.push({
    code: 'G10-CHK-04',
    name: '变动分析',
    status: missingReasons > 0 ? 'warn' : 'ok',
    detail: missingReasons > 0
      ? `${missingReasons} 行 |变动率|>20% 未填原因`
      : '重大变动原因分析已填或无需填写',
  })

  const discParts: string[] = []
  let discStatus: G10CrossCheckStatus = 'info'
  if (listedClosing != null && Math.abs(adjudicated) > 0.005) {
    const v = listedClosing - adjudicated
    discParts.push(`上市附注 ${listedClosing.toFixed(2)}`)
    if (Math.abs(v) > G10_CROSS_TOLERANCE) discStatus = 'warn'
    else discStatus = discStatus === 'warn' ? 'warn' : 'ok'
  }
  if (soeClosing != null && Math.abs(adjudicated) > 0.005) {
    const v = soeClosing - adjudicated
    discParts.push(`国企附注 ${soeClosing.toFixed(2)}`)
    if (Math.abs(v) > G10_CROSS_TOLERANCE) discStatus = 'warn'
    else if (discStatus !== 'warn') discStatus = 'ok'
  }
  const built = buildG10DisclosureAmountsFromResponses(m)
  const hasAdjDisc = Object.values(built.movementSources).some((s) => s === 'adj' || s === 'detail')
  items.push({
    code: 'G10-CHK-05',
    name: '附注披露',
    status: discParts.length ? discStatus : (hasAdjDisc ? 'info' : 'info'),
    detail: discParts.length
      ? `${discParts.join('；')} vs 审定 ${adjudicated.toFixed(2)}`
      : (hasAdjDisc ? '可从 G10-1/G10-2 分项带入附注' : '附注未编制'),
  })

  const fvTotal = fvAuditedTotal(m)
  const detailForFv = parseG10DetailRows(m.get(G10_DETAIL_ROWS_KEY)?.remark ?? m.get(G10_DETAIL_KEY)?.remark)
  const detailFvTotal = detailForFv.length
    ? calcSubtotal(detailForFv.map((r) => parseNum(r.closingAdjusted ?? r.closingBalance)))
    : null
  if (fvTotal == null) {
    items.push({
      code: 'G10-CHK-06',
      name: '公允价值测试',
      status: 'info',
      detail: 'G10-5 未编制',
    })
  } else if (detailFvTotal == null) {
    items.push({
      code: 'G10-CHK-06',
      name: '公允价值测试',
      status: 'info',
      detail: `审定 FV 合计 ${fvTotal.toFixed(2)}（G10-2 无明细可比）`,
    })
  } else {
    const fvVar = fvTotal - detailFvTotal
    items.push({
      code: 'G10-CHK-06',
      name: '公允价值测试',
      status: Math.abs(fvVar) > G10_FV_DIFF_THRESHOLD ? 'warn' : 'ok',
      detail: Math.abs(fvVar) > G10_FV_DIFF_THRESHOLD
        ? `G10-5 ${fvTotal.toFixed(2)} vs G10-2 ${detailFvTotal.toFixed(2)} 差 ${fvVar.toFixed(2)}`
        : `与 G10-2 审定合计 ${detailFvTotal.toFixed(2)} 一致`,
    })
  }

  const l3Total = l3ReportedClosingTotal(m)
  const fvL3 = fvL3AuditedTotal(m)
  const l3VarRows = l3VarianceRowCount(m)
  const l3AssetMismatch = listG10Fv5VsG96AssetMismatches(m).length
  if (l3Total == null && fvL3 == null) {
    items.push({
      code: 'G10-CHK-07',
      name: 'L3 调节表',
      status: 'info',
      detail: 'G10-6 无 Level3 数据',
    })
  } else if (fvL3 != null && l3Total != null) {
    const l3FvVar = l3Total - fvL3
    const status: G10CrossCheckStatus = l3VarRows > 0 || l3AssetMismatch > 0 || Math.abs(l3FvVar) > G10_FV_DIFF_THRESHOLD
      ? 'warn'
      : 'ok'
    const parts: string[] = []
    if (Math.abs(l3FvVar) > G10_FV_DIFF_THRESHOLD) {
      parts.push(`与 G10-5 L3 差 ${l3FvVar.toFixed(2)}`)
    } else {
      parts.push(`与 G10-5 L3 ${fvL3.toFixed(2)} 一致`)
    }
    if (l3VarRows > 0) parts.push(`${l3VarRows} 行企业期末≠计算期末`)
    if (l3AssetMismatch > 0) parts.push(`${l3AssetMismatch} 项逐笔勾稽差异`)
    items.push({
      code: 'G10-CHK-07',
      name: 'L3 调节表',
      status,
      detail: parts.join('；'),
    })
  } else {
    items.push({
      code: 'G10-CHK-07',
      name: 'L3 调节表',
      status: l3VarRows > 0 ? 'warn' : 'info',
      detail: l3VarRows > 0
        ? `${l3VarRows} 行调节差异待说明`
        : 'G10-6 已录入，待与 G10-5 Level3 勾稽',
    })
  }

  const voucherRows = parseJsonRows(m.get('G10-voucher-rows')?.remark)
  const voucherAbnormal = voucherRows.filter((r) => r.isAbnormal)
  const voucherAbnormalNoDesc = voucherAbnormal.filter((r) => !String(r.abnormalDesc ?? '').trim()).length
  const lowRatioScopes = voucherLowRatioScopes(m)
  if (!voucherRows.length) {
    items.push({
      code: 'G10-CHK-08',
      name: '凭证检查',
      status: 'info',
      detail: 'G10-7 无样本',
    })
  } else {
    let vchStatus: G10CrossCheckStatus = 'ok'
    const vchParts = [`样本 ${voucherRows.length} 笔`]
    if (voucherAbnormal.length) vchParts.push(`异常 ${voucherAbnormal.length} 笔`)
    if (voucherAbnormalNoDesc > 0) {
      vchStatus = 'warn'
      vchParts.push(`${voucherAbnormalNoDesc} 笔未填异常说明`)
    }
    if (lowRatioScopes.length) {
      vchStatus = 'warn'
      vchParts.push(`${lowRatioScopes.join('/')} 检查比例<30%`)
    }
    items.push({
      code: 'G10-CHK-08',
      name: '凭证检查',
      status: vchStatus,
      detail: vchParts.join('；'),
    })
  }

  const derivMissing = derivativeMissingCompliance(m)
  const wizardEval = evaluateG10DerivativeWizard(
    parseG10DerivativeWizardState(m.get('G10-derivative-wizard')?.remark),
  )
  const derivRows = parseJsonRows(m.get('G10-derivative-rows')?.remark)
  if (!derivRows.length) {
    items.push({
      code: 'G10-CHK-09',
      name: '衍生工具核查',
      status: 'info',
      detail: 'G10-8 未编制',
    })
  } else if (wizardEval.measurement === null) {
    items.push({
      code: 'G10-CHK-09',
      name: '衍生工具核查',
      status: derivMissing > 0 ? 'warn' : 'info',
      detail: derivMissing > 0
        ? `向导未完成；${derivMissing} 行待填合规`
        : '识别向导未完成（步骤 B～E）',
    })
  } else if (derivMissing > 0) {
    items.push({
      code: 'G10-CHK-09',
      name: '衍生工具核查',
      status: 'warn',
      detail: `${derivMissing} 行未选合规；向导：${wizardEval.summary}`,
    })
  } else {
    items.push({
      code: 'G10-CHK-09',
      name: '衍生工具核查',
      status: 'ok',
      detail: `78 项已填；向导：${wizardEval.measurement === 'none' ? '无衍生' : '结论一致'}`,
    })
  }

  const adjRows = parseJsonRows(m.get(G10_ADJ_KEY)?.remark)
  if (!adjRows.length) {
    items.push({
      code: 'G10-CHK-10',
      name: '调整分录汇总',
      status: 'info',
      detail: 'G10-3 无调整分录',
    })
  } else {
    const summary = summarizeG10Adjustment(adjRows)
    const src = countG10AdjBySource(adjRows)
    const zeroMemos = countG10ZeroAmountMemoGroups(adjRows)
    const srcParts: string[] = []
    if (src.g104) srcParts.push(`G10-4×${src.g104}`)
    if (src.g105) srcParts.push(`G10-5×${src.g105}`)
    if (src.g106) srcParts.push(`G10-6×${src.g106}`)
    if (src.g107) srcParts.push(`G10-7×${src.g107}`)
    if (src.g108) srcParts.push(`G10-8×${src.g108}`)
    if (src.module) srcParts.push(`模块×${src.module}`)
    let adjStatus: G10CrossCheckStatus = 'ok'
    const detailParts = [
      `${summary.rowCount} 行 AJE ${summary.ajeCount}/RJE ${summary.rjeCount}`,
      `2101 净额 ${summary.net2101.toFixed(2)}`,
    ]
    if (Math.abs(summary.balanceDiff) > G10_CROSS_TOLERANCE) {
      adjStatus = 'error'
      detailParts.push(`借贷差 ${summary.balanceDiff.toFixed(2)}`)
    }
    if (srcParts.length) detailParts.push(`来源 ${srcParts.join(' ')}`)
    if (zeroMemos > 0) {
      adjStatus = adjStatus === 'error' ? 'error' : 'warn'
      detailParts.push(`${zeroMemos} 组备忘待补金额`)
    }
    items.push({
      code: 'G10-CHK-10',
      name: '调整分录汇总',
      status: adjStatus,
      detail: detailParts.join('；'),
    })
  }

  const writebackCross = compareG10Adj3VsG101Writeback(m)
  if (!writebackCross) {
    items.push({
      code: 'G10-CHK-11',
      name: '调整回写勾稽',
      status: 'info',
      detail: 'G10-3 无分录或未编制',
    })
  } else if (Math.abs(writebackCross.diff) > G10_CROSS_TOLERANCE) {
    items.push({
      code: 'G10-CHK-11',
      name: '调整回写勾稽',
      status: 'warn',
      detail: `G10-3 2101 净额 ${writebackCross.adj3Net2101.toFixed(2)} vs G10-1 (三) 回写 ${writebackCross.g101BookNet.toFixed(2)} 差 ${writebackCross.diff.toFixed(2)}`,
    })
  } else {
    items.push({
      code: 'G10-CHK-11',
      name: '调整回写勾稽',
      status: 'ok',
      detail: `2101 净额 ${writebackCross.adj3Net2101.toFixed(2)} 已回写 G10-1 (三)`,
    })
  }

  return items
}

export function worstG10CrossCheckStatus(items: G10CrossCheckItem[]): G10CrossCheckStatus {
  if (items.some((i) => i.status === 'error')) return 'error'
  if (items.some((i) => i.status === 'warn')) return 'warn'
  if (items.every((i) => i.status === 'ok')) return 'ok'
  return 'info'
}
