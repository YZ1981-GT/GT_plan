/**
 * useH10FormData — H10 资产处置损益底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { H10_ACCOUNT_CODE } from './h10Constants'
import { parseNum } from './useH10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

const DRAFT_PREFIX = 'h10-draft'

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

export function useH10FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
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
      } catch { /* ignore corrupt draft */ }
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
        if (id.startsWith('H10')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
      restoreDrafts()
    } catch {
      ElMessage.warning('H10数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'h10-asset-disposal-income' },
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
        return
      } catch {
        if (i < retries - 1) await new Promise((r) => setTimeout(r, 500 * 2 ** i))
      }
    }
    try {
      localStorage.setItem(draftKey(opts.wpId.value, itemId), JSON.stringify(updated))
      ElMessage.warning(`H10 数据暂存本地（${itemId}），网络恢复后将自动同步`)
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

  /** 6115 损益类：贷方发生 − 借方发生 */
  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: H10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(H10_ACCOUNT_CODE),
      )
      if (!hit) return null
      const credit = parseNum(hit.credit_amount ?? hit.period_credit)
      const debit = parseNum(hit.debit_amount ?? hit.period_debit)
      return credit - debit
    } catch {
      return null
    }
  }

  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: H10_ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      await saveImmediate('H10-adj-tb-writeback', {
        remark: JSON.stringify({ accountCode: H10_ACCOUNT_CODE, auditedAmount }),
      })
      await saveImmediate('H10-1-adjudicated-amount', { conclusion: String(auditedAmount) })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /** H6 disposal:completed → 追加 H10-2 明细行（主入口唯一监听，防重复） */
  function handleDisposalCompleted(payload: Record<string, unknown>): void {
    const ITEM_ID = 'H10-detail-rows'
    const linkageId = String(payload.linkageId ?? `h6-${Date.now()}`)
    let rows: any[] = []
    try {
      const raw = allResponses.value.get(ITEM_ID)?.remark
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) rows = parsed
      }
    } catch { /* ignore */ }
    if (rows.some((r) => r.linkageId === linkageId)) return
    rows = [
      ...rows,
      {
        id: linkageId,
        linkageId,
        assetName: payload.assetName ?? 'H6清理结转',
        assetType: payload.assetType ?? '固定资产',
        sourceWp: 'H6',
        disposalIncome: payload.disposalIncome,
        originalCost: payload.netBookValue,
      },
    ]
    debouncedSave(ITEM_ID, { remark: JSON.stringify(rows) })
  }

  /** H1~H8 disposal:source-updated → 更新/追加明细来源行 */
  function handleSourceDisposalUpdated(payload: Record<string, unknown>): void {
    const ITEM_ID = 'H10-detail-rows'
    const linkageId = String(payload.linkageId ?? `${payload.sourceWp}-${Date.now()}`)
    let rows: any[] = []
    try {
      const raw = allResponses.value.get(ITEM_ID)?.remark
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) rows = parsed
      }
    } catch { /* ignore */ }
    const idx = rows.findIndex((r) => r.linkageId === linkageId)
    const entry = {
      ...(idx >= 0 ? rows[idx] : { id: linkageId }),
      linkageId,
      assetName: payload.assetName ?? rows[idx]?.assetName ?? '',
      sourceWp: payload.sourceWp ?? 'OTHER',
      sourceIndex: payload.sourceIndex ?? '',
      disposalGainLoss: payload.disposalGainLoss,
    }
    if (idx >= 0) rows[idx] = entry
    else rows.push(entry)
    debouncedSave(ITEM_ID, { remark: JSON.stringify(rows) })
  }

  onScopeDispose(() => {
    for (const t of _debounceTimers.values()) clearTimeout(t)
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    renderMeta,
    accountCode: H10_ACCOUNT_CODE,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    fetchTrialBalanceAmount,
    writebackTB,
    writebackTrialBalance: writebackTB,
    handleDisposalCompleted,
    handleSourceDisposalUpdated,
  }
}
