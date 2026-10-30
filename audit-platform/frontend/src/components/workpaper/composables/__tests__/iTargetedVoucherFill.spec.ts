/**
 * I2-12 / I3-5 / I4-5 / I5-4 / I6-4 针对性检查表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（凭证检查表：一行一个对方科目）；另验：回填后记抽样说明与回填同一次保存，
 * 「保存」先序列化全部内容再逐项存（原实现逐项 await，存完行后父组件改了 allResponses、watch 整页重读，
 * 抽样说明 / 风险关注存进去的是重读出的旧值），I4-5 选取原因按测试原因逐行标注，I4-2 / I6-2 挂接不改年审阶段的预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useI2TargetedCheck } from '../useI2TargetedCheck'
import { useI3TargetedCheck } from '../useI3TargetedCheck'
import { useI4TargetedCheck } from '../useI4TargetedCheck'
import { useI5TargetedCheck } from '../useI5TargetedCheck'
import { useI6TargetedCheck } from '../useI6TargetedCheck'
import { noteEngineSampling } from '../assetVoucherFill'
import { ElMessageBox } from 'element-plus'
import { paired, resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

interface TargetedRow {
  rowId: string
  voucherNo: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  projectName: string
  selectionReason: string
  isSpecific: boolean
}
type Inst = HostInstance<TargetedRow> & { api: any; saved: (key: string) => unknown; responses: Ref<Map<string, any>> }

const asItem = (k: string, v: unknown) => ({ item_id: k, conclusion: null, remark: typeof v === 'string' ? v : JSON.stringify(v) })

/** 逐 item_id 保存的宿主（I3~I6）：父组件存一项就同步改 allResponses（与 GtI3Goodwill.handleChildSave 相同） */
function perItemHost(use: (ar: any, opts: any) => any, code: string) {
  const rowsKey = `${code}-rows`
  return function make(seed?: unknown[], extra: Record<string, unknown> = {}): Inst {
    const responses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    if (seed) responses.value.set(rowsKey, asItem(rowsKey, seed))
    for (const [k, v] of Object.entries(extra)) responses.value.set(k, asItem(k, v))
    const last = new Map<string, unknown>()
    if (seed) last.set(rowsKey, JSON.stringify(seed))
    const onSave = vi.fn((itemId: string, value: unknown) => {
      last.set(itemId, value)
      responses.value.set(itemId, asItem(itemId, value))
    })
    const api = use(responses, { onSave, projectId: 'proj-1', isReadonly: false, asOfYear: () => 2025 })
    return {
      api,
      responses,
      rows: () => api.rows.value,
      stored: () => JSON.parse(String(last.get(rowsKey) ?? '[]')),
      saved: (key: string) => last.get(key),
      rowSaves: () => onSave.mock.calls.filter(c => c[0] === rowsKey).length,
    }
  }
}

/** I2-12：整页一次 saveResponse(sheet, { 各项 })，父组件同样同步改 allResponses */
function makeI2(seed?: unknown[]): Inst {
  const rowsKey = 'I2-12-rows'
  const responses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed) responses.value.set(rowsKey, asItem(rowsKey, seed))
  const last = new Map<string, unknown>()
  if (seed) last.set(rowsKey, JSON.stringify(seed))
  const saveResponse = vi.fn(async (_sheet: string, data: Record<string, unknown>) => {
    for (const [k, v] of Object.entries(data)) {
      last.set(k, v)
      responses.value.set(k, asItem(k, v))
    }
  })
  const api = useI2TargetedCheck(responses, { saveResponse, projectId: 'proj-1', isReadonly: false }) as any
  return {
    api,
    responses,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(last.get(rowsKey) ?? '[]')),
    saved: (key: string) => last.get(key),
    rowSaves: () => saveResponse.mock.calls.filter(c => rowsKey in c[1]).length,
  }
}

const HOSTS: Array<[string, string, (seed?: unknown[], extra?: Record<string, unknown>) => Inst]> = [
  ['I2-12 开（研）发支出', 'I2-12', makeI2],
  ['I3-5 商誉', 'I3-5', perItemHost(useI3TargetedCheck, 'I3-5')],
  ['I4-5 长期待摊费用', 'I4-5', perItemHost(useI4TargetedCheck, 'I4-5')],
  ['I5-4 其他非流动资产', 'I5-4', perItemHost(useI5TargetedCheck, 'I5-4')],
  ['I6-4 研发费用', 'I6-4', perItemHost(useI6TargetedCheck, 'I6-4')],
]

const prelim = (over: Record<string, unknown>) => ({
  ...over, _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
})

beforeEach(resetVoucherFillMocks)

