/**
 * 集成测试 — L7 其他非流动负债
 *
 * 覆盖：
 * 1. useL7Adjudication: computedRows + totalRow 自动计算
 * 2. useL7CrossSheet: adjudicationVsDetail match/mismatch
 * 3. useL7Adjustment: 借贷平衡校验
 * 4. 完整流程: update adjudication → compute total → validate vs detail
 * 5. writebackTB 验证
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/ Task 7.2
 * Requirements: 2.5, 2.6
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useL7CrossSheet } from '../composables/useL7CrossSheet'
import type { ChecklistResponse } from '../composables/useL7FormData'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
  calcLiabilityEndBalance,
  validateAdjudicationVsDetail,
} from '../composables/useL7FormulaEngine'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// Mock api
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion: null, remark })
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: useL7Adjudication — totalRow 计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL7Adjudication totalRow 计算 (Req 2.1-2.4)', () => {
  /**
   * 模拟 useL7Adjudication 的核心逻辑（不依赖 Vue composable 生命周期）
   * 直接验证公式引擎在审定表多行场景下的正确性
   */
  interface MockRow {
    itemName: string
    beginUnadjusted: number
    beginAje: number
    beginRje: number
    endUnadjusted: number
    endAje: number
    endRje: number
  }

  function computeAdjudicationTotal(rows: MockRow[]) {
    const computed = rows.map(row => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const variance = calcVariance(endAudited, beginAudited)
      const varianceRate = calcVarianceRate(endAudited, beginAudited)
      return { ...row, beginAudited, endAudited, variance, varianceRate }
    })

    const beginUnadjusted = calcSubtotal(computed.map(x => x.beginUnadjusted))
    const beginAje = calcSubtotal(computed.map(x => x.beginAje))
    const beginRje = calcSubtotal(computed.map(x => x.beginRje))
    const beginAudited = calcSubtotal(computed.map(x => x.beginAudited))
    const endUnadjusted = calcSubtotal(computed.map(x => x.endUnadjusted))
    const endAje = calcSubtotal(computed.map(x => x.endAje))
    const endRje = calcSubtotal(computed.map(x => x.endRje))
    const endAudited = calcSubtotal(computed.map(x => x.endAudited))
    const variance = calcVariance(endAudited, beginAudited)
    const varianceRate = calcVarianceRate(endAudited, beginAudited)

    return {
      computed,
      total: { beginUnadjusted, beginAje, beginRje, beginAudited, endUnadjusted, endAje, endRje, endAudited, variance, varianceRate },
    }
  }

  it('5行数据: totalRow正确汇总各行审定', () => {
    const rows: MockRow[] = [
      { itemName: '递延收益', beginUnadjusted: 1_000_000, beginAje: 0, beginRje: 0, endUnadjusted: 1_200_000, endAje: 50_000, endRje: 0 },
      { itemName: '保证金', beginUnadjusted: 500_000, beginAje: -20_000, beginRje: 0, endUnadjusted: 600_000, endAje: 0, endRje: 0 },
      { itemName: '质保金', beginUnadjusted: 300_000, beginAje: 0, beginRje: 10_000, endUnadjusted: 350_000, endAje: 0, endRje: 0 },
      { itemName: '专项拨款', beginUnadjusted: 2_000_000, beginAje: 100_000, beginRje: 0, endUnadjusted: 1_800_000, endAje: -50_000, endRje: 0 },
      { itemName: '其他', beginUnadjusted: 200_000, beginAje: 0, beginRje: 0, endUnadjusted: 250_000, endAje: 0, endRje: 30_000 },
    ]

    const { total } = computeAdjudicationTotal(rows)

    // 期末审定合计 = Σ(endUnadjusted + endAje + endRje)
    // = (1250000) + (600000) + (350000) + (1750000) + (280000) = 4230000
    expect(total.endAudited).toBe(4_230_000)
    // 期初审定合计 = Σ(beginUnadjusted + beginAje + beginRje)
    // = (1000000) + (480000) + (310000) + (2100000) + (200000) = 4090000
    expect(total.beginAudited).toBe(4_090_000)
    // 变动额 = 4230000 - 4090000 = 140000
    expect(total.variance).toBe(140_000)
  })

  it('所有行为0 → totalRow全0', () => {
    const rows: MockRow[] = Array(5).fill({
      itemName: '', beginUnadjusted: 0, beginAje: 0, beginRje: 0,
      endUnadjusted: 0, endAje: 0, endRje: 0,
    })
    const { total } = computeAdjudicationTotal(rows)
    expect(total.endAudited).toBe(0)
    expect(total.variance).toBe(0)
    expect(total.varianceRate).toBe(0)
  })

  it('单行: totalRow === 该行审定', () => {
    const rows: MockRow[] = [
      { itemName: '单项', beginUnadjusted: 800_000, beginAje: 50_000, beginRje: 0, endUnadjusted: 900_000, endAje: 100_000, endRje: -20_000 },
    ]
    const { total, computed } = computeAdjudicationTotal(rows)
    expect(total.endAudited).toBe(computed[0].endAudited)
    expect(total.endAudited).toBe(980_000) // 900000 + 100000 - 20000
  })

  it('变动率计算: totalRow正确应用xlsx公式', () => {
    const rows: MockRow[] = [
      { itemName: 'A', beginUnadjusted: 0, beginAje: 0, beginRje: 0, endUnadjusted: 500_000, endAje: 0, endRje: 0 },
    ]
    const { total } = computeAdjudicationTotal(rows)
    // 期初=0, 期末=500000 → varianceRate=1 (100%增长, xlsx IF(E=0,J>0)=1)
    expect(total.varianceRate).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: useL7CrossSheet — 审定vs明细勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL7CrossSheet adjudicationVsDetail (Req 2.5, 3.5)', () => {
  it('审定表合计 === 明细表合计 → isMatch=true', () => {
    const responses = createResponses([
      ['L7-L7-1-total-audited', '3000000'],
      ['L7-L7-2-item1-end_balance', '1200000'],
      ['L7-L7-2-item2-end_balance', '800000'],
      ['L7-L7-2-item3-end_balance', '1000000'],
    ])

    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 1)
  })

  it('审定表合计 ≠ 明细表合计 → isMatch=false + positive diff', () => {
    const responses = createResponses([
      ['L7-L7-1-total-audited', '5000000'],
      ['L7-L7-2-item1-end_balance', '2000000'],
      ['L7-L7-2-item2-end_balance', '1500000'],
    ])

    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(1_500_000, 0)
  })

  it('明细表合计 > 审定表 → negative diff', () => {
    const responses = createResponses([
      ['L7-L7-1-total-audited', '2000000'],
      ['L7-L7-2-item1-end_balance', '1500000'],
      ['L7-L7-2-item2-end_balance', '1000000'],
    ])

    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(-500_000, 0)
  })

  it('明细表为空(无L7-2 item) → diff=审定数全额', () => {
    const responses = createResponses([
      ['L7-L7-1-total-audited', '4000000'],
    ])

    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(4_000_000, 0)
  })

  it('两侧都为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])
    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('非L7-2前缀的key不参与明细合计', () => {
    const responses = createResponses([
      ['L7-L7-1-total-audited', '1000000'],
      ['L7-L7-2-item1-end_balance', '1000000'],
      ['L7-L7-4-check1-end_balance', '999999'], // L7-4 不是明细表
    ])

    const { adjudicationVsDetail } = useL7CrossSheet(responses)
    // L7-4开头的不匹配"L7-L7-2-*-end_balance"模式
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: useL7Adjustment — 借贷平衡校验
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL7Adjustment 借贷平衡 (Req 4.3)', () => {
  /**
   * 直接测试借贷平衡逻辑（不需要完整composable生命周期）
   */
  interface MockEntry {
    type: 'AJE' | 'RJE'
    debitAmount: number
    creditAmount: number
    accountName: string
  }

  function calcBalance(entries: MockEntry[]) {
    const totalDebit = parseFloat(calcSubtotal(entries.map(e => e.debitAmount)).toFixed(2))
    const totalCredit = parseFloat(calcSubtotal(entries.map(e => e.creditAmount)).toFixed(2))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
    }
  }

  it('借方合计 === 贷方合计 → isBalanced=true', () => {
    const entries: MockEntry[] = [
      { type: 'AJE', debitAmount: 100_000, creditAmount: 0, accountName: '管理费用' },
      { type: 'AJE', debitAmount: 0, creditAmount: 100_000, accountName: '其他非流动负债' },
    ]
    const balance = calcBalance(entries)
    expect(balance.isBalanced).toBe(true)
    expect(balance.diff).toBe(0)
  })

  it('借方 > 贷方 → isBalanced=false, diff>0', () => {
    const entries: MockEntry[] = [
      { type: 'AJE', debitAmount: 200_000, creditAmount: 0, accountName: '管理费用' },
      { type: 'AJE', debitAmount: 0, creditAmount: 150_000, accountName: '其他非流动负债' },
    ]
    const balance = calcBalance(entries)
    expect(balance.isBalanced).toBe(false)
    expect(balance.diff).toBe(50_000)
  })

  it('多行复合分录借贷平衡', () => {
    const entries: MockEntry[] = [
      { type: 'AJE', debitAmount: 50_000, creditAmount: 0, accountName: '管理费用' },
      { type: 'AJE', debitAmount: 30_000, creditAmount: 0, accountName: '营业外支出' },
      { type: 'AJE', debitAmount: 0, creditAmount: 50_000, accountName: '其他非流动负债' },
      { type: 'AJE', debitAmount: 0, creditAmount: 30_000, accountName: '预计负债' },
    ]
    const balance = calcBalance(entries)
    expect(balance.isBalanced).toBe(true)
    expect(balance.totalDebit).toBe(80_000)
    expect(balance.totalCredit).toBe(80_000)
  })

  it('空分录 → isBalanced=true (0=0)', () => {
    const balance = calcBalance([])
    expect(balance.isBalanced).toBe(true)
    expect(balance.diff).toBe(0)
  })

  it('浮点精度容差 ≤ 0.01', () => {
    // 借贷差0.005视为平衡
    const entries: MockEntry[] = [
      { type: 'AJE', debitAmount: 100_000.005, creditAmount: 0, accountName: '费用' },
      { type: 'AJE', debitAmount: 0, creditAmount: 100_000, accountName: '负债' },
    ]
    const balance = calcBalance(entries)
    // 0.005 < 0.01 → balanced
    expect(balance.isBalanced).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 完整流程 — 审定→合计→勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 完整流程: 审定→合计→明细勾稽 (Req 2.5, 2.6)', () => {
  it('审定表更新 → totalRow重算 → 与明细表勾稽一致', () => {
    // Step 1: 审定表5行数据
    const rows = [
      { endUnadjusted: 1_200_000, endAje: 50_000, endRje: 0 },
      { endUnadjusted: 600_000, endAje: 0, endRje: 0 },
      { endUnadjusted: 350_000, endAje: 0, endRje: 0 },
      { endUnadjusted: 1_800_000, endAje: -50_000, endRje: 0 },
      { endUnadjusted: 250_000, endAje: 0, endRje: 30_000 },
    ]

    // Step 2: 计算合计审定数
    const endAuditedPerRow = rows.map(r => calcAuditedAmount(r.endUnadjusted, r.endAje, r.endRje))
    const totalEndAudited = calcSubtotal(endAuditedPerRow)
    // 1250000 + 600000 + 350000 + 1750000 + 280000 = 4230000
    expect(totalEndAudited).toBe(4_230_000)

    // Step 3: 明细表各项目期末余额之和 = 审定表合计
    const detailTotal = 4_230_000
    const validation = validateAdjudicationVsDetail(totalEndAudited, detailTotal)
    expect(validation.isMatch).toBe(true)
    expect(validation.diff).toBe(0)
  })

  it('审定表AJE调增 → 与明细不一致 → diff正数', () => {
    // 审定表合计
    const adjTotal = calcAuditedAmount(3_000_000, 200_000, 0) // 3200000
    // 明细表未同步更新，仍为3000000
    const detailTotal = 3_000_000
    const validation = validateAdjudicationVsDetail(adjTotal, detailTotal)
    expect(validation.isMatch).toBe(false)
    expect(validation.diff).toBe(200_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: writebackTB 验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — writebackTB (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('writebackTB 调用API正确参数（科目2801）', async () => {
    const { useL7FormData } = await import('../composables/useL7FormData')

    // 模拟 effectScope 避免 onScopeDispose 报错
    const { effectScope } = await import('vue')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL7FormData({
        wpId: ref('test-wp-001'),
        projectId: ref('test-project-001'),
      })

      await formData.writebackTB(4_230_000)

      expect(api.put).toHaveBeenCalledWith(
        '/api/projects/test-project-001/trial-balance/writeback',
        {
          account_code: '2801',
          audited_amount: 4_230_000,
        },
      )
    })

    scope.stop()
  })

  it('writebackTB 成功后发布 substantive:adjudicated EventBus', async () => {
    const { useL7FormData } = await import('../composables/useL7FormData')
    const { effectScope } = await import('vue')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL7FormData({
        wpId: ref('test-wp-002'),
        projectId: ref('test-project-002'),
      })

      await formData.writebackTB(5_000_000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          accountCode: '2801',
          auditedAmount: 5_000_000,
          wpCode: 'L7',
        }),
      )
    })

    scope.stop()
  })

  it('writebackTB 空projectId时不调用API', async () => {
    const { useL7FormData } = await import('../composables/useL7FormData')
    const { effectScope } = await import('vue')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL7FormData({
        wpId: ref('test-wp'),
        projectId: ref(''), // 空
      })

      await formData.writebackTB(1_000_000)
      expect(api.put).not.toHaveBeenCalled()
    })

    scope.stop()
  })
})
