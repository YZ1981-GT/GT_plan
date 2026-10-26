/**
 * useAddressRegistry — 地址坐标全局注册表 Store [R4.2]
 *
 * 对接后端 GET /api/address-registry 系列 API，
 * 为 CellSelector / FormulaRefPicker / 公式编辑器提供统一数据源。
 *
 * 用法：
 * ```ts
 * const addrStore = useAddressRegistry()
 * await addrStore.refresh(projectId, year)          // 加载全部地址
 * const results = await addrStore.search('货币资金') // 搜索
 * const entry = await addrStore.resolve(uri)         // 解析单个 URI
 * const valid = await addrStore.validate(formula)    // 校验公式引用
 * const route = await addrStore.jump(uri)            // 获取跳转路由
 * ```
 */
import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'
import http from '@/utils/http'
import { addressRegistry as paths } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'
import {
  useAcnr,
  type AcnrSheetEntry,
  type AcnrCellEntry,
  type AcnrResolveResult,
} from '@/services/acnr/useAcnr'

/**
 * 整库加载一次最多取的地址条数 = 后端 `ADDRESS_REGISTRY_MAX_LIMIT`（守卫 backend/tests/test_address_registry_limit.py 比对）。
 * 原取 5000：真实项目里附注 / 底稿 / 辅助余额排在后面的域整段被截掉，选择器里是空的
 * （spec formula-fetch-and-wp-generation-defect-closure R3）。公式编辑弹窗的底稿域直调用同一个数。
 */
export const ADDRESS_REGISTRY_FULL_LOAD_LIMIT = 50000

/** 整条公式就是单个 WP 引用（两参 / 三参）：只有它可以用 ACNR 命中直接判有效（validate） */
export const SINGLE_WP_REF = /^\s*WP\(\s*'[^']*'\s*(?:,\s*'[^']*'\s*){1,2}\)\s*$/

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface AddressEntry {
  uri: string
  domain: string
  source: string
  path: string
  cell: string
  label: string
  formula_ref: string
  jump_route: string
  row_code?: string
  account_code?: string
  note_section?: string
  wp_code?: string
  tags?: string[]
}

export interface ResolveResult {
  found: boolean
  uri: string
  label?: string
  formula_ref?: string
  jump_route?: string
  domain?: string
  tags?: string[]
}

export interface ValidateResult {
  valid: boolean
  /** 与后端 `validate_formula_refs` 同形：原因文案在 `message`，`status` / `reason` 是状态码（`not_found`） */
  issues: Array<{ ref: string; message?: string; uri?: string; status?: string; reason?: string }>
  formula: string
}

export interface JumpResult {
  route: string
  uri: string
  formula_ref: string
}

// ─── ACNR → Store 映射辅助（纯函数，契约不变） ──────────────────────────────
//
// 这些映射把 ACNR SDK 的返回形态（AcnrResolveResult / AcnrSheetEntry /
// AcnrCellEntry）转换成 store 对外暴露的 ResolveResult / AddressEntry 类型，
// 使得内部数据源切到 ACNR 后，公共 return 面（含类型）保持字节级不变。

/** 从 URI（如 `wp://D2/明细表D2-2#E100`）提取 domain 前缀。 */
function _domainFromUri(uri?: string): string | undefined {
  if (!uri) return undefined
  const idx = uri.indexOf('://')
  return idx > 0 ? uri.slice(0, idx) : undefined
}

/** 解析 addr_id `{wp_code}/{sheet_code}/{coord}` 三段。 */
function _parseAddrId(addrId: string): { wpCode: string; sheetCode: string; coord: string } {
  const parts = (addrId || '').split('/')
  return {
    wpCode: parts[0] || '',
    sheetCode: parts[1] || '',
    coord: parts.slice(2).join('/') || '',
  }
}

/** AcnrResolveResult → ResolveResult（R16.1 契约保持）。 */
function _mapAcnrResolveToResult(uri: string, r: AcnrResolveResult): ResolveResult {
  const outUri = r.uri || r.addr_id || uri
  return {
    found: !!r.found,
    uri: outUri,
    label: r.semantic_label,
    formula_ref: r.formula_ref,
    jump_route: r.jump_route,
    domain: _domainFromUri(r.uri) ?? _domainFromUri(uri) ?? (r.addr_id ? 'wp' : undefined),
    tags: undefined,
  }
}

/** AcnrSheetEntry → AddressEntry（R16.3 WP 域 sheet 级）。 */
function _mapSheetToEntry(s: AcnrSheetEntry): AddressEntry {
  return {
    uri: s.addr_id,
    domain: 'wp',
    source: s.parent_wp_code,
    path: s.sheet_code,
    cell: '',
    label: s.sheet_name || s.sheet_code,
    formula_ref: '',
    jump_route: '',
    wp_code: s.parent_wp_code,
    tags: [],
  }
}

