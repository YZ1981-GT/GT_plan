/**
 * D6 合同资产披露表快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `D6TabDisclosure.syncToDisclosureNotes` 原先在组件里内联拼快照；抽成本模块的纯函数后 Tab 与离屏 provider
 * 调同一份计算 → 两条路径发出逐字节相同的载荷。
 */
import type { DisclosureRow, DisclosureSection, GroupedDetail } from './useD6Disclosure'
import type { D6DisclosureSnapshot, D6DisclosureVariant } from './d6NoteSectionMap'

export interface D6DisclosureSnapshotSource {
  listedSections: readonly DisclosureSection[]
  soeSections: readonly DisclosureSection[]
  majorChangeRows: readonly DisclosureRow[]
  mainFormat: 'detailed' | 'simple'
  impairmentPriorRows: readonly DisclosureRow[]
  singlePriorRows: readonly DisclosureRow[]
  groupedDetails: readonly GroupedDetail[]
  noteTexts: Record<string, string>
}

/** 按子节键取子节；没有时回空子节（Tab 的简化式主表行与快照共用） */
export function findD6Section(sections: readonly any[], key: string): any {
  return (sections || []).find((s) => s.sectionKey === key) || { rows: [] }
}

/** 披露表 → `buildD6SyncPayload` 的快照（上市：分类 / 计提情况两期 / 单项两期 / 逐组组合 / 变动；国企：情况 / 减值 / 重大变动）。 */
export function buildD6DisclosureSnapshot(
  variant: D6DisclosureVariant,
  src: D6DisclosureSnapshotSource,
): D6DisclosureSnapshot {
  const majorChangeRows = src.majorChangeRows.map((r: any) => ({ label: r.label, amount: r.amount, reason: r.reason }))
  if (variant === 'soe') {
    const cls = findD6Section(src.soeSections, 'soe-1')
    const imp = findD6Section(src.soeSections, 'soe-2')
    return {
      classRows: (cls.rows ?? []).map((r: any) => ({
        label: r.label,
        endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
        priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
      })),
      soeImpairmentRows: (imp.rows ?? []).map((r: any) => ({
        label: r.label, priorBalance: r.priorBalance, provision: r.provision,
        reversal: r.reversal, writeOff: r.writeOff, endBalance: r.endBalance, reason: r.reason,
      })),
      majorChangeRows,
      notes: { ...src.noteTexts },
    }
  }
  const cls = findD6Section(src.listedSections, 'listed-1')
  const prov = findD6Section(src.listedSections, 'listed-2')
  const single = findD6Section(src.listedSections, 'listed-3')
  const change = findD6Section(src.listedSections, 'listed-5')
  return {
    classRows: (cls.rows ?? []).map((r: any) => ({
      label: r.label,
      endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
      priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
    })),
    mainFormat: src.mainFormat,
    majorChangeRows,
    // 🔴 字段名必须与 `D6ImpairmentProvisionRowLike` 一致（旧代码写的是
    // endBalance/endPercentage/endAmount/endLossRate → 载荷侧读不到，静默推 0）
    impairmentProvisionRows: (prov.rows ?? []).map((r: any) => ({
      label: r.label,
      balance: r.endBalance,
      ratio: r.endPercentage,
      provision: r.endAmount,
      lossRate: r.endLossRate,
    })),
    impairmentProvisionPriorRows: src.impairmentPriorRows.map((r: any) => ({
      label: r.label, balance: r.balance, ratio: r.ratio,
      provision: r.provision, lossRate: r.lossRate,
    })),
    singleItems: (single.rows ?? []).map((r: any) => ({
      label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate, reason: r.reason,
    })),
    singleItemsPrior: src.singlePriorRows.map((r: any) => ({
      label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate, reason: r.reason,
    })),
    groups: src.groupedDetails.map((g: any) => ({
      groupName: g.groupName,
      rows: (g.rows ?? []).map((r: any) => ({
        label: r.label,
        balance: r.balance, provision: r.provision, lossRate: r.lossRate,
        priorBalance: r.priorBalance, priorProvision: r.priorProvision, priorLossRate: r.priorLossRate,
      })),
    })),
    changeRows: (change.rows ?? []).map((r: any) => ({
      label: r.label, provision: r.provision, reversal: r.reversal, writeOff: r.writeOff, reason: r.reason,
    })),
    notes: { ...src.noteTexts },
  }
}
