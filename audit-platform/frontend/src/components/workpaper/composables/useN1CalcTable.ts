/**
 * useN1CalcTable — 测算表N1-4 逻辑层
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.4
 * Requirements: 4.1-4.6
 *
 * 职责：
 * - 从 N1-2 明细项引用行（项目名）
 * - 列结构：项目/账面价值/计税基础/适用税率/可抵扣暂时性差异/应纳税暂时性差异/
 *          递延税资产/对方科目/递延税资产账面/差异/递延税负债/对方科目/递延税负债账面/差异
 * - 公式：可抵扣差异/应纳税差异/递延税资产/递延税负债/应确认差异
 * - 资产部分回填 N1-1，负债部分联动 N3
 * - 合计行 + 资产合计/负债合计
 *
 * 核心引擎：
 * - calcDeductibleDiff / calcTaxableDiff / calcDeferredTaxAsset / calcDeferredTaxLiability / calcDeferredTaxDiff
 *   from useN1DeferredTaxEngine
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcDeductibleDiff,
  calcTaxableDiff,
  calcDeferredTaxAsset,
  calcDeferredTaxLiability,
  calcDeferredTaxDiff,
} from './useN1DeferredTaxEngine'
import { calcSubtotal, parseNum } from './useN1FormulaEngine'
import type { useN1FormData } from './useN1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 测算表单行数据（可编辑字段） */
export interface N1CalcTableRow {
  /** 唯一行标识 */
  id: string
  /** 项目名称（引用自N1-2） */
  itemName: string
  /** 账面价值 */
  bookValue: number
  /** 计税基础 */
  taxBase: number
  /** 适用税率（小数如0.25） */
  taxRate: number
  /** 对方科目（资产侧） */
  assetCounterAccount: string
  /** 递延税资产当前账面余额 */
  assetBookBalance: number
  /** 对方科目（负债侧） */
  liabilityCounterAccount: string
  /** 递延税负债当前账面余额 */
  liabilityBookBalance: number
}

/** 测算表行计算结果 */
export interface N1CalcTableComputed extends N1CalcTableRow {
  /** 可抵扣暂时性差异（≥0） */
  deductibleDiff: number
  /** 应纳税暂时性差异（≥0） */
  taxableDiff: number
  /** 应确认递延所得税资产 */
  deferredTaxAsset: number
  /** 应确认递延所得税负债 */
  deferredTaxLiability: number
  /** 递延税资产差异（应确认-账面） */
  assetDiff: number
  /** 递延税负债差异（应确认-账面） */
  liabilityDiff: number
}

/** 测算表合计 */
export interface N1CalcTableTotals {
  deductibleDiff: number
  taxableDiff: number
  deferredTaxAsset: number
  deferredTaxLiability: number
  assetBookBalance: number
  liabilityBookBalance: number
  assetDiff: number
  liabilityDiff: number
}

