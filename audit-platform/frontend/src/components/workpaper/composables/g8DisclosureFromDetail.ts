/**
 * G8 附注 ← G8-2 / G8-5 带入
 * 对齐模板槽位：余额 3 行；上市 OCI 3 行；国企明细 4 行；溢出汇总到「其他」
 */
import { parseNum } from './useG8FormulaEngine'
import { G8_DETAIL_KEY, G8_DESIGNATION_KEY } from './g8CrossHelpers'
import {
  G8_LISTED_BALANCE_SLOTS,
  G8_LISTED_OCI_SLOTS,
  G8_SOE_BALANCE_SLOTS,
  G8_SOE_DETAIL_SLOTS,
  type G8DisclosureStoreV2,
  createEmptyListedStore,
  createEmptySoeStore,
} from './g8SchemaRows'
import type { ChecklistResponse } from './useF1FormData'
import type { G8DetailRow } from './useG8Detail'

export interface G8DiscSourceRow {
  investeeName: string
  openingAdjusted: number
  closingAdjusted: number
  designationReason: string
  ociCurrentChange: number
  ociCumulativeChange: number
  ociToRetainedEarnings: number
  transferReason: string
}

export interface G8DiscPullResult {
  store: G8DisclosureStoreV2
  sourceCount: number
  overflowCount: number
  /** G8-2 无对应字段，无法自动带入 */
  missingFields: string[]
  designationFilled: boolean
}

function parseDetailRows(m: Map<string, ChecklistResponse>): G8DiscSourceRow[] {
  const raw = m.get(G8_DETAIL_KEY)?.remark
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    return arr
      .map((r: Partial<G8DetailRow>) => ({
        investeeName: String(r.investeeName ?? '').trim(),
        openingAdjusted: parseNum(r.openingAdjusted ?? r.openingBalance),
        closingAdjusted: parseNum(r.closingAdjusted ?? r.closingBalance ?? r.fairValueTotal),
        designationReason: String(r.designationReason ?? '').trim(),
        ociCurrentChange: parseNum(r.ociCurrentChange),
        ociCumulativeChange: parseNum(r.ociCumulativeChange),
        ociToRetainedEarnings: parseNum(r.ociToRetainedEarnings),
        transferReason: String(r.transferReason ?? '').trim(),
      }))
      .filter((r) =>
        r.investeeName
        || Math.abs(r.closingAdjusted) > 0.01
        || Math.abs(r.openingAdjusted) > 0.01
        || Math.abs(r.ociCurrentChange) > 0.01,
      )
  } catch {
    return []
  }
}

function parseDesignationReasons(m: Map<string, ChecklistResponse>): Array<{ name: string; reason: string }> {
  const raw = m.get(G8_DESIGNATION_KEY)?.remark
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    // 旧问卷格式跳过
    if (arr[0]?.checkItem && arr[0]?.sectionNo) return []
    return arr
      .map((r: { investeeName?: string; designationReason?: string }) => ({
        name: String(r.investeeName ?? '').trim(),
        reason: String(r.designationReason ?? '').trim(),
      }))
      .filter((r) => r.name && r.reason)
  } catch {
    return []
  }
}

/**
 * 将明细压入固定槽位：前 slots-1 项保留，其余汇总为「其他」（仅 1 项时全量填入）。
 * 按 |期末| 降序，保证重要项目优先展示。
 */
export function packDisclosureSlots<T extends { label: string }>(
  items: T[],
  slots: number,
  sumFields: (keyof T)[],
): { packed: T[]; overflowCount: number } {
  if (slots <= 0) return { packed: [], overflowCount: 0 }
  if (items.length <= slots) {
    const packed = [...items]
    while (packed.length < slots) {
      packed.push({ label: '' } as T)
    }
    return { packed: packed.slice(0, slots), overflowCount: 0 }
  }
  if (slots === 1) {
    const first = { ...items[0] }
    for (const f of sumFields) {
      const total = items.reduce((s, it) => s + (Number(it[f]) || 0), 0)
      ;(first as any)[f] = total
    }
    first.label = items.length === 1 ? items[0].label : '其他'
    return { packed: [first], overflowCount: Math.max(0, items.length - 1) }
  }
  const head = items.slice(0, slots - 1).map((it) => ({ ...it }))
  const rest = items.slice(slots - 1)
  const other = { ...rest[0], label: '其他' } as T
  for (const f of sumFields) {
    ;(other as any)[f] = rest.reduce((s, it) => s + (Number(it[f]) || 0), 0)
  }
  return { packed: [...head, other], overflowCount: rest.length }
}

