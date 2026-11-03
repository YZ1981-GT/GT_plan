/**
 * G3-4 期后收回接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（期后区一张表，空白占位行不算；对方科目 = 编码 + 对方明细科目）；
 * 另验：期后区只收资产负债表日之后的凭证（截止日及以前剔除并提示）、回填时去掉空白占位行、
 * 撤销到表空补一行空白行、回填后切到期后区段、红字带符号照记（金额列同值）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { SUBSEQUENT_KEY, isBlankSubsequentRow, useG3CalcCheck, type SubsequentRow } from '../useG3CalcCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { paired, resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type G3Api = ReturnType<typeof useG3CalcCheck>
const real = (r: SubsequentRow) => !isBlankSubsequentRow(r)

function make(seedIn?: unknown[], cutoff = ''): HostInstance<SubsequentRow> & { api: G3Api } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  if (seedIn) {
    allResponses.value.set(SUBSEQUENT_KEY, { item_id: SUBSEQUENT_KEY, conclusion: JSON.stringify(seedIn), remark: null })
  }
  let saves = 0
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => {
    if (id === SUBSEQUENT_KEY) saves += 1
    allResponses.value.set(id, { item_id: id, conclusion: data.conclusion ?? null, remark: data.remark ?? null })
  })
  const api = useG3CalcCheck({
    allResponses, debouncedSave, isReadonly: ref(false), cutoffDate: ref(cutoff), projectId: 'proj-1',
  })
  return {
    api,
    rows: () => api.subsequentRows.value.filter(real),
    stored: () => (JSON.parse(String(allResponses.value.get(SUBSEQUENT_KEY)?.conclusion ?? '[]')) as SubsequentRow[]).filter(real),
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G3-4 期后收回：抽凭回填走共享函数', () => {
  voucherFillHostCases<SubsequentRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, [r.counterAccount, r.counterDetailAccount].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as unknown as G3Api).updateSubsequentRow(id, { abnormalNote: value }),
    editKey: 'abnormalNote',
    manualRow: { id: 'm1', seq: 1, voucherNo: '手-1', summary: '手工' },
    oldRow: { seq: 1, voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, creditAmount: 0, indexNo: 'G3-2' },
    oldRowKept: { indexNo: 'G3-2' },
  })

  it('期后区只收资产负债表日之后的凭证：截止日及以前剔除并提示；回填后切到期后区段', async () => {
    const inst = make(undefined, '2025-12-31')
    expect(inst.api.segment.value).toBe('increase')
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { voucherNo: '0001', voucherDate: '2025-12-31' }),
        sample('fp-2', { voucherNo: '0002', voucherDate: '2026-01-05' }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => r.voucherNo)).toEqual(['0002'])
    expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledWith(expect.stringContaining('已剔除截止日及以前 1 笔'))
    expect(inst.api.segment.value).toBe('subsequent')
  })

  it('回填时去掉空白占位行，撤销到表空补一行空白行；红字带符号照记（金额列同值）、来源记抽凭引擎', async () => {
    const inst = make()
    expect(inst.api.subsequentRows.value).toHaveLength(1)
    await inst.api.onEngineFilled({
      samples: [sample('fp-1', { debitAmount: null, creditAmount: '-80.00', pairing: paired(['1002', '银行存款', '-80.00']) })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.subsequentRows.value.map(r => [r.seq, r.voucherNo, r.creditAmount, r.amount, r.samplingSource]))
      .toEqual([[1, '0012', -80, -80, '抽凭引擎']])
    expect(await inst.api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(inst.api.subsequentRows.value).toHaveLength(1)
    expect(inst.rows()).toEqual([])
  })
})
