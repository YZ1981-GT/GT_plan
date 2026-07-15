/**
 * useAcnr — ACNR 前端 SDK composable
 *
 * 提供:
 * - listSheets(cycle?, importExportOnly?) — 调 /api/acnr/entries 构建下拉树
 * - listCells(wpCode, sheet) — 调 /api/acnr/anchors 获取坐标锚点
 * - resolveFormula(formulaRef) — 保存前 resolve 校验（R14.2: 非法引用编译期失败）
 * - resolveUri(uri) — URI 解析
 * - resolveAddr(addrId) — addr_id 解析
 * - resolveIndex(indexRef) — 索引 ns:target 解析
 * - resolveInstance(projectId, parent, sheetCode) — wp_id 解析
 *
 * 与 useAddressRegistry 的区别：
 *   useAddressRegistry 是旧 V1 运行时目录（动态 build），面向五域全搜索。
 *   useAcnr 是新 ACNR 统一出口（L1 静态 catalog），面向 catalog 树 + resolve。
 *   消费者应逐步迁移至 useAcnr（M2 消费者切换）。
 *
 * Requirements: 14.1, 14.2, 15.3
 */
import { ref, shallowRef, onUnmounted } from 'vue'
import http from '@/utils/http'
import { isValidUri, isValidIndexRef } from './resolveUri'

// ─── Types ────────────────────────────────────────────────────────────────────

/** Sheet 目录条目（list_sheets 返回） */
export interface AcnrSheetEntry {
  addr_id: string
  domain: string
  cycle: string
  parent_wp_code: string
  sheet_code: string
  sheet_name: string
  sheet_name_aliases?: string[]
  component_type?: string
  class_code?: string
  functional_type?: string
  display_label?: string
  import_export?: {
    enabled: boolean
    api_prefix?: string
    item_id?: string
    storage_field?: string
    import_order?: number
    depends_on_sheets?: string[]
  }
  skip_reason?: string | null
}

/** Cell 坐标条目（list_cells 返回） */
export interface AcnrCellEntry {
  addr_id: string
  parent_addr_id: string
  domain: string
  cell_address?: string | null
  semantic_label?: string | null
  semantic_only?: boolean
  purpose?: string
  formula_ref: string
  uri?: string
  deprecated?: boolean
}

/** Resolve 结果 */
export interface AcnrResolveResult {
  found: boolean
  addr_id?: string
  entry_type?: 'sheet' | 'cell' | 'runtime'
  cell_address?: string
  semantic_label?: string
  formula_ref?: string
  uri?: string
  jump_route?: string
  wp_id?: string
  // miss/ambiguous
  error?: string
  candidates?: Array<{
    addr_id: string
    display_label: string
    score?: number
  }>
}

/** resolve_instance 结果 */
export interface AcnrInstanceResult {
  found: boolean
  wp_id?: string
  wp_index_id?: string
  jump_route?: string
  parent_wp_code?: string
  sheet_code?: string
  error?: string
  candidates?: Array<Record<string, unknown>>
}

/** 公式选址树节点（前端构建） */
export interface AcnrTreeNode {
  label: string
  value: string
  /** sheet 或 cell */
  type: 'sheet' | 'cell'
  /** addr_id */
  addrId: string
  children?: AcnrTreeNode[]
  /** 额外元数据 */
  meta?: AcnrSheetEntry | AcnrCellEntry
}

// ─── API Paths ────────────────────────────────────────────────────────────────

const ACNR_PATHS = {
  entries: '/api/acnr/entries',
  anchors: '/api/acnr/anchors',
  resolve: '/api/acnr/resolve',
  resolveBatch: '/api/acnr/resolve-batch',
  resolveInstance: '/api/acnr/resolve-instance',
  lookup: '/api/acnr/lookup',
} as const

// ─── Module-level Cache (singleton across all useAcnr() instances) ────────────

