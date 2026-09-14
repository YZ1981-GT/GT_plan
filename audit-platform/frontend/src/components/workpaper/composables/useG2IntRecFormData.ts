import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { G2_ACCOUNT_CODE } from './g2AdjudicationItems'
import type { ChecklistResponse } from './useF1FormData'

export function useG2IntRecFormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const itemPrefix = 'G2-'

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(itemPrefix)) {
          map.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('G2数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'g2-interest-receivable' }, _silent: true,
          } as any)
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }
        })(),
      ])
    } finally { isLoading.value = false }
  }

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
      project_id: opts.projectId.value,
      items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
    })
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void saveImmediate(itemId, updated)
    }, 2000))
  }

  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }

  /** 将 G2-1 审定净值回写试算平衡表 1132（对齐 G11） */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: G2_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      await saveImmediate('G2-1-tb-writeback', {
        item_id: 'G2-1-tb-writeback',
        conclusion: null,
        remark: JSON.stringify({ accountCode: G2_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('G2-1-adjudicated-amount', {
        item_id: 'G2-1-adjudicated-amount',
        conclusion: String(auditedAmount),
        remark: null,
      })
    } catch {
      ElMessage.warning('审定数回写试算失败，请手动确认试算表 1132')
    }
  }

  function flushPending(): void {
    for (const [itemId, timer] of _debounceTimers.entries()) {
      clearTimeout(timer)
      const resp = allResponses.value.get(itemId)
      if (resp) void saveImmediate(itemId, resp)
    }
    _debounceTimers.clear()
  }

  onScopeDispose(() => {
    flushPending()
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
    writebackTrialBalance,
    writebackTB: writebackTrialBalance,
    accountCode: G2_ACCOUNT_CODE,
  }
}
