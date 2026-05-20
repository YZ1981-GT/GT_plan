/**
 * useProcedureTrimming.spec.ts — 程序适用性裁剪 composable 测试
 *
 * 验证：
 * 1. trimRows 调用 API + 更新 rows 状态 + emit eventBus
 * 2. revertRows 调用 API + 恢复状态 + emit eventBus
 * 3. fetchSummary / fetchHistory 响应解析
 * 4. 批量操作结果摘要（succeeded/skipped/failed）
 *
 * @see requirements.md Requirement 2.4, 3.4, 5.2
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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
const mockPatch = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    patch: (...args: any[]) => mockPatch(...args),
  },
}))

// Capture eventBus emissions
const emittedEvents: Array<{ event: string; payload: any }> = []
const handlers: Record<string, Function[]> = {}
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: (evt: string, h: Function) => {
      if (!handlers[evt]) handlers[evt] = []
      handlers[evt].push(h)
    },
    off: (evt: string, h: Function) => {
      handlers[evt] = (handlers[evt] || []).filter((fn) => fn !== h)
    },
    emit: (evt: string, payload: any) => {
      emittedEvents.push({ event: evt, payload })
      ;(handlers[evt] || []).forEach((h) => h(payload))
    },
  },
}))

import { useProcedureTrimming } from '../useProcedureTrimming'

beforeEach(() => {
  mockGet.mockReset()
  mockPatch.mockReset()
  emittedEvents.length = 0
  Object.keys(handlers).forEach((k) => delete handlers[k])
})

afterEach(() => {
  vi.restoreAllMocks()
})

function setupMockWorkpaper(procedureStatus: Record<string, any> = {}, trimmingMetadata: Record<string, any> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/working-papers/')) {
      return Promise.resolve({
        parsed_data: {
          procedure_status: { e1a: procedureStatus },
          trimming_metadata: { e1a: trimmingMetadata },
        },
      })
    }
    return Promise.resolve(null)
  })
}

describe('useProcedureTrimming — 初始化与加载', () => {
  it('加载程序行列表并按 Rxx 排序', async () => {
    setupMockWorkpaper({
      R22: { status: 'pending', description: '程序22' },
      R17: { status: 'not_applicable', description: '程序17' },
      R5: { status: 'filled', description: '程序5' },
    }, {
      R17: { reason_code: 'no_related_business', trimmed_by: 'user-1', trimmed_at: '2026-05-20T10:00:00Z' },
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    expect(trimming.rows.value.length).toBe(3)
    // 按 Rxx 排序
    expect(trimming.rows.value[0].row).toBe('R5')
    expect(trimming.rows.value[1].row).toBe('R17')
    expect(trimming.rows.value[2].row).toBe('R22')
    // 裁剪元数据
    expect(trimming.rows.value[1].reason_code).toBe('no_related_business')
    expect(trimming.rows.value[1].trimmed_by).toBe('user-1')
  })

  it('stats 正确计算 total/trimmed/active/trimRate', async () => {
    setupMockWorkpaper({
      R1: { status: 'pending' },
      R2: { status: 'not_applicable' },
      R3: { status: 'not_applicable' },
      R4: { status: 'filled' },
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    expect(trimming.stats.value.total).toBe(4)
    expect(trimming.stats.value.trimmed).toBe(2)
    expect(trimming.stats.value.active).toBe(2)
    expect(trimming.stats.value.trimRate).toBe(50)
  })

  it('空数据时 stats 为零', async () => {
    setupMockWorkpaper({})

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    expect(trimming.stats.value.total).toBe(0)
    expect(trimming.stats.value.trimmed).toBe(0)
    expect(trimming.stats.value.trimRate).toBe(0)
  })
})

describe('useProcedureTrimming — trimRows', () => {
  it('调用 PATCH API 并更新本地状态', async () => {
    setupMockWorkpaper({
      R17: { status: 'pending', description: '程序17' },
      R22: { status: 'pending', description: '程序22' },
    })
    mockPatch.mockResolvedValue({
      ok: true,
      action: 'trim',
      succeeded: ['R17'],
      skipped: [],
      failed: [],
      message: null,
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    const result = await trimming.trimRows(['R17'], {
      reason_code: 'no_related_business',
      reason_text: null,
    })

    expect(result.ok).toBe(true)
    expect(result.succeeded).toEqual(['R17'])
    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/proj1/workpapers/wp1/procedure-trim',
      expect.objectContaining({
        action: 'trim',
        sheet_key: 'e1a',
        row_ids: ['R17'],
        reason_code: 'no_related_business',
      }),
    )
    // 本地状态更新
    expect(trimming.rows.value.find((r) => r.row === 'R17')?.status).toBe('not_applicable')
  })

  it('成功后 emit procedure-status:changed 事件', async () => {
    setupMockWorkpaper({ R17: { status: 'pending' } })
    mockPatch.mockResolvedValue({
      ok: true, action: 'trim', succeeded: ['R17'], skipped: [], failed: [],
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()
    emittedEvents.length = 0 // 清除 refresh 触发的事件

    await trimming.trimRows(['R17'], { reason_code: 'low_risk_assessment' })

    const statusEvent = emittedEvents.find((e) => e.event === 'procedure-status:changed')
    expect(statusEvent).toBeDefined()
    expect(statusEvent!.payload.projectId).toBe('proj1')
    expect(statusEvent!.payload.status).toBe('not_applicable')
  })

  it('API 失败时返回 failed 列表', async () => {
    setupMockWorkpaper({ R17: { status: 'pending' } })
    mockPatch.mockRejectedValue(new Error('Network error'))

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    const result = await trimming.trimRows(['R17'], { reason_code: 'other', reason_text: '测试理由文本' })

    expect(result.ok).toBe(false)
    expect(result.failed).toEqual(['R17'])
  })
})

describe('useProcedureTrimming — revertRows', () => {
  it('调用 PATCH API 并恢复本地状态', async () => {
    setupMockWorkpaper(
      { R17: { status: 'not_applicable' } },
      { R17: { reason_code: 'no_related_business', trimmed_by: 'u1' } },
    )
    mockPatch.mockResolvedValue({
      ok: true, action: 'revert', succeeded: ['R17'], skipped: [], failed: [],
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    const result = await trimming.revertRows(['R17'])

    expect(result.ok).toBe(true)
    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/proj1/workpapers/wp1/procedure-trim',
      expect.objectContaining({ action: 'revert', row_ids: ['R17'] }),
    )
    // 本地状态恢复
    const row = trimming.rows.value.find((r) => r.row === 'R17')
    expect(row?.status).toBe('pending')
    expect(row?.reason_code).toBeUndefined()
    expect(row?.trimmed_by).toBeUndefined()
  })

  it('成功后 emit procedure-status:changed 事件', async () => {
    setupMockWorkpaper({ R17: { status: 'not_applicable' } })
    mockPatch.mockResolvedValue({
      ok: true, action: 'revert', succeeded: ['R17'], skipped: [], failed: [],
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()
    emittedEvents.length = 0

    await trimming.revertRows(['R17'])

    const statusEvent = emittedEvents.find((e) => e.event === 'procedure-status:changed')
    expect(statusEvent).toBeDefined()
    expect(statusEvent!.payload.status).toBe('pending')
  })
})

describe('useProcedureTrimming — fetchSummary', () => {
  it('正确解析 summary 响应', async () => {
    setupMockWorkpaper({})
    const mockSummary = {
      total_procedures: 30,
      trimmed_count: 8,
      trim_rate: 26.7,
      by_cycle: [
        { cycle: 'F', total: 10, trimmed: 6, rate: 60, warning: true },
        { cycle: 'D', total: 20, trimmed: 2, rate: 10, warning: false },
      ],
      by_reason: [
        { reason_code: 'no_related_business', count: 5 },
        { reason_code: 'low_risk_assessment', count: 3 },
      ],
      warnings: ['F 循环裁剪率 60% 超过 50% 阈值'],
    }
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/procedure-trim/summary')) return Promise.resolve(mockSummary)
      return Promise.resolve({ parsed_data: { procedure_status: { e1a: {} } } })
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    const result = await trimming.fetchSummary()

    expect(result.total_procedures).toBe(30)
    expect(result.trimmed_count).toBe(8)
    expect(result.by_cycle.length).toBe(2)
    expect(result.by_cycle[0].warning).toBe(true)
    expect(result.warnings.length).toBe(1)
  })
})

describe('useProcedureTrimming — fetchHistory', () => {
  it('正确解析 history 响应并存入 trimHistory', async () => {
    setupMockWorkpaper({})
    const mockHistory = [
      {
        id: 'log-1',
        action: 'trim',
        row_ids: ['R17', 'R22'],
        reason_code: 'no_related_business',
        reason_text: null,
        user_id: 'user-1',
        user_name: '张三',
        created_at: '2026-05-20T10:30:00Z',
      },
      {
        id: 'log-2',
        action: 'revert',
        row_ids: ['R17'],
        reason_code: null,
        reason_text: null,
        user_id: 'user-1',
        user_name: '张三',
        created_at: '2026-05-20T11:00:00Z',
      },
    ]
    mockGet.mockImplementation((url: string, config?: any) => {
      if (url.includes('/procedure-trim/history')) return Promise.resolve(mockHistory)
      return Promise.resolve({ parsed_data: { procedure_status: { e1a: {} } } })
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    const result = await trimming.fetchHistory({ reason_code: 'no_related_business' })

    expect(result.length).toBe(2)
    expect(result[0].action).toBe('trim')
    expect(result[0].row_ids).toEqual(['R17', 'R22'])
    expect(trimming.trimHistory.value.length).toBe(2)
  })

  it('API 失败时返回空数组', async () => {
    setupMockWorkpaper({})
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/procedure-trim/history')) return Promise.reject(new Error('fail'))
      return Promise.resolve({ parsed_data: { procedure_status: { e1a: {} } } })
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    const result = await trimming.fetchHistory()

    expect(result).toEqual([])
    expect(trimming.trimHistory.value).toEqual([])
  })
})

describe('useProcedureTrimming — 批量操作结果摘要', () => {
  it('批量 trim 部分成功/部分跳过', async () => {
    setupMockWorkpaper({
      R1: { status: 'pending' },
      R2: { status: 'not_applicable' },
      R3: { status: 'pending' },
    })
    mockPatch.mockResolvedValue({
      ok: true,
      action: 'trim',
      succeeded: ['R1', 'R3'],
      skipped: ['R2'],
      failed: [],
      message: null,
    })

    const trimming = useProcedureTrimming('proj1', 'wp1', 'e1a')
    await trimming.refresh()

    const result = await trimming.trimRows(['R1', 'R2', 'R3'], { reason_code: 'low_risk_assessment' })

    expect(result.succeeded.length).toBe(2)
    expect(result.skipped.length).toBe(1)
    expect(result.failed.length).toBe(0)
    // succeeded + skipped + failed = input count
    expect(result.succeeded.length + result.skipped.length + result.failed.length).toBe(3)
  })
})
