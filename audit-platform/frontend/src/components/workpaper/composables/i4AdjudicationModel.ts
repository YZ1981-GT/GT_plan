/**
 * i4AdjudicationModel — I4-1 长期待摊费用审定表纯函数
 *
 * 对齐致同 Excel「审定表 I4-1」编制逻辑：
 *   未审滚动(期初/增/摊/减/期末) → 账项调整(AJE/RJE) → 审定
 *   行来源：明细表 I4-2；调整来自 I4-3；本期摊销可自 I4-6/I4-7
 *   勾稽：审定期末 ≈ I4-2 期末合计；与 TB 1801 差异须为 0
 *   Excel 另含：本期审定 vs 上期审定（变动额/变动率）
 *
 * 公式：
 *   期末 = 期初 + 增加 − 摊销 − 减少
 *   审定 = 未审 + AJE + RJE
 *   变动额 = 本期审定 − 上期审定；变动率 = 变动额 / |上期审定|（上期为 0 时 N/A）
 */

import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
  calcTriangleReconciliation,
} from './useI4FormulaEngine'

export const I4_ADJ_ROWS_KEY = 'I4-adj-rows'
export const I4_ADJ_NOTE_KEY = 'I4-adj-audit-note'
export const I4_ADJ_CONCLUSION_KEY = 'I4-adj-audit-conclusion'
export const I4_ADJ_MATTERS_KEY = 'I4-adj-significant-matters'

export const I4_CONCLUSION_OPTIONS = [
  { key: 'A', label: 'A. 未发现异常，可确认', text: '经审计，长期待摊费用期末余额在所有重大方面公允反映，摊销计提充分，列报恰当。' },
  { key: 'B', label: 'B. 经调整后可确认', text: '经审计调整后，长期待摊费用期末余额在所有重大方面公允反映，摊销计提充分，列报恰当。' },
  { key: 'C', label: 'C. 因未调整事项/范围受限无法确认', text: '因存在重大未调整事项或审计范围受限，长期待摊费用期末余额无法确认。' },
] as const

export interface I4AdjudicationRowModel {
  rowId: string
  /** 项目 / 类别名称 */
  projectName: string
  beginBalance: number
  increase: number
  amortization: number
  decrease: number
  /** 公式：期初+增加−摊销−减少 */
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  /** 公式：未审+AJE+RJE */
  audited: number
  /** 上期审定数（Excel 比较列） */
  priorAudited: number
  /** 变动额 = 审定 − 上期审定 */
  varianceAmount: number
  /** 变动率%；上期为 0 时 null → UI 显示 N/A */
  varianceRate: number | null
  /** 三角勾稽差额 */
  triangleDiff: number
  hasError: boolean
  indexRef?: string
  isEditable?: boolean
  fromDetail?: boolean
  /**
   * 期末调整是否来自 I4-3 比例分摊（非按项目精确匹配）。
   * 为 true 时须人工复核；手工改 aje/rje 后应清除。
   */
  ajeApprox?: boolean
}

