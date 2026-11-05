/**
 * 序时账逐级穿透（不弹窗）：凭证号 → 凭证级列表（按凭证日期 + 凭证号定位）；科目编码 → 科目级（含下级）；
 * 「返回上一级」/ 路径回到原级别、原页码并高亮点过的行；换级别会重挂载页面，穿透历史须跨挂载保留。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.get, put: vi.fn(), post: vi.fn() } }))
vi.mock('@/composables/useManualEditPermission', () => ({
  MANUAL_EDIT_DENIED_TIP: '无权修改', useManualEditPermission: () => ({ canManualEdit: ref(false) }),
}))
vi.mock('../citarLedgerEdits', () => ({
  editLedgerEntry: vi.fn(), restoreLedgerRow: vi.fn(), fetchManualEdits: vi.fn().mockResolvedValue([]),
}))

import CitarJournalTab from '../components/CitarJournalTab.vue'
import { resetDrillMemory, type JournalView } from '../journalDrillMemory'

const VOUCHER_NO = '100000000#45688'

const row = (over: Record<string, unknown>) => ({
  id: 'j1', voucher_date: '2025-03-01', voucher_no: VOUCHER_NO, summary: '收货款', account_code: '100201',
  account_name: '工行', debit_amount: 100, credit_amount: null, extra_fields: {}, ...over,
})

let voucherLines: Record<string, unknown>[] = []

function calls(part: string) {
  return h.get.mock.calls.filter(([url]) => String(url).includes(part))
}

/** 表里第 col 列（从 1 起）可点的那个值 */
function drill(w: ReturnType<typeof mount>, text: string, col: 3 | 5) {
  const btn = w.findAll(`.sheet-table tbody td:nth-child(${col}) button.citar-drill`).find(b => b.text() === text)
  if (!btn) throw new Error(`找不到可点的「${text}」`)
  return btn
}

const backBtn = (w: ReturnType<typeof mount>) => w.findAll('.citar-toolbar button').find(b => b.text() === '← 返回上一级')
const lastView = (w: ReturnType<typeof mount>) => w.emitted('update:view')?.at(-1)?.[0] as JournalView | undefined

beforeEach(() => {
  h.get.mockReset()
  resetDrillMemory()
  voucherLines = [
    row({ id: 'v1', account_code: '100201', account_name: '工行', debit_amount: 100, credit_amount: null }),
    row({ id: 'j1', account_code: '1122', account_name: '应收账款', debit_amount: null, credit_amount: 100 }),
  ]
  h.get.mockImplementation((url: string) => {
    if (url.includes('cell-sources')) return Promise.resolve({ cells: {} })
    if (url.includes('/ledger/entries-all')) {
      return Promise.resolve({
        items: [row({ id: 'j1' }), row({ id: 'j2', account_code: '1122', account_name: '应收账款', debit_amount: null, credit_amount: 100 })],
        total: 2,
      })
    }
    if (url.includes('/ledger/entries/')) return Promise.resolve({ items: [row({ id: 'j9', account_code: '112201' })], total: 1, has_more: false })
    if (url.includes('/ledger/voucher/')) return Promise.resolve(voucherLines)
    return Promise.resolve(null)
  })
})

async function mountTab(props: { accountCode?: string; voucherNo?: string; voucherDate?: string } = {}) {
  const w = mount(CitarJournalTab, {
    props: { projectId: 'p1', year: 2025, entityName: '甲', ...props },
    attachTo: document.body,
  })
  await flushPromises()
  return w
}

describe('序时账：凭证号穿透到凭证级', () => {
  it('不弹窗：列表换成这张凭证的分录（按日期 + 凭证号，# 编码进路径），带合计与路径，点进来的行高亮', async () => {
    const w = await mountTab()
    await drill(w, VOUCHER_NO, 3).trigger('click')
    await flushPromises()

    const [url, cfg] = calls('/ledger/voucher/')[0]
    expect(url).toBe(`/api/projects/p1/ledger/voucher/${encodeURIComponent(VOUCHER_NO)}`)
    expect(cfg.params).toEqual({ year: 2025, voucher_date: '2025-03-01' })
    expect(lastView(w)).toEqual({ kind: 'voucher', no: VOUCHER_NO, date: '2025-03-01' })

    expect(document.querySelector('.el-dialog, .el-overlay')).toBeNull()
    expect(w.find('.citar-toolbar__count').text()).toBe(`凭证 ${VOUCHER_NO}（2025-03-01），共 2 条分录`)
    expect(w.find('.citar-journal__crumbs').text().replace(/\s+/g, '')).toBe(`全部科目›凭证${VOUCHER_NO}（2025-03-01）`)
    expect(w.findAll('.sheet-table tbody tr')).toHaveLength(2)
    expect(w.find('tr[data-journal-row="j1"]').classes()).toContain('citar-located')
    expect(w.find('tfoot').text()).toContain('合计（借贷平衡）')
    expect(w.find('tfoot').text()).toContain('100.00')
    // 凭证级不分页，凭证号不可再点，科目编码可点
    expect(w.find('.citar-pager').exists()).toBe(false)
    expect(w.findAll('.sheet-table tbody td:nth-child(3) button').length).toBe(0)
    expect(w.findAll('.sheet-table tbody td:nth-child(5) button.citar-drill').length).toBe(2)
    w.unmount()
  })

  it('借贷不平时写明差额与方向', async () => {
    voucherLines = [
      row({ id: 'v1', debit_amount: 100.1, credit_amount: null }),
      row({ id: 'v2', account_code: '1122', debit_amount: null, credit_amount: 90 }),
    ]
    const w = await mountTab()
    await drill(w, VOUCHER_NO, 3).trigger('click')
    await flushPromises()
    expect(w.find('tfoot').text()).toContain('合计（借贷不平）')
    expect(w.find('.citar-journal__unbalanced').text()).toContain('借贷不平：借方比贷方多 10.10 元')
    w.unmount()
  })

  it('地址栏直接带凭证（刷新 / 分享链接）：按凭证级读', async () => {
    const w = await mountTab({ voucherNo: VOUCHER_NO, voucherDate: '2025-03-01' })
    expect(calls('/ledger/voucher/')).toHaveLength(1)
    expect(calls('/ledger/entries-all')).toHaveLength(0)
    expect(w.find('.citar-toolbar__count').text()).toContain(`凭证 ${VOUCHER_NO}（2025-03-01）`)
    w.unmount()
  })
})

