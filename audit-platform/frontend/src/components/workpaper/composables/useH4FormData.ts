/**
 * useH4FormData — H4 工程物资底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.8
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1605工程物资，借方/资产类）
 * - selfLoad逻辑（render-config?force_component_type=h4-engineering-materials）
 * - TB自动取数 unadjusted_amount → 审定表未审数（1605）
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
  /** 科目1605工程物资 未审数（借方/资产类） */
  unadjusted1605: number
  /** 科目1605 审定数 */
  audited1605: number
  /** 科目1604在建工程 未审（期末） */
  unadjusted1604: number
  /** 科目1604 审定（期末） */
  audited1604: number
  /** 科目1604 期初余额 */
  opening1604: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 800
const ACCOUNT_CODE_1605 = '1605'
const ACCOUNT_CODE_1604 = '1604'
const ITEM_PREFIX = 'H4-'
const ITEM_PREFIX_A = 'H4A-'
const ITEM_PREFIX_LISTED = 'H4-listed'
const ITEM_PREFIX_SOE = 'H4-soe'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
}) {
  const { wpId, projectId } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<TbData>({
    unadjusted1605: 0,
    audited1605: 0,
    unadjusted1604: 0,
    audited1604: 0,
    opening1604: 0,
  })
  /** 供 H4-1 inject 的扁平 TB 键（与 render 策略 tb_values 对齐） */
  const tbValues = ref<Record<string, number>>({})
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

  // ─── writebackTrialBalance（科目1605，借方/资产类） ─────────────────────────

  /**
   * 审定数回写 trial_balance：科目1605工程物资（借方/资产类）。
   * 回写成功后发布 EventBus 事件通知其他底稿（附注/报表）。
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1605,
        audited_amount: auditedAmount,
      })

      // 发布 EventBus 事件通知其他底稿（附注/H2在建工程等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'H4',
          accountCode: ACCOUNT_CODE_1605,
          auditedAmount,
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
        params: { force_component_type: 'h4-engineering-materials' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 缓存各sheet html_data，并合并 tb_values / responses_snapshot
      const rootTb = configData?.tb_values ?? configData?.html_data?.tb_values ?? configData?.data?.tb_values
      if (rootTb) _applyTbValues(rootTb as Record<string, number>)

      for (const s of configData?.sheets ?? configData?.data?.sheets ?? []) {
        const name = s.sheet_name || s.name || 'default'
        sheetCache.value[name] = s.html_data ?? s
        const hd = s.html_data ?? s
        if (hd?.tb_values) _applyTbValues(hd.tb_values)
        if (hd?.responses_snapshot) mergeHtmlData(hd)
      }

      // 2. 加载 checklist_responses
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (
          r.item_id?.startsWith(ITEM_PREFIX)
          || r.item_id?.startsWith(ITEM_PREFIX_A)
          || r.item_id?.startsWith(ITEM_PREFIX_LISTED)
          || r.item_id?.startsWith(ITEM_PREFIX_SOE)
        ) {
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

  /**
   * 从父级 htmlData / render 策略输出合并 responses + tb_values（不覆盖已有本地编辑时可先清空）
   */
  function mergeHtmlData(htmlData: Record<string, any> | null | undefined): void {
    if (!htmlData || typeof htmlData !== 'object') return
    const map = new Map(allResponses.value)
    const snap = htmlData.responses_snapshot ?? htmlData.allResponses
    if (snap && typeof snap === 'object') {
      for (const [k, v] of Object.entries(snap)) map.set(k, v as ChecklistItem)
    }
    allResponses.value = map
    if (htmlData.tb_values && typeof htmlData.tb_values === 'object') {
      _applyTbValues(htmlData.tb_values as Record<string, number>)
    }
    renderMeta.value = { ...renderMeta.value, ...htmlData }
  }

  function _applyTbValues(tb: Record<string, number>): void {
    tbValues.value = { ...tbValues.value, ...tb }
    tbData.value = {
      unadjusted1605: Number(tb.eng_mat_1605_unadjusted) || tbData.value.unadjusted1605,
      audited1605: Number(tb.eng_mat_1605_audited) || tbData.value.audited1605,
      unadjusted1604:
        Number(tb.cip_1604_unadjusted ?? tb.cip_unadjusted) || tbData.value.unadjusted1604,
      audited1604:
        Number(tb.cip_1604_audited ?? tb.cip_audited) || tbData.value.audited1604,
      opening1604:
        Number(tb.cip_1604_unadjusted_opening) || tbData.value.opening1604,
    }
  }

  // ─── loadAllResponses（外部可调的显式加载） ─────────────────────────────────

  /**
   * 从 checklist_responses 端点加载全部 H4- 前缀数据到 allResponses Map。
   */
  async function loadAllResponses(): Promise<Map<string, ChecklistItem>> {
    if (!wpId.value) return allResponses.value
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (
          r.item_id?.startsWith(ITEM_PREFIX)
          || r.item_id?.startsWith(ITEM_PREFIX_A)
          || r.item_id?.startsWith(ITEM_PREFIX_LISTED)
          || r.item_id?.startsWith(ITEM_PREFIX_SOE)
        ) {
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
      ElMessage.warning('H4数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── TB自动取数 unadjusted_amount（1605） ──────────────────────────────────

  /**
   * 从 trial_balance 自动获取科目 1605 的未审数和审定数。
   * 填入审定表"未审数"列（只读取数）。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config / 已合并的 tb_values 取值
    const seeded = (renderMeta.value?.tb_values ?? tbValues.value) as Record<string, number> | undefined
    if (seeded && (seeded.eng_mat_1605_unadjusted != null || seeded.cip_1604_unadjusted != null || seeded.cip_unadjusted != null)) {
      _applyTbValues(seeded)
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '160' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted1605 = 0
      let audited1605 = 0
      let unadjusted1604 = 0
      let audited1604 = 0
      let found5 = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1605)) {
          unadjusted1605 += Number(item.unadjusted_amount ?? 0)
          audited1605 += Number(item.audited_amount ?? 0)
          found5 = true
        }
        if (code.startsWith(ACCOUNT_CODE_1604)) {
          unadjusted1604 += Number(item.unadjusted_amount ?? 0)
          audited1604 += Number(item.audited_amount ?? 0)
        }
      }

      tbData.value = {
        unadjusted1605,
        audited1605,
        unadjusted1604,
        audited1604,
        opening1604: tbData.value.opening1604,
      }
      tbValues.value = {
        ...tbValues.value,
        eng_mat_1605_unadjusted: unadjusted1605,
        eng_mat_1605_audited: audited1605,
        cip_1604_unadjusted: unadjusted1604,
        cip_1604_audited: audited1604,
      }

      if (!found5) {
        ElMessage.warning('科目1605工程物资未在试算表中找到，未审数显示为0')
      }
    } catch {
      tbData.value = {
        unadjusted1605: 0,
        audited1605: 0,
        unadjusted1604: 0,
        audited1604: 0,
        opening1604: 0,
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

  /** 切换双模式前刷新未落库的防抖保存 */
  async function flushPending(): Promise<void> {
    _flushPending()
    // 给 in-flight PUT 一拍缓冲
    await new Promise((r) => setTimeout(r, 50))
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
    tbValues,
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
    flushPending,
    // TB writeback
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadTbData,
    mergeHtmlData,
  }
}

export default useH4FormData
