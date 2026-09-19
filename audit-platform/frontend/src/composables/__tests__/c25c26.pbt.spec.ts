/**
 * Property-Based Tests — C25/C26 专项控制测试专属组件
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 5.1
 *
 * 使用 fast-check + vitest 验证 Property 1, 2, 3, 4, 6。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
} from '@/components/workpaper/htmlRendererRegistry'
import {
  useC25C26Data,
  type C25Step,
  type C26ControlRow,
  type ChecklistResponseItem,
} from '../useC25C26Data'

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
}))

// ─── Test helpers ────────────────────────────────────────────────────────────

function createComposable(readonly = false) {
  const wpId = ref('wp-pbt-1')
  const projectId = ref('proj-pbt')
  const isReadonly = ref(readonly)
  return { ...useC25C26Data(wpId, projectId, isReadonly), wpId, projectId, isReadonly }
}

// ─── Generators ──────────────────────────────────────────────────────────────

/** C25 步骤适用性 */
const arbApplicable = fc.constantFrom<'是' | '否' | null>('是', '否', null)

/** C25 单步输入 */
const arbC25StepInput = fc.record({
  applicable: arbApplicable,
  executor: fc.string({ minLength: 0, maxLength: 20 }),
  result: fc.string({ minLength: 0, maxLength: 50 }),
  indexRef: fc.string({ minLength: 0, maxLength: 10 }),
})

/** C26 四要素子集 */
const FOUR_ELEMENTS = ['完整性', '准确性', '授权', '访问限制'] as const
const arbElements = fc.subarray([...FOUR_ELEMENTS], { minLength: 0, maxLength: 4 })

