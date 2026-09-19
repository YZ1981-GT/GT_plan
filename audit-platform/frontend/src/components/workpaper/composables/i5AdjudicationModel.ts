/**
 * i5AdjudicationModel — I5-1 其他非流动资产审定表纯函数
 *
 * 镜像 I4-1 骨架（科目 1911；无摊销列）：
 *   未审滚动(期初/增/减/期末) → 账项调整 → 审定
 *   行来源 I5-2；AJE/RJE 自 I5-3；与 TB 1911 勾稽
 *   变动额/变动率：本期审定 vs 上期审定（上期为 0 → N/A）
 *
 * 公式：期末 = 期初 + 增加 − 减少；审定 = 未审 + AJE + RJE
 */

import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
  calcTriangleReconciliation,
} from './useI5FormulaEngine'

export const I5_ADJ_ROWS_KEY = 'I5-adj-rows'
export const I5_ADJ_NOTE_KEY = 'I5-adj-audit-note'
export const I5_ADJ_CONCLUSION_KEY = 'I5-adj-audit-conclusion'
export const I5_ADJ_MATTERS_KEY = 'I5-adj-significant-matters'
export const I5_ADJ_OWNERSHIP_KEY = 'I5-adj-ownership-pledge'

/** 对齐致同 Excel I5-1 标准项目行（可增删） */
export const I5_DEFAULT_CATEGORIES = [
  '预付土地出让金',
  '预付工程款',
  '预付房屋、设备款',
  '无形资产预付款',
  '预付投资款',
  '委托贷款',
  '合同资产',
  '合同取得成本',
  '合同履约成本',
  '应收退货成本',
  '其他',
] as const

/** 变动率超过该阈值（%）须在审计说明中解释原因 */
export const I5_VARIANCE_EXPLAIN_THRESHOLD = 30

export const I5_CONCLUSION_OPTIONS = [
  { key: 'A', label: 'A. 未发现异常，可确认', text: '经审计，其他非流动资产期末余额在所有重大方面公允反映，分类与列报恰当。' },
  { key: 'B', label: 'B. 经调整后可确认', text: '经审计调整后，其他非流动资产期末余额在所有重大方面公允反映，分类与列报恰当。' },
  { key: 'C', label: 'C. 因未调整事项/范围受限无法确认', text: '因存在重大未调整事项或审计范围受限，其他非流动资产期末余额无法确认。' },
] as const

export interface I5AdjudicationRowModel {
  rowId: string
  projectName: string
  beginBalance: number
  increase: number
  /** 本期减少（含到期转出/重分类等） */
  decrease: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorAudited: number
  varianceAmount: number
  varianceRate: number | null
  triangleDiff: number
  hasError: boolean
  /** 期初账项调整（来自 I5-2 F，对齐 Excel I5-1 C 列） */
  openingAje?: number
  /** 期初重分类调整（来自 I5-2 G，对齐 Excel I5-1 D 列） */
  openingRje?: number
  /**
   * 期末账项调整列（对齐 Excel：F+H−I = 期初账项+账项增−账项减）
   * 使得 未审期末 + endAje + endRje = 审定期末
   */
  endAje?: number
  /** 期末重分类调整列（对齐 Excel：G+J−K） */
  endRje?: number
  remark?: string
  indexRef?: string
  isEditable?: boolean
  fromDetail?: boolean
  ajeApprox?: boolean
}

