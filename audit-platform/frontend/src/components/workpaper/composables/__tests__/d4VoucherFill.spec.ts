/**
 * D4-14 营业收入发生检查（穿行测试）接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 一个样本一个事项；抽凭两次、挂凭导入两次都不重复；`_gt` 随事项 JSON 落库（d4:save-items）；
 * - 映射：收入类贷方发生额优先、对方科目来自后端配对、引擎标异常 → 事项异常；
 * - 「替换本阶段抽凭行」只删本阶段抽凭填入的事项，已录入核对内容的先确认（取消则不动）；
 * - 撤销按批次删事项；年审阶段预审事项改、删都不生效，保存时按读入版本写回；
 * - 旧事项（没有 `_gt`）同号同日同金额：不再新增，补写 `_gt`。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, h, ref, type Ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useD4WalkthroughTest, mapSampleToTransaction } from '../useD4WalkthroughTest'
import type { SamplePairing } from '../shared/voucherCheckFill'

const KEY = 'D4-14-transactions'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '1122', account_name: '应收账款', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '销售收入',
  debitAmount: null, creditAmount: '1000.00', pairing: PAIRED, ...over,
})

const wrappers: VueWrapper[] = []
const saved: unknown[][] = []
const onSave = (e: Event) => { saved.push((e as CustomEvent).detail.items) }

function mk(seed?: unknown[]) {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set(KEY, { item_id: KEY, conclusion: null, remark: JSON.stringify(seed) })
  let api!: ReturnType<typeof useD4WalkthroughTest>
  wrappers.push(mount(defineComponent({
    setup() {
      api = useD4WalkthroughTest({
        wpId: ref('wp-4'), projectId: ref('proj-1'), allResponses: computed(() => allResponses.value), isReadonly: ref(false),
      })
      return () => h('div')
    },
  })))
  return { api, allResponses }
}

const stored = (allResponses: Ref<Map<string, any>>) => JSON.parse(String(allResponses.value.get(KEY)?.remark ?? '[]'))

beforeEach(() => {
  vi.clearAllMocks()
  saved.length = 0
  window.addEventListener('d4:save-items', onSave)
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

afterEach(() => {
  window.removeEventListener('d4:save-items', onSave)
  while (wrappers.length) wrappers.pop()?.unmount()
})

describe('D4-14 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；事项编号重排；`_gt` 随事项落库并立即保存', async () => {
    const { api, allResponses } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', creditAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' })
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    expect(api.transactions.value.map(t => [t.indexNo, t.voucher.number])).toEqual([['D4-14-1', '0007'], ['D4-14-2', '0008']])
    const rows = stored(allResponses)
    expect(rows[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    // 回填即保存（不等 2 秒防抖）
    expect(saved.length).toBeGreaterThanOrEqual(4)
    expect(JSON.parse(String((saved.at(-1) as any[]).find(i => i.item_id === KEY).remark))[1]._gt.lfp).toBe('fp-2')
  })

  it('映射：贷方发生额优先、对方科目来自后端配对、引擎标异常 → 事项异常', () => {
    const t = mapSampleToTransaction({
      sample: { ...sample('fp-1'), debitAmount: '5.00', abnormal: true } as never,
      meta: { vk: VK, lfp: 'fp-1', ph: 'final', b: null, src: ['engine'], pr: 'paired', cp: null },
      counterpartAccount: '1122', counterpartAccountName: '应收账款', debitAmount: '5.00', creditAmount: '1000.00',
      isMultiAccount: false,
    })
    expect([t.label, t.voucher.number, t.voucher.date, t.voucher.amount, t.other.description, t.isAnomalous])
      .toEqual(['0007', '0007', '2025-06-15', 1000, '对方科目：1122 应收账款', true])
  })

  it('「替换本阶段抽凭行」只删本阶段抽凭填入的事项；有核对内容的先确认，取消则不动', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' })
    api.updateDimension(api.transactions.value[0].id, 'contract', 'number', 'HT-01')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel' as never)
    const cancelled = await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(cancelled.cancelled).toBe(true)
    expect(api.transactions.value.map(t => t.voucher.number)).toEqual(['0007', '0008'])
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(api.transactions.value.map(t => [t.indexNo, t.voucher.number])).toEqual([['D4-14-1', '0009']])
  })

  it('撤销按批次删事项：同时来自挂凭的保留', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(api.transactions.value.map(t => [t.indexNo, t.voucher.number])).toEqual([['D4-14-1', '0008']])
    expect((api.transactions.value[0] as any)._gt).toMatchObject({ b: null, src: ['attach'] })
  })

  it('年审阶段预审事项只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const seed = mapSampleToTransaction({
      sample: sample('fp-1') as never,
      meta: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired', cp: null },
      counterpartAccount: '1122', counterpartAccountName: '应收账款', debitAmount: null, creditAmount: '1000.00', isMultiAccount: false,
    })
    const prelim = { ...seed, id: 't-p1', conclusion: '无异常', _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const { api, allResponses } = mk([prelim])
    await api.voucherFillReady()
    expect(api.isVoucherRowLocked(api.transactions.value[0])).toBe(true)
    api.updateDimension('t-p1', 'contract', 'number', 'HT-02')
    api.removeTransaction('t-p1')
    expect(api.transactions.value.map(t => [t.id, t.contract.number])).toEqual([['t-p1', '']])
    api.transactions.value[0].conclusion = '存在重大异常'
    api.updateAuditNote('说明')
    api.updateSamplingParams({ testPopulation: '全年' })
    expect(stored(allResponses)[0]).toMatchObject({ id: 't-p1', conclusion: '无异常' })
  })

  it('旧事项（没有 `_gt`）同号同日同金额：不再新增，补写 `_gt`，核对结论保留', async () => {
    const old = mapSampleToTransaction({
      sample: sample('x') as never, meta: { vk: null, lfp: null, ph: null, b: null, src: ['manual'], pr: null, cp: null },
      counterpartAccount: '', counterpartAccountName: '', debitAmount: null, creditAmount: '1000.00', isMultiAccount: false,
    })
    const { api } = mk([{ ...old, id: 't-old', conclusion: '无异常' }])
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    expect(api.transactions.value).toHaveLength(1)
    expect(api.transactions.value[0]).toMatchObject({ id: 't-old', conclusion: '无异常' })
    expect((api.transactions.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
