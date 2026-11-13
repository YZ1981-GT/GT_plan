/**
 * 凭证键 → 各可见底稿凭证检查行的结论（spec voucher-workflow-linkage-lineage-closure R6，design §9）。
 *
 * 与 useVoucherEvidenceIndex 同一合批写法：按「项目 + 年度」合批（同一拍内各行的请求并成一次）、结果缓存 60 秒、
 * 500 键分段、晚到的旧响应丢弃、403 与其他失败分开、`project:reset` 与身份切换时清空。只做提示，不阻断保存。
 */
import { computed, onScopeDispose, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'
import { onRequestIdentityEpochChange } from '@/services/requestIdentityEpoch'
import type { VoucherVerdict } from '@/utils/voucherVerdict'

export const VOUCHER_CONCLUSION_MAX_KEYS = 500
export const VOUCHER_CONCLUSION_CACHE_TTL_MS = 60_000
export const VOUCHER_CONCLUSION_MAX_SCOPES = 32

export interface VoucherConclusionEntry {
  working_paper_id: string
  wp_code: string
  wp_name: string
  verdict: VoucherVerdict
  rows: number
  /** 有行没有凭证身份、按「号|日期」认出 */
  legacy: boolean
}

export type VoucherConclusionStatus = 'idle' | 'loading' | 'ready' | 'forbidden' | 'error'

interface Scope {
  data: Map<string, VoucherConclusionEntry[]>
  cachedAt: Map<string, number>
  /** 后端扫描截断：这批键的结果可能不全 */
  partial: Set<string>
  latest: Map<string, number>
  pending: Set<string>
  errors: Map<string, 'forbidden' | 'error'>
  controllers: Map<number, AbortController>
  scheduled: boolean
  lastAccessedAt: number
  users: number
}

const scopes = new Map<string, Scope>()
const version = shallowRef(0)
let seq = 0
const scopeKey = (projectId: string, year: number) => `${projectId}::${year}`

function scopeOf(key: string): Scope {
  let scope = scopes.get(key)
  if (!scope) {
    while (scopes.size >= VOUCHER_CONCLUSION_MAX_SCOPES) {
      const victim = [...scopes.entries()].filter(([, s]) => s.users === 0)
        .sort((a, b) => a[1].lastAccessedAt - b[1].lastAccessedAt)[0]
      if (!victim) break
      for (const controller of victim[1].controllers.values()) controller.abort()
      scopes.delete(victim[0])
    }
    scope = {
      data: new Map(), cachedAt: new Map(), partial: new Set(), latest: new Map(), pending: new Set(),
      errors: new Map(), controllers: new Map(), scheduled: false, lastAccessedAt: Date.now(), users: 0,
    }
    scopes.set(key, scope)
  }
  scope.lastAccessedAt = Date.now()
  return scope
}

function unwrap(raw: unknown): { conclusions: Record<string, VoucherConclusionEntry[]>; truncated: boolean } {
  const body = (raw ?? {}) as Record<string, any>
  const inner = body.conclusions ? body : (body.data ?? {})
  const conclusions = inner.conclusions && typeof inner.conclusions === 'object' ? inner.conclusions : {}
  return { conclusions, truncated: inner.truncated === true }
}

const isFresh = (scope: Scope, key: string) => {
  const at = scope.cachedAt.get(key)
  return at !== undefined && Date.now() - at < VOUCHER_CONCLUSION_CACHE_TTL_MS
}

async function fetchKeys(projectId: string, year: number, keys: string[]): Promise<void> {
  const scope = scopeOf(scopeKey(projectId, year))
  for (let i = 0; i < keys.length; i += VOUCHER_CONCLUSION_MAX_KEYS) {
    const chunk = keys.slice(i, i + VOUCHER_CONCLUSION_MAX_KEYS)
    const mine = ++seq
    const controller = new AbortController()
    scope.controllers.set(mine, controller)
    for (const key of chunk) {
      scope.latest.set(key, mine)
      scope.errors.delete(key)
    }
    try {
      const res = await http.post(P_ledger.voucherConclusionsQuery(projectId), { year, keys: chunk },
        { _silent: true, _dedupe: false, signal: controller.signal } as any)
      const { conclusions, truncated } = unwrap(res?.data ?? res)
      for (const key of chunk) {
        if (scope.latest.get(key) !== mine) continue
        scope.data.set(key, Array.isArray(conclusions[key]) ? conclusions[key] : [])
        scope.cachedAt.set(key, Date.now())
        if (truncated) scope.partial.add(key)
        else scope.partial.delete(key)
        scope.latest.delete(key)
      }
    } catch (error: any) {
      for (const key of chunk) {
        if (scope.latest.get(key) !== mine) continue
        scope.latest.delete(key)
        if (!controller.signal.aborted) scope.errors.set(key, Number(error?.response?.status) === 403 ? 'forbidden' : 'error')
      }
    } finally {
      scope.controllers.delete(mine)
      version.value += 1
    }
  }
}

function request(projectId: string, year: number | null | undefined, key: string | null | undefined): void {
  if (!projectId || year == null || !key) return
  const scope = scopeOf(scopeKey(projectId, year))
  if (isFresh(scope, key) || scope.latest.has(key) || scope.pending.has(key) || scope.errors.has(key)) return
  scope.pending.add(key)
  if (scope.scheduled) return
  scope.scheduled = true
  queueMicrotask(() => {
    scope.scheduled = false
    const batch = [...scope.pending]
    scope.pending.clear()
    if (batch.length) void fetchKeys(projectId, year, batch)
  })
}

export async function refreshVoucherConclusions(
  projectId: string, year: number | null | undefined, keys: ReadonlyArray<string | null | undefined>,
): Promise<void> {
  const todo = [...new Set(keys.filter((k): k is string => !!k))]
  if (!projectId || year == null || !todo.length) return
  const scope = scopeOf(scopeKey(projectId, year))
  for (const key of todo) scope.errors.delete(key)
  await fetchKeys(projectId, year, todo)
}

export function clearVoucherConclusionsForProject(projectId: string): void {
  for (const [key, scope] of [...scopes]) {
    if (!key.startsWith(`${projectId}::`)) continue
    for (const controller of scope.controllers.values()) controller.abort()
    scopes.delete(key)
  }
  version.value += 1
}

export function resetVoucherConclusionIndexForTest(): void {
  for (const scope of scopes.values()) for (const controller of scope.controllers.values()) controller.abort()
  scopes.clear()
  seq = 0
  version.value += 1
}

export function useVoucherConclusionIndex(
  projectId: MaybeRefOrGetter<string>,
  year: MaybeRefOrGetter<number | null | undefined>,
  voucherKey: MaybeRefOrGetter<string | null | undefined>,
) {
  let held = ''
  const release = () => {
    const scope = held ? scopes.get(held) : undefined
    if (scope) scope.users = Math.max(0, scope.users - 1)
    held = ''
  }
  watch(() => [toValue(projectId), toValue(year), toValue(voucherKey)] as const, ([pid, yr, key]) => {
    const next = pid && yr != null ? scopeKey(pid, yr) : ''
    if (next !== held) {
      release()
      if (next) {
        scopeOf(next).users += 1
        held = next
      }
    }
    request(pid, yr, key)
  }, { immediate: true })
  onScopeDispose(release)
  const state = computed(() => {
    void version.value
    const pid = toValue(projectId)
    const yr = toValue(year)
    const key = toValue(voucherKey)
    const scope = pid && yr != null ? scopes.get(scopeKey(pid, yr)) : undefined
    if (!scope || !key) return { entries: [] as VoucherConclusionEntry[], status: 'idle' as VoucherConclusionStatus, partial: false }
    const loading = scope.latest.has(key) || scope.pending.has(key)
    const failure = scope.errors.get(key)
    const status: VoucherConclusionStatus = loading ? 'loading' : failure ?? (scope.data.has(key) ? 'ready' : 'idle')
    return { entries: scope.data.get(key) ?? [], status, partial: scope.partial.has(key) }
  })
  return {
    entries: computed(() => state.value.entries),
    status: computed(() => state.value.status),
    partial: computed(() => state.value.partial),
    retry: () => refreshVoucherConclusions(toValue(projectId), toValue(year), [toValue(voucherKey)]),
  }
}

eventBus.on('project:reset', ({ projectId }) => clearVoucherConclusionsForProject(projectId))
onRequestIdentityEpochChange(() => resetVoucherConclusionIndexForTest())
