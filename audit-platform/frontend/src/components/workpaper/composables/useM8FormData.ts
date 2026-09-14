/**
 * useM8FormData — M8 一般风险准备数据加载/debounce保存/即时保存/TB回写
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "M8-{sheet}-{field}"（如 "M8-1-adjudicated-amount", "M8-2-detail-total"）
 * - writebackTB(4104): 审定数回写 trial_balance 科目 4104 一般风险准备
 * - EventBus: 回写成功后发布 'substantive:adjudicated'
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * ─── 权益类方向铁律 ───
 * 科目：4104 一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业从净利润中计提时贷方增加，转回/使用时借方减少
 * 回写TB用期末余额口径（audited_amount = 审定期末余额）
 * ─── 金融企业专属 ───
 * 一般风险准备仅适用于金融企业（银行/证券/保险），非金融企业不适用
 * 原则上不低于风险资产期末余额的1.5%
 * ─────────────────────────────────────────────────
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

export interface UseM8FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string> | string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'M8-'
const ACCOUNT_CODE = '4104' // 一般风险准备（贷方/权益类！金融企业专属）

// ─── Composable ──────────────────────────────────────────────────────────────

export function useM8FormData(options: UseM8FormDataOptions) {
  const { wpId, projectId } = options

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
        `/api/workpapers/${wpId.value}/render-config?force_component_type=m8-general-risk-reserve`,
        { _silent: true } as any,
      )
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 M8 数据（item_id 前缀 "M8-"）
   */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(ITEM_PREFIX)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('M8数据加载失败，可手动填写')
    }
  }

  // ─── loadData（统一加载入口） ─────────────────────────────────────────────

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
      // 发送自定义事件（EventBus集成）
      window.dispatchEvent(new CustomEvent('m8:save-items'))
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  // ─── getField / setField（便捷接口） ──────────────────────────────────────

  /**
   * 获取指定 sheet + field 的值
   * @param sheet - 如 "1", "2", "3", "4"（不含M8-前缀，最终item_id为 "M8-1-xxx"）
   * @param field - 如 "adjudicated-amount", "detail-total", "risk-provision"
   * @returns 存储的值（conclusion 字段）
   */
  function getField(sheet: string, field: string): any {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const resp = allResponses.value.get(itemId)
    if (!resp) return null
    // 尝试 JSON 解析（支持存储对象/数组）
    if (resp.conclusion) {
      try {
        return JSON.parse(resp.conclusion)
      } catch {
        return resp.conclusion
      }
    }
    return null
  }

  /**
   * 设置指定 sheet + field 的值（即时保存）
   * @param sheet - 如 "1", "2", "3", "4"
   * @param field - 如 "adjudicated-amount", "detail-total", "risk-provision"
   * @param value - 要存储的值（会 JSON.stringify 非字符串值）
   */
  async function setField(sheet: string, field: string, value: any): Promise<void> {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
    await saveField(itemId, { conclusion })
  }

  /**
   * setTbValues — 从 render-config html_data 的 TB 种子数据设置只读字段。
   * 用于 FormData 初始化时接收后端自动取数（期初/未审等TB字段）。
   * @param values - Record<itemId, value>
   */
  function setTbValues(values: Record<string, any>): void {
    for (const [itemId, value] of Object.entries(values)) {
      const fullId = itemId.startsWith(ITEM_PREFIX) ? itemId : `${ITEM_PREFIX}${itemId}`
      const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
      const existing = allResponses.value.get(fullId) || { item_id: fullId, conclusion: null, remark: null }
      allResponses.value.set(fullId, { ...existing, conclusion })
    }
  }

  // ─── saveField (单字段保存，即时) ──────────────────────────────────────────

  /**
   * 保存单个字段（结论/状态/选择类字段立即保存）
   * @param itemId - 如 "M8-1-adjudicated-amount"
   * @param value - { conclusion?, remark? }
   */
  async function saveField(itemId: string, value: { conclusion?: string; remark?: string }): Promise<void> {
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
   * 批量保存多个 items
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

  // ─── writebackTB (回写审定数到 trial_balance 4104) ─────────────────────────

  /**
   * 回写审定数到 trial_balance（科目 4104 一般风险准备，**贷方/权益类！金融企业专属**）。
   *
   * 权益类贷方方向铁律：
   * - 期末 = 期初 + 贷方(增加：从净利润计提) - 借方(减少：转回/使用)
   * - 回写的 audited_amount 代表期末余额（正数=一般风险准备贷方余额）
   * - 金融企业从净利润中计提：贷方增加（原则上≥风险资产期末余额×1.5%）
   * - 转回/使用：借方减少（弥补已识别损失）
   *
   * 并发布 EventBus 'substantive:adjudicated' 事件通知其他组件（附注刷新等）。
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      // 发布 EventBus 通知审定数变更（附注等组件订阅刷新）
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE,
        auditedAmount,
        wpCode: 'M8',
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
    getField,
    setField,
    setTbValues,
    saveField,
    saveBatch,
    debouncedSave,
    writebackTB,
  }
}

export default useM8FormData