/** 缓存 TTL 兜底：300 秒 / 5 分钟 (Req-15.1) */
export const MAX_AGE = 300_000

/** 带时间戳的缓存条目（TTL 过期判断用） */
interface CacheEntry<T> {
  data: T
  timestamp: number
}

/** 模块级缓存：所有 useAcnr() 实例共享同一份数据 */
const _sheetsCache = new Map<string, CacheEntry<AcnrSheetEntry[]>>()
const _cellsCache = new Map<string, CacheEntry<AcnrCellEntry[]>>()

/**
 * 判断缓存条目是否已过期 (TTL 兜底，Req-15.1)
 */
function _isExpired<T>(entry: CacheEntry<T>): boolean {
  return Date.now() - entry.timestamp > MAX_AGE
}

/** Resolve 结果 LRU 缓存 (Req-20) */
export const MAX_RESOLVE_CACHE_SIZE = 200

interface _ResolveCacheEntry {
  result: AcnrResolveResult
  timestamp: number
}

/**
 * _resolveCache: key = `resolve:${JSON.stringify(params)}`, value = { result, timestamp }
 * Map 的插入顺序即为 LRU 顺序（最近访问的移到最后）
 */
const _resolveCache = new Map<string, _ResolveCacheEntry>()

/**
 * LRU 缓存读取：命中时将条目移到 Map 尾部（最新位置）
 */
function _resolveCacheGet(key: string): AcnrResolveResult | undefined {
  const entry = _resolveCache.get(key)
  if (!entry) return undefined
  // 移到尾部（LRU: 最近使用排最后）
  _resolveCache.delete(key)
  _resolveCache.set(key, entry)
  return entry.result
}

/**
 * LRU 缓存写入：超过 MAX_RESOLVE_CACHE_SIZE 时删除最旧条目（Map 头部）
 * found=false 的结果不缓存 (Req-20.4)
 */
function _resolveCacheSet(key: string, result: AcnrResolveResult): void {
  if (!result.found) return

  // 如果已存在，先删除再重新插入（保证移到尾部）
  if (_resolveCache.has(key)) {
    _resolveCache.delete(key)
  }

  _resolveCache.set(key, { result, timestamp: Date.now() })

  // LRU 淘汰：超出 MAX 时删除最旧（Map 迭代顺序 = 插入顺序，头部最旧）
  while (_resolveCache.size > MAX_RESOLVE_CACHE_SIZE) {
    const firstKey = _resolveCache.keys().next().value
    if (firstKey !== undefined) {
      _resolveCache.delete(firstKey)
    } else {
      break
    }
  }
}

/** 缓存纪元：每次失效递增，用于判断缓存是否已过期 */
let _cacheEpoch = 0

/** SSE 连接（模块单例，仅建立一次） */
let _sseConnection: EventSource | null = null
let _sseListenerCount = 0

/** SSE 重连状态 */
let _sseReconnectTimer: ReturnType<typeof setTimeout> | null = null
let _sseReconnectAttempts = 0
const _SSE_MAX_RECONNECT_ATTEMPTS = 5
const _SSE_BACKOFF_SCHEDULE = [5000, 10000, 20000, 30000] // 5s/10s/20s/30s max
let _sseDegradedToTTL = false

/**
 * 获取当前缓存纪元（用于外部判断缓存新旧）
 */
export function getCacheEpoch(): number {
  return _cacheEpoch
}

/**
 * 强制失效模块缓存（递增 epoch + 清空）。
 * 可由 SSE 通知或手动调用触发。
 */
export function invalidateModuleCache(): void {
  _cacheEpoch++
  _sheetsCache.clear()
  _cellsCache.clear()
  _resolveCache.clear()
}

/**
 * 查询当前 SSE 是否已降级为 TTL-only 模式
 */
export function isSSEDegraded(): boolean {
  return _sseDegradedToTTL
}

/**
 * 计算重连延迟（指数退避 5s/10s/20s/30s max）
 */
