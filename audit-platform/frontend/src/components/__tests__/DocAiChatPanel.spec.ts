/**
 * DocAiChatPanel.vue 单元测试
 *
 * 验证：
 * 1. 面板渲染 + 文档类型标签显示
 * 2. 消息列表渲染（用户 + AI 消息）
 * 3. 引用来源标注渲染 + 点击跳转
 * 4. 采纳按钮 emit adopt 事件
 * 5. @mention scope 选择
 * 6. 关闭时 emit 正确事件
 * 7. 文档类型映射
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    user: { id: 'user-1', role: 'auditor' },
  }),
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
        // 将 el-drawer 替换为简单 div 以便测试内容
        'el-drawer': {
          template: '<div class="mock-drawer" v-if="modelValue"><slot /></div>',
          props: ['modelValue', 'title', 'direction', 'size', 'destroyOnClose'],
        },
      },
    },
  })
}

describe('DocAiChatPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockReset()
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ messages: [], items: [] }),
    })
    // Mock localStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
  })

  it('渲染文档类型标签', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('底稿')
    expect(wrapper.text()).toContain('wp-001')
  })

  it('空消息时显示空状态提示', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('暂无对话')
  })

  it('渲染对话消息列表', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      { id: '1', role: 'user', text: '什么是审计抽样？' },
      { id: '2', role: 'assistant', text: '审计抽样是指从总体中选取样本进行测试', citations: [] },
    ]
    await flushPromises()

    expect(wrapper.text()).toContain('什么是审计抽样？')
    expect(wrapper.text()).toContain('审计抽样是指从总体中选取样本进行测试')
  })

  it('渲染引用来源标注', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '根据知识库内容...',
        citations: [
          { source_type: 'knowledge_doc', source_id: 'kd-1', source_name: '审计准则第1号', paragraph_index: 3 },
        ],
      },
    ]
    await flushPromises()

    expect(wrapper.text()).toContain('引用来源')
    expect(wrapper.text()).toContain('审计准则第1号')
    expect(wrapper.text()).toContain('§3')
  })

  it('采纳按钮 emit adopt 事件', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      { id: 'msg-1', role: 'assistant', text: 'AI 建议内容', citations: [] },
    ]
    await flushPromises()

    // 找到采纳按钮并点击
    const adoptBtn = wrapper.find('.message-actions button')
    expect(adoptBtn.exists()).toBe(true)
    await adoptBtn.trigger('click')

    expect(wrapper.emitted('adopt')).toBeTruthy()
    expect(wrapper.emitted('adopt')![0]).toEqual([
      { content: 'AI 建议内容', messageId: 'msg-1' },
    ])
  })

  it('@mention 按钮切换 scope 选择器', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    // 初始不显示 mention popover
    expect(wrapper.find('.mention-popover').exists()).toBe(false)

    // 通过 vm 切换
    const vm = wrapper.vm as any
    vm.showMentionPopover = true
    await flushPromises()

    expect(wrapper.find('.mention-popover').exists()).toBe(true)
    expect(wrapper.text()).toContain('选择额外知识范围')
  })

  it('关闭抽屉时 emit close 和 update:visible', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.handleVisibleChange(false)

    expect(wrapper.emitted('update:visible')).toBeTruthy()
    expect(wrapper.emitted('update:visible')![0]).toEqual([false])
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('文档类型映射正确', async () => {
    const noteWrapper = mountPanel({ docType: 'note' })
    await flushPromises()
    expect(noteWrapper.text()).toContain('附注')

    const reportWrapper = mountPanel({ docType: 'report' })
    await flushPromises()
    expect(reportWrapper.text()).toContain('报表')

    const folderWrapper = mountPanel({ docType: 'knowledge_folder' })
    await flushPromises()
    expect(folderWrapper.text()).toContain('知识库文件夹')
  })

  it('引用来源点击触发跳转', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountPanel()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.messages = [
      {
        id: '1',
        role: 'assistant',
        text: '回答内容',
        citations: [
          { source_type: 'knowledge_doc', source_id: 'kd-123', source_name: '测试文件' },
        ],
      },
    ]
    await flushPromises()

    const citationTag = wrapper.find('.citation-tag')
    expect(citationTag.exists()).toBe(true)
    await citationTag.trigger('click')

    expect(openSpy).toHaveBeenCalledWith('/knowledge/files/kd-123', '_blank')
    openSpy.mockRestore()
  })
})
