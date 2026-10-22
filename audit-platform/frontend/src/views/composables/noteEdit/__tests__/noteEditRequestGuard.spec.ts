/**
 * noteEditRequestGuard vitest
 *
 * Feature: partner-manager-edit-permission, Task 17.4
 * Requirements: 10.7, 10.10
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed } from 'vue'
import axios from 'axios'
import { createNoteEditRequestGuard } from '../noteEditRequestGuard'
import type { UseNoteEditPermissionReturn } from '../useNoteEditPermission'

// Mock http module
vi.mock('@/utils/http', () => {
  const interceptors = {
    request: { use: vi.fn(() => 1), eject: vi.fn() },
    response: { use: vi.fn(() => 2), eject: vi.fn() },
  }
  return { default: { interceptors } }
})

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

// Mock coverage matcher
vi.mock('../noteEditCoverage', () => ({
  matchesCoverage: vi.fn((method: string, url: string) => {
    // Simulate: POST /api/disclosure-notes/generate is in coverage
    if (method === 'POST' && url.includes('/disclosure-notes/generate')) return true
    if (method === 'PUT' && url.includes('/disclosure-notes/')) return true
    if (method === 'GET') return false
    return false
  }),
}))

function createMockNoteEdit(canWriteVal = true) {
  const markRejected = vi.fn()
  const refresh = vi.fn()
  return {
    canWrite: computed(() => canWriteVal),
    markRejected,
    refresh,
  } as Pick<UseNoteEditPermissionReturn, 'canWrite' | 'markRejected' | 'refresh'>
}

describe('noteEditRequestGuard', () => {
  let http: any

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('@/utils/http')
    http = mod.default
  })

  it('install registers both interceptors and uninstall ejects them', () => {
    const noteEdit = createMockNoteEdit(true)
    const guard = createNoteEditRequestGuard(noteEdit)
    guard.install()
    expect(http.interceptors.request.use).toHaveBeenCalledOnce()
    expect(http.interceptors.response.use).toHaveBeenCalledOnce()
    guard.uninstall()
    expect(http.interceptors.request.eject).toHaveBeenCalledWith(1)
    expect(http.interceptors.response.eject).toHaveBeenCalledWith(2)
  })

  describe('request interceptor', () => {
    it('blocks coverage write requests when not writable', () => {
      const noteEdit = createMockNoteEdit(false)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const requestHandler = http.interceptors.request.use.mock.calls[0][0]
      const config = { method: 'post', url: '/api/disclosure-notes/generate' }
      expect(() => requestHandler(config)).toThrow()
      try {
        requestHandler(config)
      } catch (e: any) {
        expect(axios.isCancel(e)).toBe(true)
        expect(e.message).toBe('note-edit-readonly')
      }
      guard.uninstall()
    })

    it('allows non-coverage requests even when not writable', () => {
      const noteEdit = createMockNoteEdit(false)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const requestHandler = http.interceptors.request.use.mock.calls[0][0]
      const config = { method: 'get', url: '/api/disclosure-notes/123/456' }
      const result = requestHandler(config)
      expect(result).toBe(config) // passes through
      guard.uninstall()
    })

    it('attaches _forbiddenHandler when writable', () => {
      const noteEdit = createMockNoteEdit(true)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const requestHandler = http.interceptors.request.use.mock.calls[0][0]
      const config = { method: 'post', url: '/api/disclosure-notes/generate' } as any
      const result = requestHandler(config)
      expect(typeof result._forbiddenHandler).toBe('function')
      guard.uninstall()
    })

    it('_forbiddenHandler calls markRejected + ElMessage.error + refresh', async () => {
      const { ElMessage } = await import('element-plus')
      const noteEdit = createMockNoteEdit(true)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const requestHandler = http.interceptors.request.use.mock.calls[0][0]
      const config = { method: 'post', url: '/api/disclosure-notes/generate' } as any
      const result = requestHandler(config)
      // Simulate 403
      result._forbiddenHandler({ response: { data: { message: 'EQCR只读' } } })
      expect(noteEdit.markRejected).toHaveBeenCalledOnce()
      expect(ElMessage.error).toHaveBeenCalledWith('EQCR只读')
      expect(noteEdit.refresh).toHaveBeenCalledOnce()
      guard.uninstall()
    })
  })

  describe('response interceptor', () => {
    it('423 on coverage request calls markRejected + refresh', async () => {
      const noteEdit = createMockNoteEdit(true)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const errorHandler = http.interceptors.response.use.mock.calls[0][1]
      const error = {
        response: { status: 423 },
        config: { method: 'put', url: '/api/disclosure-notes/abc' },
      }
      await expect(errorHandler(error)).rejects.toBe(error)
      expect(noteEdit.markRejected).toHaveBeenCalledOnce()
      expect(noteEdit.refresh).toHaveBeenCalledOnce()
      guard.uninstall()
    })

    it('423 on non-coverage request does not call markRejected', async () => {
      const noteEdit = createMockNoteEdit(true)
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const errorHandler = http.interceptors.response.use.mock.calls[0][1]
      const error = {
        response: { status: 423 },
        config: { method: 'get', url: '/api/other' },
      }
      await expect(errorHandler(error)).rejects.toBe(error)
      expect(noteEdit.markRejected).not.toHaveBeenCalled()
      guard.uninstall()
    })
  })

  it('subsequent requests blocked after markRejected', () => {
    // canWrite becomes false after markRejected
    const canWriteRef = ref(true)
    const noteEdit = {
      canWrite: computed(() => canWriteRef.value),
      markRejected: vi.fn(() => { canWriteRef.value = false }),
      refresh: vi.fn(),
    }
    const guard = createNoteEditRequestGuard(noteEdit)
    guard.install()
    const requestHandler = http.interceptors.request.use.mock.calls[0][0]

    // First request goes through
    const config1 = { method: 'post', url: '/api/disclosure-notes/generate' } as any
    const result1 = requestHandler(config1)
    expect(typeof result1._forbiddenHandler).toBe('function')

    // Simulate 403 triggers markRejected
    result1._forbiddenHandler({ response: { data: 'Forbidden' } })

    // Second request is blocked
    const config2 = { method: 'post', url: '/api/disclosure-notes/generate' } as any
    expect(() => requestHandler(config2)).toThrow()
    guard.uninstall()
  })
})
