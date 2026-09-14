/**
 * useK4FormData — K4 其他流动负债 selfLoad/checklist_responses/writebackTB(2245 负债口径)/TB取数
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文 + checklist_responses
 * - loadTbData(): 从 trial_balance 获取科目 2245 未审/审定数据
 * - writebackTB(): 审定数回写 trial_balance(2245) + EventBus 'substantive:adjudicated'
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K4-{sheet}-{field}"（如 "K4-1-audited-total", "K4-2-detail-total"）
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类方向相反）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface K4TbData {
  /** 2245其他流动负债 未审数 */
  unadjusted2245: number
  /** 2245其他流动负债 审定数 */
  audited2245: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：2245 其他流动负债（贷方/负债类） */
const ACCOUNT_CODE_2245 = '2245'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK4FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetPrefix: string
}) {
  const { wpId, projectId, sheetPrefix } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const allResponses = ref<Map<string, any>>(new Map())
  const tbData = ref<K4TbData>({ unadjusted2245: 0, audited2245: 0 })
  const renderMeta = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * 完整自加载入口：render-config → checklist_responses → TB。
   * bundle内嵌场景 htmlData 为 null 时自行调用。
   * 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'k4-other-current-liabilities' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 2. 从 sheets 数组构建 allResponses Map
      const sheetsArr = configData?.sheets ?? configData?.data?.sheets
      if (sheetsArr && Array.isArray(sheetsArr)) {
        const map = new Map<string, any>()
        for (const sheet of sheetsArr) {
          if (sheet.html_data?.allResponses) {
            for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
              map.set(k, v)
            }
          }
        }
        allResponses.value = map
      }

      // 3. 加载 checklist_responses（补充已持久化数据）
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      for (const r of responses) {
        if (r.item_id?.startsWith('K4-') || r.item_id?.startsWith('K4A-')) {
          allResponses.value.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }

      // 4. 加载 TB 数据
      await loadTbData()
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadTbData: 从 trial_balance 获取 2245 数据 ───────────────────────────

  /**
   * 从 trial_balance 获取科目 2245 的未审数和审定数。
   * 优先从 renderMeta seed 读取，否则请求 TB 端点。
   *
   * 科目：2245 其他流动负债（贷方/负债类）
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seededUnadj = renderMeta.value?.tb_values?.other_current_liabilities_2245_unadjusted
    const seededAudited = renderMeta.value?.tb_values?.other_current_liabilities_2245_audited
    if (seededUnadj != null) {
      tbData.value = {
        unadjusted2245: Number(seededUnadj) || 0,
        audited2245: Number(seededAudited) || 0,
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '2245' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted = 0
      let audited = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_2245)) {
          unadjusted += Number(item.unadjusted_amount ?? 0)
          audited += Number(item.audited_amount ?? 0)
          found = true
        }
      }

      tbData.value = { unadjusted2245: unadjusted, audited2245: audited }

      if (!found) {
        ElMessage.warning('科目2245其他流动负债未在试算表中找到，请先导入试算表')
      }
    } catch {
      tbData.value = { unadjusted2245: 0, audited2245: 0 }
    }
  }

  // ─── writebackTB（2245 其他流动负债 负债口径） ────────────────────────────────

  /**
   * 审定数回写 trial_balance：科目2245其他流动负债（贷方/负债类）。
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * ⚠️ 负债类2245！正数口径回写（v2 trial_balance 正数，无需取反）。
   * 负债类方向：期末=期初+贷方-借方
   *
   * Req 2.6: WHEN 审定数变化时 SHALL 回写trial_balance(2245)+发布'substantive:adjudicated'
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_2245,
        audited_amount: auditedAmount,
      })

      // EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_2245,
        auditedAmount,
        wpCode: 'K4',
        timestamp: Date.now(),
      })

      // 同步更新本地 tbData
      tbData.value.audited2245 = auditedAmount
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── Save core ─────────────────────────────────────────────────────────────

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

  // ─── saveResponse（单条立即保存） ──────────────────────────────────────────

  /**
   * 立即保存单个 checklist item。
   * @param itemId 如 "K4-1-audited-total"
   * @param value { conclusion?, remark? }
   */
  async function saveResponse(itemId: string, value: any): Promise<void> {
    // 取消该 item 的 debounce 定时器
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    _pendingItems.delete(itemId)

    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: existing.conclusion ?? null,
      remark: strVal ?? existing.remark ?? null,
    }
    if (typeof value === 'object' && value !== null) {
      if (value.conclusion !== undefined) updated.conclusion = value.conclusion
      if (value.remark !== undefined) updated.remark = value.remark
    }
    allResponses.value.set(itemId, updated)
    await _doSave([updated])
  }

  // ─── saveResponses（批量保存） ─────────────────────────────────────────────

  /**
   * 批量原子性保存多个 items（如审定表多行回写）。
   */
  async function saveResponses(items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }>): Promise<void> {
    const checklistItems: ChecklistItem[] = items.map(({ item_id, conclusion, remark }) => {
      // 取消 debounce
      const timer = _debounceTimers.get(item_id)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(item_id)
      }
      _pendingItems.delete(item_id)

      const existing = allResponses.value.get(item_id) || { item_id, conclusion: null, remark: null }
      const updated: ChecklistItem = {
        item_id,
        conclusion: conclusion !== undefined ? (conclusion ?? null) : (existing.conclusion ?? null),
        remark: remark !== undefined ? (remark ?? null) : (existing.remark ?? null),
      }
      allResponses.value.set(item_id, updated)
      return updated
    })

    await _doSave(checklistItems)
  }

  // ─── getResponse（读取单条） ───────────────────────────────────────────────

  /**
   * 从 allResponses Map 中获取指定 item 的值（尝试 JSON 解析 remark）。
   */
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

  // ─── debouncedSave（文本字段 debounce 2s） ────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
   * 适用于 textarea / 备注等文本字段。
   */
  function debouncedSave(itemId: string, data: Partial<ChecklistItem>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: data.conclusion !== undefined ? (data.conclusion ?? null) : (existing.conclusion ?? null),
      remark: data.remark !== undefined ? (data.remark ?? null) : (existing.remark ?? null),
    }
    allResponses.value.set(itemId, updated)
    _pendingItems.add(itemId)

    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)

    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([updated])
    }, DEBOUNCE_MS))
  }

  // ─── setTbValues（外部设置TB值，render策略seed回读） ────────────────────────

  /**
   * 外部设置 TB 值（从 render 策略 seed 或组件 watch 调用）。
   */
  function setTbValues(values: Partial<K4TbData>): void {
    if (values.unadjusted2245 != null) {
      tbData.value.unadjusted2245 = values.unadjusted2245
    }
    if (values.audited2245 != null) {
      tbData.value.audited2245 = values.audited2245
    }
  }

  // ─── Flush（组件卸载时确保无数据丢失） ─────────────────────────────────────

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
    allResponses,
    isLoading,
    tbData,
    renderMeta,
    // Actions
    selfLoad,
    saveResponse,
    saveResponses,
    getResponse,
    writebackTB,
    loadTbData,
    // Extras
    debouncedSave,
    setTbValues,
  }
}

export default useK4FormData
