/**
 * GtIndexChip.spec.ts — 跨底稿索引跳转 Chip 组件测试
 *
 * spec acnr Task 17.2
 *
 * 验证：
 * 1. 合法索引渲染为 chip（el-tag）
 * 2. 非法索引渲染为纯文本
 * 3. 11 命名空间正确解析
 * 4. validate=true 时调 ACNR resolve（R13.3）
 * 5. 使用 ACNR 返回的 jump_route 跳转（R7.3）
 * 6. ACNR 不可用时显示 error 状态不回退旧逻辑（R13.5）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import GtIndexChip from '../GtIndexChip.vue'

// Mock vue-router
const mockPush = vi.fn()
const mockRoute = {
  params: { projectId: 'proj-123' },
  path: '/projects/proj-123/workpapers/wp-001/edit',
  query: {},
}
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockPush }),
}))

// Mock ACNR composable
const mockAcnrResolve = vi.fn()
const mockAcnrResolveInstance = vi.fn()
vi.mock('@/services/acnr', () => ({
  useAcnr: () => ({
    resolve: mockAcnrResolve,
    resolveInstance: mockAcnrResolveInstance,
  }),
}))

// Element Plus stubs
const ElTag = {
  name: 'ElTag',
  template: '<span class="el-tag-stub" :class="[$attrs.class]" :data-type="type" :data-effect="effect"><slot /></span>',
  props: ['type', 'effect', 'size'],
}

const ElTooltip = {
  name: 'ElTooltip',
  template: '<div class="el-tooltip-stub" :data-content="content"><slot /></div>',
  props: ['content', 'disabled', 'placement'],
}

const ElDropdown = {
  name: 'ElDropdown',
  template: '<div class="el-dropdown-stub"><slot /><slot name="dropdown" /></div>',
  props: ['trigger'],
  emits: ['command'],
}

const ElDropdownMenu = {
  name: 'ElDropdownMenu',
  template: '<div class="el-dropdown-menu-stub"><slot /></div>',
}

const ElDropdownItem = {
  name: 'ElDropdownItem',
  template: '<div class="el-dropdown-item-stub" :data-command="command"><slot /></div>',
  props: ['command'],
}

const globalConfig = {
  components: {
    'el-tag': ElTag,
    'el-tooltip': ElTooltip,
    'el-dropdown': ElDropdown,
    'el-dropdown-menu': ElDropdownMenu,
    'el-dropdown-item': ElDropdownItem,
  },
}

describe('GtIndexChip — 基本渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2', jump_route: '/projects/proj-123/workpapers/wp-001/edit' })
  })

  it('合法底稿编码渲染为 chip', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('非法值渲染为纯文本', () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: '这不是索引', validate: false },
      global: globalConfig,
    })
    expect(wrapper.find('.gt-index-chip--plain').exists()).toBe(true)
    expect(wrapper.find('.el-tag-stub').exists()).toBe(false)
  })

  it('GT_Custom 值渲染为纯文本（白名单跳过）', () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'GT_Custom_Sheet', validate: false },
      global: globalConfig,
    })
    expect(wrapper.find('.gt-index-chip--plain').exists()).toBe(true)
  })

  it('空字符串渲染为纯文本', () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: '', validate: false },
      global: globalConfig,
    })
    expect(wrapper.find('.gt-index-chip--plain').exists()).toBe(true)
  })
})

describe('GtIndexChip — 11 命名空间解析', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2-2/E100' })
  })

  it('Note:五-1-1 解析为 Note 命名空间', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'Note:五-1-1', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('Note:五-1-1')
  })

  it('TB:1122 解析为 TB 命名空间', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'TB:1122', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('TB:1122')
  })

  it('宽松模式 D2-1 解析为 wp 命名空间', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2-1', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('宽松模式 D2 解析为 wp 命名空间', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('Adj:AJE-001 解析为 Adj 命名空间', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'Adj:AJE-001', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('Adj:AJE-001')
  })
})

describe('GtIndexChip — ACNR resolve 校验（R13.3）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('validate=true 时调用 ACNR resolve（不调旧 wp-index-resolve）', async () => {
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2', jump_route: '/projects/proj-123/workpapers/wp-001/edit' })
    mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    expect(mockAcnrResolve).toHaveBeenCalledWith({
      index_ref: 'wp:D2',
      project_id: 'proj-123',
    })
  })

  it('validate=false 时不调用 ACNR', async () => {
    mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(mockAcnrResolve).not.toHaveBeenCalled()
  })

  it('ACNR resolve 返回 found:false 时显示 info 类型 chip', async () => {
    mockAcnrResolve.mockResolvedValue({ found: false, candidates: [] })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('info')
  })

  it('ACNR resolve 返回 trimmed 时显示 info 类型 chip', async () => {
    mockAcnrResolve.mockResolvedValue({ found: false, trimmed: true, reason: '不适用' })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('info')
  })

  it('ACNR 不可用时显示 error 状态（R13.5: 不回退旧逻辑）', async () => {
    mockAcnrResolve.mockRejectedValue(new Error('Network error'))
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('danger')
  })

  it('cell:D2-2!E100 索引调用 ACNR resolve 时传 index_ref=cell:D2-2!E100（R11.3）', async () => {
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2-2/E100' })
    mount(GtIndexChip, {
      props: { value: 'cell:D2-2!E100', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    expect(mockAcnrResolve).toHaveBeenCalledWith({
      index_ref: 'cell:D2-2!E100',
      project_id: 'proj-123',
    })
  })
})

describe('GtIndexChip — 跳转使用 ACNR jump_route（R7.3）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ACNR 返回 jump_route 时直接用 jump_route 跳转', async () => {
    mockAcnrResolve.mockResolvedValue({
      found: true,
      addr_id: 'D2/D2-2/E100',
      jump_route: '/projects/proj-123/workpapers/wp-abc/edit?sheet=D2-2',
    })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'cell:D2-2!E100', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-123/workpapers/wp-abc/edit?sheet=D2-2')
  })

  it('ACNR resolve 命中无 jump_route 时用 resolveInstance 跳转 wp 类型', async () => {
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2' })
    mockAcnrResolveInstance.mockResolvedValue({
      found: true,
      wp_id: 'wp-uuid-123',
      jump_route: '/projects/proj-123/workpapers/wp-uuid-123/edit',
    })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    await flushPromises()
    // Should use jump_route from resolveInstance
    expect(mockAcnrResolveInstance).toHaveBeenCalledWith({
      project_id: 'proj-123',
      parent: 'D2',
      sheet_code: 'D2',
    })
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-123/workpapers/wp-uuid-123/edit')
  })

  it('点击有效 chip 触发 click 事件', async () => {
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2' })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')![0][0]).toMatchObject({
      ns: 'wp',
      layer: 3,
      target: 'D2',
    })
  })
})

describe('GtIndexChip — 灰态兜底', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ACNR 返回 found:false 时显示灰态 chip', async () => {
    mockAcnrResolve.mockResolvedValue({ found: false })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'S4-1', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.exists()).toBe(true)
    expect(tag.attributes('data-type')).toBe('info')
    expect(tag.classes()).toContain('gt-index-chip--disabled')
  })

  it('灰态 chip 的 tooltip 显示"底稿不存在"', async () => {
    mockAcnrResolve.mockResolvedValue({ found: false })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'B10', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tooltip = wrapper.find('.el-tooltip-stub')
    expect(tooltip.attributes('data-content')).toBe('底稿不存在')
  })

  it('灰态 chip 点击不触发导航', async () => {
    mockAcnrResolve.mockResolvedValue({ found: false })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'S17', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).not.toHaveBeenCalled()
    expect(wrapper.emitted('click')).toBeFalsy()
  })
})

describe('GtIndexChip — 边缘 case', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAcnrResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2' })
  })

  it('带空格的值 trim 后正常解析', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: '  D2  ', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('大小写归一化（d2 → D2）', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'd2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('中文索引号正常解析', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'Note:五、(1)货币资金', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
  })

  it('跨项目场景禁止跳转', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: false, contextProjectId: 'other-project' },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('多目标值（含 /）渲染为 dropdown', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2-1/D2-2/D2-3', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.el-dropdown-stub').exists()).toBe(true)
  })
})
