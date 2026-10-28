/**
 * 宿主接入共享回填函数的通用用例（spec voucher-identity-writeback-and-audit-phase 任务 11~13）
 *
 * 单表凭证检查宿主（行存一个 JSON）共用五条用例：抽凭 / 挂凭导入两次都不重复且 `_gt` 落库读回、
 * 一个对方科目一行（金额在样本自己的借贷栏，配不上写「多科目」）、替换只删本阶段抽凭行与撤销按批次、
 * 年审阶段预审行只读并按读入版本写回、旧行同号同日同金额不再插入。宿主差异（字段名、改行入口、
 * 单列金额）由 `HostHarness` 给。调用方自己 vi.mock `@/utils/http` 与 `element-plus`（见各宿主 spec）。
 */
import { expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import type { SamplePairing } from '../shared/voucherCheckFill'

export const VK = JSON.stringify(['2025', '01', '2025-03-04', '记', '0012'])

export const paired = (...cps: Array<[string, string, string]>): SamplePairing => ({
  status: 'paired', basis: 'one_to_one',
  counterparts: cps.map(([account_code, account_name, amount]) => ({ account_code, account_name, amount, line_fp: null })),
  counterpart_summary: [],
})

export const MULTI: SamplePairing = { status: 'multi', basis: null, counterparts: [], counterpart_summary: [] }

/** 引擎 / 挂凭回拉样本：缺省借方 1000、配对到银行存款 */
export const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0012', voucherDate: '2025-03-04', summary: '抽凭样本',
  debitAmount: '1000.00', creditAmount: null, pairing: paired(['1002', '银行存款', '1000.00']), ...over,
})

export interface HostInstance<R> {
  api: {
    onEngineFilled: (p: any, scope?: any) => Promise<{ cancelled: boolean; added: number }>
    onAttachImported: (s: any[], scope?: any) => Promise<unknown>
    onUndoRequest: (p: any) => Promise<boolean>
    voucherFillReady: () => Promise<unknown>
    voucherRowClass: (a: { row: R }) => string
  }
  rows: () => R[]
  stored: () => any[]
  /** 行 JSON 被保存的次数 */
  rowSaves: () => number
}

export interface HostHarness<R> {
  make: (seed?: unknown[]) => HostInstance<R>
  /** 行主键字段名 */
  idKey: string
  /** 映射用例看的列：凭证号、对方科目、借方、贷方（单列金额的宿主给出它的写法） */
  view: (r: R) => unknown[]
  /**
   * 映射用例的预期（样本：贷方 300 配对银行存款 200 + 投资收益 100；凭证 0014 借方 1000 多科目）。
   * 缺省按「凭证号、`编码 名称`、借、贷」。
   */
  expected?: unknown[][]
  /** 宿主改行入口（改一个文本字段） */
  edit: (inst: HostInstance<R>, id: string, value: string) => void
  /** 改行入口改的字段名（读回比较用） */
  editKey: string
  /** 宿主的手工行（seed JSON 原样）：替换用例里不应被删 */
  manualRow: Record<string, unknown>
  /** 旧抽凭行（没有 `_gt`）：凭证号 0012、日期 2025-03-04、借方 1000，外加一项已填核对内容 */
  oldRow: Record<string, unknown>
  /** 旧行读回后应保留的核对内容 */
  oldRowKept: Record<string, unknown>
  /** 抽凭时额外的引擎载荷（如多表宿主的范围） */
  scope?: Record<string, unknown>
  /** 行上的凭证号（缺省读 `voucherNo`；凭证号与日期拼在一列的宿主给出取法，如 H10-4 凭证索引） */
  noOf?: (r: R) => unknown
  /**
   * 表里没有凭证号 / 日期 / 金额列（I2-9 人员、I2-10 工时：凭证信息只在备注 / 附件索引里），旧行（没有 `_gt`）认不出是
   * 哪笔分录：旧行原样保留、另起一行（第五条用例按此断言）
   */
  noLegacy?: boolean
}

export function resetVoucherFillMocks(): void {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
}

