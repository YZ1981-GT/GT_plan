/**
 * I2-1 审定表纯模型
 * 对齐源表：期初/期末各「未审·账项调整·审定」+ 变动额/率 + 原因分析
 * 合计 / TB数据 / 差异 三行勾稽
 */

export const I2_ADJ_ROWS_KEY = 'I2-1-rows'
export const I2_ADJ_NOTE_KEY = 'I2-1-audit-note'
export const I2_ADJ_CONCLUSION_KEY = 'I2-1-audit-conclusion'
export const I2_ADJ_PRIOR_KEY = 'I2-1-prior-audited' // 上期审定合计（可选手工）

export interface I2AdjudicationRow {
  rowId: string
  projectName: string
  /** 期初未审 */
  beginUnadj: number
  /** 期初账项调整 */
  beginAdj: number
  /** 期初审定（公式） */
  beginAudited: number
  /** 期末未审 */
  endUnadj: number
  /** 期末账项调整（含 AJE/RJE 净额） */
  endAdj: number
  /** 期末审定（公式） */
  endAudited: number
  /** 变动额 = 期末审定 − 期初审定 */
  changeAmount: number
  /** 变动率；期初审定为 0 时为 null（N/A） */
  changeRate: number | null
  /** 原因分析 */
  reasonAnalysis: string
  /** 兼容旧版滚动字段（取数/披露用） */
  increaseCapitalized: number
  decreaseTransfer: number
  decreaseExpense: number
  isAutoFilled?: boolean
  /**
   * 期末调整是否来自 I2-3 比例分摊（非按项目精确匹配）。
   * 为 true 时须人工复核，手工改 endAdj 后应清除。
   */
  ajeApprox?: boolean
}

