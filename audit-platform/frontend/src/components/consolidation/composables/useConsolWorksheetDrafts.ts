import { computed, ref } from 'vue'
import { clonePlain } from '@/utils/cloneable'

function digest(value: unknown): string {
  return JSON.stringify(value ?? null)
}

export function useConsolWorksheetDrafts() {
  const baselines = new Map<string, unknown>()
  const drafts = new Map<string, unknown>()
  const dirtyKeys = ref<Set<string>>(new Set())

  function publishDirty(next: Set<string>): void {
    dirtyKeys.value = next
  }

  function recalculate(key: string): void {
    const next = new Set(dirtyKeys.value)
    if (digest(drafts.get(key)) === digest(baselines.get(key))) next.delete(key)
    else next.add(key)
    publishDirty(next)
  }

  function prime(key: string, payload: unknown): void {
    const snapshot = clonePlain(payload)
    baselines.set(key, snapshot)
    drafts.set(key, clonePlain(snapshot))
    const next = new Set(dirtyKeys.value)
    next.delete(key)
    publishDirty(next)
  }

  function update(key: string, payload: unknown): void {
    drafts.set(key, clonePlain(payload))
    recalculate(key)
  }

  function markSaved(key: string, savedPayload: unknown): void {
    baselines.set(key, clonePlain(savedPayload))
    if (!drafts.has(key)) drafts.set(key, clonePlain(savedPayload))
    recalculate(key)
  }

  function discard(key: string): unknown {
    const baseline = clonePlain(baselines.get(key))
    drafts.set(key, clonePlain(baseline))
    recalculate(key)
    return baseline
  }

  function clear(): void {
    baselines.clear()
    drafts.clear()
    publishDirty(new Set())
  }

  return {
    dirtyKeys,
    hasDirty: computed(() => dirtyKeys.value.size > 0),
    prime,
    update,
    markSaved,
    discard,
    clear,
    current: (key: string) => clonePlain(drafts.get(key)),
    baseline: (key: string) => clonePlain(baselines.get(key)),
  }
}
