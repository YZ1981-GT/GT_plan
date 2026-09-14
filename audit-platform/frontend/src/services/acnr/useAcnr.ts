/**
 * useAcnr — ACNR 前端 SDK composable
 *
 * 提供:
 * - listSheets(cycle?, importExportOnly?) — 调 /api/acnr/entries 构建下拉树
 * - listCells(wpCode, sheet) — 调 /api/acnr/anchors 获取坐标锚点
 * - resolve(params) — 统一 resolve 入口（index_ref / uri / formula_ref / addr_id）
 * - resolveFormula(formulaRef) — 保存前 resolve 校验（R14.2: 非法引用编译期失败）
 * - resolveUri(uri) — URI 解析
 * - resolveAddr(addrId) — addr_id 解析
 * - resolveIndex(indexRef) — 索引 ns:target 解析
 * - resolveInstance(projectId|params, ...) — wp_id 解析
 * - subscribeInvalidation(projectId) — 项目级 SSE 实时失效订阅（acnr-invalidation-overlay-hardening R1）
 *
 * 与 useAddressRegistry 的区别：
 *   useAddressRegistry 是旧 V1 运行时目录（动态 build），面向五域全搜索。
 *   useAcnr 是新 ACNR 统一出口（L1 静态 catalog），面向 catalog 树 + resolve。
 *   消费者应逐步迁移至 useAcnr（M2 消费者切换）。
 *
 * Requirements: 14.1, 14.2, 15.3；acnr-invalidation-overlay-hardening R1/R4
 */
import { ref, shallowRef, onUnmounted } from 'vue'
import http from '@/utils/http'
import {
  subscribeProjectEvent,
  isProjectStreamDegraded,
  type ProjectEventSubscription,
} from '@/services/sse/projectEventStream'
import { isValidUri, isValidIndexRef } from './resolveUri'
import { composeSheetLabelsForGroup } from './sheetDisplayName'

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
  /** 科目简称（取父底稿，如 D2→应收账款）— 后端从 wp_account_mapping 补充 */
  account_name?: string
  /** 规范底稿名（取本 sheet_code，如 D2-1→应收账款审定表）— 后端从 wp_account_mapping 补充 */
  mapped_sheet_name?: string
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
  overlay: '/api/acnr/overlay',
} as const

/** 项目级 overlay 条目（GET/POST /api/acnr/overlay） */
export interface AcnrOverlay {
  project_id: string
  addr_id: string
  overlay_type: string
  overrides: Record<string, unknown>
  reason?: string
  owner?: string
  expires_at?: string | null
  wp_id?: string | null
  revision: number
}

/** overlay 写入参数 */
export interface AcnrOverlayApply {
  project_id: string
  addr_id: string
  overrides: Record<string, unknown>
  overlay_type?: string
  reason?: string
  owner?: string
  expires_at?: string | null
  wp_id?: string | null
  /** 乐观并发：提供则 CAS，冲突返回 409（并发编辑防覆盖） */
  expected_revision?: number
}

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
 *
 * TTL 兜底 (Req-15.1 / Req-20)：命中后先判断是否超过 MAX_AGE。
 * 过期条目直接删除并视为 miss，避免 SSE 降级为 TTL-only 或漏收失效
 * 消息时长期返回陈旧 resolve 结果。
 */
