/**
 * useF2StocktakeFormData — F2-21~26 监盘数据层
 */
import { ref, computed, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

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

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
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
    if (!wpId.value || !items.length) return
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
      project_id: projectId.value,
      items: items.map((i) => ({
        item_id: i.item_id,
        conclusion: i.conclusion,
        remark: i.remark,
      })),
    })
  }

  return { allResponses, isLoading, projectContext, loadAll, saveItemsFromEvent }
}

export default useF2StocktakeFormData
