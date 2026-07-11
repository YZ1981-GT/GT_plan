/**
 * useFormulaScopeCatalog — 公式作用域过滤 + 全局公式总览 composable（Req 24）
 *
 * 消费 Task 20.2 建立的后端只读端点（`backend/app/routers/formula_scope_query.py`）：
 * - GET /api/formula-scope/{project_id}/formulas?scope={scope}
 *     → 仅返回该 Formula_Scope 的公式（弹窗按域加载，Req 24.1/24.2）。
 * - GET /api/formula-scope/{project_id}/formulas
 *     → 返回按 7 类作用域分组的并集（全局公式管理页，Req 24.3）。
 *
 * 作用域隔离（Req 24.5）：缓存以 `(scope, addrKey)` 为键（`scopeCache[scope]` 为
 * `Map<addrKey, ScopeFormulaRow>`），各作用域的公式集互斥存放 → 对某作用域的
 * 增/改/删只改变该作用域列表，其余作用域列表逐一不变。
 *
 * 来源地址规范化（Req 24.6，与 Req 10 / P14 一致）：每条公式的来源地址一律经
 * ACNR full_resolve（`useAcnr().resolveAddr`）取 canonical `semantic_label`，
 * 而非前端拼接 `wp_code+sheet+cell` 坐标串。
 *
 * 工程约定：http(axios) 自动带 Authorization；响应 `{code,message,data}` 信封由
 * http 拦截器解包（此处仍做 `?.data ?? data` 双兜底，兼容测试桩）。本 composable
 * 只读，不写库。
 *
 * Spec: .kiro/specs/formula-management-library/  Task: 20.1
 * Requirements: 24.1, 24.2, 24.3, 24.4, 24.5, 24.6
 */
import { ref, computed } from 'vue'
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'

// ── Formula_Scope 7 类（与后端 FORMULA_SCOPES / 组件 FormulaManagerScope 对齐）──
export const FORMULA_SCOPES = [
  'note',
  'consol_note',
  'consol_worksheet',
  'consol_report',
  'report',
  'tb',
  'workpaper',
] as const

export type FormulaScope = (typeof FORMULA_SCOPES)[number]

// 作用域中文标签（与后端 SCOPE_LABEL_MAP / 组件 SCOPE_LABEL_MAP 一致）。
export const SCOPE_LABEL_MAP: Record<FormulaScope, string> = {
  note: '单体附注',
  consol_note: '合并附注',
  consol_worksheet: '合并工作底稿',
  consol_report: '合并报表',
  report: '报表',
  tb: '试算平衡表',
  workpaper: '底稿',
}

/** 一条作用域公式（后端 formula_to_dict 的前端归一化视图）。 */
export interface ScopeFormulaRow {
  id: string
  scope: FormulaScope
  scopeLabel: string
  wpId: string | null
  sheetName: string | null
  targetCell: string
  expression: string | null
  formulaType: string | null
  formulaSource: string | null
  refs: unknown[]
  issueDescription: string | null
  hintText: string | null
  lastComputedAt: string | null
  /** (scope, addrKey) 隔离键：优先取首个引用 addr_id，回退 wp/sheet/cell 复合键。 */
  addrKey: string
  /** 来源地址 addr_id（供 ACNR full_resolve 取规范名，Req 24.6）。 */
  sourceAddrId: string | null
  /** 经 ACNR full_resolve 得到的 canonical semantic_label（懒解析填充）。 */
  sourceLabel: string | null
}

/** 全局并集按作用域分组。 */
export type GlobalGrouped = Record<FormulaScope, ScopeFormulaRow[]>

function isFormulaScope(v: unknown): v is FormulaScope {
  return typeof v === 'string' && (FORMULA_SCOPES as readonly string[]).includes(v)
}

