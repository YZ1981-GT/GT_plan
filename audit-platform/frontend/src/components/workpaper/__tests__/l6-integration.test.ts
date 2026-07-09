/**
 * 集成测试 — L6 专项应付款
 *
 * 覆盖：
 * 1. useL6CrossSheet: 审定表L6-1 vs 明细表L6-2 勾稽验证
 * 2. writebackTB: TB回写(2601) + EventBus发布
 * 3. EventBus publish: 'substantive:adjudicated' 事件正确载荷
 * 4. 负余额检测: 期末<0预警
 * 5. 公式方向验证: 负债类(begin+credit-debit), 非资产类(begin+debit-credit)
 *
 * Spec: .kiro/specs/l6-special-payables/ Task 7.2
 * Requirements: 2.5, 2.6
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useL6CrossSheet } from '../composables/useL6CrossSheet'
import type { ChecklistResponse } from '../composables/useL6FormData'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  validateAdjudicationVsDetail,
} from '../composables/useL6FormulaEngine'

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
// Section 1: 审定→明细勾稽 (useL6CrossSheet)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL6CrossSheet 审定vs明细勾稽 (Req 2.5)', () => {
  it('审定表合计 === 明细表合计 → isMatch=true', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '5000000'],
      ['L6-L6-2-project1-end_balance', '2000000'],
      ['L6-L6-2-project2-end_balance', '1500000'],
      ['L6-L6-2-project3-end_balance', '1500000'],
    ])

    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('审定表合计 > 明细表合计 → isMatch=false, diff>0', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '8000000'],
      ['L6-L6-2-project1-end_balance', '3000000'],
      ['L6-L6-2-project2-end_balance', '2000000'],
    ])

    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(3_000_000)
  })

  it('明细表合计 > 审定表合计 → diff<0', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '2000000'],
      ['L6-L6-2-project1-end_balance', '1500000'],
      ['L6-L6-2-project2-end_balance', '1200000'],
    ])

    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(-700_000)
  })

  it('明细表为空(无L6-2 item) → diff=审定表全额', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '6000000'],
    ])

    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(6_000_000)
  })

  it('两侧都为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])
    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('非L6-2前缀的key不参与明细合计', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '1000000'],
      ['L6-L6-2-project1-end_balance', '1000000'],
      ['L6-L6-4-check1-end_balance', '999999'], // L6-4检查表，不参与
    ])

    const { adjudicationVsDetail } = useL6CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('便捷属性 adjTotal/detailTotal/isMatch/diff 正确', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '3000000'],
      ['L6-L6-2-project1-end_balance', '1800000'],
      ['L6-L6-2-project2-end_balance', '1200000'],
    ])

    const { adjTotal, detailTotal, isMatch, diff } = useL6CrossSheet(responses)
    expect(adjTotal.value).toBe(3_000_000)
    expect(detailTotal.value).toBe(3_000_000)
    expect(isMatch.value).toBe(true)
    expect(diff.value).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: writebackTB 触发 (Req 2.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — writebackTB (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('writebackTB 调用API正确参数（科目2601）', async () => {
    const { useL6FormData } = await import('../composables/useL6FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL6FormData({
        wpId: ref('test-wp-l6-001'),
        projectId: ref('test-project-001'),
      })

      await formData.writebackTB(5_000_000)

      expect(api.put).toHaveBeenCalledWith(
        '/api/projects/test-project-001/trial-balance/writeback',
        {
          account_code: '2601',
          audited_amount: 5_000_000,
        },
      )
    })

    scope.stop()
  })

  it('writebackTB 空projectId时不调用API', async () => {
    const { useL6FormData } = await import('../composables/useL6FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL6FormData({
        wpId: ref('test-wp-l6'),
        projectId: ref(''), // 空
      })

      await formData.writebackTB(1_000_000)
      expect(api.put).not.toHaveBeenCalled()
    })

    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: EventBus publish (Req 2.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus publish (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('writebackTB 成功后发布 substantive:adjudicated 事件', async () => {
    const { useL6FormData } = await import('../composables/useL6FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL6FormData({
        wpId: ref('test-wp-l6-002'),
        projectId: ref('test-project-002'),
      })

      await formData.writebackTB(7_500_000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          accountCode: '2601',
          auditedAmount: 7_500_000,
          wpCode: 'L6',
          timestamp: expect.any(Number),
        }),
      )
    })

    scope.stop()
  })

  it('writebackTB 事件载荷 timestamp 为合理时间', async () => {
    const { useL6FormData } = await import('../composables/useL6FormData')
    const scope = effectScope()

    const beforeTs = Date.now()

    await scope.run(async () => {
      const formData = useL6FormData({
        wpId: ref('test-wp-l6-003'),
        projectId: ref('test-project-003'),
      })

      await formData.writebackTB(3_000_000)
    })

    const afterTs = Date.now()

    const emitCall = vi.mocked(eventBus.emit).mock.calls.find(
      c => c[0] === 'substantive:adjudicated'
    )
    expect(emitCall).toBeDefined()
    const payload = emitCall![1] as any
    expect(payload.timestamp).toBeGreaterThanOrEqual(beforeTs)
    expect(payload.timestamp).toBeLessThanOrEqual(afterTs)

    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 负余额检测 (设计文档 P5 / 错误处理)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 负余额检测 (Req 2.5)', () => {
  it('正常余额 → 期末≥0', () => {
    const endBalance = calcLiabilityEndBalance(1_000_000, 500_000, 300_000)
    // 1000000 + 500000 - 300000 = 1200000
    expect(endBalance).toBe(1_200_000)
    expect(endBalance).toBeGreaterThanOrEqual(0)
  })

  it('借方发生>期初+贷方 → 期末<0（负余额预警场景）', () => {
    const endBalance = calcLiabilityEndBalance(500_000, 200_000, 900_000)
    // 500000 + 200000 - 900000 = -200000
    expect(endBalance).toBe(-200_000)
    expect(endBalance).toBeLessThan(0)
  })

  it('期初=0+贷方=0+借方>0 → 负余额', () => {
    const endBalance = calcLiabilityEndBalance(0, 0, 100_000)
    expect(endBalance).toBe(-100_000)
    expect(endBalance).toBeLessThan(0)
  })

  it('明细表中含负余额项目可通过勾稽检出', () => {
    // 审定表合计=正，但明细中有负余额项
    const responses = createResponses([
      ['L6-L6-1-total-audited', '1000000'],
      ['L6-L6-2-project1-end_balance', '1500000'],
      ['L6-L6-2-project2-end_balance', '-500000'], // 负余额项
    ])

    const { adjudicationVsDetail, detailTotal } = useL6CrossSheet(responses)
    // 明细合计 = 1500000 + (-500000) = 1000000
    expect(detailTotal.value).toBe(1_000_000)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('负余额项目在明细中仍正确参与合计', () => {
    const responses = createResponses([
      ['L6-L6-1-total-audited', '800000'],
      ['L6-L6-2-project1-end_balance', '1200000'],
      ['L6-L6-2-project2-end_balance', '-400000'],
    ])

    const { detailTotal, diff } = useL6CrossSheet(responses)
    // 1200000 + (-400000) = 800000
    expect(detailTotal.value).toBe(800_000)
    expect(diff.value).toBe(0) // 勾稽一致
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 公式方向验证 — 负债类(begin+credit-debit) NOT 资产类
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 公式方向验证: 负债类 vs 资产类 (Req 2.5, 2.6)', () => {
  it('负债类: begin+credit-debit（L6使用此公式）', () => {
    const begin = 2_000_000
    const credit = 800_000  // 拨入（贷方增加）
    const debit = 300_000   // 结转（借方减少）

    const endBalance = calcLiabilityEndBalance(begin, credit, debit)
    // 负债类：2000000 + 800000 - 300000 = 2500000
    expect(endBalance).toBe(2_500_000)
  })

  it('资产类公式(begin+debit-credit)会得到错误结果', () => {
    const begin = 2_000_000
    const credit = 800_000  // 拨入
    const debit = 300_000   // 结转

    // 如果错误使用资产类公式: begin + debit - credit
    const wrongAssetFormula = begin + debit - credit
    // 2000000 + 300000 - 800000 = 1500000 (错！)

    const correctLiabilityResult = calcLiabilityEndBalance(begin, credit, debit)
    // 2000000 + 800000 - 300000 = 2500000 (对！)

    expect(correctLiabilityResult).not.toBe(wrongAssetFormula)
    expect(correctLiabilityResult).toBe(2_500_000)
    expect(wrongAssetFormula).toBe(1_500_000) // 差100万！
  })

  it('credit>debit → 期末增加（政府新拨入>结转使用）', () => {
    const begin = 1_000_000
    const credit = 500_000  // 新拨入
    const debit = 200_000   // 结转使用

    const end = calcLiabilityEndBalance(begin, credit, debit)
    expect(end).toBeGreaterThan(begin)
    expect(end).toBe(1_300_000)
  })

  it('debit>credit → 期末减少（结转使用>新拨入）', () => {
    const begin = 1_000_000
    const credit = 200_000  // 少量新拨
    const debit = 600_000   // 大量结转

    const end = calcLiabilityEndBalance(begin, credit, debit)
    expect(end).toBeLessThan(begin)
    expect(end).toBe(600_000)
  })

  it('完整流程: 审定数+方向校验+勾稽联合验证', () => {
    // Step 1: L6-1 审定表计算期末审定数
    const unadj = 3_000_000
    const aje = 200_000
    const rje = -50_000
    const audited = calcAuditedAmount(unadj, aje, rje)
    expect(audited).toBe(3_150_000) // 3000000+200000-50000

    // Step 2: L6-2 明细表按负债类方向计算各项期末
    const project1End = calcLiabilityEndBalance(1_500_000, 300_000, 100_000)
    // 1500000 + 300000 - 100000 = 1700000
    const project2End = calcLiabilityEndBalance(1_000_000, 200_000, 50_000)
    // 1000000 + 200000 - 50000 = 1150000
    const project3End = calcLiabilityEndBalance(200_000, 100_000, 0)
    // 200000 + 100000 - 0 = 300000

    const detailTotal = calcSubtotal([project1End, project2End, project3End])
    // 1700000 + 1150000 + 300000 = 3150000
    expect(detailTotal).toBe(3_150_000)

    // Step 3: 勾稽验证
    const result = validateAdjudicationVsDetail(audited, detailTotal)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })
})
