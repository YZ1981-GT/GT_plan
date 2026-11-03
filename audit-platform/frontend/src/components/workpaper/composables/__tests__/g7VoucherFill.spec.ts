/**
 * G7 两处凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）：
 * - G7-18 凭证检查表（宿主 G7TabVoucherCheck，行与回填在 g7VoucherCheckRows.useG7VoucherCheckFill）；
 * - G7-10/11/12 的「凭证抽查」共享区块（G7VoucherSampleSection，行与回填在 g7VoucherSample.useG7VoucherSampleRows）。
 * 两处都用通用五条用例（voucherFillHostHarness）；表格 v-model 原地改行，组合式函数唯一的改行入口是删行 ⇒ 用它验只读，
 * 原地改了内存靠保存时按读入版本写回兜底。另验：凭证抽查不再按凭证号去重（同号不同分录各成一行）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { parseG7CheckRows, useG7VoucherCheckFill, type G7CheckRow } from '../g7VoucherCheckRows'
import { useG7VoucherSampleRows, type G7VoucherSampleRow } from '../g7VoucherSample'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type CheckApi = ReturnType<typeof useG7VoucherCheckFill>
type SampleApi = ReturnType<typeof useG7VoucherSampleRows>

function makeCheck(seed?: unknown[]): HostInstance<G7CheckRow> & { api: CheckApi & { voucherFillReady: () => Promise<unknown>; voucherRowClass: CheckApi['rowClass'] } } {
  const rows = ref(parseG7CheckRows(seed ?? []))
  let saves = 0
  let saved = JSON.stringify(seed ?? [])
  // 宿主 persistRows：rowsToPersist（年审阶段预审行按读入版本写回）序列化后写库
  const vf = useG7VoucherCheckFill({
    projectId: 'proj-1', rows, readonly: false,
    persist: () => {
      saves += 1
      saved = JSON.stringify(vf.rowsToPersist())
    },
  })
  vf.markLoaded()
  return {
    api: { ...vf, voucherFillReady: vf.ready, voucherRowClass: vf.rowClass },
    rows: () => rows.value,
    stored: () => JSON.parse(saved),
    rowSaves: () => saves,
  }
}

function makeSample(seed?: unknown[]): HostInstance<G7VoucherSampleRow> & { api: SampleApi } {
  let saves = 0
  let saved = JSON.stringify(seed ?? [])
  const api = useG7VoucherSampleRows({
    projectId: 'proj-1', readonly: false,
    save: (json) => {
      saves += 1
      saved = json
    },
  })
  api.load(seed ?? [])
  return { api, rows: () => api.rows.value, stored: () => JSON.parse(saved), rowSaves: () => saves }
}

beforeEach(resetVoucherFillMocks)

describe('G7-18 凭证检查表：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G7CheckRow>({
    make: makeCheck,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id) => (inst.api as unknown as CheckApi).removeRow(id),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, creditAmount: 0, supportingDoc: '合同' },
    oldRowKept: { supportingDoc: '合同' },
  })
})

describe('G7 凭证抽查区块：抽凭回填走共享函数', () => {
  voucherFillHostCases<G7VoucherSampleRow>({
    make: makeSample,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id) => {
      const api = inst.api as unknown as SampleApi
      api.removeRow(api.rows.value.findIndex(r => r.id === id))
    },
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, creditAmount: 0, conclusion: '相符' },
    oldRowKept: { conclusion: '相符' },
  })

  it('不再按凭证号去重：同一张凭证上的两条本科目分录（指纹不同）各成一行', async () => {
    const inst = makeSample()
    await inst.api.onEngineFilled({
      samples: [sample('fp-1'), sample('fp-2', { debitAmount: '20.00', pairing: null, counterpartAccount: '6111' })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.voucherNo, r.counterAccount, r.debitAmount])).toEqual([
      ['0012', '1002 银行存款', 1000],
      ['0012', '6111', 20],
    ])
  })
})
