/**
 * H8-12 使用权资产减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行，对方科目「编码 名称」按配对拼接）；另验：
 * - 映射：资产名称取摘要、合同号留空（原实现把摘要写进合同号，H8-2 带入与同步 H9 都按合同号匹配），
 *   原值取贷方、红字带符号照记；
 * - H8-2 带入按合同号合并时保留原行的 `_gt`（原来合并行以带入行为底，`_gt` 丢失、再抽一次就重复）；
 * - 年审阶段预审行只读：H8-2 带入、按 H9 填负债、同步 H9 都不改它。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH8DisposalCheck, type H8DisposalCheckRow } from '../useH8DisposalCheck'
import { resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'H8-12-rows'
const PRELIM = { vk: VK, lfp: 'fp-0', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' }

function make(seed?: unknown[], extra: Record<string, unknown> = {}): HostInstance<H8DisposalCheckRow> & {
  api: ReturnType<typeof useH8DisposalCheck>
} {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set(ROWS, { item_id: ROWS, remark: JSON.stringify(seed) })
  for (const [k, v] of Object.entries(extra)) allResponses.value.set(k, { item_id: k, remark: JSON.stringify(v) })
  let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
  const onSave = vi.fn((itemId: string, value: unknown) => {
    if (itemId === ROWS) last = JSON.parse(JSON.stringify(value))
  })
  const api = useH8DisposalCheck({ wpId: ref('wp-h8'), projectId: ref('proj-1'), allResponses, onSave, isReadonly: ref(false) })
  return {
    api: { ...api, voucherRowClass: api.rowClassName } as any,
    rows: () => api.rows.value,
    stored: () => last as any[],
    rowSaves: () => onSave.mock.calls.filter(c => c[0] === ROWS).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('H8-12 使用权资产减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H8DisposalCheckRow>({
    make: seed => make(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.oppositeAccount, r.rouCost],
    expected: [['0012', '1002/6111 银行存款/投资收益', 300], ['0014', '多科目', 1000]],
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', contractNo: 'L-手' },
    oldRow: { voucherNo: '0012', reductionDate: '2025-03-04', rouCost: 1000, approver: '李四' },
    oldRowKept: { approver: '李四' },
  })

  it('映射：资产名称取摘要、合同号留空（原实现写进合同号），原值取贷方、红字带符号照记', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-600.00', summary: '冲销退租' })], phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.assetName, r.contractNo, r.voucherNo, r.reductionDate, r.rouCost, r.oppositeAccount])).toEqual([
      ['冲销退租', '', '0012', '2025-03-04', -600, '1002 银行存款'],
    ])
  })

  it('H8-2 带入按合同号合并时保留原行的 `_gt`：之后再抽同一分录不重复', async () => {
    const inst = make(undefined, { 'H8-2-rows': [{ contractNo: 'L-1', assetName: '厂房', terminationDate: '2025-06-30', initialAmount: 500 }] })
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    inst.api.updateCell(inst.rows()[0].rowId, 'contractNo', 'L-1')
    inst.api.importFromH82()
    const linked = inst.rows().find(r => r.contractNo === 'L-1')!
    expect((linked as any)._gt).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-2' })
    expect(inst.rows().filter(r => r.voucherNo === '0012')).toHaveLength(1)
  })

  it('年审阶段预审行只读：H8-2 带入、按 H9 填负债、同步 H9 都不改它', async () => {
    const prelim = { rowId: 'p1', contractNo: 'L-1', voucherNo: '0011', rouCost: 100, liabilityBalance: 0, _gt: PRELIM }
    const inst = make([prelim], {
      'H8-2-rows': [{ contractNo: 'L-1', assetName: '厂房（H8-2）', terminationDate: '2025-06-30', initialAmount: 900 }],
      'H9-2-rows': [{ contractNo: 'L-1', endBalance: 77 }],
    })
    await inst.api.voucherFillReady()
    inst.api.importFromH82()
    inst.api.fillLiabilityFromH9()
    inst.api.syncToH9('p1')
    expect(inst.api.syncAllToH9()).toBe(0)
    expect(inst.rows()[0]).toMatchObject({ rowId: 'p1', rouCost: 100, liabilityBalance: 0, h9Synced: false })
  })
})
