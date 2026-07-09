/**
 * useH6FormData — H6 固定资产清理底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.8
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1606固定资产清理，借方/资产类，过渡科目）
 * - selfLoad逻辑（render-config?force_component_type=h6-asset-disposal-clearing）
 * - TB自动取数 unadjusted_amount → 审定表未审数（1606）
 * - 过渡科目规则：期末余额应为0
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

export interface TbData {
  /** 科目1606固定资产清理 未审数（借方/资产类，过渡科目） */
  unadjusted1606: number
  /** 科目1606 审定数 */
  audited1606: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1606 = '1606'
const ITEM_PREFIX = 'H6-'
const ITEM_PREFIX_A = 'H6A-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
}) {
  const { wpId, projectId } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<TbData>({ unadjusted1606: 0, audited1606: 0 })
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
   * 用于跨字段同时变更场景（如审定表回写多行/跨sheet联动批量更新）。
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

  // ─── writebackTrialBalance（科目1606，借方/资产类，过渡科目） ────────────────

  /**
   * 审定数回写 trial_balance：科目1606固定资产清理（借方/资产类，过渡科目）。
   * 过渡科目规则：期末余额应为0（清理完毕全部结转）。
   * 回写成功后发布 EventBus 事件通知其他底稿（附注/H10资产处置损益等）。
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1606,
        audited_amount: auditedAmount,
      })

      // 发布 EventBus 事件通知其他底稿（附注/H10等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'H6',
          accountCode: ACCOUNT_CODE_1606,
          auditedAmount,
          isTransitAccount: true,
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
        params: { force_component_type: 'h6-asset-disposal-clearing' },
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

      // 3. TB自动取数
      await _loadTbData()
    } catch {
      // selfLoad 404 静默处理，显示空状态
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadAllResponses（外部可调的显式加载） ─────────────────────────────────

  /**
   * 从 checklist_responses 端点加载全部 H6- 前缀数据到 allResponses Map。
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
      ElMessage.warning('H6数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── TB自动取数 unadjusted_amount（1606） ──────────────────────────────────

  /**
   * 从 trial_balance 自动获取科目 1606 的未审数和审定数。
   * 填入审定表"未审数"列（只读取数）。
   * 1606 固定资产清理：借方/资产类，过渡科目，期末余额应为0。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seeded = renderMeta.value?.tb_values?.disposal_1606_unadjusted
    if (seeded != null) {
      tbData.value = {
        unadjusted1606: Number(seeded) || 0,
        audited1606: Number(renderMeta.value?.tb_values?.disposal_1606_audited ?? 0),
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: ACCOUNT_CODE_1606 },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted1606 = 0
      let audited1606 = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1606)) {
          unadjusted1606 = Number(item.unadjusted_amount ?? 0)
          audited1606 = Number(item.audited_amount ?? 0)
          found = true
        }
      }

      tbData.value = { unadjusted1606, audited1606 }

      if (!found) {
        ElMessage.warning('科目1606固定资产清理未在试算表中找到，请先导入试算平衡表')
      }
    } catch {
      tbData.value = { unadjusted1606: 0, audited1606: 0 }
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
    // TB writeback
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadTbData,
  }
}

export default useH6FormData
