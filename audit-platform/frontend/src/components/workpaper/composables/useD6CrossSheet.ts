/**
 * useD6CrossSheet — D6 合同资产跨Sheet联动 computed 响应式链
 *
 * 所有跨sheet数据流通过 allResponses Map 的 computed 属性实现，不走API调用。
 * 核心联动链：D6-2→D6-1(原值聚合) / D6-3→D6-1(坏账聚合) / D6-8→D6-3(ECL参考)
 *            / D6-4→D6-1(AJE/RJE) / D6-1→附注 / D6-8→附注 / D6-3→附注
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 4.1
 * Requirements: 3.1, 3.2, 3.3, 3.4, 15.2, 15.3, 15.4, 16.2, 16.3, 27.1, 27.2, 27.3
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcBlockTotal,
  calcNetValue,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD6CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

export interface BlockTotals {
  block1: { subtotal: number; deduction: number; total: number }
  block2: { subtotal: number; deduction: number; total: number }
  block3: { subtotal: number; deduction: number; total: number }
}

export interface NetValueRow {
  rowKey: string
  prior: number
  current: number
}

export interface EclReferenceValues {
  single: number
  groups: Record<string, number>
  total: number
}

export interface DisclosureSourceData {
  block1Rows: Array<{ label: string; prior: number; current: number }>
  block2Rows: Array<{ label: string; prior: number; current: number }>
  block3Rows: Array<{ label: string; prior: number; current: number }>
  blockTotals: BlockTotals
}

export interface EclDisclosureData {
  singleRows: Array<{ name: string; balance: number; provision: number; lossRate: number; basis: string }>
  agingGroups: Array<{ groupName: string; rows: Array<{ aging: string; balance: number; provision: number; lossRate: number }> }>
  totalProvision: number
}

export interface ImpairmentChangeData {
  rows: Array<{ item: string; provision: number; reversal: number; writeOff: number; otherIncrease: number; otherDecrease: number }>
  totals: { provision: number; reversal: number; writeOff: number; otherIncrease: number; otherDecrease: number }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 安全解析 JSON 数组（从 remark 字段），失败返回空数组 */
