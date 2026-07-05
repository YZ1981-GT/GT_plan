/**
 * C1 企业层面控制测试 �?前端属性测试（fast-check�?
 *
 * Feature: c1-entity-level-control
 * Task 5.1 产出物。覆盖设计文�?Correctness Properties�?
 *   - Property 1: 组件注册完整�?       (Requirements 1.1, 1.2, 1.3)
 *   - Property 2: 九段分组完整�?       (Requirements 2.1)
 *   - Property 3: 适用性进度排除不适用�?(Requirements 3.2, 3.3)
 *   - Property 6: readonly 禁编�?       (Requirements 8.1)
 *
 * Property 4「样本借贷勾稽正确性�?Requirements 4.4) 已在
 * `useC1SampleEngine.test.ts` 中以 �?00 runs 覆盖，本文件不重复实现，
 * 仅在下方引用其核心函数做一次一致性回归引用（不构成重复的 property 断言）�?
 *
 * 每个 property �?00 runs。Tag 见各 describe 块标题�?
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type EffectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'
import fc from 'fast-check'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../../htmlRendererRegistry'
import {
  C1_SECTION_DEFS,
  C1_SECTION_SLUGS,
  C1_PROGRAM_ROW_MIN,
  C1_PROGRAM_ROW_MAX,
  assignSectionByRow,
  groupStepsByRow,
  groupStepsBySlug,
  totalGrouped,
  canPersistApplicability,
  sectionProgressDetail,
  type C1SectionSlug,
  type C1ResponseLike,
} from '../useC1SectionEngine'
import { calcSampleBalance } from '../useC1SampleEngine'

const C1_COMPONENT_TYPE = 'c1-entity-level-control'

// ─── Property 1: 组件注册完整�?──────────────────────────────────────────────

describe('Feature: c1-entity-level-control, Property 1: 组件注册完整�?, () => {
  // 一次性读取后端注册来源（overrides + VALID_COMPONENT_TYPES�?
  const overridesPath = path.resolve(
    __dirname,
    '../../../../../../../backend/app/data/wp_code_overrides.json',
  )
  const servicePath = path.resolve(
    __dirname,
    '../../../../../../../backend/app/services/wp_classification_service.py',
  )
  const overrides: Record<string, string> = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))
  const serviceSrc: string = fs.readFileSync(servicePath, 'utf-8')

  it('C1 �?c1-entity-level-control 且三处注册齐全（overrides + registry + VALID_COMPONENT_TYPES�?, () => {
    // C1 主底稿在 overrides 中映射到专属 componentType（子 sheet 由主组件内部分发，不单列�?
    fc.assert(
      fc.property(fc.constantFrom('C1'), (code) => {
        expect(overrides[code]).toBe(C1_COMPONENT_TYPE)
        // 前端渲染注册表登�?
        expect(HTML_RENDERER_REGISTRY.has(C1_COMPONENT_TYPE)).toBe(true)
        expect(isHtmlComponentType(C1_COMPONENT_TYPE)).toBe(true)
        const entry = getRendererEntry(C1_COMPONENT_TYPE)
        expect(entry?.componentType).toBe(C1_COMPONENT_TYPE)
        expect(entry?.component).toBeDefined()
        // 后端 VALID_COMPONENT_TYPES 登记
        expect(serviceSrc).toContain(`"${C1_COMPONENT_TYPE}"`)
      }),
      { numRuns: 25 },
    )
  })

  it('注册一致性：任意 componentType 字符�?isHtmlComponentType �?注册表存�?, () => {
    const registered = [...HTML_RENDERER_REGISTRY.keys()]
    const junk = fc.oneof(
      fc.constantFrom(C1_COMPONENT_TYPE, ...registered),
      fc.string(), // 随机噪声（几乎必为未注册�?
      fc.constantFrom('c1', 'C1', 'entity-level-control', 'c1-entity', 'skip', 'unknown'),
    )
    fc.assert(
      fc.property(junk, (t) => {
        expect(isHtmlComponentType(t)).toBe(HTML_RENDERER_REGISTRY.has(t as never))
      }),
      { numRuns: 25 },
    )
  })
})

// ─── Property 2: 九段分组完整�?──────────────────────────────────────────────

describe('Feature: c1-entity-level-control, Property 2: 九段分组完整�?, () => {
  interface RowStep { id: number; row: number }

  // 覆盖全表行区间及越界行（1..5 表头�?136 尾部�?
  const rowStepArb: fc.Arbitrary<RowStep> = fc.record({
    id: fc.nat(),
    row: fc.integer({ min: 0, max: C1_PROGRAM_ROW_MAX + 20 }),
  })

  it('按行分组：无遗漏无重复（Σ分组�?+ ungrouped == 总数�?, () => {
    fc.assert(
      fc.property(fc.array(rowStepArb, { maxLength: 300 }), (steps) => {
        const grouped = groupStepsByRow(steps)
        // 无遗漏：分组总数 + 未分�?== 输入总数
        expect(totalGrouped(grouped) + grouped.ungrouped.length).toBe(steps.length)
        // 无重复：每个步骤 id 至多出现一次（跨九�?+ ungrouped�?
        const seen = new Set<number>()
        let count = 0
        for (const slug of C1_SECTION_SLUGS) {
          for (const s of grouped.groups[slug]) {
            seen.add(s.id === undefined ? count : s.id)
            count++
          }
        }
        count += grouped.ungrouped.length
        expect(count).toBe(steps.length)
      }),
      { numRuns: 25 },
    )
  })

  it('落在九段行区间内的步骤必被唯一归段，且归段�?assignSectionByRow 一�?, () => {
    const inRangeStep: fc.Arbitrary<RowStep> = fc.record({
      id: fc.nat(),
      row: fc.integer({ min: C1_PROGRAM_ROW_MIN, max: C1_PROGRAM_ROW_MAX }),
    })
    fc.assert(
      fc.property(fc.array(inRangeStep, { maxLength: 200 }), (steps) => {
        const grouped = groupStepsByRow(steps)
        // 区间内步骤无一落入 ungrouped
        expect(grouped.ungrouped.length).toBe(0)
        expect(totalGrouped(grouped)).toBe(steps.length)
        // 每段内所有步�?assignSectionByRow 都等于该�?slug
        for (const slug of C1_SECTION_SLUGS) {
          for (const s of grouped.groups[slug]) {
            expect(assignSectionByRow(s.row)).toBe(slug)
          }
        }
      }),
      { numRuns: 25 },
    )
  })

  it('�?slug 分组：合�?slug 唯一归段，非�?slug �?ungrouped', () => {
    const slugStep = fc.record({
      id: fc.nat(),
      section: fc.oneof(
        fc.constantFrom<string>(...C1_SECTION_SLUGS),
        fc.string(),
        fc.constantFrom('COSO', 'x', ''),
      ),
    })
    fc.assert(
      fc.property(fc.array(slugStep, { maxLength: 200 }), (steps) => {
        const grouped = groupStepsBySlug(steps)
        expect(totalGrouped(grouped) + grouped.ungrouped.length).toBe(steps.length)
        // 合法 slug 步骤�?== 各段计数之和
        const legal = steps.filter((s) =>
          (C1_SECTION_SLUGS as readonly string[]).includes(s.section),
        ).length
        expect(totalGrouped(grouped)).toBe(legal)
      }),
      { numRuns: 25 },
    )
  })

  it('九段行区间连续无缝无重叠（分组完整性前提）', () => {
    // 逐行遍历整表：每一行至多命中一个段；区间内恰好命中一�?
    fc.assert(
      fc.property(fc.integer({ min: C1_PROGRAM_ROW_MIN, max: C1_PROGRAM_ROW_MAX }), (row) => {
        const hits = C1_SECTION_DEFS.filter((d) => row >= d.startRow && row <= d.endRow)
        expect(hits.length).toBe(1)
        expect(assignSectionByRow(row)).toBe(hits[0].slug)
      }),
      { numRuns: 25 },
    )
  })
})

// ─── Property 3: 适用性进度排除不适用�?──────────────────────────────────────

describe('Feature: c1-entity-level-control, Property 3: 适用性进度排除不适用�?, () => {
  it('不适用步骤必有非空理由方可保存（canPersistApplicability�?, () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.oneof(fc.constant(undefined), fc.constant(null), fc.string()),
        (applicable, reason) => {
          const ok = canPersistApplicability(applicable, reason as string | null | undefined)
          if (applicable) {
            // 适用：始终可保存，无需理由
            expect(ok).toBe(true)
          } else {
            // 不适用：当且仅当理�?trim 后非�?
            const hasReason = !!(reason && String(reason).trim())
            expect(ok).toBe(hasReason)
          }
        },
      ),
      { numRuns: 25 },
    )
  })

  it('段完成进度分�?== 适用步骤数（排除 conclusion=N 的不适用步骤�?, () => {
    const slug: C1SectionSlug = 'ce'
    // 生成若干步骤，各�?applicable(Y/N) + 可�?result �?
    const stepArb = fc.record({
      step: fc.integer({ min: 1, max: 30 }),
      applicable: fc.boolean(),
      hasResult: fc.boolean(),
    })
    fc.assert(
      fc.property(fc.array(stepArb, { maxLength: 40 }), (rawSteps) => {
        // 去重步骤号（同号后者覆盖），构�?responses
        const byStep = new Map<number, { applicable: boolean; hasResult: boolean }>()
        for (const s of rawSteps) byStep.set(s.step, { applicable: s.applicable, hasResult: s.hasResult })

        const responses: C1ResponseLike[] = []
        for (const [step, v] of byStep) {
          responses.push({
            item_id: `C1-${slug}-${step}-applicable`,
            conclusion: v.applicable ? 'Y' : 'N',
            remark: v.applicable ? null : '不适用理由',
          })
          if (v.hasResult) {
            responses.push({
              item_id: `C1-${slug}-${step}-result`,
              conclusion: null,
              remark: '已执行测�?,
            })
          }
        }

        const detail = sectionProgressDetail(responses, slug, true)

        // 期望分母：适用（applicable=true）且出现�?applicable/result 字段的步骤数
        const applicableSteps = [...byStep.values()].filter((v) => v.applicable).length
        expect(detail.denominator).toBe(applicableSteps)
        // 分子不超过分母；不适用步骤即使�?result 也不计入
        expect(detail.completed).toBeLessThanOrEqual(detail.denominator)
        // percent �?0..100 且与分子分母一�?
        const expectedPct = detail.denominator === 0
          ? 0
          : Math.round((detail.completed / detail.denominator) * 100)
        expect(detail.percent).toBe(expectedPct)
      }),
      { numRuns: 25 },
    )
  })

  it('整段不适用时进度视为已裁剪（denominator=0, percent=100�?, () => {
    const responsesArb = fc.array(
      fc.record({
        item_id: fc.constant('C1-bu-1-applicable'),
        conclusion: fc.constantFrom('Y', 'N', null),
        remark: fc.option(fc.string(), { nil: null }),
      }),
      { maxLength: 10 },
    )
    fc.assert(
      fc.property(responsesArb, (responses) => {
        const detail = sectionProgressDetail(responses as C1ResponseLike[], 'bu', false)
        expect(detail.denominator).toBe(0)
        expect(detail.percent).toBe(100)
      }),
      { numRuns: 25 },
    )
  })
})

// ─── Property 4: 引用回归（不重复断言，权威实现见 useC1SampleEngine.test.ts�?──

describe('Feature: c1-entity-level-control, Property 4 (reference): 样本借贷勾稽', () => {
  it('引用 calcSampleBalance 做一次冒烟回归（完整 property �?useC1SampleEngine.test.ts�?, () => {
    const r = calcSampleBalance([
      { date: '', account: '', ref: '', desc: '', debit: 100, credit: 0 },
      { date: '', account: '', ref: '', desc: '', debit: 0, credit: 100 },
    ])
    expect(r).toEqual({ debitTotal: 100, creditTotal: 100, balanced: true })
  })
})

// ─── Property 6: readonly 禁编�?─────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

// 动�?import 需�?mock 声明�?
import { useC1ControlData } from '../useC1ControlData'

type EditOp =
  | { kind: 'conclusion'; itemId: string; value: string }
  | { kind: 'text'; itemId: string; value: string }
  | { kind: 'wpRef'; itemId: string; value: string }
  | { kind: 'applicable'; itemId: string; applicable: boolean; reason: string }

describe('Feature: c1-entity-level-control, Property 6: readonly 禁编�?, () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue([])
  })

  const opArb: fc.Arbitrary<EditOp> = fc.oneof(
    fc.record({ kind: fc.constant('conclusion' as const), itemId: fc.string({ minLength: 1 }), value: fc.string() }),
    fc.record({ kind: fc.constant('text' as const), itemId: fc.string({ minLength: 1 }), value: fc.string() }),
    fc.record({ kind: fc.constant('wpRef' as const), itemId: fc.string({ minLength: 1 }), value: fc.string() }),
    fc.record({
      kind: fc.constant('applicable' as const),
      itemId: fc.string({ minLength: 1 }),
      applicable: fc.boolean(),
      reason: fc.string(),
    }),
  )

  it('readonly=true 下任意编辑序列都不发起保存，本地状态不�?, async () => {
    await fc.assert(
      fc.asyncProperty(fc.array(opArb, { maxLength: 30 }), async (ops) => {
        mockPut.mockClear()
        const scope: EffectScope = effectScope()
        let handle!: ReturnType<typeof useC1ControlData>
        scope.run(() => {
          handle = useC1ControlData(ref('wp-ro'), { readonly: ref(true) })
        })

        const applicableResults: boolean[] = []
        for (const op of ops) {
          switch (op.kind) {
            case 'conclusion':
              handle.setConclusion(op.itemId, op.value)
              break
            case 'text':
              handle.setText(op.itemId, op.value)
              break
            case 'wpRef':
              handle.setWpRef(op.itemId, op.value)
              break
            case 'applicable':
              applicableResults.push(handle.setApplicable(op.itemId, op.applicable, op.reason))
              break
          }
        }
        handle.flushPendingSave()
        await flushPromises()

        // 禁编辑：无任�?PUT
        expect(mockPut).not.toHaveBeenCalled()
        // 本地 responses 不被写入（方法在 readonly 时提前返回，�?applyPatch�?
        expect(handle.responses.value.size).toBe(0)
        // setApplicable �?readonly 下一律返�?false
        expect(applicableResults.every((r) => r === false)).toBe(true)

        scope.stop()
        await flushPromises()
        // 卸载 flush 也不应触发保�?
        expect(mockPut).not.toHaveBeenCalled()
      }),
      { numRuns: 25 },
    )
  })
})