const DEFAULT_EXPECTED = [
  ['0012', '1002 银行存款', 0, 200],
  ['0012', '6111 投资收益', 0, 100],
  ['0014', '多科目', 1000, 0],
]

export function voucherFillHostCases<R>(h: HostHarness<R>): void {
  const no = (r: R) => (h.noOf ? h.noOf(r) : (r as Record<string, unknown>).voucherNo)
  const meta = (r: unknown) => (r as Record<string, unknown>)._gt as Record<string, unknown> | undefined

  it('抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库，读回后还在', async () => {
    const inst = h.make()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0013', debitAmount: '20.00', pairing: paired(['1002', '银行存款', '20.00']) })]
    await inst.api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1', ...h.scope })
    await inst.api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2', ...h.scope })
    await inst.api.onAttachImported([sample('fp-1')])
    await inst.api.onAttachImported([sample('fp-1')])
    await nextTick()
    expect(inst.rows().map(no)).toEqual(['0012', '0013'])
    expect(meta(inst.stored()[0])).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    const again = h.make(inst.stored())
    expect(meta(again.rows()[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })

  it('映射：一个对方科目一行（金额是该对方科目那部分），金额在样本自己的借贷栏，配不上写「多科目」', async () => {
    const inst = h.make()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) }),
        sample('fp-2', { voucherNo: '0014', pairing: MULTI }),
      ],
      phase: 'final', batchId: 'b-1', ...h.scope,
    })
    expect(inst.rows().map(h.view)).toEqual(h.expected ?? DEFAULT_EXPECTED)
  })

  it('「替换本阶段抽凭行」只删本阶段抽凭填入的行；撤销按批次删行，同时来自挂凭的保留', async () => {
    const inst = h.make([h.manualRow])
    const manualNo = no(h.manualRow as unknown as R)
    await inst.api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1', ...h.scope })
    await inst.api.onAttachImported([sample('fp-2', { voucherNo: '0013' })])
    await inst.api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0015' })], phase: 'final', fillMode: 'replace', batchId: 'b-2', ...h.scope })
    await nextTick()
    expect(inst.rows().map(no)).toEqual([manualNo, '0013', '0015'])
    expect(await inst.api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    await nextTick()
    expect(inst.rows().map(no)).toEqual([manualNo, '0013'])
  })

  it('年审阶段预审行只读：改不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = { ...h.oldRow, [h.idKey]: 'p1', [h.editKey]: '已核对', _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const inst = h.make([prelim])
    await inst.api.voucherFillReady()
    expect(inst.api.voucherRowClass({ row: inst.rows()[0] })).toContain('gt-row-locked')
    const before = inst.rowSaves()
    h.edit(inst, 'p1', '改了')
    expect((inst.rows()[0] as Record<string, unknown>)[h.editKey]).toBe('已核对')
    expect(inst.rowSaves()).toBe(before)
    ;(inst.rows()[0] as Record<string, unknown>)[h.editKey] = '被改了'
    await inst.api.onEngineFilled({ samples: [sample('fp-9', { voucherNo: '0020' })], phase: 'final', batchId: 'b-1', ...h.scope })
    expect(inst.stored()[0]).toMatchObject({ [h.idKey]: 'p1', [h.editKey]: '已核对' })
  })

  it(h.noLegacy
    ? '旧行（没有 `_gt`）表里没有凭证号列、认不出是哪笔分录：原样保留，另起一行'
    : '旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对内容保留', async () => {
    const inst = h.make([{ ...h.oldRow, [h.idKey]: 'old' }])
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1', ...h.scope })
    await nextTick()
    if (h.noLegacy) {
      expect(inst.rows()).toHaveLength(2)
      expect(inst.rows()[0]).toMatchObject({ [h.idKey]: 'old', ...h.oldRowKept })
      expect(meta(inst.rows()[0])).toBeUndefined()
      expect(meta(inst.rows()[1])).toMatchObject({ lfp: 'fp-1', ph: 'final', src: ['engine'] })
      return
    }
    expect(inst.rows()).toHaveLength(1)
    expect(inst.rows()[0]).toMatchObject({ [h.idKey]: 'old', ...h.oldRowKept })
    expect(meta(inst.rows()[0])).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
}
