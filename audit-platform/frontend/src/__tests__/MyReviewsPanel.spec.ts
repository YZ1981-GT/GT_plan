/**
 * MyReviewsPanel 前端测试
 * Validates: Requirements F5.5, F5.6, F5.7, F5.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
import MyReviewsPanel from '@/components/MyReviewsPanel.vue'

const mockReviewsResponse = {
  data: {
    items: [
      {
        review_id: 'r1',
        wp_code: 'D2-1',
        wp_name: '销售收入审定表',
        wp_id: 'wp-1',
        cell_reference: 'B5',
        comment_text: '金额与明细不一致',
        commenter_name: '张三',
        priority: 'must_fix',
        created_at: '2026-05-20T10:00:00Z',
      },
      {
        review_id: 'r2',
        wp_code: 'E1-1',
        wp_name: '货币资金审定表',
        wp_id: 'wp-2',
        cell_reference: 'C3',
        comment_text: '建议补充说明',
        commenter_name: '李四',
        priority: 'suggest',
        created_at: '2026-05-20T11:00:00Z',
      },
      {
        review_id: 'r3',
        wp_code: 'F2-1',
        wp_name: '存货审定表',
        wp_id: 'wp-3',
        cell_reference: null,
        comment_text: '仅供参考',
        commenter_name: '王五',
        priority: 'info',
        created_at: '2026-05-20T12:00:00Z',
      },
    ],
    summary: { must_fix: 1, suggest: 1, info: 1, total: 3 },
  },
}

describe('MyReviewsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders summary cards with correct counts', async () => {
    vi.mocked(http.get).mockResolvedValue(mockReviewsResponse)

    const wrapper = mount(MyReviewsPanel, {
      props: { projectId: 'test-project' },
      global: {
        stubs: {
          'el-skeleton': true,
          'el-empty': true,
          'el-tag': { template: '<span><slot /></span>' },
        },
      },
    })

    await flushPromises()

    const cards = wrapper.findAll('.summary-card')
    expect(cards.length).toBe(3)

    // must_fix card
    expect(cards[0].text()).toContain('1')
    expect(cards[0].text()).toContain('必须修改')

    // suggest card
    expect(cards[1].text()).toContain('1')
    expect(cards[1].text()).toContain('建议修改')

    // info card
    expect(cards[2].text()).toContain('1')
    expect(cards[2].text()).toContain('仅供参考')
  })

  it('renders review items with correct content', async () => {
    vi.mocked(http.get).mockResolvedValue(mockReviewsResponse)

    const wrapper = mount(MyReviewsPanel, {
      props: { projectId: 'test-project' },
      global: {
        stubs: {
          'el-skeleton': true,
          'el-empty': true,
          'el-tag': { template: '<span><slot /></span>' },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('D2-1')
    expect(wrapper.text()).toContain('金额与明细不一致')
    expect(wrapper.text()).toContain('张三')
  })

  it('emits navigate event on item click', async () => {
    vi.mocked(http.get).mockResolvedValue(mockReviewsResponse)

    const wrapper = mount(MyReviewsPanel, {
      props: { projectId: 'test-project' },
      global: {
        stubs: {
          'el-skeleton': true,
          'el-empty': true,
          'el-tag': { template: '<span><slot /></span>' },
        },
      },
    })

    await flushPromises()

    const items = wrapper.findAll('.review-item')
    await items[0].trigger('click')

    const emitted = wrapper.emitted('navigate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ wpId: 'wp-1', cellRef: 'B5' })
  })

  it('shows empty state when no reviews', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { items: [], summary: { must_fix: 0, suggest: 0, info: 0, total: 0 } },
    })

    const wrapper = mount(MyReviewsPanel, {
      props: { projectId: 'test-project' },
      global: {
        stubs: {
          'el-skeleton': true,
          'el-empty': { template: '<div class="el-empty">暂无待回复批注</div>' },
          'el-tag': { template: '<span><slot /></span>' },
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })

  it('calls API with correct project ID', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { items: [], summary: { must_fix: 0, suggest: 0, info: 0, total: 0 } },
    })

    mount(MyReviewsPanel, {
      props: { projectId: 'my-project-123' },
      global: {
        stubs: { 'el-skeleton': true, 'el-empty': true, 'el-tag': true },
      },
    })

    await flushPromises()

    expect(http.get).toHaveBeenCalledWith(
      '/api/projects/my-project-123/my-reviews',
      { params: { status: 'open' } }
    )
  })
})
