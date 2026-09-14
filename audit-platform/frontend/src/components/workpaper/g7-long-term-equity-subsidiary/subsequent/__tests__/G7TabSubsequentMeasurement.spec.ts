import { describe, it, expect } from 'vitest'
import {
  calcCostMethodIncome,
  calcConsiderationTotal,
  calcDividendVariance,
  calcNciEquityAdjustment,
  calcNciPurchaseShare,
  calcPartialDisposalConsolAdjustment,
  calcPartialDisposalConsolShare,
  calcPartialDisposalIndividualGain,
  calcSubsequentBalance,
  parseNum,
} from '../../../composables/useG7SubFormulaEngine'
import {
  createDividendRow,
  createNciPurchaseRow,
  createPartialDisposalRow,
  fillNciEquitySplitToCapitalReserve,
  fillPartialDisposalEquitySplitToCapitalReserve,
  migrateLegacyCostMethodRow,
  normalizeSubsequentRows,
  parseSubsequentPayload,
  recalcDividendRow,
  recalcNciPurchaseRow,
  recalcPartialDisposalRow,
  syncDividendRowsFromG79Carry,
  validateSubsequentRows,
} from '../g7SubsequentModel'
import { loadSubsidiaryInvestees } from '../../../composables/g7EquityMethodCrossSheet'

/**
 * G7-10 子公司后续计量测试表 单元测试
 *
 * 对齐源模板三区段：股利测算 / 购买少数股权 / 不丧失控制权处置
 */

