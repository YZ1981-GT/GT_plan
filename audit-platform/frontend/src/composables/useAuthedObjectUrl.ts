/**
 * useAuthedObjectUrl — 给 iframe / img 用的「已鉴权」原件地址
 *
 * 浏览器原生加载（iframe / img 的 src、a 的 href、window.open）不经 axios，带不上
 * Authorization 头；后端 HTTPBearer 一律 401，预览区里显示的是
 * {"code":401,"message":"Not authenticated"}（2026-10-27 附件 OCR 确认弹窗走查实测）。
 * 这里经 api.get 取字节（走全局令牌与刷新链），换成 blob: 地址再交给元素。
 *
 * - 源地址变化 / 置空 / 所在作用域销毁：中止在途请求并释放当前作用域的 blob: 地址
 * - 晚到的旧响应不覆盖新地址
 * - 相同源地址在短时间内共享 Blob 请求，缓存带固定 TTL、LRU 容量上限和显式清理
 * - 预览端点对不可预览类型回 JSON（previewable:false）：按失败处理，不当文件显示
 * - options.type：强制 blob 类型（iframe 显示 PDF 时传 application/pdf，避免浏览器按
 *   octet-stream / 其他类型处理）；不传则沿用响应类型
 *
 * 下载类场景（a 链接 / 新窗口）不用本函数，直接用 utils/http 的 downloadFile。
 */
import { getCurrentScope, onScopeDispose, ref, watch, type WatchSource } from 'vue'
import { api } from '@/services/apiProxy'

export type AuthedObjectUrlState = 'idle' | 'loading' | 'ready' | 'forbidden' | 'not_found' | 'failed'

/** 预览 Blob 只在短时间内复用，避免附件内容更新后长期显示旧字节。 */
export const AUTHED_OBJECT_URL_CACHE_TTL_MS = 60_000
/** 限制同一浏览器上下文的预览 Blob 数，按最近访问顺序淘汰。 */
export const AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES = 32

/** 预览区的失败提示（与状态一一对应，组件直接取用） */
export const AUTHED_OBJECT_URL_FAILURE_TEXT: Record<'forbidden' | 'not_found' | 'failed', string> = {
  forbidden: '无权查看该文件',
  not_found: '文件不存在或已删除',
  failed: '文件加载失败，请稍后重试',
}

export function authedObjectUrlFailureText(state: AuthedObjectUrlState): string {
  return state === 'forbidden' || state === 'not_found' || state === 'failed'
    ? AUTHED_OBJECT_URL_FAILURE_TEXT[state]
    : ''
}

interface CachedBlob {
  blob: Blob
  expiresAt: number
}

interface InflightBlob {
  controller: AbortController
  promise: Promise<Blob>
  subscribers: number
  settled: boolean
  cacheable: boolean
}

const blobCache = new Map<string, CachedBlob>()
const inflight = new Map<string, InflightBlob>()
let cacheEpoch = 0
let cacheCleanupTimer: ReturnType<typeof setTimeout> | null = null

function clearCacheTimer(): void {
  if (cacheCleanupTimer !== null) {
    clearTimeout(cacheCleanupTimer)
    cacheCleanupTimer = null
  }
}

function scheduleCacheCleanup(): void {
  clearCacheTimer()
  if (!blobCache.size) return
  const nextExpiry = Math.min(...Array.from(blobCache.values(), (entry) => entry.expiresAt))
  const delay = Math.max(0, nextExpiry - Date.now())
  cacheCleanupTimer = setTimeout(() => {
    cacheCleanupTimer = null
    purgeExpiredCache()
  }, delay)
  // Node/Vitest timers should not keep a process alive; browsers simply ignore this branch.
  ;(cacheCleanupTimer as any)?.unref?.()
}

function purgeExpiredCache(now = Date.now()): void {
  for (const [key, entry] of blobCache) {
    if (entry.expiresAt <= now) blobCache.delete(key)
  }
  scheduleCacheCleanup()
}

function getCachedBlob(path: string): Blob | null {
  const entry = blobCache.get(path)
  if (!entry) return null
  if (entry.expiresAt <= Date.now()) {
    blobCache.delete(path)
    scheduleCacheCleanup()
    return null
  }
  // Map insertion order is the LRU order. The expiry remains fixed, so frequent use
  // changes recency without allowing a hot item to live forever.
  blobCache.delete(path)
  blobCache.set(path, entry)
  return entry.blob
}

