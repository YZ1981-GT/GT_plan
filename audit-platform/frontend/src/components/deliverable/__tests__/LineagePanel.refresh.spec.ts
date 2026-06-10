/**
 * LineagePanel.vue 刷新功能单元测试
 *
 * Spec: deliverable-lineage-and-writeback Task 10.2
 * Requirements: 4.5, 5.5, 11.4
 *
 * 验证：
 * - stale 徽标实时更新
 * - "刷新本章节"/"刷新所有过期"按钮渲染与联通
 * - 终态出品物（signed/confirmed/archived）刷新入口禁用
 * - 覆盖确认弹窗
 *
 * 铁律：组件已改用 api.get/api.post（@/services/apiProxy），不再用原生 fetch
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import LineagePanel from '../LineagePanel.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

// Mock ElMessageBox
const mockConfirm = vi.fn().mockResolvedValue('confirm')
vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return {
    ...real,
    ElMessageBox: {
      confirm: (...args: any[]) => mockConfirm(...args),
    },
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

// Mock apiProxy（api.get 已解信封直接返回业务数据；api.post 同理）
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
  },
}))

// Mock EventSource（useSSEReconnect 用 es.onmessage/onerror）
class MockEventSource {
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener() {}

  close() {
    this.readyState = 2
  }

  // 模拟服务端推送一条 message
  _emit(data: any) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  static instances: MockEventSource[] = []
  static reset() {
    MockEventSource.instances = []
  }
}
;(global as any).EventSource = MockEventSource

// 默认 trace 响应（stale 章节）
const STALE_TRACE = {
  contracts: [
    {
      source_type: 'note',
      source_id: 'note-1',
      target_type: 'note',
      target_id: 'note-1',
      basis: '长期借款',
      status: 'stale',
      confidence: 'system',
      route: '/projects/proj-001/disclosure-notes?section=八、1',
    },
  ],
  section_state: {
    section_code: '八、1',
    is_stale: true,
    source_snapshot_hash: 'abc123',
    anchor_name: 'sec_八_1',
  },
}

describe('LineagePanel.vue — 刷新功能（Task 10.1/10.2）', () => {
  const baseProps = {
    projectId: 'proj-001',
    wordExportTaskId: 'task-001',
    year: 2025,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    MockEventSource.reset()
    // Default: trace endpoint returns stale section
    mockApiGet.mockResolvedValue(STALE_TRACE)
    mockApiPost.mockResolvedValue({ version_no: 2, refreshed: ['八、1'] })
  })

  afterEach(() => {
    MockEventSource.reset()
  })

  /**
   * Helper: mount + trigger bookmark detection to show section content
   */
  async function mountWithSection(extraProps = {}) {
    const wrapper = mount(LineagePanel, {
      props: { ...baseProps, ...extraProps },
    })
    ;(wrapper.vm as any).onBookmarkDetected('sec_八_1')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await flushPromises()
    await nextTick()
    return wrapper
  }

  describe('刷新按钮渲染', () => {
    it('当选中章节时显示"刷新本章节"和"刷新所有过期"按钮', async () => {
      const wrapper = await mountWithSection()
      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      expect(buttons.length).toBe(2)
      expect(buttons[0].text()).toBe('刷新本章节')
      expect(buttons[1].text()).toBe('刷新所有过期')
    })

    it('未选中章节时不显示刷新按钮', () => {
      const wrapper = mount(LineagePanel, { props: baseProps })
      expect(wrapper.find('.lineage-panel__refresh-toolbar').exists()).toBe(false)
    })
  })

  describe('终态出品物只读（需求 11.4）', () => {
    it.each(['signed', 'confirmed', 'archived'])(
      '状态为 %s 时，两个刷新按钮 disabled',
      async (status) => {
        const wrapper = await mountWithSection({ deliverableStatus: status })
        const buttons = wrapper.findAll('.lineage-panel__action-btn')
        expect(buttons[0].attributes('disabled')).toBeDefined()
        expect(buttons[1].attributes('disabled')).toBeDefined()
      },
    )

    it('非终态(draft)时，刷新按钮不 disabled', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      // When not disabled, el-button stub still has disabled attr but set to "false"
      expect(buttons[0].attributes('disabled')).not.toBe('')
      expect(buttons[1].attributes('disabled')).not.toBe('')
    })

    it('终态时 tooltip 包含正确提示文案', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'signed' })
      // el-tooltip is rendered as a stub (<el-tooltip>), check the content attribute on it
      const tooltips = wrapper.findAll('el-tooltip-stub, el-tooltip')
      expect(tooltips.length).toBeGreaterThanOrEqual(2)
      expect(tooltips[0].attributes('content')).toBe(
        '该出品物已签字/确认/归档，不可回填或刷新',
      )
    })
  })

  describe('"刷新本章节"覆盖确认（需求 5.5）', () => {
    it('点击"刷新本章节"时弹出确认对话框', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[0].trigger('click')
      await flushPromises()

      expect(mockConfirm).toHaveBeenCalledWith(
        '刷新本章节将用最新源数据覆盖当前内容，如您有手动编辑的内容可能被覆盖。是否继续？',
        '确认刷新本章节',
        expect.objectContaining({
          confirmButtonText: '确认刷新',
          cancelButtonText: '取消',
          type: 'warning',
        }),
      )
    })

    it('用户取消确认时不调用刷新端点', async () => {
      mockConfirm.mockRejectedValueOnce('cancel')
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      // Clear initial trace api call
      mockApiPost.mockClear()

      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[0].trigger('click')
      await flushPromises()

      // refresh-section POST should not be called
      expect(mockApiPost).not.toHaveBeenCalled()
    })

    it('用户确认后调用 refresh-section 端点', async () => {
      mockConfirm.mockResolvedValueOnce('confirm')
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()
      mockApiPost.mockResolvedValue({ version_no: 2, refreshed: ['八、1'] })

      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[0].trigger('click')
      await flushPromises()

      expect(mockApiPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockApiPost.mock.calls[0]
      expect(url).toContain('/refresh-section')
      expect(body.section_code).toBe('八、1')
      expect(body.year).toBe(2025)
      expect(body.confirm_overwrite).toBe(true)
    })
  })

  describe('"刷新所有过期"按钮', () => {
    it('点击后直接调用 refresh-stale 端点（无确认）', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()
      mockApiPost.mockResolvedValue({ version_no: 2, refreshed: ['八、1', '八、2'] })

      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[1].trigger('click')
      await flushPromises()

      expect(mockApiPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockApiPost.mock.calls[0]
      expect(url).toContain('/refresh-stale')
      expect(body.year).toBe(2025)
      expect(body.confirm_overwrite).toBe(true)
    })
  })

  describe('stale 徽标显示（需求 4.5）', () => {
    it('章节 is_stale=true 时显示"源数据已变更"徽标', async () => {
      const wrapper = await mountWithSection()
      expect(wrapper.find('.lineage-panel__stale-badge').exists()).toBe(true)
      expect(wrapper.find('.lineage-panel__stale-badge').text()).toBe('源数据已变更')
    })

    it('章节 is_stale=false 时不显示 stale 徽标', async () => {
      mockApiGet.mockResolvedValue({
        contracts: [],
        section_state: {
          section_code: '八、1',
          is_stale: false,
          source_snapshot_hash: 'abc123',
          anchor_name: 'sec_八_1',
        },
      })
      const wrapper = await mountWithSection()
      expect(wrapper.find('.lineage-panel__stale-badge').exists()).toBe(false)
    })
  })

  describe('SSE LINKAGE_STALE_CHANGED 实时更新', () => {
    it('组件挂载时连接项目级事件流 /events/stream', async () => {
      mount(LineagePanel, { props: baseProps })
      await nextTick()
      expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(1)
      expect(MockEventSource.instances[0].url).toContain(
        `/api/projects/proj-001/events/stream`,
      )
    })

    it('收到 LINKAGE_STALE_CHANGED 事件时重新拉取溯源（更新 stale 状态）', async () => {
      const wrapper = await mountWithSection()
      // Initially stale
      expect(wrapper.find('.lineage-panel__stale-badge').exists()).toBe(true)

      // 服务端推 LINKAGE_STALE_CHANGED → 组件重新 traceSection（此时 api.get 返非 stale）
      mockApiGet.mockResolvedValue({
        contracts: [],
        section_state: {
          section_code: '八、1',
          is_stale: false,
          source_snapshot_hash: 'def456',
          anchor_name: 'sec_八_1',
        },
      })
      const sse = MockEventSource.instances[0]
      sse._emit({ event_type: 'LINKAGE_STALE_CHANGED', section_code: '八、1', is_stale: false })
      await nextTick()
      await flushPromises()
      await nextTick()

      expect(wrapper.find('.lineage-panel__stale-badge').exists()).toBe(false)
    })

    it('组件卸载时关闭 SSE 连接', async () => {
      const wrapper = mount(LineagePanel, { props: baseProps })
      await nextTick()
      const sse = MockEventSource.instances[0]
      expect(sse.readyState).toBe(1)

      wrapper.unmount()
      expect(sse.readyState).toBe(2) // closed
    })
  })
})
