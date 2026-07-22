/**
 * useH2FormData — H2 在建工程底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.1
 * Requirements: 14.8-14.9
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1604借方）
 * - selfLoad逻辑（render-config?force_component_type=h2-construction-in-progress）
 * - projectContext加载（含business_category/applicable_standards）
 * - TB自动取数 unadjusted_amount → 审定表未审数
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
  unadjusted_amount: number
  audited_amount: number
  /** 工程物资 1605 */
  materials_unadjusted?: number
  materials_audited?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1604 = '1604'
const ITEM_PREFIX = 'H2-'
const ITEM_PREFIX_A = 'H2A-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2FormData(wpId: Ref<string>, projectId: Ref<string>) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const projectContext = ref<ProjectContext>({})
  const tbData = ref<TbData>({
    unadjusted_amount: 0,
    audited_amount: 0,
    materials_unadjusted: 0,
    materials_audited: 0,
  })
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
   * 用于跨字段同时变更场景（如审定表回写多行/导入整表提交）。
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

  // ─── writebackTrialBalance（1604在建工程，借方/资产类） ─────────────────────

  /**
   * 审定数回写 trial_balance：科目1604在建工程（借方/资产类）。
   * H2-1审定数→TB回写，并通过EventBus发布 'substantive:adjudicated'
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1604,
        audited_amount: auditedAmount,
      })
      // 发布 EventBus 事件通知其他底稿（附注等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { wpCode: 'H2', accountCode: ACCOUNT_CODE_1604, auditedAmount },
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
        params: { force_component_type: 'h2-construction-in-progress' },
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
   * 从 checklist_responses 端点加载全部 H2- 前缀数据到 allResponses Map。
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
      ElMessage.warning('H2数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── projectContext 加载 ───────────────────────────────────────────────────

  /**
   * 加载项目上下文：business_category / applicable_standards
   * 用于附注显示判断（上市/国企）+ 适用性判断。
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

  // ─── TB自动取数 unadjusted_amount ──────────────────────────────────────────

  /**
   * 从 trial_balance 自动获取科目 1604 的未审数和审定数。
   * 填入审定表"未审数"列。科目不存在时显示0+黄色warning。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（兼容 cip_unadjusted / cip_1604_unadjusted）
    const tv = renderMeta.value?.tb_values
    if (tv && typeof tv === 'object') {
      const cipUnadj = tv.cip_1604_unadjusted ?? tv.cip_unadjusted
      if (cipUnadj != null || tv.cip_audited != null || tv.cip_1604_audited != null) {
        tbData.value = {
          unadjusted_amount: Number(cipUnadj ?? 0) || 0,
          audited_amount: Number(tv.cip_1604_audited ?? tv.cip_audited ?? 0) || 0,
          materials_unadjusted: Number(tv.eng_mat_1605_unadjusted ?? tv.eng_mat_unadjusted ?? 0) || 0,
          materials_audited: Number(tv.eng_mat_1605_audited ?? tv.eng_mat_audited ?? 0) || 0,
        }
        return
      }
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '160' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted = 0
      let audited = 0
      let matUnadj = 0
      let matAud = 0
      let foundCip = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code === '1604' || code.startsWith('1604')) {
          unadjusted += Number(item.unadjusted_amount ?? 0)
          audited += Number(item.audited_amount ?? 0)
          foundCip = true
        } else if (code === '1605' || code.startsWith('1605')) {
          matUnadj += Number(item.unadjusted_amount ?? 0)
          matAud += Number(item.audited_amount ?? 0)
        }
      }

      tbData.value = {
        unadjusted_amount: unadjusted,
        audited_amount: audited,
        materials_unadjusted: matUnadj,
        materials_audited: matAud,
      }

      if (!foundCip) {
        ElMessage.warning('科目1604在建工程未在试算表中找到，未审数显示为0')
      }
    } catch {
      tbData.value = {
        unadjusted_amount: 0,
        audited_amount: 0,
        materials_unadjusted: 0,
        materials_audited: 0,
      }
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

export default useH2FormData
