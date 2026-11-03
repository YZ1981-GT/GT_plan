/**
 * G1-13 交易性金融资产检查表、G1-14 衍生工具凭证抽查接入共享回填函数
 * （spec voucher-identity-writeback-and-audit-phase 任务 11）
 *
 * 通用五条用例见 voucherFillHostHarness；G1-13 另验两个区段各一张表（抽凭进当前区段、替换只动当前区段、
 * 样本在借方时对方科目进贷方科目），G1-14 另验回填后去掉占位空行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG1VoucherCheck, type G1VoucherCheckRow } from '../useG1VoucherCheck'
import { useG1DerivativeCheck, type G1DerivativeVoucherRow } from '../useG1DerivativeCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { metaOf } from '../shared/voucherCheckFill'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

function store() {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, data: Partial<ChecklistResponse>) => {
    allResponses.value.set(key, { item_id: key, conclusion: data.conclusion ?? null, remark: data.remark ?? null } as ChecklistResponse)
  }
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, data))
  return { allResponses, put, debouncedSave }
}

const G113 = 'G1-13-rows'
function makeG113(seed?: unknown[]): HostInstance<G1VoucherCheckRow> & { api: ReturnType<typeof useG1VoucherCheck> } {
  const { allResponses, put, debouncedSave } = store()
  if (seed) put(G113, { conclusion: JSON.stringify(seed) })
  const api = useG1VoucherCheck({ allResponses, debouncedSave, isReadonly: ref(false), projectId: ref('proj-1') })
  return {
    api,
    // 两个区段的占位空行不算
    rows: () => api.rows.value.filter(r => r.voucherNo || metaOf(r)),
    stored: () => JSON.parse(String(allResponses.value.get(G113)?.conclusion ?? '[]')).filter((r: any) => r.voucherNo),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === G113).length,
  }
}

const G114 = 'G1-14-vouchers'
function makeG114(seed?: unknown[]): HostInstance<G1DerivativeVoucherRow> & { api: ReturnType<typeof useG1DerivativeCheck> } {
  const { allResponses, put, debouncedSave } = store()
  if (seed) put(G114, { remark: JSON.stringify(seed) })
  const api = useG1DerivativeCheck({ allResponses, debouncedSave, isReadonly: ref(false), projectId: ref('proj-1') })
  return {
    api,
    rows: () => api.vouchers.value,
    stored: () => JSON.parse(String(allResponses.value.get(G114)?.remark ?? '[]')),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === G114).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G1-13 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G1VoucherCheckRow>({
    make: makeG113,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG1VoucherCheck>).updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1', period: 'current' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, supportingDocs: '合同', period: 'current' },
    oldRowKept: { supportingDocs: '合同' },
  })

  it('两个区段各一张表：抽凭进当前区段、替换只动当前区段；样本在借方时对方科目进贷方科目、本科目进借方科目', async () => {
    const inst = makeG113()
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { accountCode: '1101', accountName: '交易性金融资产' })], phase: 'final', batchId: 'b-1' })
    inst.api.activePeriod.value = 'subsequent'
    await inst.api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0101' })], phase: 'final', batchId: 'b-2' })
    await inst.api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0102' })], phase: 'final', fillMode: 'replace', batchId: 'b-3' })
    await nextTick()
    expect(inst.rows().map(r => [r.voucherNo, r.period])).toEqual([['0012', 'current'], ['0102', 'subsequent']])
    const first = inst.rows()[0]
    expect([first.debitAccount, first.creditAccount, first.sampleSource]).toEqual(['1101 交易性金融资产', '1002 银行存款', '抽凭引擎'])
  })
})

describe('G1-14 衍生工具凭证抽查走共享函数', () => {
  voucherFillHostCases<G1DerivativeVoucherRow>({
    make: makeG114,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG1DerivativeCheck>).updateVoucher(id, { conclusion: value }),
    editKey: 'conclusion',
    manualRow: { id: 'm1', seq: 1, voucherNo: '手-1', date: '', businessContent: '', detailAccount: '', counterAccount: '', debitAmount: 0, creditAmount: 0, conclusion: '' },
    oldRow: { seq: 1, voucherNo: '0012', date: '2025-03-04', businessContent: '', detailAccount: '', counterAccount: '', debitAmount: 1000, creditAmount: 0, conclusion: '人工结论' },
    oldRowKept: { conclusion: '人工结论' },
  })

  it('回填后去掉新建时的占位空行；结论按核对结果给缺省值', async () => {
    const inst = makeG114()
    expect(inst.rows()).toHaveLength(1)
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { checkResult: 'Y' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.seq, r.voucherNo, r.conclusion])).toEqual([[1, '0012', '未见异常']])
  })
})
