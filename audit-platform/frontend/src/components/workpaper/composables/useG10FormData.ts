import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG10FormData — G10 交易性金融负债底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { G10_ACCOUNT_ALIASES, G10_ACCOUNT_CODE, G10_ACCOUNT_NAME } from './g10Constants'
import { resolveG10TbRow, g10TbResolvedCode, resolveG10TbBalanceFromList } from './g10TbResolve'
import type { ChecklistResponse } from './useF1FormData'

const DRAFT_PREFIX = 'g10-draft'

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

export function useG10FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
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
        if (id.startsWith('G10')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
      restoreDrafts()
    } catch {
      ElMessage.warning('G10数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'g10-trading-financial-liabilities' },
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
      ElMessage.warning(`G10 数据暂存本地（${itemId}），网络恢复后将自动同步`)
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
      ?? renderMeta.value?.trial_balance?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      return resolveG10TbBalanceFromList(list)
    } catch {
      return null
    }
  }

  let _tbMissingWarned = false

  /**
   * 审定数回写试算表（对标 G9）。
   * 按别名/科目名称解析实际 TB 行；科目缺失时仅提示一次。
   */
  async function writebackTB(auditedAmount: number, optsWrite?: { forceToast?: boolean }): Promise<boolean> {
    if (!opts.projectId.value) return false
    const _year = _auditYearRef.value
    let accountCode = G10_ACCOUNT_CODE
    try {
      if (_year != null) {
        const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
          params: { year: _year, account_prefix: G10_ACCOUNT_CODE },
          _silent: true,
        } as any)
        const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
        const hit = resolveG10TbRow(list)
        if (!hit) {
          if (optsWrite?.forceToast || !_tbMissingWarned) {
            _tbMissingWarned = true
            ElMessage.info(
              `试算表未找到「${G10_ACCOUNT_NAME}」（已试 ${G10_ACCOUNT_ALIASES.join('/')}）。`
              + '若本年无此科目可忽略；有余额请检查科目映射后重试发布。',
            )
          }
          await saveImmediate('G10-1-adjudicated-amount', { conclusion: String(auditedAmount) })
          return false
        }
        accountCode = g10TbResolvedCode(hit)
      }
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: auditedAmount,
      }, { _silent: true } as any)
      await saveImmediate('G10-adj-tb-writeback', {
        remark: JSON.stringify({ accountCode, auditedAmount }),
      })
      await saveImmediate('G10-1-adjudicated-amount', { conclusion: String(auditedAmount) })
      return true
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || ''
      ElMessage.warning(
        detail
          ? `审定数回写失败：${detail}`
          : '审定数回写失败，请手动确认试算表数据',
      )
      return false
    }
  }

  async function writebackTrialBalance(auditedAmount: number): Promise<void> {
    await writebackTB(auditedAmount, { forceToast: true })
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

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
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
    fetchTrialBalanceAmount,
    writebackTB,
    writebackTrialBalance,
  }
}
