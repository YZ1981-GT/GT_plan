/**
 * E1-23 货币资金收支检查 / E1-31 银行流水核对日记账接入共享回填函数
 * （spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * E1-23：一个对方科目一行（金额是该对方科目对应的那部分，原实现取对方分录金额）；抽凭两次、挂凭导入两次不重复；
 *        旧行同号同日同金额不再插入；年审阶段预审行改、删都不生效、保存按读入版本写回；其余 IPO 表也透传 `_gt`。
 * E1-31：一个样本一行（整笔银行分录金额，供与对账单逐笔匹配）；抽凭两次不重复；
 *        「替换本阶段抽凭行」只删本阶段抽凭填入的日记账行（原「替换」清空整张日记账）；撤销按批次删行。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useE1IpoSpecial } from '../useE1IpoSpecial'
import { E1_BANK_FLOW_PACK_KEY, useE1BankFlowReconcile } from '../useE1BankFlowReconcile'
import { hasLargeCheckContent, largeCheckLegacyKey, mapSampleToLargeCheckRow } from '../e1LargeCheckVoucherFill'
import type { SamplePairing } from '../shared/voucherCheckFill'

const LARGE = 'E1-ipo-E1-23-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const TWO: SamplePairing = {
  status: 'paired', basis: 'many_to_many', counterpart_summary: [],
  counterparts: [
    { account_code: '1122', account_name: '应收账款', amount: '800.00', line_fp: 'a' },
    { account_code: '6603', account_name: '财务费用', amount: '200.00', line_fp: 'b' },
  ],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '收回货款',
  accountCode: '1002', debitAmount: '1000.00', creditAmount: null, pairing: TWO, ...over,
})

const wrappers: VueWrapper[] = []

function setup<T>(fn: () => T): T {
  let api!: T
  wrappers.push(mount(defineComponent({ setup() { api = fn(); return () => h('div') } })))
  return api
}

function mkLarge(seed?: unknown[]) {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) allResponses.value.set(LARGE, { item_id: LARGE, conclusion: null, remark: JSON.stringify(seed) })
  const saveImmediate = vi.fn(async (_items: Array<{ item_id: string; remark: string }>) => {})
  const api = setup(() => useE1IpoSpecial({
    wpId: ref('wp-e1'), projectId: ref('proj-1'), allResponses, saveImmediate, debouncedSave: vi.fn(async () => {}),
    isReadonly: ref(false), sheetCode: 'E1-23',
    voucherFill: {
      projectId: 'proj-1', policy: 'expand', mapSampleToRow: mapSampleToLargeCheckRow,
      hasUserContent: hasLargeCheckContent, legacy: largeCheckLegacyKey,
    },
  } as never))
  return { api, allResponses, saveImmediate, fill: api.voucherFill! }
}

const storedLarge = (allResponses: Ref<Map<string, any>>) => JSON.parse(String(allResponses.value.get(LARGE)?.remark ?? '[]'))

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

afterEach(() => {
  while (wrappers.length) wrappers.pop()?.unmount()
})

describe('E1-23 收支检查走共享回填函数', () => {
  it('一个对方科目一行、金额是该对方科目的那部分；抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库', async () => {
    const { api, allResponses, fill } = mkLarge([])
    await fill.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    await fill.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-2' })
    await fill.onAttachImported([sample('fp-1')])
    await fill.onAttachImported([sample('fp-1')])
    // 读入时的一行空白模板行 + 两个对方科目各一行
    const filled = api.rows.value.filter(r => r.voucherNo)
    expect(filled.map(r => [r.direction, r.accountName, r.counterAccount, r.counterSubAccount, r.amount])).toEqual([
      ['收', '银行存款', '1122', '应收账款', 800],
      ['收', '银行存款', '6603', '财务费用', 200],
    ])
    const rows = storedLarge(allResponses).filter((r: any) => r.voucherNo)
    expect(rows.map((r: any) => r._gt)).toMatchObject([
      { lfp: 'fp-1', cp: '1122', b: 'b-1', src: ['engine', 'attach'] },
      { lfp: 'fp-1', cp: '6603', b: 'b-1', src: ['engine', 'attach'] },
    ])
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`；已录入的银行回单保留', async () => {
    const old = { id: 'old', voucherNo: '0007', date: '2025-06-15', amount: 1000, bankReceiptParty: '甲公司' }
    const { api, fill } = mkLarge([old])
    await fill.onEngineFilled({ samples: [sample('fp-1', { pairing: null, counterpartAccount: '1122' })], phase: 'final', batchId: 'b-1' })
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0]).toMatchObject({ id: 'old', bankReceiptParty: '甲公司' })
    expect((api.rows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })

  it('年审阶段预审行只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = {
      id: 'p1', voucherNo: '0007', date: '2025-06-15', amount: 1000, otherDoc: '回单 1',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }
    const { api, allResponses, fill } = mkLarge([prelim])
    await fill.ready()
    expect(fill.rowClass({ row: api.rows.value[0] })).toBe('gt-row-locked')
    api.updateCell('p1', 'otherDoc', '改了')
    api.removeRow('p1')
    expect(api.rows.value.map(r => [r.id, r.otherDoc])).toEqual([['p1', '回单 1']])
    api.rows.value[0].otherDoc = '被改了'
    await fill.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0008' })], phase: 'final' })
    expect(storedLarge(allResponses).find((r: any) => r.id === 'p1')).toMatchObject({ otherDoc: '回单 1' })
  })

  it('其余 IPO 表（没接共享回填函数）读写也透传 `_gt`', () => {
    const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    const key = 'E1-ipo-E1-28-rows'
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify([{ id: 'r1', voucherNo: 'X', _gt: { lfp: 'f', src: ['attach'] } }]) })
    const api = setup(() => useE1IpoSpecial({
      wpId: ref('wp'), projectId: ref('p'), allResponses, saveImmediate: vi.fn(async () => {}), debouncedSave: vi.fn(async () => {}),
      isReadonly: ref(false), sheetCode: 'E1-28',
    } as never))
    expect(api.voucherFill).toBeNull()
    expect((api.rows.value[0] as any)._gt).toMatchObject({ lfp: 'f', src: ['attach'] })
  })
})

describe('E1-31 银行流水核对日记账走共享回填函数', () => {
  function mkBank(seedJournal: unknown[] = []) {
    const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    allResponses.value.set(E1_BANK_FLOW_PACK_KEY, {
      item_id: E1_BANK_FLOW_PACK_KEY, conclusion: null, remark: JSON.stringify({ journalLines: seedJournal }),
    })
    const saveImmediate = vi.fn(async (_items: Array<{ item_id: string; remark: string }>) => {})
    const api = setup(() => useE1BankFlowReconcile({
      wpId: ref('wp-e1'), projectId: ref('proj-1'), allResponses, saveImmediate, debouncedSave: vi.fn(async () => {}),
      isReadonly: ref(false), bsDate: ref('2025-12-31'),
    } as never))
    return { api, allResponses, saveImmediate }
  }
  const journal = (allResponses: Ref<Map<string, any>>) =>
    JSON.parse(String(allResponses.value.get(E1_BANK_FLOW_PACK_KEY)?.remark ?? '{}')).journalLines ?? []

  it('一个样本一行（整笔银行分录金额，对方科目拼接）；抽凭两次不重复；`_gt` 随日记账行落库', async () => {
    const { api, allResponses } = mkBank()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008', debitAmount: null, creditAmount: '30.00', pairing: null, counterpartAccount: '2202' })], phase: 'final', batchId: 'b-1' })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-2' })
    expect(api.pack.value.journalLines.map(j => [j.voucherNo, j.counterAccount, j.debit, j.credit, j.source])).toEqual([
      ['0007', '1122/6603', 1000, 0, '抽凭'],
      ['0008', '2202', 0, 30, '抽凭'],
    ])
    expect(journal(allResponses)[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', b: 'b-1', src: ['engine'] })
  })

  it('「替换本阶段抽凭行」只删本阶段抽凭填入的日记账行，手工行保留；撤销按批次删行', async () => {
    const manual = { id: 'm1', date: '2025-03-01', voucherNo: '手-1', debit: 5, credit: 0, source: 'manual' }
    const { api } = mkBank([manual])
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(api.pack.value.journalLines.map(j => j.voucherNo)).toEqual(['手-1', '0009'])
    expect(await api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    expect(api.pack.value.journalLines.map(j => j.voucherNo)).toEqual(['手-1'])
  })
})
