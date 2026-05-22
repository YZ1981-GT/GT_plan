/**
 * ArchiveCompletenessReport 前端测试
 * Validates: Requirements 3.1, 3.4, 3.5
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
    post: vi.fn(),
  },
}))

vi.mock('@/services/commonApi', () => ({
  runConsistencyCheck: vi.fn(),
  getConsistencyCheck: vi.fn(),
}))

import ArchiveWizard from '@/views/ArchiveWizard.vue'
import { api } from '@/services/apiProxy'

const mockCompletenessReport = {
  categories: [
    { category: 'missing', count: 2, items: [{ wp_code: 'D2-1', wp_name: '销售审定表', assignee: '张三', status: '缺失' }, { wp_code: 'E1-1', wp_name: '货币资金', assignee: '李四', status: '缺失' }], is_blocking: true },
    { category: 'unsigned', count: 1, items: [{ wp_code: 'F2-1', wp_name: '存货审定表', assignee: '王五', status: '未签字' }], is_blocking: true },
    { category: 'unresolved_reviews', count: 0, items: [], is_blocking: false },
    { category: 'stale', count: 1, items: [{ wp_code: 'H1-1', wp_name: '固定资产', assignee: '赵六', status: 'stale' }], is_blocking: false },
  ],
  can_proceed: false,
  generated_at: '2026-01-15T10:00:00Z',
}

const mockEmptyReport = {
  categories: [
    { category: 'missing', count: 0, items: [], is_blocking: true },
    { category: 'unsigned', count: 0, items: [], is_blocking: true },
    { category: 'unresolved_reviews', count: 0, items: [], is_blocking: false },
    { category: 'stale', count: 0, items: [], is_blocking: false },
  ],
  can_proceed: true,
  generated_at: '2026-01-15T10:00:00Z',
}

describe('ArchiveCompletenessReport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders completeness report panel with categories', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('archive-completeness-report')) return Promise.resolve(mockCompletenessReport)
      if (url.includes('archive-readiness')) return Promise.resolve({ ready: false, groups: [] })
      return Promise.resolve({})
    })

    const wrapper = mount(ArchiveWizard, {
      global: {
        stubs: {
          'el-steps': true,
          'el-step': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': false,
          'el-icon': true,
          'el-alert': true,
          GtPageHeader: true,
          GateReadinessPanel: true,
          InfoFilled: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('归档前完整性自检报告')
  })

  it('highlights blocking categories', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('archive-completeness-report')) return Promise.resolve(mockCompletenessReport)
      if (url.includes('archive-readiness')) return Promise.resolve({ ready: false, groups: [] })
      return Promise.resolve({})
    })

    const wrapper = mount(ArchiveWizard, {
      global: {
        stubs: {
          'el-steps': true,
          'el-step': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': false,
          'el-icon': true,
          'el-alert': true,
          GtPageHeader: true,
          GateReadinessPanel: true,
          InfoFilled: true,
        },
      },
    })
    await flushPromises()

    // Blocking categories should have the blocking class
    const blockingCategories = wrapper.findAll('.gt-completeness-blocking')
    expect(blockingCategories.length).toBeGreaterThanOrEqual(1)
  })

  it('sets can_proceed=false when blocking items exist', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('archive-completeness-report')) return Promise.resolve(mockCompletenessReport)
      if (url.includes('archive-readiness')) return Promise.resolve({ ready: true, groups: [] })
      return Promise.resolve({})
    })

    const wrapper = mount(ArchiveWizard, {
      global: {
        stubs: {
          'el-steps': true,
          'el-step': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-icon': true,
          'el-alert': true,
          GtPageHeader: true,
          GateReadinessPanel: true,
          InfoFilled: true,
        },
      },
    })
    await flushPromises()

    // Verify the completeness report data is loaded and can_proceed is false
    const vm = wrapper.vm as any
    expect(vm.completenessReport).not.toBeNull()
    expect(vm.completenessReport.can_proceed).toBe(false)
  })

  it('sets can_proceed=true for empty report', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('archive-completeness-report')) return Promise.resolve(mockEmptyReport)
      if (url.includes('archive-readiness')) return Promise.resolve({ ready: true, groups: [] })
      return Promise.resolve({})
    })

    const wrapper = mount(ArchiveWizard, {
      global: {
        stubs: {
          'el-steps': true,
          'el-step': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-icon': true,
          'el-alert': true,
          GtPageHeader: true,
          GateReadinessPanel: true,
          InfoFilled: true,
        },
      },
    })
    await flushPromises()

    // Verify the completeness report data is loaded and can_proceed is true
    const vm = wrapper.vm as any
    expect(vm.completenessReport).not.toBeNull()
    expect(vm.completenessReport.can_proceed).toBe(true)
  })
})
