/**
 * G10-7 交易性金融负债凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness；另验两个口径各一张表：抽凭进当前口径、替换只动当前口径、
 * 已在另一口径的分录挂凭导入时留在原处。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG10VoucherCheck, type G10VoucherCheckRow } from '../useG10VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'G10-voucher-rows'

function make(seed?: unknown[]): HostInstance<G10VoucherCheckRow> & { api: ReturnType<typeof useG10VoucherCheck> } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(ROWS, JSON.stringify({ version: 2, rows: seed }))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useG10VoucherCheck({
    wpId: ref('wp-10'), projectId: ref('proj-1'), year: ref(2025), allResponses, debouncedSave, isReadonly: ref(false),
  })
  return {
    api,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '{"rows":[]}')).rows,
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G10-7 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G10VoucherCheckRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG10VoucherCheck>).updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1', periodScope: 'current' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, supportingDocDesc: '合同', periodScope: 'current' },
    oldRowKept: { supportingDocDesc: '合同' },
  })

  it('两个口径各一张表：抽凭进当前口径；替换只动当前口径；已在另一口径的分录挂凭导入时留在原处', async () => {
    const inst = make()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    inst.api.setPeriodScope('subsequent')
    await inst.api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0101', voucherDate: '2026-01-05' })], phase: 'final', batchId: 'b-2' })
    await inst.api.onAttachImported([sample('fp-1')])
    await inst.api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0102' })], phase: 'final', fillMode: 'replace', batchId: 'b-3' })
    await nextTick()
    expect(inst.rows().map(r => [r.voucherNo, r.periodScope])).toEqual([['0012', 'current'], ['0102', 'subsequent']])
    expect(inst.api.scopedRows.value.map(r => r.voucherNo)).toEqual(['0102'])
  })
})
