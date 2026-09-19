/**
 * useF5OtherCost — F5-3 其他业务成本明细表 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5OtherCost,
  migrateF5OtherCostRows,
  computeF5OtherCostRow,
  buildF5OtherCostTotal,
  calcF5OtherCostChangeRate,
  emptyF5OtherCostRow,
  defaultF5OtherCostRows,
  F5_OTHER_COST_FIXED_ITEMS,
  F5_OTHER_COST_CHANGE_RATE_THRESHOLD,
} from '../useF5OtherCost'
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

describe('calcF5OtherCostChangeRate（对齐 Excel M 列）', () => {
  it('上期审定≠0：变动额/上期审定', () => {
    expect(calcF5OtherCostChangeRate(130, 100)).toBeCloseTo(30, 5)
  })

  it('上期审定=0且变动=0 → 0%', () => {
    expect(calcF5OtherCostChangeRate(0, 0)).toBe(0)
  })

  it('上期审定=0且本期有增加 → 100%', () => {
    expect(calcF5OtherCostChangeRate(50, 0)).toBe(100)
  })

  it('上期审定=0且本期减少 → -100%', () => {
    expect(calcF5OtherCostChangeRate(-20, 0)).toBe(-100)
  })
})

describe('migrate / compute / total', () => {
  it('兼容旧 currentAmount/priorAmount/costItem', () => {
    const rows = migrateF5OtherCostRows(JSON.stringify([
      { id: '1', costItem: '销售材料', currentAmount: 100, priorAmount: 80 },
    ]))
    expect(rows[0].item).toBe('销售材料')
    expect(rows[0].currentUnaudited).toBe(100)
    expect(rows[0].priorUnaudited).toBe(80)
    expect(rows[0].isFixed).toBe(true)
  })

  it('审定=未审+AJE+RJE；结构比按合计审定；变动额=审定差', () => {
    const a = {
      ...emptyF5OtherCostRow('A'),
      currentUnaudited: 100, currentAje: 10, currentRje: -5,
      priorUnaudited: 80, priorAje: 0, priorRje: 0,
    }
    const b = {
      ...emptyF5OtherCostRow('B'),
      currentUnaudited: 50, currentAje: 0, currentRje: 0,
      priorUnaudited: 20, priorAje: 0, priorRje: 0,
    }
    const currentTotal = 105 + 50
    const priorTotal = 80 + 20
    const rowA = computeF5OtherCostRow(a, currentTotal, priorTotal)
    expect(rowA.currentAudited).toBe(105)
    expect(rowA.priorAudited).toBe(80)
    expect(rowA.changeAmount).toBe(25)
    expect(rowA.currentStructureRatio).toBeCloseTo((105 / 155) * 100, 5)

    const total = buildF5OtherCostTotal([
      computeF5OtherCostRow(a, currentTotal, priorTotal),
      computeF5OtherCostRow(b, currentTotal, priorTotal),
    ])
    expect(total.currentAudited).toBe(155)
    expect(total.priorAudited).toBe(100)
    expect(total.changeAmount).toBe(55)
    expect(total.currentStructureRatio).toBe(100)
  })
})

describe('useF5OtherCost', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('默认预置固定项目；增删扩展行；固定行清空保留名称', () => {
    const allResponses = mkResponses()
    const other = useF5OtherCost({ allResponses, isReadonly: ref(false) })
    expect(other.rows.value.length).toBe(defaultF5OtherCostRows().length)
    expect(other.rows.value[0].item).toBe(F5_OTHER_COST_FIXED_ITEMS[0])
    expect(other.rows.value[0].isFixed).toBe(true)

    other.addRow('定制项目')
    expect(other.rows.value.some((r) => r.item === '定制项目')).toBe(true)

    const fixedId = other.rows.value[0].id
    other.updateCell(fixedId, 'currentUnaudited', 200)
    other.updateCell(fixedId, 'priorUnaudited', 100)
    expect(other.rows.value[0].changeRate).toBeCloseTo(100, 5)
    expect(other.isRowHighlighted(other.rows.value[0])).toBe(true)

    other.removeRow(fixedId)
    expect(other.rows.value.find((r) => r.id === fixedId)?.item).toBe(F5_OTHER_COST_FIXED_ITEMS[0])
    expect(other.rows.value.find((r) => r.id === fixedId)?.currentUnaudited).toBe(0)
  })

  it(`变动≥${F5_OTHER_COST_CHANGE_RATE_THRESHOLD}% 进入 significantChanges`, () => {
    const allResponses = mkResponses({
      'F5-3-other-cost-rows': JSON.stringify([{
        id: 'x', item: '销售材料', isFixed: true,
        currentUnaudited: 140, currentAje: 0, currentRje: 0,
        priorUnaudited: 100, priorAje: 0, priorRje: 0, remark: '',
      }]),
    })
    const other = useF5OtherCost({ allResponses, isReadonly: ref(false) })
    expect(other.significantChanges.value.map((r) => r.item)).toContain('销售材料')
  })

  it('legacy F5-3-rows 可迁移加载', () => {
    const allResponses = mkResponses({
      'F5-3-rows': JSON.stringify([
        { id: 'legacy', costItem: '出租固定资产', currentAmt: 30, priorAmt: 20 },
      ]),
    })
    const other = useF5OtherCost({ allResponses, isReadonly: ref(false) })
    expect(other.rows.value[0].item).toBe('出租固定资产')
    expect(other.rows.value[0].currentAudited).toBe(30)
    expect(other.rows.value[0].priorAudited).toBe(20)
  })
})
