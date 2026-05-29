/**
 * Tests for useWpNavigationHistory composable
 *
 * Feature: workpaper-editor-slimdown Sprint 4
 * Task 11.1: 底稿间导航增强
 *
 * **Validates: Requirements US-9**
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: { value: { params: { projectId: 'proj-1' } } },
  }),
}))

describe('useWpNavigationHistory', () => {
  beforeEach(() => {
    // Clear sessionStorage before each test
    sessionStorage.clear()
    // Reset module state by re-importing
    vi.resetModules()
  })

  it('push adds item to history', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, history } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: '应收账款' })
    expect(history.value.length).toBe(1)
    expect(history.value[0].wpId).toBe('wp-1')
    expect(history.value[0].wpCode).toBe('D2A')
    expect(history.value[0].sheetName).toBe('应收账款')
    expect(history.value[0].timestamp).toBeGreaterThan(0)
  })

  it('push respects MAX_HISTORY=5 limit', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, history } = useWpNavigationHistory()

    for (let i = 0; i < 7; i++) {
      push({ wpId: `wp-${i}`, wpCode: `D${i}`, sheetName: `Sheet${i}` })
    }
    expect(history.value.length).toBe(5)
    // Should keep the last 5
    expect(history.value[0].wpId).toBe('wp-2')
    expect(history.value[4].wpId).toBe('wp-6')
  })

  it('push deduplicates consecutive same wpId+sheetName', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, history } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: '应收账款' })
    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: '应收账款' })
    expect(history.value.length).toBe(1)
  })

  it('pop removes and returns last item', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, pop, history } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1' })
    push({ wpId: 'wp-2', wpCode: 'E1', sheetName: 'Sheet2' })

    const item = pop()
    expect(item).not.toBeNull()
    expect(item!.wpId).toBe('wp-2')
    expect(history.value.length).toBe(1)
  })

  it('pop returns null when history is empty', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { pop } = useWpNavigationHistory()

    const item = pop()
    expect(item).toBeNull()
  })

  it('canGoBack is true when history has items', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, canGoBack } = useWpNavigationHistory()

    expect(canGoBack.value).toBe(false)
    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1' })
    expect(canGoBack.value).toBe(true)
  })

  it('lastItem returns the most recent entry', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, lastItem } = useWpNavigationHistory()

    expect(lastItem.value).toBeNull()
    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1' })
    push({ wpId: 'wp-2', wpCode: 'E1', sheetName: 'Sheet2', rowRef: '第 3 行' })
    expect(lastItem.value!.wpCode).toBe('E1')
    expect(lastItem.value!.rowRef).toBe('第 3 行')
  })

  it('clear empties the history', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, clear, history } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1' })
    push({ wpId: 'wp-2', wpCode: 'E1', sheetName: 'Sheet2' })
    clear()
    expect(history.value.length).toBe(0)
  })

  it('persists to sessionStorage', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1' })
    const stored = sessionStorage.getItem('gt_wp_nav_history')
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored!)
    expect(parsed.length).toBe(1)
    expect(parsed[0].wpId).toBe('wp-1')
  })

  it('push with rowRef stores it correctly', async () => {
    const { useWpNavigationHistory } = await import('../useWpNavigationHistory')
    const { push, lastItem } = useWpNavigationHistory()

    push({ wpId: 'wp-1', wpCode: 'D2A', sheetName: 'Sheet1', rowRef: '第 5 行' })
    expect(lastItem.value!.rowRef).toBe('第 5 行')
  })
})
