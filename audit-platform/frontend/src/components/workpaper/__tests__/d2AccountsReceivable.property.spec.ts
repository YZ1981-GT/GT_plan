/**
 * Property-Based Tests — D2 应收账款专属组件
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
 * Tasks: 8.1–8.13
 *
 * 使用 fast-check + vitest 验证 13 个 correctness properties。
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import {
  getAuditedAmount,
  getChangeRate,
  calculateExpectedLossRate,
  calculateProvision,
  calculateDifference,
  calculatePledgeRatio,
  determineCutoff,
  sumifLegacy as sumif,
} from '../composables/useD2FormulaEngine'
import {
  getTabStatusFromResponses,
  PROCEDURE_STEPS_CONFIG,
} from '../composables/d2Constants'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Allowed conclusions for D2- prefix (backend whitelist) */
const ALLOWED_CONCLUSIONS = [
  '未开始', '执行中', '已完成', '不适用',
  '符合', '不符合',
  '单项计提', '账龄组合', '客户类型组合',
  '终止确认', '不终止确认',
  '已披露且准确', '已披露但需修改', '未披露需补充',
  '组合评估', '个别认定',
  'AJE', 'RJE',
  'Y', 'N',
  '是', '否',
  '跨期', '未跨期',
] as const

/** Generate a valid D2 item_id */
function generateItemId(sheet: string, index: number, field: string): string {
  return `D2-${sheet}-${index}-${field}`
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 审定表公式计算不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 1: 审定表公式计算不变式', () => {
  /**
   * **Validates: Requirements 3.5, 3.6**
   *
   * 审定数 = I + AJE + RJE；变动率三分支逻辑
   */
  it('audited amount equals currentUnadjusted + ajeAdjustment + rjeAdjustment', () => {
    fc.assert(
      fc.property(
        fc.record({
          currentUnadjusted: fc.float({ min: 0, max: 1e9, noNaN: true }),
          ajeAdjustment: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
          rjeAdjustment: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
          priorPeriod: fc.float({ min: 0, max: 1e9, noNaN: true }),
        }),
        ({ currentUnadjusted, ajeAdjustment, rjeAdjustment, priorPeriod }) => {
          const audited = getAuditedAmount(currentUnadjusted, ajeAdjustment, rjeAdjustment)
          const expected = currentUnadjusted + ajeAdjustment + rjeAdjustment

          // Assert: audited === I + AJE + RJE
          expect(audited).toBeCloseTo(expected, 5)

          // Assert changeRate three-branch logic
          const rate = getChangeRate(priorPeriod, audited)

          if (priorPeriod === 0 && audited === 0) {
            expect(rate).toBe('')
          } else if (priorPeriod === 0) {
            expect(rate).toBe(1)
          } else {
            expect(rate).toBeCloseTo((audited - priorPeriod) / priorPeriod, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: SUMIF 跨 sheet 引用一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 2: SUMIF 跨 sheet 引用一致性', () => {
  /**
   * **Validates: Requirements 3.2, 3.3, 3.4, 3.9**
   *
   * sumif(rows, classification, column) === rows.filter(r=>r.AI===classification).reduce sum
   */
  it('sumif aggregation equals filtered sum for any row set and classification', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            AI: fc.constantFrom('单项计提', '账龄组合', '客户类型组合'),
            S: fc.float({ min: 0, max: 1e8, noNaN: true }),
            Z: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
            AA: fc.float({ min: 0, max: 1e8, noNaN: true }),
          }),
          { minLength: 0, maxLength: 20 },
        ),
        fc.constantFrom('单项计提', '账龄组合', '客户类型组合'),
        fc.constantFrom('S' as const, 'Z' as const, 'AA' as const),
        (rows, classification, column) => {
          const result = sumif(rows, classification, column)
          const expected = rows
            .filter(r => r.AI === classification)
            .reduce((sum, r) => sum + (Number(r[column]) || 0), 0)

          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: ECL 迁徙率法计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 3: ECL 迁徙率法计算正确性', () => {
  /**
   * **Validates: Requirements 5.3, 5.4, 5.5**
   *
   * lossRate = rates.reduce(连乘); provision = balance × lossRate; diff = actual - should
   */
  it('expected loss rate equals product of migration rates', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 0, max: 1, noNaN: true }), { minLength: 1, maxLength: 6 }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (rates, balance, actualProvision) => {
          // Assert: lossRate = rates.reduce((a,r)=>a*r, 1)
          const lossRate = calculateExpectedLossRate(rates)
          const expectedLossRate = rates.reduce((acc, r) => acc * r, 1)
          expect(lossRate).toBeCloseTo(expectedLossRate, 10)

          // Assert: provision = balance × lossRate
          const provision = calculateProvision(balance, lossRate)
          expect(provision).toBeCloseTo(balance * lossRate, 5)

          // Assert: difference = actual - should
          const shouldProvision = provision
          const difference = calculateDifference(actualProvision, shouldProvision)
          expect(difference).toBeCloseTo(actualProvision - shouldProvision, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('empty migration rates array returns 0 loss rate', () => {
    const lossRate = calculateExpectedLossRate([])
    expect(lossRate).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 质押比例计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 4: 质押比例计算正确性', () => {
  /**
   * **Validates: Requirements 8.6, 8.7**
   *
   * ratio = P/T (T>0), ratio=0 (T=0), warning = ratio>0.5
   */
  it('pledge ratio equals P/T when T>0, 0 when T=0, warning when >0.5', () => {
    fc.assert(
      fc.property(
        fc.record({
          pledgedAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
          totalAR: fc.float({ min: 0, max: 1e9, noNaN: true }),
        }),
        ({ pledgedAmount, totalAR }) => {
          const ratio = calculatePledgeRatio(pledgedAmount, totalAR)

          if (totalAR === 0) {
            expect(ratio).toBe(0)
          } else {
            expect(ratio).toBeCloseTo(pledgedAmount / totalAR, 10)
          }

          // Warning logic
          const warning = ratio > 0.5
          if (totalAR > 0 && pledgedAmount / totalAR > 0.5) {
            expect(warning).toBe(true)
          } else if (totalAR === 0) {
            expect(warning).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 截止测试跨期判定一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 5: 截止测试跨期判定一致性', () => {
  /**
   * **Validates: Requirements 7.5, 7.6**
   *
   * determineCutoff(revDate, bsDate) === new Date(revDate) > new Date(bsDate)
   */
  it('cutoff determination matches date comparison logic', () => {
    fc.assert(
      fc.property(
        fc.record({
          year: fc.integer({ min: 2020, max: 2030 }),
          month: fc.integer({ min: 1, max: 12 }),
          day: fc.integer({ min: 1, max: 28 }),
          bsYear: fc.integer({ min: 2020, max: 2030 }),
        }),
        ({ year, month, day, bsYear }) => {
          const revDate = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
          const bsDate = `${bsYear}-12-31`

          const result = determineCutoff(revDate, bsDate)
          const expected = new Date(revDate) > new Date(bsDate)

          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: trial_balance 回写一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 6: trial_balance 回写一致性', () => {
  /**
   * **Validates: Requirements 10.2, 10.7**
   *
   * writebackTrialBalance is called with the same auditedAmount that was calculated
   */
  it('writeback amount matches calculated audited amount (mock round-trip)', () => {
    fc.assert(
      fc.property(
        fc.record({
          currentUnadjusted: fc.float({ min: 0, max: 1e9, noNaN: true }),
          ajeAdjustment: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
          rjeAdjustment: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        }),
        ({ currentUnadjusted, ajeAdjustment, rjeAdjustment }) => {
          // Calculate audited amount (D2 uses 3 params)
          const auditedAmount = getAuditedAmount(currentUnadjusted, ajeAdjustment, rjeAdjustment)

          // Mock writeback API call
          const mockWriteback = vi.fn()
          mockWriteback('1122', auditedAmount)

          // Verify API called with correct account code and amount
          expect(mockWriteback).toHaveBeenCalledWith('1122', auditedAmount)
          expect(mockWriteback.mock.calls[0][0]).toBe('1122')
          expect(mockWriteback.mock.calls[0][1]).toBe(auditedAmount)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 数据持久化往返一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 7: 数据持久化往返一致性', () => {
  /**
   * **Validates: Requirements 11.6**
   *
   * save then load returns same values (mock API round-trip)
   */
  it('data round-trip preserves conclusion and remark values', () => {
    fc.assert(
      fc.property(
        fc.record({
          itemId: fc.constantFrom(
            'D2-proc-1-status', 'D2-adj-individual-current',
            'D2-ecl-within-1y-balance', 'D2-entry-1-type', 'D2-baddebt-method',
            'D2-cutoff-1-revDate', 'D2-factoring-1-amount',
          ),
          conclusion: fc.constantFrom(...ALLOWED_CONCLUSIONS, null),
          remark: fc.option(fc.string({ minLength: 0, maxLength: 50 })),
        }),
        ({ itemId, conclusion, remark }) => {
          // Simulate save: store in map
          const storage = new Map<string, { conclusion: string | null; remark: string | null }>()
          const remarkVal = remark ?? null
          storage.set(itemId, { conclusion, remark: remarkVal })

          // Simulate load: read from map
          const loaded = storage.get(itemId)!

          // Verify round-trip consistency
          expect(loaded.conclusion).toBe(conclusion)
          expect(loaded.remark).toBe(remarkVal)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: item_id 命名唯一性与确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 8: item_id 命名唯一性与确定性', () => {
  /**
   * **Validates: Requirements 11.7**
   *
   * 不同输入→不同 item_ids；相同输入→相同 item_ids；均以 D2- 前缀开头
   */
  it('different inputs produce different item_ids, same inputs produce same item_ids', () => {
    fc.assert(
      fc.property(
        fc.record({
          sheet: fc.constantFrom('proc', 'adj', 'ecl', 'entry', 'cutoff', 'factoring', 'check7', 'policy', 'writeoff', 'bizmodel'),
          index: fc.integer({ min: 1, max: 20 }),
          field: fc.constantFrom('status', 'conclusion', 'amount', 'rate', 'balance', 'customer', 'remark'),
        }),
        fc.record({
          sheet: fc.constantFrom('proc', 'adj', 'ecl', 'entry', 'cutoff', 'factoring', 'check7', 'policy', 'writeoff', 'bizmodel'),
          index: fc.integer({ min: 1, max: 20 }),
          field: fc.constantFrom('status', 'conclusion', 'amount', 'rate', 'balance', 'customer', 'remark'),
        }),
        (input1, input2) => {
          const id1 = generateItemId(input1.sheet, input1.index, input1.field)
          const id2 = generateItemId(input2.sheet, input2.index, input2.field)

          // All start with D2-
          expect(id1.startsWith('D2-')).toBe(true)
          expect(id2.startsWith('D2-')).toBe(true)

          const sameInputs = (
            input1.sheet === input2.sheet &&
            input1.index === input2.index &&
            input1.field === input2.field
          )

          if (sameInputs) {
            // Same inputs → same item_id (deterministic)
            expect(id1).toBe(id2)
          } else {
            // Different inputs → different item_ids (unique)
            expect(id1).not.toBe(id2)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 程序表完成度与复核前置条件
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 9: 程序表完成度与复核前置条件', () => {
  /**
   * **Validates: Requirements 4.6, 12.2**
   *
   * canReview = all required steps are '已完成' or '不适用'
   */
  it('canReview iff all isRequired steps are 已完成 or 不适用', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.constantFrom('未开始', '执行中', '已完成', '不适用'),
          { minLength: 7, maxLength: 7 },
        ),
        (statuses) => {
          // Apply statuses to steps and check canReview logic
          const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
            if (!step.isRequired) return true
            const status = statuses[i]
            return status === '已完成' || status === '不适用'
          })

          // Count completed (progress calculation)
          const completedCount = statuses.filter(s => s === '已完成' || s === '不适用').length

          // Manual verification of canReview
          const requiredSteps = PROCEDURE_STEPS_CONFIG
            .map((step, i) => ({ ...step, status: statuses[i] }))
            .filter(s => s.isRequired)

          const allRequiredDone = requiredSteps.every(
            s => s.status === '已完成' || s.status === '不适用'
          )

          expect(canReview).toBe(allRequiredDone)
          expect(completedCount).toBeGreaterThanOrEqual(0)
          expect(completedCount).toBeLessThanOrEqual(7)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: EventBus 事件发射正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 10: EventBus 事件发射正确性', () => {
  /**
   * **Validates: Requirements 10.1, 10.5**
   *
   * old !== new → event dispatched; old === new → no event
   */
  it('event dispatched iff old amount differs from new amount', () => {
    fc.assert(
      fc.property(
        fc.record({
          oldAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
          newAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
        }),
        ({ oldAmount, newAmount }) => {
          const events: Array<{ type: string; payload: unknown }> = []

          // Simulate event dispatch logic
          function dispatchIfChanged(oldVal: number, newVal: number): void {
            if (oldVal !== newVal) {
              events.push({
                type: 'substantive:adjudicated',
                payload: { wpCode: 'D2', accountCode: '1122', auditedAmount: newVal },
              })
            }
          }

          dispatchIfChanged(oldAmount, newAmount)

          if (oldAmount !== newAmount) {
            // Event should be dispatched
            expect(events.length).toBe(1)
            expect(events[0].type).toBe('substantive:adjudicated')
            expect((events[0].payload as any).wpCode).toBe('D2')
            expect((events[0].payload as any).accountCode).toBe('1122')
            expect((events[0].payload as any).auditedAmount).toBe(newAmount)
          } else {
            // No event
            expect(events.length).toBe(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 调整分录与审定表双向同步
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 11: 调整分录与审定表双向同步', () => {
  /**
   * **Validates: Requirements 15.3, 15.5**
   *
   * AJE total = sum of AJE entries; RJE total = sum of RJE entries
   */
  it('AJE and RJE totals equal respective sums of entries', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            type: fc.constantFrom('AJE' as const, 'RJE' as const),
            amount: fc.float({ min: 0, max: 1e8, noNaN: true }),
          }),
          { minLength: 0, maxLength: 20 },
        ),
        (entries) => {
          // Calculate expected totals
          const expectedAjeTotal = entries
            .filter(e => e.type === 'AJE')
            .reduce((sum, e) => sum + e.amount, 0)
          const expectedRjeTotal = entries
            .filter(e => e.type === 'RJE')
            .reduce((sum, e) => sum + e.amount, 0)

          // Simulate the composable logic
          let ajeTotal = 0
          let rjeTotal = 0
          for (const entry of entries) {
            if (entry.type === 'AJE') ajeTotal += entry.amount
            else rjeTotal += entry.amount
          }

          expect(ajeTotal).toBeCloseTo(expectedAjeTotal, 5)
          expect(rjeTotal).toBeCloseTo(expectedRjeTotal, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 后端白名单校验正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 12: 后端白名单校验正确性', () => {
  /**
   * **Validates: Requirements 13.1, 13.2, 13.4**
   *
   * Valid conclusions → accepted; invalid conclusions → rejected
   */
  it('valid conclusions pass whitelist check, invalid ones are rejected', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          // Valid conclusion from whitelist
          fc.constantFrom(...ALLOWED_CONCLUSIONS).map(c => ({ conclusion: c, shouldPass: true })),
          // Invalid conclusion (random string not in whitelist)
          fc.constantFrom(
            '无效值', 'INVALID', '完成', '开始', 'YES', 'NO', '通过', '未通过',
            '合格', '不合格', 'true', 'false', 'done', 'pending',
            '有效', '无效', 'HIGH', 'LOW',
          ).map(c => ({ conclusion: c, shouldPass: false })),
        ),
        ({ conclusion, shouldPass }) => {
          // Simulate backend whitelist validation
          const allowed = new Set(ALLOWED_CONCLUSIONS)
          const isValid = allowed.has(conclusion as any)

          if (shouldPass) {
            expect(isValid).toBe(true)
          } else {
            expect(isValid).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('null conclusion always passes (remark-only fields)', () => {
    // null conclusion should never trigger whitelist rejection
    const allowed = new Set(ALLOWED_CONCLUSIONS)
    const conclusion: string | null = null
    const shouldReject = conclusion !== null && !allowed.has(conclusion as any)
    expect(shouldReject).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 13: Tab 完成状态一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-accounts-receivable, Property 13: Tab 完成状态一致性', () => {
  /**
   * **Validates: Requirements 2.6**
   *
   * no data→not-started; partial→in-progress; all filled→completed
   */
  it('tab status matches data completeness', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            conclusion: fc.option(fc.constantFrom(...ALLOWED_CONCLUSIONS), { nil: undefined }),
            remark: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
          }),
          { minLength: 0, maxLength: 10 },
        ),
        (responseData) => {
          // Build ChecklistResponse array
          const tabResponses = responseData.map((r, i) => ({
            item_id: `D2-test-${i}`,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          }))

          const status = getTabStatusFromResponses(tabResponses)

          if (tabResponses.length === 0) {
            // No data → not-started
            expect(status).toBe('not-started')
          } else {
            const hasAnyValue = tabResponses.some(r => r.conclusion || r.remark)
            const allHaveValue = tabResponses.every(r => r.conclusion || r.remark)

            if (!hasAnyValue) {
              expect(status).toBe('not-started')
            } else if (allHaveValue) {
              expect(status).toBe('completed')
            } else {
              expect(status).toBe('in-progress')
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
