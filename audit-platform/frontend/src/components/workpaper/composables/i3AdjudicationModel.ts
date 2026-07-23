/**
 * i3AdjudicationModel — I3-1 商誉审定表纯函数
 *
 * 对齐致同 Excel「审定表 I3-1」编制逻辑：
 *   未审数(期初/增/减/期末) → 账项调整 → 审定数(期初/增/减/期末)
 *   行来源：明细表 I3-2；调整来自 I3-3；本期减值可自 I3-6
 *   勾稽：审定期末 ≈ I3-2 净值合计；与 TB 1711 差异须为 0
 *
 * 数字版按「被投资单位」一行承载原值/减值/净额，公式：
 *   期末 = 期初 + 新并购 − 本期减值（商誉不摊销）
 *   审定 = 未审 + AJE + RJE
 *   净额 = 初始确认(原值) − 累计减值
 */

import {
  calcAuditedAmount,
  calcGoodwillEndBalance,
  calcGoodwillNetValue,
  calcSubtotal,
} from './useI3FormulaEngine'

export const I3_ADJ_ROWS_KEY = 'I3-adj-rows'
/** 后端/历史导入曾用键，加载时作候选 */
export const I3_ADJ_ROWS_KEY_LEGACY = 'I3-1-adj-rows'
export const I3_ADJ_NOTE_KEY = 'I3-adj-audit-note'
export const I3_ADJ_CONCLUSION_KEY = 'I3-adj-audit-conclusion'
export const I3_ADJ_ROWS_CANDIDATES = [I3_ADJ_ROWS_KEY, I3_ADJ_ROWS_KEY_LEGACY, 'I3-1-rows'] as const

export interface I3AdjudicationRowModel {
  rowId: string
  investee: string
  /** 初始确认（商誉原值） */
  initialRecognition: number
  /** 期初净额 */
  beginBalance: number
  /** 本期增加（仅新并购） */
  newAcquisition: number
  /** 本期减少（仅减值，≥0） */
  impairment: number
  /** 期末净额（公式） */
  endBalance: number
  /** 未审数（通常=账面期末净额） */
  unadjusted: number
  aje: number
  rje: number
  /** 审定数（公式） */
  audited: number
  /** 累计减值准备期末 */
  accImpairment: number
  /** 净额 = 原值 − 累计减值（应与 endBalance 勾稽） */
  netValue: number
  indexRef?: string
  isEditable?: boolean
  /** 自 I3-2 带入标记 */
  fromDetail?: boolean
  /**
   * 期末调整是否来自 I3-3 比例分摊（非按被投资单位精确匹配）。
   * 为 true 时须人工复核；手工改 aje/rje 后应清除。
   */
  ajeApprox?: boolean
}

