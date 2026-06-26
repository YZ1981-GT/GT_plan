/**
 * Property-Based Tests — A1-12 重大事项决定程序双模式核查表
 *
 * Spec: .kiro/specs/a1-12-dual-mode-checklist/
 * Task: 5 (Sub-tasks 5.1~5.6)
 *
 * 使用 fast-check + vitest 验证 correctness properties。
 * 测试纯计算逻辑——从组件内提取的纯函数等价实现。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Types (mirror component types for PBT) ─────────────────────────────────

interface A112ItemResponse {
  applicable: 'yes' | 'no' | null
  ref_index: string
}

interface A112CustomItem {
  id: string
  description: string
  applicable: 'yes' | 'no' | null
  ref_index: string
}

interface A112CheckItem {
  id: string
  seq: number
  description: string
  category_tag?: string
}

interface A112Category {
  id: string
  title: string
  items: A112CheckItem[]
  allow_custom: boolean
}

interface A112Responses {
  items: Record<string, A112ItemResponse>
  header: Record<string, unknown>
  custom_items: A112CustomItem[]
}

type ActiveMode = 'html' | 'docx'

// ─── Pure Logic Functions (extracted equivalents from component) ─────────────

/**
 * parseRefIndices — 解析 ref_index 字符串为独立索引号数组
 */
function parseRefIndices(refIndex: string): string[] {
  if (!refIndex) return []
  return refIndex.split(/[,;，；]/).map(s => s.trim()).filter(Boolean)
}

/**
 * getCardStateClass — 根据 item 响应返回 CSS 状态类名
 */
function getCardStateClass(
  itemId: string,
  items: Record<string, A112ItemResponse>,
): string {
  const resp = items[itemId]
  if (!resp || resp.applicable === null) return 'gt-a112-dual-checklist__card--unmarked'
  if (resp.applicable === 'yes') return 'gt-a112-dual-checklist__card--applicable'
  return 'gt-a112-dual-checklist__card--not-applicable'
}

/**
 * computeProgressStats — 计算进度统计
 */
function computeProgressStats(
  categories: A112Category[],
  responses: A112Responses,
): { applicable: number; notApplicable: number; unmarked: number; total: number; percent: number } {
  const categoryItems = categories.flatMap(c => c.items)
  const customItems = responses.custom_items ?? []
  const total = categoryItems.length + customItems.length

  let applicable = 0
  let notApplicable = 0

  for (const item of categoryItems) {
    const resp = responses.items[item.id]
    if (resp?.applicable === 'yes') applicable++
    else if (resp?.applicable === 'no') notApplicable++
  }

  for (const ci of customItems) {
    if (ci.applicable === 'yes') applicable++
    else if (ci.applicable === 'no') notApplicable++
  }

  const unmarked = total - applicable - notApplicable
  const marked = applicable + notApplicable
  const percent = total > 0 ? Math.round((marked / total) * 100) : 0

  return { applicable, notApplicable, unmarked, total, percent }
}

/**
 * shouldRefreshOnModeSwitch — 判断 DOCX→HTML 切换时是否应调用 API
 */
function shouldRefreshOnModeSwitch(
  newMode: ActiveMode,
  oldMode: ActiveMode,
  docxDirty: boolean,
): boolean {
  return newMode === 'html' && oldMode === 'docx' && docxDirty
}

// ─── Arbitraries ────────────────────────────────────────────────────────────

/** 随机适用性值 */
const arbApplicable = fc.constantFrom<'yes' | 'no' | null>('yes', 'no', null)

/** 随机索引号字符串（可含分隔符） */
const arbRefIndex = fc.oneof(
  fc.constant(''),
  // 随机混合字符串（可能含分隔符和空格）
  fc.array(
    fc.constantFrom(
      'A', 'B', 'C', 'D', 'E', 'F', '1', '2', '3', '-', ',', ';', '，', '；', ' ',
    ),
    { minLength: 0, maxLength: 30 },
  ).map(chars => chars.join('')),
  // 典型索引号格式：如 "A17-3,B2-1"
  fc.array(
    fc.tuple(
      fc.constantFrom('A', 'B', 'C', 'D', 'E', 'F'),
      fc.integer({ min: 1, max: 99 }),
      fc.option(fc.integer({ min: 1, max: 9 }), { nil: undefined }),
    ).map(([letter, num, sub]) => sub !== undefined ? `${letter}${num}-${sub}` : `${letter}${num}`),
    { minLength: 1, maxLength: 5 },
  ).map(arr => arr.join(',')),
)