for (const [label, code, make] of HOSTS) {
  describe(`${label}针对性检查：抽凭 / 挂凭回填走共享函数`, () => {
    voucherFillHostCases<TargetedRow>({
      make: seed => make(seed),
      idKey: 'rowId',
      view: r => [r.voucherNo, [r.counterpartAccount, r.counterpartDetail].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
      edit: (inst, id, value) => (inst as Inst).api.updateRow(id, 'indexRef', value),
      editKey: 'indexRef',
      manualRow: { rowId: 'm1', voucherNo: '手-1' },
      oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, supportingDocs: '合同' },
      oldRowKept: { supportingDocs: '合同' },
    })

    it('回填后记进抽样说明的方法、样本量与填入行数（多科目展开后行数 ≠ 样本数），与回填同一次保存', async () => {
      const inst = make()
      const api = inst.api
      const twoCounterparts = sample('fp-1', { debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) })
      await api.onEngineFilled(
        { samples: [twoCounterparts, sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1' },
        (added: number) => noteEngineSampling(api.sampleMeta.value, { samplingMethod: 'mus', sampleSize: 7 }, added),
      )
      await nextTick()
      const meta = JSON.parse(String(inst.saved(`${code}-sample-meta`)))
      expect(meta).toMatchObject({ sampleMethod: 'mus', sampleSize: 7 })
      expect(meta.sampleProcess).toContain('抽凭引擎回填 3 行')
      expect(inst.stored().map((r: TargetedRow) => r.voucherNo)).toEqual(['0012', '0012', '0013'])
    })

    it('「替换本阶段抽凭行」要删的行已填核对内容（核对 1）：先确认，取消则底稿不动', async () => {
      const inst = make()
      await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
      await nextTick()
      inst.api.updateRow(inst.rows()[0].rowId, 'check1', '√')
      vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel' as never)
      const out = await inst.api.onEngineFilled({
        samples: [sample('fp-2', { voucherNo: '0013' })], phase: 'final', fillMode: 'replace', batchId: 'b-2',
      })
      expect(out.cancelled).toBe(true)
      expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
      expect(inst.rows().map(r => r.voucherNo)).toEqual(['0012'])
    })
  })
}

for (const [label, code, make] of HOSTS.slice(1)) {
  it(`${label}「保存」：未保存的抽样说明与风险关注不被存行触发的整页重读覆盖`, async () => {
    const inst = make()
    await nextTick()
    inst.api.sampleMeta.value.populationDesc = '本次改的总体说明'
    inst.api.sampleMeta.value.sampleProcess = '本次改的抽样过程'
    await inst.api.persistAll({ skipGate: true })
    await nextTick()
    expect(JSON.parse(String(inst.saved(`${code}-sample-meta`)))).toMatchObject({
      populationDesc: '本次改的总体说明', sampleProcess: '本次改的抽样过程',
    })
    expect(inst.api.sampleMeta.value.populationDesc).toBe('本次改的总体说明')
  })
}

describe('I4-5 / I6-4 专项', () => {
  it('I4-5 选取原因按测试原因逐行标注：高值样本标「大额」，未勾测试原因时仍为「高值必选」', async () => {
    const withReason = perItemHost(useI4TargetedCheck, 'I4-5')(undefined, { 'I4-5-sample-meta': { testReasons: ['大额'] } })
    await nextTick()
    await withReason.api.onEngineFilled({ samples: [sample('fp-1', { isHighValue: true })], phase: 'final', batchId: 'b-1' })
    expect(withReason.rows().map(r => [r.selectionReason, r.isSpecific])).toEqual([['大额', true]])
    const plain = perItemHost(useI4TargetedCheck, 'I4-5')()
    await plain.api.onEngineFilled({ samples: [sample('fp-1', { isHighValue: true })], phase: 'final', batchId: 'b-1' })
    expect(plain.rows().map(r => [r.selectionReason, r.isSpecific])).toEqual([['高值必选', true]])
  })

  it('I6-4 回填挂接 I6-2 研发项目，同一分录再抽不重复', async () => {
    const inst = perItemHost(useI6TargetedCheck, 'I6-4')(undefined, {
      'I6-2-detail-rows': [{ category: '智能平台', months: [100], aje: 0, rje: 0 }],
    })
    await nextTick()
    const s = sample('fp-1', { summary: '智能平台材料', pairing: undefined, counterpartAccount: '1403', counterpartAccountName: '原材料' })
    await inst.api.onEngineFilled({ samples: [s], phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled({ samples: [s], phase: 'final', batchId: 'b-2' })
    expect(inst.rows().map(r => [r.voucherNo, r.projectName, r.counterpartAccount])).toEqual([['0012', '智能平台', '1403']])
  })

  it('I4-2 挂接项目名不改年审阶段的预审行，挂接数只算实际改了的行', async () => {
    const inst = perItemHost(useI4TargetedCheck, 'I4-5')(
      [
        prelim({ rowId: 'p1', voucherNo: '0012', voucherDate: '2025-03-04', debitAmount: 1000, projectName: '', businessDesc: '办公室装修款' }),
        { rowId: 'n1', voucherNo: '0013', voucherDate: '2025-04-01', debitAmount: 50, projectName: '', businessDesc: '办公室装修二期' },
      ],
      { 'I4-2-rows': [{ projectName: '办公室装修' }] },
    )
    await inst.api.voucherFillReady()
    const r = inst.api.linkProjectsFromI42(false)
    expect(r.linked).toBe(1)
    expect(inst.rows().map(x => [x.rowId, x.projectName])).toEqual([['p1', ''], ['n1', '办公室装修']])
  })
})
