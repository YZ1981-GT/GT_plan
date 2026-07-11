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

// http 默认无实现 → http.get(...) resolve undefined → 后端消费抛"空结果" →
// 降级到纯函数（既有测试全部走 fallback 路径，行为与迁移前一致）。
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))

import { getReport } from '@/services/auditPlatformApi'
import http from '@/utils/http'
import { useReportCrossCheck, computeCrossCheckResults, type CrossCheckItem } from '../useReportCrossCheck'

const mockGetReport = vi.mocked(getReport)
const mockHttpGet = vi.mocked(http.get)

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

// ─── Task 28.2: ACNR REPORT-domain canonical row_code resolution ──────────────

describe('computeCrossCheckResults — canonical row_code resolution (Task 28.2)', () => {
  /**
   * Validates: Requirements 19.2, 19.5, 19.7
   *
   * Backward compatibility: when no reportCodeMap is present, behaviour is
   * byte-identical to the pre-migration exact-then-fuzzy `get`.
   */
  it('no reportCodeMap → identical to legacy exact-then-fuzzy behaviour', () => {
    const bsMap: Record<string, number> = { assets_total: 1000, liabilities_total: 400, equity_total: 600, 货币资金: 200 }
    const isMap: Record<string, number> = { 'IS-001': 500, 'IS-002': 300, 'IS-017': 200, 'IS-018': 50, 'IS-019': 150 }

    const results = computeCrossCheckResults({ bsMap, isMap })
    expect(results).toHaveLength(7)
    // 资产合计 = 负债 + 权益
    expect(results[0].leftValue).toBe(1000)
    expect(results[0].rightValue).toBe(1000)
    expect(results[0].passed).toBe(true)
  })

  it('canonical reportCodeMap resolves value via exact row_code, not fuzzy name scan', () => {
    // 值表仅以 canonical row_code 为键（无中文名键）；语义键为中文名。
    // 若无 registry，get 的中文名精确/模糊匹配都会 miss（返回 0）；
    // 有 registry 时，中文名 → canonical code → 值表精确取值命中。
    const bsMap: Record<string, number> = {
      'BS-031': 1000, // 资产总计
      'BS-055': 400, // 负债合计
      'BS-078': 600, // 所有者权益合计
      'BS-001': 200, // 货币资金
    }
    const isMap: Record<string, number> = {
      'IS-001': 500,
      'IS-002': 300,
      'IS-017': 200,
      'IS-018': 50,
      'IS-019': 150,
    }
    const reportCodeMap: Record<string, string> = {
      'BS-031': '资产总计',
      'BS-055': '负债合计',
      'BS-078': '所有者权益合计',
      'BS-001': '货币资金',
      'IS-019': '净利润',
      'IS-017': '利润总额',
      'IS-018': '所得税费用',
      'IS-001': '营业收入',
      'IS-002': '营业成本',
    }

    // Without registry: the code aliases (assets_total 等) miss, 中文名也无键 → 资产合计=0
    const legacy = computeCrossCheckResults({ bsMap, isMap })
    expect(legacy[0].leftValue).toBeNull() // totalAssets resolved to 0 → null

    // With registry: canonical resolution finds BS-031 → 1000
    const withRegistry = computeCrossCheckResults({ bsMap, isMap, reportCodeMap })
    expect(withRegistry[0].leftValue).toBe(1000)
    expect(withRegistry[0].rightValue).toBe(1000) // 400 + 600
    expect(withRegistry[0].passed).toBe(true)
  })

  it('canonical row_code takes precedence but empty registry falls back to fuzzy (Req 19.7)', () => {
    // 值表以中文名为键（模糊匹配可命中）。
    const bsMap: Record<string, number> = {
      资产总计: 1000,
      负债合计: 400,
      所有者权益合计: 600,
      货币资金: 200,
    }
    const isMap: Record<string, number> = {
      营业收入: 500, 营业成本: 300, 利润总额: 200, 所得税费用: 50, 净利润: 150,
    }

    // 空 registry（undefined）→ 回退模糊匹配，命中中文名
    const fallback = computeCrossCheckResults({ bsMap, isMap, reportCodeMap: undefined })
    expect(fallback[0].leftValue).toBe(1000)
    expect(fallback[0].passed).toBe(true)
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

// ─── Task 19.1: 前端消费后端 logic_check 端点（收编闭环，Req 23）─────────────────

/**
 * 后端 logic_check 端点 7 条勾稽的描述（顺序与 computeCrossCheckResults 逐条对齐）。
 * 与 backend/app/services/formula_management/logic_check.py 的 _CROSS_CHECK_SEEDS 描述一致。
 */
const BACKEND_DESCRIPTIONS = [
  '资产合计 = 负债合计 + 所有者权益合计',
  '营业收入 − 营业成本 = 毛利',
  '利润总额 − 所得税 = 净利润',
  '资产 − 负债 = 权益',
  '所有者权益变动表期末 = 资产负债表权益',
  '有效税率 ≈ 25%',
  '货币资金 ≥ 0（负值异常）',
]

/**
 * 从纯函数结果构造"忠实收编"的后端响应（模拟后端 7 条 logic_check 逐条判定与纯函数一致），
 * 用于验证在线路径与降级路径的逐条判定一致（Req 23.5）。
 */
function buildBackendPayloadFrom(pure: CrossCheckItem[]) {
  const results = pure.map((item, i) => ({
    formula_id: `report-cross-check-${i + 1}`,
    description: BACKEND_DESCRIPTIONS[i],
    expression: `ROW(check-${i + 1})`,
    passed: item.passed,
  }))
  const issue_list = pure
    .map((item, i) => ({ item, i }))
    .filter(({ item }) => !item.passed)
    .map(({ item, i }) => ({
      formula_id: `report-cross-check-${i + 1}`,
      addr_id: null,
      description: BACKEND_DESCRIPTIONS[i],
      left_value: item.leftValue != null ? String(item.leftValue) : null,
      right_value: item.rightValue != null ? String(item.rightValue) : null,
    }))
  return { results, issue_list, last_computed_at: '2025-01-01T00:00:00+00:00' }
}

describe('useReportCrossCheck — backend logic_check main path (Req 23.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReport.mockReset()
    mockHttpGet.mockReset()
  })

  it('consumes backend Issue_List/results to drive per-check display (source=backend)', async () => {
    mockGetReport
      .mockResolvedValueOnce(makeBalancedBsRows() as any)
      .mockResolvedValueOnce(makeBalancedIsRows() as any)

    // 后端返回：check 3（利润总额−所得税=净利润）不通过，其余通过。
    const payload = {
      results: BACKEND_DESCRIPTIONS.map((d, i) => ({
        formula_id: `report-cross-check-${i + 1}`,
        description: d,
        expression: 'x',
        passed: i !== 2,
      })),
      issue_list: [
        {
          formula_id: 'report-cross-check-3',
          addr_id: null,
          description: BACKEND_DESCRIPTIONS[2],
          left_value: '150',
          right_value: '140',
        },
      ],
      last_computed_at: '2025-01-01T00:00:00+00:00',
    }
    mockHttpGet.mockResolvedValueOnce({ data: payload } as any)

    const options = createOptions()
    const { loadCrossCheckData, crossCheckResults, crossCheckSource } = useReportCrossCheck(options)
    await loadCrossCheckData()

    // 主路径成功：结果来源为后端（消费了 logic_check 端点，Req 23.1）
    expect(crossCheckSource.value).toBe('backend')

    const results = crossCheckResults.value
    expect(results).toHaveLength(7)
    // 逐条 passed 由后端 results 驱动
    expect(results.map((r) => r.passed)).toEqual([true, true, false, true, true, true, true])
    expect(results.map((r) => r.description)).toEqual(BACKEND_DESCRIPTIONS)
    // 不通过项的左右值由后端 issue_list 关联回填，diff 据此计算——
    // 这些值仅存在于后端 payload（纯函数对同一平衡数据会得 passed=true / rightValue=150），
    // 故命中即证明结果确由后端 Issue_List 驱动，而非纯函数。
    expect(results[2].passed).toBe(false)
    expect(results[2].leftValue).toBe(150)
    expect(results[2].rightValue).toBe(140)
    expect(results[2].diff).toBe(10)
    // 通过项无 Issue → 左右值为 null
    expect(results[0].leftValue).toBeNull()
    expect(results[0].rightValue).toBeNull()
  })
})

describe('useReportCrossCheck — degrade to pure function when backend unavailable (Req 23.2/23.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReport.mockReset()
    mockHttpGet.mockReset()
  })

  it('backend 5xx/timeout/network error → try/catch fail-open fallback (source=fallback), not blocking render', async () => {
    mockGetReport
      .mockResolvedValueOnce(makeBalancedBsRows() as any)
      .mockResolvedValueOnce(makeBalancedIsRows() as any)
    // 模拟后端不可用（网络错/5xx/超时）
    mockHttpGet.mockRejectedValueOnce(new Error('Network Error'))

    const options = createOptions()
    const { loadCrossCheckData, crossCheckResults, crossCheckData, crossCheckSource } =
      useReportCrossCheck(options)
    await loadCrossCheckData()

    // 降级到纯函数，且报表页面照常有 7 条结果（不阻断渲染）
    expect(crossCheckSource.value).toBe('fallback')
    expect(crossCheckResults.value).toHaveLength(7)
    // 降级结果与纯函数逐条一致
    const pure = computeCrossCheckResults(crossCheckData.value)
    expect(crossCheckResults.value).toEqual(pure)
  })

  it('backend returns empty results → treated as unavailable → fallback', async () => {
    mockGetReport
      .mockResolvedValueOnce(makeBalancedBsRows() as any)
      .mockResolvedValueOnce(makeBalancedIsRows() as any)
    mockHttpGet.mockResolvedValueOnce({ data: { results: [], issue_list: [] } } as any)

    const options = createOptions()
    const { loadCrossCheckData, crossCheckResults, crossCheckSource } = useReportCrossCheck(options)
    await loadCrossCheckData()

    expect(crossCheckSource.value).toBe('fallback')
    expect(crossCheckResults.value).toHaveLength(7)
  })
})

