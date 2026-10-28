/**
 * queryTemplateCache.ts — 查询模板列表的 sessionStorage 缓存（advanced-query-linkage-closure 任务 27，design §4.1）
 *
 * 从 MyTemplatesDialog 的内联缓存挪出（键与 5 分钟有效期不变；对话框改用本模块在任务 33）。比内联版多一处：
 * 缓存记下所属用户，换人登录后不再读到上一个人的列表——模板可见性因人而异，sessionStorage 在同一标签页里跨登录存活
 * （登出只清 token / user）。W3 的「系统预置」列表另用一个键（任务 43），同一组函数。
 */
export const TEMPLATE_LIST_CACHE_KEY = 'gt:cqd:my-templates-cache'
export const TEMPLATE_LIST_CACHE_TTL_MS = 5 * 60 * 1000

interface CacheEnvelope<T> {
  owner: string
  ts: number
  data: T[]
}

export interface TemplateCacheOptions {
  /** 所属用户（当前登录用户 id）；不同用户互不命中 */
  owner: string
  key?: string
  now?: number
  storage?: Storage
}

function storageOf(opts: { storage?: Storage }): Storage | null {
  try {
    return opts.storage ?? globalThis.sessionStorage ?? null
  } catch {
    return null
  }
}

/** 读缓存：过期、损坏、不属于该用户都返回 null（损坏的条目顺手删掉） */
export function readTemplateCache<T>(opts: TemplateCacheOptions): T[] | null {
  const storage = storageOf(opts)
  const key = opts.key ?? TEMPLATE_LIST_CACHE_KEY
  if (!storage) return null
  const raw = storage.getItem(key)
  if (!raw) return null
  try {
    const env = JSON.parse(raw) as Partial<CacheEnvelope<T>>
    if (env.owner !== opts.owner || typeof env.ts !== 'number' || !Array.isArray(env.data)) return null
    return (opts.now ?? Date.now()) - env.ts < TEMPLATE_LIST_CACHE_TTL_MS ? env.data : null
  } catch {
    storage.removeItem(key)
    return null
  }
}

/** 写缓存（配额不足等写入失败忽略：缓存只是加速） */
export function writeTemplateCache<T>(items: readonly T[], opts: TemplateCacheOptions): void {
  const storage = storageOf(opts)
  if (!storage) return
  const env: CacheEnvelope<T> = { owner: opts.owner, ts: opts.now ?? Date.now(), data: [...items] }
  try {
    storage.setItem(opts.key ?? TEMPLATE_LIST_CACHE_KEY, JSON.stringify(env))
  } catch { /* ignore */ }
}

/** 失效（保存 / 删除 / 恢复模板之后调用） */
export function invalidateTemplateCache(opts: { key?: string; storage?: Storage } = {}): void {
  storageOf(opts)?.removeItem(opts.key ?? TEMPLATE_LIST_CACHE_KEY)
}
