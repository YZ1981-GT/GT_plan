import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ mark: vi.fn(), revoke: vi.fn(), fetchLines: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => ({
  markAdjustmentClientBooked: api.mark,
  revokeAdjustmentClientBooking: api.revoke,
}))
vi.mock('@/components/workpaper/composables/useAttachedVouchers', () => ({ fetchVoucherLines: api.fetchLines }))

import AdjustmentCentralStatusTag from '../AdjustmentCentralStatusTag.vue'
import ClientBookingDialog from '../ClientBookingDialog.vue'
import ClientBookingSuggestionBar from '../ClientBookingSuggestionBar.vue'
import ClientBookingVoucherPicker from '../ClientBookingVoucherPicker.vue'
import { pickedFromLines, resolveSuggestionEntry, voucherLookupFailureText } from '../clientBookingVoucher'

const mounted: VueWrapper[] = []
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
})
beforeEach(() => vi.clearAllMocks())

const row: any = {
  entry_group_id: 'g1', adjustment_no: 'AJE-001', adjustment_type: 'aje',
  review_status: 'approved', description: '客户已入账', audit_phase: 'preliminary',
  line_items: [
    { standard_account_code: '1122', account_name: '应收账款', debit_amount: 100, credit_amount: 0 },
    { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 0, credit_amount: 100 },
  ],
}
const candidate: any = {
  voucher_key: '["2025","001","2025-12-31","记","0008"]',
  label: '2025-12-31 记-0008', voucher_date: '2025-12-31', voucher_type: '记',
  voucher_no: '0008', company_code: '001', summary: '客户入账调整', distance_days: 2,
  matches: [{ adjustment_line_no: 1 }, { adjustment_line_no: 2 }],
}

const LINE_KEY = '["2025","001","2025-12-31","记","0009"]'
const LINES = [
  { voucher_key: LINE_KEY, company_code: '001', voucher_date: '2025-12-31', voucher_type: '记', voucher_no: '0009',
    account_code: '1122', account_name: '应收账款', debit_amount: '100.00', credit_amount: null, summary: '客户补记坏账' },
  { voucher_key: LINE_KEY, company_code: '001', voucher_date: '2025-12-31', voucher_type: '记', voucher_no: '0009',
    account_code: '6702', account_name: '信用减值损失', debit_amount: null, credit_amount: '100.00', summary: '' },
]
const AMBIGUOUS = { response: { status: 409, data: { detail: {
  error_code: 'VOUCHER_KEY_AMBIGUOUS', message: '对应多张凭证', truncated: false, candidates: [
    { voucher_key: '["2025","001","2025-01-07","FY","0003"]', company_code: '001', voucher_date: '2025-01-07',
      voucher_type: 'FY', voucher_no: '0003', line_count: 2, debit_total: '100.00', summary: '付款' },
    { voucher_key: '["2025","001","2025-01-07","ZZ","0003"]', company_code: '001', voucher_date: '2025-01-07',
      voucher_type: 'ZZ', voucher_no: '0003', line_count: 4, debit_total: '200.00', summary: '转账' },
  ],
} } } }

