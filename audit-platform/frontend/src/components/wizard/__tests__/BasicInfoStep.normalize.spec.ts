/**
 * BasicInfoStep.vue — 三码输入框失焦写回规范化值（R1.4）
 *
 * Spec: .kiro/specs/consol-group-code-entry-consistency/ 任务 1.3
 * - 三个代码输入框失焦后 form 中存规范化值（NFKC → strip → upper；空串 → ''）
 * - 校验规则对规范化值判定：全角 / 小写 / 首尾空格的合法码不报错，中间空格仍报错
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'

vi.mock('@/services/commonApi', () => ({
  fetchTemplateRecommendation: vi.fn().mockResolvedValue(null),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'

const InputStub = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: String, default: '' } },
  emits: ['update:modelValue', 'blur'],
  template: `
    <input
      v-bind="$attrs"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      @blur="$emit('blur', $event)"
    />
  `,
})

const STUBS = {
  'el-form': defineComponent({
    template: '<form><slot /></form>',
    methods: { validate: () => Promise.resolve(true) },
  }),
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': InputStub,
  'el-select': true,
  'el-option': true,
  'el-date-picker': true,
  'el-radio-group': { template: '<div class="radio-group"><slot /></div>' },
  'el-radio-button': { template: '<span class="radio-button"><slot /></span>' },
  'el-input-number': true,
  'el-alert': { template: '<div class="alert"><slot /></div>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-dialog': true,
  BusinessCategoryFlowChart: true,
}

function mountStep(): VueWrapper<any> {
  return mount(BasicInfoStep, { global: { plugins: [getActivePinia()!], stubs: STUBS } })
}

describe('BasicInfoStep 三码失焦规范化', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('三个代码输入框真实失焦后写回规范化值', async () => {
    const wrapper = mountStep()
    const cases = [
      ['company-code-input', ' ９１１１００００７１０９３０４５１ｄ ', '91110000710930451D'],
      ['parent-code-input', ' 911100002000000005 ', '911100002000000005'],
      ['ultimate-code-input', '９１１１００００１００００００００ｒ', '91110000100000000R'],
    ] as const

    for (const [testId, input, expected] of cases) {
      const control = wrapper.get(`[data-testid="${testId}"]`)
      await control.setValue(input)
      await control.trigger('blur')
      await nextTick()
      expect((control.element as HTMLInputElement).value).toBe(expected)
    }

    const ultimate = wrapper.get('[data-testid="ultimate-code-input"]')
    await ultimate.setValue('   ')
    await ultimate.trigger('blur')
    expect((ultimate.element as HTMLInputElement).value).toBe('')
  })

  it('三条代码校验规则对规范化值判定；中间空格仍报错', async () => {
    const wrapper = mountStep()
    const rules = wrapper.vm.rules as Record<string, Array<{ validator?: any }>>
    const validators = [
      rules.company_code.find((r) => r.validator)!.validator!,
      rules.parent_company_code[0].validator!,
      rules.ultimate_company_code[0].validator!,
    ]

    const runValidator = (validator: any, value: string) => new Promise<Error | undefined>((resolve) => {
      validator({}, value, (err?: Error) => resolve(err))
    })

    await expect(runValidator(validators[0], '91110000710930451d')).resolves.toBeUndefined()
    await expect(runValidator(validators[1], ' 911100002000000005 ')).resolves.toBeUndefined()
    await expect(runValidator(validators[2], '９１１１００００１００００００００ｒ')).resolves.toBeUndefined()
    await expect(runValidator(validators[1], '91110000 2000000005')).resolves.toMatchObject({
      message: expect.stringContaining('统一社会信用代码'),
    })
  })
})
