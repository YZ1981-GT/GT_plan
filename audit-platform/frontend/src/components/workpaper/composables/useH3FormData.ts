/**
 * useH3FormData — H3 投资性房地产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.1
 * Requirements: 16.8-16.9
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（成本模式：原值 + 累计折旧；公允模式：仅原值）
 * - selfLoad逻辑（render-config?force_component_type=h3-investment-property）
 * - projectContext加载（含business_category/applicable_standards）
 * - TB自动取数 unadjusted_amount → 审定表未审数
 *
 * 🔴 **科目码一律经 `h3AccountScope` 取 render 下发的语义定位结果**，本文件不写死
 * 字面量。改造前写死 `1503`/`1504`（= 可供出售金融资产 G6 域 / 债权投资 G4 域），
 * 且 render seed 读的是 dead key ⇒ 未审数取数与审定数回写双双落在错误科目上。
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  H3_SLOT_ACCUM_DEP,
  H3_SLOT_GROSS,
  H3_TB_PREFIX,
  h3AccountScope,
} from './h3AccountScope'
import type { TbSourceCodes } from './shared/tbSourceCodes'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface ProjectContext {
  business_category?: string
  applicable_standards?: string[]
}

export interface TbData {
  /** 投资性房地产原值 未审数（借方/资产类） */
  grossUnadjusted: number
  /** 累计折旧 未审数（贷方/资产备抵类，仅成本模式） */
  accumDepUnadjusted: number
  /** 投资性房地产原值 审定数 */
  grossAudited: number
  /** 累计折旧 审定数 */
  accumDepAudited: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'H3-'
