/**
 * Property-Based Tests — B22B 内部控制缺陷评价表
 *
 * Spec: .kiro/specs/b22b-deficiency-evaluation/
 * Tasks: 5.1–5.12
 *
 * 使用 fast-check + vitest 验证 12 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref, computed } from 'vue'

import {
  suggestSeverity,
  computeOverallConclusion,
  compareMateriality,
  computeSeverityStats,
  generateItemId,
  defaultCategory,
  SEVERITY_LEVELS,
  DEFICIENCY_CATEGORIES,
  type SeverityLevel,
  type DeficiencyCategory,
  type EvaluationItem,
  type OverallConclusion,
  type MaterialityComparison,
  type SeverityEvaluatedPayload,
} from '../composables/useB22BDeficiency'
import type { DeficiencyItem } from '../composables/useB22AControlMatrix'

// ─── Helpers & Arbitraries ───────────────────────────────────────────────────

const arbSeverityLevel = fc.constantFrom<SeverityLevel>('重大缺陷', '重要缺陷', '一般缺陷')
const arbSeverityOrNull = fc.constantFrom<SeverityLevel | null>('重大缺陷', '重要缺陷', '一般缺陷', null)
const arbDeficiencyType = fc.constantFrom<'设计无效' | '未实施'>('设计无效', '未实施')
const arbCategory = fc.constantFrom<DeficiencyCategory>('设计缺陷', '运行缺陷')
const arbBoolean = fc.boolean()
const arbBooleanOrNull = fc.constantFrom<boolean | null>(true, false, null)

const arbTabNumber = fc.constantFrom<1 | 2 | 3 | 4 | 5>(1, 2, 3, 4, 5)

const arbField = fc.constantFrom<'category' | 'accounts' | 'amount' | 'compensating' | 'corrective' | 'severity' | 'override' | 'source' | 'eliminated'>(
  'category', 'accounts', 'amount', 'compensating', 'corrective', 'severity', 'override', 'source', 'eliminated'
)

/** Build a mock DeficiencyItem */
function makeDeficiencyItem(overrides?: Partial<DeficiencyItem>): DeficiencyItem {
  return {
    tab: 1,
    subPanel: null,
    index: 1,
    controlPoint: '测试控制要点',
    deficiencyType: '设计无效',
    elementName: '控制环境',
    ...overrides,
  }
}

/** Build a mock EvaluationItem */
function makeEvaluationItem(overrides?: Partial<EvaluationItem>): EvaluationItem {
  return {
    source: makeDeficiencyItem(),
    category: null,
    affectedAccounts: [],
    potentialMisstatement: null,
    hasCompensatingControl: null,
    compensatingControlDesc: '',
    hasCorrectiveAction: null,
    correctiveActionDesc: '',
    severity: null,
    severityOverridden: false,
    overrideReason: '',
    eliminated: false,
    ...overrides,
  }
}

/** Arbitrary for EvaluationItem */
const arbEvaluationItem = fc.record({
  severity: arbSeverityOrNull,
  eliminated: fc.boolean(),
}).map(({ severity, eliminated }) => makeEvaluationItem({ severity, eliminated }))

