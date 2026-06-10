/**
 * LineagePanel.vue 单元测试
 *
 * Spec: deliverable-lineage-and-writeback Task 5.2/5.3
 * Requirements: 3.2, 3.5, 3.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import LineagePanel from '../LineagePanel.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

// Mock apiProxy (项目铁律：组件用 api.get/api.post 而非原生 fetch)
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
  },
}))

// Mock EventSource（useSSEReconnect 挂载时会创建连接，jsdom 无 EventSource）
class MockEventSource {
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1
  constructor(url: string) {
    this.url = url
  }
  addEventListener() {}
  close() {
    this.readyState = 2
  }
}
;(global as any).EventSource = MockEventSource

describe('LineagePanel.vue', () => {
  const baseProps = {
    projectId: 'proj-001',
    wordExportTaskId: 'task-001',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染面板标题"数据溯源"（需求 3.6 中文化）', () => {
    const wrapper = mount(LineagePanel, { props: baseProps })
    expect(wrapper.find('.lineage-panel__title').text()).toBe('数据溯源')
  })

  it('未选中章节时显示提示文案', () => {
    const wrapper = mount(LineagePanel, { props: baseProps })
    expect(wrapper.find('.lineage-panel__hint').exists()).toBe(true)
    expect(wrapper.text()).toContain('请在文档中选中章节以查看溯源信息')
  })

  it('无锚点时显示降级提示（需求 3.5）', () => {
    const wrapper = mount(LineagePanel, {
      props: { ...baseProps, hasNoAnchors: true },
    })
    expect(wrapper.find('.lineage-panel__no-anchor').exists()).toBe(true)
    expect(wrapper.text()).toContain('该出品物版本不支持溯源，请重新生成')
  })

  it('暴露 onBookmarkDetected 方法给父组件', () => {
    const wrapper = mount(LineagePanel, { props: baseProps })
    expect(typeof (wrapper.vm as any).onBookmarkDetected).toBe('function')
  })

  it('暴露 setNoAnchors 方法给父组件', () => {
    const wrapper = mount(LineagePanel, { props: baseProps })
    expect(typeof (wrapper.vm as any).setNoAnchors).toBe('function')
  })

  it('调用 onBookmarkDetected 触发溯源查询', async () => {
    // api.get 已解信封，直接返回业务数据
    mockApiGet.mockResolvedValueOnce({
      contracts: [
        {
          source_type: 'note',
          source_id: 'note-1',
          target_type: 'note',
          target_id: 'note-1',
          basis: '长期借款',
          status: 'current',
          confidence: 'system',
          route: '/projects/proj-001/disclosure-notes?section=八、1',
        },
      ],
      section_state: { section_code: '八、1', is_stale: false, source_snapshot_hash: null, anchor_name: 'sec_八_1' },
    })

    const wrapper = mount(LineagePanel, { props: baseProps })
    ;(wrapper.vm as any).onBookmarkDetected('sec_八_1')
    await nextTick()
    // wait for async api call
    await new Promise(r => setTimeout(r, 10))
    await nextTick()

    expect(mockApiGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/projects/proj-001/deliverables/task-001/trace?section_code='),
    )
  })

  it('setNoAnchors 触发降级状态', async () => {
    const wrapper = mount(LineagePanel, { props: baseProps })
    ;(wrapper.vm as any).setNoAnchors()
    await nextTick()
    expect(wrapper.find('.lineage-panel__no-anchor').exists()).toBe(true)
  })
})
