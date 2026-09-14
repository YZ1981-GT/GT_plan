// Feature: zero-downtime-deployment, Property 3
/**
 * Property 3：版本不一致触发非阻断提示且不强制刷新
 * Validates: Requirements 1.4, 1.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'

// Mock Vue lifecycle hooks before importing the composable
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...(actual as any),
    onMounted: vi.fn((cb: () => void) => cb()),
    onUnmounted: vi.fn(),
  }
})

// Mock fetch to prevent real network calls from the polling timer
vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })))

import { useVersionCheck } from '../useVersionCheck'

describe('Property 3: 版本不一致触发非阻断提示且不强制刷新', () => {
  let reloadSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    // Mock location.reload - need to redefine since it's not configurable by default
    reloadSpy = vi.fn() as any
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadSpy },
      writable: true,
    })
  })

  it('version mismatch triggers updateAvailable, match keeps false, never reloads', () => {
    // Generate 7-char hex-like commit hashes
    const commitHash = fc.stringMatching(/^[0-9a-f]{7}$/)

    fc.assert(
      fc.property(
        commitHash,
        commitHash,
        (local, server) => {
          const { updateAvailable, recordServerVersion } = useVersionCheck()

          // First call locks local version
          recordServerVersion(local)

          // Second call with potentially different version
          recordServerVersion(server)

          if (local !== server) {
            expect(updateAvailable.value).toBe(true)
          } else {
            expect(updateAvailable.value).toBe(false)
          }

          // Never calls location.reload (composable itself must not force refresh)
          expect(reloadSpy).not.toHaveBeenCalled()
        },
      ),
      { numRuns: 5 },
    )
  })

  it('empty version string does not lock or trigger update', () => {
    const { updateAvailable, localVersion, recordServerVersion } = useVersionCheck()

    recordServerVersion('')
    expect(localVersion.value).toBe('')
    expect(updateAvailable.value).toBe(false)
  })

  it('dismiss resets updateAvailable to false', () => {
    const { updateAvailable, recordServerVersion, dismiss } = useVersionCheck()

    recordServerVersion('abc1234')
    recordServerVersion('def5678')
    expect(updateAvailable.value).toBe(true)

    dismiss()
    expect(updateAvailable.value).toBe(false)
  })
})
