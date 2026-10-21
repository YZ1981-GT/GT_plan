/**
 * FormulaDefinitionEditDialog —— 全局设置 / 模板详情编辑一个公式位（spec formula-global-settings-sync）
 *
 * 守护（浏览器实测发现）：公式类别、比较符这类枚举字段显示中文选项，不再原样露出 auto_calc；
 * 现有值不在清单里（旧数据）时保留为一项，打开再保存不会被静默清空。
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus, { ElOption, ElSelect } from 'element-plus'

import FormulaDefinitionEditDialog from '../FormulaDefinitionEditDialog.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dlg"><slot /><slot name="footer" /></div>',
})

function open(definition: Record<string, unknown>, execFields = ['formula', 'formula_category']) {
  return mount(FormulaDefinitionEditDialog, {
    props: { modelValue: true, execFields, descFields: ['formula_description'], definition },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub } },
  })
}

function optionLabels(w: ReturnType<typeof open>, field: string): string[] {
  const select = w.findAllComponents(ElSelect).find((s) => s.attributes('data-testid') === `fde-select-${field}`)
  expect(select, `${field} 应渲染为下拉`).toBeTruthy()
  return select!.findAllComponents(ElOption).map((o) => String(o.props('label')))
}

describe('FormulaDefinitionEditDialog 枚举字段', () => {
  it('公式类别给中文选项，选中值仍是原取值', async () => {
    const w = open({ formula: "TB('1001','期末余额')", formula_category: 'auto_calc' })
    await flushPromises()
    expect(optionLabels(w, 'formula_category')).toEqual(['自动运算', '逻辑审核', '提示合理性'])
    const select = w.findAllComponents(ElSelect).find((s) => s.attributes('data-testid') === 'fde-select-formula_category')!
    expect(select.props('modelValue')).toBe('auto_calc')
    expect(w.text()).not.toContain('auto_calc')
  })

  it('旧数据里不认识的类别保留为一项，保存原样带回', async () => {
    const w = open({ formula: 'X', formula_category: 'legacy_kind' })
    await flushPromises()
    expect(optionLabels(w, 'formula_category')).toEqual(['自动运算', '逻辑审核', '提示合理性', 'legacy_kind'])
    await w.find('[data-testid="fde-ok"]').trigger('click')
    await flushPromises()
    const saved = w.emitted('save')?.[0]?.[0] as Record<string, unknown>
    expect(saved.formula_category).toBe('legacy_kind')
  })

  it('表间审核比较符给中文选项；公式字段仍是文本框', async () => {
    const w = open({ left_ref: "ROW('BS-001')", operator: '<=', right_ref: '1' }, ['left_ref', 'operator', 'right_ref'])
    await flushPromises()
    expect(optionLabels(w, 'operator')).toEqual(['等于（=）', '小于等于（<=）', '大于等于（>=）'])
    expect(w.findAllComponents(ElSelect)).toHaveLength(1)
  })
})
