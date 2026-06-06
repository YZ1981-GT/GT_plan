/**
 * resolveLinkageRoute — 解析 LinkageContract 为可跳转路由
 * MVP: 支持 workpaper (wp_code/wp_id), report (row_code), note (section)
 */
import { api } from '@/services/apiProxy'
import type { LinkageContract } from '@/types/linkageContract'

export async function resolveLinkageRoute(contract: LinkageContract, projectId: string): Promise<string | null> {
  if (contract.route) return contract.route

  switch (contract.target_type) {
    case 'workpaper': {
      const id = contract.target_id
      if (id.match(/^[0-9a-f-]{36}$/)) {
        // UUID format = wp_id
        return `/projects/${projectId}/workpapers/${id}`
      }
      // wp_code format: resolve via API
      try {
        const data: any = await api.get(`/api/projects/${projectId}/wp-index/by-code/${id}`)
        const wpId = data?.working_paper_id || data?.wp_id || data?.id
        if (wpId) return `/projects/${projectId}/workpapers/${wpId}`
      } catch { /* not found */ }
      return null
    }
    case 'report':
      return `/projects/${projectId}/reports?highlight=${contract.target_id}`
    case 'note':
      return `/projects/${projectId}/disclosure-notes?section=${contract.target_id}`
    case 'trial_balance':
      return `/projects/${projectId}/trial-balance?highlight=${contract.target_id}`
    default:
      return null
  }
}
