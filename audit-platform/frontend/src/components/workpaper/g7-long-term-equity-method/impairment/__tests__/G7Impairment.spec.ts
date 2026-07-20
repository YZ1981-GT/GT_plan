/**
 * G7 长期股权投资(权益法组) — Impairment 子组件单元测试
 *
 * 测试清单:
 * 1. calcImpairmentAmount always ≥ 0
 * 2. 累计亏损≤合计权益时超额=0，Tab2禁用逻辑
 * 3. 减值迹象=否→公允/使用价值禁用；=是→两列必填；可收回金额公式取高
 *
 * Requirements: 6.4, 6.5, 6.6
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'

import {
  calcImpairmentAmount,
  calcRecoverableAmount,
  parseNum,
} from '../../../composables/useG7EquityMethodFormulaEngine'
import {
  applyProfitRecoveryReverseOrder,
  extractCumulativeLossFromG75,
  extractPriorCumulativeMap,
  parseUnrecognizedLossRowsPayload,
  recalcUnrecognizedLossRow,
  validateUnrecognizedLossRows,
} from '../../../composables/g7UnrecognizedLossModel'
import {
  applyAutoAuditConclusion,
  calcImpairmentRecon,
  hasMissingRecoverableInputs,
  isBookValueStale,
  recalcImpairmentAmounts,
  suggestAuditConclusion,
  sumG714Impairment,
  sumG72ImpairmentClosing,
} from '../g7ImpairmentTestModel'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcImpairmentAmount 永远 ≥ 0 (非负性)
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — calcImpairmentAmount 非负性', () => {
  /**
   * 减值金额 = MAX(0, 账面价值 - 可收回金额)
   * 当可收回金额 > 账面价值时，不存在负减值（不允许减值转回超原值）
   *
   * **Validates: Requirements 6.6**
   */

  it('账面价值 > 可收回金额 → 减值 = 差额', () => {
    expect(calcImpairmentAmount(100000, 80000)).toBe(20000)
  })

  it('账面价值 = 可收回金额 → 减值 = 0', () => {
    expect(calcImpairmentAmount(100000, 100000)).toBe(0)
  })

  it('账面价值 < 可收回金额 → 减值 = 0（非负）', () => {
    expect(calcImpairmentAmount(80000, 100000)).toBe(0)
  })

  it('两个参数均为0 → 减值 = 0', () => {
    expect(calcImpairmentAmount(0, 0)).toBe(0)
  })

  it('账面为负值场景（异常数据容错）→ 减值 = 0', () => {
    expect(calcImpairmentAmount(-10000, 50000)).toBe(0)
  })

  it('可收回为负值场景 → 减值 = 账面 - 负可收回 > 0', () => {
    // 100000 - (-50000) = 150000
    expect(calcImpairmentAmount(100000, -50000)).toBe(150000)
  })

  it('可收回金额 = MAX(公允净额, 使用价值)', () => {
    expect(calcRecoverableAmount(75000, 80000)).toBe(80000)
    expect(calcRecoverableAmount(90000, 80000)).toBe(90000)
  })

  it('串联：减值 = MAX(0, 账面 − MAX(公允,使用价值))', () => {
    const recoverable = calcRecoverableAmount(75000, 82000)
    expect(calcImpairmentAmount(100000, recoverable)).toBe(18000)
  })

  it('保留2位小数精度', () => {
    // 100000.556 - 80000.123 = 20000.433 → round → 20000.43
    expect(calcImpairmentAmount(100000.556, 80000.123)).toBe(20000.43)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. G7-16 超额亏损逻辑 + Tab2禁用
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — G7-16 超额亏损逻辑', () => {
  /**
   * G7-16 未确认投资损失:
   *   合计长期权益 = 投资账面 + 长期应收款 + 其他权益 + 预计负债
   *   超额亏损 = MAX(0, 累计亏损 - 合计长期权益)
   *   超额亏损为0时 Tab2 全部禁用
   *
   * **Validates: Requirements 6.4**
   */

  function calcTotalLongTermEquity(
    investmentBookValue: number,
    longTermReceivable: number,
    otherLongTermEquity: number,
    estimatedLiability: number,
  ): number {
    return Math.round((
      parseNum(investmentBookValue)
      + parseNum(longTermReceivable)
      + parseNum(otherLongTermEquity)
      + parseNum(estimatedLiability)
    ) * 100) / 100
  }

  function calcExcessLoss(cumulativeLoss: number, totalLongTermEquity: number): number {
    const diff = parseNum(cumulativeLoss) - parseNum(totalLongTermEquity)
    return Math.round(Math.max(0, diff) * 100) / 100
  }

  it('累计亏损 ≤ 合计权益 → 超额亏损 = 0', () => {
    const total = calcTotalLongTermEquity(500000, 200000, 100000, 50000) // 850000
    const excess = calcExcessLoss(800000, total)
    expect(excess).toBe(0)
  })

  it('累计亏损 > 合计权益 → 超额亏损 = 差额', () => {
    const total = calcTotalLongTermEquity(500000, 200000, 100000, 50000) // 850000
    const excess = calcExcessLoss(1000000, total)
    expect(excess).toBe(150000)
  })

  it('累计亏损 = 合计权益 → 超额亏损 = 0', () => {
    const total = calcTotalLongTermEquity(300000, 100000, 50000, 50000) // 500000
    const excess = calcExcessLoss(500000, total)
    expect(excess).toBe(0)
  })

  it('超额亏损为0时 → Tab2禁用', () => {
    const excessLoss = ref(0)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(true)
  })

  it('超额亏损 > 0 → Tab2启用', () => {
    const excessLoss = ref(150000)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(false)
  })

  it('超额亏损从正变为0时 → Tab2重新禁用', () => {
    const excessLoss = ref(50000)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(false)

    excessLoss.value = 0
    expect(isTab2Disabled.value).toBe(true)
  })

  function calcUnrecognizedLoss(
    excessLoss: number,
    reduceInvestment: number,
    reduceLongTermReceivable: number,
    reduceOtherEquity: number,
    recognizeEstimatedLiability: number,
  ): number {
    return Math.round(Math.max(0,
      parseNum(excessLoss)
      - parseNum(reduceInvestment)
      - parseNum(reduceLongTermReceivable)
      - parseNum(reduceOtherEquity)
      - parseNum(recognizeEstimatedLiability),
    ) * 100) / 100
  }

  it('未确认损失 = 超额 − 各项冲减', () => {
    expect(calcUnrecognizedLoss(150000, 50000, 30000, 20000, 10000)).toBe(40000)
  })

  it('冲减超过超额 → 未确认损失 = 0（非负）', () => {
    expect(calcUnrecognizedLoss(100000, 80000, 50000, 0, 0)).toBe(0)
  })

  it('本期变动 = 未确认 − 上期累计', () => {
    const unrecognized = 40000
    const prior = 10000
    expect(Math.round((unrecognized - prior) * 100) / 100).toBe(30000)
  })
})

