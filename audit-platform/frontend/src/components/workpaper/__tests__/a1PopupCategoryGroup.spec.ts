/**
 * A1-11 签发流转 / A1-12 重大事项核查弹窗：组别读项目详情下发的 project_classification
 * （spec trim-followup-residual-findings-closure R3）。
 *
 * 原状（可打红）：两处按 `projectInfo.business_category === 'A'` / `=== 'C'` 精确比较 ⇒ A1~A8 项目在 A1-11 只显示
 * 项目经理 + 合伙人两行（漏掉独立复核合伙人 / EQCR），A1-12 标签显示「A1类」且颜色按非 A 类。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { ProjectClassification } from '@/types/projectClassification'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue([]), put: vi.fn().mockResolvedValue({}) } }))

import WpPopupSigning from '../WpPopupSigning.vue'
import WpPopupChecklist from '../WpPopupChecklist.vue'

function pc(code: string | null, group: 'A' | 'B' | 'C', defaulted = false): ProjectClassification {
  return {
    category_code: code, category_group: group, defaulted, scenario: 'normal', scenario_label: '常规年审',
    is_ipo: false, is_refinancing: false, is_capital_market: false, tags: [],
  }
}

async function mountSigning(projectInfo: Record<string, unknown>) {
  const wrapper = mount(WpPopupSigning, { props: { wpCode: 'A1-11', projectInfo }, global: { plugins: [ElementPlus] } })
  await flushPromises()
  return wrapper
}

describe('A1-11 签发流转：按组别显示必签行', () => {
  it.each([
    [pc('A1', 'A'), ['A1-11-sign-pm', 'A1-11-sign-partner', 'A1-11-sign-irp', 'A1-11-sign-eqcr']],
    [pc('A', 'A'), ['A1-11-sign-pm', 'A1-11-sign-partner', 'A1-11-sign-irp', 'A1-11-sign-eqcr']],
    [pc('B2', 'B'), ['A1-11-sign-pm', 'A1-11-sign-partner']],
  ])('%j', async (classification, ids) => {
    const wrapper = await mountSigning({ business_category: classification.category_code, project_classification: classification })
    expect((wrapper.vm as any).visibleRows.map((r: { id: string }) => r.id)).toEqual(ids)
    expect(wrapper.find('.signing-alert').exists()).toBe(classification.category_group !== 'A')
  })

  it('分类未填写：按 C 类，提示写明', async () => {
    const wrapper = await mountSigning({ project_classification: pc(null, 'C', true) })
    expect((wrapper.vm as any).visibleRows).toHaveLength(2)
    expect(wrapper.find('.signing-alert').text()).toContain('本项目为C 类（分类未填写），仅需项目经理和合伙人签字')
  })

  it('不再按分类原值判：只有 business_category 没有 project_classification 时不当 A 类', async () => {
    const wrapper = await mountSigning({ business_category: 'A' })
    expect((wrapper.vm as any).visibleRows).toHaveLength(2)
  })
})

describe('A1-12 重大事项核查：分类标签与 C 类提示', () => {
  async function mountChecklist(projectInfo: Record<string, unknown>) {
    const wrapper = mount(WpPopupChecklist, { props: { wpCode: 'A1-12', projectInfo }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    return wrapper
  }

  it.each([
    [pc('A1', 'A'), 'A 类（A1）', 'danger', false],
    [pc('B', 'B'), 'B 类', 'warning', false],
    [pc(null, 'C', true), 'C 类（分类未填写）', 'info', true],
  ] as const)('%j → 「%s」', async (classification, text, type, hint) => {
    const wrapper = await mountChecklist({ project_classification: classification })
    const tag = wrapper.find('.checklist-header .el-tag')
    expect(tag.text()).toBe(text)
    expect(tag.classes()).toContain(`el-tag--${type}`)
    expect((wrapper.vm as any).showNotApplicableHint).toBe(hint)
  })
})
