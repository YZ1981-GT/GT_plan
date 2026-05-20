/**
 * test_m_prerequisite.spec.ts — M-F5 Task 2.3
 *
 * 验证 M_CYCLE_PREREQUISITES 配置 + ^M\d 路由：
 * - M 循环无独立 C 类前置底稿（由 A 类总体审计策略覆盖）
 * - M_CYCLE_PREREQUISITES = []（空数组）
 * - ^M\d 路由返回 overall='ready'（无前置条件）
 * - 其他循环（D/F/H/K/L）路由不受影响
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock Vue lifecycle hooks since we're testing outside a component
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onMounted: vi.fn((cb: Function) => cb()),
  }
})

// Mock api — always reject to trigger fallback logic
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

import { usePrerequisiteStatus } from '../usePrerequisiteStatus'

beforeEach(() => {
  mockGet.mockReset()
  // Default: API rejects → triggers fallback prerequisite list
  mockGet.mockRejectedValue(new Error('Not implemented'))
})

describe('usePrerequisiteStatus — M_CYCLE_PREREQUISITES 路由匹配（M-F5 Task 2.3）', () => {
  it('M2 底稿无前置底稿（items 为空数组）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('M6 底稿无前置底稿（items 为空数组）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M6')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('M10 底稿无前置底稿（items 为空数组）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M10')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('M2-2 子表路由到 M 循环（无前置）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M2-2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('M9 底稿无前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M9')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('大小写不敏感：m6 → M 循环（无前置）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'm6')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })
})

describe('usePrerequisiteStatus — M 循环不影响其他循环路由', () => {
  it('D4 底稿仍加载 D_CYCLE_PREREQUISITES（B23-1/C2/B51-5）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'D4')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['B23-1', 'C2', 'B51-5'])
  })

  it('L1 底稿仍加载 L_CYCLE_PREREQUISITES（C13）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L1')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C13'])
  })

  it('K8 底稿仍加载 K_CYCLE_PREREQUISITES（C11）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K8')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C11'])
  })

  it('H1 底稿仍加载 H_CYCLE_PREREQUISITES（C6）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H1')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C6'])
  })
})
