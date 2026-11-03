/** 凭证键→可见底稿证据的合批索引，含 TTL、容量、错误状态与项目/身份清理。 */
import { computed, onScopeDispose, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'
import { onRequestIdentityEpochChange } from '@/services/requestIdentityEpoch'

export const VOUCHER_EVIDENCE_MAX_KEYS = 500
export const VOUCHER_EVIDENCE_CACHE_TTL_MS = 60_000
export const VOUCHER_EVIDENCE_MAX_SCOPES = 32
export const VOUCHER_EVIDENCE_MAX_CACHED_KEYS = 2_000

export interface VoucherEvidenceAttachment {
  id: string
  file_name: string
  file_type: string | null
  ocr_status: string | null
  evidence_type: string | null
}

export interface VoucherEvidenceEntry {
  working_paper_id: string
  wp_code: string | null
  wp_name: string | null
  attachments: VoucherEvidenceAttachment[]
}

type EvidenceIndexError = 'forbidden' | 'error'
interface Scope {
  data: Map<string, VoucherEvidenceEntry[]>
  cachedAt: Map<string, number>
  latest: Map<string, number>
  pending: Set<string>
  errors: Map<string, EvidenceIndexError>
  controllers: Map<number, AbortController>
  scheduled: boolean
  lastAccessedAt: number
  users: number
}

const scopes = new Map<string, Scope>()
const version = shallowRef(0)
let seq = 0
const scopeKey = (projectId: string, year: number) => `${projectId}::${year}`

function evictScopes(): void {
  while (scopes.size >= VOUCHER_EVIDENCE_MAX_SCOPES) {
    const victim = [...scopes.entries()]
      .filter(([, scope]) => scope.users === 0)
      .sort((a, b) => a[1].lastAccessedAt - b[1].lastAccessedAt)[0]
    if (!victim) return
    for (const controller of victim[1].controllers.values()) controller.abort()
    scopes.delete(victim[0])
  }
}

function scopeOf(key: string): Scope {
  let scope = scopes.get(key)
  if (!scope) {
    evictScopes()
    scope = {
      data: new Map(), cachedAt: new Map(), latest: new Map(), pending: new Set(),
      errors: new Map(), controllers: new Map(), scheduled: false, lastAccessedAt: Date.now(), users: 0,
    }
    scopes.set(key, scope)
  }
  scope.lastAccessedAt = Date.now()
  return scope
}

function unwrapEvidence(raw: unknown): Record<string, VoucherEvidenceEntry[]> {
  const body = (raw ?? {}) as { data?: unknown; evidence?: unknown }
  const inner = (body.evidence ?? (body.data as { evidence?: unknown } | undefined)?.evidence) as unknown
  return inner && typeof inner === 'object' ? inner as Record<string, VoucherEvidenceEntry[]> : {}
}

function trimKeys(scope: Scope): void {
  if (scope.data.size <= VOUCHER_EVIDENCE_MAX_CACHED_KEYS) return
  const victims = [...scope.cachedAt.entries()]
    .filter(([key]) => !scope.latest.has(key) && !scope.pending.has(key))
    .sort((a, b) => a[1] - b[1])
  for (const [key] of victims.slice(0, scope.data.size - VOUCHER_EVIDENCE_MAX_CACHED_KEYS)) {
    scope.data.delete(key)
    scope.cachedAt.delete(key)
    scope.errors.delete(key)
  }
}

function isFresh(scope: Scope, key: string): boolean {
  const at = scope.cachedAt.get(key)
  return at !== undefined && Date.now() - at < VOUCHER_EVIDENCE_CACHE_TTL_MS
}

async function fetchKeys(projectId: string, year: number, keys: string[]): Promise<void> {
  const scope = scopeOf(scopeKey(projectId, year))
  for (let i = 0; i < keys.length; i += VOUCHER_EVIDENCE_MAX_KEYS) {
    const chunk = keys.slice(i, i + VOUCHER_EVIDENCE_MAX_KEYS)
    const mine = ++seq
    const controller = new AbortController()
    scope.controllers.set(mine, controller)
    for (const key of chunk) {
      scope.latest.set(key, mine)
      scope.errors.delete(key)
    }
    try {
      const res = await http.post(
        P_ledger.voucherEvidenceQuery(projectId),
        { year, keys: chunk },
        { _silent: true, _dedupe: false, signal: controller.signal } as any,
      )
      const found = unwrapEvidence(res?.data ?? res)
      for (const key of chunk) {
        if (scope.latest.get(key) !== mine) continue
        scope.data.set(key, Array.isArray(found[key]) ? found[key] : [])
        scope.cachedAt.set(key, Date.now())
        scope.latest.delete(key)
      }
      trimKeys(scope)
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

function schedule(projectId: string, year: number): void {
  const scope = scopeOf(scopeKey(projectId, year))
  if (scope.scheduled) return
  scope.scheduled = true
  queueMicrotask(() => {
    scope.scheduled = false
    const keys = [...scope.pending]
    scope.pending.clear()
    if (keys.length) void fetchKeys(projectId, year, keys)
  })
}

export function requestVoucherEvidence(projectId: string, year: number | null | undefined, key: string): void {
  if (!projectId || year == null || !key) return
  const scope = scopeOf(scopeKey(projectId, year))
  if (scope.data.has(key) && !isFresh(scope, key)) {
    scope.data.delete(key)
    scope.cachedAt.delete(key)
  }
  if (isFresh(scope, key) || scope.latest.has(key) || scope.pending.has(key) || scope.errors.has(key)) return
  scope.pending.add(key)
  schedule(projectId, year)
}

export async function refreshVoucherEvidence(
  projectId: string,
  year: number | null | undefined,
  keys: ReadonlyArray<string | null | undefined>,
): Promise<void> {
  const todo = [...new Set(keys.filter((key): key is string => !!key))]
  if (!projectId || year == null || !todo.length) return
  const scope = scopeOf(scopeKey(projectId, year))
  for (const key of todo) scope.errors.delete(key)
  await fetchKeys(projectId, year, todo)
}

export type VoucherEvidenceIndexStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'forbidden' | 'error'

export function voucherEvidenceStatusOf(
  projectId: string,
  year: number | null | undefined,
  key: string | null | undefined,
): VoucherEvidenceIndexStatus {
  void version.value
  if (!projectId || year == null || !key) return 'idle'
  const scope = scopes.get(scopeKey(projectId, year))
  if (!scope) return 'idle'
  if (scope.latest.has(key) || scope.pending.has(key)) return 'loading'
  const failure = scope.errors.get(key)
  if (failure) return failure
  if (!scope.data.has(key)) return 'idle'
  return (scope.data.get(key)?.length ?? 0) > 0 ? 'ready' : 'empty'
}

export function voucherEvidenceOf(
  projectId: string,
  year: number | null | undefined,
  key: string | null | undefined,
): VoucherEvidenceEntry[] {
  void version.value
  if (!projectId || year == null || !key) return []
  requestVoucherEvidence(projectId, year, key)
  return scopes.get(scopeKey(projectId, year))?.data.get(key) ?? []
}

export function clearVoucherEvidenceForProject(projectId: string): void {
  for (const [key, scope] of [...scopes]) {
    if (!key.startsWith(`${projectId}::`)) continue
    for (const controller of scope.controllers.values()) controller.abort()
    scopes.delete(key)
  }
  version.value += 1
}

export function resetVoucherEvidenceIndexForTest(): void {
  for (const scope of scopes.values()) {
    for (const controller of scope.controllers.values()) controller.abort()
  }
  scopes.clear()
  seq = 0
  version.value += 1
}

export function useVoucherEvidenceIndex(
  projectId: MaybeRefOrGetter<string>,
  year: MaybeRefOrGetter<number | null | undefined>,
  voucherKey: MaybeRefOrGetter<string | null | undefined>,
) {
  let heldScope = ''
  const release = () => {
    if (!heldScope) return
    const held = scopes.get(heldScope)
    if (held) held.users = Math.max(0, held.users - 1)
    heldScope = ''
  }
  watch(
    () => [toValue(projectId), toValue(year), toValue(voucherKey)] as const,
    ([pid, yr, key]) => {
      const nextScope = pid && yr != null ? scopeKey(pid, yr) : ''
      if (nextScope !== heldScope) {
        release()
        if (nextScope) {
          scopeOf(nextScope).users += 1
          heldScope = nextScope
        }
      }
      if (pid && key && yr != null) requestVoucherEvidence(pid, yr, key)
    },
    { immediate: true },
  )
  onScopeDispose(release)
  const state = computed(() => {
    void version.value
    const pid = toValue(projectId)
    const yr = toValue(year)
    const key = toValue(voucherKey)
    const scope = pid && yr != null ? scopes.get(scopeKey(pid, yr)) : undefined
    const entries = key ? scope?.data.get(key) ?? [] : []
    const failure = key ? scope?.errors.get(key) : undefined
    const loading = !!key && (!!scope?.latest.has(key) || !!scope?.pending.has(key))
    return {
      entries,
      loading,
      error: failure === 'error',
      forbidden: failure === 'forbidden',
      status: loading ? 'loading' : failure ?? (key && scope?.data.has(key) ? (entries.length ? 'ready' : 'empty') : 'idle'),
    }
  })
  return {
    entries: computed(() => state.value.entries),
    loading: computed(() => state.value.loading),
    error: computed(() => state.value.error),
    forbidden: computed(() => state.value.forbidden),
    status: computed(() => state.value.status),
    retry: () => refreshVoucherEvidence(toValue(projectId), toValue(year), [toValue(voucherKey)]),
  }
}

eventBus.on('project:reset', ({ projectId }) => clearVoucherEvidenceForProject(projectId))
onRequestIdentityEpochChange(() => resetVoucherEvidenceIndexForTest())
