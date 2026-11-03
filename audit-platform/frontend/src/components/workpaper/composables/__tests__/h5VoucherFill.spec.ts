/**
 * H5-7 油气资产增加检查 / H5-8 减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行，表里没有对方科目列）；另验：抽到的行带凭证号与金额
 * （原实现把凭证号、金额作为第二个参数传给只收名称的 addRow，被丢掉，行里只有摘要），金额取样本自己那一栏、
 * 红字带符号照记，资产名称取摘要。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH5AdditionCheck, type AdditionCheckRow } from '../useH5AdditionCheck'
import { useH5DisposalCheck, type DisposalCheckRow } from '../useH5DisposalCheck'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

function harness<R>(use: typeof useH5AdditionCheck | typeof useH5DisposalCheck, rowsKey: string) {
  return function make(seed?: unknown[]): HostInstance<R> & { api: any } {
    const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    if (seed) allResponses.value.set(rowsKey, { item_id: rowsKey, remark: JSON.stringify(seed) })
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const onSave = vi.fn((itemId: string, value: unknown) => {
      if (itemId === rowsKey) last = JSON.parse(JSON.stringify(value))
    })
    const api = use({ allResponses, wpId: ref('wp-h5'), projectId: ref('proj-1'), onSave, isReadonly: ref(false) }) as any
    return {
      api,
      rows: () => api.rows.value as R[],
      stored: () => last as any[],
      rowSaves: () => onSave.mock.calls.filter(c => c[0] === rowsKey).length,
    }
  }
}

const makeAdd = harness<AdditionCheckRow>(useH5AdditionCheck, 'H5-7-rows')
const makeDis = harness<DisposalCheckRow>(useH5DisposalCheck, 'H5-8-rows')
const ONE_ROW_EACH = [['0012', 300], ['0014', 1000]]

beforeEach(resetVoucherFillMocks)

describe('H5-7 油气资产增加检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<AdditionCheckRow>({
    make: makeAdd,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.amount],
    expected: ONE_ROW_EACH,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'conclusion', value),
    editKey: 'conclusion',
    manualRow: { rowId: 'm1', voucherNo: '手-1', assetName: '手工项' },
    oldRow: { voucherNo: '0012', amount: 1000, oilField: '大庆' },
    oldRowKept: { oilField: '大庆' },
  })

  it('抽到的行带凭证号与金额（原实现被丢掉），借方红字带符号照记，资产名称取摘要', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-r', { debitAmount: '-800.00', summary: '冲销勘探支出' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.assetName, r.voucherNo, r.amount, r.voucherResult])).toEqual([['冲销勘探支出', '0012', -800, '已抽凭']])
  })
})

describe('H5-8 油气资产减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<DisposalCheckRow>({
    make: makeDis,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.originalCost],
    expected: ONE_ROW_EACH,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'conclusion', value),
    editKey: 'conclusion',
    manualRow: { rowId: 'm1', voucherNo: '手-1', assetName: '手工项' },
    oldRow: { voucherNo: '0012', originalCost: 1000, approvalDoc: '批-1' },
    oldRowKept: { approvalDoc: '批-1' },
  })

  it('抽到的行带凭证号、减少日期与原值（原值取贷方、红字带符号照记）', async () => {
    const inst = makeDis()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-120.00', summary: '冲销报废' })], phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.assetName, r.voucherNo, r.disposalDate, r.originalCost])).toEqual([['冲销报废', '0012', '2025-03-04', -120]])
  })
})
