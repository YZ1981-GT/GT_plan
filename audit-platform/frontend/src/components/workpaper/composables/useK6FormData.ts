/**
 * useK6FormData — K6 持有待售资产和负债 selfLoad/checklist_responses/writebackTB(双科目)/TB取数
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文 + checklist_responses
 * - loadTbData(): 从 trial_balance 获取双科目（1481资产 + 2605负债）未审/审定数据
 * - writebackTB(): 审定数回写 trial_balance 双科目 + EventBus 'substantive:adjudicated'
 *   - 持有待售资产 (1481, 借方/资产类)
 *   - 持有待售负债 (2605, 贷方/负债类)
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K6-{sheet}-{field}"（如 "K6-1-audited-asset", "K6-1-audited-liability"）
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 科目：
 * - 1481 持有待售资产（**借方/资产类**）：期末=期初+增加-减少-减值
 * - 2605 持有待售负债（**贷方/负债类**）：期末=期初+增加-减少
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

export interface K6TbData {
  /** 1481持有待售资产 未审数（借方/资产类） */
  unadjustedAsset: number
  /** 1481持有待售资产 审定数 */
  auditedAsset: number
  /** 2605持有待售负债 未审数（贷方/负债类） */
  unadjustedLiability: number
  /** 2605持有待售负债 审定数 */
  auditedLiability: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：1481 持有待售资产（借方/资产类） */
const ACCOUNT_CODE_ASSET = '1481'
/** 科目：2605 持有待售负债（贷方/负债类） */
const ACCOUNT_CODE_LIABILITY = '2605'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetPrefix: string
}) {
  const { wpId, projectId, sheetPrefix } = params

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const allResponses = ref<Map<string, any>>(new Map())
  const tbData = ref<K6TbData>({
    unadjustedAsset: 0,
    auditedAsset: 0,
    unadjustedLiability: 0,
    auditedLiability: 0,
  })
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
        params: { force_component_type: 'k6-held-for-sale' },
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
        if (r.item_id?.startsWith('K6-') || r.item_id?.startsWith('K6A-')) {
          allResponses.value.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }

      // 4. 加载 TB 数据（双科目）
      await loadTbData()
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadTbData: 从 trial_balance 获取双科目数据 ───────────────────────────

  /**
   * 从 trial_balance 获取双科目的未审数和审定数。
   * - 1481 持有待售资产（借方/资产类）
   * - 2605 持有待售负债（贷方/负债类）
   *
   * 优先从 renderMeta seed 读取，否则分别请求 TB 端点。
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seededAssetUnadj = renderMeta.value?.tb_values?.held_for_sale_asset_1481_unadjusted
    const seededAssetAudited = renderMeta.value?.tb_values?.held_for_sale_asset_1481_audited
    const seededLiabUnadj = renderMeta.value?.tb_values?.held_for_sale_liability_2605_unadjusted
    const seededLiabAudited = renderMeta.value?.tb_values?.held_for_sale_liability_2605_audited

    if (seededAssetUnadj != null) {
      tbData.value = {
        unadjustedAsset: Number(seededAssetUnadj) || 0,
        auditedAsset: Number(seededAssetAudited) || 0,
        unadjustedLiability: Number(seededLiabUnadj) || 0,
        auditedLiability: Number(seededLiabAudited) || 0,
      }
      return
    }

    // 分别拉取 1481 和 2605
    try {
      const [assetRes, liabRes] = await Promise.all([
        api.get(`/api/projects/${projectId.value}/trial-balance`, {
          params: { account_prefix: ACCOUNT_CODE_ASSET },
          _silent: true,
        } as any),
        api.get(`/api/projects/${projectId.value}/trial-balance`, {
          params: { account_prefix: ACCOUNT_CODE_LIABILITY },
          _silent: true,
        } as any),
      ])

      // 解析资产1481
      const assetList: any[] = Array.isArray(assetRes?.data ?? assetRes)
        ? (assetRes?.data ?? assetRes)
        : (assetRes?.data?.items ?? [])
      let assetUnadj = 0
      let assetAudited = 0
      let assetFound = false

      for (const item of assetList) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_ASSET)) {
          assetUnadj += Number(item.unadjusted_amount ?? 0)
          assetAudited += Number(item.audited_amount ?? 0)
          assetFound = true
        }
      }

      // 解析负债2605
      const liabList: any[] = Array.isArray(liabRes?.data ?? liabRes)
        ? (liabRes?.data ?? liabRes)
        : (liabRes?.data?.items ?? [])
      let liabUnadj = 0
      let liabAudited = 0
      let liabFound = false

      for (const item of liabList) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_LIABILITY)) {
          liabUnadj += Number(item.unadjusted_amount ?? 0)
          liabAudited += Number(item.audited_amount ?? 0)
          liabFound = true
        }
      }

      tbData.value = {
        unadjustedAsset: assetUnadj,
        auditedAsset: assetAudited,
        unadjustedLiability: liabUnadj,
        auditedLiability: liabAudited,
      }

      if (!assetFound && !liabFound) {
        ElMessage.warning('持有待售资产(1481)和负债(2605)均未在试算表中找到，请先导入试算表')
      }
    } catch {
      tbData.value = { unadjustedAsset: 0, auditedAsset: 0, unadjustedLiability: 0, auditedLiability: 0 }
    }
  }

  // ─── writebackTB（双科目：1481资产 + 2605负债） ─────────────────────────────

  /**
   * 审定数回写 trial_balance：双科目。
   * - 1481 持有待售资产（借方/资产类），正数口径
   * - 2605 持有待售负债（贷方/负债类），正数口径
   *
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * Req 2.6: WHEN 审定数变化时 SHALL 回写trial_balance(持有待售资产+负债)+发布'substantive:adjudicated'
   *
   * @param assetAudited  持有待售资产审定额（1481, 借方/资产类正数口径）
   * @param liabilityAudited 持有待售负债审定额（2605, 贷方/负债类正数口径）
   */
  async function writebackTB(assetAudited: number, liabilityAudited: number): Promise<void> {
    if (!projectId.value) return
    isSaving.value = true
    try {
      // 并行回写双科目
      await Promise.all([
        api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_ASSET,
          audited_amount: assetAudited,
        }),
        api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_LIABILITY,
          audited_amount: liabilityAudited,
        }),
      ])

      // EventBus publish 'substantive:adjudicated'（资产科目）
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_ASSET,
        auditedAmount: assetAudited,
        wpCode: 'K6',
        timestamp: Date.now(),
      })

      // EventBus publish 'substantive:adjudicated'（负债科目）
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_LIABILITY,
        auditedAmount: liabilityAudited,
        wpCode: 'K6',
        timestamp: Date.now(),
      })

      // 同步更新本地 tbData
      tbData.value.auditedAsset = assetAudited
      tbData.value.auditedLiability = liabilityAudited
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    } finally {
      isSaving.value = false
    }
  }

  // ─── Save core ─────────────────────────────────────────────────────────────

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
   * @param itemId 完整 item_id（如 "K6-1-audited-asset"）
   * @param value { conclusion?, remark? } 或简单值
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
   * @param itemId 完整 item_id
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
  function setTbValues(values: Partial<K6TbData>): void {
    if (values.unadjustedAsset != null) tbData.value.unadjustedAsset = values.unadjustedAsset
    if (values.auditedAsset != null) tbData.value.auditedAsset = values.auditedAsset
    if (values.unadjustedLiability != null) tbData.value.unadjustedLiability = values.unadjustedLiability
    if (values.auditedLiability != null) tbData.value.auditedLiability = values.auditedLiability
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
    isSaving,
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

export default useK6FormData
