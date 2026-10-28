/**
 * D6-6 合同资产检查表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 抽凭进区块(1)；抽凭两次、挂凭导入两次都不重复；`_gt` 随行 JSON 落库；挂凭导入按凭证日期分区；
 * - 配上两个对方科目按对方科目展开、金额是各自那部分；配不上一行「多科目」（原宿主按对方分录展开并翻转金额）；
 * - 「替换本阶段抽凭行」只删区块(1)本阶段抽凭填入的行；撤销按批次删行；
 * - 年审阶段预审行改、删都不生效，保存时按读入版本写回；旧行同号同日同金额不再插入。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useD6Inspection } from '../useD6Inspection'
import type { ChecklistResponse } from '../useD6FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const B1 = 'D6-6-block1-rows'
const B2 = 'D6-6-block2-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '6001', account_name: '主营业务收入', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '确认合同资产',
  debitAmount: '1000.00', creditAmount: null, pairing: PAIRED, ...over,
})

const blank = (over: Record<string, unknown>) => ({
  rowId: 'r', customerName: '', date: '', voucherNo: '', businessContent: '', counterAccount: '', counterDetail: '',
  debitAmount: 0, creditAmount: 0, supportDoc: '', check1: '', check2: '', check3: '', check4: '', check5: '',
  indexRef: '', isAbnormal: '否', remark: '', ...over,
})

function mk(seed: { b1?: unknown[]; b2?: unknown[] } = {}) {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed.b1) put(B1, JSON.stringify(seed.b1))
  if (seed.b2) put(B2, JSON.stringify(seed.b2))
  const saveImmediate = vi.fn(async (id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useD6Inspection({
    allResponses, wpId: ref('wp-6'), projectId: ref('proj-1'), saveImmediate, debouncedSave,
    isReadonly: false, bsDate: () => '2025-12-31',
  })
  return { api, allResponses, saveImmediate, debouncedSave }
}

const stored = (allResponses: Ref<Map<string, ChecklistResponse>>, key: string) => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]'))
const nos = (rows: Array<{ voucherNo: string }>) => rows.map(r => r.voucherNo)

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('D6-6 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库；挂凭导入按凭证日期分区', async () => {
    const { api, allResponses } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', debitAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' }, { tables: ['block1'] })
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' }, { tables: ['block1'] })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1'), sample('fp-9', { voucherNo: '0101', voucherDate: '2026-01-10' })])
    await nextTick()
    expect(nos(api.block1Rows.value)).toEqual(['0007', '0008'])
    expect(nos(api.block2Rows.value)).toEqual(['0101'])
    expect(stored(allResponses, B1)[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
  })

  it('配上两个对方科目按对方科目展开、金额是各自那部分；配不上一行「多科目」', async () => {
    const two: SamplePairing = {
      status: 'paired', basis: 'many_to_many', counterpart_summary: [],
      counterparts: [
        { account_code: '6001', account_name: '主营业务收入', amount: '800.00', line_fp: 'a' },
        { account_code: '2221', account_name: '应交税费', amount: '200.00', line_fp: 'b' },
      ],
    }
    const multi: SamplePairing = { status: 'multi', basis: null, counterparts: [], counterpart_summary: [] }
    const { api } = mk()
    const samples = [sample('fp-1', { pairing: two }), sample('fp-2', { voucherNo: '0008', pairing: multi })]
    await api.onEngineFilled({ samples, phase: 'final' }, { tables: ['block1'] })
    await api.onEngineFilled({ samples, phase: 'final' }, { tables: ['block1'] })
    expect(api.block1Rows.value.map(r => [r.voucherNo, r.counterAccount, r.counterDetail, r.debitAmount, r.creditAmount])).toEqual([
      ['0007', '6001', '主营业务收入', 800, 0],
      ['0007', '2221', '应交税费', 200, 0],
      ['0008', '多科目', '', 1000, 0],
    ])
  })

  it('「替换本阶段抽凭行」只删区块(1)本阶段抽凭填入的行；撤销按批次删行，同时来自挂凭的保留', async () => {
    const { api } = mk({ b1: [blank({ rowId: 'm1', voucherNo: '手-1' })] })
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' }, { tables: ['block1'] })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' }, { tables: ['block1'] })
    await nextTick()
    expect(nos(api.block1Rows.value)).toEqual(['手-1', '0008', '0009'])
    expect(await api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    await nextTick()
    expect(nos(api.block1Rows.value)).toEqual(['手-1', '0008'])
  })

  it('年审阶段预审行只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = blank({
      rowId: 'p1', voucherNo: '0007', date: '2025-06-15', debitAmount: 1000, check1: '✓',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    })
    const { api, debouncedSave } = mk({ b1: [prelim] })
    await api.voucherFillReady()
    expect(api.voucherRowClass({ row: api.block1Rows.value[0] })).toBe('gt-row-locked')
    api.updateSampleCell(1, 'p1', 'check1', '')
    api.removeSample(1, 'p1')
    expect(api.block1Rows.value.map(r => [r.rowId, r.check1])).toEqual([['p1', '✓']])
    // 抽样参数的深度 watch 会自己存一次参数，这里只看区块(1)的行有没有被写
    const block1Saves = () => debouncedSave.mock.calls.filter(c => c[0] === B1)
    expect(block1Saves()).toHaveLength(0)
    api.block1Rows.value[0].check2 = '✓'
    api.addSample(1)
    expect(JSON.parse(String(block1Saves().at(-1)?.[1].remark))[0]).toMatchObject({ rowId: 'p1', check2: '' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对结果保留', async () => {
    const old = blank({ rowId: 'old', voucherNo: '0007', date: '2025-06-15', debitAmount: 1000, check1: '✓' })
    const { api } = mk({ b1: [old] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, { tables: ['block1'] })
    await nextTick()
    expect(api.block1Rows.value).toHaveLength(1)
    expect(api.block1Rows.value[0]).toMatchObject({ rowId: 'old', check1: '✓' })
    expect((api.block1Rows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
