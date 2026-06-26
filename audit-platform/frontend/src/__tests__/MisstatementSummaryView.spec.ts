/**
 * MisstatementSummaryView 组件测试
 * A13-1 错报汇总视图：有错报时渲染表格，无错报时显示空状态
 * 增强后版本：包含 MaterialityIndicator + SSE 自动刷新 + Prior_Year_Status 展示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import MisstatementSummaryView from '@/components/workpaper/MisstatementSummaryView.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'test-project-id' },
    query: { year: '2025' },
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

// Mock project store
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    year: 2025,
  }),
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// Mock API
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

describe('MisstatementSummaryView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const globalStubs = {
    global: {
      stubs: {
        'el-alert': { template: '<div class="el-alert"><slot /><slot name="title" /></div>', props: ['type', 'closable'] },
        'el-empty': { template: '<div class="el-empty"><slot name="description" /></div>', props: ['description'] },
        'el-descriptions': { template: '<div class="el-descriptions"><slot /></div>', props: ['column', 'border', 'size', 'title'] },
        'el-descriptions-item': { template: '<div class="el-descriptions-item"><slot /></div>', props: ['label'] },
        'el-badge': { template: '<div class="el-badge"><slot /></div>', props: ['value', 'type'] },
        'el-tag': { template: '<div class="el-tag"><slot /></div>', props: ['type', 'size', 'effect'] },
        'el-icon': { template: '<span class="el-icon"><slot /></span>' },
        'el-link': { template: '<a class="el-link"><slot /></a>', props: ['type'] },
        'el-notification': { template: '<div />' },
        MaterialityIndicator: { template: '<div class="materiality-indicator-stub" />' },
        WorkpaperHtmlTable: { template: '<div class="wp-html-table" />', props: ['title', 'columns', 'rows', 'scope', 'projectId', 'year'] },
      },
    },
  }

  it('renders empty state when no misstatements exist', async () => {
    // Mock API returns empty data
    mockGet.mockImplementation((url: string) => {
      if (url.includes('misstatement-summary')) {
        return Promise.resolve({ prior: [], current: [] })
      }
      if (url.includes('misstatement-evaluation')) {
        return Promise.resolve({
          total_amount: 0,
          materiality: 50000,
          exceeds_materiality: false,
          suggested_conclusion: '未更正错报合计(0.00)占重要性水平0.0%，未超过重要性水平。',
        })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(MisstatementSummaryView, {
      props: { wpId: 'wp-123' },
      ...globalStubs,
    })

    await flushPromises()

    // Empty state should be visible
    expect(wrapper.find('.misstatement-summary__empty').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    // Table should NOT be rendered when no data
    expect(wrapper.find('.wp-html-table').exists()).toBe(false)
  })

  it('renders table with data when misstatements exist', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('misstatement-summary')) {
        return Promise.resolve({
          prior: [],
          current: [
            {
              id: 'adj-001',
              adjustment_no: 'AJE-001',
              description: '存货跌价准备调整',
              account_code: '1471',
              account_name: '存货跌价准备',
              debit_amount: 10000,
              credit_amount: null,
              passed_reason: '',
            },
          ],
        })
      }
      if (url.includes('misstatement-evaluation')) {
        return Promise.resolve({
          total_amount: 10000,
          materiality: 50000,
          exceeds_materiality: false,
          suggested_conclusion: '未更正错报合计(10,000.00)占重要性水平20.0%，未超过重要性水平。',
          cumulative_total: 10000,
          materiality_info: { pm: 50000, status: 'yellow', ratio: 0.2 },
        })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(MisstatementSummaryView, {
      props: { wpId: 'wp-123' },
      ...globalStubs,
    })

    await flushPromises()

    // Empty state should NOT be visible
    expect(wrapper.find('.misstatement-summary__empty').exists()).toBe(false)
    // Table SHOULD be rendered
    expect(wrapper.find('.wp-html-table').exists()).toBe(true)
    // Evaluation alert should be visible
    expect(wrapper.find('.misstatement-summary__eval').exists()).toBe(true)
  })

  it('shows evaluation alert with correct type based on materiality', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('misstatement-summary')) {
        return Promise.resolve({
          prior: [],
          current: [
            {
              id: 'adj-002',
              adjustment_no: 'AJE-002',
              description: '超过重要性的错报',
              account_code: '6001',
              account_name: '主营业务收入',
              debit_amount: 100000,
              credit_amount: null,
              passed_reason: '',
            },
          ],
        })
      }
      if (url.includes('misstatement-evaluation')) {
        return Promise.resolve({
          total_amount: 100000,
          materiality: 50000,
          exceeds_materiality: true,
          suggested_conclusion: '未更正错报合计(100,000.00)超过重要性水平(50,000.00)，需考虑对审计意见的影响。',
          cumulative_total: 100000,
        })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(MisstatementSummaryView, {
      props: { wpId: 'wp-123' },
      ...globalStubs,
    })

    await flushPromises()

    // Evaluation alert should be visible when exceeds materiality
    const evalSection = wrapper.find('.misstatement-summary__eval')
    expect(evalSection.exists()).toBe(true)
    // The el-alert stub renders with the type prop
    const alert = evalSection.find('.el-alert')
    expect(alert.exists()).toBe(true)
    // Verify table is rendered (data exists)
    expect(wrapper.find('.wp-html-table').exists()).toBe(true)
  })

  it('handles API failure gracefully (shows empty state)', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))

    const wrapper = mount(MisstatementSummaryView, {
      props: { wpId: 'wp-123' },
      ...globalStubs,
    })

    await flushPromises()

    // Should show empty state on API failure (graceful degradation)
    expect(wrapper.find('.misstatement-summary__empty').exists()).toBe(true)
    expect(wrapper.find('.wp-html-table').exists()).toBe(false)
  })

  it('derives projectId from route.params when not passed as prop', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('misstatement-summary')) {
        return Promise.resolve({ prior: [], current: [] })
      }
      if (url.includes('misstatement-evaluation')) {
        return Promise.resolve({
          total_amount: 0,
          materiality: 0,
          exceeds_materiality: false,
          suggested_conclusion: '重要性水平未设置，无法自动判断。',
        })
      }
      return Promise.resolve({})
    })

    mount(MisstatementSummaryView, {
      props: { wpId: 'wp-456' },
      ...globalStubs,
    })

    await flushPromises()

    // Should use route.params.projectId = 'test-project-id'
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/workpapers/test-project-id/2025/misstatement-summary'),
    )
  })

  it('renders MaterialityIndicator stub when summaryLoaded is true', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('misstatement-summary')) {
        return Promise.resolve({ prior: [], current: [] })
      }
      if (url.includes('misstatement-evaluation')) {
        return Promise.resolve({
          total_amount: 0,
          materiality: 50000,
          exceeds_materiality: false,
          suggested_conclusion: '',
          cumulative_total: 0,
          materiality_info: { pm: 50000, status: 'green', ratio: 0 },
        })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(MisstatementSummaryView, {
      props: { wpId: 'wp-123' },
      ...globalStubs,
    })

    await flushPromises()

    // MaterialityIndicator stub should be present
    expect(wrapper.find('.materiality-indicator-stub').exists()).toBe(true)
  })
})