/** 从一条公式的 refs 中提取首个 addr_id（禁拼坐标串，Req 24.6）。 */
function firstRefAddrId(refs: unknown): string | null {
  if (!Array.isArray(refs)) return null
  for (const r of refs) {
    if (typeof r === 'string' && r) return r
    if (r && typeof r === 'object') {
      const addrId = (r as Record<string, unknown>).addr_id
      if (typeof addrId === 'string' && addrId) return addrId
      const formulaRef = (r as Record<string, unknown>).formula_ref
      if (typeof formulaRef === 'string' && formulaRef) return formulaRef
    }
  }
  return null
}

/** 把后端 item 归一化为 ScopeFormulaRow（含 (scope,addrKey) 隔离键派生）。 */
function mapItem(raw: Record<string, unknown>, scope: FormulaScope): ScopeFormulaRow {
  const refs = Array.isArray(raw.refs) ? (raw.refs as unknown[]) : []
  const wpId = (raw.wp_id as string) ?? null
  const sheetName = (raw.sheet_name as string) ?? null
  const targetCell = (raw.target_cell as string) ?? ''
  const sourceAddrId = firstRefAddrId(refs)
  // (scope, addrKey)：有引用 addr_id 用之；否则用 wp/sheet/cell 复合键保证域内唯一。
  const addrKey = sourceAddrId ?? `${wpId ?? ''}::${sheetName ?? ''}::${targetCell}`
  return {
    id: String(raw.id ?? ''),
    scope,
    scopeLabel: (raw.scope_label as string) ?? SCOPE_LABEL_MAP[scope] ?? scope,
    wpId,
    sheetName,
    targetCell,
    expression: (raw.expression as string) ?? null,
    formulaType: (raw.formula_type as string) ?? null,
    formulaSource: (raw.formula_source as string) ?? null,
    refs,
    issueDescription: (raw.issue_description as string) ?? null,
    hintText: (raw.hint_text as string) ?? null,
    lastComputedAt: (raw.last_computed_at as string) ?? null,
    addrKey,
    sourceAddrId,
    sourceLabel: null,
  }
}

