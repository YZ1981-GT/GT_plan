/**
 * useL3Disclosure — L3 长期借款附注披露（上市/国企）共享逻辑 composable
 *
 * 对齐致同源模板「附注披露信息核对」结构（2026-07 复盘）：
 * - 分类表固定行（质押/抵押/保证/信用借款）+ 小计 + 减一年内到期 + 合计
 * - SUMIF 等价从 L3-2 明细按借款类型聚合：期末=Σ审定期末，上年年末/期初=Σ审定期初
 * - 利率区间列（每行手工文本）
 * - (1) 一年内到期的长期借款 子表（按类型：期末/期初）
 * - 财产抵押质押说明（文本）；国企版额外「资产负债表日后已偿还」「展期说明」
 *
 * 上市版第二计量列「上年年末余额」，国企版「期初余额」，数据同源（审定期初）。
 *
 * 科目：2501 长期借款（贷方/负债类）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface L3DisclosureRow {
  rowKey: string
  label: string
  isSubtotal: boolean
  isDeduction: boolean
  isTotal: boolean
  endAmount: number
  priorAmount: number
  /** 利率区间可编辑（仅分类行） */
  rateEditable: boolean
}

export interface L3CurrentPortionRow {
  rowKey: string
  label: string
  isTotal: boolean
  endAmount: number
  priorAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_DETAIL_ROWS = 'L3-L3-2-rows'

const CLASS_ROWS = [
  { rowKey: 'pledge', label: '质押借款' },
  { rowKey: 'mortgage', label: '抵押借款' },
  { rowKey: 'guarantee', label: '保证借款' },
  { rowKey: 'credit', label: '信用借款' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function loanTypeToRowKey(loanType: string): string {
  const s = loanType || ''
  if (s.includes('质押')) return 'pledge'
  if (s.includes('抵押')) return 'mortgage'
  if (s.includes('保证')) return 'guarantee'
  if (s.includes('信用')) return 'credit'
  return 'credit'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3Disclosure(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  variant: 'listed' | 'soe',
) {
  const PREFIX = `L3-disc-${variant}`

  function getStr(itemId: string): string {
    return allResponses.value.get(itemId)?.remark ?? ''
  }

  /** 从 L3-2 明细按借款类型聚合（期末审定[endBalance] + 期初审定[beginning] + 一年内到期[currentPortion]） */
  const aggByType = computed<Record<string, { end: number; prior: number; current: number }>>(() => {
    const raw = allResponses.value.get(ITEM_DETAIL_ROWS)?.remark
    const agg: Record<string, { end: number; prior: number; current: number }> = {}
    if (!raw) return agg
    let rows: any[] = []
    try {
      const p = JSON.parse(raw)
      rows = Array.isArray(p) ? p : []
    } catch {
      return agg
    }
    for (const r of rows) {
      const key = loanTypeToRowKey(r.loanType)
      if (!agg[key]) agg[key] = { end: 0, prior: 0, current: 0 }
      agg[key].end += (r.audited != null ? parseNum(r.audited) : parseNum(r.endBalance))
      agg[key].prior += parseNum(r.beginning)
      agg[key].current += parseNum(r.currentPortion)
    }
    return agg
  })

  /** 分类表（含小计/减一年内到期/合计） */
  const classificationRows: ComputedRef<L3DisclosureRow[]> = computed(() => {
    const agg = aggByType.value
    const classRows: L3DisclosureRow[] = CLASS_ROWS.map(def => ({
      rowKey: def.rowKey,
      label: def.label,
      isSubtotal: false,
      isDeduction: false,
      isTotal: false,
      endAmount: agg[def.rowKey]?.end ?? 0,
      priorAmount: agg[def.rowKey]?.prior ?? 0,
      rateEditable: true,
    }))

    const subEnd = classRows.reduce((s, r) => s + r.endAmount, 0)
    const subPrior = classRows.reduce((s, r) => s + r.priorAmount, 0)
    const curEnd = CLASS_ROWS.reduce((s, d) => s + (agg[d.rowKey]?.current ?? 0), 0)
    // 期初一年内到期：明细简化模型无期初一年内到期列，取手工值（缺省 0）
    const curPrior = parseNum(getStr(`${PREFIX}-deduct-prior`))

    return [
      ...classRows,
      { rowKey: '__subtotal__', label: '小计', isSubtotal: true, isDeduction: false, isTotal: false, endAmount: subEnd, priorAmount: subPrior, rateEditable: false },
      { rowKey: '__deduct__', label: '减：一年内到期的长期借款', isSubtotal: false, isDeduction: true, isTotal: false, endAmount: curEnd, priorAmount: curPrior, rateEditable: false },
      { rowKey: '__total__', label: '合计', isSubtotal: false, isDeduction: false, isTotal: true, endAmount: subEnd - curEnd, priorAmount: subPrior - curPrior, rateEditable: false },
    ]
  })

  /** (1) 一年内到期的长期借款 子表（按类型） */
  const currentPortionRows: ComputedRef<L3CurrentPortionRow[]> = computed(() => {
    const agg = aggByType.value
    const rows: L3CurrentPortionRow[] = CLASS_ROWS.map(def => ({
      rowKey: def.rowKey,
      label: def.label,
      isTotal: false,
      endAmount: agg[def.rowKey]?.current ?? 0,
      priorAmount: 0,
    }))
    const totEnd = rows.reduce((s, r) => s + r.endAmount, 0)
    rows.push({ rowKey: '__total__', label: '合计', isTotal: true, endAmount: totEnd, priorAmount: 0 })
    return rows
  })

  // ─── 利率区间（每行手工，期末/期初两列） ────────────────────────────────
  function rateRange(rowKey: string, period: 'end' | 'prior'): string {
    return getStr(`${PREFIX}-rate-${rowKey}-${period}`)
  }
  function updateRate(rowKey: string, period: 'end' | 'prior', value: string): void {
    debouncedSave(`${PREFIX}-rate-${rowKey}-${period}`, { remark: value })
  }

  // ─── 文本说明 ────────────────────────────────────────────────────────────
  const propertyNote = computed(() => getStr(`${PREFIX}-property-note`))
  const repaidNote = computed(() => getStr(`${PREFIX}-repaid-note`))
  const extensionNote = computed(() => getStr(`${PREFIX}-extension-note`))
  const conclusion = computed(() => getStr(`${PREFIX}-conclusion`))

  function updateNote(field: 'property-note' | 'repaid-note' | 'extension-note' | 'conclusion' | 'deduct-prior', value: string): void {
    debouncedSave(`${PREFIX}-${field}`, { remark: value })
  }

  return {
    classificationRows,
    currentPortionRows,
    rateRange,
    updateRate,
    propertyNote,
    repaidNote,
    extensionNote,
    conclusion,
    updateNote,
  }
}

export default useL3Disclosure
