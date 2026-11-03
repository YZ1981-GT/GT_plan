/**
 * D3 预收账款披露表快照（底稿两版披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `D3TabDisclosureListed / D3TabDisclosureSoe.syncToDisclosureNotes` 原先在组件里内联拼快照；抽成本模块的纯函数后
 * Tab 与离屏 provider 调同一份计算 → 两条路径发出逐字节相同的载荷。
 */
import type { DisclosureRow } from './useD3DisclosureListed'
import type { SoeDisclosureRow } from './useD3DisclosureSoe'
import type { D3DisclosureSnapshot } from './d3NoteSectionMap'

export interface D3ListedSnapshotSource {
  section1Rows: readonly DisclosureRow[]
  section1Subtotal: DisclosureRow
  section2Rows: readonly DisclosureRow[]
  section2Subtotal: DisclosureRow
  section3Rows: readonly DisclosureRow[]
  notes: { nature: string; longTerm: string; change: string }
}

/** 上市版（五、38：按性质 / 超 1 年 / 重大变动 + 3 段说明） */
export function buildD3ListedSnapshot(src: D3ListedSnapshotSource): D3DisclosureSnapshot {
  return {
    mainRows: src.section1Rows.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
    mainTotal: { label: '合计', endAmount: src.section1Subtotal.endAmount, priorAmount: src.section1Subtotal.priorAmount },
    longTermRows: src.section2Rows.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount, reason: r.reason })),
    longTermTotal: { label: '合计', endAmount: src.section2Subtotal.endAmount, priorAmount: src.section2Subtotal.priorAmount },
    changeRows: src.section3Rows.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount, reason: r.reason })),
    notes: { nature: src.notes.nature, longTerm: src.notes.longTerm, change: src.notes.change },
  }
}

export interface D3SoeSnapshotSource {
  section1Rows: readonly SoeDisclosureRow[]
  section1Subtotal: SoeDisclosureRow
  section2Rows: readonly SoeDisclosureRow[]
  section2Subtotal: SoeDisclosureRow
}

/** 国企版（八、38：按账龄两桶（带 rowKey 供同步层映射附注口径）/ 超 1 年；无说明段） */
export function buildD3SoeSnapshot(src: D3SoeSnapshotSource): D3DisclosureSnapshot {
  return {
    mainRows: src.section1Rows.map((r) => ({ rowKey: r.rowKey, label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
    mainTotal: { label: '合计', endAmount: src.section1Subtotal.endAmount, priorAmount: src.section1Subtotal.priorAmount },
    longTermRows: src.section2Rows.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount, reason: r.reason })),
    longTermTotal: { label: '合计', endAmount: src.section2Subtotal.endAmount, priorAmount: src.section2Subtotal.priorAmount },
    notes: {},
  }
}