function putCachedBlob(path: string, blob: Blob, epoch: number): void {
  if (epoch !== cacheEpoch || AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES <= 0) return
  blobCache.delete(path)
  blobCache.set(path, {
    blob,
    expiresAt: Date.now() + AUTHED_OBJECT_URL_CACHE_TTL_MS,
  })
  while (blobCache.size > AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES) {
    const oldest = blobCache.keys().next().value as string | undefined
    if (oldest === undefined) break
    blobCache.delete(oldest)
  }
  scheduleCacheCleanup()
}

/**
 * 清除未使用的预览 Blob 缓存。
 *
 * 当前作用域正在显示的 object URL 不由该缓存持有，仍由各自 composable 在
 * 释放时 revoke；在途请求即使属于活跃作用域，也不会在清理后重新写回缓存。
 * 页面切换项目或退出附件/知识库页面时调用，避免旧项目字节跨页面滞留。
 */
export function clearAuthedObjectUrlCache(): void {
  cacheEpoch += 1
  blobCache.clear()
  clearCacheTimer()
  for (const [path, entry] of inflight) {
    entry.cacheable = false
    inflight.delete(path)
    if (entry.subscribers === 0 && !entry.settled) entry.controller.abort()
  }
}

async function fetchPreviewBlob(path: string, signal: AbortSignal): Promise<Blob> {
  const data = await api.get(path, {
    responseType: 'blob',
    _silent: true,
    _dedupe: false,
    signal,
  } as any)
  if (!(data instanceof Blob) || /json/i.test(data.type)) {
    throw new Error('预览响应不是可显示文件')
  }
  return data
}

function getOrStartInflight(path: string): InflightBlob {
  const existing = inflight.get(path)
  if (existing) return existing

  const controller = new AbortController()
  const epoch = cacheEpoch
  const entry: InflightBlob = {
    controller,
    promise: fetchPreviewBlob(path, controller.signal),
    subscribers: 0,
    settled: false,
    cacheable: true,
  }
  inflight.set(path, entry)
  void entry.promise.then(
    (blob) => {
      entry.settled = true
      if (entry.cacheable) putCachedBlob(path, blob, epoch)
      if (inflight.get(path) === entry) inflight.delete(path)
    },
    () => {
      entry.settled = true
      if (inflight.get(path) === entry) inflight.delete(path)
    },
  )
  return entry
}

export function useAuthedObjectUrl(
  source: WatchSource<string | null | undefined>,
  options: { type?: () => string | undefined } = {},
) {
  const url = ref('')
  const state = ref<AuthedObjectUrlState>('idle')
  let requestEntry: InflightBlob | null = null
  let seq = 0

  function detachRequest(): void {
    const entry = requestEntry
    requestEntry = null
    if (!entry) return
    entry.subscribers = Math.max(0, entry.subscribers - 1)
    if (entry.subscribers === 0 && !entry.settled) {
      entry.cacheable = false
      entry.controller.abort()
    }
  }

  function release(): void {
    detachRequest()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
  }

  function setObjectUrl(data: Blob): void {
    const forced = options.type?.()
    const blob = forced && forced !== data.type ? new Blob([data], { type: forced }) : data
    url.value = URL.createObjectURL(blob)
    state.value = 'ready'
  }

  async function load(path: string): Promise<void> {
    const mine = ++seq
    release()
    if (!path) {
      state.value = 'idle'
      return
    }

    const cached = getCachedBlob(path)
    if (cached) {
      state.value = 'loading'
      if (mine !== seq) return
      setObjectUrl(cached)
      return
    }

    const entry = getOrStartInflight(path)
    entry.subscribers += 1
    requestEntry = entry
    state.value = 'loading'
    try {
      const data = await entry.promise
      if (mine !== seq) return
      setObjectUrl(data)
    } catch (e: any) {
      if (mine !== seq) return
      const status = e?.response?.status
      state.value = status === 403 ? 'forbidden' : status === 404 ? 'not_found' : 'failed'
    } finally {
      if (requestEntry === entry) detachRequest()
    }
  }

  watch(source, (path) => { void load(path || '') }, { immediate: true })
  if (getCurrentScope()) {
    onScopeDispose(() => {
      seq++
      release()
    })
  }
  return { url, state }
}
