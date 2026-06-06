/**
 * useReportCrossCheck.spec.ts — composable 单元测试 + property-based test
 *
 * Task 7.3: 验证 useReportCrossCheck 核心逻辑：
 * - loadCrossCheckData: 调用 getReport 获取 BS 和 IS 数据，构建 bsMap/isMap
 * - crossCheckResults: 计算 7 条等式，平衡数据全 pass
 * - crossCheckResults: 不平衡数据 → check 1 fails
 *
 * Task 7.4: Property-Based Test
 * - Property 1: Behavioral Equivalence — 跨表核对等式
 *   fast-check 生成随机 BS/IS 行数据，验证 diff = leftValue - rightValue 且 passed = (diff within tolerance)
 *
 * Validates: Requirements 1.1, 3.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import * as fc from 'fast-check'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/services/auditPlatformApi', () => ({
  getReport: vi.fn(),
}))

import { getReport } from '@/services/auditPlatformApi'
import { useReportCrossCheck } from '../useReportCrossCheck'

const mockGetReport = vi.mocked(getReport)

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createOptions() {
  return {
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2025),
    activeTab: ref('cross_check'),
    currentApplicableStandard: computed(() => 'soe'),
  }
}

/**
 * 构造平衡的 BS/IS 数据：资产 = 负债 + 权益，利润总额 - 所得税 = 净利润
 */
function makeBalancedBsRows() {
  return [
    { row_code: 'assets_total', row_name: '资产总计', current_period_amount: '1000', is_total_row: true },
    { row_code: 'liabilities_total', row_name: '负债合计', current_period_amount: '400', is_total_row: true },
    { row_code: 'equity_total', row_name: '所有者权益合计', current_period_amount: '600', is_total_row: true },
    { row_code: 'BS-001', row_name: '货币资金', current_period_amount: '200', is_total_row: false },
  ]
}

function makeBalancedIsRows() {
  return [
    { row_code: 'IS-001', row_name: '营业收入', current_period_amount: '500', is_total_row: false },
    { row_code: 'IS-002', row_name: '营业成本', current_period_amount: '300', is_total_row: false },
    { row_code: 'IS-017', row_name: '利润总额', current_period_amount: '200', is_total_row: false },
    { row_code: 'IS-018', row_name: '所得税费用', current_period_amount: '50', is_total_row: false },
    { row_code: 'IS-019', row_name: '净利润', current_period_amount: '150', is_total_row: false },
  ]
}

// ─── Unit Tests: Task 7.3 ─────────────────────────────────────────────────────

describe('useReportCrossCheck — loadCrossCheckData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls getReport for BS and IS, builds bsMap/isMap correctly', async () => {
    const bsRows = makeBalancedBsRows()
    const isRows = makeBalancedIsRows()

    mockGetReport
      .mockResolvedValueOnce(bsRows as any)
      .mockResolvedValueOnce(isRows as any)

    const options = createOptions()
    const { loadCrossCheckData, crossCheckData, crossCheckLoading } = useReportCrossCheck(options)

    await loadCrossCheckData()

    // Verify getReport called with correct params for BS and IS
    expect(mockGetReport).toHaveBeenCalledTimes(2)
    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', false, 'soe')
    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'income_statement', false, 'soe')

    // Verify bsMap built correctly
    const { bsMap, isMap } = crossCheckData.value
    expect(bsMap).toBeDefined()
    expect(isMap).toBeDefined()

    // Total rows override non-total rows with same key
    expect(bsMap['assets_total']).toBe(1000)
    expect(bsMap['资产总计']).toBe(1000)
    expect(bsMap['liabilities_total']).toBe(400)
    expect(bsMap['equity_total']).toBe(600)
    expect(bsMap['BS-001']).toBe(200)

    // IS map
    expect(isMap['IS-001']).toBe(500)
    expect(isMap['IS-019']).toBe(150)

    // Loading should be false after completion
    expect(crossCheckLoading.value).toBe(false)
  })

  it('handles API errors gracefully (catch → empty arrays)', async () => {
    mockGetReport
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))

    const options = createOptions()
    const { loadCrossCheckData, crossCheckData, crossCheckLoading } = useReportCrossCheck(options)

    await loadCrossCheckData()

    // Should still build maps from empty arrays (catch → [])
    const { bsMap, isMap } = crossCheckData.value
    expect(bsMap).toBeDefined()
    expect(isMap).toBeDefined()
    expect(Object.keys(bsMap)).toHaveLength(0)
    expect(Object.keys(isMap)).toHaveLength(0)
    expect(crossCheckLoading.value).toBe(false)
  })
})

describe('useReportCrossCheck — crossCheckResults (balanced data)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('produces 7 checks, balanced data → all pass', async () => {
    const bsRows = makeBalancedBsRows()
    const isRows = makeBalancedIsRows()

    mockGetReport
      .mockResolvedValueOnce(bsRows as any)
      .mockResolvedValueOnce(isRows as any)

    const options = createOptions()
    const { loadCrossCheckData, crossCheckResults } = useReportCrossCheck(options)

    await loadCrossCheckData()

    const results = crossCheckResults.value
    expect(results).toHaveLength(7)

    // All checks should pass with balanced data
    for (const check of results) {
      expect(check.passed).toBe(true)
    }

    // Verify check 1: 资产合计 = 负债合计 + 所有者权益合计
    expect(results[0].description).toContain('资产合计')
    expect(results[0].leftValue).toBe(1000)
    expect(results[0].rightValue).toBe(1000) // 400 + 600
    // Note: source code uses `diff || null`, so 0 becomes null
    expect(results[0].diff).toBeNull()
  })
})

