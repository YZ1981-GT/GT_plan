/**
 * BasicInfoStep — 质控业务分类 / 专项场景（spec trim-generation-plan-followup-optimizations R4）
 *
 * - 已填写的细分类（A1~B6）读回时作为单独选项保留，不擅自改成组级；
 * - 分类未填写时按报告模板类型给同组建议、项目类型为 IPO 时给场景建议 —— 只建议，不自动写入；
 * - 旧向导数据没有场景键时按常规年审回填。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'

vi.mock('@/services/commonApi', () => ({
  fetchTemplateRecommendation: vi.fn().mockResolvedValue(null),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'
import { useWizardStore } from '@/stores/wizard'
import { SCENARIO_OPTIONS, categoryGroupFromSubtype } from '@/types/projectClassification'

const STUBS = {
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': true,
  'el-select': { template: '<div><slot /></div>' },
  'el-option': true,
  'el-date-picker': true,
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': true,
  'el-input-number': true,
  'el-alert': true,
  'el-tag': { template: '<span><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-dialog': true,
}

async function mountWith(saved: Record<string, unknown> | null) {
  const store = useWizardStore()
  store.projectId = saved ? 'proj-r4' : null
  if (saved) store.stepData.basic_info = saved as any
  const wrapper = mount(BasicInfoStep, { global: { plugins: [getActivePinia()!], stubs: STUBS } })
  await flushPromises()
  return wrapper.vm as any
}

describe('BasicInfoStep 质控业务分类 / 专项场景', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('已填写的细分类原样保留并作为单独选项', async () => {
    const vm = await mountWith({ client_name: '某公司', business_category: 'A1', scenario: 'listed', company_subtype: 'type_c' })
    expect(vm.form.business_category).toBe('A1')
    expect(vm.keptSubcategory).toBe('A1')
    expect(vm.categorySuggestion).toBeNull()
    expect(vm.form.scenario).toBe('listed')
  })

  it('分类未填写时只给同组建议，不自动写入', async () => {
    const vm = await mountWith({ client_name: '某公司', business_category: null, scenario: 'normal', company_subtype: 'type_b' })
    expect(vm.categorySuggestion).toBe('B')
    expect(vm.form.business_category).toBeNull()
    vm.form.company_subtype = 'type_d'
    await flushPromises()
    expect(vm.categorySuggestion).toBeNull()
  })

  it('项目类型为 IPO 且场景为常规时提示 IPO 场景，但不改表单值', async () => {
    const vm = await mountWith({ client_name: '某公司', project_type: 'ipo', scenario: 'normal' })
    expect(vm.scenarioSuggestion).toBe(true)
    expect(vm.form.scenario).toBe('normal')
    vm.form.scenario = 'ipo'
    await flushPromises()
    expect(vm.scenarioSuggestion).toBe(false)
  })

  it('旧向导数据没有场景 / 分类键时按常规年审、未填写回填', async () => {
    const vm = await mountWith({ client_name: '某公司' })
    expect(vm.form.scenario).toBe('normal')
    expect(vm.form.business_category).toBeNull()
  })

  it('新建项目默认常规年审、分类未填写', async () => {
    const vm = await mountWith(null)
    expect(vm.form.scenario).toBe('normal')
    expect(vm.form.business_category).toBeNull()
  })
})

describe('projectClassification 常量', () => {
  it('报告模板类型字母只对 A / B / C 给建议', () => {
    expect(categoryGroupFromSubtype('type_a')).toBe('A')
    expect(categoryGroupFromSubtype('TYPE_C')).toBe('C')
    expect(categoryGroupFromSubtype('type_d')).toBeNull()
    expect(categoryGroupFromSubtype(null)).toBeNull()
  })

  it('场景选项与后端登记值同序（后端 test_project_classification 另做跨语言对拍）', () => {
    expect(SCENARIO_OPTIONS.map((o) => o.value)).toEqual(
      ['normal', 'ipo', 'listed', 'refinancing', 'transfer', 'restructure', 'fraud_response'])
  })
})
