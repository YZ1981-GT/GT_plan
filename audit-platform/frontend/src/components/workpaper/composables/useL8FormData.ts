/**
 * useL8FormData — L8 财务费用数据加载/debounce保存/即时保存/TB回写
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.4, 2.6
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "L8-{sheet}-{field}"（如 "L8-1-interestExpTotal", "L8-2-fxLoss"）
 * - writebackTB(6603): 审定数回写 trial_balance 科目 6603 财务费用（**发生额口径！**）
 * - tbOccurrence: 从 tb_ledger(tb_balance) 取科目6603本期借贷发生额
 * - EventBus: 回写成功后发布 'substantive:adjudicated'
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * ─── 损益类方向铁律（与L1~L7负债类根本不同！） ───
 * 科目：6603 财务费用（借方/损益类！取发生额）
 * 本期发生额 = 借方发生 - 贷方发生（费用为借方科目，借增贷减）
 * 从 tb_balance 取 debit_amount / credit_amount 计算
 * 回写TB用发生额口径（audited_amount = 审定发生额）
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

export interface UseL8FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 当前审计年度（用于从tb_balance取发生额） */
  year?: Ref<number> | number
  sheetName?: Ref<string> | string
}

/** tb_ledger 发生额数据（损益类科目6603） */
export interface TbOccurrence {
  /** 借方发生额（费用增加） */
  debit: number
  /** 贷方发生额（费用冲回） */
  credit: number
  /** 净发生额 = 借方 - 贷方 */
  net: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'L8-'
const ACCOUNT_CODE = '6603' // 财务费用（借方/损益类！取发生额）

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL8FormData(options: UseL8FormDataOptions) {
  const { wpId, projectId } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  /** tb_ledger 发生额（损益类！从tb_balance取debit_amount/credit_amount） */
  const tbOccurrence = ref<TbOccurrence>({ debit: 0, credit: 0, net: 0 })

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
        `/api/workpapers/${wpId.value}/render-config?force_component_type=l8-financial-expenses`,
        { _silent: true } as any,
      )
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 L8 数据（item_id 前缀 "L8-"）
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
      ElMessage.warning('L8数据加载失败，可手动填写')
    }
  }

  // ─── Load tb_ledger occurrence（损益类取发生额！） ──────────────────────────

  /**
   * 从 tb_balance 取科目6603的借贷发生额。
   *
   * 损益类科目方向铁律：
   *   本期发生额 = debit_amount - credit_amount
   *   费用为借方科目：借增贷减
   *
   * API: GET /api/projects/{pid}/ledger/balance?year=YYYY&account_code=6603
   * 返回: [{ account_code, debit_amount, credit_amount, ... }]
   */
  async function loadTbOccurrence(): Promise<void> {
    if (!projectId.value) return
    const yearVal = typeof options.year === 'number'
      ? options.year
      : (options.year?.value ?? new Date().getFullYear())
    try {
      const data = await api.get(
        `/api/projects/${projectId.value}/ledger/balance`,
        { params: { year: yearVal, account_code: ACCOUNT_CODE } },
      )
      const rows: any[] = Array.isArray(data) ? data : (data?.data ?? [])
      // 找到6603科目行
      const row = rows.find((r: any) => r.account_code === ACCOUNT_CODE)
      if (row) {
        const debit = Number(row.debit_amount) || 0
        const credit = Number(row.credit_amount) || 0
        tbOccurrence.value = { debit, credit, net: debit - credit }
      } else {
        tbOccurrence.value = { debit: 0, credit: 0, net: 0 }
      }
    } catch {
      // tb_ledger 无数据时不阻塞
      tbOccurrence.value = { debit: 0, credit: 0, net: 0 }
    }
  }

  // ─── loadData（统一加载入口） ─────────────────────────────────────────────

  /**
   * 统一加载入口：selfLoad + loadResponses + loadTbOccurrence 并行
   */
  async function loadData(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([selfLoad(), loadResponses(), loadTbOccurrence()])
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

  // ─── getField / setField（便捷接口） ──────────────────────────────────────

  /**
   * 获取指定 sheet + field 的值
   * @param sheet - 如 "1", "2", "3"
   * @param field - 如 "interestExpTotal", "fxLoss"
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
   * @param sheet - 如 "1", "2", "3"
   * @param field - 如 "interestExpTotal", "fxLoss"
   * @param value - 要存储的值（会 JSON.stringify 非字符串值）
   */
  async function setField(sheet: string, field: string, value: any): Promise<void> {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
    await saveField(itemId, { conclusion })
  }

  // ─── saveField (单字段保存，即时) ──────────────────────────────────────────

  /**
   * 保存单个字段（结论/状态/选择类字段立即保存）
   * @param itemId - 如 "L8-1-audited_amount"
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

  // ─── writebackTB (回写审定数到 trial_balance 6603, 发生额口径) ─────────────

  /**
   * 回写审定数到 trial_balance（科目 6603 财务费用，**发生额口径！**）。
   *
   * ⚠️ 损益类特殊：
   * - 回写的 audited_amount 代表审定的本期发生额（非余额）
   * - 费用为借方科目：正值=费用增加，负值=费用冲回
   *
   * 并发布 EventBus 'substantive:adjudicated' 事件通知其他组件（附注刷新等）。
   */
  async function writebackTB(amount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE,
        audited_amount: amount,
      })
      // 发布 EventBus 通知审定数变更（附注等组件订阅刷新）
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE,
        auditedAmount: amount,
        wpCode: 'L8',
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
    tbOccurrence,
    // Actions
    loadData,
    getField,
    setField,
    saveField,
    saveBatch,
    debouncedSave,
    writebackTB,
  }
}

export default useL8FormData
