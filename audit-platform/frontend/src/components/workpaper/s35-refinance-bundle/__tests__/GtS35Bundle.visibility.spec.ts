/**
 * GtS35Bundle.visibility.spec.ts — Tab 可见性验证（Task 6.2, 6.3）
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 6.2, 6.3
 * Validates: Requirements 6.2, 6.3, 6.4
 *
 * 覆盖：
 *  - Req 6.2: wp_index 中不存在的底稿 → 对应 Tab 隐藏（非禁用）
 *  - Req 6.3: 解析到的 wp_id 正确传递给 GtAProgramConsole
 *  - Req 6.4: 无任何 S35 底稿 → 显示空状态提示
 *
 * 场景：
 *  - wp_index 仅含 3/5 底稿 → 只渲染 3 个 Tab
 *  - wp_index 仅含 1/5 底稿 → 只渲染 1 个 Tab
 *  - 各 Tab 的 GtAProgramConsole 接收正确的 wp_id
 *  - wp_index 返回空数组 → 显示空状态
 *  - wp_index 仅含非 S35 底稿 → 显示空状态
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mocks ───

const mockGet = vi.fn()
const mockGetWpIndex = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: (...args: any[]) => mockGetWpIndex(...args),
}))

const routeMock = {
  params: { projectId: 'proj-1' },
  query: {} as Record<string, any>,
}
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ push: vi.fn() }),
}))

// 子组件 stub：暴露 data-wp-id 便于断言 wp_id 传播
vi.mock('../../GtAProgramConsole.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtAProgramConsole',
    props: ['wpId', 'sheetName', 'readonly'],
    emits: ['jump-to-workpaper'],
    template:
      '<div class="program-console-stub" :data-wp-id="wpId" :data-sheet="sheetName" />',
  },
}))
vi.mock('../GtS35DetailTable.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtS35DetailTable',
    props: ['wpId', 'sheetCode', 'readonly'],
    emits: ['data-changed'],
    template: '<div class="detail-table-stub" :data-wp-id="wpId" />',
  },
}))

import GtS35Bundle from '../GtS35Bundle.vue'

// ─── el-* stubs ───

const stubs = {
  'el-alert': { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label', 'lazy'],
    template: '<div class="el-tab-pane-stub" :data-name="name" :data-label="label"><slot /></div>',
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-radio-group-stub"><slot /></div>',
  },
  'el-radio-button': {
    props: ['value'],
    template: '<span class="el-radio-button-stub">{{ value }}</span>',
  },
  'el-result': { props: ['icon', 'title'], template: '<div class="el-result-stub"><p class="el-result__title">{{ title }}</p><slot /><slot name="sub-title" /></div>' },
  'el-icon': { template: '<i class="el-icon-stub" />' },
}

function mountBundle(props: Record<string, any> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve([])
    }
    return Promise.resolve({})
  })
  return mount(GtS35Bundle, {
    props: { wpId: 'wp-s35', ...props },
    global: {
      stubs,
      directives: { loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockGetWpIndex.mockReset()
  routeMock.query = {}
})

// ─── Req 6.2：部分底稿存在 → 仅对应 Tab 可见 ───
describe('GtS35Bundle — Tab 可见性（Req 6.2）', () => {
  it('wp_index 仅含 3/5 底稿（S35-1/S35-3/S35-5）→ 只渲染 3 个 Tab', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-1', wp_id: 'wp-s35-1', id: 'idx-1' },
      { wp_code: 'S35-1-1', wp_id: 'wp-s35-1-1', id: 'idx-1-1' },
      { wp_code: 'S35-3', wp_id: 'wp-s35-3', id: 'idx-3' },
      { wp_code: 'S35-3-1', wp_id: 'wp-s35-3-1', id: 'idx-3-1' },
      { wp_code: 'S35-5', wp_id: 'wp-s35-5', id: 'idx-5' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(3)

    // 验证可见 Tab 名称正确
    const tabNames = tabPanes.map(p => p.attributes('data-name'))
    expect(tabNames).toContain('S35-1')
    expect(tabNames).toContain('S35-3')
    expect(tabNames).toContain('S35-5')

    // 不可见 Tab 不存在
    expect(tabNames).not.toContain('S35-2')
    expect(tabNames).not.toContain('S35-4')
  })

  it('wp_index 仅含 1/5 底稿（S35-4）→ 只渲染 1 个 Tab', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-4', wp_id: 'wp-s35-4', id: 'idx-4' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(1)
    expect(tabPanes[0].attributes('data-name')).toBe('S35-4')
  })

  it('wp_index 含全部 5 个底稿 → 渲染 5 个 Tab', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-1', wp_id: 'wp-s35-1', id: 'idx-1' },
      { wp_code: 'S35-2', wp_id: 'wp-s35-2', id: 'idx-2' },
      { wp_code: 'S35-3', wp_id: 'wp-s35-3', id: 'idx-3' },
      { wp_code: 'S35-4', wp_id: 'wp-s35-4', id: 'idx-4' },
      { wp_code: 'S35-5', wp_id: 'wp-s35-5', id: 'idx-5' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(5)
  })

  it('Tab 是隐藏而非禁用（不存在的 Tab 不渲染 DOM 节点）', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-2', wp_id: 'wp-s35-2', id: 'idx-2' },
      { wp_code: 'S35-4', wp_id: 'wp-s35-4', id: 'idx-4' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(2)

    // 确认隐藏的 Tab 完全不存在于 DOM 中（非 disabled 状态）
    const html = wrapper.html()
    expect(html).not.toContain('data-name="S35-1"')
    expect(html).not.toContain('data-name="S35-3"')
    expect(html).not.toContain('data-name="S35-5"')
  })

  it('wp_id 为 null 的条目被忽略 → 对应 Tab 隐藏', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-1', wp_id: 'wp-s35-1', id: 'idx-1' },
      { wp_code: 'S35-2', wp_id: null, id: 'idx-2' }, // wp_id 为 null → 被忽略
      { wp_code: 'S35-3', wp_id: 'wp-s35-3', id: 'idx-3' },
      { wp_code: 'S35-4', wp_id: undefined, id: 'idx-4' }, // wp_id 为 undefined → 被忽略
      { wp_code: 'S35-5', wp_id: 'wp-s35-5', id: 'idx-5' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(3)

    const tabNames = tabPanes.map(p => p.attributes('data-name'))
    expect(tabNames).toEqual(['S35-1', 'S35-3', 'S35-5'])
  })
})

// ─── Req 6.3：解析到的 wp_id 正确传递给 GtAProgramConsole ───
describe('GtS35Bundle — wp_id 正确传播（Req 6.3）', () => {
  it('无子表 Tab（S35-4）的 GtAProgramConsole 接收 wpIdMap[S35-4]', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-4', wp_id: 'wp-uuid-s35-4', id: 'idx-4' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    const console = wrapper.find('.program-console-stub')
    expect(console.exists()).toBe(true)
    expect(console.attributes('data-wp-id')).toBe('wp-uuid-s35-4')
  })

  it('含子表 Tab（S35-1）的 GtAProgramConsole 接收 wpIdMap[S35-1]', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-1', wp_id: 'wp-uuid-s35-1', id: 'idx-1' },
      { wp_code: 'S35-1-1', wp_id: 'wp-uuid-s35-1-1', id: 'idx-1-1' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    // 默认子 sheet 视图是 'program' → 显示 GtAProgramConsole
    const console = wrapper.find('.program-console-stub')
    expect(console.exists()).toBe(true)
    expect(console.attributes('data-wp-id')).toBe('wp-uuid-s35-1')
  })

  it('多 Tab 场景中各 Tab 的 wp_id 独立且正确', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'S35-1', wp_id: 'uuid-1', id: 'idx-1' },
      { wp_code: 'S35-1-1', wp_id: 'uuid-1-1', id: 'idx-1-1' },
      { wp_code: 'S35-4', wp_id: 'uuid-4', id: 'idx-4' },
      { wp_code: 'S35-5', wp_id: 'uuid-5', id: 'idx-5' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    // 查找所有 program-console-stub
    const consoles = wrapper.findAll('.program-console-stub')
    const wpIds = consoles.map(c => c.attributes('data-wp-id'))

    // S35-1 含子表默认走 program 视图
    expect(wpIds).toContain('uuid-1')
    // S35-4 无子表直接渲染
    expect(wpIds).toContain('uuid-4')
    // S35-5 无子表直接渲染
    expect(wpIds).toContain('uuid-5')
  })
})


// ─── Req 6.4：无任何 S35 底稿 → 空状态提示 ───
describe('GtS35Bundle — 空状态提示（Req 6.4）', () => {
  it('wp_index 返回空数组 → 显示空状态，无 Tab 渲染', async () => {
    mockGetWpIndex.mockResolvedValue([])
    const wrapper = mountBundle()
    await flushPromises()

    // 空状态容器存在
    const emptyState = wrapper.find('.gt-s35-bundle__empty')
    expect(emptyState.exists()).toBe(true)

    // 空状态标题文本
    expect(wrapper.text()).toContain('本项目未启用再融资审核专项底稿')

    // 空状态副标题
    expect(wrapper.text()).toContain('项目底稿索引中未包含 S35 系列底稿')

    // 无 Tab 渲染
    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(0)

    // 无仪表盘
    expect(wrapper.find('[data-testid="s35-dashboard"]').exists()).toBe(false)
  })

  it('wp_index 仅含非 S35 底稿 → 显示空状态', async () => {
    mockGetWpIndex.mockResolvedValue([
      { wp_code: 'D2-1', wp_id: 'wp-d2-1', id: 'idx-d2' },
      { wp_code: 'A1', wp_id: 'wp-a1', id: 'idx-a1' },
      { wp_code: 'C14', wp_id: 'wp-c14', id: 'idx-c14' },
    ])
    const wrapper = mountBundle()
    await flushPromises()

    // 空状态容器存在（非 S35 底稿对 useS35BundleState 不产生 wpIdMap）
    const emptyState = wrapper.find('.gt-s35-bundle__empty')
    expect(emptyState.exists()).toBe(true)

    // 空状态提示文本
    expect(wrapper.text()).toContain('本项目未启用再融资审核专项底稿')

    // 无 Tab
    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(0)
  })

  it('空状态下不渲染 GtAProgramConsole', async () => {
    mockGetWpIndex.mockResolvedValue([])
    const wrapper = mountBundle()
    await flushPromises()

    const consoles = wrapper.findAll('.program-console-stub')
    expect(consoles).toHaveLength(0)

    const detailTables = wrapper.findAll('.detail-table-stub')
    expect(detailTables).toHaveLength(0)
  })
})