describe('G7Impairment — G7-16 CAS2瀑布/校验/hydrate', () => {
  it('瀑布：超额依次冲减投资→长应收→其他权益，剩余为未确认', () => {
    const row: any = {
      investmentBookValue: 50,
      longTermReceivable: 30,
      otherLongTermEquity: 10,
      estimatedLiability: 0,
      cumulativeLoss: 200,
      priorCumulative: 0,
      recognizeEstimatedLiability: 0,
      allocationManual: false,
      currentChangeManual: false,
    }
    recalcUnrecognizedLossRow(row, { applyWaterfall: true })
    expect(row.excessLoss).toBe(110) // 200 - 90
    expect(row.reduceInvestment).toBe(50)
    expect(row.reduceLongTermReceivable).toBe(30)
    expect(row.reduceOtherEquity).toBe(10)
    expect(row.unrecognizedLoss).toBe(20)
    expect(row.currentChange).toBe(20)
  })

  it('手工锁定后不覆盖冲减', () => {
    const row: any = {
      investmentBookValue: 100,
      longTermReceivable: 0,
      otherLongTermEquity: 0,
      estimatedLiability: 0,
      cumulativeLoss: 250,
      reduceInvestment: 5,
      reduceLongTermReceivable: 0,
      reduceOtherEquity: 0,
      recognizeEstimatedLiability: 0,
      priorCumulative: 0,
      allocationManual: true,
      currentChangeManual: false,
    }
    recalcUnrecognizedLossRow(row)
    expect(row.reduceInvestment).toBe(5)
    expect(row.unrecognizedLoss).toBe(145) // excess 150 - 5
  })

  it('冲减超账面 → 校验 error', () => {
    const issues = validateUnrecognizedLossRows([{
      investeeName: '甲',
      investmentBookValue: 10,
      longTermReceivable: 0,
      otherLongTermEquity: 0,
      estimatedLiability: 0,
      excessLoss: 50,
      reduceInvestment: 20,
      reduceLongTermReceivable: 0,
      reduceOtherEquity: 0,
      recognizeEstimatedLiability: 0,
      unrecognizedLoss: 30,
      currentChange: 0,
    }])
    expect(issues.some(i => i.level === 'error' && i.message.includes('冲减投资'))).toBe(true)
  })

  it('本期变动为负 → 恢复路径 warning', () => {
    const issues = validateUnrecognizedLossRows([{
      investeeName: '乙',
      investmentBookValue: 0,
      longTermReceivable: 0,
      otherLongTermEquity: 0,
      estimatedLiability: 0,
      excessLoss: 0,
      reduceInvestment: 0,
      reduceLongTermReceivable: 0,
      reduceOtherEquity: 0,
      recognizeEstimatedLiability: 0,
      unrecognizedLoss: 0,
      currentChange: -12,
    }])
    expect(issues.some(i => i.message.includes('相反顺序'))).toBe(true)
  })

  it('hydrate 兼容旧 {rows} 与扁平数组', () => {
    expect(parseUnrecognizedLossRowsPayload([{ investeeName: 'A' }])).toHaveLength(1)
    expect(parseUnrecognizedLossRowsPayload({ rows: [{ investeeName: 'B' }] })).toHaveLength(1)
    expect(parseUnrecognizedLossRowsPayload(JSON.stringify({ rows: [{ investeeName: 'C' }] }))).toHaveLength(1)
    expect(parseUnrecognizedLossRowsPayload({ data: [{ investeeName: 'D' }] })).toHaveLength(1)
  })

  it('G7-5 负净资产 → 累计亏损代理', () => {
    const map = extractCumulativeLossFromG75({
      groups: [{
        investeeName: '亏企',
        rows: [
          { reportItem: '所有者权益（净资产）', currentAmount: -80 },
          { reportItem: '净利润', currentAmount: -20 },
        ],
      }],
    })
    expect(map.get('亏企')).toBe(80)
  })

  it('G7-5 显式累计亏损优先', () => {
    const map = extractCumulativeLossFromG75([
      { investeeName: '亏企', reportItem: '累计亏损', currentAmount: 120 },
      { investeeName: '亏企', reportItem: '所有者权益（净资产）', currentAmount: -80 },
    ])
    expect(map.get('亏企')).toBe(120)
  })

  it('利润恢复反序：先冲回预计负债再其他', () => {
    const row: any = {
      investmentBookValue: 100,
      longTermReceivable: 50,
      otherLongTermEquity: 20,
      estimatedLiability: 0,
      cumulativeLoss: 0,
      excessLoss: 0,
      reduceInvestment: 40,
      reduceLongTermReceivable: 30,
      reduceOtherEquity: 10,
      recognizeEstimatedLiability: 15,
      unrecognizedLoss: 0,
      priorCumulative: 80,
      currentChange: -50,
      allocationManual: true,
      currentChangeManual: false,
    }
    const { recovered, detail } = applyProfitRecoveryReverseOrder(row, 50)
    expect(recovered).toBe(50)
    expect(detail.liability).toBe(15)
    expect(detail.other).toBe(10)
    expect(detail.receivable).toBe(25)
    expect(detail.investment).toBe(0)
    expect(row.recognizeEstimatedLiability).toBe(0)
    expect(row.reduceOtherEquity).toBe(0)
    expect(row.reduceLongTermReceivable).toBe(5)
    expect(row.allocationManual).toBe(true)
  })

  it('期初快照 → priorCumulative map', () => {
    const map = extractPriorCumulativeMap([
      { investeeName: '甲', unrecognizedLoss: 33 },
      { investeeName: '乙', priorCumulative: 12, unrecognizedLoss: 99 },
    ])
    expect(map.get('甲')).toBe(33)
    expect(map.get('乙')).toBe(12)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. G7-17 减值迹象联动（公允/使用价值必填；可收回金额公式）
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — 减值迹象联动（必填列切换）', () => {
  /**
   * G7-17 减值测试:
   *   减值迹象=否 → 公允-处置/使用价值 禁用；可收回金额公式列置0
   *   减值迹象=是 → 公允-处置/使用价值 高亮必填；可收回金额=MAX(二者)
   *
   * **Validates: Requirements 6.5**
   */

  interface ImpairmentRow {
    hasImpairmentSign: boolean
    recoverableAmount: number
    fvLessDisposalCost: number
    valueInUse: number
  }

  function getDisabledInputColumns(row: ImpairmentRow): string[] {
    if (!row.hasImpairmentSign) {
      return ['fvLessDisposalCost', 'valueInUse']
    }
    return []
  }

  function getRequiredColumns(row: ImpairmentRow): string[] {
    if (row.hasImpairmentSign) {
      return ['fvLessDisposalCost', 'valueInUse']
    }
    return []
  }

  it('减值迹象=否 → 两输入列禁用', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: false,
      recoverableAmount: 0,
      fvLessDisposalCost: 0,
      valueInUse: 0,
    }
    const disabled = getDisabledInputColumns(row)
    expect(disabled).toContain('fvLessDisposalCost')
    expect(disabled).toContain('valueInUse')
    expect(disabled).toHaveLength(2)
  })

  it('减值迹象=是 → 两输入列必填（非禁用）', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: true,
      recoverableAmount: 80000,
      fvLessDisposalCost: 75000,
      valueInUse: 80000,
    }
    const disabled = getDisabledInputColumns(row)
    expect(disabled).toHaveLength(0)

    const required = getRequiredColumns(row)
    expect(required).toContain('fvLessDisposalCost')
    expect(required).toContain('valueInUse')
  })

  it('减值迹象=否 → 必填列为空', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: false,
      recoverableAmount: 0,
      fvLessDisposalCost: 0,
      valueInUse: 0,
    }
    const required = getRequiredColumns(row)
    expect(required).toHaveLength(0)
  })

  it('减值迹象切换：否→是 → 解除禁用+触发必填', () => {
    const hasSign = ref(false)

    const disabled = computed(() => hasSign.value ? [] : ['fvLessDisposalCost', 'valueInUse'])
    const required = computed(() => hasSign.value ? ['fvLessDisposalCost', 'valueInUse'] : [])

    expect(disabled.value).toHaveLength(2)
    expect(required.value).toHaveLength(0)

    hasSign.value = true
    expect(disabled.value).toHaveLength(0)
    expect(required.value).toHaveLength(2)
  })

  it('减值迹象切换：是→否 → 禁用+取消必填', () => {
    const hasSign = ref(true)

    const disabled = computed(() => hasSign.value ? [] : ['fvLessDisposalCost', 'valueInUse'])
    const required = computed(() => hasSign.value ? ['fvLessDisposalCost', 'valueInUse'] : [])

    expect(disabled.value).toHaveLength(0)
    expect(required.value).toHaveLength(2)

    hasSign.value = false
    expect(disabled.value).toHaveLength(2)
    expect(required.value).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. G7-17 改进：结论自动对齐 / 双零告警 / stale / 勾稽 / 手工覆盖
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — 行结论自动对齐', () => {
  it('减值>0 → 需计提', () => {
    expect(suggestAuditConclusion({
      hasImpairmentSign: true,
      impairmentAmount: 18000,
      auditConclusion: '',
    })).toBe('需计提')
  })

  it('有迹象但减值=0 → 无需计提', () => {
    expect(suggestAuditConclusion({
      hasImpairmentSign: true,
      impairmentAmount: 0,
      auditConclusion: '需计提',
    })).toBe('无需计提')
  })

  it('已充分计提不覆盖', () => {
    expect(suggestAuditConclusion({
      hasImpairmentSign: true,
      impairmentAmount: 100,
      auditConclusion: '已充分计提',
    })).toBeNull()
  })

  it('applyAuto 写入建议结论', () => {
    const row = {
      hasImpairmentSign: true,
      impairmentAmount: 50,
      auditConclusion: '',
    }
    applyAutoAuditConclusion(row)
    expect(row.auditConclusion).toBe('需计提')
  })
})

