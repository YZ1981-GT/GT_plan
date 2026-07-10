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
import { ref, shallowRef } from 'vue'
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
  resolveInstance: '/api/acnr/resolve-instance',
  lookup: '/api/acnr/lookup',
} as const

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAcnr() {
  // 缓存：避免重复请求同一 cycle/sheet 的数据
  const sheetsCache = new Map<string, AcnrSheetEntry[]>()
  const cellsCache = new Map<string, AcnrCellEntry[]>()

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
    if (sheetsCache.has(cacheKey)) {
      const cached = sheetsCache.get(cacheKey)!
      sheets.value = cached
      return cached
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
      sheetsCache.set(cacheKey, result)
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
    if (cellsCache.has(cacheKey)) {
      const cached = cellsCache.get(cacheKey)!
      cells.value = cached
      return cached
    }

    loading.value = true
    try {
      const { data } = await http.get(ACNR_PATHS.anchors, {
        params: { wp_code: wpCode, sheet },
      })
      const result: AcnrCellEntry[] = Array.isArray(data) ? data : (data?.items ?? [])
      cellsCache.set(cacheKey, result)
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
    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { formula_ref: formulaRef },
      })
      return data as AcnrResolveResult
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
    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { uri },
      })
      return data as AcnrResolveResult
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
    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { addr_id: addrId },
      })
      return data as AcnrResolveResult
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
    try {
      const { data } = await http.get(ACNR_PATHS.resolve, {
        params: { index_ref: indexRef },
      })
      return data as AcnrResolveResult
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

  /** 清空缓存（缓存失效时调用） */
  function clearCache() {
    sheetsCache.clear()
    cellsCache.clear()
    sheets.value = []
    cells.value = []
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
    // 树构建
    buildAddressTree,
    loadCellNodes,
    // 缓存管理
    clearCache,
  }
}
