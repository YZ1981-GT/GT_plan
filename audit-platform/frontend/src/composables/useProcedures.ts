/**
 * useProcedures — 底稿审计程序管理 composable
 *
 * Sprint 2 Task 2.5: 封装程序清单 CRUD + 裁剪 + 完成标记 + 完成率
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export interface Procedure {
  id: string
  wp_id: string
  project_id: string
  procedure_id: string
  description: string
  category: string
  is_mandatory: boolean
  applicable_project_types: string[] | null
  depends_on: string[] | null
  evidence_type: string | null
  status: string
  completed_by: string | null
  completed_at: string | null
  trimmed_by: string | null
  trimmed_at: string | null
  trim_reason: string | null
  sort_order: number
  created_at: string | null
}

export function useProcedures(projectId: string, wpId: string) {
  const procedures = ref<Procedure[]>([])
  const loading = ref(false)

  const completionRate = computed(() => {
    const applicable = procedures.value.filter(p => p.status !== 'not_applicable')
    if (applicable.length === 0) return 0
    const completed = applicable.filter(p => p.status === 'completed').length
    return Math.round((completed / applicable.length) * 100)
  })

  const groupedByCategory = computed(() => {
    const groups: Record<string, Procedure[]> = {}
    for (const p of procedures.value) {
      const cat = p.category || 'other'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(p)
    }
    return groups
  })

  const basePath = `/api/projects/${projectId}/workpapers/${wpId}/procedures`

  async function fetchProcedures(includeTrimmed = false) {
    loading.value = true
    try {
      const data: any = await api.get(basePath, {
        params: { include_trimmed: includeTrimmed },
      })
      procedures.value = data?.items || []
    } catch (e: any) {
      handleApiError(e, '加载程序清单')
    } finally {
      loading.value = false
    }
  }

  async function markComplete(procId: string, userId: string) {
    try {
      await api.patch(`${basePath}/${procId}/complete`, { user_id: userId })
      // 更新本地状态
      const idx = procedures.value.findIndex(p => p.id === procId)
      if (idx >= 0) {
        procedures.value[idx].status = 'completed'
        procedures.value[idx].completed_by = userId
        procedures.value[idx].completed_at = new Date().toISOString()
      }
    } catch (e: any) {
      handleApiError(e, '标记完成')
    }
  }

  async function trimProcedure(procId: string, reason: string) {
    try {
      await api.patch(`${basePath}/${procId}/trim`, { reason })
      // 从列表中移除（或标记）
      const idx = procedures.value.findIndex(p => p.id === procId)
      if (idx >= 0) {
        procedures.value[idx].status = 'not_applicable'
        procedures.value[idx].trim_reason = reason
      }
    } catch (e: any) {
      handleApiError(e, '裁剪程序')
    }
  }

  async function createCustom(description: string, category = 'custom', evidenceType?: string) {
    try {
      const data: any = await api.post(`${basePath}/custom`, {
        description,
        category,
        evidence_type: evidenceType || null,
      })
      if (data) procedures.value.push(data)
      return data
    } catch (e: any) {
      handleApiError(e, '新增程序')
      return null
    }
  }

  async function copyFromPrior(priorWpId: string) {
    try {
      const data: any = await api.post(`${basePath}/copy-from-prior`, {
        prior_wp_id: priorWpId,
      })
      if (data?.items) {
        procedures.value = data.items
      }
      return data
    } catch (e: any) {
      handleApiError(e, '复制程序')
      return null
    }
  }

  return {
    procedures,
    loading,
    completionRate,
    groupedByCategory,
    fetchProcedures,
    markComplete,
    trimProcedure,
    createCustom,
    copyFromPrior,
  }
}
