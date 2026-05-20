/**
 * useProcedureStatus.spec.ts — Sprint 2 Task 2.42
 *
 * 三档晋级条件 + eventBus 订阅刷新
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

// Capture eventBus subscriptions
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
      ;(handlers[evt] || []).forEach((h) => h(payload))
    },
  },
}))

import { useProcedureStatus } from '../useProcedureStatus'

beforeEach(() => {
  mockGet.mockReset()
  mockPatch.mockReset()
  Object.keys(handlers).forEach((k) => delete handlers[k])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useProcedureStatus — 三档晋级条件', () => {
  it('rows for status=filled 计为 filled+', async () => {
    mockGet.mockResolvedValue({
      parsed_data: {
        procedure_status: {
          e1a: {
            R17: { status: 'filled' },
            R18: { status: 'filled' },
            R19: { status: 'pending' },
          },
        },
      },
    })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    expect(ps.rows.value.length).toBe(3)
    expect(ps.summary.value.total).toBe(3)
    expect(ps.summary.value.filled).toBe(2)
    expect(ps.summary.value.reviewed).toBe(0)
    expect(ps.summary.value.approved).toBe(0)
    expect(ps.summary.value.pending).toBe(1)
  })

  it('rows for status=reviewed 也计入 filled (累积)', async () => {
    mockGet.mockResolvedValue({
      parsed_data: {
        procedure_status: {
          e1a: {
            R17: { status: 'reviewed' },
            R18: { status: 'reviewed' },
            R19: { status: 'pending' },
          },
        },
      },
    })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    expect(ps.summary.value.filled).toBe(2)  // reviewed 也算 filled+
    expect(ps.summary.value.reviewed).toBe(2)
    expect(ps.summary.value.approved).toBe(0)
  })

  it('rows for status=approved 计入 reviewed+filled+approved 三层', async () => {
    mockGet.mockResolvedValue({
      parsed_data: {
        procedure_status: {
          e1a: {
            R17: { status: 'approved' },
            R18: { status: 'approved' },
            R19: { status: 'pending' },
          },
        },
      },
    })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    expect(ps.summary.value.approved).toBe(2)
    expect(ps.summary.value.reviewed).toBe(2)
    expect(ps.summary.value.filled).toBe(2)
  })

  it('rate computed 按总数计算百分比', async () => {
    mockGet.mockResolvedValue({
      parsed_data: { procedure_status: { e1a: { R17: { status: 'approved' }, R18: { status: 'pending' } } } },
    })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    expect(ps.approvedRate.value).toBe(50)
    expect(ps.filledRate.value).toBe(50)
  })
})

describe('useProcedureStatus — eventBus 订阅刷新', () => {
  it('订阅 workpaper:saved 事件触发 refresh', async () => {
    mockGet.mockResolvedValue({
      parsed_data: { procedure_status: { e1a: { R17: { status: 'filled' } } } },
    })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    const callsBeforeEmit = mockGet.mock.calls.length

    // emit workpaper:saved
    ;(handlers['workpaper:saved'] || []).forEach((h) => h({ projectId: 'proj1', wpId: 'wp1' }))
    // 等待 microtask
    await Promise.resolve()
    await Promise.resolve()
    expect(mockGet.mock.calls.length).toBeGreaterThan(callsBeforeEmit)
  })

  it('订阅 review-record:resolved + signature:created + manual-refresh', async () => {
    mockGet.mockResolvedValue({
      parsed_data: { procedure_status: { e1a: { R17: { status: 'filled' } } } },
    })
    useProcedureStatus('proj1', 'wp1', 'e1a')
    await Promise.resolve()
    expect(handlers['review-record:resolved']?.length).toBe(1)
    expect(handlers['signature:created']?.length).toBe(1)
    expect(handlers['manual-refresh']?.length).toBe(1)
    expect(handlers['procedure-status:changed']?.length).toBe(1)
  })

  it('markStatus 调 PATCH 端点更新本地状态', async () => {
    mockGet.mockResolvedValue({
      parsed_data: { procedure_status: { e1a: { R17: { status: 'pending' } } } },
    })
    mockPatch.mockResolvedValue({ ok: true })
    const ps = useProcedureStatus('proj1', 'wp1', 'e1a')
    await ps.refresh()
    await ps.markStatus('R17', 'filled')
    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/proj1/working-papers/wp1/procedure-status',
      expect.objectContaining({ row: 'R17', status: 'filled' }),
    )
    expect(ps.rows.value.find((r) => r.row === 'R17')?.status).toBe('filled')
  })
})
