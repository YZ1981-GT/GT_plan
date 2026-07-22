import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG13FormData — G13 公允价值变动收益底稿数据层
 * Spec: .kiro/specs/g13-fair-value-changes/ Task 4.1
 */
import { ref, onScopeDispose, type Ref } from 'vue'
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

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        const id = r.item_id ?? ''
        if (id.startsWith('G13')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
    } catch {
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

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
      project_id: opts.projectId.value,
      items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
    })
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void saveImmediate(itemId, updated)
    }, 2000))
  }

  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G13_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G13_ACCOUNT_CODE),
      )
      if (!hit) return null
      const debit = Number(hit.debit_amount ?? hit.period_debit ?? 0)
      const credit = Number(hit.credit_amount ?? hit.period_credit ?? 0)
      return credit - debit
    } catch {
      return null
    }
  }

  /** 审定数回写试算表（科目 6101，损益类） */
  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: G13_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      await saveImmediate('G13-adj-tb-writeback', {
        remark: JSON.stringify({ accountCode: G13_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('G13-1-adjudicated-amount', { conclusion: String(auditedAmount) })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  function flushPending(): void {
    for (const [itemId, timer] of _debounceTimers.entries()) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
      const data = allResponses.value.get(itemId)
      if (data) void saveImmediate(itemId, data)
    }
  }

  onScopeDispose(() => {
    for (const t of _debounceTimers.values()) clearTimeout(t)
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
    writebackTrialBalance,
  }
}
