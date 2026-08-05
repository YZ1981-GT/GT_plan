/**
 * useH8FormData — H8 使用权资产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.7
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（使用权资产原值 借方/资产类 + 累计折旧 贷方/备抵类）
 * - selfLoad逻辑（render-config?force_component_type=h8-right-of-use-assets）
 * - TB自动取数 unadjusted_amount → 审定表未审数（原值+累计折旧）
 * - CAS21特有：H8=H9初始计量+初始直接费用-租赁激励
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { h8Scope } from './hCycleAccountScope'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface TbData {
  /** 使用权资产原值 未审数（借方/资产类） */
  unadjustedCost: number
  /** 使用权资产原值 审定数 */
  auditedCost: number
  /** 累计折旧 未审数（贷方/备抵类） */
  unadjustedAccDep: number
  /** 累计折旧 审定数 */
  auditedAccDep: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/**
 * 🔴 科目码单一真源 = `hCycleAccountScope.h8Scope`（原值 1641 / 累计折旧 1642）。
 * 历史实现写死 `1901`（待处理财产损溢）与 `1902` → TB 取数与回写全部落在错科目上。
 * 运行态优先取 render 下发的 `tb_source_codes`，常量只作兜底。
 */
const FALLBACK_ROU_COST_CODE = h8Scope.def.slotFallbacks.gross[0]
const FALLBACK_ROU_DEP_CODE = h8Scope.def.slotFallbacks.accum_dep[0]
/** render `tb_values` 键前缀（与后端 `H8_SLOT_KEY_PREFIX` 逐字对应） */
const TB_KEY_COST = 'rou_asset'
const TB_KEY_DEP = 'rou_dep'
const ITEM_PREFIX = 'H8-'
const ITEM_PREFIX_A = 'H8A-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8FormData(params: {
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
    unadjustedCost: 0,
    auditedCost: 0,
    unadjustedAccDep: 0,
    auditedAccDep: 0,
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
   * 用于跨字段同时变更场景（如审定表回写多行/跨sheet联动/H9联动批量更新）。
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

  // ─── writebackTrialBalance（使用权资产原值 + 累计折旧） ─────────────────────

  /**
   * 审定数回写 trial_balance：
   * - 使用权资产原值（借方/资产类）
   * - 累计折旧（贷方/备抵类）
   *
   * 审定数变化时回写TB并发布 'substantive:adjudicated' EventBus事件。
   * CAS21特有：H8与H9强联动，回写后通知H9底稿。
   *
   * 🔴 目标科目走 scope（历史往 `1901` 写审定数会污染 K2 其他流动资产）。
   */
  async function writebackTrialBalance(
    auditedAmountCost: number,
    auditedAmountAccDep?: number
  ): Promise<void> {
    if (!projectId.value) return
    const costCode = _costCode()
    try {
      // 回写使用权资产原值
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: costCode,
        audited_amount: auditedAmountCost,
      })

      // 回写累计折旧（如果提供）
      if (auditedAmountAccDep != null) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: _depCode(),
          audited_amount: auditedAmountAccDep,
        })
      }

      // 发布 EventBus 事件通知其他底稿（附注/H9租赁负债/报表等）
      eventBus.emit('substantive:adjudicated', {
        wpCode: 'H8',
        accountCode: costCode,
        auditedAmount: auditedAmountCost,
        adjudicatedAmount: auditedAmountCost,
        auditedAmountAccDep: auditedAmountAccDep ?? null,
      })
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
        params: { force_component_type: 'h8-right-of-use-assets' },
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

      // 3. TB自动取数（原值 + 累计折旧）
      await _loadTbData()
    } catch {
      // selfLoad 404 静默处理，显示空状态
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadAllResponses（外部可调的显式加载） ─────────────────────────────────

  /**
   * 从 checklist_responses 端点加载全部 H8- 前缀数据到 allResponses Map。
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
      ElMessage.warning('H8数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── TB自动取数 unadjusted_amount（原值 + 累计折旧） ───────────────────────

  /**
   * 从 trial_balance 自动获取使用权资产原值与累计折旧的未审数和审定数。
   * 填入审定表"未审数"列（只读取数）。
   * 原值：借方/资产类（期末=期初+借-贷）
   * 累计折旧：贷方/备抵类（期末=期初+贷-借）
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  /** 运行态科目码：溯源优先 → scope 兜底 */
  function _costCode(): string {
    return h8Scope.slotCodes(renderMeta.value?.tb_source_codes, 'gross')[0] || FALLBACK_ROU_COST_CODE
  }

  function _depCode(): string {
    return h8Scope.slotCodes(renderMeta.value?.tb_source_codes, 'accum_dep')[0] || FALLBACK_ROU_DEP_CODE
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（键与后端 H8_SLOT_KEY_PREFIX 逐字对应）
    const tv = renderMeta.value?.tb_values
    const seededCost = tv?.[`${TB_KEY_COST}_unadjusted`]
    if (seededCost != null) {
      tbData.value = {
        unadjustedCost: Number(seededCost) || 0,
        auditedCost: Number(tv?.[`${TB_KEY_COST}_audited`] ?? 0),
        unadjustedAccDep: Number(tv?.[`${TB_KEY_DEP}_unadjusted`] ?? 0),
        auditedAccDep: Number(tv?.[`${TB_KEY_DEP}_audited`] ?? 0),
      }
      return
    }

    const costCode = _costCode()
    const depCode = _depCode()

    try {
      // 查询使用权资产原值
      const resCost = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: costCode },
        _silent: true,
      } as any)
      const listCost: any[] = Array.isArray(resCost?.data ?? resCost)
        ? (resCost?.data ?? resCost)
        : (resCost?.data?.items ?? [])

      let unadjustedCost = 0
      let auditedCost = 0
      let foundCost = false

      for (const item of listCost) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(costCode)) {
          unadjustedCost = Number(item.unadjusted_amount ?? 0)
          auditedCost = Number(item.audited_amount ?? 0)
          foundCost = true
        }
      }

      // 查询累计折旧
      const resAccDep = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: depCode },
        _silent: true,
      } as any)
      const listAccDep: any[] = Array.isArray(resAccDep?.data ?? resAccDep)
        ? (resAccDep?.data ?? resAccDep)
        : (resAccDep?.data?.items ?? [])

      let unadjustedAccDep = 0
      let auditedAccDep = 0

      for (const item of listAccDep) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(depCode)) {
          unadjustedAccDep = Number(item.unadjusted_amount ?? 0)
          auditedAccDep = Number(item.audited_amount ?? 0)
        }
      }

      tbData.value = { unadjustedCost, auditedCost, unadjustedAccDep, auditedAccDep }

      if (!foundCost) {
        ElMessage.warning(
          `科目${costCode}使用权资产未在试算表中找到，请先导入试算平衡表`,
        )
      }
    } catch {
      tbData.value = { unadjustedCost: 0, auditedCost: 0, unadjustedAccDep: 0, auditedAccDep: 0 }
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
    // TB writeback (原值 + 累计折旧)
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadTbData,
  }
}

export default useH8FormData
