/**
 * test_l_prerequisite.spec.ts — L-F5 Task 2.4
 *
 * 验证 L_CYCLE_PREREQUISITES 配置 + ^L\d 路由：
 * - C13 债务循环业务层面控制测试，L0~L8 共用
 * - 其他循环（D/F/H/K）路由不受影响
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

describe('usePrerequisiteStatus — L_CYCLE_PREREQUISITES 路由匹配（L-F5 Task 2.3/2.4）', () => {
  it('L1 底稿加载 C13（债务循环业务层面控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L3 底稿加载 C13（长期借款同样命中 ^L\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L3')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L5 底稿加载 C13（长期应付款同样命中 ^L\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L5')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L8 底稿加载 C13（财务费用同样命中 ^L\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L8')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L1-2（子 sheet）也命中 ^L\\d 路由', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L1-2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L8-2（财务费用明细子 sheet）也命中 ^L\\d 路由', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'L8-2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C13')
    expect(codes).toHaveLength(1)
  })

  it('L 循环 fallback 时 overall 为 blocked', async () => {
    const { overall } = usePrerequisiteStatus('proj-1', 'L1')
    await new Promise((r) => setTimeout(r, 10))

    expect(overall.value).toBe('blocked')
  })

  it('L 循环 fallback 时 banner type 为 error（红色横幅）', async () => {
    const { banner } = usePrerequisiteStatus('proj-1', 'L1')
    await new Promise((r) => setTimeout(r, 10))

    expect(banner.value.type).toBe('error')
    expect(banner.value.message).toContain('C13')
  })
})

describe('usePrerequisiteStatus — L 循环不影响其他循环路由', () => {
  it('D4 底稿仍加载 D_CYCLE_PREREQUISITES（B23-1/C2/B51-5）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'D4')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['B23-1', 'C2', 'B51-5'])
  })

  it('F2 底稿仍加载 F_CYCLE_PREREQUISITES（B23-3/C4/B51-4）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'F2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['B23-3', 'C4', 'B51-4'])
  })

  it('H1 底稿仍加载 C6（固定资产控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['C6'])
  })

  it('K8 底稿仍加载 C11（管理循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K8')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['C11'])
  })

  it('J1 底稿仍加载 C10（薪酬循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'J1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['C10'])
  })

  it('G1 底稿仍加载 C5（投资循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'G1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['C5'])
  })
})
