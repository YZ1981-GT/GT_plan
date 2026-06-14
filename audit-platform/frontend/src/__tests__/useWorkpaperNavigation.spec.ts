/**
 * useWorkpaperNavigation — parseIndexRefs 单测
 *
 * 测试索引号字符串解析：多索引拆分、分隔符支持、不存在索引处理。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock registry — 模拟已加载的注册表
const mockLookup = vi.fn()
vi.mock('@/composables/useWorkpaperRegistry', () => ({
  useWorkpaperRegistry: () => ({
    load: vi.fn().mockResolvedValue(undefined),
    lookup: mockLookup,
    getAll: vi.fn().mockReturnValue({}),
    listByType: vi.fn().mockReturnValue({}),
    listByModule: vi.fn().mockReturnValue({}),
    getRenderTypes: vi.fn().mockReturnValue([]),
    invalidate: vi.fn(),
    loaded: { value: true },
  }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import { useWorkpaperNavigation } from '@/composables/useWorkpaperNavigation'

describe('parseIndexRefs', () => {
  beforeEach(() => {
    mockLookup.mockReset()
  })

  it('空字符串返回空数组', () => {
    const { parseIndexRefs } = useWorkpaperNavigation()
    expect(parseIndexRefs('')).toEqual([])
    expect(parseIndexRefs('  ')).toEqual([])
  })

  it('单个索引号正常解析', () => {
    mockLookup.mockReturnValue({ name: '财务报告程序表', render_type: 'html_procedure' })
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('A1')
    expect(refs).toHaveLength(1)
    expect(refs[0].code).toBe('A1')
    expect(refs[0].entry).not.toBeNull()
  })

  it('逗号分隔多个索引号', () => {
    mockLookup.mockImplementation((code: string) =>
      code === 'A1-13' ? { name: '分析性复核', render_type: 'auto_report' } : null,
    )
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('A1-13,A1-14')
    expect(refs).toHaveLength(2)
    expect(refs[0].code).toBe('A1-13')
    expect(refs[0].entry).not.toBeNull()
    expect(refs[1].code).toBe('A1-14')
    expect(refs[1].entry).toBeNull() // 不存在于注册表
  })

  it('顿号分隔多个索引号', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('A1-13、A1-14、A2')
    expect(refs).toHaveLength(3)
    expect(refs.map((r) => r.code)).toEqual(['A1-13', 'A1-14', 'A2'])
  })

  it('分号分隔', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('A5-1;A5-2；A5-3')
    expect(refs).toHaveLength(3)
  })

  it('空格分隔', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('A1 A2 A3')
    expect(refs).toHaveLength(3)
  })

  it('不存在的索引号 entry 为 null', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs('ZZZ-999')
    expect(refs).toHaveLength(1)
    expect(refs[0].code).toBe('ZZZ-999')
    expect(refs[0].entry).toBeNull()
    expect(refs[0].exists).toBe(true) // exists 默认 true，实际异步检查
  })

  it('混合分隔符+去重空白', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs(' A1 , A2 、A3 ; A4 ')
    expect(refs).toHaveLength(4)
    expect(refs.map((r) => r.code)).toEqual(['A1', 'A2', 'A3', 'A4'])
  })
})
