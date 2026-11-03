/**
 * WpAccountAbsenceHint — 试算表里找不到本底稿科目时的不阻断提示
 *
 * spec trim-followup-residual-findings-closure R1.2：只在 accounts_found 明确为 false 时出现；
 * true / null / 父组件没传都不提示（含 Boolean 的 prop 未传会被 Vue 转成 false，组件显式默认 null）；
 * 「去程序裁剪」按循环深链到裁剪页。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

import WpAccountAbsenceHint from '../WpAccountAbsenceHint.vue'

const BASE = {
  projectId: 'proj-1',
  cycle: 'H',
  accountName: '油气资产',
  usualScope: '油气资产（CAS 27 石油天然气开采）通常只在油气开采企业核算',
}

function mountHint(extra: Record<string, unknown> = {}) {
  return mount(WpAccountAbsenceHint, { props: { ...BASE, ...extra }, global: { plugins: [ElementPlus] } })
}

describe('WpAccountAbsenceHint', () => {
  beforeEach(() => {
    push.mockReset()
  })

  it('accounts_found=false 时提示科目名与通常适用的业务', () => {
    const w = mountHint({ accountsFound: false })
    expect(w.find('.wp-account-absence-hint').exists()).toBe(true)
    expect(w.text()).toContain('试算表中未找到「油气资产」科目')
    expect(w.text()).toContain('通常只在油气开采企业核算')
    expect(w.text()).toContain('程序裁剪')
  })

  it.each([
    ['true', { accountsFound: true }],
    ['null（尚未知道）', { accountsFound: null }],
    ['父组件没传', {}],
  ])('%s 不提示', (_label, extra) => {
    expect(mountHint(extra).find('.wp-account-absence-hint').exists()).toBe(false)
  })

  it('「去程序裁剪」按循环深链到裁剪页', async () => {
    const w = mountHint({ accountsFound: false, cycle: 'M' })
    await w.find('.wp-account-absence-hint__trim').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'ProcedureTrimming', params: { projectId: 'proj-1' }, query: { cycle: 'M' } })
  })
})