describe('G7TabSubsequentMeasurement — 公式验证', () => {
  describe('calcCostMethodIncome / calcDividendVariance', () => {
    it('应享股利 = 宣告 × 持股比例', () => {
      expect(calcCostMethodIncome(10_000_000, 0.6)).toBe(6_000_000)
    })

    it('差异 = 应享 − 入账', () => {
      expect(calcDividendVariance(600_000, 580_000)).toBe(20_000)
      expect(calcDividendVariance(600_000, 600_000)).toBe(0)
    })
  })

  describe('购买少数股权：④=③×①；⑤=②−④', () => {
    it('购买成本合计', () => {
      expect(calcConsiderationTotal(1_000_000, 200_000, 50_000, 0, 0)).toBe(1_250_000)
    })

    it('按新增比例享有份额④', () => {
      expect(calcNciPurchaseShare(10_000_000, 0.1)).toBe(1_000_000)
    })

    it('权益调整⑤ = 成本 − 份额', () => {
      expect(calcNciEquityAdjustment(1_250_000, 1_000_000)).toBe(250_000)
    })

    it('recalcNciPurchaseRow 串联正确', () => {
      const row = recalcNciPurchaseRow({
        ...createNciPurchaseRow(1, '甲公司'),
        priorCarryingAmount: 5_000_000,
        addedRatio: 0.1,
        costCash: 1_200_000,
        netAssetsFV: 10_000_000,
      })
      expect(row.purchaseCost).toBe(1_200_000)
      expect(row.shareOfNetAssets).toBe(1_000_000)
      expect(row.equityAdjustment).toBe(200_000)
      expect(row.carryingAfterPurchase).toBe(6_200_000)
    })
  })

  describe('不丧失控制权处置：⑤=④−①×③/②；⑧=④−⑦', () => {
    it('个别投资收益', () => {
      // 账面1000万、原持股80%、处置20%、对价300万 → ⑤=300−1000×0.2/0.8=50万
      expect(calcPartialDisposalIndividualGain(3_000_000, 10_000_000, 0.2, 0.8)).toBe(500_000)
    })

    it('原持股为0时个别损益为0', () => {
      expect(calcPartialDisposalIndividualGain(100, 1000, 0.1, 0)).toBe(0)
    })

    it('合并份额⑦与权益调整⑧', () => {
      expect(calcPartialDisposalConsolShare(20_000_000, 0.2)).toBe(4_000_000)
      expect(calcPartialDisposalConsolAdjustment(3_000_000, 4_000_000)).toBe(-1_000_000)
    })

    it('recalcPartialDisposalRow 串联正确', () => {
      const row = recalcPartialDisposalRow({
        ...createPartialDisposalRow(1, '乙公司'),
        bookValueAtDisposal: 10_000_000,
        originalRatio: 0.8,
        reducedRatio: 0.2,
        considerationCash: 3_000_000,
        netAssetsFV: 20_000_000,
      })
      expect(row.consideration).toBe(3_000_000)
      expect(row.individualGain).toBe(500_000)
      expect(row.consolShare).toBe(4_000_000)
      expect(row.consolEquityAdj).toBe(-1_000_000)
    })
  })

  describe('兼容旧版成本法滚存', () => {
    it('calcSubsequentBalance 仍可用', () => {
      expect(calcSubsequentBalance(1_000, 200, 50)).toBe(1_150)
    })

    it('migrateLegacyCostMethodRow 迁入股利区', () => {
      const row = migrateLegacyCostMethodRow({
        investeeName: '丙公司',
        declaredDividend: 1_000_000,
        shareholdingRatio: 0.6,
        investmentIncome: 600_000,
      }, 1)
      expect(row.section).toBe('dividend')
      expect(row.companyName).toBe('丙公司')
      expect(row.entitledDividend).toBe(600_000)
      expect(row.variance).toBe(0)
    })

    it('normalizeSubsequentRows 识别三区段', () => {
      const rows = normalizeSubsequentRows([
        { section: 'dividend', companyName: 'A', declaredAmount: 100, shareholdingRatio: 0.5, recordedDividend: 50 },
        { section: 'nci', companyName: 'B', addedRatio: 0.1, costCash: 100, netAssetsFV: 1000 },
        { section: 'partialDisposal', companyName: 'C', reducedRatio: 0.1, originalRatio: 0.8, bookValueAtDisposal: 800, considerationCash: 120, netAssetsFV: 1000 },
      ])
      expect(rows.map(r => r.section)).toEqual(['dividend', 'nci', 'partialDisposal'])
    })
  })

  describe('校验', () => {
    it('减少比例大于原比例报错', () => {
      const row = recalcPartialDisposalRow({
        ...createPartialDisposalRow(1, '丁'),
        originalRatio: 0.5,
        reducedRatio: 0.6,
      })
      const issues = validateSubsequentRows([row])
      expect(issues.some(i => i.severity === 'error')).toBe(true)
    })

    it('剩余持股≤50%给出控制权警告', () => {
      const row = recalcPartialDisposalRow({
        ...createPartialDisposalRow(1, '丁2'),
        originalRatio: 0.7,
        reducedRatio: 0.3,
        considerationCash: 100,
        netAssetsFV: 1000,
      })
      const issues = validateSubsequentRows([row])
      expect(issues.some(i => i.message.includes('≤ 50%'))).toBe(true)
    })

    it('股利差异超过重要性水平升为 error', () => {
      const row = recalcDividendRow({
        ...createDividendRow(1, '戊'),
        declaredAmount: 1_000_000,
        shareholdingRatio: 0.5,
        recordedDividend: 400_000,
      })
      const issues = validateSubsequentRows([row], { materialityLevel: 50_000 })
      expect(issues.some(i => i.severity === 'error' && i.message.includes('重要性'))).toBe(true)
    })

    it('股利差异产生 warning', () => {
      const row = recalcDividendRow({
        ...createDividendRow(1, '戊'),
        declaredAmount: 1000,
        shareholdingRatio: 0.5,
        recordedDividend: 400,
      })
      const issues = validateSubsequentRows([row])
      expect(issues.some(i => i.message.includes('差异'))).toBe(true)
    })
  })

  describe('一键填资本公积', () => {
    it('NCI 权益调整全额进资本公积', () => {
      const row = fillNciEquitySplitToCapitalReserve(
        recalcNciPurchaseRow({
          ...createNciPurchaseRow(1, '己'),
          addedRatio: 0.1,
          costCash: 1_200_000,
          netAssetsFV: 10_000_000,
        }),
      )
      expect(row.equityAdjustment).toBe(200_000)
      expect(row.adjCapitalReserve).toBe(200_000)
      expect(row.adjSurplusReserve).toBe(0)
      expect(row.adjRetainedEarnings).toBe(0)
    })

    it('不丧失控制权处置合并调整全额进资本公积', () => {
      const row = fillPartialDisposalEquitySplitToCapitalReserve(
        recalcPartialDisposalRow({
          ...createPartialDisposalRow(1, '庚'),
          bookValueAtDisposal: 10_000_000,
          originalRatio: 0.8,
          reducedRatio: 0.2,
          considerationCash: 3_000_000,
          netAssetsFV: 20_000_000,
        }),
      )
      expect(row.consolEquityAdj).toBe(-1_000_000)
      expect(row.adjCapitalReserve).toBe(-1_000_000)
    })
  })

  describe('G7-4 名册解析 / 载荷兼容', () => {
    it('loadSubsidiaryInvestees 提取子公司并转换百分数为小数', () => {
      const opts = loadSubsidiaryInvestees([
        {
          investeeName: '子A',
          groupType: 'subsidiary',
          directHoldingRatio: 80,
          indirectHoldingRatio: 0,
          investmentAmount: 5_000_000,
          ratioScale: 'percent',
        },
        {
          investeeName: '联营B',
          groupType: 'associate',
          directHoldingRatio: 30,
          investmentAmount: 1_000_000,
        },
      ])
      expect(opts).toHaveLength(1)
      expect(opts[0].name).toBe('子A')
      expect(opts[0].shareholdingRatio).toBe(0.8)
      expect(opts[0].carryingAmount).toBe(5_000_000)
    })

    it('parseSubsequentPayload 兼容旧数组与新对象', () => {
      const a = parseSubsequentPayload([{ section: 'dividend', companyName: 'A', declaredAmount: 100, shareholdingRatio: 0.5 }])
      expect(a.rows).toHaveLength(1)
      expect(a.materialityLevel).toBe(0)

      const b = parseSubsequentPayload({
        materialityLevel: 10000,
        rows: [{ section: 'nci', companyName: 'B', addedRatio: 0.1, costCash: 100, netAssetsFV: 1000 }],
      })
      expect(b.materialityLevel).toBe(10000)
      expect(b.rows[0].section).toBe('nci')
    })
  })

  describe('边界', () => {
    it('parseNum 边界', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum('')).toBe(0)
      expect(parseNum('abc')).toBe(0)
    })
  })

  describe('从 G7-9 带入股利名单', () => {
    it('syncDividendRowsFromG79Carry 仅补缺不覆盖', () => {
      const existing = [createDividendRow(1, '甲')]
      existing[0].shareholdingRatio = 0.5
      const { rows, added } = syncDividendRowsFromG79Carry(existing, [
        { companyName: '甲', shareholdingRatio: 0.9 },
        { companyName: '乙', shareholdingRatio: 0.8 },
      ])
      expect(added).toBe(1)
      expect(rows).toHaveLength(2)
      expect(rows[0].shareholdingRatio).toBe(0.5)
      expect(rows[1].companyName).toBe('乙')
      expect(rows[1].shareholdingRatio).toBe(0.8)
    })
  })
})
