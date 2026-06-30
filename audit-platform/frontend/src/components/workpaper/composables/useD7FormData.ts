/**
 * useD7FormData — D7 合同负债数据加载/debounce保存/即时保存/批量保存
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 3.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 D7-* 数据
 * - debounce 2s 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - trial_balance 回写：writebackTrialBalance（科目2205合同负债，贷方/负债类）
 * - selfLoad逻辑（render-config?force_component_type=d7-contract-liabilities）
 *
 * Requirements: 1.8, 3.6, 20.5, 20.7, 20.8
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseD7FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData?: Ref<any>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7FormData(options: UseD7FormDataOptions) {
  const { wpId, projectId, htmlData } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()

  // ─── Load ────────────────────────────────────────────────────────────────

  /** 从 checklist-responses 端点加载全部 D7 响应 */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await http.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res.data) ? res.data : (res.data?.data ?? res.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('D7-') || r.item_id?.startsWith('D7A-') || r.item_id?.startsWith('D7-note-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('D7数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当 htmlData prop 为 null（bundle 内嵌场景），
   * 自行调 render-config?force_component_type=d7-contract-liabilities 加载数据。
   * 响应结构: res.data.sheets[0].html_data.responses (ResponseWrapperMiddleware 信封已被 http 拦截器解包)
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    // 如果已有 htmlData 中包含 responses，则直接使用
    if (htmlData?.value?.responses) {
      const map = new Map<string, ChecklistResponse>()
      for (const r of htmlData.value.responses) {
        map.set(r.item_id, {
          item_id: r.item_id,
          conclusion: r.conclusion ?? null,
          remark: r.remark ?? null,
        })
      }
      allResponses.value = map
      return
    }
    try {
      const res = await http.get(
        `/api/workpapers/${wpId.value}/render-config`,
        { params: { force_component_type: 'd7-contract-liabilities' }, _silent: true } as any,
      )
      const data = res.data?.data || res.data
      if (data?.sheets?.[0]?.html_data?.responses) {
        const map = new Map<string, ChecklistResponse>()
        for (const r of data.sheets[0].html_data.responses) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
        allResponses.value = map
      }
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist-responses 加载数据
    }
  }

  /** 统一加载入口 */
  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      if (htmlData?.value?.responses) {
        // 有 htmlData 直接用
        await selfLoad()
      } else {
        // 并行：从 checklist-responses 加载 + selfLoad 获取 render 数据
        await Promise.all([loadResponses(), selfLoad()])
      }
    } finally {
      isLoading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  /** 内部保存逻辑 — PUT 单条 response */
  async function _doSave(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
    if (!wpId.value || !itemId) return
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses/${itemId}`, {
        item_id: itemId,
        conclusion: data.conclusion ?? null,
        remark: data.remark ?? null,
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  /** 内部批量保存逻辑 — PUT 多条 responses */
  async function _doSaveBatch(items: ChecklistResponse[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  /** 立即保存指定 item（结论/状态/选择类字段触发） */
  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
    // 取消该 item 的 debounce 定时器
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    _pendingItems.delete(itemId)

    // 合并到 allResponses
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)

    await _doSave(itemId, updated)
  }

  /** 批量保存多个 items */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of items) {
      // 取消 debounce
      const timer = _debounceTimers.get(itemId)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(itemId)
      }
      _pendingItems.delete(itemId)

      const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const updated: ChecklistResponse = {
        ...existing,
        ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
        ...(data.remark !== undefined ? { remark: data.remark } : {}),
      }
      allResponses.value.set(itemId, updated)
      toSave.push(updated)
    }

    await _doSaveBatch(toSave)
  }

  /** debounce 2s 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    // 合并到 allResponses
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    _pendingItems.add(itemId)

    // 重置该 item 的定时器
    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      _doSave(itemId, updated)
    }, 2000)
    _debounceTimers.set(itemId, timer)
  }

  // ─── trial_balance 回写 ──────────────────────────────────────────────────

  /**
   * 回写审定数到 trial_balance（科目 2205 合同负债，贷方科目/负债类）
   * 并发布 EventBus 'substantive:adjudicated' 事件通知其他组件
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await http.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: '2205',
        audited_amount: auditedAmount,
      })
      // 发布 EventBus 通知审定数变更
      try {
        window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
          detail: { wpCode: 'D7', accountCode: '2205', auditedAmount },
        }))
      } catch { /* EventBus publish 失败不阻塞 */ }
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────

  function _flushPending(): void {
    // 清除所有 debounce 定时器
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    // 保存所有 pending items
    if (_pendingItems.size > 0) {
      const items: ChecklistResponse[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) {
        _doSaveBatch(items)
      }
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  return {
    allResponses,
    isLoading,
    loadAll,
    saveImmediate,
    saveBatch,
    debouncedSave,
    writebackTrialBalance,
  }
}

export default useD7FormData
