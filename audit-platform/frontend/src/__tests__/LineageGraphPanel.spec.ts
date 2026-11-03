/**
 * LineageGraphPanel.vue 组件测试
 *
 * 验证 props→render + emit 行为：
 * - drawer 打开/关闭
 * - API 响应渲染 upstream/downstream/attachments 区域
 * - node click：当前底稿的节点交渲染器定位（locate-cell 事件），其余打开该底稿编辑器并带 ?sheet=&cell=
 *   （spec wp-deeplink-locate-coverage-closure 需求 3.2；原先只在当前页面找、找不到却提示「定位到 X」）
 * - attachment click 触发 'preview-attachment' emit
 * - 空溯源显示 el-empty
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { eventBus } from '@/utils/eventBus'

const { mockPush, mockRoute, resolveMock, warnMock } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockRoute: { params: { projectId: 'proj-001' } as Record<string, string>, query: {} },
  resolveMock: vi.fn(),
  warnMock: vi.fn(),
}))
const WP_A1 = '0b6f5c1e-2a3d-4e5f-8a9b-0c1d2e3f4a5b'
const WP_CURRENT = '8c8cd491-2d21-48ce-9622-e2d9bca0d499'

vi.mock('@/services/resolveWorkpaperByCode', () => ({ resolveWorkpaperByCode: resolveMock }))

const mockApiGet = vi.fn()

vi.mock('@/utils/apiProxy', () => ({
  apiProxy: {
    get: (...args: any[]) => mockApiGet(...args),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn().mockReturnValue(Promise.resolve()),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: warnMock },
}))

import LineageGraphPanel from '@/components/workpaper/LineageGraphPanel.vue'

const stubs = {
  'el-drawer': {
    template: '<div class="el-drawer" v-if="modelValue"><slot /></div>',
    props: ['modelValue', 'title', 'direction', 'size', 'destroyOnClose'],
    emits: ['update:modelValue'],
  },
  'el-empty': {
    template: '<div class="el-empty">{{ description }}</div>',
    props: ['description'],
  },
  'el-icon': {
    template: '<i class="el-icon"><slot /></i>',
  },
  'el-tag': {
    template: '<span class="el-tag"><slot /></span>',
    props: ['size', 'type'],
  },
  Location: { template: '<span />' },
  Top: { template: '<span />' },
  Bottom: { template: '<span />' },
  Document: { template: '<span />' },
  Paperclip: { template: '<span />' },
}

const mockLineageData = {
  current: { wp_code: 'D2-1', cell_ref: 'C5', component_type: 'd-form-table' },
  upstream: [
    { wp_code: 'A1', sheet_name: '程序表', cell_ref: 'B3', label: '审计程序' },
    { wp_code: 'B1', sheet_name: '目录', cell_ref: null, label: null },
  ],
  downstream: [
    { wp_code: 'K8', sheet_name: '管理费用', cell_ref: 'D10', label: '费用明细' },
  ],
  attachments: [
    { id: 'att-1', attachment_id: 'file-001', target_type: 'workpaper', file_name: '银行对账单.pdf', file_type: 'pdf' },
    { id: 'att-2', attachment_id: 'file-002', target_type: 'workpaper', file_name: '合同扫描件.jpg', file_type: 'image' },
  ],
}

/**
 * The component watches modelValue and fetches on change to true.
 * Mount with false then switch to true to trigger the watch.
 */
async function factoryWithLoad(props: Record<string, any> = {}) {
  const wrapper = mount(LineageGraphPanel, {
    props: {
      modelValue: false,
      objectType: 'workpaper',
      objectId: 'wp-001',
      ...props,
    },
    global: {
      stubs,
      directives: { loading: () => {} },
    },
  })
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}

function factory(props: Record<string, any> = {}) {
  return mount(LineageGraphPanel, {
    props: {
      modelValue: true,
      objectType: 'workpaper',
      objectId: 'wp-001',
      ...props,
    },
    global: {
      stubs,
      directives: { loading: () => {} },
    },
  })
}

