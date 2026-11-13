import { fetchTrialBalanceRows, tbSumUnder } from '@/services/trialBalanceRows'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG13FormData — G13 公允价值变动收益底稿数据层
 * Spec: .kiro/specs/g13-fair-value-changes/ Task 4.1
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { createChecklistCasClient, isChecklistDraftAccessDenied, isNonRetryableChecklistSaveError } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import { confirmChecklistDraftConflict, createChecklistDraftStore } from '../sync/checklistDraftStore'
import { registerPendingFlusher } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { G13_ACCOUNT_CODE } from './g13Constants'
import type { ChecklistResponse } from './useF1FormData'

export function useG13FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const _auditYearRef = useWorkpaperAuditYear()

  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const checklistCas = createChecklistCasClient()
  const drafts = createChecklistDraftStore<ChecklistResponse>({
    namespace: 'strict-cas-draft',
    wpId: () => opts.wpId.value,
    ownsItem: (itemId) => itemId.startsWith('G13'),
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
      } catch (error) {
        ElMessage.error('保存失败，本地草稿已保留，请刷新后重试')
        throw error
      }
    },
    onPending: drafts.store,
    onSettled: drafts.clear,
    onRecoveryRequired: drafts.markRecoveryRequired,
    blockOnError: isNonRetryableChecklistSaveError,
  })

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
        const id = r.item_id ?? ''
        if (id.startsWith('G13')) {
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
      ElMessage.warning('G13数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g13-fair-value-changes' },
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
    queue.mark(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch((err: unknown) => {
        // 草稿已由队列 persist 的失败路径保留；这里还需把失败显式呈现给当前用户。
        // pendingWrites 仍会把 rejection 交给过渡屏障。
        ElMessage.error('保存失败，请检查网络后重试')
        console.error('[G13] 底稿保存未落库', err)
      })
    }, 2000))
  }

  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const { rows: list } = await fetchTrialBalanceRows(opts.projectId.value, { year: _year, accountPrefix: G13_ACCOUNT_CODE })
      // 本期发生额 = 试算表未审数（单边口径，与报表同）；原先读端点没有的借 / 贷字段算差额，恒 0
      return tbSumUnder(list, G13_ACCOUNT_CODE, 'unadjusted_amount')
    } catch {
      return null
    }
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG13Writeback 触发）为零消费死代码——TB 回写
  // 已改由 useG13Adjudication.publishToTb（显式确认门 → POST publish-to-tb，科目6101发生额
  // 口径 occurrence）承载，故移除此重复定义及其 return export。

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    await queue.flush()
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    // 原先只清 timer、不冲刷：导航离开时这些待存编辑被静默丢弃。
    // flushPending 自身会清 timer，所以这里不必再单独清。
    void flushPending().catch((err: unknown) => {
      // 卸载时没有 UI 可提示：至少留下可排查的痕迹，不能让失败的保存彻底无痕消失。
      console.error('[G13] 卸载时仍有未落库的底稿保存', err)
    })
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    renderMeta,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
    fetchTrialBalanceAmount,
  }
}
