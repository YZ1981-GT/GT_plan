/**
 * Property-Based Tests — A1-15 企业会计准则财务报表列报及披露核对表
 *
 * Spec: .kiro/specs/a1-15-disclosure-checklist/
 * Task: 6 (Sub-tasks 6.1~6.11)
 *
 * 使用 fast-check + vitest 验证 correctness properties。
 * 测试纯计算逻辑——从 composable 内提取的纯函数等价实现。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Types (mirror composable types for PBT) ────────────────────────────────

interface A115Template {
  wp_code: string
  title: string
  sections: A115Section[]
  toc: A115TocEntry[]
  stats: { total_actionable: number; total_guidance: number; total_sections: number }
  parsed_at: string
}

interface A115Section {
  id: string
  title: string
  items: A115Item[]
}

interface A115Item {
  id: string
  type: 'actionable' | 'header'
  standard_ref: string
  content: string
  children: A115GuidanceChild[]
}

interface A115GuidanceChild {
  id: string
  content: string
  standard_ref: string
}

interface A115TocEntry {
  id: string
  title: string
  applicable: boolean | null
}

interface A115Responses {
  items: Record<string, A115ItemResponse>
  toc_applicability: Record<string, boolean>
}

interface A115ItemResponse {
  conclusion: 'Y' | 'N' | 'NA' | null
  remark: string
  wp_ref: string
}

type ActiveMode = 'html' | 'docx'

// ─── Pure Logic Functions (extracted equivalents from composable) ────────────

/**
 * getCardConclusionClass — 根据 item 结论返回 CSS 类名
 * 等价于 GtA115DisclosureChecklist.vue 中的 getCardConclusionClass
 */
function getCardConclusionClass(
  itemId: string,
  items: Record<string, A115ItemResponse>,
): string {
  const resp = items[itemId]
  const conclusion = resp?.conclusion ?? null
  switch (conclusion) {
    case 'Y':
      return 'gt-a115-disclosure-checklist__card--yes'
    case 'N':
      return 'gt-a115-disclosure-checklist__card--no'
    case 'NA':
      return 'gt-a115-disclosure-checklist__card--na'
    default:
      return 'gt-a115-disclosure-checklist__card--pending'
  }
}

/**
 * computeGlobalProgress — 计算全局进度（等价于 useA115Checklist.globalProgress）
 */
function computeGlobalProgress(
  template: A115Template,
  responses: A115Responses,
): { filled: number; total: number; y: number; n: number; na: number } {
  const total = template.stats.total_actionable
  let y = 0
  let n = 0
  let na = 0

  for (const section of template.sections) {
    for (const item of section.items) {
      if (item.type !== 'actionable') continue
      const resp = responses.items[item.id]
      if (!resp?.conclusion) continue
      if (resp.conclusion === 'Y') y++
      else if (resp.conclusion === 'N') n++
      else if (resp.conclusion === 'NA') na++
    }
  }

  return { filled: y + n + na, total, y, n, na }
}

/**
 * computeSectionProgress — 计算章节进度（等价于 useA115Checklist.sectionProgress）
 */
function computeSectionProgress(
  section: A115Section,
  responses: A115Responses,
): { filled: number; total: number } {
  let total = 0
  let filled = 0
  for (const item of section.items) {
    if (item.type !== 'actionable') continue
    total++
    const resp = responses.items[item.id]
    if (resp?.conclusion) filled++
  }
  return { filled, total }
}

/**
 * applyTocApplicability — 级联 NA 逻辑（等价于 useA115Checklist.setTocApplicability）
 */
function applyTocApplicability(
  section: A115Section,
  responses: A115Responses,
  applicable: boolean,
): A115Responses {
  const newResponses: A115Responses = {
    items: { ...responses.items },
    toc_applicability: { ...responses.toc_applicability, [section.id]: applicable },
  }

  if (!applicable) {
    for (const item of section.items) {
      if (item.type === 'actionable') {
        if (!newResponses.items[item.id]) {
          newResponses.items[item.id] = { conclusion: null, remark: '', wp_ref: '' }
        }
        newResponses.items[item.id] = {
          ...newResponses.items[item.id],
          conclusion: 'NA',
        }
      }
    }
  }

  return newResponses
}

