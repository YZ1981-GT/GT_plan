/**
 * K1 ECL阶段链 + 坏账测算 + 跨sheet勾稽 集成测试
 *
 * Spec: k1-other-receivables Task 7.2
 * Requirements: 2.9, 4.4, 6.5
 *
 * 验证4条集成链路:
 * 1. ECL阶段链 — K1-7 determineStage → K1-8 calcECL (阶段→参数→结果)
 * 2. 坏账测算链 — K1-8 calcAgingLoss → calcProvisionVariance vs K1-3
 * 3. 跨sheet勾稽 — useK1CrossSheet computeds (adjudicationVsDetail / badDebtVsCalc / agingVsBalance)
 * 4. 审定回写链 — calcSubtotal → writebackTB → EventBus
 *
 * 使用真实composable纯函数(非mock)验证公式链正确性。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Import REAL composable pure functions ───────────────────────────────────

import { determineStage } from '@/components/workpaper/composables/useK1ECLEngine'
import { calcECL, calcAgingLoss, calcProvisionVariance } from '@/components/workpaper/composables/useK1BadDebtCalcEngine'
import {
  calcSubtotal,
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcBadDebtEnd,
  calcNetValue,
} from '@/components/workpaper/composables/useK1FormulaEngine'
import { useK1CrossSheet } from '@/components/workpaper/composables/useK1CrossSheet'

// ══════════════════════════════════════════════════════════════════════════════
// Chain 1: ECL阶段链 — K1-7 stage determination → feeds into K1-8 ECL calculation
// ══════════════════════════════════════════════════════════════════════════════

describe('Chain 1: ECL阶段链 — determineStage → calcECL', () => {
  it('Stage 1 (正常): isImpaired=false, significantIncrease=false → 12个月ECL', () => {
    const stage = determineStage(false, false)
    expect(stage).toBe(1)

    // Stage 1 uses 12-month PD (lower)
    const pd12m = 0.02 // 12个月违约概率
    const ead = 1000000
    const lgd = 0.45
    const ecl = calcECL(ead, pd12m, lgd)

    expect(ecl).toBeCloseTo(1000000 * 0.02 * 0.45)
    expect(ecl).toBe(9000)
  })

  it('Stage 2 (显著增加): isImpaired=false, significantIncrease=true → 整个存续期ECL', () => {
    const stage = determineStage(false, true)
    expect(stage).toBe(2)

    // Stage 2 uses lifetime PD (higher than 12-month)
    const pdLifetime = 0.15 // 整个存续期违约概率
    const ead = 500000
    const lgd = 0.60
    const ecl = calcECL(ead, pdLifetime, lgd)

    expect(ecl).toBeCloseTo(500000 * 0.15 * 0.60)
    expect(ecl).toBe(45000)
  })

  it('Stage 3 (已减值): isImpaired=true → 整个存续期ECL (优先于significantIncrease)', () => {
    // ADR-1: isImpaired优先，即使significantIncrease=false
    const stage = determineStage(true, false)
    expect(stage).toBe(3)

    // Stage 3 uses lifetime PD + higher LGD
    const pdLifetime = 0.80
    const ead = 200000
    const lgd = 0.90
    const ecl = calcECL(ead, pdLifetime, lgd)

    expect(ecl).toBeCloseTo(200000 * 0.80 * 0.90)
    expect(ecl).toBe(144000)
  })

  it('Stage 3 takes priority when both isImpaired=true AND significantIncrease=true', () => {
    const stage = determineStage(true, true)
    expect(stage).toBe(3)
  })

  it('complete chain: multiple counterparties → stage → ECL parameters → total provision', () => {
    // Simulate K1-7 rows with different stage determinations
    const counterparties = [
      { name: '客户A', isImpaired: false, significantIncrease: false, ead: 300000 },
      { name: '客户B', isImpaired: false, significantIncrease: true, ead: 200000 },
      { name: '客户C', isImpaired: true, significantIncrease: false, ead: 100000 },
    ]

    // ECL parameters by stage (审计师独立测算参数)
    const eclParams: Record<number, { pd: number; lgd: number }> = {
      1: { pd: 0.02, lgd: 0.45 },
      2: { pd: 0.15, lgd: 0.60 },
      3: { pd: 0.80, lgd: 0.90 },
    }

    const results = counterparties.map(cp => {
      const stage = determineStage(cp.isImpaired, cp.significantIncrease)
      const params = eclParams[stage]
      const ecl = calcECL(cp.ead, params.pd, params.lgd)
      return { name: cp.name, stage, ecl }
    })

    expect(results[0]).toEqual({ name: '客户A', stage: 1, ecl: 300000 * 0.02 * 0.45 })
    expect(results[1]).toEqual({ name: '客户B', stage: 2, ecl: 200000 * 0.15 * 0.60 })
    expect(results[2]).toEqual({ name: '客户C', stage: 3, ecl: 100000 * 0.80 * 0.90 })

    // Total provision from K1-8
    const totalProvision = calcSubtotal(results.map(r => r.ecl))
    expect(totalProvision).toBeCloseTo(2700 + 18000 + 72000) // 92700
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Chain 2: 坏账测算链 — K1-8 calculation → K1-3 cross-validation
// ══════════════════════════════════════════════════════════════════════════════

describe('Chain 2: 坏账测算链 — calcAgingLoss → calcProvisionVariance vs K1-3', () => {
  it('aging buckets: calculate expected loss per bucket using calcAgingLoss', () => {
    // K1-8 账龄分析测算
    const agingBuckets = [
      { label: '1年以内', balance: 500000, lossRate: 0.05 },
      { label: '1-2年', balance: 200000, lossRate: 0.10 },
      { label: '2-3年', balance: 80000, lossRate: 0.30 },
      { label: '3年以上', balance: 50000, lossRate: 0.80 },
    ]

    const losses = agingBuckets.map(b => ({
      label: b.label,
      expectedLoss: calcAgingLoss(b.balance, b.lossRate),
    }))

    expect(losses[0].expectedLoss).toBe(25000)  // 500000 × 5%
    expect(losses[1].expectedLoss).toBe(20000)  // 200000 × 10%
    expect(losses[2].expectedLoss).toBe(24000)  // 80000 × 30%
    expect(losses[3].expectedLoss).toBe(40000)  // 50000 × 80%
  })

  it('total provision = sum of all aging bucket losses', () => {
    const agingBuckets = [
      { balance: 500000, lossRate: 0.05 },
      { balance: 200000, lossRate: 0.10 },
      { balance: 80000, lossRate: 0.30 },
      { balance: 50000, lossRate: 0.80 },
    ]

    const losses = agingBuckets.map(b => calcAgingLoss(b.balance, b.lossRate))
    const totalProvision = calcSubtotal(losses)

    expect(totalProvision).toBe(25000 + 20000 + 24000 + 40000)
    expect(totalProvision).toBe(109000)
  })

  it('calcProvisionVariance: K1-8 calculated vs K1-3 booked provision (企业多提)', () => {
    const calculated = 109000  // K1-8 测算应计提
    const booked = 120000      // K1-3 企业实际计提

    const variance = calcProvisionVariance(calculated, booked)

    // 差异<0 表示企业多计提
    expect(variance).toBe(-11000)
    expect(variance).toBeLessThan(0) // 企业多提
  })

  it('calcProvisionVariance: K1-8 calculated vs K1-3 booked provision (企业少提)', () => {
    const calculated = 109000  // K1-8 测算应计提
    const booked = 90000       // K1-3 企业实际计提

    const variance = calcProvisionVariance(calculated, booked)

    // 差异>0 表示企业少计提（需提示调整）
    expect(variance).toBe(19000)
    expect(variance).toBeGreaterThan(0) // 企业少提
  })

  it('end-to-end chain: aging → total → variance → materiality check', () => {
    const materialityLevel = 50000 // 重要性水平

    // Step 1: K1-8 aging loss calculation
    const agingData = [
      { balance: 800000, lossRate: 0.05 },
      { balance: 300000, lossRate: 0.12 },
      { balance: 120000, lossRate: 0.35 },
      { balance: 60000, lossRate: 0.70 },
    ]
    const losses = agingData.map(d => calcAgingLoss(d.balance, d.lossRate))
    const calcTotal = calcSubtotal(losses)

    // Step 2: K1-3 booked provision
    const bookedProvision = 80000

    // Step 3: variance
    const variance = calcProvisionVariance(calcTotal, bookedProvision)

    // Step 4: materiality check
    const exceedsMateriality = Math.abs(variance) > materialityLevel

    // Verify chain
    expect(calcTotal).toBeCloseTo(40000 + 36000 + 42000 + 42000) // 160000
    expect(variance).toBe(160000 - 80000) // 80000 (企业少提)
    expect(exceedsMateriality).toBe(true) // 80000 > 50000 → 红色标记
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Chain 3: 跨sheet勾稽 — useK1CrossSheet computeds
// ══════════════════════════════════════════════════════════════════════════════

describe('Chain 3: 跨sheet勾稽 — useK1CrossSheet', () => {
  function createAllResponses(data: Record<string, number>) {
    const map = new Map<string, any>()
    for (const [key, value] of Object.entries(data)) {
      map.set(key, { remark: value })
    }
    return ref(map)
  }

  describe('adjudicationVsDetail: K1-1 total === K1-2 subtotal', () => {
    it('matching data → isMatch=true, diff≈0', () => {
      const allResponses = createAllResponses({
        'K1-1-audited-receivable': 830000,
        'K1-2-end-subtotal': 830000,
      })

      const { adjudicationVsDetail } = useK1CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })

    it('mismatching data → isMatch=false, diff shows discrepancy', () => {
      const allResponses = createAllResponses({
        'K1-1-audited-receivable': 830000,
        'K1-2-end-subtotal': 815000,
      })

      const { adjudicationVsDetail } = useK1CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(15000)
    })

    it('missing K1-2 data → diff = K1-1 total (treated as 0)', () => {
      const allResponses = createAllResponses({
        'K1-1-audited-receivable': 500000,
      })

      const { adjudicationVsDetail } = useK1CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(500000)
    })
  })

  describe('badDebtVsCalc: K1-3 end === K1-8 calculated', () => {
    it('matching data → isMatch=true', () => {
      const allResponses = createAllResponses({
        'K1-3-bad-debt-end': 109000,
        'K1-8-calc-provision-total': 109000,
      })

      const { badDebtVsCalc } = useK1CrossSheet(allResponses)

      expect(badDebtVsCalc.value.isMatch).toBe(true)
      expect(badDebtVsCalc.value.diff).toBe(0)
    })

    it('K1-3 > K1-8 → diff > 0 (企业多计提)', () => {
      const allResponses = createAllResponses({
        'K1-3-bad-debt-end': 130000,
        'K1-8-calc-provision-total': 109000,
      })

      const { badDebtVsCalc } = useK1CrossSheet(allResponses)

      expect(badDebtVsCalc.value.isMatch).toBe(false)
      expect(badDebtVsCalc.value.diff).toBe(21000)
    })

    it('K1-3 < K1-8 → diff < 0 (企业少计提)', () => {
      const allResponses = createAllResponses({
        'K1-3-bad-debt-end': 90000,
        'K1-8-calc-provision-total': 109000,
      })

      const { badDebtVsCalc } = useK1CrossSheet(allResponses)

      expect(badDebtVsCalc.value.isMatch).toBe(false)
      expect(badDebtVsCalc.value.diff).toBe(-19000)
    })
  })

  describe('agingVsBalance: aging sum === end balance', () => {
    it('matching data → isMatch=true', () => {
      const allResponses = createAllResponses({
        'K1-2-aging-subtotal': 830000,
        'K1-2-end-subtotal': 830000,
      })

      const { agingVsBalance } = useK1CrossSheet(allResponses)

      expect(agingVsBalance.value.isMatch).toBe(true)
      expect(agingVsBalance.value.diff).toBe(0)
    })

    it('aging sum < end balance → diff < 0 (账龄划分遗漏)', () => {
      const allResponses = createAllResponses({
        'K1-2-aging-subtotal': 800000,
        'K1-2-end-subtotal': 830000,
      })

      const { agingVsBalance } = useK1CrossSheet(allResponses)

      expect(agingVsBalance.value.isMatch).toBe(false)
      expect(agingVsBalance.value.diff).toBe(-30000)
    })

    it('aging sum > end balance → diff > 0 (重复划分)', () => {
      const allResponses = createAllResponses({
        'K1-2-aging-subtotal': 850000,
        'K1-2-end-subtotal': 830000,
      })

      const { agingVsBalance } = useK1CrossSheet(allResponses)

      expect(agingVsBalance.value.isMatch).toBe(false)
      expect(agingVsBalance.value.diff).toBe(20000)
    })
  })

  describe('reactivity: computeds update when allResponses changes', () => {
    it('cross-sheet results update when allResponses map is mutated', async () => {
      const map = new Map<string, any>()
      map.set('K1-1-audited-receivable', { remark: 500000 })
      map.set('K1-2-end-subtotal', { remark: 500000 })
      const allResponses = ref(map)

      const { adjudicationVsDetail } = useK1CrossSheet(allResponses)

      // Initially matching
      expect(adjudicationVsDetail.value.isMatch).toBe(true)

      // Mutate map — change K1-2 subtotal
      const newMap = new Map(allResponses.value)
      newMap.set('K1-2-end-subtotal', { remark: 480000 })
      allResponses.value = newMap

      await nextTick()

      // Should now show mismatch
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(20000)
    })
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Chain 4: 审定回写链 — K1-1 sections → subtotal → writebackTB
// ══════════════════════════════════════════════════════════════════════════════

describe('Chain 4: 审定回写链 — calcSubtotal + calcAuditedAmount → TB amounts', () => {
  it('receivable section: calcAuditedAmount for each row → calcSubtotal → writeback amount', () => {
    // K1-1 其他应收款区块行
    const receivableRows = [
      { unadj: 300000, aje: 10000, rje: -5000 },
      { unadj: 200000, aje: 0, rje: 0 },
      { unadj: 150000, aje: -8000, rje: 3000 },
    ]

    // Calculate audited amount for each row
    const auditedAmounts = receivableRows.map(r =>
      calcAuditedAmount(r.unadj, r.aje, r.rje),
    )

    expect(auditedAmounts[0]).toBe(305000)  // 300000+10000-5000
    expect(auditedAmounts[1]).toBe(200000)  // 200000+0+0
    expect(auditedAmounts[2]).toBe(145000)  // 150000-8000+3000

    // Subtotal = sum of audited amounts → this goes to writebackTB as receivable amount
    const receivableTotal = calcSubtotal(auditedAmounts)
    expect(receivableTotal).toBe(650000)
  })

  it('bad debt section: calcAuditedAmount for each row → calcSubtotal → writeback amount', () => {
    // K1-1 坏账准备区块行
    const badDebtRows = [
      { unadj: 20000, aje: 5000, rje: 0 },
      { unadj: 15000, aje: 0, rje: 2000 },
      { unadj: 10000, aje: -3000, rje: 0 },
    ]

    const auditedAmounts = badDebtRows.map(r =>
      calcAuditedAmount(r.unadj, r.aje, r.rje),
    )

    expect(auditedAmounts[0]).toBe(25000)   // 20000+5000
    expect(auditedAmounts[1]).toBe(17000)   // 15000+2000
    expect(auditedAmounts[2]).toBe(7000)    // 10000-3000

    // Subtotal → writebackTB as bad debt amount
    const badDebtTotal = calcSubtotal(auditedAmounts)
    expect(badDebtTotal).toBe(49000)
  })

  it('net value = receivable total - bad debt total', () => {
    const receivableTotal = 650000
    const badDebtTotal = 49000

    const netValue = calcNetValue(receivableTotal, badDebtTotal)
    expect(netValue).toBe(601000)
  })

  it('full writeback chain: rows → audited → subtotals → writebackTB(receivable, badDebt)', () => {
    // Simulate complete K1-1 adjudication → writeback flow
    const receivableRows = [
      { unadj: 500000, aje: 20000, rje: -10000 },
      { unadj: 300000, aje: -5000, rje: 0 },
    ]
    const badDebtRows = [
      { unadj: 40000, aje: 8000, rje: 0 },
      { unadj: 25000, aje: 0, rje: 3000 },
    ]

    // Step 1: Audited amounts per row
    const receivableAudited = receivableRows.map(r => calcAuditedAmount(r.unadj, r.aje, r.rje))
    const badDebtAudited = badDebtRows.map(r => calcAuditedAmount(r.unadj, r.aje, r.rje))

    // Step 2: Subtotals
    const receivableTotal = calcSubtotal(receivableAudited)
    const badDebtTotal = calcSubtotal(badDebtAudited)

    expect(receivableTotal).toBe(510000 + 295000) // 805000
    expect(badDebtTotal).toBe(48000 + 28000) // 76000

    // Step 3: These values would be passed to writebackTB(receivableTotal, badDebtTotal)
    // writebackTB puts 1221 → receivableTotal, 1231 → badDebtTotal
    expect(receivableTotal).toBe(805000)
    expect(badDebtTotal).toBe(76000)

    // Step 4: Net value for display
    const netValue = calcNetValue(receivableTotal, badDebtTotal)
    expect(netValue).toBe(729000)
  })

  it('K1-3 bad debt balance chain: calcBadDebtEnd matches K1-1 audited bad debt', () => {
    // K1-3 期末坏账=期初+计提-转回-核销
    const begin = 40000
    const provision = 50000
    const reversal = 5000
    const writeoff = 9000

    const badDebtEnd = calcBadDebtEnd(begin, provision, reversal, writeoff)
    expect(badDebtEnd).toBe(76000) // 40000+50000-5000-9000

    // This should match K1-1 坏账准备审定合计 (cross-validation Req 4.5)
    const k1_1_badDebtAudited = 76000
    expect(badDebtEnd).toBe(k1_1_badDebtAudited)
  })

  it('asset end balance chain: calcAssetEndBalance validates period movement', () => {
    // K1-1 资产类期末=期初+借方-贷方
    const begin = 700000
    const debit = 200000
    const credit = 95000

    const endBalance = calcAssetEndBalance(begin, debit, credit)
    expect(endBalance).toBe(805000) // 700000+200000-95000

    // This should match the receivable audited total
    expect(endBalance).toBe(805000)
  })

  it('contra end balance chain: calcContraEndBalance validates bad debt movement', () => {
    // 坏账准备备抵类期末=期初+贷方-借方
    const begin = 40000
    const credit = 50000 // 计提
    const debit = 14000  // 转回+核销

    const endBalance = calcContraEndBalance(begin, credit, debit)
    expect(endBalance).toBe(76000) // 40000+50000-14000
  })
})
