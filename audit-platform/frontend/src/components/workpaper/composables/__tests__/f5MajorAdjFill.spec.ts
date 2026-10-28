/**
 * F5-8 重大调整事项核查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（表上 16 行空白占位行不算；本表无对方科目列，看凭证号与借贷金额）；
 * 另验：回填时去掉空白占位行、撤销到表空补回默认空白行；读入透传 `_gt`（原读入逐字段重建会丢）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import {
  F5_MAJOR_ADJ_DEFAULT_ROWS, isBlankF5MajorAdjRow, useF5MajorAdjustment, type MajorAdjustmentRow,
} from '../useF5MajorAdjustment'
import type { ChecklistResponse } from '../useF1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'F5-8-rows'
type F5Api = ReturnType<typeof useF5MajorAdjustment>
const real = (r: MajorAdjustmentRow) => !isBlankF5MajorAdjRow(r)

function make(seed?: unknown[]): HostInstance<MajorAdjustmentRow> & { api: F5Api } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  if (seed) allResponses.value.set(ROWS, { item_id: ROWS, conclusion: null, remark: JSON.stringify(seed) } as ChecklistResponse)
  let saves = 0
  watch(() => allResponses.value.get(ROWS), () => { saves += 1 }, { flush: 'sync' })
  const api = useF5MajorAdjustment({ allResponses, isReadonly: ref(false), projectId: 'proj-1' })
  return {
    api,
    rows: () => api.rows.value.filter(real),
    stored: () => (JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '[]')) as MajorAdjustmentRow[]).filter(real),
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('F5-8 抽凭回填走共享函数', () => {
  voucherFillHostCases<MajorAdjustmentRow>({
    make,
    idKey: 'id',
    // 本表没有对方科目列：同一分录按对方科目展开的两行凭证号相同、金额是各自那部分
    view: r => [r.voucherNo, r.debitAmount, r.creditAmount],
    expected: [
      ['0012', 0, 200],
      ['0012', 0, 100],
      ['0014', 1000, 0],
    ],
    edit: (inst, id, value) => (inst.api as unknown as F5Api).updateCell(id, 'adjustmentReason', value),
    editKey: 'adjustmentReason',
    manualRow: { id: 'm1', voucherNo: '手-1', itemContent: '手工' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, reasonAdequate: '充分' },
    oldRowKept: { reasonAdequate: '充分' },
  })

  it(`回填时去掉 ${F5_MAJOR_ADJ_DEFAULT_ROWS} 行空白占位行；撤销到表空补回默认空白行`, async () => {
    const inst = make()
    expect(inst.api.rows.value).toHaveLength(F5_MAJOR_ADJ_DEFAULT_ROWS)
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '返利冲减成本' })], phase: 'final', batchId: 'b-1' })
    expect(inst.api.rows.value.map(r => [r.voucherNo, r.itemContent, r.debitAmount])).toEqual([['0012', '返利冲减成本', 1000]])
    expect(await inst.api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(inst.api.rows.value).toHaveLength(F5_MAJOR_ADJ_DEFAULT_ROWS)
    expect(inst.rows()).toEqual([])
  })
})
