import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import { G1_ACCOUNT_CODE } from './g1AdjudicationItems'
import { useWorkpaperAuditYear } from './workpaperAuditYear'

export function useG1TraFinFormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
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
    } catch {
      ElMessage.warning('G1数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'g1-trading-financial-assets' },
            _silent: true,
          } as any)
          const data = res?.data ?? res
          const sheets = data?.sheets ?? data?.data?.sheets ?? []
          for (const s of sheets) {
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }
        })(),
      ])
    } finally {
      isLoading.value = false
    }
  }

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
      project_id: opts.projectId.value,
      items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
    })
    opts.onAfterSave?.()
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(
      itemId,
      setTimeout(() => {
        _debounceTimers.delete(itemId)
        void saveImmediate(itemId, updated)
      }, 2000),
    )
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /** 将 G1-1 审定账面余额回写试算平衡表 1501 */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: G1_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      await saveImmediate('G1-1-tb-writeback', {
        item_id: 'G1-1-tb-writeback',
        conclusion: null,
        remark: JSON.stringify({ accountCode: G1_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('G1-1-adjudicated-amount', {
        item_id: 'G1-1-adjudicated-amount',
        conclusion: String(auditedAmount),
        remark: null,
      })
    } catch {
      ElMessage.warning('审定数回写试算失败，请手动确认试算表 1501')
    }
  }

  /** 切表/卸载前刷出未到点的 debounce，避免 <2s 编辑丢失 */
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
  }
}
