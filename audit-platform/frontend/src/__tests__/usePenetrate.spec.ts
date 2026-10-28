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

import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectStore } from '@/stores/project'

describe('usePenetrate', () => {
  beforeEach(() => {
    mockPush.mockClear()
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
    const p = usePenetrate()
    p.toLedger('1001')
    p.toWorkpaperFromNote('D2', { sheet: 'S1' })
    expect(mockPush).toHaveBeenNthCalledWith(1, { path: '/projects/proj-001/ledger', query: { code: '1001' } })
    expect(mockPush).toHaveBeenNthCalledWith(2, { path: '/projects/proj-001/workpapers', query: { code: 'D2', sheet: 'S1' } })
  })

  it('toLedger navigates to ledger with account code and year', () => {
    const { toLedger } = usePenetrate()
    toLedger('1001')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/ledger',
      query: { code: '1001', year: '2024' },
    })
  })

  it('toWorkpaper navigates to workpapers with code', () => {
    const { toWorkpaper } = usePenetrate()
    toWorkpaper('D-100')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-001/workpapers',
      query: { code: 'D-100' },
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
