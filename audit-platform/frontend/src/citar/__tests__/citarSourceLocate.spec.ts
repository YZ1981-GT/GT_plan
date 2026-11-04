/**
 * 源头页按 ?locate= 定位到行（spec citar-fs-issue-source-locate R2）：科目余额表清筛选后高亮并滚动；
 * 试算平衡表零余额行切到底稿取数余额表；找不到时提示；sourceLink 换算。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), info: vi.fn(), query: {} as Record<string, string> }))

vi.mock('@/services/apiProxy', () => ({ api: { get: h.get, put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  ElMessage: { info: h.info, success: vi.fn(), warning: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: h.query, params: { projectId: 'p1' } }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useManualEditPermission', () => ({
  MANUAL_EDIT_DENIED_TIP: '无权修改', useManualEditPermission: () => ({ canManualEdit: ref(false) }),
}))
vi.mock('../citarLedgerEdits', () => ({
  editBalanceRow: vi.fn(), restoreLedgerRow: vi.fn(), parseMoneyInput: Number, fetchManualEdits: vi.fn().mockResolvedValue([]),
}))
vi.mock('../useCitarProject', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useCitarProject: () => ({ projectId: ref('p1'), year: ref(2025), yearLoading: ref(false), entityName: ref('甲公司'), goSegment: vi.fn() }),
}))

import CitarBalanceTab from '../components/CitarBalanceTab.vue'
import CitarTrialBalance from '../screens/CitarTrialBalance.vue'
import { sourceLink } from '../fsIssueSources'

const balanceRow = (code: string, name: string, closing: number) => ({
  id: `id-${code}`, account_code: code, account_name: name, level: 1, opening_balance: 0, debit_amount: 0,
  credit_amount: 0, closing_balance: Math.abs(closing), opening_direction: 'debit', closing_direction: closing < 0 ? 'credit' : 'debit',
})

const viewRow = (code: string, name: string, audited: string | null, closing = '0') => ({
  standard_account_code: code, account_name: name, opening_balance: '0', period_debit: '0', period_credit: '0',
  adjustment_debit: '0', adjustment_credit: '0', wp_adjustment: '0', adjusted_closing_balance: closing,
  audited_amount: audited, direction: 'debit',
})

let scroll: ReturnType<typeof vi.fn>

beforeEach(() => {
  h.get.mockReset()
  h.info.mockReset()
  for (const k of Object.keys(h.query)) delete h.query[k]
  scroll = vi.fn()
  Element.prototype.scrollIntoView = scroll
})

describe('科目余额表 ?locate=', () => {
  it('清掉关键字后高亮该客户科目行并滚动；只定位一次', async () => {
    h.get.mockResolvedValue([balanceRow('1002', '银行存款', 500), balanceRow('5801.0', '以前年度损益调整', -50)])
    const w = mount(CitarBalanceTab, { props: { projectId: 'p1', year: 2025, entityName: '甲公司' }, attachTo: document.body })
    await flushPromises()
    await w.find('input.citar-search').setValue('1002')
    expect(w.findAll('tbody tr').length).toBe(1)
    await w.setProps({ locateCode: '5801' })
    await flushPromises()
    const tr = w.find('tr[data-locate="5801"]')
    expect(tr.exists()).toBe(true)
    expect(tr.classes()).toContain('citar-located')
    expect(w.find('tr[data-locate="1002"]').classes()).not.toContain('citar-located')
    expect(scroll.mock.contexts.at(-1)).toBe(tr.element)
    // 重读数据（如保存后）不再滚动
    const n = scroll.mock.calls.length
    await w.setProps({ year: 2026 })
    await flushPromises()
    expect(h.get.mock.calls.length).toBeGreaterThan(1)
    expect(scroll.mock.calls.length).toBe(n)
    expect(w.find('tr[data-locate="5801"]').classes()).toContain('citar-located')
    w.unmount()
  })

  it('找不到该科目时提示原因', async () => {
    h.get.mockResolvedValue([balanceRow('1002', '银行存款', 500)])
    const w = mount(CitarBalanceTab, { props: { projectId: 'p1', year: 2025, entityName: '甲公司', locateCode: '9999' } })
    await flushPromises()
    expect(h.info).toHaveBeenCalledWith('科目余额表里没有科目 9999')
    expect(w.find('.citar-located').exists()).toBe(false)
    w.unmount()
  })
})

describe('试算平衡表 ?locate=', () => {
  it('零余额科目切到底稿取数余额表再定位', async () => {
    h.query.locate = '1221'
    h.get.mockImplementation((url: string) => {
      if (url.includes('standard-view')) return Promise.resolve([viewRow('1002', '银行存款', '500', '500'), viewRow('1221', '其他应收款', null)])
      return Promise.resolve([])
    })
    const w = mount(CitarTrialBalance, { attachTo: document.body, global: { stubs: { CitarTbAdjustDialog: true } } })
    await flushPromises()
    await nextTick()
    expect(w.find('.aud-tab--active').text()).toBe('底稿取数余额表')
    const tr = w.find('tr[data-locate="1221"]')
    expect(tr.classes()).toContain('citar-located')
    expect(scroll.mock.contexts.at(-1)).toBe(tr.element)
    w.unmount()
  })

  it('有数科目留在审定科目余额表', async () => {
    h.query.locate = '1002'
    h.get.mockImplementation((url: string) =>
      Promise.resolve(url.includes('standard-view') ? [viewRow('1002', '银行存款', '500', '500')] : []),
    )
    const w = mount(CitarTrialBalance, { attachTo: document.body, global: { stubs: { CitarTbAdjustDialog: true } } })
    await flushPromises()
    expect(w.find('.aud-tab--active').text()).toBe('审定科目余额表')
    expect(w.find('tr[data-locate="1002"]').classes()).toContain('citar-located')
    w.unmount()
  })
})

describe('sourceLink', () => {
  it('页 + 编码 → 菜单与查询参数', () => {
    expect(sourceLink('balance', '5801')).toEqual({ segment: 'ledger-query', query: { tab: 'balance', locate: '5801' } })
    expect(sourceLink('journal', '5801')).toEqual({ segment: 'ledger-query', query: { tab: 'journal', account: '5801' } })
    expect(sourceLink('mapping', '1221')).toEqual({ segment: 'mapping', query: { tab: 'standard', locate: '1221' } })
    expect(sourceLink('trial_balance', '6901')).toEqual({ segment: 'trial-balance', query: { locate: '6901' } })
    expect(sourceLink('trial_balance')).toEqual({ segment: 'trial-balance', query: {} })
    expect(sourceLink('ledger_import')).toEqual({ segment: 'ledger-import', query: {} })
    expect(sourceLink('statement')).toBeNull()
    expect(sourceLink(null)).toBeNull()
  })
})
