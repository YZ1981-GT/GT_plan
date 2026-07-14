import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { useChecklistPersistence } from './useChecklistPersistence'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useChecklistPersistence', () => {
  it('loads a response envelope and hydrates saved state', async () => {
    vi.mocked(api.get).mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{
        item_id: 'D2-note', remark: 'loaded', conclusion: null,
        wp_ref: 'wp:D2-1', version: 'v1',
      }],
    })
    const persistence = useChecklistPersistence({ wpId: ref('wp-1') })

    await persistence.load()

    expect(api.get).toHaveBeenCalledWith('/api/workpapers/wp-1/checklist-responses')
    expect(persistence.responses.value.get('D2-note')).toMatchObject({
      remark: 'loaded', wp_ref: 'wp:D2-1',
    })
    expect(persistence.stateOf('D2-note')).toMatchObject({
      status: 'saved', serverVersion: 'v1',
    })
  })

  it('saves the standard payload without fabricating project_id', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: [{ item_id: 'D2-note', remark: 'new', conclusion: null, wp_ref: null, version: 'v2' }],
    })
    const persistence = useChecklistPersistence({ wpId: ref('wp-2') })

    await persistence.save('D2-note', { remark: 'new' })

    expect(api.put).toHaveBeenCalledWith(
      '/api/workpapers/wp-2/checklist-responses',
      { items: [{ item_id: 'D2-note', remark: 'new', conclusion: null, wp_ref: null }] },
      expect.objectContaining({ signal: expect.any(AbortSignal), _silent: true }),
    )
    expect(persistence.stateOf('D2-note')).toMatchObject({
      status: 'saved', serverVersion: 'v2',
    })
  })

  it('keeps debounce timers isolated and lets cancel target one item', async () => {
    vi.useFakeTimers()
    vi.mocked(api.put).mockImplementation(async (_url, body: any) => body.items)
    const persistence = useChecklistPersistence({ wpId: ref('wp-3'), debounceMs: 50 })

    persistence.saveDebounced('item-a', { remark: 'first' })
    persistence.saveDebounced('item-a', { remark: 'last' })
    persistence.saveDebounced('item-b', { remark: 'discarded' })
    persistence.cancel('item-b')
    await vi.runAllTimersAsync()

    expect(api.put).toHaveBeenCalledTimes(1)
    expect((vi.mocked(api.put).mock.calls[0][1] as any).items[0]).toMatchObject({
      item_id: 'item-a', remark: 'last',
    })
    expect(persistence.stateOf('item-a').status).toBe('saved')
    expect(persistence.stateOf('item-b').status).toBe('idle')
  })

  it('flushes pending changes when the owning scope is disposed', async () => {
    vi.useFakeTimers()
    vi.mocked(api.put).mockImplementation(async (_url, body: any) => body.items)
    const scope = effectScope()
    const persistence = scope.run(() => useChecklistPersistence({
      wpId: ref('wp-4'), debounceMs: 10_000,
    }))!
    persistence.saveDebounced('dispose-me', { conclusion: 'Y' })

    scope.stop()
    await vi.waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))

    expect((vi.mocked(api.put).mock.calls[0][1] as any).items[0]).toMatchObject({
      item_id: 'dispose-me', conclusion: 'Y',
    })
  })

  it('cancels back to the latest successful in-flight baseline', async () => {
    vi.useFakeTimers()
    const first = deferred<unknown>()
    vi.mocked(api.put)
      .mockImplementationOnce(() => first.promise)
      .mockRejectedValueOnce(new Error('second save failed'))
    const persistence = useChecklistPersistence({ wpId: ref('wp-5'), debounceMs: 20 })

    const firstSave = persistence.save('same-item', { remark: 'persisted-first' })
    persistence.saveDebounced('same-item', { remark: 'local-second' })
    first.resolve({
      data: [{ item_id: 'same-item', remark: 'persisted-first', conclusion: null, version: 'v1' }],
    })
    await firstSave
    expect(persistence.stateOf('same-item')).toMatchObject({ status: 'dirty', serverVersion: 'v1' })

    await vi.runAllTimersAsync()
    expect(persistence.stateOf('same-item').status).toBe('error')
    expect(persistence.responses.value.get('same-item')?.remark).toBe('local-second')

    persistence.cancel('same-item')
    expect(persistence.responses.value.get('same-item')?.remark).toBe('persisted-first')
    expect(persistence.stateOf('same-item')).toMatchObject({ status: 'saved', serverVersion: 'v1' })
  })

  it('hydrates render-config response maps without losing item ids', () => {
    const persistence = useChecklistPersistence({ wpId: ref('wp-j2') })

    persistence.hydrate({
      responses_snapshot: {
        'J2-1-note': { remark: '审计说明', conclusion: null },
        'J2-1-conclusion': { remark: '审计结论', conclusion: null },
      },
    })

    expect([...persistence.responses.value.keys()]).toEqual([
      'J2-1-note',
      'J2-1-conclusion',
    ])
    expect(persistence.responses.value.get('J2-1-note')?.remark).toBe('审计说明')
  })

  it('persists multiple J2 sections independently and notifies the runtime after success', async () => {
    vi.useFakeTimers()
    const onSaved = vi.fn()
    vi.mocked(api.put).mockImplementation(async (_url, body: any) => ({ data: body.items }))
    const persistence = useChecklistPersistence({
      wpId: ref('wp-j2'),
      projectId: ref('project-j2'),
      debounceMs: 20,
      onSaved,
    })

    persistence.saveDebounced('J2-listed-summary', { remark: '[{"key":"dbp"}]' })
    persistence.saveDebounced('J2-listed-note-dbp', { remark: '上市公司披露说明' })
    persistence.saveDebounced('J2-soe-note-dbp', { remark: '国企披露说明' })
    await vi.runAllTimersAsync()

    expect(api.put).toHaveBeenCalledTimes(3)
    expect(new Set(vi.mocked(api.put).mock.calls.map(call => (call[1] as any).items[0].item_id))).toEqual(
      new Set(['J2-listed-summary', 'J2-listed-note-dbp', 'J2-soe-note-dbp']),
    )
    expect(onSaved).toHaveBeenCalledTimes(3)
    expect(persistence.stateOf('J2-listed-summary').status).toBe('saved')
    expect(persistence.stateOf('J2-soe-note-dbp').status).toBe('saved')
  })
})