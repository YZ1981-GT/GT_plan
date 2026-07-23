/**
 * useI2FormData — I2 开发支出底稿数据加载/保存/selfLoad/writebackTB(1717)
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.5
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTrialBalance（科目1717开发支出 借方/资产类）
 * - selfLoad逻辑（render-config?force_component_type=i2-development-expenditure）
 * - TB自动取数 unadjusted_amount → 审定表未审数（1717）
 * - checklist_responses 前缀 "I2-{sheet}-{field}"
 * - useVersionTrail auto-snapshot 由主入口集成（本composable不直接引入）
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

export interface I2TbData {
  /** 科目1717开发支出 未审数（借方/资产类） */
  unadjusted1717: number
  /** 科目1717 审定数 */
  audited1717: number
  /** 科目1717 AJE调整 */
  aje1717: number
  /** 科目1717 RJE调整 */
  rje1717: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1717 = '1717'
const ITEM_PREFIX = 'I2-'
const ITEM_PREFIX_A = 'I2A-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  year?: Ref<number | string>
}) {
  const { wpId, projectId } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const lastSavedAt = ref<string | null>(null)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<I2TbData>({
    unadjusted1717: 0,
    audited1717: 0,
    aje1717: 0,
    rje1717: 0,
  })
  const renderMeta = ref<Record<string, any>>({})
  const sheetCache = ref<Record<string, any>>({})
  /** formData: 通用reactive存储，供各sheet composable读写 */
  const formData = ref<Record<string, any>>({})

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

  // ─── saveResponse (single item, immediate) ─────────────────────────────────

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

  // ─── writebackTrialBalance（科目1717开发支出） ─────────────────────────────

  /**
   * 审定数回写 trial_balance：科目1717开发支出（借方/资产类）。
   * 回写成功后发布 'substantive:adjudicated' 事件通知其他底稿（附注/报表/I6联动等）。
   * Req 2.5: writebackTB(1717)
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1717,
        audited_amount: auditedAmount,
      })

      // 更新本地 tbData
      tbData.value.audited1717 = auditedAmount

      // 发布 EventBus 事件通知其他底稿（I6联动/附注/报表等）
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: {
          wpCode: 'I2',
          accountCodes: [ACCOUNT_CODE_1717],
          audited1717: auditedAmount,
        },
      }))
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── selfLoad（render-config + checklist_responses） ────────────────────────

  /**
   * 从 render-config 加载数据（当 htmlData prop 为 null 时自行调用）。
   * Req 1.9: selfLoad支持（bundle内嵌场景htmlData为null）
   * selfLoad 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'i2-development-expenditure' },
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
      await loadAllResponses()

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
   * 从 checklist_responses 端点加载全部 I2- / I2A- 前缀数据到 allResponses Map。
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
      ElMessage.warning('I2数据加载失败，可手动填写')
      return allResponses.value
    }
  }

  // ─── saveResponses（按sheet保存，对外接口） ─────────────────────────────────

  /**
   * 保存指定 sheetCode 下的全部数据。
   * @param sheetCode - 如 "1"(审定表)/"2"(明细表)/"6"(CAS6)
   * @param data - key-value 对象，key 会拼接为 "I2-{sheetCode}-{key}"
   */
  async function saveResponses(sheetCode: string, data: Record<string, any>): Promise<void> {
    const items: { itemId: string; value: any }[] = []
    for (const [key, value] of Object.entries(data)) {
      const itemId = `${ITEM_PREFIX}${sheetCode}-${key}`
      items.push({ itemId, value })
    }
    if (items.length > 0) {
      await saveBatchResponses(items)
    }
  }

  // ─── loadResponses（按sheet加载，对外接口） ─────────────────────────────────

  /**
   * 获取指定 sheetCode 下的全部已保存数据。
   * @param sheetCode - 如 "1"/"2"/"6"
   * @returns key-value 对象（key 已去掉 "I2-{sheetCode}-" 前缀）
   */
  function loadResponses(sheetCode: string): Record<string, any> {
    const prefix = `${ITEM_PREFIX}${sheetCode}-`
    const result: Record<string, any> = {}
    for (const [key, item] of allResponses.value) {
      if (key.startsWith(prefix)) {
        const fieldName = key.slice(prefix.length)
        const raw = item.remark ?? item.conclusion
        if (raw != null) {
          try {
            result[fieldName] = JSON.parse(raw)
          } catch {
            result[fieldName] = raw
          }
        }
      }
    }
    return result
  }

  // ─── TB自动取数 unadjusted_amount（1717） ──────────────────────────────────

  /**
   * 从 trial_balance 自动获取科目 1717 的未审数和审定数。
   * 优先从 render-config seed 取值（后端 render 策略已查询并注入 html_data）。
   */
  async function loadTbData(): Promise<void> {
    await _loadTbData()
  }

  async function _loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（后端 render 策略注入 tb_values）
    const seeds = renderMeta.value?.tb_values
    if (seeds?.dev_1717_unadjusted != null) {
      tbData.value = {
        unadjusted1717: Number(seeds.dev_1717_unadjusted) || 0,
        audited1717: Number(seeds.dev_1717_audited ?? 0),
        aje1717: Number(seeds.dev_1717_aje ?? 0),
        rje1717: Number(seeds.dev_1717_rje ?? 0),
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '1717' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted1717 = 0
      let audited1717 = 0
      let aje1717 = 0
      let rje1717 = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1717)) {
          unadjusted1717 += Number(item.unadjusted_amount ?? 0)
          audited1717 += Number(item.audited_amount ?? 0)
          aje1717 += Number(item.aje_adjustment ?? 0)
          rje1717 += Number(item.rje_adjustment ?? 0)
          found = true
        }
      }

      tbData.value = { unadjusted1717, audited1717, aje1717, rje1717 }

      if (!found) {
        ElMessage.warning('科目1717开发支出未在试算表中找到，未审数显示为0')
      }
    } catch {
      tbData.value = { unadjusted1717: 0, audited1717: 0, aje1717: 0, rje1717: 0 }
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
    formData,
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
    saveResponses,
    loadResponses,
    // TB writeback
    writebackTrialBalance,
    // Load
    selfLoad,
    loadAllResponses,
    loadTbData,
  }
}