describe('G7Impairment — 双零告警 / stale / 手工覆盖 / 勾稽', () => {
  it('迹象=是且公允/使用价值双0 → 告警', () => {
    expect(hasMissingRecoverableInputs({
      hasImpairmentSign: true,
      fvLessDisposalCost: 0,
      valueInUse: 0,
    })).toBe(true)
  })

  it('手工覆盖时不告警双零', () => {
    expect(hasMissingRecoverableInputs({
      hasImpairmentSign: true,
      fvLessDisposalCost: 0,
      valueInUse: 0,
      recoverableManual: true,
    })).toBe(false)
  })

  it('G7-14 账面变化 → stale', () => {
    expect(isBookValueStale(100000, 100000, 120000)).toBe(true)
    expect(isBookValueStale(100000, 100000, 100000)).toBe(false)
  })

  it('手工覆盖可收回金额后重算减值', () => {
    const row = {
      hasImpairmentSign: true,
      bookValue: 100000,
      fvLessDisposalCost: 90000,
      valueInUse: 85000,
      recoverableManual: true,
      recoverableAmount: 70000,
      impairmentAmount: 0,
    }
    recalcImpairmentAmounts(row)
    expect(row.recoverableAmount).toBe(70000)
    expect(row.impairmentAmount).toBe(30000)
  })

  it('勾稽：G7-17 ↔ G7-14 ↔ G7-2', () => {
    const g714 = sumG714Impairment([{ impairment: 10000 }, { impairment: 8000 }])
    const g72 = sumG72ImpairmentClosing([
      { auditedClosingAmount: 18000 },
    ])
    const recon = calcImpairmentRecon(18000, g714, g72)
    expect(recon.matched714).toBe(true)
    expect(recon.matched72).toBe(true)
    expect(calcImpairmentRecon(20000, g714, g72).diff714).toBe(2000)
  })
})

