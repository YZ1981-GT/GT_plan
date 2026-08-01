/**
 * useD6FormData — D6 合同资产数据加载/debounce保存/即时保存/批量保存
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 3.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 D6-* 数据
 * - debounce 2s 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - trial_balance 回写：writebackTrialBalance（科目1141合同资产）
 * - selfLoad逻辑（render-config?force_component_type=d6-contract-assets）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseD6FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData?: Ref<any>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6FormData(options: UseD6FormDataOptions) {
  const { wpId, projectId, htmlData } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()

  // ─── Load ────────────────────────────────────────────────────────────────

  /** 从 checklist-responses 端点加载全部 D6 响应 */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('D6-') || r.item_id?.startsWith('D6A-') || r.item_id?.startsWith('D6-proc')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('D6数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当 htmlData prop 为 null（bundle 内嵌场景），
   * 自行调 render-config?force_component_type=d6-contract-assets 加载数据。
   * 响应结构: res.data.data.sheets[0].html_data.responses (ResponseWrapperMiddleware 信封)
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
      await api.get(
        `/api/workpapers/${wpId.value}/render-config`,
        { params: { force_component_type: 'd6-contract-assets' }, _silent: true } as any,
      )
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist-responses 加载数据
    }
  }

  /** 统一加载入口 */
  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      // 如果有 htmlData 则直接用，否则走 API
      if (htmlData?.value?.responses) {
        await selfLoad()
      } else {
        await Promise.all([loadResponses(), selfLoad()])
      }
    } finally {
      isLoading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  /** 内部保存逻辑 — PUT 批量保存到 checklist-responses */
  async function _doSave(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
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

    await _doSave([updated])
  }

  /** 批量保存多个 items */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    // 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失
    //    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。
    //    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。
    const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of deduped) {
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

    await _doSave(toSave)
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
      _doSave([updated])
    }, 2000)
    _debounceTimers.set(itemId, timer)
  }

  // ─── trial_balance 回写 ──────────────────────────────────────────────────

  /** 回写审定数到 trial_balance（科目 1141 合同资产）并发布 EventBus
   *
   * 合同资产科目为 1141；`report_config` 报表行 BS-011 四准则一致。
   * 原 `1402` 是在途物资（存货类），属误用。
   */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: '1141',
        audited_amount: auditedAmount,
      })
      // 发布 EventBus 通知审定数变更
      try {
        window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
          detail: { wpCode: 'D6', accountCode: '1141', auditedAmount },
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
        _doSave(items)
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

export default useD6FormData
