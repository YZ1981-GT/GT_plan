/**
 * useN1Detail — 明细表N1-2 逻辑层
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 动态行管理（新增/删除暂时性差异项目）
 * - 列结构：序号/暂时性差异项目/类别/暂时性差异(期初)/适用税率(期初)/递延税资产期初余额(=diff×rate)/
 *          AJE/RJE/审定/暂时性差异(期末)/适用税率(期末)/递延税资产期末余额/AJE/RJE/审定
 * - 公式：递延税资产 = ROUND(暂时性差异×税率, 2)
 * - 分类小计 + 全部合计
 * - 底部统计：差异项目数/可抵扣差异合计/递延税资产合计/加权平均税率
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcDeferredTax, calcWeightedAvgRate } from './useN1DeferredTaxEngine'
import { calcAuditedAmount, calcSubtotal, parseNum } from './useN1FormulaEngine'
import type { useN1FormData } from './useN1FormData'
import type { N1AdjudicationCategory } from './useN1Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表单行数据 */
export interface N1DetailRow {
  /** 唯一行标识 */
  id: string
  /** 暂时性差异项目名称 */
  itemName: string
  /** 所属分类 */
  category: N1AdjudicationCategory | string
  /** 账面价值 */
  bookValue: number
  /** 计税基础 */
  taxBase: number
  /** 暂时性差异（期初） */
  beginDiff: number
  /** 适用税率（期初），小数如0.25 */
  beginTaxRate: number
  /** 期初AJE */
  beginAje: number
  /** 期初RJE */
  beginRje: number
  /** 暂时性差异（期末） */
  endDiff: number
  /** 适用税率（期末），小数如0.25 */
  endTaxRate: number
  /** 期末AJE */
  endAje: number
  /** 期末RJE */
  endRje: number
  /** 本期确认 */
  recognized: number
  /** 本期转回 */
  reversed: number
  /** 备注 */
  remark: string
}

/** 明细表行计算结果 */
export interface N1DetailComputed extends N1DetailRow {
  /** 序号 */
  seq: number
  /** 可抵扣暂时性差异 = max(0, 计税基础 - 账面价值) (资产项) */
  deductibleDiff: number
  /** 递延税资产期初余额 = ROUND(beginDiff × beginTaxRate, 2) */
  beginDeferredTax: number
  /** 递延税资产期初审定 = beginDeferredTax + beginAje + beginRje */
  beginAudited: number
  /** 递延税资产期末余额 = ROUND(可抵扣暂时性差异 × 适用税率, 2) */
  endDeferredTax: number
  /** 递延税资产期末审定 = endDeferredTax + endAje + endRje */
  endAudited: number
}

/** 分类小计 */
export interface N1DetailCategoryTotal {
  category: string
  beginDiff: number
  beginDeferredTax: number
  beginAudited: number
  endDiff: number
  endDeferredTax: number
  endAudited: number
  count: number
}

/** 底部统计 */
export interface N1DetailStats {
  /** 差异项目总数 */
  itemCount: number
  /** 可抵扣暂时性差异合计（期末） */
  totalDeductibleDiff: number
  /** 递延税资产合计（期末审定） */
  totalDeferredTaxAsset: number
  /** 加权平均税率 */
  weightedAvgRate: number
}

