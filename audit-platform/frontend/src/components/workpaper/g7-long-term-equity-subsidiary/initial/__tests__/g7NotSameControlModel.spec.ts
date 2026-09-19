/**

 * g7NotSameControlModel 单元测试

 *

 * 覆盖：一次购买商誉（源底稿编号）、分步逐笔④⑤、旧数据迁移、校验、G7-7 同步

 */

import { describe, it, expect } from 'vitest'

import {

  createNotSameControlMergerRow,

  createNotSameControlStepRow,

  createNotSameControlReverseRow,

  collectNotSameControlPersistBlockers,

  describeGoodwill,

  extractG79CarryToSubsequent,

  extractNotSameControlInvesteesFromG7Judgment,

  normalizeNotSameControlRows,

  recalcNotSameControlMergerRow,

  recalcNotSameControlStepRow,

  summarizeNotSameControlSteps,

  syncMergerRowsFromNotSameControlNames,

  validateNotSameControlRows,

} from '../g7NotSameControlModel'



describe('G7-9 一次购买：对齐源底稿 ③⑥⑦⑧', () => {

  it('③合计；⑥=③+④；⑦=③−⑤；⑧=⑥−①×②；费用不入成本', () => {

    const row = createNotSameControlMergerRow(1, '目标A')

    row.cashConsideration = 100

    row.nonCashAssetFV = 20

    row.debtFV = 10

    row.equitySecuritiesFV = 5

    row.contingentConsiderationFV = 5

    row.priorHoldingFV = 40

    row.considerationBookValue = 120

    row.acquireeIdentifiableNetAssetsFV = 200

    row.ownershipRatio = 0.8

    row.acquisitionCostsExpensed = 15

    recalcNotSameControlMergerRow(row)



    expect(row.totalConsiderationFV).toBe(140) // ③

    expect(row.initialInvestmentCost).toBe(180) // ⑥=③+④

    expect(row.considerationGainLoss).toBe(20) // ⑦=③−⑤

    expect(row.shareOfFV).toBe(160) // ①×②

    expect(row.nonControllingInterestShare).toBe(40)

    expect(row.goodwill).toBe(20) // ⑧=⑥−①×②

    expect(describeGoodwill(row.goodwill)).toContain('商誉')

  })



  it('廉价购买利得：⑧<0 须复核；无原持股时⑥=③', () => {

    const row = createNotSameControlMergerRow(1, '目标B')

    row.cashConsideration = 100

    row.acquireeIdentifiableNetAssetsFV = 200

    row.ownershipRatio = 0.8

    recalcNotSameControlMergerRow(row)

    expect(row.initialInvestmentCost).toBe(100)

    expect(row.goodwill).toBe(-60)

    expect(describeGoodwill(row.goodwill)).toContain('廉价购买利得')



    const issues = validateNotSameControlRows([row])

    expect(issues.some(i => i.severity === 'error' && i.message.includes('复核'))).toBe(true)



    row.bargainPurchaseReviewed = '是'

    row.bargainPurchaseReviewNote = '已复核评估与对价'

    const ok = validateNotSameControlRows([row])

    expect(ok.some(i => i.message.includes('复核'))).toBe(false)

  })

})