describe('序时账：科目编码穿透与逐级返回', () => {
  it('全部 → 凭证 → 科目，返回上一级回到凭证、再返回回到全部分录并高亮点过的行', async () => {
    const w = await mountTab()
    await drill(w, VOUCHER_NO, 3).trigger('click')
    await flushPromises()
    await drill(w, '1122', 5).trigger('click')
    await flushPromises()

    expect(calls('/ledger/entries/')[0][0]).toBe('/api/projects/p1/ledger/entries/1122*')
    expect(lastView(w)).toEqual({ kind: 'account', code: '1122' })
    expect(w.find('.citar-toolbar__count').text()).toContain('科目 1122 及下级')
    expect(w.findAll('.citar-journal__crumbs button').map(b => b.text())).toEqual(['全部科目', `凭证 ${VOUCHER_NO}（2025-03-01）`])

    await backBtn(w)!.trigger('click')
    await flushPromises()
    expect(lastView(w)).toEqual({ kind: 'voucher', no: VOUCHER_NO, date: '2025-03-01' })
    expect(w.find('.citar-toolbar__count').text()).toContain(`凭证 ${VOUCHER_NO}`)

    await backBtn(w)!.trigger('click')
    await flushPromises()
    expect(lastView(w)).toEqual({ kind: 'account', code: '' })
    expect(w.find('.citar-toolbar__count').text()).toContain('全部科目')
    expect(w.find('tr[data-journal-row="j1"]').classes()).toContain('citar-located')
    expect(backBtn(w)).toBeUndefined()
    expect(w.find('.citar-journal__crumbs').exists()).toBe(false)
    w.unmount()
  })

  it('路径上点最前一级：直接跳回，后面各级丢弃', async () => {
    const w = await mountTab()
    await drill(w, VOUCHER_NO, 3).trigger('click')
    await flushPromises()
    await drill(w, '1122', 5).trigger('click')
    await flushPromises()
    await w.findAll('.citar-journal__crumbs button')[0].trigger('click')
    await flushPromises()
    expect(w.find('.citar-toolbar__count').text()).toContain('全部科目')
    expect(w.find('tr[data-journal-row="j1"]').classes()).toContain('citar-located')
    expect(backBtn(w)).toBeUndefined()
    w.unmount()
  })

  it('当前科目级本身不可再点；下级科目可点', async () => {
    const w = await mountTab({ accountCode: '1122' })
    expect(w.find('tr[data-journal-row="j9"] td:nth-child(5) button.citar-drill').exists()).toBe(true)
    await w.setProps({ accountCode: '112201' })
    await flushPromises()
    expect(w.find('tr[data-journal-row="j9"] td:nth-child(5) button').exists()).toBe(false)
    w.unmount()
  })
})

// 换级别会改地址栏，布局按 fullPath 重挂载本页：穿透历史须跨挂载保留
describe('序时账：穿透历史跨重挂载', () => {
  it('进入凭证后按新地址重挂载：路径还在、点进来的行高亮；返回后按原地址重挂载回到原位置', async () => {
    const w1 = await mountTab()
    await drill(w1, VOUCHER_NO, 3).trigger('click')
    await flushPromises()
    w1.unmount()

    const w2 = await mountTab({ voucherNo: VOUCHER_NO, voucherDate: '2025-03-01' })
    expect(w2.find('tr[data-journal-row="j1"]').classes()).toContain('citar-located')
    expect(backBtn(w2)).toBeDefined()
    await backBtn(w2)!.trigger('click')
    await flushPromises()
    expect(lastView(w2)).toEqual({ kind: 'account', code: '' })
    w2.unmount()

    const before = calls('/ledger/entries-all').length
    const w3 = await mountTab()
    expect(calls('/ledger/entries-all').length).toBe(before + 1)
    expect(calls('/ledger/entries-all').at(-1)![1].params).toMatchObject({ page: 1 })
    expect(w3.find('tr[data-journal-row="j1"]').classes()).toContain('citar-located')
    expect(backBtn(w3)).toBeUndefined()
    w3.unmount()

    // 待恢复位置只用一次：再进来不再高亮
    const w4 = await mountTab()
    expect(w4.find('tr.citar-located').exists()).toBe(false)
    w4.unmount()
  })

  it('从别的入口带着不同级别进来：作废旧的穿透历史', async () => {
    const w1 = await mountTab()
    await drill(w1, '1122', 5).trigger('click')
    await flushPromises()
    w1.unmount()

    const w2 = await mountTab({ accountCode: '6601' })
    expect(backBtn(w2)).toBeUndefined()
    w2.unmount()

    const w3 = await mountTab({ accountCode: '1122' })
    expect(backBtn(w3)).toBeUndefined()
    w3.unmount()
  })
})
