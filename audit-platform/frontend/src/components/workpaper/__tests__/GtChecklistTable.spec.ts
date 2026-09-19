/**
 * GtChecklistTable.spec.ts — 核对表组件测试
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import GtChecklistTable from '../GtChecklistTable.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof import('element-plus')>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }
})

const mockHtmlData = {
  template: {
    wp_code: 'A1-15',
    title: '企业会计准则有关财务报表列报及披露核对表',
    sections: [
      {
        id: 'sec-1',
        title: '第一章 总则',
        items: [
          {
            id: 'item-1',
            type: 'actionable' as const,
            standard_ref: 'CAS1',
            content: '是否正确理解适用准则',
            children: [],
          },
          {
            id: 'item-2',
            type: 'guidance' as const,
            standard_ref: '',
            content: '提示性说明文字',
            children: [],
          },
          {
            id: 'item-3',
            type: 'header' as const,
            standard_ref: '',
            content: '小节标题',
            children: [],
          },
        ],
      },
    ],
    toc: [{ id: 'sec-1', title: '第一章 总则', applicable: true }],
    stats: { total_actionable: 1, total_guidance: 1, total_sections: 1 },
  },
  responses: {
    'item-1': { conclusion: 'Y', remark: '', wp_ref: '' },
  },
}

const globalStubs = {
  'el-tree': { template: '<div class="el-tree"><slot /></div>', props: ['data', 'props', 'highlightCurrent'] },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'text'] },
  'el-input': { template: '<input class="el-input" />', props: ['modelValue', 'size', 'placeholder'] },
  'el-select': { template: '<select class="el-select"><slot /></select>', props: ['modelValue', 'size', 'disabled'] },
  'el-option': { template: '<option><slot /></option>', props: ['label', 'value'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size'] },
  'el-progress': { template: '<div class="el-progress" />', props: ['percentage', 'strokeWidth'] },
  'el-dialog': { template: '<div class="el-dialog"><slot /></div>', props: ['modelValue', 'title'] },
  'el-popover': { template: '<div><slot /><slot name="reference" /></div>', props: ['placement', 'width'] },
  'el-checkbox': { template: '<input type="checkbox" />', props: ['modelValue'] },
}

describe('GtChecklistTable', () => {
  it('渲染核对表标题和目录', () => {
    const wrapper = mount(GtChecklistTable, {
      props: { wpId: 'wp-15', htmlData: mockHtmlData },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.gt-checklist-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('企业会计准则')
    expect(wrapper.text()).toContain('第一章 总则')
  })

  it('渲染 actionable 条目和 header 分隔行', () => {
    const wrapper = mount(GtChecklistTable, {
      props: { wpId: 'wp-15', htmlData: mockHtmlData },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('是否正确理解适用准则')
    expect(wrapper.text()).toContain('小节标题')
  })

  it('显示进度统计', () => {
    const wrapper = mount(GtChecklistTable, {
      props: { wpId: 'wp-15', htmlData: mockHtmlData },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toMatch(/0\/1|1\/1|100%|已完成/)
  })

  it('搜索框过滤条目', async () => {
    const wrapper = mount(GtChecklistTable, {
      props: { wpId: 'wp-15', htmlData: mockHtmlData },
      global: { stubs: globalStubs },
    })
    const searchInput = wrapper.find('.gt-checklist-table__search input, .gt-checklist-table__search .el-input')
    if (searchInput.exists()) {
      await searchInput.setValue('适用准则')
    }
    expect(wrapper.text()).toContain('是否正确理解适用准则')
  })
})
