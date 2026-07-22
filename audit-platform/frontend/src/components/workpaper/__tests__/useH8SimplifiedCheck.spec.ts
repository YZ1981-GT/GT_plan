/**
 * useH8SimplifiedCheck unit tests
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useH8SimplifiedCheck } from '../composables/useH8SimplifiedCheck'

const Y = '\u662f'
const N = '\u5426'

function mockMap(data: Record<string, unknown>) {
  const map = new Map<string, any>()
  for (const [k, v] of Object.entries(data)) {
    map.set(k, { remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return map
}

describe('useH8SimplifiedCheck', () => {
  it('short + low value auto classify', async () => {
    const allResponses = ref(mockMap({
      'H8-13-rows': [{
        rowId: 'r1',
        contractNo: 'L-001',
        leaseTermMonths: 6,
        newAssetValue: 20000,
        monthlyRent: 1000,
        accrualMonths: 6,
        bookExpense: 5500,
      }],
    }))
    const { rows, simplifiedCount, mustRecognizeCount, totalDifference } = useH8SimplifiedCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: vi.fn(),
    })
    await nextTick()
    expect(rows.value[0].isShortTerm).toBe(true)
    expect(rows.value[0].isLowValue).toBe(true)
    expect(rows.value[0].simplifiedType).toBe('\u77ed\u671f+\u4f4e\u4ef7\u503c')
    expect(rows.value[0].expectedExpense).toBe(6000)
    expect(rows.value[0].difference).toBe(500)
    expect(simplifiedCount.value).toBe(1)
    expect(mustRecognizeCount.value).toBe(0)
    expect(totalDifference.value).toBe(500)
  })

  it('non-qualifying -> recognize ROU', async () => {
    const allResponses = ref(mockMap({
      'H8-13-rows': [{
        rowId: 'r2',
        contractNo: 'L-002',
        leaseTermMonths: 24,
        newAssetValue: 80000,
        monthlyRent: 5000,
        accrualMonths: 12,
        bookExpense: 60000,
      }],
    }))
    const { rows, mustRecognizeCount, updateCell } = useH8SimplifiedCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: vi.fn(),
    })
    await nextTick()
    expect(rows.value[0].simplifiedType).toBe('\u4e0d\u7b26\u5408')
    expect(mustRecognizeCount.value).toBe(1)
    updateCell('r2', 'bookExpense', 58000)
    expect(rows.value[0].difference).toBe(2000)
  })

  it('legacy annualRental / expenseAmount', async () => {
    const allResponses = ref(mockMap({
      'H8-13-rows': [{
        rowId: 'r3',
        contractNo: 'L-003',
        leaseTermMonths: 10,
        newAssetValue: 30000,
        annualRental: 12000,
        expenseAmount: 10000,
      }],
    }))
    const { rows } = useH8SimplifiedCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: vi.fn(),
    })
    await nextTick()
    expect(rows.value[0].monthlyRent).toBe(1000)
    expect(rows.value[0].bookExpense).toBe(10000)
    expect(rows.value[0].simplifiedType).toBe('\u77ed\u671f+\u4f4e\u4ef7\u503c')
  })

  it('syncFromH85 upserts short-term and skips purchase/long', async () => {
    const allResponses = ref(mockMap({
      'H8-13-rows': [{
        rowId: 'r1',
        contractNo: 'ST-OLD',
        leaseTermMonths: 6,
        newAssetValue: 0,
      }],
      'H8-5-records': [
        {
          recordId: 'a',
          contractNo: 'ST-OLD',
          determinedLeaseTermMonths: 9,
          purchaseReasonablyCertain: N,
          conclusion: Y,
        },
        {
          recordId: 'b',
          contractNo: 'ST-NEW',
          determinedLeaseTermMonths: 8,
          purchaseReasonablyCertain: '',
          conclusion: Y,
        },
        {
          recordId: 'c',
          contractNo: 'BUY',
          determinedLeaseTermMonths: 10,
          purchaseReasonablyCertain: Y,
          conclusion: Y,
        },
        {
          recordId: 'd',
          contractNo: 'LONG',
          determinedLeaseTermMonths: 36,
          conclusion: Y,
        },
      ],
    }))
    const api = useH8SimplifiedCheck({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: vi.fn(),
    })
    await nextTick()
    expect(api.h85ShortTermCandidates.value.map(c => c.contractNo).sort()).toEqual(['ST-NEW', 'ST-OLD'])
    expect(api.h85ShortTermMissing.value.map(c => c.contractNo)).toEqual(['ST-NEW'])
    expect(api.h85LeaseTermMismatches.value).toHaveLength(1)
    const r = api.syncFromH85({ addMissing: true, onlyShortTerm: true })
    expect(r.ok).toBe(true)
    expect(r.updated).toBe(1)
    expect(r.added).toBe(1)
    expect(api.rows.value.find(x => x.contractNo === 'ST-OLD')?.leaseTermMonths).toBe(9)
    expect(api.rows.value.find(x => x.contractNo === 'ST-NEW')?.leaseTermMonths).toBe(8)
    expect(api.rows.value.find(x => x.contractNo === 'BUY')).toBeUndefined()
    expect(api.h85LeaseTermMismatches.value).toHaveLength(0)
  })
})
