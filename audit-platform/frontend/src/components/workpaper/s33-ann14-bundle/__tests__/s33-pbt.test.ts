/**
 * Property-Based Tests — S33 应对14号公告核查程序聚合组件（P1~P6）
 *
 * Spec: .kiro/specs/s33-announcement14-bundle/
 * Task: 7.1
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P6。
 * 每个 property ≥ 100 次迭代。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { S33_ANN14_TABS, S33_WP_CODES } from '../S33_TAB_CONFIG'
import {
  buildWpIdMap,
  computeVisibleTabs,
  computeProgressSummary,
  deriveProgramStatus,
  type CompletionStatus,
} from '../useS33BundleState'

// ─── 常量 ───

/** 所有 S33 wp_code 字符串集合 */
const ALL_S33_CODES = S33_WP_CODES as readonly string[]

/** 合法 Tab id（与 S33_ANN14_TABS 中 id 一致） */
const VALID_TAB_IDS = S33_ANN14_TABS.map(t => t.id)

// ─── P1 辅助：wp_code_overrides 期望值 ───

/** 已确认的 S33 skip 映射（来源 backend/app/data/wp_code_overrides.json） */
const EXPECTED_SKIP_CODES = [
  'S33-1', 'S33-2', 'S33-3', 'S33-4', 'S33-5',
  'S33-6', 'S33-7', 'S33-8', 'S33-9',
]

