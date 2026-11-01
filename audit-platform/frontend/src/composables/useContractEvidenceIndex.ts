/** 合同证据批量索引：合同键→可见底稿原件，含 TTL、容量、错误与身份清理。 */
import { computed, onScopeDispose, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'
import { onRequestIdentityEpochChange } from '@/services/requestIdentityEpoch'

export const CONTRACT_EVIDENCE_MAX_KEYS = 500
export const CONTRACT_EVIDENCE_CACHE_TTL_MS = 60_000
export const CONTRACT_EVIDENCE_MAX_SCOPES = 32
export const CONTRACT_EVIDENCE_MAX_CACHED_KEYS = 2_000

export interface ContractEvidenceAttachment {
  id: string
  file_name: string
  file_type: string | null
  ocr_status: string | null
  evidence_type: string | null
}
export interface ContractEvidenceEntry {
  working_paper_id: string
  wp_code: string | null
  wp_name: string | null
  attachments: ContractEvidenceAttachment[]
}
type Failure = 'forbidden' | 'error'
interface Scope {
  data: Map<string, ContractEvidenceEntry[]>
  cachedAt: Map<string, number>
  latest: Map<string, number>
  pending: Set<string>
  errors: Map<string, Failure>
  controllers: Map<number, AbortController>
  scheduled: boolean
  lastAccessedAt: number
  users: number
}

const scopes = new Map<string, Scope>()
const version = shallowRef(0)
let sequence = 0
const scopeKey = (projectId: string, wpId: string) => `${projectId}::${wpId}`

function scopeOf(key: string): Scope {
  let scope = scopes.get(key)
  if (!scope) {
    if (scopes.size >= CONTRACT_EVIDENCE_MAX_SCOPES) {
      const victim = [...scopes.entries()]
        .filter(([, scope]) => scope.users === 0)
        .sort((a, b) => a[1].lastAccessedAt - b[1].lastAccessedAt)[0]
      if (victim) {
        for (const controller of victim[1].controllers.values()) controller.abort()
        scopes.delete(victim[0])
      }
    }
    scope = {
      data: new Map(), cachedAt: new Map(), latest: new Map(), pending: new Set(),
      errors: new Map(), controllers: new Map(), scheduled: false, lastAccessedAt: Date.now(), users: 0,
    }
    scopes.set(key, scope)
  }
  scope.lastAccessedAt = Date.now()
  return scope
}

function unwrap(raw: unknown): Record<string, ContractEvidenceEntry[]> {
  const body = (raw ?? {}) as { data?: unknown; evidence?: unknown }
  const nested = body.data as { evidence?: unknown } | undefined
  const value = body.evidence ?? nested?.evidence
  return value && typeof value === 'object' ? value as Record<string, ContractEvidenceEntry[]> : {}
}

function isFresh(scope: Scope, key: string): boolean {
  const at = scope.cachedAt.get(key)
  return at !== undefined && Date.now() - at < CONTRACT_EVIDENCE_CACHE_TTL_MS
}

function trim(scope: Scope): void {
  const extra = scope.data.size - CONTRACT_EVIDENCE_MAX_CACHED_KEYS
  if (extra <= 0) return
  const victims = [...scope.cachedAt.entries()]
    .filter(([key]) => !scope.latest.has(key) && !scope.pending.has(key))
    .sort((a, b) => a[1] - b[1])
  for (const [key] of victims.slice(0, extra)) {
    scope.data.delete(key)
    scope.cachedAt.delete(key)
    scope.errors.delete(key)
  }
}

async function fetchKeys(projectId: string, wpId: string, keys: string[]): Promise<void> {
  if (!projectId || !wpId || !keys.length) return
  const scope = scopeOf(scopeKey(projectId, wpId))
  for (let offset = 0; offset < keys.length; offset += CONTRACT_EVIDENCE_MAX_KEYS) {
    const chunk = keys.slice(offset, offset + CONTRACT_EVIDENCE_MAX_KEYS)
    const mine = ++sequence
    const controller = new AbortController()
    scope.controllers.set(mine, controller)
    for (const key of chunk) {
      scope.latest.set(key, mine)
      scope.errors.delete(key)
    }
    try {
      const response = await http.post(
        P_att.evidenceContractQuery(projectId, wpId), { keys: chunk },
        { _silent: true, _dedupe: false, signal: controller.signal } as any,
      )
      const found = unwrap(response?.data ?? response)
      for (const key of chunk) {
        if (scope.latest.get(key) !== mine) continue
        scope.data.set(key, Array.isArray(found[key]) ? found[key] : [])
        scope.cachedAt.set(key, Date.now())
        scope.latest.delete(key)
      }
      trim(scope)
    } catch (error: any) {
      for (const key of chunk) {
        if (scope.latest.get(key) !== mine) continue
        scope.latest.delete(key)
        if (!controller.signal.aborted) {
          scope.errors.set(key, Number(error?.response?.status) === 403 ? 'forbidden' : 'error')
        }
      }
    } finally {
      scope.controllers.delete(mine)
      version.value += 1
    }
  }
}

function schedule(projectId: string, wpId: string): void {
  const scope = scopeOf(scopeKey(projectId, wpId))
  if (scope.scheduled) return
  scope.scheduled = true
  queueMicrotask(() => {
    scope.scheduled = false
    const keys = [...scope.pending]
    scope.pending.clear()
    if (keys.length) void fetchKeys(projectId, wpId, keys)
  })
}

export function requestContractEvidence(projectId: string, wpId: string, key: string): void {
  if (!projectId || !wpId || !key) return
  const scope = scopeOf(scopeKey(projectId, wpId))
  if (scope.data.has(key) && !isFresh(scope, key)) {
    scope.data.delete(key)
    scope.cachedAt.delete(key)
  }
  if (isFresh(scope, key) || scope.latest.has(key) || scope.pending.has(key) || scope.errors.has(key)) return
  scope.pending.add(key)
  schedule(projectId, wpId)
}

export async function refreshContractEvidence(
  projectId: string, wpId: string, keys: ReadonlyArray<string | null | undefined>,
): Promise<void> {
  const todo = [...new Set(keys.filter((key): key is string => !!key))]
  if (!todo.length) return
  const scope = scopeOf(scopeKey(projectId, wpId))
  for (const key of todo) scope.errors.delete(key)
  await fetchKeys(projectId, wpId, todo)
}

export function contractEvidenceOf(
  projectId: string, wpId: string, key: string | null | undefined,
): ContractEvidenceEntry[] {
  void version.value
  if (!projectId || !wpId || !key) return []
  requestContractEvidence(projectId, wpId, key)
  return scopeOf(scopeKey(projectId, wpId)).data.get(key) ?? []
}

export function clearContractEvidenceForProject(projectId: string): void {
  for (const [key, scope] of [...scopes]) {
    if (!key.startsWith(`${projectId}::`)) continue
    for (const controller of scope.controllers.values()) controller.abort()
    scopes.delete(key)
  }
  version.value += 1
}

export function resetContractEvidenceIndexForTest(): void {
  for (const scope of scopes.values()) for (const controller of scope.controllers.values()) controller.abort()
  scopes.clear()
  sequence = 0
  version.value += 1
}

export function useContractEvidenceIndex(
  projectId: MaybeRefOrGetter<string>, wpId: MaybeRefOrGetter<string>,
  contractKey: MaybeRefOrGetter<string | null | undefined>,
) {
  let heldScope = ''
  const release = () => {
    if (!heldScope) return
    const held = scopes.get(heldScope)
    if (held) held.users = Math.max(0, held.users - 1)
    heldScope = ''
  }
  watch(
    () => [toValue(projectId), toValue(wpId), toValue(contractKey)] as const,
    ([pid, wid, key]) => {
      const nextScope = pid && wid ? scopeKey(pid, wid) : ''
      if (nextScope !== heldScope) {
        release()
        if (nextScope) {
          scopeOf(nextScope).users += 1
          heldScope = nextScope
        }
      }
      if (pid && wid && key) requestContractEvidence(pid, wid, key)
    },
    { immediate: true },
  )
  onScopeDispose(release)
  const state = computed(() => {
    void version.value
    const pid = toValue(projectId)
    const wid = toValue(wpId)
    const key = toValue(contractKey)
    const scope = pid && wid ? scopes.get(scopeKey(pid, wid)) : undefined
    const entries = key ? scope?.data.get(key) ?? [] : []
    const failure = key ? scope?.errors.get(key) : undefined
    const loading = !!key && (!!scope?.latest.has(key) || !!scope?.pending.has(key))
    return {
      entries, loading,
      error: failure === 'error', forbidden: failure === 'forbidden',
      status: loading ? 'loading' : failure ?? (key && scope?.data.has(key) ? (entries.length ? 'ready' : 'empty') : 'idle'),
    }
  })
  return {
    entries: computed(() => state.value.entries),
    loading: computed(() => state.value.loading),
    error: computed(() => state.value.error),
    forbidden: computed(() => state.value.forbidden),
    status: computed(() => state.value.status),
    retry: () => refreshContractEvidence(toValue(projectId), toValue(wpId), [toValue(contractKey)]),
  }
}

eventBus.on('project:reset', ({ projectId }) => clearContractEvidenceForProject(projectId))
onRequestIdentityEpochChange(() => resetContractEvidenceIndexForTest())