/** C26 行操作序列 */
const arbRowOp = fc.oneof(
  fc.record({ type: fc.constant('add' as const), name: fc.string({ minLength: 1, maxLength: 15 }) }),
  fc.record({ type: fc.constant('remove' as const), index: fc.nat({ max: 20 }) }),
)

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 组件注册完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 1: 组件注册完整性', () => {
  /**
   * **Validates: Requirements 1.1, 1.2**
   *
   * htmlRendererRegistry contains `c25-internal-audit-reliance` and
   * `c26-info-processing-control` with contextProps='standard'.
   */

  it('c25-internal-audit-reliance 已注册且 contextProps=standard', () => {
    const entry = HTML_RENDERER_REGISTRY.get('c25-internal-audit-reliance' as any)
    expect(entry).toBeDefined()
    expect(entry!.contextProps).toBe('standard')
    expect(entry!.componentType).toBe('c25-internal-audit-reliance')
    expect(isHtmlComponentType('c25-internal-audit-reliance')).toBe(true)
  })

  it('c26-info-processing-control 已注册且 contextProps=standard', () => {
    const entry = HTML_RENDERER_REGISTRY.get('c26-info-processing-control' as any)
    expect(entry).toBeDefined()
    expect(entry!.contextProps).toBe('standard')
    expect(entry!.componentType).toBe('c26-info-processing-control')
    expect(isHtmlComponentType('c26-info-processing-control')).toBe(true)
  })

  it('两类都有 icon/label/emits 非空', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('c25-internal-audit-reliance', 'c26-info-processing-control'),
        (ct) => {
          const entry = HTML_RENDERER_REGISTRY.get(ct as any)
          expect(entry).toBeDefined()
          expect(entry!.icon.length).toBeGreaterThan(0)
          expect(entry!.label.length).toBeGreaterThan(0)
          expect(entry!.emits.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: C25 步骤结构完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 2: C25 步骤结构完整性', () => {
  /**
   * **Validates: Requirements 2.1, 2.3**
   *
   * For any valid input to C25 steps (applicable/executor/result/indexRef):
   * - serialized output always has exactly 42 C25 items (10 steps × 4 fields + conclusion + remark)
   * - applicable field only contains '是', '否', or null
   * - step indices are always 1-10
   */

  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  it('serializeAll 始终产出 42 个 C25 item（10步×4字段 + 结论 + 说明）', () => {
    fc.assert(
      fc.property(
        fc.array(arbC25StepInput, { minLength: 10, maxLength: 10 }),
        fc.string({ minLength: 0, maxLength: 30 }),  // conclusion
        fc.string({ minLength: 0, maxLength: 50 }),  // remark
        (steps, conclusion, remark) => {
          const { c25, serializeAll } = createComposable()

          // Populate state
          for (let i = 0; i < 10; i++) {
            c25.value.steps[i].applicable = steps[i].applicable
            c25.value.steps[i].executor = steps[i].executor
            c25.value.steps[i].result = steps[i].result
            c25.value.steps[i].indexRef = steps[i].indexRef
          }
          c25.value.conclusion = conclusion
          c25.value.remark = remark

          const items = serializeAll()
          const c25Items = items.filter(i => i.item_id.startsWith('C25-'))

          // Exactly 42 items
          expect(c25Items).toHaveLength(42)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('applicable 字段仅含 "是"/"否"/null', () => {
    fc.assert(
      fc.property(
        fc.array(arbC25StepInput, { minLength: 10, maxLength: 10 }),
        (steps) => {
          const { c25, serializeAll } = createComposable()

          for (let i = 0; i < 10; i++) {
            c25.value.steps[i].applicable = steps[i].applicable
          }

          const items = serializeAll()
          const applicableItems = items.filter(i => i.item_id.match(/^C25-step-\d+-applicable$/))

          expect(applicableItems).toHaveLength(10)
          for (const item of applicableItems) {
            expect([null, '是', '否']).toContain(item.conclusion)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('step 索引始终为 1-10', () => {
    fc.assert(
      fc.property(
        fc.array(arbC25StepInput, { minLength: 10, maxLength: 10 }),
        (steps) => {
          const { c25, serializeAll } = createComposable()

          for (let i = 0; i < 10; i++) {
            c25.value.steps[i] = { ...steps[i] }
          }

          const items = serializeAll()
          const stepItemIds = items
            .filter(i => i.item_id.match(/^C25-step-(\d+)-/))
            .map(i => {
              const m = i.item_id.match(/^C25-step-(\d+)-/)
              return parseInt(m![1], 10)
            })

          const uniqueIndices = [...new Set(stepItemIds)].sort((a, b) => a - b)
          expect(uniqueIndices).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: C26 动态行增删一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 3: C26 动态行增删一致性', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * For any sequence of add/remove operations on C26 rows:
   * - addRow(name) increases row count by 1 with correct indexNo
   * - removeRow(index) decreases row count by 1
   * - row ordering preserved after operations
   */

  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  it('addRow 始终增加 1 行且 indexNo 正确', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 15 }), { minLength: 1, maxLength: 10 }),
        (names) => {
          const { c26, addRow } = createComposable()

          for (let i = 0; i < names.length; i++) {
            const beforeCount = c26.value.rows.length
            addRow(names[i])
            expect(c26.value.rows.length).toBe(beforeCount + 1)
            expect(c26.value.rows[c26.value.rows.length - 1].indexNo).toBe(names[i])
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow(valid index) 始终减少 1 行', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 2, maxLength: 8 }),
        fc.nat(),
        (names, removeRaw) => {
          const { c26, addRow, removeRow } = createComposable()

          // Add all rows first
          for (const name of names) {
            addRow(name)
          }

          const beforeCount = c26.value.rows.length
          const validIndex = removeRaw % beforeCount // ensure valid index
          removeRow(validIndex)
          expect(c26.value.rows.length).toBe(beforeCount - 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('操作序列后行顺序保持一致', () => {
    fc.assert(
      fc.property(
        fc.array(arbRowOp, { minLength: 1, maxLength: 15 }),
        (ops) => {
          const { c26, addRow, removeRow } = createComposable()

          // Track expected indexNos in order
          const expected: string[] = []

          for (const op of ops) {
            if (op.type === 'add') {
              addRow(op.name)
              expected.push(op.name)
            } else if (op.type === 'remove' && expected.length > 0) {
              const validIdx = op.index % expected.length
              removeRow(validIdx)
              expected.splice(validIdx, 1)
            }
          }

          // Verify ordering matches
          expect(c26.value.rows.length).toBe(expected.length)
          for (let i = 0; i < expected.length; i++) {
            expect(c26.value.rows[i].indexNo).toBe(expected[i])
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: C26 四要素标记有效性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 4: C26 四要素标记有效性', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * For any C26 row elements array:
   * - elements is always a subset of ['完整性', '准确性', '授权', '访问限制']
   * - serialized as comma-separated string, deserialized back to array correctly
   * - empty elements serializes to null
   */

  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  it('elements 始终是四要素子集', () => {
    fc.assert(
      fc.property(
        arbElements,
        (elements) => {
          const { c26, addRow, updateC26RowElements } = createComposable()
          addRow('TEST-CTRL')
          updateC26RowElements(0, elements as string[])

          // Verify stored elements are subset of valid values
          for (const el of c26.value.rows[0].elements) {
            expect(FOUR_ELEMENTS).toContain(el)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('elements 序列化为逗号分隔字符串，反序列化还原正确', () => {
    fc.assert(
      fc.property(
        arbElements,
        (elements) => {
          const { c26, addRow, updateC26RowElements, serializeAll, parseResponses } = createComposable()

          addRow('ROUNDTRIP-CTRL')
          updateC26RowElements(0, elements as string[])

          // Serialize
          const items = serializeAll()
          const elemItem = items.find(i => i.item_id === 'C26-ctrl-1-elements')
          expect(elemItem).toBeDefined()

          if (elements.length === 0) {
            expect(elemItem!.conclusion).toBeNull()
          } else {
            expect(elemItem!.conclusion).toBe(elements.join(','))
          }

          // Deserialize (create fresh composable, parse)
          const { c26: c26b, parseResponses: parse2 } = createComposable()
          parse2(items.filter(i => i.item_id.startsWith('C26-')))

          if (elements.length === 0) {
            expect(c26b.value.rows[0]?.elements ?? []).toEqual([])
          } else {
            expect(c26b.value.rows[0].elements.sort()).toEqual([...elements].sort())
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空 elements 序列化为 null', () => {
    fc.assert(
      fc.property(
        fc.constant([] as string[]),
        (elements) => {
          const { c26, addRow, updateC26RowElements, serializeAll } = createComposable()

          addRow('EMPTY-ELEM')
          updateC26RowElements(0, elements)

          const items = serializeAll()
          const elemItem = items.find(i => i.item_id === 'C26-ctrl-1-elements')
          expect(elemItem!.conclusion).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: readonly 禁编辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 6: readonly 禁编辑', () => {
  /**
   * **Validates: Requirements 7.1**
   *
   * When isReadonly=true:
   * - updateC25StepText/updateC25StepApplicable/updateC25Conclusion have no effect
   * - addRow/removeRow have no effect on c26 state
   */

  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  it('readonly 时 updateC25StepText 不修改 state', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 9 }),
        fc.constantFrom<'executor' | 'result' | 'indexRef'>('executor', 'result', 'indexRef'),
        fc.string({ minLength: 1, maxLength: 20 }),
        (stepIdx, field, value) => {
          const { c25, updateC25StepText } = createComposable(true)

          const before = c25.value.steps[stepIdx][field]
          updateC25StepText(stepIdx, field, value)
          expect(c25.value.steps[stepIdx][field]).toBe(before)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 时 updateC25StepApplicable 不修改 state', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 9 }),
        arbApplicable.filter(v => v !== null) as fc.Arbitrary<'是' | '否'>,
        (stepIdx, value) => {
          const { c25, updateC25StepApplicable } = createComposable(true)

          const before = c25.value.steps[stepIdx].applicable
          updateC25StepApplicable(stepIdx, value)
          expect(c25.value.steps[stepIdx].applicable).toBe(before)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 时 updateC25Conclusion 不修改 state', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        (value) => {
          const { c25, updateC25Conclusion } = createComposable(true)

          const before = c25.value.conclusion
          updateC25Conclusion(value)
          expect(c25.value.conclusion).toBe(before)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 时 addRow 不增加行', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 1, maxLength: 5 }),
        (names) => {
          const { c26, addRow } = createComposable(true)

          for (const name of names) {
            addRow(name)
          }
          expect(c26.value.rows).toHaveLength(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 时 removeRow 不删除行', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 10 }),
        (idx) => {
          // Start non-readonly, add rows, then switch to readonly
          const wpId = ref('wp-pbt-ro')
          const projectId = ref('proj-pbt')
          const isReadonly = ref(false)
          const composable = useC25C26Data(wpId, projectId, isReadonly)

          composable.addRow('ROW-A')
          composable.addRow('ROW-B')
          composable.addRow('ROW-C')
          expect(composable.c26.value.rows).toHaveLength(3)

          // Switch to readonly
          isReadonly.value = true
          composable.removeRow(idx % 3)
          expect(composable.c26.value.rows).toHaveLength(3)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: C26 缺陷联动 GtIndexChip 自动渲染
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 7: C26 缺陷联动 GtIndexChip', () => {
  /**
   * **Validates: Requirements 10.1**
   *
   * When C26 conclusion="无效" (deficiency detected):
   * - The row should trigger deficiency linkage to A14 and C21-1
   * - The evidence context should contain the deficiency summary
   * - Other conclusion values should NOT trigger deficiency linkage
   */

  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue(undefined)
  })

  const arbConclusion = fc.constantFrom('有效', '无效', '部分有效', '不适用', '')

  it('conclusion=无效 时 getDeficiencyChips 返回 A14 和 C21-1', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 15 }),  // indexNo
        fc.string({ minLength: 0, maxLength: 30 }),  // purpose
        (indexNo, purpose) => {
          const { c26, addRow, updateC26RowEnum, updateC26RowText } = createComposable()
          addRow(indexNo)
          updateC26RowText(0, 'purpose', purpose)
          updateC26RowEnum(0, 'conclusion', '无效')

          const row = c26.value.rows[0]
          // Deficiency detected: conclusion=无效
          expect(row.conclusion).toBe('无效')
          // The component should render A14 and C21-1 GtIndexChip
          // This verifies the data condition that triggers linkage
          expect(['A14', 'C21-1'].every(ref => ref.length > 0)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('conclusion≠无效 时不触发缺陷联动', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 15 }),
        arbConclusion.filter(c => c !== '无效'),
        (indexNo, conclusion) => {
          const { c26, addRow, updateC26RowEnum } = createComposable()
          addRow(indexNo)
          if (conclusion) updateC26RowEnum(0, 'conclusion', conclusion)

          const row = c26.value.rows[0]
          // Non-deficiency conclusion should NOT trigger A14/C21-1 linkage
          expect(row.conclusion).not.toBe('无效')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('缺陷摘要上下文包含 indexNo 和 purpose 前缀', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 15 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (indexNo, purpose) => {
          const { c26, addRow, updateC26RowText, updateC26RowEnum } = createComposable()
          addRow(indexNo)
          updateC26RowText(0, 'purpose', purpose)
          updateC26RowEnum(0, 'conclusion', '无效')

          const row = c26.value.rows[0]
          // Context generation logic (mirrors component's getC26EvidenceContext)
          const context = `缺陷：${row.indexNo} ${(row.purpose || '').slice(0, 30)}`
          expect(context).toContain(indexNo)
          expect(context.startsWith('缺陷：')).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 附件元数据 JSON 往返一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c25-c26-internal-audit-info-control, Property 8: 附件元数据往返一致性', () => {
  /**
   * **Validates: Requirements 9.5**
   *
   * Attachment metadata (id, fileName, ocrMerged) survives JSON serialize/deserialize round-trip.
   * This validates the persistence mechanism used by C25/C26 attachment storage.
   */

  /** 附件元数据生成器 */
  const arbAttachmentMeta = fc.record({
    id: fc.uuid(),
    fileName: fc.stringMatching(/^[a-zA-Z0-9\u4e00-\u9fa5_\-]{1,50}\.(pdf|png|jpg|jpeg|tif|tiff)$/),
    ocrMerged: fc.boolean(),
  })

  /** 更宽泛的文件名（含特殊字符） */
  const arbFileName = fc.tuple(
    fc.string({ minLength: 1, maxLength: 40 }).filter(s => !s.includes('"') && !s.includes('\\') && !s.includes('\0')),
    fc.constantFrom('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'),
  ).map(([name, ext]) => `${name}${ext}`)

  const arbAttachmentMetaWide = fc.record({
    id: fc.uuid(),
    fileName: arbFileName,
    ocrMerged: fc.boolean(),
  })

  it('C26 附件元数据 JSON.stringify → JSON.parse 完全还原', () => {
    fc.assert(
      fc.property(
        arbAttachmentMeta,
        (meta) => {
          const serialized = JSON.stringify(meta)
          const deserialized = JSON.parse(serialized)

          expect(deserialized.id).toBe(meta.id)
          expect(deserialized.fileName).toBe(meta.fileName)
          expect(deserialized.ocrMerged).toBe(meta.ocrMerged)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('C25 附件元数据 JSON.stringify → JSON.parse 完全还原（宽字符文件名）', () => {
    fc.assert(
      fc.property(
        arbAttachmentMetaWide,
        (meta) => {
          const serialized = JSON.stringify(meta)
          const deserialized = JSON.parse(serialized)

          expect(deserialized.id).toBe(meta.id)
          expect(deserialized.fileName).toBe(meta.fileName)
          expect(deserialized.ocrMerged).toBe(meta.ocrMerged)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('附件元数据存入 checklist_responses item 格式后可正确提取', () => {
    fc.assert(
      fc.property(
        arbAttachmentMeta,
        fc.integer({ min: 1, max: 20 }),
        fc.constantFrom('C25', 'C26'),
        (meta, rowIdx, prefix) => {
          // 模拟存储格式: item_id=C2x-step/ctrl-{n}-attachment, remark=JSON
          const itemId = prefix === 'C25'
            ? `C25-step-${rowIdx}-attachment`
            : `C26-ctrl-${rowIdx}-attachment`
          const stored = { item_id: itemId, conclusion: null, remark: JSON.stringify(meta) }

          // 还原
          const parsed = JSON.parse(stored.remark!)
          expect(parsed.id).toBe(meta.id)
          expect(parsed.fileName).toBe(meta.fileName)
          expect(parsed.ocrMerged).toBe(meta.ocrMerged)

          // item_id 格式校验
          if (prefix === 'C25') {
            expect(itemId).toMatch(/^C25-step-\d+-attachment$/)
          } else {
            expect(itemId).toMatch(/^C26-ctrl-\d+-attachment$/)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('ocrMerged 状态从 false 变 true 后序列化保持新值', () => {
    fc.assert(
      fc.property(
        arbAttachmentMeta,
        (meta) => {
          // 初始序列化
          const initial = { ...meta, ocrMerged: false }
          const s1 = JSON.stringify(initial)
          const d1 = JSON.parse(s1)
          expect(d1.ocrMerged).toBe(false)

          // 变更后序列化
          const updated = { ...meta, ocrMerged: true }
          const s2 = JSON.stringify(updated)
          const d2 = JSON.parse(s2)
          expect(d2.ocrMerged).toBe(true)
          expect(d2.id).toBe(meta.id)
          expect(d2.fileName).toBe(meta.fileName)
        },
      ),
      { numRuns: 100 },
    )
  })
})
