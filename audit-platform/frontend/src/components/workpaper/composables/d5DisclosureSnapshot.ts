/**
 * D5 应收款项融资披露表快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `D5TabDisclosure.syncToDisclosureNotes` 原先在组件里内联拼快照；抽成本模块的纯函数后 Tab 与离屏 provider
 * 调同一份计算 → 两条路径发出逐字节相同的载荷。已质押 / 已背书两张表在 Tab 里是组件状态（不在 composable），
 * 这里同时提供默认行与持久化行解析（Tab 的 watcher 与 provider 都用它）。
 */
import type { DisclosureSection, ImpairmentRow } from './useD5Disclosure'
import type { D5DisclosureSnapshot, D5DisclosureVariant } from './d5NoteSectionMap'
import type { ChecklistResponse } from './useD5FormData'

export interface D5PledgedRow { key: string; label: string; pledgedAmount: number }
export interface D5EndorsedRow { key: string; label: string; derecognizedAmount: number; notDerecognizedAmount: number }

/** 已质押 / 已背书两张表的持久化条目 */
export const D5_PLEDGED_ITEM = 'D5-note-listed-pledged'
export const D5_ENDORSED_ITEM = 'D5-note-listed-endorsed'

export function defaultD5PledgedRows(): D5PledgedRow[] {
  return [
    { key: 'bank', label: '银行承兑票据', pledgedAmount: 0 },
    { key: 'commercial', label: '商业承兑票据', pledgedAmount: 0 },
  ]
}

export function defaultD5EndorsedRows(): D5EndorsedRow[] {
  return [
    { key: 'bank', label: '银行承兑票据', derecognizedAmount: 0, notDerecognizedAmount: 0 },
    { key: 'commercial', label: '商业承兑票据', derecognizedAmount: 0, notDerecognizedAmount: 0 },
  ]
}

/** 持久化的行（JSON 数组）：解析成功且非空才采用，否则 null（沿用当前 / 默认行）。 */
export function parseD5NoteRows<T>(remark: string | null | undefined): T[] | null {
  if (!remark) return null
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) && parsed.length > 0 ? parsed as T[] : null
  } catch {
    return null
  }
}

export function readD5PledgedRows(responses: ReadonlyMap<string, ChecklistResponse>): D5PledgedRow[] {
  return parseD5NoteRows<D5PledgedRow>(responses.get(D5_PLEDGED_ITEM)?.remark) ?? defaultD5PledgedRows()
}

export function readD5EndorsedRows(responses: ReadonlyMap<string, ChecklistResponse>): D5EndorsedRow[] {
  return parseD5NoteRows<D5EndorsedRow>(responses.get(D5_ENDORSED_ITEM)?.remark) ?? defaultD5EndorsedRows()
}

export interface D5DisclosureSnapshotSource {
  listedSections: readonly DisclosureSection[]
  soeSections: readonly DisclosureSection[]
  impairmentRows: readonly ImpairmentRow[]
  pledgedRows: readonly D5PledgedRow[]
  endorsedRows: readonly D5EndorsedRow[]
  noteTexts: Record<string, string>
}

/** 披露表 → `buildD5SyncPayload` 的快照（上市：分类 / 减值汇总 / 已质押 / 已背书 + 3 段说明；国企：分类 + 合计 + 1 段说明）。 */
export function buildD5DisclosureSnapshot(
  variant: D5DisclosureVariant,
  src: D5DisclosureSnapshotSource,
): D5DisclosureSnapshot {
  if (variant === 'soe') {
    const sec = src.soeSections[0]
    return {
      mainRows: (sec?.rows ?? []).map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
      mainTotal: sec?.totalRow ? { label: '合计', endAmount: sec.totalRow.endAmount, priorAmount: sec.totalRow.priorAmount } : undefined,
      notes: { 'soe-1': src.noteTexts['soe-1'] || '' },
    }
  }
  const cls = src.listedSections.find((s) => s.sectionKey === 'listed-classification')
  const sum = <K extends 'priorEnd' | 'provision' | 'reversal' | 'writeOff' | 'endBalance'>(k: K) =>
    src.impairmentRows.reduce((s, r) => s + (Number(r[k]) || 0), 0)
  return {
    mainRows: (cls?.rows ?? []).map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
    impairment: {
      priorBalance: sum('priorEnd'),
      provision: sum('provision'),
      reversal: sum('reversal'),
      writeOff: sum('writeOff'),
      endBalance: sum('endBalance'),
    },
    pledgedRows: src.pledgedRows.map((r) => ({ label: r.label, pledgedAmount: r.pledgedAmount })),
    endorsedRows: src.endorsedRows.map((r) => ({ label: r.label, derecognizedAmount: r.derecognizedAmount, notDerecognizedAmount: r.notDerecognizedAmount })),
    notes: {
      'listed-1': src.noteTexts['listed-1'] || '',
      'listed-2': src.noteTexts['listed-2'] || '',
      'listed-3': src.noteTexts['listed-3'] || '',
    },
  }
}
