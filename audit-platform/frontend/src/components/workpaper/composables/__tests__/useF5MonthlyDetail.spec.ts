/**
 * useF5MonthlyDetail — F5-2 主营业务成本月度明细表 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5MonthlyDetail,
  migrateF5MonthlyRows,
  computeF5MonthlyRow,
  buildF5MonthlyTotal,
  buildF5MonthlyRatioRow,
  emptyF5MonthlyRow,
  F5_MONTHLY_CHANGE_RATE_THRESHOLD,
} from '../useF5MonthlyDetail'
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

describe('migrateF5MonthlyRows', () => {
  it('兼容 months 数组与旧 priorYearTotal', () => {
    const rows = migrateF5MonthlyRows(JSON.stringify([
      { id: '1', product: '甲', months: [1, 2, 3], priorYearTotal: 50 },
    ]))
    expect(rows[0].months.slice(0, 3)).toEqual([1, 2, 3])
    expect(rows[0].priorUnaudited).toBe(50)
  })

  it('兼容扁平 m1..m12 / variety 导入格式', () => {
    const rows = migrateF5MonthlyRows(JSON.stringify([
      { variety: '乙', m1: 10, m2: 20, m12: 30, currentAje: 5, priorUnaudited: 40 },
    ]))
    expect(rows[0].product).toBe('乙')
    expect(rows[0].months[0]).toBe(10)
    expect(rows[0].months[1]).toBe(20)
    expect(rows[0].months[11]).toBe(30)
    expect(rows[0].currentAje).toBe(5)
    expect(rows[0].priorUnaudited).toBe(40)
  })
})

describe('computeF5MonthlyRow / total / ratio', () => {
  it('未审=Σ月；审定=未审+AJE+RJE；变动比例公式', () => {
    const stored = {
      ...emptyF5MonthlyRow('A'),
      months: [100, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      currentAje: 10,
      currentRje: -5,
      priorUnaudited: 200,
      priorAje: 0,
      priorRje: 0,
    }
    const row = computeF5MonthlyRow(stored)
    expect(row.currentUnaudited).toBe(300)
    expect(row.currentAudited).toBe(305)
    expect(row.priorAudited).toBe(200)
    expect(row.unauditedChangeRate).toBeCloseTo(50, 5)
    expect(row.auditedChangeRate).toBeCloseTo(52.5, 5)
  })

  it('合计行纵向汇总；比例行按本期未审合计', () => {
    const rows = [
      computeF5MonthlyRow({
        ...emptyF5MonthlyRow('A'),
        months: [60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        priorUnaudited: 50,
      }),
      computeF5MonthlyRow({
        ...emptyF5MonthlyRow('B'),
        months: [40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        priorUnaudited: 50,
      }),
    ]
    const total = buildF5MonthlyTotal(rows)
    expect(total.months[0]).toBe(100)
    expect(total.currentUnaudited).toBe(100)
    const ratio = buildF5MonthlyRatioRow(total)
    // 比例行：各月合计 / 本期未审合计 → 1月 100/100 = 100%
    expect(ratio.months[0]).toBe(100)
    expect(ratio.currentUnaudited).toBe(100)
  })
})

describe('useF5MonthlyDetail', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('默认三品种；增删行；更新月度后重算', () => {
    const allResponses = mkResponses()
    const detail = useF5MonthlyDetail({ allResponses, isReadonly: ref(false) })
    expect(detail.rows.value).toHaveLength(3)

    detail.addRow('新品')
    expect(detail.rows.value.some((r) => r.product === '新品')).toBe(true)

    const id = detail.rows.value[0].id
    detail.updateMonth(id, 0, 120)
    detail.updateCell(id, 'priorUnaudited', 100)
    expect(detail.rows.value[0].currentUnaudited).toBe(120)
    expect(detail.rows.value[0].unauditedChangeRate).toBeCloseTo(20, 5)

    detail.removeRow(id)
    expect(detail.rows.value.find((r) => r.id === id)).toBeFalsy()
  })

  it(`变动≥${F5_MONTHLY_CHANGE_RATE_THRESHOLD}% 进入 significantChanges`, () => {
    const allResponses = mkResponses({
      'F5-2-monthly-rows': JSON.stringify([{
        id: 'x', product: '波动品',
        months: [130, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        priorUnaudited: 100,
      }]),
    })
    const detail = useF5MonthlyDetail({ allResponses, isReadonly: ref(false) })
    expect(detail.isRowHighlighted(detail.rows.value[0])).toBe(true)
    expect(detail.significantChanges.value.map((r) => r.product)).toContain('波动品')
  })

  it('legacy F5-2-rows 可迁移加载', () => {
    const allResponses = mkResponses({
      'F5-2-rows': JSON.stringify([{
        id: 'legacy', variety: '旧品种', m1: 11, m2: 22, priorTotal: 20,
      }]),
    })
    const detail = useF5MonthlyDetail({ allResponses, isReadonly: ref(false) })
    expect(detail.rows.value[0].product).toBe('旧品种')
    expect(detail.rows.value[0].currentUnaudited).toBe(33)
    expect(detail.rows.value[0].priorUnaudited).toBe(20)
  })
})
