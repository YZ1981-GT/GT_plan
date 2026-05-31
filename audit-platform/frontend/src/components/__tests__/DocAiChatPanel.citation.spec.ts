/**
 * DocAiChatPanel — 引用来源跳转测试
 *
 * 验证需求 3.2, 3.3 / 属性 D3：
 * - knowledge_doc 类型：打开知识文件页面
 * - workpaper 类型：router 导航到底稿编辑器 + eventBus 触发定位
 * - trial_balance 类型：router 导航到试算表视图
 * - 通用 fallback：打开文档页面
 * - 无 source_id 时不触发任何导航
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

// Mock vue-router
const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-123' } }),
  useRouter: () => ({ push: mockRouterPush }),
}))

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    user: { id: 'user-1', role: 'auditor' },
  }),
}))

// Mock useCellLocate
const mockLocateCell = vi.fn().mockReturnValue(true)
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: mockLocateCell }),
}))

// Mock eventBus
const mockEventBusEmit = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (...args: any[]) => mockEventBusEmit(...args), on: vi.fn(), off: vi.fn() },
}))

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

import DocAiChatPanel from '../DocAiChatPanel.vue'

const defaultProps = {
  docType: 'workpaper',
  docId: 'wp-001',
  projectId: 'proj-123',
  year: 2025,
  visible: true,
}

function mountPanel(propsOverride = {}) {
  return mount(DocAiChatPanel, {
    props: { ...defaultProps, ...propsOverride },
    global: {
      plugins: [ElementPlus, createPinia()],
      stubs: {
        'el-drawer': {
          template: '<div class="mock-drawer" v-if="modelValue"><slot /></div>',
          props: ['modelValue', 'title', 'direction', 'size', 'destroyOnClose'],
        },
      },
    },
  })
}

describe('DocAiChatPanel — 引用来源跳转（需求 3.2, 3.3 / D3）', () => {
  let openSpy: any

  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockReset()
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ messages: [], items: [] }),
    })
    mockRouterPush.mockReset()
    mockLocateCell.mockReset()
    mockLocateCell.mockReturnValue(true)
    mockEventBusEmit.mockReset()
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
  })

  afterEach(() => {
    openSpy.mockRestore()
  })

  it('knowledge_doc 类型：打开知识文件页面', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '根据知识库...',
        citations: [
          { source_type: 'knowledge_doc', source_id: 'kd-456', source_name: '审计准则', paragraph_index: 5 },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    expect(citationTag.exists()).toBe(true)
    await citationTag.trigger('click')

    expect(openSpy).toHaveBeenCalledWith('/knowledge/files/kd-456', '_blank')
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('workpaper 类型：router 导航到底稿编辑器', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '底稿内容...',
        citations: [
          { source_type: 'workpaper', source_id: 'wp-789', source_name: 'D2-1' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-123', wpId: 'wp-789' },
    })
    expect(openSpy).not.toHaveBeenCalled()
  })

  it('workpaper 类型带 cell_ref：触发 eventBus locate-cell 事件', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '底稿单元格...',
        citations: [
          {
            source_type: 'workpaper',
            source_id: 'wp-789',
            source_name: 'D2-1',
            cell_ref: 'B5',
            sheet_name: '应收账款',
            component_type: 'c-note-table',
          },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')
    await flushPromises()

    // 验证 router 导航
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-123', wpId: 'wp-789' },
    })

    // 验证 eventBus 定位事件
    expect(mockEventBusEmit).toHaveBeenCalledWith('workpaper:locate-cell', {
      wpId: 'wp-789',
      sheetName: '应收账款',
      cellRef: 'B5',
      componentType: 'c-note-table',
      wpCode: 'D2-1',
    })
  })

  it('trial_balance 类型：router 导航到试算表视图', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '试算表数据...',
        citations: [
          { source_type: 'trial_balance', source_id: 'tb-001', source_name: '试算平衡表' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'TrialBalance',
      params: { projectId: 'proj-123' },
    })
    expect(openSpy).not.toHaveBeenCalled()
  })

  it('未知 source_type：fallback 打开文档页面', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '其他文档...',
        citations: [
          { source_type: 'other_doc', source_id: 'doc-999', source_name: '其他文件' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')

    expect(openSpy).toHaveBeenCalledWith('/documents/doc-999', '_blank')
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('无 source_id 时不触发任何导航', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '无来源...',
        citations: [
          { source_type: 'knowledge_doc', source_id: '', source_name: '无效引用' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')

    expect(openSpy).not.toHaveBeenCalled()
    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('paragraph_index 正确渲染在引用标签中', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '引用段落...',
        citations: [
          { source_type: 'knowledge_doc', source_id: 'kd-1', source_name: '准则文件', paragraph_index: 7 },
        ],
      },
    ]
    await flushPromises()

    expect(wrapper.text()).toContain('§7')
  })

  it('workpaper 无 cell_ref 时不触发 eventBus 定位', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '底稿...',
        citations: [
          { source_type: 'workpaper', source_id: 'wp-100', source_name: 'E1-1' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    await citationTag.trigger('click')
    await flushPromises()

    // 仍然导航到底稿
    expect(mockRouterPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-123', wpId: 'wp-100' },
    })

    // 但不触发 eventBus 定位事件
    expect(mockEventBusEmit).not.toHaveBeenCalled()
  })
})