function _resolveCacheGet(key: string): AcnrResolveResult | undefined {
  const entry = _resolveCache.get(key)
  if (!entry) return undefined
  // TTL 过期检查：超时条目删除并返回 miss（触发重新请求）
  if (Date.now() - entry.timestamp > MAX_AGE) {
    _resolveCache.delete(key)
    return undefined
  }
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

// ─── 项目级 SSE 订阅（acnr-invalidation-overlay-hardening R1 + 连接去重）──────
// 迁移到项目事件流单例总线（frontend-sse-connection-consolidation）：订阅共享连接的
// `acnr:invalidate` 事件，不再自建 SSE 连接（每项目仅一条共享连接，token 经 Authorization
// header 不入 URL）。断线重连 / 退避 / 降级由总线（createSSE）统一负责；本层做 acnr:invalidate
// 精细失效 + 重连后清项目缓存（onReconnect hook）+ 降级观测（isProjectStreamDegraded）。

/** useAcnr 侧 acnr:invalidate 订阅句柄（每 projectId 一个，引用计数复用总线连接，R1.4） */
interface _AcnrSub {
  sub: ProjectEventSubscription
  refCount: number
}
const _acnrSubByProject = new Map<string, _AcnrSub>()

/** 已知 catalog 版本（用于判断 acnr:invalidate 是否需全局目录失效，R4.2） */
let _knownCatalogVersion: string | null = null

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
 * 清除属于指定项目的 resolve 缓存条目（项目隔离失效，R4.1）。
 * Resolve_Cache key 形如 `resolve:{"index_ref":...,"project_id":"<uuid>"}`。
 */
function _clearResolveCacheForProject(projectId: string): void {
  if (!projectId) return
  const needle = `"project_id":"${projectId}"`
  for (const key of Array.from(_resolveCache.keys())) {
    if (key.includes(needle)) {
      _resolveCache.delete(key)
    }
  }
}

/**
 * 查询项目 SSE 是否已降级为 TTL-only 模式。
 * 传 projectId → 该项目状态；不传 → 存在任一降级连接则 true。
 */
export function isSSEDegraded(projectId?: string): boolean {
  if (projectId) return isProjectStreamDegraded(projectId)
  for (const pid of _acnrSubByProject.keys()) {
    if (isProjectStreamDegraded(pid)) return true
  }
  return false
}

/**
 * acnr:invalidate 精细失效（R4）：
 * - 携带变化的 catalog_version → 全局目录缓存失效 + epoch 递增（R4.2）
 * - 仅 project_id → 只清该项目 resolve 缓存（R4.3，避免过度失效）
 */
function _onAcnrInvalidate(projectId: string, payload: Record<string, unknown>): void {
  const cv = payload?.catalog_version as string | undefined
  if (cv && cv !== _knownCatalogVersion) {
    _knownCatalogVersion = cv
    invalidateModuleCache()
    return
  }
  _clearResolveCacheForProject(projectId)
}

/** 处理来自总线的 acnr:invalidate 事件负载（createSSE 已 JSON.parse；字符串兜底解析）。 */
function _handleAcnrInvalidate(projectId: string, data: unknown): void {
  let payload: Record<string, unknown> = {}
  if (data && typeof data === 'object') {
    payload = data as Record<string, unknown>
  } else if (typeof data === 'string') {
    try {
      payload = JSON.parse(data)
    } catch {
      payload = {}
    }
  }
  _onAcnrInvalidate(projectId, payload)
}

/**
 * 订阅项目失效（R1）。委托项目事件流单例总线订阅 `acnr:invalidate`；按 projectId 引用计数
 * 复用单一共享连接（同项目多次订阅只建一个总线订阅），返回 cleanup。
 * 无 projectId → no-op（R1.3，全局目录浏览不建项目级连接）。
 * onReconnect（断线重连成功）→ 清该项目 resolve 缓存（R4.5）。
 */
export function subscribeInvalidation(projectId: string): () => void {
  if (!projectId) return () => {}
  let entry = _acnrSubByProject.get(projectId)
  if (!entry) {
    const sub = subscribeProjectEvent(
      projectId,
      'acnr:invalidate',
      (data) => _handleAcnrInvalidate(projectId, data),
      { onReconnect: () => _clearResolveCacheForProject(projectId) },
    )
    entry = { sub, refCount: 0 }
    _acnrSubByProject.set(projectId, entry)
  }
  entry.refCount++
  return () => {
    const e = _acnrSubByProject.get(projectId)
    if (!e) return
    e.refCount--
    if (e.refCount <= 0) {
      e.sub.close()
      _acnrSubByProject.delete(projectId)
    }
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAcnr(projectId?: string) {
  // 使用模块级缓存引用（所有实例共享）
  const sheetsCache = _sheetsCache
  const cellsCache = _cellsCache

  // R1: 有项目上下文时订阅项目级 SSE 实时失效（引用计数复用）；
  // 无 projectId → 不建连接，仅靠 TTL_Fallback（R1.3）。
  if (projectId) {
    const _cleanupSSE = subscribeInvalidation(projectId)
    onUnmounted(() => {
      _cleanupSSE()
    })
  }

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
   * @param projectId - 可选项目 UUID（触发 L2/L3）
   */
  async function resolveIndex(indexRef: string, projectIdArg?: string): Promise<AcnrResolveResult> {
    if (!indexRef || !isValidIndexRef(indexRef)) {
      return { found: false, error: 'invalid_index_ref' }
    }
    const pid = projectIdArg ?? projectId
    // Req-20: resolve 缓存
    const cacheKey = `resolve:${JSON.stringify({ index_ref: indexRef, project_id: pid })}`
    const cached = _resolveCacheGet(cacheKey)
    if (cached) return cached

    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: {
          index_ref: indexRef,
          ...(pid ? { project_id: pid } : {}),
        },
        _silent: true,
      } as any)
      const result = data as AcnrResolveResult
      _resolveCacheSet(cacheKey, result)
      return result
    } catch {
      return { found: false, error: 'resolve_failed' }
    }
  }

  /**
   * 统一 resolve 入口（GtIndexChip / 公式选址器对象参数形态）
   */
  async function resolve(params: {
    index_ref?: string
    uri?: string
    formula_ref?: string
    addr_id?: string
    project_id?: string
  }): Promise<AcnrResolveResult> {
    if (params.index_ref) return resolveIndex(params.index_ref, params.project_id)
    if (params.uri) return resolveUri(params.uri)
    if (params.formula_ref) return resolveFormula(params.formula_ref)
    if (params.addr_id) return resolveAddr(params.addr_id)
    return { found: false, error: 'empty_resolve_params' }
  }

  type ResolveInstanceParams = {
    project_id: string
    parent: string
    sheet_code: string
    wp_id?: string
  }

  /**
   * 项目实例解析 — 唯一 wp_id 出口（R6, R13.1）
   * 兼容位置参数与 GtIndexChip 对象参数两种调用形态。
   */
  async function resolveInstance(
    projectIdOrParams: string | ResolveInstanceParams,
    parent?: string,
    sheetCode?: string,
    wpId?: string,
  ): Promise<AcnrInstanceResult> {
    const pid = typeof projectIdOrParams === 'string'
      ? projectIdOrParams
      : projectIdOrParams.project_id
    const parentCode = typeof projectIdOrParams === 'string'
      ? parent
      : projectIdOrParams.parent
    const sheet = typeof projectIdOrParams === 'string'
      ? sheetCode
      : projectIdOrParams.sheet_code
    const instanceWpId = typeof projectIdOrParams === 'string'
      ? wpId
      : projectIdOrParams.wp_id

    if (!pid || !parentCode || !sheet) {
      return { found: false, error: 'missing_params' }
    }
    try {
      const { data } = await http.get(ACNR_PATHS.resolveInstance, {
        params: {
          project_id: pid,
          parent: parentCode,
          sheet_code: sheet,
          ...(instanceWpId ? { wp_id: instanceWpId } : {}),
        },
        _silent: true,
      } as any)
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
   * @param projectIdArg - 可选项目 UUID（触发 L2/L3）
   */
  async function batchResolve(
    inputs: Array<{ uri?: string; formula_ref?: string; addr_id?: string; index_ref?: string }>,
    projectIdArg?: string,
  ): Promise<AcnrResolveResult[]> {
    if (!inputs || inputs.length === 0) return []
    const pid = projectIdArg ?? projectId
    try {
      const { data } = await http.post(ACNR_PATHS.resolveBatch, {
        items: inputs,
        ...(pid ? { project_id: pid } : {}),
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

    // 构建树（显示名走单一真源 composeSheetLabelsForGroup，与公式管理树一致）
    const tree: AcnrTreeNode[] = []
    for (const [parentCode, sheetsInGroup] of groups) {
      const subjectAbbr = sheetsInGroup.find((s) => s.account_name)?.account_name || ''
      const parentNode: AcnrTreeNode = {
        // 父节点带科目简称（如「D2 应收账款」），value 仍用 parentCode 不变
        label: subjectAbbr ? `${parentCode} ${subjectAbbr}` : parentCode,
        value: parentCode,
        type: 'sheet',
        addrId: parentCode,
        children: composeSheetLabelsForGroup(sheetsInGroup).map(({ entry, label }) => ({
          label,
          value: entry.addr_id,
          type: 'sheet' as const,
          addrId: entry.addr_id,
          meta: entry,
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

  // ─── Overlay 管理（受控变更入口 UI）──────────────────────────────────────

  /** 列出项目全部 overlay（GET /api/acnr/overlay） */
  async function listOverlays(pid: string): Promise<AcnrOverlay[]> {
    if (!pid) return []
    try {
      const { data } = await http.get(ACNR_PATHS.overlay, { params: { project_id: pid } })
      return Array.isArray(data) ? data : (data?.items ?? [])
    } catch (e) {
      console.warn('[useAcnr] listOverlays 失败', e)
      return []
    }
  }

  /**
   * 创建/更新 overlay（POST /api/acnr/overlay）。
   * 传 expected_revision 启用 CAS：并发编辑冲突时后端返回 409（抛错，调用方重新拉取重试）。
   */
  async function applyOverlay(payload: AcnrOverlayApply): Promise<AcnrOverlay> {
    const { data } = await http.post(ACNR_PATHS.overlay, payload)
    return data as AcnrOverlay
  }

  /** 删除 overlay（DELETE /api/acnr/overlay） */
  async function removeOverlay(
    pid: string,
    addrId: string,
    overlayType = 'cust',
  ): Promise<boolean> {
    const { data } = await http.delete(ACNR_PATHS.overlay, {
      data: { project_id: pid, addr_id: addrId, overlay_type: overlayType },
    })
    return !!(data?.deleted)
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
    resolve,
    resolveFormula,
    resolveUri,
    resolveAddr,
    resolveIndex,
    resolveInstance,
    batchResolve,
    // 树构建
    buildAddressTree,
    loadCellNodes,
    // Overlay 管理（受控变更入口 UI）
    listOverlays,
    applyOverlay,
    removeOverlay,
    // 缓存管理
    clearCache,
    getEpoch,
    // SSE 订阅（R1）
    subscribeInvalidation,
  }
}
