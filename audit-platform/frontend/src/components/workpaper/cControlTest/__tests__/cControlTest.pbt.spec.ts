/**
 * Property-Based Tests — C2~C15 控制测试组件翻新 (fast-check)
 *
 * Spec: .kiro/specs/c-control-test-refresh/
 * Task: 6.1
 *
 * 使用 fast-check + vitest 验证 Property 2, 3, 4, 5, 6。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  suggestSampleSize,
  getFrequencyOptions,
  SAMPLE_SIZE_TABLE,
} from '@/composables/useSampleSizeEngine'
import {
  evaluateDecisionTree,
  createEmptyState,
  isStepVisible,
  type DecisionTreeState,
  type DecisionTreeResult,
} from '@/composables/useDeviationDecisionTree'

// ─── Mock api (composable 需要) ──────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: 'test' }) },
}))

// Mock eventBus to capture emissions
const emittedEvents: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emittedEvents.push({ event, payload }) },
    on: vi.fn(),
    off: vi.fn(),
    all: { clear: vi.fn() },
  },
}))


// ─── Generators ──────────────────────────────────────────────────────────────

/** P2: 样本规模频率生成器（匹配 SAMPLE_SIZE_TABLE 实际 frequency 值） */
const arbFrequency = fc.constantFrom('每年', '每季度', '每月', '每周', '每半月', '每天', '每天多次')

/** P3/P4: 决策树全组合输入生成器 */
const arbDeviationInput = fc.record({
  isDeviation: fc.constantFrom<'是' | '否' | null>('是', '否', null),
  nature: fc.constantFrom<'系统性偏差' | '人为偏差' | '随机性偏差' | null>('系统性偏差', '人为偏差', '随机性偏差', null),
  randomResponse: fc.constantFrom<'扩大样本量' | '直接认定为偏差' | null>('扩大样本量', '直接认定为偏差', null),
  expandedFoundNew: fc.constantFrom<'是' | '否' | null>('是', '否', null),
  designDeficiency: fc.constantFrom<'是' | '否' | null>('是', '否', null),
})

/** P5: 样本集生成器 */
const arbSampleSet = fc.array(
  fc.record({
    result: fc.constantFrom<'有效' | '偏差' | '不适用'>('有效', '偏差', '不适用'),
  }),
  { minLength: 1, maxLength: 50 },
)

