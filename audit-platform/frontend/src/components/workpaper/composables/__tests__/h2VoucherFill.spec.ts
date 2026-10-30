/**
 * H2-8 在建工程增加检查 / H2-9 减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行，单列金额，表里没有对方科目列）；另验：
 * H2-8 凭证号写凭证号列、不再写进合同编号（原实现写进合同编号，证据缺口判断把它当成已查合同）；
 * H2-9 金额取样本自己那一栏、红字带符号照记；年审阶段「自动标记异常」不动预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH2AdditionCheck, type H2AdditionRow } from '../useH2AdditionCheck'
import { useH2DecreaseCheck, type H2DecreaseRow } from '../useH2DecreaseCheck'
import { resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

function harness<R>(use: typeof useH2AdditionCheck | typeof useH2DecreaseCheck, rowsKey: string) {
  return function make(seed?: unknown[]): HostInstance<R> & { api: any } {
    const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    if (seed) allResponses.value.set(rowsKey, { item_id: rowsKey, remark: JSON.stringify(seed) })
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const onSave = vi.fn((itemId: string, value: unknown) => {
      if (itemId === rowsKey) last = JSON.parse(JSON.stringify(value))
    })
    const api = use({ wpId: ref('wp-h2'), projectId: ref('proj-1'), allResponses, isReadonly: ref(false), onSave }) as any
    return {
      api,
      rows: () => api.rows.value as R[],
      stored: () => last as any[],
      rowSaves: () => onSave.mock.calls.filter(c => c[0] === rowsKey).length,
    }
  }
}

const makeAdd = harness<H2AdditionRow>(useH2AdditionCheck, 'H2-8-rows')
const makeDec = harness<H2DecreaseRow>(useH2DecreaseCheck, 'H2-9-rows')
const ONE_ROW_EACH = [['0012', 300], ['0014', 1000]]

beforeEach(resetVoucherFillMocks)

describe('H2-8 在建工程增加检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H2AdditionRow>({
    make: makeAdd,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.amount],
    expected: ONE_ROW_EACH,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    // 原实现把凭证号写在合同编号里
    oldRow: { contractNo: '0012', date: '2025-03-04', amount: 1000, supplier: '甲建设', samplingStatus: '待检查' },
    oldRowKept: { supplier: '甲建设' },
  })

  it('凭证号写凭证号列，合同编号留空（原实现写进合同编号，证据缺口判断把它当成已查合同）；名称取摘要', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '支付工程进度款' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.voucherNo, r.contractNo, r.name, r.date, r.amount, r.samplingStatus])).toEqual([
      ['0012', '', '支付工程进度款', '2025-03-04', 1000, '待检查'],
    ])
    expect(inst.stored()[0]).toMatchObject({ voucherNo: '0012', contractNo: '', _gt: { lfp: 'fp-1' } })
  })
})

describe('H2-9 在建工程减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H2DecreaseRow>({
    make: makeDec,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.transferToFaAmount],
    expected: ONE_ROW_EACH,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', decreaseDate: '2025-03-04', transferToFaAmount: 1000, approvalRef: 'SP-1' },
    oldRowKept: { approvalRef: 'SP-1' },
  })

  it('转固金额取样本自己那一栏（减少在贷方），贷方红字带符号照记；默认记入转入固定资产', async () => {
    const inst = makeDec()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-300.00', summary: '冲销转固' })], phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.name, r.decreaseDate, r.transferToFaAmount, r.decreaseType])).toEqual([
      ['冲销转固', '2025-03-04', -300, '转入固定资产'],
    ])
  })

  it('年审阶段「自动标记异常」不动预审行，只标本阶段的行', async () => {
    const prelim = {
      rowId: 'p1', voucherNo: '0011', decreaseDate: '2025-02-01', transferToFaAmount: 500,
      _gt: { vk: VK, lfp: 'fp-0', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }
    const inst = makeDec([prelim])
    await inst.api.voucherFillReady()
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { debitAmount: null, creditAmount: '800.00' })], phase: 'final', batchId: 'b-1' })
    expect(inst.api.autoMarkAnomalies()).toBe(1)
    expect(inst.rows().map(r => [r.voucherNo, r.isAbnormal])).toEqual([['0011', ''], ['0012', '是']])
    expect(inst.stored().map((r: any) => r.isAbnormal)).toEqual(['', '是'])
  })
})
