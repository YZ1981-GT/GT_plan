/**
 * useReportCrossCheck.p32.spec.ts — 属性测试 P32（前端 logic_check 收编与纯函数降级等价）
 *
 * Feature: formula-management-library, Property 32: 前端 logic_check 收编与纯函数降级等价 —
 * 对任意报表数据，前端 `useReportCrossCheck` 消费后端 logic_check 端点返回的 Issue_List 得到的
 * 逐条勾稽判定，与纯函数 `computeCrossCheckResults` 的逐条判定完全一致；且当后端端点不可用触发
 * 降级时，降级路径的逐条判定与在线路径完全一致（收编与降级均不改变勾稽语义）。
 *
 * **Validates: Requirements 23.1, 23.3, 23.5**
 *
 * 说明（model-based / fast-check）：
 * - fast-check 随机生成资产负债表（BS）/ 利润表（IS）报表数据，构造 useReportCrossCheck
 *   消费的 getReport 返回行。
 * - 先跑降级路径（http.get reject 模拟后端不可用）拿到 `fallback` 结果——它就是
 *   `computeCrossCheckResults(crossCheckData)`（Req 23.2/23.3 fail-open）。
 * - 再以 `fallback` 的逐条判定"忠实收编"成后端 logic_check 端点响应（results.passed 逐条移植 +
 *   不通过项落 issue_list），跑在线路径拿到 `online`（source=backend，Req 23.1）。
 * - 断言：① 降级路径逐条判定 == 纯函数 `computeCrossCheckResults`（收编前语义基线）；
 *         ② 在线路径逐条判定 == 降级路径（收编与降级均不改变勾稽语义，Req 23.5）。
 *
 * 本文件仅新建 P32 属性测试，不改源码；与 Task 19.1 的 `.spec.ts` / `.property.spec.ts` 分离，避免冲突。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import * as fc from 'fast-check'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/services/auditPlatformApi', () => ({
  getReport: vi.fn(),
}))

// http.get 默认无实现；每个用例显式设置 mockResolvedValueOnce / mockRejectedValueOnce。
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))

import { getReport } from '@/services/auditPlatformApi'
import http from '@/utils/http'
import {
  useReportCrossCheck,
  computeCrossCheckResults,
  type CrossCheckItem,
} from '../useReportCrossCheck'

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

interface BsFigures {
  totalAssets: number
  totalLiabilities: number
  totalEquity: number
  cash: number
}
interface IsFigures {
  revenue: number
  cost: number
  profitBeforeTax: number
  incomeTax: number
  netProfit: number
}

/** 构造 useReportCrossCheck 消费的 balance_sheet 行（含 row_code / row_name / 合计标记）。 */
function makeBsRows(bs: BsFigures) {
  return [
    { row_code: 'assets_total', row_name: '资产总计', current_period_amount: String(bs.totalAssets), is_total_row: true },
    { row_code: 'liabilities_total', row_name: '负债合计', current_period_amount: String(bs.totalLiabilities), is_total_row: true },
    { row_code: 'equity_total', row_name: '所有者权益合计', current_period_amount: String(bs.totalEquity), is_total_row: true },
    { row_code: 'BS-001', row_name: '货币资金', current_period_amount: String(bs.cash), is_total_row: false },
  ]
}

/** 构造 useReportCrossCheck 消费的 income_statement 行。 */
function makeIsRows(is: IsFigures) {
  return [
    { row_code: 'IS-001', row_name: '营业收入', current_period_amount: String(is.revenue), is_total_row: false },
    { row_code: 'IS-002', row_name: '营业成本', current_period_amount: String(is.cost), is_total_row: false },
    { row_code: 'IS-017', row_name: '利润总额', current_period_amount: String(is.profitBeforeTax), is_total_row: false },
    { row_code: 'IS-018', row_name: '所得税费用', current_period_amount: String(is.incomeTax), is_total_row: false },
    { row_code: 'IS-019', row_name: '净利润', current_period_amount: String(is.netProfit), is_total_row: false },
  ]
}

