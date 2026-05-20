/**
 * InventoryImpairmentDialog.spec.ts — Sprint 3 Task 3.5 (F-F12)
 *
 * 烟测目标：
 * 1. visible=true 时组件可挂载
 * 2. 表单默认值（method=lower_of_cost_or_nrv / threshold=50000 / 1 行产品）
 * 3. 添加/删除产品行
 * 4. 调用 impairment-analysis API 后渲染 result 区
 * 5. 风险等级标签映射（high/medium/low → 红/黄/绿）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: (...args: any[]) => mockPost(...args),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import InventoryImpairmentDialog from '../InventoryImpairmentDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
}

describe('InventoryImpairmentDialog (F-F12)', () => {
  it('mounts with default form state', () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.form.method).toBe('lower_of_cost_or_nrv')
    expect(vm.form.materiality_threshold).toBe(50000)
    expect(vm.form.products).toHaveLength(1)
    expect(vm.result).toBeNull()
  })

  it('addRow and removeRow work', async () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.form.products).toHaveLength(1)
    vm.addRow()
    expect(vm.form.products).toHaveLength(2)
    vm.removeRow(0)
    expect(vm.form.products).toHaveLength(1)
    // 删除最后一行 → 自动补一行
    vm.removeRow(0)
    expect(vm.form.products).toHaveLength(1)
  })

  it('riskLabel maps codes to Chinese labels', () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.riskLabel('high')).toBe('高')
    expect(vm.riskLabel('medium')).toBe('中')
    expect(vm.riskLabel('low')).toBe('低')
  })

  it('formatAmount converts numeric string to zh-CN with 2 decimals', () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    // 不同 locale 输出可能差异，校验关键特征：含逗号 + 2 位小数
    const out = vm.formatAmount('1234567.89')
    expect(out).toMatch(/1.234.567/) // 千分位（CN 用 , 或 ,）
    expect(out).toMatch(/89$/)
  })

  it('onAnalyze calls API and stores result', async () => {
    const fakeResp = {
      method: 'lower_of_cost_or_nrv',
      total_products: 1,
      suggestions: [
        {
          product_name: 'A',
          book_cost: '100',
          nrv: '80',
          suggested_provision: '20',
          rationale: 'cost > nrv',
          risk_level: 'low',
        },
      ],
      summary: 'analyzed 1 product',
      total_suggested_provision: '20',
      is_llm_stub: true,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    vm.form.products = [
      { product_name: 'A', cost: 100, nrv: 80, aging_months: 6, qty: 10 },
    ]
    await vm.onAnalyze()
    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/f2/impairment-analysis`,
      expect.objectContaining({
        method: 'lower_of_cost_or_nrv',
        materiality_threshold: 50000,
        products: [
          { product_name: 'A', cost: 100, nrv: 80, aging_months: 6, qty: 10 },
        ],
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('onAnalyze with empty products shows warning and skips API call', async () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: PROPS_BASE,
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    vm.form.products = [
      { product_name: '', cost: 0, nrv: 0, aging_months: 0, qty: 0 },
    ]
    await vm.onAnalyze()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('result resets when visible changes to false', async () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    vm.result = { method: 'x', total_products: 0, suggestions: [], summary: '', total_suggested_provision: '0', is_llm_stub: true }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  // P0-3 写回联动测试
  it('onApplyToSheet posts apply_to_sheet and emits applied', async () => {
    const fakeResp = {
      method: 'lower_of_cost_or_nrv',
      total_products: 1,
      suggestions: [{
        product_name: 'A', book_cost: '100', nrv: '80',
        suggested_provision: '20', rationale: 'cost > nrv', risk_level: 'low',
      }],
      summary: 'analyzed 1',
      total_suggested_provision: '20',
      is_llm_stub: true,
      applied_to_sheet: '跌价准备测试表F2-47',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(InventoryImpairmentDialog, {
      props: { ...PROPS_BASE, targetSheet: '跌价准备测试表F2-47' },
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    vm.form.products = [
      { product_name: 'A', cost: 100, nrv: 80, aging_months: 0, qty: 0 },
    ]
    await vm.onApplyToSheet()
    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/f2/impairment-analysis`,
      expect.objectContaining({
        apply_to_sheet: '跌价准备测试表F2-47',
        method: 'lower_of_cost_or_nrv',
      }),
    )
    // 弹窗 emit applied 事件
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['跌价准备测试表F2-47'])
  })

  it('onApplyToSheet skips when targetSheet is empty', async () => {
    const wrapper = mount(InventoryImpairmentDialog, {
      props: { ...PROPS_BASE, targetSheet: '' },
      global: {
        stubs: {
          'el-dialog': true, 'el-form': true, 'el-form-item': true,
          'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
          'el-input': true, 'el-divider': true, 'el-table': true,
          'el-table-column': true, 'el-button': true, 'el-alert': true,
          'el-tag': true,
        },
      },
    })
    const vm = wrapper.vm as any
    vm.form.products = [{ product_name: 'A', cost: 100, nrv: 80, aging_months: 0, qty: 0 }]
    await vm.onApplyToSheet()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
