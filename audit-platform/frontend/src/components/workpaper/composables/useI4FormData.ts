/**
 * @deprecated 壳层 GtI4LongTermPrepaid 已自管 selfLoad / handleChildSave / TB 取数；
 * I4-1 审定回写使用 useI4Adjudication.writeback。本模块保留 writebackTrialBalance 供脚本/测试复用，
 * 请勿在新 UI 中挂载 useI4FormData（会与壳层双轨）。
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.5
 *
 * 职责（历史）：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1801长期待摊费用，借方/资产类）
 * - selfLoad逻辑（render-config?force_component_type=i4-long-term-prepaid）
 * - projectContext加载（含business_category/applicable_standards）
 * - TB自动取数 unadjusted_amount → 审定表未审数（仅1801）
 * - setTbValues → 从render策略seed或TB手动设置未审数
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

/** I4仅一个科目1801长期待摊费用 */
export interface TbUnadjusted {
  longTermPrepaid1801: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1801 = '1801'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4FormData(wpId: Ref<string>, projectId: Ref<string>) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const projectContext = ref<ProjectContext>({})
  const tbUnadjusted = ref<TbUnadjusted>({ longTermPrepaid1801: 0 })
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
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
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
    if (values.longTermPrepaid1801 != null) {
      tbUnadjusted.value.longTermPrepaid1801 = values.longTermPrepaid1801
    }
  }

  // ─── writebackTrialBalance（1801） ─────────────────────────────────────────

  /**
   * 审定数回写 trial_balance：科目1801长期待摊费用（借方/资产类）。
   * I4仅一个科目1801。
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1801,
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
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'i4-long-term-prepaid' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 2. 加载 checklist_responses
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith('I4-') || r.item_id?.startsWith('I4A-')) {
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
        _loadTbUnadjusted(),
      ])
    } catch {
      // selfLoad 404 静默处理，显示空状态
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
   * 从 trial_balance 自动获取科目 1801 的未审数。
   * 填入审定表"未审数"列。科目不存在时显示0+黄色warning。
   */
  async function _loadTbUnadjusted(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seeded1801 = renderMeta.value?.tb_values?.long_term_prepaid_1801_unadjusted
    if (seeded1801 != null) {
      tbUnadjusted.value = {
        longTermPrepaid1801: Number(seeded1801) || 0,
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '1801' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let longTermPrepaid1801 = 0
      let found1801 = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1801)) {
          longTermPrepaid1801 = Number(item.unadjusted_amount ?? 0)
          found1801 = true
        }
      }

      tbUnadjusted.value = { longTermPrepaid1801 }

      // 科目未找到时黄色提示
      if (!found1801) {
        ElMessage.warning('科目1801长期待摊费用未在试算表中找到，未审数显示为0')
      }
    } catch {
      tbUnadjusted.value = { longTermPrepaid1801: 0 }
    }
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

export default useI4FormData