const ITEM_PREFIX_A = 'H3A-'
const EMPTY_TB_DATA: TbData = {
  grossUnadjusted: 0,
  accumDepUnadjusted: 0,
  grossAudited: 0,
  accumDepAudited: 0,
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  measurementModel: Ref<string>
}) {
  const { wpId, projectId, measurementModel } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const projectContext = ref<ProjectContext>({})
  const tbData = ref<TbData>({ ...EMPTY_TB_DATA })
  const renderMeta = ref<Record<string, any>>({})
  const sheetCache = ref<Record<string, any>>({})

  // ─── 科目定位（运行态取 render 下发的 `tb_source_codes`）──────────────────────
  //
  // 🔴 全部对外请求 / 回写 / 事件载荷的科目码都经这里，禁在本文件写死字面量。
  function _tbSourceCodes(): TbSourceCodes | null {
    const rm = renderMeta.value as Record<string, any> | undefined
    return (rm?.tb_source_codes ?? rm?.project_context?.tb_source_codes ?? null) as
      | TbSourceCodes
      | null
  }

  /** 某槽的查询口径（标准码集）；本项目无该科目时返空数组 */
  function h3QueryCodes(slotKey: string): string[] {
    const src = _tbSourceCodes()
    if (h3AccountScope.isAccountAbsent(src, slotKey)) return []
    return h3AccountScope.queryCodes(src, slotKey)
  }

  /** 原值科目码（回写 / 事件载荷）；无则空串 */
  function h3GrossCode(): string {
    return h3QueryCodes(H3_SLOT_GROSS)[0] || ''
  }

  /** 累计折旧科目码；本项目无该科目时空串（不回写，宁缺勿造） */
  function h3AccumDepCode(): string {
    return h3QueryCodes(H3_SLOT_ACCUM_DEP)[0] || ''
  }

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── getValue / setValue ────────────────────────────────────────────────────

  /** 从 allResponses Map 中获取指定 item 的值（尝试 JSON 解析） */
  function getValue(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return undefined
    const raw = item.remark ?? item.conclusion
    if (raw == null) return undefined
    try {
      return JSON.parse(raw)
    } catch {
      return raw
    }
  }

  /** 设置 allResponses Map 中的值，并触发 debouncedSave */
  function setValue(itemId: string, value: any): void {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId)
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: existing?.conclusion ?? null,
      remark: strVal,
    }
    allResponses.value.set(itemId, updated)
    debouncedSave(itemId, updated)
  }

  // ─── Save: core ────────────────────────────────────────────────────────────

  async function _doSave(items: ChecklistItem[]): Promise<boolean> {
    if (!wpId.value || items.length === 0) return true
    isSaving.value = true
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
      lastSavedAt.value = new Date().toISOString()
      return true
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地，请稍后重试')
      }
      return false
    } finally {
      isSaving.value = false
    }
  }

  // ─── saveImmediate ─────────────────────────────────────────────────────────

  /**
   * 立即保存指定 item（结论/状态/选择类字段触发）。
   * 乐观更新：先更新本地 Map，保存失败不回滚（保留本地数据）。
   */
  async function saveImmediate(itemId: string, value: any): Promise<void> {
    // 取消已有 debounce
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    _pendingItems.delete(itemId)

    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId)
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: existing?.conclusion ?? null,
      remark: strVal,
    }
    allResponses.value.set(itemId, updated)
    await _doSave([updated])
  }

  // ─── debouncedSave (2s) ────────────────────────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
   * 输入变更后 debounce 2秒自动保存。
   */
  function debouncedSave(itemId: string, data: ChecklistItem): void {
    allResponses.value.set(itemId, data)
    _pendingItems.add(itemId)

    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)

    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([data])
    }, DEBOUNCE_MS))
  }

  // ─── saveBatch (原子性批量保存) ────────────────────────────────────────────

  /**
   * 批量原子性保存多个 item。
   * 用于跨字段同时变更场景（如审定表回写多行/互转联动批量更新）。
   */
  async function saveBatch(items: { itemId: string; value: any }[]): Promise<void> {
    const checklistItems: ChecklistItem[] = items.map(({ itemId, value }) => {
      const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
      const existing = allResponses.value.get(itemId)
      const updated: ChecklistItem = {
        item_id: itemId,
        conclusion: existing?.conclusion ?? null,
        remark: strVal,
      }
      // 乐观更新本地 Map
      allResponses.value.set(itemId, updated)
      // 取消已有 debounce
      const timer = _debounceTimers.get(itemId)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(itemId)
      }
      _pendingItems.delete(itemId)
      return updated
    })

    await _doSave(checklistItems)
  }

  // ─── writebackTrialBalance（原值 + 累计折旧，按计量模式）─────────────────────

  /**
   * 审定数回写 trial_balance：
   * - 成本模式：投资性房地产原值（借方/资产类）+ 累计折旧（贷方/备抵类）
   * - 公允价值模式：仅原值（公允价值模式不计提折旧）
   *
   * 🔴 科目码取 render 下发的语义定位结果（`h3AccountScope`），改造前写死
   * `1503`/`1504` —— 那是**可供出售金融资产(G6 域)** 与 **债权投资(G4 域)**，
   * 即长期在往别的两个循环的试算表行写投资性房地产审定数。
   */
  async function writebackTrialBalance(auditedData: {
    grossAudited: number
    accumDepAudited?: number
  }): Promise<void> {
    if (!projectId.value) return
    const grossCode = h3GrossCode()
    const depCode = h3AccumDepCode()
    try {
      if (grossCode) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: grossCode,
          audited_amount: auditedData.grossAudited,
        })
      }

      // 成本模式额外回写累计折旧；本项目无该科目时不写（宁缺勿造）
      if (
        measurementModel.value === 'cost'
        && auditedData.accumDepAudited != null
        && depCode
      ) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: depCode,
          audited_amount: auditedData.accumDepAudited,
        })
      }

      // 发布 EventBus 事件通知其他底稿（附注等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'H3',
          accountCode: grossCode,
          auditedAmount: auditedData.grossAudited,
          measurementModel: measurementModel.value,
        },
      }))
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── selfLoad（render-config + checklist_responses） ────────────────────────

  /**
   * 从 render-config 加载数据（当 htmlData prop 为 null 时自行调用）。
   * selfLoad 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'h3-investment-property' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 缓存各sheet html_data
      for (const s of configData?.sheets ?? configData?.data?.sheets ?? []) {
        const name = s.sheet_name || s.name || 'default'
        sheetCache.value[name] = s.html_data ?? s
      }

      // 2. 加载 checklist_responses
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith(ITEM_PREFIX) || r.item_id?.startsWith(ITEM_PREFIX_A)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map

      // 3. 并行加载 projectContext + TB取数
      await Promise.all([
        _loadProjectContext(),
        _loadTbData(),
      ])
    } catch {
      // selfLoad 404 静默处理，显示空状态
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadAllResponses（外部可调的显式加载） ─────────────────────────────────

  /**
   * 从 checklist_responses 端点加载全部 H3- 前缀数据到 allResponses Map。
   * 返回加载后的 Map（供初始化后立即使用）。
   */
  async function loadAllResponses(): Promise<Map<string, ChecklistItem>> {
    if (!wpId.value) return allResponses.value
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith(ITEM_PREFIX) || r.item_id?.startsWith(ITEM_PREFIX_A)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
      return map
    } catch {
      ElMessage.warning('H3数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── projectContext 加载 ───────────────────────────────────────────────────

  /**
   * 加载项目上下文：business_category / applicable_standards
   * 用于附注显示判断（上市/国企）+ 计量模式适用性判断。
   */
  async function loadProjectContext(): Promise<void> {
    await _loadProjectContext()
  }

  async function _loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const res = await api.get(`/api/projects/${projectId.value}`, {
        _silent: true,
      } as any)
      const data = res?.data ?? res
      projectContext.value = {
        business_category: data?.business_category ?? undefined,
        applicable_standards: data?.applicable_standards ?? undefined,
      }
    } catch {
      // 静默失败，projectContext 保持空
    }
  }

  // ─── TB自动取数 unadjusted_amount（原值 + 累计折旧）──────────────────────────

  /**
   * 从 trial_balance 自动获取投资性房地产原值与累计折旧的未审数/审定数，
   * 填入审定表「未审数」列。科目不存在时显示 0 + 黄色 warning。
   *
   * 🔴 **改造前有两处独立缺陷，叠加后该函数从来没取对过数**：
   * 1. render seed 读的键是 `inv_prop_1503_unadjusted` / `dep_1504_unadjusted`，
   *    而后端 `build_h3_tb_values` 按 `H3_SLOT_KEY_PREFIX` 产出的是
   *    `ip_unadjusted` / `dep_unadjusted` / `amort_*` / `impair_*`
   *    ⇒ 四个键**全是 dead render key**，seed 分支永不命中；
   * 2. 于是必然落到 HTTP 兜底查询，而它按 `account_prefix=1503,1504` 查 ——
   *    那是**可供出售金融资产(G6)** 与 **债权投资(G4)** ⇒ 取的是别的循环的余额。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（render 策略已查好 TB 数据，避免前端重复查询）
    const tv = renderMeta.value?.tb_values as Record<string, any> | undefined
    const seededGross = tv?.[`${H3_TB_PREFIX.gross}_unadjusted`]
    if (seededGross != null) {
      tbData.value = {
        grossUnadjusted: Number(seededGross) || 0,
        accumDepUnadjusted: Number(tv?.[`${H3_TB_PREFIX.accumDep}_unadjusted`] ?? 0) || 0,
        grossAudited: Number(tv?.[`${H3_TB_PREFIX.gross}_audited`] ?? 0),
        accumDepAudited: Number(tv?.[`${H3_TB_PREFIX.accumDep}_audited`] ?? 0),
      }
      return
    }

    const grossCodes = h3QueryCodes(H3_SLOT_GROSS)
    const depCodes = h3QueryCodes(H3_SLOT_ACCUM_DEP)
    const wanted = [...grossCodes, ...depCodes].filter(Boolean)
    if (!wanted.length) {
      tbData.value = { ...EMPTY_TB_DATA }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: wanted.join(',') },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let grossUnadjusted = 0
      let accumDepUnadjusted = 0
      let grossAudited = 0
      let accumDepAudited = 0
      let foundGross = false
      let foundDep = false

      /** 严格边界：`1521` 不得误命中 `15210`（不同科目） */
      const inFamily = (code: string, prefixes: string[]) =>
        prefixes.some((p) => code === p || code.startsWith(`${p}.`) || code.startsWith(`${p}-`))

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (inFamily(code, depCodes)) {
          // 备抵先判：`投资性房地产累计折旧` 也以原值科目名为前缀
          accumDepUnadjusted += Number(item.unadjusted_amount ?? 0)
          accumDepAudited += Number(item.audited_amount ?? 0)
          foundDep = true
        } else if (inFamily(code, grossCodes)) {
          grossUnadjusted += Number(item.unadjusted_amount ?? 0)
          grossAudited += Number(item.audited_amount ?? 0)
          foundGross = true
        }
      }

      tbData.value = { grossUnadjusted, accumDepUnadjusted, grossAudited, accumDepAudited }

      // 科目未找到时黄色提示（显示的是本项目实际查询口径，不是写死的码）
      const missing: string[] = []
      if (!foundGross) missing.push(`投资性房地产原值(${grossCodes.join('/')})`)
      if (!foundDep && measurementModel.value === 'cost' && depCodes.length) {
        missing.push(`累计折旧(${depCodes.join('/')})`)
      }
      if (missing.length > 0) {
        ElMessage.warning(`科目${missing.join('、')}未在试算表中找到，未审数显示为0`)
      }
    } catch {
      tbData.value = { ...EMPTY_TB_DATA }
    }
  }

  // ─── getSheet (从 sheetCache 获取指定 sheet 数据) ───────────────────────────

  function getSheet(name: string): any {
    return sheetCache.value[name] ?? { rows: [] }
  }

  // ─── Flush (组件卸载时确保无数据丢失) ──────────────────────────────────────

  function _flushPending(): void {
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    if (_pendingItems.size > 0) {
      const items: ChecklistItem[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) {
        void _doSave(items)
      }
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    isLoading,
    isSaving,
    lastSavedAt,
    allResponses,
    projectContext,
    tbData,
    renderMeta,
    sheetCache,
    // Accessors
    getValue,
    setValue,
    getSheet,
    // Save actions
    saveImmediate,
    debouncedSave,
    saveBatch,
    // TB writeback
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadProjectContext,
    loadTbData,
  }
}

export default useH3FormData
