/**
 * GtAProgramConsole — chip disabled when program step not_applicable
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

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}) },
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
  'el-input': { template: '<input />', props: ['modelValue'] },
  'el-icon': { template: '<span />' },
  'el-dialog': { template: '<div><slot /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-timeline': { template: '<div><slot /></div>' },
  'el-timeline-item': { template: '<div><slot /></div>' },
  'el-divider': { template: '<hr />' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div />' },
  'el-badge': { template: '<span><slot /></span>' },
  'el-tour': { template: '<div />' },
  'el-tour-step': { template: '<div />' },
  ArrowDown: { template: '<span />' },
}

function mountConsole(status: string) {
  return mount(GtAProgramConsole, {
    props: {
      wpId: 'wp-1',
      sheetName: '审计程序A17',
      schema: {},
      htmlData: {
        programs: [{
          id: 'p1',
          program_no: 1,
          program_desc: '业务咨询',
          linked_workpapers: 'A17-3',
          status,
          trim_reason: status === 'not_applicable' ? 'B类不适用' : undefined,
        }],
        trim_decisions: [],
      },
    },
    global: { stubs: globalStubs },
  })
}

describe('GtAProgramConsole chip disabled', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('disables ref chips when row status is not_applicable', async () => {
    const wrapper = mountConsole('not_applicable')
    await flushPromises()
    await nextTick()
    const chip = wrapper.find('.gt-index-chip-mock[data-value="A17-3"]')
    expect(chip.attributes('data-disabled')).toBe('true')
  })

  it('keeps ref chips enabled when row is pending', async () => {
    const wrapper = mountConsole('pending')
    await flushPromises()
    await nextTick()
    const chip = wrapper.find('.gt-index-chip-mock[data-value="A17-3"]')
    expect(chip.attributes('data-disabled')).toBe('false')
  })
})
