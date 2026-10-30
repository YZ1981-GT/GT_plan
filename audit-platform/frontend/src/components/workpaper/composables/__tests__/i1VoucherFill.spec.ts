/**
 * I1-5 无形资产增加检查 / I1-6 减少检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（一个样本一行）；另验：引擎回填载荷真的写进行（原实现把载荷对象当样本数组：
 * I1-5 一行不填，I1-6 抛 TypeError），挂凭样本带上日期与金额（原实现读不存在的 `date` / `amount`），整表替换导入
 * 带回 `_gt`（年审阶段导入自己导出的表不把预审行变两行），I1-2 同名带入不改年审阶段的预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useI1AdditionCheck, type I1AdditionCheckRow } from '../useI1AdditionCheck'
import { useI1DisposalCheck, type I1DisposalCheckRow } from '../useI1DisposalCheck'
import { ElMessageBox } from 'element-plus'
import { resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type Inst<R> = HostInstance<R> & { api: any }

function makeAdd(seed?: unknown[], extra: Record<string, unknown> = {}): Inst<I1AdditionCheckRow> {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set('I1-5-rows', { item_id: 'I1-5-rows', remark: JSON.stringify(seed) })
  for (const [k, v] of Object.entries(extra)) allResponses.value.set(k, { item_id: k, remark: JSON.stringify(v) })
  let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
  const onSave = vi.fn((itemId: string, value: unknown) => {
    if (itemId === 'I1-5-rows') last = JSON.parse(JSON.stringify(value))
  })
  const api = useI1AdditionCheck(ref('wp-i1'), allResponses, { onSave, projectId: 'proj-1', isReadonly: false }) as any
  return {
    api,
    rows: () => api.rows.value,
    stored: () => last as any[],
    rowSaves: () => onSave.mock.calls.filter(c => c[0] === 'I1-5-rows').length,
  }
}

function makeDis(seed?: unknown[], extra: Record<string, unknown> = {}): Inst<I1DisposalCheckRow> {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set('I1-6-rows', { item_id: 'I1-6-rows', remark: JSON.stringify(seed) })
  for (const [k, v] of Object.entries(extra)) allResponses.value.set(k, { item_id: k, remark: JSON.stringify(v) })
  let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
  const onSave = vi.fn((itemId: string, value: unknown) => {
    if (itemId === 'I1-6-rows') last = JSON.parse(JSON.stringify(value))
  })
  const api = useI1DisposalCheck({ allResponses, onSave, projectId: 'proj-1', isReadonly: false }) as any
  return {
    api,
    rows: () => api.rows.value,
    stored: () => last as any[],
    rowSaves: () => onSave.mock.calls.filter(c => c[0] === 'I1-6-rows').length,
  }
}

const prelim = (over: Record<string, unknown>) => ({
  ...over, _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
})

beforeEach(resetVoucherFillMocks)

describe('I1-5 无形资产增加检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I1AdditionCheckRow>({
    make: seed => makeAdd(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.entryAmount],
    expected: [['0012', 300], ['0014', 1000]],
    edit: (inst, id, value) => (inst as Inst<I1AdditionCheckRow>).api.updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', entryDate: '2025-03-04', entryAmount: 1000, counterparty: '甲公司' },
    oldRowKept: { counterparty: '甲公司' },
  })

  it('引擎回填载荷写进行（原实现当数组读、一行不填）：名称取摘要，带入账日期与金额，借方红字带符号照记', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-r', { debitAmount: '-800.00', summary: '冲销软件采购' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => [r.name, r.voucherNo, r.entryDate, r.entryAmount, r.acquisitionMethod]))
      .toEqual([['冲销软件采购', '0012', '2025-03-04', -800, '购买']])
  })

  it('整表替换导入带回 `_gt`：年审阶段导入自己导出的表，预审行不变两行、按读入版本写回', async () => {
    const inst = makeAdd([prelim({ rowId: 'p1', name: '软件A', voucherNo: '0012', entryDate: '2025-03-04', entryAmount: 1000, counterparty: '甲公司' })])
    await inst.api.voucherFillReady()
    inst.api.importRows([
      { name: '软件A', voucherNo: '0012', entryDate: '2025-03-04', entryAmount: 1000, counterparty: '被改了' },
      { name: '软件B', voucherNo: '0099', entryDate: '2025-05-06', entryAmount: 50 },
    ], true)
    expect(inst.stored().map(r => [r.voucherNo, r.counterparty, r._gt?.lfp ?? null]))
      .toEqual([['0012', '甲公司', 'fp-1'], ['0099', '', null]])
    expect(inst.rows().map(r => [r.voucherNo, r.counterparty])).toEqual([['0012', '甲公司'], ['0099', '']])
  })

  it('「替换本阶段抽凭行」要删的行已填交易对方：先确认，取消则底稿不动', async () => {
    const inst = makeAdd()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    inst.api.updateCell(inst.rows()[0].rowId, 'counterparty', '甲公司')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel' as never)
    const out = await inst.api.onEngineFilled({
      samples: [sample('fp-2', { voucherNo: '0013' })], phase: 'final', fillMode: 'replace', batchId: 'b-2',
    })
    expect(out.cancelled).toBe(true)
    expect(inst.rows().map(r => [r.voucherNo, r.counterparty])).toEqual([['0012', '甲公司']])
  })

  it('I1-2 同名带入不改年审阶段的预审行', async () => {
    const inst = makeAdd(
      [prelim({ rowId: 'p1', name: '软件A', voucherNo: '0012', entryDate: '2025-03-04', entryAmount: 1000 })],
      { 'I1-2-rows': [{ rowId: 'd1', name: '软件A', costIncrease: 500 }] },
    )
    await inst.api.voucherFillReady()
    inst.api.seedFromDetail()
    expect(inst.rows().map(r => [r.name, r.entryAmount])).toEqual([['软件A', 1000]])
  })
})

describe('I1-6 无形资产减少检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I1DisposalCheckRow>({
    make: seed => makeDis(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterpartAccount, r.originalCost],
    expected: [['0012', '1002/6111 银行存款/投资收益', 300], ['0014', '多科目', 1000]],
    edit: (inst, id, value) => (inst as Inst<I1DisposalCheckRow>).api.updateField(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', name: '手工项' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', originalCost: 1000, attachmentIndex: '附-1' },
    oldRowKept: { attachmentIndex: '附-1' },
  })

  it('引擎回填载荷写进行（原实现遍历载荷对象抛 TypeError）：原值取贷方、红字带符号照记，减少日期同凭证日期', async () => {
    const inst = makeDis()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: null, creditAmount: '-120.00', summary: '冲销报废', pairing: undefined, counterpartAccount: '1702', counterpartAccountName: '累计摊销' })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.name, r.voucherNo, r.disposalDate, r.counterpartAccount, r.originalCost]))
      .toEqual([['冲销报废', '0012', '2025-03-04', '1702 累计摊销', -120]])
  })

  it('I1-2 同名带入不改年审阶段的预审行', async () => {
    const inst = makeDis(
      [prelim({ rowId: 'p1', name: '软件A', voucherNo: '0012', voucherDate: '2025-03-04', originalCost: 1000 })],
      { 'I1-2-rows': [{ rowId: 'd1', name: '软件A', costDecrease: 300 }] },
    )
    await inst.api.voucherFillReady()
    inst.api.seedFromDetail()
    expect(inst.rows().map(r => [r.name, r.originalCost])).toEqual([['软件A', 1000]])
  })
})