export interface I3AdjudicationCrossCheck {
  detailOriginal: number
  detailAccImpairment: number
  detailNet: number
  detailCurrentImpairment: number
  adjOriginal: number
  adjAccImpairment: number
  adjNet: number
  adjCurrentImpairment: number
  originalDiff: number
  netDiff: number
  impairmentDiff: number
  endVsNetDiff: number
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
  return `i31-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function _yearOf(dateStr: string): number | null {
  const m = /^(\d{4})/.exec((dateStr || '').trim())
  return m ? Number(m[1]) : null
}

export function recalcI3AdjudicationRow(row: I3AdjudicationRowModel): I3AdjudicationRowModel {
  const impairment = Math.max(0, _num(row.impairment))
  const endBalance = _round2(calcGoodwillEndBalance(
    _num(row.beginBalance),
    _num(row.newAcquisition),
    impairment,
  ))
  const audited = _round2(calcAuditedAmount(_num(row.unadjusted), _num(row.aje), _num(row.rje)))
  const netValue = _round2(calcGoodwillNetValue(_num(row.initialRecognition), _num(row.accImpairment)))
  return {
    ...row,
    impairment,
    endBalance,
    audited,
    netValue,
  }
}

export function emptyI3AdjudicationRow(
  partial?: Partial<I3AdjudicationRowModel>,
): I3AdjudicationRowModel {
  return recalcI3AdjudicationRow({
    rowId: partial?.rowId || _id(),
    investee: '',
    initialRecognition: 0,
    beginBalance: 0,
    newAcquisition: 0,
    impairment: 0,
    endBalance: 0,
    unadjusted: 0,
    aje: 0,
    rje: 0,
    audited: 0,
    accImpairment: 0,
    netValue: 0,
    indexRef: '',
    isEditable: true,
    fromDetail: false,
    ajeApprox: false,
    ...partial,
  })
}

export function normalizeI3AdjudicationRow(raw: any): I3AdjudicationRowModel {
  return emptyI3AdjudicationRow({
    rowId: _str(raw?.rowId) || undefined,
    investee: _str(raw?.investee || raw?.projectName || raw?.name),
    initialRecognition: _num(raw?.initialRecognition ?? raw?.goodwillOriginal),
    beginBalance: _num(raw?.beginBalance),
    newAcquisition: _num(raw?.newAcquisition),
    impairment: _num(raw?.impairment ?? raw?.currentImpairment),
    unadjusted: _num(raw?.unadjusted),
    aje: _num(raw?.aje),
    rje: _num(raw?.rje),
    accImpairment: _num(raw?.accImpairment ?? raw?.accImpairmentEnd),
    indexRef: _str(raw?.indexRef),
    isEditable: raw?.isEditable !== false,
    fromDetail: !!raw?.fromDetail,
    ajeApprox: !!raw?.ajeApprox,
  })
}

export function summarizeI3Adjudication(rows: I3AdjudicationRowModel[]): I3AdjudicationRowModel {
  const detail = rows.filter((r) => r.investee !== '合计')
  return emptyI3AdjudicationRow({
    rowId: 'row-subtotal',
    investee: '合计',
    initialRecognition: calcSubtotal(detail.map((r) => r.initialRecognition)),
    beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
    newAcquisition: calcSubtotal(detail.map((r) => r.newAcquisition)),
    impairment: calcSubtotal(detail.map((r) => r.impairment)),
    endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
    aje: calcSubtotal(detail.map((r) => r.aje)),
    rje: calcSubtotal(detail.map((r) => r.rje)),
    audited: calcSubtotal(detail.map((r) => r.audited)),
    accImpairment: calcSubtotal(detail.map((r) => r.accImpairment)),
    netValue: calcSubtotal(detail.map((r) => r.netValue)),
    isEditable: false,
  })
}

/** 解析 I3-2 行数组 */
export function parseI32DetailRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (typeof remark === 'string' && remark) {
      try {
        const p = JSON.parse(remark)
        return Array.isArray(p) ? p : []
      } catch { return [] }
    }
    if (Array.isArray(remark)) return remark
  }
  return []
}

/**
 * 从 I3-2 明细带入审定表行（对齐 Excel 从明细表取数）。
 * - 当年并购：期初=0，本期增加=原值
 * - 往年并购：期初=原值−累计减值期初，本期增加=0
 * - 本期减少=本期减值；累计减值=期末累计减值
 * - 未审数默认=期末净额
 */
export function seedI3AdjudicationFromDetail(
  detailRaw: unknown,
  asOfYear?: number,
  existing?: I3AdjudicationRowModel[],
): I3AdjudicationRowModel[] {
  const year = asOfYear ?? new Date().getFullYear()
  const details = parseI32DetailRows(detailRaw).filter((r) => {
    const name = _str(r?.investee || r?.projectName || r?.name)
    return name && name !== '合计'
  })
  if (!details.length) return existing?.length ? existing.map(normalizeI3AdjudicationRow) : []

  const byName = new Map((existing || []).map((r) => [r.investee, r]))
  const out: I3AdjudicationRowModel[] = []

  for (const d of details) {
    const investee = _str(d.investee || d.projectName || d.name)
    const original = _num(d.goodwillOriginal ?? d.costAudited)
    const accBegin = _num(d.accImpairmentBegin ?? d.impOpening)
    const accEnd = _num(d.accImpairmentEnd ?? d.impAudited ?? d.accImpairment)
    const currentImp = _num(d.currentImpairment ?? d.impIncrease)
    const costIncrease = _num(d.costIncrease ?? d.periodDebit)
    const netEnd = _num(d.goodwillNetValue ?? d.netValueEnd)
      || _round2(original - accEnd)
    const acqYear = _yearOf(_str(d.mergerDate || d.acquisitionDate))
    const isNew = (costIncrease > 0) || (acqYear != null && acqYear === year)

    const prev = byName.get(investee)
    const beginBalance = isNew && costIncrease > 0
      ? _round2(original - costIncrease - accBegin)
      : (isNew ? 0 : _round2(original - accBegin))
    const newAcquisition = costIncrease > 0 ? costIncrease : (isNew ? original : 0)

    out.push(recalcI3AdjudicationRow({
      rowId: prev?.rowId || _id(),
      investee,
      initialRecognition: original,
      beginBalance,
      newAcquisition,
      impairment: currentImp,
      endBalance: 0,
      unadjusted: netEnd || _round2(beginBalance + newAcquisition - currentImp),
      aje: prev?.aje ?? 0,
      rje: prev?.rje ?? 0,
      audited: 0,
      accImpairment: accEnd,
      netValue: 0,
      indexRef: prev?.indexRef || 'I3-2',
      isEditable: true,
      fromDetail: true,
    }))
  }
  return out
}

/** 按未审数占比分摊 AJE/RJE 合计到各行（全部分摊均标 ajeApprox） */
export function allocateI3Adjustments(
  rows: I3AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I3AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI3AdjudicationRow({
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
    return recalcI3AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

/**
 * 从 I3-3 调整行写入审定表 AJE/RJE（对齐 I2 applyAjeFromI23）：
 * 1) 优先按 investee / description 精确匹配（不标近似）
 * 2) 剩余净额：单行直接计入；多行按未审占比分摊并标 ajeApprox
 */
export function applyAjeFromI33(
  rows: I3AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I3AdjudicationRowModel[]
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
    const code = String(line?.accountCode || '')
    if (!code.startsWith('1711')) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const et = String(line?.entryType || (line?.category === '报表调整' ? 'RJE' : 'AJE'))
    const name = _str(line?.investee || line?.projectName || line?.description || line?.remark).trim()
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
  const byName = new Map(next.map((r) => [r.investee.trim(), r]))
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

  if (Math.abs(ajeRem) >= 0.005 || Math.abs(rjeRem) >= 0.005) {
    const weightSum = next.reduce((s, r) => s + (Math.abs(r.unadjusted) || Math.abs(r.endBalance)), 0)
    if (next.length === 1 || weightSum < 0.005) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
      if (matchedByName > 0 && next.length > 1) {
        next[0].ajeApprox = true
        approx = true
      }
      applied = Math.max(applied, 1)
    } else {
      approx = true
      let ajeAlloc = 0
      let rjeAlloc = 0
      for (let i = 0; i < next.length; i++) {
        const w = (Math.abs(next[i].unadjusted) || Math.abs(next[i].endBalance)) / weightSum
        const aAmt = i === next.length - 1 ? _round2(ajeRem - ajeAlloc) : _round2(ajeRem * w)
        const rAmt = i === next.length - 1 ? _round2(rjeRem - rjeAlloc) : _round2(rjeRem * w)
        next[i].aje = _round2(next[i].aje + aAmt)
        next[i].rje = _round2(next[i].rje + rAmt)
        next[i].ajeApprox = true
        ajeAlloc = _round2(ajeAlloc + aAmt)
        rjeAlloc = _round2(rjeAlloc + rAmt)
      }
      applied = next.length
    }
  }

  return {
    rows: next.map(recalcI3AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

/** Excel 式三层只读汇总：原始金额 / 减值准备 / 净值 */
export function buildI3LayerSummary(rows: I3AdjudicationRowModel[]): {
  original: { begin: number; increase: number; decrease: number; end: number; audited: number }
  impairment: { begin: number; increase: number; decrease: number; end: number; audited: number }
  net: { begin: number; increase: number; decrease: number; end: number; audited: number }
} {
  const sub = summarizeI3Adjudication(rows)
  const originalEnd = sub.initialRecognition
  const originalBegin = _round2(sub.initialRecognition - sub.newAcquisition)
  const impEnd = sub.accImpairment
  const impBegin = _round2(sub.accImpairment - sub.impairment)
  return {
    original: {
      begin: originalBegin,
      increase: sub.newAcquisition,
      decrease: 0,
      end: originalEnd,
      audited: originalEnd,
    },
    impairment: {
      begin: Math.max(0, impBegin),
      increase: sub.impairment,
      decrease: 0,
      end: impEnd,
      audited: impEnd,
    },
    net: {
      begin: sub.beginBalance,
      increase: sub.newAcquisition,
      decrease: sub.impairment,
      end: sub.endBalance,
      audited: sub.audited,
    },
  }
}

/** 保存前闸门：期末≠净额、TB 差异 */
export function validateI3AdjudicationSave(opts: {
  rows: I3AdjudicationRowModel[]
  tbDiff: number
  force?: boolean
}): { ok: boolean; blockers: string[]; warnings: string[] } {
  const blockers: string[] = []
  const warnings: string[] = []
  if (opts.force) return { ok: true, blockers, warnings }

  for (const r of opts.rows) {
    if (Math.abs(_num(r.endBalance) - _num(r.netValue)) > 0.01) {
      blockers.push(`${r.investee || '未命名'}：期末(${r.endBalance})≠净额(${r.netValue})`)
    }
    if (r.ajeApprox) {
      warnings.push(`${r.investee || '未命名'}：AJE/RJE 为近似分摊，建议复核`)
    }
  }
  if (Math.abs(opts.tbDiff) > 0.01) {
    blockers.push(`与 TB 差异 ${opts.tbDiff.toFixed(2)}，须勾稽为 0 后再回写`)
  }
  return { ok: blockers.length === 0, blockers, warnings }
}

/** 用 I3-6 商誉承担减值覆盖「本期减少」；无法按名称匹配时回退按合计比例 */
export function applyI3ImpairmentFromTest(
  rows: I3AdjudicationRowModel[],
  byCguOrInvestee: Record<string, number>,
  totalGoodwillImpairment: number,
): I3AdjudicationRowModel[] {
  if (!rows.length) return rows
  const keyed = { ...byCguOrInvestee }
  let matched = 0
  const next = rows.map((r) => {
    const hit = keyed[r.investee]
    if (hit != null && Number.isFinite(hit)) {
      matched++
      return recalcI3AdjudicationRow({ ...r, impairment: Math.max(0, _num(hit)) })
    }
    return r
  })
  if (matched > 0) return next
  if (!(totalGoodwillImpairment > 0)) return rows
  // 无名称匹配：按原值占比分摊总减值
  const bases = rows.map((r) => Math.abs(r.initialRecognition) || Math.abs(r.beginBalance))
  const sum = calcSubtotal(bases)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI3AdjudicationRow({
      ...r,
      impairment: i === 0 ? totalGoodwillImpairment : r.impairment,
    }))
  }
  let left = totalGoodwillImpairment
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const amt = isLast ? _round2(left) : _round2(totalGoodwillImpairment * (bases[i] / sum))
    left = _round2(left - amt)
    return recalcI3AdjudicationRow({ ...r, impairment: Math.max(0, amt) })
  })
}

export function buildI3AdjudicationCrossCheck(
  rows: I3AdjudicationRowModel[],
  detail: {
    goodwillOriginalTotal: number
    accImpairmentTotal: number
    netValueTotal: number
    currentImpairmentTotal: number
  },
): I3AdjudicationCrossCheck {
  const sub = summarizeI3Adjudication(rows)
  const originalDiff = _round2(sub.initialRecognition - _num(detail.goodwillOriginalTotal))
  const netDiff = _round2(sub.netValue - _num(detail.netValueTotal))
  const impairmentDiff = _round2(sub.impairment - _num(detail.currentImpairmentTotal))
  const endVsNetDiff = _round2(sub.endBalance - sub.netValue)
  return {
    detailOriginal: _num(detail.goodwillOriginalTotal),
    detailAccImpairment: _num(detail.accImpairmentTotal),
    detailNet: _num(detail.netValueTotal),
    detailCurrentImpairment: _num(detail.currentImpairmentTotal),
    adjOriginal: sub.initialRecognition,
    adjAccImpairment: sub.accImpairment,
    adjNet: sub.netValue,
    adjCurrentImpairment: sub.impairment,
    originalDiff,
    netDiff,
    impairmentDiff,
    endVsNetDiff,
    hasWarning:
      Math.abs(originalDiff) > 0.01
      || Math.abs(netDiff) > 0.01
      || Math.abs(impairmentDiff) > 0.01
      || Math.abs(endVsNetDiff) > 0.01,
  }
}

export function buildI3AdjudicationConclusionDraft(opts: {
  rowCount: number
  auditedTotal: number
  netTotal: number
  newAcquisitionTotal: number
  impairmentTotal: number
  tbDiff: number
  crossCheck?: I3AdjudicationCrossCheck | null
}): string {
  const parts = [
    `经审定，商誉(1711)共 ${opts.rowCount} 个被投资单位，审定合计 ${opts.auditedTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，净额 ${opts.netTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}。`,
  ]
  if (opts.newAcquisitionTotal > 0) {
    parts.push(`本期新增并购确认商誉 ${opts.newAcquisitionTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，已核对入账依据（见 I3-4）。`)
  } else {
    parts.push('本期无新并购商誉确认。')
  }
  if (opts.impairmentTotal > 0) {
    parts.push(`本期计提商誉减值 ${opts.impairmentTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（不可转回），详见 I3-6~I3-8。`)
  } else {
    parts.push('本期未计提商誉减值。')
  }
  if (Math.abs(opts.tbDiff) > 0.01) {
    parts.push(`与 TB 差异 ${opts.tbDiff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，需进一步核对。`)
  } else {
    parts.push('与试算平衡表(1711)勾稽一致。')
  }
  if (opts.crossCheck?.hasWarning) {
    parts.push('与 I3-2 明细合计存在差异，请复核勾稽后再定稿。')
  } else if (opts.crossCheck) {
    parts.push('与 I3-2 明细原值/净值勾稽一致。')
  }
  parts.push('商誉不摊销，期末余额列报在重大方面恰当。')
  return parts.join('')
}
