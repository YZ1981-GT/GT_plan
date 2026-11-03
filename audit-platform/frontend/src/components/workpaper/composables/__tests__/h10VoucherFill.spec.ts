/**
 * H10-4 资产处置检查表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（凭证号与日期拼在「凭证索引」一列）；另验：
 * 样本各成一行、不再按顺序填进还没挂凭证的明细行（原实现第 i 个样本填进第 i 个空行，凭证与资产对不上），
 * 明细行重排时抽凭行保留；抽查比例按已挂凭证索引的行数算。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { splitVoucherRef, useH10Check, type H10CheckRow } from '../useH10Check'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'H10-check-rows'
const DETAILS = 'H10-detail-rows'

function make(seed?: unknown[], details?: unknown[]): HostInstance<H10CheckRow> & {
  api: ReturnType<typeof useH10Check>; allResponses: Ref<Map<string, ChecklistResponse>>
} {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(ROWS, JSON.stringify(seed))
  if (details) put(DETAILS, JSON.stringify(details))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useH10Check({ allResponses, debouncedSave, isReadonly: ref(false), projectId: ref('proj-1') })
  return {
    api, allResponses,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '[]')),
    rowSaves: () => debouncedSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('H10-4 资产处置检查表：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H10CheckRow>({
    make,
    idKey: 'id',
    noOf: r => splitVoucherRef(r.voucherRef).no,
    view: r => [r.voucherRef, r.assetName],
    expected: [['2025-03-04/0012', '抽凭样本'], ['2025-03-04/0014', '抽凭样本']],
    edit: (inst, id, value) => (inst as ReturnType<typeof make>).api.updateRow(id, { remark: value }),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherRef: '手-1', assetName: '手工项' },
    oldRow: { voucherRef: '2025-03-04/0012', assetName: '设备A', approvalProcess: 'compliant' },
    oldRowKept: { approvalProcess: 'compliant' },
  })

  it('样本各成一行、不挂明细（原实现按顺序填进还没挂凭证的明细行）；抽查比例按已挂凭证索引的行数', async () => {
    const details = [1, 2, 3, 4, 5].map(i => ({ id: `d${i}`, assetName: `设备${i}` }))
    const inst = make(undefined, details)
    expect(inst.api.detailPopulation.value).toBe(5)
    expect(inst.api.sampleRatioLow.value).toBe(true)
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '处置设备' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.detailRowId, r.assetName, r.voucherRef])).toEqual([
      ...details.map(d => [d.id, d.assetName, '']),
      ['', '处置设备', '2025-03-04/0012'],
    ])
    expect(inst.api.sampleRatio.value).toBeCloseTo(0.2, 5)
    expect(inst.api.sampleRatioLow.value).toBe(false)
    expect(JSON.parse(String(inst.allResponses.value.get('H10-4-check-sample-meta')?.remark))).toEqual({ sampledVoucherCount: 1 })
  })

  it('明细行变化重排时抽凭行保留在末尾，`_gt` 还在', async () => {
    const inst = make(undefined, [{ id: 'd1', assetName: '设备1' }])
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    inst.allResponses.value.set(DETAILS, { item_id: DETAILS, conclusion: null, remark: JSON.stringify([
      { id: 'd1', assetName: '设备1' }, { id: 'd2', assetName: '设备2' },
    ]) } as ChecklistResponse)
    inst.allResponses.value = new Map(inst.allResponses.value)
    await nextTick()
    expect(inst.rows().map(r => [r.detailRowId, r.voucherRef])).toEqual([['d1', ''], ['d2', ''], ['', '2025-03-04/0012']])
    expect((inst.rows()[2] as any)._gt).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })
})
