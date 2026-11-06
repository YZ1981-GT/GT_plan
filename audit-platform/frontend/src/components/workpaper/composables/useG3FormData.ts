/**
 * useG3FormData — G3 应收股利数据加载/保存/selfLoad + TB 回写
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 3.1
 * 收敛：原 useG3DivRecFormData（含 writeback）并入本文件为唯一入口。
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import { G3_ACCOUNT_CODE } from './g3Constants'

export { G3_ACCOUNT_CODE }

export interface UseG3FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

export function useG3FormData(opts: UseG3FormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})
  /** G3-2 明细保存后自增，供 G3-1/4/5 感知热更新 */
  const detailRevision = ref(0)

  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => wpId.value,
    ownsItem: (itemId) => itemId.startsWith('G3-'),
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

  const ITEM_PREFIX = 'G3-'
  const DETAIL_KEY = 'G3-2-detail-rows'

  function bumpDetailRevisionIfNeeded(itemId: string): void {
    if (itemId === DETAIL_KEY) detailRevision.value += 1
  }

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
    if (restored) {
      try {
        await queue.flush()
      } catch { /* 草稿和 pending 保留，不能自动覆盖远端 */ }
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
        if (r.item_id?.startsWith(ITEM_PREFIX)) {
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
      ElMessage.warning('G3数据加载失败，可手动填写')
    }
  }

  /** selfLoad: bundle 内嵌时无 htmlData，自行调 render-config */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g3-dividend-receivable' },
        _silent: true,
      } as any)
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞
    }
  }

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

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  async function _doSave(
    items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>,
  ): Promise<void> {
    if (items.length === 0) return
    queue.markMany(items.map((item) => item.item_id))
    await queue.flush()
  }

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
    bumpDetailRevisionIfNeeded(itemId)
    await _doSave([updated])
  }

  async function saveBatch(
    items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>,
  ): Promise<void> {
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
      bumpDetailRevisionIfNeeded(itemId)
      toSave.push(updated)
    }
    await _doSave(toSave)
  }

  /** debounce 500ms 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    bumpDetailRevisionIfNeeded(itemId)
    queue.mark(itemId)
    _pendingItems.add(itemId)

    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 500)
    _debounceTimers.set(itemId, timer)
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 provide(G3WritebackTbKey) → useG3Adjudication 注入调用）
  // 为零消费死代码——TB 回写已改由 useG3Adjudication.publishToTb（显式确认门 → POST publish-to-tb，
  // 科目1131余额口径）承载，故移除此重复定义及其 return export。

  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    _pendingItems.clear()
    await queue.flush()
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    void flushPending().catch(() => undefined)
  })

  return {
    allResponses,
    detailRevision,
    isLoading,
    loadError,
    sheetCache,
    loadAll,
    getSheet,
    saveImmediate,
    saveBatch,
    debouncedSave,
    flushPending,
    accountCode: G3_ACCOUNT_CODE,
  }
}

export default useG3FormData
