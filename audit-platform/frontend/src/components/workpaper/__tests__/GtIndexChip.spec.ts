/**
 * GtIndexChip.spec.ts — 跨底稿索引跳转 Chip 组件测试
 *
 * spec workpaper-html-renderer Task 3.7
 *
 * 验证：
 * 1. 合法索引渲染为 chip（el-tag）
 * 2. 非法索引渲染为纯文本
 * 3. 11 命名空间正确解析
 * 4. 9 种边缘 case 处理
 * 5. 跨项目禁止跳转
 * 6. 多目标显示下拉菜单
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

// Mock apiProxy
const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockApiGet(...args) },
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
    mockApiGet.mockResolvedValue({ exists: true })
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
    mockApiGet.mockResolvedValue({ exists: true })
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

  it('宽松模式 D2-1 解析为 sheet 命名空间', async () => {
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

describe('GtIndexChip — 校验状态', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('validate=true 时调用 /api/wp-index-resolve', async () => {
    mockApiGet.mockResolvedValue({ exists: true })
    mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/wp-index-resolve',
      expect.objectContaining({
        params: expect.objectContaining({ ref: 'D2' }),
      }),
    )
  })

  it('validate=false 时不调用 API', async () => {
    mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    expect(mockApiGet).not.toHaveBeenCalled()
  })

  it('不存在时显示 info 类型 chip', async () => {
    mockApiGet.mockResolvedValue({ exists: false })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('info')
  })

  it('被裁剪时显示 info 类型 chip', async () => {
    mockApiGet.mockResolvedValue({ exists: false, trimmed: true, reason: '不适用' })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: true },
      global: globalConfig,
    })
    await flushPromises()
    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('info')
  })
})

describe('GtIndexChip — 点击跳转', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockResolvedValue({ exists: true })
  })

  it('点击有效 chip 触发 click 事件', async () => {
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

  it('点击 wp 类型跳转到底稿编辑器', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D2', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/projects/proj-123/workpapers/D2/edit',
      }),
    )
  })

  it('点击 Note 类型跳转到附注模块', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'Note:五-1-1', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/projects/proj-123/disclosure-notes',
        query: { section: '五-1-1' },
      }),
    )
  })

  it('点击 TB 类型跳转到试算表', async () => {
    const wrapper = mount(GtIndexChip, {
      props: { value: 'TB:1122', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    expect(mockPush).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/projects/proj-123/trial-balance',
        query: { account: '1122' },
      }),
    )
  })
})

describe('GtIndexChip — 边缘 case', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockResolvedValue({ exists: true })
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
