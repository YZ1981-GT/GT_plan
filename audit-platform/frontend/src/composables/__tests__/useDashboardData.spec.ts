/**
 * useDashboardData.spec.ts — Sprint 2 Task 4.1
 *
 * 测试 useDashboardData composable:
 * - refresh 调用 API + 更新 data ref
 * - loading 状态切换（fetch 期间 true，完成后 false）
 * - 错误处理（网络失败 → error ref）
 * - lastUpdated 更新
 * - 计算属性正确解构响应数据
 *
 * Validates: Requirements 1.4, 9.1
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// Mock Vue lifecycle hooks since we're testing outside a component
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onMounted: vi.fn((cb: Function) => cb()),
    onUnmounted: vi.fn(),
  }
})

// Mock api
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

import { useDashboardData } from '../useDashboardData'
import type { DashboardSummary } from '../useDashboardData'

// ─── Test Fixtures ───────────────────────────────────────────────────────────

function createMockDashboardResponse(): DashboardSummary {
  return {
    project_name: '测试项目',
    audit_year: 2025,
    last_updated: '2025-06-01T10:00:00Z',
    cycle_progress: [
      {
        cycle: 'D',
        cycle_name: '销售收入',
        total_procedures: 20,
        completed_procedures: 15,
        trimmed_procedures: 2,
        progress_rate: 83.33,
      },
      {
        cycle: 'E',
        cycle_name: '货币资金',
        total_procedures: 10,
        completed_procedures: 10,
        trimmed_procedures: 0,
        progress_rate: 100.0,
      },
    ],
    vr_summary: {
      total_rules: 33,
      blocking_failed: 2,
      all_passed: false,
      by_cycle: [
        {
          cycle: 'D',
          blocking_failed: 1,
          failed_rules: [{ rule_id: 'VR-D4-01', rule_name: '销售收入勾稽', details: '差异 > 1%' }],
        },
        {
          cycle: 'F',
          blocking_failed: 1,
          failed_rules: [{ rule_id: 'VR-F2-01', rule_name: '存货余额勾稽', details: null }],
        },
      ],
    },
    open_reviews: {
      total: 3,
      by_layer: { L5: 1, L4: 2 },
      items: [
        {
          id: 'r1',
          review_layer: 'L5',
          summary: '重要性水平需重新评估',
          created_at: '2025-05-30T08:00:00Z',
          wp_code: 'B15',
          sheet_name: 'Sheet1',
          cell_ref: 'A1',
        },
        {
          id: 'r2',
          review_layer: 'L4',
          summary: '销售收入截止测试样本不足',
          created_at: '2025-05-29T10:00:00Z',
          wp_code: 'D2-1',
          sheet_name: null,
          cell_ref: null,
        },
        {
          id: 'r3',
          review_layer: 'L4',
          summary: '货币资金函证回函率偏低',
          created_at: '2025-05-28T14:00:00Z',
          wp_code: 'E1-3',
          sheet_name: 'Sheet2',
          cell_ref: 'B5',
        },
      ],
    },
    timeline: {
      current_stage: 'execution',
      stages: [
        { name: '计划', status: 'completed', entered_at: '2025-01-10T00:00:00Z', completed_at: '2025-02-01T00:00:00Z', summary: null },
        { name: '执行', status: 'current', entered_at: '2025-02-02T00:00:00Z', completed_at: null, summary: '全循环完成率 72%' },
        { name: '复核', status: 'pending', entered_at: null, completed_at: null, summary: null },
        { name: '报告', status: 'pending', entered_at: null, completed_at: null, summary: null },
      ],
    },
    trimming_overview: {
      available: true,
      total_procedures: 200,
      trimmed_count: 30,
      trim_rate: 15.0,
      by_cycle: [
        { cycle: 'D', total: 20, trimmed: 2, rate: 10.0, warning: false },
        { cycle: 'K', total: 25, trimmed: 15, rate: 60.0, warning: true },
      ],
    },
    errors: null,
  }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockGet.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useDashboardData — refresh 调用 API + 更新 data ref', () => {
  it('refresh 成功时 data ref 被正确赋值', async () => {
    const mockResponse = createMockDashboardResponse()
    mockGet.mockResolvedValue(mockResponse)

    const projectId = ref('proj-123')
    const { data, refresh } = useDashboardData(projectId)

    // onMounted 已自动调用 refresh，等待完成
    await vi.waitFor(() => expect(data.value).not.toBeNull())

    expect(data.value).toEqual(mockResponse)
    expect(mockGet).toHaveBeenCalledWith('/api/projects/proj-123/dashboard/summary')
  })

  it('refresh 使用正确的 projectId 构建 URL', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('abc-456')
    useDashboardData(projectId)

    await vi.waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(mockGet).toHaveBeenCalledWith('/api/projects/abc-456/dashboard/summary')
  })

  it('手动调用 refresh 重新拉取数据', async () => {
    const response1 = createMockDashboardResponse()
    const response2 = { ...createMockDashboardResponse(), project_name: '更新后项目' }
    mockGet.mockResolvedValueOnce(response1).mockResolvedValueOnce(response2)

    const projectId = ref('proj-123')
    const { data, refresh } = useDashboardData(projectId)

    await vi.waitFor(() => expect(data.value).not.toBeNull())
    expect(data.value!.project_name).toBe('测试项目')

    await refresh()
    expect(data.value!.project_name).toBe('更新后项目')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('projectId 为空时 refresh 不发起请求', async () => {
    const projectId = ref('')
    useDashboardData(projectId)

    // 等待一个 tick 确认没有调用
    await Promise.resolve()
    await Promise.resolve()
    expect(mockGet).not.toHaveBeenCalled()
  })
})

describe('useDashboardData — loading 状态切换', () => {
  it('fetch 期间 loading=true，完成后 loading=false', async () => {
    let resolvePromise: (value: any) => void
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve
    })
    mockGet.mockReturnValue(pendingPromise)

    const projectId = ref('proj-123')
    const { loading } = useDashboardData(projectId)

    // onMounted 触发 refresh，此时应为 loading
    await Promise.resolve()
    expect(loading.value).toBe(true)

    // 完成请求
    resolvePromise!(createMockDashboardResponse())
    await vi.waitFor(() => expect(loading.value).toBe(false))
  })

  it('fetch 失败后 loading 也恢复为 false', async () => {
    mockGet.mockRejectedValue(new Error('Network Error'))

    const projectId = ref('proj-123')
    const { loading } = useDashboardData(projectId)

    await vi.waitFor(() => expect(loading.value).toBe(false))
  })
})

describe('useDashboardData — 错误处理', () => {
  it('网络失败时 error ref 被赋值错误消息', async () => {
    mockGet.mockRejectedValue(new Error('Network Error'))

    const projectId = ref('proj-123')
    const { error } = useDashboardData(projectId)

    await vi.waitFor(() => expect(error.value).not.toBeNull())
    expect(error.value).toBe('Network Error')
  })

  it('无 message 的错误使用默认消息', async () => {
    mockGet.mockRejectedValue({})

    const projectId = ref('proj-123')
    const { error } = useDashboardData(projectId)

    await vi.waitFor(() => expect(error.value).not.toBeNull())
    expect(error.value).toBe('仪表盘数据加载失败')
  })

  it('成功请求后 error 被清空', async () => {
    // 第一次失败
    mockGet.mockRejectedValueOnce(new Error('Fail'))
    const projectId = ref('proj-123')
    const { error, refresh } = useDashboardData(projectId)

    await vi.waitFor(() => expect(error.value).toBe('Fail'))

    // 第二次成功
    mockGet.mockResolvedValueOnce(createMockDashboardResponse())
    await refresh()
    expect(error.value).toBeNull()
  })
})

describe('useDashboardData — lastUpdated 更新', () => {
  it('成功 fetch 后 lastUpdated 取自响应的 last_updated 字段', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { lastUpdated } = useDashboardData(projectId)

    await vi.waitFor(() => expect(lastUpdated.value).not.toBeNull())
    expect(lastUpdated.value).toBe('2025-06-01T10:00:00Z')
  })

  it('fetch 失败时 lastUpdated 不更新', async () => {
    mockGet.mockRejectedValue(new Error('Fail'))

    const projectId = ref('proj-123')
    const { lastUpdated } = useDashboardData(projectId)

    await vi.waitFor(() => expect(lastUpdated.value).toBeNull())
  })
})

describe('useDashboardData — 计算属性正确解构响应数据', () => {
  it('cycleProgress 从 data.cycle_progress 解构', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { cycleProgress } = useDashboardData(projectId)

    await vi.waitFor(() => expect(cycleProgress.value.length).toBeGreaterThan(0))
    expect(cycleProgress.value).toHaveLength(2)
    expect(cycleProgress.value[0].cycle).toBe('D')
    expect(cycleProgress.value[1].cycle).toBe('E')
  })

  it('vrSummary 从 data.vr_summary 解构', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { vrSummary } = useDashboardData(projectId)

    await vi.waitFor(() => expect(vrSummary.value).not.toBeNull())
    expect(vrSummary.value!.total_rules).toBe(33)
    expect(vrSummary.value!.blocking_failed).toBe(2)
    expect(vrSummary.value!.all_passed).toBe(false)
  })

  it('openReviews 从 data.open_reviews.items 解构', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { openReviews } = useDashboardData(projectId)

    await vi.waitFor(() => expect(openReviews.value.length).toBeGreaterThan(0))
    expect(openReviews.value).toHaveLength(3)
    expect(openReviews.value[0].review_layer).toBe('L5')
  })

  it('timeline 从 data.timeline 解构', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { timeline } = useDashboardData(projectId)

    await vi.waitFor(() => expect(timeline.value).not.toBeNull())
    expect(timeline.value!.current_stage).toBe('execution')
    expect(timeline.value!.stages).toHaveLength(4)
  })

  it('trimmingOverview 从 data.trimming_overview 解构', async () => {
    mockGet.mockResolvedValue(createMockDashboardResponse())

    const projectId = ref('proj-123')
    const { trimmingOverview } = useDashboardData(projectId)

    await vi.waitFor(() => expect(trimmingOverview.value).not.toBeNull())
    expect(trimmingOverview.value!.available).toBe(true)
    expect(trimmingOverview.value!.trim_rate).toBe(15.0)
  })

  it('data 为 null 时计算属性返回默认值', async () => {
    // projectId 为空，不会发起请求，data 保持 null
    const projectId = ref('')
    const { cycleProgress, vrSummary, openReviews, timeline, trimmingOverview } =
      useDashboardData(projectId)

    await Promise.resolve()
    expect(cycleProgress.value).toEqual([])
    expect(vrSummary.value).toBeNull()
    expect(openReviews.value).toEqual([])
    expect(timeline.value).toBeNull()
    expect(trimmingOverview.value).toBeNull()
  })

  it('open_reviews 为 null 时 openReviews 返回空数组', async () => {
    const response = createMockDashboardResponse()
    response.open_reviews = null
    mockGet.mockResolvedValue(response)

    const projectId = ref('proj-123')
    const { openReviews } = useDashboardData(projectId)

    await vi.waitFor(() => expect(openReviews.value).toEqual([]))
  })
})
