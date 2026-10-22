/**
 * useNoteEditPermission — vitest
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.1, 10.2, 10.6
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ── Mock http ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
}))

// ── Mock ElMessage ──────────────────────────────────────────────────────────

const mockWarning = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { warning: (...args: any[]) => mockWarning(...args) },
}))

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Make a deferred response: { promise, resolve, reject } */
function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: any) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function okResponse(canEdit: boolean, isEqcr: boolean, reason: string | null = null) {
  return { data: { can_edit: canEdit, is_eqcr: isEqcr, reason } }
}

// ── Import under test (after mocks) ────────────────────────────────────────

import { useNoteEditPermission } from '../useNoteEditPermission'

// ── Test suite ──────────────────────────────────────────────────────────────

describe('useNoteEditPermission', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── Late response: only adopt result if project+sequence matches ──────

  it('discards late response from previous project', async () => {
    const projectId = ref('proj-A')
    const d1 = deferred()
    const d2 = deferred()
    let callIdx = 0
    mockGet.mockImplementation(() => {
      callIdx++
      return callIdx === 1 ? d1.promise : d2.promise
    })

    const api = useNoteEditPermission({
      projectId,
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    expect(api.status.value).toBe('pending')

    // Switch to project B before A responds
    projectId.value = 'proj-B'
    await nextTick()

    // Resolve A's response (late)
    d1.resolve(okResponse(true, false))
    await nextTick()
    // Should still be pending (waiting for B)
    expect(api.status.value).toBe('pending')
    expect(api.decision.value).toBeNull()

    // Resolve B's response
    d2.resolve(okResponse(false, true, '独立复核合伙人（EQCR）在本项目只读'))
    await nextTick()
    expect(api.status.value).toBe('ok')
    expect(api.decision.value?.canEdit).toBe(false)
    expect(api.decision.value?.isEqcr).toBe(true)
  })

  // ── 6 failure types ──────────────────────────────────────────────────

  it('handles 403 failure with backend reason', async () => {
    const err = { response: { status: 403, data: { message: '权限不足' } } }
    mockGet.mockRejectedValueOnce(err)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    // Allow async catch to run
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
    expect(mockWarning).toHaveBeenCalledTimes(1)
    expect(mockWarning.mock.calls[0][0]).toContain('权限不足')
    expect(mockWarning.mock.calls[0][0]).toContain('无法确认编辑权限')
  })

  it('handles network error as failure', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network Error'))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
    expect(mockWarning).toHaveBeenCalledTimes(1)
  })

  it('handles missing can_edit in response as failure', async () => {
    mockGet.mockResolvedValueOnce({ data: { is_eqcr: false } }) // missing can_edit
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
    expect(mockWarning).toHaveBeenCalledTimes(1)
  })

  it('handles missing is_eqcr in response as failure', async () => {
    mockGet.mockResolvedValueOnce({ data: { can_edit: true } }) // missing is_eqcr
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
  })

  it('handles can_edit=false without reason as failure', async () => {
    mockGet.mockResolvedValueOnce({ data: { can_edit: false, is_eqcr: false, reason: null } })
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
  })

  it('handles 500 server error as failure', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 500, data: '服务器内部错误' } })
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('failed')
    expect(mockWarning).toHaveBeenCalledTimes(1)
  })

  // ── 3 cancel types (not failures) ────────────────────────────────────

  it('does not treat AbortError as failure', async () => {
    const abortErr = new DOMException('Aborted', 'AbortError')
    mockGet.mockRejectedValueOnce(abortErr)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    // Should remain pending (cancel is not failure)
    expect(api.status.value).toBe('pending')
    expect(mockWarning).not.toHaveBeenCalled()
  })

  it('does not treat axios cancel as failure', async () => {
    const cancelErr = { __CANCEL__: true, message: 'canceled' }
    mockGet.mockRejectedValueOnce(cancelErr)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('pending')
    expect(mockWarning).not.toHaveBeenCalled()
  })

  it('does not treat note-edit-readonly cancel as failure', async () => {
    const cancelErr = { __CANCEL__: true, message: 'note-edit-readonly' }
    mockGet.mockRejectedValueOnce(cancelErr)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('pending')
    expect(mockWarning).not.toHaveBeenCalled()
  })

  // ── Derived refs ─────────────────────────────────────────────────────

  it('derives canWrite correctly when query succeeds, canEdit, not archived', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.canWrite.value).toBe(true)
    expect(api.canWriteLocked.value).toBe(true)
  })

  it('canWrite is false when archived', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(true),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.canWrite.value).toBe(false)
  })

  it('canWriteLocked is false when forcedReadonly', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(true),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.canWrite.value).toBe(true)
    expect(api.canWriteLocked.value).toBe(false)
  })

  it('showReadonlyBadge is true only for EQCR', async () => {
    mockGet.mockResolvedValueOnce(okResponse(false, true, 'EQCR'))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.showReadonlyBadge.value).toBe(true)
    expect(api.showNonEqcrEntries.value).toBe(false)
  })

  it('showNonEqcrEntries is true for non-EQCR', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.showNonEqcrEntries.value).toBe(true)
    expect(api.showReadonlyBadge.value).toBe(false)
  })

  // ── disabledReason priority ──────────────────────────────────────────

  it('disabledReason is pending message before query completes', () => {
    const d = deferred()
    mockGet.mockReturnValueOnce(d.promise)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    expect(api.disabledReason.value).toBe('正在确认编辑权限…')
  })

  it('disabledReason shows backend reason when not editable', async () => {
    mockGet.mockResolvedValueOnce(okResponse(false, false, '权限不足'))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.disabledReason.value).toBe('权限不足')
  })

  it('disabledReason shows archived when archived overrides editable', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(true),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.disabledReason.value).toBe('项目已归档，无法编辑')
  })

  it('disabledReason shows lock message when only forcedReadonly', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(true),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.disabledReason.value).toBe('他人正在编辑，当前为只读')
  })

  // ── markRejected ─────────────────────────────────────────────────────

  it('markRejected makes canWrite false', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.canWrite.value).toBe(true)
    api.markRejected()
    expect(api.canWrite.value).toBe(false)
  })

  // ── ready() ──────────────────────────────────────────────────────────

  it('ready() resolves immediately when already ok', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    expect(api.status.value).toBe('ok')
    await api.ready() // should not hang
  })

  it('ready() waits for pending query to complete', async () => {
    const d = deferred()
    mockGet.mockReturnValueOnce(d.promise)
    const api = useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    let resolved = false
    api.ready().then(() => { resolved = true })
    await nextTick()
    expect(resolved).toBe(false)
    d.resolve(okResponse(true, false))
    await nextTick()
    await new Promise(r => setTimeout(r, 0))
    await nextTick()
    expect(resolved).toBe(true)
  })

  // ── request params ───────────────────────────────────────────────────

  it('sends request with _silent, _dedupe, timeout, signal', async () => {
    mockGet.mockResolvedValueOnce(okResponse(true, false))
    useNoteEditPermission({
      projectId: ref('p1'),
      isArchived: ref(false),
      forcedReadonly: ref(false),
    })
    await nextTick()
    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url, config] = mockGet.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/edit-permission')
    expect(config._silent).toBe(true)
    expect(config._dedupe).toBe(false)
    expect(config.timeout).toBe(15000)
    expect(config.signal).toBeInstanceOf(AbortSignal)
  })
})
