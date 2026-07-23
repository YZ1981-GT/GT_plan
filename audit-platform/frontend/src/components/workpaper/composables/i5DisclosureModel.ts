/**
 * I5 附注披露数据模型（上市/国企）
 *
 * 对齐源 xlsx：
 * - 上市：项目 | 期末(账面余额/减值准备/账面价值) | 上年年末(账面余额/减值准备/账面价值)
 * - 国企：项目 | 期末余额 | 年初余额
 * - 账面价值 = 账面余额 − 减值准备
 * - 附注模块同步口径：上市写「期末余额/上年年末余额」= 账面价值；国企写「期末余额/期初余额」
 */
import { I5_DEFAULT_DISCLOSURE_CATEGORIES } from './i5NoteSectionMap'

export interface I5DisclosureRow {
  rowId: string
  item: string
  /** 期末账面余额 */
  endGross: number
  /** 期末减值准备 */
  endImpairment: number
  /** 期末账面价值（公式） */
  endBookValue: number
  /** 上年年末/年初 账面余额 */
  priorGross: number
  /** 上年年末减值准备 */
  priorImpairment: number
  /** 上年年末/年初 账面价值（公式；国企即年初余额） */
  priorBookValue: number
  isAutoFilled: boolean
  remark: string
}

export interface I5DisclosureTotals {
  endGross: number
  endImpairment: number
  endBookValue: number
  priorGross: number
  priorImpairment: number
  priorBookValue: number
}

export const I5_DISC_KEYS = {
  listedRows: 'I5-disc-listed-rows',
  listedNote: 'I5-disc-listed-other-note',
  listedAuditNote: 'I5-disclosure-listed-audit-note',
  listedAuditConclusion: 'I5-disclosure-listed-audit-conclusion',
  /** 旧版变动矩阵持久化键（加载时迁移） */
  listedLegacyMatrix: 'I5-disc-listed-movement-matrix',
  soeRows: 'I5-disc-soe-rows',
  soeNote: 'I5-disc-soe-other-note',
  soeAuditNote: 'I5-disclosure-soe-audit-note',
  soeAuditConclusion: 'I5-disclosure-soe-audit-conclusion',
  soeLegacyMatrix: 'I5-disc-soe-movement-matrix',
} as const

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

export function calcI5EndBookValue(row: Pick<I5DisclosureRow, 'endGross' | 'endImpairment'>): number {
  return _round2(_num(row.endGross) - _num(row.endImpairment))
}

export function calcI5PriorBookValue(row: Pick<I5DisclosureRow, 'priorGross' | 'priorImpairment'>): number {
  return _round2(_num(row.priorGross) - _num(row.priorImpairment))
}