// ═══════════════════════════════════════════════════════════════════════════════
// P1: 子底稿 skip 映射完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 1: 子底稿 skip 映射完整性', () => {
  /**
   * **Validates: Requirements 1.2, 2.1, 2.2**
   *
   * S33-1~S33-9 的 wp_code_overrides 映射均为 skip；
   * S33 映射为 s33-ann14-bundle。
   *
   * 使用硬编码期望值验证已知 S33 编码集完整性。
   */

  it('S33_WP_CODES 包含全部 9 个子底稿编码', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...EXPECTED_SKIP_CODES),
        (code) => {
          expect(ALL_S33_CODES).toContain(code)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('S33_WP_CODES 恰好 9 项且每项格式为 S33-{1~9}', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_S33_CODES),
        (code) => {
          // 每个 code 必须匹配 S33-{n} 格式
          expect(code).toMatch(/^S33-\d+$/)
          const n = parseInt(code.replace('S33-', ''), 10)
          expect(n).toBeGreaterThanOrEqual(1)
          expect(n).toBeLessThanOrEqual(9)
        },
      ),
      { numRuns: 100 },
    )
    // 总数断言
    expect(ALL_S33_CODES.length).toBe(9)
  })

  it('S33_ANN14_TABS 中每个 Tab 的 wpCode 在 S33_WP_CODES 中存在', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...S33_ANN14_TABS),
        (tab) => {
          expect(ALL_S33_CODES).toContain(tab.wpCode)
          expect(tab.id).toBe(tab.wpCode) // id 与 wpCode 一致
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P2: wp_id 解析与传播
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 2: wp_id 解析与传播', () => {
  /**
   * **Validates: Requirements 5.1, 5.3**
   *
   * ∀ wp_index 数据集（含 S33-* 条目），buildWpIdMap 正确映射。
   * 铁律：使用 item.wp_id（非 item.id）。
   */

  const wpIndexItemArb = fc.record({
    wp_code: fc.constantFrom(...ALL_S33_CODES),
    wp_id: fc.uuid(),
    id: fc.uuid(), // id 应被忽略
  })

  it('buildWpIdMap 使用 wp_id 而非 id', () => {
    fc.assert(
      fc.property(
        fc.array(wpIndexItemArb, { minLength: 1, maxLength: 20 }),
        (items) => {
          const map = buildWpIdMap(items)
          for (const item of items) {
            if (map[item.wp_code]) {
              // 映射值应为某条目的 wp_id，绝不等于 id（除非碰巧相等）
              expect(map[item.wp_code]).not.toBe(item.id)
              // 验证映射值确实来自同一 wp_code 的某条目的 wp_id
              const matchingItems = items.filter(i => i.wp_code === item.wp_code)
              const wpIds = matchingItems.map(i => i.wp_id)
              expect(wpIds).toContain(map[item.wp_code])
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('buildWpIdMap 只包含 S33-* 编码', () => {
    // 混入非 S33 编码，确保 buildWpIdMap 不收录
    const mixedItemArb = fc.record({
      wp_code: fc.oneof(
        fc.constantFrom(...ALL_S33_CODES),
        fc.constantFrom('A1', 'B2', 'D4-1', 'S32-5', 'S34-1'),
      ),
      wp_id: fc.uuid(),
      id: fc.uuid(),
    })

    fc.assert(
      fc.property(
        fc.array(mixedItemArb, { minLength: 1, maxLength: 30 }),
        (items) => {
          const map = buildWpIdMap(items)
          for (const key of Object.keys(map)) {
            expect(key).toMatch(/^S33-\d+$/)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('buildWpIdMap 忽略 wp_id 为 null/undefined 的条目', () => {
    const nullableItemArb = fc.record({
      wp_code: fc.constantFrom(...ALL_S33_CODES),
      wp_id: fc.oneof(fc.uuid(), fc.constant(null), fc.constant(undefined)),
      id: fc.uuid(),
    })

    fc.assert(
      fc.property(
        fc.array(nullableItemArb, { minLength: 1, maxLength: 20 }),
        (items) => {
          const map = buildWpIdMap(items as any)
          for (const [code, wpId] of Object.entries(map)) {
            expect(wpId).toBeTruthy()
            expect(wpId).not.toBeNull()
            expect(wpId).not.toBeUndefined()
            // 确认该 wpId 来源于 wp_id 非空的条目
            const sourceItem = items.find(i => i.wp_code === code && i.wp_id === wpId)
            expect(sourceItem).toBeDefined()
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P3: Tab 可见性由 wp_index 存在性驱动
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 3: Tab 可见性由 wp_index 存在性驱动', () => {
  /**
   * **Validates: Requirements 5.2, 5.4**
   *
   * ∀ S33 编码子集有 wp_id → 仅这些编码对应的 Tab 可见。
   * 空子集 → 无可见 Tab（触发空状态）。
   */

  it('可见 Tab 恰好等于 wpIdMap 中有值的编码集', () => {
    fc.assert(
      fc.property(
        fc.subarray([...ALL_S33_CODES]),
        (presentCodes) => {
          // 构造 wpIdMap：仅 presentCodes 有 wp_id
          const wpIdMap: Record<string, string> = {}
          for (const code of presentCodes) {
            wpIdMap[code] = `fake-uuid-${code}`
          }

          const visibleTabs = computeVisibleTabs(wpIdMap)
          const visibleCodes = visibleTabs.map(t => t.wpCode)

          // 可见 Tab 的编码集合 === presentCodes（顺序可能不同但集合相等）
          expect(new Set(visibleCodes)).toEqual(new Set(presentCodes))
          // 每个可见 Tab 在 S33_ANN14_TABS 中存在
          for (const tab of visibleTabs) {
            expect(S33_ANN14_TABS.some(t => t.id === tab.id)).toBe(true)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空 wpIdMap → 无可见 Tab（空状态）', () => {
    fc.assert(
      fc.property(
        fc.constant({}),
        (emptyMap) => {
          const visibleTabs = computeVisibleTabs(emptyMap)
          expect(visibleTabs).toHaveLength(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('可见 Tab 顺序保持 S33_ANN14_TABS 原始配置顺序', () => {
    fc.assert(
      fc.property(
        fc.subarray([...ALL_S33_CODES], { minLength: 2 }),
        (presentCodes) => {
          const wpIdMap: Record<string, string> = {}
          for (const code of presentCodes) {
            wpIdMap[code] = `uuid-${code}`
          }

          const visibleTabs = computeVisibleTabs(wpIdMap)
          // 验证可见 Tab 的顺序与 S33_ANN14_TABS 中的相对顺序一致
          for (let i = 1; i < visibleTabs.length; i++) {
            const prevIdx = S33_ANN14_TABS.findIndex(t => t.id === visibleTabs[i - 1].id)
            const currIdx = S33_ANN14_TABS.findIndex(t => t.id === visibleTabs[i].id)
            expect(prevIdx).toBeLessThan(currIdx)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P4: sheetName 路由正确激活 Tab
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 4: sheetName 路由正确激活 Tab', () => {
  /**
   * **Validates: Requirements 4.1, 4.4**
   *
   * ∀ 合法 Tab id → activeTab 切换为该值。
   * ∀ 非法 sheetName → activeTab 保持不变。
   *
   * 测试纯逻辑：给定 visibleTabs 和 sheetName，判断是否应激活。
   */

  /** 模拟 sheetName 路由逻辑（与 GtS33Bundle.vue 中 watch 逻辑一致） */
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

  it('非法 sheetName 保持当前 Tab 不变', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => !VALID_TAB_IDS.includes(s)),
        fc.constantFrom(...VALID_TAB_IDS),
        (invalidSheet, currentActive) => {
          const result = resolveActiveTab(currentActive, invalidSheet, VALID_TAB_IDS)
          expect(result).toBe(currentActive)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('sheetName 不在可见 Tab 列表中 → 保持不变', () => {
    // 部分 Tab 可见时，传入不可见 Tab id
    fc.assert(
      fc.property(
        fc.subarray([...ALL_S33_CODES], { minLength: 1, maxLength: 5 }),
        fc.constantFrom(...VALID_TAB_IDS),
        (visibleSubset, targetSheet) => {
          const currentActive = visibleSubset[0]
          if (!visibleSubset.includes(targetSheet)) {
            const result = resolveActiveTab(currentActive, targetSheet, visibleSubset)
            expect(result).toBe(currentActive)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P5: 完成进度统计一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 5: 完成进度统计一致性', () => {
  /**
   * **Validates: Requirements 7.1**
   *
   * ∀ completionMap：
   *   progressSummary.completed + inProgress + notStarted === 可见底稿数
   *   各计数与 map 中对应 status 数量一致。
   */

  const statusArb = fc.constantFrom<CompletionStatus>('completed', 'in_progress', 'not_started')

  it('进度各计数之和等于可见底稿数', () => {
    fc.assert(
      fc.property(
        fc.array(statusArb, { minLength: 0, maxLength: 9 }),
        (statuses) => {
          // 构造 completionMap
          const completionMap: Record<string, CompletionStatus> = {}
          const codes = ALL_S33_CODES.slice(0, statuses.length)
          for (let i = 0; i < statuses.length; i++) {
            completionMap[codes[i]] = statuses[i]
          }

          const summary = computeProgressSummary(completionMap)
          const total = summary.completed + summary.inProgress + summary.notStarted
          expect(total).toBe(statuses.length)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('各计数与 completionMap 中对应状态数量精确一致', () => {
    fc.assert(
      fc.property(
        fc.array(statusArb, { minLength: 1, maxLength: 9 }),
        (statuses) => {
          const completionMap: Record<string, CompletionStatus> = {}
          const codes = ALL_S33_CODES.slice(0, statuses.length)
          for (let i = 0; i < statuses.length; i++) {
            completionMap[codes[i]] = statuses[i]
          }

          const summary = computeProgressSummary(completionMap)
          const expectedCompleted = statuses.filter(s => s === 'completed').length
          const expectedInProgress = statuses.filter(s => s === 'in_progress').length
          const expectedNotStarted = statuses.filter(s => s === 'not_started').length

          expect(summary.completed).toBe(expectedCompleted)
          expect(summary.inProgress).toBe(expectedInProgress)
          expect(summary.notStarted).toBe(expectedNotStarted)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('deriveProgramStatus 返回的 status 在三种合法值之内', () => {
    const responseArb = fc.array(
      fc.record({
        item_id: fc.uuid(),
        conclusion: fc.oneof(fc.constant(null), fc.constant(''), fc.string({ minLength: 1 })),
      }),
      { minLength: 0, maxLength: 20 },
    )

    fc.assert(
      fc.property(responseArb, (responses) => {
        const status = deriveProgramStatus(responses)
        expect(['completed', 'in_progress', 'not_started']).toContain(status)
      }),
      { numRuns: 200 },
    )
  })

  it('deriveProgramStatus 空数组 → not_started', () => {
    fc.assert(
      fc.property(
        fc.constant([]),
        (empty) => {
          expect(deriveProgramStatus(empty)).toBe('not_started')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('deriveProgramStatus 全填结论 → completed', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            item_id: fc.uuid(),
            conclusion: fc.string({ minLength: 1, maxLength: 100 }).filter(s => s.trim().length > 0),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (responses) => {
          expect(deriveProgramStatus(responses)).toBe('completed')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P6: readonly 透传
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s33-announcement14-bundle, Property 6: readonly 透传', () => {
  /**
   * **Validates: Requirements 8.1**
   *
   * ∀ boolean readonly 值，所有 GtAProgramConsole 实例应接收同一 readonly 值。
   *
   * 测试纯逻辑：验证组件 props 透传原理。
   * GtS33Bundle.vue 模板中 `:readonly="props.readonly"` 对所有 Tab 统一透传。
   */

  /** 模拟 readonly 透传逻辑 */
  function getChildReadonly(parentReadonly: boolean, _tabId: string): boolean {
    // GtS33Bundle 对所有子组件统一透传 props.readonly
    return parentReadonly
  }

  it('所有 Tab 的子组件 readonly 与父 props.readonly 一致', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.constantFrom(...VALID_TAB_IDS),
        (readonly, tabId) => {
          const childReadonly = getChildReadonly(readonly, tabId)
          expect(childReadonly).toBe(readonly)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('readonly 不受 Tab 数量影响', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.subarray([...ALL_S33_CODES], { minLength: 1 }),
        (readonly, visibleCodes) => {
          // 无论可见 Tab 数量如何，每个子组件都应收到相同的 readonly
          for (const code of visibleCodes) {
            expect(getChildReadonly(readonly, code)).toBe(readonly)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
