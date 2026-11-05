import { ref, onScopeDispose, inject, type InjectionKey, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

export type G5LonRecFormData = ReturnType<typeof useG5LonRecFormData>
export const G5FormDataKey: InjectionKey<G5LonRecFormData> = Symbol('g5FormData')

/** 优先注入宿主共享实例，避免各 Tab 重复 fetch / Map 分叉 */
export function useInjectedG5FormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}): G5LonRecFormData {
  return inject(G5FormDataKey, null) ?? useG5LonRecFormData(opts)
}

export function useG5LonRecFormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => opts.wpId.value,
    ownsItem: (itemId) => itemId.startsWith('G5-'),
    versionOf: checklistCas.version,
  })
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!opts.wpId.value) throw new Error('缺少底稿标识，无法保存')
      try {
        await checklistCas.save({
          wpId: opts.wpId.value,
          projectId: opts.projectId.value,
          items,
        })
        opts.onAfterSave?.()
      } catch (error: unknown) {
        const message = (error as { message?: unknown })?.message
        if (message !== 'canceled') ElMessage.error('保存失败，请检查网络后重试')
        throw error
      }
    },
    onPending: drafts.store,
    onSettled: drafts.clear,
    onRecoveryRequired: drafts.markRecoveryRequired,
    blockOnError: isNonRetryableChecklistSaveError,
  })
  const itemPrefix = 'G5-'

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

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      checklistCas.remember(responses)
      queue.resetBlockedError()
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(itemPrefix)) {
          map.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
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
      ElMessage.warning('G5数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'g5-long-term-receivable' }, _silent: true,
          } as any)
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }
        })(),
      ])
    } finally { isLoading.value = false }
  }

  async function _doSave(items: ChecklistResponse[]): Promise<void> {
    if (items.length === 0) return
    queue.markMany(items.map((item) => item.item_id))
    await queue.flush()
  }

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    await _doSave([updated])
  }

  /** 批量保存：单次 PUT，避免上年结转等多 item 更新半成功 */
  async function saveBatch(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    const payload = items.map((item) => {
      const existing = allResponses.value.get(item.item_id) || {
        item_id: item.item_id,
        conclusion: null,
        remark: null,
      }
      const updated = { ...existing, ...item, item_id: item.item_id }
      allResponses.value.set(item.item_id, updated)
      return {
        item_id: updated.item_id,
        conclusion: updated.conclusion,
        remark: updated.remark,
      }
    })
    await _doSave(payload)
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch((err: unknown) => {
        // 草稿已由队列 persist 的失败路径保留；这里还需把失败显式呈现给当前用户。
        // pendingWrites 仍会把 rejection 交给过渡屏障。
        ElMessage.error('保存失败，请检查网络后重试')
        console.error('[G5] 底稿保存未落库', err)
      })
    }, 2000))
  }

  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG5Writeback 触发）为零消费死代码——TB 回写
  // 已改由 useG5Adjudication.publishToTb（显式确认门 → POST publish-to-tb，科目1531余额口径）
  // 承载，故移除此重复定义及其 return export。

  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    await queue.flush()
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    void flushPending().catch((err: unknown) => {
      // 卸载时没有 UI 可提示：至少留下可排查的痕迹，不能让失败的保存彻底无痕消失。
      console.error('[G5] 卸载时仍有未落库的底稿保存', err)
    })
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    loadAll,
    getSheet,
    saveImmediate,
    saveBatch,
    debouncedSave,
    flushPending,
  }
}