export function emptyI5DisclosureRow(partial?: Partial<I5DisclosureRow>): I5DisclosureRow {
  const row: I5DisclosureRow = {
    rowId: partial?.rowId || `i5d-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    item: partial?.item ?? '',
    endGross: _num(partial?.endGross),
    endImpairment: _num(partial?.endImpairment),
    endBookValue: 0,
    priorGross: _num(partial?.priorGross),
    priorImpairment: _num(partial?.priorImpairment),
    priorBookValue: 0,
    isAutoFilled: !!partial?.isAutoFilled,
    remark: partial?.remark ?? '',
  }
  // 国企简化录入：仅给了账面价值时，原值=账面价值、减值为 0
  if (partial?.endBookValue != null && partial.endGross == null && partial.endImpairment == null) {
    row.endGross = _num(partial.endBookValue)
    row.endImpairment = 0
  }
  if (partial?.priorBookValue != null && partial.priorGross == null && partial.priorImpairment == null) {
    row.priorGross = _num(partial.priorBookValue)
    row.priorImpairment = 0
  }
  row.endBookValue = calcI5EndBookValue(row)
  row.priorBookValue = calcI5PriorBookValue(row)
  return row
}

/** 兼容旧变动矩阵行 / 别名字段 */
export function normalizeI5DisclosureRow(raw: any): I5DisclosureRow {
  const hasLegacyMovement = raw
    && (raw.increase != null || raw.decrease != null)
    && raw.endGross == null
    && raw.endBookValue == null

  if (hasLegacyMovement) {
    const end = _num(raw.endBalance ?? raw.期末余额)
    const begin = _num(raw.beginBalance ?? raw.期初余额 ?? raw.年初余额)
    return emptyI5DisclosureRow({
      rowId: raw?.rowId,
      item: raw?.item ?? raw?.name ?? raw?.category ?? '',
      endGross: end,
      endImpairment: 0,
      priorGross: begin,
      priorImpairment: 0,
      isAutoFilled: !!raw?.isAutoFilled,
      remark: raw?.remark ?? '',
    })
  }

  const endBook = raw?.endBookValue ?? raw?.endBalance ?? raw?.期末余额 ?? raw?.账面价值
  const priorBook = raw?.priorBookValue ?? raw?.beginBalance ?? raw?.年初余额 ?? raw?.上年年末余额 ?? raw?.期初余额
  const endGross = raw?.endGross ?? raw?.期末账面余额 ?? raw?.账面余额
  const priorGross = raw?.priorGross ?? raw?.上年账面余额 ?? raw?.期初账面余额

  return emptyI5DisclosureRow({
    rowId: raw?.rowId,
    item: raw?.item ?? raw?.name ?? raw?.category ?? '',
    endGross: endGross != null ? endGross : endBook,
    endImpairment: raw?.endImpairment ?? raw?.期末减值准备 ?? raw?.减值准备 ?? 0,
    endBookValue: endBook,
    priorGross: priorGross != null ? priorGross : priorBook,
    priorImpairment: raw?.priorImpairment ?? raw?.上年减值准备 ?? 0,
    priorBookValue: priorBook,
    isAutoFilled: !!raw?.isAutoFilled,
    remark: raw?.remark ?? '',
  })
}

export function summarizeI5Disclosure(rows: I5DisclosureRow[]): I5DisclosureTotals {
  const t: I5DisclosureTotals = {
    endGross: 0,
    endImpairment: 0,
    endBookValue: 0,
    priorGross: 0,
    priorImpairment: 0,
    priorBookValue: 0,
  }
  for (const r of rows) {
    t.endGross += _num(r.endGross)
    t.endImpairment += _num(r.endImpairment)
    t.endBookValue += _num(r.endBookValue)
    t.priorGross += _num(r.priorGross)
    t.priorImpairment += _num(r.priorImpairment)
    t.priorBookValue += _num(r.priorBookValue)
  }
  t.endGross = _round2(t.endGross)
  t.endImpairment = _round2(t.endImpairment)
  t.endBookValue = _round2(t.endBookValue)
  t.priorGross = _round2(t.priorGross)
  t.priorImpairment = _round2(t.priorImpairment)
  t.priorBookValue = _round2(t.priorBookValue)
  return t
}

const _KNOWN = new Set<string>(I5_DEFAULT_DISCLOSURE_CATEGORIES)

/** 从 I5-2 明细行解析披露分类标签 */
export function resolveI5DisclosureLabel(detail: any): string {
  const category = String(detail?.category ?? detail?.assetType ?? '').trim()
  const name = String(detail?.name ?? detail?.projectName ?? detail?.item ?? '').trim()
  if (_KNOWN.has(name)) return name
  if (_KNOWN.has(category)) return category
  for (const label of I5_DEFAULT_DISCLOSURE_CATEGORIES) {
    if (name.includes(label) || label.includes(name)) return label
    if (category && (category.includes(label) || label.includes(category))) return label
  }
  // 常见别名
  if (/土地出让/.test(name + category)) return '预付土地出让金'
  if (/工程款/.test(name + category)) return '预付工程款'
  if (/房屋|设备款/.test(name + category)) return '预付房屋、设备款'
  if (/无形.*预付|预付.*无形/.test(name + category)) return '无形资产预付款'
  if (/投资款/.test(name + category)) return '预付投资款'
  if (/委托贷款/.test(name + category)) return '委托贷款'
  if (/合同资产/.test(name + category)) return '合同资产'
  if (/合同取得/.test(name + category)) return '合同取得成本'
  if (/合同履约/.test(name + category)) return '合同履约成本'
  if (/退货成本/.test(name + category)) return '应收退货成本'
  if (/长期资产购置/.test(name + category)) return '预付房屋、设备款'
  return name || category || '其他'
}

/**
 * 按披露分类聚合 I5-2（期末账面/减值/净值；期初≈上年年末）
 */
export function aggregateI5DetailForDisclosure(detailRows: any[]): I5DisclosureRow[] {
  const map = new Map<string, I5DisclosureRow>()

  for (const d of detailRows || []) {
    const label = resolveI5DisclosureLabel(d)
    if (!label || label === '合计') continue

    const endGross = _num(d.endBalance ?? d.auditedEnding ?? d.endingBalance ?? d.originalAmount)
    const net = d.netValue != null ? _num(d.netValue) : endGross
    const endImpairment = _round2(Math.max(0, endGross - net))
    const begin = _num(d.beginBalance ?? d.auditedOpening ?? d.openingBalance ?? d.priorBalance)

    const cur = map.get(label) || emptyI5DisclosureRow({ item: label, isAutoFilled: true })
    cur.endGross = _round2(cur.endGross + endGross)
    cur.endImpairment = _round2(cur.endImpairment + endImpairment)
    cur.priorGross = _round2(cur.priorGross + begin)
    // 明细无上年减值时，期初按净值口径（减值 0）
    cur.priorImpairment = _round2(cur.priorImpairment + 0)
    cur.endBookValue = calcI5EndBookValue(cur)
    cur.priorBookValue = calcI5PriorBookValue(cur)
    cur.isAutoFilled = true
    map.set(label, cur)
  }

  if (!map.size) return defaultI5DisclosureRows()

  const order = new Map(I5_DEFAULT_DISCLOSURE_CATEGORIES.map((c, i) => [c, i]))
  return [...map.values()].sort((a, b) => {
    const ia = order.has(a.item) ? order.get(a.item)! : 999
    const ib = order.has(b.item) ? order.get(b.item)! : 999
    if (ia !== ib) return ia - ib
    return a.item.localeCompare(b.item, 'zh')
  })
}

export function defaultI5DisclosureRows(): I5DisclosureRow[] {
  return I5_DEFAULT_DISCLOSURE_CATEGORIES.map((item) =>
    emptyI5DisclosureRow({ item, isAutoFilled: false }),
  )
}

export function mergeAutoFillPreserveManual(
  existing: I5DisclosureRow[],
  autoRows: I5DisclosureRow[],
): I5DisclosureRow[] {
  if (!existing.length) return autoRows
  const manualByItem = new Map(
    existing.filter((r) => !r.isAutoFilled && r.item).map((r) => [r.item, r]),
  )
  const merged: I5DisclosureRow[] = []
  const used = new Set<string>()

  for (const auto of autoRows) {
    const man = manualByItem.get(auto.item)
    if (man) {
      merged.push({
        ...man,
        endBookValue: calcI5EndBookValue(man),
        priorBookValue: calcI5PriorBookValue(man),
      })
      used.add(auto.item)
    } else {
      merged.push(auto)
      used.add(auto.item)
    }
  }
  for (const r of existing) {
    if (r.item && !used.has(r.item)) {
      merged.push({
        ...r,
        endBookValue: calcI5EndBookValue(r),
        priorBookValue: calcI5PriorBookValue(r),
      })
    }
  }
  return merged.length ? merged : autoRows
}
