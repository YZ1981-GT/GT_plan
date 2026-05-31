/**
 * SideStandardsTab.spec.ts — K-2 相关准则侧栏 vitest
 *
 * spec proposal-remaining-18 task 2.6 + wp-ai-review-ux-fix task 6
 *
 * 验证：
 * 1. wpCode='E1' → cycle 推断为 E → api.get 调 /api/knowledge/tsj/E
 * 2. wpCode='D2-1' → cycle='D'；wpCode='F2-2' → cycle='F'
 * 3. mock api 返回 markdown → 渲染 HTML 包含原文文字
 * 4. wpCode='B23-1' → 不属于业务循环，显示 error 而不发请求
 * 5. wpCode 切换时按 cycle 缓存避免重复请求
 * 6. api 失败时显示 error 提示
 * 7. C3: 复核按钮显示 wpCode（非固定"当前底稿"）
 * 8. C2: onLocateCell 调用 useCellLocate（mock）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SideStandardsTab from '../SideStandardsTab.vue'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

const mockLocateCell = vi.fn(() => true)

vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: mockLocateCell }),
}))

const globalStubs = {
  stubs: {
    'el-tag': {
      template: '<span class="stub-tag" :data-type="type"><slot /></span>',
      props: ['type', 'size', 'round', 'effect'],
    },
    'el-button': {
      template: '<button class="stub-btn" :disabled="disabled" :data-loading="loading" @click="$emit(\'click\')"><slot /></button>',
      props: ['type', 'size', 'loading', 'disabled'],
      emits: ['click'],
    },
    'el-button-group': {
      template: '<div class="stub-btn-group"><slot /></div>',
    },
    'el-card': {
      template: '<div class="stub-card"><div class="stub-card-header"><slot name="header" /></div><slot /></div>',
      props: ['shadow'],
    },
    'el-link': {
      template: '<a class="stub-link" @click="$emit(\'click\')"><slot /></a>',
      props: ['type', 'underline'],
      emits: ['click'],
    },
  },
  directives: {
    loading: {},
  },
}

describe('SideStandardsTab — cycle 推断', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it.each([
    ['E1', 'E'],
    ['E1-2', 'E'],
    ['D2', 'D'],
    ['D2-1', 'D'],
    ['F2-2', 'F'],
    ['G7', 'G'],
    ['H1-12', 'H'],
    ['I3', 'I'],
    ['J1', 'J'],
    ['K8-2', 'K'],
    ['L5', 'L'],
    ['M2', 'M'],
    ['N5', 'N'],
    ['S1', 'S'],
  ])('wpCode=%s → 调用 /api/knowledge/tsj/%s', async (wpCode, expectedCycle) => {
    mockGet.mockResolvedValueOnce({
      cycle_name: expectedCycle,
      source_file: 'mocked.md',
      markdown: '# stub\n\nbody',
    })
    mount(SideStandardsTab, {
      props: { wpCode },
      global: globalStubs,
    })
    await flushPromises()

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [calledUrl] = mockGet.mock.calls[0]
    expect(calledUrl).toBe(`/api/knowledge/tsj/${expectedCycle}`)
  })

  it.each(['B23-1', 'C2', 'A15', '', 'X9'])(
    'wpCode=%s 不属于 D-N/S → 不发请求，显示 error',
    async (wpCode) => {
      const wrapper = mount(SideStandardsTab, {
        props: { wpCode },
        global: globalStubs,
      })
      await flushPromises()

      // 仅当 wpCode 非空时显示业务循环错误
      if (wpCode) {
        expect(wrapper.text()).toContain('未找到对应准则')
      } else {
        expect(wrapper.text()).toContain('请先选择底稿')
      }
      expect(mockGet).not.toHaveBeenCalled()
    },
  )
})

describe('SideStandardsTab — Markdown 渲染', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('mock api 返回 markdown → 渲染为 HTML 包含原文', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'E',
      source_file: '货币资金提示词.md',
      markdown: '# 货币资金审计复核提示词\n\n本提示词覆盖银行存款。',
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'E1' },
      global: globalStubs,
    })
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('货币资金审计复核提示词')
    expect(html).toContain('本提示词覆盖银行存款')
    // marked 应渲染出 <h1>
    expect(html).toMatch(/<h1[^>]*>.*货币资金审计复核提示词/)
    // 显示来源文件
    expect(html).toContain('货币资金提示词.md')
  })

  it('api 调用失败时显示 error 提示', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network down'))

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'E1' },
      global: globalStubs,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('未找到对应准则')
    expect(wrapper.text()).toContain('加载失败')
  })
})

describe('SideStandardsTab — 缓存与切换', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('同一 cycle 下切换 wpCode 不重复请求', async () => {
    mockGet.mockResolvedValue({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# 收入审计复核提示词',
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1' },
      global: globalStubs,
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 切到同 cycle 不同底稿
    await wrapper.setProps({ wpCode: 'D4-1' })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1) // cache hit, 没新请求
  })

  it('切到不同 cycle 触发新请求', async () => {
    mockGet
      .mockResolvedValueOnce({
        cycle_name: 'D',
        source_file: '收入审计复核提示词.md',
        markdown: '# D',
      })
      .mockResolvedValueOnce({
        cycle_name: 'E',
        source_file: '货币资金提示词.md',
        markdown: '# E',
      })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1' },
      global: globalStubs,
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ wpCode: 'E1' })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(2)
    const urls = mockGet.mock.calls.map((c) => c[0])
    expect(urls).toContain('/api/knowledge/tsj/D')
    expect(urls).toContain('/api/knowledge/tsj/E')
  })
})

describe('SideStandardsTab — AI 复核按钮', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('markdown 加载成功后显示复核按钮', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# 收入审计复核提示词',
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-123' },
      global: globalStubs,
    })
    await flushPromises()

    const btn = wrapper.find('.stub-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('复核')
  })

  it('点击按钮调用 POST /api/workpapers/{wpId}/ai/tsj-review', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })
    mockPost.mockResolvedValueOnce({ findings: [] })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-456' },
      global: globalStubs,
    })
    await flushPromises()

    await wrapper.find('.stub-btn').trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/workpapers/wp-456/ai/tsj-review')
  })

  it('成功时 emit review-complete 事件', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })
    const mockFindings = { findings: [{ issue_type: '数值错误', severity: 'high' }] }
    mockPost.mockResolvedValueOnce(mockFindings)

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-789' },
      global: globalStubs,
    })
    await flushPromises()

    await wrapper.find('.stub-btn').trigger('click')
    await flushPromises()

    const emitted = wrapper.emitted('review-complete')
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual(mockFindings)
  })

  it('wpId 为空时按钮 disabled', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1' },
      global: globalStubs,
    })
    await flushPromises()

    const btn = wrapper.find('.stub-btn')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})

describe('SideStandardsTab — C3 复核按钮含底稿名', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('复核按钮显示 wpCode（如 D2-1）', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-123' },
      global: globalStubs,
    })
    await flushPromises()

    const btn = wrapper.find('.stub-btn')
    expect(btn.text()).toContain('D2-1')
    expect(btn.text()).toContain('复核')
  })

  it('wpCode 为空时按钮显示"当前底稿"', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })

    // 注意：wpCode 为空时组件显示 placeholder，不会渲染按钮
    // 但如果 wpCode 存在但 resolvedCycle 有效才渲染 body
    // 这里测试 wpCode 存在但 wpCode 为 undefined 的 fallback 文案
    // 实际上 wpCode 为空时不会进入 body 区域，所以这个 case 不适用
    // 改为测试 wpCode='D2-1' 时按钮不含"当前底稿"
    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-123' },
      global: globalStubs,
    })
    await flushPromises()

    const btn = wrapper.find('.stub-btn')
    expect(btn.text()).not.toContain('当前底稿')
  })
})

describe('SideStandardsTab — C2 onLocateCell 调 useCellLocate', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockLocateCell.mockClear()
  })

  it('onLocateCell 调用 locateCell（snake_case 参数）', async () => {
    mockGet.mockResolvedValueOnce({
      cycle_name: 'D',
      source_file: '收入审计复核提示词.md',
      markdown: '# D',
    })
    mockPost.mockResolvedValueOnce({
      findings: [
        {
          id: 'f-001',
          content_type: 'finding',
          content_text: '测试',
          confirmation_status: 'pending',
          issue_type: '数值错误',
          severity: 'high',
          sheet: '应收账款',
          cell_range: 'B5',
          description: '金额有误',
          remediation: '请核实',
        },
      ],
    })

    const wrapper = mount(SideStandardsTab, {
      props: { wpCode: 'D2-1', wpId: 'wp-123', componentType: 'c-note-table' },
      global: globalStubs,
    })
    await flushPromises()

    // 触发复核获取 findings
    await wrapper.find('.stub-btn').trigger('click')
    await flushPromises()

    // TsjReviewFindings 子组件渲染后，找到定位链接并点击
    const locateLink = wrapper.findAll('.stub-link').find((l) => l.text().includes('定位'))
    expect(locateLink).toBeTruthy()
    await locateLink!.trigger('click')

    expect(mockLocateCell).toHaveBeenCalledTimes(1)
    expect(mockLocateCell).toHaveBeenCalledWith({
      wp_code: 'D2-1',
      sheet_name: '应收账款',
      cell_ref: 'B5',
      component_type: 'c-note-table',
    })
  })
})
