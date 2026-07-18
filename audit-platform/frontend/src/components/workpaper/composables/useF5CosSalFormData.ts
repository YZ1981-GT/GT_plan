import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

export function useF5CosSalFormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  /** F5-7 成本倒轧 TB 自动取数（1401/1404/1405 期初期末，来自 render 策略） */
  const rollforwardTb = ref<Record<string, number>>({})
  /** F5-7 校验区审定营业成本回退值（来自 render 策略持久化读取） */
  const adjudicatedCogs = ref<number>(0)
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const itemPrefix = 'F5-'

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
      ElMessage.warning('F5数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'f5-cost-of-sales' }, _silent: true,
          } as any)
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
            const hd = s.html_data ?? s
            sheetCache.value[s.sheet_name || s.name || 'default'] = hd
            // render 策略在各 F5 sheet 的 html_data 中携带 rollforward_tb / adjudicated_cogs
            if (hd && typeof hd === 'object') {
              if (hd.rollforward_tb && typeof hd.rollforward_tb === 'object') {
                rollforwardTb.value = hd.rollforward_tb
              }
              if (hd.adjudicated_cogs != null && hd.adjudicated_cogs !== '') {
                const n = Number(hd.adjudicated_cogs)
                if (Number.isFinite(n)) adjudicatedCogs.value = n
              }
            }
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

  /** 批量保存多个 item（一次 PUT 提交，用于导入/整表提交） */
  async function saveBatch(items: Array<{ item_id: string } & Partial<ChecklistResponse>>) {
    if (!items.length) return
    for (const it of items) {
      const existing = allResponses.value.get(it.item_id) || { item_id: it.item_id, conclusion: null, remark: null }
      allResponses.value.set(it.item_id, { ...existing, ...it })
    }
    await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
      project_id: opts.projectId.value,
      items: items.map((it) => {
        const r = allResponses.value.get(it.item_id)!
        return { item_id: it.item_id, conclusion: r.conclusion, remark: r.remark }
      }),
    })
  }

  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }

  /** 审定数回写试算平衡表（比照 useF3FormData / useF4FormData） */
  async function writebackTrialBalance(accountCode: string, auditedAmount: number): Promise<void> {
    if (!opts.projectId.value) return
    try {
      await api.put(`/api/projects/${opts.projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: auditedAmount,
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  onScopeDispose(() => { for (const t of _debounceTimers.values()) clearTimeout(t) })

  return {
    isLoading,
    sheetCache,
    allResponses,
    rollforwardTb,
    adjudicatedCogs,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    saveBatch,
    writebackTrialBalance,
  }
}
