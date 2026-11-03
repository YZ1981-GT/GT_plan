import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ mark: vi.fn(), revoke: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => ({
  markAdjustmentClientBooked: api.mark,
  revokeAdjustmentClientBooking: api.revoke,
}))

import AdjustmentCentralStatusTag from '../AdjustmentCentralStatusTag.vue'
import ClientBookingDialog from '../ClientBookingDialog.vue'
import ClientBookingSuggestionBar from '../ClientBookingSuggestionBar.vue'

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

  it('建议条点名候选组并由用户逐组确认', async () => {
    const wrapper = mount(ClientBookingSuggestionBar, {
      props: { suggestions: [{ entry_group_id: 'g1', adjustment_no: 'AJE-001', audit_phase: 'preliminary', candidates: [candidate] }] },
      global: { plugins: [ElementPlus] },
    })
    mounted.push(wrapper)
    expect(wrapper.text()).toContain('检测到 1 组调整疑似已由客户入账')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('review')?.[0]?.[0]).toMatchObject({ entry_group_id: 'g1' })
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