function mountDialog() {
  const wrapper = mount(ClientBookingDialog, {
    props: { projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus] }, attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>('button')]
  .find((item) => item.textContent?.trim() === text)!

async function lookupVoucher(no: string) {
  const input = document.querySelector<HTMLInputElement>('input[data-testid="booking-picker-no"]')!
  input.value = no
  input.dispatchEvent(new Event('input'))
  await flushPromises()
  button('查找').click()
  await flushPromises()
}

describe('客户已入账界面', () => {
  it('共享状态标签同时显示集中复核与客户入账生效态', () => {
    const wrapper = mount(AdjustmentCentralStatusTag, {
      props: { status: { review_status: 'approved', adjustment_no: 'AJE-001', client_booking: { status: 'booked', effective: true, voucher_keys: [] } } },
      global: { plugins: [ElementPlus] },
    })
    mounted.push(wrapper)
    expect(wrapper.text()).toContain('集中登记：已批准 · AJE-001')
    expect(wrapper.text()).toContain('客户已入账')
  })

  it('只把用户选中的精确 VoucherKey 提交，系统不自动标记', async () => {
    api.mark.mockResolvedValue({})
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [candidate], false)
    await flushPromises()
    expect(document.body.textContent).toContain('平台不会自动标记')
    button('确认已入账').click()
    await flushPromises()
    expect(api.mark).toHaveBeenCalledWith('p1', 'g1', {
      year: 2025, voucher_keys: [candidate.voucher_key], note: undefined,
    })
    expect(wrapper.emitted('updated')).toBeTruthy()
  })

  it('撤销标记必须填原因', async () => {
    api.revoke.mockResolvedValue({})
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open({ ...row, client_booking: { status: 'booked', effective: true } }, [], true)
    await flushPromises()
    button('确认撤销').click()
    await flushPromises()
    expect(api.revoke).not.toHaveBeenCalled()
    const textarea = document.querySelector<HTMLTextAreaElement>('textarea[placeholder^="说明客户凭证"]')!
    textarea.value = '客户凭证已冲销'
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()
    button('确认撤销').click()
    await flushPromises()
    expect(api.revoke).toHaveBeenCalledWith('p1', 'g1', { year: 2025, reason: '客户凭证已冲销' })
  })

  it('没有候选时不再要粘贴凭证键：按凭证号查到分录、加入后提交它的凭证键', async () => {
    api.mark.mockResolvedValue({})
    api.fetchLines.mockResolvedValue(LINES)
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [], false)
    await flushPromises()
    expect(document.querySelector('textarea[placeholder*="2025"]')).toBeNull()
    await lookupVoucher('0009')
    expect(api.fetchLines).toHaveBeenCalledWith('p1', 2025, '0009', null)
    const preview = document.querySelector('[data-testid="booking-picker-preview"]')!
    expect(preview.textContent).toContain('2025-12-31 记-0009')
    expect(preview.textContent).toContain('应收账款')
    expect(preview.textContent).toContain('2 行分录，借方合计 100.00')
    button('加入').click()
    await flushPromises()
    expect(document.querySelector('[data-testid="booking-picker-selected"]')!.textContent).toContain('客户补记坏账')
    button('确认已入账').click()
    await flushPromises()
    expect(api.mark).toHaveBeenCalledWith('p1', 'g1', { year: 2025, voucher_keys: [LINE_KEY], note: undefined })
  })

  it('同号多张凭证：列候选，选一张按完整凭证键取分录', async () => {
    api.fetchLines.mockRejectedValueOnce(AMBIGUOUS).mockResolvedValueOnce(LINES)
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [], false)
    await flushPromises()
    await lookupVoucher('0003')
    const list = document.querySelector('[data-testid="booking-picker-candidates"]')!
    expect(list.textContent).toContain('在当前账套有 2 张凭证')
    expect(list.textContent).toContain('ZZ-0003')
    ;[...list.querySelectorAll<HTMLButtonElement>('button')].filter(b => b.textContent?.trim() === '选这张')[1].click()
    await flushPromises()
    expect(api.fetchLines).toHaveBeenLastCalledWith('p1', 2025, '0003', '2025-01-07', 'ZZ', '001')
    expect(document.querySelector('[data-testid="booking-picker-candidates"]')).toBeNull()
    expect(document.querySelector('[data-testid="booking-picker-preview"]')).not.toBeNull()
  })

  it('当前账套没有这张凭证（空结果或 404）时说明，不出加入按钮', async () => {
    api.fetchLines.mockResolvedValueOnce([]).mockRejectedValueOnce({ response: { status: 404, data: {} } })
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [], false)
    await flushPromises()
    for (let i = 0; i < 2; i++) {
      await lookupVoucher('0404')
      expect(document.querySelector('[data-testid="booking-picker-error"]')!.textContent).toContain('当前账套没有这张凭证')
      expect(document.querySelector('[data-testid="booking-picker-add"]')).toBeNull()
    }
  })

  it('已选可移除；一张都没选时提示且不提交', async () => {
    api.fetchLines.mockResolvedValue(LINES)
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [], false)
    await flushPromises()
    await lookupVoucher('0009')
    button('加入').click()
    await flushPromises()
    button('移除').click()
    await flushPromises()
    expect(document.querySelector('[data-testid="booking-picker-selected"]')).toBeNull()
    button('确认已入账').click()
    await flushPromises()
    expect(api.mark).not.toHaveBeenCalled()
  })

  it('自动候选都不对：切换按凭证号查找，提交用查到的凭证而不是候选', async () => {
    api.mark.mockResolvedValue({})
    api.fetchLines.mockResolvedValue(LINES)
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [candidate], false)
    await flushPromises()
    button('都不是，按凭证号查找').click()
    await flushPromises()
    await lookupVoucher('0009')
    button('加入').click()
    await flushPromises()
    button('确认已入账').click()
    await flushPromises()
    expect(api.mark).toHaveBeenCalledWith('p1', 'g1', { year: 2025, voucher_keys: [LINE_KEY], note: undefined })
  })

  it('标记弹窗说明对试算表的影响（与后端生效判定一致）', async () => {
    const wrapper = mountDialog()
    ;(wrapper.vm as any).open(row, [candidate], false)
    await flushPromises()
    expect(document.body.textContent).toContain('当前账套中找到全部所选凭证时，本组 AJE 不再计入试算表调整')
    expect(document.body.textContent).toContain('账套重导后找不到这些凭证，本组 AJE 自动恢复计入')
  })
})