/** AcnrCellEntry → AddressEntry（R16.3 WP 域 cell 级）。 */
function _mapCellToEntry(c: AcnrCellEntry): AddressEntry {
  const { wpCode, sheetCode, coord } = _parseAddrId(c.addr_id)
  return {
    uri: c.uri || c.addr_id,
    domain: 'wp',
    source: wpCode,
    path: sheetCode,
    cell: c.cell_address || coord,
    label: c.semantic_label || c.cell_address || c.addr_id,
    formula_ref: c.formula_ref || '',
    jump_route: '',
    wp_code: wpCode,
    tags: [],
  }
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAddressRegistry = defineStore('addressRegistry', () => {
  // ─── 状态 ───
  // 上万条地址只会整体替换、从不改单条 ⇒ shallowRef（ref 会给每条套一层响应式代理）
  const addresses = shallowRef<AddressEntry[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  /** 最近一次整库加载被上限截断、有地址没取回来的域（这些域不当成完整的用，见 isDomainComplete）。 */
  const truncatedDomains = shallowRef<string[]>([])
  /** 当前 addresses 属于哪个（项目, 年度, 口径）。 */
  const _loadedKey = ref('')
  /** 在途的整库加载（同一绑定共用；换绑定另发、旧的回来后丢弃）。 */
  let _inflight: { key: string; promise: Promise<void> } | null = null
  const _warnedTruncation = new Set<string>()

  /** 当前绑定的项目/年度（用于自动刷新判断） */
  const _projectId = ref('')
  const _year = ref(0)
  const _templateType = ref('soe')

  // ACNR SDK 单例：store 内复用同一实例，保证其内部缓存归 store 掌控，
  // 便于 template-applied / formula-changed 时统一 clearCache（R16.5）。
  // D9（需求 11.1）：按当前绑定项目订阅 SSE 失效。store 是 Pinia setup store（effect scope
  // 内），useAcnr 内部 watch 会在 refresh 切 _projectId 时同步切订阅、随 store 释放。
  const _acnr = useAcnr(() => _projectId.value)

  // ─── 按域分组的计算属性 ───
  const tbAddresses = computed(() => addresses.value.filter(a => a.domain === 'tb'))
  const reportAddresses = computed(() => addresses.value.filter(a => a.domain === 'report'))
  const noteAddresses = computed(() => addresses.value.filter(a => a.domain === 'note'))
  const wpAddresses = computed(() => addresses.value.filter(a => a.domain === 'wp'))
  const auxAddresses = computed(() => addresses.value.filter(a => a.domain === 'aux'))

  // ─── 加载全部地址（首次 / 刷新） ───
  async function refresh(projectId?: string, year?: number, templateType?: string) {
    const pid = projectId || _projectId.value
    const yr = year ?? _year.value
    const tpl = templateType || _templateType.value

    if (!pid) return

    // 更新绑定参数
    _projectId.value = pid
    _year.value = yr
    _templateType.value = tpl

    const key = _bindingKey()
    if (_loadedKey.value && _loadedKey.value !== key) {
      // 换了项目 / 年度 / 口径：先清掉旧数据，加载完成前不能让选择器拿上一个项目的地址当本项目的（R3.4）
      addresses.value = []
      truncatedDomains.value = []
      loaded.value = false
      _loadedKey.value = ''
    }
    // 同一绑定的刷新共用在途请求；原先 loading 时直接 return ⇒ 切到 B 项目的刷新被吞、A 的数据回来后被当成 B 的
    if (_inflight && _inflight.key === key) return _inflight.promise
    const promise = _loadAll(key, pid, yr, tpl)
    _inflight = { key, promise }
    try {
      await promise
    } finally {
      if (_inflight?.promise === promise) _inflight = null
    }
  }

  function _bindingKey(): string {
    return `${_projectId.value}|${_year.value}|${_templateType.value}`
  }

  async function _loadAll(key: string, pid: string, yr: number, tpl: string): Promise<void> {
    loading.value = true
    try {
      const { data } = await http.get(paths.search, {
        params: {
          project_id: pid,
          year: yr,
          template_type: tpl,
          limit: ADDRESS_REGISTRY_FULL_LOAD_LIMIT,
        },
      })
      if (key !== _bindingKey()) return // 回来时已经切到别的项目：丢弃
      const items = data?.items ?? data ?? []
      addresses.value = Array.isArray(items) ? items : []
      truncatedDomains.value = data?.truncated && Array.isArray(data?.truncated_domains) ? data.truncated_domains : []
      _loadedKey.value = key
      loaded.value = true
      if (data?.truncated && !_warnedTruncation.has(key)) {
        _warnedTruncation.add(key)
        console.warn(
          `[addressRegistry] 地址超过 ${ADDRESS_REGISTRY_FULL_LOAD_LIMIT} 条（共 ${data?.total}），`
          + `这些域只加载了一部分：${truncatedDomains.value.join('、')}`,
        )
      }
    } catch (e) {
      console.warn('[addressRegistry] 加载地址注册表失败', e)
    } finally {
      if (!_inflight || _inflight.key === key) loading.value = false
    }
  }

  /** 该域的地址已为当前绑定完整加载（未被上限截断）；为否时选择器改用按关键词搜索或调用方自带的数据。 */
  function isDomainComplete(domain: string): boolean {
    return loaded.value && _loadedKey.value === _bindingKey() && !truncatedDomains.value.includes(domain)
  }

  // ─── ACNR-backed WP 域搜索（R16.3） ───
  // WP 域候选源切到 ACNR listSheets/listCells，映射为 AddressEntry。
  // 匹配 sheet（名称/编码/父底稿码）→ 追加该 sheet 下全部 cell 锚点（有界）。
  async function _searchWpViaAcnr(keyword: string): Promise<AddressEntry[]> {
    const kw = (keyword || '').toLowerCase().trim()
    const sheetList = await _acnr.listSheets()
    if (!sheetList || sheetList.length === 0) return []

    const matchedSheets = kw
      ? sheetList.filter(s =>
          (s.sheet_name || '').toLowerCase().includes(kw) ||
          (s.sheet_code || '').toLowerCase().includes(kw) ||
          (s.parent_wp_code || '').toLowerCase().includes(kw),
        )
      : sheetList

    const results: AddressEntry[] = matchedSheets.map(_mapSheetToEntry)

    // 追加匹配 sheet 的 cell 级地址（有界：仅前 N 个匹配 sheet，避免过量请求）
    const CELL_SHEET_LIMIT = 20
    for (const s of matchedSheets.slice(0, CELL_SHEET_LIMIT)) {
      try {
        const cells = await _acnr.listCells(s.parent_wp_code, s.sheet_code)
        for (const c of cells) results.push(_mapCellToEntry(c))
      } catch {
        /* 单 sheet cell 加载失败忽略，不影响整体搜索 */
      }
    }
    return results
  }

  // ─── 搜索地址 ───
  async function search(
    keyword: string,
    domain?: string,
  ): Promise<AddressEntry[]> {
    if (!_projectId.value) return []

    // R16.3: WP 域走 ACNR listSheets/listCells；其余域（tb/report/note/aux）保留 legacy
    if (domain === 'wp') {
      try {
        const wpResults = await _searchWpViaAcnr(keyword)
        if (wpResults.length > 0) return wpResults
        // ACNR 空结果 → 继续走下方 legacy 回退（fail-open，无空白）
      } catch (e) {
        console.warn('[addressRegistry] ACNR wp 搜索异常，回退 legacy', e)
      }
    }

    // 本地过滤（已加载时优先本地搜索，减少请求）；被截断的域本地不全 ⇒ 走后端按关键词搜
    const localComplete = domain ? isDomainComplete(domain) : loaded.value && truncatedDomains.value.length === 0
    if (localComplete && addresses.value.length > 0) {
      const kw = keyword.toLowerCase()
      return addresses.value.filter(a => {
        if (domain && a.domain !== domain) return false
        return (
          (a.label || '').toLowerCase().includes(kw) ||
          (a.formula_ref || '').toLowerCase().includes(kw) ||
          (a.uri || '').toLowerCase().includes(kw) ||
          (a.account_code || '').includes(kw) ||
          (a.row_code || '').includes(kw) ||
          (a.wp_code || '').toLowerCase().includes(kw)
        )
      })
    }

    // 未加载时走后端搜索
    try {
      const { data } = await http.get(paths.search, {
        params: {
          project_id: _projectId.value,
          year: _year.value,
          keyword,
          domain: domain || '',
          template_type: _templateType.value,
          limit: 100,
        },
      })
      return data?.items ?? data ?? []
    } catch {
      return []
    }
  }

  // ─── 解析单个 URI ───
  async function resolve(uri: string): Promise<ResolveResult> {
    // R16.1: 先走 ACNR /api/acnr/resolve；miss/error 回退 legacy /api/address-registry/resolve
    // 带当前绑定的项目：非底稿域按项目数据判存在（不带时后端只能答「无法确认」）
    try {
      const acnrRes = await _acnr.resolveUri(uri, _projectId.value || undefined)
      if (acnrRes && acnrRes.found) {
        return _mapAcnrResolveToResult(uri, acnrRes)
      }
      // found=false（含 invalid_uri / 未命中）→ 落到 legacy 回退
    } catch (e) {
      console.warn('[addressRegistry] ACNR resolve 异常，回退 legacy', e)
    }

    // legacy 回退
    if (!_projectId.value) return { found: false, uri }
    try {
      const { data } = await http.get(paths.resolve, {
        params: {
          uri,
          project_id: _projectId.value,
          year: _year.value,
          template_type: _templateType.value,
        },
      })
      return data
    } catch {
      return { found: false, uri }
    }
  }

  // ─── 校验公式引用有效性 ───
  async function validate(formula: string): Promise<ValidateResult> {
    // R16.2: 只有「整条公式就是单个 WP 引用」才用 ACNR 命中短路（底稿目录是 ACNR 的权威域）；
    // 其余一律走带项目上下文的数据校验 —— 原先 ACNR 对试算表 / 报表 / 附注引用只做写法换算即 found=true、
    // 复合表达式取第一个引用也判命中，悬空引用被它短路放行（spec formula-fetch-followup-defect-closure R5.4）。
    if (SINGLE_WP_REF.test(formula)) {
      try {
        const r = await _acnr.resolveFormula(formula, _projectId.value || undefined)
        if (r && r.found) {
          return { valid: true, issues: [], formula }
        }
      } catch (e) {
        console.warn('[addressRegistry] ACNR validate 异常，回退 legacy(fail-open)', e)
      }
    }

    // legacy 回退
    if (!_projectId.value) return { valid: true, issues: [], formula }
    try {
      const { data } = await http.post(paths.validate, {
        formula,
        project_id: _projectId.value,
        year: _year.value,
        template_type: _templateType.value,
      })
      return data
    } catch {
      return { valid: false, issues: [{ ref: formula, message: '校验请求失败' }], formula }
    }
  }

  // ─── 获取跳转路由 ───
  async function jump(uri: string, formulaRef?: string): Promise<JumpResult> {
    try {
      const { data } = await http.post(paths.jump, {
        uri: uri || '',
        formula_ref: formulaRef || '',
        project_id: _projectId.value,
        year: _year.value,
      })
      return data
    } catch {
      return { route: '', uri, formula_ref: formulaRef || '' }
    }
  }

  // ─── 失效缓存（后端 + 本地） ───
  async function invalidate(domain?: string) {
    if (!_projectId.value) return
    try {
      await http.post(paths.invalidate, {
        project_id: _projectId.value,
        year: _year.value,
        domain: domain || '',
      })
    } catch { /* ignore */ }
    // 重新加载
    await refresh()
  }

  // ─── 清空本地状态 ───
  function $reset() {
    addresses.value = []
    truncatedDomains.value = []
    _loadedKey.value = ''
    _inflight = null
    loaded.value = false
    loading.value = false
    _projectId.value = ''
    _year.value = 0
    _templateType.value = 'soe'
  }

  // ─── 监听模板应用事件，自动刷新地址注册表 ───
  // 使用防抖避免 template-applied / formula-changed 连续触发时重复请求
  let _refreshDebounceTimer: ReturnType<typeof setTimeout> | null = null
  function _debouncedRefresh(delay = 300) {
    if (_refreshDebounceTimer) clearTimeout(_refreshDebounceTimer)
    _refreshDebounceTimer = setTimeout(() => {
      _refreshDebounceTimer = null
      // R16.5: 目录/公式变更后 ACNR 派生缓存已过时，无条件清空
      _acnr.clearCache()
      if (_projectId.value && loaded.value) refresh()
    }, delay)
  }

  const _onTemplateApplied = () => _debouncedRefresh(500)
  const _onFormulaChanged = () => _debouncedRefresh(300)

  eventBus.on('template-applied', _onTemplateApplied)
  eventBus.on('formula-changed', _onFormulaChanged)

  /**
   * 清理 eventBus 监听器，防止 Store 被销毁后仍持有引用。
   * 在组件 onUnmounted 或 Store 不再需要时调用。
   */
  function dispose() {
    if (_refreshDebounceTimer) {
      clearTimeout(_refreshDebounceTimer)
      _refreshDebounceTimer = null
    }
    eventBus.off('template-applied', _onTemplateApplied)
    eventBus.off('formula-changed', _onFormulaChanged)
  }

  return {
    // 状态
    addresses,
    loaded,
    loading,
    truncatedDomains,
    // 按域分组
    tbAddresses,
    reportAddresses,
    noteAddresses,
    wpAddresses,
    auxAddresses,
    // 方法
    refresh,
    isDomainComplete,
    search,
    resolve,
    validate,
    jump,
    invalidate,
    $reset,
    dispose,
  }
})
