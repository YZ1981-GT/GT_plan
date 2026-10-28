/**
 * H3-5 投资性房地产增减检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 * 通用五条用例见 voucherFillHostHarness（成本模式；一个样本一行，对方科目按配对用「/」拼接）；另验：
 * 成本 / 公允两张表按当前计量模式回填，替换只动当前模式那张表；按分录指纹去重（原实现按凭证号去重，
 * 同号的另一条分录被丢掉）；金额取样本自己那一栏，没有借方时取贷方。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useH3AdditionCheck, type H3AdditionCostRow } from '../useH3AdditionCheck'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const COST = 'H3-5-cost-rows'
const FAIR = 'H3-5-fair-rows'

function make(seed?: unknown[], model: 'cost' | 'fair_value' = 'cost', fairSeed?: unknown[]) {
  const store = new Map<string, any>()
  if (seed) store.set(COST, JSON.parse(JSON.stringify(seed)))
  if (fairSeed) store.set(FAIR, JSON.parse(JSON.stringify(fairSeed)))
  const allResponses = ref(store)
  const setValue = vi.fn((id: string, value: unknown) => { store.set(id, JSON.parse(JSON.stringify(value))) })
  const api = useH3AdditionCheck({
    allResponses: computed(() => allResponses.value) as any,
    wpId: ref('wp-h3'), projectId: ref('proj-1'),
    getValue: (id: string) => store.get(id), setValue, saveImmediate: async () => {},
    measurementModel: ref(model),
  })
  const inst: HostInstance<H3AdditionCostRow> & { api: typeof api; store: Map<string, any> } = {
    api, store,
    rows: () => api.costRows.value,
    stored: () => (store.get(COST) ?? []) as any[],
    rowSaves: () => setValue.mock.calls.filter(c => c[0] === COST).length,
  }
  return inst
}

beforeEach(resetVoucherFillMocks)

describe('H3-5 投资性房地产增减检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<H3AdditionCostRow>({
    make: seed => make(seed),
    idKey: 'rowId',
    view: r => [r.voucherNo, r.creditAccount, r.originalCost],
    expected: [['0012', '1002/6111 银行存款/投资收益', 300], ['0014', '多科目', 1000]],
    edit: (inst, id, value) => {
      const api = (inst as ReturnType<typeof make>).api
      api.updateCell(api.costRows.value.findIndex(r => r.rowId === id), 'remark', value)
    },
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1', assetName: '手工项' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', originalCost: 1000, supportingDocs: '合同 HT-1' },
    oldRowKept: { supportingDocs: '合同 HT-1' },
  })

  it('成本模式：被投资方取对方单位、对方科目带名称；没有借方时取贷方；同一张凭证的两条分录各成一行', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { voucherNo: 'V1', counterpartName: 'ABC置业', debitAmount: '500000.00', abnormal: false, selectionReason: '大额' }),
        sample('fp-2', { voucherNo: 'V1', counterpartName: 'ABC置业', debitAmount: null, creditAmount: '200000.00', abnormal: true,
          pairing: { status: 'paired', basis: 'one_to_one', counterparts: [{ account_code: '1122', account_name: '应收账款', amount: '200000.00', line_fp: null }], counterpart_summary: [] } }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.voucherNo, r.assetName, r.creditAccount, r.originalCost, r.isAbnormal, r.remark])).toEqual([
      ['V1', 'ABC置业', '1002 银行存款', 500000, 'N', '大额'],
      ['V1', 'ABC置业', '1122 应收账款', 200000, 'Y', '来源:抽凭'],
    ])
  })

  it('公允模式：回填进公允表（期末余额 = 公允价值），替换只动公允表，成本表不动', async () => {
    const inst = make([{ rowId: 'c1', voucherNo: 'C-1', originalCost: 10 }], 'fair_value')
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { debitAmount: '800000.00' })], phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0013', debitAmount: '9.00' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(inst.api.fairRows.value.map(r => [r.voucherNo, r.creditAccount, r.fairValue, r.endBalance])).toEqual([['0013', '1002', 9, 9]])
    expect(inst.api.costRows.value.map(r => r.voucherNo)).toEqual(['C-1'])
    expect((inst.store.get(FAIR) as any[])[0]._gt).toMatchObject({ lfp: 'fp-2', b: 'b-2' })
  })
})
