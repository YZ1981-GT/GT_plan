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
import { ref, computed } from 'vue'
import http from '@/utils/http'
import { addressRegistry as paths } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'
import {
  useAcnr,
  type AcnrSheetEntry,
  type AcnrCellEntry,
  type AcnrResolveResult,
} from '@/services/acnr/useAcnr'

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
  issues: Array<{ ref: string; reason: string }>
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
  const addresses = ref<AddressEntry[]>([])
  const loaded = ref(false)
  const loading = ref(false)

  /** 当前绑定的项目/年度（用于自动刷新判断） */
  const _projectId = ref('')
  const _year = ref(0)
  const _templateType = ref('soe')

  // ACNR SDK 单例：store 内复用同一实例，保证其内部缓存归 store 掌控，
  // 便于 template-applied / formula-changed 时统一 clearCache（R16.5）。
  const _acnr = useAcnr()

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

    if (loading.value) return
    loading.value = true
    try {
      const { data } = await http.get(paths.search, {
        params: {
          project_id: pid,
          year: yr,
          template_type: tpl,
          limit: 5000,
        },
      })
      const items = data?.items ?? data ?? []
      addresses.value = Array.isArray(items) ? items : []
      loaded.value = true
    } catch (e) {
      console.warn('[addressRegistry] 加载地址注册表失败', e)
    } finally {
      loading.value = false
    }
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

    // 本地过滤（已加载时优先本地搜索，减少请求）
    if (loaded.value && addresses.value.length > 0) {
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
    try {
      const acnrRes = await _acnr.resolveUri(uri)
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
    // R16.2: 先走 ACNR-backed 校验（resolveFormula，与后端 Req 9 同源）；
    // ACNR 明确命中（found=true）→ 直接判定有效；
    // 未命中 / 复合表达式 / 非 WP 域 / infra 失败 → fail-open 回退 legacy 权威多引用校验。
    // （前端无法安全拆分复合公式，故非命中一律交由 legacy，避免误报悬空引用。）
    try {
      const r = await _acnr.resolveFormula(formula)
      if (r && r.found) {
        return { valid: true, issues: [], formula }
      }
    } catch (e) {
      console.warn('[addressRegistry] ACNR validate 异常，回退 legacy(fail-open)', e)
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
      return { valid: false, issues: [{ ref: formula, reason: '校验请求失败' }], formula }
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
    // 按域分组
    tbAddresses,
    reportAddresses,
    noteAddresses,
    wpAddresses,
    auxAddresses,
    // 方法
    refresh,
    search,
    resolve,
    validate,
    jump,
    invalidate,
    $reset,
    dispose,
  }
})