describe('LineageGraphPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resolveMock.mockReset()
    mockPush.mockReset()
    mockPush.mockResolvedValue(undefined)
    mockRoute.params = { projectId: 'proj-001' }
  })

  it('opens drawer when modelValue=true', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    expect(wrapper.find('.el-drawer').exists()).toBe(true)
  })

  it('calls API with correct params', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    await factoryWithLoad({ objectType: 'cell', objectId: 'cell-xyz' })
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/projects/proj-001/lineage',
      {
        params: {
          object_type: 'cell',
          object_id: 'cell-xyz',
          direction: 'both',
        },
      },
    )
  })

  it('renders upstream section with correct count', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const text = wrapper.text()
    expect(text).toContain('上游来源（2）')
    expect(text).toContain('A1')
    expect(text).toContain('B1')
  })

  it('renders downstream section with correct count', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const text = wrapper.text()
    expect(text).toContain('下游影响（1）')
    expect(text).toContain('K8')
  })

  it('renders attachments section with correct count', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const text = wrapper.text()
    expect(text).toContain('关联附件（2）')
    expect(text).toContain('银行对账单.pdf')
    expect(text).toContain('合同扫描件.jpg')
  })

  it('点别的底稿的节点：按编码取本项目底稿后打开编辑器并带 ?sheet=&cell=，关闭抽屉', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    resolveMock.mockResolvedValueOnce({ wpId: WP_A1 })
    const wrapper = await factoryWithLoad()
    const upstreamNodes = wrapper.findAll('.upstream-node')
    expect(upstreamNodes.length).toBe(2)
    await upstreamNodes[0].trigger('click')
    await flushPromises()
    expect(resolveMock).toHaveBeenCalledWith('proj-001', 'A1', true)
    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_A1 },
      query: { sheet: '程序表', cell: 'B3' },
    })
    expect(warnMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('本项目没有该底稿：提示原因、不跳转（不再假报「定位到 X」）', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    resolveMock.mockResolvedValue(null)
    const wrapper = await factoryWithLoad()
    await wrapper.findAll('.downstream-node')[0].trigger('click')
    await flushPromises()
    expect(mockPush).not.toHaveBeenCalled()
    expect(warnMock).toHaveBeenCalledWith('本项目未找到底稿 K8（可能尚未生成）')
  })

  it('节点就是当前打开的底稿：交渲染器定位（locate-cell 事件），不跳转', async () => {
    mockRoute.params = { projectId: 'proj-001', wpId: WP_CURRENT }
    mockApiGet.mockResolvedValue({
      ...mockLineageData,
      upstream: [{ wp_code: 'E1', wp_id: WP_CURRENT, sheet_name: '分析程序E1-14', cell_ref: 'C34', label: null }],
    })
    const seen: any[] = []
    const onLocate = (payload: any) => seen.push(payload)
    eventBus.on('workpaper:locate-cell', onLocate)
    try {
      const wrapper = await factoryWithLoad()
      await wrapper.findAll('.upstream-node')[0].trigger('click')
      await flushPromises()
      expect(seen).toEqual([{ wpId: WP_CURRENT, sheetName: '分析程序E1-14', cellRef: 'C34' }])
      expect(mockPush).not.toHaveBeenCalled()
      expect(resolveMock).not.toHaveBeenCalled()
    } finally {
      eventBus.off('workpaper:locate-cell', onLocate)
    }
  })

  it('没带 wp_id 的节点：编码与「当前对象」相同且在编辑器里 ⇒ 交渲染器定位；不在编辑器里 ⇒ 打开编辑器', async () => {
    mockRoute.params = { projectId: 'proj-001', wpId: WP_CURRENT }
    mockApiGet.mockResolvedValue(mockLineageData)
    const seen: any[] = []
    const onLocate = (payload: any) => seen.push(payload)
    eventBus.on('workpaper:locate-cell', onLocate)
    try {
      const inEditor = await factoryWithLoad()
      await inEditor.find('.current-node').trigger('click')
      await flushPromises()
      expect(seen).toEqual([{ wpId: WP_CURRENT, sheetName: undefined, cellRef: 'C5' }])
      expect(mockPush).not.toHaveBeenCalled()
      inEditor.unmount()

      mockRoute.params = { projectId: 'proj-001' }
      resolveMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ wpId: WP_CURRENT })
      const elsewhere = await factoryWithLoad()
      await elsewhere.find('.current-node').trigger('click')
      await flushPromises()
      expect(seen).toHaveLength(1)
      expect(resolveMock.mock.calls.map((c) => c[1])).toEqual(['D2-1', 'D2'])
      expect(mockPush).toHaveBeenCalledWith({
        name: 'WorkpaperEditor',
        params: { projectId: 'proj-001', wpId: WP_CURRENT },
        query: { sheet: 'D2-1', cell: 'C5' },
      })
    } finally {
      eventBus.off('workpaper:locate-cell', onLocate)
    }
  })

  it('emits preview-attachment when attachment node is clicked', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const attachmentNodes = wrapper.findAll('.attachment-node')
    expect(attachmentNodes.length).toBe(2)
    await attachmentNodes[0].trigger('click')
    expect(wrapper.emitted('preview-attachment')).toBeTruthy()
    expect(wrapper.emitted('preview-attachment')![0][0]).toMatchObject({
      id: 'att-1',
      file_name: '银行对账单.pdf',
    })
  })

  it('shows el-empty when lineage has no upstream/downstream/attachments', async () => {
    mockApiGet.mockResolvedValue({
      current: { wp_code: 'D2-1', cell_ref: 'C5' },
      upstream: [],
      downstream: [],
      attachments: [],
    })
    const wrapper = await factoryWithLoad()
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.find('.el-empty').text()).toContain('暂无溯源数据')
  })

  it('does not call API when modelValue=false', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    factory({ modelValue: false })
    await flushPromises()
    expect(mockApiGet).not.toHaveBeenCalled()
  })

  it('renders current node with wp_code', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const currentNode = wrapper.find('.current-node')
    expect(currentNode.exists()).toBe(true)
    expect(currentNode.text()).toContain('D2-1')
  })

  it('renders node details (sheet_name, cell_ref, label)', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const text = wrapper.text()
    // upstream[0] has sheet_name='程序表', cell_ref='B3', label='审计程序'
    expect(text).toContain('程序表')
    expect(text).toContain('B3')
    expect(text).toContain('审计程序')
  })
})
