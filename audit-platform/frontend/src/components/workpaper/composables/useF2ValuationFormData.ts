/**
 * useF2ValuationFormData — F2 计价减值组数据层（比照 useF2FormData）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { createChecklistCasClient } from '@/composables/workpaper/checklistCas'
import { createChecklistWriteQueue } from '../sync/checklistWriteQueue'

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
  version?: string
  updated_at?: string
}

export interface ProjectContext {
  business_category?: string
  applicable_standards?: string[]
  [key: string]: any
}

const VAL_SHEET_MIN = 33

function isValuationItemId(itemId: string): boolean {
  if (!itemId.startsWith('F2-')) return false
  const m = itemId.match(/^F2-(\d+)/)
  if (!m) return false
  return parseInt(m[1], 10) >= VAL_SHEET_MIN
}

export function readValRowJson(resp: ChecklistResponse | undefined): string | null {
  if (!resp) return null
  return resp.remark ?? resp.conclusion ?? null
}

export function useF2ValuationFormData(options: { wpId: Ref<string>; projectId: Ref<string> }) {
  const { wpId, projectId } = options
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const projectContext = ref<ProjectContext>({})
  const sheetCache = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const cas = createChecklistCasClient()
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!wpId.value) throw new Error('缺少底稿标识，无法保存')
      try {
        await cas.save({ wpId: wpId.value, projectId: projectId.value || undefined, items })
      } catch (error) {
        ElMessage.error('保存失败，编辑已保留，请重试')
        throw error
      }
    },
  })

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      cas.remember(responses)
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && isValuationItemId(r.item_id)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F2计价减值数据加载失败')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const data = await api.get(`/api/projects/${projectId.value}`)
      projectContext.value = data || {}
    } catch { /* skip */ }
  }

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=f2-inventory-valuation-impairment`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
        sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
      }
    } catch { /* skip */ }
  }

  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadProjectContext(), selfLoad()])
    } finally {
      isLoading.value = false
    }
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  async function _doSave(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    queue.markMany(items.map((item) => item.item_id))
    await queue.flush()
  }

  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    for (const item of items) allResponses.value.set(item.item_id, item)
    await _doSave(items)
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data }
    allResponses.value.set(itemId, updated)
    queue.mark(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      void queue.flush().catch(() => undefined)
    }, 2000))
  }

  async function _flushPending(): Promise<void> {
    for (const t of _debounceTimers.values()) clearTimeout(t)
    _debounceTimers.clear()
    await queue.flush()
  }

  onScopeDispose(() => { void _flushPending().catch(() => undefined) })

  return {
    allResponses,
    isLoading,
    projectContext,
    sheetCache,
    loadAll,
    getSheet,
    saveItemsFromEvent,
    debouncedSave,
    flushPendingSave: _flushPending,
  }
}

export default useF2ValuationFormData