describe('G7-9 分步合并：逐笔④=①×③、⑤=②−④；⑦=累计②+⑥', () => {

  it('逐笔重算与公司级汇总', () => {

    const companyId = 'c1'

    const r1 = createNotSameControlStepRow(companyId, 'P公司', 1)

    r1.purchaseRatio = 0.3

    r1.considerationFV = 30

    r1.netAssetsFVAtTxn = 100

    r1.priorHoldingBookValue = 25

    r1.priorHoldingFV = 40

    r1.priorEquityMethodAdjustments = 2

    r1.isPackageDeal = '否'

    r1.notPackageBasis = '独立定价'

    recalcNotSameControlStepRow(r1)



    expect(r1.shareOfFVAtTxn).toBe(30) // ④

    expect(r1.goodwillAtTxn).toBe(0) // ⑤



    const r2 = createNotSameControlStepRow(companyId, 'P公司', 2)

    r2.purchaseRatio = 0.4

    r2.considerationFV = 50

    r2.netAssetsFVAtTxn = 100

    r2.priorEquityMethodAdjustments = 3

    r2.isPackageDeal = '否'

    recalcNotSameControlStepRow(r2)



    expect(r2.shareOfFVAtTxn).toBe(40)

    expect(r2.goodwillAtTxn).toBe(10)



    const [summary] = summarizeNotSameControlSteps([r1, r2])

    expect(summary.cumulativeRatio).toBeCloseTo(0.7, 6)

    expect(summary.cumulativeConsiderationFV).toBe(80)

    expect(summary.cumulativeShareOfFV).toBe(70)

    expect(summary.cumulativeTxnGoodwill).toBe(10)

    expect(summary.remeasurementGain).toBe(15) // 40-25

    expect(summary.priorEquityMethodAdjustments).toBe(5)

    expect(summary.parentInitialCost).toBe(85) // ⑦=累计②+累计⑥ = 80+2+3

  })

  it('空 companyId 按公司名生成同一分组，导入后交易行不会丢失', () => {
    const rows = normalizeNotSameControlRows([
      {
        section: 'step',
        companyId: '',
        companyName: '导入公司',
        transactionNo: 1,
        purchaseRatio: 0.2,
        adjustmentScope: 'transaction',
      },
      {
        section: 'step',
        companyId: '',
        companyName: '导入公司',
        transactionNo: 2,
        purchaseRatio: 0.4,
        adjustmentScope: 'transaction',
      },
    ])
    const stepRows = rows.filter(row => row.section === 'step')
    expect(stepRows).toHaveLength(2)
    expect(stepRows[0].companyId).toBeTruthy()
    expect(stepRows[1].companyId).toBe(stepRows[0].companyId)
    expect(summarizeNotSameControlSteps(stepRows)).toHaveLength(1)
  })

  it('旧版重复的公司级⑥只迁移一次', () => {
    const rows = normalizeNotSameControlRows([
      {
        id: 'legacy-1',
        section: 'step',
        companyId: 'legacy',
        companyName: '旧分步公司',
        transactionNo: 1,
        purchaseRatio: 0.2,
        considerationFV: 20,
        priorEquityMethodAdjustments: 4,
      },
      {
        id: 'legacy-2',
        section: 'step',
        companyId: 'legacy',
        companyName: '旧分步公司',
        transactionNo: 2,
        purchaseRatio: 0.4,
        considerationFV: 40,
        priorEquityMethodAdjustments: 4,
      },
    ]).filter(row => row.section === 'step')
    const [summary] = summarizeNotSameControlSteps(rows)
    expect(summary.priorEquityMethodAdjustments).toBe(4)
    expect(summary.parentInitialCost).toBe(64)
  })



  it('旧字段 netAssetsBookValueAtTxn / priorOCIReclassify 可迁移', () => {

    const rows = normalizeNotSameControlRows([

      {

        section: 'step',

        companyId: 'c2',

        companyName: 'Q公司',

        purchaseRatio: 0.5,

        considerationFV: 60,

        netAssetsBookValueAtTxn: 100,

        priorOCIReclassify: 3,

        isPackageDeal: '否',

        notPackageBasis: '分次谈判',

      },

    ])

    expect(rows).toHaveLength(1)

    const row = rows[0]

    expect(row.section).toBe('step')

    if (row.section === 'step') {

      expect(row.netAssetsFVAtTxn).toBe(100)

      expect(row.priorEquityMethodAdjustments).toBe(3)

      expect(row.shareOfFVAtTxn).toBe(50)

      expect(row.goodwillAtTxn).toBe(10)

    }

  })

})



describe('G7-9 反向购买：构成业务硬校验', () => {

  it('未判断或判定不构成业务时不得确认商誉口径', () => {

    const row = createNotSameControlReverseRow(1)

    row.transactionContent = '借壳'

    row.accountingAcquirer = 'A'

    row.accountingAcquiree = 'B'

    let issues = validateNotSameControlRows([row])

    expect(issues.some(i => i.message.includes('构成业务'))).toBe(true)



    row.constitutesBusiness = '否'

    row.businessDeterminationBasis = '仅持有金融资产'

    issues = validateNotSameControlRows([row])

    expect(issues.some(i => i.severity === 'error' && i.message.includes('不得确认商誉'))).toBe(true)



    row.constitutesBusiness = '是'

    issues = validateNotSameControlRows([row])

    expect(issues.some(i => i.message.includes('不得确认商誉'))).toBe(false)

  })

})



