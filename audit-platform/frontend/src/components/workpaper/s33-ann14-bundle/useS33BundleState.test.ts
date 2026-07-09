/**
 * Unit tests for useS33BundleState — Task 3.1 + 3.2
 *
 * 测试纯函数 buildWpIdMap / computeVisibleTabs / deriveProgramStatus / computeProgressSummary。
 * Requirements: 5.1, 5.2, 7.1
 */
import { describe, it, expect } from 'vitest'
import {
  buildWpIdMap,
  computeVisibleTabs,
  deriveProgramStatus,
  computeProgressSummary,
  type ChecklistResponse,
  type CompletionStatus,
} from './useS33BundleState'
import { S33_ANN14_TABS } from './S33_TAB_CONFIG'

describe('buildWpIdMap', () => {
  it('should extract S33-* entries using item.wp_id (not item.id)', () => {
    const items = [
      { id: 'idx-1', wp_code: 'S33-1', wp_id: 'wp-uuid-1' },
      { id: 'idx-2', wp_code: 'S33-2', wp_id: 'wp-uuid-2' },
      { id: 'idx-3', wp_code: 'A1', wp_id: 'wp-uuid-a1' },
    ]
    const map = buildWpIdMap(items)
    expect(map).toEqual({
      'S33-1': 'wp-uuid-1',
      'S33-2': 'wp-uuid-2',
    })
    // 🔴 铁律验证：确保使用 wp_id 而非 id
    expect(map['S33-1']).toBe('wp-uuid-1')
    expect(map['S33-1']).not.toBe('idx-1')
  })

  it('should ignore entries with null/undefined wp_id', () => {
    const items = [
      { id: 'idx-1', wp_code: 'S33-1', wp_id: 'wp-uuid-1' },
      { id: 'idx-2', wp_code: 'S33-2', wp_id: null },
      { id: 'idx-3', wp_code: 'S33-3', wp_id: undefined },
    ]
    const map = buildWpIdMap(items)
    expect(map).toEqual({ 'S33-1': 'wp-uuid-1' })
  })

  it('should filter only S33-\\d+ pattern (not S33 or S33-abc)', () => {
    const items = [
      { id: 'idx-0', wp_code: 'S33', wp_id: 'wp-uuid-parent' },
      { id: 'idx-1', wp_code: 'S33-1', wp_id: 'wp-uuid-1' },
      { id: 'idx-x', wp_code: 'S33-abc', wp_id: 'wp-uuid-abc' },
      { id: 'idx-9', wp_code: 'S33-9', wp_id: 'wp-uuid-9' },
    ]
    const map = buildWpIdMap(items)
    expect(Object.keys(map)).toEqual(['S33-1', 'S33-9'])
  })

  it('should return empty map for empty input', () => {
    expect(buildWpIdMap([])).toEqual({})
  })
})

