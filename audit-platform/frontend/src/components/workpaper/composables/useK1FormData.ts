/**
 * useK1FormData — K1 其他应收款 selfLoad/checklist_responses/writebackTB(1221+坏账准备)
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.8
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K1-{sheet}-{field}"（如 "K1-1-audited-receivable", "K1-3-bad-debt-end"）
 * - writebackTB: 审定数回写 trial_balance 双科目
 *     - 1221 其他应收款（借方/资产类）
 *     - 坏账准备（贷方/资产备抵类）
 * - EventBus: 回写成功后发布 'substantive:adjudicated'
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 科目：1221 其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseK1FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  year?: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：1221 其他应收款（借方/资产类） */
const ACCOUNT_CODE_1221 = '1221'
/** 科目：坏账准备（贷方/资产备抵类） */
const ACCOUNT_CODE_BAD_DEBT = '1231'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1FormData(opts: UseK1FormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * selfLoad: 当组件在bundle内嵌时无htmlData，自行加载render-config。
   * 用 _silent:true 避免触发全局404弹窗。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=k1-other-receivables`,
        { _silent: true } as any,
      )
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 K1 数据（item_id 前缀 "K1-"）
   */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('K1-') || r.item_id?.startsWith('K1A-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('K1数据加载失败，可手动填写')
    }
  }

  /**
   * 统一加载入口：selfLoad + loadResponses 并行
   */
  async function loadData(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([selfLoad(), loadResponses()])
    } finally {
      isLoading.value = false
    }
  }

  // ─── Save core ─────────────────────────────────────────────────────────────

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

  // ─── save (单字段立即保存) ─────────────────────────────────────────────────

  /**
   * 立即保存单个字段（结论/状态/选择类字段）
   * @param itemId - 如 "K1-1-audited-receivable"
   * @param value - { conclusion?, remark? }
   */
  async function save(itemId: string, value: { conclusion?: string; remark?: string }): Promise<void> {
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
      ...(value.conclusion !== undefined ? { conclusion: value.conclusion } : {}),
      ...(value.remark !== undefined ? { remark: value.remark } : {}),
    }
    allResponses.value.set(itemId, updated)

    await _doSave([updated])
  }

  // ─── saveBatch (批量保存) ──────────────────────────────────────────────────

  /**
   * 批量保存多个 items（跨字段同时变更场景，如审定表多行回写）
   */
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

  // ─── debouncedSave (文本字段 debounce 2s) ──────────────────────────────────

  /**
   * debounce 2s 文本字段保存（per item_id 独立计时器）
   */
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
    }, DEBOUNCE_MS)
    _debounceTimers.set(itemId, timer)
  }

  // ─── writebackTB (双科目回写: 1221其他应收款 + 坏账准备) ──────────────────

  /**
   * 回写审定数到 trial_balance 双科目：
   * - 1221 其他应收款（借方/资产类）
   * - 坏账准备（贷方/资产备抵类）
   *
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新等。
   * Req 2.8: WHEN 审定数变化时 SHALL 回写trial_balance(1221+坏账准备)+发布'substantive:adjudicated'
   */
  async function writebackTB(auditedReceivable: number, auditedBadDebt: number): Promise<void> {
    if (!projectId.value) return
    try {
      // 1. 回写 1221 其他应收款
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_1221,
        audited_amount: auditedReceivable,
      })
      // 2. 回写 坏账准备
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_BAD_DEBT,
        audited_amount: auditedBadDebt,
      })

      // 3. EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_1221,
        auditedAmount: auditedReceivable,
        wpCode: 'K1',
        timestamp: Date.now(),
      })
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

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    isLoading,
    allResponses,
    // Actions
    loadData,
    loadResponses,
    save,
    saveBatch,
    debouncedSave,
    writebackTB,
  }
}

export default useK1FormData
