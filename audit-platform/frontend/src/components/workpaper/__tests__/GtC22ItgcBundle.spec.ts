/**
 * GtC22ItgcBundle.spec.ts — C22 IT 一般控制测试聚合组件主入口（Task 4.1）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 4.1
 * Validates: Requirements 1.1, 3.1, 3.2, 3.3, 3.4
 *
 * 覆盖：
 *  - htmlRendererRegistry 注册（componentType c22-itgc-bundle）
 *  - matrix 总览面板默认渲染（Req 3.1）
 *  - 控制点行呈现 9 列 + 状态（Req 3.2）：类别/风险/控制编号/描述/应用系统/
 *    设计结论/执行结论/是否异常/缺陷编号
 *  - 完成进度 + 缺陷统计仪表盘（Req 3.4）
 *  - 点击控制点行 → 切换到对应子页 Tab（Req 3.3）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

// getWpIndex（composable loadWpIndex 用）
vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(async () => [
    { wp_code: 'C21', wp_id: 'wp-c21', id: 'idx-c21' },
    { wp_code: 'C21-1', wp_id: 'wp-c21-1', id: 'idx-c21-1' },
  ]),
}))

// vue-router（组件 useRoute）
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-1' }, query: {} }),
}))

// 子表 stub（避免异步加载 + 网络）
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  __esModule: true,
  default: { name: 'GtOnlyOfficeSheet', template: '<div class="onlyoffice-stub" />' },
}))

// IT 控制域子页 stub（Task 4.2；避免异步加载真实组件）
vi.mock('../GtC22ControlSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtC22ControlSheet',
    props: ['wpId', 'projectId', 'tab', 'matrixRow', 'readonly'],
    template: '<div class="c22-control-sheet-stub" :data-control="tab?.id" />',
  },
}))

import GtC22ItgcBundle from '../GtC22ItgcBundle.vue'
import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
} from '../htmlRendererRegistry'
import { itgcItemId } from '../composables/useC22BundleState'

const stubs = {
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label'],
    template: '<div class="el-tab-pane-stub" :data-name="name"><slot name="label" /><slot /></div>',
  },
  'el-progress': true,
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
}

/**
 * render-config selfLoad 返回：主矩阵 sheet 带 is_matrix + matrix 行；
 * checklist-responses 返回给定 responses。
 */
function mountBundle(responses: any[] = [], matrix: any[] = [], readonly = false) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/render-config')) {
      return Promise.resolve({
        sheets: [
          { sheet_name: 'C22 IT一般控制测试', componentType: 'c22-itgc-bundle', html_data: { is_matrix: true, matrix } },
        ],
      })
    }
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(responses)
    }
    return Promise.resolve({})
  })
  return mount(GtC22ItgcBundle, {
    props: { wpId: 'wp-c22', projectId: 'proj-1', readonly },
    global: {
      stubs,
      directives: { 'tab-wheel': {}, loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('GtC22ItgcBundle — 注册契约（Req 1.1）', () => {
  it('c22-itgc-bundle 已注册于 htmlRendererRegistry（defineAsyncComponent + contextProps standard）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('c22-itgc-bundle')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('c22-itgc-bundle')
    expect(entry?.component).toBeDefined()
    expect(entry?.contextProps).toBe('standard')
    expect(isHtmlComponentType('c22-itgc-bundle')).toBe(true)
  })
})

describe('GtC22ItgcBundle — matrix 总览面板（Req 3.1/3.2/3.4）', () => {
  it('默认展示 matrix 面板（active = matrix）', async () => {
    const wrapper = mountBundle()
    await flushPromises()
    expect((wrapper.vm as any).active).toBe('matrix')
    expect(wrapper.find('.c22-matrix-table').exists()).toBe(true)
  })

  it('每个控制点渲染一行，合并矩阵静态列 + responses 动态结论（9 列）', async () => {
    const matrix = [
      { row: 10, category: '信息安全', risk: 'ITR001 未授权访问', controlNo: 'SA-3', description: '账号权限管理', appSystem: 'A系统', indexNo: 'B22A-4-3' },
    ]
    const responses = [
      { item_id: itgcItemId('SA-3', 'design-conclusion'), conclusion: '有效', remark: '' },
      { item_id: itgcItemId('SA-3', 'exec-conclusion'), conclusion: '有效', remark: '' },
      { item_id: itgcItemId('SA-3', 'abnormal'), conclusion: '否', remark: '' },
    ]
    const wrapper = mountBundle(responses, matrix)
    await flushPromises()

    const rows = wrapper.findAll('.c22-matrix-row')
    // 31 个真正控制点
    expect(rows.length).toBe(31)

    // SA-3 行合并了矩阵静态内容与结论
    const displayRows = (wrapper.vm as any).matrixDisplayRows as any[]
    const sa3 = displayRows.find((r) => r.tab.id === 'SA-3')
    expect(sa3.category).toBe('信息安全')
    expect(sa3.riskNo).toBe('ITR001')
    expect(sa3.controlNo).toBe('SA-3')
    expect(sa3.description).toBe('账号权限管理')
    expect(sa3.appSystem).toBe('A系统')
    expect(sa3.designConclusion).toBe('有效')
    expect(sa3.execConclusion).toBe('有效')
    expect(sa3.abnormal).toBe('否')
    expect(sa3.status).toBe('completed')
  })

  it('仪表盘统计 completed/inProgress/notStarted + 缺陷总数（Req 3.4）', async () => {
    const responses = [
      // SA-3 completed
      { item_id: itgcItemId('SA-3', 'design-conclusion'), conclusion: '有效', remark: '' },
      { item_id: itgcItemId('SA-3', 'exec-conclusion'), conclusion: '有效', remark: '' },
      // SA-5 in_progress（仅设计结论）+ 异常缺陷
      { item_id: itgcItemId('SA-5', 'design-conclusion'), conclusion: '无效', remark: '' },
      { item_id: itgcItemId('SA-5', 'abnormal'), conclusion: '是', remark: '' },
      { item_id: itgcItemId('SA-5', 'defect-no'), conclusion: '', remark: 'ITGC#1' },
      { item_id: itgcItemId('SA-5', 'defect-desc'), conclusion: '', remark: '权限未复核' },
    ]
    const wrapper = mountBundle(responses)
    await flushPromises()
    const summary = (wrapper.vm as any).progressSummary
    expect(summary.completed).toBe(1)
    expect(summary.inProgress).toBe(1)
    expect(summary.notStarted).toBe(29) // 31 - 1 - 1
    expect(summary.defectCount).toBe(1)
  })
})

describe('GtC22ItgcBundle — 点击矩阵行跳转子页（Req 3.3）', () => {
  it('点击控制点行 → active 切换到该子页 Tab', async () => {
    const wrapper = mountBundle()
    await flushPromises()
    expect((wrapper.vm as any).active).toBe('matrix')

    // 直接调用行点击处理（tab = SA-7）
    const tab = (wrapper.vm as any).controlPointTabs.find((t: any) => t.id === 'SA-7')
    ;(wrapper.vm as any).onMatrixRowClick(tab)
    await flushPromises()
    expect((wrapper.vm as any).active).toBe('SA-7')
  })

  it('点击 UI 上的第一行也切换 active', async () => {
    const wrapper = mountBundle()
    await flushPromises()
    const firstRow = wrapper.find('.c22-matrix-row')
    await firstRow.trigger('click')
    // 第一个控制点为 SA-3
    expect((wrapper.vm as any).active).toBe('SA-3')
  })
})
