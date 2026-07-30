/**
 * useG3FormData — G3 应收股利数据加载/保存/selfLoad + TB 回写
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 3.1
 * 收敛：原 useG3DivRecFormData（含 writeback）并入本文件为唯一入口。
 */
import { ref, onScopeDispose, type Ref } from 'vue'
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

  const ITEM_PREFIX = 'G3-'
  const DETAIL_KEY = 'G3-2-detail-rows'

  function bumpDetailRevisionIfNeeded(itemId: string): void {
    if (itemId === DETAIL_KEY) detailRevision.value += 1
  }

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
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
    } catch {
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
    if (!wpId.value || items.length === 0) return
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
      opts.onAfterSave?.()
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
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
    // 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失
    //    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。
    //    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。
    const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of deduped) {
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
    _pendingItems.add(itemId)

    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([updated])
    }, 500)
    _debounceTimers.set(itemId, timer)
  }

  /** 将 G3-1 期末审定合计回写试算平衡表 1131 */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: G3_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      await saveImmediate('G3-1-tb-writeback', {
        item_id: 'G3-1-tb-writeback',
        conclusion: null,
        remark: JSON.stringify({ accountCode: G3_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('G3-1-adjudicated-amount', {
        item_id: 'G3-1-adjudicated-amount',
        conclusion: String(auditedAmount),
        remark: null,
      })
    } catch {
      ElMessage.warning('审定数回写试算失败，请手动确认试算表 1131')
    }
  }

  function flushPending(): void {
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    if (_pendingItems.size > 0) {
      const items: ChecklistResponse[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) void _doSave(items)
    }
  }

  onScopeDispose(() => {
    flushPending()
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
    writebackTrialBalance,
    writebackTB: writebackTrialBalance,
    accountCode: G3_ACCOUNT_CODE,
  }
}

export default useG3FormData
