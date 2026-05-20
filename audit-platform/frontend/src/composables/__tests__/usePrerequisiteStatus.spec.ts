/**
 * usePrerequisiteStatus.spec.ts — H-F9 Task 2.20
 *
 * 验证 H_CYCLE_PREREQUISITES 配置 + 条件逻辑：
 * - C6 所有 H 底稿共用
 * - C7 仅 H2 路径强制
 * - C14 仅 H8/H9 路径强制
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

describe('usePrerequisiteStatus — H_CYCLE_PREREQUISITES 路由匹配', () => {
  it('H1 底稿仅加载 C6（固定资产控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H1')
    await vi.dynamicImportSettled()
    // Wait for async refresh
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).not.toContain('C7')
    expect(codes).not.toContain('C14')
    expect(codes).toHaveLength(1)
  })

  it('H2 底稿加载 C6 + C7（在建工程控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).toContain('C7')
    expect(codes).not.toContain('C14')
    expect(codes).toHaveLength(2)
  })

  it('H2-5（在建工程子 sheet）也加载 C6 + C7', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H2-5')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).toContain('C7')
    expect(codes).not.toContain('C14')
    expect(codes).toHaveLength(2)
  })

  it('H8 底稿加载 C6 + C14（租赁循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H8')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).toContain('C14')
    expect(codes).not.toContain('C7')
    expect(codes).toHaveLength(2)
  })

  it('H9 底稿加载 C6 + C14（租赁循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H9')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).toContain('C14')
    expect(codes).not.toContain('C7')
    expect(codes).toHaveLength(2)
  })

  it('H9-1（租赁负债子 sheet）也加载 C6 + C14', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'H9-1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C6')
    expect(codes).toContain('C14')
    expect(codes).not.toContain('C7')
    expect(codes).toHaveLength(2)
  })

  it('H0/H3/H4/H5/H6/H7/H10 仅加载 C6', async () => {
    for (const code of ['H0', 'H3', 'H4', 'H5', 'H6', 'H7', 'H10']) {
      mockGet.mockRejectedValue(new Error('Not implemented'))
      const { items } = usePrerequisiteStatus('proj-1', code)
      await new Promise((r) => setTimeout(r, 10))

      const codes = items.value.map((i) => i.wp_code)
      expect(codes).toEqual(['C6'])
    }
  })

  it('H 循环 fallback 时 overall 为 blocked', async () => {
    const { overall } = usePrerequisiteStatus('proj-1', 'H1')
    await new Promise((r) => setTimeout(r, 10))

    expect(overall.value).toBe('blocked')
  })
})

describe('usePrerequisiteStatus — D/F 循环路由不受影响', () => {
  it('D4 底稿加载 D_CYCLE_PREREQUISITES（B23-1/C2/B51-5）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'D4')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['B23-1', 'C2', 'B51-5'])
  })

  it('F2 底稿加载 F_CYCLE_PREREQUISITES（B23-3/C4/B51-4）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'F2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toEqual(['B23-3', 'C4', 'B51-4'])
  })
})

describe('usePrerequisiteStatus — I_CYCLE_PREREQUISITES 路由匹配（I-F9 Task 2.22）', () => {
  it('I1 底稿仅加载 C8（无形资产及其他长期资产循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'I1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C8')
    expect(codes).not.toContain('C9')
    expect(codes).toHaveLength(1)
  })

  it('I2 底稿加载 C8 + C9（开发支出走研发循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'I2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C8')
    expect(codes).toContain('C9')
    expect(codes).toHaveLength(2)
  })

  it('I2-6（资本化时点判断子 sheet）也加载 C8 + C9', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'I2-6')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C8')
    expect(codes).toContain('C9')
    expect(codes).toHaveLength(2)
  })

  it('I6 底稿加载 C8 + C9（研发费用走研发循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'I6')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C8')
    expect(codes).toContain('C9')
    expect(codes).toHaveLength(2)
  })

  it('I6-2（研发费用月度明细子 sheet）也加载 C8 + C9', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'I6-2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C8')
    expect(codes).toContain('C9')
    expect(codes).toHaveLength(2)
  })

  it('I3/I4/I5 仅加载 C8（不涉及研发循环）', async () => {
    for (const code of ['I3', 'I4', 'I5']) {
      mockGet.mockRejectedValue(new Error('Not implemented'))
      const { items } = usePrerequisiteStatus('proj-1', code)
      await new Promise((r) => setTimeout(r, 10))

      const codes = items.value.map((i) => i.wp_code)
      expect(codes).toEqual(['C8'])
    }
  })

  it('I 循环 fallback 时 overall 为 blocked', async () => {
    const { overall } = usePrerequisiteStatus('proj-1', 'I1')
    await new Promise((r) => setTimeout(r, 10))

    expect(overall.value).toBe('blocked')
  })
})

describe('usePrerequisiteStatus — J_CYCLE_PREREQUISITES 路由匹配（J-F5 Task 2.3/2.4）', () => {
  it('J1 底稿加载 C10（薪酬循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'J1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C10')
    expect(codes).toHaveLength(1)
  })

  it('J2 底稿加载 C10（长期应付职工薪酬同样命中 ^J\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'J2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C10')
    expect(codes).toHaveLength(1)
  })

  it('J3 底稿加载 C10（股份支付同样命中 ^J\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'J3')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C10')
    expect(codes).toHaveLength(1)
  })

  it('J1-6（子 sheet）也命中 ^J\\d 路由', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'J1-6')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C10')
    expect(codes).toHaveLength(1)
  })

  it('J 循环 fallback 时 overall 为 blocked', async () => {
    const { overall } = usePrerequisiteStatus('proj-1', 'J1')
    await new Promise((r) => setTimeout(r, 10))

    expect(overall.value).toBe('blocked')
  })

  it('J 循环不影响 D/F/H/I/G 路由', async () => {
    // D 循环仍然加载 D_CYCLE_PREREQUISITES
    const { items: dItems } = usePrerequisiteStatus('proj-1', 'D4')
    await new Promise((r) => setTimeout(r, 10))
    expect(dItems.value.map((i) => i.wp_code)).toEqual(['B23-1', 'C2', 'B51-5'])

    // G 循环仍然加载 G_CYCLE_PREREQUISITES
    const { items: gItems } = usePrerequisiteStatus('proj-1', 'G1')
    await new Promise((r) => setTimeout(r, 10))
    expect(gItems.value.map((i) => i.wp_code)).toEqual(['C5'])
  })
})

describe('usePrerequisiteStatus — K_CYCLE_PREREQUISITES 路由匹配（K-F5 Task 2.3/2.4）', () => {
  it('K1 底稿加载 C11（管理循环控制测试）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K1')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C11')
    expect(codes).toHaveLength(1)
  })

  it('K8 底稿加载 C11（销售费用同样命中 ^K\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K8')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C11')
    expect(codes).toHaveLength(1)
  })

  it('K9 底稿加载 C11（管理费用同样命中 ^K\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K9')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C11')
    expect(codes).toHaveLength(1)
  })

  it('K11 底稿加载 C11（资产减值损失同样命中 ^K\\d）', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K11')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C11')
    expect(codes).toHaveLength(1)
  })

  it('K8-2（子 sheet）也命中 ^K\\d 路由', async () => {
    const { items } = usePrerequisiteStatus('proj-1', 'K8-2')
    await new Promise((r) => setTimeout(r, 10))

    const codes = items.value.map((i) => i.wp_code)
    expect(codes).toContain('C11')
    expect(codes).toHaveLength(1)
  })

  it('K 循环 fallback 时 overall 为 blocked', async () => {
    const { overall } = usePrerequisiteStatus('proj-1', 'K8')
    await new Promise((r) => setTimeout(r, 10))

    expect(overall.value).toBe('blocked')
  })

  it('K 循环 fallback 时 banner type 为 error（红色横幅）', async () => {
    const { banner } = usePrerequisiteStatus('proj-1', 'K8')
    await new Promise((r) => setTimeout(r, 10))

    expect(banner.value.type).toBe('error')
    expect(banner.value.message).toContain('C11')
  })

  it('K 循环不影响 D/F/H/I/G/J 路由', async () => {
    // D 循环
    const { items: dItems } = usePrerequisiteStatus('proj-1', 'D4')
    await new Promise((r) => setTimeout(r, 10))
    expect(dItems.value.map((i) => i.wp_code)).toEqual(['B23-1', 'C2', 'B51-5'])

    // J 循环
    const { items: jItems } = usePrerequisiteStatus('proj-1', 'J1')
    await new Promise((r) => setTimeout(r, 10))
    expect(jItems.value.map((i) => i.wp_code)).toEqual(['C10'])

    // G 循环
    const { items: gItems } = usePrerequisiteStatus('proj-1', 'G1')
    await new Promise((r) => setTimeout(r, 10))
    expect(gItems.value.map((i) => i.wp_code)).toEqual(['C5'])
  })
})

describe('usePrerequisiteStatus — API 成功时使用服务端数据', () => {
  it('API 返回数据时不使用 fallback', async () => {
    mockGet.mockResolvedValue({
      items: [
        { wp_code: 'C6', wp_name: '固定资产循环控制测试', state: 'completed' },
      ],
      overall: 'ready',
    })

    const { items, overall } = usePrerequisiteStatus('proj-1', 'H1')
    await new Promise((r) => setTimeout(r, 10))

    expect(items.value).toHaveLength(1)
    expect(items.value[0].state).toBe('completed')
    expect(overall.value).toBe('ready')
  })
})