export interface UseN1DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'N1-2-detail'
let _nextId = 1

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1Detail(options: UseN1DetailOptions) {
  const { allResponses, formData } = options

  // ─── 1. 动态行数据（从 allResponses 恢复） ─────────────────────────────

  const rows = ref<N1DetailRow[]>(_loadRows())

  function _loadRows(): N1DetailRow[] {
    const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (stored?.conclusion) {
      try {
        const parsed = JSON.parse(stored.conclusion) as N1DetailRow[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          _nextId = parsed.length + 1
          return parsed
        }
      } catch { /* fallback */ }
    }
    return []
  }

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1DetailComputed[]> = computed(() => {
    return rows.value.map((row, i) => {
      const beginDeferredTax = Math.round(calcDeferredTax(row.beginDiff, row.beginTaxRate) * 100) / 100
      // 可抵扣暂时性差异 = max(0, taxBase - bookValue)（资产项：账面＜计税基础时产生）
      const deductibleDiff = row.taxBase - row.bookValue > 0 ? row.taxBase - row.bookValue : 0
      const endDeferredTax = Math.round(calcDeferredTax(deductibleDiff, row.endTaxRate) * 100) / 100
      return {
        ...row,
        seq: i + 1,
        deductibleDiff,
        beginDeferredTax,
        beginAudited: calcAuditedAmount(beginDeferredTax, row.beginAje, row.beginRje),
        endDeferredTax,
        endAudited: calcAuditedAmount(endDeferredTax, row.endAje, row.endRje),
      }
    })
  })

  // ─── 3. 分类小计 ──────────────────────────────────────────────────────

  const categoryTotals: ComputedRef<N1DetailCategoryTotal[]> = computed(() => {
    const map = new Map<string, N1DetailComputed[]>()
    for (const row of computedRows.value) {
      const cat = row.category || '其他'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(row)
    }
    const result: N1DetailCategoryTotal[] = []
    for (const [cat, catRows] of map) {
      result.push({
        category: cat,
        beginDiff: calcSubtotal(catRows.map(r => r.beginDiff)),
        beginDeferredTax: calcSubtotal(catRows.map(r => r.beginDeferredTax)),
        beginAudited: calcSubtotal(catRows.map(r => r.beginAudited)),
        endDiff: calcSubtotal(catRows.map(r => r.endDiff)),
        endDeferredTax: calcSubtotal(catRows.map(r => r.endDeferredTax)),
        endAudited: calcSubtotal(catRows.map(r => r.endAudited)),
        count: catRows.length,
      })
    }
    return result
  })

  // ─── 4. 合计行 ─────────────────────────────────────────────────────────

  const totals = computed(() => {
    const r = computedRows.value
    return {
      beginDiff: calcSubtotal(r.map(x => x.beginDiff)),
      beginDeferredTax: calcSubtotal(r.map(x => x.beginDeferredTax)),
      beginAudited: calcSubtotal(r.map(x => x.beginAudited)),
      endDiff: calcSubtotal(r.map(x => x.deductibleDiff)),
      endDeferredTax: calcSubtotal(r.map(x => x.endDeferredTax)),
      endAudited: calcSubtotal(r.map(x => x.endAudited)),
    }
  })

  // ─── 5. 底部统计 ──────────────────────────────────────────────────────

  const stats: ComputedRef<N1DetailStats> = computed(() => {
    const r = computedRows.value
    const deductibleDiffs = r.map(x => x.deductibleDiff)
    const endTaxAmounts = r.map(x => x.endDeferredTax)
    return {
      itemCount: r.length,
      totalDeductibleDiff: calcSubtotal(deductibleDiffs),
      totalDeferredTaxAsset: calcSubtotal(r.map(x => x.endAudited)),
      weightedAvgRate: calcWeightedAvgRate(endTaxAmounts, deductibleDiffs),
    }
  })

  // ─── 6. 行操作 ─────────────────────────────────────────────────────────

  /** 新增明细行（需提供项目名称） */
  function addRow(itemName: string, category: string = '其他'): void {
    rows.value.push({
      id: `row-${_nextId++}`,
      itemName,
      category,
      bookValue: 0,
      taxBase: 0,
      beginDiff: 0,
      beginTaxRate: 0.25,
      beginAje: 0,
      beginRje: 0,
      endDiff: 0,
      endTaxRate: 0.25,
      endAje: 0,
      endRje: 0,
      recognized: 0,
      reversed: 0,
      remark: '',
    })
    _persistRows()
  }

  /** 删除明细行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _persistRows()
  }

  /** 更新行字段 */
  function updateRow(index: number, field: keyof Omit<N1DetailRow, 'id'>, value: any): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRows()
  }

  // ─── 7. 持久化 ─────────────────────────────────────────────────────────

  function _persistRows(): void {
    formData.debouncedSave(`${ITEM_PREFIX}-rows`, {
      conclusion: JSON.stringify(rows.value),
    })
    // 同步合计（供 crossSheet 读取）
    formData.saveField('N1-2-total-deferred-tax-asset', {
      remark: String(totals.value.endAudited),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    addRow,
    removeRow,
    updateRow,
    totals,
    categoryTotals,
    stats,
  }
}

export default useN1Detail