/**
 * 把纯函数逐条结果"忠实收编"为后端 logic_check 端点响应：
 * - `results[i].passed` 逐条移植自纯函数（收编不改变勾稽语义，Req 23.5）。
 * - 不通过项进入 `issue_list`，左右值取纯函数的 left/right（供在线路径回填 diff）。
 * 这模拟"后端 7 条 logic_check 公式的逐条判定与原 computeCrossCheckResults 一致"。
 */
function buildFaithfulBackendPayload(pure: CrossCheckItem[]) {
  const results = pure.map((item, i) => ({
    formula_id: `report-cross-check-${i + 1}`,
    description: item.description,
    expression: `ROW(check-${i + 1})`,
    passed: item.passed,
  }))
  const issue_list = pure
    .map((item, i) => ({ item, i }))
    .filter(({ item }) => !item.passed)
    .map(({ item, i }) => ({
      formula_id: `report-cross-check-${i + 1}`,
      addr_id: null,
      description: item.description,
      left_value: item.leftValue != null ? String(item.leftValue) : null,
      right_value: item.rightValue != null ? String(item.rightValue) : null,
    }))
  return { results, issue_list, last_computed_at: '2025-01-01T00:00:00+00:00' }
}

/** 逐条勾稽判定的可比较投影（description + passed）——语义等价性的核心断言维度。 */
function judgments(items: CrossCheckItem[]): Array<[string, boolean]> {
  return items.map((r) => [r.description, r.passed])
}

// ─── Generators ───────────────────────────────────────────────────────────────

// 随机报表数据：覆盖平衡（各等式通过）与不平衡（各等式不通过）两类，使 passed 分布非平凡。
const arbBs = fc.record({
  totalAssets: fc.integer({ min: 0, max: 100000 }),
  totalLiabilities: fc.integer({ min: 0, max: 60000 }),
  totalEquity: fc.integer({ min: 0, max: 60000 }),
  cash: fc.integer({ min: -5000, max: 30000 }),
})
const arbIs = fc.record({
  revenue: fc.integer({ min: 0, max: 100000 }),
  cost: fc.integer({ min: 0, max: 60000 }),
  profitBeforeTax: fc.integer({ min: -20000, max: 60000 }),
  incomeTax: fc.integer({ min: -5000, max: 30000 }),
  netProfit: fc.integer({ min: -20000, max: 40000 }),
})

// ─── Property 32 ───────────────────────────────────────────────────────────────

