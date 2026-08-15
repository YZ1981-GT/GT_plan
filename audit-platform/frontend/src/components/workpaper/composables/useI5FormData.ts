/**
 * useI5FormData — I5 其他非流动资产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.5
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1911其他非流动资产，借方/资产类）
 * - selfLoad逻辑（render-config?force_component_type=i5-other-noncurrent-assets）
 * - projectContext加载（含business_category/applicable_standards）
 * - TB自动取数 unadjusted_amount → 审定表未审数（仅1911）
 * - setTbValues → 从render策略seed或TB手动设置未审数
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
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

/** I5仅一个科目1911其他非流动资产 */
export interface TbUnadjusted {
  otherNoncurrent1911: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1911 = '1911'

/** TB 数据（bundle 子组件契约） */
export interface I5TbData {
  unadjusted1911: number
  audited1911: number
  priorAudited1911: number
}

export interface UseI5FormDataOptions {
  /** GtWpRenderer 透传 htmlData 时优先使用 */
  htmlData?: Ref<any>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5FormData(
  wpId: Ref<string>,
  projectId: Ref<string>,
  options?: UseI5FormDataOptions,
) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const projectContext = ref<ProjectContext>({})
  const tbUnadjusted = ref<TbUnadjusted>({ otherNoncurrent1911: 0 })
  const tbData = ref<I5TbData>({ unadjusted1911: 0, audited1911: 0, priorAudited1911: 0 })
  const renderMeta = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── getValue / setValue ────────────────────────────────────────────────────

  /** 从 allResponses Map 中获取指定 item 的 remark 值 */
  function getValue(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return undefined
    // 尝试 JSON 解析，失败则返回原始字符串
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
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
      return true
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地，请稍后重试')
      }
      return false
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
   * 用于跨字段同时变更场景（如审定表回写多行）。
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

  // ─── setTbValues（外部设置TB值，render策略seed回读） ────────────────────────

  /**
   * 外部手动设置 TB 未审数（从 render 策略 seed 或组件 watch 调用）。
   * 当 render 策略后端已查 tb_balance 并放入 html_data.tb_values 时，
   * 组件初始化后调用此方法设置本地 state，不再重复请求 TB 端点。
   */
  function setTbValues(values: Partial<TbUnadjusted>): void {
    if (values.otherNoncurrent1911 != null) {
      tbUnadjusted.value.otherNoncurrent1911 = values.otherNoncurrent1911
    }
  }

  // ─── writebackTrialBalance（1911） ─────────────────────────────────────────

  /**
   * 审定数回写 trial_balance：科目1911其他非流动资产（借方/资产类）。
   * I5仅一个科目1911。
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1911,
        audited_amount: auditedAmount,
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── selfLoad（render-config + checklist_responses） ────────────────────────

  /**
   * 从 render-config 加载 allResponses 数据。
   * 当 htmlData prop 为 null 时（bundle内嵌场景）自行调用。
   * 404 静默处理（_silent:true）。
   */
  function _applyTbFromList(list: any[]): void {
    let u1911 = 0
    let a1911 = 0
    let p1911 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith(ACCOUNT_CODE_1911)) {
        u1911 += Number(item.unadjusted_amount ?? 0)
        a1911 += Number(item.audited_amount ?? 0)
        p1911 += Number(
          item.prior_amount
          ?? item.prior_audited_amount
          ?? item.prior_period_amount
          ?? item.last_year_amount
          ?? item.opening_audited_amount
          ?? 0,
        )
      }
    }
    tbData.value = { unadjusted1911: u1911, audited1911: a1911, priorAudited1911: p1911 }
    tbUnadjusted.value = { otherNoncurrent1911: u1911 }
  }

  async function selfLoad(): Promise<void> {
    if (!wpId.value) {
      isLoading.value = false
      return
    }
    isLoading.value = true
    try {
      const html = options?.htmlData?.value
      if (html?.allResponses) {
        const map = new Map<string, ChecklistItem>()
        for (const [k, v] of Object.entries(html.allResponses)) {
          map.set(k, v as ChecklistItem)
        }
        allResponses.value = map
        renderMeta.value = html
      } else {
        const res = await http.get(`/api/workpapers/${wpId.value}/render-config`, {
          params: { force_component_type: 'i5-other-noncurrent-assets' },
          _silent: true,
        } as any)
        const data = res.data?.data || res.data
        renderMeta.value = data?.html_data ?? data ?? {}
        const map = new Map<string, ChecklistItem>()
        if (data?.sheets && Array.isArray(data.sheets)) {
          for (const sheet of data.sheets) {
            if (sheet.html_data?.allResponses) {
              for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
                map.set(k, v as ChecklistItem)
              }
            }
          }
        }
        allResponses.value = map
      }
      await Promise.all([_loadProjectContext(), _loadTbData()])
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadData（兼容别名，供子组件调用） ─────────────────────────────────────

  /** selfLoad 别名，统一接口命名 */
  async function loadData(): Promise<void> {
    return selfLoad()
  }

  // ─── projectContext 加载 ───────────────────────────────────────────────────

  /**
   * 加载项目上下文：business_category / applicable_standards
   * 用于附注显示判断（上市/国企）。
   */
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
   * 从 trial_balance 自动获取科目 1911 的未审数。
   * 填入审定表"未审数"列。科目不存在时显示0+黄色warning。
   */
  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    const seeded1911 = renderMeta.value?.tb_values?.other_noncurrent_1911_unadjusted
    if (seeded1911 != null) {
      const u = Number(seeded1911) || 0
      tbData.value = { unadjusted1911: u, audited1911: 0, priorAudited1911: 0 }
      tbUnadjusted.value = { otherNoncurrent1911: u }
      return
    }

    try {
      const res = await http.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '1911' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data?.data ?? res?.data)
        ? (res?.data?.data ?? res?.data)
        : []
      _applyTbFromList(list)
    } catch {
      tbData.value = { unadjusted1911: 0, audited1911: 0, priorAudited1911: 0 }
      tbUnadjusted.value = { otherNoncurrent1911: 0 }
    }
  }

  /** @deprecated 使用 _loadTbData */
  async function _loadTbUnadjusted(): Promise<void> {
    await _loadTbData()
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
    allResponses,
    projectContext,
    tbUnadjusted,
    tbData,
    renderMeta,
    // Accessors
    getValue,
    setValue,
    // Save actions
    saveImmediate,
    debouncedSave,
    saveBatch,
    // TB writeback
    writebackTrialBalance,
    // TB values setter
    setTbValues,
    // Load
    selfLoad,
    loadData,
  }
}

export default useI5FormData
