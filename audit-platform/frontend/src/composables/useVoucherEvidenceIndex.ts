/**
 * 凭证证据索引：凭证键 → 本项目各可见底稿已取得的这张凭证的证据（spec attachment-voucher-evidence-binding 需求 2.1、3.4）
 *
 * 凭证检查表每行一个「来源」列组件，逐行查会发几百个请求 ⇒ 同一时刻登记的键合成一次请求
 * （`POST …/ledger/voucher-evidence/query`，键里有主体名称走请求体，一次最多 500 个，超过分段顺序发）。
 *
 * - 按（项目, 年度）缓存：查过的键（含没有证据的）不再查；引用 / 上传后 `refreshVoucherEvidence` 只重查这几个键；
 * - 竞态：每个键记最近一次为它发起的请求序号，晚到的旧响应不覆盖（不比时间戳）；
 * - 查不到（网络 / 权限）只是不显示提示，不打断编辑；失败的键不进缓存，下次再查；
 * - 审计年度未知（项目没填）不查：凭证键带年度，拼不出来。
 */
import { computed, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'

export const VOUCHER_EVIDENCE_MAX_KEYS = 500

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

interface Scope {
  /** 凭证键 → 各底稿的证据；查过但没有的存空数组 */
  data: Map<string, VoucherEvidenceEntry[]>
  /** 凭证键 → 最近一次为它发起的请求序号 */
  latest: Map<string, number>
  pending: Set<string>
  scheduled: boolean
}

const scopes = new Map<string, Scope>()
const version = shallowRef(0)
let seq = 0

const scopeKey = (projectId: string, year: number) => `${projectId}::${year}`

function scopeOf(key: string): Scope {
  let scope = scopes.get(key)
  if (!scope) {
    scope = { data: new Map(), latest: new Map(), pending: new Set(), scheduled: false }
    scopes.set(key, scope)
  }
  return scope
}

function unwrapEvidence(raw: unknown): Record<string, VoucherEvidenceEntry[]> {
  const body = (raw ?? {}) as { data?: unknown; evidence?: unknown }
  const inner = (body.evidence ?? (body.data as { evidence?: unknown } | undefined)?.evidence) as unknown
  return inner && typeof inner === 'object' ? (inner as Record<string, VoucherEvidenceEntry[]>) : {}
}

async function fetchKeys(projectId: string, year: number, keys: string[]): Promise<void> {
  const scope = scopeOf(scopeKey(projectId, year))
  for (let i = 0; i < keys.length; i += VOUCHER_EVIDENCE_MAX_KEYS) {
    const chunk = keys.slice(i, i + VOUCHER_EVIDENCE_MAX_KEYS)
    const mine = ++seq
    for (const k of chunk) scope.latest.set(k, mine)
    let found: Record<string, VoucherEvidenceEntry[]>
    try {
      const res = await http.post(P_ledger.voucherEvidenceQuery(projectId), { year, keys: chunk },
        { _silent: true, _dedupe: false } as any)
      found = unwrapEvidence(res?.data ?? res)
    } catch {
      for (const k of chunk) if (scope.latest.get(k) === mine) scope.latest.delete(k)
      continue
    }
    for (const k of chunk) {
      if (scope.latest.get(k) === mine) scope.data.set(k, Array.isArray(found[k]) ? found[k] : [])
    }
    version.value += 1
  }
}

function schedule(projectId: string, year: number): void {
  const scope = scopeOf(scopeKey(projectId, year))
  if (scope.scheduled) return
  scope.scheduled = true
  // 同一轮渲染里各行登记完再一起发（微任务在本轮同步渲染之后执行）
  queueMicrotask(() => {
    scope.scheduled = false
    const keys = [...scope.pending]
    scope.pending.clear()
    if (keys.length) void fetchKeys(projectId, year, keys)
  })
}

/** 登记一个要查的键（已查过 / 在查的跳过）。 */
export function requestVoucherEvidence(projectId: string, year: number | null | undefined, voucherKey: string): void {
  if (!projectId || year == null || !voucherKey) return
  const scope = scopeOf(scopeKey(projectId, year))
  if (scope.data.has(voucherKey) || scope.latest.has(voucherKey) || scope.pending.has(voucherKey)) return
  scope.pending.add(voucherKey)
  schedule(projectId, year)
}

/** 引用 / 上传之后重查这几个键（不论缓存）。 */
export async function refreshVoucherEvidence(
  projectId: string, year: number | null | undefined, keys: ReadonlyArray<string | null | undefined>,
): Promise<void> {
  const todo = [...new Set(keys.filter((k): k is string => !!k))]
  if (!projectId || year == null || !todo.length) return
  await fetchKeys(projectId, year, todo)
}

/** 读缓存（响应式：在 computed / 模板里调用会随查询结果更新）；没查过的键先登记查询。 */
export function voucherEvidenceOf(
  projectId: string, year: number | null | undefined, voucherKey: string | null | undefined,
): VoucherEvidenceEntry[] {
  void version.value
  if (!projectId || year == null || !voucherKey) return []
  requestVoucherEvidence(projectId, year, voucherKey)
  return scopes.get(scopeKey(projectId, year))?.data.get(voucherKey) ?? []
}

/** 测试用：清空缓存。 */
export function resetVoucherEvidenceIndexForTest(): void {
  scopes.clear()
  seq = 0
  version.value += 1
}

/** 某行凭证在各可见底稿的证据（含本底稿；调用方按需排除）。 */
export function useVoucherEvidenceIndex(
  projectId: MaybeRefOrGetter<string>,
  year: MaybeRefOrGetter<number | null | undefined>,
  voucherKey: MaybeRefOrGetter<string | null | undefined>,
) {
  watch(
    () => [toValue(projectId), toValue(year), toValue(voucherKey)] as const,
    ([pid, yr, vk]) => {
      if (pid && vk && yr != null) requestVoucherEvidence(pid, yr, vk)
    },
    { immediate: true },
  )
  const entries = computed<VoucherEvidenceEntry[]>(() => {
    void version.value
    const pid = toValue(projectId)
    const yr = toValue(year)
    const vk = toValue(voucherKey)
    if (!pid || yr == null || !vk) return []
    return scopes.get(scopeKey(pid, yr))?.data.get(vk) ?? []
  })
  return { entries }
}
