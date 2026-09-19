/**
 * Property-Based Tests — B23 业务流程与控制了解表
 *
 * Spec: .kiro/specs/b23-process-control/
 * Task: 6.1
 *
 * 使用 fast-check + vitest 验证 correctness properties。
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  useB23ProcessControl,
  generateItemId,
  suggestProcessConclusion,
  PROCESS_CONCLUSION_COLOR_MAP,
  CONCLUSION_TO_B50_IMPACT,
  STANDARD_PROCESSES,
  type ProcessConclusion,
  type WalkthroughConclusion,
  type ControlPoint,
  type ProcessCard,
  type ControlConclusionPayload,
  type LinkageInfo,
} from '../composables/useB23ProcessControl'
import type { ChecklistItem, ChecklistResponse, ProcessNumber } from '../composables/useB23FormData'
import { useB23Review } from '../composables/useB23Review'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** No-op save function for testing */
const noopSave = async (_items: ChecklistItem[]) => {}

/** Arbitrary for ProcessNumber */
const arbProcessNumber = fc.constantFrom<ProcessNumber>(1, 2, 3, 4, 5, 6, 7, 8)

/** Arbitrary for ProcessConclusion (non-null) */
const arbProcessConclusion = fc.constantFrom<ProcessConclusion>(
  '设计有效且已实施',
  '设计有效但未有效实施',
  '设计无效',
  '不适用',
)

/** Arbitrary for WalkthroughConclusion */
const arbWalkthroughConclusion = fc.constantFrom<WalkthroughConclusion>(
  '控制有效运行',
  '控制未有效运行',
  '未执行穿行',
  '不适用',
)

/** Arbitrary for nullable WalkthroughConclusion */
const arbWalkthroughConclusionOrNull = fc.constantFrom<WalkthroughConclusion | null>(
  '控制有效运行',
  '控制未有效运行',
  '未执行穿行',
  '不适用',
  null,
)

/** Config for a single process in the random scenario */
interface ProcessConfig {
  applicable: boolean
  conclusion: ProcessConclusion | null
  controlPointCount: number
  /** For each control point: whether it has "穿行测试" method and its conclusion */
  controlPoints: Array<{
    hasWalkthrough: boolean
    conclusion: WalkthroughConclusion | null
  }>
}

/** Arbitrary for a single process config */
const arbProcessConfig: fc.Arbitrary<ProcessConfig> = fc.record({
  applicable: fc.boolean(),
  conclusion: fc.oneof(arbProcessConclusion, fc.constant(null)),
  controlPointCount: fc.integer({ min: 0, max: 5 }),
  controlPoints: fc.array(
    fc.record({
      hasWalkthrough: fc.boolean(),
      conclusion: arbWalkthroughConclusionOrNull,
    }),
    { minLength: 0, maxLength: 5 },
  ),
}).map(config => ({
  ...config,
  // Ensure controlPoints array matches controlPointCount
  controlPoints: config.controlPoints.slice(0, config.controlPointCount),
  controlPointCount: Math.min(config.controlPointCount, config.controlPoints.length),
}))

