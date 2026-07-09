/**
 * useK11FormData — K11 资产减值损失 selfLoad/checklist_responses/writebackTB(6701 发生额！)
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6, 5.1-5.2
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文 + checklist_responses
 * - loadTbData(): 从 trial_balance 获取科目 6701 发生额数据（损益类！）
 * - writebackTB(): 审定数回写 trial_balance(6701) + EventBus 'substantive:adjudicated'
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K11-{sheet}-{field}"
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 科目：6701 资产减值损失（**损益类/借方科目**）
 * ⚠️ 损益类！取发生额非余额！
 * - 6701为借方科目：借方=减值增加，贷方=减值转回/冲回
 * - 减值损失发生额 = 借方发生 - 贷方发生(转回红冲)
 * - TB回写发生额，非期末余额（期末结转本年利润后为0）
 * - 与K9(6602管理费用)/K8(6601销售费用)/I6(6602研发费用)/H10(6115资产处置损益)同款损益类处理逻辑
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { parseNum } from './useK11FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/**
 * 损益类TB数据结构（发生额！非余额）
 * 6701资产减值损失：借方=减值增加，贷方=减值转回/冲回
 */
export interface K11TbData {
  /** 未审借方发生额（减值增加） */
  unadjustedDebit: number
  /** 未审贷方发生额（减值转回/冲回） */
  unadjustedCredit: number
  /** 未审净发生额 = 借方 - 贷方 */
  unadjustedNet: number
  /** 审定发生额（回写值） */
  auditedAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：6701 资产减值损失（借方/损益类） */
const ACCOUNT_CODE_6701 = '6701'
const COMPONENT_TYPE = 'k11-asset-impairment-loss'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK11FormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string>
}) {
  const { wpId, projectId } = opts

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const tbData = ref<K11TbData>({
    unadjustedDebit: 0,
    unadjustedCredit: 0,
    unadjustedNet: 0,
    auditedAmount: 0,
  })

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── getResponse / setResponse ─────────────────────────────────────────────

  /** 从 allResponses Map 中获取指定 item 的值（尝试JSON解析） */
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

  /** 设置 allResponses Map 中的值，并触发 debouncedSave */
  function setResponse(itemId: string, value: any): void {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId)
    const updated: ChecklistItem = {
      item_id: itemId,
      conclusion: existing?.conclusion ?? null,
      remark: strVal,
    }
    allResponses.value.set(itemId, updated)
    debouncedSave(itemId, updated)
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

  // ─── saveResponse（单条立即保存） ──────────────────────────────────────────

  /**
   * 立即保存单个 checklist item。
   * @param itemId 完整 item_id（如 "K11-1-audited-total"）
   * @param value 值（对象会 JSON.stringify，字符串直接存 remark）
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

  // ─── saveBatch（批量保存） ─────────────────────────────────────────────────

  /**
   * 批量原子性保存多个 items（如审定表多行回写）。
   */
  async function saveBatch(items: { itemId: string; value: any }[]): Promise<void> {
    const checklistItems: ChecklistItem[] = items.map(({ itemId, value }) => {
      const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
      const existing = allResponses.value.get(itemId)
      const updated: ChecklistItem = {
        item_id: itemId,
        conclusion: existing?.conclusion ?? null,
        remark: strVal,
      }
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

  // ─── debouncedSave (2s) ────────────────────────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
   * 适用于 textarea / 备注等文本字段。
   */
  function debouncedSave(itemId: string, data: ChecklistItem): void {
    allResponses.value.set(itemId, data)
    _pendingItems.add(itemId)

    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)

    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([data])
    }, DEBOUNCE_MS))
  }

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * 完整自加载入口：render-config → checklist_responses → TB发生额。
   * bundle内嵌场景 htmlData 为 null 时自行调用。
   * 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: COMPONENT_TYPE },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 2. 从 sheets 数组提取 allResponses（如有）
      const sheetsArr = configData?.sheets ?? configData?.data?.sheets
      if (sheetsArr && Array.isArray(sheetsArr)) {
        for (const sheet of sheetsArr) {
          if (sheet.html_data?.allResponses) {
            for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
              allResponses.value.set(k, v as ChecklistItem)
            }
          }
        }
      }

      // 3. 加载 checklist_responses（补充已持久化数据）
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      for (const r of responses) {
        if (r.item_id?.startsWith('K11-') || r.item_id?.startsWith('K11A-')) {
          allResponses.value.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }

      // 4. 加载 TB 发生额数据
      await loadTbData()
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadTbData: 损益类取发生额（从tb_ledger，非期末余额！）───────────────

  /**
   * 从 trial_balance / tb_ledger 获取科目 6701 的发生额数据。
   * ⚠️ 损益类！取发生额非期末余额！
   *
   * 来源字段：borrowing_amount（借方发生）/ lending_amount（贷方发生）
   * 或：period_debit / period_credit / debit_amount / credit_amount
   *
   * 优先从 render-config seed 取值（后端 render 策略已预查 tb_ledger）。
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seeded = renderMeta.value?.tb_values
    if (seeded) {
      const debit = parseNum(seeded.unadjusted_debit ?? seeded.borrowing_amount ?? 0)
      const credit = parseNum(seeded.unadjusted_credit ?? seeded.lending_amount ?? 0)
      tbData.value = {
        unadjustedDebit: debit,
        unadjustedCredit: credit,
        unadjustedNet: debit - credit,
        auditedAmount: parseNum(seeded.audited_amount ?? 0),
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: ACCOUNT_CODE_6701 },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let totalDebit = 0
      let totalCredit = 0
      let auditedAmount = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_6701)) {
          // 损益类：取发生额字段
          totalDebit += parseNum(item.borrowing_amount ?? item.period_debit ?? item.debit_amount ?? 0)
          totalCredit += parseNum(item.lending_amount ?? item.period_credit ?? item.credit_amount ?? 0)
          auditedAmount += parseNum(item.audited_amount ?? 0)
          found = true
        }
      }

      tbData.value = {
        unadjustedDebit: totalDebit,
        unadjustedCredit: totalCredit,
        unadjustedNet: totalDebit - totalCredit,
        auditedAmount,
      }

      if (!found) {
        ElMessage.warning('科目6701资产减值损失未在试算表中找到，发生额显示为0')
      }
    } catch {
      tbData.value = {
        unadjustedDebit: 0,
        unadjustedCredit: 0,
        unadjustedNet: 0,
        auditedAmount: 0,
      }
    }
  }

  // ─── writebackTB（发生额回写！非期末余额）─────────────────────────────────

  /**
   * 审定数回写 trial_balance：科目6701资产减值损失
   * ⚠️ 关键区别：损益类回写**发生额**，非期末余额！
   * 与K9(6602)/K8(6601)/I6(6602研发)/H10(6115)同款处理逻辑。
   *
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * @param auditedAmount 审定发生额（借方-贷方净额）
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    isSaving.value = true
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_6701,
        audited_amount: auditedAmount,
        is_occurrence: true, // 标识：损益类发生额回写
      })

      // 更新本地 tbData
      tbData.value.auditedAmount = auditedAmount

      // EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_6701,
        auditedAmount,
        wpCode: 'K11',
        type: 'occurrence_amount', // 标识：发生额回写
        timestamp: Date.now(),
      })

      // 保存审定金额到独立 item_id 供跨sheet引用
      await saveResponse('K11-1-adjudicated-amount', String(auditedAmount))
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    } finally {
      isSaving.value = false
    }
  }

  // ─── setTbValues（外部设置TB值，render策略seed回读） ────────────────────────

  /**
   * 外部手动设置 TB 发生额数据（从 render 策略 seed 或组件 watch 调用）。
   */
  function setTbValues(values: Partial<K11TbData>): void {
    if (values.unadjustedDebit != null) {
      tbData.value.unadjustedDebit = values.unadjustedDebit
    }
    if (values.unadjustedCredit != null) {
      tbData.value.unadjustedCredit = values.unadjustedCredit
    }
    if (values.unadjustedNet != null) {
      tbData.value.unadjustedNet = values.unadjustedNet
    } else if (values.unadjustedDebit != null || values.unadjustedCredit != null) {
      // 自动计算净发生额
      tbData.value.unadjustedNet = tbData.value.unadjustedDebit - tbData.value.unadjustedCredit
    }
    if (values.auditedAmount != null) {
      tbData.value.auditedAmount = values.auditedAmount
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
    isLoading,
    isSaving,
    allResponses,
    tbData,
    renderMeta,
    // Actions
    selfLoad,
    saveResponse,
    saveBatch,
    getResponse,
    setResponse,
    writebackTB,
    loadTbData,
    // Extras
    debouncedSave,
    setTbValues,
  }
}

export default useK11FormData
