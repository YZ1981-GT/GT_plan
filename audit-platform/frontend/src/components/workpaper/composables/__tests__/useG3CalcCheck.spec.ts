/**
 * useG3CalcCheck 单元测试 — G3-4 三区段测算及检查
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  enrichCalcRow,
  enrichSubsequent,
  isVarianceExceeding,
  isDecreaseDiffExceeding,
  needsVarianceReason,
  isCrossCheckMismatch,
  isNotSubsequentDate,
  subsequentSamplingYear,
  defaultCutoffFromAuditYear,
  buildAdjustmentDraftFromCalcRow,
  DATA_KEY,
  SUBSEQUENT_KEY,
  useG3CalcCheck,
  type CalcCheckRow,
} from '../useG3CalcCheck'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

function baseRow(patch: Partial<CalcCheckRow> = {}): CalcCheckRow {
  return enrichCalcRow({
    id: 'r1',
    seq: 1,
    detailRowId: '',
    investeeName: 'A公司',
    shareholdingRatio: 10,
    sharesHeld: 100_000,
    dps: 0.8,
    investeeTotalDividend: 0,
    dividendPolicy: '',
    declarationDate: '',
    recordDate: '',
    dividendDocNo: '',
    calculatedDividend: 0,
    calcByRatio: 0,
    crossCheckDiff: 0,
    bookedAmount: 80_000,
    calcVariance: 0,
    varianceReason: '',
    indexNo: '',
    skipDuplicate: '',
    periodDecrease: 50_000,
    cashReceived: 50_000,
    otherDecreaseAccount: '',
    otherDecreaseAmount: 0,
    otherDecreaseReason: '',
    decreaseDiff: 0,
    decreaseIndexNo: '',
    decreaseRemark: '',
    ...patch,
  })
}

describe('enrichCalcRow', () => {
  it('测算 = 持股 × DPS；差异 = 账面 − 测算', () => {
    const row = baseRow({ sharesHeld: 100_000, dps: 0.8, bookedAmount: 79_800 })
    expect(row.calculatedDividend).toBe(80_000)
    expect(row.calcVariance).toBe(-200) // 79800 - 80000
    expect(isVarianceExceeding(row)).toBe(true)
  })

  it('减少差异 = 本期减少 − 收现 − 其他减少', () => {
    const row = baseRow({
      periodDecrease: 100_000,
      cashReceived: 60_000,
      otherDecreaseAmount: 30_000,
    })
    expect(row.decreaseDiff).toBe(10_000)
    expect(isDecreaseDiffExceeding(row)).toBe(true)
  })

  it('有分红总额时做比例交叉验算', () => {
    const row = baseRow({
      shareholdingRatio: 10,
      sharesHeld: 100_000,
      dps: 0.8,
      investeeTotalDividend: 800_000,
    })
    expect(row.calcByRatio).toBe(80_000)
    expect(row.crossCheckDiff).toBe(0)
    expect(isCrossCheckMismatch(row)).toBe(false)
  })

  it('|差异|>100 且无原因/索引 → needsVarianceReason', () => {
    const row = baseRow({ bookedAmount: 79_800, varianceReason: '', indexNo: '' })
    expect(needsVarianceReason(row)).toBe(true)
    expect(needsVarianceReason(baseRow({ bookedAmount: 79_800, varianceReason: '四舍五入' }))).toBe(false)
  })
})

describe('enrichSubsequent', () => {
  it('金额优先借方，否则贷方', () => {
    expect(enrichSubsequent({
      id: 's1', seq: 1, investeeName: '', voucherDate: '', voucherNo: '', summary: '',
      counterAccount: '', counterDetailAccount: '', debitAmount: 100, creditAmount: 0,
      amount: 0, supportingDocs: '', check1: '', check2: '', check3: '', check4: '', check5: '',
      indexNo: '', isAbnormal: '', abnormalNote: '',
    }).amount).toBe(100)

    expect(enrichSubsequent({
      id: 's2', seq: 1, investeeName: '', voucherDate: '', voucherNo: '', summary: '',
      counterAccount: '', counterDetailAccount: '', debitAmount: 0, creditAmount: 50,
      amount: 0, supportingDocs: '', check1: '', check2: '', check3: '', check4: '', check5: '',
      indexNo: '', isAbnormal: '', abnormalNote: '',
    }).amount).toBe(50)
  })
})

describe('useG3CalcCheck migration + sync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('旧扁平凭证字段迁移到期后区段', () => {
    const legacy = [{
      id: 'old1',
      seq: 1,
      investeeName: 'A公司',
      sharesHeld: 10000,
      dps: 1,
      bookedAmount: 10000,
      voucherDate: '2024-01-15',
      voucherNo: 'V-001',
      summary: '收到股利',
      amount: 10000,
      samplingSource: '抽凭引擎',
    }]
    const map = new Map<string, ChecklistResponse>([
      [DATA_KEY, { conclusion: JSON.stringify(legacy) } as ChecklistResponse],
    ])
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const { rows, subsequentRows } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: (id, data) => saves.push({ id, data }),
      isReadonly: ref(false),
    })

    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].calculatedDividend).toBe(10000)
    expect(rows.value[0].calcVariance).toBe(0)
    expect(subsequentRows.value.some((r) => r.voucherNo === 'V-001')).toBe(true)
    expect(saves.some((s) => s.id === SUBSEQUENT_KEY)).toBe(true)
  })

  it('syncFromDetail 保留已填账面已计与差异原因', () => {
    const detail = [{
      id: 'd1',
      investeeName: 'A公司',
      shareholdingRatio: 20,
      sharesHeld: 200_000,
      dps: 0.5,
      totalDividend: 100_000,
      dividendPlan: '现金分红',
      declarationDate: '2023-03-01',
      recordDate: '2023-03-10',
      receivedAmount: 40_000,
    }]
    const existing = [baseRow({
      detailRowId: 'd1',
      investeeName: 'A公司',
      bookedAmount: 99_000,
      varianceReason: '已沟通差异',
      sharesHeld: 1,
      dps: 1,
      periodDecrease: 10,
      cashReceived: 10,
    })]
    const map = new Map<string, ChecklistResponse>([
      [DATA_KEY, { conclusion: JSON.stringify(existing) } as ChecklistResponse],
      ['G3-2-detail-rows', { conclusion: JSON.stringify(detail) } as ChecklistResponse],
    ])
    const { rows, syncFromDetail } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    const result = syncFromDetail()
    expect(result.updated).toBe(1)
    expect(rows.value[0].sharesHeld).toBe(200_000)
    expect(rows.value[0].dps).toBe(0.5)
    expect(rows.value[0].bookedAmount).toBe(99_000)
    expect(rows.value[0].varianceReason).toBe('已沟通差异')
    expect(rows.value[0].periodDecrease).toBe(10) // 已填不覆盖
  })

  it('fillFromSamples 写入期后区段', () => {
    const map = new Map<string, ChecklistResponse>()
    const { subsequentRows, fillFromSamples, segment } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    fillFromSamples([{
      investeeName: 'B公司',
      voucherDate: '2024-02-01',
      voucherNo: 'V-9',
      summary: '期后收股利',
      debitAmount: 0,
      creditAmount: 0,
      amount: 12345,
    }])
    expect(segment.value).toBe('subsequent')
    expect(subsequentRows.value.some((r) => r.voucherNo === 'V-9' && r.samplingSource === '抽凭引擎')).toBe(true)
  })

  it('fillFromSamples 剔除截止日及以前凭证', () => {
    const map = new Map<string, ChecklistResponse>()
    const { subsequentRows, fillFromSamples } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: () => {},
      isReadonly: ref(false),
      cutoffDate: ref('2023-12-31'),
    })
    const result = fillFromSamples([
      { voucherDate: '2023-12-31', voucherNo: 'OLD', amount: 1 },
      { voucherDate: '2024-01-05', voucherNo: 'NEW', amount: 2 },
    ])
    expect(result.skippedCutoff).toBe(1)
    expect(result.filled).toBe(1)
    expect(subsequentRows.value.some((r) => r.voucherNo === 'NEW')).toBe(true)
    expect(subsequentRows.value.some((r) => r.voucherNo === 'OLD')).toBe(false)
  })

  it('pushVariancesToAdjustment 写入 G3-3 草稿', () => {
    const existing = [baseRow({
      investeeName: 'A公司',
      sharesHeld: 100_000,
      dps: 0.8,
      bookedAmount: 79_800, // variance -200
    })]
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const map = new Map<string, ChecklistResponse>([
      [DATA_KEY, { conclusion: JSON.stringify(existing) } as ChecklistResponse],
    ])
    const { pushVariancesToAdjustment } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: (id, data) => saves.push({ id, data }),
      isReadonly: ref(false),
    })
    const n = pushVariancesToAdjustment()
    expect(n).toBeGreaterThanOrEqual(1)
    expect(saves.some((s) => s.id === 'G3-3-rows')).toBe(true)
    const saved = saves.find((s) => s.id === 'G3-3-rows')
    const rows = JSON.parse(String(saved?.data.remark ?? '[]'))
    expect(rows[0].accountCode).toBe('1131')
    expect(rows[0].debitAmount).toBe(200) // 少计 → 借
  })

  it('pushVariancesToAdjustment 不重复推送同一来源行', () => {
    const row = baseRow({
      id: 'r-dup',
      investeeName: 'A公司',
      sharesHeld: 100_000,
      dps: 0.8,
      bookedAmount: 79_800,
    })
    const draft = buildAdjustmentDraftFromCalcRow(row)!
    const map = new Map<string, ChecklistResponse>([
      [DATA_KEY, { conclusion: JSON.stringify([row]) } as ChecklistResponse],
      ['G3-3-rows', { remark: JSON.stringify([draft]), conclusion: JSON.stringify([draft]) } as ChecklistResponse],
    ])
    const { pushVariancesToAdjustment } = useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(pushVariancesToAdjustment()).toBe(0)
  })

  it('迁移后剥离主表旧凭证字段并回写', () => {
    const legacy = [{
      id: 'old1',
      seq: 1,
      investeeName: 'A公司',
      sharesHeld: 10000,
      dps: 1,
      bookedAmount: 10000,
      voucherDate: '2024-01-15',
      voucherNo: 'V-001',
      amount: 10000,
    }]
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const map = new Map<string, ChecklistResponse>([
      [DATA_KEY, { conclusion: JSON.stringify(legacy) } as ChecklistResponse],
    ])
    useG3CalcCheck({
      allResponses: ref(map),
      debouncedSave: (id, data) => saves.push({ id, data }),
      isReadonly: ref(false),
    })
    const mainSave = saves.find((s) => s.id === DATA_KEY)
    expect(mainSave).toBeTruthy()
    const persisted = JSON.parse(String(mainSave?.data.conclusion ?? '[]'))
    expect(persisted[0].voucherNo).toBeUndefined()
    expect(persisted[0].voucherDate).toBeUndefined()
    expect(persisted[0].investeeName).toBe('A公司')
  })
})

describe('cutoff helpers', () => {
  it('defaultCutoffFromAuditYear / subsequentSamplingYear', () => {
    expect(defaultCutoffFromAuditYear(2023)).toBe('2023-12-31')
    expect(subsequentSamplingYear(2023)).toBe(2024)
    expect(isNotSubsequentDate('2023-12-31', '2023-12-31')).toBe(true)
    expect(isNotSubsequentDate('2024-01-01', '2023-12-31')).toBe(false)
  })

  it('buildAdjustmentDraftFromCalcRow 方向正确', () => {
    const over = buildAdjustmentDraftFromCalcRow(baseRow({ bookedAmount: 90_000, sharesHeld: 100_000, dps: 0.8 }))
    // booked 90000 - calc 80000 = +10000 → 多计 → 贷
    expect(over?.creditAmount).toBe(10000)
    expect(over?.debitAmount).toBe(0)

    const under = buildAdjustmentDraftFromCalcRow(baseRow({ bookedAmount: 70_000, sharesHeld: 100_000, dps: 0.8 }))
    expect(under?.debitAmount).toBe(10000)
    expect(under?.creditAmount).toBe(0)
  })
})
