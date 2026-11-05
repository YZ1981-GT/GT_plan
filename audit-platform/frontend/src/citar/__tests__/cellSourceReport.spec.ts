/**
 * 审定报表悬浮来源（spec citar-cell-source-hover R5）：金额格带来源键与操作提示（data-hint，无原生 title）、
 * 悬停取 mode=audited 的来源、点 ROW 链接在本页切页签并定位；?tab=&locate= 进页定位。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), apiGet: vi.fn(), query: {} as Record<string, string>, goSegment: vi.fn() }))

vi.mock('@/services/auditPlatformApi', () => ({ getReport: h.get }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, put: vi.fn(), post: vi.fn() } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: h.query, params: { projectId: 'p1' } }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useManualEditPermission', () => ({
  MANUAL_EDIT_DENIED_TIP: '无权修改', useManualEditPermission: () => ({ canManualEdit: ref(true) }),
}))
vi.mock('../useCitarReportGenerate', () => ({
  useCitarReportGenerate: () => ({ generating: ref(false), prerequisite: ref(null), generate: vi.fn() }),
}))
vi.mock('../useCitarProject', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useCitarProject: () => ({ projectId: ref('p1'), year: ref(2025), yearLoading: ref(false), entityName: ref('甲公司'), goSegment: h.goSegment }),
}))

import CitarAuditedReports from '../screens/CitarAuditedReports.vue'

const row = (code: string, name: string, cur: string) => ({
  row_code: code, row_name: name, current_period_amount: cur, prior_period_amount: '0', indent_level: 1, is_total_row: false,
})
const BS = [row('BS-001', '货币资金', '500'), row('BS-002', '应收账款', '300')]
const IS = [row('IS-001', '营业收入', '1000')]
const total = {
  kind: 'formula', title: "公式：ROW('IS-001')", value: '500', items: [
    { label: 'IS-001 营业收入', detail: null, amount: '1000', sign: '1', link: { page: 'reports', report_type: 'income_statement', code: 'IS-001' } },
  ], more: 0, linear: false, total: null, diff: null, notes: [], issue: null, manual: null, rule_text: null,
}

beforeEach(() => {
  h.get.mockReset()
  h.apiGet.mockReset()
  h.goSegment.mockReset()
  for (const k of Object.keys(h.query)) delete h.query[k]
  Element.prototype.scrollIntoView = vi.fn()
  h.get.mockImplementation((_p: string, _y: number, t: string) => Promise.resolve(t === 'income_statement' ? IS : BS))
  h.apiGet.mockResolvedValue({ year: 2025, cells: { 'BS-001:current': total }, notices: [] })
})
afterEach(() => vi.useRealTimers())

async function hover(w: ReturnType<typeof mount>, key: string) {
  vi.useFakeTimers()
  await w.find(`[data-src="${key}"]`).trigger('mouseover')
  vi.advanceTimersByTime(400)
  vi.useRealTimers()
  await flushPromises()
}

describe('审定报表悬浮来源', () => {
  it('格子带来源键与提示、无原生 title；悬停取审定口径来源；点行链接在本页切到利润表并定位', async () => {
    const w = mount(CitarAuditedReports, { attachTo: document.body })
    await flushPromises()
    const cell = w.find('[data-src="BS-001:current"]')
    expect(cell.exists()).toBe(true)
    expect(cell.attributes('title')).toBeUndefined()
    expect(cell.attributes('data-hint')).toBe('点击修改')
    await hover(w, 'BS-001:current')
    expect(h.apiGet).toHaveBeenCalledWith('/api/projects/p1/cell-sources/report/balance_sheet',
      expect.objectContaining({ params: { year: 2025, mode: 'audited' } }))
    expect(w.find('.src-card').text()).toContain('BS-001 货币资金 · 期末数')
    expect(w.find('.src-card__hint').text()).toBe('点击修改')
    await w.find('.src-card__link').trigger('click')
    await flushPromises()
    expect(h.goSegment).not.toHaveBeenCalled()
    expect(w.find('.aud-tab--active').text()).toBe('利润表')
    expect(w.find('tr[data-locate="IS-001"]').classes()).toContain('citar-located')
    w.unmount()
  })

  it('?tab=&locate= 进页即切页签并高亮该行', async () => {
    h.query.tab = 'income_statement'
    h.query.locate = 'IS-001'
    const w = mount(CitarAuditedReports, { attachTo: document.body })
    await flushPromises()
    expect(w.find('.aud-tab--active').text()).toBe('利润表')
    expect(w.find('tr[data-locate="IS-001"]').classes()).toContain('citar-located')
    w.unmount()
  })
})