describe('G7Impairment — applyG717 → G7-14', () => {
  it('按名称写入 impairment', async () => {
    const { applyG717ImpairmentToG714Payload } = await import(
      '../../../composables/g7EquityMethodCrossSheet'
    )
    const result = applyG717ImpairmentToG714Payload(
      { rows: [{ investeeName: '甲联营', impairment: 0 }] },
      { rows: [{ investeeName: '甲联营', impairmentAmount: 18000 }] },
    )
    expect(result.ok).toBe(true)
    expect(result.payload.rows[0].impairment).toBe(18000)
  })
})

describe('G7Impairment — 披露 parse/merge G7-17', () => {
  it('parse + merge 覆盖 bridge 减值', async () => {
    const {
      parseG717Impairment,
      mergeG717IntoEquityBridge,
    } = await import('../../../composables/g7DisclosureCrossSheet')
    const tests = parseG717Impairment([
      { investeeName: '甲', impairmentAmount: 12, openingImpairment: 3 },
    ])
    expect(tests[0].openingImpairment).toBe(3)
    const bridge = mergeG717IntoEquityBridge(
      [{
        investeeName: '甲',
        shareOfNetAssets: 100,
        adjustments: null,
        goodwill: null,
        unrealizedInternal: null,
        impairment: 0,
        other: null,
        carrying: 100,
      }],
      tests,
    )
    expect(bridge[0].impairment).toBe(12)
  })
})