function safeParseJsonArray(remark: string | null | undefined): any[] {
  if (!remark) return []
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从 allResponses 中获取指定 item_id 的 remark */
function getRemark(map: Map<string, ChecklistResponse>, itemId: string): string | null {
  return map.get(itemId)?.remark ?? null
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6CrossSheet(options: UseD6CrossSheetOptions) {
  const { allResponses } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  // ─── D6-2 → D6-1 按分类聚合原值 ────────────────────────────────────────

  const originalValueAggregation: ComputedRef<Record<string, { prior: number; current: number }>> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D6-2-rows'))
    const result: Record<string, { prior: number; current: number }> = {}

    for (const row of rows) {
      const type = row.contractType || '其他'
      if (!result[type]) {
        result[type] = { prior: 0, current: 0 }
      }
      result[type].prior += parseNum(row.priorAudited)
      result[type].current += parseNum(row.endAudited)
    }

    return result
  })

  // ─── D6-3 → D6-1 按分类聚合坏账准备 ───────────────────────────────────

  const impairmentAggregation: ComputedRef<Record<string, { prior: number; current: number }>> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D6-3-rows'))
    const result: Record<string, { prior: number; current: number }> = {}

    for (const row of rows) {
      const category = row.category || 'single'
      if (!result[category]) {
        result[category] = { prior: 0, current: 0 }
      }
      result[category].prior += parseNum(row.priorAudited)
      result[category].current += parseNum(row.endAudited)
    }

    return result
  })

  // ─── D6-1 三区块小计（原值/坏账/净值）───────────────────────────────────

  const blockTotals: ComputedRef<BlockTotals> = computed(() => {
    const map = allResponses.value

    // Block1: 原值
    const b1Categories = Object.values(originalValueAggregation.value)
    const b1Subtotal = calcSubtotal(b1Categories.map(c => c.current))
    const b1Deduction = parseNum(map.get('D6-1-adj-block1-deduction-currentAudited')?.remark)
    const b1Total = calcBlockTotal(b1Subtotal, b1Deduction)

    // Block2: 坏账准备
    const b2Categories = Object.values(impairmentAggregation.value)
    const b2Subtotal = calcSubtotal(b2Categories.map(c => c.current))
    const b2Deduction = parseNum(map.get('D6-1-adj-block2-deduction-currentAudited')?.remark)
    const b2Total = calcBlockTotal(b2Subtotal, b2Deduction)

    // Block3: 净值 = 原值 - 坏账
    const b3Subtotal = calcNetValue(b1Subtotal, b2Subtotal)
    const b3Deduction = calcNetValue(b1Deduction, b2Deduction)
    const b3Total = calcNetValue(b1Total, b2Total)

    return {
      block1: { subtotal: b1Subtotal, deduction: b1Deduction, total: b1Total },
      block2: { subtotal: b2Subtotal, deduction: b2Deduction, total: b2Total },
      block3: { subtotal: b3Subtotal, deduction: b3Deduction, total: b3Total },
    }
  })

  // ─── 净值=原值-坏账（逐行+小计+非流动+合计）─────────────────────────────

  const netValueRows: ComputedRef<NetValueRow[]> = computed(() => {
    const origAgg = originalValueAggregation.value
    const impAgg = impairmentAggregation.value
    const result: NetValueRow[] = []

    // 动态行：按合同类型对齐
    const allKeys = new Set([...Object.keys(origAgg), ...Object.keys(impAgg)])
    for (const key of allKeys) {
      const origPrior = origAgg[key]?.prior ?? 0
      const origCurrent = origAgg[key]?.current ?? 0
      const impPrior = impAgg[key]?.prior ?? 0
      const impCurrent = impAgg[key]?.current ?? 0
      result.push({
        rowKey: key,
        prior: calcNetValue(origPrior, impPrior),
        current: calcNetValue(origCurrent, impCurrent),
      })
    }

    // 小计行
    const totals = blockTotals.value
    result.push({
      rowKey: 'subtotal',
      prior: calcNetValue(
        calcSubtotal(Object.values(origAgg).map(c => c.prior)),
        calcSubtotal(Object.values(impAgg).map(c => c.prior)),
      ),
      current: totals.block3.subtotal,
    })

    // 非流动扣减行
    const map = allResponses.value
    const b1DedPrior = parseNum(map.get('D6-1-adj-block1-deduction-priorAudited')?.remark)
    const b2DedPrior = parseNum(map.get('D6-1-adj-block2-deduction-priorAudited')?.remark)
    const b1DedCurrent = parseNum(map.get('D6-1-adj-block1-deduction-currentAudited')?.remark)
    const b2DedCurrent = parseNum(map.get('D6-1-adj-block2-deduction-currentAudited')?.remark)
    result.push({
      rowKey: 'deduction',
      prior: calcNetValue(b1DedPrior, b2DedPrior),
      current: calcNetValue(b1DedCurrent, b2DedCurrent),
    })

    // 合计行
    result.push({
      rowKey: 'total',
      prior: calcNetValue(
        calcBlockTotal(
          calcSubtotal(Object.values(origAgg).map(c => c.prior)),
          b1DedPrior,
        ),
        calcBlockTotal(
          calcSubtotal(Object.values(impAgg).map(c => c.prior)),
          b2DedPrior,
        ),
      ),
      current: totals.block3.total,
    })

    return result
  })

  // ─── D6-8 → D6-3 ECL应计提参考值 ──────────────────────────────────────

  const eclReferenceValues: ComputedRef<EclReferenceValues> = computed(() => {
    const map = allResponses.value
    const singleRows = safeParseJsonArray(getRemark(map, 'D6-8-single-rows'))
    const groupsData = safeParseJsonArray(getRemark(map, 'D6-8-groups'))

    // 单项合计
    const singleTotal = calcSubtotal(singleRows.map((r: any) => parseNum(r.expectedProvision)))

    // 各组合小计
    const groups: Record<string, number> = {}
    for (const group of groupsData) {
      const groupName = group.groupName || group.groupId || 'default'
      const groupRows: any[] = Array.isArray(group.rows) ? group.rows : []
      groups[groupName] = calcSubtotal(groupRows.map((r: any) => parseNum(r.expectedProvision)))
    }

    // 总计
    const groupsTotal = calcSubtotal(Object.values(groups))
    const total = singleTotal + groupsTotal

    return { single: singleTotal, groups, total }
  })

  // ─── D6-4 → D6-1 AJE/RJE ─────────────────────────────────────────────

  const adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D6-4-rows'))

    const ajeTotal = calcSubtotal(rows.map((r: any) => parseNum(r.debitAmount)))
    const rjeTotal = calcSubtotal(rows.map((r: any) => parseNum(r.creditAmount)))

    return { ajeTotal, rjeTotal }
  })

  // ─── 三区块交叉验证 ───────────────────────────────────────────────────

  const netValueValidation: ComputedRef<{ isValid: boolean; diff: number }> = computed(() => {
    const totals = blockTotals.value
    const diff = totals.block3.total - (totals.block1.total - totals.block2.total)
    const isValid = Math.abs(diff) <= 0.01
    return { isValid, diff }
  })

  // ─── D6-1 → 附注 ─────────────────────────────────────────────────────

  const adjudicationForDisclosure: ComputedRef<DisclosureSourceData> = computed(() => {
    const origAgg = originalValueAggregation.value
    const impAgg = impairmentAggregation.value
    const totals = blockTotals.value
    const map = allResponses.value

    const block1Rows = Object.entries(origAgg).map(([label, vals]) => ({
      label,
      prior: vals.prior,
      current: vals.current,
    }))

    const block2Rows = Object.entries(impAgg).map(([label, vals]) => ({
      label,
      prior: vals.prior,
      current: vals.current,
    }))

    // 净值行 = 原值 - 坏账
    const allKeys = new Set([...Object.keys(origAgg), ...Object.keys(impAgg)])
    const block3Rows = Array.from(allKeys).map(key => ({
      label: key,
      prior: calcNetValue(origAgg[key]?.prior ?? 0, impAgg[key]?.prior ?? 0),
      current: calcNetValue(origAgg[key]?.current ?? 0, impAgg[key]?.current ?? 0),
    }))

    return { block1Rows, block2Rows, block3Rows, blockTotals: totals }
  })

  // ─── D6-8 → 附注 ─────────────────────────────────────────────────────

  const eclForDisclosure: ComputedRef<EclDisclosureData> = computed(() => {
    const map = allResponses.value
    const singleRows = safeParseJsonArray(getRemark(map, 'D6-8-single-rows'))
    const groupsData = safeParseJsonArray(getRemark(map, 'D6-8-groups'))

    const mappedSingle = singleRows.map((r: any) => ({
      name: r.debtorName || '',
      balance: parseNum(r.auditedBalance),
      provision: parseNum(r.expectedProvision),
      lossRate: parseNum(r.lossRate),
      basis: r.basis || '',
    }))

    const mappedGroups = groupsData.map((g: any) => ({
      groupName: g.groupName || g.groupId || '',
      rows: (Array.isArray(g.rows) ? g.rows : []).map((r: any) => ({
        aging: r.agingBand || r.aging || '',
        balance: parseNum(r.auditedBalance),
        provision: parseNum(r.expectedProvision),
        lossRate: parseNum(r.lossRate),
      })),
    }))

    const totalProvision = eclReferenceValues.value.total

    return { singleRows: mappedSingle, agingGroups: mappedGroups, totalProvision }
  })

  // ─── D6-3 → 附注（计提/转回/核销变动）─────────────────────────────────

  const impairmentChangesForDisclosure: ComputedRef<ImpairmentChangeData> = computed(() => {
    const rows = safeParseJsonArray(getRemark(allResponses.value, 'D6-3-rows'))

    const mapped = rows.map((r: any) => ({
      item: r.itemName || '',
      provision: parseNum(r.provision),
      reversal: parseNum(r.reversal),
      writeOff: parseNum(r.writeOff),
      otherIncrease: parseNum(r.otherIncrease),
      otherDecrease: parseNum(r.otherDecrease),
    }))

    const totals = {
      provision: calcSubtotal(mapped.map(r => r.provision)),
      reversal: calcSubtotal(mapped.map(r => r.reversal)),
      writeOff: calcSubtotal(mapped.map(r => r.writeOff)),
      otherIncrease: calcSubtotal(mapped.map(r => r.otherIncrease)),
      otherDecrease: calcSubtotal(mapped.map(r => r.otherDecrease)),
    }

    return { rows: mapped, totals }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    originalValueAggregation,
    impairmentAggregation,
    blockTotals,
    netValueRows,
    eclReferenceValues,
    adjustmentTotals,
    netValueValidation,
    adjudicationForDisclosure,
    eclForDisclosure,
    impairmentChangesForDisclosure,
    crossSheetStatus,
  }
}

export default useD6CrossSheet
