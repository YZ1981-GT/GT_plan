/**
 * G12-6 套期损益凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness；另验回填后按方法学写抽样方法 / 目标量 / 抽样过程。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG12VoucherCheck, type G12VoucherRow } from '../useG12VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'G12-voucher-rows'

function make(seed?: unknown[]): HostInstance<G12VoucherRow> & { api: ReturnType<typeof useG12VoucherCheck>; allResponses: Ref<Map<string, ChecklistResponse>> } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(ROWS, JSON.stringify(seed))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useG12VoucherCheck({
    wpId: ref('wp-12'), projectId: ref('proj-1'), year: ref(2025), allResponses, debouncedSave, isReadonly: ref(false),
  })
  return {
    api, allResponses,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '[]')),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G12-6 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G12VoucherRow>({
    make,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG12VoucherCheck>).updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', source: '手工' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, hedgeRelationId: 'H-1', source: '抽凭' },
    oldRowKept: { hedgeRelationId: 'H-1' },
  })

  it('回填后按方法学写抽样方法、目标量（缺省取本次样本数）与抽样过程', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', method: 'mus',
      methodology: { samplingMethod: 'mus', samplingInterval: '5000', sampleSize: 2 },
    })
    const params = JSON.parse(String(inst.allResponses.value.get('G12-vc-params')?.remark))
    expect(params).toMatchObject({ samplingMethod: 'mus', targetSampleSize: 2 })
    expect(String(params.samplingProcess)).not.toBe('')
  })
})
