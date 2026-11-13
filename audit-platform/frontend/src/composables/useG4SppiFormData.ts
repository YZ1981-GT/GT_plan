/**
 * useG4SppiFormData — G4 债权投资(SPPI组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/
 * Task: 1.4
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 G4-sppi-* 数据
 * - debounce 2000ms 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - selfLoad逻辑（render-config?force_component_type=g4-bond-investment-sppi）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '@/components/workpaper/sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '@/components/workpaper/sync/checklistDraftStore'
import { registerPendingFlusher } from '@/components/workpaper/sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseG4SppiFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

const G4_SPPI_ITEM_PREFIXES = ['G4-sppi-', 'G4-3-', 'G4-5-', 'G4-6-', 'G4-7-', 'G4-8-']

function isG4SppiItem(itemId: string): boolean {
  return G4_SPPI_ITEM_PREFIXES.some((prefix) => itemId.startsWith(prefix))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4SppiFormData(opts: UseG4SppiFormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => wpId.value,
    ownsItem: isG4SppiItem,
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
      // 冲突时保留旧 baseVersion 和本地草稿，不能以当前服务器版本自动覆盖。
    }
  }

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      checklistCas.remember(responses)
      queue.resetBlockedError()
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && isG4SppiItem(r.item_id)) {
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
      ElMessage.warning('G4(SPPI)数据加载失败，可手动填写')
    }
  }

  /** selfLoad: 当组件在bundle内嵌时无htmlData，自行调render-config加载sheet数据 */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g4-bond-investment-sppi' },
        _silent: true,
      } as any)
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
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

  // ─── Save ────────────────────────────────────────────────────────────────

  /** 标记当前本地快照并经 generation-safe 队列串行保存。 */
  async function _doSave(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>): Promise<void> {
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

  /** 子 composable 通过 CustomEvent 批量保存 */
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
    allResponses,
    isLoading,
    loadError,
    sheetCache,
    loadAll,
    getSheet,
    saveImmediate,
    saveBatch,
    saveItemsFromEvent,
    debouncedSave,
    flushPending: _flushPending,
  }
}

export default useG4SppiFormData
