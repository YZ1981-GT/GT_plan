/**
 * K12-4 营业外收入 / K13-4 营业外支出检查（宿主自管状态）接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * - 挂载时已有数据：检查行读得出来（原来行号计数器声明在读入侦听之后，立即执行的读入落进暂时性死区，被 catch 吞掉 ⇒ 一行都读不出）；
 * - 抽凭两次不重复，一个对方科目一行（后端配对），`_gt` 随行落库；金额取样本自己那一栏；
 * - 年审阶段预审行改不了、删不掉，保存时按读入版本写回。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import K12TabNonOperatingCheck from '../k12/core/K12TabNonOperatingCheck.vue'
import K13TabNonOperatingCheck from '../k13/core/K13TabNonOperatingCheck.vue'
import { paired, resetVoucherFillMocks, sample, VK } from '../composables/__tests__/voucherFillHostHarness'

const EL_TAGS = [
  'ElAlert', 'ElButton', 'ElCard', 'ElCheckbox', 'ElCheckboxGroup', 'ElCollapse', 'ElCollapseItem', 'ElDialog', 'ElIcon',
  'ElInput', 'ElInputNumber', 'ElOption', 'ElSelect', 'ElSwitch', 'ElTable', 'ElTableColumn', 'ElTag', 'ElTooltip', 'ElUpload',
]
const emptyStub = defineComponent({ render: () => null })

const CASES = [
  { name: 'K12-4 营业外收入', comp: K12TabNonOperatingCheck, key: 'K12-4-check-rows', amount: 'creditAmount', side: 'creditAmount' },
  { name: 'K13-4 营业外支出', comp: K13TabNonOperatingCheck, key: 'K13-4-check-rows', amount: 'debitAmount', side: 'debitAmount' },
] as const

beforeEach(resetVoucherFillMocks)

describe.each(CASES)('$name：抽凭回填走共享函数', ({ comp, key, amount }) => {
  function mountWith(rows: unknown[]) {
    const allResponses = new Map<string, any>([[key, { item_id: key, remark: JSON.stringify(rows) }]])
    const wrapper = shallowMount(comp as any, {
      props: { wpId: 'wp-1', projectId: 'proj-1', allResponses, year: 2025, isReadonly: false },
      global: { components: Object.fromEntries(EL_TAGS.map(n => [n, emptyStub])) },
    })
    const vm = wrapper.vm as any
    const saved = () => {
      const calls = (wrapper.emitted('save') ?? []).filter(c => c[0] === key)
      return calls.length ? JSON.parse(String(calls[calls.length - 1][1])) : null
    }
    return { wrapper, vm, saved }
  }

  it('挂载时已有数据：检查行读得出来（行号计数器不在暂时性死区）', async () => {
    const { vm } = mountWith([{ rowKey: 'old', voucherNo: '0001', [amount]: 50, indexNo: 'A-1' }])
    await flushPromises()
    expect(vm.checkRows.map((r: any) => [r.rowKey, r.voucherNo, r.indexNo])).toEqual([['old', '0001', 'A-1']])
  })

  it('抽凭两次不重复；一个对方科目一行，金额取样本自己那一栏；`_gt` 随行落库', async () => {
    const { vm, saved } = mountWith([])
    await flushPromises()
    const own = amount === 'creditAmount'
      ? { debitAmount: null, creditAmount: '300.00' }
      : { debitAmount: '300.00', creditAmount: null }
    const batch = [sample('fp-1', { ...own, pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) })]
    await vm.handleVoucherFilled({ samples: batch, phase: 'final', batchId: 'b-1' })
    await vm.handleVoucherFilled({ samples: batch, phase: 'final', batchId: 'b-2' })
    expect(vm.checkRows.map((r: any) => [r.voucherNo, r.offsetAccount, r[amount]])).toEqual([['0012', '1002', 200], ['0012', '6111', 100]])
    expect(saved()[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine'] })
  })

  it('年审阶段预审行只读：改不了、删不掉，保存时按读入版本写回', async () => {
    const prelim = { rowKey: 'p1', voucherNo: '0012', indexNo: '已核对', _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const { vm, saved } = mountWith([prelim])
    await flushPromises()
    await vm.voucherFill.ready()
    vm.updateCell('p1', 'indexNo', '改了')
    vm.removeRow('p1')
    expect(vm.checkRows.map((r: any) => [r.rowKey, r.indexNo])).toEqual([['p1', '已核对']])
    vm.checkRows[0].indexNo = '被改了'
    await vm.handleVoucherFilled({ samples: [sample('fp-9', { voucherNo: '0020' })], phase: 'final', batchId: 'b-1' })
    expect(saved()[0]).toMatchObject({ rowKey: 'p1', indexNo: '已核对' })
  })
})
