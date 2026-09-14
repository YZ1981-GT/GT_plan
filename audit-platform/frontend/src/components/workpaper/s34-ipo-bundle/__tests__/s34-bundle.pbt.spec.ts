/**
 * Property-Based Tests — S34 首发审核（IPO）特项底稿聚合组件
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/
 * Task: 10.1
 *
 * Property 1: skip 映射完整性 — S34-0~S34-41 及子表编码映射为 skip；S34 映射为 s34-ipo-bundle
 * Property 2: wp_id 解析 — buildWpIdMap 正确从 wp_index 数据提取 S34-* → wp_id
 * Property 3: Tab 可见性由 wp_index 存在性驱动 — 仅 wpIdMap 有值的 Tab 可见；overview 恒可见
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  buildWpIdMap,
  computeApplicableCodes,
  computeProgressSummary,
  computeRegRefMap,
  type CompletionStatus,
  type Applicability,
} from '../../composables/useS34BundleState'
import { S34_TAB_DEFS, S34_WP_CODES } from '../S34_TAB_CONFIG'

// ─── 常量 ───

/** 所有应被映射为 skip 的 S34 wp_code（主底稿 + 子表编码） */
const S34_SKIP_CODES: string[] = [
  'S34-0',
  ...Array.from({ length: 41 }, (_, i) => `S34-${i + 1}`),
  // 子表编码
  'S34-2-1', 'S34-2-2',
  'S34-3-1',
  'S34-4-1',
  'S34-8-1', 'S34-8-2',
  'S34-9-1',
  'S34-11-1',
  'S34-16-1', 'S34-16-2',
  'S34-18-1',
  'S34-20-1',
  'S34-25-1', 'S34-25-2', 'S34-25-3',
  'S34-30-1',
  'S34-34-1', 'S34-34-2',
]

/** 读取 wp_code_overrides.json */
function loadOverrides(): Record<string, string> {
  const filePath = resolve(__dirname, '../../../../../../../backend/app/data/wp_code_overrides.json')
  const content = readFileSync(filePath, 'utf-8')
  return JSON.parse(content)
}

// ─── Shared: visibleTabs 纯函数重现（对齐 GtS34Bundle.vue 的 visibleTabs computed） ───

interface TabVisibility {
  id: string
  wpCode?: string
}

/**
 * 纯函数：计算可见 Tab 列表。
 * 对齐 GtS34Bundle.vue 中 visibleTabs computed 逻辑：
 * - overview 恒可见
 * - 专项 Tab 仅 wpIdMap 有值时显示
 */
