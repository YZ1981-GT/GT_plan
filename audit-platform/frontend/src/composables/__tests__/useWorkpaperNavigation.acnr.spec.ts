/**
 * useWorkpaperNavigation ACNR 导航单测 — task 15.3 / Property 18
 *
 * 覆盖 task 15.1 为 `navigateToWorkpaper` 引入的 ACNR 前置解析行为
 * （15.2 的 parseIndexRef.acnr-parity 契约测试已覆盖 11 命名空间「解析器 parity」，
 *  此处不重复，只在文末做一次轻量交叉引用断言）：
 *
 *   1. ACNR resolveIndex 命中（found=true + jump_route）→ router.push(jump_route)，
 *      且 **不** 触及 legacy registry.lookup / index-resolve API 路径。
 *   2. ACNR miss（found=false）或 resolveIndex 抛异常 → 静默回退到既有
 *      registry.load + registry.lookup + index-resolve API + resolveRoute 路径（无崩溃、无回归）。
 *   3. A16-1~7 虚拟码路径不变：ACNR 步骤根本不会被触及（在虚拟码分支已 return）。
 *
 * Property 18: Frontend Index Parser Parity（parity 部分见 15.2 契约测试）
 * Validates: Requirements 13.3
 * _Requirements: 13.1, 13.2, 13.4_
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Hoisted spies（vi.mock 工厂在提升后仍可安全引用） ──────────────────────────
const h = vi.hoisted(() => ({
  pushSpy: vi.fn(),
  loadSpy: vi.fn().mockResolvedValue(undefined),
  lookupSpy: vi.fn(),
  apiGetSpy: vi.fn(),
  resolveIndexSpy: vi.fn(),
  warnSpy: vi.fn(),
}))

// vue-router：只需 push
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: h.pushSpy }),
}))

// 底稿注册表（legacy 回退路径）
vi.mock('../useWorkpaperRegistry', () => ({
  useWorkpaperRegistry: () => ({ load: h.loadSpy, lookup: h.lookupSpy }),
}))

// index-resolve API（legacy 回退路径）
vi.mock('@/services/apiProxy', () => ({
  api: { get: h.apiGetSpy },
}))

// ACNR 前置解析
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveIndex: h.resolveIndexSpy }),
}))

// ElMessage 副作用隔离
vi.mock('element-plus', () => ({
  ElMessage: { warning: h.warnSpy, error: vi.fn(), success: vi.fn() },
}))

import { useWorkpaperNavigation } from '../useWorkpaperNavigation'

const PROJECT_ID = 'proj-1'

beforeEach(() => {
  vi.clearAllMocks()
  h.loadSpy.mockResolvedValue(undefined)
})

// ─── 1. ACNR 命中 → 直接跳 jump_route，不走 legacy ────────────────────────────
describe('navigateToWorkpaper — ACNR 命中（Req 13.1）', () => {
  it('found=true + jump_route → router.push(jump_route)，不触及 registry / index-resolve', async () => {
    const jumpRoute = '/projects/proj-1/workpapers/wp-9/edit'
    h.resolveIndexSpy.mockResolvedValue({ found: true, jump_route: jumpRoute })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('D2', PROJECT_ID)

    // ACNR 前置解析用 'wp:'+wpCode 前缀
    expect(h.resolveIndexSpy).toHaveBeenCalledWith('wp:D2')
    // 跳转到 ACNR 返回的 jump_route
    expect(h.pushSpy).toHaveBeenCalledTimes(1)
    expect(h.pushSpy).toHaveBeenCalledWith(jumpRoute)
    // 命中即短路：legacy 路径完全不触及
    expect(h.lookupSpy).not.toHaveBeenCalled()
    expect(h.apiGetSpy).not.toHaveBeenCalled()
    expect(h.warnSpy).not.toHaveBeenCalled()
  })

  it('found=true 但缺 jump_route → 不短路，回退 legacy 路径（无回归）', async () => {
    h.resolveIndexSpy.mockResolvedValue({ found: true }) // 无 jump_route
    h.lookupSpy.mockReturnValue({ render_type: 'html_procedure', categories: [], upstream: [], downstream: [] })
    h.apiGetSpy.mockResolvedValue({ wpId: 'wp-1', exists: true })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('D2', PROJECT_ID)

    // 没有用不存在的 jump_route 跳转
    expect(h.pushSpy).not.toHaveBeenCalledWith(undefined)
    // 落入 legacy 路径
    expect(h.lookupSpy).toHaveBeenCalledWith('D2')
    expect(h.apiGetSpy).toHaveBeenCalled()
    expect(h.pushSpy).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: PROJECT_ID, wpId: 'wp-1' },
    })
  })
})

// ─── 2. ACNR miss / 异常 → 静默回退 legacy ────────────────────────────────────
describe('navigateToWorkpaper — ACNR miss/异常静默回退（Req 13.2）', () => {
  it('found=false → 回退 registry.lookup + index-resolve + resolveRoute', async () => {
    h.resolveIndexSpy.mockResolvedValue({ found: false, error: 'not_found' })
    h.lookupSpy.mockReturnValue({ render_type: 'html_procedure', categories: [], upstream: [], downstream: [] })
    h.apiGetSpy.mockResolvedValue({ wpId: 'wp-42', exists: true })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('D3', PROJECT_ID)

    expect(h.resolveIndexSpy).toHaveBeenCalledWith('wp:D3')
    // legacy 路径被完整调用
    expect(h.loadSpy).toHaveBeenCalled()
    expect(h.lookupSpy).toHaveBeenCalledWith('D3')
    expect(h.apiGetSpy).toHaveBeenCalledWith(
      '/api/workpapers/index-resolve/D3',
      { params: { project_id: PROJECT_ID } },
    )
    expect(h.pushSpy).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: PROJECT_ID, wpId: 'wp-42' },
    })
  })

  it('resolveIndex 抛异常 → 静默回退 legacy，不崩溃', async () => {
    h.resolveIndexSpy.mockRejectedValue(new Error('ACNR down'))
    h.lookupSpy.mockReturnValue({
      render_type: 'auto_report',
      module: 'report_analysis',
      categories: [], upstream: [], downstream: [],
    })
    h.apiGetSpy.mockResolvedValue({ wpId: 'wp-7', exists: true })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await expect(navigateToWorkpaper('A5', PROJECT_ID)).resolves.toBeUndefined()

    // 回退路径生效
    expect(h.lookupSpy).toHaveBeenCalledWith('A5')
    expect(h.apiGetSpy).toHaveBeenCalled()
    // auto_report + report_analysis → FinancialReport
    expect(h.pushSpy).toHaveBeenCalledWith({
      name: 'FinancialReport',
      params: { projectId: PROJECT_ID },
      query: { tab: 'A5' },
    })
  })

  it('回退后 registry 未命中 → ElMessage.warning，不跳转', async () => {
    h.resolveIndexSpy.mockResolvedValue({ found: false })
    h.lookupSpy.mockReturnValue(null)

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('ZZ99', PROJECT_ID)

    expect(h.warnSpy).toHaveBeenCalledWith('未知索引号 ZZ99')
    expect(h.pushSpy).not.toHaveBeenCalled()
  })

  it('回退后 index-resolve 报 exists=false → 提示未生成，不跳转', async () => {
    h.resolveIndexSpy.mockResolvedValue({ found: false })
    h.lookupSpy.mockReturnValue({ render_type: 'html_procedure', categories: [], upstream: [], downstream: [] })
    h.apiGetSpy.mockResolvedValue({ wpId: null, exists: false })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('D9', PROJECT_ID)

    expect(h.warnSpy).toHaveBeenCalledWith('该底稿尚未生成')
    expect(h.pushSpy).not.toHaveBeenCalled()
  })
})

// ─── 3. A16-1~7 虚拟码路径不变：ACNR 步骤不触及（Req 13.4） ─────────────────────
describe('navigateToWorkpaper — A16 虚拟码路径不变（Req 13.4）', () => {
  it('A16-3 → 走 A16 父码 index-resolve，ACNR resolveIndex 完全不触及', async () => {
    h.apiGetSpy.mockResolvedValue({ wpId: 'wp-a16', exists: true })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('A16-3', PROJECT_ID)

    // 虚拟码分支在 ACNR 前置解析之前 return
    expect(h.resolveIndexSpy).not.toHaveBeenCalled()
    // 解析 A16 父码
    expect(h.apiGetSpy).toHaveBeenCalledWith(
      '/api/workpapers/index-resolve/A16',
      { params: { project_id: PROJECT_ID } },
    )
    // 跳到 A16 编辑器并带 ?version=A16-3
    expect(h.pushSpy).toHaveBeenCalledWith({
      path: `/projects/${PROJECT_ID}/workpapers/wp-a16/edit`,
      query: { version: 'A16-3' },
    })
  })

  it('A16-5 且 A16 未解析 → 回退列表页 highlight A16，仍不触及 ACNR', async () => {
    h.apiGetSpy.mockResolvedValue({ wpId: null, exists: false })

    const { navigateToWorkpaper } = useWorkpaperNavigation()
    await navigateToWorkpaper('A16-5', PROJECT_ID)

    expect(h.resolveIndexSpy).not.toHaveBeenCalled()
    expect(h.pushSpy).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: PROJECT_ID },
      query: { highlight: 'A16' },
    })
  })
})

// ─── 4. 解析器 parity 轻量交叉引用（完整 11 命名空间见 15.2 契约测试） ───────────
describe('Property 18 — 解析器 parity 轻量交叉引用（完整覆盖见 parseIndexRef.acnr-parity.test.ts）', () => {
  it('代表性命名空间 wp/cell/TB：utils 与 ACNR 分类等价', async () => {
    const { parseIndexRef: utilsParse } = await import('../../utils/parseIndexRef')
    const { parseIndexRef: acnrParse } = await import('@/services/acnr/resolveUri')

    for (const input of ['wp:D2', 'cell:D2-1!B23', 'TB:1122']) {
      const u = utilsParse(input)
      const a = acnrParse(input)
      expect(u).not.toBeNull()
      expect(a).not.toBeNull()
      expect(u?.ns).toBe(a?.namespace)
      expect(u?.target).toBe(a?.target)
    }
  })
})
