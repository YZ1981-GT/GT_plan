/**
 * BasicInfoStep.vue —「集团架构」分组与「与上级关系」联动
 *
 * Spec: .kiro/specs/consol-tree-three-code-autobuild/ 任务 4.3（需求 1.1 / 1.3 / 1.5 / 1.7 / 2.3 / 2.4）
 * 1. 分组对单户与合并项目都显示；「合并类型」单选已移除
 * 2. 没有有效上级（空 / 就是本企业）⇒ 关系下拉置灰、值为空；有有效上级 ⇒ 必填、按名称默认
 * 3. 手动选择（或已保存的值）不被名称变化覆盖
 * 4. 上级 = 本企业不拒绝：保存前确认（三码相同改问「本企业即最终控制方」），取消不保存，同一组代码不重复问
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'

vi.mock('@/services/commonApi', () => ({
  fetchTemplateRecommendation: vi.fn().mockResolvedValue(null),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'
import { useWizardStore } from '@/stores/wizard'

const OWN = '91110000300000000G'
const PARENT = '911100002000000005'

const SelectStub = defineComponent({
  name: 'ElSelectStub',
  props: ['modelValue', 'disabled', 'placeholder'],
  emits: ['update:modelValue', 'change'],
  template: '<div class="sel-stub" :data-disabled="String(!!disabled)" :data-placeholder="placeholder"><slot /></div>',
})

const STUBS = {
  // 带 validate 的表单替身：规则校验交给 Element Plus 自己，这里只验联动与确认流程
  'el-form': defineComponent({
    template: '<form><slot /></form>',
    methods: { validate: () => Promise.resolve(true) },
  }),
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': true,
  'el-select': SelectStub,
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

function relationSelect(wrapper: VueWrapper<any>) {
  const found = wrapper.findAllComponents(SelectStub).find((c) => c.attributes('data-testid') === 'relation-select')
  if (!found) throw new Error('未找到「与上级关系」下拉')
  return found
}

async function fill(wrapper: VueWrapper<any>, patch: Record<string, unknown>) {
  Object.assign(wrapper.vm.form, patch)
  await nextTick()
  await nextTick()
}

describe('BasicInfoStep 集团架构', () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    setActivePinia(createPinia())
    confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  })

  afterEach(() => {
    confirmSpy.mockRestore()
  })

  it('单户与合并项目都显示集团架构分组，且不再有合并类型单选', async () => {
    const wrapper = mountStep()
    await flushPromises()
    expect(wrapper.find('[data-testid="group-section"]').exists()).toBe(true)
    await fill(wrapper, { report_scope: 'consolidated' })
    expect(wrapper.find('[data-testid="group-section"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('合并类型')
    expect(wrapper.text()).not.toContain('母子合并')
    expect(wrapper.text()).toContain('合并项目的下级企业按各项目的上级代码自动识别')
  })

  it('上级代码为空 ⇒ 下拉置灰、值为空；填了别家代码 ⇒ 可选并按名称默认', async () => {
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { client_name: '某某有限公司临港店', company_code: OWN })
    expect(relationSelect(wrapper).attributes('data-disabled')).toBe('true')
    expect(relationSelect(wrapper).attributes('data-placeholder')).toBe('先填写上级代码')
    expect(wrapper.vm.form.relation_to_parent).toBe('')

    await fill(wrapper, { parent_company_code: PARENT })
    expect(relationSelect(wrapper).attributes('data-disabled')).toBe('false')
    expect(wrapper.vm.form.relation_to_parent).toBe('branch')

    // 名称变化 ⇒ 默认值跟着变（用户还没手选）
    await fill(wrapper, { client_name: '某某科技有限公司' })
    expect(wrapper.vm.form.relation_to_parent).toBe('subsidiary')

    // 清空上级 ⇒ 关系清空
    await fill(wrapper, { parent_company_code: '' })
    expect(wrapper.vm.form.relation_to_parent).toBe('')
  })

  it('手动选择后改名称、清空再填上级都不覆盖', async () => {
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { client_name: '某某有限公司临港店', company_code: OWN, parent_company_code: PARENT })
    expect(wrapper.vm.form.relation_to_parent).toBe('branch')

    const sel = relationSelect(wrapper)
    sel.vm.$emit('update:modelValue', 'subsidiary')
    sel.vm.$emit('change', 'subsidiary')
    await nextTick()

    await fill(wrapper, { client_name: '某某集团有限公司上海分公司' })
    expect(wrapper.vm.form.relation_to_parent).toBe('subsidiary')
    await fill(wrapper, { parent_company_code: '' })
    await fill(wrapper, { parent_company_code: PARENT })
    expect(wrapper.vm.form.relation_to_parent).toBe('subsidiary')
  })

  it('已保存的关系视为手选；旧数据里的 consolidation_type 被丢弃', async () => {
    const store = useWizardStore()
    store.stepData.basic_info = {
      client_name: '某某有限公司临港店',
      company_code: OWN,
      parent_company_code: PARENT,
      relation_to_parent: 'subsidiary',
      consolidation_type: 'branch',
    } as any
    const wrapper = mountStep()
    await flushPromises()
    expect(wrapper.vm.form.relation_to_parent).toBe('subsidiary')
    await fill(wrapper, { client_name: '某某集团有限公司北京分公司' })
    expect(wrapper.vm.form.relation_to_parent).toBe('subsidiary')
    expect('consolidation_type' in wrapper.vm.form).toBe(false)
  })

  it('上级 = 本企业 ⇒ 下拉置灰并说明；保存前请用户确认本企业就是上级企业', async () => {
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { client_name: '某某有限公司临港店', company_code: OWN, parent_company_code: OWN })
    expect(relationSelect(wrapper).attributes('data-disabled')).toBe('true')
    expect(relationSelect(wrapper).attributes('data-placeholder')).toBe('本企业就是上级企业，无需选择')
    expect(wrapper.find('[data-testid="self-ref-hint"]').text()).toContain('表示本企业就是上级企业')
    expect(wrapper.vm.form.relation_to_parent).toBe('')

    const data = await wrapper.vm.validate()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(String(confirmSpy.mock.calls[0][0])).toContain('确认本企业就是上级企业')
    expect(data).not.toBeNull()
    expect(data.parent_company_code).toBe(OWN)
    expect(data.relation_to_parent).toBe('')

    // 同一组代码再次保存不重复问
    await wrapper.vm.validate()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
  })

  it('三个代码相同 ⇒ 确认「本企业即为最终控制方」', async () => {
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { company_code: OWN, parent_company_code: OWN, ultimate_company_code: OWN })
    expect(wrapper.find('[data-testid="self-ref-hint"]').text()).toContain('本企业即为最终控制方')

    await wrapper.vm.validate()
    expect(String(confirmSpy.mock.calls[0][0])).toContain('本企业即为最终控制方（集团总部或母公司）')
    expect((confirmSpy.mock.calls[0][2] as any).confirmButtonText).toBe('确认，本企业即最终控制方')
  })

  it('用户取消确认 ⇒ 不保存（validate 返回 null），下次仍会再问', async () => {
    confirmSpy.mockRejectedValueOnce('cancel')
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { company_code: OWN, parent_company_code: OWN })

    expect(await wrapper.vm.validate()).toBeNull()
    expect(await wrapper.vm.validate()).not.toBeNull()
    expect(confirmSpy).toHaveBeenCalledTimes(2)
  })

  it('从已保存数据回填的「上级 = 本企业」不再询问；改了代码组合才重新问', async () => {
    const store = useWizardStore()
    store.stepData.basic_info = {
      client_name: '某某集团有限公司', company_code: OWN, parent_company_code: OWN,
    } as any
    const wrapper = mountStep()
    await flushPromises()
    await wrapper.vm.validate()
    expect(confirmSpy).not.toHaveBeenCalled()

    await fill(wrapper, { ultimate_company_code: OWN })
    await wrapper.vm.validate()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
  })

  it('普通下级不弹确认', async () => {
    const wrapper = mountStep()
    await flushPromises()
    await fill(wrapper, { company_code: OWN, parent_company_code: PARENT })
    const data = await wrapper.vm.validate()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(data.relation_to_parent).toBe('subsidiary')
  })
})
