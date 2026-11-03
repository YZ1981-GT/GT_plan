/**
 * K4-4 其他流动负债 / K8-8 销售费用凭证检查：抽凭回填之后宿主自己的后处理（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * - K4-4：方法学是对象（原实现当字符串调 includes 抛 TypeError，其后关弹窗、保存都没执行）；只给本次抽凭填入的行标选取原因，
 *   手工行、挂凭行不标（原实现连它们一起标）。
 * - K8-8：回填后把方法学快照写进抽样参数（抽样方法 / 样本量 / 抽样过程），已填的抽样过程不覆盖。
 * - J1-8：期后支付是宿主自管的第三个区，交给共享回填函数一起管；挂凭导入按日期与借贷栏分三区，抽凭进所选的区；
 *   底稿数据没带年度时按本项目审计年度查挂凭（任务 14：原先用今年，新生成的底稿挂凭导入查到下一年、一条都拉不回来）。
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

import http from '@/utils/http'
import { useProjectStore } from '@/stores/project'
import J1TabGeneralCheck from '../j1/inspection/J1TabGeneralCheck.vue'
import K4TabCheck from '../k4/core/K4TabCheck.vue'
import K8TabSellingCheck from '../k8/inspection/K8TabSellingCheck.vue'
import { resetVoucherFillMocks, sample } from '../composables/__tests__/voucherFillHostHarness'

const EL_TAGS = [
  'ElAlert', 'ElButton', 'ElCard', 'ElCheckbox', 'ElCol', 'ElCollapse', 'ElCollapseItem', 'ElDialog', 'ElDivider', 'ElIcon',
  'ElInput', 'ElInputNumber', 'ElOption', 'ElRadio', 'ElRadioGroup', 'ElRow', 'ElSelect', 'ElSwitch', 'ElTable',
  'ElTableColumn', 'ElTag', 'ElTooltip', 'ElUpload',
]
const emptyStub = defineComponent({ render: () => null })
const ATTACHED_META = { vk: null, lfp: 'fp-9', ph: 'final', b: null, src: ['attach'], pr: null }

function mountWith(comp: unknown, key: string, stored: Record<string, unknown>) {
  const allResponses = new Map<string, any>([[key, { item_id: key, remark: JSON.stringify(stored) }]])
  const wrapper = shallowMount(comp as any, {
    props: { wpId: 'wp-1', projectId: 'proj-1', allResponses, year: 2025, isReadonly: false },
    global: { components: Object.fromEntries(EL_TAGS.map(n => [n, emptyStub])) },
  })
  const vm = wrapper.vm as any
  const saved = () => {
    const calls = (wrapper.emitted('save') ?? []).filter(c => c[0] === key)
    return calls.length ? JSON.parse(String((calls[calls.length - 1][1] as { remark: string }).remark)) : null
  }
  return { vm, saved }
}

beforeEach(resetVoucherFillMocks)

describe('K4-4：回填后按方法学标选取原因', () => {
  const seed = { occurrenceRows: [{ id: 'm1', voucherNo: '手-1' }, { id: 'a1', voucherNo: '0099', _gt: ATTACHED_META }] }

  it('MUS：只标本次抽凭填入的行（手工行、挂凭行不标），标完保存并关弹窗', async () => {
    const { vm, saved } = mountWith(K4TabCheck, 'K4-4-voucher-check', seed)
    await flushPromises()
    vm.samplingVisible = true
    await vm.onSamplesFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1', methodology: { samplingMethod: 'MUS', sampleSize: 1 } })
    expect(saved().occurrenceRows.map((r: any) => [r.voucherNo, r.selectionReason ?? ''])).toEqual([
      ['手-1', ''], ['0099', ''], ['0012', 'MUS高值'],
    ])
    expect(vm.samplingVisible).toBe(false)
  })

  it('非 MUS（含方法学缺失）：标「随机抽样」，不抛', async () => {
    const { vm, saved } = mountWith(K4TabCheck, 'K4-4-voucher-check', seed)
    await flushPromises()
    await vm.onSamplesFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1', methodology: { samplingMethod: 'random' } })
    await vm.onSamplesFilled({ samples: [sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-2' })
    expect(saved().occurrenceRows.map((r: any) => r.selectionReason ?? '')).toEqual(['', '', '随机抽样', '随机抽样'])
  })
})

describe('K8-8：回填后把方法学写进抽样参数', () => {
  it('抽样方法、样本量、抽样过程写进抽样参数并保存', async () => {
    const { vm, saved } = mountWith(K8TabSellingCheck, 'K8-8-voucher-check', {})
    await flushPromises()
    await vm.onSamplesFilled({
      samples: [sample('fp-1')], phase: 'final', batchId: 'b-1',
      methodology: { samplingMethod: 'MUS', sampleSize: 25, samplingInterval: 1000, suggestedSampleSize: 30 },
    })
    expect(saved().criteria).toMatchObject({ samplingMethod: 'MUS', sampleSize: 25, samplingProcess: '货币单元抽样间隔 1000，建议样本量 30' })
    expect(saved().occurrenceRows.map((r: any) => r.voucherNo)).toEqual(['0012'])
  })

  it('抽样过程已填：不覆盖', async () => {
    const { vm, saved } = mountWith(K8TabSellingCheck, 'K8-8-voucher-check', { criteria: { samplingProcess: '按金额分层后随机' } })
    await flushPromises()
    await vm.onSamplesFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1', methodology: { samplingMethod: 'MUS', samplingInterval: 500 } })
    expect(saved().criteria).toMatchObject({ samplingMethod: 'MUS', samplingProcess: '按金额分层后随机' })
  })
})

describe('J1-8：贷方计提 / 借方发放 / 期后支付三个区', () => {
  const no = (r: { voucherNo: string }) => r.voucherNo

  it('挂凭导入按日期与借贷栏分三区（导入两次不重复）；抽凭进所选的区', async () => {
    const wrapper = shallowMount(J1TabGeneralCheck as any, {
      props: { wpId: 'wp-1', projectId: 'proj-1', htmlData: { year: 2025 } },
      global: { components: Object.fromEntries(EL_TAGS.map(n => [n, emptyStub])) },
    })
    const vm = wrapper.vm as any
    await flushPromises()
    const batch = [
      sample('fp-c', { voucherNo: '0001', debitAmount: null, creditAmount: '100.00' }),
      sample('fp-d', { voucherNo: '0002' }),
      sample('fp-p', { voucherNo: '0003', voucherDate: '2026-01-10' }),
    ]
    await vm.onAttachImported(batch)
    await vm.onAttachImported(batch)
    expect([vm.occurrenceRows.map(no), vm.postCollectionRows.map(no), vm.postPeriodRows.map(no)]).toEqual([['0001'], ['0002'], ['0003']])
    vm.samplingTable = 'postPeriod'
    await vm.onSamplesFilled({ samples: [sample('fp-q', { voucherNo: '0004', voucherDate: '2026-01-20' })], phase: 'final', batchId: 'b-1' })
    expect(vm.postPeriodRows.map(no)).toEqual(['0003', '0004'])
    expect(vm.postPeriodRows[1]._gt).toMatchObject({ lfp: 'fp-q', b: 'b-1', src: ['engine'] })
  })

  it('底稿数据没带年度（按编码新生成的底稿）：挂凭计数按本项目审计年度查，不用今年兜底（任务 14 实测）', async () => {
    const store = useProjectStore()
    store.projectId = 'proj-1'
    store.auditYear = 2023 // 既不是今年也不是去年：两种日历兜底都得不出它
    store.year = 2023
    shallowMount(J1TabGeneralCheck as any, {
      props: { wpId: 'wp-1', projectId: 'proj-1', htmlData: {} },
      global: { components: Object.fromEntries(EL_TAGS.map(n => [n, emptyStub])) },
    })
    await flushPromises()
    const years = vi.mocked(http.get).mock.calls
      .filter(c => String(c[0]).includes('/ledger/sampled-vouchers'))
      .map(c => (c[1] as { params?: { year?: number } } | undefined)?.params?.year)
    expect(years).toEqual([2023])
  })
})
