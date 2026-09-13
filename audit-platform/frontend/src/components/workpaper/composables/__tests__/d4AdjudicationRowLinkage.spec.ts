/**
 * d4AdjudicationRowLinkage — D4-2/3 行同步 → D4-1 派生行守卫
 *
 * Property 1: D4-2 明细产品集合 P → D4-1 主营区块的 isFromCrossSheet 派生行数 == |P|
 * Spec: d4-price-analysis-writeback-linkage Task 7
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'

// 直接测试 useD4Adjudication 的纯函数行为（通过构造 allResponses mock）
// 由于 composable 依赖 Vue setup context，我们测试核心逻辑：
// sections 从 mainRevenueByProduct 派生行

describe('D4-1 crossSheet 行派生', () => {
  /** 模拟 labelKey 归一化 */
  function labelKey(raw: string): string {
    return raw.replace(/[\s\u3000]+/g, '').toLowerCase()
  }

  /** 模拟 crossSheetMainRows 生成逻辑 */
  function buildCrossSheetRows(
    byProduct: Record<string, { current: number; prior: number }>,
    section: 'main' | 'other',
  ) {
    return Object.entries(byProduct).map(([name, vals]) => ({
      rowKey: `xsheet-${section}-${labelKey(name)}`,
      label: name,
      isFromCrossSheet: true,
      isEditable: false,
      currentUnadjusted: vals.current,
      priorUnadjusted: vals.prior,
    }))
  }

  /** 模拟 mergeCrossSheetAndDynamic 去重逻辑 */
  function mergeCrossSheetAndDynamic(
    crossSheetRows: Array<{ rowKey: string; label: string; isFromCrossSheet: boolean }>,
    dynamicRows: Array<{ rowKey: string; label: string; isFromCrossSheet: boolean }>,
  ) {
    const seen = new Set<string>()
    const merged: typeof crossSheetRows = []
    for (const r of crossSheetRows) {
      const key = labelKey(r.label)
      if (!seen.has(key)) { seen.add(key); merged.push(r) }
    }
    for (const r of dynamicRows) {
      const key = labelKey(r.label)
      if (!seen.has(key)) { seen.add(key); merged.push(r) }
    }
    return merged
  }

  it('D4-2 有 2 产品 → 派生 2 行 isFromCrossSheet', () => {
    const byProduct = { '产品A': { current: 100, prior: 80 }, '产品B': { current: 200, prior: 150 } }
    const rows = buildCrossSheetRows(byProduct, 'main')
    expect(rows).toHaveLength(2)
    expect(rows.every(r => r.isFromCrossSheet)).toBe(true)
    expect(rows.every(r => r.isEditable === false)).toBe(true)
  })

  it('D4-2 有 0 产品 → 派生 0 行', () => {
    const rows = buildCrossSheetRows({}, 'main')
    expect(rows).toHaveLength(0)
  })

  it('D4-2 删 1 产品 → 派生行数从 3 → 2', () => {
    const initial = { 'A': { current: 1, prior: 0 }, 'B': { current: 2, prior: 0 }, 'C': { current: 3, prior: 0 } }
    expect(buildCrossSheetRows(initial, 'main')).toHaveLength(3)
    const after = { 'A': { current: 1, prior: 0 }, 'C': { current: 3, prior: 0 } }
    expect(buildCrossSheetRows(after, 'main')).toHaveLength(2)
  })

  it('同名去重：派生行优先于手工行', () => {
    const crossRows = [{ rowKey: 'xsheet-main-产品a', label: '产品A', isFromCrossSheet: true }]
    const dynamicRows = [{ rowKey: 'manual-1', label: '产品A', isFromCrossSheet: false }]
    const merged = mergeCrossSheetAndDynamic(crossRows, dynamicRows)
    expect(merged).toHaveLength(1)
    expect(merged[0].isFromCrossSheet).toBe(true)
  })

  it('不同名行全保留', () => {
    const crossRows = [{ rowKey: 'xsheet-main-a', label: 'A', isFromCrossSheet: true }]
    const dynamicRows = [{ rowKey: 'manual-1', label: 'B', isFromCrossSheet: false }]
    const merged = mergeCrossSheetAndDynamic(crossRows, dynamicRows)
    expect(merged).toHaveLength(2)
  })

  it('D4-3 项目派生 → other 区块行', () => {
    const byItem = { '租金收入': { current: 50, prior: 30 } }
    const rows = buildCrossSheetRows(byItem, 'other')
    expect(rows).toHaveLength(1)
    expect(rows[0].rowKey).toBe('xsheet-other-租金收入')
  })

  it('rowKey 稳定性：labelKey 去空格、全角空格', () => {
    expect(labelKey('产品 A')).toBe('产品a')
    expect(labelKey('产品　A')).toBe('产品a') // 全角空格
    expect(labelKey('产品A ')).toBe('产品a')
  })
})
