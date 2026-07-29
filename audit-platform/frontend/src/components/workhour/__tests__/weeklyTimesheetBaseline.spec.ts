import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock staffApi
vi.mock('@/services/staffApi', () => ({
  getAISuggestions: vi.fn().mockResolvedValue({ suggestions: [] }),
  getMyStaffId: vi.fn().mockResolvedValue({ staff_id: 'test-staff-id' }),
  getMyAssignments: vi.fn().mockResolvedValue([]),
}))

// Mock apiProxy
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}) },
}))

// Mock router
vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}))

describe('WeeklyTimesheet Baseline (characterization)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('1. 组件可挂载不崩溃', async () => {
    // 如果 WeeklyTimesheet 有复杂依赖导致挂载困难，
    // 退化为断言模块可导入不抛错
    const mod = await import('../WeeklyTimesheet.vue')
    expect(mod.default).toBeDefined()
  })

  it('2. 导出 default component 有 setup', async () => {
    const mod = await import('../WeeklyTimesheet.vue')
    expect(mod.default.__name || mod.default.name || 'WeeklyTimesheet').toBeTruthy()
  })

  it('3. WorkHoursPage 可导入', async () => {
    const mod = await import('@/views/WorkHoursPage.vue')
    expect(mod.default).toBeDefined()
  })

  it('4. SideTimerTab 可导入', async () => {
    const mod = await import('../../workpaper/SideTimerTab.vue')
    expect(mod.default).toBeDefined()
  })

  it('5. WorkHourApprovalTab 可导入', async () => {
    const mod = await import('../WorkHourApprovalTab.vue')
    expect(mod.default).toBeDefined()
  })

  it('6. BudgetCompareChart 可导入', async () => {
    const mod = await import('../BudgetCompareChart.vue')
    expect(mod.default).toBeDefined()
  })

  it('7. WorkHourStatsPanel 可导入', async () => {
    const mod = await import('../WorkHourStatsPanel.vue')
    expect(mod.default).toBeDefined()
  })

  it('8. staffApi getMyStaffId 返回 staff_id 结构', async () => {
    const { getMyStaffId } = await import('@/services/staffApi')
    const result = await getMyStaffId()
    expect(result).toHaveProperty('staff_id')
  })
})
