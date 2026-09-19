/**
 * GtC22ItgcBundle.integration.spec.ts — 集成测试（Task 7.1）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 7.1
 * Validates: Requirements 3.1, 4.1, 5.2
 *
 * 挂载 mock render-config + wp_index，验证：
 *  1. matrix 面板渲染 ITGC 控制矩阵（4 分组 SA/PE/PM/NS 均有行）
 *  2. 点击矩阵行导航到正确子页 Tab（activeSection 同步切换）
 *  3. 4 大类分组子页页签结构正确（SA=10, PE=8 含 2 aux, PM=6, NS=9）
 *  4. 缺陷联动：子页「是否异常=是」→ C21-1 汇总视图中出现对应缺陷
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock API ───
const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args), put: vi.fn(async () => ({})) },
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(async () => [
    { wp_code: 'C21', wp_id: 'wp-c21-id', id: 'idx-c21' },
    { wp_code: 'C21-1', wp_id: 'wp-c21-1-id', id: 'idx-c21-1' },
  ]),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-integration' }, query: {} }),
}))

// ─── Stubs for child components ───
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtOnlyOfficeSheet',
    props: ['wpId', 'projectId', 'sheetName', 'readonly'],
    template: '<div class="onlyoffice-stub" :data-sheet="sheetName" :data-readonly="String(readonly)" />',
  },
}))

vi.mock('../GtC22ControlSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtC22ControlSheet',
    props: ['wpId', 'projectId', 'tab', 'matrixRow', 'readonly'],
    template: '<div class="c22-control-sheet-stub" :data-control="tab?.id" :data-group="tab?.group" />',
  },
}))

vi.mock('../GtC21FindingsSummary.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtC21FindingsSummary',
    props: ['wpId', 'projectId', 'defects', 'readonly'],
    template: `<div class="c21-findings-stub">
      <div v-for="d in defects" :key="d.controlId" class="c21f-defect-item" :data-control="d.controlId" :data-no="d.defectNo">
        {{ d.description }}
      </div>
      <div v-if="!defects || defects.length === 0" class="c21f-empty">暂无 IT 审计发现</div>
    </div>`,
  },
}))

import GtC22ItgcBundle from '../GtC22ItgcBundle.vue'
import { itgcItemId, C22_BUNDLE_TABS } from '../composables/useC22BundleState'

const elStubs = {
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label'],
    template: '<div class="el-tab-pane-stub" :data-name="name" :data-label="label"><slot name="label" /><slot /></div>',
  },
  'el-progress': true,
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
}

// ─── 模拟 C22 render-config（34 sheets：1 主矩阵 + 33 子页） ───
function buildMockRenderConfig() {
  // 主矩阵 sheet 带 is_matrix + matrix 行（覆盖 4 大类各至少 1 行）
  const matrixRows = [
    { row: 10, category: '信息安全', risk: 'ITR001 未授权访问风险', controlNo: 'SA-3', description: '账号及权限管理（操作系统层面）', appSystem: 'ERP系统', indexNo: 'B22A-4-3' },
    { row: 11, category: '信息安全', risk: 'ITR002 密码策略不满足', controlNo: 'SA-4c', description: '密码策略执行', appSystem: 'ERP系统', indexNo: 'B22A-4-4c' },
    { row: 20, category: '运行维护', risk: 'ITR010 备份缺失', controlNo: 'PE-3a', description: '数据备份与恢复', appSystem: '基础设施', indexNo: 'B22A-4-20' },
    { row: 31, category: '程序变更', risk: 'ITR020 变更未审批', controlNo: 'PM-3', description: '程序变更管理', appSystem: '开发平台', indexNo: 'B22A-4-31' },
    { row: 37, category: '新系统', risk: 'ITR030 新系统上线风险', controlNo: 'NS-1', description: '新系统开发方法论', appSystem: '新系统', indexNo: 'B22A-4-37' },
  ]
  return {
    sheets: [
      {
        sheet_name: 'C22 IT一般控制测试',
        componentType: 'c22-itgc-bundle',
        html_data: { is_matrix: true, matrix: matrixRows },
      },
    ],
  }
}

/**
 * 构造模拟 checklist-responses（控制点的设计/执行结论 + 缺陷字段）。
 * 用于验证 completionMap 推导 + 缺陷联动。
 */
