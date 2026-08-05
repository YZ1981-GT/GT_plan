/**
 * H8 使用权资产 — 集成式单元测试（跨composable交互）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 7.1
 * Validates: Requirements P1-P10, 11.1-11.4
 *
 * 测试 useH8CrossSheet composable 与 useH8FormulaEngine / useH8CAS21Engine 的协作：
 * - adjudicationVsDetail: H8-1审定合计 vs H8-2明细合计
 * - h8VsH9Linkage: CAS21核心联动公式 H8=H9+直接费用-激励（±1元容差）
 * - depreciationVsAdjudication: H8-8折旧合计 vs H8-1累计折旧本期计提
 * - disclosureAutoFill: 附注自动取数
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { useH8CrossSheet } from '../composables/useH8CrossSheet'
import { calcAuditedAmount, calcAssetEndBalance, calcContraEndBalance, calcNetValue, calcSubtotal } from '../composables/useH8FormulaEngine'
import { calcInitialMeasurement, calcDepreciationPeriod, calcTerminationGainLoss, isShortTermLease, isLowValueLease } from '../composables/useH8CAS21Engine'
import { H8_ROU_COST_CODE, H8_ROU_DEP_CODE } from '../composables/useH8Adjustment'
import { h9Scope } from '../composables/hCycleAccountScope'

const LEASE_LIABILITY_CODE = h9Scope.def.grossFallback

// ─── Helper: 构造 allResponses Map ──────────────────────────────────────────

function createMockResponses(data: Record<string, any>): Map<string, any> {
  const map = new Map<string, any>()
  for (const [key, value] of Object.entries(data)) {
    map.set(key, { remark: typeof value === 'string' ? value : String(value) })
  }
  return map
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: useH8CrossSheet — adjudicationVsDetail
// Validates: Requirements 2.5
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — adjudicationVsDetail', () => {
  it('H8-1审定合计与H8-2明细合计相等时 isMatch=true', async () => {
    const allResponses = ref(createMockResponses({
      'H8-1-cost-audited-total': '500000',
      'H8-2-detail-total': '500000',
      'H8-1-dep-audited-total': '80000',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    }))

    const { adjudicationVsDetail } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
  })

  it('H8-1审定合计与H8-2明细合计不一致时 isMatch=false + diff正确', async () => {
    const allResponses = ref(createMockResponses({
      'H8-1-cost-audited-total': '500000',
      'H8-2-detail-total': '480000',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    }))

    const { adjudicationVsDetail } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(20000, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: useH8CrossSheet — h8VsH9Linkage (CAS21核心)
// Validates: Requirements 11.1-11.4
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — h8VsH9Linkage', () => {
  it('CAS21公式一致时 isConsistent=true (H8=H9+直接费用-激励)', async () => {
    // H9初始=100000, 直接费用=5000, 激励=2000 → 期望H8=103000
    const allResponses = ref(createMockResponses({
      'H8-initial-measurement': '103000',
      'H9-1-initial-liability': '100000',
      'H8-direct-cost-total': '5000',
      'H8-incentive-total': '2000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
      'H8-8-depreciation-total': '0',
    }))

    const { h8VsH9Linkage } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(h8VsH9Linkage.value.isConsistent).toBe(true)
    expect(h8VsH9Linkage.value.diff).toBeCloseTo(0, 2)
    expect(h8VsH9Linkage.value.message).toContain('一致')
  })

  it('CAS21尾差±1元容差内仍判定一致', async () => {
    // H9=100000, 直接=5000, 激励=2000 → 期望H8=103000, 实际H8=103000.5 (diff=0.5)
    const allResponses = ref(createMockResponses({
      'H8-initial-measurement': '103000.5',
      'H9-1-initial-liability': '100000',
      'H8-direct-cost-total': '5000',
      'H8-incentive-total': '2000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
      'H8-8-depreciation-total': '0',
    }))

    const { h8VsH9Linkage } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(h8VsH9Linkage.value.isConsistent).toBe(true)
    expect(Math.abs(h8VsH9Linkage.value.diff)).toBeLessThanOrEqual(1)
  })

  it('CAS21差额超过1元时 isConsistent=false + 红色警告消息', async () => {
    // H9=100000, 直接=5000, 激励=2000 → 期望H8=103000, 实际H8=105000 (diff=2000)
    const allResponses = ref(createMockResponses({
      'H8-initial-measurement': '105000',
      'H9-1-initial-liability': '100000',
      'H8-direct-cost-total': '5000',
      'H8-incentive-total': '2000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
      'H8-8-depreciation-total': '0',
    }))

    const { h8VsH9Linkage } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(h8VsH9Linkage.value.isConsistent).toBe(false)
    expect(h8VsH9Linkage.value.diff).toBeCloseTo(2000, 2)
    expect(h8VsH9Linkage.value.message).toContain('不一致')
  })

  it('H9数据未加载时提示暂无法校验', async () => {
    const allResponses = ref(createMockResponses({
      'H8-initial-measurement': '0',
      'H9-1-initial-liability': '0',
      'H8-direct-cost-total': '0',
      'H8-incentive-total': '0',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
      'H8-8-depreciation-total': '0',
    }))

    const { h8VsH9Linkage } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(h8VsH9Linkage.value.message).toContain('暂无法校验')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: useH8CrossSheet — depreciationVsAdjudication
// Validates: Requirements 6.6
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — depreciationVsAdjudication', () => {
  it('H8-8折旧合计与H8-1本期计提一致时 isMatch=true', async () => {
    const allResponses = ref(createMockResponses({
      'H8-8-depreciation-total': '25000',
      'H8-1-dep-current-provision': '25000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
    }))

    const { depreciationVsAdjudication } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(depreciationVsAdjudication.value.isMatch).toBe(true)
    expect(depreciationVsAdjudication.value.diff).toBeCloseTo(0, 2)
  })

  it('H8-8折旧与H8-1计提不一致时 isMatch=false', async () => {
    const allResponses = ref(createMockResponses({
      'H8-8-depreciation-total': '30000',
      'H8-1-dep-current-provision': '25000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
    }))

    const { depreciationVsAdjudication } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(depreciationVsAdjudication.value.isMatch).toBe(false)
    expect(depreciationVsAdjudication.value.diff).toBeCloseTo(5000, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3b: useH8CrossSheet — allocationVsDepreciation
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — allocationVsDepreciation', () => {
  it('H8-9分配合计与H8-8折旧一致时 isMatch=true', async () => {
    const allResponses = ref(createMockResponses({
      'H8-8-depreciation-total': '10000',
      'H8-9-alloc-total': '10000',
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    }))

    const { allocationVsDepreciation } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(allocationVsDepreciation.value.isMatch).toBe(true)
    expect(allocationVsDepreciation.value.diff).toBeCloseTo(0, 2)
  })

  it('可从矩阵行聚合分配合计（无汇总 item）', async () => {
    const allResponses = ref(createMockResponses({
      'H8-8-depreciation-total': '1500',
      'H8-9-alloc-rows': JSON.stringify([
        { category: '房屋及建筑物', admin: 1000, operatingCost: 0, manufacturing: 0, selling: 0, rd: 0, other: 0 },
        { category: '机器设备', operatingCost: 500, manufacturing: 0, selling: 0, admin: 0, rd: 0, other: 0 },
      ]),
      'H8-1-cost-audited-total': '0',
      'H8-2-detail-total': '0',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    }))

    const { allocationTotal, allocationVsDepreciation } = useH8CrossSheet(allResponses)
    await nextTick()

    expect(allocationTotal.value).toBeCloseTo(1500, 2)
    expect(allocationVsDepreciation.value.isMatch).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3c: h83AdjustmentSync — H8-3 → H8-1 AJE/RJE
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — h83AdjustmentSync', () => {
  it('从 H8-3-rows 汇总 原值/累计折旧 账项与报表净额', async () => {
    const rows = [
      { category: '账项调整', accountCode: H8_ROU_COST_CODE, debitAmount: 500, creditAmount: 0 },
      { category: '账项调整', accountCode: LEASE_LIABILITY_CODE, debitAmount: 0, creditAmount: 500 },
      { category: '账项调整', accountCode: H8_ROU_DEP_CODE, debitAmount: 0, creditAmount: 80 },
      { category: '账项调整', accountCode: '6603', debitAmount: 80, creditAmount: 0 },
      { category: '报表调整', accountCode: H8_ROU_COST_CODE, debitAmount: 100, creditAmount: 0 },
      { category: '报表调整', accountCode: '1601', debitAmount: 0, creditAmount: 100 },
    ]
    const map = createMockResponses({})
    map.set('H8-3-rows', {
      item_id: 'H8-3-rows',
      conclusion: null,
      remark: JSON.stringify(rows),
    })
    const allResponses = ref(map)
    const { h83AdjustmentSync } = useH8CrossSheet(allResponses)
    await nextTick()
    expect(h83AdjustmentSync.value.rowCount).toBe(6)
    expect(h83AdjustmentSync.value.rouCostAjeNet).toBeCloseTo(500, 2)
    expect(h83AdjustmentSync.value.rouCostRjeNet).toBeCloseTo(100, 2)
    expect(h83AdjustmentSync.value.rouDepAjeNet).toBeCloseTo(-80, 2)
  })

  it('无行时回退 H8-3-aje-net / H8-3-rje-net', async () => {
    const allResponses = ref(createMockResponses({
      'H8-3-aje-net': '1200',
      'H8-3-rje-net': '-50',
      'H8-3-dep-aje-net': '-30',
      'H8-3-dep-rje-net': '0',
    }))
    const { h83AdjustmentSync } = useH8CrossSheet(allResponses)
    await nextTick()
    expect(h83AdjustmentSync.value.rowCount).toBe(0)
    expect(h83AdjustmentSync.value.rouCostAjeNet).toBeCloseTo(1200, 2)
    expect(h83AdjustmentSync.value.rouCostRjeNet).toBeCloseTo(-50, 2)
    expect(h83AdjustmentSync.value.rouDepAjeNet).toBeCloseTo(-30, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: disclosureAutoFill — 附注自动取数
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — disclosureAutoFill', () => {
  it('从H8-1审定表汇总数据正确计算期末余额', async () => {
    const allResponses = ref(createMockResponses({
      'H8-1-cost-audited-total': '600000',
      'H8-1-dep-audited-total': '120000',
      'H8-1-cost-begin-total': '500000',
      'H8-1-cost-debit-total': '150000',
      'H8-1-cost-credit-total': '50000',
      'H8-1-dep-begin-total': '80000',
      'H8-1-dep-debit-total': '10000',
      'H8-1-dep-credit-total': '50000',
      'H8-1-dep-current-provision': '50000',
      'H8-2-detail-total': '600000',
      'H8-8-depreciation-total': '50000',
    }))

    const { disclosureAutoFill } = useH8CrossSheet(allResponses)
    await nextTick()

    const fill = disclosureAutoFill.value
    // 原值期末 = 500000 + 150000 - 50000 = 600000 (calcAssetEndBalance)
    expect(fill.disc_cost_end).toBeCloseTo(600000, 2)
    // 折旧期末 = 80000 + 50000 - 10000 = 120000 (calcContraEndBalance)
    expect(fill.disc_dep_end).toBeCloseTo(120000, 2)
    // 净值 = 原值期末 - 折旧期末 = 600000 - 120000 = 480000
    expect(fill.disc_net_value).toBeCloseTo(480000, 2)
    expect(fill.disc_dep_provision).toBeCloseTo(50000, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 跨引擎协作 — FormulaEngine + CAS21Engine 联合验证
// Validates: Requirements P1-P10
// ═══════════════════════════════════════════════════════════════════════════════

describe('FormulaEngine + CAS21Engine 跨引擎协作', () => {
  it('CAS21初始计量与FormulaEngine审定数协同', () => {
    // CAS21: H8 = H9(100000) + 直接(5000) - 激励(2000) = 103000
    const initialH8 = calcInitialMeasurement(100000, 5000, 2000)
    expect(initialH8).toBe(103000)

    // FormulaEngine: 审定数 = 未审(103000) + AJE(0) + RJE(0) = 103000
    const audited = calcAuditedAmount(initialH8, 0, 0)
    expect(audited).toBe(103000)

    // FormulaEngine: 资产期末 = 期初(0) + 借方(103000) - 贷方(0) = 103000
    const endBalance = calcAssetEndBalance(0, initialH8, 0)
    expect(endBalance).toBe(103000)
  })

  it('折旧期确定 + 净值计算链', () => {
    // CAS21: 折旧期 = min(36月, 120月) = 36月
    const depPeriod = calcDepreciationPeriod(36, 120)
    expect(depPeriod).toBe(36)

    // FormulaEngine: 净值 = 原值(103000) - 累计折旧(25750) - 减值(0) = 77250
    const netValue = calcNetValue(103000, 25750, 0)
    expect(netValue).toBe(77250)
  })

  it('终止损益 + 备抵期末余额 + 合计行', () => {
    // CAS21: 终止损益 = 负债余额(80000) - 净值(77250) = 2750(收益)
    const gainLoss = calcTerminationGainLoss(80000, 77250)
    expect(gainLoss).toBeCloseTo(2750, 2)

    // FormulaEngine: 备抵期末 = 期初(0) + 贷方(25750) - 借方(0) = 25750
    const contraEnd = calcContraEndBalance(0, 0, 25750)
    expect(contraEnd).toBe(25750)

    // FormulaEngine: 合计行
    const total = calcSubtotal([103000, 200000, 50000])
    expect(total).toBe(353000)
  })

  it('简化判断 + 合计行排除', () => {
    // CAS21: 短期(6月)=true, 低价值(30000)=true
    expect(isShortTermLease(6)).toBe(true)
    expect(isLowValueLease(30000)).toBe(true)

    // 不满足简化条件的
    expect(isShortTermLease(24)).toBe(false)
    expect(isLowValueLease(80000)).toBe(false)

    // FormulaEngine: 空数组合计=0
    expect(calcSubtotal([])).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: 响应式更新验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH8CrossSheet — 响应式更新', () => {
  it('allResponses变化时computed自动重算', async () => {
    const allResponses = ref(createMockResponses({
      'H8-1-cost-audited-total': '500000',
      'H8-2-detail-total': '500000',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    }))

    const { adjudicationVsDetail } = useH8CrossSheet(allResponses)
    await nextTick()
    expect(adjudicationVsDetail.value.isMatch).toBe(true)

    // 更新 H8-1 审定合计 → 产生差异
    const newMap = createMockResponses({
      'H8-1-cost-audited-total': '520000',
      'H8-2-detail-total': '500000',
      'H8-1-dep-audited-total': '0',
      'H8-1-cost-begin-total': '0',
      'H8-1-cost-debit-total': '0',
      'H8-1-cost-credit-total': '0',
      'H8-1-dep-begin-total': '0',
      'H8-1-dep-debit-total': '0',
      'H8-1-dep-credit-total': '0',
      'H8-1-dep-current-provision': '0',
    })
    allResponses.value = newMap
    await nextTick()

    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(20000, 2)
  })
})
