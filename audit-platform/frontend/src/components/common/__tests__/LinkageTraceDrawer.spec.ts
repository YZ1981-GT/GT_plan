/**
 * LinkageTraceDrawer 单元测试（P1-2）
 *
 * 验证穿透面板展示来源/口径/金额/状态/跳转/复制功能。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LinkageTraceDrawer from '../LinkageTraceDrawer.vue'

// Mock apiProxy
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Mock clipboard
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
})

describe('LinkageTraceDrawer', () => {
  const baseProps = {
    modelValue: true,
    projectId: 'proj-001',
    sourceType: 'trial_balance',
    sourceId: 'row-1',
  }

  // Stub all Element Plus components as transparent wrappers
  const globalStubs = {
    'el-drawer': { template: '<div class="el-drawer"><slot /></div>', props: ['modelValue'] },
    'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
    'el-button': { template: '<button class="el-button"><slot /></button>', props: ['type', 'text', 'size', 'disabled'] },
    'el-empty': { template: '<div class="el-empty">{{ description }}</div>', props: ['description', 'imageSize'] },
    'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应渲染 drawer 组件', () => {
    mockGet.mockResolvedValue({ contracts: [], total: 0 })
    const wrapper = mount(LinkageTraceDrawer, {
      props: { ...baseProps, modelValue: false },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.el-drawer').exists()).toBe(true)
  })

  it('drawer 打开时应发起 API 请求', async () => {
    mockGet.mockResolvedValue({ contracts: [], total: 0 })

    mount(LinkageTraceDrawer, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    await flushPromises()

    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/proj-001/linkage/trace',
      expect.objectContaining({
        params: expect.objectContaining({
          source_type: 'trial_balance',
          source_id: 'row-1',
        }),
      }),
    )
  })

  it('应正确显示 contract 卡片内容', async () => {
    mockGet.mockResolvedValue({
      contracts: [
        {
          source_type: 'trial_balance',
          source_id: 'row-1',
          target_type: 'workpaper',
          target_id: 'wp-001',
          amount: '100000.00',
          basis: 'TB audited → WP',
          status: 'stale',
          confidence: 'system',
          route: '/projects/proj-001/workpapers/wp-001',
          conflict_id: null,
        },
      ],
      total: 1,
    })

    const wrapper = mount(LinkageTraceDrawer, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('试算表')
    expect(html).toContain('底稿')
    expect(html).toContain('过期') // stale status label
    expect(html).toContain('TB audited → WP')
    expect(html).toContain('系统计算')
  })

  it('conflict_id 存在时应展示冲突 badge', async () => {
    mockGet.mockResolvedValue({
      contracts: [
        {
          source_type: 'trial_balance',
          source_id: 'row-1',
          target_type: 'workpaper',
          target_id: 'wp-001',
          amount: null,
          basis: 'test',
          status: 'conflict',
          confidence: 'system',
          route: null,
          conflict_id: 'conflict-123',
        },
      ],
      total: 1,
    })

    const wrapper = mount(LinkageTraceDrawer, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('冲突')
  })

  it('点击跳转查看应调用 router.push', async () => {
    mockGet.mockResolvedValue({
      contracts: [
        {
          source_type: 'trial_balance',
          source_id: 'row-1',
          target_type: 'workpaper',
          target_id: 'wp-001',
          amount: null,
          basis: 'test',
          status: 'current',
          confidence: 'system',
          route: '/projects/proj-001/workpapers/wp-001',
          conflict_id: null,
        },
      ],
      total: 1,
    })

    const wrapper = mount(LinkageTraceDrawer, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    await flushPromises()

    // Find the jump button and click it
    const buttons = wrapper.findAll('.el-button')
    const jumpButton = buttons.find(b => b.text().includes('跳转查看'))
    expect(jumpButton).toBeTruthy()
    await jumpButton!.trigger('click')

    expect(mockPush).toHaveBeenCalledWith('/projects/proj-001/workpapers/wp-001')
  })

  it('点击复制引用应调用 clipboard API', async () => {
    mockGet.mockResolvedValue({
      contracts: [
        {
          source_type: 'trial_balance',
          source_id: 'row-1',
          target_type: 'workpaper',
          target_id: 'wp-001',
          amount: '50000',
          basis: 'TB → WP',
          status: 'current',
          confidence: 'system',
          route: null,
          conflict_id: null,
        },
      ],
      total: 1,
    })

    const wrapper = mount(LinkageTraceDrawer, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    await flushPromises()

    const buttons = wrapper.findAll('.el-button')
    const copyButton = buttons.find(b => b.text().includes('复制引用'))
    expect(copyButton).toBeTruthy()
    await copyButton!.trigger('click')

    expect(navigator.clipboard.writeText).toHaveBeenCalled()
  })
})