export interface I5AdjudicationCrossCheck {
  detailBegin: number
  detailIncrease: number
  detailDecrease: number
  detailEnd: number
  adjBegin: number
  adjIncrease: number
  adjDecrease: number
  adjEnd: number
  adjAudited: number
  beginDiff: number
  endDiff: number
  auditedVsDetailDiff: number
  hasWarning: boolean
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function _str(v: unknown): string {
  return v == null ? '' : String(v)
}
function _round2(n: number): number {
  return Math.round(n * 100) / 100
}
function _id(): string {
  return `i51-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function calcI5Variance(audited: number, priorAudited: number): {
  varianceAmount: number
  varianceRate: number | null
} {
  const varianceAmount = _round2(_num(audited) - _num(priorAudited))
  const prior = _num(priorAudited)
  if (Math.abs(prior) < 0.005) return { varianceAmount, varianceRate: null }
  return { varianceAmount, varianceRate: _round2((varianceAmount / Math.abs(prior)) * 10000) / 100 }
}

export function formatI5VarianceRate(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}

export function recalcI5AdjudicationRow(row: I5AdjudicationRowModel): I5AdjudicationRowModel {
  const beginBalance = _num(row.beginBalance)
  const increase = _num(row.increase)
  const decrease = _num(row.decrease)
  const endBalance = _round2(calcAssetEndBalance(beginBalance, increase, decrease))
  const unadjusted = _num(row.unadjusted)
  const aje = _num(row.aje)
  const rje = _num(row.rje)
  const audited = _round2(calcAuditedAmount(unadjusted, aje, rje))
  const priorAudited = _num(row.priorAudited)
  const { varianceAmount, varianceRate } = calcI5Variance(audited, priorAudited)
  const triangleDiff = _round2(calcTriangleReconciliation(beginBalance, increase, decrease, endBalance))
  return {
    ...row,
    beginBalance,
    increase,
    decrease,
    endBalance,
    unadjusted,
    aje,
    rje,
    audited,
    priorAudited,
    varianceAmount,
    varianceRate,
    triangleDiff,
    hasError: Math.abs(triangleDiff) > 0.01,
    openingAje: _num(row.openingAje),
    openingRje: _num(row.openingRje),
    endAje: row.endAje != null ? _num(row.endAje) : undefined,
    endRje: row.endRje != null ? _num(row.endRje) : undefined,
  }
}

export function emptyI5AdjudicationRow(partial?: Partial<I5AdjudicationRowModel>): I5AdjudicationRowModel {
  return recalcI5AdjudicationRow({
    rowId: partial?.rowId || _id(),
    projectName: '',
    beginBalance: 0,
    increase: 0,
    decrease: 0,
    endBalance: 0,
    unadjusted: 0,
    aje: 0,
    rje: 0,
    audited: 0,
    priorAudited: 0,
    varianceAmount: 0,
    varianceRate: null,
    triangleDiff: 0,
    hasError: false,
    remark: '',
    indexRef: '',
    isEditable: true,
    fromDetail: false,
    ajeApprox: false,
    ...partial,
  })
}

export function normalizeI5AdjudicationRow(raw: any): I5AdjudicationRowModel {
  if (!raw || typeof raw !== 'object') return emptyI5AdjudicationRow()
  return recalcI5AdjudicationRow({
    rowId: _str(raw.rowId) || _id(),
    projectName: _str(raw.projectName || raw.项目 || raw.name),
    beginBalance: _num(raw.beginBalance ?? raw.期初),
    increase: _num(raw.increase ?? raw.增加),
    decrease: _num(raw.decrease ?? raw.减少),
    endBalance: _num(raw.endBalance ?? raw.期末),
    unadjusted: _num(raw.unadjusted ?? raw.未审),
    aje: _num(raw.aje ?? raw.AJE),
    rje: _num(raw.rje ?? raw.RJE),
    audited: _num(raw.audited ?? raw.审定),
    priorAudited: _num(raw.priorAudited ?? raw.上期审定),
    varianceAmount: 0,
    varianceRate: null,
    triangleDiff: 0,
    hasError: false,
    remark: _str(raw.remark ?? raw.备注),
    indexRef: _str(raw.indexRef),
    isEditable: raw.isEditable !== false,
    fromDetail: !!raw.fromDetail,
    ajeApprox: !!raw.ajeApprox,
    openingAje: _num(raw.openingAje),
    openingRje: _num(raw.openingRje),
    endAje: raw.endAje != null ? _num(raw.endAje) : undefined,
    endRje: raw.endRje != null ? _num(raw.endRje) : undefined,
  })
}

export function summarizeI5Adjudication(rows: I5AdjudicationRowModel[]): I5AdjudicationRowModel {
  const detail = rows.filter((r) => r.projectName !== '合计')
  return recalcI5AdjudicationRow({
    rowId: 'row-subtotal',
    projectName: '合计',
    beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
    increase: calcSubtotal(detail.map((r) => r.increase)),
    decrease: calcSubtotal(detail.map((r) => r.decrease)),
    endBalance: 0,
    unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
    aje: calcSubtotal(detail.map((r) => r.aje)),
    rje: calcSubtotal(detail.map((r) => r.rje)),
    audited: 0,
    priorAudited: calcSubtotal(detail.map((r) => r.priorAudited)),
    varianceAmount: 0,
    varianceRate: null,
    triangleDiff: 0,
    hasError: false,
    isEditable: false,
  })
}

function _detailName(r: any): string {
  return _str(r?.projectName || r?.name || r?.项目).trim()
}

/** 单层滚动块 → Excel I5-1 期初/期末矩阵字段 */
export function extractI5LeadFromRoll(block: any): {
  beginUnadj: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadj: number
  endAje: number
  endRje: number
  endAudited: number
  auditedOpening: number
  auditedIncrease: number
  auditedDecrease: number
  auditedEnding: number
} {
  const unadjOpening = _num(block?.unadjOpening)
  const unadjIncrease = _num(block?.unadjIncrease)
  const unadjDecrease = _num(block?.unadjDecrease)
  const openingAje = _num(block?.openingAje)
  const openingRje = _num(block?.openingRje)
  const ajeIncrease = _num(block?.ajeIncrease)
  const ajeDecrease = _num(block?.ajeDecrease)
  const rjeIncrease = _num(block?.rjeIncrease)
  const rjeDecrease = _num(block?.rjeDecrease)
  const unadjEnding = block?.unadjEnding != null
    ? _num(block.unadjEnding)
    : _round2(calcAssetEndBalance(unadjOpening, unadjIncrease, unadjDecrease))
  const auditedOpening = block?.auditedOpening != null
    ? _num(block.auditedOpening)
    : _round2(unadjOpening + openingAje + openingRje)
  const auditedIncrease = block?.auditedIncrease != null
    ? _num(block.auditedIncrease)
    : _round2(unadjIncrease + ajeIncrease + rjeIncrease)
  const auditedDecrease = block?.auditedDecrease != null
    ? _num(block.auditedDecrease)
    : _round2(unadjDecrease + ajeDecrease + rjeDecrease)
  const auditedEnding = block?.auditedEnding != null
    ? _num(block.auditedEnding)
    : _round2(calcAssetEndBalance(auditedOpening, auditedIncrease, auditedDecrease))
  // Excel 期末账项/重分类：使 未审期末+账项+重分类=审定期末
  const endAje = _round2(openingAje + ajeIncrease - ajeDecrease)
  const endRje = _round2(openingRje + rjeIncrease - rjeDecrease)
  return {
    beginUnadj: unadjOpening,
    beginAje: openingAje,
    beginRje: openingRje,
    beginAudited: auditedOpening,
    endUnadj: unadjEnding,
    endAje,
    endRje,
    endAudited: auditedEnding,
    auditedOpening,
    auditedIncrease,
    auditedDecrease,
    auditedEnding,
  }
}

function _subtractLead(
  a: ReturnType<typeof extractI5LeadFromRoll>,
  b: ReturnType<typeof extractI5LeadFromRoll>,
): ReturnType<typeof extractI5LeadFromRoll> {
  return {
    beginUnadj: _round2(a.beginUnadj - b.beginUnadj),
    beginAje: _round2(a.beginAje - b.beginAje),
    beginRje: _round2(a.beginRje - b.beginRje),
    beginAudited: _round2(a.beginAudited - b.beginAudited),
    endUnadj: _round2(a.endUnadj - b.endUnadj),
    endAje: _round2(a.endAje - b.endAje),
    endRje: _round2(a.endRje - b.endRje),
    endAudited: _round2(a.endAudited - b.endAudited),
    auditedOpening: _round2(a.auditedOpening - b.auditedOpening),
    auditedIncrease: _round2(a.auditedIncrease - b.auditedIncrease),
    auditedDecrease: _round2(a.auditedDecrease - b.auditedDecrease),
    auditedEnding: _round2(a.auditedEnding - b.auditedEnding),
  }
}

/** 从 I5-2 行提取净值滚动（供审定表带入） */
export function extractI5DetailLead(raw: any): ReturnType<typeof extractI5LeadFromRoll> & {
  projectName: string
} {
  const projectName = _detailName(raw)
  if (raw?.gross && typeof raw.gross === 'object') {
    const g = extractI5LeadFromRoll(raw.gross)
    const i = extractI5LeadFromRoll(raw.impairment || {})
    return { projectName, ..._subtractLead(g, i) }
  }
  const begin = _num(raw.beginBalance ?? raw.auditedOpening ?? raw.期初)
  const increase = _num(raw.increase ?? raw.auditedIncrease ?? raw.增加)
  const decrease = _num(raw.decrease ?? raw.auditedDecrease ?? raw.减少)
  const endCalc = _round2(calcAssetEndBalance(begin, increase, decrease))
  const end = raw.endBalance != null || raw.auditedEnding != null
    ? _num(raw.endBalance ?? raw.auditedEnding)
    : endCalc
  const openingAje = _num(raw.openingAje)
  const openingRje = _num(raw.openingRje)
  const endAje = raw.endAje != null
    ? _num(raw.endAje)
    : _round2(openingAje + _num(raw.ajeIncrease) - _num(raw.ajeDecrease))
  const endRje = raw.endRje != null
    ? _num(raw.endRje)
    : _round2(openingRje + _num(raw.rjeIncrease) - _num(raw.rjeDecrease))
  const unadjEnding = raw.unadjusted != null ? _num(raw.unadjusted) : end
  return {
    projectName,
    beginUnadj: begin,
    beginAje: openingAje,
    beginRje: openingRje,
    beginAudited: _round2(begin + openingAje + openingRje),
    endUnadj: unadjEnding,
    endAje,
    endRje,
    endAudited: end,
    auditedOpening: _round2(begin + openingAje + openingRje),
    auditedIncrease: increase,
    auditedDecrease: decrease,
    auditedEnding: end,
  }
}

function _detailRoll(raw: any): {
  begin: number
  increase: number
  decrease: number
  end: number
  openingAje: number
  openingRje: number
  endAje: number
  endRje: number
  unadjEnding: number
} {
  const lead = extractI5DetailLead(raw)
  return {
    begin: lead.auditedOpening,
    increase: lead.auditedIncrease,
    decrease: lead.auditedDecrease,
    end: lead.auditedEnding,
    openingAje: lead.beginAje,
    openingRje: lead.beginRje,
    endAje: lead.endAje,
    endRje: lead.endRje,
    unadjEnding: lead.endUnadj,
  }
}

export function seedI5AdjudicationFromDetail(
  detailRows: any[],
  prevRows: I5AdjudicationRowModel[] = [],
): I5AdjudicationRowModel[] {
  const prevByName = new Map(prevRows.map((r) => [r.projectName.trim(), r]))
  const out: I5AdjudicationRowModel[] = []
  for (const raw of detailRows || []) {
    const projectName = _detailName(raw)
    if (!projectName || projectName === '合计') continue
    if (raw?.layer === 'impairment' || raw?.layer === 'net') continue
    const roll = _detailRoll(raw)
    const prev = prevByName.get(projectName)
    out.push(recalcI5AdjudicationRow({
      rowId: prev?.rowId || _id(),
      projectName,
      beginBalance: roll.begin,
      increase: roll.increase,
      decrease: roll.decrease,
      endBalance: roll.end,
      // 未审列取明细净值审定期末；I5-3 AJE/RJE 在此基础上加减
      unadjusted: roll.end,
      aje: prev?.aje ?? 0,
      rje: prev?.rje ?? 0,
      audited: 0,
      priorAudited: prev?.priorAudited ?? _num(raw.priorAudited ?? raw.priorBalance),
      varianceAmount: 0,
      varianceRate: null,
      triangleDiff: 0,
      hasError: false,
      openingAje: roll.openingAje,
      openingRje: roll.openingRje,
      endAje: roll.endAje,
      endRje: roll.endRje,
      remark: prev?.remark || '',
      indexRef: prev?.indexRef || _str(raw.indexRef) || 'I5-2',
      isEditable: true,
      fromDetail: true,
      ajeApprox: prev?.ajeApprox ?? false,
    }))
  }
  return out
}

export function allocateI5Adjustments(
  rows: I5AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I5AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI5AdjudicationRow({
      ...r,
      aje: i === 0 ? totalAje : 0,
      rje: i === 0 ? totalRje : 0,
      ajeApprox: markApprox && i === 0 && rows.length > 1,
    }))
  }
  let ajeLeft = totalAje
  let rjeLeft = totalRje
  return rows.map((r, i) => {
    const ratio = base[i] / sum
    const isLast = i === rows.length - 1
    const aje = isLast ? _round2(ajeLeft) : _round2(totalAje * ratio)
    const rje = isLast ? _round2(rjeLeft) : _round2(totalRje * ratio)
    ajeLeft = _round2(ajeLeft - aje)
    rjeLeft = _round2(rjeLeft - rje)
    return recalcI5AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

export function applyAjeFromI53(
  rows: I5AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I5AdjudicationRowModel[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje: Array<{ name: string; net: number }> = []
  const namedRje: Array<{ name: string; net: number }> = []

  for (const line of adjRows || []) {
    const code = String(line?.accountCode || '1911')
    if (!code.startsWith('1911')) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const et = String(line?.entryType || (line?.category === '报表调整' ? 'RJE' : 'AJE'))
    // 仅用明细项目名精确匹配；说明/摘要不参与匹配，避免误配后走近似分摊
    const name = _str(line?.projectName || line?.investee).trim()
    if (et === 'RJE') {
      totalRje = _round2(totalRje + net)
      if (name) namedRje.push({ name, net })
    } else {
      totalAje = _round2(totalAje + net)
      if (name) namedAje.push({ name, net })
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, aje: 0, rje: 0, ajeApprox: false }))
  const byName = new Map(next.map((r) => [r.projectName.trim(), r]))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const { name, net } of namedAje) {
    const row = byName.get(name)
    if (!row) continue
    row.aje = _round2(row.aje + net)
    matchedByName++
    ajeNamed = _round2(ajeNamed + net)
  }
  for (const { name, net } of namedRje) {
    const row = byName.get(name)
    if (!row) continue
    row.rje = _round2(row.rje + net)
    matchedByName++
    rjeNamed = _round2(rjeNamed + net)
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    if (next.length === 1) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
      applied++
    } else {
      const allocated = allocateI5Adjustments(next, ajeRem, rjeRem, true)
      for (let i = 0; i < next.length; i++) {
        next[i].aje = _round2(next[i].aje + allocated[i].aje)
        next[i].rje = _round2(next[i].rje + allocated[i].rje)
        if (allocated[i].ajeApprox) {
          next[i].ajeApprox = true
          approx = true
        }
      }
      applied += next.length
    }
  }

  return {
    rows: next.map(recalcI5AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

export function buildI5AdjudicationCrossCheck(
  rows: I5AdjudicationRowModel[],
  detail: { beginBalance?: number; increase?: number; decrease?: number; endBalance?: number },
): I5AdjudicationCrossCheck {
  const sub = summarizeI5Adjudication(rows)
  const detailBegin = _num(detail.beginBalance)
  const detailIncrease = _num(detail.increase)
  const detailDecrease = _num(detail.decrease)
  const detailEnd = _num(detail.endBalance)
  const beginDiff = _round2(sub.beginBalance - detailBegin)
  const endDiff = _round2(sub.endBalance - detailEnd)
  const auditedVsDetailDiff = _round2(sub.audited - detailEnd)
  return {
    detailBegin,
    detailIncrease,
    detailDecrease,
    detailEnd,
    adjBegin: sub.beginBalance,
    adjIncrease: sub.increase,
    adjDecrease: sub.decrease,
    adjEnd: sub.endBalance,
    adjAudited: sub.audited,
    beginDiff,
    endDiff,
    auditedVsDetailDiff,
    hasWarning: [beginDiff, endDiff, auditedVsDetailDiff].some((d) => Math.abs(d) > 0.01),
  }
}

export interface I5ExcelLeadSummary {
  beginUnadj: number
  /** 期初账项调整（本期审定表通常为 0，保留列对齐 Excel） */
  beginAje: number
  beginRje: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAje: number
  endRje: number
  endAdj: number
  endAudited: number
  varianceAmount: number
  varianceRate: number | null
}

export interface I5LeadMatrixRow extends I5ExcelLeadSummary {
  label: string
  isTotal?: boolean
}

/** 对齐 Excel：期初/期末 × 未审·账项调整·重分类调整·审定 + 变动 */
export function buildI5ExcelLeadSummary(rows: I5AdjudicationRowModel[]): I5ExcelLeadSummary {
  const detail = rows.filter((r) => r.projectName !== '合计')
  const sub = summarizeI5Adjudication(detail)
  const beginAje = calcSubtotal(detail.map((r) => _num(r.openingAje)))
  const beginRje = calcSubtotal(detail.map((r) => _num(r.openingRje)))
  const endAje = calcSubtotal(detail.map((r) => (r.endAje != null ? _num(r.endAje) : _num(r.aje))))
  const endRje = calcSubtotal(detail.map((r) => (r.endRje != null ? _num(r.endRje) : _num(r.rje))))
  return {
    beginUnadj: calcSubtotal(detail.map((r) => _num(r.beginBalance) - _num(r.openingAje) - _num(r.openingRje))),
    beginAje,
    beginRje,
    beginAdj: _round2(beginAje + beginRje),
    beginAudited: sub.beginBalance,
    endUnadj: sub.unadjusted,
    endAje,
    endRje,
    endAdj: _round2(endAje + endRje),
    endAudited: sub.audited,
    varianceAmount: sub.varianceAmount,
    varianceRate: sub.varianceRate,
  }
}

/** 按项目展开审定矩阵（末行合计），对齐 Excel 逐项列示 */
export function buildI5LeadMatrixRows(rows: I5AdjudicationRowModel[]): I5LeadMatrixRow[] {
  const detail = rows.filter((r) => r.projectName !== '合计')
  const out: I5LeadMatrixRow[] = detail.map((r) => {
    const beginAje = _num(r.openingAje)
    const beginRje = _num(r.openingRje)
    const endAje = r.endAje != null ? _num(r.endAje) : _num(r.aje)
    const endRje = r.endRje != null ? _num(r.endRje) : _num(r.rje)
    const beginUnadj = _round2(_num(r.beginBalance) - beginAje - beginRje)
    return {
      label: r.projectName || '未命名',
      beginUnadj,
      beginAje,
      beginRje,
      beginAdj: _round2(beginAje + beginRje),
      beginAudited: _num(r.beginBalance),
      endUnadj: _num(r.unadjusted),
      endAje,
      endRje,
      endAdj: _round2(endAje + endRje),
      endAudited: _num(r.audited),
      varianceAmount: _num(r.varianceAmount),
      varianceRate: r.varianceRate,
      isTotal: false,
    }
  })
  const L = buildI5ExcelLeadSummary(detail)
  out.push({ ...L, label: '合计', isTotal: true })
  return out
}

export type I5LayerKind = 'gross' | 'impairment' | 'net' | 'section' | 'total' | 'tb'

export interface I5ThreeLayerLeadRow extends I5LeadMatrixRow {
  layer: I5LayerKind
  /** 区段标题行（原值：/减值准备：/净值：） */
  isSection?: boolean
  /** TB 差异行标记（|diff|>0.01） */
  tbMismatch?: boolean
}

/**
 * 对齐 Excel I5-1 三层：原值 → 减值 → 净值（从 I5-2 明细只读展开）
 */
export function buildI5ThreeLayerLeadFromDetail(detailRows: any[]): I5ThreeLayerLeadRow[] {
  const items = (detailRows || []).filter((r) => {
    const name = _detailName(r)
    return name && name !== '合计' && r?.layer !== 'impairment' && r?.layer !== 'net'
  })
  if (!items.length) return []

  const out: I5ThreeLayerLeadRow[] = []

  const pushSection = (label: string, layer: 'gross' | 'impairment' | 'net', leads: ReturnType<typeof extractI5LeadFromRoll>[]) => {
    out.push({
      label,
      layer: 'section',
      isSection: true,
      beginUnadj: 0, beginAje: 0, beginRje: 0, beginAdj: 0, beginAudited: 0,
      endUnadj: 0, endAje: 0, endRje: 0, endAdj: 0, endAudited: 0,
      varianceAmount: 0, varianceRate: null,
    })
    for (let i = 0; i < items.length; i++) {
      const lead = leads[i]
      const name = _detailName(items[i])
      out.push({
        label: name,
        layer,
        beginUnadj: lead.beginUnadj,
        beginAje: lead.beginAje,
        beginRje: lead.beginRje,
        beginAdj: _round2(lead.beginAje + lead.beginRje),
        beginAudited: lead.beginAudited,
        endUnadj: lead.endUnadj,
        endAje: lead.endAje,
        endRje: lead.endRje,
        endAdj: _round2(lead.endAje + lead.endRje),
        endAudited: lead.endAudited,
        varianceAmount: _round2(lead.endAudited - lead.beginAudited),
        varianceRate: Math.abs(lead.beginAudited) < 0.005
          ? null
          : _round2(((lead.endAudited - lead.beginAudited) / Math.abs(lead.beginAudited)) * 10000) / 100,
      })
    }
    const sum = (pick: (l: ReturnType<typeof extractI5LeadFromRoll>) => number) =>
      _round2(leads.reduce((s, l) => s + pick(l), 0))
    const beginAud = sum((l) => l.beginAudited)
    const endAud = sum((l) => l.endAudited)
    out.push({
      label: '合计',
      layer: 'total',
      isTotal: true,
      beginUnadj: sum((l) => l.beginUnadj),
      beginAje: sum((l) => l.beginAje),
      beginRje: sum((l) => l.beginRje),
      beginAdj: sum((l) => l.beginAje + l.beginRje),
      beginAudited: beginAud,
      endUnadj: sum((l) => l.endUnadj),
      endAje: sum((l) => l.endAje),
      endRje: sum((l) => l.endRje),
      endAdj: sum((l) => l.endAje + l.endRje),
      endAudited: endAud,
      varianceAmount: _round2(endAud - beginAud),
      varianceRate: Math.abs(beginAud) < 0.005
        ? null
        : _round2(((endAud - beginAud) / Math.abs(beginAud)) * 10000) / 100,
    })
  }

  const grossLeads = items.map((r) =>
    r.gross ? extractI5LeadFromRoll(r.gross) : extractI5LeadFromRoll({
      unadjOpening: _num(r.beginBalance),
      unadjIncrease: _num(r.increase),
      unadjDecrease: _num(r.decrease),
      auditedEnding: _num(r.endBalance),
    }),
  )
  const impLeads = items.map((r) => extractI5LeadFromRoll(r.impairment || {}))
  const netLeads = grossLeads.map((g, i) => _subtractLead(g, impLeads[i]))

  pushSection('其他非流动资产原值：', 'gross', grossLeads)
  pushSection('减值准备：', 'impairment', impLeads)
  pushSection('净值：', 'net', netLeads)
  return out
}

/** 自到期日推算距审计截止日（默认当年12/31）的剩余月数 */
export function calcI5RemainingMonths(
  maturityDate: string,
  asOfYear?: number,
): number | null {
  const s = _str(maturityDate).trim()
  if (!s) return null
  const year = asOfYear ?? new Date().getFullYear()
  const m = s.match(/(\d{4})[-/.年](\d{1,2})/)
  if (!m) return null
  const y = Number(m[1])
  const mo = Number(m[2])
  if (!Number.isFinite(y) || !Number.isFinite(mo) || mo < 1 || mo > 12) return null
  const months = (y - year) * 12 + mo - 12
  return months > 0 ? months : null
}

/**
 * 一年内到期（剩余月数≤12）重分类候选：供 I5-3 RJE 草稿。
 * 金额取 I5-2 净值审定期末（含 gross/impairment 嵌套结构）。
 */
export function extractI5CurrentPortionCandidates(
  detailRows: any[],
  asOfYear?: number,
): Array<{
  projectName: string
  amount: number
  remainingMonths: number
  maturityDate: string
  category: string
}> {
  const year = asOfYear ?? new Date().getFullYear()
  const out: Array<{
    projectName: string
    amount: number
    remainingMonths: number
    maturityDate: string
    category: string
  }> = []
  for (const r of detailRows || []) {
    const projectName = _detailName(r)
    if (!projectName || projectName === '合计') continue
    if (r?.layer === 'impairment' || r?.layer === 'net') continue
    let remainingMonths = _num(r?.remainingMonths)
    const maturityDate = _str(r?.maturityDate ?? r?.dueDate)
    if (!(remainingMonths > 0)) {
      const computed = calcI5RemainingMonths(maturityDate, year)
      if (computed != null) remainingMonths = computed
    }
    const lead = extractI5DetailLead(r)
    const amount = _round2(lead.auditedEnding)
    if (!(remainingMonths > 0 && remainingMonths <= 12 && amount > 0.005)) continue
    out.push({
      projectName,
      amount,
      remainingMonths,
      maturityDate,
      category: _str(r?.category || r?.assetType || ''),
    })
  }
  return out
}

/** 在三层矩阵末追加 TB 勾稽行（对齐 Excel：TB数据 / 差异） */
export function appendI5TbReconciliationToLead(
  matrix: I5ThreeLayerLeadRow[],
  tbUnadjusted: number,
): I5ThreeLayerLeadRow[] {
  if (!matrix.length) return matrix
  const netTotals = matrix.filter((r) => r.isTotal)
  const netTotal = netTotals[netTotals.length - 1]
  if (!netTotal) return matrix
  const audited = _num(netTotal.endAudited)
  const tb = _round2(_num(tbUnadjusted))
  const diff = _round2(audited - tb)
  const blank = {
    beginUnadj: 0, beginAje: 0, beginRje: 0, beginAdj: 0, beginAudited: 0,
    endUnadj: 0, endAje: 0, endRje: 0, endAdj: 0,
    varianceAmount: 0, varianceRate: null as number | null,
  }
  return [
    ...matrix,
    {
      ...blank,
      label: 'TB勾稽',
      layer: 'section',
      isSection: true,
    },
    {
      ...blank,
      label: 'TB数据(1911)',
      layer: 'tb',
      endAudited: tb,
    },
    {
      ...blank,
      label: '差异',
      layer: 'tb',
      endAudited: diff,
      varianceAmount: diff,
      tbMismatch: Math.abs(diff) > 0.01,
    },
  ]
}

/**
 * 对齐 Excel 审计说明(1)：期末较期初变动 + 超阈值项目原因占位。
 * 上期审定为 0 时写 N/A，避免 #DIV/0!。
 */
export function buildI5VarianceNoteDraft(
  rows: I5AdjudicationRowModel[],
  threshold = I5_VARIANCE_EXPLAIN_THRESHOLD,
): string {
  const sub = summarizeI5Adjudication(rows)
  const rateLabel = formatI5VarianceRate(sub.varianceRate)
  const dir = sub.varianceAmount >= 0 ? '增加' : '减少'
  const lines = [
    `（1）其他非流动资产期末净值较期初净值${dir} ${fmtPlain(Math.abs(sub.varianceAmount))}，变动率 ${rateLabel}。`,
    `主要原因（比例超过${threshold}%的）：`,
  ]
  const detail = rows.filter((r) => r.projectName !== '合计')
  const significant = detail.filter((r) =>
    r.varianceRate != null && Math.abs(r.varianceRate) >= threshold,
  )
  if (!significant.length) {
    lines.push('  本期各明细项目变动率均未超过上述阈值（或上期审定为 0 无法计算变动率）。')
  } else {
    for (const r of significant) {
      lines.push(
        `  - ${r.projectName}：变动额 ${fmtPlain(r.varianceAmount)}，变动率 ${formatI5VarianceRate(r.varianceRate)}；原因：________`,
      )
    }
  }
  return lines.join('\n')
}

function fmtPlain(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function buildI5AdjudicationConclusionDraft(opts: {
  sampleCount: number
  auditedTotal: number
  tbDiff: number
  hasAje: boolean
  crossWarning: boolean
}): string {
  const parts = [
    `其他非流动资产审定表共 ${opts.sampleCount} 个项目，审定合计 ${opts.auditedTotal.toFixed(2)}。`,
  ]
  if (opts.hasAje) parts.push('已按 I5-3 账项调整更新 AJE/RJE。')
  parts.push(Math.abs(opts.tbDiff) < 0.01
    ? '审定数与 TB(1911) 勾稽一致。'
    : `审定数与 TB 差异 ${opts.tbDiff.toFixed(2)}，须查明。`)
  if (opts.crossWarning) parts.push('与 I5-2 明细存在勾稽差异，请复核带入。')
  parts.push(opts.hasAje ? I5_CONCLUSION_OPTIONS[1].text : I5_CONCLUSION_OPTIONS[0].text)
  return parts.join('')
}

export function validateI5AdjudicationSave(opts: {
  rows: I5AdjudicationRowModel[]
  tbDiff: number
  force?: boolean
}): { ok: boolean; blockers: string[]; warnings: string[] } {
  const blockers: string[] = []
  const warnings: string[] = []
  if (opts.force) return { ok: true, blockers, warnings }
  for (const r of opts.rows) {
    if (r.hasError || Math.abs(_num(r.triangleDiff)) > 0.01) {
      blockers.push(`${r.projectName || '未命名'}：三角勾稽不平（期末≠期初+增−减）`)
    }
    if (r.ajeApprox) warnings.push(`${r.projectName || '未命名'}：AJE/RJE 为近似分摊，建议复核`)
  }
  if (Math.abs(opts.tbDiff) > 0.01) {
    blockers.push(`与 TB 差异 ${opts.tbDiff.toFixed(2)}，须勾稽为 0 后再回写`)
  }
  return { ok: blockers.length === 0, blockers, warnings }
}
