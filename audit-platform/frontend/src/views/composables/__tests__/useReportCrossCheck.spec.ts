/**
 * useReportCrossCheck —— 表间审核只消费后端 logic_check 端点（后端唯一结果）。
 *
 * 2026-11-08 c39949602 删除了前端纯函数降级（`computeCrossCheckResults` + 取 BS/IS 报表自算 7 条勾稽）：
 * 前后端两份口径会各说各话，后端不可用时前端自算的「通过」会冒充审核结果。原测试仍按降级路径写，
 * 一直红（22 条）。本文件按现行契约改写：
 * - 主路径：逐条结果来自后端 results，左右值与差额来自 issue_list，五态 / 原因 / 严重度保留，差额保真零；
 * - 后端失败：结果为空、来源 none、错误原因交界面，不本地自算、不读报表；
 * - 上下文变化（项目 / 年度 / 准则）立即清空旧结果，迟到响应作废。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import * as fc from 'fast-check'

vi.mock('@/services/auditPlatformApi', () => ({ getReport: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))

import { getReport } from '@/services/auditPlatformApi'
import http from '@/utils/http'
import { useReportCrossCheck, mapBackendCrossCheck } from '../useReportCrossCheck'

const mockGetReport = vi.mocked(getReport)
const mockHttpGet = vi.mocked(http.get)

const DESCRIPTIONS = [
  '资产合计 = 负债合计 + 所有者权益合计',
  '营业收入 − 营业成本 = 毛利',
  '利润总额 − 所得税 = 净利润',
  '资产 − 负债 = 权益',
  '所有者权益变动表期末 = 资产负债表权益',
  '有效税率 ≈ 25%',
  '货币资金 ≥ 0（负值异常）',
]

function backendPayload(failIndex: number | null, left = '150', right = '140') {
  return {
    results: DESCRIPTIONS.map((d, i) => ({
      formula_id: `report-cross-check-${i + 1}`, description: d, expression: 'x', passed: i !== failIndex,
    })),
    issue_list: failIndex === null ? [] : [{
      formula_id: `report-cross-check-${failIndex + 1}`, addr_id: null, description: DESCRIPTIONS[failIndex],
      left_value: left, right_value: right,
    }],
  }
}

function createOptions(overrides: Partial<{ projectId: any; year: any; activeTab: any; standard: any }> = {}) {
  return {
    projectId: overrides.projectId ?? computed(() => 'proj-1'),
    year: overrides.year ?? computed(() => 2025),
    activeTab: overrides.activeTab ?? ref('basic'),
    currentApplicableStandard: overrides.standard ?? computed(() => 'soe_standalone'),
  }
}

beforeEach(() => {
  mockGetReport.mockReset()
  mockHttpGet.mockReset()
})

describe('主路径：后端逐条结果', () => {
  it('请求带项目与年度，逐条 passed / 左右值 / 差额来自后端，来源为 backend', async () => {
    mockHttpGet.mockResolvedValue({ data: backendPayload(2) } as any)
    const { loadCrossCheckData, crossCheckResults, crossCheckSource, crossCheckError } = useReportCrossCheck(createOptions())
    await loadCrossCheckData()

    expect(mockHttpGet).toHaveBeenCalledWith('/api/projects/proj-1/formula/report-cross-check', { params: { year: 2025 } })
    expect(crossCheckSource.value).toBe('backend')
    expect(crossCheckError.value).toBe('')
    const results = crossCheckResults.value
    expect(results.map((r) => r.passed)).toEqual([true, true, false, true, true, true, true])
    expect(results.map((r) => r.description)).toEqual(DESCRIPTIONS)
    expect([results[2].leftValue, results[2].rightValue, results[2].diff]).toEqual([150, 140, 10])
    expect(results[0].leftValue).toBeNull()
  })

  it('不再读报表自算（getReport 不被调用）', async () => {
    mockHttpGet.mockResolvedValue({ data: backendPayload(null) } as any)
    const { loadCrossCheckData } = useReportCrossCheck(createOptions())
    await loadCrossCheckData()
    expect(mockGetReport).not.toHaveBeenCalled()
  })

  it('左右值相等时差额保真零（不变成 null）', async () => {
    mockHttpGet.mockResolvedValue({ data: backendPayload(0, '100', '100') } as any)
    const { loadCrossCheckData, crossCheckResults } = useReportCrossCheck(createOptions())
    await loadCrossCheckData()
    expect(crossCheckResults.value[0].diff).toBe(0)
  })
})

describe('后端失败：不本地自算', () => {
  it('网络错 / 5xx ⇒ 结果为空、来源 none、错误原因交界面', async () => {
    mockHttpGet.mockRejectedValue(new Error('Network Error'))
    const { loadCrossCheckData, crossCheckResults, crossCheckSource, crossCheckError, crossCheckLoading } =
      useReportCrossCheck(createOptions())
    await loadCrossCheckData()
    expect(crossCheckResults.value).toEqual([])
    expect(crossCheckSource.value).toBe('none')
    expect(crossCheckError.value).toBe('Network Error')
    expect(crossCheckLoading.value).toBe(false)
    expect(mockGetReport).not.toHaveBeenCalled()
  })

  it('后端空结果且标明无报表数据 ⇒ 提示「暂无报表数据」，不冒充通过', async () => {
    mockHttpGet.mockResolvedValue({ data: { results: [], issue_list: [], no_result: true } } as any)
    const { loadCrossCheckData, crossCheckResults, crossCheckSource, crossCheckError } = useReportCrossCheck(createOptions())
    await loadCrossCheckData()
    expect(crossCheckResults.value).toEqual([])
    expect(crossCheckSource.value).toBe('none')
    expect(crossCheckError.value).toContain('暂无报表数据')
  })

  it('没有项目或年度 ⇒ 不发请求', async () => {
    const { loadCrossCheckData } = useReportCrossCheck(createOptions({ year: computed(() => null) }))
    await loadCrossCheckData()
    expect(mockHttpGet).not.toHaveBeenCalled()
  })
})

describe('上下文围栏', () => {
  it('切年度立即清空旧结果，迟到的旧响应作废', async () => {
    const year = ref<number | null>(2025)
    let resolveOld: (v: any) => void = () => {}
    mockHttpGet.mockImplementationOnce(() => new Promise((r) => { resolveOld = r }) as any)
    const c = useReportCrossCheck(createOptions({ year: computed(() => year.value) }))
    const pending = c.loadCrossCheckData()
    year.value = 2024
    resolveOld({ data: backendPayload(2) })
    await pending
    await nextTick()
    expect(c.crossCheckResults.value).toEqual([])
    expect(c.crossCheckSource.value).toBe('none')
  })

  it('切到跨表核对页签时自动加载', async () => {
    mockHttpGet.mockResolvedValue({ data: backendPayload(null) } as any)
    const activeTab = ref('basic')
    const c = useReportCrossCheck(createOptions({ activeTab }))
    expect(mockHttpGet).not.toHaveBeenCalled()
    activeTab.value = 'cross_check'
    await nextTick()
    await Promise.resolve()
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(c.crossCheckSource.value).toBe('backend'))
  })
})

describe('mapBackendCrossCheck（PBT）', () => {
  it('逐条 description / passed 与后端一致；不通过项差额 = 左 − 右', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ passed: fc.boolean(), left: fc.integer({ min: -1e6, max: 1e6 }), right: fc.integer({ min: -1e6, max: 1e6 }) }),
          { minLength: 1, maxLength: 7 }),
        (rows) => {
          const payload = {
            results: rows.map((r, i) => ({ formula_id: `f${i}`, description: `d${i}`, passed: r.passed })),
            issue_list: rows.flatMap((r, i) => r.passed ? [] : [{
              formula_id: `f${i}`, description: `d${i}`, left_value: String(r.left), right_value: String(r.right),
            }]),
          }
          const items = mapBackendCrossCheck(payload as any)
          expect(items.map((x) => [x.description, x.passed])).toEqual(rows.map((r, i) => [`d${i}`, r.passed]))
          items.forEach((x, i) => {
            if (rows[i].passed) expect(x.diff).toBeNull()
            else expect(x.diff).toBe(rows[i].left - rows[i].right)
          })
        },
      ),
      { numRuns: 5 },
    )
  })
})