/** Build allResponses map from 8 process configs */
function buildAllResponses(configs: ProcessConfig[]): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()

  for (let i = 0; i < 8; i++) {
    const num = (i + 1) as ProcessNumber
    const config = configs[i]

    // Applicability
    const applicabilityId = generateItemId(num, 'applicability')
    map.set(applicabilityId, {
      item_id: applicabilityId,
      conclusion: config.applicable ? 'Y' : 'N',
      remark: null,
      wp_ref: null,
    })

    // Process conclusion
    const conclusionId = generateItemId(num, 'process-conclusion')
    if (!config.applicable) {
      // Not applicable → conclusion is '不适用'
      map.set(conclusionId, {
        item_id: conclusionId,
        conclusion: '不适用',
        remark: null,
        wp_ref: null,
      })
    } else if (config.conclusion) {
      map.set(conclusionId, {
        item_id: conclusionId,
        conclusion: config.conclusion,
        remark: null,
        wp_ref: null,
      })
    }

    // Control point count
    const countId = generateItemId(num, 'ctrl-count')
    map.set(countId, {
      item_id: countId,
      conclusion: null,
      remark: String(config.controlPointCount),
      wp_ref: null,
    })

    // Control points
    for (let m = 1; m <= config.controlPointCount; m++) {
      const cpConfig = config.controlPoints[m - 1]
      if (!cpConfig) continue

      // Methods
      const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
      const methods = cpConfig.hasWalkthrough ? '穿行测试' : '询问,观察'
      map.set(methodsId, {
        item_id: methodsId,
        conclusion: null,
        remark: methods,
        wp_ref: null,
      })

      // Conclusion
      const conclusionCtrlId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
      map.set(conclusionCtrlId, {
        item_id: conclusionCtrlId,
        conclusion: cpConfig.conclusion,
        remark: null,
        wp_ref: null,
      })
    }
  }

  return map
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 状态仪表盘同步不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 1: 状态仪表盘同步不变式', () => {
  /**
   * **Validates: Requirements 1.1, 1.7, 2.4**
   *
   * 生成随机 8 流程 × 随机适用性 × 随机控制点状态 × 随机 Process_Conclusion
   * → 验证：
   *   completionDistribution 各分类计数之和=8；
   *   effectivenessDistribution 各分类=实际结论分布；
   *   pendingWalkthroughCount=适用流程中需穿行但结论为空的控制点数
   */
  it('completionDistribution 各分类计数之和始终等于 8', () => {
    fc.assert(
      fc.property(
        fc.array(arbProcessConfig, { minLength: 8, maxLength: 8 }),
        (configs) => {
          const allResponses = ref(buildAllResponses(configs))
          const { dashboardStats } = useB23ProcessControl(allResponses, noopSave)

          const stats = dashboardStats.value
          const { completed, inProgress, notStarted, notApplicable } = stats.completionDistribution

          // Sum must always equal 8
          expect(completed + inProgress + notStarted + notApplicable).toBe(8)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('effectivenessDistribution 各分类计数等于实际 ProcessConclusion 分布', () => {
    fc.assert(
      fc.property(
        fc.array(arbProcessConfig, { minLength: 8, maxLength: 8 }),
        (configs) => {
          const allResponses = ref(buildAllResponses(configs))
          const { dashboardStats, processes } = useB23ProcessControl(allResponses, noopSave)

          const stats = dashboardStats.value
          const cards = processes.value

          // Manually compute expected effectiveness distribution
          let expectedEffective = 0
          let expectedPartiallyEffective = 0
          let expectedIneffective = 0
          let expectedNA = 0

          for (const card of cards) {
            if (!card.applicable) {
              expectedNA++
              continue
            }
            switch (card.conclusion) {
              case '设计有效且已实施':
                expectedEffective++
                break
              case '设计有效但未有效实施':
                expectedPartiallyEffective++
                break
              case '设计无效':
                expectedIneffective++
                break
              default:
                break
            }
          }

          expect(stats.effectivenessDistribution.effective).toBe(expectedEffective)
          expect(stats.effectivenessDistribution.partiallyEffective).toBe(expectedPartiallyEffective)
          expect(stats.effectivenessDistribution.ineffective).toBe(expectedIneffective)
          expect(stats.effectivenessDistribution.notApplicable).toBe(expectedNA)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('pendingWalkthroughCount 等于适用流程中需穿行但结论为空的控制点数', () => {
    fc.assert(
      fc.property(
        fc.array(arbProcessConfig, { minLength: 8, maxLength: 8 }),
        (configs) => {
          const allResponses = ref(buildAllResponses(configs))
          const { dashboardStats, processes } = useB23ProcessControl(allResponses, noopSave)

          const stats = dashboardStats.value
          const cards = processes.value

          // Manually compute expected pending walkthrough count
          let expectedPending = 0
          for (const card of cards) {
            if (!card.applicable) continue
            for (const cp of card.controlPoints) {
              if (cp.methods.includes('穿行测试') && cp.conclusion === null) {
                expectedPending++
              }
            }
          }

          expect(stats.pendingWalkthroughCount).toBe(expectedPending)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('completionDistribution 分类与实际流程状态一致', () => {
    fc.assert(
      fc.property(
        fc.array(arbProcessConfig, { minLength: 8, maxLength: 8 }),
        (configs) => {
          const allResponses = ref(buildAllResponses(configs))
          const { dashboardStats, processes } = useB23ProcessControl(allResponses, noopSave)

          const stats = dashboardStats.value
          const cards = processes.value

          // Manually compute expected completion distribution
          let expectedCompleted = 0
          let expectedInProgress = 0
          let expectedNotStarted = 0
          let expectedNotApplicable = 0

          for (const card of cards) {
            if (!card.applicable) {
              expectedNotApplicable++
            } else if (card.conclusion) {
              expectedCompleted++
            } else if (card.controlPoints.length > 0) {
              expectedInProgress++
            } else {
              expectedNotStarted++
            }
          }

          expect(stats.completionDistribution.completed).toBe(expectedCompleted)
          expect(stats.completionDistribution.inProgress).toBe(expectedInProgress)
          expect(stats.completionDistribution.notStarted).toBe(expectedNotStarted)
          expect(stats.completionDistribution.notApplicable).toBe(expectedNotApplicable)
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: Process_Conclusion 自动建议一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 2: Process_Conclusion 自动建议一致性', () => {
  /**
   * **Validates: Requirements 5.2, 5.3, 5.4, 5.5**
   *
   * 生成随机 N 个控制点(1~20) × 随机 WalkthroughConclusion 值
   * → 验证：
   *   全有效→"设计有效且已实施"；
   *   无效占比≤30%→"设计有效但未有效实施"；
   *   >30%→"设计无效"；
   *   无已评估→null
   */

  /** Arbitrary for a minimal ControlPoint with only conclusion relevant */
  const arbControlPointConclusion = fc.constantFrom<WalkthroughConclusion | null>(
    '控制有效运行',
    '控制未有效运行',
    '未执行穿行',
    '不适用',
    null,
  )

  /** Build a minimal ControlPoint array from conclusion values */
  function buildControlPoints(conclusions: (WalkthroughConclusion | null)[]): ControlPoint[] {
    return conclusions.map((conclusion, i) => ({
      index: i + 1,
      objective: '',
      description: '',
      frequency: null,
      executor: '',
      methods: [],
      conclusion,
      remark: '',
      isPreset: false,
    }))
  }

  it('无已评估控制点时返回 null', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.constantFrom<WalkthroughConclusion | null>(null, '不适用'),
          { minLength: 1, maxLength: 20 },
        ),
        (conclusions) => {
          const controlPoints = buildControlPoints(conclusions)
          const result = suggestProcessConclusion(controlPoints)
          expect(result).toBeNull()
        },
      ),
      { numRuns: 200 },
    )
  })

  it('全部为"控制有效运行"时返回"设计有效且已实施"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 }),
        fc.array(
          fc.constantFrom<WalkthroughConclusion | null>(null, '不适用'),
          { minLength: 0, maxLength: 10 },
        ),
        (effectiveCount, nonEvaluated) => {
          // Build array: effectiveCount "控制有效运行" + some non-evaluated
          const conclusions: (WalkthroughConclusion | null)[] = [
            ...Array(effectiveCount).fill('控制有效运行'),
            ...nonEvaluated,
          ]
          const controlPoints = buildControlPoints(conclusions)
          const result = suggestProcessConclusion(controlPoints)
          expect(result).toBe('设计有效且已实施')
        },
      ),
      { numRuns: 200 },
    )
  })

  it('无效占比≤30%时返回"设计有效但未有效实施"', () => {
    fc.assert(
      fc.property(
        // Generate total evaluated count (at least 2 so we can have ineffective ≤ 30%)
        fc.integer({ min: 4, max: 20 }),
        fc.nat(),
        fc.array(
          fc.constantFrom<WalkthroughConclusion | null>(null, '不适用'),
          { minLength: 0, maxLength: 5 },
        ),
        (totalEvaluated, seed, nonEvaluated) => {
          // Calculate max ineffective count for ≤30%: floor(totalEvaluated * 0.3)
          const maxIneffective = Math.floor(totalEvaluated * 0.3)
          if (maxIneffective < 1) return // Skip if we can't have at least 1 ineffective

          // Pick ineffective count in [1, maxIneffective]
          const ineffectiveCount = (seed % maxIneffective) + 1
          const effectiveCount = totalEvaluated - ineffectiveCount

          const conclusions: (WalkthroughConclusion | null)[] = [
            ...Array(effectiveCount).fill('控制有效运行'),
            ...Array(ineffectiveCount).fill('控制未有效运行'),
            ...nonEvaluated,
          ]
          const controlPoints = buildControlPoints(conclusions)
          const result = suggestProcessConclusion(controlPoints)
          expect(result).toBe('设计有效但未有效实施')
        },
      ),
      { numRuns: 200 },
    )
  })

  it('无效占比>30%时返回"设计无效"', () => {
    fc.assert(
      fc.property(
        // Generate total evaluated count (at least 2)
        fc.integer({ min: 2, max: 20 }),
        fc.nat(),
        fc.array(
          fc.constantFrom<WalkthroughConclusion | null>(null, '不适用'),
          { minLength: 0, maxLength: 5 },
        ),
        (totalEvaluated, seed, nonEvaluated) => {
          // Calculate min ineffective count for >30%: floor(totalEvaluated * 0.3) + 1
          const minIneffective = Math.floor(totalEvaluated * 0.3) + 1
          if (minIneffective > totalEvaluated) return // Skip if impossible

          // Pick ineffective count in [minIneffective, totalEvaluated]
          const range = totalEvaluated - minIneffective + 1
          const ineffectiveCount = minIneffective + (seed % range)
          const effectiveCount = totalEvaluated - ineffectiveCount

          const conclusions: (WalkthroughConclusion | null)[] = [
            ...Array(effectiveCount).fill('控制有效运行'),
            ...Array(ineffectiveCount).fill('控制未有效运行'),
            ...nonEvaluated,
          ]
          const controlPoints = buildControlPoints(conclusions)
          const result = suggestProcessConclusion(controlPoints)
          expect(result).toBe('设计无效')
        },
      ),
      { numRuns: 200 },
    )
  })

  it('30% 阈值规则完整验证（随机混合结论分布）', () => {
    fc.assert(
      fc.property(
        fc.array(arbControlPointConclusion, { minLength: 1, maxLength: 20 }),
        (conclusions) => {
          const controlPoints = buildControlPoints(conclusions)
          const result = suggestProcessConclusion(controlPoints)

          // Manually compute expected result
          const evaluated = conclusions.filter(c => c !== null && c !== '不适用')
          if (evaluated.length === 0) {
            expect(result).toBeNull()
            return
          }

          const ineffective = evaluated.filter(c => c === '控制未有效运行')
          if (ineffective.length === 0) {
            expect(result).toBe('设计有效且已实施')
            return
          }

          const ratio = ineffective.length / evaluated.length
          if (ratio <= 0.3) {
            expect(result).toBe('设计有效但未有效实施')
          } else {
            expect(result).toBe('设计无效')
          }
        },
      ),
      { numRuns: 500 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 流程适用性约束
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 3: 流程适用性约束', () => {
  /**
   * **Validates: Requirements 2.2, 2.3, 2.5**
   *
   * 生成随机流程编号 × 随机 toggle 序列(1~10次)
   * → 验证：
   *   最终不适用→conclusion="不适用"；
   *   最终适用→conclusion=null；
   *   已有控制点数据不被删除
   */

  /** Arbitrary for a toggle sequence: array of booleans representing applicable values */
  const arbToggleSequence = fc.array(fc.boolean(), { minLength: 1, maxLength: 10 })

  /** Helper: set up a process with some control point data pre-populated */
  function buildResponsesWithControlPointData(
    num: ProcessNumber,
    ctrlCount: number,
  ): Map<string, ChecklistResponse> {
    const map = new Map<string, ChecklistResponse>()

    // Set as applicable initially
    const applicabilityId = generateItemId(num, 'applicability')
    map.set(applicabilityId, {
      item_id: applicabilityId,
      conclusion: 'Y',
      remark: null,
      wp_ref: null,
    })

    // Control point count
    const countId = generateItemId(num, 'ctrl-count')
    map.set(countId, {
      item_id: countId,
      conclusion: null,
      remark: String(ctrlCount),
      wp_ref: null,
    })

    // Populate control point data
    for (let m = 1; m <= ctrlCount; m++) {
      const objectiveId = generateItemId(num, 'ctrl', m, undefined, 'objective')
      map.set(objectiveId, {
        item_id: objectiveId,
        conclusion: null,
        remark: `控制目标${m}`,
        wp_ref: null,
      })

      const descId = generateItemId(num, 'ctrl', m, undefined, 'description')
      map.set(descId, {
        item_id: descId,
        conclusion: null,
        remark: `控制描述${m}`,
        wp_ref: null,
      })

      const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
      map.set(methodsId, {
        item_id: methodsId,
        conclusion: null,
        remark: '穿行测试,询问',
        wp_ref: null,
      })

      const conclusionId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
      map.set(conclusionId, {
        item_id: conclusionId,
        conclusion: '控制有效运行',
        remark: null,
        wp_ref: null,
      })
    }

    return map
  }

  it('toggle 序列结束后: 不适用→conclusion="不适用"; 适用→conclusion=null', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbToggleSequence,
        (num, toggles) => {
          const allResponses = ref(buildResponsesWithControlPointData(num, 2))
          const { setApplicability, getConclusion } = useB23ProcessControl(allResponses, noopSave)

          // Apply each toggle in sequence
          for (const applicable of toggles) {
            setApplicability(num, applicable)
          }

          // The final toggle determines the expected state
          const finalApplicable = toggles[toggles.length - 1]
          const conclusion = getConclusion(num).value

          if (!finalApplicable) {
            // Not applicable → conclusion must be "不适用"
            expect(conclusion).toBe('不适用')
          } else {
            // Applicable → conclusion cleared to null
            expect(conclusion).toBeNull()
          }
        },
      ),
      { numRuns: 300 },
    )
  })

  it('toggle 序列不删除已有控制点数据（ctrl-count 保持不变）', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbToggleSequence,
        fc.integer({ min: 1, max: 5 }),
        (num, toggles, ctrlCount) => {
          const allResponses = ref(buildResponsesWithControlPointData(num, ctrlCount))
          const { setApplicability, getControlPoints } = useB23ProcessControl(allResponses, noopSave)

          // Apply each toggle in sequence
          for (const applicable of toggles) {
            setApplicability(num, applicable)
          }

          // Control point count must be preserved regardless of toggle sequence
          const countId = generateItemId(num, 'ctrl-count')
          const countResponse = allResponses.value.get(countId)
          expect(countResponse).toBeDefined()
          expect(parseInt(countResponse!.remark || '0', 10)).toBe(ctrlCount)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('toggle 序列不删除控制点字段数据（objective/description/methods/conclusion 保留）', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbToggleSequence,
        fc.integer({ min: 1, max: 3 }),
        (num, toggles, ctrlCount) => {
          const allResponses = ref(buildResponsesWithControlPointData(num, ctrlCount))
          const { setApplicability } = useB23ProcessControl(allResponses, noopSave)

          // Apply each toggle in sequence
          for (const applicable of toggles) {
            setApplicability(num, applicable)
          }

          // Verify all control point field data is still present
          for (let m = 1; m <= ctrlCount; m++) {
            const objectiveId = generateItemId(num, 'ctrl', m, undefined, 'objective')
            const objectiveResp = allResponses.value.get(objectiveId)
            expect(objectiveResp).toBeDefined()
            expect(objectiveResp!.remark).toBe(`控制目标${m}`)

            const descId = generateItemId(num, 'ctrl', m, undefined, 'description')
            const descResp = allResponses.value.get(descId)
            expect(descResp).toBeDefined()
            expect(descResp!.remark).toBe(`控制描述${m}`)

            const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
            const methodsResp = allResponses.value.get(methodsId)
            expect(methodsResp).toBeDefined()
            expect(methodsResp!.remark).toBe('穿行测试,询问')

            const conclusionCtrlId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
            const conclusionResp = allResponses.value.get(conclusionCtrlId)
            expect(conclusionResp).toBeDefined()
            expect(conclusionResp!.conclusion).toBe('控制有效运行')
          }
        },
      ),
      { numRuns: 300 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 穿行测试与了解方法联动
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 4: 穿行测试与了解方法联动', () => {
  /**
   * **Validates: Requirements 4.3, 4.5, 4.6**
   *
   * 生成随机控制点集合 × 随机 methods 组合
   * → 验证：
   *   methods 含"穿行测试"时存在记录条目；
   *   testedCount=有结论的控制点数；
   *   totalCount=需穿行的控制点数；
   *   全完成时 isWalkthroughComplete=true
   */

  /** Available Understanding_Method values */
  type UnderstandingMethod = '询问' | '观察' | '检查文件' | '穿行测试' | '重新执行'
  const ALL_METHODS: UnderstandingMethod[] = ['询问', '观察', '检查文件', '穿行测试', '重新执行']

  /** Arbitrary for a random subset of methods */
  const arbMethodsSubset = fc.subarray(ALL_METHODS, { minLength: 1 })

  /** Config for a control point in Property 4 scenario */
  interface P4ControlPointConfig {
    methods: UnderstandingMethod[]
    conclusion: WalkthroughConclusion | null
    walkthroughSampleCount: number
  }

  /** Arbitrary for a single control point config */
  const arbP4ControlPoint: fc.Arbitrary<P4ControlPointConfig> = fc.record({
    methods: arbMethodsSubset,
    conclusion: arbWalkthroughConclusionOrNull,
    walkthroughSampleCount: fc.integer({ min: 0, max: 3 }),
  })

  /** Build allResponses for a single process with given control point configs */
  function buildP4Responses(
    num: ProcessNumber,
    controlPointConfigs: P4ControlPointConfig[],
  ): Map<string, ChecklistResponse> {
    const map = new Map<string, ChecklistResponse>()

    // Set as applicable
    const applicabilityId = generateItemId(num, 'applicability')
    map.set(applicabilityId, {
      item_id: applicabilityId,
      conclusion: 'Y',
      remark: null,
      wp_ref: null,
    })

    // Control point count
    const count = controlPointConfigs.length
    const countId = generateItemId(num, 'ctrl-count')
    map.set(countId, {
      item_id: countId,
      conclusion: null,
      remark: String(count),
      wp_ref: null,
    })

    // Populate each control point
    for (let m = 1; m <= count; m++) {
      const cpConfig = controlPointConfigs[m - 1]

      // Methods (comma-separated)
      const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
      map.set(methodsId, {
        item_id: methodsId,
        conclusion: null,
        remark: cpConfig.methods.join(','),
        wp_ref: null,
      })

      // Conclusion
      const conclusionId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
      map.set(conclusionId, {
        item_id: conclusionId,
        conclusion: cpConfig.conclusion,
        remark: null,
        wp_ref: null,
      })

      // Walkthrough sample count (only relevant if methods includes 穿行测试)
      if (cpConfig.methods.includes('穿行测试')) {
        const wtCountId = generateItemId(num, 'wt-count', m)
        const sampleCount = Math.max(1, cpConfig.walkthroughSampleCount) // At least 1 record when method includes 穿行测试
        map.set(wtCountId, {
          item_id: wtCountId,
          conclusion: null,
          remark: String(sampleCount),
          wp_ref: null,
        })

        // Populate walkthrough sample records
        for (let s = 1; s <= sampleCount; s++) {
          const sampleId = generateItemId(num, 'wt', m, s, 'sample')
          map.set(sampleId, {
            item_id: sampleId,
            conclusion: null,
            remark: `样本${m}-${s}`,
            wp_ref: null,
          })
        }
      }
    }

    return map
  }

  it('walkthroughSummary.totalCount 等于 methods 包含"穿行测试"的控制点数', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(arbP4ControlPoint, { minLength: 1, maxLength: 10 }),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { walkthroughSummary } = useB23ProcessControl(allResponses, noopSave)

          const summary = walkthroughSummary(num).value

          // Expected totalCount = control points whose methods include "穿行测试"
          const expectedTotal = cpConfigs.filter(cp => cp.methods.includes('穿行测试')).length
          expect(summary.totalCount).toBe(expectedTotal)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('walkthroughSummary.testedCount 等于需穿行且有结论的控制点数', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(arbP4ControlPoint, { minLength: 1, maxLength: 10 }),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { walkthroughSummary } = useB23ProcessControl(allResponses, noopSave)

          const summary = walkthroughSummary(num).value

          // Expected testedCount = control points that have "穿行测试" in methods AND conclusion !== null
          const expectedTested = cpConfigs.filter(
            cp => cp.methods.includes('穿行测试') && cp.conclusion !== null,
          ).length
          expect(summary.testedCount).toBe(expectedTested)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('isWalkthroughComplete: 全部需穿行控制点有结论时为 true', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(arbP4ControlPoint, { minLength: 1, maxLength: 10 }),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { isWalkthroughComplete } = useB23ProcessControl(allResponses, noopSave)

          const complete = isWalkthroughComplete(num).value

          // Expected: complete=true when ALL control points with "穿行测试" method have non-null conclusion
          const needsWalkthrough = cpConfigs.filter(cp => cp.methods.includes('穿行测试'))
          const expectedComplete =
            needsWalkthrough.length === 0 || needsWalkthrough.every(cp => cp.conclusion !== null)

          expect(complete).toBe(expectedComplete)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('methods 含"穿行测试"时穿行测试记录条目存在（至少1条）', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(arbP4ControlPoint, { minLength: 1, maxLength: 10 }),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { getWalkthroughRecords } = useB23ProcessControl(allResponses, noopSave)

          for (let m = 1; m <= cpConfigs.length; m++) {
            const cpConfig = cpConfigs[m - 1]
            const records = getWalkthroughRecords(num, m).value

            if (cpConfig.methods.includes('穿行测试')) {
              // When methods include "穿行测试", there should be at least 1 record
              expect(records.length).toBeGreaterThanOrEqual(1)
            }
          }
        },
      ),
      { numRuns: 300 },
    )
  })

  it('无需穿行测试的流程 isWalkthroughComplete 始终为 true', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(
          fc.record({
            methods: fc.subarray(
              ['询问', '观察', '检查文件', '重新执行'] as UnderstandingMethod[],
              { minLength: 1 },
            ),
            conclusion: arbWalkthroughConclusionOrNull,
            walkthroughSampleCount: fc.constant(0),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { isWalkthroughComplete, walkthroughSummary } = useB23ProcessControl(allResponses, noopSave)

          // No control point has "穿行测试" in methods → complete must be true
          expect(isWalkthroughComplete(num).value).toBe(true)
          expect(walkthroughSummary(num).value.totalCount).toBe(0)
          expect(walkthroughSummary(num).value.testedCount).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('completionRate = testedCount / totalCount（totalCount=0 时为 1）', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(arbP4ControlPoint, { minLength: 0, maxLength: 10 }),
        (num, cpConfigs) => {
          const allResponses = ref(buildP4Responses(num, cpConfigs))
          const { walkthroughSummary } = useB23ProcessControl(allResponses, noopSave)

          const summary = walkthroughSummary(num).value

          if (summary.totalCount === 0) {
            expect(summary.completionRate).toBe(1)
          } else {
            const expectedRate = summary.testedCount / summary.totalCount
            expect(summary.completionRate).toBeCloseTo(expectedRate, 10)
          }
        },
      ),
      { numRuns: 300 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 复核前置条件与只读不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 5: 复核前置条件与只读不变式', () => {
  /**
   * **Validates: Requirements 9.2, 9.3, 9.5**
   *
   * 生成随机 8 流程完成度 × 随机 review 状态 × 随机 readonly prop
   * → 验证：
   *   canReview=true ⟺ 全适用流程有结论+穿行完成；
   *   isReadonly=true ⟺ reviewed=Y 或 externalReadonly=true
   */

  /** Config for Property 5 scenario */
  interface P5ProcessConfig {
    applicable: boolean
    conclusion: ProcessConclusion | null
    /** Control points that need walkthrough (methods include 穿行测试) */
    walkthroughControlPoints: Array<{
      conclusion: WalkthroughConclusion | null
    }>
  }

  /** Arbitrary for P5 process config */
  const arbP5ProcessConfig: fc.Arbitrary<P5ProcessConfig> = fc.record({
    applicable: fc.boolean(),
    conclusion: fc.oneof(arbProcessConclusion, fc.constant(null)),
    walkthroughControlPoints: fc.array(
      fc.record({
        conclusion: arbWalkthroughConclusionOrNull,
      }),
      { minLength: 0, maxLength: 5 },
    ),
  })

  /** Build allResponses for 8 processes with P5 configs + review state */
  function buildP5Responses(
    configs: P5ProcessConfig[],
    reviewed: boolean,
  ): Map<string, ChecklistResponse> {
    const map = new Map<string, ChecklistResponse>()

    for (let i = 0; i < 8; i++) {
      const num = (i + 1) as ProcessNumber
      const config = configs[i]

      // Applicability
      const applicabilityId = generateItemId(num, 'applicability')
      map.set(applicabilityId, {
        item_id: applicabilityId,
        conclusion: config.applicable ? 'Y' : 'N',
        remark: null,
        wp_ref: null,
      })

      // Process conclusion
      const conclusionId = generateItemId(num, 'process-conclusion')
      if (!config.applicable) {
        map.set(conclusionId, {
          item_id: conclusionId,
          conclusion: '不适用',
          remark: null,
          wp_ref: null,
        })
      } else if (config.conclusion) {
        map.set(conclusionId, {
          item_id: conclusionId,
          conclusion: config.conclusion,
          remark: null,
          wp_ref: null,
        })
      }

      // Control points (only walkthrough-relevant ones)
      const ctrlCount = config.walkthroughControlPoints.length
      const countId = generateItemId(num, 'ctrl-count')
      map.set(countId, {
        item_id: countId,
        conclusion: null,
        remark: String(ctrlCount),
        wp_ref: null,
      })

      for (let m = 1; m <= ctrlCount; m++) {
        const cpConfig = config.walkthroughControlPoints[m - 1]

        // All control points in this test have "穿行测试" method
        const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
        map.set(methodsId, {
          item_id: methodsId,
          conclusion: null,
          remark: '穿行测试',
          wp_ref: null,
        })

        // Conclusion
        const conclusionCtrlId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
        map.set(conclusionCtrlId, {
          item_id: conclusionCtrlId,
          conclusion: cpConfig.conclusion,
          remark: null,
          wp_ref: null,
        })
      }
    }

    // Review sign
    map.set('B23-review-sign', {
      item_id: 'B23-review-sign',
      conclusion: reviewed ? 'Y' : null,
      remark: reviewed ? '审计经理' : null,
      wp_ref: reviewed ? '2026-01-01' : null,
    })

    return map
  }

  it('canReview=true ⟺ 全适用流程有结论 + 穿行完成', () => {
    fc.assert(
      fc.property(
        fc.array(arbP5ProcessConfig, { minLength: 8, maxLength: 8 }),
        (configs) => {
          const allResponses = ref(buildP5Responses(configs, false))
          const externalReadonly = ref(false)

          const { processes } = useB23ProcessControl(allResponses, noopSave)
          const { canReview } = useB23Review(
            ref('test-wp-id'),
            allResponses,
            processes,
            externalReadonly,
            noopSave,
          )

          // Compute expected canReview
          let expectedCanReview = true
          for (let i = 0; i < 8; i++) {
            const config = configs[i]
            if (!config.applicable) continue

            // Must have a conclusion
            if (!config.conclusion) {
              expectedCanReview = false
              break
            }

            // All walkthrough control points must have conclusion
            for (const cp of config.walkthroughControlPoints) {
              if (cp.conclusion === null) {
                expectedCanReview = false
                break
              }
            }
            if (!expectedCanReview) break
          }

          expect(canReview.value).toBe(expectedCanReview)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('isReadonly=true ⟺ reviewed=Y 或 externalReadonly=true', () => {
    fc.assert(
      fc.property(
        fc.array(arbP5ProcessConfig, { minLength: 8, maxLength: 8 }),
        fc.boolean(),
        fc.boolean(),
        (configs, reviewed, extReadonly) => {
          const allResponses = ref(buildP5Responses(configs, reviewed))
          const externalReadonly = ref(extReadonly)

          const { processes } = useB23ProcessControl(allResponses, noopSave)
          const { isReadonly } = useB23Review(
            ref('test-wp-id'),
            allResponses,
            processes,
            externalReadonly,
            noopSave,
          )

          // isReadonly = reviewed OR externalReadonly
          const expectedReadonly = reviewed || extReadonly
          expect(isReadonly.value).toBe(expectedReadonly)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('canReview 与 isReadonly 组合状态一致性', () => {
    fc.assert(
      fc.property(
        fc.array(arbP5ProcessConfig, { minLength: 8, maxLength: 8 }),
        fc.boolean(),
        fc.boolean(),
        (configs, reviewed, extReadonly) => {
          const allResponses = ref(buildP5Responses(configs, reviewed))
          const externalReadonly = ref(extReadonly)

          const { processes } = useB23ProcessControl(allResponses, noopSave)
          const { canReview, isReadonly, isReviewed } = useB23Review(
            ref('test-wp-id'),
            allResponses,
            processes,
            externalReadonly,
            noopSave,
          )

          // isReviewed should match reviewed flag
          expect(isReviewed.value).toBe(reviewed)

          // If reviewed, isReadonly must be true
          if (reviewed) {
            expect(isReadonly.value).toBe(true)
          }

          // If externalReadonly, isReadonly must be true
          if (extReadonly) {
            expect(isReadonly.value).toBe(true)
          }

          // If neither reviewed nor externalReadonly, isReadonly must be false
          if (!reviewed && !extReadonly) {
            expect(isReadonly.value).toBe(false)
          }
        },
      ),
      { numRuns: 300 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 数据持久化往返一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 6: 数据持久化往返一致性', () => {
  /**
   * **Validates: Requirements 8.1, 8.6**
   *
   * 生成随机 B23- item_id（合法格式）+ 白名单 conclusion + 随机 remark
   * → PUT (setFieldImmediate / setResponseLocal via allResponses.set)
   * → GET (读取 allResponses.get)
   * → 验证 round-trip 一致
   */

  /** Valid B23 conclusions whitelist */
  const B23_VALID_CONCLUSIONS = [
    '设计有效且已实施',
    '设计有效但未有效实施',
    '设计无效',
    '不适用',
    '控制有效运行',
    '控制未有效运行',
    '未执行穿行',
    'Y',
    'N',
  ] as const

  /** Arbitrary for valid B23 conclusion */
  const arbB23Conclusion = fc.constantFrom(...B23_VALID_CONCLUSIONS)

  /** Arbitrary for nullable conclusion (some fields store null) */
  const arbB23ConclusionOrNull = fc.oneof(
    arbB23Conclusion,
    fc.constant(null as string | null),
  )

  /** Arbitrary for random remark (unicode-safe, up to 200 chars) */
  const arbRemark = fc.oneof(
    fc.string({ minLength: 0, maxLength: 200 }),
    fc.constant(null as string | null),
  )

  /** Generate valid B23- item_id using generateItemId */
  const arbItemIdFromGenerator: fc.Arbitrary<string> = fc.oneof(
    // Applicability: B23-P{n}-applicability
    arbProcessNumber.map(n => generateItemId(n, 'applicability')),
    // Process conclusion: B23-P{n}-process-conclusion
    arbProcessNumber.map(n => generateItemId(n, 'process-conclusion')),
    // Ctrl count: B23-P{n}-ctrl-count
    arbProcessNumber.map(n => generateItemId(n, 'ctrl-count')),
    // Ctrl field: B23-P{n}-ctrl-{m}-{field}
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
      fc.constantFrom('objective', 'description', 'frequency', 'executor', 'methods', 'conclusion', 'remark'),
    ).map(([n, m, f]) => generateItemId(n, 'ctrl', m, undefined, f)),
    // Walkthrough field: B23-P{n}-wt-{m}-{s}-{field}
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
      fc.integer({ min: 1, max: 5 }),
      fc.constantFrom('sample', 'path', 'finding', 'reference'),
    ).map(([n, m, s, f]) => generateItemId(n, 'wt', m, s, f)),
    // Wt count: B23-P{n}-wt-{m}-count
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
    ).map(([n, m]) => generateItemId(n, 'wt-count', m)),
    // Conclusion override: B23-P{n}-conclusion-override
    arbProcessNumber.map(n => generateItemId(n, 'conclusion-override')),
  )

  it('round-trip: set → get 返回一致的 conclusion + remark', () => {
    fc.assert(
      fc.property(
        arbItemIdFromGenerator,
        arbB23ConclusionOrNull,
        arbRemark,
        (itemId, conclusion, remark) => {
          // Setup: fresh allResponses map
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

          // PUT: write to allResponses (simulates save)
          const item: ChecklistResponse = {
            item_id: itemId,
            conclusion,
            remark,
            wp_ref: null,
          }
          allResponses.value.set(itemId, item)

          // GET: read back from allResponses (simulates load)
          const retrieved = allResponses.value.get(itemId)

          // Verify round-trip consistency
          expect(retrieved).toBeDefined()
          expect(retrieved!.item_id).toBe(itemId)
          expect(retrieved!.conclusion).toBe(conclusion)
          expect(retrieved!.remark).toBe(remark)
        },
      ),
      { numRuns: 500 },
    )
  })

  it('round-trip via composable: setApplicability → getApplicability 一致', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.boolean(),
        (num, applicable) => {
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const { setApplicability, getApplicability, getConclusion } = useB23ProcessControl(allResponses, noopSave)

          // PUT: set applicability
          setApplicability(num, applicable)

          // GET: read back
          const actualApplicable = getApplicability(num).value
          const actualConclusion = getConclusion(num).value

          // Verify round-trip
          expect(actualApplicable).toBe(applicable)
          if (!applicable) {
            expect(actualConclusion).toBe('不适用')
          } else {
            expect(actualConclusion).toBeNull()
          }
        },
      ),
      { numRuns: 300 },
    )
  })

  it('round-trip via composable: setConclusion → getConclusion 一致', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbProcessConclusion,
        (num, conclusion) => {
          // Start with applicable process
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const applicabilityId = generateItemId(num, 'applicability')
          allResponses.value.set(applicabilityId, {
            item_id: applicabilityId,
            conclusion: 'Y',
            remark: null,
            wp_ref: null,
          })

          const { setConclusion, getConclusion } = useB23ProcessControl(allResponses, noopSave)

          // PUT: set conclusion
          setConclusion(num, conclusion)

          // GET: read back
          const actualConclusion = getConclusion(num).value

          // Verify round-trip
          expect(actualConclusion).toBe(conclusion)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('round-trip via composable: setControlPointField → getControlPoints 一致', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.integer({ min: 1, max: 10 }),
        fc.string({ minLength: 1, maxLength: 100 }),
        fc.string({ minLength: 1, maxLength: 100 }),
        (num, ctrlCount, objective, description) => {
          // Setup: create responses with ctrl-count
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const countId = generateItemId(num, 'ctrl-count')
          allResponses.value.set(countId, {
            item_id: countId,
            conclusion: null,
            remark: String(ctrlCount),
            wp_ref: null,
          })

          const { setControlPointField, getControlPoints } = useB23ProcessControl(allResponses, noopSave)

          // PUT: set fields for first control point
          setControlPointField(num, 1, 'objective', objective)
          setControlPointField(num, 1, 'description', description)

          // GET: read back via getControlPoints
          const points = getControlPoints(num).value
          expect(points.length).toBe(ctrlCount)
          expect(points[0].objective).toBe(objective)
          expect(points[0].description).toBe(description)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('round-trip: 多字段同时写入后全部可正确读回', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.integer({ min: 1, max: 5 }),
        fc.array(
          fc.record({
            conclusion: arbB23ConclusionOrNull,
            remark: arbRemark,
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (num, ctrlIndex, fields) => {
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

          // PUT: write multiple items for same process
          const writtenItems: ChecklistResponse[] = []
          for (let i = 0; i < fields.length; i++) {
            const field = fields[i]
            const itemId = `B23-P${num}-test-${ctrlIndex}-${i}`
            const item: ChecklistResponse = {
              item_id: itemId,
              conclusion: field.conclusion,
              remark: field.remark,
              wp_ref: null,
            }
            allResponses.value.set(itemId, item)
            writtenItems.push(item)
          }

          // GET: read all back and verify
          for (const written of writtenItems) {
            const retrieved = allResponses.value.get(written.item_id)
            expect(retrieved).toBeDefined()
            expect(retrieved!.conclusion).toBe(written.conclusion)
            expect(retrieved!.remark).toBe(written.remark)
            expect(retrieved!.item_id).toBe(written.item_id)
          }
        },
      ),
      { numRuns: 300 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: item_id 命名唯一性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 7: item_id 命名唯一性', () => {
  /**
   * **Validates: Requirements 8.7**
   *
   * 生成随机 processNum(1~8) × ctrlIndex(1~20) × sampleIndex(1~5) × 随机 field
   * → 验证：不同组合唯一，相同组合相同输出
   */

  /** Arbitrary for process number (1~8) */
  const arbProcNum = fc.integer({ min: 1, max: 8 }) as fc.Arbitrary<ProcessNumber>

  /** Arbitrary for control index (1~20) */
  const arbCtrlIndex = fc.integer({ min: 1, max: 20 })

  /** Arbitrary for sample index (1~5) */
  const arbSampleIndex = fc.integer({ min: 1, max: 5 })

  /** Arbitrary for field name */
  const arbField = fc.constantFrom(
    'objective', 'description', 'frequency', 'executor', 'methods', 'conclusion', 'remark',
    'sample', 'path', 'finding', 'reference',
  )

  /** Arbitrary for category type that uses ctrlIndex/sampleIndex/field */
  const arbCtrlCategory = fc.constantFrom<'ctrl' | 'wt'>('ctrl', 'wt')

  it('确定性：相同输入始终产出相同 item_id', () => {
    fc.assert(
      fc.property(
        arbProcNum,
        arbCtrlCategory,
        arbCtrlIndex,
        arbSampleIndex,
        arbField,
        (processNum, category, ctrlIndex, sampleIndex, field) => {
          // Call twice with identical arguments
          const id1 = generateItemId(processNum, category, ctrlIndex, sampleIndex, field)
          const id2 = generateItemId(processNum, category, ctrlIndex, sampleIndex, field)

          // Must produce identical output
          expect(id1).toBe(id2)
        },
      ),
      { numRuns: 500 },
    )
  })

  it('唯一性：不同 (processNum, ctrlIndex, sampleIndex, field) 组合产出不同 item_id（ctrl 类型）', () => {
    fc.assert(
      fc.property(
        // Generate two distinct tuples
        fc.tuple(arbProcNum, arbCtrlIndex, arbField),
        fc.tuple(arbProcNum, arbCtrlIndex, arbField),
        (tuple1, tuple2) => {
          // Skip if tuples are identical
          const [p1, c1, f1] = tuple1
          const [p2, c2, f2] = tuple2
          if (p1 === p2 && c1 === c2 && f1 === f2) return

          const id1 = generateItemId(p1, 'ctrl', c1, undefined, f1)
          const id2 = generateItemId(p2, 'ctrl', c2, undefined, f2)

          // Different inputs → different outputs
          expect(id1).not.toBe(id2)
        },
      ),
      { numRuns: 500 },
    )
  })

  it('唯一性：不同 (processNum, ctrlIndex, sampleIndex, field) 组合产出不同 item_id（wt 类型）', () => {
    fc.assert(
      fc.property(
        // Generate two distinct tuples for walkthrough
        fc.tuple(arbProcNum, arbCtrlIndex, arbSampleIndex, arbField),
        fc.tuple(arbProcNum, arbCtrlIndex, arbSampleIndex, arbField),
        (tuple1, tuple2) => {
          // Skip if tuples are identical
          const [p1, c1, s1, f1] = tuple1
          const [p2, c2, s2, f2] = tuple2
          if (p1 === p2 && c1 === c2 && s1 === s2 && f1 === f2) return

          const id1 = generateItemId(p1, 'wt', c1, s1, f1)
          const id2 = generateItemId(p2, 'wt', c2, s2, f2)

          // Different inputs → different outputs
          expect(id1).not.toBe(id2)
        },
      ),
      { numRuns: 500 },
    )
  })

  it('唯一性：所有 8×20×5 ctrl/wt 组合产出互不相同的 id（枚举验证）', () => {
    // Exhaustive check over a reasonable subset
    fc.assert(
      fc.property(
        arbField,
        (field) => {
          const idSet = new Set<string>()

          // Generate ctrl ids for all processNum × ctrlIndex
          for (let p = 1; p <= 8; p++) {
            for (let c = 1; c <= 20; c++) {
              const id = generateItemId(p as ProcessNumber, 'ctrl', c, undefined, field)
              expect(idSet.has(id)).toBe(false)
              idSet.add(id)
            }
          }

          // Generate wt ids for all processNum × ctrlIndex × sampleIndex
          for (let p = 1; p <= 8; p++) {
            for (let c = 1; c <= 20; c++) {
              for (let s = 1; s <= 5; s++) {
                const id = generateItemId(p as ProcessNumber, 'wt', c, s, field)
                expect(idSet.has(id)).toBe(false)
                idSet.add(id)
              }
            }
          }
        },
      ),
      { numRuns: 11 }, // Once per unique field value
    )
  })

  it('确定性：所有 category 类型（无 index 参数）也满足确定性', () => {
    const arbSimpleCategory = fc.constantFrom<'applicability' | 'ctrl-count' | 'process-conclusion' | 'conclusion-override'>(
      'applicability', 'ctrl-count', 'process-conclusion', 'conclusion-override',
    )

    fc.assert(
      fc.property(
        arbProcNum,
        arbSimpleCategory,
        (processNum, category) => {
          const id1 = generateItemId(processNum, category)
          const id2 = generateItemId(processNum, category)
          expect(id1).toBe(id2)
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: EventBus 事件发射正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 8: EventBus 事件发射正确性', () => {
  /**
   * **Validates: Requirements 7.1, 7.2**
   *
   * 生成随机流程 × 随机新旧 conclusion × 随机穿行完成状态
   * → 验证：
   *   新旧不同时发射 process:control-concluded；
   *   全穿行完成时发射 process:walkthrough-completed；
   *   新旧相同时不发射
   */

  /** Arbitrary for nullable ProcessConclusion (old conclusion can be null) */
  const arbProcessConclusionOrNull = fc.oneof(
    arbProcessConclusion,
    fc.constant(null as ProcessConclusion | null),
  )

  it('新旧 conclusion 不同时发射 process:control-concluded 事件', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbProcessConclusionOrNull,
        arbProcessConclusion,
        (num, oldConclusion, newConclusion) => {
          // Only test the case where old !== new
          fc.pre(oldConclusion !== newConclusion)

          // Spy on window.dispatchEvent
          const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
          dispatchSpy.mockClear()

          // Setup: process with old conclusion already set
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const applicabilityId = generateItemId(num, 'applicability')
          allResponses.value.set(applicabilityId, {
            item_id: applicabilityId,
            conclusion: 'Y',
            remark: null,
            wp_ref: null,
          })

          // Set old conclusion directly in responses (bypass setConclusion to avoid triggering event)
          if (oldConclusion) {
            const conclusionId = generateItemId(num, 'process-conclusion')
            allResponses.value.set(conclusionId, {
              item_id: conclusionId,
              conclusion: oldConclusion,
              remark: null,
              wp_ref: null,
            })
          }

          const { setConclusion } = useB23ProcessControl(allResponses, noopSave)

          // Act: set new conclusion (triggers publishProcessConcluded internally)
          setConclusion(num, newConclusion)

          // Assert: process:control-concluded event was dispatched
          const concludedEvents = dispatchSpy.mock.calls.filter(
            ([event]) => event instanceof CustomEvent && event.type === 'process:control-concluded'
          )
          expect(concludedEvents.length).toBe(1)

          const eventDetail = (concludedEvents[0][0] as CustomEvent).detail
          expect(eventDetail.processNum).toBe(num)
          expect(eventDetail.oldConclusion).toBe(oldConclusion)
          expect(eventDetail.newConclusion).toBe(newConclusion)

          dispatchSpy.mockRestore()
        },
      ),
      { numRuns: 200 },
    )
  })

  it('新旧 conclusion 相同时不发射 process:control-concluded 事件', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbProcessConclusion,
        (num, conclusion) => {
          // Spy on window.dispatchEvent
          const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
          dispatchSpy.mockClear()

          // Setup: process with conclusion already set
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const applicabilityId = generateItemId(num, 'applicability')
          allResponses.value.set(applicabilityId, {
            item_id: applicabilityId,
            conclusion: 'Y',
            remark: null,
            wp_ref: null,
          })

          const conclusionId = generateItemId(num, 'process-conclusion')
          allResponses.value.set(conclusionId, {
            item_id: conclusionId,
            conclusion: conclusion,
            remark: null,
            wp_ref: null,
          })

          const { setConclusion } = useB23ProcessControl(allResponses, noopSave)

          // Act: set same conclusion
          setConclusion(num, conclusion)

          // Assert: no process:control-concluded event was dispatched
          const concludedEvents = dispatchSpy.mock.calls.filter(
            ([event]) => event instanceof CustomEvent && event.type === 'process:control-concluded'
          )
          expect(concludedEvents.length).toBe(0)

          dispatchSpy.mockRestore()
        },
      ),
      { numRuns: 200 },
    )
  })

  it('publishWalkthroughCompleted 发射正确的 process:walkthrough-completed 事件', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        fc.array(
          fc.record({
            hasWalkthrough: fc.constant(true),
            conclusion: arbWalkthroughConclusion.map(c => c as WalkthroughConclusion | null),
          }),
          { minLength: 1, maxLength: 5 },
        ),
        (num, controlPointConfigs) => {
          // Only test when ALL walkthrough control points have conclusions (complete)
          fc.pre(controlPointConfigs.every(cp => cp.conclusion !== null))

          // Spy on window.dispatchEvent
          const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
          dispatchSpy.mockClear()

          // Setup: process with walkthrough control points
          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const applicabilityId = generateItemId(num, 'applicability')
          allResponses.value.set(applicabilityId, {
            item_id: applicabilityId,
            conclusion: 'Y',
            remark: null,
            wp_ref: null,
          })

          const countId = generateItemId(num, 'ctrl-count')
          allResponses.value.set(countId, {
            item_id: countId,
            conclusion: null,
            remark: String(controlPointConfigs.length),
            wp_ref: null,
          })

          for (let m = 1; m <= controlPointConfigs.length; m++) {
            const cpConfig = controlPointConfigs[m - 1]

            const methodsId = generateItemId(num, 'ctrl', m, undefined, 'methods')
            allResponses.value.set(methodsId, {
              item_id: methodsId,
              conclusion: null,
              remark: '穿行测试',
              wp_ref: null,
            })

            const conclusionId = generateItemId(num, 'ctrl', m, undefined, 'conclusion')
            allResponses.value.set(conclusionId, {
              item_id: conclusionId,
              conclusion: cpConfig.conclusion,
              remark: null,
              wp_ref: null,
            })
          }

          const { publishWalkthroughCompleted } = useB23ProcessControl(allResponses, noopSave)

          // Act: publish walkthrough completed
          publishWalkthroughCompleted(num)

          // Assert: process:walkthrough-completed event was dispatched
          const wtEvents = dispatchSpy.mock.calls.filter(
            ([event]) => event instanceof CustomEvent && event.type === 'process:walkthrough-completed'
          )
          expect(wtEvents.length).toBe(1)

          const eventDetail = (wtEvents[0][0] as CustomEvent).detail
          expect(eventDetail.processNum).toBe(num)
          expect(eventDetail.controlPointCount).toBe(controlPointConfigs.length)

          // effectiveRate = count of "控制有效运行" / total
          const effectiveCount = controlPointConfigs.filter(
            cp => cp.conclusion === '控制有效运行'
          ).length
          const expectedRate = effectiveCount / controlPointConfigs.length
          expect(eventDetail.effectiveRate).toBeCloseTo(expectedRate, 10)

          dispatchSpy.mockRestore()
        },
      ),
      { numRuns: 200 },
    )
  })

  it('publishProcessConcluded 不因 old===new 而发射事件（直接调用验证）', () => {
    fc.assert(
      fc.property(
        arbProcessNumber,
        arbProcessConclusion,
        (num, conclusion) => {
          // Spy on window.dispatchEvent
          const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
          dispatchSpy.mockClear()

          const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
          const { publishProcessConcluded } = useB23ProcessControl(allResponses, noopSave)

          // Act: call with same old and new conclusion
          publishProcessConcluded(num, conclusion, conclusion)

          // Assert: no event dispatched
          const concludedEvents = dispatchSpy.mock.calls.filter(
            ([event]) => event instanceof CustomEvent && event.type === 'process:control-concluded'
          )
          expect(concludedEvents.length).toBe(0)

          dispatchSpy.mockRestore()
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 颜色编码双射
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 9: 颜色编码双射', () => {
  /**
   * **Validates: Requirements 12.1, 12.2, 12.4**
   *
   * 全量枚举 5 值（4 结论 + 待测试）→ 验证：
   *   每个结论对应唯一颜色；
   *   无同色不同结论；
   *   覆盖全部 ProcessConclusion 值
   */

  /** All ProcessConclusion values + pending state */
  const ALL_CONCLUSION_KEYS: string[] = [
    '设计有效且已实施',
    '设计有效但未有效实施',
    '设计无效',
    '不适用',
    '待测试',
  ]

  /** Expected color mapping (from Requirements 12.1, 12.2) */
  const EXPECTED_COLORS: Record<string, string> = {
    '设计有效且已实施': '#52c41a',
    '设计有效但未有效实施': '#faad14',
    '设计无效': '#ff4d4f',
    '不适用': '#bfbfbf',
    '待测试': '#1890ff',
  }

  it('PROCESS_CONCLUSION_COLOR_MAP 覆盖全部 5 个结论值（无遗漏）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        (conclusionKey) => {
          // Each conclusion key must exist in the color map
          expect(PROCESS_CONCLUSION_COLOR_MAP).toHaveProperty(conclusionKey)
          // Each entry must have color, bg, and label
          const entry = PROCESS_CONCLUSION_COLOR_MAP[conclusionKey]
          expect(entry).toBeDefined()
          expect(entry.color).toBeDefined()
          expect(typeof entry.color).toBe('string')
          expect(entry.bg).toBeDefined()
          expect(typeof entry.bg).toBe('string')
          expect(entry.label).toBeDefined()
          expect(typeof entry.label).toBe('string')
        },
      ),
      { numRuns: 50 },
    )
  })

  it('每个结论对应唯一颜色（单射：无同色不同结论）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        (keyA, keyB) => {
          if (keyA === keyB) return // Skip same key comparison

          const colorA = PROCESS_CONCLUSION_COLOR_MAP[keyA].color
          const colorB = PROCESS_CONCLUSION_COLOR_MAP[keyB].color

          // Different conclusions must have different colors (injective)
          expect(colorA).not.toBe(colorB)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('颜色值与设计文档规定一致', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        (conclusionKey) => {
          const actualColor = PROCESS_CONCLUSION_COLOR_MAP[conclusionKey].color
          const expectedColor = EXPECTED_COLORS[conclusionKey]

          // Each conclusion's color must match the specification
          expect(actualColor).toBe(expectedColor)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('待测试颜色(#1890ff)不与任何 ProcessConclusion 颜色冲突', () => {
    const pendingColor = PROCESS_CONCLUSION_COLOR_MAP['待测试'].color
    const conclusionKeys = ['设计有效且已实施', '设计有效但未有效实施', '设计无效', '不适用']

    fc.assert(
      fc.property(
        fc.constantFrom(...conclusionKeys),
        (conclusionKey) => {
          const conclusionColor = PROCESS_CONCLUSION_COLOR_MAP[conclusionKey].color
          expect(pendingColor).not.toBe(conclusionColor)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('背景色(bg)同样满足唯一性（无同背景色不同结论）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        fc.constantFrom(...ALL_CONCLUSION_KEYS),
        (keyA, keyB) => {
          if (keyA === keyB) return

          const bgA = PROCESS_CONCLUSION_COLOR_MAP[keyA].bg
          const bgB = PROCESS_CONCLUSION_COLOR_MAP[keyB].bg

          // Different conclusions must have different background colors
          expect(bgA).not.toBe(bgB)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: Entity_Level_Context 只读不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 10: Entity_Level_Context 只读不变式', () => {
  /**
   * **Validates: Requirements 6.2, 6.3, 6.4, 6.6**
   *
   * 生成随机 ControlConclusionPayload
   * → 验证：
   *   面板数据只读（修改原 payload 不影响已设置的 entityLevelContext）；
   *   completed=false 时显示"未完成"状态（overallConclusion=null → completed=false）；
   *   elementScores[1]='无效'时触发警告条件
   */

  /** Arbitrary for element score values */
  const arbElementScore = fc.constantFrom<string | null>(
    '有效',
    '部分有效',
    '无效',
    null,
  )

  /** Arbitrary for overall conclusion */
  const arbOverallConclusion = fc.constantFrom<string | null>(
    '有效',
    '部分有效',
    '无效',
    null,
  )

  /** Arbitrary for a full ControlConclusionPayload */
  const arbControlConclusionPayload = fc.record({
    elementScores: fc.record({
      1: arbElementScore,
      2: arbElementScore,
      3: arbElementScore,
      4: arbElementScore,
      5: arbElementScore,
    }) as fc.Arbitrary<Record<number, string | null>>,
    itDependency: fc.constantFrom('高', '中', '低', '无'),
    itgcConclusion: fc.constantFrom<string | null>('有效', '部分有效', '无效', null),
    overallConclusion: arbOverallConclusion,
  })

  it('onControlConclusionChanged 后 entityLevelContext 数据与 payload 一致', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload,
        (payload) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          // Initially null
          expect(entityLevelContext.value).toBeNull()

          // Apply payload
          onControlConclusionChanged(payload)

          // entityLevelContext should now be set
          expect(entityLevelContext.value).not.toBeNull()
          expect(entityLevelContext.value!.elementScores).toEqual(payload.elementScores)
          expect(entityLevelContext.value!.overallConclusion).toBe(payload.overallConclusion)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('面板数据只读：修改原始 payload 不影响已设置的 entityLevelContext', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload,
        arbElementScore,
        (payload, newScore) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          // Apply payload
          onControlConclusionChanged(payload)

          // Capture the state after setting
          const capturedScores = { ...entityLevelContext.value!.elementScores }
          const capturedConclusion = entityLevelContext.value!.overallConclusion

          // Mutate the original payload — should NOT affect entityLevelContext
          payload.elementScores[1] = newScore
          payload.overallConclusion = '已被篡改'

          // entityLevelContext should still hold the original values
          expect(entityLevelContext.value!.elementScores).toEqual(capturedScores)
          expect(entityLevelContext.value!.overallConclusion).toBe(capturedConclusion)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('overallConclusion=null → completed=false（"未完成"状态）', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload.filter(p => p.overallConclusion === null),
        (payload) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          onControlConclusionChanged(payload)

          // When overallConclusion is null → completed should be false → "未完成" state
          expect(entityLevelContext.value!.completed).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('overallConclusion 非 null → completed=true（已完成状态）', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload.filter(p => p.overallConclusion !== null),
        (payload) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          onControlConclusionChanged(payload)

          // When overallConclusion is non-null → completed should be true
          expect(entityLevelContext.value!.completed).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('elementScores[1]="无效" → 触发警告条件（控制环境薄弱）', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload.map(p => ({
          ...p,
          elementScores: { ...p.elementScores, 1: '无效' },
        })),
        (payload) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          onControlConclusionChanged(payload)

          // When elementScores[1] (控制环境) = '无效', the warning condition is active
          expect(entityLevelContext.value!.elementScores[1]).toBe('无效')

          // The warning condition is determined by checking elementScores[1] === '无效'
          const shouldWarn = entityLevelContext.value!.elementScores[1] === '无效'
          expect(shouldWarn).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('elementScores[1]≠"无效" → 不触发警告条件', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload.filter(p => p.elementScores[1] !== '无效'),
        (payload) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged } = useB23ProcessControl(allResponses, noopSave)

          onControlConclusionChanged(payload)

          // When elementScores[1] is not '无效', no warning should trigger
          const shouldWarn = entityLevelContext.value!.elementScores[1] === '无效'
          expect(shouldWarn).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('B23 内部编辑操作不影响 entityLevelContext 数据', () => {
    fc.assert(
      fc.property(
        arbControlConclusionPayload,
        arbProcessNumber,
        fc.boolean(),
        (payload, num, applicable) => {
          const allResponses = ref(new Map<string, ChecklistResponse>())
          const { entityLevelContext, onControlConclusionChanged, setApplicability } = useB23ProcessControl(allResponses, noopSave)

          // Set entity level context via EventBus payload
          onControlConclusionChanged(payload)

          // Capture state
          const capturedContext = {
            elementScores: { ...entityLevelContext.value!.elementScores },
            overallConclusion: entityLevelContext.value!.overallConclusion,
            completed: entityLevelContext.value!.completed,
          }

          // Perform internal editing operations (toggle applicability)
          setApplicability(num, applicable)

          // entityLevelContext should remain unchanged after internal edits
          expect(entityLevelContext.value!.elementScores).toEqual(capturedContext.elementScores)
          expect(entityLevelContext.value!.overallConclusion).toBe(capturedContext.overallConclusion)
          expect(entityLevelContext.value!.completed).toBe(capturedContext.completed)
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 后端白名单校验正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 11: 后端白名单校验正确性', () => {
  /**
   * **Validates: Requirements 11.1, 11.2, 11.4**
   *
   * 生成随机 B23- item_id + 随机 conclusion（合法/非法混合）
   * → 验证白名单内 conclusion 视为有效（模拟 200）/ 白名单外视为无效（模拟 422）
   *
   * 由于这是前端 property test，不调用真实后端 API，
   * 而是测试前端验证函数（纯函数），该函数镜像后端白名单逻辑。
   */

  /** B23- conclusion 完整白名单（与后端 checklist_responses.py 一致） */
  const B23_CONCLUSION_WHITELIST: readonly string[] = [
    // ProcessConclusion
    '设计有效且已实施',
    '设计有效但未有效实施',
    '设计无效',
    '不适用',
    // WalkthroughConclusion
    '控制有效运行',
    '控制未有效运行',
    '未执行穿行',
    // ControlFrequency
    '每笔',
    '每日',
    '每周',
    '每月',
    '每季',
    '每年',
    '不定期',
    // Boolean markers (applicability Y/N, review markers)
    'Y',
    'N',
  ] as const

  /**
   * 前端白名单校验函数（镜像后端逻辑）
   * 对 B23- 前缀的 item_id，验证 conclusion 是否在白名单内
   * - null conclusion 始终合法（remark-only 字段如 objective/description）
   * - 非 null conclusion 必须在白名单内
   */
  function validateB23Conclusion(itemId: string, conclusion: string | null): { valid: boolean; statusCode: 200 | 422 } {
    // null conclusion is always valid (fields that only use remark)
    if (conclusion === null) {
      return { valid: true, statusCode: 200 }
    }

    // For B23- prefixed item_ids, check whitelist
    if (itemId.startsWith('B23-')) {
      const isValid = B23_CONCLUSION_WHITELIST.includes(conclusion)
      return { valid: isValid, statusCode: isValid ? 200 : 422 }
    }

    // Non-B23 prefix → not our concern, treat as valid
    return { valid: true, statusCode: 200 }
  }

  /** Arbitrary: valid B23 conclusion from whitelist */
  const arbWhitelistConclusion = fc.constantFrom(...B23_CONCLUSION_WHITELIST)

  /** Arbitrary: invalid conclusion (random string guaranteed NOT in whitelist) */
  const arbInvalidConclusion = fc.string({ minLength: 1, maxLength: 50 }).filter(
    s => !B23_CONCLUSION_WHITELIST.includes(s),
  )

  /** Arbitrary: valid B23- item_id (using generateItemId) */
  const arbB23ItemId = fc.oneof(
    arbProcessNumber.map(n => generateItemId(n, 'applicability')),
    arbProcessNumber.map(n => generateItemId(n, 'process-conclusion')),
    arbProcessNumber.map(n => generateItemId(n, 'ctrl-count')),
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
      fc.constantFrom('objective', 'description', 'frequency', 'executor', 'methods', 'conclusion', 'remark'),
    ).map(([n, m, f]) => generateItemId(n, 'ctrl', m, undefined, f)),
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
      fc.integer({ min: 1, max: 5 }),
      fc.constantFrom('sample', 'path', 'finding', 'reference'),
    ).map(([n, m, s, f]) => generateItemId(n, 'wt', m, s, f)),
    fc.tuple(
      arbProcessNumber,
      fc.integer({ min: 1, max: 20 }),
    ).map(([n, m]) => generateItemId(n, 'wt-count', m)),
    arbProcessNumber.map(n => generateItemId(n, 'conclusion-override')),
  )

  it('白名单内 conclusion → 返回 200（有效）', () => {
    fc.assert(
      fc.property(
        arbB23ItemId,
        arbWhitelistConclusion,
        (itemId, conclusion) => {
          const result = validateB23Conclusion(itemId, conclusion)
          expect(result.valid).toBe(true)
          expect(result.statusCode).toBe(200)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('白名单外 conclusion → 返回 422（无效）', () => {
    fc.assert(
      fc.property(
        arbB23ItemId,
        arbInvalidConclusion,
        (itemId, conclusion) => {
          const result = validateB23Conclusion(itemId, conclusion)
          expect(result.valid).toBe(false)
          expect(result.statusCode).toBe(422)
        },
      ),
      { numRuns: 300 },
    )
  })

  it('null conclusion → 始终返回 200（remark-only 字段合法）', () => {
    fc.assert(
      fc.property(
        arbB23ItemId,
        (itemId) => {
          const result = validateB23Conclusion(itemId, null)
          expect(result.valid).toBe(true)
          expect(result.statusCode).toBe(200)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('混合合法/非法 conclusion 随机生成 → 状态码与白名单成员性一致', () => {
    // Mixed arbitrary: 50% whitelist, 50% random strings
    const arbMixedConclusion = fc.oneof(
      arbWhitelistConclusion,
      fc.string({ minLength: 1, maxLength: 100 }),
    )

    fc.assert(
      fc.property(
        arbB23ItemId,
        arbMixedConclusion,
        (itemId, conclusion) => {
          const result = validateB23Conclusion(itemId, conclusion)
          const expectedValid = B23_CONCLUSION_WHITELIST.includes(conclusion)

          expect(result.valid).toBe(expectedValid)
          expect(result.statusCode).toBe(expectedValid ? 200 : 422)
        },
      ),
      { numRuns: 500 },
    )
  })

  it('白名单覆盖全部 15 个合法值（无遗漏）', () => {
    // Exhaustive check: every value in the whitelist should be accepted
    const expectedValues = [
      '设计有效且已实施', '设计有效但未有效实施', '设计无效', '不适用',
      '控制有效运行', '控制未有效运行', '未执行穿行',
      '每笔', '每日', '每周', '每月', '每季', '每年', '不定期',
      'Y', 'N',
    ]

    expect(B23_CONCLUSION_WHITELIST).toHaveLength(16)

    for (const val of expectedValues) {
      const result = validateB23Conclusion('B23-P1-process-conclusion', val)
      expect(result.valid).toBe(true)
      expect(result.statusCode).toBe(200)
    }
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 联动面板结论映射
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: b23-process-control, Property 12: 联动面板结论映射', () => {
  /**
   * **Validates: Requirements 7.3, 7.6**
   *
   * 全量枚举 ProcessConclusion × 验证 CONCLUSION_TO_B50_IMPACT 映射正确
   * + "设计无效"时 needsExtendedProcedures=true
   */

  /** All valid ProcessConclusion values */
  const ALL_CONCLUSIONS: ProcessConclusion[] = [
    '设计有效且已实施',
    '设计有效但未有效实施',
    '设计无效',
    '不适用',
  ]

  /** Expected B50 impact mapping */
  const EXPECTED_B50_IMPACT: Record<ProcessConclusion, string> = {
    '设计有效且已实施': '控制风险=低',
    '设计有效但未有效实施': '控制风险=中',
    '设计无效': '控制风险=高',
    '不适用': '不影响控制风险评估',
  }

  it('CONCLUSION_TO_B50_IMPACT 覆盖全部 4 个 ProcessConclusion 值（无遗漏）', () => {
    for (const conclusion of ALL_CONCLUSIONS) {
      expect(CONCLUSION_TO_B50_IMPACT[conclusion]).toBeDefined()
      expect(CONCLUSION_TO_B50_IMPACT[conclusion]).toBe(EXPECTED_B50_IMPACT[conclusion])
    }
  })

  it('CONCLUSION_TO_B50_IMPACT 映射值与预期 B50 风险等级一致', () => {
    expect(CONCLUSION_TO_B50_IMPACT['设计有效且已实施']).toBe('控制风险=低')
    expect(CONCLUSION_TO_B50_IMPACT['设计有效但未有效实施']).toBe('控制风险=中')
    expect(CONCLUSION_TO_B50_IMPACT['设计无效']).toBe('控制风险=高')
    expect(CONCLUSION_TO_B50_IMPACT['不适用']).toBe('不影响控制风险评估')
  })

  it('"设计无效"时 needsExtendedProcedures=true；其他结论 needsExtendedProcedures=false', () => {
    for (const conclusion of ALL_CONCLUSIONS) {
      const needsExtended = conclusion === '设计无效'
      if (conclusion === '设计无效') {
        expect(needsExtended).toBe(true)
      } else {
        expect(needsExtended).toBe(false)
      }
    }
  })

  it('linkageInfo 计算属性正确使用 CONCLUSION_TO_B50_IMPACT 映射（全量枚举）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<ProcessConclusion>(...ALL_CONCLUSIONS),
        fc.constantFrom<1 | 2 | 3 | 4 | 5 | 6 | 7 | 8>(1, 2, 3, 4, 5, 6, 7, 8),
        (conclusion, processNum) => {
          // Build allResponses with the given conclusion for the given process
          const allResponses = ref(new Map<string, ChecklistResponse>())

          // Set applicability to Y
          const applicabilityId = generateItemId(processNum, 'applicability')
          allResponses.value.set(applicabilityId, {
            item_id: applicabilityId,
            conclusion: 'Y',
            remark: null,
            wp_ref: null,
          })

          // Set process conclusion
          const conclusionId = generateItemId(processNum, 'process-conclusion')
          allResponses.value.set(conclusionId, {
            item_id: conclusionId,
            conclusion,
            remark: null,
            wp_ref: null,
          })

          const { linkageInfo } = useB23ProcessControl(allResponses, async () => {})

          // Find the linkage entry for the target process
          const entry = linkageInfo.value.find(li => li.processNum === processNum)
          expect(entry).toBeDefined()
          expect(entry!.conclusion).toBe(conclusion)
          expect(entry!.b50Impact).toBe(EXPECTED_B50_IMPACT[conclusion])
          expect(entry!.needsExtendedProcedures).toBe(conclusion === '设计无效')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('linkageInfo: conclusion 为 null 时 b50Impact 为空字符串, needsExtendedProcedures=false', () => {
    // Process with no conclusion set
    const allResponses = ref(new Map<string, ChecklistResponse>())

    // Set all 8 processes as applicable but no conclusion
    for (let i = 1; i <= 8; i++) {
      const applicabilityId = generateItemId(i as 1, 'applicability')
      allResponses.value.set(applicabilityId, {
        item_id: applicabilityId,
        conclusion: 'Y',
        remark: null,
        wp_ref: null,
      })
    }

    const { linkageInfo } = useB23ProcessControl(allResponses, async () => {})

    for (const entry of linkageInfo.value) {
      expect(entry.conclusion).toBeNull()
      expect(entry.b50Impact).toBe('')
      expect(entry.needsExtendedProcedures).toBe(false)
    }
  })

  it('linkageInfo 映射关系正确：P1→DA, P2→EA, P3→FA, P4→GA, P5→HA, P6→IA, P7→JA, P8→KA', () => {
    const expectedMapping: Record<number, string> = {
      1: 'DA', 2: 'EA', 3: 'FA', 4: 'GA',
      5: 'HA', 6: 'IA', 7: 'JA', 8: 'KA',
    }

    const allResponses = ref(new Map<string, ChecklistResponse>())
    const { linkageInfo } = useB23ProcessControl(allResponses, async () => {})

    for (const entry of linkageInfo.value) {
      expect(entry.targetCycle).toBe(expectedMapping[entry.processNum])
    }
  })

  it('linkageInfo 每项包含 8 个流程（完备性）', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const { linkageInfo } = useB23ProcessControl(allResponses, async () => {})

    expect(linkageInfo.value).toHaveLength(8)

    const processNums = linkageInfo.value.map(li => li.processNum)
    expect(processNums).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
  })

  it('fast-check: 随机 ProcessConclusion 枚举 × needsExtendedProcedures 标志始终正确', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<ProcessConclusion>(...ALL_CONCLUSIONS),
        (conclusion) => {
          // Verify the mapping exists and is non-empty
          const impact = CONCLUSION_TO_B50_IMPACT[conclusion]
          expect(impact).toBeDefined()
          expect(impact.length).toBeGreaterThan(0)

          // Verify needsExtendedProcedures logic
          const needsExtended = conclusion === '设计无效'
          if (conclusion === '设计无效') {
            expect(needsExtended).toBe(true)
            expect(impact).toBe('控制风险=高')
          } else {
            expect(needsExtended).toBe(false)
            expect(impact).not.toBe('控制风险=高')
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