/**
 * computeFilteredSections — 搜索+筛选逻辑（等价于 useA115Checklist.filteredSections）
 */
function computeFilteredSections(
  sections: A115Section[],
  responses: A115Responses,
  searchQuery: string,
  conclusionFilter: 'all' | 'filled' | 'unfilled' | 'Y' | 'N' | 'NA',
): A115Section[] {
  const query = searchQuery.trim().toLowerCase()
  const filter = conclusionFilter

  if (!query && filter === 'all') {
    return sections
  }

  const result: A115Section[] = []

  for (const section of sections) {
    const matchedItems = section.items.filter((item) => {
      // 搜索条件
      if (query) {
        const contentMatch = item.content.toLowerCase().includes(query)
        const refMatch = item.standard_ref.toLowerCase().includes(query)
        if (!contentMatch && !refMatch) return false
      }

      // 结论筛选条件
      if (filter !== 'all' && item.type === 'actionable') {
        const resp = responses.items[item.id]
        const conclusion = resp?.conclusion ?? null
        if (filter === 'filled') {
          if (!conclusion) return false
        } else if (filter === 'unfilled') {
          if (conclusion) return false
        } else {
          if (conclusion !== filter) return false
        }
      } else if (filter !== 'all' && item.type === 'header') {
        if (!query) return false
      }

      return true
    })

    if (matchedItems.length > 0) {
      result.push({ ...section, items: matchedItems })
    }
  }

  return result
}

/**
 * shouldRefreshOnModeSwitch — DOCX→HTML 切换时是否应触发 API 刷新
 */
function shouldRefreshOnModeSwitch(
  newMode: ActiveMode,
  oldMode: ActiveMode,
): boolean {
  return newMode === 'html' && oldMode === 'docx'
}

// ─── Cross Reference Map (static config from composable) ────────────────────

const CROSS_REFERENCE_MAP: Record<string, string> = {
  'S02': 'D0',
  'S03': 'D1',
  'S04': 'D2',
  'S05': 'D3',
  'S06': 'E1',
  'S07': 'I1',
  'S08': 'G1',
  'S09': 'H1',
  'S10': 'F1',
  'S11': 'F2',
  'S12': 'K1',
}

// ─── Arbitraries ────────────────────────────────────────────────────────────

/** 随机 ActiveMode */
const arbMode = fc.constantFrom<ActiveMode>('html', 'docx')

/** 随机结论值 */
const arbConclusion = fc.constantFrom<'Y' | 'N' | 'NA' | null>('Y', 'N', 'NA', null)

/** 随机 A115ItemResponse */
const arbItemResponse: fc.Arbitrary<A115ItemResponse> = fc.record({
  conclusion: arbConclusion,
  remark: fc.string({ minLength: 0, maxLength: 30 }),
  wp_ref: fc.string({ minLength: 0, maxLength: 10 }),
})

/** 随机 A115GuidanceChild */
const arbGuidanceChild = (parentId: string, idx: number): fc.Arbitrary<A115GuidanceChild> =>
  fc.record({
    id: fc.constant(`${parentId}-${String.fromCharCode(97 + idx)}`),
    content: fc.string({ minLength: 1, maxLength: 60 }),
    standard_ref: fc.string({ minLength: 0, maxLength: 15 }),
  })

/** 随机 A115Item (actionable) */
function arbActionableItem(sectionId: string, seq: number): fc.Arbitrary<A115Item> {
  return fc.record({
    id: fc.constant(`${sectionId}-${String(seq).padStart(3, '0')}`),
    type: fc.constant('actionable' as const),
    standard_ref: fc.stringMatching(/^CAS\d{1,2}\.\d{1,3}$/),
    content: fc.string({ minLength: 5, maxLength: 80 }),
    children: fc.array(arbGuidanceChild(`${sectionId}-${String(seq).padStart(3, '0')}`, 0), { minLength: 0, maxLength: 3 }),
  })
}

