import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useTheme } from '../useTheme'

// Helper component to test composable with lifecycle hooks
function withSetup(composable: () => any) {
  let result: any
  const Comp = defineComponent({
    setup() {
      result = composable()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

describe('useTheme', () => {
  let originalMatchMedia: typeof window.matchMedia

  beforeEach(() => {
    // Clear localStorage
    localStorage.clear()
    // Remove dark class
    document.documentElement.classList.remove('dark')
    // Reset module state by reloading
    vi.resetModules()

    // Default: system prefers light
    originalMatchMedia = window.matchMedia
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: originalMatchMedia,
    })
    document.documentElement.classList.remove('dark')
    localStorage.clear()
  })

  it('should default to light when no localStorage and system prefers light', async () => {
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())
    expect(result.isDark.value).toBe(false)
  })

  it('should default to dark when no localStorage and system prefers dark', async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())
    expect(result.isDark.value).toBe(true)
  })

  it('should read dark from localStorage', async () => {
    localStorage.setItem('gt_theme', 'dark')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())
    expect(result.isDark.value).toBe(true)
  })

  it('should read light from localStorage', async () => {
    localStorage.setItem('gt_theme', 'light')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())
    expect(result.isDark.value).toBe(false)
  })

  it('should toggle from light to dark', async () => {
    localStorage.setItem('gt_theme', 'light')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())

    result.toggle()

    expect(result.isDark.value).toBe(true)
    expect(localStorage.getItem('gt_theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('should toggle from dark to light', async () => {
    localStorage.setItem('gt_theme', 'dark')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())

    result.toggle()

    expect(result.isDark.value).toBe(false)
    expect(localStorage.getItem('gt_theme')).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('should apply dark class on mount when isDark is true', async () => {
    localStorage.setItem('gt_theme', 'dark')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    withSetup(() => freshUseTheme())

    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('should not have dark class on mount when isDark is false', async () => {
    localStorage.setItem('gt_theme', 'light')
    const { useTheme: freshUseTheme } = await import('../useTheme')
    withSetup(() => freshUseTheme())

    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('should listen to system theme preference changes', async () => {
    let changeHandler: ((e: MediaQueryListEvent) => void) | null = null
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn((event: string, handler: any) => {
          if (event === 'change') changeHandler = handler
        }),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())

    // Simulate system theme change to dark (no localStorage set)
    expect(changeHandler).not.toBeNull()
    changeHandler!({ matches: true } as MediaQueryListEvent)

    expect(result.isDark.value).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('should NOT follow system preference when localStorage is set', async () => {
    let changeHandler: ((e: MediaQueryListEvent) => void) | null = null
    localStorage.setItem('gt_theme', 'light')
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn((event: string, handler: any) => {
          if (event === 'change') changeHandler = handler
        }),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    const { useTheme: freshUseTheme } = await import('../useTheme')
    const { result } = withSetup(() => freshUseTheme())

    // Simulate system theme change to dark (localStorage IS set)
    changeHandler!({ matches: true } as MediaQueryListEvent)

    // Should NOT change because user has explicit preference
    expect(result.isDark.value).toBe(false)
  })
})
