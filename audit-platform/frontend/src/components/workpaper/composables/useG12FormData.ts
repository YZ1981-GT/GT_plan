import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG12FormData — G12 净敞口套期收益底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { G12_ACCOUNT_CODE } from './g12Constants'
import type { ChecklistResponse } from './useF1FormData'

export function useG12FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
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
        if (id.startsWith('G12')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('G12数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g12-net-hedge-gains' },
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

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>, retries = 3): Promise<void> {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    for (let i = 0; i < retries; i++) {
      try {
        await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
          project_id: opts.projectId.value,
          items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
        })
        return
      } catch {
        if (i < retries - 1) await new Promise((r) => setTimeout(r, 500 * 2 ** i))
      }
    }
    try {
      localStorage.setItem(`g12-draft:${opts.wpId.value}:${itemId}`, JSON.stringify(updated))
    } catch { /* ignore */ }
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
        params: { year: _year, account_prefix: G12_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G12_ACCOUNT_CODE),
      )
      if (!hit) return null
      const debit = Number(hit.debit_amount ?? hit.period_debit ?? 0)
      const credit = Number(hit.credit_amount ?? hit.period_credit ?? 0)
      return credit - debit
    } catch {
      return null
    }
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG12Writeback 触发）为零消费死代码——TB 回写
  // 已改由 useG12Adjudication.publishToTb（显式确认门 → POST publish-to-tb，科目6103发生额
  // 口径 occurrence）承载，故移除此重复定义及其 return export。

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /** 卸载前刷出未落盘的 debounce 保存（比照 F2/G11） */
  function flushPending(): void {
    for (const [itemId, timer] of _debounceTimers.entries()) {
      clearTimeout(timer)
      const resp = allResponses.value.get(itemId)
      if (resp) void saveImmediate(itemId, resp, 1)
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
    renderMeta,
    accountCode: G12_ACCOUNT_CODE,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
    fetchTrialBalanceAmount,
  }
}
