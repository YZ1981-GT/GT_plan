/**
 * GtA1Dashboard.spec.ts — A1 项目总控仪表盘测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import GtA1Dashboard from '../GtA1Dashboard.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}) },
}))

vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({
  default: { name: 'GtAuditFlowGraph', template: '<div />' },
}))

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}))

const programs = [
  {
    id: 'p1',
    program_no: 1,
    program_desc: '了解被审计单位及其环境',
    program_category: '常规',
    status: 'completed',
    phase: 'planning',
    linked_workpapers: 'B10',
    summary: '已完成',
  },
  {
    id: 'p2',
    program_no: 12,
    program_desc: '完成分析性复核',
    program_category: '常规',
    status: 'pending',
    phase: 'completion',
    linked_workpapers: 'A1-13',
  },
  {
    id: 'p3',
    program_no: 17,
    program_desc: '签发审计报告',
    program_category: '常规',
    status: 'in_progress',
    phase: 'signoff',
    linked_workpapers: 'A1-11',
  },
]

const globalStubs = {
  'el-progress': { template: '<div class="el-progress"><slot /></div>', props: ['percentage', 'type', 'width', 'strokeWidth', 'color'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'text'] },
  'el-input': { template: '<input />', props: ['modelValue', 'size', 'placeholder'] },
  'el-icon': { template: '<span />' },
  'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div @click="$emit(\'click\')"><slot /></div>' },
  'el-autocomplete': {
    template: '<div class="el-autocomplete"><slot :item="{ value: \'B10\', label: \'了解被审计单位\' }" /></div>',
    props: ['modelValue', 'fetchSuggestions', 'placeholder', 'triggerOnFocus', 'clearable'],
  },
  'el-form': { template: '<div><slot /></div>' },
  'el-form-item': { template: '<div><slot /></div>', props: ['label'] },
  'el-select': { template: '<div><slot /></div>', props: ['modelValue'] },
  'el-option': { template: '<div />', props: ['label', 'value'] },
  'el-dialog': { template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title', 'width'] },
}

describe('GtA1Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染环形进度和阶段里程碑', () => {
    const wrapper = mount(GtA1Dashboard, {
      props: {
        wpId: 'wp-a1',
        sheetName: 'A1',
        schema: {},
        htmlData: { programs, trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.gt-a1-dashboard').exists()).toBe(true)
    expect(wrapper.find('.gt-a1-dashboard__milestones').exists()).toBe(true)
    expect(wrapper.text()).toContain('计划与风险评估')
    expect(wrapper.text()).toContain('完成阶段')
  })

  it('按阶段分组渲染程序卡片', () => {
    const wrapper = mount(GtA1Dashboard, {
      props: {
        wpId: 'wp-a1',
        sheetName: 'A1',
        schema: {},
        htmlData: { programs, trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })
    expect(wrapper.findAll('.program-card').length).toBe(3)
    expect(wrapper.text()).toContain('了解被审计单位及其环境')
    expect(wrapper.text()).toContain('完成分析性复核')
  })

  it('显示 auto_data_source 摘要', () => {
    const wrapper = mount(GtA1Dashboard, {
      props: {
        wpId: 'wp-a1',
        sheetName: 'A1',
        schema: {},
        htmlData: { programs, trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.program-card__summary').text()).toContain('已完成')
  })

  it('渲染关联底稿 chip', () => {
    const wrapper = mount(GtA1Dashboard, {
      props: {
        wpId: 'wp-a1',
        sheetName: 'A1',
        schema: {},
        htmlData: { programs, trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })
    expect(wrapper.findAll('.gt-index-chip-mock').length).toBeGreaterThan(0)
  })
})
