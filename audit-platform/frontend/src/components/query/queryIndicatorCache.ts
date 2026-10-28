/**
 * queryIndicatorCache.ts — 指标树的 sessionStorage 缓存（advanced-query-linkage-closure 任务 27，design §4.1；ADR-AQL-16；R10.4）
 *
 * 弹窗与页面版共用（接线在任务 28 / 29）。键 = `gt:custom-query:indicators:{schema}:{项目}:{年度}:{附注版本}`：
 * - schema = 响应头 `X-Indicators-Schema-Version`（树形改了后端升版，旧缓存自然不命中）；
 * - 附注版本 = 响应头 `X-Notes-Version`（附注行数、最近更新时间与循环范围的摘要，任务 19 下发）：同一会话里附注重新
 *   生成 / 对齐、或切换年度后，旧缓存不再命中（改造前键只有 schema 与项目，附注改了照样读旧树）。
 * 写入时顺手清掉过期条目：schema 不同的、同一项目同一年度但附注版本不同的、以及改造前的旧格式键。
 */
import { isKnownYear } from '@/components/custom-query/queryPayloads'

export const INDICATOR_CACHE_PREFIX = 'gt:custom-query:indicators:'

export interface IndicatorCacheKeyParts {
  schema?: string | number | null
  projectId?: string | null
  year?: number | null
  notesVersion?: string | null
}

function seg(v: unknown, empty: string): string {
  const s = v === undefined || v === null ? '' : String(v).trim()
  // 键用「:」分段：段内不得含「:」（项目 id、年度、摘要都不含；防御异常输入）
  return s ? s.replace(/:/g, '_') : empty
}

/** 缓存键（四段缺省分别为 unknown / no-project / no-year / none） */
export function indicatorCacheKey(parts: IndicatorCacheKeyParts): string {
  const year = isKnownYear(parts.year) ? String(parts.year) : 'no-year'
  return `${INDICATOR_CACHE_PREFIX}${seg(parts.schema, 'unknown')}:${seg(parts.projectId, 'no-project')}:${year}:${seg(parts.notesVersion, 'none')}`
}

function storageOf(storage?: Storage): Storage | null {
  try {
    return storage ?? globalThis.sessionStorage ?? null
  } catch {
    return null
  }
}

/** 读缓存；没有或损坏返回 null（损坏的条目顺手删掉） */
export function readIndicatorCache<T = unknown>(key: string, storage?: Storage): T | null {
  const s = storageOf(storage)
  const raw = s?.getItem(key)
  if (!s || !raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    s.removeItem(key)
    return null
  }
}

/** 清掉过期条目，返回清掉的个数：schema 不同的、同一项目同一年度附注版本不同的、旧格式（段数不对）的 */
export function purgeStaleIndicatorCache(currentKey: string, storage?: Storage): number {
  const s = storageOf(storage)
  if (!s || !currentKey.startsWith(INDICATOR_CACHE_PREFIX)) return 0
  const [schema, pid, year] = currentKey.slice(INDICATOR_CACHE_PREFIX.length).split(':')
  const stale: string[] = []
  for (let i = 0; i < s.length; i += 1) {
    const k = s.key(i)
    if (!k || k === currentKey || !k.startsWith(INDICATOR_CACHE_PREFIX)) continue
    const parts = k.slice(INDICATOR_CACHE_PREFIX.length).split(':')
    if (parts.length !== 4 || parts[0] !== schema || (parts[1] === pid && parts[2] === year)) stale.push(k)
  }
  stale.forEach((k) => s.removeItem(k))
  return stale.length
}

/** 写缓存并清掉过期条目（配额不足等写入失败忽略：缓存只是加速） */
export function writeIndicatorCache(key: string, tree: unknown, storage?: Storage): void {
  const s = storageOf(storage)
  if (!s) return
  purgeStaleIndicatorCache(key, s)
  try {
    s.setItem(key, JSON.stringify(tree))
  } catch { /* ignore */ }
}
