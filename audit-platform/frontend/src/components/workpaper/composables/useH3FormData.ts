/**
 * useH3FormData — H3 投资性房地产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.1
 * Requirements: 16.8-16.9
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（成本模式科目1503+1504；公允模式科目1503）
 * - selfLoad逻辑（render-config?force_component_type=h3-investment-property）
 * - projectContext加载（含business_category/applicable_standards）
 * - TB自动取数 unadjusted_amount → 审定表未审数（1503+1504）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

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
  /** 科目1503投资性房地产 未审数（借方/资产类） */
  cost1503: number
  /** 科目1504累计折旧 未审数（贷方/资产备抵类，仅成本模式） */
  dep1504: number
  /** 科目1503 审定数 */
  audited1503: number
  /** 科目1504 审定数 */
  audited1504: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1503 = '1503'
const ACCOUNT_CODE_1504 = '1504'
const ITEM_PREFIX = 'H3-'
const ITEM_PREFIX_A = 'H3A-'

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
  const tbData = ref<TbData>({ cost1503: 0, dep1504: 0, audited1503: 0, audited1504: 0 })
  const renderMeta = ref<Record<string, any>>({})
  const sheetCache = ref<Record<string, any>>({})

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

  // ─── writebackTrialBalance（1503+1504，根据计量模式） ───────────────────────

  /**
   * 审定数回写 trial_balance：
   * - 成本模式：科目1503投资性房地产（借方/资产类）+ 1504累计折旧（贷方/备抵类）
   * - 公允价值模式：仅科目1503（公允价值模式不计提折旧，无1504科目）
   *
   * auditedData:
   *   cost模式 → { cost1503: number, dep1504: number }
   *   fair_value模式 → { cost1503: number }
   */
  async function writebackTrialBalance(auditedData: {
    cost1503: number
    dep1504?: number
  }): Promise<void> {
    if (!projectId.value) return
    try {
      // 回写科目1503投资性房地产（两种模式都需要）
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1503,
        audited_amount: auditedData.cost1503,
      })

      // 成本模式额外回写1504累计折旧
      if (measurementModel.value === 'cost' && auditedData.dep1504 != null) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_1504,
          audited_amount: auditedData.dep1504,
        })
      }

      // 发布 EventBus 事件通知其他底稿（附注等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'H3',
          accountCode: ACCOUNT_CODE_1503,
          auditedAmount: auditedData.cost1503,
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

  // ─── TB自动取数 unadjusted_amount（1503+1504） ─────────────────────────────

  /**
   * 从 trial_balance 自动获取科目 1503+1504 的未审数和审定数。
   * 填入审定表"未审数"列。
   * - 1503: 投资性房地产（借方/资产类，两种模式都需要）
   * - 1504: 投资性房地产累计折旧（贷方/备抵类，仅成本模式需要）
   * 科目不存在时显示0+黄色warning。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（render策略已查好TB数据避免前端重复查询）
    const seeded1503 = renderMeta.value?.tb_values?.inv_prop_1503_unadjusted
    const seeded1504 = renderMeta.value?.tb_values?.dep_1504_unadjusted
    if (seeded1503 != null) {
      tbData.value = {
        cost1503: Number(seeded1503) || 0,
        dep1504: Number(seeded1504 ?? 0) || 0,
        audited1503: Number(renderMeta.value?.tb_values?.inv_prop_1503_audited ?? 0),
        audited1504: Number(renderMeta.value?.tb_values?.dep_1504_audited ?? 0),
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: `${ACCOUNT_CODE_1503},${ACCOUNT_CODE_1504}` },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let cost1503 = 0
      let dep1504 = 0
      let audited1503 = 0
      let audited1504 = 0
      let found1503 = false
      let found1504 = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1503)) {
          cost1503 = Number(item.unadjusted_amount ?? 0)
          audited1503 = Number(item.audited_amount ?? 0)
          found1503 = true
        } else if (code.startsWith(ACCOUNT_CODE_1504)) {
          dep1504 = Number(item.unadjusted_amount ?? 0)
          audited1504 = Number(item.audited_amount ?? 0)
          found1504 = true
        }
      }

      tbData.value = { cost1503, dep1504, audited1503, audited1504 }

      // 科目未找到时黄色提示
      const missing: string[] = []
      if (!found1503) missing.push('1503投资性房地产')
      if (!found1504 && measurementModel.value === 'cost') missing.push('1504累计折旧')
      if (missing.length > 0) {
        ElMessage.warning(`科目${missing.join('/')}未在试算表中找到，未审数显示为0`)
      }
    } catch {
      tbData.value = { cost1503: 0, dep1504: 0, audited1503: 0, audited1504: 0 }
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
