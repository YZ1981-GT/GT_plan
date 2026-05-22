/**
 * CrossCycleBreakageTab 前端测试
 * Validates: Requirements 2.1, 2.4, 2.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project' } }),
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

vi.mock('@/services/commonApi', () => ({
  runConsistencyCheck: vi.fn().mockResolvedValue({ all_consistent: true, checks: [] }),
  getConsistencyCheck: vi.fn().mockResolvedValue({ all_consistent: true, checks: [] }),
}))

import ConsistencyDashboard from '@/views/ConsistencyDashboard.vue'
import { api } from '@/services/apiProxy'

const mockBreakageData = {
  items: [
    { ref_id: 'CW-100', source_wp_code: 'D2-1', target_wp_code: 'E1-1', severity: 'blocking', reason: 'target_missing', last_checked_at: '2026-01-15T10:00:00Z' },
    { ref_id: 'CW-101', source_wp_code: 'F2-1', target_wp_code: 'H1-1', severity: 'warning', reason: 'target_stale', last_checked_at: '2026-01-15T09:00:00Z' },
    { ref_id: 'CW-102', source_wp_code: 'G7-1', target_wp_code: 'I3-1', severity: 'info', reason: 'target_stale', last_checked_at: '2026-01-14T08:00:00Z' },
  ],
  summary: { blocking: 1, required: 0, warning: 1, recommended: 0, info: 1 },
}

describe('CrossCycleBreakageTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders breakage tab and can switch to it', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBreakageData)
    const wrapper = mount(ConsistencyDashboard, {
      global: {
        stubs: {
          'el-tabs': true,
          'el-tab-pane': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-button': true,
          'el-alert': true,
          'el-row': true,
          'el-col': true,
          'el-empty': true,
          'el-icon': true,
          GtPageHeader: true,
        },
      },
    })
    await flushPromises()

    // Switch to breakage tab via vm
    const vm = wrapper.vm as any
    vm.activeTab = 'breakage'
    await flushPromises()

    // After switching, the breakage summary section should render
    expect(wrapper.find('.gt-breakage-summary').exists()).toBe(true)
  })

  it('displays summary data with correct counts', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBreakageData)
    const wrapper = mount(ConsistencyDashboard, {
      global: {
        stubs: {
          'el-tabs': true,
          'el-tab-pane': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-button': true,
          'el-alert': true,
          'el-row': true,
          'el-col': true,
          'el-empty': true,
          'el-icon': true,
          GtPageHeader: true,
        },
      },
    })
    await flushPromises()

    // Switch to breakage tab
    const vm = wrapper.vm as any
    vm.activeTab = 'breakage'
    await flushPromises()

    // Verify summary data is loaded correctly
    expect(vm.breakageSummary).not.toBeNull()
    expect(vm.breakageSummary.blocking).toBe(1)
    expect(vm.breakageSummary.warning).toBe(1)
    expect(vm.breakageSummary.info).toBe(1)
    expect(vm.breakageItems).toHaveLength(3)
  })

  it('calls API with correct project ID', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBreakageData)
    const wrapper = mount(ConsistencyDashboard, {
      global: {
        stubs: {
          'el-tabs': false,
          'el-tab-pane': false,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-button': true,
          'el-alert': true,
          'el-row': true,
          'el-col': true,
          'el-empty': true,
          'el-icon': true,
          GtPageHeader: true,
        },
      },
    })
    await flushPromises()

    // Switch to breakage tab to trigger fetch
    const vm = wrapper.vm as any
    vm.activeTab = 'breakage'
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/api/projects/test-project/cross-cycle-breakage')
  })

  it('navigates to source workpaper on row click', async () => {
    vi.mocked(api.get).mockResolvedValue(mockBreakageData)
    const wrapper = mount(ConsistencyDashboard, {
      global: {
        stubs: {
          'el-tabs': false,
          'el-tab-pane': false,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-button': true,
          'el-alert': true,
          'el-row': true,
          'el-col': true,
          'el-empty': true,
          'el-icon': true,
          GtPageHeader: true,
        },
      },
    })
    await flushPromises()

    // Call the row click handler directly
    const vm = wrapper.vm as any
    vm.onBreakageRowClick({ ref_id: 'CW-100', source_wp_code: 'D2-1', target_wp_code: 'E1-1', severity: 'blocking', reason: 'target_missing', last_checked_at: '' })

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'test-project', wpId: 'D2-1' },
    })
  })
})
