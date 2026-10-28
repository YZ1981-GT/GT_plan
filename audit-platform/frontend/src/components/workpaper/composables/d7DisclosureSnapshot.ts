/**
 * D7 合同负债披露表快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `D7TabDisclosure.syncToDisclosureNotes` 原先在组件里内联拼快照；抽成本模块的纯函数后 Tab 与离屏 provider
 * 调同一份计算 → 两条路径发出逐字节相同的载荷。
 */
import type { DisclosureRow, DisclosureSection } from './useD7Disclosure'
import type { D7DisclosureSnapshot, D7DisclosureVariant, D7RowLike } from './d7NoteSectionMap'

export interface D7DisclosureSnapshotSource {
  listedSections: readonly DisclosureSection[]
  soeSections: readonly DisclosureSection[]
  noteTexts: Record<string, string>
}

function findSection(sections: readonly DisclosureSection[], key: string): DisclosureSection | undefined {
  return (sections || []).find((s) => s.sectionKey === key)
}

function toSnapRow(r: DisclosureRow): D7RowLike {
  return { label: r.label, current: r.current, prior: r.prior, reason: (r as any).reason }
}

const EMPTY_TOTAL = { label: '合计', current: 0, prior: 0 }

/** 披露表 → `buildD7SyncPayload` 的快照（上市：主表 / 超 1 年 / 重大变动；国企：主表 / 重大变动；各段说明）。 */
export function buildD7DisclosureSnapshot(
  variant: D7DisclosureVariant,
  src: D7DisclosureSnapshotSource,
): D7DisclosureSnapshot {
  if (variant === 'soe') {
    const main = findSection(src.soeSections, 'soe-1')
    const change = findSection(src.soeSections, 'soe-2')
    return {
      mainRows: (main?.rows ?? []).map(toSnapRow),
      mainTotal: main?.totalRow ? toSnapRow(main.totalRow) : { ...EMPTY_TOTAL },
      changeRows: (change?.rows ?? []).map(toSnapRow),
      notes: { ...src.noteTexts },
    }
  }
  const main = findSection(src.listedSections, 'listed-1')
  const longTerm = findSection(src.listedSections, 'listed-2')
  const change = findSection(src.listedSections, 'listed-3')
  return {
    mainRows: (main?.rows ?? []).map(toSnapRow),
    mainTotal: main?.totalRow ? toSnapRow(main.totalRow) : { ...EMPTY_TOTAL },
    longTermRows: (longTerm?.rows ?? []).map(toSnapRow),
    longTermTotal: longTerm?.totalRow ? toSnapRow(longTerm.totalRow) : { ...EMPTY_TOTAL },
    changeRows: (change?.rows ?? []).map(toSnapRow),
    notes: { ...src.noteTexts },
  }
}
