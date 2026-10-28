/**
 * useK1VoucherCheck（J1-8 / K1-12 / K2-6 / K3-7 / K4-4 / K5-7 / K7-5 / K8-8 / K9-8 / M1-6 / M2-5 / N2 共用）接入共享回填函数
 * （spec voucher-identity-writeback-and-audit-phase 任务 13）。通用五条用例见 voucherFillHostHarness（改行入口是逐笔核对弹窗的
 * updateVoucherRow）；另验：本期 / 期后两张表 —— 抽凭进宿主所选的表（不再经引擎的 phase 传）、挂凭导入按 periodEnd 分表；
 * 没有期后表的宿主（不传 periodEnd）挂凭一律进本期；J1 的第三张表（期后支付）与按借贷栏分区的挂凭规则；删行不删预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useK1VoucherCheck, type K1VoucherRow } from '../useK1VoucherCheck'
import { sideTableOf } from '../shared/voucherCheckFill'
import { paired, resetVoucherFillMocks, sample, voucherFillHostCases, VK, type HostInstance } from './voucherFillHostHarness'

const ITEM = 'K1-12-voucher-check'
type K1Api = ReturnType<typeof useK1VoucherCheck>
const no = (r: K1VoucherRow) => r.voucherNo

/** seed 行带 `table: 'post'` 的进期后表，其余进本期发生额表 */
function make(seedIn?: unknown[], opts: { periodEnd?: string | null } = { periodEnd: '2025-12-31' }): HostInstance<K1VoucherRow> & { api: K1Api } {
  const seed = seedIn as Array<Record<string, unknown>> | undefined
  const allResponses = ref(new Map<string, any>())
  const put = (json: string) => allResponses.value.set(ITEM, { item_id: ITEM, conclusion: null, remark: json })
  if (seed) {
    put(JSON.stringify({
      occurrenceRows: seed.filter(r => r.table !== 'post'),
      postCollectionRows: seed.filter(r => r.table === 'post'),
    }))
  }
  let saves = 0
  const api: K1Api = useK1VoucherCheck({
    allResponses, projectId: 'proj-1', readonly: false, periodEnd: opts.periodEnd ?? undefined,
    persist: () => {
      saves += 1
      put(api.serialize())
    },
  })
  api.load()
  const saved = () => JSON.parse(String(allResponses.value.get(ITEM)?.remark ?? '{}'))
  return {
    api,
    rows: () => [...api.occurrenceRows.value, ...api.postCollectionRows.value],
    stored: () => [...(saved().occurrenceRows ?? []), ...(saved().postCollectionRows ?? [])],
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('useK1VoucherCheck：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<K1VoucherRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, [r.offsetAccount, r.offsetSubAccount].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => { (inst.api as unknown as K1Api).updateVoucherRow('occurrence', id, { remark: value }) },
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, supportingDoc: '合同', checks: [true, false, false, false, false] },
    oldRowKept: { supportingDoc: '合同', checks: [true, false, false, false, false] },
  })

  it('两张表：抽凭进所选的表、替换只动所选的表；挂凭导入按期末日分表，已在某张表的分录留在原处', async () => {
    const inst = make()
    const occ = () => inst.api.occurrenceRows.value.map(no)
    const post = () => inst.api.postCollectionRows.value.map(no)
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, 'occurrence')
    await inst.api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0101', voucherDate: '2026-01-05' })], phase: 'final', batchId: 'b-2' }, 'post')
    await inst.api.onAttachImported([
      sample('fp-1'),
      sample('fp-3', { voucherNo: '0102', voucherDate: '2026-02-01' }),
      sample('fp-4', { voucherNo: '0013', voucherDate: '2025-06-30' }),
    ])
    expect([occ(), post()]).toEqual([['0012', '0013'], ['0101', '0102']])
    await inst.api.onEngineFilled({ samples: [sample('fp-5', { voucherNo: '0103', voucherDate: '2026-03-01' })], phase: 'final', fillMode: 'replace', batchId: 'b-3' }, 'post')
    expect([occ(), post()]).toEqual([['0012', '0013'], ['0102', '0103']])
  })

  it('没有期后表的宿主（不传 periodEnd）：挂凭导入一律进本期发生额', async () => {
    const inst = make(undefined, { periodEnd: null })
    await inst.api.onAttachImported([sample('fp-1', { voucherDate: '2026-02-01' })])
    expect(inst.api.occurrenceRows.value.map(no)).toEqual(['0012'])
    expect(inst.api.postCollectionRows.value).toEqual([])
  })

  it('年审阶段预审行：删行不删、逐笔核对改不了；对方明细名称与编码相同时不重复写', async () => {
    const prelim = { id: 'p1', voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const inst = make([prelim, { id: 'p2', voucherNo: '0099', table: 'post', _gt: { vk: VK, lfp: 'fp-9', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }])
    await inst.api.voucherFillReady()
    inst.api.removeOccurrenceRow('p1')
    inst.api.removePostCollectionRow('p2')
    expect(inst.rows().map(r => r.id)).toEqual(['p1', 'p2'])
    expect(inst.api.updateVoucherRow('occurrence', 'p1', { remark: '改了' })).toBe(false)
    await inst.api.onEngineFilled({
      samples: [sample('fp-3', { voucherNo: '0030', pairing: paired(['1002', '1002', '1000.00']) })],
      phase: 'final', batchId: 'b-1',
    })
    const added = inst.api.occurrenceRows.value.find(r => r.voucherNo === '0030')!
    expect([added.offsetAccount, added.offsetSubAccount]).toEqual(['1002', ''])
  })

  it('J1：期后支付是宿主自管的第三张表；挂凭导入按借贷栏与日期分三区，一起去重、撤销', async () => {
    const allResponses = ref(new Map<string, any>())
    const postPeriodRows = ref<K1VoucherRow[]>([])
    const end = '2025-12-31'
    let saves = 0
    const api = useK1VoucherCheck({
      allResponses, itemId: 'J1-8-voucher-check', projectId: 'proj-1', readonly: false,
      persist: () => { saves += 1 },
      extraTables: { postPeriod: postPeriodRows },
      attachTableOf: item => (String(item.sample.voucherDate ?? '') > end ? 'postPeriod' : sideTableOf(item) === 'credit' ? 'occurrence' : 'post'),
    })
    api.load()
    await api.onAttachImported([
      sample('fp-c', { voucherNo: '0001', debitAmount: null, creditAmount: '500.00', pairing: paired(['6602', '管理费用', '500.00']) }),
      sample('fp-d', { voucherNo: '0002', pairing: paired(['1002', '银行存款', '1000.00']) }),
      sample('fp-p', { voucherNo: '0003', voucherDate: '2026-01-10' }),
    ])
    expect([api.occurrenceRows.value.map(no), api.postCollectionRows.value.map(no), postPeriodRows.value.map(no)])
      .toEqual([['0001'], ['0002'], ['0003']])
    // 抽凭进所选的区（期后支付）；已在某区的分录不重复
    await api.onEngineFilled({ samples: [sample('fp-p', { voucherNo: '0003', voucherDate: '2026-01-10' }), sample('fp-q', { voucherNo: '0004', voucherDate: '2026-01-20' })], phase: 'final', batchId: 'b-1' }, 'postPeriod')
    expect(postPeriodRows.value.map(no)).toEqual(['0003', '0004'])
    // 宿主自管表保存前同样过一遍（预审行按读入版本写回）
    expect(api.guardPersist(postPeriodRows.value, 'postPeriod').map(no)).toEqual(['0003', '0004'])
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(postPeriodRows.value.map(no)).toEqual(['0003'])
    expect(saves).toBeGreaterThan(0)
  })
})
