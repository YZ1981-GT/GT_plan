/**
 * useI6FormData — I6 研发费用底稿数据层
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.4, 2.6, 10.1-10.4
 *
 * 职责：
 * - allResponses Map 加载 + saveImmediate + debouncedSave(2s) + saveBatch
 * - writebackTB（科目6602研发费用，**损益类！回写发生额非期末余额**）
 * - selfLoad逻辑（render-config?force_component_type=i6-research-development-expense）
 * - tbData：TB发生额数据（未审借方发生/贷方发生/审定发生额）
 * - 与H10同款处理逻辑：损益类取发生额
 *
 * 关键区别（损益类 vs 资产类）：
 * - 资产类(I1~I5): TB取期末余额 → audited_amount = 期末余额
 * - 损益类(I6):    TB取发生额   → audited_amount = 借方发生 - 贷方发生
 *                  来源: tb_ledger 发生额汇总，而非 tb_balance 期末余额
 * - 6602为借方科目：借方=费用增加，贷方=费用冲回/结转
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { parseNum } from './useI6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface ProjectContext {
  business_category?: string
  applicable_standards?: string[]
}

/**
 * 损益类TB数据结构（发生额！非余额）
 * 6602研发费用：借方=费用增加，贷方=费用冲回/结转
 */
export interface I6TbData {
  /** 未审借方发生额（费用增加） */
  unadjustedDebit: number
  /** 未审贷方发生额（费用冲回/结转） */
  unadjustedCredit: number
  /** 未审净发生额 = 借方 - 贷方 */
  unadjustedNet: number
  /** 审定发生额（回写值） */
  auditedAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_6602 = '6602'
const COMPONENT_TYPE = 'i6-research-development-expense'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6FormData(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string>
}) {
  const { wpId, projectId } = options

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const projectContext = ref<ProjectContext>({})
  const renderMeta = ref<Record<string, any>>({})
  const tbData = ref<I6TbData>({
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

  // ─── saveImmediate ─────────────────────────────────────────────────────────

  /**
   * 立即保存指定 item。
   * 乐观更新：先更新本地 Map，保存失败不回滚。
   */
  async function saveImmediate(itemId: string, value: any): Promise<void> {
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

  // ─── debouncedSave (2s) ────────────────────────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
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

  // ─── save（统一保存入口） ──────────────────────────────────────────────────

  /**
   * 批量原子性保存多个 item。
   * 用于跨字段同时变更场景（如审定表回写多行）。
   */
  async function save(items: { itemId: string; value: any }[]): Promise<void> {
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

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * 从 render-config 加载数据。
   * 当 htmlData prop 为 null 时（bundle内嵌场景）自行调用。
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

      // 2. 加载 checklist_responses
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith('I6-') || r.item_id?.startsWith('I6A-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map

      // 3. 并行加载 projectContext + TB发生额取数
      await Promise.all([
        _loadProjectContext(),
        _loadTbOccurrenceData(),
      ])
    } catch {
      // selfLoad 404 静默处理，显示空状态
    } finally {
      isLoading.value = false
    }
  }

  // ─── projectContext 加载 ───────────────────────────────────────────────────

  async function _loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const res = await api.get(`/api/projects/${projectId.value}`, {
        _silent: true,
      } as any)
      const data = res?.data ?? res
      projectContext.value = {
        business_category: data?.business_category ?? undefined,
        applicable_standards: data?.applicable_standards ?? undefined,
      }
    } catch {
      // 静默失败，projectContext 保持空
    }
  }

  // ─── TB发生额取数（损益类！非余额） ───────────────────────────────────────

  /**
   * 损益类取发生额！从 tb_ledger / trial-balance 获取科目6602的发生额数据。
   * 来源字段：borrowing_amount（借方发生）/ lending_amount（贷方发生）
   * 或：period_debit / period_credit
   *
   * 优先从 render-config seed 取值（后端已预查）。
   */
  async function _loadTbOccurrenceData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（后端 render 策略已查 tb_ledger）
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
        params: { account_prefix: ACCOUNT_CODE_6602 },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let totalDebit = 0
      let totalCredit = 0
      let auditedAmount = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_6602)) {
          // 损益类：取发生额字段（borrowing_amount/lending_amount 或 period_debit/period_credit）
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
        ElMessage.warning('科目6602研发费用未在试算表中找到，发生额显示为0')
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

  // ─── writebackTB（发生额回写！非期末余额） ────────────────────────────────

  /**
   * 审定数回写 trial_balance：科目6602研发费用
   * ⚠️ 关键区别：损益类回写**发生额**，非期末余额！
   * 与H10(6115)同款处理逻辑。
   *
   * @param auditedAmount 审定发生额（借方-贷方净额）
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_6602,
        audited_amount: auditedAmount,
      })
      // 更新本地 tbData
      tbData.value.auditedAmount = auditedAmount
      // 记录回写日志
      await saveImmediate('I6-1-tb-writeback', JSON.stringify({
        accountCode: ACCOUNT_CODE_6602,
        auditedAmount,
        type: 'occurrence_amount', // 标识：发生额回写
        timestamp: new Date().toISOString(),
      }))
      // 保存审定金额到独立 item_id 供跨sheet引用
      await saveImmediate('I6-1-adjudicated-amount', String(auditedAmount))
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── setTbValues（外部设置TB值） ───────────────────────────────────────────

  /**
   * 外部手动设置 TB 发生额数据（从 render 策略 seed 或组件 watch 调用）。
   */
  function setTbValues(values: Partial<I6TbData>): void {
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
    allResponses,
    tbData,
    isLoading,
    renderMeta,
    projectContext,
    // Actions
    save,
    selfLoad,
    setResponse,
    getResponse,
    writebackTB,
    // Low-level (for advanced usage)
    saveImmediate,
    debouncedSave,
    setTbValues,
  }
}

export default useI6FormData
