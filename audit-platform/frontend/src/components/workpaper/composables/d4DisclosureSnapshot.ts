/**
 * D4 营业收入 / 营业成本披露表快照（上市 / 国企两版披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 两版 Tab 原先各自内联一份完全相同的 `buildSnapshot()`，（6）剩余履约义务行也在组件里读；抽成本模块的纯函数后
 * 两个 Tab 与离屏 provider 调同一份计算 → 发出逐字节相同的载荷。入参 `d` = `useD4Disclosure` 的返回值。
 */
import type { DisclosureVariant, useD4Disclosure } from './useD4Disclosure'
import type { D4DisclosureSnapshot } from './d4NoteSectionMap'
import type { D4ObligationRow } from './d4DisclosureModel'
import { parseNum } from './useD4FormulaEngine'
import { D4_SEGMENT_ROWS, deriveSegmentCell } from './d4RevenueSegmentColumns'

export type D4DisclosureApi = ReturnType<typeof useD4Disclosure>

/** （6）剩余履约义务的持久化条目 */
export function d4Section6Key(variant: DisclosureVariant): string {
  return `D4-disc-${variant}-section6-rows`
}

/**
 * （6）剩余履约义务行 —— Tab 现行读法原样搬出（两条路径同口径）。
 *
 * 注意：`allResponses` 的值是回复对象，这里只认字符串 / 数组 ⇒ 持久化的行（写在 `conclusion`）读不回来，实际恒为空（已报告）。
 */
export function readD4Section6Rows(responses: ReadonlyMap<string, any> | undefined, variant: DisclosureVariant): D4ObligationRow[] {
  const raw = responses?.get(d4Section6Key(variant))
  if (raw && typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return [] }
  }
  if (Array.isArray(raw)) return raw
  return []
}

/** 披露表 → `buildD4SyncPayload` 的快照（两版同一形状；（8）试运行收入两版 Tab 都未带入快照，原样保持）。 */
export function buildD4DisclosureSnapshot(
  d: D4DisclosureApi,
  extra: { section6Rows: D4ObligationRow[]; auditYear: number | null },
): D4DisclosureSnapshot {
  return {
    revenueRows: d.section1Data.value.map((r: any) => ({
      label: r.category,
      currentRevenue: r.currentRevenue, currentCost: r.currentCost,
      priorRevenue: r.priorRevenue, priorCost: r.priorCost,
    })),
    revenueTotal: {
      label: d.section1Total.value.category,
      currentRevenue: d.section1Total.value.currentRevenue, currentCost: d.section1Total.value.currentCost,
      priorRevenue: d.section1Total.value.priorRevenue, priorCost: d.section1Total.value.priorCost,
    },
    industryRows: d.section2Rows.value.map((r: any) => ({
      label: r.category, currentRevenue: parseNum(r.currentAmount), currentCost: parseNum(r.priorAmount),
    })) as any,
    regionRows: d.section3Rows.value.map((r: any) => ({
      label: r.name, currentRevenue: parseNum(r.amount), currentCost: parseNum(r.proportion),
    })) as any,
    // Task 31: 行集与源模板逐行对齐（9 行，含两个派生小计 + 空可扩行 + 合计行）；
    // 🔴 不再产出 `total_revenue`/`total_cost` —— 源模板没有横向合计列。
    timingRows: D4_SEGMENT_ROWS.map((rowDef) => {
      const row: Record<string, string | number | boolean | null> = { label: rowDef.label }
      for (const cat of d.section4Categories.value) {
        row[`${cat.key}_revenue`] = deriveSegmentCell(
          d.section4Cells.value, cat.key, rowDef.key, 'revenue',
        )
        row[`${cat.key}_cost`] = deriveSegmentCell(
          d.section4Cells.value, cat.key, rowDef.key, 'cost',
        )
      }
      if (rowDef.kind === 'total' || rowDef.kind === 'subtotal') row.is_total = true
      return row
    }) as any,
    timingCategories: d.section4Categories.value.map((c: any) => ({ key: c.key, label: c.label })),
    // （6）剩余履约义务：原先没带 ⇒ 附注（6）表恒推空行、表头按 2025 派生成 2026年 / 2027年
    section6Rows: extra.section6Rows,
    auditYear: extra.auditYear,
    notes: { ...d.noteTexts.value },
  }
}
