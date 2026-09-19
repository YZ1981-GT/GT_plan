/**
 * GtC21FindingsSummary.spec.ts — C21-1 IT 发现汇总交互视图（Task 5.1）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 5.1
 * Validates: Requirements 5.1, 5.2, 5.3, 5.4
 *
 * 覆盖：
 *  - 汇总 defects 渲染每条缺陷行（缺陷编号/所属控制点/问题描述）（Req 5.1）
 *  - 空汇总显示「暂无 IT 审计发现」
 *  - 补充影响分析/整改建议持久化（item_id C22.C21-1.{controlId}.impact/.remediation）（Req 5.3）
 *  - 财务报表认定 9 认定多选持久化
 *  - 每条缺陷行提供 GtIndexChip 跳回来源控制点子页（value=sheet:{controlId}）（Req 5.4）
 *  - defects 变更 → 视图更新（Req 5.2）
 *  - 只读模式禁止保存（Req 9）
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

// GtIndexChip stub（暴露 value/validate 以便断言）
vi.mock('../GtIndexChip.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtIndexChip',
    props: ['value', 'validate'],
    template: '<span class="gt-index-chip-stub" :data-value="value" :data-validate="String(validate)">{{ value }}</span>',
  },
}))

import GtC21FindingsSummary from '../GtC21FindingsSummary.vue'
import { c21SummaryItemId, type ItgcDefect } from '../composables/useC22BundleState'

const stubs = {
  'el-card': { template: '<div class="el-card-stub"><slot name="header" /><slot /></div>' },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-input': {
    inheritAttrs: false,
    props: ['modelValue', 'readonly'],
    emits: ['update:modelValue', 'input'],
    template: `<input class="el-input-stub" :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value); $emit('input', $event.target.value)" />`,
  },
  'el-checkbox-group': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: '<div class="el-checkbox-group-stub"><slot /></div>',
  },
  'el-checkbox': { props: ['label', 'value'], template: '<label class="el-checkbox-stub"><slot /></label>' },
  'el-table': { props: ['data'], template: '<div class="el-table-stub"><slot /></div>' },
  'el-table-column': { template: '<div class="el-table-column-stub"><slot :row="{}" :$index="0" /></div>' },
}

function defect(overrides: Partial<ItgcDefect> = {}): ItgcDefect {
  return {
    controlId: 'SA-7',
    group: '信息安全',
    sheet: 'SA-7',
    description: '权限未及时回收',
    defectNo: 'ITGC#1',
    appSystem: 'A系统',
    ...overrides,
  }
}

function mountView(defects: ItgcDefect[] = [], responses: any[] = [], readonly = false) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(responses)
    }
    return Promise.resolve({})
  })
  mockPut.mockResolvedValue({})
  return mount(GtC21FindingsSummary, {
    props: { wpId: 'wp-c22', projectId: 'proj-1', defects, readonly },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
})

describe('GtC21FindingsSummary — 汇总渲染（Req 5.1）', () => {
  it('空汇总显示「暂无 IT 审计发现」', async () => {
    const wrapper = mountView([])
    await flushPromises()
    expect(wrapper.text()).toContain('暂无 IT 审计发现')
    expect(wrapper.findAll('.c21f-finding').length).toBe(0)
  })

  it('每条缺陷渲染一行，含缺陷编号/所属控制点/问题描述', async () => {
    const wrapper = mountView([defect(), defect({ controlId: 'PM-3', defectNo: 'ITGC#2', description: '变更未审批' })])
    await flushPromises()
    const rows = wrapper.findAll('.c21f-finding')
    expect(rows.length).toBe(2)
    expect(wrapper.text()).toContain('ITGC#1')
    expect(wrapper.text()).toContain('权限未及时回收')
    expect(wrapper.text()).toContain('ITGC#2')
    expect(wrapper.text()).toContain('变更未审批')
  })

  it('findingRows 计算合并 defect + supplement', async () => {
    const wrapper = mountView([defect()])
    await flushPromises()
    const rows = (wrapper.vm as any).findingRows
    expect(rows.length).toBe(1)
    expect(rows[0].defect.controlId).toBe('SA-7')
    expect(rows[0].sourceRef).toBe('sheet:SA-7')
  })
})

describe('GtC21FindingsSummary — GtIndexChip 跳回来源子页（Req 5.4）', () => {
  it('每条缺陷行提供 chip value=sheet:{controlId} 且 validate=false', async () => {
    const wrapper = mountView([defect({ controlId: 'PE-6' })])
    await flushPromises()
    const chip = wrapper.find('.gt-index-chip-stub')
    expect(chip.exists()).toBe(true)
    expect(chip.attributes('data-value')).toBe('sheet:PE-6')
    expect(chip.attributes('data-validate')).toBe('false')
  })
})

describe('GtC21FindingsSummary — 补充字段持久化（Req 5.3）', () => {
  it('回填已存的影响分析/整改建议', async () => {
    const responses = [
      { item_id: c21SummaryItemId('SA-7', 'impact'), conclusion: null, remark: '可能导致越权访问' },
      { item_id: c21SummaryItemId('SA-7', 'remediation'), conclusion: null, remark: '建立离职权限回收流程' },
      { item_id: c21SummaryItemId('SA-7', 'assertions'), conclusion: null, remark: JSON.stringify(['准确性', '存在']) },
    ]
    const wrapper = mountView([defect()], responses)
    await flushPromises()
    const slot = (wrapper.vm as any).supplements['SA-7']
    expect(slot.impact).toBe('可能导致越权访问')
    expect(slot.remediation).toBe('建立离职权限回收流程')
    expect(slot.assertions).toEqual(['准确性', '存在'])
  })

  it('saveFieldNow 以正确 item_id PUT 保存', async () => {
    const wrapper = mountView([defect()])
    await flushPromises()
    ;(wrapper.vm as any).supplements['SA-7'].impact = '影响X'
    ;(wrapper.vm as any).saveFieldNow('SA-7', 'impact')
    await flushPromises()
    expect(mockPut).toHaveBeenCalled()
    const [url, payload] = mockPut.mock.calls[mockPut.mock.calls.length - 1]
    expect(url).toBe('/api/workpapers/wp-c22/checklist-responses')
    expect(payload.items[0].item_id).toBe('C22.C21-1.SA-7.impact')
    expect(payload.items[0].remark).toBe('影响X')
  })

  it('财务报表认定多选变更即时保存为 JSON', async () => {
    const wrapper = mountView([defect()])
    await flushPromises()
    ;(wrapper.vm as any).supplements['SA-7'].assertions = ['完整性', '截止']
    ;(wrapper.vm as any).onAssertionsChange('SA-7')
    await flushPromises()
    const call = mockPut.mock.calls.find((c) => c[1].items[0].item_id === 'C22.C21-1.SA-7.assertions')
    expect(call).toBeDefined()
    expect(JSON.parse(call![1].items[0].remark)).toEqual(['完整性', '截止'])
  })
})

describe('GtC21FindingsSummary — defects 变更同步（Req 5.2）', () => {
  it('新增缺陷后汇总行数更新', async () => {
    const list: ItgcDefect[] = [defect()]
    const wrapper = mountView(list)
    await flushPromises()
    expect(wrapper.findAll('.c21f-finding').length).toBe(1)

    await wrapper.setProps({ defects: [defect(), defect({ controlId: 'NS-1', defectNo: 'ITGC#2' })] })
    await flushPromises()
    expect(wrapper.findAll('.c21f-finding').length).toBe(2)
  })
})

describe('GtC21FindingsSummary — 只读模式（Req 9）', () => {
  it('只读时 saveFieldNow 不触发 PUT', async () => {
    const wrapper = mountView([defect()], [], true)
    await flushPromises()
    mockPut.mockClear()
    ;(wrapper.vm as any).saveFieldNow('SA-7', 'impact')
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
  })
})
