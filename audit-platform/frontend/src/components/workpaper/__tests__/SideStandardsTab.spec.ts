/**
 * SideStandardsTab.spec.ts — K-2 相关准则侧栏 vitest
 *
 * spec proposal-remaining-18 task 2.6
 *
 * 验证：
 * 1. wpCode='E1' → cycle 推断为 E → api.get 调 /api/knowledge/tsj/E
 * 2. wpCode='D2-1' → cycle='D'；wpCode='F2-2' → cycle='F'
 * 3. mock api 返回 markdown → 渲染 HTML 包含原文文字
 * 4. wpCode='B23-1' → 不属于业务循环，显示 error 而不发请求
 * 5. wpCode 切换时按 cycle 缓存避免重复请求
 * 6. api 失败时显示 error 提示
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

const globalStubs = {
  stubs: {
    'el-tag': {
      template: '<span class="stub-tag" :data-type="type"><slot /></span>',
      props: ['type', 'size', 'round'],
    },
    'el-button': {
      template: '<button class="stub-btn" :disabled="disabled" :data-loading="loading" @click="$emit(\'click\')"><slot /></button>',
      props: ['type', 'size', 'loading', 'disabled'],
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
    expect(wrapper.text()).toContain('Network down')
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
    expect(btn.text()).toContain('用此提示词复核当前底稿')
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
