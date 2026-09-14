/**
 * wpDisclosureAdjReconcile — 附注期末 vs 审定合计双向勾稽（纯函数）
 */
function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

export interface DisclosureAdjReconcileResult {
  disclosureTotal: number
  adjudicatedTotal: number
  diff: number
  hasBoth: boolean
  matched: boolean
}

export function reconcileDisclosureVsAdjudication(
  disclosureTotal: number,
  adjudicatedTotal: number,
  tol = 0.01,
): DisclosureAdjReconcileResult {
  const d = _round2(disclosureTotal)
  const a = _round2(adjudicatedTotal)
  const diff = _round2(d - a)
  const hasBoth = Math.abs(d) > 0.005 && Math.abs(a) > 0.005
  return {
    disclosureTotal: d,
    adjudicatedTotal: a,
    diff,
    hasBoth,
    matched: !hasBoth || Math.abs(diff) <= tol,
  }
}

export function sumAuditedFromAdjRows(rows: any[], auditedKeys = ['audited', '审定']): number {
  return _round2(rows.reduce((s, r) => {
    for (const k of auditedKeys) {
      if (r?.[k] != null) return s + _num(r[k])
    }
    return s
  }, 0))
}

export function sumEndFromDiscRows(rows: any[], endKeys = ['endBalance', '期末余额', 'closingBalance']): number {
  return _round2(rows.reduce((s, r) => {
    for (const k of endKeys) {
      if (r?.[k] != null) return s + _num(r[k])
    }
    return s
  }, 0))
}

/** I4：附注上市/国企 rows vs I4-adj-rows */
export function reconcileI4DisclosureVsAdj(map: Map<string, any>): DisclosureAdjReconcileResult {
  const adj = _safeParseArray(map.get('I4-adj-rows')).length
    ? _safeParseArray(map.get('I4-adj-rows'))
    : _safeParseArray(map.get('I4-1-rows'))
  const listed = _safeParseArray(map.get('I4-disc-listed-rows'))
  const soe = _safeParseArray(map.get('I4-disc-soe-rows'))
  const disc = listed.length ? listed : soe
  return reconcileDisclosureVsAdjudication(
    sumEndFromDiscRows(disc),
    sumAuditedFromAdjRows(adj),
  )
}

/** I5：附注账面价值/期末余额 vs I5-adj-rows */
export function reconcileI5DisclosureVsAdj(map: Map<string, any>): DisclosureAdjReconcileResult {
  const adj = _safeParseArray(map.get('I5-adj-rows')).length
    ? _safeParseArray(map.get('I5-adj-rows'))
    : _safeParseArray(map.get('I5-1-rows'))
  const listed = _safeParseArray(map.get('I5-disc-listed-rows'))
  const soe = _safeParseArray(map.get('I5-disc-soe-rows'))
  const movement = _safeParseArray(map.get('I5-disc-movement-rows'))
  const legacyListed = _safeParseArray(map.get('I5-disc-listed-movement-matrix'))
  const legacySoe = _safeParseArray(map.get('I5-disc-soe-movement-matrix'))
  const disc = listed.length
    ? listed
    : (soe.length ? soe : (movement.length ? movement : (legacyListed.length ? legacyListed : legacySoe)))
  return reconcileDisclosureVsAdjudication(
    sumEndFromDiscRows(disc, ['endBookValue', 'endBalance', '期末余额', 'closingBalance', '账面价值']),
    sumAuditedFromAdjRows(adj),
  )
}

/** I3：附注净值合计 vs 审定 audited */
export function reconcileI3DisclosureVsAdj(map: Map<string, any>): DisclosureAdjReconcileResult {
  const adj = _safeParseArray(map.get('I3-adj-rows')).length
    ? _safeParseArray(map.get('I3-adj-rows'))
    : _safeParseArray(map.get('I3-1-rows'))
  const listed = _safeParseArray(map.get('I3-disc-listed-rows'))
  const soe = _safeParseArray(map.get('I3-disc-soe-rows'))
  const disc = listed.length ? listed : soe
  const discTotal = sumEndFromDiscRows(disc, ['endBalance', 'netValue', 'goodwillNetValue', '期末余额'])
  const adjTotal = sumAuditedFromAdjRows(adj, ['audited', 'netValue', '审定'])
  return reconcileDisclosureVsAdjudication(discTotal, adjTotal)
}

/** I6：附注本期发生额 vs I6-1 审定合计 */
export function reconcileI6DisclosureVsAdj(map: Map<string, any>): DisclosureAdjReconcileResult {
  const adj = _safeParseArray(map.get('I6-1-rows')).length
    ? _safeParseArray(map.get('I6-1-rows'))
    : _safeParseArray(map.get('I6-adj-rows'))
  const listed = _safeParseArray(map.get('I6-disc-listed-rows')).length
    ? _safeParseArray(map.get('I6-disc-listed-rows'))
    : _safeParseArray(map.get('I6-disc-L-categories'))
  const soe = _safeParseArray(map.get('I6-disc-soe-rows')).length
    ? _safeParseArray(map.get('I6-disc-soe-rows'))
    : _safeParseArray(map.get('I6-disc-S-categories'))
  const disc = listed.length ? listed : soe
  const discTotal = _round2(disc.reduce((s, r) => s + _num(r.currentAmount ?? r.本期发生额), 0))
  const adjTotal = _round2(adj
    .filter((r) => !r?.isTotal && !r?.isSubtotal && r?.项目 !== '小计' && r?.类别 !== '小计')
    .reduce((s, r) => s + _num(r.本期审定 ?? r.audited), 0))
  return reconcileDisclosureVsAdjudication(discTotal, adjTotal)
}
