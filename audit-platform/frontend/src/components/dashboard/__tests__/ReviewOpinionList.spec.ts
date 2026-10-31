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
import { flushPromises, mount } from '@vue/test-utils'
import type { OpenReviewsData, ReviewItem } from '@/composables/useDashboardData'

// ─── Mock vue-router ─────────────────────────────────────────────────────────

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

// 点击打开底稿编辑器：按编码取本项目底稿实例（spec wp-deeplink-locate-coverage-closure 需求 3）
const { resolveMock, warnMock } = vi.hoisted(() => ({ resolveMock: vi.fn(), warnMock: vi.fn() }))
vi.mock('@/services/resolveWorkpaperByCode', () => ({ resolveWorkpaperByCode: resolveMock }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { warning: warnMock, error: vi.fn(), info: vi.fn(), success: vi.fn() },
}))
const WP_D2 = '3f2b1c0d-9e8f-4a7b-8c6d-5e4f3a2b1c0d'
const WP_K1 = '7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d'

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
  resolveMock.mockReset()
  warnMock.mockReset()
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

// 原先跳底稿列表页并带 highlight / sheet / cell：列表页不读 sheet / cell，定位丢失。现在打开该底稿编辑器并带 ?sheet=&cell=。
describe('ReviewOpinionList — 点击跳转', () => {
  it('点击列表项打开对应底稿编辑器并定位（sheet 级编码没有独立底稿时回落父底稿）', async () => {
    resolveMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ wpId: WP_D2 })
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[0].trigger('click')
    await flushPromises()

    expect(resolveMock.mock.calls.map((c) => c.slice(0, 2))).toEqual([['proj-001', 'D2-1'], ['proj-001', 'D2']])
    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_D2 },
      query: { sheet: '审定表D2-1', cell: 'C15' },
    })
    expect(warnMock).not.toHaveBeenCalled()
  })

  it('点击无 sheet/cell 的列表项：回落父底稿时以原编码作 sheet', async () => {
    resolveMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ wpId: WP_D2 })
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[1].trigger('click') // r2: F2-1, no sheet/cell
    await flushPromises()

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_D2 },
      query: { sheet: 'F2-1' },
    })
  })

  it('点击不同列表项按各自 wp_code 取底稿；本项目没有时提示原因、不跳转', async () => {
    resolveMock.mockResolvedValueOnce({ wpId: WP_K1 })
    const wrapper = mountComponent()
    const items = wrapper.findAll('.review-item')

    await items[2].trigger('click') // r3: K1-2（本项目有独立底稿）
    await flushPromises()
    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_K1 },
      query: { sheet: '明细表K1-2', cell: 'B20' },
    })

    mockPush.mockReset()
    resolveMock.mockResolvedValue(null)
    await items[3].trigger('click') // r4: E1-3
    await flushPromises()
    expect(mockPush).not.toHaveBeenCalled()
    expect(warnMock).toHaveBeenCalledWith('本项目未找到底稿 E1-3（可能尚未生成）')
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
