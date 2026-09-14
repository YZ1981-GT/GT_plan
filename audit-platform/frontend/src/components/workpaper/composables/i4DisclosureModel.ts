/**
 * I4 附注披露数据模型（上市/国企）
 *
 * 对齐源 xlsx：长期待摊费用为「账面余额滚动表」——摊销直接冲减账面，
 * 无单独累计摊销备抵（区别于固定资产/无形资产）。
 *
 * 上市：项目 | 期初 | 本期增加 | 本期摊销 | 其他减少 | 期末
 * 国企：同上 + 其他减少的原因
 * 期末 = 期初 + 增加 − 摊销 − 其他减少
 */
import { I4_DEFAULT_DISCLOSURE_CATEGORIES } from './i4NoteSectionMap'

export interface I4DisclosureRow {
  rowId: string
  /** 披露项目（类别） */
  item: string
  beginBalance: number
  increase: number
  amortization: number
  otherDecrease: number
  endBalance: number
  /** 国企：其他减少原因 */
  otherDecreaseReason: string
  isAutoFilled: boolean
  remark: string
}

export interface I4DisclosureTotals {
  beginBalance: number
  increase: number
  amortization: number
  otherDecrease: number
  endBalance: number
}

export const I4_DISC_KEYS = {
  listedRows: 'I4-disc-listed-rows',
  listedCurrentPortion: 'I4-disc-listed-current-portion',
  listedNote: 'I4-disc-listed-other-note',
  listedAuditNote: 'I4-disclosure-listed-audit-note',
  listedAuditConclusion: 'I4-disclosure-listed-audit-conclusion',
  soeRows: 'I4-disc-soe-rows',
  soeNote: 'I4-disc-soe-other-note',
  soeAuditNote: 'I4-disclosure-soe-audit-note',
  soeAuditConclusion: 'I4-disclosure-soe-audit-conclusion',
} as const

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

export function calcI4DisclosureEnd(row: Pick<I4DisclosureRow, 'beginBalance' | 'increase' | 'amortization' | 'otherDecrease'>): number {
  return _round2(
    _num(row.beginBalance) + _num(row.increase) - _num(row.amortization) - _num(row.otherDecrease),
  )
}

