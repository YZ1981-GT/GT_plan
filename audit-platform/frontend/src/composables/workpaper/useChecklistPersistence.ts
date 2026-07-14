/**
 * 统一 checklist response 持久化适配器。
 *
 * Feature: workpaper-maintainability-convergence / Task 2.1
 * Validates: Requirements 3.1, 3.2, 3.5, 3.8
 */
import { getCurrentScope, onScopeDispose, reactive, ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { persistenceMetrics } from './usePersistenceMetrics'

export interface ChecklistResponse {
  item_id: string
  remark: string | null
  conclusion: string | null
  wp_ref?: string | null
  version?: string
  updated_at?: string
}

export interface ChecklistItemPayload {
  item_id: string
  remark: string | null
  conclusion: string | null
  wp_ref: string | null
}

export type PersistenceStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict'

export interface PersistenceState {
  status: PersistenceStatus
  serverVersion?: string
  lastError?: string
}

export interface UseChecklistPersistenceOptions {
  wpId: Ref<string>
  projectId?: Ref<string | undefined>
  debounceMs?: number
  /** 保存提交成功后的横切回调（如 Runtime Boundary 自动版本快照）。 */
  onSaved?: (item: ChecklistResponse) => void | Promise<void>
}

export interface ChecklistPersistence {
  responses: Ref<Map<string, ChecklistResponse>>
  load(): Promise<void>
  hydrate(source: unknown): void
  save(itemId: string, patch: Partial<ChecklistResponse>): Promise<void>
  saveDebounced(itemId: string, patch: Partial<ChecklistResponse>): void
  flush(itemId?: string): Promise<void>
  cancel(itemId?: string): void
  stateOf(itemId: string): PersistenceState
}

type StateRecord = PersistenceState & Record<string, unknown>

function normalizedItem(itemId: string, source?: Partial<ChecklistResponse>): ChecklistResponse {
  return {
    item_id: itemId,
    remark: source?.remark ?? null,
    conclusion: source?.conclusion ?? null,
    wp_ref: source?.wp_ref ?? null,
    ...(source?.version ? { version: source.version } : {}),
    ...(source?.updated_at ? { updated_at: source.updated_at } : {}),
  }
}

function payloadOf(item: ChecklistResponse): ChecklistItemPayload {
  return {
    item_id: item.item_id,
    remark: item.remark ?? null,
    conclusion: item.conclusion ?? null,
    wp_ref: item.wp_ref ?? null,
  }
}

function sourceItems(source: unknown): unknown[] {
  if (source instanceof Map) return [...source.values()]
  if (Array.isArray(source)) return source
  if (!source || typeof source !== 'object') return []

  const value = source as Record<string, unknown>
  if (typeof value.item_id === 'string') return [value]
  for (const key of ['data', 'responses', 'items', 'responses_snapshot', 'checklist_responses']) {
    if (key in value) {
      const nested = sourceItems(value[key])
      if (nested.length > 0 || Array.isArray(value[key])) return nested
    }
  }

  // render-config 的 responses_snapshot/checklist_responses 可能是
  // { [item_id]: { remark, conclusion } }，hydrate 时补回稳定 item_id。
  const mapped = Object.entries(value).flatMap(([itemId, item]) => {
    if (!item || typeof item !== 'object') return []
    const record = item as Record<string, unknown>
    if (!('remark' in record) && !('conclusion' in record) && !('wp_ref' in record)) return []
    return [{ ...record, item_id: typeof record.item_id === 'string' ? record.item_id : itemId }]
  })
  return mapped
}

function versionOf(item: Partial<ChecklistResponse> | undefined): string | undefined {
  return item?.version ?? item?.updated_at
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message
  const detail = (error as any)?.response?.data?.detail
  return typeof detail === 'string' ? detail : '保存失败，请重试'
}

function isCanceled(error: unknown): boolean {
  return (error as any)?.code === 'ERR_CANCELED' || (error as any)?.name === 'CanceledError'
}

export function useChecklistPersistence(
  options: UseChecklistPersistenceOptions,
): ChecklistPersistence {
  const { wpId, projectId, debounceMs = 800 } = options
  const responses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const committed = new Map<string, ChecklistResponse>()
  const states = new Map<string, StateRecord>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const pending = new Set<string>()
  const revisions = new Map<string, number>()
  const generations = new Map<string, number>()
  const inFlight = new Map<string, Promise<void>>()
  const controllers = new Map<string, AbortController>()

  function stateOf(itemId: string): PersistenceState {
    let state = states.get(itemId)
    if (!state) {
      state = reactive<StateRecord>({ status: 'idle' })
      states.set(itemId, state)
    }
    return state
  }

  function setState(itemId: string, next: PersistenceState): void {
    const state = stateOf(itemId) as StateRecord
    state.status = next.status
    state.serverVersion = next.serverVersion
    state.lastError = next.lastError
  }

  function currentGeneration(itemId: string): number {
    return generations.get(itemId) ?? 0
  }

  function applyPatch(itemId: string, patch: Partial<ChecklistResponse>): number {
    const current = responses.value.get(itemId) ?? normalizedItem(itemId)
    const updated = normalizedItem(itemId, { ...current, ...patch, item_id: itemId })
    responses.value.set(itemId, updated)
    const revision = (revisions.get(itemId) ?? 0) + 1
    revisions.set(itemId, revision)
    setState(itemId, { status: 'dirty', serverVersion: stateOf(itemId).serverVersion })
    persistenceMetrics.trackDirty(itemId)
    return revision
  }

  async function persist(
    itemId: string,
    snapshot: ChecklistResponse,
    revision: number,
    generation: number,
  ): Promise<void> {
    if (generation !== currentGeneration(itemId)) return
    if (!wpId.value) {
      const error = new Error('缺少 wpId，无法保存 checklist response')
      setState(itemId, { status: 'error', lastError: error.message })
      throw error
    }

    setState(itemId, { status: 'saving', serverVersion: stateOf(itemId).serverVersion })
    const controller = new AbortController()
    controllers.set(itemId, controller)
    try {
      const body: { items: ChecklistItemPayload[]; project_id?: string } = {
        items: [payloadOf(snapshot)],
      }
      if (projectId?.value) body.project_id = projectId.value

      const result = await api.put<unknown>(
        `/api/workpapers/${wpId.value}/checklist-responses`,
        body,
        { signal: controller.signal, _silent: true } as any,
      )
      if (generation !== currentGeneration(itemId)) return

      const saved = sourceItems(result)[0] as Partial<ChecklistResponse> | undefined
      const persisted = normalizedItem(itemId, { ...snapshot, ...saved })
      committed.set(itemId, persisted)
      const currentRevision = revisions.get(itemId) ?? 0
      if (revision === currentRevision) {
        responses.value.set(itemId, persisted)
        pending.delete(itemId)
        setState(itemId, { status: 'saved', serverVersion: versionOf(persisted) })
        persistenceMetrics.untrackDirty(itemId)
      } else {
        // A newer local patch arrived while this request was in flight. Keep that
        // optimistic value dirty, but remember the actual server baseline so an
        // explicit cancel rolls back to the latest successful save.
        setState(itemId, { status: 'dirty', serverVersion: versionOf(persisted) })
      }
      persistenceMetrics.recordSaveSuccess()
      try {
        await options.onSaved?.(persisted)
      } catch (callbackError) {
        // 横切能力失败不得把已经成功提交的数据伪装成保存失败。
        console.warn('[ChecklistPersistence] onSaved callback failed:', callbackError)
      }
    } catch (error) {
      if (generation !== currentGeneration(itemId) || isCanceled(error)) return
      const status = (error as any)?.response?.status === 409 ? 'conflict' : 'error'
      setState(itemId, {
        status,
        serverVersion: versionOf(committed.get(itemId)),
        lastError: messageOf(error),
      })
      if (status === 'conflict') {
        persistenceMetrics.recordConflict()
      } else {
        persistenceMetrics.recordSaveError()
      }
      pending.add(itemId)
      throw error
    } finally {
      if (controllers.get(itemId) === controller) controllers.delete(itemId)
    }
  }

  async function flushOne(itemId: string): Promise<void> {
    const active = inFlight.get(itemId)
    if (active) {
      try { await active } catch { /* retry latest pending value below */ }
    }
    if (!pending.has(itemId)) return
    const snapshot = normalizedItem(itemId, responses.value.get(itemId))
    const revision = revisions.get(itemId) ?? 0
    const generation = currentGeneration(itemId)
    const operation = persist(itemId, snapshot, revision, generation)
    inFlight.set(itemId, operation)
    try { await operation } finally {
      if (inFlight.get(itemId) === operation) inFlight.delete(itemId)
    }
  }

  function hydrate(source: unknown): void {
    const next = new Map<string, ChecklistResponse>()
    for (const raw of sourceItems(source)) {
      if (!raw || typeof raw !== 'object') continue
      const item = raw as Partial<ChecklistResponse>
      if (!item.item_id) continue
      const normalized = normalizedItem(item.item_id, item)
      next.set(item.item_id, normalized)
      committed.set(item.item_id, normalized)
      setState(item.item_id, { status: 'saved', serverVersion: versionOf(normalized) })
    }
    responses.value = next
  }

  async function load(): Promise<void> {
    if (!wpId.value) return
    hydrate(await api.get<unknown>(`/api/workpapers/${wpId.value}/checklist-responses`))
  }

  async function save(itemId: string, patch: Partial<ChecklistResponse>): Promise<void> {
    const timer = timers.get(itemId)
    if (timer) clearTimeout(timer)
    timers.delete(itemId)
    applyPatch(itemId, patch)
    pending.add(itemId)
    await flushOne(itemId)
  }

  function saveDebounced(itemId: string, patch: Partial<ChecklistResponse>): void {
    applyPatch(itemId, patch)
    pending.add(itemId)
    const timer = timers.get(itemId)
    if (timer) clearTimeout(timer)
    timers.set(itemId, setTimeout(() => {
      timers.delete(itemId)
      void flushOne(itemId).catch(() => undefined)
    }, debounceMs))
  }

  async function flush(itemId?: string): Promise<void> {
    const itemIds = itemId ? [itemId] : [...pending]
    for (const id of itemIds) {
      const timer = timers.get(id)
      if (timer) clearTimeout(timer)
      timers.delete(id)
    }
    await Promise.all(itemIds.map(flushOne))
  }

  function cancel(itemId?: string): void {
    const itemIds = itemId
      ? [itemId]
      : [...new Set([...pending, ...timers.keys(), ...controllers.keys()])]
    for (const id of itemIds) {
      const timer = timers.get(id)
      if (timer) clearTimeout(timer)
      timers.delete(id)
      controllers.get(id)?.abort()
      controllers.delete(id)
      generations.set(id, currentGeneration(id) + 1)
      pending.delete(id)
      const previous = committed.get(id)
      if (previous) {
        responses.value.set(id, normalizedItem(id, previous))
        setState(id, { status: 'saved', serverVersion: versionOf(previous) })
      } else {
        responses.value.delete(id)
        setState(id, { status: 'idle' })
      }
    }
  }

  if (getCurrentScope()) onScopeDispose(() => { void flush().catch(() => undefined) })

  return { responses, load, hydrate, save, saveDebounced, flush, cancel, stateOf }
}

export default useChecklistPersistence