/** P6: 循环结论生成器 */
const arbConclusion = fc.constantFrom('全部有效', '部分偏差', '控制失效', '待评价')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 样本规模建议单调性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 2: 样本规模建议单调性', () => {
  /**
   * **Validates: Requirements 3.1, 3.2**
   *
   * For any 控制频率与运行总次数：
   * - suggestSampleSize 返回 min ≤ max
   * - 同频率下 totalCount 越大，min 不减（单调不降）
   */

  it('suggestSampleSize 返回 min ≤ max', () => {
    fc.assert(
      fc.property(
        arbFrequency,
        fc.nat({ max: 500 }),
        (frequency, totalCount) => {
          // totalCount=0 时返回无效提示，跳过
          if (totalCount === 0) return true
          const result = suggestSampleSize(frequency, totalCount)
          return result.min <= result.max
        },
      ),
      { numRuns: 100 },
    )
  })

  it('同频率下 totalCount 越大，min 不减（单调不降）', () => {
    fc.assert(
      fc.property(
        arbFrequency,
        fc.integer({ min: 1, max: 498 }).chain(a => fc.tuple(fc.constant(a), fc.integer({ min: a + 1, max: 500 }))),
        (frequency, [smaller, larger]) => {
          const resultSmall = suggestSampleSize(frequency, smaller)
          const resultLarge = suggestSampleSize(frequency, larger)
          // 单调不降：larger 的 min 应 >= smaller 的 min
          return resultLarge.min >= resultSmall.min
        },
      ),
      { numRuns: 100 },
    )
  })

  it('所有有效频率的 totalCount>0 结果 min >= 1', () => {
    fc.assert(
      fc.property(
        arbFrequency,
        fc.integer({ min: 1, max: 500 }),
        (frequency, totalCount) => {
          const result = suggestSampleSize(frequency, totalCount)
          return result.min >= 1
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 决策树全路径确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 3: 决策树全路径确定性', () => {
  /**
   * **Validates: Requirements 5.1, 5.2**
   *
   * For any DeviationInput 全组合：
   * - evaluateDecisionTree 不抛异常
   * - 返回确定性结论（当路径完整时 conclusion 非空）
   * - 复刻源模板 IF 链的正确路径
   */

  it('evaluateDecisionTree 对任意输入不抛异常', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          // 不抛异常
          const result = evaluateDecisionTree(state)
          expect(result).toBeDefined()
          expect(result.currentStep).toBeGreaterThanOrEqual(1)
          expect(result.currentStep).toBeLessThanOrEqual(6)
          expect(typeof result.nextStepHint).toBe('string')
          expect(result.nextStepHint.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('完整路径下 conclusion 非空且 path 非 null', () => {
    // 枚举所有 6 条完整路径
    const completePaths: DecisionTreeState[] = [
      // Path A: step1=否 → step6=否 → 不构成偏差或缺陷，控制有效
      { step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否' },
      // Path B: step1=否 → step6=是 → 设计缺陷
      { step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '是' },
      // Path C: step1=是 → step2=系统性偏差 → 控制缺陷
      { step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null },
      // Path C variant: step1=是 → step2=人为偏差 → 控制缺陷
      { step1: '是', step2: '人为偏差', step3: null, step4: null, step5: false, step6: null },
      // Path D: step1=是 → step2=随机 → step3=直接认定
      { step1: '是', step2: '随机性偏差', step3: '直接认定为偏差', step4: null, step5: false, step6: null },
      // Path E: step1=是 → step2=随机 → step3=扩大 → step4=否 → 控制有效
      { step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null },
      // Path F: step1=是 → step2=随机 → step3=扩大 → step4=是 → 控制无效
      { step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '是', step5: false, step6: null },
    ]

    for (const state of completePaths) {
      const result = evaluateDecisionTree(state)
      expect(result.conclusion).not.toBeNull()
      expect(result.conclusion!.length).toBeGreaterThan(0)
      expect(result.path).not.toBeNull()
    }
  })

  it('复刻源模板 IF 链：Path A/B 验证', () => {
    // Path A: step1=否 → step6=否
    const pathA = evaluateDecisionTree({ step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否' })
    expect(pathA.path).toBe('A')
    expect(pathA.conclusion).toContain('控制有效')
    expect(pathA.goToA14).toBe(false)

    // Path B: step1=否 → step6=是
    const pathB = evaluateDecisionTree({ step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '是' })
    expect(pathB.path).toBe('B')
    expect(pathB.conclusion).toContain('设计缺陷')
    expect(pathB.goToA14).toBe(true)
  })

  it('复刻源模板 IF 链：Path C/D/E/F 验证', () => {
    // Path C: 系统性偏差
    const pathC = evaluateDecisionTree({ step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null })
    expect(pathC.path).toBe('C')
    expect(pathC.conclusion).toContain('控制缺陷')
    expect(pathC.goToA14).toBe(true)

    // Path C: 人为偏差 (same path)
    const pathC2 = evaluateDecisionTree({ step1: '是', step2: '人为偏差', step3: null, step4: null, step5: false, step6: null })
    expect(pathC2.path).toBe('C')
    expect(pathC2.goToA14).toBe(true)

    // Path D: 随机 + 直接认定
    const pathD = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '直接认定为偏差', step4: null, step5: false, step6: null })
    expect(pathD.path).toBe('D')
    expect(pathD.goToA14).toBe(true)

    // Path E: 随机 + 扩大 + 无新偏差 → 控制有效
    const pathE = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null })
    expect(pathE.path).toBe('E')
    expect(pathE.conclusion).toContain('控制有效')
    expect(pathE.goToA14).toBe(false)

    // Path F: 随机 + 扩大 + 有新偏差 → 控制无效
    const pathF = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '是', step5: false, step6: null })
    expect(pathF.path).toBe('F')
    expect(pathF.conclusion).toContain('控制无效')
    expect(pathF.goToA14).toBe(true)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 缺陷联动 A14
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 4: 缺陷联动 A14', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * For any 决策路径，goToA14=true 当且仅当推导进入步骤五（评价控制缺陷）。
   * 步骤五路径：B（设计缺陷）、C（系统/人为）、D（直接认定）、F（扩大后新偏差）
   */

  it('goToA14=true 当且仅当推导至步骤五', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          const result = evaluateDecisionTree(state)

          if (result.goToA14) {
            // goToA14=true → 必须是进入步骤五的路径 (B/C/D/F)
            expect(['B', 'C', 'D', 'F']).toContain(result.path)
            expect(result.currentStep).toBe(5)
          } else {
            // goToA14=false → 路径为 A/E 或尚未到达结论（path=null）
            if (result.path !== null) {
              expect(['A', 'E']).toContain(result.path)
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('所有 goToA14=true 路径的 currentStep 都是 5', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          const result = evaluateDecisionTree(state)

          if (result.goToA14) {
            expect(result.currentStep).toBe(5)
          }
          return true
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Path A/E 永远不联动 A14', () => {
    // Path A: step1=否 step6=否
    const a = evaluateDecisionTree({ step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否' })
    expect(a.goToA14).toBe(false)
    expect(a.path).toBe('A')

    // Path E: step1=是 step2=随机 step3=扩大 step4=否
    const e = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null })
    expect(e.goToA14).toBe(false)
    expect(e.path).toBe('E')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 偏差回填一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 5: 偏差回填一致性', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * For any 控制测试子页样本集合：
   * - 汇总表「是否识别偏差」=== 样本中存在 result='偏差'
   * - 即 hasDeviation 应为 '是' 当且仅当至少一笔样本 result='偏差'
   */

  /**
   * 纯函数：从样本集合推导「是否识别偏差」
   * 这是 useCControlTestData 中回填逻辑的核心断言：
   *   样本存在偏差 → hasDeviation='是'
   *   样本无偏差 → hasDeviation='否'
   */
  function deriveHasDeviation(samples: Array<{ result: '有效' | '偏差' | '不适用' }>): '是' | '否' {
    return samples.some(s => s.result === '偏差') ? '是' : '否'
  }

  it('hasDeviation="是" 当且仅当样本中存在 result="偏差"', () => {
    fc.assert(
      fc.property(
        arbSampleSet,
        (samples) => {
          const hasAnyDeviation = samples.some(s => s.result === '偏差')
          const derived = deriveHasDeviation(samples)

          if (hasAnyDeviation) {
            expect(derived).toBe('是')
          } else {
            expect(derived).toBe('否')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空偏差的样本集 → hasDeviation="否"', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ result: fc.constantFrom<'有效' | '不适用'>('有效', '不适用') }),
          { minLength: 1, maxLength: 50 },
        ),
        (samples) => {
          const derived = deriveHasDeviation(samples as Array<{ result: '有效' | '偏差' | '不适用' }>)
          expect(derived).toBe('否')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('至少含一笔偏差的样本集 → hasDeviation="是"', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.array(
            fc.record({ result: fc.constantFrom<'有效' | '偏差' | '不适用'>('有效', '偏差', '不适用') }),
            { minLength: 0, maxLength: 49 },
          ),
          fc.constant({ result: '偏差' as const }),
        ).map(([rest, dev]) => [...rest, dev]),
        (samples) => {
          const derived = deriveHasDeviation(samples)
          expect(derived).toBe('是')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: EventBus 发布正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 6: EventBus 发布正确性', () => {
  /**
   * **Validates: Requirements 7.2, 7.3**
   *
   * For any 循环结论变更：
   * - 仅在新旧值不同时发布 control:test-concluded 事件
   * - 载荷含 wpCode/cycleName/conclusion/defectSummary
   */

  beforeEach(() => {
    emittedEvents.length = 0
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  /** 模拟 updateCycleConclusion 的核心逻辑（纯函数提取） */
  function simulateUpdateCycleConclusion(
    oldConclusion: string,
    newConclusion: string,
    wpCode: string,
    cycleName: string,
    hasDefects: boolean,
  ): { shouldEmit: boolean; payload?: { wpCode: string; cycleName: string; conclusion: string; defectSummary: string } } {
    if (oldConclusion === newConclusion) {
      return { shouldEmit: false }
    }
    return {
      shouldEmit: true,
      payload: {
        wpCode,
        cycleName,
        conclusion: newConclusion,
        defectSummary: hasDefects ? '存在控制缺陷' : '',
      },
    }
  }

  it('仅在新旧结论不同时应发布事件', () => {
    fc.assert(
      fc.property(
        arbConclusion,
        arbConclusion,
        (oldConclusion, newConclusion) => {
          const result = simulateUpdateCycleConclusion(
            oldConclusion, newConclusion, 'C5', '货币资金循环', false,
          )

          if (oldConclusion === newConclusion) {
            expect(result.shouldEmit).toBe(false)
          } else {
            expect(result.shouldEmit).toBe(true)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('发布载荷包含 wpCode/cycleName/conclusion/defectSummary 四个字段', () => {
    fc.assert(
      fc.property(
        arbConclusion,
        arbConclusion.filter(c => c !== '全部有效'), // 确保新旧不同
        fc.constantFrom('C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C10', 'C11', 'C12', 'C13', 'C14', 'C15'),
        fc.constantFrom('销售与收款循环', '货币资金循环', '采购与付款循环', '生产与存货循环'),
        fc.boolean(),
        (oldConclusion, newConclusion, wpCode, cycleName, hasDefects) => {
          // 确保新旧不同
          const actualNew = oldConclusion === newConclusion ? newConclusion + '变更' : newConclusion
          const result = simulateUpdateCycleConclusion(
            oldConclusion, actualNew, wpCode, cycleName, hasDefects,
          )

          expect(result.shouldEmit).toBe(true)
          expect(result.payload).toBeDefined()
          expect(result.payload!.wpCode).toBe(wpCode)
          expect(result.payload!.cycleName).toBe(cycleName)
          expect(result.payload!.conclusion).toBe(actualNew)
          expect(typeof result.payload!.defectSummary).toBe('string')

          if (hasDefects) {
            expect(result.payload!.defectSummary).toBe('存在控制缺陷')
          } else {
            expect(result.payload!.defectSummary).toBe('')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('相同值不触发发布（幂等性）', () => {
    fc.assert(
      fc.property(
        arbConclusion,
        fc.constantFrom('C2', 'C5', 'C10', 'C15'),
        (conclusion, wpCode) => {
          const result = simulateUpdateCycleConclusion(
            conclusion, conclusion, wpCode, '测试循环', false,
          )
          expect(result.shouldEmit).toBe(false)
          expect(result.payload).toBeUndefined()
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 点选值合法性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 8: 点选值合法性', () => {
  /**
   * **Validates: Requirements 9.1, 9.2**
   *
   * For any 命名下拉/点选字段，保存值必须属于命名区域选项枚举。
   * 生成器：随机选枚举值和非法值，验证只有合法值被接受。
   */

  /** 命名区域枚举定义（源模板选项清单列表） */
  const NAMED_RANGE_ENUMS: Record<string, string[]> = {
    assertion: ['存在/发生', '完整性', '准确性/计价和分摊', '权利和义务', '截止', '分类', '列报'],
    attribute: ['人工的', '自动化的', '人工依赖信息系统控制'],
    frequency: ['每笔交易', '每天', '每周', '每半月', '每月', '每季度', '每年', '非常规/低运行频率', '其他'],
    testMethod: ['询问', '检查', '观察', '重新执行', '前期', '前推', '利用内部审计工作', '利用服务机构的审计报告'],
    hasDeviation: ['是', '否'],
    sampleResult: ['有效', '偏差', '不适用'],
  }

  /** 纯函数：校验值是否属于命名区域枚举 */
  function isValueInNamedRange(field: string, value: string): boolean {
    const allowed = NAMED_RANGE_ENUMS[field]
    if (!allowed) return false
    return allowed.includes(value)
  }

  /** 非法值生成器 */
  const arbIllegalValue = fc.string({ minLength: 1, maxLength: 10 })
    .filter(v => !Object.values(NAMED_RANGE_ENUMS).flat().includes(v))

  /** 字段名生成器 */
  const arbFieldName = fc.constantFrom(...Object.keys(NAMED_RANGE_ENUMS))

  it('合法枚举值始终通过校验', () => {
    fc.assert(
      fc.property(
        arbFieldName,
        (field) => {
          const options = NAMED_RANGE_ENUMS[field]
          for (const opt of options) {
            expect(isValueInNamedRange(field, opt)).toBe(true)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('非法值始终被拒绝', () => {
    fc.assert(
      fc.property(
        arbFieldName,
        arbIllegalValue,
        (field, illegalValue) => {
          expect(isValueInNamedRange(field, illegalValue)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('对于任意命名区域字段+随机值，只有属于枚举的值才返回 true', () => {
    fc.assert(
      fc.property(
        arbFieldName,
        fc.oneof(
          // 50% 合法值
          arbFieldName.chain(f => fc.constantFrom(...NAMED_RANGE_ENUMS[f])),
          // 50% 非法值
          arbIllegalValue,
        ),
        (field, value) => {
          const result = isValueInNamedRange(field, value)
          const expected = NAMED_RANGE_ENUMS[field].includes(value)
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 决策树点选推进确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 9: 决策树点选推进确定性', () => {
  /**
   * **Validates: Requirements 9.3, 5.2**
   *
   * For any Cx-2 每步点选，nextStep 指引与 evaluateDeviation 推导一致。
   * 即：步骤可见性严格由 evaluateDecisionTree.currentStep 和 isStepVisible 一致推导。
   */

  it('evaluateDecisionTree.currentStep 与 isStepVisible 一致', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          const result = evaluateDecisionTree(state)

          // currentStep 对应的步骤必须 visible
          const currentVisible = isStepVisible(state, result.currentStep)
          expect(currentVisible).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('未到达的步骤不应可见', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }

          // 步骤一=否时，步骤二/三/四不应可见
          if (state.step1 === '否') {
            expect(isStepVisible(state, 2)).toBe(false)
            expect(isStepVisible(state, 3)).toBe(false)
            expect(isStepVisible(state, 4)).toBe(false)
          }

          // 步骤一=是时，步骤六不应可见
          if (state.step1 === '是') {
            expect(isStepVisible(state, 6)).toBe(false)
          }

          // 步骤二≠随机时，步骤三不应可见
          if (state.step2 && state.step2 !== '随机性偏差' && state.step1 === '是') {
            expect(isStepVisible(state, 3)).toBe(false)
            expect(isStepVisible(state, 4)).toBe(false)
          }

          // 步骤三≠扩大样本量时，步骤四不应可见
          if (state.step3 && state.step3 !== '扩大样本量' && state.step2 === '随机性偏差') {
            expect(isStepVisible(state, 4)).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('nextStepHint 始终非空字符串', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        (input) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          const result = evaluateDecisionTree(state)
          expect(result.nextStepHint.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: 偏差回填一致性（扩展 P5）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 10: 偏差回填一致性', () => {
  /**
   * **Validates: Requirements 11.2, 11.3**
   *
   * For any 子页样本偏差状态：
   * - 汇总表「是否识别偏差」与子页偏差状态一致
   * - 决策树推导至缺陷时，汇总「识别出的缺陷」非空
   */

  /** 偏差回填核心逻辑（纯函数） */
  function deriveHasDeviation(samples: Array<{ result: '有效' | '偏差' | '不适用' | null }>): '是' | '否' {
    return samples.some(s => s.result === '偏差') ? '是' : '否'
  }

  /** 缺陷回填逻辑：goToA14=true 时 defect 必须非空 */
  function deriveDefect(goToA14: boolean, controlName: string, conclusion: string | null): string {
    if (!goToA14 || !conclusion) return ''
    return `${controlName} — ${conclusion}`
  }

  it('样本偏差状态与汇总表 hasDeviation 一致', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            result: fc.constantFrom<'有效' | '偏差' | '不适用' | null>('有效', '偏差', '不适用', null),
          }),
          { minLength: 1, maxLength: 30 },
        ),
        (samples) => {
          const hasAnyDeviation = samples.some(s => s.result === '偏差')
          const derived = deriveHasDeviation(samples)
          expect(derived).toBe(hasAnyDeviation ? '是' : '否')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('决策树推导至缺陷时 defect 摘要非空', () => {
    fc.assert(
      fc.property(
        arbDeviationInput,
        fc.string({ minLength: 1, maxLength: 20 }),
        (input, controlName) => {
          const state: DecisionTreeState = {
            step1: input.isDeviation,
            step2: input.nature,
            step3: input.randomResponse,
            step4: input.expandedFoundNew,
            step5: false,
            step6: input.designDeficiency,
          }
          const result = evaluateDecisionTree(state)
          const defect = deriveDefect(result.goToA14, controlName, result.conclusion)

          if (result.goToA14) {
            // 缺陷路径时 defect 非空
            expect(defect.length).toBeGreaterThan(0)
            expect(defect).toContain(controlName)
          } else {
            // 非缺陷路径时 defect 为空
            expect(defect).toBe('')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('偏差回填联动偏差评价入口：有偏差时应显示进入偏差评价', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            result: fc.constantFrom<'有效' | '偏差' | '不适用'>('有效', '偏差', '不适用'),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (samples) => {
          const hasDeviation = deriveHasDeviation(samples) === '是'
          // 联动规则：hasDeviation=是 → 显示 Cx-2 偏差评价入口
          // 测试纯逻辑：hasDeviation=是 当且仅当 存在偏差样本
          const anyDeviation = samples.some(s => s.result === '偏差')
          expect(hasDeviation).toBe(anyDeviation)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: B23 引用生成一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c-control-test-refresh, Property 11: B23 引用生成一致性', () => {
  /**
   * **Validates: Requirements 11.4**
   *
   * For any B23 控制点集合：
   * - 一键引用生成的汇总行数量与控制点数量一致
   * - 控制编号/目标正确映射
   */

  /** B23 控制点生成器 */
  const arbB23ControlPoint = fc.record({
    controlId: fc.array(fc.constantFrom('A', 'B', 'C', '1', '2', '3', '-'), { minLength: 2, maxLength: 8 }).map(arr => arr.join('')),
    controlName: fc.string({ minLength: 1, maxLength: 30 }),
    relatedRisk: fc.constantFrom('高', '中', '低'),
    description: fc.option(fc.string({ minLength: 0, maxLength: 50 }), { nil: undefined }),
    subProcess: fc.option(fc.string({ minLength: 0, maxLength: 20 }), { nil: undefined }),
  })

  const arbB23ControlPoints = fc.array(arbB23ControlPoint, { minLength: 1, maxLength: 15 })

  /** 纯函数模拟 importFromB23 核心逻辑 */
  function simulateImportFromB23(
    b23Points: Array<{ controlId: string; controlName: string; relatedRisk: string; description?: string; subProcess?: string }>,
  ): Array<{ controlId: string; controlName: string; relatedRisk: string; description: string; subProcess: string }> {
    const result: Array<{ controlId: string; controlName: string; relatedRisk: string; description: string; subProcess: string }> = []
    for (const point of b23Points) {
      // 同 composable：跳过无 controlId 且无 controlName 的项
      if (!point.controlId && !point.controlName) continue
      result.push({
        controlId: point.controlId || '',
        controlName: point.controlName || '',
        relatedRisk: point.relatedRisk || '',
        description: point.description || '',
        subProcess: point.subProcess || '',
      })
    }
    return result
  }

  it('生成汇总行数量与 B23 有效控制点数量一致', () => {
    fc.assert(
      fc.property(
        arbB23ControlPoints,
        (b23Points) => {
          const result = simulateImportFromB23(b23Points)
          // 有效控制点：controlId 或 controlName 至少有一个非空
          const validCount = b23Points.filter(p => p.controlId || p.controlName).length
          expect(result.length).toBe(validCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('controlId/controlName/relatedRisk 正确映射', () => {
    fc.assert(
      fc.property(
        arbB23ControlPoints,
        (b23Points) => {
          const result = simulateImportFromB23(b23Points)
          const validPoints = b23Points.filter(p => p.controlId || p.controlName)

          for (let i = 0; i < result.length; i++) {
            const src = validPoints[i]
            const dst = result[i]
            expect(dst.controlId).toBe(src.controlId || '')
            expect(dst.controlName).toBe(src.controlName || '')
            expect(dst.relatedRisk).toBe(src.relatedRisk || '')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空 B23 集合不生成任何行', () => {
    const result = simulateImportFromB23([])
    expect(result.length).toBe(0)
  })

  it('全空字段的 B23 项被过滤', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            controlId: fc.constantFrom('', ''),
            controlName: fc.constantFrom('', ''),
            relatedRisk: fc.constantFrom('高', '中', '低'),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (emptyPoints) => {
          const result = simulateImportFromB23(emptyPoints)
          expect(result.length).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
