/**
 * ReviewOpinionList.spec.ts — Sprint 2 Task 4.3
 *
 * 测试 ReviewOpinionList.vue 组件:
 * - 排序正确性（items 按优先级顺序渲染）
 * - 点击跳转到对应底稿
 * - 空状态（"所有复核意见已解决"）
 *
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { OpenReviewsData, ReviewItem } from '@/composables/useDashboardData'

// ─── Mock vue-router ─────────────────────────────────────────────────────────

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

// ─── Import component under test ────────────────────────────────────────────

import ReviewOpinionList from '../ReviewOpinionList.vue'

// ─── Element Plus stubs ──────────────────────────────────────────────────────

const globalStubs = {
  'el-empty': {
    template: '<div class="el-empty">{{ description }}</div>',
    props: ['imageSize', 'description'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-type="type"><slot /></span>',
    props: ['type', 'effect', 'size'],
  },
  'el-scrollbar': {
    template: '<div class="el-scrollbar"><slot /></div>',
    props: ['maxHeight'],
  },
}

// ─── Test Fixtures ───────────────────────────────────────────────────────────

function createReviewItems(): ReviewItem[] {
  return [
    {
      id: 'r1',
      review_layer: 'L5',
      summary: '合伙人复核：收入确认时点需进一步核实',
      created_at: '2025-06-15T10:00:00Z',
      wp_code: 'D2-1',
      sheet_name: '审定表D2-1',
      cell_ref: 'C15',
    },
    {
      id: 'r2',
      review_layer: 'L3',
      summary: '主管复核：存货跌价准备计算方法需确认',
      created_at: '2025-06-14T09:00:00Z',
      wp_code: 'F2-1',
      sheet_name: null,
      cell_ref: null,
    },
    {
      id: 'r3',
      review_layer: 'L5',
      summary: '合伙人复核：关联方交易披露不完整',
      created_at: '2025-06-15T08:00:00Z',
      wp_code: 'K1-2',
      sheet_name: '明细表K1-2',
      cell_ref: 'B20',
    },
    {
      id: 'r4',
      review_layer: 'L1',
      summary: '助理复核：银行余额调节表日期有误',
      created_at: '2025-06-13T16:00:00Z',
      wp_code: 'E1-3',
      sheet_name: null,
      cell_ref: null,
    },
  ]
}

function createOpenReviewsData(): OpenReviewsData {
  return {
    total: 4,
    by_layer: { L5: 2, L3: 1, L1: 1 },
    items: createReviewItems(),
  }
}

function mountComponent(openReviews: OpenReviewsData | null = createOpenReviewsData()) {
  return mount(ReviewOpinionList, {
    props: { openReviews },
    global: { stubs: globalStubs },
  })
}

// ─── Tests ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockPush.mockReset()
})

describe('ReviewOpinionList — 排序正确性', () => {
  it('items 按传入顺序渲染（后端已排序）', () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')
    expect(items).toHaveLength(4)

    // 第一个应该是 L5 (r1)
    expect(items[0].text()).toContain('合伙人')
    expect(items[0].text()).toContain('D2-1')

    // 第二个应该是 L3 (r2)
    expect(items[1].text()).toContain('主管')
    expect(items[1].text()).toContain('F2-1')

    // 第三个应该是 L5 (r3)
    expect(items[2].text()).toContain('合伙人')
    expect(items[2].text()).toContain('K1-2')

    // 第四个应该是 L1 (r4)
    expect(items[3].text()).toContain('助理')
    expect(items[3].text()).toContain('E1-3')
  })

  it('显示总未解决数', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('.review-total-count').text()).toBe('4')
    expect(wrapper.text()).toContain('条未解决')
  })

  it('显示按层级分布标签', () => {
    const wrapper = mountComponent()
    const tags = wrapper.findAll('.review-layer-tag')
    expect(tags.length).toBe(3) // L5, L3, L1
  })

  it('每个列表项显示 wp_code 和 summary', () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')
    expect(items[0].find('.review-item-wp-code').text()).toBe('D2-1')
    expect(items[0].find('.review-item-summary').text()).toContain('收入确认时点需进一步核实')
  })
})

describe('ReviewOpinionList — 点击跳转', () => {
  it('点击列表项跳转到对应底稿（含 sheet + cell）', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[0].trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: {
        highlight: 'D2-1',
        sheet: '审定表D2-1',
        cell: 'C15',
      },
    })
  })

  it('点击无 sheet/cell 的列表项仅传 highlight', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[1].trigger('click') // r2: F2-1, no sheet/cell

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: {
        highlight: 'F2-1',
      },
    })
  })

  it('点击不同列表项传递正确的 wp_code', async () => {
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[2].trigger('click') // r3: K1-2

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperList',
      params: { projectId: 'proj-001' },
      query: {
        highlight: 'K1-2',
        sheet: '明细表K1-2',
        cell: 'B20',
      },
    })
  })
})

describe('ReviewOpinionList — 空状态', () => {
  it('openReviews=null 时显示"所有复核意见已解决"', () => {
    const wrapper = mountComponent(null)
    expect(wrapper.text()).toContain('所有复核意见已解决')
  })

  it('openReviews.total=0 时显示"所有复核意见已解决"', () => {
    const emptyData: OpenReviewsData = {
      total: 0,
      by_layer: {},
      items: [],
    }
    const wrapper = mountComponent(emptyData)
    expect(wrapper.text()).toContain('所有复核意见已解决')
  })

  it('空状态时不显示列表和统计', () => {
    const wrapper = mountComponent(null)
    expect(wrapper.find('.review-stats-header').exists()).toBe(false)
    expect(wrapper.find('.review-list').exists()).toBe(false)
  })

  it('有数据时不显示空状态', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.review-stats-header').exists()).toBe(true)
  })
})
