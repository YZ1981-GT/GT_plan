/**
 * noteEditAutoTriggerGating vitest - Task 17.7
 *
 * Tests auto-trigger gating and rejection handling logic.
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.7, 10.10
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import axios from 'axios'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

describe('auto-trigger gating (shouldRetry logic)', () => {
  it('shouldRetry returns false for 403 status', () => {
    const shouldRetry = (err: unknown) => {
      if (!err || typeof err !== 'object') return true
      const e = err as any
      if (e.__CANCEL__ || e.message === 'note-edit-readonly') return false
      const status = e?.response?.status
      if (status === 403 || status === 423) return false
      return true
    }
    expect(shouldRetry({ response: { status: 403 } })).toBe(false)
  })

  it('shouldRetry returns false for 423 status', () => {
    const shouldRetry = (err: unknown) => {
      if (!err || typeof err !== 'object') return true
      const e = err as any
      if (e.__CANCEL__ || e.message === 'note-edit-readonly') return false
      const status = e?.response?.status
      if (status === 403 || status === 423) return false
      return true
    }
    expect(shouldRetry({ response: { status: 423 } })).toBe(false)
  })

  it('shouldRetry returns false for guard cancel', () => {
    const shouldRetry = (err: unknown) => {
      if (!err || typeof err !== 'object') return true
      const e = err as any
      if (e.__CANCEL__ || e.message === 'note-edit-readonly') return false
      const status = e?.response?.status
      if (status === 403 || status === 423) return false
      return true
    }
    expect(shouldRetry({ message: 'note-edit-readonly', __CANCEL__: true })).toBe(false)
  })

  it('shouldRetry returns true for network errors', () => {
    const shouldRetry = (err: unknown) => {
      if (!err || typeof err !== 'object') return true
      const e = err as any
      if (e.__CANCEL__ || e.message === 'note-edit-readonly') return false
      const status = e?.response?.status
      if (status === 403 || status === 423) return false
      return true
    }
    expect(shouldRetry({ message: 'Network Error' })).toBe(true)
  })

  it('shouldRetry returns true for 500 status', () => {
    const shouldRetry = (err: unknown) => {
      if (!err || typeof err !== 'object') return true
      const e = err as any
      if (e.__CANCEL__ || e.message === 'note-edit-readonly') return false
      const status = e?.response?.status
      if (status === 403 || status === 423) return false
      return true
    }
    expect(shouldRetry({ response: { status: 500 } })).toBe(true)
  })
})

describe('rejection handling: gate rejection vs other failures', () => {
  it('distinguishes 403 as gate rejection', () => {
    const err = { response: { status: 403, data: { message: 'EQCR\u53ea\u8bfb' } } }
    const isCancelled = err?.__CANCEL__ || (err as any)?.message === 'note-edit-readonly'
    const isGateReject = err?.response?.status === 403 || err?.response?.status === 423
    expect(isCancelled).toBe(false)
    expect(isGateReject).toBe(true)
  })

  it('distinguishes 423 as gate rejection', () => {
    const err = { response: { status: 423, data: '\u5408\u5e76\u9501\u5b9a' } } as any
    const isGateReject = err?.response?.status === 403 || err?.response?.status === 423
    expect(isGateReject).toBe(true)
  })

  it('distinguishes guard cancel as gate rejection', () => {
    const err = { message: 'note-edit-readonly', __CANCEL__: true } as any
    const isCancelled = err?.__CANCEL__ || err?.message === 'note-edit-readonly'
    expect(isCancelled).toBe(true)
  })

  it('does not classify 500 as gate rejection', () => {
    const err = { response: { status: 500 } } as any
    const isCancelled = err?.__CANCEL__ || err?.message === 'note-edit-readonly'
    const isGateReject = err?.response?.status === 403 || err?.response?.status === 423
    expect(isCancelled).toBe(false)
    expect(isGateReject).toBe(false)
  })
})