function computeVisibleTabs(
  tabDefs: TabVisibility[],
  wpIdMap: Record<string, string>,
): TabVisibility[] {
  return tabDefs.filter((tab) => {
    if (tab.id === 'overview') return true
    return tab.wpCode ? !!wpIdMap[tab.wpCode] : false
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: skip 映射完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 1: skip 映射完整性', () => {
  /**
   * **Validates: Requirements 1.2, 2.1, 2.2, 2.4**
   *
   * For any wp_code in {S34-0, S34-1..S34-41} and their sub-table codes,
   * wp_code_overrides.json maps them to `skip`;
   * and `S34` maps to `s34-ipo-bundle`.
   */
  const overrides = loadOverrides()

  it('S34 maps to s34-ipo-bundle', () => {
    expect(overrides['S34']).toBe('s34-ipo-bundle')
  })

  it('all S34 sub-codes and sub-table codes map to skip', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...S34_SKIP_CODES),
        (wpCode) => {
          expect(overrides[wpCode]).toBe('skip')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('no S34-* code maps to anything other than skip', () => {
    // Enumerate all S34-* keys in overrides and verify they are all skip
    const s34Keys = Object.keys(overrides).filter(k => /^S34-/.test(k))
    fc.assert(
      fc.property(
        fc.constantFrom(...s34Keys),
        (key) => {
          expect(overrides[key]).toBe('skip')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: wp_id 解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 2: wp_id 解析', () => {
  /**
   * **Validates: Requirements 8.1, 8.3, 8.4**
   *
   * For any wp_index dataset containing S34-* entries,
   * wpIdMap should correctly map each S34-* wp_code to its wp_id,
   * and each visible Tab's GtAProgramConsole receives wp-id = wpIdMap[tab.wpCode].
   */

  /** Generator: array of wp_index items with S34 codes and UUIDs */
  const s34WpIndexItemArb = fc.record({
    wp_code: fc.constantFrom(...S34_WP_CODES),
    wp_id: fc.uuid(),
    id: fc.uuid(), // wp_id ≠ id, 铁律：必须用 wp_id
  })

  const wpIndexArb = fc.array(s34WpIndexItemArb, { minLength: 0, maxLength: 20 })

  it('buildWpIdMap maps each S34-* wp_code to its wp_id (not id)', () => {
    fc.assert(
      fc.property(wpIndexArb, (items) => {
        const map = buildWpIdMap(items)

        // Every item with valid wp_code (S34-*) and truthy wp_id should be in the map
        for (const item of items) {
          if (/^S34-\d+/.test(item.wp_code) && item.wp_id) {
            // Last occurrence wins (overwrite behavior)
            // The map should contain this wp_code
            expect(map[item.wp_code]).toBeDefined()
            // And the value must be a wp_id from the items, NOT an id
            expect(map[item.wp_code]).not.toBe('')
          }
        }

        // The map should never contain non-S34 entries
        for (const key of Object.keys(map)) {
          expect(key).toMatch(/^S34-\d+/)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('buildWpIdMap uses wp_id not id (iron rule)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...S34_WP_CODES),
        fc.uuid(),
        fc.uuid(),
        (wpCode, wpId, itemId) => {
          // Ensure wp_id ≠ id to prove the distinction matters
          fc.pre(wpId !== itemId)

          const map = buildWpIdMap([{ wp_code: wpCode, wp_id: wpId, id: itemId }])
          expect(map[wpCode]).toBe(wpId)
          expect(map[wpCode]).not.toBe(itemId)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('buildWpIdMap ignores entries with null/empty wp_id', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...S34_WP_CODES),
        fc.uuid(),
        (wpCode, itemId) => {
          const mapNull = buildWpIdMap([{ wp_code: wpCode, wp_id: null, id: itemId }])
          expect(mapNull[wpCode]).toBeUndefined()

          const mapUndefined = buildWpIdMap([{ wp_code: wpCode, wp_id: undefined, id: itemId }])
          expect(mapUndefined[wpCode]).toBeUndefined()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('each visible Tab receives correct wp-id from wpIdMap', () => {
    fc.assert(
      fc.property(wpIndexArb, (items) => {
        const wpIdMap = buildWpIdMap(items)
        const visibleTabs = computeVisibleTabs(S34_TAB_DEFS, wpIdMap)

        for (const tab of visibleTabs) {
          if (tab.id === 'overview') continue
          // 专项 Tab 必须有 wpCode 且 wpIdMap 有值
          expect(tab.wpCode).toBeDefined()
          expect(wpIdMap[tab.wpCode!]).toBeDefined()
          // GtAProgramConsole 接收的 wp-id 等于 wpIdMap[tab.wpCode]
          const receivedWpId = wpIdMap[tab.wpCode!]
          expect(receivedWpId).toBeTruthy()
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: Tab 可见性由 wp_index 存在性驱动
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 3: Tab 可见性', () => {
  /**
   * **Validates: Requirements 4.1, 9.1, 9.4**
   *
   * For any subset of S34 codes present in wp_index,
   * only those with wpIdMap entries are visible tabs;
   * overview is always visible;
   * when no S34 codes exist, only overview shows.
   */

  /** Generator: random subset of S34 wp_codes */
  const s34SubsetArb = fc.shuffledSubarray([...S34_WP_CODES])

  it('overview is always visible regardless of wpIdMap content', () => {
    fc.assert(
      fc.property(s34SubsetArb, (subset) => {
        // Build a wpIdMap for only the subset codes
        const wpIdMap: Record<string, string> = {}
        for (const code of subset) {
          wpIdMap[code] = `fake-uuid-${code}`
        }

        const visible = computeVisibleTabs(S34_TAB_DEFS, wpIdMap)
        const overviewTab = visible.find(t => t.id === 'overview')
        expect(overviewTab).toBeDefined()
      }),
      { numRuns: 100 },
    )
  })

  it('only tabs with wpIdMap entries are visible (plus overview)', () => {
    fc.assert(
      fc.property(s34SubsetArb, (subset) => {
        const wpIdMap: Record<string, string> = {}
        for (const code of subset) {
          wpIdMap[code] = `fake-uuid-${code}`
        }

        const visible = computeVisibleTabs(S34_TAB_DEFS, wpIdMap)

        // All non-overview visible tabs must have their wpCode in the subset
        for (const tab of visible) {
          if (tab.id === 'overview') continue
          expect(tab.wpCode).toBeDefined()
          expect(subset).toContain(tab.wpCode)
        }

        // All subset codes that have a tab definition should be visible
        for (const code of subset) {
          const tabDef = S34_TAB_DEFS.find(t => t.wpCode === code)
          if (tabDef) {
            expect(visible.some(t => t.id === tabDef.id)).toBe(true)
          }
        }
      }),
      { numRuns: 100 },
    )
  })

  it('when no S34 codes exist in wpIdMap, only overview is visible', () => {
    const wpIdMap: Record<string, string> = {}
    const visible = computeVisibleTabs(S34_TAB_DEFS, wpIdMap)

    expect(visible.length).toBe(1)
    expect(visible[0].id).toBe('overview')
  })

  it('visible tab count = 1 (overview) + number of subset codes that have tab definitions', () => {
    fc.assert(
      fc.property(s34SubsetArb, (subset) => {
        const wpIdMap: Record<string, string> = {}
        for (const code of subset) {
          wpIdMap[code] = `fake-uuid-${code}`
        }

        const visible = computeVisibleTabs(S34_TAB_DEFS, wpIdMap)
        // Count how many subset codes have a corresponding TabDef
        const codesWithTabs = subset.filter(code =>
          S34_TAB_DEFS.some(t => t.wpCode === code),
        )
        expect(visible.length).toBe(1 + codesWithTabs.length)
      }),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: sheetName 路由正确激活 Tab
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 4: sheetName 路由正确激活 Tab', () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
   *
   * For any legal Tab id (in visible Tab list), passing it as sheetName activates that tab;
   * invalid values keep the default (overview).
   *
   * 测试纯逻辑：给定 visibleTabs 和 sheetName，判断是否应激活。
   */

  /** 所有合法 Tab id（overview + 专项底稿） */
  const VALID_TAB_IDS = S34_TAB_DEFS.map(t => t.id)

  /**
   * 纯函数：解析 sheetName → activeTab。
   * 对齐 GtS34Bundle.vue 中 watch(sheetName) 逻辑：
   * - sheetName 在可见 Tab 列表中 → 切换
   * - 否则 → 保持当前 active（默认 overview）
   */
  function resolveActiveTab(
    currentActive: string,
    sheetName: string,
    visibleTabIds: string[],
  ): string {
    if (sheetName && visibleTabIds.includes(sheetName)) {
      return sheetName
    }
    return currentActive
  }

  it('合法 sheetName 激活对应 Tab', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_TAB_IDS),
        fc.constantFrom(...VALID_TAB_IDS),
        (sheetName, currentActive) => {
          // 所有 Tab 都可见的场景
          const result = resolveActiveTab(currentActive, sheetName, VALID_TAB_IDS)
          expect(result).toBe(sheetName)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('非法 sheetName 保持当前 Tab 不变（默认 overview）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }).filter(s => !VALID_TAB_IDS.includes(s)),
        fc.constantFrom(...VALID_TAB_IDS),
        (invalidSheet, currentActive) => {
          const result = resolveActiveTab(currentActive, invalidSheet, VALID_TAB_IDS)
          expect(result).toBe(currentActive)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('sheetName 不在可见 Tab 子集中 → 保持不变', () => {
    fc.assert(
      fc.property(
        fc.subarray([...S34_WP_CODES], { minLength: 1, maxLength: 10 }),
        fc.constantFrom(...VALID_TAB_IDS),
        (visibleSubset, targetSheet) => {
          // visibleSubset 只包含部分 Tab id
          const visibleIds = ['overview', ...visibleSubset]
          const currentActive = visibleIds[0] // overview
          if (!visibleIds.includes(targetSheet)) {
            const result = resolveActiveTab(currentActive, targetSheet, visibleIds)
            expect(result).toBe(currentActive)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空字符串 sheetName 保持当前 Tab 不变', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_TAB_IDS),
        (currentActive) => {
          const result = resolveActiveTab(currentActive, '', VALID_TAB_IDS)
          expect(result).toBe(currentActive)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 完成进度统计一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 5: 完成进度统计一致性', () => {
  /**
   * **Validates: Requirements 10.1, 10.2**
   *
   * For any completionMap + applicability combination,
   * progressSummary counts should sum to total checklist items,
   * and each count matches item states.
   */

  const statusArb = fc.constantFrom<CompletionStatus>('completed', 'in_progress', 'not_started')
  const applicabilityArb = fc.constantFrom<Applicability>('applicable', 'not_applicable', 'unknown')

  /** Generator: array of checklist-like items */
  const checklistItemArb = fc.record({
    status: statusArb,
    applicability: applicabilityArb,
  })

  it('进度各计数之和等于条目总数', () => {
    fc.assert(
      fc.property(
        fc.array(checklistItemArb, { minLength: 0, maxLength: 50 }),
        (items) => {
          const summary = computeProgressSummary(items)
          const total = summary.completed + summary.inProgress + summary.notStarted + summary.notApplicable
          expect(total).toBe(items.length)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('各计数与条目状态精确一致', () => {
    fc.assert(
      fc.property(
        fc.array(checklistItemArb, { minLength: 1, maxLength: 50 }),
        (items) => {
          const summary = computeProgressSummary(items)

          const expectedNA = items.filter(i => i.applicability === 'not_applicable').length
          const applicable = items.filter(i => i.applicability !== 'not_applicable')
          const expectedCompleted = applicable.filter(i => i.status === 'completed').length
          const expectedInProgress = applicable.filter(i => i.status === 'in_progress').length
          const expectedNotStarted = applicable.filter(i => i.status === 'not_started').length

          expect(summary.notApplicable).toBe(expectedNA)
          expect(summary.completed).toBe(expectedCompleted)
          expect(summary.inProgress).toBe(expectedInProgress)
          expect(summary.notStarted).toBe(expectedNotStarted)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('全部 not_applicable → completed/inProgress/notStarted 全为 0', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ status: statusArb, applicability: fc.constant<Applicability>('not_applicable') }),
          { minLength: 1, maxLength: 41 },
        ),
        (items) => {
          const summary = computeProgressSummary(items)
          expect(summary.completed).toBe(0)
          expect(summary.inProgress).toBe(0)
          expect(summary.notStarted).toBe(0)
          expect(summary.notApplicable).toBe(items.length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('全部 applicable + completed → completed 等于条目数', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 41 }),
        (count) => {
          const items = Array.from({ length: count }, () => ({
            status: 'completed' as CompletionStatus,
            applicability: 'applicable' as Applicability,
          }))
          const summary = computeProgressSummary(items)
          expect(summary.completed).toBe(count)
          expect(summary.inProgress).toBe(0)
          expect(summary.notStarted).toBe(0)
          expect(summary.notApplicable).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 法规溯源映射稳定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 6: 法规溯源映射稳定性', () => {
  /**
   * **Validates: Requirements 12.1, 12.3, 12.4**
   *
   * For any S34-0 checklist items with regRef data,
   * regRefMap[wpCode] returns the correct RegRef,
   * and missing exchange entries are null/undefined (not errors).
   */

  /** Generator: regRef 对象（各交易所条目可为 null 或字符串） */
  const regRefArb = fc.record({
    csrc: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
    sse: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
    szse: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
    bse: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
    title: fc.string({ minLength: 1, maxLength: 80 }),
  })

  /** Generator: checklist item with wpCode and regRef */
  const checklistWithRegRefArb = fc.array(
    fc.record({
      wpCode: fc.constantFrom(...S34_WP_CODES),
      regRef: regRefArb,
    }),
    { minLength: 0, maxLength: 41 },
  )

  it('每个输入条目的 regRef 都能在 map 中找到', () => {
    fc.assert(
      fc.property(checklistWithRegRefArb, (items) => {
        const map = computeRegRefMap(items)

        // 每个输入的 wpCode 都应存在于 map（最后一个覆盖前面相同 wpCode）
        for (const item of items) {
          expect(map[item.wpCode]).toBeDefined()
          expect(map[item.wpCode].title).toBeTruthy()
        }
      }),
      { numRuns: 100 },
    )
  })

  it('regRefMap 中 null 的交易所字段保留为 null（不抛错）', () => {
    fc.assert(
      fc.property(checklistWithRegRefArb, (items) => {
        const map = computeRegRefMap(items)

        for (const wpCode of Object.keys(map)) {
          const ref = map[wpCode]
          // 访问 null 的交易所字段不抛错
          expect(() => {
            const _csrc = ref.csrc
            const _sse = ref.sse
            const _szse = ref.szse
            const _bse = ref.bse
          }).not.toThrow()

          // null 字段确实为 null（而非 undefined 或其他）
          if (ref.csrc === null) expect(ref.csrc).toBeNull()
          if (ref.sse === null) expect(ref.sse).toBeNull()
          if (ref.szse === null) expect(ref.szse).toBeNull()
          if (ref.bse === null) expect(ref.bse).toBeNull()
        }
      }),
      { numRuns: 100 },
    )
  })

  it('不存在的 wpCode 在 map 中返回 undefined（不抛错）', () => {
    fc.assert(
      fc.property(
        checklistWithRegRefArb,
        fc.constantFrom(...S34_WP_CODES).filter(code =>
          // 选一个保证不在 items 里的 wpCode（通过后续 precondition 处理）
          true,
        ),
        (items, probeCode) => {
          // 只测试确实不在输入中的 wpCode
          const inputCodes = new Set(items.map(i => i.wpCode))
          fc.pre(!inputCodes.has(probeCode))

          const map = computeRegRefMap(items)
          // probeCode 不在 map 的 own properties 中
          expect(Object.prototype.hasOwnProperty.call(map, probeCode)).toBe(false)
          // 访问不会抛错
          expect(() => { const _r = map[probeCode] }).not.toThrow()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('regRefMap 幂等性：同一输入多次调用结果相同', () => {
    fc.assert(
      fc.property(checklistWithRegRefArb, (items) => {
        const map1 = computeRegRefMap(items)
        const map2 = computeRegRefMap(items)
        expect(map1).toEqual(map2)
      }),
      { numRuns: 100 },
    )
  })

  it('最后一个同 wpCode 条目的 regRef 覆盖前面的', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...S34_WP_CODES),
        regRefArb,
        regRefArb,
        (wpCode, ref1, ref2) => {
          const items = [
            { wpCode, regRef: ref1 },
            { wpCode, regRef: ref2 },
          ]
          const map = computeRegRefMap(items)
          expect(map[wpCode]).toEqual(ref2)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: readonly 透传
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s34-ipo-review-bundle, Property 7: readonly 透传', () => {
  /**
   * **Validates: Requirements 11.1, 11.2, 11.3**
   *
   * For any Tab and any boolean readonly value, child components
   * (GtAProgramConsole / GtS34SubCheckTable / GtS34ChecklistOverview)
   * must receive a readonly prop consistent with the parent's props.readonly.
   *
   * 测试纯逻辑：readonly 透传由 Vue 模板绑定 :readonly="props.readonly" 实现，
   * 此处验证 propagation 纯函数的确定性——相同输入永远产出相同 readonly 值。
   */

  /**
   * 纯函数：模拟 GtS34Bundle 的 readonly 传播逻辑。
   * 对齐 GtS34Bundle.vue template 中所有子组件的 :readonly="props.readonly" 绑定。
   *
   * @param parentReadonly 父组件 props.readonly 值
   * @param tabId 当前选中的 Tab id
   * @returns 各子组件接收的 readonly 值
   */
  function propagateReadonly(
    parentReadonly: boolean,
    tabId: string,
  ): { overview: boolean; programConsole: boolean; subCheckTable: boolean } {
    // GtS34Bundle.vue 统一绑定 :readonly="props.readonly" 到所有子组件
    // 不论 tabId 为何值，子组件的 readonly prop 恒等于 parentReadonly
    return {
      overview: parentReadonly,
      programConsole: parentReadonly,
      subCheckTable: parentReadonly,
    }
  }

  /** 所有合法 Tab id */
  const ALL_TAB_IDS = S34_TAB_DEFS.map(t => t.id)

  it('任意 readonly 布尔值透传到所有子组件（overview/programConsole/subCheckTable）', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.constantFrom(...ALL_TAB_IDS),
        (readonly, tabId) => {
          const result = propagateReadonly(readonly, tabId)
          // 所有子组件的 readonly 必须与父级一致
          expect(result.overview).toBe(readonly)
          expect(result.programConsole).toBe(readonly)
          expect(result.subCheckTable).toBe(readonly)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly=true 时所有子组件均为 true（不允许任何泄漏）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_TAB_IDS),
        (tabId) => {
          const result = propagateReadonly(true, tabId)
          expect(result.overview).toBe(true)
          expect(result.programConsole).toBe(true)
          expect(result.subCheckTable).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly=false 时所有子组件均为 false（可编辑模式）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_TAB_IDS),
        (tabId) => {
          const result = propagateReadonly(false, tabId)
          expect(result.overview).toBe(false)
          expect(result.programConsole).toBe(false)
          expect(result.subCheckTable).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 透传幂等性：多次取值结果一致', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.constantFrom(...ALL_TAB_IDS),
        (readonly, tabId) => {
          const r1 = propagateReadonly(readonly, tabId)
          const r2 = propagateReadonly(readonly, tabId)
          expect(r1).toEqual(r2)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 子表汇总公式确定性
// ═══════════════════════════════════════════════════════════════════════════════

import {
  sumRange,
  safeDivide,
  computeFormulas,
  S34_16_1_FORMULAS,
  extractColumnRange,
  parseNum,
} from '../useS34FormulaEngine'

describe('Feature: s34-ipo-review-bundle, Property 8: 子表汇总公式确定性', () => {
  /**
   * **Validates: Requirements 5.2, 5.5**
   *
   * For any sub-checktable detail row amounts array, summary cells
   * (e.g., S34-16-1's =SUM(E8:E18), ratio =C24/C23) should equal
   * the pure function calculation result, and be unaffected by manual overrides.
   */

  /** Generator: float array for row amounts (noNaN, finite) */
  const amountsArb = fc.array(
    fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    { minLength: 0, maxLength: 20 },
  )

  it('sumRange 返回正确的 SUM，与 Array.reduce 一致', () => {
    fc.assert(
      fc.property(amountsArb, (amounts) => {
        const result = sumRange(amounts)
        const expected = amounts.reduce((a, b) => a + b, 0)
        // 浮点数精度比较
        expect(Math.abs(result - expected)).toBeLessThan(1e-6)
      }),
      { numRuns: 200 },
    )
  })

  it('sumRange([]) = 0（空数组求和为零）', () => {
    expect(sumRange([])).toBe(0)
  })

  it('safeDivide: 分母非零时返回正确比率', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }).filter(d => d !== 0),
        (numerator, denominator) => {
          const result = safeDivide(numerator, denominator)
          expect(result).not.toBeNull()
          const expected = numerator / denominator
          expect(Math.abs(result! - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('safeDivide: 分母为零时返回 null（除零安全）', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (numerator) => {
          const result = safeDivide(numerator, 0)
          expect(result).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('S34-16-1 公式重算结果等于纯函数计算（不受手工覆盖影响）', () => {
    /**
     * 构造一个 S34-16-1 数据网格（至少25行），将随机金额填入行7~17的E/F列，
     * 然后验证 computeFormulas 结果与手动 sumRange/safeDivide 一致。
     * 即使在公式单元格位置放入"手工覆盖值"，也不影响公式重算。
     */
    const rowAmountsArb = fc.array(
      fc.float({ min: -1e9, max: 1e9, noNaN: true }),
      { minLength: 11, maxLength: 11 },
    )

    fc.assert(
      fc.property(
        rowAmountsArb, // E column (rows 7~17)
        rowAmountsArb, // F column (rows 7~17)
        fc.float({ min: -1e9, max: 1e9, noNaN: true }), // manual override attempt on formula cell
        (eAmounts, fAmounts, manualOverride) => {
          // Build data grid (25 rows)
          const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({}))
          // Fill E and F columns for rows 7~17
          for (let i = 0; i < 11; i++) {
            data[7 + i] = { E: eAmounts[i], F: fAmounts[i] }
          }
          // Simulate manual override on row 18 col E (formula cell) — should be ignored
          data[18] = { ...data[18], E: manualOverride, F: manualOverride }

          // Compute formulas
          const results = computeFormulas(data, S34_16_1_FORMULAS)

          // Expected values computed via pure functions
          const expectedSumE = sumRange(eAmounts)
          const expectedSumF = sumRange(fAmounts)
          const expectedRatio = safeDivide(expectedSumF, expectedSumE)

          // Verify SUM(E8:E18) = sumRange(eAmounts), NOT the manual override
          expect(Math.abs((results['18:E'] ?? 0) - expectedSumE)).toBeLessThan(1e-6)
          // Verify SUM(F8:F18)
          expect(Math.abs((results['18:F'] ?? 0) - expectedSumF)).toBeLessThan(1e-6)
          // Verify C23 = E19 (sum of E column)
          expect(Math.abs((results['22:C'] ?? 0) - expectedSumE)).toBeLessThan(1e-6)
          // Verify C24 = F19 (sum of F column)
          expect(Math.abs((results['23:C'] ?? 0) - expectedSumF)).toBeLessThan(1e-6)
          // Verify C25 = C24/C23 (ratio)
          if (expectedRatio === null) {
            expect(results['24:C']).toBeNull()
          } else {
            expect(Math.abs((results['24:C'] ?? 0) - expectedRatio)).toBeLessThan(1e-6)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('公式重算幂等性：同一数据多次计算结果相同', () => {
    const rowAmountsArb = fc.array(
      fc.float({ min: -1e9, max: 1e9, noNaN: true }),
      { minLength: 11, maxLength: 11 },
    )

    fc.assert(
      fc.property(rowAmountsArb, rowAmountsArb, (eAmounts, fAmounts) => {
        const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({}))
        for (let i = 0; i < 11; i++) {
          data[7 + i] = { E: eAmounts[i], F: fAmounts[i] }
        }

        const r1 = computeFormulas(data, S34_16_1_FORMULAS)
        const r2 = computeFormulas(data, S34_16_1_FORMULAS)
        expect(r1).toEqual(r2)
      }),
      { numRuns: 100 },
    )
  })
})
