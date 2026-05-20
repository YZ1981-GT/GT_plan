/**
 * test_n_prerequisite.spec.ts — N-F5 Task 2.4
 *
 * 验证 N_CYCLE_PREREQUISITES=[C12] 配置 + ^N\d 路由：
 * - N 循环前置底稿为 C12（税金循环控制测试）
 * - ^N\d 路由匹配 N1~N5 所有底稿
 * - 前置横幅正确显示 C12 状态（complete/incomplete/not_started）
 * - 其他循环（D/F/H/K/L/M）路由不受影响
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

describe('usePrerequisiteStatus — N_CYCLE_PREREQUISITES 路由匹配（N-F5 Task 2.4）', () => {
  it('N2 底稿加载 C12 前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(items.value[0].wp_name).toBe('税金循环控制测试')
    expect(overall.value).toBe('blocked')
  })

  it('N1 底稿加载 C12 前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N1')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })

  it('N3 底稿加载 C12 前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N3')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })

  it('N4 底稿加载 C12 前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N4')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })

  it('N5 底稿加载 C12 前置底稿', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N5')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })

  it('N2-1 子表路由到 N 循环（C12 前置）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'N2-1')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })

  it('大小写不敏感：n2 → N 循环（C12 前置）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'n2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C12'])
    expect(overall.value).toBe('blocked')
  })
})

describe('usePrerequisiteStatus — N 循环 API 成功返回场景', () => {
  it('C12 已完成 → overall=ready + 绿色横幅', async () => {
    mockGet.mockResolvedValue({
      items: [
        { wp_code: 'C12', wp_name: '税金循环控制测试', state: 'completed', conclusion: '有效' },
      ],
      overall: 'ready',
    })
    const { items, overall, banner } = usePrerequisiteStatus('proj-1', 'N2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value[0].state).toBe('completed')
    expect(overall.value).toBe('ready')
    expect(banner.value.type).toBe('success')
  })

  it('C12 进行中 → overall=partial + 黄色横幅', async () => {
    mockGet.mockResolvedValue({
      items: [
        { wp_code: 'C12', wp_name: '税金循环控制测试', state: 'in_progress' },
      ],
      overall: 'partial',
    })
    const { items, overall, banner } = usePrerequisiteStatus('proj-1', 'N2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value[0].state).toBe('in_progress')
    expect(overall.value).toBe('partial')
    expect(banner.value.type).toBe('warning')
  })

  it('C12 未开始 → overall=blocked + 红色横幅', async () => {
    mockGet.mockResolvedValue({
      items: [
        { wp_code: 'C12', wp_name: '税金循环控制测试', state: 'pending' },
      ],
      overall: 'blocked',
    })
    const { items, overall, banner } = usePrerequisiteStatus('proj-1', 'N2')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value[0].state).toBe('pending')
    expect(overall.value).toBe('blocked')
    expect(banner.value.type).toBe('error')
  })
})

describe('usePrerequisiteStatus — N 循环不影响其他循环路由', () => {
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

  it('M6 底稿仍加载 M_CYCLE_PREREQUISITES（空数组 → ready）', async () => {
    const { items, overall } = usePrerequisiteStatus('proj-1', 'M6')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value).toEqual([])
    expect(overall.value).toBe('ready')
  })

  it('H1 底稿仍加载 H_CYCLE_PREREQUISITES（C6）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H1')
    await new Promise((r) => setTimeout(r, 10))
    expect(items.value.map((i) => i.wp_code)).toEqual(['C6'])
  })
})
