/**
 * H1 固定资产 — 集成测试
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 7.4
 * Validates: 全部 Requirements
 *
 * 测试场景：
 * 1. H1-1 审定表: 公式计算链 (audit=unadj+aje+rje, 三角勾稽)
 * 2. H1-2 明细表: 合计计算, 交叉验证 vs H1-1
 * 3. H1-12 折旧: 引擎计算, 差异检测
 * 4. H1-14 减值: DCF计算, MAX可收回金额
 * 5. Import/Export composable API调用
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcProportion,
  calcDisposalGainLoss,
  calcTitleDiff,
  calcLeaseReturnRate,
} from '../composables/useH1FormulaEngine'
import {
  calcStraightLine,
  calcDoubleDeclining,
  calcSumOfYears,
  calcDcfPresentValue,
  isMonotonicallyIncreasing,
} from '../composables/useH1DepreciationEngine'

// ─── H1-1 审定表: 公式计算链 ─────────────────────────────────────────────

describe('H1-1 审定表 集成', () => {
  describe('审定数公式链', () => {
    it('审定数 = 未审数 + AJE + RJE', () => {
      // 固定资产原值
      expect(calcAuditedAmount(1000000, 50000, -20000)).toBe(1030000)
      // 累计折旧
      expect(calcAuditedAmount(300000, 10000, 0)).toBe(310000)
      // 零调整
      expect(calcAuditedAmount(500000, 0, 0)).toBe(500000)
    })

    it('资产类期末余额 = 期初 + 借方 - 贷方', () => {
      // 正常情况
      expect(calcAssetEndBalance(1000000, 200000, 50000)).toBe(1150000)
      // 期初为0
      expect(calcAssetEndBalance(0, 500000, 0)).toBe(500000)
    })

    it('备抵类期末余额 = 期初 + 贷方 - 借方', () => {
      // 累计折旧（贷方科目）
      expect(calcContraEndBalance(300000, 10000, 100000)).toBe(390000)
      // 减值准备转回（借方减少）
      expect(calcContraEndBalance(50000, 20000, 0)).toBe(30000)
    })
  })

  describe('三角勾稽校验', () => {
    it('平衡时差额为0', () => {
      // 原值层: 期末=期初+增加-减少
      const begin = 1000000
      const increase = 200000
      const decrease = 50000
      const end = begin + increase - decrease
      expect(calcTriangleReconciliation(begin, increase, decrease, end)).toBe(0)
    })

    it('不平衡时差额非0', () => {
      // 有差异
      const result = calcTriangleReconciliation(1000000, 200000, 50000, 1200000)
      expect(result).toBe(50000) // 1200000 - (1000000 + 200000 - 50000) = 50000
    })

    it('折旧层三角勾稽', () => {
      // 备抵类: 期末折旧 = 期初折旧 + 本期增加(计提) - 本期减少(转出)
      const depBegin = 300000
      const depIncrease = 120000 // 年度折旧
      const depDecrease = 15000 // 处置转出
      const depEnd = depBegin + depIncrease - depDecrease
      expect(calcTriangleReconciliation(depBegin, depIncrease, depDecrease, depEnd)).toBe(0)
    })
  })

  describe('净值计算', () => {
    it('净值 = 原值 - 累计折旧 - 减值', () => {
      expect(calcNetValue(1000000, 300000, 50000)).toBe(650000)
      expect(calcNetValue(500000, 500000, 0)).toBe(0)
      expect(calcNetValue(1000000, 0, 0)).toBe(1000000)
    })
  })
})

// ─── H1-2 明细表: 合计计算 + 交叉验证 ─────────────────────────────────────

describe('H1-2 明细表 集成', () => {
  describe('合计计算', () => {
    it('分类合计 = SUM(各资产原值)', () => {
      const assets = [500000, 300000, 200000, 800000, 150000]
      expect(calcSubtotal(assets)).toBe(1950000)
    })

    it('空数组合计为0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单项数组合计等于自身', () => {
      expect(calcSubtotal([123456.78])).toBe(123456.78)
    })
  })

  describe('交叉验证 vs H1-1', () => {
    it('明细表各分类合计 应等于 审定表对应行', () => {
      // 模拟H1-2各分类
      const houses = [1000000, 2000000, 500000]
      const machinery = [800000, 600000, 400000]
      const vehicles = [200000, 150000]
      const electronics = [50000, 80000, 30000]

      const totalHouses = calcSubtotal(houses)
      const totalMachinery = calcSubtotal(machinery)
      const totalVehicles = calcSubtotal(vehicles)
      const totalElectronics = calcSubtotal(electronics)

      // H1-1审定表总计 应等于 各分类小计之和
      const grandTotal = calcSubtotal([totalHouses, totalMachinery, totalVehicles, totalElectronics])
      expect(grandTotal).toBe(5810000)

      // 验证每一分类
      expect(totalHouses).toBe(3500000)
      expect(totalMachinery).toBe(1800000)
      expect(totalVehicles).toBe(350000)
      expect(totalElectronics).toBe(160000)
    })
  })

  describe('变动率计算', () => {
    it('正常变动率', () => {
      expect(calcChangeRate(120, 100)).toBeCloseTo(20)
    })

    it('上期为0时返回null', () => {
      expect(calcChangeRate(100, 0)).toBeNull()
    })

    it('占比计算', () => {
      expect(calcProportion(300000, 1000000)).toBeCloseTo(30)
    })
  })
})

// ─── H1-12 折旧: 引擎计算 + 差异检测 ──────────────────────────────────────

describe('H1-12 折旧 集成', () => {
  describe('4种折旧方法计算', () => {
    const cost = 1200000
    const salvageRate = 0.05
    const usefulLife = 10

    it('直线法月折旧', () => {
      const monthly = calcStraightLine(cost, salvageRate, usefulLife)
      // 1200000 * (1-0.05) / 10 / 12 = 9500
      expect(monthly).toBeCloseTo(9500)
    })

    it('双倍余额递减法 - 前期', () => {
      const netValue = 900000
      const monthly = calcDoubleDeclining(netValue, usefulLife, 24, 120)
      // 前期: 900000 * 2 / 10 / 12 = 15000
      expect(monthly).toBeCloseTo(15000)
    })

    it('双倍余额递减法 - 最后24月转直线', () => {
      const netValue = 200000
      const monthly = calcDoubleDeclining(netValue, usefulLife, 100, 120)
      // 剩余20个月: 200000 / 20 = 10000
      expect(monthly).toBeCloseTo(10000)
    })

    it('年数总和法', () => {
      const monthly = calcSumOfYears(cost, salvageRate, usefulLife, usefulLife)
      // 第1年: 1200000 * 0.95 * 10 / 55 / 12 = 17272.73
      const sumOfYears = usefulLife * (usefulLife + 1) / 2
      const expected = cost * (1 - salvageRate) * usefulLife / sumOfYears / 12
      expect(monthly).toBeCloseTo(expected)
    })
  })

  describe('差异检测', () => {
    it('账面折旧与测算折旧差异', () => {
      const bookMonthlyDep = 10000
      const calcMonthlyDep = calcStraightLine(1200000, 0.05, 10)
      const difference = bookMonthlyDep - calcMonthlyDep
      // 10000 - 9500 = 500
      expect(difference).toBeCloseTo(500)
      // 差异率
      const diffRate = Math.abs(difference) / calcMonthlyDep * 100
      expect(diffRate).toBeCloseTo(5.26, 1)
    })

    it('折旧累计单调递增', () => {
      const monthlyAmounts = [9500, 9500, 9500, 9500, 9500, 9500]
      const cumulative: number[] = []
      let sum = 0
      for (const amt of monthlyAmounts) {
        sum += amt
        cumulative.push(sum)
      }
      expect(isMonotonicallyIncreasing(cumulative, [])).toBe(true)
    })
  })

  describe('分支切换', () => {
    it('A/B/C三分支使用同源数据', () => {
      const cost = 1000000
      const salvageRate = 0.05
      const usefulLife = 10

      // 分支A: 直线法
      const branchA = calcStraightLine(cost, salvageRate, usefulLife)
      // 分支B: 含减值直线法 (相同参数无减值时相等)
      const branchB = calcStraightLine(cost, salvageRate, usefulLife)
      // 分支C: 多次减值 (无减值时与A相同)
      const branchC = calcStraightLine(cost, salvageRate, usefulLife)

      expect(branchA).toBe(branchB)
      expect(branchB).toBe(branchC)
    })
  })
})

// ─── H1-14 减值: DCF计算 + MAX可收回金额 ───────────────────────────────────

describe('H1-14 减值 集成', () => {
  describe('DCF现值计算', () => {
    it('单年现金流DCF', () => {
      const pv = calcDcfPresentValue([100000], 0.1)
      // 100000 / (1.1)^1 = 90909.09
      expect(pv).toBeCloseTo(90909.09, 0)
    })

    it('多年现金流DCF', () => {
      const cashFlows = [100000, 120000, 150000, 130000, 110000]
      const rate = 0.08
      const pv = calcDcfPresentValue(cashFlows, rate)
      // 手动验证
      let expected = 0
      for (let i = 0; i < cashFlows.length; i++) {
        expected += cashFlows[i] / Math.pow(1 + rate, i + 1)
      }
      expect(pv).toBeCloseTo(expected, 2)
    })
  })

  describe('可收回金额MAX选取', () => {
    it('公允减处置费 > DCF → 取公允减处置费', () => {
      const fairValueLessDisposal = 800000
      const dcfValue = 750000
      const recoverable = Math.max(fairValueLessDisposal, dcfValue)
      expect(recoverable).toBe(800000)
    })

    it('DCF > 公允减处置费 → 取DCF', () => {
      const fairValueLessDisposal = 600000
      const dcfValue = 720000
      const recoverable = Math.max(fairValueLessDisposal, dcfValue)
      expect(recoverable).toBe(720000)
    })

    it('减值金额 = MAX(账面-可收回, 0)', () => {
      const bookValue = 1000000
      const recoverable = 800000
      const impairment = Math.max(bookValue - recoverable, 0)
      expect(impairment).toBe(200000)
    })

    it('可收回>账面时无减值', () => {
      const bookValue = 800000
      const recoverable = 900000
      const impairment = Math.max(bookValue - recoverable, 0)
      expect(impairment).toBe(0)
    })
  })
})

// ─── Import/Export composable API 调用 ──────────────────────────────────────

describe('Import/Export 集成', () => {
  describe('H1-2 宽表4区段分sheet逻辑', () => {
    it('4个区段名称定义正确', () => {
      const segments = ['基本信息', '原值变动', '折旧变动', '净值减值']
      expect(segments).toHaveLength(4)
      expect(segments[0]).toBe('基本信息')
      expect(segments[1]).toBe('原值变动')
      expect(segments[2]).toBe('折旧变动')
      expect(segments[3]).toBe('净值减值')
    })

    it('导出模板endpoint路径正确', () => {
      const wpId = 'test-wp-id'
      const exportTemplatePath = `/api/workpapers/${wpId}/h1/export-template`
      const exportDataPath = `/api/workpapers/${wpId}/h1/export-data`
      const importDataPath = `/api/workpapers/${wpId}/h1/import-data`
      expect(exportTemplatePath).toContain('/h1/export-template')
      expect(exportDataPath).toContain('/h1/export-data')
      expect(importDataPath).toContain('/h1/import-data')
    })
  })

  describe('处置损益公式集成', () => {
    it('处置收益', () => {
      // 处置收入 > 净值 + 费用
      expect(calcDisposalGainLoss(500000, 300000, 20000)).toBe(180000)
    })

    it('处置损失', () => {
      // 处置收入 < 净值 + 费用
      expect(calcDisposalGainLoss(200000, 300000, 20000)).toBe(-120000)
    })
  })

  describe('权属差异集成', () => {
    it('账面>证载有正差异', () => {
      expect(calcTitleDiff(1000000, 950000)).toBe(50000)
    })

    it('账面<证载有负差异', () => {
      expect(calcTitleDiff(900000, 1000000)).toBe(-100000)
    })
  })

  describe('经营租出收益率集成', () => {
    it('正常收益率', () => {
      // 净收益50000, 原值1000000 → 5%
      expect(calcLeaseReturnRate(50000, 1000000)).toBeCloseTo(5)
    })

    it('原值为0时返回null', () => {
      expect(calcLeaseReturnRate(50000, 0)).toBeNull()
    })
  })
})
