import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  extractG7_14ClosingRows,
  buildEquityPullDiff,
  applyEquityPullToDetail,
  pullG7_14ForDetail,
  type G7EquityClosingRow,
} from '../g7EquityMethodPullToDetail'
import { createG7EquityRow, recalcG7EquityRow, type G7DetailState } from '../g7DetailModel'

// http mock（pullG7_14ForDetail 走 ACNR resolve-instance；缺源返回空集合 Property 10）
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))
import http from '@/utils/http'

function emptyState(): G7DetailState {
  return { costRows: [], equityRows: [], impairmentRows: [] }
}

describe('extractG7_14ClosingRows', () => {
  it('maps closing + movement components and drops all-zero rows', () => {
    const payload = {
      rows: [
        {
          investeeName: '甲联营公司',
          openingBalance: 100,
          equityShare: 30,
          ociShare: 5,
          otherEquityShare: 2,
          dividendDistributed: 10,
          closingBalance: 127,
        },
        { investeeName: '空行公司' }, // 全零 → 跳过
      ],
    }
    const rows = extractG7_14ClosingRows(payload)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      investeeName: '甲联营公司',
      opening: 100,
      profitLoss: 30,
      oci: 5,
      otherEquity: 2,
      dividend: 10,
      closingAmount: 127,
    })
  })

  it('dedups by normalized investee name (first wins)', () => {
    const payload = {
      rows: [
        { investeeName: ' 乙公司 ', closingBalance: 50 },
        { investeeName: '乙公司', closingBalance: 999 },
      ],
    }
    const rows = extractG7_14ClosingRows(payload)
    expect(rows).toHaveLength(1)
    expect(rows[0].closingAmount).toBe(50)
  })

  it('returns [] for empty / non-object payload (Property 10)', () => {
    expect(extractG7_14ClosingRows(null)).toEqual([])
    expect(extractG7_14ClosingRows(undefined)).toEqual([])
    expect(extractG7_14ClosingRows({})).toEqual([])
  })
})

describe('buildEquityPullDiff', () => {
  it('matches existing equity rows and computes diff', () => {
    const state = emptyState()
    const row = createG7EquityRow(1, '甲联营公司', 'associate')
    row.openingAmount = 120
    // recalc 后 closingAmount = 120（无其他运动）
    recalcG7EquityRow(row)
    state.equityRows.push(row)

    const src: G7EquityClosingRow[] = [
      { investeeName: '甲联营公司', closingAmount: 100, opening: 100, profitLoss: 0, oci: 0, otherEquity: 0, dividend: 0 },
      { investeeName: '新公司', closingAmount: 50, opening: 50, profitLoss: 0, oci: 0, otherEquity: 0, dividend: 0 },
    ]
    const diffs = buildEquityPullDiff(state, src)
    expect(diffs).toHaveLength(2)
    const matched = diffs.find(d => d.investeeName === '甲联营公司')!
    expect(matched.matched).toBe(true)
    expect(matched.current).toBe(120)
    expect(matched.incoming).toBe(100)
    expect(matched.diff).toBe(20)
    const unmatched = diffs.find(d => d.investeeName === '新公司')!
    expect(unmatched.matched).toBe(false)
    expect(unmatched.current).toBe(0)
  })
})

describe('applyEquityPullToDetail (Persist_First)', () => {
  const src: G7EquityClosingRow[] = [
    { investeeName: '甲', closingAmount: 130, opening: 100, profitLoss: 20, oci: 5, otherEquity: 3, dividend: 8 },
    { investeeName: '乙', closingAmount: 200, opening: 200, profitLoss: 0, oci: 0, otherEquity: 0, dividend: 0 },
  ]

  it('creates rows for unmatched investees', () => {
    const state = emptyState()
    const res = applyEquityPullToDetail(state, src, { overwrite: false })
    expect(res.added).toBe(2)
    expect(res.filled).toBe(0)
    expect(state.equityRows).toHaveLength(2)
    const jia = state.equityRows.find(r => r.investeeName === '甲')!
    expect(jia.openingAmount).toBe(100)
    expect(jia.profitLossAdjustment).toBe(20)
    expect(jia.dividendReceived).toBe(8)
    // recalc 派生期末 = 100 + 20 + 5 + 3 - 8 = 120
    expect(jia.closingAmount).toBe(120)
  })

  it('only fills empty rows; does not touch existing values (overwrite=false)', () => {
    const state = emptyState()
    const existing = createG7EquityRow(1, '甲', 'joint_venture')
    existing.openingAmount = 999
    state.equityRows.push(existing)
    const res = applyEquityPullToDetail(state, src, { overwrite: false })
    // 甲 已有值 → skipped；乙 新建 → added
    expect(res.skipped).toBe(1)
    expect(res.added).toBe(1)
    expect(res.filled).toBe(0)
    expect(state.equityRows.find(r => r.investeeName === '甲')!.openingAmount).toBe(999)
  })

  it('overwrite=true fills matched rows', () => {
    const state = emptyState()
    const existing = createG7EquityRow(1, '甲', 'joint_venture')
    existing.openingAmount = 999
    state.equityRows.push(existing)
    const res = applyEquityPullToDetail(state, src, { overwrite: true })
    expect(res.filled).toBe(1)
    expect(res.added).toBe(1)
    expect(state.equityRows.find(r => r.investeeName === '甲')!.openingAmount).toBe(100)
  })

  it('is idempotent when applied twice (Property 4)', () => {
    const state = emptyState()
    const first = applyEquityPullToDetail(state, src, { overwrite: false })
    expect(first.added).toBe(2)
    const beforeLen = state.equityRows.length
    const snapshot = state.equityRows.map(r => ({ ...r }))
    const second = applyEquityPullToDetail(state, src, { overwrite: false })
    // 第二次全部命中已填行 → skipped，不新增行、字段不变
    expect(second.added).toBe(0)
    expect(second.filled).toBe(0)
    expect(second.skipped).toBe(2)
    expect(state.equityRows).toHaveLength(beforeLen)
    state.equityRows.forEach((r, i) => {
      expect(r.openingAmount).toBe(snapshot[i].openingAmount)
      expect(r.closingAmount).toBe(snapshot[i].closingAmount)
    })
  })
})

describe('pullG7_14ForDetail (Cross_Book_Pull 缺源安全, Property 10)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns [] when projectId missing', async () => {
    const rows = await pullG7_14ForDetail('')
    expect(rows).toEqual([])
    expect(http.get).not.toHaveBeenCalled()
  })

  it('returns [] when resolve-instance never resolves a wp_id', async () => {
    ;(http.get as any).mockResolvedValue({ data: { data: {} } })
    const rows = await pullG7_14ForDetail('proj-1')
    expect(rows).toEqual([])
  })

  it('does not throw when resolve-instance rejects', async () => {
    ;(http.get as any).mockRejectedValue(new Error('network'))
    const rows = await pullG7_14ForDetail('proj-1')
    expect(rows).toEqual([])
  })
})
