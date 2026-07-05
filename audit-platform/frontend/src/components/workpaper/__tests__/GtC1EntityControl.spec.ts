/**
 * GtC1EntityControl.spec.ts — C1 企业层面控制测试主入口（Task 4.2）
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 4.2
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3
 *
 * 覆盖：sheetName v-if 分发 / 过程记录字段集 / item_id 构造 /
 *      适用性裁剪进度排除 / C1-4-4 样本借贷勾稽（useC1SampleEngine 派生） /
 *      样本行增删 / 只读禁编辑。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

// 子组件 stub（避免异步加载 + 网络）
// __esModule: true 让 defineAsyncComponent 正确解包 default（否则 test-utils 读取
// 命名空间的 __isTeleport 触发 vitest mock 未定义导出错误）
vi.mock('../GtAProgramConsole.vue', () => ({
  __esModule: true,
  default: { name: 'GtAProgramConsole', template: '<div class="a-program-console-stub" />' },
}))
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  __esModule: true,
  default: { name: 'GtOnlyOfficeSheet', template: '<div class="onlyoffice-stub" />' },
}))
// GtIndexChip 依赖 vue-router（useRoute/useRouter），测试环境 stub 掉，仅回显 value（Task 4.3）
vi.mock('../GtIndexChip.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId'],
    template: '<span class="gt-index-chip-stub">{{ value }}</span>',
  },
}))

import GtC1EntityControl from '../GtC1EntityControl.vue'

const stubs = {
  'el-skeleton': true,
  'el-collapse': { template: '<div><slot /></div>' },
  'el-collapse-item': { template: '<div><slot name="title" /><slot /></div>' },
  'el-progress': true,
  'el-tag': { template: '<span><slot /></span>' },
  'el-switch': true,
  'el-alert': { template: '<div><slot name="title" /><slot /></div>' },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-select': true,
  'el-option': true,
  'el-input': true,
  'el-checkbox-group': { template: '<div class="el-checkbox-group-stub"><slot /></div>' },
  'el-checkbox': { props: ['value', 'label'], template: '<label class="el-checkbox-stub">{{ label }}</label>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
  'el-upload': { template: '<div class="el-upload-stub"><slot /></div>' },
  'el-icon': { template: '<i><slot /></i>' },
}

function mountC1(sheetName: string, responses: any[] = [], readonly = false) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(responses)
    }
    // render-config selfLoad / loadPrograms
    return Promise.resolve({})
  })
  return mount(GtC1EntityControl, {
    props: { wpId: 'wp-c1', projectId: 'proj-1', wpCode: 'C1', sheetName, readonly },
    global: { stubs },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPut.mockResolvedValue([])
})

describe('sheetName v-if 分发（Req 1.5 / 5.1）', () => {
  it.each([
    ['C1 企业层面控制测试程序表', 'program'],
    ['C1-1 企业层面控制测试示例1', 'example'],
    ['C1-2 企业层面控制测试示例2', 'example'],
    ['C1-3企业层面控制测试示例3', 'example'],
    ['C1-4企业层面内控测试示例4-财务报告内部控制', 'fr-summary'],
    ['C1-4-1企业层面内控测试示例4', 'process-record'],
    ['C1-4-2企业层面内控测试示例4', 'process-record'],
    ['C1-4-4企业层面内控测试示例4', 'process-record-sample'],
    ['', 'program'],
    ['未知 sheet', 'program'],
  ])('%s → mode %s', async (sheetName, expected) => {
    const wrapper = mountC1(sheetName)
    await flushPromises()
    expect((wrapper.vm as any).mode).toBe(expected)
  })
})

describe('过程记录字段集（Req 4.2）', () => {
  it('C1-4-1 使用统一字段集（含测试方法/控制频率/如何测试/测试结果）', async () => {
    const wrapper = mountC1('C1-4-1企业层面内控测试示例4')
    await flushPromises()
    const keys = (wrapper.vm as any).processFields.map((f: any) => f.key)
    expect(keys).toContain('activity')
    expect(keys).toContain('control')
    expect(keys).toContain('freq')
    expect(keys).toContain('testMethod')
    expect(keys).toContain('howTest')
    expect(keys).toContain('testResult')
    expect(keys).not.toContain('materiality')
  })

  it('C1-4-2 额外含「重要性」字段（phase0 §5）', async () => {
    const wrapper = mountC1('C1-4-2企业层面内控测试示例4')
    await flushPromises()
    const keys = (wrapper.vm as any).processFields.map((f: any) => f.key)
    expect(keys).toContain('materiality')
  })
})

describe('item_id 构造（phase0 §6）', () => {
  it('过程记录 / 汇总 / 样本单元 item_id 前缀 C1-', async () => {
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4')
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.procItemId('testMethod')).toBe('C1-4-4-testMethod')
    expect(vm.summaryItemId(2, 'freq')).toBe('C1-4-summary-2-freq')
    expect(vm.sampleCellItemId(0, 'debit')).toBe('C1-4-4-sample-0-debit')
  })

  it('C1-4-1 过程记录 item_id 使用 k=1', async () => {
    const wrapper = mountC1('C1-4-1企业层面内控测试示例4')
    await flushPromises()
    expect((wrapper.vm as any).procItemId('activity')).toBe('C1-4-1-activity')
  })
})

describe('适用性裁剪进度排除（Req 3.3）', () => {
  it('不适用步骤排除出分母', async () => {
    const responses = [
      { item_id: 'C1-ce-1-applicable', conclusion: 'Y', remark: null, wp_ref: null },
      { item_id: 'C1-ce-1-result', conclusion: null, remark: '已测试', wp_ref: null },
      { item_id: 'C1-ce-2-applicable', conclusion: 'N', remark: '不适用理由', wp_ref: null },
      { item_id: 'C1-ce-2-result', conclusion: null, remark: '不应计入', wp_ref: null },
      { item_id: 'C1-ce-3-applicable', conclusion: 'Y', remark: null, wp_ref: null },
    ]
    const wrapper = mountC1('C1 企业层面控制测试程序表', responses)
    await flushPromises()
    // 适用步骤：1、3（共2）；已填：仅步骤1 → 50%
    expect((wrapper.vm as any).sectionProgress('ce')).toBe(50)
  })

  it('整段不适用 → 进度 100 且 isSectionApplicable=false（Req 3.3）', async () => {
    const responses = [
      { item_id: 'C1-bu-section-applicable', conclusion: 'N', remark: '非集团审计', wp_ref: null },
    ]
    const wrapper = mountC1('C1 企业层面控制测试程序表', responses)
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.isSectionApplicable('bu')).toBe(false)
    expect(vm.sectionReason('bu')).toBe('非集团审计')
    expect(vm.sectionProgress('bu')).toBe(100)
  })

  it('无数据段进度为 0', async () => {
    const wrapper = mountC1('C1 企业层面控制测试程序表', [])
    await flushPromises()
    expect((wrapper.vm as any).sectionProgress('ra')).toBe(0)
  })
})

describe('C1-4-4 样本借贷勾稽（Req 4.3/4.4，useC1SampleEngine 派生）', () => {
  it('从 checklist-responses 重建样本行并勾稽平衡', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
      { item_id: 'C1-4-4-sample-0-credit', conclusion: null, remark: '0', wp_ref: null },
      { item_id: 'C1-4-4-sample-0-desc', conclusion: null, remark: '借记应收', wp_ref: null },
      { item_id: 'C1-4-4-sample-1-debit', conclusion: null, remark: '0', wp_ref: null },
      { item_id: 'C1-4-4-sample-1-credit', conclusion: null, remark: '100', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', responses)
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.sampleRows.length).toBe(2)
    expect(vm.sampleBalance.debitTotal).toBe(100)
    expect(vm.sampleBalance.creditTotal).toBe(100)
    expect(vm.sampleBalance.balanced).toBe(true)
    // 累计借贷差（派生列）：第1行 100，第2行 0
    expect(vm.rowCumulativeDiff(0)).toBe(100)
    expect(vm.rowCumulativeDiff(1)).toBe(0)
  })

  it('借贷不等 → balanced=false', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
      { item_id: 'C1-4-4-sample-0-credit', conclusion: null, remark: '60', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', responses)
    await flushPromises()
    expect((wrapper.vm as any).sampleBalance.balanced).toBe(false)
  })

  it('新增样本行后勾稽随本地编辑实时重算（Req 4.4）', async () => {
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', [])
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.sampleRows.length).toBe(0)
    vm.addSampleRow()
    vm.addSampleRow()
    expect(vm.sampleRows.length).toBe(2)
    // 编辑金额 → 即时驱动重算
    vm.onSampleCell(0, 'debit', '250')
    vm.onSampleCell(1, 'credit', '250')
    await flushPromises()
    expect(vm.sampleBalance.debitTotal).toBe(250)
    expect(vm.sampleBalance.creditTotal).toBe(250)
    expect(vm.sampleBalance.balanced).toBe(true)
  })

  it('删除样本行后本地移除', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
      { item_id: 'C1-4-4-sample-1-debit', conclusion: null, remark: '200', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', responses)
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.sampleRows.length).toBe(2)
    vm.removeSampleRow(0)
    expect(vm.sampleRows.length).toBe(1)
    expect(vm.sampleRows[0].debit).toBe('200')
  })
})

describe('只读模式（Req 8.1）', () => {
  it('readonly 时新增/删除/编辑样本均被禁止', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', responses, true)
    await flushPromises()
    const vm = wrapper.vm as any
    vm.addSampleRow()
    expect(vm.sampleRows.length).toBe(1) // 未新增
    vm.onSampleCell(0, 'debit', '999')
    expect(vm.sampleRows[0].debit).toBe('100') // 未变
    vm.removeSampleRow(0)
    expect(vm.sampleRows.length).toBe(1) // 未删除
    // 只读下不发起保存
    expect(mockPut).not.toHaveBeenCalled()
  })
})

describe('GtIndexChip 引用渲染（Task 4.3，Req 6.1/6.2/6.3）', () => {
  it('过程记录「关联底稿索引」将多编码切分为多个 GtIndexChip', async () => {
    const responses = [
      { item_id: 'C1-4-1-refIndex', conclusion: null, remark: 'C21-1，A14', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-1企业层面内控测试示例4', responses, true)
    await flushPromises()
    const chips = wrapper.findAll('.gt-index-chip-stub')
    const texts = chips.map((c) => c.text())
    expect(texts).toContain('C21-1')
    expect(texts).toContain('A14')
  })

  it('C1-4-4 样本引用列渲染 GtIndexChip', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-ref', conclusion: null, remark: 'C21-1', wp_ref: null },
    ]
    const wrapper = mountC1('C1-4-4企业层面内控测试示例4', responses, true)
    await flushPromises()
    const texts = wrapper.findAll('.gt-index-chip-stub').map((c) => c.text())
    expect(texts).toContain('C21-1')
  })

  it('splitRefs 去除包裹符号并按分隔符切分', async () => {
    const wrapper = mountC1('C1-4-1企业层面内控测试示例4', [])
    await flushPromises()
    const split = (wrapper.vm as any).splitRefs
    expect(split('<C21-1>；A14')).toEqual(['C21-1', 'A14'])
    expect(split('')).toEqual([])
    expect(split(null)).toEqual([])
  })
})

describe('交互增强：点选控件 / 引导区 / 方法论上下文 / tooltip（Task 7.1，Req 9.1~9.6）', () => {
  it('测试方法多选点选：getMultiEnum/setMultiEnum 逗号往返 + 过滤非法值（Req 9.1 / Property 7）', async () => {
    const responses = [
      { item_id: 'C1-4-summary-1-method', conclusion: '检查,重新执行', remark: null, wp_ref: null },
    ]
    const wrapper = mountC1('C1-4企业层面内控测试示例4-财务报告内部控制', responses)
    await flushPromises()
    const vm = wrapper.vm as any
    // 读取：逗号串 → 数组
    expect(vm.getMultiEnum('C1-4-summary-1-method')).toEqual(['检查', '重新执行'])
    // 保存：数组 → 逗号串，且非法值被过滤（点选合法性）
    vm.setMultiEnum('C1-4-summary-2-method', ['询问和观察', '非法方法', '抽样'])
    await flushPromises()
    expect(vm.getMultiEnum('C1-4-summary-2-method')).toEqual(['询问和观察', '抽样'])
    // 空数组 → 清空为 null
    vm.setMultiEnum('C1-4-summary-2-method', [])
    expect(vm.getMultiEnum('C1-4-summary-2-method')).toEqual([])
  })

  it('顶部引导区含 4 个序号步骤（填写项目信息→逐要素测试→财报内控→结论，Req 9.3）', async () => {
    const wrapper = mountC1('C1 企业层面控制测试程序表')
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.GUIDE_STEPS.length).toBe(4)
    expect(vm.GUIDE_STEPS.map((s: any) => s.title)).toEqual([
      '填写项目信息', '逐要素测试', '财报内控过程记录', '形成结论',
    ])
    // DOM：蓝色渐变引导区渲染
    expect(wrapper.find('.c1-guide').exists()).toBe(true)
    expect(wrapper.findAll('.c1-guide-step').length).toBe(4)
  })

  it('方法论上下文：九段均有琥珀色左边线说明块（Req 9.4）', async () => {
    const wrapper = mountC1('C1 企业层面控制测试程序表')
    await flushPromises()
    const vm = wrapper.vm as any
    for (const slug of ['ce', 'ra', 'mo', 'bu', 'ic', 'fr', 'el', 'ye', 'rp']) {
      expect(vm.methodologyOf(slug).length).toBeGreaterThan(0)
    }
    // DOM：适用段渲染方法论块
    expect(wrapper.findAll('.c1-methodology').length).toBeGreaterThan(0)
  })

  it('判断列表头提供 tooltip 说明来源与判断依据（Req 9.5）', async () => {
    const wrapper = mountC1('C1-4企业层面内控测试示例4-财务报告内部控制')
    await flushPromises()
    const tips = wrapper.findAll('.c1-judge-head')
    expect(tips.length).toBe(3) // 控制频率 / 测试方法 / 测试结论
  })

  it('fr-summary 测试方法渲染为 checkbox-group 多选点选控件（Req 9.1）', async () => {
    const wrapper = mountC1('C1-4企业层面内控测试示例4-财务报告内部控制')
    await flushPromises()
    // 每行一个 checkbox-group，6 行 → 6 组
    expect(wrapper.findAll('.el-checkbox-group-stub').length).toBe(6)
  })
})

describe('UI 铁律：section 标题行 AI 辅助按钮（Task 4.3，Req 8.3）', () => {
  it('过程记录卡片标题行含 AI 辅助按钮', async () => {
    const wrapper = mountC1('C1-4-1企业层面内控测试示例4', [])
    await flushPromises()
    expect(wrapper.text()).toContain('AI 辅助')
  })

  it('财报内控汇总卡片标题行含 AI 辅助按钮', async () => {
    const wrapper = mountC1('C1-4企业层面内控测试示例4-财务报告内部控制', [])
    await flushPromises()
    expect(wrapper.text()).toContain('AI 辅助')
  })
})
