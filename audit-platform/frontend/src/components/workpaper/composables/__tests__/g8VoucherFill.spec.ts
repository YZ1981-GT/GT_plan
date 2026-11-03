/**
 * G8-6 其他权益工具投资凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness；另验抽样参数里的本次样本量随抽凭行数、预填实际错报不动预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))
// 🔴 HEAD 的 g8CrossHelpers.ts 引用了从未入库的 ./programStepOverrides（并发会话的模块），整个模块加载即失败
// （既有 useG8VoucherCheck.spec 套件同因加载失败）。本用例只验回填，跨表助手换成同值的最小替身。
vi.mock('../g8CrossHelpers', () => ({
  G8_DETAIL_KEY: 'G8-detail-rows',
  G8_FV_KEY: 'G8-fv-test-rows',
  G8_DESIGNATION_KEY: 'G8-designation-rows',
  G8A_VOUCHER_MARK_KEY: 'G8A-voucher-complete',
  G8A_VOUCHER_PROGRAM_NOS: [6, 7, 12],
  matchG8InvesteeKey: (name: string) => String(name ?? '').trim().toLowerCase(),
  markG8AProcedureSteps: vi.fn(async () => 0),
  buildG8VoucherProcedureSummary: () => '',
  dispatchProcedureFocus: vi.fn(),
}))

import { useG8VoucherCheck, type G8VoucherRow } from '../useG8VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'G8-voucher-rows'

function make(seed?: unknown[]): HostInstance<G8VoucherRow> & { api: ReturnType<typeof useG8VoucherCheck>; allResponses: Ref<Map<string, ChecklistResponse>> } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(ROWS, JSON.stringify(seed))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useG8VoucherCheck({
    wpId: ref('wp-8'), projectId: ref('proj-1'), year: ref(2025), allResponses, debouncedSave, isReadonly: ref(false),
  })
  return {
    api, allResponses,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '[]')),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G8-6 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G8VoucherRow>({
    make,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG8VoucherCheck>).updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', source: '手工' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, check1OriginalComplete: true, source: '抽凭' },
    oldRowKept: { check1OriginalComplete: true },
  })

  it('抽样参数：抽凭后方法与本次样本量（抽凭行数）落库', async () => {
    const inst = make()
    await inst.api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', method: 'mus' })
    expect(JSON.parse(String(inst.allResponses.value.get('G8-vc-params')?.remark))).toMatchObject({ samplingMethod: 'mus', currentSampleSize: 2 })
  })
})
