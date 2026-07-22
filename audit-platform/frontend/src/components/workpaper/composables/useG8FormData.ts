import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG8FormData — G8 其他权益工具投资底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { G8_ACCOUNT_CODE } from './g8Constants'
import type { ChecklistResponse } from './useF1FormData'

const DRAFT_PREFIX = 'g8-draft'

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

export function useG8FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const _auditYearRef = useWorkpaperAuditYear()

  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  function restoreDrafts(): void {
    if (!opts.wpId.value) return
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(`${DRAFT_PREFIX}:${opts.wpId.value}:`)) continue
      try {
        const itemId = key.slice(`${DRAFT_PREFIX}:${opts.wpId.value}:`.length)
        const updated = JSON.parse(localStorage.getItem(key) || '') as ChecklistResponse
        if (itemId && updated?.item_id) {
          allResponses.value.set(itemId, updated)
          void saveImmediate(itemId, updated, 1)
          localStorage.removeItem(key)
        }
      } catch { /* ignore */ }
    }
  }

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        const id = r.item_id ?? ''
        if (id.startsWith('G8')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
      restoreDrafts()
    } catch {
      ElMessage.warning('G8数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g8-other-equity-instruments' },
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

  function emitWorkpaperSaved(): void {
    if (!opts.wpId.value || !opts.projectId.value) return
    try {
      eventBus.emit('workpaper:saved', {
        projectId: opts.projectId.value,
        wpId: opts.wpId.value,
      })
    } catch { /* silent */ }
  }

  async function saveImmediate(
    itemId: string,
    data: Partial<ChecklistResponse>,
    retries = 3,
  ): Promise<void> {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    for (let i = 0; i < retries; i++) {
      try {
        await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
          project_id: opts.projectId.value,
          items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
        })
        try {
          localStorage.removeItem(draftKey(opts.wpId.value, itemId))
        } catch { /* ignore */ }
        emitWorkpaperSaved()
        return
      } catch {
        if (i < retries - 1) await new Promise((r) => setTimeout(r, 500 * 2 ** i))
      }
    }
    try {
      localStorage.setItem(draftKey(opts.wpId.value, itemId), JSON.stringify(updated))
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

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  function getTrialBalanceAmount(): number {
    const tb = renderMeta.value?.trial_balance?.current_amount
    return typeof tb === 'number' ? tb : parseFloat(String(tb ?? 0)) || 0
  }

  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    const seeded = renderMeta.value?.tb_values?.current_amount ?? renderMeta.value?.trial_balance?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G8_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G8_ACCOUNT_CODE),
      )
      if (!hit) return null
      const debit = Number(hit.debit_amount ?? hit.period_debit ?? 0)
      const credit = Number(hit.credit_amount ?? hit.period_credit ?? 0)
      return debit - credit
    } catch {
      return null
    }
  }

  async function writebackTB(auditedAmount: number, optsWrite?: { forceToast?: boolean }): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: G8_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      }, { _silent: true } as any)
      await saveImmediate('G8-adj-tb-writeback', {
        remark: JSON.stringify({ accountCode: G8_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('G8-1-adjudicated-amount', { conclusion: String(auditedAmount) })
      if (optsWrite?.forceToast) {
        ElMessage.success(`已回写试算表 ${G8_ACCOUNT_CODE}：${auditedAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
      }
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  function flushPending(): void {
    for (const [itemId, timer] of _debounceTimers) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
      const row = allResponses.value.get(itemId)
      if (row) void saveImmediate(itemId, row)
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
    accountCode: G8_ACCOUNT_CODE,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
    getTrialBalanceAmount,
    fetchTrialBalanceAmount,
    writebackTB,
    writebackTrialBalance: writebackTB,
  }
}
