/**
 * useH5FormData — H5 油气资产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.7
 *
 * 职责：
 * - allResponses Map 加载 + saveResponse(即时) + debouncedSave(2s) + saveBatch
 * - writebackTB（科目1631油气资产借方 + 1632累计折耗贷方/备抵）
 * - selfLoad逻辑（render-config?force_component_type=h5-oil-gas-assets）
 * - TB自动取数 unadjusted_amount → 审定表未审数
 * - EventBus publish 'substantive:adjudicated' 通知附注刷新
 *
 * 科目：1631 油气资产（借方/资产类）+ 1632 累计折耗（贷方/备抵类）
 * ⚠️ 资产负债表科目！取期末余额（非发生额）！
 * - 1631为借方科目：期末=期初+借方-贷方（资产类）
 * - 1632为贷方科目（备抵）：期末=期初+贷方-借方（备抵类）
 * - 净值=油气资产原值-累计折耗
 *
 * item_id 命名规则：前缀 "H5-{sheet编号}-{field}"
 * 例：H5-1-audited-cost, H5-2-detail-row-1, H5-12-depletion-total
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

/**
 * TB取数结构：油气资产(1631) + 累计折耗(1632)
 * 资产负债表科目，取期末余额
 */
export interface H5TbData {
  /** 1631油气资产 未审期末余额（借方科目） */
  costUnadjusted: number
  /** 1632累计折耗 未审期末余额（贷方/备抵） */
  depletionUnadjusted: number
  /** 1631 审定数 */
  costAudited: number
  /** 1632 审定数 */
  depletionAudited: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：1631 油气资产（借方/资产类） */
const ACCOUNT_CODE_1631 = '1631'
/** 科目：1632 累计折耗（贷方/备抵类） */
const ACCOUNT_CODE_1632 = '1632'
const COMPONENT_TYPE = 'h5-oil-gas-assets'

// ─── Helper ──────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5FormData(opts: {
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
  const tbData = ref<H5TbData>({
    costUnadjusted: 0,
    depletionUnadjusted: 0,
    costAudited: 0,
    depletionAudited: 0,
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
   * 立即保存单个 checklist item（结论/枚举/选择类字段触发）。
   * @param itemId 完整 item_id（如 "H5-1-audited-cost"）
   * @param value 值（对象会 JSON.stringify，字符串直接存 remark）
   * @param conclusion 可选结论字段
   */
  async function saveResponse(itemId: string, value: any, conclusion?: string | null): Promise<void> {
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
      conclusion: conclusion !== undefined ? (conclusion ?? null) : (existing?.conclusion ?? null),
      remark: strVal,
    }
    allResponses.value.set(itemId, updated)
    await _doSave([updated])
  }

  // ─── debouncedSave (2s) ────────────────────────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
   * 文本输入字段使用此方法避免频繁请求。
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

  // ─── saveBatch（原子性批量保存） ───────────────────────────────────────────

  /**
   * 批量原子性保存多个 item。
   * 用于跨字段同时变更场景（如审定表回写多行、导入数据填充）。
   */
  async function saveBatch(items: { itemId: string; value: any; conclusion?: string | null }[]): Promise<void> {
    const checklistItems: ChecklistItem[] = items.map(({ itemId, value, conclusion }) => {
      const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
      const existing = allResponses.value.get(itemId)
      const updated: ChecklistItem = {
        item_id: itemId,
        conclusion: conclusion !== undefined ? (conclusion ?? null) : (existing?.conclusion ?? null),
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

  // ─── writebackTB（1631油气资产 + 1632累计折耗） ────────────────────────────

  /**
   * 审定数回写 trial_balance：
   * - 1631 油气资产（借方/资产类）
   * - 1632 累计折耗（贷方/备抵类）
   *
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * @param accountCode 科目代码（'1631' 或 '1632'）
   * @param amount 审定数金额
   */
  async function writebackTB(accountCode: string, amount: number): Promise<void> {
    if (!projectId.value) return
    if (accountCode !== ACCOUNT_CODE_1631 && accountCode !== ACCOUNT_CODE_1632) {
      console.warn(`[H5] writebackTB: 未知科目代码 ${accountCode}，仅支持 1631/1632`)
      return
    }

    isSaving.value = true
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: amount,
      })

      // 更新本地 tbData
      if (accountCode === ACCOUNT_CODE_1631) {
        tbData.value.costAudited = amount
      } else {
        tbData.value.depletionAudited = amount
      }

      // EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        wpId: wpId.value,
        accountCode,
        auditedAmount: amount,
        componentType: COMPONENT_TYPE,
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    } finally {
      isSaving.value = false
    }
  }

  // ─── selfLoad（render-config + checklist_responses） ────────────────────────

  /**
   * 从 render-config 加载 allResponses 数据。
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

      // 2. 从 render-config 预填 allResponses（如有 checklist_data）
      const preloaded = renderMeta.value?.checklist_data
      if (preloaded && typeof preloaded === 'object') {
        for (const [k, v] of Object.entries(preloaded)) {
          if (k.startsWith('H5-') || k.startsWith('H5A-')) {
            allResponses.value.set(k, v as ChecklistItem)
          }
        }
      }

      // 3. 加载 checklist_responses（补充已持久化数据）
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      for (const r of responses) {
        if (r.item_id?.startsWith('H5-') || r.item_id?.startsWith('H5A-')) {
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

  // ─── loadTbData: 资产负债表科目取余额 ─────────────────────────────────────

  /**
   * 从 trial_balance 获取科目 1631+1632 的期末余额数据。
   * ⚠️ 资产类！取期末余额（非发生额）！
   * 1631借方科目：期末=期初+借方-贷方
   * 1632贷方备抵：期末=期初+贷方-借方
   *
   * 优先从 render-config seed 取值。
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seeded = renderMeta.value?.tb_values
    if (seeded) {
      tbData.value = {
        costUnadjusted: parseNum(seeded.cost_1631_unadjusted ?? seeded.unadjusted_1631 ?? 0),
        depletionUnadjusted: parseNum(seeded.depletion_1632_unadjusted ?? seeded.unadjusted_1632 ?? 0),
        costAudited: parseNum(seeded.cost_1631_audited ?? seeded.audited_1631 ?? 0),
        depletionAudited: parseNum(seeded.depletion_1632_audited ?? seeded.audited_1632 ?? 0),
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '1631,1632' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let costUnadj = 0
      let deplUnadj = 0
      let costAud = 0
      let deplAud = 0
      let found1631 = false
      let found1632 = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_1631)) {
          costUnadj += parseNum(item.unadjusted_amount ?? 0)
          costAud += parseNum(item.audited_amount ?? 0)
          found1631 = true
        } else if (code.startsWith(ACCOUNT_CODE_1632)) {
          deplUnadj += parseNum(item.unadjusted_amount ?? 0)
          deplAud += parseNum(item.audited_amount ?? 0)
          found1632 = true
        }
      }

      tbData.value = {
        costUnadjusted: costUnadj,
        depletionUnadjusted: deplUnadj,
        costAudited: costAud,
        depletionAudited: deplAud,
      }

      // 科目未找到时黄色提示
      if (!found1631 || !found1632) {
        const missing = []
        if (!found1631) missing.push('1631油气资产')
        if (!found1632) missing.push('1632累计折耗')
        ElMessage.warning(`科目${missing.join('/')}未在试算表中找到，未审数显示为0`)
      }
    } catch {
      tbData.value = { costUnadjusted: 0, depletionUnadjusted: 0, costAudited: 0, depletionAudited: 0 }
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
    renderMeta,
    tbData,
    // Accessors
    getResponse,
    setResponse,
    // Save actions
    saveResponse,
    debouncedSave,
    saveBatch,
    // TB writeback
    writebackTB,
    // Load
    selfLoad,
    loadTbData,
  }
}

export default useH5FormData
