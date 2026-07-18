/**
 * useF5Comparison — F5-5 主营业务成本与上年度比较分析表 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5Comparison,
  migrateF5ComparisonRows,
  computeF5ComparisonRow,
  buildF5ComparisonTotal,
  calcF5ComparisonChangeRate,
  emptyF5ComparisonRow,
  defaultF5ComparisonRows,
  F5_COMPARISON_DEFAULT_ROWS,
  F5_COMPARISON_CHANGE_RATE_THRESHOLD,
} from '../useF5Comparison'
import type { ChecklistResponse } from '../useF1FormData'

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.value.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  return map
}

describe('calcF5ComparisonChangeRate', () => {
  it('上期≠0：变动额/上期×100', () => {
    expect(calcF5ComparisonChangeRate(30, 100)).toBeCloseTo(30, 5)
  })

  it('上期=0 → N/A（对应 Excel #DIV/0）', () => {
    expect(calcF5ComparisonChangeRate(10, 0)).toBe('N/A')
    expect(calcF5ComparisonChangeRate(0, 0)).toBe('N/A')
  })
})

describe('migrate / compute / total', () => {
  it('总成本=数量×单价；变动额/率', () => {
    const row = computeF5ComparisonRow({
      ...emptyF5ComparisonRow('A'),
      currentQty: 20, currentUnitCost: 5,
      priorQty: 10, priorUnitCost: 4,
    })
    expect(row.currentTotalCost).toBe(100)
    expect(row.priorTotalCost).toBe(40)
    expect(row.qtyChange).toBe(10)
    expect(row.unitCostChange).toBe(1)
    expect(row.totalCostChange).toBe(60)
    expect(row.qtyChangeRate).toBeCloseTo(100, 5)
    expect(row.unitCostChangeRate).toBeCloseTo(25, 5)
    expect(row.totalCostChangeRate).toBeCloseTo(150, 5)
  })

  it('合计行仅汇总总成本', () => {
    const rows = [
      computeF5ComparisonRow({
        ...emptyF5ComparisonRow('A'),
        currentQty: 10, currentUnitCost: 2, priorQty: 10, priorUnitCost: 1,
      }),
      computeF5ComparisonRow({
        ...emptyF5ComparisonRow('B'),
        currentQty: 5, currentUnitCost: 4, priorQty: 5, priorUnitCost: 2,
      }),
    ]
    const total = buildF5ComparisonTotal(rows)
    expect(total.currentTotalCost).toBe(40)
    expect(total.priorTotalCost).toBe(20)
    expect(total.totalCostChange).toBe(20)
    expect(total.totalCostChangeRate).toBeCloseTo(100, 5)
  })

  it('兼容旧毛利模型 currentCost/priorCost', () => {
    const rows = migrateF5ComparisonRows(JSON.stringify([
      { id: '1', product: '旧品', currentCost: 700, priorCost: 500, changeReason: '量增' },
    ]))
    expect(rows[0].currentQty).toBe(1)
    expect(rows[0].currentUnitCost).toBe(700)
    expect(rows[0].priorUnitCost).toBe(500)
    expect(computeF5ComparisonRow(rows[0]).currentTotalCost).toBe(700)
  })
})

describe('useF5Comparison', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it(`默认 ${F5_COMPARISON_DEFAULT_ROWS} 行；增删；变动≥${F5_COMPARISON_CHANGE_RATE_THRESHOLD}% 高亮`, () => {
    const allResponses = mkResponses()
    const cmp = useF5Comparison({ allResponses, isReadonly: ref(false) })
    expect(cmp.rows.value).toHaveLength(F5_COMPARISON_DEFAULT_ROWS)
    expect(defaultF5ComparisonRows()).toHaveLength(F5_COMPARISON_DEFAULT_ROWS)

    cmp.addRow('新品')
    const id = cmp.rows.value.find((r) => r.product === '新品')!.id
    cmp.updateCell(id, 'currentQty', 130)
    cmp.updateCell(id, 'currentUnitCost', 1)
    cmp.updateCell(id, 'priorQty', 100)
    cmp.updateCell(id, 'priorUnitCost', 1)
    const row = cmp.rows.value.find((r) => r.id === id)!
    expect(row.totalCostChangeRate).toBeCloseTo(30, 5)
    expect(cmp.isRowHighlighted(row)).toBe(true)
    expect(cmp.significantChanges.value.some((r) => r.id === id)).toBe(true)

    cmp.removeRow(id)
    expect(cmp.rows.value.find((r) => r.id === id)).toBeFalsy()
  })

  it('legacy F5-5-rows 可迁移加载', () => {
    const allResponses = mkResponses({
      'F5-5-rows': JSON.stringify([
        { id: 'legacy', variety: '甲', currentQty: 2, currentUnitCost: 50, priorQty: 1, priorUnitCost: 40 },
      ]),
    })
    const cmp = useF5Comparison({ allResponses, isReadonly: ref(false) })
    expect(cmp.rows.value[0].product).toBe('甲')
    expect(cmp.rows.value[0].currentTotalCost).toBe(100)
    expect(cmp.rows.value[0].priorTotalCost).toBe(40)
  })
})
