/**
 * useK2FormData — K2 其他流动资产 selfLoad/checklist_responses/writebackTB/TB取数
 *
 * Spec: .kiro/specs/k2-other-current-assets/（科目口径修正见
 *       .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Requirements 1.1~1.3）
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文 + checklist_responses
 * - loadTbData(): 从 trial_balance 获取其他流动资产未审/审定数据
 * - writebackTB(): 审定数回写 trial_balance + EventBus 'substantive:adjudicated'
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K2-{sheet}-{field}"（如 "K2-1-audited-amount", "K2-4-contract-cost"）
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 🔴 科目口径由 `k2AccountScope` 单一真源给出（报表行 `BS-014` → 实证 `TB('1901')`）。
 * 历史实现写死 `1231`（应收款项坏账准备）→ `writebackTB` 会往坏账准备科目写审定数，
 * 覆盖 D1/D2/K1 的口径；`loadTbData` 的 seed 键 `other_current_1231_unadjusted`
 * 在 render 输出里**根本不存在**（真实键是 `other_current_unadjusted`）→ seed 从未生效。
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  K2_ACCOUNT_NAME,
  K2_GROSS_FALLBACK_STANDARD,
  k2GrossQueryCodes,
} from './k2AccountScope'
import { sumLongestPrefixOnly, type TbSourceCodes } from './shared/tbSourceCodes'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface K2TbData {
  unadjusted: number
  audited: number
}

export interface ProjectContext {
  business_category?: string
  applicable_standards?: string[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2FormData(wpId: Ref<string>, projectId: Ref<string>) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<K2TbData>({ unadjusted: 0, audited: 0 })
  const projectContext = ref<ProjectContext>({})
  const renderMeta = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  // ─── getValue / setValue ────────────────────────────────────────────────────

  /** 从 allResponses Map 中获取指定 item 的值（尝试 JSON 解析） */
  function getValue(itemId: string): any {
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
  function setValue(itemId: string, value: any): void {
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
   * 立即保存指定 item（结论/状态/选择类字段触发）。
   * 乐观更新：先更新本地 Map，保存失败不回滚。
   */
  async function saveImmediate(itemId: string, value: any): Promise<void> {
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

  // ─── saveBatch (批量保存) ──────────────────────────────────────────────────

  /**
   * 批量原子性保存多个 item（如审定表多行回写）。
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

  /** 该项目解析出的科目口径（render 下发 `tb_source_codes`；缺省回退 `1901`） */
  function _queryCodes(): string[] {
    return k2GrossQueryCodes(renderMeta.value?.tb_source_codes as TbSourceCodes | undefined)
  }

  // ─── loadTbData: 从 trial_balance 获取其他流动资产数据 ─────────────────────

  /**
   * 从 trial_balance 获取其他流动资产的未审数和审定数。
   * 优先从 renderMeta seed 读取（键名与 render 输出逐字一致），否则请求 TB 端点。
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值（render 已按最长前缀归属算好，口径同源）
    const seeded = renderMeta.value?.tb_values?.other_current_unadjusted
    const seededAudited = renderMeta.value?.tb_values?.other_current_audited
    if (seeded != null) {
      tbData.value = {
        unadjusted: Number(seeded) || 0,
        audited: Number(seededAudited) || 0,
      }
      return
    }

    const codes = _queryCodes()
    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: codes[0] },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      const rows = list.map((item) => ({
        code: String(item.standard_account_code ?? item.account_code ?? ''),
        unadjusted: Number(item.unadjusted_amount ?? 0) || 0,
        audited: Number(item.audited_amount ?? 0) || 0,
      }))
      // 最长前缀求和：父子并存时不双计（`1901` 与 `1901-01` 可能同时在册）
      const sum = sumLongestPrefixOnly(rows, codes)
      const found = rows.some((r) => codes.some((c) => r.code === c || r.code.startsWith(c)))

      tbData.value = { unadjusted: sum.unadjusted, audited: sum.audited }

      if (!found) {
        ElMessage.warning(
          `科目 ${codes.join('、')} ${K2_ACCOUNT_NAME}未在试算表中找到，请先导入试算表`,
        )
      }
    } catch {
      tbData.value = { unadjusted: 0, audited: 0 }
    }
  }

  // ─── setTbValues（外部设置TB值，render策略seed回读） ────────────────────────

  /**
   * 外部设置 TB 值（从 render 策略 seed 或组件 watch 调用）。
   */
  function setTbValues(values: Partial<K2TbData>): void {
    if (values.unadjusted != null) {
      tbData.value.unadjusted = values.unadjusted
    }
    if (values.audited != null) {
      tbData.value.audited = values.audited
    }
  }

  // ─── writebackTB（其他流动资产，科目由报表映射解析） ────────────────────────

  /**
   * 审定数回写 trial_balance：其他流动资产（借方/资产类）。
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * 🔴 科目码取解析结果（实证 `1901`），**不是** `1231`（那是应收款项坏账准备，
   * 往它回写会覆盖 D1/D2/K1 的坏账口径）。
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    const accountCode = _queryCodes()[0] || K2_GROSS_FALLBACK_STANDARD
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: auditedAmount,
      })

      // EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        accountCode,
        auditedAmount,
        wpCode: 'K2',
        timestamp: Date.now(),
      })

      // 同步更新本地 tbData
      tbData.value.audited = auditedAmount
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── selfLoad（render-config + checklist_responses + TB） ───────────────────

  /**
   * 完整自加载入口：render-config → checklist_responses → TB + projectContext。
   * bundle内嵌场景 htmlData 为 null 时自行调用。
   * 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'k2-other-current-assets' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 2. 加载 checklist_responses
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith('K2-') || r.item_id?.startsWith('K2A-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map

      // 3. 并行加载 TB + projectContext
      await Promise.all([
        loadTbData(),
        _loadProjectContext(),
      ])
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadData（兼容别名） ──────────────────────────────────────────────────

  /** selfLoad 别名，统一接口命名 */
  async function loadData(): Promise<void> {
    return selfLoad()
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
      // 静默失败
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
    allResponses,
    tbData,
    projectContext,
    renderMeta,
    // Accessors
    getValue,
    setValue,
    // Save actions
    saveImmediate,
    debouncedSave,
    saveBatch,
    // TB
    loadTbData,
    writebackTB,
    setTbValues,
    // Load
    selfLoad,
    loadData,
  }
}

export default useK2FormData