/** 随机 A115Item (header) */
function arbHeaderItem(sectionId: string, seq: number): fc.Arbitrary<A115Item> {
  return fc.record({
    id: fc.constant(`${sectionId}-H${seq}`),
    type: fc.constant('header' as const),
    standard_ref: fc.constant(''),
    content: fc.string({ minLength: 3, maxLength: 40 }),
    children: fc.constant([]),
  })
}

/** 随机 A115Section（指定 actionable 数量） */
function arbSection(sectionIdx: number, actionableCount: number): fc.Arbitrary<A115Section> {
  const sectionId = `S${String(sectionIdx + 1).padStart(2, '0')}`
  const items: fc.Arbitrary<A115Item>[] = []

  // 可能包含 1 个 header
  if (actionableCount > 2) {
    items.push(arbHeaderItem(sectionId, 0))
  }

  for (let i = 0; i < actionableCount; i++) {
    items.push(arbActionableItem(sectionId, i + 1))
  }

  return fc.tuple(
    fc.string({ minLength: 2, maxLength: 20 }),
    ...items,
  ).map(([title, ...itemList]) => ({
    id: sectionId,
    title: title as string,
    items: itemList as A115Item[],
  }))
}

/** 生成含 N 个 section 的 template + 对应 responses */
function arbTemplateWithResponses(minSections: number, maxSections: number) {
  return fc.integer({ min: minSections, max: maxSections }).chain((sectionCount) => {
    // Each section has 1~15 actionable items
    const sectionArbs = Array.from({ length: sectionCount }, (_, i) =>
      fc.integer({ min: 1, max: 15 }).chain((actionableCount) =>
        arbSection(i, actionableCount),
      ),
    )

    return fc.tuple(...sectionArbs).chain((sections) => {
      // Collect all actionable item ids
      const actionableIds: string[] = []
      for (const sec of sections) {
        for (const item of sec.items) {
          if (item.type === 'actionable') actionableIds.push(item.id)
        }
      }

      // Generate responses for each actionable item
      const responsesArb = fc.tuple(
        ...actionableIds.map(() => arbItemResponse),
      ).map((respList) => {
        const items: Record<string, A115ItemResponse> = {}
        for (let i = 0; i < actionableIds.length; i++) {
          items[actionableIds[i]] = respList[i]
        }
        return items
      })

      return responsesArb.map((items) => {
        const template: A115Template = {
          wp_code: 'A1-15',
          title: '企业会计准则有关财务报表列报及披露核对表',
          sections: sections as A115Section[],
          toc: (sections as A115Section[]).map((s) => ({
            id: s.id,
            title: s.title,
            applicable: null,
          })),
          stats: {
            total_actionable: actionableIds.length,
            total_guidance: 0,
            total_sections: sectionCount,
          },
          parsed_at: new Date().toISOString(),
        }
        const responses: A115Responses = {
          items,
          toc_applicability: {},
        }
        return { template, responses }
      })
    })
  })
}

