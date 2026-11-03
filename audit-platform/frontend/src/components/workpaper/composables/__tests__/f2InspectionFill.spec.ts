/**
 * F2-33 采购入库 / F2-34 材料领用检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 两张表都用通用五条用例（voucherFillHostHarness；单列金额：采购入库优先借方、材料领用优先贷方）；另验：
 * 对方科目进对方科目 / 对方明细科目两列（原实现写进供应商）、回填时去掉开头的空白占位行、撤销到表空补一行空白行、
 * 抽样方法记在样本来源上。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useF2MaterialUsageCheck, useF2PurchaseInboundCheck } from '../useF2InspectionCheck'
import type { MaterialUsageRow, PurchaseInboundRow } from '../useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../useF2ValuationFormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type Row = PurchaseInboundRow | MaterialUsageRow
type Api = ReturnType<typeof useF2PurchaseInboundCheck> | ReturnType<typeof useF2MaterialUsageCheck>

function makeFor(use: typeof useF2PurchaseInboundCheck | typeof useF2MaterialUsageCheck, key: string) {
  return (seed?: unknown[]): HostInstance<Row> & { api: Api } => {
    const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
    if (seed) allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(seed) } as ChecklistResponse)
    // 行 JSON 每写一次计一次
    let saves = 0
    watch(() => allResponses.value.get(key), () => { saves += 1 }, { flush: 'sync' })
    const api = use({ allResponses, isReadonly: ref(false), projectId: 'proj-1' })
    return {
      // 两张表的行类型不同，harness 按联合行类型调用
      api: api as Api & HostInstance<Row>['api'],
      rows: () => api.rows.value as Row[],
      stored: () => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]')),
      rowSaves: () => saves,
    }
  }
}

const makePurchase = makeFor(useF2PurchaseInboundCheck, 'F2-33-rows')
const makeMaterial = makeFor(useF2MaterialUsageCheck, 'F2-34-rows')
const view = (r: Row) => [r.voucherNo, [r.counterpartAccount, r.counterpartDetail].filter(Boolean).join(' '), r.amount]
// 单列金额（取样本自己那一栏）
const expected = [
  ['0012', '1002 银行存款', 200],
  ['0012', '6111 投资收益', 100],
  ['0014', '多科目', 1000],
]

beforeEach(resetVoucherFillMocks)

for (const [title, make] of [['F2-33 采购入库', makePurchase], ['F2-34 材料领用', makeMaterial]] as const) {
  describe(`${title}：抽凭 / 挂凭回填走共享函数`, () => {
    voucherFillHostCases<Row>({
      make,
      idKey: 'id',
      view,
      expected,
      edit: (inst, id, value) => (inst.api as Api).updateRow(id, { remark: value } as never),
      editKey: 'remark',
      manualRow: { id: 'm1', seq: 1, voucherNo: '手-1', itemName: '手工' },
      oldRow: { seq: 1, voucherNo: '0012', amount: 1000, indexRef: 'F2-2' },
      oldRowKept: { indexRef: 'F2-2' },
    })
  })
}

describe('F2-33 / F2-34 回填细节', () => {
  it('回填时去掉开头的空白占位行，撤销到表空补一行空白行；对方科目不再写进供应商；抽样方法记在样本来源上', async () => {
    const inst = makePurchase()
    expect(inst.rows()).toHaveLength(1)
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1', method: 'systematic' })
    expect(inst.rows().map(r => [r.seq, r.voucherNo, r.party, r.counterpartAccount, r.sampleSource]))
      .toEqual([[1, '0012', '', '1002', '来自抽凭引擎 systematic']])
    expect(await inst.api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(inst.rows().map(r => [r.seq, r.voucherNo])).toEqual([[1, '']])
  })

  it('材料领用优先取贷方金额', async () => {
    const inst = makeMaterial()
    await inst.api.onEngineFilled({
      samples: [sample('fp-1', { debitAmount: null, creditAmount: '5000.00', pairing: null, counterpartAccount: '5001' })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.voucherNo, r.amount, r.counterpartAccount])).toEqual([['0012', 5000, '5001']])
  })
})
