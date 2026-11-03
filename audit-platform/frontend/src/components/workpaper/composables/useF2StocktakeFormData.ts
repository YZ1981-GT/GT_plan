/**
 * useF2StocktakeFormData — F2-21~26 监盘数据层
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
}

const STOCKTAKE_ITEM_PREFIX = /^F2-2[1-6]/

export function isStocktakeItemId(itemId: string): boolean {
  return STOCKTAKE_ITEM_PREFIX.test(itemId) || itemId.startsWith('F2-21A')
}

export function useF2StocktakeFormData(options: { wpId: Ref<string>; projectId: Ref<string> }) {
  const { wpId, projectId } = options
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const projectContext = ref<Record<string, unknown>>({})
  const cas = createChecklistCasClient()
  const queue = createChecklistWriteQueue<ChecklistResponse>({
    readLatest: (itemId) => allResponses.value.get(itemId),
    persist: async (items) => {
      if (!wpId.value) throw new Error('缺少底稿标识，无法保存')
      await cas.save({ wpId: wpId.value, projectId: projectId.value, items })
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
        if (r.item_id && isStocktakeItemId(r.item_id)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F2监盘数据加载失败')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      projectContext.value = (await api.get(`/api/projects/${projectId.value}`)) || {}
    } catch { /* skip */ }
  }

  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadProjectContext()])
    } finally {
      isLoading.value = false
    }
  }

  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    for (const item of items) allResponses.value.set(item.item_id, item)
    queue.markMany(items.map((item) => item.item_id))
    await queue.flush()
  }

  async function _flushPending(): Promise<void> {
    await queue.flush()
  }

  onScopeDispose(() => {
    void _flushPending().catch(() => undefined)
  })

  return { allResponses, isLoading, projectContext, loadAll, saveItemsFromEvent, flushPendingSave: _flushPending }
}

export default useF2StocktakeFormData
