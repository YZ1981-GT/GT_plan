/**
 * GtAProgramConsoleA16Seq2.spec.ts — A16 seq2 推荐版本置顶 + 折叠 UI 测试
 *
 * 验证：
 * 1. A16 程序表 seq2 行：推荐版本 chip 置顶 + "推荐" badge
 * 2. 非推荐版本折叠于"其他版本 ▼"toggle 下
 * 3. 展开后所有版本 chip 可见（非禁用）
 * 4. 非 A16 程序表不触发推荐版本逻辑
 *
 * Validates: Requirements 1（seq2 chip 展示规则）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtAProgramConsole from '../GtAProgramConsole.vue'

// Mock vue-router useRoute — A16 程序表
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock apiProxy — 返回推荐版本
const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

// Mock composables
vi.mock('@/composables/useWpOnboardingGuide', () => ({
  useWpOnboardingGuide: () => ({
    showGuide: { value: false },
    guideSteps: { value: [] },
    triggerGuide: vi.fn(),
  }),
}))

vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({
  default: { name: 'GtAuditFlowGraph', template: '<div />' },
}))

vi.mock('@/components/workpaper/WpInlinePopup.vue', () => ({
  default: { name: 'WpInlinePopup', template: '<div />', props: ['visible', 'wpCode', 'wpId', 'projectId'] },
}))

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock" :data-value="value">{{ value }}</span>',
    props: ['value', 'validate', 'preventNavigate'],
    emits: ['click'],
  },
}))

vi.mock('@/utils/parseIndexRef', () => ({
  parseIndexRef: (val: string) => ({ ns: 'wp', target: val, layer: 3 }),
}))

vi.mock('@/composables/useWpNavigationHistory', () => ({
  useWpNavigationHistory: () => ({ push: vi.fn() }),
}))

const globalStubs = {
  'el-progress': { template: '<div />', props: ['percentage'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
  'el-radio-group': { template: '<div><slot /></div>', props: ['modelValue'] },
  'el-radio-button': { template: '<label><slot /></label>', props: ['label'] },
  'el-button': { template: '<button><slot /></button>', props: ['type', 'size', 'disabled'] },
  'el-table': {
    template: `<div class="el-table"><slot /></div>`,
    props: ['data', 'border', 'rowKey', 'emptyText', 'expandRowKeys'],
  },
  'el-table-column': {
    template: `<div class="el-table-column"><template v-for="(row, idx) in ($parent.$props?.data || [])" :key="idx"><slot :row="row" /></template></div>`,
    props: ['label', 'prop', 'width', 'minWidth', 'align', 'type', 'showOverflowTooltip', 'resizable'],
  },
  'el-dropdown': { template: '<div><slot /></div>', props: ['trigger'] },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>', props: ['command'] },
  'el-tooltip': { template: '<span><slot /></span>', props: ['content', 'disabled', 'placement'] },
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>', props: ['modelValue', 'title', 'width'] },
  'el-form': { template: '<div><slot /></div>', props: ['model', 'rules'] },
  'el-form-item': { template: '<div><slot /></div>', props: ['label', 'prop'] },
  'el-input': { template: '<input />', props: ['modelValue', 'type', 'placeholder'] },
  'el-select': { template: '<div><slot /></div>', props: ['modelValue'] },
  'el-option': { template: '<div />', props: ['label', 'value'] },
  'el-badge': { template: '<span><slot /></span>', props: ['value', 'hidden'] },
  'el-icon': { template: '<span />' },
  'el-timeline': { template: '<div><slot /></div>' },
  'el-timeline-item': { template: '<div><slot /></div>' },
  'el-tour': { template: '<div />', props: ['modelValue'] },
  'el-tour-step': { template: '<div />' },
  'ArrowDown': { template: '<span />' },
}

// A16 程序行数据（模拟 seq2）
const a16Programs = [
  {
    id: 'a16-seq1',
    program_no: 1,
    program_desc: '确定声明书版本',
    program_category: '',
    linked_workpapers: '',
    status: 'completed',
  },
  {
    id: 'a16-seq2',
    program_no: 2,
    program_desc: '编制管理层声明书（主版本）',
    program_category: '',
    linked_workpapers: 'A16-1,A16-2,A16-3,A16-4,A16-5,A16-6',
    status: 'pending',
  },
  {
    id: 'a16-seq3',
    program_no: 3,
    program_desc: '编制关联交易声明书（如适用）',
    program_category: '',
    linked_workpapers: 'A16-7',
    status: 'pending',
  },
]

function createWrapper(sheetName = '管理层声明书程序表A16') {
  return mount(GtAProgramConsole, {
    props: {
      wpId: 'wp-a16',
      sheetName,
      schema: {},
      htmlData: {
        programs: a16Programs,
        trim_decisions: [],
      },
    },
    global: {
      stubs: globalStubs,
    },
  })
}

describe('GtAProgramConsole — A16 seq2 推荐版本折叠', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认 API 返回推荐版本 A16-3
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({
          main: { code: 'A16-3', label: 'IPO申报', reason: 'business_category=A2', confidence: 'high' },
          supplement: null,
        })
      }
      // checklist-responses
      return Promise.resolve([])
    })
  })

  it('渲染推荐版本 chip 带「推荐」badge', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    // 推荐 badge 存在
    expect(html).toContain('推荐')
    // 推荐版本 chip（A16-3）存在
    expect(html).toContain('A16-3')
  })

  it('显示「其他版本 ▼」toggle 按钮', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('其他版本 ▼')
  })

  it('默认不展示非推荐版本 chip', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const chips = wrapper.findAll('.gt-index-chip-mock')
    // 只有推荐版本 A16-3 + seq3 的 A16-7 = 2 chip 可见
    // （seq1 无 ref_index）
    const a16MainChips = chips.filter(c => {
      const val = c.attributes('data-value') || c.text()
      return /^A16-[1-6]$/.test(val)
    })
    expect(a16MainChips.length).toBe(1) // 仅推荐版本 A16-3
  })

  it('点击「其他版本 ▼」展开全部非推荐版本', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    // 点击 toggle
    const toggle = wrapper.find('.gt-a-program-console__other-versions-toggle')
    expect(toggle.exists()).toBe(true)
    await toggle.trigger('click')
    await nextTick()

    const chips = wrapper.findAll('.gt-index-chip-mock')
    const a16MainChips = chips.filter(c => {
      const val = c.attributes('data-value') || c.text()
      return /^A16-[1-6]$/.test(val)
    })
    // 展开后：推荐 A16-3 + 其余 5 个 = 6 chip 全部可见
    expect(a16MainChips.length).toBe(6)
  })

  it('展开后 toggle 文字变为「收起 ▲」', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const toggle = wrapper.find('.gt-a-program-console__other-versions-toggle')
    await toggle.trigger('click')
    await nextTick()

    expect(toggle.text()).toContain('收起 ▲')
  })

  it('非 A16 程序表不触发推荐版本逻辑', async () => {
    // 使用 D2A sheetName
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-d2a',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: {
          programs: [
            {
              id: 'd2a-1',
              program_no: 1,
              program_desc: '检查应收账款',
              program_category: '',
              linked_workpapers: 'D2-1,D2-2,D2-3',
              status: 'pending',
            },
          ],
          trim_decisions: [],
        },
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    // 不应有推荐 badge（检查 class 而非文本，避免匹配 HTML 注释）
    expect(wrapper.find('.gt-a-program-console__recommend-badge').exists()).toBe(false)
    // 不应有其他版本 toggle
    expect(wrapper.find('.gt-a-program-console__other-versions-toggle').exists()).toBe(false)
  })

  it('API 失败时降级正常渲染全部 chip（无推荐标记）', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.reject(new Error('network error'))
      }
      return Promise.resolve([])
    })

    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    // 无推荐 badge（API 失败，a16RecommendedCode 为空）
    // 应该走非 A16 seq2 渲染路径（isA16Seq2Row 仍为 true 但 a16RecommendedCode 为空）
    // 此时不显示推荐 badge
    expect(html).not.toContain('gt-a-program-console__recommend-badge')
  })
})