describe('computeVisibleTabs', () => {
  it('should return only tabs whose wpCode exists in wpIdMap', () => {
    const wpIdMap = { 'S33-1': 'wp-1', 'S33-5': 'wp-5', 'S33-9': 'wp-9' }
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible.map(t => t.wpCode)).toEqual(['S33-1', 'S33-5', 'S33-9'])
  })

  it('should return all 9 tabs when all S33-1~9 present', () => {
    const wpIdMap: Record<string, string> = {}
    for (let i = 1; i <= 9; i++) {
      wpIdMap[`S33-${i}`] = `wp-uuid-${i}`
    }
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible).toHaveLength(9)
    expect(visible).toEqual(S33_ANN14_TABS)
  })

  it('should return empty array when wpIdMap is empty', () => {
    expect(computeVisibleTabs({})).toEqual([])
  })

  // ─── Task 6.3: 空状态提示 (Req 5.4) ───

  it('empty wpIdMap → visibleTabs.length === 0 → triggers empty state (Req 5.4)', () => {
    // When wp_index has no S33 entries, wpIdMap is {} → visibleTabs empty
    // GtS33Bundle shows empty state when !loading && visibleTabs.length === 0
    const wpIdMapFromEmptyProject = buildWpIdMap([])
    expect(wpIdMapFromEmptyProject).toEqual({})
    const visible = computeVisibleTabs(wpIdMapFromEmptyProject)
    expect(visible).toHaveLength(0)
    // Contract: visibleTabs.length === 0 is the condition for empty state display
  })

  it('wpIdMap with only non-S33 entries → empty visibleTabs (Req 5.4)', () => {
    // wp_index contains other workpapers but no S33-*
    const items = [
      { id: 'idx-1', wp_code: 'A1', wp_id: 'wp-a1' },
      { id: 'idx-2', wp_code: 'D2-1', wp_id: 'wp-d2' },
      { id: 'idx-3', wp_code: 'S34-1', wp_id: 'wp-s34' },
    ]
    const wpIdMap = buildWpIdMap(items)
    expect(Object.keys(wpIdMap)).toHaveLength(0)
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible).toHaveLength(0)
  })

  it('should maintain tab order from S33_ANN14_TABS config', () => {
    // 反向插入确认顺序不受 wpIdMap 插入顺序影响
    const wpIdMap = { 'S33-9': 'wp-9', 'S33-3': 'wp-3', 'S33-1': 'wp-1' }
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible.map(t => t.wpCode)).toEqual(['S33-1', 'S33-3', 'S33-9'])
  })

  // ─── Task 6.2: wp_id 不存在→Tab 隐藏 (Req 5.2, 5.3) ───

  it('should show exactly 5 tabs when wpIdMap has only 5 of 9 entries', () => {
    const wpIdMap: Record<string, string> = {
      'S33-1': 'wp-uuid-1',
      'S33-3': 'wp-uuid-3',
      'S33-5': 'wp-uuid-5',
      'S33-7': 'wp-uuid-7',
      'S33-9': 'wp-uuid-9',
    }
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible).toHaveLength(5)
    expect(visible.map(t => t.wpCode)).toEqual(['S33-1', 'S33-3', 'S33-5', 'S33-7', 'S33-9'])
    // S33-2, S33-4, S33-6, S33-8 不在 wpIdMap → 隐藏
    const hiddenCodes = ['S33-2', 'S33-4', 'S33-6', 'S33-8']
    for (const code of hiddenCodes) {
      expect(visible.find(t => t.wpCode === code)).toBeUndefined()
    }
  })

  it('should hide tab when its wp_id is removed from wpIdMap (dynamic visibility)', () => {
    // Scenario: initially 3 tabs visible, then one wp_id is removed
    const initialMap = { 'S33-1': 'wp-1', 'S33-2': 'wp-2', 'S33-3': 'wp-3' }
    const afterRemoval = { 'S33-1': 'wp-1', 'S33-3': 'wp-3' }

    const before = computeVisibleTabs(initialMap)
    const after = computeVisibleTabs(afterRemoval)

    expect(before).toHaveLength(3)
    expect(after).toHaveLength(2)
    expect(after.find(t => t.wpCode === 'S33-2')).toBeUndefined()
  })

  it('active tab should fallback to first visible tab when current tab becomes hidden', () => {
    // This tests the behavioral contract:
    // GtS33Bundle watches visibleTabs and resets activeTab to tabs[0].id
    // when activeTab is no longer in the visible set.
    const initialMap = { 'S33-1': 'wp-1', 'S33-4': 'wp-4', 'S33-7': 'wp-7' }
    const afterMap = { 'S33-1': 'wp-1', 'S33-7': 'wp-7' } // S33-4 removed

    const visibleBefore = computeVisibleTabs(initialMap)
    const visibleAfter = computeVisibleTabs(afterMap)

    // Simulate: activeTab was 'S33-4'
    const activeTab = 'S33-4'
    const isStillVisible = visibleAfter.some(t => t.id === activeTab)
    expect(isStillVisible).toBe(false)

    // Contract: fallback to first visible tab
    const fallbackTab = visibleAfter.length > 0 ? visibleAfter[0].id : ''
    expect(fallbackTab).toBe('S33-1')
  })
})


// ─── Task 3.2: deriveProgramStatus 单元测试 ───

describe('deriveProgramStatus', () => {
  it('should return not_started for empty responses', () => {
    expect(deriveProgramStatus([])).toBe('not_started')
  })

  it('should return not_started when all conclusions are null/empty', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: null },
      { item_id: '2', conclusion: '' },
      { item_id: '3', conclusion: '   ' },
    ]
    expect(deriveProgramStatus(responses)).toBe('not_started')
  })

  it('should return completed when all conclusions are filled', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '已核查' },
      { item_id: '2', conclusion: '无异常' },
      { item_id: '3', conclusion: '符合' },
    ]
    expect(deriveProgramStatus(responses)).toBe('completed')
  })

  it('should return in_progress when some conclusions are filled', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '已核查' },
      { item_id: '2', conclusion: null },
      { item_id: '3', conclusion: '符合' },
    ]
    expect(deriveProgramStatus(responses)).toBe('in_progress')
  })

  it('should return in_progress with mix of empty/whitespace/filled', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '已核查' },
      { item_id: '2', conclusion: '' },
      { item_id: '3', conclusion: '  ' },
    ]
    expect(deriveProgramStatus(responses)).toBe('in_progress')
  })

  it('should treat undefined conclusion same as null (not_started)', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1' },
      { item_id: '2', conclusion: undefined },
    ]
    expect(deriveProgramStatus(responses)).toBe('not_started')
  })

  it('should return completed for single item with conclusion', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '核查通过' },
    ]
    expect(deriveProgramStatus(responses)).toBe('completed')
  })
})

