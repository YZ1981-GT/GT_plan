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
    // 提示文案已随手动章节溯源改造修正（不再误导为"文档中选中"）
    expect(wrapper.text()).toContain('请在上方输入章节号后点「溯源」')
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

/**
 * US-8 溯源能力标志（deliverable-writeback-and-online-edit-integrity Task 30）
 *
 * 行为级断言（不止源码级）：supportsLineage=false（财务报表）时面板**不请求** /section-states，
 * 只渲染穿透指引文案；缺省（不传）时按支持处理（会请求 section-states）。
 *
 * 🔴 守住 Vue Boolean prop 转换坑：未传的 boolean prop 会被转成 false 而非 undefined，
 * 若 LineagePanel 不给 supportsLineage 默认 true，则「不传」会被当成不支持、吞掉附注/报告正文溯源。
 */
describe('LineagePanel.vue — US-8 supportsLineage 行为', () => {
  const baseProps = {
    projectId: 'proj-001',
    wordExportTaskId: 'task-001',
  }

  const sectionStatesUrl =
    '/api/projects/proj-001/deliverables/task-001/section-states'

  beforeEach(() => {
    vi.clearAllMocks()
  })

  function sectionStatesCalls(): string[] {
    return mockApiGet.mock.calls
      .map((c) => c[0] as string)
      .filter((u) => u.includes('/section-states'))
  }

  it('supportsLineage=false：onMounted 不请求 /section-states，改显报表穿透文案', async () => {
    mockApiGet.mockResolvedValue({ sections: [] })
    const wrapper = mount(LineagePanel, {
      props: { ...baseProps, supportsLineage: false },
    })
    await nextTick()
    await new Promise((r) => setTimeout(r, 10))
    await nextTick()

    // 行为断言：根本没打 section-states（不是「打了但拿空」）
    expect(sectionStatesCalls()).toEqual([])
    // 文案指向报表穿透，不是误导性的「请重新生成」
    expect(wrapper.text()).toContain('财务报表按报表行取数')
    expect(wrapper.text()).toContain('穿透查看')
    expect(wrapper.text()).not.toContain('请重新生成')
    // 不渲染手动溯源下拉（不支持溯源时整块 UI 用说明替代）
    expect(wrapper.find('.lineage-panel__manual').exists()).toBe(false)
  })

  it('supportsLineage=false：手动触发 onBookmarkDetected 仍不请求 /section-states', async () => {
    mockApiGet.mockResolvedValue({ sections: [] })
    const wrapper = mount(LineagePanel, {
      props: { ...baseProps, supportsLineage: false },
    })
    await nextTick()
    ;(wrapper.vm as any).onBookmarkDetected('sec_八_1')
    await nextTick()
    await new Promise((r) => setTimeout(r, 10))
    await nextTick()

    expect(sectionStatesCalls()).toEqual([])
  })

  it('缺省（不传 supportsLineage）：按支持处理，onMounted 会请求 /section-states', async () => {
    // 🔴 Vue Boolean prop 转换坑守卫：若组件不给 supportsLineage 默认 true，
    // 「不传」会被转成 false ⇒ 这里的 section-states 请求不会发出，本例打红。
    mockApiGet.mockResolvedValue({ sections: [{ section_code: '八、1', is_stale: false }] })
    const wrapper = mount(LineagePanel, { props: baseProps })
    await nextTick()
    await new Promise((r) => setTimeout(r, 10))
    await nextTick()

    expect(sectionStatesCalls()).toEqual([sectionStatesUrl])
    // 渲染正常溯源 UI（手动下拉），不显示报表穿透文案
    expect(wrapper.find('.lineage-panel__manual').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('财务报表按报表行取数')
  })
})
