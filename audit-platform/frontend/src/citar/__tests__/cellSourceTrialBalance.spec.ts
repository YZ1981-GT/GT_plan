/**
 * 试算平衡表悬浮来源（spec citar-cell-source-hover R4）：金额格带来源键、悬停取来源并补操作提示、原生 title 去掉；
 * 调整分录页 ?locate=分录组 定位（R2）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), query: {} as Record<string, string>, goSegment: vi.fn() }))

vi.mock('@/services/apiProxy', () => ({ api: { get: h.get, put: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: h.query, params: { projectId: 'p1' } }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useManualEditPermission', () => ({
  MANUAL_EDIT_DENIED_TIP: '无权修改', useManualEditPermission: () => ({ canManualEdit: ref(true) }),
}))
vi.mock('@/composables/useProjectRole', () => ({ useProjectRole: () => ({ projectCan: () => true }) }))
vi.mock('../useCitarProject', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useCitarProject: () => ({ projectId: ref('p1'), year: ref(2025), yearLoading: ref(false), entityName: ref('甲公司'), goSegment: h.goSegment }),
}))

import CitarTrialBalance from '../screens/CitarTrialBalance.vue'

const viewRow = {
  standard_account_code: '1002', account_name: '银行存款', opening_balance: '50000', period_debit: '15000', period_credit: '8000',
  adjustment_debit: '500', adjustment_credit: '0', wp_adjustment: '0', adjusted_closing_balance: '57500',
  audited_amount: '57500', direction: 'debit',
}
const source = {
  kind: 'adjustment', title: '借方审计调整', value: '500', items: [
    { label: '调整分录 AJE-1', detail: null, amount: '500', sign: '1', link: { page: 'adjustments', group: 'g-1' } },
  ], more: 0, linear: true, total: '500', diff: null, notes: [], issue: null, manual: null, rule_text: null,
}

beforeEach(() => {
  h.get.mockReset()
  h.goSegment.mockReset()
  for (const k of Object.keys(h.query)) delete h.query[k]
  Element.prototype.scrollIntoView = vi.fn()
  h.get.mockImplementation((url: string) => {
    if (url.includes('standard-view')) return Promise.resolve([viewRow])
    if (url.includes('cell-sources/trial-balance')) return Promise.resolve({ year: 2025, cells: { '1002:adj_debit': source }, notices: [] })
    if (url.includes('adjustments')) return Promise.resolve({ items: [] })
    return Promise.resolve([])
  })
})

afterEach(() => vi.useRealTimers())

describe('试算平衡表悬浮来源', () => {
  it('金额格带来源键、没有原生 title；悬停弹出卡片，点链接跳到调整分录该组', async () => {
    const w = mount(CitarTrialBalance, { attachTo: document.body, global: { stubs: { CitarTbAdjustDialog: true } } })
    await flushPromises()
    const cell = w.find('[data-src="1002:adj_debit"]')
    expect(cell.exists()).toBe(true)
    expect(w.findAll('tbody td').some(td => td.attributes('title'))).toBe(false)
    vi.useFakeTimers()
    await cell.trigger('mouseover')
    vi.advanceTimersByTime(400)
    vi.useRealTimers()
    await flushPromises()
    expect(h.get.mock.calls.some(([u]) => String(u).includes('cell-sources/trial-balance'))).toBe(true)
    const card = w.find('.src-card')
    expect(card.text()).toContain('1002 银行存款 · 借方审计调整')
    expect(card.text()).toContain('调整分录 AJE-1')
    await card.find('.src-card__link').trigger('click')
    expect(h.goSegment).toHaveBeenCalledWith('adjustments', { locate: 'g-1' })
    w.unmount()
  })

  it('审定数格的卡片带「点击修改」提示；期初调整格本地说明', async () => {
    h.get.mockImplementation((url: string) => {
      if (url.includes('standard-view')) return Promise.resolve([viewRow])
      if (url.includes('cell-sources/trial-balance')) {
        return Promise.resolve({ year: 2025, cells: { '1002:adj_closing': { ...source, kind: 'derived', title: '调整后期末' } }, notices: [] })
      }
      return Promise.resolve({ items: [] })
    })
    const w = mount(CitarTrialBalance, { attachTo: document.body, global: { stubs: { CitarTbAdjustDialog: true } } })
    await flushPromises()
    vi.useFakeTimers()
    await w.find('[data-src="1002:adj_closing"]').trigger('mouseover')
    vi.advanceTimersByTime(400)
    vi.useRealTimers()
    await flushPromises()
    expect(w.find('.src-card__hint').text()).toContain('点击修改')
    vi.useFakeTimers()
    await w.find('[data-src="1002:opening_adj"]').trigger('mouseover')
    vi.advanceTimersByTime(400)
    vi.useRealTimers()
    await flushPromises()
    expect(w.find('.src-card').text()).toContain('平台暂无期初调整分录')
    w.unmount()
  })
})