function buildMockResponses() {
  return [
    // SA-3 completed（设计有效+执行有效，无异常）
    { item_id: itgcItemId('SA-3', 'design-conclusion'), conclusion: '有效', remark: null },
    { item_id: itgcItemId('SA-3', 'exec-conclusion'), conclusion: '有效', remark: null },
    { item_id: itgcItemId('SA-3', 'abnormal'), conclusion: '否', remark: null },
    // SA-7 in_progress（仅设计，异常=是，有缺陷）
    { item_id: itgcItemId('SA-7', 'design-conclusion'), conclusion: '无效', remark: null },
    { item_id: itgcItemId('SA-7', 'abnormal'), conclusion: '是', remark: null },
    { item_id: itgcItemId('SA-7', 'defect-no'), conclusion: null, remark: 'ITGC#1' },
    { item_id: itgcItemId('SA-7', 'defect-desc'), conclusion: null, remark: '未按期复核用户权限' },
    // PE-3a completed + 异常=是
    { item_id: itgcItemId('PE-3a', 'design-conclusion'), conclusion: '有效', remark: null },
    { item_id: itgcItemId('PE-3a', 'exec-conclusion'), conclusion: '部分有效', remark: null },
    { item_id: itgcItemId('PE-3a', 'abnormal'), conclusion: '是', remark: null },
    { item_id: itgcItemId('PE-3a', 'defect-no'), conclusion: null, remark: 'ITGC#2' },
    { item_id: itgcItemId('PE-3a', 'defect-desc'), conclusion: null, remark: '备份策略执行不完整' },
    // PM-3 not_started（无任何结论）
    // NS-1 in_progress（仅执行结论）
    { item_id: itgcItemId('NS-1', 'exec-conclusion'), conclusion: '有效', remark: null },
    { item_id: itgcItemId('NS-1', 'abnormal'), conclusion: '否', remark: null },
  ]
}

