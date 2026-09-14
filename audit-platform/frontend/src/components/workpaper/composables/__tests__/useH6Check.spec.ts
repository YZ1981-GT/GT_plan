/**
 * useH6Check 单测 — 公式重算 / 检查比例 / H6-2 同步 / 旧版迁移
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useH6Check,
  recalcH6CheckRow,
  isTransferMismatch,
  draftH6AuditNote,
  mapOcrToH6CheckFields,
  type H6CheckRow,
} from '../useH6Check'

function makeMap(entries: Record<string, string>) {
  const m = ref(new Map<string, any>())
  for (const [k, v] of Object.entries(entries)) {
    m.value.set(k, { item_id: k, remark: v, conclusion: null })
  }
  return m
}

describe('recalcH6CheckRow', () => {
  it('净值含减值；净损益=收入−费用−净值', () => {
    const row = {
      originalCost: 1000,
      accumulatedDepreciation: 200,
      impairment: 50,
      clearingIncome: 800,
      clearingExpense: 30,
    } as H6CheckRow
    recalcH6CheckRow(row)
    expect(row.netValue).toBe(750)
    expect(row.clearingGainLoss).toBe(800 - 30 - 750)
  })
})

describe('isTransferMismatch', () => {
  it('已清零但结转分摊未覆盖净损益 → mismatch', () => {
    const row = {
      clearingGainLoss: 100,
      toNonOperating: 40,
      toDisposalGain: 40,
      endingBalance: 0,
    } as H6CheckRow
    expect(isTransferMismatch(row)).toBe(true)
  })

  it('分摊等于净损益且期末为0 → ok', () => {
    const row = {
      clearingGainLoss: -100,
      toNonOperating: -60,
      toDisposalGain: -40,
      endingBalance: 0,
    } as H6CheckRow
    expect(isTransferMismatch(row)).toBe(false)
  })
})

describe('useH6Check syncFromDetailRows', () => {
  it('从 H6-2 同步金额骨架并更新总体', () => {
    const saved: Record<string, any> = {}
    const allResponses = makeMap({
      'H6-2-rows': JSON.stringify([
        {
          rowId: 'd1',
          assetName: '机床',
          originalCost: 200000,
          accumulatedDepreciation: 80000,
          disposalIncome: 90000,
          disposalExpenses: 2000,
          taxAmount: 1000,
          disposalReason: '报废',
          startDate: '2025-06-01',
          status: '已结转',
          transferAccount: '6115资产处置收益',
          gainLoss: 7000,
          netBookValue: 120000,
        },
      ]),
    })

    const api = useH6Check({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses,
      onSave: (id, val) => {
        saved[id] = val
      },
    })

    const added = api.syncFromDetailRows([
      {
        rowId: 'd1',
        assetName: '机床',
        originalCost: 200000,
        accumulatedDepreciation: 80000,
        disposalIncome: 90000,
        disposalExpenses: 2000,
        taxAmount: 1000,
        disposalReason: '报废',
        startDate: '2025-06-01',
        status: '已结转',
        transferAccount: '6115资产处置收益',
        gainLoss: 7000,
        netBookValue: 120000,
      },
    ])

    expect(added).toBe(1)
    expect(api.rows.value[0].assetName).toBe('机床')
    expect(api.rows.value[0].clearingExpense).toBe(3000)
    expect(api.rows.value[0].endingBalance).toBe(0)
    expect(api.rows.value[0].toDisposalGain).toBe(api.rows.value[0].clearingGainLoss)
    expect(saved['H6-4-rows']).toHaveLength(1)
  })
})

describe('useH6Check updateCell', () => {
  it('改原值后重算净值与净损益并持久化', () => {
    const onSave = vi.fn()
    const allResponses = makeMap({
      'H6-4-rows': JSON.stringify([
        {
          rowId: 'r1',
          assetName: 'A',
          originalCost: 100,
          accumulatedDepreciation: 0,
          impairment: 0,
          clearingIncome: 50,
          clearingExpense: 0,
        },
      ]),
    })
    const api = useH6Check({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses,
      onSave,
    })
    api.updateCell('r1', 'originalCost', 200)
    expect(api.rows.value[0].netValue).toBe(200)
    expect(api.rows.value[0].clearingGainLoss).toBe(50 - 0 - 200)
    expect(onSave).toHaveBeenCalled()
  })
})

describe('draft helpers / OCR / fillFromSampledVouchers', () => {
  it('draftH6AuditNote 含检查比例与挂账提示', () => {
    const text = draftH6AuditNote({
      summary: {
        checkedCount: 2,
        originalCostTotal: 0,
        netValueTotal: 10000,
        expenseTotal: 0,
        incomeTotal: 0,
        gainLossTotal: -100,
        toNonOperatingTotal: 0,
        toDisposalGainTotal: -100,
        endingBalanceTotal: 5000,
        coverageRate: 10,
        anomalyCount: 1,
        nonZeroEndingCount: 1,
        transferMismatchCount: 0,
        overOneYearCount: 1,
        h10GainLossDiff: 50,
        hasLowCoverage: true,
        warning: '',
      },
      sampling: {
        totalPopulation: 100000,
        samplingMethod: '货币单元抽样',
        populationManual: true,
        specificSample: '大额全部测',
        samplingProcess: 'IDEA抽10笔',
      },
      testReasons: ['largeAmount', 'abnormal'],
    })
    expect(text).toContain('检查比例')
    expect(text).toContain('偏低')
    expect(text).toContain('H10')
  })

  it('mapOcrToH6CheckFields 映射合同金额与凭证号', () => {
    const patch = mapOcrToH6CheckFields({
      凭证编号: '记-12',
      合同金额: '88,000',
      固定资产名称: '挖掘机',
      批准人: '张三',
    })
    expect(patch.voucherNo).toBe('记-12')
    expect(patch.clearingIncome).toBe(88000)
    expect(patch.assetName).toBe('挖掘机')
    expect(patch.approvedBy).toBe('张三')
  })

  it('导入扁平 check1–check5 / 是 可还原为 checks[]', () => {
    const onSave = vi.fn()
    const api = useH6Check({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: makeMap({
        'H6-4-rows': JSON.stringify([{
          assetName: '车床',
          originalCost: 1000,
          accumulatedDepreciation: 200,
          impairment: 0,
          clearingIncome: 700,
          clearingExpense: 50,
          check1: '是',
          check2: true,
          check3: 1,
          check4: '否',
          check5: 'Y',
          isAbnormal: '是',
        }]),
      }),
      onSave,
    })
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0].checks).toEqual([true, true, true, false, true])
    expect(api.rows.value[0].isAbnormal).toBe(true)
    expect(api.rows.value[0].netValue).toBe(800)
  })

  it('fillFromSampledVouchers 按借贷方向填入', () => {
    const onSave = vi.fn()
    const api = useH6Check({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: makeMap({}),
      onSave,
    })
    const n = api.fillFromSampledVouchers([
      {
        voucherNo: 'V1',
        voucherDate: '2025-03-01',
        summary: '转入清理',
        debitAmount: '50000',
        creditAmount: '0',
        counterpartAccount: '1601',
      },
      {
        voucherNo: 'V2',
        voucherDate: '2025-04-01',
        summary: '结转处置收益',
        debitAmount: '0',
        creditAmount: '12000',
        counterpartAccount: '6115',
      },
    ])
    expect(n).toBe(2)
    expect(api.rows.value[0].originalCost).toBe(50000)
    expect(api.rows.value[0].counterpartAccount).toBe('1601')
    expect(api.rows.value[1].toDisposalGain).toBe(12000)
    expect(api.rows.value[1].endingBalance).toBe(0)
  })
})