export function buildG8DesignationNarrative(
  sources: G8DiscSourceRow[],
  designationExtras: Array<{ name: string; reason: string }> = [],
): string {
  const byName = new Map<string, string>()
  for (const d of designationExtras) {
    if (d.name && d.reason) byName.set(d.name, d.reason)
  }
  for (const s of sources) {
    if (s.investeeName && s.designationReason && !byName.has(s.investeeName)) {
      byName.set(s.investeeName, s.designationReason)
    }
  }
  if (!byName.size) {
    // 仅有名称时给模板句
    const names = sources.map((s) => s.investeeName).filter(Boolean)
    if (!names.length) return ''
    return names
      .map((n) =>
        `由于${n}是本公司出于战略目的而计划长期持有的投资，因此本公司将其指定为以公允价值计量且其变动计入其他综合收益的金融资产。`,
      )
      .join('\n')
  }
  return [...byName.entries()]
    .map(([name, reason]) => {
      const r = reason.trim()
      if (/指定|战略|长期持有|其他综合收益/.test(r)) return r.endsWith('。') || r.endsWith('.') ? r : `${r}。`
      return `由于${name}是本公司出于战略目的而计划长期持有的投资（${r}），因此本公司将其指定为以公允价值计量且其变动计入其他综合收益的金融资产。`
    })
    .join('\n')
}

function sortByClosingDesc(rows: G8DiscSourceRow[]): G8DiscSourceRow[] {
  return [...rows].sort((a, b) => Math.abs(b.closingAdjusted) - Math.abs(a.closingAdjusted))
}

/** 从 G8-2（及可选 G8-5）生成完整附注 v2 store */
export function pullG8DisclosureFromDetail(
  m: Map<string, ChecklistResponse>,
  variant: 'listed' | 'soe',
  opts?: { fillDesignation?: boolean },
): G8DiscPullResult {
  const fillDesignation = opts?.fillDesignation !== false
  const sources = sortByClosingDesc(parseDetailRows(m))
  const desigExtra = parseDesignationReasons(m)
  const missingFields = ['dividend'] // G8-2 无股利收入列
  const base = variant === 'listed' ? createEmptyListedStore() : createEmptySoeStore()

  if (!sources.length) {
    return {
      store: base,
      sourceCount: 0,
      overflowCount: 0,
      missingFields,
      designationFilled: false,
    }
  }

  const balSlots = variant === 'listed' ? G8_LISTED_BALANCE_SLOTS : G8_SOE_BALANCE_SLOTS
  const balItems = sources.map((s) => ({
    label: s.investeeName,
    closing: s.closingAdjusted,
    prior: s.openingAdjusted,
  }))
  const { packed: balPacked, overflowCount: balOverflow } = packDisclosureSlots(
    balItems,
    balSlots,
    ['closing', 'prior'],
  )
  base.balanceRows = balPacked.map((r) => ({
    label: r.label || '',
    closing: Number(r.closing) || 0,
    prior: Number(r.prior) || 0,
  }))

  let designationFilled = false
  if (fillDesignation) {
    const text = buildG8DesignationNarrative(sources, desigExtra)
    if (text) {
      base.designationText = text
      designationFilled = true
    }
  }

  if (variant === 'listed') {
    const ociItems = sources.map((s) => ({
      label: s.investeeName,
      ociPeriod: s.ociCurrentChange,
      ociCumulative: s.ociCumulativeChange,
      dividend: 0,
      transferToRE: s.ociToRetainedEarnings,
      derecogReason: s.transferReason,
    }))
    const { packed: ociPacked, overflowCount: ociOverflow } = packDisclosureSlots(
      ociItems,
      G8_LISTED_OCI_SLOTS,
      ['ociPeriod', 'ociCumulative', 'dividend', 'transferToRE'],
    )
    base.ociRows = ociPacked.map((r) => ({
      label: r.label || '',
      ociPeriod: Number(r.ociPeriod) || 0,
      ociCumulative: Number(r.ociCumulative) || 0,
      dividend: Number(r.dividend) || 0,
      transferToRE: Number(r.transferToRE) || 0,
      derecogReason: String(r.derecogReason || ''),
    }))
    return {
      store: base,
      sourceCount: sources.length,
      overflowCount: Math.max(balOverflow, ociOverflow),
      missingFields,
      designationFilled,
    }
  }

  const detailItems = sources.map((s) => ({
    label: s.investeeName,
    dividend: 0,
    ociPeriod: s.ociCurrentChange,
    ociCumulative: s.ociCumulativeChange,
    transferAmt: s.ociToRetainedEarnings,
    transferReason: s.transferReason,
  }))
  const { packed: detPacked, overflowCount: detOverflow } = packDisclosureSlots(
    detailItems,
    G8_SOE_DETAIL_SLOTS,
    ['dividend', 'ociPeriod', 'ociCumulative', 'transferAmt'],
  )
  base.detailRows = detPacked.map((r) => ({
    label: r.label || '',
    dividend: Number(r.dividend) || 0,
    ociPeriod: Number(r.ociPeriod) || 0,
    ociCumulative: Number(r.ociCumulative) || 0,
    transferAmt: Number(r.transferAmt) || 0,
    transferReason: String(r.transferReason || ''),
  }))

  return {
    store: base,
    sourceCount: sources.length,
    overflowCount: Math.max(balOverflow, detOverflow),
    missingFields,
    designationFilled,
  }
}

/** 仅刷新指定原因文本（不覆盖金额表） */
export function buildG8DesignationFromResponses(
  m: Map<string, ChecklistResponse>,
): string {
  return buildG8DesignationNarrative(parseDetailRows(m), parseDesignationReasons(m))
}
