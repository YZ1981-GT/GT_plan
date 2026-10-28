/**
 * H6-4 固定资产清理检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行，对方科目「编码 名称」按配对拼接）；另验：
 * 按分录自己的借贷栏写列（借方转入清理 → 原值与期末余额，贷方结转 → 清理收入与转处置收益、期末余额 0），
 * 红字带符号照记（原实现只认正数，借方红字一列都不写）；年审阶段从 H6-2 同步不改预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH6Check, type H6CheckRow } from '../useH6Check'
import { resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'H6-4-rows'

function make(seed?: unknown[]): HostInstance<H6CheckRow> & { api: ReturnType<typeof useH6Check> } {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set(ROWS, { item_id: ROWS, remark: JSON.stringify(seed) })
  let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
  const onSave = vi.fn((itemId: string, value: unknown) => {
    if (itemId === ROWS) last = JSON.parse(JSON.stringify(value))
  })
  const api = useH6Check({ wpId: ref('wp-h6'), projectId: ref('proj-1'), allResponses, onSave, isReadonly: ref(false) })
  return {
    api,
    rows: () => api.rows.value,
    stored: () => last as any[],
    rowSaves: () => onSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('H6-4 固定资产清理检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H6CheckRow>({
    make,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterpartAccount, r.originalCost, r.toDisposalGain],
    expected: [['0012', '1002/6111 银行存款/投资收益', 0, 300], ['0014', '多科目', 1000, 0]],
    edit: (inst, id, value) => (inst as ReturnType<typeof make>).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', assetName: '手工项' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', originalCost: 1000, approvedBy: '张三' },
    oldRowKept: { approvedBy: '张三' },
  })

  it('按借贷栏写列：借方转入清理记原值与期末余额，贷方结转记清理收入与转处置收益；借方红字带符号照记', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-a', { voucherNo: 'V1', summary: '转入清理', debitAmount: '50000', creditAmount: '0', pairing: null, counterpartAccount: '1601' }),
        sample('fp-b', { voucherNo: 'V2', summary: '结转处置收益', debitAmount: '0', creditAmount: '12000', pairing: null, counterpartAccount: '6115' }),
        sample('fp-c', { voucherNo: 'V3', summary: '冲销转入', debitAmount: '-500.00' }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.voucherNo, r.assetName, r.counterpartAccount, r.originalCost, r.clearingIncome, r.toDisposalGain, r.endingBalance]))
      .toEqual([
        ['V1', '转入清理', '1601', 50000, 0, 0, 50000],
        ['V2', '结转处置收益', '6115', 0, 12000, 12000, 0],
        ['V3', '冲销转入', '1002 银行存款', -500, 0, 0, -500],
      ])
  })

  it('年审阶段从 H6-2 同步不改预审行', async () => {
    const prelim = {
      rowId: 'p1', linkedDetailRowId: 'd1', voucherNo: '0012', date: '2025-03-04', assetName: '车床', originalCost: 1000,
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }
    const inst = make([prelim])
    await inst.api.voucherFillReady()
    inst.api.syncFromDetailRows([{ rowId: 'd1', assetName: '车床（改）', originalCost: 9999 }])
    expect(inst.rows()[0]).toMatchObject({ rowId: 'p1', assetName: '车床', originalCost: 1000 })
  })
})
