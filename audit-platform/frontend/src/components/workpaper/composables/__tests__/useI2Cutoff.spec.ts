/**
 * useI2Cutoff — 跨期判定 / 分段 / 样本标准 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useI2Cutoff } from '../useI2Cutoff'
import {
  isCutoffPeriodCrossing,
  calcCrossPeriodAmount,
  isCrossPeriod,
} from '../useI2FormulaEngine'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

describe('useI2FormulaEngine — 会计跨期 vs 滞后天数', () => {
  const cutoff = new Date('2025-12-31T00:00:00')

  it('单据与记账分处截止日两侧 → 跨期', () => {
    expect(
      isCutoffPeriodCrossing(
        new Date('2026-01-02T00:00:00'),
        new Date('2025-12-30T00:00:00'),
        cutoff,
      ),
    ).toBe(true)
  })

  it('单据与记账均在截止日前 → 不跨期（即使日期差>5）', () => {
    const doc = new Date('2025-12-20T00:00:00')
    const rec = new Date('2025-12-28T00:00:00')
    expect(isCutoffPeriodCrossing(doc, rec, cutoff)).toBe(false)
    expect(isCrossPeriod(rec, doc, 5)).toBe(true) // 滞后异常 ≠ 会计跨期
  })

  it('跨期金额：跨期取金额，否则 0', () => {
    expect(calcCrossPeriodAmount(true, 12345.67)).toBe(12345.67)
    expect(calcCrossPeriodAmount(false, 12345.67)).toBe(0)
  })
})

describe('useI2Cutoff', () => {
  const allResponses = ref(new Map<string, any>())
  const projectId = ref('proj-1')
  const saveResponses = vi.fn(async () => {})

  beforeEach(() => {
    allResponses.value = new Map()
    saveResponses.mockClear()
  })

  function setup() {
    return useI2Cutoff({ allResponses, saveResponses, projectId })
  }

  it('设置截止日后，账在截止前、单据在截止后 → 跨期多记，并计入期前段', () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31' })
    api.addForwardRow({
      recordDate: '2025-12-30',
      amount: 10000,
      documentDate: '2026-01-03',
      documentAmount: 10000,
      voucherNo: '记-1201',
      documentNo: 'ZC-01',
    })

    const row = api.forwardRows.value[0]
    expect(row.isCrossPeriod).toBe(true)
    expect(row.conclusion).toBe('跨期多记')
    expect(row.crossPeriodAmount).toBe(10000)
    expect(row.side).toBe('before')
    expect(api.forwardBeforeRows.value).toHaveLength(1)
    expect(api.forwardAfterRows.value).toHaveLength(0)
    expect(api.forwardCrossPeriodCount.value).toBe(1)
    expect(api.forwardCrossPeriodAmount.value).toBe(10000)
  })

  it('反向：单据在截止前、记账在截止后 → 跨期漏记，并计入期前单据段', () => {
    const api = setup()
    api.updateBackwardCriteria({ cutoffDate: '2025-12-31' })
    api.addBackwardRow({
      documentDate: '2025-12-28',
      documentAmount: 8000,
      recordDate: '2026-01-05',
      amount: 8000,
      documentNo: 'ZC-99',
      voucherNo: '记-0105',
    })

    const row = api.backwardRows.value[0]
    expect(row.isCrossPeriod).toBe(true)
    expect(row.conclusion).toBe('跨期漏记')
    expect(row.side).toBe('before')
    expect(api.backwardCrossPeriodAmount.value).toBe(8000)
  })

  it('同侧日期即使相差多日 → 不跨期', () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31' })
    api.addForwardRow({
      recordDate: '2025-12-28',
      documentDate: '2025-12-20',
      amount: 5000,
      documentAmount: 5000,
    })
    expect(api.forwardRows.value[0].isCrossPeriod).toBe(false)
    expect(api.forwardRows.value[0].conclusion).toBe('正常')
    expect(api.forwardRows.value[0].crossPeriodAmount).toBe(0)
  })

  it('save(forward) 仅持久化 I2-13 行与样本标准', async () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31', daysBefore: 7, amountThreshold: 1000 })
    api.addForwardRow({ recordDate: '2025-12-30', amount: 1, documentDate: '2025-12-30' })
    await api.save('forward')

    expect(saveResponses).toHaveBeenCalledTimes(1)
    expect(saveResponses.mock.calls[0][0]).toBe('I2-13')
    const payload = saveResponses.mock.calls[0][1]
    expect(payload['I2-13-rows']).toHaveLength(1)
    expect(payload['I2-13-sample-criteria']).toMatchObject({
      cutoffDate: '2025-12-31',
      daysBefore: 7,
      amountThreshold: 1000,
    })
  })

  it('从 allResponses 恢复旧数据并重算跨期', () => {
    allResponses.value = new Map([
      [
        'I2-13-sample-criteria',
        { remark: JSON.stringify({ cutoffDate: '2025-12-31', daysBefore: 5, daysAfter: 5, amountThreshold: 0, firstYearClient: false }) },
      ],
      [
        'I2-13-rows',
        {
          remark: JSON.stringify([
            {
              recordDate: '2025-12-30',
              voucherNo: 'V1',
              amount: 2000,
              description: '研发材料',
              documentNo: 'D1',
              documentDate: '2026-01-02',
              documentAmount: 2000,
            },
          ]),
        },
      ],
    ])
    const api = setup()
    expect(api.forwardRows.value).toHaveLength(1)
    expect(api.forwardRows.value[0].isCrossPeriod).toBe(true)
    expect(api.forwardCriteria.value.cutoffDate).toBe('2025-12-31')
  })
})