export interface I4AdjudicationCrossCheck {
  detailBegin: number
  detailIncrease: number
  detailAmortization: number
  detailDecrease: number
  detailEnd: number
  adjBegin: number
  adjIncrease: number
  adjAmortization: number
  adjDecrease: number
  adjEnd: number
  adjAudited: number
  beginDiff: number
  endDiff: number
  amortDiff: number
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
  return `i41-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function calcI4Variance(audited: number, priorAudited: number): {
  varianceAmount: number
  varianceRate: number | null
} {
  const varianceAmount = _round2(_num(audited) - _num(priorAudited))
  const prior = _num(priorAudited)
  if (Math.abs(prior) < 0.005) {
    return { varianceAmount, varianceRate: null }
  }
  return {
    varianceAmount,
    varianceRate: _round2((varianceAmount / Math.abs(prior)) * 10000) / 100,
  }
}

export function formatI4VarianceRate(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}

export function recalcI4AdjudicationRow(row: I4AdjudicationRowModel): I4AdjudicationRowModel {
  const beginBalance = _num(row.beginBalance)
  const increase = _num(row.increase)
  const amortization = Math.max(0, _num(row.amortization))
  const decrease = _num(row.decrease)
  const endBalance = _round2(calcAssetEndBalance(beginBalance, increase, amortization, decrease))
  const unadjusted = _num(row.unadjusted)
  const aje = _num(row.aje)
  const rje = _num(row.rje)
  const audited = _round2(calcAuditedAmount(unadjusted, aje, rje))
  const priorAudited = _num(row.priorAudited)
  const { varianceAmount, varianceRate } = calcI4Variance(audited, priorAudited)
  const triangleDiff = _round2(calcTriangleReconciliation(beginBalance, increase, amortization, decrease, endBalance))
  return {
    ...row,
    beginBalance,
    increase,
    amortization,
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
  }
}

export function emptyI4AdjudicationRow(partial?: Partial<I4AdjudicationRowModel>): I4AdjudicationRowModel {
  return recalcI4AdjudicationRow({
    rowId: partial?.rowId || _id(),
    projectName: partial?.projectName ?? '',
    beginBalance: 0,
    increase: 0,
    amortization: 0,
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
    indexRef: '',
    isEditable: true,
    fromDetail: false,
    ajeApprox: false,
    ...partial,
  })
}

/** 兼容旧中文键（项目/期初/增加…）与英文键 */
export function normalizeI4AdjudicationRow(raw: any): I4AdjudicationRowModel {
  if (!raw || typeof raw !== 'object') return emptyI4AdjudicationRow()
  return recalcI4AdjudicationRow({
    rowId: _str(raw.rowId) || _id(),
    projectName: _str(raw.projectName || raw.项目 || raw.name),
    beginBalance: _num(raw.beginBalance ?? raw.期初),
    increase: _num(raw.increase ?? raw.增加),
    amortization: _num(raw.amortization ?? raw.摊销),
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
    indexRef: _str(raw.indexRef),
    isEditable: raw.isEditable !== false,
    fromDetail: !!raw.fromDetail,
    ajeApprox: !!raw.ajeApprox,
  })
}

export function summarizeI4Adjudication(rows: I4AdjudicationRowModel[]): I4AdjudicationRowModel {
  const detail = rows.filter((r) => r.projectName !== '合计')
  const beginBalance = calcSubtotal(detail.map((r) => r.beginBalance))
  const increase = calcSubtotal(detail.map((r) => r.increase))
  const amortization = calcSubtotal(detail.map((r) => r.amortization))
  const decrease = calcSubtotal(detail.map((r) => r.decrease))
  const unadjusted = calcSubtotal(detail.map((r) => r.unadjusted))
  const aje = calcSubtotal(detail.map((r) => r.aje))
  const rje = calcSubtotal(detail.map((r) => r.rje))
  const priorAudited = calcSubtotal(detail.map((r) => r.priorAudited))
  return recalcI4AdjudicationRow({
    rowId: 'row-subtotal',
    projectName: '合计',
    beginBalance,
    increase,
    amortization,
    decrease,
    endBalance: 0,
    unadjusted,
    aje,
    rje,
    audited: 0,
    priorAudited,
    varianceAmount: 0,
    varianceRate: null,
    triangleDiff: 0,
    hasError: false,
    isEditable: false,
    fromDetail: false,
    ajeApprox: false,
  })
}

function _detailName(r: any): string {
  return _str(r?.projectName || r?.name || r?.项目).trim()
}

/**
 * 从 I4-2 明细带入审定表行：保留已有 AJE/RJE/上期审定
 */
export function seedI4AdjudicationFromDetail(
  detailRows: any[],
  prevRows: I4AdjudicationRowModel[] = [],
): I4AdjudicationRowModel[] {
  const prevByName = new Map(prevRows.map((r) => [r.projectName.trim(), r]))
  const out: I4AdjudicationRowModel[] = []
  for (const raw of detailRows || []) {
    const projectName = _detailName(raw)
    if (!projectName || projectName === '合计') continue
    const beginBalance = _num(
      raw.auditedOpening ?? raw.beginBalance ?? raw.unadjOpening ?? raw.期初,
    )
    const increase = _num(
      raw.auditedIncrease ?? raw.currentIncrease ?? raw.unadjIncrease ?? raw.increase ?? raw.增加,
    )
    const amortization = _num(
      raw.auditedAmortization ?? raw.currentAmortization ?? raw.unadjAmortization ?? raw.amortization ?? raw.摊销,
    )
    const decrease = _num(
      raw.auditedOtherDecrease ?? raw.currentDecrease ?? raw.unadjOtherDecrease ?? raw.decrease ?? raw.减少,
    )
    const endCalc = _round2(calcAssetEndBalance(beginBalance, increase, amortization, decrease))
    const endBalance = raw.auditedEnding != null
      ? _num(raw.auditedEnding)
      : (raw.endBalance != null ? _num(raw.endBalance) : endCalc)
    const prev = prevByName.get(projectName)
    out.push(recalcI4AdjudicationRow({
      rowId: prev?.rowId || _id(),
      projectName,
      beginBalance,
      increase,
      amortization,
      decrease,
      endBalance,
      unadjusted: endBalance,
      aje: prev?.aje ?? 0,
      rje: prev?.rje ?? 0,
      audited: 0,
      priorAudited: prev?.priorAudited ?? _num(raw.priorBalance ?? raw.priorAudited),
      varianceAmount: 0,
      varianceRate: null,
      triangleDiff: 0,
      hasError: false,
      indexRef: prev?.indexRef || 'I4-2',
      isEditable: true,
      fromDetail: true,
      ajeApprox: prev?.ajeApprox ?? false,
    }))
  }
  return out
}

/** 按未审占比分摊 AJE/RJE（多行标 ajeApprox） */
export function allocateI4Adjustments(
  rows: I4AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I4AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI4AdjudicationRow({
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
    return recalcI4AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

/**
 * 从 I4-3 写入 AJE/RJE：
 * 1) 优先按 projectName / description 精确匹配
 * 2) 剩余净额：单行直接计入；多行按未审占比分摊并标 ajeApprox
 */
export function applyAjeFromI43(
  rows: I4AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I4AdjudicationRowModel[]
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
    const code = String(line?.accountCode || '1801')
    if (!code.startsWith('1801')) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const et = String(line?.entryType || (line?.category === '报表调整' ? 'RJE' : 'AJE'))
    const name = _str(
      line?.projectName || line?.investee || line?.description || line?.summary || line?.remark,
    ).trim()
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
    row.ajeApprox = false
    matchedByName++
    ajeNamed = _round2(ajeNamed + net)
  }
  for (const { name, net } of namedRje) {
    const row = byName.get(name)
    if (!row) continue
    row.rje = _round2(row.rje + net)
    row.ajeApprox = false
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
      const allocated = allocateI4Adjustments(next, ajeRem, rjeRem, true)
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
    rows: next.map(recalcI4AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

/** 用 I4-6/I4-7 测算覆盖「本期摊销」；无法按名称匹配时回退按合计比例 */
export function applyAmortFromI46(
  rows: I4AdjudicationRowModel[],
  amortRows: any[],
  totalAmortFallback = 0,
): I4AdjudicationRowModel[] {
  if (!rows.length) return rows
  const byName: Record<string, number> = {}
  let totalFromCalc = 0
  for (const r of amortRows || []) {
    const name = _str(r?.projectName || r?.name || r?.itemName).trim()
    const annual = _num(r?.yearTotal ?? r?.annualTotal ?? r?.calcPeriodAmort)
    const monthly = Array.isArray(r?.monthlyAmorts)
      ? (r.monthlyAmorts as number[]).reduce((s, v) => s + _num(v), 0)
      : Array.isArray(r?.monthlyAmort)
        ? (r.monthlyAmort as number[]).reduce((s, v) => s + _num(v), 0)
        : 0
    const amt = annual || monthly
    if (!name || !(amt > 0)) continue
    byName[name] = _round2((byName[name] || 0) + amt)
    totalFromCalc = _round2(totalFromCalc + amt)
  }

  let matched = 0
  const next = rows.map((r) => {
    const hit = byName[r.projectName.trim()]
    if (hit != null) {
      matched++
      return recalcI4AdjudicationRow({ ...r, amortization: Math.max(0, hit) })
    }
    return r
  })
  if (matched > 0) return next

  const total = totalFromCalc || totalAmortFallback
  if (!(total > 0)) return rows
  const bases = rows.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 1)
  const sum = calcSubtotal(bases)
  let left = total
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const amt = isLast ? _round2(left) : _round2(total * (bases[i] / sum))
    left = _round2(left - amt)
    return recalcI4AdjudicationRow({ ...r, amortization: Math.max(0, amt) })
  })
}

export function buildI4AdjudicationCrossCheck(
  rows: I4AdjudicationRowModel[],
  detail: {
    beginBalance?: number
    increase?: number
    amortization?: number
    decrease?: number
    endBalance?: number
    total?: number
  },
): I4AdjudicationCrossCheck {
  const sub = summarizeI4Adjudication(rows)
  const detailBegin = _num(detail.beginBalance)
  const detailIncrease = _num(detail.increase)
  const detailAmortization = _num(detail.amortization)
  const detailDecrease = _num(detail.decrease)
  const detailEnd = _num(detail.endBalance)
  const beginDiff = _round2(sub.beginBalance - detailBegin)
  const endDiff = _round2(sub.endBalance - detailEnd)
  const amortDiff = _round2(sub.amortization - detailAmortization)
  const auditedVsDetailDiff = _round2(sub.audited - detailEnd)
  const hasWarning = [beginDiff, endDiff, amortDiff, auditedVsDetailDiff].some((d) => Math.abs(d) > 0.01)
  return {
    detailBegin,
    detailIncrease,
    detailAmortization,
    detailDecrease,
    detailEnd,
    adjBegin: sub.beginBalance,
    adjIncrease: sub.increase,
    adjAmortization: sub.amortization,
    adjDecrease: sub.decrease,
    adjEnd: sub.endBalance,
    adjAudited: sub.audited,
    beginDiff,
    endDiff,
    amortDiff,
    auditedVsDetailDiff,
    hasWarning,
  }
}

/** Excel 式只读：期初未审/调整/审定 · 期末未审/调整/审定 · 变动 */
export function buildI4ExcelLeadSummary(rows: I4AdjudicationRowModel[]): {
  beginUnadj: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAdj: number
  endAudited: number
  varianceAmount: number
  varianceRate: number | null
} {
  const sub = summarizeI4Adjudication(rows)
  const beginAdj = _round2(sub.aje + sub.rje)
  // 期初审定近似：若无单独期初调整列，用 期初未审（滚动期初）对照；期末用未审/调整/审定
  return {
    beginUnadj: sub.beginBalance,
    beginAdj: 0,
    beginAudited: sub.beginBalance,
    endUnadj: sub.unadjusted,
    endAdj: beginAdj,
    endAudited: sub.audited,
    varianceAmount: sub.varianceAmount,
    varianceRate: sub.varianceRate,
  }
}

/** 按 I4-2 expenseType 聚合只读类别汇总（对齐 Excel 类别 A/B/C） */
export function buildI4CategorySummary(
  adjRows: I4AdjudicationRowModel[],
  detailRows: any[] = [],
): Array<{
  category: string
  begin: number
  increase: number
  amortization: number
  decrease: number
  end: number
  audited: number
}> {
  const typeByName = new Map<string, string>()
  for (const d of detailRows || []) {
    const name = _str(d?.projectName || d?.name).trim()
    if (!name || name === '合计') continue
    const t = _str(d?.expenseType || d?.category || d?.accountCategory).trim() || '其他'
    typeByName.set(name, t)
  }

  const buckets = new Map<string, {
    begin: number
    increase: number
    amortization: number
    decrease: number
    end: number
    audited: number
  }>()

  for (const r of adjRows) {
    if (r.projectName === '合计') continue
    const cat = typeByName.get(r.projectName.trim()) || '未分类'
    const b = buckets.get(cat) || { begin: 0, increase: 0, amortization: 0, decrease: 0, end: 0, audited: 0 }
    b.begin = _round2(b.begin + _num(r.beginBalance))
    b.increase = _round2(b.increase + _num(r.increase))
    b.amortization = _round2(b.amortization + _num(r.amortization))
    b.decrease = _round2(b.decrease + _num(r.decrease))
    b.end = _round2(b.end + _num(r.endBalance))
    b.audited = _round2(b.audited + _num(r.audited))
    buckets.set(cat, b)
  }

  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
    .map(([category, v]) => ({ category, ...v }))
}

/** 一年内到期（剩余月数≤12）候选：供生成 RJE 草稿；自然摊销项目仍列出供人工确认 */
export function extractI4CurrentPortionCandidates(detailRows: any[]): Array<{
  projectName: string
  amount: number
  remainingMonths: number
  expenseType: string
}> {
  const out: Array<{ projectName: string; amount: number; remainingMonths: number; expenseType: string }> = []
  for (const r of detailRows || []) {
    const projectName = _str(r?.projectName || r?.name).trim()
    if (!projectName || projectName === '合计') continue
    const remainingMonths = _num(r?.remainingMonths)
    const endBalance = _num(r?.endBalance)
    if (!(remainingMonths > 0 && remainingMonths <= 12 && endBalance > 0.005)) continue
    out.push({
      projectName,
      amount: _round2(endBalance),
      remainingMonths,
      expenseType: _str(r?.expenseType || r?.category || '其他'),
    })
  }
  return out
}

export function buildI4AdjudicationConclusionDraft(opts: {
  sampleCount: number
  auditedTotal: number
  tbDiff: number
  hasAje: boolean
  crossWarning: boolean
}): string {
  const parts = [
    `长期待摊费用审定表共 ${opts.sampleCount} 个项目，审定合计 ${opts.auditedTotal.toFixed(2)}。`,
  ]
  if (opts.hasAje) {
    parts.push('已按 I4-3 账项调整更新 AJE/RJE。')
  }
  if (Math.abs(opts.tbDiff) < 0.01) {
    parts.push('审定数与 TB(1801) 勾稽一致。')
  } else {
    parts.push(`审定数与 TB 差异 ${opts.tbDiff.toFixed(2)}，须查明。`)
  }
  if (opts.crossWarning) {
    parts.push('与 I4-2 明细存在勾稽差异，请复核带入与摊销测算。')
  }
  parts.push(opts.hasAje
    ? I4_CONCLUSION_OPTIONS[1].text
    : I4_CONCLUSION_OPTIONS[0].text)
  return parts.join('')
}

export function validateI4AdjudicationSave(opts: {
  rows: I4AdjudicationRowModel[]
  tbDiff: number
  force?: boolean
}): { ok: boolean; blockers: string[]; warnings: string[] } {
  const blockers: string[] = []
  const warnings: string[] = []
  if (opts.force) return { ok: true, blockers, warnings }

  for (const r of opts.rows) {
    if (r.hasError || Math.abs(_num(r.triangleDiff)) > 0.01) {
      blockers.push(`${r.projectName || '未命名'}：三角勾稽不平（期末≠期初+增−摊−减）`)
    }
    if (r.ajeApprox) {
      warnings.push(`${r.projectName || '未命名'}：AJE/RJE 为近似分摊，建议复核`)
    }
  }
  if (Math.abs(opts.tbDiff) > 0.01) {
    blockers.push(`与 TB 差异 ${opts.tbDiff.toFixed(2)}，须勾稽为 0 后再回写`)
  }
  return { ok: blockers.length === 0, blockers, warnings }
}