describe('G7-9 旧扁平数据迁移', () => {

  it('无 section 的旧行映射为 merger，directFees→费用化，consideration→现金', () => {

    const rows = normalizeNotSameControlRows([

      {

        investeeName: '旧公司',

        consideration: 100,

        directFees: 8,

        acquireeNetAssetsFV: 200,

        shareholdingRatio: 0.6,

        acquisitionDate: '2024-06-30',

      },

    ])

    expect(rows).toHaveLength(1)

    const row = rows[0]

    expect(row.section).toBe('merger')

    if (row.section === 'merger') {

      expect(row.cashConsideration).toBe(100)

      expect(row.acquisitionCostsExpensed).toBe(8)

      expect(row.initialInvestmentCost).toBe(100)

      expect(row.shareOfFV).toBe(120)

      expect(row.goodwill).toBe(-20)

    }

  })

})



describe('G7-9 校验与同步', () => {

  it('一揽子交易不得出现在分步区', () => {

    const row = createNotSameControlStepRow('c1', 'Q公司', 1)

    row.purchaseRatio = 0.6

    row.considerationFV = 60

    row.isPackageDeal = '是'

    const issues = validateNotSameControlRows([row])

    expect(issues.some(i => i.severity === 'error' && i.message.includes('一揽子'))).toBe(true)

  })



  it('从 G7-7 提取非同控单位并同步', () => {

    const names = extractNotSameControlInvesteesFromG7Judgment({

      decision: {

        investeeName: '目标C',

        relationshipType: '控制',

        combinationType: '非同一控制下企业合并',

      },

    })

    expect(names).toEqual(['目标C'])

    const { rows, added } = syncMergerRowsFromNotSameControlNames([], names)

    expect(added).toBe(1)

    expect(rows[0].investeeName).toBe('目标C')

  })



  it('同控判定不进入非同控名单', () => {

    const names = extractNotSameControlInvesteesFromG7Judgment({

      decision: {

        investeeName: '目标D',

        relationshipType: '控制',

        combinationType: '同一控制下企业合并',

      },

    })

    expect(names).toEqual([])

  })

})

describe('G7-9 持久化硬拦与带入', () => {
  it('廉价购买未复核时 collectNotSameControlPersistBlockers 拦截', () => {
    const row = createNotSameControlMergerRow(1, '目标B')
    row.cashConsideration = 100
    row.acquireeIdentifiableNetAssetsFV = 200
    row.ownershipRatio = 0.8
    recalcNotSameControlMergerRow(row)
    const blockers = collectNotSameControlPersistBlockers([row])
    expect(blockers.some(m => m.includes('廉价购买'))).toBe(true)

    row.bargainPurchaseReviewed = '是'
    row.bargainPurchaseReviewNote = '已复核'
    expect(collectNotSameControlPersistBlockers([row])).toEqual([])
  })

  it('反向购买不构成业务硬拦；空草稿不拦', () => {
    const empty = createNotSameControlReverseRow(1)
    expect(collectNotSameControlPersistBlockers([empty])).toEqual([])
    empty.constitutesBusiness = '否'
    expect(collectNotSameControlPersistBlockers([empty]).some(m => m.includes('资产购置'))).toBe(true)
  })

  it('extractG79CarryToSubsequent 输出一次购买与分步汇总', () => {
    const merger = createNotSameControlMergerRow(1, '甲')
    merger.ownershipRatio = 0.8
    merger.cashConsideration = 100
    recalcNotSameControlMergerRow(merger)
    const step = createNotSameControlStepRow('c1', '乙', 1)
    step.purchaseRatio = 0.6
    step.considerationFV = 60
    step.netAssetsFVAtTxn = 100
    recalcNotSameControlStepRow(step)
    const carry = extractG79CarryToSubsequent([merger, step])
    expect(carry).toHaveLength(2)
    expect(carry[0]).toMatchObject({ companyName: '甲', shareholdingRatio: 0.8, source: 'merger' })
    expect(carry[1]).toMatchObject({ companyName: '乙', shareholdingRatio: 0.6, source: 'step' })
  })
})