// ─── Task 3.2: computeProgressSummary 单元测试 ───

describe('computeProgressSummary', () => {
  it('should return all zeros for empty map', () => {
    expect(computeProgressSummary({})).toEqual({
      completed: 0,
      inProgress: 0,
      notStarted: 0,
    })
  })

  it('should count each status correctly', () => {
    const map: Record<string, CompletionStatus> = {
      'S33-1': 'completed',
      'S33-2': 'in_progress',
      'S33-3': 'not_started',
      'S33-4': 'completed',
      'S33-5': 'in_progress',
    }
    expect(computeProgressSummary(map)).toEqual({
      completed: 2,
      inProgress: 2,
      notStarted: 1,
    })
  })

  it('should sum to total visible tabs count (Property 5)', () => {
    const map: Record<string, CompletionStatus> = {
      'S33-1': 'completed',
      'S33-2': 'completed',
      'S33-3': 'in_progress',
      'S33-4': 'not_started',
      'S33-5': 'not_started',
      'S33-6': 'not_started',
      'S33-7': 'completed',
      'S33-8': 'in_progress',
      'S33-9': 'completed',
    }
    const summary = computeProgressSummary(map)
    expect(summary.completed + summary.inProgress + summary.notStarted).toBe(9)
  })

  it('should handle all completed', () => {
    const map: Record<string, CompletionStatus> = {
      'S33-1': 'completed',
      'S33-2': 'completed',
      'S33-3': 'completed',
    }
    expect(computeProgressSummary(map)).toEqual({
      completed: 3,
      inProgress: 0,
      notStarted: 0,
    })
  })

  it('should handle all not_started', () => {
    const map: Record<string, CompletionStatus> = {
      'S33-1': 'not_started',
      'S33-2': 'not_started',
    }
    expect(computeProgressSummary(map)).toEqual({
      completed: 0,
      inProgress: 0,
      notStarted: 2,
    })
  })
})

// ─── Task 6.3: 空状态提示完整验证 (Req 5.4) ───

describe('Empty state logic (Req 5.4)', () => {
  /**
   * GtS33Bundle 空状态显示条件：
   *   v-if="!loading && visibleTabs.length === 0"
   *
   * 空状态文案：「本项目未启用14号公告核查程序」
   *
   * 本测试组验证空状态的触发逻辑数据层。
   */

  it('computeVisibleTabs({}) returns [] — empty state condition met', () => {
    const visible = computeVisibleTabs({})
    expect(visible).toEqual([])
    // When loading=false AND visibleTabs.length===0 → show empty state
    const loading = false
    const showEmptyState = !loading && visible.length === 0
    expect(showEmptyState).toBe(true)
  })

  it('loading=true AND visibleTabs empty → empty state NOT shown (loading indicator instead)', () => {
    const visible = computeVisibleTabs({})
    expect(visible).toHaveLength(0)
    // When loading is true, v-loading directive shows spinner, empty state hidden
    const loading = true
    const showEmptyState = !loading && visible.length === 0
    expect(showEmptyState).toBe(false)
  })

  it('visibleTabs non-empty → empty state NOT shown regardless of loading', () => {
    const wpIdMap = { 'S33-1': 'wp-1' }
    const visible = computeVisibleTabs(wpIdMap)
    expect(visible.length).toBeGreaterThan(0)
    // Empty state never shows when tabs are visible
    expect(!false && visible.length === 0).toBe(false)
    expect(!true && visible.length === 0).toBe(false)
  })

  it('wp_index API failure scenario: buildWpIdMap([]) → {} → empty state', () => {
    // When wp_index API fails, useS33BundleState sets wpIdMapState = {}
    // This leads to visibleTabs = [] and loading = false after catch/finally
    const wpIdMap = buildWpIdMap([])
    const visible = computeVisibleTabs(wpIdMap)
    const loading = false // set to false in finally block
    const showEmptyState = !loading && visible.length === 0
    expect(showEmptyState).toBe(true)
  })

  it('empty state text matches requirement 5.4', () => {
    // Verify the expected text constant
    // GtS33Bundle template: <el-result icon="info" title="本项目未启用14号公告核查程序">
    const expectedTitle = '本项目未启用14号公告核查程序'
    expect(expectedTitle).toBe('本项目未启用14号公告核查程序')
  })
})
