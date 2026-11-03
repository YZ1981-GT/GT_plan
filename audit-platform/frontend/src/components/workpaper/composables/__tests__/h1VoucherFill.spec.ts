/**
 * H1-7 固定资产增加检查 / H1-8 减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（资产类明细表：一个样本一行，对方科目按配对用「/」拼接，单列原值）；另验：
 * 原值取样本自己那一栏的金额、红字带符号照记（原实现取绝对值，冲销被记成正常增加 / 减少）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH1AdditionCheck, type AdditionRow } from '../useH1AdditionCheck'
import { useH1DisposalCheck, type DisposalRow } from '../useH1DisposalCheck'
import type { ChecklistItem } from '../useH1FormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type Composable = typeof useH1AdditionCheck | typeof useH1DisposalCheck

function harness<R>(use: Composable, prefix: string) {
  const ROWS = `${prefix}-rows`
  return function make(seed?: unknown[]): HostInstance<R> & { api: any; saved: () => unknown[] } {
    const allResponses = ref(new Map<string, ChecklistItem>()) as Ref<Map<string, ChecklistItem>>
    if (seed) allResponses.value.set(ROWS, { item_id: ROWS, remark: JSON.stringify(seed) } as unknown as ChecklistItem)
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const onSave = vi.fn((itemId: string, value: unknown) => {
      if (itemId === ROWS) last = JSON.parse(JSON.stringify(value))
    })
    const api = use(ref('wp-h1'), ref('proj-1'), allResponses, { onSave, isReadonly: ref(false) }) as any
    return {
      api,
      rows: () => api.rows.value as R[],
      stored: () => last as any[],
      saved: () => last,
      rowSaves: () => onSave.mock.calls.filter(c => c[0] === ROWS).length,
    }
  }
}

const makeAdd = harness<AdditionRow>(useH1AdditionCheck, 'H1-7')
const makeDis = harness<DisposalRow>(useH1DisposalCheck, 'H1-8')
const JOINED = [
  ['0012', '1002/6111', 300],
  ['0014', '多科目', 1000],
]

beforeEach(resetVoucherFillMocks)

describe('H1-7 固定资产增加检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<AdditionRow>({
    make: makeAdd,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterpartAccount, r.originalCost],
    expected: JOINED,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', acquisitionDate: '2025-03-04', originalCost: 1000, assetNo: 'FA-001' },
    oldRowKept: { assetNo: 'FA-001' },
  })

  it('原值取样本自己那一栏的金额，借方红字带符号照记（原实现取绝对值）；增加日期取凭证日期', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-r', { debitAmount: '-500.00', summary: '冲销购入' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.name, r.voucherNo, r.acquisitionDate, r.originalCost, r.counterpartAccount])).toEqual([
      ['冲销购入', '0012', '2025-03-04', -500, '1002'],
    ])
  })
})

describe('H1-8 固定资产减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<DisposalRow>({
    make: makeDis,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterpartAccount, r.originalCost],
    expected: JOINED,
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', disposalDate: '2025-03-04', originalCost: 1000, assetNo: 'FA-001' },
    oldRowKept: { assetNo: 'FA-001' },
  })

  it('转出原值取样本自己那一栏（减少在贷方），贷方红字带符号照记；减少日期取凭证日期', async () => {
    const inst = makeDis()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-200.00', summary: '冲销报废', pairing: null, counterpartAccount: '1606' })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.name, r.disposalDate, r.originalCost, r.counterpartAccount])).toEqual([
      ['冲销报废', '2025-03-04', -200, '1606'],
    ])
  })
})
