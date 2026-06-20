/**
 * GtAProgramConsoleA17Seq5.spec.ts — A17 seq5 核对表选版 UI
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import GtAProgramConsole from '../GtAProgramConsole.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

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
  default: { name: 'WpInlinePopup', template: '<div />' },
}))

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock" :data-value="value" :data-disabled="String(disabled)">{{ value }}</span>',
    props: ['value', 'validate', 'preventNavigate', 'disabled'],
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
  'el-tag': { template: '<span><slot /></span>', props: ['type', 'size'] },
  'el-radio-group': { template: '<div><slot /></div>', props: ['modelValue'] },
  'el-radio-button': { template: '<label><slot /></label>', props: ['label'] },
  'el-button': { template: '<button><slot /></button>', props: ['type', 'size', 'disabled'] },
  'el-table': {
    template: '<div class="el-table"><slot /></div>',
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
  'el-dialog': { template: '<div><slot /></div>', props: ['modelValue', 'title', 'width'] },
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
  ArrowDown: { template: '<span />' },
}

const a17Seq5Programs = [
  {
    id: 'a17-seq5',
    program_no: 5,
    program_desc: '编制审计工作完成核对表',
    program_category: '',
    linked_workpapers: 'A17-5-1,A17-5-2,A17-5-3,A17-5-4,A17-5-5',
    status: 'pending',
  },
]

function mountA17() {
  return mount(GtAProgramConsole, {
    props: {
      wpId: 'wp-a17',
      sheetName: '重大事项概要程序表A17',
      schema: {},
      htmlData: { programs: a17Seq5Programs, trim_decisions: [] },
    },
    global: { stubs: globalStubs },
  })
}

describe('GtAProgramConsole — A17 seq5 核对表选版', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a17/applicable-versions')) {
        return Promise.resolve([
          { wp_code: 'A17-5-1', applicable: true, mandatory: true },
          { wp_code: 'A17-5-2', applicable: false, mandatory: true },
          { wp_code: 'A17-5-3', applicable: false, mandatory: true },
          { wp_code: 'A17-5-4', applicable: false, mandatory: true },
          { wp_code: 'A17-5-5', applicable: true, mandatory: false },
        ])
      }
      return Promise.resolve([])
    })
  })

  it('仅展示适用核对表 chip（A17-5-1 + A17-5-5）', async () => {
    const wrapper = mountA17()
    await flushPromises()
    await nextTick()

    const chips = wrapper.findAll('.gt-index-chip-mock')
    const codes = chips.map(c => c.attributes('data-value'))
    expect(codes).toContain('A17-5-1')
    expect(codes).toContain('A17-5-5')
    expect(codes).not.toContain('A17-5-3')
  })

  it('必做/推荐 badge 正确显示', async () => {
    const wrapper = mountA17()
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('必做')
    expect(wrapper.text()).toContain('推荐')
  })

  it('不适用版本默认折叠，展开后灰显', async () => {
    const wrapper = mountA17()
    await flushPromises()
    await nextTick()

    const toggle = wrapper.find('.gt-a-program-console__other-versions-toggle')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('不适用版本 ▼')

    await toggle.trigger('click')
    await nextTick()

    const naChip = wrapper.find('.gt-index-chip-mock[data-value="A17-5-3"]')
    expect(naChip.exists()).toBe(true)
    expect(naChip.attributes('data-disabled')).toBe('true')
  })
})