export function useFormulaScopeCatalog() {
  const acnr = useAcnr()

  // (scope, addrKey) 隔离缓存：每个作用域一个 Map，键为 addrKey。
  const scopeCache: Record<string, Map<string, ScopeFormulaRow>> = {}
  // 响应式版本号：Map 就地修改不触发 ref 深层响应，靠此计数驱动 computed 重算。
  const revision = ref(0)
  const loading = ref(false)

  function ensureScopeMap(scope: FormulaScope): Map<string, ScopeFormulaRow> {
    if (!scopeCache[scope]) scopeCache[scope] = new Map()
    return scopeCache[scope]
  }

  function bump() {
    revision.value += 1
  }

  /** 用一批行整体替换某作用域缓存（各行按 addrKey 去重，仅动该作用域）。 */
  function replaceScope(scope: FormulaScope, rows: ScopeFormulaRow[]) {
    const map = new Map<string, ScopeFormulaRow>()
    for (const row of rows) map.set(row.addrKey, row)
    scopeCache[scope] = map
    bump()
  }

  /**
   * 按 Formula_Scope 加载本域公式（Req 24.1/24.2）。
   * 仅刷新该作用域缓存，其余作用域逐一不变（Req 24.5）。
   */
  async function loadScope(
    projectId: string,
    scope: FormulaScope,
  ): Promise<ScopeFormulaRow[]> {
    if (!projectId || !isFormulaScope(scope)) return []
    loading.value = true
    try {
      const response = await http.get(
        `/api/formula-scope/${projectId}/formulas`,
        { params: { scope } },
      )
      const payload = (response?.data?.data ?? response?.data ?? {}) as {
        items?: Record<string, unknown>[]
      }
      const items = Array.isArray(payload.items) ? payload.items : []
      const rows = items.map((it) => mapItem(it, scope))
      replaceScope(scope, rows)
      return getScopeRows(scope)
    } catch {
      return getScopeRows(scope)
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载全部作用域并集（全局公式管理页，Req 24.3）。
   * 逐作用域填充隔离缓存 → 全局页展示 == 各作用域并集。
   */
  async function loadGlobal(projectId: string): Promise<GlobalGrouped> {
    if (!projectId) return emptyGrouped()
    loading.value = true
    try {
      const response = await http.get(`/api/formula-scope/${projectId}/formulas`)
      const payload = (response?.data?.data ?? response?.data ?? {}) as {
        scopes?: Record<string, { items?: Record<string, unknown>[] }>
      }
      const scopes = payload.scopes ?? {}
      for (const scope of FORMULA_SCOPES) {
        const items = Array.isArray(scopes[scope]?.items) ? scopes[scope]!.items! : []
        replaceScope(scope, items.map((it) => mapItem(it, scope)))
      }
      return globalGrouped.value
    } catch {
      return globalGrouped.value
    } finally {
      loading.value = false
    }
  }

  /** 某作用域当前缓存的行（只返回该作用域，Req 24.2 无泄漏）。 */
  function getScopeRows(scope: FormulaScope): ScopeFormulaRow[] {
    void revision.value // 建立响应式依赖
    const map = scopeCache[scope]
    return map ? Array.from(map.values()) : []
  }

  /** 全局并集按作用域分组（含全部 7 类键，无公式者为空数组）。 */
  const globalGrouped = computed<GlobalGrouped>(() => {
    void revision.value
    const out = emptyGrouped()
    for (const scope of FORMULA_SCOPES) {
      out[scope] = getScopeRows(scope)
    }
    return out
  })

  /** 全局所有作用域行的扁平并集。 */
  const allRows = computed<ScopeFormulaRow[]>(() => {
    void revision.value
    return FORMULA_SCOPES.flatMap((s) => getScopeRows(s))
  })

  /** 全局公式总数。 */
  const totalCount = computed(() => allRows.value.length)

  /**
   * 隔离编辑：仅更新目标作用域内某公式（Req 24.5）。
   * 用于弹窗内编辑/新增后回写缓存，不触碰其他作用域。
   */
  function upsertFormula(scope: FormulaScope, row: ScopeFormulaRow) {
    ensureScopeMap(scope).set(row.addrKey, { ...row, scope })
    bump()
  }

  /** 隔离删除：仅从目标作用域移除。 */
  function removeFormula(scope: FormulaScope, addrKey: string) {
    scopeCache[scope]?.delete(addrKey)
    bump()
  }

  /**
   * 经 ACNR full_resolve 规范化一批行的来源地址（Req 24.6）。
   * found=true → 取 canonical semantic_label；否则保持 null（不拼坐标串）。
   */
  async function resolveSources(rows: ScopeFormulaRow[]): Promise<void> {
    for (const row of rows) {
      if (!row.sourceAddrId || row.sourceLabel) continue
      try {
        const res = await acnr.resolveAddr(row.sourceAddrId)
        row.sourceLabel = res?.found ? res.semantic_label ?? null : null
      } catch {
        row.sourceLabel = null
      }
    }
    bump()
  }

  /** 规范化某作用域全部行的来源地址。 */
  async function resolveScopeSources(scope: FormulaScope): Promise<void> {
    await resolveSources(getScopeRows(scope))
  }

  function clear() {
    for (const key of Object.keys(scopeCache)) delete scopeCache[key]
    bump()
  }

  return {
    // state
    loading,
    // loaders
    loadScope,
    loadGlobal,
    // accessors
    getScopeRows,
    globalGrouped,
    allRows,
    totalCount,
    // isolation mutators
    upsertFormula,
    removeFormula,
    // ACNR source normalization (Req 24.6)
    resolveSources,
    resolveScopeSources,
    clear,
  }
}

function emptyGrouped(): GlobalGrouped {
  return {
    note: [],
    consol_note: [],
    consol_worksheet: [],
    consol_report: [],
    report: [],
    tb: [],
    workpaper: [],
  }
}

export default useFormulaScopeCatalog