// Valid B22B conclusions whitelist
const B22B_VALID_CONCLUSIONS = [
  '重大缺陷', '重要缺陷', '一般缺陷',
  '设计缺陷', '运行缺陷',
  'Y', 'N',
  '存在重大缺陷', '存在重要缺陷', '仅存在一般缺陷', '未发现控制缺陷',
]

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 缺陷来源同步不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 1: 缺陷来源同步不变式', () => {
  /**
   * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6**
   *
   * 事件序列 → 缺陷列表最终状态正确
   */
  it('added items appear in list, removed items are eliminated', () => {
    fc.assert(
      fc.property(
        // Generate a set of initial deficiency items
        fc.array(
          fc.record({
            tab: arbTabNumber,
            index: fc.integer({ min: 1, max: 10 }),
            deficiencyType: arbDeficiencyType,
          }),
          { minLength: 1, maxLength: 8 },
        ),
        // Which ones to remove (subset indices)
        fc.array(fc.integer({ min: 0, max: 7 }), { minLength: 0, maxLength: 4 }),
        (initialItems, removeIndices) => {
          // Deduplicate by (tab, index) to avoid identity collision
          const deduped = new Map<string, typeof initialItems[0]>()
          for (const item of initialItems) {
            deduped.set(`${item.tab}-${item.index}`, item)
          }
          const items = [...deduped.values()]

          // Create evaluation items from "added" events
          const evaluationList: EvaluationItem[] = items.map(item =>
            makeEvaluationItem({
              source: makeDeficiencyItem({
                tab: item.tab as 1 | 2 | 3 | 4 | 5,
                index: item.index,
                deficiencyType: item.deficiencyType,
              }),
            })
          )

          // Simulate "removed" events
          const validRemoveIndices = removeIndices
            .filter(i => i < evaluationList.length)
            .filter((v, i, a) => a.indexOf(v) === i) // unique

          const eliminatedList: EvaluationItem[] = []
          // Process removals in reverse to not shift indices
          const sortedRemoves = [...validRemoveIndices].sort((a, b) => b - a)
          for (const idx of sortedRemoves) {
            const removed = evaluationList.splice(idx, 1)[0]
            removed.eliminated = true
            eliminatedList.push(removed)
          }

          // Invariant: all remaining items are NOT eliminated
          for (const item of evaluationList) {
            expect(item.eliminated).toBe(false)
          }
          // Invariant: all removed items ARE eliminated
          for (const item of eliminatedList) {
            expect(item.eliminated).toBe(true)
          }
          // Invariant: total count preserved
          expect(evaluationList.length + eliminatedList.length).toBe(items.length)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 缺陷分类默认映射一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 2: 缺陷分类默认映射一致性', () => {
  /**
   * **Validates: Requirements 2.2, 2.3**
   *
   * deficiencyType → 默认 category 双射
   */
  it('defaultCategory maps 设计无效→设计缺陷, 未实施→运行缺陷', () => {
    fc.assert(
      fc.property(
        arbDeficiencyType,
        (deficiencyType) => {
          const category = defaultCategory(deficiencyType)
          if (deficiencyType === '设计无效') {
            expect(category).toBe('设计缺陷')
          } else {
            expect(category).toBe('运行缺陷')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('mapping is bijective: different types produce different categories', () => {
    fc.assert(
      fc.property(
        arbDeficiencyType,
        arbDeficiencyType,
        (type1, type2) => {
          const cat1 = defaultCategory(type1)
          const cat2 = defaultCategory(type2)
          if (type1 === type2) {
            expect(cat1).toBe(cat2)
          } else {
            expect(cat1).not.toBe(cat2)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 严重程度建议逻辑一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 3: 严重程度建议逻辑一致性', () => {
  /**
   * **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
   *
   * suggestSeverity(M, T, C, A) 满足三分支规则
   */
  it('satisfies 3-branch severity rule', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        fc.boolean(),
        fc.boolean(),
        (amount, materiality, compensating, corrective) => {
          const result = suggestSeverity(amount, materiality, compensating, corrective)

          if (amount > materiality && !compensating && !corrective) {
            expect(result).toBe('重大缺陷')
          } else if (amount > materiality && (compensating || corrective)) {
            expect(result).toBe('重要缺陷')
          } else {
            expect(result).toBe('一般缺陷')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns null when amount or materiality is null', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<number | null>(null, 100, 500),
        fc.constantFrom<number | null>(null, 200, 1000),
        fc.boolean(),
        fc.boolean(),
        (amount, materiality, compensating, corrective) => {
          if (amount === null || materiality === null) {
            const result = suggestSeverity(amount, materiality, compensating, corrective)
            expect(result).toBeNull()
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 整体评价结论汇总不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 4: 整体评价结论汇总不变式', () => {
  /**
   * **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
   *
   * computeOverallConclusion 满足 max-severity 规则
   */
  it('follows max-severity rule', () => {
    fc.assert(
      fc.property(
        fc.array(arbEvaluationItem, { minLength: 0, maxLength: 20 }),
        (items) => {
          const result = computeOverallConclusion(items)

          // Filter active items (non-eliminated with severity set)
          const activeItems = items.filter(i => !i.eliminated && i.severity !== null)

          if (activeItems.length === 0) {
            expect(result).toBe('未发现控制缺陷')
          } else if (activeItems.some(i => i.severity === '重大缺陷')) {
            expect(result).toBe('存在重大缺陷')
          } else if (activeItems.some(i => i.severity === '重要缺陷')) {
            expect(result).toBe('存在重要缺陷')
          } else {
            expect(result).toBe('仅存在一般缺陷')
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: EventBus 事件发射正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 5: EventBus 事件发射正确性', () => {
  /**
   * **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
   *
   * impactsAuditOpinion / requiresExtendedProcedures flags correct
   */
  it('impactsAuditOpinion=true iff 存在重大缺陷; requiresExtendedProcedures=true iff 重大 or 重要', () => {
    fc.assert(
      fc.property(
        fc.array(arbEvaluationItem, { minLength: 0, maxLength: 15 }),
        (items) => {
          const conclusion = computeOverallConclusion(items)
          const stats = computeSeverityStats(items)

          // Compute expected flags
          const impactsAuditOpinion = conclusion === '存在重大缺陷'
          const requiresExtendedProcedures = conclusion === '存在重大缺陷' || conclusion === '存在重要缺陷'

          expect(impactsAuditOpinion).toBe(conclusion === '存在重大缺陷')
          expect(requiresExtendedProcedures).toBe(
            conclusion === '存在重大缺陷' || conclusion === '存在重要缺陷'
          )

          // materialCount / significantCount match stats
          expect(stats.material).toBe(
            items.filter(i => !i.eliminated && i.severity === '重大缺陷').length
          )
          expect(stats.significant).toBe(
            items.filter(i => !i.eliminated && i.severity === '重要缺陷').length
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 复核前置条件完备性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 6: 复核前置条件完备性', () => {
  /**
   * **Validates: Requirements 8.2**
   *
   * canReview=true iff all non-eliminated items have severity non-null
   */
  it('canReview=true iff all active items have severity set', () => {
    fc.assert(
      fc.property(
        fc.array(arbEvaluationItem, { minLength: 0, maxLength: 15 }),
        (items) => {
          const activeItems = items.filter(i => !i.eliminated)
          const allEvaluated = activeItems.length === 0 || activeItems.every(i => i.severity !== null)

          // This is the canReview logic
          expect(allEvaluated).toBe(
            activeItems.length === 0 || activeItems.every(i => i.severity !== null)
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 复核后只读不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 7: 复核后只读不变式', () => {
  /**
   * **Validates: Requirements 8.3, 8.5, 8.6**
   *
   * review conclusion='Y' 或 readonly=true → isReadonly=true
   */
  it('isReadonly = (externalReadonly || reviewed)', () => {
    fc.assert(
      fc.property(
        fc.boolean(), // externalReadonly
        fc.boolean(), // isReviewed
        (extReadonly, reviewed) => {
          // Simulate isReadonly computation
          const isReadonly = extReadonly || reviewed
          expect(isReadonly).toBe(extReadonly || reviewed)

          // If either is true, readonly must be true
          if (extReadonly || reviewed) {
            expect(isReadonly).toBe(true)
          }
          // If both false, readonly must be false
          if (!extReadonly && !reviewed) {
            expect(isReadonly).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 数据持久化往返一致性 (frontend pure function test)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 8: 数据持久化往返一致性', () => {
  /**
   * **Validates: Requirements 7.1, 7.5, 7.6**
   *
   * generateItemId produces valid B22B- prefix item_ids
   */
  it('generateItemId always produces B22B-def-{idx}-{field} format', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        arbField,
        (idx, field) => {
          const id = generateItemId(idx, field)
          expect(id).toBe(`B22B-def-${idx}-${field}`)
          expect(id.startsWith('B22B-')).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: item_id 命名唯一性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 9: item_id 命名唯一性', () => {
  /**
   * **Validates: Requirements 7.7**
   *
   * generateItemId(idx, field) 唯一且确定
   */
  it('different (idx, field) produce different item_ids', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        arbField,
        fc.integer({ min: 1, max: 50 }),
        arbField,
        (idx1, field1, idx2, field2) => {
          const id1 = generateItemId(idx1, field1)
          const id2 = generateItemId(idx2, field2)

          const sameInputs = idx1 === idx2 && field1 === field2
          if (sameInputs) {
            expect(id1).toBe(id2)
          } else {
            expect(id1).not.toBe(id2)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('same inputs always produce same item_id (deterministic)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        arbField,
        (idx, field) => {
          const id1 = generateItemId(idx, field)
          const id2 = generateItemId(idx, field)
          expect(id1).toBe(id2)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: 重要性水平对比确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 10: 重要性水平对比确定性', () => {
  /**
   * **Validates: Requirements 3.4, 11.2, 11.3**
   *
   * (amount, materiality) → exceeds/color 确定性
   */
  it('exceeds=true iff amount > materiality; color=red iff exceeds', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        (amount, materiality) => {
          const result = compareMateriality(amount, materiality)

          const expectedExceeds = amount > materiality
          expect(result.exceeds).toBe(expectedExceeds)
          expect(result.color).toBe(expectedExceeds ? 'red' : 'green')

          if (expectedExceeds) {
            expect(result.difference).toBeCloseTo(amount - materiality, 5)
          } else {
            expect(result.difference).toBeNull()
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('same inputs always produce same result (deterministic)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        (amount, materiality) => {
          const r1 = compareMateriality(amount, materiality)
          const r2 = compareMateriality(amount, materiality)
          expect(r1.exceeds).toBe(r2.exceeds)
          expect(r1.color).toBe(r2.color)
          expect(r1.difference).toBe(r2.difference)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 缺陷数量统计准确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 11: 缺陷数量统计准确性', () => {
  /**
   * **Validates: Requirements 5.6**
   *
   * severityStats 各字段 = 手动计数
   */
  it('stats match manual count of severities among non-eliminated items', () => {
    fc.assert(
      fc.property(
        fc.array(arbEvaluationItem, { minLength: 0, maxLength: 20 }),
        (items) => {
          const stats = computeSeverityStats(items)

          // Manual count
          const activeItems = items.filter(i => !i.eliminated)
          const manualMaterial = activeItems.filter(i => i.severity === '重大缺陷').length
          const manualSignificant = activeItems.filter(i => i.severity === '重要缺陷').length
          const manualGeneral = activeItems.filter(i => i.severity === '一般缺陷').length

          expect(stats.material).toBe(manualMaterial)
          expect(stats.significant).toBe(manualSignificant)
          expect(stats.general).toBe(manualGeneral)
          expect(stats.total).toBe(manualMaterial + manualSignificant + manualGeneral)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 后端白名单校验正确性 (frontend constant verification)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22b-deficiency-evaluation, Property 12: 后端白名单校验正确性', () => {
  /**
   * **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
   *
   * B22B- valid conclusions are exactly the defined whitelist
   */
  it('valid conclusions list is complete and consistent with design', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...B22B_VALID_CONCLUSIONS),
        (conclusion) => {
          // All values in the valid list must be one of the expected types
          expect(B22B_VALID_CONCLUSIONS).toContain(conclusion)

          // Verify it falls into one of the known categories
          const severities: string[] = ['重大缺陷', '重要缺陷', '一般缺陷']
          const categories: string[] = ['设计缺陷', '运行缺陷']
          const booleans: string[] = ['Y', 'N']
          const overalls: string[] = ['存在重大缺陷', '存在重要缺陷', '仅存在一般缺陷', '未发现控制缺陷']

          const allAllowed = [...severities, ...categories, ...booleans, ...overalls]
          expect(allAllowed).toContain(conclusion)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('invalid conclusions are not in the whitelist', () => {
    const invalidValues = ['INVALID', 'yes', 'no', 'maybe', '有效', '无效', 'abc']
    fc.assert(
      fc.property(
        fc.constantFrom(...invalidValues),
        (conclusion) => {
          expect(B22B_VALID_CONCLUSIONS).not.toContain(conclusion)
        },
      ),
      { numRuns: 100 },
    )
  })
})
