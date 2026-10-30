/**
 * K 循环「一笔样本一行」的宿主接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 13）：
 * K5-6 未决诉讼（useK5Litigation）、K8-6 / K8-7 截止测试（useK8Cutoff）、K8-5 合同费用摊销（useK8ContractAmortization）、
 * K10-6 其他收益检查（useK10Checks）。每个宿主跑通用五条用例（对方科目按配对用「/」拼接，金额取样本自己那一栏、带符号），
 * 外加各自的映射：诉讼案件名取摘要、截止测试支出凭单一侧留空、合同行记凭证索引、其他收益检查备注记凭证号。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useK5Litigation, type K5LitigationRow } from '../useK5Litigation'
import { useK8Cutoff, type K8CutoffRow } from '../useK8Cutoff'
import { useK8ContractAmortization, type K8AmortRow } from '../useK8ContractAmortization'
import { useK10Checks, type K10IncomeCheckRow } from '../useK10Checks'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

beforeEach(resetVoucherFillMocks)

// ─── K5-6 未决诉讼 ───────────────────────────────────────────────────────────
type K5Api = ReturnType<typeof useK5Litigation>
function makeK5(seed?: unknown[]): HostInstance<K5LitigationRow> & { api: K5Api } {
  const allResponses = ref(new Map<string, any>())
  if (seed) allResponses.value.set('K5-6-rows', { item_id: 'K5-6-rows', remark: JSON.stringify(seed) })
  let saves = 0
  const api = useK5Litigation({
    allResponses, projectId: 'proj-1', readonly: false,
    saveResponse: async (field, value) => {
      if (field === '6-rows') saves += 1
      allResponses.value.set(`K5-${field}`, { item_id: `K5-${field}`, ...value })
    },
  })
  return {
    api: api as unknown as HostInstance<K5LitigationRow>['api'] & K5Api,
    rows: () => api.litigationRows.value,
    stored: () => JSON.parse(String(allResponses.value.get('K5-6-rows')?.remark ?? '[]')),
    rowSaves: () => saves,
  }
}

describe('K5-6 未决诉讼：一笔样本一个案件行', () => {
  voucherFillHostCases<K5LitigationRow>({
    make: makeK5,
    idKey: 'rowId',
    noOf: r => r.voucherRef,
    view: r => [r.voucherRef, r.remark.includes('抽凭引擎回填') ? '抽凭' : r.remark, r.amount],
    expected: [['0012', '抽凭', 300], ['0014', '抽凭', 1000]],
    edit: (inst, id, value) => (inst.api as unknown as K5Api).updateCell(id, 'lawyerOpinion', value),
    editKey: 'lawyerOpinion',
    manualRow: { rowId: 'm1', caseName: '手工案件', voucherRef: '手-1' },
    oldRow: { caseName: '旧案件', voucherRef: '0012', voucherDate: '2025-03-04', amount: 1000, lawyerOpinion: '律师意见' },
    oldRowKept: { lawyerOpinion: '律师意见' },
  })

  it('案件名取摘要、凭证号与日期；败诉可能性 / 预计损失不代填，备注写明待办', async () => {
    const inst = makeK5()
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '甲公司诉乙公司合同纠纷' })], phase: 'final', batchId: 'b-1' })
    expect(inst.rows()[0]).toMatchObject({
      caseName: '甲公司诉乙公司合同纠纷', voucherRef: '0012', voucherDate: '2025-03-04', amount: 1000,
      lossLikelihood: '', estimatedLoss: 0, seqNo: 1,
    })
    expect(inst.rows()[0].remark).toContain('待结合律师意见判断败诉可能性')
  })
})

// ─── K8-6 / K8-7 截止测试 ─────────────────────────────────────────────────────
type K8Api = ReturnType<typeof useK8Cutoff>
function makeK8(seed?: unknown[]): HostInstance<K8CutoffRow> & { api: K8Api } {
  const allResponses = ref(new Map<string, any>())
  if (seed) allResponses.value.set('K8-7-rows', { item_id: 'K8-7-rows', remark: JSON.stringify(seed) })
  let saves = 0
  const api = useK8Cutoff({
    direction: 'S2V', allResponses, projectId: ref('proj-1'), wpId: ref('wp-1'),
    periodEnd: ref('2025-12-31'), isReadonly: ref(false),
    onSave: (itemId, value) => {
      if (itemId === 'K8-7-rows') saves += 1
      allResponses.value.set(itemId, { item_id: itemId, remark: typeof value === 'string' ? value : JSON.stringify(value) })
    },
  })
  return {
    api: api as unknown as HostInstance<K8CutoffRow>['api'] & K8Api,
    rows: () => api.samples.value,
    stored: () => JSON.parse(String(allResponses.value.get('K8-7-rows')?.remark ?? '[]')),
    rowSaves: () => saves,
  }
}

describe('K8-6 / K8-7 截止测试：一个样本一行（记账凭证一侧）', () => {
  voucherFillHostCases<K8CutoffRow>({
    make: makeK8,
    idKey: 'rowKey',
    view: r => [r.voucherNo, r.offsetAccount, r.amount],
    expected: [['0012', '1002/6111 银行存款/投资收益', 300], ['0014', '多科目', 1000]],
    edit: (inst, id, value) => (inst.api as unknown as K8Api).updateCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowKey: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', bookDate: '2025-03-04', amount: 1000, sourceDate: '2025-03-03' },
    oldRowKept: { sourceDate: '2025-03-03' },
  })

  it('支出凭单一侧留空待查原件（原实现把记账凭证的号、日期、金额抄进支出凭单三列，截止结论恒为正常）', async () => {
    const inst = makeK8()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const row = inst.rows()[0]
    expect([row.voucherNo, row.bookDate, row.amount, row.sourceVoucherNo, row.sourceDate, row.sourceAmount]).toEqual(['0012', '2025-03-04', 1000, '', '', 0])
    expect(row.conclusion).toBe('证据不完整')
  })
})

// ─── K8-5 合同费用摊销 ────────────────────────────────────────────────────────
type K85Api = ReturnType<typeof useK8ContractAmortization>
function makeK85(seed?: unknown[]): HostInstance<K8AmortRow> & { api: K85Api } {
  const allResponses = ref(new Map<string, any>())
  if (seed) allResponses.value.set('K8-5-amort-rows', { item_id: 'K8-5-amort-rows', remark: JSON.stringify(seed) })
  let saves = 0
  const api = useK8ContractAmortization({
    allResponses, projectId: ref('proj-1'), wpId: ref('wp-1'), year: ref(2025), isReadonly: ref(false),
    onSave: (itemId, value) => {
      if (itemId === 'K8-5-amort-rows') saves += 1
      allResponses.value.set(itemId, { item_id: itemId, remark: typeof value === 'string' ? value : JSON.stringify(value) })
    },
  })
  return {
    api: api as unknown as HostInstance<K8AmortRow>['api'] & K85Api,
    rows: () => api.rows.value,
    stored: () => JSON.parse(String(allResponses.value.get('K8-5-amort-rows')?.remark ?? '[]')),
    rowSaves: () => saves,
  }
}

describe('K8-5 合同费用摊销：一笔样本一个合同行', () => {
  voucherFillHostCases<K8AmortRow>({
    make: makeK85,
    idKey: 'rowKey',
    noOf: r => r.voucherIndex.split(' / ')[0].replace('凭证 ', ''),
    view: r => [r.voucherIndex, r.projectName],
    expected: [['凭证 0012 / 2025-03-04', '抽凭样本'], ['凭证 0014 / 2025-03-04', '抽凭样本']],
    edit: (inst, id, value) => (inst.api as unknown as K85Api).updateCell(id, 'conclusion', value),
    editKey: 'conclusion',
    manualRow: { rowKey: 'm1', projectName: '律师费', voucherIndex: '凭证 手-1' },
    oldRow: { projectName: '旧合同', voucherIndex: '凭证 0012', conclusion: '' },
    oldRowKept: { projectName: '旧合同' },
    // 原实现只写项目名，旧行认不出是哪张凭证
    noLegacy: true,
  })
})

// ─── K10-6 其他收益检查 ────────────────────────────────────────────────────────
type K10Api = ReturnType<typeof useK10Checks>
function makeK10(seed?: unknown[]): HostInstance<K10IncomeCheckRow> & { api: K10Api } {
  const allResponses = ref(new Map<string, any>())
  if (seed) allResponses.value.set('K10-6-check-rows', { item_id: 'K10-6-check-rows', remark: JSON.stringify(seed) })
  let saves = 0
  const api = useK10Checks({
    allResponses, projectId: ref('proj-1'), wpId: ref('wp-1'), sheetKey: 'K10-6', isReadonly: ref(false),
    onSave: (itemId, value) => {
      if (itemId === 'K10-6-check-rows') saves += 1
      allResponses.value.set(itemId, { item_id: itemId, remark: typeof value === 'string' ? value : JSON.stringify(value) })
    },
  })
  return {
    api: api as unknown as HostInstance<K10IncomeCheckRow>['api'] & K10Api,
    rows: () => api.incomeCheckRows.value,
    stored: () => JSON.parse(String(allResponses.value.get('K10-6-check-rows')?.remark ?? '[]')),
    rowSaves: () => saves,
  }
}

describe('K10-6 其他收益检查：一笔样本一条检查行', () => {
  voucherFillHostCases<K10IncomeCheckRow>({
    make: makeK10,
    idKey: 'rowKey',
    noOf: r => String(r.remark).replace(/^(抽凭|挂凭)：/, ''),
    view: r => [r.remark, r.checkItem, r.checkAmount],
    expected: [['抽凭：0012', '抽凭样本', 300], ['抽凭：0014', '抽凭样本', 1000]],
    edit: (inst, id, value) => (inst.api as unknown as K10Api).updateIncomeCheckCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowKey: 'm1', checkItem: '手工项目', remark: '手-1' },
    oldRow: { checkItem: '旧检查', checkAmount: 1000, remark: '抽凭：0012', classificationCorrect: '合规' },
    oldRowKept: { classificationCorrect: '合规' },
  })
})