function mountIntegration() {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/render-config')) {
      return Promise.resolve(buildMockRenderConfig())
    }
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(buildMockResponses())
    }
    return Promise.resolve({})
  })
  return mount(GtC22ItgcBundle, {
    props: { wpId: 'wp-c22-integ', projectId: 'proj-integration' },
    global: {
      stubs: elStubs,
      directives: { 'tab-wheel': {}, loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
})

// ═══════════════════════════════════════════════════════════════════
// 1. matrix 面板渲染 ITGC 控制矩阵（4 分组都有行）— Req 3.1
// ═══════════════════════════════════════════════════════════════════
describe('集成：matrix 面板渲染（Req 3.1）', () => {
  it('默认展示 matrix 面板，渲染 31 个控制点行', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('matrix')
    expect(wrapper.find('.c22-matrix-table').exists()).toBe(true)
    expect(wrapper.findAll('.c22-matrix-row').length).toBe(31)
  })

  it('matrix 行包含 4 大类控制点（SA/PE/PM/NS 均有行数据）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const rows = vm.matrixDisplayRows as any[]
    const categories = new Set(rows.map((r: any) => r.category))
    // 4 大类分组在矩阵中均有行
    expect(categories.has('信息安全')).toBe(true)
    expect(categories.has('运行维护')).toBe(true)
    expect(categories.has('程序变更')).toBe(true)
    expect(categories.has('新系统')).toBe(true)
  })

  it('matrix 合并静态矩阵列 + responses 动态结论（SA-3 行验证）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const sa3 = (vm.matrixDisplayRows as any[]).find((r: any) => r.tab.id === 'SA-3')
    expect(sa3).toBeDefined()
    expect(sa3.category).toBe('信息安全')
    expect(sa3.riskNo).toBe('ITR001')
    expect(sa3.description).toBe('账号及权限管理（操作系统层面）')
    expect(sa3.appSystem).toBe('ERP系统')
    expect(sa3.designConclusion).toBe('有效')
    expect(sa3.execConclusion).toBe('有效')
    expect(sa3.abnormal).toBe('否')
    expect(sa3.status).toBe('completed')
  })

  it('仪表盘统计与 responses 一致（completed=2, inProgress=2, defects=2）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const summary = (wrapper.vm as any).progressSummary
    // SA-3 completed, PE-3a completed, SA-7 in_progress, NS-1 in_progress
    expect(summary.completed).toBe(2)
    expect(summary.inProgress).toBe(2)
    expect(summary.notStarted).toBe(27) // 31 - 2 - 2
    expect(summary.defectCount).toBe(2) // SA-7 + PE-3a
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. 点击矩阵行 → 导航到正确子页 Tab（Req 3.1 → 4.1 联动）
// ═══════════════════════════════════════════════════════════════════
describe('集成：矩阵行点击导航（Req 3.1 / 4.1）', () => {
  it('点击 SA-3 行 → active=SA-3, activeSection=信息安全', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any

    // 找到 SA-3 行点击
    const rows = wrapper.findAll('.c22-matrix-row')
    // SA-3 是第一个控制点
    await rows[0].trigger('click')
    expect(vm.active).toBe('SA-3')
    expect(vm.activeSection).toBe('信息安全')
  })

  it('点击 PE-3a 行 → active=PE-3a, activeSection=运行维护', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any

    // PE-3a 是 SA(10) 之后的第 11 个控制点（0-indexed: 10）
    const tabs = vm.controlPointTabs as any[]
    const peIdx = tabs.findIndex((t: any) => t.id === 'PE-3a')
    const rows = wrapper.findAll('.c22-matrix-row')
    await rows[peIdx].trigger('click')
    expect(vm.active).toBe('PE-3a')
    expect(vm.activeSection).toBe('运行维护')
  })

  it('点击 PM-3 行 → active=PM-3, activeSection=程序变更', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any

    const tabs = vm.controlPointTabs as any[]
    const pmIdx = tabs.findIndex((t: any) => t.id === 'PM-3')
    const rows = wrapper.findAll('.c22-matrix-row')
    await rows[pmIdx].trigger('click')
    expect(vm.active).toBe('PM-3')
    expect(vm.activeSection).toBe('程序变更')
  })

  it('点击 NS-1 行 → active=NS-1, activeSection=新系统', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any

    const tabs = vm.controlPointTabs as any[]
    const nsIdx = tabs.findIndex((t: any) => t.id === 'NS-1')
    const rows = wrapper.findAll('.c22-matrix-row')
    await rows[nsIdx].trigger('click')
    expect(vm.active).toBe('NS-1')
    expect(vm.activeSection).toBe('新系统')
  })

  it('导航到子页后渲染 GtC22ControlSheet stub（data-control 匹配）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.active = 'SA-7'
    await flushPromises()
    const sub = wrapper.find('.c22-control-sheet-stub')
    expect(sub.exists()).toBe(true)
    expect(sub.attributes('data-control')).toBe('SA-7')
    expect(sub.attributes('data-group')).toBe('信息安全')
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. 分组子页结构验证（Req 4.1）
// ═══════════════════════════════════════════════════════════════════
describe('集成：分组子页结构（Req 4.1）', () => {
  it('顶层 section 包含 matrix + 4 大类 + C21 + C21-1', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const sections = vm.topSections.map((s: any) => s.key)
    expect(sections).toContain('matrix')
    expect(sections).toContain('信息安全')
    expect(sections).toContain('运行维护')
    expect(sections).toContain('程序变更')
    expect(sections).toContain('新系统')
    expect(sections).toContain('C21')
    expect(sections).toContain('C21-1')
  })

  it('信息安全 SA 组有 10 个子页 Tab', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    // 切到信息安全
    vm.activeSection = '信息安全'
    await flushPromises()
    const subs = vm.currentGroupTabs as any[]
    expect(subs.length).toBe(10)
    const ids = subs.map((t: any) => t.id)
    expect(ids).toContain('SA-3')
    expect(ids).toContain('SA-14')
  })

  it('运行维护 PE 组有 8 个子页（6 控制点 + 2 aux 续页）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.activeSection = '运行维护'
    await flushPromises()
    const subs = vm.currentGroupTabs as any[]
    expect(subs.length).toBe(8)
    // aux 续页也在列表中
    const ids = subs.map((t: any) => t.id)
    expect(ids).toContain('PE-5.1') // aux
    expect(ids).toContain('PE-8.1') // aux
    expect(ids).toContain('PE-3a')
  })

  it('程序变更 PM 组有 6 个子页', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.activeSection = '程序变更'
    await flushPromises()
    const subs = vm.currentGroupTabs as any[]
    expect(subs.length).toBe(6)
    const ids = subs.map((t: any) => t.id)
    expect(ids).toContain('PM-3')
    expect(ids).toContain('PM-6')
  })

  it('新系统 NS 组有 9 个子页', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.activeSection = '新系统'
    await flushPromises()
    const subs = vm.currentGroupTabs as any[]
    expect(subs.length).toBe(9)
    const ids = subs.map((t: any) => t.id)
    expect(ids).toContain('NS-1')
    expect(ids).toContain('NS-6.2')
  })

  it('各分组子页均归属正确 group（无交叉）', async () => {
    // 验证 C22_BUNDLE_TABS 单一来源
    const saSheets = C22_BUNDLE_TABS.filter(t => t.group === '信息安全')
    const peSheets = C22_BUNDLE_TABS.filter(t => t.group === '运行维护')
    const pmSheets = C22_BUNDLE_TABS.filter(t => t.group === '程序变更')
    const nsSheets = C22_BUNDLE_TABS.filter(t => t.group === '新系统')

    expect(saSheets.length).toBe(10)
    expect(peSheets.length).toBe(8)
    expect(pmSheets.length).toBe(6)
    expect(nsSheets.length).toBe(9)

    // 所有子页 id 唯一
    const allIds = [...saSheets, ...peSheets, ...pmSheets, ...nsSheets].map(t => t.id)
    expect(new Set(allIds).size).toBe(allIds.length)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 4. 缺陷联动：子页异常→C21-1 汇总（Req 5.2）
// ═══════════════════════════════════════════════════════════════════
describe('集成：缺陷联动 C21-1 汇总（Req 5.2）', () => {
  it('defects 正确收集「是否异常=是」的子页缺陷', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const defects = vm.defects as any[]
    expect(defects.length).toBe(2)

    const d1 = defects.find((d: any) => d.controlId === 'SA-7')
    expect(d1).toBeDefined()
    expect(d1.defectNo).toBe('ITGC#1')
    expect(d1.description).toBe('未按期复核用户权限')
    expect(d1.group).toBe('信息安全')

    const d2 = defects.find((d: any) => d.controlId === 'PE-3a')
    expect(d2).toBeDefined()
    expect(d2.defectNo).toBe('ITGC#2')
    expect(d2.description).toBe('备份策略执行不完整')
    expect(d2.group).toBe('运行维护')
  })

  it('C21-1 汇总视图接收 defects 并渲染缺陷条目', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    // 切到 C21-1
    vm.active = 'C21-1'
    await flushPromises()

    const findings = wrapper.find('.c21-findings-stub')
    expect(findings.exists()).toBe(true)

    // 2 个缺陷条目渲染
    const items = findings.findAll('.c21f-defect-item')
    expect(items.length).toBe(2)

    // 验证第一个缺陷条目内容
    const sa7Item = items.find(item => item.attributes('data-control') === 'SA-7')
    expect(sa7Item).toBeDefined()
    expect(sa7Item!.attributes('data-no')).toBe('ITGC#1')
    expect(sa7Item!.text()).toContain('未按期复核用户权限')
  })

  it('无缺陷时 C21-1 显示「暂无 IT 审计发现」', async () => {
    // 使用空 responses（无异常）
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/render-config')) {
        return Promise.resolve(buildMockRenderConfig())
      }
      if (typeof url === 'string' && url.includes('/checklist-responses')) {
        return Promise.resolve([]) // 无 responses → 无缺陷
      }
      return Promise.resolve({})
    })
    const wrapper = mount(GtC22ItgcBundle, {
      props: { wpId: 'wp-c22-empty', projectId: 'proj-integration' },
      global: {
        stubs: elStubs,
        directives: { 'tab-wheel': {}, loading: {} },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.defects.length).toBe(0)
    expect(vm.progressSummary.defectCount).toBe(0)

    // 切到 C21-1
    vm.active = 'C21-1'
    await flushPromises()
    const empty = wrapper.find('.c21f-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无 IT 审计发现')
  })

  it('不为异常=否的控制点收集缺陷（SA-3 无异常不出现在 defects）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const defects = vm.defects as any[]
    const sa3 = defects.find((d: any) => d.controlId === 'SA-3')
    expect(sa3).toBeUndefined()
  })
})

