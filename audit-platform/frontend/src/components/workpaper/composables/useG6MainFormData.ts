/**
 * useG6MainFormData — G6 其他债权投资(main组) 数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/
 * Task: 1.10
 *
 * 职责：
 * - selfLoad逻辑（render-config?force_component_type=g6-other-bond-investment-main）
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 G6-main 数据
 * - debounce 2000ms 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 保存完整 content JSON（saveContent）
 * - writebackTB: 保存后回写 trial_balance 审定数(科目1503)
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * Requirements: 1.4, 3.3, 7.3
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── G6MainContent 顶层数据接口 ──────────────────────────────────────────────

export interface G6AdjudicationRow {
  id: string
  item: string
  openingUnadjusted: number
  openingAdjustment: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
}

export interface G6AdjudicationTotals {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}

export interface G6AdjudicationGroup {
  groupId: string
  groupName: string
  expanded: boolean
  rows: G6AdjudicationRow[]
  subtotal: G6AdjudicationTotals
}

export interface G6DetailRow {
  id: string
  seq: number
  investProject: string
  investCategory: string
  faceValue: number
  couponRate: number
  effectiveRate: number
  maturityDate: string
  initialInvestDate: string
  holdingQuantity: number
  contractTerms: string
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingSubtotal: number
  openingFairValue: number
  openingOCICumulative: number
  periodIncrease: number
  periodDecrease: number
  periodInterestIncome: number
  periodFVChange: number
  periodImpairment: number
  closingCost: number
  closingInterestAdj: number
  closingAccruedInterest: number
  closingSubtotal: number
  closingFairValue: number
  ociCumulative: number
  impairmentProvision: number
  auditAdjustment: number
  auditedAmount: number
  indexRef: string
}

export interface G6BadDebtRow {
  id: string
  seq: number
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3' | 'single'
  investProject: string
  bookBalance: number
  creditLossRate: number
  unadjustedProvision: number
  balanceAdjustment: number
  adjustedLossRate: number
  impairmentAdjustment: number
  adjustedBalance: number
  adjustedProvision: number
  adjustedBookValue: number
  priorYearProvision: number
  currentYearProvision: number
  currentYearReversal: number
  currentYearWriteoff: number
  closingProvision: number
  provisionDiff: number
  isAdequate: 'adequate' | 'inadequate' | 'excessive'
  auditConclusion: string
  evidenceRef: string
  remark: string
}

export interface G6AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

export interface G6DisclosureSection {
  id: string
  title: string
  rows?: G6DisclosureRow[]
  textContent?: string
}

export interface G6DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}

/** G6 main组 完整 content JSON 顶层接口 */
export interface G6MainContent {
  adjudication: { groups: G6AdjudicationGroup[] }
  detail: { rows: G6DetailRow[] }
  badDebtDetail: { rows: G6BadDebtRow[]; conclusion: string }
  adjustment: { entries: G6AdjustmentEntry[] }
  disclosureListed: { sections: G6DisclosureSection[] }
  disclosureSOE: { sections: G6DisclosureSection[] }
}

