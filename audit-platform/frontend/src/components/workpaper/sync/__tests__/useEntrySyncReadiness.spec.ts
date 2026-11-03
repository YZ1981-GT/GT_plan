import { flushPromises } from '@vue/test-utils'
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const readMock = vi.fn()
vi.mock('../workpaperSyncApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../workpaperSyncApi')>()
  return { ...actual, readEntrySyncReadiness: (...args: unknown[]) => readMock(...args) }
})

import type { EntrySyncReadiness } from '../workpaperSyncApi'
import { useEntrySyncReadiness } from '../useEntrySyncReadiness'

function payload(entryId: string): EntrySyncReadiness {
  return {
    entry_id: entryId, effective_entry_id: entryId,
    capability: 'bidirectional', adjudication_state: 'terminal',
    allowed_modes: ['html', 'oo'], can_claim_bidirectional: true,
    runtime: {
      ready: true, adapter_id: 'a', authority_model: 'projection_contract',
      definition_bundle_id: 'b', definition_bundle_sha256: 'a'.repeat(64),
      typed_slots_complete: true, typed_slots: [], representation_id: 'r',
      representation_generation: 1,
    },
    acceptance: {
      state: 'verified', stale: false, run_id: 'run',
      required_scenario_set_digest: 'b'.repeat(64),
    },
    reason: null,
  }
}

const scopes: ReturnType<typeof effectScope>[] = []
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => { readMock.mockReset() })
afterEach(() => { while (scopes.length) scopes.pop()!.stop() })

describe('useEntrySyncReadiness', () => {
  it('同 scope 并发查询只发一次请求', async () => {
    const waiting = deferred<EntrySyncReadiness>()
    readMock.mockReturnValue(waiting.promise)
    const projectId = ref('p')
    const wpId = ref('w')
    const entryId = ref('xlsx/test')
    const scope = effectScope(); scopes.push(scope)
    const values = scope.run(() => [
      useEntrySyncReadiness({ projectId, wpId, entryId }),
      useEntrySyncReadiness({ projectId, wpId, entryId }),
    ])!
    await nextTick()
    expect(readMock).toHaveBeenCalledTimes(1)
    waiting.resolve(payload(entryId.value))
    await waiting.promise; await flushPromises(); await nextTick()
    expect(values.every((value) => value.readiness.value?.runtime.ready)).toBe(true)
  })

  it('换 entry 后丢弃旧响应', async () => {
    const old = deferred<EntrySyncReadiness>()
    const fresh = deferred<EntrySyncReadiness>()
    readMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const entryId = ref('xlsx/old')
    const scope = effectScope(); scopes.push(scope)
    const state = scope.run(() => useEntrySyncReadiness({
      projectId: ref('p'), wpId: ref('w'), entryId,
    }))!
    await nextTick()
    entryId.value = 'xlsx/new'
    await nextTick()
    fresh.resolve(payload('xlsx/new'))
    await fresh.promise; await nextTick()
    old.resolve(payload('xlsx/old'))
    await old.promise; await nextTick()
    expect(state.readiness.value?.entry_id).toBe('xlsx/new')
  })

  it('请求失败保留静态 fail-closed 投影并显示重试态', async () => {
    readMock.mockRejectedValueOnce(new Error('network down'))
    const scope = effectScope(); scopes.push(scope)
    const state = scope.run(() => useEntrySyncReadiness({
      projectId: ref('p'), wpId: ref('w'), entryId: ref('xlsx/b60/gt-b60-bundle'),
    }))!
    await nextTick(); await flushPromises(); await nextTick()
    expect(state.loadState.value).toBe('error')
    expect(state.presentation.value.canSwitchToOnlyOffice).toBe(false)
    expect(state.presentation.value.noticeLabel).toBe('同步状态读取失败')
  })
})

describe('首帧可见性（revalidating）', () => {
  it('已终裁 bidirectional 的 entry 首帧就给开关，不等运行时结果', async () => {
    const waiting = deferred<EntrySyncReadiness>()
    readMock.mockReturnValue(waiting.promise)
    const scope = effectScope(); scopes.push(scope)
    const state = scope.run(() => useEntrySyncReadiness({
      // manifest 里已终裁 bidirectional 的真实 entry（本 spec 第一批裁决之一）
      projectId: ref('p'), wpId: ref('w'), entryId: ref('xlsx/gt-m7-special-reserve'),
    }))!
    await nextTick()
    expect(state.loadState.value).toBe('revalidating')
    expect(state.presentation.value.showModeSwitch).toBe(true)
    expect(state.presentation.value.canClaimBidirectional).toBe(false)
    expect(state.presentation.value.noticeLabel).toBe('正在核验同步状态')

    waiting.resolve(payload('xlsx/gt-m7-special-reserve'))
    await waiting.promise; await flushPromises(); await nextTick()
    expect(state.loadState.value).toBe('ready')
    expect(state.presentation.value.canClaimBidirectional).toBe(true)
  })

  it('pending entry 首帧不长出开关（revalidating 不是无条件放行）', async () => {
    const waiting = deferred<EntrySyncReadiness>()
    readMock.mockReturnValue(waiting.promise)
    const scope = effectScope(); scopes.push(scope)
    const state = scope.run(() => useEntrySyncReadiness({
      projectId: ref('p'), wpId: ref('w'), entryId: ref('xlsx/gt-h9-lease-liabilities'),
    }))!
    await nextTick()
    expect(state.loadState.value).toBe('revalidating')
    expect(state.presentation.value.showModeSwitch).toBe(false)
    expect(state.presentation.value.canSwitchToOnlyOffice).toBe(false)
  })

  it('manifest 里没有的 entry 没有可展示值 ⇒ 仍落 loading', async () => {
    const waiting = deferred<EntrySyncReadiness>()
    readMock.mockReturnValue(waiting.promise)
    const scope = effectScope(); scopes.push(scope)
    const state = scope.run(() => useEntrySyncReadiness({
      projectId: ref('p'), wpId: ref('w'), entryId: ref('xlsx/not-in-manifest-at-all'),
    }))!
    await nextTick()
    expect(state.loadState.value).toBe('loading')
    expect(state.presentation.value.showModeSwitch).toBe(false)
  })
})
