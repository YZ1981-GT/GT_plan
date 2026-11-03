/**
 * G5-12 长期应收款凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（宿主表格 v-model 原地改行，组合式函数唯一的改行入口是删行 ⇒ 用它验只读；
 * 原地改了内存靠保存时按读入版本写回兜底）；另验：本期发生额 / 期后两张表 —— 抽凭进宿主所选的表（samplingTarget，
 * 不再经引擎的 phase 传）、替换只动所选的表；挂凭导入按凭证日期分表、已在某张表的分录留在原处。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG5VoucherCheck, type G5VoucherRow } from '../useG5VoucherCheck'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ITEM = 'G5-12-voucher-check'
type G5Api = ReturnType<typeof useG5VoucherCheck>
const no = (r: G5VoucherRow) => r.voucherNo

/** seed 行带 `table: 'post'` 的进期后表，其余进本期发生额表 */
function make(seedIn?: unknown[]): HostInstance<G5VoucherRow> & { api: G5Api } {
  const seed = seedIn as Array<Record<string, unknown>> | undefined
  const allResponses = ref(new Map<string, any>())
  const put = (json: string) => allResponses.value.set(ITEM, { item_id: ITEM, conclusion: json, remark: json })
  if (seed) {
    put(JSON.stringify({
      occurrenceRows: seed.filter(r => r.table !== 'post'),
      postPeriodRows: seed.filter(r => r.table === 'post'),
    }))
  }
  let saves = 0
  // 宿主的 persist：serialize（年审阶段预审行按读入版本写回）后写进 allResponses
  const api: G5Api = useG5VoucherCheck({
    allResponses, projectId: 'proj-1', readonly: false, periodEnd: '2025-12-31',
    persist: () => {
      saves += 1
      put(api.serialize())
    },
  })
  api.load()
  const saved = () => JSON.parse(String(allResponses.value.get(ITEM)?.remark ?? '{}'))
  return {
    api,
    rows: () => [...api.occurrenceRows.value, ...api.postPeriodRows.value],
    stored: () => [...(saved().occurrenceRows ?? []), ...(saved().postPeriodRows ?? [])],
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G5-12 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G5VoucherRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, [r.offsetAccount, r.offsetSubAccount].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
    edit: (inst, id) => (inst.api as unknown as G5Api).removeOccurrenceRow(id),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, supportingDoc: '合同' },
    oldRowKept: { supportingDoc: '合同' },
  })

  it('两张表：抽凭进所选的表、替换只动所选的表；挂凭导入按凭证日期分表，已在某张表的分录留在原处', async () => {
    const inst = make()
    const occ = () => inst.api.occurrenceRows.value.map(no)
    const post = () => inst.api.postPeriodRows.value.map(no)
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, 'occurrence')
    await inst.api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0101', voucherDate: '2026-01-05' })], phase: 'final', batchId: 'b-2' }, 'post')
    // 挂凭：fp-1 已在本期表 → 留在原处；fp-3 在期末之后 → 期后；fp-4 在期内 → 本期
    await inst.api.onAttachImported([
      sample('fp-1'),
      sample('fp-3', { voucherNo: '0102', voucherDate: '2026-02-01' }),
      sample('fp-4', { voucherNo: '0013', voucherDate: '2025-06-30' }),
    ])
    expect([occ(), post()]).toEqual([['0012', '0013'], ['0101', '0102']])
    await inst.api.onEngineFilled({ samples: [sample('fp-5', { voucherNo: '0103', voucherDate: '2026-03-01' })], phase: 'final', fillMode: 'replace', batchId: 'b-3' }, 'post')
    expect([occ(), post()]).toEqual([['0012', '0013'], ['0102', '0103']])
  })
})