function _getReconnectDelay(attempt: number): number {
  const idx = Math.min(attempt, _SSE_BACKOFF_SCHEDULE.length - 1)
  return _SSE_BACKOFF_SCHEDULE[idx]
}

/**
 * 建立 SSE 连接并绑定事件处理器。
 * 抽取为独立函数以便重连时复用。
 */
function _createSSEConnection(): void {
  try {
    const sseUrl = '/api/projects/events?topic=acnr:invalidate'
    _sseConnection = new EventSource(sseUrl)

    _sseConnection.addEventListener('acnr:invalidate', () => {
      invalidateModuleCache()
    })

    // 也监听通用 message 事件（部分后端用 event: message）
    _sseConnection.onmessage = (event) => {
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data
        if (data?.type === 'acnr:invalidate' || data?.event === 'acnr:invalidate') {
          invalidateModuleCache()
        }
      } catch {
        // 非 JSON 消息忽略
      }
    }

    // 连接成功打开时重置重连计数
    _sseConnection.onopen = () => {
      if (_sseReconnectAttempts > 0) {
        // 重建成功：断连期间可能错过消息，立即清缓存
        console.warn('[useAcnr] SSE 重连成功，清除缓存以同步断连期间可能遗漏的失效消息')
        invalidateModuleCache()
      }
      _sseReconnectAttempts = 0
    }

    _sseConnection.onerror = () => {
      // 关闭旧连接
      _sseConnection?.close()
      _sseConnection = null

      console.warn('[useAcnr] SSE 连接断开')

      // 如果已降级或无监听者，不重连
      if (_sseDegradedToTTL || _sseListenerCount <= 0) return

      // 启动重建定时器（指数退避）
      _scheduleReconnect()
    }
  } catch {
    // SSE 不可用时降级（不建连接，靠手动 invalidate 或过期机制）
  }
}

/**
 * 安排下次重连尝试
 */
function _scheduleReconnect(): void {
  // 清理旧定时器（防重入）
  if (_sseReconnectTimer !== null) {
    clearTimeout(_sseReconnectTimer)
    _sseReconnectTimer = null
  }

  if (_sseReconnectAttempts >= _SSE_MAX_RECONNECT_ATTEMPTS) {
    // 超过最大重试次数 → 降级为 TTL-only
    _sseDegradedToTTL = true
    console.warn(
      `[useAcnr] SSE 重连失败 ${_SSE_MAX_RECONNECT_ATTEMPTS} 次，降级为 TTL-only 模式（停止重试）`,
    )
    return
  }

  const delay = _getReconnectDelay(_sseReconnectAttempts)
  console.warn(`[useAcnr] SSE 将在 ${delay / 1000}s 后尝试重连 (第 ${_sseReconnectAttempts + 1} 次)`)

  _sseReconnectTimer = setTimeout(() => {
    _sseReconnectTimer = null
    _sseReconnectAttempts++
    _createSSEConnection()
  }, delay)
}

/**
 * 启动 SSE 监听 `acnr:invalidate` 事件。
 * 模块级单例——首次调用建连接，后续调用仅增引用计数。
 * 断连后自动以指数退避重建（5s/10s/20s/30s max，最多 5 次）。
 * 返回 cleanup 函数，所有引用释放后关闭连接。
 */
