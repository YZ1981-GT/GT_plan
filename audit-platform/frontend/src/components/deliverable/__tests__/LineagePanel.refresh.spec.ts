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

// Mock ElMessageBox / ElMessage（hoisted：刷新结果提示的断言要读调用参数）
const { mockConfirm, mockAlert, mockMsg } = vi.hoisted(() => ({
  mockConfirm: vi.fn(),
  mockAlert: vi.fn(),
  mockMsg: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return {
    ...real,
    ElMessageBox: {
      confirm: (...args: any[]) => mockConfirm(...args),
      alert: (...args: any[]) => mockAlert(...args),
    },
    ElMessage: mockMsg,
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

// Mock 项目事件流单例总线（LineagePanel 迁移后订阅共享连接的 LINKAGE_STALE_CHANGED）
interface MockSub {
  projectId: string
  eventName: string
  handler: (data: any, event?: string) => void
  close: ReturnType<typeof vi.fn>
}
const mockSubs: MockSub[] = []
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: (projectId: string, eventName: string, handler: any) => {
    const close = vi.fn()
    mockSubs.push({ projectId, eventName, handler, close })
    return { close }
  },
}))

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

/** 后端 RefreshResult：刷新了八、1，落第 15 版 */
const REFRESHED = {
  version_no: 15,
  refreshed: ['八、1'],
  skipped: [],
  requires_confirm: false,
  pending_confirm_sections: [],
  messages: [],
}

describe('LineagePanel.vue — 刷新功能（Task 10.1/10.2）', () => {
  const baseProps = {
    projectId: 'proj-001',
    wordExportTaskId: 'task-001',
    year: 2025,
    supportsSectionRefresh: true,
  }

  /** section-states 端点的章节列表（「刷新所有过期」先取它数过期节数） */
  let sectionStates: Array<{ section_code: string; is_stale: boolean }> | Error = []

  beforeEach(() => {
    vi.clearAllMocks()
    mockSubs.length = 0
    mockConfirm.mockResolvedValue('confirm')
    mockAlert.mockResolvedValue('confirm')
    sectionStates = [{ section_code: '八、1', is_stale: true }, { section_code: '八、2', is_stale: false }]
    // trace 端点返回 stale 章节；section-states 端点返回章节列表
    mockApiGet.mockImplementation(async (url: string) => {
      if (url.endsWith('/section-states')) {
        if (sectionStates instanceof Error) throw sectionStates
        return { sections: sectionStates }
      }
      return STALE_TRACE
    })
    mockApiPost.mockResolvedValue(REFRESHED)
  })

  afterEach(() => {
    mockSubs.length = 0
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
    it('点击"刷新本章节"时弹出确认对话框，写明以已保存的最新版本为底、未保存的在线编辑不包含在内', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[0].trigger('click')
      await flushPromises()

      expect(mockConfirm).toHaveBeenCalledWith(
        expect.stringContaining('「八、1」'),
        '确认刷新本章节',
        expect.objectContaining({
          confirmButtonText: '确认刷新',
          cancelButtonText: '取消',
          type: 'warning',
        }),
      )
      const text = mockConfirm.mock.calls[0][0] as string
      expect(text).toContain('以已保存的最新版本为底')
      expect(text).toContain('尚未保存的修改不包含在内')
      expect(text).toContain('另存为新版本')
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

    it('用户确认后调用 refresh-section 端点：先不带确认（由后端检测人工修改），静默全局拦截', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()

      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[0].trigger('click')
      await flushPromises()

      expect(mockApiPost).toHaveBeenCalledTimes(1)
      const [url, body, config] = mockApiPost.mock.calls[0]
      expect(url).toContain('/refresh-section')
      expect(body.section_code).toBe('八、1')
      expect(body.year).toBe(2025)
      expect(body.confirm_overwrite).toBe(false)
      expect(config).toEqual(expect.objectContaining({ _silent: true }))
    })

    it('后端检测到人工修改（requires_confirm）⇒ 二次确认后带确认重发', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()
      mockApiPost
        .mockResolvedValueOnce({ ...REFRESHED, version_no: null, refreshed: [], requires_confirm: true,
          pending_confirm_sections: ['八、1'] })
        .mockResolvedValueOnce(REFRESHED)

      await wrapper.findAll('.lineage-panel__action-btn')[0].trigger('click')
      await flushPromises()

      expect(mockConfirm).toHaveBeenCalledTimes(2)
      expect(mockConfirm.mock.calls[1][0]).toContain('「八、1」在交付件中有手动修改')
      expect(mockApiPost.mock.calls.map((c) => c[1].confirm_overwrite)).toEqual([false, true])
      expect(wrapper.emitted('refreshed')).toEqual([[15]])
    })

    it('二次确认取消 ⇒ 不重发、不提示结果', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()
      mockApiPost.mockResolvedValueOnce({ ...REFRESHED, version_no: null, refreshed: [], requires_confirm: true,
        pending_confirm_sections: ['八、1'] })
      mockConfirm.mockResolvedValueOnce('confirm').mockRejectedValueOnce('cancel')

      await wrapper.findAll('.lineage-panel__action-btn')[0].trigger('click')
      await flushPromises()

      expect(mockApiPost).toHaveBeenCalledTimes(1)
      expect(mockMsg.success).not.toHaveBeenCalled()
      expect(wrapper.emitted('refreshed')).toBeUndefined()
    })
  })

  describe('"刷新所有过期"按钮', () => {
    it('先取最新章节状态，确认框写明过期节数，确认后调用 refresh-stale 端点', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()

      const buttons = wrapper.findAll('.lineage-panel__action-btn')
      await buttons[1].trigger('click')
      await flushPromises()

      expect(mockConfirm).toHaveBeenCalledWith(
        expect.stringContaining('全部过期章节（共 1 节）'), '确认刷新所有过期章节', expect.any(Object))
      expect(mockApiPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockApiPost.mock.calls[0]
      expect(url).toContain('/refresh-stale')
      expect(body.year).toBe(2025)
      expect(body.confirm_overwrite).toBe(false)
    })

    it('没有过期章节 ⇒ 轻提示，不弹确认、不调端点', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      sectionStates = [{ section_code: '八、1', is_stale: false }]
      mockApiPost.mockClear()

      await wrapper.findAll('.lineage-panel__action-btn')[1].trigger('click')
      await flushPromises()

      expect(mockMsg.info).toHaveBeenCalledWith('当前没有过期章节，无需刷新')
      expect(mockConfirm).not.toHaveBeenCalled()
      expect(mockApiPost).not.toHaveBeenCalled()
    })

    it('章节状态取不到 ⇒ 不当成「没有过期章节」，确认后交给后端判断', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      sectionStates = new Error('网络错误')
      mockApiPost.mockClear()

      await wrapper.findAll('.lineage-panel__action-btn')[1].trigger('click')
      await flushPromises()

      expect(mockConfirm.mock.calls[0][0]).toContain('全部过期章节，')
      expect(mockApiPost).toHaveBeenCalledTimes(1)
    })
  })

  describe('刷新结果提示（spec deliverable-trio-generation-accuracy 16b）', () => {
    async function clickRefreshSection(result: Record<string, unknown>, extraProps = {}) {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft', ...extraProps })
      mockApiPost.mockClear()
      mockApiPost.mockResolvedValue(result)
      await wrapper.findAll('.lineage-panel__action-btn')[0].trigger('click')
      await flushPromises()
      return wrapper
    }

    it('落了新版本：提示刷新节数与版本号，emit refreshed(版本号)', async () => {
      const wrapper = await clickRefreshSection(REFRESHED)
      expect(mockMsg.success).toHaveBeenCalledWith('已刷新 1 节（八、1），已另存为第 15 版')
      expect(wrapper.emitted('refreshed')).toEqual([[15]])
    })

    it('未刷新（跳过）：逐条列出后端给的原因，不提示「已刷新」、不 emit', async () => {
      const reason = '八、1：按最新数据该节已没有可出具的内容（或已不在勾选范围），增量刷新不删除章节；如需删除请整份重新生成'
      const wrapper = await clickRefreshSection({ ...REFRESHED, version_no: null, refreshed: [], skipped: ['八、1'],
        messages: [reason] })
      expect(mockMsg.success).not.toHaveBeenCalled()
      expect(wrapper.emitted('refreshed')).toBeUndefined()
      expect(mockAlert).toHaveBeenCalledTimes(1)
      const [vnode, title] = mockAlert.mock.calls[0]
      expect(title).toBe('未刷新')
      const lines = (vnode.children as any[]).map((p) => p.children)
      expect(lines).toEqual([`• ${reason}`])
    })

    it('刷新了但带提醒（出具章节集合变化）：列出已刷新与提醒，仍 emit', async () => {
      const drift = '按最新数据出具的章节与当前交付件不同：新增 1 节（八、9）。'
      const wrapper = await clickRefreshSection({ ...REFRESHED, messages: [drift] })
      const [vnode, title] = mockAlert.mock.calls[0]
      expect(title).toBe('刷新完成，请留意以下提醒')
      expect((vnode.children as any[]).map((p) => p.children)).toEqual(
        ['• 已刷新 1 节（八、1），已另存为第 15 版', `• ${drift}`])
      expect(wrapper.emitted('refreshed')).toEqual([[15]])
    })

    it('在线编辑本次会话已有修改：拒绝刷新并说明，不弹确认、不调端点', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft', editorHasUnsavedEdits: true })
      mockApiPost.mockClear()
      for (const idx of [0, 1]) {
        await wrapper.findAll('.lineage-panel__action-btn')[idx].trigger('click')
        await flushPromises()
      }
      expect(mockAlert).toHaveBeenCalledTimes(2)
      expect(mockAlert.mock.calls[0][0]).toContain('尚未保存回交付件')
      expect(mockAlert.mock.calls[0][1]).toBe('请先保存在线编辑')
      expect(mockConfirm).not.toHaveBeenCalled()
      expect(mockApiPost).not.toHaveBeenCalled()
    })

    it('后端 409（终态）：显示后端说明', async () => {
      const wrapper = await mountWithSection({ deliverableStatus: 'draft' })
      mockApiPost.mockClear()
      mockApiPost.mockRejectedValue({ response: { status: 409, data: { detail: '该出品物已签字，不可回填或刷新' } } })
      await wrapper.findAll('.lineage-panel__action-btn')[0].trigger('click')
      await flushPromises()
      expect(mockMsg.warning).toHaveBeenCalledWith('该出品物已签字，不可回填或刷新')
      expect(wrapper.emitted('refreshed')).toBeUndefined()
    })

    it('不支持章节刷新的交付件（能力标志 false）：不显示刷新按钮，改为说明', async () => {
      const wrapper = await mountWithSection({ supportsSectionRefresh: false })
      expect(wrapper.find('.lineage-panel__refresh-toolbar').exists()).toBe(false)
      expect(wrapper.find('.lineage-panel__refresh-unsupported').text()).toContain('不支持按章节刷新')
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

  describe('SSE LINKAGE_STALE_CHANGED 实时更新（迁移到项目事件流单例总线）', () => {
    it('组件挂载时订阅项目级 LINKAGE_STALE_CHANGED 事件', async () => {
      mount(LineagePanel, { props: baseProps })
      await nextTick()
      expect(mockSubs.length).toBeGreaterThanOrEqual(1)
      expect(mockSubs[0].projectId).toBe('proj-001')
      expect(mockSubs[0].eventName).toBe('LINKAGE_STALE_CHANGED')
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
      // 经总线分发 LINKAGE_STALE_CHANGED（createSSE 已 JSON.parse，handler 收对象 + event 名）
      mockSubs[0].handler({ section_code: '八、1', is_stale: false }, 'LINKAGE_STALE_CHANGED')
      await nextTick()
      await flushPromises()
      await nextTick()

      expect(wrapper.find('.lineage-panel__stale-badge').exists()).toBe(false)
    })

    it('组件卸载时关闭 SSE 订阅', async () => {
      const wrapper = mount(LineagePanel, { props: baseProps })
      await nextTick()
      const sub = mockSubs[0]

      wrapper.unmount()
      expect(sub.close).toHaveBeenCalled()
    })
  })
})