export function emptyI4DisclosureRow(partial?: Partial<I4DisclosureRow>): I4DisclosureRow {
  const row: I4DisclosureRow = {
    rowId: partial?.rowId || `i4d-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    item: partial?.item ?? '',
    beginBalance: _num(partial?.beginBalance),
    increase: _num(partial?.increase),
    amortization: _num(partial?.amortization),
    otherDecrease: _num(partial?.otherDecrease),
    endBalance: 0,
    otherDecreaseReason: partial?.otherDecreaseReason ?? '',
    isAutoFilled: !!partial?.isAutoFilled,
    remark: partial?.remark ?? '',
  }
  row.endBalance = calcI4DisclosureEnd(row)
  return row
}

export function normalizeI4DisclosureRow(raw: any): I4DisclosureRow {
  return emptyI4DisclosureRow({
    rowId: raw?.rowId,
    item: raw?.item ?? raw?.name ?? raw?.category ?? '',
    beginBalance: raw?.beginBalance ?? raw?.opening ?? raw?.期初,
    increase: raw?.increase ?? raw?.本期增加,
    amortization: raw?.amortization ?? raw?.本期摊销,
    otherDecrease: raw?.otherDecrease ?? raw?.decrease ?? raw?.其他减少,
    otherDecreaseReason: raw?.otherDecreaseReason ?? raw?.reason ?? '',
    isAutoFilled: !!raw?.isAutoFilled,
    remark: raw?.remark ?? '',
  })
}

export function summarizeI4Disclosure(rows: I4DisclosureRow[]): I4DisclosureTotals {
  const t: I4DisclosureTotals = {
    beginBalance: 0,
    increase: 0,
    amortization: 0,
    otherDecrease: 0,
    endBalance: 0,
  }
  for (const r of rows) {
    t.beginBalance += _num(r.beginBalance)
    t.increase += _num(r.increase)
    t.amortization += _num(r.amortization)
    t.otherDecrease += _num(r.otherDecrease)
    t.endBalance += _num(r.endBalance)
  }
  t.beginBalance = _round2(t.beginBalance)
  t.increase = _round2(t.increase)
  t.amortization = _round2(t.amortization)
  t.otherDecrease = _round2(t.otherDecrease)
  t.endBalance = _round2(t.endBalance)
  return t
}

/** 从 I4-2 明细行解析披露标签 */
export function resolveI4DisclosureLabel(detail: any): string {
  const expenseType = String(detail?.expenseType ?? '').trim()
  const assetType = String(detail?.assetType ?? '').trim()
  const category = String(detail?.category ?? '').trim()
  if (expenseType && expenseType !== '其他') return expenseType
  if (assetType) {
    if (/租入|改良/.test(assetType)) return '使用权资产改良及维护支出'
    if (/大修理/.test(assetType)) return '固定资产大修理支出'
    if (/开办/.test(assetType)) return '开办费'
    return assetType
  }
  if (category && !/^类别[ABC]$/.test(category) && category !== '未分类') return category
  return I4_DEFAULT_DISCLOSURE_CATEGORIES[0]
}

/**
 * 按披露标签聚合 I4-2 审定数（优先 audited*，回退 unadj* / 旧字段）
 */
export function aggregateI4DetailForDisclosure(detailRows: any[]): I4DisclosureRow[] {
  const map = new Map<string, I4DisclosureRow>()

  for (const d of detailRows || []) {
    const label = resolveI4DisclosureLabel(d)
    const begin = _num(d.auditedOpening ?? d.beginBalance ?? d.unadjOpening ?? d.openingBalance)
    const increase = _num(d.auditedIncrease ?? d.increase ?? d.unadjIncrease ?? d.currentIncrease)
    const amort = _num(d.auditedAmortization ?? d.currentAmortization ?? d.unadjAmortization ?? d.amortization)
    const other = _num(d.auditedOtherDecrease ?? d.decrease ?? d.unadjOtherDecrease ?? d.otherDecrease)

    const cur = map.get(label) || emptyI4DisclosureRow({ item: label, isAutoFilled: true })
    cur.beginBalance = _round2(cur.beginBalance + begin)
    cur.increase = _round2(cur.increase + increase)
    cur.amortization = _round2(cur.amortization + amort)
    cur.otherDecrease = _round2(cur.otherDecrease + other)
    cur.endBalance = calcI4DisclosureEnd(cur)
    cur.isAutoFilled = true
    map.set(label, cur)
  }

  if (!map.size) {
    return [emptyI4DisclosureRow({ item: I4_DEFAULT_DISCLOSURE_CATEGORIES[0], isAutoFilled: false })]
  }
  return [...map.values()].sort((a, b) => a.item.localeCompare(b.item, 'zh'))
}

/**
 * 一年内将摊销完毕的账面余额（信息性披露；按准则提示仍列报于长期待摊，不重分类流动资产）
 * 口径：剩余月数 ∈ (0, 12] 的项目期末审定余额合计
 */
export function calcI4CurrentPortion(detailRows: any[]): number {
  let sum = 0
  for (const d of detailRows || []) {
    const remaining = _num(d.remainingMonths)
    if (remaining <= 0 || remaining > 12) continue
    sum += _num(d.auditedEnding ?? d.endBalance ?? d.unadjEnding ?? d.closingBalance)
  }
  return _round2(sum)
}

export function defaultI4DisclosureRows(): I4DisclosureRow[] {
  return [emptyI4DisclosureRow({ item: I4_DEFAULT_DISCLOSURE_CATEGORIES[0] })]
}

export function mergeAutoFillPreserveManual(
  existing: I4DisclosureRow[],
  autoRows: I4DisclosureRow[],
): I4DisclosureRow[] {
  if (!existing.length) return autoRows
  const manualByItem = new Map(
    existing.filter((r) => !r.isAutoFilled && r.item).map((r) => [r.item, r]),
  )
  const merged: I4DisclosureRow[] = []
  const used = new Set<string>()

  for (const auto of autoRows) {
    const man = manualByItem.get(auto.item)
    if (man) {
      merged.push({ ...man, endBalance: calcI4DisclosureEnd(man) })
      used.add(auto.item)
    } else {
      merged.push(auto)
      used.add(auto.item)
    }
  }
  for (const r of existing) {
    if (r.item && !used.has(r.item)) {
      merged.push({ ...r, endBalance: calcI4DisclosureEnd(r) })
    }
  }
  return merged.length ? merged : autoRows
}
