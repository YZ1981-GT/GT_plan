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
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcDeferredTax, calcWeightedAvgRate } from './useN1DeferredTaxEngine'
import { calcAuditedAmount, calcSubtotal, parseNum } from './useN1FormulaEngine'
import { resolveDeductibleDiff } from './useN1DisclosureSource'
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
  /** roll-forward 推导期末 = 期初审定 + 本期确认 − 本期转回 */
  rollForwardEnd: number
  /** roll-forward 差异 = 期末审定 − roll-forward 推导期末 */
  rollForwardDiff: number
  /** 是否存在 roll-forward 差异（已录确认/转回且差异>0.01） */
  hasRollForwardDiff: boolean
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
/** N1-4 测算表行存储键（字段级带入的来源，源模板账面价值/计税基础在 N1-4） */
const N1_CALC_ROWS_KEY = 'N1-4-calc-rows'
let _nextId = 1

/**
 * 源模板 N1-2 明细表默认项目清单（含类别映射，对齐致同 N1-2 A11~A40）
 * 项目组根据被审计单位税收情况增减，此处提供源模板全量 29 项作为初始种子。
 */
export const N1_DEFAULT_DETAIL_ITEMS: Array<{ itemName: string; category: string }> = [
  { itemName: '交易性金融资产（公允价值与初始账面成本差异）', category: '公允价值变动' },
  { itemName: '应收账款（坏账准备）', category: '资产减值准备' },
  { itemName: '其他应收款（坏账准备）', category: '资产减值准备' },
  { itemName: '存货（跌价准备）', category: '资产减值准备' },
  { itemName: '应收款项融资（公允价值与经实际利率法摊销后账面金额的差异）', category: '公允价值变动' },
  { itemName: '合同资产（减值准备）', category: '资产减值准备' },
  { itemName: '其他债权投资（公允价值与经实际利率法摊销后账面金额的差异）', category: '公允价值变动' },
  { itemName: '其他权益工具投资（公允价值与初始账面成本差异）', category: '公允价值变动' },
  { itemName: '债权投资（减值准备）', category: '资产减值准备' },
  { itemName: '长期股权投资（减值准备）', category: '资产减值准备' },
  { itemName: '投资性房地产（公允价值与账面差异）', category: '公允价值变动' },
  { itemName: '投资性房地产（折旧）', category: '其他' },
  { itemName: '固定资产（减值准备）', category: '资产减值准备' },
  { itemName: '固定资产折旧（年限、残值）', category: '其他' },
  { itemName: '在建工程（减值准备）', category: '资产减值准备' },
  { itemName: '使用权资产（减值准备）', category: '资产减值准备' },
  { itemName: '无形资产（减值准备、摊销）', category: '资产减值准备' },
  { itemName: '无形资产（研发费用资本化）', category: '其他' },
  { itemName: '开办费（摊销方法）', category: '其他' },
  { itemName: '交易性金融负债（公允价值与账面差异）', category: '公允价值变动' },
  { itemName: '应付职工薪酬（已计提未支付）', category: '其他' },
  { itemName: '应付职工薪酬（预计辞退福利费）', category: '其他' },
  { itemName: '预提费用', category: '其他' },
  { itemName: '递延收益', category: '其他' },
  { itemName: '预计负债（预计产品保修费用等）', category: '其他' },
  { itemName: '收入（预收款项）', category: '其他' },
  { itemName: '销售费用（广告费和业务宣传费）', category: '其他' },
  { itemName: '可用以后年度税前利润弥补的亏损', category: '可抵扣亏损' },
  { itemName: '除上述项目以外的其他', category: '其他' },
]

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

  // ─── 1b. 异步 hydrate（loadData 完成后 allResponses 才有数据） ───────────
  // 铁律：setup 阶段 allResponses 为空，若不重新 hydrate 则刷新后明细全空，
  //       且「预置源模板项目」的空表守卫失效会覆盖已录数据。
  let _hydrated = false

  watch(
    allResponses,
    () => {
      if (_hydrated) return
      const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
      if (!stored?.conclusion) return
      // 仅当本地仍为空时接管（不覆盖用户已开始的编辑）
      if (rows.value.length === 0) rows.value = _loadRows()
      _hydrated = true
    },
    { immediate: true },
  )

  /** 存储中是否已有明细行（供 seed 守卫用，防止 hydrate 前误覆盖） */
  function _hasStoredRows(): boolean {
    const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (!stored?.conclusion) return false
    try {
      const parsed = JSON.parse(stored.conclusion)
      return Array.isArray(parsed) && parsed.length > 0
    } catch {
      return false
    }
  }

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1DetailComputed[]> = computed(() => {
    return rows.value.map((row, i) => {
      const beginDeferredTax = Math.round(calcDeferredTax(row.beginDiff, row.beginTaxRate) * 100) / 100
      // 可抵扣暂时性差异（期末）：口径收敛到 resolveDeductibleDiff（披露表共用同一函数）
      // 铁律：期初用 beginDiff，期末优先用手工 endDiff，否则回退「计税基础−账面价值」，
      //       否则用户填的期末差异列会成为死列，且披露侧会与明细侧口径漂移。
      const deductibleDiff = resolveDeductibleDiff(row)
      const endDeferredTax = Math.round(calcDeferredTax(deductibleDiff, row.endTaxRate) * 100) / 100
      const endAudited = calcAuditedAmount(endDeferredTax, row.endAje, row.endRje)
      const beginAudited = calcAuditedAmount(beginDeferredTax, row.beginAje, row.beginRje)
      // roll-forward 自校验：期末 = 期初 + 本期确认 − 本期转回（资产类借增贷减）
      const rollForwardEnd = beginAudited + parseNum(row.recognized) - parseNum(row.reversed)
      const rollForwardDiff = Math.round((endAudited - rollForwardEnd) * 100) / 100
      return {
        ...row,
        seq: i + 1,
        deductibleDiff,
        beginDeferredTax,
        beginAudited,
        endDeferredTax,
        endAudited,
        rollForwardEnd: Math.round(rollForwardEnd * 100) / 100,
        rollForwardDiff,
        hasRollForwardDiff:
          (parseNum(row.recognized) !== 0 || parseNum(row.reversed) !== 0) &&
          Math.abs(rollForwardDiff) > 0.01,
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

  /**
   * 预置源模板 29 项常见暂时性差异项目（仅在当前为空时生效，避免覆盖已录数据）。
   * 对齐致同 N1-2 明细表默认项目清单。
   */
  function seedDefaultRows(): void {
    if (rows.value.length > 0) return
    // 双重守卫：存储中已有明细行时禁止 seed（防 hydrate 尚未完成即覆盖已录数据）
    if (_hasStoredRows()) return
    for (const item of N1_DEFAULT_DETAIL_ITEMS) {
      rows.value.push({
        id: `row-${_nextId++}`,
        itemName: item.itemName,
        category: item.category,
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
    }
    _persistRows()
  }

  /** 更新行字段 */
  function updateRow(index: number, field: keyof Omit<N1DetailRow, 'id'>, value: any): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRows()
  }

  // ─── 6b. 从 N1-4 测算表字段级带入（账面价值/计税基础/期末税率） ──────────

  interface CalcRowLike {
    itemName?: string
    bookValue?: number | string
    taxBase?: number | string
    taxRate?: number | string
  }

  function _readCalcRows(): CalcRowLike[] {
    const stored = allResponses.value.get(N1_CALC_ROWS_KEY)
    const raw = stored?.conclusion ?? stored?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(String(raw))
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /**
   * 从 N1-4 测算表按「项目名称」带入账面价值 / 计税基础 / 期末适用税率。
   *
   * 口径：源模板的账面价值与计税基础在测算表 N1-4 取得，明细表 N1-2 应引用其结果，
   * 避免同一数据两处各录一遍（此前两表都要手打，且没有任何一致性提示）。
   *
   * 🔴 仅填空不覆盖：目标字段为 0（未录）时才写入；已录数据一律保留，
   *    差异由 `calcTableMismatches` 提示人工判断。
   */
  function pullFromCalcTable(): { matched: number; filled: number } {
    const calcRows = _readCalcRows()
    if (calcRows.length === 0) return { matched: 0, filled: 0 }
    const byName = new Map<string, CalcRowLike>()
    for (const c of calcRows) {
      const name = String(c.itemName ?? '').trim()
      if (name) byName.set(name, c)
    }

    let matched = 0
    let filled = 0
    rows.value.forEach((row) => {
      const src = byName.get(String(row.itemName ?? '').trim())
      if (!src) return
      matched += 1
      if (parseNum(row.bookValue) === 0 && parseNum(src.bookValue) !== 0) {
        row.bookValue = parseNum(src.bookValue)
        filled += 1
      }
      if (parseNum(row.taxBase) === 0 && parseNum(src.taxBase) !== 0) {
        row.taxBase = parseNum(src.taxBase)
        filled += 1
      }
      if (parseNum(row.endTaxRate) === 0 && parseNum(src.taxRate) !== 0) {
        row.endTaxRate = parseNum(src.taxRate)
        filled += 1
      }
    })
    if (filled > 0) _persistRows()
    return { matched, filled }
  }

  /** N1-2 与 N1-4 同名项目的账面价值/计税基础不一致清单（两侧均非零且差额 > 0.01） */
  const calcTableMismatches: ComputedRef<
    Array<{ itemName: string; field: '账面价值' | '计税基础'; detailValue: number; calcValue: number }>
  > = computed(() => {
    const calcRows = _readCalcRows()
    if (calcRows.length === 0) return []
    const byName = new Map<string, CalcRowLike>()
    for (const c of calcRows) {
      const name = String(c.itemName ?? '').trim()
      if (name) byName.set(name, c)
    }
    const out: Array<{ itemName: string; field: '账面价值' | '计税基础'; detailValue: number; calcValue: number }> = []
    for (const row of rows.value) {
      const src = byName.get(String(row.itemName ?? '').trim())
      if (!src) continue
      const pairs: Array<['账面价值' | '计税基础', number, number]> = [
        ['账面价值', parseNum(row.bookValue), parseNum(src.bookValue)],
        ['计税基础', parseNum(row.taxBase), parseNum(src.taxBase)],
      ]
      for (const [field, a, b] of pairs) {
        if (a !== 0 && b !== 0 && Math.abs(a - b) > 0.01) {
          out.push({ itemName: row.itemName, field, detailValue: a, calcValue: b })
        }
      }
    }
    return out
  })

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
    seedDefaultRows,
    pullFromCalcTable,
    calcTableMismatches,
    totals,
    categoryTotals,
    stats,
  }
}

export default useN1Detail
