/**
 * F2-56 合同履约成本检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（单列凭证金额；旧行身份按凭证号 + 分配月份 + 凭证金额）；另验：
 * 回填时去掉空白占位行、撤销到表空补一行空白行；样本量与抽样方法随回填 / 撤销同步。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useF2ContractCostCheck } from '../useF2ContractCostCheck'
import type { ContractCostCheckSample } from '../useF2ContractCostCheckFormulas'
import type { ChecklistResponse } from '../useF2SpecialFormData'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const ROWS = 'F2-56-rows'
type F2Api = ReturnType<typeof useF2ContractCostCheck>

function make(seed?: unknown[]): HostInstance<ContractCostCheckSample> & { api: F2Api } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  if (seed) {
    allResponses.value.set(ROWS, { item_id: ROWS, conclusion: null, remark: JSON.stringify({ samples: seed }) } as ChecklistResponse)
  }
  // 行 JSON 每写一次计一次
  let saves = 0
  watch(() => allResponses.value.get(ROWS), () => { saves += 1 }, { flush: 'sync' })
  const api = useF2ContractCostCheck({ allResponses, isReadonly: ref(false), projectId: 'proj-1' })
  return {
    api,
    rows: () => api.sheet.value.samples,
    stored: () => JSON.parse(String(allResponses.value.get(ROWS)?.remark ?? '{"samples":[]}')).samples,
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('F2-56 抽凭回填走共享函数', () => {
  voucherFillHostCases<ContractCostCheckSample>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, r.offsetAccount, r.voucherAmount],
    // 本表只有一列凭证金额（取样本自己那一栏）
    expected: [
      ['0012', '1002 银行存款', 200],
      ['0012', '6111 投资收益', 100],
      ['0014', '多科目', 1000],
    ],
    edit: (inst, id, value) => (inst.api as unknown as F2Api).updateSample(id, { issueDesc: value }),
    editKey: 'issueDesc',
    manualRow: { id: 'm1', voucherNo: '手-1', projectName: '手工样本' },
    oldRow: { voucherNo: '0012', allocMonth: '2025-03-04', voucherAmount: 1000, contractDateNo: 'HT-1' },
    oldRowKept: { contractDateNo: 'HT-1' },
  })

  it('回填时去掉空白占位行；撤销到表空补一行空白行；样本量与抽样方法同步', async () => {
    const inst = make()
    expect(inst.rows()).toHaveLength(1)
    await inst.api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows().map(r => r.voucherNo)).toEqual(['0012', '0013'])
    expect(inst.api.params.value).toMatchObject({ sampleSize: 2, method: '抽凭引擎' })
    expect(await inst.api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(inst.rows()).toHaveLength(1)
    expect(inst.rows()[0].voucherNo).toBe('')
    expect(inst.api.params.value.sampleSize).toBe(0)
  })
})
