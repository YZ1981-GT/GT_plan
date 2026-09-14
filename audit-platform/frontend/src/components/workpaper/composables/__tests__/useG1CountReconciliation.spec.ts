import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  enrich,
  migrateLegacyRow,
  emptyRow,
  useG1CountReconciliation,
} from '../useG1CountReconciliation'
import { calcReconciliation, calcFaceTotal } from '../useG1TraFinFormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

describe('G1-12 roll-back formulas', () => {
  it('报表日 = 盘点日 − 增加 + 减少', () => {
    expect(calcReconciliation(1000, 200, 50)).toBe(850)
  })

  it('总计 = 面值 × 数量', () => {
    expect(calcFaceTotal(100, 10)).toBe(1000)
  })

  it('enrich 计算报表日与差异', () => {
    const row = enrich({
      ...emptyRow('1', 1),
      countQuantity: 1000,
      countFaceValue: 100,
      increaseQuantity: 100,
      decreaseQuantity: 20,
      bookQuantity: 920,
      bookFaceValue: 100,
    })
    expect(row.countTotal).toBe(100000)
    expect(row.reportQuantity).toBe(920)
    expect(row.reportTotal).toBe(92000)
    expect(row.bookTotal).toBe(92000)
    expect(row.diffQuantity).toBe(0)
    expect(row.diffAmount).toBe(0)
  })

  it('旧版字段可迁移', () => {
    const row = migrateLegacyRow(
      {
        id: 'a',
        securityName: '国债A',
        countDayQuantity: 500,
        countDayAmount: 50000,
        increaseQuantity: 50,
        decreaseQuantity: 10,
        bookQuantity: 460,
        bookAmount: 46000,
        conclusion: '相符',
      },
      0,
    )
    expect(row.securityName).toBe('国债A')
    expect(row.countQuantity).toBe(500)
    expect(row.countFaceValue).toBe(100)
    expect(row.reportQuantity).toBe(460)
    expect(row.remark).toBe('相符')
  })
})

describe('useG1CountReconciliation.syncFromSecuritiesCount', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('从 G1-11 带入盘点日与账面数量', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('G1-11-rows', {
      item_id: 'G1-11-rows',
      conclusion: JSON.stringify([
        {
          id: 'c1',
          securityName: '股票甲',
          securityType: '权益',
          faceValue: 1,
          countedQuantity: 10000,
          bookedQuantity: 9800,
          couponRate: 0,
          maturityDate: '',
        },
      ]),
      remark: null,
    } as ChecklistResponse)

    const allResponses = ref(map)
    const saves: Array<[string, unknown]> = []
    const { syncFromSecuritiesCount, rows } = useG1CountReconciliation({
      allResponses,
      debouncedSave: (id, data) => saves.push([id, data]),
      isReadonly: ref(false),
    })

    const n = syncFromSecuritiesCount()
    expect(n).toBeGreaterThan(0)
    expect(rows.value[0].securityName).toBe('股票甲')
    expect(rows.value[0].countQuantity).toBe(10000)
    expect(rows.value[0].bookQuantity).toBe(9800)
    expect(rows.value[0].category).toBe('equity')
    expect(rows.value[0].reportQuantity).toBe(10000)
  })
})
