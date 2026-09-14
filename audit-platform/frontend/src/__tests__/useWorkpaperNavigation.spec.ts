/**
 * useWorkpaperNavigation — parseIndexRefs + A16 虚拟子码重定向单测
 *
 * 测试索引号字符串解析：多索引拆分、分隔符支持、不存在索引处理。
 * 测试 A16-1~7 虚拟子码重定向至 A16 + ?version= 。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── 使用 vi.hoisted 确保 mock 变量在 vi.mock 工厂内可用 ───
const { mockLookup, mockRouterPush, mockWarning, mockApiGet } = vi.hoisted(() => ({
  mockLookup: vi.fn(),
  mockRouterPush: vi.fn(),
  mockWarning: vi.fn(),
  mockApiGet: vi.fn(),
}))

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
    get: mockApiGet,
    post: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockRouterPush,
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: mockWarning, success: vi.fn(), error: vi.fn() },
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
    expect(refs[1].entry).toBeNull()
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
    expect(refs[0].exists).toBe(true)
  })

  it('混合分隔符+去重空白', () => {
    mockLookup.mockReturnValue(null)
    const { parseIndexRefs } = useWorkpaperNavigation()
    const refs = parseIndexRefs(' A1 , A2 、A3 ; A4 ')
    expect(refs).toHaveLength(4)
    expect(refs.map((r) => r.code)).toEqual(['A1', 'A2', 'A3', 'A4'])
  })
})

describe('navigateToWorkpaper — A16 虚拟子码重定向', () => {
  beforeEach(() => {
    mockRouterPush.mockReset()
    mockWarning.mockReset()
    mockApiGet.mockReset()
    mockLookup.mockReset()
  })

  it('A16-1 重定向至 A16 + ?version=A16-1', async () => {
    mockApiGet.mockResolvedValue({ wpId: 'wp-a16-uuid', exists: true })
    const { navigateToWorkpaper } = useWorkpaperNavigation()

    await navigateToWorkpaper('A16-1', 'proj-001')

    // 应解析 A16 的 wp_id
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/workpapers/index-resolve/A16',
      { params: { project_id: 'proj-001' } },
    )
    // 应跳转到 A16 编辑器 + version query
    expect(mockRouterPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/workpapers/wp-a16-uuid/edit',
      query: { version: 'A16-1' },
    })
  })

  it('A16-7 重定向至 A16 + ?version=A16-7', async () => {
    mockApiGet.mockResolvedValue({ wpId: 'wp-a16-uuid', exists: true })
    const { navigateToWorkpaper } = useWorkpaperNavigation()

    await navigateToWorkpaper('A16-7', 'proj-002')

    expect(mockRouterPush).toHaveBeenCalledWith({
      path: '/projects/proj-002/workpapers/wp-a16-uuid/edit',
      query: { version: 'A16-7' },
    })
  })

  it('A16-3 resolve 失败时降级至列表页', async () => {
    mockApiGet.mockRejectedValue(new Error('network'))
    const { navigateToWorkpaper } = useWorkpaperNavigation()

    await navigateToWorkpaper('A16-3', 'proj-001')

    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: { highlight: 'A16' },
    })
  })

  it('A16 本身走正常流程不重定向', async () => {
    mockLookup.mockReturnValue({ name: '管理层声明书', render_type: 'word_template' })
    mockApiGet.mockResolvedValue({ wpId: 'wp-a16-uuid', exists: true })
    const { navigateToWorkpaper } = useWorkpaperNavigation()

    await navigateToWorkpaper('A16', 'proj-001')

    // A16 不是虚拟子码，走正常 resolveRoute → WorkpaperEditor
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: 'wp-a16-uuid' },
    })
  })

  it('A16-8 不命中虚拟码范围，走正常流程', async () => {
    mockLookup.mockReturnValue(null)
    const { navigateToWorkpaper } = useWorkpaperNavigation()

    await navigateToWorkpaper('A16-8', 'proj-001')

    // registry.lookup 返回 null → 提示未知索引号
    expect(mockWarning).toHaveBeenCalledWith('未知索引号 A16-8')
  })
})