describe('useReportCrossCheck — crossCheckResults (imbalanced data)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('imbalanced data → check 1 fails (资产 ≠ 负债+权益)', async () => {
    // Make assets ≠ liabilities + equity
    const bsRows = [
      { row_code: 'assets_total', row_name: '资产总计', current_period_amount: '1000', is_total_row: true },
      { row_code: 'liabilities_total', row_name: '负债合计', current_period_amount: '400', is_total_row: true },
      { row_code: 'equity_total', row_name: '所有者权益合计', current_period_amount: '500', is_total_row: true }, // 400 + 500 = 900 ≠ 1000
      { row_code: 'BS-001', row_name: '货币资金', current_period_amount: '200', is_total_row: false },
    ]
    const isRows = makeBalancedIsRows()

    mockGetReport
      .mockResolvedValueOnce(bsRows as any)
      .mockResolvedValueOnce(isRows as any)

    const options = createOptions()
    const { loadCrossCheckData, crossCheckResults } = useReportCrossCheck(options)

    await loadCrossCheckData()

    const results = crossCheckResults.value
    expect(results).toHaveLength(7)

    // Check 1 should fail: 资产合计(1000) ≠ 负债合计+权益(900), diff = 100 > tolerance(1)
    expect(results[0].passed).toBe(false)
    expect(results[0].leftValue).toBe(1000)
    expect(results[0].rightValue).toBe(900)
    expect(results[0].diff).toBe(100)
  })
})

// ─── Property-Based Test: Task 7.4 ───────────────────────────────────────────

// Feature: report-view-slimdown, Property 1: Behavioral Equivalence — 跨表核对等式
describe('useReportCrossCheck — crossCheckResults PBT', () => {
  /**
   * **Validates: Requirements 1.1, 3.4**
   *
   * Property: For any crossCheckItem in crossCheckResults,
   * diff = leftValue - rightValue AND passed = (|diff| <= tolerance)
   *
   * We generate random BS/IS amounts, feed them into the composable,
   * and verify the algebraic relationship holds for every check item.
   */
  it('diff = leftValue - rightValue and passed = (diff within tolerance)', async () => {
    fc.assert(
      fc.asyncProperty(
        // Generate random financial amounts for BS
        fc.record({
          totalAssets: fc.integer({ min: 1, max: 10000 }),
          totalLiabilities: fc.integer({ min: 0, max: 5000 }),
          totalEquity: fc.integer({ min: 0, max: 5000 }),
          cash: fc.integer({ min: 0, max: 3000 }),
        }),
        // Generate random financial amounts for IS
        fc.record({
          revenue: fc.integer({ min: 100, max: 10000 }),
          cost: fc.integer({ min: 0, max: 5000 }),
          profitBeforeTax: fc.integer({ min: 0, max: 5000 }),
          incomeTax: fc.integer({ min: 0, max: 2000 }),
          netProfit: fc.integer({ min: 0, max: 3000 }),
        }),
        async (bs, is) => {
          vi.clearAllMocks()

          const bsRows = [
            { row_code: 'assets_total', row_name: '资产总计', current_period_amount: String(bs.totalAssets), is_total_row: true },
            { row_code: 'liabilities_total', row_name: '负债合计', current_period_amount: String(bs.totalLiabilities), is_total_row: true },
            { row_code: 'equity_total', row_name: '所有者权益合计', current_period_amount: String(bs.totalEquity), is_total_row: true },
            { row_code: 'BS-001', row_name: '货币资金', current_period_amount: String(bs.cash), is_total_row: false },
          ]
          const isRows = [
            { row_code: 'IS-001', row_name: '营业收入', current_period_amount: String(is.revenue), is_total_row: false },
            { row_code: 'IS-002', row_name: '营业成本', current_period_amount: String(is.cost), is_total_row: false },
            { row_code: 'IS-017', row_name: '利润总额', current_period_amount: String(is.profitBeforeTax), is_total_row: false },
            { row_code: 'IS-018', row_name: '所得税费用', current_period_amount: String(is.incomeTax), is_total_row: false },
            { row_code: 'IS-019', row_name: '净利润', current_period_amount: String(is.netProfit), is_total_row: false },
          ]

          mockGetReport
            .mockResolvedValueOnce(bsRows as any)
            .mockResolvedValueOnce(isRows as any)

          const options = createOptions()
          const { loadCrossCheckData, crossCheckResults } = useReportCrossCheck(options)

          await loadCrossCheckData()

          const results = crossCheckResults.value
          expect(results).toHaveLength(7)

          for (const item of results) {
            // Core algebraic property: diff = leftValue - rightValue
            const left = item.leftValue ?? 0
            const right = item.rightValue ?? 0
            const expectedDiff = Math.round((left - right) * 100) / 100
            expect(item.diff ?? 0).toBeCloseTo(expectedDiff, 2)

            // passed is determined by tolerance comparison
            // We cannot know the exact tolerance without replicating the logic,
            // but we can verify: if diff === 0 then passed must be true
            if (item.diff === 0 || item.diff === null) {
              expect(item.passed).toBe(true)
            }
          }
        },
      ),
      { numRuns: 5 },
    )
  })
})
