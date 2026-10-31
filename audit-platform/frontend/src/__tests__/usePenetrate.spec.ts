/**
 * usePenetrate composable 单测
 * 验证穿透导航逻辑：路由跳转参数正确性
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock vue-router
const mockPush = vi.fn()
const mockRoute: { params: Record<string, string>; query: Record<string, string> } = {
  params: { projectId: 'proj-001' },
  query: { year: '2024' },
}
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => mockRoute,
}))

const { resolveMock, warnMock } = vi.hoisted(() => ({ resolveMock: vi.fn(), warnMock: vi.fn() }))
vi.mock('@/services/resolveWorkpaperByCode', () => ({ resolveWorkpaperByCode: resolveMock }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { warning: warnMock, error: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectStore } from '@/stores/project'

const WP_D2 = '3f2b1c0d-9e8f-4a7b-8c6d-5e4f3a2b1c0d'

describe('usePenetrate', () => {
  beforeEach(() => {
    mockPush.mockClear()
    resolveMock.mockReset()
    warnMock.mockReset()
    mockRoute.query = { year: '2024' }
    setActivePinia(createPinia())
  })

  it('路由没带年度：取项目 store 的年度（spec post-push-residual-defect-closure 6.5.3）', () => {
    mockRoute.query = {}
    useProjectStore().year = 2025
    usePenetrate().toLedger('1001')
    expect(mockPush).toHaveBeenCalledWith({ path: '/projects/proj-001/ledger', query: { code: '1001', year: '2025' } })
  })

  it('路由与 store 都没有年度：跳转不带 year（原先兜底去年）', () => {
    mockRoute.query = {}
    usePenetrate().toLedger('1001')
    expect(mockPush).toHaveBeenCalledWith({ path: '/projects/proj-001/ledger', query: { code: '1001' } })
  })

  it('toWorkpaperFromNote：按编码取本项目底稿后打开编辑器并带 ?sheet=&cell=（原先跳底稿列表页，列表页不读定位参数）', async () => {
    resolveMock.mockResolvedValueOnce({ wpId: WP_D2 })
    await usePenetrate().toWorkpaperFromNote('D2', { sheet: 'S1', cell: 'B5' })
    expect(resolveMock).toHaveBeenCalledWith('proj-001', 'D2', true)
    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_D2 },
      query: { sheet: 'S1', cell: 'B5' },
    })
    expect(warnMock).not.toHaveBeenCalled()
  })

  it('toWorkpaperFromNote：本项目没有该底稿时提示原因、不跳转', async () => {
    resolveMock.mockResolvedValue(null)
    await usePenetrate().toWorkpaperFromNote('Z9')
    expect(mockPush).not.toHaveBeenCalled()
    expect(warnMock).toHaveBeenCalledWith('本项目未找到底稿 Z9（可能尚未生成）')
  })

  it('toLedger navigates to ledger with account code and year', () => {
    const { toLedger } = usePenetrate()
    toLedger('1001')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/ledger',
      query: { code: '1001', year: '2024' },
    })
  })

  it('toWorkpaper navigates to workpapers with highlight（列表页按它定位该行）', () => {
    const { toWorkpaper } = usePenetrate()
    toWorkpaper('D-100')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/workpapers',
      query: { highlight: 'D-100' },
    })
  })

  it('toReportRow navigates to reports with type and row code', () => {
    const { toReportRow } = usePenetrate()
    toReportRow('balance_sheet', 'BS-001')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/reports',
      query: { tab: 'balance_sheet', row: 'BS-001', year: '2024' },
    })
  })

  it('toAdjustment navigates to adjustments with account', () => {
    const { toAdjustment } = usePenetrate()
    toAdjustment('6001')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/adjustments',
      query: { account: '6001', year: '2024' },
    })
  })

  it('toMisstatement navigates to misstatements with id', () => {
    const { toMisstatement } = usePenetrate()
    toMisstatement('ms-abc-123')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/misstatements',
      query: { id: 'ms-abc-123', year: '2024' },
    })
  })

  it('toNote navigates to disclosure notes with section', () => {
    const { toNote } = usePenetrate()
    toNote('section-5')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/disclosure-notes',
      query: { section: 'section-5', year: '2024' },
    })
  })

  it('toWorkpaperEditor navigates to workpaper edit page', () => {
    const { toWorkpaperEditor } = usePenetrate()
    toWorkpaperEditor('wp-uuid-001')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/workpapers/wp-uuid-001/edit',
    })
  })
})
