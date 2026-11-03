/**
 * G9-6 其他非流动金融资产凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 *
 * - 抽凭两次、挂凭导入两次都不重复；`_gt` 随行 JSON 落库，读回后还在；抽样参数里的本次样本量随抽凭行数；
 * - 映射：一个对方科目一行（金额是该对方科目那部分），金额在样本自己的借贷栏，配不上写「多科目」；
 * - 「替换本阶段抽凭行」只删本阶段抽凭填入的行；撤销按批次删行，同时来自挂凭的保留；
 * - 年审阶段预审行改不了，保存时按读入版本写回；旧行同号同日同金额不再插入。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useG9VoucherCheck } from '../useG9VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const ROWS = 'G9-voucher-rows'
const PARAMS = 'G9-vc-params'
const VK = JSON.stringify(['2025', '01', '2025-03-04', '记', '0012'])
const paired = (...cps: Array<[string, string, string]>): SamplePairing => ({
  status: 'paired', basis: 'one_to_one',
  counterparts: cps.map(([account_code, account_name, amount]) => ({ account_code, account_name, amount, line_fp: null })),
  counterpart_summary: [],
})

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0012', voucherDate: '2025-03-04', summary: '购入基金份额',
  debitAmount: '1000.00', creditAmount: null, pairing: paired(['1002', '银行存款', '1000.00']), ...over,
})

function mk(seedRows?: unknown[]) {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seedRows) put(ROWS, JSON.stringify(seedRows))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useG9VoucherCheck({
    wpId: ref('wp-9'), projectId: ref('proj-1'), year: ref(2025), allResponses, debouncedSave, isReadonly: ref(false),
  })
  return { api, allResponses, debouncedSave }
}

const stored = (allResponses: Ref<Map<string, ChecklistResponse>>, key = ROWS) => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]'))
const nos = (rows: Array<{ voucherNo: string }>) => rows.map(r => r.voucherNo)

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('G9-6 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库，读回后还在；本次样本量随抽凭行数', async () => {
    const { api, allResponses } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0013', debitAmount: '20.00', pairing: paired(['1002', '银行存款', '20.00']) })]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1', method: 'random' })
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    await nextTick()
    expect(nos(api.rows.value)).toEqual(['0012', '0013'])
    expect(api.rows.value.map(r => r.seq)).toEqual([1, 2])
    expect(stored(allResponses)[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    expect(stored(allResponses, PARAMS)).toMatchObject({ samplingMethod: 'random', currentSampleSize: 2 })
    const again = mk(stored(allResponses))
    expect((again.api.rows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })

  it('映射：一个对方科目一行（金额是该对方科目那部分），金额在样本自己的借贷栏，配不上写「多科目」', async () => {
    const { api } = mk()
    await api.onEngineFilled({
      samples: [
        sample('fp-1', { debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) }),
        sample('fp-2', { voucherNo: '0014', pairing: { status: 'multi', basis: null, counterparts: [], counterpart_summary: [] } }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(api.rows.value.map(r => [r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount, r.source])).toEqual([
      ['0012', '1002 银行存款', 0, 200, '抽凭'],
      ['0012', '6111 投资收益', 0, 100, '抽凭'],
      ['0014', '多科目', 1000, 0, '抽凭'],
    ])
  })

  it('「替换本阶段抽凭行」只删本阶段抽凭填入的行；撤销按批次删行，同时来自挂凭的保留', async () => {
    const { api } = mk([{ rowId: 'm1', voucherNo: '手-1', source: '手工' }])
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1' })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0013' })])
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0015' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    await nextTick()
    expect(nos(api.rows.value)).toEqual(['手-1', '0013', '0015'])
    expect(await api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    await nextTick()
    expect(nos(api.rows.value)).toEqual(['手-1', '0013'])
  })

  it('年审阶段预审行只读：改不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = {
      rowId: 'p1', voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, remark: '已核对', checkOriginal: true,
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }
    const { api, allResponses, debouncedSave } = mk([prelim])
    await api.voucherFillReady()
    expect(api.voucherRowClass({ row: api.rows.value[0] })).toBe('gt-row-locked')
    api.updateRow('p1', { remark: '改了' })
    expect(api.rows.value[0].remark).toBe('已核对')
    expect(debouncedSave.mock.calls.filter(c => c[0] === ROWS)).toHaveLength(0)
    api.rows.value[0].remark = '被改了'
    await api.onEngineFilled({ samples: [sample('fp-9', { voucherNo: '0020' })], phase: 'final', batchId: 'b-1' })
    expect(stored(allResponses)[0]).toMatchObject({ rowId: 'p1', remark: '已核对' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对结果保留', async () => {
    const old = { rowId: 'old', voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, checkOriginal: true, source: '抽凭' }
    const { api } = mk([old])
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    await nextTick()
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0]).toMatchObject({ rowId: 'old', checkOriginal: true })
    expect((api.rows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
