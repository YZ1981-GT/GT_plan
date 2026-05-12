/**
 * usePenetrate composable 单测
 * 验证穿透导航逻辑：路由跳转参数正确性
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({
    params: { projectId: 'proj-001' },
    query: { year: '2024' },
  }),
}))

import { usePenetrate } from '@/composables/usePenetrate'

describe('usePenetrate', () => {
  beforeEach(() => {
    mockPush.mockClear()
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
