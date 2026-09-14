/**
 * 单元测试 — M10 其他权益工具公式引擎 useM10FormulaEngine + useM10ClassificationEngine
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 7.1
 * Requirements: P1-P6
 *
 * 覆盖：
 * - calcAuditedAmount: 审定数=未审+AJE+RJE，正/负/零/NaN
 * - calcEquityEndBalance: 权益类贷方方向(begin+credit-debit)，永续债发行/优先股赎回/混合
 * - calcSubtotal: 空/单/多/负/NaN/非数组
 * - calcVariance / calcVarianceRate: 变动额/率，零处理
 * - calcNetIssuance: 净发行额=发行总额-费用
 * - calcDetailEndBalance: 明细期末=期初+发行-赎回
 * - classifyInstrument: CAS37判定（永续债/优先股/可转债）
 * - splitAmount: 复合工具金额拆分
 * - calcClassificationConsistency: 金额守恒校验+浮点容差
 *
 * 科目：4003 其他权益工具（贷方/权益类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
  calcNetIssuance,
  calcDetailEndBalance,
} from '../composables/useM10FormulaEngine'
import {
  classifyInstrument,
  splitAmount,
  calcClassificationConsistency,
} from '../composables/useM10ClassificationEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcAuditedAmount — 审定数公式链 (P1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM10FormulaEngine', () => {
  describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
    it('永续债审定: 未审1亿 + AJE调增500万 + RJE 200万 = 1.07亿', () => {
      expect(calcAuditedAmount(100_000_000, 5_000_000, 2_000_000)).toBe(107_000_000)
    })

    it('negative AJE: 优先股估值调减', () => {
      expect(calcAuditedAmount(50_000_000, -3_000_000, 0)).toBe(47_000_000)
    })

    it('negative RJE: 重分类调出至负债', () => {
      expect(calcAuditedAmount(80_000_000, 0, -20_000_000)).toBe(60_000_000)
    })

    it('all zeros → 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('NaN treated as 0 via safe()', () => {
      expect(calcAuditedAmount(NaN, 1_000_000, 500_000)).toBe(1_500_000)
    })

    it('undefined/null treated as 0', () => {
      expect(calcAuditedAmount(undefined as any, 200_000, null as any)).toBe(200_000)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 2. calcEquityEndBalance — 权益类贷方方向 (P2)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcEquityEndBalance (P2: 权益类期末=期初+贷方-借方)', () => {
    it('永续债发行: begin=100M, credit=50M(发行), debit=0 → end=150M', () => {
      expect(calcEquityEndBalance(100_000_000, 50_000_000, 0)).toBe(150_000_000)
    })

    it('优先股赎回: begin=200M, credit=0, debit=80M(赎回) → end=120M', () => {
      expect(calcEquityEndBalance(200_000_000, 0, 80_000_000)).toBe(120_000_000)
    })

    it('混合: begin=300M, credit=100M, debit=50M → end=350M', () => {
      expect(calcEquityEndBalance(300_000_000, 100_000_000, 50_000_000)).toBe(350_000_000)
    })

    it('no movement: credit=0, debit=0 → 期末=期初', () => {
      expect(calcEquityEndBalance(200_000_000, 0, 0)).toBe(200_000_000)
    })

    it('全额赎回: debit=begin → 期末=0', () => {
      expect(calcEquityEndBalance(100_000_000, 0, 100_000_000)).toBe(0)
    })

    it('VERIFY: 权益类方向 NOT asset (begin+cr-dr ≠ begin+dr-cr)', () => {
      const b = 200_000_000
      const cr = 50_000_000
      const dr = 20_000_000
      const equityEnd = calcEquityEndBalance(b, cr, dr) // 200M+50M-20M=230M
      const assetEndWouldBe = b + dr - cr // 200M+20M-50M=170M
      expect(equityEnd).toBe(230_000_000)
      expect(equityEnd).not.toBe(assetEndWouldBe)
    })

    it('all zeros → 0', () => {
      expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
    })

    it('NaN/undefined/null handling', () => {
      expect(calcEquityEndBalance(NaN, 50_000_000, 20_000_000)).toBe(30_000_000)
      expect(calcEquityEndBalance(100_000_000, undefined as any, null as any)).toBe(100_000_000)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 3. calcSubtotal — 分类小计 (P6)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcSubtotal (P6: 按工具类型分类汇总)', () => {
    it('empty array → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('single element: 仅永续债', () => {
      expect(calcSubtotal([100_000_000])).toBe(100_000_000)
    })

    it('multiple: 永续债1亿 + 优先股5000万 + 可转债权益2000万', () => {
      expect(calcSubtotal([100_000_000, 50_000_000, 20_000_000])).toBe(170_000_000)
    })

    it('negative values: 赎回汇总', () => {
      expect(calcSubtotal([-30_000_000, -20_000_000])).toBe(-50_000_000)
    })

    it('mixed positive/negative', () => {
      expect(calcSubtotal([100_000_000, -30_000_000, 50_000_000])).toBe(120_000_000)
    })

    it('NaN in array treated as 0', () => {
      expect(calcSubtotal([100_000_000, NaN, 50_000_000])).toBe(150_000_000)
    })

    it('non-array input → 0 (defensive)', () => {
      expect(calcSubtotal(null as any)).toBe(0)
      expect(calcSubtotal(undefined as any)).toBe(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 4. calcVariance / calcVarianceRate — 变动额/率
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcVariance (变动额=期末审定-期初审定)', () => {
    it('增加: 期末1.5亿 - 期初1亿 = 变动+5000万', () => {
      expect(calcVariance(150_000_000, 100_000_000)).toBe(50_000_000)
    })

    it('减少: 期末8000万 - 期初1亿 = 变动-2000万', () => {
      expect(calcVariance(80_000_000, 100_000_000)).toBe(-20_000_000)
    })

    it('无变动: 相等 → 0', () => {
      expect(calcVariance(100_000_000, 100_000_000)).toBe(0)
    })

    it('both zero → 0', () => {
      expect(calcVariance(0, 0)).toBe(0)
    })
  })

  describe('calcVarianceRate (变动率: 零处理特殊)', () => {
    it('期初=0 且 期末=0 → null(不显示)', () => {
      expect(calcVarianceRate(0, 0)).toBeNull()
    })

    it('期初=0 且 期末>0 → 1(100%)', () => {
      expect(calcVarianceRate(0, 50_000_000)).toBe(1)
    })

    it('正常变动率: 期初1亿, 期末1.5亿 → 50%', () => {
      expect(calcVarianceRate(100_000_000, 150_000_000)).toBeCloseTo(0.5, 10)
    })

    it('减少: 期初1亿, 期末8000万 → -20%', () => {
      expect(calcVarianceRate(100_000_000, 80_000_000)).toBeCloseTo(-0.2, 10)
    })

    it('期初=0 且 期末=0 (both NaN safe)', () => {
      expect(calcVarianceRate(NaN, NaN)).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 5. calcNetIssuance — 净发行额 (发行总额-费用)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcNetIssuance (净发行额=发行总额-发行费用)', () => {
    it('永续债发行: 总额5亿 - 承销费500万 = 4.95亿', () => {
      expect(calcNetIssuance(500_000_000, 5_000_000)).toBe(495_000_000)
    })

    it('零费用: 全额计入', () => {
      expect(calcNetIssuance(100_000_000, 0)).toBe(100_000_000)
    })

    it('零发行: 仅有费用(异常但公式有效)', () => {
      expect(calcNetIssuance(0, 1_000_000)).toBe(-1_000_000)
    })

    it('both zero → 0', () => {
      expect(calcNetIssuance(0, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcNetIssuance(NaN, 1_000_000)).toBe(-1_000_000)
      expect(calcNetIssuance(100_000_000, NaN)).toBe(100_000_000)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 6. calcDetailEndBalance — 明细行期末余额
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcDetailEndBalance (明细期末=期初+本期发行-本期赎回)', () => {
    it('永续债明细: 期初2亿+本期发行1亿-赎回0 = 3亿', () => {
      expect(calcDetailEndBalance(200_000_000, 100_000_000, 0)).toBe(300_000_000)
    })

    it('优先股部分赎回: 期初1亿+发行0-赎回3000万 = 7000万', () => {
      expect(calcDetailEndBalance(100_000_000, 0, 30_000_000)).toBe(70_000_000)
    })

    it('新发行工具: 期初0+发行5亿-赎回0 = 5亿', () => {
      expect(calcDetailEndBalance(0, 500_000_000, 0)).toBe(500_000_000)
    })

    it('全额赎回: 期初1亿+发行0-赎回1亿 = 0', () => {
      expect(calcDetailEndBalance(100_000_000, 0, 100_000_000)).toBe(0)
    })

    it('与calcEquityEndBalance逻辑一致（语义不同但公式相同）', () => {
      const begin = 200_000_000
      const issuance = 80_000_000
      const reduction = 30_000_000
      expect(calcDetailEndBalance(begin, issuance, reduction))
        .toBe(calcEquityEndBalance(begin, issuance, reduction))
    })

    it('NaN handling', () => {
      expect(calcDetailEndBalance(NaN, 100_000_000, 50_000_000)).toBe(50_000_000)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useM10ClassificationEngine — CAS37 负债权益区分引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM10ClassificationEngine', () => {
  // ═══════════════════════════════════════════════════════════════════════════════
  // 1. classifyInstrument — CAS37分类判定 (P3)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('classifyInstrument (P3: CAS37负债权益判定)', () => {
    it('永续债无固定期限且可递延利息 → 无合同义务 → equity', () => {
      // 永续债：无到期赎回义务、利息可无条件递延 → 不存在交付现金的合同义务
      expect(classifyInstrument(false)).toBe('equity')
    })

    it('优先股有强制赎回条款 → 有合同义务 → liability', () => {
      // 优先股：有强制赎回日期 → 存在交付现金的合同义务
      expect(classifyInstrument(true)).toBe('liability')
    })

    it('可转债权益成分 → 无合同义务 → equity', () => {
      // 可转债拆分后的权益成分（转股权）→ 不含交付义务
      expect(classifyInstrument(false)).toBe('equity')
    })

    it('可转债负债成分 → 有合同义务 → liability', () => {
      // 可转债拆分后的负债成分（利息+到期本金）→ 含交付义务
      expect(classifyInstrument(true)).toBe('liability')
    })

    it('有强制付息义务 → liability', () => {
      expect(classifyInstrument(true)).toBe('liability')
    })

    it('可递延且无赎回 → equity', () => {
      expect(classifyInstrument(false)).toBe('equity')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 2. splitAmount — 复合工具金额拆分 (P4)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('splitAmount (P4: 负债部分=总额-权益部分)', () => {
    it('total=100M, equity=60M → liability=40M', () => {
      expect(splitAmount(100_000_000, 60_000_000)).toBe(40_000_000)
    })

    it('全部为权益: total=50M, equity=50M → liability=0', () => {
      expect(splitAmount(50_000_000, 50_000_000)).toBe(0)
    })

    it('全部为负债: total=80M, equity=0 → liability=80M', () => {
      expect(splitAmount(80_000_000, 0)).toBe(80_000_000)
    })

    it('equity > total (异常但公式有效): → negative', () => {
      expect(splitAmount(100_000_000, 120_000_000)).toBe(-20_000_000)
    })

    it('both zero → 0', () => {
      expect(splitAmount(0, 0)).toBe(0)
    })

    it('NaN handling: NaN total → 0 - eq', () => {
      expect(splitAmount(NaN, 60_000_000)).toBe(-60_000_000)
      expect(splitAmount(100_000_000, NaN)).toBe(100_000_000)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // 3. calcClassificationConsistency — 金额守恒校验 (P5)
  // ═══════════════════════════════════════════════════════════════════════════════

  describe('calcClassificationConsistency (P5: 权益+负债===总额)', () => {
    it('60M + 40M === 100M → true', () => {
      expect(calcClassificationConsistency(60_000_000, 40_000_000, 100_000_000)).toBe(true)
    })

    it('60M + 30M !== 100M → false', () => {
      expect(calcClassificationConsistency(60_000_000, 30_000_000, 100_000_000)).toBe(false)
    })

    it('浮点容差: 33.33 + 66.67 === 100 → true (within 1e-10)', () => {
      expect(calcClassificationConsistency(33.33, 66.67, 100)).toBe(true)
    })

    it('浮点精度边界: 0.1 + 0.2 ≈ 0.3 → true (within tolerance)', () => {
      expect(calcClassificationConsistency(0.1, 0.2, 0.3)).toBe(true)
    })

    it('all zero → true (0+0===0)', () => {
      expect(calcClassificationConsistency(0, 0, 0)).toBe(true)
    })

    it('显著偏差: equity=50M, liability=30M, total=100M → false (差额20M)', () => {
      expect(calcClassificationConsistency(50_000_000, 30_000_000, 100_000_000)).toBe(false)
    })

    it('单侧全额: equity=0, liability=100M, total=100M → true', () => {
      expect(calcClassificationConsistency(0, 100_000_000, 100_000_000)).toBe(true)
    })

    it('单侧全额: equity=100M, liability=0, total=100M → true', () => {
      expect(calcClassificationConsistency(100_000_000, 0, 100_000_000)).toBe(true)
    })

    it('NaN handling: NaN→0, 检查守恒', () => {
      // safe(NaN)=0, 所以 0+40M vs 100M → false
      expect(calcClassificationConsistency(NaN as any, 40_000_000, 100_000_000)).toBe(false)
    })
  })
})