function _connectSSE(): () => void {
  _sseListenerCount++

  if (!_sseConnection && !_sseDegradedToTTL) {
    _createSSEConnection()
  }

  // 返回 cleanup 函数
  return () => {
    _sseListenerCount--
    if (_sseListenerCount <= 0) {
      _sseListenerCount = 0
      _sseConnection?.close()
      _sseConnection = null
      if (_sseReconnectTimer !== null) {
        clearTimeout(_sseReconnectTimer)
        _sseReconnectTimer = null
      }
    }
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAcnr() {
  // 使用模块级缓存引用（所有实例共享）
  const sheetsCache = _sheetsCache
  const cellsCache = _cellsCache

  // 订阅 SSE 失效通知（composable 生命周期管理）
  const _cleanupSSE = _connectSSE()
  onUnmounted(() => {
    _cleanupSSE()
  })

  // 记录实例创建时的 epoch，用于后续检测缓存是否已被外部失效
  let _localEpoch = _cacheEpoch

  // 响应式状态
  const loading = ref(false)
  const sheets = shallowRef<AcnrSheetEntry[]>([])
  const cells = shallowRef<AcnrCellEntry[]>([])

  /**
   * 列出 sheet 目录条目（R14.1: 公式选址器下拉树数据源）
   * 也用于 R15.3 高级查询「选字段」
   *
   * @param cycle - 循环码过滤（如 'D'），不传返回所有循环
   * @param importExportOnly - 仅返回启用 import_export 的 sheet
   */
  async function listSheets(
    cycle?: string,
    importExportOnly?: boolean,
  ): Promise<AcnrSheetEntry[]> {
    const cacheKey = `${cycle || '_all'}:${importExportOnly ? '1' : '0'}`

    // 如果 epoch 已变（外部失效），本地缓存命中无效
    if (_localEpoch !== _cacheEpoch) {
      _localEpoch = _cacheEpoch
      // 模块缓存已被 invalidateModuleCache 清空，直接跳过命中
    } else if (sheetsCache.has(cacheKey)) {
      const entry = sheetsCache.get(cacheKey)!
      // TTL 兜底：超时后自动失效并重新请求 (Req-15.1)
      if (_isExpired(entry)) {
        sheetsCache.delete(cacheKey)
      } else {
        sheets.value = entry.data
        return entry.data
      }
    }

    loading.value = true
    try {
      const { data } = await http.get(ACNR_PATHS.entries, {
        params: {
          ...(cycle ? { cycle } : {}),
          ...(importExportOnly ? { import_export_only: true } : {}),
        },
      })
      const result: AcnrSheetEntry[] = Array.isArray(data) ? data : (data?.items ?? [])
      sheetsCache.set(cacheKey, { data: result, timestamp: Date.now() })
      sheets.value = result
      return result
    } catch (e) {
      console.warn('[useAcnr] listSheets 失败', e)
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * 列出某 sheet 下的坐标锚点（R14.1: 公式选址器子节点）
   * 也用于 R15.3 高级查询「选字段」
   *
   * @param wpCode - 父底稿码（如 'D2'）
   * @param sheet - sheet_code（如 'D2-2'）
   */
  async function listCells(wpCode: string, sheet: string): Promise<AcnrCellEntry[]> {
    const cacheKey = `${wpCode}/${sheet}`

    // epoch 变化检测
    if (_localEpoch !== _cacheEpoch) {
      _localEpoch = _cacheEpoch
    } else if (cellsCache.has(cacheKey)) {
      const entry = cellsCache.get(cacheKey)!
      // TTL 兜底：超时后自动失效并重新请求 (Req-15.1)
      if (_isExpired(entry)) {
        cellsCache.delete(cacheKey)
      } else {
        cells.value = entry.data
        return entry.data
      }
    }

    loading.value = true
    try {
      const { data } = await http.get(ACNR_PATHS.anchors, {
        params: { wp_code: wpCode, sheet },
      })
      const result: AcnrCellEntry[] = Array.isArray(data) ? data : (data?.items ?? [])
      cellsCache.set(cacheKey, { data: result, timestamp: Date.now() })
      cells.value = result
      return result
    } catch (e) {
      console.warn('[useAcnr] listCells 失败', e)
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * 保存前 resolve 校验（R14.2: 非法引用总是在编译期返回失败）
   *
   * 公式管理库在用户保存 formula_ref 前调用此方法：
   * - found=true → 引用合法，允许保存
   * - found=false → 引用非法，阻止保存并提示用户
   *
   * @param formulaRef - 公式引用，如 WP('D2','明细表D2-2','E100')
   */
  async function resolveFormula(formulaRef: string): Promise<AcnrResolveResult> {
    if (!formulaRef || !formulaRef.trim()) {
      return { found: false, error: 'empty_formula' }
    }
    // Req-20: resolve 缓存 (epoch 变则已由 invalidateModuleCache 清空)
    const cacheKey = `resolve:${JSON.stringify({ formula_ref: formulaRef })}`
    const cached = _resolveCacheGet(cacheKey)
    if (cached) return cached

    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { formula_ref: formulaRef },
      })
      const result = data as AcnrResolveResult
      _resolveCacheSet(cacheKey, result)
      return result
    } catch {
      // 网络错误也视为校验失败（保守策略：非法引用绝不入库）
      return { found: false, error: 'resolve_failed' }
    }
  }

  /**
   * URI 解析
   * @param uri - 五域 URI，如 wp://D2/明细表D2-2#E100
   */
  async function resolveUri(uri: string): Promise<AcnrResolveResult> {
    if (!uri || !isValidUri(uri)) {
      return { found: false, error: 'invalid_uri' }
    }
    // Req-20: resolve 缓存
    const cacheKey = `resolve:${JSON.stringify({ uri })}`
    const cached = _resolveCacheGet(cacheKey)
    if (cached) return cached

    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { uri },
      })
      const result = data as AcnrResolveResult
      _resolveCacheSet(cacheKey, result)
      return result
    } catch {
      return { found: false, error: 'resolve_failed' }
    }
  }

  /**
   * addr_id 解析
   * @param addrId - 如 D2/D2-2/E100
   */
  async function resolveAddr(addrId: string): Promise<AcnrResolveResult> {
    if (!addrId) {
      return { found: false, error: 'empty_addr_id' }
    }
    // Req-20: resolve 缓存
    const cacheKey = `resolve:${JSON.stringify({ addr_id: addrId })}`
    const cached = _resolveCacheGet(cacheKey)
    if (cached) return cached

    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { addr_id: addrId },
      })
      const result = data as AcnrResolveResult
      _resolveCacheSet(cacheKey, result)
      return result
    } catch {
      return { found: false, error: 'resolve_failed' }
    }
  }

  /**
   * 索引 ns:target 解析（R13.3: GtIndexChip 调 resolve 获取 addr_id + jump_route）
   * @param indexRef - 如 cell:D2-2!E100, TB:1001
   */
  async function resolveIndex(indexRef: string): Promise<AcnrResolveResult> {
    if (!indexRef || !isValidIndexRef(indexRef)) {
      return { found: false, error: 'invalid_index_ref' }
    }
    // Req-20: resolve 缓存
    const cacheKey = `resolve:${JSON.stringify({ index_ref: indexRef })}`
    const cached = _resolveCacheGet(cacheKey)
    if (cached) return cached

    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { index_ref: indexRef },
      })
      const result = data as AcnrResolveResult
      _resolveCacheSet(cacheKey, result)
      return result
    } catch {
      return { found: false, error: 'resolve_failed' }
    }
  }

  /**
   * 项目实例解析 — 唯一 wp_id 出口（R6, R13.1）
   *
   * @param projectId - 项目 UUID
   * @param parent - 父底稿码（WP 第一参），如 'D2'
   * @param sheetCode - Tab 编码，如 'D2-2'
   * @param wpId - 可选 wp_id（多实例消歧时传入）
   */
  async function resolveInstance(
    projectId: string,
    parent: string,
    sheetCode: string,
    wpId?: string,
  ): Promise<AcnrInstanceResult> {
    if (!projectId || !parent || !sheetCode) {
      return { found: false, error: 'missing_params' }
    }
    try {
      const { data } = await http.get(ACNR_PATHS.resolveInstance, {
        params: {
          project_id: projectId,
          parent,
          sheet_code: sheetCode,
          ...(wpId ? { wp_id: wpId } : {}),
        },
      })
      return data as AcnrInstanceResult
    } catch {
      return { found: false, error: 'resolve_instance_failed' }
    }
  }

  // ─── 批量 Resolve (Req-15.3) ────────────────────────────────────────────────

  /**
   * 批量解析多个地址（减少公式选址器 20+ 格搜索的 RTT）
   *
   * 单次 HTTP 请求解析多个地址，返回等长结果数组。
   * 后端限制 items ≤ 50。
   *
   * @param inputs - 每项可含 uri / formula_ref / addr_id / index_ref 之一
   * @param projectId - 可选项目 UUID（触发 L2/L3）
   */
  async function batchResolve(
    inputs: Array<{ uri?: string; formula_ref?: string; addr_id?: string; index_ref?: string }>,
    projectId?: string,
  ): Promise<AcnrResolveResult[]> {
    if (!inputs || inputs.length === 0) return []
    try {
      const { data } = await http.post(ACNR_PATHS.resolveBatch, {
        items: inputs,
        ...(projectId ? { project_id: projectId } : {}),
      })
      const results: AcnrResolveResult[] = Array.isArray(data) ? data : (data?.results ?? [])
      return results
    } catch {
      // 网络错误时返回等长失败数组
      return inputs.map(() => ({ found: false, error: 'batch_resolve_failed' }))
    }
  }

  // ─── 下拉树构建辅助 ──────────────────────────────────────────────────────────

  /**
   * 构建公式选址器下拉树（R14.1）
   *
   * 按 domain 分组，每个 sheet 是父节点，可懒加载 cells 子节点。
   * 也用于 R15.3 高级查询「选字段」。
   *
   * @param cycle - 循环过滤
   */
  async function buildAddressTree(cycle?: string): Promise<AcnrTreeNode[]> {
    const sheetList = await listSheets(cycle)

    // 按 parent_wp_code 分组
    const groups = new Map<string, AcnrSheetEntry[]>()
    for (const s of sheetList) {
      const key = s.parent_wp_code
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(s)
    }

    // 构建树
    const tree: AcnrTreeNode[] = []
    for (const [parentCode, sheetsInGroup] of groups) {
      const parentNode: AcnrTreeNode = {
        label: parentCode,
        value: parentCode,
        type: 'sheet',
        addrId: parentCode,
        children: sheetsInGroup.map((s) => ({
          label: s.sheet_name || s.sheet_code,
          value: s.addr_id,
          type: 'sheet' as const,
          addrId: s.addr_id,
          meta: s,
          // cells 子节点按需懒加载
          children: undefined,
        })),
      }
      tree.push(parentNode)
    }

    return tree
  }

  /**
   * 懒加载某 sheet 下的 cell 子节点
   */
  async function loadCellNodes(sheetEntry: AcnrSheetEntry): Promise<AcnrTreeNode[]> {
    const cellList = await listCells(sheetEntry.parent_wp_code, sheetEntry.sheet_code)
    return cellList.map((c) => ({
      label: c.semantic_label || c.cell_address || c.addr_id,
      value: c.addr_id,
      type: 'cell' as const,
      addrId: c.addr_id,
      meta: c,
    }))
  }

  // ─── 缓存管理 ────────────────────────────────────────────────────────────────

  /** 清空缓存（缓存失效时调用），递增 epoch */
  function clearCache() {
    invalidateModuleCache()
    sheets.value = []
    cells.value = []
  }

  /** 获取当前缓存 epoch */
  function getEpoch(): number {
    return _cacheEpoch
  }

  return {
    // 响应式状态
    loading,
    sheets,
    cells,
    // API 方法
    listSheets,
    listCells,
    resolveFormula,
    resolveUri,
    resolveAddr,
    resolveIndex,
    resolveInstance,
    batchResolve,
    // 树构建
    buildAddressTree,
    loadCellNodes,
    // 缓存管理
    clearCache,
    getEpoch,
  }
}
