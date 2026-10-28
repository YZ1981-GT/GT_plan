/**
 * H4-4 工程物资增加检查 / H4-5 减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行，对方科目按配对用「/」拼接）；另验：
 * - 映射：金额取样本自己那一栏、红字带符号照记；H4-4 对方科目 / 明细分列，H4-5 名称取摘要（原实现取本科目名称）；
 * - 逐行抽凭（「抽凭」列）：第一笔写进所选行（已填的名称 / 备注保留，行带 `_gt` 来源手工 + 抽凭），其余样本新增；
 *   同一分录不重复写；所选行已关联凭证时按整表抽凭；撤销该批次保留所选行。原实现只取第一笔、其余静默丢掉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { useH4AdditionCheck, type H4AdditionCheckRow } from '../useH4AdditionCheck'
import { useH4DisposalCheck, type H4DisposalCheckRow } from '../useH4DisposalCheck'
import { resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

function harness<R>(use: typeof useH4AdditionCheck | typeof useH4DisposalCheck, rowsKey: string) {
  return function make(seed?: unknown[], readonly = false): HostInstance<R> & { api: any } {
    const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    if (seed) allResponses.value.set(rowsKey, { item_id: rowsKey, remark: JSON.stringify(seed) })
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const onSave = vi.fn((itemId: string, value: unknown) => {
      if (itemId === rowsKey) last = JSON.parse(JSON.stringify(value))
    })
    const api = use({ wpId: ref('wp-h4'), projectId: ref('proj-1'), allResponses, onSave, isReadonly: ref(readonly) }) as any
    return {
      api: { ...api, voucherRowClass: api.rowClassName },
      rows: () => api.rows.value as R[],
      stored: () => last as any[],
      rowSaves: () => onSave.mock.calls.filter(c => c[0] === rowsKey).length,
    }
  }
}

const makeAdd = harness<H4AdditionCheckRow>(useH4AdditionCheck, 'H4-4-rows')
const makeDis = harness<H4DisposalCheckRow>(useH4DisposalCheck, 'H4-5-rows')
const meta = (r: unknown) => (r as { _gt?: Record<string, unknown> })._gt

beforeEach(resetVoucherFillMocks)

describe('H4-4 工程物资增加检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H4AdditionCheckRow>({
    make: seed => makeAdd(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.oppositeAccount, r.oppositeDetail, r.amount],
    expected: [['0012', '1002/6111', '银行存款/投资收益', 300], ['0014', '多科目', '', 1000]],
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, supplier: '甲供应商' },
    oldRowKept: { supplier: '甲供应商' },
  })

  it('映射：业务内容取摘要（不写进支持性文件），借方红字带符号照记（原实现金额不为正就不写），标已抽凭', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-r', { debitAmount: '-500.00', summary: '冲销入库' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.name, r.businessContent, r.voucherDate, r.amount, r.supportingDocs, r.voucherResult])).toEqual([
      ['冲销入库', '冲销入库', '2025-03-04', -500, '', '已抽凭'],
    ])
  })

  it('逐行抽凭：第一笔写进所选行（名称保留、带 `_gt`），其余样本新增；同一分录不再写进别的行；撤销该批次保留所选行', async () => {
    const inst = makeAdd([{ rowId: 'r1', name: '钢管', supplier: '甲' }, { rowId: 'r2', name: '电缆' }])
    const out = await inst.api.onEngineFilledIntoRow(
      { samples: [sample('fp-1', { summary: '购入钢管' }), sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1' }, 'r1',
    )
    expect(out).toMatchObject({ cancelled: false, added: 2 })
    expect(inst.rows().map(r => [r.rowId, r.name, r.voucherNo, r.businessContent, r.amount, r.supplier])).toEqual([
      ['r1', '钢管', '0012', '购入钢管', 1000, '甲'],
      ['r2', '电缆', '', '', 0, ''],
      [expect.any(String), '抽凭样本', '0013', '抽凭样本', 1000, ''],
    ])
    expect(meta(inst.stored()[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1', ph: 'final', src: ['manual', 'engine'] })
    expect(inst.api.rowHasVoucher(inst.rows()[0])).toBe(true)

    await inst.api.onEngineFilledIntoRow({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-2' }, 'r2')
    expect(vi.mocked(ElMessage.info)).toHaveBeenCalledWith('凭证 0012 这笔分录已在本表，未写入所选行')
    expect(inst.rows()[1]).toMatchObject({ rowId: 'r2', voucherNo: '' })
    expect(meta(inst.rows()[1])).toBeUndefined()

    expect(await inst.api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(inst.rows().map(r => r.rowId)).toEqual(['r1', 'r2'])
    expect(meta(inst.rows()[0])).toMatchObject({ lfp: 'fp-1', b: null, src: ['manual'] })
  })

  it('所选行已关联凭证（含年审阶段的预审行）：不改它，本次样本按整表抽凭填入新行；只读时不改', async () => {
    const linked = { rowId: 'p1', voucherNo: '0011', name: '已抽', _gt: { vk: VK, lfp: 'fp-0', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const inst = makeAdd([linked])
    await inst.api.onEngineFilledIntoRow({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, 'p1')
    expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledWith('所选行已关联凭证，本次样本按整表抽凭填入新行')
    expect(inst.rows().map(r => [r.rowId, r.voucherNo])).toEqual([['p1', '0011'], [expect.any(String), '0012']])

    const ro = makeAdd([{ rowId: 'r1', name: '钢管' }], true)
    expect(await ro.api.onEngineFilledIntoRow({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, 'r1'))
      .toMatchObject({ cancelled: true })
    expect(ro.rows()[0].voucherNo).toBe('')
  })
})

describe('H4-5 工程物资减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H4DisposalCheckRow>({
    make: seed => makeDis(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.oppositeAccount, r.originalCost],
    expected: [['0012', '1002/6111 银行存款/投资收益', 300], ['0014', '多科目', 1000]],
    edit: (inst, id, value) => (inst as any).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    // 原实现回填不写减少日期
    oldRow: { voucherNo: '0012', originalCost: 1000, supportingDocs: '领料单 LL-1' },
    oldRowKept: { supportingDocs: '领料单 LL-1' },
  })

  it('映射：名称取摘要（原实现取本科目名称，每行都是「工程物资」），原值取贷方、红字带符号照记，写减少日期与对方科目', async () => {
    const inst = makeDis()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-300.00', summary: '冲销领用', accountName: '工程物资' })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.name, r.disposalDate, r.oppositeAccount, r.originalCost, r.amount, r.voucherResult])).toEqual([
      ['冲销领用', '2025-03-04', '1002 银行存款', -300, -300, '已抽凭'],
    ])
  })

  it('逐行抽凭：写进所选行，已填的名称 / 备注保留，摘要不写进支持性文件（原实现写进去）', async () => {
    const inst = makeDis([{ rowId: 'r1', name: '钢材', remark: '待核' }])
    await inst.api.onEngineFilledIntoRow({
      samples: [sample('fp-1', { debitAmount: null, creditAmount: '200.00', summary: '领用钢材', selectionReason: '大额' })],
      phase: 'final', batchId: 'b-1',
    }, 'r1')
    expect(inst.rows().map(r => [r.rowId, r.name, r.remark, r.voucherNo, r.originalCost, r.oppositeAccount, r.supportingDocs])).toEqual([
      ['r1', '钢材', '待核', '0012', 200, '1002 银行存款', ''],
    ])
    expect(meta(inst.stored()[0])).toMatchObject({ lfp: 'fp-1', src: ['manual', 'engine'] })
  })
})
