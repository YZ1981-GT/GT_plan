/**
 * 凭证检查行的两个展示组件（spec voucher-identity-writeback-and-audit-phase 任务 9，需求 4.8）
 * - VoucherRowMetaTag：阶段 / 来源 / 配对状态 / 存续核对标签，旧行按「手工」；
 * - VoucherPairingCell：配上的显示对方科目；「多科目」点开时按凭证键现取整张凭证（只取一次），
 *   分录过多的不取、给到序时账的入口；凭证键对应多张凭证时如实提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('../../composables/useAttachedVouchers', () => ({ fetchVoucherLines: vi.fn() }))

import { fetchVoucherLines } from '../../composables/useAttachedVouchers'
import VoucherRowMetaTag from '../VoucherRowMetaTag.vue'
import VoucherPairingCell from '../VoucherPairingCell.vue'

const fetchLines = vi.mocked(fetchVoucherLines)
const VK = JSON.stringify(['2025', '0101', '2025-01-20', 'FY', '0012'])
const RouterLink = { props: ['to'], template: '<a class="router-link"><slot /></a>' }

function metaRow(gt: Record<string, unknown> | null) {
  return gt ? { voucherNo: '0012', _gt: { vk: VK, lfp: 'fp', b: null, cp: null, ...gt } } : { voucherNo: '0012' }
}

const tagText = (row: unknown, locked = false) =>
  mount(VoucherRowMetaTag, { props: { row, locked }, global: { plugins: [ElementPlus] } }).text()

describe('VoucherRowMetaTag', () => {
  it('阶段、来源（可并列）、非配对、存续核对状态', () => {
    const text = tagText(metaRow({ ph: 'preliminary', src: ['engine', 'attach'], pr: 'multi', sv: { status: 'deleted' } }), true)
    expect(text).toContain('预审')
    expect(text).toContain('抽凭 + 挂凭')
    expect(text).toContain('非配对')
    expect(text).toContain('凭证已删除')
    expect(text).toContain('只读')
  })

  it('配上的不显示配对标签；已确认的存续结果写「已确认」；没有 _gt 的旧行按手工', () => {
    const paired = tagText(metaRow({ ph: 'final', src: ['engine'], pr: 'paired', sv: { status: 'modified', ackAt: '2026-10-27' } }))
    expect(paired).toContain('年审')
    expect(paired).not.toContain('非配对')
    expect(paired).toContain('分录已改（已确认）')
    expect(tagText(metaRow(null))).toBe('手工')
    expect(tagText(metaRow({ ph: null, src: [], pr: null }))).toContain('阶段未标')
  })
})

function cell(props: { row: unknown; account?: string; accountName?: string; accountCode?: string; year?: number | null }) {
  return mount(VoucherPairingCell, {
    props: { projectId: 'p-1', year: 2025, ...props },
    global: { plugins: [ElementPlus], stubs: { RouterLink, 'router-link': RouterLink } },
    attachTo: document.body,
  })
}

describe('VoucherPairingCell', () => {
  beforeEach(() => {
    fetchLines.mockReset()
    document.body.innerHTML = ''
  })

  it('配上的行只显示对方科目，不取凭证', () => {
    const w = cell({ row: metaRow({ pr: 'paired' }), account: '1002', accountName: '银行存款' })
    expect(w.text()).toBe('1002 银行存款')
    expect(fetchLines).not.toHaveBeenCalled()
  })

  it('「多科目」点开时按行上的凭证键取整张凭证，只取一次', async () => {
    fetchLines.mockResolvedValue([
      { account_code: '6602.01', account_name: '管理费用', debit_amount: '3680', credit_amount: null, summary: '工资' },
      { account_code: '1002', account_name: '银行存款', debit_amount: null, credit_amount: '3680', summary: '工资' },
    ])
    const w = cell({ row: metaRow({ pr: 'multi' }), account: '多科目' })
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    // 凭证键整组带上（含主体 0101）：一套账两个主体同日同号同凭证字时只按日期 + 凭证字 + 号会命中两张
    expect(fetchLines).toHaveBeenCalledWith('p-1', 2025, '0012', '2025-01-20', 'FY', '0101')
    expect(document.body.textContent).toContain('管理费用')
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    expect(fetchLines).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('项目没填审计年度（year = null）：按凭证键上的年度取，不拿 null 去查', async () => {
    fetchLines.mockResolvedValue([])
    const w = cell({ row: metaRow({ pr: 'multi' }), account: '多科目', year: null })
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    expect(fetchLines).toHaveBeenCalledWith('p-1', 2025, '0012', '2025-01-20', 'FY', '0101')
    w.unmount()
  })

  it('分录过多的大凭证不取分录，给到序时账查看的入口', async () => {
    const w = cell({ row: metaRow({ pr: 'large' }), account: '多科目', accountCode: '2211' })
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    expect(fetchLines).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('到序时账查看')
    w.unmount()
  })

  it('到序时账的年度取凭证键上的，不用宿主的兜底年度', async () => {
    const w = cell({ row: metaRow({ pr: 'large' }), account: '多科目', accountCode: '2211', year: 0 })
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    expect(w.findComponent(RouterLink).props('to')).toMatchObject({ query: { year: '2025', account: '2211' } })
    w.unmount()
  })

  it('凭证键对应多张凭证（409）时如实提示，不合并分录', async () => {
    fetchLines.mockRejectedValue({ response: { status: 409, data: { detail: { error_code: 'VOUCHER_KEY_AMBIGUOUS', message: 'x', candidates: [] } } } })
    const w = cell({ row: metaRow({ pr: 'multi' }), account: '多科目' })
    await w.find('[data-testid="voucher-pairing-multi"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('对应多张凭证')
    w.unmount()
  })
})
