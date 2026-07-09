/**
 * useLedgerCache — 项目级序时账分录缓存
 *
 * 核心思想：全量分录拉取一次后缓存在内存，同项目同年度内所有底稿复用。
 * C24/截止测试等需要全量分录的底稿不再每次独立拉取。
 *
 * 缓存策略：
 * - key = `${projectId}:${year}`
 * - 项目切换/年度切换 → 自动清空
 * - 用户手动刷新 → invalidate 后重拉
 * - 浏览器 tab 后台超过 30 分钟 → 标记 stale（下次使用时可选重拉）
 *
 * 使用方式：
 * ```ts
 * const cache = useLedgerCache()
 * const entries = await cache.getEntries(projectId, year)  // 缓存命中直接返回
 * cache.invalidate()  // 强制下次重拉
 * ```
 */
import { ref, readonly } from 'vue'
import { api } from '@/services/apiProxy'

export interface LedgerCacheEntry {
  voucherDate: string
  voucherNo: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  summary: string
  preparer: string
  [key: string]: unknown
}

interface CacheState {
  key: string           // `${projectId}:${year}`
  entries: LedgerCacheEntry[]
  total: number
  fetchedAt: number     // Date.now()
  complete: boolean     // 是否拉取完整（非中断）
}

const PAGE_SIZE = 5000
const STALE_MS = 30 * 60 * 1000  // 30 分钟后标记为 stale

// ─── 模块级单例（跨组件共享） ───
let _cache: CacheState | null = null
const _loading = ref(false)
const _progress = ref('')  // '12,000 / 348,000'
const _error = ref('')

type ProgressCallback = (loaded: number, total: number) => void

/**
 * 获取缓存分录（命中直接返回，未命中则拉取并缓存）
 */
async function getEntries(
  projectId: string,
  year: number,
  opts?: { force?: boolean; onProgress?: ProgressCallback; signal?: AbortSignal },
): Promise<LedgerCacheEntry[]> {
  const key = `${projectId}:${year}`
  const force = opts?.force ?? false

  // 缓存命中且未过期
  if (!force && _cache && _cache.key === key && _cache.complete) {
    const age = Date.now() - _cache.fetchedAt
    if (age < STALE_MS) {
      return _cache.entries
    }
    // stale 但仍有数据 → 先返回旧数据（调用方可选择后台刷新）
    return _cache.entries
  }

  // 正在加载中 → 等待完成
  if (_loading.value && _cache?.key === key) {
    return new Promise((resolve) => {
      const check = setInterval(() => {
        if (!_loading.value) {
          clearInterval(check)
          resolve(_cache?.entries ?? [])
        }
      }, 200)
    })
  }

  // 拉取
  return await _fetchAll(projectId, year, key, opts?.onProgress, opts?.signal)
}

async function _fetchAll(
  projectId: string,
  year: number,
  key: string,
  onProgress?: ProgressCallback,
  signal?: AbortSignal,
): Promise<LedgerCacheEntry[]> {
  _loading.value = true
  _error.value = ''
  _progress.value = '正在加载...'

  const allEntries: LedgerCacheEntry[] = []
  let page = 1
  let total = 0

  try {
    while (true) {
      if (signal?.aborted) {
        throw new Error('用户取消')
      }

      const res = await api.get<any>(`/api/projects/${projectId}/ledger/entries-all`, {
        params: { year, page, page_size: PAGE_SIZE },
        timeout: 300000,
        _silent: true,
      } as any)

      const items: any[] = res?.items ?? res?.data?.items ?? []
      const reportedTotal = Number(res?.total ?? res?.data?.total ?? 0)
      if (reportedTotal > 0) total = reportedTotal

      for (const r of items) {
        allEntries.push({
          voucherDate: r.voucher_date || r.voucherDate || '',
          voucherNo: r.voucher_no || r.voucherNo || '',
          accountCode: r.account_code || r.accountCode || '',
          accountName: r.account_name || r.accountName || '',
          debitAmount: Number(r.debit_amount ?? r.debitAmount ?? r.debit ?? 0),
          creditAmount: Number(r.credit_amount ?? r.creditAmount ?? r.credit ?? 0),
          summary: r.summary || '',
          preparer: r.preparer || '',
        })
      }

      // 进度回调
      _progress.value = total > 0
        ? `${allEntries.length.toLocaleString()} / ${total.toLocaleString()}`
        : `${allEntries.length.toLocaleString()} 条`
      onProgress?.(allEntries.length, total)

      const reachedEnd = items.length < PAGE_SIZE || (total > 0 && allEntries.length >= total)
      if (reachedEnd) break
      page++
    }

    // 写入缓存
    _cache = {
      key,
      entries: allEntries,
      total: total || allEntries.length,
      fetchedAt: Date.now(),
      complete: true,
    }
    _progress.value = `${allEntries.length.toLocaleString()} 条（已缓存）`
    return allEntries
  } catch (err: any) {
    _error.value = err?.message || '加载失败'
    // 即使中途失败，已拉到的数据也缓存（标记不完整）
    if (allEntries.length > 0) {
      _cache = {
        key,
        entries: allEntries,
        total: total || allEntries.length,
        fetchedAt: Date.now(),
        complete: false,
      }
    }
    throw err
  } finally {
    _loading.value = false
  }
}

/**
 * 使缓存失效（下次 getEntries 会重新拉取）
 */
function invalidate(): void {
  _cache = null
  _progress.value = ''
  _error.value = ''
}

/**
 * 获取缓存状态（不触发加载）
 */
function getCacheInfo(): { cached: boolean; count: number; complete: boolean; age: number } | null {
  if (!_cache) return null
  return {
    cached: true,
    count: _cache.entries.length,
    complete: _cache.complete,
    age: Date.now() - _cache.fetchedAt,
  }
}

/**
 * 检查指定 project+year 是否有缓存
 */
function hasCacheFor(projectId: string, year: number): boolean {
  return _cache?.key === `${projectId}:${year}` && _cache.entries.length > 0
}

// ─── 监听项目切换事件 → 自动清缓存 ───
// 由调用方在 onMounted 时注册（避免 import 时立即执行 eventBus 依赖）
function setupAutoInvalidate(eventBus: { on: (event: string, cb: () => void) => void }): void {
  eventBus.on('project:reset', invalidate)
}

/**
 * Composable 入口
 */
export function useLedgerCache() {
  return {
    getEntries,
    invalidate,
    getCacheInfo,
    hasCacheFor,
    setupAutoInvalidate,
    loading: readonly(_loading),
    progress: readonly(_progress),
    error: readonly(_error),
  }
}
