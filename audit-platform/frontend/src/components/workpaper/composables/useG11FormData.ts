import { fetchTrialBalanceRows, tbSumUnder } from '@/services/trialBalanceRows'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG11FormData — G11 投资收益底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import {
  createChecklistCasClient,
  isChecklistDraftAccessDenied,
  isNonRetryableChecklistSaveError,
  makeChecklistDraft,
  readChecklistDraft,
} from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { checklistDraftKey, checklistDraftPrefix } from '@/composables/workpaper/checklistDraftStorage'
import { confirmChecklistDraftConflict } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { G11_ACCOUNT_CODE } from './g11Constants'
import type { ChecklistResponse } from './useF1FormData'

const DRAFT_PREFIX = 'g11-draft'

function draftKey(wpId: string, itemId: string): string | null {
  return checklistDraftKey(DRAFT_PREFIX, wpId, itemId)
}

export function useG11FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const _auditYearRef = useWorkpaperAuditYear()

  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const checklistCas = createChecklistCasClient()
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: persistRows,
    onPending: storeDrafts,
    onSettled: clearDrafts,
    onRecoveryRequired: (items) => storeDrafts(items, true),
    blockOnError: isNonRetryableChecklistSaveError,
    retry: { attempts: 3, initialDelayMs: 500 },
  })

  async function restoreDrafts(): Promise<void> {
    const prefix = checklistDraftPrefix(DRAFT_PREFIX, opts.wpId.value)
    if (!prefix) return
    let restored = false
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const key = localStorage.key(i)
      if (!key?.startsWith(prefix)) continue
      try {
        const itemId = key.slice(prefix.length)
        const draft = readChecklistDraft<ChecklistResponse>(JSON.parse(localStorage.getItem(key) || ''))
        if (!itemId || !draft || draft.item.item_id !== itemId) continue
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
            clearDrafts([draft.item])
          }
          continue
        }
        if (draft.baseVersion) {
          checklistCas.remember([{ ...draft.item, version: draft.baseVersion }])
        }
        allResponses.value.set(itemId, draft.item)
        queue.mark(itemId)
        restored = true
      } catch { /* ignore corrupt draft */ }
    }
    if (restored) {
      try {
        await queue.flush()
      } catch {
        // 错误已由 persistRows 提示，草稿与 queue.pending 均保留，等待刷新或用户处理。
      }
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
        const id = r.item_id ?? ''
        if (id.startsWith('G11')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
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
      ElMessage.warning('G11数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g11-investment-income' },
      _silent: true,
    } as any)
    const data = res?.data ?? res
    renderMeta.value = data?.html_data ?? data ?? {}
    for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
      const name = s.sheet_name || s.name || 'default'
      sheetCache.value[name] = s.html_data ?? s
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadRenderConfig()])
    } finally {
      isLoading.value = false
    }
  }

  function storeDrafts(
    items: readonly ChecklistResponse[],
    requiresConfirmation = false,
  ): void {
    try {
      for (const item of items) {
        const key = draftKey(opts.wpId.value, item.item_id)
        if (!key) continue
        localStorage.setItem(
          key,
          JSON.stringify(makeChecklistDraft(
            item,
            checklistCas.version(item.item_id),
            requiresConfirmation,
          )),
        )
      }
    } catch { /* localStorage 不可用时仍保留队列 pending，避免伪装保存成功 */ }
  }

  function clearDrafts(items: readonly ChecklistResponse[]): void {
    try {
      for (const item of items) {
        const key = draftKey(opts.wpId.value, item.item_id)
        if (key) localStorage.removeItem(key)
      }
    } catch { /* ignore */ }
  }

  async function persistRows(items: ChecklistResponse[]): Promise<void> {
    if (!opts.wpId.value || items.length === 0) return
    try {
      await checklistCas.save({
        wpId: opts.wpId.value,
        projectId: opts.projectId.value,
        items,
      })
    } catch (error: unknown) {
      ElMessage.warning(
        isNonRetryableChecklistSaveError(error)
          ? '保存被拒绝或版本已变化，本地草稿已保留，请刷新后重试'
          : `G11 数据暂存本地（${items.length} 项），网络恢复后可重试`,
      )
      throw error
    }
  }

  async function saveImmediate(
    itemId: string,
    data: Partial<ChecklistResponse>,
  ): Promise<void> {
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    await queue.flush()
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 2000))
  }

  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const { rows: list } = await fetchTrialBalanceRows(opts.projectId.value, { year: _year, accountPrefix: G11_ACCOUNT_CODE })
      // 本期发生额 = 试算表未审数（单边口径，与报表同）；原先读端点没有的借 / 贷字段算差额，恒 0
      return tbSumUnder(list, G11_ACCOUNT_CODE, 'unadjusted_amount')
    } catch {
      return null
    }
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG11Writeback 触发）为零消费死代码——TB 回写
  // 已改由 useG11Adjudication.publishToTb（显式确认门 → POST publish-to-tb，科目6111发生额
  // 口径 occurrence）承载，故移除此重复定义及其 return export。

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /** 卸载前取消防抖并发送输入时已记录的最新 generation。 */
  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    await queue.flush()
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    void flushPending().catch(() => undefined)
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    renderMeta,
    accountCode: G11_ACCOUNT_CODE,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
    fetchTrialBalanceAmount,
  }
}