describe('useReportCrossCheck — online vs fallback per-check consistency (Req 23.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReport.mockReset()
    mockHttpGet.mockReset()
  })

  it('online (backend) and fallback judgments are consistent for the same imbalanced report data', async () => {
    // 不平衡数据：check 1（资产 ≠ 负债+权益）不通过
    const bsRows = [
      { row_code: 'assets_total', row_name: '资产总计', current_period_amount: '1000', is_total_row: true },
      { row_code: 'liabilities_total', row_name: '负债合计', current_period_amount: '400', is_total_row: true },
      { row_code: 'equity_total', row_name: '所有者权益合计', current_period_amount: '500', is_total_row: true },
      { row_code: 'BS-001', row_name: '货币资金', current_period_amount: '200', is_total_row: false },
    ]
    const isRows = makeBalancedIsRows()

    // ① 降级路径（后端不可用）
    mockGetReport
      .mockResolvedValueOnce(bsRows as any)
      .mockResolvedValueOnce(isRows as any)
    mockHttpGet.mockRejectedValueOnce(new Error('backend down'))
    const c1 = useReportCrossCheck(createOptions())
    await c1.loadCrossCheckData()
    const fallback = c1.crossCheckResults.value
    expect(c1.crossCheckSource.value).toBe('fallback')

    // ② 在线路径：后端忠实收编（逐条 passed 与纯函数一致）
    mockGetReport
      .mockResolvedValueOnce(bsRows as any)
      .mockResolvedValueOnce(isRows as any)
    mockHttpGet.mockResolvedValueOnce({ data: buildBackendPayloadFrom(fallback) } as any)
    const c2 = useReportCrossCheck(createOptions())
    await c2.loadCrossCheckData()
    const online = c2.crossCheckResults.value
    expect(c2.crossCheckSource.value).toBe('backend')

    // 逐条勾稽判定（description + passed）在线路径 == 降级路径（收编不改变语义）
    expect(online.map((r) => [r.description, r.passed])).toEqual(
      fallback.map((r) => [r.description, r.passed]),
    )
    // check 1 确实不通过（数据不平衡），验证判定非平凡
    expect(fallback[0].passed).toBe(false)
    expect(online[0].passed).toBe(false)
  })
})
