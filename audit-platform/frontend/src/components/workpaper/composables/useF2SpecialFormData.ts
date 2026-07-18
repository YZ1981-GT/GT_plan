/**
 * useF2SpecialFormData — F2 特殊组数据层
 */
import { ref, computed, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface ProjectContext {
  business_category?: string
  project_type?: string
  template_type?: string
  applicable_standards?: string[]
  [key: string]: any
}

export const IPO_CATEGORIES = ['IPO', '上市公司年审', '新三板', '重大资产重组'] as const

export function isSpecialItemId(itemId: string): boolean {
  if (itemId === 'F2-55A' || itemId === 'F2-61A') return true
  const m = itemId.match(/^F2-(\d+)/)
  if (!m) return false
  const n = parseInt(m[1], 10)
  return (n >= 55 && n <= 58) || (n >= 61 && n <= 72)
}

export function readSpeRowJson(resp: ChecklistResponse | undefined): string | null {
  if (!resp) return null
  return resp.remark ?? resp.conclusion ?? null
}

export function useF2SpecialFormData(options: { wpId: Ref<string>; projectId: Ref<string> }) {
  const { wpId, projectId } = options
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const projectContext = ref<ProjectContext>({})
  const sheetCache = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  // IPO 专项适用性：项目详情接口实际返回 project_type（annual/ipo/…）与
  // template_type（listed/soe），business_category 仅作历史兼容兜底。
  const isIpoProject = computed(() => {
    const ctx = projectContext.value
    if (ctx.project_type === 'ipo') return true
    if (ctx.template_type === 'listed') return true
    return IPO_CATEGORIES.includes(ctx.business_category as typeof IPO_CATEGORIES[number])
  })

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && isSpecialItemId(r.item_id)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F2特殊组数据加载失败')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const res = await api.get(`/api/projects/${projectId.value}`)
      // 项目详情响应为 {code, data, message} 信封，需解包后才能读到 project_type 等字段
      projectContext.value = res?.data ?? res ?? {}
    } catch { /* skip */ }
  }

  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        loadProjectContext(),
        (async () => {
          const res = await api.get(
            `/api/workpapers/${wpId.value}/render-config?force_component_type=f2-inventory-special`,
            { _silent: true } as any,
          )
          const data = res?.data ?? res
          for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }
        })(),
      ])
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

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  onScopeDispose(() => {
    for (const t of _debounceTimers.values()) clearTimeout(t)
  })

  return {
    allResponses,
    isLoading,
    projectContext,
    isIpoProject,
    loadAll,
    saveItemsFromEvent,
    getSheet,
  }
}

export default useF2SpecialFormData