export interface I2AdjudicationSummary {
  beginUnadj: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAdj: number
  endAudited: number
  changeAmount: number
  changeRate: number | null
  increaseCapitalized: number
  decreaseTransfer: number
  decreaseExpense: number
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
  return `i21-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function calcBeginAudited(unadj: number, adj: number): number {
  return _round2(_num(unadj) + _num(adj))
}

export function calcEndAudited(unadj: number, adj: number): number {
  return _round2(_num(unadj) + _num(adj))
}

export function calcChangeAmount(beginAudited: number, endAudited: number): number {
  return _round2(_num(endAudited) - _num(beginAudited))
}

/** 变动率；分母为 0 返回 null，避免 #DIV/0! */
export function calcChangeRate(beginAudited: number, changeAmount: number): number | null {
  if (Math.abs(_num(beginAudited)) < 0.005) return null
  return _round2((_num(changeAmount) / _num(beginAudited)) * 10000) / 100
}

export function formatChangeRate(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}

export function emptyI2AdjudicationRow(partial?: Partial<I2AdjudicationRow>): I2AdjudicationRow {
  const row: I2AdjudicationRow = {
    rowId: partial?.rowId || _id(),
    projectName: '',
    beginUnadj: 0,
    beginAdj: 0,
    beginAudited: 0,
    endUnadj: 0,
    endAdj: 0,
    endAudited: 0,
    changeAmount: 0,
    changeRate: null,
    reasonAnalysis: '',
    increaseCapitalized: 0,
    decreaseTransfer: 0,
    decreaseExpense: 0,
    isAutoFilled: false,
    ...partial,
  }
  recalcI2AdjudicationRow(row)
  return row
}

export function recalcI2AdjudicationRow(row: I2AdjudicationRow): void {
  row.beginAudited = calcBeginAudited(row.beginUnadj, row.beginAdj)
  row.endAudited = calcEndAudited(row.endUnadj, row.endAdj)
  row.changeAmount = calcChangeAmount(row.beginAudited, row.endAudited)
  row.changeRate = calcChangeRate(row.beginAudited, row.changeAmount)
}

/**
 * 兼容旧版：cipBegin/unadjusted/aje/rje/audited/increaseCapitalized…
 */
export function normalizeI2AdjudicationRow(raw: any): I2AdjudicationRow {
  const hasNew = raw?.beginUnadj != null || raw?.endUnadj != null || raw?.beginAudited != null

  let beginUnadj = 0
  let beginAdj = 0
  let endUnadj = 0
  let endAdj = 0

  if (hasNew) {
    beginUnadj = _num(raw.beginUnadj)
    beginAdj = _num(raw.beginAdj)
    endUnadj = _num(raw.endUnadj)
    endAdj = _num(raw.endAdj)
  } else {
    // 旧滚动结构 → 映射到期初/期末审定视图
    beginUnadj = _num(raw.cipBegin ?? raw.beginBalance)
    beginAdj = 0
    endUnadj = _num(raw.unadjusted ?? raw.cipEnd ?? raw.endBalance)
    endAdj = _num(raw.aje) + _num(raw.rje)
    // 若有 audited 且与 unadj+adj 不一致，以 audited 反推 endAdj
    if (raw.audited != null && Math.abs(_num(raw.audited) - (endUnadj + endAdj)) > 0.01) {
      endAdj = _round2(_num(raw.audited) - endUnadj)
    }
  }

  return emptyI2AdjudicationRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.name),
    beginUnadj,
    beginAdj,
    endUnadj,
    endAdj,
    reasonAnalysis: _str(raw?.reasonAnalysis || raw?.remark),
    increaseCapitalized: _num(raw?.increaseCapitalized),
    decreaseTransfer: _num(raw?.decreaseTransfer ?? raw?.decreaseToIntangible),
    decreaseExpense: _num(raw?.decreaseExpense ?? raw?.decreaseToExpense),
    isAutoFilled: !!raw?.isAutoFilled,
    ajeApprox: !!raw?.ajeApprox,
  })
}

export function summarizeI2Adjudication(rows: I2AdjudicationRow[]): I2AdjudicationSummary {
  const data = rows.filter((r) => r.projectName !== '合计' && r.projectName !== 'TB数据' && r.projectName !== '差异')
  const beginUnadj = _round2(data.reduce((s, r) => s + r.beginUnadj, 0))
  const beginAdj = _round2(data.reduce((s, r) => s + r.beginAdj, 0))
  const beginAudited = calcBeginAudited(beginUnadj, beginAdj)
  const endUnadj = _round2(data.reduce((s, r) => s + r.endUnadj, 0))
  const endAdj = _round2(data.reduce((s, r) => s + r.endAdj, 0))
  const endAudited = calcEndAudited(endUnadj, endAdj)
  const changeAmount = calcChangeAmount(beginAudited, endAudited)
  return {
    beginUnadj,
    beginAdj,
    beginAudited,
    endUnadj,
    endAdj,
    endAudited,
    changeAmount,
    changeRate: calcChangeRate(beginAudited, changeAmount),
    increaseCapitalized: _round2(data.reduce((s, r) => s + r.increaseCapitalized, 0)),
    decreaseTransfer: _round2(data.reduce((s, r) => s + r.decreaseTransfer, 0)),
    decreaseExpense: _round2(data.reduce((s, r) => s + r.decreaseExpense, 0)),
  }
}

/** 从 I2-2 明细带入 */
export function seedAdjudicationFromI22(detailRows: any[]): I2AdjudicationRow[] {
  return detailRows
    .filter((r) => {
      const n = _str(r?.projectName || r?.name).trim()
      return n && n !== '合计'
    })
    .map((r) => emptyI2AdjudicationRow({
      projectName: _str(r.projectName || r.name),
      beginUnadj: _num(r.capBeginAmount ?? r.beginBalance ?? r.priorEnd),
      endUnadj: _num(r.auditedEnd ?? r.capEndAmount ?? r.capNetValue ?? r.adjustedBalance),
      increaseCapitalized: _num(r.capIncrease),
      decreaseTransfer: _num(r.transferToI1),
      decreaseExpense: _num(r.decreaseToExpense),
      reasonAnalysis: '',
      isAutoFilled: true,
    }))
}

function _isDevExpAdjLine(line: any): boolean {
  const code = _str(line?.accountCode || line?.standard_account_code)
  return code.startsWith('1717') || _str(line?.accountName).includes('开发支出')
}

function _lineNet(line: any): number {
  return _round2(_num(line?.debitAmount ?? line?.debit) - _num(line?.creditAmount ?? line?.credit))
}

function _lineProjectName(line: any): string {
  return _str(line?.projectName || line?.project || line?.memo || line?.description).trim()
}

/**
 * 从 I2-3 调整净额写入期末调整：
 * 1) 优先按分录行「项目名」精确匹配到审定表行（精确，不标近似）
 * 2) 剩余净额：单行项目直接计入；多行按期末未审占比分摊并标 ajeApprox=true
 */
export function applyAjeFromI23(
  rows: I2AdjudicationRow[],
  adjRows: any[],
): { rows: I2AdjudicationRow[]; applied: number; approx: boolean; totalAje: number; matchedByName: number } {
  let totalAje = 0
  const named: Array<{ name: string; net: number }> = []
  for (const g of adjRows) {
    const lines = Array.isArray(g?.lines) ? g.lines : [g]
    for (const line of lines) {
      if (!_isDevExpAdjLine(line)) continue
      const net = _lineNet(line)
      totalAje = _round2(totalAje + net)
      const pname = _lineProjectName(line)
      if (pname) named.push({ name: pname, net })
    }
  }
  if (Math.abs(totalAje) < 0.005 || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, ajeApprox: false, endAdj: 0 }))
  const byName = new Map(next.map((r) => [r.projectName.trim(), r]))
  let matchedByName = 0
  let namedAllocated = 0

  for (const { name, net } of named) {
    const row = byName.get(name)
    if (!row) continue
    row.endAdj = _round2(row.endAdj + net)
    row.ajeApprox = false
    matchedByName++
    namedAllocated = _round2(namedAllocated + net)
  }

  const remainder = _round2(totalAje - namedAllocated)
  let approx = false
  let applied = matchedByName

  if (Math.abs(remainder) >= 0.005) {
    const weightSum = next.reduce((s, r) => s + Math.abs(r.endUnadj), 0)
    if (next.length === 1 || weightSum < 0.005) {
      next[0].endAdj = _round2(next[0].endAdj + remainder)
      // 单行全额计入不算近似；若此前已有按名匹配仍有余量，标复核
      if (matchedByName > 0) {
        next[0].ajeApprox = true
        approx = true
      }
      applied = Math.max(applied, 1)
    } else {
      approx = true
      let allocated = 0
      for (let i = 0; i < next.length; i++) {
        const w = Math.abs(next[i].endUnadj) / weightSum
        const amt = i === next.length - 1 ? _round2(remainder - allocated) : _round2(remainder * w)
        next[i].endAdj = _round2(next[i].endAdj + amt)
        next[i].ajeApprox = true
        allocated = _round2(allocated + amt)
      }
      applied = next.length
    }
  }

  for (const r of next) recalcI2AdjudicationRow(r)
  return { rows: next, applied, approx, totalAje, matchedByName }
}

export function serializeI2AdjudicationRow(row: I2AdjudicationRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    projectName: row.projectName,
    beginUnadj: row.beginUnadj,
    beginAdj: row.beginAdj,
    endUnadj: row.endUnadj,
    endAdj: row.endAdj,
    reasonAnalysis: row.reasonAnalysis,
    increaseCapitalized: row.increaseCapitalized,
    decreaseTransfer: row.decreaseTransfer,
    decreaseExpense: row.decreaseExpense,
    isAutoFilled: row.isAutoFilled,
    ajeApprox: !!row.ajeApprox,
    // 兼容旧消费者
    cipBegin: row.beginAudited,
    unadjusted: row.endUnadj,
    aje: row.endAdj,
    rje: 0,
    audited: row.endAudited,
    remark: row.reasonAnalysis,
  }
}

export function safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    return safeParseArray(obj.remark ?? obj.conclusion)
  }
  return []
}

export function readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}