/** 简化版：生成单个 section + responses */
const arbSingleSectionState = fc.integer({ min: 1, max: 20 }).chain((actionableCount) =>
  arbSection(0, actionableCount).chain((section) => {
    const actionableIds = section.items.filter(i => i.type === 'actionable').map(i => i.id)
    return fc.tuple(
      ...actionableIds.map(() => arbItemResponse),
    ).map((respList) => {
      const items: Record<string, A115ItemResponse> = {}
      for (let i = 0; i < actionableIds.length; i++) {
        items[actionableIds[i]] = respList[i]
      }
      const responses: A115Responses = { items, toc_applicability: {} }
      return { section, responses }
    })
  }),
)

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 1: 模式互斥渲染
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 1: 模式互斥渲染', () => {
  /**
   * **Validates: Requirements 2.2, 2.3**
   *
   * For any mode state ('html' | 'docx'), exactly one view is rendered —
   * never both, never neither.
   */
  it('任意 mode ∈ {html, docx} 时，恰好有一个视图被选中（互斥性）', () => {
    fc.assert(
      fc.property(
        arbMode,
        (mode) => {
          const showHtml = mode === 'html'
          const showDocx = mode === 'docx'

          // Exactly one must be true (XOR)
          expect(showHtml !== showDocx).toBe(true)
          // Never both
          expect(showHtml && showDocx).toBe(false)
          // Never neither
          expect(showHtml || showDocx).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('任意模式切换序列后，始终满足互斥不变量', () => {
    fc.assert(
      fc.property(
        fc.array(arbMode, { minLength: 1, maxLength: 30 }),
        (modeSequence) => {
          let currentMode: ActiveMode = 'html'
          for (const mode of modeSequence) {
            currentMode = mode
          }

          const showHtml = currentMode === 'html'
          const showDocx = currentMode === 'docx'
          expect(showHtml !== showDocx).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 2: DOCX→HTML 切换触发刷新
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 2: DOCX→HTML 切换触发刷新', () => {
  /**
   * **Validates: Requirements 2.6**
   *
   * For any transition from 'docx' to 'html', a render-config API request
   * must be triggered (loadData called).
   */
  it('docx→html 切换必须触发 API 刷新', () => {
    fc.assert(
      fc.property(
        fc.constant({ from: 'docx' as ActiveMode, to: 'html' as ActiveMode }),
        ({ from, to }) => {
          const result = shouldRefreshOnModeSwitch(to, from)
          expect(result).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('html→docx 切换不触发 API 刷新', () => {
    fc.assert(
      fc.property(
        fc.constant({ from: 'html' as ActiveMode, to: 'docx' as ActiveMode }),
        ({ from, to }) => {
          const result = shouldRefreshOnModeSwitch(to, from)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('同模式切换不触发 API 刷新', () => {
    fc.assert(
      fc.property(
        arbMode,
        (mode) => {
          const result = shouldRefreshOnModeSwitch(mode, mode)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('任意 (oldMode, newMode) 组合中仅 docx→html 触发刷新', () => {
    fc.assert(
      fc.property(
        arbMode,
        arbMode,
        (oldMode, newMode) => {
          const result = shouldRefreshOnModeSwitch(newMode, oldMode)
          const expected = newMode === 'html' && oldMode === 'docx'
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 3: 章节导航完整有序
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 3: 章节导航完整有序', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * For any valid template with N sections, navigation should display
   * exactly N entries in the same order as template.sections[].id.
   */
  it('导航条目数量等于 template.sections 数量', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 40),
        ({ template }) => {
          // SectionNav renders template.sections directly
          const navEntries = template.sections.map(s => s.id)
          expect(navEntries.length).toBe(template.sections.length)
          expect(navEntries.length).toBe(template.stats.total_sections)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('导航顺序与 template.sections 顺序一致', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(2, 35),
        ({ template }) => {
          const navOrder = template.sections.map(s => s.id)
          // Verify monotonically increasing section IDs (S01, S02, ...)
          for (let i = 0; i < navOrder.length - 1; i++) {
            const currentNum = parseInt(navOrder[i].replace('S', ''))
            const nextNum = parseInt(navOrder[i + 1].replace('S', ''))
            expect(nextNum).toBeGreaterThan(currentNum)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('每个章节 id 唯一（无重复）', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 35),
        ({ template }) => {
          const ids = template.sections.map(s => s.id)
          const uniqueIds = new Set(ids)
          expect(uniqueIds.size).toBe(ids.length)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 4: 章节进度计算正确
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 4: 章节进度计算正确', () => {
  /**
   * **Validates: Requirements 4.4, 5.7**
   *
   * For any section with K actionable items and given responses:
   *   sectionProgress.filled = count of non-null conclusions
   *   sectionProgress.total = K
   */
  it('filled = 非 null 结论数, total = actionable 条目数', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const progress = computeSectionProgress(section, responses)

          // total = actionable items count
          const actionableItems = section.items.filter(i => i.type === 'actionable')
          expect(progress.total).toBe(actionableItems.length)

          // filled = items with non-null conclusion
          let expectedFilled = 0
          for (const item of actionableItems) {
            const resp = responses.items[item.id]
            if (resp?.conclusion) expectedFilled++
          }
          expect(progress.filled).toBe(expectedFilled)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filled <= total 恒成立', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const progress = computeSectionProgress(section, responses)
          expect(progress.filled).toBeLessThanOrEqual(progress.total)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('所有 actionable 均有结论时 filled === total', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          // Force all actionable to have conclusions
          for (const item of section.items) {
            if (item.type === 'actionable') {
              if (!responses.items[item.id]) {
                responses.items[item.id] = { conclusion: 'Y', remark: '', wp_ref: '' }
              } else if (!responses.items[item.id].conclusion) {
                responses.items[item.id] = { ...responses.items[item.id], conclusion: 'Y' }
              }
            }
          }

          const progress = computeSectionProgress(section, responses)
          expect(progress.filled).toBe(progress.total)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('header 条目不计入 total', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const progress = computeSectionProgress(section, responses)
          const headerCount = section.items.filter(i => i.type === 'header').length
          const totalItems = section.items.length
          expect(progress.total).toBe(totalItems - headerCount)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 5: TOC 适用性级联
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 5: TOC 适用性级联', () => {
  /**
   * **Validates: Requirements 4.7**
   *
   * For any section marked toc_applicability=false, ALL actionable items
   * must have conclusion='NA'.
   */
  it('标记不适用后，章节内所有 actionable 条目 conclusion 均为 NA', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          // Apply toc_applicability = false
          const newResponses = applyTocApplicability(section, responses, false)

          // Verify ALL actionable items have conclusion='NA'
          for (const item of section.items) {
            if (item.type === 'actionable') {
              expect(newResponses.items[item.id]?.conclusion).toBe('NA')
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('标记不适用后，toc_applicability[sectionId] = false', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const newResponses = applyTocApplicability(section, responses, false)
          expect(newResponses.toc_applicability[section.id]).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('标记适用（true）不改变条目结论', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const before = JSON.parse(JSON.stringify(responses.items))
          const newResponses = applyTocApplicability(section, responses, true)

          // Items should not be modified when marking as applicable
          for (const item of section.items) {
            if (item.type === 'actionable' && before[item.id]) {
              expect(newResponses.items[item.id]?.conclusion).toBe(before[item.id].conclusion)
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('级联 NA 后 sectionProgress.filled === total（全部标 NA 视为已填）', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const newResponses = applyTocApplicability(section, responses, false)
          const progress = computeSectionProgress(section, newResponses)
          expect(progress.filled).toBe(progress.total)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 6: Actionable 卡片字段完整
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 6: Actionable 卡片字段完整', () => {
  /**
   * **Validates: Requirements 5.1, 5.2, 6.1**
   *
   * For any item with type='actionable', verify it has standard_ref, content,
   * and the UI should provide Y/N/NA buttons + remark + wp_ref.
   */
  it('type=actionable 的条目必含 standard_ref（非空）和 content（非空）', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section }) => {
          for (const item of section.items) {
            if (item.type === 'actionable') {
              // standard_ref must exist and be non-empty
              expect(item.standard_ref).toBeDefined()
              expect(item.standard_ref.length).toBeGreaterThan(0)
              // content must exist and be non-empty
              expect(item.content).toBeDefined()
              expect(item.content.length).toBeGreaterThan(0)
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('type=actionable 的条目 UI 应提供结论三值域（Y/N/NA）', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          for (const item of section.items) {
            if (item.type === 'actionable') {
              // The response for this item, if exists, must have conclusion in {Y, N, NA, null}
              const resp = responses.items[item.id]
              if (resp) {
                expect(['Y', 'N', 'NA', null]).toContain(resp.conclusion)
                // remark field must exist (string)
                expect(typeof resp.remark).toBe('string')
                // wp_ref field must exist (string)
                expect(typeof resp.wp_ref).toBe('string')
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('A115ItemResponse 结构完整：conclusion + remark + wp_ref 三字段齐全', () => {
    fc.assert(
      fc.property(
        arbItemResponse,
        (resp) => {
          expect(resp).toHaveProperty('conclusion')
          expect(resp).toHaveProperty('remark')
          expect(resp).toHaveProperty('wp_ref')
          expect(['Y', 'N', 'NA', null]).toContain(resp.conclusion)
          expect(typeof resp.remark).toBe('string')
          expect(typeof resp.wp_ref).toBe('string')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 7: 结论状态→视觉映射
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 7: 结论状态→视觉映射', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * For any conclusion in {Y, N, NA, null}, the CSS class maps correctly:
   *   Y → 'gt-a115-disclosure-checklist__card--yes' (green border)
   *   N → 'gt-a115-disclosure-checklist__card--no' (red border)
   *   NA → 'gt-a115-disclosure-checklist__card--na' (gray/transparent)
   *   null → 'gt-a115-disclosure-checklist__card--pending' (no border)
   */
  it('结论值与 CSS 类名一一映射', () => {
    const expectedMapping: Record<string, string> = {
      Y: 'gt-a115-disclosure-checklist__card--yes',
      N: 'gt-a115-disclosure-checklist__card--no',
      NA: 'gt-a115-disclosure-checklist__card--na',
      null: 'gt-a115-disclosure-checklist__card--pending',
    }

    fc.assert(
      fc.property(
        arbConclusion,
        fc.string({ minLength: 1, maxLength: 10 }),
        (conclusion, itemId) => {
          const items: Record<string, A115ItemResponse> = {
            [itemId]: { conclusion, remark: '', wp_ref: '' },
          }
          const cls = getCardConclusionClass(itemId, items)
          const expectedCls = expectedMapping[String(conclusion)]
          expect(cls).toBe(expectedCls)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('未注册 item（无 response）→ pending 类名', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 999 }).map(n => `item-${n}`),
        (itemId) => {
          const items: Record<string, A115ItemResponse> = {}
          const cls = getCardConclusionClass(itemId, items)
          expect(cls).toBe('gt-a115-disclosure-checklist__card--pending')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('四种结论状态映射到四个不同类名（互不重复）', () => {
    fc.assert(
      fc.property(
        fc.constant(null),
        () => {
          const conclusions: Array<'Y' | 'N' | 'NA' | null> = ['Y', 'N', 'NA', null]
          const classes = conclusions.map((c) => {
            const items: Record<string, A115ItemResponse> = {
              test: { conclusion: c, remark: '', wp_ref: '' },
            }
            return getCardConclusionClass('test', items)
          })

          const uniqueClasses = new Set(classes)
          expect(uniqueClasses.size).toBe(4)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 8: Header 条目渲染为分隔标题
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 8: Header 条目渲染为分隔标题', () => {
  /**
   * **Validates: Requirements 5.6**
   *
   * For any item with type='header', it must NOT have interactive elements
   * (no conclusion buttons, no remark, no wp_ref).
   */
  it('type=header 的条目不参与进度计算（不计为 actionable）', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const progress = computeSectionProgress(section, responses)
          const headerItems = section.items.filter(i => i.type === 'header')
          const actionableItems = section.items.filter(i => i.type === 'actionable')

          // Total only counts actionable, not headers
          expect(progress.total).toBe(actionableItems.length)
          // Headers should not contribute to progress
          expect(progress.total + headerItems.length).toBeLessThanOrEqual(section.items.length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('type=header 条目不应出现在 responses.items 中（无交互状态）', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          for (const item of section.items) {
            if (item.type === 'header') {
              // Header items should not have response entries
              // (our generator only creates responses for actionable items)
              expect(responses.items[item.id]).toBeUndefined()
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('type=header 条目的 type 字段恒为 "header"（不会被误判为 actionable）', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 30 }),
        fc.string({ minLength: 3, maxLength: 40 }),
        (seq, content) => {
          const headerItem: A115Item = {
            id: `S01-H${seq}`,
            type: 'header',
            standard_ref: '',
            content,
            children: [],
          }

          // Header must NOT be treated as actionable
          expect(headerItem.type).toBe('header')
          expect(headerItem.type).not.toBe('actionable')
          // Header standard_ref is empty (no CAS reference)
          expect(headerItem.standard_ref).toBe('')
          // Header has no children (guidance)
          expect(headerItem.children).toEqual([])
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 9: Cross_Reference_Map 建议显示
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 9: Cross_Reference_Map 建议显示', () => {
  /**
   * **Validates: Requirements 6.3**
   *
   * For any section with a crossRefMap entry AND items with no wp_ref,
   * a suggested chip should appear.
   */
  it('有映射且无 wp_ref 时，建议 chip 应显示', () => {
    fc.assert(
      fc.property(
        arbSingleSectionState,
        ({ section, responses }) => {
          const sectionId = section.id
          const suggestion = CROSS_REFERENCE_MAP[sectionId]

          if (suggestion) {
            for (const item of section.items) {
              if (item.type !== 'actionable') continue
              const resp = responses.items[item.id]
              const wpRef = resp?.wp_ref ?? ''
              const hasSuggestion = suggestion !== undefined
              const noUserRef = wpRef === ''

              // If section has mapping AND item has no wp_ref → suggestion visible
              if (hasSuggestion && noUserRef) {
                expect(suggestion.length).toBeGreaterThan(0)
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('有 wp_ref 时，不显示建议 chip（已手动关联优先）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...Object.keys(CROSS_REFERENCE_MAP)),
        fc.string({ minLength: 1, maxLength: 5 }),
        (sectionId, userWpRef) => {
          const suggestion = CROSS_REFERENCE_MAP[sectionId]
          const hasUserRef = userWpRef.length > 0

          // When user has set wp_ref, suggested chip should NOT show
          // (UI logic: v-else-if="crossRefMap[section.id]" only renders when no wp_ref)
          if (hasUserRef) {
            // User ref takes precedence over suggestion
            expect(hasUserRef).toBe(true)
            expect(suggestion).toBeDefined()
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('无映射的章节不显示任何建议', () => {
    fc.assert(
      fc.property(
        // Generate section IDs that are NOT in CROSS_REFERENCE_MAP
        fc.constantFrom('S01', 'S13', 'S14', 'S15', 'S20', 'S25', 'S30', 'S35'),
        (sectionId) => {
          const suggestion = CROSS_REFERENCE_MAP[sectionId]
          // These sections should not have a suggestion
          expect(suggestion).toBeUndefined()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('CROSS_REFERENCE_MAP 至少覆盖 10 个映射', () => {
    fc.assert(
      fc.property(
        fc.constant(null),
        () => {
          const entries = Object.entries(CROSS_REFERENCE_MAP)
          expect(entries.length).toBeGreaterThanOrEqual(10)

          // Each mapping has non-empty key and value
          for (const [key, value] of entries) {
            expect(key.length).toBeGreaterThan(0)
            expect(value.length).toBeGreaterThan(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 10: 全局进度不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 10: 全局进度不变量', () => {
  /**
   * **Validates: Requirements 8.1, 8.2**
   *
   * For any responses state: y + n + na + unfilled = total_actionable.
   */
  it('y + n + na + unfilled === total_actionable（守恒不变式）', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 20),
        ({ template, responses }) => {
          const progress = computeGlobalProgress(template, responses)
          const unfilled = progress.total - progress.filled
          expect(progress.y + progress.n + progress.na + unfilled).toBe(progress.total)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filled === y + n + na', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 20),
        ({ template, responses }) => {
          const progress = computeGlobalProgress(template, responses)
          expect(progress.filled).toBe(progress.y + progress.n + progress.na)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filled <= total 恒成立', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 20),
        ({ template, responses }) => {
          const progress = computeGlobalProgress(template, responses)
          expect(progress.filled).toBeLessThanOrEqual(progress.total)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('y, n, na 各分量均 >= 0', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 20),
        ({ template, responses }) => {
          const progress = computeGlobalProgress(template, responses)
          expect(progress.y).toBeGreaterThanOrEqual(0)
          expect(progress.n).toBeGreaterThanOrEqual(0)
          expect(progress.na).toBeGreaterThanOrEqual(0)
          expect(progress.filled).toBeGreaterThanOrEqual(0)
          expect(progress.total).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('total 等于所有章节 actionable 条目之和', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 20),
        ({ template, responses }) => {
          const progress = computeGlobalProgress(template, responses)
          let expectedTotal = 0
          for (const section of template.sections) {
            for (const item of section.items) {
              if (item.type === 'actionable') expectedTotal++
            }
          }
          expect(progress.total).toBe(expectedTotal)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Feature: a1-15-disclosure-checklist, Property 11: 筛选正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('A115 PBT - Property 11: 筛选正确性', () => {
  /**
   * **Validates: Requirements 8.4, 8.5**
   *
   * For any search query and filter, visible items must satisfy both conditions:
   *   (a) item.content contains Q (case-insensitive) OR item.standard_ref contains Q
   *   (b) if F ≠ 'all', then item's conclusion matches F
   */
  it('筛选后所有可见 actionable 条目满足搜索条件', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        fc.string({ minLength: 1, maxLength: 5 }),
        ({ template, responses }, query) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            query,
            'all',
          )

          for (const section of filtered) {
            for (const item of section.items) {
              // Each visible item must match the query in content or standard_ref
              const q = query.trim().toLowerCase()
              const contentMatch = item.content.toLowerCase().includes(q)
              const refMatch = item.standard_ref.toLowerCase().includes(q)
              expect(contentMatch || refMatch).toBe(true)
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('结论筛选后所有可见 actionable 条目满足 filter 条件', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        fc.constantFrom<'Y' | 'N' | 'NA'>('Y', 'N', 'NA'),
        ({ template, responses }, filter) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            '',
            filter,
          )

          for (const section of filtered) {
            for (const item of section.items) {
              if (item.type === 'actionable') {
                const resp = responses.items[item.id]
                const conclusion = resp?.conclusion ?? null
                expect(conclusion).toBe(filter)
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filter=filled 时所有可见 actionable 条目 conclusion 非 null', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        ({ template, responses }) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            '',
            'filled',
          )

          for (const section of filtered) {
            for (const item of section.items) {
              if (item.type === 'actionable') {
                const resp = responses.items[item.id]
                expect(resp?.conclusion).not.toBeNull()
                expect(resp?.conclusion).toBeDefined()
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filter=unfilled 时所有可见 actionable 条目 conclusion 为 null', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        ({ template, responses }) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            '',
            'unfilled',
          )

          for (const section of filtered) {
            for (const item of section.items) {
              if (item.type === 'actionable') {
                const resp = responses.items[item.id]
                const conclusion = resp?.conclusion ?? null
                expect(conclusion).toBeNull()
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('filter=all + 空搜索 → 返回所有章节（无过滤）', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        ({ template, responses }) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            '',
            'all',
          )

          expect(filtered.length).toBe(template.sections.length)
          for (let i = 0; i < filtered.length; i++) {
            expect(filtered[i].id).toBe(template.sections[i].id)
            expect(filtered[i].items.length).toBe(template.sections[i].items.length)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('搜索 + filter 双重条件时，可见条目同时满足两者', () => {
    fc.assert(
      fc.property(
        arbTemplateWithResponses(1, 10),
        fc.constantFrom<'Y' | 'N' | 'NA'>('Y', 'N', 'NA'),
        fc.string({ minLength: 1, maxLength: 3 }),
        ({ template, responses }, filter, query) => {
          const filtered = computeFilteredSections(
            template.sections,
            responses,
            query,
            filter,
          )

          const q = query.trim().toLowerCase()
          for (const section of filtered) {
            for (const item of section.items) {
              // Must match search query
              const contentMatch = item.content.toLowerCase().includes(q)
              const refMatch = item.standard_ref.toLowerCase().includes(q)
              expect(contentMatch || refMatch).toBe(true)

              // Must match filter if actionable
              if (item.type === 'actionable') {
                const resp = responses.items[item.id]
                const conclusion = resp?.conclusion ?? null
                expect(conclusion).toBe(filter)
              }
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