describe('客户入账建议条', () => {
  const SUGGESTIONS: any[] = [
    { entry_group_id: 'g1', adjustment_no: 'AJE-001', description: '补提坏账', audit_phase: 'preliminary', candidates: [candidate] },
    { entry_group_id: 'g2', adjustment_no: 'AJE-007', description: '', audit_phase: 'final', candidates: [candidate, candidate] },
  ]

  function mountBar(canEdit: boolean) {
    const wrapper = mount(ClientBookingSuggestionBar, {
      props: { suggestions: SUGGESTIONS, canEdit }, global: { plugins: [ElementPlus] },
    })
    mounted.push(wrapper)
    return wrapper
  }

  it('有编辑权限：展开列出全部建议，每条单独确认（不只第一条）', async () => {
    const wrapper = mountBar(true)
    expect(wrapper.text()).toContain('检测到 2 组调整疑似已由客户入账')
    await wrapper.get('[data-testid="booking-suggestion-toggle"]').trigger('click')
    const list = wrapper.get('[data-testid="booking-suggestion-list"]')
    expect(list.text()).toContain('AJE-001')
    expect(list.text()).toContain('补提坏账')
    expect(list.text()).toContain('AJE-007')
    expect(list.text()).toContain('无摘要')
    expect(list.text()).toContain('候选凭证 2 张')
    const confirms = list.findAll('button').filter(b => b.text().trim() === '确认')
    expect(confirms).toHaveLength(2)
    await confirms[1].trigger('click')
    expect(wrapper.emitted('review')?.[0]?.[0]).toMatchObject({ entry_group_id: 'g2' })
  })

  it('没有编辑权限：只提示请有权限的成员确认，没有任何按钮', () => {
    const wrapper = mountBar(false)
    expect(wrapper.text()).toContain('请有编辑权限的成员确认')
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
})

describe('建议对应的分录组：不在当前页也能打开', () => {
  const onPage = [{ entry_group_id: 'g1', adjustment_no: 'AJE-001' }]

  it('当前页有就直接用，不取数', async () => {
    const fetchFocused = vi.fn()
    expect(await resolveSuggestionEntry('g1', onPage, fetchFocused)).toBe(onPage[0])
    expect(fetchFocused).not.toHaveBeenCalled()
  })

  it('不在当前页：按分录组取它所在页；取回别的分录（已删除或不在本年度）为 null；取数失败为 undefined', async () => {
    const target = { entry_group_id: 'g9', adjustment_no: 'AJE-099' }
    const fetchFocused = vi.fn().mockResolvedValueOnce({ items: [target] })
      .mockResolvedValueOnce({ items: [{ entry_group_id: 'g1' }] })
      .mockRejectedValueOnce(new Error('boom'))
    expect(await resolveSuggestionEntry('g9', onPage, fetchFocused)).toBe(target)
    expect(fetchFocused).toHaveBeenCalledWith('g9')
    expect(await resolveSuggestionEntry('g9', onPage, fetchFocused)).toBeNull()
    expect(await resolveSuggestionEntry('g9', onPage, fetchFocused)).toBeUndefined()
  })

  it('调整分录页接线：按 focus 取每页 1 条；建议条权限与菜单「标记客户已入账」同一判定', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const page = readFileSync(resolve(process.cwd(), 'src/views/Adjustments.vue'), 'utf8')
    expect(page).toMatch(/resolveSuggestionEntry\(suggestion\.entry_group_id,[\s\S]{0,160}page_size: 1, focus_entry_group_id: groupId/)
    expect(page).toMatch(/<ClientBookingSuggestionBar[^>]*:can-edit="perms\.writable && perms\.edit"/)
    const table = readFileSync(resolve(process.cwd(), 'src/components/adjustment/AdjustmentHallTable.vue'), 'utf8')
    expect(table).toMatch(/props\.perms\.writable && booked\)[\s\S]{0,120}client-booking-revoke/)
    expect(table).toMatch(/props\.perms\.writable && !booked[\s\S]{0,160}action: 'client-booking'/)
  })
})


describe('客户入账凭证选择（纯函数与年度门）', () => {
  it('分录 → 已选条目：借方合计按分录求和；没带凭证键时按行补', () => {
    const item = pickedFromLines([{ ...LINES[0], voucher_key: undefined }, LINES[1], { ...LINES[0], debit_amount: '0.50' }], 2025)
    expect(item).toMatchObject({
      voucher_key: LINE_KEY, label: '记-0009', voucher_date: '2025-12-31', line_count: 3,
      debit_total: '100.50', summary: '客户补记坏账',
    })
    expect(pickedFromLines([], 2025)).toBeNull()
  })

  it('查找失败的原因按状态与后端说明给出', () => {
    expect(voucherLookupFailureText({ response: { status: 404 } })).toBe('当前账套没有这张凭证')
    expect(voucherLookupFailureText({ response: { status: 403 } })).toBe('没有本项目的查看权限')
    expect(voucherLookupFailureText({ response: { status: 400, data: { detail: { message: '凭证日期格式不对' } } } }))
      .toBe('凭证日期格式不对')
    expect(voucherLookupFailureText(new Error('Network Error'))).toBe('网络连接失败，请检查网络')
  })

  it('项目未填审计年度：查找禁用并说明', () => {
    const wrapper = mount(ClientBookingVoucherPicker, {
      props: { projectId: 'p1', year: null, modelValue: [] }, global: { plugins: [ElementPlus] },
    })
    mounted.push(wrapper)
    expect(wrapper.text()).toContain('项目未填审计年度')
    expect(wrapper.get('[data-testid="booking-picker-lookup"]').attributes('disabled')).toBeDefined()
  })
})

it('所有使用集中同步的底稿调整 Tab 共用客户入账状态组件', async () => {
  const { readFileSync, readdirSync, statSync } = await import('node:fs')
  const { resolve, join } = await import('node:path')
  const root = resolve(process.cwd(), 'src/components/workpaper')
  const files: string[] = []
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name)
      if (statSync(path).isDirectory()) walk(path)
      else if (name.endsWith('.vue')) files.push(path)
    }
  }
  walk(root)
  const consumers = files.filter((path) => readFileSync(path, 'utf8').includes('useAdjustmentCentralSync'))
  expect(consumers.length).toBeGreaterThan(70)
  const offenders = consumers.filter((path) => {
    const text = readFileSync(path, 'utf8')
    return !text.includes('<AdjustmentCentralStatusTag') || text.includes('CENTRAL_STATUS_LABELS')
  })
  expect(offenders).toEqual([])
})