export interface UseN1CalcTableOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'N1-4-calc'
let _nextId = 1

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1CalcTable(options: UseN1CalcTableOptions) {
  const { allResponses, formData } = options

  // ─── 1. 行数据（从 allResponses 恢复或初始化） ─────────────────────────

  const rows = ref<N1CalcTableRow[]>(_loadRows())

  function _loadRows(): N1CalcTableRow[] {
    const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (stored?.conclusion) {
      try {
        const parsed = JSON.parse(stored.conclusion) as N1CalcTableRow[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          _nextId = parsed.length + 1
          return parsed
        }
      } catch { /* fallback */ }
    }
    return []
  }

  // ─── 1b. 异步 hydrate（loadData 完成后 allResponses 才有数据） ───────────
  let _hydrated = false

  watch(
    allResponses,
    () => {
      if (_hydrated) return
      const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
      if (!stored?.conclusion) return
      if (rows.value.length === 0) rows.value = _loadRows()
      _hydrated = true
    },
    { immediate: true },
  )

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1CalcTableComputed[]> = computed(() => {
    return rows.value.map((row) => {
      const deductibleDiff = calcDeductibleDiff(row.bookValue, row.taxBase)
      const taxableDiff = calcTaxableDiff(row.bookValue, row.taxBase)
      const deferredTaxAsset = calcDeferredTaxAsset(deductibleDiff, row.taxRate)
      const deferredTaxLiability = calcDeferredTaxLiability(taxableDiff, row.taxRate)
      const assetDiff = calcDeferredTaxDiff(deferredTaxAsset, row.assetBookBalance)
      const liabilityDiff = calcDeferredTaxDiff(deferredTaxLiability, row.liabilityBookBalance)
      return {
        ...row,
        deductibleDiff,
        taxableDiff,
        deferredTaxAsset,
        deferredTaxLiability,
        assetDiff,
        liabilityDiff,
      }
    })
  })

  // ─── 3. 合计行 ─────────────────────────────────────────────────────────

  const totals: ComputedRef<N1CalcTableTotals> = computed(() => {
    const r = computedRows.value
    return {
      deductibleDiff: calcSubtotal(r.map(x => x.deductibleDiff)),
      taxableDiff: calcSubtotal(r.map(x => x.taxableDiff)),
      deferredTaxAsset: calcSubtotal(r.map(x => x.deferredTaxAsset)),
      deferredTaxLiability: calcSubtotal(r.map(x => x.deferredTaxLiability)),
      assetBookBalance: calcSubtotal(r.map(x => x.assetBookBalance)),
      liabilityBookBalance: calcSubtotal(r.map(x => x.liabilityBookBalance)),
      assetDiff: calcSubtotal(r.map(x => x.assetDiff)),
      liabilityDiff: calcSubtotal(r.map(x => x.liabilityDiff)),
    }
  })

  /** 递延税资产合计（归N1审定表） */
  const assetTotal: ComputedRef<number> = computed(() => totals.value.deferredTaxAsset)

  /** 递延税负债合计（联动N3） */
  const liabilityTotal: ComputedRef<number> = computed(() => totals.value.deferredTaxLiability)

  // ─── 4. 行操作 ─────────────────────────────────────────────────────────

  /** 新增测算行 */
  function addRow(itemName: string): void {
    rows.value.push({
      id: `calc-${_nextId++}`,
      itemName,
      bookValue: 0,
      taxBase: 0,
      taxRate: 0.25,
      assetCounterAccount: '',
      assetBookBalance: 0,
      liabilityCounterAccount: '',
      liabilityBookBalance: 0,
    })
    _persistRows()
  }

  /** 删除测算行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _persistRows()
  }

  /** 更新行字段 */
  function updateRow(index: number, field: keyof Omit<N1CalcTableRow, 'id'>, value: any): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRows()
  }

  // ─── 5. 从明细表刷新（引用N1-2项目名） ────────────────────────────────

  /**
   * 从 N1-2 明细表刷新项目列表：
   * - 已存在的项目保留数据不变
   * - 新增的项目创建空行
   * - N1-2中已删除的项目保留在测算表（允许手动删除）
   */
  function refreshFromDetail(detailItems: Array<{ itemName: string; category: string }>): void {
    const existingNames = new Set(rows.value.map(r => r.itemName))
    for (const item of detailItems) {
      if (!existingNames.has(item.itemName)) {
        addRow(item.itemName)
      }
    }
  }

  // ─── 6. 持久化 ─────────────────────────────────────────────────────────

  function _persistRows(): void {
    formData.debouncedSave(`${ITEM_PREFIX}-rows`, {
      conclusion: JSON.stringify(rows.value),
    })
    // 同步合计（供 crossSheet 读取）
    formData.saveField('N1-4-total-deferred-tax-asset', {
      remark: String(totals.value.deferredTaxAsset),
    })
    formData.saveField('N1-4-total-deferred-tax-liability', {
      remark: String(totals.value.deferredTaxLiability),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totals,
    assetTotal,
    liabilityTotal,
    addRow,
    removeRow,
    updateRow,
    refreshFromDetail,
  }
}

export default useN1CalcTable
