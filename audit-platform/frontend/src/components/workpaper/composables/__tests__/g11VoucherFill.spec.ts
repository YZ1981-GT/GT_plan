/**
 * G11-5 投资收益凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness；表上只有贷方一栏：借方样本记负数，对方科目与明细分两列。
 */
import { beforeEach, describe, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG11VoucherCheck, type G11VoucherCheckRow } from '../useG11VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'G11-voucher-rows'

function make(seed?: unknown[]): HostInstance<G11VoucherCheckRow> & { api: ReturnType<typeof useG11VoucherCheck> } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(ROWS, JSON.stringify(seed))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useG11VoucherCheck({
    wpId: ref('wp-11'), projectId: ref('proj-1'), year: ref(2025), allResponses, debouncedSave, isReadonly: ref(false),
  })
  return {
    api,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '[]')),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G11-5 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G11VoucherCheckRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, r.counterDetail, r.creditAmount],
    expected: [
      ['0012', '1002', '银行存款', 200],
      ['0012', '6111', '投资收益', 100],
      ['0014', '多科目', '', -1000],
    ],
    edit: (inst, id, value) => (inst.api as ReturnType<typeof useG11VoucherCheck>).updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1', source: '手工' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', creditAmount: 1000, supportingDocDesc: '合同' },
    oldRowKept: { supportingDocDesc: '合同' },
  })
})
