import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { createChecklistCasClient } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'
import type { ChecklistResponse } from './useF1FormData'

export function useG4BonInvFormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const cas = createChecklistCasClient()
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!opts.wpId.value) throw new Error('缺少底稿标识，无法保存')
      await cas.save({ wpId: opts.wpId.value, projectId: opts.projectId.value, items })
    },
  })
  const itemPrefix = 'G4-'

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      cas.remember(responses)
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(itemPrefix)) {
          map.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('G4数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'g4-bond-investment-main' }, _silent: true,
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
    const timer = _debounceTimers.get(itemId)
    if (timer) clearTimeout(timer)
    _debounceTimers.delete(itemId)
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    await queue.flush()
  }

  /** 批量保存：单次 strict-CAS PUT，避免上年结转等多 item 更新半成功。 */
  async function saveBatch(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    const payload = items.map((item) => {
      const timer = _debounceTimers.get(item.item_id)
      if (timer) clearTimeout(timer)
      _debounceTimers.delete(item.item_id)
      const existing = allResponses.value.get(item.item_id) || {
        item_id: item.item_id,
        conclusion: null,
        remark: null,
      }
      const updated = { ...existing, ...item, item_id: item.item_id }
      allResponses.value.set(item.item_id, updated)
      return updated
    })
    queue.markMany(payload.map((item) => item.item_id))
    await queue.flush()
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    queue.mark(itemId)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 2000))
  }

  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }

  async function flushPending(): Promise<void> {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()
    await queue.flush()
  }

  onScopeDispose(() => { void flushPending().catch(() => undefined) })

  return {
    isLoading, sheetCache, allResponses, loadAll, getSheet,
    saveImmediate, saveBatch, debouncedSave, flushPending,
  }
}