// ─── fetchI2TbData / persistI2TbData（独立轻量版，供 I2TabAdjudication / GtI2 selfLoad 复用） ──
// 与 _loadTbData 同一 API 模式；不依赖完整 composable 实例，兼容 http(axios) 与 api(已解包) 两种客户端。

/** 从 trial-balance 端点取科目 1717 未审/审定/AJE/RJE（纯函数，便于测试） */
export async function fetchI2TbData(
  httpClient: { get: (url: string, config?: any) => Promise<any> },
  projectId: string,
): Promise<I2TbData> {
  const empty: I2TbData = { unadjusted1717: 0, audited1717: 0, aje1717: 0, rje1717: 0 }
  if (!projectId) return empty
  try {
    const res = await httpClient.get(`/projects/${projectId}/trial-balance`, {
      params: { account_prefix: ACCOUNT_CODE_1717 },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

    let unadjusted1717 = 0
    let audited1717 = 0
    let aje1717 = 0
    let rje1717 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith(ACCOUNT_CODE_1717)) {
        unadjusted1717 += Number(item.unadjusted_amount ?? 0)
        audited1717 += Number(item.audited_amount ?? 0)
        aje1717 += Number(item.aje_adjustment ?? 0)
        rje1717 += Number(item.rje_adjustment ?? 0)
      }
    }
    return { unadjusted1717, audited1717, aje1717, rje1717 }
  } catch {
    return empty
  }
}

/** 将取得的 TB 数据写入 'I2-tb-data'（I2-1 审定表消费），saveResponse 的乐观更新会同步刷新 UI */
export function persistI2TbData(
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>,
  tb: I2TbData,
): Promise<void> {
  return saveResponse('I2-1', { 'I2-tb-data': JSON.stringify(tb) })
}

export default useI2FormData