// ─── ChecklistResponse 类型 ─────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG6MainFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6MainFormData(opts: UseG6MainFormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()
  /** item_id 前缀：G6 main 组独占的 checklist 条目。 */
  const ITEM_PREFIXES = ['G6A-', 'G6-1-', 'G6-2-', 'G6-3-', 'G6-4-', 'G6-main-']
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => wpId.value,
    ownsItem: (itemId) => ITEM_PREFIXES.some((prefix) => itemId.startsWith(prefix)),
    versionOf: checklistCas.version,
  })
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!wpId.value) throw new Error('缺少底稿标识，无法保存')
      try {
        await checklistCas.save({
          wpId: wpId.value,
          projectId: projectId.value,
          items: items.map((item) => ({
            item_id: item.item_id,
            conclusion: item.conclusion || null,
            remark: item.remark || null,
          })),
        })
        opts.onAfterSave?.()
      } catch (error: unknown) {
        const message = (error as { message?: unknown })?.message
        if (message !== 'canceled') ElMessage.error('保存失败，请稍后重试')
        throw error
      }
    },
    onPending: drafts.store,
    onSettled: drafts.clear,
    onRecoveryRequired: drafts.markRecoveryRequired,
    blockOnError: isNonRetryableChecklistSaveError,
  })

  // ─── Load ────────────────────────────────────────────────────────────────

  async function restoreDrafts(): Promise<void> {
    let restored = false
    for (const draft of drafts.restore()) {
      const itemId = draft.item.item_id
      const hasServerValue = allResponses.value.has(itemId)
      const serverVersion = checklistCas.version(itemId)
      const requiresDecision = draft.requiresConfirmation === true
        || queue.requiresRecoveryDecision(itemId)
        || (draft.baseVersion
          ? !hasServerValue || !serverVersion || draft.baseVersion !== serverVersion
          : hasServerValue)
      if (requiresDecision) {
        queue.discard([itemId])
        const decision = await confirmChecklistDraftConflict()
        queue.resolveRecoveryDecision([itemId])
        if (decision === 'keep') {
          allResponses.value.set(itemId, draft.item)
        } else {
          drafts.clear([draft.item])
        }
        continue
      }
      if (draft.baseVersion) {
        checklistCas.remember([{ ...draft.item, version: draft.baseVersion }])
      }
      allResponses.value.set(itemId, draft.item)
      queue.mark(itemId)
      restored = true
    }
    if (!restored) return
    try {
      await queue.flush()
    } catch {
      // 保留原始 baseVersion；不能将新 GET 版本套到旧草稿上自动重放。
    }
  }

  /** 加载 checklist-responses 数据 */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
      checklistCas.remember(responses)
      queue.resetBlockedError()
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && ITEM_PREFIXES.some((p) => r.item_id.startsWith(p))) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
      await restoreDrafts()
    } catch (error: unknown) {
      if (isChecklistDraftAccessDenied(error)) {
        ElMessage.warning('无权读取底稿数据，本地草稿未恢复')
        return
      }
      await restoreDrafts()
      ElMessage.warning('G6(main)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g6-other-bond-investment-main 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g6-other-bond-investment-main' },
        _silent: true,
      } as any)
      const payload = data?.data ?? data
      const sheets = payload?.sheets ?? []
      for (const s of sheets) {
        const key = s.sheet_name || s.name || 'default'
        sheetCache.value[key] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  /** 统一加载入口 */
  async function loadAll(): Promise<void> {
    isLoading.value = true
    loadError.value = null
    try {
      await Promise.all([loadResponses(), selfLoad()])
    } catch (err: any) {
      loadError.value = err?.message || '加载失败'
    } finally {
      isLoading.value = false
    }
  }

  /** 获取缓存的sheet数据 */
  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /**
   * 从sheetCache中解析出完整的G6MainContent结构
   * 用于从render-config返回的html_data中提取各section数据
   */
  function parseContent(): Partial<G6MainContent> {
    const result: Partial<G6MainContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G6-1') || key.includes('审定')) {
        result.adjudication = content as G6MainContent['adjudication']
      } else if (key.includes('G6-2') || key.includes('明细')) {
        result.detail = content as G6MainContent['detail']
      } else if (key.includes('G6-3') || key.includes('坏账')) {
        result.badDebtDetail = content as G6MainContent['badDebtDetail']
      } else if (key.includes('G6-4') || key.includes('调整分录')) {
        result.adjustment = content as G6MainContent['adjustment']
      } else if (key.includes('上市')) {
        result.disclosureListed = content as G6MainContent['disclosureListed']
      } else if (key.includes('国企')) {
        result.disclosureSOE = content as G6MainContent['disclosureSOE']
      }
    }

    return result
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  /** 标记当前本地快照并经 generation-safe 队列串行保存。 */
  async function _doSave(items: ChecklistResponse[]): Promise<void> {
    if (items.length === 0) return
    queue.markMany(items.map((item) => item.item_id))
    await queue.flush()
  }

  /** 立即保存指定 item（结论/状态/选择类字段触发） */
  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
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
    await _doSave([updated])
  }

  /** 批量保存多个 items */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    const patches = new Map<string, Partial<ChecklistResponse>>()
    for (const { itemId, data } of items) {
      patches.set(itemId, { ...patches.get(itemId), ...data })
    }
    const toSave: ChecklistResponse[] = []
    for (const [itemId, data] of patches) {
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

  /** 子composable通过 CustomEvent 批量保存 */
  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    await _doSave(items)
  }

  /** debounce 2000ms 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    _pendingItems.add(itemId)

    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 2000)
    _debounceTimers.set(itemId, timer)
  }

  /**
   * 保存完整 content JSON（POST到workpaper content端点）
   * 用于保存G6 main组所有sheet的完整结构化数据
   */
  async function saveContent(content: Partial<G6MainContent>): Promise<void> {
    if (!wpId.value) return
    try {
      await http.post(`/api/workpapers/${wpId.value}/content`, {
        project_id: projectId.value,
        content,
      })
      opts.onAfterSave?.()
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('内容保存失败，请稍后重试')
      }
    }
  }

  // ─── TB writeback（已移除） ───────────────────────────────────────────────
  // 原 writebackTB(adjudicatedAmount) 走 TB 回写变体端点
  // POST /api/projects/{pid}/trial_balance（科目 1503）。实证 GtG6OtherBondMain.vue 未
  // destructure/调用它、无任何测试消费 ⇒ 零消费死代码。G6 真实回写在 useG6MainAdjudication
  // （aggregateG6WritebackNets）。已移除 —— TB 回写走显式发布门 publish-to-tb。
  // 该变体端点字面量亦纳入 task 18 CI 守卫。
  // spec: tb-writeback-explicit-publish-gate Task 17 批C（Property 9）

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────

  async function _flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    _pendingItems.clear()
    await queue.flush()
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  registerPendingFlusher(_flushPending)

  onScopeDispose(() => {
    void _flushPending().catch(() => undefined)
  })

  return {
    // State
    allResponses,
    isLoading,
    loadError,
    sheetCache,
    // Load
    loadAll,
    selfLoad,
    getSheet,
    parseContent,
    // Save
    saveImmediate,
    saveBatch,
    saveItemsFromEvent,
    debouncedSave,
    saveContent,
    flushPending: _flushPending,
    // 注：TB writeback（writebackTB）已作为零消费死代码移除（见上，Task 17 批C）
  }
}

export default useG6MainFormData
