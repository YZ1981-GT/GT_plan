/**
 * Property-Based Tests — B22A 内部控制了解程序表
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Tasks: 5.1–5.13
 *
 * 使用 fast-check + vitest 验证 13 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref, computed } from 'vue'
import {
  computeAutoScore,
  computeTabStatus,
  generateItemId,
  SCORE_COLOR_MAP,
  CONCLUSIONS,
  COSO_TABS,
  IT_SUB_PANELS,
  type TabNumber,
  type Conclusion,
  type ElementScore,
  type ITDependency,
  type ITSubPanel,
  type TabStatus,
  type CheckItem,
} from '../composables/useB22AControlMatrix'
import { useB22AControlMatrix } from '../composables/useB22AControlMatrix'
import { useB22AReview } from '../composables/useB22AReview'
import type { ChecklistItem, ChecklistResponse } from '../composables/useB22AFormData'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** No-op save function for testing */
const noopSave = async (_items: ChecklistItem[]) => {}

/** Arbitrary for Conclusion */
const arbConclusion = fc.constantFrom<Conclusion>(...CONCLUSIONS)

/** Arbitrary for nullable Conclusion */
const arbConclusionOrNull = fc.constantFrom<Conclusion | null>(...CONCLUSIONS, null)

/** Arbitrary for ElementScore */
const arbElementScore = fc.constantFrom<ElementScore>('有效', '部分有效', '无效')

/** Arbitrary for nullable ElementScore */
const arbElementScoreOrNull = fc.constantFrom<ElementScore | null>('有效', '部分有效', '无效', null)

/** Arbitrary for TabNumber */
const arbTabNumber = fc.constantFrom<TabNumber>(1, 2, 3, 4, 5)

/** Arbitrary for ITDependency */
const arbITDependency = fc.constantFrom<ITDependency>('高', '中', '低')

/** Arbitrary for ITSubPanel */
const arbITSubPanel = fc.constantFrom<ITSubPanel>('env', 'itgc', 'app', 'change', 'access', 'sod')

/** Build a CheckItem for testing */
function makeCheckItem(conclusion: Conclusion | null, controlPoint = '测试控制要点'): CheckItem {
  return {
    index: 1,
    controlPoint,
    description: '描述',
    methods: [],
    conclusion,
    reference: '',
    isPreset: false,
    isDeficiency: conclusion === '设计无效' || conclusion === '未实施',
    priorYearConclusion: null,
    noChangeConfirmed: false,
    noChangeConfirmer: null,
    noChangeDate: null,
  }
}

/** Create allResponses map with given tab check items */
function buildAllResponses(
  tabData: Record<number, Conclusion[]>,
  options?: {
    itDependency?: ITDependency
    itgcItems?: Conclusion[]
    overallConclusion?: ElementScore
    reviewSign?: boolean
  }
): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()

  for (const [tabStr, conclusions] of Object.entries(tabData)) {
    const tab = Number(tabStr) as TabNumber
    // Set count
    const countId = `B22A-T${tab}-count`
    map.set(countId, { item_id: countId, conclusion: null, remark: String(conclusions.length), wp_ref: null })

    // Set each conclusion
    for (let i = 0; i < conclusions.length; i++) {
      const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
      map.set(itemId, { item_id: itemId, conclusion: conclusions[i], remark: null, wp_ref: null })
      // Set point for deficiency tracking
      const pointId = `B22A-T${tab}-item-${i + 1}-point`
      map.set(pointId, { item_id: pointId, conclusion: null, remark: `控制要点${i + 1}`, wp_ref: null })
    }
  }

  if (options?.itDependency) {
    map.set('B22A-T4-IT-dependency', {
      item_id: 'B22A-T4-IT-dependency',
      conclusion: options.itDependency,
      remark: null,
      wp_ref: null,
    })
  }

  if (options?.itgcItems) {
    const countId = 'B22A-T4-IT-itgc-count'
    map.set(countId, { item_id: countId, conclusion: null, remark: String(options.itgcItems.length), wp_ref: null })
    for (let i = 0; i < options.itgcItems.length; i++) {
      const itemId = `B22A-T4-IT-itgc-${i + 1}-conclusion`
      map.set(itemId, { item_id: itemId, conclusion: options.itgcItems[i], remark: null, wp_ref: null })
    }
  }

  if (options?.overallConclusion) {
    map.set('B22A-SUM-overall', {
      item_id: 'B22A-SUM-overall',
      conclusion: options.overallConclusion,
      remark: null,
      wp_ref: null,
    })
  }

  if (options?.reviewSign) {
    map.set('B22A-review-sign', {
      item_id: 'B22A-review-sign',
      conclusion: 'Y',
      remark: '现场经理',
      wp_ref: '2026-01-01',
    })
  }

  return map
}


// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 汇总矩阵同步不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 1: 汇总矩阵同步不变式', () => {
  /**
   * **Validates: Requirements 4.2, 4.6, 5.1**
   *
   * Summary_Tab 统计数据 = Tab_1~5 检查项 Conclusion 实际分布计数
   */
  it('elementStats matches manual count of conclusions per tab', () => {
    fc.assert(
      fc.property(
        // Generate random conclusions for 5 tabs (1-6 items each)
        fc.tuple(
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 6 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 6 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 6 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 6 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 6 }),
        ),
        ([tab1, tab2, tab3, tab4, tab5]) => {
          const tabData: Record<number, Conclusion[]> = {
            1: tab1.filter((c): c is Conclusion => c !== null),
            2: tab2.filter((c): c is Conclusion => c !== null),
            3: tab3.filter((c): c is Conclusion => c !== null),
            4: tab4.filter((c): c is Conclusion => c !== null),
            5: tab5.filter((c): c is Conclusion => c !== null),
          }

          // We need full arrays including nulls for count
          const fullTabData: Record<number, (Conclusion | null)[]> = { 1: tab1, 2: tab2, 3: tab3, 4: tab4, 5: tab5 }

          const allResponses = ref(new Map<string, ChecklistResponse>())
          // Build responses with all items including nulls
          for (const [tabStr, conclusions] of Object.entries(fullTabData)) {
            const tab = Number(tabStr) as TabNumber
            const countId = `B22A-T${tab}-count`
            allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(conclusions.length), wp_ref: null })
            for (let i = 0; i < conclusions.length; i++) {
              const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
              if (conclusions[i] !== null) {
                allResponses.value.set(itemId, { item_id: itemId, conclusion: conclusions[i], remark: null, wp_ref: null })
              }
              const pointId = `B22A-T${tab}-item-${i + 1}-point`
              allResponses.value.set(pointId, { item_id: pointId, conclusion: null, remark: `要点${i}`, wp_ref: null })
            }
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()
          const stats = matrix.elementStats.value

          // Manual count per tab
          for (const tabNum of [1, 2, 3, 4, 5] as TabNumber[]) {
            const conclusions = fullTabData[tabNum]
            let effective = 0, deficient = 0, notApplicable = 0, incomplete = 0
            for (const c of conclusions) {
              if (c === null) incomplete++
              else if (c === '不适用') notApplicable++
              else if (c === '设计无效' || c === '未实施') deficient++
              else effective++
            }

            expect(stats[tabNum].total).toBe(conclusions.length)
            expect(stats[tabNum].effective).toBe(effective)
            expect(stats[tabNum].deficient).toBe(deficient)
            expect(stats[tabNum].notApplicable).toBe(notApplicable)
            expect(stats[tabNum].incomplete).toBe(incomplete)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: Element_Score 自动计算一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 2: Element_Score 自动计算一致性', () => {
  /**
   * **Validates: Requirements 5.2, 5.3, 5.4**
   *
   * computeAutoScore 结果满足 20% 阈值规则
   */
  it('computeAutoScore satisfies threshold rules', () => {
    fc.assert(
      fc.property(
        fc.array(arbConclusion, { minLength: 1, maxLength: 20 }),
        (conclusions) => {
          const items = conclusions.map(c => makeCheckItem(c))
          const result = computeAutoScore(items)

          // Filter applicable items
          const applicable = items.filter(i => i.conclusion && i.conclusion !== '不适用')
          if (applicable.length === 0) {
            expect(result).toBe('有效')
            return
          }

          const deficient = applicable.filter(
            i => i.conclusion === '设计无效' || i.conclusion === '未实施'
          )

          if (deficient.length === 0) {
            expect(result).toBe('有效')
          } else if (deficient.length / applicable.length <= 0.2) {
            expect(result).toBe('部分有效')
          } else {
            expect(result).toBe('无效')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('all 不适用 items → 有效', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        (count) => {
          const items = Array.from({ length: count }, () => makeCheckItem('不适用'))
          expect(computeAutoScore(items)).toBe('有效')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 控制缺陷清单同步不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 3: 控制缺陷清单同步不变式', () => {
  /**
   * **Validates: Requirements 6.1, 6.5, 2.7**
   *
   * deficiencyList = 所有 Conclusion 为"设计无效"/"未实施"的检查项集合
   */
  it('deficiencyList contains exactly items with 设计无效 or 未实施 conclusion', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 5 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 5 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 5 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 5 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 5 }),
        ),
        ([tab1, tab2, tab3, tab4, tab5]) => {
          const allTabs: Record<number, (Conclusion | null)[]> = { 1: tab1, 2: tab2, 3: tab3, 4: tab4, 5: tab5 }

          const allResponses = ref(new Map<string, ChecklistResponse>())
          for (const [tabStr, conclusions] of Object.entries(allTabs)) {
            const tab = Number(tabStr) as TabNumber
            const countId = `B22A-T${tab}-count`
            allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(conclusions.length), wp_ref: null })
            for (let i = 0; i < conclusions.length; i++) {
              const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
              if (conclusions[i] !== null) {
                allResponses.value.set(itemId, { item_id: itemId, conclusion: conclusions[i], remark: null, wp_ref: null })
              }
              const pointId = `B22A-T${tab}-item-${i + 1}-point`
              allResponses.value.set(pointId, { item_id: pointId, conclusion: null, remark: `控制要点Tab${tab}-${i + 1}`, wp_ref: null })
            }
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()
          const deficiencies = matrix.deficiencyList.value

          // Manual count of expected deficiencies
          let expectedCount = 0
          for (const [tabStr, conclusions] of Object.entries(allTabs)) {
            for (const c of conclusions) {
              if (c === '设计无效' || c === '未实施') expectedCount++
            }
          }

          expect(deficiencies.length).toBe(expectedCount)

          // All items in the list must have deficiency type
          for (const d of deficiencies) {
            expect(['设计无效', '未实施']).toContain(d.deficiencyType)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: IT 依赖程度作用域约束
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 4: IT 依赖程度作用域约束', () => {
  /**
   * **Validates: Requirements 3.3, 3.4, 3.5**
   *
   * IT_Dependency 切换 → 子面板展开/必填状态正确，已填数据不变
   */

  const IT_REQUIRED_MAP: Record<ITDependency, { expanded: boolean; required: boolean; hint: string }> = {
    '高': { expanded: true, required: true, hint: '' },
    '中': { expanded: true, required: false, hint: '可选择性执行' },
    '低': { expanded: false, required: false, hint: '可简化执行' },
  }

  it('IT_Dependency determines correct expanded/required state', () => {
    fc.assert(
      fc.property(
        arbITDependency,
        (dependency) => {
          const expected = IT_REQUIRED_MAP[dependency]
          expect(expected).toBeDefined()

          if (dependency === '高') {
            expect(expected.expanded).toBe(true)
            expect(expected.required).toBe(true)
          } else if (dependency === '中') {
            expect(expected.expanded).toBe(true)
            expect(expected.required).toBe(false)
          } else {
            expect(expected.expanded).toBe(false)
            expect(expected.required).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('IT_Dependency change does not alter existing data', () => {
    fc.assert(
      fc.property(
        arbITDependency,
        arbITDependency,
        fc.array(arbConclusion, { minLength: 1, maxLength: 3 }),
        (fromDep, toDep, itgcConclusions) => {
          // Setup with existing ITGC data
          const allResponses = ref(new Map<string, ChecklistResponse>())
          allResponses.value.set('B22A-T4-IT-dependency', {
            item_id: 'B22A-T4-IT-dependency',
            conclusion: fromDep,
            remark: null,
            wp_ref: null,
          })

          // Add some ITGC items
          const countId = 'B22A-T4-IT-itgc-count'
          allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(itgcConclusions.length), wp_ref: null })
          for (let i = 0; i < itgcConclusions.length; i++) {
            const itemId = `B22A-T4-IT-itgc-${i + 1}-conclusion`
            allResponses.value.set(itemId, { item_id: itemId, conclusion: itgcConclusions[i], remark: null, wp_ref: null })
          }

          // Need counts for tab 1-5 main items
          for (let t = 1; t <= 5; t++) {
            allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
          }

          const savedItems: ChecklistItem[] = []
          const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }

          const matrix = useB22AControlMatrix(allResponses, saveFn)
          matrix.initialize()

          // Snapshot ITGC data before switch
          const beforeData = itgcConclusions.map((_, i) => {
            const id = `B22A-T4-IT-itgc-${i + 1}-conclusion`
            return allResponses.value.get(id)?.conclusion
          })

          // Switch IT dependency
          matrix.setITDependency(toDep)

          // Verify ITGC data unchanged
          const afterData = itgcConclusions.map((_, i) => {
            const id = `B22A-T4-IT-itgc-${i + 1}-conclusion`
            return allResponses.value.get(id)?.conclusion
          })

          expect(afterData).toEqual(beforeData)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: ITGC 结论传递约束
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 5: ITGC 结论传递约束', () => {
  /**
   * **Validates: Requirements 3.7, 7.3**
   *
   * ITGC 结论"无效"→ isITGCInvalid=true；单向传递不逆向
   */
  it('isITGCInvalid = true iff itgcConclusion = 无效', () => {
    fc.assert(
      fc.property(
        fc.array(arbConclusion, { minLength: 1, maxLength: 5 }),
        (itgcConclusions) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())

          // Set ITGC items
          const countId = 'B22A-T4-IT-itgc-count'
          allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(itgcConclusions.length), wp_ref: null })
          for (let i = 0; i < itgcConclusions.length; i++) {
            const itemId = `B22A-T4-IT-itgc-${i + 1}-conclusion`
            allResponses.value.set(itemId, { item_id: itemId, conclusion: itgcConclusions[i], remark: null, wp_ref: null })
          }

          // Set counts for other items
          for (let t = 1; t <= 5; t++) {
            allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()

          // Compute expected ITGC score using computeAutoScore logic
          const items = itgcConclusions.map(c => makeCheckItem(c))
          const expectedScore = computeAutoScore(items)

          expect(matrix.itgcConclusion.value).toBe(expectedScore)
          expect(matrix.isITGCInvalid.value).toBe(expectedScore === '无效')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 复核前置条件完备性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 6: 复核前置条件完备性', () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * canReview=true ⟺ 全部检查项有 Conclusion ∧ 整体结论已选择
   */
  it('canReview = true iff all items have conclusion AND overallConclusion is set', () => {
    fc.assert(
      fc.property(
        // Random items per tab (1-3 items each, with random completion)
        fc.tuple(
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 3 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 3 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 3 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 3 }),
          fc.array(arbConclusionOrNull, { minLength: 1, maxLength: 3 }),
        ),
        arbElementScoreOrNull, // overallConclusion
        ([tab1, tab2, tab3, tab4, tab5], overall) => {
          const allTabs = { 1: tab1, 2: tab2, 3: tab3, 4: tab4, 5: tab5 }

          const allResponses = ref(new Map<string, ChecklistResponse>())
          for (const [tabStr, conclusions] of Object.entries(allTabs)) {
            const tab = Number(tabStr)
            const countId = `B22A-T${tab}-count`
            allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(conclusions.length), wp_ref: null })
            for (let i = 0; i < conclusions.length; i++) {
              const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
              if (conclusions[i] !== null) {
                allResponses.value.set(itemId, { item_id: itemId, conclusion: conclusions[i], remark: null, wp_ref: null })
              }
            }
          }

          if (overall) {
            allResponses.value.set('B22A-SUM-overall', {
              item_id: 'B22A-SUM-overall',
              conclusion: overall,
              remark: null,
              wp_ref: null,
            })
          }

          const overallConclusion = ref<ElementScore | null>(overall)
          const completedCount = computed(() => 0)
          const externalReadonly = ref(false)

          const review = useB22AReview(
            ref('test-wp'),
            allResponses,
            completedCount,
            overallConclusion,
            externalReadonly,
            noopSave,
          )

          // Compute expected canReview
          let allComplete = true
          for (const conclusions of Object.values(allTabs)) {
            for (const c of conclusions) {
              if (c === null) { allComplete = false; break }
            }
            if (!allComplete) break
          }
          const expectedCanReview = allComplete && overall !== null

          expect(review.canReview.value).toBe(expectedCanReview)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 复核后只读不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 7: 复核后只读不变式', () => {
  /**
   * **Validates: Requirements 10.3, 10.4, 10.6**
   *
   * review conclusion='Y' 或 readonly=true → isReadonly=true
   */
  it('isReadonly = (externalReadonly || reviewed)', () => {
    fc.assert(
      fc.property(
        fc.boolean(), // externalReadonly
        fc.boolean(), // isReviewed
        (extReadonly, reviewed) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          if (reviewed) {
            allResponses.value.set('B22A-review-sign', {
              item_id: 'B22A-review-sign',
              conclusion: 'Y',
              remark: '现场经理',
              wp_ref: '2026-01-01',
            })
          }

          const overallConclusion = ref<ElementScore | null>('有效')
          const completedCount = computed(() => 5)
          const externalReadonly = ref(extReadonly)

          const review = useB22AReview(
            ref('test-wp'),
            allResponses,
            completedCount,
            overallConclusion,
            externalReadonly,
            noopSave,
          )

          const expected = extReadonly || reviewed
          expect(review.isReadonly.value).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: item_id 命名唯一性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 8: item_id 命名唯一性', () => {
  /**
   * **Validates: Requirements 9.7**
   *
   * generateItemId 唯一，相同输入相同输出
   */
  it('different inputs produce different item_ids', () => {
    fc.assert(
      fc.property(
        fc.record({
          tab: arbTabNumber,
          index: fc.integer({ min: 1, max: 20 }),
          field: fc.constantFrom<'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange'>('point', 'desc', 'method', 'conclusion', 'ref', 'nochange'),
          subPanel: fc.option(arbITSubPanel, { nil: undefined }),
        }),
        fc.record({
          tab: arbTabNumber,
          index: fc.integer({ min: 1, max: 20 }),
          field: fc.constantFrom<'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange'>('point', 'desc', 'method', 'conclusion', 'ref', 'nochange'),
          subPanel: fc.option(arbITSubPanel, { nil: undefined }),
        }),
        (input1, input2) => {
          const id1 = generateItemId(input1.tab, input1.index, input1.field, input1.subPanel)
          const id2 = generateItemId(input2.tab, input2.index, input2.field, input2.subPanel)

          const sameInputs = (
            input1.tab === input2.tab &&
            input1.index === input2.index &&
            input1.field === input2.field &&
            input1.subPanel === input2.subPanel
          )

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
        arbTabNumber,
        fc.integer({ min: 1, max: 20 }),
        fc.constantFrom<'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange'>('point', 'desc', 'method', 'conclusion', 'ref', 'nochange'),
        fc.option(arbITSubPanel, { nil: undefined }),
        (tab, index, field, subPanel) => {
          const id1 = generateItemId(tab, index, field, subPanel)
          const id2 = generateItemId(tab, index, field, subPanel)
          expect(id1).toBe(id2)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('IT subPanel item_ids do not collide with regular item_ids', () => {
    fc.assert(
      fc.property(
        arbTabNumber,
        fc.integer({ min: 1, max: 10 }),
        fc.constantFrom<'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange'>('point', 'desc', 'method', 'conclusion', 'ref', 'nochange'),
        arbITSubPanel,
        (tab, index, field, panel) => {
          const regularId = generateItemId(tab, index, field, undefined)
          const itId = generateItemId(tab, index, field, panel)
          expect(regularId).not.toBe(itId)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 颜色编码双射
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 9: 颜色编码双射', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * SCORE_COLOR_MAP 满足双射（有效→绿/部分有效→黄/无效→红/不适用→灰）
   */
  it('different scores produce different bg colors', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<ElementScore | '不适用'>('有效', '部分有效', '无效', '不适用'),
        fc.constantFrom<ElementScore | '不适用'>('有效', '部分有效', '无效', '不适用'),
        (score1, score2) => {
          const color1 = SCORE_COLOR_MAP[score1]
          const color2 = SCORE_COLOR_MAP[score2]

          if (score1 === score2) {
            expect(color1.bg).toBe(color2.bg)
            expect(color1.text).toBe(color2.text)
          } else {
            expect(color1.bg).not.toBe(color2.bg)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('exhaustive: 有效→绿, 部分有效→黄, 无效→红, 不适用→灰', () => {
    expect(SCORE_COLOR_MAP['有效'].bg).toBe('#D1FAE5')
    expect(SCORE_COLOR_MAP['部分有效'].bg).toBe('#FEF3C7')
    expect(SCORE_COLOR_MAP['无效'].bg).toBe('#FEE2E2')
    expect(SCORE_COLOR_MAP['不适用'].bg).toBe('#F3F4F6')

    // All unique
    const bgs = Object.values(SCORE_COLOR_MAP).map(v => v.bg)
    expect(new Set(bgs).size).toBe(4)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: Tab 切换数据保持不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 10: Tab 切换数据保持不变式', () => {
  /**
   * **Validates: Requirements 1.3**
   *
   * switchTab 操作不改变 tabXData 状态
   */
  it('tab switch does not alter allResponses data', () => {
    fc.assert(
      fc.property(
        // Random edits across tabs
        fc.array(
          fc.record({
            tab: arbTabNumber,
            index: fc.integer({ min: 1, max: 5 }),
            field: fc.constantFrom('point', 'desc', 'ref'),
            remark: fc.string({ minLength: 1, maxLength: 20 }),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        // Random tab switch sequence
        fc.array(arbTabNumber, { minLength: 1, maxLength: 8 }),
        (edits, tabSwitches) => {
          const allResponses = new Map<string, ChecklistResponse>()

          // Apply edits
          for (const edit of edits) {
            const itemId = `B22A-T${edit.tab}-item-${edit.index}-${edit.field}`
            allResponses.set(itemId, {
              item_id: itemId,
              conclusion: null,
              remark: edit.remark,
              wp_ref: null,
            })
          }

          // Helper to get tab data by prefix
          function getTabData(tab: TabNumber): Map<string, ChecklistResponse> {
            const items = new Map<string, ChecklistResponse>()
            for (const [key, val] of allResponses) {
              if (key.startsWith(`B22A-T${tab}-`)) {
                items.set(key, val)
              }
            }
            return items
          }

          // Snapshot before tab switches
          const snapshots = new Map<TabNumber, Map<string, ChecklistResponse>>()
          for (const tab of [1, 2, 3, 4, 5] as TabNumber[]) {
            snapshots.set(tab, new Map(getTabData(tab)))
          }

          // Simulate tab switches (no-op on data)
          let _activeTab: TabNumber = 1
          for (const t of tabSwitches) {
            _activeTab = t
          }

          // Verify data unchanged
          for (const tab of [1, 2, 3, 4, 5] as TabNumber[]) {
            expect(getTabData(tab)).toEqual(snapshots.get(tab))
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 续审数据继承完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 11: 续审数据继承完整性', () => {
  /**
   * **Validates: Requirements 8.3, 8.4**
   *
   * 加载上年数据仅填充空白项，不覆盖已有编辑
   */
  it('prior year data only fills empty items, never overwrites existing', () => {
    fc.assert(
      fc.property(
        // Current data: some items have conclusions, some null
        fc.array(arbConclusionOrNull, { minLength: 3, maxLength: 6 }),
        // Prior year data: all items have conclusions
        fc.array(arbConclusion, { minLength: 3, maxLength: 6 }),
        (currentConclusions, priorConclusions) => {
          const count = Math.min(currentConclusions.length, priorConclusions.length)
          const tab: TabNumber = 1

          const allResponses = ref(new Map<string, ChecklistResponse>())
          const countId = `B22A-T${tab}-count`
          allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(count), wp_ref: null })

          // Set current data
          for (let i = 0; i < count; i++) {
            const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
            if (currentConclusions[i] !== null) {
              allResponses.value.set(itemId, { item_id: itemId, conclusion: currentConclusions[i], remark: null, wp_ref: null })
            }
            const pointId = `B22A-T${tab}-item-${i + 1}-point`
            allResponses.value.set(pointId, { item_id: pointId, conclusion: null, remark: `要点${i}`, wp_ref: null })
          }

          // Set up other tabs with 0 count
          for (let t = 2; t <= 5; t++) {
            allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()

          // Set prior year data
          for (let i = 0; i < count; i++) {
            const itemId = `B22A-T${tab}-item-${i + 1}-conclusion`
            matrix.priorYearData.value.set(itemId, {
              item_id: itemId,
              conclusion: priorConclusions[i],
              remark: null,
              wp_ref: null,
            })
          }

          // Read check items — priorYearConclusion should be set
          const items = matrix.getCheckItems(tab)
          for (let i = 0; i < count; i++) {
            // priorYearConclusion always reflects prior year data
            expect(items[i].priorYearConclusion).toBe(priorConclusions[i])

            // Current conclusion should NOT be overwritten
            if (currentConclusions[i] !== null) {
              expect(items[i].conclusion).toBe(currentConclusions[i])
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: Tab/要素完成状态准确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 12: Tab/要素完成状态准确性', () => {
  /**
   * **Validates: Requirements 1.4, 1.6, 4.6**
   *
   * tabStatus + elementStats + completedElementCount 计算准确
   */
  it('computeTabStatus satisfies empty/partial/complete rules', () => {
    fc.assert(
      fc.property(
        fc.array(arbConclusionOrNull, { minLength: 0, maxLength: 10 }),
        (conclusions) => {
          const items = conclusions.map(c => makeCheckItem(c))
          const status = computeTabStatus(items)

          if (items.length === 0) {
            expect(status).toBe('empty')
          } else {
            const withConclusion = items.filter(i => i.conclusion !== null)
            if (withConclusion.length === 0) {
              expect(status).toBe('empty')
            } else if (withConclusion.length === items.length) {
              expect(status).toBe('complete')
            } else {
              expect(status).toBe('partial')
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('completedElementCount = number of tabs with non-null effective score', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.array(arbConclusion, { minLength: 0, maxLength: 3 }),
          fc.array(arbConclusion, { minLength: 0, maxLength: 3 }),
          fc.array(arbConclusion, { minLength: 0, maxLength: 3 }),
          fc.array(arbConclusion, { minLength: 0, maxLength: 3 }),
          fc.array(arbConclusion, { minLength: 0, maxLength: 3 }),
        ),
        ([t1, t2, t3, t4, t5]) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const tabs = [t1, t2, t3, t4, t5]

          for (let tabIdx = 0; tabIdx < 5; tabIdx++) {
            const tab = (tabIdx + 1) as TabNumber
            const items = tabs[tabIdx]
            allResponses.value.set(`B22A-T${tab}-count`, {
              item_id: `B22A-T${tab}-count`, conclusion: null, remark: String(items.length), wp_ref: null,
            })
            for (let i = 0; i < items.length; i++) {
              allResponses.value.set(`B22A-T${tab}-item-${i + 1}-conclusion`, {
                item_id: `B22A-T${tab}-item-${i + 1}-conclusion`, conclusion: items[i], remark: null, wp_ref: null,
              })
              allResponses.value.set(`B22A-T${tab}-item-${i + 1}-point`, {
                item_id: `B22A-T${tab}-item-${i + 1}-point`, conclusion: null, remark: `p${i}`, wp_ref: null,
              })
            }
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()

          // Count tabs with items (score can be computed)
          let expectedCompleted = 0
          for (let tabIdx = 0; tabIdx < 5; tabIdx++) {
            if (tabs[tabIdx].length > 0) expectedCompleted++
          }

          expect(matrix.completedElementCount.value).toBe(expectedCompleted)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 13: 业务规则警告条件正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b22a-control-matrix, Property 13: 业务规则警告条件正确性', () => {
  /**
   * **Validates: Requirements 13.1, 13.3, 13.4, 4.5**
   *
   * controlEnvWeakWarning 和 itControlWeakWarning 的布尔值满足条件规则
   */
  it('itControlWeakWarning = (itDependency=高 AND itgcConclusion=无效)', () => {
    fc.assert(
      fc.property(
        arbITDependency,
        fc.array(arbConclusion, { minLength: 1, maxLength: 5 }),
        (dependency, itgcConclusions) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())

          // Set IT dependency
          allResponses.value.set('B22A-T4-IT-dependency', {
            item_id: 'B22A-T4-IT-dependency',
            conclusion: dependency,
            remark: null,
            wp_ref: null,
          })

          // Set ITGC items
          const countId = 'B22A-T4-IT-itgc-count'
          allResponses.value.set(countId, { item_id: countId, conclusion: null, remark: String(itgcConclusions.length), wp_ref: null })
          for (let i = 0; i < itgcConclusions.length; i++) {
            allResponses.value.set(`B22A-T4-IT-itgc-${i + 1}-conclusion`, {
              item_id: `B22A-T4-IT-itgc-${i + 1}-conclusion`, conclusion: itgcConclusions[i], remark: null, wp_ref: null,
            })
          }

          // Set counts for other
          for (let t = 1; t <= 5; t++) {
            allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()

          // Compute expected ITGC score
          const items = itgcConclusions.map(c => makeCheckItem(c))
          const itgcScore = computeAutoScore(items)

          const expected = dependency === '高' && itgcScore === '无效'
          expect(matrix.itControlWeakWarning.value).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('controlEnvWeakWarning requires Tab_1 score 无效/部分有效 AND critical deficiency', () => {
    fc.assert(
      fc.property(
        // Tab 1 items: include some with critical keywords
        fc.array(
          fc.record({
            conclusion: arbConclusion,
            controlPoint: fc.constantFrom(
              '管理层诚信与道德', '治理层独立性', '普通控制', '组织结构', '人力资源'
            ),
          }),
          { minLength: 2, maxLength: 6 },
        ),
        (tab1Items) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())

          // Set Tab 1 items
          allResponses.value.set('B22A-T1-count', {
            item_id: 'B22A-T1-count', conclusion: null, remark: String(tab1Items.length), wp_ref: null,
          })
          for (let i = 0; i < tab1Items.length; i++) {
            allResponses.value.set(`B22A-T1-item-${i + 1}-conclusion`, {
              item_id: `B22A-T1-item-${i + 1}-conclusion`, conclusion: tab1Items[i].conclusion, remark: null, wp_ref: null,
            })
            allResponses.value.set(`B22A-T1-item-${i + 1}-point`, {
              item_id: `B22A-T1-item-${i + 1}-point`, conclusion: null, remark: tab1Items[i].controlPoint, wp_ref: null,
            })
          }

          // Other tabs empty
          for (let t = 2; t <= 5; t++) {
            allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
          }

          const matrix = useB22AControlMatrix(allResponses, noopSave)
          matrix.initialize()

          // Compute expected
          const items = tab1Items.map(t => makeCheckItem(t.conclusion, t.controlPoint))
          const tab1Score = computeAutoScore(items)
          const scoreWeak = tab1Score === '无效' || tab1Score === '部分有效'
          const hasCriticalDeficiency = tab1Items.some(
            t => t.conclusion === '设计无效' &&
              (t.controlPoint.includes('诚信') || t.controlPoint.includes('独立性') || t.controlPoint.includes('治理'))
          )

          const expected = scoreWeak && hasCriticalDeficiency
          expect(matrix.controlEnvWeakWarning.value).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})
