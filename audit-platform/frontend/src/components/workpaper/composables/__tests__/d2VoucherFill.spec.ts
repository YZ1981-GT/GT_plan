/**
 * D2-7 凭证检查表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 抽凭两次、挂凭导入两次都不重复；同一分录只留一行，来源记为两者；`_gt` 随行 JSON 落库；
 * - 按凭证日期分到本期 / 期后；已在某区的分录再次回填仍进那一区（期末日改过也不重复）；
 * - 「追加」不再整表替换（原来除「合并」外一律替换）；「替换本阶段抽凭行」只删本阶段抽凭填入的行；
 * - 按后端配对结果展开 / 标「多科目」；撤销按批次删行；年审阶段预审行改、删都不生效；
 * - 旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`。
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
import { useD2VoucherCheckEnhanced } from '../useD2VoucherCheckEnhanced'
import { D2_SAVE_ITEMS_KEY } from '../d2InjectionKeys'
import type { SamplePairing } from '../shared/voucherCheckFill'

const CUR = 'D2-vc-current-rows'
const POST = 'D2-vc-post-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '6001', account_name: '主营业务收入', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '销售',
  debitAmount: '1000.00', creditAmount: null, pairing: PAIRED, ...over,
})

const blank = (over: Record<string, unknown>) => ({
  rowId: 'r', seq: 1, customerName: '', voucherDate: '', voucherNo: '', businessContent: '',
  counterpartAccount: '', counterpartDetail: '', debitAmount: 0, creditAmount: 0, supportingDoc: '',
  check1: '', check2: '', check3: '', check4: '', check5: '', indexRef: '', isAbnormal: '', remark: '',
  attachments: [], ...over,
})

const wrappers: VueWrapper[] = []

function mk(seed: { current?: unknown[]; post?: unknown[] } = {}) {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed.current) allResponses.value.set(CUR, { item_id: CUR, conclusion: null, remark: JSON.stringify(seed.current) })
  if (seed.post) allResponses.value.set(POST, { item_id: POST, conclusion: null, remark: JSON.stringify(seed.post) })
  const bsDate = ref('2025-12-31')
  const saveSpy = vi.fn(async (_items: Array<{ item_id: string; remark: string }>) => {})
  let api!: ReturnType<typeof useD2VoucherCheckEnhanced>
  wrappers.push(mount(defineComponent({
    setup() {
      api = useD2VoucherCheckEnhanced({ allResponses, isReadonly: ref(false), bsDate, projectId: 'proj-1' })
      return () => h('div')
    },
  }), { global: { provide: { [D2_SAVE_ITEMS_KEY as symbol]: saveSpy } } }))
  return { api, allResponses, bsDate, saveSpy }
}

const stored = (allResponses: Ref<Map<string, any>>, key = CUR) => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]'))

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

afterEach(() => {
  while (wrappers.length) wrappers.pop()?.unmount()
})

describe('D2-7 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；同一分录只留一行、来源记为两者；`_gt` 随行落库', async () => {
    const { api, allResponses, saveSpy } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', debitAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', fillMode: 'append', batchId: 'b-1' })
    await api.onEngineFilled({ samples: batch, phase: 'final', fillMode: 'append', batchId: 'b-2' })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    expect(api.currentRows.value.map(r => [r.seq, r.voucherNo])).toEqual([[1, '0007'], [2, '0008']])
    const rows = stored(allResponses)
    expect(rows).toHaveLength(2)
    expect(rows[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    expect(rows[1]._gt).toMatchObject({ lfp: 'fp-2', src: ['engine'] })
    // 落库走宿主注入的保存桥
    expect(saveSpy).toHaveBeenCalled()
    expect(JSON.parse(saveSpy.mock.calls.at(-1)![0][0].remark)[0]._gt.lfp).toBe('fp-1')
  })

  it('读回（别的页签 / 在线编辑写回）后 `_gt` 还在', async () => {
    const first = mk()
    await first.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const again = mk({ current: stored(first.allResponses) })
    expect((again.api.currentRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', vk: VK, b: 'b-1' })
  })

  it('按凭证日期分到本期 / 期后；已在某区的分录期末日改过再回填也不在另一区重复', async () => {
    const { api, bsDate } = mk()
    const post = sample('fp-9', { voucherNo: '0101', voucherDate: '2026-01-05' })
    await api.onEngineFilled({ samples: [sample('fp-1'), post], phase: 'final' })
    expect(api.currentRows.value.map(r => r.voucherNo)).toEqual(['0007'])
    expect(api.postRows.value.map(r => r.voucherNo)).toEqual(['0101'])
    bsDate.value = '2026-01-31'
    await api.onEngineFilled({ samples: [post], phase: 'final' })
    expect([api.currentRows.value.length, api.postRows.value.length]).toEqual([1, 1])
  })

  it('「追加」不再整表替换；「替换本阶段抽凭行」只删本阶段抽凭填入的行，手工行与挂凭行保留', async () => {
    const { api } = mk({ current: [blank({ rowId: 'm1', voucherNo: '手-1' })] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', fillMode: 'append', batchId: 'b-1' })
    await api.onAttachImported([sample('fp-3', { voucherNo: '0009' })])
    await api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0008' })], phase: 'final', fillMode: 'append', batchId: 'b-2' })
    expect(api.currentRows.value.map(r => r.voucherNo)).toEqual(['手-1', '0007', '0009', '0008'])
    await api.onEngineFilled({ samples: [sample('fp-4', { voucherNo: '0010' })], phase: 'final', fillMode: 'replace', batchId: 'b-3' })
    expect(api.currentRows.value.map(r => [r.seq, r.voucherNo])).toEqual([[1, '手-1'], [2, '0009'], [3, '0010']])
  })

  it('配上两个对方科目：展开两行、金额是各自那部分；配不上：一行「多科目」；再回填都不重复', async () => {
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
    await api.onEngineFilled({ samples, phase: 'final' })
    await api.onEngineFilled({ samples, phase: 'final' })
    expect(api.currentRows.value.map(r => [r.voucherNo, r.counterpartAccount, r.counterpartDetail, r.debitAmount])).toEqual([
      ['0007', '6001', '主营业务收入', 800],
      ['0007', '2221', '应交税费', 200],
      ['0008', '多科目', '', 1000],
    ])
  })

  it('映射：贷方样本进贷方栏、对方科目来自后端配对；挂凭导入的来源写「挂凭导入」', async () => {
    const { api } = mk()
    await api.onAttachImported([sample('fp-c', { debitAmount: null, creditAmount: '300.00' })])
    const [r] = api.currentRows.value
    expect([r.debitAmount, r.creditAmount, r.counterpartAccount, r.counterpartDetail, r.businessContent, r.source])
      .toEqual([0, 300, '6001', '主营业务收入', '销售', '挂凭导入'])
  })

  it('撤销按批次删行：同时来自挂凭的保留；后端撤销失败不删', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => false })).toBe(false)
    expect(api.currentRows.value).toHaveLength(2)
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(api.currentRows.value.map(r => [r.seq, r.voucherNo])).toEqual([[1, '0008']])
    expect((api.currentRows.value[0] as any)._gt).toMatchObject({ b: null, src: ['attach'] })
  })

  it('年审阶段预审行只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = blank({
      rowId: 'p1', voucherNo: '0007', voucherDate: '2025-06-15', debitAmount: 1000, check1: '一致',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    })
    const { api, allResponses } = mk({ current: [prelim] })
    await api.voucherFillReady()
    const row = api.currentRows.value[0]
    expect(api.isVoucherRowLocked(row)).toBe(true)
    expect(api.voucherRowClass({ row })).toBe('gt-row-locked')
    api.updateRow('p1', 'check1', '不一致')
    api.removeRow('p1')
    expect(api.currentRows.value.map(r => [r.rowId, r.check1])).toEqual([['p1', '一致']])
    api.currentRows.value[0].check1 = '被改了'
    api.saveToResponses()
    expect(stored(allResponses)[0]).toMatchObject({ rowId: 'p1', check1: '一致' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对结果保留', async () => {
    const old = blank({ rowId: 'old', voucherNo: '0007', voucherDate: '2025-06-15', debitAmount: 1000, check1: '一致' })
    const { api } = mk({ current: [old] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    expect(api.currentRows.value).toHaveLength(1)
    expect(api.currentRows.value[0]).toMatchObject({ rowId: 'old', check1: '一致' })
    expect((api.currentRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
