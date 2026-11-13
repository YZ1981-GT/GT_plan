import { ref, onScopeDispose, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import { useWorkpaperAuditYear } from './workpaperAuditYear'

export function useG1TraFinFormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => opts.wpId.value,
    ownsItem: (itemId) => itemId.startsWith('G1-'),
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
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  async function loadResponses(): Promise<boolean> {
    if (!opts.wpId.value) return false
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      checklistCas.remember(responses)
      queue.resetBlockedError()
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('G1-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
      return true
    } catch (error: unknown) {
      if (isChecklistDraftAccessDenied(error)) {
        ElMessage.warning('无权读取底稿数据，本地草稿未恢复')
        return false
      }
      ElMessage.warning('G1数据加载失败，可手动填写')
      return true
    }
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
          // 保留只回显，不 mark/不发送；下一次用户明确编辑才用服务器当前版本保存。
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
      } catch {
        // 保留草稿和 queue pending；版本变化必须由用户显式处理，不能自动覆盖远端。
      }
    }
  }

  async function selfLoad(): Promise<void> {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g1-trading-financial-assets' },
      _silent: true,
    } as any)
    const data = res?.data ?? res
    const sheets = data?.sheets ?? data?.data?.sheets ?? []
    for (const sheet of sheets) {
      sheetCache.value[sheet.sheet_name || sheet.name || 'default'] = sheet.html_data ?? sheet
    }
    // responses_snapshot 只在 checklist GET 没有该条目时充当降级源。payload 和 version
    // 必须同源成对采用，不能用快照的新 version 为 GET 的旧值背书。
    const snapshot = data?.html_data?.responses_snapshot ?? data?.responses_snapshot
    if (snapshot && typeof snapshot === 'object' && !Array.isArray(snapshot)) {
      for (const [itemId, value] of Object.entries(snapshot)) {
        if (!itemId.startsWith('G1-') || allResponses.value.has(itemId)) continue
        const item = value as any
        checklistCas.remember([{ item_id: itemId, ...item }])
        allResponses.value.set(itemId, {
          item_id: itemId,
          conclusion: item?.conclusion ?? null,
          remark: item?.remark ?? null,
        })
      }
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      // checklist GET 是 CAS 权威基线；render snapshot 仅在 GET 没有该条目时降级采用。
      // 并发合并会把旧 payload 与另一请求的新版本令牌拼在一起，服务端会错误接受覆盖。
      const canRestoreDrafts = await loadResponses()
      if (canRestoreDrafts) {
        await restoreDrafts()
        await selfLoad()
      }
    } finally {
      isLoading.value = false
    }
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

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    // 输入一发生就记录 generation 和草稿；不能等 2 秒 timer，否则刷新会丢本地编辑。
    queue.mark(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(
      itemId,
      setTimeout(() => {
        _debounceTimers.delete(itemId)
        // 当前 item 已在输入时 mark；timer 只负责启动同一 generation 的发送。
        void queue.flush().catch((err: unknown) => {
        // 草稿已由队列 persist 的失败路径保留；这里还需把失败显式呈现给当前用户。
        // pendingWrites 仍会把 rejection 交给过渡屏障。
        ElMessage.error('保存失败，请检查网络后重试')
        console.error('[G1] 底稿保存未落库', err)
      })
      }, 2000),
    )
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG1Writeback 触发）为零消费死代码——TB 回写
  // 已改由 G1-1 审定表「发布到试算表」显式确认门（G1TabAdjudication.handlePublishToTb →
  // POST publish-to-tb，科目1501余额口径）承载，故移除此重复定义及其 return export。

  /** 切表/卸载前取消防抖并发送已在输入时标记的最新 generation。 */
  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    await queue.flush()
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    void flushPending().catch((err: unknown) => {
      // 卸载时没有 UI 可提示：至少留下可排查的痕迹，不能让失败的保存彻底无痕消失。
      console.error('[G1] 卸载时仍有未落库的底稿保存', err)
    })
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
  }
}
