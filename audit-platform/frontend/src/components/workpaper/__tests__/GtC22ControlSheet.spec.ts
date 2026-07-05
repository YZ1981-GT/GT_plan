/**
 * GtC22ControlSheet.spec.ts — C22 IT 控制域测试子页交互渲染（Task 4.2）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 4.2
 * Validates: Requirements 4.3, 4.4
 *
 * 覆盖：
 *  - 5 大区块渲染：控制信息 / 设计有效性 / 执行有效性 / 样本记录 / 缺陷评估（Req 4.3）
 *  - 控制编号/控制活动 引用主矩阵 C/D 列（matrixRow）（Req 4.4）
 *  - PM-4c #REF! 兜底：refBroken → 用 tab.id + 矩阵行内容，显示「公式引用已修复」
 *  - checklist-responses 读取（item_id = C22.{controlId}.{field}）与回填
 *  - 结论/是否异常点选即时保存；长文本 debounce 保存（PUT 批量）
 *  - 抽样 > 1 展开样本记录表
 *  - 只读透传
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

import GtC22ControlSheet from '../GtC22ControlSheet.vue'
import { C22_BUNDLE_TABS, itgcItemId, type TabDef } from '../composables/useC22BundleState'

function findTab(id: string): TabDef {
  const t = C22_BUNDLE_TABS.find((t) => t.id === id)
  if (!t) throw new Error(`tab ${id} not found`)
  return t
}

const stubs = {
  'el-card': { template: '<div class="el-card"><slot name="header" /><slot /></div>' },
  'el-input': {
    props: ['modelValue', 'readonly', 'type'],
    emits: ['update:modelValue', 'input'],
    template:
      '<textarea class="el-input" :readonly="readonly" :value="modelValue" ' +
      '@input="$emit(\'update:modelValue\', $event.target.value); $emit(\'input\', $event.target.value)" />',
  },
  'el-select': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template:
      '<select class="el-select" :disabled="disabled" :value="modelValue" ' +
      '@change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)"><slot /></select>',
  },
  'el-option': { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
  'el-radio-group': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: '<div class="el-radio-group"><slot /></div>',
  },
  'el-radio-button': { props: ['label'], template: '<label class="el-radio-button">{{ label }}</label>' },
  'el-table': { props: ['data'], template: '<table class="el-table"><slot /></table>' },
  'el-table-column': { template: '<div class="el-table-column"><slot :row="{}" :$index="0" /></div>' },
  'el-button': { template: '<button class="el-button"><slot /></button>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
}

function mountSheet(opts: {
  tab?: TabDef
  matrixRow?: any
  responses?: any[]
  readonly?: boolean
} = {}) {
  const tab = opts.tab ?? findTab('SA-3')
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(opts.responses ?? [])
    }
    return Promise.resolve([])
  })
  mockPut.mockResolvedValue({})
  return mount(GtC22ControlSheet, {
    props: {
      wpId: 'wp-c22',
      projectId: 'proj-1',
      tab,
      matrixRow: opts.matrixRow ?? { row: tab.matrixRow, controlNo: tab.id, description: '账号权限管理', appSystem: 'A系统' },
      readonly: opts.readonly ?? false,
    },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  vi.useRealTimers()
})

describe('GtC22ControlSheet — 区块渲染（Req 4.3）', () => {
  it('渲染 5 大区块：控制信息 + 设计/执行有效性 + 缺陷评估', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('.c22cs-header').exists()).toBe(true)
    const titles = wrapper.findAll('.c22cs-card-title').map((n) => n.text())
    expect(titles).toContain('一、设计有效性')
    expect(titles).toContain('二、执行有效性')
    expect(titles).toContain('三、缺陷评估')
  })

  it('默认（是否异常=否）不显示缺陷描述区', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('.c22cs-no-defect').exists()).toBe(true)
  })
})

describe('GtC22ControlSheet — 公式引用矩阵 C/D 列（Req 4.4）', () => {
  it('控制编号取自 matrixRow.controlNo，控制活动取自 matrixRow.description', async () => {
    const wrapper = mountSheet({
      matrixRow: { row: 13, controlNo: 'SA-7', description: '用户权限定期复核', appSystem: 'B系统' },
      tab: findTab('SA-7'),
    })
    await flushPromises()
    expect((wrapper.vm as any).controlNo).toBe('SA-7')
    expect((wrapper.vm as any).controlActivity).toBe('用户权限定期复核')
    // 引用来源提示含矩阵行号
    expect((wrapper.vm as any).controlNoRefTip).toContain('C13')
    expect((wrapper.vm as any).controlActivityRefTip).toContain('D13')
  })

  it('PM-4c #REF! 兜底：refBroken → 显示「公式引用已修复」并回退 tab.id', async () => {
    const pm4c = findTab('PM-4c')
    expect(pm4c.refBroken).toBe(true)
    const wrapper = mountSheet({
      tab: pm4c,
      matrixRow: { row: 32, controlNo: 'PM-4c', description: '程序变更审批' },
    })
    await flushPromises()
    expect(wrapper.find('.c22cs-ref-fixed').exists()).toBe(true)
    expect((wrapper.vm as any).refBroken).toBe(true)
    // 即使 matrixRow.controlNo 缺失也回退 tab.id
    const wrapper2 = mountSheet({ tab: pm4c, matrixRow: { row: 32 } })
    await flushPromises()
    expect((wrapper2.vm as any).controlNo).toBe('PM-4c')
  })
})

describe('GtC22ControlSheet — checklist-responses 读取回填', () => {
  it('按 item_id 前缀 C22.{controlId}. 回填字段（conclusion / remark 分槽）', async () => {
    const responses = [
      { item_id: itgcItemId('SA-3', 'design-conclusion'), conclusion: '有效', remark: null },
      { item_id: itgcItemId('SA-3', 'exec-conclusion'), conclusion: '部分有效', remark: null },
      { item_id: itgcItemId('SA-3', 'design-procedure'), conclusion: null, remark: '执行了穿行测试' },
      { item_id: itgcItemId('SA-3', 'abnormal'), conclusion: '是', remark: null },
      { item_id: itgcItemId('SA-3', 'defect-desc'), conclusion: null, remark: '权限未复核' },
      // 其他控制点的响应不应污染本页
      { item_id: itgcItemId('SA-5', 'design-conclusion'), conclusion: '无效', remark: null },
    ]
    const wrapper = mountSheet({ responses })
    await flushPromises()
    const form = (wrapper.vm as any).form
    expect(form.designConclusion).toBe('有效')
    expect(form.execConclusion).toBe('部分有效')
    expect(form.designProcedure).toBe('执行了穿行测试')
    expect(form.abnormal).toBe('是')
    expect(form.defectDesc).toBe('权限未复核')
  })

  it('是否异常=是 → 显示缺陷编号/描述区', async () => {
    const responses = [
      { item_id: itgcItemId('SA-3', 'abnormal'), conclusion: '是', remark: null },
    ]
    const wrapper = mountSheet({ responses })
    await flushPromises()
    expect((wrapper.vm as any).showDefect).toBe(true)
  })
})

describe('GtC22ControlSheet — 保存联动', () => {
  it('结论点选即时 PUT checklist-responses（conclusion 槽）', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    ;(wrapper.vm as any).form.designConclusion = '有效'
    ;(wrapper.vm as any).saveNow?.('design-conclusion', '有效')
    await flushPromises()
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c22/checklist-responses',
      expect.objectContaining({
        items: [expect.objectContaining({
          item_id: 'C22.SA-3.design-conclusion',
          conclusion: '有效',
          remark: null,
        })],
      }),
    )
  })

  it('是否异常=是 → 触发保存并建议缺陷编号 ITGC#1', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    ;(wrapper.vm as any).form.abnormal = '是'
    ;(wrapper.vm as any).onAbnormalChange?.('是')
    await flushPromises()
    expect((wrapper.vm as any).form.defectNo).toBe('ITGC#1')
    // abnormal 存 conclusion 槽
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c22/checklist-responses',
      expect.objectContaining({
        items: [expect.objectContaining({ item_id: 'C22.SA-3.abnormal', conclusion: '是' })],
      }),
    )
  })

  it('emit updated 通知父组件刷新', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    ;(wrapper.vm as any).saveNow?.('exec-conclusion', '有效')
    await flushPromises()
    expect(wrapper.emitted('updated')).toBeTruthy()
    expect(wrapper.emitted('updated')?.[0]).toEqual(['SA-3'])
  })
})

describe('GtC22ControlSheet — 样本记录表（抽样 > 1）', () => {
  it('sample-size <= 1 不展开；> 1 展开', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect((wrapper.vm as any).showSampleTable).toBe(false)
    ;(wrapper.vm as any).form.sampleSize = '25'
    await flushPromises()
    expect((wrapper.vm as any).showSampleTable).toBe(true)
  })

  it('sample-records JSON 回填', async () => {
    const responses = [
      {
        item_id: itgcItemId('SA-3', 'sample-records'),
        conclusion: null,
        remark: JSON.stringify([{ seq: '1', desc: 's1', result: '通过', remark: '' }]),
      },
    ]
    const wrapper = mountSheet({ responses })
    await flushPromises()
    const rows = (wrapper.vm as any).sampleRecords
    expect(rows.length).toBe(1)
    expect(rows[0].desc).toBe('s1')
    expect(rows[0].result).toBe('通过')
  })
})

describe('GtC22ControlSheet — 只读透传（Req 9）', () => {
  it('readonly → saveNow / saveDebounced 不触发 PUT', async () => {
    const wrapper = mountSheet({ readonly: true })
    await flushPromises()
    mockPut.mockClear()
    ;(wrapper.vm as any).saveNow?.('design-conclusion', '有效')
    ;(wrapper.vm as any).saveDebounced?.('design-procedure', 'x')
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
  })
})
