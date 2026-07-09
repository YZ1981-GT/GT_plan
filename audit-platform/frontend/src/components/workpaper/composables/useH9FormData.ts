/**
 * useH9FormData — H9 租赁负债底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.8
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目2205租赁负债 贷方/负债类 + 未确认融资费用 借方/负债备抵类）
 * - selfLoad逻辑（render-config?force_component_type=h9-lease-liabilities）
 * - TB自动取数 unadjusted_amount → 审定表未审数（2205+未确认融资费用）
 * - CAS21特有：H9与H8强联动配对底稿
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

export interface H9TbData {
  /** 科目2205租赁负债 未审数（贷方/负债类） */
  unadjusted2205: number
  /** 科目2205 审定数 */
  audited2205: number
  /** 未确认融资费用 未审数（借方/负债备抵类） */
  unadjustedFinanceCost: number
  /** 未确认融资费用 审定数 */
  auditedFinanceCost: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目2205 租赁负债（贷方/负债类） */
const ACCOUNT_CODE_2205 = '2205'
/** 未确认融资费用科目编码（借方/负债备抵类） */
const ACCOUNT_CODE_FINANCE_COST = '1802'
const ITEM_PREFIX = 'H9-'
const ITEM_PREFIX_A = 'H9A-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
}) {
  const { wpId, projectId } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<H9TbData>({
    unadjusted2205: 0,
    audited2205: 0,
    unadjustedFinanceCost: 0,
    auditedFinanceCost: 0,
  })
  const renderMeta = ref<Record<string, any>>({})
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── getResponse / getResponses ────────────────────────────────────────────

  /** 从 allResponses Map 中获取指定 item 的值（尝试 JSON 解析） */
  function getResponse(itemId: string): any {
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

  /** 获取指定前缀的全部 responses（用于跨sheet computed链） */
  function getResponses(prefix: string): Map<string, any> {
    const result = new Map<string, any>()
    for (const [key, item] of allResponses.value) {
      if (key.startsWith(prefix)) {
        const raw = item.remark ?? item.conclusion
        if (raw != null) {
          try {
            result.set(key, JSON.parse(raw))
          } catch {
            result.set(key, raw)
          }
        }
      }
    }
    return result
  }

  // ─── saveResponse (single item) ────────────────────────────────────────────

  /**
   * 立即保存指定 item（结论/状态/选择类字段触发）。
   * 乐观更新：先更新本地 Map，保存失败不回滚（保留本地数据）。
   */
  async function saveResponse(itemId: string, value: any): Promise<void> {
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

  // ─── saveBatchResponses (atomic batch) ─────────────────────────────────────

  /**
   * 批量原子性保存多个 item。
   * 用于跨字段同时变更场景（如审定表回写多行/跨sheet联动/H8联动批量更新）。
   */
  async function saveBatchResponses(items: { itemId: string; value: any }[]): Promise<void> {
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

  // ─── setValue (with debounce) ───────────────────────────────────────────────

  /** 设置 allResponses Map 中的值，并触发 debouncedSave(2s) */
  function setValue(itemId: string, value: any): void {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId)
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: existing?.conclusion ?? null,
      remark: strVal,
    }
    allResponses.value.set(itemId, updated)
    _debouncedSave(itemId, updated)
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

  // ─── debouncedSave (2s) ────────────────────────────────────────────────────

  function _debouncedSave(itemId: string, data: ChecklistItem): void {
    _pendingItems.add(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)

    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([data])
    }, DEBOUNCE_MS))
  }

  // ─── writebackTrialBalance（科目2205租赁负债 + 未确认融资费用） ──────────────

  /**
   * 审定数回写 trial_balance：
   * - 科目2205租赁负债（贷方/负债类）
   * - 未确认融资费用（借方/负债备抵类）
   *
   * 审定数变化时回写TB并发布 'substantive:adjudicated' EventBus事件。
   * CAS21特有：H9与H8强联动，回写后通知附注及相关底稿。
   */
  async function writebackTrialBalance(
    auditedAmount2205: number,
    auditedAmountFinanceCost?: number
  ): Promise<void> {
    if (!projectId.value) return
    try {
      // 回写2205租赁负债（贷方/负债类）
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_2205,
        audited_amount: auditedAmount2205,
      })

      // 回写未确认融资费用（借方/负债备抵类，如果提供）
      if (auditedAmountFinanceCost != null) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_FINANCE_COST,
          audited_amount: auditedAmountFinanceCost,
        })
      }

      // 发布 EventBus 事件通知其他底稿（附注/H8使用权资产/报表等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'H9',
          accountCode: ACCOUNT_CODE_2205,
          auditedAmount: auditedAmount2205,
          auditedAmountFinanceCost: auditedAmountFinanceCost ?? null,
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
        params: { force_component_type: 'h9-lease-liabilities' },
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

      // 3. TB自动取数（2205 + 未确认融资费用）
      await _loadTbData()
    } catch {
      // selfLoad 404 静默处理，显示空状态
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadAllResponses（外部可调的显式加载） ─────────────────────────────────

  /**
   * 从 checklist_responses 端点加载全部 H9- 前缀数据到 allResponses Map。
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
      ElMessage.warning('H9数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── TB自动取数 unadjusted_amount（2205 + 未确认融资费用） ──────────────────

  /**
   * 从 trial_balance 自动获取科目 2205 和未确认融资费用的未审数和审定数。
   * 填入审定表"未审数"列（只读取数）。
   * 2205：租赁负债，贷方/负债类（期末=期初+贷-借）
   * 未确认融资费用：借方/负债备抵类（期末=期初+借-贷）
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seeded2205 = renderMeta.value?.tb_values?.lease_2205_unadjusted
    if (seeded2205 != null) {
      tbData.value = {
        unadjusted2205: Number(seeded2205) || 0,
        audited2205: Number(renderMeta.value?.tb_values?.lease_2205_audited ?? 0),
        unadjustedFinanceCost: Number(renderMeta.value?.tb_values?.lease_finance_cost_unadjusted ?? 0),
        auditedFinanceCost: Number(renderMeta.value?.tb_values?.lease_finance_cost_audited ?? 0),
      }
      return
    }

    try {
      // 查询2205租赁负债
      const res2205 = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: ACCOUNT_CODE_2205 },
        _silent: true,
      } as any)
      const list2205: any[] = Array.isArray(res2205?.data ?? res2205)
        ? (res2205?.data ?? res2205)
        : (res2205?.data?.items ?? [])

      let unadjusted2205 = 0
      let audited2205 = 0
      let found2205 = false

      for (const item of list2205) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_2205)) {
          unadjusted2205 = Number(item.unadjusted_amount ?? 0)
          audited2205 = Number(item.audited_amount ?? 0)
          found2205 = true
        }
      }

      // 查询未确认融资费用
      const resFC = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: ACCOUNT_CODE_FINANCE_COST },
        _silent: true,
      } as any)
      const listFC: any[] = Array.isArray(resFC?.data ?? resFC)
        ? (resFC?.data ?? resFC)
        : (resFC?.data?.items ?? [])

      let unadjustedFinanceCost = 0
      let auditedFinanceCost = 0

      for (const item of listFC) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_FINANCE_COST)) {
          unadjustedFinanceCost = Number(item.unadjusted_amount ?? 0)
          auditedFinanceCost = Number(item.audited_amount ?? 0)
        }
      }

      tbData.value = { unadjusted2205, audited2205, unadjustedFinanceCost, auditedFinanceCost }

      if (!found2205) {
        ElMessage.warning('科目2205租赁负债未在试算表中找到，请先导入试算平衡表')
      }
    } catch {
      tbData.value = { unadjusted2205: 0, audited2205: 0, unadjustedFinanceCost: 0, auditedFinanceCost: 0 }
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
    tbData,
    renderMeta,
    sheetCache,
    // Accessors
    getResponse,
    getResponses,
    setValue,
    getSheet,
    // Save actions
    saveResponse,
    saveBatchResponses,
    // TB writeback (2205租赁负债 + 未确认融资费用)
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadTbData,
  }
}

export default useH9FormData
