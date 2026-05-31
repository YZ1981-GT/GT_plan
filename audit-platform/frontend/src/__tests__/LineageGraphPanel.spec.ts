/**
 * LineageGraphPanel.vue 组件测试
 *
 * 验证 props→render + emit 行为：
 * - drawer 打开/关闭
 * - API 响应渲染 upstream/downstream/attachments 区域
 * - node click 触发 locateCell
 * - attachment click 触发 'preview-attachment' emit
 * - 空溯源显示 el-empty
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

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

const mockLocateCell = vi.fn().mockReturnValue(true)
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: mockLocateCell }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-001' },
    query: {},
  }),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn().mockReturnValue(Promise.resolve()),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() },
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

  it('calls locateCell when upstream node is clicked', async () => {
    mockApiGet.mockResolvedValue(mockLineageData)
    const wrapper = await factoryWithLoad()
    const upstreamNodes = wrapper.findAll('.upstream-node')
    expect(upstreamNodes.length).toBe(2)
    await upstreamNodes[0].trigger('click')
    expect(mockLocateCell).toHaveBeenCalledWith(
      expect.objectContaining({
        wp_code: 'A1',
        sheet_name: '程序表',
        cell_ref: 'B3',
        label: '审计程序',
      }),
    )
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
