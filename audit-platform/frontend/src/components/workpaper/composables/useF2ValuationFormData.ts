/**
 * useF2ValuationFormData — F2 计价减值组数据层（比照 useF2FormData）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
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
  const _pendingItems = new Set<string>()

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
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
    if (!wpId.value || !items.length) return
    try {
      const payload: Record<string, unknown> = {
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      }
      // 空字符串会导致后端 UUID 校验 422；缺省时由服务端按底稿解析 project_id
      if (projectId.value) payload.project_id = projectId.value
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, payload)
    } catch (err: any) {
      // HTTP 层对相同 PUT body 去重会 abort 后发请求；不应提示「保存失败」
      const msg = String(err?.message || '')
      if (msg === 'canceled' || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return
      ElMessage.error('保存失败')
    }
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
    _pendingItems.add(itemId)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([updated])
    }, 2000))
  }

  onScopeDispose(() => {
    for (const t of _debounceTimers.values()) clearTimeout(t)
    if (_pendingItems.size) {
      const items = [..._pendingItems].map((id) => allResponses.value.get(id)).filter(Boolean) as ChecklistResponse[]
      if (items.length) void _doSave(items)
    }
  })

  return {
    allResponses,
    isLoading,
    projectContext,
    sheetCache,
    loadAll,
    getSheet,
    saveItemsFromEvent,
    debouncedSave,
  }
}

export default useF2ValuationFormData
