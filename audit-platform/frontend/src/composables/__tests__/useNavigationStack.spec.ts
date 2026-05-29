/**
 * useNavigationStack unit tests — V3 Req 8.3.1
 * Validates: push/pop/clear/canGoBack/maxDepth/jumpTo
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useRoute: () => ({
    fullPath: '/projects/1/trial-balance',
    params: { projectId: '1' },
    query: { year: '2025' },
    meta: { title: '试算表' },
  }),
}))

// We need to reset the singleton stack between tests
// Import after mock setup
import { useNavigationStack, MAX_STACK_DEPTH, type NavigationEntry } from '../useNavigationStack'

describe('useNavigationStack', () => {
  let navStack: ReturnType<typeof useNavigationStack>

  beforeEach(() => {
    navStack = useNavigationStack()
    navStack.clear()
  })

  it('starts with empty stack', () => {
    expect(navStack.stack.value).toHaveLength(0)
    expect(navStack.canGoBack.value).toBe(false)
  })

  it('push adds entry to stack', () => {
    const entry: NavigationEntry = { source_view: '/projects/1/trial-balance', label: '试算表' }
    navStack.push(entry)
    expect(navStack.stack.value).toHaveLength(1)
    expect(navStack.stack.value[0]).toEqual(entry)
    expect(navStack.canGoBack.value).toBe(true)
  })

  it('push multiple entries maintains order', () => {
    navStack.push({ source_view: '/a', label: 'A' })
    navStack.push({ source_view: '/b', label: 'B' })
    navStack.push({ source_view: '/c', label: 'C' })
    expect(navStack.stack.value).toHaveLength(3)
    expect(navStack.stack.value[0].source_view).toBe('/a')
    expect(navStack.stack.value[2].source_view).toBe('/c')
  })

  it('pop removes and returns last entry', () => {
    navStack.push({ source_view: '/a', label: 'A' })
    navStack.push({ source_view: '/b', label: 'B' })
    const popped = navStack.pop()
    expect(popped?.source_view).toBe('/b')
    expect(navStack.stack.value).toHaveLength(1)
    expect(navStack.stack.value[0].source_view).toBe('/a')
  })

  it('pop returns undefined when stack is empty', () => {
    const popped = navStack.pop()
    expect(popped).toBeUndefined()
  })

  it('clear empties the stack', () => {
    navStack.push({ source_view: '/a', label: 'A' })
    navStack.push({ source_view: '/b', label: 'B' })
    navStack.clear()
    expect(navStack.stack.value).toHaveLength(0)
    expect(navStack.canGoBack.value).toBe(false)
  })

  it('canGoBack is true when stack has entries', () => {
    expect(navStack.canGoBack.value).toBe(false)
    navStack.push({ source_view: '/a', label: 'A' })
    expect(navStack.canGoBack.value).toBe(true)
    navStack.pop()
    expect(navStack.canGoBack.value).toBe(false)
  })

  it('enforces MAX_STACK_DEPTH (oldest entries are shifted out)', () => {
    // Push more than MAX_STACK_DEPTH entries
    for (let i = 0; i < MAX_STACK_DEPTH + 5; i++) {
      navStack.push({ source_view: `/page-${i}`, label: `Page ${i}` })
    }
    expect(navStack.stack.value).toHaveLength(MAX_STACK_DEPTH)
    // The oldest 5 entries should have been shifted out
    expect(navStack.stack.value[0].source_view).toBe('/page-5')
    expect(navStack.stack.value[MAX_STACK_DEPTH - 1].source_view).toBe(`/page-${MAX_STACK_DEPTH + 4}`)
  })

  it('MAX_STACK_DEPTH is 20', () => {
    expect(MAX_STACK_DEPTH).toBe(20)
  })

  it('preserves NavigationEntry fields (direction, scroll_position, query)', () => {
    const entry: NavigationEntry = {
      source_view: '/projects/1/reports',
      label: '报表',
      direction: 'down',
      scroll_position: 500,
      query: { tab: 'balance_sheet' },
    }
    navStack.push(entry)
    expect(navStack.stack.value[0]).toEqual(entry)
  })
})
