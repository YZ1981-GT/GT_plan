/** Bounded Ledger window state: request epoch, cursor history and five-window LRU. */
import { computed, onScopeDispose, ref, shallowRef, type Ref } from 'vue'
import {
  fetchLedgerWindow,
  ledgerWindowQueryKey,
  type LedgerWindowQuery,
  type LedgerWindowResponse,
  type LedgerWindowSummary,
} from '@/services/ledgerWindowApi'

export type LedgerWindowFetcher = (
  query: LedgerWindowQuery,
  signal?: AbortSignal,
) => Promise<LedgerWindowResponse>

interface HistoryItem {
  cursor: string | null
}

function errorCode(error: any): string {
  const data = error?.response?.data
  return String(error?.code || data?.message?.error_code || data?.detail?.error_code || data?.error_code || '')
}

export function useLedgerWindow(fetcher: LedgerWindowFetcher = fetchLedgerWindow) {
  const response = shallowRef<LedgerWindowResponse | null>(null)
  const summary = shallowRef<LedgerWindowSummary | null>(null)
  const extraColumns = ref<string[]>([])
  const loading = ref(false)
  const error = shallowRef<unknown>(null)
  const history = ref<HistoryItem[]>([])
  const position = ref(-1)
  const cacheSize = ref(0)
  const cache = new Map<string, LedgerWindowResponse>()
  let baseQuery: LedgerWindowQuery | null = null
  let baseKey = ''
  let epoch = 0
  let controller: AbortController | null = null

  function cacheKey(cursor: string | null): string {
    return `${baseKey}|${cursor || '<first>'}`
  }

  function putCache(key: string, value: LedgerWindowResponse) {
    cache.delete(key)
    cache.set(key, value)
    while (cache.size > 5) cache.delete(cache.keys().next().value as string)
    cacheSize.value = cache.size
  }

  function accept(value: LedgerWindowResponse) {
    if (summary.value && response.value && value.dataset_id !== response.value.dataset_id) {
      throw Object.assign(new Error('生效数据集已切换，请从第一页重新查询'), {
        code: 'LEDGER_SNAPSHOT_CHANGED',
      })
    }
    response.value = value
    summary.value = value.summary
    if (value.page.page_index === 0 || value.extra_columns.length > 0) {
      extraColumns.value = [...value.extra_columns]
    }
  }

  async function request(cursor: string | null, force = false): Promise<boolean> {
    if (!baseQuery) return false
    const key = cacheKey(cursor)
    const cached = !force ? cache.get(key) : undefined
    if (cached) {
      cache.delete(key)
      cache.set(key, cached)
      accept(cached)
      cacheSize.value = cache.size
      return true
    }
    controller?.abort()
    const own = new AbortController()
    controller = own
    const ownEpoch = ++epoch
    loading.value = true
    error.value = null
    try {
      const value = await fetcher({ ...baseQuery, cursor }, own.signal)
      if (own.signal.aborted || ownEpoch !== epoch) return false
      accept(value)
      putCache(key, value)
      return true
    } catch (cause) {
      if (own.signal.aborted || ownEpoch !== epoch) return false
      error.value = cause
      if (['LEDGER_SNAPSHOT_CHANGED', 'LEDGER_SNAPSHOT_GONE'].includes(errorCode(cause))) {
        cache.clear()
        cacheSize.value = 0
        history.value = []
        position.value = -1
        response.value = null
      }
      throw cause
    } finally {
      if (ownEpoch === epoch) loading.value = false
    }
  }

  async function loadFirst(query: LedgerWindowQuery, force = false): Promise<boolean> {
    const clean = { ...query, cursor: null }
    baseQuery = clean
    baseKey = ledgerWindowQueryKey(clean)
    history.value = [{ cursor: null }]
    position.value = 0
    response.value = null
    summary.value = null
    extraColumns.value = []
    return await request(null, force)
  }

  async function next(): Promise<boolean> {
    const cursor = response.value?.page.next_cursor
    if (!cursor) return false
    const following = history.value[position.value + 1]
    if (!following || following.cursor !== cursor) {
      history.value = [...history.value.slice(0, position.value + 1), { cursor }]
    }
    position.value += 1
    return await request(cursor)
  }

  async function previous(): Promise<boolean> {
    if (position.value <= 0) return false
    position.value -= 1
    return await request(history.value[position.value].cursor)
  }

  async function reload(): Promise<boolean> {
    if (position.value < 0) return false
    return await request(history.value[position.value].cursor, true)
  }

  function clear() {
    controller?.abort()
    controller = null
    epoch += 1
    response.value = null
    summary.value = null
    extraColumns.value = []
    history.value = []
    position.value = -1
    loading.value = false
    error.value = null
  }

  function dispose() {
    clear()
    cache.clear()
    cacheSize.value = 0
  }

  const hasPrevious = computed(() => position.value > 0)
  const hasNext = computed(() => Boolean(response.value?.page.has_more && response.value.page.next_cursor))
  const rangeText = computed(() => {
    const page = response.value?.page
    const total = summary.value?.total ?? 0
    if (!page || page.start === 0) return `共 ${total.toLocaleString()} 条`
    return `第 ${page.start.toLocaleString()}–${page.end.toLocaleString()} 条，共 ${total.toLocaleString()} 条`
  })

  onScopeDispose(dispose)
  return { response, summary, extraColumns, loading, error, position, cacheSize,
    hasPrevious, hasNext, rangeText, loadFirst, next, previous, reload, clear, dispose }
}

export type LedgerWindowState = ReturnType<typeof useLedgerWindow>
