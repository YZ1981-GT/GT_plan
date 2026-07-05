/**
 * Unit tests for useG2Detail composable
 * Validates: Requirements 5.1~5.8
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG2Detail, type InterestDetailRow } from '../useG2Detail'

// Mock onBeforeUnmount since we're not in a component lifecycle
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onBeforeUnmount: vi.fn(),
  }
})

function createOptions(storedRows: any[] = []) {
  const allResponses = ref(new Map<string, any>())
  if (storedRows.length > 0) {
    allResponses.value.set('G2-2-detail-rows', {
      item_id: 'G2-2-detail-rows',
      conclusion: null,
      remark: JSON.stringify(storedRows),
    })
  }
  return {
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  }
}

function createStoredRow(overrides: Partial<any> = {}) {
  return {
    id: `test-${Math.random().toString(36).slice(2, 6)}`,
    seq: 1,
    investTarget: '某债券',
    investType: '债权投资',
    faceValue: 1000000,
    couponRate: 5,
    accrualStart: '2025-01-01',
    accrualEnd: '2025-07-01',
    receivedInterest: 0,
    bookValue: 0,
    eclStage: 'Stage1' as const,
    remark: '',
    indexRef: '',
    ...overrides,
  }
}

describe('useG2Detail', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('formula chain', () => {
    it('计息天数=截止日-起始日', () => {
      const row = createStoredRow({
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',  // 90 days
      })
      const opts = createOptions([row])
      const { dataRows } = useG2Detail(opts)
      // Jan 1 → Apr 1 = 90 days
      expect(dataRows.value[0].accruedDays).toBe(90)
    })

    it('应计利息=面值×利率/100×天数/365', () => {
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',  // 90 days
      })
      const opts = createOptions([row])
      const { dataRows } = useG2Detail(opts)
      // 1000000 × 5/100 × 90/365 = 12328.767...
      const expected = (1000000 * 5 / 100 * 90) / 365
      expect(dataRows.value[0].accruedInterest).toBeCloseTo(expected, 2)
    })

    it('期末应收=应计利息-已收利息', () => {
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        receivedInterest: 5000,
      })
      const opts = createOptions([row])
      const { dataRows } = useG2Detail(opts)
      const expectedInterest = (1000000 * 5 / 100 * 90) / 365
      const expectedNet = expectedInterest - 5000
      expect(dataRows.value[0].netReceivable).toBeCloseTo(expectedNet, 2)
    })

    it('差异=期末应收-企业账面值', () => {
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        receivedInterest: 0,
        bookValue: 12000,
      })
      const opts = createOptions([row])
      const { dataRows } = useG2Detail(opts)
      const expectedInterest = (1000000 * 5 / 100 * 90) / 365
      const expectedVariance = expectedInterest - 12000
      expect(dataRows.value[0].variance).toBeCloseTo(expectedVariance, 2)
    })
  })

  describe('isVarianceWarning', () => {
    it('|差异|>100 → true (橙色标记)', () => {
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        bookValue: 0, // variance will be >100
      })
      const opts = createOptions([row])
      const { dataRows, isVarianceWarning } = useG2Detail(opts)
      expect(isVarianceWarning(dataRows.value[0])).toBe(true)
    })

    it('|差异|≤100 → false', () => {
      const expectedInterest = (1000000 * 5 / 100 * 90) / 365
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        bookValue: expectedInterest - 50, // variance = 50 ≤ 100
      })
      const opts = createOptions([row])
      const { dataRows, isVarianceWarning } = useG2Detail(opts)
      expect(isVarianceWarning(dataRows.value[0])).toBe(false)
    })
  })

  describe('dynamic rows', () => {
    it('addRow adds a new row with sequential number', () => {
      const opts = createOptions([])
      const { dataRows, addRow } = useG2Detail(opts)
      expect(dataRows.value).toHaveLength(0)

      addRow()
      expect(dataRows.value).toHaveLength(1)
      expect(dataRows.value[0].seq).toBe(1)

      addRow()
      expect(dataRows.value).toHaveLength(2)
      expect(dataRows.value[1].seq).toBe(2)
    })

    it('removeRow removes by id and resequences', () => {
      const row1 = createStoredRow({ id: 'row-1', seq: 1 })
      const row2 = createStoredRow({ id: 'row-2', seq: 2 })
      const row3 = createStoredRow({ id: 'row-3', seq: 3 })
      const opts = createOptions([row1, row2, row3])
      const { dataRows, removeRow } = useG2Detail(opts)

      expect(dataRows.value).toHaveLength(3)
      removeRow('row-2')
      expect(dataRows.value).toHaveLength(2)
      expect(dataRows.value[0].seq).toBe(1)
      expect(dataRows.value[1].seq).toBe(2)
    })

    it('readonly mode prevents add/remove', () => {
      const opts = createOptions([createStoredRow({ id: 'row-1' })])
      opts.isReadonly = ref(true)
      const { dataRows, addRow, removeRow } = useG2Detail(opts)

      addRow()
      expect(dataRows.value).toHaveLength(1)

      removeRow('row-1')
      expect(dataRows.value).toHaveLength(1)
    })
  })

  describe('totals', () => {
    it('合计行汇总 faceValue/accruedInterest/netReceivable/variance', () => {
      const row1 = createStoredRow({
        id: 'r1', seq: 1, faceValue: 500000, couponRate: 4,
        accrualStart: '2025-01-01', accrualEnd: '2025-04-01',
        receivedInterest: 1000, bookValue: 3000,
      })
      const row2 = createStoredRow({
        id: 'r2', seq: 2, faceValue: 800000, couponRate: 6,
        accrualStart: '2025-01-01', accrualEnd: '2025-04-01',
        receivedInterest: 2000, bookValue: 10000,
      })
      const opts = createOptions([row1, row2])
      const { totals } = useG2Detail(opts)

      expect(totals.value.faceValue).toBe(1300000)

      const days = 90
      const interest1 = (500000 * 4 / 100 * days) / 365
      const interest2 = (800000 * 6 / 100 * days) / 365
      expect(totals.value.accruedInterest).toBeCloseTo(interest1 + interest2, 2)

      const net1 = interest1 - 1000
      const net2 = interest2 - 2000
      expect(totals.value.netReceivable).toBeCloseTo(net1 + net2, 2)

      const var1 = net1 - 3000
      const var2 = net2 - 10000
      expect(totals.value.variance).toBeCloseTo(var1 + var2, 2)
    })
  })

  describe('updateCell', () => {
    it('updates numeric fields correctly', () => {
      const row = createStoredRow({ id: 'row-1', faceValue: 1000 })
      const opts = createOptions([row])
      const { dataRows, updateCell } = useG2Detail(opts)

      updateCell('row-1', 'faceValue', 2000000)
      expect(dataRows.value[0].faceValue).toBe(2000000)
    })

    it('updates string fields correctly', () => {
      const row = createStoredRow({ id: 'row-1' })
      const opts = createOptions([row])
      const { dataRows, updateCell } = useG2Detail(opts)

      updateCell('row-1', 'investTarget', '国债2025-01')
      expect(dataRows.value[0].investTarget).toBe('国债2025-01')
    })
  })

  describe('persistence', () => {
    it('serializes rows to allResponses remark field', () => {
      const opts = createOptions([])
      const { addRow } = useG2Detail(opts)
      addRow()

      const stored = opts.allResponses.value.get('G2-2-detail-rows')
      expect(stored).toBeDefined()
      expect(stored!.item_id).toBe('G2-2-detail-rows')
      const parsed = JSON.parse(stored!.remark!)
      expect(parsed).toHaveLength(1)
      expect(parsed[0].seq).toBe(1)
    })
  })
})
