/**
 * H2-14 监盘小结页能挂载并渲染（原先模板读 state.completenessOk.value，composable 没有该字段 ⇒ 渲染即报错），
 * 已存的扩展字段读回后在页面上可见，编辑后保存的是完整小结。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import H2TabStocktakeSummary from '../H2TabStocktakeSummary.vue'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() }, ElMessageBox: { prompt: vi.fn() } }))

function mountWith(stored: Record<string, unknown>) {
  const saveResponse = vi.fn()
  const allResponses = new Map<string, any>([
    ['H2-14-summary', { item_id: 'H2-14-summary', remark: JSON.stringify(stored), conclusion: null }],
  ])
  const wrapper = mount(H2TabStocktakeSummary, {
    props: { wpId: 'wp-1', projectId: 'p-1', allResponses, isReadonly: false },
    global: {
      provide: { saveResponse, openReviewDialog: () => {} },
      stubs: {
        GtIndexChip: true,
        ItemAttachment: true,
        // 表格列的作用域插槽在测试里不渲染（行内容由模型测试覆盖）
        'el-table': true,
        'el-table-column': true,
        'el-card': { template: '<div><slot name="header" /><slot /></div>' },
        // @click 作为透传属性挂到根 button 上，原生点击即触发
        'el-button': { template: '<button><slot /></button>' },
      },
    },
  })
  return { wrapper, saveResponse }
}

describe('H2TabStocktakeSummary', () => {
  it('挂载不报错，闸门按已存内容计算', () => {
    const { wrapper } = mountWith({ bsDateNote: '察看日在资产负债表日后 3 天', conclusion: '结论' })
    expect(wrapper.text()).toContain('完工程度闸门')
    expect(wrapper.text()).toContain('项待补')
    expect(wrapper.text()).toContain('有无长期停工的工程')
  })

  it('新增企业人员后保存的是含扩展字段的完整小结', async () => {
    const { wrapper, saveResponse } = mountWith({ engDept: '工程部', policyIndex: 'C7' })
    const btn = wrapper.findAll('button').find((b) => b.text().includes('+ 企业人员'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(saveResponse).toHaveBeenCalled()
    const [itemId, value] = saveResponse.mock.calls.at(-1)!
    expect(itemId).toBe('H2-14-summary')
    expect(value.engDept).toBe('工程部')
    expect(value.policyIndex).toBe('C7')
    expect(value.clientPersonnel).toHaveLength(1)
  })
})