// ═══════════════════════════════════════════════════════════════════
// 5. wpIdMap 正确解析 C21/C21-1 → wp_id
// ═══════════════════════════════════════════════════════════════════
describe('集成：wpIdMap 解析（wp_index 联动）', () => {
  it('wpIdMap 包含 C21 和 C21-1 的 wp_id', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.wpIdMap['C21']).toBe('wp-c21-id')
    expect(vm.wpIdMap['C21-1']).toBe('wp-c21-1-id')
  })

  it('visibleTabs 包含 C21 和 C21-1（wpIdMap 有值）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    const visible = vm.visibleTabs as any[]
    expect(visible.some((t: any) => t.id === 'C21')).toBe(true)
    expect(visible.some((t: any) => t.id === 'C21-1')).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 6. C21 IT 专业成员 Tab（Req 8.1, 8.2, 8.3 — Task 5.2）
// ═══════════════════════════════════════════════════════════════════
describe('集成：C21 IT专业成员评估 Tab（Req 8.1/8.2/8.3）', () => {
  it('Req 8.1：切换到 C21 Tab 时渲染 GtOnlyOfficeSheet（IT 专业成员评估表）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    // 激活 C21 Tab
    vm.active = 'C21'
    await flushPromises()
    expect(vm.activeSection).toBe('C21')
    // GtOnlyOfficeSheet 渲染（stub）
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
  })

  it('Req 8.1：C21 渲染使用独立 wp_id（非父 C22 wpId）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.active = 'C21'
    await flushPromises()
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
    // GtOnlyOfficeSheet 收到的 wp-id 应为 C21 的独立 wp_id（wp-c21-id），而非父 C22
    // 通过 subWpId 函数验证
    const c21Tab = vm.visibleTabs.find((t: any) => t.id === 'C21')
    expect(c21Tab).toBeDefined()
    expect(vm.subWpId(c21Tab)).toBe('wp-c21-id')
  })

  it('Req 8.2：C21 sheetName 传递 wpCode（保留源模板命名区域数据验证下拉选项）', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.active = 'C21'
    await flushPromises()
    // GtOnlyOfficeSheet 收到 sheetName='C21'（对应源模板 sheet tab 名，
    // OnlyOffice 原生保留该 sheet 的命名区域数据验证/下拉选项）
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.attributes('data-sheet')).toBe('C21')
  })

  it('Req 8.3：C21 与其余 Tab 一致地透传 readonly', async () => {
    // 只读模式
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/render-config')) {
        return Promise.resolve(buildMockRenderConfig())
      }
      if (typeof url === 'string' && url.includes('/checklist-responses')) {
        return Promise.resolve(buildMockResponses())
      }
      return Promise.resolve({})
    })
    const wrapper = mount(GtC22ItgcBundle, {
      props: { wpId: 'wp-c22-integ', projectId: 'proj-integration', readonly: true },
      global: {
        stubs: elStubs,
        directives: { 'tab-wheel': {}, loading: {} },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    vm.active = 'C21'
    await flushPromises()
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
    expect(oo.attributes('data-readonly')).toBe('true')
  })

  it('Req 8.3：C21 编辑模式下 readonly=false 透传', async () => {
    const wrapper = mountIntegration()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.active = 'C21'
    await flushPromises()
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
    expect(oo.attributes('data-readonly')).toBe('false')
  })

  it('Req 8.1：sheetName=C21 路由可直接激活 C21 Tab', async () => {
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/render-config')) {
        return Promise.resolve(buildMockRenderConfig())
      }
      if (typeof url === 'string' && url.includes('/checklist-responses')) {
        return Promise.resolve(buildMockResponses())
      }
      return Promise.resolve({})
    })
    const wrapper = mount(GtC22ItgcBundle, {
      props: { wpId: 'wp-c22-integ', projectId: 'proj-integration', sheetName: 'C21' },
      global: {
        stubs: elStubs,
        directives: { 'tab-wheel': {}, loading: {} },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('C21')
    expect(vm.activeSection).toBe('C21')
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
  })

  it('C21 wp_id 不存在时不显示 C21 Tab（降级隐藏）', async () => {
    // 修改 mock 不返回 C21 的 wp_id
    const { getWpIndex } = await import('@/services/workpaperApi')
    ;(getWpIndex as any).mockImplementationOnce(async () => [
      // 仅返回 C21-1，不返回 C21
      { wp_code: 'C21-1', wp_id: 'wp-c21-1-id', id: 'idx-c21-1' },
    ])
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/render-config')) {
        return Promise.resolve(buildMockRenderConfig())
      }
      if (typeof url === 'string' && url.includes('/checklist-responses')) {
        return Promise.resolve([])
      }
      return Promise.resolve({})
    })
    const wrapper = mount(GtC22ItgcBundle, {
      props: { wpId: 'wp-c22-no-c21', projectId: 'proj-integration' },
      global: {
        stubs: elStubs,
        directives: { 'tab-wheel': {}, loading: {} },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    // C21 不在 visibleTabs 中
    const visible = vm.visibleTabs as any[]
    expect(visible.some((t: any) => t.id === 'C21')).toBe(false)
    // 但 C21-1 仍可见
    expect(visible.some((t: any) => t.id === 'C21-1')).toBe(true)
    // 顶层 section 不包含 C21
    const sections = vm.topSections.map((s: any) => s.key)
    expect(sections).not.toContain('C21')
  })
})