// Feature: formula-management-library, Property 32: 前端 logic_check 收编与纯函数降级等价
describe('useReportCrossCheck — P32: 收编（backend）与降级（fallback）等价于纯函数', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReport.mockReset()
    mockHttpGet.mockReset()
  })

  /**
   * **Validates: Requirements 23.1, 23.3, 23.5**
   *
   * 对任意随机报表数据：
   * ① 降级路径（后端不可用 → 纯函数）的逐条判定 == `computeCrossCheckResults`（语义基线）；
   * ② 在线路径（消费后端 Issue_List/results，source=backend）的逐条判定 == 降级路径。
   * 三者逐条 [description, passed] 完全一致 → 收编与降级均不改变勾稽语义。
   */
  it('online (backend Issue_List) per-check == fallback per-check == computeCrossCheckResults', async () => {
    await fc.assert(
      fc.asyncProperty(arbBs, arbIs, async (bs, is) => {
        const bsRows = makeBsRows(bs)
        const isRows = makeIsRows(is)

        // ── ① 降级路径：http.get reject 模拟后端不可用（超时/5xx/网络错，Req 23.2/23.3）──
        mockGetReport.mockReset()
        mockHttpGet.mockReset()
        mockGetReport
          .mockResolvedValueOnce(bsRows as any)
          .mockResolvedValueOnce(isRows as any)
        mockHttpGet.mockRejectedValueOnce(new Error('backend unavailable'))

        const c1 = useReportCrossCheck(createOptions())
        await c1.loadCrossCheckData()
        const fallback = c1.crossCheckResults.value

        // 降级路径来源必须是 fallback，且结果就是纯函数逐条一致（语义基线）。
        expect(c1.crossCheckSource.value).toBe('fallback')
        expect(fallback).toHaveLength(7)
        const pure = computeCrossCheckResults(c1.crossCheckData.value)
        expect(judgments(fallback)).toEqual(judgments(pure))

        // ── ② 在线路径：后端忠实收编 fallback 的逐条判定（source=backend，Req 23.1）──
        mockGetReport.mockReset()
        mockHttpGet.mockReset()
        mockGetReport
          .mockResolvedValueOnce(bsRows as any)
          .mockResolvedValueOnce(isRows as any)
        mockHttpGet.mockResolvedValueOnce({ data: buildFaithfulBackendPayload(fallback) } as any)

        const c2 = useReportCrossCheck(createOptions())
        await c2.loadCrossCheckData()
        const online = c2.crossCheckResults.value

        expect(c2.crossCheckSource.value).toBe('backend')
        expect(online).toHaveLength(7)

        // 核心属性：在线路径逐条判定 == 降级路径逐条判定（收编不改变语义，Req 23.5）。
        expect(judgments(online)).toEqual(judgments(fallback))
      }),
      { numRuns: 20 },
    )
  })

  /**
   * **Validates: Requirements 23.1, 23.5**
   *
   * 不通过项：在线路径应从后端 Issue_List 关联回填左右值并据此计算 diff，
   * 且这些不通过项对应纯函数同样判定为不通过（逐条一致，判定非平凡）。
   */
  it('failed checks carry backend Issue_List left/right and stay consistent with pure judgments', async () => {
    await fc.assert(
      fc.asyncProperty(arbBs, arbIs, async (bs, is) => {
        const bsRows = makeBsRows(bs)
        const isRows = makeIsRows(is)

        // 先算纯函数基线（用于构造后端 payload 并做逐条比对）。
        mockGetReport.mockReset()
        mockHttpGet.mockReset()
        mockGetReport
          .mockResolvedValueOnce(bsRows as any)
          .mockResolvedValueOnce(isRows as any)
        mockHttpGet.mockRejectedValueOnce(new Error('backend unavailable'))
        const cBase = useReportCrossCheck(createOptions())
        await cBase.loadCrossCheckData()
        const pure = cBase.crossCheckResults.value

        // 在线路径：忠实收编后端响应。
        mockGetReport.mockReset()
        mockHttpGet.mockReset()
        mockGetReport
          .mockResolvedValueOnce(bsRows as any)
          .mockResolvedValueOnce(isRows as any)
        mockHttpGet.mockResolvedValueOnce({ data: buildFaithfulBackendPayload(pure) } as any)
        const cOnline = useReportCrossCheck(createOptions())
        await cOnline.loadCrossCheckData()
        const online = cOnline.crossCheckResults.value

        expect(cOnline.crossCheckSource.value).toBe('backend')

        for (let i = 0; i < online.length; i++) {
          // 逐条 passed 一致（P32 核心：判定语义不因收编而变）。
          expect(online[i].passed).toBe(pure[i].passed)
          // 不通过项且左右值均非空（纯函数未把 0 折叠为 null）时，在线路径应能从 Issue_List
          // 完整回填并复算出与纯函数一致的 diff。若某侧值为 0（纯函数 `x || null` 折叠成 null），
          // Issue_List 无从承载该 0 值，diff 回填为 best-effort（不作等值断言）。
          if (!online[i].passed && pure[i].leftValue != null && pure[i].rightValue != null) {
            expect(online[i].leftValue).toBe(pure[i].leftValue)
            expect(online[i].rightValue).toBe(pure[i].rightValue)
            expect(online[i].diff ?? 0).toBeCloseTo(pure[i].diff ?? 0, 2)
          }
        }
      }),
      { numRuns: 20 },
    )
  })
})