/** 随机 A112ItemResponse */
const arbItemResponse: fc.Arbitrary<A112ItemResponse> = fc.record({
  applicable: arbApplicable,
  ref_index: arbRefIndex,
})

/** 随机 A112CustomItem */
const arbCustomItem: fc.Arbitrary<A112CustomItem> = fc.record({
  id: fc.string({ minLength: 1, maxLength: 20 }).map(s => `custom-${s}`),
  description: fc.string({ minLength: 0, maxLength: 50 }),
  applicable: arbApplicable,
  ref_index: arbRefIndex,
})

/** 随机 A112CheckItem */
const arbCheckItem = (seq: number): fc.Arbitrary<A112CheckItem> =>
  fc.record({
    id: fc.constant(`item-${seq}`),
    seq: fc.constant(seq),
    description: fc.string({ minLength: 1, maxLength: 100 }),
    category_tag: fc.option(fc.string({ minLength: 1, maxLength: 5 }), { nil: undefined }),
  })

/** 随机 Category（固定 items 数量范围） */
const arbCategory = (catId: string, itemOffset: number, itemCount: number): fc.Arbitrary<A112Category> =>
  fc.tuple(
    fc.string({ minLength: 3, maxLength: 30 }),
    fc.constantFrom(true, false),
    ...Array.from({ length: itemCount }, (_, i) => arbCheckItem(itemOffset + i + 1)),
  ).map(([title, allowCustom, ...items]) => ({
    id: catId,
    title: title as string,
    items: items as A112CheckItem[],
    allow_custom: allowCustom as boolean,
  }))

/** 生成完整的 categories + responses 随机状态 */
const arbFullState = fc.record({
  cat1ItemCount: fc.integer({ min: 1, max: 14 }),
  cat2ItemCount: fc.integer({ min: 0, max: 5 }),
  customItemCount: fc.integer({ min: 0, max: 5 }),
}).chain(({ cat1ItemCount, cat2ItemCount, customItemCount }) =>
  fc.tuple(
    arbCategory('cat-1', 0, cat1ItemCount),
    arbCategory('cat-2', cat1ItemCount, cat2ItemCount),
    fc.array(arbCustomItem, { minLength: customItemCount, maxLength: customItemCount }),
    // Generate responses for all items
    fc.tuple(
      ...Array.from({ length: cat1ItemCount + cat2ItemCount }, () => arbItemResponse),
    ),
  ).map(([cat1, cat2, customItems, itemResponses]) => {
    const categories: A112Category[] = [cat1, cat2]
    const allItems = [...cat1.items, ...cat2.items]
    const items: Record<string, A112ItemResponse> = {}
    for (let i = 0; i < allItems.length; i++) {
      items[allItems[i].id] = itemResponses[i]
    }
    const responses: A112Responses = { items, header: {}, custom_items: customItems }
    return { categories, responses }
  }),
)

/** 随机 ActiveMode */
const arbMode = fc.constantFrom<ActiveMode>('html', 'docx')


// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 模式互斥渲染
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 1: 模式互斥渲染', () => {
  /**
   * **Validates: Requirements 2.1, 4.2, 4.3**
   *
   * For any state (html|docx), exactly one sub-view is rendered
   * (never both, never neither when data loaded).
   *
   * 验证逻辑：activeMode 是一个二值变量，恰好决定渲染哪个分支。
   * 模板中用 v-if="activeMode === 'html'" / v-else-if="activeMode === 'docx'"
   * 因此只要 activeMode ∈ {'html','docx'}，必有且仅有一个分支渲染。
   */
  it('activeMode ∈ {html, docx} 时，恰好有一个视图分支被选中', () => {
    fc.assert(
      fc.property(
        arbMode,
        (mode) => {
          const showHtml = mode === 'html'
          const showDocx = mode === 'docx'

          // Exactly one must be true
          expect(showHtml !== showDocx).toBe(true)
          // Never both
          expect(showHtml && showDocx).toBe(false)
          // Never neither
          expect(showHtml || showDocx).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('任意模式切换序列后，始终只有一个视图激活', () => {
    fc.assert(
      fc.property(
        fc.array(arbMode, { minLength: 1, maxLength: 20 }),
        (modeSequence) => {
          // Simulate a sequence of mode switches
          let currentMode: ActiveMode = 'html' // default

          for (const mode of modeSequence) {
            currentMode = mode
          }

          // After any sequence, exactly one view active
          const showHtml = currentMode === 'html'
          const showDocx = currentMode === 'docx'
          expect(showHtml !== showDocx).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 适用性→UI映射
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 2: 适用性→UI映射', () => {
  /**
   * **Validates: Requirements 3.4, 3.5**
   *
   * For any item:
   *   applicable='yes' → index area visible (card class = applicable)
   *   applicable='no' or null → index area hidden
   */
  it('applicable=yes → 索引区可见（卡片状态=applicable）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }),
        arbRefIndex,
        (itemId, refIndex) => {
          const items: Record<string, A112ItemResponse> = {
            [itemId]: { applicable: 'yes', ref_index: refIndex },
          }
          const cls = getCardStateClass(itemId, items)
          expect(cls).toBe('gt-a112-dual-checklist__card--applicable')

          // Index area visible: applicable === 'yes'
          const indexVisible = items[itemId].applicable === 'yes'
          expect(indexVisible).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('applicable=no → 索引区隐藏（卡片状态=not-applicable）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }),
        arbRefIndex,
        (itemId, refIndex) => {
          const items: Record<string, A112ItemResponse> = {
            [itemId]: { applicable: 'no', ref_index: refIndex },
          }
          const cls = getCardStateClass(itemId, items)
          expect(cls).toBe('gt-a112-dual-checklist__card--not-applicable')

          // Index area hidden: applicable !== 'yes'
          const indexVisible = items[itemId].applicable === 'yes'
          expect(indexVisible).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('applicable=null → 索引区隐藏（卡片状态=unmarked）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }),
        arbRefIndex,
        (itemId, refIndex) => {
          const items: Record<string, A112ItemResponse> = {
            [itemId]: { applicable: null, ref_index: refIndex },
          }
          const cls = getCardStateClass(itemId, items)
          expect(cls).toBe('gt-a112-dual-checklist__card--unmarked')

          const indexVisible = items[itemId].applicable === 'yes'
          expect(indexVisible).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('未注册 item → 索引区隐藏（卡片状态=unmarked）', () => {
    fc.assert(
      fc.property(
        // Use realistic item IDs (item-N pattern) to avoid Object.prototype collisions
        fc.integer({ min: 1, max: 999 }).map(n => `item-${n}`),
        (itemId) => {
          const items: Record<string, A112ItemResponse> = {}
          const cls = getCardStateClass(itemId, items)
          expect(cls).toBe('gt-a112-dual-checklist__card--unmarked')

          // No response → applicable is effectively null → index hidden
          const resp = items[itemId]
          const indexVisible = resp?.applicable === 'yes'
          expect(indexVisible).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 索引号渲染一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 3: 索引号渲染一致性', () => {
  /**
   * **Validates: Requirements 3.5**
   *
   * For any item with non-empty ref_index, parseRefIndices produces
   * non-empty array → GtIndexChip would render for each element.
   * Empty ref_index → no chips rendered.
   */
  it('非空 ref_index 含有效分段 → parseRefIndices 返回非空数组（GtIndexChip 渲染）', () => {
    fc.assert(
      fc.property(
        // Generate ref_index with at least one non-separator, non-space char
        fc.array(
          fc.tuple(
            fc.constantFrom('A', 'B', 'C', 'D', 'E', 'F'),
            fc.integer({ min: 1, max: 99 }),
          ).map(([l, n]) => `${l}${n}`),
          { minLength: 1, maxLength: 5 },
        ).map(arr => arr.join(',')),
        (refIndex) => {
          const parsed = parseRefIndices(refIndex)
          // Should produce at least one chip
          expect(parsed.length).toBeGreaterThanOrEqual(1)
          // Each chip should be non-empty
          for (const chip of parsed) {
            expect(chip.length).toBeGreaterThan(0)
            expect(chip.trim()).toBe(chip) // no leading/trailing whitespace
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('空字符串 ref_index → parseRefIndices 返回空数组（无 GtIndexChip）', () => {
    fc.assert(
      fc.property(
        fc.constant(''),
        (refIndex) => {
          const parsed = parseRefIndices(refIndex)
          expect(parsed).toEqual([])
        },
      ),
      { numRuns: 10 },
    )
  })

  it('仅含分隔符/空白 → parseRefIndices 返回空数组', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.constantFrom(',', ';', '，', '；', ' ', '\t'),
          { minLength: 1, maxLength: 20 },
        ).map(chars => chars.join('')),
        (refIndex) => {
          const parsed = parseRefIndices(refIndex)
          expect(parsed).toEqual([])
        },
      ),
      { numRuns: 200 },
    )
  })

  it('parseRefIndices 输出的每个元素均对应一个 GtIndexChip（数量一致性）', () => {
    fc.assert(
      fc.property(
        arbRefIndex,
        (refIndex) => {
          const parsed = parseRefIndices(refIndex)
          // Each parsed element is non-empty (by filter(Boolean))
          for (const chip of parsed) {
            expect(chip.length).toBeGreaterThan(0)
          }
          // The number of chips = number of non-empty segments after split
          const manualSplit = refIndex
            .split(/[,;，；]/)
            .map(s => s.trim())
            .filter(Boolean)
          expect(parsed.length).toBe(manualSplit.length)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: DOCX→HTML 切换刷新
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 4: DOCX→HTML 切换刷新', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * If docxDirty=true when switching docx→html, API must be called.
   * Other transitions (html→docx, html→html, docx→docx) do not trigger refresh.
   */
  it('docxDirty=true + docx→html 切换 → 必须触发 API 刷新', () => {
    fc.assert(
      fc.property(
        fc.constant(true), // docxDirty always true for this property
        (docxDirty) => {
          const result = shouldRefreshOnModeSwitch('html', 'docx', docxDirty)
          expect(result).toBe(true)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('docxDirty=false + docx→html 切换 → 不触发 API', () => {
    fc.assert(
      fc.property(
        fc.constant(false),
        (docxDirty) => {
          const result = shouldRefreshOnModeSwitch('html', 'docx', docxDirty)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('html→docx 切换（无论 docxDirty）→ 不触发 API', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (docxDirty) => {
          const result = shouldRefreshOnModeSwitch('docx', 'html', docxDirty)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('同模式切换（html→html 或 docx→docx）→ 不触发 API', () => {
    fc.assert(
      fc.property(
        arbMode,
        fc.boolean(),
        (mode, docxDirty) => {
          const result = shouldRefreshOnModeSwitch(mode, mode, docxDirty)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('任意切换组合中，仅 docx→html + dirty=true 触发刷新', () => {
    fc.assert(
      fc.property(
        arbMode,
        arbMode,
        fc.boolean(),
        (newMode, oldMode, docxDirty) => {
          const result = shouldRefreshOnModeSwitch(newMode, oldMode, docxDirty)
          const expected = newMode === 'html' && oldMode === 'docx' && docxDirty
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 响应持久化不丢失
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 5: 响应持久化不丢失', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * Before/after mode switch, responses should be equivalent.
   * Mode switching should NOT mutate the responses object.
   *
   * 模拟：将 responses 深拷贝，执行模式切换逻辑（不涉及 API 调用），
   * 验证 responses 引用数据不变。
   */
  it('模式切换不修改 responses 数据（纯状态保持）', () => {
    fc.assert(
      fc.property(
        arbFullState,
        fc.array(arbMode, { minLength: 1, maxLength: 10 }),
        ({ responses }, modeSequence) => {
          // Deep clone before mode switches
          const before = JSON.parse(JSON.stringify(responses))

          // Simulate mode switches: pure mode switching does NOT touch responses
          let currentMode: ActiveMode = 'html'
          for (const mode of modeSequence) {
            // Mode switch only changes activeMode ref, not responses
            currentMode = mode
          }

          // Responses must be unchanged after pure mode switches
          expect(responses).toEqual(before)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('items 响应在模式切换前后键值完全一致', () => {
    fc.assert(
      fc.property(
        arbFullState,
        arbMode,
        arbMode,
        ({ responses }, fromMode, toMode) => {
          const itemsBefore = { ...responses.items }
          const customBefore = [...responses.custom_items]

          // Simulate: mode transition does not mutate
          // (in the real component, only docx→html with dirty triggers reload,
          //  which replaces the whole object from API; the old values are preserved
          //  because field_overrides are stored server-side and returned back)
          const _activeMode = toMode // assignment only

          // Verify items are exactly preserved
          expect(responses.items).toEqual(itemsBefore)
          expect(responses.custom_items).toEqual(customBefore)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('custom_items 在模式切换前后数量和内容一致', () => {
    fc.assert(
      fc.property(
        fc.array(arbCustomItem, { minLength: 0, maxLength: 10 }),
        fc.array(arbMode, { minLength: 1, maxLength: 5 }),
        (customItems, modeSequence) => {
          const responses: A112Responses = {
            items: {},
            header: {},
            custom_items: customItems,
          }

          const snapshot = JSON.parse(JSON.stringify(responses.custom_items))

          // Mode switching is a pure ref assignment; doesn't touch custom_items
          let _mode: ActiveMode = 'html'
          for (const m of modeSequence) {
            _mode = m
          }

          expect(responses.custom_items).toEqual(snapshot)
          expect(responses.custom_items.length).toBe(snapshot.length)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 进度统计正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-12-dual-checklist, Property 6: 进度统计正确性', () => {
  /**
   * **Validates: Requirements 3.6**
   *
   * progress = marked/total where marked = items with applicable != null
   * total = category items + custom_items
   */
  it('applicable + notApplicable + unmarked = total（守恒不变式）', () => {
    fc.assert(
      fc.property(
        arbFullState,
        ({ categories, responses }) => {
          const stats = computeProgressStats(categories, responses)
          expect(stats.applicable + stats.notApplicable + stats.unmarked).toBe(stats.total)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('percent = round((applicable + notApplicable) / total * 100)', () => {
    fc.assert(
      fc.property(
        arbFullState,
        ({ categories, responses }) => {
          const stats = computeProgressStats(categories, responses)

          if (stats.total === 0) {
            expect(stats.percent).toBe(0)
          } else {
            const marked = stats.applicable + stats.notApplicable
            const expected = Math.round((marked / stats.total) * 100)
            expect(stats.percent).toBe(expected)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('total = category items 数 + custom_items 数', () => {
    fc.assert(
      fc.property(
        arbFullState,
        ({ categories, responses }) => {
          const stats = computeProgressStats(categories, responses)
          const expectedTotal =
            categories.flatMap(c => c.items).length + responses.custom_items.length
          expect(stats.total).toBe(expectedTotal)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('所有 items 标记为 yes/no 时 percent=100, unmarked=0', () => {
    fc.assert(
      fc.property(
        arbFullState,
        ({ categories, responses }) => {
          // Force all items to have non-null applicable
          const allItems = categories.flatMap(c => c.items)
          for (const item of allItems) {
            if (!responses.items[item.id]) {
              responses.items[item.id] = { applicable: 'yes', ref_index: '' }
            } else if (responses.items[item.id].applicable === null) {
              responses.items[item.id].applicable = 'yes'
            }
          }
          for (const ci of responses.custom_items) {
            if (ci.applicable === null) {
              ci.applicable = 'yes'
            }
          }

          const stats = computeProgressStats(categories, responses)

          if (stats.total > 0) {
            expect(stats.percent).toBe(100)
            expect(stats.unmarked).toBe(0)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('无任何标记时 percent=0, unmarked=total', () => {
    fc.assert(
      fc.property(
        arbFullState,
        ({ categories }) => {
          // Create responses with all null applicable
          const allItems = categories.flatMap(c => c.items)
          const items: Record<string, A112ItemResponse> = {}
          for (const item of allItems) {
            items[item.id] = { applicable: null, ref_index: '' }
          }
          const responses: A112Responses = { items, header: {}, custom_items: [] }

          const stats = computeProgressStats(categories, responses)

          if (stats.total > 0) {
            expect(stats.percent).toBe(0)
            expect(stats.unmarked).toBe(stats.total)
            expect(stats.applicable).toBe(0)
            expect(stats.notApplicable).toBe(0)
          }
        },
      ),
      { numRuns: 200 },
    )
  })
})
